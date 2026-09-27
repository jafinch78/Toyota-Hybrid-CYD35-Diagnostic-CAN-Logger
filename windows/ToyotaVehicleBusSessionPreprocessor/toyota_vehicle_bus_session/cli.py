from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .model import ExpansionOptions
from .native import load_native_session
from .oracle import run_builder_oracle
from .packaging import expand_native_session
from .validation_fixture import synthesize_native_fixture


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _validate(source: Path) -> dict[str, Any]:
    session = load_native_session(source)
    try:
        return {
            "status": "PASS",
            "input": str(Path(source).resolve()),
            "session_id": session.session_id,
            "raw_record_count": session.can_stream.record_count if session.can_stream else 0,
            "closed_cleanly": bool(session.meta.clean_close),
        }
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and expand native Toyota vehicle-bus capture sessions")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a native session folder or ZIP")
    validate.add_argument("source", type=Path)

    expand = sub.add_parser("expand", help="Expand a native session into Builder-compatible legacy files")
    expand.add_argument("source", type=Path)
    expand.add_argument("-o", "--output", type=Path, required=True)
    expand.add_argument("--no-zip", action="store_true")

    synth = sub.add_parser("synthesize-native", help="Create a validation-only TVM1 fixture from a legacy CANLOG")
    synth.add_argument("source", type=Path)
    synth.add_argument("-o", "--output", type=Path, required=True)
    synth.add_argument("--validation-only", action="store_true", required=True)

    oracle = sub.add_parser("oracle", help="Compare original and expanded CANLOGs through Evidence Builder 1.0.4")
    oracle.add_argument("original_canlog", type=Path)
    oracle.add_argument("expanded_canlog", type=Path)
    oracle.add_argument("--builder-python", type=Path, required=True)
    oracle.add_argument("-c", "--capture", type=Path)
    oracle.add_argument("-o", "--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate":
            payload = _validate(args.source)
        elif args.command == "expand":
            result = expand_native_session(
                args.source, args.output,
                options=ExpansionOptions(make_zip=not args.no_zip),
            )
            payload = {
                "status": "PASS",
                "session_id": result.session_id,
                "output_root": str(result.output_root.resolve()),
                "legacy_session_dir": str(result.legacy_session_dir.resolve()),
                "zip_path": str(result.zip_path.resolve()) if result.zip_path else None,
                "validation_report": str(result.validation_report.resolve()),
            }
        elif args.command == "synthesize-native":
            result = synthesize_native_fixture(args.source, args.output)
            payload = {
                "status": "PASS",
                "session_id": result.session_id,
                "native_session_dir": str(result.native_session_dir.resolve()),
                "report_path": str(result.report_path.resolve()),
                "validation_only": True,
            }
        elif args.command == "oracle":
            report = run_builder_oracle(
                args.builder_python, args.original_canlog, args.expanded_canlog,
                args.capture, args.output,
            )
            payload = report.to_dict()
            payload["status"] = "PASS" if report.passed else "FAIL"
            payload["report_path"] = str((args.output / "BUILDER_ORACLE_REPORT.json").resolve())
            _print(payload)
            return 0 if report.passed else 1
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
    except Exception as error:
        _print({"status": "FAIL", "error": str(error)})
        return 1
    _print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
