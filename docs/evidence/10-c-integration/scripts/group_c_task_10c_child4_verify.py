import sys
sys.dont_write_bytecode = True

import json
import math
import os
import runpy
import traceback

REPO_ROOT = os.getcwd()
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bpy
from mathutils import Euler, Vector

from src.motion.kinematic_bridge import (
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
    convert_planned_pose_to_wbc_targets,
)
from src.motion.whole_body_controller import WholeBodyController
from src.rig.arm_ik import MAX_ARM_REACH, get_arm_ik_state

BRIDGE_TEST_PATH = os.path.join(REPO_ROOT, "tests", "verify_task6gc_r3b1_bridge.py")
BRIDGE_MOD = runpy.run_path(BRIDGE_TEST_PATH, run_name="_bridge_test_mod")
_clean_scene = BRIDGE_MOD["_clean_scene"]
test_04_truthful_rom_and_reach_failure_reporting = BRIDGE_MOD["test_04_truthful_rom_and_reach_failure_reporting"]

EVIDENCE_DIR = os.path.join(REPO_ROOT, "docs", "evidence", "10-c-child4")
RESULTS_PATH = os.path.join(EVIDENCE_DIR, "results.json")


def vec_tuple(v):
    return [float(v[0]), float(v[1]), float(v[2])]


def euclid(a, b):
    return math.sqrt(
        (float(a[0]) - float(b[0])) ** 2
        + (float(a[1]) - float(b[1])) ** 2
        + (float(a[2]) - float(b[2])) ** 2
    )


def independent_rot_err_deg(req_euler_deg, arm, side):
    q_t = Euler(tuple(math.radians(float(v)) for v in req_euler_deg), "XYZ").to_quaternion().normalized()
    p_hand = arm.pose.bones[f"hand.{side}"]
    hand_w_mat = (arm.matrix_world @ p_hand.matrix).to_3x3()
    q_a = hand_w_mat.to_quaternion().normalized()
    dot_abs = abs(q_t.w * q_a.w + q_t.x * q_a.x + q_t.y * q_a.y + q_t.z * q_a.z)
    dot_abs = max(0.0, min(1.0, dot_abs))
    return math.degrees(2.0 * math.acos(dot_abs))


def make_base_feet():
    return (
        PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        PlannedFootTarget(world_xyz=(0.11, -8.0, 0.07), is_locked=True),
    )


