"""Built-in tools: screen capture.

These are registered by default and can be toggled via ToolRegistry group control.
"""
from __future__ import annotations

import os
import sys
import io
import base64
from pathlib import Path

_SCREEN_ENABLED = os.environ.get("SCREEN_ENABLED", "1") not in {"0", "false", "no"}


def screen_capture(region: str = "full") -> str:
    """Capture current screen and return base64 PNG.

    Args:
        region: "full" for entire screen or "active" for active window.
    """
    if not _SCREEN_ENABLED:
        return '{"error": "screen capture disabled (set SCREEN_ENABLED=1)"}'
    try:
        import mss
        import mss.tools

        with mss.mss() as sct:
            if region == "active":
                # Get active window position (Windows only)
                try:
                    import ctypes
                    from ctypes import wintypes
                    user32 = ctypes.windll.user32
                    hwnd = user32.GetForegroundWindow()
                    rect = wintypes.RECT()
                    ctypes.windll.dwmapi.DwmGetWindowAttribute(
                        hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
                    )
                    monitor = {
                        "left": rect.left,
                        "top": rect.top,
                        "width": rect.right - rect.left,
                        "height": rect.bottom - rect.top,
                    }
                except Exception:
                    monitor = sct.monitors[1]
            else:
                monitor = sct.monitors[1]

            img = sct.grab(monitor)
            png = mss.tools.to_png(img.rgb, img.size)
            b64 = base64.b64encode(png).decode()
            return '{"format":"png_base64","width":%d,"height":%d,"data":"%s"}' % (
                img.width, img.height, b64[:200] + "..."
            )
    except ImportError:
        return '{"error": "mss not installed (pip install mss)"}'
    except Exception as exc:
        return '{"error": "%s"}' % str(exc)


def _register_all(registry) -> None:
    """Register all built-in tools into the given ToolRegistry."""
    from app.legacy.tools.registry import ToolRegistry

    registry.register(
        name="screen_capture",
        fn=screen_capture,
        description="Capture current screen as base64 PNG. Args: region (full|active).",
        group="builtin",
        risk="safe",
        confirm="auto_allow",
        parameters={
            "region": {
                "type": "string",
                "description": "full or active window",
                "enum": ["full", "active"],
            }
        },
    )
