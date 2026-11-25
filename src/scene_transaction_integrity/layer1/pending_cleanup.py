"""Pending cleanup preservation and retry lifecycle migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-07)."""

from typing import Any, Callable, Dict, Optional

from src.scene_transaction_integrity.layer1 import (
    cleanup_validation as _cleanup_validation,
    post_commit_cleanup as _post_commit_cleanup,
)
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import (
    _PENDING_ARM_RIG_CLEANUPS,
    _register_pending_arm_rig_cleanup,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _ISOLATED_FAILED_ARMATURES,
)
from src.scene_transaction_integrity.layer2.transaction_context import (
    _ArmRigTransactionContext,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: _coordinator_preserve_cleanup_pending
# PURPOSE: 在提交后清理失败或拒绝时严格验证状态并保留 CLEANUP_PENDING 状态与 Pending 注册，防止覆盖他事务或篡改 FAILED
# REASON: 将 Pending 挂起决策迁入 Layer 1，复用 Layer 2 被动登记入口并保留原冲突检查与状态护栏
def _coordinator_preserve_cleanup_pending(
    tx: Any,
    error: BaseException,
    *,
    transaction_context_cls: type = _ArmRigTransactionContext,
    transaction_state_cls: Any = _ArmRigTransactionState,
    pending_arm_rig_cleanups: Optional[Dict[str, Any]] = None,
    register_pending_arm_rig_cleanup: Optional[Callable[..., None]] = None,
) -> None:
    """Fail closed after logical commit without clobbering another transaction.

    Used by the initial cleanup exception paths. Never changes FAILED to
    COMMITTED/PENDING, never removes a FAILED isolation, and never pops a gate.
    In an impossible registry-key collision, raise rather than overwrite it.
    """
    if pending_arm_rig_cleanups is None:
        pending_arm_rig_cleanups = _PENDING_ARM_RIG_CLEANUPS
    if register_pending_arm_rig_cleanup is None:
        register_pending_arm_rig_cleanup = _register_pending_arm_rig_cleanup
    if not isinstance(tx, transaction_context_cls):
        raise RuntimeError("CLEANUP_PENDING_REGISTRATION_FAILED: invalid context") from error
    if tx.state not in (
        transaction_state_cls.COMMITTED,
        transaction_state_cls.CLEANUP_PENDING,
    ):
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: transaction {tx.tx_id} "
            f"cannot move from {tx.state} into CLEANUP_PENDING"
        ) from error
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("CLEANUP_PENDING_REGISTRATION_FAILED: invalid transaction ID") from error
    existing = pending_arm_rig_cleanups.get(tx.tx_id)
    if existing is not None and existing is not tx:
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: registry collision for {tx.tx_id}; "
            "foreign transaction preserved"
        ) from error
    if existing is tx and tx.state == transaction_state_cls.CLEANUP_PENDING:
        return
    tx.state = transaction_state_cls.CLEANUP_PENDING
    tx.cleanup_error = f"{type(error).__name__}: {error}"
    if existing is None:
        register_pending_arm_rig_cleanup(tx)
    if pending_arm_rig_cleanups.get(tx.tx_id) is not tx:
        raise RuntimeError(
            f"CLEANUP_PENDING_REGISTRATION_FAILED: transaction {tx.tx_id} not registered"
        ) from error


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: retry_pending_arm_rig_cleanup
# PURPOSE: 拒绝 FAILED 事务冒充重试，并对合法 CLEANUP_PENDING 事务按 Preflight -> retry_cleanup -> Apply Result 顺序执行重试
# REASON: 将挂起清理重试协调迁入 Layer 1，保持与初始清理共享同一套验证与裁决合同
def retry_pending_arm_rig_cleanup(
    tx_id: str,
    *,
    pending_arm_rig_cleanups: Optional[Dict[str, Any]] = None,
    isolated_failed_armatures: Optional[Dict[str, Any]] = None,
    transaction_state_cls: Any = _ArmRigTransactionState,
    coordinator_validate_cleanup_preflight: Optional[Callable[..., None]] = None,
    coordinator_apply_cleanup_result: Optional[Callable[..., None]] = None,
) -> None:
    """Retry cleanup of one pending transaction."""
    if pending_arm_rig_cleanups is None:
        pending_arm_rig_cleanups = _PENDING_ARM_RIG_CLEANUPS
    if isolated_failed_armatures is None:
        isolated_failed_armatures = _ISOLATED_FAILED_ARMATURES
    if coordinator_validate_cleanup_preflight is None:
        coordinator_validate_cleanup_preflight = (
            _cleanup_validation._coordinator_validate_cleanup_preflight
        )
    if coordinator_apply_cleanup_result is None:
        coordinator_apply_cleanup_result = (
            _post_commit_cleanup._coordinator_apply_cleanup_result
        )

    tx = pending_arm_rig_cleanups.get(tx_id)

    if tx is None:
        for iso_rec in isolated_failed_armatures.values():
            if iso_rec.get("transaction_id") == tx_id:
                raise RuntimeError(
                    f"Cannot retry cleanup for FAILED transaction {tx_id}: "
                    "FAILED transactions cannot be recovered via retry_pending_arm_rig_cleanup "
                    "or transition FAILED -> COMMITTED"
                )
        raise KeyError(
            f"Pending cleanup transaction not found: {tx_id}"
        )

    if tx.state == transaction_state_cls.FAILED:
        raise RuntimeError(
            f"Transaction {tx_id} is in FAILED state; "
            "FAILED -> COMMITTED transition is strictly forbidden"
        )

    if tx.state != transaction_state_cls.CLEANUP_PENDING:
        raise RuntimeError(
            f"Transaction {tx_id} is in state {tx.state}, expected CLEANUP_PENDING for pending cleanup retry"
        )

    coordinator_validate_cleanup_preflight(tx, phase="PENDING_RETRY")
    cleanup_result = tx.retry_cleanup()
    coordinator_apply_cleanup_result(tx, cleanup_result, phase="PENDING_RETRY")
