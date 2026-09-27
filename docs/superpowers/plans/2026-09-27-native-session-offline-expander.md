# Native Session Offline Expander Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a standalone Windows/Python preprocessor that reads the new native `RAW stream(s) + SESSION.META` capture contract, validates/recoverably parses the evidence, and expands it into a current Evidence Builder 1.0.4-compatible CANLOG session without modifying the native source.

**Architecture:** The new application is an independent pure-Python package under `windows/ToyotaVehicleBusSessionPreprocessor/`. It owns TVM1 parsing, native-session validation, TCB1 logical-stream handling, legacy metadata expansion, logger/external diagnostic reconstruction, deterministic packaging, and compatibility validation. Evidence Builder 1.0.4 remains an external oracle rather than a runtime dependency of the core expander. RAW TCB files are copied byte-for-byte; all generated JSON/CSV files carry reconstruction provenance. A validation-only legacy-to-native synthesizer lets us prove the contract against historical sessions before any stripped firmware exists.

**Tech Stack:** Python 3.12 release target with Python `>=3.10` source compatibility; standard library only for the core (`argparse`, `csv`, `dataclasses`, `hashlib`, `json`, `pathlib`, `struct`, `tempfile`, `tkinter`, `unittest`, `zipfile`, `zlib`); Windows 10 1607 x64 remains a release gate. Builder oracle: `evidence-builder-v1.0.4` branch / `toyota-can-evidence-builder 1.0.4`.

**Spec:** `docs/TOYOTA_VEHICLE_BUS_CAPTURE_CONTRACT.md` and `docs/TVM1_SESSION_META_BINARY_SPEC.md`.

## Global Constraints

- Native capture evidence is immutable. Never overwrite `SESSION.META` or a native raw stream file.
- TCB1 remains authoritative for CAN. Expanded `RAW_*.TCB` files must be byte-identical to native input and re-hashed after copy.
- Physical TCB rotation is transparent: `RAW_000.TCB`, `RAW_001.TCB`, etc. are one ordered logical CAN stream.
- TVM1 recovery may discard only an incomplete final record or explicitly report/resynchronize corruption; it may never invent missing records/counters.
- No CAN transmission, actuator/control action, or canonical database mutation exists anywhere in this application.
- The expander must preserve RX/TX direction. Logger-originated diagnostic requests and ISO-TP flow-control traffic must remain distinguishable from external tester traffic.
- Builder 1.0.4 compatibility uses legacy `format="ToyotaHybridCAN-Capture"`, `format_version="1.4"`, and `raw_format="TCB1_24_byte_records"` while also recording TVM1/preprocessor provenance in extra manifest fields.
- Do not generate plausible-looking derived data that has not actually been reconstructed. `DECODED.CSV`, `SIGNALS.CSV`, and `PLOT.CSV` are a separate derived-products/PLOT implementation unless Builder-oracle testing proves one is required to preserve current Builder evidence behavior; if so, the minimum required compatibility writer becomes a blocking task before this plan can pass.
- This plan does not alter Builder, Analyzer, CAN logger firmware, BTH logger firmware, or AVC-LAN logger firmware.
- Builder validation is the primary compatibility gate. After it passes, only one Analyzer RC8 `process` smoke is required because RC8 already embeds the Builder path.
- Windows launchers must use `%~dp0`, verify the expected Python/venv, capture `ERRORLEVEL` before `PAUSE`, and show explicit PASS/FAIL stage output.

## Review Focus

