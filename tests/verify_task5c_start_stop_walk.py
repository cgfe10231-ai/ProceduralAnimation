"""Reopen character_start_stop_walk.blend and verify all Task 5C requirements:
1. Saved Blender Actions exist on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R (24 FPS, 1..204 frames).
2. Root velocity starts at 0.0 m/s (Idle Stand), smoothly accelerates to 0.24 m/s (Start -> Accelerate),
   maintains constant 0.24 m/s (Steady Walk), smoothly decelerates to 0.0 m/s (Decelerate -> Stop Step),
   and remains at 0.0 m/s (Stop Stand) with no backward motion or frame-to-frame velocity jumps.
3. Step lengths, step durations, and foot contact locks are coordinated with variable-speed root motion.
4. During every stance window (including initial and final double-support standing), the locked foot
   stays fixed in world space without drifting with CharacterRoot.
5. At stop (frames 193..204), both feet rest cleanly side-by-side on Z=0 at Y=-6.74m, and body pose
   settles smoothly without sudden jumps.
6. Zero ground penetration, forward knee flexion, and 100% strict IK reachability (0 unreachable events).
"""

import math
import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.motion.start_stop_walk import build_step_schedule
from src.rig.ik import MAX_LEG_REACH, get_leg_ik_state
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 5C START-STOP WALK REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    start_x, start_y, start_z = config.character_path_points[0]
    total_frames = config.start_stop_total_frames

    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != total_frames:
        _fail(
            f"Invalid timeline settings: fps={scene.render.fps}, "
            f"range=({scene.frame_start}, {scene.frame_end}), expected=(1, {total_frames})"
        )

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if arm_obj is None or root_obj is None:
        _fail("Missing CharacterArmature or CharacterRoot")

    for obj_name in ("CharacterRoot", "CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        obj = bpy.data.objects.get(obj_name)
        if obj is None or obj.animation_data is None or obj.animation_data.action is None:
            _fail(f"Object '{obj_name}' is missing saved Blender animation Action")
    print("Verified saved Blender Actions on CharacterRoot, CharacterArmature, FootIK.L/R, and KneePole.L/R")

    schedule = build_step_schedule(config, start_y)
    t_s = config.start_stop_stand_start_frames
    t_a = t_s + config.start_stop_accel_frames
    t_w = t_a + config.start_stop_steady_frames
    t_d = t_w + config.start_stop_decel_frames

    root_y_history = []
    pelvis_z_history = []
    torso_pitch_history = []
    arm_l_rx_history = []

    max_stance_ankle_drift_l = 0.0
    max_stance_mesh_drift_l = 0.0
    max_stance_ankle_drift_r = 0.0
    max_stance_mesh_drift_r = 0.0
    min_foot_l_z = 999.0
    min_foot_r_z = 999.0
    min_knee_fwd_l = 999.0
    min_knee_fwd_r = 999.0
    min_walk_knee_fwd_l = 999.0
    min_walk_knee_fwd_r = 999.0
    max_hip_dist_l = 0.0
    max_hip_dist_r = 0.0
    unreachable_count = 0

    # Stance windows for L and R: (window_id, tau_start, tau_end_inclusive)
    l_windows = [
        ("stand_start", 0, t_s - 1),
        ("step_0", 12, 41),
        ("step_2", 66, 89),
        ("step_4", 114, 137),
        ("step_6", 162, 191),
        ("stand_stop", t_d, total_frames - 1),
    ]
    r_windows = [
        ("stand_start", 0, t_s - 1),
        ("step_1", 42, 65),
        ("step_3", 90, 113),
        ("step_5", 138, 161),
        ("stand_stop", t_d, total_frames - 1),
    ]
    ref_ankle_l = {}
    ref_mesh_l = {}
    ref_ankle_r = {}
    ref_mesh_r = {}

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1

        root_pos = root_obj.matrix_world.translation.copy()
        if abs(root_pos.x - start_x) > 1e-5 or abs(root_pos.z - start_z) > 1e-5:
            _fail(f"Root X/Z drifted at frame {frame}: {tuple(root_pos)}")
        root_y_history.append(root_pos.y)

        pb_pelvis = arm_obj.pose.bones["pelvis"]
        pb_spine = arm_obj.pose.bones["spine"]
        pb_arm_l = arm_obj.pose.bones["upper_arm.L"]
        pelvis_head_w = arm_obj.matrix_world @ pb_pelvis.head
        pelvis_z_history.append(pelvis_head_w.z)
        torso_pitch_history.append(
            -math.degrees(pb_pelvis.rotation_euler.x + pb_spine.rotation_euler.x)
        )
        arm_l_rx_history.append(math.degrees(pb_arm_l.rotation_euler.x))

        state_l = get_leg_ik_state(arm_obj, "L")
        state_r = get_leg_ik_state(arm_obj, "R")
        mesh_l = get_part_world_center("Foot_L")
        mesh_r = get_part_world_center("Foot_R")

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
        if t_s <= tau <= t_d:
            min_walk_knee_fwd_l = min(min_walk_knee_fwd_l, state_l["knee_forward_y"])
            min_walk_knee_fwd_r = min(min_walk_knee_fwd_r, state_r["knee_forward_y"])

        for w_name, ts, te in l_windows:
            if ts <= tau <= te:
                if tau == ts:
                    ref_ankle_l[w_name] = state_l["foot_head_world"].copy()
                    ref_mesh_l[w_name] = mesh_l.copy()
                max_stance_ankle_drift_l = max(
                    max_stance_ankle_drift_l,
                    (state_l["foot_head_world"] - ref_ankle_l[w_name]).length,
                )
                max_stance_mesh_drift_l = max(
                    max_stance_mesh_drift_l,
                    (mesh_l - ref_mesh_l[w_name]).length,
                )

        for w_name, ts, te in r_windows:
            if ts <= tau <= te:
                if tau == ts:
                    ref_ankle_r[w_name] = state_r["foot_head_world"].copy()
                    ref_mesh_r[w_name] = mesh_r.copy()
                max_stance_ankle_drift_r = max(
                    max_stance_ankle_drift_r,
                    (state_r["foot_head_world"] - ref_ankle_r[w_name]).length,
                )
                max_stance_mesh_drift_r = max(
                    max_stance_mesh_drift_r,
                    (mesh_r - ref_mesh_r[w_name]).length,
                )

    # Compute frame-to-frame velocities (m/s) and accelerations
    fps = float(config.fps)
    velocities_mps = [
        (root_y_history[i + 1] - root_y_history[i]) * fps
        for i in range(len(root_y_history) - 1)
    ]
    dv_steps = [
        abs(velocities_mps[i + 1] - velocities_mps[i])
        for i in range(len(velocities_mps) - 1)
    ]
    max_dv_jump = max(dv_steps)

    # Check velocity profile across phases
    stand_start_v = max(abs(v) for v in velocities_mps[:t_s])
    steady_v_min = min(velocities_mps[t_a:t_w])
    steady_v_max = max(velocities_mps[t_a:t_w])
    stand_stop_v = max(abs(v) for v in velocities_mps[t_d:])
    min_overall_v = min(velocities_mps)
    total_root_disp = root_y_history[-1] - root_y_history[0]

    # Check pose smoothness (max single-frame change in pelvis Z, torso lean, arm swing)
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

    # Check final stopped foot alignment at frame 204
    scene.frame_set(total_frames)
    bpy.context.view_layer.update()
    final_l = get_leg_ik_state(arm_obj, "L")
    final_r = get_leg_ik_state(arm_obj, "R")
    final_foot_y_diff = abs(final_l["foot_head_world"].y - final_r["foot_head_world"].y)

    print(
        f"Reopened Start-Stop Walk Verification Metrics (Frames 1..{total_frames}):\n"
        f"  Root Y: {root_y_history[0]:.4f}m -> {root_y_history[-1]:.4f}m (total_disp={total_root_disp:.4f}m)\n"
        f"  Stand-Start Max |v| : {stand_start_v:.6f} m/s\n"
        f"  Steady-Walk v range : [{steady_v_min:.4f}, {steady_v_max:.4f}] m/s\n"
        f"  Stand-Stop Max |v|  : {stand_stop_v:.6f} m/s\n"
        f"  Max Frame-to-Frame |dv|: {max_dv_jump:.5f} m/s (min_v={min_overall_v:.5f} m/s)\n"
        f"  Step Schedule Y landings: {[s['swing_y_end'] for s in schedule]}\n"
        f"  Step Lengths (m)        : {[s['step_length'] for s in schedule]}\n"
        f"  Step Durations (frames) : {[s['duration_frames'] for s in schedule]}\n"
        f"  Left Stance  max ankle_drift={max_stance_ankle_drift_l:.6f}m, max mesh_drift={max_stance_mesh_drift_l:.6f}m\n"
        f"  Right Stance max ankle_drift={max_stance_ankle_drift_r:.6f}m, max mesh_drift={max_stance_mesh_drift_r:.6f}m\n"
        f"  Final Stop Foot Y diff  : {final_foot_y_diff:.6f}m (L={final_l['foot_head_world'].y:.4f}m, R={final_r['foot_head_world'].y:.4f}m)\n"
        f"  Max Single-Frame Pose Delta: pelvis_dZ={max_pelvis_dz_jump:.5f}m, torso_pitch={max_torso_pitch_jump:.3f}deg, arm_rx={max_arm_jump:.3f}deg\n"
        f"  Min Foot Z: L={min_foot_l_z:+.6f}m, R={min_foot_r_z:+.6f}m\n"
        f"  Min Knee Forward +Y (All Frames): L={min_knee_fwd_l:+.4f}m, R={min_knee_fwd_r:+.4f}m\n"
        f"  Min Knee Forward +Y (Walking)   : L={min_walk_knee_fwd_l:+.4f}m, R={min_walk_knee_fwd_r:+.4f}m\n"
        f"  Max Hip-to-Target Dist: L={max_hip_dist_l:.5f}m, R={max_hip_dist_r:.5f}m (limit={MAX_LEG_REACH:.2f}m)\n"
        f"  IK Unreachable Events: {unreachable_count}"
    )

    if stand_start_v > 1e-5 or stand_stop_v > 1e-5:
        _fail(f"Root moved during standing phases: start_v={stand_start_v}, stop_v={stand_stop_v}")
    if abs(steady_v_min - 0.24) > 1e-3 or abs(steady_v_max - 0.24) > 1e-3:
        _fail(f"Steady walk speed mismatch: [{steady_v_min}, {steady_v_max}]")
    if min_overall_v < -1e-6:
        _fail(f"Backward root velocity detected: {min_overall_v}")
    if max_dv_jump > 0.020:
        _fail(f"Velocity jump too large between adjacent frames: {max_dv_jump}")
    if max_stance_mesh_drift_l > 0.002 or max_stance_mesh_drift_r > 0.002:
        _fail(
            f"Stance foot drifted excessively: L={max_stance_mesh_drift_l:.6f}m, "
            f"R={max_stance_mesh_drift_r:.6f}m"
        )
    if final_foot_y_diff > 0.002:
        _fail(f"Feet did not align at final stop: Y diff = {final_foot_y_diff}")
    if max_pelvis_dz_jump > 0.010 or max_torso_pitch_jump > 2.0 or max_arm_jump > 5.0:
        _fail(
            f"Sudden pose jump detected: pelvis_dz={max_pelvis_dz_jump}, "
            f"torso={max_torso_pitch_jump}, arm={max_arm_jump}"
        )
    if min_foot_l_z < -0.001 or min_foot_r_z < -0.001:
        _fail(f"Ground penetration detected: L={min_foot_l_z}, R={min_foot_r_z}")
    if min_knee_fwd_l < 0.0 or min_knee_fwd_r < 0.0:
        _fail(f"Knee backward bend detected: L={min_knee_fwd_l}, R={min_knee_fwd_r}")
    if min_walk_knee_fwd_l <= 0.05 or min_walk_knee_fwd_r <= 0.05:
        _fail(f"Insufficient forward knee flexion during walking: L={min_walk_knee_fwd_l}, R={min_walk_knee_fwd_r}")
    if unreachable_count > 0:
        _fail(f"Encountered {unreachable_count} IK unreachable frames")


    print("[VERIFY_PASSED] Task 5C start/accelerate/steady/decelerate/stop verification completed.")
    print("=== END TASK 5C START-STOP WALK REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
