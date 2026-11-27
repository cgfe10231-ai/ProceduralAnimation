"""TASK 12-D Group B: Bridge Frame Commit, Timing Admission & 7-State Consistency Verification (B01-B19).

B20 (Save & Reopen) is verified by independent Blender subprocesses in `verify_reopen.py`.

Run via real Blender 5.1.1:
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P docs/evidence/12/unified_verification/verify_bridge_commit_contract.py
"""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
import traceback
from dataclasses import replace as dc_replace
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import src.motion.kinematic_bridge as kb_mod
from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.body_kinematics import compute_differential_velocity, create_zero_velocity_state
from src.motion.framework import (
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    StartStopWalkAction,
    SurfaceQueryResult,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.run_cycle import RunAction
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import UpperLimbSegment
from src.rig.arm_ik import ARM_IK_CONSTRAINT_NAMES, HAND_ROT_CONSTRAINT_NAMES, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, setup_leg_ik
from src.rig.pose import reset_pose

OUTPUT_JSON = os.path.join(THIS_DIR, "bridge_results.json")


def _clean_scene(y_root: float = -8.0, env: Optional[EnvironmentQuery] = None) -> Tuple[bpy.types.Object, bpy.types.Object, KinematicBridgeExecutor]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    root = arm.parent or bpy.data.objects.get("CharacterRoot")
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    if root is not None:
        root.location = Vector((0.0, y_root, 0.0))
    bpy.context.view_layer.update()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root, environment=env)
    return arm, root, bridge


