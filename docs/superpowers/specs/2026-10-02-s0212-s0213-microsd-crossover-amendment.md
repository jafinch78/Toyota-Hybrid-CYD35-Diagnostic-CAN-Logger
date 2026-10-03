# DEV3.1 / DIAG4 R7.1 S0212-S0213 microSD Crossover Amendment

Date: 2026-10-02

This amendment extends:

- `2026-10-02-dev3-1-diag4-r7-1-start-perf2-design.md`
- `2026-10-02-dev3-1-diag4-r7-1-shared-can-branch-amendment.md`
- `2026-10-02-s0204-s0210-storage-latency-sd-clock-amendment.md`

It incorporates the S0212/S0213 card-only crossover while keeping each physical CYD and firmware assignment unchanged from S0204-S0210.

## Controlled Crossover Definition

The S0212/S0213 experiment changed only the microSD card between the two already cross-flashed logger pairings.

- S0212: newer physical CYD + DIAG4 R7 / 768 + Card A, where Card A is the 31,281,119,232-byte card previously used with DEV3.0 in S0204-S0206.
- S0213: older physical CYD + DEV3.0 / 1024 + Card B, where Card B is the 31,914,983,424-byte card previously used with R7 in S0207-S0210.

The same CAN transceiver/cable assembly remains common to both logger paths.

## S0212 / S0213 Structural Result

Both sessions are structurally clean:

- valid/aligned TCB1 RAW;
- zero META CRC errors;
- zero META sequence errors;
- exact `STREAM_FILE_CLOSE` physical record/byte accounting;
- zero SD/storage drops;
- clean `SESSION_CLOSE`;
- exact Android/META `CLOCK_SYNC` pairing.

Therefore the observed differences are runtime/timing/TWAI phenomena rather than file-format corruption.

## New Evidence: Card-Associated but Non-Deterministic Behaviors

### Card A — TWAI storm association

Card A participated in two severe TWAI-error sessions across different CYDs and firmware branches:

- S0204: DEV3.0 on the older CYD, approximately 182,246 TWAI errors.
- S0212: R7 on the newer CYD, approximately 229,319 TWAI errors.

But Card A is not sufficient by itself to produce the storm:

- S0205: zero TWAI errors.
- S0206: one TWAI error across approximately 4.89 million RAW records and approximately 48.6 minutes.

Therefore do not label Card A defective. Treat it as associated with a repeatable susceptibility/interacting condition that crosses firmware and CYD boundaries.

S0212 independently repeats the S0204 ordering: the high-error escalation begins while CYD diagnostics remain suspended after external-tester detection and before the five-second quiet-time auto-resume. This further rejects timeout-based CYD diagnostic auto-resume as the initiating cause of every TWAI storm. The timeout remains unsafe and must still be replaced with session-latched external-tester ownership.

### Card B — synchronous filesystem tail-latency association

Card B repeats the long-tail storage/START behavior after moving from R7/newer CYD to DEV3.0/older CYD.

Prior Card B evidence:

- S0207: first/cold R7 START saturated the 768 queue.
- S0210: isolated approximately 323 ms RAW gap with approximately 540 additional queue drops and zero TWAI bus errors.

After crossover:

- S0213: DEV3.0/1024 START again reaches queue capacity and loses startup frames.
- S0213: a later approximately 68.640 ms RAW timestamp gap corresponds quantitatively to approximately 109 additional queue drops at the local approximately 1,558 frames/s rate.

This strongly supports filesystem/card-controller/internal-storage tail latency as the cause of those queue-loss stalls. It does not prove Card B is electrically bad or corrupt; S0210/S0213 remain structurally exact with zero SD drops.

## Important Negative Result: 1024 Queue Is Not the Root Fix

S0213 demonstrates that a 1024-entry application queue can still saturate when START/post-active synchronous filesystem work blocks RAW draining long enough.

Therefore:

- retain DEV3.1 = 1024 and R7.1 = 768 as controlled comparison constants;
- do not increase R7.1 queue size as the primary fix;
- reduce and instrument blocking START/post-start work first.

## Revised START Model

START-PERF2 must now treat startup as four distinct measurable windows:

```text
command accepted
    -> loggingActive
    -> first RAW persisted
    -> deferred START postamble complete
    -> steady-state acquisition
```

A build does not pass START-PERF2 merely because `loggingActive -> first RAW` meets the target if it then incurs a postamble stall that fills the queue.

### Required startup metrics

Persist enough monotonic timing and counters to reconstruct:

- command -> loggingActive;
- loggingActive -> first RAW persisted;
- first RAW -> postamble begin;
- postamble begin -> postamble complete;
- postamble complete -> steady-state declaration;
- queue depth/high-water and drop delta for each window;
- maximum RAW timestamp gap during the first 2 seconds;
- maximum synchronous main-loop/storage call during the first 2 seconds.

A startup-period drop counter should distinguish loss before first RAW from loss during deferred postamble.

## Deferred START Postamble Design

The deferred postamble must not remain a monolithic synchronous block.

