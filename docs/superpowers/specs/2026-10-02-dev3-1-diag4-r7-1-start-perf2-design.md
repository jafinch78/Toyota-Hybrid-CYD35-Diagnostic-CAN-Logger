# DEV3.1 / DIAG4 R7.1 START-PERF2 + External-Tester/BLE Robustness Design

Date: 2026-10-02

## Purpose

Define the next bounded firmware revision after DEV3.0 / DIAG4 R7 field validation. The revision focuses only on START latency, durable BLE/control observability, conservative external-tester ownership, DEV-side reset breadcrumbs, and a defensive finite-value guard for the FUEL/TRIP/SOC page.

The revision names are:

- `DEV3.1-RAW-META` for the 1024-entry application CAN queue build.
- `DEV-DIAG4-R7.1-RAW-META` for the 768-entry application CAN queue build.
- Build family: `RAW-META-R6-FUELTRIP-STARTPERF2`.

The design intentionally does not advance graph rendering, touchscreen keypad work, Wi-Fi transfer performance, SD clock, CAN batch size, or queue size. Those remain separate experiments.

## Authoritative Field Baselines

Implementation must begin from the exact delivered and field-tested DEV3.0 / R7 package sources, not from an older branch merely carrying compatible ancestry.

- DEV3.0 package SHA-256: `9c88ad590640482fddcf7bedb7524d2264eee472273c3689b777274d7db683a2`
- DIAG4 R7 package SHA-256: `c33805c4c0a551d7da540d66195363c80213e95e785f644d45c8be2a98b85097`
- Runtime database v0.9.51 package SHA-256: `57af98c8ac098e9199b621a03ab2fdc1d80424bf7a45b8238fcffd5af77e97cb`

The implementation workflow must verify these package hashes before any source is changed and record the exact extracted source hashes used as the DEV3.1/R7.1 baselines.

## Field Evidence Driving This Revision

### S0201 / DEV3.0

S0201 ended abruptly with `SESSION.OPEN` still present and no normal STOP/finalization sequence. RAW and META remain structurally usable to the abrupt endpoint, but DEV3.0 lacked the retained reset-breadcrumb instrumentation needed to recover the exact reset cause.

After `EXTERNAL_TESTER_DETECTED`, the existing five-second quiet-time rule allowed CYD diagnostics to resume while the external tester was still logically in control of the diagnostic workflow. Roughly 366 CYD diagnostic TX frames followed the first external-tester detection. A TWAI error storm then rose to approximately 570,715 cumulative bus errors before the abrupt reset/restart signature. The evidence does not prove resumed CYD polling caused the reset, but it does prove that the five-second timeout is not a sufficient ownership rule.

S0201 also displayed `nan mi` for TRIP and SESSION despite passive 0x230 evidence indicating zero accumulated distance. This is treated as runtime-state/initialization corruption, not a distance-decoder failure.

### S0202 / DIAG4 R7

S0202 is the positive control. It closed cleanly with exact `STREAM_FILE_CLOSE` accounting, zero SD drops, zero TWAI bus errors, and a correct draining STOP. The STOP request-to-close interval was approximately 33.46 ms and the last persisted RAW frame was approximately 0.122 ms before the requested cutoff.

The R7 START path, however, remains expensive:

- Android command -> ACK: approximately 823 ms.
- Internal START timing: approximately 795 ms.
- START enter -> session directory ready: approximately 251 ms.
- Directory ready -> RAW open: approximately 52 ms.
- RAW open -> META open: approximately 52 ms.
- META open -> `loggingActive`: approximately 0.27 ms.
- `loggingActive` -> ACK: approximately 437 ms.

The next revision therefore treats first persisted RAW timing as a first-class metric rather than using ACK latency alone.

## Preserved Invariants

The following are frozen for DEV3.1 / R7.1 unless a source-contract test explicitly proves an accidental change and the change is rejected:

1. DEV queue length remains 1024.
2. DIAG4 queue length remains 768.
3. Main-loop RAW batch remains 128 frames.
4. SD logging SPI remains 4 MHz.
5. TFT PERF2 behavior remains enabled, including queue-pressure shedding and dirty rendering on the already optimized pages.
6. BLOCKS and TREND remain full-render paths in this revision.
7. RAW-first persistence ordering remains intact.
8. Pending/draining STOP semantics remain intact.
9. BLE STOP ACK remains after session finalization.
10. TCB1 format and 24-byte record layout remain unchanged.
11. TVM1 framing and existing record/event IDs remain backward compatible.
12. Existing NVS/high-water session allocator behavior remains unchanged.
13. `NEXT_SESSION.TXT` remains a deferred stopped-state mirror rather than a synchronous START authority.
14. Existing read-only diagnostic whitelist and Toyota safety policy remain unchanged.
15. Wi-Fi remains exclusive stopped-logger maintenance mode.
16. FUEL/TRIP/SOC page signal definitions remain unchanged.

