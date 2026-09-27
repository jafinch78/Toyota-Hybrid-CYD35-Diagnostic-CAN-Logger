from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from toyota_vehicle_bus_session.oracle import compare_builder_outputs


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def make_builder_output(root: Path, *, raw_count: int = 3, raw_variant: str = "base",
                        warnings: list[str] | None = None, decoded_rows: int = 2,
                        db_hash: str = "dbhash", selected_profile: str = "PRIUS_GEN2",
                        external_transactions: int = 2, external_ok: int = 2,
                        battery_rows: int = 1, action_rows: int = 1) -> Path:
    root.mkdir(parents=True)
    session = root / "S0001"
    session.mkdir()
    raw_rows = [
        [100, "123", 2, "0102", 0, 0, "RX"],
        [200, "7E0", 3, "0221C1", 0, 0, "TX"],
        [300, "7E8", 4, "0361C100", 0, 0, "RX"],
    ]
    if raw_variant == "changed":
        raw_rows[-1][3] = "0361C101"
    write_csv(session / "CAN_RAW.csv",
              ["Time_us", "CAN_ID", "DLC", "DataHex", "Extended", "RTR", "Direction"],
              raw_rows[:raw_count])
    write_csv(session / "CAN_ID_INVENTORY.csv",
              ["CAN_ID", "Direction", "Frames", "First_us", "Last_us", "Duration_s", "Mean_rate_Hz", "DLC_counts", "Variable_byte_mask"],
              [["123", "RX", 1, 100, 100, "0.000000", "0.000", "2:1", "0x00"],
               ["7E0", "TX", 1, 200, 200, "0.000000", "0.000", "3:1", "0x00"],
               ["7E8", "RX", 1, 300, 300, "0.000000", "0.000", "4:1", "0x00"]][:raw_count])
    write_csv(session / "DECODED_ALIGNED.csv", ["Time_ms", "SOC_pct"],
              [[index * 100, 50 + index] for index in range(decoded_rows)])
    summary = {
        "session": "S0001",
        "compatibility": {"supported": True, "warnings": [], "errors": []},
        "raw": {"raw_record_count": raw_count, "arbitration_id_direction_pairs": raw_count,
                "truncated_tail_bytes_total": 0},
        "alignment": {"sample_count_used": 4, "residual_rms_ms": 1.0, "drift_ppm": 2.0,
                      "formula": "video_s=(esp_us-a)/b"},
        "sync_corroboration": {"confirmed": True, "matched": 4, "missing": 0},
        "diagnostic_status_counts": {"OK": 1},
        "external_diagnostics": {
            "transactions": external_transactions,
            "status_counts": {"OK": external_ok},
            "battery_block_rows": battery_rows,
            "decoded_field_rows": 2,
            "resistance_rows": 1,
            "identity_rows": 1,
            "diagnostic_action_rows": action_rows,
        },
        "profile_evidence": {
            "selected_profile": selected_profile,
            "profile_conflict": False,
            "confidence_pct": 95,
            "decision": "MANIFEST_RETAINED",
        },
        "decoder_database": {"name": "ToyotaHybridCAN", "version": "0.9.28", "sha256": db_hash},
        "warnings": warnings or [],
    }
    (session / "SESSION_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    overall = {
        "processor_version": "1.0.4",
        "created_utc": "2026-09-27T00:00:00+00:00",
        "logger_source": "nondeterministic/source.zip",
        "decoder_database": summary["decoder_database"],
        "sessions": [summary],
    }
    (root / "PROCESSING_SUMMARY.json").write_text(json.dumps(overall, indent=2), encoding="utf-8")
    return root


class BuilderOracleTests(unittest.TestCase):
    def test_identical_outputs_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original")
            expanded = make_builder_output(base / "expanded")
            report = compare_builder_outputs(original, expanded)
            self.assertTrue(report.passed)
            self.assertEqual(report.blocking_failures, ())
            self.assertEqual(report.sessions[0]["session"], "S0001")

    def test_raw_stream_change_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original")
            expanded = make_builder_output(base / "expanded", raw_variant="changed")
            report = compare_builder_outputs(original, expanded)
            self.assertFalse(report.passed)
            self.assertTrue(any("logical CAN stream" in item for item in report.blocking_failures))

    def test_raw_count_inventory_and_external_evidence_are_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original")
            expanded = make_builder_output(base / "expanded", raw_count=2,
                                           external_transactions=1, external_ok=1,
                                           battery_rows=0, action_rows=0)
            report = compare_builder_outputs(original, expanded)
            joined = "\n".join(report.blocking_failures)
            self.assertIn("raw record count", joined)
            self.assertIn("CAN-ID/direction inventory", joined)
            self.assertIn("external diagnostic transaction count", joined)
            self.assertIn("battery_block_rows", joined)
            self.assertIn("diagnostic_action_rows", joined)

    def test_database_profile_and_sync_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original")
            expanded = make_builder_output(base / "expanded", db_hash="other",
                                           selected_profile="PRIUS_PHV_GEN1")
            summary_path = expanded / "S0001" / "SESSION_SUMMARY.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["sync_corroboration"]["confirmed"] = False
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            report = compare_builder_outputs(original, expanded)
            joined = "\n".join(report.blocking_failures)
            self.assertIn("decoder database SHA-256", joined)
            self.assertIn("selected vehicle profile", joined)
            self.assertIn("BLE sync corroboration", joined)

    def test_new_missing_evidence_warning_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original")
            expanded = make_builder_output(base / "expanded",
                                           warnings=["Android/CYD SYNC.CSV corroboration is incomplete"])
            report = compare_builder_outputs(original, expanded)
            self.assertFalse(report.passed)
            self.assertTrue(any("new material Builder warning" in item for item in report.blocking_failures))

    def test_decoded_row_loss_triggers_derived_input_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            original = make_builder_output(base / "original", decoded_rows=3)
            expanded = make_builder_output(base / "expanded", decoded_rows=0)
            report = compare_builder_outputs(original, expanded)
            self.assertFalse(report.passed)
            self.assertTrue(any("DERIVED_INPUT_GAP" in item and "DECODED.CSV" in item
                                for item in report.blocking_failures))


if __name__ == "__main__":
    unittest.main()
