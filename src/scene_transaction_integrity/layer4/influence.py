"""Arm IK influence update operation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-02)."""

from typing import Any, Callable, Dict, Optional

import bpy

from src.scene_transaction_integrity.layer4.armature_ops import _resolve_armature
from src.scene_transaction_integrity.layer4.validation import (
    _validate_influence,
    _validate_side,
)


def set_arm_ik_influence(
    armature_obj: Optional[bpy.types.Object] = None,
    side: str = "BOTH",
    influence: float = 1.0,
    *,
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    arm_rig_transaction: Callable[..., Any],
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
    arm_ik_constraint_names: Dict[str, str],
    hand_rot_constraint_names: Dict[str, str],
) -> None:
    """Set the IK and rotation constraint influence for one or both arms.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: 'L', 'R', or 'BOTH'.
        influence: Influence value in [0.0, 1.0].
    """
    valid_side = _validate_side(side, allow_both=True, param_name="side")
    valid_influence = _validate_influence(influence, param_name="influence")
    arm = _resolve_armature(armature_obj)
    sides = ("L", "R") if valid_side == "BOTH" else (valid_side,)
    require_existing_arm_ik_controller_ownership(arm, scope='set_arm_ik_influence')

    with arm_rig_transaction(arm):
        for s in sides:
            p_fore = arm.pose.bones.get(f"forearm.{s}")
            p_hand = arm.pose.bones.get(f"hand.{s}")
            if p_fore and arm_ik_constraint_names[s] in p_fore.constraints:
                p_fore.constraints[arm_ik_constraint_names[s]].influence = valid_influence
            trigger_fault_injection("set_arm_ik_influence_between_influences", {"side": s})
            if p_hand and hand_rot_constraint_names[s] in p_hand.constraints:
                p_hand.constraints[hand_rot_constraint_names[s]].influence = valid_influence
            if valid_side == "BOTH" and s == "L":
                trigger_fault_injection("set_arm_ik_influence_between_sides", {"side": s})

        depsgraph_update()
