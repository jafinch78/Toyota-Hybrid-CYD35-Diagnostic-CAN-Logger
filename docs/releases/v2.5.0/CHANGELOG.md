# Changelog

## 2.5.0-rc.1 — 2026-08-30

- Add an exclusive Wi-Fi SD file-transfer application mode.
- Add a four-button normal screen without reducing the validated 105x50 touch
  targets.
- Add a two-step Wi-Fi entry screen and restart-only exit path.
- Shut down TWAI, BLE, and their queues before allocating Wi-Fi services.
- Add a randomized persistent WPA2 password shown on TFT and Serial Monitor.
- Add HTTP file API v1 and a mobile browser interface.
- Add HTTP Range support for individual files.
- Add on-the-fly stored ZIP output with CRC-32 and no temporary SD write.
- Add clean-session deletion protected by typed confirmation and a per-boot
  authorization token.
- Add `MONOTONIC_V1` session allocation using existing-directory scan, SD
  high-water files, and NVS.
- Record allocator and Wi-Fi API policy in session metadata.
- Preserve capture package 1.4, TCB1, ToyotaCYD-Sync/1, and all CAN safety
  restrictions from v2.4.2.
