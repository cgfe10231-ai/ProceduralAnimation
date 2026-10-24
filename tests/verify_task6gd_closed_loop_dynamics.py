"""Verification Suite for Multi-Frame Closed-Loop Dynamics Coordination (Task 6G-D-C1-B).

Covers 12 Core Scenarios and Physical/Architectural Contracts:
 1. Static support equilibrium: Contact forces compensate gravity; CoM height strictly maintained without sinkage.
 2. Horizontal acceleration under admissible friction: Generates actual horizontal acceleration matching target.
 3. Insufficient friction clamping: Cannot use fictitious forces; bounds to friction cone and reports tracking error.
 4. No-contact ballistic free fall: Accurately integrates under gravity and projectile motion with zero contact forces.
 5. Eccentric contact torque and attitude integration: Produces exact moment r x F and drives roll/pitch dynamics.
 6. Multi-frame closed-loop feedback tracking: Uses actual state of frame k to compute demands for frame k+1.
 7. Infeasible target rejection: Refuses impossible targets (e.g. tensile ground pull) without corrupted motion.
 8. Solver failure failure-atomicity: Keeps previous valid state strictly unmutated when solver fails.
 9. Deterministic reproducibility: Identical inputs produce bit-exact identical multi-frame trajectories.
10. Multi-frame long-horizon stability: 120 frames (5.0s) maintain finite numbers, unit quaternions, and bounded height.
11. Telemetry serialization and diagnostics: Ensures export_telemetry() and to_dict() provide complete visualization data.
12. Lie algebra quaternion logarithm rotation error accuracy: Validates SO(3) attitude tracking error vector.
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

from src.motion.contact_dynamics import (
    Vec3,
    vec3_length,
    vec3_sub,
)
from src.motion.contact_force_solver import (
    ContactConstraintSpec,
    ContactSolverConfig,
    ContactSolverStatus,
    ContactWrenchTarget,
)
from src.motion.forward_dynamics import (
    ContactForcePoint,
    ForwardDynamicsConfig,
    ForwardDynamicsState,
    ForwardDynamicsStatus,
    ForwardDynamicsStepInput,
    InertiaTensor3x3,
    integrate_forward_dynamics_single_step,
    quat_from_axis_angle,
    quat_length,
    quat_normalize,
    quat_rotate_vector,
)
from src.motion.closed_loop_dynamics import (
    ClosedLoopAdmissibilityPolicy,
    ClosedLoopControllerConfig,
    ClosedLoopDynamicsCoordinator,
    ClosedLoopFrameTelemetry,
    ClosedLoopSimulationTrajectory,
    ClosedLoopStepStatus,
    DesiredMotionReference,
    FeedbackGainsConfig,
    compute_commanded_accelerations,
    quat_error_rot_vector,
    step_closed_loop_dynamics,
)


class TestClosedLoopDynamics(unittest.TestCase):
    """Test suite for multi-frame closed-loop dynamics coordination."""

    def setUp(self):
        self.mass = 70.0
        self.com_height = 1.0
        self.com_init = (0.0, 0.0, self.com_height)
        self.default_inertia = InertiaTensor3x3.from_diagonal(10.0, 12.0, 15.0)
        self.dt = 1.0 / 24.0  # ~0.04167s

        self.initial_standing_state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        # Standard symmetrical bilateral foot contacts on flat ground Z = 0.0m
        self.foot_L = ContactConstraintSpec(
            contact_id="foot_L",
            contact_point_world=(-0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
            is_in_contact=True,
        )
        self.foot_R = ContactConstraintSpec(
            contact_id="foot_R",
            contact_point_world=(0.15, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.70,
            is_in_contact=True,
        )
        self.standing_contacts = [self.foot_L, self.foot_R]

    # -------------------------------------------------------------------------
    # Scenario 01: Static Support Equilibrium
    # -------------------------------------------------------------------------
    def test_01_static_support_equilibrium(self):
        """Scenario 01: Contact forces compensate gravity; CoM height strictly maintained without sinkage."""
        ref = DesiredMotionReference(
            target_com_position_world=self.com_init,
            target_com_velocity_world=(0.0, 0.0, 0.0),
            target_linear_acceleration_world=(0.0, 0.0, 0.0),
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref,
            contact_schedule=self.standing_contacts,
            num_steps=24,  # 1.0 second simulation
        )

        self.assertTrue(traj.all_advanced)
        self.assertEqual(len(traj.frames), 24)

        for f in traj.frames:
            self.assertEqual(f.step_status, ClosedLoopStepStatus.SUCCESS_EXACT)
            self.assertEqual(f.solver_status, ContactSolverStatus.SOLVED)
            self.assertTrue(f.is_physically_valid)

            # Normal forces sum up to mass * 9.81 = 686.7 N
            f_z_total = f.actual_net_force_world[2]
            # Net force should be zero within solver tolerance
            self.assertAlmostEqual(f_z_total, 0.0, delta=0.05)

            # Both feet share the load symmetrically (~343.35 N each)
            f_L_z = f.actual_contact_forces["foot_L"][2]
            f_R_z = f.actual_contact_forces["foot_R"][2]
            self.assertAlmostEqual(f_L_z + f_R_z, 70.0 * 9.81, delta=0.05)
            self.assertAlmostEqual(f_L_z, f_R_z, delta=1.0)

        # Final CoM position is strictly invariant (sinkage < 0.5mm)
        p_final = traj.final_state.com_position_world
        self.assertAlmostEqual(p_final[2], 1.0, delta=0.001)
        self.assertAlmostEqual(p_final[0], 0.0, delta=0.001)
        self.assertAlmostEqual(p_final[1], 0.0, delta=0.001)

    # -------------------------------------------------------------------------
    # Scenario 02: Horizontal Acceleration Under Admissible Friction
    # -------------------------------------------------------------------------
    def test_02_horizontal_acceleration_under_admissible_friction(self):
        """Scenario 02: Generates actual horizontal acceleration matching target under valid friction."""
        # Desired acceleration: a_x = 2.0 m/s^2. Required F_x = 70 * 2 = 140 N.
        # Max normal force = 686.7 N. Max friction force = 0.8 * 686.7 = 549.36 N >> 140 N.
        # To avoid pitch-over at 2 m/s^2, staggered stance provides longitudinal base:
        # ZMP offset = h * a / g = 1.0 * 2.0 / 9.81 = 0.204 m (within [-0.25, +0.25] m).
        foot_rear = ContactConstraintSpec("foot_rear", (-0.25, 0.0, 0.0), (0.0, 0.0, 1.0), 0.80)
        foot_front = ContactConstraintSpec("foot_front", (0.25, 0.0, 0.0), (0.0, 0.0, 1.0), 0.80)

        target_ax = 2.0
        ref = DesiredMotionReference(
            target_linear_acceleration_world=(target_ax, 0.0, 0.0),
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref,
            contact_schedule=[foot_rear, foot_front],
            num_steps=10,  # 10 steps = 0.4167s
        )

        self.assertTrue(traj.all_advanced)
        for f in traj.frames:
            self.assertEqual(f.step_status, ClosedLoopStepStatus.SUCCESS_EXACT)
            # Actual acceleration matches target
            self.assertAlmostEqual(f.actual_linear_acceleration_world[0], target_ax, delta=0.02)
            self.assertAlmostEqual(f.actual_linear_acceleration_world[2], 0.0, delta=0.02)

        # Velocity increases linearly: v_x(T) ≈ a_x * T
        expected_vx = target_ax * traj.total_time
        self.assertAlmostEqual(traj.final_state.com_velocity_world[0], expected_vx, delta=0.05)
        # Position advanced in +X
        self.assertGreater(traj.final_state.com_position_world[0], 0.0)

    # -------------------------------------------------------------------------
    # Scenario 03: Insufficient Friction Clamping Without Fictitious Forces
    # -------------------------------------------------------------------------
    def test_03_insufficient_friction_clamping_no_fictitious_forces(self):
        """Scenario 03: On icy ground (mu=0.05), horizontal force is clamped to mu*Fn and tracking error is reported."""
        # mu = 0.05 on icy ground
        # Normal force Fn ≈ 686.7 N. Max friction force = 0.05 * 686.7 = 34.335 N.
        # Max possible acceleration = 34.335 / 70 = 0.4905 m/s^2.
        # Demand an unattainable a_x = 3.0 m/s^2 (requires F_x = 210 N).
        foot_icy = ContactConstraintSpec("foot_icy", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.05)

        ref = DesiredMotionReference(
            target_linear_acceleration_world=(3.0, 0.0, 0.0),
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref,
            contact_schedule=[foot_icy],
            num_steps=5,
        )

        self.assertTrue(traj.all_advanced)
        for f in traj.frames:
            # Step is accepted as approximate because physical forces are valid within friction cone
            self.assertEqual(f.step_status, ClosedLoopStepStatus.SUCCESS_APPROXIMATE)
            self.assertEqual(f.solver_status, ContactSolverStatus.APPROXIMATE)

            # Contact force must strictly satisfy friction cone: |Fx| <= mu * Fz
            fx = f.actual_contact_forces["foot_icy"][0]
            fz = f.actual_contact_forces["foot_icy"][2]
            self.assertLessEqual(abs(fx), 0.05 * fz + 1e-4)

            # Actual acceleration is limited to <= 0.50 m/s^2
            self.assertLessEqual(f.actual_linear_acceleration_world[0], 0.50)

            # Tracking error is reported truthfully (~ -2.51 m/s^2)
            self.assertLess(f.tracking_error_linear_acc[0], -2.0)

    # -------------------------------------------------------------------------
    # Scenario 04: No-Contact Ballistic Free Fall
    # -------------------------------------------------------------------------
    def test_04_no_contact_ballistic_free_fall(self):
        """Scenario 04: With zero contacts, character falls under pure gravity without fictitious support."""
        state_air = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 5.0),
            com_velocity_world=(1.5, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )

        # Free fall reference: demanding natural projectile acceleration (0, 0, -9.81)
        ref = DesiredMotionReference(
            target_linear_acceleration_world=(0.0, 0.0, -9.81),
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=state_air,
            reference_schedule=ref,
            contact_schedule=[],  # Zero contacts
            num_steps=24,  # 1.0 second simulation
        )

        self.assertTrue(traj.all_advanced)
        T = traj.total_time  # 1.0s

        # Horizontal velocity conserved exactly at 1.5 m/s
        self.assertAlmostEqual(traj.final_state.com_velocity_world[0], 1.5, places=6)
        self.assertAlmostEqual(traj.final_state.com_position_world[0], 1.5 * T, places=4)

        # Vertical velocity: v_z(1s) = -9.81 m/s
        self.assertAlmostEqual(traj.final_state.com_velocity_world[2], -9.81 * T, places=4)

        # Vertical position: p_z(1s) = 5.0 - 0.5 * 9.81 * 1.0^2 = 0.095 m
        expected_z = 5.0 - 0.5 * 9.81 * (T * T)
        self.assertAlmostEqual(traj.final_state.com_position_world[2], expected_z, places=4)

        for f in traj.frames:
            self.assertEqual(f.actual_contact_forces, {})
            self.assertEqual(f.actual_net_force_world, (0.0, 0.0, -70.0 * 9.81))

    # -------------------------------------------------------------------------
    # Scenario 05: Eccentric Contact Produces True Torque and Attitude Dynamics
    # -------------------------------------------------------------------------
    def test_05_eccentric_contact_torque_and_attitude_integration(self):
        """Scenario 05: Eccentric contact offset in Y produces roll torque and integrates angular momentum/orientation."""
        # Single contact offset to the right (+Y = 0.3m, Z = 0.0m)
        # CoM at (0, 0, 1.0m) => r = (0.0, 0.3, -1.0)
        # Upward force F = (0, 0, 300N)
        # tau = r x F = (0.3 * 300, 0, 0) = (90 N*m, 0, 0) (Roll torque)
        foot_ecc = ContactConstraintSpec("foot_ecc", (0.0, 0.3, 0.0), (0.0, 0.0, 1.0), 0.70)

        # Reference demands a roll torque
        ref = DesiredMotionReference(
            target_linear_acceleration_world=(0.0, 0.0, -9.81 + (300.0 / 70.0)),
            target_angular_momentum_rate_world=(90.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref,
            contact_schedule=[foot_ecc],
            num_steps=10,
        )

        self.assertTrue(traj.all_advanced)
        # Angular momentum L_x must increase positively
        L_final = traj.final_state.angular_momentum_about_com_world
        self.assertGreater(L_final[0], 10.0)

        # Orientation quaternion reflects positive roll rotation around +X
        q_final = traj.final_state.orientation_quat_world
        self.assertGreater(q_final[1], 0.001)  # x component of quaternion > 0

    # -------------------------------------------------------------------------
    # Scenario 06: Multi-Frame Closed-Loop Feedback Tracking
    # -------------------------------------------------------------------------
    def test_06_multi_frame_feedback_closed_loop_tracking(self):
        """Scenario 06: Uses actual state of frame k to compute demands for frame k+1, driving tracking error toward zero."""
        # 4-point foot support with longitudinal base (heel-to-toe [-0.15, +0.15]) and lateral base ([-0.10, +0.10])
        foot_L_heel = ContactConstraintSpec("L_heel", (-0.15, -0.10, 0.0), (0.0, 0.0, 1.0), 0.80)
        foot_L_toe = ContactConstraintSpec("L_toe", (0.15, -0.10, 0.0), (0.0, 0.0, 1.0), 0.80)
        foot_R_heel = ContactConstraintSpec("R_heel", (-0.15, 0.10, 0.0), (0.0, 0.0, 1.0), 0.80)
        foot_R_toe = ContactConstraintSpec("R_toe", (0.15, 0.10, 0.0), (0.0, 0.0, 1.0), 0.80)
        contacts = [foot_L_heel, foot_L_toe, foot_R_heel, foot_R_toe]

        def motion_ref(frame_idx: int, t: float, curr_state: ForwardDynamicsState) -> DesiredMotionReference:
            return DesiredMotionReference(
                target_com_position_world=(0.2 * t, 0.0, 1.0),
                target_com_velocity_world=(0.2, 0.0, 0.0),
                target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=motion_ref,
            contact_schedule=contacts,
            num_steps=24,  # 1.0 second
        )

        self.assertTrue(traj.all_advanced)

        # Check that velocity converges toward 0.2 m/s
        final_vx = traj.final_state.com_velocity_world[0]
        self.assertAlmostEqual(final_vx, 0.2, delta=0.05)

        # Check that Z height remains locked to 1.0m
        final_z = traj.final_state.com_position_world[2]
        self.assertAlmostEqual(final_z, 1.0, delta=0.005)

    # -------------------------------------------------------------------------
    # Scenario 07: Infeasible Target Rejection
    # -------------------------------------------------------------------------
    def test_07_infeasible_target_rejection(self):
        """Scenario 07: Refuses physically impossible targets (e.g. downward tensile pull on unilateral ground)."""
        # Desired acceleration demands downward force on ground: F_z_contact < 0 (requires gluing/suction)
        ref_infeasible = DesiredMotionReference(
            target_linear_acceleration_world=(0.0, 0.0, -20.0),  # Demands accelerating downward faster than gravity
        )

        config = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_infeasible_zero_force_fallback=False,  # Strict rejection
            )
        )
        coordinator = ClosedLoopDynamicsCoordinator(config=config)
        telem = coordinator.step(
            state_curr=self.initial_standing_state,
            reference=ref_infeasible,
            contacts=self.standing_contacts,
        )

        # Infeasible request must be rejected
        self.assertEqual(telem.step_status, ClosedLoopStepStatus.REJECTED_INFEASIBLE)
        self.assertFalse(telem.state_advanced)
        # State strictly preserved
        self.assertEqual(telem.state_next, self.initial_standing_state)

    # -------------------------------------------------------------------------
    # Scenario 08: Solver Input Failure Preserves State Atomically
    # -------------------------------------------------------------------------
    def test_08_solver_input_failure_preserves_state_atomically(self):
        """Scenario 08: Invalid solver inputs (e.g. duplicate contact IDs) trigger failure atomicity without corrupting state."""
        coordinator = ClosedLoopDynamicsCoordinator()

        # Step with corrupted contact spec whose normal is zero raises ValueError during construction
        with self.assertRaises(ValueError):
            ContactConstraintSpec("c", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

        # Test failure atomicity on step with duplicate contact IDs (rejected as INVALID_INPUT)
        duplicate_contacts = [self.foot_L, self.foot_L]
        telem = coordinator.step(
            state_curr=self.initial_standing_state,
            reference=DesiredMotionReference(target_linear_acceleration_world=(0.0, 0.0, 0.0)),
            contacts=duplicate_contacts,
        )
        self.assertEqual(telem.step_status, ClosedLoopStepStatus.SOLVER_INVALID_INPUT)
        self.assertEqual(telem.state_next, self.initial_standing_state)
        self.assertFalse(telem.state_advanced)
        self.assertFalse(telem.is_control_feasible)

    # -------------------------------------------------------------------------
    # Scenario 09: Deterministic Reproducibility
    # -------------------------------------------------------------------------
    def test_09_deterministic_reproducibility(self):
        """Scenario 09: Identical inputs produce 100% bit-exact reproducible trajectories."""
        ref = DesiredMotionReference(
            target_com_position_world=(0.2, 0.1, 1.0),
            target_com_velocity_world=(0.1, 0.0, 0.0),
            target_linear_acceleration_world=(0.5, 0.0, 0.0),
            target_orientation_quat_world=quat_from_axis_angle((0.0, 0.0, 1.0), math.pi / 8.0),
        )

        coord_A = ClosedLoopDynamicsCoordinator()
        traj_A = coord_A.simulate(self.initial_standing_state, ref, self.standing_contacts, num_steps=20)

        coord_B = ClosedLoopDynamicsCoordinator()
        traj_B = coord_B.simulate(self.initial_standing_state, ref, self.standing_contacts, num_steps=20)

        self.assertEqual(len(traj_A.frames), len(traj_B.frames))
        for fA, fB in zip(traj_A.frames, traj_B.frames):
            self.assertEqual(fA.state_next.com_position_world, fB.state_next.com_position_world)
            self.assertEqual(fA.state_next.com_velocity_world, fB.state_next.com_velocity_world)
            self.assertEqual(fA.state_next.angular_momentum_about_com_world, fB.state_next.angular_momentum_about_com_world)
            self.assertEqual(fA.state_next.orientation_quat_world, fB.state_next.orientation_quat_world)
            self.assertEqual(fA.actual_contact_forces, fB.actual_contact_forces)

    # -------------------------------------------------------------------------
    # Scenario 10: Multi-Frame Long-Horizon Stability
    # -------------------------------------------------------------------------
    def test_10_multi_frame_long_horizon_stability(self):
        """Scenario 10: 120 frames (5.0s) maintain finite numbers, unit quaternions, and bounded height."""
        ref = DesiredMotionReference(
            target_com_position_world=self.com_init,
            target_com_velocity_world=(0.0, 0.0, 0.0),
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
        )

        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref,
            contact_schedule=self.standing_contacts,
            num_steps=120,  # 5.0 seconds
        )

        self.assertTrue(traj.all_advanced)
        self.assertEqual(len(traj.frames), 120)

        # Check every frame for numerical sanity
        for f in traj.frames:
            # Finite numbers
            p = f.state_next.com_position_world
            v = f.state_next.com_velocity_world
            q = f.state_next.orientation_quat_world
            self.assertTrue(all(math.isfinite(x) for x in p))
            self.assertTrue(all(math.isfinite(x) for x in v))
            self.assertTrue(all(math.isfinite(x) for x in q))

            # Unit quaternion norm preserved
            self.assertAlmostEqual(quat_length(q), 1.0, places=6)

            # Height stability: within 5mm of 1.0m
            self.assertAlmostEqual(p[2], 1.0, delta=0.005)

    # -------------------------------------------------------------------------
    # Scenario 11: Telemetry Serialization and Diagnostics
    # -------------------------------------------------------------------------
    def test_11_telemetry_serialization_and_diagnostics(self):
        """Scenario 11: Telemetry records export cleanly to JSON-serializable dictionaries."""
        ref = DesiredMotionReference(target_com_position_world=self.com_init)
        coordinator = ClosedLoopDynamicsCoordinator()
        traj = coordinator.simulate(self.initial_standing_state, ref, self.standing_contacts, num_steps=2)

        data = traj.export_telemetry()
        self.assertEqual(len(data), 2)
        frame0 = data[0]

        # Verify key telemetry dictionary fields
        self.assertIn("frame_index", frame0)
        self.assertIn("state_current", frame0)
        self.assertIn("state_next", frame0)
        self.assertIn("commanded_linear_acceleration", frame0)
        self.assertIn("commanded_angular_momentum_rate", frame0)
        self.assertIn("actual_contact_forces", frame0)
        self.assertIn("actual_net_force", frame0)
        self.assertIn("actual_net_torque", frame0)
        self.assertIn("step_status", frame0)
        self.assertIn("tracking_error_position", frame0)

        # Summary dictionary
        summary = traj.summary()
        self.assertEqual(summary["total_frames"], 2)
        self.assertTrue(summary["all_advanced"])

    # -------------------------------------------------------------------------
    # Scenario 12: Lie Algebra Quaternion Logarithm Rotation Error Accuracy
    # -------------------------------------------------------------------------
    def test_12_attitude_error_quaternion_log_map_accuracy(self):
        """Scenario 12: SO(3) attitude rotation error vector matches analytical Lie algebra logarithm."""
        q_curr = (1.0, 0.0, 0.0, 0.0)

        # 1. Zero error
        e0 = quat_error_rot_vector(q_curr, q_curr)
        self.assertEqual(e0, (0.0, 0.0, 0.0))

        # 2. Pure yaw rotation of +90 deg (pi/2) about +Z
        q_yaw90 = quat_from_axis_angle((0.0, 0.0, 1.0), math.pi / 2.0)
        e_yaw = quat_error_rot_vector(q_yaw90, q_curr)
        self.assertAlmostEqual(e_yaw[0], 0.0, places=7)
        self.assertAlmostEqual(e_yaw[1], 0.0, places=7)
        self.assertAlmostEqual(e_yaw[2], math.pi / 2.0, places=7)

        # 3. Pure pitch rotation of -45 deg (-pi/4) about +Y
        q_pitch = quat_from_axis_angle((0.0, 1.0, 0.0), -math.pi / 4.0)
        e_pitch = quat_error_rot_vector(q_pitch, q_curr)
        self.assertAlmostEqual(e_pitch[0], 0.0, places=7)
        self.assertAlmostEqual(e_pitch[1], -math.pi / 4.0, places=7)
        self.assertAlmostEqual(e_pitch[2], 0.0, places=7)

        # 4. Shortest path branch on S^3: opposite sign representation of identical attitude
        q_neg = (-q_yaw90[0], -q_yaw90[1], -q_yaw90[2], -q_yaw90[3])
        e_neg = quat_error_rot_vector(q_neg, q_curr)
        self.assertAlmostEqual(e_neg[2], math.pi / 2.0, places=7)

    # -------------------------------------------------------------------------
    # Scenario 13: Full 3D Gravity Target Wrench & Integration
    # -------------------------------------------------------------------------
    def test_13_full_3d_gravity_target_wrench_and_integration(self):
        """Scenario 13: Full 3D gravity vector handling in target wrench and closed-loop integration."""
        mass = 70.0
        g_3d = (1.5, -2.0, -9.81)
        a_target = (0.5, 1.0, 0.0)
        com = (0.0, 0.0, 1.0)
        f_ext = (10.0, -5.0, 0.0)

        # 1. Test ContactWrenchTarget.from_target_motion with 3D gravity
        target_wrench = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=a_target,
            com_world=com,
            dL_com_dt=(0.0, 0.0, 0.0),
            external_forces=[f_ext],
            gravity_acceleration_world=g_3d,
        )

        # Analytical expectation: F_target = m * a - m * g - F_ext
        expected_fx = mass * a_target[0] - mass * g_3d[0] - f_ext[0]  # 35 - 105 - 10 = -80
        expected_fy = mass * a_target[1] - mass * g_3d[1] - f_ext[1]  # 70 - (-140) - (-5) = 215
        expected_fz = mass * a_target[2] - mass * g_3d[2] - f_ext[2]  # 0 - (-686.7) - 0 = 686.7

        self.assertAlmostEqual(target_wrench.target_force_world[0], expected_fx, places=9)
        self.assertAlmostEqual(target_wrench.target_force_world[1], expected_fy, places=9)
        self.assertAlmostEqual(target_wrench.target_force_world[2], expected_fz, places=9)

        # 2. Test backwards compatibility when only gravity_z is supplied
        target_wrench_compat = ContactWrenchTarget.from_target_motion(
            mass=mass,
            target_linear_acc=(0.0, 0.0, 0.0),
            com_world=com,
            gravity_z=-9.81,
        )
        self.assertAlmostEqual(target_wrench_compat.target_force_world[0], 0.0, places=9)
        self.assertAlmostEqual(target_wrench_compat.target_force_world[1], 0.0, places=9)
        self.assertAlmostEqual(target_wrench_compat.target_force_world[2], mass * 9.81, places=9)

        # 3. Test closed-loop step consistency under 3D gravity in free air
        cfg_3d = ClosedLoopControllerConfig(
            gravity_acceleration_world=g_3d,
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_infeasible_zero_force_fallback=True,
            ),
        )
        coord = ClosedLoopDynamicsCoordinator(config=cfg_3d)

        # State in free air
        state_air = ForwardDynamicsState(
            timestamp=0.0,
            mass=mass,
            com_position_world=(0.0, 0.0, 5.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )
        ref_zero = DesiredMotionReference(target_linear_acceleration_world=g_3d)
        telem = coord.step(state_air, ref_zero, contacts=[])
        self.assertTrue(telem.state_advanced)
        # Net acceleration should equal g_3d exactly
        self.assertAlmostEqual(telem.actual_linear_acceleration_world[0], g_3d[0], places=6)
        self.assertAlmostEqual(telem.actual_linear_acceleration_world[1], g_3d[1], places=6)
        self.assertAlmostEqual(telem.actual_linear_acceleration_world[2], g_3d[2], places=6)

    # -------------------------------------------------------------------------
    # Scenario 14: Rotational Gyroscopic Coupling - Isotropic Inertia
    # -------------------------------------------------------------------------
    def test_14_rotational_feedback_gyroscopic_coupling_isotropic(self):
        """Scenario 14: Isotropic inertia produces zero gyroscopic coupling torque (omega x L = 0)."""
        isotropic_inertia = InertiaTensor3x3.from_diagonal(15.0, 15.0, 15.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(15.0, 30.0, 45.0),  # L = 15 * (1, 2, 3)
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=isotropic_inertia,
        )
        # Target matching current state exactly (alpha_fb = 0)
        ref = DesiredMotionReference(
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            target_angular_velocity_world=(1.0, 2.0, 3.0),
            target_angular_momentum_rate_world=(0.0, 0.0, 0.0),
        )
        cfg = ClosedLoopControllerConfig()
        _, dL_cmd = compute_commanded_accelerations(state, ref, cfg)
        # Since I is isotropic, omega x L is identically 0
        self.assertAlmostEqual(dL_cmd[0], 0.0, places=9)
        self.assertAlmostEqual(dL_cmd[1], 0.0, places=9)
        self.assertAlmostEqual(dL_cmd[2], 0.0, places=9)

    # -------------------------------------------------------------------------
    # Scenario 15: Rotational Gyroscopic Coupling - Principal Axis Rotation
    # -------------------------------------------------------------------------
    def test_15_rotational_feedback_gyroscopic_coupling_principal_axis(self):
        """Scenario 15: Rotation strictly along a principal axis produces zero gyroscopic coupling."""
        non_iso_inertia = InertiaTensor3x3.from_diagonal(10.0, 20.0, 30.0)
        # Spin strictly along Y axis (omega_y = 2.0, L_y = 40.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 40.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=non_iso_inertia,
        )
        ref = DesiredMotionReference(
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            target_angular_velocity_world=(0.0, 2.0, 0.0),
            target_angular_momentum_rate_world=(0.0, 0.0, 0.0),
        )
        cfg = ClosedLoopControllerConfig()
        _, dL_cmd = compute_commanded_accelerations(state, ref, cfg)
        # omega x L = (0, 2, 0) x (0, 40, 0) = (0, 0, 0)
        self.assertAlmostEqual(dL_cmd[0], 0.0, places=9)
        self.assertAlmostEqual(dL_cmd[1], 0.0, places=9)
        self.assertAlmostEqual(dL_cmd[2], 0.0, places=9)

    # -------------------------------------------------------------------------
    # Scenario 16: Rotational Gyroscopic Coupling - Non-Principal Axis Exact Match
    # -------------------------------------------------------------------------
    def test_16_rotational_feedback_gyroscopic_coupling_non_principal_axis_exact(self):
        """Scenario 16: Analytical verification of gyroscopic coupling torque tau_gyro = omega x L."""
        non_iso_inertia = InertiaTensor3x3.from_diagonal(10.0, 20.0, 30.0)
        # omega = (1.0, 2.0, 3.0), L = (10, 40, 90)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(10.0, 40.0, 90.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=non_iso_inertia,
        )
        # Analytical tau_gyro:
        # omega x L = (2*90 - 3*40, 3*10 - 1*90, 1*40 - 2*10) = (60.0, -60.0, 20.0)
        tau_ff = (5.0, -10.0, 15.0)

        # Case A: On target (alpha_fb = 0), commanded torque equals tau_ff + tau_gyro
        ref_on_target = DesiredMotionReference(
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            target_angular_velocity_world=(1.0, 2.0, 3.0),
            target_angular_momentum_rate_world=tau_ff,
        )
        cfg = ClosedLoopControllerConfig()
        _, dL_cmd_A = compute_commanded_accelerations(state, ref_on_target, cfg)
        self.assertAlmostEqual(dL_cmd_A[0], 5.0 + 60.0, places=9)
        self.assertAlmostEqual(dL_cmd_A[1], -10.0 - 60.0, places=9)
        self.assertAlmostEqual(dL_cmd_A[2], 15.0 + 20.0, places=9)

        # Case B: Off target (alpha_fb != 0)
        # Target omega = (2.0, 2.0, 3.0) -> e_omega = (1.0, 0.0, 0.0)
        # kd_rot = 8.0 -> alpha_fb = (8.0, 0.0, 0.0)
        # tau_acc = I * alpha_fb = (10 * 8, 0, 0) = (80.0, 0.0, 0.0)
        # tau_fb = tau_acc + tau_gyro = (80 + 60, -60, 20) = (140.0, -60.0, 20.0)
        # dL_cmd = tau_ff + tau_fb = (5 + 140, -10 - 60, 15 + 20) = (145.0, -70.0, 35.0)
        ref_off_target = DesiredMotionReference(
            target_orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            target_angular_velocity_world=(2.0, 2.0, 3.0),
            target_angular_momentum_rate_world=tau_ff,
        )
        _, dL_cmd_B = compute_commanded_accelerations(state, ref_off_target, cfg)
        self.assertAlmostEqual(dL_cmd_B[0], 145.0, places=9)
        self.assertAlmostEqual(dL_cmd_B[1], -70.0, places=9)
        self.assertAlmostEqual(dL_cmd_B[2], 35.0, places=9)

    # -------------------------------------------------------------------------
    # Scenario 17: Pure Feedforward Preserved When No Rotational Feedback
    # -------------------------------------------------------------------------
    def test_17_rotational_feedback_zero_feedback_preserves_pure_feedforward(self):
        """Scenario 17: Pure feedforward angular momentum rate is strictly preserved when feedback is omitted."""
        non_iso_inertia = InertiaTensor3x3.from_diagonal(10.0, 20.0, 30.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(10.0, 40.0, 90.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=non_iso_inertia,
        )
        tau_ff = (12.3, -45.6, 78.9)
        ref_pure_ff = DesiredMotionReference(
            target_angular_momentum_rate_world=tau_ff,
            target_orientation_quat_world=None,
            target_angular_velocity_world=None,
        )
        cfg = ClosedLoopControllerConfig()
        _, dL_cmd = compute_commanded_accelerations(state, ref_pure_ff, cfg)
        # Must strictly preserve tau_ff without adding gyro term
        self.assertEqual(dL_cmd, tau_ff)

    # -------------------------------------------------------------------------
    # Scenario 18: Gyro Torque Application Preserves Steady Spin in Forward Dynamics
    # -------------------------------------------------------------------------
    def test_18_rotational_steady_spin_integration_preserves_angular_velocity(self):
        """Scenario 18: Applying tau = omega x L maintains constant angular velocity without spurious precession."""
        non_iso_inertia = InertiaTensor3x3.from_diagonal(10.0, 20.0, 30.0)
        omega_init = (1.0, 2.0, 3.0)
        L_init = (10.0, 40.0, 90.0)
        state = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=self.com_init,
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=L_init,
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=non_iso_inertia,
        )
        # Tau_gyro = (60.0, -60.0, 20.0)
        tau_gyro = (60.0, -60.0, 20.0)
        step_in = ForwardDynamicsStepInput(
            dt=0.001,  # fine time step
            contact_forces=(),
            external_torques_about_com_world=(tau_gyro,),
            gravity_acceleration_world=(0.0, 0.0, 0.0),
        )
        res = integrate_forward_dynamics_single_step(state, step_in)
        self.assertEqual(res.status, ForwardDynamicsStatus.SUCCESS)
        # Angular acceleration d(omega)/dt should be zero
        omega_next = res.state_next.angular_velocity_world
        self.assertAlmostEqual(omega_next[0], omega_init[0], places=4)
        self.assertAlmostEqual(omega_next[1], omega_init[1], places=4)
        self.assertAlmostEqual(omega_next[2], omega_init[2], places=4)

    # -------------------------------------------------------------------------
    # Scenario 19: Mid-Air Hover Demand Falls Naturally Under Gravity
    # -------------------------------------------------------------------------
    def test_19_mid_air_hover_demand_falls_naturally(self):
        """Scenario 19: Mid-air hover demand is control-infeasible but physics advances naturally under gravity."""
        coord = ClosedLoopDynamicsCoordinator()
        state_air = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 5.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )
        # Controller demands hovering at z=5.0m
        ref_hover = DesiredMotionReference(
            target_com_position_world=(0.0, 0.0, 5.0),
            target_com_velocity_world=(0.0, 0.0, 0.0),
            target_linear_acceleration_world=(0.0, 0.0, 0.0),
        )
        # Execute 5 consecutive frames
        curr_state = state_air
        for frame in range(5):
            telem = coord.step(curr_state, ref_hover, contacts=[], frame_index=frame)
            # Control is infeasible (hover cannot be sustained in mid-air)
            self.assertFalse(telem.is_control_feasible)
            # Physical state MUST advance (character is not frozen in mid-air)
            self.assertTrue(telem.state_advanced)
            self.assertEqual(telem.step_status, ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED)
            # Height must decrease each frame
            self.assertLess(telem.state_next.com_position_world[2], curr_state.com_position_world[2])
            # Velocity z must become increasingly negative
            self.assertLess(telem.state_next.com_velocity_world[2], curr_state.com_velocity_world[2])
            curr_state = telem.state_next

        # Total drop after 5 frames (5 * 1/24s = 0.2083s): drop ~ 0.5 * 9.81 * (0.2083)^2 ~ 0.213m
        expected_drop = 0.5 * 9.81 * (5.0 * self.dt) ** 2
        actual_drop = 5.0 - curr_state.com_position_world[2]
        self.assertAlmostEqual(actual_drop, expected_drop, delta=0.01)

    # -------------------------------------------------------------------------
    # Scenario 20: Mid-Air Hover With Strict Freeze Option
    # -------------------------------------------------------------------------
    def test_20_mid_air_hover_strict_freeze_option(self):
        """Scenario 20: When strict_freeze_on_infeasible is enabled, state preserves strictly."""
        config_strict = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                strict_freeze_on_infeasible=True,
            )
        )
        coord = ClosedLoopDynamicsCoordinator(config=config_strict)
        state_air = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 5.0),
            com_velocity_world=(0.0, 0.0, 0.0),
            angular_momentum_about_com_world=(0.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )
        ref_hover = DesiredMotionReference(
            target_com_position_world=(0.0, 0.0, 5.0),
            target_com_velocity_world=(0.0, 0.0, 0.0),
        )
        telem = coord.step(state_air, ref_hover, contacts=[])
        self.assertFalse(telem.is_control_feasible)
        self.assertFalse(telem.state_advanced)
        self.assertEqual(telem.step_status, ClosedLoopStepStatus.REJECTED_INFEASIBLE)
        self.assertEqual(telem.state_next, state_air)

    # -------------------------------------------------------------------------
    # Scenario 21: Policy Disallow Approximate Solutions
    # -------------------------------------------------------------------------
    def test_21_policy_disallow_approximate_solutions(self):
        """Scenario 21: When allow_approximate_solutions=False, approximate solutions are rejected."""
        contact = ContactConstraintSpec(
            contact_id="foot",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.1,
        )
        ref = DesiredMotionReference(
            target_com_position_world=self.com_init,
            target_linear_acceleration_world=(2.0, 0.0, 0.0),
        )

        # 1. With allow_approximate_solutions=True and large allowable residual -> Admitted
        cfg_allow = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_approximate_solutions=True,
                max_allowable_force_residual=200.0,
            )
        )
        telem_allow = step_closed_loop_dynamics(self.initial_standing_state, ref, [contact], config=cfg_allow)
        self.assertEqual(telem_allow.solver_status, ContactSolverStatus.APPROXIMATE)
        self.assertEqual(telem_allow.step_status, ClosedLoopStepStatus.SUCCESS_APPROXIMATE)
        self.assertTrue(telem_allow.state_advanced)
        self.assertTrue(telem_allow.is_target_satisfied)
        self.assertTrue(telem_allow.is_policy_admitted)

        # 2. With allow_approximate_solutions=False -> Rejected
        cfg_disallow = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_approximate_solutions=False,
                max_allowable_force_residual=200.0,
            )
        )
        telem_disallow = step_closed_loop_dynamics(self.initial_standing_state, ref, [contact], config=cfg_disallow)
        self.assertEqual(telem_disallow.solver_status, ContactSolverStatus.APPROXIMATE)
        self.assertEqual(telem_disallow.step_status, ClosedLoopStepStatus.REJECTED_APPROXIMATE)
        self.assertFalse(telem_disallow.state_advanced)
        self.assertFalse(telem_disallow.is_target_satisfied)
        self.assertFalse(telem_disallow.is_policy_admitted)
        self.assertEqual(telem_disallow.state_next, self.initial_standing_state)

    # -------------------------------------------------------------------------
    # Scenario 22: Admissibility Policy Truth Table Matrix
    # -------------------------------------------------------------------------
    def test_22_policy_approximate_solutions_matrix(self):
        """Scenario 22: Complete truth table for approximate solution admission."""
        contact = ContactConstraintSpec(
            contact_id="foot",
            contact_point_world=(0.0, 0.0, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            friction_coeff=0.1,
        )
        ref = DesiredMotionReference(
            target_com_position_world=self.com_init,
            target_linear_acceleration_world=(2.0, 0.0, 0.0),
        )

        # Matrix Case 1: strict_solved_only=True overrides allow_approximate_solutions=True
        cfg1 = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                strict_solved_only=True,
                allow_approximate_solutions=True,
                max_allowable_force_residual=200.0,
            )
        )
        t1 = step_closed_loop_dynamics(self.initial_standing_state, ref, [contact], config=cfg1)
        self.assertEqual(t1.step_status, ClosedLoopStepStatus.REJECTED_APPROXIMATE)
        self.assertFalse(t1.state_advanced)

        # Matrix Case 2: residual exceeds threshold and strict_freeze_on_infeasible=True
        cfg2 = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_approximate_solutions=True,
                max_allowable_force_residual=1.0,
                strict_freeze_on_infeasible=True,
            )
        )
        t2 = step_closed_loop_dynamics(self.initial_standing_state, ref, [contact], config=cfg2)
        self.assertEqual(t2.step_status, ClosedLoopStepStatus.REJECTED_APPROXIMATE)
        self.assertFalse(t2.state_advanced)

        # Matrix Case 3: residual exceeds threshold and strict_freeze_on_infeasible=False -> advances under physics
        cfg3 = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(
                allow_approximate_solutions=True,
                max_allowable_force_residual=1.0,
                strict_freeze_on_infeasible=False,
            )
        )
        t3 = step_closed_loop_dynamics(self.initial_standing_state, ref, [contact], config=cfg3)
        self.assertEqual(t3.step_status, ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED)
        self.assertTrue(t3.state_advanced)
        self.assertFalse(t3.is_target_satisfied)
        self.assertTrue(t3.is_policy_admitted)

    # -------------------------------------------------------------------------
    # Scenario 23: Simulation Time and Step Accounting
    # -------------------------------------------------------------------------
    def test_23_simulate_time_accounting_fail_fast_true_and_false(self):
        """Scenario 23: Accurate time accounting distinguishes requested vs actual physical time."""
        def ref_sched(k, t, s):
            if k < 2:
                return DesiredMotionReference(target_com_position_world=self.com_init)
            else:
                return DesiredMotionReference(target_com_position_world=(0.0, 0.0, 5.0))

        def contact_sched(k, t, s):
            if k < 2:
                return self.standing_contacts
            else:
                return []

        # Case A: fail_fast=True with strict_freeze
        cfg_strict = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(strict_freeze_on_infeasible=True)
        )
        coord_strict = ClosedLoopDynamicsCoordinator(config=cfg_strict)
        traj_ff = coord_strict.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref_sched,
            contact_schedule=contact_sched,
            num_steps=5,
            fail_fast=True,
        )

        self.assertEqual(traj_ff.requested_steps, 5)
        self.assertEqual(traj_ff.attempted_steps, 3)
        self.assertEqual(traj_ff.successful_steps, 2)
        self.assertEqual(traj_ff.failed_steps, 1)
        self.assertAlmostEqual(traj_ff.requested_duration, 5 * self.dt)
        self.assertAlmostEqual(traj_ff.actual_physical_time, 2 * self.dt)
        self.assertAlmostEqual(traj_ff.total_time, traj_ff.actual_physical_time)
        self.assertFalse(traj_ff.all_advanced)

        # Case B: fail_fast=False with strict_freeze
        traj_no_ff = coord_strict.simulate(
            initial_state=self.initial_standing_state,
            reference_schedule=ref_sched,
            contact_schedule=contact_sched,
            num_steps=5,
            fail_fast=False,
        )

        self.assertEqual(traj_no_ff.requested_steps, 5)
        self.assertEqual(traj_no_ff.attempted_steps, 5)
        self.assertEqual(traj_no_ff.successful_steps, 2)
        self.assertEqual(traj_no_ff.failed_steps, 3)
        self.assertAlmostEqual(traj_no_ff.requested_duration, 5 * self.dt)
        self.assertAlmostEqual(traj_no_ff.actual_physical_time, 2 * self.dt)
        self.assertAlmostEqual(traj_no_ff.total_time, traj_no_ff.actual_physical_time)
        self.assertFalse(traj_no_ff.all_advanced)

        # Summary check
        s = traj_no_ff.summary()
        self.assertEqual(s["requested_steps"], 5)
        self.assertEqual(s["attempted_steps"], 5)
        self.assertEqual(s["successful_steps"], 2)
        self.assertEqual(s["failed_steps"], 3)
        self.assertAlmostEqual(s["actual_physical_time_sec"], 2 * self.dt)

    # -------------------------------------------------------------------------
    # Scenario 24: Telemetry Orthogonal Status Semantics
    # -------------------------------------------------------------------------
    def test_24_telemetry_orthogonal_status_semantics(self):
        """Scenario 24: Validate orthogonal status flags across exact, unadmitted, and fallback frames."""
        coord = ClosedLoopDynamicsCoordinator()

        # 1. Standing exact solve
        ref_stand = DesiredMotionReference(target_com_position_world=self.com_init)
        t_stand = coord.step(self.initial_standing_state, ref_stand, self.standing_contacts)
        self.assertTrue(t_stand.is_contact_solution_physically_valid)
        self.assertTrue(t_stand.is_policy_admitted)
        self.assertTrue(t_stand.is_target_satisfied)
        self.assertTrue(t_stand.state_advanced)

        # 2. Mid-air hover demand with default physics fallback
        ref_hover = DesiredMotionReference(target_com_position_world=(0.0, 0.0, 5.0))
        t_air = coord.step(self.initial_standing_state, ref_hover, contacts=[])
        self.assertTrue(t_air.is_contact_solution_physically_valid)
        self.assertTrue(t_air.is_policy_admitted)
        self.assertFalse(t_air.is_target_satisfied)
        self.assertTrue(t_air.state_advanced)

        # 3. Mid-air hover demand with strict freeze
        cfg_strict = ClosedLoopControllerConfig(
            admissibility_policy=ClosedLoopAdmissibilityPolicy(strict_freeze_on_infeasible=True)
        )
        coord_strict = ClosedLoopDynamicsCoordinator(config=cfg_strict)
        t_freeze = coord_strict.step(self.initial_standing_state, ref_hover, contacts=[])
        self.assertTrue(t_freeze.is_contact_solution_physically_valid)
        self.assertFalse(t_freeze.is_policy_admitted)
        self.assertFalse(t_freeze.is_target_satisfied)
        self.assertFalse(t_freeze.state_advanced)

    # -------------------------------------------------------------------------
    # Scenario 25: Telemetry Immutability and No History Mutation
    # -------------------------------------------------------------------------
    def test_25_telemetry_immutability_and_no_pollution(self):
        """Scenario 25: Telemetry properties and exports cannot be mutated in place."""
        coord = ClosedLoopDynamicsCoordinator()
        ref = DesiredMotionReference(target_com_position_world=self.com_init)
        traj = coord.simulate(self.initial_standing_state, ref, self.standing_contacts, num_steps=2)

        t0 = traj.frames[0]
        # 1. actual_contact_forces is a MappingProxyType (raises TypeError on write)
        with self.assertRaises(TypeError):
            t0.actual_contact_forces["c0"] = (100.0, 200.0, 300.0)  # type: ignore

        # 2. Trajectory frames is an immutable tuple
        self.assertIsInstance(traj.frames, tuple)
        with self.assertRaises((AttributeError, TypeError)):
            traj.frames.append(t0)  # type: ignore

        # 3. export_telemetry returns detached copies
        exported = traj.export_telemetry()
        exported[0]["actual_net_force"] = [999.0, 999.0, 999.0]
        exported[0]["actual_contact_forces"]["foot_L"] = [999.0, 999.0, 999.0]

        exported_again = traj.export_telemetry()
        self.assertNotEqual(exported_again[0]["actual_net_force"], [999.0, 999.0, 999.0])
        self.assertNotEqual(exported_again[0]["actual_contact_forces"]["foot_L"], [999.0, 999.0, 999.0])

    # -------------------------------------------------------------------------
    # Scenario 26: Numerical Configuration Validation Gate
    # -------------------------------------------------------------------------
    def test_26_config_validation_numerical_gate(self):
        """Scenario 26: Deterministic validation rejects negative, NaN, or non-positive configurations."""
        # ContactSolverConfig
        with self.assertRaises(ValueError):
            ContactSolverConfig(force_tolerance_n=-1.0)
        with self.assertRaises(ValueError):
            ContactSolverConfig(torque_tolerance_nm=float("nan"))
        with self.assertRaises(ValueError):
            ContactSolverConfig(max_iterations=0)
        with self.assertRaises(ValueError):
            ContactSolverConfig(regularization_weight=-0.1)

        # FeedbackGainsConfig
        with self.assertRaises(ValueError):
            FeedbackGainsConfig(kp_pos=-1.0)
        with self.assertRaises(ValueError):
            FeedbackGainsConfig(kd_rot=float("inf"))
        with self.assertRaises(ValueError):
            FeedbackGainsConfig(max_linear_acceleration_cmd=0.0)
        with self.assertRaises(ValueError):
            FeedbackGainsConfig(max_angular_momentum_rate_cmd=-5.0)

        # ClosedLoopAdmissibilityPolicy
        with self.assertRaises(ValueError):
            ClosedLoopAdmissibilityPolicy(max_allowable_force_residual=-0.5)
        with self.assertRaises(ValueError):
            ClosedLoopAdmissibilityPolicy(max_allowable_torque_residual=float("nan"))

    # -------------------------------------------------------------------------
    # Scenario 27: System Boundaries, Inactive Contacts, and Contact ID Invariants
    # -------------------------------------------------------------------------
    def test_27_system_boundary_inactive_contacts_and_ids(self):
        """Scenario 27: Empty contacts, duplicate IDs, and single contact boundaries are strictly checked."""
        # Duplicate contact IDs rejected by solve_contact_forces
        c1 = ContactConstraintSpec("foot", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
        c2 = ContactConstraintSpec("foot", (0.1, 0.0, 0.0), (0.0, 0.0, 1.0))
        wrench = ContactWrenchTarget(
            target_force_world=(0.0, 0.0, 100.0),
            target_torque_world=(0.0, 0.0, 0.0),
            com_world=(0.0, 0.0, 1.0),
        )
        from src.motion.contact_force_solver import solve_contact_forces
        sol_dup = solve_contact_forces(wrench, [c1, c2])
        self.assertEqual(sol_dup.status, ContactSolverStatus.INVALID_INPUT)

        # Inactive contacts (is_in_contact=False)
        c_inactive = ContactConstraintSpec("foot_air", (0.0, 0.0, 0.5), (0.0, 0.0, 1.0), is_in_contact=False)
        coord = ClosedLoopDynamicsCoordinator()
        ref = DesiredMotionReference(target_com_position_world=self.com_init)
        telem = coord.step(self.initial_standing_state, ref, [c_inactive])
        self.assertTrue(telem.state_advanced)
        self.assertEqual(telem.actual_contact_forces["foot_air"], (0.0, 0.0, 0.0))

    # -------------------------------------------------------------------------
    # Scenario 28: Numerical Invariants and Analytical Conservation Verification
    # -------------------------------------------------------------------------
    def test_28_numerical_invariants_and_analytical_conservation(self):
        """Scenario 28: Zero-g momentum conservation, kinetic energy drift < 1e-6, static sinkage < 1e-5m."""
        cfg_zero_g = ClosedLoopControllerConfig(
            gravity_acceleration_world=(0.0, 0.0, 0.0),
            dt=0.01,
        )
        coord_zero_g = ClosedLoopDynamicsCoordinator(config=cfg_zero_g)
        state_spin = ForwardDynamicsState(
            timestamp=0.0,
            mass=self.mass,
            com_position_world=(0.0, 0.0, 0.0),
            com_velocity_world=(1.0, 2.0, 3.0),
            angular_momentum_about_com_world=(5.0, 0.0, 0.0),
            orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
            inertia_tensor_body=self.default_inertia,
        )
        ref_pass = DesiredMotionReference(target_linear_acceleration_world=(0.0, 0.0, 0.0))

        traj_spin = coord_zero_g.simulate(state_spin, ref_pass, contact_schedule=[], num_steps=100)
        self.assertTrue(traj_spin.all_advanced)
        f_final = traj_spin.frames[-1].state_next

        # Linear momentum: P = m * v
        p_init = (self.mass * 1.0, self.mass * 2.0, self.mass * 3.0)
        p_final = (self.mass * f_final.com_velocity_world[0], self.mass * f_final.com_velocity_world[1], self.mass * f_final.com_velocity_world[2])
        for i in range(3):
            self.assertAlmostEqual(p_final[i], p_init[i], delta=1e-10)

        # Angular momentum: L = L_0
        for i in range(3):
            self.assertAlmostEqual(f_final.angular_momentum_about_com_world[i], (5.0, 0.0, 0.0)[i], delta=1e-10)

        # Kinetic energy conservation: E_rot = 0.5 * L_x^2 / I_xx
        e_rot_init = 0.5 * (5.0 ** 2) / 10.0
        w = f_final.angular_velocity_world
        e_rot_final = 0.5 * (10.0 * w[0]**2 + 12.0 * w[1]**2 + 15.0 * w[2]**2)
        self.assertAlmostEqual(e_rot_final, e_rot_init, delta=1e-6)

        # Static standing sinkage over 50 frames
        coord = ClosedLoopDynamicsCoordinator()
        ref_stand = DesiredMotionReference(target_com_position_world=self.com_init)
        traj_stand = coord.simulate(self.initial_standing_state, ref_stand, self.standing_contacts, num_steps=50)
        z_final = traj_stand.frames[-1].state_next.com_position_world[2]
        self.assertAlmostEqual(z_final, 1.0, delta=1e-5)

    # -------------------------------------------------------------------------
    # Scenario 29: Step-Size Convergence Order Verification (O(dt^2))
    # -------------------------------------------------------------------------
    def test_29_step_size_convergence_order_two(self):
        """Scenario 29: Analytical constant-acceleration exactness and O(dt^2) nonlinear rotational convergence."""
        # Part A: Ballistic constant acceleration under Velocity Verlet has zero truncation error
        T_total = 0.4
        g = 9.81
        z0 = 10.0

        for dt_val in [0.04, 0.02, 0.01]:
            cfg = ClosedLoopControllerConfig(dt=dt_val)
            coord = ClosedLoopDynamicsCoordinator(config=cfg)
            state0 = ForwardDynamicsState(
                timestamp=0.0,
                mass=self.mass,
                com_position_world=(0.0, 0.0, z0),
                com_velocity_world=(0.0, 0.0, 0.0),
                angular_momentum_about_com_world=(0.0, 0.0, 0.0),
                orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
                inertia_tensor_body=self.default_inertia,
            )
            ref_free = DesiredMotionReference(
                target_com_position_world=(0.0, 0.0, z0),
                target_linear_acceleration_world=(0.0, 0.0, -g),
            )
            n_steps = int(round(T_total / dt_val))
            traj = coord.simulate(state0, ref_free, contact_schedule=[], num_steps=n_steps)
            z_end = traj.frames[-1].state_next.com_position_world[2]
            z_exact = z0 - 0.5 * g * (T_total ** 2)
            # Velocity Verlet integrates constant acceleration with zero truncation error (< 1e-12)
            self.assertAlmostEqual(z_end, z_exact, delta=1e-12)

        # Part B: Asymmetric rigid body nonlinear rotation exhibits true 2nd-order O(dt^2) convergence
        dts = [0.04, 0.02, 0.01, 0.001]
        quats = []
        for dt_val in dts:
            cfg_rot = ClosedLoopControllerConfig(dt=dt_val, gravity_acceleration_world=(0.0, 0.0, 0.0))
            coord_rot = ClosedLoopDynamicsCoordinator(config=cfg_rot)
            s_rot = ForwardDynamicsState(
                timestamp=0.0,
                mass=self.mass,
                com_position_world=(0.0, 0.0, 0.0),
                com_velocity_world=(0.0, 0.0, 0.0),
                angular_momentum_about_com_world=(10.0, 15.0, 20.0),
                orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
                inertia_tensor_body=InertiaTensor3x3.from_diagonal(5.0, 10.0, 15.0),
            )
            ref_zero = DesiredMotionReference(target_linear_acceleration_world=(0.0, 0.0, 0.0))
            n = int(round(T_total / dt_val))
            traj_rot = coord_rot.simulate(s_rot, ref_zero, contact_schedule=[], num_steps=n)
            quats.append(traj_rot.frames[-1].state_next.orientation_quat_world)

        q_ref = quats[-1]
        errors = [sum((a - b) ** 2 for a, b in zip(q, q_ref)) ** 0.5 for q in quats[:-1]]

        ratio1 = errors[0] / errors[1]
        ratio2 = errors[1] / errors[2]
        # Convergence ratio for O(dt^2) with dt halved is (2)^2 = 4.0
        self.assertAlmostEqual(ratio1, 4.0, delta=0.2)
        self.assertAlmostEqual(ratio2, 4.0, delta=0.2)
        self.assertLess(errors[2], errors[1])
        self.assertLess(errors[1], errors[0])

    # -------------------------------------------------------------------------
    # Scenario 30: Cross-Module Newton-Euler Balance Consistency
    # -------------------------------------------------------------------------
    def test_30_cross_module_newton_euler_balance_consistency(self):
        """Scenario 30: Sum(F) = m*a and Sum(tau) = dL/dt hold to 1e-7 across modules."""
        coord = ClosedLoopDynamicsCoordinator()
        ref = DesiredMotionReference(
            target_com_position_world=self.com_init,
            target_linear_acceleration_world=(0.5, 0.2, 0.0),
        )
        telem = coord.step(self.initial_standing_state, ref, self.standing_contacts)

        # 1. Newton's 2nd law: Sum(F_contact) + F_ext + m*g = m * a_actual
        m = self.mass
        g_vec = coord.config.gravity_acceleration_world
        f_contact_sum = [0.0, 0.0, 0.0]
        for f in telem.actual_contact_forces.values():
            for i in range(3):
                f_contact_sum[i] += f[i]

        net_force_calc = [
            f_contact_sum[0] + m * g_vec[0],
            f_contact_sum[1] + m * g_vec[1],
            f_contact_sum[2] + m * g_vec[2],
        ]
        ma_expected = [
            m * telem.actual_linear_acceleration_world[0],
            m * telem.actual_linear_acceleration_world[1],
            m * telem.actual_linear_acceleration_world[2],
        ]
        for i in range(3):
            self.assertAlmostEqual(net_force_calc[i], ma_expected[i], delta=1e-7)

        # 2. Euler's equation: Net torque about CoM = dL/dt
        for i in range(3):
            self.assertAlmostEqual(
                telem.actual_net_torque_about_com_world[i],
                telem.actual_angular_momentum_rate_world[i],
                delta=1e-7,
            )

    # -------------------------------------------------------------------------
    # Scenario 31: Non-Constant Acceleration Translational Benchmark (Section VIII)
    # -------------------------------------------------------------------------
    def test_31_non_constant_acceleration_convergence_benchmark(self):
        """Scenario 31: Measure translational error scaling under non-constant sinusoidal driving force."""
        a0 = 5.0
        omega = 2.0 * math.pi
        m = 70.0
        T = 0.4

        dts = [0.04, 0.02, 0.01]
        v_errors = []
        x_errors = []

        for dt in dts:
            n_steps = int(round(T / dt))
            state = ForwardDynamicsState(
                timestamp=0.0,
                mass=m,
                com_position_world=(0.0, 0.0, 0.0),
                com_velocity_world=(0.0, 0.0, 0.0),
                angular_momentum_about_com_world=(0.0, 0.0, 0.0),
                orientation_quat_world=(1.0, 0.0, 0.0, 0.0),
                inertia_tensor_body=self.default_inertia,
            )
            for k in range(n_steps):
                t_curr = k * dt
                F_x = m * a0 * math.sin(omega * t_curr)
                step_in = ForwardDynamicsStepInput(
                    dt=dt,
                    gravity_acceleration_world=(0.0, 0.0, 0.0),
                    external_forces_world=((F_x, 0.0, 0.0),),
                    external_torques_about_com_world=(),
                    contact_forces=(),
                )
                res = integrate_forward_dynamics_single_step(state, step_in)
                state = res.state_next

            v_exact = (a0 / omega) * (1.0 - math.cos(omega * T))
            x_exact = (a0 / omega) * T - (a0 / (omega * omega)) * math.sin(omega * T)

            v_err = abs(state.com_velocity_world[0] - v_exact)
            x_err = abs(state.com_position_world[0] - x_exact)
            v_errors.append(v_err)
            x_errors.append(x_err)

        # Velocity convergence ratios ~ 2.0 (1st order forward velocity update)
        r_v1 = v_errors[0] / v_errors[1]
        r_v2 = v_errors[1] / v_errors[2]
        self.assertAlmostEqual(r_v1, 2.0, delta=0.20)
        self.assertAlmostEqual(r_v2, 2.0, delta=0.20)

        # Position convergence ratios ~ 2.0 (driven by 1st order velocity error)
        r_x1 = x_errors[0] / x_errors[1]
        r_x2 = x_errors[1] / x_errors[2]
        self.assertAlmostEqual(r_x1, 2.0, delta=0.15)
        self.assertAlmostEqual(r_x2, 2.0, delta=0.15)

        # Monotonic convergence
        self.assertLess(v_errors[2], v_errors[1])
        self.assertLess(v_errors[1], v_errors[0])
        self.assertLess(x_errors[2], x_errors[1])
        self.assertLess(x_errors[1], x_errors[0])


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1:])
    unittest.main(argv=argv)