1. **Evidence identity:** raw byte hashes, logical CAN record count/order, and RX/TX direction must survive expansion exactly.
2. **Power-loss recovery:** truncated final TVM1 records, stale/missing clean close, and truncated final TCB records must produce explicit recovery status rather than silent success.
3. **Rotation correctness:** two or more TCB chunks must parse in numeric order as one logical stream, with no reset or duplicate at file boundaries.
4. **Diagnostic provenance:** own logger TX traffic and external tester RX traffic must never be conflated; ISO-TP sequence failures/timeouts remain visible.
5. **Legacy schema compatibility:** generated MANIFEST/CHECKPOINT/SYNC/EVENTS/DIAGNOSTICS/EXTERNAL_DIAGNOSTICS must use the current field names and value conventions that Builder 1.0.4 consumes.
6. **No evidence inflation:** received, persisted, dropped, and recovered counts remain separate; persisted RAW count must not be presented as total received traffic.
7. **Determinism:** identical native input + options produces identical generated text contents and deterministic ZIP bytes.
8. **Builder oracle:** original historical CANLOG and regenerated CANLOG must produce equivalent Builder raw stream, synchronization, diagnostics, and session/profile evidence before firmware work is authorized.

---

### Task 1: Create the standalone package and freeze public interfaces

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/pyproject.toml`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/README.md`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/__init__.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/model.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_package.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ExpansionOptions:
    make_zip: bool = True
    preserve_raw_mtime: bool = False

@dataclass(frozen=True)
class ExpansionResult:
    session_id: str
    output_root: Path
    legacy_session_dir: Path
    zip_path: Path | None
    validation_report: Path

__version__ = "0.1.0"
```

- [ ] **Step 1: Write failing package/entry-point tests.**

`tests/test_package.py` must assert version import, package import without third-party dependencies, and declared console scripts:

```text
toyota-session-preprocess = toyota_vehicle_bus_session.cli:main
toyota-session-preprocess-gui = toyota_vehicle_bus_session.gui:main
```

- [ ] **Step 2: Run the focused test and confirm RED.**

```bat
cd windows\ToyotaVehicleBusSessionPreprocessor
py -3 -m unittest tests.test_package -v
```

Expected: import/metadata failure because the package does not exist yet.

- [ ] **Step 3: Add the minimal package skeleton and dataclasses.**

Keep runtime dependencies empty. `pyproject.toml` should require Python `>=3.10` and use setuptools/wheel only for build.

- [ ] **Step 4: Run focused and discovery tests.**

```bat
py -3 -m unittest tests.test_package -v
py -3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "feat: scaffold native session preprocessor"
```

---

### Task 2: Implement the TVM1 codec and corruption recovery

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/meta.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_meta.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/fixtures/README.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class MetaHeader:
    major: int
    minor: int
    session_number: int
    header_flags: int
    session_create_us: int

@dataclass(frozen=True)
class MetaRecord:
    record_type: int
    stream_id: int
    flags: int
    sequence: int
    time_us: int
    payload: bytes

@dataclass(frozen=True)
class MetaRecovery:
    truncated_tail_bytes: int
    crc_error_offsets: tuple[int, ...]
    resynchronized_records: int
    sequence_gaps: tuple[tuple[int, int], ...]
    unknown_record_types: tuple[int, ...]

@dataclass(frozen=True)
class MetaReadResult:
    header: MetaHeader
    records: tuple[MetaRecord, ...]
    recovery: MetaRecovery
    clean_close: bool

read_meta(path: Path) -> MetaReadResult
write_meta(path: Path, header: MetaHeader, records: Iterable[MetaRecord]) -> None
encode_record(record: MetaRecord) -> bytes
decode_record_payload(record: MetaRecord) -> object
```

- [ ] **Step 1: Write RED tests from the binary specification.** Cover exact 32-byte header encoding, `zlib.crc32` compatibility, 24-byte minimum record, UTF-8 length-prefix strings, every currently defined record payload, unknown record skipping, sequence gaps, corrupted-record resynchronization, and truncated-final-record recovery.

- [ ] **Step 2: Run and confirm RED.**

```bat
py -3 -m unittest tests.test_meta -v
```

- [ ] **Step 3: Implement fixed-width parsing with no schema guessing.** Reject bad magic, unsupported major versions, bad header CRC, length `<24`, and length `>4096`. Preserve unknown valid records in the generic record list and report their type IDs.

