"""ChatPipeline: text input -> Brain -> output segments -> UI + TTS."""
from __future__ import annotations

import time
from typing import Any, Callable, TYPE_CHECKING

from app.core.event_bus import bus
from app.core.events import EventType

if TYPE_CHECKING:
    from app.brain.service import Brain
    from app.runtime.agent_runtime import AgentRuntime


class ChatPipeline:
    """Orchestrates one turn: input -> Brain -> output segments.

    Hooks:
    - on_segment(tone, zh_text, ja_text): called per segment for UI/portrait update
    - on_tts(text, tone): called to enqueue TTS synthesis
    - on_tool_call(name, args): called when a tool is invoked (optional monitor)
    - on_complete(segments, stats): called when turn is done

    Usage:
        adapter = OpenAILLMAdapter()
        pipeline = ChatPipeline(runtime, llm_adapter=adapter)
        pipeline.on_segment = lambda tone, zh, ja: print(f"[{tone}] {zh}")
        result = pipeline.process("你好")
    """

    def __init__(
        self,
        runtime: "AgentRuntime",
        llm_client: Any = None,
        model: str = "",
        llm_adapter: Any = None,          # preferred: LLMAdapter
        temperature: float = 0.3,
    ) -> None:
        from app.brain.service import Brain  # lazy to avoid circular import

        self.runtime = runtime
        self.client = llm_client
        self.model = model or ""
        self.llm_adapter = llm_adapter
        self.temperature = temperature
        self.brain = Brain(runtime=runtime, character=runtime.character, tools=runtime.tools)
        self.history = self.brain.history

        # Hooks: set these after construction
        self.on_segment: Callable[[str, str, str], None] | None = None
        self.on_tts: Callable[[str, str], None] | None = None
        self.on_tool_call: Callable[[str, dict], None] | None = None
        self.on_complete: Callable[[list, dict], None] | None = None

    # ---- main entry -------------------------------------------------------
    def process(
        self,
        user_text: str,
        screen_context: str = "",
    ) -> dict[str, Any]:
        """Process one user turn. Returns runtime result dict."""
        t0 = time.time()
        bus.publish(EventType.USER_MESSAGE, {"text": user_text}, source="pipeline")
        brain_result = self.brain.respond(
            client=self.client,
            model=self.model,
            user_text=user_text,
            screen_context=screen_context,
            temperature=self.temperature,
            llm_adapter=self.llm_adapter,
        )
        result = brain_result.to_dict()

        segments = result.get("segments", [])
        tool_rounds = result.get("tool_rounds", 0)
        final_reply = result.get("final_reply", "")

        # Fire hooks per segment
        for seg in segments:
            tone = seg.get("tone", "neutral")
            zh = seg.get("zh", "")
            ja = seg.get("ja", "")
            bus.publish(
                EventType.ASSISTANT_SEGMENT,
                {"tone": tone, "zh": zh, "ja": ja},
                source="pipeline",
            )
            if self.on_segment:
                self.on_segment(tone, zh, ja)
            if self.on_tts:
                bus.publish(
                    EventType.TTS_REQUESTED,
                    {"text": zh or ja, "tone": tone},
                    source="pipeline",
                )
                self.on_tts(zh or ja, tone)

        # Fire tool_call hooks (for monitoring)
        if self.on_tool_call and tool_rounds > 0:
            self.on_tool_call("_meta", {"rounds": tool_rounds})

        # Fire completion hook
        stats = {
            "elapsed": result.get("elapsed", time.time() - t0),
            "tool_rounds": tool_rounds,
            "segment_count": len(segments),
        }
        if self.on_complete:
            self.on_complete(segments, stats)
        bus.publish(
            EventType.ASSISTANT_REPLY,
            {"text": final_reply},
            source="pipeline",
        )
        bus.publish(
            EventType.TURN_COMPLETED,
            {"reply": final_reply, "stats": stats},
            source="pipeline",
        )

        return result

    def clear_history(self) -> None:
        self.brain.clear_history()
        self.history = self.brain.history
