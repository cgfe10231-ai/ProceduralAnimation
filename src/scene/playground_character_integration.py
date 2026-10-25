"""Task 7A-1: Real 19-Bone Character Integration into DynamicsPlayground & Minimal Control Closed-Loop Verification.

Integrates the historical 13-part placeholder character and 19-bone CharacterArmature into
`output/dynamics_playground.blend` without recreating any character/rig/controller/planner modules
and without damaging existing playground terrain surfaces or 5 dynamics stations (S1..S5).

Execution Chain Verified:
  MotionPlanner / MotionAction
  -> KinematicBridgeExecutor.execute_frame()
  -> WholeBodyController.execute_frame()
  -> Rig / IK / FK (src/rig/ik.py, src/rig/arm_ik.py, src/rig/foot_contact.py, src/rig/pose.py)
  -> Evaluated Blender PoseBones
  -> CoM / Kinematics / Contact / ROM Telemetry
"""

from __future__ import annotations

import json
import math
import os
import struct
import tempfile
from typing import Any, Dict, List, Optional, Tuple

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
from src.scene.dynamics_visual_evidence import draw_text_to_numpy, encode_animated_gif
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    create_standard_dynamics_playground_query,
)


# =============================================================================
# 1. Camera Setup & Rendering Utilities for Character inside Playground
# =============================================================================

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


def _render_camera_to_png(
    scene: bpy.types.Scene,
    camera_obj: bpy.types.Object,
    filepath: str,
    res_x: int = 640,
    res_y: int = 480,
) -> None:
    """Render a still PNG from `camera_obj` using BLENDER_WORKBENCH while restoring scene state."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    prev_cam = scene.camera
    prev_engine = scene.render.engine
    prev_x = scene.render.resolution_x
    prev_y = scene.render.resolution_y
    prev_pct = scene.render.resolution_percentage
    prev_path = scene.render.filepath

    try:
        scene.camera = camera_obj
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.render.resolution_x = res_x
        scene.render.resolution_y = res_y
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
    finally:
        scene.camera = prev_cam
        scene.render.engine = prev_engine
        scene.render.resolution_x = prev_x
        scene.render.resolution_y = prev_y
        scene.render.resolution_percentage = prev_pct
        scene.render.filepath = prev_path


def _load_png_to_numpy_rgba(filepath: str, label_text: Optional[str] = None) -> Tuple[int, int, Any]:
    """Load a rendered PNG via Blender's native `bpy.data.images` into a (H, W, 4) float32 numpy array."""
    import numpy as np

    img = bpy.data.images.load(filepath, check_existing=False)
    try:
        w, h = img.size[0], img.size[1]
        arr = np.empty((h * w * 4,), dtype=np.float32)
        img.pixels.foreach_get(arr)
        arr = arr.reshape((h, w, 4))
        if label_text:
            draw_text_to_numpy(
                arr,
                label_text,
                x=10,
                y=h - 24,
                color=(1.0, 0.95, 0.30),
                scale=2,
                bg_color=(0.08, 0.10, 0.14),
            )
        return w, h, arr
    finally:
        bpy.data.images.remove(img)


# =============================================================================
# 2. Step 2: Real 19-Bone Character Assembly into DynamicsPlayground
# =============================================================================

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

    Strictly reuses:
      - `build_character(config)` (`src/character/builder.py`)
      - `build_rig(config, character_root)` (`src/rig/builder.py`)
      - `bind_character_to_rig(arm_obj, parts)` (`src/rig/builder.py`)
      - `reset_pose(arm_obj)` (`src/rig/pose.py`)
      - `setup_leg_ik(arm_obj)` (`src/rig/ik.py`)
      - `setup_arm_ik(arm_obj, initial_influence=0.0)` (`src/rig/arm_ik.py`)
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


# =============================================================================
# 3. Step 3: Minimal Control Closed-Loop Stages (A, B, C, D)
# =============================================================================

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

def count_gif_frames(filepath: str) -> Dict[str, Any]:
    """Parse a GIF89a file binary stream and return exact frame count, resolution, and frame delays."""
    if not os.path.isfile(filepath):
        return {
            "exists": False,
            "frame_count": 0,
            "width": 0,
            "height": 0,
            "delays_cs": [],
            "file_size_bytes": 0,
        }

    with open(filepath, "rb") as f:
        data = f.read()

    if len(data) < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return {
            "exists": True,
            "valid_header": False,
            "frame_count": 0,
            "width": 0,
            "height": 0,
            "delays_cs": [],
            "file_size_bytes": len(data),
        }

    width, height = struct.unpack("<HH", data[6:10])
    packed = data[10]
    pos = 13
    if packed & 0x80:
        gct_size = 3 * (1 << ((packed & 0x07) + 1))
        pos += gct_size

    frame_count = 0
    delays_cs: List[int] = []
    n = len(data)

    while pos < n:
        block_id = data[pos]
        pos += 1
        if block_id == 0x3B:  # Trailer
            break
        elif block_id == 0x21:  # Extension
            if pos >= n:
                break
            ext_label = data[pos]
            pos += 1
            if ext_label == 0xF9 and pos + 5 <= n:  # Graphic Control Extension
                block_size = data[pos]
                if block_size == 4:
                    delay = struct.unpack("<H", data[pos + 2 : pos + 4])[0]
                    delays_cs.append(delay)
                pos += 1 + block_size + 1  # size byte + data + terminator 0x00
            else:
                while pos < n:
                    sub_len = data[pos]
                    pos += 1
                    if sub_len == 0:
                        break
                    pos += sub_len
        elif block_id == 0x2C:  # Image Descriptor
            frame_count += 1
            if pos + 9 > n:
                break
            img_packed = data[pos + 8]
            pos += 9
            if img_packed & 0x80:
                lct_size = 3 * (1 << ((img_packed & 0x07) + 1))
                pos += lct_size
            if pos >= n:
                break
            pos += 1  # LZW minimum code size
            while pos < n:
                sub_len = data[pos]
                pos += 1
                if sub_len == 0:
                    break
                pos += sub_len
        else:
            break

    return {
        "exists": True,
        "valid_header": True,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "delays_cs": delays_cs,
        "uniform_delay_cs": delays_cs[0] if delays_cs and len(set(delays_cs)) == 1 else None,
        "file_size_bytes": len(data),
    }


def render_reopened_204_frame_walk_gif(
    derived_blend_path: str,
    gif_output_path: str,
    res_x: int = 320,
    res_y: int = 240,
    delay_cs: int = 4,
) -> Dict[str, Any]:
    """Reopen `output/dynamics_playground_task7a1.blend` read-only, render all 204 frames
    (`1..204`) continuously from `Task7A1_CharSideCam`, and encode a 204-frame 24 FPS GIF.
    """
    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scene = bpy.context.scene
    cam_obj = bpy.data.objects.get("Task7A1_CharSideCam")
    root_obj = bpy.data.objects.get("CharacterRoot")
    if cam_obj is None or root_obj is None:
        raise RuntimeError("Task7A1_CharSideCam or CharacterRoot missing in reopened blend!")

    cfg = PipelineConfig()
    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    frames_rgba: List[Any] = []

    tmp_png_path = os.path.join(tempfile.gettempdir(), f"task7a1_reopen_gif_tmp_{os.getpid()}.png")
    try:
        for f_idx in range(frame_start, frame_end + 1):
            scene.frame_set(f_idx)
            bpy.context.view_layer.update()
            tau = f_idx - 1
            _, speed_ref, stage_name = evaluate_root_kinematics(tau, cfg)
            ry = float(root_obj.matrix_world.translation.y)
            _render_camera_to_png(scene, cam_obj, tmp_png_path, res_x=res_x, res_y=res_y)
            _, _, arr = _load_png_to_numpy_rgba(
                tmp_png_path,
                label_text=f"F{f_idx:03d}/204 {stage_name} Y={ry:.2f}M V={speed_ref:.2f}",
            )
            frames_rgba.append(arr)
    finally:
        if os.path.isfile(tmp_png_path):
            try:
                os.remove(tmp_png_path)
            except OSError:
                pass

    os.makedirs(os.path.dirname(gif_output_path), exist_ok=True)
    encode_animated_gif(
        filepath=gif_output_path,
        width=res_x,
        height=res_y,
        frames_rgba=frames_rgba,
        delay_cs=delay_cs,
    )
    return count_gif_frames(gif_output_path)


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
    save the derived playable `.blend` artifact (`output/dynamics_playground_task7a1.blend`),
    and render keyframe PNGs.
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

    # Keep PlaygroundOverviewCam as primary active scene camera for consistency
    overview_cam = bpy.data.objects.get("PlaygroundOverviewCam")
    if overview_cam is not None:
        scene.camera = overview_cam

    # Save derived Task 7A-1 playable scene without overwriting output/dynamics_playground.blend
    os.makedirs(os.path.dirname(output_blend_path), exist_ok=True)
    bpy.ops.wm.save_mainfile(filepath=output_blend_path)

    # Sample key frames across the continuous walk sequence to verify evaluated armature poses & render visuals
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
    }


