# Toyota Vehicle Bus Capture Contract

Status: **Proposed v1.0 for review**  
Date: 2026-09-27

## 1. Purpose

This contract defines the native acquisition boundary for the Toyota vehicle-bus logger family. The embedded logger's primary mission is faithful, low-overhead acquisition. Formatting, decoding, plotting, diagnostic reconstruction, reporting, and compatibility expansion are offline responsibilities unless a calculation is required for immediate logger operation or the live display.

The contract is bus-neutral from the beginning so CAN, BTH, AVC-LAN, and future acquisition streams can coexist in one synchronized session without redesigning the session format.

## 2. Core principles

1. **Raw acquisition is authoritative.** A stream file contains the authoritative captured traffic for that stream.
2. **Metadata records facts, not derived reports.** `SESSION.META` records session state, synchronization, health, errors, counters, stream registration, and other facts that cannot be reconstructed reliably from raw bus traffic.
3. **Derived artifacts are reproducible offline.** CSV, JSON, PLOT, diagnostic, and report files are generated from raw streams + metadata + an identified decoder database/tool version.
4. **A session contains zero or more independent streams.** No consumer may assume CAN is the only stream or that CAN is always present.
5. **All streams share one monotonic logger timebase when captured by the same logger.** This provides direct CAN/BTH/AVC-LAN correlation.
6. **Physical file rotation does not create another logical stream.** `RAW_000.TCB`, `RAW_001.TCB`, etc. are ordered chunks of one CAN stream.
7. **Forward compatibility is mandatory.** Unknown record types and unknown stream types must be skippable when their lengths are valid.
8. **Power-loss recovery is mandatory.** A missing clean-close record represents an unclean session; valid records preceding a truncated final record remain usable.

## 3. Native session layout

A native reduced session is intentionally small:

```text
S0166/
    SESSION.META
    RAW_000.TCB
    RAW_001.TCB        # only if CAN file rotation occurred
    BTH_000.<format>   # only when a BTH stream is active
    AVC_000.<format>   # only when an AVC-LAN stream is active
```

`SESSION.META` is the only mandatory session-level file. At least one registered acquisition stream is expected for a useful capture, but the contract permits a metadata-only session for startup/failure diagnostics.

## 4. Logical stream model

Each acquisition stream has:

- `stream_id`: unsigned 8-bit stable ID within the session; `0` is reserved for session-level metadata.
- `stream_type`: standardized bus type.
- `stream_format`: independently versioned raw format.
- `nominal_rate`: optional bus rate when meaningful.
- `direction_capability`: RX-only or RX/TX.
- `start_time_us` and `stop_time_us` on the common logger clock.
- physical file index sequence.
- received/transmitted/persisted/drop/error counters.
- stream-specific health state.

Initial stream-type assignments:

| Value | Type | Status |
|---:|---|---|
| 0 | SESSION | Reserved for session-level records |
| 1 | CAN | Defined in v1 |
| 2 | BTH | Reserved; raw framing to be defined with hardware validation |
| 3 | AVC_LAN | Reserved; raw framing to be defined with hardware validation |
| 4-254 | FUTURE | Reserved |
| 255 | VENDOR_EXPERIMENTAL | Noncanonical experiments only |

A session may capture one stream at a time or multiple streams concurrently. Stream start/stop times and counters are independent.

## 5. CAN stream contract

### 5.1 Raw format

CAN v1 uses the existing `TCB1` format unchanged.

Each TCB file contains:

- 16-byte TCB1 header.
- packed 24-byte records.
- little-endian fields.

Logical CAN record fields remain:

```text
uint64 time_us
uint32 can_id
uint8  data[8]
uint8  dlc
uint8  extended
uint8  rtr
uint8  direction   # 0=RX, 1=TX
```

TX records are mission-critical because offline software must be able to distinguish logger-generated diagnostic requests and ISO-TP flow-control traffic from external tester traffic.

### 5.2 Physical file rotation

The current default CAN rotation threshold remains **25 MiB** for the first optimized firmware revision because existing Builder processing already supports multiple TCB chunks.

CAN chunk names are:

```text
RAW_000.TCB
RAW_001.TCB
...
RAW_999.TCB
```

Requirements:

- suffix is zero-padded to three decimal digits;
- files are interpreted in numeric/lexicographic suffix order;
- every chunk is independently valid TCB1 and contains its own TCB1 header;
- timestamps remain on the same monotonic stream clock across rotations;
- rotation does not reset stream counters;
- normal operation uses contiguous suffixes beginning at `000`;
- a missing suffix is a recovery warning, not permission to reorder later chunks;
- a trailing partial TCB record may be discarded by the reader while all complete records remain valid.

The rotation threshold is an implementation default, not a contract constant. A future firmware may raise it without changing the logical CAN stream format.

### 5.3 Logical stream identity

Consumers must treat all valid CAN chunks for one registered CAN stream as one ordered logical stream.

