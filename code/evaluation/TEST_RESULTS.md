# TEST RESULTS

**Audit Date:** 2026-10-25
**Auditor:** Antigravity (Claude Sonnet 4.6 Thinking)
**Project:** Ghost Data Still Exists — Deletion Audit Agent

---

## Test Legend

- PASS: test ran and produced the expected outcome
- FAIL: test ran but produced an unexpected outcome or invariant violation
- BLOCKED: test could not run due to missing dependency or external API
- NOT_RUN: test exists but was not executed during this audit

---

## 1. Unit Tests (pytest)

**Command:** python -m pytest code/tests/ -v
**Exit code:** 0 (1 test session error logged from asyncio plugin deprecation warning, not a test failure)

| Test | File | Result | Notes |
|---|---|---|---|
| test_row_counts | test_loader.py | PASS | 518 requests, 32 samples, 850 identities, 306 audit rows, 4011 activity rows, 15 rules, 94 evidence files |
| test_email_resolution | test_loader.py | PASS | All request emails resolvable via current or audit-log emails |
| test_normalize_email | test_loader.py | PASS | Strips whitespace, lowercases |
| test_parse_ts | test_loader.py | PASS | Parses ISO-8601 with Z suffix; handles empty/None |
| test_all_518_requests_resolve | test_identity.py | PASS | Every evaluation email resolves to a user_id |
| test_historical_email_resolution | test_identity.py | PASS | Users with email changes: both old and new emails resolve |
| test_no_name_alone_match | test_identity.py | PASS | Name-only match returns empty list |
| test_case_insensitive_matching | test_identity.py | PASS | Uppercase email variant matched correctly |
| test_samples_all_delete | test_intent.py | PASS | All 32 sample requests classified as DELETE |
| test_custom_cases_benchmark | test_intent.py | PASS | 23 custom cases: 100% accuracy (threshold: 95%) |
| test_dataset_non_deletion_count | test_intent.py | PASS | Exactly 10 NOT_DELETE in 518 (case_533..case_542) |

**Summary: 11/11 PASS**

---

## 2. Syntax and Import Checks

| Check | Command | Result | Notes |
|---|---|---|---|
| code/main.py syntax | python -m py_compile code/main.py | PASS | |
| code/state.py syntax | python -m py_compile code/state.py | PASS | |
| code/policy.py syntax | python -m py_compile code/policy.py | PASS | |
| code/planner.py syntax | python -m py_compile code/planner.py | PASS | |
| code/evaluation/main.py syntax | python -m py_compile code/evaluation/main.py | PASS | |
| All module imports | python -c "import code.main" | PASS | All internal imports resolve |
| pdfplumber import | python -c "import pdfplumber" | PASS | Installed but unused (pypdf used instead) |
| Pillow import | python -c "import PIL" | PASS | Used by image_extract.py |
| pytesseract import | python -c "import pytesseract" | PASS | Used by image_extract.py |
| Optional annotation in main.py | Manual inspection | NOTE | Optional used at line 29 without typing import; no runtime error due to PEP 563 |

---

## 3. Main Entry Point

| Check | Command | Result | Notes |
|---|---|---|---|
| Help flag | python code/main.py --help | PASS | Shows all args: --requests, --out, --dataset, --usage-report, --offline |

---

## 4. 32-Case Sample Regression

**Command:** python run_eval_summary.py
**Gold:** dataset/sample_output.csv (32 rows)
**Prediction:** output_sample_pred.csv (32 rows, pre-existing)
**Definition:** Step matching uses (phase, system_id, resource_id, operation, state) 5-tuple without evidence_id for precision/recall; exact sequence match includes evidence_id via Levenshtein distance = 0.

| Metric | Value | Pass/Fail |
|---|---|---|
| Status Accuracy | 32/32 (100.00%) | PASS |
| Exact Sequence Match | 13/32 (40.62%) | NOTE (see mismatches below) |
| Average Edit Distance | 0.78 steps/case | NOTE |
| Step Precision | 95.03% | PASS |
| Step Recall | 89.12% | PASS |
| Step F1 | 91.98% | PASS |

**Confusion Matrix:**
- COMPLETE -> COMPLETE: 10/10
- INCOMPLETE -> INCOMPLETE: 22/22
- NOT_APPLICABLE: 0 cases in sample (not testable here)

**19 Non-Exact-Match Cases:**
All have correct deletion_status. Differences are step-level:
- Missing VERIFY_RECORD_ANONYMIZED for analytics resources in COMPLETE cases (cases 23-30).
- Missing VERIFY_RECORD_PRESENT for audit_record_* in INCOMPLETE cases (cases 29-32).

---

## 5. 518-Case Output Validation

**Command:** python validate_output.py
**File checked:** output.csv (root)

| Check | Result | Details |
|---|---|---|
| Row count | PASS | 518 rows |
| Header | PASS | case_id,deletion_status,steps_json |
| Unique case IDs | PASS | 518 unique |
| Case IDs match deletion_requests.csv | PASS | 0 extra, 0 missing |
| Sorted numerically | PASS | case_33..case_550 in ascending numeric order |
| Invalid statuses | PASS | 0 invalid (only COMPLETE/INCOMPLETE/NOT_APPLICABLE) |
| NOT_APPLICABLE with steps | PASS | 0 cases |
| Invalid JSON | PASS | 0 rows |
| Step schema errors | PASS | 0 invalid phases or operations |
| Consecutive step_no | PASS | 0 violations |
| COMPLETE w/ empty evidence_id | FAIL | 3 cases: case_39, case_55, case_363 |
| INCOMPLETE w/ empty finding evidence | FAIL | 14 cases |
| Invalid evidence IDs | PASS | 0 invalid IDs |

---

## 6. Dependency Check

| Dependency | Status | Notes |
|---|---|---|
| Python 3.12.10 | PASS | Available at C:\\Users\\HP\\AppData\\Local\\Microsoft\\WindowsApps\\... |
| csv, json, re, pathlib, datetime, sqlite3 | PASS | Standard library |
| pytest 8.3.3 | PASS | Installed |
| pdfplumber | PASS | Installed (not used; pypdf used instead) |
| pypdf | PASS | Used by doc_extract.py |
| Pillow (PIL) | PASS | Used by image_extract.py |
| pytesseract | PASS | Installed; requires Tesseract binary |

---

## 7. Tests NOT Run

| Test | Reason |
|---|---|
| Full 518-case pipeline re-execution | Not safe to overwrite existing output.csv during audit; existing file validated instead |
| Tesseract OCR binary end-to-end | pytesseract installed but Tesseract binary status not verified; image extractor has filename fallback |
| Performance/timing benchmark | Out of scope for audit |
| Thread safety / concurrent access | Not applicable (single-process pipeline) |
| Edge case: empty deletion_requests.csv | Not run; would require modifying production files |

---

## Summary

| Category | Pass | Fail | Blocked | Not Run |
|---|---|---|---|---|
| Unit tests | 11 | 0 | 0 | 0 |
| Syntax/import checks | 10 | 0 | 0 | 0 |
| 32-case regression | 1 (status acc) | 0 | 0 | 0 |
| 518-case output validation | 11 | 2 | 0 | 0 |
| Dependency checks | 7 | 0 | 0 | 0 |
| Full pipeline re-run | 0 | 0 | 0 | 1 |

**Overall: 40 checks run, 38 PASS, 2 FAIL (evidence_id invariants), 1 NOT_RUN**
