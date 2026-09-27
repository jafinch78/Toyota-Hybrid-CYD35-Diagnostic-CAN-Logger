# Simplified Capture Logger Design

Date: 2026-09-27

## Purpose

Refactor the ESP32 3.5-inch CYD logger so the embedded device spends its limited CPU, heap, SPI bandwidth, and filesystem resources on loss-resistant CAN acquisition, immediate diagnostic safety, BLE time synchronization, and minimal live display work. Move redundant decoding, transaction reconstruction, CSV/JSON generation, and human-readable reporting to the Windows Analyzer / Evidence Builder, where substantially more CPU, RAM, and storage are available.

The supported display/controller targets for this revision are:

- E32R35T resistive-touch 320x480 ST7796/XPT2046 CYD.
- Dorhea B0DLNJSSFW ESP32-WROOM-32 resistive-touch 320x480 CYD.

E32N35T is out of scope for this revision.

## Success Criteria

1. Raw CAN evidence is committed before derived decoding, display, metadata housekeeping, or nonessential filesystem activity.
2. No normal capture path creates `DECODED.CSV`, `DIAGNOSTICS.CSV`, `EXTERNAL_DIAGNOSTICS.CSV`, `SIGNALS.CSV`, `README.TXT`, `EVENTS.CSV`, `SYNC.CSV`, `MANIFEST.JSON`, or `CHECKPOINT.JSON` on the CYD.
3. The CYD session contains only authoritative raw CAN plus one compact append-only metadata stream and the open-session marker.
4. The Windows Analyzer / Evidence Builder can regenerate the removed human-readable artifacts from raw CAN plus compact metadata.
5. TFT remains at the validated 80 MHz SPI rate, but periodic full-page repainting is replaced by dirty-field updates.
6. BLE stop cannot close a session while already-received CAN frames remain queued for the current session.
7. External diagnostic traffic cannot race the logger diagnostic scheduler merely because RAW persistence now occurs before derived frame classification.
8. Capture observability improves: queue pressure, SD latency, loop latency, display latency, heap health, stack margin, and TWAI loss counters are recorded compactly without creating additional text files.
9. Wi-Fi file mode remains exclusive: logging stopped, session files closed, TWAI and BLE shut down before Wi-Fi allocation.

## Non-Goals

- No change to Toyota write/control safety policy.
- No arbitrary CAN transmit API.
- No live Wi-Fi during logging.
- No full-screen framebuffer or LVGL conversion.
- No attempt to raise SD clock until measurements justify it.
- No enlargement of the 1024-record application CAN queue until measured queue high-water data justifies it.
- No change to the 24-byte TCB1 CAN record layout in this revision.

## Current Problems Being Removed

The RC2 logger keeps six session streams open simultaneously: raw TCB, decoded CSV, logger diagnostics CSV, events CSV, BLE sync CSV, and external diagnostics CSV. It also periodically rewrites checkpoint JSON using temporary files and FAT rename/remove operations. Several streams repeat information already contained in TCB1.

The most expensive redundant behaviors are:

- Wide `DECODED.CSV` rows written every 100 ms.
- Per-frame `EXTERNAL_DIAGNOSTICS.CSV` formatting and writes.
- `DIAGNOSTICS.CSV` persistence of transactions whose request, response, and flow-control frames already exist in RAW.
- Once-per-second flushing of all six open streams.
- Five-second JSON checkpoint creation, flush, close, rename, and remove operations.
- Per-session static `README.TXT` and `SIGNALS.CSV` generation.
- Full 476x241 display clearing every 250 ms.
- BLE session-stop handling before the CAN application queue is drained.

## Session File Contract

A normal session becomes:

```text
/CANLOG/S####/
    RAW_000.TCB
    RAW_001.TCB        # only after normal raw rotation
    SESSION.META
    SESSION.OPEN       # present only while session is active / unclean
```

Additional `RAW_nnn.TCB` files may appear through existing raw rotation. No derived text artifact is required on the CYD.

### RAW_nnn.TCB

TCB1 remains authoritative bus evidence. The existing 16-byte header and packed 24-byte records remain unchanged:

