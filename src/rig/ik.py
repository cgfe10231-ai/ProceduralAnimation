"""Procedural two-bone leg IK and independent foot orientation control (Task 4C).

Builds on the existing 19-bone CharacterArmature and 13 rigidly-bound body parts from Task 4B:
- Creates dedicated Empty control objects for left/right foot IK targets (`FootIK.L`, `FootIK.R`)
  and knee pole targets (`KneePole.L`, `KneePole.R`) parented to `CharacterRoot`.
- Configures Blender native `IK` constraints (`chain_count = 2`) on `shin.L` and `shin.R`
  so `thigh` + `shin` form a deterministic two-bone IK chain per leg.
- Configures knee flexion limits, pre-bend solver hints, and forward (+Y) pole targets
  with matched `pole_angle` to prevent backward knee bending or twisting/flipping.
- Decouples `foot.L` and `foot.R` rotation from shin IK rotation via `use_inherit_rotation = False`
  and native `COPY_ROTATION` constraints targeting `FootIK.L` / `FootIK.R`, keeping feet level
  by default while allowing explicit world/local foot orientation control.
- Provides a world-coordinate programmatic API (`set_foot_ik_target`, `reset_leg_ik`, `get_leg_ik_state`)
  with automatic reach clamping (`[MIN_LEG_REACH, MAX_LEG_REACH]`) and ground penetration clamping.
"""

import math
from typing import Dict, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

from src.character.builder import world_min_z

IK_TARGET_NAMES: Dict[str, str] = {"L": "FootIK.L", "R": "FootIK.R"}
POLE_TARGET_NAMES: Dict[str, str] = {"L": "KneePole.L", "R": "KneePole.R"}
IK_CONSTRAINT_NAMES: Dict[str, str] = {"L": "LegIK.L", "R": "LegIK.R"}
FOOT_ROT_CONSTRAINT_NAMES: Dict[str, str] = {"L": "FootRotation.L", "R": "FootRotation.R"}

# Exact segment geometry from Task 4A/4B (meters)
HIP_X_OFFSET: float = 0.11
HIP_REST_Z: float = 0.89
KNEE_REST_Z: float = 0.47
ANKLE_REST_Z: float = 0.07
THIGH_LENGTH: float = 0.42
SHIN_LENGTH: float = 0.40
MAX_LEG_REACH: float = THIGH_LENGTH + SHIN_LENGTH  # 0.82 m
MIN_LEG_REACH: float = 0.16  # Safe minimum distance from hip to ankle avoiding self-folding
POLE_FORWARD_OFFSET: float = 0.65  # Meters forward (+Y) of the leg plane


def _resolve_armature(armature_obj: Optional[bpy.types.Object] = None) -> bpy.types.Object:
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")
    return armature_obj


def _ensure_character_collection() -> bpy.types.Collection:
    scene = bpy.context.scene
    col = bpy.data.collections.get("Character")
    if col is None:
        col = bpy.data.collections.new("Character")
        scene.collection.children.link(col)
    return col


def _get_or_create_empty(
    name: str,
    display_type: str,
    display_size: float,
    parent: Optional[bpy.types.Object],
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type != "EMPTY":
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = None

    if obj is None:
        obj = bpy.data.objects.new(name, None)
        collection.objects.link(obj)
    elif obj.name not in collection.objects:
        collection.objects.link(obj)

    obj.empty_display_type = display_type
    obj.empty_display_size = display_size
    obj.rotation_mode = "XYZ"

    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)

    return obj


