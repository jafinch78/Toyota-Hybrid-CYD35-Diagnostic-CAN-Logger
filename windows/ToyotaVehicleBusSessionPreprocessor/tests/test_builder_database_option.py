from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from toyota_vehicle_bus_session import oracle


class BuilderDatabaseOptionTests(unittest.TestCase):
    def test_builder_oracle_passes_same_explicit_database_to_builder(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            database = root / "toyota_hybrid_can_db_v0.9.50.json"
            database.write_text("{}", encoding="utf-8")
            fake_output = root / "BuilderOutput"
            completed = type("Completed", (), {
                "returncode": 0,
                "stdout": '{\n  "output": "' + str(fake_output).replace('\\', '\\\\') + '"\n}\n',
                "stderr": "",
            })()
            with patch.object(oracle.subprocess, "run", return_value=completed) as run:
                result = oracle._run_builder(
                    Path("python"), root / "CANLOG.zip", root / "out", None, database)
            self.assertEqual(result, fake_output)
            command = run.call_args.args[0]
            self.assertIn("--database", command)
            self.assertEqual(command[command.index("--database") + 1], str(database))

    def test_real_campaign_parser_accepts_builder_database_and_no_analyzer_gate(self) -> None:
        import importlib.util
        import sys

        script = Path(__file__).resolve().parents[1] / "scripts" / "validate_real_sessions.py"
        spec = importlib.util.spec_from_file_location("validate_real_sessions_db_option", script)
        if spec is None or spec.loader is None:
            self.fail("unable to load validate_real_sessions.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        option_names = {action.dest for action in module.build_parser()._actions}
        self.assertIn("builder_database", option_names)
        self.assertNotIn("analyzer_smoke_report", option_names)


if __name__ == "__main__":
    unittest.main()
