# Ghost Data Still Exists

This submission audits deletion requests against participant-visible identity, activity, policy, and evidence data. It writes a deterministic `output.csv` containing one result per request.

## Architecture

```text
deletion request + identity history
              |
              v
intent classification -> evidence extraction -> state at audit_at
              |                    |                 |
              +--------------------+-----------------+
                                   v
                         policy evaluation
                                   |
                                   v
                    ordered findings/remediation/verification
                                   |
                                   v
                              output.csv
```

## Requirements

- Python 3.10+ (tested with Python 3.12)
- Standard library only; no package installation is required.

Environment variables are not required for an offline run. Optional Grok intent classification uses `XAI_API_KEY` and `GROK_MODEL`; copy `.env.example` to a local, uncommitted `.env` and replace its placeholders. `.env` and the Grok cache are ignored by Git. Only intent classification can use Grok; all evidence, identity, state, policy, and planning work is deterministic code.

Media evidence is opt-in. `USE_PDF_EVIDENCE=1` enables embedded-text PDF extraction with `pypdf`; `USE_IMAGE_OCR=1` enables local PNG/JPEG OCR with Pillow, `pytesseract`, and the Tesseract executable. `USE_MEDIA_EVIDENCE=1` remains a backwards-compatible shortcut that enables both unless an individual setting overrides it. Leaving all flags unset (or setting them to values other than `1`) retains the deterministic baseline: PDFs produce no observations and images use only their existing filename fallback. The submitted `output.csv` was generated with PDF and OCR extraction on: all 4 PDFs and all 11 images produced text, Tesseract was available, and diagnostics contained no warnings.

On the public sample, media-off achieved status 32/32, exact 14/32, precision 88.89%, and recall 82.90%. PDF-on improved precision to 89.07% and recall to 84.46%. PDF plus OCR retained status 32/32 and exact 14/32 with precision 89.07% and recall 84.46%; OCR ran on all 11 images but did not change a public-sample result.

Install the optional local dependencies with `python -m pip install pypdf pillow pytesseract`. OCR additionally requires the Tesseract executable and language data installed locally and visible on `PATH` (`tesseract --list-langs`). No evidence is ever sent to an external service. If an enabled dependency is missing or a file cannot be read, the run reports a structured warning and can write it to JSON with `--media-diagnostics`.

## Run

From the repository root:

```bash
# Full 518-request run
python code/main.py

# Force a deterministic offline run
python code/main.py --offline

# Optional, independently enabled local extraction (PowerShell)
$env:USE_PDF_EVIDENCE="1"; $env:USE_IMAGE_OCR="1"
python code/main.py --offline --out media_output.csv --media-diagnostics code/evaluation/media_diagnostics.json

# Deterministic baseline, explicitly disabling both extractors
$env:USE_PDF_EVIDENCE="0"; $env:USE_IMAGE_OCR="0"
python code/main.py --offline --out baseline_output.csv

# Force optional Grok use for intent classification (falls back offline on API errors)
python code/main.py --use-llm

# Make one safe Grok connectivity check; never prints the API key
python code/main.py --check-llm

# Public 32-request sample run
python code/main.py --requests dataset/sample_deletion_requests.csv --out sample_out.csv --offline

# Sample measurement and fabricated-ID check
python quick_check.py

# Contract validator
python validate_output.py

# Unit tests
python -m unittest discover -s code/tests -t .
```

The evaluation results and final-run usage record are in `code/evaluation/`.

## Design decisions

- **Claims are not truth.** Reported workflow statuses and activity results are treated as leads; extracted evidence establishes the state.
- **Audit-time reconstruction.** Records and manifest capture times after `audit_at` are excluded.
- **Identity history.** Current and audit-log email, phone, hash, and whole-token user-ID values are resolved before evidence matching.
- **Tombstones and retention.** Account tombstones retain only permitted stable references; direct identifiers trigger redaction. Security and legal-retention records are verified as present rather than deleted.
- **Replicas and recreation risks.** Evidence from replicas can establish a remaining record. Active integrations and unsafe restore paths are remediated before dependent record deletion.
- **Account matching.** Account resources are opaque IDs sourced from evidence or `system_activity.csv`. When direct identity, trace, or catalog evidence does not identify one, the program joins an eligible `deletion_worker` `DELETE_RECORD` event targeting `account_service` within the request-to-audit window, preferring the event nearest the workflow report time. This is based on timestamps and dataset values, never on case IDs or a derived user-ID pattern.

## Known limitations

The offline intent classifier is rule-based and supports the represented languages; unusual wording can require future expansion. Account-event timing is an evidence-backed heuristic when no direct account link exists. The final run is honestly reported in `code/evaluation/usage_report.md`: it is offline unless both environment variables are configured or `--use-llm` is selected.

## Package

Build the submission archive from the repository root with the included Python
packager:

```bash
python build_zip.py
```

The archive uses forward-slash paths and intentionally excludes `dataset/`, output artifacts, caches, credentials, and nested archives.