- [ ] **Step 4: Add golden-byte fixtures.** Tests must compare encoded bytes against hand-constructed `struct.pack()` expectations, not round-trip-only tests.

- [ ] **Step 5: Run focused tests and full suite.**

```bat
py -3 -m unittest tests.test_meta -v
py -3 -m unittest discover -s tests -v
```

- [ ] **Step 6: Commit.**

```bash
git add windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/meta.py windows/ToyotaVehicleBusSessionPreprocessor/tests
git commit -m "feat: implement TVM1 metadata codec"
```

---

### Task 3: Implement native-session discovery and TCB1 logical-stream validation

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/tcb1.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/native.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_tcb1.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_native.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TcbFrame:
    time_us: int
    can_id: int
    data: bytes
    dlc: int
    extended: int
    rtr: int
    direction: int

@dataclass(frozen=True)
class TcbChunkReport:
    path: Path
    records: int
    truncated_tail_bytes: int
    first_time_us: int | None
    last_time_us: int | None
    sha256: str

@dataclass(frozen=True)
class CanStreamReport:
    chunks: tuple[TcbChunkReport, ...]
    record_count: int
    logical_record_sha256: str
    rx_count: int
    tx_count: int
    first_time_us: int | None
    last_time_us: int | None

iter_tcb_frames(paths: Sequence[Path]) -> Iterator[TcbFrame]
scan_tcb_stream(paths: Sequence[Path]) -> CanStreamReport
load_native_session(source: Path) -> NativeSession
```

- [ ] **Step 1: Write RED TCB tests.** Reproduce Builder 1.0.4's canonical `TCB1` header and `<QI8sBBBB` record behavior. Include two chunks where a logical stream is split at two different record boundaries and require identical `logical_record_sha256` and frame sequence.

- [ ] **Step 2: Add validation failures.** Reject duplicate chunk indices, missing `RAW_000.TCB`, noncontiguous suffixes as a reported integrity error, invalid DLC, bad TCB header/version, and timestamp reversal across a chunk boundary. A truncated final TCB record remains recoverable and is reported.

- [ ] **Step 3: Run RED tests.**

```bat
py -3 -m unittest tests.test_tcb1 tests.test_native -v
```

- [ ] **Step 4: Implement streaming scans.** Do not load a full TCB capture into RAM. Compute the logical record hash over concatenated complete 24-byte record bytes after each 16-byte TCB header so the hash is independent of file rotation boundaries.

- [ ] **Step 5: Implement safe ZIP/folder input.** ZIP extraction must reject path traversal and produce a temporary read-only working tree. Discover exactly one `SESSION.META` session per ordinary invocation; batch/multi-session discovery is out of this first release.

- [ ] **Step 6: Cross-check against Builder 1.0.4 parser semantics.** Add a test that feeds the same synthetic chunks through this parser and a test-vendored call to Builder `tcb1.py` when the oracle checkout is present; compare frame tuples, not implementation internals.

- [ ] **Step 7: Run full tests and commit.**

```bat
py -3 -m unittest discover -s tests -v
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "feat: validate native TCB1 streams"
```

---

### Task 4: Expand TVM1 into the core Builder-compatible legacy session

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/legacy.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/schemas.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/packaging.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_legacy.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_packaging.py`

**Interfaces:**

```python
expand_native_session(
    source: Path,
    output_parent: Path,
    *,
    options: ExpansionOptions = ExpansionOptions(),
) -> ExpansionResult

build_legacy_manifest(session: NativeSession) -> dict[str, object]
build_legacy_checkpoint(session: NativeSession) -> dict[str, object]
write_legacy_sync(session: NativeSession, path: Path) -> int
write_legacy_events(session: NativeSession, path: Path) -> int
```

**Required initial output:**

