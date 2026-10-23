"""Comprehensive Mathematical and Geometric Verification of Contact Dynamics (Task 6G-D-A).

Verifies the mathematical rigor, physical consistency, and standard DynamicsPlayground
contract integration of `src.motion.contact_dynamics`:

Core Test Categories:
1. Zero force produces zero momentum change.
2. Force applied at CoM produces zero torque about CoM.
3. Eccentric force produces exact right-handed torque (tau = r x F).
4. World coordinate translation leaves torque about CoM invariant.
5. Rigid SO(3) rotation transformation preserves mathematical consistency: R*(r x F) == (R*r) x (R*F).
6. Linear and angular impulses match momentum changes (Delta P = J, Delta L = H).
7. Strict distinction between torque/angular momentum about CoM vs World Origin.
8. Unilateral normal contact constraint (F_n >= 0, tension violation when F_n < 0).
9. Coulomb friction cone constraint (||F_t|| <= mu * F_n, stick vs slip violation).
10. Multi-contact aggregation (sum of forces, sum of torques, total impulses).
11. Robust rejection of NaN, Inf, non-positive dt, negative mu, and degenerate normals.
12. Standard DynamicsPlayground contract: Flat ground surface (Z=0m, normal=(0,0,1), mu=0.70).
13. Standard DynamicsPlayground contract: Sloped ramps (+15 deg up, -20 deg down, mu=0.65).
14. Standard DynamicsPlayground contract: Vertical wall (normal=(0,-1,0), mu=0.60, push reaction).
15. Standard DynamicsPlayground contract: Out-of-bounds and illegal contact handling.
16. Multi-contact time step (dt) consistency enforcement and mismatch rejection.
17. Contact clearance validity contract and non-contact force violation.

Pure Python implementation (fast, reproducible, no heavy scene dependencies).
"""

from __future__ import annotations

import math
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.motion.contact_dynamics import (
    FrictionConeStatus,
    FrictionConstraintEvaluation,
    MultiContactDynamics,
    SingleContactDynamics,
    create_contact_dynamics_from_environment,
    mat3_mul_vec,
    vec3_add,
    vec3_cross,
    vec3_dot,
    vec3_length,
    vec3_normalize,
    vec3_scale,
    vec3_sub,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    EnvironmentQuery,
    create_standard_dynamics_playground_query,
)


