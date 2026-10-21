"""Joint Degrees of Freedom (DOF) and Range of Motion (ROM) Constraint System (Task 6F-C).

Physics-constraint-assisted procedural animation: establishes a unified, configurable
Joint Model for anatomical joints of the 19-bone humanoid character rig.

Features:
- Configurable joint limits with biomechanical literature citations (Kapandji, Winter, AAOS).
- Supports independent 1-DOF, 2-DOF, and 3-DOF joints with coordinate convention documentation.
- Handles Euler wrap-around / +/-180 deg jump protection and multi-axis compound cone limits.
- Symmetrical lateral mirroring (L/R) with independent override support.
- Non-destructive `validate` interface reporting detailed violations.
- Precise `project`/`clamp` interface reporting all applied modifications.
- Evaluates both FK Euler poses and evaluated IK bone rotation transforms.
- Explicitly documents that `root` and `pelvis` are floating base frames rather than anatomical joints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Vector


# =============================================================================
# Mathematical Helpers
# =============================================================================

def normalize_angle_rad(angle: float) -> float:
    """Normalize an angle in radians to the principal interval (-pi, +pi].

    Prevents Euler wrap-around / +/-180 deg jump artifacts during boundary comparison.
    """
    two_pi = 2.0 * math.pi
    a = (angle + math.pi) % two_pi
    if a < 0.0:
        a += two_pi
    return a - math.pi


def normalize_angle_deg(angle: float) -> float:
    """Normalize an angle in degrees to the principal interval (-180, +180]."""
    a = (angle + 180.0) % 360.0
    if a < 0.0:
        a += 360.0
    return a - 180.0


# =============================================================================
# Enums and Violation / Modification Reporting Structures
# =============================================================================

class ConstraintMode(Enum):
    """Mathematical constraint formulation applied to a joint."""
    BOX_EULER = "box_euler"           # Independent clamping along each allowed axis
    ELLIPTICAL_CONE = "elliptical_cone" # Compound 2D swing cone (X, Z) + axial twist (Y)
    HINGE_1D = "hinge_1d"             # Strict 1-DOF hinge; disallowed minor axes clamped to slack


@dataclass(frozen=True)
class AxisViolation:
    """Details of a single-axis ROM violation."""
    axis: str               # "X", "Y", or "Z"
    requested_deg: float    # Requested angle in degrees (normalized)
    limit_min_deg: float    # Lower bound in degrees
    limit_max_deg: float    # Upper bound in degrees
    excess_deg: float       # Positive magnitude of the violation in degrees


@dataclass(frozen=True)
class JointViolation:
    """Comprehensive violation information for a single joint."""
    joint_id: str
    bone_name: str
    axis_violations: Tuple[AxisViolation, ...] = ()
    compound_violation_deg: Optional[float] = None
    compound_limit_deg: Optional[float] = None
    compound_requested_deg: Optional[float] = None
    disallowed_dof_violations: Tuple[str, ...] = ()

    @property
    def has_violations(self) -> bool:
        return bool(self.axis_violations or self.compound_violation_deg or self.disallowed_dof_violations)

    @property
    def max_excess_deg(self) -> float:
        excesses = [v.excess_deg for v in self.axis_violations]
        if self.compound_violation_deg is not None:
            excesses.append(self.compound_violation_deg)
        return max(excesses) if excesses else 0.0


@dataclass(frozen=True)
class JointValidationResult:
    """Result of checking a whole-body or multi-joint pose against ROM limits."""
    is_valid: bool
    violations: Dict[str, JointViolation] = field(default_factory=dict)
    max_excess_deg: float = 0.0

    def summary(self) -> str:
        if self.is_valid:
            return "All joints comply with ROM specifications (0 violations)."
        lines = [f"ROM Violations detected on {len(self.violations)} joint(s) (max excess: {self.max_excess_deg:.2f} deg):"]
        for b_name, viol in self.violations.items():
            details = []
            for av in viol.axis_violations:
                details.append(f"Axis {av.axis}: req={av.requested_deg:+.1f} deg out of [{av.limit_min_deg:+.1f}, {av.limit_max_deg:+.1f}] by {av.excess_deg:.1f} deg")
            if viol.compound_violation_deg is not None:
                details.append(f"Compound swing: req={viol.compound_requested_deg:.1f} deg > limit {viol.compound_limit_deg:.1f} deg by {viol.compound_violation_deg:.1f} deg")
            if viol.disallowed_dof_violations:
                details.append(f"Disallowed DOFs: {', '.join(viol.disallowed_dof_violations)}")
            lines.append(f"  - {b_name} ({viol.joint_id}): {'; '.join(details)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class AxisModification:
    """Details of modification applied to a single axis during projection/clamping."""
    axis: str
    original_deg: float
    clamped_deg: float
    delta_deg: float


@dataclass(frozen=True)
class JointModification:
    """Details of modification applied to a joint."""
    joint_id: str
    bone_name: str
    modifications: Tuple[AxisModification, ...] = ()
    compound_adjusted: bool = False

    @property
    def max_delta_deg(self) -> float:
        return max((abs(m.delta_deg) for m in self.modifications), default=0.0)


@dataclass(frozen=True)
class JointClampResult:
    """Result of projecting/clamping an out-of-range pose back into the ROM boundary."""
    clamped_rotations_deg: Dict[str, Tuple[float, float, float]]
    clamped_rotations_rad: Dict[str, Tuple[float, float, float]]
    modifications: Dict[str, JointModification] = field(default_factory=dict)
    max_adjustment_deg: float = 0.0
    is_modified: bool = False

    def summary(self) -> str:
        if not self.is_modified:
            return "No joints required adjustment (pose is fully within ROM)."
        lines = [f"Adjusted {len(self.modifications)} joint(s) to ROM boundaries (max adjustment: {self.max_adjustment_deg:.2f} deg):"]
        for b_name, mod in self.modifications.items():
            axis_strs = [f"{m.axis}: {m.original_deg:+.1f}->{m.clamped_deg:+.1f} (delta={m.delta_deg:+.1f} deg)" for m in mod.modifications]
            lines.append(f"  - {b_name} ({mod.joint_id}): {', '.join(axis_strs)}")
        return "\n".join(lines)


# =============================================================================
# Joint Specification Data Class
# =============================================================================

@dataclass(frozen=True)
class JointLimitSpec:
    """Specification of a single anatomical joint's local degrees of freedom and ROM limits.

    Coordinates & Units:
    - Angles stored internally in radians; constructor accepts degrees.
    - Bone local coordinate frame follows Blender PoseBone orientation conventions:
        Central axial chain (spine, neck, head): +Y vertical along spine, +X right, +Z backward.
        Upper/lower limbs (arm, leg): +Y along bone axis pointing towards distal extremity,
        +X rightward, +Z forward.
    """
    joint_id: str
    bone_name: str
    allowed_dofs: Tuple[str, ...]                   # Subset of ("X", "Y", "Z")
    constraint_mode: ConstraintMode
    min_deg: Tuple[float, float, float]             # (min_X, min_Y, min_Z) in degrees
    max_deg: Tuple[float, float, float]             # (max_X, max_Y, max_Z) in degrees
    compound_cone_max_deg: Optional[float] = None   # Elliptical/spherical swing cone limit in deg
    preferred_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    local_axis_description: str = ""
    source: str = "Kapandji / Winter / Biomechanical Standard"
    engineering_notes: str = ""

    # Pre-calculated radian representations for zero-overhead evaluation
    min_rad: Tuple[float, float, float] = field(init=False)
    max_rad: Tuple[float, float, float] = field(init=False)
    compound_cone_max_rad: Optional[float] = field(init=False)
    preferred_rad: Tuple[float, float, float] = field(init=False)

    def __post_init__(self) -> None:
        # Validate input limits
        for i, axis in enumerate(("X", "Y", "Z")):
            if self.min_deg[i] > self.max_deg[i]:
                raise ValueError(
                    f"Joint '{self.joint_id}' ({self.bone_name}) axis {axis}: "
                    f"min_deg ({self.min_deg[i]}) > max_deg ({self.max_deg[i]})"
                )

        object.__setattr__(
            self, "min_rad", tuple(math.radians(val) for val in self.min_deg)
        )
        object.__setattr__(
            self, "max_rad", tuple(math.radians(val) for val in self.max_deg)
        )
        object.__setattr__(
            self, "compound_cone_max_rad",
            math.radians(self.compound_cone_max_deg) if self.compound_cone_max_deg is not None else None
        )
        object.__setattr__(
            self, "preferred_rad", tuple(math.radians(val) for val in self.preferred_deg)
        )

    def validate_euler_rad(
        self,
        rx_rad: float,
        ry_rad: float,
        rz_rad: float,
        tolerance_deg: float = 0.01,
    ) -> Optional[JointViolation]:
        """Validate a 3D Euler rotation in radians against this joint's ROM limits."""
        # 1. Normalize angles to (-pi, pi] to protect against Euler wrap-around
        nx_rad = normalize_angle_rad(rx_rad)
        ny_rad = normalize_angle_rad(ry_rad)
        nz_rad = normalize_angle_rad(rz_rad)

        nx_deg = math.degrees(nx_rad)
        ny_deg = math.degrees(ny_rad)
        nz_deg = math.degrees(nz_rad)

        axis_violations: List[AxisViolation] = []
        disallowed_dof_violations: List[str] = []

        coords_deg = (nx_deg, ny_deg, nz_deg)
        axes = ("X", "Y", "Z")

        # 2. Check individual axis boundaries and allowed DOFs
        for i, axis in enumerate(axes):
            val_deg = coords_deg[i]
            low_deg = self.min_deg[i]
            high_deg = self.max_deg[i]

            # Disallowed DOF check: if axis is not allowed, angle outside tiny slack is flagged
            if axis not in self.allowed_dofs:
                slack = 2.0  # 2 degree slack for numerical/IK noise
                if abs(val_deg) > slack:
                    disallowed_dof_violations.append(f"{axis}({val_deg:+.1f}deg)")

            if val_deg < low_deg - tolerance_deg:
                excess = low_deg - val_deg
                axis_violations.append(AxisViolation(axis, val_deg, low_deg, high_deg, excess))
            elif val_deg > high_deg + tolerance_deg:
                excess = val_deg - high_deg
                axis_violations.append(AxisViolation(axis, val_deg, low_deg, high_deg, excess))

        # 3. Check compound swing cone limit (if applicable, e.g. for shoulder/hip)
        compound_excess_deg: Optional[float] = None
        compound_req_deg: Optional[float] = None
        if self.compound_cone_max_deg is not None and self.constraint_mode == ConstraintMode.ELLIPTICAL_CONE:
            # Elliptical normalized swing magnitude:
            # rx contributes along sagittal axis, rz contributes along coronal axis
            max_swing_x = max(abs(self.min_deg[0]), abs(self.max_deg[0]))
            max_swing_z = max(abs(self.min_deg[2]), abs(self.max_deg[2]))
            if max_swing_x > 1e-4 and max_swing_z > 1e-4:
                # Radial elliptical ratio:
                ratio_sq = (nx_deg / max_swing_x) ** 2 + (nz_deg / max_swing_z) ** 2
                raw_swing = math.sqrt(nx_deg ** 2 + nz_deg ** 2)
                compound_req_deg = raw_swing
                if ratio_sq > 1.0 + 1e-4:
                    # Excess in effective degrees beyond the ellipse boundary
                    effective_boundary = raw_swing / math.sqrt(ratio_sq)
                    compound_excess_deg = raw_swing - effective_boundary

        if axis_violations or compound_excess_deg is not None or disallowed_dof_violations:
            return JointViolation(
                joint_id=self.joint_id,
                bone_name=self.bone_name,
                axis_violations=tuple(axis_violations),
                compound_violation_deg=compound_excess_deg,
                compound_limit_deg=self.compound_cone_max_deg,
                compound_requested_deg=compound_req_deg,
                disallowed_dof_violations=tuple(disallowed_dof_violations),
            )
        return None

    def clamp_euler_rad(
        self,
        rx_rad: float,
        ry_rad: float,
        rz_rad: float,
    ) -> Tuple[Tuple[float, float, float], Optional[JointModification]]:
        """Project an out-of-range 3D Euler rotation in radians onto this joint's allowed ROM boundary."""
        # 1. Normalize angles to (-pi, pi]
        nx_rad = normalize_angle_rad(rx_rad)
        ny_rad = normalize_angle_rad(ry_rad)
        nz_rad = normalize_angle_rad(rz_rad)

        orig_x_deg = math.degrees(nx_rad)
        orig_y_deg = math.degrees(ny_rad)
        orig_z_deg = math.degrees(nz_rad)

        clamped_x_deg = orig_x_deg
        clamped_y_deg = orig_y_deg
        clamped_z_deg = orig_z_deg

        axes = ("X", "Y", "Z")
        vals_deg = [orig_x_deg, orig_y_deg, orig_z_deg]

        # 2. Component-wise clamp to individual axis bounds (and 0 for disallowed DOFs if HINGE_1D)
        for i, axis in enumerate(axes):
            if axis not in self.allowed_dofs and self.constraint_mode == ConstraintMode.HINGE_1D:
                vals_deg[i] = 0.0
            else:
                vals_deg[i] = max(self.min_deg[i], min(self.max_deg[i], vals_deg[i]))

        clamped_x_deg, clamped_y_deg, clamped_z_deg = vals_deg

        # 3. Apply compound swing cone projection if applicable
        compound_adjusted = False
        if self.compound_cone_max_deg is not None and self.constraint_mode == ConstraintMode.ELLIPTICAL_CONE:
            max_swing_x = max(abs(self.min_deg[0]), abs(self.max_deg[0]))
            max_swing_z = max(abs(self.min_deg[2]), abs(self.max_deg[2]))
            if max_swing_x > 1e-4 and max_swing_z > 1e-4:
                ratio_sq = (clamped_x_deg / max_swing_x) ** 2 + (clamped_z_deg / max_swing_z) ** 2
                if ratio_sq > 1.0:
                    scale = 1.0 / math.sqrt(ratio_sq)
                    clamped_x_deg *= scale
                    clamped_z_deg *= scale
                    compound_adjusted = True

        # 4. Compare clamped against original and record any modifications
        modifications: List[AxisModification] = []
        origs = (orig_x_deg, orig_y_deg, orig_z_deg)
        clampeds = (clamped_x_deg, clamped_y_deg, clamped_z_deg)
        for i, axis in enumerate(axes):
            delta = clampeds[i] - origs[i]
            if abs(delta) > 1e-4:
                modifications.append(AxisModification(axis, origs[i], clampeds[i], delta))

        final_rad = (
            math.radians(clamped_x_deg),
            math.radians(clamped_y_deg),
            math.radians(clamped_z_deg),
        )

        joint_mod = None
        if modifications or compound_adjusted:
            joint_mod = JointModification(
                joint_id=self.joint_id,
                bone_name=self.bone_name,
                modifications=tuple(modifications),
                compound_adjusted=compound_adjusted,
            )

        return final_rad, joint_mod


