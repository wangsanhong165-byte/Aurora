"""Live2D Bridge Server — serves frontend, Live2D models, WebSocket API."""
import asyncio
import io
import json
import logging
import os
import struct
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import FileResponse

# Character card state (used by switch-character)
_char_card: dict[str, Any] | None = None
_char_name: str = "Monika"

# Live2D expression config (loaded from config/live2d_models.json)
_live2d_config: dict[str, Any] | None = None
_live2d_model: str = "Design_genius_White"

# UI mode tracking
_ui_mode: str = "window"  # "window" or "pet"

# Conversation history for LLM context
_conversation_history: list[dict[str, str]] = []
MAX_HISTORY = 5  # keep last 5 exchanges (user + assistant = 1 exchange)

# Pinned memories
_PINNED_PATH: Path | None = None
_PINNED_CACHE: str = ""

# History management
_HISTORIES_DIR: Path | None = None
_CURRENT_HISTORY_UID: str = ""
_HISTORY_INDEX_CACHE: dict[str, dict] = {}


def _load_live2d_config() -> dict[str, Any]:
    """Load Live2D expression mapping from config/live2d_models.json."""
    global _live2d_config, _live2d_model
    if _live2d_config is not None:
        return _live2d_config

    import json
    config_path = BASE_DIR / "config" / "live2d_models.json"
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text("utf-8"))
            _live2d_config = raw
            # Determine active model: env var > first available > default
            env_model = os.environ.get("LIVE2D_MODEL", "")
            available = sorted(d.name for d in LIVE2D_DIR.iterdir() if d.is_dir()) if LIVE2D_DIR.exists() else []
            if env_model and env_model in available and env_model in raw:
                _live2d_model = env_model
            else:
                for m in ["Design_genius_White", "youxiaomiao", "ariu"]:
                    if m in available and m in raw:
                        _live2d_model = m
                        break
                else:
                    _live2d_model = available[0] if available else _live2d_model
            emotions = raw.get(_live2d_model, {}).get("prompt_emotions", [])
            logger.info("[Live2D] Config loaded: model=%s, emotions=%d", _live2d_model, len(emotions))
        except Exception as exc:
            logger.error("[Live2D] Config load failed: %s", exc)
    return _live2d_config or {}


def _ensure_env():
    """Ensure .env is loaded exactly once."""
    if os.environ.get("_BRIDGE_ENV_LOADED"):
        return
    from app.core.config import DEFAULT_ENV_PATH, load_env_file
    load_env_file(DEFAULT_ENV_PATH)
    os.environ["_BRIDGE_ENV_LOADED"] = "1"


def _load_character():
    """Load active character card via CompanionRuntime."""
    global _char_card, _char_name
    if _char_card is not None:
        return

    try:
        from app.runtime.runtime import runtime
        info = runtime.get_character_info()
        _char_card = info.get("card", {})
        _char_name = info.get("name", "AI")
        logger.info("[Character] Loaded: %s", _char_name)
    except Exception as exc:
        logger.error("[Character] Load failed: %s", exc)


# ═══════════════════════════════════════════════
# ═══════════════════════════════════════════════
#  Pinned Memories
# ═══════════════════════════════════════════════

def _init_pinned() -> None:
    """Ensure pinned.md exists for the active character."""
    global _PINNED_PATH, _PINNED_CACHE
    cid = _char_card.get("id", "monika") if _char_card else "monika"
    path = BASE_DIR / "config" / "characters" / cid / "pinned.md"
    _PINNED_PATH = path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    _PINNED_CACHE = path.read_text("utf-8").strip()


def _load_pinned_memories() -> str:
    """Return pinned memories content, refreshing cache if needed."""
    global _PINNED_CACHE
    if _PINNED_PATH and _PINNED_PATH.exists():
        _PINNED_CACHE = _PINNED_PATH.read_text("utf-8").strip()
    return _PINNED_CACHE


# ═══════════════════════════════════════════════
#  History Management (JSON file-based)
# ═══════════════════════════════════════════════

