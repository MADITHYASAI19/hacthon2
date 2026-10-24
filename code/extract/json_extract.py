"""JSON evidence extractor supporting snapshots, exports, and ledgers."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts


def extract_json_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Parse JSON snapshot bundles, service resource exports, and ledgers."""
    records = []
    content = json.loads(file_path.read_text(encoding="utf-8"))

    if not isinstance(content, dict):
        return records

    # Case 1: snapshots[].records[] (snapshot bundles)
    if "snapshots" in content:
        for snap in content.get("snapshots", []):
            snap_time = parse_ts(snap.get("captured_at")) or default_captured_at
            collection = snap.get("collection", "")
            for r in snap.get("records", []):
                res_id = r.get("resource_id", "")
                if not res_id:
                    continue
                sys_id = "unknown_service"
                cat = "UNKNOWN"
                for p, s in PREFIX_TO_SYSTEM.items():
                    if res_id.startswith(p):
                        sys_id = s
                        cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                        break

                state_hint = "PRESENT"
                if "restore_allowed" in r:
                    state_hint = "ACTIVE" if r.get("restore_allowed") else "BLOCKED"
                elif "enabled" in r:
                    state_hint = "ACTIVE" if r.get("enabled") else "DISABLED"
                elif "customer_profiles" in collection or res_id.startswith("account_"):
                    if r.get("account_status") in ("DELETED", "PURGED"):
                        state_hint = "ABSENT"

                records.append(
                    ExtractedRecord(
                        file_id=file_id,
                        captured_at=snap_time,
                        system_id=sys_id,
                        resource_id=res_id,
                        category=cat,
                        user_ref=str(r.get("user_id") or r.get("customer_reference") or r.get("subject_reference") or ""),
                        identifiers=r,
                        state_hint=state_hint,
                        raw=r,
                        source_table=collection,
                    )
                )

    # Case 2: service_exports: { <system>: { <sub_key>: [ records ] } } (e.g. evidence_92)
    elif "service_exports" in content:
        exp_time = parse_ts(content.get("exported_at")) or default_captured_at
        sexp = content.get("service_exports", {})
        for sys_key, sub_dict in sexp.items():
            if isinstance(sub_dict, dict):
                for sub_key, items in sub_dict.items():
                    if isinstance(items, list):
                        for item in items:
                            res_id = item.get("resource_id", "")
                            if not res_id:
                                continue
                            sys_id = sys_key
                            cat = "UNKNOWN"
                            for p, s in PREFIX_TO_SYSTEM.items():
                                if res_id.startswith(p):
                                    sys_id = s
                                    cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                                    break

                            obs_time = parse_ts(item.get("observed_at")) or exp_time

                            # Determine state_hint
                            state_hint = "PRESENT"
                            if "status_code" in item:
                                if item.get("status_code") == 404:
                                    state_hint = "ABSENT"
                                else:
                                    state_hint = "PRESENT"
                            elif "restore_allowed" in item:
                                state_hint = "ACTIVE" if item.get("restore_allowed") else "BLOCKED"
                            elif "enabled" in item:
                                state_hint = "ACTIVE" if item.get("enabled") else "DISABLED"
                            elif "email" in item or "phone" in item:
                                # Check if identifiers are present or null (anonymized)
                                has_ident = bool(item.get("email") or item.get("phone") or item.get("email_hash"))
                                if sys_id == "analytics_platform" or res_id.startswith("analytics_"):
                                    state_hint = "PRESENT" if has_ident else "ANONYMIZED"
                                elif sys_id == "support_platform" or res_id.startswith("support_"):
                                    state_hint = "PRESENT" if has_ident else "REDACTED"

                            records.append(
                                ExtractedRecord(
                                    file_id=file_id,
                                    captured_at=obs_time,
                                    system_id=sys_id,
                                    resource_id=res_id,
                                    category=cat,
                                    user_ref=str(item.get("customer_reference") or item.get("subject_reference") or item.get("user_id") or ""),
                                    identifiers=item,
                                    state_hint=state_hint,
                                    raw=item,
                                    source_table=f"{sys_key}.{sub_key}",
                                )
                            )

    # Case 3: {"records": [...]} (e.g. security_audit_ledger_20261001.json)
    elif "records" in content:
        exp_time = parse_ts(content.get("exported_at")) or default_captured_at
        for r in content.get("records", []):
            res_id = r.get("resource_id", "")
            if not res_id:
                continue
            sys_id = r.get("system", "")
            if not sys_id:
                for p, s in PREFIX_TO_SYSTEM.items():
                    if res_id.startswith(p):
                        sys_id = s
                        break
            cat = r.get("record_type") or "UNKNOWN"
            rec_time = parse_ts(r.get("recorded_at")) or exp_time

            records.append(
                ExtractedRecord(
                    file_id=file_id,
                    captured_at=rec_time,
                    system_id=sys_id,
                    resource_id=res_id,
                    category=cat,
                    user_ref=str(r.get("subject_reference", "")),
                    identifiers=r,
                    state_hint="PRESENT",
                    raw=r,
                    source_table="security_audit_ledger",
                )
            )

    return records