# =============================================================================
# Whole-Body Joint Model Data Class
# =============================================================================

@dataclass
class JointModel:
    """Configurable collection of joint DOF and ROM specifications for a humanoid character.

    Supports validation, clamping, lateral mirroring, and evaluation on Blender Armatures.
    """
    model_name: str
    joints: Dict[str, JointLimitSpec] = field(default_factory=dict)
    notes: str = ""

    def get_spec(self, bone_name: str) -> Optional[JointLimitSpec]:
        """Look up the JointLimitSpec for a bone name."""
        return self.joints.get(bone_name)

    def validate_rotations(
        self,
        rotations_dict: Mapping[str, Tuple[float, float, float]],
        in_degrees: bool = True,
        tolerance_deg: float = 0.01,
    ) -> JointValidationResult:
        """Validate a dictionary of bone rotations against this JointModel.

        Args:
            rotations_dict: Mapping of bone_name to (rx, ry, rz) rotation Euler.
            in_degrees: True if input angles are in degrees; False if in radians.
            tolerance_deg: Angular slack in degrees.

        Returns:
            JointValidationResult detailing validity and violations.
        """
        violations: Dict[str, JointViolation] = {}
        max_excess = 0.0

        for bone_name, rot in rotations_dict.items():
            spec = self.joints.get(bone_name)
            if spec is None:
                continue  # Skip unconstrained bones (e.g. root, pelvis)

            rx = math.radians(rot[0]) if in_degrees else rot[0]
            ry = math.radians(rot[1]) if in_degrees else rot[1]
            rz = math.radians(rot[2]) if in_degrees else rot[2]

            viol = spec.validate_euler_rad(rx, ry, rz, tolerance_deg=tolerance_deg)
            if viol is not None:
                violations[bone_name] = viol
                max_excess = max(max_excess, viol.max_excess_deg)

        return JointValidationResult(
            is_valid=(len(violations) == 0),
            violations=violations,
            max_excess_deg=max_excess,
        )

    def clamp_rotations(
        self,
        rotations_dict: Mapping[str, Tuple[float, float, float]],
        in_degrees: bool = True,
    ) -> JointClampResult:
        """Project/clamp a dictionary of bone rotations onto this JointModel's ROM boundaries.

        Args:
            rotations_dict: Mapping of bone_name to (rx, ry, rz) rotation Euler.
            in_degrees: True if input angles are in degrees; False if in radians.

        Returns:
            JointClampResult containing clamped angles and detailed modification report.
        """
        clamped_deg: Dict[str, Tuple[float, float, float]] = {}
        clamped_rad: Dict[str, Tuple[float, float, float]] = {}
        modifications: Dict[str, JointModification] = {}
        max_adj = 0.0

        for bone_name, rot in rotations_dict.items():
            spec = self.joints.get(bone_name)
            if spec is None:
                # Unconstrained bone passed through unchanged
                rx_d = rot[0] if in_degrees else math.degrees(rot[0])
                ry_d = rot[1] if in_degrees else math.degrees(rot[1])
                rz_d = rot[2] if in_degrees else math.degrees(rot[2])
                clamped_deg[bone_name] = (rx_d, ry_d, rz_d)
                clamped_rad[bone_name] = (math.radians(rx_d), math.radians(ry_d), math.radians(rz_d))
                continue

            rx = math.radians(rot[0]) if in_degrees else rot[0]
            ry = math.radians(rot[1]) if in_degrees else rot[1]
            rz = math.radians(rot[2]) if in_degrees else rot[2]

            c_rad, mod = spec.clamp_euler_rad(rx, ry, rz)
            c_deg = (math.degrees(c_rad[0]), math.degrees(c_rad[1]), math.degrees(c_rad[2]))

            clamped_deg[bone_name] = c_deg
            clamped_rad[bone_name] = c_rad

            if mod is not None:
                modifications[bone_name] = mod
                max_adj = max(max_adj, mod.max_delta_deg)

        return JointClampResult(
            clamped_rotations_deg=clamped_deg,
            clamped_rotations_rad=clamped_rad,
            modifications=modifications,
            max_adjustment_deg=max_adj,
            is_modified=(len(modifications) > 0),
        )

    def validate_armature_pose(
        self,
        armature_obj: Optional[bpy.types.Object] = None,
        use_evaluated_ik: bool = False,
        tolerance_deg: float = 0.01,
    ) -> JointValidationResult:
        """Validate the current pose of a CharacterArmature in Blender.

        Args:
            armature_obj: CharacterArmature object.
            use_evaluated_ik: If True, extracts evaluated relative bone rotations from
                              `pose_bone.matrix` relative to rest pose (evaluates active IK chains).
                              If False, reads `pose_bone.rotation_euler` directly (FK mode).
            tolerance_deg: Angular tolerance in degrees.
        """
        if armature_obj is None:
            armature_obj = bpy.data.objects.get("CharacterArmature")
        if armature_obj is None or armature_obj.type != "ARMATURE":
            raise RuntimeError("Valid CharacterArmature object not found")

        if use_evaluated_ik:
            dg = bpy.context.evaluated_depsgraph_get()
            dg.update()
            eval_arm = armature_obj.evaluated_get(dg)
        else:
            eval_arm = armature_obj

        rot_dict_rad: Dict[str, Tuple[float, float, float]] = {}
        for bone_name in self.joints:
            pb = eval_arm.pose.bones.get(bone_name)
            if pb is None:
                continue

            if use_evaluated_ik:
                rot_rad = extract_evaluated_bone_rotation_rad(pb)
            else:
                rot_rad = (pb.rotation_euler.x, pb.rotation_euler.y, pb.rotation_euler.z)

            rot_dict_rad[bone_name] = rot_rad

        return self.validate_rotations(rot_dict_rad, in_degrees=False, tolerance_deg=tolerance_deg)

    def clamp_armature_pose(
        self,
        armature_obj: Optional[bpy.types.Object] = None,
        apply: bool = True,
        update_scene: bool = True,
    ) -> JointClampResult:
        """Clamp the FK pose bones of a CharacterArmature in Blender.

        Non-silent: explicitly returns a JointClampResult detailing all applied modifications.
        """
        if armature_obj is None:
            armature_obj = bpy.data.objects.get("CharacterArmature")
        if armature_obj is None or armature_obj.type != "ARMATURE":
            raise RuntimeError("Valid CharacterArmature object not found")

        rot_dict_rad: Dict[str, Tuple[float, float, float]] = {}
        for bone_name in self.joints:
            pb = armature_obj.pose.bones.get(bone_name)
            if pb is not None:
                rot_dict_rad[bone_name] = (pb.rotation_euler.x, pb.rotation_euler.y, pb.rotation_euler.z)

        clamp_res = self.clamp_rotations(rot_dict_rad, in_degrees=False)

        if apply and clamp_res.is_modified:
            for bone_name, mod in clamp_res.modifications.items():
                pb = armature_obj.pose.bones.get(bone_name)
                if pb is not None:
                    c_rad = clamp_res.clamped_rotations_rad[bone_name]
                    pb.rotation_mode = "XYZ"
                    pb.rotation_euler = Euler(c_rad, "XYZ")

            if update_scene:
                bpy.context.view_layer.update()

        return clamp_res

    def with_overrides(
        self,
        overrides: Mapping[str, JointLimitSpec],
        new_model_name: Optional[str] = None,
    ) -> JointModel:
        """Create a new JointModel with specific joint specifications overridden."""
        new_joints = dict(self.joints)
        new_joints.update(overrides)
        return JointModel(
            model_name=new_model_name or f"{self.model_name}_Overridden",
            joints=new_joints,
            notes=f"Derived from {self.model_name} with overrides on {list(overrides.keys())}",
        )


