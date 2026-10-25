# Evaluation Report

## Method

The public 32-row request set was rerun with `python code/main.py --requests dataset/sample_deletion_requests.csv --out sample_out.csv --offline`. Results below compare parsed JSON arrays, not CSV string formatting. A semantic step match requires equality of `phase`, `system_id`, `resource_id`, `operation`, `state`, and `evidence_id`; `step_no` is positional metadata. Field accuracy is position-aligned within each case and penalizes unmatched extra or missing steps. Sequence accuracy is micro LCS length divided by gold-step count.

## Measured public-sample results

| Metric | Result |
|---|---:|
| Case-level deletion-status accuracy | 32/32 (100.00%) |
| Row exact match | 14/32 (43.75%) |
| Gold / predicted semantic steps | 193 / 183 |
| Exact-step precision | 163/183 (89.07%) |
| Exact-step recall | 163/193 (84.46%) |
| Exact-step F1 | 86.70% |
| Sequence accuracy (micro LCS ratio) | 163/193 (84.46%) |

### Field-level accuracy

| Field | Correct / compared positions | Accuracy |
|---|---:|---:|
| `phase` | 176/197 | 89.34% |
| `system_id` | 157/197 | 79.70% |
| `resource_id` | 146/197 | 74.11% |
| `operation` | 153/197 | 77.66% |
| `state` | 156/197 | 79.19% |
| `evidence_id` | 171/197 | 86.80% |

## Optional local media extraction comparison (2026-10-25)

Both runs used the deterministic offline pipeline. The baseline explicitly set
`USE_PDF_EVIDENCE=0` and `USE_IMAGE_OCR=0`; the comparison set both to `1`.
The baseline and media output were saved separately as
`evaluation_baseline_sample.csv` and `evaluation_media_sample.csv`; the
submission `output.csv` was not overwritten.

| Metric | Baseline | PDF/OCR enabled | Change |
|---|---:|---:|---:|
| Status accuracy | 32/32 (100.00%) | 32/32 (100.00%) | 0 |
| Exact rows | 14/32 (43.75%) | 14/32 (43.75%) | 0 |
| Gold / predicted semantic steps | 193 / 180 | 193 / 183 | +3 predicted |
| Exact-step precision | 160/180 (88.89%) | 163/183 (89.07%) | +0.18 pp |
| Exact-step recall | 160/193 (82.90%) | 163/193 (84.46%) | +1.55 pp |
| Exact-step F1 | 85.79% | 86.70% | +0.91 pp |
| Sequence accuracy (micro LCS) | 82.90% | 84.46% | +1.55 pp |

The enabled run extracted embedded text from all 4 PDFs. It discovered four
resource IDs, but only `support_001` from `evidence_58` had a valid
user-specific anchor before the applicable audit cutoff. That record added a
supported finding, remediation, and verification to `case_07`, accounting for
all three new exact semantic steps. The three remaining PDF identifiers were
synthetic document IDs or lacked an eligible identity anchor and therefore did
not enter a case view. This is intentional: more extracted strings alone do
not create findings.

OCR was requested for 11 PNG files, but this environment has no `tesseract`
executable on `PATH`; 11 structured `executable_missing` warnings were written
to `media_sample_diagnostics.json`. No OCR text, OCR-derived IDs, or OCR-driven
case changes were claimed. PDF/OCR diagnostics are structured JSON and retain
the manifest file IDs and source filenames.

## Per-case public-sample results

