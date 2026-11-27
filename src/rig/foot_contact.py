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
    FOOT_LOCK_METADATA_KEYS,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    MIN_LEG_REACH,
    POLE_FORWARD_OFFSET,
    POLE_TARGET_NAMES,
    _apply_ik_prebend_hint,
    _resolve_armature,
    _rollback_leg_rig_state,
    _snapshot_leg_rig_state,
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
    # [INTRODUCED 2026-11-27T17:09:00+08:00]
    # BLOCK: lock_foot_contact full metadata rebuild and final lock publication
    # PURPOSE: Overwrite all 7 FOOT_LOCK_METADATA_KEYS from freshly computed world lock geometry before publishing is_locked=True.
    # REASON: TASK 11-A (FIND-R3-03) — guarantee stale snapshot values never mix into relock state and is_locked=True is published only after complete 7-field reconstruction.
    lock_metadata_payload = {
        "contact_world_xyz": tuple(float(v) for v in contact_world),
        "locked_ankle_world_xyz": tuple(float(v) for v in locked_ankle_world),
        "target_rotation_deg": tuple(float(v) for v in target_rotation_deg),
        "locked_foot_head_xyz": tuple(float(v) for v in foot_head_world),
        "locked_foot_tail_xyz": tuple(float(v) for v in foot_tail_world),
        "locked_foot_center_xyz": tuple(float(v) for v in foot_center_world),
        "locked_foot_min_z": float(foot_min_z),
    }
    for meta_key in FOOT_LOCK_METADATA_KEYS:
        ik_obj[meta_key] = lock_metadata_payload[meta_key]
    ik_obj["is_locked"] = True

    return evaluate_foot_support(arm, side)


