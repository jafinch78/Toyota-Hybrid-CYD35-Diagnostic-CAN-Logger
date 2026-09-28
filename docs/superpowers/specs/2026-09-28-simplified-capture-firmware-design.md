# Simplified Capture Firmware Design

Date: 2026-09-28
Status: Approved design consolidation for implementation planning

## Provenance and precedence

This document consolidates the previously approved `Simplified Capture Logger Design` and `Simplified Capture Offline Contract Alignment` from the earlier `feature/logger-simplified-capture-v2.6` work onto the authoritative `feature/native-session-preprocessor-impl` line. It does not introduce a new product direction.

The following current-branch contracts are normative and supersede the early draft metadata framing in the older design:

1. `docs/TOYOTA_VEHICLE_BUS_CAPTURE_CONTRACT.md`
2. `docs/TVM1_SESSION_META_BINARY_SPEC.md`

In particular, the obsolete early `TCM1` header/record sketch must not be implemented. Firmware must emit canonical bus-neutral `TVM1` exactly as defined by the current contracts.

The offline-preprocessor authorization prerequisite has passed. `windows/ToyotaVehicleBusSessionPreprocessor/validation/BUILDER_CAMPAIGN_20260928.json` records S0141, S0149, and S0128 RAW/Builder gates as PASS and the Windows 10 1607 runtime gate as PASS. Analyzer RC7/RC8 smoke is not an authorization input.

## Goal

Create logger v2.6.0 from the validated v2.5.0-rc.2 firmware baseline while reducing embedded capture work to authoritative RAW acquisition, compact TVM1 metadata, diagnostic safety, BLE synchronization, minimal live decoding, and efficient display updates.

RC2 remains the rollback/reference firmware until v2.6.0 passes host/static tests, Arduino compilation, and bench testing on both supported boards.

## Supported boards

Only these board targets are in scope:

- `E32R35T_TOUCH`: 3.5-inch ESP32-32E ST7796 + XPT2046 resistive touch.
- `DORHEA_B0DLNJSSFW_TOUCH`: existing Dorhea ESP32-WROOM-32 3.5-inch resistive-touch profile.

E32N35T is not a v2.6.0 target.

The validated TFT write clock remains `80000000` Hz for both supported profiles.

## Immutable evidence and safety contracts

- TCB1 CAN framing remains unchanged: 16-byte header plus packed 24-byte `CapturedFrame` records.
- `direction=0` remains RX and `direction=1` remains logger TX.
- CAN bitrate remains 500 kbit/s.
- Raw rotation remains 25 MiB initially.
- The normal logger starts TWAI listen-only.
- The existing read-only diagnostic whitelist remains limited to service `0x01` and `0x21`; no write/control/clear/reset/coding command is added.
- Logger ISO-TP flow-control timing remains in the high-priority receive path.
- Wi-Fi remains exclusive maintenance mode and cannot coexist with CAN logging.

## Native session files

Normal active capture is reduced to:

```text
/CANLOG/S####/
    RAW_000.TCB
    RAW_001.TCB       # only after rotation
    SESSION.META      # canonical TVM1
    SESSION.OPEN      # marker only while active / after unclean close
```

At capture time only the current RAW file and `SESSION.META` remain persistently open. `SESSION.OPEN` is created/closed as a marker and is not held as a persistent descriptor.

The firmware no longer creates or continuously writes these reconstructible products:

- `DECODED.CSV`
- `DIAGNOSTICS.CSV`
- `EXTERNAL_DIAGNOSTICS.CSV`
- `EVENTS.CSV`
- `SYNC.CSV`
- `SIGNALS.CSV`
- `README.TXT`
- `MANIFEST.JSON`
- `CHECKPOINT.JSON`

The validated offline preprocessor reconstructs the Builder-compatible legacy package from RAW + TVM1.

## TVM1 responsibilities

The firmware implements the canonical `TVM1` file header, CRC-32/ISO-HDLC, record envelope, stream IDs, and record payloads from `docs/TVM1_SESSION_META_BINARY_SPEC.md`.

The first v2.6.0 firmware registers one CAN stream (stream ID 1, stream type CAN, raw format TCB1, RX/TX direction capability, nominal rate 500000). The schema remains bus-neutral; code must not make the file format CAN-only or prevent future BTH/AVC-LAN streams.

Required records for normal CAN capture include:

- `SESSION_START`
- `STREAM_REGISTER`
- `STREAM_START`
- `STREAM_FILE_OPEN` / `STREAM_FILE_CLOSE`
- `CLOCK_SYNC`
- `USER_MARKER`
- `HEALTH_SNAPSHOT`
- `STREAM_COUNTERS`
- `STORAGE_HEALTH`
- `EVENT`
- `DIAGNOSTIC_STATE`
- `BUS_STATE`
- `STREAM_STOP`
- `SESSION_CLOSE`

Metadata is append-only. It is buffered/queued in RAM and serviced after immediately available RAW work. A truncated final metadata record after power loss must leave earlier records usable by the already-validated offline parser.

## Capture pipeline

### High-priority CAN RX task

The RX task performs only latency-sensitive work:

1. Receive TWAI frame.
2. Timestamp immediately.
3. Update frame/counter state.
4. Detect external diagnostic request traffic and assert the shared external-tester transmit interlock immediately.
5. Queue the frame for RAW persistence without waiting.
6. If the frame is a logger diagnostic ISO-TP first frame, send required flow control using the existing fast path.
7. Queue diagnostic-response information needed by the in-RAM diagnostic state machine.

No filesystem formatting/writes or TFT work is added to the RX task.

