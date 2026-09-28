from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

EXPECTED_BUILDER_VERSION = "1.0.4"
EXPECTED_BUILDER_REF = "evidence-builder-v1.0.4"
_MATERIAL_WARNING_TERMS = (
    "missing", "no raw", "incomplete", "does not reconcile", "malformed",
    "unsupported", "blocked", "corrupt", "truncated",
)
_EXTERNAL_EVIDENCE_FIELDS = (
    "battery_block_rows", "diagnostic_action_rows", "decoded_field_rows",
    "resistance_rows", "identity_rows",
)


@dataclass(frozen=True)
class BuilderCompatibilityReport:
    passed: bool
    blocking_failures: tuple[str, ...]
    warnings: tuple[str, ...]
    sessions: tuple[dict[str, Any], ...]
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blocking_failures": list(self.blocking_failures),
            "warnings": list(self.warnings),
            "sessions": list(self.sessions),
            "lineage": self.lineage,
        }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as stream:
        return list(csv.DictReader(stream))


def _inventory_signature(path: Path) -> tuple[tuple[str, str, int], ...]:
    rows = _csv_rows(path)
    return tuple(sorted(
        (str(row.get("CAN_ID", "")), str(row.get("Direction", "")), int(row.get("Frames", 0) or 0))
        for row in rows
    ))


def _material_new_warnings(original: list[str], expanded: list[str]) -> list[str]:
    original_set = {str(item) for item in original}
    new = [str(item) for item in expanded if str(item) not in original_set]
    return [item for item in new if any(term in item.lower() for term in _MATERIAL_WARNING_TERMS)]


def _normalized_status_counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        count = int(raw or 0)
        if count:
            result[str(key)] = count
    return result


def _external_evidence_non_decreasing(
    original_external: dict[str, Any], expanded_external: dict[str, Any]
) -> bool:
    return all(
        int(expanded_external.get(key, 0) or 0) >= int(original_external.get(key, 0) or 0)
        for key in _EXTERNAL_EVIDENCE_FIELDS
    )


def _raw_response_recovery_improvement(
    original_external: dict[str, Any],
    expanded_external: dict[str, Any],
    *,
    raw_record_count_equal: bool,
    raw_stream_identical: bool,
    inventory_identical: bool,
) -> bool:
    """Recognize monotonic recovery of responses omitted from historical sidecars.

    This is deliberately fail-closed. Recovery is accepted only when the Builder sees
    identical authoritative RAW and CAN inventory, the reconstructed transaction set is
    not smaller, successful responses increase, no-response outcomes decrease, status
    totals reconcile, and every derived external-evidence class is non-decreasing.
    """
    if not (raw_record_count_equal and raw_stream_identical and inventory_identical):
        return False
    original_transactions = int(original_external.get("transactions", 0) or 0)
    expanded_transactions = int(expanded_external.get("transactions", 0) or 0)
    if original_transactions <= 0 or expanded_transactions < original_transactions:
        return False

    original_status = _normalized_status_counts(original_external.get("status_counts"))
    expanded_status = _normalized_status_counts(expanded_external.get("status_counts"))
    if sum(original_status.values()) != original_transactions:
        return False
    if sum(expanded_status.values()) != expanded_transactions:
        return False
    if original_status.get("NO_RESPONSE", 0) <= 0:
        return False
    if expanded_status.get("OK", 0) <= original_status.get("OK", 0):
        return False
    if expanded_status.get("NO_RESPONSE", 0) >= original_status.get("NO_RESPONSE", 0):
        return False
    if not _external_evidence_non_decreasing(original_external, expanded_external):
        return False
    return True


