"""Camera controller module for framing, focal length, target tracking, and keyframing."""

import bpy
from typing import Dict, Tuple
from src.config import PipelineConfig

def setup_camera(config: PipelineConfig, scene: bpy.types.Scene = None) -> Dict[str, bpy.types.Object]:
    """Create reusable camera with Track-To target and baseline keyframe trajectory."""
    if scene is None:
        scene = bpy.context.scene

    # Camera collection
    cam_collection = bpy.data.collections.new("Camera")
    scene.collection.children.link(cam_collection)

    # 1. Create Look-At Target (Empty object)
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0.0, -8.0, 1.0))
    target_obj = bpy.context.active_object
    target_obj.name = "CameraLookAtTarget"
    scene.collection.objects.unlink(target_obj)
    cam_collection.objects.link(target_obj)

    # 2. Create Camera
    bpy.ops.object.camera_add(location=(10.0, -14.0, 7.0))
    cam = bpy.context.active_object
    cam.name = "PipelineCamera"
    cam.data.lens = config.camera_focal_length
    scene.camera = cam
    scene.collection.objects.unlink(cam)
    cam_collection.objects.link(cam)

    # 3. Add Track-To constraint pointing at target_obj
    track_constraint = cam.constraints.new(type='TRACK_TO')
    track_constraint.target = target_obj
    track_constraint.track_axis = 'TRACK_NEGATIVE_Z'
    track_constraint.up_axis = 'UP_Y'

    # 4. Keyframe motion: Wide overview at Frame 1 -> Tracking mid-path at Frame 180 -> Tracking exit at Frame 360
    # Frame 1: Establishing view of character start/stand area
    cam.location = (10.0, -14.0, 7.0)
    target_obj.location = (0.0, -8.0, 1.0)
    cam.keyframe_insert(data_path="location", frame=config.frame_start)
    target_obj.keyframe_insert(data_path="location", frame=config.frame_start)

    # Frame 180: Closer medium framing observing walking & turn area
    cam.location = (8.0, -3.0, 5.0)
    target_obj.location = (0.0, 0.0, 1.0)
    cam.keyframe_insert(data_path="location", frame=180)
    target_obj.keyframe_insert(data_path="location", frame=180)

    # Frame 360: Low tracking shot framing exit trajectory
    cam.location = (6.0, 5.0, 4.5)
    target_obj.location = (3.5, 7.0, 1.0)
    cam.keyframe_insert(data_path="location", frame=config.frame_end)
    target_obj.keyframe_insert(data_path="location", frame=config.frame_end)

    return {"camera": cam, "target": target_obj}

def get_camera_state_at_frame(cam_obj: bpy.types.Object, scene: bpy.types.Scene, frame: int) -> Tuple[tuple, tuple]:
    """Evaluate camera position and rotation at specified frame."""
    scene.frame_set(frame)
    # Force dependency graph evaluation
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_cam = cam_obj.evaluated_get(depsgraph)
    loc = tuple(round(coord, 4) for coord in eval_cam.location)
    rot_euler = tuple(round(math_deg, 4) for math_deg in eval_cam.rotation_euler)
    return loc, rot_euler
