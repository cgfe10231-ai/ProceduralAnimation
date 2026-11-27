"""TASK 11 — FootLock Lifecycle & Query/Maintenance Split Verification Suite.

Runs directly inside Blender 5.1.1 (`blender -b -P verify_footlock_contract.py`) without
modifying any production source files or historical tests/assets:
- Group A: A01..A18 (plus A16 subprocess Blender reopen verification via verify_footlock_reopen.py;
  A19 links directly to historical 09-B-4 TEST-24 in the regression runner).
- Group B: B01..B18 & B20 (including strict Section 5 zero-side-effect rig state & call-count audits;
  B19 links directly to legacy_foot_contact in the regression runner).
- Section 7 Continuous Production Chain: StartStopWalkAction (with central bilateral independent
  upper_limb_L FK & upper_limb_R IK), TerrainWalkAction, RunAction, SprintStartAction, SprintBrakeAction
  executed through MotionPlanner -> Bridge -> WBC -> Rig -> MotionState.
"""

from __future__ import annotations

import copy
import datetime
import functools
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import bpy
from mathutils import Euler, Matrix, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import src.rig.foot_contact as fc_mod
import src.rig.ik as ik_mod
import src.scene.playground_character_assembly as pca_mod
from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    EnvironmentQuery,
    MotionPlanner,
    StartStopWalkAction,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.run_cycle import RunAction
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import UpperLimbSegment
from src.motion.whole_body_controller import WholeBodyControlTargets, WholeBodyController
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.foot_contact import (
    MAX_EFFECTIVE_SUPPORT_REACH,
    evaluate_foot_support,
    get_foot_support_state,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    FOOT_LOCK_METADATA_KEYS,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    POLE_FORWARD_OFFSET,
    POLE_TARGET_NAMES,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose
from src.scene.environment_query import create_standard_dynamics_playground_query
from src.scene_transaction_integrity.fault_injection import (
    _clear_test_fault_injection_hook,
    _set_test_fault_injection_hook,
)
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import (
    _PENDING_ARM_RIG_CLEANUPS,
)
from src.scene_transaction_integrity.layer2.session_registries import (
    _ISOLATED_FAILED_ARMATURES,
)
from src.scene_transaction_integrity.layer2.transaction_stack import (
    _ACTIVE_TRANSACTION_STACK,
)

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
REOPEN_SCRIPT = os.path.join(THIS_DIR, "verify_footlock_reopen.py")
SCRATCH_REOPEN_DIR = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\task11_reopen_scenes"
)
CONTRACT_RESULTS_JSON = os.path.join(THIS_DIR, "contract_results.json")

