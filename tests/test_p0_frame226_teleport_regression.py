"""Regression Test: Detection and Prevention of Frame 226->227 Spatial Teleportation (Task 7A-2 P0).

Proves the existence of the historical P0 defect in `output/dynamics_playground_task7a2.blend`:
- At frame 226, the character ended Course C (Stairs) at (0.0, 7.95, 0.75).
- At frame 227, the character was re-initialized at Course B (Ramp) at (0.0, 10.20, 0.0).
- This caused an artificial instantaneous jump of Delta = 2.3717m (dy = +2.25m, dz = -0.75m).
- The historical validator explicitly concealed this jump via `and frame_num != 227`.

This test:
1. Opens `output/dynamics_playground_task7a2.blend` and verifies that strict continuity
   (without frame 227 exemption) detects and rejects the 2.37m teleportation (detects failure).
2. When `output/dynamics_playground_task7a2_corrected.blend` exists, verifies that it evaluates
   with ZERO continuity exemptions across all consecutive frames and passes cleanly.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Quaternion, Vector


def inspect_baseline_teleportation_defect(
    blend_path: str = "output/dynamics_playground_task7a2.blend",
    max_allowed_displacement_m: float = 0.12,
) -> Dict[str, any]:
    """Inspect the baseline blend file and mathematically prove the 2.37m teleportation."""
    abs_blend = os.path.abspath(blend_path)
    if not os.path.exists(abs_blend):
        raise FileNotFoundError(f"Historical Task 7A-2 baseline blend file not found: {abs_blend}")

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene

    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = bpy.data.objects.get("CharacterArmature")
    ik_l_obj = bpy.data.objects.get("FootIK.L")
    ik_r_obj = bpy.data.objects.get("FootIK.R")

    if root_obj is None or arm_obj is None:
        raise RuntimeError("Required CharacterRoot or CharacterArmature missing from scene")

    # Sample frame 226
    scene.frame_set(226)
    bpy.context.view_layer.update()
    root_pos_226 = root_obj.matrix_world.translation.copy()
    ik_l_pos_226 = ik_l_obj.matrix_world.translation.copy() if ik_l_obj else Vector()
    ik_r_pos_226 = ik_r_obj.matrix_world.translation.copy() if ik_r_obj else Vector()

    # Sample frame 227
    scene.frame_set(227)
    bpy.context.view_layer.update()
    root_pos_227 = root_obj.matrix_world.translation.copy()
    ik_l_pos_227 = ik_l_obj.matrix_world.translation.copy() if ik_l_obj else Vector()
    ik_r_pos_227 = ik_r_obj.matrix_world.translation.copy() if ik_r_obj else Vector()

    delta_root = root_pos_227 - root_pos_226
    dist_root = delta_root.length
    delta_ik_l = (ik_l_pos_227 - ik_l_pos_226).length
    delta_ik_r = (ik_r_pos_227 - ik_r_pos_226).length

    has_teleportation = dist_root > max_allowed_displacement_m

    return {
        "frame_226": {
            "root_pos": tuple(round(v, 4) for v in root_pos_226),
            "ik_l_pos": tuple(round(v, 4) for v in ik_l_pos_226),
            "ik_r_pos": tuple(round(v, 4) for v in ik_r_pos_226),
        },
        "frame_227": {
            "root_pos": tuple(round(v, 4) for v in root_pos_227),
            "ik_l_pos": tuple(round(v, 4) for v in ik_l_pos_227),
            "ik_r_pos": tuple(round(v, 4) for v in ik_r_pos_227),
        },
        "delta_root_xyz": (round(delta_root.x, 4), round(delta_root.y, 4), round(delta_root.z, 4)),
        "distance_m": round(dist_root, 4),
        "delta_ik_l_m": round(delta_ik_l, 4),
        "delta_ik_r_m": round(delta_ik_r, 4),
        "max_allowed_m": max_allowed_displacement_m,
        "is_teleportation_detected": has_teleportation,
    }


def verify_strict_continuity_without_exemption(
    blend_path: str,
    max_allowed_displacement_m: float = 0.12,
    max_allowed_rot_jerk_deg: float = 35.0,
) -> Tuple[bool, List[str]]:
    """Verify full-frame C0 continuity strictly with ZERO frame exemptions."""
    abs_blend = os.path.abspath(blend_path)
    if not os.path.exists(abs_blend):
        return False, [f"File not found: {abs_blend}"]

    bpy.ops.wm.open_mainfile(filepath=abs_blend)
    scene = bpy.context.scene

    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = bpy.data.objects.get("CharacterArmature")
    if root_obj is None or arm_obj is None:
        return False, ["Missing CharacterRoot or CharacterArmature"]

    f_start = scene.frame_start
    f_end = scene.frame_end

    prev_root: Optional[Vector] = None
    prev_quats: Dict[str, Quaternion] = {}
    violations: List[str] = []

    for f in range(f_start, f_end + 1):
        scene.frame_set(f)
        bpy.context.view_layer.update()

        cur_root = root_obj.matrix_world.translation.copy()
        if prev_root is not None:
            dist = (cur_root - prev_root).length
            # STRICT: Absolutely no exemption for any frame number!
            if dist > max_allowed_displacement_m:
                violations.append(
                    f"Frame {f-1} -> {f}: Root displacement {dist:.4f}m exceeds limit {max_allowed_displacement_m:.4f}m"
                )

        prev_root = cur_root

        # Bone rotational jerk
        cur_quats = {}
        for b in arm_obj.pose.bones:
            q = b.matrix.to_quaternion()
            cur_quats[b.name] = q
            if b.name in prev_quats:
                dot = min(1.0, max(-1.0, abs(q.dot(prev_quats[b.name]))))
                angle_deg = 2.0 * 57.2957795 * (1.0 - dot) ** 0.5
                if angle_deg > max_allowed_rot_jerk_deg:
                    violations.append(
                        f"Frame {f-1} -> {f}: Bone '{b.name}' rotational jerk {angle_deg:.2f}deg exceeds limit {max_allowed_rot_jerk_deg:.2f}deg"
                    )
        prev_quats = cur_quats

    return len(violations) == 0, violations


def run_all_checks() -> int:
    print("=" * 70)
    print("P0 DEFECT REGRESSION TEST: Frame 226->227 Teleportation Verification")
    print("=" * 70)

    # 1. Inspect historical baseline
    baseline_blend = "output/dynamics_playground_task7a2.blend"
    if os.path.exists(baseline_blend):
        print(f"\n[1/2] Inspecting historical failure baseline: {baseline_blend}")
        report = inspect_baseline_teleportation_defect(baseline_blend)
        print(f"  Frame 226 Root: {report['frame_226']['root_pos']}")
        print(f"  Frame 227 Root: {report['frame_227']['root_pos']}")
        print(f"  Delta Vector:   {report['delta_root_xyz']} (Distance: {report['distance_m']:.4f}m)")
        print(f"  Teleportation Detected: {report['is_teleportation_detected']}")

        if not report["is_teleportation_detected"]:
            print("  [ERROR] Historical baseline did NOT exhibit the expected teleportation defect!")
            return 1
        print("  [PASS] Defect successfully detected and quantified in historical baseline.")

        # Test strict continuity on baseline (MUST FAIL)
        passed_strict, violations = verify_strict_continuity_without_exemption(baseline_blend)
        if passed_strict:
            print("  [ERROR] Strict continuity unexpectedly passed on baseline!")
            return 1
        print(f"  [PASS] Strict unexempted continuity correctly failed baseline with {len(violations)} violation(s).")
        print(f"         Primary violation: {violations[0]}")
    else:
        print(f"  [WARN] Baseline blend '{baseline_blend}' not found; skipping baseline defect check.")

    # 2. Check corrected file if it exists
    corrected_blend = "output/dynamics_playground_task7a2_corrected.blend"
    if os.path.exists(corrected_blend):
        print(f"\n[2/2] Inspecting corrected animation scene: {corrected_blend}")
        passed_corrected, violations = verify_strict_continuity_without_exemption(corrected_blend)
        if not passed_corrected:
            print(f"  [FAIL] Corrected scene has {len(violations)} continuity violations:")
            for v in violations[:5]:
                print(f"    - {v}")
            return 1
        print(f"  [PASS] Corrected scene passed strict unexempted continuity check (0 violations)!")
    else:
        print(f"\n[2/2] Corrected scene '{corrected_blend}' not yet generated (expected before generation stage).")

    print("\n" + "=" * 70)
    print("P0 REGRESSION TEST COMPLETED SUCCESSFULLY.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(run_all_checks())
