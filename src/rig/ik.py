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
    else:
        if obj.parent is not None:
            obj.parent = None
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

    # Synchronize scene graph to evaluate CharacterRoot world matrix
    bpy.context.view_layer.update()
    root_mat = root_obj.matrix_world.copy() if root_obj is not None else Matrix.Identity(4)
    root_rot = root_mat.to_euler("XYZ")

    controls: Dict[str, bpy.types.Object] = {}

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_name = IK_TARGET_NAMES[side]
        pole_name = POLE_TARGET_NAMES[side]
        ik_obj = _get_or_create_empty(
            name=ik_name,
            display_type="CUBE",
            display_size=0.05,
            parent=None,
            collection=collection,
        )
        pole_obj = _get_or_create_empty(
            name=pole_name,
            display_type="SPHERE",
            display_size=0.04,
            parent=None,
            collection=collection,
        )

        # Explicitly ensure existing parented objects are unparented
        if ik_obj.parent is not None:
            ik_obj.parent = None
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        if pole_obj.parent is not None:
            pole_obj.parent = None
            pole_obj.matrix_parent_inverse = Matrix.Identity(4)

        # Set neutral rest positions transformed to World space
        ik_local = Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
        pole_local = Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

        ik_obj.location = root_mat @ ik_local
        ik_obj.rotation_euler = root_rot
        ik_obj["is_locked"] = False

        pole_obj.location = root_mat @ pole_local
        pole_obj.rotation_euler = root_rot

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
        rot_con.target_space = "WORLD"
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
    bpy.context.view_layer.update()
    root_mat = root_obj.matrix_world.copy() if root_obj is not None else Matrix.Identity(4)
    root_rot = root_mat.to_euler("XYZ")

    for side, sign in (("L", -1.0), ("R", 1.0)):
        ik_obj = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_obj = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_obj is not None:
            ik_obj["is_locked"] = False
            if ik_obj.parent is not None:
                ik_obj.parent = None
                ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            ik_local = Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            ik_obj.location = root_mat @ ik_local
            ik_obj.rotation_euler = root_rot
        if pole_obj is not None:
            if pole_obj.parent is not None:
                pole_obj.parent = None
                pole_obj.matrix_parent_inverse = Matrix.Identity(4)
            pole_local = Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))
            pole_obj.location = root_mat @ pole_local
            pole_obj.rotation_euler = root_rot

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
    ground_z: Optional[float] = None,
) -> dict:
    """Set the left ('L') or right ('R') foot IK target in world coordinates.

    Automatically clamps unreachable targets to `[MIN_LEG_REACH, MAX_LEG_REACH]` from
    the hip joint and prevents foot ground penetration (`Z >= ground_z + ANKLE_REST_Z`)
    when `clamp_ground=True`. When `ground_z` is None, defaults to historical flat ground
    at Z = 0.0m (decoupled from CharacterRoot elevation). Also positions the knee pole target
    strictly forward (+Y) of the hip-ankle plane to prevent knee flipping.
    """
    # =========================================================================
    # Phase A: Read / Resolve / Validate
    # =========================================================================
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    try:
        req_coords = (float(world_xyz[0]), float(world_xyz[1]), float(world_xyz[2]))
    except (TypeError, ValueError, IndexError) as exc:
        raise TypeError(f"world_xyz must be a sequence of 3 floats, got {world_xyz}") from exc

    if not (math.isfinite(req_coords[0]) and math.isfinite(req_coords[1]) and math.isfinite(req_coords[2])):
        raise ValueError(f"world_xyz coordinates must be finite numbers, got {world_xyz}")

    if ground_z is not None:
        try:
            effective_ground_z = float(ground_z)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"ground_z must be a float or None, got {type(ground_z).__name__}") from exc
        if not math.isfinite(effective_ground_z):
            raise ValueError(f"ground_z must be finite, got {ground_z}")
    else:
        effective_ground_z = 0.0

    rot_coords: Optional[Tuple[float, float, float]] = None
    if foot_rotation_deg is not None:
        try:
            rot_coords = (float(foot_rotation_deg[0]), float(foot_rotation_deg[1]), float(foot_rotation_deg[2]))
        except (TypeError, ValueError, IndexError) as exc:
            raise TypeError(f"foot_rotation_deg must be a sequence of 3 floats or None, got {foot_rotation_deg}") from exc
        if not (math.isfinite(rot_coords[0]) and math.isfinite(rot_coords[1]) and math.isfinite(rot_coords[2])):
            raise ValueError(f"foot_rotation_deg coordinates must be finite, got {foot_rotation_deg}")

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

    # Synchronize scene graph to evaluate CharacterRoot and armature pose bone transforms
    bpy.context.view_layer.update()

    p_thigh = arm.pose.bones[f"thigh.{side}"]
    hip_world = arm.matrix_world @ p_thigh.head
    if not (math.isfinite(hip_world.x) and math.isfinite(hip_world.y) and math.isfinite(hip_world.z)):
        raise RuntimeError(f"hip_world has non-finite coordinates: {hip_world}")

    min_ankle_z = effective_ground_z + ANKLE_REST_Z
    zeta_min = min_ankle_z - hip_world.z

    requested = Vector(req_coords)
    vec_from_hip = requested - hip_world
    dist_req = vec_from_hip.length
    horiz_vec = Vector((vec_from_hip.x, vec_from_hip.y, 0.0))
    rho_r = horiz_vec.length
    z_r = vec_from_hip.z

    TOL = 1e-6

    # =========================================================================
    # Constraint Resolution
    # =========================================================================
    if not clamp_reach and not clamp_ground:
        # Mode A: Both constraints disabled -> strictly unchanged
        applied = requested.copy()
        clamped_reach = False
        clamped_ground = False
        constraints_satisfied = True

    elif clamp_ground and not clamp_reach:
        # Mode B: Only Ground enabled -> reach never restricted
        applied = requested.copy()
        clamped_reach = False
        if applied.z < min_ankle_z:
            applied.z = min_ankle_z
            clamped_ground = True
        else:
            clamped_ground = False
        constraints_satisfied = (applied.z >= min_ankle_z - 1e-5)

    elif clamp_reach and not clamp_ground:
        # Mode C: Only Reach enabled -> ground never restricted
        clamped_ground = False
        if MIN_LEG_REACH - TOL <= dist_req <= MAX_LEG_REACH + TOL:
            applied = requested.copy()
            clamped_reach = False
        elif dist_req > MAX_LEG_REACH + TOL:
            clamped_reach = True
            if dist_req > TOL:
                applied = hip_world + (vec_from_hip / dist_req) * MAX_LEG_REACH
            else:
                applied = hip_world + Vector((0.0, 0.0, -1.0)) * MAX_LEG_REACH
        elif dist_req < MIN_LEG_REACH - TOL:
            clamped_reach = True
            if dist_req > TOL:
                applied = hip_world + (vec_from_hip / dist_req) * MIN_LEG_REACH
            else:
                applied = hip_world + Vector((0.0, 0.0, -1.0)) * MIN_LEG_REACH
        else:
            applied = requested.copy()
            clamped_reach = False

        final_dist = (applied - hip_world).length
        constraints_satisfied = (MIN_LEG_REACH - 1e-4 <= final_dist <= MAX_LEG_REACH + 1e-4)

    else:
        # Mode D: Both clamp_reach and clamp_ground enabled (joint optimal projection)
        # ---------------------------------------------------------------------
        # CASE-1: Feasibility Check (zeta_min > MAX_LEG_REACH + TOL)
        # ---------------------------------------------------------------------
        if zeta_min > MAX_LEG_REACH + TOL:
            raise ValueError(
                f"GROUND_REACH_INFEASIBLE: min_ankle_z ({min_ankle_z:.6f}m) exceeds "
                f"hip_world.z ({hip_world.z:.6f}m) + MAX_LEG_REACH ({MAX_LEG_REACH:.6f}m). "
                f"Requested: {tuple(requested)}, hip: {tuple(hip_world)}, "
                f"min_ankle_z: {min_ankle_z:.6f}, actual distance: {dist_req:.6f}, "
                f"MIN_LEG_REACH: {MIN_LEG_REACH:.6f}, MAX_LEG_REACH: {MAX_LEG_REACH:.6f}, "
                f"clamp_reach={clamp_reach}, clamp_ground={clamp_ground}"
            )

        # CASE-2: Tangent to top apex (|zeta_min - MAX_LEG_REACH| <= TOL)
        if abs(zeta_min - MAX_LEG_REACH) <= TOL:
            applied = hip_world + Vector((0.0, 0.0, MAX_LEG_REACH))
            clamped_ground = abs(applied.z - requested.z) > 1e-6
            clamped_reach = abs((applied - hip_world).length - dist_req) > 1e-6
            constraints_satisfied = True

        # CASE-5: Ground is strictly below the entire outer sphere (zeta_min < -MAX_LEG_REACH - TOL)
        elif zeta_min < -MAX_LEG_REACH - TOL:
            # Ground constraint imposes zero restriction on the reach shell. Degenerates to Reach-only.
            if MIN_LEG_REACH - TOL <= dist_req <= MAX_LEG_REACH + TOL:
                applied = requested.copy()
                clamped_reach = False
            elif dist_req > MAX_LEG_REACH + TOL:
                clamped_reach = True
                applied = hip_world + (vec_from_hip / dist_req) * MAX_LEG_REACH if dist_req > TOL else hip_world + Vector((0.0, 0.0, -1.0)) * MAX_LEG_REACH
            else:
                clamped_reach = True
                applied = hip_world + (vec_from_hip / dist_req) * MIN_LEG_REACH if dist_req > TOL else hip_world + Vector((0.0, 0.0, -1.0)) * MIN_LEG_REACH
            clamped_ground = False
            constraints_satisfied = True

        # Check if requested is already strictly inside the feasible set
        elif requested.z >= min_ankle_z - TOL and MIN_LEG_REACH - TOL <= dist_req <= MAX_LEG_REACH + TOL:
            applied = requested.copy()
            clamped_reach = False
            clamped_ground = False
            constraints_satisfied = True

        else:
            # Deterministic unit horizontal direction from hip
            if rho_r > 1e-6:
                u_horiz = horiz_vec / rho_r
            else:
                u_horiz = Vector((0.0, 1.0, 0.0))

            # Outer ground intersection radius (交圆真实存在或在数值公差内相切判定)
            if -MAX_LEG_REACH - TOL <= zeta_min <= MAX_LEG_REACH + TOL:
                rho_ground_max = math.sqrt(max(0.0, MAX_LEG_REACH * MAX_LEG_REACH - zeta_min * zeta_min))
            else:
                rho_ground_max = 0.0

            # Inner ground intersection radius
            if -MIN_LEG_REACH - TOL <= zeta_min <= MIN_LEG_REACH + TOL:
                rho_ground_min = math.sqrt(max(0.0, MIN_LEG_REACH * MIN_LEG_REACH - zeta_min * zeta_min))
            else:
                rho_ground_min = 0.0

            # Collect candidate points (rho, z) relative to hip
            candidates: List[Tuple[float, float, str]] = []

            # Candidate 1: Ground line segment [rho_ground_min, rho_ground_max] at z = zeta_min
            rho_c1 = max(rho_ground_min, min(rho_ground_max, rho_r))
            candidates.append((rho_c1, zeta_min, "ground_segment"))

            # Candidate 2: Outer circle arc r = MAX_LEG_REACH with z >= zeta_min
            if dist_req > TOL:
                rho_c2 = MAX_LEG_REACH * (rho_r / dist_req)
                z_c2 = MAX_LEG_REACH * (z_r / dist_req)
            else:
                rho_c2 = 0.0
                z_c2 = MAX_LEG_REACH if zeta_min <= MAX_LEG_REACH else -MAX_LEG_REACH

            if z_c2 >= zeta_min - TOL:
                z_c2_clean = max(zeta_min, z_c2)
                candidates.append((rho_c2, z_c2_clean, "outer_arc"))

            # Candidate 3: Inner circle arc r = MIN_LEG_REACH with z >= zeta_min
            if zeta_min <= MIN_LEG_REACH + TOL:
                if dist_req > TOL:
                    rho_c3 = MIN_LEG_REACH * (rho_r / dist_req)
                    z_c3 = MIN_LEG_REACH * (z_r / dist_req)
                else:
                    if -MIN_LEG_REACH >= zeta_min - TOL:
                        rho_c3 = 0.0
                        z_c3 = -MIN_LEG_REACH
                    elif zeta_min <= 0:
                        rho_c3 = rho_ground_min
                        z_c3 = zeta_min
                    else:
                        rho_c3 = 0.0
                        z_c3 = MIN_LEG_REACH

                if z_c3 >= zeta_min - TOL:
                    z_c3_clean = max(zeta_min, z_c3)
                    candidates.append((rho_c3, z_c3_clean, "inner_arc"))

            # Evaluate best candidate by Euclidean distance to (rho_r, z_r)
            best_candidate: Optional[Tuple[float, float, str]] = None
            min_dist_sq = float('inf')

            for rho_c, z_c, tag in candidates:
                rho_clean = max(0.0, rho_c)
                z_clean = max(zeta_min, z_c)
                r_c = math.sqrt(rho_clean * rho_clean + z_clean * z_clean)

                if z_clean < zeta_min - 1e-5:
                    continue
                if r_c > MAX_LEG_REACH + 1e-5 or r_c < MIN_LEG_REACH - 1e-5:
                    continue

                d_sq = (rho_clean - rho_r) * (rho_clean - rho_r) + (z_clean - z_r) * (z_clean - z_r)
                if d_sq < min_dist_sq - 1e-9:
                    min_dist_sq = d_sq
                    best_candidate = (rho_clean, z_clean, tag)

            if best_candidate is None:
                raise RuntimeError(
                    f"GROUND_REACH_CONSTRAINT_UNSATISFIED: solver failed to find a feasible target. "
                    f"Requested: {tuple(requested)}, hip: {tuple(hip_world)}, "
                    f"min_ankle_z: {min_ankle_z:.6f}, actual distance: {dist_req:.6f}, "
                    f"MIN_LEG_REACH: {MIN_LEG_REACH:.6f}, MAX_LEG_REACH: {MAX_LEG_REACH:.6f}, "
                    f"clamp_reach={clamp_reach}, clamp_ground={clamp_ground}"
                )

            best_rho, best_z, _ = best_candidate
            applied = Vector((
                hip_world.x + u_horiz.x * best_rho,
                hip_world.y + u_horiz.y * best_rho,
                hip_world.z + best_z,
            ))

            final_dist = (applied - hip_world).length
            constraints_satisfied = (
                applied.z >= min_ankle_z - 1e-5
                and MIN_LEG_REACH - 1e-4 <= final_dist <= MAX_LEG_REACH + 1e-4
            )

            if not constraints_satisfied:
                raise RuntimeError(
                    f"GROUND_REACH_CONSTRAINT_UNSATISFIED: solver produced target violating constraints. "
                    f"Applied: {tuple(applied)}, final_dist: {final_dist:.6f}, z: {applied.z:.6f}, min_z: {min_ankle_z:.6f}. "
                    f"Requested: {tuple(requested)}, hip: {tuple(hip_world)}, "
                    f"MIN_LEG_REACH: {MIN_LEG_REACH:.6f}, MAX_LEG_REACH: {MAX_LEG_REACH:.6f}, "
                    f"clamp_reach={clamp_reach}, clamp_ground={clamp_ground}"
                )

            # Determine participation flags
            clamped_ground = abs(applied.z - requested.z) > 1e-6
            p_ground_only_z = max(requested.z, min_ankle_z)
            p_ground_only_dist = math.sqrt(rho_r * rho_r + (p_ground_only_z - hip_world.z) ** 2)
            clamped_reach = (
                (applied - Vector((requested.x, requested.y, p_ground_only_z))).length > 1e-6
                or dist_req > MAX_LEG_REACH + 1e-6
                or dist_req < MIN_LEG_REACH - 1e-6
                or p_ground_only_dist > MAX_LEG_REACH + 1e-6
                or p_ground_only_dist < MIN_LEG_REACH - 1e-6
            )

    # Compute truthfulness telemetry and constraint satisfaction flags
    final_dist = (applied - hip_world).length
    ground_clearance_m = applied.z - min_ankle_z
    hip_to_target_dist_m = final_dist

    if not (math.isfinite(applied.x) and math.isfinite(applied.y) and math.isfinite(applied.z)):
        raise RuntimeError(f"applied_world has non-finite coordinates: {applied}")

    # Keep knee pole target strictly forward (+Y) of both hip and foot target to prevent knee flip
    pole_world = Vector((
        hip_world.x,
        max(hip_world.y, applied.y) + POLE_FORWARD_OFFSET,
        0.5 * (hip_world.z + applied.z),
    ))
    if not (math.isfinite(pole_world.x) and math.isfinite(pole_world.y) and math.isfinite(pole_world.z)):
        raise RuntimeError(f"pole_world has non-finite coordinates: {pole_world}")

    # =========================================================================
    # Phase B: Commit
    # =========================================================================
    # Apply prebend hint and write targets only after successful feasibility check and clamping
    _apply_ik_prebend_hint(arm)

    # Convert applied world position to ik_obj parent space
    if ik_obj.parent is not None:
        ik_obj.location = ik_obj.parent.matrix_world.inverted() @ applied
    else:
        ik_obj.location = applied

    if rot_coords is not None:
        rx, ry, rz = (math.radians(v) for v in rot_coords)
        ik_obj.rotation_euler = Euler((rx, ry, rz), "XYZ")
    else:
        ik_obj.rotation_euler = Euler((0.0, 0.0, 0.0), "XYZ")

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
    state["ground_z"] = effective_ground_z
    state["constraints_satisfied"] = constraints_satisfied
    state["ground_clearance_m"] = ground_clearance_m
    state["hip_to_target_dist_m"] = hip_to_target_dist_m
    return state
