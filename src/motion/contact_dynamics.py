"""Contact Dynamics Foundation and Momentum Impulse System (Task 6G-D-A).

Establishes a mathematically rigorous, decoupled 3D contact dynamics foundation for
humanoid procedural animation:
- Formulates world-space contact forces, torques, linear/angular impulses, and momentum changes.
- Strictly distinguishes:
  * Force (N), Torque (N*m), Impulse (N*s), Momentum (kg*m/s or N*s).
  * Reference points: Whole-Body Center of Mass (CoM) vs World Origin.
  * Coordinate frame: Unified World Coordinate System (+Z Up, Ground Z=0.0m, Right-Handed).
- Enforces physical contact constraints:
  * Unilateral normal contact: Normal force F_n >= 0 (no adhesive tension pull).
  * Coulomb friction cone: ||F_t|| <= mu * F_n (orthogonally decomposed tangential force).
- Evaluates multi-contact aggregation (sum of forces, sum of torques, net momentum change).
- Integrates seamlessly with standard DynamicsPlayground environment queries (`src.scene.environment_query`).
- Decoupled pure Python math kernel (runs lightning fast, zero bpy write coupling).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    from src.scene.environment_query import DynamicsEnvironmentQuery, EnvironmentQuery, SurfaceQueryResult
except ImportError:
    # Graceful fallback for standalone test runners if module hierarchy differs
    DynamicsEnvironmentQuery = Any  # type: ignore
    EnvironmentQuery = Any          # type: ignore
    SurfaceQueryResult = Any        # type: ignore


# =============================================================================
# 1. 3D Vector Math Helpers (SI Units, Pure Python, Robust vs NaN/Inf)
# =============================================================================

Vec3 = Tuple[float, float, float]
AnyVec3 = Union[Tuple[float, float, float], Sequence[float]]


def _to_vec3(v: AnyVec3, name: str = "vector") -> Vec3:
    """Validate and convert 3-element input to an immutable float 3-tuple."""
    if len(v) != 3:
        raise ValueError(f"{name} must have exactly 3 components, got {len(v)}: {v}")
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    if math.isnan(x) or math.isnan(y) or math.isnan(z) or math.isinf(x) or math.isinf(y) or math.isinf(z):
        raise ValueError(f"{name} contains non-finite values (NaN or Inf): ({x}, {y}, {z})")
    return (x, y, z)


def vec3_add(a: Vec3, b: Vec3) -> Vec3:
    """Vector addition a + b."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec3_sub(a: Vec3, b: Vec3) -> Vec3:
    """Vector subtraction a - b."""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec3_scale(a: Vec3, s: float) -> Vec3:
    """Scalar multiplication a * s."""
    if math.isnan(s) or math.isinf(s):
        raise ValueError(f"Scalar multiplier is non-finite: {s}")
    return (a[0] * s, a[1] * s, a[2] * s)


