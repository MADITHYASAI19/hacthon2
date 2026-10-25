"""Image evidence extractor (PNG / screenshots)."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.media_config import ExtractionDiagnostics, enabled
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM

def extract_image_evidence(
    file_path: Path,
    file_id: str,
    default_captured_at: Optional[datetime],
    diagnostics: Optional[ExtractionDiagnostics] = None,
) -> List[ExtractedRecord]:
    """Extract text and records from image using pytesseract OCR if available."""
    records = []
    text_content = ""
    ocr_used = False
    if diagnostics:
        diagnostics.files_seen["image"] += 1
    if enabled("USE_IMAGE_OCR"):
        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            if diagnostics:
                diagnostics.warn(file_id, file_path, "tesseract", "dependency_missing", "Install with: python -m pip install pillow pytesseract; install Tesseract OCR and add it to PATH.")
        else:
            if not shutil.which("tesseract"):
                if diagnostics:
                    diagnostics.warn(file_id, file_path, "tesseract", "executable_missing", "Install Tesseract OCR, add tesseract to PATH, then run: tesseract --list-langs.")
            else:
                try:
                    with Image.open(str(file_path)) as img:
                        text_content = pytesseract.image_to_string(img)
                    ocr_used = True
                except Exception as exc:
                    if diagnostics:
                        diagnostics.warn(file_id, file_path, "tesseract", "ocr_failed", str(exc))
    if text_content.strip() and diagnostics:
        diagnostics.files_with_text["image"] += 1

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
                metadata={"source_filename": file_path.name, "engine": "tesseract" if ocr_used else "filename_fallback", "ocr_used": ocr_used},
            )
        )

    return records
