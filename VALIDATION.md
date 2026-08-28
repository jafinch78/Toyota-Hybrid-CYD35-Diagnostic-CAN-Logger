# v2.3 validation basis

This firmware revision was informed by the supplied captures, while preserving
the v2.2 TCB1 binary record layout.

## Observed capture results

- Three 2007 Camry Hybrid sessions contained 175,188 raw records. Representative
  high-rate identifiers showed no gaps larger than 2.2 times their normal period.
- The 2004 Prius session contained 196,273 raw records, 246 transmitted frames,
  157 successful diagnostic transactions, one timeout, and no negative response.
- Across 87 Prius first-frame/flow-control pairs, observed flow-control latency
  was 12.022 ms median, 61.515 ms at p95, and 173.305 ms maximum.
- The single timeout followed the 173.305 ms flow-control delay. v2.3 therefore
  sends flow control in the high-priority receive task instead of the SD/display
  loop.

## Camry passive candidates

| Signal | CAN ID and bytes | Candidate mapping | Evidence |
|---|---|---|---|
| Gear | 0x120 byte 5 low nibble | 0=P, 1=R, 2=N, 3=D | PROBABLE |
| Gear redundant | 0x2D0 byte 2 | 01=P, 02=R, 04=N, 10=D | PROBABLE |
| Engine RPM | 0x2C4 bytes 0:1, big-endian | direct rpm | PROBABLE |
| Engine coolant | 0x3B9 byte 0 | degrees C, converted to F | PROBABLE |

These mappings are activated only after the passive fingerprint selects the
Camry Hybrid Gen 1 profile. They do not authorize diagnostic requests or control
commands. More labeled drives are required before promotion to CONFIRMED.

## Safety boundary

The firmware contains passive decoding plus a fixed Prius Gen 2 read-only
diagnostic whitelist. It contains no fan override, actuator, write, clear, reset,
coding, SD erase, or SD format command. Camry operation is passive-only.