def _init_histories() -> None:
    """Ensure histories directory and index exist."""
    global _HISTORIES_DIR, _HISTORY_INDEX_CACHE
    _HISTORIES_DIR = BASE_DIR / "data" / "memory" / "histories"
    _HISTORIES_DIR.mkdir(parents=True, exist_ok=True)
    index_path = _HISTORIES_DIR / "index.json"
    if index_path.exists():
        try:
            _HISTORY_INDEX_CACHE = json.loads(index_path.read_text("utf-8"))
        except Exception:
            _HISTORY_INDEX_CACHE = {}
    else:
        _HISTORY_INDEX_CACHE = {}
        index_path.write_text("{}", encoding="utf-8")


def _save_history_index() -> None:
    """Persist history index to disk."""
    if _HISTORIES_DIR:
        (_HISTORIES_DIR / "index.json").write_text(
            json.dumps(_HISTORY_INDEX_CACHE, ensure_ascii=False), encoding="utf-8"
        )


def _get_history_list() -> list[dict]:
    """Return history list sorted by timestamp desc, for frontend."""
    result = []
    for uid, info in _HISTORY_INDEX_CACHE.items():
        latest = info.get("latest_message")
        result.append({
            "uid": uid,
            "latest_message": latest,
            "timestamp": info.get("timestamp", ""),
        })
    result.sort(key=lambda x: x["timestamp"], reverse=True)
    return result


def _load_history_messages(uid: str) -> list[dict]:
    """Load messages for a given history uid."""
    if not _HISTORIES_DIR:
        return []
    path = _HISTORIES_DIR / f"{uid}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return []


def _save_to_current_history(user_text: str, assistant_text: str) -> None:
    """Save an exchange to the current history."""
    global _CURRENT_HISTORY_UID
    if not _HISTORIES_DIR:
        return
    # Auto-create history if none exists
    if not _CURRENT_HISTORY_UID:
        _CURRENT_HISTORY_UID = f"hist_{uuid.uuid4().hex[:12]}"
    uid = _CURRENT_HISTORY_UID

    # Load existing messages
    messages = _load_history_messages(uid)
    now = datetime.now(timezone.utc).isoformat()
    messages.append({"role": "user", "content": user_text, "timestamp": now})
    messages.append({"role": "assistant", "content": assistant_text, "timestamp": now})

    # Write
    (_HISTORIES_DIR / f"{uid}.json").write_text(
        json.dumps(messages, ensure_ascii=False), encoding="utf-8"
    )

    # Update index
    _HISTORY_INDEX_CACHE[uid] = {
        "timestamp": now,
        "latest_message": {"content": assistant_text[:100], "role": "assistant", "timestamp": now},
    }
    _save_history_index()




