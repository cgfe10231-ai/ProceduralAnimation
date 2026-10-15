"""Verification module for checking pipeline output integrity."""

import os
import struct
import bpy
from src.config import PipelineConfig

def get_png_dimensions(filepath: str):
    """Extract width and height from PNG binary header (IHDR chunk)."""
    with open(filepath, "rb") as f:
        header = f.read(24)
        if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n':
            return None, None
        width, height = struct.unpack(">II", header[16:24])
        return width, height

def verify_pipeline_outputs(config: PipelineConfig) -> dict:
    """Validate all generated assets and scene settings against config."""
    results = {}
    
    # 1. Verify Scene Timeline & Resolution
    scene = bpy.context.scene
    if scene.render.fps != config.fps:
        raise ValueError(f"FPS mismatch: expected {config.fps}, got {scene.render.fps}")
    if scene.frame_start != config.frame_start or scene.frame_end != config.frame_end:
        raise ValueError(f"Frame range mismatch: expected {config.frame_start}..{config.frame_end}, got {scene.frame_start}..{scene.frame_end}")
    if scene.render.resolution_x != config.resolution_x or scene.render.resolution_y != config.resolution_y:
        raise ValueError(f"Resolution mismatch: expected {config.resolution_x}x{config.resolution_y}, got {scene.render.resolution_x}x{scene.render.resolution_y}")
    
    results["scene_settings"] = {
        "fps": scene.render.fps,
        "frame_range": (scene.frame_start, scene.frame_end),
        "total_frames": scene.frame_end - scene.frame_start + 1,
        "resolution": (scene.render.resolution_x, scene.render.resolution_y)
    }

    # 2. Verify .blend artifact
    blend_path = config.blend_file_path
    if not os.path.isfile(blend_path):
        raise FileNotFoundError(f".blend file was not created: {blend_path}")
    blend_size = os.path.getsize(blend_path)
    if blend_size <= 0:
        raise ValueError(f".blend file is empty (0 bytes): {blend_path}")
    results["blend_file"] = {"path": blend_path, "size_bytes": blend_size}

    # 3. Verify render image artifact
    image_path = config.preview_image_path
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Render image was not created: {image_path}")
    img_size = os.path.getsize(image_path)
    if img_size <= 0:
        raise ValueError(f"Render image is empty (0 bytes): {image_path}")

    w, h = get_png_dimensions(image_path)
    if (w, h) != (config.resolution_x, config.resolution_y):
        raise ValueError(f"Render image dimensions mismatch: expected {config.resolution_x}x{config.resolution_y}, got {w}x{h}")
    results["render_image"] = {"path": image_path, "size_bytes": img_size, "dimensions": (w, h)}

    return results