```text
CANLOG_TVM1_S####/
  S####/
    MANIFEST.JSON
    CHECKPOINT.JSON
    SYNC.CSV
    EVENTS.CSV
    DIAGNOSTICS.CSV               # populated in Task 5
    EXTERNAL_DIAGNOSTICS.CSV      # populated in Task 5
    README.TXT
    RAW_000.TCB
    RAW_001.TCB                   # only when present
    SESSION.OPEN                  # only when native close is unclean
  EXPANSION_REPORT.json
CANLOG_TVM1_S####.zip             # when requested
```

- [ ] **Step 1: Write RED schema tests.** Lock current CSV headers:
  - `SYNC.CSV`: `Sequence,ESP_Receive_us,ESP_Send_us,Source`
  - `EVENTS.CSV`: `Time_us,Severity,Event,Details`
  - diagnostic headers from current logger source (Task 5 fills rows).

- [ ] **Step 2: Write manifest compatibility RED tests.** Require `format`, `format_version=1.4`, `raw_format`, true firmware identity from SESSION_START, raw file count, first/last CAN times from authoritative RAW, separated RX/TX/persisted/drop counters, runtime DB identity, clean state, and extra provenance fields:

```text
native_capture_format = TVM1
native_capture_version = 1.0
native_meta_sha256
native_can_logical_sha256
preprocessor_name
preprocessor_version
```

Do not invent unavailable hardware values; omit or set explicit `null` only where current Builder tolerates it.

- [ ] **Step 3: Write checkpoint/recovery RED tests.** The last valid TVM1 counter/health snapshot plus actual RAW scan determines the checkpoint. Missing `SESSION_CLOSE` must create `SESSION.OPEN`, set `closed_cleanly=false`, and never be upgraded to clean because the raw files parse successfully.

- [ ] **Step 4: Implement byte-for-byte RAW copy and post-copy verification.** Copy each raw chunk and compare SHA-256 of source/destination before reporting success.

- [ ] **Step 5: Implement deterministic JSON/CSV/text generation.** JSON uses stable key ordering/indentation/newline. CSV uses fixed header ordering and `\n`-stable logical contents. Deterministic ZIP uses sorted member order and fixed archive timestamps; source RAW bytes remain unchanged inside the ZIP.

- [ ] **Step 6: Write explicit product status into `EXPANSION_REPORT.json`.** Mark `DECODED.CSV`, `SIGNALS.CSV`, and `PLOT.CSV` as `NOT_GENERATED_DERIVED` in this compatibility-core stage rather than creating empty or guessed values.

- [ ] **Step 7: Run focused/full tests and commit.**

```bat
py -3 -m unittest tests.test_legacy tests.test_packaging -v
py -3 -m unittest discover -s tests -v
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "feat: expand native sessions to legacy layout"
```

---

### Task 5: Reconstruct logger and external diagnostics entirely offline

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/isotp.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/diagnostics.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_isotp.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_diagnostics.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class DiagnosticTransaction:
    request_time_us: int
    complete_time_us: int | None
    request_id: int
    response_id: int | None
    service: int | None
    pid: int | None
    status: str
    payload: bytes
    frame_count: int
    response_time_ms: float | None

reconstruct_logger_diagnostics(
    frames: Iterable[TcbFrame],
    meta: MetaReadResult,
) -> tuple[DiagnosticTransaction, ...]

