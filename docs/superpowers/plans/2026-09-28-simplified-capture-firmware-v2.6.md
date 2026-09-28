# Simplified Capture Firmware v2.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:test-driven-development` for each code change and `superpowers:verification-before-completion` before every checkpoint claim. Execute on **only** `feature/logger-simplified-capture-v2.6` unless this plan explicitly says otherwise.

**Goal:** Replace the RC2 firmware's six persistent session streams and repeated JSON/CSV work with the validated native `TCB1 RAW + TVM1 SESSION.META` contract, while preserving read-only diagnostic safety, BLE synchronization, Wi-Fi maintenance, live display usefulness, and exact CAN evidence fidelity.

**Starting firmware:** `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0.ino`, v2.5.0-rc.2, blob `bbc7421da2bfc684324123b3232895cdcfd6c23d`, on `feature/logger-simplified-capture-v2.6`.

**Normative contracts:**

- `docs/superpowers/specs/2026-09-28-tvm1-firmware-contract-amendment.md`
- validated `docs/TVM1_SESSION_META_BINARY_SPEC.md` from `feature/native-session-preprocessor-impl`
- validated `docs/TOYOTA_VEHICLE_BUS_CAPTURE_CONTRACT.md` from `feature/native-session-preprocessor-impl`
- `docs/superpowers/specs/2026-09-27-simplified-capture-logger-design.md`, except where superseded by the TVM1 amendment

**Offline prerequisite:** CLOSED. `feature/native-session-preprocessor-impl` records S0141/S0149/S0128 Builder compatibility PASS plus Windows 10 build 14393 runtime PASS. Firmware file removal is authorized. Analyzer is not a firmware-authorization input.

**Supported boards:** `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`. E32N35T is not an active v2.6 target.

**Toolchain:** ESP32 Arduino core **3.3.10**, TFT_eSPI, SD/SPI, BLE, TWAI. Retain `ESP32 Dev Module` + `Huge APP (3MB No OTA/1MB SPIFFS)` release configuration unless a compile measurement proves a change is necessary.

---

## Checkpoint discipline

Every task below ends with all of the following before proceeding:

1. run the task's focused RED/GREEN test cycle;
2. run the cumulative firmware host/source test suite;
3. update `docs/superpowers/plans/2026-09-28-simplified-capture-firmware-v2.6-progress.md` with exact tests, results, unresolved risks, and current commit;
4. make one atomic Git commit;
5. read back the committed files/branch tip before calling the task complete.

Do not batch multiple unverified tasks into one commit. Do not force-update this branch if it moves concurrently; reconcile first.

---

### Task 1: Freeze the v2.6 implementation baseline and board/contract invariants

**Files:**

- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/`
- Copy from RC2 as starting point:
  - `Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino`
  - `TFT_eSPI_User_Setup_CYD35.h`
  - `README.md`
  - `VERSION.txt`
- Create: `firmware/tests/test_v2_6_0_source.py`
- Create: `docs/superpowers/plans/2026-09-28-simplified-capture-firmware-v2.6-progress.md`

**Required invariants:**

- firmware development identity begins as `2.6.0-dev` until physical board validation;
- `CapturedFrame` remains packed 24 bytes;
- CAN pins remain GPIO25 TX / GPIO32 RX;
- CAN remains 500 kbit/s;
- `RAW_ROTATE_BYTES` remains 25 MiB initially;
- CAN application queue remains 1024 records;
- TFT configured for validated 80 MHz writes;
- diagnostic request table remains services `0x01` and `0x21` only;
- no arbitrary CAN transmit API, file upload, firmware update, CAN control/write service, or SD format path is introduced;
- active board profiles are exactly `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`.

- [ ] **Step 1: Write RED source-contract tests.** Require v2.6 identity, new board-profile names, TVM1 constants (`"TVM1"`, `0xA55A`, major 1/minor 0, 32-byte header), and absence of the old `TCM1` draft magic.
- [ ] **Step 2: Require no E32N35T active profile in v2.6.** Historical files may retain it; the new sketch may not.
- [ ] **Step 3: Create v2.6 source from the exact RC2 implementation and make only identity/profile scaffolding changes.** Do not remove logging products yet.
- [ ] **Step 4: Run:**

```bat
py -3 -m unittest firmware.tests.test_v2_5_0_source firmware.tests.test_v2_6_0_source -v
```

- [ ] **Step 5: Checkpoint commit:**

```text
feat: scaffold v2.6 simplified capture firmware
```

---

### Task 2: Implement a byte-exact TVM1 encoder before changing session lifecycle

**Files:**

- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TVM1Meta.h`
- Create: `firmware/tests/test_tvm1_firmware_contract.py`
- Modify: v2.6 sketch only to include the new encoder

