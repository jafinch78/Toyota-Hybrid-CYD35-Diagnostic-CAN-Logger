from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATABASE_FILE = Path(__file__).parent / "data" / "toyota_hybrid_can_db_v0.5.9.json"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SUPPORTED_SCHEMAS = {"1.0.0", "1.1.0", "1.1.1", "1.2.0"}
ALLOWED_SAFETY = {"PASSIVE_BROADCAST", "READ_ONLY_DIAGNOSTIC", "CONTROL_WRITE_QUARANTINED"}
ALLOWED_EVIDENCE = {"CONFIRMED", "FIELD_SPECIFIC", "PROBABLE", "CANDIDATE", "REJECTED"}


@dataclass(frozen=True)
class DatabaseInfo:
    path: str
    name: str
    version: str
    schema_version: str
    sha256: str
    definition_count: int
    field_specific_definition_count: int
    candidate_observation_count: int
    candidate_unique_response_shape_count: int
    candidate_unique_request_tuple_count: int
    candidate_registry_ignored_for_decoding: bool
    warnings: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_database_unchanged(info: DatabaseInfo) -> None:
    current = _sha256(Path(info.path))
    if current != info.sha256:
        raise RuntimeError(
            f"Decoder database changed during processing: expected {info.sha256}, found {current}")


def _validate_member_grade(key: str, kind: str, member: dict[str, Any],
                           definition_grade: str) -> None:
    grade = member.get("evidence_grade", definition_grade)
    if grade not in ALLOWED_EVIDENCE - {"FIELD_SPECIFIC"}:
        raise ValueError(f"Invalid {kind} evidence grade for {key}/{member.get('name', kind)}")


def _validate_candidate_registry(data: dict[str, Any], warnings: list[str]) -> tuple[int, int, int, bool]:
    registry = data.get("candidate_registry")
    if registry is None:
        return 0, 0, 0, False
    if not isinstance(registry, dict):
        raise ValueError("candidate_registry must be an object")
    if registry.get("active_polling") != "EXCLUDED":
        raise ValueError("candidate_registry active polling must be EXCLUDED")
    if registry.get("automatic_promotion_allowed") is not False:
        raise ValueError("candidate_registry automatic promotion must be disabled")
    if int(registry.get("overlap_with_graded_definition_tuples", 0) or 0) != 0:
        raise ValueError("candidate_registry overlaps graded definition tuples")
    observations = registry.get("observations", [])
    if not isinstance(observations, list):
        raise ValueError("candidate_registry observations must be a list")
    for index, item in enumerate(observations):
        if item.get("evidence_grade") != "CANDIDATE":
            raise ValueError(f"candidate_registry observation {index} is not CANDIDATE")
        if item.get("safety_class") != "READ_ONLY_DIAGNOSTIC":
            raise ValueError(f"candidate_registry observation {index} has an invalid safety class")
        if item.get("active_polling") != "EXCLUDED" or item.get("automatic_promotion_allowed") is not False:
            raise ValueError(f"candidate_registry observation {index} is not safely excluded")
    count = int(registry.get("session_observation_count", len(observations)) or 0)
    if count != len(observations):
        raise ValueError("candidate_registry session observation count does not match observations")
    shapes = int(registry.get("unique_response_shape_count", 0) or 0)
    tuples = int(registry.get("unique_request_tuple_count", 0) or 0)
    warnings.append(
        f"Candidate registry retained as metadata only: {count} observations, "
        f"{shapes} unique response shapes, {tuples} unique request tuples; decoding disabled")
    return count, shapes, tuples, True


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
    if schema not in SUPPORTED_SCHEMAS:
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
        definition_grade = definition.get("evidence_grade")
        if definition_grade not in ALLOWED_EVIDENCE:
            raise ValueError(f"Invalid evidence grade for {key}")
        for field in definition.get("fields", []):
            _validate_member_grade(key, "field", field, definition_grade)
        repeat = definition.get("repeat")
        if isinstance(repeat, dict):
            _validate_member_grade(key, "repeat", repeat, definition_grade)
        for field in definition.get("derived_fields", []):
            _validate_member_grade(key, "derived field", field, definition_grade)
        if definition_grade == "FIELD_SPECIFIC" and not (
                definition.get("fields") or isinstance(repeat, dict) or definition.get("derived_fields")):
            raise ValueError(f"FIELD_SPECIFIC definition has no graded members: {key}")
        if definition.get("safety_class") == "CONTROL_WRITE_QUARANTINED":
            warnings.append(f"{key} is quarantined and must never be auto-transmitted")
    candidate_count, candidate_shapes, candidate_tuples, candidate_ignored = \
        _validate_candidate_registry(data, warnings)
    info = DatabaseInfo(
        path=str(selected),
        name=str(data["database"]),
        version=version,
        schema_version=schema,
        sha256=_sha256(selected),
        definition_count=len(definitions),
        field_specific_definition_count=sum(
            definition.get("evidence_grade") == "FIELD_SPECIFIC" for definition in definitions),
        candidate_observation_count=candidate_count,
        candidate_unique_response_shape_count=candidate_shapes,
        candidate_unique_request_tuple_count=candidate_tuples,
        candidate_registry_ignored_for_decoding=candidate_ignored,
        warnings=tuple(warnings),
    )
    return data, info


def find_definition(database: dict[str, Any], profile: str, request_id: int,
                    service: int, pid: int | None) -> dict[str, Any] | None:
    canonical = canonical_profile(profile)
    for definition in database.get("definitions", []):
        if canonical_profile(definition.get("profile")) != canonical:
            continue
        if int(str(definition.get("request_id", "0")), 16) != request_id:
            continue
        if int(str(definition.get("service", "0")), 16) != service:
            continue
        definition_pid = definition.get("pid")
        if definition_pid is None and pid is not None:
            continue
        if definition_pid is not None and (pid is None or int(str(definition_pid), 16) != pid):
            continue
        return definition
    return None
