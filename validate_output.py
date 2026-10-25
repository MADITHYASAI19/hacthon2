"""Comprehensive output.csv validation script checking all challenge contracts and invariants."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent

print("=" * 80)
print("FULL OUTPUT.CSV VALIDATION")
print("=" * 80)

out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (ROOT / "output.csv")
if not out_path.exists():
    print(f"CRITICAL ERROR: {out_path} not found.")
    sys.exit(1)

with open(out_path, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Check header
expected_header = ["case_id", "deletion_status", "steps_json"]
with open(out_path, "r", encoding="utf-8") as f:
    actual_header = next(csv.reader(f))
header_ok = actual_header == expected_header
print(f"1. Header: {actual_header} -> {'OK' if header_ok else 'FAIL'}")

# Check row count
total_rows = len(rows)
print(f"2. Row count: {total_rows} (expected: 518) -> {'OK' if total_rows == 518 else 'FAIL'}")

# Check unique case IDs & matching requests
with open(ROOT / "dataset" / "deletion_requests.csv", "r", encoding="utf-8") as f:
    expected_ids = [r["case_id"] for r in csv.DictReader(f)]
expected_id_set = set(expected_ids)
ids = [r["case_id"] for r in rows]
id_set = set(ids)

extra = id_set - expected_id_set
missing_from_output = expected_id_set - id_set
print(f"3. Unique case IDs: {len(id_set)} (expected: 518) -> {'OK' if len(id_set) == 518 else 'FAIL'}")
print(f"4. Case IDs match deletion_requests.csv: extra={len(extra)}, missing={len(missing_from_output)}")

# Check sorted order
def case_num(cid: str) -> int:
    parts = cid.split("_")
    return int(parts[-1]) if parts[-1].isdigit() else 999999

nums = [case_num(cid) for cid in ids]
sort_ok = nums == sorted(nums)
print(f"5. Sorted by case_id (numeric): {'OK' if sort_ok else 'FAIL'}")

# Check status distribution
allowed_statuses = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
bad_statuses = [r["case_id"] for r in rows if r["deletion_status"] not in allowed_statuses]
status_dist: Dict[str, int] = {}
for r in rows:
    s = r["deletion_status"]
    status_dist[s] = status_dist.get(s, 0) + 1
print(f"6. Status distribution: {status_dist}")
print(f"7. Invalid statuses: {len(bad_statuses)} -> {'OK' if not bad_statuses else 'FAIL'}")

# Load valid evidence IDs
valid_evidence_ids: Set[str] = set()
with open(ROOT / "dataset" / "evidence_files.csv", "r", encoding="utf-8") as f:
    valid_evidence_ids.update(r["file_id"] for r in csv.DictReader(f) if r.get("file_id"))
with open(ROOT / "dataset" / "system_activity.csv", "r", encoding="utf-8") as f:
    valid_evidence_ids.update(r["activity_id"] for r in csv.DictReader(f) if r.get("activity_id"))
with open(ROOT / "dataset" / "user_audit_log.csv", "r", encoding="utf-8") as f:
    valid_evidence_ids.update(r.get("audit_id", "") for r in csv.DictReader(f) if r.get("audit_id"))

# Resource identifiers are opaque dataset values.  Validate them against the
# source corpus, not naming conventions or generated account-number patterns.
known_resource_text = (ROOT / "dataset" / "system_activity.csv").read_text(
    encoding="utf-8", errors="ignore"
)
evidence_root = ROOT / "dataset" / "evidence"
for evidence_path in evidence_root.rglob("*"):
    if evidence_path.is_file():
        known_resource_text += evidence_path.read_bytes().decode("utf-8", errors="ignore")

# When optional media extraction is enabled, use the same participant-visible
# extraction route as the audit so IDs read from PDFs/screenshots are grounded.
# With the default flag-off setting, this intentionally matches a machine where
# pypdf/Pillow/pytesseract are unavailable.
if os.environ.get("USE_MEDIA_EVIDENCE") == "1":
    from code.extract.doc_extract import extract_doc_evidence
    from code.extract.image_extract import extract_image_evidence
    from code.loader import parse_ts

    for evidence in csv.DictReader((ROOT / "dataset" / "evidence_files.csv").open(encoding="utf-8")):
        path = ROOT / evidence["file_path"]
        if not path.exists():
            continue
        if path.suffix.lower() == ".pdf":
            records = extract_doc_evidence(path, evidence["file_id"], parse_ts(evidence.get("captured_at", "")))
        elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            records = extract_image_evidence(path, evidence["file_id"], parse_ts(evidence.get("captured_at", "")))
        else:
            continue
        known_resource_text += "\n".join(record.resource_id for record in records)

# Invariant tracking
bad_json = []
na_with_steps = []
complete_empty_steps = []
complete_empty_evidence = []
incomplete_no_findings = []
incomplete_finding_empty_evidence = []
incomplete_future_has_evidence = []
empty_system_or_resource_ids = []
legal_hold_wrong_system = []
consecutive_step_errors = []
phase_order_errors = []
invalid_evidence_citations = []
ungrounded_resource_ids = []

allowed_phases = {"FINDING", "REMEDIATION", "VERIFICATION"}
phase_rank = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}

for r in rows:
    cid = r["case_id"]
    status = r["deletion_status"]
    try:
        steps = json.loads(r["steps_json"])
    except Exception as e:
        bad_json.append((cid, str(e)))
        continue

    # NOT_APPLICABLE
    if status == "NOT_APPLICABLE":
        if steps:
            na_with_steps.append(cid)
        continue

    # COMPLETE
    if status == "COMPLETE":
        if not steps:
            complete_empty_steps.append(cid)
        for s in steps:
            if s.get("phase") != "VERIFICATION":
                phase_order_errors.append((cid, f"COMPLETE case with non-VERIFICATION step: {s.get('phase')}"))
            if not s.get("evidence_id"):
                complete_empty_evidence.append((cid, s.get("resource_id", "")))

    # INCOMPLETE
    if status == "INCOMPLETE":
        findings = [s for s in steps if s.get("phase") == "FINDING"]
        if not findings:
            incomplete_no_findings.append(cid)
        for s in steps:
            phase = s.get("phase")
            ev = s.get("evidence_id", "")
            if phase == "FINDING" and not ev:
                incomplete_finding_empty_evidence.append((cid, s.get("resource_id", "")))
            elif phase in ("REMEDIATION", "VERIFICATION") and ev:
                incomplete_future_has_evidence.append((cid, s.get("resource_id", "")))

    # Step schema, sequence, and system_id checks
    step_phases = []
    for idx, s in enumerate(steps, 1):
        if s.get("step_no") != idx:
            consecutive_step_errors.append((cid, idx, s.get("step_no")))

        sys_id = (s.get("system_id") or "").strip()
        res_id = (s.get("resource_id") or "").strip()
        if not sys_id or not res_id:
            empty_system_or_resource_ids.append((cid, res_id, sys_id))

        # Every emitted resource must be grounded in participant-visible input.
        # Match verbatim against system activity or the bytes of an evidence
        # file, so no derived user_id -> resource_id conventions can pass.
        if res_id and res_id not in known_resource_text:
            ungrounded_resource_ids.append((cid, res_id))

        if res_id.startswith("legal_hold_") and sys_id != "legal_service":
            legal_hold_wrong_system.append((cid, res_id, sys_id))

        phase = s.get("phase")
        if phase in phase_rank:
            step_phases.append(phase_rank[phase])

        ev = s.get("evidence_id", "")
        if ev and ev not in valid_evidence_ids:
            invalid_evidence_citations.append((cid, ev))

    if step_phases and step_phases != sorted(step_phases):
        phase_order_errors.append((cid, "Phases not in FINDING -> REMEDIATION -> VERIFICATION order"))

# Output summary counts
print("\n" + "=" * 80)
print("INVARIANT VALIDATION METRICS:")
print("=" * 80)

failures = {
    "Header valid (case_id,deletion_status,steps_json)": 0 if header_ok else 1,
    "Row count == 518": 0 if total_rows == 518 else 1,
    "Missing / extra case IDs": len(extra) + len(missing_from_output),
    "Sort order ascending numeric": 0 if sort_ok else 1,
    "Invalid deletion_status values": len(bad_statuses),
    "JSON parse errors in steps_json": len(bad_json),
    "NOT_APPLICABLE with non-empty steps": len(na_with_steps),
    "COMPLETE with empty steps_json []": len(complete_empty_steps),
    "COMPLETE with empty evidence_id": len(complete_empty_evidence),
    "INCOMPLETE without finding steps": len(incomplete_no_findings),
    "INCOMPLETE findings with empty evidence_id": len(incomplete_finding_empty_evidence),
    "INCOMPLETE future steps with non-empty evidence_id": len(incomplete_future_has_evidence),
    "Empty system_id or resource_id": len(empty_system_or_resource_ids),
    "legal_hold_* with system_id != 'legal_service'": len(legal_hold_wrong_system),
    "Non-consecutive step numbers": len(consecutive_step_errors),
    "Phase ordering violations": len(phase_order_errors),
    "Invalid evidence_id citations": len(invalid_evidence_citations),
    "Resource IDs absent from system_activity/evidence": len(ungrounded_resource_ids),
}

total_violations = 0
for desc, count in failures.items():
    status = "[PASS] 0" if count == 0 else f"[FAIL] {count}"
    print(f"  {desc:<55}: {status}")
    total_violations += count

print("=" * 80)
if total_violations == 0:
    print("SUCCESS: ALL 18 INVARIANT CHECKS PASSED (exit code 0)")
    sys.exit(0)
else:
    print(f"FAILURE: {total_violations} total violations detected (exit code 1)")
    if empty_system_or_resource_ids:
        print("  Sample empty system/resource:", empty_system_or_resource_ids[:5])
    if legal_hold_wrong_system:
        print("  Sample legal_hold wrong system:", legal_hold_wrong_system[:5])
    if complete_empty_steps:
        print("  Sample COMPLETE empty steps:", complete_empty_steps[:5])
    if complete_empty_evidence:
        print("  Sample COMPLETE empty evidence:", complete_empty_evidence[:5])
    if incomplete_finding_empty_evidence:
        print("  Sample INCOMPLETE finding empty evidence:", incomplete_finding_empty_evidence[:5])
    if ungrounded_resource_ids:
        print("  Sample ungrounded resource IDs:", ungrounded_resource_ids[:5])
    sys.exit(1)
