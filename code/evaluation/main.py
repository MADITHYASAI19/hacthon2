"""Comprehensive evaluation tool for deletion audit predictions vs gold standard."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def levenshtein_distance(s1: List[Tuple], s2: List[Tuple]) -> int:
    """Calculate Levenshtein edit distance between two sequences of step tuples."""
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n]


def step_tuple(s: Dict[str, Any], include_evidence: bool = False) -> Tuple:
    if include_evidence:
        return (
            s.get("phase"),
            s.get("system_id"),
            s.get("resource_id"),
            s.get("operation"),
            s.get("state"),
            s.get("evidence_id", ""),
        )
    return (
        s.get("phase"),
        s.get("system_id"),
        s.get("resource_id"),
        s.get("operation"),
        s.get("state"),
    )


def evaluate(gold_path: Path, pred_path: Path, print_diffs: bool = True):
    with open(gold_path, "r", encoding="utf-8") as f:
        gold_rows = {r["case_id"]: r for r in csv.DictReader(f)}

    with open(pred_path, "r", encoding="utf-8") as f:
        pred_rows = {r["case_id"]: r for r in csv.DictReader(f)}

    statuses = ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
    confusion_matrix = {g: {p: 0 for p in statuses} for g in statuses}

    status_correct = 0
    total_cases = len(gold_rows)
    exact_sequence_matches = 0
    total_edit_distance = 0

    gold_step_tuples_total = 0
    pred_step_tuples_total = 0
    true_positive_steps = 0

    field_counts = {
        "phase": [0, 0],
        "system_id": [0, 0],
        "resource_id": [0, 0],
        "operation": [0, 0],
        "state": [0, 0],
        "evidence_id": [0, 0],
    }

    diffs = []

    for cid, g_row in gold_rows.items():
        p_row = pred_rows.get(cid)
        if not p_row:
            diffs.append(f"MISSING: {cid} in prediction file")
            continue

        g_stat = g_row.get("deletion_status", "")
        p_stat = p_row.get("deletion_status", "")

        if g_stat in confusion_matrix and p_stat in confusion_matrix[g_stat]:
            confusion_matrix[g_stat][p_stat] += 1

        if g_stat == p_stat:
            status_correct += 1

        g_steps = json.loads(g_row.get("steps_json", "[]"))
        p_steps = json.loads(p_row.get("steps_json", "[]"))

        g_tuples = [step_tuple(s, include_evidence=False) for s in g_steps]
        p_tuples = [step_tuple(s, include_evidence=False) for s in p_steps]

        gold_step_tuples_total += len(g_tuples)
        pred_step_tuples_total += len(p_tuples)

        # Count TP step tuples (multiset intersection)
        p_temp = list(p_tuples)
        for gt in g_tuples:
            if gt in p_temp:
                true_positive_steps += 1
                p_temp.remove(gt)

        # Field-level accuracy for matched index steps
        min_len = min(len(g_steps), len(p_steps))
        for i in range(min_len):
            for field in ["phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
                field_counts[field][1] += 1
                if g_steps[i].get(field, "") == p_steps[i].get(field, ""):
                    field_counts[field][0] += 1

        # Account for length differences in field counts
        len_diff = abs(len(g_steps) - len(p_steps))
        for field in field_counts:
            field_counts[field][1] += len_diff

        # Sequence match with evidence
        g_full = [step_tuple(s, include_evidence=True) for s in g_steps]
        p_full = [step_tuple(s, include_evidence=True) for s in p_steps]

        edit_dist = levenshtein_distance(g_full, p_full)
        total_edit_distance += edit_dist

        if edit_dist == 0 and g_stat == p_stat:
            exact_sequence_matches += 1
        else:
            diffs.append((cid, g_stat, p_stat, g_steps, p_steps, edit_dist))

    # Calculations
    status_acc = status_correct / total_cases if total_cases else 0
    seq_acc = exact_sequence_matches / total_cases if total_cases else 0
    avg_edit_dist = total_edit_distance / total_cases if total_cases else 0

    step_precision = (
        true_positive_steps / pred_step_tuples_total if pred_step_tuples_total else 0
    )
    step_recall = true_positive_steps / gold_step_tuples_total if gold_step_tuples_total else 0
    step_f1 = (
        (2 * step_precision * step_recall / (step_precision + step_recall))
        if (step_precision + step_recall)
        else 0
    )

    print("================================================================================")
    print("                    DELETION AUDIT EVALUATION REPORT                            ")
    print("================================================================================")
    print(f"Total Cases: {total_cases}")
    print(f"Status Accuracy: {status_correct}/{total_cases} ({status_acc:.2%})")
    print(f"Exact Sequence Match (Gold Equivalence): {exact_sequence_matches}/{total_cases} ({seq_acc:.2%})")
    print(f"Average Levenshtein Edit Distance: {avg_edit_dist:.2f} steps per case\n")

    print("--- Status Confusion Matrix (Rows: Gold, Cols: Predicted) ---")
    headers = f"{'Gold \\ Pred':<15}" + "".join(f"{s:<15}" for s in statuses)
    print(headers)
    for g in statuses:
        row = f"{g:<15}" + "".join(f"{confusion_matrix[g][p]:<15}" for p in statuses)
        print(row)
    print()

    print("--- Step-Level Accuracy (phase, system_id, resource_id, operation, state) ---")
    print(f"Gold Steps Total:      {gold_step_tuples_total}")
    print(f"Predicted Steps Total: {pred_step_tuples_total}")
    print(f"True Positive Steps:   {true_positive_steps}")
    print(f"Step Precision:        {step_precision:.4f} ({step_precision:.2%})")
    print(f"Step Recall:           {step_recall:.4f} ({step_recall:.2%})")
    print(f"Step F1 Score:         {step_f1:.4f} ({step_f1:.2%})\n")

    print("--- Field-Level Accuracy ---")
    for field, (correct, total) in field_counts.items():
        acc = correct / total if total else 0
        print(f"  {field:<15}: {correct:>4}/{total:<4} ({acc:.2%})")
    print()

    if print_diffs and diffs:
        print("================================================================================")
        print(f"                     PER-CASE DIFFS ({len(diffs)} NON-EXACT CASES)               ")
        print("================================================================================")
        for item in diffs:
            if isinstance(item, str):
                print(item)
                continue
            cid, gs, ps, g_steps, p_steps, ed = item
            print(f"\n>>> Case {cid} | Status: Gold={gs}, Pred={ps} | Edit Distance={ed}")
            print(f"  Gold Steps ({len(g_steps)}):")
            for s in g_steps:
                print(f"    [{s.get('step_no')}] {s.get('phase')} | {s.get('system_id')} | {s.get('resource_id')} | {s.get('operation')} | {s.get('state')} | ev={s.get('evidence_id')}")
            print(f"  Pred Steps ({len(p_steps)}):")
            for s in p_steps:
                print(f"    [{s.get('step_no')}] {s.get('phase')} | {s.get('system_id')} | {s.get('resource_id')} | {s.get('operation')} | {s.get('state')} | ev={s.get('evidence_id')}")

    return {
        "status_accuracy": status_acc,
        "exact_matches": exact_sequence_matches,
        "step_precision": step_precision,
        "step_recall": step_recall,
        "step_f1": step_f1,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate deletion audit predictions vs gold")
    parser.add_argument("--gold", type=Path, default=Path(__file__).resolve().parent.parent.parent / "dataset" / "sample_output.csv")
    parser.add_argument("--pred", type=Path, default=Path(__file__).resolve().parent.parent.parent / "output.csv")
    parser.add_argument("--diffs", action="store_true", default=True)

    args = parser.parse_args()
    evaluate(args.gold, args.pred, print_diffs=args.diffs)


if __name__ == "__main__":
    main()
