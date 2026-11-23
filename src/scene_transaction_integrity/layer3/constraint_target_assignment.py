"""Unified Constraint Target and Pole Target authorized assignment entry migrated from `src/rig/arm_ik.py` (Task 10-B Layer 3 L3-10)."""

from typing import Any, Callable, Dict, List, Optional

import bpy

from src.scene_transaction_integrity.layer3.constraint_target_unit import (
    _apply_single_constraint_target_unit,
)
from src.scene_transaction_integrity.layer3.resource_contracts import (
    _TARGET_UNSET,
)


# [INTRODUCED 2026-11-23T23:58:00+08:00]
# NODE: 10-B / L3-10
# FUNCTION: _authorized_assign_constraint_targets
# PURPOSE: 将普通 Target 和 Pole Target 统一绑定入口迁移至 Layer 3
# REASON: 完成正常 Constraint Target 资源关系绑定链的物理拆分
def _authorized_assign_constraint_targets(
    pbone: bpy.types.PoseBone,
    con: bpy.types.Constraint,
    target: Any = _TARGET_UNSET,
    subtarget: Any = _TARGET_UNSET,
    pole_target: Any = _TARGET_UNSET,
    pole_subtarget: Any = _TARGET_UNSET,
    active_tx: Optional[Any] = None,
    *,
    active_transaction_stack: List[Any],
    find_live_object_by_identity: Callable[
        [Optional[bpy.types.Object], Optional[int]],
        Optional[bpy.types.Object],
    ],
    relationship_operation_state_cls: Any,
    trigger_fault_injection: Callable[[str, Dict[str, Any]], None],
) -> None:
    """Layer 3 authorized constraint target and pole target assignment.

    Applies the 7-state relation machine (PREPARE -> APPLY -> VERIFY -> CONFIRM)
    for each target/subtarget relationship mutation unit.
    """
    if active_tx is None and active_transaction_stack:
        active_tx = active_transaction_stack[-1]

    # Pose bone and constraint identity checks
    try:
        pbone_ptr = pbone.as_pointer()
    except ReferenceError as re:
        raise RuntimeError(f"PoseBone reference is dead: {re}") from re

    try:
        con_ptr = con.as_pointer()
    except ReferenceError as re:
        raise RuntimeError(f"Constraint reference is dead: {re}") from re

    if con not in pbone.constraints.values():
        raise RuntimeError(f"Constraint '{con.name}' does not belong to bone '{pbone.name}'")

    # Process Target unit if specified
    if target is not _TARGET_UNSET:
        _apply_single_constraint_target_unit(
            pbone=pbone,
            con=con,
            field="target",
            subtarget_field="subtarget",
            target_obj=target,
            target_subtarget=subtarget if subtarget is not _TARGET_UNSET else getattr(con, "subtarget", ""),
            intended_mutation="CONSTRAINT_TARGET_ASSIGN",
            active_tx=active_tx,
            find_live_object_by_identity=find_live_object_by_identity,
            relationship_operation_state_cls=relationship_operation_state_cls,
            trigger_fault_injection=trigger_fault_injection,
        )

    # Process Pole Target unit if specified
    if pole_target is not _TARGET_UNSET:
        _apply_single_constraint_target_unit(
            pbone=pbone,
            con=con,
            field="pole_target",
            subtarget_field="pole_subtarget",
            target_obj=pole_target,
            target_subtarget=pole_subtarget if pole_subtarget is not _TARGET_UNSET else getattr(con, "pole_subtarget", ""),
            intended_mutation="CONSTRAINT_POLE_TARGET_ASSIGN",
            active_tx=active_tx,
            find_live_object_by_identity=find_live_object_by_identity,
            relationship_operation_state_cls=relationship_operation_state_cls,
            trigger_fault_injection=trigger_fault_injection,
        )
