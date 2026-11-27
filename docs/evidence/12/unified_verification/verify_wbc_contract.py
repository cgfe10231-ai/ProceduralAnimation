"""TASK 12-D Group A: WBC Single-Frame Contract Verification (A01-A20).

Run via real Blender 5.1.1:
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P docs/evidence/12/unified_verification/verify_wbc_contract.py
"""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple
from unittest.mock import patch

import bpy
from mathutils import Euler, Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import src.motion.whole_body_controller as wbc_mod
from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.whole_body_controller import (
    EndEffectorTarget,
    WholeBodyControlResult,
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.arm_ik import MAX_ARM_REACH, get_arm_ik_state, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, get_leg_ik_state, setup_leg_ik
from src.rig.pose import reset_pose
from src.scene_transaction_integrity.fault_injection import _clear_test_fault_injection_hook
from src.scene_transaction_integrity.layer2.pending_cleanup_registry import _PENDING_ARM_RIG_CLEANUPS
from src.scene_transaction_integrity.layer2.session_registries import _ISOLATED_FAILED_ARMATURES
from src.scene_transaction_integrity.layer2.transaction_stack import _ACTIVE_TRANSACTION_STACK
from src.scene_transaction_integrity.wiring import _snapshot_arm_rig_state, _verify_arm_rig_state_restored

OUTPUT_JSON = os.path.join(THIS_DIR, "wbc_results.json")


def _clean_scene(y_root: float = -8.0) -> Tuple[bpy.types.Object, bpy.types.Object, WholeBodyController]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _clear_test_fault_injection_hook()
    _PENDING_ARM_RIG_CLEANUPS.clear()
    _ISOLATED_FAILED_ARMATURES.clear()
    _ACTIVE_TRANSACTION_STACK.clear()

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
    wbc = WholeBodyController(armature_obj=arm, root_obj=root, config=cfg)
    return arm, root, wbc


def _baseline_targets(y_root: float = -8.0) -> WholeBodyControlTargets:
    t = WholeBodyControlTargets()
    t.set_root(position=(0.0, y_root, 0.0), yaw_deg=0.0)
    t.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, y_root, ANKLE_REST_Z), is_locked=True)
    t.set_foot("R", target_world_xyz=(HIP_X_OFFSET, y_root, ANKLE_REST_Z), is_locked=True)
    return t


def _assert_full_snapshot_restored(wbc: WholeBodyController, pre_snap: Dict[str, Any], arm_snap: Any, label: str) -> None:
    if _ACTIVE_TRANSACTION_STACK:
        raise AssertionError(f"{label}: _ACTIVE_TRANSACTION_STACK leaked: {_ACTIVE_TRANSACTION_STACK}")
    wbc._wbc_restore_frame_state  # Ensure helper reference exists, then verify read-only equality
    arm = pre_snap["arm_ref"]
    tol = 1e-5
    for obj_label, data in pre_snap["objects"].items():
        obj = data["ref"]
        if obj.parent != data["parent"]:
            raise AssertionError(f"{label}: {obj_label}.parent mismatch ({obj.parent} != {data['parent']})")
        for field in (
            "location",
            "rotation_euler",
            "rotation_quaternion",
            "rotation_axis_angle",
            "scale",
            "delta_location",
            "delta_rotation_euler",
            "delta_rotation_quaternion",
            "delta_scale",
        ):
            diff = wbc._wbc_max_difference(getattr(obj, field), data[field])
            if diff > tol:
                raise AssertionError(f"{label}: {obj_label}.{field} residual diff={diff}")
        if data["foot"]:
            for key in WholeBodyController._WBC_FOOT_METADATA_KEYS:
                if (key in obj) != (key in data["metadata"]):
                    raise AssertionError(f"{label}: {obj_label}[{key}] presence mismatch")
                if key in data["metadata"]:
                    actual_v = WholeBodyController._wbc_clone_idprop(obj[key])
                    if actual_v != data["metadata"][key]:
                        raise AssertionError(f"{label}: {obj_label}[{key}] value mismatch ({actual_v} != {data['metadata'][key]})")
    for name, data in pre_snap["bones"].items():
        bone = arm.pose.bones[name]
        for field in ("location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle", "scale"):
            diff = wbc._wbc_max_difference(getattr(bone, field), data[field])
            if diff > tol:
                raise AssertionError(f"{label}: bone {name}.{field} residual diff={diff}")
    _verify_arm_rig_state_restored(arm, arm_snap)


