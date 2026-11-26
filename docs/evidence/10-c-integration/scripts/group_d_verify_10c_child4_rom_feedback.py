"""Task 10-c-child4 / post-ROM Bridge verification; authored by ChatGPT.

Freeze: task/10-c-child4 @ 3b86f037c1f28e0c6b84088c8a85fb5415578738.
The execution agent may execute this script verbatim only. No production writes.
"""
import json
import math
import os
from pathlib import Path
import runpy
import sys
import traceback
from dataclasses import replace

import bpy

ROOT = Path(os.environ["TASK10C_REPO_ROOT"]).resolve()
RESULT = Path(os.environ["TASK10C_RESULT_JSON"]).resolve()
sys.path.insert(0, str(ROOT))

from src.motion import kinematic_bridge as kb
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
    convert_planned_pose_to_wbc_targets,
)
from src.motion.whole_body_controller import WholeBodyController

BASE_HEAD = "3b86f037c1f28e0c6b84088c8a85fb5415578738"
assert tuple(bpy.app.version[:3]) == (5, 1, 1), bpy.app.version_string
historical = runpy.run_path(
    str(ROOT / "tests" / "verify_task6gc_r3b1_bridge.py"),
    run_name="task10c_post_rom_selected",
)
_clean_scene = historical["_clean_scene"]
records = []