_LEG_BONES_6 = ("thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R")
_CTRLS_4 = ("FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R")
_EXPECTED_SUPPORT_KEYS = {
    "side",
    "is_locked",
    "contact_world",
    "locked_ankle_world",
    "target_rotation_deg",
    "hip_world",
    "hip_to_target_dist",
    "horiz_offset_from_hip",
    "max_leg_reach",
    "max_effective_support_reach",
    "reach_margin_strict",
    "strictly_in_reach",
    "is_reachable",
    "reach_status",
    "controller_world",
    "foot_head_world",
    "foot_tail_world",
    "foot_center_world",
    "foot_min_z",
    "controller_drift",
    "ankle_bone_drift",
    "ankle_horiz_drift",
    "toe_bone_drift",
    "mesh_center_drift",
    "knee_flexion_deg",
    "knee_forward_y",
}


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _detach_prop(val: Any) -> Any:
    if hasattr(val, "to_list"):
        return tuple(_detach_prop(x) for x in val.to_list())
    if hasattr(val, "items"):
        return {str(k): _detach_prop(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return tuple(_detach_prop(x) for x in val)
    if isinstance(val, bool):
        return bool(val)
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (str, type(None))):
        return val
    return copy.deepcopy(val)


def _fresh_rig(with_arms: bool = False) -> Tuple[PipelineConfig, bpy.types.Object, bpy.types.Object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _clear_test_fault_injection_hook()
    _PENDING_ARM_RIG_CLEANUPS.clear()
    _ISOLATED_FAILED_ARMATURES.clear()
    _ACTIVE_TRANSACTION_STACK.clear()

    bpy.context.scene.render.fps = 24
    cfg = PipelineConfig()
    parts = build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm, parts)
    reset_pose(arm)
    setup_leg_ik(arm)
    if with_arms:
        setup_arm_ik(arm, initial_influence=0.0)
    root = arm.parent or bpy.data.objects["CharacterRoot"]
    bpy.context.view_layer.update()
    return cfg, arm, root


def _read_all_lock_meta(ik_obj: bpy.types.Object) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in FOOT_LOCK_METADATA_KEYS:
        if k in ik_obj:
            out[k] = _detach_prop(ik_obj[k])
    return out


def _assert_unlocked_clean(ik_obj: bpy.types.Object, label: str) -> None:
    if bool(ik_obj.get("is_locked", False)):
        raise AssertionError(f"{label}: expected is_locked=False, got {ik_obj.get('is_locked')!r}")
    leftover = [k for k in FOOT_LOCK_METADATA_KEYS if k in ik_obj]
    if leftover:
        raise AssertionError(f"{label}: expected 0 lock metadata keys, remaining={leftover}")


def _assert_locked_complete(ik_obj: bpy.types.Object, label: str) -> Dict[str, Any]:
    if ik_obj.get("is_locked") is not True:
        raise AssertionError(f"{label}: expected is_locked=True, got {ik_obj.get('is_locked')!r}")
    missing = [k for k in FOOT_LOCK_METADATA_KEYS if k not in ik_obj]
    if missing:
        raise AssertionError(f"{label}: missing lock metadata keys={missing}")
    return _read_all_lock_meta(ik_obj)


def _assert_meta_equal(actual: Dict[str, Any], expected: Dict[str, Any], label: str, tol: float = 1e-6) -> None:
    if set(actual.keys()) != set(expected.keys()):
        raise AssertionError(f"{label}: key set mismatch {sorted(actual.keys())} != {sorted(expected.keys())}")
    for k in expected:
        av = actual[k]
        ev = expected[k]
        if isinstance(ev, tuple):
            if not isinstance(av, tuple) or len(av) != len(ev):
                raise AssertionError(f"{label}[{k}]: shape mismatch {av!r} != {ev!r}")
            for a_i, e_i in zip(av, ev):
                if not math.isclose(float(a_i), float(e_i), rel_tol=tol, abs_tol=tol):
                    raise AssertionError(f"{label}[{k}]: {av!r} != {ev!r}")
        elif isinstance(ev, bool):
            if type(av) is not bool or av != ev:
                raise AssertionError(f"{label}[{k}]: {av!r} != {ev!r}")
        elif isinstance(ev, (int, float)):
            if isinstance(av, bool) or not math.isclose(float(av), float(ev), rel_tol=tol, abs_tol=tol):
                raise AssertionError(f"{label}[{k}]: {av!r} != {ev!r}")
        else:
            if av != ev:
                raise AssertionError(f"{label}[{k}]: {av!r} != {ev!r}")


# =============================================================================
# Strict Section 5 Zero-Side-Effect State Collector & Call-Count Spy
# =============================================================================

def _capture_strict_state(arm: bpy.types.Object) -> Dict[str, Any]:
    """Read-only snapshot WITHOUT calling view_layer.update(), scene.frame_set(), or evaluate_foot_support()."""
    objs = [(o.name, int(o.as_pointer()), o.type) for o in bpy.data.objects]
    constraints_snapshot: Dict[str, List[Tuple[str, str, Optional[str], float]]] = {}
    for pb in arm.pose.bones:
        c_list = []
        for c in pb.constraints:
            tgt = getattr(c, "target", None)
            c_list.append((c.name, c.type, tgt.name if tgt is not None else None, float(c.influence)))
        constraints_snapshot[pb.name] = c_list

    tracked_objs: Dict[str, Any] = {}
    for name in ("CharacterRoot", "CharacterArmature", *_CTRLS_4):
        obj = bpy.data.objects.get(name)
        if obj is None:
            tracked_objs[name] = None
            continue
        custom_all = {str(k): _detach_prop(obj[k]) for k in obj.keys() if k != "_RNA_UI"}
        tracked_objs[name] = {
            "ptr": int(obj.as_pointer()),
            "parent": obj.parent.name if obj.parent is not None else None,
            "parent_ptr": int(obj.parent.as_pointer()) if obj.parent is not None else None,
            "rotation_mode": str(obj.rotation_mode),
            "location": tuple(float(v) for v in obj.location),
            "rotation_euler": tuple(float(v) for v in obj.rotation_euler),
            "rotation_quaternion": tuple(float(v) for v in obj.rotation_quaternion),
            "rotation_axis_angle": tuple(float(v) for v in obj.rotation_axis_angle),
            "scale": tuple(float(v) for v in obj.scale),
            "delta_location": tuple(float(v) for v in obj.delta_location),
            "delta_rotation_euler": tuple(float(v) for v in obj.delta_rotation_euler),
            "delta_rotation_quaternion": tuple(float(v) for v in obj.delta_rotation_quaternion),
            "delta_scale": tuple(float(v) for v in obj.delta_scale),
            "matrix_parent_inverse": tuple(tuple(float(obj.matrix_parent_inverse[r][c]) for c in range(4)) for r in range(4)),
            "matrix_world": tuple(tuple(float(obj.matrix_world[r][c]) for c in range(4)) for r in range(4)),
            "custom_props": custom_all,
            "lock_presence": {k: (k in obj) for k in FOOT_LOCK_METADATA_KEYS} if name in IK_TARGET_NAMES.values() else {},
            "lock_meta": _read_all_lock_meta(obj) if name in IK_TARGET_NAMES.values() else {},
        }

    bones: Dict[str, Any] = {}
    for bname in _LEG_BONES_6:
        pb = arm.pose.bones[bname]
        bones[bname] = {
            "ptr": int(pb.as_pointer()),
            "rotation_mode": str(pb.rotation_mode),
            "location": tuple(float(v) for v in pb.location),
            "rotation_euler": tuple(float(v) for v in pb.rotation_euler),
            "rotation_quaternion": tuple(float(v) for v in pb.rotation_quaternion),
            "rotation_axis_angle": tuple(float(v) for v in pb.rotation_axis_angle),
            "scale": tuple(float(v) for v in pb.scale),
            "matrix_basis": tuple(tuple(float(pb.matrix_basis[r][c]) for c in range(4)) for r in range(4)),
            "matrix": tuple(tuple(float(pb.matrix[r][c]) for c in range(4)) for r in range(4)),
        }

    return {
        "objects": objs,
        "constraints": constraints_snapshot,
        "tracked_objs": tracked_objs,
        "bones": bones,
        "frame_current": int(bpy.context.scene.frame_current),
    }


def _struct_eq_nan_safe(a: Any, b: Any) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if isinstance(a, (tuple, list)):
        return len(a) == len(b) and all(_struct_eq_nan_safe(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_struct_eq_nan_safe(a[k], b[k]) for k in a)
    return a == b


def _assert_strict_state_identical(before: Dict[str, Any], after: Dict[str, Any], label: str) -> None:
    if before["objects"] != after["objects"]:
        raise AssertionError(f"{label}: bpy.data.objects changed: {before['objects']} != {after['objects']}")
    if before["constraints"] != after["constraints"]:
        raise AssertionError(f"{label}: armature constraints changed")
    if before["frame_current"] != after["frame_current"]:
        raise AssertionError(f"{label}: frame_current changed: {before['frame_current']} != {after['frame_current']}")

    for name in before["tracked_objs"]:
        b = before["tracked_objs"][name]
        a = after["tracked_objs"][name]
        if b is None or a is None:
            if b != a:
                raise AssertionError(f"{label}: object '{name}' existence changed")
            continue
        for key in ("ptr", "parent", "parent_ptr", "rotation_mode", "lock_presence", "custom_props", "lock_meta"):
            if not _struct_eq_nan_safe(b[key], a[key]):
                raise AssertionError(f"{label}: {name}.{key} mutated: {b[key]!r} != {a[key]!r}")
        for vec_key in (
            "location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle",
            "scale", "delta_location", "delta_rotation_euler", "delta_rotation_quaternion", "delta_scale",
        ):
            max_d = max((abs(float(x) - float(y)) for x, y in zip(b[vec_key], a[vec_key])), default=0.0)
            if max_d > 1e-7:
                raise AssertionError(f"{label}: {name}.{vec_key} mutated (max_diff={max_d})")
        for mat_key in ("matrix_parent_inverse", "matrix_world"):
            max_d = max(abs(b[mat_key][r][c] - a[mat_key][r][c]) for r in range(4) for c in range(4))
            if max_d > 1e-7:
                raise AssertionError(f"{label}: {name}.{mat_key} mutated (max_diff={max_d})")

    for bname in _LEG_BONES_6:
        bb = before["bones"][bname]
        ab = after["bones"][bname]
        if bb["ptr"] != ab["ptr"] or bb["rotation_mode"] != ab["rotation_mode"]:
            raise AssertionError(f"{label}: pose bone {bname} identity/mode mutated")
        for vec_key in ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"):
            max_d = max((abs(float(x) - float(y)) for x, y in zip(bb[vec_key], ab[vec_key])), default=0.0)
            if max_d > 1e-7:
                raise AssertionError(f"{label}: pose bone {bname}.{vec_key} mutated (max_diff={max_d})")
        for mat_key in ("matrix_basis", "matrix"):
            max_d = max(abs(bb[mat_key][r][c] - ab[mat_key][r][c]) for r in range(4) for c in range(4))
            if max_d > 1e-7:
                raise AssertionError(f"{label}: pose bone {bname}.{mat_key} mutated (max_diff={max_d})")


class _ViewLayerSpy:
    def __init__(self, real_vl: Any, counters: Dict[str, int]):
        self._real = real_vl
        self._counters = counters

    def update(self) -> Any:
        self._counters["view_layer_update"] += 1
        return self._real.update()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _SceneSpy:
    def __init__(self, real_sc: Any, counters: Dict[str, int]):
        self._real = real_sc
        self._counters = counters

    def frame_set(self, *args: Any, **kwargs: Any) -> Any:
        self._counters["scene_frame_set"] += 1
        return self._real.frame_set(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _ContextSpy:
    def __init__(self, real_ctx: Any, counters: Dict[str, int]):
        self._real = real_ctx
        self._counters = counters

    @property
    def view_layer(self) -> _ViewLayerSpy:
        return _ViewLayerSpy(self._real.view_layer, self._counters)

    @property
    def scene(self) -> _SceneSpy:
        return _SceneSpy(self._real.scene, self._counters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _SpyScope:
    def __init__(self) -> None:
        self.counters: Dict[str, int] = {
            "view_layer_update": 0,
            "scene_frame_set": 0,
            "ensure_ik_controls": 0,
            "setup_leg_ik": 0,
            "apply_ik_prebend_hint": 0,
            "evaluate_foot_support": 0,
            "get_leg_ik_state": 0,
            "get_leg_ik_state_update_true": 0,
        }
        self._patches: List[Any] = []

    def __enter__(self) -> Dict[str, int]:
        orig_ensure = fc_mod._ensure_ik_controls
        orig_setup_fc = fc_mod.setup_leg_ik
        orig_setup_ik = ik_mod.setup_leg_ik
        orig_pre_fc = fc_mod._apply_ik_prebend_hint
        orig_pre_ik = ik_mod._apply_ik_prebend_hint
        orig_eval = fc_mod.evaluate_foot_support
        orig_leg_fc = fc_mod.get_leg_ik_state
        orig_leg_ik = ik_mod.get_leg_ik_state

        c = self.counters

        def w_ensure(*a: Any, **kw: Any) -> Any:
            c["ensure_ik_controls"] += 1
            return orig_ensure(*a, **kw)

        def w_setup_fc(*a: Any, **kw: Any) -> Any:
            c["setup_leg_ik"] += 1
            return orig_setup_fc(*a, **kw)

        def w_setup_ik(*a: Any, **kw: Any) -> Any:
            c["setup_leg_ik"] += 1
            return orig_setup_ik(*a, **kw)

        def w_pre_fc(*a: Any, **kw: Any) -> Any:
            c["apply_ik_prebend_hint"] += 1
            return orig_pre_fc(*a, **kw)

        def w_pre_ik(*a: Any, **kw: Any) -> Any:
            c["apply_ik_prebend_hint"] += 1
            return orig_pre_ik(*a, **kw)

        def w_eval(*a: Any, **kw: Any) -> Any:
            c["evaluate_foot_support"] += 1
            return orig_eval(*a, **kw)

        def w_leg_fc(*a: Any, **kw: Any) -> Any:
            c["get_leg_ik_state"] += 1
            if kw.get("update_scene", True):
                c["get_leg_ik_state_update_true"] += 1
            return orig_leg_fc(*a, **kw)

        def w_leg_ik(*a: Any, **kw: Any) -> Any:
            c["get_leg_ik_state"] += 1
            if kw.get("update_scene", True):
                c["get_leg_ik_state_update_true"] += 1
            return orig_leg_ik(*a, **kw)

        self._patches = [
            patch.object(bpy, "context", _ContextSpy(bpy.context, c)),
            patch.object(fc_mod, "_ensure_ik_controls", side_effect=w_ensure),
            patch.object(fc_mod, "setup_leg_ik", side_effect=w_setup_fc),
            patch.object(ik_mod, "setup_leg_ik", side_effect=w_setup_ik),
            patch.object(fc_mod, "_apply_ik_prebend_hint", side_effect=w_pre_fc),
            patch.object(ik_mod, "_apply_ik_prebend_hint", side_effect=w_pre_ik),
            patch.object(fc_mod, "evaluate_foot_support", side_effect=w_eval),
            patch.object(fc_mod, "get_leg_ik_state", side_effect=w_leg_fc),
            patch.object(ik_mod, "get_leg_ik_state", side_effect=w_leg_ik),
        ]
        for p in self._patches:
            p.__enter__()
        return self.counters

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for p in reversed(self._patches):
            p.__exit__(exc_type, exc, tb)


def _assert_zero_spy(counters: Dict[str, int], label: str) -> None:
    nonzero = {
        k: counters[k]
        for k in (
            "view_layer_update",
            "scene_frame_set",
            "ensure_ik_controls",
            "setup_leg_ik",
            "apply_ik_prebend_hint",
            "evaluate_foot_support",
            "get_leg_ik_state_update_true",
        )
        if counters[k] != 0
    }
    if nonzero:
        raise AssertionError(f"{label}: zero-side-effect violation in call counters: {nonzero}")


def _assert_support_dict_close(a: Dict[str, Any], b: Dict[str, Any], label: str, tol: float = 1e-6) -> None:
    if set(a.keys()) != _EXPECTED_SUPPORT_KEYS or set(b.keys()) != _EXPECTED_SUPPORT_KEYS:
        raise AssertionError(f"{label}: missing/unexpected support keys")
    for k in _EXPECTED_SUPPORT_KEYS:
        va, vb = a[k], b[k]
        if isinstance(va, Vector):
            if (va - vb).length > tol:
                raise AssertionError(f"{label}[{k}]: {va} != {vb}")
        elif isinstance(va, tuple):
            if len(va) != len(vb) or any(not math.isclose(float(x), float(y), rel_tol=tol, abs_tol=tol) for x, y in zip(va, vb)):
                raise AssertionError(f"{label}[{k}]: {va} != {vb}")
        elif isinstance(va, float):
            if not math.isclose(va, float(vb), rel_tol=tol, abs_tol=tol):
                raise AssertionError(f"{label}[{k}]: {va} != {vb}")
        else:
            if va != vb:
                raise AssertionError(f"{label}[{k}]: {va!r} != {vb!r}")


# =============================================================================
# GROUP A: Lock Metadata Lifecycle (A01 .. A18)
# =============================================================================

def test_a01_fresh_setup() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    for side in ("L", "R"):
        _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES[side]], f"A01.{side}")
    return {"checked_sides": ["L", "R"], "all_keys_absent": True}


def test_a02_setup_clears_existing_locked() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(4.0, -5.0, 6.0))
    lock_foot_contact(arm, "R", target_rotation_deg=(-4.0, 5.0, -6.0))
    _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A02.pre.L")
    _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["R"]], "A02.pre.R")

    setup_leg_ik(arm)
    for side in ("L", "R"):
        _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES[side]], f"A02.post.{side}")
    return {"cleared_both_sides": True}


