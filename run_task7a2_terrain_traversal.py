"""Unified Execution & Evidence Generation Runner for Task 7A-2.

Entry point script to:
1. Build `output/dynamics_playground_task7a2.blend` via `generate_dynamics_playground_task7a2_blend`.
2. Validate the reopened scene via `validate_dynamics_playground_task7a2`.
3. Render keyframe PNGs and animated GIFs into `docs/evidence/task7a2/`.
4. Export comprehensive JSON reports and verify artifact integrity.

Usage:
    blender -b -P run_task7a2_terrain_traversal.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath("."))

import bpy
from src.config import PipelineConfig
from src.scene.playground_evidence_exporter import (
    _load_png_to_numpy_rgba,
    _render_camera_to_png,
    count_gif_frames,
    encode_animated_gif,
    export_verification_report_json,
)
from src.scene.playground_terrain_traversal import generate_dynamics_playground_task7a2_blend
from src.scene.playground_terrain_validation import validate_dynamics_playground_task7a2


def render_task7a2_evidence(
    derived_blend_path: str = "output/dynamics_playground_task7a2.blend",
    evidence_dir: str = "docs/evidence/task7a2",
) -> Dict[str, Any]:
    """Reopen derived blend file and render keyframe PNGs and animated GIFs."""
    abs_blend = os.path.abspath(derived_blend_path)
    abs_ev_dir = os.path.abspath(evidence_dir)
    os.makedirs(abs_ev_dir, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene

    stairs_cam = bpy.data.objects.get("Task7A2_StairsCam")
    ramp_cam = bpy.data.objects.get("Task7A2_RampCam")
    overview_cam = bpy.data.objects.get("Task7A2_OverviewCam")
    root_obj = bpy.data.objects.get("CharacterRoot")

    if stairs_cam is None or ramp_cam is None or overview_cam is None:
        raise RuntimeError("Missing required Task 7A-2 cameras in reopened scene")

    # -------------------------------------------------------------------------
    # 1. Render Keyframe PNGs
    # -------------------------------------------------------------------------
    keyframe_specs = [
        ("task7a2_f001_stairs_start.png", 1, stairs_cam, "F001/926 Stairs Start (Flat Ground)"),
        ("task7a2_f110_stairs_climb.png", 110, stairs_cam, "F110/926 Stairs Climb (Step 3/5 Z=0.45m)"),
        ("task7a2_f215_stairs_top.png", 215, stairs_cam, "F215/926 Stairs Top Platform (Z=0.75m)"),
        ("task7a2_f275_ramp_start.png", 275, ramp_cam, "F275/926 Ramp Entrance (Y=11.0m)"),
        ("task7a2_f400_ramp_uphill.png", 400, ramp_cam, "F400/926 15° Uphill Ascent (Z=0.67m)"),
        ("task7a2_f550_bridge_platform.png", 550, ramp_cam, "F550/926 Elevated Bridge (Z=1.34m)"),
        ("task7a2_f700_ramp_downhill.png", 700, ramp_cam, "F700/926 20° Downhill Descent (Z=0.67m)"),
        ("task7a2_f915_flat_landing.png", 915, ramp_cam, "F915/926 Flat Landing Stop (Z=0.00m)"),
        ("task7a2_overview_isometric.png", 400, overview_cam, "DynamicsPlayground Terrain Overview"),
    ]

    rendered_pngs: Dict[str, Any] = {}
    for filename, frame_num, cam_obj, label in keyframe_specs:
        out_path = os.path.join(abs_ev_dir, filename)
        scene.frame_set(frame_num)
        bpy.context.view_layer.update()
        _render_camera_to_png(scene, cam_obj, out_path, res_x=640, res_y=480)
        file_sz = os.path.getsize(out_path)
        rendered_pngs[filename] = {
            "filepath": out_path,
            "frame": frame_num,
            "camera": cam_obj.name,
            "file_size_bytes": file_sz,
            "exists": file_sz > 1024,
        }
        print(f"  [PNG] Rendered {filename} (Frame {frame_num}, {file_sz:,} bytes)")

    # -------------------------------------------------------------------------
    # 2. Render Animated GIFs
    # -------------------------------------------------------------------------
    # GIF 1: Course C (Stairs, frames 1..226, stride 3 -> ~76 frames)
    gif_stairs_path = os.path.join(abs_ev_dir, "task7a2_stairs_traversal.gif")
    stairs_frames_rgba = []
    tmp_png = os.path.join(tempfile.gettempdir(), f"task7a2_gif_tmp_{os.getpid()}.png")

    print("  [GIF] Rendering Course C (Stairs Traversal, frames 1..226)...")
    try:
        for f in range(1, 227, 3):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            ry = float(root_obj.matrix_world.translation.y)
            rz = float(root_obj.matrix_world.translation.z)
            _render_camera_to_png(scene, stairs_cam, tmp_png, res_x=320, res_y=240)
            _, _, arr = _load_png_to_numpy_rgba(
                tmp_png,
                label_text=f"Stairs F{f:03d}/226 Y={ry:.2f} Z={rz:.2f}",
            )
            stairs_frames_rgba.append(arr)
    finally:
        if os.path.isfile(tmp_png):
            try:
                os.remove(tmp_png)
            except OSError:
                pass

    encode_animated_gif(
        filepath=gif_stairs_path,
        width=320,
        height=240,
        frames_rgba=stairs_frames_rgba,
        delay_cs=5,
    )
    gif_stairs_info = count_gif_frames(gif_stairs_path)
    print(f"  [GIF] Encoded {os.path.basename(gif_stairs_path)}: {gif_stairs_info['frame_count']} frames, {gif_stairs_info['file_size_bytes']:,} bytes")

    # GIF 2: Course B (Ramp, frames 227..926, stride 7 -> ~100 frames)
    gif_ramps_path = os.path.join(abs_ev_dir, "task7a2_ramp_traversal.gif")
    ramps_frames_rgba = []
    print("  [GIF] Rendering Course B (Ramp Traversal, frames 227..926)...")
    try:
        for f in range(227, 927, 7):
            scene.frame_set(f)
            bpy.context.view_layer.update()
            ry = float(root_obj.matrix_world.translation.y)
            rz = float(root_obj.matrix_world.translation.z)
            _render_camera_to_png(scene, ramp_cam, tmp_png, res_x=320, res_y=240)
            _, _, arr = _load_png_to_numpy_rgba(
                tmp_png,
                label_text=f"Ramp F{f:03d}/926 Y={ry:.2f} Z={rz:.2f}",
            )
            ramps_frames_rgba.append(arr)
    finally:
        if os.path.isfile(tmp_png):
            try:
                os.remove(tmp_png)
            except OSError:
                pass

    encode_animated_gif(
        filepath=gif_ramps_path,
        width=320,
        height=240,
        frames_rgba=ramps_frames_rgba,
        delay_cs=5,
    )
    gif_ramps_info = count_gif_frames(gif_ramps_path)
    print(f"  [GIF] Encoded {os.path.basename(gif_ramps_path)}: {gif_ramps_info['frame_count']} frames, {gif_ramps_info['file_size_bytes']:,} bytes")

    manifest = {
        "task": "Task 7A-2",
        "keyframe_pngs": rendered_pngs,
        "animated_gifs": {
            "task7a2_stairs_traversal.gif": gif_stairs_info,
            "task7a2_ramp_traversal.gif": gif_ramps_info,
        },
    }
    manifest_path = os.path.join(abs_ev_dir, "task7a2_evidence_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    print("================================================================================")
    print("TASK 7A-2: DYNAMICS PLAYGROUND CONTINUOUS TERRAIN TRAVERSAL")
    print("================================================================================")

    # 1. Generate playable blend artifact
    print("\n[STEP 1] Generating playable animation scene output/dynamics_playground_task7a2.blend...")
    gen_result = generate_dynamics_playground_task7a2_blend()
    blend_path = gen_result["output_blend_path"]
    total_frames = gen_result["total_frames"]
    blend_size = os.path.getsize(blend_path)
    print(f"  [PASS] Scene generated successfully: {blend_path} ({blend_size:,} bytes, {total_frames} frames)")

    # 2. Validate reopened scene read-only
    print("\n[STEP 2] Reopening and validating output/dynamics_playground_task7a2.blend read-only...")
    val_report = validate_dynamics_playground_task7a2(blend_path)
    if not val_report["is_valid"]:
        print(f"  [FAIL] Validation reported issues: ROM violations={val_report['rom_violation_count']}, penetrations={val_report['terrain_penetration_count']}")
        sys.exit(1)
    print(f"  [PASS] Reopened validation 100% SUCCESS: {val_report['total_frames_evaluated']} frames, ROM violations={val_report['rom_violation_count']}, max ankle drift={val_report['max_ankle_drift_m']:.8f}m")

    # 3. Export validation report JSON
    val_report_path = "docs/evidence/task7a2/task7a2_validation_report.json"
    export_verification_report_json(val_report, val_report_path)
    print(f"  [JSON] Validation report exported to: {val_report_path}")

    # 4. Render keyframe PNGs and animated GIFs
    print("\n[STEP 3] Rendering keyframe evidence PNGs and animated GIFs...")
    manifest = render_task7a2_evidence(blend_path)
    print("  [PASS] Evidence generation completed.")

    print("\n================================================================================")
    print("TASK 7A-2 EXECUTION AND VERIFICATION SUMMARY")
    print(f"  - Playable Artifact: {blend_path} ({os.path.getsize(blend_path):,} bytes)")
    print(f"  - Total Timeline Frames: {total_frames} (8.5s Stairs + 29.2s Ramps)")
    print(f"  - Max Locked Ankle Drift: {val_report['max_ankle_drift_m']:.8f} m (Limit: 1e-4 m)")
    print(f"  - Max Bone Stretch: {val_report['max_bone_stretch_m']:.8f} m (Limit: 1e-4 m)")
    print(f"  - Total Humanoid Mass: {val_report['total_mass_kg']:.3f} kg (Strictly 70.0 kg)")
    print(f"  - Anatomical ROM Violations: {val_report['rom_violation_count']}")
    print(f"  - Terrain Penetrations: {val_report['terrain_penetration_count']}")
    print("================================================================================")


if __name__ == "__main__":
    main()
