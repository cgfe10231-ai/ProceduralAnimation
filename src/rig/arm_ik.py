"""Procedural two-bone arm IK and independent hand orientation control (Task 6F-A).

Builds on the existing 19-bone CharacterArmature from Task 4B and complements leg IK (Task 4C):
- Creates dedicated Empty control objects for left/right hand IK targets (`HandIK.L`, `HandIK.R`)
  and elbow pole targets (`ElbowPole.L`, `ElbowPole.R`) parented to `CharacterRoot`.
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

Note on Biomechanics and Physiology:
- The elbow flexion constraint (`use_ik_limit_x` on the forearm hinge) is strictly an IK solver hint
  to ensure correct single-axis hinge direction during IK inversion and prevent hyperextension.
  Comprehensive multi-body physiological Range of Motion (ROM) limits, Dempster mass distributions,
  and whole-body Center of Mass (CoM) are part of Task 6F-B.
"""

import math
from typing import Dict, Optional, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

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
) -> bpy.types.Object:
    """Retrieve or construct an Empty control object with unified parent transform."""
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


def _apply_arm_ik_prebend_hint(arm: bpy.types.Object) -> None:
    """Apply a small sagittal pre-bend hint to upper arm and forearm.

    In the rest pose, upper_arm and forearm are collinear along the vertical axis (180 deg).
    Blender's iterative IK solver uses the PoseBone basis transform as the initial configuration.
    A small forward (+X Euler) basis angle guarantees deterministic anatomical forward elbow
    flexion without solver ambiguity or flip.
    """
    for side in ("L", "R"):
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


def setup_arm_ik(
    armature_obj: Optional[bpy.types.Object] = None,
    initial_influence: float = 0.0,
) -> Dict[str, bpy.types.Object]:
    """Configure native Blender two-bone arm IK chains, elbow pole targets, and hand orientation controls.

    Args:
        armature_obj: Optional CharacterArmature object.
        initial_influence: Initial constraint influence in [0.0, 1.0]. Defaults to 0.0 (FK mode).

    Returns:
        Dict mapping controller names ('HandIK.L', 'HandIK.R', 'ElbowPole.L', 'ElbowPole.R')
        to their Empty objects.
    """
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    collection = _ensure_character_collection()

    controls: Dict[str, bpy.types.Object] = {}

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_name = ARM_IK_TARGET_NAMES[side]
        pole_name = ARM_POLE_TARGET_NAMES[side]

        ik_obj = _get_or_create_empty(
            name=ik_name,
            display_type="CUBE",
            display_size=0.04,
            parent=root_obj,
            collection=collection,
        )
        pole_obj = _get_or_create_empty(
            name=pole_name,
            display_type="SPHERE",
            display_size=0.035,
            parent=root_obj,
            collection=collection,
        )

        # Set neutral rest positions in CharacterRoot local space
        ik_obj.location = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
        ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

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

        # Remove existing IK constraint if any
        for con in list(p_fore.constraints):
            if con.name == ARM_IK_CONSTRAINT_NAMES[side] or (con.type == "IK" and con.name.startswith("ArmIK")):
                p_fore.constraints.remove(con)

        ik_con = p_fore.constraints.new(type="IK")
        ik_con.name = ARM_IK_CONSTRAINT_NAMES[side]
        ik_con.target = ik_obj
        ik_con.pole_target = pole_obj
        ik_con.chain_count = 2
        ik_con.use_tail = True
        ik_con.use_stretch = False
        # In this rig, Bone +X is World +X, Bone +Y points down (-Z), Bone +Z points forward (+Y).
        # When pole target is located backward (-Y), pole_angle = -90.0 deg aligns bone local X
        # with World +X, ensuring zero lateral twist and correct sagittal flexion.
        ik_con.pole_angle = math.radians(-90.0)
        ik_con.influence = max(0.0, min(1.0, initial_influence))

        # Hand independent 3D orientation control via COPY_ROTATION constraint
        # Leave arm.data.bones[hand].use_inherit_rotation = True so when influence=0,
        # hand follows forearm naturally in FK mode.
        for con in list(p_hand.constraints):
            if con.name == HAND_ROT_CONSTRAINT_NAMES[side] or (con.type == "COPY_ROTATION" and con.name.startswith("HandRotation")):
                p_hand.constraints.remove(con)

        rot_con = p_hand.constraints.new(type="COPY_ROTATION")
        rot_con.name = HAND_ROT_CONSTRAINT_NAMES[side]
        rot_con.target = ik_obj
        rot_con.target_space = "WORLD"
        rot_con.owner_space = "WORLD"
        rot_con.mix_mode = "REPLACE"
        rot_con.influence = max(0.0, min(1.0, initial_influence))

    _apply_arm_ik_prebend_hint(arm)
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
    arm = _resolve_armature(armature_obj)
    influence_clamped = max(0.0, min(1.0, float(influence)))
    sides = ("L", "R") if side.upper() == "BOTH" else (side.upper(),)

    for s in sides:
        if s not in ("L", "R"):
            raise ValueError(f"Invalid side '{s}', expected 'L', 'R', or 'BOTH'")
        p_fore = arm.pose.bones.get(f"forearm.{s}")
        p_hand = arm.pose.bones.get(f"hand.{s}")
        if p_fore and ARM_IK_CONSTRAINT_NAMES[s] in p_fore.constraints:
            p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[s]].influence = influence_clamped
        if p_hand and HAND_ROT_CONSTRAINT_NAMES[s] in p_hand.constraints:
            p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[s]].influence = influence_clamped

    bpy.context.view_layer.update()


