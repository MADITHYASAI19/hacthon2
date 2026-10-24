"""Image evidence extractor (PNG / screenshots)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None


def extract_image_evidence(file_path: Path, file_id: str, default_captured_at: Optional[datetime]) -> List[ExtractedRecord]:
    """Extract text and records from image using pytesseract OCR if available."""
    records = []
    text_content = ""
    if Image and pytesseract:
        try:
            img = Image.open(str(file_path))
            text_content = pytesseract.image_to_string(img)
        except Exception:
            pass

    # If OCR didn't find anything or isn't installed, extract filename-based record
    res_matches = re.findall(r"\b(account_\d+|support_\d+|export_\d+|audit_record_\d+|search_\d+|analytics_\d+|tombstone_\d+)\b", text_content)
    emails = re.findall(r"[\w\.-]+@[\w\.-]+", text_content)
    user_ids = re.findall(r"\buser_\d+\b", text_content)

    found_resources = set(res_matches)
    if not found_resources:
        # Check stem
        stem_m = re.findall(r"\b(account_\d+|support_\d+|export_\d+|audit_record_\d+|search_\d+|analytics_\d+|tombstone_\d+)\b", file_path.stem)
        if stem_m:
            found_resources = set(stem_m)
        else:
            found_resources = {file_path.stem}

    for res_id in found_resources:
        sys_id = "console_service"
        cat = "UNKNOWN"
        for p, s in PREFIX_TO_SYSTEM.items():
            if res_id.startswith(p):
                sys_id = s
                cat = PREFIX_TO_CATEGORY.get(p, "UNKNOWN")
                break

        records.append(
            ExtractedRecord(
                file_id=file_id,
                captured_at=default_captured_at,
                system_id=sys_id,
                resource_id=res_id,
                category=cat,
                user_ref=";".join(user_ids),
                identifiers={"emails": emails, "user_ids": user_ids, "ocr_text": text_content[:500]},
                state_hint="PRESENT",
                raw=text_content[:2000],
                source_table="image_screenshot",
            )
        )

    return records
