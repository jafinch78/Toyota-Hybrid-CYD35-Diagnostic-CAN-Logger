# DEV3.2 / DIAG4 R7.2 Storage-Resilience Design

Date: 2026-10-03

## Purpose

Define the next firmware milestone after field validation of DEV3.1 / DIAG4 R7.1 at 25 MHz and the S0218/S0219 true-LISTEN_ONLY controls.

The revision names are:

- `DEV3.2-RAW-META`.
- `DEV-DIAG4-R7.2-RAW-META`.
- Build family: `RAW-META-R7-FUELTRIP-STARTPERF2-SD25M-STORAGERES1`.

The primary objective is no longer to suppress the Autel-associated TWAI bus-error storm in firmware. S0218/S0219 demonstrate that the storm persists with TWAI forced to true `LISTEN_ONLY`, zero physical logger TX frames, zero arbitration-lost events, and zero post-latch diagnostic TX. The production logger therefore treats the storm as an externally generated/observed condition and concentrates this milestone on robust evidence acquisition through long synchronous storage stalls.

The secondary objective is to complete the observability gaps exposed by S0214-S0219 so future field captures can distinguish queue-pressure, storage, startup, and external-tester effects without reconstructing them indirectly.

## Authoritative Implementation Baselines

Implementation must begin from the exact delivered 25 MHz DEV3.1 / R7.1 package sources used for S0214/S0215 and retained for S0216/S0217, not from the S0218/S0219 forced-LISTEN_ONLY experimental edits.

Authoritative package SHA-256 values:

```text
DEV3.1 SD25M TEST
5b1675792c727ae63dc7c19d9400248e6207e1e7039eb34cf93008e46763b5df

DIAG4 R7.1 SD25M TEST
e9c62ab6535a4518d5cc4825356a22f06dbd8e90e8bcfca7406fc7b4a8a9f760
```

The implementation workflow must verify these hashes before behavioral edits and record per-file source SHA-256 values.

## Field Evidence Driving This Revision

### S0214 / S0215: 25 MHz + START-PERF2 positive control

S0214 and S0215 validate the 25 MHz baseline and START-PERF2 architecture:

- zero queue drops in both sessions;
- zero SD/storage drops;
- exact RAW/META closure accounting;
- clean SESSION_CLOSE;
- exact Android/META CLOCK_SYNC pairing;
- `loggingActive -> first RAW` below 1 ms in both sessions;
- effective SD SPI persisted as 25,000,000 Hz.

S0215/Card B nevertheless records long-tail RAW write latency up to approximately 230 ms while remaining lossless with the 1024-entry queue.

### S0216 / S0217: Manual vs Auto Autel comparison

Manual and Auto vehicle-detection paths expose essentially the same visible protocol-discovery sequence and both produce severe TWAI bus-error storms. The logger has zero post-latch diagnostic TX after external-tester ownership is asserted.

S0217/Card B independently reproduces a storage-loss event:

- raw write maximum approximately 234 ms;
- queue high-water 1024/1024;
- 394 queue drops;
- approximately 234.9 ms RAW timestamp gap;
- TWAI error count already plateaued during the storage event.

This separates storage loss from the TWAI phenomenon.

### S0218 / S0219: true LISTEN_ONLY discriminator

The S0218/S0219 experimental builds force TWAI `LISTEN_ONLY` and prohibit TX for the entire logging session.

Both sessions still reproduce severe Autel-associated bus-error storms:

- S0218 approximately 285,513 bus errors;
- S0219 approximately 287,649 bus errors;
- zero physical TX frames;
- zero arbitration-lost events;
- zero post-latch diagnostic TX.

Therefore active logger transmission, ACK participation, arbitration, and active error-frame recovery are not required for the observed high `bus_error_count` phenomenon.

S0219/Card B additionally records the strongest storage-tail evidence so far:

- raw write maximum approximately 344 ms;
- RAW flush maximum approximately 594 ms;
- combined flush-service maximum approximately 594 ms;
- queue high-water 1024/1024;
- 449 queue drops;
- dominant approximately 253 ms RAW timestamp gap after the TWAI storm had already plateaued.

Card A remains materially better behaved under the same 25 MHz generation.

## Design Decision: Separate TWAI Investigation From Production Optimization

The Autel/TWAI investigation becomes a separate validation track and does not block DEV3.2/R7.2.

Queued validation work:

1. One CYD at 500 kbit/s true LISTEN_ONLY during the Autel identification workflow.
2. A second CYD at 250 kbit/s true LISTEN_ONLY during the same interval.
3. If alternate-rate coherent traffic is not captured, use an oscilloscope or logic analyzer on CANH/CANL immediately after the functional `7DF 09 02` requests and measure bit widths / waveform behavior.

