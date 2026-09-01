from __future__ import annotations

import argparse
import json
from pathlib import Path

from .dependency_setup import installation_check
from .batch import process_batch
from .processor import ProcessingOptions, process


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process CYD Toyota hybrid CAN sessions and BLE-synchronized video")
    parser.add_argument("logger", type=Path, nargs="?", help="CANLOG ZIP or directory")
    parser.add_argument("--batch", type=Path,
                        help="Folder containing multiple CANLOG and CAPTURE ZIPs to pair by BLE session")
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
    parser.add_argument("--no-review-proxy", action="store_true",
                        help="Do not create an OCR review proxy for large videos")
    parser.add_argument("--review-proxy-threshold-mb", type=float, default=100.0,
                        help="Minimum source-video size for automatic 720p/10-fps proxy")
    parser.add_argument("--check-install", action="store_true",
                        help="Verify the active Python environment and OCR tools, then exit")
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    if args.check_install:
        print(json.dumps(installation_check(), indent=2))
        return 0
    if args.logger is None and args.batch is None:
        print("ERROR: logger or --batch is required unless --check-install is used")
        return 2
    options = ProcessingOptions(
        write_raw_csv=args.raw_csv, run_ocr=args.ocr,
        run_transcription=args.transcribe, ocr_profile=args.ocr_profile,
        ocr_interval_seconds=args.ocr_interval, whisper_model=args.whisper_model,
        create_review_proxy=not args.no_review_proxy,
        review_proxy_threshold_mb=args.review_proxy_threshold_mb,
    )
    try:
        result = process_batch(args.batch, args.output, options, print) if args.batch else \
            process(args.logger, args.output, args.companion, args.video, options, print)
    except Exception as error:
        print(f"ERROR: {error}")
        return 1
    print(json.dumps({"output": result["output"]}, indent=2))
    return 0
