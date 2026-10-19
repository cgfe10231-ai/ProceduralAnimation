"""Rigid link inertia tensors and whole-body angular momentum model (Task 6G-B).

Implements the inertial properties of human mass segments and evaluates the whole-body
inertia tensor and angular momentum relative to the whole-body Center of Mass (CoM).

Key Capabilities:
- Defines mathematically rigorous 3x3 symmetric InertiaTensor data structure supporting:
  * Sylvester criterion positive-definiteness check
  * Exact Cardano principal moments of inertia (eigenvalues)
  * SO(3) coordinate transformation (R * I * R^T)
  * 3D Parallel Axis Theorem (Steiner's theorem)
- Provides configurable segment geometric models (ellipsoids, cylinders, boxes, elliptic cylinders)
  conforming to biomechanical literature (Dempster 1955, Hanavan 1964, Winter 2009).
- Evaluates whole-body inertia tensor relative to whole-body CoM:
  * Translation invariant: whole-body translation does not alter inertia relative to CoM.
  * Rotation covariant: whole-body rotation transforms inertia according to tensor laws.
  * Reflects postural changes (tuck vs extend, limb raising).
- Computes multi-link whole-body angular momentum relative to CoM:
  * Spin angular momentum (segment rotation about own CoM: I_world * omega)
  * Orbital angular momentum (segment CoM orbital motion relative to body CoM: r x (m * v))
  * Analytically consistent with rigid-body formula I_body * omega under rigid body rotation.
- Seamless integration with BodyPoseSnapshot, BodyVelocityState, and MotionState.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import bpy
from mathutils import Matrix, Quaternion, Vector

from src.motion.rigid_link import (
    BodyMassDistribution,
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    DEMPSTER_13_SEGMENT_MODEL,
    RigidSegmentSpec,
    SegmentCoMResult,
    WholeBodyCoMResult,
    compute_whole_body_com,
)
from src.motion.body_kinematics import (
    BodyPoseSnapshot,
    BodyVelocityState,
    BodyMotionState,
)


# =============================================================================
# 1. InertiaTensor 3x3 Symmetric Matrix Representation
# =============================================================================

@dataclass(frozen=True)
class InertiaTensor:
    """Rigorous 3x3 symmetric inertia tensor representation in SI units (kg*m^2).

    Matrix form:
        [ I_xx   I_xy   I_xz ]
        [ I_xy   I_yy   I_yz ]
        [ I_xz   I_yz   I_zz ]
    """
    ixx: float
    iyy: float
    izz: float
    ixy: float = 0.0
    ixz: float = 0.0
    iyz: float = 0.0

    @classmethod
    def from_diagonal(cls, ixx: float, iyy: float, izz: float) -> "InertiaTensor":
        """Construct diagonal inertia tensor (principal axes aligned)."""
        return cls(ixx=float(ixx), iyy=float(iyy), izz=float(izz), ixy=0.0, ixz=0.0, iyz=0.0)

    @classmethod
    def from_matrix(cls, mat: Sequence[Sequence[float]]) -> "InertiaTensor":
        """Construct InertiaTensor from a 3x3 matrix-like object."""
        ixx = float(mat[0][0])
        iyy = float(mat[1][1])
        izz = float(mat[2][2])
        ixy = 0.5 * (float(mat[0][1]) + float(mat[1][0]))
        ixz = 0.5 * (float(mat[0][2]) + float(mat[2][0]))
        iyz = 0.5 * (float(mat[1][2]) + float(mat[2][1]))
        return cls(ixx=ixx, iyy=iyy, izz=izz, ixy=ixy, ixz=ixz, iyz=iyz)

    @classmethod
    def zero(cls) -> "InertiaTensor":
        """Construct zero inertia tensor."""
        return cls(ixx=0.0, iyy=0.0, izz=0.0, ixy=0.0, ixz=0.0, iyz=0.0)

    def to_matrix(self) -> Matrix:
        """Convert to a Blender mathutils.Matrix (3x3)."""
        return Matrix((
            (self.ixx, self.ixy, self.ixz),
            (self.ixy, self.iyy, self.iyz),
            (self.ixz, self.iyz, self.izz),
        ))

    def to_tuple(self) -> Tuple[Tuple[float, float, float], ...]:
        """Convert to nested 3x3 tuple of floats."""
        return (
            (self.ixx, self.ixy, self.ixz),
            (self.ixy, self.iyy, self.iyz),
            (self.ixz, self.iyz, self.izz),
        )

    def is_symmetric(self, tol: float = 1e-7) -> bool:
        """By construction, InertiaTensor stores symmetric off-diagonals."""
        return True

    def is_positive_definite(self, tol: float = 1e-8) -> bool:
        """Check positive-definiteness: all principal moments (eigenvalues) > tol."""
        e1, e2, e3 = self.principal_moments()
        return (e1 > tol) and (e2 > tol) and (e3 > tol)

    def determinant(self) -> float:
        """Determinant of the 3x3 inertia matrix."""
        return (
            self.ixx * (self.iyy * self.izz - self.iyz * self.iyz)
            - self.ixy * (self.ixy * self.izz - self.iyz * self.ixz)
            + self.ixz * (self.ixy * self.iyz - self.iyy * self.ixz)
        )

    def trace(self) -> float:
        """Trace of the inertia matrix I_xx + I_yy + I_zz."""
        return self.ixx + self.iyy + self.izz

    def principal_moments(self) -> Tuple[float, float, float]:
        """Compute the 3 principal moments of inertia (eigenvalues) via Cardano's analytical algorithm."""
        m = self.to_matrix()
        p1 = m[0][1] ** 2 + m[0][2] ** 2 + m[1][2] ** 2
        q = (m[0][0] + m[1][1] + m[2][2]) / 3.0

        if p1 < 1e-14:
            vals = sorted([m[0][0], m[1][1], m[2][2]])
            return (vals[0], vals[1], vals[2])

        p2 = (m[0][0] - q) ** 2 + (m[1][1] - q) ** 2 + (m[2][2] - q) ** 2 + 2.0 * p1
        p = math.sqrt(p2 / 6.0)
        if p < 1e-14:
            return (q, q, q)

        inv_p = 1.0 / p
        b00 = (m[0][0] - q) * inv_p
        b11 = (m[1][1] - q) * inv_p
        b22 = (m[2][2] - q) * inv_p
        b01 = m[0][1] * inv_p
        b02 = m[0][2] * inv_p
        b12 = m[1][2] * inv_p

        det_b = (
            b00 * (b11 * b22 - b12 * b12)
            - b01 * (b01 * b22 - b12 * b02)
            + b02 * (b01 * b12 - b11 * b02)
        )
        r = det_b / 2.0
        r = max(-1.0, min(1.0, r))

        phi = math.acos(r) / 3.0
        eig1 = q + 2.0 * p * math.cos(phi)
        eig3 = q + 2.0 * p * math.cos(phi + 2.0 * math.pi / 3.0)
        eig2 = 3.0 * q - eig1 - eig3
        vals = sorted([eig1, eig2, eig3])
        return (vals[0], vals[1], vals[2])

    def rotate(self, r_mat: Union[Matrix, Sequence[Sequence[float]]]) -> "InertiaTensor":
        """Transform tensor into a new coordinate frame: I_new = R * I * R^T."""
        m_in = self.to_matrix()
        r = Matrix(r_mat).to_3x3() if not isinstance(r_mat, Matrix) else r_mat.to_3x3()
        m_out = r @ m_in @ r.transposed()
        return InertiaTensor.from_matrix(m_out)

    def parallel_axis(self, mass_kg: float, offset: Sequence[float]) -> "InertiaTensor":
        """Apply 3D Parallel Axis Theorem (Steiner's Theorem):

        I_offset = I_com + mass * ( ||r||^2 * E_3 - r * r^T )
        where offset r = (x, y, z) is the displacement vector from CoM to the new reference point.
        """
        x, y, z = float(offset[0]), float(offset[1]), float(offset[2])
        m = float(mass_kg)
        r_sq = x * x + y * y + z * z

        d_ixx = m * (r_sq - x * x)   # m * (y^2 + z^2)
        d_iyy = m * (r_sq - y * y)   # m * (x^2 + z^2)
        d_izz = m * (r_sq - z * z)   # m * (x^2 + y^2)
        d_ixy = -m * (x * y)
        d_ixz = -m * (x * z)
        d_iyz = -m * (y * z)

        return InertiaTensor(
            ixx=self.ixx + d_ixx,
            iyy=self.iyy + d_iyy,
            izz=self.izz + d_izz,
            ixy=self.ixy + d_ixy,
            ixz=self.ixz + d_ixz,
            iyz=self.iyz + d_iyz,
        )

    def multiply(self, vec: Sequence[float]) -> Vector:
        """Multiply tensor by 3D angular velocity vector: H = I * omega."""
        vx, vy, vz = float(vec[0]), float(vec[1]), float(vec[2])
        return Vector((
            self.ixx * vx + self.ixy * vy + self.ixz * vz,
            self.ixy * vx + self.iyy * vy + self.iyz * vz,
            self.ixz * vx + self.iyz * vy + self.izz * vz,
        ))

    def frobenius_norm(self) -> float:
        """Compute Frobenius norm of the 3x3 inertia matrix."""
        return math.sqrt(
            self.ixx ** 2 + self.iyy ** 2 + self.izz ** 2
            + 2.0 * (self.ixy ** 2 + self.ixz ** 2 + self.iyz ** 2)
        )

    def __add__(self, other: "InertiaTensor") -> "InertiaTensor":
        return InertiaTensor(
            ixx=self.ixx + other.ixx,
            iyy=self.iyy + other.iyy,
            izz=self.izz + other.izz,
            ixy=self.ixy + other.ixy,
            ixz=self.ixz + other.ixz,
            iyz=self.iyz + other.iyz,
        )

    def __sub__(self, other: "InertiaTensor") -> "InertiaTensor":
        return InertiaTensor(
            ixx=self.ixx - other.ixx,
            iyy=self.iyy - other.iyy,
            izz=self.izz - other.izz,
            ixy=self.ixy - other.ixy,
            ixz=self.ixz - other.ixz,
            iyz=self.iyz - other.iyz,
        )

    def __mul__(self, scalar: float) -> "InertiaTensor":
        s = float(scalar)
        return InertiaTensor(
            ixx=self.ixx * s,
            iyy=self.iyy * s,
            izz=self.izz * s,
            ixy=self.ixy * s,
            ixz=self.ixz * s,
            iyz=self.iyz * s,
        )


