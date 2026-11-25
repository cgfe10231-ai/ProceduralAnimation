"""Coordinator authorization grant lifecycle migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-11)."""

import math
import time
import uuid
from typing import Any, Callable, Dict, Optional

import bpy


# [INTRODUCED 2026-11-25T15:12:03+08:00]
# NODE: 10-B / L1-11
# FUNCTION: _coordinator_reap_stale_authorization_grants
# PURPOSE: 清理过期、格式异常或与当前隔离状态失配的 Coordinator 授权 grant
# REASON: 将 Coordinator grant 生命周期管理从 arm_ik.py 物理迁入 Layer 1
def _coordinator_reap_stale_authorization_grants(
    *,
    coordinator_authorization_grants: Dict[str, Dict[str, Any]],
    coordinator_grant_ttl_seconds: float,
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    managed_armature_identities: Dict[str, Any],
) -> None:
    """Revoke expired, malformed, or provenance-stale grants without touching FAILED isolation."""
    now = time.monotonic()
    for grant_id, grant in tuple(coordinator_authorization_grants.items()):
        if not isinstance(grant, dict):
            coordinator_authorization_grants.pop(grant_id, None)
            continue
        issued = grant.get("issued_monotonic")
        expires = grant.get("expires_monotonic")
        session_id = grant.get("registry_session_id")
        session = managed_armature_identities.get(session_id)
        isolation = isolated_failed_armatures.get(session_id)
        invalid_time = (
            type(issued) not in (float, int)
            or type(expires) not in (float, int)
            or not (math.isfinite(issued) and math.isfinite(expires))
            or issued > now or expires <= now
            or expires <= issued
            or expires - issued > coordinator_grant_ttl_seconds + 1e-6
        )
        stale_binding = (
            session is None or isolation is None
            or session.registry_session_id != session_id
            or isolation.get("registry_session_id") != session_id
            or isolation.get("transaction_id") != grant.get("transaction_id")
            or isolation.get("failure_class") != grant.get("failure_class")
            or session.isolation_state.value != grant.get("current_isolation_state")
            or isolation.get("isolation_state") != grant.get("current_isolation_state")
        )
        if (
            invalid_time or stale_binding or grant.get("consumed") is not False
            or grant.get("grant_id") != grant_id
            or not isinstance(grant.get("capability_nonce"), str)
            or not grant.get("capability_nonce")
        ):
            coordinator_authorization_grants.pop(grant_id, None)


# [INTRODUCED 2026-11-25T15:12:03+08:00]
# NODE: 10-B / L1-11
# FUNCTION: _coordinator_revoke_session_authorization_grants
# PURPOSE: 在新签发 grant 或完成状态转换后撤销指定会话的旧 grant
# REASON: 将 Coordinator grant 生命周期管理从 arm_ik.py 物理迁入 Layer 1
def _coordinator_revoke_session_authorization_grants(
    session_id: str,
    *,
    coordinator_authorization_grants: Dict[str, Dict[str, Any]],
) -> None:
    """Invalidate all older grants for a session after a new issue or successful transition."""
    for grant_id, grant in tuple(coordinator_authorization_grants.items()):
        if isinstance(grant, dict) and grant.get("registry_session_id") == session_id:
            coordinator_authorization_grants.pop(grant_id, None)


