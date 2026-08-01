"""Pure interpretation of canonical LLM responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.interfaces.llm import LLMResponse
from app.runtime.character_turn import CharacterTurn, PerformancePlan
from app.runtime.character_intent import CharacterIntent

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

        dominant = max(
            enumerate(segments),
            key=lambda item: (
                float(item[1].get("intensity", 0.5)),
                float(item[1].get("energy", item[1].get("intensity", 0.5))),
                -item[0],
            ),
        )[1] if segments else {}
        intent = CharacterIntent.from_llm_segment(dominant)
        performance = PerformancePlan(
            emotion=intent.emotion,
            behavior=intent.behavior or ("speak" if response.reply else ""),
            intensity=intent.intensity,
            attention=intent.attention,
            energy=intent.energy,
            speaking=bool(response.reply),
            duration_ms=intent.duration_ms,
            context_tags=list(intent.context_tags),
            motion_plan=intent.motion_plan,
        )
        return InterpretedResponse(
            reply_text=response.reply,
            reasoning=response.reasoning,
            segments=segments,
            tool_calls=list(response.tool_calls),
            performance=performance,
            warnings=list(dict.fromkeys(warnings)),
        )