def test_a01() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_root(position=(0.15, -7.85, 0.05), yaw_deg=15.0)
    t.set_pelvis(location=(0.01, -0.02, 0.03), rotation_deg=(4.0, 2.0, -3.0))
    t.set_trunk_posture(spine_deg=(8.0, 1.0, -2.0))

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"root_mutated": False, "pelvis_mutated": False, "euler_calls": 0}
    orig_euler = wbc_mod.Euler

    def faulty_euler(*args, **kwargs):
        observed["euler_calls"] += 1
        if observed["euler_calls"] == 2:
            observed["root_mutated"] = (Vector(root.location) - Vector((0.0, -8.0, 0.0))).length > 0.05
            p_pelvis = arm.pose.bones["pelvis"]
            observed["pelvis_mutated"] = Vector(p_pelvis.location).length > 0.01
            assert observed["root_mutated"] and observed["pelvis_mutated"], "Fault injected before Root/Pelvis write"
            raise RuntimeError("Injected fault after Root/Pelvis write (A01)")
        return orig_euler(*args, **kwargs)

    with patch.object(wbc_mod, "Euler", side_effect=faulty_euler):
        try:
            wbc.execute_frame(t)
            raise AssertionError("A01 expected RuntimeError")
        except RuntimeError as exc:
            assert "A01" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A01")
    return {"observed_prior_writes": observed}


def test_a02() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_trunk_posture(spine_deg=(12.0, 3.0, -2.0), neck_deg=(4.0, 0.0, 1.0), head_deg=(3.0, -2.0, 1.0))
    t.fk_joint_rotations_deg = {"upper_arm.L": (25.0, 5.0, -4.0), "forearm.R": (0.0, 20.0, 0.0)}

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"spine_mutated": False, "fk_mutated": False}
    orig_lock = wbc_mod.lock_foot_contact

    def faulty_lock(arm_obj, side, **kwargs):
        observed["spine_mutated"] = abs(math.degrees(arm_obj.pose.bones["spine"].rotation_euler.x) - 12.0) < 0.1
        observed["fk_mutated"] = abs(math.degrees(arm_obj.pose.bones["upper_arm.L"].rotation_euler.x) - 25.0) < 0.1
        assert observed["spine_mutated"] and observed["fk_mutated"], "Torso/FK must be mutated before A02 fault"
        raise RuntimeError("Injected fault after Torso/FK write (A02)")

    with patch.object(wbc_mod, "lock_foot_contact", side_effect=faulty_lock):
        try:
            wbc.execute_frame(t)
            raise AssertionError("A02 expected RuntimeError")
        except RuntimeError as exc:
            assert "A02" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A02")
    return {"observed_prior_writes": observed}


def test_a03() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_foot("L", target_world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True)
    t.set_foot("R", target_world_xyz=(0.11, -7.88, ANKLE_REST_Z + 0.06), is_locked=False)

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"foot_L_locked": False}
    orig_set_foot = wbc_mod.set_foot_ik_target

    def faulty_second_leg(arm_obj, side, **kwargs):
        if side == "R":
            ik_l = bpy.data.objects["FootIK.L"]
            observed["foot_L_locked"] = bool(ik_l.get("is_locked", False))
            assert observed["foot_L_locked"], "foot_L lock must have mutated before A03 fault"
            raise RuntimeError("Injected fault on second leg after first leg write (A03)")
        return orig_set_foot(arm_obj, side, **kwargs)

    with patch.object(wbc_mod, "set_foot_ik_target", side_effect=faulty_second_leg):
        try:
            wbc.execute_frame(t)
            raise AssertionError("A03 expected RuntimeError")
        except RuntimeError as exc:
            assert "A03" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A03")
    return {"observed_prior_writes": observed}


