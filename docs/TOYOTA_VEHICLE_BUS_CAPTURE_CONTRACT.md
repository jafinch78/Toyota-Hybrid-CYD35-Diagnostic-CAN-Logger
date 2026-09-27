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
9. **Evidence status must be explicit.** Toyota-documented behavior, project-verified wiring, third-party reverse engineering, and acquisition hypotheses must not be blended into one certainty level.

### 2.1 Evidence-status terms

This document uses these terms for BTH/AVC-LAN details:

- `TOYOTA_DOCUMENTED`: supported directly by Toyota wiring/service/training material.
- `PROJECT_VERIFIED`: established in this project's reviewed wiring/manual work or hardware record.
- `REVERSE_ENGINEERED`: supported by reproducible public reverse-engineering work but not asserted as Toyota-published protocol documentation.
- `CAPTURE_CANDIDATE`: useful initial acquisition/decoder setting that still requires target-vehicle validation.

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
| 1 | CAN | TCB1 defined in v1 |
| 2 | BTH | Bus role/electrical path documented; raw capture framing to be frozen after target-hardware validation |
| 3 | AVC_LAN | Bus timing/frame grammar substantially documented; raw capture framing to be frozen after logger-hardware validation |
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

## 12. BTH acquisition and protocol knowledge

BTH is no longer treated as an unspecified future label. The electrical role and a substantial amount of higher-level behavior are already known, but target-specific serial framing still requires live validation before the raw-file format is frozen.

### 12.1 Platform applicability

Current audited project position:

| Platform | Battery-controller transport | Status |
|---|---|---|
| NHW20 Prius Gen 2 | Battery ECU -> public CAN -> HV Control ECU | `TOYOTA_DOCUMENTED` project audit; no later-style point-to-point BTH battery telemetry established |
| AHV40 Camry Hybrid Gen 1 | Battery Smart Unit -> private serial/BTH -> HV Control ECU | `TOYOTA_DOCUMENTED` project audit |
| ZVW30 Prius Gen 3 | Battery Smart Unit -> private serial/BTH -> Power Management Control ECU | `TOYOTA_DOCUMENTED` project audit |
| ZVW35 Prius PHV Gen 1 | Battery Smart Unit -> private serial/BTH -> Power Management ECU, plus Plug-in Control communications | `TOYOTA_DOCUMENTED` project audit |
| ZVW41 Prius v / Prius+ | Battery Smart Unit -> private serial/BTH -> Power Management ECU | `TOYOTA_DOCUMENTED` project audit |

This supersedes older NHW20 private-link hypotheses in acquisition checklists. BTH capture hardware must not be generalized to NHW20 unless new vehicle evidence establishes such a link.

### 12.2 Electrical/acquisition interface

For the immediate BTH logger work:

- the target is the low-voltage `BTH+` / `BTH-` differential pair between the Battery Smart Unit and hybrid/power-management controller;
- the logger is receive-only;
- use a protected high-impedance differential receiver;
- current project hardware uses the TI `SN75HVD12DR` as the receive front end;
- receiver-enable is asserted, transmitter-enable is held inactive, and the transmit input is held inactive;
- do not add termination or bias to the in-vehicle link unless an isolated bench topology explicitly requires it;
- preserve the vehicle's existing bus loading and wiring;
- timestamp received data on the common session clock.

For the current CYD hardware plan, the receiver output is routed to input-only GPIO35. The BTH logger must not use GPIO35 as a transmit or driver-enable output.

For the ZVW35 PHV wiring already established in project research, `BTH+` and `BTH-` are the Battery Smart Unit to Power Management ECU private pair; project pinout work identified Battery Smart Unit C5-4/C5-5 to Power Management ECU L135-32/L135-33 respectively. These pin assignments remain platform-specific and must not be propagated to other Toyota profiles without their own wiring evidence.

### 12.3 Known/reverse-engineered data-stream structure

Public Gen 3 reverse engineering provides a concrete expectation for the Toyota BSU serial family:

- 24 distinct packets;
- 16 bytes per packet;
- 384 bytes for the complete reported packet set;
- reported content includes 14 blade/block voltages, 3 battery temperatures, intake temperature, pack current, battery-fan RPM, HV isolation voltage, 12-V voltage, BSU version information, and pack-fault flags.

