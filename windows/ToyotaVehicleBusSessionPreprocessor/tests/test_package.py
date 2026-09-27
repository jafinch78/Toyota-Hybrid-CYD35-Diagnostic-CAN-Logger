from __future__ import annotations

import importlib
import pathlib
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PackageContractTests(unittest.TestCase):
    def test_public_version_and_dataclasses_import(self) -> None:
        mod = importlib.import_module("toyota_vehicle_bus_session")
        self.assertEqual(mod.__version__, "0.1.0")
        self.assertTrue(hasattr(mod, "ExpansionOptions"))
        self.assertTrue(hasattr(mod, "ExpansionResult"))

    def test_pyproject_console_scripts_and_no_runtime_dependencies(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        self.assertEqual(project["requires-python"], ">=3.10")
        self.assertEqual(project.get("dependencies", []), [])
        self.assertEqual(
            project["scripts"]["toyota-session-preprocess"],
            "toyota_vehicle_bus_session.cli:main",
        )
        self.assertEqual(
            project["scripts"]["toyota-session-preprocess-gui"],
            "toyota_vehicle_bus_session.gui:main",
        )


if __name__ == "__main__":
    unittest.main()