**Design:** Keep the encoding layer small and deterministic. The encoder writes little-endian integers into caller-provided fixed buffers, computes CRC-32/ISO-HDLC using polynomial `0xEDB88320`, and has no dynamic allocation. SD `File` ownership remains in the sketch/session layer.

Required helpers:

```text
writeLe16 / writeLe32 / writeLe64
crc32Update
encodeTvm1Header(...)
encodeTvm1RecordEnvelope(...)
appendTvm1String(...)
```

The code must support the exact validated 32-byte TVM1 header and 24+N record envelope. Maximum emitted v1 record length is 4096 bytes.

- [ ] **Step 1: RED tests pin all constants, offsets and payload sizes against the validated Python preprocessor contract.**
- [ ] **Step 2: Add golden vectors for one header and at least SESSION_START, STREAM_REGISTER, STREAM_COUNTERS and SESSION_CLOSE.** Golden bytes must be independently constructed in Python, not generated by the firmware helper under test.
- [ ] **Step 3: Implement the smallest fixed-buffer encoder that satisfies those vectors.**
- [ ] **Step 4: Keep CRC code shared with the existing Wi-Fi ZIP path only if byte behavior remains identical; otherwise isolate TVM1 CRC to prevent accidental ZIP regression.**
- [ ] **Step 5: Run cumulative tests.**
- [ ] **Step 6: Checkpoint commit:**

```text
feat: add canonical TVM1 metadata encoder
```

---

### Task 3: Replace six live SD streams with RAW + META only

**Files:**

- Modify: v2.6 sketch
- Modify: `firmware/tests/test_v2_6_0_source.py`
- Add focused lifecycle assertions to `firmware/tests/test_tvm1_firmware_contract.py`

**Current RC2 debt being removed:** `rawFile`, `decodedFile`, `diagnosticFile`, `eventFile`, `syncFile`, `externalDiagnosticFile`, plus MANIFEST/CHECKPOINT/README/SIGNALS generation and repeated flushes.

**Target open files while logging:**

```text
rawFile
metaFile
```

`SD_MAX_OPEN_FILES=5` becomes the first bench candidate. Do not lower it further without a real reason.

**Start sequence:**

1. reserve monotonic S####;
2. create directory;
3. open `RAW_000.TCB`, write unchanged TCB1 header;
4. open `SESSION.META`;
5. write TVM1 file header;
6. append SESSION_START;
7. append CAN STREAM_REGISTER for stream 1;
8. append STREAM_START;
9. append STREAM_FILE_OPEN for `RAW_000.TCB`;
10. mark logging active.

There is **no native SESSION.OPEN file**.

**Clean close sequence:** append final counters/health, STREAM_FILE_CLOSE, STREAM_STOP, SESSION_CLOSE(clean=1), durability-flush RAW/META, close both files.

- [ ] **Step 1: RED tests require that v2.6 does not declare/open/write `decodedFile`, `diagnosticFile`, `eventFile`, `syncFile`, or `externalDiagnosticFile`.**
- [ ] **Step 2: RED tests require no normal-session writes of `DECODED.CSV`, `DIAGNOSTICS.CSV`, `EXTERNAL_DIAGNOSTICS.CSV`, `EVENTS.CSV`, `SYNC.CSV`, `SIGNALS.CSV`, `README.TXT`, `MANIFEST.JSON`, `CHECKPOINT.JSON`, `PLOT.CSV`, or `SESSION.OPEN`.**
- [ ] **Step 3: Implement `metaFile`, metadata sequence state and append helpers.** A failed META append increments storage error counters and emits a Serial error; never pretend metadata persisted.
- [ ] **Step 4: Rewrite `startLogging`, `closeSessionFiles`, `cleanupFailedSession`, `stopLogging` around RAW+META only.**
- [ ] **Step 5: Retain session allocator/NVS/SD directory policy unchanged.**
- [ ] **Step 6: Cumulative tests + checkpoint:**

