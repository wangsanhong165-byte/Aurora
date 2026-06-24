"""Brain boundary for the companion AI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generator

from app.character.registry import CharacterRegistry
from app.core.event_bus import bus
from app.core.events import EventType
from app.core.state import state_store, mood_tracker
from app.memory.store import memory_store
from app.tools.registry import ToolRegistry


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
    """The system single decision center."""

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

    def respond(
        self,
        client: Any = None,
        model: str = "",
        user_text: str = "",
        screen_context: str = "",
        temperature: float = 0.3,
        llm_adapter: Any = None,
        record: bool = True,
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
        if record:
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
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": final_reply})
        if len(self.history) > 20:
            self.history = self.history[-20:]

        mood_tracker.update(user_text, final_reply)
        mood_val = mood_tracker.mood
        if mood_val > 65:
            emotion = "happy"
        elif mood_val < 40:
            emotion = "sad"
        else:
            emotion = "neutral"
        state_store.update(emotion=emotion)

        reply_dict = {
            "reply_text": final_reply,
            "intent": "unknown",
            "actions": [],
            "memory": {},
        }
        memory_store.enqueue_turn(user_text, reply_dict)

    def clear_history(self) -> None:
        self.history = []
