"""Evidence registry: iterates evidence_files.csv, dispatches by format, returns all Records."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from code.extract.doc_extract import extract_doc_evidence
from code.extract.image_extract import extract_image_evidence
from code.extract.json_extract import extract_json_evidence
from code.extract.log_extract import extract_log_evidence
from code.extract.media_config import ExtractionDiagnostics
from code.extract.schema import ExtractedRecord
from code.extract.sql_extract import extract_sql_evidence
from code.extract.txt_extract import extract_txt_evidence
from code.loader import Dataset, parse_ts


def load_all_evidence(
    dataset: Dataset,
    base_dir: Optional[Path] = None,
    diagnostics: Optional[ExtractionDiagnostics] = None,
) -> List[ExtractedRecord]:
    """Iterate over all rows in evidence_files.csv and extract records."""
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent.parent

    all_records: List[ExtractedRecord] = []

    for ev in dataset.evidence_files:
        file_id = ev.get("file_id", "")
        rel_path = ev.get("file_path", "")
        cap_str = ev.get("captured_at", "")
        cap_time = parse_ts(cap_str)

        # Path might be dataset/evidence/...
        full_path = base_dir / rel_path
        if not full_path.exists():
            full_path = base_dir / "dataset" / rel_path

        if not full_path.exists():
            continue

        ext = full_path.suffix.lower()
        if ext == ".sql":
            records = extract_sql_evidence(full_path, file_id, cap_time)
        elif ext == ".json":
            records = extract_json_evidence(full_path, file_id, cap_time)
        elif ext == ".log":
            records = extract_log_evidence(full_path, file_id, cap_time)
        elif ext == ".txt":
            records = extract_txt_evidence(full_path, file_id, cap_time)
        elif ext == ".pdf":
            records = extract_doc_evidence(full_path, file_id, cap_time, diagnostics)
        elif ext in (".png", ".jpg", ".jpeg"):
            records = extract_image_evidence(full_path, file_id, cap_time, diagnostics)
        else:
            continue

        # Keep internal observation times for state reconstruction, but also
        # retain the manifest's file-level capture time for audit eligibility and
        # evidence citation. A later-captured file must not be used early just
        # because its payload contains older timestamps.
        for record in records:
            record.file_captured_at = cap_time
        all_records.extend(records)

    return all_records
