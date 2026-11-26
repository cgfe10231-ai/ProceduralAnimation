"""Relationship mutation PREPARE registration migrated from `src/rig/arm_ik.py` (Task 10-B Layer 2 L2-10)."""

import uuid
from typing import Any, Dict

from src.scene_transaction_integrity.layer2.relationship_states import (
    _RelationshipOperationState,
)


# [INTRODUCED 2026-11-24T00:12:00+08:00]
# NODE: 10-B / L2-10
# FUNCTION: _prepare_relationship_mutation
# PURPOSE: 在资源关系写入前构造并登记 PREPARED 状态的事务关系操作记录
# REASON: 将原 TransactionContext 的 PREPARE 记录实现迁移至 Layer 2，维持单一记录所有权及原始调用合同
def _prepare_relationship_mutation(
    tx: Any,
    source_reference: Any,
    target_reference: Any,
    original_relationship_state: Dict[str, Any],
    intended_mutation: str,
) -> Dict[str, Any]:
    """PREPARE stage: create and register a 7-state relationship operation log record before mutation."""
    src_ptr = source_reference.as_pointer() if hasattr(source_reference, "as_pointer") else None
    tgt_ptr = target_reference.as_pointer() if hasattr(target_reference, "as_pointer") else None
    src_name = getattr(source_reference, "name", None)
    tgt_name = getattr(target_reference, "name", None)

    op_record: Dict[str, Any] = {
        "operation_id": f"rel_{tx.tx_id}_{len(tx.prepared_relationship_mutations) + 1:04d}_{uuid.uuid4().hex[:6]}",
        "transaction_id": tx.tx_id,
        "source_reference": source_reference,
        "target_reference": target_reference,
        "source_identity": {
            "ref": source_reference,
            "ptr": src_ptr,
            "name": src_name,
            "kind": type(source_reference).__name__,
        },
        "target_identity": {
            "ref": target_reference,
            "ptr": tgt_ptr,
            "name": tgt_name,
            "kind": type(target_reference).__name__,
        },
        "original_relationship_state": dict(original_relationship_state),
        "intended_mutation": intended_mutation,
        "operation_state": _RelationshipOperationState.PREPARED,
    }
    tx.prepared_relationship_mutations.append(op_record)
    return op_record
