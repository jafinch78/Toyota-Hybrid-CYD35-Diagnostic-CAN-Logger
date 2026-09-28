# Toyota Vehicle Bus Session Preprocessor Validation

Validation date: 2026-09-28

## Current gate state

- Native-session preprocessor CI: **PASS** on the tested implementation lineage beginning at `cd4451bd8e613a420ca224367133dc71c15b84d2`; subsequent commits on `feature/native-session-preprocessor-impl` are validation/documentation checkpoints unless separately noted.
- Evidence Builder compatibility boundary: **1.0.4**.
- Three-session RAW + Builder compatibility campaign: **PASS (3/3)**.
- Windows 10 1607 preprocessor/launcher validation: **PASS**.
- Analyzer RC7/RC8 smoke: **NOT REQUIRED** for this firmware compatibility boundary.
- Firmware SD-product removal authorization: **PASS**.

Machine-readable evidence:

- `validation/BUILDER_CAMPAIGN_20260928.json`
- `validation/WINDOWS_1607_VALIDATION.json`
- `validation/WINDOWS_1607_VALIDATION.log`

Task 9 authorization is governed by `docs/superpowers/plans/2026-09-28-task9-builder-only-gate-amendment.md`: the three required Builder gates plus the Windows 10 1607 runtime gate are the complete firmware authorization boundary. No Analyzer smoke report is an input.

## Pertinent Evidence Builder lineage

The latest pertinent standalone Builder runtime patch for this boundary is `EvidenceBuilder_v1.0.4_RC7_CanonicalDB_Patch_v1.0.1`.

- Patch ZIP SHA-256: `bffd76926a635b69fe9d0ce2f5839b5b82264ff4794704a8db925c7118a1184a`.
- It replaces only `toyota_can_processor/database.py` and `toyota_can_processor/decoding.py`.
- It intentionally leaves `processor.py`, `tcb1.py`, `sync.py`, broadcast decoding, Broadcast Discovery, OCR/media, GUI, and CAN-transmission policy unchanged.
- Later Matcher-only patches are not additional Task 9 firmware-gate requirements.

The original three-session compatibility campaign records the exact Builder/database oracle actually used for that campaign in `BUILDER_CAMPAIGN_20260928.json`. The RC7 CanonicalDB patch is documented separately because it changes database/formula compatibility, not the CANLOG input/session orchestration contract being authorized here.

## Real-session Builder campaign

| Session | RAW records | RAW gate | Builder 1.0.4 gate | Notes |
|---|---:|---|---|---|
| S0141 | 1,021,568 | PASS | PASS | Diagnostic-heavy NHW20 reference. Reconstructed RAW responses improve the historical request-only sidecar without changing authoritative CAN evidence. |
| S0149 | 1,708,032 | PASS | PASS | Two TCB chunks; unclean/stale-finalization case. Rotation, direction, record count and hashes remain identical. |
| S0128 | 1,568,001 | PASS | PASS | Two TCB chunks; ZVW35 PHV external-diagnostic holdout. Negative-response semantics remain preserved while missing RAW responses are recovered. |

### S0141

Source CANLOG SHA-256: `0034c9e165a8daff2a53473fc20177a19ba8c3d9b68dd691b73cb178dad24edd`  
Source CAPTURE SHA-256: `5aaf3569be3ce1b6fbd894d84f0fb58a60ce9ef310ae46ebb3d66a29b560d3b6`  
Logical TCB record-stream SHA-256: `a9d96bfc8ec9f3ad575dac0f6c82798f9fd73793c457fa6c276b983dfd345089`  
`RAW_000.TCB` SHA-256: `824359f8d18b80d863637f7e3f41e8c26d56f1c57f9c06f23aff626efaf148ab`.

Builder original/expanded decoded rows: **5,286 / 8,505**. External diagnostics changed from **11,406 historical request-only transactions** to **11,448 reconstructed transactions**, including **10,780 OK**, **57 NO_RESPONSE**, **569 INCOMPLETE_SEQUENCE**, and **42 UNMATCHED_RESPONSE**. This is accepted only because Builder independently verifies identical authoritative RAW and non-decreasing evidence.

### S0149

Source CANLOG SHA-256: `e8f844844e696d8e78f6b13c67238813d142b5c86b7b8b65692a263fa2530f90`  
Source CAPTURE SHA-256: `160268faf1130fe16499b594386ec22717a193e9d1276f98ffec058148fa32da`  
Logical TCB record-stream SHA-256: `cf21f7c26666cc5e991aa4455a9198a57347dd310452f7e95029a673b9e979c8`.

