"""Runner script for Task 7A-1: Real 19-Bone Character Integration into DynamicsPlayground
and Minimal Control Closed-Loop Verification.

Usage:
    blender --background --python run_task7a1_character_playground.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.scene.playground_character_integration import execute_task7a1_pipeline


def main() -> None:
    print("=" * 72)
    print("[Task 7A-1] Starting 19-Bone Character Integration & Reopen Validation...")
    print("=" * 72)
    report = execute_task7a1_pipeline(render_visuals=True)
    inv = report["inventory"]
    stg = report["minimal_control_stages"]
    reopen_sum = report["reopen_204_frame_validation_summary"]
    deep_diff = report["deep_asset_preservation"]
    gif_info = stg["stage_E_continuous_walk"]["gif_inspection"]

    print(f"[Task 7A-1] Derived blend saved: {report['derived_task7a1_blend']}")
    print(f"[Task 7A-1] Full 204-frame validation JSON: {report['full_frame_validation_json']}")
    print(
        f"[Task 7A-1] Armatures={inv['armature_count_in_scene']}, Bones={inv['bone_count']}, "
        f"Meshes={inv['mesh_part_count']}, DeepAssetPreservation={deep_diff['verdict']}"
    )
    print(
        f"[Task 7A-1] Stage A={stg['stage_A_static_standing']['success']}, "
        f"Stage B={stg['stage_B_root_displacement']['success']}, "
        f"Stage C={stg['stage_C_single_foot_ik']['success']}, "
        f"Stage D={stg['stage_D_support_foot_lock']['all_steps_succeeded']}, "
        f"Stage E Frames={stg['stage_E_continuous_walk']['total_frames']} "
        f"(Unreachable={stg['stage_E_continuous_walk']['unreachable_count']})"
    )
    print(
        f"[Task 7A-1] Reopen 204-Frame Verdict={reopen_sum['verdict']}, "
        f"MaxStanceAnkleDrift={reopen_sum['support_foot_and_contact_lifecycle']['max_stance_ankle_bone_drift_m']}m, "
        f"MaxRotGeodesicStep={reopen_sum['bone_rotation_continuity']['global_max_geodesic_step_deg']}deg, "
        f"GIFFrames={gif_info['frame_count']}"
    )
    print("=" * 72)
    print("[Task 7A-1] Execution completed successfully.")
    print("=" * 72)


if __name__ == "__main__":
    main()