def test_a03_unilateral_lock_eight_fields() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    res_l = lock_foot_contact(arm, "L", contact_world_xyz=(-0.12, -7.95, 0.0), target_rotation_deg=(5.0, -3.0, 10.0))
    meta_l = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A03.L")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["R"]], "A03.R_still_unlocked")
    assert res_l["is_locked"] is True and res_l["target_rotation_deg"] == (5.0, -3.0, 10.0)

    reset_leg_ik(arm)
    res_r = lock_foot_contact(arm, "R", contact_world_xyz=(0.13, -7.90, 0.0), target_rotation_deg=(-6.0, 4.0, -12.0))
    meta_r = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["R"]], "A03.R")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["L"]], "A03.L_still_unlocked")
    assert res_r["is_locked"] is True and res_r["target_rotation_deg"] == (-6.0, 4.0, -12.0)
    return {"L_fields": len(meta_l) + 1, "R_fields": len(meta_r) + 1}


def test_a04_bilateral_lock_independent() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.14, -7.92, 0.02), target_rotation_deg=(6.0, -2.0, 12.0))
    lock_foot_contact(arm, "R", contact_world_xyz=(0.15, -8.08, 0.0), target_rotation_deg=(-8.0, 5.0, -15.0))
    ml = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A04.L")
    mr = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["R"]], "A04.R")
    assert ml["contact_world_xyz"] != mr["contact_world_xyz"]
    assert ml["locked_ankle_world_xyz"] != mr["locked_ankle_world_xyz"]
    assert ml["target_rotation_deg"] != mr["target_rotation_deg"]
    return {"L_contact": ml["contact_world_xyz"], "R_contact": mr["contact_world_xyz"]}


def test_a05_unlock_left_preserves_right() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(4.0, 2.0, -5.0))
    lock_foot_contact(arm, "R", target_rotation_deg=(-7.0, 3.0, 14.0))
    mr_before = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["R"]], "A05.pre.R")

    unlock_foot_contact(arm, "L")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["L"]], "A05.post.L")
    mr_after = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["R"]], "A05.post.R")
    _assert_meta_equal(mr_after, mr_before, "A05.R_unchanged")
    return {"R_preserved": True}


def test_a06_unlock_right_preserves_left() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(9.0, -4.0, 8.0))
    lock_foot_contact(arm, "R", target_rotation_deg=(-3.0, 6.0, -9.0))
    ml_before = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A06.pre.L")

    unlock_foot_contact(arm, "R")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["R"]], "A06.post.R")
    ml_after = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A06.post.L")
    _assert_meta_equal(ml_after, ml_before, "A06.L_unchanged")
    return {"L_preserved": True}


def test_a07_repeat_unlock_and_legacy_unlocked_cleanup() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L")
    unlock_foot_contact(arm, "L")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["L"]], "A07.first")
    # Repeat unlock
    unlock_foot_contact(arm, "L")
    _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES["L"]], "A07.repeat")
    # Inject legacy unlocked stale metadata on FootIK.L while is_locked=False
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_l["is_locked"] = False
    for k in FOOT_LOCK_METADATA_KEYS:
        ik_l[k] = 0.123 if k == "locked_foot_min_z" else (1.0, 2.0, 3.0)
    unlock_foot_contact(arm, "L")
    _assert_unlocked_clean(ik_l, "A07.legacy_cleaned")
    return {"repeat_and_legacy_cleaned": True}


def test_a08_reset_clears_both_sides() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(5.0, 5.0, 5.0))
    lock_foot_contact(arm, "R", target_rotation_deg=(-5.0, -5.0, -5.0))
    reset_leg_ik(arm)
    for side in ("L", "R"):
        _assert_unlocked_clean(bpy.data.objects[IK_TARGET_NAMES[side]], f"A08.{side}")
    return {"both_cleared_on_reset": True}


def test_a09_relock_new_pose_overwrites_all_seven() -> Dict[str, Any]:
    _, arm, root = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0), target_rotation_deg=(1.0, 2.0, 3.0))
    m1 = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A09.lock1")

    unlock_foot_contact(arm, "L")
    root.location = Vector((0.02, -7.85, 0.03))
    bpy.context.view_layer.update()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.14, -7.82, 0.04), target_rotation_deg=(10.0, -8.0, 18.0))
    m2 = _assert_locked_complete(bpy.data.objects[IK_TARGET_NAMES["L"]], "A09.lock2")
    for k in FOOT_LOCK_METADATA_KEYS:
        assert m2[k] != m1[k], f"A09: key '{k}' failed to update on relock ({m2[k]} == {m1[k]})"
    for a, e in zip(m2["contact_world_xyz"], (-0.14, -7.82, 0.04)):
        assert math.isclose(float(a), e, abs_tol=1e-6), f"A09 contact mismatch: {m2['contact_world_xyz']}"
    for a, e in zip(m2["target_rotation_deg"], (10.0, -8.0, 18.0)):
        assert math.isclose(float(a), e, abs_tol=1e-6), f"A09 rot mismatch: {m2['target_rotation_deg']}"
    return {"all_seven_updated": True}


def test_a10_swing_ik_after_unlock() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L")
    unlock_foot_contact(arm, "L")
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    _assert_unlocked_clean(ik_l, "A10.unlocked")

    swing_res = set_foot_ik_target(
        arm,
        "L",
        world_xyz=(-0.11, -7.82, 0.22),
        foot_rotation_deg=(-12.0, 0.0, 5.0),
    )
    assert float(swing_res["target_error"]) < 0.005, f"A10 swing target_error={swing_res['target_error']}"
    _assert_unlocked_clean(ik_l, "A10.after_swing_ik")
    return {"swing_target_error_m": round(float(swing_res["target_error"]), 6)}


