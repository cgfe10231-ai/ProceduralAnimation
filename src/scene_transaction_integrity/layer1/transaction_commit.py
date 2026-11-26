"""Transaction logical commit coordination and active stack release migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-05)."""

from typing import Any, Callable, List


# [INTRODUCED 2026-11-24T13:37:00+08:00]
# NODE: 10-B / L1-05
# FUNCTION: _commit_arm_rig_transaction
# PURPOSE: 执行 rollback_only 拒绝检查、COMMITTING 状态推进、Depsgraph 更新、提交身份核验及 COMMITTED 与 NORMAL_TERMINAL 确认
# REASON: 将正常逻辑提交协调链迁入 Layer 1，同时保留原外层 try/except 异常处理、回滚分类及后续清理控制边界
def _commit_arm_rig_transaction(
    arm: Any,
    tx: Any,
    session_rec: Any,
    *,
    transaction_state_cls: Any,
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
    verify_armature_session_identity_record: Callable[..., Any],
) -> None:
    """Prepare and confirm the logical transaction commit."""
    if tx.rollback_only:
        raise RuntimeError(
            f"Arm rig transaction commit rejected: transaction {tx.tx_id} is marked rollback_only "
            f"(first failure reason: {tx.rollback_only_reason})"
        )

    # Phase 1: Reversible Commit Preparation
    tx.state = transaction_state_cls.COMMITTING
    trigger_fault_injection("before_commit_prepare", {"tx": tx})

    depsgraph_update()
    trigger_fault_injection("during_commit_prepare", {"tx": tx})

    commit_id_check = verify_armature_session_identity_record(
        session_rec,
        candidate_arm=arm,
    )
    if not commit_id_check["is_valid"]:
        raise RuntimeError(
            "Armature session identity invalidated during COMMITTING: "
            + "; ".join(commit_id_check["reasons"])
        )

    # Phase 2: Logical Commit Confirmation
    tx.state = transaction_state_cls.COMMITTED
    session_rec.lifecycle_stage = "NORMAL_TERMINAL"


# [INTRODUCED 2026-11-24T13:37:00+08:00]
# NODE: 10-B / L1-05
# FUNCTION: _release_active_arm_rig_transaction
# PURPOSE: 在协调器 finally 出口校验成员资格并从原活动事务栈移除当前事务实例
# REASON: 将活动事务栈释放协调迁入 Layer 1，复用 Layer 2 原列表对象并保持异常与正常出口的统一清理时机
def _release_active_arm_rig_transaction(
    tx: Any,
    *,
    active_transaction_stack: List[Any],
) -> None:
    """Release the transaction from the original active stack."""
    if tx in active_transaction_stack:
        active_transaction_stack.remove(tx)
