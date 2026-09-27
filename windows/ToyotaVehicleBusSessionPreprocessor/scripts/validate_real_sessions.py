from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any
import zipfile

from toyota_vehicle_bus_session.model import ExpansionOptions
from toyota_vehicle_bus_session.oracle import run_builder_oracle
from toyota_vehicle_bus_session.packaging import expand_native_session
from toyota_vehicle_bus_session.tcb1 import scan_tcb_stream
from toyota_vehicle_bus_session.validation_fixture import synthesize_native_fixture


@dataclass(frozen=True)
class ValidationCase:
    session_id: str
    canlog: Path
    capture: Path | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive, "r") as source:
        for member in source.infolist():
            pure = PurePosixPath(member.filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"ZIP path traversal rejected: {member.filename}")
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"ZIP path traversal rejected: {member.filename}")
        source.extractall(destination)
    return destination


def _find_session_root(root: Path, session_id: str | None = None) -> Path:
    root = Path(root)
    if (root / "MANIFEST.JSON").is_file():
        return root
    candidates = [path.parent for path in sorted(root.rglob("MANIFEST.JSON"))]
    if session_id:
        exact = [candidate for candidate in candidates if candidate.name.upper() == session_id.upper()]
        if len(exact) == 1:
            return exact[0]
    if len(candidates) != 1:
        raise ValueError(
            f"expected exactly one legacy session{f' {session_id}' if session_id else ''}; "
            f"found {[path.name for path in candidates]}")
    return candidates[0]


def raw_snapshot(session_root: Path) -> dict[str, Any]:
    root = Path(session_root)
    raw_paths = tuple(sorted(root.glob("RAW_*.TCB")))
    if not raw_paths:
        raise ValueError(f"no RAW_*.TCB files in {root}")
    report = scan_tcb_stream(raw_paths)
    return {
        "record_count": report.record_count,
        "logical_record_sha256": report.logical_record_sha256,
        "rx_count": report.rx_count,
        "tx_count": report.tx_count,
        "first_time_us": report.first_time_us,
        "last_time_us": report.last_time_us,
        "chunks": [
            {
                "name": chunk.path.name,
                "sha256": chunk.sha256,
                "records": chunk.records,
                "truncated_tail_bytes": chunk.truncated_tail_bytes,
                "first_time_us": chunk.first_time_us,
                "last_time_us": chunk.last_time_us,
                "size_bytes": chunk.path.stat().st_size,
            }
            for chunk in report.chunks
        ],
    }


def compare_raw_snapshots(reference: dict[str, Any], candidate: dict[str, Any],
                          label: str) -> list[str]:
    failures: list[str] = []
    for key, display in (
        ("record_count", "record count"),
        ("logical_record_sha256", "logical CAN SHA-256"),
        ("rx_count", "RX count"),
        ("tx_count", "TX count"),
        ("first_time_us", "first timestamp"),
        ("last_time_us", "last timestamp"),
    ):
        if reference.get(key) != candidate.get(key):
            failures.append(
                f"{label}: {display} differs: reference={reference.get(key)!r}, "
                f"candidate={candidate.get(key)!r}")

    reference_chunks = reference.get("chunks", [])
    candidate_chunks = candidate.get("chunks", [])
    reference_names = [item.get("name") for item in reference_chunks]
    candidate_names = [item.get("name") for item in candidate_chunks]
    if reference_names != candidate_names:
        failures.append(
            f"{label}: physical RAW chunk sequence differs: "
            f"reference={reference_names}, candidate={candidate_names}")
        return failures

    for ref, cand in zip(reference_chunks, candidate_chunks):
        name = str(ref.get("name"))
        if ref.get("sha256") != cand.get("sha256"):
            failures.append(
                f"{label}: {name} SHA-256 differs: reference={ref.get('sha256')}, "
                f"candidate={cand.get('sha256')}")
        if ref.get("records") != cand.get("records"):
            failures.append(
                f"{label}: {name} complete record count differs: "
                f"reference={ref.get('records')}, candidate={cand.get('records')}")
        if ref.get("truncated_tail_bytes") != cand.get("truncated_tail_bytes"):
            failures.append(
                f"{label}: {name} truncated-tail byte count differs: "
                f"reference={ref.get('truncated_tail_bytes')}, "
                f"candidate={cand.get('truncated_tail_bytes')}")
    return failures