def _make_pose(
    frame: int,
    time_seconds: float,
    y_root: float = -8.0,
    dt: Optional[float] = None,
    hand_l: Optional[PlannedHandTarget] = None,
    foot_r_xyz: Optional[Tuple[float, float, float]] = None,
    foot_r_locked: bool = True,
    foot_r_clamp: bool = True,
    spine_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> KinematicPlannedPose:
    return KinematicPlannedPose(
        frame=frame,
        time_seconds=time_seconds,
        root_position=(0.0, y_root, 0.0),
        pelvis_location=(0.0, -0.02, 0.0),
        dt=dt,
        spine_rotation_deg=spine_deg,
        foot_L=PlannedFootTarget(world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(
            world_xyz=foot_r_xyz or (HIP_X_OFFSET, y_root, ANKLE_REST_Z),
            is_locked=foot_r_locked,
            clamp_reach=foot_r_clamp,
        ),
        hand_L=hand_l,
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
    )


def _capture_seven_states(bridge: KinematicBridgeExecutor) -> Dict[str, Any]:
    tr = bridge.kinematics_tracker
    return {
        "_last_time_sec": bridge._last_time_sec,
        "_last_frame": bridge._last_frame,
        "last_multi_contact_id": id(bridge.last_multi_contact) if bridge.last_multi_contact is not None else None,
        "last_multi_contact": bridge.last_multi_contact,
        "last_active_limb_targets_id": id(bridge.last_active_limb_targets) if bridge.last_active_limb_targets is not None else None,
        "last_active_limb_targets": bridge.last_active_limb_targets,
        "_prev_snapshot_id": id(tr._prev_snapshot) if tr._prev_snapshot is not None else None,
        "_prev_snapshot": tr._prev_snapshot,
        "_prev_velocity_id": id(tr._prev_velocity) if tr._prev_velocity is not None else None,
        "_prev_velocity": tr._prev_velocity,
        "_history_id": id(tr._history),
        "_history_len": len(tr._history),
        "_history_copy": list(tr._history),
    }


def _assert_seven_states_unchanged(bridge: KinematicBridgeExecutor, snap: Dict[str, Any], label: str) -> None:
    cur = _capture_seven_states(bridge)
    assert cur["_last_time_sec"] == snap["_last_time_sec"], f"{label}: _last_time_sec mutated {snap['_last_time_sec']} -> {cur['_last_time_sec']}"
    assert cur["_last_frame"] == snap["_last_frame"], f"{label}: _last_frame mutated {snap['_last_frame']} -> {cur['_last_frame']}"
    assert cur["last_multi_contact_id"] == snap["last_multi_contact_id"], f"{label}: last_multi_contact identity changed"
    assert cur["last_active_limb_targets_id"] == snap["last_active_limb_targets_id"], f"{label}: last_active_limb_targets identity changed"
    assert cur["_prev_snapshot_id"] == snap["_prev_snapshot_id"], f"{label}: _prev_snapshot identity changed"
    assert cur["_prev_velocity_id"] == snap["_prev_velocity_id"], f"{label}: _prev_velocity identity changed"
    assert cur["_history_id"] == snap["_history_id"], f"{label}: _history list identity changed"
    assert cur["_history_len"] == snap["_history_len"], f"{label}: _history len changed {snap['_history_len']} -> {cur['_history_len']}"
    assert cur["_history_copy"] == snap["_history_copy"], f"{label}: _history contents mutated"


def _collect_action_frames(obj: Optional[bpy.types.Object]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    if obj is None or obj.animation_data is None or obj.animation_data.action is None:
        return out
    adt = obj.animation_data
    act = adt.action
    groups = []
    if hasattr(act, "layers") and adt.action_slot is not None:
        for layer in act.layers:
            for strip in layer.strips:
                cb = strip.channelbag(adt.action_slot)
                if cb is not None:
                    groups.append(cb.fcurves)
    elif hasattr(act, "fcurves"):
        groups.append(act.fcurves)
    for fcurves in groups:
        for fc in fcurves:
            out.setdefault(fc.data_path, []).extend(round(float(kp.co[0]), 4) for kp in fc.keyframe_points)
    for k in list(out.keys()):
        out[k] = sorted(out[k])
    return out


def _collect_all_action_frames(arm: bpy.types.Object, root: bpy.types.Object) -> Dict[str, Dict[str, List[float]]]:
    res = {"root": _collect_action_frames(root), "arm": _collect_action_frames(arm)}
    for name in ("FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R", "HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
        res[name] = _collect_action_frames(bpy.data.objects.get(name))
    return res


def test_b01() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    wbc_calls = [0]
    diff_calls = [0]
    orig_wbc = bridge.controller.execute_frame
    orig_diff = compute_differential_velocity

    def spy_wbc(*a, **kw):
        wbc_calls[0] += 1
        return orig_wbc(*a, **kw)

    def spy_diff(*a, **kw):
        diff_calls[0] += 1
        return orig_diff(*a, **kw)

    with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc), patch(
        "src.motion.body_kinematics.compute_differential_velocity", side_effect=spy_diff
    ):
        r1 = bridge.execute_frame(_make_pose(1, 0.0, -8.0, hand_l=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0)), keyframe=True)
        r2 = bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z), foot_r_locked=False), keyframe=True)

    assert r1.success and r2.success
    assert wbc_calls[0] == 2 and diff_calls[0] == 1, f"Expected wbc=2 diff=1, got wbc={wbc_calls[0]} diff={diff_calls[0]}"
    assert bridge._last_frame == 2 and math.isclose(bridge._last_time_sec, 1.0 / 24.0, abs_tol=1e-7)
    assert bridge.last_multi_contact is r2.multi_contact
    assert len(bridge.kinematics_tracker._history) == 2
    arm_fcurves = _collect_action_frames(arm)
    for side in ("L", "R"):
        for path in (
            f'pose.bones["forearm.{side}"].constraints["{ARM_IK_CONSTRAINT_NAMES[side]}"].influence',
            f'pose.bones["hand.{side}"].constraints["{HAND_ROT_CONSTRAINT_NAMES[side]}"].influence',
        ):
            assert arm_fcurves.get(path) == [1.0, 2.0], f"Missing keyframes on {path}: {arm_fcurves.get(path)}"
    return {"wbc_calls": wbc_calls[0], "diff_calls": diff_calls[0], "history_len": len(bridge.kinematics_tracker._history)}


def test_b02() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
    snap = _capture_seven_states(bridge)
    kf_before = _collect_all_action_frames(arm, root)

    r_fail = bridge.execute_frame(
        _make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -5.0, ANKLE_REST_Z), foot_r_locked=False, foot_r_clamp=False),
        keyframe=True,
    )
    assert r_fail.success is False
    assert r_fail.motion_state is not None and any(u.category == "REACHABILITY" for u in r_fail.unmet_constraints)
    assert _collect_all_action_frames(arm, root) == kf_before, "B02 polluted keyframes on unreachable WBC failure"
    _assert_seven_states_unchanged(bridge, snap, "B02")
    return {"unmet": [u.category for u in r_fail.unmet_constraints], "keyframes_preserved": True}