- `uint64 time_us`
- `uint32 CAN_ID`
- `uint8 data[8]`
- `uint8 DLC`
- `uint8 extended`
- `uint8 RTR`
- `uint8 direction` (`0=RX`, `1=TX`)

Logger-generated diagnostic requests and ISO-TP flow-control transmissions continue to be inserted into RAW with `direction=1` so the PC can reconstruct the complete on-bus transaction chronology.

### SESSION.META

`SESSION.META` is an append-only binary stream for information that cannot be reconstructed reliably from CAN alone.

#### File header

The metadata file begins with a fixed header:

```c
struct MetaFileHeader {
    char magic[4];          // "TCM1"
    uint8_t version;        // 1
    uint8_t header_size;    // sizeof(MetaFileHeader)
    uint16_t reserved;
    uint32_t firmware_id;   // build/release identifier or hash-derived ID
    uint32_t board_id;      // enumerated E32R35T or DORHEA
};
```

#### Record framing

Every record is self-delimiting and independently validatable:

```c
struct MetaRecordHeader {
    uint16_t magic;         // 0x4D52
    uint8_t version;        // 1
    uint8_t type;           // MetaRecordType
    uint16_t payload_len;
    uint16_t flags;
    uint32_t sequence;
    uint64_t time_us;
};
// payload[payload_len]
// uint32_t crc32 over header + payload
```

The parser accepts records sequentially until the first incomplete or CRC-invalid tail record. A power loss therefore leaves prior records usable without filesystem rename gymnastics.

#### Required metadata record types

- `SESSION_START`: session number, firmware ID, board profile, start request timestamp, CAN bitrate, safety mode.
- `BLE_SYNC`: sequence, ESP receive timestamp, ESP send timestamp, source flag.
- `MARKER`: BLE/user marker ID and command sequence.
- `DIAG_STATE`: diagnostic enable/disable/reject reason.
- `EXTERNAL_TESTER`: first detection timestamp and request ID.
- `TWAI_EVENT`: bus-off, recovered, error-state change, or driver reconfiguration outcome.
- `SD_EVENT`: short write, raw rotation failure, flush failure, or low-space condition.
- `HEALTH`: compact periodic counters and performance instrumentation.
- `SESSION_STOP_REQUEST`: requested synchronized stop timestamp and command sequence/source.
- `SESSION_CLOSE`: clean/unclean flag, final raw timestamp, final counters, final raw file index.

Metadata events are queued in RAM and appended after RAW service. They must never preempt an immediately available RAW batch.

## Offline-Derived Artifacts

The PC processor becomes responsible for generating the familiar human-readable artifacts when requested:

- `DECODED.CSV`: regenerate by replaying RAW through the selected canonical decoder/database version.
- `DIAGNOSTICS.CSV`: reconstruct logger requests/responses/ISO-TP transactions from RAW, supplemented by META diagnostic state events for timeouts or internal rejection states.
- `EXTERNAL_DIAGNOSTICS.CSV`: reconstruct 7DF / 7E0-7E7 requests and 7E8-7EF responses from RAW.
- `EVENTS.CSV`: expand META event records.
- `SYNC.CSV`: expand META `BLE_SYNC` records.
- `CHECKPOINT.JSON`: produce from the last valid META `HEALTH` or `SESSION_CLOSE` record if a human-readable recovery report is desired.
- `MANIFEST.JSON`: synthesize using RAW/META contents, firmware mapping, board mapping, capture counters, and processor version.
- `SIGNALS.CSV`: export from the canonical decoder/database used during processing, not from embedded firmware.
- `README.TXT`: generate as packaging documentation on the PC if retained for compatibility.

The processor must label regenerated artifacts as derived and preserve the source firmware ID, metadata version, and decoder/database version.

## External Diagnostics Simplification

External diagnostic detection remains active in firmware only for immediate safety and UI state. The CYD no longer writes `EXTERNAL_DIAGNOSTICS.CSV`.

