# Evidence Builder 1.0.2 validation

## Automated tests

- 18 unit/integration tests pass under Python 3.12-compatible code.
- Tests cover TCB1 parsing and truncated tails, logger manifest version
  compatibility, BLE alignment, S0010 `21CE` ISO-TP reconstruction, the
  exact 17-block vector, graph geometry, orientation handling, Dr. Prius
  reconstruction, diagnostic-action grouping, dependency checks, and the
  existing processor behavior.
- Python bytecode compilation (`compileall`) is clean.

## Supplied S0012 2007 Camry Hybrid capture

- Logger: CYD v2.4.2, capture format 1.4, TWAI listen-only, GPIO25 TX/GPIO32 RX.
- 737,093 raw records processed; zero session CAN transmissions and zero SD
  log drops. The logger reported 1,466 CAN queue drops; that counter remains
  visible in the session summary rather than being silently discarded.
- 2,943 external diagnostic transactions reconstructed: 2,541 OK, 382 no
  response, 17 incomplete, and 3 unmatched responses.
- 351 complete `7E2 / 21CE` 17-block samples decoded; the AHV40 definition
  remains `PROBABLE` pending an independent repeated capture or
  AP200/Techstream corroboration.
- BLE alignment used 127 of 135 samples: -11.728 ppm drift, 6.561 ms RMS
  residual, and 20.975 ms maximum residual. The residual warning is retained
  in `TIME_ALIGNMENT.json` and the session summary.

## Orientation-aware graph and diagnostic evidence

- 273 video frames were sampled at two-second intervals with per-frame
  orientation/layout detection; no fixed rotation timestamp is assumed.
- 70 Hybrid Assistant graph frames and 18 Dr. Prius Battery Monitor landscape
  frames were extracted. All 88 graph rows matched an aligned CAN sample.
- Dr. Prius rows preserve 17 ordered block values, printed pack voltage,
  current direction/current, three battery temperatures, SOC, reconstruction
  count, block RMSE, and source frame. The 330 s frame reconstructed two
  labels; its 17-value sum matched the displayed 277.43 V pack within the
  recorded rounded values. All rows are marked `PROBABLE`, not `CONFIRMED`.
- Four grouped diagnostic actions were aligned to the video: two read-code
  operations returned `53 00` (`NO_DTC_PRESENT`) and two clear operations
  returned `44` (`ACKNOWLEDGED`). They are passive observations only;
  clear-code definitions remain `CONTROL_WRITE_QUARANTINED` and are never
  enabled for automatic transmit.

## Evidence grade

## Dependency and platform notes

- Windows installation now checks/repairs the app-local `.venv`, including
  `faster-whisper==1.2.0` and `requests`, and resolves FFmpeg/Tesseract from
  PATH or standard install locations. OCR subprocess windows are hidden.
- Android source includes the operator confirmation prompt before a synced
  capture and targets compile/target SDK 35 with min SDK 26. Android Studio
  build/install was previously validated on the supplied phones; it was not
  rebuilt in this Linux validation environment.
