from typing import Any

from pydantic import BaseModel, Field


class RecordRequest(BaseModel):
    seconds: float = Field(default=5.0, gt=0)
    sample_rate: int = Field(default=16000, gt=0)
    output_path: str | None = None


class RecordResponse(BaseModel):
    ok: bool
    audio_path: str
    seconds: float
    sample_rate: int


class VADListenRequest(BaseModel):
    sample_rate: int = Field(default=16000, gt=0)
    output_path: str | None = None
    silence_timeout: float = Field(default=1.5, gt=0, description="Seconds of silence before stopping")
    speech_threshold: float = Field(default=0.5, gt=0, le=1.0, description="Fraction of frames that must be voiced to trigger")
    max_duration: float = Field(default=30.0, gt=0, description="Max recording seconds even if still speaking")
    aggressiveness: int = Field(default=2, ge=0, le=3, description="webrtcvad aggressiveness (0=least, 3=most)")


class VADListenResponse(BaseModel):
    ok: bool
    audio_path: str
    duration: float
    sample_rate: int
    triggered: bool


class ASRRequest(BaseModel):
    audio_path: str
    language: str | None = None


class ASRResult(BaseModel):
    text: str
    language: str | None = None


class ASRResponse(BaseModel):
    ok: bool
    audio_path: str | None = None
    filename: str | None = None
    result: ASRResult


class VoiceEvent(BaseModel):
    event_id: str
    type: str = "voice_user_utterance"
    created_at: str
    transcript: str
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecentRequest(BaseModel):
    limit: int = Field(default=8, ge=0)


class MemoryAppendRequest(BaseModel):
    event: VoiceEvent
    reply: dict[str, Any]


class MemoryResponse(BaseModel):
    ok: bool
    items: list[dict[str, Any]] = Field(default_factory=list)


class LLMRequest(BaseModel):
    event: VoiceEvent
    recent_memory: list[dict[str, Any]] = Field(default_factory=list)


class LLMResponse(BaseModel):
    ok: bool
    reply_text: str
    intent: str = "unknown"
    actions: list[dict[str, Any]] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class TTSRequest(BaseModel):
    text: str
    engine: str | None = None
    voice: str | None = None
    emotion: str | None = None
    model: str | None = None
    speed: float | None = None
    text_lang: str | None = None
    prompt_lang: str | None = None
    response_format: str | None = None
    ref_audio_path: str | None = None  # v2pro: reference audio
    prompt_text: str | None = None     # v2pro: transcript of ref audio


class TTSResponse(BaseModel):
    ok: bool
    spoken: bool
    text: str
    engine: str = "pyttsx3"
    voice: str | None = None
    emotion: str | None = None
    audio_path: str | None = None


class PipelineRequest(BaseModel):
    seconds: float = Field(default=5.0, gt=0)
    sample_rate: int = Field(default=16000, gt=0)
    language: str | None = None
    no_tts: bool = False
    memory_limit: int = Field(default=8, ge=0)
    audio_path: str | None = None
    tts_engine: str | None = None
    tts_voice: str | None = None
    tts_emotion: str | None = None
    tts_speed: float | None = None
    vad: bool = False
    vad_silence_timeout: float = Field(default=1.5, gt=0)
    vad_max_duration: float = Field(default=30.0, gt=0)


class PipelineResponse(BaseModel):
    ok: bool
    audio_path: str
    event: VoiceEvent
    llm: LLMResponse

