# Changelog — v2.4.3-rc.1

## Packaging correction

- Replaced the stale TFT title `v2.5 RC2` with a title generated from the shared `FIRMWARE_VERSION` constant (`2.4.3-rc.1`). This is a display-only metadata correction.

## Restored from v2.4.2

- Restored first-missing-`S####` directory allocation.
- Removed the session allocator's NVS reads/writes.
- Removed `NEXT_SESSION.TXT` / `NEXT_SESSION.NEW` reads, writes, renames, and recovery arbitration.
- Removed the allocator-ready gate and allocator counter fields from log startup.
- Retained the v2.4.2 resource settings: CAN queue length 1024 and SD `max_open_files=10`.

## Retained and made safer

- Retained exclusive Wi-Fi maintenance mode: logging must be stopped, and BLE/TWAI are shut down before Wi-Fi starts.
- Replaced permanent session-directory deletion with confirmed file clearing plus a retained tombstone directory.
- Added cleared-session state to the Wi-Fi session list.
- Kept capture format 1.4 and the existing raw 24-byte timestamped `TCB1` records.

## Board isolation

- N35T build: touch flag 7, CAN GPIO25 TX / GPIO32 RX.
- Dorhea B0DLNJSSFW build: touch flag 3, GPIO4 active-low red LED off, candidate CAN GPIO22 TX / GPIO35 RX.
- Added board profile and CAN pin status to each session manifest.

## Safety

- TWAI still starts in `LISTEN_ONLY` mode.
- Diagnostic transmit remains opt-in, profile-gated, read-only, rate-limited, and logged.
- No actuator, fan-control, CAN write, DTC-clear, reset, or coding command was added.