def test_a04() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    # First commit a frame where R is locked and L is unlocked
    t_init = _baseline_targets()
    t_init.set_foot("L", target_world_xyz=(-0.11, -7.95, ANKLE_REST_Z + 0.05), is_locked=False)
    t_init.set_foot("R", target_world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True)
    assert wbc.execute_frame(t_init).success

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"foot_L_now_locked": False, "foot_R_now_unlocked": False}

    t_flip = _baseline_targets()
    t_flip.set_foot("L", target_world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True)
    t_flip.set_foot("R", target_world_xyz=(0.11, -7.90, ANKLE_REST_Z + 0.08), is_locked=False)
    t_flip.set_hand("L", target_world_xyz=(-0.25, -7.75, 1.25), enabled=True, weight=1.0)

    def faulty_arm(*args, **kwargs):
        observed["foot_L_now_locked"] = bool(bpy.data.objects["FootIK.L"].get("is_locked", False))
        observed["foot_R_now_unlocked"] = not bool(bpy.data.objects["FootIK.R"].get("is_locked", False))
        assert observed["foot_L_now_locked"] and observed["foot_R_now_unlocked"], "Both foot lock changes must precede A04 fault"
        raise RuntimeError("Injected fault in arm dispatch after foot lock flips (A04)")

    with patch.object(wbc_mod, "set_hand_ik_target", side_effect=faulty_arm):
        try:
            wbc.execute_frame(t_flip)
            raise AssertionError("A04 expected RuntimeError")
        except RuntimeError as exc:
            assert "A04" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A04")
    return {"observed_prior_writes": observed}


def test_a05() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_hand("L", target_world_xyz=(-0.25, -7.78, 1.26), enabled=True, weight=1.0)
    t.set_hand("R", target_world_xyz=(0.25, -7.78, 1.26), enabled=True, weight=1.0)

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"hand_L_written": False}
    orig_hand = wbc_mod.set_hand_ik_target

    def faulty_right_arm(arm_obj, side, **kwargs):
        if side == "R":
            arm_ik_l = arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].influence
            observed["hand_L_written"] = abs(arm_ik_l - 1.0) < 1e-5
            assert observed["hand_L_written"], "Left arm write must precede right arm fault in A05"
            raise RuntimeError("Injected fault in right arm after left arm write (A05)")
        return orig_hand(arm_obj, side, **kwargs)

    with patch.object(wbc_mod, "set_hand_ik_target", side_effect=faulty_right_arm):
        try:
            wbc.execute_frame(t)
            raise AssertionError("A05 expected RuntimeError")
        except RuntimeError as exc:
            assert "A05" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A05")
    return {"observed_prior_writes": observed}


def test_a06() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_root(position=(0.05, -7.95, 0.0))
    t.set_trunk_posture(spine_deg=(15.0, 0.0, 0.0))
    t.set_hand("L", target_world_xyz=(-0.25, -7.75, 1.25), enabled=True, weight=1.0)

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"pose_written": False}

    def faulty_validate(arm_obj, use_evaluated_ik=True):
        observed["pose_written"] = (
            abs(math.degrees(arm_obj.pose.bones["spine"].rotation_euler.x) - 15.0) < 0.1
            and abs(arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].influence - 1.0) < 1e-5
        )
        assert observed["pose_written"], "Pose writes must complete before ROM validation fault (A06)"
        raise RuntimeError("Injected fault in ROM validation (A06)")

    with patch.object(wbc.joint_model, "validate_armature_pose", side_effect=faulty_validate):
        try:
            wbc.execute_frame(t)
            raise AssertionError("A06 expected RuntimeError")
        except RuntimeError as exc:
            assert "A06" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A06")
    return {"observed_prior_writes": observed}


def test_a07() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_trunk_posture(spine_deg=(85.0, 0.0, 0.0))
    t.set_hand("L", target_world_xyz=(-0.25, -7.75, 1.25), enabled=True, weight=1.0)

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"clamped_applied": False}
    orig_clamp = wbc.joint_model.clamp_armature_pose

    def faulty_clamp(arm_obj, apply=True, update_scene=True):
        res = orig_clamp(arm_obj, apply=apply, update_scene=update_scene)
        observed["clamped_applied"] = math.degrees(arm_obj.pose.bones["spine"].rotation_euler.x) < 65.0
        assert observed["clamped_applied"], "ROM clamp write must apply before fault (A07)"
        raise RuntimeError("Injected fault during/after ROM clamping (A07)")

    with patch.object(wbc.joint_model, "clamp_armature_pose", side_effect=faulty_clamp):
        try:
            wbc.execute_frame(t, enforce_rom_clamping=True)
            raise AssertionError("A07 expected RuntimeError")
        except RuntimeError as exc:
            assert "A07" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A07")
    return {"observed_prior_writes": observed}


