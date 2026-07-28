"""Structured telemetry event definitions for all pipeline stages.

Maps each pipeline stage to a canonical event name, expected input/output
data, and error conditions for telemetry logging.
"""

from __future__ import annotations

# ── Stage-to-event-name map ──────────────────────────────────────────────

STAGE_EVENTS = {
    "turn.started": "turn_started",
    "turn.completed": "turn_completed",
    "turn.failed": "turn_failed",
    "turn.cancelled": "turn_cancelled",
    "asr.started": "asr_started",
    "asr.completed": "asr_completed",
    "memory.retrieve.started": "memory_retrieve_started",
    "memory.retrieve.completed": "memory_retrieve_completed",
    "prompt.composed": "prompt_composed",
    "llm.started": "llm_started",
    "llm.first_token": "llm_first_token",
    "llm.completed": "llm_completed",
    "tool.started": "tool_started",
    "tool.completed": "tool_completed",
    "intent.created": "intent_created",
    "tts.started": "tts_started",
    "tts.segment.ready": "tts_segment_ready",
    "audio.started": "audio_started",
    "audio.completed": "audio_completed",
    "character.update.sent": "character_update_sent",
    "character.update.received": "character_update_received",
    "action.enqueued": "action_enqueued",
    "motion.started": "motion_started",
    "memory.save.started": "memory_save_started",
    "memory.save.completed": "memory_save_completed",
    "live2d.intent.created": "live2d_intent_created",
}

# ── Error codes ──────────────────────────────────────────────────────────

ERROR_CODES = {
    "asr_failed": "ASR transcription failed",
    "memory_retrieve_failed": "Memory retrieval failed",
    "prompt_compose_failed": "Prompt composition failed",
    "llm_api_error": "LLM API returned an error",
    "llm_timeout": "LLM generation timed out",
    "llm_empty_response": "LLM returned empty response",
    "llm_invalid_json": "LLM produced invalid JSON",
    "tool_execution_failed": "Tool execution failed",
    "tool_timeout": "Tool execution timed out",
    "tool_denied": "Tool execution was denied by user",
    "tts_failed": "TTS synthesis failed",
    "tts_unavailable": "TTS service unavailable",
    "audio_decode_failed": "Audio decoding failed",
    "character_update_failed": "Character update emit failed",
    "pipeline_step_failed": "Pipeline step raised an exception",
    "memory_save_failed": "Memory save failed",
    "turn_cancelled": "Turn was cancelled by interrupt",
    "turn_timeout": "Turn exceeded maximum duration",
    "protocol_error": "Protocol message parse or validation failed",
    "unknown_event": "Unknown or unsupported event type",
}

# ── Sensitive field patterns (redacted from telemetry) ───────────────────

SENSITIVE_KEYS = {
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "credit_card",
    "ssn",
}

# ── Default fields recorded per stage (metadata keys, no sensitive) ──────

STAGE_METADATA: dict[str, list[str]] = {
    "llm.started": ["model", "prompt_tokens"],
    "llm.completed": ["model", "prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens"],
    "tool.started": ["tool_name", "risk"],
    "tool.completed": ["tool_name", "risk", "status"],
    "tts.started": ["voice", "language", "text_length"],
    "tts.completed": ["audio_length_ms", "audio_size_bytes"],
    "memory.retrieve.completed": ["memory_count", "memory_types"],
    "character.update.sent": ["emotion", "behavior"],
    "character.update.received": ["emotion", "behavior"],
    "turn.completed": ["total_duration_ms", "stage_count", "error"],
    "turn.failed": ["error_code", "error_message"],
}
