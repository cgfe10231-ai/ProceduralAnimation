"""Stateless Upper-Limb Trajectory Math & Sequence Validation (Task 10-D Convergence).

Migrated and converged from `src/motion/terrain_walk.py` so `MotionPlanner`,
`MotionRuntimeContext`, `TerrainWalkAction`, and all historical `MotionAction`
subclasses share one single stateless source of truth without creating a second
scheduler, controller, bridge, or circular module dependency.

Constraints enforced by design:
- Pure Python math & immutable data validation only.
- Zero calls to `bpy` scene/pose write APIs or Rig solvers.
- Zero backward dependency on concrete `MotionAction` subclasses.
- Zero circular module-level imports.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.motion.kinematic_bridge import PlannedHandTarget


# [INTRODUCED 2026-11-26T17:13:00+08:00]
# [CONVERGED 2026-11-27T13:50:00+08:00] TASK 10-d-5: relocated from terrain_walk.py as shared stateless public descriptor; terrain_walk.py re-exports for compatibility.
# TASK: TASK 10-d-3
# CLASS: UpperLimbSegment
# PURPOSE: Immutable trajectory segment descriptor carrying caller-supplied FK/IK endpoints, timing, space, and clamp policy for decoupled upper-limb motion.
# REASON: Resolve TASK 10-d-3 where upper-limb motion lacked an immutable parametric segment representation independent of lower-limb gait; needed so callers provide arbitrary FK/IK targets without hardcoding action schedules or mutating shared state.
@dataclass(frozen=True)
class UpperLimbSegment:
    """Immutable caller-supplied parametric motion segment for a single arm."""

    mode: str
    start_time_sec: float
    duration_sec: float

    fk_start_deg: Optional[Tuple[Tuple[float, float, float], ...]] = None
    fk_end_deg: Optional[Tuple[Tuple[float, float, float], ...]] = None

    wrist_start_xyz: Optional[Tuple[float, float, float]] = None
    wrist_end_xyz: Optional[Tuple[float, float, float]] = None

    rotation_start_deg: Optional[Tuple[float, float, float]] = None
    rotation_end_deg: Optional[Tuple[float, float, float]] = None

    pole_start_xyz: Optional[Tuple[float, float, float]] = None
    pole_end_xyz: Optional[Tuple[float, float, float]] = None

    position_space: str = "WORLD"
    clamp_reach: bool = True


# [INTRODUCED 2026-11-26T16:52:00+08:00]
# [CONVERGED 2026-11-27T13:50:00+08:00] TASK 10-d-5: relocated from terrain_walk.py unchanged; terrain_walk.py re-exports for compatibility.
# TASK: TASK 10-d-2
# FUNCTION: _evaluate_upper_limb_progress
# PURPOSE: Compute stateless, action-local time normalized linear progress u and C2-smooth quintic progress h for upper-limb motion from time_sec, start_time_sec, and duration_sec.
# REASON: Resolve TASK 10-d-2 where terrain_walk.py lacked independent upper-limb temporal parameterization and relied on cosine _smoothstep01(); historical smoothers serve lower-limb gait locomotion and cannot alter their math semantics, so upper-limb trajectories must remain decoupled from gait_u, gait_amp, MotionMode, and lower-limb state.
def _evaluate_upper_limb_progress(
    time_sec: float,
    start_time_sec: float,
    duration_sec: float,
) -> Tuple[float, float]:
    """Evaluate decoupled upper-limb normalized linear progress u and quintic h."""
    converted: List[float] = []
    for name, raw in (
        ("time_sec", time_sec),
        ("start_time_sec", start_time_sec),
        ("duration_sec", duration_sec),
    ):
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TypeError(f"{name} must be int or float, got {type(raw).__name__}")
        try:
            val = float(raw)
        except OverflowError as exc:
            raise ValueError(f"{name} cannot be converted to a finite float") from exc
        if not math.isfinite(val):
            raise ValueError(f"{name} must be finite, got {val!r}")
        converted.append(0.0 if val == 0.0 else val)

    t, start, duration = converted
    if t < 0.0:
        raise ValueError(f"time_sec must be non-negative, got {t!r}")
    if start < 0.0:
        raise ValueError(f"start_time_sec must be non-negative, got {start!r}")
    if not (duration > 0.0):
        raise ValueError(f"duration_sec must be strictly positive, got {duration!r}")

    end_time = start + duration
    if not math.isfinite(end_time) or not (end_time > start):
        raise ValueError(
            "end_time (start_time_sec + duration_sec) must be finite and strictly "
            f"greater than start_time_sec, got start={start!r}, duration={duration!r}, "
            f"end={end_time!r}"
        )

    if t <= start:
        return (0.0, 0.0)
    if t >= end_time:
        return (1.0, 1.0)

    u = (t - start) / duration
    if not math.isfinite(u):
        u = 1.0
    elif u < 0.0:
        u = 0.0
    elif u > 1.0:
        u = 1.0

    if u <= 0.5:
        h = u**3 * (10.0 + u * (-15.0 + 6.0 * u))
    else:
        v = 1.0 - u
        h = 1.0 - v**3 * (10.0 + v * (-15.0 + 6.0 * v))
    h = max(0.0, min(1.0, h))
    return (u, h)


# [INTRODUCED 2026-11-26T17:13:00+08:00]
# [CONVERGED 2026-11-27T13:50:00+08:00] TASK 10-d-5: relocated from terrain_walk.py unchanged; terrain_walk.py re-exports for compatibility.
# TASK: TASK 10-d-3
# FUNCTION: _validate_upper_limb_vector
# PURPOSE: Validate and normalize a 3-tuple of finite non-bool numeric coordinates/angles into a new 3-float tuple without mutating input.
# REASON: Resolve TASK 10-d-3 to uniformly enforce 3D vector type, length, finiteness, and overflow safety across FK rotations, IK wrist/pole positions, and Root position without duplicating checks.
def _validate_upper_limb_vector(
    value: Tuple[float, float, float],
    name: str,
) -> Tuple[float, float, float]:
    """Validate a 3D numeric tuple and return a fresh tuple of finite floats."""
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple, got {type(value).__name__}")
    if len(value) != 3:
        raise ValueError(f"{name} must have length 3, got {len(value)}")

    out: List[float] = []
    for idx, comp in enumerate(value):
        if isinstance(comp, bool) or not isinstance(comp, (int, float)):
            raise TypeError(
                f"{name}[{idx}] must be int or float, got {type(comp).__name__}"
            )
        try:
            val = float(comp)
        except OverflowError as exc:
            raise ValueError(
                f"{name}[{idx}] cannot be converted to a finite float"
            ) from exc
        if not math.isfinite(val):
            raise ValueError(f"{name}[{idx}] must be finite, got {val!r}")
        out.append(0.0 if val == 0.0 else val)
    return (out[0], out[1], out[2])


# [INTRODUCED 2026-11-26T17:13:00+08:00]
# [CONVERGED 2026-11-27T13:50:00+08:00] TASK 10-d-5: relocated from terrain_walk.py unchanged (using local lazy imports inside IK branch to prevent framework <-> kinematic_bridge import cycle); terrain_walk.py re-exports for compatibility.
# TASK: TASK 10-d-3
# FUNCTION: _evaluate_upper_limb_segment
# PURPOSE: Evaluate a single UpperLimbSegment for side 'L' or 'R' at time_sec and current frame Root into a stateless (Optional[PlannedHandTarget], Dict[str, Tuple[float, float, float]]) pair ready for KinematicPlannedPose.
# REASON: Resolve TASK 10-d-3 so independent FK/IK upper-limb targets can be computed via _evaluate_upper_limb_progress() and root_local_to_world_vector() without touching lower-limb gait, scene state, or TerrainWalkAction frame loop.
def _evaluate_upper_limb_segment(
    segment: UpperLimbSegment,
    side: str,
    time_sec: float,
    root_position: Tuple[float, float, float],
    root_yaw_deg: float,
) -> Tuple[
    Optional["PlannedHandTarget"],
    Dict[str, Tuple[float, float, float]],
]:
    """Evaluate one decoupled upper-limb segment into FK or IK bridge targets."""
    if not isinstance(segment, UpperLimbSegment):
        raise TypeError(
            f"segment must be UpperLimbSegment, got {type(segment).__name__}"
        )
    if not isinstance(side, str):
        raise TypeError(f"side must be str, got {type(side).__name__}")
    if side not in ("L", "R"):
        raise ValueError(f"side must be 'L' or 'R', got {side!r}")
    if not isinstance(segment.mode, str):
        raise TypeError(f"mode must be str, got {type(segment.mode).__name__}")
    if segment.mode not in ("FK", "IK"):
        raise ValueError(f"mode must be 'FK' or 'IK', got {segment.mode!r}")
    if not isinstance(segment.position_space, str):
        raise TypeError(
            f"position_space must be str, got {type(segment.position_space).__name__}"
        )
    if segment.position_space not in ("WORLD", "ROOT_LOCAL"):
        raise ValueError(
            "position_space must be 'WORLD' or 'ROOT_LOCAL', got "
            f"{segment.position_space!r}"
        )
    if not isinstance(segment.clamp_reach, bool):
        raise TypeError(
            f"clamp_reach must be bool, got {type(segment.clamp_reach).__name__}"
        )

    root_pos = _validate_upper_limb_vector(root_position, "root_position")
    if isinstance(root_yaw_deg, bool) or not isinstance(root_yaw_deg, (int, float)):
        raise TypeError(
            f"root_yaw_deg must be int or float, got {type(root_yaw_deg).__name__}"
        )
    try:
        root_yaw = float(root_yaw_deg)
    except OverflowError as exc:
        raise ValueError("root_yaw_deg cannot be converted to a finite float") from exc
    if not math.isfinite(root_yaw):
        raise ValueError(f"root_yaw_deg must be finite, got {root_yaw!r}")

    if segment.mode == "FK":
        if segment.position_space != "WORLD":
            raise ValueError(
                f"FK mode requires position_space='WORLD', got {segment.position_space!r}"
            )
        for forbidden_name in (
            "wrist_start_xyz",
            "wrist_end_xyz",
            "rotation_start_deg",
            "rotation_end_deg",
            "pole_start_xyz",
            "pole_end_xyz",
        ):
            if getattr(segment, forbidden_name) is not None:
                raise ValueError(f"FK mode must not carry IK field {forbidden_name}")
        if segment.fk_start_deg is None or segment.fk_end_deg is None:
            raise ValueError("FK mode requires both fk_start_deg and fk_end_deg")
        if not isinstance(segment.fk_start_deg, tuple):
            raise TypeError(
                f"fk_start_deg must be a tuple, got {type(segment.fk_start_deg).__name__}"
            )
        if not isinstance(segment.fk_end_deg, tuple):
            raise TypeError(
                f"fk_end_deg must be a tuple, got {type(segment.fk_end_deg).__name__}"
            )
        if len(segment.fk_start_deg) != 3 or len(segment.fk_end_deg) != 3:
            raise ValueError("fk_start_deg and fk_end_deg must each have length 3")

        fk_start_vecs = tuple(
            _validate_upper_limb_vector(vec, f"fk_start_deg[{idx}]")
            for idx, vec in enumerate(segment.fk_start_deg)
        )
        fk_end_vecs = tuple(
            _validate_upper_limb_vector(vec, f"fk_end_deg[{idx}]")
            for idx, vec in enumerate(segment.fk_end_deg)
        )

        _, h = _evaluate_upper_limb_progress(
            time_sec, segment.start_time_sec, segment.duration_sec
        )

        fk_targets: Dict[str, Tuple[float, float, float]] = {}
        for bone_name, s_vec, e_vec in zip(
            ("upper_arm", "forearm", "hand"), fk_start_vecs, fk_end_vecs
        ):
            if h == 0.0:
                interp = s_vec
            elif h == 1.0:
                interp = e_vec
            else:
                interp = (
                    (1.0 - h) * s_vec[0] + h * e_vec[0],
                    (1.0 - h) * s_vec[1] + h * e_vec[1],
                    (1.0 - h) * s_vec[2] + h * e_vec[2],
                )
                if not all(math.isfinite(c) for c in interp):
                    raise ValueError(
                        f"Non-finite interpolated FK target for {bone_name}.{side}: {interp!r}"
                    )
            fk_targets[f"{bone_name}.{side}"] = interp
        return (None, fk_targets)

    # IK mode
    if segment.fk_start_deg is not None or segment.fk_end_deg is not None:
        raise ValueError("IK mode requires fk_start_deg and fk_end_deg to be None")
    if segment.wrist_start_xyz is None or segment.wrist_end_xyz is None:
        raise ValueError("IK mode requires both wrist_start_xyz and wrist_end_xyz")
    if (segment.rotation_start_deg is None) != (segment.rotation_end_deg is None):
        raise ValueError(
            "IK rotation_start_deg and rotation_end_deg must both be set or both be None"
        )
    if (segment.pole_start_xyz is None) != (segment.pole_end_xyz is None):
        raise ValueError(
            "IK pole_start_xyz and pole_end_xyz must both be set or both be None"
        )

    wrist_s = _validate_upper_limb_vector(segment.wrist_start_xyz, "wrist_start_xyz")
    wrist_e = _validate_upper_limb_vector(segment.wrist_end_xyz, "wrist_end_xyz")
    rot_s = (
        _validate_upper_limb_vector(segment.rotation_start_deg, "rotation_start_deg")
        if segment.rotation_start_deg is not None
        else None
    )
    rot_e = (
        _validate_upper_limb_vector(segment.rotation_end_deg, "rotation_end_deg")
        if segment.rotation_end_deg is not None
        else None
    )
    pole_s = (
        _validate_upper_limb_vector(segment.pole_start_xyz, "pole_start_xyz")
        if segment.pole_start_xyz is not None
        else None
    )
    pole_e = (
        _validate_upper_limb_vector(segment.pole_end_xyz, "pole_end_xyz")
        if segment.pole_end_xyz is not None
        else None
    )

    _, h = _evaluate_upper_limb_progress(
        time_sec, segment.start_time_sec, segment.duration_sec
    )

    from src.motion.framework import root_local_to_world_vector
    from src.motion.kinematic_bridge import PlannedHandTarget

    ik_values: Dict[str, Optional[Tuple[float, float, float]]] = {}
    for field_name, s_vec, e_vec in (
        ("wrist", wrist_s, wrist_e),
        ("rotation", rot_s, rot_e),
        ("pole", pole_s, pole_e),
    ):
        if s_vec is None:
            ik_values[field_name] = None
            continue
        assert e_vec is not None
        if h == 0.0:
            val_vec = s_vec
        elif h == 1.0:
            val_vec = e_vec
        else:
            val_vec = (
                (1.0 - h) * s_vec[0] + h * e_vec[0],
                (1.0 - h) * s_vec[1] + h * e_vec[1],
                (1.0 - h) * s_vec[2] + h * e_vec[2],
            )
            if not all(math.isfinite(c) for c in val_vec):
                raise ValueError(
                    f"Non-finite interpolated IK {field_name}: {val_vec!r}"
                )
        if field_name in ("wrist", "pole") and segment.position_space == "ROOT_LOCAL":
            wx, wy, wz = root_local_to_world_vector(val_vec, root_yaw)
            world_vec = (root_pos[0] + wx, root_pos[1] + wy, root_pos[2] + wz)
            if not all(math.isfinite(c) for c in world_vec):
                raise ValueError(
                    f"Non-finite world-space IK {field_name}: {world_vec!r}"
                )
            ik_values[field_name] = world_vec
        else:
            ik_values[field_name] = val_vec

    wrist_world_xyz = ik_values["wrist"]
    assert wrist_world_xyz is not None
    return (
        PlannedHandTarget(
            world_xyz=wrist_world_xyz,
            rotation_deg=ik_values["rotation"],
            enabled=True,
            weight=1.0,
            contact_intent=False,
            is_locked=False,
            pole_hint_world_xyz=ik_values["pole"],
            clamp_reach=segment.clamp_reach,
        ),
        {},
    )


# [INTRODUCED 2026-11-27T13:50:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: validate_upper_limb_segment_sequence
# PURPOSE: Validate and normalize an immutable Optional[Tuple[UpperLimbSegment, ...]] track for side 'L' or 'R' including per-segment math validation, optional timeline upper-bound check, monotonic non-overlapping times, and same-mode endpoint/space/option compatibility without mutating caller inputs.
# REASON: Converge the validated 10-d-4 segment sequence checks from terrain_walk.py into a shared stateless utility reused by MotionPlanner, MotionRuntimeContext.compose_planned_pose(), and TerrainWalkAction without duplicating validation code.
def validate_upper_limb_segment_sequence(
    segments: Optional[Tuple[UpperLimbSegment, ...]],
    side: str,
    max_time_sec: Optional[float] = None,
    parameter_name: Optional[str] = None,
) -> Optional[Tuple[UpperLimbSegment, ...]]:
    """Validate an immutable single-arm UpperLimbSegment sequence."""
    if not isinstance(side, str) or side not in ("L", "R"):
        raise ValueError(f"side must be 'L' or 'R', got {side!r}")
    label = parameter_name or f"upper_limb_{side}"

    if max_time_sec is not None:
        if isinstance(max_time_sec, bool) or not isinstance(max_time_sec, (int, float)):
            raise TypeError(f"max_time_sec must be int or float, got {type(max_time_sec).__name__}")
        max_bound = float(max_time_sec)
        if not math.isfinite(max_bound) or max_bound < 0.0:
            raise ValueError(f"max_time_sec must be finite and non-negative, got {max_time_sec!r}")
    else:
        max_bound = None

    if segments is None:
        return None
    if not isinstance(segments, tuple):
        raise TypeError(
            f"{label} must be None or a tuple of UpperLimbSegment, "
            f"got {type(segments).__name__}"
        )
    if len(segments) == 0:
        raise ValueError(f"{label} must not be an empty tuple")

    prev_start_sec: Optional[float] = None
    prev_end_sec: Optional[float] = None
    prev_seg: Optional[UpperLimbSegment] = None
    for seg_idx, seg in enumerate(segments):
        if not isinstance(seg, UpperLimbSegment):
            raise TypeError(
                f"{label}[{seg_idx}] must be UpperLimbSegment, "
                f"got {type(seg).__name__}"
            )
        _evaluate_upper_limb_segment(
            seg, side, seg.start_time_sec, (0.0, 0.0, 0.0), 0.0
        )
        seg_start_sec = float(seg.start_time_sec)
        seg_end_sec = seg_start_sec + float(seg.duration_sec)
        _evaluate_upper_limb_segment(
            seg, side, seg_end_sec, (0.0, 0.0, 0.0), 0.0
        )
        if max_bound is not None and seg_end_sec > max_bound + 1e-12:
            raise ValueError(
                f"{label}[{seg_idx}] end time {seg_end_sec:.6f}s "
                f"exceeds sequence/action timeline upper bound {max_bound:.6f}s"
            )
        if prev_seg is not None:
            assert prev_start_sec is not None and prev_end_sec is not None
            if not (seg_start_sec > prev_start_sec):
                raise ValueError(
                    f"{label}[{seg_idx}] start_time_sec ({seg_start_sec}) "
                    f"must be strictly greater than previous ({prev_start_sec})"
                )
            if seg_start_sec < prev_end_sec - 1e-12:
                raise ValueError(
                    f"{label}[{seg_idx}] start_time_sec ({seg_start_sec}) "
                    f"overlaps previous segment ending at {prev_end_sec}"
                )
            if prev_seg.mode == seg.mode:
                if seg.mode == "FK":
                    assert (
                        prev_seg.fk_end_deg is not None
                        and seg.fk_start_deg is not None
                    )
                    for bone_idx in range(3):
                        for axis_idx in range(3):
                            diff = abs(
                                float(prev_seg.fk_end_deg[bone_idx][axis_idx])
                                - float(seg.fk_start_deg[bone_idx][axis_idx])
                            )
                            if diff > 1e-6:
                                raise ValueError(
                                    f"{label} FK segment transition mismatch "
                                    f"between index {seg_idx - 1} and {seg_idx} at bone {bone_idx}[{axis_idx}]"
                                )
                else:
                    if prev_seg.position_space != seg.position_space:
                        raise ValueError(
                            f"{label} IK position_space mismatch between "
                            f"index {seg_idx - 1} ({prev_seg.position_space!r}) and {seg_idx} ({seg.position_space!r})"
                        )
                    if (prev_seg.rotation_end_deg is None) != (seg.rotation_start_deg is None):
                        raise ValueError(
                            f"{label} IK rotation presence mismatch between "
                            f"index {seg_idx - 1} and {seg_idx}"
                        )
                    if (prev_seg.pole_end_xyz is None) != (seg.pole_start_xyz is None):
                        raise ValueError(
                            f"{label} IK pole presence mismatch between "
                            f"index {seg_idx - 1} and {seg_idx}"
                        )
                    assert (
                        prev_seg.wrist_end_xyz is not None
                        and seg.wrist_start_xyz is not None
                    )
                    if any(
                        abs(float(prev_seg.wrist_end_xyz[k]) - float(seg.wrist_start_xyz[k])) > 1e-6
                        for k in range(3)
                    ):
                        raise ValueError(
                            f"{label} IK wrist transition mismatch between "
                            f"index {seg_idx - 1} and {seg_idx}"
                        )
                    if prev_seg.rotation_end_deg is not None and seg.rotation_start_deg is not None:
                        if any(
                            abs(float(prev_seg.rotation_end_deg[k]) - float(seg.rotation_start_deg[k])) > 1e-6
                            for k in range(3)
                        ):
                            raise ValueError(
                                f"{label} IK rotation transition mismatch between "
                                f"index {seg_idx - 1} and {seg_idx}"
                            )
                    if prev_seg.pole_end_xyz is not None and seg.pole_start_xyz is not None:
                        if any(
                            abs(float(prev_seg.pole_end_xyz[k]) - float(seg.pole_start_xyz[k])) > 1e-6
                            for k in range(3)
                        ):
                            raise ValueError(
                                f"{label} IK pole transition mismatch between "
                                f"index {seg_idx - 1} and {seg_idx}"
                            )
        prev_start_sec = seg_start_sec
        prev_end_sec = seg_end_sec
        prev_seg = seg

    return tuple(segments)


# [INTRODUCED 2026-11-27T13:50:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: select_upper_limb_segment
# PURPOSE: Select the active or endpoint-holding UpperLimbSegment index and descriptor at a given non-negative time_sec without modifying segments or state.
# REASON: Converge the 10-d-4 interval selection and endpoint-hold rule into a single stateless helper shared by centralized and action-local composition.
def select_upper_limb_segment(
    segments: Tuple[UpperLimbSegment, ...],
    time_sec: float,
) -> Tuple[int, UpperLimbSegment]:
    """Return (selected_idx, selected_segment) for time_sec using endpoint-hold semantics."""
    if not isinstance(segments, tuple) or len(segments) == 0:
        raise ValueError("segments must be a non-empty tuple of UpperLimbSegment")
    if isinstance(time_sec, bool) or not isinstance(time_sec, (int, float)):
        raise TypeError(f"time_sec must be int or float, got {type(time_sec).__name__}")
    t = float(time_sec)
    if not math.isfinite(t) or t < 0.0:
        raise ValueError(f"time_sec must be finite and non-negative, got {time_sec!r}")

    selected_idx = 0
    for idx, seg in enumerate(segments):
        if t >= seg.start_time_sec:
            selected_idx = idx
        else:
            break
    return selected_idx, segments[selected_idx]


# [INTRODUCED 2026-11-27T13:50:00+08:00]
# TASK: TASK 10-d-5
# FUNCTION: evaluate_upper_limb_sequence_at_time
# PURPOSE: Compose segment interval selection and _evaluate_upper_limb_segment() evaluation for one side at time_sec and current frame Root without side effects.
# REASON: Eliminate duplicate per-frame segment lookup and evaluation across unified target composition without reimplementing trajectory math.
def evaluate_upper_limb_sequence_at_time(
    segments: Tuple[UpperLimbSegment, ...],
    side: str,
    time_sec: float,
    root_position: Tuple[float, float, float],
    root_yaw_deg: float,
) -> Tuple[
    int,
    UpperLimbSegment,
    Optional["PlannedHandTarget"],
    Dict[str, Tuple[float, float, float]],
]:
    """Select the active segment at time_sec and evaluate FK or IK targets for side."""
    selected_idx, selected_seg = select_upper_limb_segment(segments, time_sec)
    hand_target, side_fk = _evaluate_upper_limb_segment(
        selected_seg,
        side,
        time_sec,
        root_position,
        root_yaw_deg,
    )
    return selected_idx, selected_seg, hand_target, side_fk
