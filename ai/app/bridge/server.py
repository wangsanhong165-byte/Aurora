"""Live2D Bridge Server — serves frontend, Live2D models, WebSocket API."""
import asyncio
import io
import json
import logging
import os
import struct
import time
import uuid
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

# Avatar config (loaded from config/avatar.yaml)
_avatar_config: dict[str, Any] | None = None
_avatar_controller: Any = None
_avatar_profiles: dict[str, Any] | None = None

# UI mode tracking
_ui_mode: str = "window"  # "window" or "pet"

# Runtime manager (lazy init)
_manager: Any = None

def _get_manager():
    """Get RuntimeManager singleton."""
    global _manager
    if _manager is None:
        from app.runtime.management import get_manager
        _manager = get_manager()
    return _manager


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


def _load_avatar_profiles() -> dict[str, Any]:
    global _avatar_profiles
    if _avatar_profiles is not None:
        return _avatar_profiles
    profiles_dir = BASE_DIR / "config" / "avatar_profiles"
    _avatar_profiles = {}
    if profiles_dir.exists():
        for path in profiles_dir.glob("*.json"):
            try:
                profile = json.loads(path.read_text("utf-8"))
                profile.setdefault("sequences", ["greet"])
                if profile.get("model"):
                    _avatar_profiles[profile["model"]] = profile
            except Exception as exc:
                logger.warning("[Live2D] Invalid avatar profile %s: %s", path.name, exc)
    return _avatar_profiles


def _load_motion_presets() -> dict[str, Any]:
    presets: dict[str, Any] = {}
    for path in (BASE_DIR / "config" / "motions").glob("*.json"):
        try:
            preset = json.loads(path.read_text("utf-8"))
            presets[preset["name"].lower()] = preset
        except Exception as exc:
            logger.warning("[Live2D] Invalid motion preset %s: %s", path.name, exc)
    return presets


def _build_model_info() -> dict[str, Any]:
    cfg = _load_live2d_config()
    model_cfg = cfg.get(_live2d_model, {})
    return {
        "name": _live2d_model,
        "url": f"/live2d-models/{_live2d_model}/{_live2d_model}.model3.json",
        "emotionMap": model_cfg.get("emotion_map", {}),
        "gestures": model_cfg.get("gestures", []),
        "accessories": model_cfg.get("accessories", {}),
        "behaviorConfig": {
            name: {
                "emotionMap": value.get("emotion_map", {}),
                "behaviorMap": value.get("behavior_map", {}),
                "personality": value.get("personality", {}),
            }
            for name, value in cfg.items()
        },
        "avatarProfiles": _load_avatar_profiles(),
        "motionPresets": _load_motion_presets(),
        "avatar": _load_avatar_config(),
    }


def _load_avatar_config() -> dict[str, Any]:
    """Load avatar configuration from config/avatar.yaml."""
    global _avatar_config
    if _avatar_config is not None:
        return _avatar_config

    config_path = BASE_DIR / "config" / "avatar.yaml"
    if config_path.exists():
        try:
            import yaml
            raw = yaml.safe_load(config_path.read_text("utf-8"))
            _avatar_config = raw or {}
            logger.info("[Avatar] Config loaded: %d models", len(_avatar_config))
        except ImportError:
            logger.warning("[Avatar] PyYAML not installed, trying JSON fallback")
            try:
                import json
                # Try avatar.json as fallback
                json_path = BASE_DIR / "config" / "avatar.json"
                if json_path.exists():
                    _avatar_config = json.loads(json_path.read_text("utf-8"))
                    logger.info("[Avatar] Config loaded from JSON: %d models", len(_avatar_config or {}))
                else:
                    _avatar_config = {}
                    logger.warning("[Avatar] No avatar config found")
            except Exception as exc:
                _avatar_config = {}
                logger.error("[Avatar] Config load failed: %s", exc)
        except Exception as exc:
            _avatar_config = {}
            logger.error("[Avatar] Config load failed: %s", exc)
    else:
        _avatar_config = {}
        logger.warning("[Avatar] config/avatar.yaml not found")
    return _avatar_config or {}


