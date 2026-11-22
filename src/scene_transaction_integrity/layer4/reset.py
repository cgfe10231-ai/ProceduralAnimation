"""Arm IK bilateral reset operation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-04)."""

from typing import Any, Callable, Dict, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.scene_transaction_integrity.layer4.armature_ops import (
    _apply_arm_ik_prebend_hint_side,
    _resolve_armature,
)


def reset_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    *,
    arm_rig_transaction: Callable[..., Any],
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
    compute_effective_parent_matrix: Callable[[bpy.types.Object], Matrix],
    validate_effective_parent_transform: Callable[[Matrix, str], None],
    world_to_local_position: Callable[[Vector, Matrix], Vector],
    apply_target_rotation: Callable[[bpy.types.Object, Quaternion, Matrix], None],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    arm_ik_constraint_names: Dict[str, str],
    hand_rot_constraint_names: Dict[str, str],
    shoulder_x_offset: float,
    wrist_rest_z: float,
    elbow_rest_z: float,
    default_pole_outward_offset: float,
    default_pole_backward_offset: float,
) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode).

    Follows the Gate A-3 Transaction Atomicity Contract:
    - Phase 1: Resolves Armature and CharacterRoot, updates view layer.
    - Phase 2: Preflights effective parent transforms for all existing controllers on both sides (L and R)
      using compute_effective_parent_matrix() and validate_effective_parent_transform().
      If any preflight check fails, aborts immediately with ZERO scene writes on either side.
    - Phase 3: Enters unified _arm_rig_transaction(arm) context.
    - Phase 4: Executes bilateral reset with observable fault injection boundaries.
    - Phase 5: Synchronizes dependency graph and commits. Any write exception triggers atomic rollback.
    """
    arm = _resolve_armature(armature_obj)
    require_existing_arm_ik_controller_ownership(arm, scope='reset_arm_ik')
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    depsgraph_update()

    # Preflight parent transform domains for all existing controllers on both sides BEFORE any writes
    eff_mats: Dict[str, Tuple[Optional[Matrix], Optional[Matrix]]] = {}
    for s in ("L", "R"):
        ik_c = bpy.data.objects.get(arm_ik_target_names[s])
        pole_c = bpy.data.objects.get(arm_pole_target_names[s])
        eff_ik = None
        eff_pole = None
        if ik_c is not None:
            eff_ik = compute_effective_parent_matrix(ik_c)
            validate_effective_parent_transform(eff_ik, ik_c.name)
        if pole_c is not None:
            eff_pole = compute_effective_parent_matrix(pole_c)
            validate_effective_parent_transform(eff_pole, pole_c.name)
        eff_mats[s] = (eff_ik, eff_pole)

    # All preflight checks passed; execute reset under unified transaction protection
    with arm_rig_transaction(arm):
        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = bpy.data.objects.get(arm_ik_target_names[side])
            pole_obj = bpy.data.objects.get(arm_pole_target_names[side])
            eff_ik_mat, eff_pole_mat = eff_mats[side]

            # Compute neutral targets in root/world coordinates
            ik_neutral_local = Vector((sign * shoulder_x_offset, 0.0, wrist_rest_z))
            pole_neutral_local = Vector((
                sign * (shoulder_x_offset + default_pole_outward_offset),
                -default_pole_backward_offset,
                elbow_rest_z,
            ))

            if root_obj is not None:
                ik_neutral_world = root_obj.matrix_world @ ik_neutral_local
                pole_neutral_world = root_obj.matrix_world @ pole_neutral_local
                neutral_world_rot_quat = root_obj.matrix_world.to_quaternion()
            else:
                ik_neutral_world = ik_neutral_local
                pole_neutral_world = pole_neutral_local
                neutral_world_rot_quat = Quaternion()

            if ik_obj is not None and eff_ik_mat is not None:
                ik_obj.location = world_to_local_position(ik_neutral_world, eff_ik_mat)
                apply_target_rotation(ik_obj, neutral_world_rot_quat, eff_ik_mat)
                trigger_fault_injection(f"reset_arm_ik_after_hand_controller_{side.lower()}", {"side": side, "ik_obj": ik_obj})

            if pole_obj is not None and eff_pole_mat is not None:
                pole_obj.location = world_to_local_position(pole_neutral_world, eff_pole_mat)
                apply_target_rotation(pole_obj, Quaternion(), eff_pole_mat)
                trigger_fault_injection(f"reset_arm_ik_after_pole_{side.lower()}", {"side": side, "pole_obj": pole_obj})

            p_up = arm.pose.bones.get(f"upper_arm.{side}")
            p_fore = arm.pose.bones.get(f"forearm.{side}")
            p_hand = arm.pose.bones.get(f"hand.{side}")
            if p_up:
                p_up.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
            if p_fore:
                p_fore.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
                if arm_ik_constraint_names[side] in p_fore.constraints:
                    p_fore.constraints[arm_ik_constraint_names[side]].influence = 0.0
            if p_hand:
                p_hand.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
                if hand_rot_constraint_names[side] in p_hand.constraints:
                    p_hand.constraints[hand_rot_constraint_names[side]].influence = 0.0
            trigger_fault_injection(f"reset_arm_ik_after_influence_{side.lower()}", {"side": side})

            _apply_arm_ik_prebend_hint_side(arm, side)

        trigger_fault_injection("reset_arm_ik_during_depsgraph_update", {"arm": arm})
        depsgraph_update()
