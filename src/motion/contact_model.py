"""Multi-Limb Contact Geometry, Constraints, and Support State System (Task 6G-C).

Physics-constraint-assisted procedural animation: provides a unified, extensible contact
model for humanoid characters interacting with complex environments (ground, walls, obstacles, ledges).

Key Capabilities:
- Distinguishes clearly between contact constraint types:
  * UNILATERAL: One-way compression/push only, no adhesive pull (e.g. feet on ground, hand push).
  * GRASP / BILATERAL: Two-way fixed or constrained attachment (e.g. hand hanging from a bar/ledge).
  * FREE / FLIGHT: Disengaged limb, no contact constraint applied.
- Contact lifecycle management:
  * CANDIDATE -> ESTABLISHED (Active) -> RELEASED (Actively unlocked) / BROKEN (Violated).
- Read-only geometric constraint validation:
  * Distinguishes body local anchor (e.g. sole, palm) from bone origin.
  * Environment local anchor tracking under environment rigid transformations.
  * Normal distance (gap vs penetration depth) and tangential slip calculations.
  * Outward unit surface normal convention: unit vector pointing out from environment into free space.
- Unified multi-limb support state representation:
  * Double stance, single stance, hand vault/touch, ground+wall support, ledge hang, full flight phase.
  * Coplanar ground 2D support polygon computation (with documented physical disclaimers).
- Seamless bidirectional compatibility with MotionState, ContactPointState, and WholeBodyController.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

import bpy
from mathutils import Matrix, Quaternion, Vector

from src.motion.framework import (
    ContactPointState,
    EnvironmentQuery,
    MotionState,
    WORLD_UP_AXIS,
)


# =============================================================================
# 1. Enums and Conventions
# =============================================================================

class ContactType(str, Enum):
    """Physical constraint category of a contact."""
    UNILATERAL = "unilateral"   # Normal push only; no adhesive pull; tangential friction limit
    GRASP = "grasp"             # Bilateral constraint; resists push and pull in all 3 axes (bar/ledge hold)
    FREE = "free"               # Disengaged limb, zero contact constraint (flight/swing phase)


class ContactLifecycle(str, Enum):
    """Lifecycle state of a contact constraint."""
    CANDIDATE = "candidate"       # In proximity, evaluating potential contact engagement
    ESTABLISHED = "established"   # Actively engaged and enforcing geometric constraint
    RELEASED = "released"         # Intentionally disengaged by controller; old anchor discarded
    BROKEN = "broken"             # Unintentionally violated (excessive slip, detachment, or penetration)


class SupportType(str, Enum):
    """High-level classification of instantaneous multi-limb support state."""
    DOUBLE_STANCE = "double_stance"         # Both feet on ground plane
    SINGLE_STANCE_L = "single_stance_l"     # Left foot support only, right foot free/swing
    SINGLE_STANCE_R = "single_stance_r"     # Right foot support only, left foot free/swing
    HAND_SUPPORT = "hand_support"           # Hand(s) on obstacle or ground
    WALL_FOOT_STANCE = "wall_foot_stance"   # Foot on ground + foot on vertical wall
    LEDGE_HANG = "ledge_hang"               # Hand(s) grasping bar/ledge, body suspended, feet free
    MULTI_SURFACE = "multi_surface"         # Complex contact across multiple non-coplanar surfaces
    FLIGHT = "flight"                       # Zero active contacts (running jump, hurdle, airborne)


# Standard nominal limb local anchor offsets (meters) in bone local coordinate frames:
# - Foot bone (foot.L/R): bone head is ankle joint (Z=0.07 m above ground at rest).
#   Local anchor (0.0, 0.015906, -0.068169) accounts for bone pitch tilt (-13.13 deg) and places
#   contact anchor directly beneath the ankle on the sole at rest ground plane Z=0.0m.
# - Hand bone (hand.L/R): bone head is wrist. Bone length is 0.10 m along +Y.
#   Local anchor (0, 0.050, -0.015) places contact point at palm center.
DEFAULT_LIMB_LOCAL_ANCHORS: Dict[str, Tuple[float, float, float]] = {
    "foot_L": (0.0, 0.015906, -0.068169),
    "foot_R": (0.0, 0.015906, -0.068169),
    "hand_L": (0.0, 0.050, -0.015),
    "hand_R": (0.0, 0.050, -0.015),
    "knee_L": (0.0, 0.000, 0.050),
    "knee_R": (0.0, 0.000, 0.050),
    "elbow_L": (0.0, 0.000, -0.040),
    "elbow_R": (0.0, 0.000, -0.040),
}

# Associated bone names in CharacterArmature
LIMB_TO_BONE_NAME: Dict[str, str] = {
    "foot_L": "foot.L",
    "foot_R": "foot.R",
    "hand_L": "hand.L",
    "hand_R": "hand.R",
    "knee_L": "shin.L",
    "knee_R": "shin.R",
    "elbow_L": "forearm.L",
    "elbow_R": "forearm.R",
}

# Known lowercase legacy keys mapping to canonical public MotionState limb names
KNOWN_LEGACY_LIMB_MAP: Dict[str, str] = {
    "foot_l": "foot_L",
    "foot_r": "foot_R",
    "hand_l": "hand_L",
    "hand_r": "hand_R",
}


# =============================================================================
# 2. Geometric Constraint Checking Result
# =============================================================================

@dataclass(frozen=True)
class GeometricConstraintResult:
    """Quantitative evaluation of a contact's instantaneous geometric compliance.

    Normal distance sign convention:
    - distance_normal > 0: GAP (body anchor is detached/separated from environment surface).
    - distance_normal < 0: PENETRATION (body anchor has penetrated inside the surface).
    - distance_normal == 0: Exact contact alignment.
    """
    is_valid: bool
    total_position_error_m: float
    distance_normal_m: float
    penetration_depth_m: float
    tangential_slip_m: float
    violation_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 3. Contact Record Data Structure
# =============================================================================

@dataclass
class ContactRecord:
    """Comprehensive multi-limb physical contact specification and state.

    Attributes:
        contact_id: Unique identifier for this contact event (e.g. 'ground_foot_L_001').
        limb: Body contact site ('foot_L', 'foot_R', 'hand_L', 'hand_R', etc.).
        surface_id: Identifier of the environmental surface or obstacle (e.g. 'ground_plane', 'wall_01').
        contact_type: UNILATERAL, GRASP, or FREE.
        lifecycle: CANDIDATE, ESTABLISHED, RELEASED, or BROKEN.
        world_position: World-space position of target contact point (m).
        world_normal: Outward unit normal vector in World Space (pointing out from surface).
        body_local_anchor: Local anchor offset in bone local frame (m).
        env_local_anchor: Optional local anchor offset in environment object space (m).
        env_object_name: Optional Blender object name of the environment obstacle.
        friction_coeff_static: Static friction coefficient mu_s (stored & validated).
        friction_coeff_dynamic: Dynamic friction coefficient mu_d.
        max_allowable_gap_m: Tolerance for normal separation before flagging violation (m).
        max_allowable_penetration_m: Tolerance for surface penetration before flagging violation (m).
        max_allowable_slip_m: Tolerance for tangential drift/slip before flagging violation (m).
        metadata: Extensible property bag for high-level action context.
    """
    contact_id: str
    limb: str
    surface_id: str
    contact_type: ContactType = ContactType.UNILATERAL
    lifecycle: ContactLifecycle = ContactLifecycle.ESTABLISHED
    world_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    world_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)
    body_local_anchor: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    env_local_anchor: Optional[Tuple[float, float, float]] = None
    env_object_name: Optional[str] = None
    friction_coeff_static: float = 0.60
    friction_coeff_dynamic: float = 0.50
    max_allowable_gap_m: float = 0.015          # 15 mm allowable air gap
    max_allowable_penetration_m: float = 0.010  # 10 mm allowable penetration
    max_allowable_slip_m: float = 0.020         # 20 mm allowable tangential slip
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_compliance_result: Optional[GeometricConstraintResult] = None

    def __setattr__(self, name: str, value: Any) -> None:
        # Invalidate compliance verification if lifecycle, contact type, geometric targets, or tolerances change
        if name in (
            "lifecycle",
            "contact_type",
            "world_position",
            "world_normal",
            "body_local_anchor",
            "max_allowable_gap_m",
            "max_allowable_penetration_m",
            "max_allowable_slip_m",
        ):
            if hasattr(self, name) and getattr(self, name) != value:
                super().__setattr__("last_compliance_result", None)
        super().__setattr__(name, value)

    def __post_init__(self):
        # Guarantee normal is strictly unit length
        nx, ny, nz = self.world_normal
        n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if n_len < 1e-6:
            self.world_normal = (0.0, 0.0, 1.0)
        else:
            self.world_normal = (nx / n_len, ny / n_len, nz / n_len)

        # Validate friction
        if self.friction_coeff_static < 0.0 or self.friction_coeff_dynamic < 0.0:
            raise ValueError("Friction coefficients must be non-negative")

    @property
    def is_lifecycle_active(self) -> bool:
        """True if contact lifecycle is ESTABLISHED and type is not FREE."""
        return self.lifecycle == ContactLifecycle.ESTABLISHED and self.contact_type != ContactType.FREE

    @property
    def is_effective_support(self) -> bool:
        """True if contact has valid lifecycle AND passed instantaneous geometric compliance check."""
        if not self.is_lifecycle_active:
            return False
        if self.last_compliance_result is None:
            # UNVALIDATED: unmeasured contacts cannot be assumed valid!
            return False
        return self.last_compliance_result.is_valid

    @property
    def is_active(self) -> bool:
        """True if contact provides effective physical support (SSOT)."""
        return self.is_effective_support

    def set_compliance_result(self, result: Optional[GeometricConstraintResult]) -> None:
        """Set instantaneous geometric compliance result for this contact record."""
        self.last_compliance_result = result

    def reset_compliance(self) -> None:
        """Reset instantaneous compliance verification to UNVALIDATED (None)."""
        self.last_compliance_result = None

    def update_from_environment_transform(
        self,
        env_matrix_world: Union[Matrix, Sequence[Sequence[float]]],
    ) -> None:
        """Update world_position and world_normal when the environment object moves/rotates."""
        if self.env_local_anchor is None:
            return
        m = Matrix(env_matrix_world) if not isinstance(env_matrix_world, Matrix) else env_matrix_world
        local_p = Vector(self.env_local_anchor)
        world_p = m @ local_p
        self.world_position = (world_p.x, world_p.y, world_p.z)

        # Rotate normal vector via rotation submatrix
        rot_mat = m.to_3x3()
        # Assume initial local normal was aligned or compute via inverse-transpose for non-uniform scale
        local_n = Vector(self.metadata.get("env_local_normal", (0.0, 0.0, 1.0)))
        world_n = (rot_mat @ local_n).normalized()
        self.world_normal = (world_n.x, world_n.y, world_n.z)

    def compute_body_anchor_world_position(
        self,
        bone_matrix_world: Union[Matrix, Sequence[Sequence[float]]],
    ) -> Tuple[float, float, float]:
        """Compute the world-space coordinate of the body contact anchor given bone's world matrix."""
        m = Matrix(bone_matrix_world) if not isinstance(bone_matrix_world, Matrix) else bone_matrix_world
        p_world = m @ Vector(self.body_local_anchor)
        return (p_world.x, p_world.y, p_world.z)

    def check_geometric_compliance(
        self,
        current_body_world_pos: Tuple[float, float, float],
    ) -> GeometricConstraintResult:
        """Evaluate geometric error between current body anchor and environment target surface."""
        if self.contact_type == ContactType.FREE or self.lifecycle == ContactLifecycle.RELEASED:
            return GeometricConstraintResult(
                is_valid=True,
                total_position_error_m=0.0,
                distance_normal_m=0.0,
                penetration_depth_m=0.0,
                tangential_slip_m=0.0,
            )

        p_body = Vector(current_body_world_pos)
        p_target = Vector(self.world_position)
        n_surf = Vector(self.world_normal).normalized()

        disp = p_body - p_target
        tot_err = disp.length

        # Normal distance: disp . n (positive = gap away from surface; negative = penetration)
        d_norm = disp.dot(n_surf)
        gap = max(0.0, d_norm)
        penetration = max(0.0, -d_norm)

        # Tangential slip vector: disp - (disp . n) * n
        disp_tangent = disp - d_norm * n_surf
        slip = disp_tangent.length

        is_valid = True
        reason = None

        if self.contact_type == ContactType.UNILATERAL:
            # Unilateral constraint: cannot penetrate surface, cannot have large air gap, slip must be bounded
            if gap > self.max_allowable_gap_m:
                is_valid = False
                reason = f"EXCESSIVE_GAP: {gap * 1000.0:.2f} mm > {self.max_allowable_gap_m * 1000.0:.1f} mm"
            elif penetration > self.max_allowable_penetration_m:
                is_valid = False
                reason = f"EXCESSIVE_PENETRATION: {penetration * 1000.0:.2f} mm > {self.max_allowable_penetration_m * 1000.0:.1f} mm"
            elif slip > self.max_allowable_slip_m:
                is_valid = False
                reason = f"EXCESSIVE_SLIP: {slip * 1000.0:.2f} mm > {self.max_allowable_slip_m * 1000.0:.1f} mm"

        elif self.contact_type == ContactType.GRASP:
            # Bilateral constraint: holds fixed point in 3D (both normal and tangential displacement bounded)
            grasp_tol = max(self.max_allowable_gap_m, self.max_allowable_slip_m)
            if tot_err > grasp_tol:
                is_valid = False
                reason = f"GRASP_DISPLACEMENT: {tot_err * 1000.0:.2f} mm > {grasp_tol * 1000.0:.1f} mm"

        return GeometricConstraintResult(
            is_valid=is_valid,
            total_position_error_m=tot_err,
            distance_normal_m=d_norm,
            penetration_depth_m=penetration,
            tangential_slip_m=slip,
            violation_reason=reason,
        )