def test_a11_illegal_reparent_and_shear_rejections() -> Dict[str, Any]:
    _, arm, root = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(7.0, -5.0, 9.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    pole_l = bpy.data.objects[POLE_TARGET_NAMES["L"]]
    m_before = _assert_locked_complete(ik_l, "A11.pre")

    # 1. Illegal reparent_to_root=True
    snap1 = _capture_strict_state(arm)
    try:
        unlock_foot_contact(arm, "L", reparent_to_root=True)
        raise AssertionError("A11.1 expected ValueError for reparent_to_root=True")
    except ValueError:
        pass
    _assert_strict_state_identical(snap1, _capture_strict_state(arm), "A11.1")

    # 2. Shear parent matrix on FootIK.L
    shear_parent = bpy.data.objects.new("ShearParent_A11_IK", None)
    bpy.context.scene.collection.objects.link(shear_parent)
    shear_parent.scale = Vector((1.0, 2.2, 1.0))
    shear_parent.rotation_euler = Euler((0.2, 0.3, 0.4), "XYZ")
    bpy.context.view_layer.update()
    ik_l.parent = shear_parent
    ik_l.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()
    snap2 = _capture_strict_state(arm)
    try:
        unlock_foot_contact(arm, "L")
        raise AssertionError("A11.2 expected RuntimeError for FootIK shear")
    except RuntimeError:
        pass
    _assert_strict_state_identical(snap2, _capture_strict_state(arm), "A11.2")

    # Reset FootIK.L clean lock, then apply shear on KneePole.L only
    ik_l.parent = None
    ik_l.matrix_parent_inverse = Matrix.Identity(4)
    lock_foot_contact(arm, "L", target_rotation_deg=(7.0, -5.0, 9.0))
    pole_parent = bpy.data.objects.new("ShearParent_A11_Pole", None)
    bpy.context.scene.collection.objects.link(pole_parent)
    pole_parent.location = Vector((0.0, -8.0, 0.0))
    pole_l.parent = pole_parent
    pole_l.matrix_parent_inverse = Matrix((
        (1.0, 0.5, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    bpy.context.view_layer.update()
    snap3 = _capture_strict_state(arm)
    try:
        unlock_foot_contact(arm, "L")
        raise AssertionError("A11.3 expected RuntimeError for KneePole shear")
    except RuntimeError as exc:
        assert POLE_TARGET_NAMES["L"] in str(exc) or "pole_obj" in str(exc), f"Unexpected msg: {exc}"
    _assert_strict_state_identical(snap3, _capture_strict_state(arm), "A11.3")
    _assert_meta_equal(_assert_locked_complete(ik_l, "A11.post"), m_before, "A11.meta")
    return {"reparent_and_shears_rejected": 3}


def test_a12_unlock_fault_injection_full_rollback() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(11.0, -13.0, 17.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    m_before = _assert_locked_complete(ik_l, "A12.pre")
    snap_before = _capture_strict_state(arm)

    with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_A12")):
        try:
            unlock_foot_contact(arm, "L")
            raise AssertionError("A12 expected RuntimeError")
        except RuntimeError as exc:
            assert "INJECTED_A12" in str(exc)

    bpy.context.view_layer.update()
    _assert_strict_state_identical(snap_before, _capture_strict_state(arm), "A12.post")
    _assert_meta_equal(_assert_locked_complete(ik_l, "A12.meta"), m_before, "A12.meta_exact")
    return {"rolled_back_keys": 7}


def test_a13_partial_metadata_rollback_exact_subset() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(5.0, -7.0, 9.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    # Delete 3 keys to create pre-transaction partial state (4 keys present, 3 missing)
    deleted_subset = ("locked_foot_head_xyz", "locked_foot_tail_xyz", "locked_foot_min_z")
    for k in deleted_subset:
        del ik_l[k]
    kept_subset = tuple(k for k in FOOT_LOCK_METADATA_KEYS if k not in deleted_subset)
    m_before = _read_all_lock_meta(ik_l)
    assert tuple(sorted(m_before.keys())) == tuple(sorted(kept_subset))
    snap_before = _capture_strict_state(arm)

    with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_A13")):
        try:
            unlock_foot_contact(arm, "L")
            raise AssertionError("A13 expected RuntimeError")
        except RuntimeError as exc:
            assert "INJECTED_A13" in str(exc)

    bpy.context.view_layer.update()
    _assert_strict_state_identical(snap_before, _capture_strict_state(arm), "A13.post")
    for k in kept_subset:
        assert k in ik_l
    for k in deleted_subset:
        assert k not in ik_l
    _assert_meta_equal(_read_all_lock_meta(ik_l), m_before, "A13.partial_exact")
    return {"kept": len(kept_subset), "still_absent": len(deleted_subset)}


def test_a14_absent_fields_stay_absent_on_rollback() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_l["is_locked"] = True
    present = ("contact_world_xyz", "locked_ankle_world_xyz")
    absent = tuple(k for k in FOOT_LOCK_METADATA_KEYS if k not in present)
    ik_l["contact_world_xyz"] = (-0.11, -8.0, 0.0)
    ik_l["locked_ankle_world_xyz"] = (-0.11, -8.0, 0.07)
    snap_before = _capture_strict_state(arm)

    with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_A14")):
        try:
            unlock_foot_contact(arm, "L")
            raise AssertionError("A14 expected RuntimeError")
        except RuntimeError as exc:
            assert "INJECTED_A14" in str(exc)

    bpy.context.view_layer.update()
    _assert_strict_state_identical(snap_before, _capture_strict_state(arm), "A14.post")
    for k in absent:
        assert k not in ik_l, f"A14: originally absent key '{k}' was fabricated during rollback"
    return {"absent_preserved": len(absent)}


def test_a15_unrelated_custom_props_preserved() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
    ik_l["diag_note"] = "keep_left"
    ik_l["diag_vec"] = (1.5, 2.5, 3.5)
    ik_r["diag_count"] = 42

    lock_foot_contact(arm, "L")
    assert ik_l["diag_note"] == "keep_left" and _detach_prop(ik_l["diag_vec"]) == (1.5, 2.5, 3.5)
    with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_A15")):
        try:
            unlock_foot_contact(arm, "L")
        except RuntimeError:
            pass
    assert ik_l["diag_note"] == "keep_left" and _detach_prop(ik_l["diag_vec"]) == (1.5, 2.5, 3.5)
    unlock_foot_contact(arm, "L")
    assert ik_l["diag_note"] == "keep_left" and _detach_prop(ik_l["diag_vec"]) == (1.5, 2.5, 3.5)
    reset_leg_ik(arm)
    assert ik_l["diag_note"] == "keep_left" and _detach_prop(ik_l["diag_vec"]) == (1.5, 2.5, 3.5)
    assert ik_r["diag_count"] == 42
    setup_leg_ik(arm)
    assert ik_l["diag_note"] == "keep_left" and _detach_prop(ik_l["diag_vec"]) == (1.5, 2.5, 3.5)
    assert ik_r["diag_count"] == 42
    return {"unrelated_props_preserved_across_all_ops": True}


def test_a16_save_and_subprocess_reopen() -> Dict[str, Any]:
    os.makedirs(SCRATCH_REOPEN_DIR, exist_ok=True)
    saved_assets: List[Dict[str, Any]] = []

    # Case 1: L locked, R unlocked
    _, arm1, _ = _fresh_rig()
    bpy.data.objects[IK_TARGET_NAMES["L"]]["custom_reopen_tag"] = "locked_asset"
    lock_foot_contact(arm1, "L", contact_world_xyz=(-0.12, -7.96, 0.0), target_rotation_deg=(8.0, -10.0, 15.0))
    ml_expected = {k: list(v) if isinstance(v, tuple) else v for k, v in _read_all_lock_meta(bpy.data.objects[IK_TARGET_NAMES["L"]]).items()}
    blend_locked = os.path.join(SCRATCH_REOPEN_DIR, "task11_a16_locked.blend")
    spec_locked = os.path.join(SCRATCH_REOPEN_DIR, "task11_a16_locked_spec.json")
    bpy.ops.wm.save_as_mainfile(filepath=blend_locked)
    with open(spec_locked, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "sides": {
                    "L": {"expected_locked": True, "expected_metadata": ml_expected, "expected_unrelated_props": {"custom_reopen_tag": "locked_asset"}},
                    "R": {"expected_locked": False, "expected_metadata": {}, "expected_unrelated_props": {}},
                }
            },
            fp,
            indent=2,
        )

    # Case 2: L locked then unlocked cleanly
    _, arm2, _ = _fresh_rig()
    bpy.data.objects[IK_TARGET_NAMES["L"]]["custom_reopen_tag"] = "unlocked_asset"
    lock_foot_contact(arm2, "L", target_rotation_deg=(4.0, 5.0, 6.0))
    unlock_foot_contact(arm2, "L")
    blend_unlocked = os.path.join(SCRATCH_REOPEN_DIR, "task11_a16_unlocked.blend")
    spec_unlocked = os.path.join(SCRATCH_REOPEN_DIR, "task11_a16_unlocked_spec.json")
    bpy.ops.wm.save_as_mainfile(filepath=blend_unlocked)
    with open(spec_unlocked, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "sides": {
                    "L": {"expected_locked": False, "expected_metadata": {}, "expected_unrelated_props": {"custom_reopen_tag": "unlocked_asset"}},
                    "R": {"expected_locked": False, "expected_metadata": {}, "expected_unrelated_props": {}},
                }
            },
            fp,
            indent=2,
        )

    for label, bpath, spath in (
        ("locked", blend_locked, spec_locked),
        ("unlocked", blend_unlocked, spec_unlocked),
    ):
        proc = subprocess.run(
            [BLENDER_EXE, "--python-exit-code", "1", "-b", bpath, "-P", REOPEN_SCRIPT, "--", spath],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        assert "REOPEN_VERIFY_RESULT:" in proc.stdout, f"Missing reopen marker for {label}: {proc.stdout}"
        saved_assets.append(
            {
                "case": label,
                "blend_path": bpath,
                "size_bytes": os.path.getsize(bpath),
                "sha256": _sha256(bpath),
                "subprocess_rc": proc.returncode,
            }
        )
    return {"temp_assets": saved_assets}


def test_a17_wbc_continuous_lr_switch_lifecycle() -> Dict[str, Any]:
    cfg, arm, root = _fresh_rig(with_arms=True)
    wbc = WholeBodyController(armature_obj=arm, root_obj=root, config=cfg)
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]

    seq = [
        # (root_y, l_xyz, l_lock, r_xyz, r_lock)
        (-8.00, (-0.11, -8.00, 0.07), True, (0.11, -8.00, 0.07), True),
        (-7.96, (-0.11, -8.00, 0.07), True, (0.11, -7.92, 0.14), False),
        (-7.92, (-0.11, -8.00, 0.07), True, (0.11, -7.84, 0.07), True),
        (-7.88, (-0.11, -7.90, 0.14), False, (0.11, -7.84, 0.07), True),
        (-7.84, (-0.11, -7.76, 0.07), True, (0.11, -7.84, 0.07), True),
    ]
    frame_audit = []
    for f_idx, (ry, l_xyz, l_lock, r_xyz, r_lock) in enumerate(seq, 1):
        tgt = WholeBodyControlTargets()
        tgt.set_root(position=(0.0, ry, 0.0))
        tgt.set_pelvis(location=(0.0, -0.034, 0.0))
        tgt.set_foot("L", target_world_xyz=l_xyz, is_locked=l_lock)
        tgt.set_foot("R", target_world_xyz=r_xyz, is_locked=r_lock)
        res = wbc.execute_frame(tgt)
        assert res.success, f"A17 frame {f_idx} failed: {res.unmet_constraints}"
        if l_lock:
            _assert_locked_complete(ik_l, f"A17.f{f_idx}.L")
        else:
            _assert_unlocked_clean(ik_l, f"A17.f{f_idx}.L")
        if r_lock:
            _assert_locked_complete(ik_r, f"A17.f{f_idx}.R")
        else:
            _assert_unlocked_clean(ik_r, f"A17.f{f_idx}.R")
        frame_audit.append({"frame": f_idx, "L_locked": l_lock, "R_locked": r_lock})
    return {"frames_verified": len(frame_audit)}


def test_a18_wbc_arm_fault_after_leg_write_restores_foot_meta() -> Dict[str, Any]:
    cfg, arm, root = _fresh_rig(with_arms=True)
    wbc = WholeBodyController(armature_obj=arm, root_obj=root, config=cfg)

    # Pre-establish: L locked at anchor1 + custom tag, R unlocked clean
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.00, 0.0), target_rotation_deg=(6.0, -4.0, 10.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
    ik_l["wbc_unrelated"] = "preserve_a18"
    meta_l_before = _assert_locked_complete(ik_l, "A18.pre.L")
    _assert_unlocked_clean(ik_r, "A18.pre.R")
    snap_before = _capture_strict_state(arm)

    # Step 3 will unlock L and lock R, then Step 4 Arm IK fails mid-write
    tgt = WholeBodyControlTargets()
    tgt.set_root(position=(0.02, -7.90, 0.0))
    tgt.set_foot("L", target_world_xyz=(-0.11, -7.85, 0.14), is_locked=False)
    tgt.set_foot("R", target_world_xyz=(0.11, -7.90, 0.07), is_locked=True)
    tgt.set_hand("L", target_world_xyz=(-0.22, -7.70, 1.25), weight=1.0, enabled=True)

    fault_hits = []

    def arm_fault(stage: str, ctx: dict) -> None:
        if stage == "set_hand_ik_target_after_hand_location":
            # Confirm Step 3 already mutated L/R lock metadata before Step 4 fault
            fault_hits.append({"L_locked_mid": bool(ik_l.get("is_locked")), "R_locked_mid": bool(ik_r.get("is_locked"))})
            raise RuntimeError("INJECTED_WBC_ARM_FAULT_A18")

    _set_test_fault_injection_hook(arm_fault)
    try:
        try:
            wbc.execute_frame(tgt)
            raise AssertionError("A18 expected RuntimeError from Arm IK fault")
        except RuntimeError as exc:
            assert "INJECTED_WBC_ARM_FAULT_A18" in str(exc)
    finally:
        _clear_test_fault_injection_hook()
        _PENDING_ARM_RIG_CLEANUPS.clear()
        _ISOLATED_FAILED_ARMATURES.clear()
        _ACTIVE_TRANSACTION_STACK.clear()

    assert len(fault_hits) == 1 and fault_hits[0]["L_locked_mid"] is False and fault_hits[0]["R_locked_mid"] is True
    _assert_strict_state_identical(snap_before, _capture_strict_state(arm), "A18.post")
    _assert_meta_equal(_assert_locked_complete(ik_l, "A18.post.L"), meta_l_before, "A18.L_meta")
    _assert_unlocked_clean(ik_r, "A18.post.R")
    assert ik_l["wbc_unrelated"] == "preserve_a18"
    return {"mid_frame_leg_mutated": fault_hits[0], "full_wbc_foot_restored": True}


# =============================================================================
# GROUP B: Pure Query vs Active Support Maintenance (B01..B18, B20)
# =============================================================================

def test_b01_unlocked_query_zero_side_effects() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    bpy.data.objects[IK_TARGET_NAMES["L"]]["unrelated_prop"] = "b01_l"
    bpy.data.objects[IK_TARGET_NAMES["R"]]["unrelated_prop"] = "b01_r"
    bpy.context.view_layer.update()
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        ql = get_foot_support_state(arm, "L")
        qr = get_foot_support_state(arm, "R")
    _assert_zero_spy(c, "B01")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B01")
    assert set(ql.keys()) == _EXPECTED_SUPPORT_KEYS and set(qr.keys()) == _EXPECTED_SUPPORT_KEYS
    assert ql["is_locked"] is False and qr["is_locked"] is False
    return {"spy": c}


def test_b02_left_locked_query_zero_side_effects() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(4.0, -3.0, 8.0))
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        ql = get_foot_support_state(arm, "L")
    _assert_zero_spy(c, "B02")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B02")
    assert ql["is_locked"] is True and ql["controller_drift"] < 1e-6
    return {"spy": c}


def test_b03_right_locked_query_zero_side_effects() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "R", target_rotation_deg=(-5.0, 4.0, -9.0))
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        qr = get_foot_support_state(arm, "R")
    _assert_zero_spy(c, "B03")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B03")
    assert qr["is_locked"] is True and qr["controller_drift"] < 1e-6
    return {"spy": c}


def test_b04_bilateral_locked_query_zero_side_effects() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.13, -7.95, 0.0), target_rotation_deg=(5.0, -2.0, 9.0))
    lock_foot_contact(arm, "R", contact_world_xyz=(0.14, -8.05, 0.0), target_rotation_deg=(-6.0, 3.0, -11.0))
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        ql = get_foot_support_state(arm, "L")
        qr = get_foot_support_state(arm, "R")
    _assert_zero_spy(c, "B04")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B04")
    assert ql["is_locked"] is True and qr["is_locked"] is True
    assert ql["contact_world"] != qr["contact_world"]
    return {"spy": c}


