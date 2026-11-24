"""Pending committed cleanup transaction registry migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L1-03)."""

from typing import Any, Dict, Tuple

# [INTRODUCED 2026-11-24T13:16:00+08:00]
# NODE: 10-B / L1-03
# FUNCTION: _PENDING_ARM_RIG_CLEANUPS
# PURPOSE: 持有已逻辑提交但清理未完成的 Arm Rig 事务单一真实运行时注册表
# REASON: 将待清理事务注册表所有权从 arm_ik.py 迁入 Layer 2，消除双份字典并由 Coordinator 统一门禁引用
_PENDING_ARM_RIG_CLEANUPS: Dict[str, Any] = {}


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: _register_pending_arm_rig_cleanup
# PURPOSE: 在事务状态确认为 CLEANUP_PENDING 后向原 Pending 注册表被动写入事务引用
# REASON: 将 Pending Cleanup 注册表写入动作迁入 Layer 2，保持 Layer 1 独占状态决定权而 Layer 2 仅被动登记
def _register_pending_arm_rig_cleanup(
    tx: Any,
    *,
    transaction_state_cls: Any,
    pending_arm_rig_cleanups: Dict[str, Any],
) -> None:
    if tx.state != transaction_state_cls.CLEANUP_PENDING:
        raise RuntimeError(
            "Cannot register cleanup for "
            "a non-pending transaction"
        )

    pending_arm_rig_cleanups[tx.tx_id] = tx


# [INTRODUCED 2026-11-24T15:31:00+08:00]
# NODE: 10-B / L1-07
# FUNCTION: get_pending_arm_rig_cleanup_ids
# PURPOSE: 返回当前 Pending Cleanup 注册表中排序后的事务 ID 元组
# REASON: 将 Pending 注册表只读查询迁入 Layer 2，维持原始排序及 tuple 返回类型
def get_pending_arm_rig_cleanup_ids(
    *,
    pending_arm_rig_cleanups: Dict[str, Any],
) -> Tuple[str, ...]:
    """Return pending cleanup transaction IDs."""
    return tuple(
        sorted(pending_arm_rig_cleanups)
    )