### Main logger loop priority

The normal loop follows this order:

1. Consume critical command/state flags without performing expensive close operations.
2. Drain up to the existing 128-frame application batch.
3. Persist the batch to RAW using the existing contiguous binary write.
4. Process the same in-memory batch for fingerprinting, passive live values, and UI state.
5. Drain/reassemble diagnostic responses and update live values.
6. Append pending compact TVM1 records.
7. Service diagnostic scheduler and TWAI health.
8. Process touch/UI commands.
9. Perform dirty TFT updates if due and queue pressure permits.
10. Perform periodic RAW/TVM1 durability flush only after capture work is serviced.
11. Yield.

Priority is `CAN evidence > diagnostic safety > metadata > display > housekeeping`.

## Start/stop session boundaries

BLE STOP must not directly close session files. It records a pending stop request (`stopPending`, request timestamp, source/sequence). The main loop drains and persists already-received frames, writes the stop/event/final counter metadata, writes orderly `STREAM_STOP` and `SESSION_CLOSE`, flushes RAW + TVM1, closes files, and removes `SESSION.OPEN`.

The close evidence retains the requested synchronized stop boundary and the final persisted RAW time through canonical event/state/counter records so offline processing can label or clip the tail without deleting evidence.

BLE START records the accepted start boundary. Pre-start queue residue must not silently enter the new session; implementation must explicitly drain/discard residue before opening the session or timestamp-filter it, with tests pinning the chosen behavior.

## External diagnostics and logger diagnostics

External diagnostic detection is retained only for immediate safety/UI state; there is no live external diagnostic CSV.

The RX task sets the external-tester interlock before main-loop RAW/derived processing. Both the diagnostic scheduler and `transmitCAN()` refuse logger-originated diagnostic transmissions while the interlock is active. The established 5000 ms external tester hold policy remains initially.

Logger diagnostics remain live in RAM: whitelist validation, scheduling, ISO-TP reassembly, low-latency flow control, overlap prevention, and live value updates are still required. RAW contains request/response/flow-control evidence; internal outcomes not fully inferable from bus traffic are recorded with `DIAGNOSTIC_STATE` / `EVENT` TVM1 records.

## SD/file policy

- SD SPI remains 4 MHz initially.
- `SD_MAX_OPEN_FILES=5` is a bench-test candidate, not an assumed production fact.
- The 1024-record application CAN queue remains unchanged initially.
- The 128-record main-loop batch remains unchanged initially.
- File descriptor, SD clock, queue size, and batch size are changed only from measured evidence, not by assumption.
- Clean stop forces final RAW + TVM1 flush.
- Periodic flush occurs only after RAW service and no longer flushes redundant streams.

## Instrumentation and load shedding

Low-overhead aggregate instrumentation is stored in RAM and periodically emitted through `HEALTH_SNAPSHOT`, `STREAM_COUNTERS`, and `STORAGE_HEALTH`. It includes at minimum:

- CAN queue current depth/high-water and drops;
- diagnostic queue drops;
- TWAI missed/overrun/bus-error/bus-off/recovery counters;
- RAW write count, cumulative/average and maximum latency;
- RAW/TVM1 flush count and maximum latency;
- maximum main-loop latency;
- TFT dirty render count and maximum render latency;
- free heap, largest free block, minimum free heap;
- CAN RX task and main task stack high-water where available;
- SD short-write/write/flush/open failures;
- current RAW file index.

Queue pressure may defer TFT rendering and noncritical periodic metadata/housekeeping. It must never intentionally discard RAW data to preserve UI responsiveness.

## Display and touch

Normal logger pages use dirty-field rendering:

- page entry draws static labels/outlines once;
- each dynamic field caches its last rendered text/state;
- changed fields clear/redraw only their own fixed rectangles;
- buttons redraw only when text/state/color changes;
- fixed `char[]` + `snprintf` replace hot-path temporary `String` formatting where practical;
- periodic full 476x241 clearing is absent from steady-state logger display;
- no full-screen RGB565 framebuffer is allocated;
- Wi-Fi maintenance screens may retain independent full refresh behavior because logging is already stopped.

Touch remains lower priority than RAW. Existing board-specific calibration is preserved. IRQ-gating may be used only when validated for the selected board profile; it is not required for the first v2.6.0 implementation.

## Wi-Fi maintenance mode

Preserve the RC2 exclusive shutdown sequence: logging stopped/files closed, CAN RX/TWAI stopped, CAN/diagnostic queues released, BLE deinitialized/queues released, then Wi-Fi AP/HTTP resources allocated. Exit remains restart-based. File listing/ZIP/download code must tolerate the reduced native session file set.

## Implementation baseline and release boundary

Implementation starts from the exact validated RC2 sketch:

`release/logger-v2.5.0-rc.2-dorhea-touch`

`firmware/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0/Toyota_Hybrid_CYD35_Diagnostic_CAN_Logger_v2_5_0.ino`

baseline blob SHA: `bbc7421da2bfc684324123b3232895cdcfd6c23d`

The authoritative preprocessor branch currently contains only firmware through v2.4.2, so RC2 must be imported/copied into a new v2.6.0 firmware directory on the authoritative development line rather than modifying v2.4.2.

v2.6.0 must not replace RC2 as rollback/preferred vehicle firmware merely because host tests or compilation pass. Promotion requires physical bench validation on both E32R35T and Dorhea, including SD, BLE, touch, session start/stop, external tester interlock, read-only diagnostics/ISO-TP, unclean recovery, and exclusive Wi-Fi file mode.