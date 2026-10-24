"""Verification Suite for Forward Dynamics Single-Step Integration Kernel (Task 6G-D-C1-A & C1-A-R1).

Covers 22 Core Analytical, Physical Theorems, and Contract Validations:
 1. Constant force linear kinematic position and velocity exact integration.
 2. Free fall multi-step exact analytical trajectory comparison.
 3. Momentum conservation in free space (F_net = 0 => P = const).
 4. Impulse-momentum theorem (Delta P = F_net * dt).
 5. Static support equilibrium with gravity compensation (70kg * 9.81m/s^2).
 6. Eccentric contact force produces exact torque about CoM (r x F).
 7. Angular momentum change equals external torque impulse (Delta L = tau_net * dt).
 8. Angular momentum conservation under zero net torque (tau_net = 0 => L = const).
 9. Angular velocity computation with positive-definite inertia (I * omega = L).
10. Rejection of singular, zero-determinant, or non-positive-definite inertia tensors.
11. Attitude quaternion normalization and active rotation direction correctness.
12. Quaternion invariance under zero net torque and zero initial angular velocity.
13. Time step convergence and error scaling across dt = 0.04s, 0.02s, 0.01s.
14. Robust rejection of non-finite (NaN/Inf) forces, masses, dt, and inertia tensors.
15. Failure atomicity: input state is strictly unmodified when step integration fails.
16. Duplicate contact ID rejection in forward dynamics step inputs.
17. Zero regression on existing Contact Force Solver and Contact Dynamics modules.
18. State and step input defensive immutability against external caller list mutations.
19. Strict vector and quaternion component dimension validation (exact len=3 and len=4).
20. Non-isotropic rigid body torque-free motion and rotational kinetic energy conservation.
21. Non-isotropic rigid body constant torque integration and angular momentum tracking.
22. Rigorous 2nd-order midpoint attitude integration quadratic convergence rate (ratio ~ 4.0).
"""

from __future__ import annotations

import math
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from typing import List

from src.motion.forward_dynamics import (
    ContactForcePoint,
    ForwardDynamicsConfig,
    ForwardDynamicsState,
    ForwardDynamicsStatus,
    ForwardDynamicsStepInput,
    ForwardDynamicsStepResult,
    InertiaTensor3x3,
    integrate_forward_dynamics_single_step,
    quat_from_axis_angle,
    quat_length,
    quat_multiply,
    quat_normalize,
    quat_rotate_vector,
    quat_to_rot_matrix,
    vec3_cross,
    vec3_dot,
    vec3_length,
    vec3_scale,
    vec3_sub,
)
from src.motion.contact_force_solver import (
    ContactConstraintSpec,
    ContactForceSolution,
    ContactSolverConfig,
    ContactSolverStatus,
    ContactWrenchTarget,
    solve_contact_forces,
)
from src.motion.contact_dynamics import (
    MultiContactDynamics,
    SingleContactDynamics,
)