# =============================================================================
# 2. Segment Geometry & Local Inertia Model
# =============================================================================

@dataclass(frozen=True)
class SegmentGeometrySpec:
    """Configurable geometric specification used to compute a segment's local inertia tensor.

    Bone coordinate frame conventions (CharacterArmature):
        +Y: Longitudinal axis (from bone head/proximal to bone tail/distal).
        +X: Lateral / transverse axis (character right).
        +Z: Anterior-posterior / sagittal axis (character front/back or dorsal/ventral).

    Attributes:
        segment_id: Unique segment identifier matching RigidSegmentSpec.
        shape_type: Geometric primitive approximation:
            - 'cylinder': Circular cylinder along longitudinal +Y (radius, length).
            - 'elliptic_cylinder': Elliptical cylinder along +Y (radius_x, radius_z, length).
            - 'ellipsoid': 3D Ellipsoid (semi-axes radius_x, radius_y, radius_z).
            - 'box': Rectangular cuboid (dim_x, dim_y, dim_z).
            - 'custom': Directly specified custom diagonal inertia moments.
        radius_x: Semi-axis along local X (meters).
        radius_y: Semi-axis along local Y (meters). For ellipsoid, half-length.
        radius_z: Semi-axis along local Z (meters).
        nominal_length: Reference segment length (meters).
        dim_x: Box dimension along local X (meters).
        dim_y: Box dimension along local Y (meters).
        dim_z: Box dimension along local Z (meters).
        custom_moments: Optional (I_xx, I_yy, I_zz) for 'custom' shape_type.
        description: Biomechanical notes or references.
    """
    segment_id: str
    shape_type: str = "cylinder"
    radius_x: float = 0.05
    radius_y: float = 0.05
    radius_z: float = 0.05
    nominal_length: float = 0.30
    dim_x: float = 0.0
    dim_y: float = 0.0
    dim_z: float = 0.0
    custom_moments: Optional[Tuple[float, float, float]] = None
    description: str = ""

    def compute_local_tensor(
        self,
        mass_kg: float,
        actual_length: Optional[float] = None,
    ) -> InertiaTensor:
        """Compute the segment's local inertia tensor relative to its own CoM (kg*m^2).

        In local bone coordinates, longitudinal axis is +Y.
        """
        if mass_kg <= 0.0:
            raise ValueError(f"Segment '{self.segment_id}' mass must be > 0, got {mass_kg}")

        length = actual_length if actual_length is not None and actual_length > 0.0 else self.nominal_length
        m = mass_kg

        if self.shape_type == "custom" and self.custom_moments is not None:
            return InertiaTensor.from_diagonal(
                self.custom_moments[0],
                self.custom_moments[1],
                self.custom_moments[2],
            )

        if self.shape_type == "cylinder":
            # Circular cylinder along Y axis:
            # I_yy = 0.5 * m * r^2
            # I_xx = I_zz = (1/12) * m * (3 * r^2 + L^2)
            r = self.radius_x
            iyy = 0.5 * m * (r * r)
            ixx = (1.0 / 12.0) * m * (3.0 * r * r + length * length)
            izz = ixx
            return InertiaTensor.from_diagonal(ixx, iyy, izz)

        if self.shape_type == "elliptic_cylinder":
            # Elliptical cylinder along Y axis (semi-axes rx, rz):
            # I_yy = 0.25 * m * (rx^2 + rz^2)
            # I_xx = (1/12) * m * (3 * rz^2 + L^2)
            # I_zz = (1/12) * m * (3 * rx^2 + L^2)
            rx = self.radius_x
            rz = self.radius_z
            iyy = 0.25 * m * (rx * rx + rz * rz)
            ixx = (1.0 / 12.0) * m * (3.0 * rz * rz + length * length)
            izz = (1.0 / 12.0) * m * (3.0 * rx * rx + length * length)
            return InertiaTensor.from_diagonal(ixx, iyy, izz)

        if self.shape_type == "ellipsoid":
            # Ellipsoid with semi-axes a=rx, b=ry, c=rz:
            # I_xx = (1/5) * m * (b^2 + c^2)
            # I_yy = (1/5) * m * (a^2 + c^2)
            # I_zz = (1/5) * m * (a^2 + b^2)
            a = self.radius_x
            b = self.radius_y if self.radius_y > 0.0 else (length * 0.5)
            c = self.radius_z
            ixx = 0.2 * m * (b * b + c * c)
            iyy = 0.2 * m * (a * a + c * c)
            izz = 0.2 * m * (a * a + b * b)
            return InertiaTensor.from_diagonal(ixx, iyy, izz)

        if self.shape_type == "box":
            # Rectangular cuboid with dimensions dx, dy, dz:
            # I_xx = (1/12) * m * (dy^2 + dz^2)
            # I_yy = (1/12) * m * (dx^2 + dz^2)
            # I_zz = (1/12) * m * (dx^2 + dy^2)
            dx = self.dim_x if self.dim_x > 0.0 else (self.radius_x * 2.0)
            dy = self.dim_y if self.dim_y > 0.0 else length
            dz = self.dim_z if self.dim_z > 0.0 else (self.radius_z * 2.0)
            ixx = (1.0 / 12.0) * m * (dy * dy + dz * dz)
            iyy = (1.0 / 12.0) * m * (dx * dx + dz * dz)
            izz = (1.0 / 12.0) * m * (dx * dx + dy * dy)
            return InertiaTensor.from_diagonal(ixx, iyy, izz)

        # Fallback generic slender rod
        ixx = (1.0 / 12.0) * m * (length * length)
        iyy = 0.001 * m
        izz = ixx
        return InertiaTensor.from_diagonal(ixx, iyy, izz)