def _get_avatar_controller() -> Any:
    """Get or create the singleton AvatarController."""
    global _avatar_controller
    if _avatar_controller is None:
        from app.avatar.controller import AvatarController
        _avatar_controller = AvatarController()
        cfg = _load_avatar_config()
        _avatar_controller.configure(_live2d_model, cfg)
        # Restore persisted state
        _avatar_controller.restore_state()
        logger.info("[Avatar] Controller initialized for model=%s", _live2d_model)
    return _avatar_controller


def _ensure_env():
    """Ensure .env is loaded exactly once."""
    if os.environ.get("_BRIDGE_ENV_LOADED"):
        return
    from app.core.config import DEFAULT_ENV_PATH, load_env_file
    load_env_file(DEFAULT_ENV_PATH)
    os.environ["_BRIDGE_ENV_LOADED"] = "1"


def _load_character():
    """Load the active character card through CharacterRuntime."""
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
    """Ensure pinned.md exists for the active character. Delegates to RuntimeManager."""
    _get_manager().ensure_pinned()


def _load_pinned_memories() -> str:
    """Return pinned memories content. Delegates to RuntimeManager."""
    return _get_manager().get_pinned()


# ═══════════════════════════════════════════════
#  History Management (JSON file-based)
# ═══════════════════════════════════════════════

def _init_histories() -> None:
    """Ensure histories directory and index exist. Delegates to RuntimeManager."""
    _get_manager()._ensure_dirs()


def _get_history_list() -> list[dict]:
    """Return history list sorted by timestamp desc. Delegates to RuntimeManager."""
    return _get_manager().get_history_list()


def _load_history_messages(uid: str) -> list[dict]:
    """Load messages for a given history uid. Delegates to RuntimeManager."""
    result = _get_manager().load_history(uid)
    return result.get("messages", [])




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
FRONTEND_PUBLIC_DIR = BASE_DIR / "frontend" / "public"
LIVE2D_DIR = BASE_DIR / "models" / "live2d-models"
BACKGROUNDS_DIR = Path(
    os.environ.get("BRIDGE_BACKGROUNDS_DIR",
                   str(BASE_DIR.parent / "Open-LLM-VTuber-1.2.1" / "Open-LLM-VTuber-1.2.1" / "backgrounds"))
)

# ── App ─────────────────────────────────────────────────────────────────
app = FastAPI()


@app.post("/api/tool-confirmations/{request_id}")
async def resolve_tool_confirmation(request_id: str, payload: dict):
    from app.runtime.tool_confirmation import tool_confirmation_broker
    resolved = tool_confirmation_broker.resolve(
        request_id, bool(payload.get("approved", False))
    )
    return {"resolved": resolved}
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


async def _heartbeat_loop() -> None:
    """Background task: periodically prune dead WebSocket relay clients."""
    while True:
        await asyncio.sleep(30)
        if not _ws_clients:
            continue
        dead: list[WebSocket] = []
        for ws in list(_ws_clients):
            try:
                # Send a lightweight heartbeat — raises if client is gone
                await ws.send_text(json.dumps({"type": "heartbeat"}))
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.discard(ws)
        if dead:
            logger.info("[WS Heartbeat] Pruned %d dead client(s) (remaining=%d)", len(dead), len(_ws_clients))


class ExpressionCommand(BaseModel):
    """Request body for POST /live2d/expression"""
    expression: str
    intensity: float = 0.5


class GestureCommand(BaseModel):
    """Request body for POST /live2d/gesture"""
    gesture: str


class AccessoryToggle(BaseModel):
    """Request body for POST /live2d/accessory"""
    name: str
    active: bool = True


