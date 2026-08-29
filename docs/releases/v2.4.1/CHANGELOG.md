# Changelog

## 2.4.1 — 2026-08-29

- Mount SD with `max_files=16`.
- Mount and validate `/CANLOG` at boot without consuming a session number.
- Allocate the session transactionally on explicit Start and remove only the
  newly allocated partial session if its required files cannot open.
- Reset raw, diagnostic, and SD-drop counters per session while retaining
  since-boot RX/TX and controller-health counters.
- Record session start, first/last CAN timestamps, traffic state, and
  per-session RX/TX counts in manifest/checkpoint metadata.
- Suppress decoded and optional USB decoded output while session CAN traffic is
  absent or stale.
- Add first-traffic and empty-session evidence events.
- Add TFT armed/logging/stale/start-failure states and persistent BLE status.
- Close SD directory entries and roots explicitly.
- Preserve capture 1.4, TCB1, BLE protocol 1, read-only diagnostics, pins, and
  passive Camry behavior.