def test_b03() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
    snap = _capture_seven_states(bridge)
    kf_before = _collect_all_action_frames(arm, root)

    r_fail = bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, spine_deg=(85.0, 0.0, 0.0)), keyframe=True)
    assert r_fail.success is False and r_fail.wbc_result.has_rom_violation is True
    assert r_fail.motion_state is not None
    assert _collect_all_action_frames(arm, root) == kf_before, "B03 polluted keyframes on ROM failure"
    _assert_seven_states_unchanged(bridge, snap, "B03")
    return {"rom_violations": list(r_fail.rom_violations.keys()), "keyframes_preserved": True}


def test_b04() -> Dict[str, Any]:
    class VoidEnv(EnvironmentQuery):
        def query_ground_support_at(self, x: float, y: float, **kwargs) -> SurfaceQueryResult:
            return SurfaceQueryResult(
                surface_id="none",
                surface_type="horizontal_ground",
                contact_point_world=(x, y, -999.0),
                surface_normal_world=(0.0, 0.0, 1.0),
                signed_distance=-999.0,
                friction_coeff=0.0,
                allows_regular_support=False,
                success=False,
                error_reason="Void surface (B04)",
            )

    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
    snap = _capture_seven_states(bridge)
    kf_before = _collect_all_action_frames(arm, root)

    bridge.environment = VoidEnv()
    r_fail = bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98), keyframe=True)
    assert r_fail.success is False
    assert r_fail.multi_contact is not None and "foot_L" in r_fail.contact_geometry_errors
    assert _collect_all_action_frames(arm, root) == kf_before, "B04 polluted keyframes on ContactModel geometry failure"
    _assert_seven_states_unchanged(bridge, snap, "B04")
    return {"contact_geom_errors": list(r_fail.contact_geometry_errors.keys())}


def test_b05() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    r_fail = bridge.execute_frame(_make_pose(1, 0.0, -8.0, spine_deg=(85.0, 0.0, 0.0)), keyframe=True)
    assert r_fail.success is False
    assert r_fail.motion_state is not None and r_fail.multi_contact is not None
    assert bridge._last_time_sec is None and bridge._last_frame is None
    assert bridge.last_multi_contact is None and bridge.last_active_limb_targets is None
    tr = bridge.kinematics_tracker
    assert tr._prev_snapshot is None and tr._prev_velocity is None and len(tr._history) == 0
    assert all(len(v) == 0 for v in _collect_all_action_frames(arm, root).values())
    return {"first_frame_uncommitted": True}


def test_b06() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    r1 = bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True)
    assert r1.success
    snap = _capture_seven_states(bridge)
    r2 = bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, spine_deg=(88.0, 0.0, 0.0)), keyframe=True)
    assert r2.success is False
    _assert_seven_states_unchanged(bridge, snap, "B06")
    return {"seven_states_preserved": True}


def test_b07() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
    snap = _capture_seven_states(bridge)
    kf_before = _collect_all_action_frames(arm, root)
    for idx in range(3):
        rf = bridge.execute_frame(_make_pose(2 + idx, (1 + idx) / 24.0, -7.98, spine_deg=(80.0 + idx, 0.0, 0.0)), keyframe=True)
        assert rf.success is False
        _assert_seven_states_unchanged(bridge, snap, f"B07[{idx}]")
    assert _collect_all_action_frames(arm, root) == kf_before
    return {"consecutive_failures": 3, "history_len": len(bridge.kinematics_tracker._history)}


def test_b08() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    # Retry failed frame 1
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0, spine_deg=(85.0, 0.0, 0.0)), keyframe=True).success is False
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success is True
    # Fail frame 2, then retry corrected frame 2
    assert bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, spine_deg=(85.0, 0.0, 0.0)), keyframe=True).success is False
    assert bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z), foot_r_locked=False), keyframe=True).success is True
    assert bridge._last_frame == 2 and len(bridge.kinematics_tracker._history) == 2
    return {"retried_frame1_and_frame2_committed": 2}