def test_a08() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_root(position=(0.0, -7.90, 0.0))
    t.set_trunk_posture(spine_deg=(82.0, 0.0, 0.0))
    t.set_hand("R", target_world_xyz=(0.25, -7.75, 1.25), enabled=True, weight=1.0)

    pre_snap = wbc._wbc_capture_frame_state()
    arm_snap = _snapshot_arm_rig_state(arm)
    observed = {"pose_and_clamp_done": False}

    def faulty_com(*args, **kwargs):
        observed["pose_and_clamp_done"] = (
            abs(root.location.y - (-7.90)) < 1e-4
            and math.degrees(arm.pose.bones["spine"].rotation_euler.x) < 65.0
        )
        assert observed["pose_and_clamp_done"], "Pose + ROM clamp must finish before CoM fault (A08)"
        raise RuntimeError("Injected fault during CoM computation (A08)")

    with patch.object(wbc_mod, "compute_whole_body_com", side_effect=faulty_com):
        try:
            wbc.execute_frame(t, enforce_rom_clamping=True)
            raise AssertionError("A08 expected RuntimeError")
        except RuntimeError as exc:
            assert "A08" in str(exc)

    _assert_full_snapshot_restored(wbc, pre_snap, arm_snap, "A08")
    return {"observed_prior_writes": observed}


def _run_rom_clamped_bilateral_case() -> Tuple[bpy.types.Object, WholeBodyControlTargets, WholeBodyControlResult]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_trunk_posture(spine_deg=(85.0, 0.0, 0.0))  # Exceeds anatomical limit
    t.set_hand("L", target_world_xyz=(-0.25, -7.70, 1.15), rotation_deg=(15.0, 10.0, -5.0), enabled=True, weight=1.0)
    t.set_hand("R", target_world_xyz=(0.25, -7.70, 1.15), rotation_deg=(-10.0, 5.0, 8.0), enabled=True, weight=1.0)
    t.set_foot("R", target_world_xyz=(0.11, -7.90, ANKLE_REST_Z + 0.04), is_locked=False)
    res = wbc.execute_frame(t, update_scene=True, enforce_rom_clamping=True)
    return arm, t, res


def test_a09() -> Dict[str, Any]:
    arm, t, res = _run_rom_clamped_bilateral_case()
    diffs = {}
    for side in ("L", "R"):
        fb_h = res.end_effectors[f"hand_{side}"]
        actual_wrist = tuple(float(v) for v in get_arm_ik_state(arm, side)["wrist_world"])
        diff_h = math.dist(fb_h.actual_world_xyz, actual_wrist)
        assert diff_h < 1e-5, f"hand_{side} feedback stale vs post-clamp wrist: diff={diff_h}"
        exp_err_h = math.dist(actual_wrist, fb_h.requested_world_xyz)
        assert abs(fb_h.position_error_m - exp_err_h) < 1e-5
        diffs[f"hand_{side}"] = round(diff_h, 8)

        fb_f = res.end_effectors[f"foot_{side}"]
        actual_ankle = tuple(float(v) for v in get_leg_ik_state(arm, side)["ankle_world"])
        diff_f = math.dist(fb_f.actual_world_xyz, actual_ankle)
        assert diff_f < 1e-5, f"foot_{side} feedback stale vs post-clamp ankle: diff={diff_f}"
        diffs[f"foot_{side}"] = round(diff_f, 8)
    return {"post_clamp_diffs_m": diffs}


