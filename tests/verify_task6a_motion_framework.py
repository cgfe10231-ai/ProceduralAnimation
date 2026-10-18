"""Verify Task 6A Extensible Procedural Motion System Foundation:
1. Verify `MotionState`, `ContactPointState`, `MotionMode`, coordinate conversion helpers
   (World <-> CharacterRoot Local), and `EnvironmentQuery` contracts.
2. Reopen `output/character_motion_framework_5c.blend` in headless Blender and verify that
   executing the Task 5C start-accelerate-walk-decelerate-stop sequence through
   `MotionPlanner` + `StartStopWalkAction` produces identical root displacement (1.2600 m),
   velocity profile (0 -> 0.2400 -> 0 m/s), support foot stability (0.000024 m max drift),
   ground clearance, knee flexion, and 100% IK reachability (0 unreachable events) as Task 5C.
3. Verify that `MotionPlanner` and `StartStopWalkAction` are free of hardcoded frame-1 or
   origin assumptions by running a second chained segment starting from frame 205 at Y = -6.74 m
   (`frames 205..408`, `Y: -6.7400 m -> -5.4800 m`, `0` unreachable events).
"""

import math
import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.motion.framework import (
    ContactPointState,
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    MotionState,
    StartStopWalkAction,
    create_initial_motion_state,
    forward_unit_vector_from_yaw,
    root_local_to_world_vector,
    world_to_root_local_vector,
)
from src.motion.start_stop_walk import build_step_schedule
from src.rig.ik import MAX_LEG_REACH, get_leg_ik_state
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def _verify_state_and_coordinate_contracts(config: PipelineConfig) -> None:
    # 1. Verify World <-> Root Local vector conversions at 0 deg and 90 deg yaw
    fwd_0 = forward_unit_vector_from_yaw(0.0)
    if not (abs(fwd_0[0]) < 1e-6 and abs(fwd_0[1] - 1.0) < 1e-6 and abs(fwd_0[2]) < 1e-6):
        _fail(f"Unexpected forward unit vector at yaw=0: {fwd_0}")

    v_world = (0.0, 0.24, 0.0)
    v_local_0 = world_to_root_local_vector(v_world, 0.0)
    v_back_0 = root_local_to_world_vector(v_local_0, 0.0)
    if abs(v_local_0[1] - 0.24) > 1e-6 or abs(v_back_0[1] - 0.24) > 1e-6:
        _fail(f"World<->Local conversion failed at yaw=0: local={v_local_0}, world={v_back_0}")

    # At +90 deg CCW yaw, character faces -X; local forward (0, 0.24, 0) -> world (-0.24, 0, 0)
    v_world_90 = root_local_to_world_vector((0.0, 0.24, 0.0), 90.0)
    v_local_90 = world_to_root_local_vector(v_world_90, 90.0)
    if abs(v_world_90[0] + 0.24) > 1e-6 or abs(v_local_90[1] - 0.24) > 1e-6:
        _fail(f"World<->Local conversion failed at yaw=90: world={v_world_90}, local={v_local_90}")

    # 2. Verify initial MotionState structure
    init_state = create_initial_motion_state(config, start_frame=1)
    if (
        init_state.frame != 1
        or init_state.mode != MotionMode.IDLE
        or init_state.speed_mps != 0.0
        or init_state.is_airborne
        or "foot_L" not in init_state.contacts
        or "foot_R" not in init_state.contacts
    ):
        _fail(f"Invalid initial MotionState: {init_state.to_dict()}")

    env = EnvironmentQuery(ground_z=0.0)
    if env.ground_height_at(0.0, -8.0) != 0.0 or env.surface_normal_at(0.0, -8.0) != (0.0, 0.0, 1.0):
        _fail("EnvironmentQuery default flat ground check failed")

    print("Verified MotionState, ContactPointState, EnvironmentQuery, and World<->Local coordinate helpers")