class TestContactDynamics(unittest.TestCase):
    """Rigorous unit test suite for Contact Dynamics and Momentum Impulse system."""

    @classmethod
    def setUpClass(cls):
        cls.playground_query = create_standard_dynamics_playground_query()
        cls.base_query = EnvironmentQuery(ground_z=0.0)

    # -------------------------------------------------------------------------
    # 1. Zero Force and CoM Dynamics
    # -------------------------------------------------------------------------

    def test_01_zero_force_zero_momentum_change(self):
        """Req 1: Zero contact force must produce strictly zero torque, impulse, and momentum change."""
        contact = SingleContactDynamics(
            contact_id="foot_L_zero",
            contact_point_world=(0.10, 0.20, 0.0),
            contact_force_world=(0.0, 0.0, 0.0),
            com_world=(0.0, 0.0, 1.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
            dt=0.04,
        )
        self.assertEqual(contact.torque_about_com, (0.0, 0.0, 0.0))
        self.assertEqual(contact.torque_about_origin, (0.0, 0.0, 0.0))
        self.assertEqual(contact.linear_impulse, (0.0, 0.0, 0.0))
        self.assertEqual(contact.angular_impulse_about_com, (0.0, 0.0, 0.0))
        self.assertEqual(contact.linear_momentum_change, (0.0, 0.0, 0.0))
        self.assertEqual(contact.angular_momentum_change_about_com, (0.0, 0.0, 0.0))

        eval_res = contact.evaluate_friction_constraint()
        self.assertTrue(eval_res.is_valid)
        self.assertEqual(eval_res.status, FrictionConeStatus.SEPARATED)
        self.assertAlmostEqual(eval_res.normal_force_n, 0.0)
        self.assertAlmostEqual(eval_res.tangential_force_n, 0.0)

    def test_02_force_at_com_zero_torque_about_com(self):
        """Req 2: A force applied directly at Whole-Body CoM produces zero torque about CoM."""
        com = (1.5, 2.5, 1.2)
        contact = SingleContactDynamics(
            contact_id="com_push",
            contact_point_world=com,  # Contact point is exactly CoM
            contact_force_world=(150.0, -80.0, 450.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.60,
            dt=0.02,
        )
        self.assertEqual(contact.lever_arm_from_com, (0.0, 0.0, 0.0))
        self.assertEqual(contact.torque_about_com, (0.0, 0.0, 0.0))
        self.assertEqual(contact.angular_impulse_about_com, (0.0, 0.0, 0.0))
        self.assertEqual(contact.angular_momentum_change_about_com, (0.0, 0.0, 0.0))

        # But torque about world origin is non-zero: p_com x F
        expected_origin_tau = vec3_cross(com, (150.0, -80.0, 450.0))
        self.assertAlmostEqual(contact.torque_about_origin[0], expected_origin_tau[0], places=5)
        self.assertAlmostEqual(contact.torque_about_origin[1], expected_origin_tau[1], places=5)
        self.assertAlmostEqual(contact.torque_about_origin[2], expected_origin_tau[2], places=5)

    def test_03_eccentric_force_and_right_hand_rule_torque(self):
        """Req 3: Eccentric forces produce right-handed torque: tau = r x F."""
        com = (0.0, 0.0, 1.0)
        # Foot contact 0.2m forward in Y, on ground Z=0.0m:
        # r = (0.0, 0.2, 0.0) - (0.0, 0.0, 1.0) = (0.0, +0.2, -1.0)
        pt = (0.0, 0.2, 0.0)
        # Upward ground reaction force along +Z of 600N:
        # tau = (0, 0.2, -1.0) x (0, 0, 600)
        # tau_x = 0.2 * 600 - (-1.0) * 0 = +120 N*m (pitches backward / positive pitch about +X)
        # tau_y = (-1.0) * 0 - 0 * 600 = 0
        # tau_z = 0 * 0 - 0.2 * 0 = 0
        contact = SingleContactDynamics(
            contact_id="foot_pitch",
            contact_point_world=pt,
            contact_force_world=(0.0, 0.0, 600.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
            dt=0.05,
        )
        self.assertAlmostEqual(contact.lever_arm_from_com[0], 0.0, places=5)
        self.assertAlmostEqual(contact.lever_arm_from_com[1], 0.2, places=5)
        self.assertAlmostEqual(contact.lever_arm_from_com[2], -1.0, places=5)

        tau = contact.torque_about_com
        self.assertAlmostEqual(tau[0], 120.0, places=5)
        self.assertAlmostEqual(tau[1], 0.0, places=5)
        self.assertAlmostEqual(tau[2], 0.0, places=5)

        # Right-handed cross product linearity check:
        # tau(F1 + F2) == tau(F1) + tau(F2)
        f1 = (50.0, 30.0, 400.0)
        f2 = (-20.0, 40.0, 100.0)
        c1 = SingleContactDynamics("c1", pt, f1, com, (0, 0, 1), 0.7, 0.01)
        c2 = SingleContactDynamics("c2", pt, f2, com, (0, 0, 1), 0.7, 0.01)
        c_sum = SingleContactDynamics("c_sum", pt, vec3_add(f1, f2), com, (0, 0, 1), 0.7, 0.01)

        tau_sum = vec3_add(c1.torque_about_com, c2.torque_about_com)
        self.assertAlmostEqual(c_sum.torque_about_com[0], tau_sum[0], places=5)
        self.assertAlmostEqual(c_sum.torque_about_com[1], tau_sum[1], places=5)
        self.assertAlmostEqual(c_sum.torque_about_com[2], tau_sum[2], places=5)

    # -------------------------------------------------------------------------
    # 2. Invariance & Covariance Principles
    # -------------------------------------------------------------------------

    def test_04_world_translation_invariance_about_com(self):
        """Req 4: Rigid translation of world space coordinates leaves torque about CoM identical."""
        com_0 = (1.0, 2.0, 0.95)
        pt_0 = (1.1, 2.2, 0.0)
        force = (35.0, -45.0, 720.0)

        c_orig = SingleContactDynamics("orig", pt_0, force, com_0, (0, 0, 1), 0.70, 0.02)
        tau_orig = c_orig.torque_about_com

        # Translate world coordinate frame by offset (+100.0, -50.0, +25.0)
        offset = (100.0, -50.0, 25.0)
        com_trans = vec3_add(com_0, offset)
        pt_trans = vec3_add(pt_0, offset)

        c_trans = SingleContactDynamics("trans", pt_trans, force, com_trans, (0, 0, 1), 0.70, 0.02)
        tau_trans = c_trans.torque_about_com

        # Relative lever arm is identical
        self.assertAlmostEqual(c_orig.lever_arm_from_com[0], c_trans.lever_arm_from_com[0], places=5)
        self.assertAlmostEqual(c_orig.lever_arm_from_com[1], c_trans.lever_arm_from_com[1], places=5)
        self.assertAlmostEqual(c_orig.lever_arm_from_com[2], c_trans.lever_arm_from_com[2], places=5)

        # Torque about CoM is strictly invariant
        self.assertAlmostEqual(tau_orig[0], tau_trans[0], places=5)
        self.assertAlmostEqual(tau_orig[1], tau_trans[1], places=5)
        self.assertAlmostEqual(tau_orig[2], tau_trans[2], places=5)

        # Angular impulse & momentum change about CoM are invariant
        self.assertAlmostEqual(c_orig.angular_momentum_change_about_com[0], c_trans.angular_momentum_change_about_com[0], places=5)
        self.assertAlmostEqual(c_orig.angular_momentum_change_about_com[1], c_trans.angular_momentum_change_about_com[1], places=5)
        self.assertAlmostEqual(c_orig.angular_momentum_change_about_com[2], c_trans.angular_momentum_change_about_com[2], places=5)

    def test_05_rigid_rotation_covariance_consistency(self):
        """Req 5: Rigid rotation R in SO(3) satisfies R*(r x F) == (R*r) x (R*F)."""
        # Construct rotation matrix for yaw = 37 deg, pitch = 22 deg
        yaw = math.radians(37.0)
        pitch = math.radians(22.0)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        # R = R_z(yaw) * R_y(pitch)
        rot_mat = [
            [cy * cp, -sy, cy * sp],
            [sy * cp,  cy, sy * sp],
            [-sp,      0.0, cp],
        ]

        com = (0.5, -0.3, 0.9)
        pt = (0.7, -0.1, 0.0)
        force = (-40.0, 75.0, 650.0)
        norm = (0.0, 0.0, 1.0)

        c_base = SingleContactDynamics("base", pt, force, com, norm, 0.65, 0.02)
        r_base = c_base.lever_arm_from_com
        tau_base = c_base.torque_about_com

        # Rotate vectors
        pt_rot = mat3_mul_vec(rot_mat, pt)
        com_rot = mat3_mul_vec(rot_mat, com)
        force_rot = mat3_mul_vec(rot_mat, force)
        norm_rot = mat3_mul_vec(rot_mat, norm)

        c_rot = SingleContactDynamics("rot", pt_rot, force_rot, com_rot, norm_rot, 0.65, 0.02)
        r_rot = c_rot.lever_arm_from_com
        tau_rot = c_rot.torque_about_com

        # Verify lever arm rotates as R*r
        expected_r_rot = mat3_mul_vec(rot_mat, r_base)
        self.assertAlmostEqual(r_rot[0], expected_r_rot[0], places=5)
        self.assertAlmostEqual(r_rot[1], expected_r_rot[1], places=5)
        self.assertAlmostEqual(r_rot[2], expected_r_rot[2], places=5)

        # Verify torque transforms covariantly: tau_rot == R * tau_base
        expected_tau_rot = mat3_mul_vec(rot_mat, tau_base)
        self.assertAlmostEqual(tau_rot[0], expected_tau_rot[0], places=5)
        self.assertAlmostEqual(tau_rot[1], expected_tau_rot[1], places=5)
        self.assertAlmostEqual(tau_rot[2], expected_tau_rot[2], places=5)

        # Verify normal force magnitude invariance under rotation: F_n == F_n_rot
        eval_base = c_base.evaluate_friction_constraint()
        eval_rot = c_rot.evaluate_friction_constraint()
        self.assertAlmostEqual(eval_base.normal_force_n, eval_rot.normal_force_n, places=5)
        self.assertAlmostEqual(eval_base.tangential_force_n, eval_rot.tangential_force_n, places=5)

    # -------------------------------------------------------------------------
    # 3. Impulses & Momentum Distinction
    # -------------------------------------------------------------------------

    def test_06_impulse_and_momentum_equivalence(self):
        """Req 6: Linear impulse J == Delta P, and angular impulse H == Delta L."""
        dt = 0.025  # 40 Hz
        force = (100.0, -50.0, 800.0)
        c = SingleContactDynamics(
            contact_id="c_impulse",
            contact_point_world=(0.1, 0.2, 0.0),
            contact_force_world=force,
            com_world=(0.0, 0.0, 1.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            dt=dt,
        )

        # Linear impulse: J = F * dt
        expected_j = (100.0 * dt, -50.0 * dt, 800.0 * dt)
        self.assertAlmostEqual(c.linear_impulse[0], expected_j[0], places=6)
        self.assertAlmostEqual(c.linear_impulse[1], expected_j[1], places=6)
        self.assertAlmostEqual(c.linear_impulse[2], expected_j[2], places=6)

        # Momentum change must equal impulse exactly
        self.assertEqual(c.linear_momentum_change, c.linear_impulse)
        self.assertEqual(c.angular_momentum_change_about_com, c.angular_impulse_about_com)
        self.assertEqual(c.angular_momentum_change_about_origin, c.angular_impulse_about_origin)

    def test_07_distinction_between_com_and_world_origin_torque(self):
        """Req 7: Must NOT confuse torque about CoM with torque about World Origin."""
        com = (2.0, 3.0, 1.0)
        pt = (2.1, 3.2, 0.0)
        force = (50.0, 0.0, 700.0)

        c = SingleContactDynamics("distinguish", pt, force, com, (0, 0, 1), 0.70, 0.01)

        tau_com = c.torque_about_com
        tau_origin = c.torque_about_origin

        # They are mathematically different
        self.assertNotEqual(tau_com, tau_origin)

        # Identity: tau_origin = p_com x F + tau_com
        expected_origin = vec3_add(vec3_cross(com, force), tau_com)
        self.assertAlmostEqual(tau_origin[0], expected_origin[0], places=5)
        self.assertAlmostEqual(tau_origin[1], expected_origin[1], places=5)
        self.assertAlmostEqual(tau_origin[2], expected_origin[2], places=5)

    # -------------------------------------------------------------------------
    # 4. Constraints: Normal Force & Coulomb Friction
    # -------------------------------------------------------------------------

    def test_08_unilateral_normal_constraint_validation(self):
        """Req 8: Unilateral contact requires F_n >= 0; negative normal force is rejected."""
        norm = (0.0, 0.0, 1.0)
        pt = (0.0, 0.0, 0.0)
        com = (0.0, 0.0, 1.0)

        # Valid push: F_z = +500N
        c_push = SingleContactDynamics("push", pt, (0.0, 0.0, 500.0), com, norm, 0.70)
        eval_push = c_push.evaluate_friction_constraint()
        self.assertTrue(eval_push.is_valid)
        self.assertAlmostEqual(eval_push.normal_force_n, 500.0, places=5)

        # Invalid pull (tension): F_z = -100N (attempting to pull down into ground)
        c_pull = SingleContactDynamics("pull", pt, (0.0, 0.0, -100.0), com, norm, 0.70)
        eval_pull = c_pull.evaluate_friction_constraint()
        self.assertFalse(eval_pull.is_valid)
        self.assertEqual(eval_pull.status, FrictionConeStatus.TENSION_VIOLATION)
        self.assertAlmostEqual(eval_pull.normal_force_n, -100.0, places=5)
        self.assertIn("UNILATERAL_TENSION_VIOLATION", eval_pull.violation_reason)

    def test_09_coulomb_friction_cone_and_margin(self):
        """Req 9: Tangential friction must not exceed Coulomb limit: ||F_t|| <= mu * F_n."""
        norm = (0.0, 0.0, 1.0)
        pt = (0.0, 0.0, 0.0)
        com = (0.0, 0.0, 1.0)
        mu = 0.60
        f_n = 400.0
        # Friction limit = 0.60 * 400 = 240N

        # 1. Inside cone (Stick): F_t = 120N < 240N
        c_stick = SingleContactDynamics("stick", pt, (120.0, 0.0, f_n), com, norm, mu)
        eval_stick = c_stick.evaluate_friction_constraint()
        self.assertTrue(eval_stick.is_valid)
        self.assertEqual(eval_stick.status, FrictionConeStatus.STICK)
        self.assertAlmostEqual(eval_stick.tangential_force_n, 120.0, places=4)
        self.assertAlmostEqual(eval_stick.friction_limit_n, 240.0, places=4)
        self.assertAlmostEqual(eval_stick.friction_margin_n, 120.0, places=4)

        # 2. On boundary (Slip Limit): F_t = 240N == 240N
        c_limit = SingleContactDynamics("limit", pt, (0.0, 240.0, f_n), com, norm, mu)
        eval_limit = c_limit.evaluate_friction_constraint()
        self.assertTrue(eval_limit.is_valid)
        self.assertEqual(eval_limit.status, FrictionConeStatus.SLIP_LIMIT)
        self.assertAlmostEqual(eval_limit.friction_margin_n, 0.0, places=4)

        # 3. Outside cone (Slip Violation): F_x=180N, F_y=180N -> F_t = sqrt(180^2 + 180^2) ~= 254.56N > 240N
        c_slip = SingleContactDynamics("slip", pt, (180.0, 180.0, f_n), com, norm, mu)
        eval_slip = c_slip.evaluate_friction_constraint()
        self.assertFalse(eval_slip.is_valid)
        self.assertEqual(eval_slip.status, FrictionConeStatus.SLIP_VIOLATION)
        self.assertGreater(eval_slip.tangential_force_n, 240.0)
        self.assertLess(eval_slip.friction_margin_n, 0.0)
        self.assertIn("COULOMB_SLIP_VIOLATION", eval_slip.violation_reason)

    # -------------------------------------------------------------------------
    # 5. Multi-Contact Aggregation
    # -------------------------------------------------------------------------

    def test_10_multi_contact_aggregation_and_net_momentum(self):
        """Req 10: MultiContactDynamics aggregates forces, torques, impulses, and net momentum changes."""
        com = (0.0, 1.0, 0.95)
        dt = 0.02
        multi = MultiContactDynamics(com_world=com, dt=dt)

        # Left foot stance: X=-0.15, Y=1.0, Z=0.0; F1 = (10, 20, 350)
        c_L = SingleContactDynamics(
            "foot_L", (-0.15, 1.0, 0.0), (10.0, 20.0, 350.0), com, (0, 0, 1), 0.70, dt
        )
        # Right foot stance: X=+0.15, Y=1.2, Z=0.0; F2 = (-10, 40, 350)
        c_R = SingleContactDynamics(
            "foot_R", (0.15, 1.2, 0.0), (-10.0, 40.0, 350.0), com, (0, 0, 1), 0.70, dt
        )
        multi.add_contact(c_L)
        multi.add_contact(c_R)

        # Total force: F1 + F2 = (0.0, 60.0, 700.0)
        self.assertAlmostEqual(multi.total_contact_force[0], 0.0, places=5)
        self.assertAlmostEqual(multi.total_contact_force[1], 60.0, places=5)
        self.assertAlmostEqual(multi.total_contact_force[2], 700.0, places=5)

        # Total torque about CoM: tau_L + tau_R
        expected_tau = vec3_add(c_L.torque_about_com, c_R.torque_about_com)
        self.assertAlmostEqual(multi.total_torque_about_com[0], expected_tau[0], places=5)
        self.assertAlmostEqual(multi.total_torque_about_com[1], expected_tau[1], places=5)
        self.assertAlmostEqual(multi.total_torque_about_com[2], expected_tau[2], places=5)

        # Total linear impulse: F_total * dt
        self.assertAlmostEqual(multi.total_linear_impulse[0], 0.0 * dt, places=5)
        self.assertAlmostEqual(multi.total_linear_impulse[1], 60.0 * dt, places=5)
        self.assertAlmostEqual(multi.total_linear_impulse[2], 700.0 * dt, places=5)

        # Total momentum change matches impulse
        self.assertEqual(multi.total_linear_momentum_change, multi.total_linear_impulse)
        self.assertEqual(multi.total_angular_momentum_change_about_com, multi.total_angular_impulse_about_com)

        # All friction valid
        self.assertTrue(multi.is_all_friction_valid)

    # -------------------------------------------------------------------------
    # 6. Input Validation & Error Handling
    # -------------------------------------------------------------------------

    def test_11_rejection_of_nan_inf_and_invalid_inputs(self):
        """Req 11: Rejects NaN, Inf, non-positive dt, negative mu, and degenerate normal vectors."""
        # 1. NaN in contact force
        with self.assertRaises(ValueError):
            SingleContactDynamics("nan_f", (0, 0, 0), (float("nan"), 0, 100), (0, 0, 1), (0, 0, 1))

        # 2. Inf in contact point
        with self.assertRaises(ValueError):
            SingleContactDynamics("inf_p", (float("inf"), 0, 0), (0, 0, 100), (0, 0, 1), (0, 0, 1))

        # 3. Degenerate zero normal
        with self.assertRaises(ValueError):
            SingleContactDynamics("zero_n", (0, 0, 0), (0, 0, 100), (0, 0, 1), (0.0, 0.0, 0.0))

        # 4. Negative friction coefficient
        with self.assertRaises(ValueError):
            SingleContactDynamics("neg_mu", (0, 0, 0), (0, 0, 100), (0, 0, 1), (0, 0, 1), friction_coeff=-0.5)

        # 5. Non-positive dt
        with self.assertRaises(ValueError):
            SingleContactDynamics("zero_dt", (0, 0, 0), (0, 0, 100), (0, 0, 1), (0, 0, 1), dt=0.0)
        with self.assertRaises(ValueError):
            SingleContactDynamics("neg_dt", (0, 0, 0), (0, 0, 100), (0, 0, 1), (0, 0, 1), dt=-0.01)

    # -------------------------------------------------------------------------
    # 7. Standard DynamicsPlayground Contract Testing
    # -------------------------------------------------------------------------

    def test_12_standard_playground_flat_ground_contract(self):
        """Req 12: Contact dynamics binding against standard playground flat ground (Zone 1)."""
        pt = (0.5, -2.0, 0.0)
        force = (20.0, 15.0, 686.0)  # ~70kg supporting force
        com = (0.5, -2.0, 1.0)

        contact = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt,
            contact_force_world=force,
            com_world=com,
            dt=1.0 / 24.0,
            contact_id="flat_ground_foot",
            surface_type_filter="horizontal_ground",
        )

        # Verify surface parameters inherited from environment query
        self.assertEqual(contact.surface_normal_world, (0.0, 0.0, 1.0))
        self.assertAlmostEqual(contact.friction_coeff, 0.70, places=4)

        # Verify normal force and friction compliance
        eval_res = contact.evaluate_friction_constraint()
        self.assertTrue(eval_res.is_valid)
        self.assertAlmostEqual(eval_res.normal_force_n, 686.0, places=4)
        expected_ft = math.hypot(20.0, 15.0)  # 25.0 N
        self.assertAlmostEqual(eval_res.tangential_force_n, expected_ft, places=4)
        self.assertGreater(eval_res.friction_margin_n, 0.0)

    def test_13_standard_playground_sloped_ramp_contract(self):
        """Req 13: Contact dynamics binding against standard playground sloped ramp (Zone 3)."""
        # Ramp up midpoint at Y = 13.5m (15 deg slope)
        # Center of ramp up is (0.0, 13.5, 0.66987)
        mid_y = 13.5
        expected_z = (mid_y - 11.0) * math.tan(math.radians(15.0))
        pt = (0.0, mid_y, expected_z)
        com = (0.0, mid_y, expected_z + 1.0)

        # True ramp up unit normal:
        expected_ny = -math.sin(math.radians(15.0))
        expected_nz = math.cos(math.radians(15.0))

        # Reaction force pushing perpendicular to ramp (along normal): F = 500 * normal
        f_perp = (0.0, 500.0 * expected_ny, 500.0 * expected_nz)

        contact = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt,
            contact_force_world=f_perp,
            com_world=com,
            dt=0.02,
            contact_id="ramp_up_foot",
            surface_type_filter="sloped_ramp",
        )

        # Verify exact normal and friction coefficient from playground
        self.assertAlmostEqual(contact.surface_normal_world[0], 0.0, places=5)
        self.assertAlmostEqual(contact.surface_normal_world[1], expected_ny, places=5)
        self.assertAlmostEqual(contact.surface_normal_world[2], expected_nz, places=5)
        self.assertAlmostEqual(contact.friction_coeff, 0.65, places=4)

        # Pure normal force -> 0 tangential friction
        eval_res = contact.evaluate_friction_constraint()
        self.assertTrue(eval_res.is_valid)
        self.assertAlmostEqual(eval_res.normal_force_n, 500.0, places=4)
        self.assertAlmostEqual(eval_res.tangential_force_n, 0.0, places=4)

        # Test tangential sliding force along slope (exceeding mu=0.65):
        # Tangent vector along slope: (0, cos(15 deg), sin(15 deg))
        tan_y = math.cos(math.radians(15.0))
        tan_z = math.sin(math.radians(15.0))
        # Excessive shear force of 400N (400N > 0.65 * 500 = 325N)
        f_excessive = (
            0.0,
            500.0 * expected_ny + 400.0 * tan_y,
            500.0 * expected_nz + 400.0 * tan_z,
        )
        c_slip = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt,
            contact_force_world=f_excessive,
            com_world=com,
            dt=0.02,
            surface_type_filter="sloped_ramp",
        )
        eval_slip = c_slip.evaluate_friction_constraint()
        self.assertFalse(eval_slip.is_valid)
        self.assertEqual(eval_slip.status, FrictionConeStatus.SLIP_VIOLATION)
        self.assertAlmostEqual(eval_slip.tangential_force_n, 400.0, places=4)
        self.assertAlmostEqual(eval_slip.friction_limit_n, 325.0, places=4)

    def test_14_standard_playground_vertical_wall_contract(self):
        """Req 14: Contact dynamics binding against standard playground vertical wall (Zone 4)."""
        # Wall is at Y = 24.0m, front face at Y = 23.8m, facing -Y (normal=(0, -1, 0))
        pt_wall = (0.0, 23.8, 1.5)
        com = (0.0, 23.2, 1.2)  # Character in front of wall at Y=23.2

        # A wall plant or hand push: wall pushes back on character along -Y (F_y = -300N)
        # Normal of wall is (0, -1, 0), so F . normal = (-300) * (-1) = +300N (valid normal push!)
        f_wall_push = (0.0, -300.0, 50.0)

        contact = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_wall,
            contact_force_world=f_wall_push,
            com_world=com,
            dt=0.04,
            contact_id="hand_wall_plant",
            surface_type_filter="vertical_wall",
        )

        self.assertEqual(contact.surface_normal_world, (0.0, -1.0, 0.0))
        self.assertAlmostEqual(contact.friction_coeff, 0.60, places=4)

        eval_res = contact.evaluate_friction_constraint()
        self.assertTrue(eval_res.is_valid)
        self.assertAlmostEqual(eval_res.normal_force_n, 300.0, places=4)
        self.assertAlmostEqual(eval_res.tangential_force_n, 50.0, places=4)
        self.assertAlmostEqual(eval_res.friction_limit_n, 180.0, places=4)  # 0.60 * 300 = 180N
        self.assertGreater(eval_res.friction_margin_n, 0.0)

        # Illegal pulling on wall (trying to pull wall away along +Y): F_y = +150N
        # F . normal = (+150) * (-1) = -150N < 0 (unilateral tension violation)
        f_wall_pull = (0.0, 150.0, 0.0)
        c_pull = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_wall,
            contact_force_world=f_wall_pull,
            com_world=com,
            surface_type_filter="vertical_wall",
        )
        eval_pull = c_pull.evaluate_friction_constraint()
        self.assertFalse(eval_pull.is_valid)
        self.assertEqual(eval_pull.status, FrictionConeStatus.TENSION_VIOLATION)
        self.assertAlmostEqual(eval_pull.normal_force_n, -150.0, places=4)

    def test_15_standard_playground_out_of_bounds_and_filtering_errors(self):
        """Req 15: Out-of-bounds contact points or mismatched filters truthfully raise ValueError."""
        # Point far in empty space (100m away) where no surface exists
        with self.assertRaises(ValueError):
            create_contact_dynamics_from_environment(
                env_query=self.playground_query,
                contact_point_world=(100.0, 100.0, 50.0),
                contact_force_world=(0, 0, 100),
                com_world=(0, 0, 1),
                max_search_distance=2.0,
            )

        # Point at ground (0, 0, 0) filtering for 'vertical_wall' (no vertical wall within 2.0m)
        with self.assertRaises(ValueError):
            create_contact_dynamics_from_environment(
                env_query=self.playground_query,
                contact_point_world=(0.0, 0.0, 0.0),
                contact_force_world=(0, 0, 100),
                com_world=(0, 0, 1),
                surface_type_filter="vertical_wall",
                max_search_distance=2.0,
            )

    # -------------------------------------------------------------------------
    # 5. Task 6G-D-A-R1 Contract Additions: dt Consistency & Contact Validity
    # -------------------------------------------------------------------------

    def test_16_multi_contact_dt_consistency_enforcement(self):
        """Req 16: MultiContactDynamics owns unified dt; rejects contact dt mismatch."""
        dt_sys = 0.02
        com = (0.0, 0.0, 1.0)
        c1 = SingleContactDynamics(
            contact_id="foot_L",
            contact_point_world=(-0.1, 0.0, 0.0),
            contact_force_world=(0.0, 0.0, 300.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            dt=dt_sys,
        )
        c2 = SingleContactDynamics(
            contact_id="foot_R",
            contact_point_world=(0.1, 0.0, 0.0),
            contact_force_world=(0.0, 0.0, 300.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            dt=dt_sys,
        )
        c_mismatch = SingleContactDynamics(
            contact_id="hand_R",
            contact_point_world=(0.2, 0.0, 0.8),
            contact_force_world=(0.0, 0.0, 50.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            dt=0.04,  # Mismatched dt!
        )

        # 1. Matching contacts initialize cleanly
        multi = MultiContactDynamics(contacts=[c1, c2], com_world=com, dt=dt_sys)
        self.assertEqual(len(multi.contacts), 2)
        self.assertAlmostEqual(multi.total_linear_impulse[2], (300.0 + 300.0) * dt_sys, places=5)
        self.assertAlmostEqual(
            multi.total_linear_impulse[2],
            c1.linear_impulse[2] + c2.linear_impulse[2],
            places=5,
        )

        # 2. Rejects contact with mismatched dt during constructor initialization
        with self.assertRaises(ValueError) as ctx:
            MultiContactDynamics(contacts=[c1, c_mismatch], com_world=com, dt=dt_sys)
        self.assertIn("Time step mismatch", str(ctx.exception))

        # 3. Rejects contact with mismatched dt during add_contact
        with self.assertRaises(ValueError) as ctx:
            multi.add_contact(c_mismatch)
        self.assertIn("Time step mismatch", str(ctx.exception))

        # 4. set_dt with update_contacts=True synchronizes all child contacts
        multi.set_dt(0.05, update_contacts=True)
        self.assertAlmostEqual(multi.dt, 0.05, places=5)
        self.assertAlmostEqual(c1.dt, 0.05, places=5)
        self.assertAlmostEqual(c2.dt, 0.05, places=5)

        # 5. set_dt with update_contacts=False raises if contacts don't match
        with self.assertRaises(ValueError):
            multi.set_dt(0.01, update_contacts=False)

    def test_17_contact_validity_and_clearance_tolerance(self):
        """Req 17: Physical contact validity vs proximity binding, tolerance, and force violation."""
        com = (0.0, 0.0, 1.0)
        tolerance = 0.02  # 20mm tolerance

        # 1. Exact surface contact (Z=0.0 on flat ground): valid physical contact
        pt_exact = (0.0, 0.0, 0.0)
        c_exact = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_exact,
            contact_force_world=(0.0, 0.0, 400.0),
            com_world=com,
            contact_tolerance=tolerance,
            require_contact=True,
        )
        self.assertTrue(c_exact.is_in_contact)
        self.assertAlmostEqual(c_exact.surface_distance, 0.0, places=4)
        eval_exact = c_exact.evaluate_friction_constraint()
        self.assertTrue(eval_exact.is_valid)

        # 2. Within tolerance (Z=0.015m, 15mm clearance <= 20mm): valid physical contact
        pt_close = (0.0, 0.0, 0.015)
        c_close = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_close,
            contact_force_world=(0.0, 0.0, 400.0),
            com_world=com,
            contact_tolerance=tolerance,
            require_contact=True,
        )
        self.assertTrue(c_close.is_in_contact)
        self.assertAlmostEqual(c_close.surface_distance, 0.015, places=4)

        # 3. Separated contact (Z=0.05m, 50mm clearance > 20mm):
        pt_separated = (0.0, 0.0, 0.05)

        # 3a. require_contact=True strictly rejects separated contact
        with self.assertRaises(ValueError) as ctx:
            create_contact_dynamics_from_environment(
                env_query=self.playground_query,
                contact_point_world=pt_separated,
                contact_force_world=(0.0, 0.0, 400.0),
                com_world=com,
                contact_tolerance=tolerance,
                require_contact=True,
            )
        self.assertIn("Contact validity violation", str(ctx.exception))

        # 3b. require_contact=False allows geometric proximity binding with is_in_contact=False
        c_prox = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_separated,
            contact_force_world=(0.0, 0.0, 100.0),  # Non-zero force on separated point
            com_world=com,
            contact_tolerance=tolerance,
            require_contact=False,
        )
        self.assertFalse(c_prox.is_in_contact)
        self.assertAlmostEqual(c_prox.surface_distance, 0.05, places=4)

        # 3c. Non-zero force on separated point triggers NON_CONTACT_FORCE_VIOLATION
        eval_violation = c_prox.evaluate_friction_constraint()
        self.assertFalse(eval_violation.is_valid)
        self.assertEqual(eval_violation.status, FrictionConeStatus.NON_CONTACT_FORCE_VIOLATION)
        self.assertIn("NON_CONTACT_FORCE_VIOLATION", eval_violation.violation_reason)

        # 3d. Zero force on separated point evaluates to SEPARATED (valid)
        c_prox_zero = create_contact_dynamics_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_separated,
            contact_force_world=(0.0, 0.0, 0.0),  # Zero force on separated point
            com_world=com,
            contact_tolerance=tolerance,
            require_contact=False,
        )
        eval_separated = c_prox_zero.evaluate_friction_constraint()
        self.assertTrue(eval_separated.is_valid)
        self.assertEqual(eval_separated.status, FrictionConeStatus.SEPARATED)


if __name__ == "__main__":
    unittest.main()