- `RAW_000.TCB`: 1,093,248 records, SHA-256 `8e2e17db542bd94622122d65e8e71c2b4929ce4575ecf8a9641237585fa884de`.
- `RAW_001.TCB`: 614,784 records, SHA-256 `3c19b4738f0e25525ba747aea327e4860c3fda3bfdcaca8412692a7962fe1a6c`.

Builder original/expanded decoded rows: **9,215 / 15,007**. The historical diagnostic sidecar had 2,666 transactions; reconstruction produced 2,678 while preserving request-backed counts and improving successful-response recovery under the fail-closed RAW-response rule.

### S0128

Source CANLOG SHA-256: `0bd16c28047dc0d455ef707b8dd6fdc34ca6f62d42ff691fd4b16a3dc1e773ef`  
Source CAPTURE SHA-256: `fdce59cceb4f7731fe9acc4b1312b41fa7b30bb5cf6c2affcbd472051f7d6807`  
Logical TCB record-stream SHA-256: `da889e91895cbb77319477dc10bd896bb1b9e0045b8667ec9f3ea0ce8238ba81`.

- `RAW_000.TCB`: 1,093,114 records, SHA-256 `6b369bcb0911a9562b36a167e72304661528a45729f711cea54eb27744447a9f`.
- `RAW_001.TCB`: 474,887 records, SHA-256 `9e80a25ab450ae380a2b65bcab8634def7e442837bee83286942e7a9eeef6849`.

Builder original/expanded decoded rows: **8,941 / 13,543**. The transaction count remains **2,651**; the existing `NEGATIVE_RESPONSE_12` is preserved while RAW reconstruction reduces NO_RESPONSE from 235 to 4 and raises OK from 2,279 to 2,526.

## Windows 10 1607 runtime gate

The packaged preprocessor/launcher was run on the required target platform against the real S0141 source session.

- Platform: `Windows-10-10.0.14393-SP0` / Windows build **14393**.
- Python: **3.12.7 x64**.
- Session: **S0141**.
- Source CANLOG SHA-256: `0034c9e165a8daff2a53473fc20177a19ba8c3d9b68dd691b73cb178dad24edd`.
- RAW records: **1,021,568** source = native = expanded.
- RX/TX: **1,021,568 / 0** source = native = expanded.
- Logical record SHA-256: `a9d96bfc8ec9f3ad575dac0f6c82798f9fd73793c457fa6c276b983dfd345089` source = native = expanded.
- `RAW_000.TCB` SHA-256: `824359f8d18b80d863637f7e3f41e8c26d56f1c57f9c06f23aff626efaf148ab` source = native = expanded.
- Truncated tail bytes: **0**.
- `SESSION.META` SHA-256: `e6831d85bade4baa466fb57b18605ae8b6cab4884f0329faea22352d884eaf17`.
- Expanded CANLOG SHA-256: `a2368990e8983484778e5019ac05e7e7f357bf342d5ec18bfffa69a6f0a21919`.
- Failures: **0**.
- Final `ERRORLEVEL`: **0**.
- Runtime status: **PASS**.

Retained evidence hashes:

- `validation/WINDOWS_1607_VALIDATION.json`: SHA-256 `5246090d1d05ae30514798abdf63cb0c3ca54381ebdb84540a25a536c4a446f1`.
- `validation/WINDOWS_1607_VALIDATION.log`: SHA-256 `9d293ee489c6c5cb0d4fb4b2d266ccb9bac1475bb5602deb562f56cf32d2839f`.

## Interpretation

The three historical holdouts demonstrate that the offline preprocessor can reproduce a Builder-compatible package while preserving authoritative TCB evidence byte-for-byte. The target-machine S0141 run independently demonstrates that the packaged application can perform the legacy -> synthetic TVM1 -> expanded legacy round trip on Windows 10 1607 without changing the RAW evidence stream.

Where historical CSV sidecars omitted response information still present in RAW, the rebuilt package increases usable evidence rather than silently forcing equality with an incomplete sidecar. This validates the architectural decision to stop treating firmware-generated diagnostic/decoded CSV products as authoritative. RAW TCB plus TVM1 metadata are authorized as the native acquisition contract, with legacy CSV/JSON products reconstructed offline.

## Final authorization

All four required Task 9 conditions are PASS:

1. S0141 RAW identity + Builder compatibility: **PASS**.
2. S0149 RAW identity + Builder compatibility: **PASS**.
3. S0128 RAW identity + Builder compatibility: **PASS**.
4. Windows 10 1607 packaged runtime validation: **PASS**.

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```