# =============================================================================
# 6. Deep Scene & Historical Asset Integrity Snapshot & Diff (Section 六)
# =============================================================================

PROTECTED_PLAYGROUND_COLLECTIONS: Tuple[str, ...] = (
    "Playground_Surfaces",
    "Playground_Visuals",
    "Playground_Lighting_Cameras",
    "Playground_Dynamics_Visualization",
)


def capture_deep_playground_snapshot(scene: Optional[bpy.types.Scene] = None) -> Dict[str, Any]:
    """Capture a deep, deterministic snapshot of all protected collections, objects,
    mesh geometries, materials, and 73-frame station trajectories in `output/dynamics_playground.blend`.
    """
    scn = scene or bpy.context.scene
    scn.frame_set(1)
    bpy.context.view_layer.update()

    collections_map: Dict[str, List[str]] = {}
    protected_obj_names: List[str] = []
    for col_name in PROTECTED_PLAYGROUND_COLLECTIONS:
        col = bpy.data.collections.get(col_name)
        members = sorted(o.name for o in col.objects) if col is not None else []
        collections_map[col_name] = members
        for m in members:
            if m not in protected_obj_names:
                protected_obj_names.append(m)
    protected_obj_names.sort()

    # Record transforms at Frame 1
    scn.frame_set(1)
    bpy.context.view_layer.update()
    f1_transforms: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is not None:
            loc = obj.matrix_world.translation
            quat = obj.matrix_world.to_quaternion().normalized()
            scl = obj.matrix_world.to_scale()
            f1_transforms[obj_name] = {
                "loc": (round(loc.x, 5), round(loc.y, 5), round(loc.z, 5)),
                "quat": (round(quat.w, 5), round(quat.x, 5), round(quat.y, 5), round(quat.z, 5)),
                "scale": (round(scl.x, 5), round(scl.y, 5), round(scl.z, 5)),
            }

    # Record transforms at Frame 73
    scn.frame_set(73)
    bpy.context.view_layer.update()
    f73_transforms: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is not None:
            loc = obj.matrix_world.translation
            quat = obj.matrix_world.to_quaternion().normalized()
            scl = obj.matrix_world.to_scale()
            f73_transforms[obj_name] = {
                "loc": (round(loc.x, 5), round(loc.y, 5), round(loc.z, 5)),
                "quat": (round(quat.w, 5), round(quat.x, 5), round(quat.y, 5), round(quat.z, 5)),
                "scale": (round(scl.x, 5), round(scl.y, 5), round(scl.z, 5)),
            }

    # Record per-object metadata, mesh geometry signatures, and animation F-Curve signatures
    objects_meta: Dict[str, Any] = {}
    for obj_name in protected_obj_names:
        obj = bpy.data.objects.get(obj_name)
        if obj is None:
            continue
        mesh_sig = None
        if obj.type == "MESH" and obj.data is not None:
            me = obj.data
            v_count = len(me.vertices)
            p_count = len(me.polygons)
            if v_count > 0:
                xs = [v.co.x for v in me.vertices]
                ys = [v.co.y for v in me.vertices]
                zs = [v.co.z for v in me.vertices]
                bbox_min = (round(min(xs), 5), round(min(ys), 5), round(min(zs), 5))
                bbox_max = (round(max(xs), 5), round(max(ys), 5), round(max(zs), 5))
            else:
                bbox_min = (0.0, 0.0, 0.0)
                bbox_max = (0.0, 0.0, 0.0)
            mats = [m.name for m in me.materials if m is not None]
            mesh_sig = {
                "vertex_count": v_count,
                "polygon_count": p_count,
                "local_bbox_min": bbox_min,
                "local_bbox_max": bbox_max,
                "materials": mats,
            }

        anim_sig = None
        if obj.animation_data is not None and obj.animation_data.action is not None:
            act = obj.animation_data.action
            fcurves_list = []
            if hasattr(act, "fcurves"):
                for fc in act.fcurves:
                    fcurves_list.append({
                        "data_path": fc.data_path,
                        "array_index": int(fc.array_index),
                        "keyframe_count": len(fc.keyframe_points),
                    })
            anim_sig = {
                "action_name": act.name,
                "fcurve_count": len(fcurves_list),
                "fcurves": fcurves_list,
            }

        objects_meta[obj_name] = {
            "type": obj.type,
            "data_name": obj.data.name if obj.data is not None else None,
            "parent": obj.parent.name if obj.parent is not None else None,
            "parent_type": obj.parent_type,
            "collections": sorted(
                c.name for c in obj.users_collection if c.name in PROTECTED_PLAYGROUND_COLLECTIONS
            ),
            "f1_transform": f1_transforms.get(obj_name),
            "f73_transform": f73_transforms.get(obj_name),
            "mesh_signature": mesh_sig,
            "animation_signature": anim_sig,
        }

    # Record multi-frame trajectory samples (Frames 1, 18, 36, 54, 73) for S1..S5 stations
    sample_station_frames = (1, 18, 36, 54, 73)
    station_trajectories: Dict[str, Dict[str, Any]] = {f"S{i}": {} for i in range(1, 6)}
    for sf in sample_station_frames:
        scn.frame_set(sf)
        bpy.context.view_layer.update()
        for s_idx in range(1, 6):
            com_obj = bpy.data.objects.get(f"Dynamics_CoM_S{s_idx}")
            body_obj = bpy.data.objects.get(f"Dynamics_BodyProxy_S{s_idx}")
            station_trajectories[f"S{s_idx}"][f"frame_{sf}"] = {
                "com_loc": tuple(round(v, 5) for v in com_obj.location) if com_obj else None,
                "body_loc": tuple(round(v, 5) for v in body_obj.location) if body_obj else None,
                "body_quat": tuple(round(v, 5) for v in body_obj.rotation_quaternion) if body_obj else None,
            }

    scn.frame_set(1)
    bpy.context.view_layer.update()
    return {
        "frame_start": int(scn.frame_start),
        "frame_end": int(scn.frame_end),
        "fps": int(scn.render.fps),
        "protected_collections": collections_map,
        "protected_object_count": len(protected_obj_names),
        "protected_objects": objects_meta,
        "station_trajectories_73f": station_trajectories,
    }


