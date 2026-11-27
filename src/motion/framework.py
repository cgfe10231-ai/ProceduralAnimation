"""Extensible Procedural Motion System Foundation (Task 6A).

Establishes the minimal, modular architecture required to chain and compose procedural
3D character motions without hardcoding global frame numbers or duplicating biomechanics:

1. Coordinate Space Conventions (`WORLD_FORWARD_AXIS`, `world_to_root_local_vector`, `root_local_to_world_vector`):
   - **World Space**: Right-handed Blender world coordinates (`+X` Right, `+Y` Forward at 0° yaw, `+Z` Up, `Z = 0.0 m` ground plane).
   - **CharacterRoot Local Space**: Origin at `CharacterRoot.location` (between the ankles at `Z = 0.0 m` on flat ground). At `orientation_deg = (0, 0, 0)`, local `+X` is Right, local `+Y` is Forward, and local `+Z` is Up.
   - **Armature Bone Local Space**: Vertical rest-pose bones (`pelvis`, `spine`, `neck`, `head`) have bone `+Y` aligned with World `+Z` (Up), bone `+X` aligned with World `+X` (Right), and bone `+Z` aligned with World `-Y` (Backward).

2. Unified State Representation (`MotionMode`, `ContactPointState`, `MotionState`):
   - Captures position, orientation, velocity vector, acceleration vector, motion mode, gait phase,
     and multi-limb contact states (`foot_L`, `foot_R`, and extensible to `hand_L`, `hand_R`).

3. Explicit Responsibility Boundaries:
   - `EnvironmentQuery`: Ground height, surface normal, and future obstacle geometry queries.
   - `ContactConstraintAdapter`: Bridges `MotionState.contacts` with low-level IK & foot locking (`src/rig/foot_contact.py`).
   - `BlenderPoseApplicator`: Applies bone pose transforms, swing IK targets, and keyframes (`src/rig/pose.py`, `src/rig/ik.py`, `src/motion/walk_cycle.py`).
   - `MotionAction`: Composable action interface (`initial_state -> trajectory + final_state`) independent of hardcoded start frames.
   - `MotionPlanner`: Sequences and executes one or more `MotionAction` instances, threading `MotionState` across action boundaries.
   - `StartStopWalkAction`: Thin adapter wrapping the verified Task 5C start-accelerate-walk-decelerate-stop generator (`src/motion/start_stop_walk.py`).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum
import inspect
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Vector

from src.character.builder import character_start_location
from src.config import PipelineConfig
from src.motion.forward_walk import compute_forward_swing_point
from src.motion.start_stop_walk import (
    _apply_start_stop_upper_body_pose,
    _evaluate_gait_phase_and_envelopes,
    _smooth_bell01,
    build_step_schedule,
    evaluate_root_kinematics,
)
from src.motion.upper_limb_trajectory import (
    UpperLimbSegment,
    evaluate_upper_limb_sequence_at_time,
    validate_upper_limb_segment_sequence,
)
from src.motion.walk_cycle import _clear_existing_animation_data, _keyframe_walk_frame
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    _resolve_armature,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)
from src.rig.pose import reset_pose

# ============================================================================
# 1. Coordinate Conventions & Spatial Helpers
# ============================================================================

WORLD_RIGHT_AXIS: Tuple[float, float, float] = (1.0, 0.0, 0.0)
WORLD_FORWARD_AXIS: Tuple[float, float, float] = (0.0, 1.0, 0.0)
WORLD_UP_AXIS: Tuple[float, float, float] = (0.0, 0.0, 1.0)


def forward_unit_vector_from_yaw(yaw_deg: float) -> Tuple[float, float, float]:
    """Return the World-space horizontal forward unit vector for a given `CharacterRoot` Z-yaw (deg).

    At `yaw_deg = 0.0`, character faces World `+Y` `(0.0, 1.0, 0.0)`.
    Positive yaw rotates counter-clockwise around World `+Z`.
    """
    rad = math.radians(yaw_deg)
    return (-math.sin(rad), math.cos(rad), 0.0)


def right_unit_vector_from_yaw(yaw_deg: float) -> Tuple[float, float, float]:
    """Return the World-space horizontal right unit vector (`+X` at `yaw_deg = 0.0`)."""
    rad = math.radians(yaw_deg)
    return (math.cos(rad), math.sin(rad), 0.0)


def world_to_root_local_vector(
    vec_world: Tuple[float, float, float],
    yaw_deg: float,
) -> Tuple[float, float, float]:
    """Convert a 3D vector (e.g., velocity or acceleration) from World Space to CharacterRoot Local Space."""
    rx, ry, _ = right_unit_vector_from_yaw(yaw_deg)
    fx, fy, _ = forward_unit_vector_from_yaw(yaw_deg)
    wx, wy, wz = vec_world
    local_x = wx * rx + wy * ry
    local_y = wx * fx + wy * fy
    local_z = wz
    return (local_x, local_y, local_z)


def root_local_to_world_vector(
    vec_local: Tuple[float, float, float],
    yaw_deg: float,
) -> Tuple[float, float, float]:
    """Convert a 3D vector from CharacterRoot Local Space (`+X` Right, `+Y` Forward, `+Z` Up) to World Space."""
    rx, ry, _ = right_unit_vector_from_yaw(yaw_deg)
    fx, fy, _ = forward_unit_vector_from_yaw(yaw_deg)
    lx, ly, lz = vec_local
    world_x = lx * rx + ly * fx
    world_y = lx * ry + ly * fy
    world_z = lz
    return (world_x, world_y, world_z)


# ============================================================================
# 2. Unified MotionState & Contact Representation
# ============================================================================

class MotionMode(str, Enum):
    """Canonical locomotion and parkour/stunt motion modes.

    Currently active in Task 5A-6A:
      `IDLE`, `START`, `ACCELERATE`, `WALK`, `DECELERATE`, `STOP`.
    Reserved for Task 6B+ expansion:
      `TURN`, `RUN`, `SPRINT`, `JUMP`, `AIRBORNE`, `ROLL`, `SLIDE`,
      `VAULT`, `CLIMB`, `WALL_RUN`, `SLOPE_BOOST`.
    """

    IDLE = "idle"
    START = "start"
    ACCELERATE = "accelerate"
    WALK = "walk"
    DECELERATE = "decelerate"
    STOP = "stop"
    # Reserved modes for subsequent tasks (no action implementation in Task 6A)
    TURN = "turn"
    RUN = "run"
    SPRINT = "sprint"
    JUMP = "jump"
    AIRBORNE = "airborne"
    ROLL = "roll"
    SLIDE = "slide"
    VAULT = "vault"
    CLIMB = "climb"
    WALL_RUN = "wall_run"
    SLOPE_BOOST = "slope_boost"


STAGE_TO_MOTION_MODE: Dict[str, MotionMode] = {
    "stand_start": MotionMode.IDLE,
    "start": MotionMode.START,
    "accelerate": MotionMode.ACCELERATE,
    "steady_walk": MotionMode.WALK,
    "decelerate": MotionMode.DECELERATE,
    "stop_step": MotionMode.STOP,
    "stand_stop": MotionMode.IDLE,
}


@dataclass(frozen=True)
class ContactPointState:
    """State of a single limb contact point (foot_L, foot_R, or future hand_L, hand_R).

    All spatial coordinates (`contact_world_xyz`, `current_world_xyz`, `surface_normal`)
    are expressed in Blender World Space (meters).
    """

    limb: str  # e.g. "foot_L", "foot_R", "hand_L", "hand_R"
    phase: str  # "stance", "swing", "support", or "free"
    is_locked: bool
    contact_world_xyz: Tuple[float, float, float]
    current_world_xyz: Tuple[float, float, float]
    target_rotation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    drift_m: float = 0.0
    hip_to_target_dist: float = 0.0
    is_reachable: bool = True
    strictly_in_reach: bool = True
    surface_normal: Tuple[float, float, float] = WORLD_UP_AXIS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limb": self.limb,
            "phase": self.phase,
            "is_locked": self.is_locked,
            "contact_world_xyz": self.contact_world_xyz,
            "current_world_xyz": self.current_world_xyz,
            "target_rotation_deg": self.target_rotation_deg,
            "drift_m": round(self.drift_m, 6),
            "hip_to_target_dist": round(self.hip_to_target_dist, 6),
            "is_reachable": self.is_reachable,
            "strictly_in_reach": self.strictly_in_reach,
            "surface_normal": self.surface_normal,
        }


@dataclass(frozen=True)
class MotionState:
    """Unified kinematic and contact state of the character at a discrete timeline frame.

    Coordinate Conventions:
    - `position`: `CharacterRoot` World-space position `(x, y, z)` in meters.
    - `orientation_deg`: `CharacterRoot` World-space Euler `(roll_x, pitch_y, yaw_z)` in degrees.
      At `(0, 0, 0)`, the character faces World `+Y`.
    - `velocity`: World-space velocity vector `(vx, vy, vz)` in `m/s`.
    - `acceleration`: World-space acceleration vector `(ax, ay, az)` in `m/s^2`.
    - `mode`: Active `MotionMode`.
    - `gait_phase`: Normalized cyclic gait phase `u` in `[0.0, 1.0)`.
    - `contacts`: Dictionary mapping limb keys (`"foot_L"`, `"foot_R"`, and optionally
      `"hand_L"`, `"hand_R"`) to `ContactPointState`.
    - `is_airborne`: True when no foot/hand contact is locked in support/stance.
    - `params`: Extensible dictionary for posture & step telemetry (`pelvis_dz`,
      `torso_lean_deg`, `gait_amp`, `step_k`, `stage`, etc.).
    """

    frame: int
    time_sec: float
    position: Tuple[float, float, float]
    orientation_deg: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    acceleration: Tuple[float, float, float]
    mode: MotionMode
    gait_phase: float
    contacts: Dict[str, ContactPointState] = field(default_factory=dict)
    is_airborne: bool = False
    params: Dict[str, Any] = field(default_factory=dict)

    @property
    def yaw_deg(self) -> float:
        return self.orientation_deg[2]

    @property
    def speed_mps(self) -> float:
        vx, vy, vz = self.velocity
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    @property
    def horizontal_speed_mps(self) -> float:
        vx, vy, _ = self.velocity
        return math.hypot(vx, vy)

    def forward_direction_world(self) -> Tuple[float, float, float]:
        return forward_unit_vector_from_yaw(self.yaw_deg)

    def local_velocity(self) -> Tuple[float, float, float]:
        """Return velocity vector expressed in `CharacterRoot` Local Space (`+X` Right, `+Y` Forward, `+Z` Up)."""
        return world_to_root_local_vector(self.velocity, self.yaw_deg)

    def local_acceleration(self) -> Tuple[float, float, float]:
        """Return acceleration vector expressed in `CharacterRoot` Local Space."""
        return world_to_root_local_vector(self.acceleration, self.yaw_deg)

    def clone_with(self, **overrides: Any) -> "MotionState":
        return replace(self, **overrides)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": self.frame,
            "time_sec": round(self.time_sec, 5),
            "position": tuple(round(v, 5) for v in self.position),
            "orientation_deg": tuple(round(v, 4) for v in self.orientation_deg),
            "velocity": tuple(round(v, 5) for v in self.velocity),
            "acceleration": tuple(round(v, 5) for v in self.acceleration),
            "speed_mps": round(self.speed_mps, 5),
            "mode": self.mode.value,
            "gait_phase": round(self.gait_phase, 4),
            "is_airborne": self.is_airborne,
            "contacts": {k: v.to_dict() for k, v in self.contacts.items()},
            "params": dict(self.params),
        }


# ============================================================================
# 3. Environment Query, Contact Adapter & Blender Pose Applicator
# ============================================================================

from src.scene.environment_query import (
    EnvironmentQuery,
    DynamicsEnvironmentQuery,
    SurfaceQueryResult,
    SurfaceGeometryType,
)


class ContactConstraintAdapter:
    """Responsibility layer mediating between `MotionState.contacts` and Blender's
    low-level IK / foot-contact constraint system (`src/rig/foot_contact.py`).
    """

    def __init__(self, armature_obj: bpy.types.Object, environment: EnvironmentQuery) -> None:
        self.armature_obj = armature_obj
        self.environment = environment

    def move_root_preserving_locks(self, root_world_xyz: Tuple[float, float, float]) -> None:
        """Move `CharacterRoot` to `root_world_xyz` while keeping locked support feet pinned in World Space."""
        move_character_root_with_support(self.armature_obj, root_world_xyz)

    def lock_foot(
        self,
        side: str,
        contact_world_xyz: Tuple[float, float, float],
        target_rotation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Tuple[Dict[str, Any], ContactPointState]:
        raw = lock_foot_contact(
            self.armature_obj,
            side,
            contact_world_xyz=contact_world_xyz,
            target_rotation_deg=target_rotation_deg,
        )
        return raw, self._raw_to_contact_point(side, "stance", raw)

    def evaluate_locked_foot(self, side: str) -> Tuple[Dict[str, Any], ContactPointState]:
        raw = evaluate_foot_support(self.armature_obj, side)
        return raw, self._raw_to_contact_point(side, "stance", raw)

    def set_swing_foot_target(
        self,
        side: str,
        ankle_world_xyz: Tuple[float, float, float],
        foot_rotation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Tuple[Dict[str, Any], ContactPointState]:
        unlock_foot_contact(self.armature_obj, side, reparent_to_root=False)
        set_foot_ik_target(
            self.armature_obj,
            side,
            ankle_world_xyz,
            foot_rotation_deg=foot_rotation_deg,
        )
        raw = evaluate_foot_support(self.armature_obj, side)
        return raw, self._raw_to_contact_point(side, "swing", raw)

    def _raw_to_contact_point(
        self,
        side: str,
        phase: str,
        raw: Dict[str, Any],
    ) -> ContactPointState:
        contact_vec = raw["contact_world"]
        fh_vec = raw["foot_head_world"]
        cx, cy, cz = float(contact_vec.x), float(contact_vec.y), float(contact_vec.z)
        normal = self.environment.surface_normal_at(cx, cy)
        return ContactPointState(
            limb=f"foot_{side}",
            phase=phase,
            is_locked=bool(raw["is_locked"]),
            contact_world_xyz=(cx, cy, cz),
            current_world_xyz=(float(fh_vec.x), float(fh_vec.y), float(fh_vec.z)),
            target_rotation_deg=tuple(float(v) for v in raw["target_rotation_deg"]),
            drift_m=float(raw["ankle_bone_drift"]),
            hip_to_target_dist=float(raw["hip_to_target_dist"]),
            is_reachable=bool(raw["is_reachable"]),
            strictly_in_reach=bool(raw["strictly_in_reach"]),
            surface_normal=normal,
        )


class BlenderPoseApplicator:
    """Responsibility layer encapsulating Blender pose transforms and keyframing."""

    def __init__(self, armature_obj: bpy.types.Object, root_obj: bpy.types.Object, config: PipelineConfig) -> None:
        self.armature_obj = armature_obj
        self.root_obj = root_obj
        self.config = config

    def apply_upper_body_locomotion_pose(
        self,
        u: float,
        gait_amp: float,
        crouch_env: float,
        trans_drop: float,
        trans_lean_deg: float,
        prep_shift_x: float = 0.0,
    ) -> Tuple[float, float, float, float]:
        return _apply_start_stop_upper_body_pose(
            self.armature_obj,
            self.config,
            u=u,
            gait_amp=gait_amp,
            crouch_env=crouch_env,
            trans_drop=trans_drop,
            trans_lean_deg=trans_lean_deg,
            prep_shift_x=prep_shift_x,
        )

    def keyframe_current_frame(self, frame: int) -> None:
        _keyframe_walk_frame(self.armature_obj, self.root_obj, frame)


_UNSET = object()


# [INTRODUCED 2026-11-27T13:57:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: _round_optional_vec
# PURPOSE: Format optional 3D coordinate/rotation tuples into rounded diagnostic lists without repeating rounding logic across planned and actual upper-limb feedback.
# REASON: Eliminate duplicated optional vector rounding in MotionRuntimeContext.compose_planned_pose() and build_upper_limb_feedback_metadata().
def _round_optional_vec(vec: Optional[Sequence[float]], digits: int) -> Optional[List[float]]:
    """Round each component of an optional vector to the requested precision."""
    if vec is None:
        return None
    return [round(float(v), digits) for v in vec]


# [INTRODUCED 2026-11-27T13:55:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: build_upper_limb_feedback_metadata
# PURPOSE: Extract unified, non-misleading upper-limb feedback distinguishing planned targets, optional historical arm-swing references, and actual WBC/Bridge execution feedback along BridgeExecutionResult -> MotionState -> ActionExecutionResult.
# REASON: Enforce TASK 10-d-5 Section 9 across all five MotionAction classes without duplicating feedback formatting or allowing historical arm_l_rx/arm_r_rx values to masquerade as active independent targets or actual bone poses.
def build_upper_limb_feedback_metadata(
    bridge_res: Any,
    compose_diag: Dict[str, Any],
    hist_arm_l_rx: Optional[float] = None,
    hist_arm_r_rx: Optional[float] = None,
) -> Dict[str, Any]:
    """Assemble planned/historical/actual upper-limb feedback metadata for one executed frame."""
    end_effectors = getattr(getattr(bridge_res, "wbc_result", None), "end_effectors", {}) or {}
    rom_violations = getattr(bridge_res, "rom_violations", {}) or {}
    tracking_errors = getattr(bridge_res, "tracking_errors", {}) or {}

    planned_upper: Dict[str, Any] = {}
    actual_upper: Dict[str, Any] = {}
    for side in ("L", "R"):
        sdiag = compose_diag[side]
        planned_upper[side] = {
            "source": sdiag["source"],
            "is_independent": bool(sdiag["is_independent"]),
            "mode": sdiag["mode"],
            "segment_index": sdiag["segment_index"],
            "time_base": sdiag["time_base"],
            "time_sec": round(float(sdiag["time_sec"]), 6) if sdiag["time_sec"] is not None else None,
            "target": sdiag["planned_target"],
        }

        eff_hand = end_effectors.get(f"hand_{side}")
        side_rom_viols = {
            k: v for k, v in rom_violations.items() if str(k).endswith(f".{side}")
        }
        actual_upper[side] = {
            "enabled": bool(eff_hand and eff_hand.enabled),
            "weight": float(eff_hand.weight) if eff_hand is not None else 0.0,
            "wrist_world_xyz": _round_optional_vec(eff_hand.actual_world_xyz, 5) if eff_hand is not None else None,
            "requested_world_xyz": (
                _round_optional_vec(eff_hand.requested_world_xyz, 5)
                if (eff_hand is not None and eff_hand.enabled)
                else None
            ),
            "hand_rotation_deg": (
                _round_optional_vec(eff_hand.actual_rotation_deg, 4)
                if (eff_hand is not None and eff_hand.actual_rotation_deg is not None)
                else None
            ),
            "position_error_m": (
                round(float(eff_hand.position_error_m), 6)
                if (eff_hand is not None and eff_hand.enabled)
                else None
            ),
            "orientation_error_deg": (
                round(float(eff_hand.orientation_error_deg), 4)
                if (eff_hand is not None and eff_hand.enabled and eff_hand.orientation_error_deg is not None)
                else None
            ),
            "is_reachable": (
                bool(eff_hand.is_reachable)
                if (eff_hand is not None and eff_hand.enabled)
                else None
            ),
            "strictly_in_reach": (
                bool(eff_hand.strictly_in_reach)
                if (eff_hand is not None and eff_hand.enabled)
                else None
            ),
            "tracking_error_m": (
                round(float(tracking_errors[f"hand_{side}"]), 6)
                if f"hand_{side}" in tracking_errors
                else None
            ),
            "rom_violations": side_rom_viols,
        }

    hist_ref = {
        "L": round(float(hist_arm_l_rx), 2) if hist_arm_l_rx is not None else None,
        "R": round(float(hist_arm_r_rx), 2) if hist_arm_r_rx is not None else None,
    }
    return {
        "planned_upper_limb": planned_upper,
        "historical_arm_swing_ref_deg": hist_ref,
        "actual_upper_limb": actual_upper,
        "arm_l_rx_effective": (
            hist_ref["L"] if (hist_ref["L"] is not None and not compose_diag["L"]["is_independent"]) else None
        ),
        "arm_r_rx_effective": (
            hist_ref["R"] if (hist_ref["R"] is not None and not compose_diag["R"]["is_independent"]) else None
        ),
        "upper_limb_source_L": compose_diag["L"]["source"],
        "upper_limb_source_R": compose_diag["R"]["source"],
    }


@dataclass
class MotionRuntimeContext:
    """Execution context supplied by `MotionPlanner` to each `MotionAction`."""

    config: PipelineConfig
    armature_obj: bpy.types.Object
    root_obj: bpy.types.Object
    scene: bpy.types.Scene
    environment: EnvironmentQuery
    contact_adapter: ContactConstraintAdapter
    pose_applicator: BlenderPoseApplicator
    bridge_executor: Optional[Any] = None
    upper_limb_L: Optional[Tuple[UpperLimbSegment, ...]] = None
    upper_limb_R: Optional[Tuple[UpperLimbSegment, ...]] = None
    sequence_start_frame: Optional[int] = None
    sequence_duration_sec: Optional[float] = None

    # [INTRODUCED 2026-11-27T13:55:00+08:00]
    # [UPDATED 2026-11-27T14:26:00+08:00] TASK 10-d-5 (BUG-01; revert unsafe validate_segments bypass)
    # FUNCTION: MotionRuntimeContext.compose_planned_pose
    # PURPOSE: Pure-data combination interface merging a MotionAction's full KinematicPlannedPose with optional central or legal action-local upper-limb tracks while preserving all non-overridden targets and rejecting same-side control conflicts.
    # REASON: Enforce central sequence upper-bound gating and unconditional full sequence validation before target evaluation / Bridge / WBC.
    def compose_planned_pose(
        self,
        planned_pose: Any,
        action_upper_limb_L: Optional[Tuple[UpperLimbSegment, ...]] = None,
        action_upper_limb_R: Optional[Tuple[UpperLimbSegment, ...]] = None,
        action_time_sec: Optional[float] = None,
    ) -> Tuple[Any, Dict[str, Any]]:
        """Compose a KinematicPlannedPose with independent left/right upper-limb targets cleanly."""
        from src.motion.kinematic_bridge import KinematicPlannedPose

        if not isinstance(planned_pose, KinematicPlannedPose):
            raise TypeError(
                f"planned_pose must be KinematicPlannedPose, got {type(planned_pose).__name__}"
            )
        if (
            isinstance(self.config.fps, bool)
            or not isinstance(self.config.fps, (int, float))
            or not math.isfinite(float(self.config.fps))
            or float(self.config.fps) <= 0.0
        ):
            raise ValueError(
                f"MotionRuntimeContext.config.fps must be finite and positive, got {self.config.fps!r}"
            )
        fps = float(self.config.fps)

        uses_central = (self.upper_limb_L is not None) or (self.upper_limb_R is not None)
        sequence_time_sec: Optional[float] = None
        validated_seq_dur: Optional[float] = None
        if uses_central:
            if (
                isinstance(self.sequence_start_frame, bool)
                or not isinstance(self.sequence_start_frame, int)
                or self.sequence_start_frame < 1
            ):
                raise ValueError(
                    "Central upper-limb trajectory requires valid integer sequence_start_frame >= 1 "
                    f"in MotionRuntimeContext, got {self.sequence_start_frame!r}"
                )
            if self.sequence_duration_sec is None:
                raise ValueError(
                    "Central upper-limb trajectory requires explicit finite sequence_duration_sec "
                    "in MotionRuntimeContext"
                )
            if isinstance(self.sequence_duration_sec, bool) or not isinstance(self.sequence_duration_sec, (int, float)):
                raise TypeError(
                    f"sequence_duration_sec must be int or float, got {type(self.sequence_duration_sec).__name__}"
                )
            validated_seq_dur = float(self.sequence_duration_sec)
            if not math.isfinite(validated_seq_dur) or validated_seq_dur < 0.0:
                raise ValueError(
                    f"sequence_duration_sec must be finite and non-negative, got {self.sequence_duration_sec!r}"
                )
            raw_seq_intervals = validated_seq_dur * fps
            if not math.isfinite(raw_seq_intervals) or abs(raw_seq_intervals - round(raw_seq_intervals)) > 1e-6:
                raise ValueError(
                    f"sequence_duration_sec={validated_seq_dur!r} does not align with integer frame "
                    f"boundaries at fps={fps!r}"
                )
            max_seq_frame = self.sequence_start_frame + int(round(raw_seq_intervals))

            if isinstance(planned_pose.frame, bool) or not isinstance(planned_pose.frame, int):
                raise TypeError(f"planned_pose.frame must be int, got {type(planned_pose.frame).__name__}")
            if planned_pose.frame < self.sequence_start_frame:
                raise ValueError(
                    f"planned_pose.frame ({planned_pose.frame}) precedes sequence_start_frame ({self.sequence_start_frame})"
                )
            if planned_pose.frame > max_seq_frame:
                raise ValueError(
                    f"planned_pose.frame ({planned_pose.frame}) exceeds central sequence upper bound "
                    f"{max_seq_frame} (sequence_start_frame={self.sequence_start_frame}, "
                    f"sequence_duration_sec={validated_seq_dur:.6f}s)"
                )
            sequence_time_sec = (planned_pose.frame - self.sequence_start_frame) / fps

        # Disallow simultaneous central + action-local control on the same side
        for side, c_segs, l_segs in (
            ("L", self.upper_limb_L, action_upper_limb_L),
            ("R", self.upper_limb_R, action_upper_limb_R),
        ):
            if c_segs is not None and l_segs is not None:
                raise ValueError(
                    f"Upper-limb control ownership conflict on side '{side}': "
                    f"central MotionPlanner upper_limb_{side} and action-local upper_limb_{side} cannot both be active."
                )

        central_L = validate_upper_limb_segment_sequence(
            self.upper_limb_L, "L", max_time_sec=validated_seq_dur, parameter_name="central_upper_limb_L"
        )
        central_R = validate_upper_limb_segment_sequence(
            self.upper_limb_R, "R", max_time_sec=validated_seq_dur, parameter_name="central_upper_limb_R"
        )
        local_L = validate_upper_limb_segment_sequence(
            action_upper_limb_L, "L", parameter_name="action_upper_limb_L"
        )
        local_R = validate_upper_limb_segment_sequence(
            action_upper_limb_R, "R", parameter_name="action_upper_limb_R"
        )

        uses_local = (local_L is not None) or (local_R is not None)

        validated_action_time_sec: Optional[float] = None
        if uses_local:
            if isinstance(action_time_sec, bool) or not isinstance(action_time_sec, (int, float)):
                raise TypeError(
                    f"action_time_sec must be finite non-negative float when action-local upper limb is used, got {type(action_time_sec).__name__}"
                )
            validated_action_time_sec = float(action_time_sec)
            if not math.isfinite(validated_action_time_sec) or validated_action_time_sec < 0.0:
                raise ValueError(
                    f"action_time_sec must be finite and non-negative, got {action_time_sec!r}"
                )
        elif action_time_sec is not None:
            if isinstance(action_time_sec, bool) or not isinstance(action_time_sec, (int, float)):
                raise TypeError(f"action_time_sec must be int or float, got {type(action_time_sec).__name__}")
            val_t = float(action_time_sec)
            if not math.isfinite(val_t) or val_t < 0.0:
                raise ValueError(f"action_time_sec must be finite and non-negative, got {action_time_sec!r}")
            validated_action_time_sec = val_t

        fk_rotations: Dict[str, Tuple[float, float, float]] = {
            str(k): tuple(float(c) for c in v)
            for k, v in planned_pose.fk_joint_rotations_deg.items()
        }

        composed_hands: Dict[str, Optional[Any]] = {}
        side_diag: Dict[str, Dict[str, Any]] = {}

        for side, c_segs, l_segs, orig_hand in (
            ("L", central_L, local_L, planned_pose.hand_L),
            ("R", central_R, local_R, planned_pose.hand_R),
        ):
            if c_segs is None and l_segs is None:
                cloned_hand = replace(orig_hand) if orig_hand is not None else None
                composed_hands[side] = cloned_hand
                if cloned_hand is not None and cloned_hand.enabled:
                    diag_mode = "IK"
                    planned_target_info: Any = {
                        "mode": "IK",
                        "world_xyz": [round(float(v), 5) for v in cloned_hand.world_xyz],
                        "rotation_deg": _round_optional_vec(cloned_hand.rotation_deg, 4),
                        "pole_hint_world_xyz": _round_optional_vec(cloned_hand.pole_hint_world_xyz, 5),
                        "clamp_reach": bool(cloned_hand.clamp_reach),
                    }
                else:
                    diag_mode = "HISTORICAL_FK"
                    planned_target_info = {
                        "mode": "HISTORICAL_FK",
                        "fk_joint_rotations_deg": {
                            b_key: [round(float(v), 4) for v in fk_rotations[b_key]]
                            for b_key in (f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}")
                            if b_key in fk_rotations
                        },
                    }
                side_diag[side] = {
                    "source": "HISTORICAL_ACTION",
                    "is_independent": False,
                    "mode": diag_mode,
                    "segment_index": None,
                    "time_base": "ACTION",
                    "time_sec": validated_action_time_sec,
                    "planned_target": planned_target_info,
                }
                continue

            if c_segs is not None:
                active_segs = c_segs
                source_label = "CENTRAL"
                time_base = "SEQUENCE"
                assert sequence_time_sec is not None
                eval_time = sequence_time_sec
            else:
                assert l_segs is not None and validated_action_time_sec is not None
                active_segs = l_segs
                source_label = "ACTION_LOCAL"
                time_base = "ACTION"
                eval_time = validated_action_time_sec

            for bone_prefix in ("upper_arm", "forearm", "hand"):
                fk_rotations.pop(f"{bone_prefix}.{side}", None)

            seg_idx, selected_seg, hand_target, side_fk = evaluate_upper_limb_sequence_at_time(
                active_segs,
                side,
                eval_time,
                planned_pose.root_position,
                planned_pose.root_yaw_deg,
            )

            if selected_seg.mode == "FK":
                fk_rotations.update(side_fk)
                composed_hands[side] = None
                planned_target_info = {
                    "mode": "FK",
                    "fk_joint_rotations_deg": {
                        b_key: [round(float(v), 4) for v in fk_rotations[b_key]]
                        for b_key in (f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}")
                        if b_key in fk_rotations
                    },
                }
            else:
                composed_hands[side] = hand_target
                assert hand_target is not None
                planned_target_info = {
                    "mode": "IK",
                    "world_xyz": [round(float(v), 5) for v in hand_target.world_xyz],
                    "rotation_deg": _round_optional_vec(hand_target.rotation_deg, 4),
                    "pole_hint_world_xyz": _round_optional_vec(hand_target.pole_hint_world_xyz, 5),
                    "clamp_reach": bool(hand_target.clamp_reach),
                }

            side_diag[side] = {
                "source": source_label,
                "is_independent": True,
                "mode": selected_seg.mode,
                "segment_index": int(seg_idx),
                "time_base": time_base,
                "time_sec": float(eval_time),
                "planned_target": planned_target_info,
            }

        composed_pose = replace(
            planned_pose,
            hand_L=composed_hands["L"],
            hand_R=composed_hands["R"],
            fk_joint_rotations_deg=fk_rotations,
        )
        diagnostics: Dict[str, Any] = {
            "sequence_start_frame": self.sequence_start_frame,
            "sequence_time_sec": sequence_time_sec,
            "action_time_sec": validated_action_time_sec,
            "L": side_diag["L"],
            "R": side_diag["R"],
        }
        return composed_pose, diagnostics


# ============================================================================
# 4. Extensible MotionAction Interface & Action Execution Result
# ============================================================================

def is_fatal_constraint(constraint: Any) -> bool:
    """Determine whether an unmet constraint represents a fatal execution failure
    rather than a non-fatal diagnostic/telemetry warning.

    Priority rules:
    1. Fatal physical categories (e.g. REACHABILITY, ROM_VIOLATION, etc.) take strict
       precedence over optional warning flags (is_fatal=False / severity='warning').
    2. Explicit fatal escalations (is_fatal=True, severity in ('fatal', 'error', 'critical'))
       are always fatal.
    3. Recognized diagnostic categories (WARNING, TELEMETRY, etc.) and non-fatal severity
       flags (when not attached to a known fatal category) are non-fatal.
    4. Unknown categories and unrecognized objects must NOT be silently considered safe;
       they default to fatal (fail-safe).
    """
    if constraint is None:
        return False

    # Extract category
    category = getattr(constraint, "category", None)
    if category is None and isinstance(constraint, dict):
        category = constraint.get("category")
    cat_upper = str(category).upper() if category is not None else None

    # Extract explicit boolean fatal flag
    is_fatal_flag: Optional[bool] = None
    if hasattr(constraint, "is_fatal"):
        is_fatal_flag = bool(constraint.is_fatal)
    elif isinstance(constraint, dict):
        if "is_fatal" in constraint:
            is_fatal_flag = bool(constraint["is_fatal"])
        elif "fatal" in constraint:
            is_fatal_flag = bool(constraint["fatal"])

    # Extract explicit severity string
    severity = getattr(constraint, "severity", None)
    if severity is None and isinstance(constraint, dict):
        severity = constraint.get("severity")
    sev_lower = str(severity).lower() if severity is not None else None

    # Rule 1: Fatal physical categories take strict precedence over optional warning flags
    KNOWN_FATAL_CATEGORIES = {
        "REACHABILITY",
        "ROM_VIOLATION",
        "ROM_CONFLICT",
        "DISALLOWED_DOF",
        "COLLISION",
        "CONTACT_FAILURE",
        "CONTACT_GEOMETRY",
        "ORIENTATION_ERROR",
        "FATAL",
    }
    if cat_upper in KNOWN_FATAL_CATEGORIES:
        return True

    # Rule 2: Explicit fatal escalations on non-fatal or generic items
    if is_fatal_flag is True:
        return True
    if sev_lower in ("fatal", "error", "critical"):
        return True

    # Rule 3: Recognized non-fatal diagnostic categories
    KNOWN_NON_FATAL_CATEGORIES = {
        "WARNING",
        "WARN",
        "INFO",
        "DIAGNOSTIC",
        "TELEMETRY",
        "NON_FATAL",
    }
    if cat_upper in KNOWN_NON_FATAL_CATEGORIES:
        return False

    # Rule 4: Explicit non-fatal severity/flag when category is absent (pure diagnostic dict)
    if cat_upper is None:
        if is_fatal_flag is False:
            return False
        if sev_lower in ("warning", "warn", "info", "diagnostic", "telemetry"):
            return False

    # Rule 5: Physical / kinematic UnmetConstraint instance
    if hasattr(constraint, "category") and hasattr(constraint, "error_amount"):
        return True

    # Rule 6: Fail-safe: Unknown category or unclassified constraint must NOT be silently safe
    return True


@dataclass
class ActionExecutionResult:
    """Standardized output produced by executing a `MotionAction`."""

    action_name: str
    initial_state: MotionState
    final_state: MotionState
    states: List[MotionState]
    frame_records: List[dict]
    step_schedule: List[dict] = field(default_factory=list)
    unreachable_count: int = 0
    metrics: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    unmet_constraints: List[Any] = field(default_factory=list)
    failure_reason: Optional[str] = None
    failure_frame: Optional[int] = None

    def __post_init__(self) -> None:
        """Enforce contract consistency: do not let default success=True mask explicit failures."""
        if self.unreachable_count > 0 and self.success:
            self.success = False
            if not self.failure_reason:
                self.failure_reason = f"Encountered {self.unreachable_count} unreachable IK target(s)"

        fatal_unmet = [c for c in self.unmet_constraints if is_fatal_constraint(c)]
        if fatal_unmet and self.success:
            self.success = False
            if not self.failure_reason:
                self.failure_reason = f"Encountered {len(fatal_unmet)} fatal unmet constraint(s)"


class MotionAction(ABC):
    """Abstract base interface for composable procedural motion actions.

    Contract:
    - Reads `initial_state` (including start frame, position, orientation, velocity, and contacts).
    - Generates keyframes and per-frame `MotionState` trajectories relative to `initial_state.frame`
      rather than assuming hardcoded frame 1.
    - Returns an `ActionExecutionResult` whose `final_state` can be fed directly into a subsequent
      `MotionAction` by `MotionPlanner`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable action identifier."""

    def can_start_from(self, state: MotionState) -> bool:
        """Return True if this action can validly transition from `state`."""
        _ = state
        return True

    @abstractmethod
    def estimate_duration_frames(
        self,
        initial_state: MotionState,
        config: PipelineConfig,
        environment: Optional[EnvironmentQuery] = None,
    ) -> int:
        """Return the expected number of frames produced by this action."""

    @abstractmethod
    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        """Execute the action from `initial_state` and return `ActionExecutionResult`."""


# ============================================================================
# 5. Task 5C Thin Adapter: StartStopWalkAction
# ============================================================================

def evaluate_root_acceleration_mps2(tau: float, config: PipelineConfig) -> float:
    """Analytical derivative `dv/dt` (`m/s^2`) of `evaluate_root_kinematics` at frame offset `tau`."""
    fps = float(config.fps)
    v_max = float(config.start_stop_target_speed)

    t_s = float(config.start_stop_stand_start_frames)  # 12
    dur_a = float(config.start_stop_accel_frames)      # 54
    dur_w = float(config.start_stop_steady_frames)     # 72
    dur_d = float(config.start_stop_decel_frames)      # 54

    t_a = t_s + dur_a  # 66
    t_w = t_a + dur_w  # 138
    t_d = t_w + dur_d  # 192

    if tau < t_s or (t_a <= tau <= t_w) or tau > t_d:
        return 0.0
    if t_s <= tau <= t_a:
        dt = tau - t_s
        return 0.5 * v_max * (math.pi / (dur_a / fps)) * math.sin(math.pi * dt / dur_a)
    if t_w <= tau <= t_d:
        dt = tau - t_w
        return -0.5 * v_max * (math.pi / (dur_d / fps)) * math.sin(math.pi * dt / dur_d)
    return 0.0


class StartStopWalkAction(MotionAction):
    """Thin `MotionAction` adapter wrapping the validated Task 5C start-accelerate-walk-decelerate-stop
    algorithm (`src/motion/start_stop_walk.py`) without duplicating biomechanics or step math.
    """

    @property
    def name(self) -> str:
        return "start_stop_walk"

    def can_start_from(self, state: MotionState) -> bool:
        return state.mode in (MotionMode.IDLE, MotionMode.STOP, MotionMode.WALK) and not state.is_airborne

    def estimate_duration_frames(
        self,
        initial_state: MotionState,
        config: PipelineConfig,
        environment: Optional[EnvironmentQuery] = None,
    ) -> int:
        _ = (initial_state, environment)
        return config.start_stop_total_frames

    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        if not self.can_start_from(initial_state):
            raise ValueError(
                f"StartStopWalkAction cannot start from mode={initial_state.mode}, "
                f"is_airborne={initial_state.is_airborne}"
            )

        config = context.config
        scene = context.scene

        from src.motion.kinematic_bridge import (
            KinematicBridgeExecutor,
            KinematicPlannedPose,
            PlannedFootTarget,
            PlannedHandTarget,
        )
        bridge_executor = getattr(context, "bridge_executor", None)
        if bridge_executor is None:
            bridge_executor = KinematicBridgeExecutor(
                armature_obj=context.armature_obj,
                root_obj=context.root_obj,
                environment=context.environment,
                default_fps=config.fps,
            )

        start_frame = initial_state.frame
        total_frames = config.start_stop_total_frames
        fps = float(config.fps)

        start_x, start_y, start_z = initial_state.position
        yaw_deg = initial_state.yaw_deg
        fx, fy, _ = forward_unit_vector_from_yaw(yaw_deg)

        schedule = build_step_schedule(config, start_y)
        t_s = config.start_stop_stand_start_frames  # 12
        t_d = (
            config.start_stop_stand_start_frames
            + config.start_stop_accel_frames
            + config.start_stop_steady_frames
            + config.start_stop_decel_frames
        )  # 192
        stop_y = schedule[-1]["swing_y_end"]

        states: List[MotionState] = []
        frame_records: List[dict] = []
        unreachable_events: List[dict] = []

        for tau in range(total_frames):
            frame = start_frame + tau
            scene.frame_set(frame)

            disp_y, speed_mps, stage = evaluate_root_kinematics(tau, config)
            accel_mps2 = evaluate_root_acceleration_mps2(tau, config)
            root_y = start_y + disp_y
            ground_z = context.environment.ground_height_at(start_x, root_y)
            root_world = (start_x, root_y, ground_z)

            u, gait_amp, crouch_env, trans_drop, trans_lean_deg, active_step = (
                _evaluate_gait_phase_and_envelopes(tau, config, schedule)
            )

            prep_shift_x = 0.0
            if 6 <= tau <= 18:
                prep_shift_x = -0.008 * _smooth_bell01((tau - 6) / 12.0)

            # Analytical Upper Body FK Posture
            theta = 2.0 * math.pi * u
            sin_t = math.sin(theta)
            cos_2t = math.cos(2.0 * theta)

            pelvis_dx = -config.walk_pelvis_sway_amp * sin_t * gait_amp + prep_shift_x
            pelvis_dz = (
                config.forward_walk_pelvis_crouch * crouch_env
                - config.walk_pelvis_bob_amp * cos_2t * gait_amp
                + trans_drop
            )
            pelvis_rx = (-1.5 * crouch_env) + (1.0 * cos_2t * gait_amp)
            pelvis_ry = config.walk_pelvis_yaw_deg * sin_t * gait_amp
            pelvis_rz = config.walk_pelvis_roll_deg * sin_t * gait_amp

            spine_rx = (
                -config.walk_torso_lean_deg * gait_amp
                - 0.8 * cos_2t * gait_amp
                - trans_lean_deg
            )
            spine_ry = -config.walk_torso_yaw_deg * sin_t * gait_amp
            spine_rz = -0.6 * pelvis_rz

            total_rx = pelvis_rx + spine_rx
            total_ry = pelvis_ry + spine_ry
            total_rz = pelvis_rz + spine_rz
            neck_rot = (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz)
            head_rot = (-0.45 * total_rx, -0.45 * total_ry, -0.45 * total_rz)

            arm_l_rx = config.walk_arm_swing_deg * sin_t * gait_amp
            arm_r_rx = -config.walk_arm_swing_deg * sin_t * gait_amp
            elbow_l_rx = (
                config.walk_elbow_base_deg * crouch_env
                + config.walk_elbow_swing_deg * max(0.0, sin_t) * gait_amp
            )
            elbow_r_rx = (
                config.walk_elbow_base_deg * crouch_env
                + config.walk_elbow_swing_deg * max(0.0, -sin_t) * gait_amp
            )

            fk_rotations = {
                "upper_arm.L": (arm_l_rx, 0.0, -4.0),
                "forearm.L": (elbow_l_rx, 0.0, 0.0),
                "upper_arm.R": (arm_r_rx, 0.0, 4.0),
                "forearm.R": (elbow_r_rx, 0.0, 0.0),
            }

            # Lower Body Foot Targets
            if tau < t_s:
                z_l = context.environment.ground_height_at(start_x - HIP_X_OFFSET, start_y)
                z_r = context.environment.ground_height_at(start_x + HIP_X_OFFSET, start_y)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(start_x - HIP_X_OFFSET, start_y, z_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw_deg),
                    contact_intent=True,
                )
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(start_x + HIP_X_OFFSET, start_y, z_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw_deg),
                    contact_intent=True,
                )
                phase_l, phase_r = "stance", "stance"
                step_idx = -1

            elif tau >= t_d:
                z_l = context.environment.ground_height_at(start_x - HIP_X_OFFSET, stop_y)
                z_r = context.environment.ground_height_at(start_x + HIP_X_OFFSET, stop_y)
                foot_tgt_l = PlannedFootTarget(
                    world_xyz=(start_x - HIP_X_OFFSET, stop_y, z_l + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw_deg),
                    contact_intent=True,
                )
                foot_tgt_r = PlannedFootTarget(
                    world_xyz=(start_x + HIP_X_OFFSET, stop_y, z_r + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(0.0, 0.0, yaw_deg),
                    contact_intent=True,
                )
                phase_l, phase_r = "stance", "stance"
                step_idx = len(schedule)

            else:
                assert active_step is not None
                step_idx = active_step["k"]
                s = (tau - active_step["tau_start"]) / float(active_step["duration_frames"])
                y_swing, z_lift = compute_forward_swing_point(
                    active_step["swing_y_start"],
                    active_step["swing_y_end"],
                    s,
                    active_step["step_height"],
                )

                pitch_sw = -12.0 * math.sin(math.pi * max(0.0, min(1.0, s)))

                if active_step["stance_side"] == "L":
                    z_st = context.environment.ground_height_at(
                        start_x - HIP_X_OFFSET, active_step["stance_y"]
                    )
                    foot_tgt_l = PlannedFootTarget(
                        world_xyz=(start_x - HIP_X_OFFSET, active_step["stance_y"], z_st + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(0.0, 0.0, yaw_deg),
                        contact_intent=True,
                    )
                    z_sw_ground = context.environment.ground_height_at(start_x + HIP_X_OFFSET, y_swing)
                    foot_tgt_r = PlannedFootTarget(
                        world_xyz=(start_x + HIP_X_OFFSET, y_swing, z_sw_ground + ANKLE_REST_Z + z_lift),
                        is_locked=False,
                        rotation_deg=(pitch_sw, 0.0, yaw_deg),
                        contact_intent=False,
                    )
                    phase_l, phase_r = "stance", "swing"
                else:
                    z_st = context.environment.ground_height_at(
                        start_x + HIP_X_OFFSET, active_step["stance_y"]
                    )
                    foot_tgt_r = PlannedFootTarget(
                        world_xyz=(start_x + HIP_X_OFFSET, active_step["stance_y"], z_st + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(0.0, 0.0, yaw_deg),
                        contact_intent=True,
                    )
                    z_sw_ground = context.environment.ground_height_at(start_x - HIP_X_OFFSET, y_swing)
                    foot_tgt_l = PlannedFootTarget(
                        world_xyz=(start_x - HIP_X_OFFSET, y_swing, z_sw_ground + ANKLE_REST_Z + z_lift),
                        is_locked=False,
                        rotation_deg=(pitch_sw, 0.0, yaw_deg),
                        contact_intent=False,
                    )
                    phase_l, phase_r = "swing", "stance"

            mode = STAGE_TO_MOTION_MODE.get(stage, MotionMode.WALK)
            planned_pose = KinematicPlannedPose(
                frame=frame,
                time_seconds=(frame - 1) / fps,
                root_position=root_world,
                root_yaw_deg=yaw_deg,
                speed_mps=speed_mps,
                accel_mps2=accel_mps2,
                motion_mode=mode,
                dt=1.0 / fps,
                pelvis_location=(pelvis_dx, pelvis_dz, 0.0),
                pelvis_rotation_deg=(pelvis_rx, pelvis_ry, pelvis_rz),
                spine_rotation_deg=(spine_rx, spine_ry, spine_rz),
                neck_rotation_deg=neck_rot,
                head_rotation_deg=head_rot,
                foot_L=foot_tgt_l,
                foot_R=foot_tgt_r,
                hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
                fk_joint_rotations_deg=fk_rotations,
                active_step_index=step_idx,
                gait_phase=u,
                is_flight=False,
            )

            planned_pose, upper_diag = context.compose_planned_pose(planned_pose)
            bridge_res = bridge_executor.execute_frame(planned_pose, keyframe=True, dt=1.0 / fps)

            has_central_upper = upper_diag["L"]["is_independent"] or upper_diag["R"]["is_independent"]
            if has_central_upper:
                if not bridge_res.success:
                    unmet_desc = "; ".join(
                        f"{uc.target_name} ({uc.category}): {uc.description} (err={uc.error_amount:.4f})"
                        for uc in bridge_res.unmet_constraints
                    ) if bridge_res.unmet_constraints else "unspecified constraint failure"
                    raise RuntimeError(
                        f"StartStopWalkAction failed at Frame {frame}: "
                        f"KinematicBridge execution failed (unmet={len(bridge_res.unmet_constraints)}): {unmet_desc}"
                    )
                if bridge_res.motion_state is None:
                    raise RuntimeError(
                        f"StartStopWalkAction failed at Frame {frame}: KinematicBridge returned motion_state=None"
                    )

            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")
            eff_hand_l = bridge_res.wbc_result.end_effectors.get("hand_L")
            eff_hand_r = bridge_res.wbc_result.end_effectors.get("hand_R")

            if eff_l and (not eff_l.is_reachable or not eff_l.strictly_in_reach):
                unreachable_events.append({
                    "frame": frame,
                    "side": "L",
                    "phase": phase_l,
                    "dist": round(eff_l.reach_distance_m, 5),
                })
            if eff_r and (not eff_r.is_reachable or not eff_r.strictly_in_reach):
                unreachable_events.append({
                    "frame": frame,
                    "side": "R",
                    "phase": phase_r,
                    "dist": round(eff_r.reach_distance_m, 5),
                })

            if has_central_upper:
                if eff_hand_l and eff_hand_l.enabled and (not eff_hand_l.is_reachable or not eff_hand_l.strictly_in_reach):
                    unreachable_events.append({
                        "frame": frame,
                        "side": "L",
                        "phase": "hand_ik",
                        "dist": round(eff_hand_l.reach_distance_m, 5),
                    })
                if eff_hand_r and eff_hand_r.enabled and (not eff_hand_r.is_reachable or not eff_hand_r.strictly_in_reach):
                    unreachable_events.append({
                        "frame": frame,
                        "side": "R",
                        "phase": "hand_ik",
                        "dist": round(eff_hand_r.reach_distance_m, 5),
                    })
            elif not bridge_res.success:
                for uc in bridge_res.unmet_constraints:
                    unreachable_events.append({
                        "frame": frame,
                        "category": uc.category,
                        "target": uc.target_name,
                        "error": uc.error_amount,
                        "desc": uc.description,
                    })

            state_l = {
                "target_world": eff_l.requested_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "actual_world": eff_l.actual_world_xyz if eff_l else (0.0, 0.0, 0.0),
                "is_reachable": eff_l.is_reachable if eff_l else True,
                "strictly_in_reach": eff_l.strictly_in_reach if eff_l else True,
                "hip_to_target_dist": eff_l.reach_distance_m if eff_l else 0.0,
                "position_error_m": eff_l.position_error_m if eff_l else 0.0,
            }
            state_r = {
                "target_world": eff_r.requested_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "actual_world": eff_r.actual_world_xyz if eff_r else (0.0, 0.0, 0.0),
                "is_reachable": eff_r.is_reachable if eff_r else True,
                "strictly_in_reach": eff_r.strictly_in_reach if eff_r else True,
                "hip_to_target_dist": eff_r.reach_distance_m if eff_r else 0.0,
                "position_error_m": eff_r.position_error_m if eff_r else 0.0,
            }

            upper_fb = build_upper_limb_feedback_metadata(
                bridge_res, upper_diag, hist_arm_l_rx=arm_l_rx, hist_arm_r_rx=arm_r_rx
            )
            ms = bridge_res.motion_state
            ms_params = dict(ms.params)
            ms_params.update({
                "tau": tau,
                "stage": stage,
                "step_k": step_idx,
                "gait_amp": round(gait_amp, 4),
                "crouch_env": round(crouch_env, 4),
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_lean_deg": round(-(pelvis_rx + spine_rx), 3),
                "arm_l_rx": upper_fb["arm_l_rx_effective"],
                "arm_r_rx": upper_fb["arm_r_rx_effective"],
                "upper_limb_source_L": upper_fb["upper_limb_source_L"],
                "upper_limb_source_R": upper_fb["upper_limb_source_R"],
                "planned_upper_limb": upper_fb["planned_upper_limb"],
                "historical_arm_swing_ref_deg": upper_fb["historical_arm_swing_ref_deg"],
                "actual_upper_limb": upper_fb["actual_upper_limb"],
            })
            ms = ms.clone_with(params=ms_params)
            states.append(ms)

            frame_records.append({
                "frame": frame,
                "tau": tau,
                "stage": stage,
                "mode": mode.value,
                "step_k": step_idx,
                "u": round(u, 4),
                "gait_amp": round(gait_amp, 4),
                "root_y": round(root_y, 5),
                "speed_mps": round(speed_mps, 5),
                "accel_mps2": round(accel_mps2, 5),
                "pelvis_dz": round(pelvis_dz, 5),
                "torso_lean_deg": round(-(pelvis_rx + spine_rx), 3),
                "phase_l": phase_l,
                "phase_r": phase_r,
                "state_l": state_l,
                "state_r": state_r,
                "arm_l_rx": upper_fb["arm_l_rx_effective"],
                "arm_r_rx": upper_fb["arm_r_rx_effective"],
                "upper_limb_source_L": upper_fb["upper_limb_source_L"],
                "upper_limb_source_R": upper_fb["upper_limb_source_R"],
                "planned_upper_limb": upper_fb["planned_upper_limb"],
                "historical_arm_swing_ref_deg": upper_fb["historical_arm_swing_ref_deg"],
                "actual_upper_limb": upper_fb["actual_upper_limb"],
            })

        if unreachable_events:
            raise RuntimeError(
                f"Encountered {len(unreachable_events)} IK reach violations during StartStopWalkAction: "
                f"{unreachable_events[:5]}"
            )

        total_disp = frame_records[-1]["root_y"] - frame_records[0]["root_y"]
        peak_speed = max(r["speed_mps"] for r in frame_records)

        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1],
            states=states,
            frame_records=frame_records,
            step_schedule=schedule,
            unreachable_count=len(unreachable_events),
            metrics={
                "total_frames": total_frames,
                "fps": config.fps,
                "total_root_displacement": round(total_disp, 5),
                "peak_speed_mps": round(peak_speed, 5),
                "unreachable_count": len(unreachable_events),
            },
            success=True,
            unmet_constraints=[],
            failure_reason=None,
            failure_frame=None,
        )


# ============================================================================
# 6. MotionPlanner Orchestrator
# ============================================================================

def create_initial_motion_state(
    config: PipelineConfig,
    start_frame: int = 1,
    position: Optional[Tuple[float, float, float]] = None,
    orientation_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> MotionState:
    """Create the canonical initial stationary `MotionState` at `character_start_location(config)`."""
    pos = position if position is not None else character_start_location(config)
    sx, sy, sz = pos
    yaw_deg = orientation_deg[2]
    contacts = {
        "foot_L": ContactPointState(
            limb="foot_L",
            phase="stance",
            is_locked=True,
            contact_world_xyz=(sx - HIP_X_OFFSET, sy, sz),
            current_world_xyz=(sx - HIP_X_OFFSET, sy, sz),
            target_rotation_deg=(0.0, 0.0, yaw_deg),
        ),
        "foot_R": ContactPointState(
            limb="foot_R",
            phase="stance",
            is_locked=True,
            contact_world_xyz=(sx + HIP_X_OFFSET, sy, sz),
            current_world_xyz=(sx + HIP_X_OFFSET, sy, sz),
            target_rotation_deg=(0.0, 0.0, yaw_deg),
        ),
    }
    return MotionState(
        frame=start_frame,
        time_sec=(start_frame - 1) / float(config.fps),
        position=(float(sx), float(sy), float(sz)),
        orientation_deg=orientation_deg,
        velocity=(0.0, 0.0, 0.0),
        acceleration=(0.0, 0.0, 0.0),
        mode=MotionMode.IDLE,
        gait_phase=0.0,
        contacts=contacts,
        is_airborne=False,
        params={"stage": "stand_start", "step_k": -1},
    )


# [INTRODUCED 2026-11-27T13:55:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: _estimate_action_duration_frames
# PURPOSE: Query an action's declared estimate_duration_frames() cleanly while respecting 2-arg vs 3-arg (environment-aware) signatures and enforcing positive non-bool integer duration output.
# REASON: Enforce static and per-action declared duration contracts in MotionPlanner.execute() across legacy actions (RunAction, SprintStartAction, SprintBrakeAction) and environment-aware actions (StartStopWalkAction, TerrainWalkAction).
def _estimate_action_duration_frames(
    action: MotionAction,
    initial_state: MotionState,
    config: PipelineConfig,
    environment: EnvironmentQuery,
) -> int:
    """Invoke action.estimate_duration_frames safely and validate positive integer output."""
    fn = action.estimate_duration_frames
    supports_env = False
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        supports_env = ("environment" in sig.parameters) or (len(params) >= 3) or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params
        )
    except (ValueError, TypeError):
        supports_env = False
    est = fn(initial_state, config, environment) if supports_env else fn(initial_state, config)
    if isinstance(est, bool) or not isinstance(est, int) or est < 1:
        raise ValueError(
            f"Action '{action.name}'.estimate_duration_frames() returned invalid frame count {est!r}"
        )
    return int(est)


class MotionPlanner:
    """High-level motion sequence orchestrator.

    Responsibilities:
    - Maintains an ordered queue of `MotionAction` instances.
    - Initializes the Blender character rig, IK constraints, `EnvironmentQuery`,
      `ContactConstraintAdapter`, and `BlenderPoseApplicator`.
    - Executes actions sequentially, feeding the `final_state` of action `i` (with
      `frame` advanced if starting a subsequent segment) into action `i + 1`.
    - Aggregates all `MotionState` trajectories, frame records, step schedules, and
      verification metrics without coupling callers to action-internal implementation details.
    """

    def __init__(
        self,
        config: PipelineConfig,
        armature_obj: Optional[bpy.types.Object] = None,
        environment: Optional[EnvironmentQuery] = None,
        upper_limb_L: Optional[Tuple[UpperLimbSegment, ...]] = None,
        upper_limb_R: Optional[Tuple[UpperLimbSegment, ...]] = None,
        sequence_duration_sec: Optional[float] = None,
    ) -> None:
        if (
            isinstance(config.fps, bool)
            or not isinstance(config.fps, (int, float))
            or not math.isfinite(float(config.fps))
            or float(config.fps) <= 0.0
        ):
            raise ValueError(f"PipelineConfig.fps must be finite and positive, got {config.fps!r}")
        fps = float(config.fps)

        self.config = config
        self.armature_obj = armature_obj
        self.environment = environment or EnvironmentQuery(ground_z=0.0)
        self._actions: List[MotionAction] = []
        if sequence_duration_sec is not None:
            if isinstance(sequence_duration_sec, bool) or not isinstance(sequence_duration_sec, (int, float)):
                raise TypeError(
                    f"sequence_duration_sec must be int or float, got {type(sequence_duration_sec).__name__}"
                )
            seq_dur = float(sequence_duration_sec)
            if not math.isfinite(seq_dur) or seq_dur < 0.0:
                raise ValueError(
                    f"sequence_duration_sec must be finite and non-negative, got {sequence_duration_sec!r}"
                )
            raw_seq_intervals = seq_dur * fps
            if not math.isfinite(raw_seq_intervals) or abs(raw_seq_intervals - round(raw_seq_intervals)) > 1e-6:
                raise ValueError(
                    f"sequence_duration_sec={seq_dur!r} does not align with integer frame boundaries at fps={fps!r}"
                )
        else:
            seq_dur = None

        if (upper_limb_L is not None or upper_limb_R is not None) and seq_dur is None:
            raise ValueError(
                "Enabling central upper_limb_L or upper_limb_R requires explicit finite sequence_duration_sec=(total_frames - 1) / fps"
            )

        self.sequence_duration_sec: Optional[float] = seq_dur
        self.upper_limb_L: Optional[Tuple[UpperLimbSegment, ...]] = validate_upper_limb_segment_sequence(
            upper_limb_L, "L", max_time_sec=seq_dur, parameter_name="upper_limb_L"
        )
        self.upper_limb_R: Optional[Tuple[UpperLimbSegment, ...]] = validate_upper_limb_segment_sequence(
            upper_limb_R, "R", max_time_sec=seq_dur, parameter_name="upper_limb_R"
        )

    @property
    def actions(self) -> Sequence[MotionAction]:
        return tuple(self._actions)

    def add_action(self, action: MotionAction, allow_env_override: bool = False) -> "MotionPlanner":
        bind_fn = getattr(action, "bind_environment", None)
        if callable(bind_fn):
            supports_allow_override = False
            try:
                sig = inspect.signature(bind_fn)
                supports_allow_override = "allow_override" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
            except (ValueError, TypeError):
                supports_allow_override = False

            if supports_allow_override:
                bind_fn(self.environment, allow_override=allow_env_override)
            else:
                existing_env = getattr(action, "environment", None)
                if existing_env is not None and existing_env is not self.environment and not allow_env_override:
                    raise ValueError(
                        f"MotionPlanner.add_action({action.name}): environment ownership conflict — "
                        f"action is already bound to {existing_env!r}, which conflicts with planner "
                        f"environment {self.environment!r}."
                    )
                bind_fn(self.environment)
        elif hasattr(action, "environment"):
            existing_env = getattr(action, "environment", None)
            if existing_env is None or allow_env_override:
                action.environment = self.environment
            elif existing_env is not self.environment:
                raise ValueError(
                    f"MotionPlanner.add_action({action.name}): environment ownership conflict — "
                    f"action is already bound to {existing_env!r}, which conflicts with planner "
                    f"environment {self.environment!r}."
                )
        self._actions.append(action)
        return self

    def execute(
        self,
        initial_state: Optional[MotionState] = None,
        upper_limb_L: Any = _UNSET,
        upper_limb_R: Any = _UNSET,
        sequence_duration_sec: Any = _UNSET,
    ) -> Dict[str, Any]:
        if not self._actions:
            raise ValueError("MotionPlanner requires at least one MotionAction before execute()")
        if (
            isinstance(self.config.fps, bool)
            or not isinstance(self.config.fps, (int, float))
            or not math.isfinite(float(self.config.fps))
            or float(self.config.fps) <= 0.0
        ):
            raise ValueError(f"PipelineConfig.fps must be finite and positive, got {self.config.fps!r}")
        fps = float(self.config.fps)

        if initial_state is not None:
            if not isinstance(initial_state, MotionState):
                raise TypeError(f"initial_state must be MotionState, got {type(initial_state).__name__}")
            if (
                isinstance(initial_state.frame, bool)
                or not isinstance(initial_state.frame, int)
                or initial_state.frame < 1
            ):
                raise ValueError(
                    f"initial_state.frame must be a positive integer >= 1, got {initial_state.frame!r}"
                )
        entry_state = initial_state or create_initial_motion_state(self.config, start_frame=1)
        sequence_start_frame = int(entry_state.frame)

        # Static Phase-0 input, time-bound, admission & conflict checks BEFORE any scene writes
        resolved_seq_dur = self.sequence_duration_sec if sequence_duration_sec is _UNSET else sequence_duration_sec
        declared_seq_total_frames: Optional[int] = None
        sequence_max_frame: Optional[int] = None
        if resolved_seq_dur is not None:
            if isinstance(resolved_seq_dur, bool) or not isinstance(resolved_seq_dur, (int, float)):
                raise TypeError(
                    f"sequence_duration_sec must be int or float, got {type(resolved_seq_dur).__name__}"
                )
            resolved_seq_dur = float(resolved_seq_dur)
            if not math.isfinite(resolved_seq_dur) or resolved_seq_dur < 0.0:
                raise ValueError(
                    f"sequence_duration_sec must be finite and non-negative, got {resolved_seq_dur!r}"
                )
            raw_seq_intervals = resolved_seq_dur * fps
            if not math.isfinite(raw_seq_intervals) or abs(raw_seq_intervals - round(raw_seq_intervals)) > 1e-6:
                raise ValueError(
                    f"sequence_duration_sec={resolved_seq_dur!r} does not align with integer frame "
                    f"boundaries at fps={fps!r}"
                )
            declared_seq_intervals = int(round(raw_seq_intervals))
            declared_seq_total_frames = declared_seq_intervals + 1
            sequence_max_frame = sequence_start_frame + declared_seq_intervals

        raw_L = self.upper_limb_L if upper_limb_L is _UNSET else upper_limb_L
        raw_R = self.upper_limb_R if upper_limb_R is _UNSET else upper_limb_R
        has_central_upper = (raw_L is not None) or (raw_R is not None)
        if has_central_upper and resolved_seq_dur is None:
            raise ValueError(
                "MotionPlanner.execute(): enabling central upper_limb_L or upper_limb_R requires "
                "explicit finite sequence_duration_sec=(total_frames - 1) / fps"
            )

        resolved_L = validate_upper_limb_segment_sequence(
            raw_L, "L", max_time_sec=resolved_seq_dur, parameter_name="upper_limb_L"
        )
        resolved_R = validate_upper_limb_segment_sequence(
            raw_R, "R", max_time_sec=resolved_seq_dur, parameter_name="upper_limb_R"
        )

        # BUG-02 exact runtime type admission & ownership conflict check BEFORE scene writes (only when central upper-limb enabled)
        static_action_durations: Dict[int, int] = {}
        central_contract_active = has_central_upper or (resolved_seq_dur is not None)
        terrain_action_cls: Optional[type] = None

        if has_central_upper:
            from src.motion.terrain_walk import TerrainWalkAction
            from src.motion.run_cycle import RunAction
            from src.motion.sprint_start import SprintStartAction
            from src.motion.sprint_brake import SprintBrakeAction

            terrain_action_cls = TerrainWalkAction
            authorized_central_action_types = (
                StartStopWalkAction,
                TerrainWalkAction,
                RunAction,
                SprintStartAction,
                SprintBrakeAction,
            )
            for action in self._actions:
                if type(action) not in authorized_central_action_types:
                    raise TypeError(
                        f"MotionPlanner.execute(): action '{action.name}' of type {type(action).__name__} "
                        f"is not an independently audited action type authorized for centralized upper-limb control."
                    )
                if resolved_L is not None and type(action) is TerrainWalkAction and action.upper_limb_L is not None:
                    raise ValueError(
                        f"MotionPlanner.execute(): upper_limb_L control conflict — central MotionPlanner "
                        f"trajectory conflicts with action '{action.name}'.upper_limb_L"
                    )
                if resolved_R is not None and type(action) is TerrainWalkAction and action.upper_limb_R is not None:
                    raise ValueError(
                        f"MotionPlanner.execute(): upper_limb_R control conflict — central MotionPlanner "
                        f"trajectory conflicts with action '{action.name}'.upper_limb_R"
                    )

        # Static sequence duration contract check ONLY when central sequence contract is active
        # (never alter legacy estimate_duration_frames call counts or contracts when disabled; never forge terrain durations for idx > 0 TerrainWalkAction)
        if central_contract_active:
            assert resolved_seq_dur is not None and declared_seq_total_frames is not None
            if terrain_action_cls is None:
                from src.motion.terrain_walk import TerrainWalkAction as _TWCls
                terrain_action_cls = _TWCls

            static_prefix_frames = 0
            all_durations_statically_known = True
            for idx, action in enumerate(self._actions):
                is_runtime_terrain_dependent = (idx > 0) and (type(action) is terrain_action_cls)
                if is_runtime_terrain_dependent:
                    all_durations_statically_known = False
                    break
                dur_i = _estimate_action_duration_frames(action, entry_state, self.config, self.environment)
                static_action_durations[idx] = dur_i
                static_prefix_frames += dur_i

            if static_prefix_frames > declared_seq_total_frames:
                raise ValueError(
                    f"MotionPlanner.execute(): static action prefix frames ({static_prefix_frames}) already exceed "
                    f"declared sequence frame count {declared_seq_total_frames} "
                    f"(sequence_duration_sec={resolved_seq_dur:.6f}s)"
                )
            if all_durations_statically_known:
                static_max_seq_time_sec = (static_prefix_frames - 1) / fps
                if abs(resolved_seq_dur - static_max_seq_time_sec) > 1e-6:
                    raise ValueError(
                        f"Declared sequence_duration_sec={resolved_seq_dur:.6f}s conflicts with "
                        f"statically determined sequence time bound {static_max_seq_time_sec:.6f}s "
                        f"(total_frames={static_prefix_frames})"
                    )

        arm = _resolve_armature(self.armature_obj)
        root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
        if root_obj is None:
            raise RuntimeError("CharacterRoot object not found")

        scene = bpy.context.scene
        scene.render.fps = self.config.fps

        current_state = entry_state
        start_x, start_y, start_z = current_state.position
        root_obj.location = Vector((start_x, start_y, start_z))
        root_obj.rotation_euler = tuple(math.radians(a) for a in current_state.orientation_deg)

        reset_pose(arm)
        setup_leg_ik(arm)
        reset_leg_ik(arm)
        _clear_existing_animation_data(arm)

        contact_adapter = ContactConstraintAdapter(arm, self.environment)
        pose_applicator = BlenderPoseApplicator(arm, root_obj, self.config)
        from src.motion.kinematic_bridge import KinematicBridgeExecutor
        bridge_executor = KinematicBridgeExecutor(
            armature_obj=arm,
            root_obj=root_obj,
            environment=self.environment,
            default_fps=self.config.fps,
        )
        # [INTRODUCED 2026-11-26T17:52:00+08:00]
        # [UPDATED 2026-11-26T21:39:00+08:00] TASK 10-d-4 / BUG-01
        # BLOCK: MotionPlanner.execute() upper-limb controller animation cleanup
        # PURPOSE: Clear prior animation_data exclusively on the four upper-limb controllers (HandIK.L/R, ElbowPole.L/R) resolved from this Armature's own constraint bindings after authoritative ownership admission and before creating MotionRuntimeContext.
        # REASON: Resolve P03 without stale HandIK/ElbowPole curves, and fix BUG-01 by delegating controller ownership verification to _require_existing_arm_ik_controller_ownership() instead of a redundant object scan and comparing Blender RNA wrappers via != and as_pointer() rather than Python `is`.
        from src.rig.arm_ik import (
            ARM_IK_CONSTRAINT_NAMES,
            ARM_IK_TARGET_NAMES,
            ARM_POLE_TARGET_NAMES,
            HAND_ROT_CONSTRAINT_NAMES,
        )
        from src.scene_transaction_integrity import (
            _require_existing_arm_ik_controller_ownership,
        )

        _require_existing_arm_ik_controller_ownership(
            arm,
            scope="MotionPlanner.execute.upper_limb_animation_cleanup",
        )

        upper_limb_controllers = []
        seen_controller_ptrs = set()
        for side in ("L", "R"):
            p_fore = arm.pose.bones.get(f"forearm.{side}")
            p_hand = arm.pose.bones.get(f"hand.{side}")
            ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side]) if p_fore is not None else None
            rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side]) if p_hand is not None else None
            if ik_con is None or rot_con is None:
                raise RuntimeError(
                    f"MotionPlanner.execute(): missing bound arm constraints for side {side!r} on {arm.name!r}"
                )
            ik_obj = ik_con.target
            pole_obj = ik_con.pole_target
            rot_obj = rot_con.target
            if (
                ik_obj is None
                or ik_obj.type != "EMPTY"
                or ik_obj.name != ARM_IK_TARGET_NAMES[side]
                or rot_obj is None
                or rot_obj != ik_obj
                or int(rot_obj.as_pointer()) != int(ik_obj.as_pointer())
            ):
                raise RuntimeError(
                    f"MotionPlanner.execute(): HandIK binding ownership unverified for side {side!r} on {arm.name!r}"
                )
            if (
                pole_obj is None
                or pole_obj.type != "EMPTY"
                or pole_obj.name != ARM_POLE_TARGET_NAMES[side]
            ):
                raise RuntimeError(
                    f"MotionPlanner.execute(): ElbowPole binding ownership unverified for side {side!r} on {arm.name!r}"
                )
            for ctrl_obj in (ik_obj, pole_obj):
                ctrl_ptr = int(ctrl_obj.as_pointer())
                if ctrl_ptr not in seen_controller_ptrs:
                    seen_controller_ptrs.add(ctrl_ptr)
                    upper_limb_controllers.append(ctrl_obj)

        for ctrl_obj in upper_limb_controllers:
            if ctrl_obj.animation_data is not None:
                ctrl_obj.animation_data_clear()

        context = MotionRuntimeContext(
            config=self.config,
            armature_obj=arm,
            root_obj=root_obj,
            scene=scene,
            environment=self.environment,
            contact_adapter=contact_adapter,
            pose_applicator=pose_applicator,
            bridge_executor=bridge_executor,
            upper_limb_L=resolved_L,
            upper_limb_R=resolved_R,
            sequence_start_frame=sequence_start_frame,
            sequence_duration_sec=resolved_seq_dur,
        )

        all_states: List[MotionState] = []
        all_frame_records: List[dict] = []
        all_step_schedules: List[dict] = []
        action_results: List[ActionExecutionResult] = []
        total_unreachable = 0

        for idx, action in enumerate(self._actions):
            if idx > 0:
                # Subsequent actions begin on the next timeline frame from the previous final state
                next_frame = current_state.frame + 1
                current_state = current_state.clone_with(
                    frame=next_frame,
                    time_sec=(next_frame - 1) / fps,
                )
            declared_action_frames: Optional[int] = None
            if central_contract_active:
                assert sequence_max_frame is not None and resolved_seq_dur is not None
                if idx in static_action_durations:
                    declared_action_frames = static_action_durations[idx]
                else:
                    declared_action_frames = _estimate_action_duration_frames(
                        action, current_state, self.config, self.environment
                    )
                predicted_end_frame = current_state.frame + declared_action_frames - 1
                if predicted_end_frame > sequence_max_frame:
                    raise ValueError(
                        f"MotionPlanner.execute(): action '{action.name}' predicted end frame {predicted_end_frame} "
                        f"(start_frame={current_state.frame}, duration_frames={declared_action_frames}) "
                        f"exceeds central sequence bound {sequence_max_frame} "
                        f"(sequence_start_frame={sequence_start_frame}, sequence_duration_sec={resolved_seq_dur:.6f}s)"
                    )
            result = action.execute(current_state, context)

            # Contract Validation 1: Verify result type
            if not isinstance(result, ActionExecutionResult):
                raise TypeError(
                    f"MotionPlanner execution failed: Action '{action.name}' returned invalid result type "
                    f"{type(result).__name__}, expected ActionExecutionResult."
                )

            # Contract Validation 2: Verify action execution success and absence of fatal constraints
            fatal_unmet = [c for c in result.unmet_constraints if is_fatal_constraint(c)]
            if (not result.success) or fatal_unmet or (result.unreachable_count > 0):
                fail_parts = []
                if result.failure_reason:
                    fail_parts.append(result.failure_reason)
                elif not result.success:
                    fail_parts.append("Action reported execution failure (success=False)")

                if fatal_unmet:
                    unmet_details = "; ".join(
                        f"{getattr(c, 'target_name', 'target')} ({getattr(c, 'category', 'category')}): "
                        f"{getattr(c, 'description', str(c))}"
                        for c in fatal_unmet[:3]
                    )
                    fail_parts.append(f"fatal unmet constraints ({len(fatal_unmet)}): {unmet_details}")

                if result.unreachable_count > 0:
                    fail_parts.append(f"unreachable count={result.unreachable_count}")

                reason_str = " | ".join(fail_parts)
                frame_str = f" at Frame {result.failure_frame}" if result.failure_frame is not None else ""
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' failed{frame_str}: {reason_str}"
                )

            # Contract Validation 3: Verify trajectory is non-empty (motion contract disallows 0-frame actions)
            if not result.states or not result.frame_records:
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' claims success but produced "
                    f"empty trajectory (states={len(result.states)}, frame_records={len(result.frame_records)})."
                )

            # Contract Validation 4: Verify trajectory entry frame continuity
            if result.states[0].frame != current_state.frame:
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' first state frame "
                    f"({result.states[0].frame}) does not match expected entry frame ({current_state.frame})."
                )

            # Contract Validation 5: Verify final_state consistency with last trajectory frame
            last_state = result.states[-1]
            if result.final_state is None:
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' returned final_state=None."
                )
            if result.final_state.frame != last_state.frame:
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' returned final_state.frame "
                    f"({result.final_state.frame}) mismatch with last state frame ({last_state.frame})."
                )
            pos_diff = max(abs(a - b) for a, b in zip(result.final_state.position, last_state.position))
            if pos_diff > 1e-4:
                raise RuntimeError(
                    f"MotionPlanner execution failed: Action '{result.action_name}' returned final_state.position "
                    f"{result.final_state.position} mismatch with last state position {last_state.position} "
                    f"(max_diff={pos_diff:.5f}m > 0.0001m)."
                )

            # Contract Validation 6 (active only under central sequence contract): verify action duration & monotonic frames
            if central_contract_active:
                assert declared_action_frames is not None
                if len(result.states) != declared_action_frames or len(result.frame_records) != declared_action_frames:
                    raise RuntimeError(
                        f"MotionPlanner execution failed: Action '{result.action_name}' produced "
                        f"{len(result.states)} state(s) / {len(result.frame_records)} frame_record(s), "
                        f"expected declared duration {declared_action_frames} frame(s)."
                    )
                for offset, st in enumerate(result.states):
                    expected_frame = current_state.frame + offset
                    if st.frame != expected_frame or st.frame < sequence_start_frame:
                        raise RuntimeError(
                            f"MotionPlanner execution failed: Action '{result.action_name}' produced invalid "
                            f"frame sequence {st.frame} at offset {offset} (expected {expected_frame}, "
                            f"sequence_start_frame={sequence_start_frame})."
                        )

            # Commit action result only after all contract checks pass
            action_results.append(result)
            all_states.extend(result.states)
            all_frame_records.extend(result.frame_records)
            all_step_schedules.extend(result.step_schedule)
            total_unreachable += result.unreachable_count
            current_state = result.final_state

        actual_total_frames = len(all_states)
        actual_end_frame = all_states[-1].frame
        actual_max_seq_time_sec = (actual_end_frame - sequence_start_frame) / fps
        if central_contract_active:
            assert resolved_seq_dur is not None
            if actual_total_frames != (actual_end_frame - sequence_start_frame + 1):
                raise RuntimeError(
                    f"MotionPlanner execution failed: total frames {actual_total_frames} does not match "
                    f"frame span {sequence_start_frame}..{actual_end_frame}"
                )
            if abs(resolved_seq_dur - actual_max_seq_time_sec) > 1e-6:
                raise ValueError(
                    f"Declared sequence_duration_sec={resolved_seq_dur:.6f}s conflicts with "
                    f"realized sequence time bound {actual_max_seq_time_sec:.6f}s "
                    f"(frames={sequence_start_frame}..{actual_end_frame})"
                )
            validate_upper_limb_segment_sequence(
                resolved_L, "L", max_time_sec=actual_max_seq_time_sec, parameter_name="upper_limb_L"
            )
            validate_upper_limb_segment_sequence(
                resolved_R, "R", max_time_sec=actual_max_seq_time_sec, parameter_name="upper_limb_R"
            )

        scene.frame_start = sequence_start_frame
        scene.frame_end = actual_end_frame

        total_disp = all_frame_records[-1]["root_y"] - all_frame_records[0]["root_y"]
        peak_speed = max(r["speed_mps"] for r in all_frame_records)

        print(
            f"[MOTION_PLANNER] Executed {len(action_results)} action(s) "
            f"({[a.name for a in self._actions]}): frames {scene.frame_start}..{scene.frame_end} "
            f"(@ {self.config.fps} FPS), root Y {all_frame_records[0]['root_y']:.4f}m -> "
            f"{all_frame_records[-1]['root_y']:.4f}m (disp={total_disp:.4f}m, "
            f"peak_speed={peak_speed:.4f}m/s, unreachable={total_unreachable})"
        )

        return {
            "success": True,
            "total_frames": len(all_frame_records),
            "fps": self.config.fps,
            "sequence_start_frame": sequence_start_frame,
            "sequence_end_frame": actual_end_frame,
            "sequence_duration_sec": round(actual_max_seq_time_sec, 6),
            "central_upper_limb_enabled": {
                "L": resolved_L is not None,
                "R": resolved_R is not None,
            },
            "total_root_displacement": round(total_disp, 5),
            "peak_speed_mps": round(peak_speed, 5),
            "unreachable_count": total_unreachable,
            "step_schedule": all_step_schedules,
            "frame_records": all_frame_records,
            "initial_state": entry_state,
            "final_state": current_state,
            "states": all_states,
            "action_results": action_results,
            "action_names": [a.name for a in self._actions],
        }


def run_task5c_via_motion_framework(
    config: PipelineConfig,
    armature_obj: Optional[bpy.types.Object] = None,
) -> Dict[str, Any]:
    """Convenience entry point running the Task 5C start-stop walk through `MotionPlanner` + `StartStopWalkAction`."""
    planner = MotionPlanner(config, armature_obj=armature_obj)
    planner.add_action(StartStopWalkAction())
    return planner.execute()
