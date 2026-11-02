"""Procedural two-bone arm IK and independent hand orientation control (Task 6F-A / Task 10-A).

Builds on the existing 19-bone CharacterArmature from Task 4B and complements leg IK (Task 4C):
- Creates dedicated Empty control objects for left/right hand IK targets (`HandIK.L`, `HandIK.R`)
  and elbow pole targets (`ElbowPole.L`, `ElbowPole.R`).
- Configures Blender native `IK` constraints (`chain_count = 2`) on `forearm.L` and `forearm.R`
  so `upper_arm` + `forearm` form a deterministic two-bone IK chain per arm.
- Configures elbow flexion constraints and pre-bend solver hints with matched `pole_angle = -90.0 deg`
  to guarantee natural forward/inward elbow flexion and outward/backward olecranon projection.
- Configures native `COPY_ROTATION` constraints on `hand.L` and `hand.R` targeting `HandIK.L` / `HandIK.R`
  in world space, enabling independent 3D hand orientation control decoupled from IK arm solving.
- Zero-impact backward compatibility:
  - Bone hierarchy and naming are 100% preserved.
  - IK constraints and rotation constraints default to `influence = 0.0`.
  - When influence is 0.0, the armature evaluates 100% identical to the original FK arm swing.
- Programmatic API:
  - `setup_arm_ik(...)`: idempotent configuration of arm IK constraints and empties.
  - `set_hand_ik_target(...)`: sets independent world-space position, 3D hand rotation, and elbow pole.
  - `set_arm_ik_influence(...)`: smoothly blends between FK (0.0) and IK (1.0).
  - `reset_arm_ik(...)`: resets arm IK targets and sets influence back to 0.0.
  - `get_arm_ik_state(...)`: inspects actual bone lengths, target error, orientation error, and reachability.

Task 10-A Contracts:
- Setup Idempotency: setup_arm_ik() ensures controls and constraints exist with correct configuration,
  without resetting active positions, orientations, or influences.
- Explicit Reset: reset_arm_ik() actively restores neutral rest positions and influence=0.0 while
  respecting existing effective parent transforms and rotation modes.
- Effective Parent Matrix: M_eff = M_parent @ matrix_parent_inverse handles world translation and
  rotation inversion across arbitrary valid conformal parent hierarchies.
- Rotation Mode Fidelity: preserves controller active rotation_mode across 6 Euler modes, QUATERNION,
  and AXIS_ANGLE without forced conversion to XYZ.
- Dependency Graph Freshness: synchronizes view layer before computing effective parent matrices.
"""

import math
from typing import Any, Dict, Optional, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.rig.transform_utils import (
    apply_target_rotation,
    compute_effective_parent_matrix,
    validate_effective_parent_transform,
    world_to_local_position,
    world_to_local_rotation,
    world_to_local_rotation_quaternion,
)

ARM_IK_TARGET_NAMES: Dict[str, str] = {"L": "HandIK.L", "R": "HandIK.R"}
ARM_POLE_TARGET_NAMES: Dict[str, str] = {"L": "ElbowPole.L", "R": "ElbowPole.R"}
ARM_IK_CONSTRAINT_NAMES: Dict[str, str] = {"L": "ArmIK.L", "R": "ArmIK.R"}
HAND_ROT_CONSTRAINT_NAMES: Dict[str, str] = {"L": "HandRotation.L", "R": "HandRotation.R"}

# Segment geometry matching Task 4B specifications (meters)
SHOULDER_X_OFFSET: float = 0.24
SHOULDER_REST_Z: float = 1.54
ELBOW_REST_Z: float = 1.24
WRIST_REST_Z: float = 0.98
HAND_TIP_REST_Z: float = 0.88

UPPER_ARM_LENGTH: float = 0.30
FOREARM_LENGTH: float = 0.26
HAND_LENGTH: float = 0.10

MAX_ARM_REACH: float = UPPER_ARM_LENGTH + FOREARM_LENGTH  # 0.56 m
MIN_ARM_REACH: float = 0.08  # Minimum distance avoiding degenerate zero-length vectors

DEFAULT_POLE_BACKWARD_OFFSET: float = 0.40  # Meters backward (-Y) from arm plane
DEFAULT_POLE_OUTWARD_OFFSET: float = 0.08   # Meters outward (X) from arm plane


