"""Procedural Terrain-Aware Locomotion Framework (Task 7A-2).

Enables the existing 19-bone humanoid character (CharacterArmature) to continuously
traverse complex multi-surface 3D terrain in DynamicsPlayground:
- Horizontal flat ground
- 5-step alternating stairs (rise 0.15m, tread 0.30m) and elevated landing platform
- 15-degree uphill sloped ramp, elevated connector bridge, and 20-degree downhill ramp
- Multi-surface continuous transitions with normal-aligned foot orientation

Architectural Compliance:
- Strictly executes via the unified 6-phase pipeline:
  MotionAction -> KinematicPlannedPose -> KinematicBridgeExecutor -> WholeBodyController -> Rig/IK/FK.
- Zero bone keyframe bypass; WholeBodyController retains exclusive write ownership.
- Zero hardcoded environment heights: all terrain elevations and surface normals
  are dynamically queried from `DynamicsEnvironmentQuery` (`src/scene/environment_query.py`).
- 100% pure Python kinematics kernel decoupled from direct bpy dependency where possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

from src.config import PipelineConfig
from src.motion.contact_model import ContactType
from src.motion.framework import (
    ActionExecutionResult,
    ContactConstraintAdapter,
    ContactPointState,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionRuntimeContext,
    MotionState,
    STAGE_TO_MOTION_MODE,
    WORLD_FORWARD_AXIS,
    WORLD_RIGHT_AXIS,
    WORLD_UP_AXIS,
    forward_unit_vector_from_yaw,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor, KinematicPlannedPose, PlannedFootTarget
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, MAX_LEG_REACH, MIN_LEG_REACH
from src.scene.environment_query import DynamicsEnvironmentQuery, SurfaceGeometryType, SurfaceQueryResult


# =============================================================================
# Mathematical Helpers
# =============================================================================

def _smoothstep01(x: float) -> float:
    """C1 cosine smoothstep on [0, 1]."""
    t = max(0.0, min(1.0, x))
    return 0.5 * (1.0 - math.cos(math.pi * t))


def _smooth_bell01(x: float) -> float:
    """C1 bell curve sin^2(pi * x) on [0, 1], peaking at 1.0 when x = 0.5."""
    t = max(0.0, min(1.0, x))
    return math.sin(math.pi * t) ** 2


def pitch_from_surface_normal(normal_world: Tuple[float, float, float]) -> float:
    """Compute anatomical foot pitch angle (deg) parallel to a 3D terrain surface.

    Convention:
    - Outward normal n = (nx, ny, nz)
    - Flat ground (0, 0, 1) -> pitch = 0.0 deg
    - 15 deg uphill (0, -sin(15), cos(15)) -> pitch = +15.0 deg (toes up)
    - 20 deg downhill (0, sin(20), cos(20)) -> pitch = -20.0 deg (toes down)
    """
    nx, ny, nz = normal_world
    n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
    if n_len < 1e-6:
        return 0.0
    ny_n = ny / n_len
    nz_n = nz / n_len
    pitch_rad = math.atan2(-ny_n, nz_n)
    return math.degrees(pitch_rad)


# =============================================================================
# Step Schedule & Specification for Terrain Traversal
# =============================================================================

@dataclass
class TerrainStepPlan:
    """Plan for a single half-step in a terrain-traversal sequence."""
    k: int
    frame_start: int
    frame_end: int
    duration_frames: int
    stance_side: str            # "L" or "R" (the foot bearing weight / locked)
    swing_side: str             # "R" or "L" (the foot in flight)
    stance_xyz: Tuple[float, float, float]
    stance_pitch_deg: float
    stance_surface_id: str
    stance_normal: Tuple[float, float, float]
    swing_start_xyz: Tuple[float, float, float]
    swing_start_pitch_deg: float
    swing_end_xyz: Tuple[float, float, float]
    swing_end_pitch_deg: float
    swing_surface_id: str
    swing_normal: Tuple[float, float, float]
    step_height_clearance: float
    stage_name: str


@dataclass
class TerrainTraversalSpec:
    """High-level trajectory descriptor for a continuous terrain traversal action."""
    course_id: str                          # e.g., "stairs_course", "ramps_course"
    start_pos: Tuple[float, float, float]   # Character start (x, y, z)
    waypoint_y: List[float]                 # Sequential foot landing Y positions
    stand_start_frames: int = 12            # Stationary preparation frames
    step_frames: int = 24                   # Frames per individual step (cadence)
    stand_stop_frames: int = 16             # Final stationary stabilization frames
    base_clearance_stairs: float = 0.16     # Vertical foot lift over stair risers (m)
    base_clearance_ramp: float = 0.12       # Vertical foot lift over slope (m)
    pelvis_drop_stairs: float = 0.12        # Knee bend depth on stairs (m)
    pelvis_drop_slope: float = 0.08         # Knee bend depth on generic slope (m)
    pelvis_drop_uphill: float = 0.04        # Knee bend depth on uphill ascent (m)
    pelvis_drop_downhill: float = 0.085     # Knee bend depth on downhill descent (m)
    pelvis_drop_flat: float = 0.03          # Knee bend depth on flat ground (m)
    torso_lean_uphill_deg: float = 6.0      # Forward lean when climbing (deg)
    torso_lean_downhill_deg: float = -2.5   # Upright/cushion lean when descending (deg)
    arm_swing_deg: float = 16.0             # Upper arm sagittal swing amplitude (deg)


def build_terrain_step_schedule(
    spec: TerrainTraversalSpec,
    environment: EnvironmentQuery,
    start_frame: int = 1,
) -> Tuple[List[TerrainStepPlan], int]:
    """Generate discrete step schedule from terrain traversal specification and environment query.

    Zero hardcoded elevations: every stance and swing target queries `environment.ground_height_at(x, y)`
    and `environment.surface_normal_at(x, y)`.
    """
    corridor_x = spec.start_pos[0]
    left_x = corridor_x - HIP_X_OFFSET
    right_x = corridor_x + HIP_X_OFFSET

    # Start feet positions on ground
    y0 = spec.start_pos[1]
    z0_l = environment.ground_height_at(left_x, y0)
    z0_r = environment.ground_height_at(right_x, y0)
    norm0_l = environment.surface_normal_at(left_x, y0)
    norm0_r = environment.surface_normal_at(right_x, y0)
    pitch0_l = pitch_from_surface_normal(norm0_l)
    pitch0_r = pitch_from_surface_normal(norm0_r)

    # Foot state tracker: current resting world coords
    feet_pos = {
        "L": (left_x, y0, z0_l),
        "R": (right_x, y0, z0_r),
    }
    feet_pitch = {
        "L": pitch0_l,
        "R": pitch0_r,
    }
    feet_normal = {
        "L": norm0_l,
        "R": norm0_r,
    }

    current_frame = start_frame + spec.stand_start_frames
    schedule: List[TerrainStepPlan] = []

    # Alternating steps: first swing is R (stance is L)
    for k, target_y in enumerate(spec.waypoint_y):
        stance_side = "L" if (k % 2 == 0) else "R"
        swing_side = "R" if (k % 2 == 0) else "L"
        sw_x = right_x if swing_side == "R" else left_x

        # Query landing surface
        sw_landing_z = environment.ground_height_at(sw_x, target_y)
        sw_landing_norm = environment.surface_normal_at(sw_x, target_y)
        sw_landing_pitch = pitch_from_surface_normal(sw_landing_norm)
        sw_landing_xyz = (sw_x, target_y, sw_landing_z)

        # Query surface ID
        surf_res = environment.query_surface_at_point((sw_x, target_y, sw_landing_z))
        surf_id = surf_res.surface_id if hasattr(surf_res, "surface_id") else "ground"

        # Stance foot reference
        st_xyz = feet_pos[stance_side]
        st_pitch = feet_pitch[stance_side]
        st_norm = feet_normal[stance_side]
        st_res = environment.query_surface_at_point(st_xyz)
        st_surf_id = st_res.surface_id if hasattr(st_res, "surface_id") else "ground"

        # Swing takeoff reference
        sw_start_xyz = feet_pos[swing_side]
        sw_start_pitch = feet_pitch[swing_side]

        # Determine appropriate clearance height
        is_stairs = "stair" in surf_id.lower() or "stair" in st_surf_id.lower()
        clearance = spec.base_clearance_stairs if is_stairs else spec.base_clearance_ramp

        # Stage naming
        if k == 0:
            stage_name = "start"
        elif k == len(spec.waypoint_y) - 1:
            stage_name = "stop_step"
        else:
            stage_name = "steady_traversal"

        step_dur = spec.step_frames
        plan = TerrainStepPlan(
            k=k,
            frame_start=current_frame,
            frame_end=current_frame + step_dur,
            duration_frames=step_dur,
            stance_side=stance_side,
            swing_side=swing_side,
            stance_xyz=st_xyz,
            stance_pitch_deg=st_pitch,
            stance_surface_id=st_surf_id,
            stance_normal=st_norm,
            swing_start_xyz=sw_start_xyz,
            swing_start_pitch_deg=sw_start_pitch,
            swing_end_xyz=sw_landing_xyz,
            swing_end_pitch_deg=sw_landing_pitch,
            swing_surface_id=surf_id,
            swing_normal=sw_landing_norm,
            step_height_clearance=clearance,
            stage_name=stage_name,
        )
        schedule.append(plan)

        # Update tracker: swinging foot now lands at target
        feet_pos[swing_side] = sw_landing_xyz
        feet_pitch[swing_side] = sw_landing_pitch
        feet_normal[swing_side] = sw_landing_norm
        current_frame += step_dur

    total_frames = (current_frame - start_frame) + spec.stand_stop_frames
    return schedule, total_frames


# =============================================================================
# Terrain Locomotion Action Implementation
# =============================================================================

class TerrainWalkAction(MotionAction):
    """Composable terrain-aware walking action traversing multi-surface 3D environments."""

    def __init__(
        self,
        spec: TerrainTraversalSpec,
        action_name: Optional[str] = None,
    ) -> None:
        self.spec = spec
        self._action_name = action_name or f"TerrainWalk_{spec.course_id}"

    @property
    def name(self) -> str:
        return self._action_name

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        schedule, total_frames = build_terrain_step_schedule(
            self.spec,
            EnvironmentQuery(ground_z=0.0),
            start_frame=initial_state.frame,
        )
        return total_frames

    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        """Execute continuous terrain-aware locomotion sequence using unified 6-phase pipeline."""
        config = context.config
        environment = context.environment
        fps = float(config.fps)

        bridge_executor: Optional[KinematicBridgeExecutor] = context.bridge_executor
        if bridge_executor is None:
            bridge_executor = KinematicBridgeExecutor(
                armature_obj=context.armature_obj,
                root_obj=context.root_obj,
                environment=environment,
                default_fps=fps,
            )

        start_frame = initial_state.frame
        schedule, total_frames = build_terrain_step_schedule(
            self.spec,
            environment,
            start_frame=start_frame,
        )

        first_step_frame = schedule[0].frame_start if schedule else start_frame + self.spec.stand_start_frames
        last_step_frame = schedule[-1].frame_end if schedule else first_step_frame

        # Precompute timeline boundaries
        stand_start_end_frame = first_step_frame
        stand_stop_start_frame = last_step_frame
        final_frame = start_frame + total_frames - 1

        states: List[MotionState] = []
        frame_records: List[dict] = []
        unreachable_events: List[dict] = []

        # Find initial standing posture values
        init_corridor_x = self.spec.start_pos[0]
        init_y = self.spec.start_pos[1]
        init_z_l = environment.ground_height_at(init_corridor_x - HIP_X_OFFSET, init_y)
        init_z_r = environment.ground_height_at(init_corridor_x + HIP_X_OFFSET, init_y)
        init_z = 0.5 * (init_z_l + init_z_r)

        # Track last stance and swing states across frame boundary
        last_known_l_xyz = (init_corridor_x - HIP_X_OFFSET, init_y, init_z_l)
        last_known_r_xyz = (init_corridor_x + HIP_X_OFFSET, init_y, init_z_r)
        last_known_l_pitch = pitch_from_surface_normal(environment.surface_normal_at(init_corridor_x - HIP_X_OFFSET, init_y))
        last_known_r_pitch = pitch_from_surface_normal(environment.surface_normal_at(init_corridor_x + HIP_X_OFFSET, init_y))

        # Main frame generation loop
        for frame in range(start_frame, final_frame + 1):
            time_sec = (frame - 1) / fps
            tau = frame - start_frame

            # -----------------------------------------------------------------
            # 1. Kinematic Stage Classification & Step Plan Lookup
            # -----------------------------------------------------------------
            active_step: Optional[TerrainStepPlan] = None
            if frame < stand_start_end_frame:
                stage = "stand_start"
                mode = MotionMode.IDLE
                step_idx = -1
                step_alpha = 0.0
            elif frame >= stand_stop_start_frame:
                stage = "stand_stop"
                mode = MotionMode.IDLE
                step_idx = len(schedule)
                step_alpha = 1.0
            else:
                for step in schedule:
                    if step.frame_start <= frame < step.frame_end:
                        active_step = step
                        break
                if active_step is not None:
                    step_idx = active_step.k
                    stage = active_step.stage_name
                    mode = MotionMode.WALK if stage == "steady_traversal" else (
                        MotionMode.START if stage == "start" else MotionMode.STOP
                    )
                    step_alpha = (frame - active_step.frame_start) / float(active_step.duration_frames)
                else:
                    stage = "steady_traversal"
                    mode = MotionMode.WALK
                    step_idx = -1
                    step_alpha = 0.0

            # -----------------------------------------------------------------
            # 2. Foot IK Targets and Locking Coordination
            # -----------------------------------------------------------------
            if frame < stand_start_end_frame:
                # Idle start: both feet firmly locked in initial stance
                foot_l_tgt = PlannedFootTarget(
                    world_xyz=(last_known_l_xyz[0], last_known_l_xyz[1], last_known_l_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(last_known_l_pitch, 0.0, 0.0),
                    surface_id=schedule[0].stance_surface_id if schedule else "ground",
                    clamp_ground=False,
                )
                foot_r_tgt = PlannedFootTarget(
                    world_xyz=(last_known_r_xyz[0], last_known_r_xyz[1], last_known_r_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(last_known_r_pitch, 0.0, 0.0),
                    surface_id=schedule[0].stance_surface_id if schedule else "ground",
                    clamp_ground=False,
                )
                root_x = init_corridor_x
                root_y = init_y
                root_z = init_z
                gait_u = 0.0
                gait_amp = 0.0
                phase_l = "stance"
                phase_r = "stance"

            elif frame >= stand_stop_start_frame:
                # Idle stop: both feet firmly locked at final landing points
                final_l_xyz = feet_pos_final["L"] if "feet_pos_final" in locals() else last_known_l_xyz
                final_r_xyz = feet_pos_final["R"] if "feet_pos_final" in locals() else last_known_r_xyz
                final_l_pitch = feet_pitch_final["L"] if "feet_pitch_final" in locals() else last_known_l_pitch
                final_r_pitch = feet_pitch_final["R"] if "feet_pitch_final" in locals() else last_known_r_pitch

                foot_l_tgt = PlannedFootTarget(
                    world_xyz=(final_l_xyz[0], final_l_xyz[1], final_l_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(final_l_pitch, 0.0, 0.0),
                    surface_id="ground",
                    clamp_ground=False,
                )
                foot_r_tgt = PlannedFootTarget(
                    world_xyz=(final_r_xyz[0], final_r_xyz[1], final_r_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(final_r_pitch, 0.0, 0.0),
                    surface_id="ground",
                    clamp_ground=False,
                )
                root_x = init_corridor_x
                root_y = 0.5 * (final_l_xyz[1] + final_r_xyz[1])
                root_z = 0.5 * (final_l_xyz[2] + final_r_xyz[2])
                gait_u = 0.0
                gait_amp = 0.0
                phase_l = "stance"
                phase_r = "stance"

            else:
                assert active_step is not None
                st_side = active_step.stance_side
                sw_side = active_step.swing_side
                s = _smoothstep01(step_alpha)

                # Stance foot: strictly locked in world space
                st_xyz = active_step.stance_xyz
                st_pitch = active_step.stance_pitch_deg
                st_target = PlannedFootTarget(
                    world_xyz=(st_xyz[0], st_xyz[1], st_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(st_pitch, 0.0, 0.0),
                    surface_id=active_step.stance_surface_id,
                    normal_world=active_step.stance_normal,
                    clamp_ground=False,
                )

                # Swing foot: 3D parabolic arc with continuous terrain elevation clearance
                sw_x = active_step.swing_end_xyz[0]
                sw_y = (1.0 - s) * active_step.swing_start_xyz[1] + s * active_step.swing_end_xyz[1]

                # Base interpolated height
                z_base = (1.0 - step_alpha) * active_step.swing_start_xyz[2] + step_alpha * active_step.swing_end_xyz[2]
                # Primary parabolic clearance arc
                h_clear = active_step.step_height_clearance
                arc_z = 4.0 * h_clear * step_alpha * (1.0 - step_alpha)

                # Guaranteed minimum clearance across entire foot rigid bounding footprint
                z_terr_heel = environment.ground_height_at(sw_x, sw_y - 0.07)
                z_terr_ankle = environment.ground_height_at(sw_x, sw_y)
                z_terr_toe = environment.ground_height_at(sw_x, sw_y + 0.15)
                z_terr_foot = max(z_terr_heel, z_terr_ankle, z_terr_toe)
                min_clearance = 0.045 * math.sin(math.pi * step_alpha)
                sw_z_clean = max(z_base + arc_z, z_terr_foot + min_clearance)

                # Natural swing foot ankle pitch coordination:
                # Smoothly blends from takeoff pitch to landing pitch, with physiological mid-swing relaxation
                # (plantarflexion / toe down) aligning with the flexed swinging lower leg to prevent ankle ROM limits.
                # At takeoff from steep uphill inclines, natural toe-off extension caps initial swing pitch to 10.0°.
                sw_pitch_start = min(10.0, active_step.swing_start_pitch_deg)
                sw_pitch_base = (1.0 - step_alpha) * sw_pitch_start + step_alpha * active_step.swing_end_pitch_deg
                is_stair_step = "stair" in str(active_step.stage_name).lower() or "stair" in str(active_step.swing_surface_id).lower()
                if is_stair_step:
                    swing_relax_amp = 19.0
                elif active_step.swing_end_pitch_deg > 5.0 or active_step.swing_start_pitch_deg > 5.0:
                    swing_relax_amp = 22.0
                else:
                    swing_relax_amp = 8.0
                swing_flex_deg = -swing_relax_amp * math.sin(math.pi * step_alpha)
                sw_pitch = sw_pitch_base + swing_flex_deg

                sw_target = PlannedFootTarget(
                    world_xyz=(sw_x, sw_y, sw_z_clean + ANKLE_REST_Z),
                    is_locked=False,
                    rotation_deg=(sw_pitch, 0.0, 0.0),
                    surface_id=active_step.swing_surface_id,
                    normal_world=active_step.swing_normal,
                    clamp_ground=False,
                )

                if st_side == "L":
                    foot_l_tgt = st_target
                    foot_r_tgt = sw_target
                    phase_l = "stance"
                    phase_r = "swing"
                    last_known_l_xyz = st_xyz
                    last_known_l_pitch = st_pitch
                    last_known_r_xyz = (sw_x, sw_y, sw_z_clean)
                    last_known_r_pitch = sw_pitch
                else:
                    foot_l_tgt = sw_target
                    foot_r_tgt = st_target
                    phase_l = "swing"
                    phase_r = "stance"
                    last_known_r_xyz = st_xyz
                    last_known_r_pitch = st_pitch
                    last_known_l_xyz = (sw_x, sw_y, sw_z_clean)
                    last_known_l_pitch = sw_pitch

                # Store for final standing stop reference
                feet_pos_final = {
                    st_side: st_xyz,
                    sw_side: active_step.swing_end_xyz,
                }
                feet_pitch_final = {
                    st_side: st_pitch,
                    sw_side: active_step.swing_end_pitch_deg,
                }

                # Root base position: centered between stance anchor and current swing footprint
                root_x = init_corridor_x
                root_y = 0.5 * (st_xyz[1] + sw_y)
                # Root elevation smoothly transitions from stance height to swing landing height
                root_z = 0.5 * (st_xyz[2] + z_base)

                gait_u = (active_step.k % 2) * 0.5 + 0.5 * step_alpha
                gait_amp = 1.0

            # -----------------------------------------------------------------
            # 3. Dynamic Posture, Knee Flexion & Slope Adaptation
            # -----------------------------------------------------------------
            # Query local slope gradient under current root
            terr_norm = environment.surface_normal_at(root_x, root_y)
            slope_pitch_deg = pitch_from_surface_normal(terr_norm)

            # Pelvis drop depth based on terrain type and slope gradient
            is_stair_zone = "stair" in str(getattr(foot_l_tgt, "surface_id", "")).lower() or "stair" in str(getattr(foot_r_tgt, "surface_id", "")).lower()

            step_pitch = 0.0
            if active_step is not None:
                step_pitch = 0.5 * (active_step.stance_pitch_deg + active_step.swing_end_pitch_deg)
            eff_slope_pitch = slope_pitch_deg if abs(slope_pitch_deg) > 4.0 else step_pitch

            if is_stair_zone:
                target_drop = self.spec.pelvis_drop_stairs
            elif eff_slope_pitch > 4.0:
                target_drop = self.spec.pelvis_drop_uphill
            elif eff_slope_pitch < -4.0:
                target_drop = self.spec.pelvis_drop_downhill
            else:
                target_drop = self.spec.pelvis_drop_flat

            # Vertical oscillation bounce
            bounce = -0.012 * math.cos(4.0 * math.pi * gait_u) if mode != MotionMode.IDLE else 0.0
            pelvis_dz = -(target_drop + bounce)

            # Lateral list and axial pelvis rotation
            pelvis_roll = 2.0 * math.sin(2.0 * math.pi * gait_u) if mode != MotionMode.IDLE else 0.0
            pelvis_yaw = 2.5 * math.sin(2.0 * math.pi * gait_u) if mode != MotionMode.IDLE else 0.0
            pelvis_rot_deg = (pelvis_roll, slope_pitch_deg * 0.4, pelvis_yaw)

            # Torso forward lean based on uphill/downhill gradient
            if slope_pitch_deg > 2.0:
                # Climbing uphill: lean forward to keep CoM centered over support
                forward_lean = self.spec.torso_lean_uphill_deg * (slope_pitch_deg / 15.0)
            elif slope_pitch_deg < -2.0:
                # Descending downhill: keep torso upright / slight cushion lean
                forward_lean = self.spec.torso_lean_downhill_deg * (-slope_pitch_deg / 20.0)
            else:
                forward_lean = 2.0 if is_stair_zone else 1.0

            spine_rot_deg = (forward_lean, -0.5 * pelvis_yaw, -0.5 * pelvis_roll)
            neck_rot_deg = (-0.5 * forward_lean, 0.0, 0.0)
            head_rot_deg = (-0.5 * forward_lean, 0.0, 0.0)

            # Arm swing: natural contralateral arm swinging
            arm_swing_amp = self.spec.arm_swing_deg * gait_amp
            arm_l_rx = -arm_swing_amp * math.sin(2.0 * math.pi * gait_u)
            arm_r_rx = arm_swing_amp * math.sin(2.0 * math.pi * gait_u)

            fk_rotations = {
                "upper_arm.L": (arm_l_rx, 0.0, 0.0),
                "upper_arm.R": (arm_r_rx, 0.0, 0.0),
                "forearm.L": (max(0.0, -0.5 * arm_l_rx + 15.0), 0.0, 0.0),
                "forearm.R": (max(0.0, -0.5 * arm_r_rx + 15.0), 0.0, 0.0),
            }

            # -----------------------------------------------------------------
            # 4. Package Kinematic Planned Pose
            # -----------------------------------------------------------------
            planned_pose = KinematicPlannedPose(
                frame=frame,
                time_seconds=time_sec,
                root_position=(root_x, root_y, root_z),
                root_yaw_deg=0.0,
                speed_mps=0.0,  # Telemetry tracker computes exact derivative
                accel_mps2=0.0,
                motion_mode=mode,
                pelvis_location=(0.0, pelvis_dz, 0.0),
                pelvis_rotation_deg=pelvis_rot_deg,
                spine_rotation_deg=spine_rot_deg,
                neck_rotation_deg=neck_rot_deg,
                head_rotation_deg=head_rot_deg,
                foot_L=foot_l_tgt,
                foot_R=foot_r_tgt,
                fk_joint_rotations_deg=fk_rotations,
                active_step_index=step_idx,
                gait_phase=gait_u,
            )

            # -----------------------------------------------------------------
            # 5. Execute 6-Phase Frame via Bridge & WholeBodyController
            # -----------------------------------------------------------------
            bridge_res = bridge_executor.execute_frame(
                planned=planned_pose,
                keyframe=True,
                enforce_rom_clamping=False,
            )

            # Truthful verification recording
            if not bridge_res.wbc_result.is_all_reachable:
                for uc in bridge_res.unmet_constraints:
                    if uc.category == "REACHABILITY":
                        unreachable_events.append({
                            "frame": frame,
                            "target": uc.target_name,
                            "error": uc.error_amount,
                            "desc": uc.description,
                        })

            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")

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
                "pelvis_dz": round(pelvis_dz, 5),
                "slope_pitch_deg": round(slope_pitch_deg, 2),
                "torso_lean_deg": round(forward_lean, 2),
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
                "root_y": round(root_y, 5),
                "root_z": round(root_z, 5),
                "speed_mps": round(ms.speed_mps, 5),
                "pelvis_dz": round(pelvis_dz, 5),
                "slope_pitch_deg": round(slope_pitch_deg, 2),
                "torso_lean_deg": round(forward_lean, 2),
                "phase_l": phase_l,
                "phase_r": phase_r,
                "state_l": state_l,
                "state_r": state_r,
            })

        if unreachable_events:
            raise RuntimeError(
                f"Encountered {len(unreachable_events)} IK reach violations during {self.name}: "
                f"{unreachable_events[:5]}"
            )

        total_disp_y = frame_records[-1]["root_y"] - frame_records[0]["root_y"]
        total_disp_z = frame_records[-1]["root_z"] - frame_records[0]["root_z"]

        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1],
            states=states,
            frame_records=frame_records,
            step_schedule=[{
                "k": p.k,
                "frame_start": p.frame_start,
                "frame_end": p.frame_end,
                "duration_frames": p.duration_frames,
                "stance_side": p.stance_side,
                "swing_side": p.swing_side,
                "stance_xyz": [round(v, 4) for v in p.stance_xyz],
                "stance_pitch_deg": round(p.stance_pitch_deg, 2),
                "stance_surface_id": p.stance_surface_id,
                "swing_end_xyz": [round(v, 4) for v in p.swing_end_xyz],
                "swing_end_pitch_deg": round(p.swing_end_pitch_deg, 2),
                "swing_surface_id": p.swing_surface_id,
                "stage_name": p.stage_name,
            } for p in schedule],
            unreachable_count=len(unreachable_events),
            metrics={
                "total_frames": total_frames,
                "fps": config.fps,
                "total_disp_y": round(total_disp_y, 5),
                "total_disp_z": round(total_disp_z, 5),
                "unreachable_count": len(unreachable_events),
            },
        )
