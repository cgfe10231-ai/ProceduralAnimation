"""Verification of StartStopWalkAction migration to KinematicBridgeExecutor (Task 6G-C-R3B-2 Phase A)."""

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


def verify_walk_migration():
    print("=" * 80)
    print("VERIFYING STARTSTOPWALKACTION MIGRATION TO KINEMATICBRIDGEEXECUTOR")
    print("=" * 80)

    config = PipelineConfig()
    arm, root = _clean_scene()

    planner = MotionPlanner(config, armature_obj=arm)
    walk_action = StartStopWalkAction()
    planner.add_action(walk_action)

    print("Executing StartStopWalkAction via MotionPlanner...")
    plan_result = planner.execute()

    total_frames = plan_result["total_frames"]
    assert total_frames == 204, f"Expected 204 frames, got {total_frames}"

    action_res = plan_result["action_results"][0]
    assert action_res.action_name == "start_stop_walk"
    assert action_res.unreachable_count == 0, f"Unreachable count must be 0, got {action_res.unreachable_count}"

    states = action_res.states
    assert len(states) == 204, f"Expected 204 states, got {len(states)}"

    # 1. Root displacement check
    init_y = states[0].position[1]
    final_y = states[-1].position[1]
    disp = final_y - init_y
    assert math.isclose(init_y, -8.0, abs_tol=1e-4), f"Initial Y must be -8.0, got {init_y}"
    assert math.isclose(final_y, -6.74, abs_tol=1e-4), f"Final Y must be -6.74, got {final_y}"
    assert math.isclose(disp, 1.26, abs_tol=1e-4), f"Total displacement must be 1.26m, got {disp}"
    print(f"  [OK] Root displacement: {init_y:.4f}m -> {final_y:.4f}m (disp={disp:.4f}m)")

    # 2. Velocity profile check
    peak_speed = plan_result["peak_speed_mps"]
    assert math.isclose(peak_speed, 0.24, abs_tol=1e-3), f"Peak speed must be 0.24 m/s, got {peak_speed}"
    assert math.isclose(states[0].speed_mps, 0.0, abs_tol=1e-4), "Start speed must be 0.0"
    assert math.isclose(states[-1].speed_mps, 0.0, abs_tol=1e-4), "Stop speed must be 0.0"
    print(f"  [OK] Speed profile: start=0.0, peak={peak_speed:.4f}m/s, stop=0.0")

    # 3. Telemetry and distinct velocity fields check (Requirement 1 & 2)
    sample_state = states[100]  # in steady walk
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
    print(f"  [OK] Velocity telemetry: planned={v_plan}, derived={v_derived}, com={v_com}")
    assert math.isclose(v_plan[1], 0.24, abs_tol=1e-3), "Steady planned velocity must be 0.24 m/s"
    assert math.isclose(v_derived[1], 0.24, abs_tol=1e-2), f"Derived root velocity should match planned, got {v_derived}"

    # 4. Multi-action chaining check
    print("Testing 2-action chaining...")
    arm2, root2 = _clean_scene()
    planner2 = MotionPlanner(config, armature_obj=arm2)
    planner2.add_action(StartStopWalkAction())
    planner2.add_action(StartStopWalkAction())
    chain_result = planner2.execute()

    assert chain_result["total_frames"] == 408, f"Expected 408 frames, got {chain_result['total_frames']}"
    assert chain_result["unreachable_count"] == 0, f"Unreachable count must be 0, got {chain_result['unreachable_count']}"
    assert math.isclose(chain_result["total_root_displacement"], 2.52, abs_tol=1e-4), "Total chained displacement mismatch"
    print(f"  [OK] Chaining 2 walk actions: frames 1..408, total disp = {chain_result['total_root_displacement']:.4f}m")

    print("\n" + "=" * 80)
    print("RESULT: STARTSTOPWALKACTION MIGRATION TO KINEMATICBRIDGEEXECUTOR PASSED 100%!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = verify_walk_migration()
    sys.exit(0 if success else 1)
