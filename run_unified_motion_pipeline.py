"""Unified Motion Pipeline Integration (Task 6G-C-R3B-2).

Chains all 4 procedural locomotion actions through the unified MotionPlanner,
KinematicBridgeExecutor, and WholeBodyController architecture:
1. StartStopWalkAction (204 frames: Idle -> Accelerate -> Steady Walk -> Decelerate -> Stop)
2. RunAction (96 frames: 4 cycles of running gait with alternating single stance and dual-foot flight)
3. SprintStartAction (114 frames: Static set crouch -> push-off burst -> sprint acceleration)
4. SprintBrakeAction (38 frames: High-speed handoff -> active brake footwork -> stable bilateral stop)

Saves directly playable Blender file: output/unified_motion_integration.blend (452 frames).
"""

import math
import os
import sys
from typing import Any, Dict

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    MotionPlanner,
    StartStopWalkAction,
    create_initial_motion_state,
)
from src.motion.run_cycle import RunAction
from src.motion.sprint_start import SprintStartAction
from src.motion.sprint_brake import SprintBrakeAction
from src.render.engine import configure_render
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik
from src.rig.pose import reset_pose


def setup_camera_and_lighting(config: PipelineConfig):
    """Cleanly create PipelineCamera with Track-To target and sun illumination."""
    scene = bpy.context.scene

    # 1. Look-at Target
    target_obj = bpy.data.objects.new("CameraLookAtTarget", None)
    target_obj.empty_display_type = "PLAIN_AXES"
    target_obj.location = Vector((0.0, -8.0, 0.90))
    scene.collection.objects.link(target_obj)

    # 2. Camera
    cam_data = bpy.data.cameras.new("PipelineCameraData")
    cam_data.lens = config.camera_focal_length
    cam_obj = bpy.data.objects.new("PipelineCamera", cam_data)
    cam_obj.location = Vector((-3.60, -11.20, 1.85))
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    # 3. Track-To constraint pointing at target_obj
    track = cam_obj.constraints.new(type="TRACK_TO")
    track.target = target_obj
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    # 4. Sun light for viewport clarity
    light_data = bpy.data.lights.new(name="PipelineSunLight", type="SUN")
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new("PipelineSunLight", light_data)
    light_obj.location = Vector((5.0, -10.0, 10.0))
    light_obj.rotation_euler = (math.radians(45.0), math.radians(15.0), math.radians(30.0))
    scene.collection.objects.link(light_obj)

    return cam_obj, target_obj


def build_unified_scene(config: PipelineConfig):
    """Set up character, armature, leg IK, arm IK, ground plane, lighting, and camera."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh, do_unlink=True)
    for arm in list(bpy.data.armatures):
        bpy.data.armatures.remove(arm, do_unlink=True)

    # 1. Ground plane at Z=0.0
    bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0.0, 0.0, 0.0))
    ground_obj = bpy.context.active_object
    ground_obj.name = "GroundPlane"

    # 2. Character & Rig
    build_character(config)
    arm_obj = build_rig(config)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    root_obj = arm_obj.parent or bpy.data.objects.get("CharacterRoot")
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj)

    # 3. Camera & Lighting
    setup_camera_and_lighting(config)

    bpy.context.view_layer.update()
    return arm_obj, root_obj


def run_unified_motion_pipeline(config: PipelineConfig = None) -> Dict[str, Any]:
    if config is None:
        config = PipelineConfig()

    print("=" * 80)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 6G-C-R3B-2 UNIFIED MOTION INTEGRATION")
    print("=" * 80)

    arm_obj, root_obj = build_unified_scene(config)

    planner = MotionPlanner(config, armature_obj=arm_obj)
    planner.add_action(StartStopWalkAction())
    planner.add_action(SprintStartAction())
    planner.add_action(SprintBrakeAction())
    planner.add_action(RunAction(cycles=4))

    print("\n[PLANNER] Executing unified 4-action sequence via KinematicBridgeExecutor...")
    plan_result = planner.execute()

    total_frames = plan_result["total_frames"]
    unreachable = plan_result["unreachable_count"]
    print(f"\n[PLANNER] Completed: {total_frames} frames, {unreachable} unreachable events.")

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = config.fps

    # Configure camera and smooth tracking target across 452 frames
    configure_render(config)
    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")

    if cam_obj and target_obj:
        if cam_obj.animation_data:
            cam_obj.animation_data_clear()
        if target_obj.animation_data:
            target_obj.animation_data_clear()

        # Keyframe camera tracking smoothly following character
        all_records = plan_result["frame_records"]
        for r in all_records:
            f = r["frame"]
            if f == 1 or f == total_frames or f % 12 == 0:
                scene.frame_set(f)
                ry = r["root_y"]
                target_obj.location = Vector((0.0, ry, 0.90))
                cam_obj.location = Vector((-3.60, ry - 3.20, 1.85))
                target_obj.keyframe_insert("location", frame=f)
                cam_obj.keyframe_insert("location", frame=f)

    scene.frame_set(1)
    bpy.context.view_layer.update()

    out_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(out_dir, exist_ok=True)
    blend_path = os.path.join(out_dir, "unified_motion_integration.blend")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"\n[OUTPUT] Unified motion integration blend saved: {blend_path}")
    print(f"[OUTPUT] File size: {os.path.getsize(blend_path)} bytes")
    print("=" * 80)
    print("R3B-2 UNIFIED MOTION INTEGRATION PIPELINE COMPLETED SUCCESSFULLY!")
    print("=" * 80)

    return {
        "total_frames": total_frames,
        "unreachable_count": unreachable,
        "blend_path": blend_path,
        "action_names": [res.action_name for res in plan_result["action_results"]],
        "total_displacement": plan_result["total_root_displacement"],
    }


if __name__ == "__main__":
    run_unified_motion_pipeline()
