"""Cleanup preflight and result contract validation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-07)."""

from typing import Any, Callable, Dict, List, Optional

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
from src.scene_transaction_integrity.layer2.transaction_context import (
    _ArmRigTransactionContext,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)
from src.scene_transaction_integrity.layer2.transaction_states import (
    _ArmRigTransactionState,
)
from src.scene_transaction_integrity.layer6.cleanup_results import (
    _CleanupOutcome,
    _CleanupResult,
)


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: _coordinator_validate_cleanup_preflight
# PURPOSE: 在破坏性清理执行前核验 phase、事务类型与状态、空活动栈、Pending 注册表、原会话及骨架身份、FAILED 隔离和待清理队列
# REASON: 将 Cleanup Preflight 验证从 arm_ik.py 迁入 Layer 1，保持与结果后验分离且严禁调用 ensure_armature_session_identity
def _coordinator_validate_cleanup_preflight(
    tx: Any,
    phase: str,
    *,
    transaction_context_cls: type = _ArmRigTransactionContext,
    transaction_state_cls: Any = _ArmRigTransactionState,
    active_transaction_stack: Optional[List[Any]] = None,
    pending_arm_rig_cleanups: Optional[Dict[str, Any]] = None,
    managed_armature_identities: Optional[Dict[str, Any]] = None,
    isolated_failed_armatures: Optional[Dict[str, Any]] = None,
    armature_isolation_state_cls: Any = _ArmatureIsolationState,
    verify_armature_session_identity_record: Optional[Callable[..., Dict[str, Any]]] = None,
) -> None:
    """Authorize cleanup BEFORE its first destructive resource operation.

    This is the Coordinator's phase-admission decision, distinct from the
    post-operation CleanupResult validator. It performs no resource deletion,
    relationship mutation, gate clearing, or transaction-state transition.
    An unknown live identity or an isolation mismatch must fail closed.
    """
    if active_transaction_stack is None:
        active_transaction_stack = _ACTIVE_TRANSACTION_STACK
    if pending_arm_rig_cleanups is None:
        pending_arm_rig_cleanups = _PENDING_ARM_RIG_CLEANUPS
    if managed_armature_identities is None:
        managed_armature_identities = _MANAGED_ARMATURE_IDENTITIES
    if isolated_failed_armatures is None:
        isolated_failed_armatures = _ISOLATED_FAILED_ARMATURES
    if verify_armature_session_identity_record is None:
        verify_armature_session_identity_record = (
            _session_verification._verify_armature_session_identity_record
        )
    if phase not in ("INITIAL_CLEANUP", "PENDING_RETRY"):
        raise ValueError(f"Invalid cleanup preflight phase: {phase!r}")
    if not isinstance(tx, transaction_context_cls):
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: transaction context type is invalid")
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: missing transaction ID")

    expected_state = (
        transaction_state_cls.COMMITTED
        if phase == "INITIAL_CLEANUP"
        else transaction_state_cls.CLEANUP_PENDING
    )
    if tx.state != expected_state:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
            f"is {tx.state}, expected {expected_state}"
        )

    if active_transaction_stack:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: active transaction stack is nonempty "
            f"during {phase}"
        )

    registered_pending = pending_arm_rig_cleanups.get(tx.tx_id)
    if phase == "PENDING_RETRY":
        if registered_pending is not tx:
            raise RuntimeError(
                "CLEANUP_PREFLIGHT_REJECTED: pending registry transaction "
                f"identity mismatch for {tx.tx_id}"
            )
    elif registered_pending is not None:
        raise RuntimeError(
            "CLEANUP_PREFLIGHT_REJECTED: initial cleanup transaction "
            f"{tx.tx_id} already exists in the pending registry"
        )

    # Check both registry provenance and Blender's current object identity.
    # Never call ensure_armature_session_identity() here: it can register a new
    # session, which is not a valid substitute for the transaction's original.
    record = tx.session_record
    session_id = tx.session_id
    if not isinstance(session_id, str) or not session_id:
        raise RuntimeError("CLEANUP_PREFLIGHT_REJECTED: missing original session ID")
    if record is None or managed_armature_identities.get(session_id) is not record:
        raise RuntimeError(
            "CLEANUP_PREFLIGHT_REJECTED: original session registry record "
            f"not found or substituted for {tx.tx_id}"
        )
    if record.registry_session_id != session_id or record.original_blender_ref is not tx.arm:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: session and original Armature provenance "
            f"mismatch for {tx.tx_id}"
        )
    try:
        live_ptr = int(tx.arm.as_pointer())
    except BaseException as exc:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: cannot read original Armature identity "
            f"for {tx.tx_id}: {exc}"
        ) from exc
    if live_ptr != tx.arm_ptr or live_ptr != record.registration_pointer:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: original Armature pointer mismatch "
            f"for {tx.tx_id}"
        )
    try:
        identity_check = verify_armature_session_identity_record(record, candidate_arm=tx.arm)
    except BaseException as exc:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: Armature identity verification raised "
            f"for {tx.tx_id}: {exc}"
        ) from exc
    if identity_check.get("is_valid") is not True:
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: original Armature session not verified "
            f"for {tx.tx_id}: {identity_check.get('reasons', [])}"
        )

    if (record.isolation_state != armature_isolation_state_cls.NONE
            or session_id in isolated_failed_armatures):
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
            f"is associated with active FAILED isolation"
        )
    # Also defend against a malformed isolation registry record whose key is
    # different from the transaction's session ID, but whose tx_id matches.
    for isolation in isolated_failed_armatures.values():
        if isolation.get("transaction_id") == tx.tx_id:
            raise RuntimeError(
                f"CLEANUP_PREFLIGHT_REJECTED: transaction {tx.tx_id} "
                "is referenced by FAILED isolation under another registry key"
            )

    if (not isinstance(tx.uncleaned_stashed_objects, list)
            or not isinstance(tx.uncleaned_stashed_constraints, list)
            or any(not isinstance(entry, dict) for entry in tx.uncleaned_stashed_objects)
            or any(not isinstance(entry, dict) for entry in tx.uncleaned_stashed_constraints)):
        raise RuntimeError(
            f"CLEANUP_PREFLIGHT_REJECTED: cleanup resource queue is malformed "
            f"for {tx.tx_id}"
        )


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: _coordinator_validate_cleanup_result_contract
# PURPOSE: 在任何生命周期变更前严格校验 _CleanupResult 实例、精确 Outcome 类型、资源数量、errors 元组、cause 及三种结局不变式
# REASON: 将清理结果合同校验从 arm_ik.py 迁入 Layer 1，保持严格 type() 判断及错误文本零弱化
def _coordinator_validate_cleanup_result_contract(
    tx: Any,
    result: Any,
    phase: str,
    *,
    transaction_context_cls: type = _ArmRigTransactionContext,
    transaction_state_cls: Any = _ArmRigTransactionState,
    cleanup_result_cls: type = _CleanupResult,
    cleanup_outcome_cls: Any = _CleanupOutcome,
) -> None:
    """Validate the exact outcome contract BEFORE any lifecycle mutation.

    This routine does not repair a malformed result, infer a missing outcome,
    mutate the registry, or translate an invalid result into CLEANUP_SUCCESS.
    """
    if phase not in ("INITIAL_CLEANUP", "PENDING_RETRY"):
        raise ValueError(f"Invalid cleanup decision phase: {phase!r}")
    if not isinstance(tx, transaction_context_cls):
        raise RuntimeError("Coordinator rejected cleanup result: invalid transaction context")
    if not isinstance(result, cleanup_result_cls):
        raise RuntimeError(
            f"Coordinator rejected cleanup result: expected _CleanupResult instance, got {type(result)}"
        )
    if not isinstance(tx.tx_id, str) or not tx.tx_id:
        raise RuntimeError("Coordinator rejected cleanup result: missing transaction_id")
    if not isinstance(result.transaction_id, str) or result.transaction_id != tx.tx_id:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: transaction_id mismatch "
            f"({result.transaction_id!r} != {tx.tx_id!r})"
        )
    expected_state = (
        transaction_state_cls.COMMITTED
        if phase == "INITIAL_CLEANUP"
        else transaction_state_cls.CLEANUP_PENDING
    )
    if tx.state != expected_state:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: phase {phase} requires "
            f"state {expected_state.value}, got {tx.state}"
        )
    if type(result.outcome) is not cleanup_outcome_cls:
        raise RuntimeError(
            f"Coordinator rejected cleanup result: invalid CleanupOutcome {result.outcome!r}"
        )
    for label, count in (
        ("remaining_objects", result.remaining_objects),
        ("remaining_constraints", result.remaining_constraints),
    ):
        if type(count) is not int or count < 0:
            raise RuntimeError(
                f"Coordinator rejected cleanup result: {label} must be a nonnegative int, got {count!r}"
            )
    if not isinstance(result.errors, tuple) or any(
        not isinstance(message, str) or not message.strip()
        for message in result.errors
    ):
        raise RuntimeError(
            "Coordinator rejected cleanup result: errors must be a tuple of nonempty strings"
        )
    if result.cause is not None and not isinstance(result.cause, BaseException):
        raise RuntimeError(
            "Coordinator rejected cleanup result: cause must be BaseException or None"
        )
    if not isinstance(tx.uncleaned_stashed_objects, list) or not isinstance(
        tx.uncleaned_stashed_constraints, list
    ):
        raise RuntimeError("Coordinator rejected cleanup result: malformed cleanup queues")
    actual_rem_objs = len(tx.uncleaned_stashed_objects)
    actual_rem_cons = len(tx.uncleaned_stashed_constraints)
    if (result.remaining_objects != actual_rem_objs
            or result.remaining_constraints != actual_rem_cons):
        raise RuntimeError(
            "Coordinator rejected cleanup result: remaining resource count mismatch "
            f"(reported: objs={result.remaining_objects}, cons={result.remaining_constraints}; "
            f"actual: objs={actual_rem_objs}, cons={actual_rem_cons})"
        )
    remaining = result.remaining_objects + result.remaining_constraints
    if result.outcome == cleanup_outcome_cls.CLEANUP_SUCCESS:
        if result.errors:
            raise RuntimeError(
                f"Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot carry errors: {result.errors}"
            )
        if remaining:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot have remaining resources "
                f"(objs={result.remaining_objects}, cons={result.remaining_constraints})"
            )
        if result.cause is not None:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_SUCCESS cannot carry a cause"
            )
    elif result.outcome == cleanup_outcome_cls.CLEANUP_INCOMPLETE:
        if remaining == 0:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_INCOMPLETE requires remaining resources"
            )
    elif result.outcome == cleanup_outcome_cls.CLEANUP_FAILED:
        if remaining != 0 or not result.errors:
            raise RuntimeError(
                "Coordinator rejected cleanup result: CLEANUP_FAILED requires "
                "zero remaining resources and at least one error"
            )
    else:
        raise RuntimeError("Coordinator rejected cleanup result: unsupported outcome")
