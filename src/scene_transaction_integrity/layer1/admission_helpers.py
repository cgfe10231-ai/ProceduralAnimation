"""Admission and object name/uncertainty helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1)."""

from typing import Any, Callable, Dict


def _safe_object_name(obj: Any, fallback: str = "<invalid_or_destroyed_object>") -> str:
    """Safely read a Blender object's name without raising ReferenceError."""
    if obj is None:
        return fallback
    try:
        return str(obj.name)
    except BaseException:
        return fallback


def _identity_failure_is_uncertain(verification: Dict[str, Any]) -> bool:
    """Keep indeterminate Blender reads separate from confirmed session invalidation."""
    return bool(
        verification.get("object_liveness_status", "UNKNOWN") == "UNKNOWN"
        or verification.get("identity_verification_uncertain", False)
    )


# [INTRODUCED 2026-11-24T15:08:00+08:00]
# NODE: 10-B / L1-08
# FUNCTION: _assert_nested_transaction_admission
# PURPOSE: 校验嵌套/重入事务的跨骨架禁止、外层 ACTIVE 状态及 rollback_only 准入条件
# REASON: 将 _arm_rig_transaction() 内嵌套事务三个准入判断迁入 Layer 1，保持 try/yield/except/mark_rollback_only 控制流不变
def _assert_nested_transaction_admission(
    arm: Any,
    outer_tx: Any,
    *,
    transaction_state_cls: Any,
    safe_object_name: Callable[[Any], str],
) -> None:
    """Validate nested transaction re-entry ownership, ACTIVE state, and rollback_only status."""
    if outer_tx.arm != arm:
        outer_name = safe_object_name(outer_tx.arm)
        req_name = safe_object_name(arm)
        raise RuntimeError(
            f"Cross-armature nested transaction rejected: active transaction owns armature "
            f"'{outer_name}', but requested transaction is for armature '{req_name}'."
        )
    if outer_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError(
            f"Nested transaction rejected: outer transaction {outer_tx.tx_id} is in state "
            f"{outer_tx.state}, expected ACTIVE."
        )
    if outer_tx.rollback_only:
        raise RuntimeError(
            f"Nested transaction rejected: outer transaction {outer_tx.tx_id} is already marked "
            f"rollback_only ({outer_tx.rollback_only_reason})."
        )