def _run_track_b09_b10(with_failure: bool) -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=False).success
    if with_failure:
        rf = bridge.execute_frame(
            _make_pose(2, 1.0 / 24.0, -7.90, foot_r_xyz=(HIP_X_OFFSET, -5.0, ANKLE_REST_Z), foot_r_locked=False, foot_r_clamp=False),
            keyframe=False,
        )
        assert rf.success is False
    # Next valid frame moves forward +0.04m at frame 3, t=2/24 -> compared against Frame 1 (both tracks skip valid Frame 2 so dt=2/24!)
    r2 = bridge.execute_frame(_make_pose(3, 2.0 / 24.0, -7.96, foot_r_xyz=(HIP_X_OFFSET, -7.94, ANKLE_REST_Z), foot_r_locked=False), keyframe=False)
    r3 = bridge.execute_frame(_make_pose(4, 3.0 / 24.0, -7.90, foot_r_xyz=(HIP_X_OFFSET, -7.88, ANKLE_REST_Z), foot_r_locked=False), keyframe=False)
    assert r2.success and r3.success
    vel3 = bridge.kinematics_tracker._history[-1].velocity
    iner3 = r3.inertia_state
    return {
        "v_root": vel3.root_linear_velocity,
        "w_root": vel3.root_angular_velocity,
        "v_com": vel3.com_linear_velocity,
        "a_root": vel3.root_linear_acceleration,
        "alpha_root": vel3.root_angular_acceleration,
        "a_com": vel3.com_linear_acceleration,
        "H_total": iner3.angular_momentum_body_com,
        "H_spin": iner3.spin_angular_momentum_total,
        "H_orbital": iner3.orbital_angular_momentum_total,
    }


def _assert_vec_dict_close(d1: Dict[str, Tuple[float, float, float]], d2: Dict[str, Tuple[float, float, float]], tol: float = 1e-7) -> None:
    for k in d1:
        for a, b in zip(d1[k], d2[k]):
            assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), f"{k} mismatch: {d1[k]} != {d2[k]}"


def test_b09() -> Dict[str, Any]:
    clean = _run_track_b09_b10(with_failure=False)
    dirty = _run_track_b09_b10(with_failure=True)
    _assert_vec_dict_close({k: clean[k] for k in ("v_root", "w_root", "v_com")}, {k: dirty[k] for k in ("v_root", "w_root", "v_com")})
    return {"v_root": clean["v_root"], "v_com": clean["v_com"]}


def test_b10() -> Dict[str, Any]:
    clean = _run_track_b09_b10(with_failure=False)
    dirty = _run_track_b09_b10(with_failure=True)
    keys = ("a_root", "alpha_root", "a_com", "H_total", "H_spin", "H_orbital")
    _assert_vec_dict_close({k: clean[k] for k in keys}, {k: dirty[k] for k in keys})
    return {"a_root": clean["a_root"], "H_total": clean["H_total"]}


def test_b11() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    # Frame 1: first-frame default fps (1/24), Frame 2: explicit dt=0.02, Frame 3: planned.dt=0.05, Frame 4: timestamp delta=0.03
    r1 = bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=False)
    r2 = bridge.execute_frame(_make_pose(2, 0.02, -7.99, foot_r_xyz=(HIP_X_OFFSET, -7.99, ANKLE_REST_Z), foot_r_locked=False), keyframe=False, dt=0.02)
    r3 = bridge.execute_frame(_make_pose(3, 0.07, -7.98, dt=0.05, foot_r_xyz=(HIP_X_OFFSET, -7.98, ANKLE_REST_Z), foot_r_locked=False), keyframe=False)
    r4 = bridge.execute_frame(_make_pose(4, 0.10, -7.97, dt=None, foot_r_xyz=(HIP_X_OFFSET, -7.97, ANKLE_REST_Z), foot_r_locked=False), keyframe=False)
    assert all(r.success for r in (r1, r2, r3, r4))
    dts = [r.motion_state.params["dt_seconds"] for r in (r1, r2, r3, r4)]
    assert math.isclose(dts[0], 1.0 / 24.0, abs_tol=1e-7)
    assert math.isclose(dts[1], 0.02, abs_tol=1e-7)
    assert math.isclose(dts[2], 0.05, abs_tol=1e-7)
    assert math.isclose(dts[3], 0.03, abs_tol=1e-7)
    return {"dts": [round(x, 6) for x in dts]}