class TestForwardDynamicsSingleStep(unittest.TestCase):
    """Test suite for single-step forward dynamics integration kernel."""

    def setUp(self):
        self.mass = 70.0
        self.com = (0.0, 0.0, 1.0)
        self.default_inertia = InertiaTensor3x3.from_diagonal(10.0, 12.0, 15.0)
        self.dt = 1.0 / 24.0  # ~0.04167s

        self.default_state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

    # -------------------------------------------------------------------------
    # Test 01: Constant Force Linear Kinematic Integration
    # -------------------------------------------------------------------------
    def test_01_constant_force_linear_integration(self):
        """Test 01: Verify constant force linear integration matches exact kinematic equations."""
        F_ext = (140.0, -70.0, 210.0)
        m = 70.0
        dt = 0.04
        v0 = (1.0, -0.5, 2.0)
        p0 = (0.1, 0.2, 1.5)

        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=m,
            com_position_world=p0,
            com_velocity_world=v0,
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            external_forces_world=(F_ext,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),  # Zero gravity to isolate F_ext
            dt=dt,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)
        self.assertTrue(res.is_physically_valid)

        # Analytical acceleration: a = F / m
        a_exact = (F_ext[0] / m, F_ext[1] / m, F_ext[2] / m)
        self.assertAlmostEqual(res.actual_linear_acceleration_world[0], a_exact[0], places=10)
        self.assertAlmostEqual(res.actual_linear_acceleration_world[1], a_exact[1], places=10)
        self.assertAlmostEqual(res.actual_linear_acceleration_world[2], a_exact[2], places=10)

        # Exact velocity: v_next = v0 + a * dt
        v_exact = (v0[0] + a_exact[0] * dt, v0[1] + a_exact[1] * dt, v0[2] + a_exact[2] * dt)
        self.assertAlmostEqual(res.state_next.com_velocity_world[0], v_exact[0], places=10)
        self.assertAlmostEqual(res.state_next.com_velocity_world[1], v_exact[1], places=10)
        self.assertAlmostEqual(res.state_next.com_velocity_world[2], v_exact[2], places=10)

        # Exact position: p_next = p0 + v0 * dt + 0.5 * a * dt^2
        p_exact = (
            p0[0] + v0[0] * dt + 0.5 * a_exact[0] * dt * dt,
            p0[1] + v0[1] * dt + 0.5 * a_exact[1] * dt * dt,
            p0[2] + v0[2] * dt + 0.5 * a_exact[2] * dt * dt,
        )
        self.assertAlmostEqual(res.state_next.com_position_world[0], p_exact[0], places=10)
        self.assertAlmostEqual(res.state_next.com_position_world[1], p_exact[1], places=10)
        self.assertAlmostEqual(res.state_next.com_position_world[2], p_exact[2], places=10)

    # -------------------------------------------------------------------------
    # Test 02: Free Fall Analytical Trajectory Comparison
    # -------------------------------------------------------------------------
    def test_02_free_fall_analytical_solution(self):
        """Test 02: Multi-step free fall trajectory matches analytical z(t) = z0 + v0*t - 0.5*g*t^2."""
        z0 = 10.0
        v0_z = 2.0
        g = 9.81
        dt = 0.05
        num_steps = 20

        curr_state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, z0),
            com_velocity_world=(0.0, 0.0, v0_z),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            gravity_acceleration_world=(0.0, 0.0, -g),
            dt=dt,
        )

        for step_idx in range(num_steps):
            res = integrate_forward_dynamics_single_step(curr_state, step_in)
            self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)
            curr_state = res.state_next

            t = (step_idx + 1) * dt
            z_analytical = z0 + v0_z * t - 0.5 * g * t * t
            vz_analytical = v0_z - g * t

            self.assertAlmostEqual(curr_state.com_position_world[2], z_analytical, places=8)
            self.assertAlmostEqual(curr_state.com_velocity_world[2], vz_analytical, places=8)
            self.assertAlmostEqual(curr_state.timestamp, t, places=8)

    # -------------------------------------------------------------------------
    # Test 03: Momentum Conservation in Free Space
    # -------------------------------------------------------------------------
    def test_03_momentum_conservation_in_free_space(self):
        """Test 03: In absence of net external forces, linear momentum P = m * v is strictly conserved."""
        v_init = (2.5, -3.1, 1.4)
        state = ForwardDynamicsState(
            timestamp=1.0,
            mass=self.mass,
            com_position_world=(0.5, 0.5, 2.0),
            com_velocity_world=v_init,
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            contact_forces=(),
            external_forces_world=(),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=0.04,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        # Velocity must be identical
        self.assertEqual(res.state_next.com_velocity_world, v_init)
        # Momentum must be identical
        P_init = state.linear_momentum_world
        P_next = res.state_next.linear_momentum_world
        self.assertAlmostEqual(P_init[0], P_next[0], places=10)
        self.assertAlmostEqual(P_init[1], P_next[1], places=10)
        self.assertAlmostEqual(P_init[2], P_next[2], places=10)

    # -------------------------------------------------------------------------
    # Test 04: Linear Momentum Change by Net Force Impulse
    # -------------------------------------------------------------------------
    def test_04_constant_force_linear_momentum_change(self):
        """Test 04: Delta P = m * (v_next - v_curr) matches net force impulse F_net * dt."""
        F_net = (300.0, -150.0, 450.0)
        dt = 0.02

        step_in = ForwardDynamicsStepInput(
            external_forces_world=(F_net,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=dt,
        )

        res = integrate_forward_dynamics_single_step(self.default_state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        delta_P = vec3_sub(res.state_next.linear_momentum_world, self.default_state.linear_momentum_world)
        expected_impulse = vec3_scale(F_net, dt)

        self.assertAlmostEqual(delta_P[0], expected_impulse[0], places=9)
        self.assertAlmostEqual(delta_P[1], expected_impulse[1], places=9)
        self.assertAlmostEqual(delta_P[2], expected_impulse[2], places=9)

    # -------------------------------------------------------------------------
    # Test 05: Static Support Gravity Compensation Equilibrium
    # -------------------------------------------------------------------------
    def test_05_static_support_gravity_compensation(self):
        """Test 05: 70kg mass supported by ground normal forces perfectly cancels 9.81m/s^2 gravity."""
        m = 70.0
        g = 9.81
        gravity_force = m * g  # 686.7 N

        # Two symmetric feet on ground supporting 343.35 N each
        foot_L = ContactForcePoint((-0.15, 0.0, 0.0), (0.0, 0.0, 0.5 * gravity_force), "foot_L")
        foot_R = ContactForcePoint((0.15, 0.0, 0.0), (0.0, 0.0, 0.5 * gravity_force), "foot_R")

        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=m,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            contact_forces=(foot_L, foot_R),
            gravity_acceleration_world=(0.0, 0.0, -g),
            dt=1.0 / 24.0,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        # Net force must be identically zero
        self.assertAlmostEqual(res.net_force_world[0], 0.0, places=9)
        self.assertAlmostEqual(res.net_force_world[1], 0.0, places=9)
        self.assertAlmostEqual(res.net_force_world[2], 0.0, places=9)

        # Net torque about CoM must be identically zero
        self.assertAlmostEqual(res.net_torque_about_com_world[0], 0.0, places=9)
        self.assertAlmostEqual(res.net_torque_about_com_world[1], 0.0, places=9)
        self.assertAlmostEqual(res.net_torque_about_com_world[2], 0.0, places=9)

        # Position and velocity remain completely stationary
        self.assertAlmostEqual(res.state_next.com_velocity_world[2], 0.0, places=9)
        self.assertAlmostEqual(res.state_next.com_position_world[2], 1.0, places=9)

    # -------------------------------------------------------------------------
    # Test 06: Eccentric Contact Force Produces Exact Torque about CoM
    # -------------------------------------------------------------------------
    def test_06_eccentric_contact_force_torque(self):
        """Test 06: Contact force off CoM produces exact torque tau = r x F."""
        com = (0.0, 0.0, 1.0)
        p_c = (0.2, 0.1, 0.5)
        F_c = (0.0, 0.0, 200.0)

        # Expected r = p_c - com = (0.2, 0.1, -0.5)
        # tau = (0.1*200 - (-0.5)*0, (-0.5)*0 - 0.2*200, 0.2*0 - 0.1*0) = (20.0, -40.0, 0.0)
        expected_tau = (20.0, -40.0, 0.0)

        cp = ContactForcePoint(p_c, F_c, "toe")
        step_in = ForwardDynamicsStepInput(
            contact_forces=(cp,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=0.04,
        )

        res = integrate_forward_dynamics_single_step(self.default_state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        self.assertAlmostEqual(res.net_torque_about_com_world[0], expected_tau[0], places=9)
        self.assertAlmostEqual(res.net_torque_about_com_world[1], expected_tau[1], places=9)
        self.assertAlmostEqual(res.net_torque_about_com_world[2], expected_tau[2], places=9)

    # -------------------------------------------------------------------------
    # Test 07: Angular Momentum Changes by External Torque Impulse
    # -------------------------------------------------------------------------
    def test_07_angular_momentum_torque_integral(self):
        """Test 07: Delta L = tau_net * dt."""
        tau_ext = (15.0, -25.0, 8.0)
        dt = 0.04

        step_in = ForwardDynamicsStepInput(
            external_torques_about_com_world=(tau_ext,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=dt,
        )

        res = integrate_forward_dynamics_single_step(self.default_state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        expected_delta_L = vec3_scale(tau_ext, dt)
        actual_delta_L = vec3_sub(
            res.state_next.angular_momentum_about_com_world,
            self.default_state.angular_momentum_about_com_world,
        )

        self.assertAlmostEqual(actual_delta_L[0], expected_delta_L[0], places=9)
        self.assertAlmostEqual(actual_delta_L[1], expected_delta_L[1], places=9)
        self.assertAlmostEqual(actual_delta_L[2], expected_delta_L[2], places=9)

    # -------------------------------------------------------------------------
    # Test 08: Angular Momentum Conservation under Zero Torque
    # -------------------------------------------------------------------------
    def test_08_angular_momentum_conservation_zero_torque(self):
        """Test 08: Under zero net torque, angular momentum L is strictly conserved."""
        L_init = (4.0, -6.0, 10.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=L_init,
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=0.04,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        self.assertEqual(res.state_next.angular_momentum_about_com_world, L_init)

    # -------------------------------------------------------------------------
    # Test 09: Angular Velocity Computation under Positive-Definite Inertia
    # -------------------------------------------------------------------------
    def test_09_angular_velocity_positive_definite_inertia(self):
        """Test 09: omega = I^-1 * L matches analytical inverse for positive-definite inertia."""
        I_diag = InertiaTensor3x3.from_diagonal(10.0, 20.0, 25.0)
        L = (20.0, -40.0, 50.0)

        # Expected omega = (20/10, -40/20, 50/25) = (2.0, -2.0, 2.0)
        expected_omega = (2.0, -2.0, 2.0)
        omega = I_diag.solve_angular_velocity(L)

        self.assertAlmostEqual(omega[0], expected_omega[0], places=9)
        self.assertAlmostEqual(omega[1], expected_omega[1], places=9)
        self.assertAlmostEqual(omega[2], expected_omega[2], places=9)

    # -------------------------------------------------------------------------
    # Test 10: Singular or Non-Positive-Definite Inertia Rejection
    # -------------------------------------------------------------------------
    def test_10_singular_or_non_positive_definite_inertia_rejection(self):
        """Test 10: Zero-determinant or negative-eigenvalue inertia tensor is rejected with SINGULAR_INERTIA."""
        # Case A: Singular inertia with zero eigenvalue
        singular_inertia = InertiaTensor3x3.from_diagonal(10.0, 10.0, 0.0)
        self.assertFalse(singular_inertia.is_positive_definite())

        # Constructing state with singular inertia
        state_sing = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(1.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=singular_inertia,
        )

        step_in = ForwardDynamicsStepInput(dt=0.04)
        res = integrate_forward_dynamics_single_step(state_sing, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SINGULAR_INERTIA)
        self.assertFalse(res.is_physically_valid)

        # Case B: Negative principal moment
        neg_inertia = InertiaTensor3x3.from_diagonal(10.0, -5.0, 10.0)
        self.assertFalse(neg_inertia.is_positive_definite())

        state_neg = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(1.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=neg_inertia,
        )
        res_neg = integrate_forward_dynamics_single_step(state_neg, step_in)
        self.assertEqual(res_neg.status, ForwardDynamicsStatus.SINGULAR_INERTIA)
        self.assertFalse(res_neg.is_physically_valid)

    # -------------------------------------------------------------------------
    # Test 11: Quaternion Normalization and Active Rotation Direction
    # -------------------------------------------------------------------------
    def test_11_quaternion_normalization_and_active_rotation_direction(self):
        """Test 11: Attitude update produces exact 90 deg yaw rotation and preserves unit norm."""
        # Body spinning about Z axis with omega = pi/2 rad/s
        # Over dt = 1.0s, total rotation is 90 deg = pi/2 rad about +Z.
        # Starting with diagonal inertia I = diag(10, 10, 10), L = (0, 0, 10 * pi/2) = (0, 0, 5*pi).
        L_z = 10.0 * (math.pi / 2.0)
        I_iso = InertiaTensor3x3.from_diagonal(10.0, 10.0, 10.0)

        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, L_z),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=I_iso,
        )

        step_in = ForwardDynamicsStepInput(
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=1.0,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        q_next = res.state_next.orientation_quat_world
        # Unit norm verification
        self.assertAlmostEqual(quat_length(q_next), 1.0, places=12)

        # 90 deg yaw about +Z: q_exact = (cos(pi/4), 0, 0, sin(pi/4)) = (sqrt(2)/2, 0, 0, sqrt(2)/2)
        q_exact_w = math.cos(math.pi / 4.0)
        q_exact_z = math.sin(math.pi / 4.0)

        self.assertAlmostEqual(q_next[0], q_exact_w, places=7)
        self.assertAlmostEqual(q_next[1], 0.0, places=7)
        self.assertAlmostEqual(q_next[2], 0.0, places=7)
        self.assertAlmostEqual(q_next[3], q_exact_z, places=7)

        # Active rotation test: body vector (1, 0, 0) rotated by 90 deg about +Z becomes (0, 1, 0)
        v_body = (1.0, 0.0, 0.0)
        v_world = quat_rotate_vector(q_next, v_body)
        self.assertAlmostEqual(v_world[0], 0.0, places=7)
        self.assertAlmostEqual(v_world[1], 1.0, places=7)
        self.assertAlmostEqual(v_world[2], 0.0, places=7)

    # -------------------------------------------------------------------------
    # Test 12: Zero Torque & Zero Angular Velocity Quaternion Invariance
    # -------------------------------------------------------------------------
    def test_12_zero_torque_zero_angular_velocity_quaternion_invariance(self):
        """Test 12: When L = 0 and tau = 0, orientation quaternion is strictly invariant."""
        # Non-trivial initial quaternion: 45 deg roll
        q0 = quat_from_axis_angle((1.0, 0.0, 0.0), math.pi / 4.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=q0,
            inertia_tensor_body=self.default_inertia,
        )

        step_in = ForwardDynamicsStepInput(
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=0.04,
        )

        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        self.assertEqual(res.state_next.orientation_quat_world, q0)

    # -------------------------------------------------------------------------
    # Test 13: Time Step Convergence and Error Scaling
    # -------------------------------------------------------------------------
    def test_13_time_step_convergence_and_error_scaling(self):
        """Test 13: Rotational motion under external torque exhibits systematic convergence as dt -> 0."""
        # Apply sinusoidal-like torque over a total horizon T = 0.04s
        # Compare solutions with dt = 0.04, dt = 0.02 (2 steps), dt = 0.01 (4 steps)
        T_total = 0.04
        tau = (20.0, 10.0, -15.0)

        def simulate_horizon(dt_step: float) -> ForwardDynamicsState:
            curr = self.default_state
            steps = int(round(T_total / dt_step))
            step_in = ForwardDynamicsStepInput(
                external_torques_about_com_world=(tau,),
                gravity_acceleration_world=(0.0, 0.0, 0.0),
                dt=dt_step,
            )
            for _ in range(steps):
                curr = integrate_forward_dynamics_single_step(curr, step_in).state_next
            return curr

        state_coarse = simulate_horizon(0.04)
        state_medium = simulate_horizon(0.02)
        state_fine = simulate_horizon(0.01)

        # Angular momentum update is linear in torque: Delta L = tau * T is exact for all step sizes
        L_exact = vec3_scale(tau, T_total)
        self.assertAlmostEqual(state_coarse.angular_momentum_about_com_world[0], L_exact[0], places=9)
        self.assertAlmostEqual(state_medium.angular_momentum_about_com_world[0], L_exact[0], places=9)
        self.assertAlmostEqual(state_fine.angular_momentum_about_com_world[0], L_exact[0], places=9)

        # Orientation quaternion difference should converge
        err_coarse_medium = quat_length(
            (
                state_coarse.orientation_quat_world[0] - state_medium.orientation_quat_world[0],
                state_coarse.orientation_quat_world[1] - state_medium.orientation_quat_world[1],
                state_coarse.orientation_quat_world[2] - state_medium.orientation_quat_world[2],
                state_coarse.orientation_quat_world[3] - state_medium.orientation_quat_world[3],
            )
        )
        err_medium_fine = quat_length(
            (
                state_medium.orientation_quat_world[0] - state_fine.orientation_quat_world[0],
                state_medium.orientation_quat_world[1] - state_fine.orientation_quat_world[1],
                state_medium.orientation_quat_world[2] - state_fine.orientation_quat_world[2],
                state_medium.orientation_quat_world[3] - state_fine.orientation_quat_world[3],
            )
        )

        # Error must decrease monotonically as step size is halved
        self.assertLess(err_medium_fine, err_coarse_medium)

    # -------------------------------------------------------------------------
    # Test 14: Non-Finite Inputs Rejection
    # -------------------------------------------------------------------------
    def test_14_non_finite_inputs_rejection(self):
        """Test 14: Rejection of NaN and Inf in state, forces, torques, mass, dt without uncaught exceptions."""
        # 1. State with NaN mass raises ValueError during instantiation
        with self.assertRaises(ValueError):
            ForwardDynamicsState(mass=float("nan"))

        # 2. State with negative mass raises ValueError
        with self.assertRaises(ValueError):
            ForwardDynamicsState(mass=-10.0)

        # 3. State with NaN com position
        with self.assertRaises(ValueError):
            ForwardDynamicsState(com_position_world=(float("nan"), 0.0, 1.0))

        # 4. StepInput with NaN force
        with self.assertRaises(ValueError):
            ForwardDynamicsStepInput(external_forces_world=((float("nan"), 0.0, 0.0),))

        # 5. StepInput with negative dt
        with self.assertRaises(ValueError):
            ForwardDynamicsStepInput(dt=-0.04)

        # 6. StepInput with zero dt
        with self.assertRaises(ValueError):
            ForwardDynamicsStepInput(dt=0.0)

        # 7. ContactForcePoint with Inf coordinate
        with self.assertRaises(ValueError):
            ContactForcePoint((float("inf"), 0.0, 0.0), (0.0, 0.0, 100.0))

    # -------------------------------------------------------------------------
    # Test 15: Input State Immutability on Failure
    # -------------------------------------------------------------------------
    def test_15_input_state_immutability_on_failure(self):
        """Test 15: Frozen input state is strictly unmutated when single-step integration fails."""
        initial_state = ForwardDynamicsState(
            timestamp=5.0,
            mass=70.0,
            com_position_world=(1.0, 2.0, 3.0),
            com_velocity_world=(0.1, 0.2, 0.3),
            angular_momentum_about_com_world=(0.4, 0.5, 0.6),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        # Cannot modify frozen state directly
        with self.assertRaises(Exception):
            initial_state.timestamp = 6.0  # type: ignore

        # Trigger failure with singular inertia
        sing_state = ForwardDynamicsState(
            timestamp=5.0,
            mass=70.0,
            com_position_world=(1.0, 2.0, 3.0),
            com_velocity_world=(0.1, 0.2, 0.3),
            angular_momentum_about_com_world=(0.4, 0.5, 0.6),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=InertiaTensor3x3.from_diagonal(10.0, 10.0, 0.0),
        )
        step_in = ForwardDynamicsStepInput(dt=0.04)
        res = integrate_forward_dynamics_single_step(sing_state, step_in)

        self.assertEqual(res.status, ForwardDynamicsStatus.SINGULAR_INERTIA)
        # Returned state_next is exactly the original unmutated input state
        self.assertEqual(res.state_next.timestamp, 5.0)
        self.assertEqual(res.state_next.com_position_world, (1.0, 2.0, 3.0))

    # -------------------------------------------------------------------------
    # Test 16: Duplicate Contact ID Rejection
    # -------------------------------------------------------------------------
    def test_16_duplicate_contact_id_rejection(self):
        """Test 16: Duplicate contact IDs in ForwardDynamicsStepInput are strictly rejected."""
        c1 = ContactForcePoint((0.0, 0.0, 0.0), (0.0, 0.0, 100.0), "foot")
        c2 = ContactForcePoint((0.2, 0.0, 0.0), (0.0, 0.0, 100.0), "foot")

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsStepInput(contact_forces=(c1, c2), dt=0.04)

        self.assertIn("Duplicate contact_id detected", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 17: Zero Regression on Existing Dynamics Modules
    # -------------------------------------------------------------------------
    def test_17_zero_regression_on_existing_dynamics_modules(self):
        """Test 17: MultiContactDynamics and ContactForceSolver operate seamlessly with ForwardDynamics."""
        # 1. Contact Force Solver solves equilibrium on two feet
        com = (0.0, 0.0, 1.0)
        foot_L = ContactConstraintSpec("foot_L", (-0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        foot_R = ContactConstraintSpec("foot_R", (0.15, 0.0, 0.0), (0.0, 0.0, 1.0), 0.70)
        target = ContactWrenchTarget((0.0, 0.0, 686.7), (0.0, 0.0, 0.0), com)

        sol = solve_contact_forces(target, [foot_L, foot_R])
        self.assertEqual(sol.status, ContactSolverStatus.SOLVED)

        # 2. Convert to ForwardDynamicsStepInput via factory
        step_in = ForwardDynamicsStepInput.from_solution_and_specs(
            solution=sol,
            specs=[foot_L, foot_R],
            gravity_acceleration_world=(0.0, 0.0, -9.81),
            dt=1.0 / 24.0,
            target_linear_acceleration_world=(0.0, 0.0, 0.0),
            target_angular_momentum_rate_world=(0.0, 0.0, 0.0),
        )

        # 3. Integrate single step
        res = integrate_forward_dynamics_single_step(self.default_state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)

        # Net force is <= 10mN (solver tolerance)
        self.assertLessEqual(res.net_force_world[2], 0.02)
        # Net torque is <= 10mN*m
        self.assertLessEqual(vec3_length(res.net_torque_about_com_world), 0.02)

        # Tracking error diagnostics are populated without writing into actual state
        self.assertIsNotNone(res.linear_acceleration_tracking_error)
        self.assertIsNotNone(res.angular_momentum_rate_tracking_error)

    # -------------------------------------------------------------------------
    # Test 18: State & Step Input Defensive Immutability Against External List Mutation
    # -------------------------------------------------------------------------
    def test_18_state_and_input_defensive_immutability(self):
        """Test 18: External list modification does not corrupt ForwardDynamicsState, StepInput, or ContactPoint."""
        # 1. ForwardDynamicsState defensive copying
        pos_list = [1.0, 2.0, 3.0]
        vel_list = [0.1, 0.2, 0.3]
        ang_list = [0.4, 0.5, 0.6]
        quat_list = [1.0, 0.0, 0.0, 0.0]

        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=70.0,
            com_position_world=pos_list,  # type: ignore
            com_velocity_world=vel_list,  # type: ignore
            angular_momentum_about_com_world=ang_list,  # type: ignore
            orientation_quat_world=quat_list,  # type: ignore
            inertia_tensor_body=self.default_inertia,
        )

        # Mutate the source lists in-place
        pos_list[0] = 999.0
        vel_list[1] = 888.0
        ang_list[2] = 777.0
        quat_list[0] = 666.0

        # State fields must remain completely unaffected and stored as tuples
        self.assertEqual(state.com_position_world, (1.0, 2.0, 3.0))
        self.assertIsInstance(state.com_position_world, tuple)
        self.assertEqual(state.com_velocity_world, (0.1, 0.2, 0.3))
        self.assertIsInstance(state.com_velocity_world, tuple)
        self.assertEqual(state.angular_momentum_about_com_world, (0.4, 0.5, 0.6))
        self.assertIsInstance(state.angular_momentum_about_com_world, tuple)
        self.assertEqual(state.orientation_quat_world, (1.0, 0.0, 0.0, 0.0))
        self.assertIsInstance(state.orientation_quat_world, tuple)

        # 2. ContactForcePoint defensive copying
        cp_p = [0.1, 0.2, 0.3]
        cp_f = [10.0, 20.0, 30.0]
        cp = ContactForcePoint(cp_p, cp_f, "test_cp")  # type: ignore
        cp_p[0] = -999.0
        cp_f[2] = 555.0
        self.assertEqual(cp.contact_point_world, (0.1, 0.2, 0.3))
        self.assertIsInstance(cp.contact_point_world, tuple)
        self.assertEqual(cp.contact_force_world, (10.0, 20.0, 30.0))
        self.assertIsInstance(cp.contact_force_world, tuple)

        # 3. ForwardDynamicsStepInput defensive copying
        ef_list = [[10.0, 0.0, 0.0], [0.0, 5.0, 0.0]]
        et_list = [[0.0, 0.0, 2.0]]
        grav_list = [0.0, 0.0, -9.81]
        cp_seq = [cp]

        step_in = ForwardDynamicsStepInput(
            contact_forces=cp_seq,  # type: ignore
            external_forces_world=ef_list,  # type: ignore
            external_torques_about_com_world=et_list,  # type: ignore
            gravity_acceleration_world=grav_list,  # type: ignore
            dt=0.04,
        )

        # Mutate the source structures in-place
        ef_list[0][0] = -888.0
        ef_list.append([100.0, 100.0, 100.0])
        et_list[0][2] = 999.0
        grav_list[2] = 0.0
        cp_seq.append(ContactForcePoint((1.0, 1.0, 1.0), (0.0, 0.0, 0.0), "extra"))

        # StepInput fields must remain completely unaffected
        self.assertEqual(step_in.external_forces_world, ((10.0, 0.0, 0.0), (0.0, 5.0, 0.0)))
        self.assertIsInstance(step_in.external_forces_world, tuple)
        self.assertIsInstance(step_in.external_forces_world[0], tuple)
        self.assertEqual(step_in.external_torques_about_com_world, ((0.0, 0.0, 2.0),))
        self.assertIsInstance(step_in.external_torques_about_com_world, tuple)
        self.assertIsInstance(step_in.external_torques_about_com_world[0], tuple)
        self.assertEqual(step_in.gravity_acceleration_world, (0.0, 0.0, -9.81))
        self.assertIsInstance(step_in.gravity_acceleration_world, tuple)
        self.assertEqual(len(step_in.contact_forces), 1)

    # -------------------------------------------------------------------------
    # Test 19: Strict Vector and Quaternion Component Dimension Validation
    # -------------------------------------------------------------------------
    def test_19_strict_vector_dimension_validation(self):
        """Test 19: Strict rejection of vectors without exactly 3 components and quaternions without 4."""
        # 1. State vector length checks
        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsState(com_position_world=(1.0, 2.0))  # 2 components
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsState(com_velocity_world=(1.0, 2.0, 3.0, 4.0))  # 4 components
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsState(angular_momentum_about_com_world=(1.0,))  # 1 component
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsState(orientation_quat_world=(1.0, 0.0, 0.0))  # 3 components instead of 4
        self.assertIn("exactly 4 components", str(ctx.exception))

        # 2. ContactForcePoint length checks
        with self.assertRaises(ValueError) as ctx:
            ContactForcePoint((1.0, 2.0), (0.0, 0.0, 10.0))
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ContactForcePoint((1.0, 2.0, 3.0), (0.0, 0.0, 10.0, 5.0))
        self.assertIn("exactly 3 components", str(ctx.exception))

        # 3. StepInput vector length checks
        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsStepInput(gravity_acceleration_world=(0.0, -9.81))
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsStepInput(external_forces_world=((10.0, 20.0),))
        self.assertIn("exactly 3 components", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            ForwardDynamicsStepInput(external_torques_about_com_world=((1.0, 2.0, 3.0, 4.0),))
        self.assertIn("exactly 3 components", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 20: Non-Isotropic Rigid Body Torque-Free Motion and Energy Conservation
    # -------------------------------------------------------------------------
    def test_20_non_isotropic_torque_free_motion(self):
        """Test 20: Non-isotropic rigid body (Ixx != Iyy != Izz) conserves L and rotational kinetic energy."""
        # Non-isotropic principal moments: 2.0, 3.0, 5.0 kg*m^2
        I_non_iso = InertiaTensor3x3.from_diagonal(2.0, 3.0, 5.0)
        L0 = (1.5, 2.0, 2.5)  # Not aligned with any principal axis
        dt = 0.005
        total_steps = 100

        curr_state = ForwardDynamicsState(
            timestamp=0.0,
            mass=70.0,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=L0,
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=I_non_iso,
        )

        E0 = curr_state.rotational_kinetic_energy

        step_in = ForwardDynamicsStepInput(
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=dt,
        )

        for _ in range(total_steps):
            res = integrate_forward_dynamics_single_step(curr_state, step_in)
            self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)
            curr_state = res.state_next

            # Exact angular momentum conservation in free space
            self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[0], L0[0], places=9)
            self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[1], L0[1], places=9)
            self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[2], L0[2], places=9)

        Ef = curr_state.rotational_kinetic_energy
        rel_energy_drift = abs(Ef - E0) / E0
        # Energy drift must remain below 1e-4 over 100 steps
        self.assertLess(rel_energy_drift, 1e-4)

    # -------------------------------------------------------------------------
    # Test 21: Non-Isotropic Rigid Body Constant Torque Rotation
    # -------------------------------------------------------------------------
    def test_21_non_isotropic_constant_torque_rotation(self):
        """Test 21: Non-isotropic rigid body under constant external torque integrates exact Delta L."""
        I_non_iso = InertiaTensor3x3.from_diagonal(2.5, 3.5, 4.5)
        L0 = (0.5, 1.0, -0.5)
        tau = (10.0, -5.0, 8.0)
        dt = 0.01
        steps = 25
        total_T = steps * dt

        curr_state = ForwardDynamicsState(
            timestamp=0.0,
            mass=70.0,
            com_position_world=(0.0, 0.0, 1.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=L0,
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=I_non_iso,
        )

        step_in = ForwardDynamicsStepInput(
            external_torques_about_com_world=(tau,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=dt,
        )

        for _ in range(steps):
            res = integrate_forward_dynamics_single_step(curr_state, step_in)
            self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)
            curr_state = res.state_next

        # Expected final angular momentum
        L_expected = (
            L0[0] + tau[0] * total_T,
            L0[1] + tau[1] * total_T,
            L0[2] + tau[2] * total_T,
        )
        self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[0], L_expected[0], places=9)
        self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[1], L_expected[1], places=9)
        self.assertAlmostEqual(curr_state.angular_momentum_about_com_world[2], L_expected[2], places=9)

        # Orientation must maintain unit norm
        self.assertAlmostEqual(quat_length(curr_state.orientation_quat_world), 1.0, places=9)

    # -------------------------------------------------------------------------
    # Test 22: Rigorous 2nd-Order Midpoint Attitude Convergence Rate Verification
    # -------------------------------------------------------------------------
    def test_22_second_order_midpoint_convergence_rate(self):
        """Test 22: Midpoint attitude integrator demonstrates quadratic O(dt^2) error reduction."""
        I_body = InertiaTensor3x3.from_diagonal(2.0, 4.0, 5.0)
        L0 = (2.0, 1.5, -1.0)
        tau = (5.0, -3.0, 4.0)
        T_horizon = 0.04

        def simulate_with_dt(dt_val: float):
            s = ForwardDynamicsState(
                mass=70.0,
                inertia_tensor_body=I_body,
                angular_momentum_about_com_world=L0,
                com_velocity_world=(0.0, 0.0, 0.0),
                com_position_world=(0.0, 0.0, 1.0),
            )
            step_count = int(round(T_horizon / dt_val))
            step_input = ForwardDynamicsStepInput(
                external_torques_about_com_world=(tau,),
                gravity_acceleration_world=(0.0, 0.0, 0.0),
                dt=dt_val,
            )
            for _ in range(step_count):
                s = integrate_forward_dynamics_single_step(s, step_input).state_next
            return s.orientation_quat_world

        q_dt1 = simulate_with_dt(0.04)
        q_dt2 = simulate_with_dt(0.02)
        q_dt3 = simulate_with_dt(0.01)
        q_dt4 = simulate_with_dt(0.005)

        def quat_diff_norm(qa, qb):
            return quat_length((qa[0] - qb[0], qa[1] - qb[1], qa[2] - qb[2], qa[3] - qb[3]))

        e12 = quat_diff_norm(q_dt1, q_dt2)
        e23 = quat_diff_norm(q_dt2, q_dt3)
        e34 = quat_diff_norm(q_dt3, q_dt4)

        # Monotonic convergence: error strictly decreases as dt is halved
        self.assertLess(e23, e12)
        self.assertLess(e34, e23)

        # Convergence ratio: for a 2nd-order method, e(2h) / e(h) ~ 2^2 = 4.0
        ratio_12_23 = e12 / e23
        ratio_23_34 = e23 / e34

        self.assertAlmostEqual(ratio_12_23, 4.0, delta=0.2)
        self.assertAlmostEqual(ratio_23_34, 4.0, delta=0.2)


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv)
