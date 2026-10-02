# DEV3.1 / DIAG4 R7.1 Shared CAN-Branch Amendment

Date: 2026-10-02

This amendment corrects Phase D of `2026-10-02-dev3-1-diag4-r7-1-start-perf2-design.md`.

## Corrected Known Hardware Fact

DEV/1024 and DIAG4/768 testing uses the same CAN transceiver/cable assembly. The CAN transceiver/cable is therefore already a controlled constant between those logger runs and must not be treated as a separate branch that can explain recurring DEV-versus-DIAG TWAI error asymmetry.

The previously proposed "swap only the CAN transceiver/cable branch" experiment is invalid for this setup and is superseded by this amendment.

## Revised Phase D: Board / Firmware / microSD Isolation

After DEV3.1/R7.1 passes the START, external-tester, BLE, and STOP gates, investigate any remaining TWAI asymmetry with controlled sequential tests using the same vehicle connection and the same CAN transceiver/cable assembly.

### D1 — Isolate CYD board hardware

Hold constant:

- exact firmware image;
- exact CAN transceiver/cable assembly;
- exact microSD card;
- vehicle/test point;
- diagnostic mode, preferably passive-only initially;
- test procedure and approximate duration.

Change only the CYD board.

Compare:

- TWAI bus errors;
- arbitration-lost events;
- RX missed/overrun counters;
- queue high-water and drops;
- reset/breadcrumb state;
- RAW integrity and timestamp gaps.

Interpretation:

- error tendency follows one CYD board -> board-level hardware, power, pin/interface, or board-specific resource behavior becomes the primary lead;
- error tendency does not follow the board -> proceed to firmware isolation.

### D2 — Isolate firmware/resource path

Hold constant:

- one CYD board;
- exact CAN transceiver/cable assembly;
- exact microSD card;
- vehicle/test point;
- passive/diagnostic operating mode;
- test procedure and duration.

Change only the firmware image/configuration under test.

Where practical, use a common passive-only diagnostic image first so queue size, active diagnostic polling, and TFT behavior do not obscure the basic TWAI comparison. Then introduce the DEV versus DIAG configuration differences individually or in a documented sequence.

Interpretation:

- error tendency follows firmware/configuration -> firmware scheduling, resource pressure, TWAI state handling, queue configuration, display workload, diagnostic activity, or another software-path difference becomes the primary lead;
- error tendency remains with the physical CYD despite firmware changes -> CYD board or its local power/interface path remains the stronger lead.

### D3 — Isolate microSD only if needed

The prior field runs use their respective established microSD cards, so microSD remains a potential indirect workload/timing variable even though it cannot directly create CAN electrical errors.

If D1/D2 remain ambiguous, hold the CYD, firmware, CAN transceiver/cable, vehicle procedure, and operating mode fixed and change only the microSD card. Compare SD write latency, queue pressure, timestamp gaps, and whether TWAI error onset correlates with storage stalls.

## Corrected Interpretation of Existing Field Evidence

Because the same CAN transceiver/cable assembly is used for both logger variants, the recurring DEV-versus-DIAG TWAI difference should not presently be attributed to separate CAN transceiver/cable branches.

The remaining plausible differentiators include:

- the individual CYD board;
- DEV versus DIAG firmware/resource behavior;
- the respective microSD card and resulting timing/load effects;
- diagnostic-active versus passive operating state;
- session timing and vehicle/bus conditions.

This correction does not change DEV3.1/R7.1 firmware acceptance criteria. The board/firmware/microSD isolation work remains a follow-on experiment after the revision itself passes its defined gates.
