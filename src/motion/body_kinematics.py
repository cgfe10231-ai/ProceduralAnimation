"""Continuous Body Motion State and Differential Kinematics (Task 6G-A).

Physics-constraint-assisted procedural animation: establishes a unified, reusable body
kinematics and differential velocity computation engine for the 19-bone humanoid character rig.

Core Capabilities:
1. Samples actual evaluated body postures from Blender Armature and WholeBodyController.
2. Derives spatial linear and angular velocities for:
   - Root node (world position, orientation, linear velocity, angular velocity vector).
   - Whole-body Center of Mass (CoM position and linear velocity).
   - 15 rigid mass segments (segment world CoM position, linear velocity, world angular velocity).
   - 17 anatomical joints (relative local rotation Euler/quaternion, local angular velocity).
   - 4 end effectors (world position, linear velocity, contact grounding flag).
3. Geodesic SO(3) angular velocity formulation via shortest-path quaternions:
   - Eliminates Euler wrap-around jump artifacts at +/-180 deg.
   - Singularity-free 3D angular velocity vectors in rad/s (and deg/s).
4. Explicit parameterization by arbitrary dt (no hardcoded 24 FPS assumption).
5. Explicit distinction between commanded velocities and derived velocities.
6. Transparent boundary handling for single-step causal tracking and full-trajectory smoothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.config import PipelineConfig
from src.motion.framework import ContactPointState, MotionMode, MotionState
from src.motion.joint_limits import (
    DEFAULT_HUMANOID_ROM_MODEL,
    JointModel,
    extract_evaluated_bone_rotation_rad,
    normalize_angle_deg,
    normalize_angle_rad,
)
from src.motion.rigid_link import (
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    BodyMassDistribution,
    SegmentCoMResult,
    WholeBodyCoMResult,
    compute_whole_body_com,
)
from src.motion.whole_body_controller import WholeBodyControlResult


# =============================================================================
# Mathematical Helpers for Differential Kinematics
# =============================================================================

def relative_angular_velocity(
    q0: Quaternion,
    q1: Quaternion,
    dt: float,
    frame: str = "world",
) -> Vector:
    """Compute the 3D angular velocity vector in rad/s from orientation q0 to q1 over time dt.

    Mathematics:
        Uses the shortest geodesic path on the 3-sphere S^3 to represent relative rotation in SO(3).
        Guarantees dot(q0, q1) >= 0 to avoid antipodal ambiguity where q and -q represent
        the identical 3D rotation.

        - For frame="world" (Spatial angular velocity in World frame):
            R_rel = R_1 * R_0^(-1)  <=>  delta_q = q1 * q0^(-1)
            omega_world = (theta * n) / dt

        - For frame="local" (Body-fixed angular velocity in local frame):
            R_rel = R_0^(-1) * R_1  <=>  delta_q = q0^(-1) * q1
            omega_local = (theta * n) / dt

    Properties:
        - 100% free of Euler angle wrap-around spikes at +/-180 deg.
        - Robust against gimbal lock and kinematic singularities.
        - Returns Vector((0.0, 0.0, 0.0)) when dt <= 0 or when q0 == q1.
    """
    if dt <= 1e-9:
        return Vector((0.0, 0.0, 0.0))

    q0_n = q0.normalized()
    q1_n = q1.normalized()

    # Shortest geodesic path: flip sign if in opposite quaternion hemispheres
    if q0_n.dot(q1_n) < 0.0:
        q1_n = -q1_n

    if frame == "world":
        diff = q1_n @ q0_n.inverted()
    elif frame == "local":
        diff = q0_n.inverted() @ q1_n
    else:
        raise ValueError(f"Unknown frame '{frame}', expected 'world' or 'local'")

    axis, angle = diff.to_axis_angle()

    # Normalize angle to (-pi, pi] to guarantee minimal angular displacement
    if angle > math.pi:
        angle -= 2.0 * math.pi
    elif angle < -math.pi:
        angle += 2.0 * math.pi

    if abs(angle) < 1e-8:
        return Vector((0.0, 0.0, 0.0))

    return (axis * angle) / dt


def relative_rotation_vector(
    q0: Quaternion,
    q1: Quaternion,
) -> Vector:
    """Compute the minimal 3D rotation displacement vector theta * n in radians from q0 to q1."""
    q0_n = q0.normalized()
    q1_n = q1.normalized()
    if q0_n.dot(q1_n) < 0.0:
        q1_n = -q1_n
    diff = q0_n.rotation_difference(q1_n)
    axis, angle = diff.to_axis_angle()
    if angle > math.pi:
        angle -= 2.0 * math.pi
    elif angle < -math.pi:
        angle += 2.0 * math.pi
    if abs(angle) < 1e-8:
        return Vector((0.0, 0.0, 0.0))
    return axis * angle


def linear_velocity(
    p0: Sequence[float],
    p1: Sequence[float],
    dt: float,
) -> Tuple[float, float, float]:
    """Compute 3D linear velocity (p1 - p0) / dt in m/s."""
    if dt <= 1e-9:
        return (0.0, 0.0, 0.0)
    return (
        (p1[0] - p0[0]) / dt,
        (p1[1] - p0[1]) / dt,
        (p1[2] - p0[2]) / dt,
    )


def linear_acceleration(
    v0: Sequence[float],
    v1: Sequence[float],
    dt: float,
) -> Tuple[float, float, float]:
    """Compute 3D linear acceleration (v1 - v0) / dt in m/s^2."""
    if dt <= 1e-9:
        return (0.0, 0.0, 0.0)
    return (
        (v1[0] - v0[0]) / dt,
        (v1[1] - v0[1]) / dt,
        (v1[2] - v0[2]) / dt,
    )


# =============================================================================
# Data Structures: Snapshot, Velocities, and Motion State
# =============================================================================

@dataclass(frozen=True)
class BodyPoseSnapshot:
    """Evaluated kinematic snapshot of the character at a single discrete instant t.

    Stores the actual physical positions and orientations evaluated after FK/IK solving.
    """
    time_sec: float
    frame: Optional[int]
    root_position: Tuple[float, float, float]
    root_orientation_quat: Tuple[float, float, float, float]       # (w, x, y, z)
    root_orientation_euler_deg: Tuple[float, float, float]        # (roll, pitch, yaw) in deg
    pelvis_position: Tuple[float, float, float]
    pelvis_orientation_quat: Tuple[float, float, float, float]
    com_world: Tuple[float, float, float]
    segment_positions: Dict[str, Tuple[float, float, float]]      # segment_id -> (x, y, z) in world (m)
    segment_orientations: Dict[str, Tuple[float, float, float, float]]  # segment_id -> (w, x, y, z) quat
    joint_rotations_rad: Dict[str, Tuple[float, float, float]]    # bone_name -> (rx, ry, rz) relative local rad
    joint_quats: Dict[str, Tuple[float, float, float, float]]      # bone_name -> (w, x, y, z) relative local quat
    end_effectors: Dict[str, Tuple[float, float, float]]          # "hand_L", "hand_R", "foot_L", "foot_R" world (m)
    contacts: Dict[str, bool]                                     # limb -> is_locked / in_contact
    commanded_velocity: Optional[Tuple[float, float, float]] = None # Optional controller goal velocity (m/s)
    source: str = "evaluated_armature"

    @property
    def root_yaw_deg(self) -> float:
        return self.root_orientation_euler_deg[2]


@dataclass(frozen=True)
class BodyVelocityState:
    """Derived differential kinematic velocities and accelerations at instant t."""
    time_sec: float
    dt: float                                                     # Time step used for differentiation (s)
    root_linear_velocity: Tuple[float, float, float]              # World frame (m/s)
    root_angular_velocity: Tuple[float, float, float]             # World frame (rad/s)
    root_angular_velocity_deg: Tuple[float, float, float]         # World frame (deg/s)
    pelvis_linear_velocity: Tuple[float, float, float]            # World frame (m/s)
    com_linear_velocity: Tuple[float, float, float]               # World frame (m/s)
    segment_linear_velocities: Dict[str, Tuple[float, float, float]]    # segment_id -> World CoM linear v (m/s)
    segment_angular_velocities: Dict[str, Tuple[float, float, float]]   # segment_id -> World angular v (rad/s)
    joint_angular_velocities: Dict[str, Tuple[float, float, float]]     # bone_name -> Local angular v in parent frame (rad/s)
    joint_angular_velocities_deg: Dict[str, Tuple[float, float, float]] # bone_name -> Local angular v (deg/s)
    end_effector_velocities: Dict[str, Tuple[float, float, float]]      # limb -> World linear v (m/s)
    root_linear_acceleration: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # World (m/s^2)
    root_angular_acceleration: Tuple[float, float, float] = (0.0, 0.0, 0.0) # World (rad/s^2)
    com_linear_acceleration: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # World (m/s^2)
    commanded_velocity: Optional[Tuple[float, float, float]] = None         # Controller reference velocity
    velocity_tracking_error_mps: Optional[float] = None                     # ||derived_v - commanded_v|| (m/s)

    @property
    def root_speed_mps(self) -> float:
        vx, vy, vz = self.root_linear_velocity
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    @property
    def root_horizontal_speed_mps(self) -> float:
        return math.hypot(self.root_linear_velocity[0], self.root_linear_velocity[1])

    @property
    def com_speed_mps(self) -> float:
        vx, vy, vz = self.com_linear_velocity
        return math.sqrt(vx * vx + vy * vy + vz * vz)

    @property
    def root_angular_speed_radps(self) -> float:
        wx, wy, wz = self.root_angular_velocity
        return math.sqrt(wx * wx + wy * wy + wz * wz)

    @property
    def root_angular_speed_degps(self) -> float:
        return math.degrees(self.root_angular_speed_radps)


@dataclass(frozen=True)
class BodyMotionState:
    """Unified composite body motion state containing both snapshot pose and differential velocities."""
    pose: BodyPoseSnapshot
    velocity: BodyVelocityState

    @property
    def frame(self) -> Optional[int]:
        return self.pose.frame

    @property
    def time_sec(self) -> float:
        return self.pose.time_sec

    @property
    def root_position(self) -> Tuple[float, float, float]:
        return self.pose.root_position

    @property
    def root_linear_velocity(self) -> Tuple[float, float, float]:
        return self.velocity.root_linear_velocity

    @property
    def root_angular_velocity(self) -> Tuple[float, float, float]:
        return self.velocity.root_angular_velocity

    @property
    def com_world(self) -> Tuple[float, float, float]:
        return self.pose.com_world

    @property
    def com_linear_velocity(self) -> Tuple[float, float, float]:
        return self.velocity.com_linear_velocity

    @property
    def speed_mps(self) -> float:
        return self.velocity.root_speed_mps

    @property
    def com_speed_mps(self) -> float:
        return self.velocity.com_speed_mps


# =============================================================================
# Sampling and Extraction Engine
# =============================================================================

def sample_body_pose_snapshot(
    armature_obj: Optional[bpy.types.Object] = None,
    root_obj: Optional[bpy.types.Object] = None,
    time_sec: float = 0.0,
    frame: Optional[int] = None,
    mass_distribution: Optional[BodyMassDistribution] = None,
    joint_model: Optional[JointModel] = None,
    commanded_velocity: Optional[Tuple[float, float, float]] = None,
    contacts_override: Optional[Mapping[str, bool]] = None,
    source: str = "evaluated_armature",
) -> BodyPoseSnapshot:
    """Sample a complete, evaluated BodyPoseSnapshot from the active Blender scene.

    Reads:
    - `CharacterRoot` World location and rotation quaternion.
    - `pelvis` PoseBone evaluated position and rotation quaternion.
    - Whole-Body CoM and 15 segment positions via `compute_whole_body_com`.
    - 17 anatomical joint evaluated relative rotations and quaternions via `extract_evaluated_bone_rotation_rad`.
    - 4 end effectors (`hand_L`, `hand_R`, `foot_L`, `foot_R`) evaluated world positions.
    - Contact lock state for feet and hands.
    """
    if armature_obj is None:
        armature_obj = bpy.data.objects.get("CharacterArmature")
    if armature_obj is None or armature_obj.type != "ARMATURE":
        raise RuntimeError("Valid CharacterArmature object not found in scene")

    if root_obj is None:
        root_obj = armature_obj.parent or bpy.data.objects.get("CharacterRoot")
    if root_obj is None:
        raise RuntimeError("Valid CharacterRoot object not found in scene")

    dist = mass_distribution or DEMPSTER_WINTER_15_SEGMENT_MODEL
    jm = joint_model or DEFAULT_HUMANOID_ROM_MODEL

    # 1. Root World Transform
    root_mat = root_obj.matrix_world
    root_pos = (root_mat.translation.x, root_mat.translation.y, root_mat.translation.z)
    root_q = root_mat.to_quaternion()
    root_quat = (root_q.w, root_q.x, root_q.y, root_q.z)
    root_euler = root_mat.to_euler("XYZ")
    root_euler_deg = (
        round(math.degrees(root_euler.x), 4),
        round(math.degrees(root_euler.y), 4),
        round(math.degrees(root_euler.z), 4),
    )

    # 2. Pelvis Pose
    pb_pelvis = armature_obj.pose.bones.get("pelvis")
    if pb_pelvis is not None:
        pelvis_world_pos_v = armature_obj.matrix_world @ pb_pelvis.head
        pelvis_pos = (pelvis_world_pos_v.x, pelvis_world_pos_v.y, pelvis_world_pos_v.z)
        pelvis_world_mat = (armature_obj.matrix_world.to_3x3() @ pb_pelvis.matrix.to_3x3())
        pelvis_q = pelvis_world_mat.to_quaternion()
        pelvis_quat = (pelvis_q.w, pelvis_q.x, pelvis_q.y, pelvis_q.z)
    else:
        pelvis_pos = root_pos
        pelvis_quat = root_quat

    # 3. Whole-Body CoM and Segments
    com_res = compute_whole_body_com(armature_obj, dist, update_scene=False)
    com_world = (com_res.com_world.x, com_res.com_world.y, com_res.com_world.z)

    seg_positions: Dict[str, Tuple[float, float, float]] = {}
    seg_orientations: Dict[str, Tuple[float, float, float, float]] = {}

    for seg_id, s_res in com_res.segments.items():
        seg_positions[seg_id] = (s_res.world_com.x, s_res.world_com.y, s_res.world_com.z)
        pb = armature_obj.pose.bones.get(s_res.bone_name)
        if pb is not None:
            seg_mat = armature_obj.matrix_world.to_3x3() @ pb.matrix.to_3x3()
            sq = seg_mat.to_quaternion()
            seg_orientations[seg_id] = (sq.w, sq.x, sq.y, sq.z)
        else:
            seg_orientations[seg_id] = root_quat

    # 4. Joint Rotations (Local relative to rest pose in parent space)
    joint_rot_rad: Dict[str, Tuple[float, float, float]] = {}
    joint_quats: Dict[str, Tuple[float, float, float, float]] = {}

    for bone_name in jm.joints:
        pb = armature_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        rx, ry, rz = extract_evaluated_bone_rotation_rad(pb)
        joint_rot_rad[bone_name] = (rx, ry, rz)
        jq = Euler((rx, ry, rz), "XYZ").to_quaternion()
        joint_quats[bone_name] = (jq.w, jq.x, jq.y, jq.z)

    # 5. End Effectors (hand_L, hand_R, foot_L, foot_R)
    end_effs: Dict[str, Tuple[float, float, float]] = {}
    contacts: Dict[str, bool] = {
        "foot_L": False,
        "foot_R": False,
        "hand_L": False,
        "hand_R": False,
    }

    # Feet (ankle / shin.tail)
    for side in ("L", "R"):
        p_shin = armature_obj.pose.bones.get(f"shin.{side}")
        if p_shin is not None:
            ankle_w = armature_obj.matrix_world @ p_shin.tail
            end_effs[f"foot_{side}"] = (ankle_w.x, ankle_w.y, ankle_w.z)
        ik_obj = bpy.data.objects.get(f"FootIK.{side}")
        if ik_obj is not None:
            contacts[f"foot_{side}"] = bool(ik_obj.get("is_locked", False))

    # Hands (wrist / forearm.tail)
    for side in ("L", "R"):
        p_fore = armature_obj.pose.bones.get(f"forearm.{side}")
        if p_fore is not None:
            wrist_w = armature_obj.matrix_world @ p_fore.tail
            end_effs[f"hand_{side}"] = (wrist_w.x, wrist_w.y, wrist_w.z)
        ik_obj = bpy.data.objects.get(f"HandIK.{side}")
        if ik_obj is not None:
            contacts[f"hand_{side}"] = bool(ik_obj.get("is_locked", False))

    if contacts_override is not None:
        contacts.update(contacts_override)

    return BodyPoseSnapshot(
        time_sec=time_sec,
        frame=frame,
        root_position=root_pos,
        root_orientation_quat=root_quat,
        root_orientation_euler_deg=root_euler_deg,
        pelvis_position=pelvis_pos,
        pelvis_orientation_quat=pelvis_quat,
        com_world=com_world,
        segment_positions=seg_positions,
        segment_orientations=seg_orientations,
        joint_rotations_rad=joint_rot_rad,
        joint_quats=joint_quats,
        end_effectors=end_effs,
        contacts=contacts,
        commanded_velocity=commanded_velocity,
        source=source,
    )


def sample_body_pose_from_controller_result(
    ctrl_res: WholeBodyControlResult,
    time_sec: float,
    frame: Optional[int] = None,
    armature_obj: Optional[bpy.types.Object] = None,
    root_obj: Optional[bpy.types.Object] = None,
    mass_distribution: Optional[BodyMassDistribution] = None,
    joint_model: Optional[JointModel] = None,
    commanded_velocity: Optional[Tuple[float, float, float]] = None,
) -> BodyPoseSnapshot:
    """Sample a BodyPoseSnapshot directly from a WholeBodyControlResult and its armature."""
    contacts_override = {}
    for eff_id in ("foot_L", "foot_R", "hand_L", "hand_R"):
        fb = ctrl_res.end_effectors.get(eff_id)
        if fb is not None:
            # An effector is locked if active and indicated in feedback or custom dict
            pass

    return sample_body_pose_snapshot(
        armature_obj=armature_obj,
        root_obj=root_obj,
        time_sec=time_sec,
        frame=frame,
        mass_distribution=mass_distribution,
        joint_model=joint_model,
        commanded_velocity=commanded_velocity,
        source="whole_body_controller",
    )


# =============================================================================
# Differential Kinematics Evaluator & Tracker
# =============================================================================

def compute_differential_velocity(
    curr: BodyPoseSnapshot,
    prev: BodyPoseSnapshot,
    dt: Optional[float] = None,
    prev_velocity: Optional[BodyVelocityState] = None,
) -> BodyVelocityState:
    """Compute complete differential velocity state between two sequential snapshots.

    Args:
        curr: Current pose snapshot at time t.
        prev: Previous pose snapshot at time t - dt.
        dt: Optional explicit delta time. If None, computes curr.time_sec - prev.time_sec.
        prev_velocity: Optional preceding velocity state to compute linear/angular accelerations.

    Returns:
        BodyVelocityState containing all linear and angular velocities.
    """
    effective_dt = dt if dt is not None else (curr.time_sec - prev.time_sec)
    if effective_dt <= 1e-9:
        effective_dt = 1e-6

    # 1. Root Linear & Angular Velocities
    root_v = linear_velocity(prev.root_position, curr.root_position, effective_dt)
    q_root_prev = Quaternion(prev.root_orientation_quat)
    q_root_curr = Quaternion(curr.root_orientation_quat)
    root_w = relative_angular_velocity(q_root_prev, q_root_curr, effective_dt, frame="world")
    root_w_tuple = (root_w.x, root_w.y, root_w.z)
    root_w_deg_tuple = (
        math.degrees(root_w.x),
        math.degrees(root_w.y),
        math.degrees(root_w.z),
    )

    # 2. Pelvis & CoM Linear Velocities
    pelvis_v = linear_velocity(prev.pelvis_position, curr.pelvis_position, effective_dt)
    com_v = linear_velocity(prev.com_world, curr.com_world, effective_dt)

    # 3. Segment Linear & Angular Velocities
    seg_v: Dict[str, Tuple[float, float, float]] = {}
    seg_w: Dict[str, Tuple[float, float, float]] = {}

    for seg_id, p_curr in curr.segment_positions.items():
        p_prev = prev.segment_positions.get(seg_id, p_curr)
        seg_v[seg_id] = linear_velocity(p_prev, p_curr, effective_dt)

        q_prev_s = Quaternion(prev.segment_orientations.get(seg_id, curr.segment_orientations[seg_id]))
        q_curr_s = Quaternion(curr.segment_orientations[seg_id])
        w_s = relative_angular_velocity(q_prev_s, q_curr_s, effective_dt, frame="world")
        seg_w[seg_id] = (w_s.x, w_s.y, w_s.z)

    # 4. Joint Angular Velocities (in parent bone local frame)
    joint_w: Dict[str, Tuple[float, float, float]] = {}
    joint_w_deg: Dict[str, Tuple[float, float, float]] = {}

    for bone_name, q_curr_t in curr.joint_quats.items():
        q_prev_t = prev.joint_quats.get(bone_name, q_curr_t)
        jq_prev = Quaternion(q_prev_t)
        jq_curr = Quaternion(q_curr_t)
        jw = relative_angular_velocity(jq_prev, jq_curr, effective_dt, frame="local")
        joint_w[bone_name] = (jw.x, jw.y, jw.z)
        joint_w_deg[bone_name] = (math.degrees(jw.x), math.degrees(jw.y), math.degrees(jw.z))

    # 5. End Effector Linear Velocities
    eff_v: Dict[str, Tuple[float, float, float]] = {}
    for eff_id, pos_curr in curr.end_effectors.items():
        pos_prev = prev.end_effectors.get(eff_id, pos_curr)
        eff_v[eff_id] = linear_velocity(pos_prev, pos_curr, effective_dt)

    # 6. Accelerations (if previous velocity is provided)
    if prev_velocity is not None and prev_velocity.dt > 1e-9:
        root_a = linear_acceleration(prev_velocity.root_linear_velocity, root_v, effective_dt)
        com_a = linear_acceleration(prev_velocity.com_linear_velocity, com_v, effective_dt)
        prev_root_w = Vector(prev_velocity.root_angular_velocity)
        root_alpha = (root_w - prev_root_w) / effective_dt
        root_alpha_tuple = (root_alpha.x, root_alpha.y, root_alpha.z)
    else:
        root_a = (0.0, 0.0, 0.0)
        com_a = (0.0, 0.0, 0.0)
        root_alpha_tuple = (0.0, 0.0, 0.0)

    # 7. Commanded vs Derived Velocity Comparison
    tracking_err = None
    if curr.commanded_velocity is not None:
        cmd_v = Vector(curr.commanded_velocity)
        der_v = Vector(root_v)
        tracking_err = (der_v - cmd_v).length

    return BodyVelocityState(
        time_sec=curr.time_sec,
        dt=effective_dt,
        root_linear_velocity=root_v,
        root_angular_velocity=root_w_tuple,
        root_angular_velocity_deg=root_w_deg_tuple,
        pelvis_linear_velocity=pelvis_v,
        com_linear_velocity=com_v,
        segment_linear_velocities=seg_v,
        segment_angular_velocities=seg_w,
        joint_angular_velocities=joint_w,
        joint_angular_velocities_deg=joint_w_deg,
        end_effector_velocities=eff_v,
        root_linear_acceleration=root_a,
        root_angular_acceleration=root_alpha_tuple,
        com_linear_acceleration=com_a,
        commanded_velocity=curr.commanded_velocity,
        velocity_tracking_error_mps=tracking_err,
    )


def create_zero_velocity_state(
    snapshot: BodyPoseSnapshot,
    dt: float = 1.0 / 24.0,
) -> BodyVelocityState:
    """Create a stationary zero-velocity state for an initial frame."""
    zeros_3 = (0.0, 0.0, 0.0)
    seg_zeros = {s: zeros_3 for s in snapshot.segment_positions}
    joint_zeros = {j: zeros_3 for j in snapshot.joint_rotations_rad}
    eff_zeros = {e: zeros_3 for e in snapshot.end_effectors}
    return BodyVelocityState(
        time_sec=snapshot.time_sec,
        dt=dt,
        root_linear_velocity=zeros_3,
        root_angular_velocity=zeros_3,
        root_angular_velocity_deg=zeros_3,
        pelvis_linear_velocity=zeros_3,
        com_linear_velocity=zeros_3,
        segment_linear_velocities=seg_zeros,
        segment_angular_velocities=seg_zeros,
        joint_angular_velocities=joint_zeros,
        joint_angular_velocities_deg=joint_zeros,
        end_effector_velocities=eff_zeros,
        root_linear_acceleration=zeros_3,
        root_angular_acceleration=zeros_3,
        com_linear_acceleration=zeros_3,
        commanded_velocity=snapshot.commanded_velocity,
        velocity_tracking_error_mps=0.0 if snapshot.commanded_velocity is not None else None,
    )


# =============================================================================
# BodyKinematicsTracker Class
# =============================================================================

class BodyKinematicsTracker:
    """Stateful body kinematics tracking coordinator.

    Provides sequential online frame updates and batch trajectory evaluation across animations.
    """

    def __init__(
        self,
        armature_obj: Optional[bpy.types.Object] = None,
        root_obj: Optional[bpy.types.Object] = None,
        mass_distribution: Optional[BodyMassDistribution] = None,
        joint_model: Optional[JointModel] = None,
        config: Optional[PipelineConfig] = None,
    ) -> None:
        self.config = config or PipelineConfig()
        if armature_obj is None:
            armature_obj = bpy.data.objects.get("CharacterArmature")
        self.armature_obj = armature_obj

        if root_obj is None and self.armature_obj is not None:
            root_obj = self.armature_obj.parent or bpy.data.objects.get("CharacterRoot")
        self.root_obj = root_obj

        self.mass_distribution = mass_distribution or DEMPSTER_WINTER_15_SEGMENT_MODEL
        self.joint_model = joint_model or DEFAULT_HUMANOID_ROM_MODEL

        self._prev_snapshot: Optional[BodyPoseSnapshot] = None
        self._prev_velocity: Optional[BodyVelocityState] = None
        self._history: List[BodyMotionState] = []

    def reset(self) -> None:
        """Reset internal history and tracking buffers."""
        self._prev_snapshot = None
        self._prev_velocity = None
        self._history.clear()

    def update(
        self,
        snapshot: BodyPoseSnapshot,
        dt: Optional[float] = None,
    ) -> BodyMotionState:
        """Process a new pose snapshot in causal sequential order and return the updated BodyMotionState."""
        if self._prev_snapshot is None:
            # First frame: initialize with zero velocity (or dt from config)
            default_dt = dt or (1.0 / self.config.fps)
            vel_state = create_zero_velocity_state(snapshot, dt=default_dt)
        else:
            vel_state = compute_differential_velocity(
                curr=snapshot,
                prev=self._prev_snapshot,
                dt=dt,
                prev_velocity=self._prev_velocity,
            )

        motion_state = BodyMotionState(pose=snapshot, velocity=vel_state)
        self._prev_snapshot = snapshot
        self._prev_velocity = vel_state
        self._history.append(motion_state)
        return motion_state

    def sample_and_update(
        self,
        time_sec: float,
        frame: Optional[int] = None,
        commanded_velocity: Optional[Tuple[float, float, float]] = None,
        dt: Optional[float] = None,
    ) -> BodyMotionState:
        """Sample current scene state and perform sequential differential update."""
        snap = sample_body_pose_snapshot(
            armature_obj=self.armature_obj,
            root_obj=self.root_obj,
            time_sec=time_sec,
            frame=frame,
            mass_distribution=self.mass_distribution,
            joint_model=self.joint_model,
            commanded_velocity=commanded_velocity,
        )
        return self.update(snap, dt=dt)

    def compute_trajectory_motion_states(
        self,
        snapshots: Sequence[BodyPoseSnapshot],
        method: str = "backward",
        default_dt: Optional[float] = None,
    ) -> List[BodyMotionState]:
        """Compute complete BodyMotionState trajectory from a pre-recorded sequence of snapshots.

        Methods:
            - "backward": Causal backward difference (v[k] = (p[k] - p[k-1]) / dt).
            - "central": 2nd-order central difference for interior frames (v[k] = (p[k+1] - p[k-1]) / 2dt).
        """
        n = len(snapshots)
        if n == 0:
            return []
        if n == 1:
            dt = default_dt or (1.0 / self.config.fps)
            return [BodyMotionState(pose=snapshots[0], velocity=create_zero_velocity_state(snapshots[0], dt=dt))]

        results: List[BodyMotionState] = []

        if method == "backward":
            prev_v = None
            for i, snap in enumerate(snapshots):
                if i == 0:
                    dt = snapshots[1].time_sec - snapshots[0].time_sec if snapshots[1].time_sec > snapshots[0].time_sec else (default_dt or (1.0 / self.config.fps))
                    vel = create_zero_velocity_state(snap, dt=dt)
                else:
                    vel = compute_differential_velocity(snap, snapshots[i - 1], prev_velocity=prev_v)
                prev_v = vel
                results.append(BodyMotionState(pose=snap, velocity=vel))
            return results

        elif method == "central":
            # Interior frames use central difference; endpoints use one-sided differences
            vel_states: List[BodyVelocityState] = []
            for i in range(n):
                if i == 0:
                    dt = snapshots[1].time_sec - snapshots[0].time_sec
                    vel = compute_differential_velocity(snapshots[1], snapshots[0], dt=dt)
                    vel = replace(vel, time_sec=snapshots[0].time_sec)
                elif i == n - 1:
                    dt = snapshots[n - 1].time_sec - snapshots[n - 2].time_sec
                    vel = compute_differential_velocity(snapshots[n - 1], snapshots[n - 2], dt=dt)
                else:
                    # Central difference: compare i+1 with i-1 over total span (t[i+1] - t[i-1])
                    dt_span = snapshots[i + 1].time_sec - snapshots[i - 1].time_sec
                    vel = compute_differential_velocity(snapshots[i + 1], snapshots[i - 1], dt=dt_span)
                    vel = replace(vel, time_sec=snapshots[i].time_sec, dt=dt_span * 0.5)
                vel_states.append(vel)

            # Compute accelerations via central difference on velocity states
            for i in range(n):
                snap = snapshots[i]
                v_curr = vel_states[i]
                if 0 < i < n - 1:
                    dt_span = snapshots[i + 1].time_sec - snapshots[i - 1].time_sec
                    if dt_span > 1e-9:
                        a_root = linear_velocity(vel_states[i - 1].root_linear_velocity, vel_states[i + 1].root_linear_velocity, dt_span)
                        a_com = linear_velocity(vel_states[i - 1].com_linear_velocity, vel_states[i + 1].com_linear_velocity, dt_span)
                        w_diff = Vector(vel_states[i + 1].root_angular_velocity) - Vector(vel_states[i - 1].root_angular_velocity)
                        alpha_root = tuple(w_diff / dt_span)
                        v_curr = replace(
                            v_curr,
                            root_linear_acceleration=a_root,
                            com_linear_acceleration=a_com,
                            root_angular_acceleration=alpha_root,
                        )
                results.append(BodyMotionState(pose=snap, velocity=v_curr))
            return results
        else:
            raise ValueError(f"Unknown differentiation method: '{method}', expected 'backward' or 'central'")


# =============================================================================
# Seamless Integration Helpers with MotionState
# =============================================================================

def enrich_motion_state_with_kinematics(
    motion_state: MotionState,
    body_motion_state: BodyMotionState,
) -> MotionState:
    """Enrich an existing MotionState with comprehensive body kinematics telemetry.

    Injects:
    - `params["com_world"]`: (x, y, z)
    - `params["com_linear_velocity"]`: (vx, vy, vz)
    - `params["root_angular_velocity_radps"]`: (wx, wy, wz)
    - `params["root_angular_velocity_degps"]`: (wx, wy, wz)
    - `params["segment_linear_velocities"]`: dict of segment speeds
    - `params["joint_angular_velocities_deg"]`: dict of joint angular speeds
    - `params["velocity_tracking_error_mps"]`: float

    Returns a new MotionState clone without mutating the original.
    """
    p = dict(motion_state.params)
    v = body_motion_state.velocity
    snap = body_motion_state.pose

    p["com_world"] = snap.com_world
    p["com_linear_velocity"] = v.com_linear_velocity
    p["root_angular_velocity_radps"] = v.root_angular_velocity
    p["root_angular_velocity_degps"] = v.root_angular_velocity_deg
    p["root_derived_linear_velocity"] = v.root_linear_velocity
    p["segment_linear_velocities"] = v.segment_linear_velocities
    p["joint_angular_velocities_deg"] = v.joint_angular_velocities_deg
    if v.velocity_tracking_error_mps is not None:
        p["velocity_tracking_error_mps"] = v.velocity_tracking_error_mps

    return motion_state.clone_with(params=p)
