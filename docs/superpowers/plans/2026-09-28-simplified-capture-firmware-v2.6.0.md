# Simplified Capture Firmware v2.6.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Toyota Hybrid CYD logger v2.6.0 from the validated v2.5.0-rc.2 baseline with RAW-first TCB1 persistence, canonical TVM1 metadata, reduced SD products, hard diagnostic safety interlocks, and 80 MHz dirty-field TFT updates.

**Architecture:** Preserve the RC2 high-priority CAN RX and exclusive Wi-Fi architecture, but move archival convenience work off the ESP32. Normal capture keeps only RAW + TVM1 `SESSION.META` open, performs contiguous RAW persistence before derived/live work, and records non-reconstructible state as compact TVM1 records. The existing offline preprocessor is already authorized to regenerate Builder-compatible legacy artifacts.

**Tech Stack:** ESP32 Arduino core 3.3.10, C++/Arduino, TFT_eSPI/ST7796/XPT2046, ESP32 TWAI, SD/SPI, BLE, WiFi/WebServer, Preferences, Python `unittest` source/contract tests.

**Spec:** `docs/superpowers/specs/2026-09-28-simplified-capture-firmware-design.md`

## Global Constraints

- Baseline source is exact RC2 blob `bbc7421da2bfc684324123b3232895cdcfd6c23d` from `release/logger-v2.5.0-rc.2-dorhea-touch`.
- Create v2.6.0 separately; do not modify v2.4.2 or overwrite the RC2 rollback/reference.
- Supported boards are only `E32R35T_TOUCH` and `DORHEA_B0DLNJSSFW_TOUCH`; E32N35T is excluded.
- TFT SPI write frequency remains `80000000` Hz.
- TCB1 remains a 16-byte header plus packed 24-byte CAN records; CAN bitrate remains 500000 bit/s and raw rotation remains 25 MiB initially.
- Diagnostic CAN transmissions remain read-only services `0x01` and `0x21`; no control/write/clear/reset/coding API is introduced.
- SD SPI remains 4 MHz initially; application CAN queue stays 1024 and main-loop RAW batch stays 128 until measured evidence justifies changes.
- `SD_MAX_OPEN_FILES=5` is only the first bench-test candidate, not an accepted production value until both boards pass resource/SD/BLE testing.
- Wi-Fi remains an exclusive stopped-logger maintenance mode and exits by restart.
- Canonical TVM1 is defined by `docs/TVM1_SESSION_META_BINARY_SPEC.md`; the older TCM1 draft must never appear in v2.6.0.
- RC2 remains the rollback/preferred vehicle build until host/static checks, Arduino compilation, and physical E32R35T + Dorhea bench validation pass.

## Review Focus

1. **Power loss during TVM1 append:** previously valid metadata and complete RAW records remain parseable; a partial final TVM1 record is tolerated by the validated offline parser. Task 2 pins record framing and Task 9 exercises unclean recovery.
2. **BLE STOP while CAN queue is nonempty:** STOP becomes pending and cannot close RAW/META until queued evidence is drained. Task 4 tests this source/state ordering.
3. **External tester appears between RAW receive and scheduler tick:** RX asserts the interlock before the scheduler/transmit path can send. Task 5 pins both scheduler and `transmitCAN()` refusal.
4. **Display/SD latency under CAN load:** UI and noncritical metadata are deferred under queue pressure rather than sacrificing RAW. Tasks 6 and 7 pin load shedding and removal of steady-state full clears.
5. **Reduced session set in Wi-Fi ZIP/list/download:** Wi-Fi must work with RAW/META/OPEN without assuming legacy CSV/JSON files exist. Task 8 pins native-session enumeration/ZIP behavior.

---

### Task 1: Import the Exact RC2 Baseline as v2.6.0 and Pin Invariants

**Files:**
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0.ino`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TFT_eSPI_User_Setup_CYD35.h`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/README.md`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/VERSION.txt`
- Create: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: RC2 sketch/setup from release branch; no current-branch firmware source later than v2.4.2 is used as a substitute.
- Produces: v2.6.0 sketch baseline with unchanged TCB1, safety whitelist, Wi-Fi exclusivity, session allocator, CAN pins, and RC2 functional structure for later tasks.