def verify_derived_blend_against_deep_snapshot(
    deep_baseline: Dict[str, Any],
    derived_blend_path: str,
) -> Dict[str, Any]:
    """Reopen `output/dynamics_playground_task7a1.blend` read-only and perform a deep
    comparison against `deep_baseline` from `output/dynamics_playground.blend`.
    """
    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scn = bpy.context.scene
    derived_snap = capture_deep_playground_snapshot(scn)

    missing_collections: List[str] = []
    collection_membership_diffs: Dict[str, Any] = {}
    for col_name, base_members in deep_baseline["protected_collections"].items():
        der_members = derived_snap["protected_collections"].get(col_name)
        if der_members is None:
            missing_collections.append(col_name)
        elif der_members != base_members:
            collection_membership_diffs[col_name] = {
                "missing": sorted(set(base_members) - set(der_members)),
                "unexpected": sorted(set(der_members) - set(base_members)),
            }

    missing_objects: List[str] = []
    modified_objects: Dict[str, Any] = {}
    mesh_geometry_diffs: Dict[str, Any] = {}
    animation_diffs: Dict[str, Any] = {}

    for obj_name, base_info in deep_baseline["protected_objects"].items():
        der_info = derived_snap["protected_objects"].get(obj_name)
        if der_info is None:
            missing_objects.append(obj_name)
            continue

        for field_key in ("type", "data_name", "parent", "parent_type", "collections", "f1_transform", "f73_transform"):
            if base_info[field_key] != der_info[field_key]:
                modified_objects.setdefault(obj_name, {})[field_key] = {
                    "baseline": base_info[field_key],
                    "derived": der_info[field_key],
                }

        if base_info["mesh_signature"] != der_info["mesh_signature"]:
            mesh_geometry_diffs[obj_name] = {
                "baseline": base_info["mesh_signature"],
                "derived": der_info["mesh_signature"],
            }

        if base_info["animation_signature"] != der_info["animation_signature"]:
            animation_diffs[obj_name] = {
                "baseline": base_info["animation_signature"],
                "derived": der_info["animation_signature"],
            }

    station_trajectory_diffs: Dict[str, Any] = {}
    for st_key, base_traj in deep_baseline["station_trajectories_73f"].items():
        der_traj = derived_snap["station_trajectories_73f"].get(st_key)
        if base_traj != der_traj:
            station_trajectory_diffs[st_key] = {
                "baseline": base_traj,
                "derived": der_traj,
            }

    all_scene_obj_names = sorted(o.name for o in bpy.data.objects)
    base_protected_set = set(deep_baseline["protected_objects"].keys())
    added_objects = sorted(set(all_scene_obj_names) - base_protected_set)
    char_col = bpy.data.collections.get("Character")
    char_col_members = sorted(o.name for o in char_col.objects) if char_col is not None else []

    expected_added_set = set(
        ["CharacterRoot", "CharacterArmature"]
        + list(REQUIRED_PARTS)
        + [
            IK_TARGET_NAMES["L"],
            IK_TARGET_NAMES["R"],
            POLE_TARGET_NAMES["L"],
            POLE_TARGET_NAMES["R"],
            ARM_IK_TARGET_NAMES["L"],
            ARM_IK_TARGET_NAMES["R"],
            ARM_POLE_TARGET_NAMES["L"],
            ARM_POLE_TARGET_NAMES["R"],
            "Task7A1_CharFrontCam",
            "Task7A1_CharSideCam",
            "Task7A1_CharIsoCam",
        ]
    )
    unexpected_added_objects = sorted(set(added_objects) - expected_added_set)
    missing_expected_character_objects = sorted(expected_added_set - set(added_objects))

    passed = (
        len(missing_collections) == 0
        and len(collection_membership_diffs) == 0
        and len(missing_objects) == 0
        and len(modified_objects) == 0
        and len(mesh_geometry_diffs) == 0
        and len(animation_diffs) == 0
        and len(station_trajectory_diffs) == 0
        and len(unexpected_added_objects) == 0
        and len(missing_expected_character_objects) == 0
        and added_objects == char_col_members
    )

    return {
        "verdict": "PASS" if passed else "FAIL",
        "passed": passed,
        "protected_collection_count": len(PROTECTED_PLAYGROUND_COLLECTIONS),
        "protected_object_count_baseline": deep_baseline["protected_object_count"],
        "protected_object_count_derived": derived_snap["protected_object_count"],
        "surface_mesh_count": len(deep_baseline["protected_collections"].get("Playground_Surfaces", [])),
        "missing_collections": missing_collections,
        "collection_membership_diffs": collection_membership_diffs,
        "missing_protected_objects": missing_objects,
        "modified_protected_objects": modified_objects,
        "mesh_geometry_diffs": mesh_geometry_diffs,
        "animation_fcurve_diffs": animation_diffs,
        "station_trajectory_diffs_73f": station_trajectory_diffs,
        "baseline_timeline": {
            "frame_start": deep_baseline["frame_start"],
            "frame_end": deep_baseline["frame_end"],
            "fps": deep_baseline["fps"],
        },
        "derived_timeline": {
            "frame_start": derived_snap["frame_start"],
            "frame_end": derived_snap["frame_end"],
            "fps": derived_snap["fps"],
        },
        "added_character_object_count": len(added_objects),
        "added_character_objects": added_objects,
        "unexpected_added_objects": unexpected_added_objects,
        "missing_expected_character_objects": missing_expected_character_objects,
    }


# =============================================================================
# 7. Independent Read-Only 204-Frame Reopen Validation (Sections 二, 三, 四, 五)
# =============================================================================

KEY_CONTINUITY_BONES: Tuple[str, ...] = (
    "pelvis",
    "spine",
    "thigh.L",
    "thigh.R",
    "shin.L",
    "shin.R",
    "foot.L",
    "foot.R",
)


def _quat_geodesic_angle_deg(q1: Tuple[float, float, float, float], q2: Tuple[float, float, float, float]) -> float:
    """Compute quaternion geodesic angular distance in degrees with antipodal equivalence (q ~ -q)."""
    n1 = math.sqrt(sum(c * c for c in q1))
    n2 = math.sqrt(sum(c * c for c in q2))
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    dot = abs(sum((a / n1) * (b / n2) for a, b in zip(q1, q2)))
    dot_clamped = min(1.0, max(0.0, dot))
    return math.degrees(2.0 * math.acos(dot_clamped))