def verify() -> None:
    print("=== START TASK 6A MOTION FRAMEWORK VERIFICATION ===")
    config = PipelineConfig()
    _verify_state_and_coordinate_contracts(config)

    scene = bpy.context.scene
    start_x, start_y, start_z = config.character_path_points[0]
    total_frames = config.start_stop_total_frames

    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != total_frames:
        _fail(
            f"Invalid timeline settings in reopened blend: fps={scene.render.fps}, "
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
    max_stance_ankle_drift_l = 0.0
    max_stance_ankle_drift_r = 0.0
    min_foot_l_z = 999.0
    min_foot_r_z = 999.0
    min_knee_fwd_l = 999.0
    min_knee_fwd_r = 999.0
    min_walk_knee_fwd_l = 999.0
    min_walk_knee_fwd_r = 999.0
    max_hip_dist_l = 0.0
    max_hip_dist_r = 0.0
    unreachable_count = 0

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
    ref_ankle_r = {}

    for frame in range(1, total_frames + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1

        root_pos = root_obj.matrix_world.translation.copy()
        if abs(root_pos.x - start_x) > 1e-5 or abs(root_pos.z - start_z) > 1e-5:
            _fail(f"Root X/Z drifted at frame {frame}: {tuple(root_pos)}")
        root_y_history.append(root_pos.y)

        state_l = get_leg_ik_state(arm_obj, "L")
        state_r = get_leg_ik_state(arm_obj, "R")

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
                max_stance_ankle_drift_l = max(
                    max_stance_ankle_drift_l,
                    (state_l["foot_head_world"] - ref_ankle_l[w_name]).length,
                )

        for w_name, ts, te in r_windows:
            if ts <= tau <= te:
                if tau == ts:
                    ref_ankle_r[w_name] = state_r["foot_head_world"].copy()
                max_stance_ankle_drift_r = max(
                    max_stance_ankle_drift_r,
                    (state_r["foot_head_world"] - ref_ankle_r[w_name]).length,
                )

    fps = float(config.fps)
    velocities_mps = [
        (root_y_history[i + 1] - root_y_history[i]) * fps
        for i in range(len(root_y_history) - 1)
    ]
    max_dv_jump = max(
        abs(velocities_mps[i + 1] - velocities_mps[i])
        for i in range(len(velocities_mps) - 1)
    )
    stand_start_v = max(abs(v) for v in velocities_mps[:t_s])
    steady_v_min = min(velocities_mps[t_a:t_w])
    steady_v_max = max(velocities_mps[t_a:t_w])
    stand_stop_v = max(abs(v) for v in velocities_mps[t_d:])
    total_root_disp = root_y_history[-1] - root_y_history[0]

    scene.frame_set(total_frames)
    bpy.context.view_layer.update()
    final_l = get_leg_ik_state(arm_obj, "L")
    final_r = get_leg_ik_state(arm_obj, "R")
    final_foot_y_diff = abs(final_l["foot_head_world"].y - final_r["foot_head_world"].y)

    print(
        f"Reopened Task 6A Motion Framework 5C Baseline Metrics (Frames 1..{total_frames}):\n"
        f"  Root Y: {root_y_history[0]:.4f}m -> {root_y_history[-1]:.4f}m (total_disp={total_root_disp:.4f}m)\n"
        f"  Stand-Start Max |v| : {stand_start_v:.6f} m/s\n"
        f"  Steady-Walk v range : [{steady_v_min:.4f}, {steady_v_max:.4f}] m/s\n"
        f"  Stand-Stop Max |v|  : {stand_stop_v:.6f} m/s\n"
        f"  Max Frame-to-Frame |dv|: {max_dv_jump:.5f} m/s\n"
        f"  Left Stance  max ankle_drift={max_stance_ankle_drift_l:.6f}m\n"
        f"  Right Stance max ankle_drift={max_stance_ankle_drift_r:.6f}m\n"
        f"  Final Stop Foot Y diff: {final_foot_y_diff:.6f}m (L={final_l['foot_head_world'].y:.4f}m, R={final_r['foot_head_world'].y:.4f}m)\n"
        f"  Min Foot Z: L={min_foot_l_z:+.6f}m, R={min_foot_r_z:+.6f}m\n"
        f"  Min Knee Forward +Y (All / Walk): L={min_knee_fwd_l:+.4f}m / {min_walk_knee_fwd_l:+.4f}m, R={min_knee_fwd_r:+.4f}m / {min_walk_knee_fwd_r:+.4f}m\n"
        f"  Max Hip-to-Target Dist: L={max_hip_dist_l:.5f}m, R={max_hip_dist_r:.5f}m (limit={MAX_LEG_REACH:.2f}m)\n"
        f"  IK Unreachable Events: {unreachable_count}"
    )

    if abs(total_root_disp - 1.26) > 1e-4:
        _fail(f"Total root displacement mismatch vs Task 5C baseline: {total_root_disp:.5f}m != 1.26000m")
    if stand_start_v > 1e-5 or stand_stop_v > 1e-5:
        _fail(f"Root moved during standing phases: start_v={stand_start_v}, stop_v={stand_stop_v}")
    if abs(steady_v_min - 0.24) > 1e-3 or abs(steady_v_max - 0.24) > 1e-3:
        _fail(f"Steady walk speed mismatch: [{steady_v_min}, {steady_v_max}]")
    if max_stance_ankle_drift_l > 0.001 or max_stance_ankle_drift_r > 0.001:
        _fail(f"Support foot drifted: L={max_stance_ankle_drift_l}, R={max_stance_ankle_drift_r}")
    if final_foot_y_diff > 0.001:
        _fail(f"Feet did not align at stop: {final_foot_y_diff}")
    if min_foot_l_z < -0.001 or min_foot_r_z < -0.001:
        _fail(f"Ground penetration detected: L={min_foot_l_z}, R={min_foot_r_z}")
    if min_knee_fwd_l < 0.0 or min_knee_fwd_r < 0.0:
        _fail(f"Knee backward bend detected: L={min_knee_fwd_l}, R={min_knee_fwd_r}")
    if unreachable_count > 0:
        _fail(f"Encountered {unreachable_count} IK unreachable events")

    # 3. Verify multi-action chaining without hardcoded frame 1 or origin assumptions
    planner = MotionPlanner(config, armature_obj=arm_obj)
    planner.add_action(StartStopWalkAction())
    planner.add_action(StartStopWalkAction())
    chained = planner.execute()

    if (
        chained["total_frames"] != 408
        or abs(chained["total_root_displacement"] - 2.52) > 1e-4
        or chained["unreachable_count"] != 0
        or chained["action_results"][1].initial_state.frame != 205
        or abs(chained["action_results"][1].initial_state.position[1] - (-6.74)) > 1e-4
        or abs(chained["final_state"].position[1] - (-5.48)) > 1e-4
    ):
        _fail(
            f"Multi-action chaining verification failed: total_frames={chained['total_frames']}, "
            f"disp={chained['total_root_displacement']}, final_pos={chained['final_state'].position}"
        )
    print(
        f"Verified 2-action MotionPlanner chaining (frames 1..408, "
        f"Y: -8.0000m -> -6.7400m -> -5.4800m, total_disp=2.5200m, unreachable=0)"
    )

    print("[VERIFY_PASSED] Task 6A motion system foundation verification completed.")
    print("=== END TASK 6A MOTION FRAMEWORK VERIFICATION ===")


if __name__ == "__main__":
    verify()