- [ ] **Step 1: Write failing baseline/source tests**

In `test_v2_6_0_source.py`, assert the new sketch exists and contains: `sizeof(CapturedFrame) == 24`, CAN TX/RX 25/32, only diagnostic services `{0x01,0x21}`, `twai_driver_uninstall()` and `BLEDevice::deinit(true)` before Wi-Fi AP creation, `ESP.restart()` exit, monotonic session allocator inputs, and no write/control services. Assert board-target text names E32R35T and Dorhea and does not advertise E32N35T.

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m unittest firmware.tests.test_v2_6_0_source -v`
Expected: FAIL because the v2.6.0 directory/sketch does not exist.

- [ ] **Step 3: Copy RC2 exactly, then change only version/target identity needed to establish v2.6.0**

Copy the RC2 `.ino` whose source blob SHA is `bbc7421...`, RC2 TFT setup, and RC2 documentation into the new directory. Change sketch/version strings to `2.6.0-dev` and define the two supported board-profile identities without changing capture behavior yet. Keep TFT setup at 80 MHz.

- [ ] **Step 4: Run baseline tests GREEN**

Run: `python -m unittest firmware.tests.test_v2_6_0_source -v`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "feat: establish v2.6.0 from validated RC2 baseline"`

---

### Task 2: Add Canonical TVM1 Encoder and Metadata Queue

**Files:**
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TVM1_Meta.h`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/TVM1_Meta.cpp`
- Modify: v2.6.0 `.ino`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`
- Test against: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/meta.py`

**Interfaces:**
- Consumes: canonical TVM1 constants/payload layout and CRC-32/ISO-HDLC contract.
- Produces: `Tvm1Writer`/equivalent focused API capable of opening a session header, appending typed records, flushing, and closing; a bounded RAM metadata queue serviced by the main loop.

- [ ] **Step 1: Add failing TVM1 contract tests**

Assert source definitions encode magic `TVM1`, major/minor `1/0`, 32-byte header, sync `0xA55A`, minimum 24-byte record, CRC polynomial `0xEDB88320`, stream 0 session scope, stream 1 CAN/TBC1 registration, and all record IDs required by the spec. Assert no `TCM1` token exists in v2.6.0 firmware.

- [ ] **Step 2: Verify RED**

Run: `python -m unittest firmware.tests.test_v2_6_0_source -v`
Expected: FAIL on missing TVM1 encoder/constants.

- [ ] **Step 3: Implement the minimal TVM1 encoder**

Use explicit byte serialization rather than compiler-dependent packed metadata structs. Implement CRC-32/ISO-HDLC, file header serialization, record envelope serialization, length-prefixed UTF-8 provenance strings, and typed helpers for the records required by the v2.6.0 spec. Keep storage ownership outside the RX task.

- [ ] **Step 4: Add a firmware-generated TVM1 contract vector path**

Provide a deterministic encoder fixture/helper callable from a host/static test configuration or captured as fixed bytes so Python `meta.py` can parse the header and representative SESSION_START, STREAM_REGISTER, counters, event, and SESSION_CLOSE records. The test must compare record field values and CRC acceptance, not only source tokens.

- [ ] **Step 5: Run firmware and preprocessor TVM1 tests GREEN**

Run: `python -m unittest firmware.tests.test_v2_6_0_source windows.ToyotaVehicleBusSessionPreprocessor.tests.test_meta -v`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat: add canonical TVM1 firmware metadata writer"`

---

### Task 3: Reduce Capture Files to RAW + META + OPEN

**Files:**
- Modify: v2.6.0 `.ino`
- Modify: `TVM1_Meta.*`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: Task 2 TVM1 writer.
- Produces: start/rotation/close file lifecycle where only current `RAW_nnn.TCB` and `SESSION.META` stay open; `SESSION.OPEN` is marker-only.

- [ ] **Step 1: Write failing file-contract tests**

