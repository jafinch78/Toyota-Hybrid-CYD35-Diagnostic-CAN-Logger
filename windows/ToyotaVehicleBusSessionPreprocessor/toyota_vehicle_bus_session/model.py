from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExpansionOptions:
    make_zip: bool = True
    preserve_raw_mtime: bool = False


@dataclass(frozen=True)
class ExpansionResult:
    session_id: str
    output_root: Path
    legacy_session_dir: Path
    zip_path: Path | None
    validation_report: Path
