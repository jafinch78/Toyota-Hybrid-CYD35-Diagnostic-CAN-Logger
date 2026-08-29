# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.1

This is the BLE-synchronized successor to v2.3.0. It targets the
ESP32-3248S035R/E32R35T 3.5-inch resistive-touch CYD, SN65HVD230/VP230, and a
500 kbit/s Toyota CAN bus.

## Validated hardware configuration

- CAN TX GPIO25; CAN RX GPIO32
- VP230 CAN-H to OBD-II pin 6; CAN-L to pin 14
- No added 120-ohm termination on an intact vehicle bus
- TFT backlight GPIO27; touch CS GPIO33
- SD SCK/MISO/MOSI/CS GPIO18/19/23/5 on separate HSPI
- Touch calibration `{295, 3524, 310, 3487, 7}`

## What changed from v2.4.0

- Fixes the ESP32 SD `no free file descriptors` failure by mounting with 16
  descriptors. Six session streams remain open and metadata operations retain
  safe headroom.
- Mounting the card no longer creates a session directory. A new `Snnnn`
  directory is allocated only after an explicit touchscreen or BLE Start.
- Start initially displays `ARMED / WAIT CAN`, allowing capture of the useful
  OFF-to-IG-ON/READY transition. It changes to `LOGGING` after the first received
  CAN frame and to `LOG / NO CAN` if traffic later becomes stale.
- Repeated empty `UNKNOWN / PROFILE_AMBIGUOUS` decoded rows are suppressed while
  no CAN traffic is present. The binary RAW stream remains authoritative.
- SD/session start failures are printed explicitly and shown on the TFT.
- BLE status is always visible as `ADV`, `CON`, or `ERR`.
- Directory handles are explicitly closed after card listings.

Capture package 1.4, the 24-byte TCB1 record, ToyotaCYD-Sync/1 BLE UUIDs and
commands, and the read-only diagnostic whitelist are unchanged from v2.4.0.

## Arduino IDE installation

1. Install ESP32 Arduino core 3.3.10 and the `TFT_eSPI` library.
2. Replace the active TFT_eSPI `User_Setup.h` definitions with those in
   `TFT_eSPI_User_Setup_CYD35.h`.
3. Create an Arduino folder named
   `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_1`.
4. Put only the identically named `.ino` in that folder. The reference header
   must not become a second Arduino tab.
5. Select `ESP32 Dev Module`, the correct COM port, and upload. A microSD card is
   not needed for upload, but is required to start a log.

## Operating modes

- `LISTEN-ONLY`: default and required while Hybrid Assistant, Dr. Prius,
  MaxiAP200, Techstream, or another tester is active.
- `NORMAL DIAGNOSTIC`: available only after a strong Prius Gen 2 fingerprint,
  active SD logging, no recently observed external tester, and an explicit
  touchscreen press. It uses only the fixed read-only whitelist.
- Camry Hybrid remains passive-only.

No fan, actuator, write, clear-code, reset, coding, erase, or format command is
present. Incorrect CAN transmission can affect vehicle behavior; use passive
capture for discovery and perform any diagnostic-mode testing while stationary.

## Expected bench test without a vehicle

1. Boot with the microSD inserted. The TFT shows `READY / STOPPED` and no new
   session folder is created.
2. BLE shows `ADV`, then `CON` after the companion connects.
3. Press `START LOG`. A new session is created and the TFT shows
   `Snnnn ARMED / WAIT CAN`.
4. Wait at least ten seconds. `DECODED.CSV` receives only its header; it does not
   accumulate empty rows.
5. Press `STOP LOG`. The TFT shows `Snnnn CLOSED EMPTY`, `SESSION.OPEN` is
   removed, and Serial prints `# LOG CLOSED`.

## Rollback

The release bundle includes the unchanged v2.4.0 immediate predecessor and the
known capture-tested v2.3.0 release. Prefer v2.3.0 if rollback logging is needed,
because v2.4.0 retains the five-descriptor SD defect corrected here. TCB1 data
from all versions remains readable by the Windows processor.
