"""Unified Execution & Evidence Generation Runner for Task 7A-2.

Entry point script to:
1. Build `output/dynamics_playground_task7a2_corrected.blend` via `generate_dynamics_playground_task7a2_corrected_blend`.
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
from src.scene.playground_terrain_traversal import (
    generate_dynamics_playground_task7a2_corrected_blend,
)
from src.scene.playground_terrain_validation import validate_dynamics_playground_task7a2


def render_task7a2_evidence(
    derived_blend_path: str = "output/dynamics_playground_task7a2_corrected.blend",
    evidence_dir: str = "docs/evidence/task7a2",
) -> Dict[str, Any]:
    """Reopen derived blend file and render keyframe PNGs and animated GIFs."""
    abs_blend = os.path.abspath(derived_blend_path)
    abs_ev_dir = os.path.abspath(evidence_dir)
    os.makedirs(abs_ev_dir, exist_ok=True)

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene_main = bpy.data.scenes.get("Scene") or bpy.context.scene
    scene_debug = bpy.data.scenes.get("Task7A2_ControlChain_Debug")

    ramp_cam = bpy.data.objects.get("Task7A2_RampCam")
    overview_cam = bpy.data.objects.get("Task7A2_OverviewCam")
    debug_cam = bpy.data.objects.get("Task7A2_DebugCam")
    root_obj = bpy.data.objects.get("CharacterRoot")

    if ramp_cam is None or overview_cam is None:
        raise RuntimeError("Missing required Task 7A-2 inspection cameras in reopened scene")

    # -------------------------------------------------------------------------
    # 1. Render Keyframe PNGs
    # -------------------------------------------------------------------------
    keyframe_specs = [
        ("task7a2_f001_ramp_start.png", 1, scene_main, ramp_cam, "F001/700 Ramp Entrance (Flat Ground Y=10.2m)"),
        ("task7a2_f120_ramp_uphill.png", 120, scene_main, ramp_cam, "F120/700 15° Uphill Ascent (Y=12.0m, Z=0.27m)"),
        ("task7a2_f350_bridge_platform.png", 350, scene_main, ramp_cam, "F350/700 Elevated Bridge Platform (Y=17.0m, Z=1.34m)"),
        ("task7a2_f480_ramp_downhill.png", 480, scene_main, ramp_cam, "F480/700 20° Downhill Descent (Y=19.5m, Z=0.79m)"),
        ("task7a2_f685_flat_landing.png", 685, scene_main, ramp_cam, "F685/700 Flat Landing Stop (Y=22.4m, Z=0.00m)"),
        ("task7a2_overview_isometric.png", 350, scene_main, overview_cam, "DynamicsPlayground Continuous Course B Overview"),
    ]
    if scene_debug and debug_cam:
        keyframe_specs.append(
            ("task7a2_control_chain_debug.png", 350, scene_debug, debug_cam, "Task7A2 Control Chain Diagnostic Scene (6-Phase HUD & 3D Indicators)")
        )

    rendered_pngs: Dict[str, Any] = {}
    for filename, frame_num, scn, cam_obj, label in keyframe_specs:
        out_path = os.path.join(abs_ev_dir, filename)
        scn.frame_set(frame_num)
        bpy.context.window.scene = scn
        bpy.context.view_layer.update()
        _render_camera_to_png(scn, cam_obj, out_path, res_x=640, res_y=480)
        file_sz = os.path.getsize(out_path)
        rendered_pngs[filename] = {
            "filepath": out_path,
            "frame": frame_num,
            "scene": scn.name,
            "camera": cam_obj.name,
            "file_size_bytes": file_sz,
            "exists": file_sz > 1024,
        }
        print(f"  [PNG] Rendered {filename} ({scn.name}, Frame {frame_num}, {file_sz:,} bytes)")

    # -------------------------------------------------------------------------
    # 2. Render Animated GIFs
    # -------------------------------------------------------------------------
    tmp_png = os.path.join(tempfile.gettempdir(), f"task7a2_gif_tmp_{os.getpid()}.png")

    # GIF 1: Continuous Ramp Traversal (Scene, frames 1..700, stride 5 -> 140 frames)
    gif_ramps_path = os.path.join(abs_ev_dir, "task7a2_ramp_traversal.gif")
    ramps_frames_rgba = []
    print("  [GIF] Rendering Continuous Course B Ramp Traversal (frames 1..700)...")
    try:
        bpy.context.window.scene = scene_main
        total_f = scene_main.frame_end
        for f in range(1, total_f + 1, 5):
            scene_main.frame_set(f)
            bpy.context.view_layer.update()
            ry = float(root_obj.matrix_world.translation.y) if root_obj else 0.0
            rz = float(root_obj.matrix_world.translation.z) if root_obj else 0.0
            _render_camera_to_png(scene_main, ramp_cam, tmp_png, res_x=320, res_y=240)
            _, _, arr = _load_png_to_numpy_rgba(
                tmp_png,
                label_text=f"Ramp F{f:03d}/{total_f} Y={ry:.2f} Z={rz:.2f}",
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
        delay_cs=6,
    )
    gif_ramps_info = count_gif_frames(gif_ramps_path)
    print(f"  [GIF] Encoded {os.path.basename(gif_ramps_path)}: {gif_ramps_info['frame_count']} frames, {gif_ramps_info['file_size_bytes']:,} bytes")

    # GIF 2: Diagnostic Scene Live Scrubbing (Task7A2_ControlChain_Debug)
    gif_debug_path = os.path.join(abs_ev_dir, "task7a2_control_chain_debug.gif")
    gif_debug_info = {}
    if scene_debug and debug_cam:
        debug_frames_rgba = []
        print("  [GIF] Rendering Diagnostic Scene HUD & 3D Telemetry (frames 1..700)...")
        try:
            bpy.context.window.scene = scene_debug
            for f in range(1, total_f + 1, 7):
                scene_debug.frame_set(f)
                bpy.context.view_layer.update()
                _render_camera_to_png(scene_debug, debug_cam, tmp_png, res_x=320, res_y=240)
                _, _, arr = _load_png_to_numpy_rgba(
                    tmp_png,
                    label_text=f"Debug HUD F{f:03d}/{total_f}",
                )
                debug_frames_rgba.append(arr)
        finally:
            if os.path.isfile(tmp_png):
                try:
                    os.remove(tmp_png)
                except OSError:
                    pass

        encode_animated_gif(
            filepath=gif_debug_path,
            width=320,
            height=240,
            frames_rgba=debug_frames_rgba,
            delay_cs=6,
        )
        gif_debug_info = count_gif_frames(gif_debug_path)
        print(f"  [GIF] Encoded {os.path.basename(gif_debug_path)}: {gif_debug_info['frame_count']} frames, {gif_debug_info['file_size_bytes']:,} bytes")

    manifest = {
        "task": "Task 7A-2 Corrected",
        "keyframe_pngs": rendered_pngs,
        "animated_gifs": {
            "task7a2_ramp_traversal.gif": gif_ramps_info,
            "task7a2_control_chain_debug.gif": gif_debug_info,
        },
    }
    manifest_path = os.path.join(abs_ev_dir, "task7a2_evidence_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return manifest


def main():
    print("================================================================================")
    print("TASK 7A-2: DYNAMICS PLAYGROUND CONTINUOUS TERRAIN TRAVERSAL (CORRECTED)")
    print("================================================================================")

    # 1. Generate playable blend artifact
    print("\n[STEP 1] Generating playable animation scene output/dynamics_playground_task7a2_corrected.blend...")
    gen_result = generate_dynamics_playground_task7a2_corrected_blend()
    blend_path = gen_result["output_blend_path"]
    total_frames = gen_result["total_frames"]
    blend_size = os.path.getsize(blend_path)
    print(f"  [PASS] Scene generated successfully: {blend_path} ({blend_size:,} bytes, {total_frames} frames)")

    # 2. Validate reopened scene read-only
    print("\n[STEP 2] Reopening and validating output/dynamics_playground_task7a2_corrected.blend read-only...")
    val_report = validate_dynamics_playground_task7a2(blend_path)
    if val_report.get("status") != "PASS":
        print(f"  [FAIL] Validation reported issues: {val_report}")
        sys.exit(1)
    print(f"  [PASS] Reopened validation 100% SUCCESS: {val_report['total_frames_evaluated']} frames, ROM violations={val_report['total_rom_violations']}, max ankle drift={val_report['max_locked_ankle_drift_m']:.8f}m")

    # 3. Export validation report JSON
    val_report_path = "docs/evidence/task7a2/task7a2_validation_report.json"
    with open(val_report_path, "w", encoding="utf-8") as f:
        json.dump(val_report, f, indent=2)
    print(f"  [JSON] Validation report exported to: {val_report_path}")

    # 4. Render keyframe PNGs and animated GIFs
    print("\n[STEP 3] Rendering keyframe evidence PNGs and animated GIFs...")
    manifest = render_task7a2_evidence(blend_path)
    print("  [PASS] Evidence generation completed.")

    print("\n================================================================================")
    print("TASK 7A-2 EXECUTION AND VERIFICATION SUMMARY")
    print(f"  - Playable Artifact: {blend_path} ({os.path.getsize(blend_path):,} bytes)")
    print(f"  - Total Timeline Frames: {total_frames} (@ 24 FPS, 29.17 seconds continuous)")
    print(f"  - Max Locked Ankle Drift: {val_report['max_locked_ankle_drift_m']:.8f} m (Limit: 1e-4 m)")
    print(f"  - Max Bone Stretch: {val_report['max_bone_stretch_m']:.8f} m (Limit: 1e-4 m)")
    print(f"  - Mass Conservation Pass: {val_report['mass_conservation_pass']} (Strictly 70.0 kg)")
    print(f"  - Anatomical ROM Violations: {val_report['total_rom_violations']}")
    print(f"  - Terrain Penetrations: {val_report['total_terrain_penetrations']}")
    print(f"  - Diagnostic Scene Verified: {val_report['diagnostic_scene_verified']}")
    print("================================================================================")


if __name__ == "__main__":
    main()
