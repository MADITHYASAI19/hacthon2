"""State reconstruction at audit_at."""
from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

from code.extract.schema import ExtractedRecord
from code.identity import IdentitySet
from code.loader import Dataset, parse_ts


@dataclass
class ResourceState:
    resource_id: str
    system_id: str
    category: str
    state: str  # PRESENT | ABSENT | REDACTED | ANONYMIZED | ACTIVE | DISABLED | BLOCKED
    exposing_identifiers: List[str] = field(default_factory=list)
    evidence_id: str = ""
    why: str = ""


PREFIX_TO_SYSTEM = {
    "account_": "account_service",
    "analytics_": "analytics_platform",
    "audit_record_": "security_service",
    "backup_": "backup_service",
    "cache_": "cache_service",
    "data_flow_": "integration_service",
    "email_delivery_": "email_delivery_service",
    "export_": "export_service",
    "legal_hold_": "legal_service",
    "marketing_": "marketing_platform",
    "object_": "object_storage",
    "search_": "search_service",
    "support_": "support_platform",
    "tombstone_": "identity_service",
}

PREFIX_TO_CATEGORY = {
    "account_": "USER_PROFILE",
    "analytics_": "ANALYTICS_PROFILE",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "backup_": "BACKUP_ARCHIVE",
    "cache_": "CACHE_ENTRY",
    "data_flow_": "INTEGRATION_FLOW",
    "email_delivery_": "EMAIL_DELIVERY_LOG",
    "export_": "USER_EXPORT",
    "legal_hold_": "LEGAL_HOLD_RECORD",
    "marketing_": "MARKETING_PROFILE",
    "object_": "SUPPORT_ATTACHMENT",
    "search_": "SEARCH_INDEX_ENTRY",
    "support_": "SUPPORT_MESSAGE",
    "tombstone_": "ACCOUNT_TOMBSTONE",
}


