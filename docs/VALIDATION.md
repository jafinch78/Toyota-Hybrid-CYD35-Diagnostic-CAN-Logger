# Release validation

## Completed in this build environment

- Windows Python modules compiled successfully.
- Nine unit tests passed: firmware/version normalization, known-format forward
  tolerance, missing/malformed-manifest safe stops, unknown-major safe stop,
  TCB1 parsing, truncated-tail recovery, Android-style BLE fitting,
  Windows-style BLE fitting, and v2.3 processing with extra fields.
- The processor completed the supplied `CANLOG(2).zip` containing 34 sessions.
- S0034 processed 1,583,358 TCB1 records across two files with zero truncated
  bytes and 67 CAN-ID/direction pairs.
- S0034 diagnostic normalization preserved 3,166 `OK` rows and reclassified 43
  v2.3 `UNEXPECTED_RESPONSE` rows as
  `LEGACY_POSSIBLE_EXTERNAL_DIAGNOSTIC_TRAFFIC`; this is a cautious label, not
  proof of the source of each reply.
- All Android Java source files passed a Java syntax parser, and all Android
  manifest/layout/resource XML files parsed successfully.
- Firmware braces and parentheses are balanced and the v2.3 TCB1 record layout
  remains protected by its 24-byte static assertion.

## Required on-device validation

The current environment did not contain ESP32 Arduino core 3.3.10, TFT_eSPI, or
Android SDK 35, so it could not produce a board-compiled binary or APK. Before
vehicle use:

1. Compile/upload the firmware in the stated Arduino IDE environment.
2. Bench-test with VP230 CAN-H/CAN-L disconnected: display, touch, SD start/stop,
   BLE connection, clock samples, and session files.
3. Verify LISTEN-ONLY operation on a stationary vehicle and confirm TX remains
   zero while an external diagnostic app is active.
4. Build/install the Android debug APK and run a short screen/microphone capture
   on each Samsung model.
5. Process the new paired session and confirm matching `SYNC.CSV` sequences,
   reasonable drift, low fit residuals, and an aligned narration marker.

Rollback is the included v2.3.0 firmware ZIP.
