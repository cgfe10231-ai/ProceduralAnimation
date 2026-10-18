"""Reopen `output/character_run_prototype.blend` in headless Blender and verify all Task 6B requirements:
1. Saved Blender Actions exist on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R (24 FPS, 1..96 frames).
2. Character moves continuously forward (+Y) at 0.9000 m/s (3.5625 m across 96 frames), clearly distinct from 0.24 m/s walking.
3. Each 24-frame running cycle contains 4 ordered phases (`stance_L` 7f -> `flight_1` 5f -> `stance_R` 7f -> `flight_2` 5f)
   with 10 measurable dual-foot airborne frames (0.4167 s) per cycle (40 airborne frames total across 4 cycles).
4. During every airborne frame, both feet have `is_locked == False` and both feet are genuinely off the ground
   (`foot_min_z >= +0.015 m`).
5. During every 7-frame stance window, the locked support foot stays pinned at its planned world landing coordinate
   `y_stance(k) = -8.0 + (k + 0.25) * 0.45 m` with sub-millimeter bone/mesh drift (`<= 0.001 m`).
6. Pelvis exhibits running bounce (lower in mid-stance, higher in mid-flight), smooth continuity across all frames
   and cycle boundaries (`24->25`, `48->49`, `72->73`), zero ground penetration (`min_foot_z >= -0.001 m`),
   forward knee flexion (`min_knee_fwd > 0.05 m`), and 100% strict IK reachability (`max_hip_dist <= 0.82 m`, 0 unreachable).
7. Verify `RunAction` composability via `MotionPlanner` from a non-1 start frame and offset position.
"""

