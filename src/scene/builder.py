"""Scene builder module for configuring environment and render parameters."""

import bpy
from src.config import PipelineConfig

def setup_scene(config: PipelineConfig) -> bpy.types.Scene:
    """Initialize clean scene and apply timeline and resolution settings from config."""
    # Reset factory settings with empty scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "ProceduralAnimScene"

    # Set timeline parameters
    scene.render.fps = config.fps
    scene.frame_start = config.frame_start
    scene.frame_end = config.frame_end
    scene.frame_current = config.frame_start

    # Set output dimensions
    scene.render.resolution_x = config.resolution_x
    scene.render.resolution_y = config.resolution_y
    scene.render.resolution_percentage = config.resolution_percentage

    # Add a minimal reference calibration cube for pipeline verification
    # Note: This is an infrastructure marker only, not a formal character or asset.
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.5))
    marker = bpy.context.active_object
    marker.name = "PipelineReferenceMarker"

    return scene
