"""Post-commit irreversible cleanup coordination and success confirmation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-06)."""

from typing import Any, Callable, Dict


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