The high-priority CAN receive task will continue to inspect received frames for external diagnostic request IDs. On detection it immediately updates a shared `externalTesterLastUs` / `externalTesterActive` interlock before normal queue processing.

Both `serviceDiagnosticScheduler()` and `transmitCAN()` must refuse logger-originated diagnostic transmission while that interlock is active. This ensures moving frame classification behind RAW persistence cannot introduce a collision window.

The application loop may later classify and append a compact `EXTERNAL_TESTER` META record, but that record is informational; the interlock itself is set in the receive path.

## Logger Diagnostics Simplification

Live diagnostic request scheduling and ISO-TP reassembly remain in firmware because they are required to:

- enforce the fixed read-only whitelist;
- send flow control with low latency;
- decide when a transaction is complete or timed out;
- update live display values;
- prevent overlapping requests.

`DIAGNOSTICS.CSV` is removed. Requests, responses, and logger flow-control frames remain reconstructible from RAW. Internal-only outcomes such as timeout, user disable, validation rejection, or bus-off are represented as compact META records.

## Main Capture Pipeline

### High-priority CAN RX task

The CAN receive task remains pinned at high priority and performs only low-latency operations:

1. Receive TWAI frame.
2. Timestamp immediately.
3. Update received-frame counters.
4. Detect an external diagnostic request and assert the diagnostic-transmit interlock if applicable.
5. Queue the frame into the application RAW queue without waiting.
6. For logger diagnostic responses, perform the existing immediate ISO-TP first-frame flow-control transmit before TFT or SD work can delay it.
7. Queue required diagnostic-response frames into the diagnostic reassembly queue.

No filesystem or TFT work is allowed in this task.

### Main loop priority order

The logger-mode main loop uses this order:

1. Read critical command/state flags without performing expensive session close work.
2. Drain up to the current 128-frame application batch.
3. Commit the batch to RAW in one contiguous write.
4. Process the same in-RAM frames for vehicle fingerprinting, passive live decodes, external tester UI state, and derived in-memory values.
5. Drain/reassemble diagnostic responses and update live values.
6. Service pending compact META records.
7. Run diagnostic scheduler and TWAI health handling.
8. Sample touch / process UI commands.
9. Perform a dirty TFT update if due and if queue pressure permits.
10. Perform periodic RAW/META durability flush only after capture work is serviced.
11. Yield briefly.

This explicitly establishes the priority hierarchy:

`CAN evidence > diagnostic safety > metadata > display > housekeeping`.

## Synchronized Start and Stop Semantics

A BLE stop command must no longer call `stopLogging()` immediately from `serviceBleSync()`.

Instead it sets:

- `stopPending = true`
- `stopRequestUs = command.receiveUs`
- source / sequence metadata

The main loop then drains and commits already-received CAN data, appends the stop-request META record, finalizes pending metadata, writes `SESSION_CLOSE`, flushes RAW/META, closes files, and removes `SESSION.OPEN` for a clean stop.

The close record contains both the requested stop timestamp and the final persisted RAW timestamp. Offline processing may clip or label frames after the requested synchronized boundary without losing evidence.

BLE start similarly records `startRequestUs`. Frames with timestamps earlier than the accepted start boundary must not be silently attributed to the new session. The implementation may drain/discard pre-start queue residue before opening the session or filter by timestamp; whichever implementation is chosen must be covered by tests.

## TFT Design

The validated TFT write frequency remains 80 MHz for E32R35T and Dorhea.

The normal logger UI stops clearing the large content area every 250 ms. Each page is divided into fixed dynamic fields. Static labels and outlines are drawn on page entry. For each dynamic field the firmware stores the last rendered value/state and redraws only when the rendered content changes.

Requirements:

- Page transition performs one full page redraw.
- Dynamic numeric/status fields use fixed `char[]` buffers and `snprintf`, not repeated temporary `String` concatenation.
- Buttons redraw only when state/color/text changes.
- Display update may be deferred under RAW queue pressure.
- Wi-Fi maintenance mode may retain independent full-screen refresh behavior because TWAI logging is stopped before that mode starts.
- No full-screen RGB565 framebuffer is allocated.

