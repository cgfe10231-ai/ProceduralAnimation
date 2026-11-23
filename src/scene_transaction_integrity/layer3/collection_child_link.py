"""Collection child relationship ownership check and authorized link protocol migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-03)."""

from typing import Any, Callable, Dict, List, Optional

import bpy


def _require_collection_child_relationship_ownership(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Any,
    *,
    unlink: bool,
    transaction_context_cls: type,
    transaction_state_cls: Any,
    active_transaction_stack: List[Any],
    managed_armature_identities: Dict[str, Any],
    find_live_collection_by_identity: Callable[
        [Optional[bpy.types.Collection], Optional[int]],
        Optional[bpy.types.Collection],
    ],
    relationship_operation_state_cls: Any,
) -> None:
    """Admit writes only to an original-parent edge of a proven TX-created child.

    A live reference, a Collection name, or an unsealed created_collections
    registry entry is not sufficient to establish mutation authority.
    """
    if (not isinstance(active_tx, transaction_context_cls)
            or active_tx.state != transaction_state_cls.ACTIVE
            or active_tx.rollback_only
            or not active_transaction_stack
            or active_transaction_stack[-1] is not active_tx):
        raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: transaction not authorized")
    if (active_tx.session_record is None
            or managed_armature_identities.get(active_tx.session_id) is not active_tx.session_record
            or active_tx.session_record.original_blender_ref is not active_tx.arm
            or not isinstance(active_tx.entry_collection_ptrs, (set, frozenset))):
        raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: entry/session provenance unavailable")
    try:
        parent_ptr = int(parent_collection.as_pointer())
        child_ptr = int(child_collection.as_pointer())
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: Collection identity unreadable") from exc
    if (parent_ptr <= 0 or child_ptr <= 0
            or find_live_collection_by_identity(parent_collection, parent_ptr) is None
            or find_live_collection_by_identity(child_collection, child_ptr) is None
            or child_ptr in active_tx.entry_collection_ptrs):
        raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: child is not a live TX-created Collection")
    records = [r for r in active_tx.created_collections
               if isinstance(r, dict) and r.get("col_ptr") == child_ptr]
    receipt = active_tx._collection_creation_receipts.get(child_ptr)
    if (len(records) != 1 or not isinstance(receipt, tuple) or len(receipt) != 5
            or records[0].get("col_ref") != child_collection
            or records[0].get("initial_parent") != parent_collection
            or records[0].get("initial_parent_ptr") != parent_ptr
            or receipt[0] != child_collection or receipt[1] != parent_collection
            or receipt[2] != active_tx.session_id or receipt[3] != active_tx.tx_id
            or receipt[4] is not active_tx._collection_receipt_seal):
        raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: creation receipt/initial parent mismatch")
    if unlink:
        # Merely discovering a link between owned objects cannot prove that
        # THIS transaction created that edge. Require its confirmed link log.
        proven_link = any(
            isinstance(op, dict)
            and op.get("intended_mutation") == "COLLECTION_CHILD_LINK"
            and op.get("operation_state") in (
                relationship_operation_state_cls.CONFIRMED,
                relationship_operation_state_cls.APPLIED_VERIFIED,
            )
            and op.get("parent_col_ref") == parent_collection
            and op.get("parent_col_ptr") == parent_ptr
            and op.get("child_col_ref") == child_collection
            and op.get("child_col_ptr") == child_ptr
            and op.get("original_relationship_state", {}).get("linked") is False
            for op in active_tx.prepared_relationship_mutations
        )
        if not proven_link:
            raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: link not created by transaction")


def _authorized_link_child_collection(
    parent_collection: bpy.types.Collection,
    child_collection: bpy.types.Collection,
    active_tx: Optional[Any] = None,
    category: str = "TX_ADDED",
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    find_live_collection_by_identity: Callable[
        [Optional[bpy.types.Collection], Optional[int]],
        Optional[bpy.types.Collection],
    ],
    is_collection_descendant_of: Callable[
        [bpy.types.Collection, bpy.types.Collection],
        bool,
    ],
    is_child_collection_linked_by_identity: Callable[..., bool],
    require_collection_child_relationship_ownership: Callable[..., None],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    relationship_operation_state_cls: Any,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Collection child linking executing 3-step PREPARE -> APPLY -> CONFIRM protocol."""
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    if active_tx is None or active_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError("Collection child link requires an active transaction in ACTIVE state")

    if getattr(active_tx, "rollback_only", False):
        raise RuntimeError(f"Cannot link collection child: transaction is rollback_only ({active_tx.rollback_only_reason})")

    p_ptr = parent_collection.as_pointer() if hasattr(parent_collection, "as_pointer") else None
    c_ptr = child_collection.as_pointer() if hasattr(child_collection, "as_pointer") else None

    live_parent = find_live_collection_by_identity(parent_collection, p_ptr)
    live_child = find_live_collection_by_identity(child_collection, c_ptr)
    if live_parent is None or live_child is None:
        raise RuntimeError("Parent or child collection identity invalid during child link")

    if is_collection_descendant_of(live_parent, live_child):
        raise ValueError("Cannot link collection: creates circular dependency in collection hierarchy")

    already_linked = is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr)
    child_name = getattr(child_collection, "name", "<unknown>")
    if not already_linked:
        if category != "TX_ADDED":
            raise RuntimeError("COLLECTION_RELATION_OWNERSHIP_UNPROVEN: unexpected link category")
        require_collection_child_relationship_ownership(
            parent_collection, child_collection, active_tx, unlink=False,
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
        intended_mutation="COLLECTION_CHILD_LINK",
    )
    op_record["parent_col_ref"] = parent_collection
    op_record["parent_col_ptr"] = p_ptr
    op_record["parent_col_name"] = parent_collection.name
    op_record["child_col_ref"] = child_collection
    op_record["child_col_ptr"] = c_ptr
    op_record["child_col_name"] = child_name
    op_record["category"] = category

    trigger_fault_injection(
        "collection_child_link_after_prepare",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    if already_linked:
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
            "collection_child_link_during_apply_before_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )

        parent_collection.children.link(child_collection)

        trigger_fault_injection(
            "collection_child_link_during_apply_after_c_api",
            {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
        )
    except BaseException:
        if is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
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

    if not is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection child link did not take effect in RNA for '{child_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    trigger_fault_injection(
        "collection_child_link_before_confirm",
        {"op": op_record, "parent": parent_collection, "child": child_collection, "tx": active_tx},
    )

    if not is_child_collection_linked_by_identity(parent_collection, child_collection, c_ptr):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Collection child link verification failed at CONFIRM stage for '{child_name}'")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.CONFIRMED,
    )
    return op_record