def test_b05_repeat_alternating_queries_no_accumulation() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(3.0, -2.0, 4.0))
    snap = _capture_strict_state(arm)
    l_outs, r_outs = [], []
    with _SpyScope() as c:
        for side in ("L", "R", "L", "R", "L", "R"):
            res = get_foot_support_state(arm, side)
            (l_outs if side == "L" else r_outs).append(res)
    _assert_zero_spy(c, "B05")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B05")
    for res in l_outs[1:]:
        _assert_support_dict_close(res, l_outs[0], "B05.L_repeat", tol=0.0)
    for res in r_outs[1:]:
        _assert_support_dict_close(res, r_outs[0], "B05.R_repeat", tol=0.0)
    return {"queries_executed": 6, "spy": c}


def test_b06_missing_footik_query_refuses_no_create() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    bpy.data.objects.remove(bpy.data.objects[IK_TARGET_NAMES["L"]], do_unlink=True)
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        try:
            get_foot_support_state(arm, "L")
            raise AssertionError("B06 expected KeyError")
        except KeyError as exc:
            assert IK_TARGET_NAMES["L"] in str(exc)
    _assert_zero_spy(c, "B06")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B06")
    return {"refused_without_creation": True}


def test_b07_missing_kneepole_query_and_locked_maintenance_refuse() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(6.0, -4.0, 8.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    m_before = _assert_locked_complete(ik_l, "B07.pre")
    bpy.data.objects.remove(bpy.data.objects[POLE_TARGET_NAMES["L"]], do_unlink=True)
    snap = _capture_strict_state(arm)

    # 1. Pure query refuses
    with _SpyScope() as c1:
        try:
            get_foot_support_state(arm, "L")
            raise AssertionError("B07.query expected KeyError")
        except KeyError as exc:
            assert POLE_TARGET_NAMES["L"] in str(exc)
    _assert_zero_spy(c1, "B07.query")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B07.query")

    # 2. Active maintenance refuses BEFORE _ensure_ik_controls / setup_leg_ik, leaving lock & metadata untouched
    with _SpyScope() as c2:
        try:
            evaluate_foot_support(arm, "L")
            raise AssertionError("B07.maintain expected KeyError")
        except KeyError as exc:
            assert POLE_TARGET_NAMES["L"] in str(exc)
    _assert_zero_spy(c2, "B07.maintain")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B07.maintain")
    _assert_meta_equal(_assert_locked_complete(ik_l, "B07.post"), m_before, "B07.meta")
    return {"setup_leg_ik_calls": c2["setup_leg_ik"], "ensure_ik_calls": c2["ensure_ik_controls"]}


def test_b08_lock_metadata_missing_and_invalid_formats() -> Dict[str, Any]:
    tested_cases = 0

    # 1. Delete each of 7 keys individually
    for drop_key in FOOT_LOCK_METADATA_KEYS:
        _, arm, _ = _fresh_rig()
        lock_foot_contact(arm, "L")
        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
        del ik_l[drop_key]
        snap = _capture_strict_state(arm)
        for fn_name, fn in (("query", get_foot_support_state), ("maintain", evaluate_foot_support)):
            with _SpyScope() as c:
                try:
                    fn(arm, "L")
                    raise AssertionError(f"B08.{fn_name} missing '{drop_key}' did not raise")
                except ValueError as exc:
                    assert drop_key in str(exc)
            assert c["apply_ik_prebend_hint"] == 0, f"B08.{fn_name} mutated prebend before rejection"
            assert c["view_layer_update"] == 0
            _assert_strict_state_identical(snap, _capture_strict_state(arm), f"B08.{fn_name}.{drop_key}")
            tested_cases += 1

    # 2. Invalid lengths, non-numeric, booleans, dict, NaN/Inf
    bad_mutations = [
        ("contact_world_xyz", (0.1, 0.2), "len2"),
        ("locked_ankle_world_xyz", (0.1, 0.2, 0.3, 0.4), "len4"),
        ("target_rotation_deg", "not_a_vec", "str"),
        ("locked_foot_head_xyz", True, "bool_scalar_on_vec"),
        ("locked_foot_head_xyz", {"x": 0.0, "y": 0.0, "z": 0.0}, "dict_on_vec"),
        ("locked_foot_tail_xyz", (float("nan"), 0.0, 0.0), "nan_elem"),
        ("locked_foot_center_xyz", (0.0, float("inf"), 0.0), "inf_elem"),
        ("locked_foot_min_z", True, "bool_scalar"),
        ("locked_foot_min_z", "zero", "str_scalar"),
        ("locked_foot_min_z", (0.0, 0.0, 0.0), "vec_on_scalar"),
        ("locked_foot_min_z", float("-inf"), "neginf_scalar"),
    ]
    for key, bad_val, tag in bad_mutations:
        _, arm, _ = _fresh_rig()
        lock_foot_contact(arm, "L")
        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_l[key] = bad_val
        snap = _capture_strict_state(arm)
        for fn_name, fn in (("query", get_foot_support_state), ("maintain", evaluate_foot_support)):
            with _SpyScope() as c:
                try:
                    fn(arm, "L")
                    raise AssertionError(f"B08.{fn_name}.{tag} did not raise ValueError")
                except ValueError:
                    pass
            assert c["apply_ik_prebend_hint"] == 0
            _assert_strict_state_identical(snap, _capture_strict_state(arm), f"B08.{fn_name}.{tag}")
            tested_cases += 1

    # 3. Combination: incomplete snapshot + missing KneePole.L
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L")
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    del ik_l["locked_foot_center_xyz"]
    bpy.data.objects.remove(bpy.data.objects[POLE_TARGET_NAMES["L"]], do_unlink=True)
    snap = _capture_strict_state(arm)
    with _SpyScope() as c:
        try:
            evaluate_foot_support(arm, "L")
            raise AssertionError("B08.combo expected rejection")
        except (KeyError, ValueError):
            pass
    assert c["setup_leg_ik"] == 0 and c["ensure_ik_controls"] == 0 and c["apply_ik_prebend_hint"] == 0
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B08.combo")
    tested_cases += 1
    return {"subcases_passed": tested_cases}


def test_b09_unlocked_with_stale_snapshot_neither_consumed_nor_deleted() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    ik_l["is_locked"] = False
    ik_l["contact_world_xyz"] = (9.9, 9.9, 0.0)
    ik_l["locked_ankle_world_xyz"] = (9.9, 9.9, 0.07)
    ik_l["target_rotation_deg"] = (25.0, -15.0, 45.0)
    ik_l["locked_foot_head_xyz"] = (9.9, 9.9, 0.07)
    ik_l["locked_foot_tail_xyz"] = (9.9, 10.1, 0.02)
    ik_l["locked_foot_center_xyz"] = (9.9, 10.0, 0.04)
    ik_l["locked_foot_min_z"] = 5.0
    bpy.context.view_layer.update()
    snap = _capture_strict_state(arm)

    with _SpyScope() as c:
        q = get_foot_support_state(arm, "L")
    _assert_zero_spy(c, "B09")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B09")
    assert q["is_locked"] is False
    assert (q["locked_ankle_world"] - ik_l.matrix_world.translation).length < 1e-6
    assert q["controller_drift"] == 0.0
    for k in FOOT_LOCK_METADATA_KEYS:
        assert k in ik_l, f"B09: query improperly deleted stale key '{k}'"
    return {"stale_keys_intact": 7}


def test_b10_manual_controller_drift_reports_truth_without_repair() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", target_rotation_deg=(0.0, 0.0, 0.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    offset = Vector((0.08, -0.05, 0.03))
    ik_l.location = ik_l.location + offset
    bpy.context.view_layer.update()
    snap = _capture_strict_state(arm)

    with _SpyScope() as c:
        q = get_foot_support_state(arm, "L")
    _assert_zero_spy(c, "B10")
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B10")
    expected_ctrl_drift = offset.length
    assert abs(float(q["controller_drift"]) - expected_ctrl_drift) < 1e-4, (
        f"B10 drift mismatch: {q['controller_drift']} != {expected_ctrl_drift}"
    )
    assert float(q["ankle_bone_drift"]) > 0.02
    return {"measured_ctrl_drift_m": round(float(q["controller_drift"]), 6)}


def test_b11_active_maintenance_restores_locked_position() -> Dict[str, Any]:
    _, arm, root = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0), target_rotation_deg=(5.0, -4.0, 12.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    expected_loc = Vector(ik_l["locked_ankle_world_xyz"])

    # Perturb location & temporarily reparent to simulate external displacement
    ik_l.parent = root
    ik_l.location = ik_l.location + Vector((0.10, 0.08, 0.05))
    bpy.context.view_layer.update()

    maintained = evaluate_foot_support(arm, "L")
    assert ik_l.parent is None
    assert (ik_l.matrix_world.translation - expected_loc).length < 1e-6
    assert maintained["controller_drift"] < 1e-6
    assert maintained["target_rotation_deg"] == (5.0, -4.0, 12.0)
    return {"restored_ctrl_drift_m": round(float(maintained["controller_drift"]), 7)}


def test_b12_active_maintenance_updates_kneepole_formula() -> Dict[str, Any]:
    _, arm, root = _fresh_rig()
    lock_foot_contact(arm, "L")
    root.location = root.location + Vector((0.05, 0.12, -0.02))
    bpy.context.view_layer.update()

    evaluate_foot_support(arm, "L")
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    pole_l = bpy.data.objects[POLE_TARGET_NAMES["L"]]
    hip_world = arm.matrix_world @ arm.pose.bones["thigh.L"].head
    locked_ankle = Vector(ik_l["locked_ankle_world_xyz"])
    expected_pole = Vector((
        hip_world.x,
        max(hip_world.y, locked_ankle.y) + POLE_FORWARD_OFFSET,
        0.5 * (hip_world.z + locked_ankle.z),
    ))
    assert pole_l.parent is None
    diff = (pole_l.matrix_world.translation - expected_pole).length
    assert diff < 1e-5, f"B12 KneePole formula diff={diff}"
    return {"pole_formula_diff_m": round(float(diff), 7)}


def test_b13_root_translation_keeps_locked_foot_world_pinned() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0))
    locked_ankle_exp = Vector((-0.11, -8.0, ANKLE_REST_Z))
    max_ctrl_drift = 0.0
    max_bone_drift = 0.0
    for i in range(1, 9):
        step_root = (0.005 * i, -8.0 + 0.015 * i, -0.004 * i)
        both = move_character_root_with_support(arm, step_root)
        st = both["L"]
        assert st["is_reachable"], f"B13 step {i} unexpectedly unreachable"
        assert (st["controller_world"] - locked_ankle_exp).length < 1e-6
        max_ctrl_drift = max(max_ctrl_drift, float(st["controller_drift"]))
        max_bone_drift = max(max_bone_drift, float(st["ankle_bone_drift"]))
    assert max_ctrl_drift < 1e-6
    return {"max_ctrl_drift_m": round(max_ctrl_drift, 7), "max_bone_drift_m": round(max_bone_drift, 6)}


