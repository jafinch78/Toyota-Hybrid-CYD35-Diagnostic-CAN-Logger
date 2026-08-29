# Validation and first-board test

## Completed before packaging

- v2.4.1 failure evidence recorded: `CREATE_SERVER`, `LoadProhibited`, and null
  exception address; boot succeeded after the SD card was removed.
- BLE service creation is ordered before SD, TWAI, and the large CAN queue.
- BLE advertising is deferred until the end of setup.
- BLE failure paths release BLE resources and do not dereference failed objects.
- SD is mounted with 10 descriptors; the existing session design peaks at seven.
- CAN queue is 1,024 packed 24-byte records (24 KiB).
- Diagnostic table contains only read-only services `01` and `21`.
- Guards found no Mode `2E`, Mode `3E`, fan override, SD format, arbitrary BLE
  CAN transmit, actuator, clear, reset, or coding operation.
- TCB1 record size remains protected by a 24-byte `static_assert`.
- Capture package 1.4 and ToyotaCYD-Sync/1 are unchanged.
- Host C++17 syntax validation with Arduino/ESP32 API stubs passed across the
  2,241-line sketch; the final board-package compile remains an Arduino IDE step.
- All nine Toyota CAN Evidence Builder unit tests passed; firmware 2.4.x with
  capture package 1.4 and TCB1 remains accepted by its version parser.

The final ESP32 compile and CYD test must be performed in Arduino IDE because
the release environment does not include the ESP32 Arduino board package.

## Required USB bench test with microSD installed

1. Insert the same 483 MB microSD and power the CYD by USB.
2. Open Serial Monitor at 115200 baud and press the board EN/reset button once.
3. Confirm one startup sequence, not repeated reboot banners. Expected lines:

   ```text
   # ToyotaHybridCAN Diagnostic Logger v2.4.2
   # HEAP,BOOT,...
   # BLE SERVICE READY,ToyotaCYD-xxxx,advertising=deferred
   # SD READY,max_open_files=10,session=deferred
   # BLE READY,ToyotaCYD-xxxx,6ed9f000-4f21-4c8c-a8a7-923c86b40001
   # EVENT,...,INFO,TWAI_READY,500 kbps LISTEN_ONLY; GPIO25 TX; GPIO32 RX
   ```

4. Confirm the TFT remains stable and shows `BLE ADV`.
5. Connect the Android recorder and confirm `BLE CON`.
6. Press Start, wait at least ten seconds without CAN, then Stop. Confirm no
   file-descriptor error and no reboot. The session should close as empty.
7. Save all `# HEAP` lines. The `largest=` value after `SETUP_COMPLETE` is the
   most useful margin measurement.

## Vehicle test after the bench test passes

1. Keep diagnostics off and perform the first capture while stationary.
2. Connect VP230 CAN-H/CAN-L to OBD-II pins 6/14 without additional termination.
3. Start logging before IG-ON/READY; confirm first traffic changes the state from
   `ARMED / WAIT CAN` to `LOGGING`.
4. Stop cleanly and process the complete session folder.
5. Test optional Prius Gen 2 read-only diagnostics separately only after passive
   logging succeeds. Camry Hybrid remains passive-only.

Incorrect CAN transmission can affect vehicle behavior. Passive listen-only
capture is the required first validation mode.
