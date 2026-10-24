"""Usage tracker and ledger."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class ModelUsage:
    model_name: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    cache_hits: int = 0
    api_errors: int = 0


class UsageLedger:
    def __init__(self):
        self.usages: Dict[str, ModelUsage] = {}

    def record_call(self, model_name: str, prompt_tokens: int, completion_tokens: int, cost: float = 0.0):
        if model_name not in self.usages:
            self.usages[model_name] = ModelUsage(model_name=model_name)
        u = self.usages[model_name]
        u.calls += 1
        u.prompt_tokens += prompt_tokens
        u.completion_tokens += completion_tokens
        u.total_tokens += (prompt_tokens + completion_tokens)
        u.estimated_cost += cost

    def _usage(self, model_name: str) -> ModelUsage:
        if model_name not in self.usages:
            self.usages[model_name] = ModelUsage(model_name=model_name)
        return self.usages[model_name]

    def record_cache_hit(self, model_name: str):
        self._usage(model_name).cache_hits += 1

    def record_api_error(self, model_name: str):
        self._usage(model_name).api_errors += 1

    def generate_report(self, total_cases: int, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Token Usage and Cost Analysis",
            "",
            f"**Total Cases Audited:** {total_cases}",
            "",
            "## Summary by Model",
            "",
            "| Provider | Model | Real calls | Cache hits | API errors | Input tokens | Output tokens | Total tokens | Estimated cost (USD) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]

        tot_calls = sum(u.calls for u in self.usages.values())
        tot_prompt = sum(u.prompt_tokens for u in self.usages.values())
        tot_comp = sum(u.completion_tokens for u in self.usages.values())
        tot_tokens = sum(u.total_tokens for u in self.usages.values())
        tot_cost = sum(u.estimated_cost for u in self.usages.values())

        for u in self.usages.values():
            lines.append(
                f"| xAI | `{u.model_name}` | {u.calls} | {u.cache_hits} | {u.api_errors} | {u.prompt_tokens:,} | {u.completion_tokens:,} | {u.total_tokens:,} | ${u.estimated_cost:.4f} |"
            )

        if not self.usages:
            lines.append("| None | offline deterministic pipeline | 0 | 0 | 0 | 0 | 0 | 0 | $0.0000 |")

        lines.extend([
            "",
            "## Overall Totals",
            "",
            f"- **Total Model Calls:** {tot_calls:,}",
            f"- **Total Tokens:** {tot_tokens:,} ({tot_tokens/max(1, total_cases):.1f} per request)",
            f"- **Total Estimated Cost:** ${tot_cost:.4f} (${tot_cost/max(1, total_cases):.5f} per request)",
            "",
            "## Methodology & Optimization",
            "- Only intent classification can call Grok; identity resolution, evidence extraction, state reconstruction, policy evaluation, and planning are deterministic code.",
            "- API errors fall back to the offline intent result and are counted above.",
        ])

        output_path.write_text("\n".join(lines), encoding="utf-8")