def run_c4_t01():
    metrics = {}
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)
    foot_l, foot_r = make_base_feet()
    req_l_pos = (-0.24, -7.65, 1.35)
    req_l_rot = (20.0, 10.0, -5.0)
    req_r_pos = (0.24, -7.70, 1.25)
    req_r_rot = (15.0, -10.0, 5.0)

    planned = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(world_xyz=req_l_pos, rotation_deg=req_l_rot, enabled=True, weight=1.0),
        hand_R=PlannedHandTarget(world_xyz=req_r_pos, rotation_deg=req_r_rot, enabled=True, weight=1.0),
    )
    targets = convert_planned_pose_to_wbc_targets(planned)
    res = wbc.execute_frame(targets, update_scene=True)

    st_l = get_arm_ik_state(arm, "L")
    st_r = get_arm_ik_state(arm, "R")
    fb_l = res.end_effectors["hand_L"]
    fb_r = res.end_effectors["hand_R"]

    ep_l = euclid(st_l["wrist_world"], req_l_pos)
    ep_r = euclid(st_r["wrist_world"], req_r_pos)
    er_l = independent_rot_err_deg(req_l_rot, arm, "L")
    er_r = independent_rot_err_deg(req_r_rot, arm, "R")

    pos_fb_vs_wrist_l = euclid(fb_l.actual_world_xyz, st_l["wrist_world"])
    pos_fb_vs_wrist_r = euclid(fb_r.actual_world_xyz, st_r["wrist_world"])
    pos_err_diff_l = abs(float(fb_l.position_error_m) - ep_l)
    pos_err_diff_r = abs(float(fb_r.position_error_m) - ep_r)
    rot_err_diff_l = abs(float(fb_l.orientation_error_deg) - er_l) if fb_l.orientation_error_deg is not None else None
    rot_err_diff_r = abs(float(fb_r.orientation_error_deg) - er_r) if fb_r.orientation_error_deg is not None else None
    wrist_to_tip_l = euclid(st_l["wrist_world"], st_l["hand_tip_world"])
    wrist_to_tip_r = euclid(st_r["wrist_world"], st_r["hand_tip_world"])

    metrics.update({
        "wbc_success": bool(res.success),
        "hand_L": {
            "requested_world_xyz": list(req_l_pos),
            "target_world": vec_tuple(st_l["target_world"]),
            "wrist_world": vec_tuple(st_l["wrist_world"]),
            "hand_tip_world": vec_tuple(st_l["hand_tip_world"]),
            "wrist_to_tip_m": wrist_to_tip_l,
            "feedback_actual_world_xyz": vec_tuple(fb_l.actual_world_xyz),
            "feedback_vs_wrist_diff_m": pos_fb_vs_wrist_l,
            "feedback_position_error_m": float(fb_l.position_error_m),
            "independent_e_p_m": ep_l,
            "position_error_diff_m": pos_err_diff_l,
            "requested_rotation_deg": list(req_l_rot),
            "hand_world_euler_deg": list(st_l["hand_world_euler_deg"]),
            "feedback_actual_rotation_deg": list(fb_l.actual_rotation_deg) if fb_l.actual_rotation_deg is not None else None,
            "feedback_orientation_error_deg": float(fb_l.orientation_error_deg) if fb_l.orientation_error_deg is not None else None,
            "independent_e_R_deg": er_l,
            "orientation_error_diff_deg": rot_err_diff_l,
        },
        "hand_R": {
            "requested_world_xyz": list(req_r_pos),
            "target_world": vec_tuple(st_r["target_world"]),
            "wrist_world": vec_tuple(st_r["wrist_world"]),
            "hand_tip_world": vec_tuple(st_r["hand_tip_world"]),
            "wrist_to_tip_m": wrist_to_tip_r,
            "feedback_actual_world_xyz": vec_tuple(fb_r.actual_world_xyz),
            "feedback_vs_wrist_diff_m": pos_fb_vs_wrist_r,
            "feedback_position_error_m": float(fb_r.position_error_m),
            "independent_e_p_m": ep_r,
            "position_error_diff_m": pos_err_diff_r,
            "requested_rotation_deg": list(req_r_rot),
            "hand_world_euler_deg": list(st_r["hand_world_euler_deg"]),
            "feedback_actual_rotation_deg": list(fb_r.actual_rotation_deg) if fb_r.actual_rotation_deg is not None else None,
            "feedback_orientation_error_deg": float(fb_r.orientation_error_deg) if fb_r.orientation_error_deg is not None else None,
            "independent_e_R_deg": er_r,
            "orientation_error_diff_deg": rot_err_diff_r,
        },
    })

    # 1. Routing to correct effectors
    assert targets.hand_L.effector_id == "hand_L" and targets.hand_L.target_world_xyz == req_l_pos
    assert targets.hand_R.effector_id == "hand_R" and targets.hand_R.target_world_xyz == req_r_pos
    assert euclid(st_l["target_world"], req_l_pos) <= 1e-5, f"L target routing mismatch: {st_l['target_world']}"
    assert euclid(st_r["target_world"], req_r_pos) <= 1e-5, f"R target routing mismatch: {st_r['target_world']}"
    assert fb_l.effector_id == "hand_L" and fb_r.effector_id == "hand_R"
    assert fb_l.requested_world_xyz == req_l_pos and fb_r.requested_world_xyz == req_r_pos
    assert fb_l.requested_rotation_deg == req_l_rot and fb_r.requested_rotation_deg == req_r_rot

    # 2. Actual pos equals wrist_world (not fingertip)
    assert pos_fb_vs_wrist_l <= 1e-5, f"L actual_world_xyz != wrist_world: diff={pos_fb_vs_wrist_l}"
    assert pos_fb_vs_wrist_r <= 1e-5, f"R actual_world_xyz != wrist_world: diff={pos_fb_vs_wrist_r}"
    assert wrist_to_tip_l > 0.05 and wrist_to_tip_r > 0.05, "Wrist and fingertip must be distinct"
    assert euclid(fb_l.actual_world_xyz, st_l["hand_tip_world"]) > 0.05
    assert euclid(fb_r.actual_world_xyz, st_r["hand_tip_world"]) > 0.05

    # 3. Position error matches independent Euclidean distance within 1e-5 m
    assert pos_err_diff_l <= 1e-5, f"L position_error_m mismatch: diff={pos_err_diff_l}"
    assert pos_err_diff_r <= 1e-5, f"R position_error_m mismatch: diff={pos_err_diff_r}"

    # 4. Actual rotation matches hand_world_euler_deg
    assert fb_l.actual_rotation_deg is not None and fb_r.actual_rotation_deg is not None
    assert max(abs(a - b) for a, b in zip(fb_l.actual_rotation_deg, st_l["hand_world_euler_deg"])) <= 1e-4
    assert max(abs(a - b) for a, b in zip(fb_r.actual_rotation_deg, st_r["hand_world_euler_deg"])) <= 1e-4

    # 5. Orientation error matches independent quaternion angle within 0.01 deg
    assert rot_err_diff_l is not None and rot_err_diff_l <= 0.01, f"L rot_err diff={rot_err_diff_l}"
    assert rot_err_diff_r is not None and rot_err_diff_r <= 0.01, f"R rot_err diff={rot_err_diff_r}"

    # 6. No L/R crosstalk
    assert fb_l.actual_world_xyz[0] < 0.0 and fb_r.actual_world_xyz[0] > 0.0
    assert euclid(fb_l.actual_world_xyz, req_r_pos) > 0.3
    assert euclid(fb_r.actual_world_xyz, req_l_pos) > 0.3
    assert independent_rot_err_deg(req_r_rot, arm, "L") > 5.0
    assert independent_rot_err_deg(req_l_rot, arm, "R") > 5.0

    # Tracking tolerances for reachable targets
    assert ep_l <= 0.005 and fb_l.position_error_m <= 0.005, f"L tracking pos err > 5mm: {ep_l}"
    assert ep_r <= 0.005 and fb_r.position_error_m <= 0.005, f"R tracking pos err > 5mm: {ep_r}"
    assert er_l <= 1.0 and fb_l.orientation_error_deg <= 1.0, f"L tracking rot err > 1deg: {er_l}"
    assert er_r <= 1.0 and fb_r.orientation_error_deg <= 1.0, f"R tracking rot err > 1deg: {er_r}"
    assert res.success is True, f"Expected WBC success=True, unmet={res.unmet_constraints}"

    return metrics