def _validate_one_case(case: ValidationCase, output_root: Path,
                       builder_python: Path | None) -> dict[str, Any]:
    case_root = output_root / case.session_id
    if case_root.exists():
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)

    report: dict[str, Any] = {
        "session_id": case.session_id,
        "source_canlog": str(case.canlog.resolve()),
        "source_canlog_sha256": sha256_file(case.canlog),
        "source_capture": str(case.capture.resolve()) if case.capture else None,
        "source_capture_sha256": sha256_file(case.capture) if case.capture else None,
        "raw_gate": "FAIL",
        "builder_gate": "NOT_RUN",
        "failures": [],
    }

    with tempfile.TemporaryDirectory(prefix=f"{case.session_id}_original_") as temp:
        extracted = _safe_extract(case.canlog, Path(temp))
        original_root = _find_session_root(extracted, case.session_id)
        original_raw = raw_snapshot(original_root)

    native = synthesize_native_fixture(case.canlog, case_root / "native")
    native_raw = raw_snapshot(native.native_session_dir)
    expansion = expand_native_session(
        native.native_session_dir,
        case_root / "expanded",
        options=ExpansionOptions(make_zip=True),
    )
    expanded_raw = raw_snapshot(expansion.legacy_session_dir)

    raw_failures = compare_raw_snapshots(original_raw, native_raw, "native")
    raw_failures.extend(compare_raw_snapshots(original_raw, expanded_raw, "expanded"))
    report.update({
        "original_raw": original_raw,
        "native_raw": native_raw,
        "expanded_raw": expanded_raw,
        "synthesis_report": str(native.report_path.resolve()),
        "expansion_report": str(expansion.validation_report.resolve()),
        "expanded_canlog": str(expansion.zip_path.resolve()) if expansion.zip_path else None,
        "raw_gate": "PASS" if not raw_failures else "FAIL",
    })
    report["failures"].extend(raw_failures)

    if raw_failures:
        return report

    if builder_python is None:
        report["failures"].append("Builder 1.0.4 oracle was not run")
        return report

    if expansion.zip_path is None:
        report["failures"].append("expanded CANLOG ZIP was not produced")
        return report

    oracle_root = case_root / "builder_oracle"
    try:
        oracle = run_builder_oracle(
            builder_python,
            case.canlog,
            expansion.zip_path,
            case.capture,
            oracle_root,
        )
        report["builder_gate"] = "PASS" if oracle.passed else "FAIL"
        report["builder_oracle_report"] = str((oracle_root / "BUILDER_ORACLE_REPORT.json").resolve())
        report["builder_failures"] = list(oracle.blocking_failures)
        report["builder_warnings"] = list(oracle.warnings)
        if not oracle.passed:
            report["failures"].extend(f"Builder: {item}" for item in oracle.blocking_failures)
    except Exception as error:
        report["builder_gate"] = "FAIL"
        report["failures"].append(f"Builder oracle execution failed: {error}")
    return report


def final_gate_status(case_reports: list[dict[str, Any]], analyzer_smoke: str,
                      windows_1607: str) -> str:
    if not case_reports:
        return "FAIL"
    if any(item.get("raw_gate") != "PASS" or item.get("builder_gate") != "PASS"
           for item in case_reports):
        return "FAIL"
    if analyzer_smoke != "PASS" or windows_1607 != "PASS":
        return "FAIL"
    return "PASS"


def parse_case(value: str) -> ValidationCase:
    parts = value.split("|", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            "case must be SESSION|CANLOG[|CAPTURE], e.g. S0141|CANLOG.zip|CAPTURE.zip")
    session_id = parts[0].upper()
    if not (session_id.startswith("S") and session_id[1:].isdigit()):
        raise argparse.ArgumentTypeError("session must use S#### notation")
    canlog = Path(parts[1])
    capture = Path(parts[2]) if len(parts) == 3 and parts[2] else None
    return ValidationCase(session_id, canlog, capture)


def _read_external_gate(path: Path | None, gate_name: str) -> tuple[str, dict[str, Any] | None]:
    if path is None:
        return "NOT_RUN", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as error:
        return "FAIL", {"error": f"unable to read {gate_name} evidence: {error}"}
    status = str(payload.get("status", payload.get("result", ""))).upper()
    if status not in {"PASS", "FAIL"}:
        return "FAIL", {"error": f"{gate_name} evidence has no PASS/FAIL status", "payload": payload}
    return status, payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the TVM1 real-session firmware authorization campaign")
    parser.add_argument(
        "--case", action="append", type=parse_case, required=True,
        help="SESSION|CANLOG[|CAPTURE]; repeat for every validation session")
    parser.add_argument("--builder-python", type=Path,
                        help="Python executable for the exact Evidence Builder 1.0.4 environment")
    parser.add_argument("--analyzer-smoke-report", type=Path,
                        help="JSON result from the one required Analyzer RC8 process smoke")
    parser.add_argument("--windows-1607-report", type=Path,
                        help="JSON result captured on the Windows 10 1607 validation machine")
    parser.add_argument("-o", "--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    case_reports: list[dict[str, Any]] = []
    for case in args.case:
        if not case.canlog.is_file():
            case_reports.append({
                "session_id": case.session_id,
                "raw_gate": "FAIL",
                "builder_gate": "NOT_RUN",
                "failures": [f"CANLOG not found: {case.canlog}"],
            })
            continue
        if case.capture is not None and not case.capture.is_file():
            case_reports.append({
                "session_id": case.session_id,
                "raw_gate": "FAIL",
                "builder_gate": "NOT_RUN",
                "failures": [f"CAPTURE not found: {case.capture}"],
            })
            continue
        try:
            case_reports.append(_validate_one_case(case, output_root, args.builder_python))
        except Exception as error:
            case_reports.append({
                "session_id": case.session_id,
                "raw_gate": "FAIL",
                "builder_gate": "NOT_RUN",
                "failures": [f"validation exception: {error}"],
            })

    analyzer_status, analyzer_evidence = _read_external_gate(
        args.analyzer_smoke_report, "Analyzer RC8 smoke")
    windows_status, windows_evidence = _read_external_gate(
        args.windows_1607_report, "Windows 10 1607")
    gate = final_gate_status(case_reports, analyzer_status, windows_status)

    result = {
        "format": "TVM1_OFFLINE_EXPANDER_VALIDATION",
        "version": 1,
        "cases": case_reports,
        "analyzer_smoke": analyzer_status,
        "analyzer_smoke_evidence": analyzer_evidence,
        "windows_10_1607": windows_status,
        "windows_10_1607_evidence": windows_evidence,
        "gate": gate,
        "firmware_authorization": (
            "TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed."
            if gate == "PASS" else
            "TVM1 OFFLINE EXPANDER GATE: FAIL — do not remove legacy firmware SD products."
        ),
    }
    report_path = output_root / "TVM1_REAL_SESSION_VALIDATION.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": gate,
        "report": str(report_path),
        "firmware_authorization": result["firmware_authorization"],
    }, indent=2))
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
