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
    vec3_normalize,
    vec3_scale,
    vec3_sub,
)
from src.motion.contact_force_solver import (
    HAVE_SCIPY,
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

    # -------------------------------------------------------------------------
    # Test 18: Bounded Friction Cone Exact Counterexample (Task 6G-D-B-R1)
    # -------------------------------------------------------------------------
    def test_18_bounded_friction_cone_exact_counterexample(self):
        """Test 18: F=(1,0,10) under n=(0,0,1), mu=0.5, max_Fn=5 projects to (1,0,5), not (0.5,0,5)."""
        F = (1.0, 0.0, 10.0)
        normal = (0.0, 0.0, 1.0)
        mu = 0.5
        min_fn = 0.0
        max_fn = 5.0

        F_proj = project_to_friction_cone(F, normal, mu, min_fn, max_fn)

        # Theoretical closest feasible point in K:
        # At Fn = 5.0, max allowable tangential force is mu * Fn = 0.5 * 5.0 = 2.5.
        # Since Ft = 1.0 <= 2.5, the tangential force 1.0 is completely feasible!
        # The closest point is (1.0, 0.0, 5.0), with distance = 5.0.
        # The flawed scaled projection gave (0.5, 0.0, 5.0) with distance = sqrt(0.25 + 25) = 5.0249 > 5.0.
        self.assertAlmostEqual(F_proj[0], 1.0, places=6)
        self.assertAlmostEqual(F_proj[1], 0.0, places=6)
        self.assertAlmostEqual(F_proj[2], 5.0, places=6)

        dist_optimal = math.sqrt((F[0] - F_proj[0])**2 + (F[1] - F_proj[1])**2 + (F[2] - F_proj[2])**2)
        dist_flawed = math.sqrt((1.0 - 0.5)**2 + 0.0 + (10.0 - 5.0)**2)
        self.assertAlmostEqual(dist_optimal, 5.0, places=6)
        self.assertLess(dist_optimal, dist_flawed)

    # -------------------------------------------------------------------------
    # Test 19: Bounded Friction Cone Interior Point Invariant
    # -------------------------------------------------------------------------
    def test_19_bounded_friction_cone_interior_point_invariant(self):
        """Test 19: Points strictly inside bounded cone are unchanged by projection."""
        normal = (0.0, 0.0, 1.0)
        mu = 0.6
        min_fn = 1.0
        max_fn = 10.0

        # Interior point: Fn = 4.0 in [1.0, 10.0], Ft = sqrt(0.5^2 + 0.3^2) = 0.583 <= 0.6 * 4.0 = 2.4
        F_in = (0.5, 0.3, 4.0)
        F_proj = project_to_friction_cone(F_in, normal, mu, min_fn, max_fn)

        self.assertAlmostEqual(F_proj[0], F_in[0], places=7)
        self.assertAlmostEqual(F_proj[1], F_in[1], places=7)
        self.assertAlmostEqual(F_proj[2], F_in[2], places=7)

    # -------------------------------------------------------------------------
    # Test 20: Finite Normal Upper and Lower Bounds
    # -------------------------------------------------------------------------
    def test_20_bounded_friction_cone_finite_bounds(self):
        """Test 20: Clamping with finite min_normal_force > 0 and finite max_normal_force."""
        normal = (0.0, 0.0, 1.0)
        mu = 0.5
        min_fn = 2.0
        max_fn = 8.0

        # Below lower bound: Fn = 0.5 < 2.0, Ft = 0.2 <= mu * min_fn
        F_low = (0.2, 0.0, 0.5)
        P_low = project_to_friction_cone(F_low, normal, mu, min_fn, max_fn)
        self.assertAlmostEqual(P_low[0], 0.2, places=6)
        self.assertAlmostEqual(P_low[1], 0.0, places=6)
        self.assertAlmostEqual(P_low[2], 2.0, places=6)

        # Above upper bound: Fn = 15.0 > 8.0, Ft = 1.0 <= mu * max_fn (4.0)
        F_high = (1.0, 0.0, 15.0)
        P_high = project_to_friction_cone(F_high, normal, mu, min_fn, max_fn)
        self.assertAlmostEqual(P_high[0], 1.0, places=6)
        self.assertAlmostEqual(P_high[1], 0.0, places=6)
        self.assertAlmostEqual(P_high[2], 8.0, places=6)

    # -------------------------------------------------------------------------
    # Test 21: Zero Friction Coeff (mu == 0)
    # -------------------------------------------------------------------------
    def test_21_bounded_friction_cone_zero_friction(self):
        """Test 21: mu=0 strictly projects to normal axis [min_fn, max_fn] eliminating all tangential force."""
        normal = (0.0, 0.0, 1.0)
        mu = 0.0
        min_fn = 0.0
        max_fn = 10.0

        F = (5.0, -3.0, 4.0)
        P = project_to_friction_cone(F, normal, mu, min_fn, max_fn)
        self.assertAlmostEqual(P[0], 0.0, places=7)
        self.assertAlmostEqual(P[1], 0.0, places=7)
        self.assertAlmostEqual(P[2], 4.0, places=7)

    # -------------------------------------------------------------------------
    # Test 22: Projection Idempotency
    # -------------------------------------------------------------------------
    def test_22_bounded_friction_cone_idempotency(self):
        """Test 22: Projection operator is idempotent: P(P(F)) == P(F) for diverse forces."""
        normal = vec3_normalize((0.2, -0.3, 0.9))
        mu = 0.45
        min_fn = 0.5
        max_fn = 12.0

        test_vectors = [
            (10.0, -20.0, 30.0),
            (-50.0, 10.0, -5.0),
            (0.0, 0.0, 0.0),
            (0.1, -0.1, 2.0),
            (100.0, 100.0, 100.0),
        ]
        for F in test_vectors:
            P1 = project_to_friction_cone(F, normal, mu, min_fn, max_fn)
            P2 = project_to_friction_cone(P1, normal, mu, min_fn, max_fn)
            for k in range(3):
                self.assertAlmostEqual(P1[k], P2[k], places=7)

    # -------------------------------------------------------------------------
    # Test 23: Post-Projection Constraint Feasibility
    # -------------------------------------------------------------------------
    def test_23_bounded_friction_cone_feasibility(self):
        """Test 23: Every projected force strictly satisfies normal bounds and circular friction cone."""
        normal = vec3_normalize((-0.5, 0.2, 0.8))
        mu = 0.55
        min_fn = 1.0
        max_fn = 7.5

        test_vectors = [
            (25.0, 15.0, 4.0),
            (-10.0, -10.0, -10.0),
            (0.0, 0.0, 0.0),
            (3.0, 4.0, 20.0),
        ]
        for F in test_vectors:
            P = project_to_friction_cone(F, normal, mu, min_fn, max_fn)
            fn = vec3_dot(P, normal)
            ft_vec = vec3_sub(P, vec3_scale(normal, fn))
            ft = vec3_length(ft_vec)

            self.assertGreaterEqual(fn, min_fn - 1e-6)
            self.assertLessEqual(fn, max_fn + 1e-6)
            self.assertLessEqual(ft, mu * fn + 1e-6)

    # -------------------------------------------------------------------------
    # Test 24: Projection Closest-Point Optimality Verification
    # -------------------------------------------------------------------------
    def test_24_bounded_friction_cone_closest_point_property(self):
        """Test 24: P(F) achieves strictly minimal Euclidean distance compared to neighboring feasible points."""
        normal = (0.0, 0.0, 1.0)
        mu = 0.5
        min_fn = 0.0
        max_fn = 5.0
        F = (1.0, 0.0, 10.0)

        P = project_to_friction_cone(F, normal, mu, min_fn, max_fn)
        dist_P = vec3_length(vec3_sub(P, F))

        # Sample local feasible perturbations around P in K
        epsilons = [-0.1, 0.0, 0.1]
        for dfx in epsilons:
            for dfy in epsilons:
                for dfz in [-0.2, -0.1, 0.0]:
                    y = (P[0] + dfx, P[1] + dfy, P[2] + dfz)
                    y_fn = y[2]
                    y_ft = math.sqrt(y[0]**2 + y[1]**2)
                    if min_fn <= y_fn <= max_fn and y_ft <= mu * y_fn:
                        dist_y = vec3_length(vec3_sub(y, F))
                        self.assertGreaterEqual(dist_y, dist_P - 1e-9)

    # -------------------------------------------------------------------------
    # Test 25: SPG Max Iterations and Convergence Status Handling
    # -------------------------------------------------------------------------
    def test_25_spg_max_iterations_handling(self):
        """Test 25: SPG with tiny max_iterations terminates with APPROXIMATE, reports iter count, not SOLVED."""
        com = (0.0, 0.0, 1.0)
        foot = ContactConstraintSpec("foot", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.65)
        target = ContactWrenchTarget(
            target_force_world=(100.0, 50.0, 600.0),
            target_torque_world=(10.0, -15.0, 0.0),
            com_world=com,
        )
        config = ContactSolverConfig(max_iterations=2, method="spg")
        sol = solve_contact_forces(target, [foot], config)

        self.assertEqual(sol.solver_engine, "spg")
        self.assertEqual(sol.iterations, 2)
        self.assertFalse(sol.optimizer_converged)
        self.assertEqual(sol.status, ContactSolverStatus.APPROXIMATE)
        self.assertIn("reached maximum iteration limit", sol.optimizer_message)

    # -------------------------------------------------------------------------
    # Test 26: SLSQP Optimizer Termination and Diagnostics
    # -------------------------------------------------------------------------
    def test_26_slsqp_optimizer_termination_and_diagnostics(self):
        """Test 26: SLSQP propagates termination status, message, and iteration diagnostics."""
        if not HAVE_SCIPY:
            self.skipTest("SciPy not installed in this environment")

        com = (0.0, 0.0, 1.0)
        foot_L = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        foot_R = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        target = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 686.7),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        config = ContactSolverConfig(method="slsqp", max_iterations=100)
        sol = solve_contact_forces(target, [foot_L, foot_R], config)

        self.assertEqual(sol.solver_engine, "slsqp")
        self.assertTrue(sol.optimizer_converged)
        self.assertGreater(sol.iterations, 0)
        self.assertEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertFalse(sol.fallback_occurred)

    # -------------------------------------------------------------------------
    # Test 27: Optimizer Fallback Reporting
    # -------------------------------------------------------------------------
    def test_27_optimizer_fallback_reporting(self):
        """Test 27: Fallback from SLSQP exception to SPG explicitly records fallback_occurred and engine."""
        com = (0.0, 0.0, 1.0)
        foot = ContactConstraintSpec("foot", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        target = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 500.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )

        import src.motion.contact_force_solver as cfs
        orig_slsqp = cfs._solve_with_slsqp

        def mock_failing_slsqp(*args, **kwargs):
            raise RuntimeError("Mock SLSQP internal optimizer failure")

        try:
            cfs._solve_with_slsqp = mock_failing_slsqp
            config = ContactSolverConfig(method="slsqp")
            sol = solve_contact_forces(target, [foot], config)

            self.assertTrue(sol.fallback_occurred)
            self.assertEqual(sol.solver_engine, "spg")
            self.assertIn("Fallback from SLSQP", sol.optimizer_message)
            self.assertTrue(sol.is_physically_valid)
        finally:
            cfs._solve_with_slsqp = orig_slsqp

    # -------------------------------------------------------------------------
    # Test 28: Numerical Failure Cannot Falsely Report SOLVED
    # -------------------------------------------------------------------------
    def test_28_numerical_failure_cannot_falsely_report_solved(self):
        """Test 28: Physical constraint violation or numerical exception is strictly NUMERICAL_FAILURE."""
        com = (0.0, 0.0, 1.0)
        # Separated contact
        foot_sep = ContactConstraintSpec(
            "foot_sep", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.7, is_in_contact=False
        )
        target = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 500.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol = solve_contact_forces(target, [foot_sep])
        self.assertNotEqual(sol.status, ContactSolverStatus.SOLVED)
        self.assertEqual(sol.status, ContactSolverStatus.INFEASIBLE)

    # -------------------------------------------------------------------------
    # Test 29: High-Friction Slope Feasibility Counterexample
    # -------------------------------------------------------------------------
    def test_29_high_friction_slope_feasibility_counterexample(self):
        """Test 29: Inclined slope (n_z > 0.5) with high friction can produce downward force (not INFEASIBLE a priori)."""
        # Slope with normal inclined at 30 deg from vertical: normal = (0.0, 0.5, 0.866)
        # Tangent downhill vector: (0.0, 0.866, -0.5).
        # High friction mu = 2.0.
        # When pushing against the slope downhill: F = 100 * n - 150 * t
        # F_z = 100 * 0.866 - 150 * (-0.5) ... wait, tangent has negative z!
        # Pushing into the wall/slope: F_n = 100 N > 0.
        # Downhill friction: F_t = 120 N * (0, 0.866, -0.5).
        # Net F_z = 100 * 0.866 + 120 * (-0.5) = 86.6 - 60 = 26.6 N.
        # If F_t is even larger: 100 * 0.866 + 180 * (-0.5) = 86.6 - 90 = -3.4 N (downward!)
        # Here mu = 2.0 allows F_t up to 200 N. Thus negative F_z is physically feasible!
        normal = (0.0, 0.5, 0.866025)
        com = (0.0, 0.0, 1.0)
        slope_contact = ContactConstraintSpec("slope", (0.0, 1.0, 0.5), normal, friction_coeff=2.0)

        # Target has negative F_z = -5.0 N
        target = ContactWrenchTarget(
            target_force_world=(0.0, 150.0, -5.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        # Previous flawed logic had all(n_z > 0.5) -> INFEASIBLE.
        # Now it must NOT be a priori rejected as INFEASIBLE.
        sol = solve_contact_forces(target, [slope_contact])
        self.assertNotEqual(sol.status, ContactSolverStatus.INFEASIBLE)
        self.assertTrue(sol.is_physically_valid)

    # -------------------------------------------------------------------------
    # Test 30: Known Provably Infeasible Targets Strictness
    # -------------------------------------------------------------------------
    def test_30_known_infeasible_targets_strictness(self):
        """Test 30: True provable infeasibilities (zero contacts, flat ground tensile pull) are INFEASIBLE."""
        com = (0.0, 0.0, 1.0)
        # Case A: Zero active contacts with non-zero force
        target_f = ContactWrenchTarget(
            target_force_world=(10.0, 0.0, 0.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_a = solve_contact_forces(target_f, [])
        self.assertEqual(sol_a.status, ContactSolverStatus.INFEASIBLE)

        # Case B: Strictly horizontal ground (n = [0, 0, 1]) with downward pull
        ground = ContactConstraintSpec("ground", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.7)
        target_down = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, -100.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=com,
        )
        sol_b = solve_contact_forces(target_down, [ground])
        self.assertEqual(sol_b.status, ContactSolverStatus.INFEASIBLE)

    # -------------------------------------------------------------------------
    # Test 31: Contact Geometry Distance Fidelity
    # -------------------------------------------------------------------------
    def test_31_contact_geometry_distance_fidelity(self):
        """Test 31: ContactConstraintSpec and MultiContactDynamics preserve true surface_distance without fakes."""
        from src.scene.environment_query import create_standard_dynamics_playground_query
        env_query = create_standard_dynamics_playground_query()

        # Query point with true clearance gap of 10mm (0.010m) above ground
        pt = (0.0, 0.0, 0.010)
        spec = create_contact_constraint_from_environment(
            env_query=env_query,
            contact_point_world=pt,
            contact_id="test_foot",
            contact_tolerance=0.02,
        )
        self.assertTrue(spec.is_in_contact)
        self.assertIsNotNone(spec.surface_distance)
        self.assertAlmostEqual(spec.surface_distance, 0.010, places=4)
        self.assertEqual(spec.surface_id, "default_ground")

        # Solve and bridge to MultiContactDynamics
        target = ContactWrenchTarget((0, 0, 500), (0, 0, 0), (0, 0, 1))
        sol = solve_contact_forces(target, [spec])
        multi = solution_to_multi_contact_dynamics(sol, [spec], (0, 0, 1))

        self.assertEqual(len(multi.contacts), 1)
        single = multi.contacts[0]
        # Must retain true 0.010m clearance, NOT fabricated 0.0 or 0.05
        self.assertAlmostEqual(single.surface_distance, 0.010, places=4)
        self.assertEqual(single.surface_id, "default_ground")

        # Manual spec with unknown distance (surface_distance=None)
        manual_spec = ContactConstraintSpec("manual", (0, 0, 0), (0, 0, 1), 0.7, surface_distance=None)
        multi_manual = solution_to_multi_contact_dynamics(sol, [manual_spec], (0, 0, 1))
        self.assertIsNone(multi_manual.contacts[0].surface_distance)


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv)