Assert normal session creation opens RAW + `SESSION.META`, creates `SESSION.OPEN`, and does not open/create `DECODED.CSV`, `DIAGNOSTICS.CSV`, `EXTERNAL_DIAGNOSTICS.CSV`, `EVENTS.CSV`, `SYNC.CSV`, `SIGNALS.CSV`, `README.TXT`, `MANIFEST.JSON`, or `CHECKPOINT.JSON`. Assert RAW rotation emits TVM1 STREAM_FILE_CLOSE/OPEN rather than legacy manifest/checkpoint work.

- [ ] **Step 2: Verify RED**

Run focused source tests; expect failures on legacy file creation/open calls.

- [ ] **Step 3: Remove redundant persistent file globals/open/write/flush paths**

Retain in-RAM live signal and diagnostic state. Replace non-reconstructible event/sync/health persistence with TVM1 record enqueue calls. Do not remove diagnostics themselves.

- [ ] **Step 4: Make clean and unclean markers match the contract**

Clean close writes final counters/state, STREAM_STOP, SESSION_CLOSE, flushes/closes RAW + META, then removes `SESSION.OPEN`. Power loss leaves marker and recoverable prior records.

- [ ] **Step 5: Run focused and full firmware source tests GREEN**

Run: `python -m unittest discover -s firmware/tests -v`
Expected: PASS with no forbidden live artifact creation in v2.6.0.

- [ ] **Step 6: Commit**

`git commit -m "feat: reduce v2.6 capture to raw and TVM1"`

---

### Task 4: Make RAW Persistence First and Make Start/Stop Boundaries Loss-Safe

**Files:**
- Modify: v2.6.0 `.ino`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: existing 1024-frame queue and 128-frame batch, Task 3 file lifecycle.
- Produces: `stopPending` state and explicit start-boundary handling; main loop persists each drained batch before derived processing/meta/display.

- [ ] **Step 1: Add failing ordering/boundary tests**

Source/state tests assert `writeRawBatch(batch,count)` precedes batch-derived processing and metadata service; BLE STOP sets pending state rather than calling file close directly; clean close executes only after queued RAW drain; BLE START explicitly clears/filters pre-start residue before session opening.

- [ ] **Step 2: Verify RED**

Run focused test; expect current RC2 ordering/direct STOP behavior to fail.

- [ ] **Step 3: Reorder normal loop**

Implement spec order: critical flags → drain batch → RAW write → process same batch → diagnostic drain → TVM1 service → diagnostics/TWAI → touch → dirty display → flush → yield.

- [ ] **Step 4: Implement pending stop and explicit start semantics**

Use request timestamp/source/sequence state; record stop-request event immediately in RAM/TVM1 queue, drain evidence, append final TVM1 state, then close. Choose and document one deterministic pre-start policy (drain/discard stale queue before opening is preferred because it avoids cross-session ambiguity).

- [ ] **Step 5: Run full firmware source tests GREEN**

Run: `python -m unittest discover -s firmware/tests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "fix: persist raw before derived work and close safely"`

---

### Task 5: Harden External-Tester Interlock Without Removing Live Diagnostics

**Files:**
- Modify: v2.6.0 `.ino`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: RC2 external request detector, diagnostic scheduler, fast ISO-TP FC path.
- Produces: shared RX-set interlock checked independently by scheduler and `transmitCAN()`; TVM1 diagnostic/event state instead of external diagnostic CSV.

- [ ] **Step 1: Add failing interlock tests**

Assert RX task updates `externalTesterLastUs`/interlock before raw queue handoff, scheduler refuses new transactions during 5000 ms hold, and `transmitCAN()` itself refuses diagnostic TX while interlocked. Assert fast ISO-TP FC for an already-owned logger transaction remains in the RX path and TX evidence is still queued into RAW.

- [ ] **Step 2: Verify RED**

Run focused test; expect direct transmit-level hard interlock assertion to fail if RC2 only relies on scheduler state.

- [ ] **Step 3: Implement the shared hard interlock**

Keep request classification minimal and nonallocating in RX. Record `EXTERNAL_TESTER_DETECTED`/`DIAGNOSTIC_STATE` to TVM1 as compact state transitions; do not write a CSV.

- [ ] **Step 4: Run full tests GREEN**

Also assert diagnostic whitelist remains exactly services `0x01` and `0x21`.