def run_c4_t02():
    metrics = {}
    # Sub-part 1: Pole world consumption (fresh scene)
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)
    foot_l, foot_r = make_base_feet()
    pole_l_req = (-0.55, -8.45, 1.25)
    pole_r_req = (0.62, -8.35, 1.18)

    planned_pole = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(
            world_xyz=(-0.24, -7.65, 1.35),
            pole_hint_world_xyz=pole_l_req,
            enabled=True,
            weight=1.0,
        ),
        hand_R=PlannedHandTarget(
            world_xyz=(0.24, -7.70, 1.25),
            pole_hint_world_xyz=pole_r_req,
            enabled=True,
            weight=1.0,
        ),
    )
    wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_pole), update_scene=True)
    st_l = get_arm_ik_state(arm, "L")
    st_r = get_arm_ik_state(arm, "R")
    pole_l_err = euclid(st_l["pole_world"], pole_l_req)
    pole_r_err = euclid(st_r["pole_world"], pole_r_req)

    metrics["pole"] = {
        "requested_L": list(pole_l_req),
        "actual_L": vec_tuple(st_l["pole_world"]),
        "error_L_m": pole_l_err,
        "requested_R": list(pole_r_req),
        "actual_R": vec_tuple(st_r["pole_world"]),
        "error_R_m": pole_r_err,
    }

    assert pole_l_err <= 1e-4, f"L pole_world mismatch: err={pole_l_err}"
    assert pole_r_err <= 1e-4, f"R pole_world mismatch: err={pole_r_err}"
    assert euclid(st_l["pole_world"], st_r["pole_world"]) > 0.5, "L and R poles must be distinct"

    # Sub-part 2A: Clamp True (fresh scene)
    unreachable_l = (-0.24, -6.20, 1.30)
    arm_t, _ = _clean_scene()
    wbc_t = WholeBodyController(armature_obj=arm_t)
    foot_l, foot_r = make_base_feet()
    planned_ct = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(
            world_xyz=unreachable_l,
            enabled=True,
            weight=1.0,
            clamp_reach=True,
        ),
    )
    wbc_t.execute_frame(convert_planned_pose_to_wbc_targets(planned_ct), update_scene=True)
    st_ct = get_arm_ik_state(arm_t, "L")
    raw_dist_ct = euclid(unreachable_l, st_ct["shoulder_world"])
    target_dist_ct = euclid(st_ct["target_world"], st_ct["shoulder_world"])

    metrics["clamp_true"] = {
        "requested_world_xyz": list(unreachable_l),
        "shoulder_world": vec_tuple(st_ct["shoulder_world"]),
        "applied_target_world": vec_tuple(st_ct["target_world"]),
        "raw_distance_to_shoulder_m": raw_dist_ct,
        "applied_distance_to_shoulder_m": target_dist_ct,
        "max_arm_reach_m": float(MAX_ARM_REACH),
    }

    assert raw_dist_ct > MAX_ARM_REACH + 0.5, f"Test target not sufficiently out of reach: {raw_dist_ct}"
    assert target_dist_ct <= MAX_ARM_REACH + 1e-3, f"clamp_reach=True exceeded MAX_ARM_REACH+1e-3: {target_dist_ct}"

    # Sub-part 2B: Clamp False (fresh scene)
    arm_f, _ = _clean_scene()
    wbc_f = WholeBodyController(armature_obj=arm_f)
    foot_l, foot_r = make_base_feet()
    planned_cf = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(
            world_xyz=unreachable_l,
            enabled=True,
            weight=1.0,
            clamp_reach=False,
        ),
    )
    wbc_f.execute_frame(convert_planned_pose_to_wbc_targets(planned_cf), update_scene=True)
    st_cf = get_arm_ik_state(arm_f, "L")
    unclamped_diff = euclid(st_cf["target_world"], unreachable_l)
    target_dist_cf = euclid(st_cf["target_world"], st_cf["shoulder_world"])

    metrics["clamp_false"] = {
        "requested_world_xyz": list(unreachable_l),
        "shoulder_world": vec_tuple(st_cf["shoulder_world"]),
        "applied_target_world": vec_tuple(st_cf["target_world"]),
        "diff_from_requested_m": unclamped_diff,
        "applied_distance_to_shoulder_m": target_dist_cf,
    }

    assert unclamped_diff < 1e-4, f"clamp_reach=False did not preserve raw coords: diff={unclamped_diff}"
    return metrics


