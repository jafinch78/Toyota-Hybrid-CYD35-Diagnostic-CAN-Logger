import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toyota_can_processor.dependency_setup import (DependencyStatus,
                                                   ensure_voice_dependencies)


class DependencySetupTests(unittest.TestCase):
    def test_voice_repair_uses_active_interpreter_and_rechecks_imports(self):
        broken = [DependencyStatus("faster-whisper", "1.2.0", False, "requests missing"),
                  DependencyStatus("requests", None, False, "not installed")]
        repaired = [DependencyStatus("faster-whisper", "1.2.0", True),
                    DependencyStatus("requests", "2.32.0", True)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "requirements-voice-optional.txt").write_text(
                "faster-whisper==1.2.0\nrequests>=2.31,<3\n", encoding="utf-8")
            with patch("toyota_can_processor.dependency_setup.app_root", return_value=root), \
                    patch("toyota_can_processor.dependency_setup.voice_dependency_status",
                          side_effect=[broken, repaired]), \
                    patch("toyota_can_processor.dependency_setup.subprocess.run",
                          return_value=SimpleNamespace(returncode=0, stdout="installed\n")) as run:
                result = ensure_voice_dependencies()
        self.assertTrue(all(status.import_ok for status in result))
        command = run.call_args.args[0]
        self.assertEqual(command[1:4], ["-m", "pip", "install"])
        self.assertTrue(command[0])


if __name__ == "__main__":
    unittest.main()
