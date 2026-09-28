# CAN + BTH Capture Firmware Design

Date: 2026-09-28
Status: Approved implementation delta

## Provenance and precedence

This specification extends `docs/superpowers/specs/2026-09-28-simplified-capture-firmware-design.md` and the normative bus-neutral `docs/TOYOTA_VEHICLE_BUS_CAPTURE_CONTRACT.md` after validation of `feature/native-session-preprocessor-impl`.

Where this document conflicts with the earlier simplified-capture design, this document controls the CAN+BTH build. The TVM1 binary contract remains unchanged.

## Goal

Produce an acquisition-focused CYD 3.5 firmware that prioritizes loss-resistant synchronized CAN and Toyota BTH capture, retains BLE synchronization, read-only diagnostics, and stopped-logger Wi-Fi file transfer, and removes archival/display work that can be reconstructed offline.

Normal native session output is:

```text
/CANLOG/S####/
    RAW_000.TCB
    RAW_001.TCB       # CAN rotation when required
    BTH_000.BTH       # BTH1 stream, when BTH is enabled
    BTH_001.BTH       # BTH rotation when required
    SESSION.META      # canonical TVM1
    SESSION.OPEN      # marker only while active / after unclean close
```

The validated offline preprocessor remains responsible for Builder-compatible CAN artifacts. BTH files are native auxiliary evidence and must never be disguised as CAN/TCB1.

## Hardware scope

Supported display/logger profiles remain:

- `E32R35T_TOUCH`
- `DORHEA_B0DLNJSSFW_TOUCH`

CAN remains:

- GPIO25 -> CAN transceiver TXD
- GPIO32 <- CAN transceiver RXD
- 500 kbit/s TWAI

BTH receive-only interface is fixed for the first implementation:

- Toyota `BTH+` / `BTH-` -> TI `SN75HVD12DR` A/B differential receiver
- SN75HVD12 pin 1 `R`/receiver output -> CYD GPIO35
- `/RE` held LOW
- `DE` held LOW
- `D` held LOW
- VCC = 3.3 V, shared CYD ground
- 100 nF local decoupling at the transceiver plus approximately 4.7-10 uF nearby bulk capacitance
- no added in-vehicle termination or bias
- GPIO35 is input-only and must never be assigned BTH TX, DE, or other output duty
- GPIO39 remains unused/reserved for this revision

The firmware does not control `/RE`, `DE`, or `D`; they are fixed by hardware for receive-only operation.

## Initial BTH acquisition configuration

Historical project acquisition notes specify **19200 baud, 8 data bits, odd parity, 1 stop bit** as the first decoding configuration. This is an acquisition starting point, not a universal Toyota BTH protocol assertion.

The first implementation therefore uses ESP32 hardware UART receive on GPIO35 with:

- UART controller: UART2
- baud: 19200
- data bits: 8
- parity: odd
- stop bits: 1
- RX only
- default RX inversion: disabled
- compile-time/runtime configuration must permit RX inversion for polarity validation without rewiring

No BTH transmission API exists in this firmware.

## BTH1 raw format

BTH protocol packet boundaries are not assumed. `BTH1` is a generic serial-chunk evidence format.

### File header

Every `BTH_nnn.BTH` begins with a fixed 32-byte little-endian header:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | ASCII `BTH1` |
| 4 | 1 | major = 1 |
| 5 | 1 | minor = 0 |
| 6 | 2 | header size = 32 |
| 8 | 4 | baud used for acquisition |
| 12 | 1 | data bits |
| 13 | 1 | parity enum: 0 none, 1 odd, 2 even |
| 14 | 1 | stop bits x2: 2 means one stop bit |
| 15 | 1 | flags; bit0 = RX inverted |
| 16 | 8 | stream start `time_us` on the common ESP32 monotonic clock |
| 24 | 4 | CRC-32/ISO-HDLC of bytes 0-23 |
| 28 | 4 | reserved = 0 |

### Chunk record

Each record preserves bytes in original order without asserting protocol framing:

| Size | Field |
|---:|---|
| 2 | sync `0xB7B1` |
| 2 | total record length |
| 4 | monotonically increasing BTH chunk sequence |
| 8 | `observed_time_us` from the dedicated UART event task |
| 2 | status flags |
| 2 | payload byte count |
| N | received bytes, 1-64 |
| 4 | CRC-32/ISO-HDLC over record prefix + payload |

Status flag assignments:

- bit0 parity error observed since prior data record
- bit1 framing error observed since prior data record
- bit2 break observed since prior data record
- bit3 UART FIFO overflow observed since prior data record
- bit4 UART driver ring-buffer full observed since prior data record
- remaining bits reserved

A truncated final record is ignored offline; all preceding CRC-valid records remain usable.

`observed_time_us` is the time the dedicated UART event task services the data event. It is not falsely represented as the exact physical arrival time of every byte. At the configured UART framing, byte order and nominal inter-byte duration remain available for later reconstruction.

## BTH runtime architecture

Use the ESP-IDF UART driver rather than polling GPIO35 or a software UART.

A dedicated BTH RX task blocks on the UART event queue. Its responsibilities are limited to:

1. receive UART events;
2. timestamp immediately with `esp_timer_get_time()`;
3. read at most 64 bytes per chunk;
4. accumulate UART error flags;
5. enqueue an owned fixed-size `BthChunk` to a bounded BTH queue;
6. update receive/drop/error counters;
7. return to waiting.

