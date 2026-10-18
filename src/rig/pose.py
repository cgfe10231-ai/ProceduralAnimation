"""Reusable programmatic pose control interface for CharacterArmature (Task 4B).

Provides deterministic functions to reset poses, rotate individual joints in degrees,
translate root/pelvis bones, and apply batch pose dictionaries for future motion modules.
"""

import math
from typing import Dict, Optional, Tuple

import bpy
from mathutils import Euler, Vector


def _resolve_armature(armature_obj: Optional[bpy.types.Object] = None) -> bpy.types.Object:
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")
    return armature_obj


def reset_pose(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset all pose bones of the armature back to rest pose."""
    arm = _resolve_armature(armature_obj)
    for pbone in arm.pose.bones:
        pbone.rotation_mode = "XYZ"
        pbone.location = Vector((0.0, 0.0, 0.0))
        pbone.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
        pbone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pbone.scale = Vector((1.0, 1.0, 1.0))
    bpy.context.view_layer.update()


def set_bone_rotation(
    armature_obj: Optional[bpy.types.Object],
    bone_name: str,
    euler_deg: Tuple[float, float, float],
    update: bool = True,
) -> bpy.types.PoseBone:
    """Set a pose bone's local XYZ Euler rotation in degrees."""
    arm = _resolve_armature(armature_obj)
    pbone = arm.pose.bones.get(bone_name)
    if pbone is None:
        raise KeyError(f"Pose bone '{bone_name}' not found in '{arm.name}'")
    pbone.rotation_mode = "XYZ"
    rx, ry, rz = (math.radians(val) for val in euler_deg)
    pbone.rotation_euler = Euler((rx, ry, rz), "XYZ")
    if update:
        bpy.context.view_layer.update()
    return pbone


def set_bone_location(
    armature_obj: Optional[bpy.types.Object],
    bone_name: str,
    location_xyz: Tuple[float, float, float],
    update: bool = True,
) -> bpy.types.PoseBone:
    """Set a pose bone's local translation offset (in meters)."""
    arm = _resolve_armature(armature_obj)
    pbone = arm.pose.bones.get(bone_name)
    if pbone is None:
        raise KeyError(f"Pose bone '{bone_name}' not found in '{arm.name}'")
    pbone.location = Vector(location_xyz)
    if update:
        bpy.context.view_layer.update()
    return pbone


def apply_pose_dict(
    armature_obj: Optional[bpy.types.Object],
    rotations_deg: Optional[Dict[str, Tuple[float, float, float]]] = None,
    locations: Optional[Dict[str, Tuple[float, float, float]]] = None,
    reset_first: bool = False,
) -> None:
    """Apply a dictionary of bone rotations (in degrees) and optional translations."""
    arm = _resolve_armature(armature_obj)
    if reset_first:
        reset_pose(arm)
    if rotations_deg:
        for bone_name, deg_xyz in rotations_deg.items():
            set_bone_rotation(arm, bone_name, deg_xyz, update=False)
    if locations:
        for bone_name, loc_xyz in locations.items():
            set_bone_location(arm, bone_name, loc_xyz, update=False)
    bpy.context.view_layer.update()


def get_bone_world_head_tail(
    armature_obj: Optional[bpy.types.Object],
    bone_name: str,
) -> Tuple[Vector, Vector]:
    """Return the posed world-space (head, tail) coordinates of a bone."""
    arm = _resolve_armature(armature_obj)
    pbone = arm.pose.bones.get(bone_name)
    if pbone is None:
        raise KeyError(f"Pose bone '{bone_name}' not found in '{arm.name}'")
    world_head = arm.matrix_world @ pbone.head
    world_tail = arm.matrix_world @ pbone.tail
    return world_head, world_tail


def get_part_world_center(part_name: str) -> Vector:
    """Return the current world-space origin/center of a bound body part object."""
    obj = bpy.data.objects.get(part_name)
    if obj is None:
        raise KeyError(f"Character part '{part_name}' not found")
    return obj.matrix_world.translation.copy()
