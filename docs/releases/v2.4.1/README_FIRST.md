# Toyota Hybrid CYD35 Diagnostic CAN Logger v2.4.1

This is the SD reliability and traffic-aware session update to v2.4.0. It keeps
the working BLE protocol and the established capture formats unchanged.

## Install

1. Extract this release.
2. Open
   `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_1/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_4_1.ino`
   in Arduino IDE.
3. Keep that `.ino` inside the identically named folder. Do not put another
   `.ino` in the same folder.
4. Use ESP32 Arduino core 3.3.10, `ESP32 Dev Module`, the active CYD TFT_eSPI
   configuration, and the correct COM port.
5. Compile, then upload. The microSD card is not required for upload; insert it
   before starting a logging session.

The included `TFT_eSPI_User_Setup_CYD35.h` is a reference. Copy its definitions
into the active TFT_eSPI `User_Setup.h`; do not rename it to another `.ino` tab.

## Principal v2.4.1 corrections

- Uses 16 SD descriptors instead of the default five, fixing
  `vfs_fat: open: no free file descriptors`.
- Defers `Snnnn` creation until touchscreen or BLE Start.
- Starts as `ARMED / WAIT CAN`, becomes `LOGGING` on the first received frame,
  and reports `LOG / NO CAN` if traffic becomes stale.
- Does not write repeated empty decoded rows on an unconnected bench.
- Reports session-open failures on Serial and the TFT.
- Shows BLE `ADV`, `CON`, or `ERR` even when no vehicle is connected.
- Explicitly closes temporary directory listing handles.

## Compatibility and safety

- Capture package: 1.4
- Raw format: TCB1 with unchanged packed 24-byte records
- BLE protocol: ToyotaCYD-Sync/1 with unchanged service and commands
- CAN TX/RX: GPIO25/GPIO32
- TWAI default: hardware listen-only at 500 kbit/s
- Camry Hybrid: passive-only
- Diagnostic mode: explicit touchscreen action, active logging, strong Prius
  Gen 2 profile, no recently observed external tester, and a fixed read-only
  Mode 01/21 whitelist

There is no BLE CAN-transmit API and no fan, actuator, write, clear-code, reset,
coding, SD erase, or SD format command.

## Rollback

The `rollback` folder contains:

- v2.3.0: preferred capture-tested rollback without BLE synchronization.
- v2.4.0: immediate predecessor retained for exact comparison; it has the
  five-descriptor SD defect and should not be used for dependable logging.

Read `VALIDATION_AND_TEST.md` before the first vehicle capture.
