# DEV3.1 / DIAG4 R7.1 START-PERF2 Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build field-testable DEV3.1/1024 and DIAG4 R7.1/768 firmware from the exact DEV3.0/R7 field packages, reducing START exposure, instrumenting synchronous storage stalls, latching external-tester ownership, persisting BLE/control evidence, adding DEV reset breadcrumbs and finite trip guards, then producing a controlled 4 MHz versus 10 MHz SD A/B.

**Architecture:** Preserve RAW-first acquisition, 128-record batches, existing queue sizes, draining STOP, TVM1/TCB1 contracts, TFT PERF2, NVS allocator, and read-only diagnostic safety. Add bounded RAM instrumentation/state and persist it only through the normal META service. Complete and verify the 4 MHz firmware before creating 10 MHz A/B builds whose only functional difference is the SD SPI clock.

**Tech Stack:** ESP32 Arduino core 3.3.10, C++/Arduino, TFT_eSPI, SD/SPI, BLE, TWAI, TVM1 SESSION.META, TCB1 RAW.

**Spec:**
- `docs/superpowers/specs/2026-10-02-dev3-1-diag4-r7-1-start-perf2-design.md`
- `docs/superpowers/specs/2026-10-02-dev3-1-diag4-r7-1-shared-can-branch-amendment.md`
- `docs/superpowers/specs/2026-10-02-s0204-s0210-storage-latency-sd-clock-amendment.md`

## Global Constraints

- DEV3.1 queue = 1024; R7.1 queue = 768.
- RAW batch = 128.
- Primary acceptance builds use `SD_SPI_FREQUENCY = 4000000`.
- 10 MHz A/B builds are created only after the exact 4 MHz source passes verification; their only functional difference is `SD_SPI_FREQUENCY = 10000000` plus build identity.
- TCB1 record layout remains 24 bytes and unchanged.
- Existing TVM1 framing/CRC/sequence and historical IDs remain compatible.
- Existing NVS/high-water session allocator remains unchanged.
- `SESSION.OPEN` remains required for abrupt-reset forensics.
- Draining STOP and BLE STOP ACK-after-finalization remain unchanged.
- BLE callbacks and CAN RX callbacks/tasks perform no direct SD/META filesystem writes.
- Once external tester ownership is latched in a logging session, CYD diagnostic TX remains disabled until STOP/new session.
- BLOCKS/TREND rendering remains out of scope.
- Do not increase queue size, RAW batch size, or SD clock beyond the explicit 10 MHz A/B during this plan.

## Authoritative Baseline Gate

The implementation working copies must be extracted from the exact archived packages:

```text
DEV3.0 ZIP SHA-256
9c88ad590640482fddcf7bedb7524d2264eee472273c3689b777274d7db683a2

DIAG4 R7 ZIP SHA-256
c33805c4c0a551d7da540d66195363c80213e95e785f644d45c8be2a98b85097
```

Primary source files in each archive:

```text
logger_v2_4_3_core.inc
TVM1_SessionMeta.h
TVM1_SessionMeta.cpp
TVM1_Meta.h
TVM1_Meta.cpp
runtime_trip_math.h
<variant>.ino
```

Record SHA-256 for every extracted implementation source before modifying it.

## Review Focus

1. Cold/first START after boot must not be hidden by good warm-start results.
2. Any synchronous SD call over 100/250 ms must be observable without instrumentation itself blocking RAW acquisition.
3. External-tester latch must stop every CYD diagnostic TX path, including stale scheduler state and direct transmit helpers.
4. BLE START command received before SESSION.META exists must still be reconstructible later without callback SD writes.
5. 10 MHz must remain a true one-variable A/B; no unrelated source changes between 4 MHz and 10 MHz packages.

---

### Task 1: Freeze exact DEV3.0/R7 field baselines and create DEV3.1/R7.1 working trees

**Files:**
- Create working tree: `firmware/field/DEV3_1_RAW_META/`
- Create working tree: `firmware/field/DEV_DIAG4_R7_1_RAW_META/`
- Create: `firmware/tests/test_dev3_1_r7_1_source_contract.py`
- Create: `firmware/field/DEV3_1_R7_1_BASELINE_SHA256.txt`

**Interfaces:**
- Consumes: exact DEV3.0/R7 ZIPs listed above.
- Produces: two source trees whose only initial changes are directory/sketch/build identities.

- [ ] **Step 1: Write failing baseline tests.** Assert the expected ZIP SHA values, DEV/R7 queue constants 1024/768, batch 128, SD clock 4 MHz, TCB1 24-byte invariant, `SESSION.OPEN`, draining STOP symbols, and unchanged read-only diagnostic services.
- [ ] **Step 2: Run baseline tests and confirm they fail because DEV3.1/R7.1 trees do not exist yet.**
- [ ] **Step 3: Extract/copy exact field sources and record per-file SHA-256 before any behavioral edit.** Rename only variant/sketch/build identities to DEV3.1 and R7.1.
- [ ] **Step 4: Run source-contract tests; require PASS.**
- [ ] **Step 5: Commit:** `chore: freeze DEV3.0 R7 field baselines for next revision`.