# =============================================================================
# 4. Multi-Contact and Support State
# =============================================================================

@dataclass
class MultiContactState:
    """Container representing all limb contacts and global support state at a frame."""
    frame: Optional[int] = None
    time_sec: float = 0.0
    contacts: Dict[str, ContactRecord] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        # If frame advances on an existing state, reset compliance on all contacts
        if name == "frame" and hasattr(self, "frame") and getattr(self, "frame") != value:
            for c in getattr(self, "contacts", {}).values():
                c.reset_compliance()
        super().__setattr__(name, value)

    @property
    def effective_contacts(self) -> Dict[str, ContactRecord]:
        """Return subset of contacts providing effective physical support (SSOT)."""
        return {k: v for k, v in self.contacts.items() if v.is_effective_support}

    @property
    def active_contacts(self) -> Dict[str, ContactRecord]:
        """Return subset of contacts providing effective physical support (SSOT)."""
        return self.effective_contacts

    @property
    def lifecycle_active_contacts(self) -> Dict[str, ContactRecord]:
        """Return subset of contacts with established lifecycle, regardless of compliance."""
        return {k: v for k, v in self.contacts.items() if v.is_lifecycle_active}

    @property
    def supporting_limbs(self) -> List[str]:
        """List of limb keys currently providing active physical support."""
        return list(self.active_contacts.keys())

    @property
    def active_contact_count(self) -> int:
        """Number of contacts providing effective physical support."""
        return len(self.active_contacts)

    @property
    def is_flight(self) -> bool:
        """True if the character has zero active support contacts (airborne)."""
        return len(self.active_contacts) == 0

    @property
    def support_type(self) -> SupportType:
        """Classify instantaneous support state based on active limbs and surfaces."""
        active = self.active_contacts
        if not active:
            return SupportType.FLIGHT

        has_foot_l = any(k in active for k in ("foot_L", "foot_l"))
        has_foot_r = any(k in active for k in ("foot_R", "foot_r"))
        has_hand_l = any(k in active for k in ("hand_L", "hand_l"))
        has_hand_r = any(k in active for k in ("hand_R", "hand_r"))

        # Ledge hang: hands active with GRASP, feet free
        if (has_hand_l or has_hand_r) and not has_foot_l and not has_foot_r:
            if any(c.contact_type == ContactType.GRASP for c in active.values()):
                return SupportType.LEDGE_HANG
            return SupportType.HAND_SUPPORT

        # Wall + foot stance: check if one contact normal is vertical and another is horizontal
        normals = [Vector(c.world_normal) for c in active.values()]
        has_ground_norm = any(abs(n.z - 1.0) < 0.1 for n in normals)
        has_wall_norm = any(abs(n.z) < 0.2 and (n.x * n.x + n.y * n.y) > 0.8 for n in normals)
        if has_ground_norm and has_wall_norm:
            return SupportType.WALL_FOOT_STANCE

        # Hand touch / vault
        if (has_hand_l or has_hand_r) and (has_foot_l or has_foot_r):
            return SupportType.MULTI_SURFACE

        # Stance configurations
        if has_foot_l and has_foot_r:
            return SupportType.DOUBLE_STANCE
        elif has_foot_l:
            return SupportType.SINGLE_STANCE_L
        elif has_foot_r:
            return SupportType.SINGLE_STANCE_R

        return SupportType.MULTI_SURFACE

    def check_all_contacts(
        self,
        current_limb_positions: Dict[str, Tuple[float, float, float]],
    ) -> Dict[str, GeometricConstraintResult]:
        """Check geometric constraints for all contacts given evaluated limb positions.

        Evaluates geometric compliance, commits the result to each ContactRecord,
        and returns the dictionary of results mapping limb -> GeometricConstraintResult.
        """
        results = {}
        for limb, c in self.contacts.items():
            if limb in current_limb_positions:
                res = c.check_geometric_compliance(current_limb_positions[limb])
            elif c.contact_type == ContactType.FREE or c.lifecycle == ContactLifecycle.RELEASED:
                res = c.check_geometric_compliance((0.0, 0.0, 0.0))
            else:
                # Deterministic failure for missing limb measurement on non-free/non-released contact
                res = GeometricConstraintResult(
                    is_valid=False,
                    total_position_error_m=float("inf"),
                    distance_normal_m=float("inf"),
                    penetration_depth_m=0.0,
                    tangential_slip_m=0.0,
                    violation_reason=f"MISSING_MEASUREMENT: Limb '{limb}' has no measured position in current_limb_positions",
                    details={"missing_limb": limb},
                )
            c.set_compliance_result(res)
            results[limb] = res
        return results

    def reset_compliance(self) -> None:
        """Reset instantaneous compliance status for all contacts."""
        for c in self.contacts.values():
            c.reset_compliance()

    def get_coplanar_support_polygon(
        self,
        coplanar_tolerance_z: float = 0.03,
        vertical_normal_tol: float = 0.05,
    ) -> Tuple[bool, Optional[List[Tuple[float, float]]]]:
        """Compute the 2D convex hull of active coplanar ground contact points.

        Returns:
            (is_coplanar, polygon_2d_points)
            - If contacts are non-coplanar (e.g. wall contact or hanging), is_coplanar is False
              and polygon is None.
            - If in flight phase, returns (True, []).

        Physical Disclaimer:
            A 2D support polygon defines the geometric boundary of ground contacts;
            it does NOT guarantee dynamic stability (no ZMP, capture point, or balance recovery).
        """
        active = self.active_contacts
        if not active:
            return (True, [])

        # Check coplanarity with horizontal ground
        z_vals = [c.world_position[2] for c in active.values()]
        normals = [c.world_normal for c in active.values()]

        min_z, max_z = min(z_vals), max(z_vals)
        if (max_z - min_z) > coplanar_tolerance_z:
            return (False, None)  # Non-coplanar heights (e.g. one foot on ground, one on ledge/wall)

        for nx, ny, nz in normals:
            if abs(nz - 1.0) > vertical_normal_tol:
                return (False, None)  # Non-vertical surface normal (e.g. vertical wall)

        # Extract 2D ground points (X, Y)
        points_2d = [(c.world_position[0], c.world_position[1]) for c in active.values()]
        hull = _compute_2d_convex_hull(points_2d)
        return (True, hull)


