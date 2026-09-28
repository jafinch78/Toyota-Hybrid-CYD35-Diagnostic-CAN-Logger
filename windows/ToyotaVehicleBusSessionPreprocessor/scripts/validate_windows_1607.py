from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
from typing import Any

from toyota_vehicle_bus_session.model import ExpansionOptions
from toyota_vehicle_bus_session.packaging import expand_native_session
from toyota_vehicle_bus_session.tcb1 import scan_tcb_stream
from toyota_vehicle_bus_session.validation_fixture import synthesize_native_fixture


WINDOWS_10_1607_BUILD = 14393
REPORT_NAME = "WINDOWS_1607_VALIDATION.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_windows_build() -> int | None:
    if os.name != "nt":
        return None
    try:
        return int(sys.getwindowsversion().build)  # type: ignore[attr-defined]
    except (AttributeError, TypeError, ValueError):
        match = re.search(r"(?:^|\.)(\d{5})(?:\.|$)", platform.version())
        return int(match.group(1)) if match else None


def is_windows_10_1607(os_name: str, build: int | None) -> bool:
    return os_name == "nt" and build == WINDOWS_10_1607_BUILD


def raw_snapshot(paths: list[Path] | tuple[Path, ...]) -> dict[str, Any]:
    report = scan_tcb_stream(tuple(Path(path) for path in paths))
    return {
        "logical_record_sha256": report.logical_record_sha256,
        "record_count": report.record_count,
        "rx_count": report.rx_count,
        "tx_count": report.tx_count,
        "chunks": {chunk.path.name: chunk.sha256 for chunk in report.chunks},
        "truncated_tail_bytes": {
            chunk.path.name: chunk.truncated_tail_bytes for chunk in report.chunks
        },
    }


def compare_raw_identity(reference: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if reference.get("logical_record_sha256") != candidate.get("logical_record_sha256"):
        failures.append(
            "logical RAW stream SHA-256 mismatch: "
            f"reference={reference.get('logical_record_sha256')} "
            f"candidate={candidate.get('logical_record_sha256')}")
    if reference.get("record_count") != candidate.get("record_count"):
        failures.append(
            "RAW record count mismatch: "
            f"reference={reference.get('record_count')} candidate={candidate.get('record_count')}")
    reference_chunks = dict(reference.get("chunks", {}) or {})
    candidate_chunks = dict(candidate.get("chunks", {}) or {})
    if set(reference_chunks) != set(candidate_chunks):
        failures.append(
            f"RAW chunk set mismatch: reference={sorted(reference_chunks)} "
            f"candidate={sorted(candidate_chunks)}")
    for name in sorted(set(reference_chunks) & set(candidate_chunks)):
        if reference_chunks[name] != candidate_chunks[name]:
            failures.append(
                f"{name} SHA-256 mismatch: reference={reference_chunks[name]} "
                f"candidate={candidate_chunks[name]}")
    reference_tails = dict(reference.get("truncated_tail_bytes", {}) or {})
    candidate_tails = dict(candidate.get("truncated_tail_bytes", {}) or {})
    if reference_tails and reference_tails != candidate_tails:
        failures.append(
            f"RAW truncated-tail status mismatch: reference={reference_tails} "
            f"candidate={candidate_tails}")
    return failures


def final_status(platform_ok: bool, failures: list[str]) -> str:
    return "PASS" if platform_ok and not failures else "FAIL"


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_validation(source_canlog: Path, output_root: Path) -> dict[str, Any]:
    source = Path(source_canlog).resolve()
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / REPORT_NAME
    build = detect_windows_build()
    platform_ok = is_windows_10_1607(os.name, build)
    report: dict[str, Any] = {
        "format": "TVM1_WINDOWS_1607_RUNTIME_VALIDATION",
        "version": 1,
        "status": "FAIL",
        "platform_ok": platform_ok,
        "os_name": os.name,
        "platform": platform.platform(),
        "windows_build": build,
        "required_windows_build": WINDOWS_10_1607_BUILD,
        "python_executable": sys.executable,
        "python_version": sys.version,
        "source_canlog": str(source),
        "source_canlog_sha256": None,
        "session_id": None,
        "native_session_meta_sha256": None,
        "expanded_canlog_sha256": None,
        "source_raw": None,
        "native_raw": None,
        "expanded_raw": None,
        "failures": [],
        "final_errorlevel": 1,
    }

    failures: list[str] = report["failures"]
    try:
        if not source.is_file():
            failures.append(f"CANLOG not found: {source}")
            return report
        report["source_canlog_sha256"] = sha256_file(source)
        if not platform_ok:
            failures.append(
                f"platform is not Windows 10 1607 build {WINDOWS_10_1607_BUILD}: "
                f"os_name={os.name!r}, build={build!r}")
            return report

        work = output / "runtime_work"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)

        native = synthesize_native_fixture(source, work / "native")
        report["session_id"] = native.session_id
        synthesis = json.loads(native.report_path.read_text(encoding="utf-8-sig"))
        native_paths = tuple(sorted(native.native_session_dir.glob("RAW_*.TCB")))
        native_raw = raw_snapshot(native_paths)
        source_raw = {
            "logical_record_sha256": synthesis.get("raw_logical_sha256"),
            "record_count": native_raw["record_count"],
            "rx_count": native_raw["rx_count"],
            "tx_count": native_raw["tx_count"],
            "chunks": dict(synthesis.get("raw_identity", {}) or {}),
            "truncated_tail_bytes": dict(native_raw["truncated_tail_bytes"]),
        }
        report["source_raw"] = source_raw
        report["native_raw"] = native_raw
        failures.extend(
            f"native: {item}" for item in compare_raw_identity(source_raw, native_raw))

        meta_path = native.native_session_dir / "SESSION.META"
        report["native_session_meta_sha256"] = sha256_file(meta_path)

        expansion = expand_native_session(
            native.native_session_dir,
            work / "expanded",
            options=ExpansionOptions(make_zip=True),
        )
        expanded_paths = tuple(sorted(expansion.legacy_session_dir.glob("RAW_*.TCB")))
        expanded_raw = raw_snapshot(expanded_paths)
        report["expanded_raw"] = expanded_raw
        failures.extend(
            f"expanded: {item}" for item in compare_raw_identity(source_raw, expanded_raw))
        if expansion.zip_path is None or not expansion.zip_path.is_file():
            failures.append("expanded CANLOG ZIP was not produced")
        else:
            report["expanded_canlog_sha256"] = sha256_file(expansion.zip_path)

        report["status"] = final_status(platform_ok, failures)
        report["final_errorlevel"] = 0 if report["status"] == "PASS" else 1
        return report
    except Exception as error:
        failures.append(f"validation exception: {error}")
        report["status"] = "FAIL"
        report["final_errorlevel"] = 1
        return report
    finally:
        _write_report(report_path, report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the TVM1 preprocessor runtime on Windows 10 1607")
    parser.add_argument("source_canlog", type=Path, help="One real historical CANLOG ZIP")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Validation output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_validation(args.source_canlog, args.output)
    report_path = Path(args.output).resolve() / REPORT_NAME
    print(json.dumps({
        "status": report["status"],
        "report": str(report_path),
        "windows_build": report["windows_build"],
        "raw_record_count": (report.get("source_raw") or {}).get("record_count"),
        "final_errorlevel": report["final_errorlevel"],
    }, indent=2, sort_keys=True))
    return int(report["final_errorlevel"])


if __name__ == "__main__":
    raise SystemExit(main())
