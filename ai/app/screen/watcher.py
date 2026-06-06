"""Screen monitor  watches active window and pushes context events.

Never calls LLM directly. Events go to InitiativeQueue; Brain decides.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from app.core.event_bus import bus
from app.core.events import EventType


class ScreenWatcher:
    """Periodically captures screen context and pushes to initiative queue.

    Usage:
        watcher = ScreenWatcher(interval=5.0)
        watcher.on_context_change = lambda old, new: initiative_queue.push(...)
        watcher.start()
    """

    def __init__(self, interval: float = 5.0) -> None:
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_context: dict[str, Any] = {}
        self.on_context_change: Callable[[dict, dict], None] | None = None

    @property
    def enabled(self) -> bool:
        return os.environ.get("SCREEN_ENABLED", "0") == "1"

    def start(self) -> None:
        if self._running or not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="screen-watcher")
        self._thread.start()
        print(f"[ScreenWatcher] Started (interval={self.interval}s)")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def capture(self) -> dict[str, Any]:
        """Capture current screen context.

        Returns dict with keys: app, title, changed
        """
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return {"app": "unknown", "title": "", "changed": False}

            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            # Get process name
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_name = "unknown"
            try:
                handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
                if handle:
                    exe_buf = ctypes.create_unicode_buffer(260)
                    exe_len = wintypes.DWORD(260)
                    if kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(exe_len)):
                        path = exe_buf.value
                        process_name = path.rsplit("\\", 1)[-1].replace(".exe", "")
                    kernel32.CloseHandle(handle)
            except Exception:
                pass

            context = {"app": process_name, "title": title}
            context["changed"] = (
                context["app"] != self._last_context.get("app")
                or context["title"] != self._last_context.get("title")
            )
            return context
        except Exception:
            return {"app": "unknown", "title": "", "changed": False}

    def _loop(self) -> None:
        while self._running:
            try:
                ctx = self.capture()

                if ctx.get("changed") and self._last_context:
                    old = dict(self._last_context)
                    bus.publish(
                        EventType.STATE_CHANGED,
                        {
                            "screen": {
                                "from": {"app": old.get("app"), "title": old.get("title")},
                                "to": {"app": ctx["app"], "title": ctx["title"]},
                            }
                        },
                        source="screen_watcher",
                    )
                    if self.on_context_change:
                        self.on_context_change(old, ctx)

                self._last_context = ctx
            except Exception as exc:
                print(f"[ScreenWatcher] Error: {exc}")

            time.sleep(self.interval)
