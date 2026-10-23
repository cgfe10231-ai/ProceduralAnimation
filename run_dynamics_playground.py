"""Generate Procedural Dynamics Training Ground Scene (Task 6G-D-PRE-P2).

Executes scene builder and saves output/dynamics_playground.blend.
Can be executed via Blender headless:
  blender -b -P run_dynamics_playground.py
or via run_tests.ps1 / run_test_suite.py.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def main():
    print("=" * 80)
    print("PROCEDURAL DYNAMICS PLAYGROUND GENERATOR (Task 6G-D-PRE-P2)")
    print("=" * 80)

    try:
        import bpy
    except ImportError:
        print("[ERROR] run_dynamics_playground.py requires the Blender Python environment (bpy).", file=sys.stderr)
        print("Run via: blender -b -P run_dynamics_playground.py", file=sys.stderr)
        return 1

    from src.scene.builder import build_dynamics_playground
    from src.scene.environment_query import create_standard_dynamics_playground_query

    output_blend = os.path.join(PROJECT_ROOT, "output", "dynamics_playground.blend")
    query = create_standard_dynamics_playground_query()

    print(f"\n1. Initializing 6-zone Dynamics Training Ground...")
    print(f"   Registered {len(query.get_all_surfaces())} analytical surface patches:")
    for idx, s in enumerate(query.get_all_surfaces(), 1):
        print(f"     {idx:02d}. [{s.surface_id}] {s.surface_type.value} at center={s.center}, normal={s.normal}")

    print(f"\n2. Building Blender scene geometry, normal arrows, and lighting...")
    scene, _ = build_dynamics_playground(query=query, output_path=output_blend)

    file_size = os.path.getsize(output_blend) if os.path.exists(output_blend) else 0
    print(f"\n3. Validation & Output Summary:")
    print(f"   - Target file: {output_blend}")
    print(f"   - File size:   {file_size:,} bytes")
    print(f"   - Objects:     {len(scene.objects)} objects created in scene")
    print("=" * 80)
    print("DYNAMICS PLAYGROUND GENERATION COMPLETED SUCCESSFULLY.")
    print("=" * 80)
    return 0

if __name__ == "__main__":
    sys.exit(main())