classify_external_diagnostic_frames(
    frames: Iterable[TcbFrame],
    *,
    hold_us: int = 5_000_000,
) -> tuple[ExternalDiagnosticFrame, ...]
```

- [ ] **Step 1: Write RED ISO-TP tests.** Cover single frame, first/consecutive frames, sequence wrap, missing sequence, negative response, no response, logger TX flow control, response mismatch, and concurrent external tester traffic.

- [ ] **Step 2: Freeze ownership rules in tests.** A standard RX request at `0x7DF` or `0x7E0-0x7E7` with PCI 0/1 is external; a `direction=TX` request is logger-owned. RX responses `0x7E8-0x7EF` within 5 seconds of external activity are external unless claimed by an active logger-owned transaction. Never classify a logger TX frame as external.

- [ ] **Step 3: Reproduce current legacy CSV schemas.** `DIAGNOSTICS.CSV` fields:

```text
Transaction,RequestTime_us,CompleteTime_us,RequestID,ResponseID,Service,PID,Status,PayloadLength,PayloadHex,FrameCount,ResponseTime_ms
```

`EXTERNAL_DIAGNOSTICS.CSV` fields:

```text
Time_us,CAN_ID,DLC,DataHex,Classification
```

- [ ] **Step 4: Preserve metadata-only diagnostic states.** TVM1 timeout, user-disable, external-interlock, bus-off, or reassembly-state records can refine transaction status but may not replace raw bus observations.

- [ ] **Step 5: Add counter reconciliation.** Expansion report must state raw RX/TX counts, reconstructed logger request/response counts, external request/response counts, incomplete transactions, timeouts, and any META-vs-reconstruction disagreements.

- [ ] **Step 6: Run focused/full tests and commit.**

```bat
py -3 -m unittest tests.test_isotp tests.test_diagnostics -v
py -3 -m unittest discover -s tests -v
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "feat: reconstruct diagnostics from raw CAN"
```

---

### Task 6: Add a validation-only legacy-to-native synthesizer

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/validation_fixture.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_validation_fixture.py`

**Purpose:** Until optimized firmware writes TVM1, convert an existing historical CANLOG into a **synthetic validation native session** (`RAW_*.TCB + SESSION.META`) so the expander can be exercised end-to-end. This is a test/validation bridge, not an archival migration format.

**Interface:**

```python
synthesize_native_fixture(
    legacy_canlog: Path,
    output_dir: Path,
) -> NativeFixtureResult
```

- [ ] **Step 1: Write RED round-trip tests using synthetic legacy inputs.** Legacy MANIFEST/CHECKPOINT/SYNC/EVENTS plus TCB input becomes TVM1+RAW, then expands again.

- [ ] **Step 2: Implement conservative mapping.** Preserve only facts representable in the approved TVM1 contract. Known event names map to defined event codes. Unknown legacy free-form event details are reported as `VALIDATION_FIXTURE_LOSSY_EVENT_DETAIL`; do not pretend the synthetic fixture is a lossless archival conversion.

- [ ] **Step 3: Assert raw identity through both legs.** Original legacy TCB SHA-256 == synthetic-native TCB SHA-256 == expanded TCB SHA-256; parsed frame tuples and logical hash must also match.

- [ ] **Step 4: Test stale manifest / authoritative checkpoint behavior.** A stale or unclean historical manifest must synthesize native unclean state using the newest recoverable checkpoint/raw facts and remain unclean after expansion.

- [ ] **Step 5: Run tests and commit.**

```bat
py -3 -m unittest tests.test_validation_fixture -v
py -3 -m unittest discover -s tests -v
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "test: add historical TVM1 validation bridge"
```

---

### Task 7: Build the Builder 1.0.4 oracle comparison gate

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/oracle.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_builder_oracle.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/scripts/validate_against_builder.py`

**Interfaces:**

```python
compare_builder_outputs(
    original_builder_output: Path,
    expanded_builder_output: Path,
) -> BuilderCompatibilityReport

