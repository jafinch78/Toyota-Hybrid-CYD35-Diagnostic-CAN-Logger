from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATABASE_FILE = Path(__file__).parent / "data" / "toyota_hybrid_can_db_v0.5.2.json"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
ALLOWED_SAFETY = {"PASSIVE_BROADCAST", "READ_ONLY_DIAGNOSTIC", "CONTROL_WRITE_QUARANTINED"}
ALLOWED_EVIDENCE = {"CONFIRMED", "PROBABLE", "CANDIDATE", "REJECTED"}


@dataclass(frozen=True)
class DatabaseInfo:
    path: str
    name: str
    version: str
    schema_version: str
    definition_count: int
    warnings: tuple[str, ...]


def canonical_profile(value: str | None) -> str:
    text = str(value or "").upper().replace("-", " ").replace("_", " ")
    text = " ".join(text.split())
    aliases = {
        "CAMRY HYB G1": "CAMRY_HYBRID_GEN1",
        "CAMRY HYBRID GEN 1": "CAMRY_HYBRID_GEN1",
        "CAMRY HYBRID G1": "CAMRY_HYBRID_GEN1",
        "PRIUS GEN 1": "PRIUS_GEN1",
        "PRIUS GEN 2": "PRIUS_GEN2",
        "PRIUS GEN 3": "PRIUS_GEN3",
        "PRIUS PHV GEN 1": "PRIUS_PHV_GEN1",
    }
    return aliases.get(text, text.replace(" ", "_"))


def load_database(path: Path | None = None) -> tuple[dict[str, Any], DatabaseInfo]:
    selected = (path or DATABASE_FILE).resolve()
    with selected.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    warnings: list[str] = []
    if data.get("database") != "ToyotaHybridCAN":
        raise ValueError("Decoder database name is not ToyotaHybridCAN")
    version = str(data.get("version", ""))
    schema = str(data.get("schema_version", ""))
    if not SEMVER.match(version):
        raise ValueError(f"Malformed decoder database version: {version!r}")
    match = SEMVER.match(schema)
    if not match or int(match.group(1)) != 1:
        raise ValueError(f"Unsupported decoder database schema: {schema!r}")
    definitions = data.get("definitions")
    if not isinstance(definitions, list):
        raise ValueError("Decoder database definitions must be a list")
    seen: set[str] = set()
    for definition in definitions:
        key = str(definition.get("key", ""))
        if not key or key in seen:
            raise ValueError(f"Missing or duplicate decoder key: {key!r}")
        seen.add(key)
        if definition.get("safety_class") not in ALLOWED_SAFETY:
            raise ValueError(f"Invalid safety class for {key}")
        if definition.get("evidence_grade") not in ALLOWED_EVIDENCE:
            raise ValueError(f"Invalid evidence grade for {key}")
        if definition.get("safety_class") == "CONTROL_WRITE_QUARANTINED":
            warnings.append(f"{key} is quarantined and must never be auto-transmitted")
    info = DatabaseInfo(
        path=str(selected),
        name=str(data["database"]),
        version=version,
        schema_version=schema,
        definition_count=len(definitions),
        warnings=tuple(warnings),
    )
    return data, info


def find_definition(database: dict[str, Any], profile: str, request_id: int,
                    service: int, pid: int) -> dict[str, Any] | None:
    canonical = canonical_profile(profile)
    for definition in database.get("definitions", []):
        if canonical_profile(definition.get("profile")) != canonical:
            continue
        if int(str(definition.get("request_id", "0")), 16) != request_id:
            continue
        if int(str(definition.get("service", "0")), 16) != service:
            continue
        if int(str(definition.get("pid", "0")), 16) != pid:
            continue
        return definition
    return None