## Non-Goals

This revision does not:

- optimize BLOCKS or TREND graph rendering;
- add a touchscreen numeric keypad;
- redesign gauges or page cosmetics;
- increase SD clock above 4 MHz;
- tune queue length or RAW batch size;
- change CAN bitrate;
- change BLE protocol packet size or Android protocol semantics;
- add arbitrary CAN transmit capability;
- add a same-session external-tester override button;
- change the decoding database except where a runtime-only metadata/schema declaration is required;
- claim to fix an Android command that never reaches the ESP32.

## Design Overview

The revision has five coordinated but independently testable changes:

1. `START-PERF2`: reduce synchronous START work and measure `loggingActive -> first RAW persisted`.
2. Persistent BLE/control observability in TVM1 without SD writes inside BLE callbacks.
3. Session-latched external-tester ownership that suppresses CYD diagnostic TX for the remainder of that logging session.
4. DEV3.1 retained reset breadcrumbs equivalent to the useful R7 reset/audit state.
5. FUEL/TRIP/SOC finite-value protection with one-shot anomaly telemetry.

No other functional area is intentionally changed.

## 1. START-PERF2

### 1.1 Target behavior

START must establish a durable native capture session with the minimum synchronous filesystem work necessary, then allow the main acquisition loop to persist RAW immediately.

The critical ordering is:

```text
BLE START command accepted
    -> capture START request timestamp/baselines
    -> reserve existing allocator session ID
    -> create S#### directory
    -> open RAW_000.TCB and write TCB1 header
    -> open SESSION.META and write/validate TVM1 header/session-open records required by contract
    -> establish SESSION.OPEN crash marker
    -> initialize session counters/state
    -> loggingActive = true
    -> return to acquisition loop
    -> drain accepted CAN queue
    -> persist first RAW batch
    -> perform deferred START housekeeping/audit
    -> emit BLE START response
```

The exact BLE response may occur before or after some deferred housekeeping, but it must never be placed ahead of first-RAW persistence solely to improve apparent ACK latency. First-RAW protection outranks ACK cosmetics.

### 1.2 SD free-space handling

Normal START must no longer call both `SD.cardSize()` and `SD.usedBytes()` unconditionally.

Instead maintain a stopped-state SD-space cache:

- obtain an exact total/used/free measurement after SD initialization while logging is stopped;
- refresh exact free space after a clean session close when the logger is stopped;
- optionally refresh during other stopped/idle maintenance points;
- while logging, maintain a conservative estimated remaining value by subtracting bytes successfully written to RAW and META from the last exact free-space value;
- before START, use the cached/conservative value for the normal low-space decision;
- only perform an exact START-time `SD.usedBytes()` refresh when cached free space is within a safety margin of the existing minimum-free threshold or the cache is invalid.

The cache is an optimization only. It must never permit a START when the firmware already knows free space is below the established minimum.

No SD clock change is permitted as part of this work.

### 1.3 `SESSION.OPEN`

`SESSION.OPEN` remains required because S0201 demonstrated its forensic value after an abrupt reset.

The preferred implementation is to reduce marker overhead without weakening crash detection:

- create the marker before `loggingActive` becomes true;
- avoid extra nonessential text/file churn around marker creation;
- if an open-handle approach is considered, it must first be proven on the actual ESP32 SD stack to survive an abrupt reset as a detectable marker;
- if durability is uncertain, retain the existing write-and-close marker behavior and optimize other START work instead.

A performance optimization must not remove or weaken the unclean-session indicator.

### 1.4 Deferred START housekeeping

Work not required for the native RAW+META session to become valid must be deferred until after first RAW persistence. Candidates include:

- exact SD-space refresh when not required by the low-space safety margin;
- human-readable Serial audit output;
- extended heap/largest-block reports;
- duplicate status formatting;
- noncritical reset/audit reporting;
- deferred `NEXT_SESSION.TXT` mirror work;
- any optional TFT refresh caused by START;
- other non-authoritative housekeeping discovered by instrumentation.

Deferred work must remain bounded and must obey the existing RAW-first queue-pressure rules.

### 1.5 START-PERF2 telemetry

Extend START timing so a single session can reconstruct these monotonic timestamps:

1. BLE START command received.
2. `startLogging()` entered.
3. session ID reserved.
4. session directory ready.
5. RAW file ready/header written.
6. META file ready/header written.
7. `SESSION.OPEN` established.
8. `loggingActive` asserted.
9. first session-eligible RAW frame/batch successfully persisted.
10. deferred START housekeeping complete.
11. BLE control response notify attempted.
12. START processing returned to normal loop state.

Existing START_TIMING arguments must remain backward compatible. New arguments/metrics must use previously unused IDs rather than reassigning existing meanings.

The primary new performance metric is:

```text
logging_active_to_first_raw_us
```

Secondary metrics are:

```text
command_to_first_raw_us
first_raw_to_ble_response_us
start_enter_to_logging_active_us
```

### 1.6 Acceptance targets

The field target is:

- `loggingActive -> first RAW persisted` < 100 ms for both variants under ordinary vehicle traffic;
- preferably one main-loop acquisition cycle rather than hundreds of milliseconds;
- R7.1 must no longer fill the 768 queue solely because synchronous START/post-active work delays the first RAW drain;
- command -> first RAW should materially improve from the S0202 baseline, with a target of at least 40% reduction;
- no regression in STOP timing/accounting or clean-close semantics.

The <100 ms value is a test target, not a reason to weaken crash markers, metadata integrity, or low-space protection.

## 2. Persistent BLE / Control Observability

### 2.1 Problem

DEV3.0/R7 added useful Serial records for BLE command receipt and control-response activity, but Serial output does not survive a field failure unless separately captured. A future S0199/S0201-like disappearance must leave durable session-local evidence.

### 2.2 Required persistent state

Add compact TVM1 observability for:

- BLE connected;
- BLE disconnected;
- advertising/reconnect transition where practical;
- control command received: opcode, sequence, receive timestamp;
- control command accepted/rejected status;
- response packet prepared;
- response `notify()` attempted;
- current BLE link state at periodic health snapshots;
- last command opcode/sequence/timestamp;
- last response status/sequence/timestamp.

The metadata must distinguish:

```text
notify_attempted
```

from any stronger claim of phone receipt. `BLECharacteristic::notify()` success at the firmware call site does not prove Android received or processed the notification.

### 2.3 Callback safety

BLE callbacks must not write to SD or append TVM1 directly.

Callbacks may only update fixed-size state and/or enqueue a compact record into an existing or dedicated bounded RAM metadata queue. The normal main-loop META service persists the record when safe according to RAW-first priority.

Queue overflow must increment an observable counter rather than block the BLE callback.

### 2.4 START-before-META edge case

A BLE START command necessarily arrives before the new session META file is fully available. The command-received record must therefore support a short pending/prestart RAM slot or queue. Once SESSION.META is ready, that record is emitted with its original receive timestamp and command sequence.

This preserves evidence of the initiating command without moving SD work into the BLE callback.

## 3. External-Tester Ownership Latch

### 3.1 New ownership rule

The five-second automatic resumption rule is removed for active logging sessions.

Once positively classified external-tester diagnostic activity is observed during a logging session:

```text
externalTesterOwnsSession = true
```

and CYD diagnostic transmission is suppressed for the remainder of that logging session.

### 3.2 Preserved behavior

While the latch is set:

- passive CAN acquisition continues;
- RAW persistence continues;
- passive broadcast decoding continues;
- TFT pages continue under existing PERF2 pressure rules;
- external tester request/response observation continues;
- TVM1 diagnostic evidence/health telemetry continues;
- TWAI remains in the safe passive/listen state required by the existing diagnostic-suspension implementation;
- CYD-generated diagnostic scheduler transmissions are prohibited.

### 3.3 Clearing the latch

The latch clears only when the current logging session ends or a new logger session is initialized.

DEV3.1/R7.1 does not add a same-session manual override. If an external tester remains active in the next session it will be detected again and the latch will be asserted again.

This rule is intentionally more conservative than a longer timeout because tester applications can have long quiet intervals while still logically owning the diagnostic workflow.

### 3.4 Observability

Record at least:

- first external-tester detection timestamp;
- ownership-latch timestamp;
- last observed external tester request timestamp;
- whether diagnostic TX was enabled at detection;
- whether the CYD was forced back to passive/listen state;
- count of CYD diagnostic TX frames after latch assertion.

The expected count of CYD diagnostic TX frames after latch assertion is zero. Any nonzero count is a release-blocking defect.

## 4. DEV3.1 Retained Reset Breadcrumbs

Port the useful retained reset/audit instrumentation from R7 into DEV3.1 so both variants provide comparable post-reset evidence.

Persist on the next boot, where technically available:

- ESP reset reason;
- previous uptime;
- previous logger state/stage;
- previous `loggingActive` state;
- previous session number;
- page index;
- external tester ownership/active state;
- external tester last-seen timestamp;
- diagnostic enabled state;
- TWAI normal/listen state;
- CAN queue depth/high-water;
- session-local TWAI bus errors;
- arbitration-lost counter;
- RX missed/overrun and TX failed counters;
- free internal heap;
- largest free internal block;
- minimum free heap if available;
- last completed major stage code.

Breadcrumb updates must be lightweight enough not to become a new acquisition hot-path problem. Stage changes should be coarse and meaningful, not per-frame writes.

The R7.1 implementation must preserve its existing retained reset/audit capability while aligning field names/stage meanings with DEV3.1 where practical.

## 5. FUEL/TRIP/SOC Finite-Value Guard

The established distance decoders and scaling remain unchanged.

Before trip/session miles reach TFT formatting or persisted runtime state, enforce finite values:

```cpp
if (!isfinite(sessionMiles)) sessionMiles = 0.0;
if (!isfinite(tripMiles))    tripMiles = 0.0;
```

The implementation should instrument the first non-finite transition per session before clamping, including enough context to identify which accumulator became non-finite and the immediately available source/baseline state.

Do not repeatedly emit the same anomaly every render cycle.

This is a defensive runtime guard, not a substitute for root-causing memory/state corruption if the condition occurs again.

## TVM1 Compatibility

Existing TVM1 record framing, CRC, sequence semantics, record types, and previously assigned event/metric IDs must remain stable.

New START-PERF2, BLE observability, external-ownership, reset/breadcrumb, and finite-value metrics may extend the HEALTH/EVENT payload schemas only by:

- using a new schema version when payload interpretation changes; and/or
- adding previously unused metric/event IDs;
- preserving all previously defined IDs and meanings.

The Windows native-session preprocessor must continue to accept the revised META stream without requiring a firmware-era special case. Unknown future metrics must remain skippable according to the existing contract.

## Protected-Routine Change Control

This revision necessarily touches protected areas: START lifecycle, BLE/control path, external-tester arbitration, and reset observability. The implementation must therefore record exact diffs and regression coverage for those changes.

The following must remain text-identical where no change is required, or have an explicit justified diff where a change is required:

- CAN RX task and accepted-frame queueing;
- RAW batch write format;
- RAW rotation accounting;
- STOP request/cutoff logic;
- draining STOP finalizer;
- STREAM_FILE_CLOSE accounting;
- SESSION_CLOSE and `SESSION.OPEN` removal on clean stop;
- diagnostic whitelist contents;
- Wi-Fi exclusivity and TWAI/BLE shutdown ordering;
- page signal formulas unrelated to the finite-value guard.

## Source / Host Test Requirements

Before packaging, source-contract and host tests must prove:

1. DEV queue remains 1024 and R7.1 remains 768.
2. RAW batch remains 128.
3. SD frequency remains 4 MHz.
4. Existing NVS allocator/high-water logic remains present and unchanged in behavior.
5. START no longer unconditionally performs `SD.cardSize()` + `SD.usedBytes()`.
6. Low-space rejection still exists.
7. START telemetry includes first-RAW persistence timing.
8. `SESSION.OPEN` remains part of the session contract.
9. BLE callbacks contain no direct SD/META writes.
10. BLE command/response/link observability reaches a bounded RAM path and TVM1 service path.
11. External tester detection asserts a session latch.
12. No five-second automatic diagnostic re-enable can occur while the session latch is set.
13. CYD diagnostic TX refuses transmission while external tester ownership is latched.
14. DEV3.1 includes reset breadcrumbs equivalent to the specified R7 observability subset.
15. FUEL/TRIP/SOC finite guards exist and anomaly emission is one-shot/bounded.
16. Existing draining STOP tests remain green without modification of their expected semantics.
17. Existing TVM1 parser/preprocessor tests remain green.
18. Event/metric registry contains no duplicate IDs and no changed historical meanings.
19. C/C++ delimiter/string/comment structural checks pass.
20. Exact delivered sources compile under the same host stubs used for prior validation.

Where practical, use RED-GREEN tests for each behavioral source contract before implementation.

## Arduino / Hardware Validation Gate

The packages remain TEST builds until both exact delivered archives pass Arduino IDE Verify with the established ESP32 3.3.10 / TFT_eSPI environment and then physical CYD testing.

### Phase A: START/STOP without external tester

For each CYD/microSD pairing:

1. Boot normally and confirm no reset breadcrumb indicates an unexplained prior failure.
2. Perform at least five consecutive Android BLE START/STOP cycles.
3. Confirm session IDs remain sequential and match Android ACKs.
4. Confirm BLE remains connected/reconnects normally.
5. Confirm `logging_active_to_first_raw_us` and `command_to_first_raw_us` are present in META.
6. Confirm no startup queue saturation caused solely by START synchronous work.
7. Confirm zero SD drops.
8. Confirm exact STREAM_FILE_CLOSE record/byte accounting.
9. Confirm SESSION_CLOSE and `SESSION.OPEN` removal on every clean STOP.
10. Confirm current draining STOP relation remains valid.

### Phase B: External tester ownership

1. Start a normal logging session.
2. Enable CYD read-only diagnostics if needed for the test.
3. Enter an Autel/AP200 diagnostic workflow.
4. Confirm `EXTERNAL_TESTER_DETECTED` and ownership-latch telemetry.
5. Confirm CYD diagnostic TX stops immediately.
6. Leave tester-request gaps longer than 5 s and 30 s.
7. Confirm CYD diagnostic TX does not automatically resume.
8. Continue passive logging and display operation.
9. STOP cleanly and verify exact closure/accounting.
10. Start a new session and confirm the ownership latch resets, then reasserts if the tester is still active.

### Phase C: BLE observability negative/positive controls

Exercise:

- normal START -> ACK;
- normal STOP -> ACK;
- manual TFT STOP after Android control inactivity;
- BLE disconnect/reconnect while stopped;
- BLE disconnect/reconnect while logging if supported by the existing implementation.

For every case, reconstruct from SESSION.META the last command received, BLE link state, response status, and `notify_attempted` state without depending on Serial output.

### Phase D: Controlled physical CAN-branch swap

After DEV3.1/R7.1 itself passes the above gates, perform a separate controlled A/B to investigate the recurring DEV/1024 versus DIAG/768 TWAI error asymmetry.

Keep firmware/CYD/microSD pairings fixed and swap only the CAN transceiver/cable branch between the two CYDs. Begin passive-only so diagnostic scheduling cannot confound the result. Compare TWAI bus errors, arbitration lost, queue loss, reset behavior, and RAW integrity.

Interpretation:

- error tendency follows transceiver/cable branch -> physical branch becomes the primary lead;
- error tendency remains with DEV CYD -> board/firmware/resource path remains the primary lead;
- error tendency disappears -> prior result remains environment/workflow-dependent and requires another controlled reproduction.

This hardware swap is an experiment, not part of the DEV3.1/R7.1 firmware acceptance requirement.

## Release-Blocking Failures

Any of the following blocks promotion of the revision:

- unexplained reset/reboot during START, logging, tester coexistence, or STOP;
- retained `SESSION.OPEN` after a clean STOP;
- missing SESSION_CLOSE on a clean STOP;
- changed TCB1 layout;
- SD frequency not equal to 4 MHz;
- altered queue size or batch size outside the two defined variants;
- nonzero CYD diagnostic TX after the external-tester session latch is asserted;
- automatic diagnostic re-enable based only on tester quiet time while the latch is active;
- BLE callback performing blocking filesystem/META I/O;
- START optimization weakening low-space safety or unclean-session detection;
- loss of exact STREAM_FILE_CLOSE accounting;
- regression of draining STOP behavior;
- duplicated/reassigned TVM1 IDs;
- repeated `NaN` TFT output after the finite guard;
- source/hash mismatch against the exact intended baseline or delivered package.

## Success Criteria

DEV3.1 / DIAG4 R7.1 is successful when field testing demonstrates all of the following:

1. The NVS/session allocator remains correct and sequential.
2. First RAW persistence occurs promptly after `loggingActive`, target <100 ms.
3. R7.1 no longer incurs startup queue saturation solely from post-active START work.
4. BLE/control state can be reconstructed durably from META rather than Serial alone.
5. External tester detection suppresses CYD diagnostic TX for the rest of the session with no timeout auto-resume.
6. DEV3.1 can report useful retained reset breadcrumbs after an unexpected restart.
7. FUEL/TRIP/SOC cannot display non-finite trip/session miles without a one-shot anomaly record.
8. RAW-first acquisition, exact file accounting, and draining STOP remain unchanged in semantics.
9. SD remains at 4 MHz and queue/batch sizes remain controlled A/B constants.
10. BLOCKS/TREND remain intentionally unchanged for the subsequent display-performance revision.

## Follow-On Revision

After DEV3.1 / R7.1 field acceptance, the next display-performance revision may optimize BLOCKS and TREND away from full-page rendering. That work must remain separate so START/control-path results are not confounded by another large rendering change.
