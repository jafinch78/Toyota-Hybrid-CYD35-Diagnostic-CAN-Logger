# DEV3.1 / DIAG4 R7.1 START-PERF2 Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build field-testable DEV3.1/1024 and DIAG4 R7.1/768 firmware from the exact DEV3.0/R7 field packages, reducing START and post-START blocking, instrumenting synchronous storage/TWAI interactions, latching external-tester ownership, persisting BLE/control evidence, adding DEV reset breadcrumbs and finite trip guards, then producing a controlled 4 MHz versus 10 MHz SD A/B.

**Architecture:** Preserve RAW-first acquisition, 128-record batches, existing queue sizes, draining STOP, TVM1/TCB1 contracts, TFT PERF2, NVS allocator, and read-only diagnostic safety. Add bounded RAM instrumentation/state and persist it only through the normal META service. Treat START as four measurable windows through steady-state, split deferred postamble work into bounded queue-aware steps, and complete/verify the 4 MHz firmware before creating 10 MHz A/B builds whose only functional difference is the SD SPI clock plus explicit build identity.

**Tech Stack:** ESP32 Arduino core 3.3.10, C++/Arduino, TFT_eSPI, SD/SPI, BLE, TWAI, TVM1 SESSION.META, TCB1 RAW.

**Spec:**
- `docs/superpowers/specs/2026-10-02-dev3-1-diag4-r7-1-start-perf2-design.md`
- `docs/superpowers/specs/2026-10-02-dev3-1-diag4-r7-1-shared-can-branch-amendment.md`
- `docs/superpowers/specs/2026-10-02-s0204-s0210-storage-latency-sd-clock-amendment.md`
- `docs/superpowers/specs/2026-10-02-s0212-s0213-microsd-crossover-amendment.md`

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
- Deferred START postamble work is queue-aware and serviced at most one bounded step per eligible main-loop opportunity.
- No unconditional `SD.usedBytes()` scan occurs solely because START completed.
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

1. A fast `loggingActive -> first RAW` must not hide later queue loss during deferred START postamble; tests must separately account for pre-first-RAW and postamble drops.
2. `SESSION.OPEN` open/write/close and every other synchronous SD operation over 25/50/100/250 ms must be observable without instrumentation itself blocking RAW acquisition.
3. TWAI-error onset must be correlatable with storage operation timing, external-tester timing, diagnostic ownership state, and queue pressure without assuming the microSD directly causes CAN errors.
4. External-tester latch must stop every CYD diagnostic TX path, including stale scheduler state and direct transmit helpers, while preserving passive acquisition/display.
5. 10 MHz must remain a true one-variable A/B, with Card B tested first for storage-tail isolation and Card A kept at instrumented 4 MHz until TWAI timing is characterized.

---

### Task 1: Freeze exact DEV3.0/R7 field baselines and create DEV3.1/R7.1 working trees

**Files:**
- Create: `firmware/field/DEV3_1_RAW_META/`
- Create: `firmware/field/DEV_DIAG4_R7_1_RAW_META/`
- Create: `firmware/tests/test_dev3_1_r7_1_source_contract.py`
- Create: `firmware/field/DEV3_1_R7_1_BASELINE_SHA256.txt`

**Interfaces:**
- Consumes: exact DEV3.0/R7 ZIPs listed above.
- Produces: two source trees whose only initial changes are directory/sketch/build identities, plus recorded per-file baseline hashes.

- [ ] **Step 1: Write failing baseline tests.** Add `test_exact_field_baselines`, `test_fixed_queue_and_batch_constants`, `test_tcb1_layout_unchanged`, `test_session_open_retained`, and `test_read_only_diagnostic_whitelist_unchanged`.
- [ ] **Step 2: Run:** `py -3 -m unittest firmware.tests.test_dev3_1_r7_1_source_contract -v`. Expected: FAIL because DEV3.1/R7.1 trees do not yet exist.
- [ ] **Step 3: Extract/copy exact field sources and record SHA-256 for every implementation file before behavioral edits.** Rename only variant/sketch/build identities.
- [ ] **Step 4: Re-run the focused test command.** Expected: PASS.
- [ ] **Step 5: Commit:** `chore: freeze DEV3.0 R7 field baselines for next revision`.

### Task 2: Add storage, START-window, and TWAI-correlation observability first

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: both `TVM1_SessionMeta.*` copies only if new metric/event IDs require it.
- Modify: `firmware/tests/test_dev3_1_r7_1_source_contract.py`.

**Interfaces:**
- Produces: bounded `StorageTimingState`/equivalent aggregate state; four START-window timestamps/counters; TWAI onset correlation snapshot state.
- No measurement site directly writes SD or formats Serial output.