```text
feat: reduce capture session to RAW and TVM1 metadata
```

---

### Task 4: Make RAW commit the main-loop priority and measure it

**Files:**

- Modify: v2.6 sketch
- Modify: v2.6 source tests

**Current RC2 order:** BLE service → diagnostic queue → drain CAN batch → `processCapturedFrame()` → `writeRawBatch()`.

**Required v2.6 order:**

```text
critical flags / pending command state
CAN batch drain (up to 128)
RAW batch commit
process same in-RAM batch for fingerprint/live decoding
诊ostic reassembly
META service
scheduler / TWAI health
touch
TFT if allowed
RAW/META durability flush if allowed
```

Keep the local batch at 128 records. Do not increase to 256 because that materially raises loop-stack pressure.

Instrumentation added now:

- queue current depth and session high-water;
- raw write count;
- raw write total microseconds;
- raw write maximum microseconds;
- short-write count;
- persisted record count distinct from received count/drop count;
- main-loop maximum latency.

- [ ] **Step 1: RED source-order test asserts `writeRawBatch(batch,count)` occurs before `processCapturedFrame(batch[i])` in `loop()`.**
- [ ] **Step 2: RED tests pin batch size at 128 and queue length at 1024.**
- [ ] **Step 3: Instrument `writeRawBatch()` with `esp_timer_get_time()` without per-frame logging/formatting.**
- [ ] **Step 4: `rawSequence` must count successfully persisted complete records, not requested bytes when an SD short write occurs. Keep separate attempted/received counters if useful.**
- [ ] **Step 5: Rotation still occurs at 25 MiB, but rotation emits STREAM_FILE_CLOSE then opens the next TCB1 file and emits STREAM_FILE_OPEN.**
- [ ] **Step 6: Cumulative tests + checkpoint:**

```text
perf: commit RAW before derived capture work
```

---

### Task 5: Fix BLE start/stop boundaries and move sync/markers to META

**Files:**

- Modify: v2.6 sketch
- Add/modify source-contract tests

**Problem:** RC2 services BLE before draining the CAN application queue and a STOP command directly calls `stopLogging(true)`, so already-received frames can remain queued when files close.

**New state:**

```text
startPending / startRequestUs / startCommandSequence
stopPending / stopRequestUs / stopCommandSequence
```

**STOP rule:** BLE STOP only sets pending state. The loop drains and RAW-commits all frames already received for the current boundary, appends EVENT/stop metadata, finalizes counters, writes SESSION_CLOSE, then closes. Record both requested stop time and final persisted RAW time via the defined EVENT/record arguments rather than inventing a new incompatible TVM1 envelope.

**START rule:** record accepted start request and guarantee queued pre-start residue is not silently attributed to the new session. Prefer draining/discarding stale pre-start queue entries before opening the new session, with explicit count/event if any are discarded.

BLE sync records become TVM1 CLOCK_SYNC; markers become USER_MARKER plus the corresponding EVENT where useful. No SYNC/EVENT CSV is written on-device.

- [ ] **Step 1: RED tests forbid `stopLogging(true)` directly inside BLE opcode 2 handling.**
- [ ] **Step 2: RED tests require pending-stop fields and finalization in the main loop after CAN drain/RAW commit.**
- [ ] **Step 3: Convert pending prestart BLE sync samples to CLOCK_SYNC records after session start.**
- [ ] **Step 4: Keep 20-byte BLE protocol/replies compatible; no CAN-control BLE command is added.**
- [ ] **Step 5: Cumulative tests + checkpoint:**

```text
fix: drain capture before synchronized session close
```

