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

class EnvironmentQuery:
    """Lightweight environment geometry query interface.

    Defaults to a flat ground plane at `Z = 0.0 m` with normal `(0, 0, 1)`.
    Provides an explicit extension seam for future slopes, ledges, walls, and obstacles
    without coupling locomotion actions directly to Blender mesh raycasts.
    """

    def __init__(self, ground_z: float = 0.0) -> None:
        self.ground_z = float(ground_z)

    def ground_height_at(self, x: float, y: float) -> float:
        """Return ground surface Z elevation (m) at World `(x, y)`."""
        _ = (x, y)
        return self.ground_z

    def surface_normal_at(self, x: float, y: float) -> Tuple[float, float, float]:
        """Return unit surface normal vector in World Space at `(x, y)`."""
        _ = (x, y)
        return WORLD_UP_AXIS


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


# ============================================================================
# 4. Extensible MotionAction Interface & Action Execution Result
# ============================================================================

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
    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
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

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        _ = initial_state
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

            bridge_res = bridge_executor.execute_frame(planned_pose, keyframe=True, dt=1.0 / fps)

            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")

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

            if not bridge_res.success:
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
                "arm_l_rx": round(arm_l_rx, 2),
                "arm_r_rx": round(arm_r_rx, 2),
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
                "arm_l_rx": round(arm_l_rx, 2),
                "arm_r_rx": round(arm_r_rx, 2),
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
    ) -> None:
        self.config = config
        self.armature_obj = armature_obj
        self.environment = environment or EnvironmentQuery(ground_z=0.0)
        self._actions: List[MotionAction] = []

    @property
    def actions(self) -> Sequence[MotionAction]:
        return tuple(self._actions)

    def add_action(self, action: MotionAction) -> "MotionPlanner":
        self._actions.append(action)
        return self

    def execute(
        self,
        initial_state: Optional[MotionState] = None,
    ) -> Dict[str, Any]:
        if not self._actions:
            raise ValueError("MotionPlanner requires at least one MotionAction before execute()")

        arm = _resolve_armature(self.armature_obj)
        root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
        if root_obj is None:
            raise RuntimeError("CharacterRoot object not found")

        scene = bpy.context.scene
        scene.render.fps = self.config.fps

        current_state = initial_state or create_initial_motion_state(self.config, start_frame=1)
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
        context = MotionRuntimeContext(
            config=self.config,
            armature_obj=arm,
            root_obj=root_obj,
            scene=scene,
            environment=self.environment,
            contact_adapter=contact_adapter,
            pose_applicator=pose_applicator,
            bridge_executor=bridge_executor,
        )

        all_states: List[MotionState] = []
        all_frame_records: List[dict] = []
        all_step_schedules: List[dict] = []
        action_results: List[ActionExecutionResult] = []
        total_unreachable = 0

        entry_state = current_state
        for idx, action in enumerate(self._actions):
            if idx > 0:
                # Subsequent actions begin on the next timeline frame from the previous final state
                next_frame = current_state.frame + 1
                current_state = current_state.clone_with(
                    frame=next_frame,
                    time_sec=(next_frame - 1) / float(self.config.fps),
                )
            result = action.execute(current_state, context)
            action_results.append(result)
            all_states.extend(result.states)
            all_frame_records.extend(result.frame_records)
            all_step_schedules.extend(result.step_schedule)
            total_unreachable += result.unreachable_count
            current_state = result.final_state

        scene.frame_start = entry_state.frame
        scene.frame_end = all_states[-1].frame

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
            "total_frames": len(all_frame_records),
            "fps": self.config.fps,
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