The production firmware does not attempt to auto-switch bitrates, suppress the externally generated storm, or reconfigure TWAI during an active session in response to bus-error count alone.

## Preserved Invariants

Unless explicitly changed below:

1. SD SPI remains 25 MHz.
2. TCB1 remains unchanged with 24-byte records.
3. TVM1 framing, CRC, sequence semantics, and historical IDs remain backward compatible.
4. RAW batch size remains 128 records.
5. Draining STOP remains authoritative.
6. BLE STOP response remains after finalization.
7. `SESSION.OPEN` remains required.
8. NVS/high-water session allocation remains unchanged.
9. Existing read-only Toyota diagnostic whitelist remains unchanged.
10. Wi-Fi remains stopped-state maintenance mode.
11. TFT PERF2 dirty rendering remains the baseline.
12. The session-latched external-tester ownership rule remains in production.
13. External-tester ownership uses software diagnostic-TX inhibition and does not tear down/restart TWAI merely because ownership is latched.
14. Production firmware is based on the NORMAL-mode S0214-S0217 baseline, not the forced-LISTEN_ONLY S0218/S0219 experiment.
15. No automatic CAN bitrate changes are introduced.

## Design Overview

DEV3.2/R7.2 contains six coordinated changes:

1. Increase application CAN queue headroom to a target of 1536 records if memory acceptance gates pass.
2. Add queue-pressure hysteresis and RAW-only catch-up service.
3. Make periodic storage/metadata service pressure-aware so it does not compound an existing backlog.
4. Complete startup/storage/pressure telemetry.
5. Add a deterministic one-shot 650 ms stall-injection validation build.
6. Preserve the proven 25 MHz, START-PERF2, external-tester latch, and clean STOP behavior.

A dedicated SD writer task, filesystem/library replacement, larger RAW batch, and clocks above 25 MHz remain deferred unless this simpler architecture fails field validation.

## 1. Queue Capacity and Memory Gate

### 1.1 Target capacity

The preferred queue capacity for both production variants is:

```text
CAN_CAPTURE_QUEUE_LEN = 1536
```

At 24 bytes per `CapturedFrame`, the payload allocation is approximately 36,864 bytes plus FreeRTOS queue metadata.

At the observed approximately 1,670 frames/s NHW20 traffic rate, 1536 records represent approximately 920 ms of capture buffering.

This exceeds the largest observed Card-B synchronous blocking interval (~594 ms) and gives recovery margin without immediately doubling to 2048.

### 1.2 Memory acceptance gate

1536 is a target, not an assumption.

Before field release, both variants must expose and verify:

- free internal heap immediately before queue allocation;
- largest free internal block immediately before queue allocation;
- queue allocation success/failure;
- free internal heap immediately after queue allocation;
- largest free internal block immediately after queue allocation;
- minimum free internal heap after normal startup where available.

Release acceptance requires:

- queue allocation succeeds normally;
- no startup/reset loop caused by memory pressure;
- post-allocation free internal heap remains at least 64 KiB;
- post-allocation largest free internal block remains at least 32 KiB;
- normal BLE, TFT, META, and diagnostic initialization still succeed.

If either firmware variant fails this gate, do not silently fall back at runtime. Revisit the compile-time queue target and choose the largest common tested value that satisfies the gate.

The queue length must be persisted in runtime telemetry so the field capture proves which capacity was actually running.

## 2. Queue-Pressure Hysteresis and RAW Catch-Up Mode

### 2.1 Pressure thresholds

For a 1536-entry queue, initial production thresholds are:

```text
PRESSURE_HIGH = 768 records   // 50%
PRESSURE_LOW  = 384 records   // 25%
```

If the final accepted queue length differs from 1536, define thresholds as 50% HIGH and 25% LOW using integer compile-time constants.

### 2.2 Entering pressure mode

When queue depth reaches or exceeds `PRESSURE_HIGH`:

```text
capturePressureMode = true
```

Record the transition once with:

- timestamp;
- queue depth;
- queue high-water;
- queue-drop count;
- current storage operation / last storage maximum;
- current page;
- external-tester ownership state;
- TWAI bus-error/arbitration-lost snapshot.

### 2.3 Behavior while pressured

While `capturePressureMode` is true, the main loop prioritizes RAW persistence and performs repeated existing 128-record RAW batches while work is available.

The following nonessential work is deferred:

- TFT rendering;
- trend/block graph rendering;
- optional BLE status notifications;
- routine health/checkpoint META emission;
- exact SD free-space refresh;
- periodic flush initiation;
- noncritical Serial formatting/audit output;
- deferred START housekeeping that is not required for capture validity.

The following must remain available:

- CAN RX task / queueing;
- RAW batch persistence;
- required RAW rotation;
- pending STOP recognition;
- safety-critical session state;
- already-required minimal metadata needed to preserve file-format correctness.

### 2.4 Leaving pressure mode

Pressure mode clears only when queue depth falls to or below `PRESSURE_LOW`.

This hysteresis prevents page/flush/checkpoint work from oscillating on and off near one threshold.

Record exit timestamp, duration, maximum queue depth while pressured, drop delta, and RAW records drained.

## 3. Pressure-Aware Storage Service

### 3.1 Periodic flush

The existing periodic flush interval remains the nominal target, but a periodic flush must not begin while queue depth is elevated enough to threaten acquisition.

Rules:

- if queue depth is above `PRESSURE_LOW`, defer a routine periodic flush;
- never start a routine flush while `capturePressureMode` is active;
- record flush-deferred count and maximum deferral duration;
- perform the deferred flush once queue pressure is relieved and RAW catch-up has completed;
- STOP finalization always performs required durability work regardless of pressure;
- RAW file rotation performs the durability work required for a valid close/open transition.

A periodic flush deferral is preferable to immediately compounding a queue backlog with another known-blocking storage operation.

### 3.2 Checkpoint / health META

Routine health/storage checkpoints follow the same pressure policy:

- defer while pressure mode is active;
- coalesce repeated missed intervals into one later checkpoint rather than emitting a burst of stale checkpoints;
- persist counts of deferred/coalesced checkpoints.

Critical one-shot evidence such as reset/open/close semantics remains protected by its existing contract.

### 3.3 Storage operation instrumentation

Retain and extend PERF-INSTR2 metrics for:

- RAW write;
- RAW flush;
- META flush;
- combined flush service;
- SD free-space calls;
- `SESSION.OPEN` open/write/close;
- rotation close/open/header;
- STOP finalization;
- pressure-mode entry/exit;
- flush deferral duration;
- queue depth before/after maximum-duration operations.

Retain >25, >50, >100, and >250 ms counters.

## 4. Complete Runtime Observability

### 4.1 START timing completion

Persist the START state that DEV3.1/R7.1 already tracks internally but does not fully expose:

- postamble begin timestamp;
- postamble complete timestamp;
- steady-state timestamp;
- drops before first RAW;
- drops during postamble;
- maximum RAW gap during startup window.

Existing START metric IDs retain their meanings; allocate new IDs for new fields.

### 4.2 STOP timing completion

Ensure the final STOP/finalization duration is persisted before the metadata stream becomes unavailable.

Do not compute a STOP metric only after SESSION.META has already been closed if no durable record remains to carry it.

Persist at least:

- STOP request timestamp;
- request queue depth;
- drained frame count;
- last accepted/persisted RAW timestamp;
- final RAW flush duration;
- final META flush duration;
- request-to-stream-close duration;
- request-to-session-close duration.

### 4.3 Pressure / memory telemetry

Persist:

- compile-time queue capacity;
- queue allocation memory snapshots;
- pressure-entry count;
- total time in pressure mode;
- maximum pressure duration;
- maximum queue depth;
- RAW records drained during pressure mode;
- queue-drop delta during pressure mode;
- routine flush-deferred count/max duration;
- routine checkpoint-deferred/coalesced count.

## 5. Deterministic Stall-Injection Validation Build

Create a separate TEST-ONLY build option that can inject exactly one controlled main-loop stall of approximately 650 ms.

Requirements:

- disabled by default in production packages;
- compile-time or clearly isolated test flag;
- one-shot only per session unless explicitly rebuilt for another mode;
- inject only after logging has reached steady state;
- record event immediately before and after the artificial stall using RAM-safe state that can be persisted afterward;
- do not alter CAN RX task behavior;
- do not intentionally disable interrupts or TWAI reception;
- the injection simulates synchronous main-loop/storage blocking, not electrical SD failure.

Acceptance for a 1536-entry queue at normal NHW20 traffic:

- zero queue drops during the 650 ms injection;
- pressure mode enters and later exits;
- queue high-water remains below capacity;
- RAW timestamps remain continuous apart from any loss that would indicate a defect;
- normal TFT/META/flush work resumes after recovery;
- clean STOP remains exact.