def test_b14_out_of_reach_reports_unreachable_without_moving_target() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    orig_locked_ankle = Vector(ik_l["locked_ankle_world_xyz"])

    both = move_character_root_with_support(arm, (0.0, -7.45, 0.0))
    st_eval = both["L"]
    st_query = get_foot_support_state(arm, "L")
    for label, st in (("eval", st_eval), ("query", st_query)):
        assert st["is_reachable"] is False, f"B14.{label}: expected is_reachable=False"
        assert st["reach_status"] == "UNREACHABLE", f"B14.{label}: status={st['reach_status']}"
        assert float(st["hip_to_target_dist"]) > MAX_EFFECTIVE_SUPPORT_REACH
        assert float(st["controller_drift"]) < 1e-6
    assert (ik_l.matrix_world.translation - orig_locked_ankle).length < 1e-6
    assert (Vector(ik_l["locked_ankle_world_xyz"]) - orig_locked_ankle).length < 1e-6
    return {"hip_to_target_dist_m": round(float(st_eval["hip_to_target_dist"]), 5)}


def test_b15_get_leg_ik_state_refresh_paths() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    bpy.context.view_layer.update()

    # 1. update_scene=False must not call view_layer.update or init objects
    snap = _capture_strict_state(arm)
    with _SpyScope() as c_no:
        s_no = get_leg_ik_state(arm, "L", update_scene=False)
    assert c_no["view_layer_update"] == 0 and c_no["setup_leg_ik"] == 0
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B15.no_refresh")

    # 2. Mutate ik_l location without updating scene; default update_scene=True refreshes scene once and reads updated target_world
    ik_l.location = ik_l.location + Vector((0.0, 0.05, 0.08))
    with _SpyScope() as c_yes:
        s_yes = get_leg_ik_state(arm, "L")
    assert c_yes["view_layer_update"] == 1
    assert abs(s_yes["target_world"].y - (-8.0 + 0.05)) < 1e-5
    assert set(s_no.keys()) == set(s_yes.keys())
    return {"no_refresh_updates": c_no["view_layer_update"], "default_updates": c_yes["view_layer_update"]}


def test_b16_evaluate_matches_subsequent_pure_query() -> Dict[str, Any]:
    _, arm, root = _fresh_rig()
    # Locked case
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0), target_rotation_deg=(4.0, -3.0, 7.0))
    root.location = root.location + Vector((0.02, 0.06, -0.01))
    bpy.context.view_layer.update()
    eval_locked = evaluate_foot_support(arm, "L")
    with _SpyScope() as c1:
        query_locked = get_foot_support_state(arm, "L")
    _assert_zero_spy(c1, "B16.locked")
    _assert_support_dict_close(eval_locked, query_locked, "B16.locked")

    # Unlocked case
    unlock_foot_contact(arm, "L")
    set_foot_ik_target(arm, "L", (-0.11, -7.88, 0.16))
    eval_unlocked = evaluate_foot_support(arm, "L")
    with _SpyScope() as c2:
        query_unlocked = get_foot_support_state(arm, "L")
    _assert_zero_spy(c2, "B16.unlocked")
    _assert_support_dict_close(eval_unlocked, query_unlocked, "B16.unlocked")
    return {"locked_equal": True, "unlocked_equal": True}


