"""Policy engine applying deletion_rules.csv."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from code.state import ResourceState


@dataclass
class PolicyDecision:
    resource_id: str
    system_id: str
    category: str
    required_action: str  # DELETE | REDACT | ANONYMIZE | RETAIN | DISABLE | BLOCK
    compliant: bool
    violation_type: Optional[str]  # REMAINING_RECORD | EXPOSED_PII | ACTIVE_DATA_FLOW | RESTORE_RISK | None
    current_state: str
    evidence_id: str


def evaluate_policy(res_state: ResourceState) -> PolicyDecision:
    """Evaluate resource state against deletion rules and return compliance decision."""
    cat = res_state.category
    res_id = res_state.resource_id
    sys_id = res_state.system_id
    state = res_state.state

    # Explicit record type wins over a broad resource prefix. Attachments and
    # secondary identifiers are deleted; shared support messages are redacted and
    # analytics profiles are anonymized.
    if cat in ("SUPPORT_ATTACHMENT", "SECONDARY_IDENTIFIER"):
        compliant = state != "PRESENT"
        return PolicyDecision(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            required_action="DELETE",
            compliant=compliant,
            violation_type=None if compliant else "REMAINING_RECORD",
            current_state=state,
            evidence_id=res_state.evidence_id,
        )

    # 1. Integration flow (data_flow_)
    if cat == "INTEGRATION_FLOW" or res_id.startswith("data_flow_"):
        if state == "ACTIVE":
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="DISABLE",
                compliant=False,
                violation_type="ACTIVE_DATA_FLOW",
                current_state=state,
                evidence_id=res_state.evidence_id,
            )
        else:
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="DISABLE",
                compliant=True,
                violation_type=None,
                current_state=state,
                evidence_id=res_state.evidence_id,
            )

    # 2. Backup archive (backup_)
    if cat == "BACKUP_ARCHIVE" or res_id.startswith("backup_"):
        if state == "ACTIVE":  # restore_allowed = true
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="BLOCK",
                compliant=False,
                violation_type="RESTORE_RISK",
                current_state=state,
                evidence_id=res_state.evidence_id,
            )
        else:
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="BLOCK",
                compliant=True,
                violation_type=None,
                current_state=state,
                evidence_id=res_state.evidence_id,
            )

    # 3. Retained records (Security Audit Log, Legal Hold)
    if cat in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD") or res_id.startswith("audit_record_") or res_id.startswith("legal_hold_"):
        return PolicyDecision(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            required_action="RETAIN",
            compliant=True,
            violation_type=None,
            current_state="PRESENT",
            evidence_id=res_state.evidence_id,
        )

    # 4. Account Tombstone
    if cat == "ACCOUNT_TOMBSTONE" or res_id.startswith("tombstone_"):
        if state == "PRESENT":
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="REDACT",
                compliant=False,
                violation_type="EXPOSED_PII",
                current_state=state,
                evidence_id=res_state.evidence_id,
            )
        else:
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="REDACT",
                compliant=True,
                violation_type=None,
                current_state=state,
                evidence_id=res_state.evidence_id,
            )

    # 5. Support Message (shared context -> REDACT)
    if cat == "SUPPORT_MESSAGE" or res_id.startswith("support_"):
        if state == "PRESENT":
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="REDACT",
                compliant=False,
                violation_type="EXPOSED_PII",
                current_state=state,
                evidence_id=res_state.evidence_id,
            )
        else:
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="REDACT",
                compliant=True,
                violation_type=None,
                current_state=state,
                evidence_id=res_state.evidence_id,
            )

    # 6. Analytics Profile (ANONYMIZE)
    if cat in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY") or res_id.startswith("analytics_"):
        if state == "PRESENT":
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="ANONYMIZE",
                compliant=False,
                violation_type="EXPOSED_PII",
                current_state=state,
                evidence_id=res_state.evidence_id,
            )
        else:
            return PolicyDecision(
                resource_id=res_id,
                system_id=sys_id,
                category=cat,
                required_action="ANONYMIZE",
                compliant=True,
                violation_type=None,
                current_state=state,
                evidence_id=res_state.evidence_id,
            )

    # 7. Complete deletion categories (USER_PROFILE, SEARCH_INDEX_ENTRY, USER_EXPORT, etc.)
    if state == "PRESENT":
        return PolicyDecision(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            required_action="DELETE",
            compliant=False,
            violation_type="REMAINING_RECORD",
            current_state=state,
            evidence_id=res_state.evidence_id,
        )
    else:
        return PolicyDecision(
            resource_id=res_id,
            system_id=sys_id,
            category=cat,
            required_action="DELETE",
            compliant=True,
            violation_type=None,
            current_state=state,
            evidence_id=res_state.evidence_id,
        )
