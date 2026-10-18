"""Reopen character_prototype.blend and verify Task 4A placeholder contents."""

import math
import os
import sys

import bpy
from mathutils import Vector

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import REQUIRED_PARTS
from src.config import PipelineConfig


def _world_min_z(obj):
    return min((obj.matrix_world @ Vector(c)).z for c in obj.bound_box)


def verify():
    print("=== START TASK 4A CHARACTER REOPEN VERIFICATION ===")
    config = PipelineConfig()
    start = config.character_path_points[0]

    col_names = [c.name for c in bpy.data.collections]
    print(f"Collections: {col_names}")
    if "Character" not in col_names:
        print("[FAIL] Missing Character collection", file=sys.stderr)
        sys.exit(1)
    if "Environment" not in col_names:
        print("[FAIL] Task 3 Environment collection missing", file=sys.stderr)
        sys.exit(1)

    root = bpy.data.objects.get("CharacterRoot")
    if root is None:
        print("[FAIL] Missing CharacterRoot", file=sys.stderr)
        sys.exit(1)

    dx = root.location.x - start[0]
    dy = root.location.y - start[1]
    dist_xy = math.hypot(dx, dy)
    print(f"Root location: {tuple(round(c, 6) for c in root.location)}")
    print(f"Start waypoint: {start}")
    print(f"Root XY distance to start: {dist_xy:.6f} m")
    if dist_xy > 1e-4:
        print("[FAIL] Character is not at Task 3 start waypoint", file=sys.stderr)
        sys.exit(1)

    missing = [name for name in REQUIRED_PARTS if bpy.data.objects.get(name) is None]
    if missing:
        print(f"[FAIL] Missing parts: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"Found all {len(REQUIRED_PARTS)} required body parts")

    pelvis = bpy.data.objects["Pelvis"]
    pelvis_world = pelvis.matrix_world.translation
    print(f"Pelvis world: {tuple(round(c, 6) for c in pelvis_world)}")
    pelvis_xy_err = math.hypot(pelvis_world.x - start[0], pelvis_world.y - start[1])
    if pelvis_xy_err > 0.25:
        print("[FAIL] Pelvis world XY is not at the start waypoint (parenting offset?)", file=sys.stderr)
        sys.exit(1)

    armatures = [obj.name for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if armatures:
        print(f"[FAIL] Unexpected armatures in Task 4A file: {armatures}", file=sys.stderr)
        sys.exit(1)

    foot_l_z = _world_min_z(bpy.data.objects["Foot_L"])
    foot_r_z = _world_min_z(bpy.data.objects["Foot_R"])
    print(f"Foot_L min Z: {foot_l_z:.6f}")
    print(f"Foot_R min Z: {foot_r_z:.6f}")
    for name, z in (("Foot_L", foot_l_z), ("Foot_R", foot_r_z)):
        if z < -0.02 or z > 0.05:
            print(f"[FAIL] {name} not near ground Z=0 (got {z})", file=sys.stderr)
            sys.exit(1)

    print("[VERIFY_PASSED] Task 4A character prototype verification completed.")
    print("=== END TASK 4A CHARACTER REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