def test_b12() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    wbc_calls = [0]
    orig_wbc = bridge.controller.execute_frame

    def spy_wbc(*a, **kw):
        wbc_calls[0] += 1
        return orig_wbc(*a, **kw)

    rejected = 0
    with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc):
        snap0 = _capture_seven_states(bridge)
        # Explicit dt invalid values
        for bad_dt in (float("nan"), float("inf"), float("-inf"), 0.0, -0.01, 1e-9, 1e-12, True):
            try:
                bridge.execute_frame(_make_pose(1, 0.0), keyframe=False, dt=bad_dt)  # type: ignore[arg-type]
                raise AssertionError(f"dt={bad_dt!r} was not rejected")
            except ValueError:
                rejected += 1
        # Planned.dt invalid values
        for bad_pdt in (float("nan"), float("inf"), float("-inf"), 0.0, -0.01, 1e-9, False):
            try:
                bridge.execute_frame(_make_pose(1, 0.0, dt=bad_pdt), keyframe=False)  # type: ignore[arg-type]
                raise AssertionError(f"planned.dt={bad_pdt!r} was not rejected")
            except ValueError:
                rejected += 1
        # Invalid time_seconds & non-int/bool frames
        for bad_t in (float("nan"), float("inf"), float("-inf"), True):
            try:
                bridge.execute_frame(_make_pose(1, bad_t), keyframe=False)  # type: ignore[arg-type]
                raise AssertionError(f"time_seconds={bad_t!r} was not rejected")
            except ValueError:
                rejected += 1
        for bad_f in (True, False, 1.5, "1", None):
            try:
                bridge.execute_frame(_make_pose(bad_f, 0.0), keyframe=False)  # type: ignore[arg-type]
                raise AssertionError(f"frame={bad_f!r} was not rejected")
            except ValueError:
                rejected += 1
        # Illegal default_fps on first frame
        orig_fps = bridge.default_fps
        for bad_fps in (float("nan"), float("inf"), float("-inf"), 0.0, -24.0, 1e9, 1e10, 1e-320, True):
            bridge.default_fps = bad_fps  # type: ignore[assignment]
            try:
                bridge.execute_frame(_make_pose(1, 0.0), keyframe=False)
                raise AssertionError(f"default_fps={bad_fps!r} was not rejected")
            except ValueError:
                rejected += 1
        bridge.default_fps = orig_fps
        _assert_seven_states_unchanged(bridge, snap0, "B12_precommit")
    assert wbc_calls[0] == 0, f"WBC called on rejected pre-admission timing inputs: {wbc_calls[0]}"

    # Timestamp difference overflow (-1e308 -> +1e308) with no explicit/planned dt
    assert bridge.execute_frame(_make_pose(1, -1e308), keyframe=False).success
    snap1 = _capture_seven_states(bridge)
    with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc):
        try:
            bridge.execute_frame(_make_pose(2, 1e308), keyframe=False)
            raise AssertionError("Timestamp delta overflow was not rejected")
        except ValueError:
            rejected += 1
        _assert_seven_states_unchanged(bridge, snap1, "B12_overflow")
    assert wbc_calls[0] == 0
    return {"rejected_invalid_cases": rejected, "wbc_calls_on_rejected": wbc_calls[0]}


def test_b13() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(2, 0.10, -8.0), keyframe=False).success
    snap = _capture_seven_states(bridge)
    wbc_calls = [0]
    orig_wbc = bridge.controller.execute_frame

    def spy_wbc(*a, **kw):
        wbc_calls[0] += 1
        return orig_wbc(*a, **kw)

    with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc):
        for bad_f, bad_t in ((2, 0.15), (1, 0.15), (3, 0.10), (3, 0.05)):
            try:
                bridge.execute_frame(_make_pose(bad_f, bad_t), keyframe=False)
                raise AssertionError(f"Duplicate/decreasing ({bad_f}, {bad_t}) not rejected")
            except ValueError:
                pass
        _assert_seven_states_unchanged(bridge, snap, "B13")
    assert wbc_calls[0] == 0
    return {"duplicate_and_decreasing_rejected": 4, "wbc_calls": wbc_calls[0]}


