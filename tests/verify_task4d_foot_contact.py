"""Reopen character_foot_contact_prototype.blend and verify Task 4D support-foot
locking, ground contact state persistence, world-space bone/mesh stability under
root translation, unlocked-foot IK responsiveness, and boundary/out-of-reach behavior.
"""

import os
import sys

import bpy
from mathutils import Vector

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import REQUIRED_PARTS
from src.config import PipelineConfig
from src.rig.builder import BONE_HIERARCHY, PART_TO_BONE_MAP
from src.rig.foot_contact import (
    evaluate_foot_support,
    get_foot_support_state,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import HIP_X_OFFSET, reset_leg_ik, set_foot_ik_target


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 4D FOOT CONTACT & LOCK REOPEN VERIFICATION ===")
    config = PipelineConfig()
    start_x, start_y, start_z = config.character_path_points[0]

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if arm_obj is None or root_obj is None:
        _fail("Missing CharacterArmature or CharacterRoot")

    # 1. Verify 19-bone hierarchy and 13-part bindings remain intact
    if len(arm_obj.data.bones) != len(BONE_HIERARCHY):
        _fail(f"Expected {len(BONE_HIERARCHY)} bones, found {len(arm_obj.data.bones)}")
    for part_name in REQUIRED_PARTS:
        part_obj = bpy.data.objects.get(part_name)
        if part_obj is None or part_obj.parent_bone != PART_TO_BONE_MAP[part_name]:
            _fail(f"Broken binding on part {part_name}")
    print("Verified 19 bones and 13 rigid body-part bindings preserved")

    # 2. Verify reopened state from saved .blend (Left foot locked at waypoint while Root is displaced)
    reopened_l = get_foot_support_state(arm_obj, "L")
    reopened_r = get_foot_support_state(arm_obj, "R")
    print(
        f"Reopened Saved State: L_locked={reopened_l['is_locked']}, L_status={reopened_l['reach_status']}, "
        f"L_ankle_drift={reopened_l['ankle_bone_drift']:.6f}m, L_mesh_drift={reopened_l['mesh_center_drift']:.6f}m, "
        f"Foot_L_minZ={reopened_l['foot_min_z']:.6f}m | R_locked={reopened_r['is_locked']}, Foot_R_minZ={reopened_r['foot_min_z']:.4f}m"
    )
    if not reopened_l["is_locked"] or reopened_r["is_locked"]:
        _fail("Saved lock state in reopened .blend does not match expected L=locked, R=unlocked")
    if not reopened_l["is_reachable"] or reopened_l["ankle_bone_drift"] > 0.001:
        _fail(f"Reopened locked foot L drifted excessively: {reopened_l['ankle_bone_drift']}")
    if abs(reopened_l["foot_min_z"]) > 1e-3:
        _fail(f"Reopened locked foot L not grounded: minZ={reopened_l['foot_min_z']}")

    # 3. Verify pure horizontal root displacement stability (Left locked, Right free)
    unlock_foot_contact(arm_obj, "L")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)

    lock_foot_contact(arm_obj, "L", contact_world_xyz=(start_x - HIP_X_OFFSET, start_y, 0.0))
    move_character_root_with_support(arm_obj, (start_x + 0.03, start_y + 0.08, start_z))
    horiz_l = evaluate_foot_support(arm_obj, "L")
    free_r = set_foot_ik_target(arm_obj, "R", (start_x + HIP_X_OFFSET + 0.03, start_y + 0.22, start_z + 0.24))
    print(
        f"Pure Horizontal Shift (+0.03X, +0.08Y): L_status={horiz_l['reach_status']}, "
        f"controller_drift={horiz_l['controller_drift']:.6f}m, ankle_bone_drift={horiz_l['ankle_bone_drift']:.6f}m, "
        f"mesh_center_drift={horiz_l['mesh_center_drift']:.6f}m, Foot_L_minZ={horiz_l['foot_min_z']:.6f}m | "
        f"Free_R_err={free_r['target_error']:.6f}m"
    )
    if not horiz_l["is_reachable"] or horiz_l["controller_drift"] > 1e-6 or horiz_l["ankle_bone_drift"] > 0.010:
        _fail("Pure horizontal shift stability check failed on Left foot")
    if horiz_l["foot_min_z"] < -1e-3 or horiz_l["foot_min_z"] > 0.010:
        _fail(f"Support foot L left ground vicinity: minZ={horiz_l['foot_min_z']}")
    if free_r["target_error"] > 0.005:
        _fail(f"Unlocked Right foot IK failed while Left foot locked: err={free_r['target_error']}")

    # 4. Verify independent Right foot lock + Left foot free
    unlock_foot_contact(arm_obj, "L")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)

    lock_foot_contact(arm_obj, "R", contact_world_xyz=(start_x + HIP_X_OFFSET, start_y, 0.0))
    move_character_root_with_support(arm_obj, (start_x - 0.02, start_y + 0.10, start_z - 0.015))
    strict_r = evaluate_foot_support(arm_obj, "R")
    free_l = set_foot_ik_target(arm_obj, "L", (start_x - HIP_X_OFFSET - 0.02, start_y + 0.22, start_z + 0.24))
    print(
        f"Right Foot Locked Shift (-0.02X, +0.10Y, -0.015Z): R_status={strict_r['reach_status']}, "
        f"R_ankle_drift={strict_r['ankle_bone_drift']:.6f}m, R_mesh_drift={strict_r['mesh_center_drift']:.6f}m, "
        f"Foot_R_minZ={strict_r['foot_min_z']:.6f}m | Free_L_err={free_l['target_error']:.6f}m"
    )
    if not strict_r["strictly_in_reach"] or strict_r["ankle_bone_drift"] > 0.001 or free_l["target_error"] > 0.005:
        _fail("Right foot support lock or Left free IK check failed")

    # 5. Verify boundary and out-of-reach behavior (must report UNREACHABLE and never move locked point)
    move_character_root_with_support(arm_obj, (start_x, start_y + 0.45, start_z))
    exceed_r = evaluate_foot_support(arm_obj, "R")
    print(
        f"Out-of-Reach Shift (+0.45Y): R_status={exceed_r['reach_status']}, is_reachable={exceed_r['is_reachable']}, "
        f"hip_dist={exceed_r['hip_to_target_dist']:.5f}m, controller_drift={exceed_r['controller_drift']:.6f}m, "
        f"actual_ankle_drift={exceed_r['ankle_bone_drift']:.5f}m"
    )
    if exceed_r["is_reachable"] or exceed_r["reach_status"] != "UNREACHABLE":
        _fail("Failed to report UNREACHABLE when root exceeded leg reach")
    if exceed_r["controller_drift"] > 1e-6:
        _fail("Locked target point was secretly moved during out-of-reach root displacement")

    # 6. Verify releasing lock returns control to normal IK
    released_r = unlock_foot_contact(arm_obj, "R")
    if released_r["is_locked"]:
        _fail("unlock_foot_contact failed to release Right foot")
    root_obj.location = Vector((start_x, start_y, start_z))
    reset_leg_ik(arm_obj)
    normal_r = set_foot_ik_target(arm_obj, "R", (start_x + HIP_X_OFFSET, start_y + 0.15, start_z + 0.22))
    if normal_r["target_error"] > 0.005:
        _fail(f"Released Right foot failed to follow normal IK target: err={normal_r['target_error']}")

    print("[VERIFY_PASSED] Task 4D support-foot locking and ground contact verification completed.")
    print("=== END TASK 4D FOOT CONTACT & LOCK REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
