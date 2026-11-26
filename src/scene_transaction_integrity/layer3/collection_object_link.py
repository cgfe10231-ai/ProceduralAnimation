"""Object-to-Collection positive authorized link protocol migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-05)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-23T20:42:30+08:00]
# NODE: 10-B / L3-05
# FUNCTION: _authorized_link_object_to_collection
# PURPOSE: Object -> Collection forward authorized link under 3-step PREPARE -> APPLY -> CONFIRM protocol, preserving non-tx compatibility and exception-window verification
# REASON: Migrate Object -> Collection relationship operation along the normal Blender creation chain while retaining original transaction log, state verification, and explicit dependencies
def _authorized_link_object_to_collection(
    collection: bpy.types.Collection,
    obj: bpy.types.Object,
    active_tx: Optional[Any] = None,
    *,
    active_transaction_stack: List[Any],
    relationship_operation_state_cls: Any,
    find_live_collection_by_identity: Callable[
        [Optional[bpy.types.Collection], Optional[int]],
        Optional[bpy.types.Collection],
    ],
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ],
    is_object_linked_to_collection_by_identity: Callable[
        [bpy.types.Collection, Optional[bpy.types.Object], Optional[int]],
        bool,
    ],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection <-> Object link executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None:
        obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
        if not is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
            collection.objects.link(obj)
        return None

    col_ptr = collection.as_pointer() if hasattr(collection, "as_pointer") else None
    obj_ptr = obj.as_pointer() if hasattr(obj, "as_pointer") else None
    obj_name = getattr(obj, "name", "<unknown>")

    # 1. PREPARE: Register relationship mutation before executing any Blender C-API write
    already_linked = is_object_linked_to_collection_by_identity(collection, obj, obj_ptr)
    category = "PRE_EXISTING_ORIGINAL" if already_linked else "TX_ADDED"
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=collection,
        target_reference=obj,
        original_relationship_state={
            "linked": already_linked,
            "category": category,
            "col_ptr": col_ptr,
            "obj_ptr": obj_ptr,
        },
        intended_mutation="COLLECTION_OBJECT_LINK",
    )

    trigger_fault_injection(
        "relationship_link_after_prepare",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )

    # Duplicate link on pre-existing relationship: transition PREPARED -> NO_EFFECT with zero revocation rights
    if already_linked:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.NO_EFFECT,
        )
        return op_record

    # 2. APPLY: Transition PREPARED -> APPLYING and execute C-API link with exception-window inspection
    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLYING,
    )
    try:
        trigger_fault_injection(
            "relationship_link_during_apply_before_c_api",
            {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
        )
        live_col = find_live_collection_by_identity(collection, col_ptr)
        live_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
        if live_col is None or live_obj is None:
            raise RuntimeError("Target object or collection identity invalid during link apply")

        live_col.objects.link(live_obj)

        trigger_fault_injection(
            "relationship_link_during_apply_after_c_api",
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
        elif is_object_linked_to_collection_by_identity(check_col, check_obj, obj_ptr):
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
            active_tx.register_created_collection_link(check_col, check_obj)
        else:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.NO_EFFECT,
            )
        raise

    if not is_object_linked_to_collection_by_identity(collection, obj, obj_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection link apply did not take effect in RNA for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )
    active_tx.register_created_collection_link(collection, obj)

    # 3. CONFIRM: Verify live RNA state and transition APPLIED_VERIFIED -> CONFIRMED
    trigger_fault_injection(
        "relationship_link_before_confirm",
        {"op": op_record, "collection": collection, "obj": obj, "name": obj_name, "tx": active_tx},
    )
    confirm_col = find_live_collection_by_identity(collection, col_ptr)
    confirm_obj = find_live_object_by_identity(obj, obj_ptr) if obj_ptr is not None else None
    if (
        confirm_col is None
        or confirm_obj is None
        or not is_object_linked_to_collection_by_identity(confirm_col, confirm_obj, obj_ptr)
    ):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection link verification failed at CONFIRM stage for '{obj_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.CONFIRMED,
    )
    return op_record