This is `REVERSE_ENGINEERED`, not yet a guarantee that every AHV40/ZVW30/ZVW35/ZVW41 packet layout is byte-identical. The native logger must therefore preserve raw observations rather than emit only interpreted fields.

### 12.4 Baud/framing status

The contract intentionally separates **acquisition configuration** from **protocol truth**.

Existing research gives useful starting points around approximately 9600-baud Toyota BSU serial operation, while an older NHW20 experimental checklist used `19200 8O1` as an initial decoder probe. Neither value is promoted here as a universal BTH contract.

When BTH hardware arrives, the first target-vehicle capture must determine and record:

- polarity and idle state;
- baud rate;
- data-bit count;
- parity;
- stop-bit count;
- packet spacing/repetition period;
- packet sequence/identity;
- checksums or integrity fields;
- startup/shutdown behavior;
- directionality/request-response behavior if any.

`STREAM_REGISTER` for BTH must record the actual acquisition UART/framing configuration used. A later decoder may reinterpret the bytes, but it must not silently rewrite the original capture configuration.

### 12.5 BTH raw-format design direction

The eventual BTH raw format should preserve at minimum:

- monotonic timestamp;
- byte(s) received in original order;
- acquisition framing configuration identity;
- UART framing/parity/overrun error status where available;
- RX/TX direction if transmission is ever enabled in a later Smart Unit development mode;
- physical-file rotation identity and stream counters.

The first vehicle logger remains receive-only. Active BTH emulation/transmission belongs to a later Smart Unit scope, not this capture firmware.

## 13. AVC-LAN acquisition and protocol knowledge

AVC-LAN is also sufficiently characterized to document its acquisition target now, even though its native raw file format will be frozen only when logger hardware is selected and bench/vehicle capture is validated.

### 13.1 Toyota-documented network characteristics

For Prius-era AVC-LAN:

- Toyota identifies AVC-LAN as a Toyota-original audio/visual communication network;
- nominal/maximum communication rate is approximately **17.8 kbit/s**;
- physical medium is a **twisted-pair differential** connection;
- payload length is variable from **0 to 32 bytes**;
- Prius uses a **star topology** centered on the multimedia master; Toyota service information identifies the multi-display or audio head unit as the master depending on configuration.

These are `TOYOTA_DOCUMENTED` characteristics.

### 13.2 Project wiring points

Relevant Gen 2 Prius wiring already documented in this project includes:

- 2004 low-resolution/navigation MFD `86110-47071`: M14 pin 13 `TX+`, pin 14 `TX-` for AVC-LAN;
- 2006-2009 MFD family: primary MFD/gateway branch `TX1+` / `TX1-` at M13 pins 4/5; the separate `TX2+` / `TX2-` branch appears at M13 pins 18/19 for the associated audio branch/configuration;
- navigation/audio equipment uses additional paired AVC-LAN connections according to vehicle option wiring.

Pin assignments are profile/option specific. The acquisition contract stores the selected physical tap in session metadata rather than assuming one universal connector.

### 13.3 Reverse-engineered bit timing

The widely reproduced AVC-LAN/IEBus implementation model is timing encoded and collision/arbitration aware:

- bus logical `1` is released/floating differential state;
- bus logical `0` is the driven/dominant differential state;
- start pulse is approximately **165 us high**, followed by approximately 30 us released time;
- logical `0` is approximately **32 us high + 7 us low/released**;
- logical `1` is approximately **20 us high + 19 us low/released**;
- ordinary bit period is therefore approximately **40 us**;
- logical `0` is dominant, which supports arbitration.

These values are `REVERSE_ENGINEERED` and should be treated as decoder timing windows, not exact crystal-clock constants.

### 13.4 Reverse-engineered frame grammar

The established public AVC-LAN frame model is:

```text
START
MSG_NORMAL
MASTER_ADDRESS[12]
PARITY
SLAVE_ADDRESS[12]
PARITY
ACK
CONTROL[4]
PARITY
ACK
PAYLOAD_LENGTH[8]
PARITY
ACK
repeat PAYLOAD_LENGTH times:
    DATA[8]
    PARITY
    ACK
```

Point-to-point acknowledgement is represented by the receiving node extending the sender's released ACK bit into the dominant state. Broadcast behavior differs because receivers do not acknowledge the same way.

This grammar is `REVERSE_ENGINEERED` and is adequate to guide raw logger design and offline decoder tests.