def vec3_dot(a: Vec3, b: Vec3) -> float:
    """Euclidean inner dot product a . b."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec3_cross(a: Vec3, b: Vec3) -> Vec3:
    """Right-handed vector cross product a x b."""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def vec3_length_sq(a: Vec3) -> float:
    """Squared Euclidean norm ||a||^2."""
    return a[0] * a[0] + a[1] * a[1] + a[2] * a[2]


def vec3_length(a: Vec3) -> float:
    """Euclidean norm ||a||."""
    return math.sqrt(vec3_length_sq(a))


def vec3_normalize(a: Vec3, eps: float = 1e-8) -> Vec3:
    """Normalize vector to unit length. Raises ValueError if degenerate."""
    l = vec3_length(a)
    if l < eps:
        raise ValueError(f"Cannot normalize degenerate near-zero vector: {a} (length={l})")
    inv_l = 1.0 / l
    return (a[0] * inv_l, a[1] * inv_l, a[2] * inv_l)


def mat3_mul_vec(rot_mat: Sequence[Sequence[float]], v: Vec3) -> Vec3:
    """Multiply 3x3 matrix by 3D column vector: R * v."""
    return (
        rot_mat[0][0] * v[0] + rot_mat[0][1] * v[1] + rot_mat[0][2] * v[2],
        rot_mat[1][0] * v[0] + rot_mat[1][1] * v[1] + rot_mat[1][2] * v[2],
        rot_mat[2][0] * v[0] + rot_mat[2][1] * v[1] + rot_mat[2][2] * v[2],
    )


# =============================================================================
# 2. Friction Cone Status and Evaluation Contracts
# =============================================================================

class FrictionConeStatus(str, Enum):
    """Categorical evaluation status of Coulomb friction cone constraint."""
    STICK = "stick"                           # Well inside friction cone: ||F_t|| < mu * F_n
    SLIP_LIMIT = "slip_limit"                 # On boundary of friction cone within tolerance: ||F_t|| ~= mu * F_n
    SLIP_VIOLATION = "slip_violation"         # Tangential force exceeds static limit: ||F_t|| > mu * F_n
    TENSION_VIOLATION = "tension_violation"   # Normal force is negative: F_n < 0 (unilateral adhesive pull)
    SEPARATED = "separated"                   # Zero contact normal force and zero tangential force


@dataclass(frozen=True)
class FrictionConstraintEvaluation:
    """Quantitative report of Coulomb friction cone and unilateral normal constraint compliance.

    Attributes:
        is_valid: True if both unilateral push (F_n >= 0) and friction cone (||F_t|| <= mu*F_n) are satisfied.
        status: Detailed categorization from FrictionConeStatus.
        normal_force_n: Normal force component along surface outward normal (N). F_n >= 0 for push.
        tangential_force_n: Magnitude of tangential friction force ||F_t|| (N).
        friction_limit_n: Maximum allowable friction force mu * max(0.0, F_n) (N).
        friction_margin_n: Margin capacity (friction_limit_n - tangential_force_n) in N (>= 0 is valid).
        normal_force_vector: Normal force vector F_n * normal in World space (N).
        tangential_force_vector: Tangential force vector (F - normal_force_vector) in World space (N).
        violation_reason: Human-readable diagnostic description if is_valid is False; None on success.
    """
    is_valid: bool
    status: FrictionConeStatus
    normal_force_n: float
    tangential_force_n: float
    friction_limit_n: float
    friction_margin_n: float
    normal_force_vector: Vec3
    tangential_force_vector: Vec3
    violation_reason: Optional[str] = None


# =============================================================================
# 3. Single Contact Dynamics Representation
# =============================================================================

@dataclass
class SingleContactDynamics:
    """Instantaneous mathematical contact dynamics representation for a single contact point.

    Coordinates & Units:
    - `contact_point_world`: World-space position of force application p_c (m).
    - `contact_force_world`: World-space contact force F applied to the character (N = kg*m/s^2).
    - `com_world`: World-space position of Whole-Body Center of Mass p_com (m).
    - `surface_normal_world`: Unit outward normal of the contact surface pointing into free space.
    - `friction_coeff`: Static friction coefficient mu >= 0 (dimensionless).
    - `dt`: Positive simulation time step delta_t (s).

    Derived Physical Quantities:
    - Lever arm: r = p_c - p_com (m, from CoM to contact point).
    - Contact torque about CoM: tau_com = r x F (N*m).
    - Contact torque about World Origin: tau_origin = p_c x F (N*m).
    - Linear impulse: J = F * dt (N*s = kg*m/s).
    - Angular impulse about CoM: H_com = tau_com * dt (N*m*s = kg*m^2/s).
    - Linear momentum change: Delta P = J (kg*m/s).
    - Angular momentum change about CoM: Delta L_com = H_com (kg*m^2/s).
    """
    contact_id: str
    contact_point_world: Vec3
    contact_force_world: Vec3
    com_world: Vec3
    surface_normal_world: Vec3
    friction_coeff: float = 0.65
    dt: float = 1.0 / 24.0

    def __post_init__(self):
        # Validate inputs and sanitize vectors
        self.contact_point_world = _to_vec3(self.contact_point_world, "contact_point_world")
        self.contact_force_world = _to_vec3(self.contact_force_world, "contact_force_world")
        self.com_world = _to_vec3(self.com_world, "com_world")
        norm = _to_vec3(self.surface_normal_world, "surface_normal_world")
        self.surface_normal_world = vec3_normalize(norm)

        if math.isnan(self.friction_coeff) or math.isinf(self.friction_coeff) or self.friction_coeff < 0.0:
            raise ValueError(f"friction_coeff must be non-negative and finite, got {self.friction_coeff}")

        if math.isnan(self.dt) or math.isinf(self.dt) or self.dt <= 0.0:
            raise ValueError(f"dt must be strictly positive and finite, got {self.dt}")

    # -------------------------------------------------------------------------
    # Relative Lever Arm & Torques
    # -------------------------------------------------------------------------

    @property
    def lever_arm_from_com(self) -> Vec3:
        """Position vector from Whole-Body CoM to contact point: r = p_c - p_com (meters)."""
        return vec3_sub(self.contact_point_world, self.com_world)

    @property
    def torque_about_com(self) -> Vec3:
        """Contact torque about Whole-Body CoM: tau_com = r x F (N*m).

        Adheres strictly to the right-hand rule:
        tau_x = r_y * F_z - r_z * F_y
        tau_y = r_z * F_x - r_x * F_z
        tau_z = r_x * F_y - r_y * F_x
        """
        return vec3_cross(self.lever_arm_from_com, self.contact_force_world)

    @property
    def torque_about_origin(self) -> Vec3:
        """Contact torque about World Coordinate Origin (0, 0, 0): tau_origin = p_c x F (N*m).

        Relation: tau_origin = p_com x F + tau_com.
        """
        return vec3_cross(self.contact_point_world, self.contact_force_world)

    # -------------------------------------------------------------------------
    # Impulses & Momentum Changes
    # -------------------------------------------------------------------------

    @property
    def linear_impulse(self) -> Vec3:
        """Linear impulse over time step dt: J = F * dt (N*s = kg*m/s)."""
        return vec3_scale(self.contact_force_world, self.dt)

    @property
    def angular_impulse_about_com(self) -> Vec3:
        """Angular impulse about Whole-Body CoM: H_com = tau_com * dt (N*m*s = kg*m^2/s)."""
        return vec3_scale(self.torque_about_com, self.dt)

    @property
    def angular_impulse_about_origin(self) -> Vec3:
        """Angular impulse about World Origin: H_origin = tau_origin * dt (N*m*s)."""
        return vec3_scale(self.torque_about_origin, self.dt)

    @property
    def linear_momentum_change(self) -> Vec3:
        """Linear momentum change by Newton's Second Law: Delta P = J = F * dt (kg*m/s)."""
        return self.linear_impulse

    @property
    def angular_momentum_change_about_com(self) -> Vec3:
        """Angular momentum change about Whole-Body CoM: Delta L_com = H_com (kg*m^2/s)."""
        return self.angular_impulse_about_com

    @property
    def angular_momentum_change_about_origin(self) -> Vec3:
        """Angular momentum change about World Origin: Delta L_origin = H_origin (kg*m^2/s)."""
        return self.angular_impulse_about_origin

    # -------------------------------------------------------------------------
    # Normal & Coulomb Friction Constraints
    # -------------------------------------------------------------------------

    def evaluate_friction_constraint(self, eps: float = 1e-5) -> FrictionConstraintEvaluation:
        """Evaluate normal non-adhesive constraint and Coulomb friction cone.

        Decomposes force F into:
        - Normal force F_n = F . normal (scalar, along surface outward unit normal).
        - Normal force vector F_n_vec = F_n * normal.
        - Tangential friction force vector F_t_vec = F - F_n_vec.
        - Tangential force magnitude ||F_t||.

        Physical Requirements:
        - Normal push: F_n >= -eps. (A contact force pushing into the character from the ground
          points in the direction of the surface outward normal, i.e. F . normal >= 0).
        - Coulomb friction limit: ||F_t|| <= mu * max(0.0, F_n) + eps.
        """
        F = self.contact_force_world
        n = self.surface_normal_world
        f_len = vec3_length(F)

        # Handle fully separated/zero-force contact
        if f_len < eps:
            return FrictionConstraintEvaluation(
                is_valid=True,
                status=FrictionConeStatus.SEPARATED,
                normal_force_n=0.0,
                tangential_force_n=0.0,
                friction_limit_n=0.0,
                friction_margin_n=0.0,
                normal_force_vector=(0.0, 0.0, 0.0),
                tangential_force_vector=(0.0, 0.0, 0.0),
                violation_reason=None,
            )

        # Normal component along surface outward normal
        f_n = vec3_dot(F, n)
        f_n_vec = vec3_scale(n, f_n)

        # Tangential component orthogonal to surface normal
        f_t_vec = vec3_sub(F, f_n_vec)
        f_t = vec3_length(f_t_vec)

        # Unilateral constraint check (no tension/adhesive pull)
        if f_n < -eps:
            reason = (
                f"UNILATERAL_TENSION_VIOLATION: Normal force F_n={f_n:.3f}N < 0 "
                f"(contact cannot pull or exert adhesive tension away from surface)"
            )
            return FrictionConstraintEvaluation(
                is_valid=False,
                status=FrictionConeStatus.TENSION_VIOLATION,
                normal_force_n=f_n,
                tangential_force_n=f_t,
                friction_limit_n=0.0,
                friction_margin_n=-f_t,
                normal_force_vector=f_n_vec,
                tangential_force_vector=f_t_vec,
                violation_reason=reason,
            )

        # Coulomb friction limit
        f_n_clamped = max(0.0, f_n)
        f_limit = self.friction_coeff * f_n_clamped
        margin = f_limit - f_t

        if margin < -eps:
            reason = (
                f"COULOMB_SLIP_VIOLATION: Tangential force ||F_t||={f_t:.3f}N exceeds "
                f"Coulomb limit mu*F_n={f_limit:.3f}N by {-margin:.3f}N (mu={self.friction_coeff:.2f})"
            )
            return FrictionConstraintEvaluation(
                is_valid=False,
                status=FrictionConeStatus.SLIP_VIOLATION,
                normal_force_n=f_n,
                tangential_force_n=f_t,
                friction_limit_n=f_limit,
                friction_margin_n=margin,
                normal_force_vector=f_n_vec,
                tangential_force_vector=f_t_vec,
                violation_reason=reason,
            )

        # Check if on slip boundary
        status = FrictionConeStatus.SLIP_LIMIT if abs(margin) <= eps else FrictionConeStatus.STICK
        return FrictionConstraintEvaluation(
            is_valid=True,
            status=status,
            normal_force_n=f_n,
            tangential_force_n=f_t,
            friction_limit_n=f_limit,
            friction_margin_n=margin,
            normal_force_vector=f_n_vec,
            tangential_force_vector=f_t_vec,
            violation_reason=None,
        )


