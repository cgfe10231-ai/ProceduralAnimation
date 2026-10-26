"""Procedural support-foot locking and flat-ground (Z=0) contact control (Task 4D).

Builds on the Task 4C two-bone leg IK system (`FootIK.L/R`, `KneePole.L/R`):
- Manages independent left/right foot support states stored persistently on `FootIK.L/R`.
- Locks a support foot in fixed world coordinates (`parent = None` in world space) so
  moving `CharacterRoot` does not drag the locked foot controller along.
- Records ground contact position (`Z = 0.0`), locked ankle IK target (`Z = 0.07 m`),
  target foot orientation (degrees), lock status, and baseline bone/mesh world coordinates.
- Evaluates IK reachability when `CharacterRoot` moves:
  - Never secretly moves the locked target point when root displacement exceeds leg reach.
  - Explicitly reports `is_reachable = False` and `reach_status = "UNREACHABLE"` when
    root movement exceeds reachable leg bounds.
  - Measures actual world-space drift of the ankle bone (`foot.head`), toe bone (`foot.tail`),
    and bound foot mesh (`Foot_L/R`) alongside controller drift (`0.0 m`).
- Supports releasing the support lock (`unlock_foot_contact`) and handing control back
  to normal `set_foot_ik_target()` calls.
"""

import math
from typing import Dict, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

from src.character.builder import world_min_z
from src.rig.ik import (
    ANKLE_REST_Z,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    MIN_LEG_REACH,
    POLE_FORWARD_OFFSET,
    POLE_TARGET_NAMES,
    _apply_ik_prebend_hint,
    _resolve_armature,
    get_leg_ik_state,
    setup_leg_ik,
)
from src.rig.pose import get_part_world_center

FLAT_GROUND_Z: float = 0.0
# In neutral standing rest pose (Z_root = 0.0, Z_hip = 0.89 m, Z_ankle = 0.07 m),
# the vertical span is 0.89 - 0.07 = 0.82 m == MAX_LEG_REACH.
# For small pure-horizontal root shifts (e.g. d_xy <= 0.15 m at Z_root = 0.0),
# the 3D hip-to-ankle distance is sqrt(d_xy^2 + 0.82^2) <= 0.8336 m (<= 15 mm drift).
MAX_SUPPORT_DRIFT_TOLERANCE: float = 0.015  # 15 mm max allowable ankle drift near full extension
MAX_EFFECTIVE_SUPPORT_REACH: float = MAX_LEG_REACH + MAX_SUPPORT_DRIFT_TOLERANCE  # 0.835 m


def _ensure_ik_controls(arm: bpy.types.Object, side: str) -> Tuple[bpy.types.Object, bpy.types.Object]:
    ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
    pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
    if ik_obj is None or pole_obj is None:
        setup_leg_ik(arm)
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
    return ik_obj, pole_obj


def _classify_reach(hip_to_target_dist: float) -> Tuple[bool, bool, str]:
    """Return (strictly_in_reach, is_reachable, reach_status)."""
    if hip_to_target_dist < MIN_LEG_REACH:
        return False, False, "UNREACHABLE_TOO_CLOSE"
    if hip_to_target_dist <= MAX_LEG_REACH + 1e-4:
        return True, True, "REACHABLE_STRICT"
    if hip_to_target_dist <= MAX_EFFECTIVE_SUPPORT_REACH + 1e-5:
        return False, True, "REACHABLE_NEAR_BOUNDARY"
    return False, False, "UNREACHABLE"


