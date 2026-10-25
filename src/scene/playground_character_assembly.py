"""Playground Character Assembly & Control Verification Module (Task 7A-1).

Responsible for:
1. Character assembly in `DynamicsPlayground`:
   Reuses existing `build_character`, `build_rig`, `bind_character_to_rig`, `setup_leg_ik`, `setup_arm_ik`.
2. Scene inspection & character inventory checks.
3. Stages A, B, C, D minimal control closed-loop execution.
4. Five-coordinate-space, CoM, and constraint truthfulness mathematical checks.
5. Stage E continuous walk execution via `MotionPlanner`, contact state persistence embedding,
   and derived blend artifact generation.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.character.builder import REQUIRED_PARTS, build_character, character_start_location, world_min_z
from src.config import PipelineConfig
from src.motion.body_kinematics import sample_body_pose_snapshot
from src.motion.contact_model import (
    ContactLifecycle,
    ContactType,
    DEFAULT_LIMB_LOCAL_ANCHORS,
    EnvironmentalSurface,
    SupportType,
    evaluate_limb_contacts_from_armature,
)
from src.motion.framework import (
    STAGE_TO_MOTION_MODE,
    MotionMode,
    MotionPlanner,
    StartStopWalkAction,
    forward_unit_vector_from_yaw,
    right_unit_vector_from_yaw,
    root_local_to_world_vector,
    world_to_root_local_vector,
)
from src.motion.joint_limits import (
    DEFAULT_HUMANOID_ROM_MODEL,
    extract_evaluated_bone_rotation_rad,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.rigid_link import (
    DEMPSTER_13_SEGMENT_MODEL,
    DEMPSTER_WINTER_15_SEGMENT_MODEL,
    compute_whole_body_com,
)
from src.motion.start_stop_walk import (
    _evaluate_gait_phase_and_envelopes,
    build_step_schedule,
    compute_forward_swing_point,
    evaluate_root_kinematics,
)
from src.motion.whole_body_controller import (
    WholeBodyControlTargets,
    WholeBodyController,
)
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    HAND_ROT_CONSTRAINT_NAMES,
    MAX_ARM_REACH,
    get_arm_ik_state,
    reset_arm_ik,
    setup_arm_ik,
)
from src.rig.builder import (
    BONE_HIERARCHY,
    BONE_SPECIFICATIONS,
    PART_TO_BONE_MAP,
    bind_character_to_rig,
    build_rig,
)
from src.rig.foot_contact import (
    evaluate_foot_support,
    lock_foot_contact,
    move_character_root_with_support,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    FOOT_ROT_CONSTRAINT_NAMES,
    HIP_X_OFFSET,
    IK_CONSTRAINT_NAMES,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    POLE_TARGET_NAMES,
    SHIN_LENGTH,
    THIGH_LENGTH,
    get_leg_ik_state,
    reset_leg_ik,
    setup_leg_ik,
)
from src.rig.pose import get_part_world_center, reset_pose
from src.scene.environment_query import DynamicsEnvironmentQuery
from src.scene.playground_evidence_exporter import _render_camera_to_png


def _setup_character_inspection_cameras(char_col: bpy.types.Collection) -> Dict[str, bpy.types.Object]:
    """Create dedicated front, side, and isometric cameras inside the 'Character' collection
    aimed at the character corridor on Surface_FlatGround (Y in [-8.0, -6.74], Z in [0.0, 1.82]).
    """
    specs = {
        "Task7A1_CharFrontCam": {
            "location": (0.0, -4.60, 1.15),
            "look_at": (0.0, -7.40, 0.92),
            "lens": 38.0,
        },
        "Task7A1_CharSideCam": {
            "location": (3.10, -7.40, 1.05),
            "look_at": (0.0, -7.40, 0.90),
            "lens": 38.0,
        },
        "Task7A1_CharIsoCam": {
            "location": (2.55, -5.15, 1.65),
            "look_at": (0.0, -7.40, 0.90),
            "lens": 35.0,
        },
    }

    cameras: Dict[str, bpy.types.Object] = {}
    for cam_name, spec in specs.items():
        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj is None:
            cam_data = bpy.data.cameras.new(cam_name)
            cam_obj = bpy.data.objects.new(cam_name, cam_data)
            char_col.objects.link(cam_obj)
        else:
            cam_data = cam_obj.data

        cam_data.lens = spec["lens"]
        cam_data.clip_start = 0.05
        cam_data.clip_end = 100.0
        loc = Vector(spec["location"])
        target = Vector(spec["look_at"])
        direction = (target - loc).normalized()
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam_obj.location = loc
        cam_obj.rotation_mode = "XYZ"
        cam_obj.rotation_euler = rot_quat.to_euler("XYZ")
        cameras[cam_name] = cam_obj

    bpy.context.view_layer.update()
    return cameras


def snapshot_playground_baseline(scene: bpy.types.Scene) -> Dict[str, Any]:
    """Capture baseline counts and station coordinates of `output/dynamics_playground.blend` prior to character assembly."""
    req_collections = [
        "Playground_Surfaces",
        "Playground_Visuals",
        "Playground_Lighting_Cameras",
        "Playground_Dynamics_Visualization",
    ]
    col_counts = {}
    for c_name in req_collections:
        col = bpy.data.collections.get(c_name)
        col_counts[c_name] = len(col.objects) if col is not None else 0

    scene.frame_set(1)
    bpy.context.view_layer.update()
    station_f1 = {}
    for s_idx in range(1, 6):
        com_obj = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
        body_obj = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
        station_f1[f"S{s_idx}"] = {
            "com_loc": tuple(round(v, 5) for v in com_obj.location) if com_obj else None,
            "body_loc": tuple(round(v, 5) for v in body_obj.location) if body_obj else None,
            "body_quat": tuple(round(v, 5) for v in body_obj.rotation_quaternion) if body_obj else None,
        }

    scene.frame_set(73)
    bpy.context.view_layer.update()
    station_f73 = {}
    for s_idx in range(1, 6):
        com_obj = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
        body_obj = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
        station_f73[f"S{s_idx}"] = {
            "com_loc": tuple(round(v, 5) for v in com_obj.location) if com_obj else None,
            "body_loc": tuple(round(v, 5) for v in body_obj.location) if body_obj else None,
            "body_quat": tuple(round(v, 5) for v in body_obj.rotation_quaternion) if body_obj else None,
        }

    scene.frame_set(1)
    bpy.context.view_layer.update()
    return {
        "collection_object_counts": col_counts,
        "station_f1": station_f1,
        "station_f73": station_f73,
    }


def assemble_character_in_playground(
    config: Optional[PipelineConfig] = None,
) -> Dict[str, Any]:
    """Assemble the real 13-part placeholder character and 19-bone CharacterArmature
    with bilateral Leg IK and Arm IK into the active DynamicsPlayground scene.
    """
    cfg = config or PipelineConfig()
    bpy.context.scene.frame_set(1)

    char_info = build_character(cfg)
    root_obj = char_info["root"]
    parts_map = char_info["parts"]

    arm_obj = build_rig(cfg, character_root=root_obj)
    bound_map = bind_character_to_rig(arm_obj, parts=parts_map)
    reset_pose(arm_obj)
    leg_ik_info = setup_leg_ik(arm_obj)
    reset_leg_ik(arm_obj)
    arm_ik_info = setup_arm_ik(arm_obj, initial_influence=0.0)
    reset_arm_ik(arm_obj)

    char_col = bpy.data.collections.get("Character")
    cameras = _setup_character_inspection_cameras(char_col)

    bpy.context.view_layer.update()
    return {
        "config": cfg,
        "root": root_obj,
        "armature": arm_obj,
        "parts": parts_map,
        "bound_map": bound_map,
        "leg_ik": leg_ik_info,
        "arm_ik": arm_ik_info,
        "collection": char_col,
        "cameras": cameras,
    }


def inspect_scene_and_character_inventory(
    baseline_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Build complete scene object, 19-bone skeleton, 13-part mesh, and IK/FK controller inspection report."""
    scene = bpy.context.scene
    scene.frame_set(1)
    bpy.context.view_layer.update()

    arm_objs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")

    # 1. Verify playground preservation against baseline snapshot
    current_snap = snapshot_playground_baseline(scene)
    playground_preserved = (
        current_snap["collection_object_counts"] == baseline_snapshot["collection_object_counts"]
        and current_snap["station_f1"] == baseline_snapshot["station_f1"]
        and current_snap["station_f73"] == baseline_snapshot["station_f73"]
    )

    # 2. 19 Bones Inspection
    expected_bone_names = [spec[0] for spec in BONE_SPECIFICATIONS]
    actual_bone_names = [b.name for b in arm_obj.data.bones] if arm_obj else []
    bones_report: Dict[str, Any] = {}
    for b_name in actual_bone_names:
        b = arm_obj.data.bones[b_name]
        pb = arm_obj.pose.bones[b_name]
        w_head = (arm_obj.matrix_world @ pb.head).to_tuple()
        w_tail = (arm_obj.matrix_world @ pb.tail).to_tuple()
        bones_report[b_name] = {
            "parent": b.parent.name if b.parent else None,
            "head_local": tuple(round(v, 4) for v in b.head_local),
            "tail_local": tuple(round(v, 4) for v in b.tail_local),
            "head_world": tuple(round(v, 4) for v in w_head),
            "tail_world": tuple(round(v, 4) for v in w_tail),
            "rest_length_m": round(float(b.length), 4),
            "posed_length_m": round(float((pb.tail - pb.head).length), 4),
            "use_connect": bool(b.use_connect),
            "use_inherit_rotation": bool(b.use_inherit_rotation),
            "constraints": [
                {
                    "name": c.name,
                    "type": c.type,
                    "influence": round(float(c.influence), 4),
                    "target": c.target.name if getattr(c, "target", None) else None,
                    "pole_target": c.pole_target.name if getattr(c, "pole_target", None) else None,
                    "chain_count": getattr(c, "chain_count", None),
                }
                for c in pb.constraints
            ],
        }

    # 3. 13 Mesh Parts Inspection
    parts_report: Dict[str, Any] = {}
    for part_name in REQUIRED_PARTS:
        p_obj = bpy.data.objects.get(part_name)
        if p_obj is not None:
            parts_report[part_name] = {
                "parent": p_obj.parent.name if p_obj.parent else None,
                "parent_type": p_obj.parent_type,
                "parent_bone": p_obj.parent_bone,
                "expected_bone": PART_TO_BONE_MAP[part_name],
                "modifiers": [m.type for m in p_obj.modifiers],
                "dimensions_m": tuple(round(v, 4) for v in p_obj.dimensions),
                "world_center_m": tuple(round(v, 4) for v in p_obj.matrix_world.translation),
                "world_min_z_m": round(world_min_z(p_obj), 5),
                "in_character_collection": "Character" in [c.name for c in p_obj.users_collection],
            }

    # 4. 8 IK & Pole Controllers Inspection
    controller_names = [
        IK_TARGET_NAMES["L"],
        IK_TARGET_NAMES["R"],
        POLE_TARGET_NAMES["L"],
        POLE_TARGET_NAMES["R"],
        ARM_IK_TARGET_NAMES["L"],
        ARM_IK_TARGET_NAMES["R"],
        ARM_POLE_TARGET_NAMES["L"],
        ARM_POLE_TARGET_NAMES["R"],
    ]
    controllers_report: Dict[str, Any] = {}
    for c_name in controller_names:
        c_obj = bpy.data.objects.get(c_name)
        if c_obj is not None:
            controllers_report[c_name] = {
                "type": c_obj.type,
                "parent": c_obj.parent.name if c_obj.parent else None,
                "world_location_m": tuple(round(v, 4) for v in c_obj.matrix_world.translation),
                "world_euler_deg": tuple(
                    round(math.degrees(v), 4) for v in c_obj.matrix_world.to_euler("XYZ")
                ),
                "is_locked": bool(c_obj.get("is_locked", False)) if "is_locked" in c_obj else None,
                "in_character_collection": "Character" in [c.name for c in c_obj.users_collection],
            }

    char_col = bpy.data.collections.get("Character")
    return {
        "armature_count_in_scene": len(arm_objs),
        "armature_names": [o.name for o in arm_objs],
        "character_collection_exists": char_col is not None,
        "character_collection_object_count": len(char_col.objects) if char_col else 0,
        "character_root_world_location_m": (
            tuple(round(v, 4) for v in root_obj.matrix_world.translation) if root_obj else None
        ),
        "bone_count": len(actual_bone_names),
        "bone_names_match_specification": (actual_bone_names == expected_bone_names),
        "bone_hierarchy_matches_specification": all(
            bones_report[b]["parent"] == BONE_HIERARCHY[b] for b in expected_bone_names
        ),
        "bones": bones_report,
        "mesh_part_count": len(parts_report),
        "mesh_parts": parts_report,
        "controller_count": len(controllers_report),
        "controllers": controllers_report,
        "playground_preserved": playground_preserved,
        "playground_collections_snapshot": current_snap["collection_object_counts"],
        "playground_stations_f1": current_snap["station_f1"],
        "playground_stations_f73": current_snap["station_f73"],
    }