def test_b17_wbc_continuous_lr_support_switching() -> Dict[str, Any]:
    cfg, arm, root = _fresh_rig(with_arms=True)
    wbc = WholeBodyController(armature_obj=arm, root_obj=root, config=cfg)

    steps = [
        (0.00, (-0.11, -8.00, 0.07), True, (0.11, -8.00, 0.07), True),
        (0.04, (-0.11, -8.00, 0.07), True, (0.11, -7.90, 0.14), False),
        (0.08, (-0.11, -8.00, 0.07), True, (0.11, -7.82, 0.07), True),
        (0.12, (-0.11, -7.86, 0.15), False, (0.11, -7.82, 0.07), True),
        (0.18, (-0.11, -7.72, 0.07), True, (0.11, -7.82, 0.07), True),
    ]
    for idx, (dy, l_xyz, l_lk, r_xyz, r_lk) in enumerate(steps, 1):
        tgt = WholeBodyControlTargets()
        tgt.set_root(position=(0.0, -8.0 + dy, 0.0))
        tgt.set_pelvis(location=(0.0, -0.034, 0.0))
        tgt.set_foot("L", target_world_xyz=l_xyz, is_locked=l_lk)
        tgt.set_foot("R", target_world_xyz=r_xyz, is_locked=r_lk)
        res = wbc.execute_frame(tgt)
        assert res.success, f"B17 step {idx} failed"
        ql = get_foot_support_state(arm, "L")
        qr = get_foot_support_state(arm, "R")
        assert ql["is_locked"] is l_lk and qr["is_locked"] is r_lk
        if l_lk:
            assert (ql["controller_world"] - Vector(l_xyz)).length < 1e-4
        if r_lk:
            assert (qr["controller_world"] - Vector(r_xyz)).length < 1e-4
    return {"steps_verified": len(steps)}


def test_b18_playground_stage_d_bridge_no_duplicate_eval() -> Dict[str, Any]:
    cfg, arm, root = _fresh_rig(with_arms=True)
    # Match DynamicsPlayground Stage D root placement at Surface_FlatGround (-8.0)
    root.location = Vector((0.0, -8.0, 0.0))
    reset_leg_ik(arm)
    bpy.context.view_layer.update()
    env_query = create_standard_dynamics_playground_query()
    stage_tmp = os.path.join(SCRATCH_REOPEN_DIR, "b18_stage_tmp")
    os.makedirs(stage_tmp, exist_ok=True)

    in_bridge = [False]
    stage_d_active = [False]
    counters = {
        "eval_outside_bridge_in_stage_d": 0,
        "eval_inside_bridge_in_stage_d": 0,
        "query_outside_bridge_in_stage_d": 0,
    }
    orig_exec = KinematicBridgeExecutor.execute_frame
    orig_eval = fc_mod.evaluate_foot_support
    orig_unlock = pca_mod.unlock_foot_contact
    orig_pca_query = pca_mod.get_foot_support_state

    def w_exec(self_bridge: Any, pose: Any, *args: Any, **kwargs: Any) -> Any:
        if int(pose.frame) >= 10:
            stage_d_active[0] = True
        in_bridge[0] = True
        try:
            return orig_exec(self_bridge, pose, *args, **kwargs)
        finally:
            in_bridge[0] = False

    def w_eval(*args: Any, **kwargs: Any) -> Any:
        if stage_d_active[0]:
            if in_bridge[0]:
                counters["eval_inside_bridge_in_stage_d"] += 1
            else:
                counters["eval_outside_bridge_in_stage_d"] += 1
        return orig_eval(*args, **kwargs)

    def w_pca_query(*args: Any, **kwargs: Any) -> Any:
        if stage_d_active[0] and not in_bridge[0]:
            counters["query_outside_bridge_in_stage_d"] += 1
        return orig_pca_query(*args, **kwargs)

    with (
        patch.object(KinematicBridgeExecutor, "execute_frame", w_exec),
        patch.object(fc_mod, "evaluate_foot_support", w_eval),
        patch.object(pca_mod, "get_foot_support_state", w_pca_query),
        patch.object(pca_mod, "unlock_foot_contact", orig_unlock),
    ):
        report = pca_mod.run_minimal_control_stages_verification(
            arm_obj=arm,
            root_obj=root,
            config=cfg,
            env_query=env_query,
            cameras={},
            evidence_dir=stage_tmp,
            render_images=False,
        )

    assert not hasattr(pca_mod, "evaluate_foot_support"), "B18: playground_character_assembly still imports evaluate_foot_support"
    stage_d = report["stage_D_support_foot_lock"]
    assert stage_d["all_steps_succeeded"] is True
    assert counters["eval_outside_bridge_in_stage_d"] == 0, (
        f"B18: Stage D called evaluate_foot_support outside bridge: {counters}"
    )
    assert counters["query_outside_bridge_in_stage_d"] == 5, (
        f"B18: expected 5 Stage D pure queries, got {counters}"
    )
    return {"stage_d_steps": len(stage_d["steps"]), **counters}


def test_b20_unlock_world_transform_explicit_prebend_and_rollback() -> Dict[str, Any]:
    _, arm, _ = _fresh_rig()
    lock_foot_contact(arm, "L", contact_world_xyz=(-0.11, -8.0, 0.0), target_rotation_deg=(12.0, -14.0, 22.0))
    ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
    pole_l = bpy.data.objects[POLE_TARGET_NAMES["L"]]
    ik_mat_before = ik_l.matrix_world.copy()
    pole_mat_before = pole_l.matrix_world.copy()

    # 1. Fault-injection rollback check
    snap = _capture_strict_state(arm)
    with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_B20")):
        try:
            unlock_foot_contact(arm, "L")
            raise AssertionError("B20 rollback expected RuntimeError")
        except RuntimeError:
            pass
    bpy.context.view_layer.update()
    _assert_strict_state_identical(snap, _capture_strict_state(arm), "B20.rollback")

    # 2. Normal unlock must explicitly execute _apply_ik_prebend_hint and view_layer.update inside Phase B
    with _SpyScope() as c:
        res_unlock = unlock_foot_contact(arm, "L")
    assert c["apply_ik_prebend_hint"] >= 1, "B20: explicit Phase B prebend did not execute"
    assert c["view_layer_update"] >= 2, "B20: view_layer updates did not execute"
    assert c["evaluate_foot_support"] == 0, "B20: unlock must use pure query at end"
    assert ik_l.parent is None and pole_l.parent is None
    assert max(abs(ik_l.matrix_world[r][col] - ik_mat_before[r][col]) for r in range(4) for col in range(4)) < 1e-5
    assert max(abs(pole_l.matrix_world[r][col] - pole_mat_before[r][col]) for r in range(4) for col in range(4)) < 1e-5
    _assert_unlocked_clean(ik_l, "B20.post_unlock")
    with _SpyScope() as c_after:
        q_after = get_foot_support_state(arm, "L")
    _assert_zero_spy(c_after, "B20.post_query")
    _assert_support_dict_close(res_unlock, q_after, "B20.match")
    return {"unlock_prebend_calls": c["apply_ik_prebend_hint"], "unlock_updates": c["view_layer_update"]}


# =============================================================================
# SECTION 7: Continuous Production Chain (5 Actions + Central Bilateral Upper-Limb)
# =============================================================================