@dataclass(frozen=True)
class BodyInertiaModel:
    """Whole-body inertia model mapping mass distribution to segment geometric parameters."""
    model_name: str
    source: str
    mass_distribution: BodyMassDistribution
    geometries: Dict[str, SegmentGeometrySpec] = field(default_factory=dict)

    def get_geometry(self, segment_id: str) -> SegmentGeometrySpec:
        """Retrieve the geometry specification for a segment."""
        if segment_id in self.geometries:
            return self.geometries[segment_id]
        seg_spec = self.mass_distribution.get_segment(segment_id)
        # Default fallback geometry
        return SegmentGeometrySpec(
            segment_id=segment_id,
            shape_type="cylinder",
            radius_x=0.05,
            nominal_length=seg_spec.nominal_length,
        )

    def with_overrides(
        self,
        geometry_overrides: Dict[str, SegmentGeometrySpec],
        new_name: Optional[str] = None,
    ) -> "BodyInertiaModel":
        """Return a new BodyInertiaModel with updated segment geometries."""
        updated = dict(self.geometries)
        updated.update(geometry_overrides)
        return BodyInertiaModel(
            model_name=new_name or f"{self.model_name}_Custom",
            source=f"Derived from {self.source} with overrides",
            mass_distribution=self.mass_distribution,
            geometries=updated,
        )


