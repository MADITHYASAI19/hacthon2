"""Log evidence extractor."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts


def extract_log_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Parse log files (both key=value and JSON structured events)."""
    records = []
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return records

    res_regex = re.compile(r'(?:resource_id|"resource_id")\s*[=:]\s*["\']?([\w\d_]+)["\']?', re.IGNORECASE)
    time_regex = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)")

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # Look for resource_id via regex
        m_res = res_regex.search(line_clean)
        if not m_res:
            continue
        res_id = m_res.group(1)

        sys_id = "unknown_service"
        cat = "UNKNOWN"
        for p, s in PREFIX_TO_SYSTEM.items():
            if res_id.startswith(p):
                sys_id = s
                cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                break

        # Check structured JSON line if applicable
        json_obj = None
        if "{" in line_clean and "}" in line_clean:
            try:
                # Extract json substring
                start_idx = line_clean.find("{")
                end_idx = line_clean.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_obj = json.loads(line_clean[start_idx : end_idx + 1])
            except Exception:
                pass

        if json_obj:
            if "service" in json_obj and json_obj["service"]:
                # Map or keep
                sys_cand = json_obj["service"]
                if sys_cand in PREFIX_TO_SYSTEM.values():
                    sys_id = sys_cand

        m_event = re.search(r'(?:event|"event")\s*[=:]\s*["\']?([^,\s"\'\}]+)', line_clean, re.IGNORECASE)
        event_name = m_event.group(1).lower() if m_event else ""
        if res_id.startswith("analytics_") and event_name.startswith("contact_lookup"):
            cat = "SECONDARY_IDENTIFIER"

        # Parse timestamp from start of line
        m_time = time_regex.match(line_clean)
        log_time = parse_ts(m_time.group(1)) if m_time else default_captured_at

        # Derive state_hint
        state_hint = "PRESENT"
        line_lower = line_clean.lower()
        if (
            "rows=0" in line_clean
            or '"rows":"0"' in line_clean
            or '"rows":0' in line_clean
            or "404" in line_clean
            or "status=absent" in line_lower
            or "deleted" in line_lower
        ):
            state_hint = "ABSENT"
        elif "enabled=false" in line_clean or '"enabled":"false"' in line_clean or '"enabled":false' in line_clean:
            state_hint = "DISABLED"
        elif "enabled=true" in line_clean or '"enabled":"true"' in line_clean or '"enabled":true' in line_clean:
            state_hint = "ACTIVE"
        elif "restore_allowed=false" in line_clean or '"deletion_block":"true"' in line_clean:
            state_hint = "BLOCKED"
        elif "restore_allowed=true" in line_clean or '"deletion_block":"false"' in line_clean:
            state_hint = "ACTIVE"
        elif "customer_email=null" in line_clean or '"email":null' in line_clean:
            state_hint = "ANONYMIZED"

        identifiers = {"raw_log": line_clean}
        user_ref = ""
        if json_obj:
            identifiers.update(json_obj)
            user_ref = str(json_obj.get("subject_ref") or json_obj.get("subject_reference") or json_obj.get("user_id") or "")

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=log_time,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=user_ref,
                identifiers=identifiers,
                state_hint=state_hint,
                raw=line_clean,
                source_table="log_file",
            )
        )

    return records
