"""Multi-Frame Dynamics Closed-Loop Control & State Feedback (Task 6G-D-C1-B & C1-B-R1).

Implements a mathematically rigorous, decoupled multi-frame closed-loop dynamics
coordination module for humanoid procedural animation:
- Connects the computation chain:
    Actual Physical State -> Desired Reference -> Feedback Law -> Target Wrench ->
    Contact Force Solver -> Actual Contact Forces & Torques -> Forward Dynamics Integration ->
    Next Actual State -> Telemetry & Tracking Feedback.
- 100% Decoupled Pure Python:
    Zero dependency on Blender GUI or bpy; fully runnable and testable in standalone Python.
- Never directly overwrites actual state with target velocities or accelerations:
    The actual physical trajectory is 100% computed from real physical forces integrated
    through 6-DOF Newton-Euler equations of motion.
- Strict Admissibility Policies:
    Differentiates between exact solved equilibrium, physically valid approximate solutions,
    control-infeasible targets, and numerical failures.
    - Numerical failures (NaN, invalid inputs) preserve state with failure atomicity.
    - Infeasible control targets (e.g. demanding hover in mid-air) do not freeze physical
      time by default: true physical forces (gravity, zero contact force) continue to advance
      natural physical evolution, while clearly reporting control infeasibility.
- Contact Geometry & Multi-Frame Boundary Contract:
    - ContactConstraintSpec represents instantaneous contact geometry and friction at the
      CURRENT time step.
    - Multi-frame simulation cannot assume static contact points remain valid indefinitely.
    - Subsequent Task 6G-D-C2 dynamically updates contact locations, clearances, and states
      via the environment query system (src/scene/environment_query.py) and contact model
      (src/motion/contact_model.py).
- Comprehensive Telemetry:
    Every frame records time, current/next state, reference, commanded controls, target wrench,
    contact forces, solver status, integration status, control feasibility, and diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.motion.contact_dynamics import (
    Vec3,
    _to_vec3,
    vec3_add,
    vec3_cross,
    vec3_dot,
    vec3_length,
    vec3_length_sq,
    vec3_normalize,
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
from src.motion.forward_dynamics import (
    ContactForcePoint,
    ForwardDynamicsConfig,
    ForwardDynamicsState,
    ForwardDynamicsStatus,
    ForwardDynamicsStepInput,
    ForwardDynamicsStepResult,
    InertiaTensor3x3,
    integrate_forward_dynamics_single_step,
    quat_length,
    quat_multiply,
    quat_normalize,
)

Vec4 = Tuple[float, float, float, float]  # Quaternion (w, x, y, z)


# =============================================================================
# 1. Low-Level Lie Algebra and Vector Utility Functions
# =============================================================================

def quat_conjugate(q: Sequence[float]) -> Vec4:
    """Quaternion conjugate representing spatial inversion for unit quaternions."""
    return (float(q[0]), -float(q[1]), -float(q[2]), -float(q[3]))


def quat_error_rot_vector(q_target: Sequence[float], q_curr: Sequence[float]) -> Vec3:
    """Compute SO(3) rotation error vector e_rot such that:

        R(q_target) ≈ exp([e_rot]x) * R(q_curr).

    Returns rotation vector (axis * angle_in_radians) defined in World Space coordinates.
    Exact logarithmic map on unit quaternions with shortest-path geodesic branch selection.
    """
    q_t = quat_normalize(q_target)
    q_c = quat_normalize(q_curr)

    # Relative attitude quaternion: q_rel = q_t * q_c^-1
    q_c_inv = quat_conjugate(q_c)
    q_rel = quat_multiply(q_t, q_c_inv)

    w, x, y, z = q_rel[0], q_rel[1], q_rel[2], q_rel[3]
    # Enforce shortest path on S^3: choose positive scalar w
    if w < 0.0:
        w, x, y, z = -w, -x, -y, -z

    v_norm = math.sqrt(x * x + y * y + z * z)
    if v_norm < 1e-12:
        return (0.0, 0.0, 0.0)

    angle = 2.0 * math.atan2(v_norm, w)
    scale = angle / v_norm
    return (float(x * scale), float(y * scale), float(z * scale))


def vec3_clamp_norm(v: Vec3, max_norm: float) -> Vec3:
    """Clamp 3D vector magnitude to max_norm without changing its direction."""
    if max_norm <= 0.0:
        return (0.0, 0.0, 0.0)
    n = vec3_length(v)
    if n <= max_norm or n < 1e-12:
        return (float(v[0]), float(v[1]), float(v[2]))
    scale = max_norm / n
    return (float(v[0] * scale), float(v[1] * scale), float(v[2] * scale))


def _validate_vec3_strict(v: Any, name: str) -> Vec3:
    """Strictly validate and defensively copy a 3D float vector."""
    if not isinstance(v, (list, tuple)):
        raise TypeError(f"{name} must be a sequence of 3 floats, got {type(v).__name__}")
    if len(v) != 3:
        raise ValueError(f"{name} must contain exactly 3 components, got {len(v)}")
    try:
        x, y, z = float(v[0]), float(v[1]), float(v[2])
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} components must be convertible to float: {exc}") from exc
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        raise ValueError(f"{name} components must be finite numbers, got ({x}, {y}, {z})")
    return (x, y, z)


def _validate_quat_strict(q: Any, name: str) -> Vec4:
    """Strictly validate and defensively normalize a 4D quaternion."""
    if not isinstance(q, (list, tuple)):
        raise TypeError(f"{name} must be a sequence of 4 floats, got {type(q).__name__}")
    if len(q) != 4:
        raise ValueError(f"{name} must contain exactly 4 components, got {len(q)}")
    try:
        w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} components must be convertible to float: {exc}") from exc
    if not (math.isfinite(w) and math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
        raise ValueError(f"{name} components must be finite numbers, got ({w}, {x}, {y}, {z})")
    norm_sq = w * w + x * x + y * y + z * z
    if norm_sq < 1e-24:
        raise ValueError(f"{name} cannot be degenerate with zero norm: ({w}, {x}, {y}, {z})")
    inv_norm = 1.0 / math.sqrt(norm_sq)
    return (w * inv_norm, x * inv_norm, y * inv_norm, z * inv_norm)


# =============================================================================
# 2. Desired Motion Reference & Feedback Control Configurations
# =============================================================================

@dataclass(frozen=True)
class DesiredMotionReference:
    """Independent desired motion target at an instant in time.

    Units & Conventions:
    - target_com_position_world: Desired CoM position in World Space (m), or None if tracking is unconstrained.
    - target_com_velocity_world: Desired CoM velocity in World Space (m/s), or None.
    - target_linear_acceleration_world: Feedforward linear acceleration (m/s^2). Default: (0, 0, 0).
    - target_orientation_quat_world: Desired Body-to-World attitude quaternion (w, x, y, z), or None.
    - target_angular_velocity_world: Desired angular velocity in World Space (rad/s), or None.
    - target_angular_momentum_rate_world: Feedforward rate of angular momentum dL/dt about CoM (N*m). Default: (0, 0, 0).
    - external_forces_world: External non-contact forces (e.g. payload, disturbance) (N).
    - external_torques_about_com_world: External non-contact moments about CoM (N*m).
    """
    target_com_position_world: Optional[Vec3] = None
    target_com_velocity_world: Optional[Vec3] = None
    target_linear_acceleration_world: Vec3 = (0.0, 0.0, 0.0)
    target_orientation_quat_world: Optional[Vec4] = None
    target_angular_velocity_world: Optional[Vec3] = None
    target_angular_momentum_rate_world: Vec3 = (0.0, 0.0, 0.0)
    external_forces_world: Tuple[Vec3, ...] = ()
    external_torques_about_com_world: Tuple[Vec3, ...] = ()

    def __post_init__(self):
        # Defensively standardize all vector inputs
        if self.target_com_position_world is not None:
            p = _validate_vec3_strict(self.target_com_position_world, "target_com_position_world")
            object.__setattr__(self, "target_com_position_world", p)

        if self.target_com_velocity_world is not None:
            v = _validate_vec3_strict(self.target_com_velocity_world, "target_com_velocity_world")
            object.__setattr__(self, "target_com_velocity_world", v)

        a_ff = _validate_vec3_strict(self.target_linear_acceleration_world, "target_linear_acceleration_world")
        object.__setattr__(self, "target_linear_acceleration_world", a_ff)

        if self.target_orientation_quat_world is not None:
            q = _validate_quat_strict(self.target_orientation_quat_world, "target_orientation_quat_world")
            object.__setattr__(self, "target_orientation_quat_world", q)

        if self.target_angular_velocity_world is not None:
            w = _validate_vec3_strict(self.target_angular_velocity_world, "target_angular_velocity_world")
            object.__setattr__(self, "target_angular_velocity_world", w)

        dL_ff = _validate_vec3_strict(
            self.target_angular_momentum_rate_world, "target_angular_momentum_rate_world"
        )
        object.__setattr__(self, "target_angular_momentum_rate_world", dL_ff)

        if not isinstance(self.external_forces_world, (list, tuple)):
            raise TypeError(f"external_forces_world must be a sequence, got {type(self.external_forces_world)}")
        ef_list = [_validate_vec3_strict(ef, f"external_forces_world[{i}]") for i, ef in enumerate(self.external_forces_world)]
        object.__setattr__(self, "external_forces_world", tuple(ef_list))

        if not isinstance(self.external_torques_about_com_world, (list, tuple)):
            raise TypeError(
                f"external_torques_about_com_world must be a sequence, got {type(self.external_torques_about_com_world)}"
            )
        et_list = [
            _validate_vec3_strict(et, f"external_torques_about_com_world[{i}]")
            for i, et in enumerate(self.external_torques_about_com_world)
        ]
        object.__setattr__(self, "external_torques_about_com_world", tuple(et_list))


@dataclass(frozen=True)
class FeedbackGainsConfig:
    """Feedback control gains and numerical stability bounds.

    Units:
    - kp_pos: Proportional gain for CoM position tracking (1/s^2). a_fb = kp * e_p + kd * e_v.
    - kd_pos: Derivative gain for CoM velocity tracking (1/s).
    - kp_rot: Proportional gain for orientation rotation tracking (1/s^2). alpha_fb = kp_rot * e_rot + kd_rot * e_omega.
    - kd_rot: Derivative gain for angular velocity tracking (1/s).
    - max_linear_acceleration_cmd: Saturation limit on commanded linear acceleration ||a_cmd|| (m/s^2).
    - max_angular_momentum_rate_cmd: Saturation limit on commanded torque ||dL_cmd/dt|| (N*m).
    """
    kp_pos: float = 16.0
    kd_pos: float = 6.0
    kp_rot: float = 25.0
    kd_rot: float = 8.0
    max_linear_acceleration_cmd: float = 20.0
    max_angular_momentum_rate_cmd: float = 300.0

    def __post_init__(self):
        for name, val in [
            ("kp_pos", self.kp_pos),
            ("kd_pos", self.kd_pos),
            ("kp_rot", self.kp_rot),
            ("kd_rot", self.kd_rot),
            ("max_linear_acceleration_cmd", self.max_linear_acceleration_cmd),
            ("max_angular_momentum_rate_cmd", self.max_angular_momentum_rate_cmd),
        ]:
            if not math.isfinite(val) or val < 0.0:
                raise ValueError(f"Gain '{name}' must be non-negative and finite, got {val}")


@dataclass(frozen=True)
class ClosedLoopAdmissibilityPolicy:
    """Policy rules governing when a solver solution is admitted to advance physical state.

    Controls:
    - allow_approximate_solutions: If True, physically valid solutions with non-zero residual are admitted.
    - max_allowable_force_residual: Max permitted force residual norm (N) if approximate.
    - max_allowable_torque_residual: Max permitted torque residual norm (N*m) if approximate.
    - allow_infeasible_zero_force_fallback: If True, free flight advances naturally under 0 contact force.
    - strict_freeze_on_infeasible: If True, freezes time whenever control target is physically infeasible.
    - strict_solved_only: If True, only SOLVED status is admitted; APPROXIMATE is rejected.
    """
    allow_approximate_solutions: bool = True
    max_allowable_force_residual: float = 250.0  # Max permitted force residual norm (N) if approximate
    max_allowable_torque_residual: float = 150.0  # Max permitted torque residual norm (N*m) if approximate
    allow_infeasible_zero_force_fallback: bool = True  # If True, free fall continues under 0 contact force
    strict_freeze_on_infeasible: bool = False  # If True, freeze physical time on infeasible control target
    strict_solved_only: bool = False  # If True, only SOLVED status is admitted


@dataclass(frozen=True)
class ClosedLoopControllerConfig:
    """Complete configuration for multi-frame closed-loop dynamics simulation."""
    dt: float = 1.0 / 24.0
    gravity_acceleration_world: Vec3 = (0.0, 0.0, -9.81)
    feedback_gains: FeedbackGainsConfig = field(default_factory=FeedbackGainsConfig)
    admissibility_policy: ClosedLoopAdmissibilityPolicy = field(default_factory=ClosedLoopAdmissibilityPolicy)
    solver_config: ContactSolverConfig = field(default_factory=ContactSolverConfig)
    forward_dynamics_config: ForwardDynamicsConfig = field(default_factory=ForwardDynamicsConfig)

    def __post_init__(self):
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError(f"dt must be strictly positive and finite, got {self.dt}")
        grav = _validate_vec3_strict(self.gravity_acceleration_world, "gravity_acceleration_world")
        object.__setattr__(self, "gravity_acceleration_world", grav)


# =============================================================================
# 3. Status and Telemetry Contracts
# =============================================================================

class ClosedLoopStepStatus(str, Enum):
    """Detailed outcome classification of a single closed-loop coordination step."""
    SUCCESS_EXACT = "SUCCESS_EXACT"                             # Solver exact SOLVED, physical state advanced
    SUCCESS_APPROXIMATE = "SUCCESS_APPROXIMATE"                 # Solver APPROXIMATE within tolerance, physical state advanced
    CONTROL_INFEASIBLE_PHYSICS_ADVANCED = "CONTROL_INFEASIBLE_PHYSICS_ADVANCED" # Control target infeasible, but physics advanced under true valid forces
    REJECTED_INFEASIBLE = "REJECTED_INFEASIBLE"                 # Infeasible and forces unprovable or strict freeze, state preserved
    REJECTED_APPROXIMATE = "REJECTED_APPROXIMATE"               # Residual exceeded tolerance and strict freeze, state preserved
    SOLVER_INVALID_INPUT = "SOLVER_INVALID_INPUT"               # Invalid solver inputs (NaN, corrupt specs), state preserved
    SOLVER_NUMERICAL_FAILURE = "SOLVER_NUMERICAL_FAILURE"       # Solver crashed or NaN output, state preserved
    INTEGRATION_FAILURE = "INTEGRATION_FAILURE"                 # Forward dynamics numerical breakdown, state preserved


@dataclass(frozen=True)
class ClosedLoopFrameTelemetry:
    """Rich observable telemetry record for a single simulation frame."""
    frame_index: int
    timestamp: float
    state_current: ForwardDynamicsState
    state_next: ForwardDynamicsState
    motion_reference: DesiredMotionReference
    commanded_linear_acceleration_world: Vec3
    commanded_angular_momentum_rate_world: Vec3
    target_contact_wrench_force_world: Vec3
    target_contact_wrench_torque_world: Vec3
    solver_status: ContactSolverStatus
    solver_is_physically_valid: bool
    solver_force_residual_n: float
    solver_torque_residual_nm: float
    actual_contact_forces: Dict[str, Vec3]
    actual_net_force_world: Vec3
    actual_net_torque_about_com_world: Vec3
    actual_linear_acceleration_world: Vec3
    actual_angular_momentum_rate_world: Vec3
    step_status: ClosedLoopStepStatus
    is_physically_valid: bool
    state_advanced: bool
    is_control_feasible: bool = True
    tracking_error_position: Optional[Vec3] = None
    tracking_error_velocity: Optional[Vec3] = None
    tracking_error_linear_acc: Vec3 = (0.0, 0.0, 0.0)
    tracking_error_angular_momentum_rate: Vec3 = (0.0, 0.0, 0.0)
    message: str = ""

    @property
    def control_feasible(self) -> bool:
        return self.is_control_feasible

    @property
    def solver_force_residual_norm(self) -> float:
        return self.solver_force_residual_n

    @property
    def solver_torque_residual_norm(self) -> float:
        return self.solver_torque_residual_nm

    def to_dict(self) -> Dict[str, Any]:
        """Convert telemetry record into a pure JSON-serializable dictionary."""
        return {
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "state_current": {
                "timestamp": self.state_current.timestamp,
                "com_position": list(self.state_current.com_position_world),
                "com_velocity": list(self.state_current.com_velocity_world),
                "angular_momentum": list(self.state_current.angular_momentum_about_com_world),
                "orientation_quat": list(self.state_current.orientation_quat_world),
            },
            "state_next": {
                "timestamp": self.state_next.timestamp,
                "com_position": list(self.state_next.com_position_world),
                "com_velocity": list(self.state_next.com_velocity_world),
                "angular_momentum": list(self.state_next.angular_momentum_about_com_world),
                "orientation_quat": list(self.state_next.orientation_quat_world),
            },
            "commanded_linear_acceleration": list(self.commanded_linear_acceleration_world),
            "commanded_angular_momentum_rate": list(self.commanded_angular_momentum_rate_world),
            "target_contact_wrench_force": list(self.target_contact_wrench_force_world),
            "target_contact_wrench_torque": list(self.target_contact_wrench_torque_world),
            "solver_status": self.solver_status.value,
            "solver_is_physically_valid": self.solver_is_physically_valid,
            "solver_force_residual_n": self.solver_force_residual_n,
            "solver_torque_residual_nm": self.solver_torque_residual_nm,
            "solver_force_residual_norm": self.solver_force_residual_n,
            "solver_torque_residual_norm": self.solver_torque_residual_nm,
            "actual_contact_forces": {k: list(v) for k, v in self.actual_contact_forces.items()},
            "actual_net_force": list(self.actual_net_force_world),
            "actual_net_torque": list(self.actual_net_torque_about_com_world),
            "actual_linear_acceleration": list(self.actual_linear_acceleration_world),
            "actual_angular_momentum_rate": list(self.actual_angular_momentum_rate_world),
            "step_status": self.step_status.value,
            "is_physically_valid": self.is_physically_valid,
            "state_advanced": self.state_advanced,
            "is_control_feasible": self.is_control_feasible,
            "tracking_error_position": list(self.tracking_error_position) if self.tracking_error_position else None,
            "tracking_error_velocity": list(self.tracking_error_velocity) if self.tracking_error_velocity else None,
            "tracking_error_linear_acc": list(self.tracking_error_linear_acc),
            "tracking_error_angular_momentum_rate": list(self.tracking_error_angular_momentum_rate),
            "message": self.message,
        }


@dataclass(frozen=True)
class ClosedLoopSimulationTrajectory:
    """Complete multi-frame closed-loop trajectory record and summary."""
    frames: Tuple[ClosedLoopFrameTelemetry, ...]
    initial_state: ForwardDynamicsState
    final_state: ForwardDynamicsState
    dt: float
    total_time: float
    all_advanced: bool

    def summary(self) -> Dict[str, Any]:
        """Compute aggregate trajectory performance metrics."""
        step_counts: Dict[str, int] = {}
        for f in self.frames:
            s = f.step_status.value
            step_counts[s] = step_counts.get(s, 0) + 1

        pos_errors = [
            vec3_length(f.tracking_error_position)
            for f in self.frames
            if f.tracking_error_position is not None
        ]
        max_pos_err = max(pos_errors) if pos_errors else 0.0

        acc_errors = [vec3_length(f.tracking_error_linear_acc) for f in self.frames]
        max_acc_err = max(acc_errors) if acc_errors else 0.0

        return {
            "total_frames": len(self.frames),
            "total_time": self.total_time,
            "all_advanced": self.all_advanced,
            "step_status_counts": step_counts,
            "max_position_tracking_error_m": max_pos_err,
            "max_acceleration_tracking_error_m_s2": max_acc_err,
        }

    def export_telemetry(self) -> List[Dict[str, Any]]:
        """Export full trajectory as a list of dictionaries for JSON persistence / Blender playback."""
        return [f.to_dict() for f in self.frames]


# =============================================================================
# 4. Feedback Computation Engine
# =============================================================================

def compute_commanded_accelerations(
    state: ForwardDynamicsState,
    reference: DesiredMotionReference,
    config: ClosedLoopControllerConfig,
) -> Tuple[Vec3, Vec3]:
    """Compute commanded linear acceleration a_cmd (m/s^2) and angular momentum rate dL_cmd (N*m).

    Formulation:
    1. CoM Linear Motion PD Tracking:
       a_cmd = a_ff + kp_pos * (p_tgt - p_curr) + kd_pos * (v_tgt - v_curr)
       bounded to ||a_cmd|| <= max_linear_acceleration_cmd.

    2. Attitude & Angular Velocity PD Tracking:
       e_rot = log(q_tgt * q_curr^-1)  (SO(3) rotation error vector)
       e_omega = omega_tgt - omega_curr
       alpha_fb = kp_rot * e_rot + kd_rot * e_omega
       dL_cmd = dL_ff + I_world * alpha_fb
       bounded to ||dL_cmd|| <= max_angular_momentum_rate_cmd.
    """
    gains = config.feedback_gains

    # 1. Linear Tracking Law
    a_cmd = reference.target_linear_acceleration_world

    if reference.target_com_position_world is not None:
        p_err = vec3_sub(reference.target_com_position_world, state.com_position_world)
        a_cmd = vec3_add(a_cmd, vec3_scale(p_err, gains.kp_pos))

    if reference.target_com_velocity_world is not None:
        v_err = vec3_sub(reference.target_com_velocity_world, state.com_velocity_world)
        a_cmd = vec3_add(a_cmd, vec3_scale(v_err, gains.kd_pos))

    a_cmd = vec3_clamp_norm(a_cmd, gains.max_linear_acceleration_cmd)

    # 2. Rotational Tracking Law
    dL_cmd = reference.target_angular_momentum_rate_world

    alpha_fb: Vec3 = (0.0, 0.0, 0.0)
    has_rotational_feedback = False

    if reference.target_orientation_quat_world is not None:
        rot_err = quat_error_rot_vector(reference.target_orientation_quat_world, state.orientation_quat_world)
        alpha_fb = vec3_add(alpha_fb, vec3_scale(rot_err, gains.kp_rot))
        has_rotational_feedback = True

    if reference.target_angular_velocity_world is not None:
        omega_curr = state.angular_velocity_world
        omega_err = vec3_sub(reference.target_angular_velocity_world, omega_curr)
        alpha_fb = vec3_add(alpha_fb, vec3_scale(omega_err, gains.kd_rot))
        has_rotational_feedback = True

    if has_rotational_feedback:
        # Full rigid body rotational equation in World coordinates:
        # dL/dt = I_world * alpha + omega x L
        # alpha_fb is world-space angular acceleration feedback.
        # Gyroscopic coupling torque is tau_gyro = omega x L.
        I_world = state.inertia_tensor_world
        tau_acc = I_world.multiply_vec(alpha_fb)
        tau_gyro = vec3_cross(state.angular_velocity_world, state.angular_momentum_about_com_world)
        tau_fb = vec3_add(tau_acc, tau_gyro)
        dL_cmd = vec3_add(dL_cmd, tau_fb)

    dL_cmd = vec3_clamp_norm(dL_cmd, gains.max_angular_momentum_rate_cmd)

    return (a_cmd, dL_cmd)


# =============================================================================
# 5. Single-Step Coordination Algorithm
# =============================================================================

def step_closed_loop_dynamics(
    state_curr: ForwardDynamicsState,
    reference: DesiredMotionReference,
    contacts: Sequence[ContactConstraintSpec],
    config: Optional[ClosedLoopControllerConfig] = None,
    frame_index: int = 0,
) -> ClosedLoopFrameTelemetry:
    """Execute a single closed-loop coordination step.

    Execution Flow:
    1. Input validation and feedback control evaluation.
    2. Target wrench construction from Newton-Euler equations.
    3. Contact force optimization solving.
    4. Admissibility gating and policy verification.
    5. Forward dynamics integration with true physical forces.
    6. Assembly of comprehensive frame telemetry.
    """
    cfg = config or ClosedLoopControllerConfig()
    m = state_curr.mass
    com = state_curr.com_position_world
    dt = cfg.dt
    policy = cfg.admissibility_policy

    # 1. Feedback Control Law Evaluation
    a_cmd, dL_cmd = compute_commanded_accelerations(state_curr, reference, cfg)

    # 2. Construct Target Contact Wrench:
    # F_target_contact = m * a_cmd - m * g - sum(F_ext)
    # tau_target_contact = dL_cmd - sum(tau_ext)
    target_wrench = ContactWrenchTarget.from_target_motion(
        mass=m,
        target_linear_acc=a_cmd,
        com_world=com,
        dL_com_dt=dL_cmd,
        gravity_z=cfg.gravity_acceleration_world[2],
        external_forces=reference.external_forces_world,
        external_torques=reference.external_torques_about_com_world,
        gravity_acceleration_world=cfg.gravity_acceleration_world,
    )

    # 3. Contact Force Optimization Solving
    active_contacts = [c for c in contacts if c.is_in_contact]

    if len(active_contacts) == 0:
        # Ballistic free-flight or no active surface contacts
        f_req_norm = vec3_length(target_wrench.target_force_world)
        tau_req_norm = vec3_length(target_wrench.target_torque_world)

        if f_req_norm < 1e-4 and tau_req_norm < 1e-4:
            # Demanded zero contact wrench (e.g. pure free fall): naturally solved with zero force
            sol = ContactForceSolution(
                status=ContactSolverStatus.SOLVED,
                contact_forces={},
                total_contact_force=(0.0, 0.0, 0.0),
                total_contact_torque_about_com=(0.0, 0.0, 0.0),
                force_error_vector=(0.0, 0.0, 0.0),
                force_residual_n=0.0,
                torque_error_vector=(0.0, 0.0, 0.0),
                torque_residual_nm=0.0,
                max_normal_violation_n=0.0,
                max_friction_violation_n=0.0,
                iterations=0,
                computation_time_sec=0.0,
                is_physically_valid=True,
                message="Free flight zero contact wrench naturally satisfied",
                solver_engine="analytical_free_flight",
                optimizer_converged=True,
                optimizer_message="Free flight zero contact wrench naturally satisfied",
            )
            is_control_feasible = True
        else:
            # Non-zero contact wrench demanded in free air (e.g. hover demanded without contact)
            is_control_feasible = False
            sol = ContactForceSolution(
                status=ContactSolverStatus.INFEASIBLE,
                contact_forces={},
                total_contact_force=(0.0, 0.0, 0.0),
                total_contact_torque_about_com=(0.0, 0.0, 0.0),
                force_error_vector=target_wrench.target_force_world,
                force_residual_n=f_req_norm,
                torque_error_vector=target_wrench.target_torque_world,
                torque_residual_nm=tau_req_norm,
                max_normal_violation_n=0.0,
                max_friction_violation_n=0.0,
                iterations=0,
                computation_time_sec=0.0,
                is_physically_valid=True,  # 0 contact force in air is 100% physically valid
                message="Zero active contacts cannot produce required contact wrench",
                solver_engine="zero_contact_check",
                optimizer_converged=False,
                optimizer_message="Zero active contacts cannot produce required contact wrench",
            )
    else:
        # Call Contact Force Solver
        sol = solve_contact_forces(target_wrench, contacts, config=cfg.solver_config)
        is_control_feasible = (sol.status == ContactSolverStatus.SOLVED)

    # 4. Admissibility Gating and Policy Evaluation
    state_next = state_curr
    state_advanced = False
    step_status: ClosedLoopStepStatus
    message = ""

    if sol.status == ContactSolverStatus.INVALID_INPUT:
        is_control_feasible = False
        step_status = ClosedLoopStepStatus.SOLVER_INVALID_INPUT
        message = f"Solver rejected inputs as invalid: {sol.optimizer_message}"

    elif sol.status == ContactSolverStatus.NUMERICAL_FAILURE:
        is_control_feasible = False
        step_status = ClosedLoopStepStatus.SOLVER_NUMERICAL_FAILURE
        message = f"Solver encountered numerical failure: {sol.optimizer_message}"

    elif sol.status == ContactSolverStatus.INFEASIBLE:
        is_control_feasible = False
        if len(active_contacts) == 0:
            # Free air infeasible wrench (e.g. demanding hover)
            if policy.strict_freeze_on_infeasible or not policy.allow_infeasible_zero_force_fallback:
                step_status = ClosedLoopStepStatus.REJECTED_INFEASIBLE
                message = "Strict policy rejected mid-air hover demand"
            else:
                step_status = ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED
                message = "Mid-air hover infeasible: proceeding under natural unassisted free fall"
        else:
            # Ground contacts present, but wrench infeasible (e.g. downward suction force)
            if (
                policy.strict_freeze_on_infeasible
                or not policy.allow_infeasible_zero_force_fallback
                or not sol.is_physically_valid
            ):
                step_status = ClosedLoopStepStatus.REJECTED_INFEASIBLE
                message = f"Contact wrench is provably infeasible: {sol.optimizer_message}"
            else:
                step_status = ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED
                message = f"Contact wrench infeasible: proceeding under valid physical forces ({sol.optimizer_message})"

    elif sol.status == ContactSolverStatus.APPROXIMATE:
        if not sol.is_physically_valid:
            is_control_feasible = False
            step_status = ClosedLoopStepStatus.SOLVER_NUMERICAL_FAILURE
            message = "Approximate solution violated physical unilateral/cone constraints"
        elif (
            sol.force_residual_n <= policy.max_allowable_force_residual
            and sol.torque_residual_nm <= policy.max_allowable_torque_residual
        ):
            if policy.strict_solved_only:
                is_control_feasible = False
                step_status = ClosedLoopStepStatus.REJECTED_APPROXIMATE
                message = "Strict policy rejected APPROXIMATE contact solution"
            else:
                is_control_feasible = True
                step_status = ClosedLoopStepStatus.SUCCESS_APPROXIMATE
                message = (
                    f"Admitted physically valid approximate solution (F_res={sol.force_residual_n:.2f}N, "
                    f"tau_res={sol.torque_residual_nm:.2f}N*m)"
                )
        else:
            is_control_feasible = False
            if policy.strict_freeze_on_infeasible:
                step_status = ClosedLoopStepStatus.REJECTED_APPROXIMATE
                message = (
                    f"Residual exceeds policy bounds (F_res={sol.force_residual_n:.1f}N > "
                    f"{policy.max_allowable_force_residual:.1f}N or tau_res={sol.torque_residual_nm:.1f}N*m > "
                    f"{policy.max_allowable_torque_residual:.1f}N*m)"
                )
            else:
                step_status = ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED
                message = (
                    f"Residual exceeded tolerance, but contact forces are physically valid: "
                    f"proceeding under actual physical forces (F_res={sol.force_residual_n:.1f}N)"
                )

    elif sol.status == ContactSolverStatus.SOLVED:
        if not sol.is_physically_valid:
            is_control_feasible = False
            step_status = ClosedLoopStepStatus.SOLVER_NUMERICAL_FAILURE
            message = "Solved solution had invalid physical flag"
        else:
            is_control_feasible = True
            step_status = ClosedLoopStepStatus.SUCCESS_EXACT
            message = "Solved contact forces exactly satisfied physical wrench target"
    else:
        is_control_feasible = False
        step_status = ClosedLoopStepStatus.SOLVER_NUMERICAL_FAILURE
        message = f"Unhandled solver status: {sol.status}"

    # 5. Forward Dynamics Integration (Only if Admitted)
    actual_forces_map: Dict[str, Vec3] = {}
    actual_net_force: Vec3 = (0.0, 0.0, 0.0)
    actual_net_torque: Vec3 = (0.0, 0.0, 0.0)
    actual_a: Vec3 = (0.0, 0.0, 0.0)
    actual_dL: Vec3 = (0.0, 0.0, 0.0)
    is_valid_step = False

    should_integrate = step_status in (
        ClosedLoopStepStatus.SUCCESS_EXACT,
        ClosedLoopStepStatus.SUCCESS_APPROXIMATE,
        ClosedLoopStepStatus.CONTROL_INFEASIBLE_PHYSICS_ADVANCED,
    )

    if should_integrate:
        # Convert contact forces into ContactForcePoint collection
        step_in = ForwardDynamicsStepInput.from_solution_and_specs(
            solution=sol,
            specs=contacts,
            external_forces_world=reference.external_forces_world,
            external_torques_about_com_world=reference.external_torques_about_com_world,
            gravity_acceleration_world=cfg.gravity_acceleration_world,
            dt=dt,
            target_linear_acceleration_world=a_cmd,
            target_angular_momentum_rate_world=dL_cmd,
        )

        res = integrate_forward_dynamics_single_step(state_curr, step_in, config=cfg.forward_dynamics_config)

        if res.status == ForwardDynamicsStatus.SUCCESS:
            state_next = res.state_next
            state_advanced = True
            is_valid_step = True
            actual_forces_map = {c.contact_id: sol.contact_forces.get(c.contact_id, (0.0, 0.0, 0.0)) for c in contacts}
            actual_net_force = res.net_force_world
            actual_net_torque = res.net_torque_about_com_world
            actual_a = res.actual_linear_acceleration_world
            actual_dL = res.actual_angular_momentum_rate_world
        else:
            # Forward dynamics integration failed
            state_next = state_curr  # Strict failure atomicity
            state_advanced = False
            step_status = ClosedLoopStepStatus.INTEGRATION_FAILURE
            is_valid_step = False
            message = f"Forward dynamics integration failed: {res.message}"
    else:
        # State advancement was rejected
        state_next = state_curr
        state_advanced = False
        is_valid_step = False

    # 6. Tracking Error Evaluation
    pos_err = None
    if reference.target_com_position_world is not None:
        pos_err = vec3_sub(state_next.com_position_world, reference.target_com_position_world)

    vel_err = None
    if reference.target_com_velocity_world is not None:
        vel_err = vec3_sub(state_next.com_velocity_world, reference.target_com_velocity_world)

    err_a = vec3_sub(actual_a, a_cmd)
    err_dL = vec3_sub(actual_dL, dL_cmd)

    return ClosedLoopFrameTelemetry(
        frame_index=frame_index,
        timestamp=state_curr.timestamp,
        state_current=state_curr,
        state_next=state_next,
        motion_reference=reference,
        commanded_linear_acceleration_world=a_cmd,
        commanded_angular_momentum_rate_world=dL_cmd,
        target_contact_wrench_force_world=target_wrench.target_force_world,
        target_contact_wrench_torque_world=target_wrench.target_torque_world,
        solver_status=sol.status,
        solver_is_physically_valid=sol.is_physically_valid,
        solver_force_residual_n=sol.force_residual_n,
        solver_torque_residual_nm=sol.torque_residual_nm,
        actual_contact_forces=actual_forces_map,
        actual_net_force_world=actual_net_force,
        actual_net_torque_about_com_world=actual_net_torque,
        actual_linear_acceleration_world=actual_a,
        actual_angular_momentum_rate_world=actual_dL,
        step_status=step_status,
        is_physically_valid=is_valid_step,
        state_advanced=state_advanced,
        is_control_feasible=is_control_feasible,
        tracking_error_position=pos_err,
        tracking_error_velocity=vel_err,
        tracking_error_linear_acc=err_a,
        tracking_error_angular_momentum_rate=err_dL,
        message=message,
    )


# =============================================================================
# 6. Multi-Frame Closed-Loop Dynamics Coordinator
# =============================================================================

class ClosedLoopDynamicsCoordinator:
    """Manages multi-frame closed-loop dynamics simulation and state history.

    Coordinates:
    - Step-by-step state propagation: state_{k+1} is fed into frame k+1 as state_k.
    - Flexible scheduling for references and environmental contact constraints.
    - Deterministic reproducibility and telemetry capture.
    """

    def __init__(self, config: Optional[ClosedLoopControllerConfig] = None):
        self.config = config or ClosedLoopControllerConfig()

    def step(
        self,
        state_curr: ForwardDynamicsState,
        reference: DesiredMotionReference,
        contacts: Sequence[ContactConstraintSpec],
        frame_index: int = 0,
    ) -> ClosedLoopFrameTelemetry:
        """Execute a single closed-loop coordination step."""
        return step_closed_loop_dynamics(
            state_curr=state_curr,
            reference=reference,
            contacts=contacts,
            config=self.config,
            frame_index=frame_index,
        )

    def simulate(
        self,
        initial_state: ForwardDynamicsState,
        reference_schedule: Union[
            DesiredMotionReference,
            Sequence[DesiredMotionReference],
            Callable[[int, float, ForwardDynamicsState], DesiredMotionReference],
        ],
        contact_schedule: Union[
            Sequence[ContactConstraintSpec],
            Sequence[Sequence[ContactConstraintSpec]],
            Callable[[int, float, ForwardDynamicsState], Sequence[ContactConstraintSpec]],
        ],
        num_steps: int,
        fail_fast: bool = False,
    ) -> ClosedLoopSimulationTrajectory:
        """Simulate a continuous multi-frame trajectory under closed-loop control.

        Parameters:
        - initial_state: Rigorous ForwardDynamicsState at frame 0.
        - reference_schedule: Constant reference, list of references per frame, or dynamic generator callable.
        - contact_schedule: Constant contacts, list of contacts per frame, or dynamic generator callable.
        - num_steps: Total number of frames to integrate.
        - fail_fast: If True, halts simulation on the first unadmitted or failed step.
        """
        if num_steps <= 0:
            raise ValueError(f"num_steps must be strictly positive, got {num_steps}")

        dt = self.config.dt
        telemetry_records: List[ClosedLoopFrameTelemetry] = []
        curr_state = initial_state
        all_advanced = True

        for k in range(num_steps):
            t_curr = curr_state.timestamp

            # 1. Resolve Motion Reference
            if callable(reference_schedule):
                ref_k = reference_schedule(k, t_curr, curr_state)
            elif isinstance(reference_schedule, Sequence):
                idx = min(k, len(reference_schedule) - 1)
                ref_k = reference_schedule[idx]
            else:
                ref_k = reference_schedule

            # 2. Resolve Contact Constraints
            if callable(contact_schedule):
                contacts_k = contact_schedule(k, t_curr, curr_state)
            elif isinstance(contact_schedule, Sequence) and len(contact_schedule) > 0 and isinstance(contact_schedule[0], (list, tuple)):
                idx = min(k, len(contact_schedule) - 1)
                contacts_k = contact_schedule[idx]
            else:
                contacts_k = contact_schedule  # type: ignore

            # 3. Step Coordinator
            telem = self.step(
                state_curr=curr_state,
                reference=ref_k,
                contacts=contacts_k,
                frame_index=k,
            )
            telemetry_records.append(telem)

            if telem.state_advanced:
                curr_state = telem.state_next
            else:
                all_advanced = False
                if fail_fast:
                    break

        total_time = len(telemetry_records) * dt
        return ClosedLoopSimulationTrajectory(
            frames=tuple(telemetry_records),
            initial_state=initial_state,
            final_state=curr_state,
            dt=dt,
            total_time=total_time,
            all_advanced=all_advanced,
        )
