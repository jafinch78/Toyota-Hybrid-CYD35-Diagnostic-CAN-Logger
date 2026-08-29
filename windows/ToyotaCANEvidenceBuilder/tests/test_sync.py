import unittest

from toyota_can_processor.sync import fit_alignment


class SyncTests(unittest.TestCase):
    def test_session_specific_affine_fit(self):
        slope = 1000.08
        intercept = 5_000_000_000.0
        samples = []
        for sequence in range(20):
            esp_mid = 1_000_000.0 + sequence * 2_000_000.0
            android_mid = slope * esp_mid + intercept
            samples.append({
                "sequence": sequence,
                "t1_android_ns": int(android_mid - 1_000_000),
                "t4_android_ns": int(android_mid + 1_000_000),
                "e2_esp_us": int(esp_mid - 50),
                "e3_esp_us": int(esp_mid + 50),
            })
        result = fit_alignment({"sync_samples": samples,
                                "video_anchor_ns": int(intercept + slope * 1_000_000),
                                "video_anchor_uncertainty_ns": 33_333_334})
        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.slope_android_ns_per_esp_us, slope, places=3)
        self.assertAlmostEqual(result.video_seconds(1_000_000), 0.0, places=5)

    def test_generic_windows_client_fields(self):
        samples = []
        for sequence in range(6):
            esp = 2_000_000 + sequence * 1_000_000
            client = esp * 1000 + 7_000_000_000
            samples.append({"sequence": sequence, "t1_client_ns": client - 400_000,
                            "t4_client_ns": client + 400_000,
                            "e2_esp_us": esp - 5, "e3_esp_us": esp + 5})
        result = fit_alignment({"sync_samples": samples, "video_anchor_ns": 9_000_000_000})
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
