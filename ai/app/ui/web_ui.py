"""Web UI 鈥?stdlib HTTP server + SSE (Server-Sent Events).

Zero dependencies. Opens the system browser to display
the chat interface. SSE pushes live segments, portraits,
and audio to the frontend in real-time.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any


_sse_clients: list = []
_sse_lock = threading.Lock()
_EVENT_QUEUE: queue.Queue = queue.Queue()

# Web input queue
_web_input_queue: queue.Queue = queue.Queue()


def get_web_input_queue() -> queue.Queue:
    return _web_input_queue


# ---- Pre-scan portrait cache (tone -> absolute image path) ----
_PORTRAIT_CACHE: dict[str, Path] = {}
_CHARS_DIR = Path(__file__).resolve().parents[2] / "characters"
if _CHARS_DIR.exists():
    for _cd in _CHARS_DIR.iterdir():
        if not _cd.is_dir():
            continue
        _card = _cd / "character.json"
        if not _card.exists():
            continue
        try:
            _c = json.loads(_card.read_text(encoding="utf-8"))
        except Exception:
            continue
        _sprites = _c.get("sprites", _c.get("portraits", {}))
        for _tone, _match in _sprites.items():
            _ps = _match.get("path", "") if isinstance(_match, dict) else str(_match)
            if _ps:
                _ip = _cd / _ps
                if _ip.exists():
                    _PORTRAIT_CACHE[_tone] = _ip
    print(f"[WebUI] Portrait cache: {len(_PORTRAIT_CACHE)} tones loaded")


class _SSEClient:
    def __init__(self, wfile: Any) -> None:
        self._wfile = wfile
        self._closed = False

    def send(self, event: str, data: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            payload = json.dumps(data, ensure_ascii=False)
            msg = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
            self._wfile.write(msg)
            self._wfile.flush()
        except Exception:
            self._closed = True

    def close(self) -> None:
        self._closed = True


def broadcast(event: str, data: dict[str, Any]) -> None:
    _EVENT_QUEUE.put((event, data))
    with _sse_lock:
        dead = []
        for client in _sse_clients:
            if client._closed:
                dead.append(client)
            else:
                client.send(event, data)
        for d in dead:
            _sse_clients.remove(d)


class _UIHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(_STATIC_DIR), **kwargs)

    def do_GET(self) -> None:
        if self.path == "/events":
            self._handle_sse()
            return
        if self.path.startswith("/portrait/"):
            self._serve_portrait()
            return
        if self.path.startswith("/audio/"):
            self._serve_audio()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/chat":
            self._handle_chat()
            return
        self.send_response(404)
        self.end_headers()

    def _handle_chat(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(body)
            text = str(data.get("text", "")).strip()
        except (json.JSONDecodeError, UnicodeDecodeError):
            text = ""
        if not text:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "empty text"}).encode())
            return
        _web_input_queue.put({"text": text, "timestamp": time.time()})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True}).encode())

    def _serve_portrait(self) -> None:
        tone = self.path.split("/portrait/", 1)[-1] or "neutral"
        data, ct = _get_portrait(tone)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _serve_audio(self) -> None:
        name = self.path.split("/audio/", 1)[-1]
        audio_path = _TEMP_AUDIO_DIR / name
        if audio_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(audio_path.stat().st_size))
            self.end_headers()
            with open(audio_path, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        client = _SSEClient(self.wfile)
        with _sse_lock:
            _sse_clients.append(client)
        try:
            while not client._closed:
                client.send("ping", {"ts": time.time()})
                time.sleep(15)
        except Exception:
            pass
        finally:
            client.close()
            with _sse_lock:
                if client in _sse_clients:
                    _sse_clients.remove(client)

    def log_message(self, format: str, *args: Any) -> None:
        pass


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)

_TEMP_AUDIO_DIR = Path(__file__).resolve().parents[2] / "temp_audio"
_TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def save_tts_audio(wav_bytes: bytes, text: str = "") -> str | None:
    try:
        ts = int(time.time() * 1000)
        name = f"tts_{ts}.wav"
        path = _TEMP_AUDIO_DIR / name
        with open(path, "wb") as f:
            f.write(wav_bytes)
        _cleanup_old_audio(keep=50)
        return f"/audio/{name}"
    except Exception:
        return None


def _cleanup_old_audio(keep: int = 50) -> None:
    try:
        files = sorted(
            _TEMP_AUDIO_DIR.glob("tts_*.wav"),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        for f in files[keep:]:
            f.unlink(missing_ok=True)
    except Exception:
        pass


_PORTRAIT_PLACEHOLDER = None


def _get_portrait(tone: str) -> tuple[bytes, str]:
    """Return (image_bytes, mime_type) for a tone, or placeholder SVG."""
    global _PORTRAIT_PLACEHOLDER
    img_path = _PORTRAIT_CACHE.get(tone) or _PORTRAIT_CACHE.get("neutral")
    if img_path and img_path.exists():
        ct = "image/webp" if img_path.suffix == ".webp" else "image/png"
        return (img_path.read_bytes(), ct)
    if _PORTRAIT_PLACEHOLDER is None:
        _PORTRAIT_PLACEHOLDER = b'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300">\n  <rect width="300" height="300" fill="#16213e" rx="16"/>\n  <circle cx="150" cy="120" r="40" fill="#533483"/>\n  <path d="M80 240 Q150 180 220 240" stroke="#533483" stroke-width="8" fill="none" stroke-linecap="round"/>\n</svg>' 
    return (_PORTRAIT_PLACEHOLDER, "image/svg+xml")


def start_server(port: int = 8090, open_browser: bool = True) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _UIHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="web-ui")
    t.start()
    print(f"[WebUI] http://127.0.0.1:{port}")
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    return server


def stop_server(server: ThreadingHTTPServer) -> None:
    server.shutdown()
