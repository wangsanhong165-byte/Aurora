import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from app.core.config import DEFAULT_MEMORY_PATH
from app.core.schemas import MemoryAppendRequest, MemoryRecentRequest, MemoryResponse


app = FastAPI(title="Short Memory API", version="1.0.0")
_memory_path = DEFAULT_MEMORY_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_memory(limit: int) -> list[dict[str, Any]]:
    if not _memory_path.exists():
        return []

    rows = []
    with _memory_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:] if limit else []


def append_memory(request: MemoryAppendRequest) -> None:
    _memory_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": utc_now(),
        "event": request.event.model_dump(),
        "reply": request.reply,
    }
    with _memory_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "module": "memory", "memory_path": str(_memory_path)}


@app.post("/v1/memory/recent", response_model=MemoryResponse)
def recent(request: MemoryRecentRequest) -> MemoryResponse:
    try:
        return MemoryResponse(ok=True, items=read_memory(request.limit))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/v1/memory/append")
def append(request: MemoryAppendRequest) -> dict[str, Any]:
    try:
        append_memory(request)
        return {"ok": True, "memory_path": str(_memory_path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def main() -> None:
    global _memory_path

    parser = argparse.ArgumentParser(description="Short memory API service")
    parser.add_argument("--memory-path", type=Path, default=DEFAULT_MEMORY_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8040)
    args = parser.parse_args()
    _memory_path = args.memory_path

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