# =============================================================================
# Evaluated Relative Bone Rotation Extraction
# =============================================================================

def extract_evaluated_bone_rotation_rad(pose_bone: bpy.types.PoseBone) -> Tuple[float, float, float]:
    """Extract a PoseBone's evaluated 3D rotation in radians relative to its rest pose in parent space.

    Works identically under forward kinematics (FK) and active two-bone inverse kinematics (IK).

    Mathematics:
        rest_rel = parent.bone.matrix_local.inverted() @ bone.matrix_local
        pose_rel = parent.matrix.inverted() @ pose_bone.matrix
        evaluated_rot = rest_rel.inverted() @ pose_rel
    """
    if pose_bone.parent is None:
        # Root-level bone relative to armature origin
        rel_mat = pose_bone.bone.matrix_local.inverted() @ pose_bone.matrix
    else:
        rest_rel = pose_bone.parent.bone.matrix_local.inverted() @ pose_bone.bone.matrix_local
        pose_rel = pose_bone.parent.matrix.inverted() @ pose_bone.matrix
        rel_mat = rest_rel.inverted() @ pose_rel

    euler = rel_mat.to_euler("XYZ")
    return (euler.x, euler.y, euler.z)


# =============================================================================
# Default Biomechanical Humanoid Joint Model (Dempster / Kapandji / Winter)
# =============================================================================