# =============================================================================
# 4. Multi-Contact Dynamics Aggregation
# =============================================================================

@dataclass
class MultiContactDynamics:
    """Aggregated contact dynamics system across multiple contact sites.

    Computes total external force, total torque about CoM, total impulses, and net
    linear/angular momentum changes across all active contact points.
    """
    contacts: List[SingleContactDynamics] = field(default_factory=list)
    com_world: Vec3 = (0.0, 0.0, 1.0)
    dt: float = 1.0 / 24.0

    def __post_init__(self):
        self.com_world = _to_vec3(self.com_world, "com_world")
        if math.isnan(self.dt) or math.isinf(self.dt) or self.dt <= 0.0:
            raise ValueError(f"dt must be strictly positive and finite, got {self.dt}")

    def add_contact(self, contact: SingleContactDynamics) -> None:
        """Add a single contact dynamics instance, synchronizing CoM and dt if necessary."""
        self.contacts.append(contact)

    # -------------------------------------------------------------------------
    # Net External Forces & Torques
    # -------------------------------------------------------------------------

    @property
    def total_contact_force(self) -> Vec3:
        """Net external contact force: F_total = sum(F_i) in World space (N)."""
        tx, ty, tz = 0.0, 0.0, 0.0
        for c in self.contacts:
            fx, fy, fz = c.contact_force_world
            tx += fx
            ty += fy
            tz += fz
        return (tx, ty, tz)

    @property
    def total_torque_about_com(self) -> Vec3:
        """Net contact torque about Whole-Body CoM: tau_total,com = sum(r_i x F_i) (N*m)."""
        tx, ty, tz = 0.0, 0.0, 0.0
        for c in self.contacts:
            # Enforce calculation relative to multi-contact system's CoM
            r = vec3_sub(c.contact_point_world, self.com_world)
            tau = vec3_cross(r, c.contact_force_world)
            tx += tau[0]
            ty += tau[1]
            tz += tau[2]
        return (tx, ty, tz)

    @property
    def total_torque_about_origin(self) -> Vec3:
        """Net contact torque about World Origin: tau_total,origin = sum(p_c,i x F_i) (N*m)."""
        tx, ty, tz = 0.0, 0.0, 0.0
        for c in self.contacts:
            tau = c.torque_about_origin
            tx += tau[0]
            ty += tau[1]
            tz += tau[2]
        return (tx, ty, tz)

    # -------------------------------------------------------------------------
    # Total Impulses & Net Momentum Changes
    # -------------------------------------------------------------------------

    @property
    def total_linear_impulse(self) -> Vec3:
        """Total linear impulse over time dt: J_total = F_total * dt (N*s = kg*m/s)."""
        return vec3_scale(self.total_contact_force, self.dt)

    @property
    def total_angular_impulse_about_com(self) -> Vec3:
        """Total angular impulse about CoM: H_total,com = tau_total,com * dt (N*m*s = kg*m^2/s)."""
        return vec3_scale(self.total_torque_about_com, self.dt)

    @property
    def total_angular_impulse_about_origin(self) -> Vec3:
        """Total angular impulse about Origin: H_total,origin = tau_total,origin * dt (N*m*s)."""
        return vec3_scale(self.total_torque_about_origin, self.dt)

    @property
    def total_linear_momentum_change(self) -> Vec3:
        """Net change in linear momentum: Delta P = J_total (kg*m/s)."""
        return self.total_linear_impulse

    @property
    def total_angular_momentum_change_about_com(self) -> Vec3:
        """Net change in angular momentum about CoM: Delta L_com = H_total,com (kg*m^2/s)."""
        return self.total_angular_impulse_about_com

    @property
    def total_angular_momentum_change_about_origin(self) -> Vec3:
        """Net change in angular momentum about Origin: Delta L_origin = H_total,origin (kg*m^2/s)."""
        return self.total_angular_impulse_about_origin

    # -------------------------------------------------------------------------
    # Multi-Contact Constraint Checking
    # -------------------------------------------------------------------------

    def evaluate_all_friction_constraints(self, eps: float = 1e-5) -> Dict[str, FrictionConstraintEvaluation]:
        """Evaluate friction constraints for each registered contact."""
        results: Dict[str, FrictionConstraintEvaluation] = {}
        for c in self.contacts:
            results[c.contact_id] = c.evaluate_friction_constraint(eps=eps)
        return results

    @property
    def is_all_friction_valid(self) -> bool:
        """True if every registered contact complies with unilateral and Coulomb friction limits."""
        for c in self.contacts:
            if not c.evaluate_friction_constraint().is_valid:
                return False
        return True