def test_b14() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(2, 0.10, -8.0), keyframe=False).success
    snap = _capture_seven_states(bridge)
    wbc_calls = [0]
    orig_wbc = bridge.controller.execute_frame

    def spy_wbc(*a, **kw):
        wbc_calls[0] += 1
        return orig_wbc(*a, **kw)

    with patch.object(bridge.controller, "execute_frame", side_effect=spy_wbc):
        for explicit_dt, p_dt in ((0.04, None), (None, 0.04)):
            for bad_t in (0.10, 0.05):
                try:
                    bridge.execute_frame(_make_pose(3, bad_t, dt=p_dt), keyframe=False, dt=explicit_dt)
                    raise AssertionError(f"Explicit dt bypassed backward/duplicate timestamp ({bad_t})")
                except ValueError:
                    pass
        _assert_seven_states_unchanged(bridge, snap, "B14")
    assert wbc_calls[0] == 0
    return {"explicit_dt_bypass_blocked": 4}


def test_b15() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    r1 = bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=False)
    r2 = bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z), foot_r_locked=False), keyframe=False)
    assert r1.success and r2.success
    assert all(len(v) == 0 for v in _collect_all_action_frames(arm, root).values())
    assert bridge._last_frame == 2 and math.isclose(bridge._last_time_sec, 1.0 / 24.0, abs_tol=1e-7)
    assert bridge.last_multi_contact is r2.multi_contact
    assert len(bridge.kinematics_tracker._history) == 2
    return {"keyframe_false_state_updated": True}


def test_b16() -> Dict[str, Any]:
    cfg = PipelineConfig()
    action_factories = [
        ("start_stop_walk", lambda: StartStopWalkAction()),
        ("terrain_walk", lambda: TerrainWalkAction(
            route=TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -6.5, 0.0), nominal_stride_m=0.35),
        )),
        ("run", lambda: RunAction(cycles=1)),
        ("sprint_start", lambda: SprintStartAction()),
        ("sprint_brake", lambda: SprintBrakeAction()),
    ]
    per_action = {}
    for act_name, make_act in action_factories:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_character(cfg)
        arm = build_rig(cfg)
        bind_character_to_rig(arm)
        reset_pose(arm)
        setup_leg_ik(arm)
        setup_arm_ik(arm, initial_influence=0.0)
        bpy.context.view_layer.update()

        planner = MotionPlanner(cfg, armature_obj=arm, environment=EnvironmentQuery(ground_z=0.0))
        act = make_act()
        planner.add_action(act)
        if act_name == "sprint_brake":
            init_st = create_initial_motion_state(cfg, start_frame=1)
            init_st = init_st.clone_with(mode=MotionMode.SPRINT, velocity=(0.0, 2.0, 0.0))
        else:
            init_st = None

        orig_exec = KinematicBridgeExecutor.execute_frame
        seen_frames: List[int] = []

        def fail_on_frame_3(self_bridge, planned, *a, **kw):
            seen_frames.append(planned.frame)
            if len(seen_frames) == 3:
                bad_planned = dc_replace(
                    planned,
                    foot_R=dc_replace(planned.foot_R, world_xyz=(HIP_X_OFFSET, 50.0, ANKLE_REST_Z), is_locked=False, clamp_reach=False),
                )
                return orig_exec(self_bridge, bad_planned, *a, **kw)
            return orig_exec(self_bridge, planned, *a, **kw)

        with patch.object(KinematicBridgeExecutor, "execute_frame", autospec=True, side_effect=fail_on_frame_3):
            try:
                planner.execute(initial_state=init_st)
                raise AssertionError(f"{act_name} did not stop on Frame 3 Bridge failure")
            except RuntimeError as exc:
                assert "Frame 3" in str(exc), f"{act_name} error missing Frame 3: {exc}"
        assert seen_frames == [1, 2, 3], f"{act_name} continued past failure frame! seen={seen_frames}"
        per_action[act_name] = seen_frames
    return {"stopped_immediately": per_action}


