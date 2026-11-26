"""Collection-to-Child-Collection forward authorized unlink protocol migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-11)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-25T16:20:09+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _authorized_unlink_child_collection
# PURPOSE: 在 ACTIVE 事务与受权所有权核验前提下按 PREPARE -> APPLY -> CONFIRM 三步协议执行 Collection <-> Child Collection 正向解绑
# REASON: 将正向受权 Collection <-> Child Collection 解绑实现从 arm_ik.py 物理迁入 Layer 3，全部外部依赖经显式参数传入
def _authorized_unlink_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    relationship_operation_state_cls: Any,
    find_live_collection_by_identity: Callable[..., Optional[bpy.types.Collection]],
    is_child_collection_linked_by_identity: Callable[..., bool],
    require_collection_child_relationship_ownership: Callable[..., None],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child unlinking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None or active_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError("Collection child unlink requires an active transaction in ACTIVE state")

    p_ptr = parent_collection.as_pointer() if hasattr(parent_collection, "as_pointer") else None
    c_ptr = child_collection.as_pointer() if hasattr(child_collection, "as_pointer") else None

    live_parent = find_live_collection_by_identity(parent_collection, p_ptr)
    live_child = find_live_collection_by_identity(child_collection, c_ptr)
    if live_parent is None or live_child is None:
        raise RuntimeError("Parent or child collection identity invalid during child unlink")

    already_linked = is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr)
    child_name = getattr(child_collection, "name", "<unknown>")
    if already_linked:
        require_collection_child_relationship_ownership(
            parent_collection, child_collection, active_tx, unlink=True,
        )

    # 1. PREPARE
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=parent_collection,
        target_reference=child_collection,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "parent_col_ref": parent_collection,
            "parent_col_ptr": p_ptr,
            "parent_col_name": parent_collection.name,
            "child_col_ref": child_collection,
            "child_col_ptr": c_ptr,
            "child_col_name": child_name,
        },
        intended_mutation="COLLECTION_CHILD_UNLINK",
    )
    op_record["parent_col_ref"] = parent_collection
    op_record["parent_col_ptr"] = p_ptr
    op_record["parent_col_name"] = parent_collection.name
    op_record["child_col_ref"] = child_collection
    op_record["child_col_ptr"] = c_ptr
    op_record["child_col_name"] = child_name
    op_record["category"] = category

    trigger_fault_injection(
        "collection_child_unlink_after_prepare",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    if not already_linked:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.NO_EFFECT,
        )
        return op_record

    # 2. APPLY
    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLYING,
    )

    try:
        trigger_fault_injection(
            "collection_child_unlink_during_apply_before_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )

        parent_collection.children.unlink(child_collection)

        trigger_fault_injection(
            "collection_child_unlink_during_apply_after_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )
    except BaseException:
        if not is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.NO_EFFECT,
            )
        raise

    if is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection child unlink did not take effect in RNA for '{child_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    trigger_fault_injection(
        "collection_child_unlink_before_confirm",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.CONFIRMED,
    )
    return op_record