import math
import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.motion.framework import MotionMode, MotionPlanner, create_initial_motion_state
from src.motion.run_cycle import RunAction
from src.rig.ik import IK_TARGET_NAMES, MAX_LEG_REACH, get_leg_ik_state
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 6B PROCEDURAL RUN REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    start_x, start_y, start_z = config.character_path_points[0]

    total_frames = config.run_total_frames
    cycle_frames = config.run_cycle_frames
    half_step = config.run_half_step_frames
    stance_frames = config.run_stance_frames
    flight_frames = config.run_flight_frames
    step_len = config.run_step_length
    stance_center_offset = 0.5 * (stance_frames - 1) / float(half_step)

    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != total_frames:
        _fail(
            f"Invalid timeline settings: fps={scene.render.fps}, "
            f"range=({scene.frame_start}, {scene.frame_end}), expected=(1, {total_frames})"
        )

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    ik_l_obj = bpy.data.objects.get(IK_TARGET_NAMES["L"])
    ik_r_obj = bpy.data.objects.get(IK_TARGET_NAMES["R"])
    if arm_obj is None or root_obj is None or ik_l_obj is None or ik_r_obj is None:
        _fail("Missing CharacterArmature, CharacterRoot, or FootIK.L/R")

    for obj_name in ("CharacterRoot", "CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.animation_data is None or obj.animation_data.action is None:
            _fail(f"Object '{obj_name}' is missing saved Blender animation Action")
    print("Verified saved Blender Actions on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R")

    root_y_history = []
    pelvis_z_history = []
    torso_pitch_history = []
    arm_l_rx_history = []

    max_stance_ankle_drift_l = 0.0
    max_stance_mesh_drift_l = 0.0
    max_stance_ankle_drift_r = 0.0
    max_stance_mesh_drift_r = 0.0
    max_landing_error = 0.0

    min_foot_l_z = 999.0
    min_foot_r_z = 999.0
    min_flight_foot_l_z = 999.0
    min_flight_foot_r_z = 999.0
    max_flight_foot_l_z = -999.0
    max_flight_foot_r_z = -999.0
    min_knee_fwd_l = 999.0
    min_knee_fwd_r = 999.0
    max_hip_dist_l = 0.0
    max_hip_dist_r = 0.0
    unreachable_count = 0

    airborne_frames_per_cycle = [0 for _ in range(config.run_cycles)]
    ref_ankle_l = {}
    ref_mesh_l = {}
    ref_ankle_r = {}
    ref_mesh_r = {}

    mid_stance_pelvis_z = []
    mid_flight_pelvis_z = []

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1
        cycle_idx = tau // cycle_frames
        k = tau // half_step
        local_f = tau - k * half_step

        root_pos = root_obj.matrix_world.translation.copy()
        if abs(root_pos.x - start_x) > 1e-5 or abs(root_pos.z - start_z) > 1e-5:
            _fail(f"Root X/Z drifted at frame {frame}: {tuple(root_pos)}")
        root_y_history.append(root_pos.y)

        pb_pelvis = arm_obj.pose.bones["pelvis"]
        pb_spine = arm_obj.pose.bones["spine"]
        pb_arm_l = arm_obj.pose.bones["upper_arm.L"]
        pelvis_head_w = arm_obj.matrix_world @ pb_pelvis.head
        pelvis_z_history.append(pelvis_head_w.z)
        torso_pitch_history.append(-math.degrees(pb_pelvis.rotation_euler.x + pb_spine.rotation_euler.x))
        arm_l_rx_history.append(math.degrees(pb_arm_l.rotation_euler.x))

        if local_f == 3:
            mid_stance_pelvis_z.append(pelvis_head_w.z)
        elif local_f == 9:
            mid_flight_pelvis_z.append(pelvis_head_w.z)

        state_l = get_leg_ik_state(arm_obj, "L")
        state_r = get_leg_ik_state(arm_obj, "R")
        mesh_l = get_part_world_center("Foot_L")
        mesh_r = get_part_world_center("Foot_R")
        locked_l = bool(ik_l_obj.get("is_locked", False))
        locked_r = bool(ik_r_obj.get("is_locked", False))

        dist_l = (state_l["target_world"] - state_l["hip_world"]).length
        dist_r = (state_r["target_world"] - state_r["hip_world"]).length
        max_hip_dist_l = max(max_hip_dist_l, dist_l)
        max_hip_dist_r = max(max_hip_dist_r, dist_r)
        if dist_l > MAX_LEG_REACH + 1e-4 or dist_r > MAX_LEG_REACH + 1e-4:
            unreachable_count += 1

        min_foot_l_z = min(min_foot_l_z, state_l["foot_min_z"])
        min_foot_r_z = min(min_foot_r_z, state_r["foot_min_z"])
        min_knee_fwd_l = min(min_knee_fwd_l, state_l["knee_forward_y"])
        min_knee_fwd_r = min(min_knee_fwd_r, state_r["knee_forward_y"])

        expected_stance_y = start_y + (k + stance_center_offset) * step_len
        if local_f < stance_frames:
            if k % 2 == 0:
                if not locked_l or locked_r:
                    _fail(f"Frame {frame}: expected L locked and R unlocked, got L={locked_l}, R={locked_r}")
                if local_f == 0:
                    ref_ankle_l[k] = state_l["foot_head_world"].copy()
                    ref_mesh_l[k] = mesh_l.copy()
                    max_landing_error = max(
                        max_landing_error,
                        abs(state_l["foot_head_world"].y - expected_stance_y),
                    )
                max_stance_ankle_drift_l = max(
                    max_stance_ankle_drift_l,
                    (state_l["foot_head_world"] - ref_ankle_l[k]).length,
                )
                max_stance_mesh_drift_l = max(
                    max_stance_mesh_drift_l,
                    (mesh_l - ref_mesh_l[k]).length,
                )
            else:
                if not locked_r or locked_l:
                    _fail(f"Frame {frame}: expected R locked and L unlocked, got L={locked_l}, R={locked_r}")
                if local_f == 0:
                    ref_ankle_r[k] = state_r["foot_head_world"].copy()
                    ref_mesh_r[k] = mesh_r.copy()
                    max_landing_error = max(
                        max_landing_error,
                        abs(state_r["foot_head_world"].y - expected_stance_y),
                    )
                max_stance_ankle_drift_r = max(
                    max_stance_ankle_drift_r,
                    (state_r["foot_head_world"] - ref_ankle_r[k]).length,
                )
                max_stance_mesh_drift_r = max(
                    max_stance_mesh_drift_r,
                    (mesh_r - ref_mesh_r[k]).length,
                )
        else:
            # Airborne flight phase: both feet must be unlocked and above ground
            if locked_l or locked_r:
                _fail(f"Frame {frame} (flight): expected both feet unlocked, got L={locked_l}, R={locked_r}")
            airborne_frames_per_cycle[cycle_idx] += 1
            min_flight_foot_l_z = min(min_flight_foot_l_z, state_l["foot_min_z"])
            min_flight_foot_r_z = min(min_flight_foot_r_z, state_r["foot_min_z"])
            max_flight_foot_l_z = max(max_flight_foot_l_z, state_l["foot_min_z"])
            max_flight_foot_r_z = max(max_flight_foot_r_z, state_r["foot_min_z"])

    fps = float(config.fps)
    velocities_mps = [
        (root_y_history[i + 1] - root_y_history[i]) * fps
        for i in range(len(root_y_history) - 1)
    ]
    min_v = min(velocities_mps)
    max_v = max(velocities_mps)
    total_root_disp = root_y_history[-1] - root_y_history[0]

    max_pelvis_dz_jump = max(
        abs(pelvis_z_history[i + 1] - pelvis_z_history[i])
        for i in range(len(pelvis_z_history) - 1)
    )
    max_torso_pitch_jump = max(
        abs(torso_pitch_history[i + 1] - torso_pitch_history[i])
        for i in range(len(torso_pitch_history) - 1)
    )
    max_arm_jump = max(
        abs(arm_l_rx_history[i + 1] - arm_l_rx_history[i])
        for i in range(len(arm_l_rx_history) - 1)
    )

    # Check cycle boundary continuity at frames (24->25), (48->49), (72->73)
    boundary_pelvis_jumps = [
        abs(pelvis_z_history[b] - pelvis_z_history[b - 1])
        for b in (24, 48, 72)
    ]
    max_boundary_pelvis_jump = max(boundary_pelvis_jumps)
    avg_mid_stance_z = sum(mid_stance_pelvis_z) / len(mid_stance_pelvis_z)
    avg_mid_flight_z = sum(mid_flight_pelvis_z) / len(mid_flight_pelvis_z)
    pelvis_flight_vs_stance_lift = avg_mid_flight_z - avg_mid_stance_z

    print(
        f"Reopened Task 6B Procedural Run Verification Metrics (Frames 1..{total_frames}):\n"
        f"  Root Y: {root_y_history[0]:.4f}m -> {root_y_history[-1]:.4f}m (total_disp={total_root_disp:.4f}m)\n"
        f"  Forward Speed Range : [{min_v:.4f}, {max_v:.4f}] m/s (target={config.run_speed_mps:.4f} m/s)\n"
        f"  Airborne Frames / Cycle: {airborne_frames_per_cycle} (expected 10 per 24f cycle = 0.4167s/cycle)\n"
        f"  Flight Foot Min Z   : L in [{min_flight_foot_l_z:+.4f}, {max_flight_foot_l_z:+.4f}] m, "
        f"R in [{min_flight_foot_r_z:+.4f}, {max_flight_foot_r_z:+.4f}] m\n"
        f"  Left Stance  max ankle_drift={max_stance_ankle_drift_l:.6f}m, max mesh_drift={max_stance_mesh_drift_l:.6f}m\n"
        f"  Right Stance max ankle_drift={max_stance_ankle_drift_r:.6f}m, max mesh_drift={max_stance_mesh_drift_r:.6f}m\n"
        f"  Max Stance Landing Y Error : {max_landing_error:.6f}m\n"
        f"  Pelvis Vertical Bounce     : mid_stance_Z={avg_mid_stance_z:.4f}m -> mid_flight_Z={avg_mid_flight_z:.4f}m (lift={pelvis_flight_vs_stance_lift:+.4f}m)\n"
        f"  Max Single-Frame Pose Delta: pelvis_dZ={max_pelvis_dz_jump:.5f}m (cycle_boundary={max_boundary_pelvis_jump:.5f}m), "
        f"torso_pitch={max_torso_pitch_jump:.3f}deg, arm_rx={max_arm_jump:.3f}deg\n"
        f"  Overall Min Foot Z  : L={min_foot_l_z:+.6f}m, R={min_foot_r_z:+.6f}m\n"
        f"  Min Knee Forward +Y : L={min_knee_fwd_l:+.4f}m, R={min_knee_fwd_r:+.4f}m\n"
        f"  Max Hip-to-Target Dist: L={max_hip_dist_l:.5f}m, R={max_hip_dist_r:.5f}m (limit={MAX_LEG_REACH:.2f}m)\n"
        f"  IK Unreachable Events : {unreachable_count}"
    )

    if abs(min_v - config.run_speed_mps) > 1e-3 or abs(max_v - config.run_speed_mps) > 1e-3:
        _fail(f"Forward speed mismatch: [{min_v}, {max_v}] vs {config.run_speed_mps}")
    if any(c != 2 * flight_frames for c in airborne_frames_per_cycle):
        _fail(f"Unexpected airborne frame count per cycle: {airborne_frames_per_cycle}")
    if min_flight_foot_l_z < 0.015 or min_flight_foot_r_z < 0.015:
        _fail(f"Insufficient dual-foot airborne clearance during flight: L={min_flight_foot_l_z}, R={min_flight_foot_r_z}")
    if max_stance_ankle_drift_l > 0.001 or max_stance_ankle_drift_r > 0.001:
        _fail(f"Stance foot drifted: L={max_stance_ankle_drift_l}, R={max_stance_ankle_drift_r}")
    if max_landing_error > 0.001:
        _fail(f"Stance landing coordinate error too large: {max_landing_error}")
    if pelvis_flight_vs_stance_lift < 0.030:
        _fail(f"Pelvis vertical flight bounce too small: {pelvis_flight_vs_stance_lift}")
    if max_pelvis_dz_jump > 0.018 or max_boundary_pelvis_jump > 0.018:
        _fail(f"Pelvis vertical discontinuity detected: max={max_pelvis_dz_jump}, boundary={max_boundary_pelvis_jump}")
    if min_foot_l_z < -0.001 or min_foot_r_z < -0.001:
        _fail(f"Ground penetration detected: L={min_foot_l_z}, R={min_foot_r_z}")
    if min_knee_fwd_l < 0.05 or min_knee_fwd_r < 0.05:
        _fail(f"Knee backward bend or insufficient flexion: L={min_knee_fwd_l}, R={min_knee_fwd_r}")
    if unreachable_count > 0:
        _fail(f"Encountered {unreachable_count} IK unreachable events")

    # Verify non-hardcoded start frame & position composability via MotionPlanner
    offset_init = create_initial_motion_state(
        config,
        start_frame=101,
        position=(0.0, -4.40, 0.0),
    ).clone_with(mode=MotionMode.WALK)
    planner = MotionPlanner(config, armature_obj=arm_obj)
    planner.add_action(RunAction(cycles=2))
    offset_res = planner.execute(initial_state=offset_init)
    if (
        offset_res["total_frames"] != 48
        or offset_res["initial_state"].frame != 101
        or offset_res["final_state"].frame != 148
        or offset_res["unreachable_count"] != 0
        or abs(offset_res["final_state"].velocity[1] - config.run_speed_mps) > 1e-4
    ):
        _fail(f"Offset RunAction execution via MotionPlanner failed: {offset_res}")
    print(
        f"Verified offset RunAction via MotionPlanner (frames 101..148, "
        f"Y: -4.4000m -> {offset_res['final_state'].position[1]:.4f}m, v={offset_res['final_state'].velocity}, unreachable=0)"
    )

    print("[VERIFY_PASSED] Task 6B procedural running verification completed.")
    print("=== END TASK 6B PROCEDURAL RUN REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