# =============================================================================
# 3. Standard Predefined Anthropometric Inertia Models
# =============================================================================

# Standard 15-Segment Inertia Model based on Winter (2009) and Hanavan (1964)
# Approximates segments as ellipsoids, elliptical cylinders, circular cylinders, and boxes.
DEFAULT_15_SEGMENT_INERTIA_MODEL = BodyInertiaModel(
    model_name="WinterHanavan15",
    source="Winter (2009) Table 4.1 / Hanavan (1964) standard anthropometric geometric solids",
    mass_distribution=DEMPSTER_WINTER_15_SEGMENT_MODEL,
    geometries={
        "head": SegmentGeometrySpec(
            segment_id="head",
            shape_type="ellipsoid",
            radius_x=0.080,   # Half-breadth 8 cm
            radius_y=0.110,   # Half-height 11 cm
            radius_z=0.090,   # Half-depth 9 cm
            nominal_length=0.22,
            description="Head modeled as triaxial ellipsoid",
        ),
        "torso": SegmentGeometrySpec(
            segment_id="torso",
            shape_type="elliptic_cylinder",
            radius_x=0.150,   # Chest half-width 15 cm
            radius_z=0.110,   # Chest half-depth 11 cm
            nominal_length=0.48,
            description="Thorax & Abdomen modeled as elliptical cylinder",
        ),
        "pelvis": SegmentGeometrySpec(
            segment_id="pelvis",
            shape_type="elliptic_cylinder",
            radius_x=0.160,   # Hip half-width 16 cm
            radius_z=0.120,   # Hip half-depth 12 cm
            nominal_length=0.18,
            description="Pelvis modeled as elliptical cylinder",
        ),
        "upper_arm_L": SegmentGeometrySpec(
            segment_id="upper_arm_L",
            shape_type="cylinder",
            radius_x=0.045,   # Radius 4.5 cm
            nominal_length=0.30,
            description="Left Upper Arm modeled as circular cylinder",
        ),
        "upper_arm_R": SegmentGeometrySpec(
            segment_id="upper_arm_R",
            shape_type="cylinder",
            radius_x=0.045,   # Radius 4.5 cm
            nominal_length=0.30,
            description="Right Upper Arm modeled as circular cylinder",
        ),
        "forearm_L": SegmentGeometrySpec(
            segment_id="forearm_L",
            shape_type="cylinder",
            radius_x=0.035,   # Radius 3.5 cm
            nominal_length=0.26,
            description="Left Forearm modeled as circular cylinder",
        ),
        "forearm_R": SegmentGeometrySpec(
            segment_id="forearm_R",
            shape_type="cylinder",
            radius_x=0.035,   # Radius 3.5 cm
            nominal_length=0.26,
            description="Right Forearm modeled as circular cylinder",
        ),
        "hand_L": SegmentGeometrySpec(
            segment_id="hand_L",
            shape_type="box",
            dim_x=0.080,      # Palm breadth 8 cm
            dim_y=0.100,      # Hand length 10 cm
            dim_z=0.025,      # Hand thickness 2.5 cm
            nominal_length=0.10,
            description="Left Hand modeled as rectangular box",
        ),
        "hand_R": SegmentGeometrySpec(
            segment_id="hand_R",
            shape_type="box",
            dim_x=0.080,
            dim_y=0.100,
            dim_z=0.025,
            nominal_length=0.10,
            description="Right Hand modeled as rectangular box",
        ),
        "thigh_L": SegmentGeometrySpec(
            segment_id="thigh_L",
            shape_type="cylinder",
            radius_x=0.075,   # Thigh radius 7.5 cm
            nominal_length=0.42,
            description="Left Thigh modeled as circular cylinder",
        ),
        "thigh_R": SegmentGeometrySpec(
            segment_id="thigh_R",
            shape_type="cylinder",
            radius_x=0.075,
            nominal_length=0.42,
            description="Right Thigh modeled as circular cylinder",
        ),
        "shin_L": SegmentGeometrySpec(
            segment_id="shin_L",
            shape_type="cylinder",
            radius_x=0.050,   # Shank radius 5.0 cm
            nominal_length=0.40,
            description="Left Shank modeled as circular cylinder",
        ),
        "shin_R": SegmentGeometrySpec(
            segment_id="shin_R",
            shape_type="cylinder",
            radius_x=0.050,
            nominal_length=0.40,
            description="Right Shank modeled as circular cylinder",
        ),
        "foot_L": SegmentGeometrySpec(
            segment_id="foot_L",
            shape_type="box",
            dim_x=0.080,      # Foot breadth 8 cm
            dim_y=0.154,      # Foot length 15.4 cm
            dim_z=0.050,      # Foot height 5 cm
            nominal_length=0.154,
            description="Left Foot modeled as rectangular box",
        ),
        "foot_R": SegmentGeometrySpec(
            segment_id="foot_R",
            shape_type="box",
            dim_x=0.080,
            dim_y=0.154,
            dim_z=0.050,
            nominal_length=0.154,
            description="Right Foot modeled as rectangular box",
        ),
    },
)