def run_c4_t03():
    metrics = {"frames": []}
    # Single scene for all 3 frames (MUST NOT re-initialize between frames)
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)

    frame_specs = [
        (1, True, 1.0, True, 1.0, 1.0, 1.0, True, True),
        (2, True, 0.0, True, 1.0, 0.0, 1.0, False, True),
        (3, False, 1.0, True, 1.0, 0.0, 1.0, False, True),
    ]

    for f_idx, l_en, l_w, r_en, r_w, exp_l_inf, exp_r_inf, exp_l_fb_en, exp_r_fb_en in frame_specs:
        foot_l, foot_r = make_base_feet()
        planned = KinematicPlannedPose(
            frame=f_idx,
            time_seconds=(f_idx - 1) / 24.0,
            root_position=(0.0, -8.0, 0.0),
            foot_L=foot_l,
            foot_R=foot_r,
            hand_L=PlannedHandTarget(world_xyz=(-0.24, -7.65, 1.35), enabled=l_en, weight=l_w),
            hand_R=PlannedHandTarget(world_xyz=(0.24, -7.70, 1.25), enabled=r_en, weight=r_w),
        )
        res = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned), update_scene=True)
        st_l = get_arm_ik_state(arm, "L")
        st_r = get_arm_ik_state(arm, "R")
        fb_l = res.end_effectors["hand_L"]
        fb_r = res.end_effectors["hand_R"]

        frame_rec = {
            "frame": f_idx,
            "input": {"hand_L": {"enabled": l_en, "weight": l_w}, "hand_R": {"enabled": r_en, "weight": r_w}},
            "ik_influence_L": float(st_l["ik_influence"]),
            "ik_influence_R": float(st_r["ik_influence"]),
            "feedback_enabled_L": bool(fb_l.enabled),
            "feedback_enabled_R": bool(fb_r.enabled),
            "feedback_weight_L": float(fb_l.weight),
            "feedback_weight_R": float(fb_r.weight),
        }
        metrics["frames"].append(frame_rec)

        assert abs(float(st_l["ik_influence"]) - exp_l_inf) <= 1e-6, (
            f"Frame {f_idx} L ik_influence={st_l['ik_influence']} != {exp_l_inf}"
        )
        assert abs(float(st_r["ik_influence"]) - exp_r_inf) <= 1e-6, (
            f"Frame {f_idx} R ik_influence={st_r['ik_influence']} != {exp_r_inf}"
        )
        assert fb_l.enabled is exp_l_fb_en, (
            f"Frame {f_idx} feedback hand_L.enabled={fb_l.enabled} != {exp_l_fb_en}"
        )
        assert fb_r.enabled is exp_r_fb_en, (
            f"Frame {f_idx} feedback hand_R.enabled={fb_r.enabled} != {exp_r_fb_en}"
        )

    return metrics