### Task 2: Add storage-latency and cold/warm START observability first

**Files:**
- Modify both `logger_v2_4_3_core.inc` copies.
- Modify both `TVM1_SessionMeta.*` copies only if new metric/event IDs require it.
- Modify `firmware/tests/test_dev3_1_r7_1_source_contract.py`.

**Interfaces:**
- Produces aggregate `StorageTimingState`/equivalent state with count/total/max and threshold counters; no direct SD writes from measurement sites.

- [ ] **Step 1: Write failing tests for timing coverage.** Require timing around RAW write, RAW flush, META flush, combined `flushLogFiles()`, `SD.usedBytes()`, `SD.cardSize()`, mkdir, RAW open/header, META open/header, SESSION.OPEN creation, rotation, and STOP finalization.
- [ ] **Step 2: Require threshold counters at >25, >50, >100 and >250 ms, plus queue depth snapshots around long synchronous operations where practical.**
- [ ] **Step 3: Add a boot/cold-start generation marker so first START after boot is distinguishable from warm START.** Do not infer this only from session number.
- [ ] **Step 4: Implement aggregate timing using `esp_timer_get_time()`/existing monotonic timer.** No `Serial.printf`, String construction, SD write, or BLE notify inside timed hot sections except the operation being measured.
- [ ] **Step 5: Persist the aggregate through existing TVM1 HEALTH/EVENT service after RAW priority permits.**
- [ ] **Step 6: Run tests and commit:** `feat: instrument START and synchronous SD latency`.

### Task 3: Implement START-PERF2 and conservative free-space caching

**Files:**
- Modify both `logger_v2_4_3_core.inc` copies.
- Modify source-contract tests.

**Interfaces:**
- Produces `logging_active_to_first_raw_us`, `command_to_first_raw_us`, `first_raw_to_ble_response_us`, and `start_enter_to_logging_active_us`.

- [ ] **Step 1: Write failing tests requiring normal START not to unconditionally execute both `SD.cardSize()` and `SD.usedBytes()`.** Low-space rejection must remain.
- [ ] **Step 2: Add stopped-state exact SD-space cache and conservative in-session decrement by successfully written RAW+META bytes.** Invalid/near-threshold cache falls back to exact free-space query.
- [ ] **Step 3: Keep `SESSION.OPEN` established before `loggingActive`; do not change its durability behavior unless an explicit bench test proves an alternative survives abrupt reset.**
- [ ] **Step 4: Defer non-authoritative post-start work until after first RAW persistence.** Preserve allocator, RAW/META headers, crash marker, and required session records before activation.
- [ ] **Step 5: Capture first successfully persisted session RAW timestamp in the RAW write path and emit START-PERF2 timing once.**
- [ ] **Step 6: Tests require SD clock remains 4 MHz and queue/batch constants remain unchanged.**
- [ ] **Step 7: Commit:** `perf: add START-PERF2 first RAW priority`.

### Task 4: Replace five-second tester auto-resume with session ownership latch

**Files:**
- Modify both `logger_v2_4_3_core.inc` copies.
- Modify source/safety tests.

**Interfaces:**
- Produces `externalTesterOwnsSession` (or equivalent) initialized false at new session, latched true on positive external request detection, cleared only after STOP/new-session initialization.

- [ ] **Step 1: Write failing tests proving the old quiet-time path cannot re-enable CYD diagnostics while ownership latch is set.**
- [ ] **Step 2: Latch ownership on the same positive external-tester classifier already used for `EXTERNAL_TESTER_DETECTED`.**
- [ ] **Step 3: Gate both diagnostic scheduler and final CAN diagnostic transmit helper so stale scheduler state cannot transmit after latch.**
- [ ] **Step 4: Preserve passive logging, external transaction observation, display, RAW/META service and STOP while latched.**
- [ ] **Step 5: Count CYD diagnostic TX attempts/frames after latch; acceptance value is zero.**
- [ ] **Step 6: Commit:** `fix: latch external tester ownership for logging session`.

### Task 5: Persist BLE/control observability without callback filesystem work

**Files:**
- Modify both `logger_v2_4_3_core.inc` copies.
- Modify TVM1 metadata helper/registry only as required.
- Modify tests.

**Interfaces:**
- Produces a fixed-size bounded pending BLE event queue/state containing link transition, opcode, sequence, timestamp, accepted/rejected status, response-prepared status, and `notify_attempted`.

- [ ] **Step 1: Write failing tests forbidding `SD.*`, `File.*`, `sessionMeta.write*`, and filesystem calls in BLE `onConnect`, `onDisconnect`, and `onWrite` callbacks.**
- [ ] **Step 2: Add bounded RAM state/queue for BLE events. Overflow increments an observable counter and never blocks callback.**
- [ ] **Step 3: Preserve the pre-META START command event with its original command timestamp/sequence and flush it to META once the new session META is active.**
- [ ] **Step 4: Record `notify_attempted`; never label it Android receipt/ACK delivery unless Android independently confirms it.**
- [ ] **Step 5: Commit:** `feat: persist BLE control observability in META`.