# Standard 13-Segment Inertia Model matching DEMPSTER_13_SEGMENT_MODEL
DEFAULT_13_SEGMENT_INERTIA_MODEL = BodyInertiaModel(
    model_name="WinterHanavan13Combined",
    source="Dempster/Winter with Forearm+Hand combined into LowerArm matching 13 placeholder meshes",
    mass_distribution=DEMPSTER_13_SEGMENT_MODEL,
    geometries={
        "Head": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["head"],
        "Torso": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["torso"],
        "Pelvis": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["pelvis"],
        "UpperArm_L": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["upper_arm_L"],
        "UpperArm_R": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["upper_arm_R"],
        "LowerArm_L": SegmentGeometrySpec(
            segment_id="LowerArm_L",
            shape_type="cylinder",
            radius_x=0.040,
            nominal_length=0.36,
            description="Combined Left Lower Arm & Hand cylinder",
        ),
        "LowerArm_R": SegmentGeometrySpec(
            segment_id="LowerArm_R",
            shape_type="cylinder",
            radius_x=0.040,
            nominal_length=0.36,
            description="Combined Right Lower Arm & Hand cylinder",
        ),
        "UpperLeg_L": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["thigh_L"],
        "UpperLeg_R": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["thigh_R"],
        "LowerLeg_L": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["shin_L"],
        "LowerLeg_R": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["shin_R"],
        "Foot_L": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["foot_L"],
        "Foot_R": DEFAULT_15_SEGMENT_INERTIA_MODEL.geometries["foot_R"],
    },
)


