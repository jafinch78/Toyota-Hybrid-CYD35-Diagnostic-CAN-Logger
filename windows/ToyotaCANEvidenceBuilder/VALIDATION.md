# Evidence Builder 1.0.4 validation

## Corrective-action verification

- The legacy reusable-nearest-neighbor result is retained only as a post2
  control. Version 1.0.4 uses a disclosed per-field fixed-lag grid and
  one-to-one CAN/OCR assignment.
- Regrading the unchanged S0069 v0.5.9 outputs produced 817 one-to-one pairs
  from 209 unique OCR frames and 717 within-tolerance agreements. MG2 RPM
  reproduced 87 pairs/86 agreements across 184 seconds and 1,721 rpm dynamic
  range and was the only S0069 row to pass every strengthened local gate.
- MG2 torque produced 85 pairs/83 agreements but remained `PROBABLE` because
  RMSE exceeded half its field tolerance. This demonstrates that agreement
  count alone cannot create `CONFIRMATION_READY`.
- A synthetic S0062 pump-speed regression has 30/30 tolerance agreements but a
  100 rpm RMSE; it is blocked from `CONFIRMATION_READY`.
- Blank or unit-unsafe OCR observations are exported separately and cannot be
  used as pairs. Every grade includes an explicit decision reason.
- App detection identifies Hybrid Assistant evidence ahead of a conflicting
  requested Dr. Prius profile, covering the S0060 routing cause.
- Exact duplicate archives are collapsed by SHA-256. Multiple distinct CANLOG
  archives containing the same BLE session produce an unprocessed `AMBIGUOUS`
  record with all candidates.
- Synthetic camera frames with four long yellow guides crop to the enclosed
  evidence region; normal landscape-band behavior remains covered.
- Counter reconciliation compares parsed raw records with the logger processed
  count while reporting session and since-boot receive counts separately.
- Review proxies require a five-timestamp original/proxy Tesseract comparison.
  A proxy that cannot be tested or does not meet recall gates is not used for OCR.

## Database compatibility patch

- Database v0.5.5/schema 1.0.0 loaded with 44 definitions and SHA-256
  `6833c8ccddab9294c1fa07caadb0e49649a38fed997289881726e59be0471869`.
  The original v1.0.3-bundled v0.5.5 snapshot (also 44 definitions), SHA-256
  `17be1867055aaecd6b7791eaf74bb5ac17c5d68d5098528a10a834a3caa06114`,
  was independently loaded successfully as an external database as well.
- Database v0.5.6/schema 1.1.0 loaded with 44 definitions, including two
  `FIELD_SPECIFIC` definitions, and SHA-256
  `afcd6f0c1c0e78675552a77a4686ae23339547bdc7c890df3a758c0e39c37b9a`.
- Database v0.5.7/schema 1.1.1 loaded with 44 definitions, including two
  `FIELD_SPECIFIC` definitions, and SHA-256
  `a936dfa0dd2149b0c452cbc520a96b314966e0eabea15ecf45768a96012ff6b1`.
- Database v0.5.8/schema 1.2.0 loaded with 44 definitions, including two
  `FIELD_SPECIFIC` definitions, and SHA-256
  `a6d8b35877d56c6204b162f33147c054e8dd2311479c2a2bc35c3d8926c03604`.
- Database v0.5.9/schema 1.2.0 loaded with 44 definitions, six new S0069-backed
  AHV40 `21C3` field members, and SHA-256
  `28c0ac47db211cde9ef318ef55bb3bf9bc0cc4017b06227753d1cf18ed12a979`.
- The v0.5.9 candidate registry contains 267 session observations, 243 unique
  response shapes, and 238 unique request tuples. Tests confirm it is excluded
  from decoder lookup; unsafe active-polling or automatic-promotion settings are
  rejected.
- Each requested database release completed a minimal end-to-end processing
  fixture with its version, schema, path, hash, and unchanged-after-processing
  result recorded in the session summary and HTML report.

## Automated regression

- 37 unit/integration tests pass under the available Python environment.
- Tests cover TCB1 parsing/truncated tails, capture compatibility, BLE affine
  alignment, ISO-TP reconstruction, read-only safety handling, graph OCR,
  generic v0.5.5 decoding, authoritative profile correction, indexed AP200 OCR
  parsing, and BLE-session batch pairing.
- Database compatibility tests cover v0.5.5 through v0.5.9, field-level grade
  propagation, candidate-registry isolation, and database immutability.
- Python bytecode compilation is clean.

## S0069 2007 Camry Hybrid regression

- Immutable CANLOG SHA-256:
  `616607769c68ecae13a6178b739111b5424a85239669dde7d66ed5bf271cd805`.
- Immutable compact CAPTURE SHA-256:
  `844f1f2023d1f063d4a68f0a3abf5d30758f60fe0a1dba4230c064b12d381c2d`.
- The v0.5.8 control produced 3,709 decoded field rows and zero label-based
  CAN/OCR rows. With identical inputs, v0.5.9 produced 5,491 decoded field rows
  and 919 legacy nearest-neighbor correlation rows.
- An independent fixed-lag, one-to-one audit of 297 successful `7E2/21C3`
  responses confirmed MG2 RPM/torque, MG1 RPM, and Autel Engine spd across
  nontrivial time spans and dynamic ranges. MG1 torque execution and the
  separately labeled Engine revolution channel remain PROBABLE.
- The difference between the Builder's 919 rows and the independent non-reuse
  counts is the explicit v1.0.4 one-to-one matching regression target. The
  Builder's current `CONFIRMATION_READY` result is not accepted as promotion
  evidence.

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
- Historical v1.0.3 regrading against the previously generated full-resolution AP200 OCR yielded
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
  smoke-tested on Windows 10 1607 before publishing an executable installer.
- `--check-install` completed in the audit environment and correctly reported
  that the interpreter is not the package's Windows `.venv`. Optional
  `faster-whisper` and `requests` imports are absent here; narration was not
  required for this database compatibility patch and was not claimed as
  validated.