---

### Task 6: Preserve diagnostic safety while removing diagnostic CSV work

**Files:**

- Modify: v2.6 sketch
- Modify source safety tests

**Must remain in firmware:** read-only request scheduler, ISO-TP reassembly needed for live values, immediate first-frame flow control, fixed request whitelist, profile gate, external-tester collision interlock.

**Must disappear from SD hot path:** formatted `DIAGNOSTICS.CSV` and `EXTERNAL_DIAGNOSTICS.CSV`.

- [ ] **Step 1: Keep high-priority CAN RX behavior that timestamps external requests and updates `externalTesterLastUs` before queue processing.**
- [ ] **Step 2: Add the same recent-external-tester hard refusal directly to both `serviceDiagnosticScheduler()` and `transmitCAN()`.** This is required even if diagnostic enable state is stale.
- [ ] **Step 3: Keep immediate ISO-TP FC in the CAN RX task; do not move FC transmission back behind SD/TFT work.**
- [ ] **Step 4: Requests, FC TX, and any other logger-originated diagnostic frames remain queued into TCB1 with `direction=1`.**
- [ ] **Step 5: Replace internal-only CSV status persistence with compact DIAGNOSTIC_STATE/EVENT records for enable, disable, timeout, negative response, incomplete/reassembly error, external tester interlock, user disabled and bus-off.**
- [ ] **Step 6: Remove `writeDiagnosticRecord()` and `writeExternalDiagnosticFrame()` filesystem formatting; external traffic itself remains reconstructible from RAW.**
- [ ] **Step 7: Safety tests continue to assert diagnostic service set `{0x01,0x21}` and absence of 0x2E/control paths.**
- [ ] **Step 8: Cumulative tests + checkpoint:**

```text
refactor: move diagnostic evidence persistence to RAW and META
```

---

### Task 7: Emit health, storage and TWAI state as compact TVM1 records

**Files:**

- Modify: v2.6 sketch
- Modify TVM1 contract tests

Use the validated TVM1 metric IDs, not ad-hoc strings.

At five-second default cadence, after RAW service and only when queue pressure permits, append:

- STREAM_COUNTERS;
- HEALTH_SNAPSHOT;
- STORAGE_HEALTH.

Track at minimum:

- CAN queue current depth/high-water;
- CAN queue drops;
- diagnostic queue drops;
- TWAI RX missed/overrun/bus-error/bus-off;
- raw persisted count;
- raw write avg/max;
- RAW/META flush count/max latency;
- main-loop max latency;
- TFT render count/max latency;
- free/largest/minimum heap;
- CAN RX task stack high-water;
- loop task stack high-water where available;
- SD short writes/storage dropped records;
- current raw file index.

Map bus-off/recovery/mode transitions to BUS_STATE and important storage faults to EVENT/STORAGE_HEALTH.

- [ ] **Step 1: RED tests require defined TVM1 metric IDs and five-second default cadence.**
- [ ] **Step 2: Implement aggregate counters in RAM; no instrumentation CSV.**
- [ ] **Step 3: Queue pressure can defer periodic health metadata but not RAW persistence or required close records.**
- [ ] **Step 4: Cumulative tests + checkpoint:**

```text
feat: add compact capture health telemetry
```

---

### Task 8: Replace full logger-page repaint with 80 MHz dirty fields

**Files:**

- Modify: v2.6 sketch
- Modify source tests

**Current expensive behavior:** `updateDisplay()` clears `fillRect(2,2,476,241,TFT_BLACK)` every ~250 ms and reconstructs many `String` values.

**Target:**

- full page/static labels only on page entry;
- each dynamic value has a fixed rectangle and cached last-rendered text/state;
- redraw a field only when its rendered value/state changes;
- fixed `char[]` + `snprintf` in logger hot path;
- buttons redraw only when state/text/color changes;
- defer normal logger TFT work under queue pressure;
- Wi-Fi maintenance screen may retain full-screen/large-area refresh because CAN/TWAI logging is off;
- no full-screen RGB565 sprite.

