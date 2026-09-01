from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_evidence_capsule(output_root: Path) -> dict[str, Any]:
    names = {
        "PROCESSING_SUMMARY.json", "SESSION_SUMMARY.json", "PROFILE_EVIDENCE.json",
        "IDENTITY_ALIGNED.csv", "SIGNAL_CANDIDATES.json", "EVIDENCE_GRADING.csv",
        "EVIDENCE_GRADING.json", "CAN_OCR_CORRELATION.csv", "BATTERY_BLOCKS_ALIGNED.csv",
        "RESISTANCE_ARRAYS_ALIGNED.csv", "DIAGNOSTIC_ACTIONS_ALIGNED.csv",
        "EVENTS_ALIGNED.csv", "REPORT.html", "VOICE_TRANSCRIPT.csv",
        "OCR_KEYFRAMES.csv", "CAPTURE_DERIVATIVE_REPORT.json",
    }
    files = [path for path in output_root.rglob("*") if path.is_file()
             and (path.name in names or "OCR_KEYFRAMES" in path.parts)]
    files = [path for path in files if path.suffix.lower() != ".zip"]
    manifest = {
        "format": "ToyotaCAN-Evidence-Capsule",
        "format_version": "1.0",
        "processor_version": "1.0.3",
        "source_raw_files_included": False,
        "vin_policy": "Only masked identity exports are included; raw diagnostic payload CSV is excluded.",
        "files": [{"path": str(path.relative_to(output_root)).replace("\\", "/"),
                   "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
                  for path in sorted(files)],
    }
    manifest_path = output_root / "CAPSULE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    files.append(manifest_path)
    target = output_root / "ToyotaCAN_Evidence_Capsule.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files):
            info = zipfile.ZipInfo(str(path.relative_to(output_root)).replace("\\", "/"),
                                   date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return {"path": str(target), "size_bytes": target.stat().st_size,
            "file_count": len(files), "sha256": _sha256(target)}