run_builder_oracle(
    builder_python: Path,
    original_canlog: Path,
    expanded_canlog: Path,
    capture: Path | None,
    output_dir: Path,
) -> BuilderCompatibilityReport
```

- [ ] **Step 1: Write RED comparison tests.** Normalize only nondeterministic metadata such as generation timestamps/output paths. Do not normalize away frame counts, statuses, profile decisions, database hashes, sync results, or decoded diagnostic evidence.

- [ ] **Step 2: Compare these blocking invariants:**
  - Builder compatibility `supported=true` for both;
  - same TCB raw record count and ordered logical CAN stream;
  - same CAN-ID/direction inventory counts;
  - same BLE alignment/corroboration outcome when CAPTURE is supplied;
  - same external diagnostic transaction count and status-count distribution;
  - same battery-block/diagnostic-action/decoded-diagnostic row counts where the original contains them;
  - same selected vehicle profile/evidence class, allowing only explicitly documented provenance-label differences;
  - no new Builder warning that indicates missing evidence.

- [ ] **Step 3: Add an explicit derived-input gap gate.** If Builder output is materially degraded because regenerated CANLOG lacks `DECODED.CSV` or `SIGNALS.CSV`, stop the plan as FAIL and add only the minimum offline compatibility writer required. Do not waive the difference and do not generate blank stand-ins. The implementation must use the same selected ToyotaHybridCAN database and record its SHA-256.

- [ ] **Step 4: Pin Builder oracle lineage.** The validation report records Builder version `1.0.4`, branch/ref or package hash, database path/hash, Python version, and processing options.

- [ ] **Step 5: Run oracle unit tests and commit.**

```bat
py -3 -m unittest tests.test_builder_oracle -v
py -3 -m unittest discover -s tests -v
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "test: add Builder 1.0.4 compatibility oracle"
```

---

### Task 8: Add production CLI, simple GUI, and observable Windows launcher

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/cli.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/toyota_vehicle_bus_session/gui.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/RUN_SESSION_PREPROCESSOR.bat`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_cli.py`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/tests/test_gui_model.py`

**CLI:**

```text
toyota-session-preprocess validate <native-session-or-zip>
toyota-session-preprocess expand <native-session-or-zip> -o <output-parent> [--no-zip]
toyota-session-preprocess synthesize-native <legacy-canlog-or-folder> -o <output-dir> --validation-only
toyota-session-preprocess oracle <original-canlog> <expanded-canlog> --builder-python <python.exe> [-c CAPTURE] -o <output-dir>
```

- [ ] **Step 1: Write RED CLI exit-code tests.** `0` success, `1` validation/processing failure, `2` usage/configuration error. JSON summary to stdout must include exact output paths and PASS/FAIL status.

- [ ] **Step 2: Implement a minimal Tkinter GUI.** Inputs: native session/ZIP, output folder, `Validate`, `Expand`, `Open Output Folder`. Display stages, current file, raw count, clean/unclean state, warnings, and final PASS/FAIL. The GUI calls the same library functions as CLI; no duplicated parser logic.

- [ ] **Step 3: Implement the BAT launcher with observability.** Use `%~dp0`, prefer `.venv\Scripts\python.exe`, print working directory/Python/version stages, capture `ERRORLEVEL` immediately, print PASS/FAIL, and pause on interactive launch.

- [ ] **Step 4: Run CLI/GUI-model/full tests.**

```bat
py -3 -m unittest tests.test_cli tests.test_gui_model -v
py -3 -m unittest discover -s tests -v
```

- [ ] **Step 5: Build/install smoke.**

```bat
py -3 -m pip wheel . --no-deps -w dist
py -3 -m venv .venv_test
.venv_test\Scripts\python.exe -m pip install --no-index --find-links dist toyota-vehicle-bus-session-preprocessor
.venv_test\Scripts\toyota-session-preprocess.exe --help
```

- [ ] **Step 6: Commit.**

```bash
git add windows/ToyotaVehicleBusSessionPreprocessor
git commit -m "feat: add session preprocessor CLI and GUI"
```

---

### Task 9: Validate real historical sessions and freeze the firmware-go/no-go gate

