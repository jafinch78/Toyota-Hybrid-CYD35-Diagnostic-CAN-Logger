#!/usr/bin/env python3
"""Validate v0.5.5 structure, safety invariants, and S0018 promotion gates."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "toyota_hybrid_can_db_v0.5.5.json"
PREVIOUS = ROOT / "toyota_hybrid_can_db_v0.5.4.json"
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
    require(current["version"] == "0.5.5", "wrong database version")
    require(current["schema_version"].split(".")[0] == "1", "unsupported schema major")
    require(current["rollback"] == "Toyota_Hybrid_CAN_Database_v0.5.4.xlsx", "wrong rollback")

    definitions = current["definitions"]
    lookup = {item["key"]: item for item in definitions}
    require(len(lookup) == len(definitions), "duplicate definition key")
    require(len(definitions) == len(previous["definitions"]) + 6, "unexpected definition count")
    profiles = set(current["profiles"])
    for item in definitions:
        key = item["key"]
        require(item.get("profile") in profiles, f"unknown profile in {key}")
        require(item.get("safety_class") in ALLOWED_SAFETY, f"invalid safety class in {key}")
        require(item.get("evidence_grade") in ALLOWED_EVIDENCE, f"invalid evidence grade in {key}")
        for name in ("request_id", "response_id", "service"):
            value = item.get(name)
            require(isinstance(value, str) and HEX.fullmatch(value) is not None,
                    f"invalid {name} in {key}")
        pid = item.get("pid")
        require(pid is None or (isinstance(pid, str) and HEX.fullmatch(pid) is not None),
                f"invalid pid in {key}")
        for entry in item.get("fields", []):
            require(entry.get("evidence_grade", item["evidence_grade"]) in ALLOWED_EVIDENCE,
                    f"invalid field evidence in {key}/{entry.get('name')}")

    for old in previous["definitions"]:
        key = old["key"]
        require(key in lookup, f"v0.5.4 definition removed: {key}")
        require(lookup[key]["safety_class"] == old["safety_class"], f"safety changed: {key}")

    quarantined = {item["key"] for item in definitions
                   if item["safety_class"] == "CONTROL_WRITE_QUARANTINED"}
    require(quarantined == {
        "AHV40_HYBRID_ECU_04_CLEAR_DTC_QUARANTINED",
        "AHV40_ENGINE_ECU_04_CLEAR_DTC_QUARANTINED",
    }, "unexpected quarantined definition set")

    for key in [
        "ZVW35_ENGINE_ECU_21C1_MODEL_SIGNATURE",
        "ZVW35_ENGINE_ECU_0902_VIN",
        "ZVW35_HYBRID_ECU_21C2_ECU_CODE",
        "ZVW35_HYBRID_ECU_2175_INVERTER_COOLANT_AND_PUMP",
        "ZVW35_HYBRID_ECU_218A_POWER_RESOURCE_CURRENTS",
        "ZVW35_HYBRID_ECU_2192_BLOCK_EXTREMA",
        "ZVW35_HYBRID_ECU_2181_EIGHT_BLOCK_VOLTAGES",
        "ZVW35_HYBRID_ECU_2187_BATTERY_TEMPERATURES",
        "ZVW35_HYBRID_ECU_2195_BLOCK_INTERNAL_RESISTANCE",
        "ZVW35_HYBRID_ECU_2198_BATTERY_CURRENT_AND_SOC",
    ]:
        require(lookup[key]["evidence_grade"] == "CONFIRMED", f"S0018 grade regression: {key}")
        require(lookup[key]["safety_class"] == "READ_ONLY_DIAGNOSTIC", f"unsafe S0018 definition: {key}")

    temperatures = lookup["ZVW35_HYBRID_ECU_2187_BATTERY_TEMPERATURES"]["fields"]
    require(len([item for item in temperatures if item["name"].startswith("battery_temperature_")]) == 12,
            "PHV TB1-TB12 fields missing")
    phv = current["profiles"]["PRIUS_PHV_GEN1"]
    require((phv["block_count"], phv["cell_count"], phv["cells_per_block"]) == (8, 56, 7),
            "wrong PHV topology")
    require(phv["individual_cell_values_available"] is False, "individual PHV cells must remain unavailable")
    require(not any("56" in item["key"] and "CELL" in item["key"] for item in definitions),
            "unvalidated 56-cell definition present")

    gen3 = current["profiles"]["PRIUS_GEN3"]
    require((gen3["block_count"], gen3["cell_count"], gen3["cells_per_block"]) == (14, 168, 12),
            "wrong ZVW30 NiMH block/cell topology")
    require((gen3["module_count"], gen3["cells_per_module"], gen3["modules_per_block"]) == (28, 6, 2),
            "wrong ZVW30 NiMH module topology")
    require(gen3["chemistry"] == "NiMH", "wrong ZVW30 battery chemistry")
    require(gen3["voltage_sensing_level"] == "block", "ZVW30 sensing must remain block-level")
    require(gen3["individual_module_values_available"] is False,
            "ZVW30 module-level values must remain unavailable")
    require(gen3["individual_cell_values_available"] is False,
            "ZVW30 cell-level values must remain unavailable")

    model_signatures = [item for item in current.get("profile_signatures", [])
                        if item.get("profile") == "PRIUS_PHV_GEN1"
                        and item.get("response_ascii_contains") == "ZVW35"]
    require(len(model_signatures) == 1 and model_signatures[0].get("authoritative") is True,
            "authoritative ZVW35 signature missing")
    require("S0018" in current.get("capture_evidence", {}), "S0018 provenance missing")
    s0035 = current.get("capture_evidence", {}).get("S0035")
    require(s0035 is not None, "S0035 provenance missing")
    require(s0035["vehicle"] == "2006 Prius Gen 2 NHW20", "wrong S0035 vehicle")
    require(s0035["raw_records"] == 931047, "wrong S0035 raw-record count")
    require(s0035["external_diagnostic_transactions"] == 1226,
            "wrong S0035 external transaction count")
    require(s0035["successful_external_transactions"] == 1111,
            "wrong S0035 successful transaction count")
    require(s0035["session_transmit_frames"] == 0, "S0035 must remain passive")
    require(s0035["battery_block_rows"] == 0,
            "S0035 must not claim unavailable decoded battery-block rows")

    print(f"PASS: {CURRENT.name}")
    print(f"definitions={len(definitions)} profiles={len(profiles)} signatures={len(current.get('profile_signatures', []))}")
    print(f"quarantined={len(quarantined)} new_definitions={len(definitions) - len(previous['definitions'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
