"""Coordinator-authorized isolation clear and tombstone retirement transition migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L1-11)."""

import math
import time
from typing import Any, Callable, Dict, Optional

from src.scene_transaction_integrity.layer2.session_records import (
    _ArmatureIsolationState,
)


# [INTRODUCED 2026-11-25T15:12:03+08:00]
# NODE: 10-B / L1-11
# FUNCTION: _clear_or_retire_failure_isolation_by_coordinator
# PURPOSE: 在 Layer 2 验证单次授权 grant 与实时证据后执行隔离解除或 FAILED-D 墓碑归档转换
# REASON: 将 Coordinator 授权隔离状态转换实现从 arm_ik.py 物理迁入 Layer 2
def _clear_or_retire_failure_isolation_by_coordinator(
    session_id: str,
    action: str,
    reason: str,
    authorization_grant: Optional[Dict[str, Any]] = None,
    verification_evidence: Optional[Dict[str, Any]] = None,
    *,
    archived_failed_d_tombstones: Dict[str, Dict[str, Any]],
    coordinator_authorization_grants: Dict[str, Dict[str, Any]],
    coordinator_grant_ttl_seconds: float,
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    managed_armature_identities: Dict[str, Any],
    coordinator_reap_stale_authorization_grants: Callable[[], None],
    coordinator_revoke_session_authorization_grants: Callable[[str], None],
    verify_deisolation_evidence: Callable[..., Dict[str, Any]],
    verify_dead_armature_tombstone_retirement_evidence: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Layer 2: Clear FAILED-B/C isolation or archive FAILED-D tombstone exclusively for Layer 1 Coordinator."""
    if authorization_grant is None:
        raise RuntimeError(
            f"Layer 2 rejected {'de-isolation' if action == 'CLEAR_TO_NONE' else 'tombstone retirement'}: "
            "authorization_grant is required; verification_evidence is not authorization"
        )
    grant_candidate = authorization_grant
    session_rec = managed_armature_identities.get(session_id)
    iso_rec = isolated_failed_armatures.get(session_id)
    if session_rec is None or iso_rec is None:
        raise RuntimeError(f"Cannot modify isolation state: session {session_id} not found in active isolation registry")

    action_label = "de-isolation" if action == "CLEAR_TO_NONE" else "tombstone retirement"

    # Audit & validate Coordinator single-use authorization grant
    if not isinstance(grant_candidate, dict):
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization_grant must be a valid dictionary")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError(f"Layer 2 rejected {action_label}: non-empty reason is required")
    grant_id = grant_candidate.get("grant_id")
    coordinator_reap_stale_authorization_grants()
    if not grant_id or grant_id not in coordinator_authorization_grants:
        raise RuntimeError(f"Layer 2 rejected {action_label}: invalid or missing Coordinator authorization grant")

    registered_grant = coordinator_authorization_grants[grant_id]
    if registered_grant.get("consumed", False):
        raise RuntimeError(f"Layer 2 rejected {action_label}: Coordinator authorization grant has already been consumed")
    if registered_grant.get("registry_session_id") != session_id:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant session mismatch "
            f"('{registered_grant.get('registry_session_id')}' != '{session_id}')"
        )
    if registered_grant.get("transition_action") != action:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant action mismatch "
            f"('{registered_grant.get('transition_action')}' != '{action}')"
        )
    if registered_grant.get("transaction_id") != iso_rec.get("transaction_id"):
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant transaction ID mismatch "
            f"('{registered_grant.get('transaction_id')}' != '{iso_rec.get('transaction_id')}')"
        )
    if registered_grant.get("failure_class") != iso_rec.get("failure_class"):
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant failure class mismatch "
            f"('{registered_grant.get('failure_class')}' != '{iso_rec.get('failure_class')}')"
        )
    if registered_grant.get("current_isolation_state") != session_rec.isolation_state.value:
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: grant isolation state mismatch "
            f"('{registered_grant.get('current_isolation_state')}' != '{session_rec.isolation_state.value}')"
        )

    # Authenticate the *presented* capability against the independent
    # Coordinator-owned record, not merely an attacker-supplied grant_id.
    if grant_candidate is registered_grant:
        raise RuntimeError(f"Layer 2 rejected {action_label}: grant registry record is not independently owned")
    bound_fields = (
        "grant_id", "registry_session_id", "transaction_id", "failure_class",
        "current_isolation_state", "transition_action", "evidence_status",
        "capability_nonce", "issued_monotonic", "expires_monotonic", "created_at",
    )
    if any(grant_candidate.get(field) != registered_grant.get(field) for field in bound_fields):
        raise RuntimeError(f"Layer 2 rejected {action_label}: presented grant binding mismatch")
    if grant_candidate.get("consumed") is not False:
        raise RuntimeError(f"Layer 2 rejected {action_label}: presented grant is already consumed")
    issued = registered_grant.get("issued_monotonic")
    expires = registered_grant.get("expires_monotonic")
    now = time.monotonic()
    if (
        type(issued) not in (float, int)
        or type(expires) not in (float, int)
        or not (math.isfinite(issued) and math.isfinite(expires))
        or now < issued or now >= expires
        or expires <= issued
        or expires - issued > coordinator_grant_ttl_seconds + 1e-6
    ):
        coordinator_authorization_grants.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization grant expired or invalid")

    # Evidence is not a permanent permission. Re-evaluate it immediately
    # before the FAILED-isolation state transition (TOCTOU defense).
    if action == "CLEAR_TO_NONE":
        latest_evidence = verify_deisolation_evidence(
            arm=session_rec.original_blender_ref, session_id=session_id,
        )
        evidence_ok = (
            latest_evidence.get("can_deisolate") is True
            and latest_evidence.get("status") == "RECOVERY_VERIFIED"
        )
    elif action == "ARCHIVE_TOMBSTONE":
        latest_evidence = verify_dead_armature_tombstone_retirement_evidence(session_id)
        evidence_ok = (
            latest_evidence.get("can_retire") is True
            and latest_evidence.get("status") == "TOMBSTONE_RETIREMENT_VERIFIED"
        )
    else:
        raise RuntimeError(f"Layer 2 rejected {action_label}: unsupported transition action")
    evidence_ok = evidence_ok and (
        latest_evidence.get("registry_session_id") == session_id
        and latest_evidence.get("transaction_id") == registered_grant.get("transaction_id")
        and latest_evidence.get("failure_class") == registered_grant.get("failure_class")
        and latest_evidence.get("isolation_state") == registered_grant.get("current_isolation_state")
        and latest_evidence.get("status") == registered_grant.get("evidence_status")
    )
    if not evidence_ok:
        coordinator_authorization_grants.pop(grant_id, None)
        raise RuntimeError(
            f"Layer 2 rejected {action_label}: recovery evidence no longer verified "
            f"({latest_evidence.get('status')}: {latest_evidence.get('reasons', [])})"
        )
    # Revalidation may update liveness records; check original isolation
    # identity and state once more before consuming the capability.
    if (
        managed_armature_identities.get(session_id) is not session_rec
        or isolated_failed_armatures.get(session_id) is not iso_rec
        or iso_rec.get("registry_session_id") != session_id
        or iso_rec.get("transaction_id") != registered_grant.get("transaction_id")
        or iso_rec.get("failure_class") != registered_grant.get("failure_class")
        or session_rec.isolation_state.value != registered_grant.get("current_isolation_state")
        or iso_rec.get("isolation_state") != registered_grant.get("current_isolation_state")
    ):
        coordinator_authorization_grants.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: isolation provenance changed during revalidation")

    # Real-time verification can be slow. Recheck the deadline immediately
    # before consumption rather than allowing a just-expired grant to pass.
    if time.monotonic() >= expires:
        coordinator_authorization_grants.pop(grant_id, None)
        raise RuntimeError(f"Layer 2 rejected {action_label}: authorization grant expired during evidence verification")

    # Atomic single-use consumption before irreversible isolation transition;
    # replay cannot succeed even when the transition raises afterwards.
    registered_grant["consumed"] = True
    coordinator_authorization_grants.pop(grant_id, None)
    grant_candidate["consumed"] = True

    if action == "CLEAR_TO_NONE":
        if session_rec.isolation_state == _ArmatureIsolationState.TOMBSTONED_FAILED_D:
            raise RuntimeError("Layer 2 rejected de-isolation: TOMBSTONED_FAILED_D cannot return to active status")
        previous_state = session_rec.isolation_state.value
        session_rec.isolation_state = _ArmatureIsolationState.NONE
        session_rec.lifecycle_stage = "NORMAL_TERMINAL"
        isolated_failed_armatures.pop(session_id, None)
        coordinator_revoke_session_authorization_grants(session_id)
        return {
            "registry_session_id": session_id,
            "previous_isolation_state": previous_state,
            "new_isolation_state": _ArmatureIsolationState.NONE.value,
            "action": "CLEAR_TO_NONE",
            "reason": reason,
            "grant_id": grant_id,
        }
    elif action == "ARCHIVE_TOMBSTONE":
        if session_rec.isolation_state != _ArmatureIsolationState.TOMBSTONED_FAILED_D:
            raise RuntimeError(
                f"Layer 2 rejected tombstone retirement: session {session_id} is in {session_rec.isolation_state}, "
                "expected TOMBSTONED_FAILED_D"
            )
        previous_state = session_rec.isolation_state.value
        session_rec.isolation_state = _ArmatureIsolationState.ARCHIVED_RETIRED
        session_rec.lifecycle_stage = "ARCHIVED_RETIRED"
        iso_rec["isolation_state"] = _ArmatureIsolationState.ARCHIVED_RETIRED.value
        if session_rec.tombstone_record is not None:
            session_rec.tombstone_record["isolation_state"] = _ArmatureIsolationState.ARCHIVED_RETIRED.value
            session_rec.tombstone_record["retirement_state"] = "ARCHIVED_RETIRED"
            session_rec.tombstone_record["retirement_reason"] = reason
        isolated_failed_armatures.pop(session_id, None)
        archived_failed_d_tombstones[session_id] = iso_rec
        coordinator_revoke_session_authorization_grants(session_id)
        return {
            "registry_session_id": session_id,
            "previous_isolation_state": previous_state,
            "new_isolation_state": _ArmatureIsolationState.ARCHIVED_RETIRED.value,
            "action": "ARCHIVE_TOMBSTONE",
            "reason": reason,
            "grant_id": grant_id,
        }
    else:
        raise RuntimeError(f"Unsupported Layer 2 isolation transition action: {action!r}")
