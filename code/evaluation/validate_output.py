"""Comprehensive output validation enforcing all invariant checks and challenge contracts.

Validates:
1. Row count (518 evaluation cases)
2. CSV header (case_id,deletion_status,steps_json)
3. Unique and sorted case IDs
4. Valid deletion_status values
5. NOT_APPLICABLE cases must have steps_json == []
6. COMPLETE cases must have non-empty steps, all in VERIFICATION phase with non-empty evidence_id
7. INCOMPLETE cases must have at least one FINDING with non-empty evidence_id,
   and all REMEDIATION and VERIFICATION steps must have empty evidence_id
8. No empty system_id or resource_id
9. All legal_hold_* resources must have system_id == "legal_service"
10. Valid evidence IDs citing real participant-visible files, activities, or audit IDs
11. Invariant: non-zero counts in critical failure categories exit with non-zero code.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent


def validate_output(output_file: Path, dataset_dir: Path, requests_file: Optional[Path] = None, fail_fast: bool = False) -> int:
    print("=" * 80)
    print(f"VALIDATING DELETION AUDIT OUTPUT: {output_file}")
    print("=" * 80)

    if not output_file.exists():
        print(f"CRITICAL ERROR: File not found: {output_file}")
        return 1

    with open(output_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            actual_header = next(reader)
        except StopIteration:
            print("CRITICAL ERROR: Output file is completely empty.")
            return 1

    expected_header = ["case_id", "deletion_status", "steps_json"]
    if actual_header != expected_header:
        print(f"CRITICAL ERROR: Invalid header: {actual_header} != {expected_header}")
        return 1

    with open(output_file, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total_rows = len(rows)
    print(f"Total Rows: {total_rows}")

    # Load dataset manifests for evidence validation
    valid_evidence_ids: Set[str] = set()
    ev_files = dataset_dir / "evidence_files.csv"
    if ev_files.exists():
        with open(ev_files, "r", encoding="utf-8") as f:
            valid_evidence_ids.update(r["file_id"] for r in csv.DictReader(f) if r.get("file_id"))

    sys_act = dataset_dir / "system_activity.csv"
    if sys_act.exists():
        with open(sys_act, "r", encoding="utf-8") as f:
            valid_evidence_ids.update(r["activity_id"] for r in csv.DictReader(f) if r.get("activity_id"))

    audit_log = dataset_dir / "user_audit_log.csv"
    if audit_log.exists():
        with open(audit_log, "r", encoding="utf-8") as f:
            valid_evidence_ids.update(r.get("audit_id", "") for r in csv.DictReader(f) if r.get("audit_id"))

    # Tracking error categories
    row_count_errors = 0
    duplicate_or_missing_ids = 0
    sort_order_errors = 0
    invalid_status_errors = 0
    na_with_steps_errors = 0
    complete_empty_steps_errors = 0
    complete_empty_evidence_errors = 0
    incomplete_no_finding_errors = 0
    incomplete_finding_empty_evidence_errors = 0
    incomplete_future_has_evidence_errors = 0
    empty_sys_or_res_errors = 0
    legal_hold_system_id_errors = 0
    invalid_evidence_id_errors = 0
    json_parse_errors = 0
    phase_order_errors = 0
    consecutive_step_errors = 0

    # 1. Unique and expected case IDs
    if requests_file is None:
        requests_file = dataset_dir / ("deletion_requests.csv" if total_rows > 32 else "sample_deletion_requests.csv")
    if requests_file.exists():
        with open(requests_file, "r", encoding="utf-8") as f:
            expected_cids = [r["case_id"] for r in csv.DictReader(f)]
        expected_cid_set = set(expected_cids)
        actual_cid_list = [r["case_id"] for r in rows]
        actual_cid_set = set(actual_cid_list)

        if len(rows) != len(expected_cids):
            row_count_errors += 1
            print(f"[-] Row count mismatch: got {len(rows)}, expected {len(expected_cids)}")

        if actual_cid_set != expected_cid_set:
            duplicate_or_missing_ids += 1
            missing = expected_cid_set - actual_cid_set
            extra = actual_cid_set - expected_cid_set
            if missing:
                print(f"[-] Missing case IDs ({len(missing)}): {sorted(list(missing))[:5]}")
            if extra:
                print(f"[-] Extra case IDs ({len(extra)}): {sorted(list(extra))[:5]}")

        # Check numeric sort order
        def case_num(cid: str) -> int:
            parts = cid.split("_")
            return int(parts[-1]) if parts[-1].isdigit() else 999999

        actual_nums = [case_num(cid) for cid in actual_cid_list]
        if actual_nums != sorted(actual_nums):
            sort_order_errors += 1
            print(f"[-] Output rows are not sorted in ascending case order.")

    allowed_statuses = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
    allowed_phases = {"FINDING", "REMEDIATION", "VERIFICATION"}
    phase_rank = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}

    for r in rows:
        cid = r.get("case_id", "")
        status = r.get("deletion_status", "")
        steps_raw = r.get("steps_json", "")

        if status not in allowed_statuses:
            invalid_status_errors += 1

        try:
            steps = json.loads(steps_raw)
            if not isinstance(steps, list):
                json_parse_errors += 1
                continue
        except Exception:
            json_parse_errors += 1
            continue

        # Check NOT_APPLICABLE
        if status == "NOT_APPLICABLE":
            if steps:
                na_with_steps_errors += 1
            continue

        # Check COMPLETE
        if status == "COMPLETE":
            if not steps:
                complete_empty_steps_errors += 1
            for s in steps:
                if s.get("phase") != "VERIFICATION":
                    phase_order_errors += 1
                if not s.get("evidence_id"):
                    complete_empty_evidence_errors += 1

        # Check INCOMPLETE
        if status == "INCOMPLETE":
            findings = [s for s in steps if s.get("phase") == "FINDING"]
            if not findings:
                incomplete_no_finding_errors += 1
            for s in steps:
                phase = s.get("phase")
                ev = s.get("evidence_id", "")
                if phase == "FINDING" and not ev:
                    incomplete_finding_empty_evidence_errors += 1
                elif phase in ("REMEDIATION", "VERIFICATION") and ev:
                    incomplete_future_has_evidence_errors += 1

        # Check step sequence & schema
        step_phases = []
        for idx, s in enumerate(steps, 1):
            if s.get("step_no") != idx:
                consecutive_step_errors += 1

            sys_id = (s.get("system_id") or "").strip()
            res_id = (s.get("resource_id") or "").strip()
            if not sys_id or not res_id:
                empty_sys_or_res_errors += 1

            if res_id.startswith("legal_hold_") and sys_id != "legal_service":
                legal_hold_system_id_errors += 1

            phase = s.get("phase")
            if phase in phase_rank:
                step_phases.append(phase_rank[phase])

            ev = s.get("evidence_id", "")
            if ev and ev not in valid_evidence_ids:
                invalid_evidence_id_errors += 1

        if step_phases and step_phases != sorted(step_phases):
            phase_order_errors += 1

    # Print Category Summaries
    print("\n--- INVARIANT VALIDATION AUDIT SUMMARY ---")
    metrics = [
        ("Row count error", row_count_errors),
        ("Duplicate or missing case IDs", duplicate_or_missing_ids),
        ("Sort order errors", sort_order_errors),
        ("Invalid deletion_status values", invalid_status_errors),
        ("JSON parse or format errors", json_parse_errors),
        ("NOT_APPLICABLE with non-empty steps", na_with_steps_errors),
        ("COMPLETE with empty steps_json []", complete_empty_steps_errors),
        ("COMPLETE with empty evidence_id in verification", complete_empty_evidence_errors),
        ("INCOMPLETE without finding steps", incomplete_no_finding_errors),
        ("INCOMPLETE finding with empty evidence_id", incomplete_finding_empty_evidence_errors),
        ("INCOMPLETE future step with non-empty evidence_id", incomplete_future_has_evidence_errors),
        ("Empty system_id or resource_id", empty_sys_or_res_errors),
        ("legal_hold_* with system_id != 'legal_service'", legal_hold_system_id_errors),
        ("Phase ordering errors (FINDING -> REMEDIATION -> VERIFICATION)", phase_order_errors),
        ("Non-consecutive step_no numbering", consecutive_step_errors),
        ("Invalid evidence_id citations", invalid_evidence_id_errors),
    ]

    total_failures = 0
    for name, count in metrics:
        status_tag = "[PASS] 0" if count == 0 else f"[FAIL] {count}"
        print(f"  {name:<60}: {status_tag}")
        total_failures += count

    print("=" * 80)
    if total_failures == 0:
        print("ALL INVARIANT CHECKS PASSED: Output file conforms to project contract.")
        return 0
    else:
        print(f"VALIDATION FAILED: {total_failures} total violation(s) detected.")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Validate deletion audit output.csv invariants")
    parser.add_argument("output_path", type=Path, nargs="?", default=ROOT / "output.csv")
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--fail-fast", action="store_true", default=False)

    args = parser.parse_args()
    exit_code = validate_output(args.output_path, args.dataset, fail_fast=args.fail_fast)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