- [ ] **Step 1: RED test forbids the 476x241 normal logger clear inside periodic `updateDisplay()`.**
- [ ] **Step 2: RED tests pin 80 MHz TFT configuration and reject a full-screen 307,200-byte framebuffer allocation.**
- [ ] **Step 3: Build static page renderers + dirty dynamic-field renderers.**
- [ ] **Step 4: Add TFT render timing counters used by HEALTH_SNAPSHOT.**
- [ ] **Step 5: Preserve page switch/touch behavior; a page change intentionally performs one full redraw.**
- [ ] **Step 6: Cumulative tests + checkpoint:**

```text
perf: use dirty-field logger display updates
```

---

### Task 9: Make Wi-Fi maintenance understand native TVM1 sessions without weakening legacy safety

**Files:**

- Modify: v2.6 sketch
- Modify Wi-Fi/source tests

Current RC2 uses `SESSION.OPEN` to mark an unclean session and block deletion. v2.6 native sessions have no marker.

Implement a small maintenance-mode TVM1 status reader that determines whether a native session contains a valid clean SESSION_CLOSE. It runs only when logging/TWAI/BLE are already stopped.

Rules:

- legacy session + `SESSION.OPEN` => unclean;
- native session + valid clean SESSION_CLOSE => closed;
- native session without valid clean close => unclean;
- unknown/unreadable session state => fail closed and prohibit deletion.

Update browser wording so a reduced TVM1 capture is not represented as already-expanded Builder input. Keep download endpoints compatible where practical, but label native ZIPs clearly as requiring the offline preprocessor before Evidence Builder 1.0.4.

- [ ] **Step 1: RED tests cover legacy marker and native META close detection.**
- [ ] **Step 2: Preserve exclusive Wi-Fi order: logging closed → CAN RX task/TWAI stopped → queues released → BLE deinit → Wi-Fi allocated.**
- [ ] **Step 3: ZIP code must tolerate sessions containing only META + one/more RAW files.**
- [ ] **Step 4: deletion of unclean/unknown state remains blocked.**
- [ ] **Step 5: node/static HTTP tests remain green.**
- [ ] **Step 6: Cumulative tests + checkpoint:**

```text
feat: support native TVM1 sessions in Wi-Fi maintenance
```

---

### Task 10: Finalize E32R35T and Dorhea profile separation

**Files:**

- Modify: v2.6 sketch
- Modify: `TFT_eSPI_User_Setup_CYD35.h` if board-selected settings require it
- Modify board-profile source tests
- Update v2.6 README

Requirements:

- compile-time profile values are `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`;
- E32R35T touch uses XPT2046 CS=33, IRQ=36, landscape rotation 1 and its verified calibration;
- Dorhea retains its physically tested `{295,3524,310,3487,3}` calibration unless new bench evidence requires correction;
- manufacturer E32R35T/LCDWiki and known-working HaleHound 3.5-inch examples are the reference for E32R35T pin/controller setup;
- never repurpose GPIO35 as an output; it remains available as a future BTH receive input;
- do not add BTH or AVC-LAN active acquisition in this task—only preserve the bus-neutral TVM1 architecture and pin headroom.

- [ ] **Step 1: Source test rejects old E32N35T profile text in the v2.6 active configuration.**
- [ ] **Step 2: Insert only documented/verified E32R35T configuration; do not guess calibration.**
- [ ] **Step 3: Build both board profiles from one source with explicit compile-time selection.**
- [ ] **Step 4: Cumulative tests + checkpoint:**

```text
feat: finalize E32R35T and Dorhea logger profiles
```

---

### Task 11: Host/build verification and offline-preprocessor contract round trip

**Files:**

- Modify/add test/build scripts only as necessary
- Update progress ledger with exact tool versions and outputs

- [ ] **Step 1: Run full Python/source tests:**

```bat
py -3 -m unittest discover -s firmware\tests -v
```