def run_c4_t04():
    metrics = {}
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)
    foot_l, foot_r = make_base_feet()
    planned = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(world_xyz=(-0.24, -6.00, 1.30), enabled=True, weight=1.0),
        hand_R=PlannedHandTarget(world_xyz=(0.24, -7.70, 1.25), enabled=True, weight=1.0),
    )
    res = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned), update_scene=True)
    fb_l = res.end_effectors["hand_L"]
    fb_r = res.end_effectors["hand_R"]

    unmet_list = [
        {"category": uc.category, "target_name": uc.target_name, "error_amount": float(uc.error_amount)}
        for uc in res.unmet_constraints
    ]

    metrics.update({
        "success": bool(res.success),
        "is_all_reachable": bool(res.is_all_reachable),
        "hand_L": {
            "is_reachable": bool(fb_l.is_reachable),
            "actual_world_xyz": vec_tuple(fb_l.actual_world_xyz),
            "position_error_m": float(fb_l.position_error_m),
            "reach_distance_m": float(fb_l.reach_distance_m),
        },
        "hand_R": {
            "is_reachable": bool(fb_r.is_reachable),
            "actual_world_xyz": vec_tuple(fb_r.actual_world_xyz),
            "position_error_m": float(fb_r.position_error_m),
            "reach_distance_m": float(fb_r.reach_distance_m),
        },
        "unmet_constraints": unmet_list,
    })

    assert fb_l.is_reachable is False, f"Expected hand_L.is_reachable=False, got {fb_l.is_reachable}"
    assert fb_r.is_reachable is True, f"Expected hand_R.is_reachable=True, got {fb_r.is_reachable}"
    assert res.success is False, f"Expected global success=False, got {res.success}"
    assert any(uc.category == "REACHABILITY" and uc.target_name == "hand_L" for uc in res.unmet_constraints), (
        f"Missing hand_L REACHABILITY in unmet_constraints: {unmet_list}"
    )
    assert not any(uc.category == "REACHABILITY" and uc.target_name == "hand_R" for uc in res.unmet_constraints), (
        f"Unexpected hand_R REACHABILITY misattribution: {unmet_list}"
    )
    for side_lbl, fb in (("hand_L", fb_l), ("hand_R", fb_r)):
        assert all(math.isfinite(float(c)) for c in fb.actual_world_xyz), f"{side_lbl} non-finite actual_world_xyz"
        assert math.isfinite(float(fb.position_error_m)), f"{side_lbl} non-finite position_error_m"

    return metrics


