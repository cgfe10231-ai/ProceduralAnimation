"""Single Constraint Target/Subtarget assignment unit under 7-state protocol migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-09)."""

from typing import Any, Callable, Dict, Optional

import bpy

from src.scene_transaction_integrity.layer3.constraint_target_pair_classifier import (
    _classify_constraint_target_pair_effect,
)


# [INTRODUCED 2026-11-23T23:37:00+08:00]
# NODE: 10-B / L3-09
# FUNCTION: _apply_single_constraint_target_unit
# PURPOSE: Validate Constraint Target identity, capture original target/subtarget state, record PREPARE/APPLY/VERIFY/CONFIRM transitions, execute sequential RNA writes with partial-write L3-08 classification, and fire 5 fault hooks
# REASON: Migrate single-unit Constraint Target relationship mutation from src/rig/arm_ik.py into Layer 3 while keeping original 8-arg signature, non-tx compatibility, and L3-08 classifier reuse
def _apply_single_constraint_target_unit(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    field: str,
    subtarget_field: str,
    target_obj: Optional[bpy.types.Object],
    target_subtarget: str,
    intended_mutation: str,
    active_tx: Optional[Any],
    *,
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ],
    relationship_operation_state_cls: Any,
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
) -> Optional[Dict[str, Any]]:
    """Execute a single constraint target or pole target assignment unit under 7-state protocol."""
    if not hasattr(con, field):
        raise AttributeError(f"Constraint '{con.name}' ({con.type}) does not have property '{field}'")

    # Identity validation of target_obj
    dest_ptr: Optional[int] = None
    if target_obj is not None:
        if not isinstance(target_obj, bpy.types.Object):
            raise TypeError(f"Target must be a Blender Object, got {type(target_obj)}")
        try:
            dest_ptr = target_obj.as_pointer()
        except ReferenceError as re:
            raise RuntimeError(f"Target object reference is dead: {re}") from re
        live_obj = find_live_object_by_identity(target_obj, dest_ptr)
        if live_obj is None or live_obj != target_obj:
            raise RuntimeError(f"Target object identity verification failed for '{target_obj.name}'")

    orig_target = getattr(con, field, None)
    orig_subtarget = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
    orig_ptr: Optional[int] = None
    if orig_target is not None:
        try:
            orig_ptr = orig_target.as_pointer()
        except ReferenceError:
            orig_ptr = None

    # If active_tx is None (backward-compatible restoration without transaction):
    if active_tx is None:
        setattr(con, field, target_obj)
        if hasattr(con, subtarget_field):
            setattr(con, subtarget_field, target_subtarget)
        return None

    # Check if unchanged
    orig_matches_dest = False
    if target_obj is None and orig_target is None and orig_subtarget == target_subtarget:
        orig_matches_dest = True
    elif target_obj is not None and orig_target is not None:
        if orig_target == target_obj and orig_ptr == dest_ptr and orig_subtarget == target_subtarget:
            orig_matches_dest = True

    category = "PRE_EXISTING" if orig_target is not None else "UNASSIGNED"

    # 1. PREPARE: register mutation log record
    op_record = active_tx.prepare_relationship_mutation(
        source_reference=con,
        target_reference=target_obj,
        original_relationship_state={
            "field": field,
            "subtarget_field": subtarget_field,
            "category": category,
            "pbone_ref": pbone,
            "pbone_ptr": pbone.as_pointer(),
            "bone_name": pbone.name,
            "con_ref": con,
            "con_ptr": con.as_pointer(),
            "con_name": con.name,
            "orig_target_ref": orig_target,
            "orig_target_ptr": orig_ptr,
            "orig_subtarget": orig_subtarget,
            "dest_target_ref": target_obj,
            "dest_target_ptr": dest_ptr,
            "dest_subtarget": target_subtarget,
        },
        intended_mutation=intended_mutation,
    )
    # Populate top-level fields for convenience
    op_record["pbone_ref"] = pbone
    op_record["pbone_ptr"] = pbone.as_pointer()
    op_record["bone_name"] = pbone.name
    op_record["con_ref"] = con
    op_record["con_ptr"] = con.as_pointer()
    op_record["con_name"] = con.name
    op_record["field"] = field
    op_record["subtarget_field"] = subtarget_field
    op_record["orig_target_ref"] = orig_target
    op_record["orig_target_ptr"] = orig_ptr
    op_record["orig_subtarget"] = orig_subtarget
    op_record["dest_target_ref"] = target_obj
    op_record["dest_target_ptr"] = dest_ptr
    op_record["dest_subtarget"] = target_subtarget
    op_record["category"] = category

    trigger_fault_injection(
        "relationship_constraint_target_after_prepare",
        {"op": op_record, "pbone": pbone, "con": con, "target": target_obj, "tx": active_tx},
    )

    # If unchanged, transition to NO_EFFECT without calling Blender C-API write
    if orig_matches_dest:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.NO_EFFECT,
        )
        return op_record

    # 2. APPLY: transition PREPARED -> APPLYING
    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLYING,
    )
    try:
        trigger_fault_injection(
            "during_constraint_target_apply_before_write",
            {"op": op_record, "pbone": pbone, "con": con, "target": target_obj, "tx": active_tx},
        )

        setattr(con, field, target_obj)
        # Distinct C-API setters: expose the genuinely partial write window.
        trigger_fault_injection(
            "during_constraint_target_apply_between_fields",
            {"op": op_record, "pbone": pbone, "con": con, "target": target_obj, "tx": active_tx},
        )
        if hasattr(con, subtarget_field):
            setattr(con, subtarget_field, target_subtarget)

        trigger_fault_injection(
            "during_constraint_target_apply_after_write",
            {"op": op_record, "pbone": pbone, "con": con, "target": target_obj, "tx": active_tx},
        )
    except BaseException:
        # The two RNA setters are separate. After the first succeeds, the
        # second can fail: TARGET=destination + SUBTARGET=original is NOT
        # NO_EFFECT. Keep it undoable when both values have known provenance.
        try:
            curr_target = getattr(con, field, None)
            curr_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
            classification = _classify_constraint_target_pair_effect(
                curr_target, curr_sub,
                orig_target, orig_ptr, orig_subtarget,
                target_obj, dest_ptr, target_subtarget,
                relationship_operation_state_cls=relationship_operation_state_cls,
                find_live_object_by_identity=find_live_object_by_identity,
            )
        except Exception:
            classification = relationship_operation_state_cls.RECOVERY_UNCERTAIN
        active_tx.update_relationship_mutation_state(op_record, classification)
        raise

    # Verify RNA write
    curr_target = getattr(con, field, None)
    curr_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
    curr_target_ptr = curr_target.as_pointer() if (curr_target and hasattr(curr_target, "as_pointer")) else None
    target_ok = (curr_target == target_obj if target_obj is not None else curr_target is None)
    ptr_ok = (curr_target_ptr == dest_ptr)
    sub_ok = (curr_sub == target_subtarget)

    if not (target_ok and ptr_ok and sub_ok):
        # RNA returned without raising, but at least one property differs.
        # A recognizable partial write is still undoable; it is never NO_EFFECT.
        classification = _classify_constraint_target_pair_effect(
            curr_target, curr_sub,
            orig_target, orig_ptr, orig_subtarget,
            target_obj, dest_ptr, target_subtarget,
            relationship_operation_state_cls=relationship_operation_state_cls,
            find_live_object_by_identity=find_live_object_by_identity,
        )
        active_tx.update_relationship_mutation_state(op_record, classification)
        raise RuntimeError(f"Constraint {field} assignment did not take effect in RNA")

    active_tx.update_relationship_mutation_state(
        op_record,
        relationship_operation_state_cls.APPLIED_VERIFIED,
    )

    # 3. CONFIRM
    trigger_fault_injection(
        "constraint_target_before_confirm",
        {"op": op_record, "pbone": pbone, "con": con, "target": target_obj, "tx": active_tx},
    )

    confirm_target = getattr(con, field, None)
    confirm_sub = getattr(con, subtarget_field, "") if hasattr(con, subtarget_field) else ""
    confirm_ptr = confirm_target.as_pointer() if (confirm_target is not None and hasattr(confirm_target, "as_pointer")) else None
    c_tgt_ok = (confirm_target == target_obj if target_obj is not None else confirm_target is None)
    c_ptr_ok = (confirm_ptr == dest_ptr)
    if c_tgt_ok and c_ptr_ok and confirm_sub == target_subtarget:
        active_tx.update_relationship_mutation_state(
            op_record,
            relationship_operation_state_cls.CONFIRMED,
        )
    else:
        classification = _classify_constraint_target_pair_effect(
            confirm_target, confirm_sub,
            orig_target, orig_ptr, orig_subtarget,
            target_obj, dest_ptr, target_subtarget,
            relationship_operation_state_cls=relationship_operation_state_cls,
            find_live_object_by_identity=find_live_object_by_identity,
        )
        if classification == relationship_operation_state_cls.RECOVERY_UNCERTAIN:
            active_tx.update_relationship_mutation_state(
                op_record,
                relationship_operation_state_cls.RECOVERY_UNCERTAIN,
            )
        # An already APPLIED_VERIFIED operation stays there for reversal if
        # values are still within this transaction's original/destination pair.
        raise RuntimeError(f"Constraint {field}/{subtarget_field} verification failed at CONFIRM stage")

    return op_record