def test_a10() -> Dict[str, Any]:
    arm, t, res = _run_rom_clamped_bilateral_case()
    rot_diffs = {}
    for side in ("L", "R"):
        fb = res.end_effectors[f"hand_{side}"]
        st = get_arm_ik_state(arm, side)
        actual_euler = tuple(float(v) for v in st["hand_world_euler_deg"])
        actual_rot_err = float(st["rotation_error_deg"])
        assert fb.actual_rotation_deg is not None
        max_e = max(abs(a - b) for a, b in zip(fb.actual_rotation_deg, actual_euler))
        assert max_e < 1e-4, f"hand_{side} actual_rotation_deg mismatch: {max_e}"
        assert fb.orientation_error_deg is not None and abs(fb.orientation_error_deg - actual_rot_err) < 1e-4
        rot_diffs[f"hand_{side}"] = {"euler_diff_deg": round(max_e, 6), "err_deg": round(actual_rot_err, 4)}
    return rot_diffs


def test_a11() -> Dict[str, Any]:
    arm, t, res = _run_rom_clamped_bilateral_case()
    active_errors = [fb.position_error_m for fb in res.end_effectors.values() if fb.enabled]
    expected_max = max(active_errors) if active_errors else 0.0
    assert abs(res.max_end_effector_error_m - expected_max) < 1e-7
    expected_all_reach = all(fb.is_reachable and fb.position_error_m <= 0.005 for fb in res.end_effectors.values() if fb.enabled)
    assert res.is_all_reachable == expected_all_reach
    # CoM must reflect clamped spine (<= 60 deg), NOT unclamped 85 deg!
    assert math.degrees(arm.pose.bones["spine"].rotation_euler.x) <= 60.05
    assert res.com_result is not None and math.isfinite(res.com_result.com_world.z)
    return {"max_effector_error_m": round(res.max_end_effector_error_m, 6), "com_z": round(res.com_result.com_world.z, 6)}


def test_a12() -> Dict[str, Any]:
    arm, t, res = _run_rom_clamped_bilateral_case()
    assert res.success is False, "Clamped ROM failure must NOT turn into success=True"
    assert res.has_rom_violation is True
    assert "spine" in res.rom_validation.violations
    cats = [uc.category for uc in res.unmet_constraints]
    assert "ROM_VIOLATION" in cats
    assert any(uc.category == "ROM_VIOLATION" and uc.target_name == "spine" for uc in res.unmet_constraints)
    return {"unmet_categories": cats}


def test_a13() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_trunk_posture(spine_deg=(85.0, 0.0, 0.0))  # ROM invalid
    # Requested target is 0.45m beyond shoulder (unreachable), WITH clamp_reach=True so internal IK target != requested target
    st_l = get_arm_ik_state(arm, "L")
    shoulder = st_l["shoulder_world"]
    req_xyz = (float(shoulder.x), float(shoulder.y) + MAX_ARM_REACH + 0.35, float(shoulder.z))
    t.set_hand("L", target_world_xyz=req_xyz, enabled=True, weight=1.0, clamp_reach=True)

    res = wbc.execute_frame(t, update_scene=True, enforce_rom_clamping=True)
    assert res.success is False
    fb_l = res.end_effectors["hand_L"]
    rom_conflicts = [uc for uc in res.unmet_constraints if uc.category == "ROM_CONFLICT" and uc.target_name == "hand_L"]
    assert len(rom_conflicts) == 1, f"Expected hand_L ROM_CONFLICT, got {res.unmet_constraints}"
    # Key check: ROM_CONFLICT error_amount MUST equal original-request position_error_m (~0.35m), NOT clamped IK controller error (~0)!
    assert fb_l.position_error_m > 0.25, f"Expected large error vs original request, got {fb_l.position_error_m}"
    assert abs(rom_conflicts[0].error_amount - fb_l.position_error_m) < 1e-6, (
        f"ROM_CONFLICT error ({rom_conflicts[0].error_amount}) != EndEffectorFeedback.position_error_m ({fb_l.position_error_m})"
    )
    return {
        "requested_error_m": round(fb_l.position_error_m, 6),
        "rom_conflict_error_m": round(rom_conflicts[0].error_amount, 6),
    }