def run_minimal_control_stages_verification(
    arm_obj: bpy.types.Object,
    root_obj: bpy.types.Object,
    config: PipelineConfig,
    env_query: DynamicsEnvironmentQuery,
    cameras: Dict[str, bpy.types.Object],
    evidence_dir: str,
    render_images: bool = True,
) -> Dict[str, Any]:
    """Execute and verify Stages A, B, C, and D through `KinematicBridgeExecutor.execute_frame()`
    -> `WholeBodyController.execute_frame()`.
    """
    scene = bpy.context.scene
    fps = float(config.fps)
    dt = 1.0 / fps

    bridge = KinematicBridgeExecutor(
        armature_obj=arm_obj,
        root_obj=root_obj,
        environment=env_query,
        default_fps=config.fps,
    )

    rendered_files: List[str] = []

    # -------------------------------------------------------------------------
    # Stage A: Static Standing Pose at (0.0, -8.0, 0.0) on Surface_FlatGround
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)
    reset_pose(arm_obj)
    reset_leg_ik(arm_obj)
    reset_arm_ik(arm_obj)

    start_x, start_y, start_z = character_start_location(config)
    gz_l = env_query.ground_height_at(start_x - HIP_X_OFFSET, start_y)
    gz_r = env_query.ground_height_at(start_x + HIP_X_OFFSET, start_y)

    pose_a = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(start_x, start_y, start_z),
        root_yaw_deg=0.0,
        speed_mps=0.0,
        accel_mps2=0.0,
        motion_mode=MotionMode.IDLE,
        dt=dt,
        pelvis_location=(0.0, 0.0, 0.0),
        pelvis_rotation_deg=(0.0, 0.0, 0.0),
        spine_rotation_deg=(0.0, 0.0, 0.0),
        neck_rotation_deg=(0.0, 0.0, 0.0),
        head_rotation_deg=(0.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=(start_x - HIP_X_OFFSET, start_y, gz_l + ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=(start_x + HIP_X_OFFSET, start_y, gz_r + ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={},
        active_step_index=-1,
        gait_phase=0.0,
        is_flight=False,
    )
    res_a = bridge.execute_frame(pose_a, keyframe=False, dt=dt)
    foot_l_min_z = world_min_z(bpy.data.objects["Foot_L"])
    foot_r_min_z = world_min_z(bpy.data.objects["Foot_R"])
    com_a = res_a.wbc_result.com_result.com_world

    stage_a_imgs = {}
    for view_key, cam_name in (
        ("front", "Task7A1_CharFrontCam"),
        ("side", "Task7A1_CharSideCam"),
        ("iso", "Task7A1_CharIsoCam"),
    ):
        img_path = os.path.join(evidence_dir, f"stage_A_static_{view_key}.png")
        if render_images:
            _render_camera_to_png(scene, cameras[cam_name], img_path)
            rendered_files.append(img_path)
        if os.path.isfile(img_path):
            stage_a_imgs[view_key] = os.path.relpath(img_path, config.project_root).replace("\\", "/")

    stage_a_report = {
        "success": bool(res_a.success),
        "root_world_position": tuple(round(v, 5) for v in res_a.wbc_result.root_world_position),
        "pelvis_world_position": tuple(round(v, 5) for v in res_a.wbc_result.pelvis_world_position),
        "com_world_m": (round(com_a.x, 5), round(com_a.y, 5), round(com_a.z, 5)),
        "max_end_effector_error_m": round(res_a.wbc_result.max_end_effector_error_m, 6),
        "foot_L_min_z_m": round(foot_l_min_z, 5),
        "foot_R_min_z_m": round(foot_r_min_z, 5),
        "has_rom_violation": bool(res_a.wbc_result.has_rom_violation),
        "support_type": res_a.support_type,
        "images": stage_a_imgs,
    }

    # -------------------------------------------------------------------------
    # Stage B: Finite Root Displacement & Non-Zero Yaw via Unified Control Chain
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)

    target_root_b = (0.25, -7.65, 0.0)
    target_yaw_b = 6.0
    pelvis_dz_b = -0.030
    rx_b, ry_b, _ = right_unit_vector_from_yaw(target_yaw_b)
    foot_l_world_b = (
        target_root_b[0] - HIP_X_OFFSET * rx_b,
        target_root_b[1] - HIP_X_OFFSET * ry_b,
        ANKLE_REST_Z,
    )
    foot_r_world_b = (
        target_root_b[0] + HIP_X_OFFSET * rx_b,
        target_root_b[1] + HIP_X_OFFSET * ry_b,
        ANKLE_REST_Z,
    )

    pose_b = KinematicPlannedPose(
        frame=2,
        time_seconds=dt,
        root_position=target_root_b,
        root_yaw_deg=target_yaw_b,
        speed_mps=0.20,
        accel_mps2=0.0,
        motion_mode=MotionMode.WALK,
        dt=dt,
        pelvis_location=(0.0, pelvis_dz_b, 0.0),
        pelvis_rotation_deg=(-1.5, 0.0, 0.0),
        spine_rotation_deg=(-3.0, 0.0, 0.0),
        neck_rotation_deg=(2.0, 0.0, 0.0),
        head_rotation_deg=(2.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=foot_l_world_b,
            is_locked=False,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=foot_r_world_b,
            is_locked=False,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={
            "upper_arm.L": (12.0, 0.0, -4.0),
            "forearm.L": (20.0, 0.0, 0.0),
            "upper_arm.R": (-12.0, 0.0, 4.0),
            "forearm.R": (20.0, 0.0, 0.0),
        },
        active_step_index=0,
        gait_phase=0.1,
        is_flight=False,
    )
    res_b = bridge.execute_frame(pose_b, keyframe=False, dt=dt)
    actual_root_b = root_obj.matrix_world.translation
    actual_yaw_b = math.degrees(root_obj.matrix_world.to_euler("XYZ").z)
    pelvis_center_b = get_part_world_center("Pelvis")
    torso_center_b = get_part_world_center("Torso")
    head_center_b = get_part_world_center("Head")

    stage_b_imgs = {}
    for view_key, cam_name in (
        ("front", "Task7A1_CharFrontCam"),
        ("side", "Task7A1_CharSideCam"),
    ):
        img_path = os.path.join(evidence_dir, f"stage_B_root_disp_{view_key}.png")
        if render_images:
            _render_camera_to_png(scene, cameras[cam_name], img_path)
            rendered_files.append(img_path)
        if os.path.isfile(img_path):
            stage_b_imgs[view_key] = os.path.relpath(img_path, config.project_root).replace("\\", "/")

    stage_b_report = {
        "success": bool(res_b.success),
        "has_rom_violation": bool(res_b.wbc_result.has_rom_violation),
        "requested_root_position_m": target_root_b,
        "actual_root_position_m": (round(actual_root_b.x, 5), round(actual_root_b.y, 5), round(actual_root_b.z, 5)),
        "root_position_error_m": round((actual_root_b - Vector(target_root_b)).length, 6),
        "requested_yaw_deg": target_yaw_b,
        "actual_yaw_deg": round(actual_yaw_b, 4),
        "pelvis_bone_world_m": tuple(round(v, 5) for v in res_b.wbc_result.pelvis_world_position),
        "pelvis_mesh_world_m": (round(pelvis_center_b.x, 5), round(pelvis_center_b.y, 5), round(pelvis_center_b.z, 5)),
        "torso_mesh_world_m": (round(torso_center_b.x, 5), round(torso_center_b.y, 5), round(torso_center_b.z, 5)),
        "head_mesh_world_m": (round(head_center_b.x, 5), round(head_center_b.y, 5), round(head_center_b.z, 5)),
        "max_end_effector_error_m": round(res_b.wbc_result.max_end_effector_error_m, 6),
        "images": stage_b_imgs,
    }

    # -------------------------------------------------------------------------
    # Stage C: Independent Single-Foot IK Control (Distinct L/R World Targets)
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)

    target_l_c = (-0.11, -8.05, 0.07)
    target_r_c = (0.14, -7.82, 0.21)
    rot_l_c = (0.0, 0.0, 0.0)
    rot_r_c = (-12.0, 0.0, 0.0)

    pose_c = KinematicPlannedPose(
        frame=3,
        time_seconds=2.0 * dt,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        speed_mps=0.15,
        accel_mps2=0.0,
        motion_mode=MotionMode.WALK,
        dt=dt,
        pelvis_location=(0.0, -0.035, 0.0),
        pelvis_rotation_deg=(-1.5, 2.0, 1.0),
        spine_rotation_deg=(-2.5, -2.5, -0.6),
        neck_rotation_deg=(1.8, 0.2, -0.2),
        head_rotation_deg=(1.8, 0.2, -0.2),
        foot_L=PlannedFootTarget(
            world_xyz=target_l_c,
            is_locked=False,
            rotation_deg=rot_l_c,
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=target_r_c,
            is_locked=False,
            rotation_deg=rot_r_c,
            contact_intent=False,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={
            "upper_arm.L": (18.0, 0.0, -4.0),
            "forearm.L": (24.0, 0.0, 0.0),
            "upper_arm.R": (-18.0, 0.0, 4.0),
            "forearm.R": (18.0, 0.0, 0.0),
        },
        active_step_index=0,
        gait_phase=0.25,
        is_flight=False,
    )
    res_c = bridge.execute_frame(pose_c, keyframe=False, dt=dt)
    leg_state_l = get_leg_ik_state(arm_obj, "L")
    leg_state_r = get_leg_ik_state(arm_obj, "R")
    thigh_len_l = (leg_state_l["knee_world"] - leg_state_l["hip_world"]).length
    shin_len_l = (leg_state_l["ankle_world"] - leg_state_l["knee_world"]).length
    thigh_len_r = (leg_state_r["knee_world"] - leg_state_r["hip_world"]).length
    shin_len_r = (leg_state_r["ankle_world"] - leg_state_r["knee_world"]).length
    foot_r_euler_rad = (arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].matrix).to_euler("XYZ")
    foot_r_euler_deg = tuple(math.degrees(v) for v in foot_r_euler_rad)

    stage_c_imgs = {}
    for view_key, cam_name in (
        ("front", "Task7A1_CharFrontCam"),
        ("side", "Task7A1_CharSideCam"),
    ):
        img_path = os.path.join(evidence_dir, f"stage_C_single_foot_ik_{view_key}.png")
        if render_images:
            _render_camera_to_png(scene, cameras[cam_name], img_path)
            rendered_files.append(img_path)
        if os.path.isfile(img_path):
            stage_c_imgs[view_key] = os.path.relpath(img_path, config.project_root).replace("\\", "/")

    stage_c_report = {
        "success": bool(res_c.success),
        "has_rom_violation": bool(res_c.wbc_result.has_rom_violation),
        "foot_L": {
            "requested_world_m": target_l_c,
            "actual_world_m": tuple(round(v, 5) for v in leg_state_l["ankle_world"]),
            "target_error_m": round(float(leg_state_l["target_error"]), 6),
            "thigh_length_m": round(float(thigh_len_l), 5),
            "shin_length_m": round(float(shin_len_l), 5),
            "knee_flexion_deg": round(float(leg_state_l["knee_flexion_deg"]), 3),
            "knee_forward_y_m": round(float(leg_state_l["knee_forward_y"]), 4),
            "no_stretch": (
                abs(float(thigh_len_l) - THIGH_LENGTH) < 1e-4
                and abs(float(shin_len_l) - SHIN_LENGTH) < 1e-4
            ),
            "no_flip": float(leg_state_l["knee_forward_y"]) > 0.01,
        },
        "foot_R": {
            "requested_world_m": target_r_c,
            "actual_world_m": tuple(round(v, 5) for v in leg_state_r["ankle_world"]),
            "target_error_m": round(float(leg_state_r["target_error"]), 6),
            "thigh_length_m": round(float(thigh_len_r), 5),
            "shin_length_m": round(float(shin_len_r), 5),
            "knee_flexion_deg": round(float(leg_state_r["knee_flexion_deg"]), 3),
            "knee_forward_y_m": round(float(leg_state_r["knee_forward_y"]), 4),
            "foot_world_euler_deg": tuple(round(v, 3) for v in foot_r_euler_deg),
            "no_stretch": (
                abs(float(thigh_len_r) - THIGH_LENGTH) < 1e-4
                and abs(float(shin_len_r) - SHIN_LENGTH) < 1e-4
            ),
            "no_flip": float(leg_state_r["knee_forward_y"]) > 0.01,
        },
        "images": stage_c_imgs,
    }

    # -------------------------------------------------------------------------
    # Stage D: Support-Foot World Locking under Root Displacement Sequence
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)

    locked_l_anchor_world = (-0.11, -8.00, 0.07)
    root_shift_steps = [
        (0.00, -8.00, 0.0),
        (-0.015, -7.96, 0.0),
        (-0.025, -7.92, 0.0),
        (-0.015, -7.88, 0.0),
        (0.00, -7.84, 0.0),
    ]
    swing_r_targets = [
        (0.11, -8.04, 0.07),
        (0.11, -7.99, 0.13),
        (0.11, -7.93, 0.17),
        (0.11, -7.87, 0.12),
        (0.11, -7.82, 0.07),
    ]

    stage_d_steps: List[Dict[str, Any]] = []
    stage_d_imgs = {}

    for step_idx, (r_xyz, sw_r_xyz) in enumerate(zip(root_shift_steps, swing_r_targets)):
        pose_d = KinematicPlannedPose(
            frame=10 + step_idx,
            time_seconds=(10 + step_idx) * dt,
            root_position=r_xyz,
            root_yaw_deg=0.0,
            speed_mps=0.20,
            accel_mps2=0.0,
            motion_mode=MotionMode.WALK,
            dt=dt,
            pelvis_location=(0.0, -0.034, 0.0),
            pelvis_rotation_deg=(-1.5, 0.0, 0.0),
            spine_rotation_deg=(-3.0, 0.0, 0.0),
            neck_rotation_deg=(2.0, 0.0, 0.0),
            head_rotation_deg=(2.0, 0.0, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=locked_l_anchor_world,
                is_locked=True,
                rotation_deg=(0.0, 0.0, 0.0),
                contact_intent=True,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=sw_r_xyz,
                is_locked=False,
                rotation_deg=(-8.0 if 0 < step_idx < 4 else 0.0, 0.0, 0.0),
                contact_intent=(step_idx in (0, 4)),
            ),
            hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
            hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
            fk_joint_rotations_deg={},
            active_step_index=0,
            gait_phase=step_idx * 0.125,
            is_flight=False,
        )
        res_d = bridge.execute_frame(pose_d, keyframe=False, dt=dt)
        sup_l = evaluate_foot_support(arm_obj, "L")
        ik_l_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]

        if step_idx in (0, 4):
            img_path = os.path.join(evidence_dir, f"stage_D_lock_step{step_idx}_side.png")
            if render_images:
                _render_camera_to_png(scene, cameras["Task7A1_CharSideCam"], img_path)
                rendered_files.append(img_path)
            if os.path.isfile(img_path):
                stage_d_imgs[f"step_{step_idx}_side"] = os.path.relpath(img_path, config.project_root).replace("\\", "/")

        stage_d_steps.append({
            "step_index": step_idx,
            "root_world_m": r_xyz,
            "swing_foot_R_target_m": sw_r_xyz,
            "wbc_success": bool(res_d.success),
            "foot_L_is_locked": bool(sup_l["is_locked"]),
            "foot_L_controller_parent": ik_l_obj.parent.name if ik_l_obj.parent else None,
            "foot_L_locked_ankle_world_m": tuple(round(v, 5) for v in sup_l["locked_ankle_world"]),
            "foot_L_actual_ankle_world_m": tuple(round(v, 5) for v in sup_l["foot_head_world"]),
            "controller_drift_m": round(float(sup_l["controller_drift"]), 6),
            "ankle_bone_drift_m": round(float(sup_l["ankle_bone_drift"]), 6),
            "mesh_center_drift_m": round(float(sup_l["mesh_center_drift"]), 6),
            "hip_to_target_dist_m": round(float(sup_l["hip_to_target_dist"]), 5),
            "is_reachable": bool(sup_l["is_reachable"]),
        })

    max_ctrl_drift = max(s["controller_drift_m"] for s in stage_d_steps)
    max_ankle_drift = max(s["ankle_bone_drift_m"] for s in stage_d_steps)
    max_mesh_drift = max(s["mesh_center_drift_m"] for s in stage_d_steps)

    stage_d_report = {
        "all_steps_succeeded": all(s["wbc_success"] and s["is_reachable"] for s in stage_d_steps),
        "locked_anchor_world_m": locked_l_anchor_world,
        "max_controller_drift_m": round(max_ctrl_drift, 6),
        "max_ankle_bone_drift_m": round(max_ankle_drift, 6),
        "max_mesh_center_drift_m": round(max_mesh_drift, 6),
        "steps": stage_d_steps,
        "images": stage_d_imgs,
    }

    return {
        "stage_A_static_standing": stage_a_report,
        "stage_B_root_displacement": stage_b_report,
        "stage_C_single_foot_ik": stage_c_report,
        "stage_D_support_foot_lock": stage_d_report,
        "rendered_files": rendered_files,
    }


