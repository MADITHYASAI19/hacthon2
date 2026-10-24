"""Plan generation, phase ordering, and step serialization."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from code.policy import PolicyDecision

# Strict operation order within each phase as defined in problem_statement.md
FINDING_OP_ORDER = {
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
}

REMEDIATION_OP_ORDER = {
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,
}

VERIFICATION_OP_ORDER = {
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6,
}


def plan_case(
    case_id: str,
    intent: str,
    decisions: List[PolicyDecision],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate final deletion_status and ordered steps_json array."""
    if intent == "NOT_DELETE":
        return "NOT_APPLICABLE", []

    findings = []
    remediations = []
    verifications = []

    has_violation = any(not d.compliant for d in decisions)
    status = "INCOMPLETE" if has_violation else "COMPLETE"

    for d in decisions:
        res_id = d.resource_id
        sys_id = d.system_id

        if not d.compliant:
            # 1. FINDING
            f_op = ""
            f_state = "PRESENT"
            if d.violation_type == "REMAINING_RECORD":
                f_op = "REPORT_REMAINING_RECORD"
                f_state = "PRESENT"
            elif d.violation_type == "EXPOSED_PII":
                f_op = "REPORT_EXPOSED_PII"
                f_state = "PRESENT"
            elif d.violation_type == "ACTIVE_DATA_FLOW":
                f_op = "REPORT_ACTIVE_DATA_FLOW"
                f_state = "ACTIVE"
            elif d.violation_type == "RESTORE_RISK":
                f_op = "REPORT_RESTORE_RISK"
                f_state = "ACTIVE"

            findings.append({
                "phase": "FINDING",
                "system_id": sys_id,
                "resource_id": res_id,
                "operation": f_op,
                "state": f_state,
                "evidence_id": d.evidence_id,
            })

            # 2. REMEDIATION
            r_op = ""
            r_state = ""
            if d.required_action == "DISABLE":
                r_op = "DISABLE_DATA_FLOW"
                r_state = "DISABLED"
            elif d.required_action == "BLOCK":
                r_op = "BLOCK_RESTORE"
                r_state = "BLOCKED"
            elif d.required_action == "DELETE":
                r_op = "DELETE_RECORD"
                r_state = "ABSENT"
            elif d.required_action == "REDACT":
                r_op = "REDACT_RECORD"
                r_state = "REDACTED"
            elif d.required_action == "ANONYMIZE":
                r_op = "ANONYMIZE_RECORD"
                r_state = "ANONYMIZED"

            remediations.append({
                "phase": "REMEDIATION",
                "system_id": sys_id,
                "resource_id": res_id,
                "operation": r_op,
                "state": r_state,
                "evidence_id": "",
            })

        # 3. VERIFICATION
        v_op = ""
        v_state = ""
        if d.required_action == "DELETE":
            v_op = "VERIFY_RECORD_ABSENT"
            v_state = "ABSENT"
        elif d.required_action == "RETAIN":
            v_op = "VERIFY_RECORD_PRESENT"
            v_state = "PRESENT"
        elif d.required_action == "REDACT":
            v_op = "VERIFY_RECORD_REDACTED"
            v_state = "REDACTED"
        elif d.required_action == "ANONYMIZE":
            v_op = "VERIFY_RECORD_ANONYMIZED"
            v_state = "ANONYMIZED"
        elif d.required_action == "DISABLE":
            v_op = "VERIFY_DATA_FLOW_DISABLED"
            v_state = "DISABLED"
        elif d.required_action == "BLOCK":
            v_op = "VERIFY_RESTORE_BLOCKED"
            v_state = "BLOCKED"

        verifications.append({
            "phase": "VERIFICATION",
            "system_id": sys_id,
            "resource_id": res_id,
            "operation": v_op,
            "state": v_state,
            "evidence_id": d.evidence_id if status == "COMPLETE" else "",
        })

    # Sort within each phase: operation order, then system_id asc, then resource_id asc (string sort)
    findings_sorted = sorted(
        findings,
        key=lambda s: (FINDING_OP_ORDER.get(s["operation"], 99), s["system_id"], s["resource_id"]),
    )
    remediations_sorted = sorted(
        remediations,
        key=lambda s: (REMEDIATION_OP_ORDER.get(s["operation"], 99), s["system_id"], s["resource_id"]),
    )
    verifications_sorted = sorted(
        verifications,
        key=lambda s: (VERIFICATION_OP_ORDER.get(s["operation"], 99), s["system_id"], s["resource_id"]),
    )

    combined_steps = []
    if status == "COMPLETE":
        combined_steps = verifications_sorted
    else:
        combined_steps = findings_sorted + remediations_sorted + verifications_sorted

    # Assign consecutive 1..N step numbers
    final_steps = []
    for idx, step in enumerate(combined_steps, 1):
        step_obj = {
            "step_no": idx,
            "phase": step["phase"],
            "system_id": step["system_id"],
            "resource_id": step["resource_id"],
            "operation": step["operation"],
            "state": step["state"],
            "evidence_id": step["evidence_id"],
        }
        final_steps.append(step_obj)

    return status, final_steps