**Files:**
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/VALIDATION.md`
- Create: `windows/ToyotaVehicleBusSessionPreprocessor/scripts/validate_real_sessions.py`
- Modify: `docs/VALIDATION.md`
- Modify: `README.md`

**Real validation set:**

Use actual source archives, not normalized substitutes:

- **S0141**: known clean session, Builder/Analyzer reference lineage, substantial external diagnostic traffic; prior normalized evidence establishes 1,021,568 persisted raw frames.
- **S0149**: NHW20 session with 1,708,032 raw records and unclean/stale-finalization history; its size necessarily exercises more than one 25 MiB TCB chunk under the existing 24-byte/25 MiB rotation policy.
- **S0128** (or a later clean multi-chunk PHV session if a better source is present at execution time): clean ZVW35 PHV with >1.5M persisted frames and external diagnostic evidence.

If any exact archive is not locally available at execution time, retrieve the identified source from the project/library before substituting another session. Record source SHA-256 in the validation report.

- [ ] **Step 1: Run historical -> synthetic native -> expanded legacy for all three sessions.** No source mutation.

- [ ] **Step 2: Require raw gates.** Per session: every TCB source/destination SHA matches; complete record count matches; logical CAN hash matches; RX/TX counts match; rotation order is continuous; any truncated tail is reported identically.

- [ ] **Step 3: Run Builder 1.0.4 twice per session.** Same Builder build, same database, same CAPTURE/options: once on original CANLOG and once on expanded CANLOG.

- [ ] **Step 4: Require Builder oracle PASS.** Any material evidence loss blocks firmware changes. Do not downgrade a mismatch to warning merely because Builder completes.

- [ ] **Step 5: Run one Analyzer RC8 `process` smoke.** Use one reconstructed session only after Builder gates pass. Confirm the session reaches the normal ready/processed state and retains the same logical CAN evidence identity. Do not duplicate the full three-session Builder campaign in Analyzer.

- [ ] **Step 6: Windows 10 1607 validation.** Run the packaged app on the project’s Win10 1607 machine using one real session. Capture a validation log containing Python path/version, input/output hashes, all gate results, and final ERRORLEVEL.

- [ ] **Step 7: Write the firmware authorization statement.** `VALIDATION.md` must end with exactly one of:

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```

or

```text
TVM1 OFFLINE EXPANDER GATE: FAIL — do not remove legacy firmware SD products.
```

- [ ] **Step 8: Run final verification before claiming completion.**

```bat
py -3 -m unittest discover -s tests -v
py -3 -m compileall toyota_vehicle_bus_session tests
py -3 -m pip wheel . --no-deps -w dist
```

Also run the three real-session oracle campaign and inspect the generated validation JSON/log, not only exit codes.

- [ ] **Step 9: Commit validation/release documentation.**

```bash
git add windows/ToyotaVehicleBusSessionPreprocessor docs/VALIDATION.md README.md
git commit -m "test: validate TVM1 offline expansion contract"
```

---

## Follow-on plans after this gate

These are deliberately not mixed into this implementation because they have different validation boundaries:

1. **Derived Session Products / PLOT Generator:** reusable offline timeline engine for `DECODED.CSV`, `SIGNALS.CSV`, `PLOT.CSV`, improved historical re-decoding, and later Builder/Analyzer integration. It consumes the same native-session API from this package rather than rereading firmware-specific CSVs.
2. **Stripped CAN Logger firmware:** RAW-first write ordering, `SESSION.META`, RAW+META-only SD persistence, pending BLE STOP drain/finalization semantics, queue/load instrumentation, E32R35T+Dorhea profile cleanup, 80 MHz dirty-rectangle TFT updates, and reduced open-file count.
3. **BTH native stream:** receive-only SN75HVD12DR acquisition, target baud/framing validation, frozen BTH raw format, and common-clock correlation.
4. **AVC-LAN native stream:** high-impedance receive-only edge/pulse capture, frozen timing-event raw format, and offline symbol/frame reconstruction.

The firmware plan must not begin removing existing SD products until Task 9 reports the TVM1 offline expander gate as PASS.