# =============================================================================
# 4. Step 4: Mathematical Consistency Verifications (Section 五)
# =============================================================================

def run_mathematical_consistency_verifications(
    arm_obj: bpy.types.Object,
    root_obj: bpy.types.Object,
    config: PipelineConfig,
    env_query: DynamicsEnvironmentQuery,
) -> Dict[str, Any]:
    """Verify:
    1. 5 Coordinate Spaces under non-zero translation, non-zero yaw, and distinct L/R foot targets.
    2. Mass distribution & Whole-Body CoM (`src/motion/rigid_link.py`).
    3. Geometric Contact vs Dynamic Force distinction (`contact_model.py`, `foot_contact.py`, `environment_query.py`).
    4. Constraint Truthfulness (`JointModel` & `WholeBodyControlResult` error/ROM/unreachable reporting).
    """
    fps = float(config.fps)
    dt = 1.0 / fps
    bridge = KinematicBridgeExecutor(
        armature_obj=arm_obj,
        root_obj=root_obj,
        environment=env_query,
        default_fps=config.fps,
    )

    # -------------------------------------------------------------------------
    # 4.1 Five Coordinate Spaces Round-Trip Consistency
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)

    test_root_pos = (1.35, -7.25, 0.0)
    test_yaw_deg = 6.5
    rx, ry, _ = right_unit_vector_from_yaw(test_yaw_deg)
    fx, fy, _ = forward_unit_vector_from_yaw(test_yaw_deg)

    # Asymmetric foot targets in CharacterRoot local space -> transformed to World Space
    local_foot_l = (-0.12, -0.06, ANKLE_REST_Z)
    local_foot_r = (0.14, 0.16, 0.19)
    world_foot_l_offset = root_local_to_world_vector(local_foot_l, test_yaw_deg)
    world_foot_r_offset = root_local_to_world_vector(local_foot_r, test_yaw_deg)
    world_foot_l = (
        test_root_pos[0] + world_foot_l_offset[0],
        test_root_pos[1] + world_foot_l_offset[1],
        test_root_pos[2] + world_foot_l_offset[2],
    )
    world_foot_r = (
        test_root_pos[0] + world_foot_r_offset[0],
        test_root_pos[1] + world_foot_r_offset[1],
        test_root_pos[2] + world_foot_r_offset[2],
    )

    pose_coord = KinematicPlannedPose(
        frame=20,
        time_seconds=20 * dt,
        root_position=test_root_pos,
        root_yaw_deg=test_yaw_deg,
        speed_mps=0.22,
        accel_mps2=0.0,
        motion_mode=MotionMode.WALK,
        dt=dt,
        pelvis_location=(0.015, -0.032, 0.0),
        pelvis_rotation_deg=(-1.5, 3.0, 1.5),
        spine_rotation_deg=(-3.0, -3.5, -0.9),
        neck_rotation_deg=(2.0, 0.2, -0.3),
        head_rotation_deg=(2.0, 0.2, -0.3),
        foot_L=PlannedFootTarget(
            world_xyz=world_foot_l,
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=world_foot_r,
            is_locked=False,
            rotation_deg=(-10.0, 0.0, 0.0),
            contact_intent=False,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={},
        active_step_index=1,
        gait_phase=0.3,
        is_flight=False,
    )
    res_coord = bridge.execute_frame(pose_coord, keyframe=False, dt=dt)

    # (a) Vector round-trip: World <-> CharacterRoot Local Space
    test_vec_world = (0.45, -1.15, 0.30)
    vec_local = world_to_root_local_vector(test_vec_world, test_yaw_deg)
    vec_world_rt = root_local_to_world_vector(vec_local, test_yaw_deg)
    vec_rt_err = (Vector(test_vec_world) - Vector(vec_world_rt)).length

    # (b) Point round-trip across all 5 spaces:
    # PoseBone Local Space -> Armature Object Space -> CharacterRoot Local Space -> World Space -> IK End-Effector World Space
    pb_foot_r = arm_obj.pose.bones["foot.R"]
    bone_local_pt = Vector(DEFAULT_LIMB_LOCAL_ANCHORS["foot_R"])
    arm_space_pt = pb_foot_r.matrix @ bone_local_pt
    world_space_pt = arm_obj.matrix_world @ arm_space_pt
    root_local_pt = root_obj.matrix_world.inverted() @ world_space_pt
    world_from_root_pt = root_obj.matrix_world @ root_local_pt
    arm_from_world_pt = arm_obj.matrix_world.inverted() @ world_from_root_pt
    bone_local_rt = pb_foot_r.matrix.inverted() @ arm_from_world_pt

    point_chain_rt_err = (bone_local_pt - bone_local_rt).length
    arm_vs_root_matrix_diff = (arm_obj.matrix_world.translation - root_obj.matrix_world.translation).length

    # (c) IK End-Effector World Space vs Evaluated Bone Head World Space
    ik_l_world = bpy.data.objects[IK_TARGET_NAMES["L"]].matrix_world.translation
    ik_r_world = bpy.data.objects[IK_TARGET_NAMES["R"]].matrix_world.translation
    foot_l_head_world = arm_obj.matrix_world @ arm_obj.pose.bones["foot.L"].head
    foot_r_head_world = arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].head
    ik_l_err = (ik_l_world - foot_l_head_world).length
    ik_r_err = (ik_r_world - foot_r_head_world).length

    coordinate_spaces_report = {
        "non_zero_translation_m": test_root_pos,
        "non_zero_yaw_deg": test_yaw_deg,
        "distinct_foot_targets_world_m": {
            "foot_L": tuple(round(v, 5) for v in world_foot_l),
            "foot_R": tuple(round(v, 5) for v in world_foot_r),
        },
        "wbc_success": bool(res_coord.success),
        "world_to_root_local_vector_roundtrip_error_m": round(vec_rt_err, 9),
        "five_space_point_chain_roundtrip_error_m": round(point_chain_rt_err, 9),
        "armature_vs_root_origin_alignment_error_m": round(arm_vs_root_matrix_diff, 9),
        "ik_end_effector_vs_bone_head_error_m": {
            "foot_L": round(ik_l_err, 6),
            "foot_R": round(ik_r_err, 6),
        },
        "sample_point_in_all_5_spaces": {
            "1_pose_bone_local_m": tuple(round(v, 5) for v in bone_local_pt),
            "2_armature_object_m": tuple(round(v, 5) for v in arm_space_pt),
            "3_character_root_local_m": tuple(round(v, 5) for v in root_local_pt),
            "4_world_space_m": tuple(round(v, 5) for v in world_space_pt),
            "5_ik_effector_world_m": tuple(round(v, 5) for v in ik_r_world),
        },
    }

    # -------------------------------------------------------------------------
    # 4.2 Mass Distribution & Whole-Body Center of Mass (src/motion/rigid_link.py)
    # -------------------------------------------------------------------------
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)
    reset_pose(arm_obj)
    reset_leg_ik(arm_obj)
    reset_arm_ik(arm_obj)
    bridge.reset()

    # Neutral standing at (0.0, -8.0, 0.0)
    pose_stand = KinematicPlannedPose(
        frame=1,
        time_seconds=0.0,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        speed_mps=0.0,
        accel_mps2=0.0,
        motion_mode=MotionMode.IDLE,
        dt=dt,
        pelvis_location=(0.0, 0.0, 0.0),
        pelvis_rotation_deg=(0.0, 0.0, 0.0),
        spine_rotation_deg=(0.0, 0.0, 0.0),
        neck_rotation_deg=(0.0, 0.0, 0.0),
        head_rotation_deg=(0.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={},
    )
    bridge.execute_frame(pose_stand, keyframe=False, dt=dt)

    com_default = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    com_75kg = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL, total_mass_kg=75.0)
    com_13seg = compute_whole_body_com(arm_obj, DEMPSTER_13_SEGMENT_MODEL)
    ratio_sum = sum(s.mass_ratio for s in DEMPSTER_WINTER_15_SEGMENT_MODEL.segments)

    # Check bilateral symmetry in neutral standing
    symmetry_pairs = [
        ("upper_arm_L", "upper_arm_R"),
        ("forearm_L", "forearm_R"),
        ("hand_L", "hand_R"),
        ("thigh_L", "thigh_R"),
        ("shin_L", "shin_R"),
        ("foot_L", "foot_R"),
    ]
    pair_sym_errors = {}
    for seg_l, seg_r in symmetry_pairs:
        pl = com_default.segments[seg_l].world_com
        pr = com_default.segments[seg_r].world_com
        pair_sym_errors[f"{seg_l}_vs_{seg_r}"] = round(
            max(abs(pl.x + pr.x), abs(pl.y - pr.y), abs(pl.z - pr.z)), 7
        )

    # Check CoM shift when pelvis lowers (-0.06m), leans forward (-25 deg), and shifts right (+0.05m)
    pose_crouch = KinematicPlannedPose(
        frame=2,
        time_seconds=dt,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        speed_mps=0.0,
        accel_mps2=0.0,
        motion_mode=MotionMode.IDLE,
        dt=dt,
        pelvis_location=(0.05, -0.06, 0.0),
        pelvis_rotation_deg=(-5.0, 0.0, 0.0),
        spine_rotation_deg=(-25.0, 0.0, 0.0),
        neck_rotation_deg=(0.0, 0.0, 0.0),
        head_rotation_deg=(0.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        fk_joint_rotations_deg={},
    )
    bridge.execute_frame(pose_crouch, keyframe=False, dt=dt)
    com_crouch = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL)
    com_delta = com_crouch.com_world - com_default.com_world

    mass_and_com_report = {
        "model_15_name": DEMPSTER_WINTER_15_SEGMENT_MODEL.model_name,
        "segment_count_15": len(DEMPSTER_WINTER_15_SEGMENT_MODEL.segments),
        "default_total_mass_kg": com_default.total_mass_kg,
        "scaled_reference_mass_kg": com_75kg.total_mass_kg,
        "mass_ratio_sum": round(ratio_sum, 6),
        "segment_mass_ratios": {
            s.segment_id: s.mass_ratio for s in DEMPSTER_WINTER_15_SEGMENT_MODEL.segments
        },
        "neutral_standing_com_world_m": tuple(round(v, 5) for v in com_default.com_world),
        "neutral_standing_com_armature_m": tuple(round(v, 5) for v in com_default.com_armature),
        "neutral_standing_13seg_com_world_m": tuple(round(v, 5) for v in com_13seg.com_world),
        "bilateral_com_x_offset_m": round(abs(com_default.com_world.x), 7),
        "bilateral_segment_symmetry_errors_m": pair_sym_errors,
        "posture_change_com_world_m": tuple(round(v, 5) for v in com_crouch.com_world),
        "posture_change_com_delta_m": (
            round(com_delta.x, 5),
            round(com_delta.y, 5),
            round(com_delta.z, 5),
        ),
    }

    # -------------------------------------------------------------------------
    # 4.3 Geometric Contact Verification (contact_model.py, foot_contact.py, environment_query.py)
    # -------------------------------------------------------------------------
    # Query environment surface at character start
    surf_q_l = env_query.query_surface_at_point((-HIP_X_OFFSET, -8.0, 0.0))
    surf_q_r = env_query.query_surface_at_point((HIP_X_OFFSET, -8.0, 0.0))

    # Case 1: Dual Foot Lock (DOUBLE_STANCE)
    bridge.reset()
    res_dual = bridge.execute_frame(pose_stand, keyframe=False, dt=dt)
    flat_surfaces = [
        EnvironmentalSurface(
            surface_id="Surface_FlatGround",
            surface_type="ground",
            center_world=(0.0, -2.5, 0.0),
            normal_world=(0.0, 0.0, 1.0),
        )
    ]
    mc_dual = evaluate_limb_contacts_from_armature(
        armature_obj=arm_obj,
        surfaces=flat_surfaces,
        active_limb_targets={
            "foot_L": {
                "surface_id": "Surface_FlatGround",
                "target_world": (-HIP_X_OFFSET, -8.0, 0.0),
                "normal_world": (0.0, 0.0, 1.0),
                "contact_type": ContactType.UNILATERAL,
                "lifecycle": ContactLifecycle.ESTABLISHED,
            },
            "foot_R": {
                "surface_id": "Surface_FlatGround",
                "target_world": (HIP_X_OFFSET, -8.0, 0.0),
                "normal_world": (0.0, 0.0, 1.0),
                "contact_type": ContactType.UNILATERAL,
                "lifecycle": ContactLifecycle.ESTABLISHED,
            },
        },
    )
    comp_dual = mc_dual.check_all_contacts({
        "foot_L": (-HIP_X_OFFSET, -8.0, 0.0),
        "foot_R": (HIP_X_OFFSET, -8.0, 0.0),
    })

    # Case 2: Left Foot Lock + Right Foot Release (SINGLE_STANCE_L)
    pose_single_l = KinematicPlannedPose(
        frame=3,
        time_seconds=2 * dt,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        speed_mps=0.1,
        accel_mps2=0.0,
        motion_mode=MotionMode.WALK,
        dt=dt,
        pelvis_location=(0.0, -0.03, 0.0),
        pelvis_rotation_deg=(0.0, 0.0, 0.0),
        spine_rotation_deg=(0.0, 0.0, 0.0),
        neck_rotation_deg=(0.0, 0.0, 0.0),
        head_rotation_deg=(0.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=(HIP_X_OFFSET, -7.88, ANKLE_REST_Z + 0.12),
            is_locked=False,
            rotation_deg=(-10.0, 0.0, 0.0),
            contact_intent=False,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
    )
    res_single_l = bridge.execute_frame(pose_single_l, keyframe=False, dt=dt)

    # Case 3: Right Foot Lock + Left Foot Release (SINGLE_STANCE_R)
    pose_single_r = KinematicPlannedPose(
        frame=4,
        time_seconds=3 * dt,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        speed_mps=0.1,
        accel_mps2=0.0,
        motion_mode=MotionMode.WALK,
        dt=dt,
        pelvis_location=(0.0, -0.03, 0.0),
        pelvis_rotation_deg=(0.0, 0.0, 0.0),
        spine_rotation_deg=(0.0, 0.0, 0.0),
        neck_rotation_deg=(0.0, 0.0, 0.0),
        head_rotation_deg=(0.0, 0.0, 0.0),
        foot_L=PlannedFootTarget(
            world_xyz=(-HIP_X_OFFSET, -7.88, ANKLE_REST_Z + 0.12),
            is_locked=False,
            rotation_deg=(-10.0, 0.0, 0.0),
            contact_intent=False,
        ),
        foot_R=PlannedFootTarget(
            world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z),
            is_locked=True,
            rotation_deg=(0.0, 0.0, 0.0),
            contact_intent=True,
        ),
        hand_L=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
        hand_R=PlannedHandTarget(world_xyz=(0.0, 0.0, 0.0), enabled=False, contact_intent=False),
    )
    res_single_r = bridge.execute_frame(pose_single_r, keyframe=False, dt=dt)

    geometric_contact_report = {
        "surface_query_foot_L": {
            "surface_id": surf_q_l.surface_id,
            "surface_type": surf_q_l.surface_type,
            "contact_point_world_m": surf_q_l.contact_point_world,
            "surface_normal_world": surf_q_l.surface_normal_world,
            "signed_distance_m": round(surf_q_l.signed_distance, 6),
            "friction_coeff": surf_q_l.friction_coeff,
        },
        "surface_query_foot_R": {
            "surface_id": surf_q_r.surface_id,
            "surface_type": surf_q_r.surface_type,
            "contact_point_world_m": surf_q_r.contact_point_world,
            "surface_normal_world": surf_q_r.surface_normal_world,
            "signed_distance_m": round(surf_q_r.signed_distance, 6),
        },
        "dual_foot_lock": {
            "support_type": res_dual.support_type,
            "supporting_limbs": res_dual.motion_state.params.get("supporting_limbs", []),
            "foot_L_valid": bool(comp_dual["foot_L"].is_valid),
            "foot_R_valid": bool(comp_dual["foot_R"].is_valid),
            "foot_L_normal_dist_m": round(comp_dual["foot_L"].distance_normal_m, 6),
            "foot_L_slip_m": round(comp_dual["foot_L"].tangential_slip_m, 6),
        },
        "left_foot_lock_right_release": {
            "support_type": res_single_l.support_type,
            "supporting_limbs": res_single_l.motion_state.params.get("supporting_limbs", []),
            "foot_L_is_locked": bool(res_single_l.motion_state.contacts["foot_L"].is_locked),
            "foot_R_is_locked": bool(res_single_l.motion_state.contacts["foot_R"].is_locked),
            "foot_L_phase": res_single_l.motion_state.contacts["foot_L"].phase,
            "foot_R_phase": res_single_l.motion_state.contacts["foot_R"].phase,
        },
        "right_foot_lock_left_release": {
            "support_type": res_single_r.support_type,
            "supporting_limbs": res_single_r.motion_state.params.get("supporting_limbs", []),
            "foot_L_is_locked": bool(res_single_r.motion_state.contacts["foot_L"].is_locked),
            "foot_R_is_locked": bool(res_single_r.motion_state.contacts["foot_R"].is_locked),
            "foot_L_phase": res_single_r.motion_state.contacts["foot_L"].phase,
            "foot_R_phase": res_single_r.motion_state.contacts["foot_R"].phase,
        },
        "physical_semantics_boundary": (
            "Geometric contact (contact_model.py + foot_contact.py) enforces kinematic anchor pinning, "
            "normal gap/penetration, and tangential slip checks in meters; dynamic reaction forces (N) "
            "belong exclusively to contact_force_solver.py / forward_dynamics.py."
        ),
    }

    # -------------------------------------------------------------------------
    # 4.4 Constraint Truthfulness Verification (JointModel & WholeBodyController)
    # -------------------------------------------------------------------------
    wbc = WholeBodyController(armature_obj=arm_obj, root_obj=root_obj)
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)
    wbc.reset_all_controls()

    # Case 4A: Valid pose
    tgt_valid = WholeBodyControlTargets()
    tgt_valid.set_root((0.0, -8.0, 0.0), yaw_deg=0.0)
    tgt_valid.set_pelvis(location=(0.0, -0.02, 0.0), rotation_deg=(0.0, 0.0, 0.0))
    tgt_valid.set_foot("L", (-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, 0.0), is_locked=False)
    tgt_valid.set_foot("R", (HIP_X_OFFSET, -8.0, ANKLE_REST_Z), rotation_deg=(0.0, 0.0, 0.0), is_locked=False)
    res_valid = wbc.execute_frame(tgt_valid, enforce_rom_clamping=False)

    # Case 4B: Unreachable Foot Target (1.60m forward of hip > MAX_LEG_REACH = 0.82m)
    tgt_unreach = WholeBodyControlTargets()
    tgt_unreach.set_root((0.0, -8.0, 0.0), yaw_deg=0.0)
    tgt_unreach.set_foot("L", (-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=False)
    tgt_unreach.set_foot("R", (HIP_X_OFFSET, -6.30, 0.50), is_locked=False, clamp_reach=True)
    res_unreach = wbc.execute_frame(tgt_unreach, enforce_rom_clamping=False)

    # Case 4C: Anatomical ROM Violation (spine flexion -85 deg < min -30 deg; upper_arm.L Z +175 deg > max +150 deg)
    wbc.reset_all_controls()
    tgt_rom_viol = WholeBodyControlTargets()
    tgt_rom_viol.set_root((0.0, -8.0, 0.0), yaw_deg=0.0)
    tgt_rom_viol.set_trunk_posture(spine_deg=(-85.0, 0.0, 0.0))
    tgt_rom_viol.fk_joint_rotations_deg["upper_arm.L"] = (0.0, 0.0, 175.0)
    tgt_rom_viol.set_foot("L", (-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=False)
    tgt_rom_viol.set_foot("R", (HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=False)
    res_rom_viol = wbc.execute_frame(tgt_rom_viol, enforce_rom_clamping=False)

    # Case 4D: ROM Clamping Conflict (spine bent excessively while HandIK.L targets point dependent on unclamped spine)
    wbc.reset_all_controls()
    tgt_conflict = WholeBodyControlTargets()
    tgt_conflict.set_root((0.0, -8.0, 0.0), yaw_deg=0.0)
    tgt_conflict.set_trunk_posture(spine_deg=(85.0, 0.0, 0.0))  # Exceeds max +60 deg
    tgt_conflict.set_foot("L", (-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=False)
    tgt_conflict.set_foot("R", (HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=False)
    res_clamped = wbc.execute_frame(tgt_conflict, enforce_rom_clamping=True)

    wbc.reset_all_controls()

    constraint_truthfulness_report = {
        "valid_pose_case": {
            "success": bool(res_valid.success),
            "is_all_reachable": bool(res_valid.is_all_reachable),
            "has_rom_violation": bool(res_valid.has_rom_violation),
            "max_end_effector_error_m": round(res_valid.max_end_effector_error_m, 6),
            "unmet_constraint_count": len(res_valid.unmet_constraints),
        },
        "unreachable_target_case": {
            "requested_foot_R_world_m": (HIP_X_OFFSET, -6.30, 0.50),
            "actual_foot_R_world_m": tuple(
                round(v, 5) for v in res_unreach.end_effectors["foot_R"].actual_world_xyz
            ),
            "position_error_m": round(res_unreach.end_effectors["foot_R"].position_error_m, 5),
            "is_reachable": bool(res_unreach.end_effectors["foot_R"].is_reachable),
            "is_all_reachable": bool(res_unreach.is_all_reachable),
            "overall_success": bool(res_unreach.success),
            "unmet_categories": [u.category for u in res_unreach.unmet_constraints],
        },
        "rom_violation_case": {
            "has_rom_violation": bool(res_rom_viol.has_rom_violation),
            "overall_success": bool(res_rom_viol.success),
            "violated_joints": list(res_rom_viol.rom_validation.violations.keys()),
            "max_excess_deg": round(res_rom_viol.rom_validation.max_excess_deg, 3),
            "unmet_categories": [u.category for u in res_rom_viol.unmet_constraints],
        },
        "rom_clamp_reporting_case": {
            "initial_rom_valid": bool(res_clamped.rom_validation.is_valid),
            "overall_success_reported_truthfully_false": (not res_clamped.success),
            "unmet_categories": [u.category for u in res_clamped.unmet_constraints],
        },
    }

    return {
        "coordinate_spaces": coordinate_spaces_report,
        "mass_and_com": mass_and_com_report,
        "geometric_contact": geometric_contact_report,
        "constraint_truthfulness": constraint_truthfulness_report,
    }


# =============================================================================
# 5. Step 3 Stage E: Minimal Historical Action Reuse (StartStopWalkAction)
# =============================================================================


def run_stage_e_continuous_walk_in_playground(
    arm_obj: bpy.types.Object,
    root_obj: bpy.types.Object,
    config: PipelineConfig,
    env_query: DynamicsEnvironmentQuery,
    cameras: Dict[str, bpy.types.Object],
    output_blend_path: str,
    evidence_dir: str,
    render_visuals: bool = True,
) -> Dict[str, Any]:
    """Execute historical `StartStopWalkAction` via `MotionPlanner` inside `DynamicsPlayground`,
    embed canonical contact state metadata into `scene['task7a1_contact_state_records']`,
    keyframe `is_locked` on FootIK controls across all 204 frames, save the derived playable
    `.blend` artifact (`output/dynamics_playground_task7a1.blend`), and render keyframe PNGs.
    """
    scene = bpy.context.scene
    unlock_foot_contact(arm_obj, "L", reparent_to_root=True)
    unlock_foot_contact(arm_obj, "R", reparent_to_root=True)
    reset_pose(arm_obj)
    reset_leg_ik(arm_obj)
    reset_arm_ik(arm_obj)

    planner = MotionPlanner(config=config, armature_obj=arm_obj, environment=env_query)
    planner.add_action(StartStopWalkAction())
    plan_result = planner.execute()

    # -------------------------------------------------------------------------
    # Contact State Persistence Contract (Section 六)
    # -------------------------------------------------------------------------
    total_frames = len(plan_result["frame_records"])
    contact_records: List[Dict[str, Any]] = []
    transition_events: List[Dict[str, Any]] = []
    prev_support_side: Optional[str] = None

    foot_ik_l = bpy.data.objects.get("FootIK.L")
    foot_ik_r = bpy.data.objects.get("FootIK.R")

    for f_idx in range(1, total_frames + 1):
        rec = plan_result["frame_records"][f_idx - 1]
        ms = plan_result["states"][f_idx - 1]
        time_sec = round((f_idx - 1) / float(config.fps), 6)

        c_l = ms.contacts.get("foot_L") or ms.contacts.get("foot_l")
        c_r = ms.contacts.get("foot_R") or ms.contacts.get("foot_r")
        is_l_locked = bool(c_l.is_locked if c_l else False)
        is_r_locked = bool(c_r.is_locked if c_r else False)

        anchor_l = (
            [round(float(v), 6) for v in c_l.contact_world_xyz]
            if (is_l_locked and c_l and c_l.contact_world_xyz)
            else None
        )
        anchor_r = (
            [round(float(v), 6) for v in c_r.contact_world_xyz]
            if (is_r_locked and c_r and c_r.contact_world_xyz)
            else None
        )

        if is_l_locked and is_r_locked:
            support_side = "DOUBLE"
        elif is_l_locked:
            support_side = "LEFT"
        elif is_r_locked:
            support_side = "RIGHT"
        else:
            support_side = "FLIGHT"

        event_type = "NONE"
        if prev_support_side is not None and support_side != prev_support_side:
            event_type = f"{prev_support_side}_TO_{support_side}"
            transition_events.append({
                "frame": f_idx,
                "time_sec": time_sec,
                "from_side": prev_support_side,
                "to_side": support_side,
                "event_type": event_type,
                "anchor_L": anchor_l,
                "anchor_R": anchor_r,
            })
        prev_support_side = support_side

        contact_records.append({
            "frame": f_idx,
            "time_sec": time_sec,
            "left_foot_locked": is_l_locked,
            "right_foot_locked": is_r_locked,
            "support_side": support_side,
            "support_anchor_L": anchor_l,
            "support_anchor_R": anchor_r,
            "stage": rec.get("stage", ""),
            "step_k": rec.get("step_k", -1),
            "contact_event": event_type,
            "source": "runtime_recorded",
        })

        # Keyframe custom property is_locked on IK Empty controls for Blender UI/Graph Editor
        scene.frame_set(f_idx)
        if foot_ik_l is not None:
            foot_ik_l["is_locked"] = 1.0 if is_l_locked else 0.0
            foot_ik_l.keyframe_insert(data_path='["is_locked"]', frame=f_idx)
        if foot_ik_r is not None:
            foot_ik_r["is_locked"] = 1.0 if is_r_locked else 0.0
            foot_ik_r.keyframe_insert(data_path='["is_locked"]', frame=f_idx)

    contact_metadata_payload = {
        "schema_name": "Task7A1_ContactStatePersistence",
        "schema_version": "1.0",
        "blend_asset_version": "Task7A1_204f_v1",
        "action_id": "start_stop_walk",
        "total_frames": total_frames,
        "fps": config.fps,
        "character_armature": "CharacterArmature",
        "records": contact_records,
        "transition_events": transition_events,
    }

    # Persist directly into Blender Scene custom ID property (native to .blend binary)
    scene["task7a1_contact_state_records"] = json.dumps(contact_metadata_payload)

    # Save companion JSON file in docs/evidence/task7a1/
    companion_json_path = os.path.join(evidence_dir, "task7a1_contact_state_records.json")
    os.makedirs(os.path.dirname(companion_json_path), exist_ok=True)
    with open(companion_json_path, "w", encoding="utf-8") as f:
        json.dump(contact_metadata_payload, f, indent=2)

    overview_cam = bpy.data.objects.get("PlaygroundOverviewCam")
    if overview_cam is not None:
        scene.camera = overview_cam

    # Save derived Task 7A-1 playable scene
    os.makedirs(os.path.dirname(output_blend_path), exist_ok=True)
    bpy.ops.wm.save_mainfile(filepath=output_blend_path)

    sample_frames = (1, 24, 54, 78, 102, 126, 150, 174, 204)
    sampled_telemetry: List[Dict[str, Any]] = []
    keyframe_images: Dict[str, List[str]] = {"side": [], "front": [], "iso": []}

    for f_idx in sample_frames:
        scene.frame_set(f_idx)
        bpy.context.view_layer.update()

        com_res = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL, update_scene=False)
        rom_res = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm_obj, use_evaluated_ik=True)
        leg_l = get_leg_ik_state(arm_obj, "L")
        leg_r = get_leg_ik_state(arm_obj, "R")
        rec = plan_result["frame_records"][f_idx - 1]

        sampled_telemetry.append({
            "frame": f_idx,
            "stage": rec["stage"],
            "mode": rec["mode"],
            "root_world_m": tuple(round(v, 5) for v in root_obj.matrix_world.translation),
            "com_world_m": tuple(round(v, 5) for v in com_res.com_world),
            "speed_mps": rec["speed_mps"],
            "phase_L": rec["phase_l"],
            "phase_R": rec["phase_r"],
            "foot_L_ankle_world_m": tuple(round(v, 5) for v in leg_l["ankle_world"]),
            "foot_R_ankle_world_m": tuple(round(v, 5) for v in leg_r["ankle_world"]),
            "foot_L_target_error_m": round(float(leg_l["target_error"]), 6),
            "foot_R_target_error_m": round(float(leg_r["target_error"]), 6),
            "rom_is_valid": bool(rom_res.is_valid),
            "rom_max_excess_deg": round(rom_res.max_excess_deg, 4),
        })

        side_path = os.path.join(evidence_dir, f"stage_E_walk_f{f_idx:03d}_side.png")
        if render_visuals:
            _render_camera_to_png(scene, cameras["Task7A1_CharSideCam"], side_path)
        if os.path.isfile(side_path):
            keyframe_images["side"].append(
                os.path.relpath(side_path, config.project_root).replace("\\", "/")
            )

        if f_idx in (1, 54, 102, 150, 204):
            front_path = os.path.join(evidence_dir, f"stage_E_walk_f{f_idx:03d}_front.png")
            iso_path = os.path.join(evidence_dir, f"stage_E_walk_f{f_idx:03d}_iso.png")
            if render_visuals:
                _render_camera_to_png(scene, cameras["Task7A1_CharFrontCam"], front_path)
                _render_camera_to_png(scene, cameras["Task7A1_CharIsoCam"], iso_path)
            if os.path.isfile(front_path):
                keyframe_images["front"].append(
                    os.path.relpath(front_path, config.project_root).replace("\\", "/")
                )
            if os.path.isfile(iso_path):
                keyframe_images["iso"].append(
                    os.path.relpath(iso_path, config.project_root).replace("\\", "/")
                )

    scene.frame_set(1)
    bpy.context.view_layer.update()

    gif_path = os.path.join(evidence_dir, "task7a1_walk_preview.gif")
    gif_rel_path = (
        os.path.relpath(gif_path, config.project_root).replace("\\", "/")
        if os.path.isfile(gif_path)
        else "docs/evidence/task7a1/task7a1_walk_preview.gif"
    )

    return {
        "action_names": plan_result["action_names"],
        "total_frames": plan_result["total_frames"],
        "fps": plan_result["fps"],
        "start_root_y_m": plan_result["frame_records"][0]["root_y"],
        "end_root_y_m": plan_result["frame_records"][-1]["root_y"],
        "total_root_displacement_m": plan_result["total_root_displacement"],
        "peak_speed_mps": plan_result["peak_speed_mps"],
        "unreachable_count": plan_result["unreachable_count"],
        "step_count": len(plan_result["step_schedule"]),
        "output_blend_path": os.path.relpath(output_blend_path, config.project_root).replace("\\", "/"),
        "output_blend_size_bytes": os.path.getsize(output_blend_path) if os.path.exists(output_blend_path) else 0,
        "sampled_frames": sampled_telemetry,
        "keyframe_images": keyframe_images,
        "animated_gif_preview": gif_rel_path,
        "contact_state_metadata_version": contact_metadata_payload["blend_asset_version"],
        "companion_contact_records_json": os.path.relpath(companion_json_path, config.project_root).replace("\\", "/"),
    }