- [ ] **Step 2: Run existing host C++17/Arduino-stub syntax validation used by RC2.** If that harness is not reproducibly present, restore/document it before claiming host compile coverage.
- [ ] **Step 3: Run `node --check` on embedded Wi-Fi JavaScript extraction as used by RC2 validation.**
- [ ] **Step 4: Arduino compile with ESP32 core 3.3.10 for both E32R35T and Dorhea builds using `ESP32 Dev Module` / Huge APP. Record program and global-memory usage.**
- [ ] **Step 5: Build a deterministic synthetic v2.6 native session using the exact firmware TVM1 golden vectors + TCB1 fixture; feed it through the validated `ToyotaVehicleBusSessionPreprocessor`.** Require successful legacy expansion and exact RAW equality.
- [ ] **Step 6: Feed the expanded compatibility package into Evidence Builder 1.0.4 with the pertinent RC7 CanonicalDB v1.0.1 runtime patch available. Require Builder acceptance; no Analyzer gate is needed.**
- [ ] **Step 7: Checkpoint commit:**

```text
test: verify v2.6 native capture contract
```

---

### Task 12: Physical bench validation — both CYD targets

**Evidence output:**

- Create: `docs/releases/v2.6.0/VALIDATION_AND_TEST.md`
- Create per-board validation logs/hashes as appropriate

Perform on **both** E32R35T and Dorhea before an RC label.

Required bench sequence:

1. boot with SD absent: one clean startup, BLE/TWAI LISTEN_ONLY stable;
2. boot with known SD: no reboot loop / no BLE allocation regression;
3. verify only RAW + SESSION.META are created in a native session;
4. verify start/stop twice and monotonic S#### allocation;
5. verify clean SESSION_CLOSE and absence of native SESSION.OPEN;
6. force/observe an unclean reset and verify missing SESSION_CLOSE is recognized offline as unclean;
7. verify BLE sync and marker records expand to legacy SYNC/EVENTS;
8. verify BLE STOP drains queued RAW before close;
9. verify touch matrix and both display pages;
10. verify dirty updates at 80 MHz without corruption;
11. enter/exit Wi-Fi maintenance, list native session, download native ZIP, verify hashes;
12. verify unclean native session cannot be deleted;
13. test a controlled small-threshold rotation build or sufficiently long capture to exercise RAW_001.TCB; verify STREAM_FILE_CLOSE/OPEN and offline logical-stream equality;
14. record queue high-water, raw write max, flush max, loop max, TFT max, heap minima and task stack margins.

After each board capture, run the downloaded native session through the validated offline preprocessor and Builder. The expanded RAW files must remain byte-identical to the native source.

- [ ] **Checkpoint only after both boards pass:**

```text
test: bench validate simplified capture on E32R35T and Dorhea
```

---

### Task 13: Stationary vehicle regression and RC packaging

Do not start with active diagnostics.

1. stationary vehicle, diagnostics OFF, passive CAN only;
2. BLE synchronized start/markers/stop;
3. inspect firmware health counters for zero queue/raw drops;
4. preprocess native session offline;
5. run Evidence Builder 1.0.4 and confirm normal processing;
6. separately test the existing Prius Gen 2 read-only diagnostic mode only after passive test passes;
7. confirm logger TX request/FC frames appear in RAW with `direction=1` and external-tester interlock still blocks collision;
8. leave Camry/unresolved profiles passive-only;
9. package as `2.6.0-rc.1` only after all above evidence is retained.

Create release ZIP/SHA256 and update `VERSION.txt`, README, changelog and validation documentation only after verification-before-completion has been run against the final files.

**Final checkpoint:**

```text
release: package simplified capture logger v2.6.0-rc.1
```

---

## Explicit deferrals after v2.6 CAN capture

These are separate follow-on plans and must not expand this implementation while stabilizing CAN capture:

- BTH receive-only stream implementation using SN75HVD12DR/GPIO35 after hardware arrival and live baud/framing validation;
- AVC-LAN edge/pulse acquisition and native raw format;
- standalone richer PLOT/derived-products generator beyond the already validated legacy compatibility expander;
- changing the 25 MiB raw rotation threshold;
- SD clock increase from 4 MHz to 10/20 MHz unless instrumentation demonstrates a reliability/latency benefit;
- CAN queue enlargement beyond 1024 records.