def run_c4_t05():
    metrics = {}
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)
    foot_l, foot_r = make_base_feet()
    req_l_pos = (-0.24, -7.65, 1.35)
    req_l_rot = (20.0, 10.0, -5.0)
    req_r_pos = (0.24, -7.70, 1.25)
    req_r_rot = (15.0, -10.0, 5.0)

    planned = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        spine_rotation_deg=(85.0, 0.0, 0.0),
        foot_L=foot_l,
        foot_R=foot_r,
        hand_L=PlannedHandTarget(world_xyz=req_l_pos, rotation_deg=req_l_rot, enabled=True, weight=1.0),
        hand_R=PlannedHandTarget(world_xyz=req_r_pos, rotation_deg=req_r_rot, enabled=True, weight=1.0),
    )
    targets = convert_planned_pose_to_wbc_targets(planned)
    res = wbc.execute_frame(
        targets,
        update_scene=True,
        enforce_rom_clamping=True,
    )

    # Re-read actual final scene state AFTER ROM clamping
    final_l = get_arm_ik_state(arm, "L")
    final_r = get_arm_ik_state(arm, "R")
    p_spine = arm.pose.bones["spine"]
    final_spine_deg = [math.degrees(v) for v in p_spine.rotation_euler]

    unmet_list = [
        {"category": uc.category, "target_name": uc.target_name, "error_amount": float(uc.error_amount)}
        for uc in res.unmet_constraints
    ]

    metrics["success"] = bool(res.success)
    metrics["has_rom_violation"] = bool(res.has_rom_violation)
    metrics["rom_validation_is_valid"] = bool(res.rom_validation.is_valid)
    metrics["rom_violations"] = list(res.rom_validation.violations.keys())
    metrics["final_spine_euler_deg"] = final_spine_deg
    metrics["unmet_constraints"] = unmet_list

    hand_checks = {}
    for side, req_pos, req_rot, final_st in (
        ("L", req_l_pos, req_l_rot, final_l),
        ("R", req_r_pos, req_r_rot, final_r),
    ):
        eff_id = f"hand_{side}"
        fb = res.end_effectors[eff_id]
        final_wrist = vec_tuple(final_st["wrist_world"])
        fb_actual = vec_tuple(fb.actual_world_xyz)
        actual_pos_diff = euclid(fb_actual, final_wrist)
        recomputed_pos_err = euclid(final_wrist, req_pos)
        pos_err_diff = abs(float(fb.position_error_m) - recomputed_pos_err)

        final_rot_err = independent_rot_err_deg(req_rot, arm, side)
        fb_rot_err = float(fb.orientation_error_deg) if fb.orientation_error_deg is not None else None
        rot_err_diff = abs(fb_rot_err - final_rot_err) if fb_rot_err is not None else None
        final_euler = list(final_st["hand_world_euler_deg"])
        fb_euler = list(fb.actual_rotation_deg) if fb.actual_rotation_deg is not None else None
        euler_max_diff = (
            max(abs(a - b) for a, b in zip(fb_euler, final_euler))
            if fb_euler is not None
            else None
        )

        hand_checks[eff_id] = {
            "requested_world_xyz": list(req_pos),
            "final_actual_wrist_world": final_wrist,
            "returned_actual_world_xyz": fb_actual,
            "actual_pos_mismatch_m": actual_pos_diff,
            "final_recomputed_position_error_m": recomputed_pos_err,
            "returned_position_error_m": float(fb.position_error_m),
            "position_error_mismatch_m": pos_err_diff,
            "final_hand_world_euler_deg": final_euler,
            "returned_actual_rotation_deg": fb_euler,
            "euler_max_mismatch_deg": euler_max_diff,
            "final_recomputed_orientation_error_deg": final_rot_err,
            "returned_orientation_error_deg": fb_rot_err,
            "orientation_error_mismatch_deg": rot_err_diff,
        }

    metrics["hands"] = hand_checks

    # 1. ROM violation explicitly detected
    assert res.has_rom_violation is True, "Expected has_rom_violation=True"
    assert res.rom_validation.is_valid is False, "Expected rom_validation.is_valid=False"
    assert "spine" in res.rom_validation.violations, f"Expected spine in violations: {res.rom_validation.violations}"

    # 2. success=False
    assert res.success is False, "Expected success=False on ROM violation with clamping"

    # 3. Violation in unmet_constraints
    assert any(uc.category == "ROM_VIOLATION" and uc.target_name == "spine" for uc in res.unmet_constraints), (
        f"Expected spine ROM_VIOLATION in unmet_constraints: {unmet_list}"
    )

    # 4-8. Post-ROM actual wrist & orientation vs returned feedback (tolerance 1e-4 m, 0.01 deg)
    for eff_id, hc in hand_checks.items():
        assert hc["actual_pos_mismatch_m"] <= 1e-4, (
            f"{eff_id} returned actual_world_xyz disagrees with post-ROM final wrist_world by "
            f"{hc['actual_pos_mismatch_m']:.6f} m (> 1e-4 m): "
            f"returned={hc['returned_actual_world_xyz']}, final={hc['final_actual_wrist_world']}"
        )
        assert hc["position_error_mismatch_m"] <= 1e-4, (
            f"{eff_id} returned position_error_m ({hc['returned_position_error_m']:.6f} m) "
            f"disagrees with post-ROM recomputed Euclidean error ({hc['final_recomputed_position_error_m']:.6f} m) "
            f"by {hc['position_error_mismatch_m']:.6f} m (> 1e-4 m)"
        )
        assert hc["euler_max_mismatch_deg"] is not None and hc["euler_max_mismatch_deg"] <= 0.01, (
            f"{eff_id} returned actual_rotation_deg disagrees with post-ROM final hand_world_euler_deg by "
            f"{hc['euler_max_mismatch_deg']} deg"
        )
        assert hc["orientation_error_mismatch_deg"] is not None and hc["orientation_error_mismatch_deg"] <= 0.01, (
            f"{eff_id} returned orientation_error_deg ({hc['returned_orientation_error_deg']}) "
            f"disagrees with post-ROM recomputed orientation error ({hc['final_recomputed_orientation_error_deg']}) "
            f"by {hc['orientation_error_mismatch_deg']} deg"
        )

    return metrics


