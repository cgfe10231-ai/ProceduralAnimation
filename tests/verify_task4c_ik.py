"""Reopen character_ik_prototype.blend and verify Task 4C two-bone leg IK,
knee pole targets, independent foot orientation control, neutral/left-lift/right-lift
static poses, zero cross-leg interference, ground-penetration protection,
and out-of-reach target clamping.
"""

import os
import sys

import bpy

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.character.builder import REQUIRED_PARTS, world_min_z
from src.config import PipelineConfig
from src.rig.builder import BONE_HIERARCHY, PART_TO_BONE_MAP
from src.rig.ik import (
    FOOT_ROT_CONSTRAINT_NAMES,
    HIP_X_OFFSET,
    IK_CONSTRAINT_NAMES,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    POLE_TARGET_NAMES,
    get_leg_ik_state,
    reset_leg_ik,
    set_foot_ik_target,
)
from src.rig.pose import get_part_world_center


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify() -> None:
    print("=== START TASK 4C LEG IK REOPEN VERIFICATION ===")
    config = PipelineConfig()
    start_x, start_y, start_z = config.character_path_points[0]

    # 1. Verify Armature and all 19 bones from Task 4B are preserved
    arm_obj = bpy.data.objects.get("CharacterArmature")
    if arm_obj is None or arm_obj.type != "ARMATURE":
        _fail("CharacterArmature missing or not an ARMATURE")

    bones = arm_obj.data.bones
    if len(bones) != len(BONE_HIERARCHY):
        _fail(f"Expected {len(BONE_HIERARCHY)} bones, found {len(bones)}")

    for bone_name, expected_parent in BONE_HIERARCHY.items():
        bone = bones.get(bone_name)
        if bone is None:
            _fail(f"Missing bone: {bone_name}")
        actual_parent = bone.parent.name if bone.parent else None
        if actual_parent != expected_parent:
            _fail(f"Bone '{bone_name}' parent mismatch: expected {expected_parent}, got {actual_parent}")
    print(f"Verified all {len(bones)} bones and hierarchy preserved")

    # 2. Verify all 13 character mesh parts remain rigidly bound to expected bones
    for part_name in REQUIRED_PARTS:
        part_obj = bpy.data.objects.get(part_name)
        if part_obj is None:
            _fail(f"Missing body part: {part_name}")
        expected_bone = PART_TO_BONE_MAP[part_name]
        if part_obj.parent != arm_obj or part_obj.parent_type != "BONE" or part_obj.parent_bone != expected_bone:
            _fail(f"Part '{part_name}' binding invalid: bone={part_obj.parent_bone}, expected={expected_bone}")
    print(f"Verified all {len(REQUIRED_PARTS)} body parts bound to exact target bones")

    # 3. Verify IK constraints, chain_count=2, IK targets, Pole targets, and Foot orientation constraints
    for side in ("L", "R"):
        ik_target = bpy.data.objects.get(IK_TARGET_NAMES[side])
        pole_target = bpy.data.objects.get(POLE_TARGET_NAMES[side])
        if ik_target is None or pole_target is None:
            _fail(f"Missing IK or Pole target object for side {side}")

        p_shin = arm_obj.pose.bones[f"shin.{side}"]
        ik_con = p_shin.constraints.get(IK_CONSTRAINT_NAMES[side])
        if ik_con is None or ik_con.type != "IK":
            _fail(f"Missing native IK constraint on shin.{side}")
        if ik_con.chain_count != 2:
            _fail(f"Expected chain_count=2 on shin.{side}, got {ik_con.chain_count}")
        if ik_con.target != ik_target or ik_con.pole_target != pole_target:
            _fail(f"IK target/pole mismatch on shin.{side}")

        p_foot = arm_obj.pose.bones[f"foot.{side}"]
        rot_con = p_foot.constraints.get(FOOT_ROT_CONSTRAINT_NAMES[side])
        if rot_con is None or rot_con.type != "COPY_ROTATION" or rot_con.target != ik_target:
            _fail(f"Missing or invalid foot orientation constraint on foot.{side}")
        if arm_obj.data.bones[f"foot.{side}"].use_inherit_rotation:
            _fail(f"foot.{side} should have use_inherit_rotation=False for independent foot orientation")
    print("Verified L/R native IK constraints (chain_count=2), pole targets, and foot orientation controls")

    # 4. Pose Test 1: Neutral Standing Pose
    reset_leg_ik(arm_obj)
    neutral_l = get_leg_ik_state(arm_obj, "L")
    neutral_r = get_leg_ik_state(arm_obj, "R")
    neutral_centers = {name: get_part_world_center(name) for name in REQUIRED_PARTS}
    print(
        f"Pose 1 (Neutral): L_err={neutral_l['target_error']:.5f}m, Foot_L_minZ={neutral_l['foot_min_z']:.6f}m | "
        f"R_err={neutral_r['target_error']:.5f}m, Foot_R_minZ={neutral_r['foot_min_z']:.6f}m"
    )
    if neutral_l["target_error"] > 0.005 or neutral_r["target_error"] > 0.005:
        _fail(f"Neutral IK target error exceeded 5mm: L={neutral_l['target_error']}, R={neutral_r['target_error']}")
    if abs(neutral_l["foot_min_z"]) > 1e-3 or abs(neutral_r["foot_min_z"]) > 1e-3:
        _fail(f"Neutral stance feet not grounded at Z=0: L={neutral_l['foot_min_z']}, R={neutral_r['foot_min_z']}")

    # 5. Pose Test 2: Left Foot Lifted (verify L bends forward, R stays completely stationary)
    reset_leg_ik(arm_obj)
    lift_l = set_foot_ik_target(arm_obj, "L", (start_x - HIP_X_OFFSET, start_y + 0.18, start_z + 0.28))
    stay_r = get_leg_ik_state(arm_obj, "R")
    r_disp = max(
        (get_part_world_center(p) - neutral_centers[p]).length
        for p in ("UpperLeg_R", "LowerLeg_R", "Foot_R")
    )
    l_disp = min(
        (get_part_world_center(p) - neutral_centers[p]).length
        for p in ("UpperLeg_L", "LowerLeg_L", "Foot_L")
    )
    print(
        f"Pose 2 (Left Lift): L_err={lift_l['target_error']:.5f}m, L_knee_flex={lift_l['knee_flexion_deg']:.2f}deg, "
        f"L_knee_fwd_y={lift_l['knee_forward_y']:+.4f}m, Foot_L_minZ={lift_l['foot_min_z']:.4f}m | "
        f"R_max_disp={r_disp:.6f}m, Foot_R_minZ={stay_r['foot_min_z']:.6f}m"
    )
    if lift_l["target_error"] > 0.005:
        _fail(f"Left lift target error too large: {lift_l['target_error']}")
    if lift_l["knee_forward_y"] <= 0.05 or lift_l["knee_flexion_deg"] < 30.0:
        _fail(f"Left knee did not bend forward properly: fwd_y={lift_l['knee_forward_y']}, flex={lift_l['knee_flexion_deg']}")
    if l_disp < 0.05:
        _fail(f"Left leg mesh parts did not follow IK motion: min disp={l_disp}")
    if r_disp > 1e-4 or abs(stay_r["foot_min_z"]) > 1e-3:
        _fail(f"Right leg moved or lost grounding during Left foot lift: r_disp={r_disp}, minZ={stay_r['foot_min_z']}")

    # 6. Pose Test 3: Right Foot Lifted (verify R bends forward, L stays completely stationary)
    reset_leg_ik(arm_obj)
    lift_r = set_foot_ik_target(arm_obj, "R", (start_x + HIP_X_OFFSET, start_y + 0.18, start_z + 0.28))
    stay_l = get_leg_ik_state(arm_obj, "L")
    l_stay_disp = max(
        (get_part_world_center(p) - neutral_centers[p]).length
        for p in ("UpperLeg_L", "LowerLeg_L", "Foot_L")
    )
    r_move_disp = min(
        (get_part_world_center(p) - neutral_centers[p]).length
        for p in ("UpperLeg_R", "LowerLeg_R", "Foot_R")
    )
    print(
        f"Pose 3 (Right Lift): R_err={lift_r['target_error']:.5f}m, R_knee_flex={lift_r['knee_flexion_deg']:.2f}deg, "
        f"R_knee_fwd_y={lift_r['knee_forward_y']:+.4f}m, Foot_R_minZ={lift_r['foot_min_z']:.4f}m | "
        f"L_max_disp={l_stay_disp:.6f}m, Foot_L_minZ={stay_l['foot_min_z']:.6f}m"
    )
    if lift_r["target_error"] > 0.005:
        _fail(f"Right lift target error too large: {lift_r['target_error']}")
    if lift_r["knee_forward_y"] <= 0.05 or lift_r["knee_flexion_deg"] < 30.0:
        _fail(f"Right knee did not bend forward properly: fwd_y={lift_r['knee_forward_y']}, flex={lift_r['knee_flexion_deg']}")
    if r_move_disp < 0.05:
        _fail(f"Right leg mesh parts did not follow IK motion: min disp={r_move_disp}")
    if l_stay_disp > 1e-4 or abs(stay_l["foot_min_z"]) > 1e-3:
        _fail(f"Left leg moved or lost grounding during Right foot lift: l_disp={l_stay_disp}, minZ={stay_l['foot_min_z']}")

    # 7. Pose Test 4: Out-of-reach & Sub-ground target clamping
    reset_leg_ik(arm_obj)
    extreme = set_foot_ik_target(
        arm_obj, "L", (start_x - HIP_X_OFFSET, start_y + 2.5, start_z - 0.60), clamp_reach=True, clamp_ground=True
    )
    hip_dist = (extreme["applied_world"] - extreme["hip_world"]).length
    print(
        f"Pose 4 (Out-of-reach clamp): hip_dist={hip_dist:.4f}m (max={MAX_LEG_REACH:.2f}m), "
        f"clamped_reach={extreme['clamped_reach']}, clamped_ground={extreme['clamped_ground']}, "
        f"target_err={extreme['target_error']:.5f}m, Foot_L_minZ={extreme['foot_min_z']:.6f}m"
    )
    if not extreme["clamped_reach"] or not extreme["clamped_ground"]:
        _fail("Out-of-reach/sub-ground target was not clamped")
    if hip_dist > MAX_LEG_REACH + 1e-4 or extreme["target_error"] > 0.005 or extreme["foot_min_z"] < -1e-3:
        _fail(f"Clamped target produced invalid result: dist={hip_dist}, err={extreme['target_error']}, minZ={extreme['foot_min_z']}")

    print("[VERIFY_PASSED] Task 4C two-bone leg IK and pose control verification completed.")
    print("=== END TASK 4C LEG IK REOPEN VERIFICATION ===")


if __name__ == "__main__":
    verify()
