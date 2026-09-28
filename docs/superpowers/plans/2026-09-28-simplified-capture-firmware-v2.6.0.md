# Simplified Capture Firmware v2.6.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Toyota Hybrid CYD logger v2.6.0 from the validated v2.5.0-rc.2 baseline with RAW-first TCB1 persistence, canonical TVM1 metadata, reduced SD products, hard diagnostic safety interlocks, and 80 MHz dirty-field TFT updates.

**Architecture:** Preserve the RC2 high-priority CAN RX and exclusive Wi-Fi architecture, but move archival convenience work off the ESP32. Normal capture keeps only RAW + TVM1 `SESSION.META` open, performs contiguous RAW persistence before derived/live work, and records non-reconstructible state as compact TVM1 records. The validated offline preprocessor regenerates Builder-compatible legacy artifacts.

**Tech Stack:** ESP32 Arduino core 3.3.10, C++/Arduino, TFT_eSPI/ST7796/XPT2046, ESP32 TWAI, SD/SPI, BLE, WiFi/WebServer, Preferences, Python `unittest` source/contract tests.

**Spec:** `docs/superpowers/specs/2026-09-28-simplified-capture-firmware-design.md`

## Global Constraints

- Baseline source is exact RC2 blob `bbc7421da2bfc684324123b3232895cdcfd6c23d` from `release/logger-v2.5.0-rc.2-dorhea-touch`.
- Create v2.6.0 separately; do not modify v2.4.2 or overwrite RC2 rollback/reference.
- Supported boards are only `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`; E32N35T is excluded.
- TFT SPI write frequency remains `80000000` Hz.
- TCB1 remains a 16-byte header plus packed 24-byte CAN records; CAN bitrate remains 500000 bit/s and raw rotation remains 25 MiB initially.
- Diagnostic CAN transmissions remain read-only services `0x01` and `0x21`; no control/write/clear/reset/coding API is introduced.
- SD SPI remains 4 MHz initially; application CAN queue stays 1024 and main-loop RAW batch stays 128 until measured evidence justifies changes.
- `SD_MAX_OPEN_FILES=5` is only the first bench-test candidate, not an accepted production value until both boards pass resource/SD/BLE testing.
- Wi-Fi remains an exclusive stopped-logger maintenance mode and exits by restart.
- Canonical TVM1 is defined by `docs/TVM1_SESSION_META_BINARY_SPEC.md`; obsolete TCM1 must never appear in v2.6.0.
- Analyzer RC7/RC8 is not a firmware-authorization input.
- RC2 remains rollback/preferred vehicle firmware until host/static tests, Arduino compilation, and physical E32R35T + Dorhea bench validation pass.

## Review Focus

1. **Power loss during TVM1 append:** complete RAW and prior valid metadata remain usable; partial final metadata is recoverable. Task 2 pins framing; Task 9 exercises unclean recovery.
2. **BLE STOP while CAN queue is nonempty:** STOP is pending and cannot close RAW/META until evidence drains. Task 4 owns this.
3. **External tester appears between receive and scheduler tick:** RX asserts the interlock before scheduler/transmit. Task 5 owns this.
4. **Display/SD latency under CAN load:** UI and noncritical metadata defer rather than sacrificing RAW. Tasks 6-7 own this.
5. **Reduced session set in Wi-Fi ZIP/list/download:** Wi-Fi works with RAW/META/OPEN without legacy CSV/JSON assumptions. Task 8 owns this.

---

### Task 1: Import Exact RC2 Baseline and Pin Safety Invariants

