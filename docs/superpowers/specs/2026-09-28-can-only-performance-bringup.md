# CAN-only Performance Bring-up Before BTH Hardware

Date: 2026-09-28
Status: Approved staged validation

The SN75HVD12 BTH transceiver is not yet physically available. This does not block v2.6 acquisition work.

## Bring-up rule

The CAN+BTH firmware shall compile with the BTH subsystem present but disabled by default:

```cpp
constexpr bool ENABLE_BTH_CAPTURE = false;
```

When disabled:

- GPIO35 is not configured as a UART input by the logger;
- no UART driver, BTH event queue, BTH chunk queue, BTH task, or BTH file is allocated/opened;
- TVM1 registers only the CAN stream;
- `registered_stream_count` is 1;
- the TFT reports `BTH: DISABLED` rather than a false error state;
- Wi-Fi file transfer remains unchanged and simply has no `BTH_*.BTH` files to list;
- no BTH memory reservation is allowed to distort the CAN-only benchmark.

After the SN75HVD12 arrives, the same source is built with BTH enabled and the CAN-only result becomes the A/B reference for measuring BTH overhead.

## Immediate CAN-only performance baseline

Keep these variables fixed for the first comparison:

- CAN queue: 768 frames
- CAN batch: 128 frames
- CAN bitrate: 500 kbit/s
- SD SPI: 4 MHz
- same known-good CYD and microSD used for the strongest prior baseline when practical
- diagnostics OFF for the primary throughput run
- Wi-Fi OFF during logging
- BLE synchronization retained
- simplified native session output: TCB1 RAW + TVM1 SESSION.META + SESSION.OPEN marker during active/unclean state
- no on-device PLOT or legacy CSV/JSON generation
- fixed low-overhead logger integrity display

Do not combine SPI-host reassignment, SD clock increases, or other performance experiments with this first baseline. Those are separate A/B changes after the simplified logger establishes its own performance.

## Compare against historical baseline

Primary historical reference is the repeated SanDisk Ultra 32 GB / FAT32 / 16 KB cluster at approximately 1.43 k RAW records/s, with incoming CAN near approximately 1.68 k frames/s in representative sessions.

The new firmware must report enough telemetry to distinguish:

- TWAI receive rate;
- RAW persisted rate;
- application queue depth/high-water/drops;
- TWAI missed/overrun/errors;
- RAW write average/max latency;
- RAW flush max latency;
- loop max latency;
- free internal heap/largest block/minimum heap;
- BLE connection/sync state;
- clean versus unclean stop.

The key metric is session-relative `received -> persisted RAW` retention, not `sd_log_drops` alone.

## Test sequence

1. Boot without logging and verify no BTH resources are allocated.
2. Run ten START/STOP cycles with BLE control and verify clean close each time.
3. Run a sustained passive CAN capture long enough to reach steady-state SD behavior.
4. Repeat with the same CYD/card/vehicle conditions where practical.
5. Compare CAN retention, queue pressure, write latency, heap headroom, BLE stability, and session-open/close latency against RC2/DEV2.5 history.
6. Only after this baseline is stable, begin one-variable performance experiments such as SD clock or SPI-host mapping.
7. When SN75HVD12 hardware arrives, enable BTH and rerun the same test to quantify incremental BTH cost.

No vehicle-level claim of improvement is made until physical capture evidence is produced.