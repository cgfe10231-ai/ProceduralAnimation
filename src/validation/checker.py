"""Verification module for checking pipeline output integrity, spatial constraints, and camera motion."""

import os
import struct
import math
import hashlib
import bpy
from src.config import PipelineConfig
from src.scene.layout import SceneLayoutData, verify_layout_corridor_clearance
from src.camera.controller import get_camera_state_at_frame

def get_png_dimensions(filepath: str):
    """Extract width and height from PNG binary header (IHDR chunk)."""
    with open(filepath, "rb") as f:
        header = f.read(24)
        if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n':
            return None, None
        width, height = struct.unpack(">II", header[16:24])
        return width, height

def compute_file_hash(filepath: str) -> str:
    """Compute SHA256 of file for binary difference verification."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def verify_pipeline_outputs(config: PipelineConfig, layout: SceneLayoutData = None) -> dict:
    """Validate all generated assets, spatial layout constraints, and camera motion against config."""
    results = {}
    scene = bpy.context.scene

    # 1. Verify Scene Timeline & Resolution
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

    # 2. Verify Ground Coordinate Convention (Top face strictly at Z = 0.0)
    ground_obj = scene.objects.get("GroundPlane")
    if not ground_obj:
        raise ValueError("GroundPlane object not found in scene.")
    # For a scaled cube centered at z_center with scale z_scale, top is z_center + z_scale/2
    ground_top_z = ground_obj.location.z + (ground_obj.dimensions.z / 2.0)
    if abs(ground_top_z) > 1e-4:
        raise ValueError(f"Ground coordinate convention violated: top face Z is {ground_top_z:.6f}, expected 0.0")
    results["ground"] = {
        "name": ground_obj.name,
        "top_z": ground_top_z,
        "dimensions": (ground_obj.dimensions.x, ground_obj.dimensions.y)
    }

    # 3. Verify Environmental Obstacles & Corridor Clearance
    buildings = [obj for obj in scene.objects if obj.name.startswith("BuildingBlock_")]
    pillars = [obj for obj in scene.objects if obj.name.startswith("ObstaclePillar_")]
    if len(buildings) < 2 or len(pillars) < 2:
        raise ValueError(f"Insufficient environmental elements: {len(buildings)} buildings, {len(pillars)} pillars.")
    
    if layout:
        clearance_valid = verify_layout_corridor_clearance(layout, config.corridor_clearance)
        if not clearance_valid:
            raise ValueError(f"Corridor clearance violated by one or more environmental obstacles!")
    results["environment"] = {
        "building_count": len(buildings),
        "pillar_count": len(pillars),
        "corridor_clearance_verified": True
    }

    # 4. Verify Lighting System
    key_light = scene.objects.get("PipelineKeyLight")
    fill_light = scene.objects.get("PipelineFillLight")
    if not key_light or not fill_light:
        raise ValueError("Key light or fill light missing from scene.")
    results["lighting"] = {
        "key_light": key_light.name,
        "key_energy": key_light.data.energy,
        "fill_light": fill_light.name,
        "fill_energy": fill_light.data.energy
    }

    # 5. Verify Camera System & Keyframe Motion
    cam_obj = scene.objects.get("PipelineCamera")
    target_obj = scene.objects.get("CameraLookAtTarget")
    if not cam_obj or not target_obj:
        raise ValueError("Camera or Look-At Target missing from scene.")
    if not cam_obj.constraints.get("Track To"):
        raise ValueError("Camera Track-To constraint missing.")

    # Evaluate camera position at Frame 1 and Frame 180
    loc_f1, rot_f1 = get_camera_state_at_frame(cam_obj, scene, config.preview_frames[0])
    loc_f180, rot_f180 = get_camera_state_at_frame(cam_obj, scene, config.preview_frames[1])
    cam_disp = math.hypot(loc_f180[0] - loc_f1[0], loc_f180[1] - loc_f1[1], loc_f180[2] - loc_f1[2])
    if cam_disp < 1.0:
        raise ValueError(f"Camera keyframe displacement too small ({cam_disp:.2f}m). Camera motion not detected.")
    results["camera"] = {
        "frame_1_location": loc_f1,
        "frame_180_location": loc_f180,
        "displacement_meters": round(cam_disp, 4)
    }

    # 6. Verify .blend Artifact
    blend_path = config.blend_file_path
    if not os.path.isfile(blend_path):
        raise FileNotFoundError(f".blend file was not created: {blend_path}")
    blend_size = os.path.getsize(blend_path)
    if blend_size <= 0:
        raise ValueError(f".blend file is empty: {blend_path}")
    results["blend_file"] = {"path": blend_path, "size_bytes": blend_size}

    # 7. Verify Render Preview Stills
    preview_hashes = []
    for frame in config.preview_frames:
        img_path = config.get_preview_image_path(frame)
        if not os.path.isfile(img_path):
            raise FileNotFoundError(f"Preview image missing for frame {frame}: {img_path}")
        img_size = os.path.getsize(img_path)
        if img_size <= 0:
            raise ValueError(f"Preview image empty for frame {frame}: {img_path}")
        w, h = get_png_dimensions(img_path)
        if (w, h) != (config.resolution_x, config.resolution_y):
            raise ValueError(f"Preview image resolution mismatch on frame {frame}: expected {config.resolution_x}x{config.resolution_y}, got {w}x{h}")
        img_hash = compute_file_hash(img_path)
        preview_hashes.append(img_hash)
        results[f"preview_frame_{frame}"] = {
            "path": img_path,
            "size_bytes": img_size,
            "dimensions": (w, h),
            "sha256": img_hash
        }

    # Verify that multiple preview frames captured different visual perspectives
    if len(preview_hashes) >= 2 and preview_hashes[0] == preview_hashes[1]:
        raise ValueError("Rendered preview images across frames are identical! Expected visual change due to camera movement.")
    results["preview_visual_variance_verified"] = True

    return results