**Files:**
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TFT_eSPI_User_Setup_CYD35.h`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/README.md`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/VERSION.txt`
- Create: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: exact RC2 sketch/setup from the release branch.
- Produces: separate v2.6.0 baseline preserving TCB1, diagnostic whitelist, Wi-Fi exclusivity, allocator, pins, and RC2 behavior.

- [ ] **Step 1:** Write failing tests asserting v2.6 source exists, `sizeof(CapturedFrame)==24`, CAN TX/RX 25/32, diagnostic services exactly `{0x01,0x21}`, TWAI/BLE shutdown precedes Wi-Fi AP, restart-only Wi-Fi exit, monotonic session allocator inputs, E32R35T + Dorhea targets, no E32N35T target, and no write/control services.
- [ ] **Step 2:** Run `python -m unittest firmware.tests.test_v2_6_0_source -v`; expected RED because v2.6 files do not exist.
- [ ] **Step 3:** Copy exact RC2 `.ino`, TFT setup and docs to the v2.6 directory; change only version/target identity needed for `2.6.0-dev`. Preserve 80 MHz TFT and capture behavior.
- [ ] **Step 4:** Re-run focused tests; expected GREEN.
- [ ] **Step 5:** Commit `feat: establish v2.6.0 from validated RC2 baseline`.

---

### Task 2: Add Canonical TVM1 Encoder and Bounded Metadata Queue

**Files:**
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TVM1_Meta.h`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TVM1_Meta.cpp`
- Modify: v2.6.0 `.ino`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`
- Test against: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/meta.py`

**Interfaces:**
- Consumes: canonical TVM1 binary specification and SD `File` object owned by the logger.
- Produces exactly:
  - `class Tvm1Writer` with `bool begin(File &file, uint32_t sessionNumber, uint64_t sessionCreateUs)`, `bool append(uint16_t recordType, uint8_t streamId, uint8_t flags, uint64_t timeUs, const uint8_t *payload, uint16_t payloadLen)`, `bool flush()`, and `uint32_t sequence() const`.
  - firmware helpers `bool enqueueMetaRecord(uint16_t recordType, uint8_t streamId, uint8_t flags, uint64_t timeUs, const uint8_t *payload, uint16_t payloadLen)` and `void serviceMetaQueue()` backed by bounded owned payload storage so callers never enqueue borrowed pointers.

- [ ] **Step 1:** Add failing contract tests for magic `TVM1`, version 1.0, 32-byte header, sync `0xA55A`, minimum 24-byte record, CRC polynomial `0xEDB88320`, stream 0 session scope, stream 1 CAN/TCB1 registration, required record IDs, and absence of `TCM1`.
- [ ] **Step 2:** Run focused tests; expected RED on missing encoder/constants.
- [ ] **Step 3:** Implement explicit byte serialization, CRC-32/ISO-HDLC, length-prefixed provenance strings, typed payload helpers, `Tvm1Writer`, and bounded metadata queue. No compiler-layout dependency and no filesystem work in CAN RX task.
- [ ] **Step 4:** Add a deterministic firmware TVM1 byte-vector test parsed by Python `meta.py`; verify header plus representative SESSION_START, STREAM_REGISTER, counters, EVENT and SESSION_CLOSE values and CRCs.
- [ ] **Step 5:** Run firmware source tests plus `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_meta.py`; expected GREEN.
- [ ] **Step 6:** Commit `feat: add canonical TVM1 firmware metadata writer`.

---

### Task 3: Reduce Normal Capture to RAW + META + OPEN

**Files:** v2.6 `.ino`, `TVM1_Meta.*`, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: Task 2 `Tvm1Writer`, `enqueueMetaRecord()`, `serviceMetaQueue()`.
- Produces: lifecycle with only current RAW and `SESSION.META` persistently open; `SESSION.OPEN` marker only.

- [ ] **Step 1:** Add failing tests proving normal session creation no longer opens/creates `DECODED.CSV`, `DIAGNOSTICS.CSV`, `EXTERNAL_DIAGNOSTICS.CSV`, `EVENTS.CSV`, `SYNC.CSV`, `SIGNALS.CSV`, `README.TXT`, `MANIFEST.JSON`, or `CHECKPOINT.JSON`; RAW rotation must emit TVM1 file-close/open metadata.
- [ ] **Step 2:** Run focused tests; expected RED on legacy file paths.
- [ ] **Step 3:** Remove redundant persistent file globals/open/write/flush paths while retaining in-RAM diagnostics/live signals. Route sync/event/health facts into TVM1.
- [ ] **Step 4:** Clean close writes final counters/state, STREAM_STOP, SESSION_CLOSE, flushes/closes RAW+META, then removes `SESSION.OPEN`; power loss leaves marker and prior evidence intact.
- [ ] **Step 5:** Run `python -m unittest discover -s firmware/tests -v`; expected GREEN.
- [ ] **Step 6:** Commit `feat: reduce v2.6 capture to raw and TVM1`.

---

### Task 4: Make RAW Persistence First and Session Boundaries Loss-Safe

**Files:** v2.6 `.ino`, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: CAN queue length 1024, 128-frame batch, Task 3 lifecycle.
- Produces: `bool stopPending`, stop request timestamp/source/sequence state, and deterministic pre-start residue drain before opening a new session.

- [ ] **Step 1:** Add failing tests asserting `writeRawBatch(batch,count)` precedes batch-derived processing and metadata service; BLE STOP sets `stopPending` instead of directly closing files; close waits for queue drain; START drains pre-start residue before session open.
- [ ] **Step 2:** Run focused test; expected RED on current RC2 ordering/direct STOP.
- [ ] **Step 3:** Reorder loop: flags → drain batch → RAW write → process same batch → diagnostic drain → TVM1 service → diagnostics/TWAI → touch → dirty display → flush → yield.
- [ ] **Step 4:** Implement pending STOP and explicit START boundary, including TVM1 request/final state records.
- [ ] **Step 5:** Run full firmware tests GREEN.
- [ ] **Step 6:** Commit `fix: persist raw before derived work and close safely`.

---

### Task 5: Harden External-Tester Interlock Without Removing Live Diagnostics

**Files:** v2.6 `.ino`, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: RC2 request detector, diagnostic scheduler, fast ISO-TP flow-control path.
- Produces: shared RX-set interlock checked independently by scheduler and `transmitCAN()`; external state recorded in TVM1, not CSV.

- [ ] **Step 1:** Add failing tests asserting RX updates external-tester state before raw-queue handoff; scheduler refuses new logger diagnostics during 5000 ms hold; `transmitCAN()` independently refuses logger diagnostic TX while interlocked; existing owned ISO-TP flow-control remains in RX path and is queued as RAW TX evidence.
- [ ] **Step 2:** Run focused tests; expected RED if transmit-level hard guard is absent.
- [ ] **Step 3:** Implement nonallocating shared interlock and TVM1 `EXTERNAL_TESTER_DETECTED`/`DIAGNOSTIC_STATE` transitions.
- [ ] **Step 4:** Run full tests; confirm whitelist still exactly services `0x01` and `0x21`.
- [ ] **Step 5:** Commit `fix: harden external tester diagnostic interlock`.

---

### Task 6: Add Health Instrumentation and Queue-Pressure Load Shedding

**Files:** v2.6 `.ino`, `TVM1_Meta.*`, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: TVM1 HEALTH_SNAPSHOT / STREAM_COUNTERS / STORAGE_HEALTH and existing TWAI/heap APIs.
- Produces exactly `struct CaptureHealth`, global `CaptureHealth captureHealth`, and `bool capturePressureHigh()` used by display/noncritical housekeeping.

- [ ] **Step 1:** Add failing tests for queue depth/HWM/drops, diagnostic drops, TWAI loss/error/off/recovery, RAW write count/average/max, flush count/max, loop max, TFT count/max, free/largest/min heap, stack HWM, SD short/write/flush/open errors and raw file index. Pin queue=1024, batch=128, SD=4 MHz.
- [ ] **Step 2:** Run focused tests; expected RED.
- [ ] **Step 3:** Implement aggregate counters using `esp_timer_get_time()`, queue-depth APIs, TWAI state and heap APIs; emit 5-second TVM1 snapshots plus final clean-close snapshot.
- [ ] **Step 4:** Implement `capturePressureHigh()` with named thresholds; defer TFT/noncritical housekeeping only, never RAW or protocol safety.
- [ ] **Step 5:** Run full tests GREEN.
- [ ] **Step 6:** Commit `feat: add v2.6 capture health instrumentation`.

---

### Task 7: Implement 80 MHz Dirty-Field Display for E32R35T and Dorhea

**Files:** v2.6 `.ino`, `TFT_eSPI_User_Setup_CYD35.h`, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: live signal state and `capturePressureHigh()`.
- Produces: E32R35T + Dorhea profile selection, page-entry static rendering, cached dynamic fields/buttons.

- [ ] **Step 1:** Add failing tests for exactly the two supported board profiles, no E32N35T target, `SPI_FREQUENCY 80000000`, absence of periodic steady-state 476x241 clear, and presence of cached field/button state.
- [ ] **Step 2:** Run focused tests; expected RED on RC2 full redraw/E32N35T fallback.
- [ ] **Step 3:** Implement explicit E32R35T/Dorhea profile constants and preserve validated pins/calibration.
- [ ] **Step 4:** Split page-entry static draw from dynamic update; fixed rectangles + cached text/state + `snprintf`; full redraw only on page/mode transition; defer dynamic render under `capturePressureHigh()`.
- [ ] **Step 5:** Run full tests; assert no full-screen RGB565 framebuffer.
- [ ] **Step 6:** Commit `perf: use 80MHz dirty-field CYD rendering`.

---

### Task 8: Adapt SD Descriptor Reservation and Wi-Fi to Native Session Files

**Files:** v2.6 `.ino`, v2.6 README, `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: RAW/META/OPEN session set and RC2 file-only HTTP API.
- Produces: capture candidate `SD_MAX_OPEN_FILES=5`, file list/ZIP/download that requires no legacy products, unchanged exclusive Wi-Fi shutdown/restart safety.

