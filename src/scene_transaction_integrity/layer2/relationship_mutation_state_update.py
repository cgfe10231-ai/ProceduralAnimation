"""Relationship mutation state transition migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-11)."""

from typing import Any, Dict

from src.scene_transaction_integrity.layer2.relationship_states import (
    _LEGAL_RELATIONSHIP_LOG_TRANSITIONS,
    _RelationshipOperationState,
)


# [INTRODUCED 2026-11-24T00:21:00+08:00]
# NODE: 10-B / L2-11
# FUNCTION: _update_relationship_mutation_state
# PURPOSE: 根据已有七状态合法转换表验证并原位更新关系事务操作记录
# REASON: 将 TransactionContext 的关系状态转换执行实现迁入 Layer 2，保持原始状态机及异常合同
def _update_relationship_mutation_state(
    tx: Any,
    op_record: Dict[str, Any],
    new_state: _RelationshipOperationState,
) -> None:
    """Transition a relationship operation record across the approved 7-state machine."""
    raw_current = op_record.get("operation_state")
    current_state = (
        raw_current
        if isinstance(raw_current, _RelationshipOperationState)
        else _RelationshipOperationState(raw_current)
    )
    target_state = (
        new_state
        if isinstance(new_state, _RelationshipOperationState)
        else _RelationshipOperationState(new_state)
    )
    if (current_state, target_state) not in _LEGAL_RELATIONSHIP_LOG_TRANSITIONS:
        raise RuntimeError(
            f"Illegal relationship operation state transition: {current_state} -> {target_state}"
        )
    op_record["operation_state"] = target_state