def build_case_view(
    identity: IdentitySet,
    audit_at: Optional[datetime],
    all_records: List[ExtractedRecord],
    dataset: Dataset,
    requested_at: Optional[datetime] = None,
    own_account_id_override: Optional[str] = None,
) -> Dict[str, ResourceState]:
    """Reconstruct state of all candidate resources for a user at audit_at."""
    # 1. Candidate resources must have a user-specific anchor. A resource merely
    # appearing in a shared snapshot or nearby activity is not sufficient.
    candidate_res_ids: Set[str] = set()
    res_to_system: Dict[str, str] = {}
    res_to_category: Dict[str, str] = {}

    # A direct identifier in the same activity record is a valid anchor. Catalog
    # links are also valid, but only when they are explicit LINK_RESOURCE_IDENTITY
    # events emitted by data_catalog for this identity.
    for act in dataset.system_activity:
        act_time = parse_ts(act.get("event_time"))
        if audit_at and act_time and act_time > audit_at:
            continue
        res_id = (act.get("resource_id") or "").strip()
        if not res_id:
            continue
        event_type = (act.get("event_type") or "").upper()
        source_system = (act.get("source_system") or "").lower()
        details = act.get("details", "")
        direct_match = bool(identity.matches(details))
        catalog_link = event_type == "LINK_RESOURCE_IDENTITY" and source_system == "data_catalog" and direct_match
        if direct_match or catalog_link:
            candidate_res_ids.add(res_id)
            target = (act.get("target_system") or "").strip()
            if target:
                res_to_system.setdefault(res_id, target)

    # Join profile lookup traces by trace_id: lookup_key on the started line and
    # resource_id on the completed line. Use the evidence manifest's file-level
    # captured_at as the cutoff for which log files were available at audit time.
    project_root = Path(__file__).resolve().parent.parent
    field_prefix = r"(?:\\?[\"'])?{field}(?:\\?[\"'])?\s*[:=]\s*(?:\\?[\"'])?"
    key_re = re.compile(field_prefix.format(field=r"(?:trace_id|requestId)") + r"([^,\s\"']+)", re.IGNORECASE)
    event_re = re.compile(field_prefix.format(field="event") + r"([^,\s\"']+)", re.IGNORECASE)
    lookup_re = re.compile(field_prefix.format(field=r"(?:lookup_key|subject_key|owner_key|match_key|correlation_key|subject_ref|subject_reference|user_id)") + r"([^,\s\"']+)", re.IGNORECASE)
    resource_re = re.compile(field_prefix.format(field="resource_id") + r"([A-Za-z0-9_]+)", re.IGNORECASE)
    for manifest_row in dataset.evidence_files:
        rel_path = (manifest_row.get("file_path") or "").strip()
        if not rel_path.lower().endswith(".log"):
            continue
        file_capture = parse_ts(manifest_row.get("captured_at"))
        if audit_at and file_capture and file_capture > audit_at:
            continue
        log_path = project_root / "dataset" / rel_path
        if not log_path.exists():
            log_path = project_root / rel_path
        if not log_path.exists():
            continue
        starts: Dict[str, str] = {}
        completions: Dict[str, str] = {}
        try:
            lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            tm = key_re.search(line)
            em = event_re.search(line)
            if not tm or not em:
                continue
            trace_id = tm.group(1)
            event = em.group(1).lower()
            if event.endswith("_started"):
                km = lookup_re.search(line)
                if km and identity.matches(km.group(1)):
                    starts[trace_id] = km.group(1)
            else:
                # Some services emit the resource_id on a later heartbeat or
                # readback event rather than an *_completed event. The shared
                # trace_id still links it to the identity-bearing start line.
                rm = resource_re.search(line)
                if rm:
                    completions[trace_id] = rm.group(1)
        for trace_id in starts.keys() & completions.keys():
            candidate_res_ids.add(completions[trace_id])
            res_to_system.setdefault(completions[trace_id], "account_service")
            res_to_category.setdefault(completions[trace_id], "USER_PROFILE")

    # Direct evidence-record anchors. Once a resource is anchored, other records
    # for that same resource may contribute state, but unrelated resources from
    # the same file/snapshot are never promoted to candidates.
    matching_records_by_res: Dict[str, List[ExtractedRecord]] = {}
    for rec in all_records:
        file_capture = rec.file_captured_at or rec.captured_at
        if audit_at and file_capture and file_capture > audit_at:
            continue
        if audit_at and rec.captured_at and rec.captured_at > audit_at:
            continue
        res_id = rec.resource_id
        if not res_id:
            continue
        manifest_row = dataset.file_id_to_evidence.get(rec.file_id, {})
        manifest_path = (manifest_row.get("file_path") or "").strip()
        suffix = Path(manifest_path).suffix.lower()
        is_synthetic_document_id = suffix in (".pdf", ".png", ".jpg", ".jpeg") and res_id == Path(manifest_path).stem
        if res_id not in candidate_res_ids and not is_synthetic_document_id:
            matches = identity.matches(rec.identifiers)
            if not matches and rec.user_ref:
                matches = identity.matches(rec.user_ref)
            if matches:
                candidate_res_ids.add(res_id)
                if rec.system_id != "unknown_service":
                    res_to_system[res_id] = rec.system_id
                if rec.category != "UNKNOWN":
                    res_to_category[res_id] = rec.category
        if res_id in candidate_res_ids and not is_synthetic_document_id:
            matching_records_by_res.setdefault(res_id, []).append(rec)
            if rec.system_id != "unknown_service":
                res_to_system[res_id] = rec.system_id
            if rec.category != "UNKNOWN":
                res_to_category[res_id] = rec.category

    # Resolve exactly one own account resource. Prefer account resources anchored
    # by post-request evidence/activity; pre-request lookup traces are not enough
    # to identify the account being audited.  Resource IDs remain opaque values
    # sourced from the dataset and are never derived from a user identifier.
    account_candidates = [r for r in candidate_res_ids if r.startswith("account_")]
    relevant_accounts: List[tuple] = []
    for rid in account_candidates:
        rec_times = [r.captured_at for r in matching_records_by_res.get(rid, []) if r.captured_at]
        act_times = [
            parse_ts(a.get("event_time")) for a in dataset.system_activity
            if a.get("resource_id") == rid and (a.get("event_type") or "").upper() == "DELETE_RECORD"
            and (a.get("source_system") or "").lower() == "deletion_worker"
        ]
        act_times = [t for t in act_times if t]
        times = rec_times + act_times
        if any((requested_at is None or t >= requested_at) and (audit_at is None or t <= audit_at) for t in times):
            relevant_accounts.append((rid, max(t for t in times if (requested_at is None or t >= requested_at) and (audit_at is None or t <= audit_at))))

    own_account_id = own_account_id_override
    if own_account_id is None and relevant_accounts:
        # Prefer latest relevant account evidence/activity; this rejects stale
        # historical lookup traces when a later account readback identifies the
        # current resource.
        own_account_id = sorted(relevant_accounts, key=lambda x: (x[1], x[0]), reverse=True)[0][0]

    if own_account_id:
        candidate_res_ids.add(own_account_id)
        if own_account_id not in matching_records_by_res:
            matching_records_by_res[own_account_id] = []
        for rec in all_records:
            if rec.resource_id != own_account_id:
                continue
            file_capture = rec.file_captured_at or rec.captured_at
            if audit_at and file_capture and file_capture > audit_at:
                continue
            if audit_at and rec.captured_at and rec.captured_at > audit_at:
                continue
            if rec not in matching_records_by_res[own_account_id]:
                matching_records_by_res[own_account_id].append(rec)
        # Never emit account checks for other account resources.
        for rid in account_candidates:
            if rid != own_account_id:
                candidate_res_ids.discard(rid)
                matching_records_by_res.pop(rid, None)
                res_to_system.pop(rid, None)
                res_to_category.pop(rid, None)
        res_to_system.setdefault(own_account_id, "account_service")
        res_to_category.setdefault(own_account_id, "USER_PROFILE")

    # Build ResourceState for each candidate resource
    results: Dict[str, ResourceState] = {}

    for res_id in candidate_res_ids:
        # Determine system_id and category
        sys_id = res_to_system.get(res_id, "")
        cat = res_to_category.get(res_id, "")
        if not sys_id or not cat:
            for p, s in PREFIX_TO_SYSTEM.items():
                if res_id.startswith(p):
                    sys_id = sys_id or s
                    cat = cat or PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                    break

        recs = matching_records_by_res.get(res_id, [])
        # Sort records by captured_at descending (latest evidence wins)
        state_priority = {
            "UNKNOWN": 0, "PRESENT": 1, "ACTIVE": 3, "DISABLED": 3,
            "BLOCKED": 3, "REDACTED": 3, "ANONYMIZED": 3, "ABSENT": 4,
        }
        recs_sorted = sorted(
            recs,
            key=lambda r: (
                r.captured_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
                state_priority.get(r.state_hint, 0),
            ),
            reverse=True,
        )

        state = "PRESENT"
        best_evidence_id = ""
        why = ""

        if recs_sorted:
            latest = recs_sorted[0]
            citation_record = max(
                recs_sorted,
                key=lambda r: (r.file_captured_at or r.captured_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)),
            )
            best_evidence_id = citation_record.file_id
            state = latest.state_hint
        elif res_id == own_account_id:
            eligible_account_files = []
            for ev in dataset.evidence_files:
                origin = (ev.get("origin") or "").lower()
                cap = parse_ts(ev.get("captured_at"))
                if cap and (audit_at is None or cap <= audit_at) and (
                    "customer_account" in origin
                    or "records_assurance_snapshot_bundle" in origin
                    or "service_resource_export" in origin
                ):
                    eligible_account_files.append((cap, ev.get("file_id", "")))
            if eligible_account_files:
                best_evidence_id = max(eligible_account_files)[1]
            state = "ABSENT"

        # If best_evidence_id is still empty, look for an explicit data_catalog link activity or audit_id
        if not best_evidence_id:
            for act in dataset.system_activity:
                act_time = parse_ts(act.get("event_time"))
                if audit_at and act_time and act_time > audit_at:
                    continue
                if act.get("resource_id") == res_id and act.get("activity_id"):
                    best_evidence_id = act.get("activity_id", "")
                    break

            # If there are replica records, check for replication drift:
            # If any replica table holds the row present, state is PRESENT
            has_replica_present = any(
                "replica" in r.source_table and r.state_hint == "PRESENT"
                for r in recs_sorted
            )
            if has_replica_present and cat in ("USER_PROFILE", "SEARCH_INDEX_ENTRY"):
                state = "PRESENT"
                replica_records = [r for r in recs_sorted if "replica" in r.source_table and r.state_hint == "PRESENT"]
                replica_rec = max(replica_records, key=lambda r: (r.file_captured_at or r.captured_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)))
                best_evidence_id = replica_rec.file_id
                why = "Replication drift: replica table retains record"

        # Check tombstone specifics
        if cat == "ACCOUNT_TOMBSTONE" or res_id.startswith("tombstone_"):
            # If identifiers (name, email, phone, hash) exist in raw, it's PRESENT (exposed PII)
            # If only user_id exists, it's REDACTED
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = identity.matches(latest.identifiers)
                non_uid_matches = [m for m in ident_matches if m[0] != "user_id"]
                if non_uid_matches:
                    state = "PRESENT"
                    why = f"Tombstone exposes PII: {non_uid_matches}"
                else:
                    state = "REDACTED"
                    why = "Tombstone contains only stable user_id"

        # Check support message context
        if cat == "SUPPORT_MESSAGE" or (res_id.startswith("support_") and cat not in ("SUPPORT_ATTACHMENT",)):
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = [m for m in identity.matches(latest.identifiers) if m[0] != "user_id"]
                has_positive_row_readback = any(
                    re.search(r"\brows[=:]\s*[\"']?1\b", str(r.raw), re.IGNORECASE)
                    and ("_completed" in str(r.raw).lower() or "query_completed" in str(r.raw).lower())
                    for r in recs_sorted
                )
                if ident_matches or has_positive_row_readback:
                    state = "PRESENT"
                    why = "Support record exposes identifiers or a positive row readback"
                else:
                    state = "REDACTED"

        # Check analytics profile
        if cat == "ANALYTICS_PROFILE" or (res_id.startswith("analytics_") and cat not in ("SECONDARY_IDENTIFIER", "PRODUCT_TELEMETRY")):
            if recs_sorted:
                latest = recs_sorted[0]
                ident_matches = identity.matches(latest.identifiers)
                if ident_matches:
                    state = "PRESENT"
                    why = "Analytics profile contains direct identifiers"
                else:
                    state = "ANONYMIZED"
                    why = "Analytics profile is anonymized"

        results[res_id] = ResourceState(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            state=state,
            evidence_id=best_evidence_id,
            why=why,
        )

    return results
