"""Unified admission gate status query migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L1-08)."""

from typing import Any, Callable, Dict, Optional

from src.scene_transaction_integrity.layer2.session_records import (
    ArmatureSessionIdentityRecord,
)


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: query_admission_gate_status
# PURPOSE: 基于受管会话、待清理注册表、隔离与墓碑状态查询统一准入门禁状态并返回原始查询字典
# REASON: 将准入门禁状态查询迁入 Layer 2，同时由兼容入口先行执行 Layer 1 存活扫描以避免 Layer 2 反向调用 Layer 1
def query_admission_gate_status(
    arm: Optional[Any] = None,
    session_id: Optional[str] = None,
    *,
    managed_armature_identities: Dict[str, Any],
    pending_arm_rig_cleanups: Dict[str, Any],
    isolated_failed_armatures: Dict[str, Any],
    archived_failed_d_tombstones: Dict[str, Any],
    armature_liveness_status_cls: Any,
    armature_isolation_state_cls: Any,
    safe_object_pointer: Callable[..., int],
    verify_armature_session_identity_record: Callable[..., Dict[str, Any]],
) -> Dict[str, Any]:
    """Layer 2: Read-only query of unified admission gate status for an Armature or session_id."""
    session_rec: Optional[ArmatureSessionIdentityRecord] = None
    if session_id is not None:
        session_rec = managed_armature_identities.get(session_id)
    elif arm is not None:
        for rec in managed_armature_identities.values():
            if rec.original_blender_ref is arm:
                session_rec = rec
                break
            if rec.liveness_status == armature_liveness_status_cls.ALIVE_VERIFIED:
                ver = verify_armature_session_identity_record(rec, candidate_arm=arm)
                if ver["is_valid"]:
                    session_rec = rec
                    break

    resolved_session_id = session_rec.registry_session_id if session_rec is not None else session_id
    arm_ptr = safe_object_pointer(
        arm,
        fallback=(session_rec.registration_pointer if session_rec is not None else 0),
    )

    pending_cleanup_txs = [
        tx_id
        for tx_id, tx in pending_arm_rig_cleanups.items()
        if (arm_ptr and tx.arm_ptr == arm_ptr)
        or (resolved_session_id is not None and getattr(tx, "session_id", None) == resolved_session_id)
    ]
    iso_rec = isolated_failed_armatures.get(resolved_session_id) if resolved_session_id else None
    archived_rec = archived_failed_d_tombstones.get(resolved_session_id) if resolved_session_id else None

    id_check = (
        verify_armature_session_identity_record(session_rec, candidate_arm=arm)
        if session_rec is not None
        else {"is_valid": False, "reasons": ["Session record not registered"]}
    )

    cleanup_blocked = len(pending_cleanup_txs) > 0
    failed_isolated = bool(
        iso_rec is not None
        or (
            session_rec is not None
            and session_rec.isolation_state != armature_isolation_state_cls.NONE
        )
    )
    identity_valid = bool(id_check["is_valid"])

    return {
        "registry_session_id": resolved_session_id,
        "cleanup_pending_blocked": cleanup_blocked,
        "pending_cleanup_transaction_ids": sorted(pending_cleanup_txs),
        "failed_isolation_blocked": failed_isolated,
        "failure_class": (
            iso_rec.get("failure_class")
            if iso_rec is not None
            else (archived_rec.get("failure_class") if archived_rec is not None else None)
        ),
        "isolation_state": (
            session_rec.isolation_state.value
            if session_rec is not None
            else None
        ),
        "liveness_status": (
            session_rec.liveness_status.value
            if session_rec is not None
            else None
        ),
        "identity_valid": identity_valid,
        "identity_reasons": id_check.get("reasons", []),
        "can_admit": (not cleanup_blocked and not failed_isolated and identity_valid),
    }
