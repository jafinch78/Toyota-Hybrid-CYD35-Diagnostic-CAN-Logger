from __future__ import annotations

import argparse
import json
from pathlib import Path

from .processor import ProcessingOptions, process


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process CYD Toyota hybrid CAN sessions and BLE-synchronized video")
    parser.add_argument("logger", type=Path, help="CANLOG ZIP or directory")
    parser.add_argument("-c", "--companion", type=Path, help="Android capture ZIP or directory")
    parser.add_argument("-v", "--video", type=Path, help="MP4 override, including a Techstream recording")
    parser.add_argument("-o", "--output", type=Path, default=Path.cwd(), help="Output parent directory")
    parser.add_argument("--raw-csv", action="store_true", help="Expand all TCB1 frames to CAN_RAW.csv")
    parser.add_argument("--ocr", action="store_true", help="Run optional FFmpeg/Tesseract OCR")
    parser.add_argument("--ocr-profile", default="AUTO",
                        choices=["AUTO", "HYBRID_ASSISTANT", "HYBRID_ASSISTANT_BATTERY_CHECK",
                                 "DR_PRIUS", "DR_PRIUS_BATTERY_MONITOR",
                                 "AUTEL_MAXIAP200", "TECHSTREAM"])
    parser.add_argument("--ocr-interval", type=float, default=2.0, help="Seconds between OCR frames")
    parser.add_argument("--transcribe", action="store_true", help="Run optional faster-whisper narration transcription")
    parser.add_argument("--whisper-model", default="small.en")
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    options = ProcessingOptions(args.raw_csv, args.ocr, args.transcribe, args.ocr_profile,
                                args.ocr_interval, args.whisper_model)
    try:
        result = process(args.logger, args.output, args.companion, args.video, options, print)
    except Exception as error:
        print(f"ERROR: {error}")
        return 1
    print(json.dumps({"output": result["output"]}, indent=2))
    return 0