# Scientific Citations & References:
# 1. Kapandji, I.A. (2008). "The Physiology of the Joints" (Volumes 1, 2, 3), Churchill Livingstone Elsevier.
#    - Vol 1: Upper Limb (Shoulder, Elbow, Wrist)
#    - Vol 2: Lower Limb (Hip, Knee, Ankle)
#    - Vol 3: The Spinal Column, Pelvic Girdle and Head
# 2. Winter, D.A. (2009). "Biomechanics and Motor Control of Human Movement", 4th ed., Wiley.
# 3. Greene, W.B. & Heckman, J.D. (1994). "The Clinical Measurement of Joint Motion", AAOS (American Academy of Orthopaedic Surgeons).
# 4. White, A.A. & Panjabi, M.M. (1990). "Clinical Biomechanics of the Spine", 2nd ed., Lippincott.
#
# Engineering Assumptions & Approximations:
# - Pelvis & Root are base floating frames (not anatomical human joints), therefore excluded from ROM joint checks.
# - Multi-vertebra spine is modeled as a single effective joint (`spine`) with aggregate lumbar+thoracic flexibility.
# - Shoulder complex is divided into clavicular scapulothoracic elevation (`shoulder.L/R`) and glenohumeral 3-DOF (`upper_arm.L/R`).
# - Elbow and knee are modeled as primary 1-DOF hinges with tiny physiological slack on minor axes.
# - Lateral mirror symmetry: left/right abduction sign differs due to common rightward (+X) bone roll vectors in rig.

