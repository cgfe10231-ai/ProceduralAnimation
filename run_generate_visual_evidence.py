"""Master Automation Pipeline: Visual Evidence, Telemetry & Contact Sheet (Task 6G-D-C2-A).

Executes end-to-end:
1. Loads authoritative scene: `output/dynamics_playground.blend`.
2. Registers Front, Side, and Top cameras for all 5 stations.
3. Collects frame-by-frame physics & evaluated object telemetry (72 frames).
4. Renders multi-angle keyframe PNGs (105 station stills + 7 overview stills).
5. Assembles high-resolution multi-scenario Contact Sheet.
6. Encodes continuous motion animated GIF.
7. Produces interactive HTML5 visual player.
8. Generates validation_report.md and evidence zip package.
9. Synchronizes representative deliverables into `docs/evidence/task6gd_c2a/`.

Usage:
    & "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b output/dynamics_playground.blend -P run_generate_visual_evidence.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List

import bpy
import numpy as np

# Ensure project root in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from src.scene.dynamics_visualizer import (
    inject_dynamics_visualization,
    run_dynamics_scenarios,
)
from src.scene.dynamics_visual_evidence import (
    build_and_register_station_cameras,
    build_contact_sheet_image,
    collect_frame_telemetry,
    create_evidence_zip_package,
    encode_animated_gif,
    generate_interactive_html_player,
    generate_validation_markdown_report,
    render_keyframe_images,
)


def main() -> int:
    t0 = time.time()
    print("=" * 78)
    print("TASK 6G-D-C2-A: AUTOMATED VISUAL EVIDENCE & TELEMETRY GENERATION")
    print("=" * 78)

    blend_path = os.path.abspath("output/dynamics_playground.blend")
    if not os.path.isfile(blend_path):
        print(f"[ERROR] Target benchmark blend not found: {blend_path}")
        return 1

    scene = bpy.context.scene
    print(f"[INFO] Authoritative blend loaded: {blend_path}")

    # Output directory layout
    output_base = os.path.abspath("output/evidence/task6gd_c2a")
    img_dir = os.path.join(output_base, "keyframe_samples")
    docs_evidence_dir = os.path.abspath("docs/evidence/task6gd_c2a")
    docs_img_dir = os.path.join(docs_evidence_dir, "keyframe_samples")

    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(docs_img_dir, exist_ok=True)

    # 1. Run numerical simulation scenarios (72 frames, dt=1/24s)
    print("\n[STEP 1/8] Running numerical closed-loop scenarios...")
    scenarios_data = run_dynamics_scenarios(num_steps=72, dt=1.0 / 24.0)
    print(f"  Simulated {len(scenarios_data)} physical stations across 72 frames.")

    # 2. Inject visual keyframes & cameras
    print("\n[STEP 2/8] Injecting/refreshing visual keyframes & station cameras...")
    inject_dynamics_visualization(scene, scenarios_data)
    cams = build_and_register_station_cameras(scene)
    print(f"  Registered {len(cams)} station inspection cameras.")

    # 3. Collect frame-by-frame telemetry
    print("\n[STEP 3/8] Extracting frame-by-frame physics and object telemetry...")
    telemetry = collect_frame_telemetry(scene, scenarios_data)
    telem_json_path = os.path.join(output_base, "telemetry.json")
    with open(telem_json_path, "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2)
    print(f"  Saved telemetry.json ({os.path.getsize(telem_json_path)} bytes).")
    print(f"  Max Position Error:    {telemetry['summary']['max_position_error_m']:.2e} m")
    print(f"  Max Orientation Error: {telemetry['summary']['max_orientation_error_rad']:.2e} rad")
    print(f"  Coherence Audit:       {'PASS' if telemetry['summary']['coherence_passed'] else 'FAIL'}")

    # 4. Render keyframe stills
    print("\n[STEP 4/8] Rendering multi-view keyframe stills across 7 keyframe intervals...")
    keyframe_indices = (1, 12, 24, 36, 48, 60, 72)
    rendered_stills = render_keyframe_images(scene, img_dir, keyframe_indices=keyframe_indices, cams=cams)
    print(f"  Rendered {len(rendered_stills)} keyframe image files to: {img_dir}")

    # 5. Assemble Contact Sheet
    print("\n[STEP 5/8] Assembling 5-station x 6-column Dynamics Contact Sheet...")
    contact_sheet_path = os.path.join(output_base, "contact_sheet.png")
    build_contact_sheet_image(img_dir, contact_sheet_path, telemetry)
    print(f"  Contact Sheet generated: {contact_sheet_path} ({os.path.getsize(contact_sheet_path)} bytes).")

    # 6. Encode Animated GIF
    print("\n[STEP 6/8] Encoding continuous motion animated GIF preview...")
    gif_path = os.path.join(output_base, "dynamics_overview_anim.gif")
    # Read rendered overview frames
    gif_frames = []
    for f_idx in keyframe_indices:
        ov_path = os.path.join(img_dir, f"overview_f{f_idx:03d}.png")
        if os.path.isfile(ov_path):
            b_img = bpy.data.images.load(ov_path)
            w, h = b_img.size
            buf = np.empty(w * h * 4, dtype=np.float32)
            b_img.pixels.foreach_get(buf)
            buf = buf.reshape((h, w, 4))
            bpy.data.images.remove(b_img)
            # Downscale for compact GIF (320x180)
            dh, dw = 180, 320
            y_idx = (np.linspace(0, h - 1, dh)).astype(int)
            x_idx = (np.linspace(0, w - 1, dw)).astype(int)
            gif_frames.append(buf[np.ix_(y_idx, x_idx)])

    if gif_frames:
        encode_animated_gif(gif_path, 320, 180, gif_frames, delay_cs=25)
        print(f"  Animated GIF encoded: {gif_path} ({os.path.getsize(gif_path)} bytes).")

    # 7. Generate Interactive HTML Player & Markdown Report
    print("\n[STEP 7/8] Generating Interactive HTML Player and Validation Report...")
    html_path = os.path.join(output_base, "visual_player.html")
    generate_interactive_html_player(telemetry, "keyframe_samples", html_path)
    print(f"  HTML Player generated: {html_path}")

    report_path = os.path.join(output_base, "validation_report.md")
    generate_validation_markdown_report(telemetry, "contact_sheet.png", report_path)
    print(f"  Validation Report generated: {report_path}")

    # Create distributable ZIP evidence package
    zip_path = os.path.join(output_base, "task6gd_c2a_evidence_pack.zip")
    create_evidence_zip_package(output_base, zip_path)
    print(f"  Evidence ZIP package created: {zip_path} ({os.path.getsize(zip_path)} bytes).")

    # 8. Synchronize Tracked Deliverables to docs/evidence/task6gd_c2a/
    print("\n[STEP 8/8] Synchronizing deliverables to Git-tracked docs/evidence/task6gd_c2a/...")
    shutil.copy2(telem_json_path, os.path.join(docs_evidence_dir, "telemetry.json"))
    shutil.copy2(contact_sheet_path, os.path.join(docs_evidence_dir, "contact_sheet.png"))
    shutil.copy2(report_path, os.path.join(docs_evidence_dir, "validation_report.md"))
    if os.path.isfile(gif_path):
        shutil.copy2(gif_path, os.path.join(docs_evidence_dir, "dynamics_overview_anim.gif"))

    # Copy representative keyframe stills (e.g., F01, F36, F72 for each station)
    sample_frames = (1, 36, 72)
    sample_count = 0
    for s_idx in range(1, 6):
        for v_type in ("side", "front", "top"):
            for f_idx in sample_frames:
                src_name = f"s{s_idx}_{v_type}_f{f_idx:03d}.png"
                src_p = os.path.join(img_dir, src_name)
                if os.path.isfile(src_p):
                    shutil.copy2(src_p, os.path.join(docs_img_dir, src_name))
                    sample_count += 1
    # Copy overview samples
    for f_idx in sample_frames:
        src_name = f"overview_f{f_idx:03d}.png"
        src_p = os.path.join(img_dir, src_name)
        if os.path.isfile(src_p):
            shutil.copy2(src_p, os.path.join(docs_img_dir, src_name))
            sample_count += 1

    print(f"  Synchronized {sample_count} sample stills, contact sheet, telemetry, and report to docs/evidence.")

    # Save blend file back to disk with cameras preserved
    bpy.ops.wm.save_mainfile(filepath=blend_path)
    print(f"  Updated and saved {blend_path}.")

    elapsed = time.time() - t0
    print("\n" + "=" * 78)
    print(f"[SUCCESS] Master Visual Evidence Pipeline completed in {elapsed:.2f}s.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    ret = main()
    sys.exit(ret)
