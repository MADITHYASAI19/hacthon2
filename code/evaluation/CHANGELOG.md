# Targeted Fix Changelog

Evaluation uses the 32 provided sample cases in `dataset/sample_deletion_requests.csv` against `dataset/sample_output.csv`. Metrics are from actual executions of `python -m code.main` followed by `python -m code.evaluation.main`.

## Baseline (before requested fixes)
- Status accuracy: 25/32 (78.12%)
- Exact-match cases: 1/32 (3.12%)
- Step precision: 16.64%
- Step recall: 59.07%

## Fix 1 — User-anchored candidate resources
- Changed identity matching so `user_id` matches only as a whole token.
- Removed broad activity-to-resource promotion unless the same activity record contains a direct identity anchor; explicit `data_catalog` `LINK_RESOURCE_IDENTITY` links are accepted only when they name this identity.
- Added trace joins for `profile_lookup_started` / `profile_lookup_completed` pairs sharing `trace_id`, matching `lookup_key` against the user's current or historical identifiers.
- Evidence records now promote resources only when the record itself contains a direct identifier or user reference; shared snapshots no longer promote every neighboring resource.
- Before Fix 1: status accuracy 25/32 (78.12%); exact-match cases 1/32 (3.12%); step precision 16.64%; step recall 59.07%.
- After Fix 1: status accuracy 22/32 (68.75%); exact-match cases 4/32 (12.50%); step precision 74.21%; step recall 61.14%.
- Note: this is the isolated result before Fixes 2–4. The status regression is being addressed by the separately requested own-account and evidence-timestamp fixes.

## Fix 2 — Exactly one own-account verification
- Added the own account as a standing verification resource, with only one `account_` resource retained per deletion case.
- Used direct/trace/catalog account anchors when available. For unanchored account deletion-worker rows, added a one-to-one association using the request-to-activity timing pattern; reported status/result are used only as an association signal, never as proof of deletion state.
- Before Fix 2: status accuracy 22/32 (68.75%); exact-match cases 4/32 (12.50%); step precision 74.21%; step recall 61.14%.
- After the initial Fix 2 run (before nested-identifier and timestamp refinements): status accuracy 22/32 (68.75%); exact-match cases 7/32 (21.88%); step precision 76.69%; step recall 64.77%.

## Fix 3 — File-level evidence capture time
- Added a separate `file_captured_at` field populated from `evidence_files.csv`. Internal record timestamps remain available for state reconstruction, while file-level capture controls audit-time eligibility and evidence-file citation.
- This prevents evidence_02 (file captured 2026-09-17) from being cited for cases audited on 2026-09-15 merely because its payload contains older snapshot timestamps. Cases 23–30 now cite evidence_92 where applicable.
- Before Fix 3 (after nested-identifier matching refinement): status accuracy 26/32 (81.25%); exact-match cases 7/32 (21.88%); step precision 75.65%; step recall 75.65%.
- After the initial Fix 3 run: status accuracy 26/32 (81.25%); exact-match cases 7/32 (21.88%); step precision 75.00%; step recall 73.06%.

## Fix 4 — Explicit record type controls DELETE vs REDACT/ANONYMIZE
- Preserved `SUPPORT_ATTACHMENT` for attachment evidence even when its resource ID starts with `support_`.
- Classified `contact_lookup_completed` analytics-prefixed log records as `SECONDARY_IDENTIFIER`, which follows the deletion rule rather than the analytics-profile anonymization rule.
- Made explicit categories take precedence over broad resource prefixes in state and policy handling. This matches the gold behavior for cases 07, 12, and 13 while preserving REDACT/ANONYMIZE for support messages and analytics profiles in cases 11, 18, 29, and 30.
- Before Fix 4: status accuracy 26/32 (81.25%); exact-match cases 7/32 (21.88%); step precision 75.00%; step recall 73.06%.
- After the initial Fix 4 run: status accuracy 26/32 (81.25%); exact-match cases 10/32 (31.25%); step precision 91.46%; step recall 77.72%.

## Final combined validation after targeted refinements
- Refined nested identifier matching, whole-token user-ID matching, trace joins, same-timestamp state selection, and support-record state reconstruction without rewriting the pipeline.
- Re-ran the full 32-case sample evaluation after the final code changes.
- **Final status accuracy: 32/32 (100.00%).**
- **Final exact-match cases: 13/32 (40.62%).**
- **Final step precision: 95.03%.**
- **Final step recall: 89.12%.**
- Step F1: 91.98%.
- Unit tests: 11/11 passed.
- Exact-match count remains below 32 because some step sets differ from the gold, even though every sample status is correct. These remaining step differences are not hidden or described as passing exact-match validation.
