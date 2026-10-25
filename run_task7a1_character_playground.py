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
    print("[Task 7A-1] Starting 19-Bone Character Integration into DynamicsPlayground...")
    print("=" * 72)
    report = execute_task7a1_pipeline(render_visuals=True)
    inv = report["inventory"]
    stg = report["minimal_control_stages"]
    print(f"[Task 7A-1] Derived blend saved: {report['derived_task7a1_blend']}")
    print(
        f"[Task 7A-1] Armatures={inv['armature_count_in_scene']}, Bones={inv['bone_count']}, "
        f"Meshes={inv['mesh_part_count']}, StationsIntact={report['playground_stations_intact_after_walk']}"
    )
    print(
        f"[Task 7A-1] Stage A={stg['stage_A_static_standing']['success']}, "
        f"Stage B={stg['stage_B_root_displacement']['success']}, "
        f"Stage C={stg['stage_C_single_foot_ik']['success']}, "
        f"Stage D={stg['stage_D_support_foot_lock']['all_steps_succeeded']}, "
        f"Stage E Frames={stg['stage_E_continuous_walk']['total_frames']} "
        f"(Unreachable={stg['stage_E_continuous_walk']['unreachable_count']})"
    )
    print("=" * 72)
    print("[Task 7A-1] Execution completed successfully.")
    print("=" * 72)


if __name__ == "__main__":
    main()
