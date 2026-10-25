"""Configuration and structured diagnostics for optional local media extraction."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


def enabled(name: str) -> bool:
    """Return the independent flag value, with the legacy media flag as fallback."""
    return os.environ.get(name, os.environ.get("USE_MEDIA_EVIDENCE", "0")) == "1"


@dataclass
class ExtractionDiagnostics:
    """Inspectable local extraction outcomes; never contains evidence text."""
    files_seen: Dict[str, int] = field(default_factory=lambda: {"pdf": 0, "image": 0})
    files_with_text: Dict[str, int] = field(default_factory=lambda: {"pdf": 0, "image": 0})
    warnings: List[Dict[str, str]] = field(default_factory=list)

    def warn(self, file_id: str, filename: Path, engine: str, code: str, detail: str) -> None:
        self.warnings.append({
            "file_id": file_id,
            "filename": filename.name,
            "engine": engine,
            "code": code,
            "detail": detail,
        })

    def summary(self) -> Dict[str, object]:
        return {
            "pdf_enabled": enabled("USE_PDF_EVIDENCE"),
            "ocr_enabled": enabled("USE_IMAGE_OCR"),
            "pypdf_available": _module_available("pypdf"),
            "tesseract_available": bool(shutil.which("tesseract")),
            "files_seen": self.files_seen,
            "files_with_text": self.files_with_text,
            "warnings": self.warnings,
        }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False
