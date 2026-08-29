from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .windows_capture import list_audio_devices, run_windows_capture


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BLE-synchronized Windows desktop/Techstream recorder")
    parser.add_argument("-o", "--output", type=Path, default=Path.home() / "Documents" / "ToyotaCANSync")
    parser.add_argument("--microphone", help="Exact FFmpeg DirectShow audio device name")
    parser.add_argument("--list-audio-devices", action="store_true")
    args = parser.parse_args(arguments)
    if args.list_audio_devices:
        print(list_audio_devices())
        return 0
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(run_windows_capture(args.output, args.microphone))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"ERROR: {error}")
        return 1
    return 0