def test_b17() -> Dict[str, Any]:
    # Historical walk & central bilateral independent upper-limb smoke
    cfg = PipelineConfig()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    bpy.context.view_layer.update()

    seq_dur = 23.0 / float(cfg.fps)
    seg_l = (
        UpperLimbSegment(
            mode="FK",
            start_time_sec=0.0,
            duration_sec=seq_dur,
            fk_start_deg=((10.0, 0.0, 4.0), (20.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((14.0, 0.0, 4.0), (24.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),
    )
    seg_r = (
        UpperLimbSegment(
            mode="IK",
            start_time_sec=0.0,
            duration_sec=seq_dur,
            wrist_start_xyz=(0.25, 0.25, 1.25),
            wrist_end_xyz=(0.25, 0.28, 1.25),
            position_space="ROOT_LOCAL",
        ),
    )
    planner = MotionPlanner(cfg, armature_obj=arm, upper_limb_L=seg_l, upper_limb_R=seg_r, sequence_duration_sec=seq_dur)
    planner.add_action(RunAction(cycles=1))
    res = planner.execute()
    assert len(res["states"]) == 24
    return {"run_cycles_with_central_bilateral": len(res["states"])}


def test_b18() -> Dict[str, Any]:
    arm, root, bridge = _clean_scene()
    assert bridge.execute_frame(_make_pose(1, 0.0, -8.0, hand_l=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0)), keyframe=True).success
    kf_after_1 = _collect_all_action_frames(arm, root)
    # Fail frame 2
    assert bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, spine_deg=(85.0, 0.0, 0.0)), keyframe=True).success is False
    assert _collect_all_action_frames(arm, root) == kf_after_1
    # Retry frame 2 validly
    assert bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z), foot_r_locked=False), keyframe=True).success
    # Verify all 4 influence FCurves have [1.0, 2.0] and CONSTANT interpolation
    adt = arm.animation_data
    cb = adt.action.layers[0].strips[0].channelbag(adt.action_slot)
    expected_paths = {
        f'pose.bones["forearm.{s}"].constraints["{ARM_IK_CONSTRAINT_NAMES[s]}"].influence': 0
        for s in ("L", "R")
    }
    expected_paths.update({
        f'pose.bones["hand.{s}"].constraints["{HAND_ROT_CONSTRAINT_NAMES[s]}"].influence': 0
        for s in ("L", "R")
    })
    for fc in cb.fcurves:
        if fc.data_path in expected_paths:
            for kp in fc.keyframe_points:
                assert kp.interpolation == "CONSTANT", f"Non-CONSTANT interp on {fc.data_path}: {kp.interpolation}"
            expected_paths[fc.data_path] = len(fc.keyframe_points)
    assert all(cnt == 2 for cnt in expected_paths.values()), f"Influence keyframe counts invalid: {expected_paths}"
    return {"influence_constant_keyframes": expected_paths}


