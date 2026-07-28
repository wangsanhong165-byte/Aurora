"""Pure interpretation of canonical LLM responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.interfaces.llm import LLMResponse
from app.runtime.character_turn import CharacterTurn, PerformancePlan

def _is_renderer_key(key: Any) -> bool:
    normalized = str(key).casefold()
    return (
        normalized.startswith(("param", "cubism"))
        or normalized in {"expression", "motion", "model", "model_id"}
        or normalized.endswith((".exp3", ".model3", ".motion3"))
    )


@dataclass
class InterpretedResponse:
    reply_text: str
    reasoning: str
    segments: list[dict[str, Any]]
    tool_calls: list[Any]
    performance: PerformancePlan
    warnings: list[str] = field(default_factory=list)


class ResponseInterpreter:
    """Normalize an LLMResponse into renderer-independent turn output."""

    def interpret(
        self,
        response: LLMResponse,
        turn: CharacterTurn,
    ) -> InterpretedResponse:
        warnings: list[str] = []
        segments: list[dict[str, Any]] = []
        for raw in response.segments or []:
            cleaned = {
                key: value
                for key, value in dict(raw).items()
                if not _is_renderer_key(key)
            }
            if len(cleaned) != len(raw):
                warnings.append("renderer_details_removed")
            segments.append(cleaned)

        last = segments[-1] if segments else {}
        emotion = str(last.get("emotion", "neutral"))
        behavior = str(last.get("behavior", "speak" if response.reply else ""))
        energy = float(last.get("energy", last.get("intensity", 0.5)))
        performance = PerformancePlan(
            emotion=emotion,
            behavior=behavior,
            attention=str(last.get("attention", "user")),
            energy=max(0.0, min(1.0, energy)),
            speaking=bool(response.reply),
            duration_ms=last.get("duration_ms"),
            context_tags=list(last.get("contextTags", last.get("context_tags", ())))[:8],
        )
        return InterpretedResponse(
            reply_text=response.reply,
            reasoning=response.reasoning,
            segments=segments,
            tool_calls=list(response.tool_calls),
            performance=performance,
            warnings=list(dict.fromkeys(warnings)),
        )
