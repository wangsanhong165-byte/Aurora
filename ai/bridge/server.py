"""OLV Frontend Bridge Server -- serves frontend + WebSocket protocol translation."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import tempfile
import time
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from app.memory.ticker import MemoryTicker

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

# ------------------------------------------------------------------ #
#  Logging setup
# ------------------------------------------------------------------ #
logger = logging.getLogger("bridge")
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "[Bridge] %(asctime)s.%(msecs)03d %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
))
logger.addHandler(_handler)

def _elapsed_s(start: float) -> str:
    ms = (time.perf_counter() - start) * 1000
    return f"{ms:.0f}ms"

def _marker(msg: str):
    logger.info("\u2500" * 6 + " " + msg)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    logger.info("=" * 44)
    logger.info("  Bridge server starting up")
    logger.info("  Frontend: %s  (exists=%s)", FRONTEND_DIR, FRONTEND_DIR.exists())
    logger.info("  Live2D:   %s  (exists=%s)", LIVE2D_DIR, LIVE2D_DIR.exists())
    if LIVE2D_DIR.exists():
        models = [p.name for p in LIVE2D_DIR.iterdir() if p.is_dir()]
        logger.info("  Live2D models: %s", models if models else "(none)")
    assets = FRONTEND_DIR / "assets"
    if assets.exists():
        files = [f.name for f in assets.iterdir() if f.is_file()]
        logger.info("  Frontend assets (%d files):", len(files))
        for f in files:
            logger.debug("    . %s", f)
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        logger.info("  index.html: found (%d bytes)", index.stat().st_size)
    else:
        logger.warning("  index.html: NOT FOUND!")
    logger.info("=" * 44)
    yield
    # --- shutdown ---
    logger.info("Bridge server shutting down")


class BridgeHandler:
    """Handles one WebSocket client session. Loads backend adapters lazily."""

    def __init__(self):
        self._id = datetime.now(timezone.utc).strftime("%H%M%S%f")[-8:]
        logger.info("[%s] BridgeHandler created", self._id)
        self.audio_buffer = bytearray()
        self.interrupted = False
        self.current_task = None
        self.websocket = None
        self._audio_chunks = 0
        self._last_route_time = 0.0
        self._ws_closed = False
        # Backend adapters -- lazy to avoid import errors when backends are down
        self._brain = None
        self._llm_adapter = None
        self._asr_url = os.environ.get("ASR_URL", "http://127.0.0.1:8000")
        self._tts_url = os.environ.get("TTS_URL", "http://127.0.0.1:8030")
        logger.info("[%s]  Config: ASR=%s  TTS=%s", self._id, self._asr_url, self._tts_url)
        self._ticker: MemoryTicker | None = None

    async def _safe_send(self, data: dict) -> None:
        """Send JSON only if WebSocket is still connected."""
        if self._ws_closed or self.websocket is None:
            logger.debug("[%s]  Skipping send, ws closed", self._id)
            return
        try:
            await self.websocket.send_json(data)
        except Exception:
            logger.debug("[%s]  Send failed (ws probably closed)", self._id)
            self._ws_closed = True

    # ------------------------------------------------------------------ #
    #  Lazy backend loader
    # ------------------------------------------------------------------ #
    @property
    def brain(self):
        if self._brain is None:
            t0 = time.perf_counter()
            logger.info("[%s]  Loading Brain...", self._id)
            from app.brain.service import Brain
            from app.character.registry import CharacterRegistry
            from app.tools.registry import ToolRegistry
            self._brain = Brain(
                character=CharacterRegistry(),
                tools=ToolRegistry(),
            )
            logger.info("[%s]  Brain loaded in %s", self._id, _elapsed_s(t0))
            # Start memory ticker
            if self._ticker is None:
                self._ticker = MemoryTicker()
            self._ticker.set_llm_adapter(self._llm_adapter)
            self._ticker.start()
            self._ticker.recover()
        return self._brain

    @property
    def llm_adapter(self):
        if self._llm_adapter is None:
            t0 = time.perf_counter()
            logger.info("[%s]  Loading LLM adapter...", self._id)
            from app.models.http_adapters import OpenAILLMAdapter
            self._llm_adapter = OpenAILLMAdapter()
            logger.info("[%s]  LLM adapter loaded in %s", self._id, _elapsed_s(t0))
        return self._llm_adapter

    # ------------------------------------------------------------------ #
    #  Main handler
    # ------------------------------------------------------------------ #
    async def handle(self, ws: WebSocket):
        _marker("WebSocket connected [%s]" % self._id)
        logger.info("[%s]  Client: %s", self._id, ws.client)
        self.websocket = ws
        await self._send_init()
        try:
            while True:
                raw = await ws.receive_json()
                logger.debug("[%s]  WS recv: type=%s  keys=%s", self._id, raw.get("type"), list(raw.keys()))
                await self._route(raw)
        except WebSocketDisconnect:
            logger.info("[%s] WebSocket disconnected", self._id)
            self._ws_closed = True
            if self._ticker:
                self._ticker.notify_session_end()
            if self.current_task and not self.current_task.done():
                logger.info("[%s]  Cancelling pending task", self._id)
                self.current_task.cancel()
        except json.JSONDecodeError as exc:
            logger.error("[%s] WS JSON decode error: %s", self._id, exc)
        except asyncio.CancelledError:
            logger.info("[%s] WS handler cancelled", self._id)
        except Exception as exc:
            logger.error("[%s] WS handler error: %s\n%s", self._id, exc, traceback.format_exc())
    # ------------------------------------------------------------------ #
    #  Init messages
    # ------------------------------------------------------------------ #
    async def _send_init(self):
        _marker("Sending init config to frontend [%s]" % self._id)
        info = {
            "type": "set-model-and-conf",
            "model_info": {
                "name": "youxiaomiao",
                "url": "http://127.0.0.1:9528/live2d-models/youxiaomiao/youxiaomiao.model3.json",
                "kScale": 0.5,
                "initialXshift": 0,
                "initialYshift": -0,
                "kXOffset": 0,
                "idleMotionGroupName": "Idle",
                "emotionMap": {
                    "neutral": 0, "joy": 1, "anger": 2, "sadness": 3, "surprise": 4,
                },
                "tapMotions": {},
                "pointerInteractive": True,
                "scrollToResize": True,
            },
            "conf_name": "youxiaomiao",
            "conf_uid": "youxiaomiao_001",
            "client_uid": "monika-client",
        }
        await self._safe_send(info)
        logger.debug("[%s]  -> set-model-and-conf sent (%s)", self._id, info["model_info"]["name"])
        # Small delay so the frontend can initialize the Live2D renderer
        greeting = "Okaeri, welcome back~ (click mic to start)"
        await self.websocket.send_json({"type": "full-text", "text": greeting})
        logger.info("[%s]  -> greeting sent: %s", self._id, greeting)
        # Tell frontend to start microphone
        await self.websocket.send_json({"type": "control", "text": "start-mic"})
        logger.info("[%s]  -> start-mic sent", self._id)

    # ------------------------------------------------------------------ #
    #  Message router
    # ------------------------------------------------------------------ #
    async def _route(self, data: dict):
        """Route incoming WS message to handler 闁?OLV Web compatible protocol."""
        msg_type = data.get("type", "")
        now = time.perf_counter()
        if self._last_route_time > 0:
            gap = (now - self._last_route_time) * 1000
            if gap > 100:
                logger.debug("[%s]  Gap since last route: %.0fms", self._id, gap)
        self._last_route_time = now

        # ---- heartbeat keepalive ----
        if msg_type == "heartbeat":
            await self.websocket.send_json({"type": "heartbeat-ack"})
            return

        # ---- init config request (frontend ready) ----
        if msg_type == "request-init-config":
            logger.info("[%s]  Frontend ready, re-sending model config", self._id)
            await self._send_init()
            return

        # ---- fetch history list ----
        if msg_type == "fetch-history-list":
            await self.websocket.send_json({
                "type": "history-list", "histories": []
            })
            return

        # ---- create new history ----
        if msg_type == "create-new-history":
            import uuid
            history_uid = str(uuid.uuid4())[:8]
            await self.websocket.send_json({
                "type": "new-history-created", "history_uid": history_uid,
            })
            return

        # ---- fetch configs ----
        if msg_type == "fetch-configs":
            logger.info("[%s]  fetch-configs", self._id)
            await self.websocket.send_json({
                "type": "config-files", "configs": []
            })
            return

        # ---- switch config ----
        if msg_type == "switch-config":
            logger.info("[%s]  switch-config: file=%s", self._id, data.get("file"))
            return  # single character, no-op

        # ---- fetch backgrounds ----
        if msg_type == "fetch-backgrounds":
            bg_files = []
            bg_dir = BACKGROUNDS_DIR
            if bg_dir and bg_dir.exists():
                bg_files = [f.name for f in bg_dir.iterdir() if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
                logger.info("[%(id)s]  Backgrounds: %(len)d files from %(dir)s", {"id": self._id, "len": len(bg_files), "dir": bg_dir})
            await self.websocket.send_json({
                "type": "background-files", "files": bg_files
            })
            return

        # ---- audio data streaming ----
        if msg_type == "mic-audio-data":
            audio_floats = data.get("audio", [])
            if audio_floats:
                self._audio_chunks += 1
                chunk_len = len(audio_floats)
                import numpy as np
                int16_data = (np.array(audio_floats, dtype=np.float32) * 32767).astype(np.int16)
                self.audio_buffer.extend(int16_data.tobytes())
                buf_sec = len(self.audio_buffer) / 32000
                if self._audio_chunks <= 5 or self._audio_chunks % 20 == 0:
                    logger.info("[%s]  Audio chunk #%d: %d floats -> buffer=%.1fsec",
                                self._id, self._audio_chunks, chunk_len, buf_sec)
            return

        # ---- voice input end ----
        if msg_type == "mic-audio-end":
            buf_sec = len(self.audio_buffer) / 32000
            logger.info("[%s] mic-audio-end: chunks=%d buffer=%.1fsec",
                        self._id, self._audio_chunks, buf_sec)
            if self.current_task and not self.current_task.done():
                self.current_task.cancel()
            self.current_task = asyncio.create_task(self._process_audio())
            return

        # ---- raw audio data (browser VAD) ----
        if msg_type == "raw-audio-data":
            logger.debug("[%s] raw-audio-data: %d values", self._id, len(data.get("audio", [])))
            return

        # ---- text input ----
        if msg_type == "text-input":
            text = data.get("text", "").strip()
            logger.info("[%s] text-input: len=%d preview=%s", self._id, len(text), text[:80])
            if text and (not self.current_task or self.current_task.done()):
                self.current_task = asyncio.create_task(self._process_text(text))
            else:
                busy = self.current_task and not self.current_task.done()
                logger.debug("[%s]  Text skipped (busy=%s, empty=%s)", self._id, busy, not text)
            return

        # ---- AI speak signal (proactive) ----
        if msg_type == "ai-speak-signal":
            logger.info("[%s] ai-speak-signal", self._id)
            if not self.current_task or self.current_task.done():
                self.current_task = asyncio.create_task(self._process_proactive())
            return

        # ---- client info ----
        if msg_type == "client-info":
            info = data.get("info", {})
            logger.info("[%s] client-info: %s", self._id, json.dumps(info, ensure_ascii=False))
            return

        # ---- interrupt ----
        if msg_type in ("interrupt", "interrupt-signal"):
            logger.info("[%s] interrupt signal", self._id)
            self.interrupted = True
            if self.current_task and not self.current_task.done():
                self.current_task.cancel()
            await self.websocket.send_json({"type": "control", "text": "interrupt"})
            return

        # ---- audio play start (group sync) ----
        if msg_type == "audio-play-start":
            return

        # ---- frontend playback complete ----
        if msg_type == "frontend-playback-complete":
            return

        # ---- unknown ----
        logger.debug("[%s] Unhandled WS type: %s", self._id, msg_type)
    async def _process_audio(self):
        _marker("Processing audio [%s]" % self._id)
        t_start = time.perf_counter()
        import requests as http
        import numpy as np
        from scipy.io import wavfile

        buf_len = len(self.audio_buffer)
        logger.info("[%s]  Audio buffer: %d bytes (%.1f sec)", self._id, buf_len, buf_len / 32000)

        # Write buffer to temp WAV for ASR
        tmp_wav = Path(tempfile.gettempdir()) / f"_bridge_asr_{self._id}.wav"
        try:
            wavfile.write(str(tmp_wav), 16000, np.frombuffer(self.audio_buffer, dtype=np.int16))
        except Exception as exc:
            logger.error("[%s]  WAV write failed: %s", self._id, exc)
            await self._safe_send({
                "type": "full-text",
                "text": "Sorry, audio processing failed.",
            })
            self.audio_buffer.clear()
            return

        # Transcribe via ASR
        t_asr = time.perf_counter()
        try:
            resp = http.post(
                f"{self._asr_url}/v1/asr/transcribe",
                json={"audio_path": str(tmp_wav)},
                timeout=120,
            )
            resp.encoding = "utf-8"
            asr_dur = _elapsed_s(t_asr)
            logger.info("[%s]  ASR: status=%d dur=%s", self._id, resp.status_code, asr_dur)
            if resp.status_code != 200:
                logger.error("[%s]  ASR error: %s", self._id, resp.text[:200])
                await self.websocket.send_json({
                    "type": "full-text",
                    "text": f"ASR error: {resp.status_code}",
                })
                return
            result = resp.json()
            text = result.get("result", {}).get("text", "").strip()
            logger.info("[%s]  ASR result: len=%d text=%s", self._id, len(text), text[:120])
            if not text:
                logger.info("[%s]  ASR returned empty, skipping", self._id)
                await self.websocket.send_json({
                    "type": "full-text",
                    "text": "",
                })
                return
        except requests.exceptions.ConnectionError:
            logger.error("[%s]  ASR connection refused at %s", self._id, self._asr_url)
            await self._safe_send({
                "type": "full-text",
                "text": "ASR service unavailable.",
            })
            return
        except Exception as exc:
            logger.error("[%s]  ASR error: %s\n%s", self._id, exc, traceback.format_exc())
            await self._safe_send({
                "type": "full-text",
                "text": "ASR error.",
            })
            return
        finally:
            self.audio_buffer.clear()
            self._audio_chunks = 0
            try:
                tmp_wav.unlink(missing_ok=True)
            except Exception:
                pass
            logger.debug("[%s]  Audio buffer cleared, temp file removed", self._id)

        # Now call brain + stream
        await self._process_text(text)
        total_dur = _elapsed_s(t_start)
        logger.info("[%s]  Audio pipeline total: %s", self._id, total_dur)

    # ------------------------------------------------------------------ #
    #  Text pipeline
    # ------------------------------------------------------------------ #
    async def _process_text(self, text: str):
        _marker("Processing text [%s]" % self._id)
        logger.info("[%s]  Input: %s", self._id, text[:200] if text else "(empty/proactive)")
        await self.websocket.send_json({"type": "control", "text": "conversation-chain-start"})
        try:
            await self._brain_call_and_stream(text)
        except Exception as exc:
            logger.error("[%s]  Brain error: %s\n%s", self._id, exc, traceback.format_exc())
            await self._safe_send({
                    "type": "full-text",
                    "text": "I'm sorry, something went wrong.",
                })
        finally:
            await self._safe_send({"type": "conversation-chain-end"})
            await self._safe_send({"type": "backend-synth-complete"})
            logger.info("[%s]  Text processing done", self._id)

    async def _brain_call_and_stream(self, text: str):
        """Call brain, stream segments, and synthesize TTS for each."""
        import numpy as np
        import requests as http

        self.interrupted = False
        t_brain = time.perf_counter()
        loop = asyncio.get_event_loop()

        def _brain_call():
            return self.brain.respond(
                user_text=text,
                temperature=0.3,
                llm_adapter=self.llm_adapter,
            )

        logger.info("[%s]  Invoking brain.respond()...", self._id)
        result = await loop.run_in_executor(None, _brain_call)
        brain_dur = _elapsed_s(t_brain)
        logger.info("[%s]  Brain responded in %s", self._id, brain_dur)

        # Notify memory ticker
        if self._ticker:
            self._ticker.notify_turn()

        if self.interrupted:
            logger.info("[%s]  Interrupted after brain, skipping output", self._id)
            return

        segments = result.segments
        reply = result.final_reply
        logger.info("[%s]  Brain result: %d segments, final=%s",
                     self._id, len(segments), (reply[:80] if reply else "(none)"))

        if not segments:
            logger.info("[%s]  No segments, using final_reply", self._id)
            if reply:
                await self.websocket.send_json({"type": "full-text", "text": reply})
                t_tts = time.perf_counter()
                try:
                    tts_resp = http.post(
                        f"{self._tts_url}/v1/tts/synthesize",
                        json={"text": reply},
                        timeout=60,
                    )
                    logger.info("[%s]  TTS single: %d in %s  preview=%s",
                                self._id, tts_resp.status_code, _elapsed_s(t_tts), reply[:60])
                    if tts_resp.status_code == 200:
                        await self._send_audio(tts_resp.content, "neutral", reply, "none")
                except Exception as exc:
                    logger.warning("[%s]  TTS single failed: %s", self._id, exc)
            return

        # Determine TTS language from character config
        try:
            char_card = self.brain.character.active
            native_lang = char_card.get("tts", {}).get("prompt_lang", "ja")
        except Exception:
            native_lang = "ja"
        logger.info("[%s]  TTS lang: %s", self._id, native_lang)

        for i, seg in enumerate(segments):
            if self.interrupted:
                logger.info("[%s]  Interrupted during segment %d", self._id, i)
                break
            tone = seg.get("tone", "neutral")
            gesture = seg.get("gesture", "none")
            display_text = seg.get("zh", "") or seg.get("en", "") or ""
            tts_text = (
                seg.get(native_lang, "")
                or seg.get("en", "")
                or seg.get("ja", "")
                or display_text
            )

            if display_text:
                logger.debug("[%s]  Segment %d: tone=%s display=%s", self._id, i, tone, display_text[:60])
                await self.websocket.send_json({
                    "type": "full-text",
                    "text": display_text,
                })

            if tts_text:
                t_tts = time.perf_counter()
                try:
                    tts_resp = http.post(
                        f"{self._tts_url}/v1/tts/synthesize",
                        json={"text": tts_text},
                        timeout=60,
                    )
                    logger.info("[%s]  TTS seg %d: %d in %s  text=%s",
                                self._id, i, tts_resp.status_code, _elapsed_s(t_tts), tts_text[:60])
                    if tts_resp.status_code == 200:
                        await self._send_audio(tts_resp.content, tone, tts_text, gesture)
                except Exception as exc:
                    logger.warning("[%s]  TTS seg %d failed: %s  text=%s", self._id, i, exc, tts_text[:60])

    async def _process_proactive(self):
        """Handle AI proactive speak signal."""
        logger.info("[%s] Proactive speak triggered", self._id)
        await self._process_text("")

    # ------------------------------------------------------------------ #
    #  Audio chunker + sender
    # ------------------------------------------------------------------ #
    async def _send_audio(self, wav_bytes: bytes, tone: str, text: str, gesture: str = "none"):
        """Send audio to frontend with volume levels and expression data."""
        t0 = time.perf_counter()
        logger.debug("[%s]  _send_audio: tone=%s text=%s size=%d",
                     self._id, tone, text[:40], len(wav_bytes))
        import numpy as np
        is_adpcm = wav_bytes[0:4] == b"RIFF"
        if not is_adpcm:
            volumes = []
            try:
                from pydub import AudioSegment
                from pydub.utils import make_chunks
                audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
                chunks = make_chunks(audio, 20)
                volumes = [chunk.rms for chunk in chunks]
                max_vol = max(volumes) if volumes else 1
                volumes = [v / max_vol for v in volumes] if max_vol > 0 else []
                logger.debug("[%s]  Volumes: %d chunks max=%d", self._id, len(volumes), max_vol)
            except ImportError:
                logger.warning("[%s] pydub not installed, no volume levels", self._id)
            except Exception as exc:
                logger.warning("[%s] Volume extraction failed: %s", self._id, exc)
        else:
            volumes = []

        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        logger.debug("[%s]  Audio base64: %d chars", self._id, len(audio_b64))

        emotion_map = {
            # index 0 - neutral / gentle
            "neutral": 0, "gentle": 0, "emphasizing": 0, "explaining": 0,
            "warm_smile": 0, "soft_smile": 0, "thinking": 0, "curious": 0,
            "meek": 0, "blank": 0,
            # index 1 - joy / happy
            "joy": 1, "playful": 1, "smile": 1, "cheerful": 1,
            "happy_closed": 1, "laughing": 1, "joyful": 1, "blissful": 1,
            "friendly": 1, "awkward_grin": 1,
            # index 2 - anger / serious
            "anger": 2, "serious": 2, "stern": 2, "cold": 2,
            "cold_stare": 2,
            # index 3 - sadness / awkward
            "sadness": 3, "sad": 3, "awkward_smile": 3, "awkward": 3,
            "nervous": 3, "sigh": 3, "giving_up": 3, "shy": 3,
            "embarrassed": 3, "confused": 3, "panicked": 3,
            # index 4 - surprise / shock
            "surprise": 4, "shocked": 4, "lightly_surprised": 4, "startled": 4,
        }
        expr_idx = emotion_map.get(tone, 0)

        payload = {
            "type": "audio",
            "audio": audio_b64,
            "volumes": volumes,
            "display_text": {"text": text, "name": "Monika"},
            "expressions": [expr_idx],
            "gesture": gesture,
            "forwarded": False,
        }
        await self._safe_send(payload)
        logger.debug("[%s]  Audio sent in %s", self._id, _elapsed_s(t0))


# ------------------------------------------------------------------ #
#  FastAPI routes
# ------------------------------------------------------------------ #

app = FastAPI(title="Monika Live2D Bridge", lifespan=lifespan)

# CORS middleware for in-app browser compatibility
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
LIVE2D_DIR = Path(__file__).resolve().parent.parent / "live2d-models"
BACKGROUNDS_DIR = Path(__file__).resolve().parent.parent.parent / "Open-LLM-VTuber-1.2.1" / "Open-LLM-VTuber-1.2.1" / "backgrounds"




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


@app.websocket("/client-ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("\u2500" * 44)
    logger.info("New WebSocket: %s", websocket.client)
    t0 = time.perf_counter()
    await websocket.accept()
    logger.info("WebSocket accepted in %s", _elapsed_s(t0))
    handler = BridgeHandler()
    await handler.handle(websocket)
    total = time.perf_counter() - t0
    logger.info("WebSocket session ended (%.1f sec)", total)


@app.get("/live2d-models/{rest:path}")
async def serve_live2d(rest: str):
    """Serve Live2D model files (model3.json, textures, moc3, etc.)."""
    logger.info("Live2D request: %s", rest)
    target = LIVE2D_DIR / rest
    if target.exists() and target.is_file():
        sz = target.stat().st_size
        logger.debug("  -> serving %s (%d bytes)", rest, sz)
        return FileResponse(str(target))
    logger.warning("  -> 404: %s not found in Live2D models", rest)
    return Response(status_code=404)


@app.get("/")
async def serve_index():
    logger.info("Serving index.html")
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        logger.info("  -> found (%d bytes)", index.stat().st_size)
        return FileResponse(str(index))
    logger.error("  -> NOT FOUND at %s", index)
    return {"error": "frontend not built"}


@app.get("/bg/{rest:path}")
async def serve_background(rest: str):
    target = BACKGROUNDS_DIR / rest
    if target.exists() and target.is_file():
        return FileResponse(str(target))
    return Response(status_code=404)


@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve frontend static assets, fallback to index.html for SPA routing."""
    logger.debug("Static request: %s", path)
    target = FRONTEND_DIR / path
    if target.exists() and target.is_file():
        logger.debug("  -> serving %s (%d bytes)", path, target.stat().st_size)
        return FileResponse(str(target))
    if path.startswith(".well-known/"): return Response(status_code=404)
    # Model file 404: don't serve index.html for Live2D/model requests
    if any(ext in path for ext in (".model3.json", ".moc3", ".exp3.json", ".physics3", ".pose3", ".cdi3", ".motion3.json")):
        logger.warning("  -> 404: model file %s not found", path)
        return Response(status_code=404)
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return Response(status_code=404)


if __name__ == "__main__":
    import uvicorn
    import shutil
    port = int(os.environ.get("BRIDGE_PORT", "9528"))
    logger.info("Starting uvicorn on port %d", port)
    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not found. Install for audio chunk/volume support:")
        logger.warning("  https://ffmpeg.org/download.html  or: winget install ffmpeg")
    else:
        logger.info("ffmpeg found, audio processing ready")
    logger.info("Bridge listening on http://127.0.0.1:%d", port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info", ws="websockets")






