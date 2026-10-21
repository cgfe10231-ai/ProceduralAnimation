"""Verification of SprintStartAction migration to KinematicBridgeExecutor (Task 6G-C-R3B-2 Phase C)."""

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


def verify_sprint_start_migration():
    print("=" * 80)
    print("VERIFYING SPRINTSTARTACTION MIGRATION TO KINEMATICBRIDGEEXECUTOR")
    print("=" * 80)

    config = PipelineConfig()
    arm, root = _clean_scene()

    planner = MotionPlanner(config, armature_obj=arm)
    sprint_start_action = SprintStartAction()
    planner.add_action(sprint_start_action)

    print("Executing SprintStartAction via MotionPlanner...")
    plan_result = planner.execute()

    total_frames = plan_result["total_frames"]
    assert total_frames == config.sprint_total_frames, f"Expected {config.sprint_total_frames} frames, got {total_frames}"

    action_res = plan_result["action_results"][0]
    assert action_res.action_name == "sprint_start"
    assert action_res.unreachable_count == 0, f"Unreachable count must be 0, got {action_res.unreachable_count}"

    states = action_res.states
    assert len(states) == config.sprint_total_frames, f"Expected {config.sprint_total_frames} states, got {len(states)}"

    # 1. Root displacement & velocity profile check
    init_y = states[0].position[1]
    final_y = states[-1].position[1]
    disp = final_y - init_y
    peak_speed = plan_result["peak_speed_mps"]
    final_speed = states[-1].speed_mps

    assert math.isclose(init_y, -8.0, abs_tol=1e-4), f"Initial Y must be -8.0, got {init_y}"
    assert math.isclose(disp, 6.5833, abs_tol=1e-3), f"Total displacement must be ~6.5833m, got {disp}"
    assert math.isclose(peak_speed, config.sprint_target_speed, abs_tol=1e-3), f"Peak speed must be {config.sprint_target_speed}, got {peak_speed}"
    assert math.isclose(final_speed, config.sprint_target_speed, abs_tol=1e-3), f"Final speed must be {config.sprint_target_speed}, got {final_speed}"
    print(f"  [OK] Root displacement: {init_y:.4f}m -> {final_y:.4f}m (disp={disp:.4f}m)")
    print(f"  [OK] Speed profile: start=0.0m/s -> peak={peak_speed:.4f}m/s -> final={final_speed:.4f}m/s")

    # 2. Airborne frames verification
    airborne_frames = sum(1 for s in states if s.is_airborne)
    assert airborne_frames > 20, f"Expected >20 airborne frames during sprint, got {airborne_frames}"
    print(f"  [OK] Airborne flight frames: {airborne_frames} / {total_frames}")

    # 3. Telemetry and distinct velocity fields check (Requirement 1 & 2)
    sample_state = states[70]  # inside steady sprint phase
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
    assert v_plan[1] > 1.8, "Planned Y velocity should be ~2.0 m/s"
    assert v_derived[1] > 1.8, "Derived Y velocity should be ~2.0 m/s"

    # 4. Multi-action chaining test: WalkAction -> SprintStartAction
    print("\nTesting sequential action chaining: WalkAction -> SprintStartAction...")
    arm2, root2 = _clean_scene()
    planner2 = MotionPlanner(config, armature_obj=arm2)
    planner2.add_action(StartStopWalkAction())
    planner2.add_action(SprintStartAction())
    chain_res = planner2.execute()

    assert chain_res["total_frames"] == 204 + config.sprint_total_frames
    assert chain_res["unreachable_count"] == 0, f"Chained unreachable events: {chain_res['unreachable_count']}"
    walk_res = chain_res["action_results"][0]
    sprint_res = chain_res["action_results"][1]
    assert walk_res.final_state.frame + 1 == sprint_res.initial_state.frame
    print(f"  [OK] Chained 2-action execution: {chain_res['total_frames']} frames, 0 unreachable events")

    print("\n" + "=" * 80)
    print("ALL SPRINTSTARTACTION MIGRATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    verify_sprint_start_migration()
