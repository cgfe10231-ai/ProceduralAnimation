"""Outermost Arm Rig transaction establishment migrated from `src/rig/arm_ik.py` (Task 10-B Layer 1 L1-02)."""

from typing import Any, Callable, List


# [INTRODUCED 2026-11-24T12:47:00+08:00]
# NODE: 10-B / L1-02
# FUNCTION: _establish_outermost_arm_rig_transaction
# PURPOSE: 按原始顺序创建外层事务实例、更新 Session 生命周期并登记活动事务
# REASON: 将正常事务建立协调迁入 Layer 1，同时复用 Layer 2 已有初始化与活动事务栈，维持原对象身份和异常边界
def _establish_outermost_arm_rig_transaction(
    arm: Any,
    session_rec: Any,
    *,
    transaction_context_cls: Callable[..., Any],
    active_transaction_stack: List[Any],
) -> Any:
    """Establish and register the outermost transaction in original order."""
    tx = transaction_context_cls(
        arm,
        session_record=session_rec,
    )
    session_rec.lifecycle_stage = "ACTIVE_TRANSACTION"
    active_transaction_stack.append(tx)
    return tx
