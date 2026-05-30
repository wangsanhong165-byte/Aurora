import argparse
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.core.config import DEFAULT_ENV_PATH, load_env_file
from app.core.schemas import LLMResponse, PipelineRequest, PipelineResponse, VoiceEvent


DEFAULT_URLS = {
    "RECORDER_URL": "http://127.0.0.1:8010",
    "ASR_URL": "http://127.0.0.1:8000",
    "LLM_URL": "http://127.0.0.1:8020",
    "TTS_URL": "http://127.0.0.1:8030",
    "MEMORY_URL": "http://127.0.0.1:8040",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    response = requests.post(f"{base_url.rstrip('/')}{path}", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def service_url(name: str) -> str:
    return os.environ.get(name, DEFAULT_URLS[name])


def build_event(transcript: str, language: str | None, audio_path: str) -> VoiceEvent:
    return VoiceEvent(
        event_id=str(uuid.uuid4()),
        created_at=utc_now(),
        transcript=transcript,
        language=language,
        metadata={
            "audio_path": audio_path,
            "source": "microphone",
        },
    )


def run_pipeline(request: PipelineRequest) -> PipelineResponse:
    if request.audio_path:
        audio_path = request.audio_path
    else:
        record = post_json(
            service_url("RECORDER_URL"),
            "/v1/audio/record",
            {
                "seconds": request.seconds,
                "sample_rate": request.sample_rate,
            },
        )
        audio_path = record["audio_path"]

    asr = post_json(
        service_url("ASR_URL"),
        "/v1/asr/transcribe",
        {
            "audio_path": audio_path,
            "language": request.language,
        },
    )
    transcript = asr["result"]["text"].strip()
    language = asr["result"].get("language")
    if not transcript:
        raise RuntimeError("ASR returned empty text.")

    event = build_event(transcript, language, audio_path)

    memory = post_json(
        service_url("MEMORY_URL"),
        "/v1/memory/recent",
        {"limit": request.memory_limit},
    )
    llm = post_json(
        service_url("LLM_URL"),
        "/v1/llm/chat",
        {
            "event": event.model_dump(),
            "recent_memory": memory.get("items", []),
        },
    )
    llm_response = LLMResponse(**llm)

    if not request.no_tts:
        tts_payload: dict[str, Any] = {"text": llm_response.reply_text}
        if request.tts_engine:
            tts_payload["engine"] = request.tts_engine
        if request.tts_voice:
            tts_payload["voice"] = request.tts_voice
        if request.tts_emotion:
            tts_payload["emotion"] = request.tts_emotion
        if request.tts_speed is not None:
            tts_payload["speed"] = request.tts_speed
        post_json(service_url("TTS_URL"), "/v1/tts/speak", tts_payload)

    post_json(
        service_url("MEMORY_URL"),
        "/v1/memory/append",
        {
            "event": event.model_dump(),
            "reply": llm_response.model_dump(),
        },
    )

    return PipelineResponse(
        ok=True,
        audio_path=audio_path,
        event=event,
        llm=llm_response,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Voice assistant pipeline orchestrator")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--language", default="Chinese")
    parser.add_argument("--memory-limit", type=int, default=8)
    parser.add_argument("--audio-path", help="Skip recording and use an existing audio file")
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--loop", "--continuous", action="store_true", dest="loop")
    parser.add_argument("--turns", type=int, default=0, help="Maximum loop turns, 0 means unlimited")
    parser.add_argument("--tts-engine", choices=["gsvi", "pyttsx3"])
    parser.add_argument("--tts-voice", help="GPT-SoVITS voice/model name, overrides GSVI_VOICE")
    parser.add_argument("--tts-emotion", help="GPT-SoVITS emotion tag, overrides GSVI_EMOTION")
    parser.add_argument("--tts-speed", type=float)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH)
    return parser.parse_args()


def build_pipeline_request(args: argparse.Namespace) -> PipelineRequest:
    return PipelineRequest(
        seconds=args.seconds,
        sample_rate=args.sample_rate,
        language=args.language,
        memory_limit=args.memory_limit,
        audio_path=args.audio_path,
        no_tts=args.no_tts,
        tts_engine=args.tts_engine,
        tts_voice=args.tts_voice,
        tts_emotion=args.tts_emotion,
        tts_speed=args.tts_speed,
    )


def print_turn(response: PipelineResponse) -> None:
    print(response.model_dump_json(indent=2))
    print(f"\nUser: {response.event.transcript}")
    print(f"Assistant: {response.llm.reply_text}\n")


def main() -> int:
    args = parse_args()
    load_env_file(args.env_file)
    if not args.loop:
        try:
            print_turn(run_pipeline(build_pipeline_request(args)))
            return 0
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

    turn = 0
    print("Continuous voice conversation started. Press Enter for the next turn, or type q to quit.")
    while True:
        command = input("Next turn> ").strip().lower()
        if command in {"q", "quit", "exit"}:
            return 0
        turn += 1
        try:
            print_turn(run_pipeline(build_pipeline_request(args)))
        except Exception as exc:
            print(f"Error: {exc}")
        if args.turns and turn >= args.turns:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
