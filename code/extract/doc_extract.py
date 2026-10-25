"""Document evidence extractor (PDF)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code.extract.schema import ExtractedRecord
from code.extract.media_config import ExtractionDiagnostics, enabled
from code.extract.sql_extract import PREFIX_TO_CATEGORY, PREFIX_TO_SYSTEM
from code.loader import parse_ts

def extract_doc_evidence(
    file_path: Path,
    file_id: str,
    default_captured_at: Optional[datetime],
    diagnostics: Optional[ExtractionDiagnostics] = None,
) -> List[ExtractedRecord]:
    """Extract text from every readable PDF page when explicitly enabled."""
    records = []
    if diagnostics:
        diagnostics.files_seen["pdf"] += 1
    if not enabled("USE_PDF_EVIDENCE"):
        return records
    try:
        import pypdf
    except ImportError:
        if diagnostics:
            diagnostics.warn(file_id, file_path, "pypdf", "dependency_missing", "Install with: python -m pip install pypdf")
        return records

    text_pages = []
    try:
        reader = pypdf.PdfReader(str(file_path))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise ValueError("encrypted PDF cannot be opened without a password")
            except Exception as exc:
                if diagnostics:
                    diagnostics.warn(file_id, file_path, "pypdf", "encrypted_pdf", str(exc))
                return records
        for page_no, page in enumerate(reader.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                if diagnostics:
                    diagnostics.warn(file_id, file_path, "pypdf", "page_extract_failed", f"page {page_no}: {exc}")
                continue
            if text.strip():
                text_pages.append((page_no, text))
    except Exception as exc:
        if diagnostics:
            diagnostics.warn(file_id, file_path, "pypdf", "pdf_read_failed", str(exc))
        return records

    text_content = "\n".join(text for _, text in text_pages)

    if not text_content:
        if diagnostics:
            diagnostics.warn(file_id, file_path, "pypdf", "scanned_or_empty_pdf", "No embedded text; local PDF OCR is not configured.")
        return records
    if diagnostics:
        diagnostics.files_with_text["pdf"] += 1

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
                metadata={"source_filename": file_path.name, "page_numbers": [page for page, _ in text_pages], "engine": "pypdf"},
            )
        )

    return records