| Case | Status match | Exact match | Note |
|---|---|---|---|
| case_01 | yes | yes | — |
| case_02 | yes | yes | — |
| case_03 | yes | no | Missing anonymized analytics verification. |
| case_04 | yes | no | No grounded account resource supports the sample's account step. |
| case_05 | yes | yes | — |
| case_06 | yes | yes | — |
| case_07 | yes | no | Extra/misaligned account-related steps. |
| case_08 | yes | yes | — |
| case_09 | yes | no | Account event association differs. |
| case_10 | yes | no | Account evidence citation differs. |
| case_11 | yes | yes | — |
| case_12 | yes | yes | — |
| case_13 | yes | yes | — |
| case_14 | yes | yes | — |
| case_15 | yes | yes | — |
| case_16 | yes | yes | — |
| case_17 | yes | no | Additional trace-derived step. |
| case_18 | yes | no | Account event association differs. |
| case_19 | yes | yes | — |
| case_20 | yes | no | Account event association differs. |
| case_21 | yes | no | Account association and analytics verification differ. |
| case_22 | yes | yes | — |
| case_23 | yes | no | Account event association differs. |
| case_24 | yes | no | Retained audit verification missing. |
| case_25 | yes | no | Account event association differs. |
| case_26 | yes | no | Account association and analytics verification differ. |
| case_27 | yes | no | Account association and analytics verification differ. |
| case_28 | yes | no | Account event association differs. |
| case_29 | yes | no | Account event association differs. |
| case_30 | yes | no | Retained audit verification missing. |
| case_31 | yes | no | Account event association differs. |
| case_32 | yes | yes | — |

## Custom evaluation cases

These cases were exercised with the same deterministic components and use only fictional participant data already present in the public fixture.

### 1. Non-English, non-deletion request

**Input:** `case_id=custom_es_access`, `email=amina.elmasri@gmail.com`, `requested_at=2026-08-18T09:14:00Z`, `reported_status=NOT_STARTED`, `reported_at=2026-08-18T09:14:00Z`, `audit_at=2026-09-03T11:30:00Z`, `request_text="No deseo borrar mi cuenta; solo quiero una copia de mis datos."`

**Expected:** `NOT_APPLICABLE`, `steps_json=[]` because the request explicitly says not to delete and requests access. **Actual:** `NOT_APPLICABLE`, `steps_json=[]`. **Result:** PASS.

### 2. Tombstone redaction

**Input:** `case_id=custom_tombstone`, `email=addo.kofi@gmail.com`, `requested_at=2026-09-03T12:00:00Z`, `reported_status=PARTIALLY_COMPLETE`, `reported_at=2026-09-06T12:00:00Z`, `audit_at=2026-09-15T12:00:00Z`, `request_text="Delete my account but preserve only the internal deleted-account reference required for retained records."`

**Expected:** `INCOMPLETE`, with a `REPORT_EXPOSED_PII` finding and `REDACT_RECORD` remediation for the tombstone, while retained audit data remains present. **Actual:** `INCOMPLETE`; the run reported `tombstone_9178` exposed PII, planned redaction, and retained `audit_record_7068`. **Result:** PASS.

### 3. Active data-flow risk

**Input:** `case_id=custom_flow`, `email=lucia-torres@gmail.com`, `requested_at=2026-08-21T12:00:00Z`, `reported_status=COMPLETE`, `reported_at=2026-08-22T12:00:00Z`, `audit_at=2026-09-15T12:00:00Z`, `request_text="Delete my account and ensure no active integration can send my personal data elsewhere."`

**Expected:** `INCOMPLETE`, with `REPORT_ACTIVE_DATA_FLOW`, then `DISABLE_DATA_FLOW` and `VERIFY_DATA_FLOW_DISABLED`. **Actual:** `INCOMPLETE`; the run found active `data_flow_9846`, planned disablement, and included the required verification. **Result:** PASS.

## Failures found

- Earlier output fabricated 95 padded account IDs that were not present in participant-facing data.
- The earlier validator imposed an unsupported requirement that every non-NA case contain an account verification, encouraging fabrication.
- Some sample rows remain non-exact because direct identity evidence does not always disambiguate a deletion-worker account event, or because the public sample includes an account step lacking a corpus-grounded resource ID.
- Several non-exact rows differ by missing or additional retained/analytics verification steps.

## Improvements made

- Fabricated resource IDs: **95 -> 0**.
- Sample exact matches: **10/32 -> 14/32**; status accuracy remains **32/32**.
- Empty `system_id` and required-evidence citation defects were fixed; the final validator reports zero empty system/resource IDs, zero empty evidence IDs on complete-case steps, and zero invalid citations.
- Account IDs are now opaque evidence/activity values. The code never derives an account resource ID from a user ID.
- Trace joining recognizes `subject_ref`, while file-level evidence timestamps, whole-token user-ID matching, and record-category precedence remain enforced.
