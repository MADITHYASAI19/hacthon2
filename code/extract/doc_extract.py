"""Document evidence extractor (PDF)."""
from __future__ import annotations

import re
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts

# Media extraction is deliberately opt-in.  PDF parser availability differs by
# machine, so the default path must behave like an installation without pypdf.
if os.environ.get("USE_MEDIA_EVIDENCE") == "1":
    try:
        import pypdf
    except ImportError:
        pypdf = None
else:
    pypdf = None


def extract_doc_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Extract text from PDF documents using pypdf."""
    records = []
    text_content = ""
    if pypdf:
        try:
            reader = pypdf.PdfReader(str(file_path))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_content += t + "\n"
        except Exception:
            pass

    if not text_content:
        return records

    # Look for identifiers and resource references
    res_matches = re.findall(r"\b(account_\d+|support_\d+|export_\d+|audit_record_\d+|object_\d+)\b", text_content)
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", text_content)
    user_ids = re.findall(r"\buser_\d+\b", text_content)

    found_resources = set(res_matches)
    if not found_resources:
        # Create a document record
        found_resources = {file_path.stem}

    for res_id in found_resources:
        sys_id = "document_service"
        # A PDF attachment linked to a support ticket is a user-owned attachment,
        # not a shared support conversation. Preserve that explicit document type
        # even when the resource ID begins with support_.
        is_attachment = "attachment" in file_path.name.lower() or "attachment" in text_content.lower()
        cat = "SUPPORT_ATTACHMENT" if is_attachment else "UNKNOWN"
        for p, s in PREFIX_TO_SYSTEM.items():
            if res_id.startswith(p):
                sys_id = s
                if not (p == "support_" and is_attachment):
                    cat = PREFIX_TO_CATEGORY.get(p, cat or "UNKNOWN")
                break
        if cat == "UNKNOWN":
            cat = "SUPPORT_ATTACHMENT" if is_attachment else "UNKNOWN"

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=default_captured_at,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=";".join(user_ids),
                identifiers={"emails": emails, "user_ids": user_ids, "text": text_content[:500]},
                state_hint="PRESENT",
                raw=text_content[:2000],
                source_table="pdf_document",
            )
        )

    return records
