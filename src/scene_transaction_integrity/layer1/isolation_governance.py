"""Isolation de-isolation and tombstone retirement coordinator entrypoints migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-10)."""

import uuid
from typing import Any, Callable, Dict, Optional

import bpy


# [INTRODUCED 2026-11-25T14:51:00+08:00]
# NODE: 10-B / L1-10
# FUNCTION: request_armature_deisolation
# PURPOSE: 作为 Layer 1 Coordinator 接收解除隔离请求、驱动 Layer 5 证据核验并在批准时签发 CLEAR_TO_NONE 授权转换隔离状态
# REASON: 将隔离治理主入口及证据验证链整体迁入目标层
def request_armature_deisolation(
    arm: Optional[bpy.types.Object],
    reason: str,
    session_id: Optional[str] = None,
    raise_on_reject: bool = False,
    *,
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    verify_deisolation_evidence: Callable[..., Dict[str, Any]],
    issue_coordinator_authorization_grant: Callable[..., Dict[str, Any]],
    clear_or_retire_failure_isolation_by_coordinator: Callable[..., Dict[str, Any]],
    append_deisolation_audit: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Evaluate Layer 5 evidence and authorize or reject de-isolation (Section 8.1/8.3)."""
    # Enforce non-empty string reason
    if not isinstance(reason, str) or not reason.strip():
        reason_err = "De-isolation rejected: reason must be a non-empty string"
        audit_entry = {
            "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
            "operation": "REQUEST_DEISOLATION",
            "decision": "REJECTED",
            "registry_session_id": session_id,
            "transaction_id": None,
            "failure_class": None,
            "previous_isolation_state": None,
            "new_isolation_state": None,
            "reason": reason,
            "verification_status": "INVALID_REASON",
            "verification_reasons": [reason_err],
        }
        append_deisolation_audit(audit_entry)
        if raise_on_reject:
            raise ValueError(reason_err)
        return {
            "approved": False,
            "action": "REJECTED",
            "registry_session_id": session_id,
            "reasons": [reason_err],
            "audit_entry": audit_entry,
        }

    evidence = verify_deisolation_evidence(arm=arm, session_id=session_id)
    resolved_session_id = evidence.get("registry_session_id") or session_id
    iso_rec = isolated_failed_armatures.get(resolved_session_id) if resolved_session_id else None
    tx_id = (
        evidence.get("transaction_id")
        or (iso_rec.get("transaction_id") if iso_rec is not None else None)
    )
    failure_class = evidence.get("failure_class")
    previous_state = evidence.get("isolation_state")

    if evidence.get("can_deisolate", False) and resolved_session_id is not None:
        grant = issue_coordinator_authorization_grant(
            session_id=resolved_session_id,
            transition_action="CLEAR_TO_NONE",
            arm=arm,
        )
        transition = clear_or_retire_failure_isolation_by_coordinator(
            session_id=resolved_session_id,
            action="CLEAR_TO_NONE",
            reason=reason,
            authorization_grant=grant,
        )
        audit_entry = {
            "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
            "operation": "REQUEST_DEISOLATION",
            "decision": "APPROVED",
            "registry_session_id": resolved_session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "previous_isolation_state": previous_state,
            "new_isolation_state": transition["new_isolation_state"],
            "grant_id": grant["grant_id"],
            "reason": reason,
            "verification_status": evidence.get("status"),
            "verification_reasons": list(evidence.get("reasons", [])),
        }
        append_deisolation_audit(audit_entry)
        return {
            "approved": True,
            "action": "DEISOLATED",
            "registry_session_id": resolved_session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "isolation_state": transition["new_isolation_state"],
            "evidence": evidence,
            "audit_entry": audit_entry,
        }

    audit_entry = {
        "audit_id": f"deiso_{uuid.uuid4().hex[:8]}",
        "operation": "REQUEST_DEISOLATION",
        "decision": "REJECTED",
        "registry_session_id": resolved_session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "previous_isolation_state": previous_state,
        "new_isolation_state": previous_state,
        "reason": reason,
        "verification_status": evidence.get("status"),
        "verification_reasons": list(evidence.get("reasons", [])),
    }
    append_deisolation_audit(audit_entry)

    if raise_on_reject:
        raise RuntimeError(
            f"Armature de-isolation rejected for session {resolved_session_id} "
            f"(status={evidence.get('status')}): {'; '.join(evidence.get('reasons', []))}"
        )

    return {
        "approved": False,
        "action": "REJECTED",
        "registry_session_id": resolved_session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "isolation_state": previous_state,
        "evidence": evidence,
        "audit_entry": audit_entry,
    }


# [INTRODUCED 2026-11-25T14:51:00+08:00]
# NODE: 10-B / L1-10
# FUNCTION: retire_dead_armature_tombstone
# PURPOSE: 作为 Layer 1 Coordinator 接收墓碑退休请求、驱动 Layer 5 墓碑证据核验并在批准时签发 ARCHIVE_TOMBSTONE 授权完成归档
# REASON: 将隔离治理主入口及证据验证链整体迁入目标层
def retire_dead_armature_tombstone(
    session_id: str,
    reason: str,
    raise_on_reject: bool = False,
    *,
    verify_dead_armature_tombstone_retirement_evidence: Callable[..., Dict[str, Any]],
    issue_coordinator_authorization_grant: Callable[..., Dict[str, Any]],
    clear_or_retire_failure_isolation_by_coordinator: Callable[..., Dict[str, Any]],
    append_deisolation_audit: Callable[[Dict[str, Any]], Any],
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Verify dead Armature tombstone retirement evidence and transition to ARCHIVED_RETIRED."""
    # Enforce non-empty string reason
    if not isinstance(reason, str) or not reason.strip():
        reason_err = "Tombstone retirement rejected: reason must be a non-empty string"
        audit_entry = {
            "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
            "operation": "RETIRE_DEAD_TOMBSTONE",
            "decision": "REJECTED",
            "registry_session_id": session_id,
            "transaction_id": None,
            "failure_class": None,
            "previous_isolation_state": None,
            "new_isolation_state": None,
            "reason": reason,
            "verification_status": "INVALID_REASON",
            "verification_reasons": [reason_err],
        }
        append_deisolation_audit(audit_entry)
        if raise_on_reject:
            raise ValueError(reason_err)
        return {
            "approved": False,
            "action": "REJECTED",
            "registry_session_id": session_id,
            "reasons": [reason_err],
            "audit_entry": audit_entry,
        }

    evidence = verify_dead_armature_tombstone_retirement_evidence(session_id)
    previous_state = evidence.get("isolation_state")
    tx_id = evidence.get("transaction_id")
    failure_class = evidence.get("failure_class")

    if evidence.get("can_retire", False):
        grant = issue_coordinator_authorization_grant(
            session_id=session_id,
            transition_action="ARCHIVE_TOMBSTONE",
        )
        transition = clear_or_retire_failure_isolation_by_coordinator(
            session_id=session_id,
            action="ARCHIVE_TOMBSTONE",
            reason=reason,
            authorization_grant=grant,
        )
        audit_entry = {
            "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
            "operation": "RETIRE_DEAD_TOMBSTONE",
            "decision": "APPROVED",
            "registry_session_id": session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "previous_isolation_state": previous_state,
            "new_isolation_state": transition["new_isolation_state"],
            "grant_id": grant["grant_id"],
            "reason": reason,
            "verification_status": evidence.get("status"),
            "verification_reasons": list(evidence.get("reasons", [])),
        }
        append_deisolation_audit(audit_entry)
        return {
            "approved": True,
            "action": "ARCHIVED_RETIRED",
            "registry_session_id": session_id,
            "transaction_id": tx_id,
            "failure_class": failure_class,
            "isolation_state": transition["new_isolation_state"],
            "evidence": evidence,
            "audit_entry": audit_entry,
        }

    audit_entry = {
        "audit_id": f"retire_{uuid.uuid4().hex[:8]}",
        "operation": "RETIRE_DEAD_TOMBSTONE",
        "decision": "REJECTED",
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "previous_isolation_state": previous_state,
        "new_isolation_state": previous_state,
        "reason": reason,
        "verification_status": evidence.get("status"),
        "verification_reasons": list(evidence.get("reasons", [])),
    }
    append_deisolation_audit(audit_entry)

    if raise_on_reject:
        raise RuntimeError(
            f"Dead Armature tombstone retirement rejected for session {session_id} "
            f"(status={evidence.get('status')}): {'; '.join(evidence.get('reasons', []))}"
        )

    return {
        "approved": False,
        "action": "REJECTED",
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "isolation_state": previous_state,
        "evidence": evidence,
        "audit_entry": audit_entry,
    }