def write_results():
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps({
        "node": "10-c-child4",
        "frozen_source_head": BASE_HEAD,
        "blender_version": bpy.app.version_string,
        "executed": len(records),
        "passed": sum(r["status"] == "PASS" for r in records),
        "failed": sum(r["status"] == "FAIL" for r in records),
        "tests": records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def check(name, fn):
    print(f"RUN: {name}", flush=True)
    try:
        metrics = fn()
        if metrics is False:
            raise AssertionError("Test explicitly returned False")
    except BaseException as exc:
        records.append({"test": name, "status": "FAIL", "error": repr(exc)})
        write_results()
        traceback.print_exc()
        raise
    records.append({"test": name, "status": "PASS", "metrics": metrics})
    write_results()
    print(f"PASS: {name}", flush=True)


def hand(side, enabled=True, weight=1.0, pos=None, rot=None):
    if pos is None:
        pos = (-0.24, -7.65, 1.35) if side == "L" else (0.24, -7.70, 1.25)
    if rot is None:
        rot = (20.0, 10.0, -5.0) if side == "L" else (15.0, -10.0, 5.0)
    return PlannedHandTarget(
        world_xyz=pos, rotation_deg=rot, enabled=enabled,
        weight=weight, contact_intent=False,
    )


def pose(frame=1, time=0.0, spine=85.0, left=None, right=None):
    return KinematicPlannedPose(
        frame=frame, time_seconds=time, root_position=(0.0, -8.0, 0.0),
        spine_rotation_deg=(spine, 0.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, 0.07), is_locked=True),
        hand_L=left, hand_R=right,
    )


def setup_bridge():
    arm, root = _clean_scene()
    return arm, KinematicBridgeExecutor(armature_obj=arm, root_obj=root)


def final_point(arm, name, enabled):
    kind, side = name.split("_")
    bone = arm.pose.bones[("shin." if kind == "foot" else "forearm.") + side] if enabled else arm.pose.bones[("foot." if kind == "foot" else "hand.") + side]
    return tuple(float(x) for x in arm.matrix_world @ (bone.tail if enabled else bone.head))


def validate_feedback(arm, wbc_result, eps=1e-5):
    bpy.context.view_layer.update()
    errors = {}
    for name in ("foot_L", "foot_R", "hand_L", "hand_R"):
        fb = wbc_result.end_effectors[name]
        point = final_point(arm, name, fb.enabled)
        assert math.dist(point, fb.actual_world_xyz) <= eps, (name, "actual position", point, fb.actual_world_xyz)
        if fb.enabled:
            error = math.dist(point, fb.requested_world_xyz)
            assert abs(error - fb.position_error_m) <= eps, (name, "position error", error, fb.position_error_m)
            assert math.isfinite(error)
            errors[name] = error
        else:
            assert fb.position_error_m == 0.0, (name, "disabled error")
    expected_max = max(errors.values(), default=0.0)
    assert abs(wbc_result.max_end_effector_error_m - expected_max) <= eps, ("aggregate", expected_max, wbc_result.max_end_effector_error_m)
    return errors


def t07():
    arm, bridge = setup_bridge()
    result = bridge.execute_frame(pose(left=hand("L"), right=hand("R")), keyframe=False, enforce_rom_clamping=True)
    wb = result.wbc_result
    assert wb.has_rom_violation is True
    assert wb.success is False and result.success is False
    errors = validate_feedback(arm, wb)
    assert result.tracking_errors.keys() == errors.keys()
    for name in errors:
        assert abs(result.tracking_errors[name] - wb.end_effectors[name].position_error_m) <= 1e-9
        assert abs(result.motion_state.params["tracking_errors_m"][name] - wb.end_effectors[name].position_error_m) <= 1e-9
    assert any(d.category == "ROM_VIOLATION" for d in wb.unmet_constraints)
    return {"max_error_m": wb.max_end_effector_error_m, "active": sorted(errors)}


def t08():
    arm, bridge = setup_bridge()
    result = bridge.execute_frame(pose(left=hand("L"), right=hand("R")), keyframe=False, enforce_rom_clamping=True)
    wb = result.wbc_result
    for name in ("foot_L", "foot_R", "hand_L", "hand_R"):
        fb = wb.end_effectors[name]
        current = [d for d in wb.unmet_constraints if d.target_name == name and d.category in ("REACHABILITY", "ORIENTATION_ERROR")]
        assert len([d for d in current if d.category == "REACHABILITY"]) <= 1, name
        assert len([d for d in current if d.category == "ORIENTATION_ERROR"]) <= 1, name
        reach = [d for d in current if d.category == "REACHABILITY"]
        if reach:
            assert fb.enabled, (name, "disabled diagnostic")
            assert abs(reach[0].error_amount - fb.position_error_m) <= 1e-9, (name, "stale error")
    return {"diagnoses": [(x.category, x.target_name) for x in wb.unmet_constraints]}


def t09():
    arm, bridge = setup_bridge()
    result = bridge.execute_frame(pose(left=hand("L", enabled=True, weight=0.0), right=hand("R")), keyframe=False, enforce_rom_clamping=True)
    wb = result.wbc_result
    assert wb.has_rom_violation is True
    assert wb.end_effectors["hand_L"].enabled is False
    assert wb.end_effectors["hand_L"].weight == 0.0
    assert wb.end_effectors["hand_L"].position_error_m == 0.0
    assert wb.end_effectors["hand_R"].enabled is True
    assert math.dist(wb.end_effectors["hand_L"].actual_world_xyz, final_point(arm, "hand_L", False)) < 1e-5
    validate_feedback(arm, wb)
    return {"left_enabled": False, "right_enabled": True}


def t10():
    arm, bridge = setup_bridge()
    normal = pose(spine=0.0, left=hand("L"), right=hand("R"))
    old_function = kb._reconcile_post_rom_feedback
    def forbidden_reconciler(*args, **kwargs):
        raise AssertionError("Reconciler must not run when ROM clamping is disabled")
    kb._reconcile_post_rom_feedback = forbidden_reconciler
    try:
        result = bridge.execute_frame(normal, keyframe=False, enforce_rom_clamping=False)
    finally:
        kb._reconcile_post_rom_feedback = old_function
    assert bridge._last_time_sec == normal.time_seconds
    assert bridge._last_frame == normal.frame
    assert result.tracking_errors == {name: x.position_error_m for name, x in result.wbc_result.end_effectors.items() if x.enabled}
    return {"frame": bridge._last_frame, "without_clamp": True}


def t11():
    arm, _ = setup_bridge()
    wbc = WholeBodyController(armature_obj=arm)
    planned = pose(left=hand("L", pos=(-0.24, -6.0, 1.3)), right=hand("R"))
    targets = convert_planned_pose_to_wbc_targets(planned)
    raw = wbc.execute_frame(targets, enforce_rom_clamping=True)
    assert raw.has_rom_violation is True
    bpy.context.view_layer.update()
    before_rom = [d for d in raw.unmet_constraints if d.category in ("ROM_VIOLATION", "ROM_CONFLICT")]
    a = kb._reconcile_post_rom_feedback(arm, targets, raw)
    b = kb._reconcile_post_rom_feedback(arm, targets, a)
    assert a is not raw and a.end_effectors is not raw.end_effectors
    assert [d for d in a.unmet_constraints if d.category in ("ROM_VIOLATION", "ROM_CONFLICT")] == before_rom
    assert [d for d in b.unmet_constraints if d.category in ("ROM_VIOLATION", "ROM_CONFLICT")] == before_rom
    assert a.end_effectors == b.end_effectors
    assert a.unmet_constraints == b.unmet_constraints
    validate_feedback(arm, a)
    return {"rom_diagnoses_retained": len(before_rom), "idempotent": True}


def t12():
    arm, bridge = setup_bridge()
    original = kb._reconcile_post_rom_feedback
    before_actions = len(bpy.data.actions)
    def injected_failure(*args, **kwargs):
        raise RuntimeError("TEST_INJECTED_POST_ROM_READ_FAILURE")
    kb._reconcile_post_rom_feedback = injected_failure
    try:
        try:
            bridge.execute_frame(pose(left=hand("L")), keyframe=True, enforce_rom_clamping=True)
        except RuntimeError as exc:
            assert "TEST_INJECTED_POST_ROM_READ_FAILURE" in str(exc), str(exc)
        else:
            raise AssertionError("Missing propagation of injected post-ROM failure")
    finally:
        kb._reconcile_post_rom_feedback = original
    assert bridge._last_frame is None and bridge._last_time_sec is None
    assert bridge.last_multi_contact is None
    assert bridge.last_active_limb_targets is None
    assert len(bpy.data.actions) == before_actions, "Unexpected keyframe action created"
    return {"injection_propagated": True, "bridge_time_not_advanced": True}


def t13():
    arm, _ = setup_bridge()
    wbc = WholeBodyController(armature_obj=arm)
    targets = convert_planned_pose_to_wbc_targets(pose(left=hand("L"), right=hand("R")))
    raw = wbc.execute_frame(targets, enforce_rom_clamping=True)
    bpy.context.view_layer.update()
    bad = replace(raw, end_effectors={name: fb for name, fb in raw.end_effectors.items() if name != "hand_R"})
    try:
        kb._reconcile_post_rom_feedback(arm, targets, bad)
    except RuntimeError as exc:
        assert "POST_ROM_FEEDBACK_MISSING: hand_R" in str(exc)
    else:
        raise AssertionError("Missing feedback must fail closed")
    assert "hand_R" in raw.end_effectors
    return {"missing_feedback_rejected": True}


TESTS = [
    ("C4-T07", t07),
    ("C4-T08", t08),
    ("C4-T09", t09),
    ("C4-T10", t10),
    ("C4-T11", t11),
    ("C4-T12", t12),
    ("C4-T13", t13),
]
for test_name, func in TESTS:
    check(test_name, func)
assert len(records) == 7 and all(r["status"] == "PASS" for r in records)
print("TASK10C_CHILD4_POST_ROM_ALL_7_PASS", flush=True)
