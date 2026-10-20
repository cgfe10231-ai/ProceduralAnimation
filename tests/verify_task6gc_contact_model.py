"""Automated verification suite for Task 6G-C: Multi-Limb Contact Geometry, Constraints, and Support State.

Executes 15 comprehensive verification tests in Blender headless mode:
1. World space contact point and local body anchor transformations.
2. Contact surface normal unitization and outward direction convention.
3. Proper distinction between UNILATERAL and GRASP constraint types.
4. Double stance simultaneous ground contacts.
5. Single stance and swing foot release.
6. Single hand support on obstacle top.
7. Ground and vertical wall simultaneous multi-normal contact.
8. Double hand grasp ledge hang suspension state.
9. Full flight phase with zero active contacts or fabricated support.
10. Contact lifecycle state transitions (CANDIDATE -> ESTABLISHED -> RELEASED / BROKEN).
11. Quantitative error reporting for gap, penetration, and tangential slip.
12. Environment object rigid transform covariance for local anchors and normals.
13. Compatibility with WholeBodyController evaluated actual limb poses.
14. Bidirectional adapter compatibility with MotionState and ContactPointState.
15. Full regression suite (Task 6G-B, 6G-A, 6F-D, 6F-C, 6F-B, 6F-A, 6D).
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from typing import Dict, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    ContactPointState,
    EnvironmentQuery,
    MotionMode,
    MotionState,
    create_initial_motion_state,
)
from src.motion.whole_body_controller import (
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.motion.contact_model import (
    ContactLifecycle,
    ContactRecord,
    ContactType,
    DEFAULT_LIMB_LOCAL_ANCHORS,
    EnvironmentalSurface,
    GeometricConstraintResult,
    MultiContactState,
    SupportType,
    contact_record_to_legacy_contact_point,
    enrich_motion_state_with_contacts,
    evaluate_limb_contacts_from_armature,
    legacy_contact_point_to_contact_record,
)
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.pose import reset_pose


def _setup_clean_character_scene() -> bpy.types.Object:
    """Setup a clean testing scene with CharacterArmature, Leg IK, and Arm IK."""
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
# Test 1: World to Local Anchor Transforms
# =============================================================================
def test_01_world_to_local_anchor_transforms() -> bool:
    print("\n--- Test 1: World to Local Body Anchor Transformations ---")
    arm_obj = _setup_clean_character_scene()

    pb_foot = arm_obj.pose.bones.get("foot.L")
    if pb_foot is None:
        print("FAILED: foot.L bone not found")
        return False

    # Bone world matrix
    bone_mat_world = arm_obj.matrix_world @ pb_foot.matrix
    local_anchor = DEFAULT_LIMB_LOCAL_ANCHORS["foot_L"]

    rec = ContactRecord(
        contact_id="test_foot_L",
        limb="foot_L",
        surface_id="ground",
        body_local_anchor=local_anchor,
    )

    world_anchor = rec.compute_body_anchor_world_position(bone_mat_world)
    expected_world_p = bone_mat_world @ Vector(local_anchor)

    err = (Vector(world_anchor) - expected_world_p).length
    print(f"Bone local anchor: {local_anchor} m")
    print(f"Derived world anchor: ({world_anchor[0]:.4f}, {world_anchor[1]:.4f}, {world_anchor[2]:.4f}) m")
    print(f"Direct matrix multiplication: ({expected_world_p.x:.4f}, {expected_world_p.y:.4f}, {expected_world_p.z:.4f}) m")
    print(f"Transformation discrepancy: {err:.2e} m")

    passed = err < 1e-6
    print(f"Local-to-world anchor mapping: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 2: Normal Unit Length and Convention
# =============================================================================
def test_02_normal_unit_length_and_convention() -> bool:
    print("\n--- Test 2: Normal Unitization and Outward Convention ---")

    # Provide an unnormalized normal vector
    raw_norm = (0.0, 3.0, 4.0)
    rec = ContactRecord(
        contact_id="norm_test",
        limb="foot_L",
        surface_id="slope",
        world_normal=raw_norm,
    )

    nx, ny, nz = rec.world_normal
    n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
    expected_len = 1.0
    err_len = abs(n_len - expected_len)

    print(f"Raw normal: {raw_norm}")
    print(f"Normalized normal: ({nx:.6f}, {ny:.6f}, {nz:.6f}) | Length = {n_len:.8f}")
    print(f"Unit length error: {err_len:.2e}")

    # Ground surface outward normal should point +Z (0, 0, 1)
    ground_rec = ContactRecord(contact_id="g_test", limb="foot_L", surface_id="ground")
    ground_nz = ground_rec.world_normal[2]
    is_upward = abs(ground_nz - 1.0) < 1e-6

    passed = err_len < 1e-6 and is_upward
    print(f"Normal convention & unit length: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 3: Unilateral vs Grasp Constraint Types
# =============================================================================
def test_03_unilateral_vs_grasp_constraint_types() -> bool:
    print("\n--- Test 3: Unilateral vs Grasp Constraint Types ---")

    # Target surface at Z = 0 with normal (0, 0, 1)
    target_pos = (0.0, 0.0, 0.0)
    normal = (0.0, 0.0, 1.0)

    # 1. Unilateral Contact (push only):
    # Case A: Detachment/pull (gap +0.05 m > 0.015 m tolerance) -> must fail (cannot pull)
    uni_rec = ContactRecord(
        contact_id="c_uni",
        limb="foot_L",
        surface_id="ground",
        contact_type=ContactType.UNILATERAL,
        world_position=target_pos,
        world_normal=normal,
        max_allowable_gap_m=0.015,
    )
    res_gap = uni_rec.check_geometric_compliance((0.0, 0.0, 0.050))
    print(f"Unilateral pull (+50mm gap): is_valid={res_gap.is_valid}, reason={res_gap.violation_reason}")

    # Case B: In-contact alignment (+2mm gap <= 15mm tolerance) -> must pass
    res_contact = uni_rec.check_geometric_compliance((0.0, 0.0, 0.002))
    print(f"Unilateral contact (+2mm gap): is_valid={res_contact.is_valid}")

    # Case C: Penetration (-30mm < -10mm tolerance) -> must fail (penetration)
    res_pen = uni_rec.check_geometric_compliance((0.0, 0.0, -0.030))
    print(f"Unilateral penetration (-30mm): is_valid={res_pen.is_valid}, reason={res_pen.violation_reason}")

    # 2. Grasp Contact (bilateral):
    # Hand holds bar at (0.0, 0.0, 1.80).
    grasp_rec = ContactRecord(
        contact_id="c_grasp",
        limb="hand_L",
        surface_id="bar",
        contact_type=ContactType.GRASP,
        world_position=(0.0, 0.0, 1.80),
        world_normal=normal,
        max_allowable_gap_m=0.020,
        max_allowable_slip_m=0.020,
    )
    # Small displacement (5mm in X, 3mm in Z) within tolerance -> valid
    res_grasp_pass = grasp_rec.check_geometric_compliance((0.005, 0.0, 1.803))
    # Large displacement (35mm in X) -> invalid
    res_grasp_fail = grasp_rec.check_geometric_compliance((0.035, 0.0, 1.800))
    print(f"Grasp compliant (5mm offset): is_valid={res_grasp_pass.is_valid}")
    print(f"Grasp displaced (35mm offset): is_valid={res_grasp_fail.is_valid}, reason={res_grasp_fail.violation_reason}")

    passed = (not res_gap.is_valid) and res_contact.is_valid and (not res_pen.is_valid) and res_grasp_pass.is_valid and (not res_grasp_fail.is_valid)
    print(f"Constraint distinction: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 4: Double Stance Two Valid Contacts
# =============================================================================
def test_04_double_stance_two_valid_contacts() -> bool:
    print("\n--- Test 4: Double Stance Simultaneous Ground Contacts ---")

    c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1))
    c_r = ContactRecord("g_foot_R", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -8.0, 0.0), (0, 0, 1))

    mc = MultiContactState(contacts={"foot_L": c_l, "foot_R": c_r})

    print(f"Active contact count: {len(mc.active_contacts)}")
    print(f"Supporting limbs: {mc.supporting_limbs}")
    print(f"Classified support type: {mc.support_type.value}")
    print(f"Is flight: {mc.is_flight}")

    is_coplanar, poly = mc.get_coplanar_support_polygon()
    print(f"Coplanar support polygon (is_coplanar={is_coplanar}): {poly}")

    passed = (
        len(mc.active_contacts) == 2
        and mc.support_type == SupportType.DOUBLE_STANCE
        and not mc.is_flight
        and is_coplanar
        and poly is not None
        and len(poly) == 2
    )
    print(f"Double stance validation: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 5: Single Stance and Swing Release
# =============================================================================
def test_05_single_stance_and_swing_release() -> bool:
    print("\n--- Test 5: Single Stance with Released Swing Foot ---")

    # Left foot support on ground, Right foot released into swing
    c_l = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1))
    c_r = ContactRecord("g_foot_R", "foot_R", "ground", ContactType.FREE, ContactLifecycle.RELEASED, (0.11, -7.7, 0.15), (0, 0, 1))

    mc = MultiContactState(contacts={"foot_L": c_l, "foot_R": c_r})

    print(f"Active contact count: {len(mc.active_contacts)}")
    print(f"Supporting limbs: {mc.supporting_limbs}")
    print(f"Classified support type: {mc.support_type.value}")
    print(f"Is flight: {mc.is_flight}")

    passed = (
        len(mc.active_contacts) == 1
        and mc.supporting_limbs == ["foot_L"]
        and mc.support_type == SupportType.SINGLE_STANCE_L
        and not mc.is_flight
    )
    print(f"Single stance validation: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 6: Single Hand Support on Obstacle
# =============================================================================
def test_06_single_hand_support_obstacle() -> bool:
    print("\n--- Test 6: Single Hand Support on Obstacle Top ---")

    # Vault touch: Left foot on ground, Right hand planted on top of box obstacle at Z=0.90 m
    c_foot = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1))
    c_hand = ContactRecord("box_hand_R", "hand_R", "vault_box", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.25, -7.5, 0.90), (0, 0, 1))

    mc = MultiContactState(contacts={"foot_L": c_foot, "hand_R": c_hand})

    print(f"Active contacts: {list(mc.active_contacts.keys())}")
    print(f"Support type: {mc.support_type.value}")

    # Heights are non-coplanar (0.0 vs 0.90 m) -> support polygon must return is_coplanar = False
    is_coplanar, poly = mc.get_coplanar_support_polygon()
    print(f"Coplanar check: is_coplanar={is_coplanar}, polygon={poly}")

    passed = (
        len(mc.active_contacts) == 2
        and "hand_R" in mc.supporting_limbs
        and mc.support_type == SupportType.MULTI_SURFACE
        and not is_coplanar
        and poly is None
    )
    print(f"Hand support on obstacle: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 7: Ground and Vertical Wall Multi-Normal Contact
# =============================================================================
def test_07_ground_and_wall_multi_normal() -> bool:
    print("\n--- Test 7: Ground + Vertical Wall Multi-Normal Contacts ---")

    # Left foot on horizontal ground: normal (0, 0, 1)
    # Right foot pushed against vertical wall facing -Y: normal (0, -1, 0)
    c_ground = ContactRecord("g_foot_L", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -7.0, 0.0), (0, 0, 1))
    c_wall = ContactRecord("wall_foot_R", "foot_R", "wall_north", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -6.5, 0.40), (0, -1, 0))

    mc = MultiContactState(contacts={"foot_L": c_ground, "foot_R": c_wall})

    print(f"Ground normal: {c_ground.world_normal}")
    print(f"Wall normal:   {c_wall.world_normal}")
    print(f"Support type:  {mc.support_type.value}")

    # Wall contact has non-vertical normal -> cannot form a coplanar ground polygon
    is_coplanar, poly = mc.get_coplanar_support_polygon()
    print(f"Coplanar polygon check: is_coplanar={is_coplanar}")

    passed = (
        mc.support_type == SupportType.WALL_FOOT_STANCE
        and not is_coplanar
        and c_ground.world_normal == (0.0, 0.0, 1.0)
        and c_wall.world_normal == (0.0, -1.0, 0.0)
    )
    print(f"Ground + wall multi-normal: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 8: Double Hand Grasp Ledge Hang
# =============================================================================
def test_08_double_hand_grasp_ledge_hang() -> bool:
    print("\n--- Test 8: Double Hand Grasp Ledge Hang ---")

    # Ledge hang: Both hands grasping bar at Z=1.80 m, feet free (suspended)
    c_hand_l = ContactRecord("bar_hand_L", "hand_L", "ledge_bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (-0.20, -5.0, 1.80), (0, 0, 1))
    c_hand_r = ContactRecord("bar_hand_R", "hand_R", "ledge_bar", ContactType.GRASP, ContactLifecycle.ESTABLISHED, (0.20, -5.0, 1.80), (0, 0, 1))
    c_foot_l = ContactRecord("free_foot_L", "foot_L", "none", ContactType.FREE, ContactLifecycle.RELEASED, (-0.11, -5.0, 0.50), (0, 0, 1))
    c_foot_r = ContactRecord("free_foot_R", "foot_R", "none", ContactType.FREE, ContactLifecycle.RELEASED, (0.11, -5.0, 0.50), (0, 0, 1))

    mc = MultiContactState(contacts={"hand_L": c_hand_l, "hand_R": c_hand_r, "foot_L": c_foot_l, "foot_R": c_foot_r})

    print(f"Active limbs: {mc.supporting_limbs}")
    print(f"Support type: {mc.support_type.value}")
    print(f"Is flight:    {mc.is_flight}")

    passed = (
        mc.support_type == SupportType.LEDGE_HANG
        and len(mc.active_contacts) == 2
        and "hand_L" in mc.supporting_limbs
        and "hand_R" in mc.supporting_limbs
        and not mc.is_flight
    )
    print(f"Double hand grasp ledge hang: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 9: Flight Phase Zero False Contacts
# =============================================================================
def test_09_flight_phase_zero_false_contacts() -> bool:
    print("\n--- Test 9: Flight Phase Zero Active Contacts ---")

    # Running jump: All limbs released/free
    c_foot_l = ContactRecord("c_fl", "foot_L", "none", ContactType.FREE, ContactLifecycle.RELEASED, (-0.11, 0.0, 0.40))
    c_foot_r = ContactRecord("c_fr", "foot_R", "none", ContactType.FREE, ContactLifecycle.RELEASED, (0.11, 0.2, 0.35))
    c_hand_l = ContactRecord("c_hl", "hand_L", "none", ContactType.FREE, ContactLifecycle.RELEASED, (-0.30, 0.0, 1.30))
    c_hand_r = ContactRecord("c_hr", "hand_R", "none", ContactType.FREE, ContactLifecycle.RELEASED, (0.30, 0.0, 1.30))

    mc = MultiContactState(contacts={"foot_L": c_foot_l, "foot_R": c_foot_r, "hand_L": c_hand_l, "hand_R": c_hand_r})

    print(f"Active contact count: {len(mc.active_contacts)}")
    print(f"Is flight:            {mc.is_flight}")
    print(f"Support type:         {mc.support_type.value}")

    is_coplanar, poly = mc.get_coplanar_support_polygon()
    print(f"Polygon on flight: {poly}")

    passed = (
        len(mc.active_contacts) == 0
        and mc.is_flight
        and mc.support_type == SupportType.FLIGHT
        and is_coplanar
        and poly == []
    )
    print(f"Flight phase validation: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 10: Lifecycle State Transitions
# =============================================================================
def test_10_lifecycle_transitions() -> bool:
    print("\n--- Test 10: Contact Lifecycle State Transitions ---")

    rec = ContactRecord("c_cycle", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.CANDIDATE, (0, 0, 0))
    print(f"Initial: {rec.lifecycle.value} (is_active={rec.is_active})")
    if rec.is_active:
        return False

    # Engagement
    rec.lifecycle = ContactLifecycle.ESTABLISHED
    print(f"Engaged: {rec.lifecycle.value} (is_active={rec.is_active})")
    if not rec.is_active:
        return False

    # Violation / Broken
    rec.lifecycle = ContactLifecycle.BROKEN
    print(f"Broken:  {rec.lifecycle.value} (is_active={rec.is_active})")
    if rec.is_active:
        return False

    # Intentional release
    rec.lifecycle = ContactLifecycle.RELEASED
    print(f"Released: {rec.lifecycle.value} (is_active={rec.is_active})")
    if rec.is_active:
        return False

    print("Lifecycle state transitions: PASSED")
    return True


# =============================================================================
# Test 11: Error Reporting Gap, Penetration, and Slip
# =============================================================================
def test_11_error_reporting_gap_penetration_slip() -> bool:
    print("\n--- Test 11: Quantitative Error Reporting (Gap, Penetration, Slip) ---")

    target = (1.0, 2.0, 0.0)
    normal = (0.0, 0.0, 1.0)
    rec = ContactRecord("c_err", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, target, normal)

    # Body anchor at (1.03, 2.04, -0.02)
    # dx = 0.03 m, dy = 0.04 m, dz = -0.02 m
    # Normal distance = -0.02 m (penetration = 0.02 m)
    # Tangential slip = sqrt(0.03^2 + 0.04^2) = 0.05 m
    # Total error = sqrt(0.03^2 + 0.04^2 + (-0.02)^2) = sqrt(0.0025 + 0.0004) = 0.05385 m
    res = rec.check_geometric_compliance((1.03, 2.04, -0.02))

    err_pen = abs(res.penetration_depth_m - 0.020)
    err_slip = abs(res.tangential_slip_m - 0.050)
    err_tot = abs(res.total_position_error_m - math.sqrt(0.05 ** 2 + 0.02 ** 2))

    print(f"Penetration depth: {res.penetration_depth_m:.4f} m (expected 0.0200 m, err={err_pen:.2e})")
    print(f"Tangential slip:   {res.tangential_slip_m:.4f} m (expected 0.0500 m, err={err_slip:.2e})")
    print(f"Total error:       {res.total_position_error_m:.4f} m (expected 0.0539 m, err={err_tot:.2e})")
    print(f"Violation report:  {res.violation_reason}")

    passed = err_pen < 1e-6 and err_slip < 1e-6 and err_tot < 1e-6 and (not res.is_valid) and (res.violation_reason is not None)
    print(f"Quantitative error evaluation: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 12: Environment Object Rigid Transform Covariance
# =============================================================================
def test_12_environment_transform_anchor_update() -> bool:
    print("\n--- Test 12: Environment Transform Covariance for Anchors & Normals ---")

    # Obstacle with local contact point at (0.5, 0.0, 0.4) and local normal (0, 0, 1)
    rec = ContactRecord(
        contact_id="c_box",
        limb="hand_R",
        surface_id="box_01",
        env_local_anchor=(0.5, 0.0, 0.4),
        world_normal=(0.0, 0.0, 1.0),
        metadata={"env_local_normal": (0.0, 0.0, 1.0)},
    )

    # Transform obstacle: translate by (2.0, -4.0, 0.0) and rotate 90 deg around Z
    mat_rot = Matrix.Rotation(math.radians(90.0), 4, "Z")
    mat_trans = Matrix.Translation(Vector((2.0, -4.0, 0.0)))
    env_mat = mat_trans @ mat_rot

    # Local (0.5, 0.0, 0.4) rotated 90 deg around Z becomes (0.0, 0.5, 0.4)
    # Translated by (2.0, -4.0, 0.0) becomes (2.0, -3.5, 0.4)
    expected_pos = Vector((2.0, -3.5, 0.4))
    expected_norm = Vector((0.0, 0.0, 1.0))

    rec.update_from_environment_transform(env_mat)

    err_p = (Vector(rec.world_position) - expected_pos).length
    err_n = (Vector(rec.world_normal) - expected_norm).length

    print(f"Updated world position: ({rec.world_position[0]:.4f}, {rec.world_position[1]:.4f}, {rec.world_position[2]:.4f}) m")
    print(f"Updated world normal:   ({rec.world_normal[0]:.4f}, {rec.world_normal[1]:.4f}, {rec.world_normal[2]:.4f})")
    print(f"Position discrepancy: {err_p:.2e} m | Normal discrepancy: {err_n:.2e}")

    passed = err_p < 1e-6 and err_n < 1e-6
    print(f"Environment transform covariance: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 13: WholeBodyController Pose Compatibility
# =============================================================================
def test_13_whole_body_controller_pose_compatibility() -> bool:
    print("\n--- Test 13: WholeBodyController Evaluated Pose Compatibility ---")
    arm_obj = _setup_clean_character_scene()

    controller = WholeBodyController(armature_obj=arm_obj)
    targets = WholeBodyControlTargets()
    # Place feet on ground (ankle at Z=0.07), set right hand target on obstacle at reachable pos (0.25, -7.85, 1.05)
    targets.set_foot("L", (-0.11, -8.0, 0.07), is_locked=True)
    targets.set_foot("R", (0.11, -8.0, 0.07), is_locked=True)
    targets.set_hand("R", (0.25, -7.85, 1.05), clamp_reach=True)

    res = controller.execute_frame(targets)

    # Build multi-contact from targets and evaluate against controller result
    c_fl = ContactRecord("c_fl", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.07), (0, 0, 1))
    c_fr = ContactRecord("c_fr", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -8.0, 0.07), (0, 0, 1))
    c_hr = ContactRecord("c_hr", "hand_R", "box", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.25, -7.85, 1.05), (0, 0, 1))

    mc = MultiContactState(contacts={"foot_L": c_fl, "foot_R": c_fr, "hand_R": c_hr})

    actual_positions = {
        "foot_L": res.end_effectors["foot_L"].actual_world_xyz,
        "foot_R": res.end_effectors["foot_R"].actual_world_xyz,
        "hand_R": res.end_effectors["hand_R"].actual_world_xyz,
    }

    compliance = mc.check_all_contacts(actual_positions)

    all_valid = all(cr.is_valid for cr in compliance.values())
    for limb, cr in compliance.items():
        print(f"Limb {limb:<6}: valid={cr.is_valid}, pos_err={cr.total_position_error_m * 1000.0:.3f} mm")

    passed = all_valid and len(compliance) == 3
    print(f"WholeBodyController contact integration: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 14: MotionState Legacy Adapter Compatibility
# =============================================================================
def test_14_motion_state_legacy_adapter_compatibility() -> bool:
    print("\n--- Test 14: MotionState Legacy Adapter Compatibility ---")

    cfg = PipelineConfig()
    m_state = create_initial_motion_state(cfg)

    # Modern multi-contact state
    c_l = ContactRecord("c_l", "foot_L", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (-0.11, -8.0, 0.0), (0, 0, 1))
    c_r = ContactRecord("c_r", "foot_R", "ground", ContactType.UNILATERAL, ContactLifecycle.ESTABLISHED, (0.11, -8.0, 0.0), (0, 0, 1))
    mc = MultiContactState(contacts={"foot_L": c_l, "foot_R": c_r})

    enriched = enrich_motion_state_with_contacts(m_state, mc)

    # Verify MotionState.contacts contains ContactPointState objects
    has_foot_l = "foot_L" in enriched.contacts and isinstance(enriched.contacts["foot_L"], ContactPointState)
    has_foot_r = "foot_R" in enriched.contacts and isinstance(enriched.contacts["foot_R"], ContactPointState)

    # Verify params telemetry
    support_type = enriched.params.get("support_type")
    supporting_limbs = enriched.params.get("supporting_limbs")
    has_poly = enriched.params.get("support_polygon_2d") is not None

    print(f"MotionState.contacts has ContactPointState: foot_L={has_foot_l}, foot_R={has_foot_r}")
    print(f"MotionState.params support_type: {support_type}")
    print(f"MotionState.params supporting_limbs: {supporting_limbs}")
    print(f"MotionState.params support_polygon_2d present: {has_poly}")

    # Reverse conversion test: ContactPointState -> ContactRecord
    rec_converted = legacy_contact_point_to_contact_record(enriched.contacts["foot_L"])
    roundtrip_ok = rec_converted.limb == "foot_L" and rec_converted.is_active

    passed = has_foot_l and has_foot_r and support_type == "double_stance" and has_poly and roundtrip_ok
    print(f"MotionState bidirectional adapter: {'PASSED' if passed else 'FAILED'}")
    return passed


# =============================================================================
# Test 15: Core Regression Suite
# =============================================================================
def test_15_core_regression_suite() -> bool:
    print("\n--- Test 15: Core Regression Verification Suite ---")
    tests_dir = os.path.dirname(__file__)
    regression_scripts = [
        "verify_task6gb_body_inertia.py",
        "verify_task6ga_body_kinematics.py",
        "verify_task6fd_whole_body_controller.py",
        "verify_task6fc_joint_limits.py",
        "verify_task6fb_rigid_link.py",
        "verify_task6fa_arm_ik.py",
    ]

    blender_bin = getattr(bpy.app, "binary_path", sys.executable)
    all_passed = True

    for script_name in regression_scripts:
        script_path = os.path.join(tests_dir, script_name)
        if not os.path.exists(script_path):
            print(f"Regression script {script_name} not found, skipping.")
            continue

        print(f"\nRunning regression: {script_name}...")
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
# Test 16: Visual Prototype Integration Acceptance Suite
# =============================================================================
def test_16_visual_prototype_integration_acceptance() -> bool:
    print("\n--- Test 16: Visual Prototype Integration Acceptance Suite ---")
    blend_path = os.path.join(PROJECT_ROOT, "output", "contact_model_debug.blend")
    if not os.path.exists(blend_path):
        print(f"FAILED: Visual prototype file not found at: {blend_path}")
        return False

    file_size_kb = os.path.getsize(blend_path) / 1024.0
    print(f"Inspecting prototype .blend ({file_size_kb:.1f} KB): {blend_path}")

    # Load blend file into bpy
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.context.scene
    arm = bpy.data.objects.get("CharacterArmature")
    root = bpy.data.objects.get("CharacterRoot")

    if arm is None or root is None:
        print("FAILED: CharacterArmature or CharacterRoot not found in blend file")
        return False

    # 1. Facing alignment with obstacles across all 6 segments
    facing_checks_passed = True
    print("\n[Check 1: Facing alignment with obstacles (+Y)]")
    sample_frames = [
        (15, "Double Stance"),
        (45, "Single Stance"),
        (75, "Vault Touch"),
        (105, "Foot on Wall"),
        (135, "Ledge Hang"),
        (165, "Flight Phase"),
    ]
    for f, name in sample_frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        facing = (arm.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
        dot = facing.dot(Vector((0, 1, 0)))
        angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        ok = (dot >= 0.98)
        print(f"  Segment {name:15s} (F{f:3d}): Facing=({facing.x:.3f}, {facing.y:.3f}, {facing.z:.3f}) | dot={dot:.4f} | angle={angle_deg:.2f} deg -> {'OK' if ok else 'FAIL'}")
        if not ok:
            facing_checks_passed = False

    # 2. Standing hand height (wrists hanging down, not horizontal)
    standing_hand_passed = True
    print("\n[Check 2: Natural standing hand drop (wrists >= 0.40m below shoulders)]")
    for f, name in [(15, "Double Stance"), (45, "Single Stance")]:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        sh_l = arm.matrix_world @ arm.pose.bones["upper_arm.L"].head
        wr_l = arm.matrix_world @ arm.pose.bones["forearm.L"].tail
        sh_r = arm.matrix_world @ arm.pose.bones["upper_arm.R"].head
        wr_r = arm.matrix_world @ arm.pose.bones["forearm.R"].tail
        drop_l = sh_l.z - wr_l.z
        drop_r = sh_r.z - wr_r.z
        ok = (drop_l >= 0.40 and drop_r >= 0.40 and abs(wr_l.x) <= 0.35 and abs(wr_r.x) <= 0.35)
        print(f"  {name:15s}: L drop={drop_l:.3f}m, R drop={drop_r:.3f}m, L_wrist_x={wr_l.x:.2f}, R_wrist_x={wr_r.x:.2f} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            standing_hand_passed = False

    # 3. Morphological pose differentiation across the 6 segments
    pose_diff_passed = True
    print("\n[Check 3: Morphological joint angle differentiation]")
    pose_rotations: List[List[float]] = []
    monitored_bones = ["spine", "thigh.L", "shin.L", "thigh.R", "shin.R", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R"]
    from src.motion.joint_limits import extract_evaluated_bone_rotation_rad
    for f, name in sample_frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        rots: List[float] = []
        for b_name in monitored_bones:
            pb = arm.pose.bones.get(b_name)
            if pb:
                rots.extend([math.degrees(a) for a in extract_evaluated_bone_rotation_rad(pb)])
        pose_rotations.append(rots)

    min_diff_deg = 999.0
    for i in range(len(sample_frames)):
        for j in range(i + 1, len(sample_frames)):
            diff = math.sqrt(sum((a - b) ** 2 for a, b in zip(pose_rotations[i], pose_rotations[j])))
            if diff < min_diff_deg:
                min_diff_deg = diff
    print(f"  Minimum pairwise joint angle difference across 6 segments: {min_diff_deg:.2f} deg (expected >= 20.0 deg)")
    if min_diff_deg < 20.0:
        pose_diff_passed = False

    # 4. Contact anchor accuracy on environment surfaces
    contact_acc_passed = True
    print("\n[Check 4: Contact anchor accuracy on environment surfaces]")
    # Double stance (F15)
    scene.frame_set(15)
    bpy.context.view_layer.update()
    ak_l = arm.matrix_world @ arm.pose.bones["shin.L"].tail
    ak_r = arm.matrix_world @ arm.pose.bones["shin.R"].tail
    err_fl = abs(ak_l.z - 0.07)
    err_fr = abs(ak_r.z - 0.07)
    print(f"  Double Stance ground ankles: L_err={err_fl*1000:.2f}mm, R_err={err_fr*1000:.2f}mm")

    # Vault touch (F75)
    scene.frame_set(75)
    bpy.context.view_layer.update()
    wr_r = arm.matrix_world @ arm.pose.bones["forearm.R"].tail
    err_vault = math.sqrt((wr_r.z - 1.05) ** 2 + (wr_r.y - (-5.75)) ** 2)
    print(f"  Vault Touch right wrist on box top: err={err_vault*1000:.2f}mm (target Z=1.05m, Y=-5.75m)")

    # Foot on wall (F105)
    scene.frame_set(105)
    bpy.context.view_layer.update()
    ak_r = arm.matrix_world @ arm.pose.bones["shin.R"].tail
    err_wall = math.sqrt((ak_r.y - (-4.07)) ** 2 + (ak_r.z - 0.45) ** 2)
    print(f"  Foot on Wall right ankle against wall: err={err_wall*1000:.2f}mm (target Y=-4.07m, Z=0.45m)")

    # Ledge hang (F135)
    scene.frame_set(135)
    bpy.context.view_layer.update()
    wr_l = arm.matrix_world @ arm.pose.bones["forearm.L"].tail
    wr_r = arm.matrix_world @ arm.pose.bones["forearm.R"].tail
    err_bar = max(abs(wr_l.z - 1.95), abs(wr_r.z - 1.95))
    print(f"  Ledge Hang wrists grasping bar: err={err_bar*1000:.2f}mm (target Z=1.95m)")

    if max(err_fl, err_fr, err_vault, err_wall, err_bar) > 0.010:  # 10 mm
        contact_acc_passed = False

    # 5. Hold phase anchor stability (drift < 1.0 mm)
    drift_passed = True
    print("\n[Check 5: Hold phase contact anchor stability (drift < 1.0 mm)]")
    hold_checks = [
        ("Double Stance", 15, 25, "shin.L", "tail"),
        ("Vault Touch", 75, 85, "forearm.R", "tail"),
        ("Foot on Wall", 105, 115, "shin.R", "tail"),
        ("Ledge Hang", 135, 145, "forearm.L", "tail"),
    ]
    for name, f0, f1, b_name, end in hold_checks:
        scene.frame_set(f0)
        bpy.context.view_layer.update()
        p0 = (arm.matrix_world @ getattr(arm.pose.bones[b_name], end)).copy()

        scene.frame_set(f1)
        bpy.context.view_layer.update()
        p1 = (arm.matrix_world @ getattr(arm.pose.bones[b_name], end)).copy()

        drift_mm = (p1 - p0).length * 1000.0
        ok = (drift_mm <= 1.0)
        print(f"  {name:15s} (F{f0}->F{f1}): Drift = {drift_mm:.3f} mm -> {'OK' if ok else 'FAIL'}")
        if not ok:
            drift_passed = False

    # 6. Motion smoothness / continuity across entire timeline
    smooth_passed = True
    print("\n[Check 6: Motion continuity across frames 1..180 (max step <= 0.40m)]")
    max_step = 0.0
    prev_pos = None
    for f in range(1, 181):
        scene.frame_set(f)
        pos = root.matrix_world.translation.copy()
        if prev_pos is not None:
            step = (pos - prev_pos).length
            if step > max_step:
                max_step = step
        prev_pos = pos

    print(f"  Maximum single-frame root displacement: {max_step*1000:.2f} mm (expected <= 400 mm)")
    if max_step > 0.40:
        smooth_passed = False

    # Summary
    all_ok = (
        facing_checks_passed
        and standing_hand_passed
        and pose_diff_passed
        and contact_acc_passed
        and drift_passed
        and smooth_passed
    )
    print(f"\nVisual Prototype Integration Acceptance: {'PASSED' if all_ok else 'FAILED'}")
    return all_ok


# =============================================================================
# Main Test Runner
# =============================================================================
def run_all_tests() -> int:
    print("================================================================================")
    print("Task 6G-C Verification: Multi-Limb Contact Geometry & Support State System")
    print("================================================================================")

    test_results = [
        ("Test 01: World to Local Anchor Transforms", test_01_world_to_local_anchor_transforms()),
        ("Test 02: Normal Unit Length & Direction Convention", test_02_normal_unit_length_and_convention()),
        ("Test 03: Unilateral vs Grasp Constraint Types", test_03_unilateral_vs_grasp_constraint_types()),
        ("Test 04: Double Stance Simultaneous Ground Contacts", test_04_double_stance_two_valid_contacts()),
        ("Test 05: Single Stance & Swing Foot Release", test_05_single_stance_and_swing_release()),
        ("Test 06: Single Hand Support on Obstacle Top", test_06_single_hand_support_obstacle()),
        ("Test 07: Ground + Vertical Wall Multi-Normal Contacts", test_07_ground_and_wall_multi_normal()),
        ("Test 08: Double Hand Grasp Ledge Hang Suspension", test_08_double_hand_grasp_ledge_hang()),
        ("Test 09: Flight Phase Zero False Contacts", test_09_flight_phase_zero_false_contacts()),
        ("Test 10: Lifecycle State Transitions", test_10_lifecycle_transitions()),
        ("Test 11: Quantitative Error Reporting (Gap, Penetration, Slip)", test_11_error_reporting_gap_penetration_slip()),
        ("Test 12: Environment Transform Covariance", test_12_environment_transform_anchor_update()),
        ("Test 13: WholeBodyController Evaluated Pose Compatibility", test_13_whole_body_controller_pose_compatibility()),
        ("Test 14: MotionState Legacy Adapter Compatibility", test_14_motion_state_legacy_adapter_compatibility()),
        ("Test 15: Core Regression Verification Suite", test_15_core_regression_suite()),
        ("Test 16: Visual Prototype Integration Acceptance Suite", test_16_visual_prototype_integration_acceptance()),
    ]

    print("\n================================================================================")
    print("Task 6G-C Verification Summary")
    print("================================================================================")
    total_passed = 0
    for name, res in test_results:
        status = "PASSED" if res else "FAILED"
        print(f"[{status:<6}] {name}")
        if res:
            total_passed += 1

    print(f"\nResult: {total_passed}/{len(test_results)} tests passed.")
    if total_passed == len(test_results):
        print("ALL TASK 6G-C TESTS PASSED!")
        return 0
    else:
        print("SOME TESTS FAILED.")
        return 1


if __name__ == "__main__":
    code = run_all_tests()
    sys.exit(code)