- [ ] **Step 1: Write failing timing-coverage tests.** Require measurement around RAW write, RAW flush, META flush, combined `flushLogFiles()`, `SD.usedBytes()`, `SD.cardSize()`, mkdir, RAW open/header, META open/header, `SESSION.OPEN` open/write/close/total, rotation, each deferred postamble step, and STOP finalization.
- [ ] **Step 2: Write failing threshold/correlation tests.** Require >25, >50, >100, >250 ms counters; maximum duration; queue depth/drop counters before/after the maximum operation; last external-tester request time; external ownership state; diagnostic-enabled state; TWAI bus-error/arbitration-lost values at correlation snapshots.
- [ ] **Step 3: Write failing START-window tests.** Require explicit timestamps/counters for command→loggingActive, loggingActive→first RAW, first RAW→postamble begin, postamble begin→postamble complete, and postamble complete→steady-state declaration; require separate `drops_before_first_raw` and `drops_during_postamble` fields.
- [ ] **Step 4: Add a boot/cold-start generation marker.** First START after boot must be distinguishable from warm START without inferring from session number.
- [ ] **Step 5: Implement aggregate timing with `esp_timer_get_time()`/existing monotonic timer and bounded POD state.** No `String`, `Serial.printf`, BLE notify, or filesystem write inside measurement sites except the operation being timed.
- [ ] **Step 6: Persist aggregates through existing TVM1 HEALTH/EVENT service only after RAW priority permits.** Unknown/new metric IDs must remain skippable by existing tooling.
- [ ] **Step 7: Run the focused and cumulative source tests; require PASS.**
- [ ] **Step 8: Commit:** `feat: instrument START storage and TWAI correlation`.

### Task 3: Implement START-PERF2, bounded postamble service, and conservative free-space caching

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: source-contract tests.

**Interfaces:**
- Consumes: timing/window state from Task 2.
- Produces: `logging_active_to_first_raw_us`, `command_to_first_raw_us`, postamble duration, steady-state timestamp, and separated startup-drop accounting.

- [ ] **Step 1: Write failing tests requiring normal START not to unconditionally execute both `SD.cardSize()` and `SD.usedBytes()`.** Existing low-space refusal remains mandatory.
- [ ] **Step 2: Write failing postamble tests.** Require postamble to be represented as an explicit bounded state machine/step index, with at most one postamble step serviced per eligible loop pass and a queue-pressure gate before each step.
- [ ] **Step 3: Require candidate postamble steps to remain independently observable:** pending BLE/control META, noncritical reset/audit reporting, checkpoint/storage metadata, deferred `NEXT_SESSION.TXT`, exact free-space refresh only when safety requires it, and optional TFT/status refresh.
- [ ] **Step 4: Add stopped-state exact SD-space cache and conservative decrement by successfully written RAW+META bytes.** Invalid/near-threshold cache falls back to an exact query; START completion itself does not trigger a scan.
- [ ] **Step 5: Keep `SESSION.OPEN` durable and established before `loggingActive`.** Instrument open, payload write, close/flush, total, and surrounding queue state separately; do not remove/weakly emulate the marker.
- [ ] **Step 6: Move every non-authoritative START activity that can safely be deferred into the bounded postamble state machine.** RAW queue drain/persistence outranks every postamble step.
- [ ] **Step 7: Capture first successfully persisted session RAW and declare steady state only after postamble completion and a subsequent normal acquisition opportunity.**
- [ ] **Step 8: Tests require SD=4 MHz, DEV/R7 queue=1024/768, batch=128, and unchanged allocator/TCB1/STOP semantics.**
- [ ] **Step 9: Run tests and commit:** `perf: split START postamble and prioritize first RAW`.

### Task 4: Replace five-second tester auto-resume with session ownership latch

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: source/safety tests.

**Interfaces:**
- Produces: `externalTesterOwnsSession` (or equivalent), initialized false for a new session, latched true on positive external request classification, cleared only after STOP/new-session initialization.
- Supplies tester state to Task 2 correlation snapshots.

- [ ] **Step 1: Write failing tests proving the quiet-time path cannot re-enable CYD diagnostics while the ownership latch is set.**
- [ ] **Step 2: Latch ownership on the existing positive external-tester classifier used for `EXTERNAL_TESTER_DETECTED`.**
- [ ] **Step 3: Gate both diagnostic scheduler and final diagnostic transmit helper so stale state cannot transmit after latch.**
- [ ] **Step 4: Preserve passive logging, external request/response observation, display, RAW/META service, and STOP while latched.**
- [ ] **Step 5: Count post-latch CYD diagnostic TX attempts/frames.** Acceptance value is zero.
- [ ] **Step 6: Add source test asserting next-session initialization clears the latch and permits normal diagnostic policy until an external tester is detected again.**
- [ ] **Step 7: Commit:** `fix: latch external tester ownership for logging session`.

