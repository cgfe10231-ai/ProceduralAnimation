"""Armature resolution and pre-bend helpers migrated from `src/rig/arm_ik.py` (Task 10-B Layer 4)."""

import math
from typing import Optional

import bpy
from mathutils import Euler


def _resolve_armature(armature_obj: Optional[bpy.types.Object] = None) -> bpy.types.Object:
    """Resolve and validate the CharacterArmature object."""
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")
    return armature_obj


def _apply_arm_ik_prebend_hint_side(arm: bpy.types.Object, side: str) -> None:
    """Apply a small sagittal pre-bend hint to a single arm side if currently unbent."""
    p_up = arm.pose.bones[f"upper_arm.{side}"]
    p_fore = arm.pose.bones[f"forearm.{side}"]
    p_hand = arm.pose.bones[f"hand.{side}"]

    p_up.rotation_mode = "XYZ"
    p_fore.rotation_mode = "XYZ"
    p_hand.rotation_mode = "XYZ"

    # Apply slight pre-bend only if currently zero
    euler_mag = p_up.rotation_euler.to_matrix().to_quaternion().angle
    if euler_mag < 1e-4:
        p_up.rotation_euler = Euler((math.radians(2.0), 0.0, 0.0), "XYZ")
    euler_mag_fore = p_fore.rotation_euler.to_matrix().to_quaternion().angle
    if euler_mag_fore < 1e-4:
        p_fore.rotation_euler = Euler((math.radians(4.0), 0.0, 0.0), "XYZ")


def _apply_arm_ik_prebend_hint(arm: bpy.types.Object) -> None:
    """Apply a small sagittal pre-bend hint to upper arm and forearm across both sides."""
    for side in ("L", "R"):
        _apply_arm_ik_prebend_hint_side(arm, side)
