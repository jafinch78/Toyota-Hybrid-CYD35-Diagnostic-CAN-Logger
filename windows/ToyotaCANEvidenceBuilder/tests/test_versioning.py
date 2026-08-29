import unittest

from toyota_can_processor.versioning import check_manifest, normalize_semver


class VersioningTests(unittest.TestCase):
    def test_normalizes_logger_versions(self):
        self.assertEqual(normalize_semver("v2.3"), "2.3.0")
        self.assertEqual(normalize_semver("2.3.1"), "2.3.1")
        self.assertEqual(normalize_semver("ToyotaLogger-v2.4.0"), "2.4.0")

    def test_known_format_accepts_unknown_firmware(self):
        result = check_manifest({"format": "ToyotaHybridCAN-Capture",
                                 "format_version": "1.4",
                                 "firmware_version": "2.9.1",
                                 "raw_format": "TCB1_24_byte_records",
                                 "future_extra_field": 123})
        self.assertTrue(result.supported)
        self.assertTrue(result.warnings)

    def test_unknown_major_stops_safely(self):
        result = check_manifest({"format": "ToyotaHybridCAN-Capture",
                                 "format_version": "2.0",
                                 "firmware_version": "3.0.0",
                                 "raw_format": "TCB2_32_byte_records"})
        self.assertFalse(result.supported)
        self.assertGreaterEqual(len(result.errors), 2)

    def test_missing_manifest_fields_are_blocked(self):
        result = check_manifest({})
        self.assertFalse(result.supported)
        self.assertTrue(result.errors)


if __name__ == "__main__":
    unittest.main()
