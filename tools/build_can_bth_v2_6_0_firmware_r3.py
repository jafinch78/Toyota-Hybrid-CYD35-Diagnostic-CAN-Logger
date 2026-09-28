from __future__ import annotations

import importlib.util
from pathlib import Path

BASE_PATH = Path(__file__).with_name("build_can_bth_v2_6_0_firmware_r2.py")
_spec = importlib.util.spec_from_file_location("can_bth_v260_r2", BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_base)

OLD_BOARD_BLOCK = r'''#define CYD_BOARD_PROFILE_DORHEA 1
#define CYD_BOARD_PROFILE_E32R35T 2
#ifndef CYD_BOARD_PROFILE_SELECT
#define CYD_BOARD_PROFILE_SELECT CYD_BOARD_PROFILE_DORHEA
#endif

#if CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_DORHEA
constexpr char CYD_BOARD_PROFILE[] = "DORHEA_B0DLNJSSFW_TOUCH";
uint16_t touchCalibration[5] = {295, 3524, 310, 3487, 3};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = false;
#elif CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_E32R35T
constexpr char CYD_BOARD_PROFILE[] = "E32R35T_TOUCH";
uint16_t touchCalibration[5] = {0, 0, 0, 0, 0};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = true;
#else
#error "CYD_BOARD_PROFILE_SELECT must be Dorhea or E32R35T"
#endif'''

NEW_BOARD_BLOCK = r'''#define CYD_BOARD_PROFILE_DORHEA 1
#define CYD_BOARD_PROFILE_E32R35T 2
#define CYD_BOARD_PROFILE_E32N35T 3
#ifndef CYD_BOARD_PROFILE_SELECT
#define CYD_BOARD_PROFILE_SELECT CYD_BOARD_PROFILE_DORHEA
#endif

#if CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_DORHEA
constexpr char CYD_BOARD_PROFILE[] = "DORHEA_B0DLNJSSFW_TOUCH";
uint16_t touchCalibration[5] = {295, 3524, 310, 3487, 3};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = false;
#elif CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_E32R35T
constexpr char CYD_BOARD_PROFILE[] = "E32R35T_TOUCH";
uint16_t touchCalibration[5] = {0, 0, 0, 0, 0};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = true;
#elif CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_E32N35T
constexpr char CYD_BOARD_PROFILE[] = "E32N35T_TOUCH";
uint16_t touchCalibration[5] = {295, 3524, 310, 3487, 7};
constexpr bool CYD_TOUCH_AUTO_CALIBRATE = false;
#else
#error "CYD_BOARD_PROFILE_SELECT must be Dorhea, E32R35T, or E32N35T"
#endif'''


def generate(rc2_dir: Path | str, out_root: Path | str) -> Path:
    out_dir = _base.generate(rc2_dir, out_root)
    ino_path = out_dir / "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0.ino"
    source = ino_path.read_text(encoding="utf-8")
    count = source.count(OLD_BOARD_BLOCK)
    if count != 1:
        raise ValueError(f"expected one v2.6 board profile block, found {count}")
    source = source.replace(OLD_BOARD_BLOCK, NEW_BOARD_BLOCK, 1)
    ino_path.write_text(source, encoding="utf-8", newline="\n")

    readme_path = out_dir / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme += """

## CYD board profile selection

Three display/logger profiles are deliberately distinct:

- `CYD_BOARD_PROFILE_DORHEA=1` - fixed validated Dorhea touch calibration `{295,3524,310,3487,3}`.
- `CYD_BOARD_PROFILE_E32R35T=2` - first-boot touch calibration; no N35T constants are relabelled as R35T.
- `CYD_BOARD_PROFILE_E32N35T=3` - preserves the RC2 N35T fallback calibration `{295,3524,310,3487,7}`.

The checked-in/default build remains Dorhea. For an N35T or R35T image, compile with `CYD_BOARD_PROFILE_SELECT` set to 3 or 2 respectively. All three profiles must compile before a test package is published.
"""
    readme_path.write_text(readme, encoding="utf-8", newline="\n")
    return out_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("rc2_dir", type=Path)
    parser.add_argument("out_root", type=Path)
    args = parser.parse_args()
    print(generate(args.rc2_dir, args.out_root))