### Task 5: Persist BLE/control observability without callback filesystem work

**Files:**
- Modify: both `logger_v2_4_3_core.inc` copies.
- Modify: TVM1 helper/registry only as required.
- Modify: tests.

**Interfaces:**
- Produces: fixed-size bounded pending BLE event queue/state containing link transition, opcode, sequence, timestamp, accepted/rejected status, response-prepared status, and `notify_attempted`.
- Postamble service from Task 3 may persist pending startup control evidence only after RAW priority permits.

- [ ] **Step 1: Write failing tests forbidding `SD.*`, `File.*`, `sessionMeta.write*`, and filesystem calls in BLE `onConnect`, `onDisconnect`, and `onWrite` callbacks.**
- [ ] **Step 2: Add bounded RAM state/queue for BLE events.** Overflow increments an observable counter and never blocks the callback.
- [ ] **Step 3: Preserve a pre-META START command event with its original timestamp/sequence until SESSION.META is active.**
- [ ] **Step 4: Persist that event through normal META/postamble service, not the callback.**
- [ ] **Step 5: Record `notify_attempted`; never label it Android receipt unless Android independently confirms it.**
- [ ] **Step 6: Commit:** `feat: persist BLE control observability in META`.

### Task 6: Port reset breadcrumbs to DEV3.1 and guard non-finite trip/session miles

**Files:**
- Modify: DEV3.1 `logger_v2_4_3_core.inc` using R7 retained breadcrumb implementation as source.
- Modify: R7.1 only for shared stage/field naming where necessary.
- Modify: both finite-value display/runtime paths.
- Modify: tests.

**Interfaces:**
- Produces: comparable retained reset data on both variants and one-shot non-finite anomaly telemetry.

- [ ] **Step 1: Write failing tests requiring DEV3.1 retained reset reason, prior logger/logging state, session, tester/diag state, queue high-water, TWAI counters, heap fields, and last major stage.**
- [ ] **Step 2: Port R7 retained state into DEV3.1 without per-frame RTC writes.** Update only coarse major stages/checkpoints, including START-window/postamble stage identity useful for crash localization.
- [ ] **Step 3: Add `isfinite()` guard before trip/session miles reach TFT formatting or stored runtime state.**
- [ ] **Step 4: Emit one bounded anomaly event per affected accumulator/session before clamping; no render-loop spam.**
- [ ] **Step 5: Run tests and commit:** `fix: add DEV reset breadcrumbs and finite trip guards`.

### Task 7: Verify and package the canonical 4 MHz DEV3.1/R7.1 baseline

**Files:**
- Update: `VALIDATION.txt`, `SOURCE_BASELINES.txt`, `SHA256SUMS.txt`, and build/readme identities in both package trees.
- Create: host/source validation report.

**Interfaces:**
- Produces: two canonical 4 MHz TEST archives with complete source/hash provenance.

- [ ] **Step 1: Run full source-contract suite and structural C/C++ checks.** Require zero failures.
- [ ] **Step 2: Verify exact invariants:** DEV=1024, R7.1=768, batch=128, SD=4 MHz, same diagnostic whitelist, TCB1/TVM1 compatible, `SESSION.OPEN` retained, draining STOP present.
- [ ] **Step 3: Verify START/postamble contract statically:** four measurable windows, separate pre-first/postamble loss counters, one bounded postamble step per eligible service, no unconditional post-START `SD.usedBytes()` scan.
- [ ] **Step 4: Run host C++/stub compile used for prior DEV3.0/R7 validation.**
- [ ] **Step 5: If Arduino CLI/IDE toolchain is available, Verify both exact sketches with ESP32 core 3.3.10; otherwise record Arduino Verify as a user toolchain gate without claiming it passed.**
- [ ] **Step 6: Build deterministic ZIPs, calculate SHA-256, reopen archives, and verify internal source hashes/names.**
- [ ] **Step 7: Commit:** `build: package DEV3.1 R7.1 4MHz field test firmware`.

### Task 8: Produce controlled 10 MHz A/B variants and card-ordered validation manifest

**Files:**
- Clone: exact verified Task 7 package trees into clearly labeled SD10M A/B trees.
- Change: only variant/build identity and `SD_SPI_FREQUENCY`.
- Create: machine-readable 4M-vs-10M diff/hash manifest and physical-validation checklist.

