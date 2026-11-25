"""Object-to-Collection forward authorized unlink protocol migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-11)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-25T16:20:09+08:00]
# NODE: 10-B / L3-11
# FUNCTION: _authorized_unlink_object_from_collection
# PURPOSE: 按 PREPARE -> APPLY -> CONFIRM 三步协议执行受权 Collection <-> Object 正向解绑，保留无事务兼容路径与异常窗口状态核验
# REASON: 将正向受权 Collection <-> Object 解绑实现从 arm_ik.py 物理迁入 Layer 3，全部外部依赖经显式参数传入
def _authorized_unlink_object_from_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
    category: str = "TX_UNLINKED_ORIGINAL",
    *,
    active_transaction_stack: List[Any],
    relationship_operation_state_cls: Any,
    is_object_linked_to_collection_by_identity: Callable[..., bool],
    find_live_collection_by_identity: Callable[..., Optional[bpy.types.Collection]],
    find_live_object_by_identity: Callable[..., Optional[bpy.types.Object]],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object unlink executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None:
        obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
        if is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
            collection.objects.unlink(obj)
        return None

    col_ptr = collection.as_pointer() if hasattr(collection, "as_pointer") else None
    obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
    obj_name = getattr(obj, "name", "<unknown>")

    # 1. PREPARE
    already_linked = is_object_linked_to_collection_by_identity(collection, obj, obj_ptr)
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=collection,
        target_reference=obj,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "col_ptr": col_ptr,
            "obj_ptr": obj_ptr,
        },
        intended_mutation="COLLECTION_OBJECT_UNLINK",
    )

    trigger_fault_injection(
        "relationship_unlink_after_prepare",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
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
            "relationship_unlink_during_apply_before_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
        live_col = find_live_collection_by_identity(collection, col_ptr)
        live_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_col is None or live_obj is None:
            raise RuntimeError("Target object or collection identity invalid during unlink apply")

        live_col.objects.unlink(live_obj)

        trigger_fault_injection(
            "relationship_unlink_during_apply_after_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
    except BaseException:
        check_col = find_live_collection_by_identity(collection, col_ptr)
        check_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if check_col is None or check_obj is None:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
        elif not is_object_linked_to_collection_by_identity(check_col, check_obj, obj_ptr):
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

    if is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection unlink apply did not take effect in RNA for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    trigger_fault_injection(
        "relationship_unlink_before_confirm",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )
    confirm_col = find_live_collection_by_identity(collection, col_ptr)
    confirm_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
    if (
        confirm_col is None
        or confirm_obj is None
        or is_object_linked_to_collection_by_identity(confirm_col, confirm_obj, obj_ptr)
    ):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection unlink verification failed at CONFIRM stage for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.CONFIRMED,
    )
    return op_record
