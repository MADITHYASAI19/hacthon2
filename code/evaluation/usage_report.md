# Token Usage and Cost Analysis

**Total Cases Audited:** 518

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