- [ ] **Step 5: Commit**

`git commit -m "fix: harden external tester diagnostic interlock"`

---

### Task 6: Add Health Instrumentation and Queue-Pressure Load Shedding

**Files:**
- Modify: v2.6.0 `.ino`
- Modify: `TVM1_Meta.*`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: TVM1 HEALTH_SNAPSHOT, STREAM_COUNTERS, STORAGE_HEALTH; existing TWAI status and heap APIs.
- Produces: `CaptureHealth`/equivalent aggregate state, queue high-water accounting, timing counters, periodic 5 s TVM1 snapshots, and a single queue-pressure predicate used by UI/noncritical work.

- [ ] **Step 1: Add failing instrumentation tests**

Assert fields/counters exist for CAN queue HWM/drops, diagnostic drops, TWAI loss/error/off/recovery, RAW write avg/max, flush count/max, loop max, TFT max/count, free/largest/min heap, stack HWM, SD short/write/flush/open failures, and raw file index. Assert 1024 queue, batch 128, SD 4 MHz remain unchanged.

- [ ] **Step 2: Verify RED**

Run focused tests; expect missing aggregate instrumentation/load-shed predicate.

- [ ] **Step 3: Instrument existing boundaries without hot-path strings**

Use `esp_timer_get_time()`, queue depth/high-water updates, existing TWAI status, and heap-cap APIs. Emit only aggregate TVM1 snapshots every 5 seconds and immediately before clean close.

- [ ] **Step 4: Add queue-pressure deferral**

Under configured occupancy threshold(s), defer TFT refresh and noncritical periodic metadata/housekeeping; never skip queued RAW persistence or protocol safety work. Keep thresholds named constants and report occupancy/HWM for later tuning.

- [ ] **Step 5: Run full tests GREEN**

Run: `python -m unittest discover -s firmware/tests -v`
Expected: PASS.

- [ ] **Step 6: Commit**

`git commit -m "feat: add v2.6 capture health instrumentation"`

---

### Task 7: Implement 80 MHz Dirty-Field Display for E32R35T and Dorhea

**Files:**
- Modify: v2.6.0 `.ino`
- Modify: `TFT_eSPI_User_Setup_CYD35.h`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: live signal state and Task 6 pressure predicate.
- Produces: two board profiles, static-on-entry page drawing, cached fixed-field redraws, state-only button redraws.

- [ ] **Step 1: Add failing board/display tests**

Assert supported profile identifiers are exactly E32R35T + Dorhea; no E32N35T profile. Assert TFT setup retains `SPI_FREQUENCY 80000000`. Assert normal steady-state update path contains no periodic `fillRect(2, 2, 476, 241, ...)` or equivalent full content clear, and uses cached field/button state.

- [ ] **Step 2: Verify RED**

Run focused test; expect RC2 full redraw and fallback E32N35T scope to fail.

- [ ] **Step 3: Implement board profile selection**

Preserve validated pin mapping and profile-specific touch calibration; isolate profile constants so one sketch can be compiled intentionally for either supported board.

- [ ] **Step 4: Implement dirty rendering**

Split page-entry static draw from dynamic field update. Use fixed rectangles and last-rendered char/state caches; use `snprintf` in hot dynamic formatting. Full page redraw occurs only on page/mode transition. Defer steady-state render when Task 6 pressure predicate says capture is busy.

- [ ] **Step 5: Run full tests GREEN**

Run firmware tests; verify no framebuffer allocation and no E32N35T target token in active target definitions.

- [ ] **Step 6: Commit**

`git commit -m "perf: use 80MHz dirty-field CYD rendering"`

---

### Task 8: Adapt SD Descriptor and Wi-Fi File Mode to the Native Session Set

