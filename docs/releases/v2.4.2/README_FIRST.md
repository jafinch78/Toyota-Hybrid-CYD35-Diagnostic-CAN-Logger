# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.2

This release corrects the v2.4.1 SD-plus-BLE startup failure observed on the
ESP32-D0WD-V3 CYD. With a 483 MB microSD installed, v2.4.1 reported
`BLE ERROR,CREATE_SERVER`, dereferenced address zero, and rebooted repeatedly.
Removing the card allowed startup, isolating resource order/fragmentation.

## Install

1. Extract this release.
2. Open
   `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_2/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_2.ino`
   in Arduino IDE.
3. Keep that `.ino` inside the identically named folder. Do not place another
   `.ino` in the same Arduino sketch folder.
4. Use ESP32 Arduino core 3.3.10, `ESP32 Dev Module`, the active CYD TFT_eSPI
   setup, and the correct COM port.
5. Use the same partition scheme that compiled v2.4.1. The SPIFFS partition does
   not increase runtime heap; the v2.4.2 fix is in startup/resource handling.
6. Compile and upload. The card is not needed during upload, but the first bench
   test must be performed with it installed.

The included `TFT_eSPI_User_Setup_CYD35.h` is a reference for the active
TFT_eSPI `User_Setup.h`; it is not an Arduino sketch tab.

## v2.4.2 corrections

- Builds the BLE service before SD, TWAI, and the large CAN receive queue.
- Delays BLE advertising until all logger subsystems finish initialization.
- Reduces the CAN queue from 2,048 to 1,024 packed records (48 KiB to 24 KiB).
- Uses 10 SD descriptors: enough for the measured peak of seven, with headroom.
- Treats every BLE allocation failure as nonfatal: BLE becomes `ERR`, releases
  its stack resources, and passive CAN/SD logging can continue.
- Prints free, minimum, and largest-contiguous heap measurements at each setup
  stage for hardware verification.

## Compatibility and safety

- Capture package 1.4 and TCB1 24-byte records are unchanged.
- ToyotaCYD-Sync/1 UUIDs and Android/Windows protocol are unchanged.
- CAN TX/RX remain GPIO25/GPIO32 at 500 kbit/s.
- TWAI still starts in hardware listen-only mode.
- Camry Hybrid remains passive-only.
- Optional Prius Gen 2 diagnostics remain explicitly enabled, profile-gated,
  rate-limited, and limited to the fixed read-only Mode 01/21 whitelist.
- There is no actuator, fan-control, write, clear, reset, coding, arbitrary BLE
  CAN-transmit, SD erase, or SD format command.

Read `VALIDATION_AND_TEST.md` before connecting to a vehicle. Do not use v2.4.1;
it is retained in `rollback` only as a reproducible failed-build reference.
