import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from toyota_can_processor.batch import discover_pairs
from toyota_can_processor.candidates import write_signal_candidates
from toyota_can_processor.database import find_definition, load_database
from toyota_can_processor.decoding import decode_definition
from toyota_can_processor.diagnostics import Request, Transaction
from toyota_can_processor.grading import grade_session
from toyota_can_processor.profile_detection import detect_vehicle_profile


class V103PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database, cls.database_info = load_database()

    def test_zvw35_model_signature_overrides_incorrect_camry_manifest(self):
        request = SimpleNamespace(can_id=0x7E0, service=0x21, pid=0xC1,
                                  payload=bytes.fromhex("21C1"))
        transaction = SimpleNamespace(
            request=request,
            status="OK",
            response_id=0x7E8,
            response_payload=bytes.fromhex("61C1") + b"ZVW35 2ZRFXE\x00\x00\x00",
        )
        result = detect_vehicle_profile(
            [transaction], self.database, "CAMRY HYB G1")
        self.assertEqual(result["selected_profile"], "PRIUS_PHV_GEN1")
        self.assertEqual(result["decision"], "AUTHORITATIVE_MODEL_SIGNATURE")
        self.assertTrue(result["profile_conflict"])
        self.assertEqual(result["confidence_pct"], 100)

    def test_generic_decoder_exports_eight_phv_blocks_and_resistances(self):
        block_definition = find_definition(
            self.database, "PRIUS_PHV_GEN1", 0x7E2, 0x21, 0x81)
        self.assertIsNotNone(block_definition)
        decoded = decode_definition(
            bytes.fromhex("61814F224F434F434F224F0A4F744F744F22AE1407BC0000"),
            block_definition,
        )
        self.assertTrue(decoded["matched"])
        self.assertEqual(len(decoded["arrays"]), 8)
        self.assertTrue(all(item["bounds_status"] == "PASS" for item in decoded["arrays"]))
        self.assertAlmostEqual(decoded["arrays"][0]["value"], 24.726, places=2)
        self.assertEqual(decoded["fields"][1]["name"], "pack_voltage")
        self.assertAlmostEqual(decoded["fields"][1]["value"], 198.0, places=1)
        self.assertEqual(decoded["fields"][1]["bounds_status"], "")

        resistance_definition = find_definition(
            self.database, "PRIUS_PHV_GEN1", 0x7E2, 0x21, 0x95)
        resistances = decode_definition(
            bytes.fromhex("6195") + bytes([7] * 8), resistance_definition)
        self.assertEqual(len(resistances["arrays"]), 8)
        self.assertTrue(all(item["value"] == 0.007 for item in resistances["arrays"]))

    def test_generic_decoder_preserves_gen2_fourteen_block_profile(self):
        block_definition = find_definition(
            self.database, "PRIUS_GEN2", 0x7E3, 0x21, 0xCE)
        # 50% SoC, +1.23 A, then fourteen 15.00 V blocks.
        payload = bytes.fromhex("61CE64807B") + bytes.fromhex("85DC") * 14
        decoded = decode_definition(payload, block_definition)
        self.assertTrue(decoded["matched"])
        self.assertEqual(len(decoded["arrays"]), 14)
        self.assertTrue(all(item["value"] == 15.0 for item in decoded["arrays"]))
        self.assertEqual(decoded["fields"][0]["value"], 50.0)
        self.assertAlmostEqual(decoded["fields"][1]["value"], 1.23, places=2)

        health_definition = find_definition(
            self.database, "PRIUS_GEN2", 0x7E3, 0x21, 0xD0)
        health_data = bytearray(29)
        health_data[0] = 14
        health_data[9:11] = bytes.fromhex("85DC")
        health_data[11] = 1
        health_data[12:14] = bytes.fromhex("85E6")
        health_data[14] = 2
        health_data[15:29] = bytes([20] * 14)
        health = decode_definition(bytes.fromhex("61D0") + health_data, health_definition)
        self.assertEqual(health["fields"][0]["expected_status"], "MATCH")
        self.assertEqual(len(health["arrays"]), 14)
        self.assertTrue(all(item["value"] == 0.02 for item in health["arrays"]))

    def test_local_grading_rejects_blank_indexed_ocr_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decoded_path = root / "decoded.csv"
            with decoded_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=[
                    "Profile", "DecoderKey", "Field", "ArrayIndex", "Unit",
                    "Video_s", "Value", "OCRLabels", "OCRTolerance",
                    "BoundsStatus", "ExpectedStatus", "EvidenceGrade", "SourceSession",
                ])
                writer.writeheader()
                writer.writerow({
                    "Profile": "PRIUS_PHV_GEN1", "DecoderKey": "TEST_2195",
                    "Field": "resistance", "ArrayIndex": "7", "Unit": "ohm",
                    "Video_s": "10.0", "Value": "0.007",
                    "OCRLabels": "Internal resistance r07", "OCRTolerance": "0.0011",
                    "EvidenceGrade": "CONFIRMED", "SourceSession": "S0018",
                })
            ocr_path = root / "ocr.csv"
            with ocr_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["Video_s", "Frame", "Text"])
                writer.writeheader()
                writer.writerow({
                    "Video_s": "9.9", "Frame": "blank.png",
                    "Text": "Internal resistance r07 -- Ohm Internal resistance r08 0.008 Ohm",
                })
                writer.writerow({
                    "Video_s": "10.1", "Frame": "value.png",
                    "Text": "Internal resistance r07 0.007 Ohm Internal resistance r08 0.008 Ohm",
                })
            summary = grade_session(
                decoded_path, ocr_path, root / "correlation.csv",
                root / "grades.csv", root / "grades.json", "S0018")
            self.assertEqual(summary["can_ocr_pairs"], 1)
            self.assertEqual(summary["agreements"], 1)
            with (root / "correlation.csv").open(newline="", encoding="utf-8") as stream:
                correlation = list(csv.DictReader(stream))
            self.assertEqual(correlation[0]["OCRFrame"], "value.png")
            self.assertEqual(correlation[0]["OCRValue"], "0.007")

    def test_local_grading_uses_each_ocr_frame_once_per_field(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decoded = root / "decoded.csv"
            fields = ["Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "Video_s",
                      "Value", "OCRLabels", "OCRTolerance", "BoundsStatus", "ExpectedStatus",
                      "EvidenceGrade", "SourceSession"]
            with decoded.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for time_s in (9.9, 10.0, 10.1):
                    writer.writerow({"Profile": "TEST", "DecoderKey": "RPM", "Field": "speed",
                                     "Unit": "rpm", "Video_s": time_s, "Value": 1000,
                                     "OCRLabels": "Engine speed", "OCRTolerance": 150,
                                     "EvidenceGrade": "CANDIDATE", "SourceSession": "S0001"})
            ocr = root / "ocr.csv"
            with ocr.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["Video_s", "Frame", "Text"])
                writer.writeheader()
                writer.writerow({"Video_s": 10, "Frame": "one.png",
                                 "Text": "Engine speed 1000 rpm"})
            summary = grade_session(decoded, ocr, root / "pairs.csv", root / "grades.csv",
                                    root / "grades.json", "S0001")
            self.assertEqual(summary["can_ocr_pairs"], 1)
            self.assertEqual(summary["unique_ocr_frames"], 1)
            self.assertEqual(summary["confirmation_ready_rows"], 0)

    def test_large_pump_speed_errors_cannot_pass_on_tolerance_count_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            decoded = root / "decoded.csv"
            fields = ["Profile", "DecoderKey", "Field", "ArrayIndex", "Unit", "Video_s",
                      "Value", "OCRLabels", "OCRTolerance", "BoundsStatus", "ExpectedStatus",
                      "EvidenceGrade", "SourceSession"]
            with decoded.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for index in range(30):
                    writer.writerow({"Profile": "PRIUS_PHV_GEN1", "DecoderKey": "PUMP",
                                     "Field": "pump_speed", "Unit": "rpm", "Video_s": index * 2,
                                     "Value": 500 + index * 20, "OCRLabels": "Pump speed",
                                     "OCRTolerance": 130, "EvidenceGrade": "PROBABLE",
                                     "SourceSession": "S0062"})
            ocr = root / "ocr.csv"
            with ocr.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["Video_s", "Frame", "Text"])
                writer.writeheader()
                for index in range(30):
                    writer.writerow({"Video_s": index * 2, "Frame": f"f{index}.png",
                                     "Text": f"Pump speed {400 + index * 20} rpm"})
            grade_session(decoded, ocr, root / "pairs.csv", root / "grades.csv",
                          root / "grades.json", "S0062", max_lag_seconds=0.1)
            with (root / "grades.csv").open(newline="", encoding="utf-8") as stream:
                grade = next(csv.DictReader(stream))
            self.assertEqual(grade["Agreements"], "30")
            self.assertEqual(grade["RMSE"], "100")
            self.assertNotEqual(grade["PreliminaryLocalGrade"], "CONFIRMATION_READY")
            self.assertIn("RMSE", grade["DecisionReason"])

    def test_distinct_duplicate_session_archives_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, marker in (("CANLOG_A.zip", "A"), ("CANLOG_B.zip", "B")):
                with zipfile.ZipFile(root / name, "w") as archive:
                    archive.writestr("CANLOG/S0060/MANIFEST.JSON", json.dumps({"marker": marker}))
            with zipfile.ZipFile(root / "CAPTURE.zip", "w") as archive:
                archive.writestr("CAPTURE/CAPTURE_SYNC.JSON", json.dumps({
                    "control_events": [{"operation": "START_PASSIVE", "status": 0,
                                        "cyd_session": 60}]}))
            pairs = discover_pairs(root)
            ambiguous = [item for item in pairs if item.status == "AMBIGUOUS"]
            self.assertEqual(len(ambiguous), 1)
            self.assertIsNone(ambiguous[0].logger)
            self.assertEqual(len(ambiguous[0].candidate_loggers), 2)

    def test_byte_identical_canlog_archives_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / "CANLOG_A.zip", "w") as archive:
                archive.writestr("CANLOG/S0061/MANIFEST.JSON", "{}")
            (root / "CANLOG_B.zip").write_bytes((root / "CANLOG_A.zip").read_bytes())
            pairs = discover_pairs(root)
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0].status, "READY")
            self.assertEqual(len(pairs[0].duplicate_archives), 1)

    def test_batch_pairing_uses_successful_ble_start_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with zipfile.ZipFile(root / "CANLOG.zip", "w") as archive:
                archive.writestr("CANLOG/S0018/MANIFEST.JSON", json.dumps({"session": 18}))
                archive.writestr("CANLOG/S0019/MANIFEST.JSON", json.dumps({"session": 19}))
            with zipfile.ZipFile(root / "CAPTURE.zip", "w") as archive:
                archive.writestr("CAPTURE/CAPTURE_SYNC.JSON", json.dumps({
                    "control_events": [{
                        "operation": "START_PASSIVE", "status": 0, "cyd_session": 18,
                    }]
                }))
            pairs = discover_pairs(root)
            self.assertEqual(len(pairs), 2)
            self.assertEqual(pairs[0].session, 18)
            self.assertEqual(pairs[0].basis, "BLE_START_PASSIVE_SESSION")
            self.assertTrue(pairs[0].companion.endswith("CAPTURE.zip"))
            self.assertEqual(pairs[1].session, 19)
            self.assertEqual(pairs[1].basis, "LOGGER_SESSION_UNPAIRED")
            self.assertIsNone(pairs[1].companion)

    def test_candidate_export_never_includes_raw_standard_vin_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "candidates.json"
            request = Request(1, 0x7E0, bytes.fromhex("0902"), 0x09, 0x02)
            transaction = Transaction(
                request, 0x7E8, 2, 3,
                bytes.fromhex("490201") + b"NOT_A_REAL_VIN_001",
                frame_count=3, status="OK",
            )
            # UNKNOWN has no VIN definition, so this follows the candidate path.
            write_signal_candidates(target, [transaction], "UNKNOWN", self.database)
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(result["candidate_count"], 1)
            self.assertEqual(result["candidates"][0]["sample_response_payloads"], [])
            self.assertTrue(result["candidates"][0]["identity_payload_omitted"])
            self.assertNotIn("NOT_A_REAL_VIN_001", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
