"""Automated Verification Suite for Task 7A-2 Continuous Terrain Locomotion.

Performs read-only validation on:
1. `output/dynamics_playground_task7a2_corrected.blend`:
   - Scene exists, valid Blender file (> 200 KB).
   - Contains 19-bone CharacterArmature, 13 character mesh parts, and IK empty targets.
   - 700 animated frames of continuous Course B (Ramp) traversal.
   - Strict unexempted frame-to-frame C0 continuity (< 0.12 m/frame @ 24 FPS, NO exemptions).
   - Maximum locked foot ankle drift <= 1.0e-4 m.
   - Maximum bone length stretch <= 1.0e-4 m.
   - Zero anatomical joint ROM violations across all joints.
   - Zero terrain penetration (vertex min Z >= terrain Z - 0.005 m).
   - Rigid link mass strictly conserved at 70.000 kg.
   - Dedicated `Task7A2_ControlChain_Debug` diagnostic scene with 6-phase HUD & 3D indicators.
2. P0 Teleportation Regression:
   - Proves historical baseline `output/dynamics_playground_task7a2.blend` exhibited the 2.37m jump.
   - Proves `output/dynamics_playground_task7a2_corrected.blend` passes with ZERO exemptions.
3. Evidence Artifacts in `docs/evidence/task7a2/`:
   - All 7 keyframe PNGs rendered and valid (> 10 KB).
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
from tests.test_p0_frame226_teleport_regression import (
    inspect_baseline_teleportation_defect,
    verify_strict_continuity_without_exemption,
)


def run_verification() -> bool:
    print("================================================================================")
    print("VERIFICATION SUITE: TASK 7A-2 CONTINUOUS TERRAIN TRAVERSAL (CORRECTED)")
    print("================================================================================")

    all_passed = True
    corrected_blend = os.path.abspath("output/dynamics_playground_task7a2_corrected.blend")
    baseline_blend = os.path.abspath("output/dynamics_playground_task7a2.blend")
    evidence_dir = os.path.abspath("docs/evidence/task7a2")

    # 1. Check corrected blend file existence and size
    print("\n[CHECK 1] Verifying output/dynamics_playground_task7a2_corrected.blend artifact...")
    if not os.path.isfile(corrected_blend):
        print(f"  [FAIL] Blend file missing: {corrected_blend}")
        return False
    blend_sz = os.path.getsize(corrected_blend)
    if blend_sz < 200_000:
        print(f"  [FAIL] Blend file suspiciously small: {blend_sz} bytes (< 200 KB)")
        return False
    print(f"  [PASS] Corrected blend file exists: {blend_sz:,} bytes")

    # 2. Execute deep read-only validation
    print("\n[CHECK 2] Reopening corrected blend file and evaluating 700-frame kinematics...")
    try:
        val_report = validate_dynamics_playground_task7a2(corrected_blend)
    except Exception as e:
        print(f"  [FAIL] Validation threw unexpected exception: {e}")
        return False

    print(f"  - Status: {val_report.get('status')}")
    print(f"  - Frames evaluated: {val_report.get('total_frames_evaluated')}")
    print(f"  - Max ankle drift: {val_report.get('max_locked_ankle_drift_m'):.8f} m (Limit: 1.0e-4 m)")
    print(f"  - Max bone stretch: {val_report.get('max_bone_stretch_m'):.8f} m (Limit: 1.0e-4 m)")
    print(f"  - Max root velocity: {val_report.get('max_root_velocity_m_per_frame'):.4f} m/frame (Limit: 0.12 m/frame)")
    print(f"  - Mass conservation: {val_report.get('mass_conservation_pass')} (70.0 kg)")
    print(f"  - ROM violations: {val_report.get('total_rom_violations')}")
    print(f"  - Terrain penetrations: {val_report.get('total_terrain_penetrations')}")
    print(f"  - Diagnostic scene verified: {val_report.get('diagnostic_scene_verified')}")

    if val_report.get("status") != "PASS":
        print(f"  [FAIL] Kinematic validation failed: {val_report}")
        all_passed = False
    else:
        print("  [PASS] Kinematic validation passed 100%.")

    # 3. P0 Regression Checks
    print("\n[CHECK 3] Running P0 defect detection on historical baseline vs corrected scene...")
    if os.path.exists(baseline_blend):
        base_rep = inspect_baseline_teleportation_defect(baseline_blend)
        if not base_rep["is_teleportation_detected"]:
            print("  [FAIL] Baseline defect was not detected!")
            all_passed = False
        else:
            print(f"  [PASS] Historical baseline defect detected: Frame 226->227 jump = {base_rep['distance_m']:.4f}m")
    else:
        print("  [WARN] Baseline blend not found; skipping baseline check.")

    passed_cont, violations = verify_strict_continuity_without_exemption(corrected_blend)
    if not passed_cont:
        print(f"  [FAIL] Corrected scene failed strict continuity with {len(violations)} violation(s):")
        for v in violations[:3]:
            print(f"    - {v}")
        all_passed = False
    else:
        print("  [PASS] Corrected scene passed strict unexempted continuity (0 violations).")

    # 4. Check JSON telemetry files
    print("\n[CHECK 4] Verifying JSON telemetry documents in docs/evidence/task7a2/...")
    req_json_files = [
        "task7a2_contact_state_records.json",
        "task7a2_execution_summary.json",
        "task7a2_control_chain_diagnostics.json",
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

    # 5. Check keyframe PNGs
    print("\n[CHECK 5] Verifying keyframe rendered PNGs...")
    req_pngs = [
        "task7a2_f001_ramp_start.png",
        "task7a2_f120_ramp_uphill.png",
        "task7a2_f350_bridge_platform.png",
        "task7a2_f480_ramp_downhill.png",
        "task7a2_f685_flat_landing.png",
        "task7a2_overview_isometric.png",
        "task7a2_control_chain_debug.png",
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

    # 6. Check animated GIFs
    print("\n[CHECK 6] Verifying animated GIFs...")
    gif_ramps = os.path.join(evidence_dir, "task7a2_ramp_traversal.gif")
    gif_debug = os.path.join(evidence_dir, "task7a2_control_chain_debug.gif")

    for gp, min_frames, desc in [
        (gif_ramps, 100, "Continuous Ramp Traversal GIF"),
        (gif_debug, 80, "Diagnostic Scene Scrubbing GIF"),
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
