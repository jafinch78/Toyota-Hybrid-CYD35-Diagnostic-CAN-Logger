from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from .legacy import build_legacy_checkpoint, build_legacy_manifest, write_legacy_events, write_legacy_sync
from .model import ExpansionOptions, ExpansionResult
from .native import load_native_session
from .schemas import DIAGNOSTICS_HEADER, EXTERNAL_DIAGNOSTICS_HEADER


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, separators=(",", ": ")) + "\n", encoding="utf-8")


def _write_header(path: Path, header: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerow(header)


def _copy_raw_verified(src: Path, dst: Path, preserve_mtime: bool) -> None:
    if preserve_mtime:
        shutil.copy2(src, dst)
    else:
        shutil.copyfile(src, dst)
    if hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dst.read_bytes()).digest():
        raise IOError("RAW copy verification failed")


def _write_deterministic_zip(root: Path, zip_path: Path) -> None:
    members = sorted(path for path in root.rglob("*") if path.is_file())
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in members:
            arcname = path.relative_to(root.parent).as_posix()
            info = zipfile.ZipInfo(arcname, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def expand_native_session(source: Path, output_parent: Path, *, options: ExpansionOptions = ExpansionOptions()) -> ExpansionResult:
    session = load_native_session(Path(source))
    output_parent = Path(output_parent)
    output_parent.mkdir(parents=True, exist_ok=True)
    output_root = output_parent / f"CANLOG_TVM1_{session.session_id}"
    legacy_dir = output_root / session.session_id
    legacy_dir.mkdir(parents=True, exist_ok=False)
    try:
        for source_raw in session.can_paths:
            _copy_raw_verified(source_raw, legacy_dir / source_raw.name, options.preserve_raw_mtime)

        _write_json(legacy_dir / "MANIFEST.JSON", build_legacy_manifest(session))
        _write_json(legacy_dir / "CHECKPOINT.JSON", build_legacy_checkpoint(session))
        write_legacy_sync(session, legacy_dir / "SYNC.CSV")
        write_legacy_events(session, legacy_dir / "EVENTS.CSV")
        _write_header(legacy_dir / "DIAGNOSTICS.CSV", DIAGNOSTICS_HEADER)
        _write_header(legacy_dir / "EXTERNAL_DIAGNOSTICS.CSV", EXTERNAL_DIAGNOSTICS_HEADER)
        (legacy_dir / "README.TXT").write_text(
            "Offline-expanded Toyota vehicle-bus session. RAW TCB bytes are authoritative and were copied byte-for-byte. Generated compatibility text products carry TVM1 provenance.\n",
            encoding="utf-8",
        )
        if not session.meta.clean_close:
            (legacy_dir / "SESSION.OPEN").write_text("UNCLEAN_NATIVE_SESSION\n", encoding="utf-8")

        report = {
            "session_id": session.session_id,
            "closed_cleanly": session.meta.clean_close,
            "products": {
                "MANIFEST.JSON": "GENERATED_COMPATIBILITY",
                "CHECKPOINT.JSON": "GENERATED_COMPATIBILITY",
                "SYNC.CSV": "GENERATED_COMPATIBILITY",
                "EVENTS.CSV": "GENERATED_COMPATIBILITY",
                "DIAGNOSTICS.CSV": "HEADER_ONLY_PENDING_TASK5",
                "EXTERNAL_DIAGNOSTICS.CSV": "HEADER_ONLY_PENDING_TASK5",
                "DECODED.CSV": "NOT_GENERATED_DERIVED",
                "SIGNALS.CSV": "NOT_GENERATED_DERIVED",
                "PLOT.CSV": "NOT_GENERATED_DERIVED",
            },
            "raw_files": [
                {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in session.can_paths
            ],
        }
        report_path = output_root / "EXPANSION_REPORT.json"
        _write_json(report_path, report)
        zip_path = None
        if options.make_zip:
            zip_path = output_parent / f"CANLOG_TVM1_{session.session_id}.zip"
            _write_deterministic_zip(output_root, zip_path)
        return ExpansionResult(session.session_id, output_root, legacy_dir, zip_path, report_path)
    finally:
        session.close()