def test_a14() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.foot_L = EndEffectorTarget(
        effector_id="foot_L",
        target_world_xyz=(-HIP_X_OFFSET, 10.0, ANKLE_REST_Z),  # Impossible 18m away!
        is_locked=False,
        enabled=True,
        weight=0.0,
    )
    res = wbc.execute_frame(t, update_scene=True, enforce_rom_clamping=True)
    fb_l = res.end_effectors["foot_L"]
    assert fb_l.enabled is False and fb_l.weight == 0.0 and fb_l.position_error_m == 0.0 and fb_l.is_reachable is True
    assert not any(uc.target_name == "foot_L" for uc in res.unmet_constraints)
    assert res.success is True, f"Zero-weight unreachable foot_L caused failure: {res.unmet_constraints}"
    return {"foot_L_feedback_enabled": fb_l.enabled, "success": res.success}


def test_a15() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    # Right foot weight=0.0 + both feet weight<=0.0 (including negative weight)
    for w_l, w_r in ((1.0, 0.0), (0.0, 0.0), (-0.5, 0.0)):
        t = _baseline_targets()
        if w_l <= 0.0:
            t.foot_L = EndEffectorTarget("foot_L", (-HIP_X_OFFSET, 5.0, ANKLE_REST_Z), enabled=True, weight=w_l)
        if w_r <= 0.0:
            t.foot_R = EndEffectorTarget("foot_R", (HIP_X_OFFSET, 5.0, ANKLE_REST_Z), enabled=True, weight=w_r)
        res = wbc.execute_frame(t, update_scene=True)
        assert res.success is True, f"Failed for weights ({w_l}, {w_r}): {res.unmet_constraints}"
        if w_r <= 0.0:
            assert res.end_effectors["foot_R"].enabled is False and res.end_effectors["foot_R"].position_error_m == 0.0
        if w_l <= 0.0:
            assert res.end_effectors["foot_L"].enabled is False and res.end_effectors["foot_L"].position_error_m == 0.0
    return {"cases_verified": 3}


def test_a16() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t_ok = _baseline_targets()
    assert wbc.execute_frame(t_ok).success is True
    t_bad = _baseline_targets()
    t_bad.foot_R = EndEffectorTarget("foot_R", (HIP_X_OFFSET, -6.0, ANKLE_REST_Z), enabled=True, weight=1.0, clamp_reach=False)
    res_bad = wbc.execute_frame(t_bad)
    assert res_bad.success is False
    assert any(uc.category == "REACHABILITY" and uc.target_name == "foot_R" for uc in res_bad.unmet_constraints)
    return {"positive_weight_reachability_rejected": True}


def test_a17() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t1 = _baseline_targets()
    t1.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, 0.0), is_locked=True)
    assert wbc.execute_frame(t1).success

    calls = {"lock": 0, "eval": 0}
    orig_lock = wbc_mod.lock_foot_contact
    orig_eval = wbc_mod.evaluate_foot_support

    def spy_lock(*a, **kw):
        calls["lock"] += 1
        return orig_lock(*a, **kw)

    def spy_eval(*a, **kw):
        calls["eval"] += 1
        return orig_eval(*a, **kw)

    t2 = _baseline_targets()
    t2.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(10.0, 0.0, 15.0), is_locked=True)
    with patch.object(wbc_mod, "lock_foot_contact", side_effect=spy_lock), patch.object(wbc_mod, "evaluate_foot_support", side_effect=spy_eval):
        res2 = wbc.execute_frame(t2)
    assert res2.success is True
    assert calls["lock"] == 1 and calls["eval"] == 1, f"Expected re-lock on L and eval on R, got {calls}"
    rot_l = tuple(float(v) for v in bpy.data.objects["FootIK.L"]["target_rotation_deg"])
    assert max(abs(a - b) for a, b in zip(rot_l, (10.0, 0.0, 15.0))) < 1e-4
    return {"calls": calls, "updated_rot_L": rot_l}