## Touch Design

Both supported boards are resistive-touch configurations. Existing validated calibrations remain board-specific.

Touch polling must not become higher priority than RAW service. Where the board's touch IRQ line is available and validated, the firmware may gate `getTouch()` calls with the IRQ level; correctness of the existing touch path takes precedence over adding an interrupt-driven implementation in this revision.

## File Descriptor and SD Policy

The target capture-time open files are only:

- current `RAW_nnn.TCB`;
- `SESSION.META`.

`SESSION.OPEN` is created and closed immediately; it does not remain as an open descriptor.

`SD_MAX_OPEN_FILES=5` becomes the first bench candidate because the six persistent streams are removed. It is accepted only after BLE + SD + CAN queue allocation and session start/stop testing on actual hardware. If five proves insufficient for temporary Wi-Fi or allocator operations, increase only to the minimum measured requirement.

The initial SD SPI clock remains 4 MHz. The new instrumentation is used to benchmark 4, 10, and 20 MHz with the actual capture cards in a later measured step. Average throughput alone is not sufficient; maximum RAW write/flush latency and queue high-water are the deciding metrics.

## Durability Policy

The firmware separates throughput writes from durability checkpoints.

- RAW data is written in contiguous batches.
- META data is appended in compact batches after RAW service.
- A periodic durability flush occurs only after the RAW queue has been serviced.
- Flush frequency remains conservative for the first implementation and is instrumented; it must not flush multiple redundant streams because only RAW and META remain open.
- Clean session stop forces final RAW/META flush before close.

## Instrumentation

Instrumentation must be low-overhead and primarily aggregated in RAM. Periodically append a compact `HEALTH` META record containing at least:

- application CAN queue current depth and high-water;
- `canQueueDrops`;
- diagnostic queue drops;
- TWAI RX missed count;
- TWAI RX overrun count;
- TWAI bus error count;
- raw write count;
- raw write maximum microseconds;
- raw write cumulative microseconds or average-ready sum/count;
- RAW/META flush count and maximum microseconds;
- main-loop maximum latency;
- TFT dirty-render count and maximum microseconds;
- current free heap;
- largest free heap block;
- minimum free heap;
- CAN RX task stack high-water;
- loop task stack high-water where available;
- SD short-write count / estimated dropped records;
- current raw file index.

No separate instrumentation CSV is created on the CYD.

## Queue-Pressure Load Shedding

The 1024-record application CAN queue remains unchanged initially.

The implementation tracks queue high-water and uses queue pressure only to defer nonessential work. It must never intentionally discard RAW frames to maintain UI responsiveness.

Initial behavior:

- RAW drain/write remains unconditional while logging is active.
- TFT refresh may be skipped when the queue is materially occupied.
- periodic health/checkpoint metadata may be deferred until pressure drops;
- human-readable derived output no longer exists to consume time;
- only queue-full conditions increment RAW drop counters.

Thresholds should be constants and verified by tests/bench instrumentation rather than hidden magic numbers.

## Session Allocation

The deletion-safe `MONOTONIC_V1` session allocator remains. NVS plus SD high-water/session directory scanning behavior remains unless profiling proves it affects active capture, because allocation occurs before capture starts.

The session counter files are not part of the active session stream and are not considered capture-time redundancy.

## Wi-Fi Maintenance Mode

Existing exclusive Wi-Fi design remains:

1. logging must be stopped;
2. session files are closed;
3. CAN RX task and TWAI driver are stopped;
4. CAN/diagnostic queues are released;
5. BLE is deinitialized and queues released;
6. Wi-Fi AP and HTTP file services are then allocated.

Wi-Fi ZIP/download code must tolerate the simplified session file set. PC-derived files are not required to exist on the card.

## Analyzer / Evidence Builder Changes

The Windows processor must add support for the simplified capture package before the firmware revision becomes the preferred vehicle release.

Required processor behavior:

1. Detect `SESSION.META` / metadata format version 1.
2. Parse metadata records with CRC validation and tolerate an incomplete final record after power loss.
3. Read all TCB1 raw files in chronological order.
4. Reconstruct logger-originated diagnostics from direction-marked request/response/flow-control frames plus META internal-outcome events.
5. Reconstruct external diagnostics from RAW.
6. Regenerate decoded signal tables using the selected canonical decoder/database rather than trusting embedded decoded CSV.
7. Rebuild sync tables from META BLE records and combine them with Android `CAPTURE_SYNC.json` as today.
8. Regenerate manifest/checkpoint/event CSV/JSON artifacts for compatibility when requested.
9. Preserve provenance: firmware ID, board profile, metadata version, processor version, decoder/database version, CRC/truncation status, and RAW drop/health counters.
10. Continue accepting all existing v2.3/v2.4/v2.5 legacy session packages.

## Compatibility and Migration

This is a new capture-package variant, not an in-place reinterpretation of legacy files.

- TCB1 remains unchanged.
- Existing legacy sessions remain readable.
- New firmware does not require old CSV files to be present.
- The processor must branch on package metadata and/or `SESSION.META` presence rather than assuming old files are missing due to corruption.
- Wi-Fi file browser lists the simplified files without fabricating derived artifacts on-device.

## Test-Driven Implementation Requirements

Before implementation changes, tests must be added for the new behavior.

### Host / pure logic tests

- META record encode/decode round trip.
- CRC rejection and recovery to last valid record after truncated tail.
- External diagnostic request/response reconstruction from TCB frames.
- Logger diagnostic transaction reconstruction from direction-marked RAW frames.
- Session start/stop boundary filtering rules.
- Dirty-display state comparison logic where extractable as pure functions.
- Health counter aggregation and high-water behavior.

### Firmware/static tests

- Forbidden capture files are absent from the new session-start path.
- only RAW and META persistent `File` objects remain for active capture.
- main loop calls RAW persistence before frame-derived SD/meta work.
- BLE stop sets pending finalization rather than directly closing the session.
- `transmitCAN()` and diagnostic scheduler enforce the external tester interlock.
- E32N35T references are removed from the new firmware target/profile selection.
- TFT remains configured at 80 MHz.
- full periodic 476x241 logger-page clear is absent from normal dirty-update path.

### Bench validation

On both E32R35T and Dorhea:

- Arduino IDE build with the documented ESP32 core and TFT_eSPI setup.
- boot with and without microSD;
- BLE allocation/startup;
- start logging, CAN idle, CAN active, clean stop;
- BLE synchronized start/stop under active traffic;
- repeated page/touch operation during logging;
- external diagnostic tester present while logger diagnostics are off;
- logger read-only diagnostics where supported, including multi-frame ISO-TP;
- forced unclean power removal followed by PC metadata recovery;
- Wi-Fi file mode entry, list, individual file transfer, ZIP transfer, deletion, restart;
- confirm no CAN logging service remains active in Wi-Fi mode;
- compare queue/drop/latency instrumentation against RC2 under the same capture conditions.

Acceptance requires zero new queue drops attributable to the refactor, successful RAW/META recovery after unclean shutdown, successful PC regeneration of removed derived artifacts, and no regression of the diagnostic safety boundary.

## Implementation Staging

The implementation should proceed in this order:

1. Add host tests and META format implementation.
2. Add Analyzer / Evidence Builder support for RAW + META while retaining legacy package support.
3. Introduce simplified firmware file contract and remove redundant live CSV/static artifacts.
4. Implement raw-first loop ordering and pending stop/start finalization.
5. Add external tester hard interlock to scheduler/transmit path.
6. Add instrumentation and compact health records.
7. Implement 80 MHz dirty-field display updates and fixed-buffer formatting.
8. Reduce SD open-file reservation to the measured minimum candidate and verify BLE memory headroom.
9. Run host tests, Arduino compile, and both-board bench validation before designating the new firmware as preferred over RC2.

## Release Boundary

RC2 remains the rollback / known vehicle-capture baseline until the simplified firmware and updated processor both pass host tests and actual E32R35T + Dorhea bench validation. The new branch must not silently replace RC2 merely because it compiles.