def _summary_by_session(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    processing = _load_json(root / "PROCESSING_SUMMARY.json")
    sessions: dict[str, dict[str, Any]] = {}
    for item in processing.get("sessions", []):
        name = str(item.get("session", ""))
        if name:
            path = root / name / "SESSION_SUMMARY.json"
            sessions[name] = _load_json(path) if path.exists() else item
    return processing, sessions


def compare_builder_outputs(original_builder_output: Path,
                            expanded_builder_output: Path) -> BuilderCompatibilityReport:
    original_root = Path(original_builder_output)
    expanded_root = Path(expanded_builder_output)
    failures: list[str] = []
    warnings: list[str] = []
    session_reports: list[dict[str, Any]] = []

    try:
        original_processing, original_sessions = _summary_by_session(original_root)
        expanded_processing, expanded_sessions = _summary_by_session(expanded_root)
    except Exception as error:
        return BuilderCompatibilityReport(False, (f"Builder output unreadable: {error}",), (), ())

    original_version = str(original_processing.get("processor_version", ""))
    expanded_version = str(expanded_processing.get("processor_version", ""))
    if original_version != EXPECTED_BUILDER_VERSION or expanded_version != EXPECTED_BUILDER_VERSION:
        failures.append(
            f"Builder version mismatch: original={original_version!r}, expanded={expanded_version!r}, "
            f"required={EXPECTED_BUILDER_VERSION!r}")

    original_db = original_processing.get("decoder_database", {}) or {}
    expanded_db = expanded_processing.get("decoder_database", {}) or {}
    if original_db.get("sha256") != expanded_db.get("sha256"):
        failures.append(
            f"decoder database SHA-256 mismatch: original={original_db.get('sha256')}, "
            f"expanded={expanded_db.get('sha256')}")

    original_names = set(original_sessions)
    expanded_names = set(expanded_sessions)
    if original_names != expanded_names:
        failures.append(
            f"Builder session set mismatch: original={sorted(original_names)}, expanded={sorted(expanded_names)}")

    for name in sorted(original_names | expanded_names):
        if name not in original_sessions or name not in expanded_sessions:
            continue
        original = original_sessions[name]
        expanded = expanded_sessions[name]
        local_failures: list[str] = []

        original_supported = bool((original.get("compatibility") or {}).get("supported"))
        expanded_supported = bool((expanded.get("compatibility") or {}).get("supported"))
        if not original_supported:
            local_failures.append(f"{name}: original Builder compatibility supported=false")
        if not expanded_supported:
            local_failures.append(f"{name}: expanded Builder compatibility supported=false")

        original_raw = original.get("raw", {}) or {}
        expanded_raw = expanded.get("raw", {}) or {}
        original_count = int(original_raw.get("raw_record_count", 0) or 0)
        expanded_count = int(expanded_raw.get("raw_record_count", 0) or 0)
        raw_record_count_equal = original_count == expanded_count
        if not raw_record_count_equal:
            local_failures.append(
                f"{name}: raw record count mismatch: original={original_count}, expanded={expanded_count}")

        original_raw_csv = original_root / name / "CAN_RAW.csv"
        expanded_raw_csv = expanded_root / name / "CAN_RAW.csv"
        raw_stream_identical = False
        if not original_raw_csv.exists() or not expanded_raw_csv.exists():
            local_failures.append(f"{name}: CAN_RAW.csv missing; oracle requires Builder --raw-csv for logical CAN stream verification")
        else:
            raw_stream_identical = _sha256(original_raw_csv) == _sha256(expanded_raw_csv)
            if not raw_stream_identical:
                local_failures.append(f"{name}: ordered logical CAN stream differs (CAN_RAW.csv SHA-256 mismatch)")

        original_inventory = _inventory_signature(original_root / name / "CAN_ID_INVENTORY.csv")
        expanded_inventory = _inventory_signature(expanded_root / name / "CAN_ID_INVENTORY.csv")
        inventory_identical = original_inventory == expanded_inventory
        if not inventory_identical:
            local_failures.append(f"{name}: CAN-ID/direction inventory counts differ")

        if original.get("alignment") != expanded.get("alignment"):
            local_failures.append(f"{name}: BLE alignment result differs")
        if original.get("sync_corroboration") != expanded.get("sync_corroboration"):
            local_failures.append(f"{name}: BLE sync corroboration differs")

        original_external = original.get("external_diagnostics", {}) or {}
        expanded_external = expanded.get("external_diagnostics", {}) or {}
        original_external_transactions = int(original_external.get("transactions", 0) or 0)
        expanded_external_transactions = int(expanded_external.get("transactions", 0) or 0)
        original_external_status = _normalized_status_counts(original_external.get("status_counts"))
        expanded_external_status = _normalized_status_counts(expanded_external.get("status_counts"))
        external_mismatch = (
            original_external_transactions != expanded_external_transactions
            or original_external_status != expanded_external_status
        )
        external_comparison = "EXACT"
        recovery_improvement = False
        if external_mismatch:
            recovery_improvement = _raw_response_recovery_improvement(
                original_external,
                expanded_external,
                raw_record_count_equal=raw_record_count_equal,
                raw_stream_identical=raw_stream_identical,
                inventory_identical=inventory_identical,
            )
            if recovery_improvement:
                external_comparison = "RAW_RESPONSE_RECOVERY_IMPROVEMENT"
                warnings.append(
                    f"{name}: RAW_RESPONSE_RECOVERY_IMPROVEMENT: authoritative identical RAW recovered "
                    f"external responses omitted by the historical sidecar evidence "
                    f"({original_external_transactions} -> {expanded_external_transactions} transactions; "
                    f"statuses {original_external_status} -> {expanded_external_status})")
            else:
                if original_external_transactions != expanded_external_transactions:
                    local_failures.append(f"{name}: external diagnostic transaction count differs")
                if original_external_status != expanded_external_status:
                    local_failures.append(f"{name}: external diagnostic status-count distribution differs")

        for key in _EXTERNAL_EVIDENCE_FIELDS:
            original_value = int(original_external.get(key, 0) or 0)
            expanded_value = int(expanded_external.get(key, 0) or 0)
            if recovery_improvement:
                if expanded_value < original_value:
                    local_failures.append(
                        f"{name}: {key} decreased during RAW response recovery: "
                        f"original={original_value}, expanded={expanded_value}")
            elif original_value != expanded_value:
                local_failures.append(f"{name}: {key} differs")

        original_profile = original.get("profile_evidence", {}) or {}
        expanded_profile = expanded.get("profile_evidence", {}) or {}
        if original_profile.get("selected_profile") != expanded_profile.get("selected_profile"):
            local_failures.append(f"{name}: selected vehicle profile differs")
        if bool(original_profile.get("profile_conflict")) != bool(expanded_profile.get("profile_conflict")):
            local_failures.append(f"{name}: profile evidence conflict class differs")
        if int(original_profile.get("confidence_pct", 0) or 0) != int(expanded_profile.get("confidence_pct", 0) or 0):
            local_failures.append(f"{name}: profile evidence confidence differs")
        if original_profile.get("decision") != expanded_profile.get("decision"):
            warnings.append(
                f"{name}: profile provenance decision label differs: "
                f"{original_profile.get('decision')} -> {expanded_profile.get('decision')}")

        material_warnings = _material_new_warnings(
            list(original.get("warnings", []) or []), list(expanded.get("warnings", []) or []))
        for item in material_warnings:
            local_failures.append(f"{name}: new material Builder warning: {item}")

        original_decoded_rows = len(_csv_rows(original_root / name / "DECODED_ALIGNED.csv"))
        expanded_decoded_rows = len(_csv_rows(expanded_root / name / "DECODED_ALIGNED.csv"))
        if expanded_decoded_rows < original_decoded_rows:
            local_failures.append(
                f"{name}: DERIVED_INPUT_GAP DECODED.CSV: Builder decoded rows fell "
                f"from {original_decoded_rows} to {expanded_decoded_rows}")

        session_reports.append({
            "session": name,
            "passed": not local_failures,
            "failures": local_failures,
            "raw_record_count_original": original_count,
            "raw_record_count_expanded": expanded_count,
            "decoded_rows_original": original_decoded_rows,
            "decoded_rows_expanded": expanded_decoded_rows,
            "external_diagnostic_comparison": external_comparison,
        })
        failures.extend(local_failures)

    return BuilderCompatibilityReport(
        passed=not failures,
        blocking_failures=tuple(failures),
        warnings=tuple(warnings),
        sessions=tuple(session_reports),
    )


def _run_builder(builder_python: Path, canlog: Path, output_parent: Path,
                 capture: Path | None) -> Path:
    command = [str(builder_python), "-m", "toyota_can_processor", str(canlog),
               "-o", str(output_parent), "--raw-csv"]
    if capture is not None:
        command.extend(["-c", str(capture)])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Builder failed ({completed.returncode}) for {canlog}:\n{completed.stdout}\n{completed.stderr}")
    marker = '{\n  "output"'
    start = completed.stdout.rfind(marker)
    if start < 0:
        raise RuntimeError(f"Builder did not report its output path:\n{completed.stdout}")
    payload = json.loads(completed.stdout[start:])
    return Path(payload["output"])


def _builder_lineage(builder_python: Path) -> dict[str, Any]:
    probe = r'''
import hashlib, json, pathlib, sys
import toyota_can_processor
root = pathlib.Path(toyota_can_processor.__file__).resolve().parent
digest = hashlib.sha256()
for path in sorted(root.rglob("*.py")):
    digest.update(path.relative_to(root).as_posix().encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
print(json.dumps({
    "builder_version": getattr(toyota_can_processor, "__version__", ""),
    "builder_module_path": str(root),
    "builder_package_sha256": digest.hexdigest(),
    "python_version": sys.version,
}))
'''
    completed = subprocess.run([str(builder_python), "-c", probe], text=True,
                               capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Unable to query Builder lineage:\n{completed.stdout}\n{completed.stderr}")
    data = json.loads(completed.stdout.strip())
    if data.get("builder_version") != EXPECTED_BUILDER_VERSION:
        raise RuntimeError(
            f"Builder version {data.get('builder_version')!r} is not required {EXPECTED_BUILDER_VERSION!r}")
    data["builder_ref"] = EXPECTED_BUILDER_REF
    data["host_python"] = platform.python_version()
    return data


def run_builder_oracle(builder_python: Path, original_canlog: Path,
                       expanded_canlog: Path, capture: Path | None,
                       output_dir: Path) -> BuilderCompatibilityReport:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    original_parent = output_dir / "original_builder"
    expanded_parent = output_dir / "expanded_builder"
    original_parent.mkdir(exist_ok=True)
    expanded_parent.mkdir(exist_ok=True)
    lineage = _builder_lineage(Path(builder_python))
    original_output = _run_builder(Path(builder_python), Path(original_canlog), original_parent,
                                   Path(capture) if capture else None)
    expanded_output = _run_builder(Path(builder_python), Path(expanded_canlog), expanded_parent,
                                   Path(capture) if capture else None)
    report = compare_builder_outputs(original_output, expanded_output)
    original_summary = _load_json(original_output / "PROCESSING_SUMMARY.json")
    expanded_summary = _load_json(expanded_output / "PROCESSING_SUMMARY.json")
    lineage.update({
        "original_builder_output": str(original_output),
        "expanded_builder_output": str(expanded_output),
        "original_canlog": str(Path(original_canlog).resolve()),
        "expanded_canlog": str(Path(expanded_canlog).resolve()),
        "capture": str(Path(capture).resolve()) if capture else None,
        "processing_options": {"raw_csv": True, "ocr": False, "transcribe": False},
        "original_database": original_summary.get("decoder_database", {}),
        "expanded_database": expanded_summary.get("decoder_database", {}),
    })
    report = replace(report, lineage=lineage)
    (output_dir / "BUILDER_ORACLE_REPORT.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
