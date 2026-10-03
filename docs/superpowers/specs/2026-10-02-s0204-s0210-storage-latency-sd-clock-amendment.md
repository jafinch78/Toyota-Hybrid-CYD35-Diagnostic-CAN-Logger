# DEV3.1 / DIAG4 R7.1 S0204-S0210 Storage-Latency and SD-Clock Amendment

Date: 2026-10-02

This amendment extends `2026-10-02-dev3-1-diag4-r7-1-start-perf2-design.md` using the S0204-S0210 field batch and supersedes only the parts of that design that prohibited any SD-clock experiment.

## New Field Evidence

The S0204-S0210 cross-flash batch separates two distinct failure classes:

1. TWAI bus-error storms, reproduced by S0204 but not deterministically by physical CYD or DEV3.0 alone.
2. Main-loop/storage stalls that can fill the application queue without any TWAI bus error, demonstrated by S0210.

S0206 is the strongest positive control: DEV3.0 on the alternate CYD logged approximately 4.89 million RAW records over approximately 48.6 minutes with zero queue drops, zero SD drops, one TWAI error, clean rotations, and clean close.

S0204 accumulated approximately 182,246 TWAI errors with zero queue drops and clean close. Its error escalation began before the five-second external-tester timeout re-enabled CYD diagnostics, so auto-resume is not established as the storm initiator. The five-second ownership rule nevertheless remains unsafe because it can resume CYD transmissions inside a logically continuing external-tester workflow.

R7 sessions S0207-S0210 reached the 768-entry application queue limit. S0207 shows a cold/first-start effect, while S0208-S0210 have substantially shorter START latency. S0210 contains an isolated approximately 323 ms RAW timestamp gap and approximately 540 additional queue drops with zero TWAI bus errors. This is treated as a separate synchronous-stall problem rather than as a CAN electrical error.

## Revised START-PERF2 Requirements

START-PERF2 validation must distinguish:

- first START after boot/cold state;
- subsequent warm STARTs;
- `loggingActive -> first persisted RAW`;
- command -> first persisted RAW;
- queue high-water/drop count attributable to START.

Do not claim START-PERF2 success from warm repeated starts alone.

## Storage-Latency Telemetry

Add bounded aggregate timing around synchronous SD/filesystem operations, with no Serial formatting in the hot path.

At minimum measure:

- RAW batch write duration: current/total/max/count;
- RAW flush duration: current/max/count;
- META flush duration: current/max/count;
- combined `flushLogFiles()` duration: current/max/count;
- `SD.usedBytes()` duration: current/max/count;
- `SD.cardSize()` duration when called;
- session directory creation duration;
- RAW open/header duration;
- META open/header duration;
- SESSION.OPEN create/write/close duration;
- RAW rotation close/open duration;
- clean STOP final flush/close duration.

Maintain threshold counters for synchronous stalls over 25, 50, 100, and 250 ms. Capture queue depth/high-water immediately before and after the longest class of operations where practical.

These metrics must be written through the normal bounded TVM1 metadata path after RAW priority permits. Instrumentation must not add blocking writes to CAN RX or BLE callbacks.

## SD Frequency Policy

The 4 MHz value remains the primary DEV3.1/R7.1 baseline because all S0201-S0210 evidence was collected at 4 MHz and changing START lifecycle, external-tester ownership, BLE observability, and storage timing simultaneously with the SD clock would weaken causal interpretation.

However, 10 MHz is now an explicitly authorized controlled A/B experiment.

### Baseline packages

First build and validate normal DEV3.1 and R7.1 packages at:

```text
SD_SPI_FREQUENCY = 4000000
```

All acceptance criteria from the main design apply.

### 10 MHz A/B packages

After the exact 4 MHz source passes source/host verification, produce otherwise-identical A/B builds whose only intentional change is:

```text
SD_SPI_FREQUENCY = 10000000
```

The 10 MHz builds must carry an unmistakable build/version suffix such as `-SD10M-A_B` and must not replace the 4 MHz baseline packages until field evidence supports promotion.

### Compare 4 MHz vs 10 MHz

Hold constant for each comparison:

- CYD board;
- microSD card;
- CAN transceiver/cable assembly;
- firmware source commit except the SD clock constant/build label;
- queue length;
- RAW batch size;
- vehicle and test procedure;
- diagnostic/passive mode;
- Android controller where practical.

Compare:

- mount/start reliability;
- command -> first RAW;
- `loggingActive -> first RAW`;
- RAW write average/max latency;
- flush average/max latency;
- `SD.usedBytes()` latency;
- queue high-water and drops;
- RAW timestamp gaps;
- SD short writes/errors;
- STREAM_FILE_CLOSE accounting;
- SESSION_CLOSE/SESSION.OPEN behavior;
- TWAI errors, to detect an unexpected system-level interaction.

## Promotion Rule for 10 MHz

10 MHz may become the new default only after repeated physical tests on both established CYD/microSD pairings show:

- no mount/open/close reliability regression;
- zero structural RAW/META corruption;
- zero increase in SD short writes or storage drops;
- exact close accounting;
- equal or better START and synchronous-storage latency distribution;
- no new reset pattern;
- no evidence that higher SPI clock creates board/card-specific instability.

If 10 MHz improves sequential writes but the S0210-like >250 ms stalls remain, treat filesystem/flush behavior as the remaining bottleneck rather than raising the clock again.

No 20/25/40 MHz experiment is part of DEV3.1/R7.1. Any higher clock requires a separate controlled revision after 10 MHz evidence.

## External-Tester Interpretation Update

Retain the session-latched external-tester ownership design. Its purpose is now explicitly preventive: S0204 shows the five-second auto-resume is not proven to initiate every TWAI storm, but the timeout still allows CYD diagnostic TX to restart while the tester session is logically continuing. Once external tester ownership is established, CYD diagnostic TX remains suppressed until logger STOP/new session.

## Display Scope

S0204-S0210 do not justify moving BLOCKS/TREND optimization forward. S0206 exercised those expensive pages during a long, near-zero-error capture. Graph-page optimization remains the following display-performance revision.