def _apply_ik_prebend_hint(arm: bpy.types.Object) -> None:
    """Apply a small sagittal pre-bend hint before IK constraint evaluation.

    In Edit Mode, `thigh` and `shin` are strictly vertical (180 deg collinear).
    Blender's iterative IK solver uses the PoseBone's pre-constraint basis transform
    as the initial configuration. A small forward thigh (+X) / backward shin (-X)
    basis angle guarantees deterministic forward (+Y) knee flexion even when the
    foot target moves vertically along the hip-ankle axis, while still extending
    to 180 deg when the target is at full standing reach (0.82 m).
    """
    for side in ("L", "R"):
        p_thigh = arm.pose.bones[f"thigh.{side}"]
        p_shin = arm.pose.bones[f"shin.{side}"]
        p_foot = arm.pose.bones[f"foot.{side}"]

        p_thigh.rotation_mode = "XYZ"
        p_shin.rotation_mode = "XYZ"
        p_foot.rotation_mode = "XYZ"

        p_thigh.rotation_euler = Euler((math.radians(2.0), 0.0, 0.0), "XYZ")
        p_shin.rotation_euler = Euler((math.radians(-4.0), 0.0, 0.0), "XYZ")
        p_foot.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")


def setup_leg_ik(armature_obj: Optional[bpy.types.Object] = None) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone IK chains, knee pole targets, and foot orientation controls."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    collection = _ensure_character_collection()

    controls: Dict[str, bpy.types.Object] = {}

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_name = IK_TARGET_NAMES[side]
        pole_name = POLE_TARGET_NAMES[side]

        ik_obj = _get_or_create_empty(
            name=ik_name,
            display_type="CUBE",
            display_size=0.05,
            parent=root_obj,
            collection=collection,
        )
        pole_obj = _get_or_create_empty(
            name=pole_name,
            display_type="SPHERE",
            display_size=0.04,
            parent=root_obj,
            collection=collection,
        )

        # Set neutral rest positions in CharacterRoot local space
        ik_obj.location = Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
        ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        pole_obj.location = Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))
        pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        controls[ik_name] = ik_obj
        controls[pole_name] = pole_obj

        # Configure IK joint properties on thigh and shin
        p_thigh = arm.pose.bones[f"thigh.{side}"]
        p_shin = arm.pose.bones[f"shin.{side}"]
        p_foot = arm.pose.bones[f"foot.{side}"]

        # Lock non-sagittal knee axes and restrict knee to anatomical flexion only (local -X)
        p_shin.lock_ik_x = False
        p_shin.lock_ik_y = True
        p_shin.lock_ik_z = True
        p_shin.use_ik_limit_x = True
        p_shin.ik_min_x = math.radians(-155.0)
        p_shin.ik_max_x = math.radians(0.0)

        p_thigh.lock_ik_x = False
        p_thigh.lock_ik_y = False
        p_thigh.lock_ik_z = False

        # Remove any existing IK constraints on shin to keep idempotency
        for con in list(p_shin.constraints):
            if con.type == "IK" or con.name == IK_CONSTRAINT_NAMES[side]:
                p_shin.constraints.remove(con)

        ik_con = p_shin.constraints.new(type="IK")
        ik_con.name = IK_CONSTRAINT_NAMES[side]
        ik_con.target = ik_obj
        ik_con.pole_target = pole_obj
        ik_con.chain_count = 2
        ik_con.use_tail = True
        ik_con.use_stretch = False
        # Bone +X points to World +X, Bone +Y points down (0,0,-1), Bone +Z points to World +Y (Forward).
        # Rotating +X by +90 deg around Bone +Y (0,0,-1) aligns with World +Y (Pole Target direction).
        ik_con.pole_angle = math.radians(90.0)

        # Decouple foot orientation from shin IK rotation so foot stays level by default
        arm.data.bones[f"foot.{side}"].use_inherit_rotation = False
        for con in list(p_foot.constraints):
            if con.type == "COPY_ROTATION" or con.name == FOOT_ROT_CONSTRAINT_NAMES[side]:
                p_foot.constraints.remove(con)

        rot_con = p_foot.constraints.new(type="COPY_ROTATION")
        rot_con.name = FOOT_ROT_CONSTRAINT_NAMES[side]
        rot_con.target = ik_obj
        rot_con.target_space = "LOCAL"
        rot_con.owner_space = "LOCAL"
        rot_con.mix_mode = "REPLACE"

    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    # Auto-verify whether pole_angle = +90 deg or -90 deg aligns bone +X with World +X
    p_thigh_l = arm.pose.bones["thigh.L"]
    thigh_world_x = (arm.matrix_world.to_3x3() @ p_thigh_l.matrix.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
    if thigh_world_x.x < 0.5:
        for side in ("L", "R"):
            p_shin = arm.pose.bones[f"shin.{side}"]
            ik_con = p_shin.constraints[IK_CONSTRAINT_NAMES[side]]
            ik_con.pole_angle = math.radians(-90.0)
        bpy.context.view_layer.update()

    print("[IK] Configured two-bone leg IK constraints, knee poles, and foot rotation controls for L/R")
    return controls


def reset_leg_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both legs and IK/Pole targets to the neutral grounded standing pose."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_obj is not None:
            ik_obj["is_locked"] = False
            if root_obj is not None:
                ik_obj.parent = root_obj
                ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            ik_obj.location = Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
        if pole_obj is not None:
            if root_obj is not None:
                pole_obj.parent = root_obj
                pole_obj.matrix_parent_inverse = Matrix.Identity(4)
            pole_obj.location = Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))
            pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()