If this deterministic test fails, do not proceed directly to a dedicated writer task; first inspect whether the failure is caused by insufficient queue capacity, pressure-mode ordering, or an unexpected blocking operation during recovery.

## 6. External-Tester / TWAI Behavior

Production DEV3.2/R7.2 retains the DEV3.1/R7.1 session-latched ownership policy:

```text
externalTesterOwnsSession = true
```

once positively detected.

While latched:

- CYD diagnostic TX remains software-inhibited;
- passive logging/display remain available;
- no same-session automatic timeout re-enables diagnostic TX;
- TWAI is not automatically restarted/reconfigured solely because the external tester is present;
- `postLatchDiagnosticTxAttempts` and `postLatchDiagnosticTxFrames` must remain zero.

Do not force production firmware into true LISTEN_ONLY merely to address the Autel bus-error storm. S0218/S0219 show that true LISTEN_ONLY does not remove the phenomenon.

## Validation Matrix

### Production field builds

Test both accepted DEV3.2 and R7.2 builds at 25 MHz on:

- Card A as the normal-storage control;
- Card B as the repeatable long-tail storage stress source.

At least one run per variant must include:

- cold START;
- warm START;
- normal driving/logging long enough to cross repeated periodic flush/checkpoint intervals;
- external Autel connection to verify ownership latch remains TX-silent;
- clean Android STOP.

### Stall-injection builds

Run the 650 ms one-shot validation on both physical CYDs before relying on random Card-B stalls for proof.

### Autel electrical/protocol track

The 500/250-kbit/s dual-listen test and waveform test remain independent of DEV3.2/R7.2 acceptance. Findings may inform a future diagnostic-observer revision, but they do not block storage-resilience release unless they reveal actual logger corruption.

## Acceptance Criteria

DEV3.2/R7.2 is field-testable only when all of the following are true:

1. Authoritative DEV3.1/R7.1 baseline package hashes match before edits.
2. Accepted queue capacity passes the explicit heap/largest-block gate on both variants.
3. 25 MHz remains the runtime-reported SD clock.
4. RAW batch remains 128.
5. TCB1/TVM1 compatibility tests pass.
6. The deterministic 650 ms stall produces zero queue drops on both variants.
7. Pressure mode enters above HIGH and does not clear until LOW.
8. Routine flush/checkpoint work is deferred/coalesced during pressure mode.
9. Normal work resumes after recovery without manual intervention.
10. External-tester latch produces zero post-latch CYD diagnostic TX attempts/frames.
11. NORMAL-mode production TWAI behavior is retained; no forced-LISTEN_ONLY regression is introduced.
12. START timing exposes all four measurable windows through steady state.
13. STOP finalization timing is durably recoverable from META.
14. STREAM_FILE_CLOSE exactly matches physical RAW record/byte counts.
15. META CRC/sequence/trailing-byte checks are clean.
16. SD/storage drops remain zero.
17. SESSION_CLOSE is clean after normal STOP.
18. Android/META CLOCK_SYNC pairing remains exact for captured field sessions.
19. Card-B field stress does not produce queue loss for any observed storage stall shorter than the validated 650 ms injection envelope.

## Deferred Escalations

Do not implement these in DEV3.2/R7.2 unless the approved architecture fails its acceptance tests:

- dedicated FreeRTOS SD writer task;
- separate filesystem mutex/ownership architecture;
- SdFat or alternate SD library migration;
- preallocation redesign;
- SD clocks above 25 MHz;
- RAW batch increase beyond 128;
- queue capacity above the accepted 1536 target without new memory analysis;
- automatic CAN bitrate switching;
- automatic TWAI mode switching in response to Autel bus-error count;
- graph/TFT feature expansion unrelated to pressure recovery.

## Failure Interpretation

If the 650 ms deterministic stall fails despite a successfully allocated 1536-entry queue, classify the failure before changing architecture:

1. Did the queue actually begin the stall substantially occupied?
2. Did the RX task continue accepting frames throughout the stall?
3. Did pressure mode begin immediately after the main loop resumed?
4. Did a second blocking filesystem/TFT/META operation occur before backlog recovery?
5. Was queue capacity genuinely exhausted at the observed bus rate?

Only after those questions are instrumented and answered should the design escalate to a dedicated writer task or larger buffering model.

## Release Position

DEV3.2/R7.2 is an acquisition-resilience milestone. It does not claim to cure the externally generated Autel/TWAI storm. Its success criterion is that the logger remains a trustworthy evidence recorder through known SD-card latency tails and diagnostic-observer disturbances while preserving exact session provenance and clean shutdown semantics.