# =============================================================================
# 4. Result Dataclasses
# =============================================================================

@dataclass(frozen=True)
class SegmentInertiaState:
    """Evaluated inertial state and angular momentum contribution of a single segment."""
    segment_id: str
    bone_name: str
    mass_kg: float
    world_com: Tuple[float, float, float]
    displacement_from_body_com: Tuple[float, float, float]
    local_inertia: InertiaTensor            # Relative to segment CoM, in bone local frame
    world_inertia_com: InertiaTensor        # Relative to segment CoM, in world frame (R * I * R^T)
    world_inertia_body_com: InertiaTensor   # Relative to whole-body CoM (Parallel Axis Theorem)
    spin_angular_momentum: Tuple[float, float, float]    # World frame (kg*m^2/s)
    orbital_angular_momentum: Tuple[float, float, float] # World frame (kg*m^2/s)
    total_angular_momentum: Tuple[float, float, float]   # World frame (kg*m^2/s)


@dataclass(frozen=True)
class WholeBodyInertiaState:
    """Complete evaluated whole-body inertia tensor and multi-link angular momentum state."""
    time_sec: float
    frame: Optional[int]
    total_mass_kg: float
    com_world: Tuple[float, float, float]
    com_linear_velocity: Tuple[float, float, float]
    inertia_tensor_body_com: InertiaTensor          # Relative to whole-body CoM in world frame
    angular_momentum_body_com: Tuple[float, float, float] # Total H = H_spin + H_orbital (kg*m^2/s)
    spin_angular_momentum_total: Tuple[float, float, float]
    orbital_angular_momentum_total: Tuple[float, float, float]
    segments: Dict[str, SegmentInertiaState]
    reference_frame: str = "WORLD_Z_UP"
    reference_point: str = "WHOLE_BODY_COM"
    units: Dict[str, str] = field(default_factory=lambda: {
        "mass": "kg",
        "distance": "m",
        "linear_velocity": "m/s",
        "angular_velocity": "rad/s",
        "inertia": "kg*m^2",
        "angular_momentum": "kg*m^2/s",
    })

    @property
    def principal_moments(self) -> Tuple[float, float, float]:
        """Principal moments of inertia (eigenvalues) of the whole body relative to CoM."""
        return self.inertia_tensor_body_com.principal_moments()

    @property
    def angular_momentum_magnitude(self) -> float:
        """Magnitude of whole-body angular momentum vector in kg*m^2/s."""
        hx, hy, hz = self.angular_momentum_body_com
        return math.sqrt(hx * hx + hy * hy + hz * hz)


# =============================================================================
# 5. Core Evaluation Algorithms
# =============================================================================

