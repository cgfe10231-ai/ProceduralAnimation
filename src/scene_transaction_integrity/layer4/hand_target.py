"""Arm IK hand target operation migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-06)."""

import math
from typing import Any, Callable, Dict, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.scene_transaction_integrity.layer4.armature_ops import (
    _apply_arm_ik_prebend_hint_side,
    _resolve_armature,
)
from src.scene_transaction_integrity.layer4.validation import (
    _validate_bool,
    _validate_influence,
    _validate_side,
    _validate_vec3,
)


def set_hand_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Optional[Tuple[float, float, float]] = None,
    pole_world_xyz: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    influence: float = 1.0,
    *,
    preflight_arm_ik_parent_transforms: Callable[..., Tuple[bool, Matrix, Matrix]],
    setup_arm_ik: Callable[..., Dict[str, bpy.types.Object]],
    get_arm_ik_state: Callable[..., dict],
    arm_rig_transaction: Callable[..., Any],
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    trigger_fault_injection: Callable[..., None],
    depsgraph_update: Callable[[], None],
    update_arm_ik_depsgraph: Callable[[], None],
    world_to_local_position: Callable[[Vector, Matrix], Vector],
    world_to_local_rotation_quaternion: Callable[[Quaternion, Matrix], Quaternion],
    apply_target_rotation: Callable[[bpy.types.Object, Quaternion, Matrix], None],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    arm_ik_constraint_names: Dict[str, str],
    hand_rot_constraint_names: Dict[str, str],
    min_arm_reach: float,
    max_arm_reach: float,
    default_pole_outward_offset: float,
    default_pole_backward_offset: float,
) -> dict:
    """Set the left ('L') or right ('R') hand IK target in world coordinates.

    Follows the 10-A, 10-B-1, and 10-B-2 Pre-validation and Zero-Side-Effect Contracts:
    - Phase A: Validates all user inputs strictly before any scene access or mutation.
    - Phase B: Preflights dependency graph (view_layer.update()) and validates effective
      parent transforms of existing and anticipated controllers before auto-initialization.
    - Phase C: Invokes setup_arm_ik() only after Phase B validation succeeds with zero mutation.
    - Phase D: Computes targets, checks finite derived coordinates, and commits transforms/influences.
    - HandIK and ElbowPole transforms are resolved independently using their respective M_eff.
    - Preserves controller active rotation_mode (Euler modes, QUATERNION, AXIS_ANGLE).
    - Rejects non-conformal transforms (shears, non-uniform scaling, reflections, singularities).
    - Preserves default neutral orientation matching CharacterRoot when hand_rotation_deg is None.

    Args:
        armature_obj: Optional CharacterArmature object.
        side: Arm side, 'L' or 'R'.
        world_xyz: Desired wrist position in world coordinates (meters).
        hand_rotation_deg: Desired hand 3D Euler orientation in world coordinates (degrees, 'XYZ').
        pole_world_xyz: Optional explicit elbow pole target in world coordinates.
        clamp_reach: If True, out-of-reach targets are safely projected onto the sphere of radius
            `MAX_ARM_REACH` (or `MIN_ARM_REACH`) centered at the shoulder. If False, target is
            unclamped (bone lengths are still strictly preserved via use_stretch=False).
        influence: Constraint influence to set on ArmIK and HandRotation in [0.0, 1.0]. Defaults to 1.0.

    Returns:
        dict containing state information including requested/applied positions, target error,
        rotation error, reachability flag, and clamping status.
    """
    # Phase A: User input pre-validation (all inputs validated before scene mutation or auto-init)
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    valid_world_xyz = _validate_vec3(world_xyz, param_name="world_xyz", allow_none=False)
    valid_hand_rot = _validate_vec3(hand_rotation_deg, param_name="hand_rotation_deg", allow_none=True)
    valid_pole_world = _validate_vec3(pole_world_xyz, param_name="pole_world_xyz", allow_none=True)
    valid_clamp_reach = _validate_bool(clamp_reach, param_name="clamp_reach")
    valid_influence = _validate_influence(influence, param_name="influence")

    # Phase B: Zero-mutation controller and environment preflight
    arm = _resolve_armature(armature_obj)
    require_existing_arm_ik_controller_ownership(arm, scope='set_hand_ik_target')
    depsgraph_update()
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")

    needs_auto_init, eff_ik_mat, eff_pole_mat = preflight_arm_ik_parent_transforms(
        arm, valid_side, root_obj
    )

    # Phase B2: Zero-mutation derived spatial coordinate and orientation preflight
    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    shoulder_world = arm.matrix_world @ p_up.head

    requested = Vector(valid_world_xyz)
    applied = requested.copy()
    clamped_reach = False

    vec_from_shoulder = applied - shoulder_world
    dist = vec_from_shoulder.length
    is_reachable = (min_arm_reach <= dist <= max_arm_reach)

    # Reach clamping relative to shoulder joint
    if valid_clamp_reach:
        if dist > max_arm_reach:
            clamped_reach = True
            if dist > 1e-6:
                applied = shoulder_world + vec_from_shoulder.normalized() * max_arm_reach
            else:
                applied = shoulder_world + Vector((0.0, 0.0, -1.0)) * max_arm_reach
        elif dist < min_arm_reach:
            clamped_reach = True
            direction = vec_from_shoulder.normalized() if dist > 1e-6 else Vector((0.0, 0.0, -1.0))
            applied = shoulder_world + direction * min_arm_reach

    # Elbow pole target positioning in world space
    sign = -1.0 if valid_side == "L" else 1.0
    if valid_pole_world is not None:
        pole_world = Vector(valid_pole_world)
    else:
        # Default pole placement: behind (-Y) and slightly outward (X)
        mid_pt = 0.5 * (shoulder_world + applied)
        pole_world = Vector((
            mid_pt.x + sign * default_pole_outward_offset,
            min(shoulder_world.y, applied.y) - default_pole_backward_offset,
            mid_pt.z,
        ))

    # Hand 3D orientation target in world coordinates
    if valid_hand_rot is not None:
        target_world_rot_quat = Euler((math.radians(v) for v in valid_hand_rot), "XYZ").to_quaternion()
    else:
        # Neutral level orientation matching CharacterRoot
        if root_obj is not None:
            target_world_rot_quat = root_obj.matrix_world.to_quaternion()
        else:
            target_world_rot_quat = Quaternion()

    ik_local_pos = world_to_local_position(applied, eff_ik_mat)
    pole_local_pos = world_to_local_position(pole_world, eff_pole_mat)
    ik_local_rot_quat = world_to_local_rotation_quaternion(target_world_rot_quat, eff_ik_mat)

    # Phase B3: Verify all derived spatial coordinates and orientations are strictly finite
    for v in (applied, pole_world, ik_local_pos, pole_local_pos):
        for coord in v:
            if not math.isfinite(coord):
                raise ValueError(f"Derived coordinate {coord!r} in target computation is not finite")
    for q_comp in target_world_rot_quat:
        if not math.isfinite(q_comp):
            raise ValueError(f"Derived orientation component {q_comp!r} is not finite")
    for q_comp in ik_local_rot_quat:
        if not math.isfinite(q_comp):
            raise ValueError(f"Derived local orientation component {q_comp!r} is not finite")

    # Phase C & Phase D: Transaction snapshot & atomic commit
    with arm_rig_transaction(arm):
        if needs_auto_init:
            setup_arm_ik(arm, initial_influence=valid_influence)

        ik_obj = bpy.data.objects[arm_ik_target_names[valid_side]]
        pole_obj = bpy.data.objects[arm_pole_target_names[valid_side]]

        _apply_arm_ik_prebend_hint_side(arm, valid_side)

        # Convert applied world targets to controller local spaces preserving rotation_mode
        ik_obj.location = ik_local_pos
        trigger_fault_injection("set_hand_ik_target_after_hand_location", {"ik_obj": ik_obj})

        apply_target_rotation(ik_obj, target_world_rot_quat, eff_ik_mat)
        trigger_fault_injection("set_hand_ik_target_after_hand_rotation", {"ik_obj": ik_obj})

        pole_obj.location = pole_local_pos
        trigger_fault_injection("set_hand_ik_target_after_pole_location", {"pole_obj": pole_obj})

        # Update constraint influence
        ik_con = p_fore.constraints.get(arm_ik_constraint_names[valid_side])
        if ik_con:
            ik_con.influence = valid_influence
        trigger_fault_injection("set_hand_ik_target_between_influences", {"ik_con": ik_con})

        rot_con = p_hand.constraints.get(hand_rot_constraint_names[valid_side])
        if rot_con:
            rot_con.influence = valid_influence
        trigger_fault_injection("set_hand_ik_target_after_rot_influence", {"rot_con": rot_con})

        update_arm_ik_depsgraph()

        trigger_fault_injection("set_hand_ik_target_during_state_read", {"arm": arm})
        state = get_arm_ik_state(arm, valid_side)
        state["requested_world"] = requested
        state["applied_world"] = applied
        state["is_reachable"] = is_reachable
        state["clamped_reach"] = clamped_reach

    return state
