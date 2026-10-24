"""Pipe-delimited plain text evidence extractor."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts


def extract_txt_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Parse pipe-delimited text records.
    Format: time | system | resource | CATEGORY | STATE | identifier
    """
    records = []
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue

        ts_str = parts[0]
        rec_time = parse_ts(ts_str) or default_captured_at
        sys_id = parts[1]
        res_id = parts[2]
        cat = parts[3]
        state_str = parts[4].upper() if len(parts) > 4 else "UNKNOWN"
        ident_str = parts[5] if len(parts) > 5 else ""

        # Map state_str
        state_hint = "PRESENT"
        if state_str in ("NOT_FOUND", "ABSENT", "DELETED"):
            state_hint = "ABSENT"
        elif state_str in ("IDENTIFIABLE", "EXPOSED_PII", "PRESENT"):
            state_hint = "PRESENT"
        elif state_str in ("ANONYMIZED", "ANONYMOUS"):
            state_hint = "ANONYMIZED"
        elif state_str in ("REDACTED",):
            state_hint = "REDACTED"
        elif state_str in ("ACTIVE", "ENABLED"):
            state_hint = "ACTIVE"
        elif state_str in ("DISABLED",):
            state_hint = "DISABLED"
        elif state_str in ("BLOCKED",):
            state_hint = "BLOCKED"

        if not cat or cat == "UNKNOWN":
            for p, c in PREFIX_TO_CATEGORY.items():
                if res_id.startswith(p):
                    cat = c
                    break

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=rec_time,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=ident_str,
                identifiers={"ident": ident_str, "raw": line},
                state_hint=state_hint,
                raw=line,
                source_table="txt_pipe_records",
            )
        )

    return records
