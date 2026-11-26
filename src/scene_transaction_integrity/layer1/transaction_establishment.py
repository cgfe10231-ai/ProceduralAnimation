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
    transaction_context_cls: type,
    transaction_context_factory: Callable[..., Any],
    active_transaction_stack: List[Any],
) -> Any:
    """Establish and register the outermost transaction in original order."""
    tx = transaction_context_factory(
        arm,
        session_record=session_rec,
    )
    if not isinstance(tx, transaction_context_cls):
        raise RuntimeError(
            "Transaction context factory did not return an _ArmRigTransactionContext instance"
        )
    session_rec.lifecycle_stage = "ACTIVE_TRANSACTION"
    active_transaction_stack.append(tx)
    return tx


# [INTRODUCED 2026-11-24T13:23:30+08:00]
# NODE: 10-B / L1-04
# FUNCTION: _capture_transaction_entry_fingerprint
# PURPOSE: 在预写入阶段触发故障注入并调用结构指纹捕获，同时保留捕获失败的零写入完整性证据
# REASON: 将外层事务预写入指纹捕获协调迁入 Layer 1，确保未触发指纹注入或指纹捕获失败时外层 pre_snap_fp 仍为 None
def _capture_transaction_entry_fingerprint(
    arm: Any,
    tx: Any,
    *,
    trigger_fault_injection: Callable[..., None],
    capture_pre_snapshot_structural_fingerprint: Callable[..., Any],
) -> Any:
    """Capture transaction entry fingerprint and preserve failure evidence."""
    trigger_fault_injection(
        "during_pre_snapshot_fingerprint",
        {"arm": arm, "tx": tx},
    )

    try:
        return capture_pre_snapshot_structural_fingerprint(arm)
    except BaseException as fp_exc:
        tx.pre_write_integrity_compromised = True
        tx.pre_write_integrity_reasons = [
            f"Pre-snapshot fingerprint capture failed: {fp_exc}"
        ]
        raise


# [INTRODUCED 2026-11-24T13:23:30+08:00]
# NODE: 10-B / L1-04
# FUNCTION: _snapshot_and_activate_transaction
# PURPOSE: 登记事务入口对象与 Collection 指针证据、推进至 SNAPSHOTTING、捕获快照并在成功后激活至 ACTIVE
# REASON: 将外层事务快照与激活协调迁入 Layer 1，保持 Layer 5 快照实现不变且外层 pre_snap_fp 在入口指针或快照失败时保持已捕获引用
def _snapshot_and_activate_transaction(
    arm: Any,
    tx: Any,
    pre_snap_fp: Any,
    *,
    transaction_state_cls: Any,
    snapshot_arm_rig_state: Callable[..., Any],
) -> None:
    """Register entry evidence, capture snapshot and activate transaction."""
    tx.entry_object_ptrs = (
        pre_snap_fp.get("all_object_ptrs")
        if isinstance(pre_snap_fp, dict)
        else None
    )
    tx.entry_collection_ptrs = (
        pre_snap_fp.get("all_collection_ptrs")
        if isinstance(pre_snap_fp, dict)
        else None
    )
    tx.state = transaction_state_cls.SNAPSHOTTING
    tx.snapshot = snapshot_arm_rig_state(arm)
    tx.state = transaction_state_cls.ACTIVE
