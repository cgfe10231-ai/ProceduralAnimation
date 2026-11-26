"""Arm IK state inspection query migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4 L4-01)."""

import math
from typing import Callable, Dict, Optional

import bpy

from src.rig.arm_ik import ARM_IK_CONSTRAINT_NAMES
from src.scene_transaction_integrity.layer4.armature_ops import _resolve_armature
from src.scene_transaction_integrity.layer4.validation import _validate_side


def get_arm_ik_state(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    *,
    require_existing_arm_ik_controller_ownership: Callable[..., None],
    depsgraph_update: Callable[[], None],
    arm_ik_target_names: Dict[str, str],
    arm_pole_target_names: Dict[str, str],
    hand_rot_constraint_names: Dict[str, str],
    arm_ik_constraint_names: Dict[str, str] = ARM_IK_CONSTRAINT_NAMES,
) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    arm = _resolve_armature(armature_obj)
    require_existing_arm_ik_controller_ownership(arm, scope='get_arm_ik_state')
    depsgraph_update()

    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    ik_obj = bpy.data.objects.get(arm_ik_target_names[valid_side])
    pole_obj = bpy.data.objects.get(arm_pole_target_names[valid_side])

    shoulder_world = arm.matrix_world @ p_up.head
    elbow_world = arm.matrix_world @ p_fore.head
    wrist_world = arm.matrix_world @ p_fore.tail
    hand_tip_world = arm.matrix_world @ p_hand.tail

    target_world = ik_obj.matrix_world.translation.copy() if ik_obj else wrist_world.copy()
    pole_world = pole_obj.matrix_world.translation.copy() if pole_obj else elbow_world.copy()

    target_error = (wrist_world - target_world).length
    upper_arm_length = (elbow_world - shoulder_world).length
    forearm_length = (wrist_world - elbow_world).length
    hand_length = (hand_tip_world - wrist_world).length
    total_arm_length = upper_arm_length + forearm_length

    # Compute interior elbow angle
    v_up = (shoulder_world - elbow_world).normalized()
    v_fore = (wrist_world - elbow_world).normalized()
    cos_angle = max(-1.0, min(1.0, v_up.dot(v_fore)))
    elbow_interior_deg = math.degrees(math.acos(cos_angle))
    elbow_flexion_deg = 180.0 - elbow_interior_deg

    # Hand orientation inspection
    hand_w_mat = (arm.matrix_world @ p_hand.matrix).to_3x3()
    hand_world_euler = tuple(round(math.degrees(a), 4) for a in hand_w_mat.to_euler("XYZ"))

    if ik_obj:
        target_quat = ik_obj.matrix_world.to_quaternion()
        target_world_euler = tuple(round(math.degrees(a), 4) for a in target_quat.to_euler("XYZ"))
        rot_diff = target_quat.rotation_difference(hand_w_mat.to_quaternion()).angle
        rotation_error_deg = round(math.degrees(rot_diff), 4)
    else:
        target_world_euler = hand_world_euler
        rotation_error_deg = 0.0

    ik_con = p_fore.constraints.get(arm_ik_constraint_names[valid_side])
    rot_con = p_hand.constraints.get(hand_rot_constraint_names[valid_side])
    ik_influence = ik_con.influence if ik_con else 0.0
    rot_influence = rot_con.influence if rot_con else 0.0

    return {
        "side": valid_side,
        "shoulder_world": shoulder_world,
        "elbow_world": elbow_world,
        "wrist_world": wrist_world,
        "hand_tip_world": hand_tip_world,
        "target_world": target_world,
        "pole_world": pole_world,
        "target_error": target_error,
        "hand_world_euler_deg": hand_world_euler,
        "target_world_euler_deg": target_world_euler,
        "rotation_error_deg": rotation_error_deg,
        "upper_arm_length": upper_arm_length,
        "forearm_length": forearm_length,
        "hand_length": hand_length,
        "total_arm_length": total_arm_length,
        "elbow_flexion_deg": elbow_flexion_deg,
        "ik_influence": ik_influence,
        "rot_influence": rot_influence,
    }