### Task 6: Port reset breadcrumbs to DEV3.1 and guard non-finite trip/session miles

**Files:**
- Modify DEV3.1 `logger_v2_4_3_core.inc` using R7 retained breadcrumb implementation as source.
- Modify R7.1 only for shared stage/field naming where necessary.
- Modify both finite-value display/runtime paths.
- Modify tests.

**Interfaces:**
- Produces comparable retained reset data on both variants and one-shot non-finite anomaly telemetry.

- [ ] **Step 1: Write failing tests requiring DEV3.1 retained reset reason, prior logger/logging state, session, tester/diag state, queue high-water, TWAI counters, heap fields and last major stage.**
- [ ] **Step 2: Port R7 retained state into DEV3.1 without per-frame RTC writes.** Update only coarse major stages/checkpoints.
- [ ] **Step 3: Add `isfinite()` guard before trip/session miles reach TFT formatting or stored runtime state.**
- [ ] **Step 4: Emit one bounded anomaly event per affected accumulator/session before clamping; no render-loop spam.**
- [ ] **Step 5: Commit:** `fix: add DEV reset breadcrumbs and finite trip guards`.

### Task 7: Verify and package the 4 MHz DEV3.1/R7.1 baseline

**Files:**
- Update `VALIDATION.txt`, `SOURCE_BASELINES.txt`, `SHA256SUMS.txt`, and build/readme identities in both package trees.
- Create host/source validation report.

**Interfaces:**
- Produces two canonical 4 MHz TEST archives.

- [ ] **Step 1: Run full source-contract suite and structural C/C++ checks.** Require zero failures.
- [ ] **Step 2: Verify exact invariants: DEV=1024, R7.1=768, batch=128, SD=4 MHz, same diagnostic whitelist, TCB1/TVM1 compatible, draining STOP present.**
- [ ] **Step 3: Run host C++/stub compile used for prior DEV3.0/R7 validation.**
- [ ] **Step 4: If Arduino CLI/IDE toolchain is available in execution environment, Verify both exact sketches with ESP32 core 3.3.10; otherwise mark Arduino Verify as a user hardware/toolchain gate rather than claiming it passed.**
- [ ] **Step 5: Build deterministic ZIPs, calculate SHA-256, reopen archives and verify internal source hashes and names.**
- [ ] **Step 6: Commit:** `build: package DEV3.1 R7.1 4MHz field test firmware`.

### Task 8: Produce the controlled 10 MHz A/B variants

**Files:**
- Clone the exact verified Task 7 package trees into clearly labeled SD10M A/B trees.
- Change only variant/build identity and `SD_SPI_FREQUENCY`.
- Add comparison manifest generated from file hashes/diffs.

**Interfaces:**
- Produces DEV3.1-SD10M-A_B and R7.1-SD10M-A_B test archives.

- [ ] **Step 1: Write a diff test that fails unless the 4 MHz and 10 MHz source trees differ only in the SD frequency constant and explicit build/version labels.**
- [ ] **Step 2: Change `SD_SPI_FREQUENCY` from `4000000` to `10000000`; make no other behavioral edit.**
- [ ] **Step 3: Re-run full source/host verification.**
- [ ] **Step 4: Generate machine-readable 4M-vs-10M diff/hash manifest proving the one-variable A/B.**
- [ ] **Step 5: Package, hash, reopen and independently verify both 10 MHz archives.**
- [ ] **Step 6: Commit:** `test: add controlled 10MHz SD A B firmware builds`.

## Physical Validation Sequence

Use the 4 MHz package first on each established CYD/microSD pairing. For each, include a true first START after boot and at least four warm START/STOP repetitions, then a longer run designed to cross multiple one-second flushes and five-second health/storage checkpoints. Verify first-RAW latency, queue loss, SD timing histograms, exact close accounting, BLE META reconstruction and no tester-latch TX violations.

Only after the matching 4 MHz run is clean, flash the corresponding 10 MHz A/B package and repeat the same procedure without changing CYD, microSD, transceiver/cable, vehicle/test point or Android controller where practical.

Do not promote 10 MHz merely because average RAW write latency improves. Promotion requires no structural/mount/close regression and must materially improve or at least not worsen the tail latency responsible for S0210-like stalls.

## Self-Review Result

- Spec coverage: START-PERF2, SD-space cache, storage-tail telemetry, tester latch, BLE durability, reset breadcrumbs, finite guard, 4 MHz baseline, 10 MHz A/B and protected invariants are each assigned to a task.
- Type/interface consistency: all new state is bounded RAM state serviced through the existing main-loop META path; no task introduces callback filesystem I/O.
- Review Focus coverage: cold START is Task 2/3; long storage stalls Task 2; stale diagnostic TX Task 4; pre-META BLE START Task 5; one-variable SD clock A/B Task 8.
- Scope control: graph rendering, queue enlargement, batch enlargement and >10 MHz testing remain outside this plan.
