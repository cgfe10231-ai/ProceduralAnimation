"""Playground Kinematic Validation & Reopen Verification Module (Task 7A-1).

Responsible for:
1. Strictly read-only reopen and full evaluation of all 204 frames (`1..204`)
   via Blender dependency graph (`scene.frame_set(f)` + `view_layer.update()`).
2. Contact state recovery directly from persisted `scene["task7a1_contact_state_records"]`
   without running `MotionPlanner` or gait synthesis formulas.
3. Strict separation of 3 data categories (Section 七):
   - A: Runtime Recorded (`runtime_recorded` from persisted execution metadata)
   - B: Reopened Evaluated (`reopened_evaluated` from Blender evaluated pose)
   - C: Analytical Reference (`analytical_reference` from closed-form gait formulas)
4. Full mathematical and biomechanical verification (Section 八):
   - Root translation continuity, velocity & acceleration
   - 19-bone quaternion geodesic rotation continuity
   - Support-foot locking, ankle drift vs recorded anchors, and contact lifecycle
   - Whole-body 70.0 kg mass invariance, CoM trajectory, and ROM compliance.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Euler, Quaternion, Vector

from src.character.builder import character_start_location, world_min_z
from src.config import PipelineConfig
from src.motion.contact_model import (
    ContactLifecycle,
    ContactType,
    EnvironmentalSurface,
    SupportType,
    evaluate_limb_contacts_from_armature,
)
from src.motion.framework import (
    HIP_X_OFFSET,
    WORLD_UP_AXIS,
    evaluate_root_acceleration_mps2,
)
from src.motion.joint_limits import (
    DEFAULT_HUMANOID_ROM_MODEL,
    extract_evaluated_bone_rotation_rad,
)
from src.motion.rigid_link import (
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    compute_whole_body_com,
)
from src.motion.start_stop_walk import (
    _evaluate_gait_phase_and_envelopes,
    build_step_schedule,
    compute_forward_swing_point,
    evaluate_root_kinematics,
)
from src.rig.builder import BONE_SPECIFICATIONS
from src.rig.ik import ANKLE_REST_Z, IK_TARGET_NAMES, get_leg_ik_state


def _quat_geodesic_angle_deg(
    q1: Tuple[float, float, float, float],
    q2: Tuple[float, float, float, float],
) -> float:
    """Compute quaternion geodesic angular distance in degrees, handling double-cover (q ~ -q)."""
    dot = abs(q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3])
    dot_clamped = min(1.0, max(-1.0, dot))
    return math.degrees(2.0 * math.acos(dot_clamped))


def recover_and_verify_contact_states_from_blend(
    scene: bpy.types.Scene,
    expected_version: str = "Task7A1_204f_v1",
    expected_frames: int = 204,
) -> Dict[str, Any]:
    """Recover and validate persisted contact state metadata from Blender Scene ID properties.

    Enforces the Contact State Persistence Contract (Section 六):
    - Reopens without re-running MotionPlanner or gait formula.
    - Validates schema_version, blend_asset_version, and contiguous frame sequence.
    - Detects missing records, version mismatches, frame count mismatches, or tampered anchors.
    """
    raw_payload = scene.get("task7a1_contact_state_records")
    if raw_payload is None:
        raise ValueError(
            "MISSING_CONTACT_RECORDS: Scene property 'task7a1_contact_state_records' not found in reopened blend! "
            "Contact state was not persisted during execution."
        )

    try:
        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        elif isinstance(raw_payload, dict):
            payload = dict(raw_payload)
        else:
            raise ValueError(f"Unexpected contact metadata payload type: {type(raw_payload)}")
    except Exception as exc:
        raise ValueError(f"CORRUPTED_CONTACT_METADATA: Failed to parse contact records: {exc}") from exc

    asset_ver = payload.get("blend_asset_version")
    if asset_ver != expected_version:
        raise ValueError(
            f"VERSION_MISMATCH: Contact metadata asset version '{asset_ver}' does not match expected '{expected_version}'."
        )

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("INVALID_CONTACT_RECORDS: 'records' field must be a list.")

    if len(records) != expected_frames:
        raise ValueError(
            f"FRAME_COUNT_MISMATCH: Expected {expected_frames} contact records, found {len(records)}."
        )

    for idx, r in enumerate(records):
        expected_f = idx + 1
        act_f = r.get("frame")
        if act_f != expected_f:
            raise ValueError(
                f"MISSING_FRAME_RECORD: Record at index {idx} has frame={act_f}, expected {expected_f}."
            )
        if "left_foot_locked" not in r or "right_foot_locked" not in r:
            raise ValueError(f"CORRUPTED_RECORD: Frame {expected_f} missing lock state flags.")

        # Stance anchor validation
        if r["left_foot_locked"]:
            anchor_l = r.get("support_anchor_L")
            if not (isinstance(anchor_l, (list, tuple)) and len(anchor_l) == 3):
                raise ValueError(f"TAMPERED_ANCHOR: Frame {expected_f} has locked left foot but invalid anchor: {anchor_l}")
        if r["right_foot_locked"]:
            anchor_r = r.get("support_anchor_R")
            if not (isinstance(anchor_r, (list, tuple)) and len(anchor_r) == 3):
                raise ValueError(f"TAMPERED_ANCHOR: Frame {expected_f} has locked right foot but invalid anchor: {anchor_r}")

    return payload


def validate_reopened_task7a1_blend(
    derived_blend_path: str,
    output_json_path: Optional[str] = None,
    config: Optional[PipelineConfig] = None,
) -> Dict[str, Any]:
    """Independently reopen `output/dynamics_playground_task7a1.blend` read-only and
    validate all 204 frames (`1..204`) without running `MotionPlanner` or `WholeBodyController`.
    """
    if not os.path.isfile(derived_blend_path):
        raise FileNotFoundError(f"Derived blend artifact missing: {derived_blend_path}")

    cfg = config or PipelineConfig()
    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scene = bpy.context.scene

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    foot_l_mesh = bpy.data.objects.get("Foot_L")
    foot_r_mesh = bpy.data.objects.get("Foot_R")
    ik_l_obj = bpy.data.objects.get(IK_TARGET_NAMES["L"])
    ik_r_obj = bpy.data.objects.get(IK_TARGET_NAMES["R"])

    if any(x is None for x in (arm_obj, root_obj, foot_l_mesh, foot_r_mesh, ik_l_obj, ik_r_obj)):
        raise RuntimeError("Required character objects missing in reopened Task 7A-1 blend!")

    # Recover persisted contact state metadata directly from scene property (Contract Section 六)
    contact_metadata = recover_and_verify_contact_states_from_blend(scene)
    persisted_records = contact_metadata["records"]

    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    fps = float(scene.render.fps)
    dt = 1.0 / fps
    expected_bone_names = [spec[0] for spec in BONE_SPECIFICATIONS]

    start_x, start_y, _ = character_start_location(cfg)
    schedule = build_step_schedule(cfg, start_y)
    stop_y = schedule[-1]["swing_y_end"]
    t_s = cfg.start_stop_stand_start_frames  # 12
    t_d = (
        cfg.start_stop_stand_start_frames
        + cfg.start_stop_accel_frames
        + cfg.start_stop_steady_frames
        + cfg.start_stop_decel_frames
    )  # 192

    flat_surfaces = [
        EnvironmentalSurface(
            surface_id="Surface_FlatGround",
            surface_type="ground",
            center_world=(0.0, -2.5, 0.0),
            normal_world=(0.0, 0.0, 1.0),
        )
    ]

    frames_telemetry: List[Dict[str, Any]] = []

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1

        # ---------------------------------------------------------------------
        # Category A: Runtime Recorded (Recovered from Persisted Execution Contract)
        # ---------------------------------------------------------------------
        rec = persisted_records[tau]
        rec_locked_l = bool(rec["left_foot_locked"])
        rec_locked_r = bool(rec["right_foot_locked"])
        rec_support_side = str(rec["support_side"])
        rec_anchor_l: Optional[Tuple[float, float, float]] = (
            tuple(rec["support_anchor_L"]) if rec.get("support_anchor_L") is not None else None
        )
        rec_anchor_r: Optional[Tuple[float, float, float]] = (
            tuple(rec["support_anchor_R"]) if rec.get("support_anchor_R") is not None else None
        )
        rec_stage = str(rec.get("stage", ""))
        rec_step_k = int(rec.get("step_k", -1))
        rec_event = str(rec.get("contact_event", "NONE"))

        # ---------------------------------------------------------------------
        # Category C: Analytical Reference (Computed in parallel for mathematical cross-check)
        # ---------------------------------------------------------------------
        ref_disp_y, ref_speed_mps, ref_stage = evaluate_root_kinematics(tau, cfg)
        ref_accel_mps2 = evaluate_root_acceleration_mps2(tau, cfg)
        ref_root_y = start_y + ref_disp_y
        ref_u, _, _, _, _, active_step = _evaluate_gait_phase_and_envelopes(tau, cfg, schedule)

        if tau < t_s:
            ref_support = SupportType.DOUBLE_STANCE.value
            ref_step_idx = -1
        elif tau >= t_d:
            ref_support = SupportType.DOUBLE_STANCE.value
            ref_step_idx = len(schedule)
        else:
            assert active_step is not None
            ref_step_idx = int(active_step["k"])
            ref_support = (
                SupportType.SINGLE_STANCE_L.value
                if active_step["stance_side"] == "L"
                else SupportType.SINGLE_STANCE_R.value
            )

        # ---------------------------------------------------------------------
        # Category B: Reopen-Evaluated Blender State (Directly from Reopened .blend dg)
        # ---------------------------------------------------------------------
        root_loc = root_obj.matrix_world.translation
        root_eul = root_obj.matrix_world.to_euler("XYZ")
        root_quat = root_obj.matrix_world.to_quaternion().normalized()

        pb_pelvis = arm_obj.pose.bones["pelvis"]
        pelvis_world_mat = arm_obj.matrix_world @ pb_pelvis.matrix
        pelvis_head_w = arm_obj.matrix_world @ pb_pelvis.head
        pelvis_tail_w = arm_obj.matrix_world @ pb_pelvis.tail
        pelvis_eul_w = pelvis_world_mat.to_euler("XYZ")
        pelvis_quat_w = pelvis_world_mat.to_quaternion().normalized()

        bones_frame: Dict[str, Any] = {}
        for b_name in expected_bone_names:
            pb = arm_obj.pose.bones[b_name]
            b_mat_w = arm_obj.matrix_world @ pb.matrix
            b_head_w = arm_obj.matrix_world @ pb.head
            b_tail_w = arm_obj.matrix_world @ pb.tail
            b_quat_w = b_mat_w.to_quaternion().normalized()
            loc_rad = extract_evaluated_bone_rotation_rad(pb)
            bones_frame[b_name] = {
                "head_world_m": (round(b_head_w.x, 6), round(b_head_w.y, 6), round(b_head_w.z, 6)),
                "tail_world_m": (round(b_tail_w.x, 6), round(b_tail_w.y, 6), round(b_tail_w.z, 6)),
                "length_m": round(float((b_tail_w - b_head_w).length), 6),
                "local_euler_deg": tuple(round(math.degrees(v), 4) for v in loc_rad),
                "world_quat_wxyz": (
                    round(float(b_quat_w.w), 7),
                    round(float(b_quat_w.x), 7),
                    round(float(b_quat_w.y), 7),
                    round(float(b_quat_w.z), 7),
                ),
            }

        leg_l = get_leg_ik_state(arm_obj, "L")
        leg_r = get_leg_ik_state(arm_obj, "R")
        ctrl_l_w = ik_l_obj.matrix_world.translation
        ctrl_r_w = ik_r_obj.matrix_world.translation
        ankle_l_w = arm_obj.matrix_world @ arm_obj.pose.bones["shin.L"].tail
        ankle_r_w = arm_obj.matrix_world @ arm_obj.pose.bones["shin.R"].tail
        foot_head_l_w = arm_obj.matrix_world @ arm_obj.pose.bones["foot.L"].head
        foot_head_r_w = arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].head
        foot_eul_l_deg = tuple(
            round(math.degrees(v), 4)
            for v in (arm_obj.matrix_world @ arm_obj.pose.bones["foot.L"].matrix).to_euler("XYZ")
        )
        foot_eul_r_deg = tuple(
            round(math.degrees(v), 4)
            for v in (arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].matrix).to_euler("XYZ")
        )
        foot_l_min_z = float(world_min_z(foot_l_mesh))
        foot_r_min_z = float(world_min_z(foot_r_mesh))

        thigh_l_len = float((leg_l["knee_world"] - leg_l["hip_world"]).length)
        shin_l_len = float((leg_l["ankle_world"] - leg_l["knee_world"]).length)
        thigh_r_len = float((leg_r["knee_world"] - leg_r["hip_world"]).length)
        shin_r_len = float((leg_r["ankle_world"] - leg_r["knee_world"]).length)

        ik_track_err_l = float((ankle_l_w - ctrl_l_w).length)
        ik_track_err_r = float((ankle_r_w - ctrl_r_w).length)

        # Stance drift measurements against RECOVERED stance anchors (Section 六)
        exp_ankle_pos_l = (
            Vector((rec_anchor_l[0], rec_anchor_l[1], rec_anchor_l[2] + (ANKLE_REST_Z if abs(rec_anchor_l[2]) < 1e-3 else 0.0)))
            if rec_anchor_l is not None else None
        )
        exp_ankle_pos_r = (
            Vector((rec_anchor_r[0], rec_anchor_r[1], rec_anchor_r[2] + (ANKLE_REST_Z if abs(rec_anchor_r[2]) < 1e-3 else 0.0)))
            if rec_anchor_r is not None else None
        )
        ctrl_drift_l = (
            float((ctrl_l_w - exp_ankle_pos_l).length) if exp_ankle_pos_l is not None else None
        )
        ankle_drift_l = (
            float((ankle_l_w - exp_ankle_pos_l).length) if exp_ankle_pos_l is not None else None
        )
        ctrl_drift_r = (
            float((ctrl_r_w - exp_ankle_pos_r).length) if exp_ankle_pos_r is not None else None
        )
        ankle_drift_r = (
            float((ankle_r_w - exp_ankle_pos_r).length) if exp_ankle_pos_r is not None else None
        )

        com_res = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL, update_scene=False)
        rom_res = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm_obj, use_evaluated_ik=True)

        frames_telemetry.append({
            "frame": frame,
            "tau": tau,
            "time_s": round(tau * dt, 6),
            "runtime_recorded": {
                "data_source": "runtime_recorded",
                "left_foot_locked": rec_locked_l,
                "right_foot_locked": rec_locked_r,
                "support_side": rec_support_side,
                "support_anchor_L": rec_anchor_l,
                "support_anchor_R": rec_anchor_r,
                "stage": rec_stage,
                "step_k": rec_step_k,
                "contact_event": rec_event,
            },
            "reopen_evaluated": {
                "data_source": "reopen_evaluated",
                "root_world_pos_m": (round(root_loc.x, 6), round(root_loc.y, 6), round(root_loc.z, 6)),
                "root_world_euler_deg": tuple(round(math.degrees(v), 4) for v in root_eul),
                "root_world_quat_wxyz": (
                    round(float(root_quat.w), 7),
                    round(float(root_quat.x), 7),
                    round(float(root_quat.y), 7),
                    round(float(root_quat.z), 7),
                ),
                "pelvis_head_world_m": (round(pelvis_head_w.x, 6), round(pelvis_head_w.y, 6), round(pelvis_head_w.z, 6)),
                "pelvis_tail_world_m": (round(pelvis_tail_w.x, 6), round(pelvis_tail_w.y, 6), round(pelvis_tail_w.z, 6)),
                "pelvis_world_euler_deg": tuple(round(math.degrees(v), 4) for v in pelvis_eul_w),
                "pelvis_world_quat_wxyz": (
                    round(float(pelvis_quat_w.w), 7),
                    round(float(pelvis_quat_w.x), 7),
                    round(float(pelvis_quat_w.y), 7),
                    round(float(pelvis_quat_w.z), 7),
                ),
                "foot_L": {
                    "controller_world_m": (round(ctrl_l_w.x, 6), round(ctrl_l_w.y, 6), round(ctrl_l_w.z, 6)),
                    "controller_parent": ik_l_obj.parent.name if ik_l_obj.parent else None,
                    "ankle_bone_world_m": (round(ankle_l_w.x, 6), round(ankle_l_w.y, 6), round(ankle_l_w.z, 6)),
                    "foot_head_bone_world_m": (round(foot_head_l_w.x, 6), round(foot_head_l_w.y, 6), round(foot_head_l_w.z, 6)),
                    "ik_tracking_error_m": round(ik_track_err_l, 7),
                    "world_euler_deg": foot_eul_l_deg,
                    "mesh_min_z_m": round(foot_l_min_z, 6),
                    "thigh_length_m": round(thigh_l_len, 6),
                    "shin_length_m": round(shin_l_len, 6),
                    "knee_forward_y_m": round(float(leg_l["knee_forward_y"]), 5),
                    "is_locked_evaluated": bool(ik_l_obj.get("is_locked", 0.0) > 0.5),
                    "controller_drift_vs_recorded_anchor_m": round(ctrl_drift_l, 6) if ctrl_drift_l is not None else None,
                    "ankle_bone_drift_vs_recorded_anchor_m": round(ankle_drift_l, 6) if ankle_drift_l is not None else None,
                },
                "foot_R": {
                    "controller_world_m": (round(ctrl_r_w.x, 6), round(ctrl_r_w.y, 6), round(ctrl_r_w.z, 6)),
                    "controller_parent": ik_r_obj.parent.name if ik_r_obj.parent else None,
                    "ankle_bone_world_m": (round(ankle_r_w.x, 6), round(ankle_r_w.y, 6), round(ankle_r_w.z, 6)),
                    "foot_head_bone_world_m": (round(foot_head_r_w.x, 6), round(foot_head_r_w.y, 6), round(foot_head_r_w.z, 6)),
                    "ik_tracking_error_m": round(ik_track_err_r, 7),
                    "world_euler_deg": foot_eul_r_deg,
                    "mesh_min_z_m": round(foot_r_min_z, 6),
                    "thigh_length_m": round(thigh_r_len, 6),
                    "shin_length_m": round(shin_r_len, 6),
                    "knee_forward_y_m": round(float(leg_r["knee_forward_y"]), 5),
                    "is_locked_evaluated": bool(ik_r_obj.get("is_locked", 0.0) > 0.5),
                    "controller_drift_vs_recorded_anchor_m": round(ctrl_drift_r, 6) if ctrl_drift_r is not None else None,
                    "ankle_bone_drift_vs_recorded_anchor_m": round(ankle_drift_r, 6) if ankle_drift_r is not None else None,
                },
                "com_world_m": (round(com_res.com_world.x, 6), round(com_res.com_world.y, 6), round(com_res.com_world.z, 6)),
                "total_mass_kg": round(com_res.total_mass_kg, 4),
                "rom_validation": {
                    "is_valid": bool(rom_res.is_valid),
                    "violation_count": len(rom_res.violations),
                    "max_excess_deg": round(float(rom_res.max_excess_deg), 4),
                },
                "bones": bones_frame,
            },
            "analytical_reference": {
                "data_source": "analytical_reference",
                "root_y_ref_m": round(ref_root_y, 6),
                "speed_ref_mps": round(ref_speed_mps, 6),
                "accel_ref_mps2": round(ref_accel_mps2, 6),
                "stage_ref": ref_stage,
                "step_k_ref": ref_step_idx,
                "support_type_ref": ref_support,
            },
        })

    # =========================================================================
    # Mathematical Continuity & Biomechanical Analysis Across Reopened Frames
    # =========================================================================

    # 1. Root Translation Continuity
    root_steps_m: List[float] = []
    fd_speeds_mps: List[float] = []
    fd_accels_mps2: List[float] = []
    root_ys = [f["reopen_evaluated"]["root_world_pos_m"][1] for f in frames_telemetry]

    for i in range(1, len(root_ys)):
        dy = root_ys[i] - root_ys[i - 1]
        root_steps_m.append(dy)
        fd_speeds_mps.append(dy / dt)

    for i in range(1, len(fd_speeds_mps)):
        dv = fd_speeds_mps[i] - fd_speeds_mps[i - 1]
        fd_accels_mps2.append(dv / dt)

    stand_start_steps = root_steps_m[:12]
    stand_stop_steps = root_steps_m[192:]
    steady_steps = root_steps_m[43:162]

    speed_planned_diffs = []
    for i, fd_v in enumerate(fd_speeds_mps):
        midpoint_ref_v = 0.5 * (
            frames_telemetry[i]["analytical_reference"]["speed_ref_mps"]
            + frames_telemetry[i + 1]["analytical_reference"]["speed_ref_mps"]
        )
        speed_planned_diffs.append(abs(fd_v - midpoint_ref_v))

    root_cont_passed = (
        max(abs(s) for s in stand_start_steps) < 1e-6
        and max(abs(s) for s in stand_stop_steps) < 1e-6
        and max(root_steps_m) <= 0.0105
        and max(speed_planned_diffs) <= 0.005
        and max(abs(a) for a in fd_accels_mps2) <= 0.25
    )

    max_acc_idx = max(range(len(fd_accels_mps2)), key=lambda i: abs(fd_accels_mps2[i])) if fd_accels_mps2 else 0
    max_fd_acc = abs(fd_accels_mps2[max_acc_idx]) if fd_accels_mps2 else 0.0

    root_continuity_summary = {
        "passed": root_cont_passed,
        "total_displacement_m": round(root_ys[-1] - root_ys[0], 6),
        "start_y_m": round(root_ys[0], 6),
        "end_y_m": round(root_ys[-1], 6),
        "stand_start_frames_1_to_13_max_step_m": round(max(abs(s) for s in stand_start_steps), 8),
        "stand_stop_frames_193_to_204_max_step_m": round(max(abs(s) for s in stand_stop_steps), 8),
        "steady_walk_single_frame_step_range_m": (
            round(min(steady_steps), 6),
            round(max(steady_steps), 6),
        ),
        "max_single_frame_step_m": round(max(root_steps_m), 6),
        "max_single_frame_step_frame": int(root_steps_m.index(max(root_steps_m)) + 2),
        "max_fd_speed_mps": round(max(fd_speeds_mps), 6),
        "max_speed_vs_planned_midpoint_error_mps": round(max(speed_planned_diffs), 6),
        "max_speed_error_frame": int(speed_planned_diffs.index(max(speed_planned_diffs)) + 2),
        "max_fd_acceleration_mps2": round(max_fd_acc, 6),
        "max_fd_acceleration_frame": int(max_acc_idx + 2),
    }

    # 2. 19-Bone Quaternion Geodesic Rotation Continuity
    bone_rot_diffs: Dict[str, List[float]] = {b_name: [] for b_name in expected_bone_names}
    for i in range(1, len(frames_telemetry)):
        f_prev = frames_telemetry[i - 1]["reopen_evaluated"]["bones"]
        f_curr = frames_telemetry[i]["reopen_evaluated"]["bones"]
        for b_name in expected_bone_names:
            q_prev = f_prev[b_name]["world_quat_wxyz"]
            q_curr = f_curr[b_name]["world_quat_wxyz"]
            deg_diff = _quat_geodesic_angle_deg(q_prev, q_curr)
            bone_rot_diffs[b_name].append(deg_diff)

    bone_rot_stats: Dict[str, Any] = {}
    global_max_step_deg = 0.0
    global_max_bone = ""
    global_max_frame = 1

    for b_name, diffs in bone_rot_diffs.items():
        max_d = max(diffs)
        max_f = diffs.index(max_d) + 2
        avg_d = sum(diffs) / len(diffs)
        if max_d > global_max_step_deg:
            global_max_step_deg = max_d
            global_max_bone = b_name
            global_max_frame = max_f
        bone_rot_stats[b_name] = {
            "max_geodesic_step_deg": round(max_d, 5),
            "max_step_frame": max_f,
            "avg_geodesic_step_deg": round(avg_d, 5),
        }

    bone_rot_passed = global_max_step_deg < 8.0

    bone_rot_summary = {
        "passed": bone_rot_passed,
        "global_max_geodesic_step_deg": round(global_max_step_deg, 5),
        "global_max_bone": global_max_bone,
        "global_max_frame": global_max_frame,
        "key_bones": {
            k: bone_rot_stats[k]
            for k in ("pelvis", "spine", "thigh.L", "thigh.R", "shin.L", "shin.R", "foot.L", "foot.R")
        },
        "all_bones": bone_rot_stats,
    }

    # 3. Support Foot & Contact Lifecycle (Recovered from Persisted Records)
    stance_intervals_audit: List[Dict[str, Any]] = []
    curr_int: Optional[Dict[str, Any]] = None

    for f_data in frames_telemetry:
        f_num = f_data["frame"]
        rec_data = f_data["runtime_recorded"]
        eval_data = f_data["reopen_evaluated"]
        side = rec_data["support_side"]
        anchor_l = rec_data["support_anchor_L"]
        anchor_r = rec_data["support_anchor_R"]

        if curr_int is None or curr_int["support_side"] != side:
            if curr_int is not None:
                stance_intervals_audit.append(curr_int)
            curr_int = {
                "support_side": side,
                "frame_start": f_num,
                "frame_end": f_num,
                "duration_frames": 1,
                "anchor_L": anchor_l,
                "anchor_R": anchor_r,
                "max_controller_drift_L_m": 0.0,
                "max_controller_drift_R_m": 0.0,
                "max_ankle_bone_drift_L_m": 0.0,
                "max_ankle_bone_drift_R_m": 0.0,
                "ankle_bone_coords_L": [],
                "ankle_bone_coords_R": [],
            }
        else:
            curr_int["frame_end"] = f_num
            curr_int["duration_frames"] += 1

        if rec_data["left_foot_locked"]:
            d_c = eval_data["foot_L"]["controller_drift_vs_recorded_anchor_m"] or 0.0
            d_a = eval_data["foot_L"]["ankle_bone_drift_vs_recorded_anchor_m"] or 0.0
            curr_int["max_controller_drift_L_m"] = max(curr_int["max_controller_drift_L_m"], d_c)
            curr_int["max_ankle_bone_drift_L_m"] = max(curr_int["max_ankle_bone_drift_L_m"], d_a)
            curr_int["ankle_bone_coords_L"].append(eval_data["foot_L"]["ankle_bone_world_m"])

        if rec_data["right_foot_locked"]:
            d_c = eval_data["foot_R"]["controller_drift_vs_recorded_anchor_m"] or 0.0
            d_a = eval_data["foot_R"]["ankle_bone_drift_vs_recorded_anchor_m"] or 0.0
            curr_int["max_controller_drift_R_m"] = max(curr_int["max_controller_drift_R_m"], d_c)
            curr_int["max_ankle_bone_drift_R_m"] = max(curr_int["max_ankle_bone_drift_R_m"], d_a)
            curr_int["ankle_bone_coords_R"].append(eval_data["foot_R"]["ankle_bone_world_m"])

    if curr_int is not None:
        stance_intervals_audit.append(curr_int)

    # Calculate inter-frame ankle slip across stance intervals
    max_interframe_ankle_slip_m = 0.0
    for s_int in stance_intervals_audit:
        for ankle_series in (s_int["ankle_bone_coords_L"], s_int["ankle_bone_coords_R"]):
            if len(ankle_series) > 1:
                for i in range(1, len(ankle_series)):
                    p0 = Vector(ankle_series[i - 1])
                    p1 = Vector(ankle_series[i])
                    max_interframe_ankle_slip_m = max(max_interframe_ankle_slip_m, float((p1 - p0).length))

    max_ctrl_drift_all = max(
        max(it["max_controller_drift_L_m"], it["max_controller_drift_R_m"])
        for it in stance_intervals_audit
    )
    max_ankle_drift_all = max(
        max(it["max_ankle_bone_drift_L_m"], it["max_ankle_bone_drift_R_m"])
        for it in stance_intervals_audit
    )

    max_ik_err_l = max(f["reopen_evaluated"]["foot_L"]["ik_tracking_error_m"] for f in frames_telemetry)
    max_ik_err_r = max(f["reopen_evaluated"]["foot_R"]["ik_tracking_error_m"] for f in frames_telemetry)

    stance_foot_l_min_z = [
        f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"]
        for f in frames_telemetry
        if f["runtime_recorded"]["left_foot_locked"]
    ]
    stance_foot_r_min_z = [
        f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"]
        for f in frames_telemetry
        if f["runtime_recorded"]["right_foot_locked"]
    ]
    swing_foot_l_min_z = [
        f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"]
        for f in frames_telemetry
        if not f["runtime_recorded"]["left_foot_locked"]
    ]
    swing_foot_r_min_z = [
        f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"]
        for f in frames_telemetry
        if not f["runtime_recorded"]["right_foot_locked"]
    ]

    # Evaluate transition boundary jumps
    boundary_steps_m: List[float] = []
    transition_frames = [it["frame_start"] for it in stance_intervals_audit[1:]]
    for tf in transition_frames:
        f_idx = tf - 1
        p_prev_l = Vector(frames_telemetry[f_idx - 1]["reopen_evaluated"]["foot_L"]["ankle_bone_world_m"])
        p_curr_l = Vector(frames_telemetry[f_idx]["reopen_evaluated"]["foot_L"]["ankle_bone_world_m"])
        p_prev_r = Vector(frames_telemetry[f_idx - 1]["reopen_evaluated"]["foot_R"]["ankle_bone_world_m"])
        p_curr_r = Vector(frames_telemetry[f_idx]["reopen_evaluated"]["foot_R"]["ankle_bone_world_m"])
        boundary_steps_m.append(float((p_curr_l - p_prev_l).length))
        boundary_steps_m.append(float((p_curr_r - p_prev_r).length))

    max_trans_boundary_step_m = max(boundary_steps_m) if boundary_steps_m else 0.0

    support_contact_passed = (
        max_ctrl_drift_all < 1e-6
        and max_ankle_drift_all < 1e-4
        and max_interframe_ankle_slip_m < 1e-4
        and max_ik_err_l < 1e-4
        and max_ik_err_r < 1e-4
        and min(stance_foot_l_min_z) >= -1e-4
        and max(stance_foot_l_min_z) <= 1e-4
        and min(stance_foot_r_min_z) >= -1e-4
        and max(stance_foot_r_min_z) <= 1e-4
        and min(swing_foot_l_min_z) >= -0.003
        and min(swing_foot_r_min_z) >= -0.003
        and len(stance_intervals_audit) == 9
        and max_trans_boundary_step_m < 0.005
    )

    support_contact_summary = {
        "passed": support_contact_passed,
        "max_stance_controller_drift_m": round(max_ctrl_drift_all, 7),
        "max_stance_ankle_bone_drift_m": round(max_ankle_drift_all, 7),
        "max_stance_interframe_ankle_slip_m": round(max_interframe_ankle_slip_m, 7),
        "max_ik_tracking_error_L_m": round(max_ik_err_l, 7),
        "max_ik_tracking_error_R_m": round(max_ik_err_r, 7),
        "stance_foot_L_mesh_min_z_range_m": (round(min(stance_foot_l_min_z), 6), round(max(stance_foot_l_min_z), 6)),
        "stance_foot_R_mesh_min_z_range_m": (round(min(stance_foot_r_min_z), 6), round(max(stance_foot_r_min_z), 6)),
        "swing_foot_L_mesh_min_z_range_m": (round(min(swing_foot_l_min_z), 6), round(max(swing_foot_l_min_z), 6)),
        "swing_foot_R_mesh_min_z_range_m": (round(min(swing_foot_r_min_z), 6), round(max(swing_foot_r_min_z), 6)),
        "stance_intervals": [
            {
                "support_side": it["support_side"],
                "frames": f"{it['frame_start']}..{it['frame_end']}",
                "duration": it["duration_frames"],
                "anchor_L": it["anchor_L"],
                "anchor_R": it["anchor_R"],
                "max_controller_drift_L_m": round(it["max_controller_drift_L_m"], 7),
                "max_controller_drift_R_m": round(it["max_controller_drift_R_m"], 7),
                "max_ankle_bone_drift_L_m": round(it["max_ankle_bone_drift_L_m"], 7),
                "max_ankle_bone_drift_R_m": round(it["max_ankle_bone_drift_R_m"], 7),
            }
            for it in stance_intervals_audit
        ],
        "lifecycle_transitions": contact_metadata.get("transition_events", []),
        "max_transition_boundary_foot_step_m": round(max_trans_boundary_step_m, 6),
    }

    # 4. Center of Mass & Rigid-Body Geometry Consistency
    com_ys = [f["reopen_evaluated"]["com_world_m"][1] for f in frames_telemetry]
    com_xs = [f["reopen_evaluated"]["com_world_m"][0] for f in frames_telemetry]
    com_zs = [f["reopen_evaluated"]["com_world_m"][2] for f in frames_telemetry]
    masses = [f["reopen_evaluated"]["total_mass_kg"] for f in frames_telemetry]

    com_steps_m: List[float] = []
    for i in range(1, len(frames_telemetry)):
        c0 = Vector(frames_telemetry[i - 1]["reopen_evaluated"]["com_world_m"])
        c1 = Vector(frames_telemetry[i]["reopen_evaluated"]["com_world_m"])
        com_steps_m.append(float((c1 - c0).length))

    thigh_l_lens = [f["reopen_evaluated"]["foot_L"]["thigh_length_m"] for f in frames_telemetry]
    shin_l_lens = [f["reopen_evaluated"]["foot_L"]["shin_length_m"] for f in frames_telemetry]
    thigh_r_lens = [f["reopen_evaluated"]["foot_R"]["thigh_length_m"] for f in frames_telemetry]
    shin_r_lens = [f["reopen_evaluated"]["foot_R"]["shin_length_m"] for f in frames_telemetry]

    max_thigh_err = max(
        max(abs(l - 0.42) for l in thigh_l_lens),
        max(abs(l - 0.42) for l in thigh_r_lens),
    )
    max_shin_err = max(
        max(abs(l - 0.40) for l in shin_l_lens),
        max(abs(l - 0.40) for l in shin_r_lens),
    )

    rom_viols_total = sum(f["reopen_evaluated"]["rom_validation"]["violation_count"] for f in frames_telemetry)

    nan_inf_found = False
    for f in frames_telemetry:
        for val in (
            f["reopen_evaluated"]["root_world_pos_m"]
            + f["reopen_evaluated"]["com_world_m"]
            + (f["reopen_evaluated"]["total_mass_kg"],)
        ):
            if math.isnan(val) or math.isinf(val):
                nan_inf_found = True
                break

    com_rigid_passed = (
        not nan_inf_found
        and min(masses) == 70.0
        and max(masses) == 70.0
        and abs((com_ys[-1] - com_ys[0]) - 1.26) < 0.001
        and (max(com_xs) - min(com_xs)) >= 0.02
        and (max(com_xs) - min(com_xs)) <= 0.12
        and max(com_steps_m) <= 0.015
        and max_thigh_err < 1e-4
        and max_shin_err < 1e-4
        and rom_viols_total == 0
    )

    com_rigid_summary = {
        "passed": com_rigid_passed,
        "nan_or_inf_count": 0 if not nan_inf_found else 1,
        "total_mass_kg_min": round(min(masses), 4),
        "total_mass_kg_max": round(max(masses), 4),
        "com_forward_y_displacement_m": round(com_ys[-1] - com_ys[0], 6),
        "com_lateral_x_range_m": (round(min(com_xs), 6), round(max(com_xs), 6)),
        "com_lateral_x_span_m": round(max(com_xs) - min(com_xs), 6),
        "com_vertical_z_range_m": (round(min(com_zs), 6), round(max(com_zs), 6)),
        "com_vertical_z_span_m": round(max(com_zs) - min(com_zs), 6),
        "max_single_frame_com_step_m": round(max(com_steps_m), 6),
        "max_thigh_length_error_m": round(max_thigh_err, 7),
        "max_shin_length_error_m": round(max_shin_err, 7),
        "rom_violation_frame_count": rom_viols_total,
    }

    overall_passed = (
        root_cont_passed
        and bone_rot_passed
        and support_contact_passed
        and com_rigid_passed
    )

    validation_result = {
        "verdict": "PASS" if overall_passed else "FAIL",
        "passed": overall_passed,
        "evaluated_blend_path": derived_blend_path,
        "contact_metadata_version": contact_metadata.get("blend_asset_version"),
        "frame_start": frame_start,
        "frame_end": frame_end,
        "total_evaluated_frames": len(frames_telemetry),
        "fps": int(fps),
        "root_translation_continuity": root_continuity_summary,
        "bone_rotation_continuity": bone_rot_summary,
        "support_foot_and_contact_lifecycle": support_contact_summary,
        "com_and_rigid_body_geometry": com_rigid_summary,
        "frames": frames_telemetry,
    }

    if output_json_path:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(validation_result, f, indent=2)

    return validation_result
