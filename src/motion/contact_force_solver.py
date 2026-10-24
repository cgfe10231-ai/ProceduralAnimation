"""Multi-Contact Force Solver and Physical Constraint Allocation (Task 6G-D-B).

Implements a mathematically rigorous, decoupled 3D contact force allocation solver
for humanoid procedural animation:
- Formulates the inverse contact wrench distribution problem:
    Find contact forces f = [F_1, F_2, ..., F_N]^T (3N x 1)
    to satisfy:
        A * f ≈ w_target = [F_target, tau_target_com]^T (6 x 1)
    subject to hard physical contact constraints on each contact i:
        1. Contact validity: If is_in_contact == False, F_i = 0.
        2. Unilateral normal contact: F_n,i = F_i . n_i >= 0 (no tensile pull).
        3. 3D Coulomb friction cone: ||F_t,i|| <= mu_i * F_n,i (where F_t,i = F_i - F_n,i * n_i).
        4. Normal force limits: min_normal_force <= F_n,i <= max_normal_force.

- Physical Separation & Principles:
    * Distinguishes target motion wrench, gravity compensation, and external disturbance forces:
        F_target_contact = m * a_target - F_gravity - sum(F_other)
        tau_target_contact = dL_com/dt - sum(tau_other)
    * Distinguishes forward kinematics/dynamics from inverse constrained allocation and independent physical verification.
    * Reference point for torques is strictly the Whole-Body Center of Mass (CoM).
    * Coordinate frame: Unified World Coordinate System (+Z Up, Ground Z=0.0m, Right-Handed).
    * Units: m, kg, N, N*m, s, m/s^2.

- Dual Optimization Engine Architecture:
    * Engine 1 (SLSQP): Sequential Least Squares Programming via SciPy when available.
    * Engine 2 (SPG Native): Self-contained Spectral Projected Gradient solver with exact
      closed-form 3D second-order Euclidean friction cone projection. Runs in pure Python/NumPy
      without external optimizer dependencies (works inside Blender headless and standalone).

- Zero Pose Mutation:
    * Pure mathematical solver. Does NOT directly mutate Blender bones, Rig IK, WholeBodyController,
      or KinematicBridgeExecutor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    np = None  # type: ignore
    HAVE_NUMPY = False

try:
    from scipy.optimize import minimize as scipy_minimize
    HAVE_SCIPY = True
except ImportError:
    scipy_minimize = None  # type: ignore
    HAVE_SCIPY = False

from src.motion.contact_dynamics import (
    MultiContactDynamics,
    SingleContactDynamics,
    Vec3,
    _to_vec3,
    vec3_add,
    vec3_cross,
    vec3_dot,
    vec3_length,
    vec3_normalize,
    vec3_scale,
    vec3_sub,
)

try:
    from src.scene.environment_query import (
        DynamicsEnvironmentQuery,
        SurfaceQueryResult,
    )
except ImportError:
    DynamicsEnvironmentQuery = Any  # type: ignore
    SurfaceQueryResult = Any        # type: ignore


# =============================================================================
# 1. Status & Data Contracts
# =============================================================================

class ContactSolverStatus(str, Enum):
    """Detailed mathematical convergence and feasibility state of the Contact Force Solver."""
    SOLVED = "solved"                        # Converged; hard constraints satisfied; residuals <= tolerance
    APPROXIMATE = "approximate"              # Physical constraints satisfied; target wrench partially satisfied
    INFEASIBLE = "infeasible"                # Provably impossible target under physical contact constraints
    INVALID_INPUT = "invalid_input"          # Degenerate normal, NaN/Inf, negative mass, or illegal inputs
    NUMERICAL_FAILURE = "numerical_failure"  # Numerical breakdown or solver divergence


@dataclass(frozen=True)
class ContactConstraintSpec:
    """Specification of an environmental contact point and its physical constraints.

    Coordinates & Units:
    - contact_id: Descriptive unique identifier for this contact (e.g. 'foot_L', 'foot_R').
    - contact_point_world: World-space position p_c (m).
    - surface_normal_world: Unit outward normal pointing away from contact surface into free space.
    - friction_coeff: Static Coulomb friction coefficient mu >= 0 (dimensionless).
    - is_in_contact: True if body point is in physical contact with surface (within tolerance).
    - allows_regular_support: Informational indicator of foot-support viability (e.g. ground vs wall).
    - min_normal_force: Minimum required normal force F_n >= min_normal_force >= 0 (N).
    - max_normal_force: Maximum allowable normal force F_n <= max_normal_force (N).
    - surface_id: Unique identifier of environmental surface if bound, or empty string.
    - surface_distance: True measured signed distance to surface (m) if available, or None if unmeasured.
    - contact_tolerance: Permissible clearance gap or penetration threshold for contact (m).
    """
    contact_id: str
    contact_point_world: Vec3
    surface_normal_world: Vec3
    friction_coeff: float = 0.65
    is_in_contact: bool = True
    allows_regular_support: bool = True
    min_normal_force: float = 0.0
    max_normal_force: float = float("inf")
    surface_id: str = ""
    surface_distance: Optional[float] = None
    contact_tolerance: float = 0.02

    def __post_init__(self):
        # Validate spatial coordinates and vectors
        p = _to_vec3(self.contact_point_world, "contact_point_world")
        norm = _to_vec3(self.surface_normal_world, "surface_normal_world")
        n_len = vec3_length(norm)
        if n_len < 1e-6:
            raise ValueError(f"surface_normal_world cannot be degenerate/zero, got {norm}")
        norm = vec3_normalize(norm)

        object.__setattr__(self, "contact_point_world", p)
        object.__setattr__(self, "surface_normal_world", norm)

        if math.isnan(self.friction_coeff) or math.isinf(self.friction_coeff) or self.friction_coeff < 0.0:
            raise ValueError(f"friction_coeff must be finite and non-negative, got {self.friction_coeff}")

        if math.isnan(self.min_normal_force) or self.min_normal_force < 0.0:
            raise ValueError(f"min_normal_force must be non-negative, got {self.min_normal_force}")

        if math.isnan(self.max_normal_force) or self.max_normal_force < self.min_normal_force:
            raise ValueError(
                f"max_normal_force ({self.max_normal_force}) cannot be less than min_normal_force ({self.min_normal_force})"
            )

        if self.surface_distance is not None:
            if math.isnan(self.surface_distance) or math.isinf(self.surface_distance):
                raise ValueError(f"surface_distance must be finite when provided, got {self.surface_distance}")

        if math.isnan(self.contact_tolerance) or math.isinf(self.contact_tolerance) or self.contact_tolerance <= 0.0:
            raise ValueError(f"contact_tolerance must be strictly positive and finite, got {self.contact_tolerance}")


@dataclass(frozen=True)
class ContactWrenchTarget:
    """Target 6D generalized contact wrench (force and torque) in World Space.

    Units:
    - target_force_world: Total contact force F_target in World Space (N).
    - target_torque_world: Total contact torque tau_target about com_world (N*m).
    - com_world: Reference point (Whole-Body Center of Mass) (m).
    """
    target_force_world: Vec3
    target_torque_world: Vec3
    com_world: Vec3

    def __post_init__(self):
        object.__setattr__(self, "target_force_world", _to_vec3(self.target_force_world, "target_force_world"))
        object.__setattr__(self, "target_torque_world", _to_vec3(self.target_torque_world, "target_torque_world"))
        object.__setattr__(self, "com_world", _to_vec3(self.com_world, "com_world"))

    @classmethod
    def from_target_motion(
        cls,
        mass: float,
        target_linear_acc: Vec3,
        com_world: Vec3,
        dL_com_dt: Vec3 = (0.0, 0.0, 0.0),
        gravity_z: float = -9.81,
        external_forces: Sequence[Vec3] = (),
        external_torques: Sequence[Vec3] = (),
    ) -> ContactWrenchTarget:
        """Construct target contact wrench from desired acceleration, gravity, and external disturbances.

        Newton-Euler equations of motion:
            m * a_target = F_contact + F_gravity + sum(F_ext)
            dL_com/dt = tau_contact + sum(tau_ext)

        Therefore:
            F_target_contact = m * a_target - F_gravity - sum(F_ext)
            tau_target_contact = dL_com/dt - sum(tau_ext)
        """
        if math.isnan(mass) or math.isinf(mass) or mass <= 0.0:
            raise ValueError(f"mass must be strictly positive and finite, got {mass}")
        if math.isnan(gravity_z) or math.isinf(gravity_z):
            raise ValueError(f"gravity_z must be finite, got {gravity_z}")

        acc = _to_vec3(target_linear_acc, "target_linear_acc")
        dL = _to_vec3(dL_com_dt, "dL_com_dt")
        com = _to_vec3(com_world, "com_world")

        # Gravity force: [0, 0, mass * gravity_z]
        f_grav: Vec3 = (0.0, 0.0, mass * gravity_z)

        # Total required net force: m * a
        f_net: Vec3 = vec3_scale(acc, mass)

        # Target contact force: F_net - F_grav - sum(F_ext)
        f_contact = vec3_sub(f_net, f_grav)
        for f_ext in external_forces:
            f_contact = vec3_sub(f_contact, _to_vec3(f_ext, "external_force"))

        # Target contact torque: dL/dt - sum(tau_ext)
        tau_contact = dL
        for t_ext in external_torques:
            tau_contact = vec3_sub(tau_contact, _to_vec3(t_ext, "external_torque"))

        return cls(
            target_force_world=f_contact,
            target_torque_world=tau_contact,
            com_world=com,
        )


@dataclass(frozen=True)
class ContactSolverConfig:
    """Tolerances, weights, and algorithm configuration for contact force allocation."""
    force_tolerance_n: float = 0.05        # 50 mN force tolerance
    torque_tolerance_nm: float = 0.05      # 50 mN*m torque tolerance
    constraint_tolerance: float = 1e-4     # 0.1 mN constraint violation margin
    weight_force: float = 1.0              # Objective weight for force tracking
    weight_torque: float = 1.0             # Objective weight for torque tracking
    regularization_weight: float = 1e-6    # Minimum-norm force regularization alpha
    max_iterations: int = 1000             # Maximum solver iterations
    method: str = "auto"                   # 'auto', 'slsqp', 'spg'
    enable_fallback: bool = True           # Allow fallback to SPG on SLSQP failure

    def __post_init__(self):
        if self.force_tolerance_n <= 0.0 or math.isnan(self.force_tolerance_n):
            raise ValueError(f"force_tolerance_n must be > 0, got {self.force_tolerance_n}")
        if self.torque_tolerance_nm <= 0.0 or math.isnan(self.torque_tolerance_nm):
            raise ValueError(f"torque_tolerance_nm must be > 0, got {self.torque_tolerance_nm}")
        if self.constraint_tolerance < 0.0 or math.isnan(self.constraint_tolerance):
            raise ValueError(f"constraint_tolerance must be >= 0, got {self.constraint_tolerance}")
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")


@dataclass
class ContactForceSolution:
    """Complete numerical result of contact force allocation and constraint satisfaction."""
    status: ContactSolverStatus
    contact_forces: Dict[str, Vec3]
    total_contact_force: Vec3
    total_contact_torque_about_com: Vec3
    force_error_vector: Vec3
    force_residual_n: float
    torque_error_vector: Vec3
    torque_residual_nm: float
    max_normal_violation_n: float
    max_friction_violation_n: float
    iterations: int
    computation_time_sec: float
    is_physically_valid: bool
    message: str
    solver_engine: str = "none"
    optimizer_converged: bool = False
    optimizer_message: str = ""
    fallback_occurred: bool = False


# =============================================================================
# 2. Linear Contact Mapping Matrix A (w = A * f)
# =============================================================================

def build_contact_mapping_matrix(
    contacts: Sequence[ContactConstraintSpec],
    com_world: Vec3,
) -> List[List[float]]:
    """Build the 6 x 3N linear contact grasp/mapping matrix A.

    Maps stacked 3D contact forces f = [F_1, F_2, ..., F_N]^T (3N x 1) to the 6D
    net contact wrench w = [F_total, tau_total_com]^T (6 x 1) about com_world:
        w = A * f

    Each 6x3 sub-block A_i corresponding to contact i is:
        A_i = [    I_3x3    ]
              [  [r_i]_x    ]
    where r_i = p_i - com_world, and [r_i]_x is the standard 3x3 skew-symmetric
    cross-product matrix such that [r_i]_x * F_i = r_i x F_i:
        [r_i]_x = [   0    -r_z   r_y  ]
                  [  r_z     0   -r_x  ]
                  [ -r_y    r_x    0   ]
    """
    com = _to_vec3(com_world, "com_world")
    N = len(contacts)
    # Initialize 6 x 3N matrix
    A = [[0.0 for _ in range(3 * N)] for _ in range(6)]

    for i, c in enumerate(contacts):
        p = c.contact_point_world
        rx = p[0] - com[0]
        ry = p[1] - com[1]
        rz = p[2] - com[2]

        col_base = 3 * i

        # Top 3x3: Identity (Forces sum directly into F_total)
        A[0][col_base + 0] = 1.0
        A[1][col_base + 1] = 1.0
        A[2][col_base + 2] = 1.0

        # Bottom 3x3: [r_i]_x (Skew-symmetric cross product matrix)
        # tau_x = ry * Fz - rz * Fy
        A[3][col_base + 1] = -rz
        A[3][col_base + 2] = ry

        # tau_y = rz * Fx - rx * Fz
        A[4][col_base + 0] = rz
        A[4][col_base + 2] = -rx

        # tau_z = rx * Fy - ry * Fx
        A[5][col_base + 0] = -ry
        A[5][col_base + 1] = rx

    return A


def contact_mapping_multiply(
    A: Sequence[Sequence[float]],
    forces: Sequence[Vec3],
) -> Tuple[Vec3, Vec3]:
    """Multiply the 6 x 3N mapping matrix A by stacked contact forces f.

    Returns:
        (total_force_world, total_torque_about_com)
    """
    N = len(forces)
    if len(A) != 6:
        raise ValueError(f"A must have 6 rows, got {len(A)}")
    if any(len(row) != 3 * N for row in A):
        raise ValueError(f"Each row of A must have length {3 * N}")

    f_flat: List[float] = []
    for F in forces:
        f_flat.extend([float(F[0]), float(F[1]), float(F[2])])

    w = [0.0] * 6
    for r in range(6):
        w[r] = sum(A[r][c] * f_flat[c] for c in range(3 * N))

    return (w[0], w[1], w[2]), (w[3], w[4], w[5])


# =============================================================================
# 3. Exact 3D Circular Friction Cone Projection
# =============================================================================

def project_to_friction_cone(
    F: Vec3,
    surface_normal: Vec3,
    friction_coeff: float,
    min_normal_force: float = 0.0,
    max_normal_force: float = float("inf"),
) -> Vec3:
    """Project a 3D force vector onto the exact 3D circular Coulomb friction cone.

    Cone definition:
        K = { F in R^3 | F_n = F . n in [min_Fn, max_Fn], ||F_t|| <= mu * F_n }
    where F_t = F - F_n * n.

    Properties:
    - 100% exact closed-form Euclidean projection (no polyhedral approximation).
    - Preserves tangency direction and handles mu == 0 seamlessly.
    - True orthogonal closest point under finite normal lower and upper bounds.
    - Guaranteed non-expansive, continuous, idempotent (P(P(x)) = P(x)),
      and strictly satisfies F_n in [min_normal_force, max_normal_force].
    """
    n = surface_normal
    fn = vec3_dot(F, n)
    ft_vec = vec3_sub(F, vec3_scale(n, fn))
    ft = vec3_length(ft_vec)

    mu = max(0.0, float(friction_coeff))
    min_fn = max(0.0, float(min_normal_force))
    max_fn = max(min_fn, float(max_normal_force))

    # 1. Point is already strictly inside the feasible bounded cone
    if min_fn <= fn <= max_fn and ft <= mu * fn:
        return F

    # 2. Candidate projections onto boundary segments of the convex planar region
    #    Omega = { (f_n, f_t) | f_n in [min_fn, max_fn], 0 <= f_t <= mu * f_n }
    candidates: List[Tuple[float, float]] = []

    # Candidate A: Slant boundary f_t = mu * f_n for f_n in [min_fn, max_fn]
    if mu > 0.0:
        denom = 1.0 + mu * mu
        fn_slant = (fn + mu * ft) / denom
        fn_slant_clamped = max(min_fn, min(fn_slant, max_fn))
        ft_slant_clamped = mu * fn_slant_clamped
        candidates.append((fn_slant_clamped, ft_slant_clamped))
    else:
        # mu == 0: slant line is the segment [min_fn, max_fn] on the f_n axis (f_t = 0)
        fn_clamped = max(min_fn, min(fn, max_fn))
        candidates.append((fn_clamped, 0.0))

    # Candidate B: Upper normal cap f_n = max_fn for f_t in [0, mu * max_fn]
    if not math.isinf(max_fn):
        ft_upper = max(0.0, min(ft, mu * max_fn))
        candidates.append((max_fn, ft_upper))

    # Candidate C: Lower normal cap f_n = min_fn for f_t in [0, mu * min_fn]
    ft_lower = max(0.0, min(ft, mu * min_fn))
    candidates.append((min_fn, ft_lower))

    # Candidate D: Bottom axis f_t = 0 for f_n in [min_fn, max_fn]
    fn_axis = max(min_fn, min(fn, max_fn))
    candidates.append((fn_axis, 0.0))

    # Select candidate (best_fn, best_ft) minimizing Euclidean distance (fn - c_fn)^2 + (ft - c_ft)^2
    best_fn, best_ft = candidates[0]
    best_dist_sq = (fn - best_fn) ** 2 + (ft - best_ft) ** 2
    for c_fn, c_ft in candidates[1:]:
        dist_sq = (fn - c_fn) ** 2 + (ft - c_ft) ** 2
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_fn, best_ft = c_fn, c_ft

    # Reconstruct 3D force vector preserving tangential direction
    if ft > 1e-12 and best_ft > 1e-12:
        dir_t = vec3_scale(ft_vec, 1.0 / ft)
        return vec3_add(vec3_scale(dir_t, best_ft), vec3_scale(n, best_fn))
    else:
        return vec3_scale(n, best_fn)


# =============================================================================
# 4. Solvers: SLSQP & Native Spectral Projected Gradient (SPG)
# =============================================================================

def _solve_with_slsqp(
    target: ContactWrenchTarget,
    active_contacts: Sequence[ContactConstraintSpec],
    config: ContactSolverConfig,
) -> Tuple[Dict[str, Vec3], int, bool]:
    """Solve constrained allocation QP using SciPy SLSQP with exact circular cone constraints."""
    if not HAVE_SCIPY or not HAVE_NUMPY:
        raise RuntimeError("SciPy and NumPy must be installed to use SLSQP solver")

    N = len(active_contacts)
    com = target.com_world
    w_target = np.array([
        target.target_force_world[0],
        target.target_force_world[1],
        target.target_force_world[2],
        target.target_torque_world[0],
        target.target_torque_world[1],
        target.target_torque_world[2],
    ], dtype=np.float64)

    # Build A matrix
    A_list = build_contact_mapping_matrix(active_contacts, com)
    A = np.array(A_list, dtype=np.float64)  # 6 x 3N

    w_F = config.weight_force
    w_tau = config.weight_torque
    alpha = config.regularization_weight

    W = np.diag([w_F, w_F, w_F, w_tau, w_tau, w_tau])

    def objective(f: np.ndarray) -> float:
        res = A @ f - w_target
        w_cost = 0.5 * float(res.T @ W @ res)
        reg_cost = 0.5 * alpha * float(np.sum(f * f))
        return w_cost + reg_cost

    def objective_grad(f: np.ndarray) -> np.ndarray:
        res = A @ f - w_target
        return A.T @ (W @ res) + alpha * f

    constraints = []
    for i, c in enumerate(active_contacts):
        n_vec = np.array(c.surface_normal_world, dtype=np.float64)
        mu = c.friction_coeff
        min_fn = c.min_normal_force
        max_fn = c.max_normal_force

        # 1. Normal force lower bound: F_i . n - min_fn >= 0
        def con_fn_lower(f: np.ndarray, idx=i, n_v=n_vec, min_f=min_fn) -> float:
            fi = f[3*idx:3*idx+3]
            return float(np.dot(fi, n_v) - min_f)
        constraints.append({'type': 'ineq', 'fun': con_fn_lower})

        # 2. Normal force upper bound (if finite): max_fn - F_i . n >= 0
        if not math.isinf(max_fn):
            def con_fn_upper(f: np.ndarray, idx=i, n_v=n_vec, max_f=max_fn) -> float:
                fi = f[3*idx:3*idx+3]
                return float(max_f - np.dot(fi, n_v))
            constraints.append({'type': 'ineq', 'fun': con_fn_upper})

        # 3. Exact 3D circular Coulomb cone: mu * (F_i . n) - ||F_t,i|| >= 0
        def con_cone(f: np.ndarray, idx=i, n_v=n_vec, m=mu) -> float:
            fi = f[3*idx:3*idx+3]
            fn = float(np.dot(fi, n_v))
            ft_vec = fi - fn * n_v
            ft = float(np.linalg.norm(ft_vec))
            return float(m * fn - ft)
        constraints.append({'type': 'ineq', 'fun': con_cone})

    # Symmetric initial guess: divide target normal force equally across upward contacts
    f0 = np.zeros(3 * N, dtype=np.float64)
    target_fz = max(0.0, target.target_force_world[2])
    for i, c in enumerate(active_contacts):
        f0[3*i:3*i+3] = np.array(c.surface_normal_world) * (target_fz / max(1, N))

    opt_res = scipy_minimize(
        objective,
        f0,
        jac=objective_grad,
        constraints=constraints,
        method="SLSQP",
        options={"ftol": 1e-9, "maxiter": config.max_iterations},
    )

    f_sol = opt_res.x
    sol_dict: Dict[str, Vec3] = {}
    for i, c in enumerate(active_contacts):
        fi = (float(f_sol[3*i]), float(f_sol[3*i+1]), float(f_sol[3*i+2]))
        # Cleanly project to guarantee zero numerical leakage on friction cone boundary
        fi_proj = project_to_friction_cone(
            fi, c.surface_normal_world, c.friction_coeff, c.min_normal_force, c.max_normal_force
        )
        sol_dict[c.contact_id] = fi_proj

    nit = int(getattr(opt_res, "nit", 0))
    success = bool(getattr(opt_res, "success", False))
    msg = str(getattr(opt_res, "message", ""))
    return sol_dict, nit, success, msg


def _solve_with_spg(
    target: ContactWrenchTarget,
    active_contacts: Sequence[ContactConstraintSpec],
    config: ContactSolverConfig,
) -> Tuple[Dict[str, Vec3], int, bool, str]:
    """Solve constrained allocation QP using Native Spectral Projected Gradient (SPG).

    Pure Python/NumPy implementation:
    - Exactly projects onto circular friction cone at every iteration.
    - Uses adaptive Barzilai-Borwein spectral step size with projected gradient descent.
    - Zero external optimizer dependencies.
    """
    N = len(active_contacts)
    com = target.com_world
    com_x, com_y, com_z = com

    r_vecs: List[Vec3] = []
    normals: List[Vec3] = []
    mus: List[float] = []
    min_fns: List[float] = []
    max_fns: List[float] = []

    for c in active_contacts:
        p = c.contact_point_world
        r_vecs.append((p[0] - com_x, p[1] - com_y, p[2] - com_z))
        normals.append(c.surface_normal_world)
        mus.append(c.friction_coeff)
        min_fns.append(c.min_normal_force)
        max_fns.append(c.max_normal_force)

    # Initial symmetric guess
    target_fz = max(0.0, target.target_force_world[2])
    init_share = target_fz / max(1, N)
    forces: List[Vec3] = [
        project_to_friction_cone(
            vec3_scale(normals[i], init_share),
            normals[i],
            mus[i],
            min_fns[i],
            max_fns[i],
        )
        for i in range(N)
    ]

    w_F = config.weight_force
    w_tau = config.weight_torque
    alpha = config.regularization_weight

    def evaluate_gradient(F_curr: Sequence[Vec3]) -> Tuple[List[Vec3], Vec3, Vec3, float, float]:
        # Compute net force
        fx_tot = sum(f[0] for f in F_curr)
        fy_tot = sum(f[1] for f in F_curr)
        fz_tot = sum(f[2] for f in F_curr)
        e_F = (
            fx_tot - target.target_force_world[0],
            fy_tot - target.target_force_world[1],
            fz_tot - target.target_force_world[2],
        )

        # Compute net torque
        tx_tot, ty_tot, tz_tot = 0.0, 0.0, 0.0
        for i in range(N):
            ti = vec3_cross(r_vecs[i], F_curr[i])
            tx_tot += ti[0]
            ty_tot += ti[1]
            tz_tot += ti[2]
        e_tau = (
            tx_tot - target.target_torque_world[0],
            ty_tot - target.target_torque_world[1],
            tz_tot - target.target_torque_world[2],
        )

        grad: List[Vec3] = []
        for i in range(N):
            # Gradient with respect to F_i:
            # grad_F = w_F * e_F
            # grad_tau = w_tau * (e_tau x r_vecs[i])
            g_tau = vec3_cross(e_tau, r_vecs[i])
            g_i = (
                w_F * e_F[0] + w_tau * g_tau[0] + alpha * F_curr[i][0],
                w_F * e_F[1] + w_tau * g_tau[1] + alpha * F_curr[i][1],
                w_F * e_F[2] + w_tau * g_tau[2] + alpha * F_curr[i][2],
            )
            grad.append(g_i)

        res_F = vec3_length(e_F)
        res_tau = vec3_length(e_tau)
        return grad, e_F, e_tau, res_F, res_tau

    grad, e_F, e_tau, res_F, res_tau = evaluate_gradient(forces)
    alpha_bb = 0.005
    converged = False

    for it in range(config.max_iterations):
        if res_F <= config.force_tolerance_n and res_tau <= config.torque_tolerance_nm:
            converged = True
            break

        # Projected gradient step
        forces_trial: List[Vec3] = []
        for i in range(N):
            step_i = (
                forces[i][0] - alpha_bb * grad[i][0],
                forces[i][1] - alpha_bb * grad[i][1],
                forces[i][2] - alpha_bb * grad[i][2],
            )
            forces_trial.append(
                project_to_friction_cone(step_i, normals[i], mus[i], min_fns[i], max_fns[i])
            )

        grad_next, e_F_next, e_tau_next, res_F_next, res_tau_next = evaluate_gradient(forces_trial)

        # Check for NaN / Inf in residuals
        if not (math.isfinite(res_F_next) and math.isfinite(res_tau_next)):
            sol_dict = {c.contact_id: forces_trial[i] for i, c in enumerate(active_contacts)}
            return sol_dict, it + 1, False, f"SPG encountered non-finite residuals at iteration {it + 1}"

        # Barzilai-Borwein spectral step update
        s_dot_y = 0.0
        s_dot_s = 0.0
        for i in range(N):
            for k in range(3):
                sk = forces_trial[i][k] - forces[i][k]
                yk = grad_next[i][k] - grad[i][k]
                s_dot_y += sk * yk
                s_dot_s += sk * sk

        if s_dot_y > 1e-12:
            alpha_bb = min(max(s_dot_s / s_dot_y, 1e-5), 2.0)
        else:
            alpha_bb = 0.005

        forces = forces_trial
        grad = grad_next
        res_F = res_F_next
        res_tau = res_tau_next

    sol_dict: Dict[str, Vec3] = {}
    for i, c in enumerate(active_contacts):
        sol_dict[c.contact_id] = forces[i]

    iters_done = it + 1
    if converged:
        spg_msg = f"SPG converged in {iters_done} iterations (res_F={res_F:.4f}N, res_tau={res_tau:.4f}N*m)"
    else:
        spg_msg = f"SPG reached maximum iteration limit ({config.max_iterations}) without reaching tolerance (res_F={res_F:.4f}N, res_tau={res_tau:.4f}N*m)"

    return sol_dict, iters_done, converged, spg_msg


# =============================================================================
# 5. Feasibility Analysis & Main Solver Entry
# =============================================================================

def _check_a_priori_infeasibility(
    target: ContactWrenchTarget,
    active_contacts: Sequence[ContactConstraintSpec],
    tol: float = 1e-4,
) -> Optional[Tuple[ContactSolverStatus, str]]:
    """Detect strictly mathematically or physically provable infeasibilities before solving."""
    # 1. Zero contacts but non-zero target wrench
    if len(active_contacts) == 0:
        f_len = vec3_length(target.target_force_world)
        tau_len = vec3_length(target.target_torque_world)
        if f_len <= tol and tau_len <= tol:
            return None  # Feasible zero equilibrium in free flight
        return (
            ContactSolverStatus.INFEASIBLE,
            f"Zero active contacts cannot produce non-zero wrench: ||F||={f_len:.3f}N, ||tau||={tau_len:.3f}N*m"
        )

    # 2. Strictly horizontal upward ground contacts cannot provide tensile downward pull
    # When ALL contact normals are strictly vertical (n = [0, 0, 1]), normal force F_n = F_z >= 0,
    # and all tangential friction forces lie strictly in the horizontal X-Y plane (t_z == 0).
    # Thus F_z_total = sum(F_n_i) >= 0 is mathematically non-negative.
    # Note: If any contact has an inclined normal (e.g. slope, ramp, wall), tangential friction forces
    # can possess negative Z components (e.g. high friction downhill pushing), which is not provably
    # infeasible a priori; those are deferred to the numerical optimizer.
    if all(
        abs(c.surface_normal_world[0]) < 1e-6 and
        abs(c.surface_normal_world[1]) < 1e-6 and
        c.surface_normal_world[2] > 0.999
        for c in active_contacts
    ):
        if target.target_force_world[2] < -tol:
            return (
                ContactSolverStatus.INFEASIBLE,
                f"Tensile pull violation: strictly horizontal upward ground contacts cannot pull downwards (F_target_z={target.target_force_world[2]:.3f}N < 0)"
            )

    return None


def solve_contact_forces(
    target: ContactWrenchTarget,
    contacts: Sequence[ContactConstraintSpec],
    config: Optional[ContactSolverConfig] = None,
) -> ContactForceSolution:
    """Solve the multi-contact force allocation problem under 3D Coulomb friction cone constraints.

    Parameters:
        target: Target 6D contact wrench (force and torque about CoM) in World Space.
        contacts: Sequence of ContactConstraintSpec for all potential contact points.
        config: Optional configuration settings and tolerances.

    Returns:
        ContactForceSolution detailing individual forces, residuals, violations, and status.
    """
    t0 = time.perf_counter()
    if config is None:
        config = ContactSolverConfig()

    # -------------------------------------------------------------------------
    # 1. Robust Input Validation
    # -------------------------------------------------------------------------
    try:
        # Check target values for finiteness
        for val in target.target_force_world + target.target_torque_world + target.com_world:
            if math.isnan(val) or math.isinf(val):
                raise ValueError(f"Target contains non-finite values: {val}")

        seen_contact_ids = set()
        for c in contacts:
            if not isinstance(c.contact_id, str) or not c.contact_id.strip():
                raise ValueError("Contact ID must be a non-empty string")
            if c.contact_id in seen_contact_ids:
                raise ValueError(f"Duplicate contact_id detected: '{c.contact_id}'. Contact IDs must be unique.")
            seen_contact_ids.add(c.contact_id)
            for val in c.contact_point_world + c.surface_normal_world:
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Contact '{c.contact_id}' contains non-finite values")
    except (ValueError, TypeError) as exc:
        return ContactForceSolution(
            status=ContactSolverStatus.INVALID_INPUT,
            contact_forces={c.contact_id: (0.0, 0.0, 0.0) for c in contacts},
            total_contact_force=(0.0, 0.0, 0.0),
            total_contact_torque_about_com=(0.0, 0.0, 0.0),
            force_error_vector=vec3_scale(target.target_force_world, -1.0),
            force_residual_n=vec3_length(target.target_force_world),
            torque_error_vector=vec3_scale(target.target_torque_world, -1.0),
            torque_residual_nm=vec3_length(target.target_torque_world),
            max_normal_violation_n=0.0,
            max_friction_violation_n=0.0,
            iterations=0,
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message=f"INVALID_INPUT: {exc}",
            solver_engine="none",
            optimizer_converged=False,
            optimizer_message=str(exc),
            fallback_occurred=False,
        )

    # -------------------------------------------------------------------------
    # 2. Filter Active Contacts & Sort for Permutation Invariance
    # -------------------------------------------------------------------------
    # Inactive/separated contacts are strictly constrained to zero force.
    # To guarantee permutation invariance, sort active contacts by contact_id.
    active_contacts = [c for c in contacts if c.is_in_contact]
    active_contacts_sorted = sorted(active_contacts, key=lambda c: c.contact_id)

    # Check a priori physical infeasibilities
    infeasible_check = _check_a_priori_infeasibility(
        target, active_contacts_sorted, tol=config.force_tolerance_n
    )

    if len(active_contacts_sorted) == 0:
        f_len = vec3_length(target.target_force_world)
        tau_len = vec3_length(target.target_torque_world)
        status = ContactSolverStatus.SOLVED if (f_len <= config.force_tolerance_n and tau_len <= config.torque_tolerance_nm) else ContactSolverStatus.INFEASIBLE
        msg = "No active contacts. All contact forces set to zero." if status == ContactSolverStatus.SOLVED else "INFEASIBLE: Non-zero target wrench with zero active contacts."
        return ContactForceSolution(
            status=status,
            contact_forces={c.contact_id: (0.0, 0.0, 0.0) for c in contacts},
            total_contact_force=(0.0, 0.0, 0.0),
            total_contact_torque_about_com=(0.0, 0.0, 0.0),
            force_error_vector=vec3_scale(target.target_force_world, -1.0),
            force_residual_n=f_len,
            torque_error_vector=vec3_scale(target.target_torque_world, -1.0),
            torque_residual_nm=tau_len,
            max_normal_violation_n=0.0,
            max_friction_violation_n=0.0,
            iterations=0,
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=True,
            message=msg,
            solver_engine="analytical" if status == ContactSolverStatus.SOLVED else "none",
            optimizer_converged=(status == ContactSolverStatus.SOLVED),
            optimizer_message=msg,
            fallback_occurred=False,
        )

    # -------------------------------------------------------------------------
    # 3. Execute Optimization Engine
    # -------------------------------------------------------------------------
    use_slsqp = (config.method == "slsqp") or (config.method == "auto" and HAVE_SCIPY)
    iterations = 0
    solved_forces: Dict[str, Vec3] = {}
    engine_used = "none"
    fallback_occurred = False
    opt_converged = False
    opt_message = ""

    if use_slsqp:
        engine_used = "slsqp"
        slsqp_failed = False
        slsqp_fail_reason = ""
        slsqp_iters = 0
        try:
            solved_forces, iterations, opt_converged, opt_message = _solve_with_slsqp(
                target, active_contacts_sorted, config
            )
            slsqp_iters = iterations
            if not opt_converged:
                slsqp_failed = True
                slsqp_fail_reason = opt_message if opt_message else "SLSQP reported success=False"
        except Exception as exc:
            slsqp_failed = True
            slsqp_fail_reason = f"SLSQP raised exception: {exc}"

        if slsqp_failed and config.enable_fallback:
            # Fallback to Native SPG if SLSQP fails (either exception or success=False)
            fallback_occurred = True
            engine_used = "spg"
            try:
                spg_forces, spg_iters, spg_converged, spg_message = _solve_with_spg(
                    target, active_contacts_sorted, config
                )
                solved_forces = spg_forces
                iterations = slsqp_iters + spg_iters
                opt_converged = spg_converged
                opt_message = f"Fallback from SLSQP ({slsqp_fail_reason}) to SPG: {spg_message}"
            except Exception as exc2:
                return ContactForceSolution(
                    status=ContactSolverStatus.NUMERICAL_FAILURE,
                    contact_forces={c.contact_id: (0.0, 0.0, 0.0) for c in contacts},
                    total_contact_force=(0.0, 0.0, 0.0),
                    total_contact_torque_about_com=(0.0, 0.0, 0.0),
                    force_error_vector=vec3_scale(target.target_force_world, -1.0),
                    force_residual_n=vec3_length(target.target_force_world),
                    torque_error_vector=vec3_scale(target.target_torque_world, -1.0),
                    torque_residual_nm=vec3_length(target.target_torque_world),
                    max_normal_violation_n=0.0,
                    max_friction_violation_n=0.0,
                    iterations=slsqp_iters,
                    computation_time_sec=time.perf_counter() - t0,
                    is_physically_valid=False,
                    message=f"NUMERICAL_FAILURE: SLSQP failed ({slsqp_fail_reason}); SPG fallback failed ({exc2})",
                    solver_engine="spg",
                    optimizer_converged=False,
                    optimizer_message=f"SLSQP failure: {slsqp_fail_reason}; SPG error: {exc2}",
                    fallback_occurred=True,
                )
        elif slsqp_failed and not config.enable_fallback:
            engine_used = "slsqp"
            fallback_occurred = False
            opt_converged = False
            opt_message = f"SLSQP non-success (fallback disabled): {slsqp_fail_reason}"
    else:
        engine_used = "spg"
        try:
            solved_forces, iterations, opt_converged, opt_message = _solve_with_spg(
                target, active_contacts_sorted, config
            )
        except Exception as exc:
            return ContactForceSolution(
                status=ContactSolverStatus.NUMERICAL_FAILURE,
                contact_forces={c.contact_id: (0.0, 0.0, 0.0) for c in contacts},
                total_contact_force=(0.0, 0.0, 0.0),
                total_contact_torque_about_com=(0.0, 0.0, 0.0),
                force_error_vector=vec3_scale(target.target_force_world, -1.0),
                force_residual_n=vec3_length(target.target_force_world),
                torque_error_vector=vec3_scale(target.target_torque_world, -1.0),
                torque_residual_nm=vec3_length(target.target_torque_world),
                max_normal_violation_n=0.0,
                max_friction_violation_n=0.0,
                iterations=iterations,
                computation_time_sec=time.perf_counter() - t0,
                is_physically_valid=False,
                message=f"NUMERICAL_FAILURE: SPG failed ({exc})",
                solver_engine="spg",
                optimizer_converged=False,
                optimizer_message=f"SPG error: {exc}",
                fallback_occurred=False,
            )

    # -------------------------------------------------------------------------
    # 4. Assemble Results & Evaluate Physical Constraints
    # -------------------------------------------------------------------------
    all_forces: Dict[str, Vec3] = {}
    for c in contacts:
        if c.is_in_contact:
            all_forces[c.contact_id] = solved_forces.get(c.contact_id, (0.0, 0.0, 0.0))
        else:
            all_forces[c.contact_id] = (0.0, 0.0, 0.0)

    # Verify all forces are finite numbers
    forces_are_finite = True
    for c_id, F in all_forces.items():
        if not (math.isfinite(F[0]) and math.isfinite(F[1]) and math.isfinite(F[2])):
            forces_are_finite = False
            break

    if not forces_are_finite:
        return ContactForceSolution(
            status=ContactSolverStatus.NUMERICAL_FAILURE,
            contact_forces=all_forces,
            total_contact_force=(float("nan"), float("nan"), float("nan")),
            total_contact_torque_about_com=(float("nan"), float("nan"), float("nan")),
            force_error_vector=(float("nan"), float("nan"), float("nan")),
            force_residual_n=float("nan"),
            torque_error_vector=(float("nan"), float("nan"), float("nan")),
            torque_residual_nm=float("nan"),
            max_normal_violation_n=float("nan"),
            max_friction_violation_n=float("nan"),
            iterations=iterations,
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message="NUMERICAL_FAILURE: Contact forces contain non-finite numbers (NaN/Inf).",
            solver_engine=engine_used,
            optimizer_converged=False,
            optimizer_message=opt_message if opt_message else "Non-finite values encountered in solution forces",
            fallback_occurred=fallback_occurred,
        )

    # Calculate actual net force and torque about com
    tot_fx, tot_fy, tot_fz = 0.0, 0.0, 0.0
    tot_tx, tot_ty, tot_tz = 0.0, 0.0, 0.0
    com_x, com_y, com_z = target.com_world

    max_norm_violation = 0.0
    max_fric_violation = 0.0

    for c in contacts:
        F = all_forces[c.contact_id]
        tot_fx += F[0]
        tot_fy += F[1]
        tot_fz += F[2]

        r = (c.contact_point_world[0] - com_x, c.contact_point_world[1] - com_y, c.contact_point_world[2] - com_z)
        tau = vec3_cross(r, F)
        tot_tx += tau[0]
        tot_ty += tau[1]
        tot_tz += tau[2]

        if c.is_in_contact:
            fn = vec3_dot(F, c.surface_normal_world)
            ft_vec = vec3_sub(F, vec3_scale(c.surface_normal_world, fn))
            ft = vec3_length(ft_vec)

            # Normal force violation: fn < min_fn or fn > max_fn
            v_n_lower = max(0.0, c.min_normal_force - fn)
            v_n_upper = max(0.0, fn - c.max_normal_force) if not math.isinf(c.max_normal_force) else 0.0
            max_norm_violation = max(max_norm_violation, v_n_lower, v_n_upper)

            # Friction cone violation: ft - mu * fn
            v_fric = max(0.0, ft - c.friction_coeff * fn)
            max_fric_violation = max(max_fric_violation, v_fric)
        else:
            # Separated contact must have zero force
            f_len = vec3_length(F)
            if f_len > 1e-6:
                max_norm_violation = max(max_norm_violation, f_len)

    total_F = (tot_fx, tot_fy, tot_fz)
    total_tau = (tot_tx, tot_ty, tot_tz)

    e_F = vec3_sub(total_F, target.target_force_world)
    res_F = vec3_length(e_F)

    e_tau = vec3_sub(total_tau, target.target_torque_world)
    res_tau = vec3_length(e_tau)

    res_is_finite = math.isfinite(res_F) and math.isfinite(res_tau)
    violations_are_finite = math.isfinite(max_norm_violation) and math.isfinite(max_fric_violation)

    if not res_is_finite or not violations_are_finite:
        return ContactForceSolution(
            status=ContactSolverStatus.NUMERICAL_FAILURE,
            contact_forces=all_forces,
            total_contact_force=total_F,
            total_contact_torque_about_com=total_tau,
            force_error_vector=e_F,
            force_residual_n=res_F if math.isfinite(res_F) else float("nan"),
            torque_error_vector=e_tau,
            torque_residual_nm=res_tau if math.isfinite(res_tau) else float("nan"),
            max_normal_violation_n=max_norm_violation if math.isfinite(max_norm_violation) else float("nan"),
            max_friction_violation_n=max_fric_violation if math.isfinite(max_fric_violation) else float("nan"),
            iterations=iterations,
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message=f"NUMERICAL_FAILURE: Non-finite residuals or violations detected (res_F={res_F}, res_tau={res_tau}).",
            solver_engine=engine_used,
            optimizer_converged=False,
            optimizer_message=opt_message if opt_message else "Non-finite residuals detected",
            fallback_occurred=fallback_occurred,
        )

    is_physically_valid = (
        max_norm_violation <= config.constraint_tolerance and
        max_fric_violation <= config.constraint_tolerance
    )

    # -------------------------------------------------------------------------
    # 5. Status Determination
    # -------------------------------------------------------------------------
    if not is_physically_valid:
        status = ContactSolverStatus.NUMERICAL_FAILURE
        msg = (
            f"Physical constraint violation: max normal={max_norm_violation:.4f}N, "
            f"max friction={max_fric_violation:.4f}N (slack={config.constraint_tolerance:.4f}N)"
        )
    elif infeasible_check is not None and infeasible_check[0] == ContactSolverStatus.INFEASIBLE:
        status = ContactSolverStatus.INFEASIBLE
        msg = f"INFEASIBLE: {infeasible_check[1]}"
    elif res_F <= config.force_tolerance_n and res_tau <= config.torque_tolerance_nm:
        # Check if optimizer actually confirmed convergence
        if not opt_converged:
            status = ContactSolverStatus.APPROXIMATE
            if iterations >= config.max_iterations:
                msg = (
                    f"APPROXIMATE: Residuals nominally within tolerance, but optimizer reached max iterations "
                    f"({iterations}/{config.max_iterations}) without convergence confirmation ({opt_message})."
                )
            else:
                msg = (
                    f"APPROXIMATE: Residuals nominally within tolerance, but optimizer terminated non-successfully "
                    f"without convergence confirmation ({opt_message})."
                )
        else:
            status = ContactSolverStatus.SOLVED
            msg = (
                f"SOLVED: Converged via {engine_used} in {iterations} iters. "
                f"res_F={res_F:.4f}N (tol={config.force_tolerance_n:.4f}N), "
                f"res_tau={res_tau:.4f}N*m (tol={config.torque_tolerance_nm:.4f}N*m)."
            )
    else:
        # Residual exceeds tolerance
        status = ContactSolverStatus.APPROXIMATE
        if len(active_contacts_sorted) == 1:
            r1 = (
                active_contacts_sorted[0].contact_point_world[0] - com_x,
                active_contacts_sorted[0].contact_point_world[1] - com_y,
                active_contacts_sorted[0].contact_point_world[2] - com_z,
            )
            r1_len = vec3_length(r1)
            if r1_len > 1e-4:
                parallel_tau = abs(vec3_dot(target.target_torque_world, vec3_scale(r1, 1.0 / r1_len)))
                if parallel_tau > config.torque_tolerance_nm:
                    msg = (
                        f"APPROXIMATE: Single contact point cannot produce torque parallel to lever arm "
                        f"(parallel tau={parallel_tau:.3f}N*m). Hard physical constraints satisfied."
                    )
                else:
                    msg = (
                        f"APPROXIMATE: Physical constraints satisfied, but target wrench residual exceeds tolerance "
                        f"({opt_message}): res_F={res_F:.4f}N (tol={config.force_tolerance_n:.4f}N), "
                        f"res_tau={res_tau:.4f}N*m (tol={config.torque_tolerance_nm:.4f}N*m)."
                    )
            else:
                msg = (
                    f"APPROXIMATE: Physical constraints satisfied, but target wrench residual exceeds tolerance "
                    f"({opt_message}): res_F={res_F:.4f}N (tol={config.force_tolerance_n:.4f}N), "
                    f"res_tau={res_tau:.4f}N*m (tol={config.torque_tolerance_nm:.4f}N*m)."
                )
        else:
            msg = (
                f"APPROXIMATE: Physical constraints satisfied, but target wrench residual exceeds tolerance "
                f"({opt_message}): res_F={res_F:.4f}N (tol={config.force_tolerance_n:.4f}N), "
                f"res_tau={res_tau:.4f}N*m (tol={config.torque_tolerance_nm:.4f}N*m)."
            )

    return ContactForceSolution(
        status=status,
        contact_forces=all_forces,
        total_contact_force=total_F,
        total_contact_torque_about_com=total_tau,
        force_error_vector=e_F,
        force_residual_n=res_F,
        torque_error_vector=e_tau,
        torque_residual_nm=res_tau,
        max_normal_violation_n=max_norm_violation,
        max_friction_violation_n=max_fric_violation,
        iterations=iterations,
        computation_time_sec=time.perf_counter() - t0,
        is_physically_valid=is_physically_valid,
        message=msg,
        solver_engine=engine_used,
        optimizer_converged=opt_converged,
        optimizer_message=opt_message,
        fallback_occurred=fallback_occurred,
    )


# =============================================================================
# 6. Environmental Integration & MultiContactDynamics Bridge
# =============================================================================

def create_contact_constraint_from_environment(
    env_query: DynamicsEnvironmentQuery,
    contact_point_world: Vec3,
    contact_id: str = "env_contact",
    surface_type_filter: Optional[str] = None,
    max_search_distance: float = 1.0,
    contact_tolerance: float = 0.02,
    min_normal_force: float = 0.0,
    max_normal_force: float = float("inf"),
) -> ContactConstraintSpec:
    """Construct a ContactConstraintSpec by querying the 3D analytical environment.

    Directly extracts outward surface normal, friction coefficient, and true signed distance
    from standard DynamicsPlayground surface patches (Zone 1 Flat Ground, Zone 3 Sloped Ramps,
    Zone 4 Vertical Walls).
    """
    pt = _to_vec3(contact_point_world, "contact_point_world")
    res: SurfaceQueryResult = env_query.query_surface_at_point(
        point_world=pt,
        surface_type_filter=surface_type_filter,
        max_distance=max_search_distance,
    )
    if not res.success:
        reason = getattr(res, "error_reason", None) or "Failed to query matching surface"
        raise ValueError(
            f"Failed to query environment surface at {pt}: {reason}"
        )

    is_in_contact = abs(res.signed_distance) <= contact_tolerance

    return ContactConstraintSpec(
        contact_id=contact_id,
        contact_point_world=pt,
        surface_normal_world=res.surface_normal_world,
        friction_coeff=res.friction_coeff,
        is_in_contact=is_in_contact,
        allows_regular_support=res.allows_regular_support,
        min_normal_force=min_normal_force,
        max_normal_force=max_normal_force,
        surface_id=res.surface_id,
        surface_distance=res.signed_distance,
        contact_tolerance=contact_tolerance,
    )


def solution_to_multi_contact_dynamics(
    solution: ContactForceSolution,
    contacts: Sequence[ContactConstraintSpec],
    com_world: Vec3,
    dt: float = 1.0 / 24.0,
) -> MultiContactDynamics:
    """Convert a ContactForceSolution into an independent verified MultiContactDynamics instance.

    Preserves true measured surface_distance from upstream contact specs without fabricating
    arbitrary placeholder clearances.
    """
    seen_ids = set()
    for c in contacts:
        if c.contact_id in seen_ids:
            raise ValueError(f"Duplicate contact_id detected in contacts: '{c.contact_id}'")
        seen_ids.add(c.contact_id)

    single_contacts: List[SingleContactDynamics] = []
    for c in contacts:
        f = solution.contact_forces.get(c.contact_id, (0.0, 0.0, 0.0))
        single_c = SingleContactDynamics(
            contact_id=c.contact_id,
            contact_point_world=c.contact_point_world,
            contact_force_world=f,
            com_world=com_world,
            surface_normal_world=c.surface_normal_world,
            friction_coeff=c.friction_coeff,
            dt=dt,
            surface_id=c.surface_id or c.contact_id,
            surface_distance=c.surface_distance,
            contact_tolerance=c.contact_tolerance,
            is_in_contact_override=c.is_in_contact,
        )
        single_contacts.append(single_c)

    return MultiContactDynamics(
        contacts=single_contacts,
        com_world=com_world,
        dt=dt,
    )