**Files:**
- Modify: v2.6.0 `.ino`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`
- Modify: v2.6.0 `README.md`

**Interfaces:**
- Consumes: Task 3 native session file set and RC2 file-only HTTP API.
- Produces: capture mount candidate `SD_MAX_OPEN_FILES=5`, ZIP/list/download behavior that requires no legacy artifacts, unchanged exclusive Wi-Fi shutdown/restart safety.

- [ ] **Step 1: Add failing descriptor/Wi-Fi tests**

Assert capture build candidate is 5 descriptors, only RAW/META are persistent, Wi-Fi starts only after logger files/TWAI/BLE/queues are released, HTTP remains files-only, deletion token/open-marker protection remains, and ZIP generation includes whatever files are actually present instead of requiring MANIFEST/CSV products.

- [ ] **Step 2: Verify RED**

Run focused test; expect RC2 assumptions/comments about six persistent streams and descriptor count 10 to fail.

- [ ] **Step 3: Apply minimal descriptor/native-session changes**

Set 5 as a documented bench candidate; do not change SD clock. Update file listing/ZIP metadata and UI descriptions to the reduced set without adding CAN APIs to Wi-Fi mode.

- [ ] **Step 4: Run full tests GREEN**

Run: `python -m unittest discover -s firmware/tests -v`
Expected: PASS.

- [ ] **Step 5: Commit**

`git commit -m "perf: simplify SD and WiFi native session handling"`

---

### Task 9: Integration Verification, Arduino Compile, and Two-Board Bench Gate

**Files:**
- Modify: v2.6.0 `README.md`
- Modify: v2.6.0 `VERSION.txt`
- Create: `firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_6_0/BENCH_VALIDATION.md`
- Modify/Test: `firmware/tests/test_v2_6_0_source.py`

**Interfaces:**
- Consumes: all prior tasks plus validated offline preprocessor.
- Produces: a release-candidate package/checklist with explicit host/compile/bench evidence; no promotion until both physical boards pass.

- [ ] **Step 1: Add final static acceptance tests**

Assert TCB1 24-byte contract, 500 kbit/s, 25 MiB rotation, queue 1024, batch 128, SD 4 MHz, TFT 80 MHz, no legacy live file creation, TVM1 present/no TCM1, RAW-before-derived order, pending STOP, hard external interlock, read-only whitelist, exclusive Wi-Fi, and only the two supported boards.

- [ ] **Step 2: Run complete host/static suites**

Run:

`python -m unittest discover -s firmware/tests -v`

`python -m unittest discover -s windows/ToyotaVehicleBusSessionPreprocessor/tests -v`

Expected: all PASS, no warnings/errors.

- [ ] **Step 3: Compile both board-profile builds in the documented Arduino environment**

Use ESP32 Arduino core 3.3.10, ESP32 Dev Module, Huge APP partition, TFT_eSPI with the v2.6.0 setup, and compile once for E32R35T and once for Dorhea. Record exact IDE/core/library versions and build output. Do not claim compile PASS unless actual compile output is available.

- [ ] **Step 4: Bench E32R35T**

Verify boot with/without SD; BLE allocation; idle and active start/stop; BLE sync/marker; touch/pages; sustained passive logging; external tester suppresses own diagnostics; read-only logger diagnostics + ISO-TP; deliberate unclean power loss recoverable by preprocessor; Wi-Fi list/download/ZIP/delete/restart; no CAN logging in Wi-Fi; health counters show no new queue drops attributable to refactor.

- [ ] **Step 5: Bench Dorhea**

Repeat the same checklist with Dorhea-specific touch calibration and profile identity.

- [ ] **Step 6: Compare resource/latency evidence to RC2**

Review queue HWM/drops, RAW max/avg write latency, flush max, heap/largest/min heap, stack HWM, TFT max, and BLE reliability. Accept `SD_MAX_OPEN_FILES=5` only if both boards pass; otherwise raise to the minimum measured value needed and rerun affected tests.

- [ ] **Step 7: Expand at least one real v2.6.0 bench session offline**

Run the validated Toyota Vehicle Bus Session Preprocessor on RAW + TVM1, confirm legacy package generation and Builder acceptance. This is a v2.6 output sanity check, not a repeat of the completed three-session authorization campaign and not an Analyzer run.

- [ ] **Step 8: Mark release boundary accurately**

Update README/VERSION with actual test state. RC2 remains rollback until all required physical checks above have evidence. Never describe unperformed hardware tests as PASS.

- [ ] **Step 9: Commit**

`git commit -m "test: document v2.6 simplified logger validation"`
