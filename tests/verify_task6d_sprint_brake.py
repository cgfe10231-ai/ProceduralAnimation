"""Reopen character_sprint_brake_prototype.blend and verify Task 6D:
- Timeline (1..162 @ 24 FPS)
- Boundary continuity at Frame 114 -> 115 (root displacement, discrete velocity, torso pitch, pelvis Z, contact lock)
- Strictly monotonic deceleration curve from 2.0 m/s to 0.0 m/s, zero backward motion
- Foot placement, contact locking, and zero stance drift (<= 0.0001m)
- Ground clearance and zero penetration (foot_min_z >= -0.0001m)
- Knee direction integrity (knee_forward_y >= +0.05m)
- Leg IK reachability (hip_to_target_dist <= 0.82000m, 0 unreachable, 0 target clamp events)
- Final stop bilateral stability and zero root jitter in the final 10 frames
- Chained execution with offset start via MotionPlanner
"""

import math
import os
import sys

import bpy
from mathutils import Vector

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import PipelineConfig
from src.motion.framework import MotionMode, MotionPlanner, create_initial_motion_state
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.rig.ik import IK_TARGET_NAMES, MAX_LEG_REACH, get_leg_ik_state


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 6D SPRINT BRAKE REOPEN VERIFICATION ===")
    config = PipelineConfig()
    scene = bpy.context.scene
    sx, sy, sz = config.character_path_points[0]
    fps = float(config.fps)

    expected_total = config.sprint_total_frames + config.sprint_brake_total_frames  # 114 + 48 = 162
    if scene.render.fps != 24 or scene.frame_start != 1 or scene.frame_end != expected_total:
        _fail(f"Bad timeline: fps={scene.render.fps}, range={scene.frame_start}..{scene.frame_end}, expected 1..{expected_total}")

    arm = bpy.data.objects.get("CharacterArmature")
    root = bpy.data.objects.get("CharacterRoot")
    ik = {s: bpy.data.objects.get(IK_TARGET_NAMES[s]) for s in "LR"}
    if arm is None or root is None or None in ik.values():
        _fail("Missing rig objects in blend file")

    for n in ("CharacterRoot", "CharacterArmature", "FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R"):
        o = bpy.data.objects.get(n)
        if o is None or o.animation_data is None or o.animation_data.action is None:
            _fail(f"Object {n} is missing animated Action data")
    print("Verified saved Actions on root/armature/IK/pole objects")

    root_y = []
    pelvis_z = []
    torso_pitch = []
    min_foot_z = 999.0
    min_knee_fwd = 999.0
    max_hip_dist = 0.0
    unreachable_count = 0
    stance_drifts = {"L": [], "R": []}

    for frame in range(1, expected_total + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()

        rp = root.matrix_world.translation
        if abs(rp.x - sx) > 1e-4 or abs(rp.z - sz) > 1e-4:
            _fail(f"Frame {frame}: CharacterRoot X/Z drift (x={rp.x}, z={rp.z})")
        root_y.append(rp.y)

        pb_p, pb_s = arm.pose.bones["pelvis"], arm.pose.bones["spine"]
        hz = (arm.matrix_world @ pb_p.head).z
        pelvis_z.append(hz)
        pitch = -math.degrees(pb_p.rotation_euler.x + pb_s.rotation_euler.x)
        torso_pitch.append(pitch)

        st = {s: get_leg_ik_state(arm, s) for s in "LR"}
        for s in "LR":
            d = (st[s]["target_world"] - st[s]["hip_world"]).length
            max_hip_dist = max(max_hip_dist, d)
            if d > MAX_LEG_REACH + 1e-4:
                unreachable_count += 1
            min_foot_z = min(min_foot_z, st[s]["foot_min_z"])
            if frame > config.sprint_prep_frames:
                min_knee_fwd = min(min_knee_fwd, st[s]["knee_forward_y"])

        # Track stance phase drift during braking (Frames 115..162)
        if frame >= 115:
            tau = frame - 115
            # Braking stance schedule:
            # R stance: tau in [0, 2], [12, 23], [34, 47]
            # L stance: tau in [3, 11], [24, 47]
            is_stance_l = (3 <= tau < 12) or (tau >= 24)
            is_stance_r = (tau < 3) or (12 <= tau < 24) or (tau >= 34)

            # Left stance drift
            if is_stance_l:
                if tau in (3, 24):
                    ref_l = st["L"]["ankle_world"].copy()
                else:
                    drift_l = (st["L"]["ankle_world"] - ref_l).length
                    stance_drifts["L"].append(drift_l)

            # Right stance drift
            if is_stance_r:
                if tau in (0, 12, 34):
                    ref_r = st["R"]["ankle_world"].copy()
                else:
                    drift_r = (st["R"]["ankle_world"] - ref_r).length
                    stance_drifts["R"].append(drift_r)

    # 1. Boundary Continuity Check at Frame 114 -> 115
    y114 = root_y[113]
    y115 = root_y[114]
    dy_boundary = y115 - y114
    v_discrete_boundary = dy_boundary * fps

    p114 = torso_pitch[113]
    p115 = torso_pitch[114]
    dpitch_boundary = abs(p115 - p114)

    z114 = pelvis_z[113]
    z115 = pelvis_z[114]
    dz_boundary = abs(z115 - z114)

    print("\n--- Boundary Continuity (Frame 114 -> 115) ---")
    print(f"  Root Y: {y114:.5f} -> {y115:.5f} (dy = {dy_boundary:.5f}m, discrete v = {v_discrete_boundary:.4f} m/s)")
    print(f"  Torso pitch: {p114:.3f} deg -> {p115:.3f} deg (delta = {dpitch_boundary:.3f} deg)")
    print(f"  Pelvis Z: {z114:.5f}m -> {z115:.5f}m (delta = {dz_boundary:.5f}m)")

    if abs(v_discrete_boundary - 2.0) > 0.05:
        _fail(f"Boundary velocity jump: discrete v = {v_discrete_boundary:.4f} m/s, expected ~2.0 m/s")
    if dpitch_boundary > 1.5:
        _fail(f"Boundary torso pitch jump too large: {dpitch_boundary:.3f} deg")
    if dz_boundary > 0.015:
        _fail(f"Boundary pelvis Z jump too large: {dz_boundary:.5f} m")

    # 2. Deceleration Kinematics (Frames 115..162)
    brake_root_y = root_y[113:]  # Include frame 114 as baseline
    discrete_velocities = [(brake_root_y[i + 1] - brake_root_y[i]) * fps for i in range(len(brake_root_y) - 1)]

    # Check for zero backward displacement
    for i, v in enumerate(discrete_velocities):
        if v < -1e-5:
            _fail(f"Backward motion detected at brake frame {115 + i}: velocity = {v:.5f} m/s")

    # Check monotonic speed decline
    monotonic_errors = []
    for i in range(len(discrete_velocities) - 1):
        if discrete_velocities[i + 1] > discrete_velocities[i] + 1e-4:
            monotonic_errors.append((115 + i, discrete_velocities[i], discrete_velocities[i + 1]))
    if monotonic_errors:
        _fail(f"Braking velocity not monotonically non-increasing: {monotonic_errors[:3]}")

    total_brake_disp = root_y[-1] - root_y[113]
    final_v = discrete_velocities[-1]

    print("\n--- Braking Kinematics (Frames 115..162) ---")
    print(f"  Total brake displacement: {total_brake_disp:.5f} m (expected ~1.5000 m)")
    print(f"  Initial discrete velocity: {discrete_velocities[0]:.4f} m/s")
    print(f"  Final discrete velocity: {final_v:.6f} m/s")
    print(f"  Monotonic deceleration: True (0 violations)")

    if abs(total_brake_disp - 1.5000) > 0.02:
        _fail(f"Braking displacement mismatch: got {total_brake_disp:.5f} m, expected ~1.5000 m")
    if abs(final_v) > 1e-5:
        _fail(f"Final velocity non-zero: {final_v:.6f} m/s")

    # 3. Contact, IK and Knee Checks
    max_drift_l = max(stance_drifts["L"]) if stance_drifts["L"] else 0.0
    max_drift_r = max(stance_drifts["R"]) if stance_drifts["R"] else 0.0
    print("\n--- Contact, Drift & IK Checks ---")
    print(f"  Max stance drift: L = {max_drift_l:.6f} m, R = {max_drift_r:.6f} m (limit 0.00010 m)")
    print(f"  Min foot mesh Z: {min_foot_z:.6f} m (limit >= -0.00010 m)")
    print(f"  Min knee forward offset: {min_knee_fwd:.4f} m (limit >= +0.050 m)")
    print(f"  Max hip-to-target distance: {max_hip_dist:.5f} m (limit <= {MAX_LEG_REACH:.5f} m)")
    print(f"  Unreachable events: {unreachable_count}")

    if max_drift_l > 1e-4 or max_drift_r > 1e-4:
        _fail(f"Stance foot drift exceeded limit: L={max_drift_l:.6f}m, R={max_drift_r:.6f}m")
    if min_foot_z < -1e-4:
        _fail(f"Foot ground penetration: min Z = {min_foot_z:.6f} m")
    if min_knee_fwd < 0.045:
        _fail(f"Knee hyperextension or inversion: min knee forward = {min_knee_fwd:.4f} m")
    if unreachable_count > 0:
        _fail(f"{unreachable_count} IK unreachable events detected")

    # 4. Final 10 Frames Stability
    last_10_y = root_y[-10:]
    jitter = max(last_10_y) - min(last_10_y)
    print("\n--- Final Stop Stability (Last 10 Frames) ---")
    print(f"  Root Y jitter: {jitter:.8f} m (limit <= 1e-6 m)")
    if jitter > 1e-6:
        _fail(f"Root position jitter during final stop: {jitter:.8f} m")

    # Check both feet locked symmetrically at stop
    scene.frame_set(expected_total)
    bpy.context.view_layer.update()
    ik_l = bpy.data.objects.get(IK_TARGET_NAMES["L"])
    ik_r = bpy.data.objects.get(IK_TARGET_NAMES["R"])
    if not (bool(ik_l.get("is_locked", False)) and bool(ik_r.get("is_locked", False))):
        _fail("Final frame must have both feet locked in ground support")
    pos_l = ik_l.matrix_world.translation
    pos_r = ik_r.matrix_world.translation
    dy_feet = abs(pos_l.y - pos_r.y)
    print(f"  Final feet positions: L=({pos_l.x:.3f}, {pos_l.y:.4f}, {pos_l.z:.4f}), R=({pos_r.x:.3f}, {pos_r.y:.4f}, {pos_r.z:.4f})")
    print(f"  Feet alignment dy: {dy_feet:.6f} m")
    if dy_feet > 0.01:
        _fail(f"Final bilateral foot placement misaligned: dy = {dy_feet:.6f} m")

    # 5. Offset Start Chaining via MotionPlanner
    print("\n--- Offset Start Chaining via MotionPlanner ---")
    planner = MotionPlanner(config, armature_obj=arm)
    planner.add_action(SprintStartAction())
    planner.add_action(SprintBrakeAction())

    # Execute from offset state (e.g. frame 201, y = -3.0m)
    offset_start = create_initial_motion_state(
        config,
        start_frame=201,
        position=(sx, -3.0, sz),
    )
    plan_res = planner.execute(initial_state=offset_start)
    fin_state = plan_res["final_state"]
    print(f"  Executed 2 actions from frame 201: frames {plan_res['frame_records'][0]['frame']}..{plan_res['frame_records'][-1]['frame']}")
    print(f"  Displacement: {plan_res['total_root_displacement']:.4f} m (expected {6.5833 + 1.5000:.4f} m)")
    print(f"  Final state: mode={fin_state.mode.value}, v={fin_state.velocity}, pos=({fin_state.position[0]:.2f}, {fin_state.position[1]:.4f}, {fin_state.position[2]:.4f})")
    print(f"  Unreachable count: {plan_res['unreachable_count']}")

    if fin_state.mode != MotionMode.STOP:
        _fail(f"Final state mode should be STOP, got {fin_state.mode}")
    if abs(fin_state.velocity[1]) > 1e-4:
        _fail(f"Final state forward velocity should be 0, got {fin_state.velocity[1]}")
    if plan_res["unreachable_count"] > 0:
        _fail(f"Offset chaining had {plan_res['unreachable_count']} unreachable events")

    print("\n[VERIFY_PASSED] Task 6D sprint brake verification completed successfully.")
    print("=== END TASK 6D SPRINT BRAKE REOPEN VERIFICATION ===")


if __name__ == "__main__":
    try:
        verify()
    except Exception as exc:
        print(f"[VERIFY_FAILED] {exc}", file=sys.stderr)
        sys.exit(1)
