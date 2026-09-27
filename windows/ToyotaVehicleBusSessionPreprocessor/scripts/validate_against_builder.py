from __future__ import annotations

import argparse
import json
from pathlib import Path

from toyota_vehicle_bus_session.oracle import run_builder_oracle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare original and TVM1-expanded CANLOGs through Evidence Builder 1.0.4")
    parser.add_argument("original_canlog", type=Path)
    parser.add_argument("expanded_canlog", type=Path)
    parser.add_argument("--builder-python", type=Path, required=True)
    parser.add_argument("-c", "--capture", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = run_builder_oracle(args.builder_python, args.original_canlog,
                                    args.expanded_canlog, args.capture, args.output)
    except Exception as error:
        print(json.dumps({"passed": False, "error": str(error)}, indent=2))
        return 1
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
