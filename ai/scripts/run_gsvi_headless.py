"""
Launch GPT-SoVITS GSVI without opening a browser window.

Usage: python scripts/run_gsvi_headless.py -s 127.0.0.1 -p 8050 -c <config_path>

All arguments are forwarded to gsvi.py — only webbrowser.open is suppressed.
"""
import os
import sys

# Change to GSVI directory so relative paths work
GSVI_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "GPT-SoVITS-1007-cu128")
os.chdir(os.path.abspath(GSVI_DIR))

# Suppress browser before anything else
import webbrowser
_original_open = webbrowser.open
webbrowser.open = lambda url: print(f"[GSVI] Browser suppressed. WebUI: {url}")

# Forward all arguments to gsvi.py
sys.argv = ["gsvi.py"] + sys.argv[1:]
exec(open("gsvi.py", encoding="utf-8").read())
