#!/usr/bin/env python3
"""Build Toyota Hybrid CAN Database v0.5.5 from the reviewed v0.5.4 release.

This is a profile-isolated evidence promotion release.  It preserves every
v0.5.4 record, adds only read-only ZVW35 definitions observed in S0018, and
retains the explicit prohibition on claiming 56 individual PHV cell values.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "toyota_hybrid_can_db_v0.5.4.json"
OUTPUT = ROOT / "toyota_hybrid_can_db_v0.5.5.json"
S0018_SOURCE = (
    "S0018 2014 Prius PHV Gen 1 ZVW35; Autel MAXIAP200 OCR/CAN correlation; "
    "CYD logger v2.4.2 listen-only"
)


def read_only(*, key: str, request_id: str, response_id: str, service: str,
              pid: str | None, decoder: str, grade: str, **extra: Any) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "key": key,
        "profile": "PRIUS_PHV_GEN1",
        "request_id": request_id,
        "response_id": response_id,
        "service": service,
        "pid": pid,
        "response_prefix": f"{int(service, 16) + 0x40:02X}{pid or ''}",
        "decoder": decoder,
        "safety_class": "READ_ONLY_DIAGNOSTIC",
        "evidence_grade": grade,
        "transport": "ISO-TP",
        "source": S0018_SOURCE,
    }
    definition.update(extra)
    return definition


def field(name: str, offset: int, formula: str, unit: str | None = None,
          *, width: int = 1, grade: str = "CONFIRMED", **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "offset": offset,
        "width_bytes": width,
        "formula": formula,
        "evidence_grade": grade,
    }
    if width > 1:
        result["endian"] = "big"
    if unit:
        result["unit"] = unit
    result.update(extra)
    return result


def by_key(data: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in data["definitions"] if item["key"] == key)


def main() -> None:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    data["version"] = "0.5.5"
    data["released_utc"] = "2026-09-01T00:00:00Z"
    data["rollback"] = "Toyota_Hybrid_CAN_Database_v0.5.4.xlsx"
    gen3_profile = data["profiles"]["PRIUS_GEN3"]
    gen3_profile.update({
        "block_count": 14,
        "cell_count": 168,
        "cells_per_block": 12,
        "module_count": 28,
        "cells_per_module": 6,
        "modules_per_block": 2,
        "chemistry": "NiMH",
        "voltage_sensing_level": "block",
        "individual_module_values_available": False,
        "individual_cell_values_available": False,
        "notes": (
            "ZVW30 NiMH pack: 28 six-cell modules paired as 14 twelve-cell blocks. "
            "The battery ECU reports the 14 block-level voltages; it does not report "
            "28 individual module voltages or 168 individual cell voltages."
        ),
    })
    phv_profile = data["profiles"]["PRIUS_PHV_GEN1"]
    phv_profile["identity_model_codes"] = ["ZVW35"]
    phv_profile["engine_codes"] = ["2ZRFXE"]
    phv_profile["notes"] = (
        "S0018 confirmed ZVW35/2ZRFXE identity and eight seven-cell aggregate blocks. "
        "No validated 56-individual-cell voltage decoder is present."
    )

    # Refine pre-existing S0015 ZVW35 records with independent AP200 labels.
    phv_2101 = by_key(data, "ZVW35_HYBRID_ECU_2101_ENGINE_AND_SOC")
    phv_2101.update({
        "evidence_grade": "CONFIRMED",
        "source": f"{phv_2101['source']}; {S0018_SOURCE}",
        "fields": [
            field("calculated_load", 0, "A*20/51", "%", grade="CANDIDATE"),
            field("manifold_pressure", 1, "B", "kPa", grade="CANDIDATE"),
            field("intake_air_temperature", 2, "C-40", "degC", grade="PROBABLE"),
            field("ambient_temperature", 3, "D-40", "degC", grade="PROBABLE"),
            field("coolant_temperature", 5, "F-40", "degC",
                  ocr_labels=["Engine coolant temp"], ocr_tolerance=0.6),
            field("engine_rpm", 6, "uint16/4", "rpm", width=2, grade="PROBABLE"),
            field("vehicle_speed", 8, "I*15625/25146", "mph", grade="PROBABLE"),
            field("runtime", 9, "uint16", "s", width=2, grade="PROBABLE"),
            field("throttle", 11, "L*20/51", "%", grade="PROBABLE"),
            field("accelerator_pedal_1", 12, "M*20/51", "%", grade="PROBABLE"),
            field("accelerator_pedal_2", 13, "N*20/51", "%", grade="PROBABLE"),
            field("auxiliary_battery_voltage", 19, "uint16/1000", "V", width=2,
                  grade="PROBABLE"),
            field("actual_soc", 21, "V*20/51", "%",
                  ocr_labels=["State of charge (all bat)"], ocr_tolerance=0.3),
        ],
        "observations": {
            **phv_2101.get("observations", {}),
            "s0018_7e2_successful_transactions": 87,
            "s0018_ap200_actual_soc_example_pct": 20.0,
            "s0018_ap200_coolant_example_degc": 66.0,
        },
        "validation": (
            "S0018 independently matched 20.0% all-battery SoC and 66 degC coolant. "
            "Fields marked CANDIDATE/PROBABLE retain their narrower field-level grades."
        ),
    })

    for key, current_name, current_label, transactions in [
        # AP200's generic labels are counterintuitive here: S0018 repeatedly
        # correlated 2161 (66 degC) with "Motor temp no2" and 2162 (62 degC)
        # with "Motor temp no1".  Retain the Toyota MG semantic names while
        # recording the observed AP200 label crosswalk explicitly.
        ("ZVW35_HYBRID_ECU_2161_MG1_STATUS", "mg1_temperature", "Motor temp no2", 22),
        ("ZVW35_HYBRID_ECU_2162_MG2_STATUS", "mg2_temperature", "Motor temp no1", 29),
    ]:
        definition = by_key(data, key)
        definition.update({
            "evidence_grade": "PROBABLE",
            "source": f"{definition['source']}; {S0018_SOURCE}",
            "observations": {**definition.get("observations", {}),
                             "s0018_successful_transactions": transactions},
            "validation": (
                f"S0018 repeatedly matched {key.split('_')[3]} temperature to AP200 label "
                f"'{current_label}'. AP200's no1/no2 labels are the reverse of the MG1/MG2 "
                "semantic key names; the observed label crosswalk is preserved explicitly."
            ),
        })
        for item in definition["fields"]:
            item["formula"] = item["formula"].replace("*1.8-40", "-40")
            if item.get("unit") == "degF":
                item["unit"] = "degC"
            item["evidence_grade"] = "CONFIRMED" if item["name"] == current_name else "PROBABLE"
            if item["name"] == current_name:
                item["ocr_labels"] = [current_label]
                item["ocr_tolerance"] = 0.6

    for key, prefix, transactions in [
        ("ZVW35_HYBRID_ECU_2170_MG1_INVERTER_TEMPERATURE", "mg1", 20),
        ("ZVW35_HYBRID_ECU_2171_MG2_INVERTER_TEMPERATURE", "mg2", 19),
    ]:
        definition = by_key(data, key)
        definition.update({
            "evidence_grade": "CONFIRMED",
            "source": f"{definition['source']}; {S0018_SOURCE}",
            "observations": {**definition.get("observations", {}),
                             "s0018_successful_transactions": transactions},
            "validation": "S0018 AP200 current, after-IG-on, and maximum temperatures matched the decoded bytes.",
        })
        for item in definition["fields"]:
            item["formula"] = item["formula"].replace("*1.8-40", "-40")
            if item.get("unit") == "degF":
                item["unit"] = "degC"
            item["evidence_grade"] = "CONFIRMED"
            item.pop("semantic_status", None)
        if not any(item["name"] == "inverter_gate_status" for item in definition["fields"]):
            definition["fields"].append(field("inverter_gate_status", 3, "bit(D,0)"))
        definition["fields"][0]["ocr_labels"] = [f"Inverter temp-({prefix})"]
        definition["fields"][0]["ocr_tolerance"] = 0.6

    phv_2181 = by_key(data, "ZVW35_HYBRID_ECU_2181_EIGHT_BLOCK_VOLTAGES")
    phv_2181.update({
        "evidence_grade": "CONFIRMED",
        "source": f"{phv_2181['source']}; {S0018_SOURCE}",
        "observations": {
            **phv_2181.get("observations", {}),
            "s0018_successful_transactions": 79,
            "s0018_ap200_block_rmse_v": 0.009,
        },
        "validation": (
            "S0018 AP200 independently displayed all eight aggregate blocks; matched rows had about "
            "0.009 V aggregate RMSE after display rounding. These are not individual cell values."
        ),
    })
    phv_2181["repeat"].update({
        "evidence_grade": "CONFIRMED",
        "ocr_label_pattern": "Battery block vol -v{index:02d}",
        "ocr_tolerance": 0.05,
    })
    for item in phv_2181["fields"]:
        item["evidence_grade"] = "CONFIRMED"
    next(item for item in phv_2181["fields"] if item["name"] == "pack_voltage").update({
        "ocr_labels": ["Power resource vb"], "ocr_tolerance": 1.1,
    })

    phv_2187 = by_key(data, "ZVW35_HYBRID_ECU_2187_BATTERY_TEMPERATURES")
    temperature_fields = [
        field("battery_intake_temperature_1", 0, "uint16*255.9/65535-50", "degC", width=2,
              ocr_labels=["Inhaling air temp"], ocr_tolerance=0.6),
    ]
    for index in range(1, 13):
        temperature_fields.append(field(
            f"battery_temperature_{index}", index * 2,
            "uint16*255.9/65535-50", "degC", width=2,
            ocr_labels=[f"Temp of batt tb{index}"], ocr_tolerance=0.6,
        ))
    for index in range(2, 5):
        temperature_fields.append(field(
            f"battery_intake_temperature_{index}", (index + 11) * 2,
            "uint16*255.9/65535-50", "degC", width=2,
            ocr_labels=[f"Inhaling air temp{index}"], ocr_tolerance=0.6,
        ))
    phv_2187.update({
        "evidence_grade": "CONFIRMED",
        "source": f"{phv_2187['source']}; {S0018_SOURCE}",
        "fields": temperature_fields,
        "observations": {**phv_2187.get("observations", {}),
                         "s0018_successful_transactions": 38,
                         "s0018_ap200_labeled_battery_temperature_sensors": 12},
        "validation": (
            "S0018 AP200 labels matched intake temperatures 1-4 and battery sensors TB1-TB12. "
            "For example TB1-TB12 decoded to the displayed 31.5-33.7 degC range."
        ),
    })

    phv_2195 = by_key(data, "ZVW35_HYBRID_ECU_2195_BLOCK_INTERNAL_RESISTANCE")
    phv_2195.update({
        "evidence_grade": "CONFIRMED",
        "source": f"{phv_2195['source']}; {S0018_SOURCE}",
        "observations": {**phv_2195.get("observations", {}),
                         "s0018_successful_transactions": 12,
                         "s0018_ap200_labeled_values": 8},
        "validation": "All eight 0x07 bytes decoded to 0.007 ohm and matched AP200 r01-r08 labels.",
    })
    phv_2195["repeat"].update({
        "evidence_grade": "CONFIRMED",
        "ocr_label_pattern": "Internal resistance r{index:02d}",
        "ocr_tolerance": 0.0011,
    })

    phv_2198 = by_key(data, "ZVW35_HYBRID_ECU_2198_BATTERY_CURRENT_AND_SOC")
    phv_2198.update({
        "evidence_grade": "CONFIRMED",
        "source": f"{phv_2198['source']}; {S0018_SOURCE}",
        "fields": [
            field("battery_current", 0, "uint16/100-327.68", "A", width=2,
                  ocr_labels=["Batt pack val current"], ocr_tolerance=0.2),
            field("charge_control_limit", 2, "C/2-64", "kW",
                  ocr_labels=["Charge control value"], ocr_tolerance=0.6),
            field("discharge_control_limit", 3, "D/2-64", "kW",
                  ocr_labels=["Discharge control value"], ocr_tolerance=0.6),
            field("delta_soc", 4, "E/2", "%", ocr_labels=["Delta soc"], ocr_tolerance=0.3),
            field("soc_after_ig", 5, "F/2", "%", ocr_labels=["Soc after ig-on"], ocr_tolerance=0.3),
            field("soc_max", 6, "G/2", "%", ocr_labels=["Status of charge max"], ocr_tolerance=0.3),
            field("soc_min", 7, "H/2", "%", ocr_labels=["Status of charge min"], ocr_tolerance=0.3),
        ],
        "observations": {**phv_2198.get("observations", {}),
                         "s0018_successful_transactions": 59},
        "validation": (
            "S0018 AP200 independently matched battery current, -29 kW charge limit, 35.5-36 kW "
            "discharge limit, 2% delta SoC, 25% ignition/max SoC, and 19.5% minimum SoC."
        ),
    })

    additions = [
        read_only(
            key="ZVW35_ENGINE_ECU_21C1_MODEL_SIGNATURE", request_id="7E0", response_id="7E8",
            service="21", pid="C1", decoder="ascii_model_signature", grade="CONFIRMED",
            signature={"ascii_contains": "ZVW35", "minimum_response_bytes": 18},
            observations={"s0018_successful_transactions": 19,
                          "response_ascii_prefix": "ZVW35 2ZRFXE", "model_year": 2014},
            validation="Nineteen responses contained ZVW35/2ZRFXE and matched the AP200 model page.",
        ),
        read_only(
            key="ZVW35_ENGINE_ECU_0902_VIN", request_id="7E0", response_id="7E8",
            service="09", pid="02", decoder="vin", grade="CONFIRMED",
            prefix_skip_bytes=1, mask_by_default=True,
            observations={"s0018_successful_transactions": 2,
                          "vin_masked": "JTDKN3DP4E3******", "ocr_exact_match": True},
            validation="Two standard Mode 09 PID 02 responses matched the AP200 VIN exactly; exports mask it by default.",
        ),
        read_only(
            key="ZVW35_HYBRID_ECU_21C2_ECU_CODE", request_id="7E2", response_id="7EA",
            service="21", pid="C2", decoder="ascii_field", grade="CONFIRMED",
            ascii_field={"name": "hybrid_ecu_code", "offset": 0, "length": 5},
            observations={"s0018_successful_transactions": 10, "value": "47520"},
            validation="The five-byte ASCII ECU code 47520 matched the AP200 live-data label.",
        ),
        read_only(
            key="ZVW35_HYBRID_ECU_2175_INVERTER_COOLANT_AND_PUMP", request_id="7E2",
            response_id="7EA", service="21", pid="75", decoder="field_map", grade="CONFIRMED",
            fields=[
                field("inverter_pump_speed", 1, "uint16", "rpm", width=2,
                      ocr_labels=["Inverter w/p revolution"], ocr_tolerance=130.0),
                field("inverter_coolant_temperature", 3, "D-40", "degC",
                      ocr_labels=["Inverter coolant water temperature"], ocr_tolerance=0.6),
            ],
            signature={"response_length_bytes": 8},
            observations={"s0018_successful_transactions": 24,
                          "ap200_pump_examples_rpm": [3250, 3375],
                          "ap200_coolant_example_degc": 44},
            validation="S0018 AP200 labels matched pump speed and inverter coolant temperature.",
        ),
        read_only(
            key="ZVW35_HYBRID_ECU_218A_POWER_RESOURCE_CURRENTS", request_id="7E2",
            response_id="7EA", service="21", pid="8A", decoder="field_map", grade="CONFIRMED",
            fields=[
                field("power_resource_current_sensor_1", 0, "uint16/100-327.68", "A", width=2,
                      ocr_labels=["Bat no.1 no.2 val sens cur"], ocr_tolerance=0.2),
                field("power_resource_current_sensor_2", 2, "uint16/100-327.68", "A", width=2,
                      ocr_labels=["Power resource ib", "Bat1 ib sens2 pwr resourc"], ocr_tolerance=0.2),
            ],
            observations={"s0018_successful_transactions": 29,
                          "ap200_labeled_current_examples_a": [4.82, 5.31, 5.37]},
            validation="Both signed current-sensor values followed the AP200 labels with 0.01 A scaling.",
        ),
        read_only(
            key="ZVW35_HYBRID_ECU_2192_BLOCK_EXTREMA", request_id="7E2", response_id="7EA",
            service="21", pid="92", decoder="field_map", grade="CONFIRMED",
            fields=[
                field("minimum_block_voltage", 0, "uint16*79.99/65535", "V", width=2,
                      ocr_labels=["Batt block minimum vol"], ocr_tolerance=0.05),
                field("minimum_block_number", 2, "C+1", "1-based block",
                      ocr_labels=["Minimum batt block no"], ocr_tolerance=0.1),
                field("maximum_block_voltage", 3, "uint16*79.99/65535", "V", width=2,
                      ocr_labels=["Batt block max vol"], ocr_tolerance=0.05),
                field("maximum_block_number", 5, "F+1", "1-based block",
                      ocr_labels=["Max battery block no"], ocr_tolerance=0.1),
                field("block_count", 6, "G", expected=8,
                      ocr_labels=["Battery block num"], ocr_tolerance=0.1),
            ],
            derived_fields=[{
                "name": "block_voltage_difference",
                "formula": "maximum_block_voltage-minimum_block_voltage",
                "unit": "V",
                "evidence_grade": "CONFIRMED",
            }],
            signature={"response_length_bytes": 24},
            observations={"s0018_successful_transactions": 48},
            validation="AP200 labels confirmed eight blocks, voltage extrema, and zero-based payload indexes converted to one-based block numbers.",
        ),
    ]
    data["definitions"].extend(additions)

    signatures = [item for item in data.get("profile_signatures", [])
                  if not (item.get("profile") == "PRIUS_PHV_GEN1" and item.get("pid") == "81")]
    signatures.extend([
        {
            "profile": "PRIUS_PHV_GEN1", "request_id": "7E0", "service": "21", "pid": "C1",
            "response_id": "7E8", "response_ascii_contains": "ZVW35",
            "evidence_grade": "CONFIRMED", "detector_weight": 100, "authoritative": True,
        },
        {
            "profile": "PRIUS_PHV_GEN1", "request_id": "7E2", "service": "21", "pid": "81",
            "response_id": "7EA", "response_length_bytes": 24, "block_count": 8,
            "block_voltage_bounds_v": [15.0, 35.0], "evidence_grade": "CONFIRMED",
            "detector_weight": 90,
        },
    ])
    data["profile_signatures"] = signatures

    data.setdefault("capture_evidence", {})["S0018"] = {
        "vehicle": "2014 Prius PHV Gen 1 ZVW35",
        "logger_version": "2.4.2",
        "raw_frames": 1195423,
        "session_transmit_frames": 0,
        "diagnostic_transactions": 1870,
        "successful_diagnostic_transactions": 1554,
        "alignment_rms_ms": 5.497549916915953,
        "model_signature": "ZVW35 2ZRFXE",
        "vin_masked": "JTDKN3DP4E3******",
        "source_sha256": {
            "CANLOG_083126_130240.zip": "d7f85f1c9d56753eba9ac38ba48e763be68962e2afd03ec96bbb2253209297f6",
            "ToyotaCAN_Evidence_20260831_135501.zip": "d8ec3ee2554d2762de99c2e1b6418d701697228fc518c059d11372afe10b8c0f",
        },
        "notes": (
            "AP200 identity and labeled battery data contradict the logger's Camry 95% heuristic. "
            "The model-code response is authoritative for offline profile correction."
        ),
    }
    data["capture_evidence"]["S0035"] = {
        "vehicle": "2006 Prius Gen 2 NHW20",
        "logger_version": "2.4.2",
        "board_profile": "DORHEA_B0DLNJSSFW",
        "processor_version": "1.0.2",
        "processor_database_version": "0.5.3",
        "capture_format": "1.4",
        "twai_mode": "LISTEN_ONLY",
        "can_bitrate": 500000,
        "raw_records": 931047,
        "session_duration_us": 562069613,
        "session_transmit_frames": 0,
        "can_queue_drops": 177,
        "sd_log_drops": 0,
        "bus_error_count": 23,
        "bus_off_events": 0,
        "external_diagnostic_frames": 4662,
        "external_diagnostic_transactions": 1226,
        "successful_external_transactions": 1111,
        "diagnostic_action_rows": 7,
        "battery_block_rows": 0,
        "ble_sync_samples": 135,
        "alignment_samples_used": 130,
        "alignment_rms_ms": 5.1274277610864685,
        "alignment_warning": "BLE fit residual RMS exceeds 5 ms",
        "identity_model_response": "NHW20C 1NZFXE",
        "identity_evidence_grade": "OBSERVED_ONLY",
        "source_sha256": {
            "CANLOG_2026090126_185750.zip": "371f3ebfd5ef8f181124f7312fa02727cf34ef720e01ff6ea9534fc478c21f28",
            "CAPTURE_20260901_185750.zip": "e49c9e6baf6563705e13a2ea011984b4858a49b71752d06d8697c40eff016a99",
            "CAPTURE_20260901_185750_rsz.zip": "d1b6be8e80d6ed8d37a7e9d4ddbac69a1324d0d54360dfc1bc3c8e651ff6d6b8",
            "ToyotaCAN_Evidence_20260901_193400.zip": "11cbd995257904c2cb15e9f9f6b0418aaf4aba634023bacab76f3f91040001e0",
        },
        "notes": (
            "Processed acquisition retained as profile-specific evidence. The logger transmitted no frames. "
            "The v1.0.2/v0.5.3 processor produced no decoded battery-block rows, so S0035 does not by itself "
            "promote or regrade a database definition. VIN-bearing source data remains masked or omitted."
        ),
    }
    data["release_notes"] = [
        "Corrects the ZVW30 NiMH profile topology to 14 sensed blocks, 168 cells, 12 cells per block, and 28 six-cell modules paired two per block; no module- or cell-level values are claimed.",
        "Adds the processed S0035 2006 NHW20 acquisition summary and provenance without changing definition grades.",
        "Uses the S0018 ZVW35/2ZRFXE model response to distinguish Prius PHV Gen 1 from AHV40 Camry.",
        "Adds masked standard VIN, hybrid ECU code, inverter coolant/pump, dual power-resource current, and block-extrema definitions.",
        "Confirms PHV 2101 core SoC/coolant, 2170/2171 temperatures, 2181 eight aggregate block voltages, 2187 intake/TB1-TB12 temperatures, 2195 eight resistances, and 2198 current/SoC/control fields.",
        "Retains field-level PROBABLE/CANDIDATE grades where S0018 did not supply independent dynamic corroboration.",
        "Does not claim 56 individual PHV cell voltages and adds no control/write definition.",
    ]

    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(data['definitions'])} definitions")


if __name__ == "__main__":
    main()
