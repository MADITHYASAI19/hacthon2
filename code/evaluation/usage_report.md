# Token Usage and Cost Analysis

**Total Cases Audited:** 32

## Summary by Model

| Provider | Model | Real calls | Cache hits | API errors | Input tokens | Output tokens | Total tokens | Estimated cost (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| None | offline deterministic pipeline | 0 | 0 | 0 | 0 | 0 | 0 | $0.0000 |

## Overall Totals

- **Total Model Calls:** 0
- **Total Tokens:** 0 (0.0 per request)
- **Total Estimated Cost:** $0.0000 ($0.00000 per request)

## Methodology & Optimization
- Only intent classification can call Grok; identity resolution, evidence extraction, state reconstruction, policy evaluation, and planning are deterministic code.
- API errors fall back to the offline intent result and are counted above.

## Local media-extraction usage (2026-10-25)

- PDF engine: `pypdf` (local), enabled only with `USE_PDF_EVIDENCE=1`.
- OCR engine: Pillow + `pytesseract` client (local), enabled only with
  `USE_IMAGE_OCR=1`; the required `tesseract` executable was unavailable on
  this machine, so no OCR call was performed.
- Enabled sample run: 4 PDF files processed with embedded text; 11 PNG files
  inspected and reported as `executable_missing`; 0 external/API/LLM calls,
  tokens, or cost.
- These local engines are not model usage and are not included in the token or
  cost totals above. See `media_sample_diagnostics.json` for the structured
  per-file warning records.