def run_c4_t06():
    ret = test_04_truthful_rom_and_reach_failure_reporting()
    metrics = {"return_value": ret}
    assert ret is True, f"test_04_truthful_rom_and_reach_failure_reporting() returned {ret!r}, expected True"
    return metrics


TESTS = [
    ("C4-T01", run_c4_t01),
    ("C4-T02", run_c4_t02),
    ("C4-T03", run_c4_t03),
    ("C4-T04", run_c4_t04),
    ("C4-T05", run_c4_t05),
    ("C4-T06", run_c4_t06),
]


def main():
    report = {
        "node": "10-c-child4",
        "frozen_source_head": "9f7ad1af04c4a542df0e73843be49eb5f8c55136",
        "stage1_docs_commit_head": "9e88ede441d589bf57274015adb639a1ffa03a7a",
        "production_file": "src/motion/kinematic_bridge.py",
        "production_blob": "9bda0a3f82d679a74b3358e9ebfbc92349e52593",
        "blender_version": bpy.app.version_string,
        "blender_version_tuple": list(bpy.app.version),
        "executed": 0,
        "passed": 0,
        "failed": 0,
        "not_run": len(TESTS),
        "tests": {},
    }
    for test_id, _ in TESTS:
        report["tests"][test_id] = {"status": "NOT_RUN", "metrics": {}, "error": None}

    failed = False
    try:
        for test_id, fn in TESTS:
            print(f"=== RUNNING {test_id} ===", flush=True)
            report["executed"] += 1
            report["not_run"] -= 1
            # Capture metrics even if assertion fails by passing a holder? Better: catch exception and let fn attach metrics?
            # Actually let's wrap so we always capture metrics!
            try:
                m = fn()
                report["tests"][test_id] = {"status": "PASS", "metrics": m, "error": None}
                report["passed"] += 1
                print(f"[PASS] {test_id}", flush=True)
            except BaseException as exc:
                tb = traceback.format_exc()
                # If exception occurred inside run_c4_t05, extract local 'metrics' from traceback frame for complete audit evidence!
                captured_metrics = {}
                tb_obj = exc.__traceback__
                while tb_obj is not None:
                    if tb_obj.tb_frame.f_code.co_name == fn.__name__:
                        if isinstance(tb_obj.tb_frame.f_locals.get("metrics"), dict):
                            captured_metrics = tb_obj.tb_frame.f_locals["metrics"]
                        break
                    tb_obj = tb_obj.tb_next
                report["tests"][test_id] = {
                    "status": "FAIL",
                    "metrics": captured_metrics,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": tb,
                }
                report["failed"] += 1
                failed = True
                print(f"[FAIL] {test_id}: {type(exc).__name__}: {exc}", flush=True)
                print(tb, file=sys.stderr, flush=True)
                break  # Fail-Fast
    finally:
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(
            f"SUMMARY: executed={report['executed']} passed={report['passed']} "
            f"failed={report['failed']} not_run={report['not_run']}",
            flush=True,
        )

    if failed:
        raise SystemExit(1)


main()
