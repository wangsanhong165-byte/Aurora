import argparse
import json
import os
import sys
import time
import uuid
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_DIR = BASE_DIR / "Qwen3-ASR-1.7B"
DEFAULT_MEMORY_PATH = BASE_DIR / "memory.short.jsonl"
DEFAULT_AUDIO_PATH = BASE_DIR / "last_recording.wav"
DEFAULT_ENV_PATH = BASE_DIR / ".env"


@dataclass
class VoiceEvent:
    event_id: str
    type: str
    created_at: str
    transcript: str
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloudReply:
    reply_text: str
    intent: str = "unknown"
    actions: list[dict[str, Any]] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_module(module_name: str, install_hint: str) -> Any:
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise RuntimeError(f"缺少依赖 {module_name}。请先安装：{install_hint}") from exc


def record_microphone(output_path: Path, seconds: float, sample_rate: int) -> Path:
    sounddevice = require_module("sounddevice", "pip install sounddevice soundfile")
    soundfile = require_module("soundfile", "pip install sounddevice soundfile")

    print(f"开始录音 {seconds:g} 秒，请说话...")
    audio = sounddevice.rec(
        int(seconds * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
    )
    sounddevice.wait()
    soundfile.write(str(output_path), audio, sample_rate)
    print(f"录音已保存：{output_path}")
    return output_path


def transcribe_local(audio_path: Path, model_dir: Path, language: str | None) -> tuple[str, str | None]:
    torch = require_module("torch", "按你的 CUDA 版本安装 PyTorch")
    qwen_asr = require_module("qwen_asr", "pip install -U qwen-asr")

    if not model_dir.exists():
        raise RuntimeError(f"找不到 ASR 模型目录：{model_dir}")

    device_map = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    print(f"加载本地 ASR：{model_dir} ({device_map})")
    model = qwen_asr.Qwen3ASRModel.from_pretrained(
        str(model_dir),
        dtype=dtype,
        device_map=device_map,
        max_inference_batch_size=1,
        max_new_tokens=256,
    )
    results = model.transcribe(audio=str(audio_path), language=language)
    first = results[0]
    transcript = getattr(first, "text", "").strip()
    detected_language = getattr(first, "language", None)
    print(f"ASR: [{detected_language}] {transcript}")
    return transcript, detected_language


def build_event(transcript: str, language: str | None, audio_path: Path) -> VoiceEvent:
    return VoiceEvent(
        event_id=str(uuid.uuid4()),
        type="voice_user_utterance",
        created_at=utc_now(),
        transcript=transcript,
        language=language,
        metadata={
            "audio_path": str(audio_path),
            "source": "microphone",
        },
    )


def load_recent_memory(memory_path: Path, limit: int) -> list[dict[str, Any]]:
    if not memory_path.exists():
        return []
    rows = []
    with memory_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]


def call_cloud_llm(event: VoiceEvent, memory: list[dict[str, Any]]) -> CloudReply:
    api_key = os.environ.get("LLM_API_KEY")
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4.1-mini")

    if not api_key:
        raise RuntimeError("缺少环境变量 LLM_API_KEY。也可以设置 LLM_BASE_URL 和 LLM_MODEL。")

    system_prompt = (
        "你是一个语音助手。必须只返回 JSON，不要 Markdown。"
        "JSON schema: {"
        '"reply_text": "给用户播放的自然语言回复", '
        '"intent": "简短意图名", '
        '"actions": [{"type": "动作名", "args": {}}], '
        '"memory": {"summary": "可写入短期记忆的摘要", "facts": []}'
        "}。"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "event": asdict(event),
                        "recent_memory": memory,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)

    return CloudReply(
        reply_text=str(parsed.get("reply_text", "")).strip(),
        intent=str(parsed.get("intent", "unknown")),
        actions=parsed.get("actions") or [],
        memory=parsed.get("memory") or {},
        raw=parsed,
    )


def speak_local(text: str) -> None:
    if not text:
        return
    try:
        pyttsx3 = require_module("pyttsx3", "pip install pyttsx3")
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        print(f"TTS 播放失败：{exc}")
        print(f"reply_text: {text}")


def append_memory(memory_path: Path, event: VoiceEvent, reply: CloudReply) -> None:
    record = {
        "created_at": utc_now(),
        "event": asdict(event),
        "reply": {
            "reply_text": reply.reply_text,
            "intent": reply.intent,
            "actions": reply.actions,
            "memory": reply.memory,
        },
    }
    with memory_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"短期记忆已写入：{memory_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地 ASR + 云端 LLM + 本地 TTS 语音助手")
    parser.add_argument("--seconds", type=float, default=5.0, help="麦克风录音秒数")
    parser.add_argument("--sample-rate", type=int, default=16000, help="录音采样率")
    parser.add_argument("--language", default=None, help='ASR 语言提示，例如 "Chinese" 或 "English"')
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR, help="Qwen3-ASR 模型目录")
    parser.add_argument("--audio-path", type=Path, default=DEFAULT_AUDIO_PATH, help="录音 wav 保存路径")
    parser.add_argument("--memory-path", type=Path, default=DEFAULT_MEMORY_PATH, help="短期记忆 JSONL 路径")
    parser.add_argument("--memory-limit", type=int, default=8, help="发给 LLM 的最近记忆条数")
    parser.add_argument("--skip-record", type=Path, help="跳过录音，直接识别指定音频文件")
    parser.add_argument("--no-tts", action="store_true", help="不播放 TTS，只打印 reply_text")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_PATH, help="LLM 环境变量文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start = time.time()
    load_env_file(args.env_file)

    try:
        audio_path = args.skip_record or record_microphone(args.audio_path, args.seconds, args.sample_rate)
        transcript, detected_language = transcribe_local(audio_path, args.model_dir, args.language)
        if not transcript:
            raise RuntimeError("ASR 没有识别到文本。")

        event = build_event(transcript, detected_language, audio_path)
        print("事件 JSON:")
        print(json.dumps(asdict(event), ensure_ascii=False, indent=2))

        recent_memory = load_recent_memory(args.memory_path, args.memory_limit)
        reply = call_cloud_llm(event, recent_memory)
        print("云端结构化 JSON:")
        print(json.dumps(reply.raw, ensure_ascii=False, indent=2))

        if args.no_tts:
            print(f"reply_text: {reply.reply_text}")
        else:
            speak_local(reply.reply_text)

        append_memory(args.memory_path, event, reply)
        print(f"完成，用时 {time.time() - start:.1f}s")
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
