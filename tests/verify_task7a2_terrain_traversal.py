"""Automated Verification Suite for Task 7A-2 Terrain Locomotion.

Performs read-only validation on:
1. `output/dynamics_playground_task7a2.blend`:
   - Scene exists, valid Blender file (> 200 KB).
   - Contains 19-bone CharacterArmature, 13 character mesh parts, and 4 IK empty targets.
   - 926 animated frames across Course C (Stairs) and Course B (Ramp).
   - Maximum locked foot ankle drift <= 1.0e-4 m.
   - Maximum bone length stretch <= 1.0e-4 m.
   - Zero anatomical joint ROM violations across all joints.
   - Zero terrain penetration (foot min Z >= terrain Z - 0.005 m).
   - Rigid link mass strictly conserved at 70.000 kg.
2. Evidence Artifacts in `docs/evidence/task7a2/`:
   - All 9 keyframe PNGs rendered and valid (> 10 KB).
   - Both animated GIFs exist, valid GIF89a header, and expected frame counts.
   - All companion JSON telemetry records exist and parse correctly.

Returns exit code 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import json
import os
import sys

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath("."))

from src.scene.playground_evidence_exporter import count_gif_frames
from src.scene.playground_terrain_validation import validate_dynamics_playground_task7a2


def run_verification() -> bool:
    print("================================================================================")
    print("VERIFICATION SUITE: TASK 7A-2 CONTINUOUS TERRAIN TRAVERSAL")
    print("================================================================================")

    all_passed = True
    blend_path = os.path.abspath("output/dynamics_playground_task7a2.blend")
    evidence_dir = os.path.abspath("docs/evidence/task7a2")

    # 1. Check blend file existence and size
    print("\n[CHECK 1] Verifying output/dynamics_playground_task7a2.blend artifact...")
    if not os.path.isfile(blend_path):
        print(f"  [FAIL] Blend file missing: {blend_path}")
        return False
    blend_sz = os.path.getsize(blend_path)
    if blend_sz < 200_000:
        print(f"  [FAIL] Blend file suspiciously small: {blend_sz} bytes (< 200 KB)")
        return False
    print(f"  [PASS] Blend file exists: {blend_sz:,} bytes")

    # 2. Execute deep read-only validation
    print("\n[CHECK 2] Reopening blend file and evaluating 926-frame kinematics...")
    try:
        val_report = validate_dynamics_playground_task7a2(blend_path)
    except Exception as e:
        print(f"  [FAIL] Validation threw unexpected exception: {e}")
        return False

    print(f"  - Frames evaluated: {val_report['total_frames_evaluated']}")
    print(f"  - Max ankle drift: {val_report['max_ankle_drift_m']:.8f} m (Limit: 1.0e-4 m)")
    print(f"  - Max bone stretch: {val_report['max_bone_stretch_m']:.8f} m (Limit: 1.0e-4 m)")
    print(f"  - Humanoid total mass: {val_report['total_mass_kg']:.3f} kg (Target: 70.0 kg)")
    print(f"  - ROM violations: {val_report['rom_violation_count']}")
    print(f"  - Terrain penetrations: {val_report['terrain_penetration_count']}")

    if not val_report["is_valid"]:
        print(f"  [FAIL] Kinematic validation failed: {val_report}")
        all_passed = False
    else:
        print("  [PASS] Kinematic validation passed 100%.")

    # 3. Check JSON telemetry files
    print("\n[CHECK 3] Verifying JSON telemetry documents in docs/evidence/task7a2/...")
    req_json_files = [
        "task7a2_contact_state_records.json",
        "task7a2_execution_summary.json",
        "task7a2_validation_report.json",
        "task7a2_evidence_manifest.json",
    ]
    for jf in req_json_files:
        jp = os.path.join(evidence_dir, jf)
        if not os.path.isfile(jp):
            print(f"  [FAIL] Missing required JSON file: {jf}")
            all_passed = False
            continue
        sz = os.path.getsize(jp)
        if sz < 100:
            print(f"  [FAIL] JSON file suspiciously empty: {jf} ({sz} bytes)")
            all_passed = False
            continue
        try:
            with open(jp, "r", encoding="utf-8") as f:
                json.load(f)
            print(f"  [PASS] JSON verified: {jf} ({sz:,} bytes)")
        except Exception as e:
            print(f"  [FAIL] Failed to parse JSON {jf}: {e}")
            all_passed = False

    # 4. Check keyframe PNGs
    print("\n[CHECK 4] Verifying keyframe rendered PNGs...")
    req_pngs = [
        "task7a2_f001_stairs_start.png",
        "task7a2_f110_stairs_climb.png",
        "task7a2_f215_stairs_top.png",
        "task7a2_f275_ramp_start.png",
        "task7a2_f400_ramp_uphill.png",
        "task7a2_f550_bridge_platform.png",
        "task7a2_f700_ramp_downhill.png",
        "task7a2_f915_flat_landing.png",
        "task7a2_overview_isometric.png",
    ]
    for png in req_pngs:
        pp = os.path.join(evidence_dir, png)
        if not os.path.isfile(pp):
            print(f"  [FAIL] Missing keyframe PNG: {png}")
            all_passed = False
            continue
        sz = os.path.getsize(pp)
        if sz < 10_000:
            print(f"  [FAIL] PNG suspiciously small: {png} ({sz} bytes)")
            all_passed = False
            continue
        print(f"  [PASS] Keyframe PNG verified: {png} ({sz:,} bytes)")

    # 5. Check animated GIFs
    print("\n[CHECK 5] Verifying animated GIFs...")
    gif_stairs = os.path.join(evidence_dir, "task7a2_stairs_traversal.gif")
    gif_ramps = os.path.join(evidence_dir, "task7a2_ramp_traversal.gif")

    for gp, min_frames, desc in [
        (gif_stairs, 50, "Stairs Traversal GIF"),
        (gif_ramps, 80, "Ramp Traversal GIF"),
    ]:
        if not os.path.isfile(gp):
            print(f"  [FAIL] Missing GIF: {os.path.basename(gp)}")
            all_passed = False
            continue
        info = count_gif_frames(gp)
        if not info["valid_header"]:
            print(f"  [FAIL] Invalid GIF header: {os.path.basename(gp)}")
            all_passed = False
            continue
        if info["frame_count"] < min_frames:
            print(f"  [FAIL] GIF has too few frames: {info['frame_count']} < {min_frames}")
            all_passed = False
            continue
        print(f"  [PASS] {desc}: {info['frame_count']} frames, {info['width']}x{info['height']}, {info['file_size_bytes']:,} bytes")

    print("\n================================================================================")
    if all_passed:
        print("[OVERALL RESULT] TASK 7A-2 VERIFICATION: ALL CHECKS PASSED (100%)")
        print("================================================================================")
        return True
    else:
        print("[OVERALL RESULT] TASK 7A-2 VERIFICATION: FAILED")
        print("================================================================================")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
