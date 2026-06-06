"""Brain boundary for the companion AI.

The first implementation delegates model/tool execution to the existing
``AgentRuntime``. The architectural change is ownership: callers talk to Brain,
and Brain talks to state, memory, character, tools, and execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generator, TYPE_CHECKING

from app.character.registry import CharacterRegistry
from app.core.event_bus import bus
from app.core.events import EventType
from app.core.state import state_store
from app.memory.background import memory_worker
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.runtime.agent_runtime import AgentRuntime


@dataclass(slots=True)
class BrainResult:
    segments: list[dict[str, str]]
    final_reply: str
    tool_rounds: int
    elapsed: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments": self.segments,
            "final_reply": self.final_reply,
            "tool_rounds": self.tool_rounds,
            "elapsed": self.elapsed,
        }


class Brain:
    """The system's single decision center."""

    def __init__(
        self,
        character: CharacterRegistry | None = None,
        tools: ToolRegistry | None = None,
        runtime: "AgentRuntime | None" = None,
    ) -> None:
        from app.runtime.agent_runtime import AgentRuntime
        self.character = character or CharacterRegistry()
        self.tools = tools or ToolRegistry()
        self.runtime = runtime or AgentRuntime(character=self.character, tools=self.tools)
        self.history: list[dict[str, str]] = []

    # ---- non-streaming respond -------------------------------------------
    def respond(
        self,
        client: Any = None,
        model: str = "",
        user_text: str = "",
        screen_context: str = "",
        temperature: float = 0.3,
        llm_adapter: Any = None,
    ) -> BrainResult:
        bus.publish(
            EventType.BRAIN_STARTED,
            {"input": user_text, "state": state_store.snapshot()},
            source="brain",
        )
        result = self.runtime.run(
            client=client,
            model=model,
            user_text=user_text,
            history=self.history,
            screen_context=screen_context,
            temperature=temperature,
            llm_adapter=llm_adapter,
        )
        final_reply = result.get("final_reply", "")
        self._record_turn(user_text, final_reply)

        bus.publish(
            EventType.BRAIN_FINISHED,
            {"reply": final_reply, "tool_rounds": result.get("tool_rounds", 0)},
            source="brain",
        )
        return BrainResult(
            segments=result.get("segments", []),
            final_reply=final_reply,
            tool_rounds=int(result.get("tool_rounds", 0)),
            elapsed=float(result.get("elapsed", 0.0)),
        )

    # ---- streaming respond -----------------------------------------------
    def respond_stream(
        self,
        llm_adapter: Any,
        user_text: str = "",
        screen_context: str = "",
        temperature: float = 0.3,
    ) -> Generator[str, None, BrainResult]:
        import time
        t0 = time.time()

        bus.publish(
            EventType.BRAIN_STARTED,
            {"input": user_text, "state": state_store.snapshot()},
            source="brain",
        )

        system = self.runtime.build_system(screen_context)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_text})

        full_reply: list[str] = []
        stream_gen = llm_adapter.generate_stream(messages, temperature=temperature)
        try:
            for token in stream_gen:
                full_reply.append(token)
                yield token
        except Exception:
            pass

        final_reply = "".join(full_reply)
        try:
            stream_result = stream_gen.throw(GeneratorExit)
        except (StopIteration, GeneratorExit, RuntimeError):
            stream_result = {}
        except Exception:
            stream_result = {}
        if isinstance(stream_result, dict) and stream_result.get("content"):
            final_reply = stream_result["content"]

        self._record_turn(user_text, final_reply)

        elapsed = time.time() - t0
        bus.publish(
            EventType.BRAIN_FINISHED,
            {"reply": final_reply, "streaming": True},
            source="brain",
        )
        return BrainResult(segments=[], final_reply=final_reply, tool_rounds=0, elapsed=elapsed)

    def _record_turn(self, user_text: str, final_reply: str) -> None:
        """Record a turn in history, update emotion, enqueue memory work."""
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": final_reply})
        if len(self.history) > 20:
            self.history = self.history[-20:]

        # Auto-infer emotion from conversation
        from app.core.emotion import emotion_tracker
        emotion = emotion_tracker.infer(user_text, final_reply)
        state_store.update(emotion=emotion)

        reply_dict = {
            "reply_text": final_reply,
            "intent": "unknown",
            "actions": [],
            "memory": {},
        }
        memory_worker.enqueue_turn(user_text, reply_dict)

    def clear_history(self) -> None:
        self.history = []
