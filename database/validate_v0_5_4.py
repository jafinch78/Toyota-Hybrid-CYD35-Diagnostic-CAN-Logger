#!/usr/bin/env python3
"""Validate database v0.5.4 structure, safety policy, and release invariants."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "toyota_hybrid_can_db_v0.5.4.json"
PREVIOUS = ROOT / "toyota_hybrid_can_db_v0.5.3.json"
HEX = re.compile(r"^[0-9A-F]+$")
ALLOWED_SAFETY = {"PASSIVE_BROADCAST", "READ_ONLY_DIAGNOSTIC", "CONTROL_WRITE_QUARANTINED"}
ALLOWED_EVIDENCE = {"CONFIRMED", "PROBABLE", "CANDIDATE", "REJECTED"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    previous = json.loads(PREVIOUS.read_text(encoding="utf-8"))

    require(current["database"] == "ToyotaHybridCAN", "wrong database name")
    require(current["version"] == "0.5.4", "wrong database version")
    require(current["schema_version"].split(".")[0] == "1", "unsupported schema major")
    require(current["rollback"] == "Toyota_Hybrid_CAN_Database_v0.5.3.xlsx", "wrong rollback target")

    definitions = current.get("definitions")
    require(isinstance(definitions, list), "definitions must be a list")
    keys = [item.get("key") for item in definitions]
    require(all(isinstance(key, str) and key for key in keys), "empty definition key")
    require(len(keys) == len(set(keys)), "duplicate definition key")

    profiles = set(current["profiles"])
    lookup: dict[str, dict[str, object]] = {}
    for item in definitions:
        key = str(item["key"])
        lookup[key] = item
        require(item.get("profile") in profiles, f"unknown profile in {key}")
        require(item.get("safety_class") in ALLOWED_SAFETY, f"invalid safety class in {key}")
        require(item.get("evidence_grade") in ALLOWED_EVIDENCE, f"invalid evidence grade in {key}")
        for field in ("request_id", "response_id", "service"):
            value = item.get(field)
            require(isinstance(value, str) and HEX.fullmatch(value) is not None, f"invalid {field} in {key}")
        pid = item.get("pid")
        require(pid is None or (isinstance(pid, str) and HEX.fullmatch(pid) is not None), f"invalid pid in {key}")

    # No v0.5.3 definition may disappear or change its safety classification.
    old_by_key = {item["key"]: item for item in previous["definitions"]}
    for key, old in old_by_key.items():
        require(key in lookup, f"v0.5.3 definition removed: {key}")
        require(lookup[key]["safety_class"] == old["safety_class"], f"safety class changed: {key}")

    # The only write-class definitions are the two inherited clear-DTC records.
    quarantined = {item["key"] for item in definitions if item["safety_class"] == "CONTROL_WRITE_QUARANTINED"}
    require(quarantined == {
        "AHV40_HYBRID_ECU_04_CLEAR_DTC_QUARANTINED",
        "AHV40_ENGINE_ECU_04_CLEAR_DTC_QUARANTINED",
    }, "unexpected quarantined/write definition set")

    # Evidence gates.
    require(lookup["NHW20_BATTERY_ECU_21CE_SOC_CURRENT_BLOCK_VOLTAGES"]["evidence_grade"] == "CONFIRMED", "NHW20 21CE grade regression")
    require(lookup["NHW20_BATTERY_ECU_21D0_BLOCK_HEALTH"]["evidence_grade"] == "CONFIRMED", "NHW20 21D0 grade regression")
    require(lookup["AHV40_HYBRID_ECU_21CE_BLOCK_VOLTAGES"]["evidence_grade"] == "CONFIRMED", "Camry 21CE confirmation regression")
    require(lookup["AHV40_HYBRID_ECU_21D0_BLOCK_HEALTH"]["evidence_grade"] == "CONFIRMED", "Camry 21D0 confirmation regression")
    require(lookup["AHV40_HYBRID_ECU_21C3_MG_TEMPERATURES"]["evidence_grade"] == "CONFIRMED", "Camry 21C3 field confirmation regression")
    require(lookup["AHV40_HYBRID_ECU_21CF_BATTERY_TEMPERATURES"]["evidence_grade"] == "CONFIRMED", "Camry 21CF field confirmation regression")
    require(lookup["AHV40_HYBRID_ECU_21C1_MODEL_SIGNATURE"]["evidence_grade"] == "CONFIRMED", "Camry hybrid ECU model signature regression")

    camry_21ce = lookup["AHV40_HYBRID_ECU_21CE_BLOCK_VOLTAGES"]
    require(camry_21ce["repeat"]["count"] == 17 and camry_21ce["preamble_bytes"] == 3, "wrong Camry 21CE layout")
    require({field["name"] for field in camry_21ce["fields"]} == {"battery_soc", "battery_current"}, "Camry 21CE SoC/current fields missing")

    camry_21d0 = lookup["AHV40_HYBRID_ECU_21D0_BLOCK_HEALTH"]
    require(camry_21d0["repeat"]["count"] == 17, "wrong Camry 21D0 resistance count")
    require({field["name"] for field in camry_21d0["fields"]} == {
        "block_count", "minimum_block_voltage", "minimum_block_number", "maximum_block_voltage", "maximum_block_number"
    }, "wrong Camry 21D0 field set")
    require(not any(field.get("semantic_status", "").startswith("CANDIDATE") for field in camry_21d0["fields"]), "confirmed Camry 21D0 fields retain candidate labels")

    phv = current["profiles"]["PRIUS_PHV_GEN1"]
    require(phv["block_count"] == 8 and phv["cell_count"] == 56 and phv["cells_per_block"] == 7, "wrong PHV topology")
    require(phv["individual_cell_values_available"] is False, "PHV individual cells must not be claimed")
    phv_2181 = lookup["ZVW35_HYBRID_ECU_2181_EIGHT_BLOCK_VOLTAGES"]
    require(phv_2181["repeat"]["count"] == 8, "PHV 2181 must expose eight blocks")
    require("seven_cell_block" in phv_2181["repeat"]["name"], "PHV 2181 label must identify aggregate blocks")
    require(not any("56" in item["key"] and "CELL" in item["key"] for item in definitions), "unvalidated 56-cell definition present")

    for bundle in current.get("bundled_requests", []):
        require(bundle["safety_class"] == "READ_ONLY_DIAGNOSTIC", "unsafe bundled request")
        require(bundle["evidence_grade"] in ALLOWED_EVIDENCE, "invalid bundled-request grade")

    print(f"PASS: {CURRENT.name}")
    print(f"definitions={len(definitions)} profiles={len(profiles)} signatures={len(current.get('profile_signatures', []))}")
    print(f"quarantined={len(quarantined)} new_definitions={len(definitions) - len(previous['definitions'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