@app.post("/live2d/accessory")
async def live2d_accessory(cmd: AccessoryToggle):
    """Toggle a Live2D accessory on/off. Relays to all WS clients."""
    payload = json.dumps({
        "type": "accessory",
        "name": cmd.name,
        "active": cmd.active,
    }, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
    logger.info("Accessory '%s' %s relayed to %d client(s)", cmd.name, "ON" if cmd.active else "OFF", len(_ws_clients))
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    """WebSocket for Live2D control and real-time events."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info("WS client connected: %s (total=%d)", websocket.client, len(_ws_clients))
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # No message for 60s — probe the connection
                try:
                    await websocket.send_text("ping")
                except Exception:
                    break
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
    payload = json.dumps({
        "type": "expression",
        "name": cmd.expression,
        "intensity": cmd.intensity,
    }, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
    logger.info("Expression '%s' sent to %d client(s)", cmd.expression, len(_ws_clients))
    return {"ok": True, "sent": len(_ws_clients)}


@app.post("/live2d/gesture")
async def live2d_gesture(cmd: GestureCommand):
    """Relay Live2D gesture command to all connected WebSocket clients."""
    payload = json.dumps({"type": "gesture", "name": cmd.gesture}, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)
    logger.info("Gesture '%s' sent to %d client(s)", cmd.gesture, len(_ws_clients))
    return {"ok": True, "sent": len(_ws_clients)}


# ── Pinned Memories API ─────────────────────────────────────────

class PinnedBody(BaseModel):
    content: str = ""


@app.get("/api/pinned")
async def get_pinned():
    """Return current pinned memories. Delegates to RuntimeManager."""
    content = _get_manager().get_pinned()
    return {"content": content}


@app.post("/api/pinned")
async def set_pinned(body: PinnedBody):
    """Update pinned memories. Delegates to RuntimeManager."""
    _get_manager().set_pinned(body.content)
    logger.info("[Pinned] Updated (%d chars)", len(body.content))
    return {"ok": True}


# ── History API (used by frontend settings panel) ───────────────

@app.get("/api/histories")
async def api_histories():
    """Return history list. Delegates to RuntimeManager."""
    return {"histories": _get_manager().get_history_list()}


@app.get("/api/histories/{uid}")
async def api_history_detail(uid: str):
    """Return history messages. Delegates to RuntimeManager."""
    result = _get_manager().load_history(uid)
    return {"messages": result.get("messages", [])}


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
    # Start background heartbeat to prune dead WS relay clients
    asyncio.create_task(_heartbeat_loop())


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


# ── V2 Protocol WebSocket ─────────────────────────────────────────────
@app.websocket("/v2/ws")
async def v2_websocket_endpoint(websocket: WebSocket):
    """V2 Runtime Protocol WebSocket.

    Uses the new transport layer with formal protocol types.
    Coexists with legacy /client-ws and /ws endpoints.
    """
    from app.transport.websocket.handler import RuntimeEventHandler
    from app.transport.session import WebSocketSession

    avatar_ctrl = _get_avatar_controller()
    handler = RuntimeEventHandler(avatar_controller=avatar_ctrl)
    session = WebSocketSession(websocket, handler.handle)
    handler.send_message = session.send  # enable assistant_chunk streaming
    handler.enable_proactive_push()       # receive proactive LLM responses
    await session.run()
    handler.disable_proactive_push()      # cleanup on disconnect


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


# ── Settings persistence ─────────────────────────────────────────────────

SETTINGS_FILE = BASE_DIR / "data" / "settings.json"


def _load_settings() -> dict:
    """Load persisted settings from disk, returning defaults if missing."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_settings(settings: dict) -> None:
    """Atomically save settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), "utf-8")
    tmp.replace(SETTINGS_FILE)


@app.get("/api/model-info")
async def get_model_info():
    """Return the same Live2D runtime configuration injected into production HTML."""
    return _build_model_info()


@app.get("/api/settings")
async def get_settings():
    """Return current persisted settings."""
    return {"settings": _load_settings()}


@app.post("/api/settings")
async def save_settings(data: dict):
    """Persist frontend settings."""
    settings = data.get("settings", {})
    if isinstance(settings, dict):
        _save_settings(settings)
        logger.info("[Settings] Saved %d keys", len(settings))
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
    """Send initial configuration to the frontend, including emotion and gesture maps."""
    cfg = _load_live2d_config()
    model_cfg = cfg.get(_live2d_model, {})
    emotion_map = model_cfg.get("emotion_map", {})
    gestures = model_cfg.get("gestures", [])
    accessories = model_cfg.get("accessories", {})
    behavior_config = {
        name: {
            "emotionMap": value.get("emotion_map", {}),
            "behaviorMap": value.get("behavior_map", {}),
            "personality": value.get("personality", {}),
        }
        for name, value in cfg.items()
    }
    avatar_cfg = _load_avatar_config()
    avatar_profiles = _load_avatar_profiles()
    motion_presets = _load_motion_presets()
    await _ws_send(websocket, {
        "type": "set-model-and-conf",
        "conf_name": "default",
        "conf_uid": str(uuid.uuid4()),
        "client_uid": str(uuid.uuid4()),
        "model_info": {
            "name": _live2d_model,
            "url": f"/live2d-models/{_live2d_model}/{_live2d_model}.model3.json",
            "emotionMap": emotion_map,
            "gestures": gestures,
            "accessories": accessories,
            "behaviorConfig": behavior_config,
            "avatarProfiles": avatar_profiles,
            "motionPresets": motion_presets,
            "avatar": avatar_cfg,  # full per-model config
        },
    })


# ── Canonical V3 WebSocket alias ───────────────────────────────────────

@app.websocket("/client-ws")
async def client_websocket_endpoint(websocket: WebSocket):
    """Route the historical public URL through the canonical V3 session."""
    return await v2_websocket_endpoint(websocket)

@app.get("/libs/{rest:path}")
async def serve_libs(rest: str):
    """Serve frontend library files (Cubism Core JS, etc.)."""
    for root in (FRONTEND_DIR, FRONTEND_PUBLIC_DIR):
        target = root / "libs" / rest
        if target.exists() and target.is_file():
            return FileResponse(str(target))
    logger.warning("  -> 404: /libs/%s not found", rest)
    return Response(status_code=404)

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

        # Inject model config into HTML so Live2D renders immediately
        # without waiting for WebSocket set-model-and-conf
        cfg = _load_live2d_config()
        model_cfg = cfg.get(_live2d_model, {})
        emotion_map = model_cfg.get("emotion_map", {})
        gestures = model_cfg.get("gestures", [])
        accessories = model_cfg.get("accessories", {})
        behavior_config = {
            name: {
                "emotionMap": value.get("emotion_map", {}),
                "behaviorMap": value.get("behavior_map", {}),
                "personality": value.get("personality", {}),
            }
            for name, value in cfg.items()
        }
        model_url = f"/live2d-models/{_live2d_model}/{_live2d_model}.model3.json"

        # Inject avatar config for ALL models (not just active) so model
        # switching picks up the correct component/expression/motion definitions.
        avatar_cfg = _load_avatar_config()
        avatar_profiles = _load_avatar_profiles()
        motion_presets = _load_motion_presets()

        inject = (
            '<script>window.__INITIAL_MODEL_INFO__ = '
            + json.dumps({
                "name": _live2d_model,
                "url": model_url,
                "emotionMap": emotion_map,
                "gestures": gestures,
                "accessories": accessories,
                "behaviorConfig": behavior_config,
                "avatarProfiles": avatar_profiles,
                "motionPresets": motion_presets,
                "avatar": avatar_cfg,  # full per-model config
            }, ensure_ascii=False)
            + ';</script>'
        )
        content = content.replace("</head>", inject + "</head>") if "</head>" in content else content + inject
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
    logger.info("  Pinned memories initialized")
    logger.info("  Histories: %d entries", len(_get_manager().get_history_list()))
    logger.info("=" * 44)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
