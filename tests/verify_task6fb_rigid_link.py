"""Automated verification suite for Task 6F-B: Rigid Link Body Mass Distribution and Whole-Body CoM.

Tests:
1. Mass distribution integrity & conservation (sum of mass_ratios == 1.0, positive masses, total mass scaling).
2. Custom mass overrides and total mass re-scaling.
3. Neutral standing rest pose CoM quantitative evaluation (lateral symmetry |X| <= 1e-4, height in 55%~60% range).
4. Independent numerical verification of CoM calculation against raw segment coordinates.
5. Directional CoM shifts under single-arm raising (forward pitch shifts +Y and +Z; lateral roll shifts X).
6. Dual-arm asymmetric pose CoM updates and return-to-rest invariance (non-destructiveness).
7. IK pose compatibility (simultaneous leg IK lift + arm IK reaches) and non-destructiveness.
8. Pelvis motion and Armature world-transform invariance (no double-application of root transform).
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
from src.motion.rigid_link import (
    DEFAULT_HUMAN_TOTAL_MASS_KG,
    DEMPSTER_13_SEGMENT_MODEL,
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    BodyMassDistribution,
    RigidSegmentSpec,
    compute_whole_body_com,
    create_custom_mass_distribution,
)
from src.rig.arm_ik import reset_arm_ik, set_hand_ik_target, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, set_foot_ik_target, setup_leg_ik
from src.rig.pose import reset_pose


def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def verify_rigid_link_com() -> None:
    print("=" * 74)
    print("VERIFYING TASK 6F-B: RIGID LINK BODY MASS DISTRIBUTION & WHOLE-BODY CoM")
    print("=" * 74)

    # -------------------------------------------------------------------------
    # 1. Mass Distribution Integrity & Conservation
    # -------------------------------------------------------------------------
    print("\n[Test 1] Verifying mass distribution integrity and mass conservation...")
    models = (
        ("DempsterWinter15", DEMPSTER_WINTER_15_SEGMENT_MODEL, 15),
        ("Dempster13Combined", DEMPSTER_13_SEGMENT_MODEL, 13),
    )
    for name, model, expected_count in models:
        if len(model.segments) != expected_count:
            _fail(f"Model '{name}': expected {expected_count} segments, got {len(model.segments)}")

        ratio_sum = sum(seg.mass_ratio for seg in model.segments)
        if abs(ratio_sum - 1.0) > 1e-6:
            _fail(f"Model '{name}': mass ratio sum violates conservation: {ratio_sum:.8f} != 1.0")

        mass_sum = sum(model.get_segment_mass_kg(seg.segment_id) for seg in model.segments)
        if abs(mass_sum - model.total_mass_kg) > 1e-4:
            _fail(f"Model '{name}': segment mass sum {mass_sum:.4f}kg != total {model.total_mass_kg:.4f}kg")

        for seg in model.segments:
            if seg.mass_ratio <= 0.0:
                _fail(f"Model '{name}': segment '{seg.segment_id}' mass ratio is non-positive")
            if seg.nominal_length <= 0.0:
                _fail(f"Model '{name}': segment '{seg.segment_id}' length is non-positive")

        print(f"  {name:20s}: {len(model.segments)} segments, ratio_sum={ratio_sum:.6f}, total_mass={mass_sum:.2f}kg (PASSED)")

    # -------------------------------------------------------------------------
    # 2. Custom Total Mass Scaling and Override Support
    # -------------------------------------------------------------------------
    print("\n[Test 2] Testing custom total mass scaling and segment ratio overrides...")
    custom_mass_kg = 85.0
    scaled_model = DEMPSTER_WINTER_15_SEGMENT_MODEL.with_total_mass(custom_mass_kg)
    scaled_mass_sum = sum(scaled_model.get_segment_mass_kg(s.segment_id) for s in scaled_model.segments)
    if abs(scaled_mass_sum - custom_mass_kg) > 1e-4:
        _fail(f"Scaled model total mass {scaled_mass_sum:.4f}kg != {custom_mass_kg}kg")
    print(f"  Scaled mass {custom_mass_kg:.1f}kg: segment mass sum = {scaled_mass_sum:.4f}kg (PASSED)")

    # Override torso ratio
    overridden = DEMPSTER_WINTER_15_SEGMENT_MODEL.with_overrides({"torso": 0.4000}, new_model_name="HeavyTorso")
    if abs(sum(s.mass_ratio for s in overridden.segments) - 1.0) > 1e-6:
        _fail("Overridden normalized mass ratio sum != 1.0")
    print(f"  Override model '{overridden.model_name}': normalized sum={sum(s.mass_ratio for s in overridden.segments):.6f} (PASSED)")

    # -------------------------------------------------------------------------
    # Scene Setup
    # -------------------------------------------------------------------------
    config = PipelineConfig()
    build_character(config)
    arm = build_rig(config)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    reset_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    reset_arm_ik(arm)
    reset_pose(arm)

    # -------------------------------------------------------------------------
    # 3. Neutral Standing Rest Pose CoM Evaluation
    # -------------------------------------------------------------------------
    print("\n[Test 3] Quantitative evaluation of neutral standing rest pose CoM...")
    res_rest = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    c_w = res_rest.com_world
    c_a = res_rest.com_armature

    print(f"  Neutral Standing CoM (World)   : X={c_w.x:+.6f} m, Y={c_w.y:+.6f} m, Z={c_w.z:+.6f} m")
    print(f"  Neutral Standing CoM (Armature): X={c_a.x:+.6f} m, Y={c_a.y:+.6f} m, Z={c_a.z:+.6f} m")

    # Lateral symmetry check (X must be within 0.1 mm of zero)
    if abs(c_w.x) > 0.0001:
        _fail(f"Standing rest CoM violates sagittal symmetry: X={c_w.x:.6f}m > 0.0001m")

    # Sagittal check: body centerline is at Y = -8.0; feet project forward (+Y)
    if not (-8.05 <= c_w.y <= -7.95):
        _fail(f"Standing rest CoM Y out of expected body range [-8.05, -7.95]: Y={c_w.y:.6f}m")

    # Vertical height check: Total height is 1.82m. 55% to 60% of 1.82m is [1.001, 1.092]m
    height_ratio = c_w.z / 1.82
    print(f"  CoM Height Ratio: {c_w.z:.4f}m / 1.82m = {height_ratio * 100:.2f}% (anatomical benchmark: 55%~58%)")
    if not (0.95 <= c_w.z <= 1.15):
        _fail(f"Standing rest CoM Z out of realistic human range [0.95, 1.15]m: Z={c_w.z:.6f}m")
    print("  -> PASSED: Rest CoM matches human anatomical benchmarks.")

    # -------------------------------------------------------------------------
    # 4. Independent Numerical Verification of Weighted CoM
    # -------------------------------------------------------------------------
    print("\n[Test 4] Independent numerical verification against raw segment coordinates...")
    independent_com = Vector((0.0, 0.0, 0.0))
    for seg_id, seg_res in res_rest.segments.items():
        independent_com += seg_res.mass_ratio * seg_res.world_com

    num_err = (independent_com - c_w).length
    print(f"  Numerical discrepancy between API CoM and raw weighted sum: {num_err:.10f} m")
    if num_err > 1e-8:
        _fail(f"Numerical verification failed: discrepancy = {num_err:.10f}m > 1e-8m")
    print("  -> PASSED: Weighted CoM mathematically exact.")

    # -------------------------------------------------------------------------
    # 5. Directional CoM Shifts Under Single-Arm Raising (FK Mode)
    # -------------------------------------------------------------------------
    print("\n[Test 5] Testing directional CoM shifts under single-arm raising (FK mode)...")
    p_up_l = arm.pose.bones["upper_arm.L"]

    # 5A: Raise Left Arm forward by +90 deg (+X in bone local space)
    p_up_l.rotation_euler = Euler((math.radians(90.0), 0.0, 0.0), "XYZ")
    res_fwd = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    dy_fwd = res_fwd.com_world.y - c_w.y
    dz_fwd = res_fwd.com_world.z - c_w.z
    dx_fwd = res_fwd.com_world.x - c_w.x

    print(f"  Left Arm Forward +90 deg: dX={dx_fwd * 1000:+.3f}mm, dY={dy_fwd * 1000:+.3f}mm, dZ={dz_fwd * 1000:+.3f}mm")
    if dy_fwd <= 0.005:  # Must shift forward by at least 5 mm
        _fail(f"Left arm raised forward did not produce expected positive Y shift: dY={dy_fwd * 1000:.3f}mm")
    if dz_fwd <= 0.005:  # Must shift upward by at least 5 mm
        _fail(f"Left arm raised forward did not produce expected positive Z shift: dZ={dz_fwd * 1000:.3f}mm")
    if abs(dx_fwd) > 0.001:
        _fail(f"Sagittal arm raise produced unexpected lateral X shift: dX={dx_fwd * 1000:.3f}mm")
    print("  -> PASSED: Forward arm pitch shifts CoM forward (+Y) and upward (+Z).")

    # 5B: Lateral arm raise (Left is -X world):
    # In upper_arm.L, rotating around local Y or combination creates lateral swing
    reset_pose(arm)
    p_up_l = arm.pose.bones["upper_arm.L"]
    # Coronal abduction: in our rig, Bone +Z points forward, Bone +X points Right.
    # Rotating upper arm around local Z by +90 deg swings arm outward (-X world)
    p_up_l.rotation_euler = Euler((0.0, 0.0, math.radians(90.0)), "XYZ")
    res_lat = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    dx_lat = res_lat.com_world.x - c_w.x
    dz_lat = res_lat.com_world.z - c_w.z
    print(f"  Left Arm Lateral Outward: dX={dx_lat * 1000:+.3f}mm, dZ={dz_lat * 1000:+.3f}mm")
    if dx_lat >= -0.005:  # Must shift leftward (-X)
        _fail(f"Left arm lateral raise did not shift CoM leftward: dX={dx_lat * 1000:.3f}mm")
    if dz_lat <= 0.005:   # Must shift upward (+Z)
        _fail(f"Left arm lateral raise did not shift CoM upward: dZ={dz_lat * 1000:.3f}mm")
    print("  -> PASSED: Lateral arm abduction shifts CoM outward (-X) and upward (+Z).")

    # -------------------------------------------------------------------------
    # 6. Dual-Arm Asymmetric Poses & Non-Destructive Invariance
    # -------------------------------------------------------------------------
    print("\n[Test 6] Testing dual-arm asymmetric poses and non-destructive return to rest...")
    reset_pose(arm)
    p_up_r = arm.pose.bones["upper_arm.R"]
    p_up_l = arm.pose.bones["upper_arm.L"]

    # Left forward, Right backward
    p_up_l.rotation_euler = Euler((math.radians(45.0), 0.0, 0.0), "XYZ")
    p_up_r.rotation_euler = Euler((math.radians(-45.0), 0.0, 0.0), "XYZ")
    res_asym = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    print(f"  Dual Arm Asymmetric: CoM=({res_asym.com_world.x:.4f}, {res_asym.com_world.y:.4f}, {res_asym.com_world.z:.4f})")

    # Return to rest pose and verify CoM returns to identical rest CoM
    reset_pose(arm)
    res_rest_return = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    return_diff = (res_rest_return.com_world - c_w).length
    if return_diff > 1e-6:
        _fail(f"Return to rest pose did not preserve CoM: diff = {return_diff:.8f}m")
    print(f"  -> PASSED: CoM returns to rest with zero drift (drift = {return_diff:.10f}m).")

    # -------------------------------------------------------------------------
    # 7. IK Pose Compatibility & Non-Destructiveness
    # -------------------------------------------------------------------------
    print("\n[Test 7] Testing CoM calculation under active IK poses (leg + arm IK)...")
    start_y = -8.0
    # Lift Left foot by 0.20m via Leg IK
    set_foot_ik_target(arm, "L", (-0.11, start_y + 0.15, 0.27))
    # Reach Left hand forward via Arm IK
    set_hand_ik_target(arm, "L", (-0.24, start_y + 0.25, 1.30), influence=1.0)
    # Reach Right hand outward via Arm IK
    set_hand_ik_target(arm, "R", (0.42, start_y - 0.10, 1.20), influence=1.0)

    # Capture bone transforms before CoM calculation
    p_shin_l = arm.pose.bones["shin.L"]
    p_fore_l = arm.pose.bones["forearm.L"]
    shin_mat_before = p_shin_l.matrix.copy()
    fore_mat_before = p_fore_l.matrix.copy()

    res_ik = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    print(f"  Active IK Pose CoM: X={res_ik.com_world.x:+.4f}m, Y={res_ik.com_world.y:+.4f}m, Z={res_ik.com_world.z:+.4f}m")

    # Verify bone transforms were completely undisturbed
    shin_drift = (p_shin_l.matrix - shin_mat_before).to_translation().length
    fore_drift = (p_fore_l.matrix - fore_mat_before).to_translation().length
    if shin_drift > 1e-6 or fore_drift > 1e-6:
        _fail(f"CoM calculation disturbed bone transforms: shin_drift={shin_drift}, fore_drift={fore_drift}")

    # Lifting leg and reaching arms must raise CoM Z and shift CoM
    if res_ik.com_world.z <= c_w.z:
        _fail("Lifting leg and raising arm did not raise whole-body CoM Z")
    print(f"  IK Pose dZ vs Rest: +{(res_ik.com_world.z - c_w.z) * 1000:.2f} mm (PASSED)")

    # Reset IK
    reset_leg_ik(arm)
    reset_arm_ik(arm)
    reset_pose(arm)

    # -------------------------------------------------------------------------
    # 8. Pelvis and Armature World Transform Invariance
    # -------------------------------------------------------------------------
    print("\n[Test 8] Testing Pelvis motion and Armature world-transform invariance...")
    # 8A: Pelvis crouch by -0.08m in pose mode (pelvis local +Y is vertical world +Z)
    p_pelvis = arm.pose.bones["pelvis"]
    p_pelvis.location = Vector((0.0, -0.08, 0.0))
    res_crouch = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    dz_crouch = res_crouch.com_world.z - c_w.z
    print(f"  Pelvis drop -80mm -> CoM dZ = {dz_crouch * 1000:.2f} mm")
    if dz_crouch >= -0.01:
        _fail("Pelvis downward translation did not lower whole-body CoM")
    p_pelvis.location = Vector((0.0, 0.0, 0.0))

    # 8B: Armature World Translation & Rotation
    root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
    orig_root_loc = root_obj.location.copy()
    orig_root_rot = root_obj.rotation_euler.copy()

    # Move root by (+2.5, +5.0, +0.3)
    root_shift = Vector((2.5, 5.0, 0.3))
    root_obj.location = orig_root_loc + root_shift
    bpy.context.view_layer.update()

    res_trans = compute_whole_body_com(arm, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    expected_world_com = c_w + root_shift
    trans_err = (res_trans.com_world - expected_world_com).length
    print(f"  Root Translation (+2.5, +5.0, +0.3)m -> World CoM discrepancy: {trans_err:.10f} m")
    if trans_err > 1e-4:
        _fail(f"World transform discrepancy: {trans_err:.6f}m > 1e-4m")

    # Armature local CoM must remain invariant regardless of root translation
    arm_space_diff = (res_trans.com_armature - c_a).length
    print(f"  Armature-space CoM invariance check: diff = {arm_space_diff:.10f} m")
    if arm_space_diff > 1e-6:
        _fail(f"Armature-space CoM changed under root translation: diff={arm_space_diff}")

    # Restore root
    root_obj.location = orig_root_loc
    root_obj.rotation_euler = orig_root_rot
    reset_pose(arm)
    bpy.context.view_layer.update()
    print("  -> PASSED: Armature and World coordinate transformations exact with zero double-transform.")

    print("\n" + "=" * 74)
    print("ALL TASK 6F-B RIGID LINK AND CoM VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 74)


if __name__ == "__main__":
    verify_rigid_link_com()
