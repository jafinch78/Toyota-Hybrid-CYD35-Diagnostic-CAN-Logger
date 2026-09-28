# Toyota Vehicle Bus Session Preprocessor Validation

Validation date: 2026-09-28

## Current gate state

- Native-session preprocessor CI: **PASS** on `feature/native-session-preprocessor-impl` commit `cd4451bd8e613a420ca224367133dc71c15b84d2`.
- Evidence Builder lineage: **1.0.4**, ref `evidence-builder-v1.0.4`.
- Builder source/package SHA-256: `10507690da14a71370ec66cae508aeacf8955c7664d5d63fca271d0e50775fb9`.
- Builder database: ToyotaHybridCAN **0.5.9**, SHA-256 `d91863e8f845749b9286391b6bb68cc8db0141e4366a042f53550feecc2cb446`.
- Three-session RAW + Builder compatibility campaign: **PASS (3/3)**.
- Windows 10 1607 preprocessor/launcher validation: **PENDING**.
- Analyzer RC7/RC8 smoke: **NOT REQUIRED** for this firmware compatibility boundary.

The machine-readable campaign record is `validation/BUILDER_CAMPAIGN_20260928.json`.

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

## Interpretation

The three historical holdouts demonstrate that the offline preprocessor can reproduce a Builder-compatible package while preserving the authoritative TCB evidence byte-for-byte. Where the historical CSV sidecars omitted response information still present in RAW, the rebuilt package increases usable evidence rather than silently forcing equality with an incomplete sidecar.

This validates the architectural decision to stop treating the firmware-generated diagnostic/decoded CSV products as authoritative. RAW TCB plus TVM1 metadata can be the native acquisition contract, with legacy CSV/JSON products reconstructed offline.

## Remaining release gate

Only the Windows 10 1607 application/runtime check remains. It must validate the preprocessor/launcher on one real session and record Python path/version, source/output hashes, explicit PASS/FAIL stages and final `ERRORLEVEL`.

Until that platform check passes:

```text
TVM1 OFFLINE EXPANDER GATE: FAIL — do not remove legacy firmware SD products.
```

After it passes, with the 3/3 Builder campaign above unchanged:

```text
TVM1 OFFLINE EXPANDER GATE: PASS — firmware SD-product removal may proceed.
```
