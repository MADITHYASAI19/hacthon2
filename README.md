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

## Run

From the repository root:

```bash
# Full 518-request run
python code/main.py

# Force a deterministic offline run
python code/main.py --offline

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

Run this exact command from a shell with `zip` available:

```bash
zip -r code.zip README.md code -x "*/__pycache__/*" "*/.venv/*" "*/.cache/*" "*/.git/*"
```

The archive intentionally excludes `dataset/`, output artifacts, caches, credentials, and nested archives.