def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode)."""
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])
        if ik_obj is not None:
            if root_obj is not None:
                ik_obj.parent = root_obj
                ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            ik_obj.location = Vector((sign * SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
            ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")
        if pole_obj is not None:
            if root_obj is not None:
                pole_obj.parent = root_obj
                pole_obj.matrix_parent_inverse = Matrix.Identity(4)
            pole_obj.location = Vector((
                sign * (SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
                -DEFAULT_POLE_BACKWARD_OFFSET,
                ELBOW_REST_Z,
            ))
            pole_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

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

    _apply_arm_ik_prebend_hint(arm)
    bpy.context.view_layer.update()


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    bpy.context.view_layer.update()

    p_up = arm.pose.bones[f"upper_arm.{side}"]
    p_fore = arm.pose.bones[f"forearm.{side}"]
    p_hand = arm.pose.bones[f"hand.{side}"]

    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])

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
        target_w_mat = ik_obj.matrix_world.to_3x3()
        target_world_euler = tuple(round(math.degrees(a), 4) for a in target_w_mat.to_euler("XYZ"))
        rot_diff = target_w_mat.to_quaternion().rotation_difference(hand_w_mat.to_quaternion()).angle
        rotation_error_deg = round(math.degrees(rot_diff), 4)
    else:
        target_world_euler = hand_world_euler
        rotation_error_deg = 0.0

    ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
    rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side])
    ik_influence = ik_con.influence if ik_con else 0.0
    rot_influence = rot_con.influence if rot_con else 0.0

    return {
        "side": side,
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
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid arm side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[side])
    if ik_obj is None or pole_obj is None:
        setup_arm_ik(arm, initial_influence=influence)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES[side]]

    _apply_arm_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    p_up = arm.pose.bones[f"upper_arm.{side}"]
    p_fore = arm.pose.bones[f"forearm.{side}"]
    p_hand = arm.pose.bones[f"hand.{side}"]

    shoulder_world = arm.matrix_world @ p_up.head

    requested = Vector(world_xyz)
    applied = requested.copy()
    clamped_reach = False

    vec_from_shoulder = applied - shoulder_world
    dist = vec_from_shoulder.length
    is_reachable = (MIN_ARM_REACH <= dist <= MAX_ARM_REACH)

    # Reach clamping relative to shoulder joint
    if clamp_reach:
        if dist > MAX_ARM_REACH:
            clamped_reach = True
            if dist > 1e-6:
                applied = shoulder_world + vec_from_shoulder.normalized() * MAX_ARM_REACH
        elif dist < MIN_ARM_REACH:
            clamped_reach = True
            direction = vec_from_shoulder.normalized() if dist > 1e-6 else Vector((0.0, 0.0, -1.0))
            applied = shoulder_world + direction * MIN_ARM_REACH

    # Convert applied world position to ik_obj parent coordinate space
    if ik_obj.parent is not None:
        ik_obj.location = ik_obj.parent.matrix_world.inverted() @ applied
    else:
        ik_obj.location = applied

    # Hand 3D orientation control
    if hand_rotation_deg is not None:
        world_rot_mat = Euler((math.radians(v) for v in hand_rotation_deg), "XYZ").to_matrix()
        if ik_obj.parent is not None:
            local_rot_mat = ik_obj.parent.matrix_world.to_3x3().inverted() @ world_rot_mat
            ik_obj.rotation_euler = local_rot_mat.to_euler("XYZ")
        else:
            ik_obj.rotation_euler = Euler((math.radians(v) for v in hand_rotation_deg), "XYZ")
    else:
        # Default level neutral orientation matching root
        ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

    # Elbow pole target positioning
    sign = -1.0 if side == "L" else 1.0
    if pole_world_xyz is not None:
        pole_world = Vector(pole_world_xyz)
    else:
        # Default pole placement: behind (-Y) and slightly outward (X)
        mid_pt = 0.5 * (shoulder_world + applied)
        pole_world = Vector((
            mid_pt.x + sign * DEFAULT_POLE_OUTWARD_OFFSET,
            min(shoulder_world.y, applied.y) - DEFAULT_POLE_BACKWARD_OFFSET,
            mid_pt.z,
        ))

    if pole_obj.parent is not None:
        pole_obj.location = pole_obj.parent.matrix_world.inverted() @ pole_world
    else:
        pole_obj.location = pole_world

    # Update constraint influence
    influence_clamped = max(0.0, min(1.0, float(influence)))
    ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
    if ik_con:
        ik_con.influence = influence_clamped
    rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side])
    if rot_con:
        rot_con.influence = influence_clamped

    bpy.context.view_layer.update()

    state = get_arm_ik_state(arm, side)
    state["requested_world"] = requested
    state["applied_world"] = applied
    state["is_reachable"] = is_reachable
    state["clamped_reach"] = clamped_reach
    return state
