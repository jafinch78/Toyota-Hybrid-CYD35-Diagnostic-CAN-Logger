# Validation — Toyota CAN Evidence Analyzer v0.2.0-rc1

**Deployment status:** PRE-ALPHA branch/Drive deployment approved by user; not merged to `main`.

## Verification pass A — functional and resource hygiene

- 38/38 unit/regression tests passed.
- `ResourceWarning` promoted to error; no unclosed SQLite warnings remained.
- Legacy v0.1 behavior, typed proposals, multi-axis confidence, coverage, acquisition gaps, research orchestration, and Builder S0093 contract are covered.

## Verification pass B — real-reference and deterministic smoke

- Canonical v0.9.12: 208 definitions.
- Proposed v0.9.13/v0.9.14: 209 definitions each and retained as PROPOSED.
- Master Session Index: 54 rows through S0140.
- Successful Decode Method Registry: 140 rows.
- Method Exhaustion Matrix: 107 rows.
- Seven first-class inputs were pre/post SHA-256 verified immutable.
- S0093 synthetic contract fixture imported 4 passive observations. This fixture is synthetic acceptance data, not vehicle evidence.
- Registered rolling-counter method completed with no survivor, persisted an exhaustion record, then an identical rerun returned `SKIPPED_EXHAUSTED`.
- 13 deterministic CSV/JSON/HTML/Markdown outputs matched byte-for-byte across identical real-reference runs. SQLite and ZIP containers are excluded because database import timestamps and ZIP container metadata are run-local; deterministic semantic exports are compared directly.
- S0094 real Master Session provenance retained 633,635 raw records and empty-MANIFEST warning while no S0094 decoded Builder session was fabricated.

## Verification pass C — clean package

- Wheel built successfully: `toyota_can_evidence_analyzer-0.2.0rc1-py3-none-any.whl`.
- Wheel SHA-256: `496308822b76e72f0c19b2312f045ffad28194de491b77ef927769262fedc1ab`.
- Installed into a fresh virtual environment with no project source path.
- Runtime version imported as `0.2.0rc1`.
- Legacy CLI parsed.
- 12 registered executable methods loaded.

## Native Windows deployment gate

**NOT RUN in the Linux sandbox.** The updated Windows 3.10/3.12 build scripts are statically checked and run the unit suite before PyInstaller, but a Windows PyInstaller executable must still be built and launched on the supported target before alpha/production promotion.
