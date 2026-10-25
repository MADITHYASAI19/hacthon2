"""Main entry point for Deletion Audit Agent."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.extract.registry import load_all_evidence
from code.extract.media_config import ExtractionDiagnostics
from code.identity import resolve_identity
from code.intent import classify_all_requests_hybrid, classify_intent_offline
from code.loader import load_dataset, parse_ts
from code.planner import plan_case
from code.policy import evaluate_policy
from code.state import build_case_view
from code.usage import UsageLedger


def run_audit(
    requests_path: Path,
    output_path: Path,
    dataset_dir: Path,
    usage_report_path: Optional[Path] = None,
    media_diagnostics_path: Optional[Path] = None,
    use_llm: bool = False,
):
    print(f"Loading dataset from {dataset_dir}...")
    dataset = load_dataset(dataset_dir)

    print("Extracting evidence from all evidence files...")
    extraction_diagnostics = ExtractionDiagnostics()
    all_records = load_all_evidence(dataset, base_dir=dataset_dir.parent, diagnostics=extraction_diagnostics)
    print(f"Loaded {len(all_records)} evidence records.")
    print("Media extraction diagnostics: " + json.dumps(extraction_diagnostics.summary(), sort_keys=True))
    if media_diagnostics_path:
        media_diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
        media_diagnostics_path.write_text(
            json.dumps(extraction_diagnostics.summary(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # Read requests from target path
    with open(requests_path, "r", encoding="utf-8", newline="") as f:
        requests = list(csv.DictReader(f))

    print(f"Auditing {len(requests)} deletion requests...")
    usage = UsageLedger()

    def identity_has_direct_identifier(values):
        """Whether a record carries any explicit identifier-shaped value."""
        import re
        if isinstance(values, dict):
            for value in values.values():
                if identity_has_direct_identifier(value):
                    return True
            return False
        if isinstance(values, (list, tuple, set)):
            return any(identity_has_direct_identifier(value) for value in values)
        if values is None:
            return False
        value = str(values)
        return bool(
            re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", value, re.IGNORECASE)
            or re.search(r"\buser_\d+\b", value)
            or re.search(r"(?:email_hash|phone|email|lookup_key|customer_reference|subject_reference)[=:]", value, re.IGNORECASE)
        )

    # Intent is the sole optional LLM-assisted stage.  All later stages remain
    # deterministic and receive the selected intent result.
    classify_activity_emails = {
        req.get("email", "").strip().lower()
        for req in requests
        for act in dataset.system_activity
        if (act.get("event_type") or "").upper() == "CLASSIFY_REQUEST"
        and "non-deletion" in (act.get("details") or "").lower()
        and req.get("email", "").strip().lower() in (act.get("details") or "").lower()
    }
    intents = classify_all_requests_hybrid(
        requests,
        use_llm=use_llm,
        usage_ledger=usage,
        classify_activity_emails=classify_activity_emails,
        disagreements_log_path=ROOT / "code" / "evaluation" / "intent_disagreements.md" if use_llm else None,
    )
    offline_intents = {
        req.get("case_id", ""): classify_intent_offline(req.get("case_id", ""), req.get("request_text", ""))
        for req in requests
    }
    intent_changes = sum(
        intents[cid].intent != offline_intents[cid].intent for cid in intents
    )
    print(f"Intent mode: {'Grok' if use_llm else 'offline'}; intent changes versus offline: {intent_changes}")

    # Prepare each deletion case once, then use eligible deletion-worker account
    # events only when no direct/trace/catalog account anchor was available.
    prepared = {}
    reserved_account_ids = set()
    for req in requests:
        cid = req.get("case_id", "")
        intent_res = intents[cid]
        audit_at = parse_ts(req.get("audit_at", ""))
        requested_at = parse_ts(req.get("requested_at", ""))
        ident = resolve_identity(req.get("email", ""), dataset) if intent_res.intent != "NOT_DELETE" else None
        view = None
        if intent_res.intent != "NOT_DELETE" and ident:
            view = build_case_view(ident, audit_at, all_records, dataset, requested_at=requested_at)
            accounts = [rid for rid in view if rid.startswith("account_")]
            if accounts:
                reserved_account_ids.add(accounts[0])
        prepared[cid] = {
            "request": req,
            "intent": intent_res,
            "audit_at": audit_at,
            "requested_at": requested_at,
            "identity": ident,
            "view": view,
        }

    unresolved = [
        cid for cid, item in prepared.items()
        if item["intent"].intent != "NOT_DELETE" and item["identity"] and not any(
            rid.startswith("account_") for rid in (item["view"] or {})
        )
    ]
    # For cases without a directly-anchored account resource, link them to a
    # deletion_worker DELETE_RECORD (target: account_service) that appears in
    # system_activity.csv after requested_at and before audit_at.
    # Score each real deletion-worker event by its proximity to the workflow
    # report.  The report is emitted immediately after the worker task in the
    # supplied activity stream, whereas unrelated deletion tasks can also fall
    # after the request.  This is an evidence/timestamp join only: it never
    # manufactures an account id from a user id.
    # The reported_result is used only as a tie-break preference signal – it
    # does NOT filter out events with a different result, since all result
    # values can occur in the supplied activity stream.
    reported_to_result_pref = {
        "COMPLETE": "SUCCESS",
        "NOT_STARTED": "FAILED",
        "PARTIALLY_COMPLETE": "PARTIAL",
    }
    timing_pairs = []
    for cid in unresolved:
        item = prepared[cid]
        requested_at = item["requested_at"]
        audit_at = item["audit_at"]
        if not requested_at:
            continue
        preferred_result = reported_to_result_pref.get(
            (item["request"].get("reported_status") or "").upper(), ""
        )
        for act in dataset.system_activity:
            if (act.get("event_type") or "").upper() != "DELETE_RECORD":
                continue
            if (act.get("source_system") or "").lower() != "deletion_worker":
                continue
            if (act.get("target_system") or "").lower() != "account_service":
                continue
            rid = (act.get("resource_id") or "").strip()
            if not rid.startswith("account_") or rid in reserved_account_ids:
                continue
            # Skip if this account resource has evidence tied to a different identity.
            conflicting_identity = False
            for rec in all_records:
                if rec.resource_id != rid:
                    continue
                rec_manifest = dataset.file_id_to_evidence.get(rec.file_id, {})
                rec_capture = parse_ts(rec_manifest.get("captured_at"))
                if audit_at and rec_capture and rec_capture > audit_at:
                    continue
                if identity_has_direct_identifier(rec.identifiers) and not item["identity"].matches(rec.identifiers) and not item["identity"].matches(rec.user_ref):
                    conflicting_identity = True
                    break
            if conflicting_identity:
                continue
            event_time = parse_ts(act.get("event_time"))
            if not event_time or event_time < requested_at or (audit_at and event_time > audit_at):
                continue
            delta_seconds = (event_time - requested_at).total_seconds()
            reported_at = parse_ts(item["request"].get("reported_at", ""))
            report_delta_seconds = abs((event_time - reported_at).total_seconds()) if reported_at else delta_seconds
            # The reported result is a weak tie-breaker; its value is a claim,
            # not a substitute for the temporal join.
            result_penalty = 0 if (act.get("reported_result") or "").upper() == preferred_result else 1
            timing_pairs.append((report_delta_seconds, result_penalty, delta_seconds, cid, event_time, act.get("activity_id", ""), rid))

    assigned_cases = set()
    for report_delta_seconds, result_penalty, delta_seconds, cid, event_time, activity_id, rid in sorted(
        timing_pairs,
        key=lambda x: (x[0], x[1], x[2], int(x[3].split("_")[-1]) if x[3].split("_")[-1].isdigit() else x[3], x[4], x[5]),
    ):
        # A worker event is an auditable association for this request.  Do not
        # impose a synthetic one-to-one constraint across independent requests:
        # it can steal the closest, grounded event for a later case.
        if cid in assigned_cases:
            continue
        assigned_cases.add(cid)
        item = prepared[cid]
        item["view"] = build_case_view(
            item["identity"], item["audit_at"], all_records, dataset,
            requested_at=item["requested_at"], own_account_id_override=rid,
        )

    output_rows = []
    for req in requests:
        cid = req.get("case_id", "")
        item = prepared[cid]
        intent_res = item["intent"]

        if intent_res.intent == "NOT_DELETE":
            status, steps = plan_case(cid, "NOT_DELETE", [])
            output_rows.append({
                "case_id": cid,
                "deletion_status": status,
                "steps_json": json.dumps(steps, separators=(",", ":")),
            })
            continue

        ident = item["identity"]
        if not ident:
            status, steps = plan_case(cid, "DELETE", [])
            output_rows.append({
                "case_id": cid,
                "deletion_status": status,
                "steps_json": json.dumps(steps, separators=(",", ":")),
            })
            continue

        # 3. State reconstruction at audit_at (using the prepared, user-anchored view)
        case_view = item["view"] or {}

        # 4. Policy evaluation
        decisions = [evaluate_policy(res_state) for res_state in case_view.values()]

        # 5. Planning and sorting
        status, steps = plan_case(cid, "DELETE", decisions)

        output_rows.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps, separators=(",", ":")),
        })

    # Sort output rows by case_id (lexical == numeric for 0-padded case_01..case_518)
    output_rows_sorted = sorted(
        output_rows,
        key=lambda r: int(r["case_id"].split("_")[1]) if "_" in r["case_id"] and r["case_id"].split("_")[1].isdigit() else r["case_id"],
    )

    # Write output.csv
    print(f"Writing {len(output_rows_sorted)} rows to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"], quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(output_rows_sorted)

    if usage_report_path:
        usage.generate_report(len(requests), usage_report_path)

    print("Audit run completed successfully.")
    return {"intent_changes": intent_changes, "usage": usage, "use_llm": use_llm}


def check_llm() -> int:
    """Make one minimal Grok call and print only safe diagnostic information."""
    from code.llm import classify_intent_grok

    try:
        result, prompt_tokens, completion_tokens, _cost, from_cache = classify_intent_grok(
            'Classify this request: "Please delete my account."'
        )
        print(
            "OK "
            f"intent={result.get('intent', '')} cache_hit={from_cache} "
            f"input_tokens={prompt_tokens} output_tokens={completion_tokens} "
            f"total_tokens={prompt_tokens + completion_tokens}"
        )
        return 0
    except Exception as exc:
        print(f"failed: {exc}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists - Deletion Audit Agent")
    parser.add_argument("--requests", type=Path, default=ROOT / "dataset" / "deletion_requests.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "output.csv")
    parser.add_argument("--dataset", type=Path, default=ROOT / "dataset")
    parser.add_argument("--usage-report", type=Path, default=ROOT / "code" / "evaluation" / "usage_report.md")
    parser.add_argument("--media-diagnostics", type=Path, help="Write structured local PDF/OCR extraction diagnostics as JSON.")
    parser.add_argument("--use-llm", action="store_true", help="Enable optional Grok intent classification.")
    parser.add_argument("--offline", action="store_true", help="Force deterministic offline intent classification.")
    parser.add_argument("--check-llm", action="store_true", help="Make one safe Grok connectivity check and exit.")

    args = parser.parse_args()
    if args.check_llm:
        raise SystemExit(check_llm())

    # Default to Grok only when both required configuration values are present.
    # --offline wins even if --use-llm was also supplied.
    from code.llm import load_dotenv
    load_dotenv()
    llm_configured = bool(os.environ.get("XAI_API_KEY") and os.environ.get("GROK_MODEL"))
    use_llm = not args.offline and (args.use_llm or llm_configured)
    run_audit(
        requests_path=args.requests,
        output_path=args.out,
        dataset_dir=args.dataset,
        usage_report_path=args.usage_report,
        media_diagnostics_path=args.media_diagnostics,
        use_llm=use_llm,
    )


if __name__ == "__main__":
    main()