def test_b19() -> Dict[str, Any]:
    subresults: Dict[str, Any] = {}

    # Part A: Post-WBC measurement exceptions (kinematics, inertia, contacts) -> ZERO keyframes written, 7 states untouched
    for label, mod_path, attr in (
        ("kinematics_exc", "kinematics_tracker.sample_and_update", None),
        ("inertia_exc", kb_mod, "compute_whole_body_inertia"),
        ("contact_exc", kb_mod, "evaluate_limb_contacts_from_armature"),
    ):
        arm, root, bridge = _clean_scene()
        assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
        snap = _capture_seven_states(bridge)
        kf_before = _collect_all_action_frames(arm, root)
        p_ctx = (
            patch.object(bridge.kinematics_tracker, "sample_and_update", side_effect=RuntimeError(f"Injected {label}"))
            if attr is None
            else patch.object(mod_path, attr, side_effect=RuntimeError(f"Injected {label}"))
        )
        with p_ctx:
            try:
                bridge.execute_frame(_make_pose(2, 1.0 / 24.0, -7.98, foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z), foot_r_locked=False), keyframe=True)
                raise AssertionError(f"{label} did not propagate")
            except RuntimeError as exc:
                assert label in str(exc)
        assert _collect_all_action_frames(arm, root) == kf_before, f"{label}: keyframes modified!"
        _assert_seven_states_unchanged(bridge, snap, f"B19_{label}")
        subresults[label] = {"keyframes_written": 0, "seven_states_preserved": True}

    # Part B: Keyframe write returning False OR raising RuntimeError at Root, PoseBone, Leg Ctrl, Arm Ctrl, Influence
    orig_obj_kf = bpy.types.Object.keyframe_insert
    orig_pb_kf = bpy.types.PoseBone.keyframe_insert
    orig_con_kf = bpy.types.Constraint.keyframe_insert

    cases = [
        ("root_false", "Object", "CharacterRoot", "location", "false"),
        ("root_exc", "Object", "CharacterRoot", "rotation_euler", "exc"),
        ("posebone_false", "PoseBone", "spine", "rotation_euler", "false"),
        ("posebone_exc", "PoseBone", "pelvis", "location", "exc"),
        ("legctrl_false", "Object", "FootIK.L", "location", "false"),
        ("legctrl_exc", "Object", "KneePole.R", "rotation_euler", "exc"),
        ("armctrl_false", "Object", "HandIK.L", "location", "false"),
        ("armctrl_exc", "Object", "ElbowPole.R", "rotation_euler", "exc"),
        ("influence_false", "Constraint", "ArmIK.L", "influence", "false"),
        ("influence_exc", "Constraint", "HandRotation.R", "influence", "exc"),
    ]
    for case_name, kind, target_name, path_target, mode in cases:
        arm, root, bridge = _clean_scene()
        assert bridge.execute_frame(_make_pose(1, 0.0, -8.0), keyframe=True).success
        snap = _capture_seven_states(bridge)
        kf_before = _collect_all_action_frames(arm, root)

        def make_hook(orig_fn, expect_kind):
            def hook(self_obj, data_path, *args, **kwargs):
                if kind == expect_kind and self_obj.name == target_name and data_path == path_target:
                    if mode == "false":
                        return False
                    raise RuntimeError(f"Injected keyframe exception on {self_obj.name}.{data_path}")
                return orig_fn(self_obj, data_path, *args, **kwargs)
            return hook

        with patch.object(bpy.types.Object, "keyframe_insert", new=make_hook(orig_obj_kf, "Object")), patch.object(
            bpy.types.PoseBone, "keyframe_insert", new=make_hook(orig_pb_kf, "PoseBone")
        ), patch.object(bpy.types.Constraint, "keyframe_insert", new=make_hook(orig_con_kf, "Constraint")):
            try:
                bridge.execute_frame(
                    _make_pose(
                        2,
                        1.0 / 24.0,
                        -7.98,
                        foot_r_xyz=(HIP_X_OFFSET, -7.96, ANKLE_REST_Z),
                        foot_r_locked=False,
                        hand_l=PlannedHandTarget((-0.25, -7.75, 1.25), enabled=True, weight=1.0),
                    ),
                    keyframe=True,
                )
                raise AssertionError(f"{case_name} did not abort on keyframe failure")
            except RuntimeError as exc:
                msg = str(exc)
                if mode == "false":
                    assert "frame 2" in msg.lower() and target_name in msg and path_target in msg, f"{case_name} msg incomplete: {msg}"
        _assert_seven_states_unchanged(bridge, snap, f"B19_{case_name}")
        kf_after = _collect_all_action_frames(arm, root)
        partial_fcurves_frame2 = {
            obj_k: [p for p, fs in paths.items() if 2.0 in fs]
            for obj_k, paths in kf_after.items()
            if any(2.0 in fs for fs in paths.values())
        }
        # Note honestly whether partial frame-2 FCurves were written prior to the fault point
        subresults[case_name] = {
            "seven_states_preserved": True,
            "partial_frame2_fcurve_paths_count": sum(len(v) for v in partial_fcurves_frame2.values()),
            "changed_vs_before": kf_after != kf_before,
        }
    return subresults


TESTS: List[Tuple[str, Callable[[], Dict[str, Any]]]] = [
    ("B01", test_b01),
    ("B02", test_b02),
    ("B03", test_b03),
    ("B04", test_b04),
    ("B05", test_b05),
    ("B06", test_b06),
    ("B07", test_b07),
    ("B08", test_b08),
    ("B09", test_b09),
    ("B10", test_b10),
    ("B11", test_b11),
    ("B12", test_b12),
    ("B13", test_b13),
    ("B14", test_b14),
    ("B15", test_b15),
    ("B16", test_b16),
    ("B17", test_b17),
    ("B18", test_b18),
    ("B19", test_b19),
]


def main() -> int:
    results: Dict[str, Any] = {}
    all_ok = True
    for tid, fn in TESTS:
        try:
            detail = fn()
            results[tid] = {"status": "PASSED", "detail": detail}
            print(f"[PASS] {tid}: {detail}")
        except Exception as exc:
            all_ok = False
            results[tid] = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
            print(f"[FAIL] {tid}: {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()
            break

    payload = {
        "group": "Group B — Bridge Frame Commit & Timing Admission (B01-B19)",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "passed": all_ok,
        "total": len(TESTS),
        "passed_count": sum(1 for v in results.values() if v["status"] == "PASSED"),
        "results": results,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
