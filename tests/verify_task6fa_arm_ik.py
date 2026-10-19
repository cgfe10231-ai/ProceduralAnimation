"""Automated verification suite for Task 6F-A: Independent Arm IK and World Space Control.

Tests:
1. 19-bone hierarchy and bone naming preservation.
2. Creation and initial state of arm IK and rotation constraints with default influence = 0.0 (FK pass-through).
3. Bilateral independent world-space reaching across multiple spatial targets (target error <= 0.001 m).
4. Strict bone length preservation (zero stretching, upper_arm == 0.30m, forearm == 0.26m).
5. Simultaneous bilateral targets without cross-arm interference.
6. Decoupled 3D hand orientation control (zero wrist position drift, rotation error <= 0.1 deg).
7. Elbow pole swivel control (predictable elbow repositioning with zero wrist position drift).
8. Unreachable target handling (clamped vs unclamped, is_reachable=False, zero bone stretching).
9. Full reset and influence toggle verification.
"""

import math
import os
import sys

import bpy
from mathutils import Euler, Matrix, Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    DEFAULT_POLE_BACKWARD_OFFSET,
    DEFAULT_POLE_OUTWARD_OFFSET,
    FOREARM_LENGTH,
    HAND_LENGTH,
    HAND_ROT_CONSTRAINT_NAMES,
    MAX_ARM_REACH,
    MIN_ARM_REACH,
    SHOULDER_REST_Z,
    SHOULDER_X_OFFSET,
    UPPER_ARM_LENGTH,
    WRIST_REST_Z,
    get_arm_ik_state,
    reset_arm_ik,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.builder import BONE_HIERARCHY, bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify_arm_ik() -> None:
    print("=" * 74)
    print("VERIFYING TASK 6F-A: INDEPENDENT ARM IK AND WORLD SPACE CONTROL")
    print("=" * 74)

    config = PipelineConfig()
    build_character(config)
    arm = build_rig(config)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    reset_leg_ik(arm)

    # -------------------------------------------------------------------------
    # 1. Verify Armature and Bone Hierarchy Preservation
    # -------------------------------------------------------------------------
    print("\n[Test 1] Verifying 19-bone hierarchy and naming preservation...")
    bones = arm.data.bones
    if len(bones) != 19:
        _fail(f"Expected 19 bones, found {len(bones)}")
    for bname in ("shoulder.L", "upper_arm.L", "forearm.L", "hand.L",
                  "shoulder.R", "upper_arm.R", "forearm.R", "hand.R"):
        if bname not in bones:
            _fail(f"Missing required arm bone '{bname}'")
    print("  -> PASSED: All 19 bones and arm hierarchies verified.")

    # -------------------------------------------------------------------------
    # 2. Setup Arm IK with default influence = 0.0 (FK Pass-through)
    # -------------------------------------------------------------------------
    print("\n[Test 2] Setting up Arm IK and verifying default FK pass-through...")
    controls = setup_arm_ik(arm, initial_influence=0.0)
    for name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
        obj = bpy.data.objects.get(name)
        if obj is None:
            _fail(f"Control empty '{name}' was not created")

    # Verify constraints have influence == 0.0
    for side in ("L", "R"):
        p_fore = arm.pose.bones[f"forearm.{side}"]
        p_hand = arm.pose.bones[f"hand.{side}"]
        ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
        rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side])
        if ik_con is None or ik_con.influence != 0.0:
            _fail(f"IK constraint on forearm.{side} does not have initial influence 0.0")
        if rot_con is None or rot_con.influence != 0.0:
            _fail(f"Rotation constraint on hand.{side} does not have initial influence 0.0")

    # Test FK swing: set FK pose on upper arm and verify hand moves naturally
    p_up_l = arm.pose.bones["upper_arm.L"]
    p_up_l.rotation_euler = Euler((math.radians(30.0), 0.0, 0.0), "XYZ")
    bpy.context.view_layer.update()
    fk_wrist_y = (arm.matrix_world @ p_fore.tail).y
    if abs(fk_wrist_y - (-8.0)) < 0.01:
        _fail("FK rotation had no effect when IK influence is 0.0")
    print(f"  -> PASSED: Default influence = 0.0 preserves FK mode (wrist swung to Y={fk_wrist_y:.4f}m).")

    # Reset pose before IK testing
    reset_pose(arm)
    reset_arm_ik(arm)

    # -------------------------------------------------------------------------
    # 3. Bilateral Independent World Space Targets across Multiple Poses
    # -------------------------------------------------------------------------
    print("\n[Test 3] Testing independent reachable world space targets...")
    start_y = -8.0  # CharacterRoot Y coordinate

    # Test targets for Left arm (shoulder is at X=-0.24, Y=-8.0, Z=1.54)
    left_targets = [
        # (name, (x, y, z), max_err)
        ("Forward reach", (-0.24, start_y + 0.25, 1.25)),
        ("Low forward reach", (-0.24, start_y + 0.18, 1.05)),
        ("Outward reach", (-0.45, start_y + 0.05, 1.30)),
        ("Chest touch", (-0.12, start_y + 0.15, 1.35)),
        ("High forward reach", (-0.24, start_y + 0.30, 1.50)),
    ]

    for name, tgt_xyz in left_targets:
        res = set_hand_ik_target(arm, "L", tgt_xyz, influence=1.0)
        err = res["target_error"]
        up_len = res["upper_arm_length"]
        fore_len = res["forearm_length"]
        flex = res["elbow_flexion_deg"]

        if err > 0.001:
            _fail(f"Left arm '{name}' target error too high: {err:.6f}m > 0.001m")
        if abs(up_len - UPPER_ARM_LENGTH) > 1e-4:
            _fail(f"Upper arm stretched/compressed: {up_len:.6f}m != {UPPER_ARM_LENGTH}m")
        if abs(fore_len - FOREARM_LENGTH) > 1e-4:
            _fail(f"Forearm stretched/compressed: {fore_len:.6f}m != {FOREARM_LENGTH}m")
        print(f"  Left '{name}': err={err * 1000:.3f}mm, up_len={up_len:.4f}m, fore_len={fore_len:.4f}m, flexion={flex:.1f}deg")

    # Test targets for Right arm (shoulder is at X=+0.24, Y=-8.0, Z=1.54)
    right_targets = [
        ("Forward reach", (0.24, start_y + 0.25, 1.25)),
        ("Low forward reach", (0.24, start_y + 0.18, 1.05)),
        ("Outward reach", (0.45, start_y + 0.05, 1.30)),
        ("Chest touch", (0.12, start_y + 0.15, 1.35)),
        ("High forward reach", (0.24, start_y + 0.30, 1.50)),
    ]

    for name, tgt_xyz in right_targets:
        res = set_hand_ik_target(arm, "R", tgt_xyz, influence=1.0)
        err = res["target_error"]
        up_len = res["upper_arm_length"]
        fore_len = res["forearm_length"]
        flex = res["elbow_flexion_deg"]

        if err > 0.001:
            _fail(f"Right arm '{name}' target error too high: {err:.6f}m > 0.001m")
        if abs(up_len - UPPER_ARM_LENGTH) > 1e-4:
            _fail(f"Right upper arm stretched/compressed: {up_len:.6f}m != {UPPER_ARM_LENGTH}m")
        if abs(fore_len - FOREARM_LENGTH) > 1e-4:
            _fail(f"Right forearm stretched/compressed: {fore_len:.6f}m != {FOREARM_LENGTH}m")
        print(f"  Right '{name}': err={err * 1000:.3f}mm, up_len={up_len:.4f}m, fore_len={fore_len:.4f}m, flexion={flex:.1f}deg")
    print("  -> PASSED: All bilateral reachable targets achieved with < 1mm error and 0 bone stretching.")

    # -------------------------------------------------------------------------
    # 4. Simultaneous Bilateral Targets with Zero Cross-talk
    # -------------------------------------------------------------------------
    print("\n[Test 4] Testing simultaneous bilateral targets with zero cross-talk...")
    tgt_l = (-0.28, start_y + 0.20, 1.30)
    tgt_r = (0.35, start_y - 0.10, 1.15)

    set_hand_ik_target(arm, "L", tgt_l, influence=1.0)
    set_hand_ik_target(arm, "R", tgt_r, influence=1.0)

    st_l = get_arm_ik_state(arm, "L")
    st_r = get_arm_ik_state(arm, "R")

    if st_l["target_error"] > 0.001:
        _fail(f"Left target error when both active: {st_l['target_error']:.6f}m")
    if st_r["target_error"] > 0.001:
        _fail(f"Right target error when both active: {st_r['target_error']:.6f}m")

    # Record Left wrist position, then modify Right target drastically
    l_wrist_before = st_l["wrist_world"].copy()
    tgt_r_new = (0.20, start_y + 0.35, 1.45)
    set_hand_ik_target(arm, "R", tgt_r_new, influence=1.0)

    st_l_after = get_arm_ik_state(arm, "L")
    cross_talk = (st_l_after["wrist_world"] - l_wrist_before).length
    if cross_talk > 1e-5:
        _fail(f"Cross-talk detected on Left arm when Right changed: drift = {cross_talk:.6f}m")
    print(f"  -> PASSED: Zero cross-arm interference (cross-talk drift = {cross_talk:.8f}m).")

    # -------------------------------------------------------------------------
    # 5. Decoupled 3D Hand Orientation Control
    # -------------------------------------------------------------------------
    print("\n[Test 5] Testing decoupled 3D hand orientation control...")
    fixed_pos = (-0.24, start_y + 0.22, 1.25)
    rotations = [
        (0.0, 0.0, 0.0),
        (30.0, -20.0, 45.0),
        (-25.0, 40.0, -15.0),
        (0.0, 60.0, 0.0),
    ]

    for rot_deg in rotations:
        res = set_hand_ik_target(arm, "L", fixed_pos, hand_rotation_deg=rot_deg, influence=1.0)
        pos_err = res["target_error"]
        rot_err = res["rotation_error_deg"]

        if pos_err > 0.001:
            _fail(f"Wrist position shifted during hand rotation {rot_deg}: err={pos_err:.6f}m")
        if rot_err > 0.1:
            _fail(f"Hand orientation mismatch for {rot_deg}: err={rot_err:.4f}deg > 0.1deg")
        print(f"  Hand rot {rot_deg}: pos_err={pos_err * 1000:.3f}mm, rot_err={rot_err:.4f}deg")
    print("  -> PASSED: Hand 3D orientation independently controlled with 0 wrist drift.")

    # -------------------------------------------------------------------------
    # 6. Elbow Pole Swivel Control
    # -------------------------------------------------------------------------
    print("\n[Test 6] Testing elbow pole swivel control without position drift...")
    fixed_hand_pos = (-0.24, start_y + 0.20, 1.25)
    # Set initial pose with default pole
    res1 = set_hand_ik_target(arm, "L", fixed_hand_pos, influence=1.0)
    elbow1 = res1["elbow_world"].copy()
    wrist1 = res1["wrist_world"].copy()

    # Move pole target outward (-X) and upward (+Z)
    pole_alt = (-0.55, start_y - 0.35, 1.45)
    res2 = set_hand_ik_target(arm, "L", fixed_hand_pos, pole_world_xyz=pole_alt, influence=1.0)
    elbow2 = res2["elbow_world"].copy()
    wrist2 = res2["wrist_world"].copy()

    wrist_drift = (wrist2 - wrist1).length
    elbow_movement = (elbow2 - elbow1).length

    if wrist_drift > 1e-4:
        _fail(f"Wrist drifted during elbow swivel: {wrist_drift:.6f}m > 1e-4m")
    if elbow_movement < 0.03:
        _fail(f"Elbow did not move in response to pole target change: {elbow_movement:.6f}m < 0.03m")
    print(f"  Wrist drift: {wrist_drift * 1000:.4f}mm, Elbow movement: {elbow_movement * 100:.2f}cm")
    print("  -> PASSED: Elbow pole swivels arm predictably with zero wrist drift.")

    # -------------------------------------------------------------------------
    # 7. Unreachable Target Clamping & Non-Stretching Guarantee
    # -------------------------------------------------------------------------
    print("\n[Test 7] Testing unreachable target handling and non-stretching guarantee...")
    # Shoulder is at (-0.24, -8.0, 1.54). Reaching to Y=-7.10 is 0.90m > 0.56m
    out_of_reach_pos = (-0.24, start_y + 0.90, 1.54)

    # 7A: With clamp_reach=True
    res_clamped = set_hand_ik_target(arm, "L", out_of_reach_pos, clamp_reach=True, influence=1.0)
    if res_clamped["is_reachable"]:
        _fail("Expected is_reachable=False for out-of-reach target")
    if not res_clamped["clamped_reach"]:
        _fail("Expected clamped_reach=True when clamp_reach=True")
    applied_dist = (res_clamped["applied_world"] - res_clamped["shoulder_world"]).length
    if abs(applied_dist - MAX_ARM_REACH) > 1e-4:
        _fail(f"Applied target not clamped to MAX_ARM_REACH: {applied_dist:.4f}m != {MAX_ARM_REACH}m")
    if abs(res_clamped["upper_arm_length"] - UPPER_ARM_LENGTH) > 1e-4:
        _fail(f"Upper arm stretched: {res_clamped['upper_arm_length']:.6f}m")
    if abs(res_clamped["forearm_length"] - FOREARM_LENGTH) > 1e-4:
        _fail(f"Forearm stretched: {res_clamped['forearm_length']:.6f}m")
    print(f"  Clamp=True: is_reachable={res_clamped['is_reachable']}, clamped={res_clamped['clamped_reach']}, applied_reach={applied_dist:.4f}m")

    # 7B: With clamp_reach=False (unclamped request)
    res_unclamped = set_hand_ik_target(arm, "L", out_of_reach_pos, clamp_reach=False, influence=1.0)
    if res_unclamped["is_reachable"]:
        _fail("Expected is_reachable=False for out-of-reach target")
    if res_unclamped["clamped_reach"]:
        _fail("Expected clamped_reach=False when clamp_reach=False")
    # Even without target clamping, Blender IK with use_stretch=False MUST NOT stretch bones!
    if abs(res_unclamped["upper_arm_length"] - UPPER_ARM_LENGTH) > 1e-4:
        _fail(f"Upper arm stretched under unclamped target: {res_unclamped['upper_arm_length']:.6f}m")
    if abs(res_unclamped["forearm_length"] - FOREARM_LENGTH) > 1e-4:
        _fail(f"Forearm stretched under unclamped target: {res_unclamped['forearm_length']:.6f}m")
    expected_err = 0.90 - MAX_ARM_REACH
    if abs(res_unclamped["target_error"] - expected_err) > 0.01:
        _fail(f"Target error report inaccurate: {res_unclamped['target_error']:.4f}m != {expected_err:.4f}m")
    print(f"  Clamp=False: target_err={res_unclamped['target_error']:.4f}m (expected ~{expected_err:.4f}m), arm_len={res_unclamped['total_arm_length']:.4f}m")
    print("  -> PASSED: Unreachable targets handled strictly without bone stretching.")

    # -------------------------------------------------------------------------
    # 8. Reset and Influence Blending
    # -------------------------------------------------------------------------
    print("\n[Test 8] Testing reset_arm_ik and smooth influence blending...")
    set_hand_ik_target(arm, "L", (-0.24, start_y + 0.25, 1.25), influence=1.0)
    set_hand_ik_target(arm, "R", (0.24, start_y + 0.25, 1.25), influence=1.0)

    # Blend influence to 0.5
    set_arm_ik_influence(arm, "BOTH", influence=0.5)
    st_half_l = get_arm_ik_state(arm, "L")
    if abs(st_half_l["ik_influence"] - 0.5) > 1e-4:
        _fail(f"Influence not set to 0.5: {st_half_l['ik_influence']}")

    # Reset arm IK
    reset_arm_ik(arm)
    st_reset_l = get_arm_ik_state(arm, "L")
    st_reset_r = get_arm_ik_state(arm, "R")
    if st_reset_l["ik_influence"] != 0.0 or st_reset_r["ik_influence"] != 0.0:
        _fail("reset_arm_ik did not restore influence to 0.0")
    print("  -> PASSED: Arm IK influence blending and reset verified.")

    print("\n" + "=" * 74)
    print("ALL TASK 6F-A ARM IK VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 74)


if __name__ == "__main__":
    verify_arm_ik()
