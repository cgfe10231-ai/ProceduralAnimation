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
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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


def _find_collection_by_name(col_name: str) -> Optional[bpy.types.Collection]:
    """Resolve a collection by name across scene master collections and user collections."""
    if bpy.context.scene and bpy.context.scene.collection.name == col_name:
        return bpy.context.scene.collection
    for scene in bpy.data.scenes:
        if scene.collection.name == col_name:
            return scene.collection
    return bpy.data.collections.get(col_name)


# =============================================================================
# Production Transaction Snapshot, Rollback, and Verification Infrastructure
# =============================================================================

_FAULT_INJECTION_HOOK: Optional[Callable[[str, Dict[str, Any]], None]] = None


def set_fault_injection_hook(hook: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
    """Set internal hook callback for deterministic fault injection during tests."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = hook


def clear_fault_injection_hook() -> None:
    """Clear internal fault injection hook."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = None


def _trigger_fault_injection(stage: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Trigger internal fault injection if a hook is active."""
    global _FAULT_INJECTION_HOOK
    if _FAULT_INJECTION_HOOK is not None:
        _FAULT_INJECTION_HOOK(stage, context or {})


def _snapshot_arm_rig_state(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture full production state snapshot of Arm IK controllers, pose bones, constraints, and collections.

    Zero-mutation guarantee: Strictly inspects and copies properties without modifying Blender state.
    """
    # 1. Character Collection snapshot
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children
    char_col_data = {
        "existed": char_col is not None,
        "children_of_scene": (char_col is not None and char_col.name in scene_children),
        "object_names": set(char_col.objects.keys()) if char_col is not None else set(),
    }

    # 2. Controllers snapshot (HandIK.L/R, ElbowPole.L/R)
    ctrl_names = (
        ARM_IK_TARGET_NAMES["L"],
        ARM_IK_TARGET_NAMES["R"],
        ARM_POLE_TARGET_NAMES["L"],
        ARM_POLE_TARGET_NAMES["R"],
    )
    controllers_data: Dict[str, Dict[str, Any]] = {}
    for c_name in ctrl_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is None:
            controllers_data[c_name] = {"exists": False}
        else:
            controllers_data[c_name] = {
                "exists": True,
                "obj_ref": c_obj,
                "data_ref": getattr(c_obj, "data", None),
                "obj_name": c_obj.name,
                "type": c_obj.type,
                "parent": c_obj.parent,
                "matrix_parent_inverse": c_obj.matrix_parent_inverse.copy(),
                "location": c_obj.location.copy(),
                "rotation_mode": c_obj.rotation_mode,
                "rotation_euler": c_obj.rotation_euler.copy(),
                "rotation_quaternion": c_obj.rotation_quaternion.copy(),
                "rotation_axis_angle": list(c_obj.rotation_axis_angle),
                "scale": c_obj.scale.copy(),
                "matrix_world": c_obj.matrix_world.copy(),
                "empty_display_type": getattr(c_obj, "empty_display_type", None) if c_obj.type == "EMPTY" else None,
                "empty_display_size": getattr(c_obj, "empty_display_size", None) if c_obj.type == "EMPTY" else None,
                "collections": [c.name for c in c_obj.users_collection],
            }

    # 3. Pose bones snapshot (upper_arm, forearm, hand across L and R)
    bone_names = (
        "upper_arm.L", "upper_arm.R",
        "forearm.L", "forearm.R",
        "hand.L", "hand.R",
    )
    pose_bones_data: Dict[str, Dict[str, Any]] = {}
    for b_name in bone_names:
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        con_list: List[Dict[str, Any]] = []
        for con in pbone.constraints:
            c_dict: Dict[str, Any] = {
                "name": con.name,
                "type": con.type,
                "influence": float(con.influence),
                "mute": bool(con.mute),
            }
            if con.type == "IK":
                c_dict.update({
                    "target": con.target,
                    "subtarget": getattr(con, "subtarget", ""),
                    "pole_target": getattr(con, "pole_target", None),
                    "pole_subtarget": getattr(con, "pole_subtarget", ""),
                    "chain_count": getattr(con, "chain_count", 0),
                    "use_tail": getattr(con, "use_tail", True),
                    "use_stretch": getattr(con, "use_stretch", False),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": getattr(con, "iterations", 500),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
                    "target": con.target,
                    "subtarget": getattr(con, "subtarget", ""),
                    "target_space": getattr(con, "target_space", "WORLD"),
                    "owner_space": getattr(con, "owner_space", "WORLD"),
                    "mix_mode": getattr(con, "mix_mode", "REPLACE"),
                    "use_x": getattr(con, "use_x", True),
                    "use_y": getattr(con, "use_y", True),
                    "use_z": getattr(con, "use_z", True),
                    "invert_x": getattr(con, "invert_x", False),
                    "invert_y": getattr(con, "invert_y", False),
                    "invert_z": getattr(con, "invert_z", False),
                    "use_offset": getattr(con, "use_offset", False),
                })
            con_list.append(c_dict)

        pose_bones_data[b_name] = {
            "name": b_name,
            "location": pbone.location.copy(),
            "rotation_mode": pbone.rotation_mode,
            "rotation_euler": pbone.rotation_euler.copy(),
            "rotation_quaternion": pbone.rotation_quaternion.copy(),
            "rotation_axis_angle": list(pbone.rotation_axis_angle),
            "scale": pbone.scale.copy(),
            "matrix_basis": pbone.matrix_basis.copy(),
            "lock_ik_x": bool(pbone.lock_ik_x),
            "lock_ik_y": bool(pbone.lock_ik_y),
            "lock_ik_z": bool(pbone.lock_ik_z),
            "use_ik_limit_x": bool(pbone.use_ik_limit_x),
            "use_ik_limit_y": bool(pbone.use_ik_limit_y),
            "use_ik_limit_z": bool(pbone.use_ik_limit_z),
            "ik_min_x": float(pbone.ik_min_x),
            "ik_max_x": float(pbone.ik_max_x),
            "ik_min_y": float(pbone.ik_min_y),
            "ik_max_y": float(pbone.ik_max_y),
            "ik_min_z": float(pbone.ik_min_z),
            "ik_max_z": float(pbone.ik_max_z),
            "constraints": con_list,
        }

    return {
        "character_collection": char_col_data,
        "controllers": controllers_data,
        "pose_bones": pose_bones_data,
    }


def _rollback_arm_rig_state(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Restore the Arm IK rig state precisely to the recorded snapshot."""
    controllers_snap = snapshot.get("controllers", {})

    # Step 1: Controller cleanup, stashed object restoration, and transform restoration
    for c_name, c_snap in controllers_snap.items():
        curr_obj = bpy.data.objects.get(c_name)

        if not c_snap["exists"]:
            if curr_obj is not None:
                bpy.data.objects.remove(curr_obj, do_unlink=True)
        else:
            orig_ref = c_snap.get("obj_ref")
            # If current object with c_name is not the original object reference (it was replaced)
            if curr_obj is not None and curr_obj != orig_ref:
                bpy.data.objects.remove(curr_obj, do_unlink=True)

            if orig_ref is not None:
                # Restore original object name if it was stashed
                if orig_ref.name != c_snap["obj_name"]:
                    orig_ref.name = c_snap["obj_name"]

                # Ensure linked back to original collections
                for col_name in c_snap.get("collections", []):
                    col = _find_collection_by_name(col_name)
                    if col is not None and orig_ref.name not in col.objects:
                        col.objects.link(orig_ref)

                # Unlink from any collection it was not originally in
                for col in list(orig_ref.users_collection):
                    if col.name not in c_snap.get("collections", []):
                        col.objects.unlink(orig_ref)

                # Restore transforms, parents, display settings
                orig_ref.parent = c_snap["parent"]
                orig_ref.matrix_parent_inverse = c_snap["matrix_parent_inverse"].copy()
                orig_ref.rotation_mode = c_snap["rotation_mode"]
                orig_ref.location = c_snap["location"].copy()
                orig_ref.rotation_euler = c_snap["rotation_euler"].copy()
                orig_ref.rotation_quaternion = c_snap["rotation_quaternion"].copy()
                orig_ref.rotation_axis_angle = tuple(c_snap["rotation_axis_angle"])
                orig_ref.scale = c_snap["scale"].copy()
                if orig_ref.type == "EMPTY":
                    if c_snap.get("empty_display_type") is not None:
                        orig_ref.empty_display_type = c_snap["empty_display_type"]
                    if c_snap.get("empty_display_size") is not None:
                        orig_ref.empty_display_size = c_snap["empty_display_size"]

    # Step 2: Pose bones restoration
    pose_bones_snap = snapshot.get("pose_bones", {})
    for b_name, b_snap in pose_bones_snap.items():
        pbone = arm.pose.bones.get(b_name)
        if pbone is None:
            continue

        pbone.rotation_mode = b_snap["rotation_mode"]
        pbone.location = b_snap["location"].copy()
        pbone.rotation_euler = b_snap["rotation_euler"].copy()
        pbone.rotation_quaternion = b_snap["rotation_quaternion"].copy()
        pbone.rotation_axis_angle = tuple(b_snap["rotation_axis_angle"])
        pbone.scale = b_snap["scale"].copy()
        pbone.matrix_basis = b_snap["matrix_basis"].copy()

        pbone.lock_ik_x = b_snap["lock_ik_x"]
        pbone.lock_ik_y = b_snap["lock_ik_y"]
        pbone.lock_ik_z = b_snap["lock_ik_z"]
        pbone.use_ik_limit_x = b_snap["use_ik_limit_x"]
        pbone.use_ik_limit_y = b_snap["use_ik_limit_y"]
        pbone.use_ik_limit_z = b_snap["use_ik_limit_z"]
        pbone.ik_min_x = b_snap["ik_min_x"]
        pbone.ik_max_x = b_snap["ik_max_x"]
        pbone.ik_min_y = b_snap["ik_min_y"]
        pbone.ik_max_y = b_snap["ik_max_y"]
        pbone.ik_min_z = b_snap["ik_min_z"]
        pbone.ik_max_z = b_snap["ik_max_z"]

        # Step 3: Constraints restoration
        saved_cons = b_snap.get("constraints", [])
        saved_names = [c["name"] for c in saved_cons]
        curr_names = [c.name for c in pbone.constraints]

        if curr_names != saved_names:
            for con in list(pbone.constraints):
                pbone.constraints.remove(con)
            for sc in saved_cons:
                new_c = pbone.constraints.new(type=sc["type"])
                new_c.name = sc["name"]

        for sc in saved_cons:
            con = pbone.constraints.get(sc["name"])
            if con is None or con.type != sc["type"]:
                if con is not None:
                    pbone.constraints.remove(con)
                con = pbone.constraints.new(type=sc["type"])
                con.name = sc["name"]
            con.influence = sc["influence"]
            con.mute = sc["mute"]
            if con.type == "IK":
                con.target = sc.get("target")
                con.subtarget = sc.get("subtarget", "")
                con.pole_target = sc.get("pole_target")
                con.pole_subtarget = sc.get("pole_subtarget", "")
                con.chain_count = sc.get("chain_count", 0)
                con.use_tail = sc.get("use_tail", True)
                con.use_stretch = sc.get("use_stretch", False)
                con.pole_angle = sc.get("pole_angle", 0.0)
                con.iterations = sc.get("iterations", 500)
            elif con.type == "COPY_ROTATION":
                con.target = sc.get("target")
                con.subtarget = sc.get("subtarget", "")
                con.target_space = sc.get("target_space", "WORLD")
                con.owner_space = sc.get("owner_space", "WORLD")
                con.mix_mode = sc.get("mix_mode", "REPLACE")
                con.use_x = sc.get("use_x", True)
                con.use_y = sc.get("use_y", True)
                con.use_z = sc.get("use_z", True)
                con.invert_x = sc.get("invert_x", False)
                con.invert_y = sc.get("invert_y", False)
                con.invert_z = sc.get("invert_z", False)
                con.use_offset = sc.get("use_offset", False)

    # Step 4: Character Collection restoration
    char_col_snap = snapshot.get("character_collection", {})
    if not char_col_snap.get("existed", False):
        col = bpy.data.collections.get("Character")
        if col is not None:
            for child in list(bpy.context.scene.collection.children):
                if child == col:
                    bpy.context.scene.collection.children.unlink(col)
            bpy.data.collections.remove(col)
    else:
        col = bpy.data.collections.get("Character")
        if col is not None:
            expected_objs = char_col_snap.get("object_names", set())
            for o in list(col.objects):
                if o.name not in expected_objs:
                    col.objects.unlink(o)
            for o_name in expected_objs:
                o = bpy.data.objects.get(o_name)
                if o is not None and o.name not in col.objects:
                    col.objects.link(o)

    bpy.context.view_layer.update()


def _verify_arm_rig_state_restored(arm: bpy.types.Object, snapshot: Dict[str, Any]) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot.

    Raises:
        RuntimeError: If any discrepancy is detected between current state and snapshot.
    """
    current = _snapshot_arm_rig_state(arm)
    diffs: List[str] = []

    # 1. Collection check
    s_col = snapshot.get("character_collection", {})
    c_col = current.get("character_collection", {})
    if s_col.get("existed") != c_col.get("existed"):
        diffs.append(f"Character collection existed={c_col.get('existed')}, expected {s_col.get('existed')}")
    elif s_col.get("existed"):
        if s_col.get("object_names") != c_col.get("object_names"):
            diffs.append(f"Character collection members {c_col.get('object_names')} != {s_col.get('object_names')}")

    # 2. Controllers check
    s_ctrls = snapshot.get("controllers", {})
    c_ctrls = current.get("controllers", {})
    for c_name, sc in s_ctrls.items():
        cc = c_ctrls.get(c_name)
        if cc is None or sc["exists"] != cc["exists"]:
            diffs.append(f"Controller {c_name} exists={getattr(cc, 'get', lambda k: None)('exists')}, expected {sc['exists']}")
            continue
        if not sc["exists"]:
            continue

        if sc["obj_ref"] != cc["obj_ref"]:
            diffs.append(f"Controller {c_name} obj_ref identity mismatch")
        if sc["data_ref"] != cc["data_ref"]:
            diffs.append(f"Controller {c_name} data_ref identity mismatch")
        if sc["obj_name"] != cc["obj_name"]:
            diffs.append(f"Controller {c_name} obj_name {cc['obj_name']} != {sc['obj_name']}")
        if sc["type"] != cc["type"]:
            diffs.append(f"Controller {c_name} type {cc['type']} != {sc['type']}")
        if sc["parent"] != cc["parent"]:
            diffs.append(f"Controller {c_name} parent {cc['parent']} != {sc['parent']}")
        if sc["rotation_mode"] != cc["rotation_mode"]:
            diffs.append(f"Controller {c_name} rotation_mode {cc['rotation_mode']} != {sc['rotation_mode']}")
        if (sc["location"] - cc["location"]).length > 1e-5:
            diffs.append(f"Controller {c_name} location {cc['location']} != {sc['location']}")
        if (sc["scale"] - cc["scale"]).length > 1e-5:
            diffs.append(f"Controller {c_name} scale {cc['scale']} != {sc['scale']}")
        if set(sc["collections"]) != set(cc["collections"]):
            diffs.append(f"Controller {c_name} collections {cc['collections']} != {sc['collections']}")
        if sc["type"] == "EMPTY":
            if sc["empty_display_type"] != cc["empty_display_type"]:
                diffs.append(f"Controller {c_name} empty_display_type {cc['empty_display_type']} != {sc['empty_display_type']}")
            if abs(sc["empty_display_size"] - cc["empty_display_size"]) > 1e-5:
                diffs.append(f"Controller {c_name} empty_display_size {cc['empty_display_size']} != {sc['empty_display_size']}")

    # 3. Pose bones check
    s_bones = snapshot.get("pose_bones", {})
    c_bones = current.get("pose_bones", {})
    for b_name, sb in s_bones.items():
        cb = c_bones.get(b_name)
        if cb is None:
            diffs.append(f"Pose bone {b_name} missing in current state")
            continue
        if sb["rotation_mode"] != cb["rotation_mode"]:
            diffs.append(f"Bone {b_name} rotation_mode {cb['rotation_mode']} != {sb['rotation_mode']}")
        if (sb["location"] - cb["location"]).length > 1e-5:
            diffs.append(f"Bone {b_name} location {cb['location']} != {sb['location']}")
        if (sb["scale"] - cb["scale"]).length > 1e-5:
            diffs.append(f"Bone {b_name} scale {cb['scale']} != {sb['scale']}")

        for axis in ("x", "y", "z"):
            if sb[f"lock_ik_{axis}"] != cb[f"lock_ik_{axis}"]:
                diffs.append(f"Bone {b_name} lock_ik_{axis} {cb[f'lock_ik_{axis}']} != {sb[f'lock_ik_{axis}']}")
            if sb[f"use_ik_limit_{axis}"] != cb[f"use_ik_limit_{axis}"]:
                diffs.append(f"Bone {b_name} use_ik_limit_{axis} {cb[f'use_ik_limit_{axis}']} != {sb[f'use_ik_limit_{axis}']}")
            if abs(sb[f"ik_min_{axis}"] - cb[f"ik_min_{axis}"]) > 1e-5:
                diffs.append(f"Bone {b_name} ik_min_{axis} {cb[f'ik_min_{axis}']} != {sb[f'ik_min_{axis}']}")
            if abs(sb[f"ik_max_{axis}"] - cb[f"ik_max_{axis}"]) > 1e-5:
                diffs.append(f"Bone {b_name} ik_max_{axis} {cb[f'ik_max_{axis}']} != {sb[f'ik_max_{axis}']}")

        # Constraints
        sc_list = sb["constraints"]
        cc_list = cb["constraints"]
        if len(sc_list) != len(cc_list):
            diffs.append(f"Bone {b_name} constraint count {len(cc_list)} != {len(sc_list)}")
        else:
            for idx, (sc, cc) in enumerate(zip(sc_list, cc_list)):
                if sc["name"] != cc["name"]:
                    diffs.append(f"Bone {b_name} constraint {idx} name {cc['name']} != {sc['name']}")
                if sc["type"] != cc["type"]:
                    diffs.append(f"Bone {b_name} constraint {idx} type {cc['type']} != {sc['type']}")
                if abs(sc["influence"] - cc["influence"]) > 1e-5:
                    diffs.append(f"Bone {b_name} constraint {idx} influence {cc['influence']} != {sc['influence']}")
                if sc["mute"] != cc["mute"]:
                    diffs.append(f"Bone {b_name} constraint {idx} mute {cc['mute']} != {sc['mute']}")
                if sc.get("target") != cc.get("target"):
                    diffs.append(f"Bone {b_name} constraint {idx} target {cc.get('target')} != {sc.get('target')}")
                if sc.get("pole_target") != cc.get("pole_target"):
                    diffs.append(f"Bone {b_name} constraint {idx} pole_target {cc.get('pole_target')} != {sc.get('pole_target')}")

    if diffs:
        raise RuntimeError("Arm rig rollback verification failed: " + "; ".join(diffs))


class _ArmRigTransactionContext:
    """Active transaction execution state tracking."""

    def __init__(self, arm: bpy.types.Object):
        self.arm = arm
        self.snapshot: Optional[Dict[str, Any]] = None
        self.stashed_objects: List[Dict[str, Any]] = []
        self.committed: bool = False


_ACTIVE_TRANSACTION_STACK: List[_ArmRigTransactionContext] = []


@contextmanager
def _arm_rig_transaction(arm: bpy.types.Object):
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    global _ACTIVE_TRANSACTION_STACK
    if _ACTIVE_TRANSACTION_STACK:
        # Re-entrant invocation: outer transaction retains exclusive ownership
        yield _ACTIVE_TRANSACTION_STACK[-1]
        return

    tx = _ArmRigTransactionContext(arm)
    _ACTIVE_TRANSACTION_STACK.append(tx)
    tx.snapshot = _snapshot_arm_rig_state(arm)

    try:
        yield tx
        # Commit Phase: permanently remove stashed doomed objects
        for stashed in tx.stashed_objects:
            obj = stashed["stashed_obj"]
            mesh_data = stashed.get("stashed_data")
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            if mesh_data is not None and hasattr(bpy.data, "meshes") and mesh_data.name in bpy.data.meshes:
                if mesh_data.users == 0:
                    bpy.data.meshes.remove(mesh_data, do_unlink=True)
        tx.committed = True
    except BaseException as orig_exc:
        # Phase E: Failure Rollback & Verification
        rollback_err = None
        try:
            _rollback_arm_rig_state(arm, tx.snapshot, tx)
            bpy.context.view_layer.update()
            _trigger_fault_injection("during_rollback_verification", {"arm": arm})
            _verify_arm_rig_state_restored(arm, tx.snapshot)
        except BaseException as rb_exc:
            rollback_err = rb_exc

        if rollback_err is not None:
            raise RuntimeError(
                f"Arm rig transaction failed with {type(orig_exc).__name__}: {orig_exc}, "
                f"AND rollback verification failed with {type(rollback_err).__name__}: {rollback_err}"
            ) from orig_exc
        else:
            raise
    finally:
        _ACTIVE_TRANSACTION_STACK.pop()


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
    global _ACTIVE_TRANSACTION_STACK
    obj = bpy.data.objects.get(name)
    replaced_wrong_type = False

    if obj is not None and obj.type != "EMPTY":
        if _ACTIVE_TRANSACTION_STACK:
            # Active transaction: safely stash the doomed wrong-type object to allow complete rollback
            tx = _ACTIVE_TRANSACTION_STACK[-1]
            stashed_record = {
                "original_name": name,
                "stashed_obj": obj,
                "stashed_data": getattr(obj, "data", None),
                "collections": [c.name for c in obj.users_collection],
            }
            tx.stashed_objects.append(stashed_record)
            obj.name = f"__stashed_doomed_{name}__"
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            obj = None
            replaced_wrong_type = True
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
            obj = None
            replaced_wrong_type = True

    if obj is None:
        obj = bpy.data.objects.new(name, None)
        collection.objects.link(obj)
        obj.empty_display_type = display_type
        obj.empty_display_size = display_size
        obj.rotation_mode = "XYZ"
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = Matrix.Identity(4)
        if replaced_wrong_type:
            _trigger_fault_injection("setup_arm_ik_after_controller_replaced", {"obj": obj, "name": name})
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

    with _arm_rig_transaction(arm):
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
            if ik_is_new and side == "L":
                _trigger_fault_injection("setup_arm_ik_after_first_controller", {"ik_obj": ik_obj})
                _trigger_fault_injection("set_hand_ik_target_during_auto_init", {"ik_obj": ik_obj})

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

            _trigger_fault_injection("setup_arm_ik_after_constraints_or_prebend", {"side": side, "arm": arm})

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

    with _arm_rig_transaction(arm):
        for s in sides:
            p_fore = arm.pose.bones.get(f"forearm.{s}")
            p_hand = arm.pose.bones.get(f"hand.{s}")
            if p_fore and ARM_IK_CONSTRAINT_NAMES[s] in p_fore.constraints:
                p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[s]].influence = valid_influence
            _trigger_fault_injection("set_arm_ik_influence_between_influences", {"side": s})
            if p_hand and HAND_ROT_CONSTRAINT_NAMES[s] in p_hand.constraints:
                p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[s]].influence = valid_influence
            if valid_side == "BOTH" and s == "L":
                _trigger_fault_injection("set_arm_ik_influence_between_sides", {"side": s})

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


def _preflight_arm_ik_parent_transforms(
    arm: bpy.types.Object,
    valid_side: str,
    root_obj: Optional[bpy.types.Object],
) -> Tuple[bool, Matrix, Matrix]:
    """Preflight check effective parent transform domains before any scene mutation (Task 10-B-2 & 10-B-3).

    Inspects existing and anticipated arm IK controllers without writing to the scene.
    A controller is valid if and only if the object exists and its type is 'EMPTY'.
    If any controller on valid_side is missing or not an EMPTY, setup_arm_ik() will be required.

    Preflight rules:
    - Case A: Existing object is an EMPTY -> compute actual effective parent matrix.
    - Case B: Object does not exist -> compute expected effective parent matrix (root_obj @ Identity).
    - Case C: Object exists but type != 'EMPTY' -> it will be unlinked and recreated by _get_or_create_empty();
      anticipate the expected effective parent matrix for the new EMPTY, NOT the doomed object's matrix.

    Returns:
        (needs_auto_init, eff_ik_mat, eff_pole_mat)
    """
    ik_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES[valid_side])
    pole_obj = bpy.data.objects.get(ARM_POLE_TARGET_NAMES[valid_side])
    ik_valid = (ik_obj is not None and ik_obj.type == "EMPTY")
    pole_valid = (pole_obj is not None and pole_obj.type == "EMPTY")
    needs_auto_init = not (ik_valid and pole_valid)

    expected_new_eff_mat = (
        root_obj.matrix_world @ Matrix.Identity(4)
        if root_obj is not None
        else Matrix.Identity(4)
    )

    if needs_auto_init:
        # setup_arm_ik() processes all four controllers (L and R);
        # validate effective parent transforms for existing valid controls and anticipated new controls.
        other_side = "R" if valid_side == "L" else "L"
        all_ctrl_names = (
            ARM_IK_TARGET_NAMES[valid_side],
            ARM_POLE_TARGET_NAMES[valid_side],
            ARM_IK_TARGET_NAMES[other_side],
            ARM_POLE_TARGET_NAMES[other_side],
        )
        for ctrl_name in all_ctrl_names:
            existing_obj = bpy.data.objects.get(ctrl_name)
            if existing_obj is not None and existing_obj.type == "EMPTY":
                # Case A: Existing valid EMPTY controller
                ctrl_eff_mat = compute_effective_parent_matrix(existing_obj)
            else:
                # Case B (missing) & Case C (wrong type, will be unlinked/recreated):
                # Use expected effective parent matrix for the new Empty
                ctrl_eff_mat = expected_new_eff_mat
            validate_effective_parent_transform(ctrl_eff_mat, ctrl_name)

        eff_ik_mat = (
            compute_effective_parent_matrix(ik_obj)
            if ik_valid
            else expected_new_eff_mat
        )
        eff_pole_mat = (
            compute_effective_parent_matrix(pole_obj)
            if pole_valid
            else expected_new_eff_mat
        )
    else:
        # Both target controllers exist and are valid EMPTY objects; validate their transforms directly
        eff_ik_mat = compute_effective_parent_matrix(ik_obj)
        eff_pole_mat = compute_effective_parent_matrix(pole_obj)
        validate_effective_parent_transform(eff_ik_mat, ik_obj.name)
        validate_effective_parent_transform(eff_pole_mat, pole_obj.name)

    return needs_auto_init, eff_ik_mat, eff_pole_mat


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
    bpy.context.view_layer.update()
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")

    needs_auto_init, eff_ik_mat, eff_pole_mat = _preflight_arm_ik_parent_transforms(
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
    with _arm_rig_transaction(arm):
        if needs_auto_init:
            setup_arm_ik(arm, initial_influence=valid_influence)

        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES[valid_side]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES[valid_side]]

        _apply_arm_ik_prebend_hint_side(arm, valid_side)

        # Convert applied world targets to controller local spaces preserving rotation_mode
        ik_obj.location = ik_local_pos
        _trigger_fault_injection("set_hand_ik_target_after_hand_location", {"ik_obj": ik_obj})

        apply_target_rotation(ik_obj, target_world_rot_quat, eff_ik_mat)
        _trigger_fault_injection("set_hand_ik_target_after_hand_rotation", {"ik_obj": ik_obj})

        pole_obj.location = pole_local_pos
        _trigger_fault_injection("set_hand_ik_target_after_pole_location", {"pole_obj": pole_obj})

        # Update constraint influence
        ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[valid_side])
        if ik_con:
            ik_con.influence = valid_influence
        _trigger_fault_injection("set_hand_ik_target_between_influences", {"ik_con": ik_con})

        rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[valid_side])
        if rot_con:
            rot_con.influence = valid_influence
        _trigger_fault_injection("set_hand_ik_target_after_rot_influence", {"rot_con": rot_con})

        bpy.context.view_layer.update()

        _trigger_fault_injection("set_hand_ik_target_during_state_read", {"arm": arm})
        state = get_arm_ik_state(arm, valid_side)
        state["requested_world"] = requested
        state["applied_world"] = applied
        state["is_reachable"] = is_reachable
        state["clamped_reach"] = clamped_reach

    return state