# =============================================================================
# 5. Convex Hull Utility (Monotone Chain Algorithm)
# =============================================================================

def _compute_2d_convex_hull(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Compute 2D convex hull of points in Counter-Clockwise order (Monotone Chain algorithm)."""
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in points))
    if len(pts) <= 2:
        return list(pts)

    def cross(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 1e-9:
            lower.pop()
        lower.append(p)

    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 1e-9:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


# =============================================================================
# 6. Adapter & Compatibility Helpers
# =============================================================================

def contact_record_to_legacy_contact_point(record: ContactRecord) -> ContactPointState:
    """Convert a modern ContactRecord to a legacy ContactPointState for MotionState compatibility."""
    is_effective = record.is_effective_support
    phase = "stance" if is_effective else "swing"
    return ContactPointState(
        limb=record.limb,
        phase=phase,
        is_locked=is_effective,
        contact_world_xyz=record.world_position,
        current_world_xyz=record.world_position,
        surface_normal=record.world_normal,
        drift_m=0.0,
        is_reachable=True,
    )


def legacy_contact_point_to_contact_record(
    legacy: ContactPointState,
    contact_id: Optional[str] = None,
    surface_id: str = "ground_plane",
) -> ContactRecord:
    """Convert a legacy ContactPointState to a full ContactRecord."""
    c_type = ContactType.UNILATERAL if legacy.is_locked else ContactType.FREE
    c_life = ContactLifecycle.ESTABLISHED if legacy.is_locked else ContactLifecycle.RELEASED
    cid = contact_id or f"{surface_id}_{legacy.limb}"
    anchor = DEFAULT_LIMB_LOCAL_ANCHORS.get(legacy.limb, (0.0, 0.0, 0.0))
    return ContactRecord(
        contact_id=cid,
        limb=legacy.limb,
        surface_id=surface_id,
        contact_type=c_type,
        lifecycle=c_life,
        world_position=legacy.contact_world_xyz,
        world_normal=legacy.surface_normal,
        body_local_anchor=anchor,
    )


def enrich_motion_state_with_contacts(
    motion_state: MotionState,
    multi_contact: MultiContactState,
) -> MotionState:
    """Enrich a MotionState with multi-contact telemetry, updating contacts dict and params."""
    legacy_contacts: Dict[str, ContactPointState] = {}
    for limb, rec in multi_contact.contacts.items():
        canonical_limb = KNOWN_LEGACY_LIMB_MAP.get(limb, limb)
        if canonical_limb in legacy_contacts:
            raise ValueError(
                f"Conflicting contact input for canonical limb '{canonical_limb}': "
                f"attempted to register '{limb}' but '{canonical_limb}' is already present in contacts."
            )
        legacy_point = contact_record_to_legacy_contact_point(rec)
        legacy_contacts[canonical_limb] = legacy_point

    is_flight = multi_contact.is_flight
    support_str = multi_contact.support_type.value

    updated_params = dict(motion_state.params)
    updated_params["support_type"] = support_str
    updated_params["supporting_limbs"] = multi_contact.supporting_limbs
    updated_params["active_contact_count"] = multi_contact.active_contact_count

    is_coplanar, poly = multi_contact.get_coplanar_support_polygon()
    if is_coplanar and poly is not None:
        updated_params["support_polygon_2d"] = poly
        updated_params["is_support_coplanar"] = True
    else:
        updated_params["support_polygon_2d"] = None
        updated_params["is_support_coplanar"] = False

    return motion_state.clone_with(
        contacts=legacy_contacts,
        is_airborne=is_flight,
        params=updated_params,
    )


# =============================================================================
# 7. Environment Geometry Generator & Evaluator
# =============================================================================

@dataclass
class EnvironmentalSurface:
    """Explicit geometry description of a physical environment surface/obstacle."""
    surface_id: str
    surface_type: str                   # 'ground', 'wall', 'box_top', 'ledge_bar'
    center_world: Tuple[float, float, float]
    normal_world: Tuple[float, float, float]
    dimensions: Tuple[float, float, float] = (1.0, 1.0, 1.0) # Length, Width, Height
    friction_static: float = 0.60
    friction_dynamic: float = 0.50


def evaluate_limb_contacts_from_armature(
    armature_obj: bpy.types.Object,
    surfaces: Sequence[EnvironmentalSurface],
    active_limb_targets: Dict[str, Dict[str, Any]],
) -> MultiContactState:
    """Evaluate contact states for specified limbs against environmental surfaces."""
    contacts: Dict[str, ContactRecord] = {}

    for limb, spec in active_limb_targets.items():
        bone_name = LIMB_TO_BONE_NAME.get(limb)
        pb = armature_obj.pose.bones.get(bone_name) if bone_name else None
        anchor_local = spec.get("local_anchor", DEFAULT_LIMB_LOCAL_ANCHORS.get(limb, (0.0, 0.0, 0.0)))

        # Actual limb anchor world coordinate
        if pb is not None:
            bone_mat_world = armature_obj.matrix_world @ pb.matrix
            actual_world_p = bone_mat_world @ Vector(anchor_local)
        else:
            actual_world_p = Vector(spec.get("target_world", (0.0, 0.0, 0.0)))

        # Target surface
        surface_id = spec.get("surface_id", "ground")
        target_pos = spec.get("target_world", (actual_world_p.x, actual_world_p.y, 0.0))
        target_normal = spec.get("normal_world", (0.0, 0.0, 1.0))
        c_type = spec.get("contact_type", ContactType.UNILATERAL)
        c_life = spec.get("lifecycle", ContactLifecycle.ESTABLISHED)

        rec = ContactRecord(
            contact_id=f"{surface_id}_{limb}",
            limb=limb,
            surface_id=surface_id,
            contact_type=c_type,
            lifecycle=c_life,
            world_position=target_pos,
            world_normal=target_normal,
            body_local_anchor=anchor_local,
            friction_coeff_static=spec.get("friction_static", 0.60),
            friction_coeff_dynamic=spec.get("friction_dynamic", 0.50),
        )
        contacts[limb] = rec

    return MultiContactState(contacts=contacts)