- [ ] **Step 1:** Add failing tests for descriptor candidate 5, only RAW+META persistent descriptors, TWAI/BLE/queues released before Wi-Fi, files-only routes, deletion token/open-marker protection, and ZIP/list code that enumerates files actually present rather than requiring MANIFEST/CSV.
- [ ] **Step 2:** Run focused tests; expected RED on RC2 descriptor/comment/session assumptions.
- [ ] **Step 3:** Apply minimal native-session changes; keep SD 4 MHz and no CAN API in Wi-Fi mode.
- [ ] **Step 4:** Run full tests GREEN.
- [ ] **Step 5:** Commit `perf: simplify SD and WiFi native session handling`.

---

### Task 9: Integration Verification, Compile, and Two-Board Bench Gate

**Files:** v2.6 README/VERSION, create `BENCH_VALIDATION.md`, update firmware tests as needed.

**Interfaces:**
- Consumes: Tasks 1-8 and validated offline preprocessor.
- Produces: release-candidate evidence; no promotion until both physical boards pass.

- [ ] **Step 1:** Add final acceptance assertions: TCB1 24-byte, 500 kbit/s, 25 MiB rotation, queue 1024, batch 128, SD 4 MHz, TFT 80 MHz, no live legacy artifacts, TVM1/no TCM1, RAW-first, pending STOP, hard external interlock, read-only whitelist, exclusive Wi-Fi, only two supported boards.
- [ ] **Step 2:** Run `python -m unittest discover -s firmware/tests -v` and `python -m unittest discover -s windows/ToyotaVehicleBusSessionPreprocessor/tests -v`; expected all PASS with no warnings/errors.
- [ ] **Step 3:** Compile E32R35T and Dorhea builds with ESP32 Arduino core 3.3.10, ESP32 Dev Module, Huge APP partition, documented TFT_eSPI setup. Record exact tool/library versions and build output; never claim compile PASS without actual output.
- [ ] **Step 4:** Bench E32R35T: boot with/without SD; BLE allocation; start/stop/sync/marker; touch/pages; sustained passive logging; external tester suppresses own diagnostics; read-only diagnostics+ISO-TP; unclean power recovery; Wi-Fi list/download/ZIP/delete/restart; no logging in Wi-Fi; health/drop counters.
- [ ] **Step 5:** Repeat same bench checklist on Dorhea with its profile/calibration.
- [ ] **Step 6:** Compare queue HWM/drops, RAW avg/max write latency, flush max, heap/largest/min heap, stack HWM, TFT max and BLE reliability to RC2. Keep `SD_MAX_OPEN_FILES=5` only if both boards pass; otherwise raise to minimum measured requirement and rerun affected checks.
- [ ] **Step 7:** Expand one real v2.6 bench session offline; verify legacy package generation and Builder acceptance. This is a v2.6 output sanity check, not another three-session campaign and not an Analyzer run.
- [ ] **Step 8:** Update README/VERSION/BENCH_VALIDATION with actual evidence; keep RC2 rollback until all required physical checks pass.
- [ ] **Step 9:** Commit `test: document v2.6 simplified logger validation`.
