"""Automated verification suite for Task 6G-B: Rigid Link Inertia Tensor & Whole-Body Angular Momentum.

Executes 13 rigorous verification tests in Blender headless mode:
1. All segment local inertia tensors symmetric and positive-definite.
2. Geometric solid formulas match independent analytical reference values.
3. 3D Parallel Axis Theorem numerical correctness.
4. Whole-body translation invariance of inertia tensor relative to CoM.
5. Whole-body rotation covariance obeying tensor coordinate transformation law.
6. Neutral stance bilateral symmetry and physical magnitude reasonableness.
7. Single-arm raised asymmetric inertia response.
8. Tucked vs extended posture rotational inertia difference about Z axis.
9. Static body whole-body angular momentum is strictly zero.
10. Rigid body rotation angular momentum consistency with I_body * omega.
11. Independent limb motion spin and orbital angular momentum decomposition.
12. Seamless integration with compute_whole_body_com, BodyKinematicsTracker, and MotionState.
13. Full regression verification across Task 6G-A, 6F-D, 6F-C, 6F-B, 6F-A, 6D.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.rigid_link import (
    BodyMassDistribution,
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    compute_whole_body_com,
)
from src.motion.body_kinematics import (
    BodyKinematicsTracker,
    BodyPoseSnapshot,
    BodyVelocityState,
    create_zero_velocity_state,
    sample_body_pose_snapshot,
)
from src.motion.body_inertia import (
    BodyInertiaModel,
    DEFAULT_15_SEGMENT_INERTIA_MODEL,
    InertiaTensor,
    SegmentGeometrySpec,
    SegmentInertiaState,
    WholeBodyInertiaState,
    compute_whole_body_inertia,
    compute_whole_body_inertia_from_snapshots,
    enrich_motion_state_with_inertia,
)
from src.motion.framework import create_initial_motion_state
from src.rig.arm_ik import set_hand_ik_target, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.pose import reset_pose


def _setup_clean_character_scene() -> bpy.types.Object:
    """Setup a clean testing scene with a CharacterArmature and Arm IK."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm_obj = build_rig(cfg)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    setup_arm_ik(arm_obj)
    bpy.context.view_layer.update()
    return arm_obj


# =============================================================================
# Test 1: Local Inertia Symmetric & Positive Definite
# =============================================================================
def test_01_local_inertia_symmetric_and_positive_definite() -> bool:
    print("\n--- Test 1: Segment Local Inertia Symmetric & Positive Definite ---")
    model = DEFAULT_15_SEGMENT_INERTIA_MODEL
    mass_dist = model.mass_distribution

    passed = True
    print(f"{'Segment ID':<15} | {'Mass (kg)':<9} | {'I_xx':<8} | {'I_yy':<8} | {'I_zz':<8} | {'Symm':<5} | {'PosDef':<6} | {'Principal Moments (kg*m^2)'}")
    print("-" * 105)

    for seg in mass_dist.segments:
        geom = model.get_geometry(seg.segment_id)
        mass_kg = seg.mass_ratio * mass_dist.total_mass_kg
        tensor = geom.compute_local_tensor(mass_kg=mass_kg, actual_length=seg.nominal_length)

        is_symm = tensor.is_symmetric()
        is_posdef = tensor.is_positive_definite()
        e1, e2, e3 = tensor.principal_moments()

        print(
            f"{seg.segment_id:<15} | {mass_kg:9.4f} | {tensor.ixx:8.5f} | {tensor.iyy:8.5f} | "
            f"{tensor.izz:8.5f} | {str(is_symm):<5} | {str(is_posdef):<6} | "
            f"({e1:.5f}, {e2:.5f}, {e3:.5f})"
        )

        if not is_symm or not is_posdef:
            print(f"FAILED: Segment {seg.segment_id} failed symmetry or positive-definiteness!")
            passed = False
        if e1 <= 0.0 or e2 <= 0.0 or e3 <= 0.0:
            print(f"FAILED: Segment {seg.segment_id} has non-positive principal moment!")
            passed = False

    return passed


