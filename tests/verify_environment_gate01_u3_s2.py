"""ProceduralAnimation - Environment Gate 01 / Unit 3 / Atomic Repair S2
Swing-to-Stance Landing Continuity Diagnosis & Verification Suite

This script provides:
1. S2-A: Pre-modification boundary extraction and diagnosis (landing_boundary_before.json)
2. S2-B: Post-modification boundary extraction (landing_boundary_after.json)
3. S2-C: Before vs After boundary comparison & contract verification (landing_boundary_comparison.json)
"""

import os
import sys
import json
import math
import argparse
from typing import Dict, List, Any, Tuple, Optional

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)


def euclidean_distance(p1: List[float], p2: List[float]) -> float:
    """Compute 3D Euclidean distance between two points."""
    return math.sqrt(
        (p1[0] - p2[0]) ** 2 +
        (p1[1] - p2[1]) ** 2 +
        (p1[2] - p2[2]) ** 2
    )


def extract_landing_boundaries(
    blend_path: str,
    telemetry_json_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Extract planned targets and actual armature ankle coordinates at all step boundaries."""
    records = None
    if telemetry_json_path and os.path.exists(telemetry_json_path):
        with open(telemetry_json_path, "r", encoding="utf-8") as f:
            records = json.load(f)

    # Need bpy if blend needs to be opened or records missing
    try:
        import bpy
        has_bpy = True
    except ImportError:
        has_bpy = False

    if records is None:
        if not has_bpy:
            raise RuntimeError(f"Cannot extract boundaries: {telemetry_json_path} not found and bpy not available.")
        bpy.ops.wm.open_mainfile(filepath=blend_path)
        scene = bpy.context.scene
        if "task7a2_control_chain_diagnostics" not in scene:
            raise KeyError("Missing 'task7a2_control_chain_diagnostics' in blend scene.")
        records = json.loads(scene["task7a2_control_chain_diagnostics"])

    # Determine step boundaries from scheduled steps
    # Course B route specification:
    from src.scene.playground_terrain_traversal import create_standard_dynamics_playground_query
    from src.motion.terrain_walk import TerrainRouteInput, plan_terrain_footsteps

    env = create_standard_dynamics_playground_query()
    route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 22.40, 0.0),
        nominal_stride_m=0.30,
        step_frames=16,
        stand_start_frames=12,
        stand_stop_frames=16,
    )
    sched, total_frames = plan_terrain_footsteps(route, env, start_frame=1)

    boundaries = []
    for s in sched:
        swing_side = s.swing_side
        last_swing_f = s.frame_end - 1
        first_stance_f = s.frame_end

        # Index in 0-based records (frame 1 is index 0)
        idx_last = last_swing_f - 1
        idx_first = first_stance_f - 1

        rec_last = records[idx_last]
        rec_first = records[idx_first]

        planned_last = rec_last["motion_planning"]["planned_foot_" + swing_side]
        planned_first = rec_first["motion_planning"]["planned_foot_" + swing_side]
        target_diff = euclidean_distance(planned_last, planned_first)

        arm_last = rec_last["actual_armature"]["ankle_" + swing_side + "_world"]
        arm_first = rec_first["actual_armature"]["ankle_" + swing_side + "_world"]
        arm_diff = euclidean_distance(arm_last, arm_first)

        boundaries.append({
            "step_k": s.k,
            "swing_side": swing_side,
            "frame_last_swing": last_swing_f,
            "frame_first_stance": first_stance_f,
            "planned_last_swing": [round(x, 4) for x in planned_last],
            "planned_first_stance": [round(x, 4) for x in planned_first],
            "target_diff_m": target_diff,
            "ik_last_swing": arm_last,
            "ik_first_stance": arm_first,
            "ik_diff_m": arm_diff,
        })

    return boundaries


def compare_landing_boundaries(
    before_data: List[Dict[str, Any]],
    after_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare before vs after boundary data and evaluate tolerance contract."""
    n = len(before_data)
    if len(after_data) != n:
        raise ValueError(f"Mismatched boundary counts: before={n}, after={len(after_data)}")

    comparisons = []
    passed_count = 0
    max_before_diff = 0.0
    max_after_target_diff = 0.0
    max_after_arm_diff = 0.0

    f188_before = None
    f188_after = None

    for b, a in zip(before_data, after_data):
        b_diff = b["target_diff_m"]
        a_target_diff = a["target_diff_m"]
        a_arm_diff = a["ik_diff_m"]

        max_before_diff = max(max_before_diff, b_diff)
        max_after_target_diff = max(max_after_target_diff, a_target_diff)
        max_after_arm_diff = max(max_after_arm_diff, a_arm_diff)

        # Contract: target difference <= 1e-4 m (0.1 mm)
        passed = a_target_diff <= 1e-4 and a_arm_diff <= 1e-4
        if passed:
            passed_count += 1

        if b["frame_last_swing"] == 188:
            f188_before = b_diff
            f188_after = a_target_diff

        comparisons.append({
            "step_k": b["step_k"],
            "swing_side": b["swing_side"],
            "boundary_frames": f"{b['frame_last_swing']} -> {b['frame_first_stance']}",
            "before_target_diff_m": b_diff,
            "after_target_diff_m": a_target_diff,
            "after_armature_diff_m": a_arm_diff,
            "improvement_m": b_diff - a_target_diff,
            "passed": passed,
        })

    return {
        "total_boundaries": n,
        "boundaries_passed_contract": passed_count,
        "all_passed": (passed_count == n),
        "before_max_target_diff_m": max_before_diff,
        "after_max_target_diff_m": max_after_target_diff,
        "after_max_armature_diff_m": max_after_arm_diff,
        "frame_188_189_before_diff_m": f188_before,
        "frame_188_189_after_diff_m": f188_after,
        "comparisons": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description="Environment Gate 01 / Unit 3-S2 Landing Boundary Verification")
    parser.add_argument("--before-json", default="docs/evidence/environment_gate01_u3_s2/landing_boundary_before.json")
    parser.add_argument("--after-json", default="docs/evidence/environment_gate01_u3_s2/landing_boundary_after.json")
    parser.add_argument("--comparison-json", default="docs/evidence/environment_gate01_u3_s2/landing_boundary_comparison.json")
    parser.add_argument("--blend-path", default="output/dynamics_playground_environment_gate01_u3_s2.blend")
    parser.add_argument("--telemetry-path", default="docs/evidence/environment_gate01_u3_s2/u3_control_chain_diagnostics.json")

    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    args = parser.parse_args(argv)

    print("[S2 VERIFY] Extracting post-modification boundaries from S2 blend...")
    after_data = extract_landing_boundaries(
        blend_path=args.blend_path,
        telemetry_json_path=args.telemetry_path,
    )

    with open(args.after_json, "w", encoding="utf-8") as f:
        json.dump(after_data, f, indent=2)
    print(f"[S2 VERIFY] Saved {len(after_data)} boundaries to {args.after_json}")

    if os.path.exists(args.before_json):
        with open(args.before_json, "r", encoding="utf-8") as f:
            before_data = json.load(f)

        comp = compare_landing_boundaries(before_data, after_data)
        with open(args.comparison_json, "w", encoding="utf-8") as f:
            json.dump(comp, f, indent=2)
        print(f"[S2 VERIFY] Saved comparison report to {args.comparison_json}")

        print("\n" + "=" * 70)
        print("ENVIRONMENT GATE 01 / UNIT 3-S2 LANDING CONTINUITY VERIFICATION SUMMARY")
        print("=" * 70)
        print(f"Total Boundaries Tested:           {comp['total_boundaries']}")
        print(f"Boundaries Meeting Contract:       {comp['boundaries_passed_contract']} / {comp['total_boundaries']}")
        print(f"Before Max Target Diff:            {comp['before_max_target_diff_m'] * 1000:.3f} mm")
        print(f"After Max Planned Target Diff:     {comp['after_max_target_diff_m'] * 1000:.6f} mm")
        print(f"After Max Armature Ankle Diff:     {comp['after_max_armature_diff_m'] * 1000:.6f} mm")
        print(f"Frame 188 -> 189 Before Drop:      {comp['frame_188_189_before_diff_m'] * 1000:.3f} mm")
        print(f"Frame 188 -> 189 After Drop:       {comp['frame_188_189_after_diff_m'] * 1000:.6f} mm")
        print(f"Contract Verified (<= 0.1 mm):     {comp['all_passed']}")
        print("=" * 70)
    else:
        print(f"[WARN] Before json {args.before_json} not found. Skipping comparison.")


if __name__ == "__main__":
    main()
