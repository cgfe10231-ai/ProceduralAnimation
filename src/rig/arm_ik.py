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
import uuid
from contextlib import contextmanager
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

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
        if _ACTIVE_TRANSACTION_STACK:
            _ACTIVE_TRANSACTION_STACK[-1].register_created_collection(col, initial_parent=scene.collection)
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

class _ArmRigTransactionState(str, Enum):
    """Explicit lifecycle state machine for Arm IK rig transactions."""
    CREATED = "CREATED"
    SNAPSHOTTING = "SNAPSHOTTING"
    ACTIVE = "ACTIVE"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    CLEANUP_PENDING = "CLEANUP_PENDING"
    FAILED = "FAILED"


_FAULT_INJECTION_HOOK: Optional[Callable[[str, Dict[str, Any]], None]] = None


def _set_test_fault_injection_hook(hook: Optional[Callable[[str, Dict[str, Any]], None]]) -> None:
    """Private test hook callback for deterministic fault injection during tests."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = hook


def _clear_test_fault_injection_hook() -> None:
    """Clear private internal test fault injection hook."""
    global _FAULT_INJECTION_HOOK
    _FAULT_INJECTION_HOOK = None


def _trigger_fault_injection(stage: str, context: Optional[Dict[str, Any]] = None) -> None:
    """Trigger internal fault injection if a hook is active."""
    global _FAULT_INJECTION_HOOK
    if _FAULT_INJECTION_HOOK is not None:
        _FAULT_INJECTION_HOOK(stage, context or {})


_DEPSGRAPH_UPDATER: Callable[[], None] = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


def _set_test_depsgraph_updater(updater: Optional[Callable[[], None]]) -> None:
    """Private test hook to replace or wrap depsgraph update execution at the boundary."""
    global _DEPSGRAPH_UPDATER
    if updater is None:
        _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None
    else:
        _DEPSGRAPH_UPDATER = updater


def _clear_test_depsgraph_updater() -> None:
    """Clear private test depsgraph updater hook."""
    global _DEPSGRAPH_UPDATER
    _DEPSGRAPH_UPDATER = lambda: bpy.context.view_layer.update() if (bpy.context and bpy.context.view_layer) else None


def _depsgraph_update() -> None:
    """Internal unified dependency graph update boundary."""
    _DEPSGRAPH_UPDATER()


def _update_arm_ik_depsgraph() -> None:
    """Synchronize the dependency graph for Arm IK calculations within mutations."""
    _trigger_fault_injection("set_hand_ik_target_during_depsgraph_update")
    _depsgraph_update()


def _clone_snapshot_property_value(val: Any) -> Any:
    """Safely clone an RNA property value into an immutable/independent snapshot representation."""
    if val is None:
        return None
    if isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, (Vector, Euler, Matrix, Quaternion)):
        return val.copy()
    if hasattr(val, "__len__") and hasattr(val, "__getitem__") and not isinstance(val, (str, bytes, dict)):
        # Convert RNA arrays and sequences into independent immutable tuples of cloned values
        return tuple(_clone_snapshot_property_value(elem) for elem in val)
    if isinstance(val, (bpy.types.Object, bpy.types.ID, bpy.types.bpy_struct)):
        # ID / StructRNA reference: keep reference, do not deepcopy Blender C data
        return val
    return val


def _snapshot_arm_rig_state(arm: bpy.types.Object) -> Dict[str, Any]:
    """Capture full production state snapshot of Arm IK controllers, pose bones, constraints, and collections.

    Zero-mutation guarantee: Strictly inspects and copies properties without modifying Blender state.
    """
    _trigger_fault_injection("during_snapshot_creation", {"arm": arm})
    _depsgraph_update()

    # 1. Collections snapshot
    char_col = bpy.data.collections.get("Character")
    scene_children = bpy.context.scene.collection.children if bpy.context.scene else []
    char_col_data = {
        "existed": char_col is not None,
        "col_ref": char_col,
        "col_ptr": char_col.as_pointer() if (char_col is not None and hasattr(char_col, "as_pointer")) else None,
        "name": char_col.name if char_col is not None else None,
        "children_of_scene": (char_col is not None and char_col.name in scene_children),
        "parent_collections": [c.name for c in bpy.data.collections if char_col is not None and char_col.name in c.children],
        "child_collections": [c.name for c in char_col.children] if char_col is not None else [],
        "object_names": set(char_col.objects.keys()) if char_col is not None else set(),
        "parent_refs": [
            parent
            for parent in bpy.data.collections
            if char_col is not None
            and any(child.as_pointer() == char_col.as_pointer() for child in parent.children)
        ],
        "child_refs": (
            list(char_col.children)
            if char_col is not None
            else []
        ),
        "object_refs": (
            list(char_col.objects)
            if char_col is not None
            else []
        ),
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
                "obj_ptr": c_obj.as_pointer() if hasattr(c_obj, "as_pointer") else None,
                "data_ref": getattr(c_obj, "data", None),
                "data_ptr": c_obj.data.as_pointer() if getattr(c_obj, "data", None) and hasattr(c_obj.data, "as_pointer") else None,
                "obj_name": c_obj.name,
                "type": c_obj.type,
                "parent": c_obj.parent,
                "matrix_parent_inverse": c_obj.matrix_parent_inverse.copy(),
                "location": c_obj.location.copy(),
                "rotation_mode": c_obj.rotation_mode,
                "rotation_euler": c_obj.rotation_euler.copy(),
                "rotation_quaternion": c_obj.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(c_obj.rotation_axis_angle),
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
                "con_ref": con,
                "con_ptr": con.as_pointer() if hasattr(con, "as_pointer") else None,
                "influence": float(con.influence),
                "mute": bool(con.mute),
                "target": getattr(con, "target", None),
                "subtarget": getattr(con, "subtarget", ""),
                "pole_target": getattr(con, "pole_target", None),
                "pole_subtarget": getattr(con, "pole_subtarget", ""),
            }
            if con.type == "IK":
                c_dict.update({
                    "chain_count": getattr(con, "chain_count", 0),
                    "use_tail": getattr(con, "use_tail", True),
                    "use_stretch": getattr(con, "use_stretch", False),
                    "pole_angle": float(getattr(con, "pole_angle", 0.0)),
                    "iterations": getattr(con, "iterations", 500),
                })
            elif con.type == "COPY_ROTATION":
                c_dict.update({
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

            generic_props: Dict[str, Any] = {}
            for p in con.rna_type.properties:
                if not p.is_readonly and p.identifier not in ("rna_type", "name", "mute", "influence"):
                    try:
                        val = getattr(con, p.identifier)
                    except Exception as pe:
                        raise RuntimeError(
                            f"Snapshot failed: cannot read property '{p.identifier}' (type {p.type}) "
                            f"on constraint '{con.name}' ({con.type}) on bone '{pbone.name}': {pe}"
                        ) from pe
                    generic_props[p.identifier] = _clone_snapshot_property_value(val)

            c_dict["generic_props"] = generic_props
            con_list.append(c_dict)

        pose_bones_data[b_name] = {
            "name": b_name,
            "location": pbone.location.copy(),
            "rotation_mode": pbone.rotation_mode,
            "rotation_euler": pbone.rotation_euler.copy(),
            "rotation_quaternion": pbone.rotation_quaternion.copy(),
            "rotation_axis_angle": tuple(pbone.rotation_axis_angle),
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
    # Step 1: Controller cleanup, stashed object restoration, and transform restoration
    controllers_snap = snapshot.get("controllers", {})
    for c_name, c_snap in controllers_snap.items():
        curr_obj = bpy.data.objects.get(c_name)

        if not c_snap["exists"]:
            if curr_obj is not None:
                bpy.data.objects.remove(curr_obj, do_unlink=True)
        else:
            orig_ref = c_snap.get("obj_ref")
            if curr_obj is not None and curr_obj != orig_ref:
                bpy.data.objects.remove(curr_obj, do_unlink=True)

            if orig_ref is not None:
                try:
                    _ = orig_ref.name
                    orig_alive = True
                except ReferenceError:
                    orig_alive = False

                if orig_alive:
                    if orig_ref.name != c_snap["obj_name"]:
                        orig_ref.name = c_snap["obj_name"]

                    for col_name in c_snap.get("collections", []):
                        col = _find_collection_by_name(col_name)
                        if col is not None and orig_ref.name not in col.objects:
                            col.objects.link(orig_ref)

                    for col in list(orig_ref.users_collection):
                        if col.name not in c_snap.get("collections", []):
                            col.objects.unlink(orig_ref)

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

    # Also ensure any other stashed objects from active_tx are restored
    if active_tx is not None:
        for stashed in getattr(active_tx, "stashed_objects", []):
            obj = stashed.get("stashed_obj")
            orig_name = stashed.get("original_name")
            if obj is not None and obj.name in bpy.data.objects:
                if orig_name and obj.name != orig_name:
                    obj.name = orig_name
                for col_name in stashed.get("collections", []):
                    col = _find_collection_by_name(col_name)
                    if col is not None and obj.name not in col.objects:
                        col.objects.link(obj)

    # Step 2: Pose bones and constraints restoration
    pose_bones_snap = snapshot.get("pose_bones", {})
    restoration_errors: List[str] = []

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

        # Constraints non-destructive restoration
        saved_cons = b_snap.get("constraints", [])
        saved_con_refs = {sc["con_ref"] for sc in saved_cons if "con_ref" in sc}

        # 2.1: Remove constraints added during transaction (identity check)
        for con in list(pbone.constraints):
            if con not in saved_con_refs:
                pbone.constraints.remove(con)

        # 2.2: Restore names and mutes for any stashed constraints on this bone
        if active_tx is not None:
            for item in getattr(active_tx, "stashed_constraints", []):
                if item["pbone"] == pbone:
                    c = item["con"]
                    if c in pbone.constraints.values():
                        c.name = item["orig_name"]
                        c.mute = item["orig_mute"]

        # 2.3: Reconcile and restore all saved constraints
        for sc in saved_cons:
            # Task 10-B-6
            # Resolve original constraint without substitution

            original_con = sc.get("con_ref")
            original_ptr = sc.get("con_ptr")

            if original_con is None or original_ptr is None:
                restoration_errors.append(
                    f"Missing snapshot identity: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            try:
                live_ptr = original_con.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    f"Original constraint destroyed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if live_ptr != original_ptr:
                restoration_errors.append(
                    f"Original constraint pointer changed: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con = None

            for candidate in pbone.constraints:
                if candidate.as_pointer() == original_ptr:
                    con = candidate
                    break

            if con is None:
                restoration_errors.append(
                    f"Original constraint absent from live chain: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            if con.type != sc["type"]:
                restoration_errors.append(
                    f"Original constraint type mismatch: "
                    f"{b_name}/{sc['name']}"
                )
                continue

            con.name = sc["name"]

            con.influence = sc["influence"]
            con.mute = sc["mute"]

            for prop, val in sc.get("generic_props", {}).items():
                try:
                    _trigger_fault_injection("during_constraint_property_restore", {
                        "bone": b_name, "con": sc["name"], "prop": prop, "val": val
                    })
                    if hasattr(con, prop):
                        if isinstance(val, (Vector, Euler, Quaternion, Matrix)):
                            setattr(con, prop, val.copy())
                        elif isinstance(val, tuple):
                            curr_val = getattr(con, prop)
                            if hasattr(curr_val, "__len__"):
                                for arr_i, el in enumerate(val):
                                    curr_val[arr_i] = el
                            else:
                                setattr(con, prop, val)
                        else:
                            setattr(con, prop, val)
                except Exception as ce:
                    restoration_errors.append(
                        f"Failed to restore property '{prop}' on constraint '{sc['name']}' "
                        f"on bone '{b_name}' with value {val!r}: {ce}"
                    )

            if hasattr(con, "target"):
                con.target = sc.get("target")
            if hasattr(con, "subtarget"):
                con.subtarget = sc.get("subtarget", "")
            if hasattr(con, "pole_target"):
                con.pole_target = sc.get("pole_target")
            if hasattr(con, "pole_subtarget"):
                con.pole_subtarget = sc.get("pole_subtarget", "")

            if sc["type"] == "IK":
                con.chain_count = sc.get("chain_count", 0)
                con.use_tail = sc.get("use_tail", True)
                con.use_stretch = sc.get("use_stretch", False)
                con.pole_angle = sc.get("pole_angle", 0.0)
                con.iterations = sc.get("iterations", 500)
            elif sc["type"] == "COPY_ROTATION":
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

        # 2.4: Restore constraint ordering
        for target_idx, sc in enumerate(saved_cons):
            curr_names = [c.name for c in pbone.constraints]
            if sc["name"] in curr_names:
                curr_idx = curr_names.index(sc["name"])
                if curr_idx != target_idx:
                    pbone.constraints.move(curr_idx, target_idx)

    # Step 3: Collection hierarchy restoration with strict ownership isolation
    # Only delete collections explicitly registered as created by this transaction!
    if active_tx is not None:
        for reg in list(getattr(active_tx, "created_collections", [])):
            col_ref = reg.get("col_ref")
            col_ptr = reg.get("col_ptr")
            created_name = reg.get("created_name")

            target_col = None
            if col_ref is not None:
                try:
                    if col_ref.name in bpy.data.collections and bpy.data.collections[col_ref.name] == col_ref:
                        target_col = col_ref
                except ReferenceError:
                    target_col = None
            if target_col is None and created_name in bpy.data.collections:
                c_candidate = bpy.data.collections[created_name]
                if col_ptr is None or c_candidate.as_pointer() == col_ptr:
                    target_col = c_candidate

            if target_col is not None:
                for p_col in list(bpy.data.collections):
                    if target_col.name in p_col.children:
                        p_col.children.unlink(target_col)
                for scene in list(bpy.data.scenes):
                    if target_col.name in scene.collection.children:
                        scene.collection.children.unlink(target_col)
                bpy.data.collections.remove(target_col)

    char_col_snap = snapshot.get("character_collection", {})
    if not char_col_snap.get("existed", False):
        # Transaction-owned collections are handled
        # exclusively by active_tx.created_collections.
        #
        # Never delete a collection merely because
        # its name is "Character".
        pass
    else:
        # ------------------------------------------------------
        # Task 10-B-7
        # Identity-safe restoration of Character collection
        # ------------------------------------------------------
        orig_name = char_col_snap.get("name")
        col = char_col_snap.get("col_ref")
        original_ptr = char_col_snap.get("col_ptr")

        if col is None or original_ptr is None:
            restoration_errors.append(
                "Character collection snapshot identity missing"
            )
        else:
            try:
                live_ptr = col.as_pointer()
            except ReferenceError:
                restoration_errors.append(
                    "Original Character collection destroyed"
                )
            else:
                if live_ptr != original_ptr:
                    restoration_errors.append(
                        "Character collection identity changed"
                    )
                else:
                    # Identity verified! Restore name, parents, children, and members.
                    if orig_name is not None and col.name != orig_name:
                        col.name = orig_name

                    should_be_in_scene = char_col_snap.get("children_of_scene", False)
                    is_in_scene = any(
                        c.as_pointer() == col.as_pointer()
                        for c in (bpy.context.scene.collection.children if bpy.context.scene else [])
                    )
                    if should_be_in_scene and not is_in_scene:
                        bpy.context.scene.collection.children.link(col)

                    # Parent Collection restoration by reference
                    expected_parents = char_col_snap.get(
                        "parent_refs", []
                    )
                    for parent in expected_parents:
                        try:
                            parent_ptr = parent.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Original Character parent collection destroyed"
                            )
                            continue

                        linked = any(
                            child.as_pointer() == col.as_pointer()
                            for child in parent.children
                        )
                        if not linked:
                            parent.children.link(col)

                    # Child Collection restoration by reference
                    expected_children = char_col_snap.get(
                        "child_refs", []
                    )
                    for child in expected_children:
                        try:
                            child_ptr = child.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Original Character child collection destroyed"
                            )
                            continue

                        linked = any(
                            current.as_pointer() == child_ptr
                            for current in col.children
                        )
                        if not linked:
                            col.children.link(child)

                    # Member Objects restoration by reference
                    expected_refs = char_col_snap.get(
                        "object_refs", []
                    )

                    for obj in expected_refs:
                        try:
                            obj_ptr = obj.as_pointer()
                        except ReferenceError:
                            restoration_errors.append(
                                "Character collection original member was destroyed"
                            )
                            continue

                        found = any(
                            current.as_pointer() == obj_ptr
                            for current in col.objects
                        )
                        if not found:
                            col.objects.link(obj)

    _depsgraph_update()

    if restoration_errors:
        raise RuntimeError("Rollback constraint restoration failed: " + "; ".join(restoration_errors))


def _verify_arm_rig_state_restored(
    arm: bpy.types.Object,
    snapshot: Dict[str, Any],
    active_tx: Optional[Any] = None,
) -> None:
    """Verify that current Arm IK rig state precisely matches the snapshot.

    Raises:
        RuntimeError: If any discrepancy is detected between current state and snapshot.
    """
    current = _snapshot_arm_rig_state(arm)
    diffs: List[str] = []
    TOL = 1e-5

    def _vec_diff(v1, v2) -> float:
        return max(abs(a - b) for a, b in zip(v1, v2))

    def _quat_diff(q1, q2) -> float:
        d1 = sum((a - b)**2 for a, b in zip(q1, q2))**0.5
        d2 = sum((a + b)**2 for a, b in zip(q1, q2))**0.5
        return min(d1, d2)

    def _mat_diff(m1, m2) -> Tuple[float, int, int]:
        max_d = 0.0
        max_r, max_c = 0, 0
        for r in range(4):
            for c in range(4):
                d = abs(m1[r][c] - m2[r][c])
                if d > max_d:
                    max_d = d
                    max_r, max_c = r, c
        return max_d, max_r, max_c

    # 1. Collection check
    s_col = snapshot.get("character_collection", {})
    c_col = current.get("character_collection", {})

    if s_col.get("existed"):
        if not c_col.get("existed"):
            diffs.append("Character collection existed in snapshot but is missing in current state")
        else:
            # Check original collection object identity
            orig_col_ref = s_col.get("col_ref")
            orig_col_ptr = s_col.get("col_ptr")
            curr_col_ref = c_col.get("col_ref")
            curr_col_ptr = c_col.get("col_ptr")

            if orig_col_ref is not None:
                try:
                    live_col_ptr = orig_col_ref.as_pointer()
                    if orig_col_ptr and live_col_ptr != orig_col_ptr:
                        diffs.append("Character collection original pointer changed")
                except ReferenceError:
                    diffs.append("Character collection original collection destroyed")

            if orig_col_ptr and curr_col_ptr and curr_col_ptr != orig_col_ptr:
                diffs.append(f"Character collection identity mismatch: expected={orig_col_ptr}, actual={curr_col_ptr}")

            if orig_col_ref is not None and s_col.get("name") != c_col.get("name"):
                diffs.append(f"Character collection name '{c_col.get('name')}' != expected '{s_col.get('name')}'")

            # Parent / Child / Member identity hierarchy verification
            if s_col.get("children_of_scene") and not c_col.get("children_of_scene"):
                diffs.append("Character collection missing from scene collection children")

            def _live_identity_set(items, desc: str = "item"):
                result = set()
                for item in items:
                    try:
                        result.add(item.as_pointer())
                    except ReferenceError:
                        diffs.append(f"Character collection original {desc} was destroyed")
                return result

            original_parent_ptrs = _live_identity_set(
                s_col.get("parent_refs", []), "parent collection"
            )
            current_parent_ptrs = _live_identity_set(
                c_col.get("parent_refs", []), "current parent collection"
            )
            missing_parent_ptrs = (
                original_parent_ptrs - current_parent_ptrs
            )
            if missing_parent_ptrs:
                diffs.append(
                    "Character collection original parent "
                    f"identities missing: {missing_parent_ptrs}"
                )

            original_child_ptrs = _live_identity_set(
                s_col.get("child_refs", []), "child collection"
            )
            current_child_ptrs = _live_identity_set(
                c_col.get("child_refs", []), "current child collection"
            )
            missing_child_ptrs = (
                original_child_ptrs - current_child_ptrs
            )
            if missing_child_ptrs:
                diffs.append(
                    "Character collection original child "
                    f"identities missing: {missing_child_ptrs}"
                )

            original_obj_ptrs = _live_identity_set(
                s_col.get("object_refs", []), "member object"
            )
            current_obj_ptrs = _live_identity_set(
                c_col.get("object_refs", []), "current member object"
            )
            missing_obj_ptrs = (
                original_obj_ptrs - current_obj_ptrs
            )
            if missing_obj_ptrs:
                diffs.append(
                    "Character collection original member "
                    f"identities missing: {missing_obj_ptrs}"
                )
    else:
        # Snapshot did NOT have Character collection.
        # If active_tx created it, active_tx.created_collections will catch it below if not removed.
        # If an external party created a Character collection, it must be preserved.
        pass

    # Check that transaction-created collections do not linger
    if active_tx is not None:
        for reg in getattr(active_tx, "created_collections", []):
            c_name = reg.get("created_name")
            c_ptr = reg.get("col_ptr")
            c_ref = reg.get("col_ref")
            found_lingering = False
            if c_ref is not None:
                try:
                    if c_ref.name in bpy.data.collections and bpy.data.collections[c_ref.name] == c_ref:
                        found_lingering = True
                except ReferenceError:
                    found_lingering = False
            if not found_lingering and c_name in bpy.data.collections:
                col_obj = bpy.data.collections[c_name]
                if c_ptr is None or col_obj.as_pointer() == c_ptr:
                    found_lingering = True
            if found_lingering:
                diffs.append(f"Transaction-created collection '{c_name}' still exists in scene")

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

        try:
            obj_mismatch = (sc["obj_ref"] != cc["obj_ref"])
        except ReferenceError:
            obj_mismatch = True
        if obj_mismatch:
            diffs.append(f"Controller {c_name} obj_ref identity mismatch")
        if sc.get("obj_ptr") and cc.get("obj_ptr") and sc["obj_ptr"] != cc["obj_ptr"]:
            diffs.append(f"Controller {c_name} obj_ptr mismatch: {cc['obj_ptr']} != {sc['obj_ptr']}")
        try:
            data_mismatch = (sc["data_ref"] != cc["data_ref"])
        except ReferenceError:
            data_mismatch = True
        if data_mismatch:
            diffs.append(f"Controller {c_name} data_ref identity mismatch")
        if sc.get("data_ptr") and cc.get("data_ptr") and sc["data_ptr"] != cc["data_ptr"]:
            diffs.append(f"Controller {c_name} data_ptr mismatch: {cc['data_ptr']} != {sc['data_ptr']}")
        if sc["obj_name"] != cc["obj_name"]:
            diffs.append(f"Controller {c_name} obj_name {cc['obj_name']} != {sc['obj_name']}")
        if sc["type"] != cc["type"]:
            diffs.append(f"Controller {c_name} type {cc['type']} != {sc['type']}")
        if sc["parent"] != cc["parent"]:
            diffs.append(f"Controller {c_name} parent {cc['parent']} != {sc['parent']}")

        mat_inv_diff, mr, mc = _mat_diff(sc["matrix_parent_inverse"], cc["matrix_parent_inverse"])
        if mat_inv_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_parent_inverse[{mr}][{mc}] diff {mat_inv_diff:.6e} > {TOL}")

        loc_diff = _vec_diff(sc["location"], cc["location"])
        if loc_diff > TOL:
            diffs.append(f"Controller {c_name} location diff {loc_diff:.6e} > {TOL}")

        if sc["rotation_mode"] != cc["rotation_mode"]:
            diffs.append(f"Controller {c_name} rotation_mode {cc['rotation_mode']} != {sc['rotation_mode']}")

        euler_diff = _vec_diff(sc["rotation_euler"], cc["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sc["rotation_quaternion"], cc["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sc["rotation_axis_angle"][0] - cc["rotation_axis_angle"][0])
        d_axis = _vec_diff(sc["rotation_axis_angle"][1:], cc["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Controller {c_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sc["scale"], cc["scale"])
        if scale_diff > TOL:
            diffs.append(f"Controller {c_name} scale diff {scale_diff:.6e} > {TOL}")

        mat_w_diff, wr, wc = _mat_diff(sc["matrix_world"], cc["matrix_world"])
        if mat_w_diff > TOL:
            diffs.append(f"Controller {c_name} matrix_world[{wr}][{wc}] diff {mat_w_diff:.6e} > {TOL}")

        if set(sc["collections"]) != set(cc["collections"]):
            diffs.append(f"Controller {c_name} collections {cc['collections']} != {sc['collections']}")

        if sc["type"] == "EMPTY":
            if sc["empty_display_type"] != cc["empty_display_type"]:
                diffs.append(f"Controller {c_name} empty_display_type {cc['empty_display_type']} != {sc['empty_display_type']}")
            if abs(sc["empty_display_size"] - cc["empty_display_size"]) > TOL:
                diffs.append(f"Controller {c_name} empty_display_size {cc['empty_display_size']} != {sc['empty_display_size']}")

    # 3. Pose bones check
    s_bones = snapshot.get("pose_bones", {})
    c_bones = current.get("pose_bones", {})
    for b_name, sb in s_bones.items():
        cb = c_bones.get(b_name)
        if cb is None:
            diffs.append(f"Pose bone {b_name} missing in current state")
            continue

        loc_diff = _vec_diff(sb["location"], cb["location"])
        if loc_diff > TOL:
            diffs.append(f"Bone {b_name} location diff {loc_diff:.6e} > {TOL}")

        if sb["rotation_mode"] != cb["rotation_mode"]:
            diffs.append(f"Bone {b_name} rotation_mode {cb['rotation_mode']} != {sb['rotation_mode']}")

        euler_diff = _vec_diff(sb["rotation_euler"], cb["rotation_euler"])
        if euler_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_euler diff {euler_diff:.6e} > {TOL}")

        quat_diff = _quat_diff(sb["rotation_quaternion"], cb["rotation_quaternion"])
        if quat_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_quaternion diff {quat_diff:.6e} > {TOL}")

        d_angle = abs(sb["rotation_axis_angle"][0] - cb["rotation_axis_angle"][0])
        d_axis = _vec_diff(sb["rotation_axis_angle"][1:], cb["rotation_axis_angle"][1:])
        axis_diff = max(d_angle, d_axis)
        if axis_diff > TOL:
            diffs.append(f"Bone {b_name} rotation_axis_angle diff {axis_diff:.6e} > {TOL}")

        scale_diff = _vec_diff(sb["scale"], cb["scale"])
        if scale_diff > TOL:
            diffs.append(f"Bone {b_name} scale diff {scale_diff:.6e} > {TOL}")

        basis_diff, br, bc = _mat_diff(sb["matrix_basis"], cb["matrix_basis"])
        if basis_diff > TOL:
            diffs.append(f"Bone {b_name} matrix_basis[{br}][{bc}] diff {basis_diff:.6e} > {TOL}")

        for axis in ("x", "y", "z"):
            if sb[f"lock_ik_{axis}"] != cb[f"lock_ik_{axis}"]:
                diffs.append(f"Bone {b_name} lock_ik_{axis} {cb[f'lock_ik_{axis}']} != {sb[f'lock_ik_{axis}']}")
            if sb[f"use_ik_limit_{axis}"] != cb[f"use_ik_limit_{axis}"]:
                diffs.append(f"Bone {b_name} use_ik_limit_{axis} {cb[f'use_ik_limit_{axis}']} != {sb[f'use_ik_limit_{axis}']}")
            if abs(sb[f"ik_min_{axis}"] - cb[f"ik_min_{axis}"]) > TOL:
                diffs.append(f"Bone {b_name} ik_min_{axis} {cb[f'ik_min_{axis}']} != {sb[f'ik_min_{axis}']}")
            if abs(sb[f"ik_max_{axis}"] - cb[f"ik_max_{axis}"]) > TOL:
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
                # Task 10-B-6
                # Original constraint identity verification

                orig_con = sc.get("con_ref")
                orig_ptr = sc.get("con_ptr")

                curr_con = cc.get("con_ref")
                curr_ptr = cc.get("con_ptr")

                label = (
                    f"Bone {b_name} "
                    f"constraint[{idx}] '{sc['name']}'"
                )

                if orig_con is None or orig_ptr is None:
                    diffs.append(
                        f"{label}: snapshot identity missing"
                    )

                else:
                    try:
                        live_orig_ptr = orig_con.as_pointer()
                    except ReferenceError:
                        diffs.append(
                            f"{label}: original constraint destroyed"
                        )
                    else:
                        if live_orig_ptr != orig_ptr:
                            diffs.append(
                                f"{label}: original pointer changed"
                            )

                        elif curr_con is None or curr_ptr is None:
                            diffs.append(
                                f"{label}: current identity missing"
                            )

                        elif curr_ptr != orig_ptr:
                            diffs.append(
                                f"{label}: identity mismatch; "
                                f"expected={orig_ptr}, "
                                f"actual={curr_ptr}"
                            )
                if abs(sc["influence"] - cc["influence"]) > TOL:
                    diffs.append(f"Bone {b_name} constraint {idx} influence {cc['influence']} != {sc['influence']}")
                if sc["mute"] != cc["mute"]:
                    diffs.append(f"Bone {b_name} constraint {idx} mute {cc['mute']} != {sc['mute']}")
                if sc.get("target") != cc.get("target"):
                    diffs.append(f"Bone {b_name} constraint {idx} target {cc.get('target')} != {sc.get('target')}")
                if sc.get("subtarget") != cc.get("subtarget"):
                    diffs.append(f"Bone {b_name} constraint {idx} subtarget {cc.get('subtarget')} != {sc.get('subtarget')}")
                if sc.get("pole_target") != cc.get("pole_target"):
                    diffs.append(f"Bone {b_name} constraint {idx} pole_target {cc.get('pole_target')} != {sc.get('pole_target')}")
                if sc.get("pole_subtarget") != cc.get("pole_subtarget"):
                    diffs.append(f"Bone {b_name} constraint {idx} pole_subtarget {cc.get('pole_subtarget')} != {sc.get('pole_subtarget')}")

                if sc["type"] == "IK":
                    if sc.get("chain_count") != cc.get("chain_count"):
                        diffs.append(f"Bone {b_name} constraint {idx} chain_count {cc.get('chain_count')} != {sc.get('chain_count')}")
                    if sc.get("use_tail") != cc.get("use_tail"):
                        diffs.append(f"Bone {b_name} constraint {idx} use_tail {cc.get('use_tail')} != {sc.get('use_tail')}")
                    if sc.get("use_stretch") != cc.get("use_stretch"):
                        diffs.append(f"Bone {b_name} constraint {idx} use_stretch {cc.get('use_stretch')} != {sc.get('use_stretch')}")
                    if abs(sc.get("pole_angle", 0.0) - cc.get("pole_angle", 0.0)) > TOL:
                        diffs.append(f"Bone {b_name} constraint {idx} pole_angle {cc.get('pole_angle')} != {sc.get('pole_angle')}")
                    if sc.get("iterations") != cc.get("iterations"):
                        diffs.append(f"Bone {b_name} constraint {idx} iterations {cc.get('iterations')} != {sc.get('iterations')}")
                elif sc["type"] == "COPY_ROTATION":
                    if sc.get("target_space") != cc.get("target_space"):
                        diffs.append(f"Bone {b_name} constraint {idx} target_space {cc.get('target_space')} != {sc.get('target_space')}")
                    if sc.get("owner_space") != cc.get("owner_space"):
                        diffs.append(f"Bone {b_name} constraint {idx} owner_space {cc.get('owner_space')} != {sc.get('owner_space')}")
                    if sc.get("mix_mode") != cc.get("mix_mode"):
                        diffs.append(f"Bone {b_name} constraint {idx} mix_mode {cc.get('mix_mode')} != {sc.get('mix_mode')}")
                    for axis in ("x", "y", "z"):
                        if sc.get(f"use_{axis}") != cc.get(f"use_{axis}"):
                            diffs.append(f"Bone {b_name} constraint {idx} use_{axis} {cc.get(f'use_{axis}')} != {sc.get(f'use_{axis}')}")
                        if sc.get(f"invert_{axis}") != cc.get(f"invert_{axis}"):
                            diffs.append(f"Bone {b_name} constraint {idx} invert_{axis} {cc.get(f'invert_{axis}')} != {sc.get(f'invert_{axis}')}")
                    if sc.get("use_offset") != cc.get("use_offset"):
                        diffs.append(f"Bone {b_name} constraint {idx} use_offset {cc.get('use_offset')} != {sc.get('use_offset')}")

                # Check generic properties
                s_gen = sc.get("generic_props", {})
                c_gen = cc.get("generic_props", {})
                for g_prop, s_val in s_gen.items():
                    c_val = c_gen.get(g_prop)
                    if isinstance(s_val, (Vector, Euler)):
                        if c_val is None or _vec_diff(s_val, c_val) > TOL:
                            diffs.append(f"Bone {b_name} constraint {idx} {g_prop} {c_val} != {s_val}")
                    elif isinstance(s_val, Quaternion):
                        if c_val is None or _quat_diff(s_val, c_val) > TOL:
                            diffs.append(f"Bone {b_name} constraint {idx} {g_prop} {c_val} != {s_val}")
                    elif isinstance(s_val, tuple):
                        if c_val is None or not hasattr(c_val, "__len__") or len(c_val) != len(s_val):
                            diffs.append(f"Bone {b_name} constraint {idx} {g_prop} length mismatch: {c_val} != {s_val}")
                        else:
                            for arr_i, (sv, cv) in enumerate(zip(s_val, c_val)):
                                if isinstance(sv, float):
                                    if abs(sv - cv) > TOL:
                                        diffs.append(f"Bone {b_name} constraint {idx} {g_prop}[{arr_i}] {cv} != {sv} (diff {abs(sv - cv):.6e} > {TOL})")
                                elif sv != cv:
                                    diffs.append(f"Bone {b_name} constraint {idx} {g_prop}[{arr_i}] {cv} != {sv}")
                    elif isinstance(s_val, float):
                        if c_val is None or abs(s_val - c_val) > TOL:
                            diffs.append(f"Bone {b_name} constraint {idx} {g_prop} {c_val} != {s_val}")
                    else:
                        if s_val != c_val:
                            diffs.append(f"Bone {b_name} constraint {idx} {g_prop} {c_val} != {s_val}")

    # 4. Active transaction stack check
    if active_tx is None:
        if len(_ACTIVE_TRANSACTION_STACK) != 0:
            diffs.append(f"Active transaction stack is not empty (contains {len(_ACTIVE_TRANSACTION_STACK)} transactions)")
    else:
        if _ACTIVE_TRANSACTION_STACK != [active_tx]:
            diffs.append(f"Active transaction stack contains unexpected transactions: {_ACTIVE_TRANSACTION_STACK}")

    if diffs:
        raise RuntimeError("Arm rig rollback verification failed: " + "; ".join(diffs))


class _ArmRigTransactionContext:
    """Active transaction execution state tracking."""

    def __init__(self, arm: bpy.types.Object):
        self.arm = arm
        self.arm_ptr = arm.as_pointer()
        self.state: _ArmRigTransactionState = _ArmRigTransactionState.CREATED
        self.snapshot: Optional[Dict[str, Any]] = None
        self.stashed_objects: List[Dict[str, Any]] = []
        self.stashed_constraints: List[Dict[str, Any]] = []
        self.created_collections: List[Dict[str, Any]] = []
        self.uncleaned_stashed_objects: List[Dict[str, Any]] = []
        self.uncleaned_stashed_constraints: List[Dict[str, Any]] = []
        self.cleanup_error: Optional[str] = None
        self.tx_id: str = uuid.uuid4().hex[:8]

    @property
    def committed(self) -> bool:
        """Backward-compatibility property reflecting logical commit status."""
        return self.state in (_ArmRigTransactionState.COMMITTED, _ArmRigTransactionState.CLEANUP_PENDING)

    def register_created_collection(
        self,
        col: bpy.types.Collection,
        initial_parent: Optional[bpy.types.Collection] = None,
    ) -> None:
        """Register a collection created within this transaction for ownership tracking."""
        rec = {
            "col_ref": col,
            "col_ptr": col.as_pointer() if hasattr(col, "as_pointer") else None,
            "created_name": col.name,
            "initial_parent": initial_parent,
        }
        self.created_collections.append(rec)

    def retry_cleanup(self) -> None:
        """Idempotently retry irreversible cleanup of pending stashed resources."""
        cleanup_failures: List[str] = []

        # ------------------------------------------------------
        # Task 10-B-7
        # Identity-safe cleanup of stashed constraints
        # ------------------------------------------------------

        for stashed_con in list(
            self.uncleaned_stashed_constraints
        ):
            try:
                pbone = stashed_con["pbone"]

                expected_ptr = stashed_con.get("con_ptr")

                if expected_ptr is None:
                    raise RuntimeError(
                        "Stashed constraint has no recorded identity"
                    )

                live_matches = [
                    candidate
                    for candidate in pbone.constraints
                    if candidate.as_pointer() == expected_ptr
                ]

                if len(live_matches) > 1:
                    raise RuntimeError(
                        "Multiple live constraints match "
                        "the same recorded identity"
                    )

                if len(live_matches) == 1:
                    target = live_matches[0]

                    pbone.constraints.remove(target)

                    still_present = any(
                        candidate.as_pointer() == expected_ptr
                        for candidate in pbone.constraints
                    )

                    if still_present:
                        raise RuntimeError(
                            "Stashed constraint removal did not "
                            "remove the recorded identity"
                        )

                # No live match means the recorded resource
                # is already absent. Never remove by name.

                self.uncleaned_stashed_constraints.remove(
                    stashed_con
                )

            except Exception as exc:
                cleanup_failures.append(
                    "Failed to clean up stashed constraint "
                    f"{stashed_con.get('orig_name')}: {exc}"
                )

        # 2. Clean up stashed doomed objects and unreferenced datablocks
        for stashed in list(self.uncleaned_stashed_objects):
            # Step 2.1: Object cleanup
            if not stashed.get("obj_cleaned", False):
                try:
                    _trigger_fault_injection("during_cleanup_object_removal", {"stashed": stashed})
                    obj_ref = stashed.get("stashed_obj")
                    obj_ptr = stashed.get("stashed_obj_ptr")

                    target_obj = None
                    for o in bpy.data.objects:
                        try:
                            if obj_ptr and o.as_pointer() == obj_ptr:
                                target_obj = o
                                break
                            elif obj_ref is not None and o == obj_ref:
                                target_obj = o
                                break
                        except ReferenceError:
                            continue

                    if target_obj is not None:
                        bpy.data.objects.remove(target_obj, do_unlink=True)
                        still_exists = any(
                            (obj_ptr and o.as_pointer() == obj_ptr)
                            for o in bpy.data.objects
                        )
                        if still_exists:
                            cleanup_failures.append(
                                f"Failed to delete doomed object {stashed.get('original_name')}: still exists in bpy.data.objects"
                            )
                        else:
                            stashed["obj_cleaned"] = True
                    else:
                        stashed["obj_cleaned"] = True
                except Exception as oe:
                    cleanup_failures.append(f"Failed to clean up stashed object {stashed.get('original_name')}: {oe}")

            # Step 2.2: DataBlock cleanup (runs only if object cleanup has succeeded)
            if stashed.get("obj_cleaned", False) and not stashed.get("data_cleaned", False):
                try:
                    _trigger_fault_injection("during_cleanup_datablock_removal", {"stashed": stashed})
                    data_ref = stashed.get("stashed_data")
                    data_ptr = stashed.get("stashed_data_ptr")
                    data_name = stashed.get("stashed_data_name")

                    if data_ptr is None and data_ref is None:
                        stashed["data_cleaned"] = True
                    else:
                        target_data = None
                        target_coll = None
                        for coll_name in ("meshes", "curves", "lights", "cameras", "armatures", "lattices", "metaballs", "volumes"):
                            coll = getattr(bpy.data, coll_name, None)
                            if coll is not None:
                                for item in coll:
                                    try:
                                        if data_ptr and item.as_pointer() == data_ptr:
                                            target_data = item
                                            target_coll = coll
                                            break
                                        elif data_ref is not None and item == data_ref:
                                            target_data = item
                                            target_coll = coll
                                            break
                                    except ReferenceError:
                                        continue
                            if target_data is not None:
                                break

                        if target_data is None:
                            stashed["data_cleaned"] = True
                        else:
                            try:
                                user_count = getattr(target_data, "users", 0)
                            except ReferenceError:
                                user_count = 0

                            if user_count > 0:
                                # Shared datablock with remaining users: preserve it per DataBlock rules
                                stashed["data_cleaned"] = True
                            else:
                                target_coll.remove(target_data, do_unlink=True)
                                still_present = any(
                                    (data_ptr and item.as_pointer() == data_ptr)
                                    for item in target_coll
                                )
                                if still_present:
                                    cleanup_failures.append(f"Failed to delete datablock {data_name}: still exists in {target_coll}")
                                else:
                                    stashed["data_cleaned"] = True
                except Exception as de:
                    cleanup_failures.append(f"Failed to clean up datablock for {stashed.get('original_name')}: {de}")

            # Only remove record from uncleaned_stashed_objects when BOTH object and datablock are cleaned
            if stashed.get("obj_cleaned", False) and stashed.get("data_cleaned", False):
                if stashed in self.uncleaned_stashed_objects:
                    self.uncleaned_stashed_objects.remove(stashed)

        if cleanup_failures:
            self.cleanup_error = "; ".join(cleanup_failures)
            self.state = _ArmRigTransactionState.CLEANUP_PENDING
            raise RuntimeError("Arm rig transaction commit cleanup failed: " + self.cleanup_error)
        else:
            self.cleanup_error = None
            if self.state == _ArmRigTransactionState.CLEANUP_PENDING:
                self.state = _ArmRigTransactionState.COMMITTED


_ACTIVE_TRANSACTION_STACK: List[_ArmRigTransactionContext] = []

# Task 10-B-6
# Runtime registry for committed transactions
# with unfinished resource cleanup.

_PENDING_ARM_RIG_CLEANUPS: Dict[
    str,
    "_ArmRigTransactionContext"
] = {}


def _register_pending_arm_rig_cleanup(
    tx: "_ArmRigTransactionContext",
) -> None:

    if tx.state != _ArmRigTransactionState.CLEANUP_PENDING:
        raise RuntimeError(
            "Cannot register cleanup for "
            "a non-pending transaction"
        )

    _PENDING_ARM_RIG_CLEANUPS[tx.tx_id] = tx


def get_pending_arm_rig_cleanup_ids() -> Tuple[str, ...]:
    """Return pending cleanup transaction IDs."""

    return tuple(
        sorted(_PENDING_ARM_RIG_CLEANUPS)
    )


def retry_pending_arm_rig_cleanup(tx_id: str) -> None:
    """Retry cleanup of one pending transaction."""

    tx = _PENDING_ARM_RIG_CLEANUPS.get(tx_id)

    if tx is None:
        raise KeyError(
            f"Pending cleanup transaction not found: {tx_id}"
        )

    tx.retry_cleanup()

    if tx.state == _ArmRigTransactionState.COMMITTED:
        if (
            tx.uncleaned_stashed_objects
            or tx.uncleaned_stashed_constraints
        ):
            raise RuntimeError(
                "Cleanup reported COMMITTED "
                "while pending resources remain"
            )

        _PENDING_ARM_RIG_CLEANUPS.pop(
            tx_id,
            None
        )


def _assert_arm_rig_cleanup_gate(
    arm: bpy.types.Object,
) -> None:
    """
    Reject new independent writes while the same Armature
    owns an unresolved committed cleanup transaction.
    """

    arm_ptr = arm.as_pointer()

    blocking_transactions = []

    for tx_id, tx in tuple(
        _PENDING_ARM_RIG_CLEANUPS.items()
    ):

        if tx.state != _ArmRigTransactionState.CLEANUP_PENDING:
            raise RuntimeError(
                "Arm IK cleanup registry invariant violated: "
                f"transaction {tx_id} is registered with "
                f"state {tx.state}"
            )

        if tx.arm_ptr == arm_ptr:
            blocking_transactions.append(tx_id)

    if blocking_transactions:
        raise RuntimeError(
            "Arm IK write blocked: unresolved cleanup "
            "for the same Armature; pending transactions="
            + ",".join(sorted(blocking_transactions))
        )


@contextmanager
def _arm_rig_transaction(arm: bpy.types.Object):
    """Context manager executing Arm IK mutations under atomic transaction protection."""
    global _ACTIVE_TRANSACTION_STACK
    if _ACTIVE_TRANSACTION_STACK:
        outer_tx = _ACTIVE_TRANSACTION_STACK[-1]
        if outer_tx.arm != arm:
            raise RuntimeError(
                f"Cross-armature nested transaction rejected: active transaction owns armature "
                f"'{outer_tx.arm.name}', but requested transaction is for armature '{arm.name}'."
            )
        # Re-entrant invocation on same armature: outer transaction retains exclusive ownership
        yield outer_tx
        return

    # Reject a new outermost transaction when previous
    # committed cleanup is unresolved on this Armature.
    _assert_arm_rig_cleanup_gate(arm)

    tx = _ArmRigTransactionContext(arm)
    _ACTIVE_TRANSACTION_STACK.append(tx)

    try:
        tx.state = _ArmRigTransactionState.SNAPSHOTTING
        tx.snapshot = _snapshot_arm_rig_state(arm)
        tx.state = _ArmRigTransactionState.ACTIVE

        yield tx

        # -------------------------------------------------------------
        # Phase 1: Reversible Commit Preparation
        # -------------------------------------------------------------
        tx.state = _ArmRigTransactionState.COMMITTING
        _trigger_fault_injection("before_commit_prepare", {"tx": tx})

        _depsgraph_update()
        _trigger_fault_injection("during_commit_prepare", {"tx": tx})

        # -------------------------------------------------------------
        # Phase 2: Logical Commit Confirmation
        # -------------------------------------------------------------
        tx.state = _ArmRigTransactionState.COMMITTED
        _trigger_fault_injection("after_logical_commit", {"tx": tx})

    except BaseException as orig_exc:
        # If failure occurred before Phase 2 (Logical Commit), execute full rollback!
        if tx.state != _ArmRigTransactionState.COMMITTED:
            tx.state = _ArmRigTransactionState.ROLLING_BACK
            rollback_err = None
            if tx.snapshot is not None:
                try:
                    _rollback_arm_rig_state(arm, tx.snapshot, tx)
                    _depsgraph_update()
                    _trigger_fault_injection("during_rollback_verification", {"arm": arm})
                    _verify_arm_rig_state_restored(arm, tx.snapshot, active_tx=tx)
                    tx.state = _ArmRigTransactionState.ROLLED_BACK
                except BaseException as rb_exc:
                    tx.state = _ArmRigTransactionState.FAILED
                    rollback_err = rb_exc

                if rollback_err is not None:
                    raise RuntimeError(
                        f"Arm rig transaction failed with {type(orig_exc).__name__}: {orig_exc}, "
                        f"AND rollback verification failed with {type(rollback_err).__name__}: {rollback_err}"
                    ) from orig_exc
                else:
                    raise
            else:
                tx.state = _ArmRigTransactionState.FAILED
                raise
        else:
            raise
    finally:
        if tx in _ACTIVE_TRANSACTION_STACK:
            _ACTIVE_TRANSACTION_STACK.remove(tx)

    # -----------------------------------------------------------------
    # Phase 3: Irreversible Resource Cleanup (runs only after logical commit)
    # -----------------------------------------------------------------
    if tx.state == _ArmRigTransactionState.COMMITTED:
        tx.uncleaned_stashed_constraints = list(tx.stashed_constraints)
        tx.uncleaned_stashed_objects = list(tx.stashed_objects)
        try:
            _trigger_fault_injection("during_commit_cleanup", {"tx": tx})
            tx.retry_cleanup()
        except BaseException as ce:
            tx.state = _ArmRigTransactionState.CLEANUP_PENDING
            tx.cleanup_error = str(ce)
            _register_pending_arm_rig_cleanup(tx)
            raise RuntimeError(
                f"Arm rig transaction committed, but irreversible cleanup failed: {ce}"
            ) from ce


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
                "stashed_obj_ptr": obj.as_pointer() if hasattr(obj, "as_pointer") else None,
                "stashed_data": getattr(obj, "data", None),
                "stashed_data_ptr": getattr(obj, "data", None).as_pointer() if (getattr(obj, "data", None) and hasattr(getattr(obj, "data", None), "as_pointer")) else None,
                "stashed_data_name": getattr(obj, "data", None).name if getattr(obj, "data", None) else None,
                "collections": [c.name for c in obj.users_collection],
                "obj_cleaned": False,
                "data_cleaned": False,
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
            for idx, con in enumerate(list(p_fore.constraints)):
                if con.name == con_name_ik:
                    if con.type == "IK":
                        ik_con = con
                    else:
                        if _ACTIVE_TRANSACTION_STACK:
                            tx = _ACTIVE_TRANSACTION_STACK[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_fore,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            p_fore.constraints.remove(con)
                elif con.type == "IK" and con.name.startswith("ArmIK"):
                    if _ACTIVE_TRANSACTION_STACK:
                        tx = _ACTIVE_TRANSACTION_STACK[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_fore,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
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
            for idx, con in enumerate(list(p_hand.constraints)):
                if con.name == con_name_rot:
                    if con.type == "COPY_ROTATION":
                        rot_con = con
                    else:
                        if _ACTIVE_TRANSACTION_STACK:
                            tx = _ACTIVE_TRANSACTION_STACK[-1]
                            orig_name = con.name
                            orig_mute = con.mute
                            orig_idx = idx
                            stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                            con.name = stashed_name
                            con.mute = True
                            tx.stashed_constraints.append({
                                "pbone": p_hand,
                                "con": con,
                                "con_ptr": con.as_pointer(),
                                "orig_name": orig_name,
                                "orig_mute": orig_mute,
                                "orig_idx": orig_idx,
                            })
                        else:
                            p_hand.constraints.remove(con)
                elif con.type == "COPY_ROTATION" and con.name.startswith("HandRotation"):
                    if _ACTIVE_TRANSACTION_STACK:
                        tx = _ACTIVE_TRANSACTION_STACK[-1]
                        orig_name = con.name
                        orig_mute = con.mute
                        orig_idx = idx
                        stashed_name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"
                        con.name = stashed_name
                        con.mute = True
                        tx.stashed_constraints.append({
                            "pbone": p_hand,
                            "con": con,
                            "con_ptr": con.as_pointer(),
                            "orig_name": orig_name,
                            "orig_mute": orig_mute,
                            "orig_idx": orig_idx,
                        })
                    else:
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

        _depsgraph_update()
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

        _depsgraph_update()


def reset_arm_ik(armature_obj: Optional[bpy.types.Object] = None) -> None:
    """Reset both arms, empties, and constraint influences back to neutral rest (FK mode).

    Preserves existing controller parent relationships, rotation_mode, and matrix_parent_inverse,
    transforming neutral world positions and orientations into the controller's effective parent space.
    """
    arm = _resolve_armature(armature_obj)
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    _depsgraph_update()

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

    _depsgraph_update()


def get_arm_ik_state(armature_obj: Optional[bpy.types.Object], side: str) -> dict:
    """Inspect current world-space arm bone positions, target errors, bone lengths, and flexion."""
    valid_side = _validate_side(side, allow_both=False, param_name="side")
    arm = _resolve_armature(armature_obj)
    _depsgraph_update()

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
    _depsgraph_update()
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

        _update_arm_ik_depsgraph()

        _trigger_fault_injection("set_hand_ik_target_during_state_read", {"arm": arm})
        state = get_arm_ik_state(arm, valid_side)
        state["requested_world"] = requested
        state["applied_world"] = applied
        state["is_reachable"] = is_reachable
        state["clamped_reach"] = clamped_reach

    return state