**Interfaces:**
- Produces: DEV3.1-SD10M-A_B and R7.1-SD10M-A_B TEST archives.
- Validation order encoded in checklist: Card B first for storage-tail A/B; Card A second only after instrumented 4 MHz TWAI characterization.

- [ ] **Step 1: Write a diff test that fails unless 4 MHz and 10 MHz source trees differ only in SD-frequency constant and explicit build/version labels.**
- [ ] **Step 2: Change `SD_SPI_FREQUENCY` from `4000000` to `10000000`; make no other behavioral edit.**
- [ ] **Step 3: Re-run full source/host verification.**
- [ ] **Step 4: Generate machine-readable diff/hash manifest proving the one-variable A/B.**
- [ ] **Step 5: Generate validation checklist requiring Card B 4 MHz baseline before Card B 10 MHz, comparing START tail, `SESSION.OPEN`, postamble, RAW/META flush tails, >25/>50/>100/>250 ms counts, RAW gaps, drops, mount/open/close behavior, and exact close accounting.**
- [ ] **Step 6: In the same checklist require Card A instrumented 4 MHz runs to capture TWAI/storage/external-tester causal ordering before any Card A 10 MHz run.**
- [ ] **Step 7: Package, hash, reopen, and independently verify both 10 MHz archives.**
- [ ] **Step 8: Commit:** `test: add controlled 10MHz SD A B firmware builds`.

## Physical Validation Sequence

### Phase A — 4 MHz baseline on both established CYD/card pairings

For each pairing, perform one true first START after boot, at least four warm START/STOP repetitions, and one longer run crossing multiple flush/health intervals. Verify:

- command→loggingActive;
- loggingActive→first RAW;
- pre-first-RAW drop count;
- postamble drop count;
- postamble completion and steady-state declaration;
- maximum RAW gap in first 2 seconds;
- `SESSION.OPEN` open/write/close/total timing;
- synchronous SD >25/>50/>100/>250 ms counters;
- exact STREAM_FILE_CLOSE/SESSION_CLOSE accounting;
- BLE META reconstruction;
- zero post-latch CYD diagnostic TX.

### Phase B — Card B 4 MHz → 10 MHz storage-tail A/B

Use the same CYD, Card B, transceiver/cable, vehicle/test point, diagnostic/passive mode, and Android controller where practical. Compare tail latency, not merely averages. A 10 MHz build is not promoted if average writes improve while >100/>250 ms stalls, queue loss, structural errors, or mount/open/close regressions remain.

### Phase C — Card A instrumented TWAI characterization

Keep Card A at 4 MHz initially. Reproduce external-tester workflow while correlating first TWAI error and escalation with storage operation timing, queue pressure, external-tester request timing, tester ownership latch, and diagnostic TX state. Do not describe Card A as electrically causing CAN errors from association alone.

Only after a clean/reproducible 4 MHz characterization may the otherwise-identical Card A 10 MHz A/B be run.

### Phase D — Acceptance interpretation

- A 1024 queue that still saturates confirms blocking-time root cause remains; do not respond by enlarging queue as the primary fix.
- If START first RAW improves but postamble still causes loss, START-PERF2 has not passed.
- If 10 MHz improves average throughput but not long-tail stalls, treat filesystem/card-controller/internal latency as the remaining bottleneck.
- If TWAI storms occur before any diagnostic auto-resume with the ownership latch active, continue investigating external-tester/protocol/power/storage-state interactions rather than the removed timeout path.

## Self-Review Result

- Spec coverage: S0212/S0213 crossover, Card A/Card B interpretations, four START windows, bounded postamble, `SESSION.OPEN` sub-timing, SD-space caching, storage-tail telemetry, TWAI correlation, tester latch, BLE durability, reset breadcrumbs, finite guard, 4 MHz baseline, and 10 MHz A/B are each assigned to a task.
- Step scan: every implementation step names one testable state/change; no firmware body is pre-written in the plan.
- Type/interface consistency: Task 2 owns aggregate timing/window/correlation state; Task 3 consumes START/storage timing; Task 4 supplies tester ownership state; Task 5 supplies bounded BLE state; later packaging tasks consume the same named contracts.
- Review Focus coverage: postamble-hidden loss is Task 2/3; long SD stalls and `SESSION.OPEN` timing are Task 2/3; TWAI causal snapshots are Task 2/4; stale diagnostic TX is Task 4; one-variable/card-ordered SD A/B is Task 8.
- Scope control: graph rendering, queue enlargement, batch enlargement, >10 MHz testing, arbitrary CAN control, and unrelated decoder work remain outside this plan.
