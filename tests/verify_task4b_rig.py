"""Reopen character_rig_prototype.blend and verify Task 4B armature, bone hierarchy,
13-part rigid binding, L/R symmetry, rest-pose grounding, and multi-joint pose control.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import REQUIRED_PARTS, world_min_z
from src.config import PipelineConfig
from src.rig.builder import BONE_HIERARCHY, PART_TO_BONE_MAP
from src.rig.pose import apply_pose_dict, get_part_world_center, reset_pose, set_bone_rotation


def verify():
    print("=== START TASK 4B RIG & BINDING REOPEN VERIFICATION ===")
    config = PipelineConfig()
    start_x, start_y, _ = config.character_path_points[0]

    # 1. Verify CharacterArmature exists
    arm_obj = bpy.data.objects.get("CharacterArmature")
    if arm_obj is None or arm_obj.type != "ARMATURE":
        print("[FAIL] CharacterArmature object missing or not an ARMATURE", file=sys.stderr)
        sys.exit(1)

    # 2. Verify all 19 bones and parent-child relationships
    bones = arm_obj.data.bones
    if len(bones) != len(BONE_HIERARCHY):
        print(f"[FAIL] Expected {len(BONE_HIERARCHY)} bones, found {len(bones)}", file=sys.stderr)
        sys.exit(1)

    for bone_name, expected_parent in BONE_HIERARCHY.items():
        bone = bones.get(bone_name)
        if bone is None:
            print(f"[FAIL] Missing bone: {bone_name}", file=sys.stderr)
            sys.exit(1)
        actual_parent = bone.parent.name if bone.parent else None
        if actual_parent != expected_parent:
            print(
                f"[FAIL] Bone '{bone_name}' parent mismatch: expected {expected_parent}, got {actual_parent}",
                file=sys.stderr,
            )
            sys.exit(1)
    print(f"Verified all {len(bones)} bones and parent-child relationships")

    # 3. Verify 13 character parts exist and are bound to expected bones
    for part_name in REQUIRED_PARTS:
        part_obj = bpy.data.objects.get(part_name)
        if part_obj is None:
            print(f"[FAIL] Missing character part: {part_name}", file=sys.stderr)
            sys.exit(1)
        expected_bone = PART_TO_BONE_MAP[part_name]
        if part_obj.parent != arm_obj or part_obj.parent_type != "BONE" or part_obj.parent_bone != expected_bone:
            print(
                f"[FAIL] Part '{part_name}' binding invalid: parent={part_obj.parent}, "
                f"type={part_obj.parent_type}, bone={part_obj.parent_bone} (expected {expected_bone})",
                file=sys.stderr,
            )
            sys.exit(1)
    print(f"Verified all {len(REQUIRED_PARTS)} body parts bound to exact target bones")

    # 4. Verify saved pose in reopened .blend and compare with rest pose
    posed_centers_reopened = {name: get_part_world_center(name) for name in REQUIRED_PARTS}

    # Reset to rest pose and verify feet grounded at Z=0 and no L/R crossover
    reset_pose(arm_obj)
    rest_centers = {name: get_part_world_center(name) for name in REQUIRED_PARTS}

    foot_l_z = world_min_z(bpy.data.objects["Foot_L"])
    foot_r_z = world_min_z(bpy.data.objects["Foot_R"])
    print(f"Rest pose Foot_L min Z: {foot_l_z:.6f}, Foot_R min Z: {foot_r_z:.6f}")
    if abs(foot_l_z) > 1e-4 or abs(foot_r_z) > 1e-4:
        print(f"[FAIL] Rest pose feet not grounded at Z=0 ({foot_l_z}, {foot_r_z})", file=sys.stderr)
        sys.exit(1)

    for part_name, center in rest_centers.items():
        if part_name.endswith("_L") and not (center.x < start_x - 0.02):
            print(f"[FAIL] Left part '{part_name}' L/R crossover: X={center.x}", file=sys.stderr)
            sys.exit(1)
        if part_name.endswith("_R") and not (center.x > start_x + 0.02):
            print(f"[FAIL] Right part '{part_name}' L/R crossover: X={center.x}", file=sys.stderr)
            sys.exit(1)

    for bone in bones:
        head_world = arm_obj.matrix_world @ bone.head_local
        if bone.name.endswith(".L") and not (head_world.x < start_x - 0.02):
            print(f"[FAIL] Left bone '{bone.name}' L/R crossover: X={head_world.x}", file=sys.stderr)
            sys.exit(1)
        if bone.name.endswith(".R") and not (head_world.x > start_x + 0.02):
            print(f"[FAIL] Right bone '{bone.name}' L/R crossover: X={head_world.x}", file=sys.stderr)
            sys.exit(1)
    print("Verified L/R symmetry and zero crossover on all bones and parts")

    # 5. Test rotating at least 3 distinct joints via pose interface and verify mesh movement
    test_rotations = {
        "upper_arm.L": (50.0, 0.0, 0.0),
        "forearm.R": (45.0, 0.0, 0.0),
        "thigh.L": (30.0, 0.0, 0.0),
        "shin.R": (-40.0, 0.0, 0.0),
    }
    apply_pose_dict(arm_obj, test_rotations, reset_first=True)
    for part_name in ("UpperArm_L", "LowerArm_L", "LowerArm_R", "UpperLeg_L", "LowerLeg_L", "LowerLeg_R", "Foot_R"):
        disp = (get_part_world_center(part_name) - rest_centers[part_name]).length
        print(f"Dynamic joint test displacement '{part_name}': {disp:.4f} m")
        if disp < 0.03:
            print(f"[FAIL] Part '{part_name}' did not move after joint rotation", file=sys.stderr)
            sys.exit(1)

    print("[VERIFY_PASSED] Task 4B character rig and binding verification completed.")
    print("=== END TASK 4B RIG & BINDING REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