def test_continuous_production_chain() -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    def _run_action_chain(
        label: str,
        start_pos: Tuple[float, float, float],
        env: EnvironmentQuery,
        actions_fn: Callable[[PipelineConfig, EnvironmentQuery], List[Any]],
        upper_l: Optional[Tuple[UpperLimbSegment, ...]] = None,
        upper_r: Optional[Tuple[UpperLimbSegment, ...]] = None,
        seq_dur_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        cfg, arm, _ = _fresh_rig(with_arms=True)
        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
        orig_ef = KinematicBridgeExecutor.execute_frame
        stats = {
            "frames": 0,
            "locked_checks_L": 0,
            "unlocked_checks_L": 0,
            "locked_checks_R": 0,
            "unlocked_checks_R": 0,
            "lr_lock_transitions": 0,
            "max_locked_ctrl_drift_m": 0.0,
        }
        prev_locks: Optional[Tuple[bool, bool]] = None

        @functools.wraps(orig_ef)
        def obs_ef(self_b: Any, planned: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal prev_locks
            res = orig_ef(self_b, planned, *args, **kwargs)
            assert res.success, f"{label} frame {planned.frame} bridge failed: {res.unmet_constraints}"
            stats["frames"] += 1

            cur_l = bool(ik_l.get("is_locked", False))
            cur_r = bool(ik_r.get("is_locked", False))
            if prev_locks is not None and (cur_l, cur_r) != prev_locks:
                stats["lr_lock_transitions"] += 1
            prev_locks = (cur_l, cur_r)

            for side, ik_obj, foot_tgt in (("L", ik_l, planned.foot_L), ("R", ik_r, planned.foot_R)):
                if foot_tgt is None:
                    continue
                if foot_tgt.is_locked:
                    _assert_locked_complete(ik_obj, f"{label}.f{planned.frame}.{side}")
                    q = get_foot_support_state(arm, side)
                    assert q["is_locked"] is True and ik_obj.parent is None
                    stats["max_locked_ctrl_drift_m"] = max(stats["max_locked_ctrl_drift_m"], float(q["controller_drift"]))
                    stats[f"locked_checks_{side}"] += 1
                else:
                    _assert_unlocked_clean(ik_obj, f"{label}.f{planned.frame}.{side}")
                    q = get_foot_support_state(arm, side)
                    assert q["is_locked"] is False
                    stats[f"unlocked_checks_{side}"] += 1
            return res

        planner = MotionPlanner(
            config=cfg,
            armature_obj=arm,
            environment=env,
            upper_limb_L=upper_l,
            upper_limb_R=upper_r,
            sequence_duration_sec=seq_dur_sec,
        )
        for act in actions_fn(cfg, env):
            planner.add_action(act)

        with patch.object(KinematicBridgeExecutor, "execute_frame", obs_ef):
            out = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=start_pos))
        assert out["total_frames"] == stats["frames"]
        assert stats["max_locked_ctrl_drift_m"] < 1e-4
        return stats

    # 1. StartStopWalkAction + Central Bilateral Independent Upper-Limb (L FK + R IK)
    cfg_probe = PipelineConfig()
    seq_dur = (cfg_probe.start_stop_total_frames - 1) / float(cfg_probe.fps)
    central_fk_l = (
        UpperLimbSegment(
            mode="FK",
            start_time_sec=0.2,
            duration_sec=2.0,
            fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((40.0, 10.0, 20.0), (50.0, 12.0, 0.0), (10.0, 4.0, 6.0)),
        ),
        UpperLimbSegment(
            mode="FK",
            start_time_sec=2.4,
            duration_sec=2.2,
            fk_start_deg=((40.0, 10.0, 20.0), (50.0, 12.0, 0.0), (10.0, 4.0, 6.0)),
            fk_end_deg=((15.0, -5.0, 10.0), (25.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),
    )
    central_ik_r = (
        UpperLimbSegment(
            mode="IK",
            start_time_sec=0.2,
            duration_sec=2.0,
            wrist_start_xyz=(0.24, 0.16, 1.15),
            wrist_end_xyz=(0.30, 0.24, 1.32),
            pole_start_xyz=(0.30, -0.22, 1.18),
            pole_end_xyz=(0.34, -0.22, 1.20),
            rotation_start_deg=(0.0, 0.0, 0.0),
            rotation_end_deg=(8.0, -4.0, -6.0),
            position_space="ROOT_LOCAL",
            clamp_reach=True,
        ),
        UpperLimbSegment(
            mode="IK",
            start_time_sec=2.4,
            duration_sec=2.0,
            wrist_start_xyz=(0.30, 0.24, 1.32),
            wrist_end_xyz=(0.24, 0.16, 1.18),
            pole_start_xyz=(0.34, -0.22, 1.20),
            pole_end_xyz=(0.30, -0.22, 1.18),
            rotation_start_deg=(8.0, -4.0, -6.0),
            rotation_end_deg=(0.0, 0.0, 0.0),
            position_space="ROOT_LOCAL",
            clamp_reach=True,
        ),
    )
    summary["StartStopWalk_with_central_bilateral_upper"] = _run_action_chain(
        "StartStopWalk_central",
        (0.0, -8.0, 0.0),
        EnvironmentQuery(ground_z=0.0),
        lambda c, e: [StartStopWalkAction()],
        upper_l=central_fk_l,
        upper_r=central_ik_r,
        seq_dur_sec=seq_dur,
    )

    # 2. TerrainWalkAction
    flat_route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30,
        step_frames=16,
        stand_start_frames=24,
        stand_stop_frames=24,
    )
    summary["TerrainWalk"] = _run_action_chain(
        "TerrainWalk",
        (0.0, 10.20, 0.0),
        create_standard_dynamics_playground_query(),
        lambda c, e: [TerrainWalkAction(route=flat_route, environment=e)],
    )

    # 3. RunAction
    summary["Run"] = _run_action_chain(
        "Run",
        (0.0, 0.0, 0.0),
        EnvironmentQuery(ground_z=0.0),
        lambda c, e: [RunAction(cycles=2)],
    )

    # 4 & 5. SprintStartAction -> SprintBrakeAction
    summary["SprintStart_SprintBrake"] = _run_action_chain(
        "SprintStart_SprintBrake",
        (0.0, 0.0, 0.0),
        EnvironmentQuery(ground_z=0.0),
        lambda c, e: [SprintStartAction(), SprintBrakeAction()],
    )
    return summary


# =============================================================================
# Runner Orchestration
# =============================================================================

def main() -> int:
    tests: List[Tuple[str, str, Callable[[], Dict[str, Any]]]] = [
        ("A01", "Fresh setup leaves is_locked=False and all 7 metadata keys absent", test_a01_fresh_setup),
        ("A02", "Setup on already-locked controller clears all 7 metadata keys", test_a02_setup_clears_existing_locked),
        ("A03", "Unilateral L/R locks populate all 8 fields cleanly", test_a03_unilateral_lock_eight_fields),
        ("A04", "Bilateral simultaneous locks maintain independent snapshots", test_a04_bilateral_lock_independent),
        ("A05", "Unlocking L preserves R is_locked and all 7 metadata keys", test_a05_unlock_left_preserves_right),
        ("A06", "Unlocking R preserves L is_locked and all 7 metadata keys", test_a06_unlock_right_preserves_left),
        ("A07", "Repeat unlock and legacy unlocked stale metadata cleanup", test_a07_repeat_unlock_and_legacy_unlocked_cleanup),
        ("A08", "Reset clears lock flag and all 7 metadata keys on both sides", test_a08_reset_clears_both_sides),
        ("A09", "Relocking at new position/rotation updates all 7 keys to new geometry", test_a09_relock_new_pose_overwrites_all_seven),
        ("A10", "Normal swing foot IK executes cleanly after unlock", test_a10_swing_ik_after_unlock),
        ("A11", "Illegal reparent, FootIK shear, KneePole shear reject atomically", test_a11_illegal_reparent_and_shear_rejections),
        ("A12", "Phase B fault injection rolls back is_locked and all 7 metadata keys", test_a12_unlock_fault_injection_full_rollback),
        ("A13", "Rollback restores exact partial metadata subset & values", test_a13_partial_metadata_rollback_exact_subset),
        ("A14", "Rollback leaves originally absent metadata fields absent", test_a14_absent_fields_stay_absent_on_rollback),
        ("A15", "Unrelated custom properties remain intact across all lifecycle ops", test_a15_unrelated_custom_props_preserved),
        ("A16", "Saved locked/unlocked blends reopen cleanly in independent Blender processes", test_a16_save_and_subprocess_reopen),
        ("A17", "WBC continuous L/R lock switching enforces per-frame metadata lifecycle", test_a17_wbc_continuous_lr_switch_lifecycle),
        ("A18", "WBC upper-limb failure after leg writes restores pre-frame foot metadata", test_a18_wbc_arm_fault_after_leg_write_restores_foot_meta),
        ("B01", "Unlocked pure query has zero side effects", test_b01_unlocked_query_zero_side_effects),
        ("B02", "Left-locked pure query has zero side effects", test_b02_left_locked_query_zero_side_effects),
        ("B03", "Right-locked pure query has zero side effects", test_b03_right_locked_query_zero_side_effects),
        ("B04", "Bilateral-locked pure query has zero side effects", test_b04_bilateral_locked_query_zero_side_effects),
        ("B05", "Repeated/alternating pure queries cause zero cumulative state change", test_b05_repeat_alternating_queries_no_accumulation),
        ("B06", "Missing FootIK causes pure query rejection without creating objects", test_b06_missing_footik_query_refuses_no_create),
        ("B07", "Missing KneePole rejects pure query & locked evaluate_foot_support without setup_leg_ik", test_b07_missing_kneepole_query_and_locked_maintenance_refuse),
        ("B08", "All 7 metadata missing/invalid formats & missing KneePole combo reject before writes", test_b08_lock_metadata_missing_and_invalid_formats),
        ("B09", "Unlocked state with stale metadata neither consumes nor deletes stale fields", test_b09_unlocked_with_stale_snapshot_neither_consumed_nor_deleted),
        ("B10", "Drifted locked controller pure query reports real drift without repairing", test_b10_manual_controller_drift_reports_truth_without_repair),
        ("B11", "Active maintenance restores locked world coordinate & parentless state", test_b11_active_maintenance_restores_locked_position),
        ("B12", "Active maintenance updates KneePole world location by exact formula", test_b12_active_maintenance_updates_kneepole_formula),
        ("B13", "Continuous root movement maintains locked foot world reference position", test_b13_root_translation_keeps_locked_foot_world_pinned),
        ("B14", "Out-of-reach root reports UNREACHABLE without moving locked target", test_b14_out_of_reach_reports_unreachable_without_moving_target),
        ("B15", "get_leg_ik_state default refresh vs update_scene=False paths", test_b15_get_leg_ik_state_refresh_paths),
        ("B16", "evaluate_foot_support result matches immediate subsequent pure query", test_b16_evaluate_matches_subsequent_pure_query),
        ("B17", "WBC continuous L/R support switching & active maintenance integration", test_b17_wbc_continuous_lr_support_switching),
        ("B18", "playground_character_assembly Stage D measures post-Bridge via pure query only", test_b18_playground_stage_d_bridge_no_duplicate_eval),
        ("B20", "unlock_foot_contact preserves transforms, runs Phase B prebend, and rolls back on fault", test_b20_unlock_world_transform_explicit_prebend_and_rollback),
        ("CHAIN", "Continuous production chain (5 actions + central bilateral upper-limb)", test_continuous_production_chain),
    ]

    results: Dict[str, Any] = {}
    all_passed = True
    for tid, desc, fn in tests:
        print(f"[{tid}] Running: {desc}")
        try:
            detail = fn()
            results[tid] = {"status": "PASSED", "description": desc, "detail": detail}
            print(f"[{tid}] PASSED: {json.dumps(detail, ensure_ascii=False)}")
        except Exception as exc:
            all_passed = False
            tb = traceback.format_exc()
            results[tid] = {
                "status": "FAILED",
                "description": desc,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": tb,
            }
            print(f"[FAIL] [{tid}] {type(exc).__name__}: {exc}\n{tb}", file=sys.stderr)
            break

    payload = {
        "generated_at": datetime.datetime.now().isoformat(),
        "blender_version": bpy.app.version_string,
        "all_passed": all_passed,
        "executed_count": len(results),
        "total_in_script": len(tests),
        "results": results,
    }
    os.makedirs(THIS_DIR, exist_ok=True)
    with open(CONTRACT_RESULTS_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)

    print(f"TASK11_CONTRACT_SUITE_DONE all_passed={all_passed} executed={len(results)}/{len(tests)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
