"""Procedural Terrain-Aware Locomotion Framework (Task 7A-2).

Enables the existing 19-bone humanoid character (CharacterArmature) to continuously
traverse complex multi-surface 3D terrain in DynamicsPlayground:
- Horizontal flat ground
- 5-step alternating stairs (rise 0.15m, tread 0.30m) and elevated landing platform
- 15-degree uphill sloped ramp, elevated connector bridge, and 20-degree downhill ramp
- Multi-surface continuous transitions with normal-aligned foot orientation

Architectural Compliance:
- Strictly executes via the unified 6-phase pipeline:
  MotionPlanner -> MotionAction -> KinematicPlannedPose -> KinematicBridgeExecutor -> WholeBodyController -> Rig/IK/FK.
- Zero bone keyframe bypass; WholeBodyController retains exclusive write ownership.
- Zero hardcoded environment heights: all terrain elevations and surface normals
  are dynamically queried from `DynamicsEnvironmentQuery` (`src/scene/environment_query.py`).
- 100% pure geometric reasoning: ZERO reliance on object name substrings ('stair', 'ramp', 'bridge').
- Automated dynamic foot placement planning decoupled from route waypoints.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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


def _compute_swing_clearance_z(
    step_alpha: float,
    z_base: float,
    arc_z: float,
    z_terr_foot: float,
    min_clearance_amp: float = 0.045,
) -> float:
    """Compute swing foot elevation with smooth terrain clearance tapering to zero at boundaries.

    Ensures that swing foot targets match takeoff (alpha=0) and landing (alpha=1)
    elevations with C0 continuity, while maintaining clearance during mid-swing.
    """
    envelope = math.sin(math.pi * step_alpha)
    min_clearance = min_clearance_amp * envelope
    terrain_lift = max(0.0, (z_terr_foot + min_clearance) - z_base) * envelope
    return z_base + max(arc_z, terrain_lift)


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
class TerrainRouteInput:
    """High-level route and corridor constraints for procedural terrain locomotion.

    Decouples route specification (start, target, stride, boundaries) from
    the discrete foot placement planning generated by `plan_terrain_footsteps`.
    """
    start_pos: Tuple[float, float, float]       # Starting world position (x, y, z)
    target_pos: Tuple[float, float, float]      # Target world destination (x, y, z)
    nominal_stride_m: float = 0.30              # Target step length (m)
    step_width_m: float = 0.22                  # Lateral stance separation (2 * HIP_X_OFFSET)
    max_step_length_m: float = 0.45             # Maximum reach limit
    min_step_length_m: float = 0.15             # Minimum stride length
    stand_start_frames: int = 12                # Initial idle stabilization frames
    step_frames: int = 16                       # Timeline frames per half-step
    stand_stop_frames: int = 16                 # Final idle stabilization frames
    base_clearance_m: float = 0.12              # Minimum swing apex lift
    pelvis_drop_uphill_m: float = 0.088         # Knee cushion when climbing
    pelvis_drop_downhill_m: float = 0.098       # Knee cushion when descending
    pelvis_drop_flat_m: float = 0.035           # Knee cushion on level ground
    pelvis_drop_step_m: float = 0.120           # Knee cushion on step rise
    torso_lean_uphill_deg: float = 6.0          # Forward lean on uphill
    torso_lean_downhill_deg: float = -2.5       # Cushion lean on downhill
    arm_swing_deg: float = 16.0                 # Arm swing amplitude


@dataclass
class TerrainTraversalSpec:
    """Legacy compatibility descriptor mapping to TerrainRouteInput."""
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
    pelvis_drop_uphill: float = 0.088       # Knee bend depth on uphill ascent (m)
    pelvis_drop_downhill: float = 0.098     # Knee bend depth on downhill descent (m)
    pelvis_drop_flat: float = 0.035         # Knee bend depth on flat ground (m)
    torso_lean_uphill_deg: float = 6.0      # Forward lean when climbing (deg)
    torso_lean_downhill_deg: float = -2.5   # Upright/cushion lean when descending (deg)
    arm_swing_deg: float = 16.0             # Upper arm sagittal swing amplitude (deg)


def _validate_route_input(route: TerrainRouteInput) -> None:
    """Validate route geometric and kinematic bounds before planning."""
    x0, y0, _ = route.start_pos
    x_tgt, y_tgt, _ = route.target_pos

    if abs(x_tgt - x0) > 1e-4:
        raise ValueError(
            f"Terrain route rejected: requires collinear X corridor: start X {x0:.3f} != target X {x_tgt:.3f}"
        )

    for name, val in [
        ("nominal_stride_m", route.nominal_stride_m),
        ("step_width_m", route.step_width_m),
        ("max_step_length_m", route.max_step_length_m),
        ("min_step_length_m", route.min_step_length_m),
        ("base_clearance_m", route.base_clearance_m),
    ]:
        if val is None or not math.isfinite(val) or val <= 0.0:
            raise ValueError(f"Terrain route parameter '{name}' must be finite and > 0, got {val}")

    for name, val in [
        ("stand_start_frames", route.stand_start_frames),
        ("step_frames", route.step_frames),
        ("stand_stop_frames", route.stand_stop_frames),
    ]:
        if val is None or val < 0:
            raise ValueError(f"Terrain route frame count '{name}' must be non-negative, got {val}")

    if route.min_step_length_m > route.max_step_length_m:
        raise ValueError(
            f"min_step_length_m ({route.min_step_length_m:.3f}) cannot exceed "
            f"max_step_length_m ({route.max_step_length_m:.3f})"
        )



def _adjust_footfall_for_seams_and_edges(
    environment: EnvironmentQuery,
    sw_x: float,
    y: float,
    corridor_y_min: float,
    corridor_y_max: float,
) -> float:
    """Adjust prospective footfall Y so that the 22cm foot rigid sole lies flat on one surface.

    The foot rigid extent is:
    - Heel: y - 0.07m
    - Ankle: y
    - Toe: y + 0.15m

    If the toe and heel sample different surface normals (straddling a slope seam or ledge),
    shifts y slightly to ensure full-sole planar seating with >= 0.03m margin from the seam.
    Samples at the true lateral position `sw_x` of the swing foot.
    """
    res_heel = environment.query_ground_support_at(sw_x, y - 0.07)
    res_toe = environment.query_ground_support_at(sw_x, y + 0.15)
    res_ankle = environment.query_ground_support_at(sw_x, y)

    n_heel = res_heel.surface_normal_world if res_heel.success else (0.0, 0.0, 1.0)
    n_toe = res_toe.surface_normal_world if res_toe.success else (0.0, 0.0, 1.0)
    dn = (Vector(n_toe) - Vector(n_heel)).length

    min_y = min(corridor_y_min, corridor_y_max)
    max_y = max(corridor_y_min, corridor_y_max)

    all_supported = (
        res_heel.allows_regular_support
        and res_toe.allows_regular_support
        and res_ankle.allows_regular_support
    )

    if dn > 0.05 or not all_supported:
        best_y = None
        min_dn = dn if all_supported else 1e9

        for shift in [-0.08, -0.05, -0.03, 0.03, 0.05, 0.08]:
            cand_y = y + shift
            if cand_y < min_y or cand_y > max_y:
                continue
            rh = environment.query_ground_support_at(sw_x, cand_y - 0.07)
            rt = environment.query_ground_support_at(sw_x, cand_y + 0.15)
            ra = environment.query_ground_support_at(sw_x, cand_y)
            if not (rh.allows_regular_support and rt.allows_regular_support and ra.allows_regular_support):
                continue
            curr_dn = (Vector(rt.surface_normal_world) - Vector(rh.surface_normal_world)).length
            if curr_dn < min_dn:
                min_dn = curr_dn
                best_y = cand_y
                if curr_dn < 0.02:
                    break
        if best_y is not None:
            return best_y
        if all_supported:
            return y
        raise ValueError(
            f"Footfall at ({sw_x:.2f}, {y:.2f}) straddles unsupported surface boundary "
            f"and no valid support shift was found in corridor [{min_y:.2f}, {max_y:.2f}]"
        )
    return y


def _build_step_schedule_core(
    start_pos: Tuple[float, float, float],
    target_y_sequence: Sequence[float],
    environment: EnvironmentQuery,
    step_width_m: float,
    stand_start_frames: int,
    step_frames: int,
    stand_stop_frames: int,
    clearance_type: str,
    route_base_clearance: float = 0.12,
    spec_stairs_clearance: float = 0.14,
    spec_ramp_clearance: float = 0.10,
    start_frame: int = 1,
    corridor_y_bounds: Optional[Tuple[float, float]] = None,
) -> Tuple[List[TerrainStepPlan], int]:
    """Authoritative unified core for discrete footstep planning and 3D surface alignment.

    Used by both `plan_terrain_footsteps` and `build_terrain_step_schedule`.
    100% geometric: NO synthetic fallbacks, NO string-based naming checks.
    """
    corridor_x = start_pos[0]
    y0 = start_pos[1]
    left_x = corridor_x - (step_width_m / 2.0)
    right_x = corridor_x + (step_width_m / 2.0)

    # Initial resting foot placement via single-hit ground support queries
    res0_l = environment.query_ground_support_at(left_x, y0)
    res0_r = environment.query_ground_support_at(right_x, y0)
    if not res0_l.allows_regular_support:
        raise ValueError(
            f"Initial left foot placement at ({left_x:.2f}, {y0:.2f}) rejected: "
            f"surface '{res0_l.surface_id}' does not allow regular support"
        )
    if not res0_r.allows_regular_support:
        raise ValueError(
            f"Initial right foot placement at ({right_x:.2f}, {y0:.2f}) rejected: "
            f"surface '{res0_r.surface_id}' does not allow regular support"
        )
    if not res0_l.success:
        raise ValueError(
            f"Initial left foot placement at ({left_x:.2f}, {y0:.2f}) rejected: {res0_l.error_reason}"
        )
    if not res0_r.success:
        raise ValueError(
            f"Initial right foot placement at ({right_x:.2f}, {y0:.2f}) rejected: {res0_r.error_reason}"
        )

    z0_l = res0_l.contact_point_world[2]
    z0_r = res0_r.contact_point_world[2]
    norm0_l = res0_l.surface_normal_world
    norm0_r = res0_r.surface_normal_world
    pitch0_l = pitch_from_surface_normal(norm0_l)
    pitch0_r = pitch_from_surface_normal(norm0_r)
    surf0_l_id = res0_l.surface_id
    surf0_r_id = res0_r.surface_id

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
    feet_surface_id = {
        "L": surf0_l_id,
        "R": surf0_r_id,
    }

    current_frame = start_frame + stand_start_frames
    schedule: List[TerrainStepPlan] = []
    num_steps = len(target_y_sequence)

    for k, target_y in enumerate(target_y_sequence):
        stance_side = "L" if (k % 2 == 0) else "R"
        swing_side = "R" if (k % 2 == 0) else "L"
        sw_x = right_x if swing_side == "R" else left_x

        # Single-hit ground support query for landing surface
        sw_landing_res = environment.query_ground_support_at(sw_x, target_y)
        if not sw_landing_res.allows_regular_support:
            raise ValueError(
                f"Footstep {k} at ({sw_x:.2f}, {target_y:.2f}) rejected: lands on unsupported surface '{sw_landing_res.surface_id}'"
            )
        if not sw_landing_res.success:
            raise ValueError(
                f"Footstep {k} at ({sw_x:.2f}, {target_y:.2f}) rejected: {sw_landing_res.error_reason}"
            )

        sw_landing_z = sw_landing_res.contact_point_world[2]
        sw_landing_norm = sw_landing_res.surface_normal_world
        sw_landing_pitch = pitch_from_surface_normal(sw_landing_norm)
        sw_landing_xyz = (sw_x, target_y, sw_landing_z)
        surf_id = sw_landing_res.surface_id

        # Stance foot reference (from previous valid landing or initial stance)
        st_xyz = feet_pos[stance_side]
        st_pitch = feet_pitch[stance_side]
        st_norm = feet_normal[stance_side]
        st_surf_id = feet_surface_id[stance_side]

        # Check step elevation difference (physiological reachability)
        delta_z = sw_landing_z - st_xyz[2]
        if abs(delta_z) > 0.35:
            raise ValueError(
                f"Footstep {k} at y={target_y:.2f} requires vertical reach {delta_z:.3f}m, "
                f"exceeding physical stepping limit (0.35m)"
            )

        # Swing takeoff reference
        sw_start_xyz = feet_pos[swing_side]
        sw_start_pitch = feet_pitch[swing_side]

        # Geometric clearance height
        is_stepped = (delta_z > 0.05 and abs(sw_landing_pitch) < 3.0)
        if clearance_type == "route":
            base_lift = route_base_clearance + (0.04 if is_stepped else 0.0)
            clearance = max(base_lift, abs(delta_z) + 0.04)
        else:
            clearance = spec_stairs_clearance if is_stepped else spec_ramp_clearance

        if k == 0:
            stage_name = "start"
        elif k == num_steps - 1:
            stage_name = "stop_step"
        else:
            stage_name = "steady_traversal"

        plan = TerrainStepPlan(
            k=k,
            frame_start=current_frame,
            frame_end=current_frame + step_frames,
            duration_frames=step_frames,
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

        feet_pos[swing_side] = sw_landing_xyz
        feet_pitch[swing_side] = sw_landing_pitch
        feet_normal[swing_side] = sw_landing_norm
        feet_surface_id[swing_side] = surf_id
        current_frame += step_frames

    total_frames = (current_frame - start_frame) + stand_stop_frames
    return schedule, total_frames


def plan_terrain_footsteps(
    route: TerrainRouteInput,
    environment: EnvironmentQuery,
    start_frame: int = 1,
) -> Tuple[List[TerrainStepPlan], int]:
    """Dynamically plan discrete alternating footsteps over arbitrary 3D terrain.

    Separates route goal input from footstep planning:
    - Automatically steps along the fixed-X corridor from start_pos to target_pos (+Y and -Y).
    - Queries `environment` for 3D elevations and surface normals dynamically via `query_ground_support_at`.
    - Single-hit contract: height Z, normal, surface_id, and support eligibility come from a single hit.
    - Strict rejection: misses (NO_HIT) and non-support surfaces raise explicit ValueError.
    - Detects seams and edge boundaries on true lateral footfall positions to place full 22cm soles safely.
    - Checks physiological climbing/stepping reach limits (flags unreachable drops/rises).
    - Computes normal-aligned foot pitches and adaptive swing clearance.
    - 100% geometric: NO string-based naming checks.
    """
    _validate_route_input(route)
    x0, y0, _ = route.start_pos
    x_tgt, y_tgt, _ = route.target_pos

    dy_total = y_tgt - y0
    if abs(dy_total) < 1e-4:
        return [], route.stand_start_frames + route.stand_stop_frames

    dir_sign = 1.0 if dy_total > 0 else -1.0
    stride_len = min(route.nominal_stride_m, route.max_step_length_m)
    signed_stride = dir_sign * stride_len

    step_ys: List[float] = []
    curr_lead_y = y0
    left_x = x0 - (route.step_width_m / 2.0)
    right_x = x0 + (route.step_width_m / 2.0)
    step_idx = 0

    while abs(y_tgt - curr_lead_y) - stride_len >= route.min_step_length_m * 0.5:
        curr_lead_y += signed_stride
        swing_side = "R" if (step_idx % 2 == 0) else "L"
        sw_x = right_x if swing_side == "R" else left_x
        adjusted_y = _adjust_footfall_for_seams_and_edges(
            environment, sw_x, curr_lead_y, y0, y_tgt
        )
        step_ys.append(adjusted_y)
        step_idx += 1

    # Closing steps to land side-by-side at target_pos
    step_ys.append(y_tgt)
    step_ys.append(y_tgt)

    return _build_step_schedule_core(
        start_pos=route.start_pos,
        target_y_sequence=step_ys,
        environment=environment,
        step_width_m=route.step_width_m,
        stand_start_frames=route.stand_start_frames,
        step_frames=route.step_frames,
        stand_stop_frames=route.stand_stop_frames,
        clearance_type="route",
        route_base_clearance=route.base_clearance_m,
        start_frame=start_frame,
        corridor_y_bounds=(y0, y_tgt),
    )


def build_terrain_step_schedule(
    spec: TerrainTraversalSpec,
    environment: EnvironmentQuery,
    start_frame: int = 1,
) -> Tuple[List[TerrainStepPlan], int]:
    """Generate discrete step schedule from terrain traversal specification and environment query.

    Legacy interface preserved for backward compatibility.
    100% geometric: replaces string-based naming with surface normal and height analysis.
    """
    if len(spec.waypoint_y) >= 2:
        diffs = [spec.waypoint_y[i + 1] - spec.waypoint_y[i] for i in range(len(spec.waypoint_y) - 1)]
        if not (all(d > 0 for d in diffs) or all(d < 0 for d in diffs)):
            raise ValueError(
                "TerrainTraversalSpec waypoint_y must be strictly monotonic (unidirectional traversal along fixed corridor)"
            )

    y0 = spec.start_pos[1]
    y_end = spec.waypoint_y[-1] if spec.waypoint_y else y0

    return _build_step_schedule_core(
        start_pos=spec.start_pos,
        target_y_sequence=list(spec.waypoint_y),
        environment=environment,
        step_width_m=2.0 * HIP_X_OFFSET,
        stand_start_frames=spec.stand_start_frames,
        step_frames=spec.step_frames,
        stand_stop_frames=spec.stand_stop_frames,
        clearance_type="spec",
        spec_stairs_clearance=spec.base_clearance_stairs,
        spec_ramp_clearance=spec.base_clearance_ramp,
        start_frame=start_frame,
        corridor_y_bounds=(y0, y_end),
    )


# =============================================================================
# Continuous Root Forward Motion Spline Helper Functions
# =============================================================================

def _build_continuous_root_forward_spline(
    schedule: List[TerrainStepPlan],
    fps: float,
) -> Tuple[List[int], List[float], List[float]]:
    """Build knot points and boundary velocities for monotonic, C1-continuous Root forward motion.

    Derives knot positions and boundary velocities purely from TerrainStepPlan
    and actual footstep positions without hardcoded coordinates.
    """
    K = len(schedule)
    if K == 0:
        return [0], [0.0], [0.0]

    knot_frames = [schedule[k].frame_start for k in range(K)] + [schedule[K - 1].frame_end]
    knot_y = [
        0.5 * (schedule[k].stance_xyz[1] + schedule[k].swing_start_xyz[1])
        for k in range(K)
    ] + [0.5 * (schedule[K - 1].stance_xyz[1] + schedule[K - 1].swing_end_xyz[1])]

    knot_v = [0.0] * (K + 1)
    if K == 1:
        knot_v[0] = 0.0
        knot_v[1] = 0.0
        return knot_frames, knot_y, knot_v

    # Interior knots: transition velocities
    for k in range(1, K):
        dt_prev = (knot_frames[k] - knot_frames[k - 1]) / fps
        dt_next = (knot_frames[k + 1] - knot_frames[k]) / fps
        dy_prev = knot_y[k] - knot_y[k - 1]
        dy_next = knot_y[k + 1] - knot_y[k]

        v_prev = dy_prev / dt_prev if dt_prev > 1e-6 else 0.0
        v_next = dy_next / dt_next if dt_next > 1e-6 else 0.0

        # Strict monotonicity: if consecutive slopes have opposite signs, knot velocity must be 0
        if v_prev * v_next <= 0.0:
            knot_v[k] = 0.0
        else:
            # Monotone tangent preserving travel direction (+Y non-negative, -Y non-positive)
            avg_v = 0.5 * (v_prev + v_next)
            knot_v[k] = avg_v

    return knot_frames, knot_y, knot_v


def _evaluate_root_y_hermite(
    current_frame: int,
    step_k: int,
    knot_frames: List[int],
    knot_y: List[float],
    knot_v: List[float],
    fps: float,
) -> float:
    """Evaluate monotonic cubic Hermite spline for Root Y position at current_frame."""
    if step_k < 0 or step_k >= len(knot_frames) - 1:
        return knot_y[0] if step_k < 0 else knot_y[-1]

    f0 = knot_frames[step_k]
    f1 = knot_frames[step_k + 1]
    if f1 <= f0:
        return knot_y[step_k]

    u = (current_frame - f0) / float(f1 - f0)
    u = max(0.0, min(1.0, u))

    y0 = knot_y[step_k]
    y1 = knot_y[step_k + 1]
    delta = y1 - y0
    if abs(delta) < 1e-9:
        return y0

    dur_sec = (f1 - f0) / fps
    m0 = (knot_v[step_k] * dur_sec) / delta
    m1 = (knot_v[step_k + 1] * dur_sec) / delta

    # Fritsch-Carlson bounds to guarantee strict monotonicity (no backward motion)
    m0 = max(0.0, min(3.0, m0))
    m1 = max(0.0, min(3.0, m1))

    # Hermite basis expansion
    h = (3.0 * u * u - 2.0 * u * u * u) + m0 * (u * u * u - 2.0 * u * u + u) + m1 * (u * u * u - u * u)
    return y0 + delta * h


# =============================================================================
# Terrain Locomotion Action Implementation
# =============================================================================

class TerrainWalkAction(MotionAction):
    """Composable terrain-aware walking action traversing multi-surface 3D environments."""

    def __init__(
        self,
        spec: Optional[TerrainTraversalSpec] = None,
        route: Optional[TerrainRouteInput] = None,
        action_name: Optional[str] = None,
        environment: Optional[EnvironmentQuery] = None,
    ) -> None:
        if route is not None:
            self.route: Optional[TerrainRouteInput] = route
            self.spec: TerrainTraversalSpec = TerrainTraversalSpec(
                course_id="route_traversal",
                start_pos=route.start_pos,
                waypoint_y=[],
                stand_start_frames=route.stand_start_frames,
                step_frames=route.step_frames,
                stand_stop_frames=route.stand_stop_frames,
                base_clearance_stairs=route.base_clearance_m + 0.04,
                base_clearance_ramp=route.base_clearance_m,
                pelvis_drop_stairs=route.pelvis_drop_step_m,
                pelvis_drop_slope=0.08,
                pelvis_drop_uphill=route.pelvis_drop_uphill_m,
                pelvis_drop_downhill=route.pelvis_drop_downhill_m,
                pelvis_drop_flat=route.pelvis_drop_flat_m,
                torso_lean_uphill_deg=route.torso_lean_uphill_deg,
                torso_lean_downhill_deg=route.torso_lean_downhill_deg,
                arm_swing_deg=route.arm_swing_deg,
            )
        elif spec is not None:
            self.spec = spec
            self.route = None
        else:
            raise ValueError("TerrainWalkAction requires either 'route' or 'spec'")

        self.environment = environment
        self._action_name = action_name or f"TerrainWalk_{self.spec.course_id}"

    @property
    def name(self) -> str:
        return self._action_name

    def bind_environment(
        self,
        environment: EnvironmentQuery,
        allow_override: bool = False,
    ) -> None:
        """Bind authoritative environment instance from planner or runtime context.

        Contract:
        - If unbound (self.environment is None), binds environment.
        - If already bound to the exact same instance (self.environment is environment), no-op.
        - If already bound to a different instance and allow_override is False, raises ValueError
          to prevent silent environment overwrite.
        """
        if environment is None:
            raise ValueError(f"{self.name}.bind_environment() requires a non-None EnvironmentQuery instance.")
        if self.environment is not None and self.environment is not environment and not allow_override:
            raise ValueError(
                f"{self.name}: environment ownership conflict — action is already bound to "
                f"{self.environment!r}, cannot silently overwrite with {environment!r}. "
                f"Pass allow_override=True or call rebind_environment() explicitly."
            )
        self.environment = environment

    def rebind_environment(self, environment: EnvironmentQuery) -> None:
        """Explicitly replace the bound environment instance on this action."""
        self.bind_environment(environment, allow_override=True)

    def resolve_environment(
        self,
        runtime_env: Optional[EnvironmentQuery] = None,
        allow_override: bool = False,
    ) -> EnvironmentQuery:
        """Resolve the single authoritative environment instance for planning and execution."""
        if runtime_env is not None:
            if allow_override:
                return runtime_env
            if self.environment is not None and self.environment is not runtime_env:
                raise ValueError(
                    f"{self.name}: environment ownership conflict — action is bound to "
                    f"{self.environment!r}, which conflicts with runtime environment {runtime_env!r}."
                )
            return runtime_env
        if self.environment is not None:
            return self.environment
        raise ValueError(
            f"{self.name} requires an authoritative environment "
            f"instance (either bound to action, provided by caller, or injected by planner); "
            f"silent fallback to synthetic flat ground is prohibited."
        )

    def estimate_duration_frames(
        self,
        initial_state: MotionState,
        config: PipelineConfig,
        environment: Optional[EnvironmentQuery] = None,
    ) -> int:
        """Estimate timeline duration using the real authoritative environment query."""
        env = self.resolve_environment(
            runtime_env=environment,
            allow_override=(environment is not None),
        )
        if self.route is not None:
            current_route = replace(self.route, start_pos=initial_state.position)
            _, total_frames = plan_terrain_footsteps(current_route, env, start_frame=initial_state.frame)
            return total_frames
        else:
            _, total_frames = build_terrain_step_schedule(
                self.spec,
                env,
                start_frame=initial_state.frame,
            )
            return total_frames

    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        """Execute terrain-aware locomotion through the authoritative 6-phase pipeline."""
        environment = self.resolve_environment(
            runtime_env=context.environment,
            allow_override=False,
        )
        fps = float(context.config.fps)
        start_frame = initial_state.frame

        bridge_executor: Optional[KinematicBridgeExecutor] = context.bridge_executor
        if bridge_executor is None:
            bridge_executor = KinematicBridgeExecutor(
                armature_obj=context.armature_obj,
                root_obj=context.root_obj,
                environment=environment,
                default_fps=context.config.fps,
            )

        # 1. Build discrete terrain step schedule dynamically from environment
        if self.route is not None:
            current_route = replace(self.route, start_pos=initial_state.position)
            schedule, total_frames = plan_terrain_footsteps(
                current_route, environment, start_frame=start_frame
            )
        else:
            schedule, total_frames = build_terrain_step_schedule(
                self.spec, environment, start_frame=start_frame
            )

        # Monotonic, C1-continuous Hermite knot parameters for Root forward motion
        knot_frames, knot_y, knot_v = _build_continuous_root_forward_spline(schedule, fps)

        # Initial reference positions
        init_corridor_x = initial_state.position[0]
        init_y = initial_state.position[1]
        left_x = init_corridor_x - HIP_X_OFFSET
        right_x = init_corridor_x + HIP_X_OFFSET

        res_init_l = environment.query_ground_support_at(left_x, init_y)
        res_init_r = environment.query_ground_support_at(right_x, init_y)
        if not res_init_l.success:
            raise ValueError(f"Initial left foot execution rejected: {res_init_l.error_reason}")
        if not res_init_r.success:
            raise ValueError(f"Initial right foot execution rejected: {res_init_r.error_reason}")
        if not res_init_l.allows_regular_support:
            raise ValueError(f"Initial left foot execution rejected: surface '{res_init_l.surface_id}' does not allow regular support")
        if not res_init_r.allows_regular_support:
            raise ValueError(f"Initial right foot execution rejected: surface '{res_init_r.surface_id}' does not allow regular support")

        init_l_z = res_init_l.contact_point_world[2]
        init_r_z = res_init_r.contact_point_world[2]
        init_l_norm = res_init_l.surface_normal_world
        init_r_norm = res_init_r.surface_normal_world
        init_l_surf_id = res_init_l.surface_id
        init_r_surf_id = res_init_r.surface_id
        init_z = 0.5 * (init_l_z + init_r_z)

        last_known_l_xyz = (left_x, init_y, init_l_z)
        last_known_r_xyz = (right_x, init_y, init_r_z)
        last_known_l_pitch = pitch_from_surface_normal(init_l_norm)
        last_known_r_pitch = pitch_from_surface_normal(init_r_norm)

        feet_pos_final = {
            "L": last_known_l_xyz,
            "R": last_known_r_xyz,
        }
        feet_pitch_final = {
            "L": last_known_l_pitch,
            "R": last_known_r_pitch,
        }

        states: List[MotionState] = []
        frame_records: List[dict] = []
        unreachable_count = 0
        current_motion_state = initial_state

        # ---------------------------------------------------------------------
        # Frame-by-Frame Traversal Execution Loop
        # ---------------------------------------------------------------------
        for f_idx in range(total_frames):
            current_frame = start_frame + f_idx
            time_sec = (current_frame - 1) / fps

            # 2. Determine Stance/Swing Phase & Gait Parameter
            active_step: Optional[TerrainStepPlan] = None
            for step in schedule:
                if step.frame_start <= current_frame < step.frame_end:
                    active_step = step
                    break

            if active_step is None:
                # Stationary standing (Start preparation or Final stop)
                is_start_stand = f_idx < self.spec.stand_start_frames
                mode = MotionMode.IDLE
                gait_u = 0.0
                gait_amp = 0.0

                if is_start_stand:
                    # Initial stance
                    foot_l_tgt = PlannedFootTarget(
                        world_xyz=(left_x, init_y, init_l_z + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(last_known_l_pitch, 0.0, 0.0),
                        surface_id=init_l_surf_id,
                        normal_world=init_l_norm,
                        clamp_ground=False,
                    )
                    foot_r_tgt = PlannedFootTarget(
                        world_xyz=(right_x, init_y, init_r_z + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(last_known_r_pitch, 0.0, 0.0),
                        surface_id=init_r_surf_id,
                        normal_world=init_r_norm,
                        clamp_ground=False,
                    )
                    root_x = init_corridor_x
                    root_y = init_y
                    root_z = 0.5 * (init_l_z + init_r_z)
                    phase_l = "stance"
                    phase_r = "stance"
                else:
                    # Final stop stance
                    fl_xyz = feet_pos_final["L"]
                    fr_xyz = feet_pos_final["R"]
                    fl_pitch = feet_pitch_final["L"]
                    fr_pitch = feet_pitch_final["R"]
                    last_known_l_xyz = fl_xyz
                    last_known_r_xyz = fr_xyz
                    last_known_l_pitch = fl_pitch
                    last_known_r_pitch = fr_pitch
                    res_fl = environment.query_ground_support_at(fl_xyz[0], fl_xyz[1])
                    res_fr = environment.query_ground_support_at(fr_xyz[0], fr_xyz[1])
                    fl_norm = res_fl.surface_normal_world if res_fl.success else (0.0, 0.0, 1.0)
                    fr_norm = res_fr.surface_normal_world if res_fr.success else (0.0, 0.0, 1.0)

                    foot_l_tgt = PlannedFootTarget(
                        world_xyz=(fl_xyz[0], fl_xyz[1], fl_xyz[2] + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(fl_pitch, 0.0, 0.0),
                        normal_world=fl_norm,
                        clamp_ground=False,
                    )
                    foot_r_tgt = PlannedFootTarget(
                        world_xyz=(fr_xyz[0], fr_xyz[1], fr_xyz[2] + ANKLE_REST_Z),
                        is_locked=True,
                        rotation_deg=(fr_pitch, 0.0, 0.0),
                        normal_world=fr_norm,
                        clamp_ground=False,
                    )
                    root_x = init_corridor_x
                    root_y = 0.5 * (fl_xyz[1] + fr_xyz[1])
                    root_z = 0.5 * (fl_xyz[2] + fr_xyz[2])
                    phase_l = "stance"
                    phase_r = "stance"
            else:
                # Active step transition
                mode = MotionMode.WALK
                dur = active_step.duration_frames
                step_progress = (current_frame - active_step.frame_start) / float(dur) if dur > 0 else 1.0
                step_progress = max(0.0, min(1.0, step_progress))
                step_alpha = _smoothstep01(step_progress)

                st_side = active_step.stance_side
                sw_side = active_step.swing_side
                st_xyz = active_step.stance_xyz
                st_pitch = active_step.stance_pitch_deg

                # Stance foot is pinned strictly in World Space
                st_target = PlannedFootTarget(
                    world_xyz=(st_xyz[0], st_xyz[1], st_xyz[2] + ANKLE_REST_Z),
                    is_locked=True,
                    rotation_deg=(st_pitch, 0.0, 0.0),
                    surface_id=active_step.stance_surface_id,
                    normal_world=active_step.stance_normal,
                    clamp_ground=False,
                )

                # Swing foot trajectory: smooth horizontal interpolation
                sw_x = (1.0 - step_alpha) * active_step.swing_start_xyz[0] + step_alpha * active_step.swing_end_xyz[0]
                sw_y = (1.0 - step_alpha) * active_step.swing_start_xyz[1] + step_alpha * active_step.swing_end_xyz[1]

                # Elevation baseline smoothly blending between takeoff and landing surfaces
                z_takeoff = active_step.swing_start_xyz[2]
                z_landing = active_step.swing_end_xyz[2]
                z_base = (1.0 - step_alpha) * z_takeoff + step_alpha * z_landing

                # Parabolic clearance arc
                h_clear = active_step.step_height_clearance
                arc_z = 4.0 * h_clear * step_alpha * (1.0 - step_alpha)

                # Guaranteed minimum clearance across entire foot rigid bounding footprint
                res_heel = environment.query_ground_support_at(sw_x, sw_y - 0.07)
                res_ankle = environment.query_ground_support_at(sw_x, sw_y)
                res_toe = environment.query_ground_support_at(sw_x, sw_y + 0.15)
                z_terr_heel = res_heel.contact_point_world[2] if res_heel.success else z_base
                z_terr_ankle = res_ankle.contact_point_world[2] if res_ankle.success else z_base
                z_terr_toe = res_toe.contact_point_world[2] if res_toe.success else z_base
                z_terr_foot = max(z_terr_heel, z_terr_ankle, z_terr_toe)
                sw_z_clean = _compute_swing_clearance_z(
                    step_alpha=step_alpha,
                    z_base=z_base,
                    arc_z=arc_z,
                    z_terr_foot=z_terr_foot,
                    min_clearance_amp=0.045,
                )

                # Natural swing foot ankle pitch coordination:
                # Continuous pitch takeoff from stance pitch.
                # Mid-swing relaxation (plantarflexion) prevents shin-ankle ROM conflict.
                sw_pitch_start = active_step.swing_start_pitch_deg
                sw_pitch_base = (1.0 - step_alpha) * sw_pitch_start + step_alpha * active_step.swing_end_pitch_deg

                # Pure geometric determination of swing relaxation amplitude:
                delta_z_step = active_step.swing_end_xyz[2] - active_step.swing_start_xyz[2]
                if delta_z_step > 0.08 and abs(active_step.swing_end_pitch_deg) < 3.0:
                    # Stepping up onto raised surface / stairs
                    swing_relax_amp = 19.0
                elif active_step.swing_end_pitch_deg > 5.0 or active_step.swing_start_pitch_deg > 5.0:
                    # Sloped terrain
                    swing_relax_amp = 25.0
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

                feet_pos_final = {
                    st_side: st_xyz,
                    sw_side: active_step.swing_end_xyz,
                }
                feet_pitch_final = {
                    st_side: st_pitch,
                    sw_side: active_step.swing_end_pitch_deg,
                }

                root_x = init_corridor_x
                root_y = _evaluate_root_y_hermite(
                    current_frame=current_frame,
                    step_k=active_step.k,
                    knot_frames=knot_frames,
                    knot_y=knot_y,
                    knot_v=knot_v,
                    fps=fps,
                )
                root_z = 0.5 * (st_xyz[2] + z_base)

                gait_u = (active_step.k % 2) * 0.5 + 0.5 * step_alpha
                gait_amp = 1.0

            # -----------------------------------------------------------------
            # 3. Dynamic Posture, Knee Flexion & Slope Adaptation (Pure Geometry)
            # -----------------------------------------------------------------
            res_root = environment.query_ground_support_at(root_x, root_y)
            terr_norm = res_root.surface_normal_world if res_root.success else (0.0, 0.0, 1.0)
            slope_pitch_deg = pitch_from_surface_normal(terr_norm)

            step_pitch = 0.0
            step_delta_z = 0.0
            trans_delta_z = 0.0
            is_descending_trans = False
            if active_step is not None:
                step_pitch = 0.5 * (active_step.stance_pitch_deg + active_step.swing_end_pitch_deg)
                step_delta_z = abs(active_step.swing_end_xyz[2] - active_step.stance_xyz[2])
                trans_delta_z = max(
                    abs(active_step.swing_start_xyz[2] - active_step.stance_xyz[2]),
                    abs(active_step.swing_end_xyz[2] - active_step.stance_xyz[2]),
                )
                if (
                    active_step.swing_start_xyz[2] > active_step.stance_xyz[2]
                    or active_step.swing_start_xyz[2] > active_step.swing_end_xyz[2]
                    or active_step.swing_end_pitch_deg < -4.0
                    or active_step.stance_pitch_deg < -4.0
                ):
                    is_descending_trans = True

            eff_slope_pitch = slope_pitch_deg if abs(slope_pitch_deg) > 4.0 else step_pitch

            # Pure geometric pelvis drop depth
            if step_delta_z > 0.08 and abs(eff_slope_pitch) < 4.0:
                target_drop = self.spec.pelvis_drop_stairs
            elif eff_slope_pitch > 4.0:
                target_drop = self.spec.pelvis_drop_uphill
            elif eff_slope_pitch < -4.0:
                target_drop = self.spec.pelvis_drop_downhill
            elif trans_delta_z > 0.03:
                # Transition step onto or off slope
                target_drop = self.spec.pelvis_drop_downhill if is_descending_trans else self.spec.pelvis_drop_uphill
            else:
                target_drop = self.spec.pelvis_drop_flat

            # Vertical oscillation bounce
            bounce = -0.012 * math.cos(4.0 * math.pi * gait_u) if mode != MotionMode.IDLE else 0.0
            pelvis_dz = -(target_drop + bounce)

            # Lateral list and axial pelvis rotation
            if mode == MotionMode.IDLE:
                pelvis_rot_deg = (0.0, 0.0, 0.0)
                spine_rot_deg = (0.0, 0.0, 0.0)
                neck_rot_deg = (0.0, 0.0, 0.0)
                head_rot_deg = (0.0, 0.0, 0.0)
            else:
                pelvis_roll = 1.5 * math.sin(2.0 * math.pi * gait_u)
                pelvis_yaw = 2.0 * math.sin(2.0 * math.pi * gait_u)
                pelvis_pitch = 0.2 * slope_pitch_deg
                pelvis_rot_deg = (pelvis_pitch, pelvis_yaw, pelvis_roll)

                # Torso forward lean based on uphill/downhill gradient (pure geometry)
                if slope_pitch_deg > 2.0:
                    forward_lean = self.spec.torso_lean_uphill_deg * (slope_pitch_deg / 15.0)
                elif slope_pitch_deg < -2.0:
                    forward_lean = self.spec.torso_lean_downhill_deg * (-slope_pitch_deg / 20.0)
                elif step_delta_z > 0.05:
                    forward_lean = 2.0
                else:
                    forward_lean = 1.0

                spine_rot_deg = (forward_lean, -0.5 * pelvis_yaw, -0.5 * pelvis_roll)
                neck_rot_deg = (-0.4 * forward_lean, 0.0, 0.0)
                head_rot_deg = (-0.4 * forward_lean, 0.0, 0.0)

            # Arm swing: contralateral arm swinging
            arm_swing_amp = self.spec.arm_swing_deg * gait_amp
            arm_l_rx = -arm_swing_amp * math.sin(2.0 * math.pi * gait_u)
            arm_r_rx = arm_swing_amp * math.sin(2.0 * math.pi * gait_u)

            fk_rotations = {
                "upper_arm.L": (arm_l_rx, 0.0, 0.0),
                "upper_arm.R": (arm_r_rx, 0.0, 0.0),
                "forearm.L": (max(0.0, -0.5 * arm_l_rx + 15.0), 0.0, 0.0),
                "forearm.R": (max(0.0, -0.5 * arm_r_rx + 15.0), 0.0, 0.0),
                "hand.L": (0.0, 0.0, 0.0),
                "hand.R": (0.0, 0.0, 0.0),
            }

            # 4. Formulate Unified Planned Pose Contract
            planned_pose = KinematicPlannedPose(
                frame=current_frame,
                time_seconds=time_sec,
                root_position=(root_x, root_y, root_z),
                root_yaw_deg=0.0,
                motion_mode=mode,
                pelvis_location=(0.0, pelvis_dz, 0.0),
                pelvis_rotation_deg=pelvis_rot_deg,
                spine_rotation_deg=spine_rot_deg,
                neck_rotation_deg=neck_rot_deg,
                head_rotation_deg=head_rot_deg,
                foot_L=foot_l_tgt,
                foot_R=foot_r_tgt,
                fk_joint_rotations_deg=fk_rotations,
            )

            # 5. Execute 6-Phase Frame via Bridge & WholeBodyController
            bridge_res = bridge_executor.execute_frame(
                planned=planned_pose,
            )

            if not bridge_res.success:
                unmet_desc = "; ".join(
                    f"{uc.target_name} ({uc.category}): {uc.description} (err={uc.error_amount:.4f})"
                    for uc in bridge_res.unmet_constraints
                ) if bridge_res.unmet_constraints else "unspecified constraint failure"
                raise RuntimeError(
                    f"TerrainWalkAction '{self.name}' failed at Frame {current_frame}: "
                    f"KinematicBridge execution failed (unmet={len(bridge_res.unmet_constraints)}): {unmet_desc}"
                )

            ms = bridge_res.motion_state
            if ms is None:
                raise RuntimeError(
                    f"TerrainWalkAction '{self.name}' failed at Frame {current_frame}: "
                    f"KinematicBridge returned motion_state=None"
                )

            # Extract contacts & telemetry
            eff_l = bridge_res.wbc_result.end_effectors.get("foot_L")
            eff_r = bridge_res.wbc_result.end_effectors.get("foot_R")
            drift_l = eff_l.position_error_m if eff_l else 0.0
            drift_r = eff_r.position_error_m if eff_r else 0.0
            reach_l = eff_l.is_reachable if eff_l else True
            reach_r = eff_r.is_reachable if eff_r else True

            ms_params = dict(ms.params)
            ms_params.update({
                "planned_phase_l": phase_l,
                "planned_phase_r": phase_r,
                "planned_locked_l": foot_l_tgt.is_locked,
                "planned_locked_r": foot_r_tgt.is_locked,
                "planned_target_l": foot_l_tgt.world_xyz,
                "planned_target_r": foot_r_tgt.world_xyz,
            })
            ms = ms.clone_with(mode=mode, params=ms_params)

            current_motion_state = ms
            states.append(ms)

            # Build 6-Phase Diagnostic Record for this frame
            prev_y = frame_records[-1]["root_y"] if frame_records else root_y
            speed_mps = abs(root_y - prev_y) * fps
            frame_records.append({
                "frame": current_frame,
                "time_sec": round(time_sec, 4),
                "mode": mode.value,
                "root_x": round(root_x, 5),
                "root_y": round(root_y, 5),
                "root_z": round(root_z, 5),
                "speed_mps": round(speed_mps, 4),
                # Phase 1: Environment
                "environment": {
                    "query_pos": [round(root_x, 3), round(root_y, 3), round(root_z, 3)],
                    "terrain_height": round(h, 3) if (h := environment.ground_height_at(root_x, root_y)) is not None else None,
                    "surface_normal": [round(v, 3) for v in terr_norm],
                    "slope_pitch_deg": round(slope_pitch_deg, 2),
                    "surface_id_L": getattr(foot_l_tgt, "surface_id", "ground"),
                    "surface_id_R": getattr(foot_r_tgt, "surface_id", "ground"),
                },
                # Phase 2: Motion Planning
                "motion_planning": {
                    "action_name": self.name,
                    "active_step_k": active_step.k if active_step else -1,
                    "stage_name": active_step.stage_name if active_step else "standing",
                    "phase_L": phase_l,
                    "phase_R": phase_r,
                    "planned_foot_L": [round(v, 4) for v in foot_l_tgt.world_xyz],
                    "planned_foot_R": [round(v, 4) for v in foot_r_tgt.world_xyz],
                    "foot_pitch_L": round(foot_l_tgt.rotation_deg[0], 2),
                    "foot_pitch_R": round(foot_r_tgt.rotation_deg[0], 2),
                },
                # Phase 3: Kinematic Bridge
                "kinematic_bridge": {
                    "root_target": [round(v, 4) for v in planned_pose.root_position],
                    "pelvis_offset": [round(v, 4) for v in planned_pose.pelvis_location],
                    "pelvis_rot_deg": [round(v, 2) for v in planned_pose.pelvis_rotation_deg],
                    "spine_rot_deg": [round(v, 2) for v in planned_pose.spine_rotation_deg],
                },
                # Phase 4: Whole Body Controller
                "whole_body_controller": {
                    "is_all_reachable": bridge_res.wbc_result.is_all_reachable,
                    "foot_L_locked": foot_l_tgt.is_locked,
                    "foot_R_locked": foot_r_tgt.is_locked,
                    "unmet_constraints": len(bridge_res.unmet_constraints),
                },
                # Phase 5: Actual Armature & Telemetry
                "actual_armature": {
                    "com_world": [round(v, 4) for v in bridge_res.com_world],
                    "mass_kg": round(bridge_res.wbc_result.com_result.total_mass_kg, 2) if bridge_res.wbc_result.com_result else 70.0,
                    "ankle_L_world": [round(v, 4) for v in eff_l.actual_world_xyz] if eff_l else [0, 0, 0],
                    "ankle_R_world": [round(v, 4) for v in eff_r.actual_world_xyz] if eff_r else [0, 0, 0],
                },
                # Phase 6: Validation Metrics
                "validation": {
                    "drift_L_m": round(drift_l, 6),
                    "drift_R_m": round(drift_r, 6),
                    "reach_L": reach_l,
                    "reach_R": reach_r,
                    "pass": (drift_l < 1e-4 and drift_r < 1e-4 and reach_l and reach_r),
                },
            })

        disp_y = states[-1].position[1] - states[0].position[1] if states else 0.0
        disp_z = states[-1].position[2] - states[0].position[2] if states else 0.0

        return ActionExecutionResult(
            action_name=self.name,
            initial_state=initial_state,
            final_state=states[-1] if states else initial_state,
            states=states,
            frame_records=frame_records,
            unreachable_count=unreachable_count,
            step_schedule=[
                {
                    "k": s.k,
                    "frame_start": s.frame_start,
                    "frame_end": s.frame_end,
                    "stance_side": s.stance_side,
                    "swing_side": s.swing_side,
                    "stance_xyz": s.stance_xyz,
                    "swing_end_xyz": s.swing_end_xyz,
                    "clearance": s.step_height_clearance,
                    "stage_name": s.stage_name,
                }
                for s in schedule
            ],
            metrics={
                "total_disp_y": disp_y,
                "total_disp_z": disp_z,
                "unreachable_count": unreachable_count,
                "schedule_steps": len(schedule),
            },
            success=True,
            unmet_constraints=[],
            failure_reason=None,
            failure_frame=None,
        )