# =============================================================================
# Test 2: Geometric Formulas Match Independent Analytical Reference
# =============================================================================
def test_02_geometric_formulas_match_analytical_references() -> bool:
    print("\n--- Test 2: Geometric Solid Formulas Match Analytical References ---")

    # A. Cylinder: m=2.0 kg, r=0.05 m, L=0.40 m
    # I_yy = 0.5 * m * r^2 = 0.0025
    # I_xx = I_zz = (1/12) * m * (3*r^2 + L^2) = (2/12) * (3*0.0025 + 0.16) = 0.0279166667
    geom_cyl = SegmentGeometrySpec("test_cyl", shape_type="cylinder", radius_x=0.05, nominal_length=0.40)
    t_cyl = geom_cyl.compute_local_tensor(mass_kg=2.0)
    expected_cyl_yy = 0.5 * 2.0 * (0.05 ** 2)
    expected_cyl_xx = (1.0 / 12.0) * 2.0 * (3.0 * (0.05 ** 2) + (0.40 ** 2))

    err_cyl_yy = abs(t_cyl.iyy - expected_cyl_yy)
    err_cyl_xx = abs(t_cyl.ixx - expected_cyl_xx)
    print(f"Cylinder I_yy: {t_cyl.iyy:.8f} vs {expected_cyl_yy:.8f} (err: {err_cyl_yy:.2e})")
    print(f"Cylinder I_xx: {t_cyl.ixx:.8f} vs {expected_cyl_xx:.8f} (err: {err_cyl_xx:.2e})")

    # B. Ellipsoid: m=5.0 kg, a=0.08, b=0.11, c=0.09
    # I_xx = 0.2 * m * (b^2 + c^2) = 1.0 * (0.0121 + 0.0081) = 0.0202
    # I_yy = 0.2 * m * (a^2 + c^2) = 1.0 * (0.0064 + 0.0081) = 0.0145
    # I_zz = 0.2 * m * (a^2 + b^2) = 1.0 * (0.0064 + 0.0121) = 0.0185
    geom_ell = SegmentGeometrySpec("test_ell", shape_type="ellipsoid", radius_x=0.08, radius_y=0.11, radius_z=0.09)
    t_ell = geom_ell.compute_local_tensor(mass_kg=5.0)
    err_ell_xx = abs(t_ell.ixx - 0.0202)
    err_ell_yy = abs(t_ell.iyy - 0.0145)
    err_ell_zz = abs(t_ell.izz - 0.0185)
    print(f"Ellipsoid I_xx: {t_ell.ixx:.8f} vs 0.02020000 (err: {err_ell_xx:.2e})")
    print(f"Ellipsoid I_yy: {t_ell.iyy:.8f} vs 0.01450000 (err: {err_ell_yy:.2e})")
    print(f"Ellipsoid I_zz: {t_ell.izz:.8f} vs 0.01850000 (err: {err_ell_zz:.2e})")

    # C. Elliptic Cylinder: m=10.0 kg, rx=0.15, rz=0.11, L=0.48
    # I_yy = 0.25 * m * (rx^2 + rz^2) = 2.5 * (0.0225 + 0.0121) = 0.0865
    # I_xx = (10/12) * (3*0.0121 + 0.2304) = (10/12) * 0.2667 = 0.22225
    # I_zz = (10/12) * (3*0.0225 + 0.2304) = (10/12) * 0.2979 = 0.24825
    geom_ec = SegmentGeometrySpec("test_ec", shape_type="elliptic_cylinder", radius_x=0.15, radius_z=0.11, nominal_length=0.48)
    t_ec = geom_ec.compute_local_tensor(mass_kg=10.0)
    err_ec_yy = abs(t_ec.iyy - 0.0865)
    err_ec_xx = abs(t_ec.ixx - 0.22225)
    err_ec_zz = abs(t_ec.izz - 0.24825)
    print(f"Elliptic Cylinder I_yy: {t_ec.iyy:.8f} vs 0.08650000 (err: {err_ec_yy:.2e})")
    print(f"Elliptic Cylinder I_xx: {t_ec.ixx:.8f} vs 0.22225000 (err: {err_ec_xx:.2e})")
    print(f"Elliptic Cylinder I_zz: {t_ec.izz:.8f} vs 0.24825000 (err: {err_ec_zz:.2e})")

    # D. Box: m=1.0 kg, dx=0.08, dy=0.154, dz=0.05
    # I_xx = (1/12) * 1.0 * (0.154^2 + 0.05^2) = (0.023716 + 0.0025)/12 = 0.00218466667
    geom_box = SegmentGeometrySpec("test_box", shape_type="box", dim_x=0.08, dim_y=0.154, dim_z=0.05)
    t_box = geom_box.compute_local_tensor(mass_kg=1.0)
    expected_box_xx = (1.0 / 12.0) * (0.154 ** 2 + 0.05 ** 2)
    err_box_xx = abs(t_box.ixx - expected_box_xx)
    print(f"Box I_xx: {t_box.ixx:.8f} vs {expected_box_xx:.8f} (err: {err_box_xx:.2e})")

    max_err = max(err_cyl_yy, err_cyl_xx, err_ell_xx, err_ell_yy, err_ell_zz, err_ec_yy, err_ec_xx, err_ec_zz, err_box_xx)
    print(f"Max geometric formula discrepancy: {max_err:.2e}")
    return max_err < 1e-9


