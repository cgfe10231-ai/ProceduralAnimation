"""Object Parent and Matrix Parent Inverse authorized assignment migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-06)."""

import math
from typing import Any, Callable, Dict, List, Optional

import bpy


# [INTRODUCED 2026-11-23T21:19:00+08:00]
# NODE: 10-B / L3-06
# FUNCTION: _authorized_assign_object_parent
# PURPOSE: Verify transaction authority, parent/armature constraints, matrix finiteness and effective parent transform, then mutate Object Parent and Matrix Parent Inverse under 7-state relationship logging and exception-window checks
# REASON: Migrate Object Parent relationship mutation along the normal Blender Controller creation chain from src/rig/arm_ik.py into Layer 3 while preserving original math, write order, and transaction semantics
def _authorized_assign_object_parent(
    obj: bpy.types.Object,
    parent: Optional[bpy.types.Object],
    matrix_parent_inverse: Optional[Any] = None,
    active_tx: Optional[Any] = None,
    *,
    active_transaction_stack: List[Any],
    transaction_state_cls: Any,
    relationship_operation_state_cls: Any,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ],
    verify_controller_object_transaction_authority: Callable[..., Optional[str]],
    matrix_equals: Callable[..., bool],
    validate_effective_parent_transform: Callable[[Any, str], None],
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
    matrix_cls: Any,
) -> Optional[Dict[str, Any]]:
    """Layer 3 authorized Object Parent and Matrix Parent Inverse assignment under 7-state protocol."""
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    # Pre-write verification (Section 3.3)
    # 1. Active transaction exists and is ACTIVE
    if active_tx is None or active_tx.state != transaction_state_cls.ACTIVE:
        raise RuntimeError("Object parent assignment requires an active transaction in ACTIVE state")

    # 10. Rollback-only check
    if getattr(active_tx, "rollback_only", False):
        raise RuntimeError(f"Cannot assign object parent: transaction is rollback_only ({active_tx.rollback_only_reason})")

    # 2 & 3. Controller live reference valid and pointer matches
    try:
        obj_ptr = obj.as_pointer()
    except (ReferenceError, Exception) as re:
        raise RuntimeError(f"Target controller object reference is invalid: {re}") from re

    live_obj = find_live_object_by_identity(obj, obj_ptr)
    if live_obj is None or live_obj != obj:
        raise RuntimeError(f"Target controller identity verification failed for '{obj.name}'")

    # 4 & 9. Ownership needs exact transaction provenance, not a controller name.
    # Fail before preparing any relationship log or mutating parent fields.
    if not active_transaction_stack or active_transaction_stack[-1] is not active_tx:
        raise RuntimeError("Object parent assignment rejected: transaction is not the active stack owner")
    controller_authority = verify_controller_object_transaction_authority(obj, active_tx)
    if controller_authority is None:
        raise RuntimeError(
            f"Object '{obj.name}' is not owned or managed by the active transaction (TEST-224)"
        )

    # 5 & 6. New parent verification
    dest_parent_ptr: Optional[int] = None
    if parent is not None:
        if not isinstance(parent, bpy.types.Object):
            raise TypeError(f"Parent must be a Blender Object, got {type(parent)}")
        try:
            dest_parent_ptr = parent.as_pointer()
        except ReferenceError as re:
            raise RuntimeError(f"Parent object reference is dead: {re}") from re
        live_parent = find_live_object_by_identity(parent, dest_parent_ptr)
        if live_parent is None or live_parent != parent:
            raise RuntimeError(f"Parent object identity verification failed for '{parent.name}'")

        # 6. Cross-armature check (Section 3.3, item 6)
        if active_tx.arm is not None and parent != active_tx.arm:
            if parent.type == "ARMATURE" or (getattr(parent, "parent", None) is not None and getattr(parent, "parent") != active_tx.arm and getattr(parent, "parent").type == "ARMATURE"):
                raise RuntimeError(f"Cross-armature parent assignment rejected: parent '{parent.name}' != active armature '{active_tx.arm.name}'")

        # 7. No self-parenting and no cycle
        if parent == obj:
            raise ValueError("Self-parenting not permitted")
        curr = getattr(parent, "parent", None)
        while curr is not None:
            if curr == obj:
                raise ValueError("Cyclic parent hierarchy detected")
            curr = getattr(curr, "parent", None)

    # Matrix parent inverse resolution
    target_inv = matrix_parent_inverse.copy() if matrix_parent_inverse is not None else matrix_cls.Identity(4)

    # Check finite
    for r in range(4):
        for c in range(4):
            if not math.isfinite(target_inv[r][c]):
                raise ValueError(f"Non-finite matrix_parent_inverse element at ({r}, {c})")

    # 8. Conformal matrix check
    if parent is not None:
        eff_matrix = parent.matrix_world @ target_inv
        validate_effective_parent_transform(eff_matrix, obj.name)

    # Capture original state
    orig_parent = getattr(obj, "parent", None)
    orig_parent_ptr: Optional[int] = None
    if orig_parent is not None:
        try:
            orig_parent_ptr = orig_parent.as_pointer()
        except ReferenceError:
            orig_parent_ptr = None

    orig_inv = getattr(obj, "matrix_parent_inverse", matrix_cls.Identity(4)).copy()
    category = "PRE_EXISTING_ORIGINAL" if orig_parent is not None else "TX_ADDED"

    # 1. PREPARE stage
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=parent,
        target_reference=obj,
        original_relationship_state={
            "controller_ref": obj,
            "controller_ptr": obj_ptr,
            "controller_name": obj.name,
            "orig_parent_ref": orig_parent,
            "orig_parent_ptr": orig_parent_ptr,
            "orig_parent_name": orig_parent.name if orig_parent is not None else None,
            "orig_matrix_parent_inverse": orig_inv,
            "dest_parent_ref": parent,
            "dest_parent_ptr": dest_parent_ptr,
            "dest_parent_name": parent.name if parent is not None else None,
            "dest_matrix_parent_inverse": target_inv,
            "category": category,
        },
        intended_mutation="OBJECT_PARENT_ASSIGN",
    )
    op_record["controller_ref"] = obj
    op_record["controller_ptr"] = obj_ptr
    op_record["controller_name"] = obj.name
    op_record["orig_parent_ref"] = orig_parent
    op_record["orig_parent_ptr"] = orig_parent_ptr
    op_record["orig_parent_name"] = orig_parent.name if orig_parent is not None else None
    op_record["orig_matrix_parent_inverse"] = orig_inv
    op_record["dest_parent_ref"] = parent
    op_record["dest_parent_ptr"] = dest_parent_ptr
    op_record["dest_parent_name"] = parent.name if parent is not None else None
    op_record["dest_matrix_parent_inverse"] = target_inv
    op_record["category"] = category

    trigger_fault_injection(
        "object_parent_after_prepare",
        {"op": op_record, "obj": obj, "parent": parent, "inv": target_inv, "tx": active_tx},
    )

    # Check for NO_EFFECT
    parent_is_same = False
    if orig_parent is None and parent is None:
        parent_is_same = True
    elif orig_parent is not None and parent is not None:
        try:
            if orig_parent == parent and orig_parent_ptr == dest_parent_ptr:
                parent_is_same = True
        except ReferenceError:
            parent_is_same = False

    inv_is_same = matrix_equals(orig_inv, target_inv, tol=1e-5)

    if parent_is_same and inv_is_same:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.NO_EFFECT,
        )
        return op_record

    # 2. APPLY stage
    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLYING,
    )

    try:
        trigger_fault_injection(
            "object_parent_before_write",
            {"op": op_record, "obj": obj, "parent": parent, "inv": target_inv, "tx": active_tx},
        )

        obj.parent = parent

        trigger_fault_injection(
            "object_parent_after_parent_before_inverse",
            {"op": op_record, "obj": obj, "parent": parent, "inv": target_inv, "tx": active_tx},
        )

        obj.matrix_parent_inverse = target_inv.copy()

        trigger_fault_injection(
            "object_parent_after_write",
            {"op": op_record, "obj": obj, "parent": parent, "inv": target_inv, "tx": active_tx},
        )
    except BaseException:
        curr_p = getattr(obj, "parent", None)
        curr_inv = getattr(obj, "matrix_parent_inverse", matrix_cls.Identity(4))
        p_changed = False
        if orig_parent is None and curr_p is not None:
            p_changed = True
        elif orig_parent is not None and (curr_p is None or curr_p != orig_parent):
            p_changed = True
        inv_changed = not matrix_equals(orig_inv, curr_inv, tol=1e-5)

        if p_changed or inv_changed:
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

    # Verify write took effect in RNA
    v_parent = getattr(obj, "parent", None)
    v_inv = getattr(obj, "matrix_parent_inverse", matrix_cls.Identity(4))
    p_ok = (v_parent == parent)
    inv_ok = matrix_equals(v_inv, target_inv, tol=1e-5)

    if not (p_ok and inv_ok):
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.RECOVERY_UNCERTAIN,
        )
        raise RuntimeError(f"Object parent/inverse verification failed for '{obj.name}' (p_ok={p_ok}, inv_ok={inv_ok})")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )

    # 3. CONFIRM stage
    trigger_fault_injection(
        "object_parent_before_confirm",
        {"op": op_record, "obj": obj, "parent": parent, "inv": target_inv, "tx": active_tx},
    )

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.CONFIRMED,
    )
    return op_record