def compute_whole_body_inertia(
    armature_obj: Optional[bpy.types.Object] = None,
    velocity_state: Optional[BodyVelocityState] = None,
    inertia_model: Optional[BodyInertiaModel] = None,
    update_scene: bool = True,
    time_sec: float = 0.0,
    frame: Optional[int] = None,
) -> WholeBodyInertiaState:
    """Compute whole-body inertia tensor and angular momentum from an evaluated Blender Armature.

    Non-destructive: Reads evaluated bone matrices without modifying rig or scene.

    Args:
        armature_obj: CharacterArmature object. Defaults to searching scene.
        velocity_state: Optional differential velocity state from Task 6G-A.
            If None, angular momentum is evaluated as zero.
        inertia_model: BodyInertiaModel specification. Defaults to DEFAULT_15_SEGMENT_INERTIA_MODEL.
        update_scene: If True, calls view_layer.update() before evaluation.
        time_sec: Timestamp in seconds.
        frame: Optional frame number.

    Returns:
        WholeBodyInertiaState containing whole-body inertia tensor and angular momentum breakdown.
    """
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")

    model = inertia_model if inertia_model is not None else DEFAULT_15_SEGMENT_INERTIA_MODEL
    mass_dist = model.mass_distribution

    # 1. Compute Whole-Body Center of Mass (CoM)
    com_res = compute_whole_body_com(
        armature_obj=armature_obj,
        mass_distribution=mass_dist,
        update_scene=update_scene,
    )
    com_world = com_res.com_world

    # Linear velocity of body CoM
    if velocity_state is not None:
        com_vel = Vector(velocity_state.com_linear_velocity)
        t_sec = velocity_state.time_sec
    else:
        com_vel = Vector((0.0, 0.0, 0.0))
        t_sec = time_sec

    # 2. Iterate segments and accumulate inertia and angular momentum
    seg_states: Dict[str, SegmentInertiaState] = {}
    accum_inertia = InertiaTensor.zero()
    total_spin_h = Vector((0.0, 0.0, 0.0))
    total_orbital_h = Vector((0.0, 0.0, 0.0))

    arm_mat_world = armature_obj.matrix_world

    for seg_spec in mass_dist.segments:
        seg_id = seg_spec.segment_id
        s_res = com_res.segments[seg_id]
        pb = armature_obj.pose.bones.get(seg_spec.bone_name)
        if pb is None:
            continue

        # A. Local inertia tensor relative to segment CoM in bone local frame
        geom = model.get_geometry(seg_id)
        local_tensor = geom.compute_local_tensor(
            mass_kg=s_res.mass_kg,
            actual_length=pb.length,
        )

        # B. World orientation matrix of segment: R_world = (arm_world @ pb.matrix).to_3x3()
        seg_mat_3x3 = (arm_mat_world.to_3x3() @ pb.matrix.to_3x3())
        # Normalize via quaternion to guarantee strictly orthogonal SO(3) matrix
        r_world = seg_mat_3x3.to_quaternion().to_matrix()

        # C. Transform local inertia to world orientation (relative to segment's OWN CoM)
        world_tensor_com_i = local_tensor.rotate(r_world)

        # D. Parallel Axis Theorem to whole-body CoM
        # Displacement vector r_i = segment_com - whole_body_com
        r_i = s_res.world_com - com_world
        world_tensor_body_com = world_tensor_com_i.parallel_axis(
            mass_kg=s_res.mass_kg,
            offset=r_i,
        )

        # Accumulate to whole-body inertia tensor
        accum_inertia = accum_inertia + world_tensor_body_com

        # E. Angular momentum terms
        spin_h = Vector((0.0, 0.0, 0.0))
        orbital_h = Vector((0.0, 0.0, 0.0))

        if velocity_state is not None:
            # Spin term: I_world * omega_world
            if seg_id in velocity_state.segment_angular_velocities:
                omega_w = Vector(velocity_state.segment_angular_velocities[seg_id])
                spin_h = world_tensor_com_i.multiply(omega_w)

            # Orbital term: r_i x (m * v_i)
            # Analytically: r_i x (m * (v_i - v_com)) == r_i x (m * v_i) since sum(m * r_i) == 0.
            if seg_id in velocity_state.segment_linear_velocities:
                v_w = Vector(velocity_state.segment_linear_velocities[seg_id])
                # Using relative velocity improves numerical conditioning
                v_rel = v_w - com_vel
                orbital_h = r_i.cross(s_res.mass_kg * v_rel)

        seg_total_h = spin_h + orbital_h
        total_spin_h += spin_h
        total_orbital_h += orbital_h

        seg_states[seg_id] = SegmentInertiaState(
            segment_id=seg_id,
            bone_name=seg_spec.bone_name,
            mass_kg=s_res.mass_kg,
            world_com=(s_res.world_com.x, s_res.world_com.y, s_res.world_com.z),
            displacement_from_body_com=(r_i.x, r_i.y, r_i.z),
            local_inertia=local_tensor,
            world_inertia_com=world_tensor_com_i,
            world_inertia_body_com=world_tensor_body_com,
            spin_angular_momentum=(spin_h.x, spin_h.y, spin_h.z),
            orbital_angular_momentum=(orbital_h.x, orbital_h.y, orbital_h.z),
            total_angular_momentum=(seg_total_h.x, seg_total_h.y, seg_total_h.z),
        )

    total_h = total_spin_h + total_orbital_h

    return WholeBodyInertiaState(
        time_sec=t_sec,
        frame=frame if frame is not None else (velocity_state.time_sec if velocity_state else None),
        total_mass_kg=mass_dist.total_mass_kg,
        com_world=(com_world.x, com_world.y, com_world.z),
        com_linear_velocity=(com_vel.x, com_vel.y, com_vel.z),
        inertia_tensor_body_com=accum_inertia,
        angular_momentum_body_com=(total_h.x, total_h.y, total_h.z),
        spin_angular_momentum_total=(total_spin_h.x, total_spin_h.y, total_spin_h.z),
        orbital_angular_momentum_total=(total_orbital_h.x, total_orbital_h.y, total_orbital_h.z),
        segments=seg_states,
    )


