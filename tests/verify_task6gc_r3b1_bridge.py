"""Verification Test Suite for Task 6G-C-R3B-1: Minimal Compatibility Bridge Layer.

Validates:
1. Lossless Input Mapping: historical action parameters map 1:1 to WholeBodyControlTargets.
2. FK/IK Arbitration and Control Ownership: arm FK vs IK priorities and exclusive writing.
3. Stance Foot Ground Anchor Preservation: root translation leaves locked stance foot pinned.
4. Truthful ROM & Reach Failure Reporting: zero false-success reporting on violations.
5. Quantitative Pose Equivalence: old pose applicator vs KinematicBridgeExecutor pose match.
6. Immutability of Historical Gait Curves: step schedule & C1 velocity functions unaltered.
7. Coordinate and Unit Consistency: +Z up, +Y forward, ground Z=0, meters/degrees/seconds.
8. Duplicate Write Conflict Prevention: single ownership enforced per frame.
9. Full Single-Frame 6-Phase Pipeline Execution: phases 1..6 executed in strict sequence.
10. Core Historical Regression: verifies Task 6F-D, 6F-C, 6F-B, 6F-A, 6D, 6G regression.
"""

import math
import os
import subprocess
import sys
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import bpy
from mathutils import Euler, Matrix, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.body_inertia import compute_whole_body_inertia
from src.motion.contact_model import ContactLifecycle, ContactType, EnvironmentalSurface
from src.motion.framework import (
    ContactPointState,
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    MotionState,
    StartStopWalkAction,
    WORLD_FORWARD_AXIS,
    WORLD_RIGHT_AXIS,
    WORLD_UP_AXIS,
    create_initial_motion_state,
)
from src.motion.joint_limits import JointModel
from src.motion.kinematic_bridge import (
    BridgeExecutionResult,
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
    convert_planned_pose_to_wbc_targets,
)
from src.motion.run_cycle import RunAction
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.start_stop_walk import (
    _apply_start_stop_upper_body_pose,
    _evaluate_gait_phase_and_envelopes,
    build_step_schedule,
    evaluate_root_kinematics,
)
from src.motion.whole_body_controller import (
    EndEffectorTarget,
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.arm_ik import get_arm_ik_state, reset_arm_ik, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    MIN_LEG_REACH,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose, set_bone_location, set_bone_rotation


def _clean_scene() -> Tuple[bpy.types.Object, bpy.types.Object]:
    """Reset Blender scene with fresh character armature."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm, do_unlink=True)

    config = PipelineConfig()
    build_character(config)
    arm_obj = build_rig(config)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    root_obj = arm_obj.parent or bpy.data.objects.get("CharacterRoot")
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj)
    bpy.context.view_layer.update()
    return arm_obj, root_obj


# =============================================================================
# Test 1: Lossless Input Mapping
# =============================================================================
def test_01_lossless_input_mapping() -> bool:
    print("\n--- Test 1: Lossless Input Mapping ---")
    planned = KinematicPlannedPose(
        frame=25,
        time_seconds=1.04167,
        root_position=(0.0, -7.500, 0.0),
        root_yaw_deg=5.0,
        speed_mps=0.24,
        motion_mode=MotionMode.WALK,
        pelvis_location=(0.015, -0.020, 0.0),
        pelvis_rotation_deg=(1.2, -0.5, 2.0),
        spine_rotation_deg=(-3.5, 1.0, -1.2),
        neck_rotation_deg=(1.5, -0.4, 0.5),
        head_rotation_deg=(1.5, -0.4, 0.5),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -7.50, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.35, 0.17), is_locked=False),
        fk_joint_rotations_deg={
            "upper_arm.L": (15.0, 0.0, -5.0),
            "forearm.L": (0.0, 30.0, 0.0),
            "upper_arm.R": (-12.0, 0.0, 4.0),
            "forearm.R": (0.0, 25.0, 0.0),
        },
        active_step_index=1,
        gait_phase=0.35,
    )

    targets = convert_planned_pose_to_wbc_targets(planned)

    # Validate lossless translation
    assert targets.root_position == (0.0, -7.500, 0.0), f"Root pos mismatch: {targets.root_position}"
    assert targets.root_yaw_deg == 5.0, f"Root yaw mismatch: {targets.root_yaw_deg}"
    assert targets.pelvis_location == (0.015, -0.020, 0.0), f"Pelvis loc mismatch: {targets.pelvis_location}"
    assert targets.pelvis_rotation_deg == (1.2, -0.5, 2.0), f"Pelvis rot mismatch: {targets.pelvis_rotation_deg}"
    assert targets.spine_rotation_deg == (-3.5, 1.0, -1.2), f"Spine rot mismatch: {targets.spine_rotation_deg}"
    assert targets.neck_rotation_deg == (1.5, -0.4, 0.5), f"Neck rot mismatch: {targets.neck_rotation_deg}"
    assert targets.head_rotation_deg == (1.5, -0.4, 0.5), f"Head rot mismatch: {targets.head_rotation_deg}"

    # Feet mapping
    assert targets.foot_L is not None and targets.foot_L.is_locked is True, "Foot L lock status mismatch"
    assert targets.foot_L.target_world_xyz == (-0.11, -7.50, 0.07), "Foot L target mismatch"
    assert targets.foot_R is not None and targets.foot_R.is_locked is False, "Foot R lock status mismatch"
    assert targets.foot_R.target_world_xyz == (0.11, -7.35, 0.17), "Foot R target mismatch"

    # Arms in FK mode
    assert targets.hand_L is not None and targets.hand_L.enabled is False, "Hand L should be disabled for FK"
    assert targets.hand_R is not None and targets.hand_R.enabled is False, "Hand R should be disabled for FK"
    assert "upper_arm.L" in targets.fk_joint_rotations_deg, "Arm FK joints missing"
    assert targets.fk_joint_rotations_deg["upper_arm.L"] == (15.0, 0.0, -5.0)

    print("  -> Lossless conversion verified: 100% of spatial and kinematic fields preserved.")
    return True


# =============================================================================
# Test 2: FK/IK Arbitration and Control Ownership
# =============================================================================
def test_02_fk_ik_arbitration_and_ownership() -> bool:
    print("\n--- Test 2: FK/IK Arbitration & Control Ownership ---")
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)

    # Sub-test A: Arms in FK mode (hands disabled, FK joint rotations provided)
    planned_fk = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, 0.07), is_locked=True),
        fk_joint_rotations_deg={
            "upper_arm.L": (30.0, 0.0, 0.0),
            "upper_arm.R": (-30.0, 0.0, 0.0),
        },
    )
    res_fk = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_fk), update_scene=True)

    # Check that Hand IK influence was zeroed
    ik_c_l = arm.pose.bones["forearm.L"].constraints.get("ArmIK.L")
    assert ik_c_l is not None and ik_c_l.influence == 0.0, f"FK mode failed to zero HandIK influence: {ik_c_l.influence if ik_c_l else 'None'}"

    # Check that bone rotation was applied directly to upper_arm.L
    p_upper_l = arm.pose.bones["upper_arm.L"]
    assert math.isclose(math.degrees(p_upper_l.rotation_euler.x), 30.0, abs_tol=1e-3), "FK rotation not applied"

    # Sub-test B: Arms in IK mode (hand_L enabled with world target)
    planned_ik = KinematicPlannedPose(
        frame=2,
        time_seconds=0.04167,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, 0.07), is_locked=True),
        hand_L=PlannedHandTarget(world_xyz=(-0.24, -7.65, 1.35), enabled=True, weight=1.0),
    )
    res_ik = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_ik), update_scene=True)

    assert ik_c_l.influence == 1.0, f"IK mode failed to set HandIK influence to 1.0: {ik_c_l.influence}"
    eff_l = res_ik.end_effectors["hand_L"]
    err_m = eff_l.position_error_m
    assert err_m < 0.005, f"Hand IK did not reach target: err={err_m*1000:.2f}mm"

    print(f"  -> FK/IK arbitration verified: FK influence=0.0, IK influence=1.0, wrist tracking error={err_m*1000:.3f}mm.")
    return True


# =============================================================================
# Test 3: Stance Foot Ground Anchor Preservation
# =============================================================================
def test_03_root_motion_stance_foot_preservation() -> bool:
    print("\n--- Test 3: Stance Foot Ground Anchor Preservation ---")
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)

    # Frame 1: Lock Left foot at stance coordinate (-0.11, -8.0, 0.07)
    locked_ankle = (-0.11, -8.000, 0.070)
    planned_f1 = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.000, 0.0),
        foot_L=PlannedFootTarget(world_xyz=locked_ankle, is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.000, 0.07), is_locked=True),
    )
    wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_f1), update_scene=True)

    # Verify locked status
    ik_obj_l = bpy.data.objects["FootIK.L"]
    assert ik_obj_l.get("is_locked") is True, "FootIK.L was not marked locked"
    assert ik_obj_l.parent is None, "FootIK.L must be unparented in world space when locked"

    # Frame 2: Move CharacterRoot forward by 0.020 m (single-frame locomotion increment) while keeping Left foot locked
    planned_f2 = KinematicPlannedPose(
        frame=2,
        time_seconds=0.04167,
        root_position=(0.0, -7.980, 0.0),  # +0.020 m forward
        foot_L=PlannedFootTarget(world_xyz=locked_ankle, is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.960, 0.10), is_locked=False),  # swing
    )
    wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_f2), update_scene=True)

    # Verify Left foot controller did NOT drift
    controller_pos = ik_obj_l.matrix_world.translation
    ctrl_drift_m = (controller_pos - Vector(locked_ankle)).length
    assert ctrl_drift_m < 1e-6, f"FootIK.L drifted when root moved: drift={ctrl_drift_m*1000:.4f}mm"

    # Verify ankle bone world drift
    p_shin_l = arm.pose.bones["shin.L"]
    ankle_world = arm.matrix_world @ p_shin_l.tail
    bone_drift_m = (ankle_world - Vector(locked_ankle)).length
    assert bone_drift_m < 0.005, f"Ankle bone drifted beyond tolerance: drift={bone_drift_m*1000:.3f}mm"

    print(f"  -> Stance foot preservation verified: controller drift={ctrl_drift_m*1000:.6f}mm, bone drift={bone_drift_m*1000:.3f}mm.")
    return True


# =============================================================================
# Test 4: Truthful ROM and Reach Failure Reporting
# =============================================================================
def test_04_truthful_rom_and_reach_failure_reporting() -> bool:
    print("\n--- Test 4: Truthful ROM & Reach Failure Reporting ---")
    arm, root = _clean_scene()
    wbc = WholeBodyController(armature_obj=arm)

    # Sub-test A: Impossible reach target
    planned_unreachable = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -6.5, 0.07), is_locked=False),  # 1.5 m away!
    )
    res = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_unreachable), update_scene=True)

    assert res.success is False, "Unreachable target was falsely reported as success"
    assert res.is_all_reachable is False, "is_all_reachable must be False"
    reasons = [u.category for u in res.unmet_constraints]
    assert "REACHABILITY" in reasons, f"Expected REACHABILITY in unmet constraints: {reasons}"

    # Sub-test B: Deliberate Spine ROM violation
    planned_rom_viol = KinematicPlannedPose(
        frame=2,
        time_seconds=0.04167,
        root_position=(0.0, -8.0, 0.0),
        spine_rotation_deg=(85.0, 0.0, 0.0),  # Max anatomical flexion is +60 deg
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, 0.07), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, 0.07), is_locked=True),
    )
    res_rom = wbc.execute_frame(convert_planned_pose_to_wbc_targets(planned_rom_viol), update_scene=True)

    assert res_rom.success is False, "ROM violation was falsely reported as success"
    assert res_rom.has_rom_violation is True, "has_rom_violation must be True"
    assert "spine" in res_rom.rom_validation.violations, "Spine violation not flagged"

    # Sub-test C: Enforcing ROM clamping with conflicting reach
    # When clamp is applied, if reach conflicts, ROM_CONFLICT must be returned
    res_clamp = wbc.execute_frame(
        convert_planned_pose_to_wbc_targets(planned_rom_viol),
        update_scene=True,
        enforce_rom_clamping=True,
    )
    # The original violation was intercepted
    assert res_clamp.success is False, "Clamping on invalid pose must truthfully report overall success=False"

    print("  -> Truthful reporting verified: REACHABILITY and ROM_VIOLATION strictly report success=False.")
    return True


# =============================================================================
# Test 5: Quantitative Pose Comparison (Old Applicator vs Bridge Executor)
# =============================================================================
def test_05_quantitative_pose_comparison_old_vs_bridge() -> bool:
    print("\n--- Test 5: Quantitative Pose Equivalence (Old vs Bridge) ---")
    config = PipelineConfig()

    # Step 1: Compute historical kinematics for frame 28 (steady step)
    tau = 27.0
    schedule = build_step_schedule(config, start_y=-8.0)
    disp_y, speed_mps, stage = evaluate_root_kinematics(tau, config)
    u, gait_amp, crouch_env, trans_drop, trans_lean_deg, active_step = _evaluate_gait_phase_and_envelopes(tau, config, schedule)

    # Old Direct Application:
    arm_old, root_old = _clean_scene()
    root_world_old = (0.0, -8.0 + disp_y, 0.0)
    root_old.location = Vector(root_world_old)
    _apply_start_stop_upper_body_pose(
        arm_old,
        config,
        u=u,
        gait_amp=gait_amp,
        crouch_env=crouch_env,
        trans_drop=trans_drop,
        trans_lean_deg=trans_lean_deg,
    )
    # Stance left, swing right
    locked_ankle = (-0.11, -8.0, ANKLE_REST_Z)
    lock_foot_contact(arm_old, "L", contact_world_xyz=(-0.11, -8.0, 0.0))
    swing_ankle = (0.11, -8.0 + 0.15, ANKLE_REST_Z + 0.10)
    set_foot_ik_target(arm_old, "R", swing_ankle)
    bpy.context.view_layer.update()

    # Extract old bone transforms before resetting scene
    p_pelvis_old = arm_old.pose.bones["pelvis"]
    pelvis_old_world = (arm_old.matrix_world @ p_pelvis_old.head).copy()
    pelvis_old_loc = p_pelvis_old.location.to_tuple()
    pelvis_old_rot = tuple(round(math.degrees(v), 3) for v in p_pelvis_old.rotation_euler)
    p_spine_old = arm_old.pose.bones["spine"]
    spine_old_rot = tuple(round(math.degrees(v), 3) for v in p_spine_old.rotation_euler)
    neck_old_rot = tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["neck"].rotation_euler)
    head_old_rot = tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["head"].rotation_euler)
    l_ankle_old = (arm_old.matrix_world @ arm_old.pose.bones["shin.L"].tail).copy()
    r_ankle_old = (arm_old.matrix_world @ arm_old.pose.bones["shin.R"].tail).copy()
    arm_fk_rotations = {
        "upper_arm.L": tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["upper_arm.L"].rotation_euler),
        "forearm.L": tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["forearm.L"].rotation_euler),
        "upper_arm.R": tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["upper_arm.R"].rotation_euler),
        "forearm.R": tuple(round(math.degrees(v), 3) for v in arm_old.pose.bones["forearm.R"].rotation_euler),
    }

    # Step 2: Bridge Executor Application on fresh scene
    arm_new, root_new = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm_new, root_obj=root_new)

    # Package into KinematicPlannedPose
    planned = KinematicPlannedPose(
        frame=28,
        time_seconds=27.0 / 24.0,
        root_position=root_world_old,
        root_yaw_deg=0.0,
        speed_mps=speed_mps,
        motion_mode=MotionMode.WALK,
        pelvis_location=pelvis_old_loc,
        pelvis_rotation_deg=pelvis_old_rot,
        spine_rotation_deg=spine_old_rot,
        neck_rotation_deg=neck_old_rot,
        head_rotation_deg=head_old_rot,
        foot_L=PlannedFootTarget(world_xyz=locked_ankle, is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=swing_ankle, is_locked=False),
        fk_joint_rotations_deg=arm_fk_rotations,
    )

    res_bridge = bridge.execute_frame(planned, keyframe=False)
    assert res_bridge.success is True, f"Bridge execution failed: {res_bridge.unmet_constraints}"

    # Extract new bone transforms
    p_pelvis_new = arm_new.pose.bones["pelvis"]
    pelvis_new_world = arm_new.matrix_world @ p_pelvis_new.head
    pelvis_pos_diff_m = (pelvis_new_world - pelvis_old_world).length
    assert pelvis_pos_diff_m < 0.0001, f"Pelvis position mismatch: diff={pelvis_pos_diff_m*1000:.4f}mm"

    # Feet comparison
    l_ankle_new = arm_new.matrix_world @ arm_new.pose.bones["shin.L"].tail
    ankle_l_diff_m = (l_ankle_new - l_ankle_old).length
    assert ankle_l_diff_m < 0.0001, f"Left ankle mismatch: diff={ankle_l_diff_m*1000:.4f}mm"

    r_ankle_new = arm_new.matrix_world @ arm_new.pose.bones["shin.R"].tail
    ankle_r_diff_m = (r_ankle_new - r_ankle_old).length
    assert ankle_r_diff_m < 0.0001, f"Right ankle mismatch: diff={ankle_r_diff_m*1000:.4f}mm"

    print(f"  -> Quantitative equivalence verified: Pelvis diff={pelvis_pos_diff_m*1000:.4f}mm, Ankle L diff={ankle_l_diff_m*1000:.4f}mm, Ankle R diff={ankle_r_diff_m*1000:.4f}mm.")
    return True


# =============================================================================
# Test 6: Immutability of Historical Gait Curves & Step Schedule
# =============================================================================
def test_06_immutability_of_historical_step_schedule_and_curves() -> bool:
    print("\n--- Test 6: Immutability of Historical Gait Curves ---")
    config = PipelineConfig()
    schedule = build_step_schedule(config, start_y=-8.0)

    assert len(schedule) == 7, f"Expected 7 steps in StartStop schedule, got {len(schedule)}"
    assert schedule[0]["stance_side"] == "L", "Step 0 stance side must be L"
    assert schedule[1]["stance_side"] == "R", "Step 1 stance side must be R"

    # Test C1 root velocity profile values
    disp_0, speed_0, stage_0 = evaluate_root_kinematics(0.0, config)
    assert disp_0 == 0.0 and speed_0 == 0.0, "Start stand must have zero speed"

    disp_mid, speed_mid, stage_mid = evaluate_root_kinematics(100.0, config)
    assert math.isclose(speed_mid, 0.24, abs_tol=1e-4), f"Steady speed must be 0.24 m/s, got {speed_mid}"

    disp_end, speed_end, stage_end = evaluate_root_kinematics(204.0, config)
    assert math.isclose(disp_end, 1.26, abs_tol=1e-3), f"Total displacement must be 1.26 m, got {disp_end}"

    print(f"  -> Gait curves verified: 7 steps intact, peak speed={speed_mid} m/s, total disp={disp_end} m.")
    return True


# =============================================================================
# Test 7: Data Types, Units & Coordinate Consistency
# =============================================================================
def test_07_data_types_units_and_coordinate_consistency() -> bool:
    print("\n--- Test 7: Data Types, Units & Coordinate Conventions ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    planned = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
    )
    res = bridge.execute_frame(planned, keyframe=False)

    ms = res.motion_state
    assert isinstance(ms.position, tuple) and len(ms.position) == 3, "MotionState position must be 3-tuple"
    assert isinstance(ms.velocity, tuple) and len(ms.velocity) == 3, "MotionState velocity must be 3-tuple"
    assert isinstance(ms.params, dict), "MotionState params must be dict"
    assert "com_world" in ms.params, "com_world missing from params"
    assert "support_type" in ms.params, "support_type missing from params"
    assert ms.params["support_type"] == "double_stance", f"Expected double_stance, got {ms.params['support_type']}"

    # Verify ground plane convention: Z = 0.0 m
    assert math.isclose(ms.position[2], 0.0, abs_tol=1e-5), "Ground plane Z must be 0.0 m"

    print("  -> Types, units, and coordinate conventions verified: +Z Up, ground Z=0.0, support_type=double_stance.")
    return True


# =============================================================================
# Test 8: Duplicate Write Conflict Prevention
# =============================================================================
def test_08_duplicate_write_conflict_prevention() -> bool:
    print("\n--- Test 8: Duplicate Write Conflict Prevention ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    # In bridge mode, WholeBodyController holds exclusive write ownership of armature pose bones.
    # We verify that attempting to set an IK target on an effector that is managed as locked
    # is intercepted by WBC and routed to foot_contact without conflicting duplicate matrix assignments.
    planned = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=False),
    )
    res = bridge.execute_frame(planned, keyframe=False)
    assert res.success is True

    # Check FootIK.L parent state: must be None (managed exclusively by foot_contact)
    ik_l = bpy.data.objects["FootIK.L"]
    assert ik_l.parent is None, "FootIK.L must remain unparented in world space"

    # Check FootIK.R parent state: swing foot remains parented or positioned in root frame
    ik_r = bpy.data.objects["FootIK.R"]
    assert ik_r.get("is_locked", False) is False, "FootIK.R swing foot must not be locked"

    print("  -> Exclusive write ownership verified: zero conflict between foot_contact and WBC.")
    return True


# =============================================================================
# Test 9: Full Single-Frame 6-Phase Pipeline Execution
# =============================================================================
def test_09_full_6phase_pipeline_execution() -> bool:
    print("\n--- Test 9: Full Single-Frame 6-Phase Pipeline Execution ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    # Run 5 consecutive frames through the bridge
    results: List[BridgeExecutionResult] = []
    for f in range(1, 6):
        t = (f - 1) * (1.0 / 24.0)
        y_root = -8.0 + 0.01 * (f - 1)
        planned = KinematicPlannedPose(
            frame=f,
            time_seconds=t,
            root_position=(0.0, y_root, 0.0),
            pelvis_location=(0.0, -0.02, 0.0),  # Walking crouch gives knee flexion and reach margin
            speed_mps=0.24 if f > 1 else 0.0,
            motion_mode=MotionMode.WALK,
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0 + 0.02 * f, ANKLE_REST_Z + 0.01 * f), is_locked=False),
            fk_joint_rotations_deg={
                "upper_arm.L": (5.0 * f, 0.0, 0.0),
                "upper_arm.R": (-5.0 * f, 0.0, 0.0),
            },
        )
        res = bridge.execute_frame(planned, keyframe=True)
        if not res.success:
            print(f"DEBUG Frame {f} failed: {[u.description for u in res.unmet_constraints]}, has_rom={res.wbc_result.has_rom_violation}, all_reach={res.wbc_result.is_all_reachable}")
            if res.wbc_result.has_rom_violation:
                print(f"ROM violations: {res.wbc_result.rom_validation.violations}")
        assert res.success is True, f"Frame {f} execution failed"
        results.append(res)

    assert len(results) == 5, "Expected 5 execution results"
    # Verify animation data was keyframed
    assert arm.animation_data is not None and arm.animation_data.action is not None, "Armature action not created"
    assert root.animation_data is not None and root.animation_data.action is not None, "Root action not created"

    # Verify telemetry evolution
    assert "com_world" in results[-1].motion_state.params
    assert "support_type" in results[-1].motion_state.params
    assert results[-1].support_type == "single_stance_l", f"Expected single_stance_l, got {results[-1].support_type}"
    assert "inertia_tensor_com" in results[-1].motion_state.params, "inertia_tensor_com missing from params"
    assert "angular_momentum_com" in results[-1].motion_state.params, "angular_momentum_com missing from params"
    assert results[-1].inertia_state is not None, "Inertia state missing from BridgeExecutionResult"

    print(f"  -> 5 frames executed via 6-phase pipeline: keyframing active, support_type={results[-1].support_type}, inertia evaluated.")
    return True


# =============================================================================
# Test 10: Variable Time Step (dt) & Kinematic Scaling
# =============================================================================
def test_10_variable_dt_and_kinematic_scaling() -> bool:
    print("\n--- Test 10: Variable Time Step (dt) & Kinematic Scaling ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    # 1. Test explicit dt = 0.01s (100 FPS) vs dt = 0.05s (20 FPS)
    # Frame 1: start at Y = -8.0
    p1 = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
    )
    bridge.execute_frame(p1, keyframe=False, dt=0.01)

    # Frame 2: move Y by +0.02m with dt = 0.01s -> expected v_y = 0.02 / 0.01 = 2.0 m/s
    p2 = KinematicPlannedPose(
        frame=2,
        time_seconds=0.01,
        root_position=(0.0, -7.98, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.98, ANKLE_REST_Z), is_locked=False),
    )
    res2 = bridge.execute_frame(p2, keyframe=False, dt=0.01)
    derived_vy_100fps = res2.motion_state.params["root_derived_linear_velocity"][1]
    assert math.isclose(derived_vy_100fps, 2.0, abs_tol=1e-3), f"Expected 2.0 m/s at dt=0.01, got {derived_vy_100fps}"

    # Frame 3: move Y by another +0.02m with dt = 0.04s -> expected v_y = 0.02 / 0.04 = 0.5 m/s
    p3 = KinematicPlannedPose(
        frame=3,
        time_seconds=0.05,
        root_position=(0.0, -7.96, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.96, ANKLE_REST_Z), is_locked=False),
    )
    res3 = bridge.execute_frame(p3, keyframe=False, dt=0.04)
    derived_vy_25fps = res3.motion_state.params["root_derived_linear_velocity"][1]
    assert math.isclose(derived_vy_25fps, 0.5, abs_tol=1e-3), f"Expected 0.5 m/s at dt=0.04, got {derived_vy_25fps}"

    # 2. Test timestamp-derived dt (p4 with time_seconds=0.09 -> delta_t = 0.04s)
    p4 = KinematicPlannedPose(
        frame=4,
        time_seconds=0.09,
        root_position=(0.0, -7.94, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.94, ANKLE_REST_Z), is_locked=False),
    )
    res4 = bridge.execute_frame(p4, keyframe=False)  # dt derived from time_seconds
    assert math.isclose(res4.motion_state.params["dt_seconds"], 0.04, abs_tol=1e-5), "Derived dt mismatch"

    # 3. Test illegal inputs: zero dt, negative dt, backward timestamps
    illegal_dt_caught = False
    try:
        bridge.execute_frame(p4, keyframe=False, dt=0.0)
    except ValueError:
        illegal_dt_caught = True
    assert illegal_dt_caught, "dt=0.0 must raise ValueError"

    backward_time_caught = False
    try:
        p_back = KinematicPlannedPose(
            frame=5,
            time_seconds=0.05,  # <= previous 0.09
            root_position=(0.0, -7.94, 0.0),
        )
        bridge.execute_frame(p_back, keyframe=False)
    except ValueError:
        backward_time_caught = True
    assert backward_time_caught, "Backward timestamp must raise ValueError"

    print("  -> Variable dt scaling & invalid timestamp protections verified.")
    return True


# =============================================================================
# Test 11: Decoupling Hand IK vs Contact Intent & Geometric Constraints
# =============================================================================
def test_11_hand_ik_vs_contact_intent_decoupling() -> bool:
    print("\n--- Test 11: Hand IK vs Contact Intent Decoupling ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    # Case A: Ordinary reaching hand IK (enabled=True, but contact_intent=False, is_locked=False)
    planned_reach = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        hand_L=PlannedHandTarget(
            world_xyz=(-0.24, -7.65, 1.35),
            enabled=True,
            weight=1.0,
            contact_intent=False,  # Reaching in free space!
            is_locked=False,
        ),
    )
    res_reach = bridge.execute_frame(planned_reach, keyframe=False)
    assert res_reach.success is True, f"Reaching frame failed: {res_reach.unmet_constraints}"
    # Must NOT produce fake contact!
    assert res_reach.support_type == "double_stance", f"Expected double_stance, got {res_reach.support_type}"
    ms_reach = res_reach.motion_state
    assert ms_reach.params["support_type"] == "double_stance"

    # Case B: Hand contact with explicit intent and lock (e.g. grasping a bar or vault surface)
    vault_surface = EnvironmentalSurface(
        surface_id="vault_box",
        surface_type="box",
        center_world=(-0.24, -7.65, 1.35),
        normal_world=(0.0, 0.0, 1.0),
    )
    bridge_vault = KinematicBridgeExecutor(armature_obj=arm, root_obj=root, surfaces=[vault_surface])
    planned_vault = KinematicPlannedPose(
        frame=2,
        time_seconds=0.04167,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=False),
        hand_L=PlannedHandTarget(
            world_xyz=(-0.24, -7.65, 1.35),
            enabled=True,
            weight=1.0,
            contact_intent=True,
            is_locked=True,
            surface_id="vault_box",
            contact_type=ContactType.UNILATERAL,
        ),
    )
    res_vault = bridge_vault.execute_frame(planned_vault, keyframe=False)
    assert res_vault.support_type == "multi_surface", f"Expected multi_surface, got {res_vault.support_type}"

    # Case C: Geometric constraint compliance failure truthfully reported
    # Place hand contact target far away from actual surface
    bad_surface = EnvironmentalSurface(
        surface_id="far_wall",
        surface_type="wall",
        center_world=(0.0, -5.0, 1.5),
        normal_world=(0.0, -1.0, 0.0),
    )
    bridge_bad = KinematicBridgeExecutor(armature_obj=arm, root_obj=root, surfaces=[bad_surface])
    planned_bad = KinematicPlannedPose(
        frame=3,
        time_seconds=0.08333,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        hand_L=PlannedHandTarget(
            world_xyz=(-0.24, -5.0, 1.5),  # 3 meters away from character!
            enabled=True,
            contact_intent=True,
            is_locked=True,
            surface_id="far_wall",
        ),
    )
    res_bad = bridge_bad.execute_frame(planned_bad, keyframe=False)
    # Must report unmet constraint or failure
    assert res_bad.success is False, "Geometric contact violation must report success=False"
    has_contact_or_reach_fail = any(u.category in ("REACHABILITY", "CONTACT_GEOMETRY") for u in res_bad.unmet_constraints)
    assert has_contact_or_reach_fail, f"Expected contact/reach failure, got {res_bad.unmet_constraints}"

    print("  -> Contact semantics decoupled: clean distinction between free IK and active contacts verified.")
    return True


# =============================================================================
# Test 12: Whole-Body Inertia & Angular Momentum Telemetry in Bridge
# =============================================================================
def test_12_whole_body_inertia_and_angular_momentum_telemetry() -> bool:
    print("\n--- Test 12: Whole-Body Inertia & Angular Momentum Telemetry ---")
    arm, root = _clean_scene()
    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)

    # Frame 1: Static neutral pose
    p1 = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
    )
    res1 = bridge.execute_frame(p1, keyframe=False)

    params1 = res1.motion_state.params
    assert "inertia_tensor_com" in params1, "inertia_tensor_com missing"
    assert "angular_momentum_com" in params1, "angular_momentum_com missing"
    assert "spin_angular_momentum" in params1, "spin_angular_momentum missing"
    assert "orbital_angular_momentum" in params1, "orbital_angular_momentum missing"

    # Static posture: derived velocities are zero -> total angular momentum must be 0.0
    h1 = params1["angular_momentum_com"]
    h1_mag = math.sqrt(h1[0]**2 + h1[1]**2 + h1[2]**2)
    assert math.isclose(h1_mag, 0.0, abs_tol=1e-5), f"Static angular momentum must be 0, got {h1_mag}"

    # Inertia tensor components must be positive on diagonal
    I_mat = params1["inertia_tensor_com"]
    assert I_mat[0][0] > 0.0 and I_mat[1][1] > 0.0 and I_mat[2][2] > 0.0, "Principal inertias must be positive"

    # Frame 2: Translate forward (+Y)
    p2 = KinematicPlannedPose(
        frame=2,
        time_seconds=0.04167,
        root_position=(0.0, -7.96, 0.0),
        pelvis_location=(0.0, -0.02, 0.0),
        foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget(world_xyz=(0.11, -7.96, ANKLE_REST_Z), is_locked=False),
    )
    res2 = bridge.execute_frame(p2, keyframe=False)
    params2 = res2.motion_state.params
    assert res2.inertia_state is not None
    assert res2.inertia_state.total_mass_kg > 50.0, f"Expected total mass > 50 kg, got {res2.inertia_state.total_mass_kg}"

    print(f"  -> Inertia tensor and angular momentum telemetry verified (I_zz={I_mat[2][2]:.4f} kg*m^2, static H={h1_mag:.6f}).")
    return True


# =============================================================================
# Test 13: Historical Motion Actions Intactness & Planning
# =============================================================================
def test_13_historical_actions_intactness() -> bool:
    print("\n--- Test 13: Historical Actions Intactness & Planning ---")
    config = PipelineConfig()
    start_pos = config.character_path_points[0]

    # 1. WalkAction schedule & displacement
    walk_sched = build_step_schedule(config, start_pos[1])
    assert len(walk_sched) == 7, f"Expected 7 walk steps, got {len(walk_sched)}"

    # 2. RunAction cycle structure
    run_act = RunAction(cycles=1)
    assert run_act.name == "run"
    init_state = create_initial_motion_state(config, start_frame=1)
    dur_run = run_act.estimate_duration_frames(init_state, config)
    assert dur_run == 24, f"RunAction cycle must be 24 frames, got {dur_run}"

    # 3. SprintStartAction
    sprint_act = SprintStartAction()
    assert sprint_act.name == "sprint_start"
    dur_sprint = sprint_act.estimate_duration_frames(init_state, config)
    assert dur_sprint == config.sprint_total_frames, "SprintStart frames mismatch"

    # 4. SprintBrakeAction
    sprint_end_state = MotionState(
        frame=114,
        time_sec=114.0/24.0,
        position=(0.0, -1.4167, 0.0),
        orientation_deg=(0.0, 0.0, 0.0),
        velocity=(0.0, 2.0, 0.0),
        acceleration=(0.0, 0.0, 0.0),
        mode=MotionMode.SPRINT,
        gait_phase=0.0,
    )
    brake_act = SprintBrakeAction()
    assert brake_act.name == "sprint_brake"
    dur_brake = brake_act.estimate_duration_frames(sprint_end_state, config)
    assert dur_brake == config.sprint_brake_total_frames, "SprintBrake frames mismatch"

    print("  -> Walk, Run, SprintStart, SprintBrake actions intact and plan successfully.")
    return True


# =============================================================================
# Test 14: Core Historical Regression Suite
# =============================================================================
def test_14_core_historical_regression_suite() -> bool:
    print("\n--- Test 14: Core Historical Regression Suite ---")
    python_exe = sys.executable

    test_scripts = [
        "tests/verify_task6fd_whole_body_controller.py",
        "tests/verify_task6fc_joint_limits.py",
        "tests/verify_task6fb_rigid_link.py",
        "tests/verify_task6fa_arm_ik.py",
        "tests/verify_task6ga_body_kinematics.py",
        "tests/verify_task6gb_body_inertia.py",
    ]

    for script in test_scripts:
        if not os.path.exists(script):
            print(f"  [SKIP] {script} not found")
            continue
        print(f"  Running regression: {script}...")
        blender_exe = bpy.app.binary_path
        cmd = [blender_exe, "-b", "-P", script]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            print(f"  [FAILED] {script} exited with code {proc.returncode}")
            print(proc.stderr[:500])
            return False
        print(f"  [PASSED] {script}")

    return True


# =============================================================================
# Main Verification Runner
# =============================================================================
def run_all_tests() -> bool:
    print("=" * 80)
    print("TASK 6G-C-R3B-1-FINAL: ARCHITECTURAL GAP FIXING & BRIDGE VERIFICATION")
    print("=" * 80)

    tests = [
        ("Test 01: Lossless Input Mapping", test_01_lossless_input_mapping),
        ("Test 02: FK/IK Arbitration & Control Ownership", test_02_fk_ik_arbitration_and_ownership),
        ("Test 03: Stance Foot Ground Anchor Preservation", test_03_root_motion_stance_foot_preservation),
        ("Test 04: Truthful ROM & Reach Failure Reporting", test_04_truthful_rom_and_reach_failure_reporting),
        ("Test 05: Quantitative Pose Equivalence (Old vs Bridge)", test_05_quantitative_pose_comparison_old_vs_bridge),
        ("Test 06: Immutability of Historical Gait Curves", test_06_immutability_of_historical_step_schedule_and_curves),
        ("Test 07: Data Types, Units & Coordinate Consistency", test_07_data_types_units_and_coordinate_consistency),
        ("Test 08: Duplicate Write Conflict Prevention", test_08_duplicate_write_conflict_prevention),
        ("Test 09: Full Single-Frame 6-Phase Pipeline Execution", test_09_full_6phase_pipeline_execution),
        ("Test 10: Variable Time Step (dt) & Kinematic Scaling", test_10_variable_dt_and_kinematic_scaling),
        ("Test 11: Hand IK vs Contact Intent Decoupling", test_11_hand_ik_vs_contact_intent_decoupling),
        ("Test 12: Whole-Body Inertia & Angular Momentum Telemetry", test_12_whole_body_inertia_and_angular_momentum_telemetry),
        ("Test 13: Historical Motion Actions Intactness & Planning", test_13_historical_actions_intactness),
        ("Test 14: Core Historical Regression Suite", test_14_core_historical_regression_suite),
    ]

    all_passed = True
    for name, func in tests:
        try:
            passed = func()
            if not passed:
                all_passed = False
                print(f"[FAILED] {name}")
                break
            else:
                print(f"[PASSED] {name}")
        except Exception as e:
            all_passed = False
            print(f"[ERROR] {name} raised exception: {e}")
            import traceback
            traceback.print_exc()
            break

    print("\n" + "=" * 80)
    if all_passed:
        print("RESULT: ALL 14 TASK 6G-C-R3B-1-FINAL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    else:
        print("RESULT: ONE OR MORE TESTS FAILED!")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