The BTH RX task performs no filesystem, TFT, BLE, Wi-Fi, diagnostic decoding, or dynamic allocation.

Initial RAM bounds:

- CAN application queue: **768** records
- CAN persisted batch: 128 records
- BTH chunk payload: 64 bytes
- BTH chunk queue: 32 records
- UART RX driver buffer: 1024 bytes
- UART event queue: 16 events

The 768 CAN queue is intentional: earlier logger testing established that 1024 consumed 24 KiB for `CapturedFrame` storage while 768 recovers 6144 bytes of scarce internal DRAM. BTH must fit inside the recovered headroom rather than re-consuming it with another large duplicate buffer.

## Main-loop priority

The acquisition priority is:

1. CAN receive/timestamp and protocol-safety work
2. CAN RAW persistence
3. BTH UART receive/event capture
4. BTH raw persistence
5. critical TVM1 metadata
6. read-only diagnostic state work
7. BLE/touch control
8. TFT dirty-field status updates
9. durability flush and other housekeeping

The main loop drains CAN RAW first, then BTH persistence, then metadata/derived work. Neither TFT responsiveness nor diagnostic presentation may intentionally discard CAN or BTH data.

## TVM1 stream registration

Stream IDs are:

- 0: session metadata
- 1: CAN / TCB1
- 2: BTH / BTH1

BTH `STREAM_REGISTER` records the actual UART configuration used: baud, data bits, parity, stop bits, RX inversion, GPIO35, and receive-only capability.

BTH gets independent `STREAM_START`, `STREAM_FILE_OPEN/CLOSE`, `STREAM_COUNTERS`, `BUS_STATE`/EVENT records as applicable, `STREAM_STOP`, and final counters.

`SESSION_CLOSE.registered_stream_count` is 2 when both CAN and BTH were registered.

## Start/stop and failure behavior

CAN and BTH share one session and one `esp_timer` timebase.

START must establish both stream files before acknowledging a successful synchronized capture when BTH is enabled. A BTH initialization failure must be explicit in TVM1 and on the TFT; it must not silently claim dual-stream capture.

STOP is pending. Session close waits until already-queued CAN frames and BTH chunks are persisted, then writes final counters, stream stops, session close, flushes/closes RAW/BTH/META, and removes `SESSION.OPEN`.

A power loss leaves complete RAW TCB1 records, complete BTH1 records, prior valid TVM1 records and `SESSION.OPEN` recoverable.

## Display and controls

There is no PAGE button in the acquisition firmware. Normal logger mode uses one fixed low-overhead status screen.

Three controls are retained:

- `START/STOP LOG`
- `DIAG OFF/ON`
- `WIFI FILES`

Wi-Fi remains available only while logging is stopped and remains exclusive maintenance mode.

The fixed status screen prioritizes integrity metrics:

- CAN RX rate, persisted rate, queue depth/high-water, drops, TWAI missed/overrun/errors
- BTH byte/chunk rate, queue depth/high-water, drops, UART overflow/parity/framing/break state
- SD write/flush latency and errors
- BLE connection/sync state
- diagnostics enabled/interlock state
- free internal heap/largest block
- current session and clean/active state

Minimal passive vehicle context may remain where already confirmed and cheap to calculate: speed, numeric fuel level, and profile-appropriate ODO/session-distance. No PLOT or archival decoded stream is generated on-device.

## Wi-Fi file transfer

Preserve the existing stopped-logger Wi-Fi server, including file listing, individual downloads, ZIP creation/download/delete/cancel, clear protections, and restart-based exit.

The implementation must enumerate files actually present and must include native `BTH_*.BTH` and `SESSION.META`; it must not assume MANIFEST/CSV files exist.

## Performance instrumentation

Record CAN and BTH independently. At minimum preserve:

- CAN received/persisted/queue drops/queue high-water/TWAI errors
- BTH received bytes/chunks, persisted bytes/chunks, queue drops/high-water, UART FIFO overflow, UART buffer full, parity errors, framing errors, breaks
- RAW and BTH write count, average/max latency, short-write count
- RAW/BTH/META flush count/max latency
- main-loop max latency
- TFT render count/max latency
- free heap/largest block/minimum heap
- task stack high-water where available
- SD open/write/flush failures

## Performance and release gates

Initial SD SPI remains 4 MHz and the known RC2 SPI-controller arrangement remains unchanged for the first dual-stream build. Native SPI-host remapping and SD clock increases are separate controlled A/B experiments after the simplified dual-stream baseline works.

Host/static tests and compilation are necessary but not sufficient for promotion. RC2 remains rollback firmware until bench/vehicle validation demonstrates:

- no panic/reset or BLE allocation regression;
- clean repeated START/STOP;
- Wi-Fi maintenance remains exclusive;
- zero CAN TWAI missed/overrun under the controlled test;
- zero SD short writes;
- no unexplained BTH UART overflow/buffer-full events;
- CAN retention materially improves relative to the feature-heavy logger baseline;
- adding BTH does not materially regress CAN retention;
- native session can still be expanded by the validated preprocessor into a Builder-compatible CAN package;
- BTH native files remain preserved separately and byte-order/timing provenance is intact.
