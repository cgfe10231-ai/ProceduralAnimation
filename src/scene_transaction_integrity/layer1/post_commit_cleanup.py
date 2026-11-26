"""Post-commit irreversible cleanup coordination and success confirmation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-06)."""

from typing import Any, Callable, Dict, List, Optional

from src.scene_transaction_integrity.layer1 import (
    cleanup_validation as _cleanup_validation,
)
from src.scene_transaction_integrity.layer2 import (
    session_verification as _session_verification,
)
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import (
    _PENDING_ARM_RIG_CLEANUPS,
)
from src.scene_transaction_integrity.layer2.session_records import (
    _ArmatureIsolationState,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _ISOLATED_FAILED_ARMATURES,
    _MANAGED_ARMATURE_IDENTITIES,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)
from src.scene_transaction_integrity.layer6.cleanup_results import (
    _CleanupOutcome,
)


# [INTRODUCED 2026-11-24T13:44:00+08:00]
# NODE: 10-B / L1-06
# FUNCTION: _dispatch_initial_post_commit_cleanup
# PURPOSE: 在逻辑提交且活动事务栈释放后初始化待清理队列、调度清理预检与执行并保留两段既有异常保护
# REASON: 将外层事务 Phase 3 提交后清理调度迁入 Layer 1，保持 COMMITTED 条件、队列初始化及 Pending 兜底边界不变
def _dispatch_initial_post_commit_cleanup(
    tx: Any,
    *,
    transaction_state_cls: Any,
    trigger_fault_injection: Callable[..., None],
    coordinator_validate_cleanup_preflight: Callable[..., None],
    coordinator_preserve_cleanup_pending: Callable[..., None],
    coordinator_apply_cleanup_result: Callable[..., None],
) -> None:
    """Dispatch initial irreversible cleanup after logical commit."""
    if tx.state == transaction_state_cls.COMMITTED:
        tx.uncleaned_stashed_constraints = list(tx.stashed_constraints)
        tx.uncleaned_stashed_objects = list(tx.stashed_objects)

        try:
            trigger_fault_injection(
                "after_logical_commit",
                {"tx": tx},
            )
            trigger_fault_injection(
                "during_commit_cleanup",
                {"tx": tx},
            )
            coordinator_validate_cleanup_preflight(
                tx,
                phase="INITIAL_CLEANUP",
            )
            cleanup_result = tx.retry_cleanup()
        except BaseException as exc:
            coordinator_preserve_cleanup_pending(tx, exc)
            raise RuntimeError(
                "Arm rig transaction committed, "
                "but post-commit cleanup failed (irreversible cleanup failed): "
                f"{exc}"
            ) from exc

        try:
            coordinator_apply_cleanup_result(
                tx,
                cleanup_result,
                phase="INITIAL_CLEANUP",
            )
        except BaseException as exc:
            coordinator_preserve_cleanup_pending(tx, exc)
            raise