def _float32_to_wav(samples: list[float], sample_rate: int = 16000) -> bytes:
    """Convert float32 samples (list of floats in [-1, 1]) to WAV bytes."""
    num_channels = 1
    bits_per_sample = 16
    block_align = num_channels * bits_per_sample // 8
    byte_rate = sample_rate * block_align
    data_size = len(samples) * block_align

    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))  # chunk size
    buf.write(struct.pack("<H", 1))   # PCM
    buf.write(struct.pack("<H", num_channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    for sample in samples:
        buf.write(struct.pack("<h", max(-32768, min(32767, int(sample * 32767)))))
    return buf.getvalue()


# ── Logger ──────────────────────────────────────────────────────────────
logger = logging.getLogger("bridge")
logger.setLevel(logging.DEBUG)
_ch = logging.StreamHandler()
_ch.setLevel(logging.DEBUG)
_ch.setFormatter(logging.Formatter("[Bridge] %(asctime)s.%(msecs)03d %(levelname)-5s %(message)s", datefmt="%H:%M:%S"))
logger.handlers.clear()
logger.addHandler(_ch)

# ── Paths ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"
LIVE2D_DIR = BASE_DIR / "models" / "live2d-models"
BACKGROUNDS_DIR = Path(
    os.environ.get("BRIDGE_BACKGROUNDS_DIR",
                   str(BASE_DIR.parent / "Open-LLM-VTuber-1.2.1" / "Open-LLM-VTuber-1.2.1" / "backgrounds"))
)

# ── App ─────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Utilities ───────────────────────────────────────────────────────────
def _elapsed_s(t0: float) -> str:
    return f"{time.perf_counter() - t0:.3f}s"


# ── WebSocket Client Manager ────────────────────────────────────────────
_ws_clients: set[WebSocket] = set()


class ExpressionCommand(BaseModel):
    """Request body for POST /live2d/expression"""
    expression: str


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket for Live2D control and real-time events."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("WS client connected: %s (total=%d)", websocket.client, len(_ws_clients))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info("WS client disconnected (total=%d)", len(_ws_clients))


@app.post("/live2d/expression")
async def live2d_expression(cmd: ExpressionCommand):
    """Relay Live2D expression command to all connected WebSocket clients.

    Uses the emotion_map from live2d_models.json to translate raw emotion
    names to frontend expression names. Falls back to the first available
    expression if the emotion is not mapped.
    """
    cfg = _load_live2d_config()
    model_cfg = cfg.get(_live2d_model, {})
    emotion_map = model_cfg.get("emotion_map", {})

    # Translate through emotion_map; fall back to raw if not found
    expression_name = emotion_map.get(cmd.expression, cmd.expression)

    payload = json.dumps({"type": "expression", "name": expression_name}, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
    logger.info("Expression '%s' → '%s' sent to %d client(s)", cmd.expression, expression_name, len(_ws_clients))
    return {"ok": True, "sent": len(_ws_clients)}


# ── Pinned Memories API ─────────────────────────────────────────

class PinnedBody(BaseModel):
    content: str = ""


@app.get("/api/pinned")
async def get_pinned():
    """Return current pinned memories."""
    content = _load_pinned_memories()
    return {"content": content}


@app.post("/api/pinned")
async def set_pinned(body: PinnedBody):
    """Update pinned memories."""
    global _PINNED_CACHE
    _PINNED_CACHE = body.content
    if _PINNED_PATH:
        _PINNED_PATH.write_text(body.content, encoding="utf-8")
    logger.info("[Pinned] Updated (%d chars)", len(body.content))
    return {"ok": True}


# ── History API (used by frontend settings panel) ───────────────

@app.get("/api/histories")
async def api_histories():
    return {"histories": _get_history_list()}


@app.get("/api/histories/{uid}")
async def api_history_detail(uid: str):
    return {"messages": _load_history_messages(uid)}


# ── Model Switcher Injection ────────────────────────────────────────────
MODEL_SWITCHER_SCRIPT = None


def _get_model_switcher_script():
    """Model switcher now lives in the React settings panel (live2d.tsx).
    This function is kept as a no-op to avoid breaking the injection point
    in serve_index()."""
    return ""


# ── API Endpoints ───────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    """Initialize background services on server start."""
    logger.info("Server starting")


@app.get("/health")
def health():
    ok = {
        "ok": True,
        "module": "bridge",
        "frontend": FRONTEND_DIR.exists(),
        "live2d": LIVE2D_DIR.exists(),
    }
    logger.debug("Health check: %s", ok)
    return ok


@app.get("/api/models")
async def list_models():
    if not LIVE2D_DIR.exists():
        return {"models": []}
    models = []
    for d in sorted(LIVE2D_DIR.iterdir()):
        if d.is_dir():
            model3 = d / f"{d.name}.model3.json"
            models.append({"name": d.name, "hasModel3": model3.exists()})
    return {"models": models}


# ── Set Model Endpoint ─────────────────────────────────────────────────

@app.post("/api/set-model")
async def set_model(data: dict):
    """Receive model selection from frontend before page reload."""
    global _live2d_model
    name = data.get("model", "")
    cfg = _load_live2d_config()
    if name and name in cfg:
        _live2d_model = name
        logger.info("[Live2D] Model switched to: %s", name)
    return {"status": "ok"}


@app.post("/api/set-mode")
async def set_mode(data: dict):
    """Receive UI mode from frontend."""
    global _ui_mode
    mode = data.get("mode", "")
    if mode in ("window", "pet"):
        _ui_mode = mode
        logger.info("[Mode] UI mode set to: %s", mode)
    return {"status": "ok"}


# ── WebSocket Helpers ───────────────────────────────────────────────────

async def _ws_send(websocket: WebSocket, msg: dict) -> None:
    """Send a JSON message to a WebSocket client."""
    try:
        await websocket.send_text(json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass


# Per-client audio buffers: {client_id: {"samples": [float, ...], "sample_rate": int}}
_mic_buffers: dict[str, dict] = {}


def _get_mic_buffer(client_id: str) -> dict:
    if client_id not in _mic_buffers:
        _mic_buffers[client_id] = {"samples": [], "sample_rate": 16000}
    return _mic_buffers[client_id]


# ── Initialization ──────────────────────────────────────────────────────

async def _send_init_conf(websocket: WebSocket) -> None:
    """Send initial configuration to the frontend, including emotion map."""
    cfg = _load_live2d_config()
    model_cfg = cfg.get(_live2d_model, {})
    emotion_map = model_cfg.get("emotion_map", {})
    await _ws_send(websocket, {
        "type": "set-model-and-conf",
        "conf_name": "default",
        "conf_uid": str(uuid.uuid4()),
        "client_uid": str(uuid.uuid4()),
        "model_info": {
            "name": _live2d_model,
            "url": f"/live2d-models/{_live2d_model}/{_live2d_model}.model3.json",
            "emotionMap": emotion_map,
        },
    })


# ── Client-WS Endpoint ──────────────────────────────────────────────────

@app.websocket("/runtime-ws")
async def runtime_websocket_endpoint(websocket: WebSocket):
    """Alternate WebSocket endpoint that routes through CompanionRuntime.dispatch().

    Opt-in by connecting to ws://host:port/runtime-ws instead of /client-ws.
    Handles the same message types but uses the v2 Pipeline internally.
    """
    from app.bridge.runtime_handler import RuntimeWebSocketHandler
    handler = RuntimeWebSocketHandler()

    await websocket.accept()
    await _send_init_conf(websocket)
    logger.info("[RuntimeWS] New connection")

    ws_id = f"rws_{id(websocket)}"
    _mic_buffers[ws_id] = {"samples": [], "sample_rate": 16000}

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "text-input":
                user_text = str(msg.get("text", "")).strip()
                if user_text:
                    await handler.handle_text(websocket, user_text)

            elif msg_type == "mic-audio-data":
                audio_data = msg.get("audio", [])
                buf = _mic_buffers.get(ws_id)
                if buf:
                    buf["samples"].extend(float(v) for v in audio_data)

            elif msg_type == "mic-audio-end":
                buf = _mic_buffers.pop(ws_id, None)
                if buf and buf["samples"]:
                    import struct
                    samples = buf["samples"]
                    sr = buf["sample_rate"]
                    wav_bytes = _float32_to_wav(samples, sr)
                    await handler.handle_voice(websocket, wav_bytes, sr)

            elif msg_type == "ai-speak-signal":
                idle_time = float(msg.get("idle_time", 5))
                await handler.handle_proactive(websocket, idle_time)

            elif msg_type == "ping":
                await websocket.send_text("pong")

            # All other message types (fetch-backgrounds, history, etc.)
            # fall through to the legacy handler for now
            elif msg_type in ("fetch-backgrounds", "fetch-configs",
                              "fetch-history-list", "fetch-and-set-history",
                              "create-new-history", "delete-history",
                              "switch-character", "reload-prompts"):
                # Delegate to legacy handler for non-core messages
                pass  # These are handled by REST API endpoints in production

    except WebSocketDisconnect:
        _mic_buffers.pop(ws_id, None)
        logger.info("[RuntimeWS] disconnected")
    except Exception as e:
        _mic_buffers.pop(ws_id, None)
        logger.error("[RuntimeWS] error: %s", e)


@app.websocket("/client-ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint — routes core interaction through CompanionRuntime.dispatch().

    Thin transport layer: text-input, mic-audio-end, and ai-speak-signal are
    forwarded to RuntimeWebSocketHandler which calls Runtime.dispatch().
    All other message types (history, backgrounds, config) are handled inline.
    """
    from app.bridge.runtime_handler import RuntimeWebSocketHandler
    handler = RuntimeWebSocketHandler()

    logger.info("New WebSocket: %s", websocket.client)
    t0 = time.perf_counter()
    ws_id = f"ws_{id(websocket)}"
    await websocket.accept()
    logger.info("WebSocket accepted in %s", _elapsed_s(t0))
    # Send initial config to properly initialize frontend state
    await _send_init_conf(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(raw)
                continue

            msg_type = msg.get("type", "")

            if msg_type == "text-input":
                user_text = str(msg.get("text", "")).strip()
                if user_text:
                    await handler.handle_text(websocket, user_text)

            elif msg_type == "mic-audio-data":
                # Buffer audio chunk
                audio_data = msg.get("audio", [])
                buf = _get_mic_buffer(ws_id)
                buf["samples"].extend(float(v) for v in audio_data)

            elif msg_type == "mic-audio-end":
                buf = _mic_buffers.pop(ws_id, None)
                if buf and buf["samples"]:
                    samples = buf["samples"]
                    sr = buf["sample_rate"]
                    wav_bytes = _float32_to_wav(samples, sr)
                    await handler.handle_voice(websocket, wav_bytes, sr)

            elif msg_type == "ping":
                await _ws_send(websocket, {"type": "pong"})

            elif msg_type == "ai-speak-signal":
                idle_time = float(msg.get("idle_time", 5))
                logger.info("[Proactive] Triggered (idle=%.0fs)", idle_time)
                await handler.handle_proactive(websocket, idle_time)

            elif msg_type == "fetch-backgrounds":
                files = []
                bg_dir = BACKGROUNDS_DIR
                if bg_dir.exists():
                    files = sorted(f.name for f in bg_dir.iterdir() if f.is_file())
                await _ws_send(websocket, {"type": "background-files", "files": files})

            elif msg_type == "fetch-configs":
                await _ws_send(websocket, {"type": "config-files", "configs": []})

            elif msg_type == "fetch-history-list":
                histories = _get_history_list()
                await _ws_send(websocket, {"type": "history-list", "histories": histories})

            elif msg_type == "fetch-and-set-history":
                uid = str(msg.get("history_uid", ""))
                if uid:
                    global _CURRENT_HISTORY_UID, _conversation_history
                    _CURRENT_HISTORY_UID = uid
                    messages = _load_history_messages(uid)
                    # Restore conversation history from loaded messages
                    _conversation_history = []
                    for m in messages:
                        _conversation_history.append({"role": m["role"], "content": m["content"]})
                    await _ws_send(websocket, {"type": "history-data", "messages": messages})

            elif msg_type == "create-new-history":
                uid = f"hist_{uuid.uuid4().hex[:12]}"
                _CURRENT_HISTORY_UID = uid
                _conversation_history = []
                now = datetime.now(timezone.utc).isoformat()
                _HISTORY_INDEX_CACHE[uid] = {"timestamp": now, "latest_message": None}
                _save_history_index()
                await _ws_send(websocket, {
                    "type": "new-history-created",
                    "history_uid": uid,
                })

            elif msg_type == "delete-history":
                uid = str(msg.get("history_uid", ""))
                if uid and _HISTORIES_DIR:
                    path = _HISTORIES_DIR / f"{uid}.json"
                    if path.exists():
                        path.unlink()
                    _HISTORY_INDEX_CACHE.pop(uid, None)
                    _save_history_index()
                    await _ws_send(websocket, {"type": "history-deleted", "success": True, "history_uid": uid})
                else:
                    await _ws_send(websocket, {"type": "history-deleted", "success": False, "history_uid": uid})

            elif msg_type == "switch-character":
                char_id = str(msg.get("character_id", "")).strip()
                if char_id:
                    logger.info("[Switch] Switching to character: %s", char_id)
                    from app.runtime.runtime import runtime
                    result = runtime.switch_character(char_id)
                    if "error" in result:
                        logger.error("[Switch] Failed: %s", result["error"])
                    else:
                        global _char_card, _char_name
                        info = runtime.get_character_info()
                        _char_card = info.get("card", {})
                        _char_name = info.get("name", "AI")
                        logger.info("[Switch] Character switched to: %s", _char_name)

                    _conversation_history = []
                    _CURRENT_HISTORY_UID = ""
                    # Re-init character-specific state
                    _init_pinned()
                    _init_histories()
                    # Clear prompt template cache
                    from app.prompts.loader import reload_cache as _reload_prompts
                    _reload_prompts()
                    # Send new config to frontend
                    await _send_init_conf(websocket)
                    logger.info("[Switch] Character switched to: %s", _char_name)
                    await _ws_send(websocket, {
                        "type": "character-switched",
                        "character_id": char_id,
                        "character_name": _char_name,
                    })
                else:
                    await _ws_send(websocket, {"type": "error", "message": "switch-character requires character_id"})

            elif msg_type == "reload-prompts":
                """Hot-reload prompt template files without restart."""
                from app.prompts.loader import reload_cache as _reload_prompts
                _reload_prompts()
                logger.info("[Prompts] Cache cleared (prompts will reload on next use)")
                await _ws_send(websocket, {"type": "prompts-reloaded"})

            else:
                # Unknown type: echo back for debugging
                await websocket.send_text(raw)

    except WebSocketDisconnect:
        # Clean up mic buffer if any
        _mic_buffers.pop(ws_id, None)
        logger.info("WebSocket disconnected after %s", _elapsed_s(t0))
    except Exception as e:
        _mic_buffers.pop(ws_id, None)
        logger.error("WebSocket error: %s", e)


# ── Static File Serving ─────────────────────────────────────────────────

@app.get("/live2d-models/{rest:path}")
async def serve_live2d(rest: str):
    """Serve Live2D model files (model3.json, textures, moc3, etc.)."""
    logger.info("Live2D request: %s", rest)
    target = LIVE2D_DIR / rest
    if target.exists() and target.is_file():
        sz = target.stat().st_size
        logger.debug("  -> serving %s (%d bytes)", rest, sz)
        headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        return FileResponse(str(target), headers=headers)
    logger.warning("  -> 404: %s not found in Live2D models", rest)
    return Response(status_code=404)


@app.get("/bg/{rest:path}")
async def serve_background(rest: str):
    target = BACKGROUNDS_DIR / rest
    if target.exists() and target.is_file():
        return FileResponse(str(target))
    return Response(status_code=404)


@app.get("/")
async def serve_index():
    from starlette.responses import HTMLResponse

    logger.info("Serving index.html")
    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        logger.info("  -> found (%d bytes)", index.stat().st_size)
        content = index.read_text(encoding="utf-8")
        return HTMLResponse(content, headers=cache_headers)
    logger.error("  -> NOT FOUND at %s", index)
    return {"error": "frontend not built"}


@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve frontend static assets, fallback to index.html for SPA routing."""
    logger.debug("Static request: %s", path)
    target = FRONTEND_DIR / path
    if target.exists() and target.is_file():
        logger.debug("  -> serving %s (%d bytes)", path, target.stat().st_size)
        cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        return FileResponse(str(target), headers=cache_headers)
    if path.startswith(".well-known/"):
        return Response(status_code=404)
    if any(ext in path for ext in (".model3.json", ".moc3", ".exp3.json", ".physics3", ".pose3", ".cdi3", ".motion3.json")):
        logger.warning("  -> 404: model file %s not found", path)
        return Response(status_code=404)
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return Response(status_code=404)


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import shutil
    import uvicorn

    port = int(os.environ.get("BRIDGE_PORT", "9528"))
    logger.info("Starting uvicorn on port %d", port)
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not found. Install for audio chunk/volume support:")

    logger.info("=" * 44)
    logger.info("  Bridge server starting up")
    logger.info("  Frontend: %s  (exists=%s)", FRONTEND_DIR, FRONTEND_DIR.exists())
    logger.info("  Live2D:   %s  (exists=%s)", LIVE2D_DIR, LIVE2D_DIR.exists())
    if LIVE2D_DIR.exists():
        models = sorted(d.name for d in LIVE2D_DIR.iterdir() if d.is_dir())
        logger.info("  Live2D models: %s", models)
    assets = list(FRONTEND_DIR.glob("assets/*")) if FRONTEND_DIR.exists() else []
    logger.info("  Frontend assets (%d files):", len(assets))
    for a in assets:
        logger.debug("   . %s", a.name)
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        logger.info("  index.html: found (%d bytes)", index.stat().st_size)
    # Load live2d config
    cfg = _load_live2d_config()
    model_cfg = cfg.get(_live2d_model, {})
    logger.info("  Live2D active model: %s (%d emotions)", _live2d_model, len(model_cfg.get("prompt_emotions", [])))
    # Init subsystems
    _ensure_env()
    _load_character()
    _init_pinned()
    _init_histories()
    logger.info("  Pinned memories: %s", _PINNED_PATH if _PINNED_PATH else "none")
    logger.info("  Histories: %d entries", len(_HISTORY_INDEX_CACHE))
    logger.info("=" * 44)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