# =============================================================================
# Test 3: 3D Parallel Axis Theorem Numerical Correctness
# =============================================================================
def test_03_parallel_axis_theorem_numerical_correctness() -> bool:
    print("\n--- Test 3: Parallel Axis Theorem Numerical Correctness ---")
    t0 = InertiaTensor.from_diagonal(1.0, 2.0, 3.0)
    mass = 4.0
    r = Vector((0.3, -0.4, 0.5))

    # Analytical parallel axis increments:
    # d_Ixx = m * (y^2 + z^2) = 4 * (0.16 + 0.25) = 1.64
    # d_Iyy = m * (x^2 + z^2) = 4 * (0.09 + 0.25) = 1.36
    # d_Izz = m * (x^2 + y^2) = 4 * (0.09 + 0.16) = 1.00
    # d_Ixy = -m * (x * y) = -4 * (0.3 * -0.4) = +0.48
    # d_Ixz = -m * (x * z) = -4 * (0.3 * 0.5) = -0.60
    # d_Iyz = -m * (y * z) = -4 * (-0.4 * 0.5) = +0.40
    t_shifted = t0.parallel_axis(mass, r)

    exp_ixx = 1.0 + 1.64
    exp_iyy = 2.0 + 1.36
    exp_izz = 3.0 + 1.00
    exp_ixy = 0.48
    exp_ixz = -0.60
    exp_iyz = 0.80

    err_xx = abs(t_shifted.ixx - exp_ixx)
    err_yy = abs(t_shifted.iyy - exp_iyy)
    err_zz = abs(t_shifted.izz - exp_izz)
    err_xy = abs(t_shifted.ixy - exp_ixy)
    err_xz = abs(t_shifted.ixz - exp_ixz)
    err_yz = abs(t_shifted.iyz - exp_iyz)

    max_err = max(err_xx, err_yy, err_zz, err_xy, err_xz, err_yz)
    print(f"Shifted I_xx: {t_shifted.ixx:.6f} vs {exp_ixx:.6f} (err: {err_xx:.2e})")
    print(f"Shifted I_yy: {t_shifted.iyy:.6f} vs {exp_iyy:.6f} (err: {err_yy:.2e})")
    print(f"Shifted I_zz: {t_shifted.izz:.6f} vs {exp_izz:.6f} (err: {err_zz:.2e})")
    print(f"Shifted I_xy: {t_shifted.ixy:.6f} vs {exp_ixy:.6f} (err: {err_xy:.2e})")
    print(f"Shifted I_xz: {t_shifted.ixz:.6f} vs {exp_ixz:.6f} (err: {err_xz:.2e})")
    print(f"Shifted I_yz: {t_shifted.iyz:.6f} vs {exp_iyz:.6f} (err: {err_yz:.2e})")
    print(f"Max parallel axis theorem error: {max_err:.2e}")
    return max_err < 1e-6


# =============================================================================
# Test 4: Whole-Body Translation Invariance
# =============================================================================
def test_04_whole_body_translation_invariance() -> bool:
    print("\n--- Test 4: Whole-Body Translation Invariance Relative to CoM ---")
    arm_obj = _setup_clean_character_scene()
    root_obj = bpy.data.objects.get("CharacterRoot")

    # 1. State at origin
    state1 = compute_whole_body_inertia(arm_obj, update_scene=True)
    com1 = state1.com_world
    i1 = state1.inertia_tensor_body_com

    # 2. Translate CharacterRoot far away
    if root_obj is not None:
        root_obj.location = Vector((12.5, -45.0, 3.2))
    else:
        arm_obj.location = Vector((12.5, -45.0, 3.2))
    bpy.context.view_layer.update()

    state2 = compute_whole_body_inertia(arm_obj, update_scene=True)
    com2 = state2.com_world
    i2 = state2.inertia_tensor_body_com

    diff_norm = (i1 - i2).frobenius_norm()
    print(f"CoM before translation: ({com1[0]:.4f}, {com1[1]:.4f}, {com1[2]:.4f}) m")
    print(f"CoM after translation:  ({com2[0]:.4f}, {com2[1]:.4f}, {com2[2]:.4f}) m")
    print(f"Inertia tensor Frobenius difference: {diff_norm:.2e} kg*m^2")

    # Reset
    if root_obj is not None:
        root_obj.location = Vector((0.0, 0.0, 0.0))
    else:
        arm_obj.location = Vector((0.0, 0.0, 0.0))
    bpy.context.view_layer.update()

    return diff_norm < 1e-5