def _validate_influence(val: Any, param_name: str = "influence") -> float:
    """Validate that influence is a finite real number in [0.0, 1.0]."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise TypeError(f"'{param_name}' must be a real number, got {type(val).__name__}: {val!r}")
    f_val = float(val)
    if not math.isfinite(f_val):
        raise ValueError(f"'{param_name}' must be finite, got: {val!r}")
    if f_val < 0.0 or f_val > 1.0:
        raise ValueError(f"'{param_name}' must be in [0.0, 1.0], got: {val!r}")
    return f_val


def _validate_side(side: Any, allow_both: bool = False, param_name: str = "side") -> str:
    """Validate arm side identifier ('L', 'R', or optionally 'BOTH')."""
    if not isinstance(side, str):
        raise TypeError(f"'{param_name}' must be a string, got {type(side).__name__}: {side!r}")
    s_up = side.strip().upper()
    valid_sides = ("L", "R", "BOTH") if allow_both else ("L", "R")
    if s_up not in valid_sides:
        expected = "'L', 'R', or 'BOTH'" if allow_both else "'L' or 'R'"
        raise ValueError(f"Invalid {param_name} '{side}', expected {expected}")
    return s_up


def _validate_vec3(vec: Any, param_name: str, allow_none: bool = False) -> Optional[Tuple[float, float, float]]:
    """Validate 3-element finite coordinate sequence."""
    if vec is None:
        if allow_none:
            return None
        raise TypeError(f"'{param_name}' cannot be None; expected 3-element sequence of finite numbers")
    if isinstance(vec, (str, bytes, dict)) or not hasattr(vec, "__len__") or not hasattr(vec, "__getitem__"):
        raise TypeError(f"'{param_name}' must be a sequence of 3 finite numbers, got {type(vec).__name__}")
    if len(vec) != 3:
        raise ValueError(f"'{param_name}' must have exactly 3 components, got {len(vec)}: {vec!r}")
    out = []
    for i, comp in enumerate(vec):
        if isinstance(comp, bool) or not isinstance(comp, (int, float)):
            raise TypeError(f"'{param_name}[{i}]' must be a real number, got {type(comp).__name__}: {comp!r}")
        f_comp = float(comp)
        if not math.isfinite(f_comp):
            raise ValueError(f"'{param_name}[{i}]' must be finite, got: {comp!r}")
        out.append(f_comp)
    return (out[0], out[1], out[2])


def _validate_bool(val: Any, param_name: str = "clamp_reach") -> bool:
    """Validate that value is strictly a boolean."""
    if not isinstance(val, bool):
        raise TypeError(f"'{param_name}' must be a boolean (True or False), got {type(val).__name__}: {val!r}")
    return val


def _resolve_armature(armature_obj: Optional[bpy.types.Object] = None) -> bpy.types.Object:
    """Resolve and validate the CharacterArmature object."""
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")
    return armature_obj


def _ensure_character_collection() -> bpy.types.Collection:
    """Ensure the Character collection exists in the active scene."""
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
) -> Tuple[bpy.types.Object, bool]:
    """Retrieve or construct an Empty control object preserving existing parent and transform.

    Returns:
        Tuple (obj, is_new): obj is the Empty object, is_new indicates whether it was created fresh.
    """
    obj = bpy.data.objects.get(name)
    if obj is not None and obj.type != "EMPTY":
        bpy.data.objects.remove(obj, do_unlink=True)
        obj = None

    if obj is None:
        obj = bpy.data.objects.new(name, None)
        collection.objects.link(obj)
        obj.empty_display_type = display_type
        obj.empty_display_size = display_size
        obj.rotation_mode = "XYZ"
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = Matrix.Identity(4)
        return obj, True

    # Existing valid Empty: ensure linked to collection and update display properties
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    obj.empty_display_type = display_type
    obj.empty_display_size = display_size
    return obj, False


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


def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone arm IK chains, elbow pole targets, and hand orientation controls.

    This function is strictly idempotent:
    - Preserves existing controller objects, parents, matrices, positions, orientations, and rotation modes.
    - Preserves existing constraint instances, configurations, and active influences.
    - Only initializes neutral rest positions when creating brand new controllers.
    - Only sets initial_influence when creating brand new constraints.
    - Only applies pre-bend hints when initializing a previously unconstrained arm.

    Args:
        armature_obj: Optional CharacterArmature object.
        initial_influence: Initial constraint influence in [0.0, 1.0]. Defaults to 0.0 (FK mode).

    Returns:
        Dict mapping controller names ('HandIK.L', 'HandIK.R', 'ElbowPole.L', 'ElbowPole.R')
        to their Empty objects.
    """
    valid_influence = _validate_influence(initial_influence, param_name="initial_influence")
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    collection = _ensure_character_collection()

    controls: Dict[str, bpy.types.Object] = {}

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_name = ARM_IK_TARGET_NAMES[side]
        pole_name = ARM_POLE_TARGET_NAMES[side]

        ik_obj, ik_is_new = _get_or_create_empty(
            name=ik_name,
            display_type="CUBE",
            display_size=0.04,
            parent=root_obj,
            collection=collection,
        )
        pole_obj, pole_is_new = _get_or_create_empty(
            name=pole_name,
            display_type="SPHERE",
            display_size=0.035,
            parent=root_obj,
            collection=collection,
        )

        # Set neutral rest positions only for newly created controllers
        if ik_is_new:
            ik_obj.location = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
            ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        if pole_is_new:
            pole_obj.location = Vector((
                sign * (SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
                -DEFAULT_POLE_BACKWARD_OFFSET,
                ELBOW_REST_Z,
            ))
            pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

        controls[ik_name] = ik_obj
        controls[pole_name] = pole_obj

        p_up = arm.pose.bones[f"upper_arm.{side}"]
        p_fore = arm.pose.bones[f"forearm.{side}"]
        p_hand = arm.pose.bones[f"hand.{side}"]

        # Shoulder ball joint: unconstrained 3D rotation during IK
        p_up.lock_ik_x = False
        p_up.lock_ik_y = False
        p_up.lock_ik_z = False

        # Elbow hinge joint: flex on sagittal local X (positive is forward flexion)
        # Lock Y (axial twist) and Z (lateral adduction/abduction)
        p_fore.lock_ik_x = False
        p_fore.lock_ik_y = True
        p_fore.lock_ik_z = True
        p_fore.use_ik_limit_x = True
        p_fore.ik_min_x = math.radians(0.0)      # Fully extended (straight)
        p_fore.ik_max_x = math.radians(150.0)    # Maximum anatomical elbow flexion

        # Resolve or configure existing ArmIK constraint
        ik_con = None
        con_name_ik = ARM_IK_CONSTRAINT_NAMES[side]
        for con in list(p_fore.constraints):
            if con.name == con_name_ik:
                if con.type == "IK":
                    ik_con = con
                else:
                    p_fore.constraints.remove(con)
            elif con.type == "IK" and con.name.startswith("ArmIK"):
                p_fore.constraints.remove(con)

        newly_created_ik_con = False
        if ik_con is None:
            ik_con = p_fore.constraints.new(type="IK")
            ik_con.name = con_name_ik
            ik_con.influence = valid_influence
            newly_created_ik_con = True

        ik_con.target = ik_obj
        ik_con.pole_target = pole_obj
        ik_con.chain_count = 2
        ik_con.use_tail = True
        ik_con.use_stretch = False
        ik_con.pole_angle = math.radians(-90.0)

        # Resolve or configure existing HandRotation constraint
        rot_con = None
        con_name_rot = HAND_ROT_CONSTRAINT_NAMES[side]
        for con in list(p_hand.constraints):
            if con.name == con_name_rot:
                if con.type == "COPY_ROTATION":
                    rot_con = con
                else:
                    p_hand.constraints.remove(con)
            elif con.type == "COPY_ROTATION" and con.name.startswith("HandRotation"):
                p_hand.constraints.remove(con)

        if rot_con is None:
            rot_con = p_hand.constraints.new(type="COPY_ROTATION")
            rot_con.name = con_name_rot
            rot_con.influence = valid_influence

        rot_con.target = ik_obj
        rot_con.target_space = "WORLD"
        rot_con.owner_space = "WORLD"
        rot_con.mix_mode = "REPLACE"

        # Apply pre-bend hint only when establishing an IK chain for the first time
        if newly_created_ik_con:
            _apply_arm_ik_prebend_hint_side(arm, side)

    bpy.context.view_layer.update()
    return controls


def set_arm_ik_influence(
    armature_obj: Optional[bpy.types.Object] = None,
    side: str = "BOTH",
    influence: float = 1.0,
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

    for s in sides:
        p_fore = arm.pose.bones.get(f"forearm.{s}")
        p_hand = arm.pose.bones.get(f"hand.{s}")
        if p_fore and ARM_IK_CONSTRAINT_NAMES[s] in p_fore.constraints:
            p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[s]].influence = valid_influence
        if p_hand and HAND_ROT_CONSTRAINT_NAMES[s] in p_hand.constraints:
            p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[s]].influence = valid_influence

    bpy.context.view_layer.update()


