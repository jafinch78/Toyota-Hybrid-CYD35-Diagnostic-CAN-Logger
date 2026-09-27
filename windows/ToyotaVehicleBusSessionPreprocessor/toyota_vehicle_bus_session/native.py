from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from .meta import MetaReadResult, decode_record_payload, read_meta
from .tcb1 import CanStreamReport, scan_tcb_stream

_RAW_NAME = re.compile(r"^RAW_(\d{3})\.TCB$", re.IGNORECASE)


@dataclass
class NativeSession:
    session_id: str
    source_root: Path
    meta: MetaReadResult
    can_paths: tuple[Path, ...]
    can_stream: CanStreamReport | None
    _temporary: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    def close(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


def _safe_extract_zip(source: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory(prefix="toyota_native_")
    root = Path(temp.name)
    with zipfile.ZipFile(source, "r") as archive:
        names = archive.namelist()
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                temp.cleanup()
                raise ValueError("ZIP path traversal rejected")
        meta_names = [name for name in names if PurePosixPath(name).name == "SESSION.META"]
        if len(meta_names) != 1:
            temp.cleanup()
            raise ValueError("ZIP must contain exactly one SESSION.META")
        archive.extractall(root)
        return root / PurePosixPath(meta_names[0]).parent, temp


def _discover_raw_paths(root: Path) -> tuple[Path, ...]:
    indexed: list[tuple[int, Path]] = []
    for child in root.iterdir():
        if not child.is_file():
            continue
        match = _RAW_NAME.match(child.name)
        if match:
            indexed.append((int(match.group(1)), child))
    if not indexed:
        return ()
    indexed.sort(key=lambda item: item[0])
    if indexed[0][0] != 0:
        raise ValueError("native CAN stream is missing RAW_000.TCB")
    expected = list(range(indexed[-1][0] + 1))
    actual = [index for index, _ in indexed]
    if actual != expected:
        raise ValueError("native CAN stream has noncontiguous RAW suffixes")
    return tuple(path for _, path in indexed)


def load_native_session(source: Path) -> NativeSession:
    source = Path(source)
    temporary = None
    if source.is_file() and source.suffix.lower() == ".zip":
        root, temporary = _safe_extract_zip(source)
    elif source.is_dir():
        root = source
    else:
        raise ValueError("native session source must be a folder or ZIP")

    meta_path = root / "SESSION.META"
    if not meta_path.is_file():
        if temporary is not None:
            temporary.cleanup()
        raise ValueError("native session is missing SESSION.META")
    try:
        meta = read_meta(meta_path)
        session_id = f"S{meta.header.session_number:04d}"
        can_paths = _discover_raw_paths(root)
        can_stream = scan_tcb_stream(can_paths) if can_paths else None

        can_regs = []
        for record in meta.records:
            if record.record_type == 0x0002:
                decoded = decode_record_payload(record)
                if decoded.get("stream_type") == 1:
                    can_regs.append((record.stream_id, decoded))
        if can_paths and not can_regs:
            raise ValueError("TCB1 raw files present without a registered CAN stream")
        if can_regs:
            for _, reg in can_regs:
                if reg.get("raw_format_id") != 1:
                    raise ValueError("registered CAN stream is not TCB1")

        return NativeSession(session_id, root, meta, can_paths, can_stream, temporary)
    except Exception:
        if temporary is not None:
            temporary.cleanup()
        raise
