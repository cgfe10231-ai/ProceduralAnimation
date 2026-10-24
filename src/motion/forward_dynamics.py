"""Forward Dynamics Single-Step Integration Kernel (Task 6G-D-C1-A).

Implements an independent, mathematically rigorous, and fully testable single-step
forward dynamics integration kernel for a 6-DOF rigid body model with multi-contact forces.

Pure Python Architecture:
- 100% decoupled from Blender GUI and bpy; fully runnable and testable in standalone Python.
- Strict separation between actual physical state and reference target values.
- Full 6-DOF Newton-Euler rigid body equations of motion.

Coordinate System & Reference Conventions:
- World Coordinate Frame: Right-handed Cartesian with +Z pointing Up, Ground plane at Z = 0.0 m.
- Units: SI units throughout:
  * Length / Position: meters (m)
  * Time: seconds (s)
  * Mass: kilograms (kg)
  * Force: Newtons (N)
  * Torque: Newton-meters (N*m)
  * Linear Velocity: meters / second (m/s)
  * Linear Acceleration: meters / second^2 (m/s^2)
  * Angular Momentum: kg*m^2 / s (or N*m*s)
  * Angular Velocity: radians / second (rad/s)
  * Inertia Tensor: kg*m^2
- Attitude Quaternion: (w, x, y, z) where w is the real scalar component and (x, y, z) is the
  imaginary vector part. Represents active Body-to-World coordinate transformation:
      v_world = R(q) * v_body
- Inertia Tensor Frames:
  * inertia_tensor_body: 3x3 symmetric matrix defined in the rigid body's Local/Body frame
    (invariant under rigid-body rotation).
  * inertia_tensor_world: 3x3 symmetric matrix defined in World frame, transformed covariantly:
      I_world = R(q) * I_body * R(q)^T
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# Vector and Matrix Type Aliases
Vec3 = Tuple[float, float, float]
Vec4 = Tuple[float, float, float, float]  # Quaternion (w, x, y, z)
Matrix3x3 = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]


# =============================================================================
# 1. Low-Level Pure Python Vector & Quaternion Mathematics
# =============================================================================

def vec3_add(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (float(a[0] + b[0]), float(a[1] + b[1]), float(a[2] + b[2]))


def vec3_sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (float(a[0] - b[0]), float(a[1] - b[1]), float(a[2] - b[2]))


def vec3_scale(v: Sequence[float], s: float) -> Vec3:
    return (float(v[0] * s), float(v[1] * s), float(v[2] * s))


def vec3_dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def vec3_cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (
        float(a[1] * b[2] - a[2] * b[1]),
        float(a[2] * b[0] - a[0] * b[2]),
        float(a[0] * b[1] - a[1] * b[0]),
    )


def vec3_length_sq(v: Sequence[float]) -> float:
    return float(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def vec3_length(v: Sequence[float]) -> float:
    return math.sqrt(vec3_length_sq(v))


def vec3_normalize(v: Sequence[float], tol: float = 1e-12) -> Vec3:
    l = vec3_length(v)
    if l < tol:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / l
    return (float(v[0] * inv), float(v[1] * inv), float(v[2] * inv))


def vec3_is_finite(v: Sequence[float]) -> bool:
    return len(v) == 3 and math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2])


def quat_is_finite(q: Sequence[float]) -> bool:
    return (
        len(q) == 4
        and math.isfinite(q[0])
        and math.isfinite(q[1])
        and math.isfinite(q[2])
        and math.isfinite(q[3])
    )


def quat_length(q: Sequence[float]) -> float:
    return math.sqrt(float(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]))


def quat_normalize(q: Sequence[float], tol: float = 1e-12) -> Vec4:
    l = quat_length(q)
    if l < tol:
        raise ValueError(f"Cannot normalize degenerate quaternion with length {l}")
    inv = 1.0 / l
    return (float(q[0] * inv), float(q[1] * inv), float(q[2] * inv), float(q[3] * inv))


def quat_multiply(q1: Sequence[float], q2: Sequence[float]) -> Vec4:
    """Hamilton quaternion multiplication: q = q1 * q2."""
    w1, x1, y1, z1 = float(q1[0]), float(q1[1]), float(q1[2]), float(q1[3])
    w2, x2, y2, z2 = float(q2[0]), float(q2[1]), float(q2[2]), float(q2[3])
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def quat_to_rot_matrix(q: Sequence[float]) -> Matrix3x3:
    """Convert unit quaternion (w, x, y, z) to 3x3 rotation matrix R in SO(3).
    
    Transforms vectors from body to world: v_world = R * v_body.
    """
    qn = quat_normalize(q)
    w, x, y, z = qn[0], qn[1], qn[2], qn[3]
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)),
        (2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)),
        (2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)),
    )


def quat_rotate_vector(q: Sequence[float], v: Sequence[float]) -> Vec3:
    """Active rotation of vector v by quaternion q: v_rot = R(q) * v."""
    R = quat_to_rot_matrix(q)
    vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
    return (
        R[0][0] * vx + R[0][1] * vy + R[0][2] * vz,
        R[1][0] * vx + R[1][1] * vy + R[1][2] * vz,
        R[2][0] * vx + R[2][1] * vy + R[2][2] * vz,
    )


def quat_from_axis_angle(axis: Sequence[float], angle_rad: float) -> Vec4:
    """Construct unit quaternion (w, x, y, z) representing rotation by angle_rad around axis."""
    ax = vec3_normalize(axis)
    half_angle = 0.5 * float(angle_rad)
    s = math.sin(half_angle)
    c = math.cos(half_angle)
    return (c, ax[0] * s, ax[1] * s, ax[2] * s)


# =============================================================================
# 2. 3x3 Matrix Mathematics & Inertia Tensor Representation
# =============================================================================

def mat3_multiply(A: Matrix3x3, B: Matrix3x3) -> Matrix3x3:
    """Multiply two 3x3 matrices: C = A * B."""
    return (
        (
            A[0][0] * B[0][0] + A[0][1] * B[1][0] + A[0][2] * B[2][0],
            A[0][0] * B[0][1] + A[0][1] * B[1][1] + A[0][2] * B[2][1],
            A[0][0] * B[0][2] + A[0][1] * B[1][2] + A[0][2] * B[2][2],
        ),
        (
            A[1][0] * B[0][0] + A[1][1] * B[1][0] + A[1][2] * B[2][0],
            A[1][0] * B[0][1] + A[1][1] * B[1][1] + A[1][2] * B[2][1],
            A[1][0] * B[0][2] + A[1][1] * B[1][2] + A[1][2] * B[2][2],
        ),
        (
            A[2][0] * B[0][0] + A[2][1] * B[1][0] + A[2][2] * B[2][0],
            A[2][0] * B[0][1] + A[2][1] * B[1][1] + A[2][2] * B[2][1],
            A[2][0] * B[0][2] + A[2][1] * B[1][2] + A[2][2] * B[2][2],
        ),
    )


def mat3_transpose(A: Matrix3x3) -> Matrix3x3:
    """Transpose a 3x3 matrix."""
    return (
        (A[0][0], A[1][0], A[2][0]),
        (A[0][1], A[1][1], A[2][1]),
        (A[0][2], A[1][2], A[2][2]),
    )


def mat3_multiply_vec(A: Matrix3x3, v: Sequence[float]) -> Vec3:
    """Matrix-vector product: u = A * v."""
    vx, vy, vz = float(v[0]), float(v[1]), float(v[2])
    return (
        A[0][0] * vx + A[0][1] * vy + A[0][2] * vz,
        A[1][0] * vx + A[1][1] * vy + A[1][2] * vz,
        A[2][0] * vx + A[2][1] * vy + A[2][2] * vz,
    )


def mat3_determinant(A: Matrix3x3) -> float:
    """Determinant of 3x3 matrix via cofactor expansion."""
    return (
        A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1])
        - A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0])
        + A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0])
    )


def mat3_inverse(A: Matrix3x3, tol: float = 1e-12) -> Matrix3x3:
    """Analytical inverse of a 3x3 matrix via classical adjugate / cofactors."""
    c00 = A[1][1] * A[2][2] - A[1][2] * A[2][1]
    c01 = -(A[1][0] * A[2][2] - A[1][2] * A[2][0])
    c02 = A[1][0] * A[2][1] - A[1][1] * A[2][0]

    det = A[0][0] * c00 + A[0][1] * c01 + A[0][2] * c02
    if abs(det) < tol or not math.isfinite(det):
        raise ValueError(f"Matrix is singular or ill-conditioned (det = {det})")

    inv_det = 1.0 / det

    c10 = -(A[0][1] * A[2][2] - A[0][2] * A[2][1])
    c11 = A[0][0] * A[2][2] - A[0][2] * A[2][0]
    c12 = -(A[0][0] * A[2][1] - A[0][1] * A[2][0])

    c20 = A[0][1] * A[1][2] - A[0][2] * A[1][1]
    c21 = -(A[0][0] * A[1][2] - A[0][2] * A[1][0])
    c22 = A[0][0] * A[1][1] - A[0][1] * A[1][0]

    # Transpose of cofactor matrix divided by det
    return (
        (c00 * inv_det, c10 * inv_det, c20 * inv_det),
        (c01 * inv_det, c11 * inv_det, c21 * inv_det),
        (c02 * inv_det, c12 * inv_det, c22 * inv_det),
    )


@dataclass(frozen=True)
class InertiaTensor3x3:
    """Pure Python 3x3 symmetric inertia tensor representation in SI units (kg*m^2).
    
    Matrix form:
        [ ixx   ixy   ixz ]
        [ ixy   iyy   iyz ]
        [ ixz   iyz   izz ]
    """
    ixx: float
    iyy: float
    izz: float
    ixy: float = 0.0
    ixz: float = 0.0
    iyz: float = 0.0

    def __post_init__(self):
        for name, val in [
            ("ixx", self.ixx),
            ("iyy", self.iyy),
            ("izz", self.izz),
            ("ixy", self.ixy),
            ("ixz", self.ixz),
            ("iyz", self.iyz),
        ]:
            if not math.isfinite(val):
                raise ValueError(f"InertiaTensor3x3 element '{name}' must be finite, got {val}")

    @classmethod
    def from_diagonal(cls, ixx: float, iyy: float, izz: float) -> "InertiaTensor3x3":
        """Construct diagonal inertia tensor (principal axes aligned)."""
        return cls(ixx=float(ixx), iyy=float(iyy), izz=float(izz), ixy=0.0, ixz=0.0, iyz=0.0)

    @classmethod
    def from_matrix(cls, mat: Sequence[Sequence[float]]) -> "InertiaTensor3x3":
        """Construct InertiaTensor3x3 from 3x3 matrix-like object, averaging off-diagonals for symmetry."""
        if len(mat) != 3 or any(len(row) != 3 for row in mat):
            raise ValueError(f"Expected 3x3 matrix, got dimensions {len(mat)}x{[len(r) for r in mat]}")
        ixx = float(mat[0][0])
        iyy = float(mat[1][1])
        izz = float(mat[2][2])
        ixy = 0.5 * (float(mat[0][1]) + float(mat[1][0]))
        ixz = 0.5 * (float(mat[0][2]) + float(mat[2][0]))
        iyz = 0.5 * (float(mat[1][2]) + float(mat[2][1]))
        return cls(ixx=ixx, iyy=iyy, izz=izz, ixy=ixy, ixz=ixz, iyz=iyz)

    def to_matrix(self) -> Matrix3x3:
        """Convert to nested 3x3 tuple."""
        return (
            (self.ixx, self.ixy, self.ixz),
            (self.ixy, self.iyy, self.iyz),
            (self.ixz, self.iyz, self.izz),
        )

    def determinant(self) -> float:
        """Determinant of 3x3 inertia matrix."""
        return (
            self.ixx * (self.iyy * self.izz - self.iyz * self.iyz)
            - self.ixy * (self.ixy * self.izz - self.iyz * self.ixz)
            + self.ixz * (self.ixy * self.iyz - self.iyy * self.ixz)
        )

    def trace(self) -> float:
        """Trace of inertia matrix: ixx + iyy + izz."""
        return self.ixx + self.iyy + self.izz

    def is_positive_definite(self, tol: float = 1e-8) -> bool:
        """Sylvester's criterion for positive-definiteness of a 3x3 symmetric matrix:
        
        1. D_1 = ixx > tol
        2. D_2 = ixx * iyy - ixy^2 > tol
        3. D_3 = det(I) > tol
        """
        d1 = self.ixx
        d2 = self.ixx * self.iyy - self.ixy * self.ixy
        d3 = self.determinant()
        return (d1 > tol) and (d2 > tol) and (d3 > tol)

    def is_physically_valid(self, tol: float = 1e-8) -> bool:
        """Check positive-definiteness plus triangle inequalities for rigid body inertia:
        
        ixx + iyy >= izz, iyy + izz >= ixx, ixx + izz >= iyy.
        """
        if not self.is_positive_definite(tol):
            return False
        return (
            (self.ixx + self.iyy + tol >= self.izz)
            and (self.iyy + self.izz + tol >= self.ixx)
            and (self.ixx + self.izz + tol >= self.iyy)
        )

    def rotate(self, R: Matrix3x3) -> "InertiaTensor3x3":
        """Transform tensor into a new coordinate frame: I_new = R * I * R^T."""
        I_mat = self.to_matrix()
        RT = mat3_transpose(R)
        I_rot = mat3_multiply(mat3_multiply(R, I_mat), RT)
        return InertiaTensor3x3.from_matrix(I_rot)

    def multiply_vec(self, v: Sequence[float]) -> Vec3:
        """Multiply inertia tensor by 3D angular velocity vector: L = I * omega."""
        return mat3_multiply_vec(self.to_matrix(), v)

    def solve_angular_velocity(self, L_world: Sequence[float], tol: float = 1e-8) -> Vec3:
        """Solve I_world * omega_world = L_world for angular velocity omega_world."""
        if not self.is_positive_definite(tol):
            raise ValueError(f"Inertia tensor is not strictly positive-definite (det={self.determinant()})")
        inv_I = mat3_inverse(self.to_matrix(), tol=tol)
        return mat3_multiply_vec(inv_I, L_world)


# =============================================================================
# 3. Status & Contact Input Structures
# =============================================================================

class ForwardDynamicsStatus(str, Enum):
    """Execution status for single-step forward dynamics integration."""
    SUCCESS = "SUCCESS"
    INVALID_INPUT = "INVALID_INPUT"
    SINGULAR_INERTIA = "SINGULAR_INERTIA"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"


@dataclass(frozen=True)
class ContactForcePoint:
    """3D Contact force applied at a specific world position."""
    contact_point_world: Vec3
    contact_force_world: Vec3
    contact_id: str = ""

    def __post_init__(self):
        p = (float(self.contact_point_world[0]), float(self.contact_point_world[1]), float(self.contact_point_world[2]))
        f = (float(self.contact_force_world[0]), float(self.contact_force_world[1]), float(self.contact_force_world[2]))
        if not vec3_is_finite(p):
            raise ValueError(f"contact_point_world contains non-finite numbers: {self.contact_point_world}")
        if not vec3_is_finite(f):
            raise ValueError(f"contact_force_world contains non-finite numbers: {self.contact_force_world}")
        object.__setattr__(self, "contact_point_world", p)
        object.__setattr__(self, "contact_force_world", f)


# =============================================================================
# 4. State & Step Inputs
# =============================================================================

@dataclass(frozen=True)
class ForwardDynamicsState:
    """Rigorous 6-DOF rigid body dynamical state at a single instant in time.
    
    Immutable (frozen) to guarantee failure atomicity and prevent partial mutations.
    """
    timestamp: float = 0.0
    mass: float = 70.0
    com_position_world: Vec3 = (0.0, 0.0, 1.0)
    com_velocity_world: Vec3 = (0.0, 0.0, 0.0)
    angular_momentum_about_com_world: Vec3 = (0.0, 0.0, 0.0)
    orientation_quat_world: Vec4 = (1.0, 0.0, 0.0, 0.0)  # (w, x, y, z)
    inertia_tensor_body: InertiaTensor3x3 = field(
        default_factory=lambda: InertiaTensor3x3.from_diagonal(10.0, 10.0, 10.0)
    )

    def __post_init__(self):
        # Validate mass
        if not math.isfinite(self.mass) or self.mass <= 0.0:
            raise ValueError(f"Mass must be positive and finite, got {self.mass}")

        # Validate timestamp
        if not math.isfinite(self.timestamp) or self.timestamp < 0.0:
            raise ValueError(f"Timestamp must be non-negative and finite, got {self.timestamp}")

        # Validate vectors
        for name, v in [
            ("com_position_world", self.com_position_world),
            ("com_velocity_world", self.com_velocity_world),
            ("angular_momentum_about_com_world", self.angular_momentum_about_com_world),
        ]:
            if not vec3_is_finite(v):
                raise ValueError(f"{name} must contain finite numbers, got {v}")

        # Validate and normalize quaternion
        if not quat_is_finite(self.orientation_quat_world):
            raise ValueError(f"orientation_quat_world must be finite, got {self.orientation_quat_world}")
        ql = quat_length(self.orientation_quat_world)
        if ql < 1e-12:
            raise ValueError(f"orientation_quat_world is degenerate with zero norm: {self.orientation_quat_world}")
        
        # Ensure exact unit quaternion is stored
        q_norm = quat_normalize(self.orientation_quat_world)
        object.__setattr__(self, "orientation_quat_world", q_norm)

        # Validate inertia tensor
        if not isinstance(self.inertia_tensor_body, InertiaTensor3x3):
            raise TypeError(f"inertia_tensor_body must be InertiaTensor3x3, got {type(self.inertia_tensor_body)}")

    @property
    def rotation_matrix_world(self) -> Matrix3x3:
        """Active Body-to-World rotation matrix R in SO(3): v_world = R * v_body."""
        return quat_to_rot_matrix(self.orientation_quat_world)

    @property
    def inertia_tensor_world(self) -> InertiaTensor3x3:
        """Current whole-body inertia tensor in World coordinates: I_world = R * I_body * R^T."""
        return self.inertia_tensor_body.rotate(self.rotation_matrix_world)

    @property
    def angular_velocity_world(self) -> Vec3:
        """Current instantaneous angular velocity in World coordinates: omega = I_world^-1 * L_world."""
        return self.inertia_tensor_world.solve_angular_velocity(self.angular_momentum_about_com_world)

    @property
    def linear_momentum_world(self) -> Vec3:
        """Linear momentum vector in World coordinates: P = mass * v."""
        return vec3_scale(self.com_velocity_world, self.mass)

    @property
    def rotational_kinetic_energy(self) -> float:
        """Rotational kinetic energy: T_rot = 0.5 * omega . L."""
        omega = self.angular_velocity_world
        return 0.5 * vec3_dot(omega, self.angular_momentum_about_com_world)

    @property
    def translational_kinetic_energy(self) -> float:
        """Translational kinetic energy: T_trans = 0.5 * mass * ||v||^2."""
        return 0.5 * self.mass * vec3_length_sq(self.com_velocity_world)

    @property
    def total_kinetic_energy(self) -> float:
        """Total kinetic energy: T_tot = T_trans + T_rot."""
        return self.translational_kinetic_energy + self.rotational_kinetic_energy


@dataclass(frozen=True)
class ForwardDynamicsStepInput:
    """Complete collection of forces, torques, gravity, and timing for a single step integration."""
    contact_forces: Tuple[ContactForcePoint, ...] = ()
    external_forces_world: Tuple[Vec3, ...] = ()
    external_torques_about_com_world: Tuple[Vec3, ...] = ()
    gravity_acceleration_world: Vec3 = (0.0, 0.0, -9.81)
    dt: float = 1.0 / 24.0
    target_linear_acceleration_world: Optional[Vec3] = None
    target_angular_momentum_rate_world: Optional[Vec3] = None

    def __post_init__(self):
        # Validate dt
        if not math.isfinite(self.dt) or self.dt <= 0.0:
            raise ValueError(f"dt must be strictly positive and finite, got {self.dt}")

        # Validate gravity
        if not vec3_is_finite(self.gravity_acceleration_world):
            raise ValueError(f"gravity_acceleration_world must be finite, got {self.gravity_acceleration_world}")

        # Check unique contact_ids in contact forces
        seen_ids = set()
        for cp in self.contact_forces:
            if not isinstance(cp, ContactForcePoint):
                raise TypeError(f"contact_forces elements must be ContactForcePoint, got {type(cp)}")
            if cp.contact_id:
                if cp.contact_id in seen_ids:
                    raise ValueError(f"Duplicate contact_id detected in step input: '{cp.contact_id}'")
                seen_ids.add(cp.contact_id)

        # Validate external forces
        for ef in self.external_forces_world:
            if not vec3_is_finite(ef):
                raise ValueError(f"external_forces_world element contains non-finite numbers: {ef}")

        # Validate external torques
        for et in self.external_torques_about_com_world:
            if not vec3_is_finite(et):
                raise ValueError(f"external_torques_about_com_world element contains non-finite numbers: {et}")

        # Validate targets if provided
        if self.target_linear_acceleration_world is not None:
            if not vec3_is_finite(self.target_linear_acceleration_world):
                raise ValueError(
                    f"target_linear_acceleration_world must be finite, got {self.target_linear_acceleration_world}"
                )
        if self.target_angular_momentum_rate_world is not None:
            if not vec3_is_finite(self.target_angular_momentum_rate_world):
                raise ValueError(
                    f"target_angular_momentum_rate_world must be finite, got {self.target_angular_momentum_rate_world}"
                )

    @classmethod
    def from_solution_and_specs(
        cls,
        solution: Any,  # ContactForceSolution
        specs: Sequence[Any],  # ContactConstraintSpec
        external_forces_world: Sequence[Vec3] = (),
        external_torques_about_com_world: Sequence[Vec3] = (),
        gravity_acceleration_world: Vec3 = (0.0, 0.0, -9.81),
        dt: float = 1.0 / 24.0,
        target_linear_acceleration_world: Optional[Vec3] = None,
        target_angular_momentum_rate_world: Optional[Vec3] = None,
    ) -> "ForwardDynamicsStepInput":
        """Convenience factory: convert solver solution + contact specs into forward step inputs."""
        points: List[ContactForcePoint] = []
        for c in specs:
            f = solution.contact_forces.get(c.contact_id, (0.0, 0.0, 0.0))
            points.append(
                ContactForcePoint(
                    contact_point_world=c.contact_point_world,
                    contact_force_world=f,
                    contact_id=c.contact_id,
                )
            )
        return cls(
            contact_forces=tuple(points),
            external_forces_world=tuple(external_forces_world),
            external_torques_about_com_world=tuple(external_torques_about_com_world),
            gravity_acceleration_world=gravity_acceleration_world,
            dt=dt,
            target_linear_acceleration_world=target_linear_acceleration_world,
            target_angular_momentum_rate_world=target_angular_momentum_rate_world,
        )


@dataclass(frozen=True)
class ForwardDynamicsConfig:
    """Numerical parameters and tolerances for forward dynamics integration."""
    integration_method: str = "verlet"  # "verlet" (exact constant force), "symplectic", "euler"
    tolerance_positive_definite: float = 1e-8
    tolerance_quaternion_norm: float = 1e-7


@dataclass(frozen=True)
class ForwardDynamicsStepResult:
    """Comprehensive output of single-step forward dynamics integration."""
    status: ForwardDynamicsStatus
    state_next: ForwardDynamicsState
    net_force_world: Vec3
    net_torque_about_com_world: Vec3
    actual_linear_acceleration_world: Vec3
    actual_angular_momentum_rate_world: Vec3
    actual_angular_velocity_world: Vec3
    target_linear_acceleration_world: Optional[Vec3] = None
    target_angular_momentum_rate_world: Optional[Vec3] = None
    linear_acceleration_tracking_error: Optional[Vec3] = None
    angular_momentum_rate_tracking_error: Optional[Vec3] = None
    computation_time_sec: float = 0.0
    is_physically_valid: bool = True
    message: str = ""


# =============================================================================
# 5. Core Single-Step Integration Algorithm
# =============================================================================

def integrate_forward_dynamics_single_step(
    state: ForwardDynamicsState,
    step_input: ForwardDynamicsStepInput,
    config: Optional[ForwardDynamicsConfig] = None,
) -> ForwardDynamicsStepResult:
    """Perform a mathematically rigorous single-step forward dynamics integration.

    Equations of Motion (Newton-Euler 6-DOF):
    1. Linear Momentum (Newton's 2nd Law):
       F_net = sum(F_c,i) + sum(F_ext,j) + mass * gravity
       a_actual = F_net / mass
       v_next = v_curr + a_actual * dt
       p_next = p_curr + v_curr * dt + 0.5 * a_actual * dt^2 (Velocity Verlet exact for constant force)

    2. Angular Momentum & Attitude (Euler's Rotational Equations):
       tau_net = sum((p_c,i - com_curr) x F_c,i) + sum(tau_ext,j)
       L_next = L_curr + tau_net * dt
       I_world = R(q_curr) * I_body * R(q_curr)^T
       omega_mid = I_world^-1 * (L_curr + 0.5 * tau_net * dt)
       Delta_q = exp(0.5 * omega_mid * dt)  (Exact exponential map on SO(3))
       q_next = normalize(Delta_q * q_curr)
    """
    t0 = time.perf_counter()
    cfg = config or ForwardDynamicsConfig()

    # -------------------------------------------------------------------------
    # 1. Defensive Input Validation
    # -------------------------------------------------------------------------
    try:
        if not isinstance(state, ForwardDynamicsState):
            raise TypeError(f"state must be ForwardDynamicsState, got {type(state)}")
        if not isinstance(step_input, ForwardDynamicsStepInput):
            raise TypeError(f"step_input must be ForwardDynamicsStepInput, got {type(step_input)}")

        # Verify positive definiteness of body inertia tensor
        if not state.inertia_tensor_body.is_positive_definite(tol=cfg.tolerance_positive_definite):
            return ForwardDynamicsStepResult(
                status=ForwardDynamicsStatus.SINGULAR_INERTIA,
                state_next=state,  # Input state strictly unmodified
                net_force_world=(0.0, 0.0, 0.0),
                net_torque_about_com_world=(0.0, 0.0, 0.0),
                actual_linear_acceleration_world=(0.0, 0.0, 0.0),
                actual_angular_momentum_rate_world=(0.0, 0.0, 0.0),
                actual_angular_velocity_world=(0.0, 0.0, 0.0),
                computation_time_sec=time.perf_counter() - t0,
                is_physically_valid=False,
                message=(
                    f"SINGULAR_INERTIA: Body inertia tensor is not strictly positive-definite "
                    f"(det={state.inertia_tensor_body.determinant():.4e})"
                ),
            )
    except (ValueError, TypeError) as exc:
        return ForwardDynamicsStepResult(
            status=ForwardDynamicsStatus.INVALID_INPUT,
            state_next=state,  # Input state strictly unmodified
            net_force_world=(0.0, 0.0, 0.0),
            net_torque_about_com_world=(0.0, 0.0, 0.0),
            actual_linear_acceleration_world=(0.0, 0.0, 0.0),
            actual_angular_momentum_rate_world=(0.0, 0.0, 0.0),
            actual_angular_velocity_world=(0.0, 0.0, 0.0),
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message=f"INVALID_INPUT: {exc}",
        )

    # -------------------------------------------------------------------------
    # 2. Linear Force and Torque Evaluation
    # -------------------------------------------------------------------------
    m = state.mass
    com = state.com_position_world
    dt = step_input.dt

    # Contact forces and their moments about Whole-Body CoM
    f_contact_x, f_contact_y, f_contact_z = 0.0, 0.0, 0.0
    tau_contact_x, tau_contact_y, tau_contact_z = 0.0, 0.0, 0.0

    for cp in step_input.contact_forces:
        Fx, Fy, Fz = cp.contact_force_world
        f_contact_x += Fx
        f_contact_y += Fy
        f_contact_z += Fz

        # r_i = p_contact - CoM
        rx = cp.contact_point_world[0] - com[0]
        ry = cp.contact_point_world[1] - com[1]
        rz = cp.contact_point_world[2] - com[2]

        # tau_i = r_i x F_i
        tau_contact_x += ry * Fz - rz * Fy
        tau_contact_y += rz * Fx - rx * Fz
        tau_contact_z += rx * Fy - ry * Fx

    # Additional external forces
    f_ext_x = sum(ef[0] for ef in step_input.external_forces_world)
    f_ext_y = sum(ef[1] for ef in step_input.external_forces_world)
    f_ext_z = sum(ef[2] for ef in step_input.external_forces_world)

    # Additional external torques about CoM
    tau_ext_x = sum(et[0] for et in step_input.external_torques_about_com_world)
    tau_ext_y = sum(et[1] for et in step_input.external_torques_about_com_world)
    tau_ext_z = sum(et[2] for et in step_input.external_torques_about_com_world)

    # Gravity force: F_grav = mass * gravity
    gx, gy, gz = step_input.gravity_acceleration_world
    f_grav_x = m * gx
    f_grav_y = m * gy
    f_grav_z = m * gz
    # Note: Gravity acts through CoM, so tau_grav_about_com = (0, 0, 0) identically.

    # Net force and net torque
    F_net: Vec3 = (
        f_contact_x + f_ext_x + f_grav_x,
        f_contact_y + f_ext_y + f_grav_y,
        f_contact_z + f_ext_z + f_grav_z,
    )
    tau_net: Vec3 = (
        tau_contact_x + tau_ext_x,
        tau_contact_y + tau_ext_y,
        tau_contact_z + tau_ext_z,
    )

    if not vec3_is_finite(F_net) or not vec3_is_finite(tau_net):
        return ForwardDynamicsStepResult(
            status=ForwardDynamicsStatus.NUMERICAL_FAILURE,
            state_next=state,
            net_force_world=F_net,
            net_torque_about_com_world=tau_net,
            actual_linear_acceleration_world=(0.0, 0.0, 0.0),
            actual_angular_momentum_rate_world=(0.0, 0.0, 0.0),
            actual_angular_velocity_world=(0.0, 0.0, 0.0),
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message="NUMERICAL_FAILURE: Non-finite net force or net torque encountered",
        )

    # -------------------------------------------------------------------------
    # 3. Linear Kinematic Integration (CoM Acceleration, Velocity & Position)
    # -------------------------------------------------------------------------
    # Linear acceleration: a = F_net / mass
    inv_m = 1.0 / m
    a_actual: Vec3 = (F_net[0] * inv_m, F_net[1] * inv_m, F_net[2] * inv_m)

    # Velocity and position update:
    v_curr = state.com_velocity_world
    p_curr = state.com_position_world

    v_next: Vec3 = (
        v_curr[0] + a_actual[0] * dt,
        v_curr[1] + a_actual[1] * dt,
        v_curr[2] + a_actual[2] * dt,
    )

    if cfg.integration_method == "euler":
        # Explicit Euler
        p_next: Vec3 = (
            p_curr[0] + v_curr[0] * dt,
            p_curr[1] + v_curr[1] * dt,
            p_curr[2] + v_curr[2] * dt,
        )
    elif cfg.integration_method == "symplectic":
        # Symplectic / Semi-implicit Euler
        p_next = (
            p_curr[0] + v_next[0] * dt,
            p_curr[1] + v_next[1] * dt,
            p_curr[2] + v_next[2] * dt,
        )
    else:
        # Default: Velocity Verlet exact constant-acceleration formulation
        # p_next = p_curr + v_curr * dt + 0.5 * a * dt^2
        half_dt_sq = 0.5 * dt * dt
        p_next = (
            p_curr[0] + v_curr[0] * dt + a_actual[0] * half_dt_sq,
            p_curr[1] + v_curr[1] * dt + a_actual[1] * half_dt_sq,
            p_curr[2] + v_curr[2] * dt + a_actual[2] * half_dt_sq,
        )

    # -------------------------------------------------------------------------
    # 4. Rotational Integration (Angular Momentum, Velocity & Attitude Quaternion)
    # -------------------------------------------------------------------------
    # Angular momentum update: L_next = L_curr + tau_net * dt
    L_curr = state.angular_momentum_about_com_world
    L_next: Vec3 = (
        L_curr[0] + tau_net[0] * dt,
        L_curr[1] + tau_net[1] * dt,
        L_curr[2] + tau_net[2] * dt,
    )
    L_dot_actual = tau_net

    # Evaluate current rotation matrix and world inertia tensor
    q_curr = state.orientation_quat_world
    R_curr = quat_to_rot_matrix(q_curr)
    I_body = state.inertia_tensor_body
    I_world_curr = I_body.rotate(R_curr)

    # Verify conditioning of world inertia tensor
    if not I_world_curr.is_positive_definite(tol=cfg.tolerance_positive_definite):
        return ForwardDynamicsStepResult(
            status=ForwardDynamicsStatus.SINGULAR_INERTIA,
            state_next=state,
            net_force_world=F_net,
            net_torque_about_com_world=tau_net,
            actual_linear_acceleration_world=a_actual,
            actual_angular_momentum_rate_world=L_dot_actual,
            actual_angular_velocity_world=(0.0, 0.0, 0.0),
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message=(
                f"SINGULAR_INERTIA: World inertia tensor became singular/non-positive-definite "
                f"(det={I_world_curr.determinant():.4e})"
            ),
        )

    # Current angular velocity: omega_curr = I_world^-1 * L_curr
    try:
        omega_curr = I_world_curr.solve_angular_velocity(L_curr, tol=cfg.tolerance_positive_definite)
    except Exception as exc:
        return ForwardDynamicsStepResult(
            status=ForwardDynamicsStatus.SINGULAR_INERTIA,
            state_next=state,
            net_force_world=F_net,
            net_torque_about_com_world=tau_net,
            actual_linear_acceleration_world=a_actual,
            actual_angular_momentum_rate_world=L_dot_actual,
            actual_angular_velocity_world=(0.0, 0.0, 0.0),
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message=f"SINGULAR_INERTIA: Failed to solve angular velocity: {exc}",
        )

    # Midpoint angular momentum for second-order accurate attitude integration
    L_mid: Vec3 = (
        L_curr[0] + 0.5 * tau_net[0] * dt,
        L_curr[1] + 0.5 * tau_net[1] * dt,
        L_curr[2] + 0.5 * tau_net[2] * dt,
    )
    omega_mid = I_world_curr.solve_angular_velocity(L_mid, tol=cfg.tolerance_positive_definite)

    # Exponential map quaternion update on SO(3):
    # theta = ||omega_mid|| * dt
    # Delta_q = (cos(theta/2), sin(theta/2) * (omega_mid / ||omega_mid||))
    # q_next = normalize(Delta_q * q_curr)
    omega_mag = vec3_length(omega_mid)
    theta = omega_mag * dt

    if theta < 1e-12:
        # Stationary or vanishing rotation: quaternion is strictly invariant
        q_next = q_curr
    else:
        half_theta = 0.5 * theta
        s = math.sin(half_theta) / omega_mag
        c = math.cos(half_theta)
        delta_q = (c, omega_mid[0] * s, omega_mid[1] * s, omega_mid[2] * s)
        # Active world rotation: q_next = delta_q * q_curr
        q_next_unnorm = quat_multiply(delta_q, q_curr)
        q_next = quat_normalize(q_next_unnorm)

    # Re-evaluate next world inertia tensor and next angular velocity
    R_next = quat_to_rot_matrix(q_next)
    I_world_next = I_body.rotate(R_next)
    omega_next = I_world_next.solve_angular_velocity(L_next, tol=cfg.tolerance_positive_definite)

    # Check finite numbers on all updated state quantities
    if (
        not vec3_is_finite(p_next)
        or not vec3_is_finite(v_next)
        or not vec3_is_finite(L_next)
        or not quat_is_finite(q_next)
    ):
        return ForwardDynamicsStepResult(
            status=ForwardDynamicsStatus.NUMERICAL_FAILURE,
            state_next=state,
            net_force_world=F_net,
            net_torque_about_com_world=tau_net,
            actual_linear_acceleration_world=a_actual,
            actual_angular_momentum_rate_world=L_dot_actual,
            actual_angular_velocity_world=omega_curr,
            computation_time_sec=time.perf_counter() - t0,
            is_physically_valid=False,
            message="NUMERICAL_FAILURE: Non-finite numbers detected in updated kinematic state",
        )

    # -------------------------------------------------------------------------
    # 5. Assemble Next State & Diagnostics
    # -------------------------------------------------------------------------
    state_next = ForwardDynamicsState(
        timestamp=state.timestamp + dt,
        mass=state.mass,
        com_position_world=p_next,
        com_velocity_world=v_next,
        angular_momentum_about_com_world=L_next,
        orientation_quat_world=q_next,
        inertia_tensor_body=state.inertia_tensor_body,  # Constant body-fixed inertia
    )

    # Diagnostic tracking error against reference targets (if provided)
    err_a = None
    if step_input.target_linear_acceleration_world is not None:
        err_a = vec3_sub(a_actual, step_input.target_linear_acceleration_world)

    err_L_dot = None
    if step_input.target_angular_momentum_rate_world is not None:
        err_L_dot = vec3_sub(L_dot_actual, step_input.target_angular_momentum_rate_world)

    t_calc = time.perf_counter() - t0
    msg = (
        f"SUCCESS: Integrated 1 step dt={dt:.4f}s. "
        f"||F_net||={vec3_length(F_net):.2f}N, ||tau_net||={vec3_length(tau_net):.2f}N*m. "
        f"p_com=({p_next[0]:.3f}, {p_next[1]:.3f}, {p_next[2]:.3f})m."
    )

    return ForwardDynamicsStepResult(
        status=ForwardDynamicsStatus.SUCCESS,
        state_next=state_next,
        net_force_world=F_net,
        net_torque_about_com_world=tau_net,
        actual_linear_acceleration_world=a_actual,
        actual_angular_momentum_rate_world=L_dot_actual,
        actual_angular_velocity_world=omega_next,
        target_linear_acceleration_world=step_input.target_linear_acceleration_world,
        target_angular_momentum_rate_world=step_input.target_angular_momentum_rate_world,
        linear_acceleration_tracking_error=err_a,
        angular_momentum_rate_tracking_error=err_L_dot,
        computation_time_sec=t_calc,
        is_physically_valid=True,
        message=msg,
    )