# =============================================================================
# 5. Integration Factory with Standard Dynamics Playground Environment Query
# =============================================================================

def create_contact_dynamics_from_environment(
    env_query: Union[DynamicsEnvironmentQuery, EnvironmentQuery],
    contact_point_world: AnyVec3,
    contact_force_world: AnyVec3,
    com_world: AnyVec3,
    dt: float = 1.0 / 24.0,
    contact_id: str = "env_contact",
    surface_type_filter: Optional[str] = None,
    max_search_distance: float = 1.0,
) -> SingleContactDynamics:
    """Instantiate a SingleContactDynamics with surface normal and friction derived from environment.

    Args:
        env_query: Standard DynamicsEnvironmentQuery (or base EnvironmentQuery) instance.
        contact_point_world: World coordinate (x, y, z) where contact occurs.
        contact_force_world: World force (Fx, Fy, Fz) in Newtons applied to character.
        com_world: Whole-Body Center of Mass (x, y, z) in meters.
        dt: Time step duration (seconds).
        contact_id: Descriptive label for this contact point.
        surface_type_filter: Optional filter restriction (e.g. 'vertical_wall', 'sloped_ramp').
        max_search_distance: Maximum distance to query environmental surface patch.

    Returns:
        SingleContactDynamics populated with the true surface outward normal and friction coefficient.

    Raises:
        ValueError: If environment query fails to locate a matching surface within search radius.
    """
    pt = _to_vec3(contact_point_world, "contact_point_world")
    res: SurfaceQueryResult = env_query.query_surface_at_point(
        pt,
        max_distance=max_search_distance,
        surface_type_filter=surface_type_filter,
    )
    if not res.success:
        reason = res.error_reason or "Unknown surface query error"
        raise ValueError(
            f"Failed to bind contact dynamics at point {pt} to environment: {reason}"
        )

    # Use actual analytical surface normal and static friction coefficient
    return SingleContactDynamics(
        contact_id=contact_id,
        contact_point_world=pt,
        contact_force_world=contact_force_world,
        com_world=com_world,
        surface_normal_world=res.surface_normal_world,
        friction_coeff=res.friction_coeff,
        dt=dt,
    )