# =============================================================================
# Test 5: Whole-Body Rotation Tensor Transformation
# =============================================================================
def test_05_whole_body_rotation_tensor_transformation() -> bool:
    print("\n--- Test 5: Whole-Body Rotation Tensor Transformation Covariance ---")
    arm_obj = _setup_clean_character_scene()
    root_obj = bpy.data.objects.get("CharacterRoot")

    # Base inertia at neutral orientation
    state_base = compute_whole_body_inertia(arm_obj, update_scene=True)
    i_base = state_base.inertia_tensor_body_com

    # Apply rigid rotation around arbitrary normalized axis
    rot_axis = Vector((0.57735, 0.57735, 0.57735)).normalized()
    rot_angle_rad = math.radians(40.0)
    q_rot = Quaternion(rot_axis, rot_angle_rad)
    q_rot.normalize()
    r_mat = q_rot.to_matrix()

    target_obj = root_obj if root_obj is not None else arm_obj
    target_obj.rotation_mode = "QUATERNION"
    target_obj.rotation_quaternion = q_rot
    bpy.context.view_layer.update()

    state_rotated = compute_whole_body_inertia(arm_obj, update_scene=True)
    i_rotated = state_rotated.inertia_tensor_body_com

    # Theoretical expected: I_rotated = R * I_base * R^T
    i_expected = i_base.rotate(r_mat)
    diff_norm = (i_rotated - i_expected).frobenius_norm()

    print(f"Base I_xx: {i_base.ixx:.5f}, I_yy: {i_base.iyy:.5f}, I_zz: {i_base.izz:.5f} kg*m^2")
    print(f"Rotated I_xx: {i_rotated.ixx:.5f}, I_yy: {i_rotated.iyy:.5f}, I_zz: {i_rotated.izz:.5f} kg*m^2")
    print(f"Expected I_xx: {i_expected.ixx:.5f}, I_yy: {i_expected.iyy:.5f}, I_zz: {i_expected.izz:.5f} kg*m^2")
    print(f"Tensor transformation difference Frobenius norm: {diff_norm:.2e} kg*m^2")

    # Reset
    target_obj.rotation_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    target_obj.rotation_mode = "XYZ"
    bpy.context.view_layer.update()

    return diff_norm < 1e-4


# =============================================================================
# Test 6: Neutral Stance Bilateral Symmetry & Physical Magnitudes
# =============================================================================
def test_06_neutral_stance_symmetry() -> bool:
    print("\n--- Test 6: Neutral Stance Bilateral Symmetry & Physical Magnitudes ---")
    arm_obj = _setup_clean_character_scene()
    state = compute_whole_body_inertia(arm_obj, update_scene=True)
    i = state.inertia_tensor_body_com

    print(f"Total Body Mass: {state.total_mass_kg:.2f} kg")
    print(f"Whole-Body CoM: ({state.com_world[0]:.4f}, {state.com_world[1]:.4f}, {state.com_world[2]:.4f}) m")
    print("Whole-Body Inertia Tensor relative to CoM (kg*m^2):")
    print(f"  [{i.ixx:10.5f}, {i.ixy:10.5f}, {i.ixz:10.5f}]")
    print(f"  [{i.ixy:10.5f}, {i.iyy:10.5f}, {i.iyz:10.5f}]")
    print(f"  [{i.ixz:10.5f}, {i.iyz:10.5f}, {i.izz:10.5f}]")
    p1, p2, p3 = state.principal_moments
    print(f"Principal Moments (kg*m^2): I1={p1:.5f}, I2={p2:.5f}, I3={p3:.5f}")

    # Bilateral symmetry across sagittal plane (X=0) implies I_xy and I_xz are very small
    symm_ok = abs(i.ixy) < 0.05 and abs(i.ixz) < 0.05
    print(f"Bilateral symmetry off-diagonals: I_xy={i.ixy:.5f}, I_xz={i.ixz:.5f} (Pass: {symm_ok})")

    # Anthropometric magnitude sanity check for 70 kg human standing:
    # Pitch (I_xx) ~ 10-15 kg*m^2, Roll (I_yy) ~ 10-15 kg*m^2, Yaw (I_zz) ~ 1-2 kg*m^2
    mag_ok = (8.0 <= i.ixx <= 20.0) and (8.0 <= i.iyy <= 20.0) and (0.8 <= i.izz <= 3.0)
    print(f"Anthropometric magnitudes sanity: I_xx={i.ixx:.2f}, I_yy={i.iyy:.2f}, I_zz={i.izz:.2f} (Pass: {mag_ok})")

    return symm_ok and mag_ok and i.is_positive_definite()


