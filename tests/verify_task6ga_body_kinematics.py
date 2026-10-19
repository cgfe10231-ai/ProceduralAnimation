"""Automated verification suite for Task 6G-A: Continuous Body Motion State and Differential Kinematics.

Tests:
1. Static Pose Zero Velocity: stationary character has strictly zero linear and angular velocities.
2. Constant Linear Translation: uniform root translation yields exact linear velocity matching dx/dt.
3. Constant Angular Rotation: uniform spin around axis yields exact angular velocity vector matching dtheta/dt.
4. Compound 3D Rotation: multi-axis 3D rotation yields accurate angular velocity vector without cross-axis distortion.
5. Wrap-Around Stability (+/-180 deg): rotating across +/-180 deg boundary produces smooth angular velocity without spikes.
6. Variable dt Scaling: velocity scales strictly inversely with dt (independent of frame rate assumption).
7. Single-Limb Isolation: moving one limb produces velocities only on that limb while contralateral limbs remain zero.
8. CoM Velocity Consistency: whole-body CoM velocity identically equals mass-weighted sum of segment velocities.
9. IK Actual Pose Integration: WholeBodyController evaluated actual poses cleanly produce valid BodyMotionStates.
10. SprintStart/SprintBrake Boundary Continuity: transition across action boundary (Frames 114 -> 115) is continuous.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.body_kinematics import (
    BodyKinematicsTracker,
    BodyMotionState,
    BodyPoseSnapshot,
    BodyVelocityState,
    compute_differential_velocity,
    create_zero_velocity_state,
    enrich_motion_state_with_kinematics,
    linear_acceleration,
    linear_velocity,
    relative_angular_velocity,
    relative_rotation_vector,
    sample_body_pose_from_controller_result,
    sample_body_pose_snapshot,
)
from src.motion.framework import (
    ContactConstraintAdapter,
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    create_initial_motion_state,
)
from src.motion.joint_limits import DEFAULT_HUMANOID_ROM_MODEL
from src.motion.rigid_link import (
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    compute_whole_body_com,
)
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.whole_body_controller import (
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.pose import reset_pose


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify_body_kinematics() -> None:
    print("=" * 74)
    print("VERIFYING TASK 6G-A: CONTINUOUS BODY MOTION STATE AND DIFFERENTIAL KINEMATICS")
    print("=" * 74)

    config = PipelineConfig()
    build_character(config)
    arm = build_rig(config)
    bind_character_to_rig(arm)
    reset_pose(arm)
    root = arm.parent or bpy.data.objects.get("CharacterRoot")

    tracker = BodyKinematicsTracker(
        armature_obj=arm,
        root_obj=root,
        mass_distribution=DEMPSTER_WINTER_15_SEGMENT_MODEL,
        joint_model=DEFAULT_HUMANOID_ROM_MODEL,
        config=config,
    )

    # -------------------------------------------------------------------------
    # Test 1: Static Pose Zero Velocity
    # -------------------------------------------------------------------------
    print("\n[Test 1] Verifying static pose zero velocity...")
    snap_0 = sample_body_pose_snapshot(arm, root, time_sec=0.0, frame=1)
    snap_1 = sample_body_pose_snapshot(arm, root, time_sec=0.05, frame=2)

    vel_static = compute_differential_velocity(snap_1, snap_0, dt=0.05)
    root_speed = vel_static.root_speed_mps
    root_w = vel_static.root_angular_speed_radps
    com_speed = vel_static.com_speed_mps

    print(f"  Root linear speed : {root_speed:.8f} m/s")
    print(f"  Root angular speed: {root_w:.8f} rad/s")
    print(f"  CoM linear speed  : {com_speed:.8f} m/s")

    max_seg_v = max(math.sqrt(v[0]**2 + v[1]**2 + v[2]**2) for v in vel_static.segment_linear_velocities.values())
    max_joint_w = max(math.sqrt(w[0]**2 + w[1]**2 + w[2]**2) for w in vel_static.joint_angular_velocities.values())
    print(f"  Max segment speed : {max_seg_v:.8f} m/s")
    print(f"  Max joint rot vel : {max_joint_w:.8f} rad/s")

    if root_speed > 1e-7:
        _fail(f"Static root speed > 1e-7: {root_speed}")
    if root_w > 1e-7:
        _fail(f"Static root angular speed > 1e-7: {root_w}")
    if com_speed > 1e-7:
        _fail(f"Static CoM speed > 1e-7: {com_speed}")
    if max_seg_v > 1e-7:
        _fail(f"Static segment speed > 1e-7: {max_seg_v}")
    if max_joint_w > 1e-7:
        _fail(f"Static joint angular speed > 1e-7: {max_joint_w}")
    print("  -> PASSED: Static posture produces strictly zero linear and angular velocities.")

    # -------------------------------------------------------------------------
    # Test 2: Constant Linear Translation
    # -------------------------------------------------------------------------
    print("\n[Test 2] Verifying constant root linear translation...")
    expected_v = 2.5  # m/s along +Y
    dt_2 = 0.04       # 25 Hz
    dy = expected_v * dt_2  # 0.10 m

    p0 = (0.0, -8.0, 0.0)
    p1 = (0.0, -8.0 + dy, 0.0)

    # Synthetic snapshots with exact translation
    snap_t0 = sample_body_pose_snapshot(arm, root, time_sec=0.0)
    snap_t1 = BodyPoseSnapshot(
        time_sec=dt_2,
        frame=2,
        root_position=p1,
        root_orientation_quat=snap_t0.root_orientation_quat,
        root_orientation_euler_deg=snap_t0.root_orientation_euler_deg,
        pelvis_position=(snap_t0.pelvis_position[0], snap_t0.pelvis_position[1] + dy, snap_t0.pelvis_position[2]),
        pelvis_orientation_quat=snap_t0.pelvis_orientation_quat,
        com_world=(snap_t0.com_world[0], snap_t0.com_world[1] + dy, snap_t0.com_world[2]),
        segment_positions={k: (v[0], v[1] + dy, v[2]) for k, v in snap_t0.segment_positions.items()},
        segment_orientations=snap_t0.segment_orientations,
        joint_rotations_rad=snap_t0.joint_rotations_rad,
        joint_quats=snap_t0.joint_quats,
        end_effectors={k: (v[0], v[1] + dy, v[2]) for k, v in snap_t0.end_effectors.items()},
        contacts=snap_t0.contacts,
    )

    vel_t = compute_differential_velocity(snap_t1, snap_t0, dt=dt_2)
    err_v = abs(vel_t.root_linear_velocity[1] - expected_v)
    err_vx = abs(vel_t.root_linear_velocity[0])
    err_vz = abs(vel_t.root_linear_velocity[2])

    print(f"  Expected v_y: {expected_v:.4f} m/s | Derived: {vel_t.root_linear_velocity[1]:.8f} m/s (error: {err_v:.10f} m/s)")
    print(f"  Cross-axis v_x: {err_vx:.10f} m/s, v_z: {err_vz:.10f} m/s")

    if err_v > 1e-7:
        _fail(f"Linear velocity error too large: {err_v}")
    if err_vx > 1e-7 or err_vz > 1e-7:
        _fail("Spurious cross-axis velocity detected during pure Y translation")
    print("  -> PASSED: Linear translation derived velocity matches analytic dx/dt exactly.")

    # -------------------------------------------------------------------------
    # Test 3: Constant Angular Rotation
    # -------------------------------------------------------------------------
    print("\n[Test 3] Verifying constant angular velocity rotation...")
    expected_w_deg = 60.0  # deg/s around Z
    expected_w_rad = math.radians(expected_w_deg)
    dt_3 = 0.05
    d_theta_rad = expected_w_rad * dt_3

    q0 = Euler((0.0, 0.0, 0.0), "XYZ").to_quaternion()
    q1 = Euler((0.0, 0.0, d_theta_rad), "XYZ").to_quaternion()

    w_rot = relative_angular_velocity(q0, q1, dt=dt_3)
    err_w_rad = abs(w_rot.z - expected_w_rad)
    err_wx = abs(w_rot.x)
    err_wy = abs(w_rot.y)
    derived_deg = math.degrees(w_rot.z)

    print(f"  Expected w_z: {expected_w_deg:.4f} deg/s ({expected_w_rad:.6f} rad/s)")
    print(f"  Derived w_z : {derived_deg:.6f} deg/s ({w_rot.z:.8f} rad/s) [error: {err_w_rad:.10f} rad/s]")
    print(f"  Cross-axis w_x: {err_wx:.10f}, w_y: {err_wy:.10f}")

    if err_w_rad > 1e-6:
        _fail(f"Angular velocity error too large: {err_w_rad}")
    if err_wx > 1e-7 or err_wy > 1e-7:
        _fail("Spurious cross-axis angular velocity detected")
    print("  -> PASSED: Constant angular rotation derived velocity matches dtheta/dt exactly.")

    # -------------------------------------------------------------------------
    # Test 4: Compound 3D Rotation
    # -------------------------------------------------------------------------
    print("\n[Test 4] Verifying compound 3D rotation angular velocity...")
    target_omega = Vector((0.5, -0.8, 1.2))  # rad/s in 3D
    omega_mag = target_omega.length
    axis_3d = target_omega.normalized()
    dt_4 = 0.04
    theta_3d = omega_mag * dt_4

    # Build quaternion corresponding to exact rotation
    delta_q = Quaternion(axis_3d, theta_3d)
    q_base = Euler((math.radians(15.0), math.radians(-20.0), math.radians(40.0)), "XYZ").to_quaternion()
    q_next = delta_q @ q_base

    computed_w = relative_angular_velocity(q_base, q_next, dt=dt_4)
    w_error = (computed_w - target_omega).length
    print(f"  Target omega  : ({target_omega.x:.4f}, {target_omega.y:.4f}, {target_omega.z:.4f}) rad/s")
    print(f"  Computed omega: ({computed_w.x:.4f}, {computed_w.y:.4f}, {computed_w.z:.4f}) rad/s")
    print(f"  3D vector discrepancy: {w_error:.10f} rad/s")

    if w_error > 1e-5:
        _fail(f"Compound 3D rotation angular velocity error > 1e-5: {w_error}")
    print("  -> PASSED: Arbitrary 3D compound rotation vector correctly reconstructed.")

    # -------------------------------------------------------------------------
    # Test 5: Wrap-Around Stability (+/-180 deg)
    # -------------------------------------------------------------------------
    print("\n[Test 5] Verifying wrap-around stability across +/-180 deg boundary...")
    # Rotate smoothly from +175 deg to -175 deg in dt = 0.05 s (rotation of +10 deg = +200 deg/s)
    q_pos = Euler((0.0, 0.0, math.radians(175.0)), "XYZ").to_quaternion()
    q_neg = Euler((0.0, 0.0, math.radians(-175.0)), "XYZ").to_quaternion()
    dt_5 = 0.05

    w_forward = relative_angular_velocity(q_pos, q_neg, dt=dt_5)
    w_forward_deg = math.degrees(w_forward.z)
    expected_spike_free_deg = 200.0  # +10 deg / 0.05s = +200 deg/s

    print(f"  +175 -> -175 deg crossing: derived w_z = {w_forward_deg:.4f} deg/s (expected {expected_spike_free_deg:.4f} deg/s)")
    if abs(w_forward_deg - expected_spike_free_deg) > 0.01:
        _fail(f"Angular velocity spike detected during +180/-180 crossing: {w_forward_deg} deg/s")

    # Reverse direction: -175 deg to +175 deg (-10 deg / 0.05s = -200 deg/s)
    w_reverse = relative_angular_velocity(q_neg, q_pos, dt=dt_5)
    w_reverse_deg = math.degrees(w_reverse.z)
    print(f"  -175 -> +175 deg crossing: derived w_z = {w_reverse_deg:.4f} deg/s (expected {-expected_spike_free_deg:.4f} deg/s)")
    if abs(w_reverse_deg - (-expected_spike_free_deg)) > 0.01:
        _fail(f"Angular velocity spike detected during reverse crossing: {w_reverse_deg} deg/s")

    print("  -> PASSED: Geodesic SO(3) formulation guarantees zero +/-180 deg velocity spikes.")

    # -------------------------------------------------------------------------
    # Test 6: Variable dt Scaling
    # -------------------------------------------------------------------------
    print("\n[Test 6] Verifying variable dt scaling...")
    disp_m = 0.10
    test_dts = [0.10, 0.05, 0.02, 0.01, 0.005]
    for test_dt in test_dts:
        v_derived = linear_velocity((0.0, 0.0, 0.0), (0.0, disp_m, 0.0), test_dt)[1]
        v_expected = disp_m / test_dt
        err_dt = abs(v_derived - v_expected)
        print(f"  dt={test_dt:.4f}s -> derived v={v_derived:.4f} m/s, expected={v_expected:.4f} m/s (err={err_dt:.10f})")
        if err_dt > 1e-8:
            _fail(f"Variable dt scaling error at dt={test_dt}: {err_dt}")
    print("  -> PASSED: Kinematics strictly parameterizes by arbitrary dt without assuming 24 FPS.")

    # -------------------------------------------------------------------------
    # Test 7: Single-Limb Isolation
    # -------------------------------------------------------------------------
    print("\n[Test 7] Verifying single-limb motion isolation...")
    wbc = WholeBodyController(armature_obj=arm, root_obj=root, config=config)
    wbc.reset_all_controls()

    # Step 1: Base pose
    t_base = WholeBodyControlTargets()
    t_base.set_hand("L", (-0.24, -7.80, 1.25))
    t_base.set_hand("R", (0.24, -7.80, 1.25))
    t_base.set_foot("L", (-0.11, -8.00, 0.07))
    t_base.set_foot("R", (0.11, -8.00, 0.07))
    res_base = wbc.execute_frame(t_base)
    snap_base = sample_body_pose_snapshot(arm, root, time_sec=0.0, frame=1)

    # Step 2: Move ONLY left hand forward by +0.10m over dt = 0.05s
    dt_7 = 0.05
    t_moved = WholeBodyControlTargets()
    t_moved.set_hand("L", (-0.24, -7.70, 1.25))  # +0.10m in Y
    t_moved.set_hand("R", (0.24, -7.80, 1.25))  # unchanged
    t_moved.set_foot("L", (-0.11, -8.00, 0.07))  # unchanged
    t_moved.set_foot("R", (0.11, -8.00, 0.07))  # unchanged
    res_moved = wbc.execute_frame(t_moved)
    snap_moved = sample_body_pose_snapshot(arm, root, time_sec=dt_7, frame=2)

    vel_iso = compute_differential_velocity(snap_moved, snap_base, dt=dt_7)

    # Left hand/forearm velocity must be significant
    v_hand_l = math.hypot(vel_iso.end_effector_velocities["hand_L"][0],
                          vel_iso.end_effector_velocities["hand_L"][1],
                          vel_iso.end_effector_velocities["hand_L"][2])
    # Right hand velocity must be zero
    v_hand_r = math.hypot(vel_iso.end_effector_velocities["hand_R"][0],
                          vel_iso.end_effector_velocities["hand_R"][1],
                          vel_iso.end_effector_velocities["hand_R"][2])
    # Feet velocities must be zero
    v_foot_l = math.hypot(vel_iso.end_effector_velocities["foot_L"][0],
                          vel_iso.end_effector_velocities["foot_L"][1],
                          vel_iso.end_effector_velocities["foot_L"][2])
    v_foot_r = math.hypot(vel_iso.end_effector_velocities["foot_R"][0],
                          vel_iso.end_effector_velocities["foot_R"][1],
                          vel_iso.end_effector_velocities["foot_R"][2])

    print(f"  Left Hand speed : {v_hand_l:.4f} m/s (expected ~2.000 m/s)")
    print(f"  Right Hand speed: {v_hand_r:.8f} m/s (expected 0.000 m/s)")
    print(f"  Left Foot speed : {v_foot_l:.8f} m/s (expected 0.000 m/s)")
    print(f"  Right Foot speed: {v_foot_r:.8f} m/s (expected 0.000 m/s)")

    if abs(v_hand_l - 2.0) > 0.05:
        _fail(f"Left hand velocity discrepancy: {v_hand_l} != 2.0 m/s")
    if v_hand_r > 1e-4:
        _fail(f"Right hand unexpectedly moved: {v_hand_r} m/s")
    if v_foot_l > 1e-4 or v_foot_r > 1e-4:
        _fail(f"Feet unexpectedly moved: L={v_foot_l}, R={v_foot_r}")
    print("  -> PASSED: Single-limb motion cleanly isolated with zero contralateral cross-talk.")

    # -------------------------------------------------------------------------
    # Test 8: CoM Velocity Consistency
    # -------------------------------------------------------------------------
    print("\n[Test 8] Verifying Whole-Body CoM velocity consistency with segment momentum...")
    # CoM velocity derived directly from position difference must equal mass-weighted sum of segment velocities
    v_com_direct = Vector(vel_iso.com_linear_velocity)
    v_com_weighted = Vector((0.0, 0.0, 0.0))
    for seg in DEMPSTER_WINTER_15_SEGMENT_MODEL.segments:
        seg_v = Vector(vel_iso.segment_linear_velocities[seg.segment_id])
        v_com_weighted += seg.mass_ratio * seg_v

    com_momentum_discrepancy = (v_com_direct - v_com_weighted).length
    print(f"  Direct CoM velocity       : ({v_com_direct.x:.6f}, {v_com_direct.y:.6f}, {v_com_direct.z:.6f}) m/s")
    print(f"  Mass-weighted segment sum : ({v_com_weighted.x:.6f}, {v_com_weighted.y:.6f}, {v_com_weighted.z:.6f}) m/s")
    print(f"  Mathematical discrepancy   : {com_momentum_discrepancy:.10f} m/s")

    if com_momentum_discrepancy > 1e-5:
        _fail(f"CoM velocity does not match mass-weighted sum of segment velocities: {com_momentum_discrepancy}")
    print("  -> PASSED: Whole-body CoM velocity mathematically consistent with multi-link momentum.")

    # -------------------------------------------------------------------------
    # Test 9: IK Actual Pose Integration & MotionState Enrichment
    # -------------------------------------------------------------------------
    print("\n[Test 9] Testing WholeBodyController actual pose sampling and MotionState enrichment...")
    # Verify sample_body_pose_from_controller_result and enrich_motion_state_with_kinematics
    snap_ctrl = sample_body_pose_from_controller_result(res_moved, time_sec=0.05, frame=2, armature_obj=arm, root_obj=root)
    b_motion_state = tracker.update(snap_ctrl, dt=0.05)

    base_ms = MotionState(
        frame=2,
        time_sec=0.05,
        position=snap_ctrl.root_position,
        orientation_deg=snap_ctrl.root_orientation_euler_deg,
        velocity=(0.0, 0.0, 0.0),
        acceleration=(0.0, 0.0, 0.0),
        mode=MotionMode.IDLE,
        gait_phase=0.0,
    )
    enriched_ms = enrich_motion_state_with_kinematics(base_ms, b_motion_state)

    print(f"  Enriched params['com_world']            : {enriched_ms.params['com_world']}")
    print(f"  Enriched params['com_linear_velocity']  : {enriched_ms.params['com_linear_velocity']}")
    print(f"  Enriched params['root_angular_velocity']: {enriched_ms.params['root_angular_velocity_radps']}")
    print(f"  Original ms.velocity preserved          : {enriched_ms.velocity}")

    if "com_world" not in enriched_ms.params or "com_linear_velocity" not in enriched_ms.params:
        _fail("Enriched MotionState is missing CoM telemetry in params")
    if enriched_ms.velocity != (0.0, 0.0, 0.0):
        _fail("Enrichment mutated base MotionState velocity unexpectedly")
    print("  -> PASSED: Actual IK pose cleanly sampled and seamlessly enriches MotionState.")

    # -------------------------------------------------------------------------
    # Test 10: SprintStart / SprintBrake Boundary Continuity
    # -------------------------------------------------------------------------
    print("\n[Test 10] Testing SprintStart / SprintBrake boundary velocity continuity...")
    env = EnvironmentQuery(ground_z=0.0)
    contact_adapter = ContactConstraintAdapter(arm, env)
    from src.motion.framework import BlenderPoseApplicator
    pose_applicator = BlenderPoseApplicator(arm, root, config)
    ctx = MotionRuntimeContext(
        config=config,
        armature_obj=arm,
        root_obj=root,
        scene=bpy.context.scene,
        environment=env,
        contact_adapter=contact_adapter,
        pose_applicator=pose_applicator,
    )

    init_state = create_initial_motion_state(config)
    sprint_action = SprintStartAction()
    res_sprint = sprint_action.execute(init_state, ctx)

    # Frame 114 is final sprint frame (v = 2.0 m/s)
    final_sprint_state = res_sprint.final_state
    print(f"  Sprint final state: frame={final_sprint_state.frame}, v={final_sprint_state.velocity[1]:.4f} m/s, y={final_sprint_state.position[1]:.4f} m")

    brake_action = SprintBrakeAction()
    res_brake = brake_action.execute(final_sprint_state, ctx)
    first_brake_state = res_brake.states[0]
    print(f"  Brake first state : frame={first_brake_state.frame}, v={first_brake_state.velocity[1]:.4f} m/s, y={first_brake_state.position[1]:.4f} m")

    # Inspect boundary continuity
    disp_gap = abs(first_brake_state.position[1] - final_sprint_state.position[1])
    vel_gap = abs(first_brake_state.velocity[1] - final_sprint_state.velocity[1])

    print(f"  Boundary root Y gap   : {disp_gap:.8f} m (expected <= 0.084 m, exactly 1 frame step)")
    print(f"  Boundary velocity gap : {vel_gap:.8f} m/s (expected 0.000 m/s)")

    if vel_gap > 0.01:
        _fail(f"Velocity jump detected at SprintStart -> SprintBrake boundary: {vel_gap} m/s")

    # Sample boundary snapshots through tracker
    tracker.reset()
    boundary_states = [res_sprint.states[-2], res_sprint.states[-1], res_brake.states[0], res_brake.states[1]]
    diff_velocities = []
    for ms in boundary_states:
        snap = BodyPoseSnapshot(
            time_sec=ms.time_sec,
            frame=ms.frame,
            root_position=ms.position,
            root_orientation_quat=Euler((0.0, 0.0, 0.0), "XYZ").to_quaternion(),
            root_orientation_euler_deg=ms.orientation_deg,
            pelvis_position=ms.position,
            pelvis_orientation_quat=Euler((0.0, 0.0, 0.0), "XYZ").to_quaternion(),
            com_world=ms.position,
            segment_positions={"torso": ms.position},
            segment_orientations={"torso": (1.0, 0.0, 0.0, 0.0)},
            joint_rotations_rad={},
            joint_quats={},
            end_effectors={},
            contacts={},
            commanded_velocity=ms.velocity,
        )
        b_ms = tracker.update(snap, dt=1.0 / config.fps)
        diff_velocities.append(b_ms.velocity.root_linear_velocity[1])

    print(f"  Derived boundary velocities: {[round(v, 4) for v in diff_velocities]} m/s")
    # Verify smooth deceleration without reverse motion or extreme spikes
    for v in diff_velocities[1:]:
        if v < -0.1 or v > 2.5:
            _fail(f"Anomalous derived velocity at boundary: {v} m/s")
    print("  -> PASSED: SprintStart -> SprintBrake boundary velocity continuity verified.")

    # Reset
    reset_pose(arm)
    tracker.reset()

    print("\n" + "=" * 74)
    print("ALL TASK 6G-A BODY KINEMATICS VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 74)


if __name__ == "__main__":
    verify_body_kinematics()