Split it into bounded work items such as:

1. pending BLE/control META emission;
2. noncritical reset/audit reporting;
3. checkpoint/storage metadata;
4. deferred `NEXT_SESSION.TXT` mirror update;
5. exact free-space refresh only when required;
6. optional TFT/status refresh.

Rules:

- service at most one bounded postamble step per main-loop opportunity;
- RAW queue drain/persistence outranks every postamble step;
- skip/defer a step while queue pressure exceeds the established threshold;
- no `SD.usedBytes()` scan is allowed merely because START completed;
- exact free-space refresh occurs only in stopped/idle maintenance or a low-space safety fallback;
- every postamble step must have duration telemetry.

## `SESSION.OPEN` Timing Requirement

S0213 localizes a large part of the post-`loggingActive` delay to the same interval that includes `SESSION.OPEN` create/write/close.

Instrument separately:

- marker open/create duration;
- marker payload write duration;
- marker close/flush duration;
- total marker duration;
- queue depth immediately before and after marker handling.

`SESSION.OPEN` remains required. Do not remove or weaken the crash marker to improve START timing.

## Storage Timing Requirements

Retain the storage-latency instrumentation from the S0204-S0210 amendment and add explicit correlation fields for queue pressure/drop deltas.

At minimum measure:

- RAW write;
- RAW flush;
- META flush;
- combined flush service;
- `SD.usedBytes()`;
- `SD.cardSize()`;
- mkdir/session-directory creation;
- RAW open/header;
- META open/header;
- `SESSION.OPEN` open/write/close/total;
- RAW rotation close/open/header;
- each deferred START postamble step;
- clean STOP final flush/close.

Maintain >25, >50, >100 and >250 ms counters and retain the maximum duration plus queue depth before/after the maximum operation.

## 4 MHz -> 10 MHz A/B Order

The 10 MHz experiment remains authorized, but the crossover changes the preferred order.

### Card B first for performance isolation

Card B is the preferred first 4 MHz -> 10 MHz storage-performance A/B because its dominant observed pathology is storage/filesystem tail latency while TWAI errors remain comparatively low.

First establish the fully instrumented 4 MHz DEV3.1/R7.1 baseline. Then run the otherwise-identical 10 MHz build on the same CYD/Card B pairing.

Compare not just average write time, but:

- START tail latency;
- `SESSION.OPEN` latency;
- deferred-postamble latency;
- RAW/META flush maximums;
- >25/>50/>100/>250 ms counts;
- RAW timestamp gaps;
- queue drop deltas;
- mount/open/close reliability;
- exact RAW/META close accounting.

If average writes improve while >100/>250 ms tails remain, do not promote a higher SPI clock as the root fix.

### Card A second

Keep Card A at 4 MHz for the first instrumented reproduction because its severe TWAI-error behavior has now crossed CYD and firmware boundaries. Obtain the new TWAI/storage timing evidence before introducing the SD-clock variable.

Only after a clean/reproducible 4 MHz instrumented baseline should Card A receive the matching 10 MHz one-variable A/B.

## TWAI Investigation Implication

The crossover weakens simple explanations based on one CYD or one firmware branch.

Remaining leading classes include:

- an interaction involving Card A timing/power/current/noise or system load;
- vehicle/external-tester/protocol-identification timing;
- CYD power/local interface susceptibility that is excited only under some storage states;
- firmware scheduling/state interactions that are necessary in combination with another variable.

Do not infer that the microSD electrically causes CAN errors merely from association. The next firmware must correlate TWAI error onset with storage operation duration, queue pressure, diagnostic ownership state, and external-tester request timing so causal order can be tested.

## External Tester Ownership

No change to the approved latch behavior:

```text
externalTesterOwnsSession = true
```

once positively detected during logging, and CYD diagnostic TX remains blocked until STOP/new session.

S0212 further supports this as preventive isolation, but does not identify the latch as the TWAI-storm root fix.

## Acceptance Additions

DEV3.1/R7.1 field acceptance now additionally requires:

1. First/cold START and warm START are reported separately.
2. Startup losses are separated into pre-first-RAW versus deferred-postamble loss.
3. Maximum RAW gap during the first 2 seconds is recorded.
4. No single deferred START step may block RAW service unobservably.
5. `SESSION.OPEN` open/write/close timing is independently visible.
6. Card B 4 MHz baseline must demonstrate whether the known long-tail stalls remain after START-PERF2 restructuring.
7. 10 MHz remains a controlled A/B and cannot be promoted solely on average throughput.
8. Card A TWAI testing must correlate error onset against storage and external-tester timing before assigning a card-level electrical cause.

## Scope Control

Still deferred:

- BLOCKS/TREND rendering optimization;
- queue enlargement beyond the existing 1024/768 comparison;
- RAW batch increase beyond 128;
- SD clocks above 10 MHz;
- arbitrary diagnostic/CAN control;
- changes to TCB1 layout;
- changes to established decoder formulas unrelated to this runtime investigation.