def compute_whole_body_inertia_from_snapshots(
    pose_snapshot: BodyPoseSnapshot,
    velocity_state: Optional[BodyVelocityState] = None,
    inertia_model: Optional[BodyInertiaModel] = None,
) -> WholeBodyInertiaState:
    """Compute whole-body inertia tensor and angular momentum directly from snapshot data.

    Allows evaluation in headless, non-Blender-Armature pipelines or post-processing stages.
    """
    model = inertia_model if inertia_model is not None else DEFAULT_15_SEGMENT_INERTIA_MODEL
    mass_dist = model.mass_distribution

    com_world = Vector(pose_snapshot.com_world)
    if velocity_state is not None:
        com_vel = Vector(velocity_state.com_linear_velocity)
        t_sec = velocity_state.time_sec
    else:
        com_vel = Vector((0.0, 0.0, 0.0))
        t_sec = pose_snapshot.time_sec

    seg_states: Dict[str, SegmentInertiaState] = {}
    accum_inertia = InertiaTensor.zero()
    total_spin_h = Vector((0.0, 0.0, 0.0))
    total_orbital_h = Vector((0.0, 0.0, 0.0))

    for seg_spec in mass_dist.segments:
        seg_id = seg_spec.segment_id
        if seg_id not in pose_snapshot.segment_positions:
            continue

        mass_kg = seg_spec.mass_ratio * mass_dist.total_mass_kg
        geom = model.get_geometry(seg_id)
        local_tensor = geom.compute_local_tensor(mass_kg=mass_kg)

        # Read orientation quaternion from snapshot
        sq = pose_snapshot.segment_orientations.get(seg_id, (1.0, 0.0, 0.0, 0.0))
        q = Quaternion((sq[0], sq[1], sq[2], sq[3])).normalized()
        r_world = q.to_matrix()

        world_tensor_com_i = local_tensor.rotate(r_world)

        seg_pos = Vector(pose_snapshot.segment_positions[seg_id])
        r_i = seg_pos - com_world
        world_tensor_body_com = world_tensor_com_i.parallel_axis(mass_kg=mass_kg, offset=r_i)

        accum_inertia = accum_inertia + world_tensor_body_com

        spin_h = Vector((0.0, 0.0, 0.0))
        orbital_h = Vector((0.0, 0.0, 0.0))

        if velocity_state is not None:
            if seg_id in velocity_state.segment_angular_velocities:
                omega_w = Vector(velocity_state.segment_angular_velocities[seg_id])
                spin_h = world_tensor_com_i.multiply(omega_w)

            if seg_id in velocity_state.segment_linear_velocities:
                v_w = Vector(velocity_state.segment_linear_velocities[seg_id])
                v_rel = v_w - com_vel
                orbital_h = r_i.cross(mass_kg * v_rel)

        seg_total_h = spin_h + orbital_h
        total_spin_h += spin_h
        total_orbital_h += orbital_h

        seg_states[seg_id] = SegmentInertiaState(
            segment_id=seg_id,
            bone_name=seg_spec.bone_name,
            mass_kg=mass_kg,
            world_com=(seg_pos.x, seg_pos.y, seg_pos.z),
            displacement_from_body_com=(r_i.x, r_i.y, r_i.z),
            local_inertia=local_tensor,
            world_inertia_com=world_tensor_com_i,
            world_inertia_body_com=world_tensor_body_com,
            spin_angular_momentum=(spin_h.x, spin_h.y, spin_h.z),
            orbital_angular_momentum=(orbital_h.x, orbital_h.y, orbital_h.z),
            total_angular_momentum=(seg_total_h.x, seg_total_h.y, seg_total_h.z),
        )

    total_h = total_spin_h + total_orbital_h

    return WholeBodyInertiaState(
        time_sec=t_sec,
        frame=pose_snapshot.frame,
        total_mass_kg=mass_dist.total_mass_kg,
        com_world=(com_world.x, com_world.y, com_world.z),
        com_linear_velocity=(com_vel.x, com_vel.y, com_vel.z),
        inertia_tensor_body_com=accum_inertia,
        angular_momentum_body_com=(total_h.x, total_h.y, total_h.z),
        spin_angular_momentum_total=(total_spin_h.x, total_spin_h.y, total_spin_h.z),
        orbital_angular_momentum_total=(total_orbital_h.x, total_orbital_h.y, total_orbital_h.z),
        segments=seg_states,
    )


def enrich_motion_state_with_inertia(
    motion_state: Any,
    inertia_state: WholeBodyInertiaState,
) -> Any:
    """Seamlessly inject inertia tensor and angular momentum into MotionState.params."""
    if not hasattr(motion_state, "params") or motion_state.params is None:
        motion_state.params = {}

    motion_state.params["inertia_tensor_com"] = inertia_state.inertia_tensor_body_com.to_tuple()
    motion_state.params["inertia_principal_moments"] = inertia_state.principal_moments
    motion_state.params["angular_momentum_com"] = inertia_state.angular_momentum_body_com
    motion_state.params["angular_momentum_magnitude"] = inertia_state.angular_momentum_magnitude
    motion_state.params["spin_angular_momentum"] = inertia_state.spin_angular_momentum_total
    motion_state.params["orbital_angular_momentum"] = inertia_state.orbital_angular_momentum_total
    return motion_state