# [INTRODUCED 2026-11-24T13:44:00+08:00]
# NODE: 10-B / L1-06
# FUNCTION: _confirm_cleanup_success
# PURPOSE: 在 CLEANUP_SUCCESS 全部合同验证通过后确认最终 COMMITTED 状态并在 PENDING_RETRY 下释放原 Pending 注册项
# REASON: 将清理成功确认迁入 Layer 1，严格复用 Layer 2 原 Pending Cleanup 注册表与事务状态枚举
def _confirm_cleanup_success(
    tx: Any,
    phase: str,
    *,
    pending_arm_rig_cleanups: Dict[str, Any],
    transaction_state_cls: Any,
) -> None:
    """Confirm a validated successful cleanup result."""
    if (
        phase == "PENDING_RETRY"
        and pending_arm_rig_cleanups.get(tx.tx_id) is not tx
    ):
        raise RuntimeError(
            "Coordinator rejected cleanup result: pending registry changed before release"
        )

    tx.cleanup_error = None
    tx.state = transaction_state_cls.COMMITTED

    if phase == "PENDING_RETRY":
        pending_arm_rig_cleanups.pop(tx.tx_id)


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: _coordinator_apply_cleanup_result
# PURPOSE: 依次校验清理结果合同、空活动栈、原会话与骨架身份、Pending 归属及 FAILED 隔离并完成最终成功确认或非成功挂起
# REASON: 将清理结果裁决从 arm_ik.py 迁入 Layer 1，复用已有结果验证、成功确认与挂起保留入口
def _coordinator_apply_cleanup_result(
    tx: Any,
    result: Any,
    phase: str,
    *,
    coordinator_validate_cleanup_result_contract: Optional[Callable[..., None]] = None,
    active_transaction_stack: Optional[List[Any]] = None,
    managed_armature_identities: Optional[Dict[str, Any]] = None,
    pending_arm_rig_cleanups: Optional[Dict[str, Any]] = None,
    isolated_failed_armatures: Optional[Dict[str, Any]] = None,
    armature_isolation_state_cls: Any = _ArmatureIsolationState,
    transaction_state_cls: Any = _ArmRigTransactionState,
    cleanup_outcome_cls: Any = _CleanupOutcome,
    verify_armature_session_identity_record: Optional[Callable[..., Dict[str, Any]]] = None,
    confirm_cleanup_success: Optional[Callable[..., None]] = None,
    coordinator_preserve_cleanup_pending: Optional[Callable[..., None]] = None,
) -> None:
    """Exclusively decide cleanup state after full result/identity validation.

    No malformed result, uncertain Armature, or FAILED isolation may be treated
    as success; rejection is reported, not swallowed or coerced to NO_EFFECT.
    """
    if coordinator_validate_cleanup_result_contract is None:
        coordinator_validate_cleanup_result_contract = (
            _cleanup_validation._coordinator_validate_cleanup_result_contract
        )
    if active_transaction_stack is None:
        active_transaction_stack = _ACTIVE_TRANSACTION_STACK
    if managed_armature_identities is None:
        managed_armature_identities = _MANAGED_ARMATURE_IDENTITIES
    if pending_arm_rig_cleanups is None:
        pending_arm_rig_cleanups = _PENDING_ARM_RIG_CLEANUPS
    if isolated_failed_armatures is None:
        isolated_failed_armatures = _ISOLATED_FAILED_ARMATURES
    if verify_armature_session_identity_record is None:
        verify_armature_session_identity_record = (
            _session_verification._verify_armature_session_identity_record
        )
    if confirm_cleanup_success is None:
        confirm_cleanup_success = _confirm_cleanup_success
    if coordinator_preserve_cleanup_pending is None:
        from src.scene_transaction_integrity.layer1 import (
            pending_cleanup as _pending_cleanup,
        )

        coordinator_preserve_cleanup_pending = (
            _pending_cleanup._coordinator_preserve_cleanup_pending
        )
    coordinator_validate_cleanup_result_contract(tx, result, phase)

    if active_transaction_stack:
        raise RuntimeError(
            "Coordinator rejected cleanup result: active transaction stack must be empty"
        )
    # Verify original registry provenance, not a newly generated replacement
    # session from ensure_armature_session_identity().
    session_id = tx.session_id
    record = tx.session_record
    if (not isinstance(session_id, str) or not session_id
            or record is None
            or managed_armature_identities.get(session_id) is not record
            or record.registry_session_id != session_id):
        raise RuntimeError(
            "Coordinator rejected cleanup result: session_id mismatch or original session record unavailable"
        )
    if record.original_blender_ref is not tx.arm:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature reference mismatch"
        )
    try:
        pointer = int(tx.arm.as_pointer())
    except BaseException as exc:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature identity unreadable"
        ) from exc
    if pointer != tx.arm_ptr or pointer != record.registration_pointer:
        raise RuntimeError(
            "Coordinator rejected cleanup result: original Armature pointer mismatch"
        )
    try:
        identity_check = verify_armature_session_identity_record(record, candidate_arm=tx.arm)
    except BaseException as exc:
        raise RuntimeError(
            "Coordinator rejected cleanup result: Armature identity verification raised"
        ) from exc
    if identity_check.get("is_valid") is not True:
        raise RuntimeError(
            "Coordinator rejected cleanup result: Armature identity unverified: "
            f"{identity_check.get('reasons', [])}"
        )

    registered = pending_arm_rig_cleanups.get(tx.tx_id)
    if phase == "PENDING_RETRY":
        if registered is not tx:
            raise RuntimeError(
                "Coordinator rejected cleanup result: transaction "
                f"{tx.tx_id} identity mismatch or absent in _PENDING_ARM_RIG_CLEANUPS"
            )
    elif registered is not None:
        raise RuntimeError(
            "Coordinator rejected cleanup result: unexpected pending registry entry "
            f"for initial cleanup {tx.tx_id}"
        )

    # Any FAILED isolation of this Armature blocks a cleanup-result decision.
    # ALSO reject an isolation record under a corrupted/mis-keyed session entry.
    # No try/except here: an identity or isolation read error MUST propagate.
    if (record.isolation_state != armature_isolation_state_cls.NONE
            or session_id in isolated_failed_armatures):
        raise RuntimeError(
            f"Coordinator rejected cleanup result: active FAILED isolation for session {session_id}"
        )
    for isolated in isolated_failed_armatures.values():
        if isolated.get("transaction_id") == tx.tx_id:
            raise RuntimeError(
                "Coordinator rejected cleanup result: transaction "
                f"{tx.tx_id} associated with FAILED isolation under another key"
            )

    if result.outcome is cleanup_outcome_cls.CLEANUP_SUCCESS:
        confirm_cleanup_success(
            tx,
            phase,
            pending_arm_rig_cleanups=pending_arm_rig_cleanups,
            transaction_state_cls=transaction_state_cls,
        )
        return

    # Non-success outcome: keep gate, preserve original traceback in __cause__.
    err_msg = (
        f"Arm rig transaction commit cleanup {result.outcome.value}: "
        f"transaction={tx.tx_id}; phase={phase}; "
        f"remaining_objects={result.remaining_objects}; "
        f"remaining_constraints={result.remaining_constraints}; "
        f"errors={'; '.join(result.errors)}"
    )
    coordinator_preserve_cleanup_pending(tx, RuntimeError(err_msg))
    tx.cleanup_error = "; ".join(result.errors) if result.errors else "Cleanup incomplete or failed"
    if result.cause is not None:
        raise RuntimeError(err_msg) from result.cause
    raise RuntimeError(err_msg)
