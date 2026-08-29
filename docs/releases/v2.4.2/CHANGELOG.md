# Changelog

## 2.4.2 — 2026-08-29

- Correct the v2.4.1 boot loop seen only with the microSD installed:
  `BLE ERROR,CREATE_SERVER`, `LoadProhibited`, `EXCVADDR 0x00000000`.
- Allocate BLE controller/service resources before the FAT filesystem, TWAI,
  and large CAN queue; start advertising only after setup completes.
- Reduce CAN queue capacity from 2,048 to 1,024 TCB1 records.
- Reduce SD `max_files` from 16 to 10. Six persistent session files and the
  measured peak of seven descriptors remain supported.
- Add staged `# HEAP` telemetry reporting free, largest-contiguous, and minimum
  heap values.
- Add graceful BLE shutdown/fallback after server, service, characteristic, or
  advertising allocation failure; passive logging remains usable.
- Preserve capture package 1.4, TCB1, BLE protocol 1, read-only diagnostic
  whitelist, GPIO25/GPIO32, and passive Camry behavior.

## 2.4.1 — superseded

- Added deferred traffic-aware sessions and additional SD descriptors.
- Do not deploy: hardware testing found an SD-plus-BLE startup resource failure
  and null-address reboot loop.