A logical CAN stream hash should be computed from the ordered parsed record tuples, not from physical filenames or TCB headers. This permits file rotation policy to change without changing the logical evidence identity.

## 6. `SESSION.META` binary format

### 6.1 File header

All multi-byte numeric values are little-endian.

`SESSION.META` begins with a fixed 32-byte header:

| Offset | Size | Field |
|---:|---:|---|
| 0 | 4 | ASCII magic `TVM1` |
| 4 | 1 | major version = 1 |
| 5 | 1 | minor version = 0 |
| 6 | 2 | header size = 32 |
| 8 | 4 | numeric session number, e.g. 166 for S0166 |
| 12 | 4 | header flags |
| 16 | 8 | logger boot-time monotonic value at session creation, microseconds |
| 24 | 4 | CRC-32 of bytes 0-23 |
| 28 | 4 | reserved, zero in v1 |

The file header contains no decoder-specific engineering values.

### 6.2 Record framing

After the file header, metadata is append-only. Every record uses this framing:

| Size | Field |
|---:|---|
| 2 | record sync word `0xA55A` |
| 2 | total record length including header, payload, and CRC |
| 2 | record type |
| 1 | stream_id (`0` for session-level records) |
| 1 | flags |
| 4 | monotonically increasing metadata sequence number |
| 8 | `time_us` on the common logger monotonic clock |
| N | record-type payload |
| 4 | CRC-32 over all bytes from sync word through payload |

Minimum record size is 24 bytes. Consumers must skip unknown record types using the declared record length after validating framing and CRC.

A truncated final record is ignored. A CRC-invalid record is reported. A reader may attempt resynchronization on the next `0xA55A` marker, but must report that recovery occurred.

### 6.3 Required record types

Initial v1 assignments:

| Type | Name | Stream | Purpose |
|---:|---|---:|---|
| `0x0001` | SESSION_START | 0 | Session creation, firmware/build, board identity |
| `0x0002` | STREAM_REGISTER | stream | Bus type, raw format, version, nominal rate, direction capability |
| `0x0003` | STREAM_START | stream | Acquisition begins |
| `0x0004` | STREAM_STOP | stream | Acquisition intentionally stops |
| `0x0005` | STREAM_FILE_OPEN | stream | Physical file index opened |
| `0x0006` | STREAM_FILE_CLOSE | stream | Physical file index closed/rotated and final persisted count |
| `0x0010` | CLOCK_SYNC | 0 | BLE/companion E2/E3 timing sample or later equivalent |
| `0x0011` | USER_MARKER | 0 | User/session marker tied to monotonic time |
| `0x0020` | HEALTH_SNAPSHOT | 0 | Heap/stack/storage/global health instrumentation |
| `0x0021` | STREAM_COUNTERS | stream | RX/TX/persisted/drop/error counters and queue high-water |
| `0x0022` | STORAGE_HEALTH | 0 | SD free space, write/flush latency/error counters |
| `0x0030` | EVENT | 0 or stream | Enumerated logger event, severity, compact code/arguments |
| `0x0031` | DIAGNOSTIC_STATE | CAN stream | Diagnostic scheduler enable/disable/timeout/internal status not fully inferable from CAN |
| `0x0032` | BUS_STATE | stream | Bus-off/recovery/link-state changes |
| `0x00FE` | SESSION_CLOSE | 0 | Final counters, clean-close flag, close reason |

Record payloads must use fixed-width numeric fields wherever practical. Free-form strings are prohibited in high-frequency records. String identifiers required for provenance are limited to SESSION_START and are length-prefixed UTF-8.

## 7. Session close and recovery

A session is clean only when a valid `SESSION_CLOSE` record exists.

If no valid `SESSION_CLOSE` exists:

- the session is `UNCLEAN`;
- all complete raw stream records remain authoritative;
- the last valid `STREAM_COUNTERS` and `HEALTH_SNAPSHOT` records provide recoverable counters;
- the offline expander may emit legacy `SESSION.OPEN` and checkpoint semantics;
- no consumer may invent a clean-close state.

This replaces repeated JSON checkpoint rewrite/rename operations on the SD card with append-only metadata.

## 8. Embedded logger responsibilities

The optimized firmware must prioritize work in this order:

1. receive/timestamp bus traffic;
2. enqueue and persist raw stream records;
3. perform immediate protocol/safety work required for acquisition (for CAN, e.g. necessary ISO-TP flow control and external-tester interlock);
4. append compact metadata facts;
5. maintain live display state;
6. perform noncritical housekeeping.

The embedded logger must not continuously generate archival convenience products when those products can be recreated offline.

Specifically, future optimized firmware does **not** need to persist:

- `DECODED.CSV`
- `DIAGNOSTICS.CSV`
- `EXTERNAL_DIAGNOSTICS.CSV`
- `EVENTS.CSV`
- `SYNC.CSV`
- `SIGNALS.CSV`
- `PLOT.CSV`
- `MANIFEST.JSON`
- `CHECKPOINT.JSON`
- session README/report files

