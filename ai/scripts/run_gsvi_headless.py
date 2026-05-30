"""
Launch GPT-SoVITS GSVI without opening a browser window.

Usage: python scripts/run_gsvi_headless.py -s 127.0.0.1 -p 8050 -c <config_path>

All arguments are forwarded to gsvi.py — only webbrowser.open is suppressed.
"""
import os
import sys

# Change to GSVI directory so relative paths work
GSVI_DIR = os.path.join(os.path.dirname(__file__), "..", "models", "GPT-SoVITS-1007-cu128")
GSVI_DIR = os.path.abspath(GSVI_DIR)
os.chdir(GSVI_DIR)
sys.path.insert(0, GSVI_DIR)  # gsvi.py needs this for "from tools.my_infer import ..."

# Suppress browser before anything else
import webbrowser
webbrowser.open = lambda url: print(f"[GSVI] Browser suppressed. WebUI: {url}")

# Run gsvi.py as __main__
sys.argv = ["gsvi.py"] + sys.argv[1:]
gsvi_path = os.path.join(GSVI_DIR, "gsvi.py")
with open(gsvi_path, encoding="utf-8") as f:
    code = compile(f.read(), gsvi_path, "exec")
exec(code, {"__name__": "__main__"})
