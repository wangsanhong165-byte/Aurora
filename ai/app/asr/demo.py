"""Pseudo-streaming ASR demo — standalone runnable script.

Usage::

    python -m app.asr.demo              # with local Qwen3-ASR model
    python -m app.asr.demo --model-dir path/to/model

Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path
_proj_root = Path(__file__).resolve().parents[2]
if str(_proj_root) not in sys.path:
    sys.path.insert(0, str(_proj_root))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pseudo-Streaming ASR Demo")
    p.add_argument("--model-dir", default=None, help="Path to Qwen3-ASR model")
    p.add_argument("--chunk", type=float, default=0.5, help="ASR trigger interval (s)")
    p.add_argument("--window", type=float, default=2.0, help="Sliding window size (s)")
    p.add_argument("--silence", type=float, default=0.8, help="Silence timeout (s)")
    p.add_argument("--language", default=None, help="Language hint (e.g. zh, en)")
    return p


async def _amain() -> None:
    args = _build_parser().parse_args()

    from app.asr.pseudo_stream_asr import PseudoStreamASR

    asr = PseudoStreamASR(
        model_dir=args.model_dir,
        chunk_duration=args.chunk,
        window_duration=args.window,
        silence_timeout=args.silence,
        language=args.language,
        on_partial=lambda text: print(text, end="", flush=True),
        on_final=lambda text: print(f"\n[FINAL] {text}"),
    )

    print("=" * 56)
    print("  Pseudo-Streaming ASR Demo — speak to test")
    print(f"  chunk={args.chunk}s  window={args.window}s  silence={args.silence}s")
    print("  Press Ctrl+C to stop")
    print("=" * 56)
    print()

    try:
        await asr.run()
    except KeyboardInterrupt:
        print("\n\nStopped.")
    finally:
        asr.stop()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
