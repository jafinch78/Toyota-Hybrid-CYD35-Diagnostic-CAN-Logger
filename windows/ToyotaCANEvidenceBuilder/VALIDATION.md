# Evidence Builder 1.0.3 validation

## Automated regression

- 24 unit/integration tests pass under Python 3.12-compatible code.
- Tests cover TCB1 parsing/truncated tails, capture compatibility, BLE affine
  alignment, ISO-TP reconstruction, read-only safety handling, graph OCR,
  generic v0.5.5 decoding, authoritative profile correction, indexed AP200 OCR
  parsing, and BLE-session batch pairing.
- Database v0.5.5 validation passes with 44 definitions, five profiles, seven
  profile signatures, six new definitions, and two explicitly quarantined
  clear-code observations.
- Python bytecode compilation is clean.

## S0018 2014 Prius PHV Gen 1 regression

- Immutable source: `CANLOG_083126_130240.zip`, SHA-256
  `d7f85f1c9d56753eba9ac38ba48e763be68962e2afd03ec96bbb2253209297f6`.
- Companion derivative: `CAPTURE_20260831_130240_rsz.zip`, SHA-256
  `2d4c38a21345b7e07dcf82be04d1b8aa7b3d951eea51f9110af5352f6a831436`.
- 1,195,423 raw TCB1 records; zero truncated-tail bytes, session transmissions,
  CAN/diagnostic queue drops, SD log drops, and bus-off events.
- 215 BLE synchronization samples; fitted alignment RMS 5.498 ms.
- 1,870 external diagnostic transactions reconstructed; 1,554 completed OK.
- Confirmed `7E0/21C1` ASCII `ZVW35 2ZRFXE` identity selected
  `PRIUS_PHV_GEN1` at 100% database-evidence confidence and overrode the
  incorrect `CAMRY_HYBRID_GEN1` logger manifest. The conflict remains visible
  in `PROFILE_EVIDENCE.json` and `REPORT.html`.
- Standard `09/02` VIN is decoded but masked by default as
  `JTDKN3DP4E3******`.
- The generic decoder exported 4,388 field/array rows, 79 eight-block rows, and
  12 eight-resistance rows with zero bounds or expected-value failures.
- Regrading against the previously generated full-resolution AP200 OCR yielded
  837 CAN/OCR pairs and 798 within-tolerance agreements. Forty-nine field/index
  rows met the local `CONFIRMATION_READY` rule; this advisory grade does not
  alter the database.
- All eight aggregate block indexes had at least 88% agreement; index 1 RMSE
  was 0.022 V and index 8 RMSE was 0.027 V. All matched resistance rows were
  exact at 0.007 ohm.
- Repeated CAN/OCR evidence showed AP200's generic `Motor temp no1/no2` labels
  cross-map to the MG2/MG1 semantic PID keys. Database v0.5.5 records that
  observed crosswalk explicitly rather than renaming Toyota semantic keys.

## Batch, report, and compact-media checks

- Batch discovery ignored the processed Evidence ZIP and paired the source
  CANLOG/CAPTURE archives solely from successful BLE `START_PASSIVE` session
  18. The batch produced one pair and an aggregate grading table.
- The self-contained report opens without network dependencies and contains
  the corrected-profile warning, decoded timeline, battery-block review,
  grading table, events/actions, narration, and OCR-keyframe index when present.
- The evidence capsule passes ZIP CRC validation and excludes raw source video,
  raw TCB1 traffic, and unmasked VIN data.
- The supplied resized video was recognized as already compact: H.264,
  720x1568, 10 fps. No second proxy was created. The derivative report warns
  that its unchanged `CAPTURE_SYNC.json` describes the original 1072x2336
  recording; future direct compact captures should write current media
  properties or a derivative manifest.

## Safety and evidence boundary

- Evidence Builder processes only frames already present in the supplied
  archives. It does not transmit diagnostic requests or enable clear-code,
  reset, actuator, or other control/write commands.
- Local `CANDIDATE`, `PROBABLE`, `CONFIRMATION_READY`, and `REJECTED` grades are
  review aids. Only a reviewed versioned database release can assign or promote
  a definition to `CONFIRMED`.
- AP200 is treated as a list/table OCR source; zero battery-graph rows is an
  expected layout result, not a capture failure.
- Database v0.5.5 retains eight seven-cell PHV aggregate blocks. It does not
  infer or export 56 individual cell voltages.

## Platform note

- Source processing and release validation were performed in the Linux build
  environment with FFmpeg and Tesseract available. The Windows source package
  and build scripts are included; the PyInstaller `.exe` must be built and
  smoke-tested on Windows before publishing an executable installer.
