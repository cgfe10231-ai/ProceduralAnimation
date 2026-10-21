"""Verification of SprintBrakeAction migration to KinematicBridgeExecutor (Task 6G-C-R3B-2 Phase D)."""

import math
import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    MotionMode,
    MotionPlanner,
    StartStopWalkAction,
    create_initial_motion_state,
)
from src.motion.sprint_start import SprintStartAction
from src.motion.sprint_brake import SprintBrakeAction
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik
from src.rig.pose import reset_pose


def _clean_scene():
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


def verify_sprint_brake_migration():
    print("=" * 80)
    print("VERIFYING SPRINTBRAKEACTION MIGRATION TO KINEMATICBRIDGEEXECUTOR")
    print("=" * 80)

    config = PipelineConfig()
    arm, root = _clean_scene()

    # SprintBrakeAction starts from SPRINT mode (inheriting from SprintStartAction)
    planner = MotionPlanner(config, armature_obj=arm)
    sprint_start = SprintStartAction()
    sprint_brake = SprintBrakeAction()
    planner.add_action(sprint_start)
    planner.add_action(sprint_brake)

    print("Executing SprintStartAction -> SprintBrakeAction via MotionPlanner...")
    plan_result = planner.execute()

    total_expected = config.sprint_total_frames + config.sprint_brake_total_frames
    assert plan_result["total_frames"] == total_expected, f"Expected {total_expected} frames, got {plan_result['total_frames']}"
    assert plan_result["unreachable_count"] == 0, f"Unreachable count must be 0, got {plan_result['unreachable_count']}"

    start_res = plan_result["action_results"][0]
    brake_res = plan_result["action_results"][1]
    assert brake_res.action_name == "sprint_brake"
    assert brake_res.unreachable_count == 0, f"Brake unreachable count: {brake_res.unreachable_count}"

    states = brake_res.states
    assert len(states) == config.sprint_brake_total_frames, f"Expected {config.sprint_brake_total_frames} states, got {len(states)}"

    # 1. Handoff continuity check
    handoff_y = start_res.final_state.position[1]
    brake_init_y = states[0].position[1]
    assert math.isclose(handoff_y, brake_init_y, abs_tol=0.1), f"Root Y continuity: handoff={handoff_y}, brake_init={brake_init_y}"
    print(f"  [OK] Handoff continuity: Y={brake_init_y:.4f}m, speed={states[0].speed_mps:.4f}m/s")

    # 2. Deceleration and stop profile check
    v_init = states[0].speed_mps
    v_final = states[-1].speed_mps
    assert math.isclose(v_init, 2.0, abs_tol=0.1), f"Initial brake speed must be ~2.0 m/s, got {v_init}"
    assert math.isclose(v_final, 0.0, abs_tol=1e-4), f"Final speed must be exactly 0.0 m/s, got {v_final}"
    assert states[-1].mode == MotionMode.STOP, f"Final mode must be STOP, got {states[-1].mode}"
    print(f"  [OK] Deceleration profile: initial={v_init:.4f}m/s -> final={v_final:.4f}m/s (mode={states[-1].mode.value})")

    # 3. Bilateral stance hold at final frame
    final_contacts = states[-1].contacts
    assert final_contacts["foot_L"].is_locked, "Left foot must be locked in final stance"
    assert final_contacts["foot_R"].is_locked, "Right foot must be locked in final stance"
    assert not states[-1].is_airborne, "Character must not be airborne at stop"
    print("  [OK] Bilateral stance lock verified: both feet locked at stop")

    # 4. Telemetry and distinct velocity fields check (Requirement 1 & 2)
    sample_state = states[10]  # active braking frame
    params = sample_state.params
    assert "planned_linear_velocity" in params, "planned_linear_velocity missing"
    assert "root_derived_linear_velocity" in params, "root_derived_linear_velocity missing"
    assert "com_linear_velocity" in params, "com_linear_velocity missing"
    assert "inertia_tensor_com" in params, "inertia_tensor_com missing"
    assert "angular_momentum_com" in params, "angular_momentum_com missing"
    assert "support_type" in params, "support_type missing"

    v_plan = params["planned_linear_velocity"]
    v_derived = params["root_derived_linear_velocity"]
    v_com = params["com_linear_velocity"]
    print(f"  [OK] Telemetry verification: planned={v_plan}, derived={v_derived}, com={v_com}")

    print("\n" + "=" * 80)
    print("ALL SPRINTBRAKEACTION MIGRATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    verify_sprint_brake_migration()
