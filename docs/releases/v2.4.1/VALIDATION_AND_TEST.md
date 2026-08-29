# Validation and first-board test

## Completed before packaging

- C++ lexical/delimiter scan passed across 2,168 source lines.
- Duplicate function-definition scan passed (67 definitions).
- Diagnostic request table contains only read-only services `01` and `21`.
- Source guard confirmed no Mode `2E`, Mode `3E`, fan override, SD format, or
  arbitrary BLE CAN-transmit command.
- Source guard confirmed `initializeSD()` does not create a session.
- Source guard confirmed SD is mounted with 16 descriptors.
- TCB1 packed-record `static_assert` remains 24 bytes.
- Extracted manifest and checkpoint output templates both parsed as valid JSON
  (68 manifest keys and 30 checkpoint keys).
- Session-state model confirmed zero boot folders, one folder per explicit
  Start, zero empty decoded rows before traffic, and a seven-descriptor peak
  below the configured capacity of 16.
- All nine Toyota CAN Evidence Builder unit tests passed.
- A synthetic firmware 2.4.1 / capture 1.4 / TCB1 manifest was accepted with no
  warnings or errors by the installed processor version logic.

The release environment does not contain the ESP32 Arduino board package, so
the final Arduino compile and CYD hardware test must be performed in Arduino IDE.
The target setup is the already working ESP32 core 3.3.10 configuration used for
v2.4.0.

## Bench test — SD, touch, and BLE only

1. Insert the microSD card and power the CYD by USB.
2. Serial should include:

   ```text
   # ToyotaHybridCAN Diagnostic Logger v2.4.1
   # SD READY,max_open_files=16,session=deferred
   # BLE READY,ToyotaCYD-xxxx,6ed9f000-4f21-4c8c-a8a7-923c86b40001
   ```

3. The TFT should show `READY / STOPPED` and `BLE ADV`. Power cycling without
   pressing Start must not create a new `Snnnn` folder.
4. Connect the Android companion. The TFT should change to `BLE CON`.
5. Press Start. Serial should show `# LOG STARTED,...,ARMED_WAIT_CAN`; the TFT
   should show `Snnnn ARMED / WAIT CAN` with an orange Stop button.
6. Leave it running for at least ten seconds without CAN, then press Stop.
7. Confirm there is no `vfs_fat: open: no free file descriptors` message. The
   TFT should show `Snnnn CLOSED EMPTY`.
8. On the card, confirm `SESSION.OPEN` is absent and `DECODED.CSV` has its header
   but no repeated `PROFILE_AMBIGUOUS` rows.

## Vehicle test — passive first

1. Keep diagnostics off. Connect VP230 CAN-H/CAN-L to OBD-II pins 6/14 with no
   added 120-ohm termination.
2. Start logging before switching the vehicle to IG-ON/READY so the transition
   is captured.
3. The TFT should change from `ARMED / WAIT CAN` to green `LOGGING` after the
   first received frame. Serial should include `CAN_TRAFFIC_STARTED`.
4. Record a short stationary session and stop cleanly.
5. Process the entire `Snnnn` folder with Toyota CAN Evidence Builder. Confirm
   firmware 2.4.1/capture 1.4 is supported and TCB1 records decode.
6. Repeat BLE synchronized capture with narration only after the passive test
   succeeds.

Do not enable diagnostic mode during the first v2.4.1 vehicle test. Camry
Hybrid remains passive-only. Prius Gen 2 diagnostics remain optional and must
be tested separately while stationary.
