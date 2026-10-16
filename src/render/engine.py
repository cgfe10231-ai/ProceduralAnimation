"""Render configuration and execution module."""

import bpy
from typing import List
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

def render_still(config: PipelineConfig, frame: int) -> str:
    """Render a single frame still according to config settings."""
    scene = bpy.context.scene
    scene.frame_set(frame)
    output_path = config.get_preview_image_path(frame)
    scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    return output_path

def render_preview_stills(config: PipelineConfig) -> List[str]:
    """Render all preview frames designated in config."""
    rendered_paths = []
    for frame in config.preview_frames:
        path = render_still(config, frame=frame)
        rendered_paths.append(path)
    return rendered_paths
