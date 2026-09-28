from __future__ import annotations

import importlib.util
from pathlib import Path

BASE_PATH = Path(__file__).with_name("build_can_bth_v2_6_0_firmware.py")
_spec = importlib.util.spec_from_file_location("can_bth_v260_base", BASE_PATH)
_base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_base)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def generate(rc2_dir: Path | str, out_root: Path | str) -> Path:
    out_dir = _base.generate(rc2_dir, out_root)

    meta_path = out_dir / "TVM1Meta.h"
    meta = meta_path.read_text(encoding="utf-8")
    meta = _replace_once(
        meta,
        "static constexpr uint8_t TVM1_STREAM_CAN = 1;",
        "static constexpr uint8_t TVM1_STREAM_CAN = 1;\nstatic constexpr uint8_t TVM1_STREAM_BTH = 2;",
        "TVM1 BTH stream identity",
    )
    meta_path.write_text(meta, encoding="utf-8", newline="\n")

    ino_path = out_dir / "Toyota_Hybrid_CYD35_CAN_BTH_Logger_v2_6_0.ino"
    source = ino_path.read_text(encoding="utf-8")

    source = source.replace(
        "// A 1024-record queue still buffers 24 KiB of raw CAN data while preserving a\n"
        "// larger contiguous block for the ESP32 BLE controller and host stack.\n"
        "constexpr uint16_t CAN_QUEUE_LENGTH = 768;",
        "// A 768-record queue buffers 18 KiB of raw CAN data and recovers 6144 bytes\n"
        "// versus the 1024-record DEV baseline for BLE/BTH/internal-DRAM headroom.\n"
        "constexpr uint16_t CAN_QUEUE_LENGTH = 768;",
    )

    source = _replace_once(
        source,
        "uint32_t bthChunkSequence = 0;\nvolatile uint16_t bthPendingStatus = 0;",
        "uint32_t bthChunkSequence = 0;\nuint32_t lastBthCountersMs = 0;\nvolatile uint16_t bthPendingStatus = 0;",
        "BTH counter cadence state",
    )

    source = _replace_once(
        source,
        "  bthChunkSequence = 0;\n  bthPendingStatus = 0;",
        "  bthChunkSequence = 0;\n  lastBthCountersMs = millis();\n  bthPendingStatus = 0;",
        "BTH session counter timer reset",
    )

    source = _replace_once(
        source,
        "  emitPeriodicHealth();\n"
        "  if (BTH_CAPTURE_ENABLED && loggingActive && millis() - lastHealthMetaMs >= 5000)\n"
        "    emitBthCounters((uint64_t)esp_timer_get_time());\n"
        "  serviceMetaQueue();",
        "  emitPeriodicHealth();\n"
        "  if (BTH_CAPTURE_ENABLED && loggingActive && millis() - lastBthCountersMs >= 5000) {\n"
        "    lastBthCountersMs = millis();\n"
        "    emitBthCounters((uint64_t)esp_timer_get_time());\n"
        "  }\n"
        "  serviceMetaQueue();",
        "independent BTH counter cadence",
    )

    source = _replace_once(
        source,
        "    if (loggingActive && !stopPending) {\n"
        "      stopPending = true;",
        "    if (loggingActive && !stopPending) {\n"
        "      bthSessionAccepting = false;\n"
        "      stopPending = true;",
        "BLE STOP BTH intake gate",
    )

    source = _replace_once(
        source,
        "  if (BTH_CAPTURE_ENABLED) emitBthCounters(nowUs);\n"
        "  emitStreamFileClose(nowUs, rawFileIndex, 1);",
        "  if (BTH_CAPTURE_ENABLED) {\n"
        "    emitBthCounters(nowUs);\n"
        "    serviceMetaQueue();\n"
        "  }\n"
        "  emitStreamFileClose(nowUs, rawFileIndex, 1);",
        "final BTH counters persistence",
    )

    source = source.replace(
        "#if CYD_BOARD_DORHEA_B0DLNJSSFW\n",
        "#if CYD_BOARD_PROFILE_SELECT == CYD_BOARD_PROFILE_DORHEA\n",
    )

    ino_path.write_text(source, encoding="utf-8", newline="\n")
    return out_dir


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("rc2_dir", type=Path)
    parser.add_argument("out_root", type=Path)
    args = parser.parse_args()
    print(generate(args.rc2_dir, args.out_root))