def lock_foot_contact(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    contact_world_xyz: Optional[Tuple[float, float, float]] = None,
    target_rotation_deg: Optional[Tuple[float, float, float]] = None,
) -> dict:
    """Lock the specified foot ('L' or 'R') to a fixed world-space ground contact point on Z=0.

    Decouples `FootIK.<side>` and `KneePole.<side>` from `CharacterRoot` (`parent = None`)
    so moving `CharacterRoot` leaves the locked world coordinate untouched.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj, pole_obj = _ensure_ik_controls(arm, side)
    bpy.context.view_layer.update()

    p_thigh = arm.pose.bones[f"thigh.{side}"]
    p_shin = arm.pose.bones[f"shin.{side}"]
    hip_world = arm.matrix_world @ p_thigh.head
    current_ankle_world = arm.matrix_world @ p_shin.tail

    if contact_world_xyz is None:
        contact_world = Vector((current_ankle_world.x, current_ankle_world.y, FLAT_GROUND_Z))
    else:
        contact_world = Vector((contact_world_xyz[0], contact_world_xyz[1], float(contact_world_xyz[2])))

    locked_ankle_world = Vector((contact_world.x, contact_world.y, contact_world.z + ANKLE_REST_Z))

    if target_rotation_deg is None:
        current_euler = ik_obj.matrix_world.to_euler("XYZ")
        target_rotation_deg = (
            round(math.degrees(current_euler.x), 4),
            round(math.degrees(current_euler.y), 4),
            round(math.degrees(current_euler.z), 4),
        )

    # Unparent FootIK and KneePole so they remain fixed in World Space independent of CharacterRoot
    ik_obj.parent = None
    ik_obj.matrix_parent_inverse = Matrix.Identity(4)
    ik_obj.location = locked_ankle_world.copy()
    rx, ry, rz = (math.radians(v) for v in target_rotation_deg)
    ik_obj.rotation_euler = Euler((rx, ry, rz), "XYZ")

    pole_world = Vector((
        hip_world.x,
        max(hip_world.y, locked_ankle_world.y) + POLE_FORWARD_OFFSET,
        0.5 * (hip_world.z + locked_ankle_world.z),
    ))
    pole_obj.parent = None
    pole_obj.matrix_parent_inverse = Matrix.Identity(4)
    pole_obj.location = pole_world

    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    # Record baseline bone and geometry world positions at the moment of locking
    p_foot = arm.pose.bones[f"foot.{side}"]
    foot_mesh = bpy.data.objects[f"Foot_{side}"]
    foot_head_world = arm.matrix_world @ p_foot.head
    foot_tail_world = arm.matrix_world @ p_foot.tail
    foot_center_world = get_part_world_center(f"Foot_{side}")
    foot_min_z = world_min_z(foot_mesh)

    # Persist lock metadata on the controller object so .blend reopen retains full state
    ik_obj["is_locked"] = True
    ik_obj["contact_world_xyz"] = tuple(float(v) for v in contact_world)
    ik_obj["locked_ankle_world_xyz"] = tuple(float(v) for v in locked_ankle_world)
    ik_obj["target_rotation_deg"] = tuple(float(v) for v in target_rotation_deg)
    ik_obj["locked_foot_head_xyz"] = tuple(float(v) for v in foot_head_world)
    ik_obj["locked_foot_tail_xyz"] = tuple(float(v) for v in foot_tail_world)
    ik_obj["locked_foot_center_xyz"] = tuple(float(v) for v in foot_center_world)
    ik_obj["locked_foot_min_z"] = float(foot_min_z)

    return evaluate_foot_support(arm, side)


def unlock_foot_contact(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    reparent_to_root: bool = True,
) -> dict:
    """Release the support lock on the specified foot ('L' or 'R') and return it to normal IK control."""
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj, pole_obj = _ensure_ik_controls(arm, side)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    bpy.context.view_layer.update()

    current_ik_world = ik_obj.matrix_world.translation.copy()
    current_ik_euler = ik_obj.matrix_world.to_euler("XYZ")
    current_pole_world = pole_obj.matrix_world.translation.copy()

    ik_obj["is_locked"] = False

    if reparent_to_root and root_obj is not None:
        inv_root = root_obj.matrix_world.inverted()
        ik_obj.parent = root_obj
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        ik_obj.location = inv_root @ current_ik_world
        ik_obj.rotation_euler = current_ik_euler

        pole_obj.parent = root_obj
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        pole_obj.location = inv_root @ current_pole_world
    else:
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        ik_obj.location = current_ik_world
        ik_obj.rotation_euler = current_ik_euler

        pole_obj.parent = None
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        pole_obj.location = current_pole_world

    bpy.context.view_layer.update()
    return get_foot_support_state(arm, side)


def evaluate_foot_support(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Evaluate current support state, IK reachability, and bone/mesh world drift for a foot.

    Never moves or clamps the locked `FootIK.<side>` point when locked.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj, pole_obj = _ensure_ik_controls(arm, side)

    is_locked = bool(ik_obj.get("is_locked", False))
    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    p_thigh = arm.pose.bones[f"thigh.{side}"]
    hip_world = arm.matrix_world @ p_thigh.head

    if is_locked:
        locked_ankle_world = Vector(ik_obj.get("locked_ankle_world_xyz", tuple(ik_obj.matrix_world.translation)))
        contact_world = Vector(ik_obj.get("contact_world_xyz", (locked_ankle_world.x, locked_ankle_world.y, FLAT_GROUND_Z)))
        target_rot_deg = tuple(ik_obj.get("target_rotation_deg", (0.0, 0.0, 0.0)))

        # Ensure FootIK remains strictly at its locked world coordinate (never secretly moved)
        if ik_obj.parent is not None:
            ik_obj.parent = None
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        ik_obj.location = locked_ankle_world.copy()
        rx, ry, rz = (math.radians(v) for v in target_rot_deg)
        ik_obj.rotation_euler = Euler((rx, ry, rz), "XYZ")

        # Update knee pole in world space so the knee plane tracks forward (+Y) without moving FootIK
        if pole_obj.parent is not None:
            pole_obj.parent = None
            pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        pole_obj.location = Vector((
            hip_world.x,
            max(hip_world.y, locked_ankle_world.y) + POLE_FORWARD_OFFSET,
            0.5 * (hip_world.z + locked_ankle_world.z),
        ))
        bpy.context.view_layer.update()
    else:
        locked_ankle_world = ik_obj.matrix_world.translation.copy()
        contact_world = Vector((locked_ankle_world.x, locked_ankle_world.y, max(FLAT_GROUND_Z, locked_ankle_world.z - ANKLE_REST_Z)))
        euler = ik_obj.matrix_world.to_euler("XYZ")
        target_rot_deg = (
            round(math.degrees(euler.x), 4),
            round(math.degrees(euler.y), 4),
            round(math.degrees(euler.z), 4),
        )

    ik_state = get_leg_ik_state(arm, side)
    hip_world = ik_state["hip_world"]
    current_controller_world = ik_obj.matrix_world.translation.copy()
    current_foot_head_world = ik_state["foot_head_world"]
    current_foot_tail_world = ik_state["foot_tail_world"]
    current_foot_center_world = get_part_world_center(f"Foot_{side}")
    current_foot_min_z = ik_state["foot_min_z"]

    hip_to_target_vec = locked_ankle_world - hip_world
    hip_to_target_dist = hip_to_target_vec.length
    horiz_offset = Vector((hip_to_target_vec.x, hip_to_target_vec.y, 0.0)).length

    strictly_in_reach, is_reachable, reach_status = _classify_reach(hip_to_target_dist)

    if is_locked and "locked_foot_head_xyz" in ik_obj:
        ref_head = Vector(ik_obj["locked_foot_head_xyz"])
        ref_tail = Vector(ik_obj["locked_foot_tail_xyz"])
        ref_center = Vector(ik_obj["locked_foot_center_xyz"])
        controller_drift = (current_controller_world - locked_ankle_world).length
        ankle_bone_drift = (current_foot_head_world - ref_head).length
        toe_bone_drift = (current_foot_tail_world - ref_tail).length
        mesh_center_drift = (current_foot_center_world - ref_center).length
        ankle_horiz_drift = Vector((
            current_foot_head_world.x - ref_head.x,
            current_foot_head_world.y - ref_head.y,
            0.0,
        )).length
    else:
        controller_drift = 0.0
        ankle_bone_drift = ik_state["target_error"]
        toe_bone_drift = 0.0
        mesh_center_drift = 0.0
        ankle_horiz_drift = 0.0

    return {
        "side": side,
        "is_locked": is_locked,
        "contact_world": contact_world,
        "locked_ankle_world": locked_ankle_world,
        "target_rotation_deg": target_rot_deg,
        "hip_world": hip_world,
        "hip_to_target_dist": hip_to_target_dist,
        "horiz_offset_from_hip": horiz_offset,
        "max_leg_reach": MAX_LEG_REACH,
        "max_effective_support_reach": MAX_EFFECTIVE_SUPPORT_REACH,
        "reach_margin_strict": MAX_LEG_REACH - hip_to_target_dist,
        "strictly_in_reach": strictly_in_reach,
        "is_reachable": is_reachable,
        "reach_status": reach_status,
        "controller_world": current_controller_world,
        "foot_head_world": current_foot_head_world,
        "foot_tail_world": current_foot_tail_world,
        "foot_center_world": current_foot_center_world,
        "foot_min_z": current_foot_min_z,
        "controller_drift": controller_drift,
        "ankle_bone_drift": ankle_bone_drift,
        "ankle_horiz_drift": ankle_horiz_drift,
        "toe_bone_drift": toe_bone_drift,
        "mesh_center_drift": mesh_center_drift,
        "knee_flexion_deg": ik_state["knee_flexion_deg"],
        "knee_forward_y": ik_state["knee_forward_y"],
    }


def get_foot_support_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Query the current support state and drift metrics for the given foot ('L' or 'R')."""
    return evaluate_foot_support(armature_obj, side)


def move_character_root_with_support(
    armature_obj: Optional[bpy.types.Object],
    new_root_world_xyz: Tuple[float, float, float],
) -> Dict[str, dict]:
    """Move `CharacterRoot` to `new_root_world_xyz` while maintaining any locked support feet
    in fixed world coordinates and evaluating reachability and bone/mesh drift for both legs.
    """
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    if root_obj is None:
        raise RuntimeError("CharacterRoot object not found")

    root_obj.location = Vector(new_root_world_xyz)
    bpy.context.view_layer.update()

    return {
        "L": evaluate_foot_support(arm, "L"),
        "R": evaluate_foot_support(arm, "R"),
    }