def unlock_foot_contact(
    armature_obj: Optional[bpy.types.Object],
    side: str,
    reparent_to_root: bool = False,
) -> dict:
    """Release the support lock on the specified foot ('L' or 'R') and return it to normal IK control.

    In accordance with Architecture Invariant (Rule 7: controllers must remain parentless in world space),
    FootIK and KneePole controllers remain parentless (`parent is None`).
    If `reparent_to_root=True` is explicitly passed, raises ValueError.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    if reparent_to_root:
        raise ValueError(
            "reparent_to_root=True is forbidden: leg IK controllers must remain parentless in world space "
            "across their entire lifecycle (Rule 7 / FIND-R3-01)."
        )

    arm = _resolve_armature(armature_obj)
    ik_obj, pole_obj = _ensure_ik_controls(arm, side)
    bpy.context.view_layer.update()

    current_ik_world_mat = ik_obj.matrix_world.copy()
    current_pole_world_mat = pole_obj.matrix_world.copy()

    # Pre-validation: ensure all 16 elements are finite numbers
    for name, mat in [("ik_obj", current_ik_world_mat), ("pole_obj", current_pole_world_mat)]:
        for r in range(4):
            for c in range(4):
                val = mat[r][c]
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"{name} matrix_world element ({r}, {c}) is not finite: {val}")

    # Validate TRS representability (check for non-orthogonal shear)
    ik_loc, ik_rot_quat, ik_scale = current_ik_world_mat.decompose()
    ik_reconstructed = Matrix.LocRotScale(ik_loc, ik_rot_quat, ik_scale)
    max_ik_shear = max(abs(current_ik_world_mat[r][c] - ik_reconstructed[r][c]) for r in range(4) for c in range(4))
    if max_ik_shear > 1e-4:
        raise RuntimeError(
            f"ik_obj world matrix contains non-TRS shear (diff={max_ik_shear:.6f}) which cannot be faithfully represented by a parentless Blender object"
        )

    pole_loc, pole_rot_quat, pole_scale = current_pole_world_mat.decompose()
    pole_reconstructed = Matrix.LocRotScale(pole_loc, pole_rot_quat, pole_scale)
    max_pole_shear = max(abs(current_pole_world_mat[r][c] - pole_reconstructed[r][c]) for r in range(4) for c in range(4))
    if max_pole_shear > 1e-4:
        raise RuntimeError(
            f"pole_obj world matrix contains non-TRS shear (diff={max_pole_shear:.6f}) which cannot be faithfully represented by a parentless Blender object"
        )

    # Phase B transaction: capture pre-commit state of controllers and bones for failure rollback
    ctrl_snap, bone_snap = _snapshot_leg_rig_state(arm)

    try:
        ik_obj["is_locked"] = False
        # [INTRODUCED 2026-11-27T17:09:00+08:00]
        # BLOCK: unlock_foot_contact lock metadata cleanup
        # PURPOSE: Delete any existing 7 FootLock snapshot custom properties on FootIK.<side> inside the Phase B rollback-protected transaction.
        # REASON: TASK 11-A (FIND-R3-03) — eliminate stale lock snapshots on unlock, repeat unlock, or legacy unlocked controllers while preserving opposite-side state and 09-B-4 failure rollback.
        for meta_key in FOOT_LOCK_METADATA_KEYS:
            if meta_key in ik_obj:
                del ik_obj[meta_key]

        # Ensure parentless in world space with identity parent inverse and full TRS restoration
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        ik_obj.location = ik_loc
        ik_obj.rotation_euler = ik_rot_quat.to_euler("XYZ")
        ik_obj.scale = ik_scale

        pole_obj.parent = None
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        pole_obj.location = pole_loc
        pole_obj.rotation_euler = pole_rot_quat.to_euler("XYZ")
        pole_obj.scale = pole_scale

        bpy.context.view_layer.update()

        # Post-validation: ensure restored matrix_world matches original within 1e-4
        post_ik_diff = max(abs(ik_obj.matrix_world[r][c] - current_ik_world_mat[r][c]) for r in range(4) for c in range(4))
        if post_ik_diff > 1e-4:
            raise RuntimeError(f"unlock_foot_contact failed post-validation: ik_obj matrix_world drifted by {post_ik_diff:.6f}")

        post_pole_diff = max(abs(pole_obj.matrix_world[r][c] - current_pole_world_mat[r][c]) for r in range(4) for c in range(4))
        if post_pole_diff > 1e-4:
            raise RuntimeError(f"unlock_foot_contact failed post-validation: pole_obj matrix_world drifted by {post_pole_diff:.6f}")

        # [INTRODUCED 2026-11-27T17:20:00+08:00]
        # BLOCK: unlock_foot_contact explicit Phase B prebend & scene update
        # PURPOSE: Execute the historical leg IK prebend hint and dependency-graph update explicitly inside the Phase B rollback-protected transaction before the read-only final state query.
        # REASON: TASK 11-B (FIND-R3-04) — preserve unlock_foot_contact's solved pose contract and 09-B-4 rollback semantics after get_foot_support_state() becomes side-effect-free.
        _apply_ik_prebend_hint(arm)
        bpy.context.view_layer.update()

        return get_foot_support_state(arm, side)
    except Exception as exc:
        _rollback_leg_rig_state(arm, ctrl_snap, bone_snap, exc)


def evaluate_foot_support(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Actively maintain locked support transforms/knee pole alignment, update scene evaluation,
    and return the resulting support state for a foot ('L' or 'R').

    Never moves or clamps the locked `FootIK.<side>` point when locked.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_obj, pole_obj = _ensure_ik_controls(arm, side)

    is_locked = bool(ik_obj.get("is_locked", False))
    # [INTRODUCED 2026-11-27T17:20:00+08:00]
    # BLOCK: evaluate_foot_support pre-write lock snapshot gate and maintenance split
    # PURPOSE: Validate all 7 FOOT_LOCK_METADATA_KEYS via pure query before any prebend/controller write when locked, maintain locked FootIK/KneePole world state, and delegate final measurement to get_foot_support_state().
    # REASON: TASK 11-B (FIND-R3-04) — avoid duplicating metadata validation or support metric calculation and reject incomplete lock snapshots before writing support transforms.
    locked_ankle_world: Optional[Vector] = None
    target_rot_deg: Optional[Tuple[float, float, float]] = None
    if is_locked:
        pre_locked_state = get_foot_support_state(arm, side)
        locked_ankle_world = pre_locked_state["locked_ankle_world"].copy()
        rx_deg, ry_deg, rz_deg = pre_locked_state["target_rotation_deg"]
        target_rot_deg = (float(rx_deg), float(ry_deg), float(rz_deg))

    _apply_ik_prebend_hint(arm)
    bpy.context.view_layer.update()

    if is_locked:
        assert locked_ankle_world is not None and target_rot_deg is not None
        p_thigh = arm.pose.bones[f"thigh.{side}"]
        hip_world = arm.matrix_world @ p_thigh.head

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

    return get_foot_support_state(arm, side)


# [INTRODUCED 2026-11-27T17:20:00+08:00]
# FUNCTION: get_foot_support_state
# PURPOSE: Pure read-only foot support query reading current solved rig/mesh world transforms and computing reachability and drift metrics without initializing objects, mutating poses/controllers/parents/metadata, or refreshing the scene.
# REASON: TASK 11-B (FIND-R3-04) — separate side-effect-free telemetry queries from active support maintenance in evaluate_foot_support().
def get_foot_support_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Read current solved support state, reachability, and drift metrics for foot ('L' or 'R')
    without modifying objects, bones, constraints, custom properties, or refreshing the scene.
    """
    side = side.upper()
    if side not in ("L", "R"):
        raise ValueError(f"Invalid leg side '{side}', expected 'L' or 'R'")

    arm = _resolve_armature(armature_obj)
    ik_name = IK_TARGET_NAMES[side]
    pole_name = POLE_TARGET_NAMES[side]
    ik_obj = bpy.data.objects.get(ik_name)
    pole_obj = bpy.data.objects.get(pole_name)
    missing_controls = [
        name for name, obj in ((ik_name, ik_obj), (pole_name, pole_obj))
        if obj is None
    ]
    if missing_controls:
        raise KeyError(
            f"Missing required leg IK controller(s) for side '{side}': {', '.join(missing_controls)}"
        )

    assert ik_obj is not None and pole_obj is not None
    is_locked = bool(ik_obj.get("is_locked", False))

    if is_locked:
        parsed_lock_meta: Dict[str, object] = {}
        for meta_key in FOOT_LOCK_METADATA_KEYS:
            if meta_key not in ik_obj:
                raise ValueError(
                    f"Locked foot controller '{ik_name}' is missing required lock metadata '{meta_key}'"
                )
            raw_val = ik_obj[meta_key]
            if meta_key == "locked_foot_min_z":
                if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)):
                    raise ValueError(
                        f"Locked foot controller '{ik_name}' has invalid lock metadata '{meta_key}': expected finite number, got {type(raw_val).__name__}"
                    )
                fval = float(raw_val)
                if not math.isfinite(fval):
                    raise ValueError(
                        f"Locked foot controller '{ik_name}' has non-finite lock metadata '{meta_key}': {fval}"
                    )
                parsed_lock_meta[meta_key] = fval
            else:
                if hasattr(raw_val, "to_list"):
                    seq = raw_val.to_list()
                elif isinstance(raw_val, (list, tuple, Vector, Euler)):
                    seq = list(raw_val)
                else:
                    raise ValueError(
                        f"Locked foot controller '{ik_name}' has invalid lock metadata '{meta_key}': expected 3-element sequence, got {type(raw_val).__name__}"
                    )
                if len(seq) != 3:
                    raise ValueError(
                        f"Locked foot controller '{ik_name}' has invalid lock metadata '{meta_key}': expected length 3, got {len(seq)}"
                    )
                vals = []
                for elem in seq:
                    if isinstance(elem, bool) or not isinstance(elem, (int, float)):
                        raise ValueError(
                            f"Locked foot controller '{ik_name}' has non-numeric element in '{meta_key}': {elem!r}"
                        )
                    felem = float(elem)
                    if not math.isfinite(felem):
                        raise ValueError(
                            f"Locked foot controller '{ik_name}' has non-finite element in '{meta_key}': {felem}"
                        )
                    vals.append(felem)
                parsed_lock_meta[meta_key] = (vals[0], vals[1], vals[2])

        contact_world = Vector(parsed_lock_meta["contact_world_xyz"])
        locked_ankle_world = Vector(parsed_lock_meta["locked_ankle_world_xyz"])
        target_rot_deg = parsed_lock_meta["target_rotation_deg"]  # type: ignore[assignment]
        ref_head = Vector(parsed_lock_meta["locked_foot_head_xyz"])
        ref_tail = Vector(parsed_lock_meta["locked_foot_tail_xyz"])
        ref_center = Vector(parsed_lock_meta["locked_foot_center_xyz"])
    else:
        locked_ankle_world = ik_obj.matrix_world.translation.copy()
        contact_world = Vector((
            locked_ankle_world.x,
            locked_ankle_world.y,
            max(FLAT_GROUND_Z, locked_ankle_world.z - ANKLE_REST_Z),
        ))
        euler = ik_obj.matrix_world.to_euler("XYZ")
        target_rot_deg = (
            round(math.degrees(euler.x), 4),
            round(math.degrees(euler.y), 4),
            round(math.degrees(euler.z), 4),
        )

    ik_state = get_leg_ik_state(arm, side, update_scene=False)
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

    if is_locked:
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
