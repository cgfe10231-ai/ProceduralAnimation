"""Verification and Mathematical Validation of Contact Force Solver (Task 6G-D-B).

Covers all 16 core test specifications from Task 6G-D-B:
1. Test 1: Single-point vertical support (70kg character, g=9.81m/s^2, F_z ≈ 686.7N).
2. Test 2: Dual-foot symmetric static support (symmetric 50/50 load share ≈ 343.35N).
3. Test 3: CoM offset adaptation (2:1 load split at x=0.05; INFEASIBLE/APPROXIMATE outside base at x=0.25).
4. Test 4: Single-point contact geometric torque limitations (cannot generate torque parallel to lever arm).
5. Test 5: No-contact / separated contact state (zero force, non-zero target -> INFEASIBLE).
6. Test 6: Frictionless ground (mu = 0: shear force cannot be generated -> APPROXIMATE/INFEASIBLE).
7. Test 7: Coulomb friction limits (below limit -> SOLVED; above limit -> APPROXIMATE with exact residual).
8. Test 8: Sloped ramp contact (real 15° ramp from standard DynamicsPlayground).
9. Test 9: Vertical wall contact (real vertical wall from standard DynamicsPlayground; push allowed, pull rejected).
10. Test 10: Multi-contact heterogeneous normals (ground + ramp + wall in unified World Space).
11. Test 11: Torque consistency with independent MultiContactDynamics evaluation.
12. Test 12: Infeasible target detection (tensile pull on ground strictly rejected, status INFEASIBLE).
13. Test 13: Numerical degeneracy and illegal input rejection (NaN, Inf, zero normal, negative mass).
14. Test 14: Permutation invariance (order of contacts does not alter physical solution).
15. Test 15: Determinism and reproducibility across repeated calls.
16. Test 16: Backward compatibility (SingleContactDynamics and MultiContactDynamics contracts unregressed).
17. Test 17: Linear contact mapping matrix A verification (A * f == [sum(F), sum(r x F)]).
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
    MultiContactDynamics,
    SingleContactDynamics,
    Vec3,
    vec3_cross,
    vec3_dot,
    vec3_length,
    vec3_sub,
)
from src.motion.contact_force_solver import (
    ContactConstraintSpec,
    ContactForceSolution,
    ContactSolverConfig,
    ContactSolverStatus,
    ContactWrenchTarget,
    build_contact_mapping_matrix,
    contact_mapping_multiply,
    create_contact_constraint_from_environment,
    project_to_friction_cone,
    solution_to_multi_contact_dynamics,
    solve_contact_forces,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    create_standard_dynamics_playground_query,
)


class TestContactForceSolver(unittest.TestCase):
    """Rigorous unit test suite for Contact Force Solver and Constraint Allocation."""

    @classmethod
    def setUpClass(cls):
        cls.playground_query = create_standard_dynamics_playground_query()
        cls.default_config = ContactSolverConfig(
            force_tolerance_n=0.05,
            torque_tolerance_nm=0.05,
            constraint_tolerance=1e-4,
        )

    # -------------------------------------------------------------------------
    # Test 1: Single-Point Vertical Support
    # -------------------------------------------------------------------------
    def test_01_single_contact_vertical_support(self):
        """Test 1: Single flat ground contact supporting 70kg character in static equilibrium."""
        mass = 70.0
        g = 9.81
        com = (0.0, 0.0, 1.0)
        target = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.0, 0.0, 0.0),
            com_world=com,
            gravity_z=-g,
        )
        expected_fz = mass * g  # 686.7 N
        self.assertAlmostEqual(target.target_force_world[2], expected_fz, places=4)
        self.assertAlmostEqual(target.target_force_world[0], 0.0, places=4)
        self.assertAlmostEqual(target.target_force_world[1], 0.0, places=4)

        contact = ContactConstraintSpec(
            contact_id="single_foot",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )

        sol = solve_contact_forces(target, [contact], self.default_config)
        self.assertEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol.is_physically_valid)

        F = sol.contact_forces["single_foot"]
        self.assertAlmostEqual(F[0], 0.0, delta=0.05)
        self.assertAlmostEqual(F[1], 0.0, delta=0.05)
        self.assertAlmostEqual(F[2], expected_fz, delta=0.05)

        self.assertLessEqual(sol.force_residual_n, self.default_config.force_tolerance_n)
        self.assertLessEqual(sol.torque_residual_nm, self.default_config.torque_tolerance_nm)

    # -------------------------------------------------------------------------
    # Test 2: Dual Foot Symmetric Static Support
    # -------------------------------------------------------------------------
    def test_02_dual_foot_symmetric_static_support(self):
        """Test 2: Two symmetric feet on flat ground; load splits evenly (approx 343.35N each)."""
        mass = 70.0
        g = 9.81
        com = (0.0, 0.0, 1.0)
        target = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.0, 0.0, 0.0),
            com_world=com,
            gravity_z=-g,
        )
        expected_total_fz = mass * g  # 686.7 N

        foot_L = ContactConstraintSpec(
            contact_id="foot_L",
            contact_point_world=(-0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )
        foot_R = ContactConstraintSpec(
            contact_id="foot_R",
            contact_point_world=(0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )

        sol = solve_contact_forces(target, [foot_L, foot_R], self.default_config)
        self.assertEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol.is_physically_valid)

        F_L = sol.contact_forces["foot_L"]
        F_R = sol.contact_forces["foot_R"]

        # Both feet share the vertical load equally (~343.35 N)
        self.assertAlmostEqual(F_L[2], expected_total_fz / 2.0, delta=0.1)
        self.assertAlmostEqual(F_R[2], expected_total_fz / 2.0, delta=0.1)
        self.assertAlmostEqual(F_L[0], 0.0, delta=0.05)
        self.assertAlmostEqual(F_R[0], 0.0, delta=0.05)

        # Total force balances target
        self.assertAlmostEqual(sol.total_contact_force[2], expected_total_fz, delta=0.05)
        self.assertLessEqual(sol.force_residual_n, self.default_config.force_tolerance_n)
        self.assertLessEqual(sol.torque_residual_nm, self.default_config.torque_tolerance_nm)

    # -------------------------------------------------------------------------
    # Test 3: CoM Offset Adaptation
    # -------------------------------------------------------------------------
    def test_03_com_offset_adaptation(self):
        """Test 3: Shifted CoM shifts load distribution; CoM outside base triggers APPROXIMATE/INFEASIBLE."""
        mass = 70.0
        g = 9.81
        expected_total_fz = mass * g  # 686.7 N

        foot_L = ContactConstraintSpec(
            contact_id="foot_L",
            contact_point_world=(-0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )
        foot_R = ContactConstraintSpec(
            contact_id="foot_R",
            contact_point_world=(0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )

        # 3a. CoM shifted to x = +0.05 (2/3 toward right foot)
        # Lever arm to L is -0.20, lever arm to R is +0.10 -> R carries 2x L load
        com_shifted = (0.05, 0.0, 1.0)
        target_shifted = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.0, 0.0, 0.0),
            com_world=com_shifted,
            gravity_z=-g,
        )

        sol_shifted = solve_contact_forces(target_shifted, [foot_L, foot_R], self.default_config)
        self.assertEqual(sol_shifted.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_shifted.is_physically_valid)

        F_L = sol_shifted.contact_forces["foot_L"]
        F_R = sol_shifted.contact_forces["foot_R"]

        # Expected: F_L ≈ 686.7 * (0.10 / 0.30) = 228.9 N; F_R ≈ 686.7 * (0.20 / 0.30) = 457.8 N
        self.assertAlmostEqual(F_L[2], expected_total_fz * (1.0 / 3.0), delta=0.5)
        self.assertAlmostEqual(F_R[2], expected_total_fz * (2.0 / 3.0), delta=0.5)

        # 3b. CoM shifted outside base to x = +0.25 (past right foot at 0.15)
        # To balance torque, left foot would need negative normal force (tension), which is forbidden!
        com_outside = (0.25, 0.0, 1.0)
        target_outside = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.0, 0.0, 0.0),
            com_world=com_outside,
            gravity_z=-g,
        )

        sol_outside = solve_contact_forces(target_outside, [foot_L, foot_R], self.default_config)
        self.assertIn(sol_outside.status, (ContactSolverStatus.APPROXIMATE, ContactSolverStatus.INFEASIBLE))
        self.assertNotEqual(sol_outside.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_outside.is_physically_valid)  # Still respects F_n >= 0
        self.assertGreater(sol_outside.torque_residual_nm, self.default_config.torque_tolerance_nm)

    # -------------------------------------------------------------------------
    # Test 4: Single-Point Contact Torque Limitations
    # -------------------------------------------------------------------------
    def test_04_single_point_contact_torque_limitations(self):
        """Test 4: Single point contact cannot generate torque parallel to its lever arm."""
        com = (0.0, 0.0, 1.0)
        # Single contact at origin, lever arm r = (0, 0, -1.0)
        contact = ContactConstraintSpec(
            contact_id="pivot_point",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )
        # Target includes a yaw torque tau_z = 25.0 N*m
        target = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 686.7),
            target_torque_world=(0.0, 0.0, 25.0),
            com_world=com,
        )

        sol = solve_contact_forces(target, [contact], self.default_config)
        # Point contact cannot generate torque along z-axis because r x F has zero z-component
        self.assertIn(sol.status, (ContactSolverStatus.APPROXIMATE, ContactSolverStatus.INFEASIBLE))
        self.assertNotEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol.is_physically_valid)
        self.assertAlmostEqual(sol.torque_error_vector[2], -25.0, delta=0.5)

    # -------------------------------------------------------------------------
    # Test 5: No Contact / Separated Contact State
    # -------------------------------------------------------------------------
    def test_05_no_contact_state(self):
        """Test 5: Separated contacts must produce zero force; non-zero target is INFEASIBLE."""
        com = (0.0, 0.0, 1.0)
        # Inactive/separated contact
        separated_contact = ContactConstraintSpec(
            contact_id="air_foot",
            contact_point_world=(0.0, 0.0, 0.10),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
            is_in_contact=False,  # Separated
        )

        # 5a. Non-zero force target with separated contacts -> INFEASIBLE
        target_nonzero = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 686.7),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_nonzero = solve_contact_forces(target_nonzero, [separated_contact], self.default_config)
        self.assertEqual(sol_nonzero.status, ContactSolverStatus.INFEASIBLE)
        self.assertEqual(sol_nonzero.contact_forces["air_foot"], (0.0, 0.0, 0.0))
        self.assertAlmostEqual(sol_nonzero.force_residual_n, 686.7, places=4)

        # 5b. Zero wrench target in free-flight -> SOLVED with zero forces
        target_zero = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 0.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_zero = solve_contact_forces(target_zero, [separated_contact], self.default_config)
        self.assertEqual(sol_zero.status, ContactSolverStatus.SOLVED)
        self.assertEqual(sol_zero.contact_forces["air_foot"], (0.0, 0.0, 0.0))
        self.assertEqual(sol_zero.force_residual_n, 0.0)

    # -------------------------------------------------------------------------
    # Test 6: Frictionless Ground (mu = 0)
    # -------------------------------------------------------------------------
    def test_06_frictionless_ground(self):
        """Test 6: On frictionless ground (mu=0), horizontal shear force cannot be generated."""
        com = (0.0, 0.0, 1.0)
        ice_contact = ContactConstraintSpec(
            contact_id="ice_foot",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.0,  # Zero friction (ideal ice)
        )

        # Target requires 100N horizontal pushing force
        target_shear = ContactWrenchTarget(
            target_force_world=(100.0, 0.0, 686.7),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_shear = solve_contact_forces(target_shear, [ice_contact], self.default_config)
        self.assertIn(sol_shear.status, (ContactSolverStatus.APPROXIMATE, ContactSolverStatus.INFEASIBLE))
        self.assertNotEqual(sol_shear.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_shear.is_physically_valid)

        # Horizontal force is strictly clamped to zero
        F = sol_shear.contact_forces["ice_foot"]
        self.assertAlmostEqual(F[0], 0.0, places=4)
        self.assertAlmostEqual(F[1], 0.0, places=4)
        self.assertAlmostEqual(F[2], 686.7, delta=0.05)

        # Pure vertical target on ice is fully SOLVED
        target_vert = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 686.7),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_vert = solve_contact_forces(target_vert, [ice_contact], self.default_config)
        self.assertEqual(sol_vert.status, ContactSolverStatus.SOLVED)

    # -------------------------------------------------------------------------
    # Test 7: Coulomb Friction Limits
    # -------------------------------------------------------------------------
    def test_07_coulomb_friction_limits(self):
        """Test 7: Tangential force within friction limit solves; exceeding limit clamps and yields APPROXIMATE."""
        com = (0.0, 0.0, 1.0)
        # Normal force target 500 N, mu = 0.50 -> Max allowable friction is 250 N
        contact = ContactConstraintSpec(
            contact_id="foot_fric",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.50,
        )

        # 7a. Within friction limit (Ft = 150 N < 250 N) -> SOLVED
        target_within = ContactWrenchTarget(
            target_force_world=(150.0, 0.0, 500.0),
            target_torque_world=(0.0, -150.0, 0.0),  # r x F = (0,0,-1) x (150,0,500) = (0, -150, 0)
            com_world=com,
        )
        sol_within = solve_contact_forces(target_within, [contact], self.default_config)
        self.assertEqual(sol_within.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_within.is_physically_valid)
        self.assertAlmostEqual(sol_within.contact_forces["foot_fric"][0], 150.0, delta=0.1)

        # 7b. Exactly at friction limit (Ft = 250 N == 0.5 * 500 N) -> SOLVED
        target_limit = ContactWrenchTarget(
            target_force_world=(250.0, 0.0, 500.0),
            target_torque_world=(0.0, -250.0, 0.0),
            com_world=com,
        )
        sol_limit = solve_contact_forces(target_limit, [contact], self.default_config)
        self.assertEqual(sol_limit.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_limit.is_physically_valid)
        self.assertAlmostEqual(sol_limit.contact_forces["foot_fric"][0], 250.0, delta=0.5)

        # 7c. Exceeding friction limit (Ft = 350 N > 250 N) with max_normal_force = 500 N
        # -> Bounded by mu * Fn = 0.50 * 500 = 250 N -> APPROXIMATE with ~100N residual
        contact_capped = ContactConstraintSpec(
            contact_id="foot_fric",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.50,
            max_normal_force=500.0,
        )
        target_exceed = ContactWrenchTarget(
            target_force_world=(350.0, 0.0, 500.0),
            target_torque_world=(0.0, -350.0, 0.0),
            com_world=com,
        )
        sol_exceed = solve_contact_forces(target_exceed, [contact_capped], self.default_config)
        self.assertEqual(sol_exceed.status, ContactSolverStatus.APPROXIMATE)
        self.assertTrue(sol_exceed.is_physically_valid)
        # Tangential force must not exceed 250 N
        Ft_solved = sol_exceed.contact_forces["foot_fric"][0]
        self.assertLessEqual(Ft_solved, 250.0 + 1e-4)
        self.assertAlmostEqual(Ft_solved, 250.0, delta=1.0)
        self.assertAlmostEqual(sol_exceed.force_residual_n, 100.0, delta=1.5)

    # -------------------------------------------------------------------------
    # Test 8: Sloped Ramp Contact (from DynamicsPlayground)
    # -------------------------------------------------------------------------
    def test_08_sloped_ramp_contact(self):
        """Test 8: Contact dynamics on real 15° sloped ramp from standard DynamicsPlayground."""
        # Query analytical surface of Zone 3 sloped ramp (+15° up ramp, Y in [11.0, 16.0])
        mid_y = 13.5
        expected_z = (mid_y - 11.0) * math.tan(math.radians(15.0))  # ≈ 0.66987m
        pt_ramp = (0.0, mid_y, expected_z)
        ramp_contact = create_contact_constraint_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_ramp,
            contact_id="ramp_foot",
            surface_type_filter="sloped_ramp",
        )
        self.assertTrue(ramp_contact.is_in_contact)
        self.assertAlmostEqual(ramp_contact.friction_coeff, 0.65, places=4)
        # Normal should be tilted: (0, -sin 15°, cos 15°)
        ny_exp = -math.sin(math.radians(15.0))
        nz_exp = math.cos(math.radians(15.0))
        self.assertAlmostEqual(ramp_contact.surface_normal_world[1], ny_exp, places=4)
        self.assertAlmostEqual(ramp_contact.surface_normal_world[2], nz_exp, places=4)

        com = (0.0, mid_y, expected_z + 1.0)
        # Target normal support force of 500 N along ramp outward normal
        f_target = (0.0, 500.0 * ny_exp, 500.0 * nz_exp)
        r = (0.0, 0.0, -1.0)
        tau_target = vec3_cross(r, f_target)

        target = ContactWrenchTarget(
            target_force_world=f_target,
            target_torque_world=tau_target,
            com_world=com,
        )

        sol = solve_contact_forces(target, [ramp_contact], self.default_config)
        self.assertEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol.is_physically_valid)

        F = sol.contact_forces["ramp_foot"]
        fn = vec3_dot(F, ramp_contact.surface_normal_world)
        self.assertAlmostEqual(fn, 500.0, delta=0.5)

    # -------------------------------------------------------------------------
    # Test 9: Vertical Wall Contact (from DynamicsPlayground)
    # -------------------------------------------------------------------------
    def test_09_vertical_wall_contact(self):
        """Test 9: Vertical wall contact from standard DynamicsPlayground; push allowed, pull rejected."""
        pt_wall = (0.0, 23.8, 1.5)
        wall_contact = create_contact_constraint_from_environment(
            env_query=self.playground_query,
            contact_point_world=pt_wall,
            contact_id="hand_wall",
            surface_type_filter="vertical_wall",
        )
        self.assertTrue(wall_contact.is_in_contact)
        self.assertEqual(wall_contact.surface_normal_world, (0.0, -1.0, 0.0))
        self.assertAlmostEqual(wall_contact.friction_coeff, 0.60, places=4)

        com = (0.0, 23.0, 1.2)

        # 9a. Normal push reaction: wall pushes character along -Y by 300N (Fy = -300N)
        f_push = (0.0, -300.0, 0.0)
        r = (0.0, 0.8, 0.3)
        tau_push = vec3_cross(r, f_push)
        target_push = ContactWrenchTarget(
            target_force_world=f_push,
            target_torque_world=tau_push,
            com_world=com,
        )

        sol_push = solve_contact_forces(target_push, [wall_contact], self.default_config)
        self.assertEqual(sol_push.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_push.is_physically_valid)
        self.assertAlmostEqual(sol_push.contact_forces["hand_wall"][1], -300.0, delta=0.5)

        # 9b. Tensile pull: trying to pull wall along +Y by +200N is strictly rejected
        f_pull = (0.0, 200.0, 0.0)
        target_pull = ContactWrenchTarget(
            target_force_world=f_pull,
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_pull = solve_contact_forces(target_pull, [wall_contact], self.default_config)
        self.assertIn(sol_pull.status, (ContactSolverStatus.APPROXIMATE, ContactSolverStatus.INFEASIBLE))
        self.assertNotEqual(sol_pull.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_pull.is_physically_valid)
        # Normal force F . n = (+Fy) * (-1) must not be negative
        self.assertLessEqual(sol_pull.contact_forces["hand_wall"][1], 1e-4)

    # -------------------------------------------------------------------------
    # Test 10: Multi-Contact with Heterogeneous Normals
    # -------------------------------------------------------------------------
    def test_10_multi_contact_heterogeneous_normals(self):
        """Test 10: Multi-contact with flat ground, sloped ramp, and vertical wall in unified World Space."""
        com = (0.0, 5.0, 1.0)
        c_ground = ContactConstraintSpec(
            contact_id="ground_foot",
            contact_point_world=(-0.2, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
        )
        ny = -math.sin(math.radians(15.0))
        nz = math.cos(math.radians(15.0))
        c_ramp = ContactConstraintSpec(
            contact_id="ramp_foot",
            contact_point_world=(0.2, 8.0, 0.5),
            surface_normal_world=(0.0, ny, nz),
            friction_coeff=0.65,
        )
        c_wall = ContactConstraintSpec(
            contact_id="wall_hand",
            contact_point_world=(0.0, 23.8, 1.5),
            surface_normal_world=(0.0, -1.0, 0.0),
            friction_coeff=0.60,
        )

        target = ContactWrenchTarget(
            target_force_world=(0.0, -100.0, 686.7),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )

        sol = solve_contact_forces(target, [c_ground, c_ramp, c_wall], self.default_config)
        self.assertTrue(sol.is_physically_valid)
        self.assertIn(sol.status, (ContactSolverStatus.SOLVED, ContactSolverStatus.APPROXIMATE))
        # Total force matches within acceptable tolerance
        self.assertLessEqual(sol.force_residual_n, 0.1)

    # -------------------------------------------------------------------------
    # Test 11: Torque Consistency with MultiContactDynamics
    # -------------------------------------------------------------------------
    def test_11_torque_consistency_with_multi_contact_dynamics(self):
        """Test 11: Compare solver net torque with independent MultiContactDynamics evaluation."""
        mass = 70.0
        com = (0.05, 0.02, 1.1)
        target = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.2, 0.1, 0.0),
            com_world=com,
            gravity_z=-9.81,
        )
        foot_L = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        foot_R = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)

        sol = solve_contact_forces(target, [foot_L, foot_R], self.default_config)
        self.assertTrue(sol.is_physically_valid)

        # Convert to MultiContactDynamics
        multi = solution_to_multi_contact_dynamics(sol, [foot_L, foot_R], com_world=com, dt=0.04)
        self.assertEqual(len(multi.contacts), 2)

        # Compare total force
        self.assertAlmostEqual(sol.total_contact_force[0], multi.total_contact_force[0], places=5)
        self.assertAlmostEqual(sol.total_contact_force[1], multi.total_contact_force[1], places=5)
        self.assertAlmostEqual(sol.total_contact_force[2], multi.total_contact_force[2], places=5)

        # Compare total torque about CoM
        self.assertAlmostEqual(sol.total_contact_torque_about_com[0], multi.total_torque_about_com[0], places=5)
        self.assertAlmostEqual(sol.total_contact_torque_about_com[1], multi.total_torque_about_com[1], places=5)
        self.assertAlmostEqual(sol.total_contact_torque_about_com[2], multi.total_torque_about_com[2], places=5)

    # -------------------------------------------------------------------------
    # Test 12: Infeasible Target Detection
    # -------------------------------------------------------------------------
    def test_12_infeasible_targets(self):
        """Test 12: Tensile downward pull on ground is truthfully reported as INFEASIBLE, never SOLVED."""
        com = (0.0, 0.0, 1.0)
        foot_L = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        foot_R = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)

        # Target requires downward pull on ground F_z = -500 N
        target_down = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, -500.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )

        sol = solve_contact_forces(target_down, [foot_L, foot_R], self.default_config)
        self.assertEqual(sol.status, ContactSolverStatus.INFEASIBLE)
        self.assertNotEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol.is_physically_valid)
        # Normal force must not be negative
        self.assertGreaterEqual(sol.contact_forces["foot_L"][2], -1e-5)
        self.assertGreaterEqual(sol.contact_forces["foot_R"][2], -1e-5)

    # -------------------------------------------------------------------------
    # Test 13: Numerical Degeneracy and Illegal Parameter Rejection
    # -------------------------------------------------------------------------
    def test_13_numerical_degeneracy_and_invalid_inputs(self):
        """Test 13: Robust rejection of NaN, Inf, zero normal, negative mass without uncaught exceptions."""
        com = (0.0, 0.0, 1.0)
        valid_contact = ContactConstraintSpec("foot", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)

        # 1. Negative mass raises ValueError
        with self.assertRaises(ValueError):
            ContactWrenchTarget.from_target_motion(
                mass=-70.0, target_linear_acc=(0, 0, 0), com_world=com
            )

        # 2. Degenerate zero normal in spec raises ValueError
        with self.assertRaises(ValueError):
            ContactConstraintSpec("bad_norm", (0, 0, 0), (0.0, 0.0, 0.0), 0.70)

        # 3. Negative friction raises ValueError
        with self.assertRaises(ValueError):
            ContactConstraintSpec("bad_mu", (0, 0, 0), (0.0, 0.0, 1.0), -0.5)

        # 4. Target containing NaN/Inf is strictly rejected with ValueError during instantiation
        with self.assertRaises(ValueError):
            ContactWrenchTarget(
                target_force_world=(float("nan"), 0.0, 686.7),
                target_torque_world=(0.0, 0.0, 0.0),
                com_world=com,
            )
        with self.assertRaises(ValueError):
            ContactWrenchTarget(
                target_force_world=(0.0, 0.0, 686.7),
                target_torque_world=(0.0, float("inf"), 0.0),
                com_world=com,
            )

        # 5. Very small friction coefficient (mu = 1e-6) solves cleanly without dividing by zero
        low_fric = ContactConstraintSpec("low_mu", (0, 0, 0), (0, 0, 1.0), 1e-6)
        vert_target = ContactWrenchTarget((0, 0, 100.0), (0, 0, 0), com)
        sol_low = solve_contact_forces(vert_target, [low_fric], self.default_config)
        self.assertEqual(sol_low.status, ContactSolverStatus.SOLVED)
        self.assertTrue(sol_low.is_physically_valid)

    # -------------------------------------------------------------------------
    # Test 14: Permutation Invariance
    # -------------------------------------------------------------------------
    def test_14_permutation_invariance(self):
        """Test 14: Swapping input contact order yields identical physical solutions."""
        com = (0.0, 0.0, 1.0)
        target = ContactWrenchTarget((0.0, 0.0, 686.7), (0.0, 0.0, 0.0), com)
        cL = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        cR = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)

        sol_LR = solve_contact_forces(target, [cL, cR], self.default_config)
        sol_RL = solve_contact_forces(target, [cR, cL], self.default_config)

        self.assertEqual(sol_LR.status, sol_RL.status)
        self.assertAlmostEqual(sol_LR.contact_forces["foot_L"][2], sol_RL.contact_forces["foot_L"][2], places=4)
        self.assertAlmostEqual(sol_LR.contact_forces["foot_R"][2], sol_RL.contact_forces["foot_R"][2], places=4)
        self.assertAlmostEqual(sol_LR.total_contact_force[2], sol_RL.total_contact_force[2], places=4)
        self.assertAlmostEqual(sol_LR.force_residual_n, sol_RL.force_residual_n, places=4)

    # -------------------------------------------------------------------------
    # Test 15: Determinism and Reproducibility
    # -------------------------------------------------------------------------
    def test_15_determinism_and_reproducibility(self):
        """Test 15: Repeated calls with identical inputs produce bitwise or epsilon-identical results."""
        com = (0.02, -0.01, 1.05)
        target = ContactWrenchTarget((10.0, 5.0, 686.7), (1.0, -0.5, 0.0), com)
        cL = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        cR = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)

        runs = [solve_contact_forces(target, [cL, cR], self.default_config) for _ in range(5)]
        first = runs[0]
        for other in runs[1:]:
            self.assertEqual(first.status, other.status)
            self.assertAlmostEqual(first.contact_forces["foot_L"][2], other.contact_forces["foot_L"][2], places=6)
            self.assertAlmostEqual(first.contact_forces["foot_R"][2], other.contact_forces["foot_R"][2], places=6)
            self.assertAlmostEqual(first.force_residual_n, other.force_residual_n, places=6)

    # -------------------------------------------------------------------------
    # Test 16: Backward Compatibility
    # -------------------------------------------------------------------------
    def test_16_backward_compatibility(self):
        """Test 16: SingleContactDynamics and MultiContactDynamics contracts remain unregressed."""
        com = (0.0, 0.0, 1.0)
        c = SingleContactDynamics(
            contact_id="compat_foot",
            contact_point_world=(0.1, 0.0, 0.0),
            contact_force_world=(0.0, 0.0, 300.0),
            com_world=com,
            surface_normal_world=(0.0, 0.0, 1.0),
            dt=0.02,
        )
        self.assertTrue(c.is_in_contact)
        self.assertAlmostEqual(c.linear_impulse[2], 6.0, places=4)

        multi = MultiContactDynamics(contacts=[c], com_world=com, dt=0.02)
        self.assertEqual(len(multi.contacts), 1)
        self.assertAlmostEqual(multi.total_linear_impulse[2], 6.0, places=4)

    # -------------------------------------------------------------------------
    # Test 17: Linear Contact Mapping Matrix A Contract
    # -------------------------------------------------------------------------
    def test_17_linear_contact_mapping_matrix_contract(self):
        """Test 17: Linear contact grasp matrix A satisfies w = A * f == [sum(F), sum(r x F)]."""
        com = (0.5, 1.0, 1.2)
        c1 = ContactConstraintSpec("c1", (-0.1, 0.8, 0.0), (0, 0, 1), 0.7)
        c2 = ContactConstraintSpec("c2", (0.2, 1.3, 0.0), (0, 0, 1), 0.7)
        c3 = ContactConstraintSpec("c3", (0.0, 2.0, 1.5), (0, -1, 0), 0.6)

        contacts = [c1, c2, c3]
        A = build_contact_mapping_matrix(contacts, com_world=com)

        # Matrix dimensions must be 6 x (3 * 3) = 6 x 9
        self.assertEqual(len(A), 6)
        self.assertTrue(all(len(row) == 9 for row in A))

        # Test with arbitrary non-zero force vectors
        f1 = (10.0, 20.0, 300.0)
        f2 = (-5.0, 15.0, 250.0)
        f3 = (0.0, -100.0, 50.0)
        forces = [f1, f2, f3]

        w_F, w_tau = contact_mapping_multiply(A, forces)

        # Independent reference calculation
        expected_F = (
            f1[0] + f2[0] + f3[0],
            f1[1] + f2[1] + f3[1],
            f1[2] + f2[2] + f3[2],
        )
        r1 = (c1.contact_point_world[0] - com[0], c1.contact_point_world[1] - com[1], c1.contact_point_world[2] - com[2])
        r2 = (c2.contact_point_world[0] - com[0], c2.contact_point_world[1] - com[1], c2.contact_point_world[2] - com[2])
        r3 = (c3.contact_point_world[0] - com[0], c3.contact_point_world[1] - com[1], c3.contact_point_world[2] - com[2])
        t1 = vec3_cross(r1, f1)
        t2 = vec3_cross(r2, f2)
        t3 = vec3_cross(r3, f3)
        expected_tau = (
            t1[0] + t2[0] + t3[0],
            t1[1] + t2[1] + t3[1],
            t1[2] + t2[2] + t3[2],
        )

        for k in range(3):
            self.assertAlmostEqual(w_F[k], expected_F[k], places=6)
            self.assertAlmostEqual(w_tau[k], expected_tau[k], places=6)


if __name__ == "__main__":
    unittest.main()
