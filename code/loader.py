"""Data loader and normalization for deletion audit agent."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def normalize_email(s: Optional[str]) -> str:
    """Normalize email: strip whitespace and lowercase."""
    if not s:
        return ""
    return s.strip().lower()


def parse_ts(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string with Z to aware UTC datetime."""
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None


@dataclass
class Dataset:
    requests: List[Dict[str, str]]
    sample_requests: List[Dict[str, str]]
    user_identities: List[Dict[str, str]]
    user_audit_log: List[Dict[str, str]]
    system_activity: List[Dict[str, str]]
    deletion_rules: List[Dict[str, str]]
    evidence_files: List[Dict[str, str]]

    # Indexes
    email_to_user: Dict[str, Dict[str, str]] = field(default_factory=dict)
    user_id_to_identity: Dict[str, Dict[str, str]] = field(default_factory=dict)
    user_id_to_audit: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    resource_id_to_activity: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    file_id_to_evidence: Dict[str, Dict[str, str]] = field(default_factory=dict)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with open(path, mode="r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_dataset(dataset_dir: Optional[Path] = None) -> Dataset:
    """Load all dataset files and build fast indexes."""
    if dataset_dir is None:
        dataset_dir = Path(__file__).resolve().parent.parent / "dataset"

    requests = _read_csv(dataset_dir / "deletion_requests.csv")
    sample_requests = _read_csv(dataset_dir / "sample_deletion_requests.csv")
    user_identities = _read_csv(dataset_dir / "user_identities.csv")
    user_audit_log = _read_csv(dataset_dir / "user_audit_log.csv")
    system_activity = _read_csv(dataset_dir / "system_activity.csv")
    deletion_rules = _read_csv(dataset_dir / "deletion_rules.csv")
    evidence_files = _read_csv(dataset_dir / "evidence_files.csv")

    ds = Dataset(
        requests=requests,
        sample_requests=sample_requests,
        user_identities=user_identities,
        user_audit_log=user_audit_log,
        system_activity=system_activity,
        deletion_rules=deletion_rules,
        evidence_files=evidence_files,
    )

    # Build indexes
    for row in user_identities:
        norm_email = normalize_email(row.get("email", ""))
        if norm_email:
            ds.email_to_user[norm_email] = row
        uid = row.get("user_id", "")
        if uid:
            ds.user_id_to_identity[uid] = row

    # Sort audit rows by event_time
    sorted_audit = sorted(
        user_audit_log,
        key=lambda r: parse_ts(r.get("event_time", "")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for row in sorted_audit:
        uid = row.get("user_id", "")
        if uid not in ds.user_id_to_audit:
            ds.user_id_to_audit[uid] = []
        ds.user_id_to_audit[uid].append(row)

    # Sort activity rows by event_time
    sorted_activity = sorted(
        system_activity,
        key=lambda r: parse_ts(r.get("event_time", "")) or datetime.min.replace(tzinfo=timezone.utc),
    )
    for row in sorted_activity:
        res_id = row.get("resource_id", "")
        if res_id:
            if res_id not in ds.resource_id_to_activity:
                ds.resource_id_to_activity[res_id] = []
            ds.resource_id_to_activity[res_id].append(row)

    for row in evidence_files:
        fid = row.get("file_id", "")
        if fid:
            ds.file_id_to_evidence[fid] = row

    return ds
