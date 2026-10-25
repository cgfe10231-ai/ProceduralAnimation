"""Playground Visual Evidence & Exporter Module (Task 7A-1).

Responsible for:
1. Workbench still PNG rendering from designated cameras.
2. Binary inspection and parsing of animated GIF streams.
3. 204-frame continuous 24 FPS GIF rendering from reopened blend files.
4. JSON verification reports export.
"""

from __future__ import annotations

import json
import os
import struct
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import bpy

from src.config import PipelineConfig
from src.motion.start_stop_walk import evaluate_root_kinematics
from src.scene.dynamics_visual_evidence import draw_text_to_numpy, encode_animated_gif


def _render_camera_to_png(
    scene: bpy.types.Scene,
    camera_obj: bpy.types.Object,
    filepath: str,
    res_x: int = 640,
    res_y: int = 480,
) -> None:
    """Render a still PNG from `camera_obj` using BLENDER_WORKBENCH while restoring scene state."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    prev_cam = scene.camera
    prev_engine = scene.render.engine
    prev_x = scene.render.resolution_x
    prev_y = scene.render.resolution_y
    prev_pct = scene.render.resolution_percentage
    prev_path = scene.render.filepath

    try:
        scene.camera = camera_obj
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = res_x
        scene.render.resolution_y = res_y
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
    finally:
        scene.camera = prev_cam
        scene.render.engine = prev_engine
        scene.render.resolution_x = prev_x
        scene.render.resolution_y = prev_y
        scene.render.resolution_percentage = prev_pct
        scene.render.filepath = prev_path


def _load_png_to_numpy_rgba(filepath: str, label_text: Optional[str] = None) -> Tuple[int, int, Any]:
    """Load a rendered PNG via Blender's native `bpy.data.images` into a (H, W, 4) float32 numpy array."""
    import numpy as np

    img = bpy.data.images.load(filepath, check_existing=False)
    try:
        w, h = img.size[0], img.size[1]
        arr = np.empty((h * w * 4,), dtype=np.float32)
        img.pixels.foreach_get(arr)
        arr = arr.reshape((h, w, 4))
        if label_text:
            draw_text_to_numpy(
                arr,
                label_text,
                x=10,
                y=h - 24,
                color=(1.0, 0.95, 0.30),
                scale=2,
                bg_color=(0.08, 0.10, 0.14),
            )
        return w, h, arr
    finally:
        bpy.data.images.remove(img)


def count_gif_frames(filepath: str) -> Dict[str, Any]:
    """Parse a GIF89a file binary stream and return exact frame count, resolution, and frame delays."""
    if not os.path.isfile(filepath):
        return {
            "exists": False,
            "frame_count": 0,
            "width": 0,
            "height": 0,
            "delays_cs": [],
            "file_size_bytes": 0,
        }

    with open(filepath, "rb") as f:
        data = f.read()

    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return {
            "exists": True,
            "valid_header": False,
            "frame_count": 0,
            "width": 0,
            "height": 0,
            "delays_cs": [],
            "file_size_bytes": len(data),
        }

    width, height = struct.unpack("<HH", data[6:10])
    packed = data[10]
    pos = 13
    if packed & 0x80:
        gct_size = 3 * (1 << ((packed & 0x07) + 1))
        pos += gct_size

    frame_count = 0
    delays_cs: List[int] = []
    n = len(data)

    while pos < n:
        block_id = data[pos]
        pos += 1
        if block_id == 0x3B:  # Trailer
            break
        elif block_id == 0x21:  # Extension
            if pos >= n:
                break
            ext_label = data[pos]
            pos += 1
            if ext_label == 0xF9 and pos + 5 <= n:  # Graphic Control Extension
                block_size = data[pos]
                if block_size == 4:
                    delay = struct.unpack("<H", data[pos + 2 : pos + 4])[0]
                    delays_cs.append(delay)
                pos += 1 + block_size + 1  # size byte + data + terminator 0x00
            else:
                while pos < n:
                    sub_len = data[pos]
                    pos += 1
                    if sub_len == 0:
                        break
                    pos += sub_len
        elif block_id == 0x2C:  # Image Descriptor
            frame_count += 1
            if pos + 9 > n:
                break
            img_packed = data[pos + 8]
            pos += 9
            if img_packed & 0x80:
                lct_size = 3 * (1 << ((img_packed & 0x07) + 1))
                pos += lct_size
            if pos >= n:
                break
            pos += 1  # LZW minimum code size
            while pos < n:
                sub_len = data[pos]
                pos += 1
                if sub_len == 0:
                    break
                pos += sub_len
        else:
            break

    return {
        "exists": True,
        "valid_header": True,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "delays_cs": delays_cs,
        "uniform_delay_cs": delays_cs[0] if delays_cs and len(set(delays_cs)) == 1 else None,
        "file_size_bytes": len(data),
    }


def render_reopened_204_frame_walk_gif(
    derived_blend_path: str,
    gif_output_path: str,
    res_x: int = 320,
    res_y: int = 240,
    delay_cs: int = 4,
) -> Dict[str, Any]:
    """Reopen `output/dynamics_playground_task7a1.blend` read-only, render all 204 frames
    (`1..204`) continuously from `Task7A1_CharSideCam`, and encode a 204-frame 24 FPS GIF.
    """
    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scene = bpy.context.scene
    cam_obj = bpy.data.objects.get("Task7A1_CharSideCam")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if cam_obj is None or root_obj is None:
        raise RuntimeError("Task7A1_CharSideCam or CharacterRoot missing in reopened blend!")

    cfg = PipelineConfig()
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    frames_rgba: List[Any] = []

    tmp_png_path = os.path.join(tempfile.gettempdir(), f"task7a1_reopen_gif_tmp_{os.getpid()}.png")
    try:
        for f_idx in range(frame_start, frame_end + 1):
            scene.frame_set(f_idx)
            bpy.context.view_layer.update()
            tau = f_idx - 1
            disp_y, speed_ref, stage_name = evaluate_root_kinematics(tau, cfg)
            ry = float(root_obj.matrix_world.translation.y)
            _render_camera_to_png(scene, cam_obj, tmp_png_path, res_x=res_x, res_y=res_y)
            _, _, arr = _load_png_to_numpy_rgba(
                tmp_png_path,
                label_text=f"F{f_idx:03d}/204 {stage_name} Y={ry:.2f}M V={speed_ref:.2f}",
            )
            frames_rgba.append(arr)
    finally:
        if os.path.isfile(tmp_png_path):
            try:
                os.remove(tmp_png_path)
            except OSError:
                pass

    os.makedirs(os.path.dirname(gif_output_path), exist_ok=True)
    encode_animated_gif(
        filepath=gif_output_path,
        width=res_x,
        height=res_y,
        frames_rgba=frames_rgba,
        delay_cs=delay_cs,
    )
    return count_gif_frames(gif_output_path)


def export_verification_report_json(report_data: Dict[str, Any], output_path: str) -> None:
    """Write structured verification report JSON with directory creation."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