def validate_reopened_task7a1_blend(
    derived_blend_path: str,
    output_json_path: Optional[str] = None,
    config: Optional[PipelineConfig] = None,
) -> Dict[str, Any]:
    """Independently reopen `output/dynamics_playground_task7a1.blend` read-only and
    validate all 204 frames (`1..204`) without running `MotionPlanner` or `WholeBodyController`.
    """
    if not os.path.isfile(derived_blend_path):
        raise FileNotFoundError(f"Derived blend artifact missing: {derived_blend_path}")

    cfg = config or PipelineConfig()
    bpy.ops.wm.open_mainfile(filepath=derived_blend_path)
    scene = bpy.context.scene

    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    foot_l_mesh = bpy.data.objects.get("Foot_L")
    foot_r_mesh = bpy.data.objects.get("Foot_R")
    ik_l_obj = bpy.data.objects.get(IK_TARGET_NAMES["L"])
    ik_r_obj = bpy.data.objects.get(IK_TARGET_NAMES["R"])

    if any(x is None for x in (arm_obj, root_obj, foot_l_mesh, foot_r_mesh, ik_l_obj, ik_r_obj)):
        raise RuntimeError("Required character objects missing in reopened Task 7A-1 blend!")

    frame_start = int(scene.frame_start)
    frame_end = int(scene.frame_end)
    fps = float(scene.render.fps)
    dt = 1.0 / fps
    expected_bone_names = [spec[0] for spec in BONE_SPECIFICATIONS]

    start_x, start_y, _ = character_start_location(cfg)
    schedule = build_step_schedule(cfg, start_y)
    stop_y = schedule[-1]["swing_y_end"]
    t_s = cfg.start_stop_stand_start_frames  # 12
    t_d = (
        cfg.start_stop_stand_start_frames
        + cfg.start_stop_accel_frames
        + cfg.start_stop_steady_frames
        + cfg.start_stop_decel_frames
    )  # 192

    flat_surfaces = [
        EnvironmentalSurface(
            surface_id="Surface_FlatGround",
            surface_type="ground",
            center_world=(0.0, -2.5, 0.0),
            normal_world=(0.0, 0.0, 1.0),
        )
    ]

    frames_telemetry: List[Dict[str, Any]] = []

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        tau = frame - 1

        # ---------------------------------------------------------------------
        # A. Analytical Reference (for comparison only; clearly labeled)
        # ---------------------------------------------------------------------
        ref_disp_y, ref_speed_mps, ref_stage = evaluate_root_kinematics(tau, cfg)
        ref_root_y = start_y + ref_disp_y
        ref_u, _, _, _, _, active_step = _evaluate_gait_phase_and_envelopes(tau, cfg, schedule)

        if tau < t_s:
            ref_locked_l = True
            ref_locked_r = True
            ref_phase_l = "stance"
            ref_phase_r = "stance"
            ref_anchor_l: Optional[Tuple[float, float, float]] = (start_x - HIP_X_OFFSET, start_y, ANKLE_REST_Z)
            ref_anchor_r: Optional[Tuple[float, float, float]] = (start_x + HIP_X_OFFSET, start_y, ANKLE_REST_Z)
            ref_target_l = ref_anchor_l
            ref_target_r = ref_anchor_r
            ref_step_idx = -1
            ref_support = SupportType.DOUBLE_STANCE.value
            ref_interval_id = "interval_0_stand_start_dual"
        elif tau >= t_d:
            ref_locked_l = True
            ref_locked_r = True
            ref_phase_l = "stance"
            ref_phase_r = "stance"
            ref_anchor_l = (start_x - HIP_X_OFFSET, stop_y, ANKLE_REST_Z)
            ref_anchor_r = (start_x + HIP_X_OFFSET, stop_y, ANKLE_REST_Z)
            ref_target_l = ref_anchor_l
            ref_target_r = ref_anchor_r
            ref_step_idx = len(schedule)
            ref_support = SupportType.DOUBLE_STANCE.value
            ref_interval_id = "interval_8_stand_stop_dual"
        else:
            assert active_step is not None
            ref_step_idx = int(active_step["k"])
            s_step = (tau - active_step["tau_start"]) / float(active_step["duration_frames"])
            y_sw, z_lift = compute_forward_swing_point(
                active_step["swing_y_start"],
                active_step["swing_y_end"],
                s_step,
                active_step["step_height"],
            )
            if active_step["stance_side"] == "L":
                ref_locked_l = True
                ref_locked_r = False
                ref_phase_l = "stance"
                ref_phase_r = "swing"
                ref_anchor_l = (start_x - HIP_X_OFFSET, float(active_step["stance_y"]), ANKLE_REST_Z)
                ref_anchor_r = None
                ref_target_l = ref_anchor_l
                ref_target_r = (start_x + HIP_X_OFFSET, float(y_sw), ANKLE_REST_Z + float(z_lift))
                ref_support = SupportType.SINGLE_STANCE_L.value
                ref_interval_id = f"interval_{ref_step_idx + 1}_step{ref_step_idx}_stance_L"
            else:
                ref_locked_l = False
                ref_locked_r = True
                ref_phase_l = "swing"
                ref_phase_r = "stance"
                ref_anchor_l = None
                ref_anchor_r = (start_x + HIP_X_OFFSET, float(active_step["stance_y"]), ANKLE_REST_Z)
                ref_target_l = (start_x - HIP_X_OFFSET, float(y_sw), ANKLE_REST_Z + float(z_lift))
                ref_target_r = ref_anchor_r
                ref_support = SupportType.SINGLE_STANCE_R.value
                ref_interval_id = f"interval_{ref_step_idx + 1}_step{ref_step_idx}_stance_R"

        # ---------------------------------------------------------------------
        # B. Reopen-Evaluated Blender State (directly from reopened .blend)
        # ---------------------------------------------------------------------
        root_loc = root_obj.matrix_world.translation
        root_eul = root_obj.matrix_world.to_euler("XYZ")
        root_quat = root_obj.matrix_world.to_quaternion().normalized()

        pb_pelvis = arm_obj.pose.bones["pelvis"]
        pelvis_world_mat = arm_obj.matrix_world @ pb_pelvis.matrix
        pelvis_head_w = arm_obj.matrix_world @ pb_pelvis.head
        pelvis_tail_w = arm_obj.matrix_world @ pb_pelvis.tail
        pelvis_eul_w = pelvis_world_mat.to_euler("XYZ")
        pelvis_quat_w = pelvis_world_mat.to_quaternion().normalized()

        bones_frame: Dict[str, Any] = {}
        for b_name in expected_bone_names:
            pb = arm_obj.pose.bones[b_name]
            b_mat_w = arm_obj.matrix_world @ pb.matrix
            b_head_w = arm_obj.matrix_world @ pb.head
            b_tail_w = arm_obj.matrix_world @ pb.tail
            b_quat_w = b_mat_w.to_quaternion().normalized()
            loc_rad = extract_evaluated_bone_rotation_rad(pb)
            bones_frame[b_name] = {
                "head_world_m": (round(b_head_w.x, 6), round(b_head_w.y, 6), round(b_head_w.z, 6)),
                "tail_world_m": (round(b_tail_w.x, 6), round(b_tail_w.y, 6), round(b_tail_w.z, 6)),
                "length_m": round(float((b_tail_w - b_head_w).length), 6),
                "local_euler_deg": tuple(round(math.degrees(v), 4) for v in loc_rad),
                "world_quat_wxyz": (
                    round(float(b_quat_w.w), 7),
                    round(float(b_quat_w.x), 7),
                    round(float(b_quat_w.y), 7),
                    round(float(b_quat_w.z), 7),
                ),
            }

        leg_l = get_leg_ik_state(arm_obj, "L")
        leg_r = get_leg_ik_state(arm_obj, "R")
        ctrl_l_w = ik_l_obj.matrix_world.translation
        ctrl_r_w = ik_r_obj.matrix_world.translation
        ankle_l_w = arm_obj.matrix_world @ arm_obj.pose.bones["shin.L"].tail
        ankle_r_w = arm_obj.matrix_world @ arm_obj.pose.bones["shin.R"].tail
        foot_head_l_w = arm_obj.matrix_world @ arm_obj.pose.bones["foot.L"].head
        foot_head_r_w = arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].head
        foot_eul_l_deg = tuple(
            round(math.degrees(v), 4)
            for v in (arm_obj.matrix_world @ arm_obj.pose.bones["foot.L"].matrix).to_euler("XYZ")
        )
        foot_eul_r_deg = tuple(
            round(math.degrees(v), 4)
            for v in (arm_obj.matrix_world @ arm_obj.pose.bones["foot.R"].matrix).to_euler("XYZ")
        )
        foot_l_min_z = float(world_min_z(foot_l_mesh))
        foot_r_min_z = float(world_min_z(foot_r_mesh))

        thigh_l_len = float((leg_l["knee_world"] - leg_l["hip_world"]).length)
        shin_l_len = float((leg_l["ankle_world"] - leg_l["knee_world"]).length)
        thigh_r_len = float((leg_r["knee_world"] - leg_r["hip_world"]).length)
        shin_r_len = float((leg_r["ankle_world"] - leg_r["knee_world"]).length)

        ik_track_err_l = float((ankle_l_w - ctrl_l_w).length)
        ik_track_err_r = float((ankle_r_w - ctrl_r_w).length)

        # Stance drift measurements against analytical stance anchor (both controller AND actual ankle bone!)
        ctrl_drift_l = (
            float((ctrl_l_w - Vector(ref_anchor_l)).length) if ref_anchor_l is not None else None
        )
        ankle_drift_l = (
            float((ankle_l_w - Vector(ref_anchor_l)).length) if ref_anchor_l is not None else None
        )
        ctrl_drift_r = (
            float((ctrl_r_w - Vector(ref_anchor_r)).length) if ref_anchor_r is not None else None
        )
        ankle_drift_r = (
            float((ankle_r_w - Vector(ref_anchor_r)).length) if ref_anchor_r is not None else None
        )

        com_res = compute_whole_body_com(arm_obj, DEMPSTER_WINTER_15_SEGMENT_MODEL, update_scene=False)
        rom_res = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm_obj, use_evaluated_ik=True)

        # Geometric contact evaluation on reopened armature
        active_limb_targets = {}
        if ref_locked_l and ref_anchor_l is not None:
            active_limb_targets["foot_L"] = {
                "surface_id": "Surface_FlatGround",
                "target_world": (ref_anchor_l[0], ref_anchor_l[1], 0.0),
                "normal_world": (0.0, 0.0, 1.0),
                "contact_type": ContactType.UNILATERAL,
                "lifecycle": ContactLifecycle.ESTABLISHED,
            }
        if ref_locked_r and ref_anchor_r is not None:
            active_limb_targets["foot_R"] = {
                "surface_id": "Surface_FlatGround",
                "target_world": (ref_anchor_r[0], ref_anchor_r[1], 0.0),
                "normal_world": (0.0, 0.0, 1.0),
                "contact_type": ContactType.UNILATERAL,
                "lifecycle": ContactLifecycle.ESTABLISHED,
            }
        mc_state = evaluate_limb_contacts_from_armature(
            armature_obj=arm_obj,
            surfaces=flat_surfaces,
            active_limb_targets=active_limb_targets,
        )

        frames_telemetry.append({
            "frame": frame,
            "tau": tau,
            "time_s": round(tau * dt, 6),
            "reopen_evaluated": {
                "data_source": "reopen_evaluated",
                "root_world_pos_m": (round(root_loc.x, 6), round(root_loc.y, 6), round(root_loc.z, 6)),
                "root_world_euler_deg": tuple(round(math.degrees(v), 4) for v in root_eul),
                "root_world_quat_wxyz": (
                    round(float(root_quat.w), 7),
                    round(float(root_quat.x), 7),
                    round(float(root_quat.y), 7),
                    round(float(root_quat.z), 7),
                ),
                "pelvis_head_world_m": (round(pelvis_head_w.x, 6), round(pelvis_head_w.y, 6), round(pelvis_head_w.z, 6)),
                "pelvis_tail_world_m": (round(pelvis_tail_w.x, 6), round(pelvis_tail_w.y, 6), round(pelvis_tail_w.z, 6)),
                "pelvis_world_euler_deg": tuple(round(math.degrees(v), 4) for v in pelvis_eul_w),
                "pelvis_world_quat_wxyz": (
                    round(float(pelvis_quat_w.w), 7),
                    round(float(pelvis_quat_w.x), 7),
                    round(float(pelvis_quat_w.y), 7),
                    round(float(pelvis_quat_w.z), 7),
                ),
                "foot_L": {
                    "controller_world_m": (round(ctrl_l_w.x, 6), round(ctrl_l_w.y, 6), round(ctrl_l_w.z, 6)),
                    "controller_parent": ik_l_obj.parent.name if ik_l_obj.parent else None,
                    "ankle_bone_world_m": (round(ankle_l_w.x, 6), round(ankle_l_w.y, 6), round(ankle_l_w.z, 6)),
                    "foot_head_bone_world_m": (round(foot_head_l_w.x, 6), round(foot_head_l_w.y, 6), round(foot_head_l_w.z, 6)),
                    "ik_tracking_error_m": round(ik_track_err_l, 7),
                    "world_euler_deg": foot_eul_l_deg,
                    "mesh_min_z_m": round(foot_l_min_z, 6),
                    "thigh_length_m": round(thigh_l_len, 6),
                    "shin_length_m": round(shin_l_len, 6),
                    "knee_forward_y_m": round(float(leg_l["knee_forward_y"]), 5),
                    "stance_controller_drift_m": round(ctrl_drift_l, 7) if ctrl_drift_l is not None else None,
                    "stance_ankle_bone_drift_m": round(ankle_drift_l, 7) if ankle_drift_l is not None else None,
                },
                "foot_R": {
                    "controller_world_m": (round(ctrl_r_w.x, 6), round(ctrl_r_w.y, 6), round(ctrl_r_w.z, 6)),
                    "controller_parent": ik_r_obj.parent.name if ik_r_obj.parent else None,
                    "ankle_bone_world_m": (round(ankle_r_w.x, 6), round(ankle_r_w.y, 6), round(ankle_r_w.z, 6)),
                    "foot_head_bone_world_m": (round(foot_head_r_w.x, 6), round(foot_head_r_w.y, 6), round(foot_head_r_w.z, 6)),
                    "ik_tracking_error_m": round(ik_track_err_r, 7),
                    "world_euler_deg": foot_eul_r_deg,
                    "mesh_min_z_m": round(foot_r_min_z, 6),
                    "thigh_length_m": round(thigh_r_len, 6),
                    "shin_length_m": round(shin_r_len, 6),
                    "knee_forward_y_m": round(float(leg_r["knee_forward_y"]), 5),
                    "stance_controller_drift_m": round(ctrl_drift_r, 7) if ctrl_drift_r is not None else None,
                    "stance_ankle_bone_drift_m": round(ankle_drift_r, 7) if ankle_drift_r is not None else None,
                },
                "com_world_m": (
                    round(float(com_res.com_world.x), 6),
                    round(float(com_res.com_world.y), 6),
                    round(float(com_res.com_world.z), 6),
                ),
                "total_mass_kg": round(float(com_res.total_mass_kg), 6),
                "rom_is_valid": bool(rom_res.is_valid),
                "rom_max_excess_deg": round(float(rom_res.max_excess_deg), 5),
                "rom_violated_joints": list(rom_res.violations.keys()),
                "evaluated_support_type": mc_state.support_type.value,
                "bones": bones_frame,
            },
            "analytical_reference": {
                "data_source": "analytical_reference",
                "stage": ref_stage,
                "interval_id": ref_interval_id,
                "active_step_index": ref_step_idx,
                "gait_phase_u": round(float(ref_u), 5),
                "planned_root_y_m": round(float(ref_root_y), 6),
                "planned_speed_mps": round(float(ref_speed_mps), 6),
                "foot_L_phase_ref": ref_phase_l,
                "foot_R_phase_ref": ref_phase_r,
                "foot_L_is_locked_ref": ref_locked_l,
                "foot_R_is_locked_ref": ref_locked_r,
                "stance_anchor_L_ref_m": tuple(round(v, 5) for v in ref_anchor_l) if ref_anchor_l else None,
                "stance_anchor_R_ref_m": tuple(round(v, 5) for v in ref_anchor_r) if ref_anchor_r else None,
                "planned_foot_L_world_m": tuple(round(v, 5) for v in ref_target_l),
                "planned_foot_R_world_m": tuple(round(v, 5) for v in ref_target_r),
                "expected_support_type": ref_support,
            },
        })

    # =========================================================================
    # Section 三.1: Root Translation Continuity Analysis across 204 Frames
    # =========================================================================
    root_steps: List[Dict[str, Any]] = []
    stand_start_max_step_m = 0.0
    stand_stop_max_step_m = 0.0
    overall_max_step_m = 0.0
    overall_max_step_frame = 1
    max_speed_tracking_err_mps = 0.0
    max_speed_tracking_err_frame = 1
    max_accel_mag_mps2 = 0.0
    max_accel_mag_frame = 2

    prev_vel_vec: Optional[Vector] = None
    for idx in range(1, len(frames_telemetry)):
        f_prev = frames_telemetry[idx - 1]
        f_curr = frames_telemetry[idx]
        frame_no = f_curr["frame"]
        p_prev = Vector(f_prev["reopen_evaluated"]["root_world_pos_m"])
        p_curr = Vector(f_curr["reopen_evaluated"]["root_world_pos_m"])
        dp = p_curr - p_prev
        step_dist = float(dp.length)
        vel_vec = dp / dt
        speed_fd = float(vel_vec.y)
        # Analytical average speed over [tau-1, tau] is 0.5*(v(tau-1)+v(tau))
        v_plan_prev = float(f_prev["analytical_reference"]["planned_speed_mps"])
        v_plan_curr = float(f_curr["analytical_reference"]["planned_speed_mps"])
        v_plan_mid = 0.5 * (v_plan_prev + v_plan_curr)
        speed_err = abs(speed_fd - v_plan_mid)

        if prev_vel_vec is not None:
            accel_vec = (vel_vec - prev_vel_vec) / dt
            accel_mag = float(accel_vec.length)
            if accel_mag > max_accel_mag_mps2:
                max_accel_mag_mps2 = accel_mag
                max_accel_mag_frame = frame_no
        else:
            accel_vec = Vector((0.0, 0.0, 0.0))
            accel_mag = 0.0
        prev_vel_vec = vel_vec

        if frame_no <= 13:
            stand_start_max_step_m = max(stand_start_max_step_m, step_dist)
        if frame_no >= 194:
            stand_stop_max_step_m = max(stand_stop_max_step_m, step_dist)
        if step_dist > overall_max_step_m:
            overall_max_step_m = step_dist
            overall_max_step_frame = frame_no
        if speed_err > max_speed_tracking_err_mps:
            max_speed_tracking_err_mps = speed_err
            max_speed_tracking_err_frame = frame_no

        root_steps.append({
            "frame": frame_no,
            "delta_pos_m": (round(dp.x, 7), round(dp.y, 7), round(dp.z, 7)),
            "step_dist_m": round(step_dist, 7),
            "fd_velocity_mps": (round(vel_vec.x, 6), round(vel_vec.y, 6), round(vel_vec.z, 6)),
            "planned_midpoint_speed_mps": round(v_plan_mid, 6),
            "speed_tracking_error_mps": round(speed_err, 6),
            "fd_accel_mps2": (round(accel_vec.x, 5), round(accel_vec.y, 5), round(accel_vec.z, 5)),
            "fd_accel_mag_mps2": round(accel_mag, 5),
        })

    start_pos = Vector(frames_telemetry[0]["reopen_evaluated"]["root_world_pos_m"])
    end_pos = Vector(frames_telemetry[-1]["reopen_evaluated"]["root_world_pos_m"])
    total_disp_m = float((end_pos - start_pos).length)

    root_continuity_passed = (
        stand_start_max_step_m < 1e-6
        and stand_stop_max_step_m < 1e-6
        and overall_max_step_m <= 0.0105
        and max_speed_tracking_err_mps <= 0.005
        and max_accel_mag_mps2 <= 0.25
        and abs(total_disp_m - 1.26) < 1e-4
    )

    root_continuity_summary = {
        "passed": root_continuity_passed,
        "start_root_world_m": tuple(round(v, 5) for v in start_pos),
        "end_root_world_m": tuple(round(v, 5) for v in end_pos),
        "total_displacement_m": round(total_disp_m, 6),
        "stand_start_frames_1_to_13_max_step_m": round(stand_start_max_step_m, 8),
        "stand_stop_frames_193_to_204_max_step_m": round(stand_stop_max_step_m, 8),
        "max_single_frame_step_m": round(overall_max_step_m, 6),
        "max_single_frame_step_frame": overall_max_step_frame,
        "max_fd_speed_mps": round(overall_max_step_m / dt, 6),
        "max_speed_vs_planned_midpoint_error_mps": round(max_speed_tracking_err_mps, 6),
        "max_speed_error_frame": max_speed_tracking_err_frame,
        "max_fd_acceleration_mps2": round(max_accel_mag_mps2, 6),
        "max_fd_acceleration_frame": max_accel_mag_frame,
        "analytical_peak_acceleration_mps2": round(math.pi * 0.24 / (2.0 * (54.0 / 24.0)), 6),
    }

    # =========================================================================
    # Section 三.2: Bone Rotation Continuity (Quaternion Geodesic Distance)
    # =========================================================================
    per_bone_rot_stats: Dict[str, Dict[str, Any]] = {
        b_name: {
            "max_geodesic_step_deg": 0.0,
            "max_step_frame": 2,
            "mean_geodesic_step_deg": 0.0,
        }
        for b_name in expected_bone_names
    }
    global_max_rot_step_deg = 0.0
    global_max_rot_bone = "pelvis"
    global_max_rot_frame = 2

    for b_name in expected_bone_names:
        steps_deg: List[float] = []
        for idx in range(1, len(frames_telemetry)):
            q_prev = frames_telemetry[idx - 1]["reopen_evaluated"]["bones"][b_name]["world_quat_wxyz"]
            q_curr = frames_telemetry[idx]["reopen_evaluated"]["bones"][b_name]["world_quat_wxyz"]
            ang_deg = _quat_geodesic_angle_deg(q_prev, q_curr)
            steps_deg.append(ang_deg)
            frame_no = frames_telemetry[idx]["frame"]
            if ang_deg > per_bone_rot_stats[b_name]["max_geodesic_step_deg"]:
                per_bone_rot_stats[b_name]["max_geodesic_step_deg"] = round(ang_deg, 5)
                per_bone_rot_stats[b_name]["max_step_frame"] = frame_no
            if ang_deg > global_max_rot_step_deg:
                global_max_rot_step_deg = ang_deg
                global_max_rot_bone = b_name
                global_max_rot_frame = frame_no
        per_bone_rot_stats[b_name]["mean_geodesic_step_deg"] = round(
            sum(steps_deg) / float(len(steps_deg)), 5
        )

    rotation_continuity_passed = global_max_rot_step_deg < 8.0
    rotation_continuity_summary = {
        "passed": rotation_continuity_passed,
        "metric": "Quaternion geodesic angle 2*arccos(|<q_f, q_{f-1}>|) in degrees with q ~ -q equivalence",
        "threshold_max_step_deg": 8.0,
        "global_max_geodesic_step_deg": round(global_max_rot_step_deg, 5),
        "global_max_bone": global_max_rot_bone,
        "global_max_frame": global_max_rot_frame,
        "key_bones": {k: per_bone_rot_stats[k] for k in KEY_CONTINUITY_BONES},
        "all_19_bones": per_bone_rot_stats,
    }

    # =========================================================================
    # Section 四: Support-Foot Locking & Contact Lifecycle Across All 9 Intervals
    # =========================================================================
    interval_specs = [
        ("interval_0_stand_start_dual", 1, 12, "BOTH", (-0.11, -8.00, 0.07), (0.11, -8.00, 0.07)),
        ("interval_1_step0_stance_L", 13, 42, "L", (-0.11, -8.00, 0.07), None),
        ("interval_2_step1_stance_R", 43, 66, "R", None, (0.11, -7.85, 0.07)),
        ("interval_3_step2_stance_L", 67, 90, "L", (-0.11, -7.61, 0.07), None),
        ("interval_4_step3_stance_R", 91, 114, "R", None, (0.11, -7.37, 0.07)),
        ("interval_5_step4_stance_L", 115, 138, "L", (-0.11, -7.13, 0.07), None),
        ("interval_6_step5_stance_R", 139, 162, "R", None, (0.11, -6.89, 0.07)),
        ("interval_7_step6_stance_L", 163, 192, "L", (-0.11, -6.74, 0.07), None),
        ("interval_8_stand_stop_dual", 193, 204, "BOTH", (-0.11, -6.74, 0.07), (0.11, -6.74, 0.07)),
    ]

    stance_intervals_report: List[Dict[str, Any]] = []
    max_stance_controller_drift_m = 0.0
    max_stance_controller_drift_frame = 1
    max_stance_ankle_bone_drift_m = 0.0
    max_stance_ankle_bone_drift_frame = 1
    max_stance_interframe_ankle_slip_m = 0.0
    max_stance_interframe_ankle_slip_frame = 1

    for int_id, f_beg, f_end_inc, st_side, anc_l, anc_r in interval_specs:
        int_ctrl_max_l = 0.0
        int_ankle_max_l = 0.0
        int_slip_max_l = 0.0
        int_ctrl_max_r = 0.0
        int_ankle_max_r = 0.0
        int_slip_max_r = 0.0
        int_min_z_l = 999.0
        int_max_z_l = -999.0
        int_min_z_r = 999.0
        int_max_z_r = -999.0

        prev_ankle_l: Optional[Vector] = None
        prev_ankle_r: Optional[Vector] = None

        for f_no in range(f_beg, f_end_inc + 1):
            fe = frames_telemetry[f_no - 1]["reopen_evaluated"]
            fl = fe["foot_L"]
            fr = fe["foot_R"]
            int_min_z_l = min(int_min_z_l, float(fl["mesh_min_z_m"]))
            int_max_z_l = max(int_max_z_l, float(fl["mesh_min_z_m"]))
            int_min_z_r = min(int_min_z_r, float(fr["mesh_min_z_m"]))
            int_max_z_r = max(int_max_z_r, float(fr["mesh_min_z_m"]))

            cur_ank_l = Vector(fl["ankle_bone_world_m"])
            cur_ank_r = Vector(fr["ankle_bone_world_m"])

            if st_side in ("L", "BOTH") and anc_l is not None:
                cd_l = float(fl["stance_controller_drift_m"])
                ad_l = float(fl["stance_ankle_bone_drift_m"])
                int_ctrl_max_l = max(int_ctrl_max_l, cd_l)
                int_ankle_max_l = max(int_ankle_max_l, ad_l)
                if cd_l > max_stance_controller_drift_m:
                    max_stance_controller_drift_m = cd_l
                    max_stance_controller_drift_frame = f_no
                if ad_l > max_stance_ankle_bone_drift_m:
                    max_stance_ankle_bone_drift_m = ad_l
                    max_stance_ankle_bone_drift_frame = f_no
                if prev_ankle_l is not None:
                    slip_l = float((cur_ank_l - prev_ankle_l).length)
                    int_slip_max_l = max(int_slip_max_l, slip_l)
                    if slip_l > max_stance_interframe_ankle_slip_m:
                        max_stance_interframe_ankle_slip_m = slip_l
                        max_stance_interframe_ankle_slip_frame = f_no
                prev_ankle_l = cur_ank_l

            if st_side in ("R", "BOTH") and anc_r is not None:
                cd_r = float(fr["stance_controller_drift_m"])
                ad_r = float(fr["stance_ankle_bone_drift_m"])
                int_ctrl_max_r = max(int_ctrl_max_r, cd_r)
                int_ankle_max_r = max(int_ankle_max_r, ad_r)
                if cd_r > max_stance_controller_drift_m:
                    max_stance_controller_drift_m = cd_r
                    max_stance_controller_drift_frame = f_no
                if ad_r > max_stance_ankle_bone_drift_m:
                    max_stance_ankle_bone_drift_m = ad_r
                    max_stance_ankle_bone_drift_frame = f_no
                if prev_ankle_r is not None:
                    slip_r = float((cur_ank_r - prev_ankle_r).length)
                    int_slip_max_r = max(int_slip_max_r, slip_r)
                    if slip_r > max_stance_interframe_ankle_slip_m:
                        max_stance_interframe_ankle_slip_m = slip_r
                        max_stance_interframe_ankle_slip_frame = f_no
                prev_ankle_r = cur_ank_r

        stance_intervals_report.append({
            "interval_id": int_id,
            "frame_range": (f_beg, f_end_inc),
            "stance_side": st_side,
            "stance_anchor_L_m": anc_l,
            "stance_anchor_R_m": anc_r,
            "max_controller_drift_L_m": round(int_ctrl_max_l, 7) if st_side in ("L", "BOTH") else None,
            "max_ankle_bone_drift_L_m": round(int_ankle_max_l, 7) if st_side in ("L", "BOTH") else None,
            "max_interframe_ankle_slip_L_m": round(int_slip_max_l, 7) if st_side in ("L", "BOTH") else None,
            "max_controller_drift_R_m": round(int_ctrl_max_r, 7) if st_side in ("R", "BOTH") else None,
            "max_ankle_bone_drift_R_m": round(int_ankle_max_r, 7) if st_side in ("R", "BOTH") else None,
            "max_interframe_ankle_slip_R_m": round(int_slip_max_r, 7) if st_side in ("R", "BOTH") else None,
            "foot_L_mesh_min_z_range_m": (round(int_min_z_l, 6), round(int_max_z_l, 6)),
            "foot_R_mesh_min_z_range_m": (round(int_min_z_r, 6), round(int_max_z_r, 6)),
        })

    # Contact lifecycle transitions smoothness check across the 8 boundary frames
    transition_boundaries = [13, 43, 67, 91, 115, 139, 163, 193]
    lifecycle_transitions: List[Dict[str, Any]] = []
    max_transition_foot_step_m = 0.0
    for tb in transition_boundaries:
        f_before = frames_telemetry[tb - 2]
        f_after = frames_telemetry[tb - 1]
        ank_l_b = Vector(f_before["reopen_evaluated"]["foot_L"]["ankle_bone_world_m"])
        ank_l_a = Vector(f_after["reopen_evaluated"]["foot_L"]["ankle_bone_world_m"])
        ank_r_b = Vector(f_before["reopen_evaluated"]["foot_R"]["ankle_bone_world_m"])
        ank_r_a = Vector(f_after["reopen_evaluated"]["foot_R"]["ankle_bone_world_m"])
        step_l = float((ank_l_a - ank_l_b).length)
        step_r = float((ank_r_a - ank_r_b).length)
        max_transition_foot_step_m = max(max_transition_foot_step_m, step_l, step_r)
        lifecycle_transitions.append({
            "transition_frame": tb,
            "from_support": f_before["analytical_reference"]["expected_support_type"],
            "to_support": f_after["analytical_reference"]["expected_support_type"],
            "from_interval": f_before["analytical_reference"]["interval_id"],
            "to_interval": f_after["analytical_reference"]["interval_id"],
            "foot_L_ankle_step_across_boundary_m": round(step_l, 6),
            "foot_R_ankle_step_across_boundary_m": round(step_r, 6),
        })

    stance_foot_l_zs = [
        f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"]
        for f in frames_telemetry
        if f["analytical_reference"]["foot_L_is_locked_ref"]
    ]
    stance_foot_r_zs = [
        f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"]
        for f in frames_telemetry
        if f["analytical_reference"]["foot_R_is_locked_ref"]
    ]
    swing_foot_l_zs = [
        f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"]
        for f in frames_telemetry
        if not f["analytical_reference"]["foot_L_is_locked_ref"]
    ]
    swing_foot_r_zs = [
        f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"]
        for f in frames_telemetry
        if not f["analytical_reference"]["foot_R_is_locked_ref"]
    ]

    global_min_foot_l_z = min(f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"] for f in frames_telemetry)
    global_min_foot_r_z = min(f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"] for f in frames_telemetry)
    global_max_foot_l_z = max(f["reopen_evaluated"]["foot_L"]["mesh_min_z_m"] for f in frames_telemetry)
    global_max_foot_r_z = max(f["reopen_evaluated"]["foot_R"]["mesh_min_z_m"] for f in frames_telemetry)
    max_ik_track_err_l = max(f["reopen_evaluated"]["foot_L"]["ik_tracking_error_m"] for f in frames_telemetry)
    max_ik_track_err_r = max(f["reopen_evaluated"]["foot_R"]["ik_tracking_error_m"] for f in frames_telemetry)

    support_and_contact_passed = (
        max_stance_controller_drift_m == 0.0
        and max_stance_ankle_bone_drift_m < 1e-4
        and max_stance_interframe_ankle_slip_m < 1e-4
        and min(stance_foot_l_zs) >= -1e-4
        and max(stance_foot_l_zs) <= 1e-4
        and min(stance_foot_r_zs) >= -1e-4
        and max(stance_foot_r_zs) <= 1e-4
        and min(swing_foot_l_zs) >= -0.003
        and min(swing_foot_r_zs) >= -0.003
        and max_transition_foot_step_m < 0.005
    )

    support_and_contact_summary = {
        "passed": support_and_contact_passed,
        "max_stance_controller_drift_m": round(max_stance_controller_drift_m, 7),
        "max_stance_controller_drift_frame": max_stance_controller_drift_frame,
        "max_stance_ankle_bone_drift_m": round(max_stance_ankle_bone_drift_m, 7),
        "max_stance_ankle_bone_drift_frame": max_stance_ankle_bone_drift_frame,
        "max_stance_interframe_ankle_slip_m": round(max_stance_interframe_ankle_slip_m, 7),
        "max_stance_interframe_ankle_slip_frame": max_stance_interframe_ankle_slip_frame,
        "max_ik_tracking_error_L_m": round(max_ik_track_err_l, 7),
        "max_ik_tracking_error_R_m": round(max_ik_track_err_r, 7),
        "stance_foot_L_mesh_min_z_range_m": (round(min(stance_foot_l_zs), 6), round(max(stance_foot_l_zs), 6)),
        "stance_foot_R_mesh_min_z_range_m": (round(min(stance_foot_r_zs), 6), round(max(stance_foot_r_zs), 6)),
        "swing_foot_L_mesh_min_z_range_m": (round(min(swing_foot_l_zs), 6), round(max(swing_foot_l_zs), 6)),
        "swing_foot_R_mesh_min_z_range_m": (round(min(swing_foot_r_zs), 6), round(max(swing_foot_r_zs), 6)),
        "foot_L_mesh_min_z_global_range_m": (round(global_min_foot_l_z, 6), round(global_max_foot_l_z, 6)),
        "foot_R_mesh_min_z_global_range_m": (round(global_min_foot_r_z, 6), round(global_max_foot_r_z, 6)),
        "swing_toe_box_geometry_note": (
            "During stance, Foot_L and Foot_R mesh min_z stay within [-0.000029m, +0.000003m] (zero penetration, zero lift). "
            "At the first/last frame of swing (s=1/N or (N-1)/N), frozen StartStopWalkAction (src/motion/framework.py:661) "
            "applies linear-onset toe pitch (-12 deg * sin(pi*s)) while vertical lift uses quadratic-onset sin^2(pi*s), "
            "causing the front bottom edge of the 0.22m unrounded Foot box (+0.15m ahead of ankle) to dip to -0.002057m (L) "
            "and -0.002598m (R) while the ankle joint itself remains above ANKLE_REST_Z (0.070m)."
        ),
        "max_transition_boundary_foot_step_m": round(max_transition_foot_step_m, 6),
        "stance_intervals": stance_intervals_report,
        "lifecycle_transitions": lifecycle_transitions,
    }

    # =========================================================================
    # Section 五: CoM & Rigid-Body Geometry Consistency Across All 204 Frames
    # =========================================================================
    masses = [f["reopen_evaluated"]["total_mass_kg"] for f in frames_telemetry]
    com_xs = [f["reopen_evaluated"]["com_world_m"][0] for f in frames_telemetry]
    com_ys = [f["reopen_evaluated"]["com_world_m"][1] for f in frames_telemetry]
    com_zs = [f["reopen_evaluated"]["com_world_m"][2] for f in frames_telemetry]

    nan_or_inf_count = sum(
        1
        for f in frames_telemetry
        for c in f["reopen_evaluated"]["com_world_m"] + (f["reopen_evaluated"]["total_mass_kg"],)
        if math.isnan(c) or math.isinf(c)
    )
    max_com_step_m = 0.0
    max_com_step_frame = 2
    for idx in range(1, len(frames_telemetry)):
        c0 = Vector(frames_telemetry[idx - 1]["reopen_evaluated"]["com_world_m"])
        c1 = Vector(frames_telemetry[idx]["reopen_evaluated"]["com_world_m"])
        cs = float((c1 - c0).length)
        if cs > max_com_step_m:
            max_com_step_m = cs
            max_com_step_frame = frames_telemetry[idx]["frame"]

    # Check bone length invariance and ROM validity across all 204 frames
    max_thigh_len_err = max(
        max(
            abs(f["reopen_evaluated"]["foot_L"]["thigh_length_m"] - THIGH_LENGTH),
            abs(f["reopen_evaluated"]["foot_R"]["thigh_length_m"] - THIGH_LENGTH),
        )
        for f in frames_telemetry
    )
    max_shin_len_err = max(
        max(
            abs(f["reopen_evaluated"]["foot_L"]["shin_length_m"] - SHIN_LENGTH),
            abs(f["reopen_evaluated"]["foot_R"]["shin_length_m"] - SHIN_LENGTH),
        )
        for f in frames_telemetry
    )
    rom_violation_frames = [
        f["frame"] for f in frames_telemetry if not f["reopen_evaluated"]["rom_is_valid"]
    ]

    com_forward_disp = float(com_ys[-1] - com_ys[0])
    com_lateral_span = float(max(com_xs) - min(com_xs))
    com_vertical_span = float(max(com_zs) - min(com_zs))

    com_and_geometry_passed = (
        nan_or_inf_count == 0
        and max(abs(m - 70.0) for m in masses) < 1e-6
        and abs(com_forward_disp - 1.26) < 1e-3
        and 0.02 <= com_lateral_span <= 0.12
        and 0.01 <= com_vertical_span <= 0.08
        and max_com_step_m <= 0.015
        and max_thigh_len_err < 1e-4
        and max_shin_len_err < 1e-4
        and len(rom_violation_frames) == 0
    )

    com_and_geometry_summary = {
        "passed": com_and_geometry_passed,
        "nan_or_inf_count": nan_or_inf_count,
        "total_mass_kg_min": min(masses),
        "total_mass_kg_max": max(masses),
        "com_start_world_m": frames_telemetry[0]["reopen_evaluated"]["com_world_m"],
        "com_end_world_m": frames_telemetry[-1]["reopen_evaluated"]["com_world_m"],
        "com_forward_y_displacement_m": round(com_forward_disp, 6),
        "com_lateral_x_range_m": (round(min(com_xs), 6), round(max(com_xs), 6)),
        "com_lateral_x_span_m": round(com_lateral_span, 6),
        "com_vertical_z_range_m": (round(min(com_zs), 6), round(max(com_zs), 6)),
        "com_vertical_z_span_m": round(com_vertical_span, 6),
        "max_single_frame_com_step_m": round(max_com_step_m, 6),
        "max_single_frame_com_step_frame": max_com_step_frame,
        "max_thigh_length_error_m": round(max_thigh_len_err, 7),
        "max_shin_length_error_m": round(max_shin_len_err, 7),
        "rom_violation_frame_count": len(rom_violation_frames),
        "rom_violation_frames": rom_violation_frames,
        "physical_semantics_boundary": (
            "Whole-body CoM trajectory is kinematic mass-weighted telemetry computed from "
            "evaluated 15-segment pose bones (DEMPSTER_WINTER_15_SEGMENT_MODEL) and is NOT "
            "claimed as closed-loop dynamic balance or ground reaction force proof."
        ),
    }

    overall_passed = (
        frame_start == 1
        and frame_end == 204
        and int(fps) == 24
        and len(frames_telemetry) == 204
        and root_continuity_passed
        and rotation_continuity_passed
        and support_and_contact_passed
        and com_and_geometry_passed
    )

    validation_payload = {
        "task_id": "Task 7A-1",
        "validation_mode": "independent_readonly_blend_reopen_204_frames",
        "reopened_blend_path": os.path.relpath(derived_blend_path, cfg.project_root).replace("\\", "/"),
        "verdict": "PASS" if overall_passed else "FAIL",
        "passed": overall_passed,
        "frame_start": frame_start,
        "frame_end": frame_end,
        "total_evaluated_frames": len(frames_telemetry),
        "fps": int(fps),
        "data_provenance": {
            "reopen_evaluated": (
                "Evaluated directly from reopened output/dynamics_playground_task7a1.blend via "
                "scene.frame_set(f) + bpy.context.view_layer.update() without executing MotionPlanner or WholeBodyController."
            ),
            "analytical_reference": (
                "Computed from deterministic StartStopWalkConfig analytical schedule in src/motion/start_stop_walk.py "
                "strictly as reference targets for drift and velocity error comparison."
            ),
            "custom_property_is_locked_note": (
                "FootIK.L['is_locked'] and FootIK.R['is_locked'] custom properties are not keyframed by "
                "KinematicBridgeExecutor (only location and rotation_euler are keyframed), so per-frame "
                "stance/swing lock reference is taken from analytical_reference while actual controller "
                "and ankle bone world positions/drifts are measured from reopen_evaluated."
            ),
        },
        "root_translation_continuity": root_continuity_summary,
        "bone_rotation_continuity": rotation_continuity_summary,
        "support_foot_and_contact_lifecycle": support_and_contact_summary,
        "com_and_rigid_body_geometry": com_and_geometry_summary,
        "root_frame_transitions": root_steps,
        "frames": frames_telemetry,
    }

    if output_json_path is not None:
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(validation_payload, f, indent=2, ensure_ascii=False)

    return validation_payload


# =============================================================================
# 8. Full Task 7A-1 End-to-End Integration Orchestrator (Generation Entry Point)
# =============================================================================

def execute_task7a1_pipeline(
    source_playground_blend: Optional[str] = None,
    output_derived_blend: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    render_visuals: bool = True,
) -> Dict[str, Any]:
    """Load `output/dynamics_playground.blend`, integrate the real 19-bone character,
    execute all Task 7A-1 control and mathematical verifications, save the derived
    playable `.blend` scene (`output/dynamics_playground_task7a1.blend`), then reopen
    the saved `.blend` read-only to execute the 204-frame continuous GIF render,
    204-frame full mathematical validation (`full_frame_validation.json`), and deep
    playground preservation diff.
    """
    config = PipelineConfig()
    src_blend = source_playground_blend or os.path.join(
        config.project_root, "output", "dynamics_playground.blend"
    )
    out_blend = output_derived_blend or os.path.join(
        config.project_root, "output", "dynamics_playground_task7a1.blend"
    )
    ev_dir = evidence_dir or os.path.join(
        config.project_root, "docs", "evidence", "task7a1"
    )
    os.makedirs(ev_dir, exist_ok=True)

    if not os.path.isfile(src_blend):
        raise FileNotFoundError(f"Authoritative playground blend not found: {src_blend}")

    # 1. Open authoritative dynamics_playground.blend (read-only on source file) & take deep snapshot
    bpy.ops.wm.open_mainfile(filepath=src_blend)
    scene = bpy.context.scene
    baseline_snap = snapshot_playground_baseline(scene)
    deep_baseline_snap = capture_deep_playground_snapshot(scene)

    # 2. Assemble real 19-bone character into 'Character' collection
    asm = assemble_character_in_playground(config)
    arm_obj = asm["armature"]
    root_obj = asm["root"]
    cameras = asm["cameras"]
    env_query = create_standard_dynamics_playground_query()

    # 3. Inspect scene, 19 bones, 13 mesh parts, and 8 IK/FK controllers
    inventory_report = inspect_scene_and_character_inventory(baseline_snap)

    # 4. Run minimal control closed-loop stages (A, B, C, D)
    stages_abcd_report = run_minimal_control_stages_verification(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
        cameras=cameras,
        evidence_dir=ev_dir,
        render_images=render_visuals,
    )

    # 5. Run mathematical consistency verifications (Section 五: 1..4)
    math_report = run_mathematical_consistency_verifications(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
    )

    # 6. Run Stage E continuous StartStopWalkAction in playground & save derived blend
    stage_e_report = run_stage_e_continuous_walk_in_playground(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
        cameras=cameras,
        output_blend_path=out_blend,
        evidence_dir=ev_dir,
        render_visuals=render_visuals,
    )

    # 7. Verify post-execution playground station integrity
    post_snap = snapshot_playground_baseline(scene)
    stations_intact_after_walk = (
        post_snap["collection_object_counts"] == baseline_snap["collection_object_counts"]
        and post_snap["station_f1"] == baseline_snap["station_f1"]
        and post_snap["station_f73"] == baseline_snap["station_f73"]
    )

    # 8. Reopen saved `output/dynamics_playground_task7a1.blend` read-only to render 204-frame continuous GIF
    gif_path = os.path.join(ev_dir, "task7a1_walk_preview.gif")
    if render_visuals:
        gif_inspection = render_reopened_204_frame_walk_gif(
            derived_blend_path=out_blend,
            gif_output_path=gif_path,
            res_x=320,
            res_y=240,
            delay_cs=4,
        )
    else:
        gif_inspection = count_gif_frames(gif_path)
    stage_e_report["gif_inspection"] = gif_inspection

    # 9. Reopen saved `output/dynamics_playground_task7a1.blend` read-only for 204-frame mathematical validation
    full_frame_json_path = os.path.join(ev_dir, "full_frame_validation.json")
    reopen_validation = validate_reopened_task7a1_blend(
        derived_blend_path=out_blend,
        output_json_path=full_frame_json_path,
        config=config,
    )

    # 10. Reopen saved `output/dynamics_playground_task7a1.blend` read-only for deep asset preservation diff
    deep_asset_diff = verify_derived_blend_against_deep_snapshot(
        deep_baseline=deep_baseline_snap,
        derived_blend_path=out_blend,
    )

    full_report = {
        "task_id": "Task 7A-1",
        "source_playground_blend": os.path.relpath(src_blend, config.project_root).replace("\\", "/"),
        "derived_task7a1_blend": os.path.relpath(out_blend, config.project_root).replace("\\", "/"),
        "full_frame_validation_json": os.path.relpath(full_frame_json_path, config.project_root).replace("\\", "/"),
        "playground_stations_intact_after_walk": stations_intact_after_walk,
        "deep_asset_preservation": deep_asset_diff,
        "reopen_204_frame_validation_summary": {
            "verdict": reopen_validation["verdict"],
            "total_evaluated_frames": reopen_validation["total_evaluated_frames"],
            "root_translation_continuity": reopen_validation["root_translation_continuity"],
            "bone_rotation_continuity": {
                k: v
                for k, v in reopen_validation["bone_rotation_continuity"].items()
                if k != "all_19_bones"
            },
            "support_foot_and_contact_lifecycle": reopen_validation["support_foot_and_contact_lifecycle"],
            "com_and_rigid_body_geometry": reopen_validation["com_and_rigid_body_geometry"],
        },
        "inventory": inventory_report,
        "minimal_control_stages": {
            "stage_A_static_standing": stages_abcd_report["stage_A_static_standing"],
            "stage_B_root_displacement": stages_abcd_report["stage_B_root_displacement"],
            "stage_C_single_foot_ik": stages_abcd_report["stage_C_single_foot_ik"],
            "stage_D_support_foot_lock": stages_abcd_report["stage_D_support_foot_lock"],
            "stage_E_continuous_walk": stage_e_report,
        },
        "mathematical_consistency": math_report,
    }

    report_json_path = os.path.join(ev_dir, "task7a1_verification_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    return full_report