### 13.5 AVC-LAN raw-format design direction

Because AVC-LAN encodes information in pulse widths and arbitration timing, the acquisition format should preserve timing evidence before relying on frame interpretation.

The preferred raw capture hierarchy is:

1. timestamped differential/logic edge durations or equivalent pulse-width events;
2. offline reconstruction of start/0/1 symbols;
3. offline frame/parity/ACK decoding;
4. offline higher-level address/control/payload interpretation.

The logger interface should be high impedance and must not add termination to the in-vehicle network. Receive-only capture is the default until a separate active-interface design is deliberately validated.

A future AVC-LAN raw format should preserve at minimum:

- common-clock timestamp;
- edge/pulse duration or symbol timing sufficient to reproduce bit classification;
- capture polarity/configuration identity;
- decoder error/recovery markers where produced;
- frame direction only when it can be established without inventing information;
- physical-file rotation and stream counters.

This keeps the embedded mission aligned with CAN/BTH: capture facts first, interpret offline.

## 14. Cross-stream expansion rules

BTH and AVC-LAN receive independently versioned raw formats, but neither may require a change to `SESSION.META` framing or to CAN TCB1.

Each stream format must:

- use the same common `time_us` session clock semantics;
- define RX/TX direction when meaningful and observable;
- support its own physical rotation without becoming multiple logical streams;
- expose persisted/drop/error counters through `STREAM_COUNTERS`;
- preserve raw evidence needed to rerun improved offline decoders;
- support one-stream-at-a-time operation initially and concurrent acquisition later.

## 15. Validation requirements

Before optimized firmware removes legacy SD products, the offline expander must be validated against representative historical sessions.

Required CAN/legacy cases:

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

BTH validation adds:

- target-vehicle receive-only electrical capture;
- frozen baud/framing determination with error-rate evidence;
- repeatable packet boundaries and sequence;
- correlation against known battery voltage/current/temperature/fan reference values;
- no transmission on the vehicle private link during logger validation.

AVC-LAN validation adds:

- bench/vehicle edge timing consistent with start/0/1 timing families;
- reproducible parity/ACK/frame reconstruction;
- address/control/payload decoding from raw timing without requiring firmware-side interpretation;
- correlation to known MFD/audio/navigation actions where safe and appropriate.

## 16. Non-goals for v1

The v1 contract does not define:

- a universal byte-identical BTH packet map across all Toyota platforms;
- a final BTH raw-file binary layout before target-hardware capture validates UART/framing requirements;
- a final AVC-LAN raw-file binary layout before acquisition hardware/timing capture is validated;
- active BTH Smart Unit emulation;
- active AVC-LAN control/injection;
- a replacement for TCB1;
- cloud storage or remote streaming;
- live Wi-Fi transmission during acquisition;
- automatic canonical-database mutation;
- actuator/control commands.

## 17. Evidence references for BTH/AVC-LAN sections

Primary project/source basis includes:

- Toyota Gen 2 Prius electrical wiring diagrams documenting MFD AVC-LAN `TX+/TX-`, `TX1+/TX1-`, and `TX2+/TX2-` branches;
- Toyota multiplex/network documentation identifying AVC-LAN as approximately 17.8 kbit/s, twisted-pair differential, 0-32-byte variable payload, and Prius star topology;
- project Toyota hybrid DTC/INF audits establishing Battery Smart Unit private-serial/BTH architecture for AHV40, ZVW30, ZVW35, and ZVW41, while explicitly not establishing later-style BTH for NHW20;
- project BTH acquisition checklists requiring a protected, high-impedance receive-only capture path and preservation of raw data before framing assumptions;
- public LiBSU reverse engineering documenting the Gen 3 24 x 16-byte / 384-byte BSU data set and its reported battery telemetry contents;
- public AVC-LAN/IEBus reverse engineering documenting pulse timing, dominant/released bit behavior, addressing, parity, acknowledgement, control, length, and payload grammar.

All target-platform values discovered by future live acquisition must be added with explicit evidence status instead of silently changing a generic protocol assumption.

## 18. Compatibility statement

Existing historical CANLOG packages remain valid and unchanged. The native reduced-session contract is a new acquisition representation. The offline expander is the compatibility boundary that converts the reduced representation into the established legacy session products when those products are required.
