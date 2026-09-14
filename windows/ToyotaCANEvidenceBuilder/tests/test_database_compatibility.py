import copy
import json
import tempfile
import unittest
from pathlib import Path

from toyota_can_processor.database import (
    DATABASE_FILE,
    find_definition,
    load_database,
    verify_database_unchanged,
)
from toyota_can_processor.decoding import decode_definition
from toyota_can_processor.processor import ProcessingOptions, process


class DatabaseCompatibilityTests(unittest.TestCase):
    DATA = Path(__file__).parents[1] / "toyota_can_processor" / "data"
    EXPECTED = {
        "0.5.5": ("1.0.0", "6833c8ccddab9294c1fa07caadb0e49649a38fed997289881726e59be0471869"),
        "0.5.6": ("1.1.0", "afcd6f0c1c0e78675552a77a4686ae23339547bdc7c890df3a758c0e39c37b9a"),
        "0.5.7": ("1.1.1", "a936dfa0dd2149b0c452cbc520a96b314966e0eabea15ecf45768a96012ff6b1"),
        "0.5.8": ("1.2.0", "a6d8b35877d56c6204b162f33147c054e8dd2311479c2a2bc35c3d8926c03604"),
        "0.5.9": ("1.2.0", "28c0ac47db211cde9ef318ef55bb3bf9bc0cc4017b06227753d1cf18ed12a979"),
    }

    def test_requested_database_versions_load_with_expected_hashes(self):
        for version, (schema, expected_hash) in self.EXPECTED.items():
            with self.subTest(version=version):
                path = self.DATA / f"toyota_hybrid_can_db_v{version}.json"
                _, info = load_database(path)
                self.assertEqual(info.version, version)
                self.assertEqual(info.schema_version, schema)
                self.assertEqual(info.definition_count, 44)
                self.assertEqual(info.sha256, expected_hash)

    def test_processing_records_selected_database_and_unchanged_verification(self):
        for version, (schema, expected_hash) in self.EXPECTED.items():
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                session = root / "CANLOG" / "S0001"
                session.mkdir(parents=True)
                (session / "MANIFEST.JSON").write_text(json.dumps({
                    "format": "ToyotaHybridCAN-Capture",
                    "format_version": "1.3",
                    "firmware_version": "v2.3",
                    "raw_format": "TCB1_24_byte_records",
                    "vehicle_profile": "PRIUS GEN 2",
                    "profile_confidence_pct": 50,
                }), encoding="utf-8")
                database_path = self.DATA / f"toyota_hybrid_can_db_v{version}.json"
                result = process(
                    root / "CANLOG", root / "out",
                    options=ProcessingOptions(database_path=database_path),
                )
                summary = json.loads(
                    (Path(result["output"]) / "S0001" / "SESSION_SUMMARY.json").read_text())
                provenance = summary["decoder_database"]
                self.assertEqual(provenance["version"], version)
                self.assertEqual(provenance["schema_version"], schema)
                self.assertEqual(provenance["sha256"], expected_hash)
                self.assertTrue(provenance["verified_unchanged_after_processing"])
                report = (Path(result["output"]) / "S0001" / "REPORT.html").read_text()
                self.assertIn(expected_hash, report)
                self.assertIn("Unchanged after processing</th><td>True", report)

    def test_default_is_v059_and_candidate_registry_is_metadata_only(self):
        database, info = load_database()
        self.assertEqual(DATABASE_FILE.name, "toyota_hybrid_can_db_v0.5.9.json")
        self.assertEqual(info.version, "0.5.9")
        self.assertEqual(info.field_specific_definition_count, 2)
        self.assertEqual(info.candidate_observation_count, 267)
        self.assertEqual(info.candidate_unique_response_shape_count, 243)
        self.assertEqual(info.candidate_unique_request_tuple_count, 238)
        self.assertTrue(info.candidate_registry_ignored_for_decoding)
        candidate = database["candidate_registry"]["observations"][0]
        self.assertIsNone(find_definition(
            database,
            candidate.get("profile", "UNKNOWN"),
            int(candidate["request_id"], 16),
            int(candidate["service"], 16),
            int(candidate["pid"], 16) if candidate.get("pid") is not None else None,
        ))

    def test_v059_includes_s0069_ahv40_21c3_fields(self):
        database, _ = load_database()
        definition = next(
            item for item in database["definitions"]
            if item["key"] == "AHV40_HYBRID_ECU_21C3_MG_TEMPERATURES"
        )
        fields = {field["name"]: field for field in definition["fields"]}
        self.assertEqual(fields["mg2_revolution"]["formula"], "uint16-16383")
        self.assertEqual(fields["mg2_torque"]["formula"], "(uint16-4000)/8")
        self.assertEqual(fields["mg1_revolution"]["evidence_grade"], "CONFIRMED")
        self.assertEqual(fields["mg1_torque_execution_value"]["evidence_grade"], "PROBABLE")
        self.assertEqual(fields["engine_speed"]["ocr_labels"], ["Engine spd"])

    def test_field_repeat_and_derived_grades_are_preserved(self):
        definition = {
            "key": "GRADE_TEST",
            "profile": "PRIUS_GEN2",
            "request_id": "7E3",
            "service": "21",
            "pid": "AA",
            "response_prefix": "61AA",
            "decoder": "block_array",
            "evidence_grade": "FIELD_SPECIFIC",
            "safety_class": "READ_ONLY_DIAGNOSTIC",
            "fields": [
                {"name": "base", "offset": 0, "width_bytes": 1,
                 "formula": "raw", "evidence_grade": "CONFIRMED"},
                {"name": "second", "offset": 1, "width_bytes": 1,
                 "formula": "raw", "evidence_grade": "CANDIDATE"},
            ],
            "repeat": {"name": "cell", "data_offset": 2, "count": 2,
                       "width_bytes": 1, "evidence_grade": "PROBABLE"},
            "derived_fields": [
                {"name": "sum", "formula": "base + second",
                 "evidence_grade": "CONFIRMED"},
            ],
        }
        decoded = decode_definition(bytes.fromhex("61AA01020304"), definition)
        self.assertTrue(decoded["matched"])
        self.assertEqual(
            [item["evidence_grade"] for item in decoded["fields"]],
            ["CONFIRMED", "CANDIDATE", "CONFIRMED"],
        )
        self.assertEqual(
            [item["evidence_grade"] for item in decoded["arrays"]],
            ["PROBABLE", "PROBABLE"],
        )

    def test_database_hash_detects_mutation(self):
        source = self.DATA / "toyota_hybrid_can_db_v0.5.8.json"
        with tempfile.TemporaryDirectory() as directory:
            copy_path = Path(directory) / source.name
            copy_path.write_bytes(source.read_bytes())
            _, info = load_database(copy_path)
            verify_database_unchanged(info)
            copy_path.write_bytes(copy_path.read_bytes() + b"\n")
            with self.assertRaisesRegex(RuntimeError, "changed during processing"):
                verify_database_unchanged(info)

    def test_unsupported_schema_and_unsafe_candidate_registry_are_rejected(self):
        source = json.loads((self.DATA / "toyota_hybrid_can_db_v0.5.8.json").read_text())
        cases = []
        unsupported = copy.deepcopy(source)
        unsupported["schema_version"] = "1.3.0"
        cases.append((unsupported, "Unsupported decoder database schema"))
        active = copy.deepcopy(source)
        active["candidate_registry"]["active_polling"] = "ALLOWED"
        cases.append((active, "active polling must be EXCLUDED"))
        promoted = copy.deepcopy(source)
        promoted["candidate_registry"]["automatic_promotion_allowed"] = True
        cases.append((promoted, "automatic promotion must be disabled"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "database.json"
            for database, message in cases:
                with self.subTest(message=message):
                    path.write_text(json.dumps(database), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        load_database(path)


if __name__ == "__main__":
    unittest.main()
