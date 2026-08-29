# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.0

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

## What changed from v2.3.0

- The controller starts in hardware `TWAI_MODE_LISTEN_ONLY`.
- BLE service `ToyotaCYD-Sync/1` provides four-timestamp clock exchanges,
  start/stop logging, and narration markers. It exposes no CAN injection API.
- BLE synchronized capture always forces diagnostics off and listen-only mode.
- `SYNC.CSV` preserves ESP32 E2/E3 samples; the phone/PC companion preserves
  client T1/T4 samples and the video time anchor.
- Externally observed 7DF/7E0-7E7 diagnostic requests force logger diagnostics
  off. Their traffic is preserved in `EXTERNAL_DIAGNOSTICS.CSV` rather than
  being reported as a failed logger transaction.
- Capture package 1.4 adds optional BLE fields and files. TCB1 records remain
  byte-for-byte compatible with v2.3.
- Automatic logging at boot is off. Start from the Android/Windows companion or
  press `START LOG` on the CYD.

## Arduino IDE installation

1. Install ESP32 Arduino core 3.3.10 and the `TFT_eSPI` library.
2. Replace the active TFT_eSPI `User_Setup.h` definitions with those in
   `TFT_eSPI_User_Setup_CYD35.h`.
3. Create an Arduino folder named
   `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_0`.
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

## Rollback

The release bundle includes the unchanged v2.3.0 ZIP under `firmware/rollback`.
Upload that sketch if BLE affects stability on the actual board. TCB1 data from
both versions remains readable by the Windows processor.
