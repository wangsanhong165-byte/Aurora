"""Normalize model presentation output before TTS and memory."""

import re
from dataclasses import dataclass

from app.runtime.character_intent import BEHAVIORS, EMOTIONS, CharacterIntent


@dataclass
class ValidatedResponse:
    reply: str
    segments: list[dict]
    valid: bool = True


class ResponseValidator:
    def validate(self, reply: str, segments: list[dict] | None) -> ValidatedResponse:
        missing_structured = bool(
            reply and not segments and len(self._split_sentences(str(reply))) > 1
        )
        malformed_structured = bool(
            reply and str(reply).lstrip().startswith(("{", "["))
            and not segments
        )
        normalized = []
        for raw in segments or []:
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            emotion = str(raw.get("emotion", "neutral")).lower()
            behavior = str(raw.get("behavior", "speak")).lower()
            if emotion not in EMOTIONS:
                emotion = "neutral"
            if behavior not in BEHAVIORS or behavior == "idle":
                behavior = "speak"
            item = dict(raw)
            item.update({
                "text": text,
                "emotion": emotion,
                "behavior": behavior,
                "energy": self._clamp(raw.get("energy", 0.5)),
                "intensity": self._clamp(raw.get("intensity", 0.5)),
            })
            motion_plan = CharacterIntent._motion_plan(
                raw.get("motionPlan", raw.get("motion_plan"))
            )
            item.pop("motion_plan", None)
            if motion_plan is None:
                item.pop("motionPlan", None)
            else:
                item["motionPlan"] = motion_plan
            normalized.append(item)
        if normalized:
            reply = " ".join(item["text"] for item in normalized)
        elif reply:
            reply = str(reply).strip()
            if reply:
                if reply.startswith(("{", "[")):
                    reply = "I couldn't format that response safely."
                normalized = self._recover_semantic_segments(reply)
        # An empty reply (no spoken text and no non-empty segments) is never a
        # legitimate completion for a voice companion: it is either truncation
        # (finish_reason="length", reasoning consumed the budget) or the model
        # silently emitted no content. Mark it invalid so the pipeline repairs
        # it instead of presenting silence as success.
        valid = (
            not malformed_structured
            and not missing_structured
            and bool(normalized or str(reply or "").strip())
        )
        return ValidatedResponse(
            str(reply or "").strip(), normalized, valid,
        )

    @classmethod
    def _recover_semantic_segments(cls, reply: str) -> list[dict]:
        """Conservative fallback when a provider drops the JSON envelope.

        The first validation remains invalid so DecisionStep asks the LLM for
        one structured repair. These renderer-independent segments are retained
        only if that repair also fails; no Cubism or model-specific names are
        inferred here.
        """
        sentences = cls._split_sentences(reply)
        if not sentences:
            sentences = [reply]
        return [cls._recover_sentence(sentence) for sentence in sentences]

    @staticmethod
    def _split_sentences(reply: str) -> list[str]:
        return [
            match.group(0).strip()
            for match in re.finditer(r"[^。！？!?]+[。！？!?]?", reply)
            if match.group(0).strip()
        ][:6]

    @staticmethod
    def _recover_sentence(text: str) -> dict:
        lowered = text.casefold()
        emotion = "neutral"
        behavior = "speak"
        energy = 0.5
        intensity = 0.5

        if any(token in lowered for token in ("害羞", "紧张", "不好意思", "脸红", "shy", "nervous")):
            emotion, energy, intensity = "shy", 0.35, 0.48
        elif any(token in lowered for token in ("开心", "高兴", "乐意", "期待", "happy", "glad", "excited")):
            emotion, energy, intensity = "happy", 0.68, 0.62
        elif any(token in lowered for token in ("难过", "伤心", "悲伤", "sad", "sorry to hear")):
            emotion, energy, intensity = "sad", 0.3, 0.55
        elif any(token in lowered for token in ("生气", "愤怒", "angry", "mad")):
            emotion, energy, intensity = "angry", 0.75, 0.68
        elif any(token in lowered for token in (
            "没关系", "慢慢来", "放心", "已经很好", "做得很好", "相信你",
            "it's okay", "take your time", "you can do it",
        )):
            emotion, behavior, energy, intensity = "calm", "comfort", 0.38, 0.52

        if any(token in lowered for token in ("你好", "您好", "嗨", "来啦", "见到你", "hello", "hi ")):
            behavior = "greet"
        elif any(token in lowered for token in ("谢谢", "赞同", "同意", "没错", "thank", "agree")):
            behavior = "agree"

        return {
            "text": text,
            "emotion": emotion,
            "behavior": behavior,
            "attention": "user",
            "energy": energy,
            "intensity": intensity,
            "contextTags": ["semantic_recovery"],
        }

    @staticmethod
    def _clamp(value) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5
