"""Camera controller module for framing and camera transforms."""

import bpy
from src.config import PipelineConfig

def setup_camera(config: PipelineConfig, scene: bpy.types.Scene = None) -> bpy.types.Object:
    """Create basic camera and set it as active scene camera."""
    if scene is None:
        scene = bpy.context.scene

    bpy.ops.object.camera_add(location=(4.0, -4.0, 3.0), rotation=(1.1, 0.0, 0.785))
    cam = bpy.context.active_object
    cam.name = "PipelineCamera"
    cam.data.lens = 50.0  # standard 50mm lens
    scene.camera = cam
    return cam
