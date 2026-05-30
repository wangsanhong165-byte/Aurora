import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from openai import OpenAI

from app.core.config import DEFAULT_ENV_PATH, load_env_file
from app.core.schemas import LLMRequest, LLMResponse


app = FastAPI(title="Cloud LLM Adapter API", version="1.0.0")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def get_api_key() -> tuple[str, str]:
    key_env = os.environ.get("LLM_API_KEY_ENV", "DEEPSEEK_API_KEY")
    api_key = os.environ.get(key_env) or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError(f"Missing API key. Set {key_env} or LLM_API_KEY.")
    return api_key, key_env


def extract_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(content[start : end + 1])


def build_messages(request: LLMRequest) -> list[dict[str, str]]:
    system_prompt = os.environ.get(
        "LLM_SYSTEM_PROMPT",
        (
            "你是语音助手。只返回JSON。要求：1~2句话，口语化，有停顿感。禁止\"请问\"、\"您是否\"、\"明白了\"、\"很高兴\"这类客服话术。用户是说话不是写作文，允许\"嗯\"\"对\"\"这个\"等碎片表达，结合上下文理解，不要立即追问。用户说\"打开微信\"就直接说\"好，打开微信\"，不要反问确认。"
            "JSON schema: {"
            '"reply_text": "natural language response to speak to the user", '
            '"intent": "short intent name", '
            '"actions": [{"type": "action name", "args": {}}], '
            '"memory": {"summary": "short memory summary", "facts": []}'
            "}."
        ),
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(request.model_dump(), ensure_ascii=False)},
    ]


def build_extra_body() -> dict[str, Any] | None:
    extra_body: dict[str, Any] = {}

    thinking_type = os.environ.get("LLM_THINKING_TYPE", "enabled").strip().lower()
    if thinking_type and thinking_type not in {"none", "off", "disabled"}:
        extra_body["thinking"] = {"type": thinking_type}

    raw_extra_body = os.environ.get("LLM_EXTRA_BODY_JSON")
    if raw_extra_body:
        extra_body.update(json.loads(raw_extra_body))

    return extra_body or None


def call_cloud_llm(request: LLMRequest) -> LLMResponse:
    api_key, _ = get_api_key()
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
    reasoning_effort = os.environ.get("LLM_REASONING_EFFORT", "high")
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.3"))
    response_format = os.environ.get("LLM_RESPONSE_FORMAT", "json_object")
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    params: dict[str, Any] = {
        "model": model,
        "messages": build_messages(request),
        "stream": False,
        "temperature": temperature,
    }
    if reasoning_effort:
        params["reasoning_effort"] = reasoning_effort
    if response_format and response_format.lower() not in {"none", "off", "disabled"}:
        params["response_format"] = {"type": response_format}

    extra_body = build_extra_body()
    if extra_body:
        params["extra_body"] = extra_body

    response = client.chat.completions.create(**params)
    content = response.choices[0].message.content or ""
    parsed = extract_json(content)

    return LLMResponse(
        ok=True,
        reply_text=str(parsed.get("reply_text", "")).strip(),
        intent=str(parsed.get("intent", "unknown")),
        actions=parsed.get("actions") or [],
        memory=parsed.get("memory") or {},
        raw=parsed,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    key_env = os.environ.get("LLM_API_KEY_ENV", "DEEPSEEK_API_KEY")
    return {
        "ok": True,
        "module": "llm",
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"),
        "model": os.environ.get("LLM_MODEL", "deepseek-v4-pro"),
        "api_key_env": key_env,
        "has_api_key": bool(os.environ.get(key_env) or os.environ.get("LLM_API_KEY")),
        "reasoning_effort": os.environ.get("LLM_REASONING_EFFORT", "high"),
        "thinking_type": os.environ.get("LLM_THINKING_TYPE", "enabled"),
    }


@app.post("/v1/llm/chat", response_model=LLMResponse)
def chat(request: LLMRequest) -> LLMResponse:
    try:
        return call_cloud_llm(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Cloud LLM adapter API service")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8020)
    args = parser.parse_args()

    load_env_file(Path(args.env_file))

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()


