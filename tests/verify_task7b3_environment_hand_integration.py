"""TASK 7B-3 — Environmental Target Integration into Upper-Limb Production Pipeline (T01–T20).

Proves that live Mesh query targets from ``output/dynamics_playground.blend`` drive
continuous, independent bilateral upper-limb IK motion on the 19-bone character
across the complete, unmodified production pipeline:

    DynamicsEnvironmentQuery.query_spatial_surface()
        -> compute_hand_target_from_surface()
        -> UpperLimbSegment (mode="IK", position_space="WORLD", clamp_reach=False)
        -> MotionPlanner.execute()
        -> MotionRuntimeContext.compose_planned_pose()
        -> KinematicBridgeExecutor.execute_frame()
        -> WholeBodyController.execute_frame()
        -> Existing Arm IK/FK + JointModel ROM
        -> Evaluated Armature PoseBones & MotionState

Scope & Boundaries:
- Production ``src/`` is 100% read-only; zero new production functions, classes, or controllers.
- Controlled in-memory obstacle placement near ``Surface_FlatGround`` provides real foot ground
  support while querying real obstacle Mesh geometry; ``output/dynamics_playground.blend`` is
  never saved or modified on disk, and relocated tests do not claim full obstacle-course parkour.
- Maintains ``contact_intent=False`` and ``is_locked=False`` (no hand support/grasp/load-bearing).
- Componentwise Euler segment interpolation is evaluated truthfully as componentwise Euler
  interpolation avoiding ``+-180 deg`` branch cuts (never claimed to be general SO(3) slerp).

Intended execution (strictly after ChatGPT independent Diff review authorization):
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b --factory-startup --python-exit-code 1 --python tests/verify_task7b3_environment_hand_integration.py -- --failfast
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
import sys
import unittest
from uuid import uuid4
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.config import PipelineConfig
import src.motion.contact_model as contact_model_mod
from src.motion.contact_model import (
    DEFAULT_LIMB_LOCAL_ANCHORS,
    ContactLifecycle,
    ContactType,
    SupportType,
    compute_hand_target_from_surface,
)
from src.motion.framework import (
    BlenderPoseApplicator,
    ContactConstraintAdapter,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
)
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import (
    UpperLimbSegment,
    _evaluate_upper_limb_progress,
    validate_upper_limb_segment_sequence,
)
import src.motion.whole_body_controller as wbc_mod
from src.motion.whole_body_controller import WholeBodyController
from src.rig.arm_ik import (
    ARM_IK_TARGET_NAMES,
    FOREARM_LENGTH,
    HAND_LENGTH,
    MAX_ARM_REACH,
    MIN_ARM_REACH,
    UPPER_ARM_LENGTH,
)
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, IK_TARGET_NAMES
from src.scene.blender_mesh_query_adapter import create_mesh_backed_dynamics_query
from src.scene.environment_query import DynamicsEnvironmentQuery, SurfaceQueryResult
from src.scene.playground_character_assembly import assemble_character_in_playground

PLAYGROUND_BLEND = os.path.join(REPO_ROOT, "output", "dynamics_playground.blend")

# Inherit existing WholeBodyController default acceptance tolerances (Section 10)
WBC_POS_TOL_M: float = 0.005
WBC_ROT_TOL_DEG: float = 1.0
RIGID_MAT_TOL: float = 1e-4
IDENTITY_MAT_TOL: float = 1e-6

# Controlled in-memory obstacle relocations onto Surface_FlatGround (X in [-10, 10], Y in [-10, 5], Z=0.0)
# Character stands at (0.0, -8.00, 0.0) with feet at (-0.11, -8.00, 0.0) and (+0.11, -8.00, 0.0):
# - Left obstacle: Surface_Ramp_TopPlatform (local X[-3,3], Y[16,18], Z[0, 1.339746])
#   shifted by (-3.05, -23.68, 0.0) -> world X[-6.05, -0.05], Y[-7.68, -5.68], Z_top=1.339746m.
# - Right obstacle: Surface_VerticalWall (local X[-3,3], Y[23.8,24.2], Z[0, 2.50])
#   shifted by (+3.05, -31.42, 0.0) -> world X[+0.05, +6.05], Y[-7.62, -7.22], Z[0, 2.50]m.
LEFT_PLATFORM_OBJ_NAME = "Surface_Ramp_TopPlatform"
RIGHT_WALL_OBJ_NAME = "Surface_VerticalWall"
CROSSBAR_OBJ_NAME = "Surface_LedgeBar_Crossbar"

LEFT_PLATFORM_RELOC = (-3.05, -23.68, 0.0)
RIGHT_WALL_RELOC = (3.05, -31.42, 0.0)

STAND_START_FRAMES = 8
STAND_STOP_FRAMES = 8
STANDING_TOTAL_FRAMES = STAND_START_FRAMES + STAND_STOP_FRAMES  # 16 frames (0.625s @ 24 FPS)


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _sha256_file
# PURPOSE: Compute SHA-256 hex digest of a binary file on disk without modifying it.
# REASON: TASK 7B-3 (T20) — Verify byte-level immutability of output/dynamics_playground.blend before and after all integration runs.
def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _palm_error_bound_m
# PURPOSE: Compute exact Section 10 palm anchor world position error bound 0.005 + 2*||local_anchor||*sin(0.5 deg) + 1e-5.
# REASON: TASK 7B-3 (T06, T08, T09, T10) — Propagate WBC 5mm wrist tolerance and 1 deg SO(3) orientation tolerance through DEFAULT_LIMB_LOCAL_ANCHORS without ad-hoc loosening.
def _palm_error_bound_m(side: str) -> float:
    local_anchor = Vector(DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"])
    return WBC_POS_TOL_M + 2.0 * float(local_anchor.length) * math.sin(math.radians(0.5)) + 1e-5


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _matrix_from_euler_deg
# PURPOSE: Convert 'XYZ' Euler angles in degrees into a 3x3 rotation Matrix.
# REASON: TASK 7B-3 (T05, T06, T07) — Reconstruct target SO(3) orientation matrices without comparing raw Euler components.
def _matrix_from_euler_deg(rot_deg: Sequence[float]) -> Matrix:
    return Euler(
        (
            math.radians(float(rot_deg[0])),
            math.radians(float(rot_deg[1])),
            math.radians(float(rot_deg[2])),
        ),
        "XYZ",
    ).to_matrix()


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _max_matrix_diff
# PURPOSE: Compute maximum entrywise absolute difference between two matrices of equal dimensions.
# REASON: TASK 7B-3 (T06, T08, T09, T10) — Check initial identity transforms and unit-scale rigid orthogonality of evaluated hand bone matrices.
def _max_matrix_diff(mat_a: Matrix, mat_b: Matrix) -> float:
    rows = len(mat_a)
    cols = len(mat_a[0])
    return max(abs(float(mat_a[r][c]) - float(mat_b[r][c])) for r in range(rows) for c in range(cols))


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _so3_angle_diff_deg
# PURPOSE: Compute geodesic SO(3) rotation difference angle in degrees between two 3x3 rotation matrices.
# REASON: TASK 7B-3 (Section 10, T05, T07, T09, T10) — Measure orientation tracking error strictly via SO(3) rotation difference rather than Euler subtraction.
def _so3_angle_diff_deg(mat_a: Matrix, mat_b: Matrix) -> float:
    quat_a: Quaternion = mat_a.to_quaternion().normalized()
    quat_b: Quaternion = mat_b.to_quaternion().normalized()
    dot_abs = min(1.0, max(0.0, abs(float(quat_a.dot(quat_b)))))
    return math.degrees(2.0 * math.acos(dot_abs))


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _unit_vector_angle_deg
# PURPOSE: Compute angular separation in degrees between two non-zero 3D vectors.
# REASON: TASK 7B-3 (T07, T10) — Verify actual hand bone outward normal (col_z) and projected surface tangent (col_y) alignment <= 1.0 deg.
def _unit_vector_angle_deg(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    ua = Vector(vec_a).normalized()
    ub = Vector(vec_b).normalized()
    cos_val = max(-1.0, min(1.0, float(ua.dot(ub))))
    return math.degrees(math.acos(cos_val))


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _expected_surface_tangent
# PURPOSE: Project tangent_hint_world onto the plane orthogonal to surface_normal_world and normalize.
# REASON: TASK 7B-3 (T07, T10) — Compute reference unit tangent vector on the queried surface for evaluated bone basis comparison.
def _expected_surface_tangent(
    surface_normal_world: Sequence[float],
    tangent_hint_world: Sequence[float],
) -> Tuple[float, float, float]:
    n_unit = Vector(surface_normal_world).normalized()
    t_raw = Vector(tangent_hint_world)
    t_proj = (t_raw - t_raw.dot(n_unit) * n_unit).normalized()
    return (float(t_proj.x), float(t_proj.y), float(t_proj.z))


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _assert_unit_scale_rigid_4x4
# PURPOSE: Verify that a 4x4 world matrix has an orthonormal right-handed 3x3 rotation block (det == +1) before applying Section 10's palm bound.
# REASON: TASK 7B-3 (Section 10, T06) — Enforce unit-scale rigid bone matrix precondition required for palm error propagation bound.
def _assert_unit_scale_rigid_4x4(tc: unittest.TestCase, mat4: Matrix, label: str) -> Matrix:
    rot3 = mat4.to_3x3()
    ortho_err = _max_matrix_diff(rot3.transposed() @ rot3, Matrix.Identity(3))
    det_err = abs(float(rot3.determinant()) - 1.0)
    tc.assertLessEqual(
        ortho_err,
        RIGID_MAT_TOL,
        f"{label} 3x3 block violates unit-scale orthogonality: ortho_err={ortho_err:.3e}",
    )
    tc.assertLessEqual(
        det_err,
        RIGID_MAT_TOL,
        f"{label} 3x3 block violates right-handed determinant=1: det_err={det_err:.3e}",
    )
    return rot3


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# CLASS: _FrameTelemetrySnapshot
# PURPOSE: Immutable per-frame read-only observation captured immediately after KinematicBridgeExecutor.execute_frame() evaluates the scene.
# REASON: TASK 7B-3 (Section 10, T01–T10, T16–T20) — Preserve exact unrounded evaluated bone matrices, wrist/palm coordinates, ROM status, reachability, and contact states at every executed frame without re-running scenes.
@dataclass(frozen=True)
class _FrameTelemetrySnapshot:
    frame: int
    time_sec: float
    root_world: Tuple[float, float, float]
    root_yaw_deg: float
    planned_hand_L: Optional[Dict[str, Any]]
    planned_hand_R: Optional[Dict[str, Any]]
    shoulder_world_L: Tuple[float, float, float]
    shoulder_world_R: Tuple[float, float, float]
    actual_wrist_L: Tuple[float, float, float]
    actual_wrist_R: Tuple[float, float, float]
    actual_palm_L: Tuple[float, float, float]
    actual_palm_R: Tuple[float, float, float]
    actual_hand_rot_deg_L: Tuple[float, float, float]
    actual_hand_rot_deg_R: Tuple[float, float, float]
    hand_matrix_world_L: Matrix
    hand_matrix_world_R: Matrix
    arm_lengths_L: Tuple[float, float, float]
    arm_lengths_R: Tuple[float, float, float]
    fk_pose_euler_deg: Dict[str, Tuple[float, float, float]]
    ankle_world_L: Tuple[float, float, float]
    ankle_world_R: Tuple[float, float, float]
    foot_locked_L: bool
    foot_locked_R: bool
    hand_ik_custom_locked_L: bool
    hand_ik_custom_locked_R: bool
    bridge_success: bool
    wbc_success: bool
    rom_valid: bool
    rom_violations: Dict[str, Any]
    is_all_reachable: bool
    eff_feedback: Dict[str, Any]
    unmet_constraints: Tuple[Any, ...]
    support_type: str
    active_contacts: Tuple[str, ...]
    supporting_limbs: Tuple[str, ...]
    effective_contacts: Tuple[str, ...]
    hand_contact_L: Tuple[str, str]
    hand_contact_R: Tuple[str, str]
    motion_state_contacts: Dict[str, Any]


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _pack_planned_hand
# PURPOSE: Extract pure-Python immutable fields from an optional PlannedHandTarget without mutating it.
# REASON: TASK 7B-3 (T04, T05, T06, T08, T16, T20) — Preserve exact unrounded per-frame planned hand target values across scene reloads.
def _pack_planned_hand(ht: Any) -> Optional[Dict[str, Any]]:
    if ht is None:
        return None
    return {
        "enabled": bool(ht.enabled),
        "world_xyz": tuple(float(v) for v in ht.world_xyz),
        "rotation_deg": (
            tuple(float(v) for v in ht.rotation_deg)
            if ht.rotation_deg is not None
            else None
        ),
        "pole_hint_world_xyz": (
            tuple(float(v) for v in ht.pole_hint_world_xyz)
            if ht.pole_hint_world_xyz is not None
            else None
        ),
        "contact_intent": bool(ht.contact_intent),
        "is_locked": bool(ht.is_locked),
        "clamp_reach": bool(ht.clamp_reach),
        "contact_type": ht.contact_type.value,
    }


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# CLASS: _PipelineReadOnlyObserver
# PURPOSE: Non-intrusive context manager recording real call counts and read-only per-frame snapshots across the 7B-3 authoritative production chain, restoring all originals in __exit__.
# REASON: TASK 7B-3 (Section 8, T01, T19) — Observe true production call sequence and raw feedback objects while forwarding exact arguments, returning exact results, and never swallowing exceptions.
class _PipelineReadOnlyObserver:
    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: _PipelineReadOnlyObserver.__init__
    # PURPOSE: Initialize zeroed call counters, invocation order log, and per-frame snapshot list.
    # REASON: TASK 7B-3 (T01, T19) — Track read-only pipeline telemetry per execution run.
    def __init__(self, query_instance: DynamicsEnvironmentQuery) -> None:
        self._query_instance = query_instance
        self.counts: Dict[str, int] = {
            "query_spatial_surface": 0,
            "compute_hand_target_from_surface": 0,
            "planner_execute": 0,
            "compose_planned_pose": 0,
            "bridge_execute_frame": 0,
            "wbc_execute_frame": 0,
            "set_hand_ik_target": 0,
            "set_arm_ik_influence": 0,
        }
        self.call_order: List[str] = []
        self.frame_snapshots: List[_FrameTelemetrySnapshot] = []
        self.last_bridge_result: Optional[Any] = None
        self.last_wbc_result: Optional[Any] = None
        self._orig: Dict[str, Any] = {}

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: _PipelineReadOnlyObserver.__enter__
    # PURPOSE: Install transparent forwarding wrappers on authoritative pipeline entrypoints that record read-only observations and return unmodified production outputs.
    # REASON: TASK 7B-3 (Section 8, T01, T19) — Capture per-frame evaluated bone matrices and exact call counts without mocking or altering execution semantics.
    def __enter__(self) -> "_PipelineReadOnlyObserver":
        obs = self
        run_id = uuid4().hex
        self._orig["query_cls_spatial"] = DynamicsEnvironmentQuery.query_spatial_surface
        self._orig["compute_hand_target"] = contact_model_mod.compute_hand_target_from_surface
        self._orig["planner_execute"] = MotionPlanner.execute
        self._orig["compose_planned_pose"] = MotionRuntimeContext.compose_planned_pose
        self._orig["bridge_execute_frame"] = KinematicBridgeExecutor.execute_frame
        self._orig["wbc_execute_frame"] = WholeBodyController.execute_frame
        self._orig["wbc_set_hand_ik"] = wbc_mod.set_hand_ik_target
        self._orig["wbc_set_arm_inf"] = wbc_mod.set_arm_ik_influence

        orig_query = self._orig["query_cls_spatial"]
        orig_convert = self._orig["compute_hand_target"]
        orig_planner_exec = self._orig["planner_execute"]
        orig_compose = self._orig["compose_planned_pose"]
        orig_bridge_exec = self._orig["bridge_execute_frame"]
        orig_wbc_exec = self._orig["wbc_execute_frame"]
        orig_set_ik = self._orig["wbc_set_hand_ik"]
        orig_set_inf = self._orig["wbc_set_arm_inf"]

        # Read-only pass-through spies: forward exact (*args, **kwargs) and return exact original result
        def _spy_query(q_self: Any, *args: Any, **kwargs: Any) -> Any:
            if q_self is obs._query_instance:
                obs.counts["query_spatial_surface"] += 1
                obs.call_order.append("query_spatial_surface")
            return orig_query(q_self, *args, **kwargs)

        def _spy_convert(*args: Any, **kwargs: Any) -> Any:
            obs.counts["compute_hand_target_from_surface"] += 1
            obs.call_order.append("compute_hand_target_from_surface")
            return orig_convert(*args, **kwargs)

        def _spy_planner_exec(p_self: Any, *args: Any, **kwargs: Any) -> Any:
            obs.counts["planner_execute"] += 1
            obs.call_order.append("planner_execute")
            return orig_planner_exec(p_self, *args, **kwargs)

        def _spy_compose(ctx_self: Any, *args: Any, **kwargs: Any) -> Any:
            obs.counts["compose_planned_pose"] += 1
            obs.call_order.append("compose_planned_pose")
            return orig_compose(ctx_self, *args, **kwargs)

        def _spy_wbc_exec(w_self: Any, *args: Any, **kwargs: Any) -> Any:
            obs.counts["wbc_execute_frame"] += 1
            obs.call_order.append("wbc_execute_frame")
            res = orig_wbc_exec(w_self, *args, **kwargs)
            obs.last_wbc_result = res
            return res

        def _spy_set_ik(*args: Any, **kwargs: Any) -> Any:
            obs.counts["set_hand_ik_target"] += 1
            obs.call_order.append("set_hand_ik_target")
            return orig_set_ik(*args, **kwargs)

        def _spy_set_inf(*args: Any, **kwargs: Any) -> Any:
            obs.counts["set_arm_ik_influence"] += 1
            obs.call_order.append("set_arm_ik_influence")
            return orig_set_inf(*args, **kwargs)

        def _spy_bridge_exec(b_self: Any, *args: Any, **kwargs: Any) -> Any:
            obs.counts["bridge_execute_frame"] += 1
            obs.call_order.append("bridge_execute_frame")
            planned = args[0] if args else kwargs.get("planned")
            res = orig_bridge_exec(b_self, *args, **kwargs)
            obs.last_bridge_result = res
            arm = b_self.armature_obj
            root = b_self.root_obj

            p_up_l = arm.pose.bones["upper_arm.L"]
            p_fore_l = arm.pose.bones["forearm.L"]
            p_hand_l = arm.pose.bones["hand.L"]
            p_up_r = arm.pose.bones["upper_arm.R"]
            p_fore_r = arm.pose.bones["forearm.R"]
            p_hand_r = arm.pose.bones["hand.R"]

            sh_l = arm.matrix_world @ p_up_l.head
            el_l = arm.matrix_world @ p_fore_l.head
            wr_l = arm.matrix_world @ p_hand_l.head
            tip_l = arm.matrix_world @ p_hand_l.tail

            sh_r = arm.matrix_world @ p_up_r.head
            el_r = arm.matrix_world @ p_fore_r.head
            wr_r = arm.matrix_world @ p_hand_r.head
            tip_r = arm.matrix_world @ p_hand_r.tail

            hmat_l = (arm.matrix_world @ p_hand_l.matrix).copy()
            hmat_r = (arm.matrix_world @ p_hand_r.matrix).copy()
            palm_l = hmat_l @ Vector(DEFAULT_LIMB_LOCAL_ANCHORS["hand_L"])
            palm_r = hmat_r @ Vector(DEFAULT_LIMB_LOCAL_ANCHORS["hand_R"])
            hrot_l = tuple(math.degrees(a) for a in hmat_l.to_3x3().to_euler("XYZ"))
            hrot_r = tuple(math.degrees(a) for a in hmat_r.to_3x3().to_euler("XYZ"))

            tracked_bones = (
                "pelvis",
                "spine",
                "neck",
                "head",
                "upper_arm.L",
                "forearm.L",
                "hand.L",
                "upper_arm.R",
                "forearm.R",
                "hand.R",
            )
            fk_pose_deg: Dict[str, Tuple[float, float, float]] = {}
            for b_name in tracked_bones:
                pb = arm.pose.bones[b_name]
                fk_pose_deg[b_name] = tuple(math.degrees(float(v)) for v in pb.rotation_euler)

            p_foot_l = arm.pose.bones["foot.L"]
            p_foot_r = arm.pose.bones["foot.R"]
            ankle_l = (arm.matrix_world @ p_foot_l.head).to_tuple()
            ankle_r = (arm.matrix_world @ p_foot_r.head).to_tuple()
            foot_ik_l = bpy.data.objects.get(IK_TARGET_NAMES["L"])
            foot_ik_r = bpy.data.objects.get(IK_TARGET_NAMES["R"])
            hand_ik_l = bpy.data.objects.get(ARM_IK_TARGET_NAMES["L"])
            hand_ik_r = bpy.data.objects.get(ARM_IK_TARGET_NAMES["R"])

            mc = res.multi_contact
            rec_hl = mc.contacts.get("hand_L") if mc is not None else None
            rec_hr = mc.contacts.get("hand_R") if mc is not None else None

            obs.frame_snapshots.append(
                _FrameTelemetrySnapshot(
                    frame=int(res.frame),
                    time_sec=float(planned.time_seconds) if planned is not None else 0.0,
                    root_world=(
                        tuple(float(v) for v in root.matrix_world.translation)
                        if root is not None
                        else (0.0, 0.0, 0.0)
                    ),
                    root_yaw_deg=(
                        math.degrees(float(root.matrix_world.to_euler("XYZ").z))
                        if root is not None
                        else 0.0
                    ),
                    planned_hand_L=_pack_planned_hand(planned.hand_L) if planned is not None else None,
                    planned_hand_R=_pack_planned_hand(planned.hand_R) if planned is not None else None,
                    shoulder_world_L=(float(sh_l.x), float(sh_l.y), float(sh_l.z)),
                    shoulder_world_R=(float(sh_r.x), float(sh_r.y), float(sh_r.z)),
                    actual_wrist_L=(float(wr_l.x), float(wr_l.y), float(wr_l.z)),
                    actual_wrist_R=(float(wr_r.x), float(wr_r.y), float(wr_r.z)),
                    actual_palm_L=(float(palm_l.x), float(palm_l.y), float(palm_l.z)),
                    actual_palm_R=(float(palm_r.x), float(palm_r.y), float(palm_r.z)),
                    actual_hand_rot_deg_L=hrot_l,
                    actual_hand_rot_deg_R=hrot_r,
                    hand_matrix_world_L=hmat_l,
                    hand_matrix_world_R=hmat_r,
                    arm_lengths_L=(
                        float((el_l - sh_l).length),
                        float((wr_l - el_l).length),
                        float((tip_l - wr_l).length),
                    ),
                    arm_lengths_R=(
                        float((el_r - sh_r).length),
                        float((wr_r - el_r).length),
                        float((tip_r - wr_r).length),
                    ),
                    fk_pose_euler_deg=fk_pose_deg,
                    ankle_world_L=(float(ankle_l[0]), float(ankle_l[1]), float(ankle_l[2])),
                    ankle_world_R=(float(ankle_r[0]), float(ankle_r[1]), float(ankle_r[2])),
                    foot_locked_L=bool(foot_ik_l.get("is_locked", False)) if foot_ik_l is not None else False,
                    foot_locked_R=bool(foot_ik_r.get("is_locked", False)) if foot_ik_r is not None else False,
                    hand_ik_custom_locked_L=bool(hand_ik_l.get("is_locked", False)) if hand_ik_l is not None else False,
                    hand_ik_custom_locked_R=bool(hand_ik_r.get("is_locked", False)) if hand_ik_r is not None else False,
                    bridge_success=bool(res.success),
                    wbc_success=bool(res.wbc_result.success),
                    rom_valid=bool(res.wbc_result.rom_validation.is_valid),
                    rom_violations=dict(res.wbc_result.rom_validation.violations),
                    is_all_reachable=bool(res.wbc_result.is_all_reachable),
                    eff_feedback=dict(res.wbc_result.end_effectors),
                    unmet_constraints=tuple(res.unmet_constraints),
                    support_type=str(res.support_type),
                    active_contacts=tuple(mc.active_contacts.keys()) if mc is not None else (),
                    supporting_limbs=tuple(mc.supporting_limbs) if mc is not None else (),
                    effective_contacts=tuple(mc.effective_contacts.keys()) if mc is not None else (),
                    hand_contact_L=(
                        rec_hl.contact_type.value if rec_hl is not None else "none",
                        rec_hl.lifecycle.value if rec_hl is not None else "none",
                    ),
                    hand_contact_R=(
                        rec_hr.contact_type.value if rec_hr is not None else "none",
                        rec_hr.lifecycle.value if rec_hr is not None else "none",
                    ),
                    motion_state_contacts=(
                        {k: v.to_dict() for k, v in res.motion_state.contacts.items()}
                        if res.motion_state is not None
                        else {}
                    ),
                )
            )
            # [INTRODUCED 2026-11-28T15:40:19+08:00]
            # FUNCTION: _PipelineReadOnlyObserver.__enter__._spy_bridge_exec
            # PURPOSE: Emit one structured evidence record from the captured Bridge frame snapshot.
            # REASON: TASK 7B-3 evidence output — correlate frames by observer run ID for independent review.
            snapshot = obs.frame_snapshots[-1]
            evidence = {
                **vars(snapshot),
                "event": "task_7b_3_bridge_frame",
                "run_id": run_id,
                "hand_matrix_world_L": [tuple(row) for row in snapshot.hand_matrix_world_L],
                "hand_matrix_world_R": [tuple(row) for row in snapshot.hand_matrix_world_R],
                "rom_violations": {
                    bone: asdict(violation) for bone, violation in snapshot.rom_violations.items()
                },
                "eff_feedback": {
                    limb: asdict(feedback) for limb, feedback in snapshot.eff_feedback.items()
                },
                "unmet_constraints": [
                    asdict(constraint) for constraint in snapshot.unmet_constraints
                ],
            }
            print(json.dumps(evidence, ensure_ascii=True), flush=True)
            return res

        DynamicsEnvironmentQuery.query_spatial_surface = _spy_query  # type: ignore[method-assign]
        contact_model_mod.compute_hand_target_from_surface = _spy_convert  # type: ignore[assignment]
        MotionPlanner.execute = _spy_planner_exec  # type: ignore[method-assign]
        MotionRuntimeContext.compose_planned_pose = _spy_compose  # type: ignore[method-assign]
        KinematicBridgeExecutor.execute_frame = _spy_bridge_exec  # type: ignore[method-assign]
        WholeBodyController.execute_frame = _spy_wbc_exec  # type: ignore[method-assign]
        wbc_mod.set_hand_ik_target = _spy_set_ik  # type: ignore[assignment]
        wbc_mod.set_arm_ik_influence = _spy_set_inf  # type: ignore[assignment]
        return self

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: _PipelineReadOnlyObserver.__exit__
    # PURPOSE: Unconditionally restore all original production methods and module attributes in finally.
    # REASON: TASK 7B-3 (Section 8) — Guarantee zero residual observer state even when negative tests raise expected exceptions.
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        try:
            DynamicsEnvironmentQuery.query_spatial_surface = self._orig["query_cls_spatial"]  # type: ignore[method-assign]
            contact_model_mod.compute_hand_target_from_surface = self._orig["compute_hand_target"]  # type: ignore[assignment]
            MotionPlanner.execute = self._orig["planner_execute"]  # type: ignore[method-assign]
            MotionRuntimeContext.compose_planned_pose = self._orig["compose_planned_pose"]  # type: ignore[method-assign]
            KinematicBridgeExecutor.execute_frame = self._orig["bridge_execute_frame"]  # type: ignore[method-assign]
            WholeBodyController.execute_frame = self._orig["wbc_execute_frame"]  # type: ignore[method-assign]
            wbc_mod.set_hand_ik_target = self._orig["wbc_set_hand_ik"]  # type: ignore[assignment]
            wbc_mod.set_arm_ik_influence = self._orig["wbc_set_arm_inf"]  # type: ignore[assignment]
        finally:
            self._orig.clear()
        return False


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _assert_observers_restored
# PURPOSE: Verify all production module/class entrypoints match their original unwrapped functions.
# REASON: TASK 7B-3 (Section 8) — Guarantee zero residual monkey-patching across test boundaries.
def _assert_observers_restored(tc: unittest.TestCase) -> None:
    tc.assertIs(
        contact_model_mod.compute_hand_target_from_surface,
        compute_hand_target_from_surface,
    )
    tc.assertEqual(DynamicsEnvironmentQuery.query_spatial_surface.__name__, "query_spatial_surface")
    tc.assertEqual(MotionPlanner.execute.__name__, "execute")
    tc.assertEqual(MotionRuntimeContext.compose_planned_pose.__name__, "compose_planned_pose")
    tc.assertEqual(KinematicBridgeExecutor.execute_frame.__name__, "execute_frame")
    tc.assertEqual(WholeBodyController.execute_frame.__name__, "execute_frame")
    tc.assertEqual(wbc_mod.set_hand_ik_target.__name__, "set_hand_ik_target")
    tc.assertEqual(wbc_mod.set_arm_ik_influence.__name__, "set_arm_ik_influence")


MappingType = Optional[Dict[str, Matrix]]


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _prepare_controlled_playground_scene
# PURPOSE: Open output/dynamics_playground.blend read-only, verify initial Identity(4) obstacle transforms, apply controlled in-memory obstacle translations onto Surface_FlatGround, assemble the 19-bone character, and build the mesh-backed DynamicsEnvironmentQuery.
# REASON: TASK 7B-3 (Section 6) — Establish real foot support on Surface_FlatGround alongside real obstacle Mesh targets without adding ground, altering Mesh topology, or saving over source .blend.
def _prepare_controlled_playground_scene(
    obstacle_transforms: MappingType = None,
) -> Dict[str, Any]:
    if not os.path.isfile(PLAYGROUND_BLEND):
        raise FileNotFoundError(f"Authoritative playground blend missing: {PLAYGROUND_BLEND}")

    bpy.ops.wm.open_mainfile(filepath=PLAYGROUND_BLEND)
    bpy.context.view_layer.update()

    transforms_to_apply: Dict[str, Matrix] = {}
    if obstacle_transforms is None:
        transforms_to_apply[LEFT_PLATFORM_OBJ_NAME] = Matrix.Translation(Vector(LEFT_PLATFORM_RELOC))
        transforms_to_apply[RIGHT_WALL_OBJ_NAME] = Matrix.Translation(Vector(RIGHT_WALL_RELOC))
    else:
        for obj_name, mat_val in obstacle_transforms.items():
            transforms_to_apply[str(obj_name)] = mat_val.copy()

    initial_matrices: Dict[str, Matrix] = {}
    applied_matrices: Dict[str, Matrix] = {}
    for obj_name, target_mat in transforms_to_apply.items():
        env_obj = bpy.data.objects.get(obj_name)
        if env_obj is None:
            raise RuntimeError(f"Required playground obstacle object missing: {obj_name!r}")
        init_mat = env_obj.matrix_world.copy()
        init_diff = _max_matrix_diff(init_mat, Matrix.Identity(4))
        if init_diff > IDENTITY_MAT_TOL:
            raise RuntimeError(
                f"Precondition failed: {obj_name!r} initial matrix_world is not Identity(4) "
                f"(max_diff={init_diff:.3e} > {IDENTITY_MAT_TOL})"
            )
        initial_matrices[obj_name] = init_mat
        env_obj.matrix_world = target_mat.copy()
        applied_matrices[obj_name] = target_mat.copy()

    bpy.context.view_layer.update()

    cfg = PipelineConfig()
    assembly = assemble_character_in_playground(cfg)
    query = create_mesh_backed_dynamics_query(
        scene=bpy.context.scene,
        collection_names=("Playground_Surfaces",),
        prefer_mesh=True,
        ground_z=0.0,
    )
    arm_objs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    return {
        "config": cfg,
        "assembly": assembly,
        "armature": assembly["armature"],
        "root": assembly["root"],
        "query": query,
        "armature_count": len(arm_objs),
        "armature_names": [o.name for o in arm_objs],
        "initial_obstacle_matrices": initial_matrices,
        "applied_obstacle_matrices": applied_matrices,
    }


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _make_standing_route
# PURPOSE: Build a stationary TerrainRouteInput on Surface_FlatGround (start_pos == target_pos) reusing TerrainWalkAction's standing-in-place branch.
# REASON: TASK 7B-3 (Section 6) — Exercise full lower-limb ground support and locked stance feet without inventing custom test actions.
def _make_standing_route(
    start_pos: Tuple[float, float, float] = (0.0, -8.0, 0.0),
    stand_start_frames: int = STAND_START_FRAMES,
    stand_stop_frames: int = STAND_STOP_FRAMES,
) -> TerrainRouteInput:
    return TerrainRouteInput(
        start_pos=start_pos,
        target_pos=start_pos,
        stand_start_frames=stand_start_frames,
        stand_stop_frames=stand_stop_frames,
    )


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _compute_ready_start_pose_from_shoulder
# PURPOSE: Derive a deterministic, anatomically comfortable ready start wrist, rotation, and olecranon pole hint strictly from the actual evaluated shoulder bone world position.
# REASON: TASK 7B-3 (Section 7) — Ensure start pose uses live shoulder bone coordinates (never static rest height), stays well inside [MIN_ARM_REACH, MAX_ARM_REACH] and JointModel ROM, and pairs cleanly with surface end rotations without crossing +-180 deg Euler branch cuts.
def _compute_ready_start_pose_from_shoulder(
    side: str,
    shoulder_world: Tuple[float, float, float],
    *,
    start_pitch_deg: float,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    sign = -1.0 if side == "L" else 1.0
    sx, sy, sz = shoulder_world
    wrist_start = (sx, sy + 0.28, sz - 0.24)
    rot_start = (float(start_pitch_deg), 0.0, 0.0)
    pole_hint = (sx + sign * 0.03, sy - 0.25, sz - 0.45)
    return wrist_start, rot_start, pole_hint


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _build_ik_reach_segment
# PURPOSE: Construct an immutable UpperLimbSegment with mode="IK", position_space="WORLD", clamp_reach=False, paired finite rotations, and anatomical pole hints.
# REASON: TASK 7B-3 (Section 7) — Enforce mandatory Task 7B-3 segment contract across all positive and negative integration tests.
def _build_ik_reach_segment(
    *,
    start_time_sec: float,
    duration_sec: float,
    wrist_start_xyz: Tuple[float, float, float],
    wrist_end_xyz: Tuple[float, float, float],
    rotation_start_deg: Tuple[float, float, float],
    rotation_end_deg: Tuple[float, float, float],
    pole_start_xyz: Tuple[float, float, float],
    pole_end_xyz: Tuple[float, float, float],
) -> Tuple[UpperLimbSegment, ...]:
    return (
        UpperLimbSegment(
            mode="IK",
            start_time_sec=float(start_time_sec),
            duration_sec=float(duration_sec),
            wrist_start_xyz=wrist_start_xyz,
            wrist_end_xyz=wrist_end_xyz,
            rotation_start_deg=rotation_start_deg,
            rotation_end_deg=rotation_end_deg,
            pole_start_xyz=pole_start_xyz,
            pole_end_xyz=pole_end_xyz,
            position_space="WORLD",
            clamp_reach=False,
        ),
    )


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# FUNCTION: _execute_observed_standing_sequence
# PURPOSE: Execute a complete standing TerrainWalkAction sequence through MotionPlanner.execute() under _PipelineReadOnlyObserver, optionally acquiring left/right live Mesh surface targets first.
# REASON: TASK 7B-3 (Section 4, Section 9) — Provide shared read-only production evidence for T01–T07 and T16–T20 without repeating identical scene runs.
def _execute_observed_standing_sequence(
    *,
    standing_shoulder_L: Tuple[float, float, float],
    standing_shoulder_R: Tuple[float, float, float],
    left_spec: Optional[Dict[str, Any]] = None,
    right_spec: Optional[Dict[str, Any]] = None,
    start_pos: Tuple[float, float, float] = (0.0, -8.0, 0.0),
    obstacle_transforms: MappingType = None,
) -> Dict[str, Any]:
    env_ctx = _prepare_controlled_playground_scene(obstacle_transforms=obstacle_transforms)
    cfg: PipelineConfig = env_ctx["config"]
    arm = env_ctx["armature"]
    query: DynamicsEnvironmentQuery = env_ctx["query"]
    fps = float(cfg.fps)

    route = _make_standing_route(start_pos=start_pos)
    init_state = create_initial_motion_state(cfg, start_frame=1, position=start_pos)
    action = TerrainWalkAction(
        route=route,
        action_name="Task7B3_StandingReach",
        environment=query,
    )
    total_frames = action.estimate_duration_frames(init_state, cfg, query)
    sequence_duration_sec = (total_frames - 1) / fps

    anchors_before = copy.deepcopy(DEFAULT_LIMB_LOCAL_ANCHORS)

    with _PipelineReadOnlyObserver(query) as observer:
        segs_L: Optional[Tuple[UpperLimbSegment, ...]] = None
        segs_R: Optional[Tuple[UpperLimbSegment, ...]] = None
        acq_L: Optional[Dict[str, Any]] = None
        acq_R: Optional[Dict[str, Any]] = None

        if left_spec is not None:
            surf_l = query.query_spatial_surface(
                left_spec["ray_origin"],
                left_spec["ray_direction"],
                max_distance=left_spec["max_distance"],
            )
            surf_l_before = copy.deepcopy(surf_l)
            wrist_l, rot_l = contact_model_mod.compute_hand_target_from_surface(
                "L",
                surf_l,
                left_spec["tangent_hint"],
            )
            w_start_l, r_start_l, pole_l = _compute_ready_start_pose_from_shoulder(
                "L",
                standing_shoulder_L,
                start_pitch_deg=left_spec["start_pitch_deg"],
            )
            segs_L = _build_ik_reach_segment(
                start_time_sec=left_spec["start_time_sec"],
                duration_sec=left_spec["duration_sec"],
                wrist_start_xyz=w_start_l,
                wrist_end_xyz=wrist_l,
                rotation_start_deg=r_start_l,
                rotation_end_deg=rot_l,
                pole_start_xyz=pole_l,
                pole_end_xyz=pole_l,
            )
            segs_l_before = copy.deepcopy(segs_L)
            acq_L = {
                "surface": surf_l,
                "surface_snapshot_before": surf_l_before,
                "tangent_hint": left_spec["tangent_hint"],
                "expected_tangent": _expected_surface_tangent(
                    surf_l.surface_normal_world, left_spec["tangent_hint"]
                ),
                "wrist_end_xyz": wrist_l,
                "rotation_end_deg": rot_l,
                "wrist_start_xyz": w_start_l,
                "rotation_start_deg": r_start_l,
                "pole_xyz": pole_l,
                "segments": segs_L,
                "segments_snapshot_before": segs_l_before,
                "start_time_sec": float(left_spec["start_time_sec"]),
                "duration_sec": float(left_spec["duration_sec"]),
            }

        if right_spec is not None:
            surf_r = query.query_spatial_surface(
                right_spec["ray_origin"],
                right_spec["ray_direction"],
                max_distance=right_spec["max_distance"],
            )
            surf_r_before = copy.deepcopy(surf_r)
            wrist_r, rot_r = contact_model_mod.compute_hand_target_from_surface(
                "R",
                surf_r,
                right_spec["tangent_hint"],
            )
            w_start_r, r_start_r, pole_r = _compute_ready_start_pose_from_shoulder(
                "R",
                standing_shoulder_R,
                start_pitch_deg=right_spec["start_pitch_deg"],
            )
            segs_R = _build_ik_reach_segment(
                start_time_sec=right_spec["start_time_sec"],
                duration_sec=right_spec["duration_sec"],
                wrist_start_xyz=w_start_r,
                wrist_end_xyz=wrist_r,
                rotation_start_deg=r_start_r,
                rotation_end_deg=rot_r,
                pole_start_xyz=pole_r,
                pole_end_xyz=pole_r,
            )
            segs_r_before = copy.deepcopy(segs_R)
            acq_R = {
                "surface": surf_r,
                "surface_snapshot_before": surf_r_before,
                "tangent_hint": right_spec["tangent_hint"],
                "expected_tangent": _expected_surface_tangent(
                    surf_r.surface_normal_world, right_spec["tangent_hint"]
                ),
                "wrist_end_xyz": wrist_r,
                "rotation_end_deg": rot_r,
                "wrist_start_xyz": w_start_r,
                "rotation_start_deg": r_start_r,
                "pole_xyz": pole_r,
                "segments": segs_R,
                "segments_snapshot_before": segs_r_before,
                "start_time_sec": float(right_spec["start_time_sec"]),
                "duration_sec": float(right_spec["duration_sec"]),
            }

        planner = MotionPlanner(
            config=cfg,
            armature_obj=arm,
            environment=query,
            upper_limb_L=segs_L,
            upper_limb_R=segs_R,
            sequence_duration_sec=(
                sequence_duration_sec if (segs_L is not None or segs_R is not None) else None
            ),
        )
        planner.add_action(action)
        planner_result = planner.execute(initial_state=init_state)

    arm_objs_after = [o.name for o in bpy.data.objects if o.type == "ARMATURE"]
    return {
        "env_ctx": env_ctx,
        "fps": fps,
        "total_frames": total_frames,
        "sequence_duration_sec": sequence_duration_sec,
        "acq_L": acq_L,
        "acq_R": acq_R,
        "planner_result": planner_result,
        "frame_snapshots": list(observer.frame_snapshots),
        "counts": dict(observer.counts),
        "call_order": list(observer.call_order),
        "anchors_before": anchors_before,
        "anchors_after": copy.deepcopy(DEFAULT_LIMB_LOCAL_ANCHORS),
        "armature_names_after": arm_objs_after,
    }


# [INTRODUCED 2026-11-28T14:40:00+08:00]
# CLASS: TestTask7B3EnvironmentHandIntegration
# PURPOSE: Fixed 20-case verification suite (T01–T20) proving live environmental Mesh target integration across the upper-limb production pipeline.
# REASON: TASK 7B-3 — Validate end-to-end environmental target acquisition, wrist/palm conversion, trajectory interpolation, WBC IK/ROM execution, spatial covariance, perturbation re-planning, and truthful negative failure reporting.
class TestTask7B3EnvironmentHandIntegration(unittest.TestCase):
    _initial_blend_sha256: str = ""
    run_baseline_fk: Dict[str, Any] = {}
    run_left_ik: Dict[str, Any] = {}
    run_right_ik: Dict[str, Any] = {}
    run_bilateral_ik: Dict[str, Any] = {}
    standing_shoulder_L: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    standing_shoulder_R: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.setUpClass
    # PURPOSE: Record source .blend SHA-256 and execute the shared read-only production runs (historical FK baseline, Left IK, Right IK, Bilateral IK) once for T01–T07 and T16–T20.
    # REASON: TASK 7B-3 (Section 9) — Share read-only evidence from real production runs without redundantly re-running identical scenes.
    @classmethod
    def setUpClass(cls) -> None:
        if not os.path.isfile(PLAYGROUND_BLEND):
            raise FileNotFoundError(f"Missing required playground asset: {PLAYGROUND_BLEND}")
        cls._initial_blend_sha256 = _sha256_file(PLAYGROUND_BLEND)
        print(
            f"[7B-3][SETUP] source_blend={PLAYGROUND_BLEND} sha256={cls._initial_blend_sha256}",
            flush=True,
        )

        # 1. Historical standing baseline (both arms historical FK) -> read true execution-state shoulder world coords
        cls.run_baseline_fk = _execute_observed_standing_sequence(
            standing_shoulder_L=(-0.24, -8.0, 1.505),
            standing_shoulder_R=(0.24, -8.0, 1.505),
            left_spec=None,
            right_spec=None,
        )
        first_base_snap: _FrameTelemetrySnapshot = cls.run_baseline_fk["frame_snapshots"][0]
        cls.standing_shoulder_L = first_base_snap.shoulder_world_L
        cls.standing_shoulder_R = first_base_snap.shoulder_world_R
        fps = float(cls.run_baseline_fk["fps"])
        print(
            f"[7B-3][SETUP] evaluated_standing_shoulder_L={cls.standing_shoulder_L} "
            f"evaluated_standing_shoulder_R={cls.standing_shoulder_R} fps={fps}",
            flush=True,
        )

        left_platform_spec = {
            "ray_origin": (-0.24, -7.60, 1.85),
            "ray_direction": (0.0, 0.0, -1.0),
            "max_distance": 1.0,
            "tangent_hint": (0.0, 1.0, 0.0),
            "start_pitch_deg": 10.0,
            "start_time_sec": 2.0 / fps,
            "duration_sec": 9.0 / fps,  # frames 1..3 hold start, 4..11 transition, 12..16 hold end
        }
        right_wall_spec = {
            "ray_origin": (0.24, -7.95, 1.585),
            "ray_direction": (0.0, 1.0, 0.0),
            "max_distance": 1.0,
            "tangent_hint": (0.0, 0.0, 1.0),
            "start_pitch_deg": 35.0,
            "start_time_sec": 3.0 / fps,
            "duration_sec": 10.0 / fps,  # frames 1..4 hold start, 5..13 transition, 14..16 hold end
        }

        # 2. Left hand independent IK to relocated Surface_Ramp_TopPlatform top face; Right hand historical FK
        cls.run_left_ik = _execute_observed_standing_sequence(
            standing_shoulder_L=cls.standing_shoulder_L,
            standing_shoulder_R=cls.standing_shoulder_R,
            left_spec=left_platform_spec,
            right_spec=None,
        )

        # 3. Right hand independent IK to relocated Surface_VerticalWall front face; Left hand historical FK
        cls.run_right_ik = _execute_observed_standing_sequence(
            standing_shoulder_L=cls.standing_shoulder_L,
            standing_shoulder_R=cls.standing_shoulder_R,
            left_spec=None,
            right_spec=right_wall_spec,
        )

        # 4. Bilateral independent IK to two distinct Mesh surfaces with distinct schedules
        cls.run_bilateral_ik = _execute_observed_standing_sequence(
            standing_shoulder_L=cls.standing_shoulder_L,
            standing_shoulder_R=cls.standing_shoulder_R,
            left_spec=left_platform_spec,
            right_spec=right_wall_spec,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.tearDownClass
    # PURPOSE: Re-verify source .blend byte-level SHA-256 immutability after all 20 tests complete.
    # REASON: TASK 7B-3 (Section 6, T20) — Guarantee zero disk writes or accidental saves to output/dynamics_playground.blend.
    @classmethod
    def tearDownClass(cls) -> None:
        final_sha256 = _sha256_file(PLAYGROUND_BLEND)
        print(
            f"[7B-3][TEARDOWN] source_blend={PLAYGROUND_BLEND} sha256={final_sha256} "
            f"matches_initial={final_sha256 == cls._initial_blend_sha256}",
            flush=True,
        )
        if final_sha256 != cls._initial_blend_sha256:
            raise AssertionError(
                f"Source playground .blend mutated! initial={cls._initial_blend_sha256} final={final_sha256}"
            )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t01_real_mesh_target_through_full_central_pipeline
    # PURPOSE: T01 — Prove a live Mesh query result traverses every layer of the authoritative central production chain into evaluated bones and MotionState.
    # REASON: TASK 7B-3 T01 — Confirm end-to-end execution without bypassing query, 7B-2 conversion, UpperLimbSegment, MotionPlanner, compose_planned_pose, Bridge, WBC, or Arm IK/ROM.
    def test_t01_real_mesh_target_through_full_central_pipeline(self) -> None:
        _assert_observers_restored(self)
        run = self.run_left_ik
        acq = run["acq_L"]
        surf: SurfaceQueryResult = acq["surface"]
        res = run["planner_result"]
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
        order: List[str] = run["call_order"]

        self.assertTrue(surf.success)
        self.assertEqual(surf.source_type, "mesh")
        self.assertTrue(surf.surface_id.startswith(f"mesh:{LEFT_PLATFORM_OBJ_NAME}:"))
        self.assertNotEqual(acq["wrist_end_xyz"], surf.contact_point_world)

        self.assertTrue(res["success"])
        self.assertEqual(res["total_frames"], STANDING_TOTAL_FRAMES)
        self.assertEqual(res["central_upper_limb_enabled"], {"L": True, "R": False})
        self.assertEqual(res["unreachable_count"], 0)
        self.assertEqual(len(snaps), STANDING_TOTAL_FRAMES)

        # Verify strict causal ordering of first invocation across every production layer
        expected_chain = [
            "query_spatial_surface",
            "compute_hand_target_from_surface",
            "planner_execute",
            "compose_planned_pose",
            "bridge_execute_frame",
            "wbc_execute_frame",
            "set_hand_ik_target",
        ]
        first_indices = [order.index(step) for step in expected_chain]
        self.assertEqual(first_indices, sorted(first_indices))

        final_ms: MotionState = res["final_state"]
        self.assertEqual(final_ms.params["upper_limb_source_L"], "CENTRAL")
        self.assertEqual(final_ms.params["upper_limb_source_R"], "HISTORICAL_ACTION")
        self.assertTrue(final_ms.params["actual_upper_limb"]["L"]["enabled"])
        self.assertFalse(final_ms.params["actual_upper_limb"]["R"]["enabled"])

        final_snap = snaps[-1]
        wrist_err = (Vector(final_snap.actual_wrist_L) - Vector(acq["wrist_end_xyz"])).length
        self.assertLessEqual(wrist_err, WBC_POS_TOL_M)
        self.assertTrue(final_snap.rom_valid)
        print(
            f"[7B-3][T01] surface_id={surf.surface_id} contact_pt={surf.contact_point_world} "
            f"wrist_target={acq['wrist_end_xyz']} final_wrist={final_snap.actual_wrist_L} "
            f"wrist_err_m={wrist_err:.6f} chain_indices={first_indices}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t02_left_hand_ik_right_hand_preserves_historical_fk
    # PURPOSE: T02 — Verify independent Left-hand IK execution while Right arm preserves exact historical FK standing pose and 0.0 IK influence.
    # REASON: TASK 7B-3 T02 — Confirm unilateral Left IK does not bleed into or alter contralateral Right FK arm behavior.
    def test_t02_left_hand_ik_right_hand_preserves_historical_fk(self) -> None:
        snaps_l: List[_FrameTelemetrySnapshot] = self.run_left_ik["frame_snapshots"]
        snaps_base: List[_FrameTelemetrySnapshot] = self.run_baseline_fk["frame_snapshots"]
        records = self.run_left_ik["planner_result"]["frame_records"]
        acq_l = self.run_left_ik["acq_L"]

        max_r_wrist_diff = 0.0
        max_r_fk_diff_deg = 0.0
        for idx, (sl, sb) in enumerate(zip(snaps_l, snaps_base)):
            eff_l = sl.eff_feedback["hand_L"]
            eff_r = sl.eff_feedback["hand_R"]
            self.assertTrue(eff_l.enabled)
            self.assertFalse(eff_r.enabled)
            self.assertEqual(eff_r.weight, 0.0)
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_source_L"], "CENTRAL")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_source_R"], "HISTORICAL_ACTION")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_mode_L"], "IK")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_mode_R"], "HISTORICAL_FK")

            r_wrist_diff = (Vector(sl.actual_wrist_R) - Vector(sb.actual_wrist_R)).length
            max_r_wrist_diff = max(max_r_wrist_diff, r_wrist_diff)
            self.assertLessEqual(r_wrist_diff, 1e-6)
            for b_name in ("upper_arm.R", "forearm.R", "hand.R"):
                for a, b in zip(sl.fk_pose_euler_deg[b_name], sb.fk_pose_euler_deg[b_name]):
                    diff = abs(a - b)
                    max_r_fk_diff_deg = max(max_r_fk_diff_deg, diff)
                    self.assertLessEqual(diff, 1e-5)

        final_l_err = (Vector(snaps_l[-1].actual_wrist_L) - Vector(acq_l["wrist_end_xyz"])).length
        self.assertLessEqual(final_l_err, WBC_POS_TOL_M)
        print(
            f"[7B-3][T02] left_final_err_m={final_l_err:.6f} "
            f"right_fk_max_wrist_diff_m={max_r_wrist_diff:.3e} right_fk_max_euler_diff_deg={max_r_fk_diff_deg:.3e}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t03_right_hand_ik_left_hand_preserves_historical_fk
    # PURPOSE: T03 — Verify independent Right-hand IK execution to relocated vertical wall while Left arm preserves exact historical FK standing pose.
    # REASON: TASK 7B-3 T03 — Confirm symmetric unilateral Right IK / Left historical FK decoupling.
    def test_t03_right_hand_ik_left_hand_preserves_historical_fk(self) -> None:
        snaps_r: List[_FrameTelemetrySnapshot] = self.run_right_ik["frame_snapshots"]
        snaps_base: List[_FrameTelemetrySnapshot] = self.run_baseline_fk["frame_snapshots"]
        records = self.run_right_ik["planner_result"]["frame_records"]
        acq_r = self.run_right_ik["acq_R"]
        surf_r: SurfaceQueryResult = acq_r["surface"]

        self.assertTrue(surf_r.success)
        self.assertEqual(surf_r.source_type, "mesh")
        self.assertTrue(surf_r.surface_id.startswith(f"mesh:{RIGHT_WALL_OBJ_NAME}:"))

        max_l_wrist_diff = 0.0
        max_l_fk_diff_deg = 0.0
        for idx, (sr, sb) in enumerate(zip(snaps_r, snaps_base)):
            eff_l = sr.eff_feedback["hand_L"]
            eff_r = sr.eff_feedback["hand_R"]
            self.assertFalse(eff_l.enabled)
            self.assertEqual(eff_l.weight, 0.0)
            self.assertTrue(eff_r.enabled)
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_source_L"], "HISTORICAL_ACTION")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_source_R"], "CENTRAL")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_mode_L"], "HISTORICAL_FK")
            self.assertEqual(records[idx]["motion_planning"]["upper_limb_mode_R"], "IK")

            l_wrist_diff = (Vector(sr.actual_wrist_L) - Vector(sb.actual_wrist_L)).length
            max_l_wrist_diff = max(max_l_wrist_diff, l_wrist_diff)
            self.assertLessEqual(l_wrist_diff, 1e-6)
            for b_name in ("upper_arm.L", "forearm.L", "hand.L"):
                for a, b in zip(sr.fk_pose_euler_deg[b_name], sb.fk_pose_euler_deg[b_name]):
                    diff = abs(a - b)
                    max_l_fk_diff_deg = max(max_l_fk_diff_deg, diff)
                    self.assertLessEqual(diff, 1e-5)

        final_r_err = (Vector(snaps_r[-1].actual_wrist_R) - Vector(acq_r["wrist_end_xyz"])).length
        self.assertLessEqual(final_r_err, WBC_POS_TOL_M)
        print(
            f"[7B-3][T03] surface_id={surf_r.surface_id} right_final_err_m={final_r_err:.6f} "
            f"left_fk_max_wrist_diff_m={max_l_wrist_diff:.3e} left_fk_max_euler_diff_deg={max_l_fk_diff_deg:.3e}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t04_bilateral_distinct_surface_targets_and_independent_trajectories
    # PURPOSE: T04 — Verify simultaneous bilateral IK where Left hand targets horizontal platform top and Right hand targets vertical wall front on distinct timelines.
    # REASON: TASK 7B-3 T04 — Confirm independent bilateral spatial targets, normals, timings, and zero cross-arm interference.
    def test_t04_bilateral_distinct_surface_targets_and_independent_trajectories(self) -> None:
        run = self.run_bilateral_ik
        acq_l = run["acq_L"]
        acq_r = run["acq_R"]
        surf_l: SurfaceQueryResult = acq_l["surface"]
        surf_r: SurfaceQueryResult = acq_r["surface"]
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]

        self.assertNotEqual(surf_l.surface_id, surf_r.surface_id)
        normal_angle = _unit_vector_angle_deg(surf_l.surface_normal_world, surf_r.surface_normal_world)
        self.assertGreater(normal_angle, 85.0)
        self.assertNotAlmostEqual(acq_l["start_time_sec"], acq_r["start_time_sec"], places=4)
        self.assertNotAlmostEqual(
            acq_l["start_time_sec"] + acq_l["duration_sec"],
            acq_r["start_time_sec"] + acq_r["duration_sec"],
            places=4,
        )

        # At frame 12 (index 11, t = 11/24s): Left has arrived (t >= 11/24s), Right is still mid-transition (t < 13/24s)
        snap_f12 = snaps[11]
        l_dist_to_end_f12 = (Vector(snap_f12.planned_hand_L["world_xyz"]) - Vector(acq_l["wrist_end_xyz"])).length
        r_dist_to_end_f12 = (Vector(snap_f12.planned_hand_R["world_xyz"]) - Vector(acq_r["wrist_end_xyz"])).length
        self.assertLessEqual(l_dist_to_end_f12, 1e-7)
        self.assertGreater(r_dist_to_end_f12, 0.015)

        final_snap = snaps[-1]
        err_l = (Vector(final_snap.actual_wrist_L) - Vector(acq_l["wrist_end_xyz"])).length
        err_r = (Vector(final_snap.actual_wrist_R) - Vector(acq_r["wrist_end_xyz"])).length
        self.assertLessEqual(err_l, WBC_POS_TOL_M)
        self.assertLessEqual(err_r, WBC_POS_TOL_M)
        self.assertTrue(all(s.rom_valid and s.wbc_success and s.bridge_success for s in snaps))
        print(
            f"[7B-3][T04] surf_L={surf_l.surface_id} surf_R={surf_r.surface_id} "
            f"normal_sep_deg={normal_angle:.2f} f12_rem_L_m={l_dist_to_end_f12:.3e} "
            f"f12_rem_R_m={r_dist_to_end_f12:.4f} final_err_L_m={err_l:.6f} final_err_R_m={err_r:.6f}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t05_continuous_frame_planned_and_actual_wrist_tracking
    # PURPOSE: T05 — Verify every frame across unilateral and bilateral runs tracks quintic-interpolated planned wrist (<= 0.005m) and SO(3) orientation (<= 1.0 deg) with true bone-derived shoulder reach margins.
    # REASON: TASK 7B-3 T05 — Prove continuous per-frame tracking and reachability margins relative to actual evaluated shoulder bones.
    def test_t05_continuous_frame_planned_and_actual_wrist_tracking(self) -> None:
        for run_label, run, active_sides in (
            ("left_ik", self.run_left_ik, ("L",)),
            ("right_ik", self.run_right_ik, ("R",)),
            ("bilateral_ik", self.run_bilateral_ik, ("L", "R")),
        ):
            snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
            max_pos_err = 0.0
            max_rot_err = 0.0
            min_reach_margin = float("inf")
            for snap in snaps:
                self.assertTrue(snap.bridge_success)
                self.assertTrue(snap.wbc_success)
                self.assertTrue(snap.rom_valid)
                self.assertTrue(snap.is_all_reachable)
                for side in active_sides:
                    acq = run[f"acq_{side}"]
                    planned_hand = snap.planned_hand_L if side == "L" else snap.planned_hand_R
                    actual_wrist = snap.actual_wrist_L if side == "L" else snap.actual_wrist_R
                    actual_hmat = snap.hand_matrix_world_L if side == "L" else snap.hand_matrix_world_R
                    shoulder_w = snap.shoulder_world_L if side == "L" else snap.shoulder_world_R
                    arm_lens = snap.arm_lengths_L if side == "L" else snap.arm_lengths_R
                    eff_fb = snap.eff_feedback[f"hand_{side}"]

                    _, h = _evaluate_upper_limb_progress(
                        snap.time_sec, acq["start_time_sec"], acq["duration_sec"]
                    )
                    expected_wrist = tuple(
                        (1.0 - h) * s_v + h * e_v
                        for s_v, e_v in zip(acq["wrist_start_xyz"], acq["wrist_end_xyz"])
                    )
                    expected_rot_deg = tuple(
                        (1.0 - h) * s_a + h * e_a
                        for s_a, e_a in zip(acq["rotation_start_deg"], acq["rotation_end_deg"])
                    )
                    self.assertLessEqual(
                        (Vector(planned_hand["world_xyz"]) - Vector(expected_wrist)).length,
                        1e-7,
                    )
                    self.assertLessEqual(
                        max(abs(a - b) for a, b in zip(planned_hand["rotation_deg"], expected_rot_deg)),
                        1e-6,
                    )

                    # Reachability measured strictly against live evaluated shoulder bone world position
                    live_req_dist = (Vector(expected_wrist) - Vector(shoulder_w)).length
                    self.assertGreater(live_req_dist, MIN_ARM_REACH + 0.05)
                    self.assertLess(live_req_dist, MAX_ARM_REACH - 0.05)
                    min_reach_margin = min(
                        min_reach_margin,
                        live_req_dist - MIN_ARM_REACH,
                        MAX_ARM_REACH - live_req_dist,
                    )

                    # Non-stretching bone length preservation
                    self.assertAlmostEqual(arm_lens[0], UPPER_ARM_LENGTH, delta=1e-4)
                    self.assertAlmostEqual(arm_lens[1], FOREARM_LENGTH, delta=1e-4)
                    self.assertAlmostEqual(arm_lens[2], HAND_LENGTH, delta=1e-4)

                    pos_err = (Vector(actual_wrist) - Vector(expected_wrist)).length
                    rot_err = _so3_angle_diff_deg(
                        actual_hmat.to_3x3(), _matrix_from_euler_deg(expected_rot_deg)
                    )
                    max_pos_err = max(max_pos_err, pos_err)
                    max_rot_err = max(max_rot_err, rot_err)
                    self.assertLessEqual(pos_err, WBC_POS_TOL_M)
                    self.assertLessEqual(rot_err, WBC_ROT_TOL_DEG)
                    self.assertTrue(eff_fb.is_reachable)
                    self.assertTrue(eff_fb.strictly_in_reach)

            print(
                f"[7B-3][T05] run={run_label} frames={len(snaps)} max_wrist_err_m={max_pos_err:.6f} "
                f"max_so3_rot_err_deg={max_rot_err:.4f} min_reach_margin_m={min_reach_margin:.4f}",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t06_actual_hand_bone_matrix_reconstructs_palm_anchor
    # PURPOSE: T06 — Verify actual_palm = (arm.matrix_world @ pose_bone.matrix) @ Vector(local_anchor) matches frame-interpolated palm during transition and queried surface contact_point_world during arrival & hold within Section 10's ~5.921mm bound.
    # REASON: TASK 7B-3 T06 — Confirm palm anchor reconstruction on real solved bones after unit-scale rigid matrix verification.
    def test_t06_actual_hand_bone_matrix_reconstructs_palm_anchor(self) -> None:
        run = self.run_bilateral_ik
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]

        for side in ("L", "R"):
            acq = run[f"acq_{side}"]
            surf: SurfaceQueryResult = acq["surface"]
            local_anchor = Vector(DEFAULT_LIMB_LOCAL_ANCHORS[f"hand_{side}"])
            palm_bound_m = _palm_error_bound_m(side)

            hold_palm_errors: List[float] = []
            transition_palm_errors: List[float] = []
            for snap in snaps:
                hmat = snap.hand_matrix_world_L if side == "L" else snap.hand_matrix_world_R
                _assert_unit_scale_rigid_4x4(self, hmat, f"hand.{side}@f{snap.frame}")
                actual_palm = hmat @ local_anchor

                _, h = _evaluate_upper_limb_progress(
                    snap.time_sec, acq["start_time_sec"], acq["duration_sec"]
                )
                if abs(h - 1.0) <= 1e-12:
                    surf_palm_err = (actual_palm - Vector(surf.contact_point_world)).length
                    hold_palm_errors.append(surf_palm_err)
                    self.assertLessEqual(surf_palm_err, palm_bound_m)
                else:
                    planned_hand = snap.planned_hand_L if side == "L" else snap.planned_hand_R
                    interp_palm = Vector(planned_hand["world_xyz"]) + (
                        _matrix_from_euler_deg(planned_hand["rotation_deg"]) @ local_anchor
                    )
                    trans_err = (actual_palm - interp_palm).length
                    transition_palm_errors.append(trans_err)
                    self.assertLessEqual(trans_err, palm_bound_m)

            self.assertGreaterEqual(len(hold_palm_errors), 3)
            self.assertGreaterEqual(len(transition_palm_errors), 8)
            print(
                f"[7B-3][T06] side={side} palm_bound_m={palm_bound_m:.6f} "
                f"hold_frames={len(hold_palm_errors)} max_surface_palm_err_m={max(hold_palm_errors):.6f} "
                f"max_transition_palm_err_m={max(transition_palm_errors):.6f}",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t07_actual_3d_orientation_normal_and_tangent_alignment
    # PURPOSE: T07 — Verify SO(3) orientation error <= 1 deg and actual hand normal (col_z) / tangent (col_y) angular errors <= 1 deg on target arrival and hold frames.
    # REASON: TASK 7B-3 T07 — Prove 3D surface basis alignment on solved hand bones for both horizontal top and vertical wall surfaces.
    def test_t07_actual_3d_orientation_normal_and_tangent_alignment(self) -> None:
        run = self.run_bilateral_ik
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]

        for side in ("L", "R"):
            acq = run[f"acq_{side}"]
            surf: SurfaceQueryResult = acq["surface"]
            expected_normal = surf.surface_normal_world
            expected_tangent = acq["expected_tangent"]
            target_rot_mat = _matrix_from_euler_deg(acq["rotation_end_deg"])

            max_so3_deg = 0.0
            max_norm_deg = 0.0
            max_tan_deg = 0.0
            checked_hold_frames = 0
            for snap in snaps:
                _, h = _evaluate_upper_limb_progress(
                    snap.time_sec, acq["start_time_sec"], acq["duration_sec"]
                )
                hmat = snap.hand_matrix_world_L if side == "L" else snap.hand_matrix_world_R
                rot3 = _assert_unit_scale_rigid_4x4(self, hmat, f"T07.hand.{side}@f{snap.frame}")
                if abs(h - 1.0) <= 1e-12:
                    checked_hold_frames += 1
                    col_y = Vector((rot3[0][1], rot3[1][1], rot3[2][1]))
                    col_z = Vector((rot3[0][2], rot3[1][2], rot3[2][2]))
                    so3_err = _so3_angle_diff_deg(rot3, target_rot_mat)
                    norm_err = _unit_vector_angle_deg(col_z, expected_normal)
                    tan_err = _unit_vector_angle_deg(col_y, expected_tangent)
                    max_so3_deg = max(max_so3_deg, so3_err)
                    max_norm_deg = max(max_norm_deg, norm_err)
                    max_tan_deg = max(max_tan_deg, tan_err)
                    self.assertLessEqual(so3_err, WBC_ROT_TOL_DEG)
                    self.assertLessEqual(norm_err, WBC_ROT_TOL_DEG)
                    self.assertLessEqual(tan_err, WBC_ROT_TOL_DEG)

            self.assertGreaterEqual(checked_hold_frames, 3)
            print(
                f"[7B-3][T07] side={side} hold_frames={checked_hold_frames} "
                f"max_so3_err_deg={max_so3_deg:.4f} max_normal_err_deg={max_norm_deg:.4f} "
                f"max_tangent_err_deg={max_tan_deg:.4f}",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t08_world_target_invariance_under_root_translation_and_yaw
    # PURPOSE: T08 — Verify position_space="WORLD" hand targets are never double-transformed by non-zero CharacterRoot translation (full pipeline execution) or non-zero root_yaw_deg (MotionRuntimeContext.compose_planned_pose).
    # REASON: TASK 7B-3 T08 — Confirm WORLD target frame invariance across Root translation and heading rotation without modifying TerrainWalkAction.
    def test_t08_world_target_invariance_under_root_translation_and_yaw(self) -> None:
        base_acq_l = self.run_left_ik["acq_L"]
        fps = float(self.run_left_ik["fps"])

        # Part A: Full production execution with translated CharacterRoot start_pos on Surface_FlatGround
        shifted_start = (0.08, -8.06, 0.0)
        shifted_shoulder_l = (
            self.standing_shoulder_L[0] + shifted_start[0],
            self.standing_shoulder_L[1] + (shifted_start[1] - (-8.0)),
            self.standing_shoulder_L[2],
        )
        shifted_run = _execute_observed_standing_sequence(
            standing_shoulder_L=shifted_shoulder_l,
            standing_shoulder_R=(
                self.standing_shoulder_R[0] + shifted_start[0],
                self.standing_shoulder_R[1] + (shifted_start[1] - (-8.0)),
                self.standing_shoulder_R[2],
            ),
            left_spec={
                "ray_origin": (-0.24, -7.60, 1.85),
                "ray_direction": (0.0, 0.0, -1.0),
                "max_distance": 1.0,
                "tangent_hint": (0.0, 1.0, 0.0),
                "start_pitch_deg": 10.0,
                "start_time_sec": 2.0 / fps,
                "duration_sec": 9.0 / fps,
            },
            right_spec=None,
            start_pos=shifted_start,
        )
        shifted_snaps: List[_FrameTelemetrySnapshot] = shifted_run["frame_snapshots"]
        palm_bound_l = _palm_error_bound_m("L")
        for snap in shifted_snaps:
            self.assertAlmostEqual(snap.root_world[0], shifted_start[0], delta=1e-5)
            self.assertAlmostEqual(snap.root_world[1], shifted_start[1], delta=1e-5)
            self.assertTrue(snap.rom_valid and snap.wbc_success)

        final_shifted = shifted_snaps[-1]
        planned_end_diff = (
            Vector(final_shifted.planned_hand_L["world_xyz"]) - Vector(base_acq_l["wrist_end_xyz"])
        ).length
        self.assertLessEqual(planned_end_diff, 1e-12)
        actual_palm_diff_to_surface = (
            Vector(final_shifted.actual_palm_L) - Vector(base_acq_l["surface"].contact_point_world)
        ).length
        self.assertLessEqual(actual_palm_diff_to_surface, palm_bound_l)

        # Part B: Non-zero root_yaw_deg + non-zero root_position invariance via MotionRuntimeContext.compose_planned_pose()
        env_ctx = shifted_run["env_ctx"]
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        root = env_ctx["root"]
        query = env_ctx["query"]
        seq_dur = shifted_run["sequence_duration_sec"]
        segs_world = base_acq_l["segments"]

        runtime_ctx = MotionRuntimeContext(
            config=cfg,
            armature_obj=arm,
            root_obj=root,
            scene=bpy.context.scene,
            environment=query,
            contact_adapter=ContactConstraintAdapter(arm, query),
            pose_applicator=BlenderPoseApplicator(arm, root, cfg),
            upper_limb_L=segs_world,
            upper_limb_R=None,
            sequence_start_frame=1,
            sequence_duration_sec=seq_dur,
        )

        root_configs = [
            ((0.0, -8.0, 0.0), 0.0),
            ((1.35, -4.20, 0.25), 37.5),
            ((-2.10, -6.50, 0.0), -112.0),
        ]
        for test_frame in (6, 14):  # transition frame 6 and hold frame 14
            composed_targets = []
            for r_pos, r_yaw in root_configs:
                base_pose = KinematicPlannedPose(
                    frame=test_frame,
                    time_seconds=(test_frame - 1) / fps,
                    root_position=r_pos,
                    root_yaw_deg=r_yaw,
                    motion_mode=MotionMode.IDLE,
                    foot_L=PlannedFootTarget(world_xyz=(r_pos[0] - HIP_X_OFFSET, r_pos[1], ANKLE_REST_Z), is_locked=True),
                    foot_R=PlannedFootTarget(world_xyz=(r_pos[0] + HIP_X_OFFSET, r_pos[1], ANKLE_REST_Z), is_locked=True),
                )
                composed_pose, _ = runtime_ctx.compose_planned_pose(base_pose)
                composed_targets.append(composed_pose.hand_L)

            ref_ht = composed_targets[0]
            for other_ht in composed_targets[1:]:
                self.assertLessEqual(
                    (Vector(other_ht.world_xyz) - Vector(ref_ht.world_xyz)).length,
                    1e-12,
                )
                self.assertLessEqual(
                    max(abs(a - b) for a, b in zip(other_ht.rotation_deg, ref_ht.rotation_deg)),
                    1e-12,
                )
                self.assertLessEqual(
                    (Vector(other_ht.pole_hint_world_xyz) - Vector(ref_ht.pole_hint_world_xyz)).length,
                    1e-12,
                )

        print(
            f"[7B-3][T08] shifted_root={shifted_start} planned_world_diff_m={planned_end_diff:.3e} "
            f"shifted_palm_surface_err_m={actual_palm_diff_to_surface:.6f} yaw_cases_verified={len(root_configs)}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t09_environment_translation_requery_replan_and_execute
    # PURPOSE: T09 — Translate the target obstacle in memory, re-query via the existing DynamicsEnvironmentQuery, re-convert, re-plan, and execute through MotionPlanner.
    # REASON: TASK 7B-3 T09 — Prove re-query -> re-convert -> re-plan -> execute adapts accurately to translated real Mesh geometry without claiming per-frame closed-loop tracking.
    def test_t09_environment_translation_requery_replan_and_execute(self) -> None:
        env_ctx = _prepare_controlled_playground_scene()
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        query: DynamicsEnvironmentQuery = env_ctx["query"]
        fps = float(cfg.fps)

        # Query 1 before additional obstacle translation
        surf_before = query.query_spatial_surface((-0.24, -7.60, 1.85), (0.0, 0.0, -1.0), max_distance=1.0)
        wrist_before, rot_before = compute_hand_target_from_surface("L", surf_before, (0.0, 1.0, 0.0))

        # Apply controlled translation delta (+0.05, +0.06, +0.08) to the same Surface_Ramp_TopPlatform
        delta_vec = Vector((0.05, 0.06, 0.08))
        plat_obj = bpy.data.objects[LEFT_PLATFORM_OBJ_NAME]
        plat_obj.matrix_world = Matrix.Translation(Vector(LEFT_PLATFORM_RELOC) + delta_vec)
        bpy.context.view_layer.update()

        # Re-query using the SAME query instance (verifying automatic cache invalidation)
        ray_origin_after = (-0.24 + delta_vec.x, -7.60 + delta_vec.y, 1.85 + delta_vec.z)
        surf_after = query.query_spatial_surface(ray_origin_after, (0.0, 0.0, -1.0), max_distance=1.0)
        self.assertTrue(surf_after.success)
        self.assertEqual(surf_after.source_type, "mesh")
        self.assertTrue(surf_after.surface_id.startswith(f"mesh:{LEFT_PLATFORM_OBJ_NAME}:"))

        contact_shift = Vector(surf_after.contact_point_world) - Vector(surf_before.contact_point_world)
        self.assertLessEqual((contact_shift - delta_vec).length, 1e-5)

        wrist_after, rot_after = compute_hand_target_from_surface("L", surf_after, (0.0, 1.0, 0.0))
        self.assertLessEqual((Vector(wrist_after) - Vector(wrist_before) - delta_vec).length, 1e-5)
        self.assertLessEqual(
            _so3_angle_diff_deg(_matrix_from_euler_deg(rot_after), _matrix_from_euler_deg(rot_before)),
            1e-5,
        )

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        action = TerrainWalkAction(route=route, action_name="Task7B3_T09_Translated", environment=query)
        total_frames = action.estimate_duration_frames(init_state, cfg, query)
        seq_dur = (total_frames - 1) / fps

        w_start, r_start, pole_l = _compute_ready_start_pose_from_shoulder(
            "L", self.standing_shoulder_L, start_pitch_deg=10.0
        )
        segs_after = _build_ik_reach_segment(
            start_time_sec=2.0 / fps,
            duration_sec=9.0 / fps,
            wrist_start_xyz=w_start,
            wrist_end_xyz=wrist_after,
            rotation_start_deg=r_start,
            rotation_end_deg=rot_after,
            pole_start_xyz=pole_l,
            pole_end_xyz=pole_l,
        )

        with _PipelineReadOnlyObserver(query) as obs:
            planner = MotionPlanner(
                config=cfg,
                armature_obj=arm,
                environment=query,
                upper_limb_L=segs_after,
                sequence_duration_sec=seq_dur,
            )
            planner.add_action(action)
            res = planner.execute(initial_state=init_state)

        self.assertTrue(res["success"])
        final_snap = obs.frame_snapshots[-1]
        self.assertTrue(final_snap.rom_valid)
        wrist_err = (Vector(final_snap.actual_wrist_L) - Vector(wrist_after)).length
        palm_err = (Vector(final_snap.actual_palm_L) - Vector(surf_after.contact_point_world)).length
        self.assertLessEqual(wrist_err, WBC_POS_TOL_M)
        self.assertLessEqual(palm_err, _palm_error_bound_m("L"))
        print(
            f"[7B-3][T09] contact_before={surf_before.contact_point_world} "
            f"contact_after={surf_after.contact_point_world} wrist_err_m={wrist_err:.6f} "
            f"palm_err_m={palm_err:.6f}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t10_environment_rotation_requery_replan_and_execute
    # PURPOSE: T10 — Rotate the target obstacle rigidly around a top-surface pivot, re-query via the existing DynamicsEnvironmentQuery, re-convert, re-plan, and verify tilted 3D hand normal/tangent alignment.
    # REASON: TASK 7B-3 T10 — Prove rotated Mesh normals & tangents propagate through 7B-2 conversion and WBC 3D orientation control within <= 1 deg.
    def test_t10_environment_rotation_requery_replan_and_execute(self) -> None:
        env_ctx = _prepare_controlled_playground_scene()
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        query: DynamicsEnvironmentQuery = env_ctx["query"]
        fps = float(cfg.fps)

        surf_flat = query.query_spatial_surface((-0.24, -7.60, 1.85), (0.0, 0.0, -1.0), max_distance=1.0)
        self.assertTrue(surf_flat.success)

        # Rigidly tilt Surface_Ramp_TopPlatform by (+15 deg X, -8 deg Y) around top-surface pivot
        pivot = Vector(surf_flat.contact_point_world)
        tilt_euler = Euler((math.radians(15.0), math.radians(-8.0), 0.0), "XYZ")
        tilt_rot4 = tilt_euler.to_matrix().to_4x4()
        base_reloc_mat = Matrix.Translation(Vector(LEFT_PLATFORM_RELOC))
        plat_obj = bpy.data.objects[LEFT_PLATFORM_OBJ_NAME]
        plat_obj.matrix_world = (
            Matrix.Translation(pivot)
            @ tilt_rot4
            @ Matrix.Translation(-pivot)
            @ base_reloc_mat
        )
        bpy.context.view_layer.update()

        # Re-query using the SAME query instance
        surf_tilted = query.query_spatial_surface((-0.24, -7.60, 1.85), (0.0, 0.0, -1.0), max_distance=1.0)
        self.assertTrue(surf_tilted.success)
        self.assertEqual(surf_tilted.source_type, "mesh")
        normal_tilt_deg = _unit_vector_angle_deg(
            surf_tilted.surface_normal_world, surf_flat.surface_normal_world
        )
        self.assertGreater(normal_tilt_deg, 16.0)

        tangent_hint = (0.0, 1.0, 0.0)
        wrist_tilted, rot_tilted = compute_hand_target_from_surface("L", surf_tilted, tangent_hint)
        expected_tan = _expected_surface_tangent(surf_tilted.surface_normal_world, tangent_hint)

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        action = TerrainWalkAction(route=route, action_name="Task7B3_T10_Rotated", environment=query)
        total_frames = action.estimate_duration_frames(init_state, cfg, query)
        seq_dur = (total_frames - 1) / fps

        w_start, r_start, pole_l = _compute_ready_start_pose_from_shoulder(
            "L", self.standing_shoulder_L, start_pitch_deg=10.0
        )
        segs_tilted = _build_ik_reach_segment(
            start_time_sec=2.0 / fps,
            duration_sec=9.0 / fps,
            wrist_start_xyz=w_start,
            wrist_end_xyz=wrist_tilted,
            rotation_start_deg=r_start,
            rotation_end_deg=rot_tilted,
            pole_start_xyz=pole_l,
            pole_end_xyz=pole_l,
        )

        with _PipelineReadOnlyObserver(query) as obs:
            planner = MotionPlanner(
                config=cfg,
                armature_obj=arm,
                environment=query,
                upper_limb_L=segs_tilted,
                sequence_duration_sec=seq_dur,
            )
            planner.add_action(action)
            res = planner.execute(initial_state=init_state)

        self.assertTrue(res["success"])
        final_snap = obs.frame_snapshots[-1]
        self.assertTrue(final_snap.rom_valid)
        rot3 = _assert_unit_scale_rigid_4x4(self, final_snap.hand_matrix_world_L, "T10.hand.L")
        col_y = Vector((rot3[0][1], rot3[1][1], rot3[2][1]))
        col_z = Vector((rot3[0][2], rot3[1][2], rot3[2][2]))

        wrist_err = (Vector(final_snap.actual_wrist_L) - Vector(wrist_tilted)).length
        palm_err = (Vector(final_snap.actual_palm_L) - Vector(surf_tilted.contact_point_world)).length
        so3_err = _so3_angle_diff_deg(rot3, _matrix_from_euler_deg(rot_tilted))
        norm_err = _unit_vector_angle_deg(col_z, surf_tilted.surface_normal_world)
        tan_err = _unit_vector_angle_deg(col_y, expected_tan)

        self.assertLessEqual(wrist_err, WBC_POS_TOL_M)
        self.assertLessEqual(palm_err, _palm_error_bound_m("L"))
        self.assertLessEqual(so3_err, WBC_ROT_TOL_DEG)
        self.assertLessEqual(norm_err, WBC_ROT_TOL_DEG)
        self.assertLessEqual(tan_err, WBC_ROT_TOL_DEG)
        print(
            f"[7B-3][T10] normal_tilt_deg={normal_tilt_deg:.3f} tilted_normal={surf_tilted.surface_normal_world} "
            f"wrist_err_m={wrist_err:.6f} palm_err_m={palm_err:.6f} "
            f"so3_err_deg={so3_err:.4f} norm_err_deg={norm_err:.4f} tan_err_deg={tan_err:.4f}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t11_failed_mesh_query_refuses_hand_trajectory_generation
    # PURPOSE: T11 — Execute a genuine unhit sky ray query via DynamicsEnvironmentQuery on the live scene and verify compute_hand_target_from_surface() rejects it with explicit ValueError before any UpperLimbSegment can be built.
    # REASON: TASK 7B-3 T11 — Confirm failed real queries never fabricate wrist targets or trajectories (binding query to current live bpy.context.scene after T10's open_mainfile).
    def test_t11_failed_mesh_query_refuses_hand_trajectory_generation(self) -> None:
        query = create_mesh_backed_dynamics_query(
            scene=bpy.context.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
            ground_z=0.0,
        )
        miss_res = query.query_spatial_surface(
            point_world=(0.0, -8.0, 1.80),
            ray_direction=(0.0, 0.0, 1.0),
            max_distance=2.0,
        )
        self.assertFalse(miss_res.success)
        self.assertTrue(bool(miss_res.error_reason))

        with self.assertRaises(ValueError) as ctx:
            compute_hand_target_from_surface("L", miss_res, (0.0, 1.0, 0.0))

        err_msg = str(ctx.exception)
        self.assertIn("surface query must succeed", err_msg)
        self.assertIn(str(miss_res.error_reason), err_msg)
        print(
            f"[7B-3][T11] miss_success={miss_res.success} error_reason={miss_res.error_reason!r} "
            f"rejected_with={err_msg!r}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t12_beyond_max_arm_reach_fails_truthfully
    # PURPOSE: T12 — Place Surface_VerticalWall at Y=-7.15m (real queried wrist distance ~0.836m > MAX_ARM_REACH=0.56m) with clamp_reach=False and verify truthful REACHABILITY failure.
    # REASON: TASK 7B-3 T12 — Prove out-of-max-reach real Mesh targets fail with explicit REACHABILITY unmet constraint rather than silently clamping.
    def test_t12_beyond_max_arm_reach_fails_truthfully(self) -> None:
        # Surface_VerticalWall local Y in [23.8, 24.2] + (-30.95) -> world front face at Y = -7.15m
        env_ctx = _prepare_controlled_playground_scene(
            obstacle_transforms={
                RIGHT_WALL_OBJ_NAME: Matrix.Translation(Vector((0.0, -30.95, 0.0))),
            }
        )
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        query: DynamicsEnvironmentQuery = env_ctx["query"]
        fps = float(cfg.fps)

        surf_far = query.query_spatial_surface((-0.24, -7.90, 1.52), (0.0, 1.0, 0.0), max_distance=2.0)
        self.assertTrue(surf_far.success)
        self.assertEqual(surf_far.source_type, "mesh")
        wrist_far, rot_far = compute_hand_target_from_surface("L", surf_far, (0.0, 0.0, 1.0))

        req_dist = (Vector(wrist_far) - Vector(self.standing_shoulder_L)).length
        self.assertGreater(req_dist, MAX_ARM_REACH + 0.20)

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        action = TerrainWalkAction(route=route, action_name="Task7B3_T12_TooFar", environment=query)
        total_frames = action.estimate_duration_frames(init_state, cfg, query)
        seq_dur = (total_frames - 1) / fps

        w_start, r_start, pole_l = _compute_ready_start_pose_from_shoulder(
            "L", self.standing_shoulder_L, start_pitch_deg=35.0
        )
        # Transition in 1 frame (frame 1 valid start -> frame 2 exact far target)
        segs_far = _build_ik_reach_segment(
            start_time_sec=0.0,
            duration_sec=1.0 / fps,
            wrist_start_xyz=w_start,
            wrist_end_xyz=wrist_far,
            rotation_start_deg=r_start,
            rotation_end_deg=rot_far,
            pole_start_xyz=pole_l,
            pole_end_xyz=pole_l,
        )

        with _PipelineReadOnlyObserver(query) as obs:
            planner = MotionPlanner(
                config=cfg,
                armature_obj=arm,
                environment=query,
                upper_limb_L=segs_far,
                sequence_duration_sec=seq_dur,
            )
            planner.add_action(action)
            with self.assertRaises(RuntimeError) as ctx:
                planner.execute(initial_state=init_state)

        err_msg = str(ctx.exception)
        self.assertIn("REACHABILITY", err_msg)
        self.assertIn("hand_L", err_msg)
        fail_snap = obs.frame_snapshots[-1]
        self.assertEqual(fail_snap.frame, 2)
        self.assertFalse(fail_snap.wbc_success)
        self.assertFalse(fail_snap.is_all_reachable)
        self.assertFalse(fail_snap.eff_feedback["hand_L"].is_reachable)
        self.assertTrue(
            any(uc.category == "REACHABILITY" and uc.target_name == "hand_L" for uc in fail_snap.unmet_constraints)
        )
        print(
            f"[7B-3][T12] req_dist_m={req_dist:.4f} max_arm_reach_m={MAX_ARM_REACH:.4f} "
            f"failed_frame={fail_snap.frame} reason={err_msg!r}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t13_below_min_arm_reach_fails_truthfully
    # PURPOSE: T13 — Relocate Surface_LedgeBar_Crossbar lateral to left shoulder (X in [-4.20, -0.20], clear of feet at X=+-0.11) so queried wrist distance ~0.047m < MIN_ARM_REACH=0.08m and verify truthful REACHABILITY failure.
    # REASON: TASK 7B-3 T13 — Prove too-close real Mesh targets (< MIN_ARM_REACH relative to actual posed shoulder bone) fail truthfully with clamp_reach=False.
    def test_t13_below_min_arm_reach_fails_truthfully(self) -> None:
        # Surface_LedgeBar_Crossbar local X[-2, 2], Y[31.95, 32.05], Z[2.15, 2.25]
        # Shift by (-2.20, -39.96, -0.715) -> world X[-4.20, -0.20] (clear of feet at X=-0.11/+0.11),
        # Y[-8.01, -7.91], Z[1.435, 1.535] (top Z=1.535 -> wrist Z=1.550, Y=-7.985 -> dist=0.0474m < 0.08m).
        env_ctx = _prepare_controlled_playground_scene(
            obstacle_transforms={
                CROSSBAR_OBJ_NAME: Matrix.Translation(Vector((-2.20, -39.96, -0.715))),
            }
        )
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        query: DynamicsEnvironmentQuery = env_ctx["query"]
        fps = float(cfg.fps)

        surf_close = query.query_spatial_surface((-0.24, -7.935, 1.80), (0.0, 0.0, -1.0), max_distance=1.0)
        self.assertTrue(surf_close.success)
        self.assertEqual(surf_close.source_type, "mesh")
        self.assertTrue(surf_close.surface_id.startswith(f"mesh:{CROSSBAR_OBJ_NAME}:"))
        wrist_close, rot_close = compute_hand_target_from_surface("L", surf_close, (0.0, 1.0, 0.0))

        req_dist = (Vector(wrist_close) - Vector(self.standing_shoulder_L)).length
        self.assertLess(req_dist, MIN_ARM_REACH - 0.025)

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        action = TerrainWalkAction(route=route, action_name="Task7B3_T13_TooClose", environment=query)
        total_frames = action.estimate_duration_frames(init_state, cfg, query)
        seq_dur = (total_frames - 1) / fps

        w_start, r_start, pole_l = _compute_ready_start_pose_from_shoulder(
            "L", self.standing_shoulder_L, start_pitch_deg=10.0
        )
        # Transition in 1 frame (frame 1 valid start -> frame 2 exact too-close target with req_dist < MIN_ARM_REACH)
        segs_close = _build_ik_reach_segment(
            start_time_sec=0.0,
            duration_sec=1.0 / fps,
            wrist_start_xyz=w_start,
            wrist_end_xyz=wrist_close,
            rotation_start_deg=r_start,
            rotation_end_deg=rot_close,
            pole_start_xyz=pole_l,
            pole_end_xyz=pole_l,
        )

        with _PipelineReadOnlyObserver(query) as obs:
            planner = MotionPlanner(
                config=cfg,
                armature_obj=arm,
                environment=query,
                upper_limb_L=segs_close,
                sequence_duration_sec=seq_dur,
            )
            planner.add_action(action)
            with self.assertRaises(RuntimeError) as ctx:
                planner.execute(initial_state=init_state)

        err_msg = str(ctx.exception)
        self.assertIn("REACHABILITY", err_msg)
        self.assertIn("hand_L", err_msg)
        fail_snap = obs.frame_snapshots[-1]
        live_fail_dist = (Vector(wrist_close) - Vector(fail_snap.shoulder_world_L)).length
        self.assertEqual(fail_snap.frame, 2)
        self.assertLess(live_fail_dist, MIN_ARM_REACH)
        self.assertFalse(fail_snap.wbc_success)
        self.assertFalse(fail_snap.is_all_reachable)
        self.assertFalse(fail_snap.eff_feedback["hand_L"].is_reachable)
        reach_ucs = [
            uc for uc in fail_snap.unmet_constraints if uc.category == "REACHABILITY" and uc.target_name == "hand_L"
        ]
        self.assertTrue(len(reach_ucs) >= 1)
        self.assertLess(float(reach_ucs[0].details["requested_reach"]), MIN_ARM_REACH)
        print(
            f"[7B-3][T13] live_req_dist_m={live_fail_dist:.5f} min_arm_reach_m={MIN_ARM_REACH:.4f} "
            f"failed_frame={fail_snap.frame} reason={err_msg!r}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t14_geometrically_reachable_but_rom_infeasible_reports_truthfully
    # PURPOSE: T14 — Query real relocated platform top surface with a backward-twisted tangent (-0.5, -0.8660254, 0.0) so wrist is strictly reachable (~0.453m) and IK solves accurately, while JointModel detects anatomical wrist ROM_VIOLATION.
    # REASON: TASK 7B-3 T14 — Confirm ROM checking stays active and truthfully rejects anatomically infeasible real surface orientations without loosening limits.
    def test_t14_geometrically_reachable_but_rom_infeasible_reports_truthfully(self) -> None:
        env_ctx = _prepare_controlled_playground_scene()
        cfg = env_ctx["config"]
        arm = env_ctx["armature"]
        query: DynamicsEnvironmentQuery = env_ctx["query"]
        fps = float(cfg.fps)

        surf_top = query.query_spatial_surface((-0.24, -7.60, 1.85), (0.0, 0.0, -1.0), max_distance=1.0)
        self.assertTrue(surf_top.success)
        self.assertEqual(surf_top.source_type, "mesh")

        # 120-deg hyper-pronated/ulnar-twisted tangent on horizontal platform top
        twisted_tangent = (-0.5, -0.8660254037844386, 0.0)
        wrist_rom_bad, rot_rom_bad = compute_hand_target_from_surface("L", surf_top, twisted_tangent)

        req_dist = (Vector(wrist_rom_bad) - Vector(self.standing_shoulder_L)).length
        self.assertGreater(req_dist, MIN_ARM_REACH + 0.25)
        self.assertLess(req_dist, MAX_ARM_REACH - 0.08)

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        action = TerrainWalkAction(route=route, action_name="Task7B3_T14_RomInfeasible", environment=query)
        total_frames = action.estimate_duration_frames(init_state, cfg, query)
        seq_dur = (total_frames - 1) / fps

        w_start, r_start, pole_l = _compute_ready_start_pose_from_shoulder(
            "L", self.standing_shoulder_L, start_pitch_deg=10.0
        )
        segs_rom_bad = _build_ik_reach_segment(
            start_time_sec=0.0,
            duration_sec=1.0 / fps,
            wrist_start_xyz=w_start,
            wrist_end_xyz=wrist_rom_bad,
            rotation_start_deg=r_start,
            rotation_end_deg=rot_rom_bad,
            pole_start_xyz=pole_l,
            pole_end_xyz=pole_l,
        )

        with _PipelineReadOnlyObserver(query) as obs:
            planner = MotionPlanner(
                config=cfg,
                armature_obj=arm,
                environment=query,
                upper_limb_L=segs_rom_bad,
                sequence_duration_sec=seq_dur,
            )
            planner.add_action(action)
            with self.assertRaises(RuntimeError) as ctx:
                planner.execute(initial_state=init_state)

        err_msg = str(ctx.exception)
        self.assertIn("ROM_VIOLATION", err_msg)
        self.assertIn("hand.L", err_msg)

        fail_snap = obs.frame_snapshots[-1]
        eff_l = fail_snap.eff_feedback["hand_L"]
        self.assertEqual(fail_snap.frame, 2)
        self.assertTrue(fail_snap.is_all_reachable)
        self.assertTrue(eff_l.is_reachable)
        self.assertLessEqual(eff_l.position_error_m, WBC_POS_TOL_M)
        self.assertLessEqual(eff_l.orientation_error_deg, WBC_ROT_TOL_DEG)
        self.assertFalse(fail_snap.rom_valid)
        self.assertIn("hand.L", fail_snap.rom_violations)
        self.assertTrue(any(uc.category == "ROM_VIOLATION" for uc in fail_snap.unmet_constraints))
        print(
            f"[7B-3][T14] req_dist_m={req_dist:.4f} pos_err_m={eff_l.position_error_m:.6f} "
            f"rot_err_deg={eff_l.orientation_error_deg:.4f} rom_violations={list(fail_snap.rom_violations.keys())} "
            f"reason={err_msg!r}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t15_same_side_central_and_local_ownership_conflict_rejected
    # PURPOSE: T15 — Verify supplying upper_limb_L simultaneously on MotionPlanner (central) and TerrainWalkAction (action-local) is rejected with explicit ValueError before execution and inside compose_planned_pose().
    # REASON: TASK 7B-3 T15 — Enforce single-owner upper-limb trajectory arbitration per side using live scene objects.
    def test_t15_same_side_central_and_local_ownership_conflict_rejected(self) -> None:
        cfg = PipelineConfig()
        arm = bpy.data.objects["CharacterArmature"]
        root = bpy.data.objects["CharacterRoot"]
        query = create_mesh_backed_dynamics_query(
            scene=bpy.context.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
            ground_z=0.0,
        )
        segs_l = self.run_left_ik["acq_L"]["segments"]
        seq_dur = self.run_left_ik["sequence_duration_sec"]
        fps = float(self.run_left_ik["fps"])

        route = _make_standing_route()
        init_state = create_initial_motion_state(cfg, start_frame=1)
        conflicting_action = TerrainWalkAction(
            route=route,
            action_name="Task7B3_T15_Conflict",
            environment=query,
            upper_limb_L=segs_l,
        )
        planner = MotionPlanner(
            config=cfg,
            armature_obj=arm,
            environment=query,
            upper_limb_L=segs_l,
            sequence_duration_sec=seq_dur,
        )
        planner.add_action(conflicting_action)

        with self.assertRaises(ValueError) as planner_ctx:
            planner.execute(initial_state=init_state)
        self.assertIn("upper_limb_L control conflict", str(planner_ctx.exception))

        runtime_ctx = MotionRuntimeContext(
            config=cfg,
            armature_obj=arm,
            root_obj=root,
            scene=bpy.context.scene,
            environment=query,
            contact_adapter=ContactConstraintAdapter(arm, query),
            pose_applicator=BlenderPoseApplicator(arm, root, cfg),
            upper_limb_L=segs_l,
            sequence_duration_sec=seq_dur,
            sequence_start_frame=1,
        )
        sample_pose = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0,
            root_position=(0.0, -8.0, 0.0),
            root_yaw_deg=0.0,
            motion_mode=MotionMode.IDLE,
            foot_L=PlannedFootTarget(world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
        )
        with self.assertRaises(ValueError) as compose_ctx:
            runtime_ctx.compose_planned_pose(
                sample_pose,
                action_upper_limb_L=segs_l,
                action_time_sec=0.0 / fps,
            )
        self.assertIn("Upper-limb control ownership conflict on side 'L'", str(compose_ctx.exception))
        print(
            f"[7B-3][T15] planner_err={str(planner_ctx.exception)!r} "
            f"compose_err={str(compose_ctx.exception)!r}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t16_ik_execution_creates_zero_fake_contact_or_support
    # PURPOSE: T16 — Verify contact_intent=False and is_locked=False remain preserved across every frame, producing FREE/RELEASED hand contacts, DOUBLE_STANCE foot-only support, and unlocked HandIK controllers.
    # REASON: TASK 7B-3 T16 (Section 8) — Confirm Task 7B-3 hand reaching never fabricates hand support, grasp, or load-bearing state.
    def test_t16_ik_execution_creates_zero_fake_contact_or_support(self) -> None:
        for run_label, run in (
            ("left_ik", self.run_left_ik),
            ("right_ik", self.run_right_ik),
            ("bilateral_ik", self.run_bilateral_ik),
        ):
            snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
            for snap in snaps:
                for ph in (snap.planned_hand_L, snap.planned_hand_R):
                    if ph is not None:
                        self.assertFalse(ph["contact_intent"])
                        self.assertFalse(ph["is_locked"])
                        self.assertEqual(ph["contact_type"], ContactType.FREE.value)

                self.assertEqual(snap.support_type, SupportType.DOUBLE_STANCE.value)
                self.assertNotIn("hand_L", snap.active_contacts)
                self.assertNotIn("hand_R", snap.active_contacts)
                self.assertNotIn("hand_L", snap.supporting_limbs)
                self.assertNotIn("hand_R", snap.supporting_limbs)
                self.assertNotIn("hand_L", snap.effective_contacts)
                self.assertNotIn("hand_R", snap.effective_contacts)
                self.assertEqual(
                    snap.hand_contact_L,
                    (ContactType.FREE.value, ContactLifecycle.RELEASED.value),
                )
                self.assertEqual(
                    snap.hand_contact_R,
                    (ContactType.FREE.value, ContactLifecycle.RELEASED.value),
                )
                self.assertFalse(snap.hand_ik_custom_locked_L)
                self.assertFalse(snap.hand_ik_custom_locked_R)
                # [INTRODUCED 2026-11-28T16:11:07+08:00]
                # FUNCTION: test_t16_ik_execution_creates_zero_fake_contact_or_support
                # PURPOSE: Verify that legacy MotionState hand contact entries remain unlocked in swing phase.
                # REASON: TASK 7B-3 T16 — Match the independently reviewed legacy contact projection contract.
                for limb in ("hand_L", "hand_R"):
                    self.assertIn(limb, snap.motion_state_contacts)
                    self.assertEqual(snap.motion_state_contacts[limb]["limb"], limb)
                    self.assertEqual(snap.motion_state_contacts[limb]["phase"], "swing")
                    self.assertFalse(snap.motion_state_contacts[limb]["is_locked"])

            print(
                f"[7B-3][T16] run={run_label} frames={len(snaps)} support_type={snaps[-1].support_type} "
                f"hand_contacts=({snaps[-1].hand_contact_L}, {snaps[-1].hand_contact_R}) fake_hand_support=False",
                flush=True,
            )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t17_timeline_bounds_endpoint_hold_and_contiguous_frames
    # PURPOSE: T17 — Verify sequence_duration_sec == (total_frames - 1)/fps, contiguous frames 1..N, pre-start and post-end endpoint holding, monotonic C2 quintic progress, and rejection of out-of-bounds segment end times.
    # REASON: TASK 7B-3 T17 — Confirm strict temporal contract across UpperLimbSegment, compose_planned_pose(), and MotionPlanner.execute().
    def test_t17_timeline_bounds_endpoint_hold_and_contiguous_frames(self) -> None:
        run = self.run_bilateral_ik
        res = run["planner_result"]
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
        acq_l = run["acq_L"]
        fps = float(run["fps"])
        total_frames = int(run["total_frames"])
        expected_seq_dur = (total_frames - 1) / fps

        self.assertAlmostEqual(run["sequence_duration_sec"], expected_seq_dur, places=9)
        self.assertEqual(res["sequence_start_frame"], 1)
        self.assertEqual(res["sequence_end_frame"], total_frames)
        self.assertEqual([s.frame for s in snaps], list(range(1, total_frames + 1)))

        # Verify pre-start hold (frames 1..3 where t <= 2/24), monotonic transition (frames 4..11), and post-end hold (frames 12..16 where t >= 11/24)
        prev_h = 0.0
        pre_hold_count = 0
        post_hold_count = 0
        for snap in snaps:
            _, h = _evaluate_upper_limb_progress(
                snap.time_sec, acq_l["start_time_sec"], acq_l["duration_sec"]
            )
            self.assertGreaterEqual(h, prev_h - 1e-12)
            prev_h = h
            planned_w = snap.planned_hand_L["world_xyz"]
            if snap.time_sec <= acq_l["start_time_sec"] + 1e-12:
                pre_hold_count += 1
                self.assertEqual(planned_w, acq_l["wrist_start_xyz"])
            if snap.time_sec >= acq_l["start_time_sec"] + acq_l["duration_sec"] - 1e-12:
                post_hold_count += 1
                self.assertEqual(planned_w, acq_l["wrist_end_xyz"])

        self.assertEqual(pre_hold_count, 3)
        self.assertEqual(post_hold_count, 5)

        # Out-of-bounds segment end time (> sequence_duration_sec) must be rejected
        bad_seg = _build_ik_reach_segment(
            start_time_sec=2.0 / fps,
            duration_sec=expected_seq_dur,  # end = seq_dur + 2/fps > seq_dur
            wrist_start_xyz=acq_l["wrist_start_xyz"],
            wrist_end_xyz=acq_l["wrist_end_xyz"],
            rotation_start_deg=acq_l["rotation_start_deg"],
            rotation_end_deg=acq_l["rotation_end_deg"],
            pole_start_xyz=acq_l["pole_xyz"],
            pole_end_xyz=acq_l["pole_xyz"],
        )
        with self.assertRaises(ValueError) as bound_ctx:
            validate_upper_limb_segment_sequence(bad_seg, "L", max_time_sec=expected_seq_dur)
        self.assertIn("exceeds sequence/action timeline upper bound", str(bound_ctx.exception))
        print(
            f"[7B-3][T17] frames=1..{total_frames} seq_dur_sec={expected_seq_dur:.6f} "
            f"pre_hold={pre_hold_count} post_hold={post_hold_count} oob_rejected=True",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t18_non_target_limbs_and_historical_standing_preserved
    # PURPOSE: T18 — Verify locked stance feet (foot_L, foot_R), root, pelvis, spine, neck, head, and non-overridden arms match the historical standing baseline without drift.
    # REASON: TASK 7B-3 T18 — Confirm upper-limb environmental target integration introduces zero regression on lower-limb stance locking or axial posture.
    def test_t18_non_target_limbs_and_historical_standing_preserved(self) -> None:
        base_snaps: List[_FrameTelemetrySnapshot] = self.run_baseline_fk["frame_snapshots"]
        max_foot_drift_m = 0.0
        max_trunk_diff_deg = 0.0

        for run in (self.run_left_ik, self.run_right_ik, self.run_bilateral_ik):
            snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
            first_ankle_l = Vector(snaps[0].ankle_world_L)
            first_ankle_r = Vector(snaps[0].ankle_world_R)
            for snap, b_snap in zip(snaps, base_snaps):
                self.assertTrue(snap.foot_locked_L)
                self.assertTrue(snap.foot_locked_R)
                drift_l = (Vector(snap.ankle_world_L) - first_ankle_l).length
                drift_r = (Vector(snap.ankle_world_R) - first_ankle_r).length
                vs_base_l = (Vector(snap.ankle_world_L) - Vector(b_snap.ankle_world_L)).length
                vs_base_r = (Vector(snap.ankle_world_R) - Vector(b_snap.ankle_world_R)).length
                max_foot_drift_m = max(max_foot_drift_m, drift_l, drift_r, vs_base_l, vs_base_r)
                self.assertLessEqual(max(drift_l, drift_r, vs_base_l, vs_base_r), 1e-4)

                self.assertLessEqual((Vector(snap.root_world) - Vector(b_snap.root_world)).length, 1e-6)
                for axial_bone in ("pelvis", "spine", "neck", "head"):
                    for a, b in zip(snap.fk_pose_euler_deg[axial_bone], b_snap.fk_pose_euler_deg[axial_bone]):
                        diff = abs(a - b)
                        max_trunk_diff_deg = max(max_trunk_diff_deg, diff)
                        self.assertLessEqual(diff, 1e-5)

        print(
            f"[7B-3][T18] max_locked_foot_drift_m={max_foot_drift_m:.3e} "
            f"max_axial_trunk_diff_deg={max_trunk_diff_deg:.3e}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t19_single_armature_unique_control_chain_and_exact_call_counts
    # PURPOSE: T19 — Verify single CharacterArmature in scene and exact non-duplicated invocation counts across query, conversion, planner, compose_planned_pose, Bridge, WBC, set_hand_ik_target, and set_arm_ik_influence.
    # REASON: TASK 7B-3 T19 — Prove no shadow armature, duplicate pose controller, or bypassed execution layer exists.
    def test_t19_single_armature_unique_control_chain_and_exact_call_counts(self) -> None:
        _assert_observers_restored(self)

        left_counts = self.run_left_ik["counts"]
        self.assertEqual(self.run_left_ik["env_ctx"]["armature_count"], 1)
        self.assertEqual(self.run_left_ik["env_ctx"]["armature_names"], ["CharacterArmature"])
        self.assertEqual(self.run_left_ik["armature_names_after"], ["CharacterArmature"])
        self.assertEqual(left_counts["query_spatial_surface"], 1)
        self.assertEqual(left_counts["compute_hand_target_from_surface"], 1)
        self.assertEqual(left_counts["planner_execute"], 1)
        self.assertEqual(left_counts["compose_planned_pose"], STANDING_TOTAL_FRAMES)
        self.assertEqual(left_counts["bridge_execute_frame"], STANDING_TOTAL_FRAMES)
        self.assertEqual(left_counts["wbc_execute_frame"], STANDING_TOTAL_FRAMES)
        self.assertEqual(left_counts["set_hand_ik_target"], STANDING_TOTAL_FRAMES)
        self.assertEqual(left_counts["set_arm_ik_influence"], STANDING_TOTAL_FRAMES)

        bi_counts = self.run_bilateral_ik["counts"]
        self.assertEqual(self.run_bilateral_ik["env_ctx"]["armature_count"], 1)
        self.assertEqual(self.run_bilateral_ik["armature_names_after"], ["CharacterArmature"])
        self.assertEqual(bi_counts["query_spatial_surface"], 2)
        self.assertEqual(bi_counts["compute_hand_target_from_surface"], 2)
        self.assertEqual(bi_counts["planner_execute"], 1)
        self.assertEqual(bi_counts["compose_planned_pose"], STANDING_TOTAL_FRAMES)
        self.assertEqual(bi_counts["bridge_execute_frame"], STANDING_TOTAL_FRAMES)
        self.assertEqual(bi_counts["wbc_execute_frame"], STANDING_TOTAL_FRAMES)
        self.assertEqual(bi_counts["set_hand_ik_target"], 2 * STANDING_TOTAL_FRAMES)
        self.assertEqual(bi_counts["set_arm_ik_influence"], 0)

        print(
            f"[7B-3][T19] armature=['CharacterArmature'] left_counts={left_counts} bilateral_counts={bi_counts}",
            flush=True,
        )

    # [INTRODUCED 2026-11-28T14:40:00+08:00]
    # FUNCTION: TestTask7B3EnvironmentHandIntegration.test_t20_input_immutability_asset_integrity_and_evidence_completeness
    # PURPOSE: T20 — Verify SurfaceQueryResult, UpperLimbSegment tuples, and DEFAULT_LIMB_LOCAL_ANCHORS were not mutated, source .blend SHA-256 is unchanged, and per-frame telemetry records contain all required Section 10 fields.
    # REASON: TASK 7B-3 T20 — Confirm stateless input handling, source asset preservation, and complete per-frame evidence capture.
    def test_t20_input_immutability_asset_integrity_and_evidence_completeness(self) -> None:
        current_sha256 = _sha256_file(PLAYGROUND_BLEND)
        self.assertEqual(current_sha256, self._initial_blend_sha256)

        run = self.run_bilateral_ik
        self.assertEqual(run["anchors_before"], run["anchors_after"])
        self.assertEqual(DEFAULT_LIMB_LOCAL_ANCHORS, run["anchors_before"])

        for side in ("L", "R"):
            acq = run[f"acq_{side}"]
            self.assertEqual(acq["surface"], acq["surface_snapshot_before"])
            self.assertEqual(acq["segments"], acq["segments_snapshot_before"])

        records = run["planner_result"]["frame_records"]
        snaps: List[_FrameTelemetrySnapshot] = run["frame_snapshots"]
        self.assertEqual(len(records), STANDING_TOTAL_FRAMES)
        self.assertEqual(len(snaps), STANDING_TOTAL_FRAMES)

        for idx, (rec, snap) in enumerate(zip(records, snaps), start=1):
            self.assertEqual(rec["frame"], idx)
            self.assertEqual(snap.frame, idx)
            self.assertEqual(len(snap.actual_wrist_L), 3)
            self.assertEqual(len(snap.actual_wrist_R), 3)
            self.assertEqual(len(snap.actual_hand_rot_deg_L), 3)
            self.assertEqual(len(snap.actual_hand_rot_deg_R), 3)
            self.assertIsNotNone(snap.planned_hand_L)
            self.assertIsNotNone(snap.planned_hand_R)
            self.assertTrue(snap.rom_valid)
            self.assertTrue(snap.is_all_reachable)
            self.assertEqual(snap.support_type, SupportType.DOUBLE_STANCE.value)

            actual_ul = rec["actual_armature"]["actual_upper_limb"]
            planned_ul = rec["motion_planning"]["planned_upper_limb"]
            for side in ("L", "R"):
                self.assertTrue(actual_ul[side]["enabled"])
                self.assertEqual(len(actual_ul[side]["wrist_world_xyz"]), 3)
                self.assertEqual(len(actual_ul[side]["hand_rotation_deg"]), 3)
                self.assertIsNotNone(actual_ul[side]["is_reachable"])
                self.assertEqual(actual_ul[side]["rom_violations"], {})
                self.assertEqual(planned_ul[side]["mode"], "IK")

        print(
            f"[7B-3][T20] blend_sha256={current_sha256} immutable_inputs=True "
            f"complete_frame_records={len(records)}",
            flush=True,
        )


if __name__ == "__main__":
    argv = [sys.argv[0]]
    if "--" in sys.argv:
        argv.extend(sys.argv[sys.argv.index("--") + 1 :])
    unittest.main(argv=argv, verbosity=2)
