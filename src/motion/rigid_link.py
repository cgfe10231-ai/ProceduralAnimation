"""Rigid link segments, body mass distribution models, and whole-body Center of Mass (CoM) computation (Task 6F-B).

Builds on the existing 19-bone CharacterArmature from Task 4B/4C/6F-A without altering rig structure:
- Defines clean data structures for rigid body segments (`RigidSegmentSpec`) and mass distributions (`BodyMassDistribution`).
- Decouples Blender control bones from anatomical mass segments (bones != mass segments 1:1 requirement).
- Provides standard biomechanical reference models (Dempster 1955, Winter 2009 15-segment model; 13-segment combined model).
- Allows runtime configuration overrides of total mass and segment ratios to support different body builds.
- Implements non-destructive, robust forward-kinematics Whole-Body Center of Mass (`compute_whole_body_com`)
  supporting arbitrary FK/IK poses, root motion, and object coordinate transformations.
- Distinguishes clearly between bone local space, Armature object space, and World space.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Matrix, Vector

DEFAULT_HUMAN_TOTAL_MASS_KG: float = 70.0


@dataclass(frozen=True)
class RigidSegmentSpec:
    """Specification of an anatomical rigid body segment and its local inertial properties.

    Attributes:
        segment_id: Unique identifier for this mass segment (e.g. 'head', 'torso', 'thigh_L').
        bone_name: Controlling bone in CharacterArmature to which this segment is bound.
        mass_ratio: Fraction of whole-body mass contributed by this segment (0.0 < mass_ratio <= 1.0).
        nominal_length: Reference anatomical length of this link in meters.
        local_com_fraction: Distance fraction t in [0.0, 1.0] along the bone longitudinal (+Y) axis
            from proximal joint (bone head) toward distal joint (bone tail).
        local_com_offset: Additional 3D offset (dx, dy, dz) in meters in the bone local coordinate frame.
        description: Informational label or anatomical reference.
    """
    segment_id: str
    bone_name: str
    mass_ratio: float
    nominal_length: float
    local_com_fraction: float = 0.50
    local_com_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    description: str = ""

    def get_local_com(self, actual_length: Optional[float] = None) -> Vector:
        """Return the local Center of Mass position in bone local coordinates (meters).

        In this rig, bone +Y is the longitudinal axis (head -> tail).
        Local (0, 0, 0) is the proximal joint (bone head).
        """
        length = actual_length if actual_length is not None else self.nominal_length
        return Vector((
            self.local_com_offset[0],
            self.local_com_fraction * length + self.local_com_offset[1],
            self.local_com_offset[2],
        ))


@dataclass(frozen=True)
class BodyMassDistribution:
    """Complete whole-body mass distribution specification.

    Attributes:
        model_name: Name of this distribution model (e.g. 'DempsterWinter15').
        source: Biomechanical publication reference or modeling assumption.
        total_mass_kg: Total body mass in kilograms.
        segments: Tuple of RigidSegmentSpec definitions covering all body segments.
    """
    model_name: str
    source: str
    total_mass_kg: float = DEFAULT_HUMAN_TOTAL_MASS_KG
    segments: Tuple[RigidSegmentSpec, ...] = field(default_factory=tuple)

    def __post_init__(self):
        self.validate()

    def validate(self) -> None:
        """Validate mass distribution integrity: non-empty, positive masses, sum == 1.0, unique IDs."""
        if not self.segments:
            raise ValueError(f"BodyMassDistribution '{self.model_name}' has no segments")
        if self.total_mass_kg <= 0.0:
            raise ValueError(f"Total mass must be strictly positive, got {self.total_mass_kg} kg")

        seen_ids = set()
        ratio_sum = 0.0
        for seg in self.segments:
            if seg.segment_id in seen_ids:
                raise ValueError(f"Duplicate segment_id '{seg.segment_id}' in model '{self.model_name}'")
            seen_ids.add(seg.segment_id)
            if seg.mass_ratio <= 0.0:
                raise ValueError(f"Segment '{seg.segment_id}' mass ratio must be > 0, got {seg.mass_ratio}")
            ratio_sum += seg.mass_ratio

        if abs(ratio_sum - 1.0) > 1e-4:
            raise ValueError(
                f"Sum of segment mass ratios in '{self.model_name}' must equal 1.0, got {ratio_sum:.6f}"
            )

    def get_segment(self, segment_id: str) -> RigidSegmentSpec:
        """Retrieve a segment specification by its segment_id."""
        for seg in self.segments:
            if seg.segment_id == segment_id:
                return seg
        raise KeyError(f"Segment '{segment_id}' not found in model '{self.model_name}'")

    def get_segment_mass_kg(self, segment_id: str) -> float:
        """Return the absolute mass of a segment in kilograms."""
        return self.get_segment(segment_id).mass_ratio * self.total_mass_kg

    def with_total_mass(self, new_total_mass_kg: float) -> "BodyMassDistribution":
        """Return a copy of this mass distribution scaled to a new total mass."""
        if new_total_mass_kg <= 0.0:
            raise ValueError(f"Total mass must be positive, got {new_total_mass_kg}")
        return BodyMassDistribution(
            model_name=self.model_name,
            source=self.source,
            total_mass_kg=new_total_mass_kg,
            segments=self.segments,
        )

    def with_overrides(
        self,
        ratio_overrides: Dict[str, float],
        new_model_name: Optional[str] = None,
        normalize: bool = True,
    ) -> "BodyMassDistribution":
        """Return a new BodyMassDistribution with specified segment mass ratios modified."""
        updated = []
        for seg in self.segments:
            if seg.segment_id in ratio_overrides:
                new_ratio = ratio_overrides[seg.segment_id]
                updated.append(RigidSegmentSpec(
                    segment_id=seg.segment_id,
                    bone_name=seg.bone_name,
                    mass_ratio=new_ratio,
                    nominal_length=seg.nominal_length,
                    local_com_fraction=seg.local_com_fraction,
                    local_com_offset=seg.local_com_offset,
                    description=seg.description + " (overridden)",
                ))
            else:
                updated.append(seg)

        if normalize:
            curr_sum = sum(s.mass_ratio for s in updated)
            if curr_sum > 0:
                normalized = []
                for s in updated:
                    normalized.append(RigidSegmentSpec(
                        segment_id=s.segment_id,
                        bone_name=s.bone_name,
                        mass_ratio=s.mass_ratio / curr_sum,
                        nominal_length=s.nominal_length,
                        local_com_fraction=s.local_com_fraction,
                        local_com_offset=s.local_com_offset,
                        description=s.description,
                    ))
                updated = normalized

        return BodyMassDistribution(
            model_name=new_model_name or f"{self.model_name}_Custom",
            source=f"Derived from {self.source} with overrides",
            total_mass_kg=self.total_mass_kg,
            segments=tuple(updated),
        )


@dataclass
class SegmentCoMResult:
    """Evaluated Center of Mass position and mass properties for an individual segment."""
    segment_id: str
    bone_name: str
    mass_kg: float
    mass_ratio: float
    local_com: Vector       # Position in bone local space (m)
    armature_com: Vector    # Position in Armature object space (m)
    world_com: Vector       # Position in World space (m)


@dataclass
class WholeBodyCoMResult:
    """Evaluated whole-body center of mass result and individual segment breakdown."""
    com_world: Vector                       # Whole-body CoM in World coordinates (m)
    com_armature: Vector                    # Whole-body CoM in Armature object coordinates (m)
    total_mass_kg: float                    # Total body mass in kg
    model_name: str                         # Name of the mass distribution model used
    segments: Dict[str, SegmentCoMResult]   # Detailed per-segment CoM results keyed by segment_id


# =============================================================================
# Predefined Biomechanical Body Mass Distribution Models
# =============================================================================

# 1. Dempster (1955) / Winter (2009) Standard 15-Segment Model
# Sources:
# - Winter, D.A. (2009). "Biomechanics and Motor Control of Human Movement", 4th ed., Table 4.1.
# - Dempster, W.T. (1955). "Space Requirements of the Seated Operator", WADC-TR-55-159.
#
# Mass ratios:
#   Head: 0.081 (8.1%)
#   Torso: 0.355 (35.5% - Thorax + Abdomen)
#   Pelvis: 0.142 (14.2%)
#   Upper Arm (x2): 0.028 (2.8% each, total 5.6%)
#   Forearm (x2): 0.016 (1.6% each, total 3.2%)
#   Hand (x2): 0.006 (0.6% each, total 1.2%)
#   Thigh (x2): 0.100 (10.0% each, total 20.0%)
#   Shank / Lower Leg (x2): 0.0465 (4.65% each, total 9.3%)
#   Foot (x2): 0.0145 (1.45% each, total 2.9%)
#   Sum = 0.081 + 0.355 + 0.142 + 2*(0.028 + 0.016 + 0.006) + 2*(0.100 + 0.0465 + 0.0145) = 1.0000
DEMPSTER_WINTER_15_SEGMENT_MODEL = BodyMassDistribution(
    model_name="DempsterWinter15",
    source="Winter (2009) Table 4.1 / Dempster (1955) standard 15-segment humanoid distribution",
    total_mass_kg=DEFAULT_HUMAN_TOTAL_MASS_KG,
    segments=(
        RigidSegmentSpec("head", "head", 0.0810, 0.22, 0.500, (0.0, 0.0, 0.0), "Head & Neck"),
        RigidSegmentSpec("torso", "spine", 0.3550, 0.48, 0.550, (0.0, 0.0, 0.0), "Thorax & Abdomen"),
        RigidSegmentSpec("pelvis", "pelvis", 0.1420, 0.18, 0.500, (0.0, 0.0, 0.0), "Pelvis & Sacrum"),
        RigidSegmentSpec("upper_arm_L", "upper_arm.L", 0.0280, 0.30, 0.436, (0.0, 0.0, 0.0), "Left Upper Arm"),
        RigidSegmentSpec("upper_arm_R", "upper_arm.R", 0.0280, 0.30, 0.436, (0.0, 0.0, 0.0), "Right Upper Arm"),
        RigidSegmentSpec("forearm_L", "forearm.L", 0.0160, 0.26, 0.430, (0.0, 0.0, 0.0), "Left Forearm"),
        RigidSegmentSpec("forearm_R", "forearm.R", 0.0160, 0.26, 0.430, (0.0, 0.0, 0.0), "Right Forearm"),
        RigidSegmentSpec("hand_L", "hand.L", 0.0060, 0.10, 0.506, (0.0, 0.0, 0.0), "Left Hand"),
        RigidSegmentSpec("hand_R", "hand.R", 0.0060, 0.10, 0.506, (0.0, 0.0, 0.0), "Right Hand"),
        RigidSegmentSpec("thigh_L", "thigh.L", 0.1000, 0.42, 0.433, (0.0, 0.0, 0.0), "Left Thigh"),
        RigidSegmentSpec("thigh_R", "thigh.R", 0.1000, 0.42, 0.433, (0.0, 0.0, 0.0), "Right Thigh"),
        RigidSegmentSpec("shin_L", "shin.L", 0.0465, 0.40, 0.433, (0.0, 0.0, 0.0), "Left Lower Leg"),
        RigidSegmentSpec("shin_R", "shin.R", 0.0465, 0.40, 0.433, (0.0, 0.0, 0.0), "Right Lower Leg"),
        RigidSegmentSpec("foot_L", "foot.L", 0.0145, 0.154, 0.500, (0.0, 0.0, -0.010), "Left Foot"),
        RigidSegmentSpec("foot_R", "foot.R", 0.0145, 0.154, 0.500, (0.0, 0.0, -0.010), "Right Foot"),
    ),
)

# 2. Combined 13-Segment Model (Forearm + Hand combined into LowerArm, matching 13 placeholder meshes)
# Ratios: LowerArm (Forearm 0.016 + Hand 0.006 = 0.0220), CoM ~45% from elbow
DEMPSTER_13_SEGMENT_MODEL = BodyMassDistribution(
    model_name="Dempster13Combined",
    source="Dempster/Winter with Forearm+Hand combined, matching Task 4A 13-part meshes",
    total_mass_kg=DEFAULT_HUMAN_TOTAL_MASS_KG,
    segments=(
        RigidSegmentSpec("Head", "head", 0.0810, 0.22, 0.500, (0.0, 0.0, 0.0), "Head mesh"),
        RigidSegmentSpec("Torso", "spine", 0.3550, 0.48, 0.550, (0.0, 0.0, 0.0), "Torso mesh"),
        RigidSegmentSpec("Pelvis", "pelvis", 0.1420, 0.18, 0.500, (0.0, 0.0, 0.0), "Pelvis mesh"),
        RigidSegmentSpec("UpperArm_L", "upper_arm.L", 0.0280, 0.30, 0.436, (0.0, 0.0, 0.0), "UpperArm_L mesh"),
        RigidSegmentSpec("UpperArm_R", "upper_arm.R", 0.0280, 0.30, 0.436, (0.0, 0.0, 0.0), "UpperArm_R mesh"),
        RigidSegmentSpec("LowerArm_L", "forearm.L", 0.0220, 0.26, 0.450, (0.0, 0.0, 0.0), "LowerArm_L mesh"),
        RigidSegmentSpec("LowerArm_R", "forearm.R", 0.0220, 0.26, 0.450, (0.0, 0.0, 0.0), "LowerArm_R mesh"),
        RigidSegmentSpec("UpperLeg_L", "thigh.L", 0.1000, 0.42, 0.433, (0.0, 0.0, 0.0), "UpperLeg_L mesh"),
        RigidSegmentSpec("UpperLeg_R", "thigh.R", 0.1000, 0.42, 0.433, (0.0, 0.0, 0.0), "UpperLeg_R mesh"),
        RigidSegmentSpec("LowerLeg_L", "shin.L", 0.0465, 0.40, 0.433, (0.0, 0.0, 0.0), "LowerLeg_L mesh"),
        RigidSegmentSpec("LowerLeg_R", "shin.R", 0.0465, 0.40, 0.433, (0.0, 0.0, 0.0), "LowerLeg_R mesh"),
        RigidSegmentSpec("Foot_L", "foot.L", 0.0145, 0.154, 0.500, (0.0, 0.0, -0.010), "Foot_L mesh"),
        RigidSegmentSpec("Foot_R", "foot.R", 0.0145, 0.154, 0.500, (0.0, 0.0, -0.010), "Foot_R mesh"),
    ),
)


# =============================================================================
# Core Center of Mass (CoM) Evaluation API
# =============================================================================

def compute_whole_body_com(
    armature_obj: Optional[bpy.types.Object] = None,
    mass_distribution: Optional[BodyMassDistribution] = None,
    total_mass_kg: Optional[float] = None,
    update_scene: bool = True,
) -> WholeBodyCoMResult:
    """Compute the mass-weighted Whole-Body Center of Mass (CoM) from current armature pose.

    Evaluates arbitrary FK/IK poses cleanly by reading Blender's post-constraint evaluated
    pose bone matrices (`pose_bone.matrix`) and transforming segment local CoM positions
    into Armature space and World space.

    Args:
        armature_obj: CharacterArmature object. Defaults to searching scene for "CharacterArmature".
        mass_distribution: Mass distribution specification. Defaults to DEMPSTER_WINTER_15_SEGMENT_MODEL.
        total_mass_kg: Optional total mass override in kg.
        update_scene: If True, calls view_layer.update() before reading evaluated bone matrices.

    Returns:
        WholeBodyCoMResult containing com_world, com_armature, total_mass_kg, and per-segment results.

    Non-destructive: Does NOT alter bone matrices, locations, rotations, or constraints.
    """
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found")

    dist = mass_distribution if mass_distribution is not None else DEMPSTER_WINTER_15_SEGMENT_MODEL
    if total_mass_kg is not None:
        dist = dist.with_total_mass(total_mass_kg)

    if update_scene:
        bpy.context.view_layer.update()

    arm_mat_world = armature_obj.matrix_world
    segment_results: Dict[str, SegmentCoMResult] = {}

    com_world_accum = Vector((0.0, 0.0, 0.0))
    com_arm_accum = Vector((0.0, 0.0, 0.0))
    mass_sum = 0.0

    for seg in dist.segments:
        pb = armature_obj.pose.bones.get(seg.bone_name)
        if pb is None:
            raise KeyError(
                f"Bone '{seg.bone_name}' required by mass segment '{seg.segment_id}' "
                f"not found in '{armature_obj.name}'"
            )

        # 1. Local CoM position in bone local coordinate frame
        local_com = seg.get_local_com(actual_length=pb.length)

        # 2. Transform into Armature object space:
        # In Blender, pose_bone.matrix represents the bone frame relative to Armature object origin.
        armature_com = pb.matrix @ local_com

        # 3. Transform into World space:
        # arm_mat_world encompasses Armature location/rotation and parent (CharacterRoot) transforms.
        world_com = arm_mat_world @ armature_com

        mass_kg = seg.mass_ratio * dist.total_mass_kg
        mass_sum += mass_kg

        com_world_accum += seg.mass_ratio * world_com
        com_arm_accum += seg.mass_ratio * armature_com

        segment_results[seg.segment_id] = SegmentCoMResult(
            segment_id=seg.segment_id,
            bone_name=seg.bone_name,
            mass_kg=mass_kg,
            mass_ratio=seg.mass_ratio,
            local_com=local_com,
            armature_com=armature_com,
            world_com=world_com,
        )

    return WholeBodyCoMResult(
        com_world=com_world_accum,
        com_armature=com_arm_accum,
        total_mass_kg=dist.total_mass_kg,
        model_name=dist.model_name,
        segments=segment_results,
    )


def create_custom_mass_distribution(
    model_name: str,
    segments: Sequence[RigidSegmentSpec],
    total_mass_kg: float = DEFAULT_HUMAN_TOTAL_MASS_KG,
    source: str = "User Custom Specification",
) -> BodyMassDistribution:
    """Helper constructor for custom mass distribution models with auto-validation."""
    return BodyMassDistribution(
        model_name=model_name,
        source=source,
        total_mass_kg=total_mass_kg,
        segments=tuple(segments),
    )