def test_a18() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t1 = _baseline_targets()
    t1.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, 15.0), is_locked=True)
    assert wbc.execute_frame(t1).success

    calls = {"lock": 0, "eval": 0}
    orig_lock = wbc_mod.lock_foot_contact
    orig_eval = wbc_mod.evaluate_foot_support

    def spy_lock(*a, **kw):
        calls["lock"] += 1
        return orig_lock(*a, **kw)

    def spy_eval(*a, **kw):
        calls["eval"] += 1
        return orig_eval(*a, **kw)

    # Equivalent Euler (360, 0, -345) AND None rotation_deg should NOT trigger lock_foot_contact
    t_equiv = _baseline_targets()
    t_equiv.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(360.0, 0.0, -345.0), is_locked=True)
    t_none = _baseline_targets()
    t_none.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=None, is_locked=True)
    with patch.object(wbc_mod, "lock_foot_contact", side_effect=spy_lock), patch.object(wbc_mod, "evaluate_foot_support", side_effect=spy_eval):
        assert wbc.execute_frame(t_equiv).success
        assert wbc.execute_frame(t_none).success
    assert calls["lock"] == 0 and calls["eval"] == 4, f"Unexpected re-locks on equiv/None rotation: {calls}"
    return {"calls": calls}


def test_a19() -> Dict[str, Any]:
    arm, root, wbc = _clean_scene()
    t1 = _baseline_targets()
    t1.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, 0.0), is_locked=True)
    t1.set_foot("R", target_world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, -12.0), is_locked=True)
    assert wbc.execute_frame(t1).success

    ik_r = bpy.data.objects["FootIK.R"]
    r_before = {
        k: WholeBodyController._wbc_clone_idprop(ik_r[k])
        for k in WholeBodyController._WBC_FOOT_METADATA_KEYS
        if k in ik_r
    }

    t2 = _baseline_targets()
    t2.set_foot("L", target_world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(8.0, 0.0, 14.0), is_locked=True)
    t2.set_foot("R", target_world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, -12.0), is_locked=True)
    assert wbc.execute_frame(t2).success

    r_after = {
        k: WholeBodyController._wbc_clone_idprop(ik_r[k])
        for k in WholeBodyController._WBC_FOOT_METADATA_KEYS
        if k in ik_r
    }
    assert r_before == r_after, f"Right foot metadata mutated during L unilateral update: {r_before} != {r_after}"
    return {"right_foot_metadata_keys_preserved": len(r_after)}


def test_a20() -> Dict[str, Any]:
    # 10-C bilateral pole_hint + clamp_reach smoke on current WBC, referencing standalone historical suites
    arm, root, wbc = _clean_scene()
    t = _baseline_targets()
    t.set_hand(
        "L",
        target_world_xyz=(-0.25, -7.75, 1.25),
        rotation_deg=None,
        pole_hint_xyz=(-0.40, -8.10, 1.15),
        enabled=True,
        weight=1.0,
        clamp_reach=True,
    )
    t.set_hand(
        "R",
        target_world_xyz=(0.25, -7.75, 1.25),
        rotation_deg=None,
        pole_hint_xyz=(0.40, -8.10, 1.15),
        enabled=True,
        weight=1.0,
        clamp_reach=False,
    )
    res = wbc.execute_frame(t)
    assert res.success is True
    assert res.end_effectors["hand_L"].enabled and res.end_effectors["hand_R"].enabled
    return {
        "bilateral_10c_wbc_smoke": "PASS",
        "hand_L_err_m": round(res.end_effectors["hand_L"].position_error_m, 6),
        "hand_R_err_m": round(res.end_effectors["hand_R"].position_error_m, 6),
        "cross_referenced_suites": [
            "tests/test_task10b_wbc_failure_contract.py",
            "docs/evidence/11/unified_verification/verify_footlock_contract.py",
        ],
    }


TESTS: List[Tuple[str, Callable[[], Dict[str, Any]]]] = [
    ("A01", test_a01),
    ("A02", test_a02),
    ("A03", test_a03),
    ("A04", test_a04),
    ("A05", test_a05),
    ("A06", test_a06),
    ("A07", test_a07),
    ("A08", test_a08),
    ("A09", test_a09),
    ("A10", test_a10),
    ("A11", test_a11),
    ("A12", test_a12),
    ("A13", test_a13),
    ("A14", test_a14),
    ("A15", test_a15),
    ("A16", test_a16),
    ("A17", test_a17),
    ("A18", test_a18),
    ("A19", test_a19),
    ("A20", test_a20),
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
        "group": "Group A — WBC Single-Frame Contract (A01-A20)",
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