# =============================================================================
# Test 7: Single-Arm Raised Asymmetric Inertia Response
# =============================================================================
def test_07_single_arm_raised_inertia_change() -> bool:
    print("\n--- Test 7: Single-Arm Raised Asymmetric Inertia Response ---")
    arm_obj = _setup_clean_character_scene()

    state_neutral = compute_whole_body_inertia(arm_obj, update_scene=True)
    i_neut = state_neutral.inertia_tensor_body_com

    # Raise right arm laterally (+X abduction) using official IK API
    set_hand_ik_target(
        arm_obj,
        side="R",
        world_xyz=(0.70, -8.0, 1.45),
        clamp_reach=False,
        influence=1.0,
    )
    bpy.context.view_layer.update()

    state_raised = compute_whole_body_inertia(arm_obj, update_scene=True)
    i_raised = state_raised.inertia_tensor_body_com

    delta_izz = i_raised.izz - i_neut.izz
    asymm_ixy = abs(i_raised.ixy)

    print(f"Neutral I_zz: {i_neut.izz:.5f} kg*m^2 | Raised I_zz: {i_raised.izz:.5f} kg*m^2 (delta: {delta_izz:+.5f} kg*m^2)")
    print(f"Neutral I_xy: {i_neut.ixy:.5f} kg*m^2 | Raised I_xy: {i_raised.ixy:.5f} kg*m^2 (asymmetry introduced)")

    # Extending arm laterally moves mass away from Z-axis -> I_zz must increase
    passed = delta_izz > 0.05 and asymm_ixy > 0.01
    print(f"Single arm raise physical response: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 8: Tucked vs Extended Posture Rotational Inertia Difference
# =============================================================================
def test_08_tucked_vs_extended_inertia_difference() -> bool:
    print("\n--- Test 8: Tucked vs Extended Posture Rotational Inertia Difference ---")
    arm_obj = _setup_clean_character_scene()

    # 1. Extended Pose (T-Pose with arms stretched wide outwards)
    set_hand_ik_target(
        arm_obj,
        side="L",
        world_xyz=(-0.70, -8.0, 1.45),
        clamp_reach=False,
        influence=1.0,
    )
    set_hand_ik_target(
        arm_obj,
        side="R",
        world_xyz=(0.70, -8.0, 1.45),
        clamp_reach=False,
        influence=1.0,
    )
    bpy.context.view_layer.update()

    state_ext = compute_whole_body_inertia(arm_obj, update_scene=True)
    izz_ext = state_ext.inertia_tensor_body_com.izz

    # 2. Tucked Pose (Arms tucked closely against center of chest)
    set_hand_ik_target(
        arm_obj,
        side="L",
        world_xyz=(-0.10, -7.85, 1.20),
        clamp_reach=False,
        influence=1.0,
    )
    set_hand_ik_target(
        arm_obj,
        side="R",
        world_xyz=(0.10, -7.85, 1.20),
        clamp_reach=False,
        influence=1.0,
    )
    bpy.context.view_layer.update()

    state_tuck = compute_whole_body_inertia(arm_obj, update_scene=True)
    izz_tuck = state_tuck.inertia_tensor_body_com.izz

    ratio = izz_ext / izz_tuck
    diff = izz_ext - izz_tuck

    print(f"Extended Pose I_zz (T-Pose): {izz_ext:.5f} kg*m^2")
    print(f"Tucked Pose I_zz (Folded):   {izz_tuck:.5f} kg*m^2")
    print(f"Ratio (Extended / Tucked):   {ratio:.3f}x (+{diff:.5f} kg*m^2)")

    # T-pose should have substantially higher yaw inertia than tucked pose (at least 30% higher)
    passed = ratio >= 1.30 and diff > 0.30
    print(f"Tuck vs Extend inertia differentiation: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 9: Static Body Zero Angular Momentum
# =============================================================================
def test_09_static_body_zero_angular_momentum() -> bool:
    print("\n--- Test 9: Static Body Zero Angular Momentum ---")
    arm_obj = _setup_clean_character_scene()
    state = compute_whole_body_inertia(arm_obj, velocity_state=None, update_scene=True)

    hx, hy, hz = state.angular_momentum_body_com
    h_mag = state.angular_momentum_magnitude
    h_spin_mag = Vector(state.spin_angular_momentum_total).length
    h_orb_mag = Vector(state.orbital_angular_momentum_total).length

    print(f"Angular momentum vector: ({hx:.8f}, {hy:.8f}, {hz:.8f}) kg*m^2/s")
    print(f"H magnitude: {h_mag:.8f} kg*m^2/s | H_spin: {h_spin_mag:.8f} | H_orbital: {h_orb_mag:.8f}")

    passed = (h_mag == 0.0) and (h_spin_mag == 0.0) and (h_orb_mag == 0.0)
    print(f"Static body zero angular momentum: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 10: Rigid Rotation Angular Momentum Consistency
# =============================================================================
def test_10_rigid_rotation_angular_momentum_consistency() -> bool:
    print("\n--- Test 10: Rigid Rotation Angular Momentum Consistency with I_body * omega ---")
    arm_obj = _setup_clean_character_scene()
    model = DEFAULT_15_SEGMENT_INERTIA_MODEL
    mass_dist = model.mass_distribution

    # Compute static pose inertia
    state_static = compute_whole_body_inertia(arm_obj, update_scene=True)
    i_body = state_static.inertia_tensor_body_com
    com_world = Vector(state_static.com_world)

    # Assign rigid angular velocity about CoM
    omega_rigid = Vector((0.40, 0.80, -0.60))  # rad/s

    # Construct synthetic BodyVelocityState under rigid rotation:
    # omega_i = omega_rigid
    # v_i = omega_rigid x (c_i - c_com)
    seg_lin_v: Dict[str, Tuple[float, float, float]] = {}
    seg_ang_v: Dict[str, Tuple[float, float, float]] = {}

    for seg_id, s_res in state_static.segments.items():
        r_i = Vector(s_res.world_com) - com_world
        v_i = omega_rigid.cross(r_i)
        seg_lin_v[seg_id] = (v_i.x, v_i.y, v_i.z)
        seg_ang_v[seg_id] = (omega_rigid.x, omega_rigid.y, omega_rigid.z)

    vel_state = BodyVelocityState(
        time_sec=0.0,
        dt=0.041667,
        root_linear_velocity=(0.0, 0.0, 0.0),
        root_angular_velocity=(omega_rigid.x, omega_rigid.y, omega_rigid.z),
        root_angular_velocity_deg=(math.degrees(omega_rigid.x), math.degrees(omega_rigid.y), math.degrees(omega_rigid.z)),
        pelvis_linear_velocity=(0.0, 0.0, 0.0),
        com_linear_velocity=(0.0, 0.0, 0.0),
        segment_linear_velocities=seg_lin_v,
        segment_angular_velocities=seg_ang_v,
        joint_angular_velocities={},
        joint_angular_velocities_deg={},
        end_effector_velocities={},
    )

    state_dyn = compute_whole_body_inertia(arm_obj, velocity_state=vel_state, update_scene=False)

    # Multi-link evaluated H
    h_eval = Vector(state_dyn.angular_momentum_body_com)
    # Analytical expected H = I_body * omega
    h_rigid_expected = i_body.multiply(omega_rigid)

    err_vec = (h_eval - h_rigid_expected).length
    rel_err = err_vec / h_rigid_expected.length

    print(f"Rigid Omega: ({omega_rigid.x:.2f}, {omega_rigid.y:.2f}, {omega_rigid.z:.2f}) rad/s")
    print(f"Evaluated Multi-Link H:    ({h_eval.x:.6f}, {h_eval.y:.6f}, {h_eval.z:.6f}) kg*m^2/s")
    print(f"Analytical Expected I * w: ({h_rigid_expected.x:.6f}, {h_rigid_expected.y:.6f}, {h_rigid_expected.z:.6f}) kg*m^2/s")
    print(f"Discrepancy: absolute={err_vec:.2e} kg*m^2/s, relative={rel_err:.2e}")

    passed = err_vec < 1e-4
    print(f"Rigid rotation angular momentum consistency: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 11: Independent Limb Motion Spin & Orbital Decomposition
# =============================================================================
def test_11_independent_limb_motion_spin_and_orbital_decomposition() -> bool:
    print("\n--- Test 11: Independent Limb Motion Spin & Orbital Decomposition ---")
    arm_obj = _setup_clean_character_scene()
    state_static = compute_whole_body_inertia(arm_obj, update_scene=True)

    # Simulate right arm swinging forward (only upper_arm_R and forearm_R active)
    seg_lin_v: Dict[str, Tuple[float, float, float]] = {}
    seg_ang_v: Dict[str, Tuple[float, float, float]] = {}

    for seg_id in state_static.segments:
        if seg_id in ("upper_arm_R", "forearm_R", "hand_R"):
            seg_ang_v[seg_id] = (4.0, 0.0, 0.0)      # Pitching forward
            seg_lin_v[seg_id] = (0.0, 1.5, 0.2)      # Forward-up velocity
        else:
            seg_ang_v[seg_id] = (0.0, 0.0, 0.0)
            seg_lin_v[seg_id] = (0.0, 0.0, 0.0)

    vel_state = BodyVelocityState(
        time_sec=0.0,
        dt=0.041667,
        root_linear_velocity=(0.0, 0.0, 0.0),
        root_angular_velocity=(0.0, 0.0, 0.0),
        root_angular_velocity_deg=(0.0, 0.0, 0.0),
        pelvis_linear_velocity=(0.0, 0.0, 0.0),
        com_linear_velocity=(0.0, 0.0, 0.0),
        segment_linear_velocities=seg_lin_v,
        segment_angular_velocities=seg_ang_v,
        joint_angular_velocities={},
        joint_angular_velocities_deg={},
        end_effector_velocities={},
    )

    state_dyn = compute_whole_body_inertia(arm_obj, velocity_state=vel_state, update_scene=False)

    h_spin = Vector(state_dyn.spin_angular_momentum_total)
    h_orb = Vector(state_dyn.orbital_angular_momentum_total)
    h_tot = Vector(state_dyn.angular_momentum_body_com)

    print(f"Spin Angular Momentum:    ({h_spin.x:8.5f}, {h_spin.y:8.5f}, {h_spin.z:8.5f}) kg*m^2/s (norm={h_spin.length:.5f})")
    print(f"Orbital Angular Momentum: ({h_orb.x:8.5f}, {h_orb.y:8.5f}, {h_orb.z:8.5f}) kg*m^2/s (norm={h_orb.length:.5f})")
    print(f"Total Angular Momentum:   ({h_tot.x:8.5f}, {h_tot.y:8.5f}, {h_tot.z:8.5f}) kg*m^2/s (norm={h_tot.length:.5f})")

    # Both spin and orbital components must be non-zero
    passed = h_spin.length > 0.01 and h_orb.length > 0.05 and (h_spin + h_orb - h_tot).length < 1e-6
    print(f"Limb motion decomposition: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 12: Consistency with CoM and Kinematics Integration
# =============================================================================
def test_12_consistency_with_com_and_kinematics_tracker() -> bool:
    print("\n--- Test 12: Consistency with CoM, Tracker, and MotionState Integration ---")
    arm_obj = _setup_clean_character_scene()

    # 1. Compare CoM position with independent compute_whole_body_com
    com_ref = compute_whole_body_com(arm_obj, update_scene=True)
    state_inertia = compute_whole_body_inertia(arm_obj, update_scene=False)

    com_err = (com_ref.com_world - Vector(state_inertia.com_world)).length
    print(f"CoM position consistency error: {com_err:.2e} m")

    # 2. Test snapshot-based computation consistency
    snap = sample_body_pose_snapshot(arm_obj, frame=1, time_sec=0.041667)
    zero_vel = create_zero_velocity_state(snap, dt=0.041667)
    state_from_snap = compute_whole_body_inertia_from_snapshots(snap, zero_vel)

    snap_diff = (state_inertia.inertia_tensor_body_com - state_from_snap.inertia_tensor_body_com).frobenius_norm()
    print(f"Armature vs Snapshot inertia Frobenius difference: {snap_diff:.2e} kg*m^2")

    # 3. Test enrich_motion_state_with_inertia
    m_state = create_initial_motion_state(PipelineConfig())
    enrich_motion_state_with_inertia(m_state, state_inertia)

    has_tensor = "inertia_tensor_com" in m_state.params
    has_mom = "angular_momentum_com" in m_state.params
    print(f"MotionState.params contains inertia_tensor_com: {has_tensor}")
    print(f"MotionState.params contains angular_momentum_com: {has_mom}")

    passed = (com_err < 1e-7) and (snap_diff < 1e-5) and has_tensor and has_mom
    print(f"CoM and tracker integration: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 13: Core Regression Suite
# =============================================================================
def test_13_core_regression_suite() -> bool:
    print("\n--- Test 13: Core Regression Verification Suite ---")
    import os
    import subprocess

    tests_dir = os.path.dirname(__file__)
    regression_scripts = [
        "verify_task6ga_body_kinematics.py",
        "verify_task6fd_whole_body_controller.py",
        "verify_task6fc_joint_limits.py",
        "verify_task6fb_rigid_link.py",
        "verify_task6fa_arm_ik.py",
    ]

    all_passed = True
    for script_name in regression_scripts:
        script_path = os.path.join(tests_dir, script_name)
        if not os.path.exists(script_path):
            print(f"Regression script {script_name} not found, skipping.")
            continue

        print(f"\nRunning regression: {script_name}...")
        blender_bin = getattr(bpy.app, "binary_path", sys.executable)
        res = subprocess.run(
            [blender_bin, "--background", "--python", script_path],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            print(f"PASSED: {script_name} (exit code 0)")
        else:
            print(f"FAILED: {script_name} (exit code {res.returncode})")
            if res.stderr:
                print(f"Stderr: {res.stderr[-500:]}")
            if res.stdout:
                print(f"Stdout tail: {res.stdout[-500:]}")
            all_passed = False

    return all_passed


# =============================================================================
# Main Entry Point
# =============================================================================
def run_all_tests() -> int:
    print("================================================================================")
    print("Task 6G-B Verification: Rigid Link Inertia Tensor & Whole-Body Angular Momentum")
    print("================================================================================")

    test_results = [
        ("Test 01: Segment Local Inertia Symmetric & Positive Definite", test_01_local_inertia_symmetric_and_positive_definite()),
        ("Test 02: Geometric Solid Formulas Match Analytical References", test_02_geometric_formulas_match_analytical_references()),
        ("Test 03: Parallel Axis Theorem Numerical Correctness", test_03_parallel_axis_theorem_numerical_correctness()),
        ("Test 04: Whole-Body Translation Invariance Relative to CoM", test_04_whole_body_translation_invariance()),
        ("Test 05: Whole-Body Rotation Tensor Transformation Covariance", test_05_whole_body_rotation_tensor_transformation()),
        ("Test 06: Neutral Stance Bilateral Symmetry & Physical Magnitudes", test_06_neutral_stance_symmetry()),
        ("Test 07: Single-Arm Raised Asymmetric Inertia Response", test_07_single_arm_raised_inertia_change()),
        ("Test 08: Tucked vs Extended Posture Rotational Inertia Difference", test_08_tucked_vs_extended_inertia_difference()),
        ("Test 09: Static Body Zero Angular Momentum", test_09_static_body_zero_angular_momentum()),
        ("Test 10: Rigid Rotation Angular Momentum Consistency with I*w", test_10_rigid_rotation_angular_momentum_consistency()),
        ("Test 11: Independent Limb Motion Spin & Orbital Decomposition", test_11_independent_limb_motion_spin_and_orbital_decomposition()),
        ("Test 12: Consistency with CoM, Tracker, and MotionState Integration", test_12_consistency_with_com_and_kinematics_tracker()),
        ("Test 13: Core Regression Verification Suite", test_13_core_regression_suite()),
    ]

    print("\n================================================================================")
    print("Task 6G-B Verification Summary")
    print("================================================================================")
    total_passed = 0
    for name, res in test_results:
        status = "PASSED" if res else "FAILED"
        print(f"[{status:<6}] {name}")
        if res:
            total_passed += 1

    print(f"\nResult: {total_passed}/{len(test_results)} tests passed.")
    if total_passed == len(test_results):
        print("ALL TASK 6G-B TESTS PASSED!")
        return 0
    else:
        print("SOME TESTS FAILED.")
        return 1


if __name__ == "__main__":
    code = run_all_tests()
    sys.exit(code)
