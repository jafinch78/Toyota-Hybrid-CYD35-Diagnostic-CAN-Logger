from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any


SEMVER_RE = re.compile(r"(?i)(?:^|[^0-9])v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass
class Compatibility:
    supported: bool
    firmware_original: str
    firmware_normalized: str | None
    format_original: str
    format_normalized: str | None
    raw_format: str
    parser: str | None
    warnings: list[str]
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_semver(value: Any) -> str | None:
    text = str(value or "").strip()
    match = SEMVER_RE.search(text)
    if not match:
        return None
    major, minor, patch = match.groups()
    return f"{int(major)}.{int(minor)}.{int(patch or 0)}"


def check_manifest(manifest: dict[str, Any]) -> Compatibility:
    warnings: list[str] = []
    errors: list[str] = []
    firmware_original = str(manifest.get("firmware_version", ""))
    format_original = str(manifest.get("format_version", ""))
    raw_format = str(manifest.get("raw_format", ""))
    firmware = normalize_semver(firmware_original)
    capture_format = normalize_semver(format_original)

    if manifest.get("format") != "ToyotaHybridCAN-Capture":
        errors.append("MANIFEST.JSON format is not ToyotaHybridCAN-Capture")
    if firmware is None:
        warnings.append("Firmware version is missing or not semantic-version compatible")
    if capture_format is None:
        errors.append("Capture format version is missing or malformed")
    else:
        major, minor, _ = map(int, capture_format.split("."))
        if major != 1:
            errors.append(f"Capture format major {major} is unsupported; no data was guessed")
        elif minor > 4:
            warnings.append(f"Capture format 1.{minor} is newer than tested 1.4; known fields only")
        elif minor < 3:
            warnings.append(f"Legacy capture format 1.{minor}; some integrity and sync fields may be absent")

    parser = None
    if raw_format == "TCB1_24_byte_records":
        parser = "TCB1"
    elif raw_format.startswith("TCB1"):
        parser = "TCB1"
        warnings.append(f"Noncanonical TCB1 raw_format label: {raw_format}")
    else:
        errors.append(f"Unsupported raw format {raw_format!r}; raw records were not guessed")

    if firmware:
        fw_major, fw_minor, _ = map(int, firmware.split("."))
        if fw_major == 2 and fw_minor in (3, 4):
            pass
        elif capture_format and capture_format.startswith("1."):
            warnings.append(f"Firmware {firmware} is untested, but its known capture format can be parsed")

    return Compatibility(
        supported=not errors,
        firmware_original=firmware_original,
        firmware_normalized=firmware,
        format_original=format_original,
        format_normalized=capture_format,
        raw_format=raw_format,
        parser=parser,
        warnings=warnings,
        errors=errors,
    )
