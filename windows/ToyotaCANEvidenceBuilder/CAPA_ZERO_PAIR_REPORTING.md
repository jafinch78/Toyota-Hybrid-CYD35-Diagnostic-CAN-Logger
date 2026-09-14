# CAPA: zero label-based CAN/OCR reporting

## Root cause

Evidence Builder 1.0.3 accurately counted rows written to its label-based
correlation file but displayed the result as the broad term `CAN/OCR pairs`.
The report did not expose prerequisite gates or the separate graph-to-CAN
channel. Its correlator also required exact database OCR aliases and reused the
nearest OCR frame for multiple CAN rows. A displayed zero therefore described
several different conditions and was not proof that a session lacked evidence.

## Diagnosed sessions

| Session | Root cause of reported zero |
| --- | --- |
| S0047 | No database-matched decoded rows. The 93 candidate response shapes establish observations, not validated semantics that can be paired. |
| S0051 | 4,896 decoded rows lacked applicable OCR aliases. Fifty-five graph/CAN matches existed in a separate channel and were omitted from the label-pair count. |
| S0053 | 3,837 decoded rows lacked an app-specific comparison schema despite readable Autel keyframes. |
| S0055 | 1,008 decoded rows lacked applicable OCR aliases; the camera recording of another display produced no structured graph observations. |
| S0056 | 592 decoded rows existed but no OCR output existed, so a pair count was not applicable. Queue drops remain a separate quality condition. |
| S0060 | Hybrid Assistant content was routed as Dr. Prius, preventing supported structured observations. |
| S0061 | Dr. Prius text was readable, but AP200-oriented aliases and absent comparable block/pack decoded rows left no valid pair schema. |

## Corrective action implemented in 1.0.4

1. The report names the metric `Label-based CAN/OCR pairs` and displays graph
   CAN matches and effective evidence events beside it.
2. Every zero receives a cause code: no decoded fields, no OCR, no database OCR
   aliases, rejected numeric/unit semantics, or no safe time-window overlap.
3. App/layout is detected per frame and summarized into contiguous segments.
   Detected evidence takes precedence over a conflicting requested profile.
4. Pairing uses per-field fixed-lag selection and one-to-one assignment; neither
   an OCR observation nor CAN sample is reused within a field.
5. Unique OCR frames, independent time buckets, time span, dynamic range,
   outliers, and semantic rejections are recorded.
6. Confirmation requires strengthened sample, time, range, agreement, RMSE,
   median-error, unit, bounds, and expected-value gates.

## Preventive controls

1. S0060 routing, duplicate archive ambiguity, hash deduplication, OCR-frame
   non-reuse, yellow-guide crop, and high-tolerance/high-error rejection have
   automated regression coverage.
2. Human-readable outlier, rejected-semantic, counter, and field-decision panels
   remain adjacent to the summary counts.
3. Newly created media proxies are never selected for OCR until matched-frame
   comparison passes.
4. Candidate registry records remain metadata-only and cannot enter decoder
   lookup, active polling, automatic promotion, or automatic database updates.
5. Local results are advisory. Database changes still require external review
   and a separately versioned database release.

## Remaining release gate

The source package is validated in the audit environment. The PyInstaller
executable still requires build and smoke testing on the target Windows 10 1607
(build 14393) system before the executable is called validated.