def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode).

    Preserves existing controller parent relationships, rotation_mode, and matrix_parent_inverse,
    transforming neutral world positions and orientations into the controller's effective parent space.
    """
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    bpy.context.view_layer.update()

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])

        # Compute neutral targets in root/world coordinates
        ik_neutral_local = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
        pole_neutral_local = Vector((
            sign * (SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
            -DEFAULT_POLE_BACKWARD_OFFSET,
            ELBOW_REST_Z,
        ))

        if root_obj is not None:
            ik_neutral_world = root_obj.matrix_world @ ik_neutral_local
            pole_neutral_world = root_obj.matrix_world @ pole_neutral_local
            neutral_world_rot_quat = root_obj.matrix_world.to_quaternion()
        else:
            ik_neutral_world = ik_neutral_local
            pole_neutral_world = pole_neutral_local
            neutral_world_rot_quat = Quaternion()

        if ik_obj is not None:
            eff_ik_mat = compute_effective_parent_matrix(ik_obj)
            validate_effective_parent_transform(eff_ik_mat, ik_obj.name)
            ik_obj.location = world_to_local_position(ik_neutral_world, eff_ik_mat)
            apply_target_rotation(ik_obj, neutral_world_rot_quat, eff_ik_mat)

        if pole_obj is not None:
            eff_pole_mat = compute_effective_parent_matrix(pole_obj)
            validate_effective_parent_transform(eff_pole_mat, pole_obj.name)
            pole_obj.location = world_to_local_position(pole_neutral_world, eff_pole_mat)
            apply_target_rotation(pole_obj, Quaternion(), eff_pole_mat)

        p_up = arm.pose.bones.get(f"upper_arm.{side}")
        p_fore = arm.pose.bones.get(f"forearm.{side}")
        p_hand = arm.pose.bones.get(f"hand.{side}")
        if p_up:
            p_up.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
        if p_fore:
            p_fore.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
            if ARM_IK_CONSTRAINT_NAMES[side] in p_fore.constraints:
                p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[side]].influence = 0.0
        if p_hand:
            p_hand.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
            if HAND_ROT_CONSTRAINT_NAMES[side] in p_hand.constraints:
                p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[side]].influence = 0.0

        _apply_arm_ik_prebend_hint_side(arm, side)

    bpy.context.view_layer.update()


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    arm = _resolve_armature(armature_obj)
    bpy.context.view_layer.update()

    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[valid_side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[valid_side])

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

    ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[valid_side])
    rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[valid_side])
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


def set_hand_ik_target(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    world_xyz: Tuple[float, float, float],
    hand_rotation_deg: Optional[Tuple[float, float, float]] = None,
    pole_world_xyz: Optional[Tuple[float, float, float]] = None,
    clamp_reach: bool = True,
    influence: float = 1.0,
) -> dict:
    """Set the left ('L') or right ('R') hand IK target in world coordinates.

    Follows the 10-A and 10-B-1 Pre-validation Contracts:
    - Pre-validation: Validates all user inputs strictly before any scene mutation or auto-initialization.
    - Phase A1: Synchronizes dependency graph (view_layer.update()) before reading parent transforms.
    - Phase A2: Validates effective parent matrices before any scene mutation occurs.
    - Phase A3: Verifies reachability, pole, and derived local targets are strictly finite.
    - Phase B: Commits transforms and constraints atomically.
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
    # Pre-validation: ALL user inputs validated before any scene mutation or auto-initialization
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    valid_world_xyz = _validate_vec3(world_xyz, param_name="world_xyz", allow_none=False)
    valid_hand_rot = _validate_vec3(hand_rotation_deg, param_name="hand_rotation_deg", allow_none=True)
    valid_pole_world = _validate_vec3(pole_world_xyz, param_name="pole_world_xyz", allow_none=True)
    valid_clamp_reach = _validate_bool(clamp_reach, param_name="clamp_reach")
    valid_influence = _validate_influence(influence, param_name="influence")

    arm = _resolve_armature(armature_obj)
    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[valid_side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[valid_side])
    if ik_obj is None or pole_obj is None:
        setup_arm_ik(arm, initial_influence=valid_influence)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES[valid_side]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES[valid_side]]

    # Phase A1: Synchronize dependency graph FIRST before reading parent matrices
    bpy.context.view_layer.update()

    # Phase A2: Compute and validate effective parent transform domains before any scene mutation
    eff_ik_mat = compute_effective_parent_matrix(ik_obj)
    eff_pole_mat = compute_effective_parent_matrix(pole_obj)
    validate_effective_parent_transform(eff_ik_mat, ik_obj.name)
    validate_effective_parent_transform(eff_pole_mat, pole_obj.name)

    # Note: No mutation of controllers, pose bones, constraints, or pre-bend hint occurs before this point!
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")

    p_up = arm.pose.bones[f"upper_arm.{valid_side}"]
    p_fore = arm.pose.bones[f"forearm.{valid_side}"]
    p_hand = arm.pose.bones[f"hand.{valid_side}"]

    shoulder_world = arm.matrix_world @ p_up.head

    requested = Vector(valid_world_xyz)
    applied = requested.copy()
    clamped_reach = False

    vec_from_shoulder = applied - shoulder_world
    dist = vec_from_shoulder.length
    is_reachable = (MIN_ARM_REACH <= dist <= MAX_ARM_REACH)

    # Reach clamping relative to shoulder joint
    if valid_clamp_reach:
        if dist > MAX_ARM_REACH:
            clamped_reach = True
            if dist > 1e-6:
                applied = shoulder_world + vec_from_shoulder.normalized() * MAX_ARM_REACH
            else:
                applied = shoulder_world + Vector((0.0, 0.0, -1.0)) * MAX_ARM_REACH
        elif dist < MIN_ARM_REACH:
            clamped_reach = True
            direction = vec_from_shoulder.normalized() if dist > 1e-6 else Vector((0.0, 0.0, -1.0))
            applied = shoulder_world + direction * MIN_ARM_REACH

    # Elbow pole target positioning in world space
    sign = -1.0 if valid_side == "L" else 1.0
    if valid_pole_world is not None:
        pole_world = Vector(valid_pole_world)
    else:
        # Default pole placement: behind (-Y) and slightly outward (X)
        mid_pt = 0.5 * (shoulder_world + applied)
        pole_world = Vector((
            mid_pt.x + sign * DEFAULT_POLE_OUTWARD_OFFSET,
            min(shoulder_world.y, applied.y) - DEFAULT_POLE_BACKWARD_OFFSET,
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

    # Phase A3: Verify all derived spatial coordinates and orientations are strictly finite
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

    # Phase B: Commit transforms and constraints
    _apply_arm_ik_prebend_hint_side(arm, valid_side)

    # Convert applied world targets to controller local spaces preserving rotation_mode
    ik_obj.location = ik_local_pos
    apply_target_rotation(ik_obj, target_world_rot_quat, eff_ik_mat)
    pole_obj.location = pole_local_pos

    # Update constraint influence
    ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[valid_side])
    if ik_con:
        ik_con.influence = valid_influence
    rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[valid_side])
    if rot_con:
        rot_con.influence = valid_influence

    bpy.context.view_layer.update()

    state = get_arm_ik_state(arm, valid_side)
    state["requested_world"] = requested
    state["applied_world"] = applied
    state["is_reachable"] = is_reachable
    state["clamped_reach"] = clamped_reach
    return state
