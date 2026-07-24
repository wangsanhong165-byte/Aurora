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
    """Capture current screen and return full-size base64 PNG JSON.

    Args:
        region: "full" for entire screen or "active" for active window.
    """
    if not _SCREEN_ENABLED:
        return '{"error": "screen capture disabled (set SCREEN_ENABLED=1)"}'
    try:
        from PIL import ImageGrab

        if region == "active":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                rect = wintypes.RECT()
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
                )
                bbox = (rect.left, rect.top, rect.right, rect.bottom)
                img = ImageGrab.grab(bbox)
            except Exception:
                img = ImageGrab.grab()
        else:
            img = ImageGrab.grab()

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        w, h = img.size
        return '{"type":"screenshot","format":"png_base64","width":%d,"height":%d,"data":"%s"}' % (
            w, h, b64,
        )
    except ImportError:
        return '{"error": "PIL not installed (pip install Pillow)"}'
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