The firmware may continue decoding a minimal working set in RAM for the live display and diagnostic scheduler. RAM-only display calculations are not evidence artifacts.

## 9. Offline legacy-session expander contract

The first offline consumer is a compatibility preprocessor/expander. Given a native session, it reconstructs the current legacy session layout required by Evidence Builder and related tooling.

For CAN sessions it can emit:

```text
S0166/
    MANIFEST.JSON
    CHECKPOINT.JSON
    SYNC.CSV
    EVENTS.CSV
    DIAGNOSTICS.CSV
    EXTERNAL_DIAGNOSTICS.CSV
    DECODED.CSV
    SIGNALS.CSV
    PLOT.CSV
    README.TXT
    RAW_000.TCB
    RAW_001.TCB        # if present in native source
    SESSION.OPEN       # only for unclean sessions
```

Rules:

- raw stream files are copied byte-for-byte or referenced without mutation;
- legacy metadata is reconstructed only from native raw + native META + identified offline database/tool versions;
- diagnostic transaction reconstruction must preserve logger-vs-external provenance using CAN TX/RX direction and metadata state;
- `PLOT.CSV` is a derived product, not native evidence;
- generated artifacts record the preprocessor version and decoder/database identity;
- the expander must never overwrite the native session.

The expander logic should be implemented as a reusable library so the same engine can later be:

1. integrated into Evidence Builder;
2. integrated into Analyzer;
3. exposed as a dedicated PLOT/session-product generator application.

## 10. PLOT generation

`PLOT.CSV` is explicitly classified as a reproducible offline product.

Inputs may include:

- CAN/BTH/AVC-LAN native streams;
- `SESSION.META` timing, stream state, and quality records;
- the selected decoder/database version;
- diagnostic reconstruction results.

PLOT generation must preserve:

- session-relative time;
- stream/data age semantics;
- data-quality state;
- provenance for each derived signal family;
- missing values as missing, never guessed.

Because PLOT is regenerated offline, old sessions can benefit from improved decoders without modifying the native evidence.

## 11. Board and firmware scope for the first optimized revision

Supported display/logger boards moving forward in this revision:

- E32R35T 3.5-inch ESP32-32E, ST7796 + XPT2046 touch;
- existing Dorhea 3.5-inch CYD profile.

The first optimized revision retains:

- validated 80 MHz TFT operation;
- dirty-rectangle/value-field updates instead of periodic full-page clearing;
- existing TCB1 CAN format;
- existing 25 MiB CAN rotation threshold initially;
- dedicated CAN RX task and raw queue architecture;
- exclusive Wi-Fi maintenance mode;
- live display decoding only where required.

It removes or defers offline-reconstructible SD products and adopts RAW-first persistence.

## 12. BTH and AVC-LAN expansion rules

BTH and AVC-LAN are reserved now but their raw byte/packet formats are intentionally not guessed before hardware validation.

When each format is defined it must:

- receive its own independently versioned raw format identifier;
- use the same common `time_us` clock semantics;
- define RX/TX direction when meaningful;
- support its own physical rotation without becoming multiple logical streams;
- expose persisted/drop/error counters through `STREAM_COUNTERS`;
- avoid changing the SESSION.META framing or CAN TCB1 format.

This permits one-stream-at-a-time operation initially and concurrent stream acquisition later.

## 13. Validation requirements

Before optimized firmware removes legacy SD products, the offline expander must be validated against representative historical sessions.

Required cases:

1. clean close;
2. unclean/power-loss close;
3. multiple `RAW_nnn.TCB` chunks;
4. BLE synchronization;
5. logger-generated diagnostics;
6. external Autel/AP200 diagnostic traffic;
7. queue/drop/error counters;
8. raw-file truncated-tail recovery.

Acceptance requirements:

- native TCB files remain byte-identical;
- ordered logical CAN record tuples and logical stream hash match the source;
- reconstructed Builder-required artifacts are schema-compatible;
- Evidence Builder processes the expanded session successfully;
- Builder raw record count matches native logical CAN count;
- diagnostic/external transaction counts and timing are semantically equivalent to the historical path;
- a single integrated Analyzer `process` smoke test is sufficient after Builder compatibility is established because Analyzer uses the integrated Builder path for raw CANLOG/CAPTURE processing.

## 14. Non-goals for v1

The v1 contract does not define:

- BTH electrical/protocol framing;
- AVC-LAN electrical/protocol framing;
- a replacement for TCB1;
- cloud storage or remote streaming;
- live Wi-Fi transmission during acquisition;
- automatic canonical-database mutation;
- actuator/control commands.

## 15. Compatibility statement

Existing historical CANLOG packages remain valid and unchanged. The native reduced-session contract is a new acquisition representation. The offline expander is the compatibility boundary that converts the reduced representation into the established legacy session products when those products are required.
