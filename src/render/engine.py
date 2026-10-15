"""Render configuration and execution module."""

import bpy
from src.config import PipelineConfig

def configure_render(config: PipelineConfig, scene: bpy.types.Scene = None):
    """Apply rendering parameters from config."""
    if scene is None:
        scene = bpy.context.scene

    scene.render.engine = config.render_engine
    scene.render.image_settings.file_format = config.file_format
    scene.render.image_settings.color_mode = config.color_mode
    scene.render.filepath = config.preview_image_path

def save_blend_file(config: PipelineConfig) -> str:
    """Save the active Blender scene to .blend file specified in config."""
    path = config.blend_file_path
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return path

def render_still(config: PipelineConfig, frame: int = 1) -> str:
    """Render a single frame still according to config settings."""
    scene = bpy.context.scene
    scene.frame_set(frame)
    path = config.preview_image_path
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path
