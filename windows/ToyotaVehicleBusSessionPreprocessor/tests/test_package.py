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
    def test_package_exposes_version_and_model_types(self):
        pkg = importlib.import_module("toyota_vehicle_bus_session")
        self.assertEqual(pkg.__version__, "0.1.0")
        self.assertTrue(hasattr(pkg, "ExpansionOptions"))
        self.assertTrue(hasattr(pkg, "ExpansionResult"))

    def test_pyproject_declares_expected_console_scripts_and_python_floor(self):
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["requires-python"], ">=3.10")
        self.assertEqual(
            data["project"]["scripts"]["toyota-session-preprocess"],
            "toyota_vehicle_bus_session.cli:main",
        )
        self.assertEqual(
            data["project"]["scripts"]["toyota-session-preprocess-gui"],
            "toyota_vehicle_bus_session.gui:main",
        )
        self.assertEqual(data["project"].get("dependencies", []), [])


if __name__ == "__main__":
    unittest.main()