def get_leg_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space IK positions, target error, knee bend, and foot grounding."""
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    bpy.context.view_layer.update()

    p_thigh = arm.pose.bones[f"thigh.{side}"]
    p_shin = arm.pose.bones[f"shin.{side}"]
    p_foot = arm.pose.bones[f"foot.{side}"]
    ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
    pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
    foot_mesh = bpy.data.objects[f"Foot_{side}"]

    hip_world = arm.matrix_world @ p_thigh.head
    knee_world = arm.matrix_world @ p_shin.head
    ankle_world = arm.matrix_world @ p_shin.tail
    foot_head_world = arm.matrix_world @ p_foot.head
    foot_tail_world = arm.matrix_world @ p_foot.tail
    target_world = ik_obj.matrix_world.translation.copy()
    pole_world = pole_obj.matrix_world.translation.copy()

    # Compute knee forward (+Y) offset relative to the hip -> ankle line segment
    hip_to_ankle = ankle_world - hip_world
    if hip_to_ankle.length > 1e-6:
        t = max(0.0, min(1.0, (knee_world - hip_world).dot(hip_to_ankle) / hip_to_ankle.length_squared))
        line_pt = hip_world + t * hip_to_ankle
        knee_forward_y = knee_world.y - line_pt.y
    else:
        knee_forward_y = knee_world.y - hip_world.y

    # Compute interior angle at the knee (180 deg = straight, < 180 deg = flexed)
    v_thigh = (hip_world - knee_world).normalized()
    v_shin = (ankle_world - knee_world).normalized()
    cos_angle = max(-1.0, min(1.0, v_thigh.dot(v_shin)))
    knee_interior_deg = math.degrees(math.acos(cos_angle))
    knee_flexion_deg = 180.0 - knee_interior_deg

    target_error = (ankle_world - target_world).length
    foot_min_z = world_min_z(foot_mesh)

    return {
        "side": side,
        "hip_world": hip_world,
        "knee_world": knee_world,
        "ankle_world": ankle_world,
        "foot_head_world": foot_head_world,
        "foot_tail_world": foot_tail_world,
        "target_world": target_world,
        "pole_world": pole_world,
        "target_error": target_error,
        "knee_forward_y": knee_forward_y,
        "knee_flexion_deg": knee_flexion_deg,
        "foot_min_z": foot_min_z,
    }


def set_foot_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    foot_rotation_deg: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    clamp_ground: bool = True,
) -> dict:
    """Set the left ('L') or right ('R') foot IK target in world coordinates.

    Automatically clamps unreachable targets to `[MIN_LEG_REACH, MAX_LEG_REACH]` from
    the hip joint and prevents foot ground penetration (`Z >= ground_z + ANKLE_REST_Z`)
    when `clamp_ground=True`. Also positions the knee pole target strictly forward (+Y)
    of the hip-ankle plane to prevent knee flipping.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
    pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
    if ik_obj is None or pole_obj is None:
        setup_leg_ik(arm)
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

    if bool(ik_obj.get("is_locked", False)):
        raise RuntimeError(
            f"Foot '{side}' is currently locked in ground support state; "
            f"call unlock_foot_contact(arm, '{side}') before setting a new IK target."
        )


    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    p_thigh = arm.pose.bones[f"thigh.{side}"]
    hip_world = arm.matrix_world @ p_thigh.head
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    ground_z = root_obj.matrix_world.translation.z if root_obj is not None else 0.0
    min_ankle_z = ground_z + ANKLE_REST_Z

    requested = Vector(world_xyz)
    applied = requested.copy()
    clamped_ground = False
    clamped_reach = False

    # 1. Ground penetration protection
    if clamp_ground and applied.z < min_ankle_z:
        applied.z = min_ankle_z
        clamped_ground = True

    # 2. Reach clamping relative to hip joint
    vec_from_hip = applied - hip_world
    dist = vec_from_hip.length
    if clamp_reach:
        if dist > MAX_LEG_REACH:
            clamped_reach = True
            if dist > 1e-6:
                applied = hip_world + vec_from_hip.normalized() * MAX_LEG_REACH
            # If spherical clamp pushed Z below min_ankle_z, project onto circle at Z = min_ankle_z
            if clamp_ground and applied.z < min_ankle_z:
                clamped_ground = True
                dz = min_ankle_z - hip_world.z
                horiz_budget_sq = max(0.0, MAX_LEG_REACH * MAX_LEG_REACH - dz * dz)
                horiz_budget = math.sqrt(horiz_budget_sq)
                horiz_vec = Vector((vec_from_hip.x, vec_from_hip.y, 0.0))
                if horiz_vec.length > 1e-6:
                    horiz_vec = horiz_vec.normalized() * horiz_budget
                applied = Vector((hip_world.x + horiz_vec.x, hip_world.y + horiz_vec.y, min_ankle_z))
        elif dist < MIN_LEG_REACH:
            clamped_reach = True
            direction = vec_from_hip.normalized() if dist > 1e-6 else Vector((0.0, 0.0, -1.0))
            applied = hip_world + direction * MIN_LEG_REACH
            if clamp_ground and applied.z < min_ankle_z:
                applied.z = min_ankle_z
                clamped_ground = True

    # Convert applied world position to ik_obj parent space
    if ik_obj.parent is not None:
        ik_obj.location = ik_obj.parent.matrix_world.inverted() @ applied
    else:
        ik_obj.location = applied

    if foot_rotation_deg is not None:
        rx, ry, rz = (math.radians(v) for v in foot_rotation_deg)
        ik_obj.rotation_euler = Euler((rx, ry, rz), "XYZ")
    else:
        ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

    # Keep knee pole target strictly forward (+Y) of both hip and foot target to prevent knee flip
    pole_world = Vector((
        hip_world.x,
        max(hip_world.y, applied.y) + POLE_FORWARD_OFFSET,
        0.5 * (hip_world.z + applied.z),
    ))
    if pole_obj.parent is not None:
        pole_obj.location = pole_obj.parent.matrix_world.inverted() @ pole_world
    else:
        pole_obj.location = pole_world

    bpy.context.view_layer.update()

    state = get_leg_ik_state(arm, side)
    state["requested_world"] = requested
    state["applied_world"] = applied
    state["clamped_reach"] = clamped_reach
    state["clamped_ground"] = clamped_ground
    return state