# [INTRODUCED 2026-11-25T15:12:03+08:00]
# NODE: 10-B / L1-11
# FUNCTION: _issue_coordinator_authorization_grant
# PURPOSE: 校验 Layer 5 恢复/墓碑退休证据并签发单次 Coordinator 内部授权 grant
# REASON: 将 Coordinator grant 签发实现从 arm_ik.py 物理迁入 Layer 1
def _issue_coordinator_authorization_grant(
    session_id: str,
    transition_action: str = "CLEAR_TO_NONE",
    arm: Optional[bpy.types.Object] = None,
    *,
    coordinator_authorization_grants: Dict[str, Dict[str, Any]],
    coordinator_grant_ttl_seconds: float,
    isolated_failed_armatures: Dict[str, Dict[str, Any]],
    managed_armature_identities: Dict[str, Any],
    coordinator_reap_stale_authorization_grants: Callable[[], None],
    coordinator_revoke_session_authorization_grants: Callable[[str], None],
    verify_deisolation_evidence: Callable[..., Dict[str, Any]],
    verify_dead_armature_tombstone_retirement_evidence: Callable[..., Dict[str, Any]],
    failed_transaction_class_cls: Any,
    armature_isolation_state_cls: Any,
    legacy_kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Layer 1 Coordinator: Issue a single-use internal authorization grant binding verified Layer 5 recovery evidence.

    Execution order:
    1. Read current session from _MANAGED_ARMATURE_IDENTITIES.
    2. Read current isolation record from _ISOLATED_FAILED_ARMATURES.
    3. Confirm both point to the same session.
    4. Check requested transition_action in ("CLEAR_TO_NONE", "ARCHIVE_TOMBSTONE").
    5. Call Layer 5 to execute real-time verification (verify_armature_deisolation_evidence or _verify_dead_armature_tombstone_retirement_evidence).
    6. Verify that verification evidence matches registry fields strictly.
    7. Generate single-use grant binding grant_id, session, tx_id, failure_class, isolation_state, action.
    8. Register grant in _COORDINATOR_AUTHORIZATION_GRANTS.
    9. Return grant.
    """
    session_rec = managed_armature_identities.get(session_id)
    iso_rec = isolated_failed_armatures.get(session_id)
    if session_rec is None:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' not found in _MANAGED_ARMATURE_IDENTITIES")
    if iso_rec is None:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' not found in _ISOLATED_FAILED_ARMATURES")

    if session_rec.registry_session_id != session_id or iso_rec.get("registry_session_id") != session_id:
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: registry session ID mismatch for '{session_id}'")

    if transition_action not in ("CLEAR_TO_NONE", "ARCHIVE_TOMBSTONE"):
        raise RuntimeError(f"Cannot issue Coordinator authorization grant: unsupported transition action {transition_action!r}")

    tx_id = iso_rec.get("transaction_id")
    failure_class = iso_rec.get("failure_class")
    current_iso_state = session_rec.isolation_state.value

    if transition_action == "CLEAR_TO_NONE":
        target_arm = arm if arm is not None else session_rec.original_blender_ref
        evidence = verify_deisolation_evidence(arm=target_arm, session_id=session_id)

        if not evidence.get("can_deisolate", False) or evidence.get("status") != "RECOVERY_VERIFIED":
            err_reasons = "; ".join(evidence.get("reasons", [])) or f"status is {evidence.get('status')}"
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: recovery verification failed: {err_reasons}")

        if evidence.get("registry_session_id") != session_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence registry_session_id mismatch")
        if evidence.get("transaction_id") != tx_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence transaction_id mismatch")
        if evidence.get("failure_class") != failure_class:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence failure_class mismatch")
        if evidence.get("isolation_state") != current_iso_state:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence isolation_state mismatch")

        evidence_status = evidence.get("status", "RECOVERY_VERIFIED")

    elif transition_action == "ARCHIVE_TOMBSTONE":
        evidence = verify_dead_armature_tombstone_retirement_evidence(session_id=session_id)

        if not evidence.get("can_retire", False) or evidence.get("status") != "TOMBSTONE_RETIREMENT_VERIFIED":
            err_reasons = "; ".join(evidence.get("reasons", [])) or f"status is {evidence.get('status')}"
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: tombstone retirement verification failed: {err_reasons}")

        if failure_class != failed_transaction_class_cls.FAILED_D.value or current_iso_state != armature_isolation_state_cls.TOMBSTONED_FAILED_D.value:
            raise RuntimeError(f"Cannot issue Coordinator authorization grant: session '{session_id}' is not an active FAILED-D tombstone")

        if evidence.get("registry_session_id") != session_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence registry_session_id mismatch")
        if evidence.get("transaction_id") != tx_id:
            raise RuntimeError("Cannot issue Coordinator authorization grant: evidence transaction_id mismatch")

        evidence_status = evidence.get("status", "TOMBSTONE_RETIREMENT_VERIFIED")

    # Only the latest verified capability for a session remains active.
    # This does not clear any FAILED isolation or modify Blender resources.
    coordinator_reap_stale_authorization_grants()
    coordinator_revoke_session_authorization_grants(session_id)
    issued_monotonic = time.monotonic()
    grant_id = f"grant_{uuid.uuid4().hex}"
    grant = {
        "grant_id": grant_id,
        "registry_session_id": session_id,
        "transaction_id": tx_id,
        "failure_class": failure_class,
        "current_isolation_state": current_iso_state,
        "transition_action": transition_action,
        "evidence_status": evidence_status,
        "capability_nonce": uuid.uuid4().hex,
        "issued_monotonic": issued_monotonic,
        "expires_monotonic": issued_monotonic + coordinator_grant_ttl_seconds,
        "consumed": False,
        "created_at": time.time(),
    }
    # A caller receives a separate dictionary; mutating the returned grant
    # cannot rewrite the Coordinator's authoritative capability record.
    coordinator_authorization_grants[grant_id] = dict(grant)
    return grant


# [INTRODUCED 2026-11-25T15:12:03+08:00]
# NODE: 10-B / L1-11
# FUNCTION: _clear_coordinator_authorization_grants
# PURPOSE: 清空当前活跃的 Coordinator 授权 grant 注册表
# REASON: 将 Coordinator grant 生命周期管理从 arm_ik.py 物理迁入 Layer 1
def _clear_coordinator_authorization_grants(
    *,
    coordinator_authorization_grants: Dict[str, Dict[str, Any]],
) -> None:
    """Clear active Coordinator authorization grants (test fixture cleanup)."""
    coordinator_authorization_grants.clear()
