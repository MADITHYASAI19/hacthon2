"""Regression tests for opt-in, local PDF and image evidence extraction."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from code.extract.doc_extract import extract_doc_evidence
from code.extract.image_extract import extract_image_evidence
from code.extract.media_config import ExtractionDiagnostics
from code.identity import resolve_identity
from code.loader import load_dataset, parse_ts
from code.state import build_case_view


class MediaExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.captured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def _pdf(self) -> Path:
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab unavailable for readable-PDF fixture")
        path = self.root / "readable.pdf"
        page = canvas.Canvas(str(path))
        page.drawString(72, 720, "account_4321 user_99 person@example.test")
        page.showPage()
        page.drawString(72, 720, "audit_record_003")
        page.save()
        return path

    def test_pdf_text_extraction_preserves_manifest_id_and_page_metadata(self):
        diagnostics = ExtractionDiagnostics()
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            records = extract_doc_evidence(self._pdf(), "evidence_fixture", self.captured_at, diagnostics)
        self.assertEqual({r.file_id for r in records}, {"evidence_fixture"})
        self.assertEqual({r.resource_id for r in records}, {"account_4321", "audit_record_003"})
        self.assertTrue(all(r.file_captured_at is None for r in records))  # Registry sets file-level time.
        self.assertTrue(all(r.captured_at == self.captured_at for r in records))
        self.assertTrue(all(r.metadata["source_filename"] == "readable.pdf" for r in records))
        self.assertEqual(records[0].metadata["page_numbers"], [1, 2])
        self.assertEqual(diagnostics.files_with_text["pdf"], 1)

    def test_pdf_disabled_is_the_empty_baseline(self):
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "0", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            self.assertEqual(extract_doc_evidence(self._pdf(), "evidence_fixture", self.captured_at), [])

    def test_unreadable_pdf_warns_without_fabricating_observations(self):
        path = self.root / "broken.pdf"
        path.write_bytes(b"not a PDF")
        diagnostics = ExtractionDiagnostics()
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            self.assertEqual(extract_doc_evidence(path, "broken", self.captured_at, diagnostics), [])
        self.assertTrue(any(w["code"] == "pdf_read_failed" for w in diagnostics.warnings))

    def test_scanned_or_empty_pdf_is_distinguished(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab unavailable for empty-PDF fixture")
        path = self.root / "empty.pdf"
        canvas.Canvas(str(path)).save()
        diagnostics = ExtractionDiagnostics()
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            self.assertEqual(extract_doc_evidence(path, "empty", self.captured_at, diagnostics), [])
        self.assertTrue(any(w["code"] == "scanned_or_empty_pdf" for w in diagnostics.warnings))

    def test_image_disabled_retains_filename_only_baseline(self):
        path = self.root / "account_4321.png"
        path.write_bytes(b"not-an-image")
        with patch.dict(os.environ, {"USE_IMAGE_OCR": "0", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            records = extract_image_evidence(path, "image_fixture", self.captured_at)
        self.assertEqual([r.resource_id for r in records], ["account_4321"])
        self.assertFalse(records[0].metadata["ocr_used"])

    def test_enabled_ocr_reports_missing_engine_without_fake_text(self):
        path = self.root / "screen.png"
        path.write_bytes(b"not-an-image")
        diagnostics = ExtractionDiagnostics()
        with patch.dict(os.environ, {"USE_IMAGE_OCR": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False), patch("code.extract.image_extract.shutil.which", return_value=None):
            records = extract_image_evidence(path, "image_fixture", self.captured_at, diagnostics)
        self.assertEqual(records[0].metadata["engine"], "filename_fallback")
        self.assertTrue(any(w["code"] == "executable_missing" for w in diagnostics.warnings))

    def test_repeat_extraction_is_stable_and_nonduplicating(self):
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            first = extract_doc_evidence(self._pdf(), "evidence_fixture", self.captured_at)
            second = extract_doc_evidence(self._pdf(), "evidence_fixture", self.captured_at)
        self.assertEqual([(r.file_id, r.resource_id) for r in first], [(r.file_id, r.resource_id) for r in second])
        self.assertEqual(len(first), len({(r.file_id, r.resource_id) for r in first}))

    def test_real_pdf_observation_requires_identity_anchor_and_respects_manifest_cutoff(self):
        """The production support attachment only enters case_07 after capture time."""
        dataset = load_dataset(Path("dataset"))
        manifest = dataset.file_id_to_evidence["evidence_58"]
        evidence_path = Path("dataset") / manifest["file_path"]
        captured_at = parse_ts(manifest["captured_at"])
        request = next(row for row in dataset.sample_requests if row["case_id"] == "case_07")
        identity = resolve_identity(request["email"], dataset)
        self.assertIsNotNone(identity)
        with patch.dict(os.environ, {"USE_PDF_EVIDENCE": "1", "USE_MEDIA_EVIDENCE": "0"}, clear=False):
            records = extract_doc_evidence(evidence_path, "evidence_58", captured_at)
        before = build_case_view(identity, captured_at.replace(year=captured_at.year - 1), records, dataset)
        after = build_case_view(identity, captured_at, records, dataset)
        self.assertNotIn("support_001", before)
        self.assertIn("support_001", after)
        self.assertEqual(after["support_001"].evidence_id, "evidence_58")