def _build_default_humanoid_rom_joints() -> Dict[str, JointLimitSpec]:
    """Construct the standard 17-joint humanoid ROM specification dictionary."""
    specs: List[JointLimitSpec] = [
        # ---------------------------------------------------------------------
        # 1. Axial Hierarchy (Spine, Neck, Head)
        # ---------------------------------------------------------------------
        JointLimitSpec(
            joint_id="spine",
            bone_name="spine",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # X: Flexion forward (+60 deg) / Extension back (-30 deg)
            # Y: Axial torsion (+/-40 deg)
            # Z: Lateral bending (+/-35 deg)
            min_deg=(-30.0, -40.0, -35.0),
            max_deg=(60.0, 40.0, 35.0),
            compound_cone_max_deg=65.0,
            local_axis_description="X=Pitch(Flex/Ext), Y=Twist(Torsion along spine), Z=Roll(Lateral bend)",
            source="White & Panjabi (1990) Table 2-1; Kapandji Vol 3 p. 44",
            engineering_notes="Lumbosacral + thoracic aggregate single-joint approximation.",
        ),
        JointLimitSpec(
            joint_id="neck",
            bone_name="neck",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # X: Neck flexion forward (+50 deg) / Extension back (-50 deg)
            # Y: Neck axial rotation (+/-60 deg)
            # Z: Neck lateral tilt (+/-40 deg)
            min_deg=(-50.0, -60.0, -40.0),
            max_deg=(50.0, 60.0, 40.0),
            compound_cone_max_deg=55.0,
            local_axis_description="X=Pitch(Flex/Ext), Y=Twist(Axial rotation), Z=Roll(Lateral bend)",
            source="Kapandji Vol 3 p. 192; AAOS (1994)",
            engineering_notes="Cervical spine aggregate motion.",
        ),
        JointLimitSpec(
            joint_id="head",
            bone_name="head",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            min_deg=(-25.0, -35.0, -20.0),
            max_deg=(25.0, 35.0, 20.0),
            compound_cone_max_deg=35.0,
            local_axis_description="X=Nod(Pitch), Y=Turn(Yaw), Z=Tilt(Roll)",
            source="Kapandji Vol 3 p. 194",
            engineering_notes="Atlanto-occipital articulation tilt relative to neck.",
        ),

        # ---------------------------------------------------------------------
        # 2. Left Upper Limb (Shoulder, Arm, Forearm, Hand)
        # ---------------------------------------------------------------------
        JointLimitSpec(
            joint_id="shoulder_L",
            bone_name="shoulder.L",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # shoulder.L local axes: Y=(-1,0,0) left, X=(0,1,0) forward, Z=(0,0,1) up
            # X: Protraction forward (+20 deg) / Retraction back (-15 deg)
            # Y: Clavicle axial roll (+/-10 deg)
            # Z: Elevation upward (+30 deg) / Depression downward (-10 deg)
            min_deg=(-15.0, -10.0, -10.0),
            max_deg=(20.0, 10.0, 30.0),
            local_axis_description="X=Protraction/Retraction(fwd/back), Y=Axial roll, Z=Elevation/Depression(up/down)",
            source="Inman et al. (1944); Kapandji Vol 1 p. 54",
            engineering_notes="Scapulothoracic / clavicular elevation-protraction.",
        ),
        JointLimitSpec(
            joint_id="upper_arm_L",
            bone_name="upper_arm.L",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.ELLIPTICAL_CONE,
            # upper_arm.L: Y=(0,0,-1) down, X=(1,0,0) right(inward), Z=(0,1,0) forward
            # X: Forward pitch/flexion (+160 deg) / Extension backward (-50 deg)
            # Y: Internal/external humeral twist (+/-80 deg)
            # Z: Abduction outward away from body (+150 deg) / Adduction across chest (-30 deg)
            min_deg=(-50.0, -80.0, -30.0),
            max_deg=(160.0, 80.0, 150.0),
            compound_cone_max_deg=165.0,
            local_axis_description="X=Flexion/Extension(fwd/back), Y=Humeral axial twist, Z=Abduction/Adduction(out/in)",
            source="Kapandji Vol 1 p. 14; AAOS (1994)",
            engineering_notes="Glenohumeral 3-DOF ball-and-socket with elliptical swing cone.",
        ),
        JointLimitSpec(
            joint_id="forearm_L",
            bone_name="forearm.L",
            allowed_dofs=("X", "Y"),
            constraint_mode=ConstraintMode.HINGE_1D,
            # forearm.L: Y=(0,0,-1) down, X=(1,0,0) right, Z=(0,1,0) forward
            # X: Elbow flexion (+145 deg) / Hyperextension back (-2 deg lock)
            # Y: Forearm pronation/supination (+/-85 deg)
            # Z: Varus/valgus carry angle slack (+/-3 deg)
            min_deg=(-2.0, -85.0, -3.0),
            max_deg=(145.0, 85.0, 3.0),
            local_axis_description="X=Elbow flexion(+145)/lock(-2), Y=Pronation/supination, Z=Carry slack",
            source="Morrey et al. (1985); Kapandji Vol 1 p. 78",
            engineering_notes="Elbow hinge with radioulnar axial pronation/supination.",
        ),
        JointLimitSpec(
            joint_id="hand_L",
            bone_name="hand.L",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # X: Palmar flexion (+70 deg) / Dorsiflexion back (-60 deg)
            # Y: Wrist axial twist (+/-20 deg, residual)
            # Z: Radial/ulnar deviation (+/-30 deg)
            min_deg=(-60.0, -20.0, -30.0),
            max_deg=(70.0, 20.0, 30.0),
            local_axis_description="X=Palmar flex/Dorsiflex, Y=Axial twist, Z=Radial/ulnar deviation",
            source="Kapandji Vol 1 p. 144; Ryu et al. (1991)",
            engineering_notes="Radiocarpal wrist joint.",
        ),

        # ---------------------------------------------------------------------
        # 3. Right Upper Limb (Shoulder, Arm, Forearm, Hand) - Mirrored
        # ---------------------------------------------------------------------
        JointLimitSpec(
            joint_id="shoulder_R",
            bone_name="shoulder.R",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # shoulder.R: Y=(1,0,0) right, X=(0,-1,0) back, Z=(0,0,1) up
            # X: Retraction (-20 deg) / Protraction (+15 deg)
            # Y: Clavicle axial roll (+/-10 deg)
            # Z: Elevation (+30 deg) / Depression (-10 deg)
            min_deg=(-20.0, -10.0, -10.0),
            max_deg=(15.0, 10.0, 30.0),
            local_axis_description="X=Protraction/Retraction, Y=Axial roll, Z=Elevation/Depression",
            source="Inman et al. (1944); Kapandji Vol 1 p. 54",
            engineering_notes="Mirrored right scapulothoracic elevation.",
        ),
        JointLimitSpec(
            joint_id="upper_arm_R",
            bone_name="upper_arm.R",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.ELLIPTICAL_CONE,
            # upper_arm.R: Y=(0,0,-1) down, X=(1,0,0) right(outward!), Z=(0,1,0) forward
            # X: Forward pitch/flexion (+160 deg) / Extension backward (-50 deg)
            # Y: Internal/external humeral twist (+/-80 deg)
            # Z: Abduction outward (-150 deg) / Adduction across chest (+30 deg) (inverted Z sign vs Left!)
            min_deg=(-50.0, -80.0, -150.0),
            max_deg=(160.0, 80.0, 30.0),
            compound_cone_max_deg=165.0,
            local_axis_description="X=Flexion/Extension(fwd/back), Y=Humeral axial twist, Z=Abduction(-150)/Adduction(+30)",
            source="Kapandji Vol 1 p. 14; AAOS (1994)",
            engineering_notes="Mirrored right glenohumeral ball-and-socket (Z axis sign flipped for abduction).",
        ),
        JointLimitSpec(
            joint_id="forearm_R",
            bone_name="forearm.R",
            allowed_dofs=("X", "Y"),
            constraint_mode=ConstraintMode.HINGE_1D,
            min_deg=(-2.0, -85.0, -3.0),
            max_deg=(145.0, 85.0, 3.0),
            local_axis_description="X=Elbow flexion(+145)/lock(-2), Y=Pronation/supination, Z=Carry slack",
            source="Morrey et al. (1985); Kapandji Vol 1 p. 78",
            engineering_notes="Mirrored right elbow hinge.",
        ),
        JointLimitSpec(
            joint_id="hand_R",
            bone_name="hand.R",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            min_deg=(-60.0, -20.0, -30.0),
            max_deg=(70.0, 20.0, 30.0),
            local_axis_description="X=Palmar flex/Dorsiflex, Y=Axial twist, Z=Radial/ulnar deviation",
            source="Kapandji Vol 1 p. 144; Ryu et al. (1991)",
            engineering_notes="Mirrored right wrist joint.",
        ),

        # ---------------------------------------------------------------------
        # 4. Left Lower Limb (Thigh, Shin, Foot)
        # ---------------------------------------------------------------------
        JointLimitSpec(
            joint_id="thigh_L",
            bone_name="thigh.L",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.ELLIPTICAL_CONE,
            # thigh.L: Y=(0,0,-1) down, X=(1,0,0) right(inward), Z=(0,1,0) forward
            # X: Hip flexion forward (+120 deg) / Extension backward (-25 deg)
            # Y: Internal/external femoral rotation (+/-40 deg)
            # Z: Abduction outward (+50 deg) / Adduction inward across midline (-25 deg)
            min_deg=(-25.0, -40.0, -25.0),
            max_deg=(120.0, 40.0, 50.0),
            compound_cone_max_deg=125.0,
            local_axis_description="X=Hip Flex/Ext(fwd/back), Y=Femoral twist, Z=Abduction(+50)/Adduction(-25)",
            source="Kapandji Vol 2 p. 14; Winter (2009); Roach et al. (1991)",
            engineering_notes="Acetabulofemoral hip ball-and-socket joint.",
        ),
        JointLimitSpec(
            joint_id="shin_L",
            bone_name="shin.L",
            allowed_dofs=("X",),
            constraint_mode=ConstraintMode.HINGE_1D,
            # shin.L: Y=(0,0,-1) down, X=(1,0,0) right, Z=(0,1,0) forward
            # X: Knee flexion backward (-145 deg) / Hyperextension forward (+2 deg lock!)
            # Y: Tibial axial rotation slack (+/-8 deg)
            # Z: Varus/valgus carry slack (+/-3 deg)
            min_deg=(-145.0, -8.0, -3.0),
            max_deg=(2.0, 8.0, 3.0),
            local_axis_description="X=Knee flexion(-145)/hyperextension lock(+2), Y=Tibial twist slack, Z=Varus slack",
            source="Kapandji Vol 2 p. 76; Winter (2009)",
            engineering_notes="Tibiofemoral knee hinge (strictly locked against forward bending).",
        ),
        JointLimitSpec(
            joint_id="foot_L",
            bone_name="foot.L",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            # foot.L: Y=(0, 0.97, -0.23), Z=(0, 0.23, 0.97), X=(1, 0, 0)
            # X: Plantarflexion (+45 deg) / Dorsiflexion (-25 deg)
            # Y: Inversion/eversion (+/-25 deg)
            # Z: Abduction/adduction (+/-15 deg)
            min_deg=(-25.0, -25.0, -15.0),
            max_deg=(45.0, 20.0, 15.0),
            local_axis_description="X=Plantarflex/Dorsiflex, Y=Inversion/eversion, Z=Abduction/adduction",
            source="Kapandji Vol 2 p. 158; Siegler et al. (1988)",
            engineering_notes="Talocrural & subtalar ankle joint complex.",
        ),

        # ---------------------------------------------------------------------
        # 5. Right Lower Limb (Thigh, Shin, Foot) - Mirrored
        # ---------------------------------------------------------------------
        JointLimitSpec(
            joint_id="thigh_R",
            bone_name="thigh.R",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.ELLIPTICAL_CONE,
            # thigh.R: Y=(0,0,-1) down, X=(1,0,0) right(outward!), Z=(0,1,0) forward
            # X: Hip flexion forward (+120 deg) / Extension backward (-25 deg)
            # Y: Internal/external femoral rotation (+/-40 deg)
            # Z: Abduction outward (-50 deg) / Adduction inward across midline (+25 deg) (inverted Z sign vs Left!)
            min_deg=(-25.0, -40.0, -50.0),
            max_deg=(120.0, 40.0, 25.0),
            compound_cone_max_deg=125.0,
            local_axis_description="X=Hip Flex/Ext, Y=Femoral twist, Z=Abduction(-50)/Adduction(+25)",
            source="Kapandji Vol 2 p. 14; Winter (2009)",
            engineering_notes="Mirrored right acetabulofemoral hip (Z axis sign flipped for abduction).",
        ),
        JointLimitSpec(
            joint_id="shin_R",
            bone_name="shin.R",
            allowed_dofs=("X",),
            constraint_mode=ConstraintMode.HINGE_1D,
            min_deg=(-145.0, -8.0, -3.0),
            max_deg=(2.0, 8.0, 3.0),
            local_axis_description="X=Knee flexion(-145)/hyperextension lock(+2), Y=Tibial twist slack, Z=Varus slack",
            source="Kapandji Vol 2 p. 76; Winter (2009)",
            engineering_notes="Mirrored right tibiofemoral knee hinge (strictly locked against forward bending).",
        ),
        JointLimitSpec(
            joint_id="foot_R",
            bone_name="foot.R",
            allowed_dofs=("X", "Y", "Z"),
            constraint_mode=ConstraintMode.BOX_EULER,
            min_deg=(-25.0, -25.0, -15.0),
            max_deg=(45.0, 20.0, 15.0),
            local_axis_description="X=Plantarflex/Dorsiflex, Y=Inversion/eversion, Z=Abduction/adduction",
            source="Kapandji Vol 2 p. 158; Siegler et al. (1988)",
            engineering_notes="Mirrored right ankle joint complex.",
        ),
    ]

    return {spec.bone_name: spec for spec in specs}


DEFAULT_HUMANOID_ROM_MODEL: JointModel = JointModel(
    model_name="DefaultHumanoidROM",
    joints=_build_default_humanoid_rom_joints(),
    notes=(
        "Standard 17-joint humanoid ROM model based on Kapandji, Winter, AAOS, and White & Panjabi. "
        "Root and Pelvis are excluded as non-joint floating base frames."
    ),
)


# =============================================================================
# Helper Constructors
# =============================================================================

def create_custom_joint_model(
    model_name: str,
    joint_specs: Sequence[JointLimitSpec],
    notes: str = "User custom joint model",
) -> JointModel:
    """Construct a custom JointModel from a sequence of JointLimitSpec objects."""
    return JointModel(
        model_name=model_name,
        joints={spec.bone_name: spec for spec in joint_specs},
        notes=notes,
    )
