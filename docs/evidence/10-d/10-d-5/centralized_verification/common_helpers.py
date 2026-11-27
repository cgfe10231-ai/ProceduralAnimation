"""Shared read-only helpers, Blender scene assemblers, call-chain observer, and
whole-body / reopen metrics for TASK 10-d-5 centralized production verification.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
BLENDER_PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", "..", ".."))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
SCRATCH_WORK = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\centralized_verification_work"
)

EXPECTED_HEAD = "824c52ec73f86aa3d08245a58297118cb4a9f110"
HIST_BASELINE_COMMIT = "9f5f825059fad3b9dafa8ed0b9b2c0af1bb7d1d0"
HIST_BASELINE_DIR = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\baseline_9f5f825"
)

VR_SCRIPT = os.path.join(
    REPO_ROOT, "docs", "evidence", "10-d", "10-d-4", "visual_redelivery", "generate_visual_redelivery.py"
)
EXT_SCRIPT = os.path.join(
    REPO_ROOT, "docs", "evidence", "10-d", "10-d-4", "extended_visual_delivery", "generate_extended_visual_delivery.py"
)

BODY_TELEMETRY_BONES: Tuple[str, ...] = (
    "pelvis",
    "spine",
    "neck",
    "head",
    "thigh.L",
    "shin.L",
    "foot.L",
    "thigh.R",
    "shin.R",
    "foot.R",
    "shoulder.L",
    "upper_arm.L",
    "forearm.L",
    "hand.L",
    "shoulder.R",
    "upper_arm.R",
    "forearm.R",
    "hand.R",
)
UPPER_LIMB_BONES: Tuple[str, ...] = (
    "shoulder.L",
    "upper_arm.L",
    "forearm.L",
    "hand.L",
    "shoulder.R",
    "upper_arm.R",
    "forearm.R",
    "hand.R",
)
LOWER_LIMB_BONES: Tuple[str, ...] = (
    "thigh.L",
    "shin.L",
    "foot.L",
    "thigh.R",
    "shin.R",
    "foot.R",
)
UPPER_CONTROLLERS: Tuple[str, ...] = ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R")
UPPER_CONSTRAINTS: Tuple[Tuple[str, str, str], ...] = (
    ("ArmIK.L", "forearm.L", 'pose.bones["forearm.L"].constraints["ArmIK.L"].influence'),
    ("ArmIK.R", "forearm.R", 'pose.bones["forearm.R"].constraints["ArmIK.R"].influence'),
    ("HandRotation.L", "hand.L", 'pose.bones["hand.L"].constraints["HandRotation.L"].influence'),
    ("HandRotation.R", "hand.R", 'pose.bones["hand.R"].constraints["HandRotation.R"].influence'),
)

REOPEN_POS_TOL_M = 1e-5
REOPEN_ROT_TOL_RAD = 1e-4
REOPEN_INF_TOL = 1e-6


def setup_repo_sys_path(repo_root: str = REPO_ROOT) -> None:
    norm_target = os.path.normpath(os.path.abspath(repo_root))
    cleaned = []
    for p in sys.path:
        if not p:
            continue
        np = os.path.normpath(os.path.abspath(p))
        if np not in (
            os.path.normpath(REPO_ROOT),
            os.path.normpath(HIST_BASELINE_DIR),
        ):
            cleaned.append(p)
    sys.path[:] = [norm_target] + cleaned


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_historical_baseline_extracted() -> str:
    marker = os.path.join(HIST_BASELINE_DIR, "src", "motion", "framework.py")
    if os.path.exists(marker):
        return HIST_BASELINE_DIR
    import zipfile

    os.makedirs(HIST_BASELINE_DIR, exist_ok=True)
    zip_path = os.path.join(SCRATCH_WORK, "baseline_9f5f825.zip")
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    subprocess.run(
        ["git", "archive", "--format=zip", f"--output={zip_path}", HIST_BASELINE_COMMIT, "src/"],
        cwd=REPO_ROOT,
        check=True,
    )
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(HIST_BASELINE_DIR)
    return HIST_BASELINE_DIR


def load_vr():
    spec = importlib.util.spec_from_file_location("vr10d4_ro", VR_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_ext():
    spec = importlib.util.spec_from_file_location("ext10d4_ro", EXT_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# PRODUCTION BLENDER SCENE ASSEMBLERS (WITH DIAGNOSTIC HANDS & CAMERAS)
# =============================================================================

def _setup_diagnostic_hands_and_cameras(
    arm_obj,
    root_obj,
    scene,
    follow_cam: bool = True,
):
    import bpy
    from mathutils import Vector

    vr = load_vr()
    ext = load_ext()

    mat_left = vr._make_diagnostic_material("VisualDiag_LeftArm", (0.12, 0.56, 0.96, 1.0))
    mat_right = vr._make_diagnostic_material("VisualDiag_RightArm", (0.96, 0.42, 0.12, 1.0))
    mat_dorsal = vr._make_diagnostic_material("VisualDiag_HandDorsalAccent", (0.95, 0.92, 0.18, 1.0))

    for pname in ("UpperArm_L", "LowerArm_L"):
        pobj = bpy.data.objects[pname]
        pobj.data.materials.clear()
        pobj.data.materials.append(mat_left)
    for pname in ("UpperArm_R", "LowerArm_R"):
        pobj = bpy.data.objects[pname]
        pobj.data.materials.clear()
        pobj.data.materials.append(mat_right)

    char_col = bpy.data.collections.get("Character") or scene.collection
    hand_l = vr._build_asymmetric_hand_mesh(arm_obj, "L", char_col, mat_left, mat_dorsal)
    hand_r = vr._build_asymmetric_hand_mesh(arm_obj, "R", char_col, mat_right, mat_dorsal)

    cam_col = bpy.data.collections.get("VisualRedelivery_Cameras")
    if cam_col is None:
        cam_col = bpy.data.collections.new("VisualRedelivery_Cameras")
        scene.collection.children.link(cam_col)

    cam_specs = {
        "Visual_FrontCam": {
            "location": (0.0, 5.20, 1.48),
            "look_at": (0.0, 0.0, 1.00),
            "lens": 28.0,
        },
        "Visual_ObliqueSideCam": {
            "location": (4.20, 4.40, 2.25),
            "look_at": (0.0, 0.15, 1.00),
            "lens": 26.0,
        },
    }
    cameras = {}
    for cname, spec in cam_specs.items():
        cdata = bpy.data.cameras.new(cname)
        cdata.lens = spec["lens"]
        cdata.clip_start = 0.05
        cdata.clip_end = 250.0
        cobj = bpy.data.objects.new(cname, cdata)
        loc = Vector(spec["location"])
        tgt = Vector(spec["look_at"])
        cobj.location = loc
        cobj.rotation_mode = "XYZ"
        cobj.rotation_euler = (tgt - loc).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
        cam_col.objects.link(cobj)
        cameras[cname] = cobj

    scene.camera = cameras["Visual_ObliqueSideCam"]
    if follow_cam:
        ext._attach_root_follow_camera(scene, root_obj, scene.camera)
    bpy.context.view_layer.update()
    return hand_l, hand_r, cameras


def assemble_flat_locomotion_scene(
    fps: int = 24,
    start_pos: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    with_visual_hands: bool = True,
):
    import bpy
    from mathutils import Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.ik import setup_leg_ik
    from src.rig.arm_ik import setup_arm_ik
    from src.rig.pose import reset_pose
    from src.scene.builder import create_box_mesh, create_simple_material
    from src.motion.framework import EnvironmentQuery

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "CentralizedLocomotionScene"
    scene.render.fps = int(fps)
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    col_env = bpy.data.collections.new("Playground_Surfaces")
    col_light = bpy.data.collections.new("Playground_Lighting")
    scene.collection.children.link(col_env)
    scene.collection.children.link(col_light)

    mat_ground = create_simple_material("Mat_FlatGround", (0.30, 0.32, 0.36, 1.0), roughness=0.85)
    create_box_mesh(
        "Surface_FlatCorridor",
        (-8.0, -12.0, -0.30),
        (8.0, 50.0, 0.0),
        col_env,
        mat_ground,
    )

    # Lane tick marks every 2 meters along Y so forward translation is visually clear
    mat_tick = create_simple_material("Mat_LaneTick", (0.85, 0.85, 0.85, 1.0), roughness=0.5)
    for y_tick in range(-6, 46, 2):
        create_box_mesh(
            f"LaneTick_{y_tick:03d}",
            (-1.6, float(y_tick) - 0.02, 0.001),
            (1.6, float(y_tick) + 0.02, 0.004),
            col_env,
            mat_tick,
        )

    for loc, rot in (
        ((12.0, -6.0, 22.0), (math.radians(45.0), math.radians(20.0), math.radians(35.0))),
        ((-10.0, 25.0, 15.0), (math.radians(60.0), math.radians(-30.0), math.radians(-45.0))),
    ):
        ldata = bpy.data.lights.new("SunLight", type="SUN")
        ldata.energy = 2.8
        lobj = bpy.data.objects.new("SunLight", ldata)
        lobj.location = loc
        lobj.rotation_euler = rot
        col_light.objects.link(lobj)

    cfg = PipelineConfig()
    cfg.fps = int(fps)
    parts = build_character(cfg)
    root_obj = bpy.data.objects["CharacterRoot"]
    root_obj.location = Vector(start_pos)
    arm_obj = build_rig(cfg, character_root=root_obj)
    bind_character_to_rig(arm_obj, parts)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj)
    bpy.context.view_layer.update()

    hand_l = hand_r = None
    if with_visual_hands:
        hand_l, hand_r, _ = _setup_diagnostic_hands_and_cameras(arm_obj, root_obj, scene, follow_cam=True)

    env = EnvironmentQuery(ground_z=0.0)
    return cfg, scene, root_obj, arm_obj, hand_l, hand_r, env


def assemble_continuous_course_b_scene(fps: int = 24, with_visual_hands: bool = True):
    """Build real Course-B terrain corridor (Flat Approach -> 15 deg Ramp Up -> Bridge -> 20 deg Ramp Down -> Flat Runway).

    Reuses exact Zone-3 geometry from create_standard_dynamics_playground_query() and
    src.scene.builder without placing Zone-4 walls inside the sprint/run runway.
    """
    import bpy
    from mathutils import Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.ik import setup_leg_ik
    from src.rig.arm_ik import setup_arm_ik
    from src.rig.pose import reset_pose
    from src.scene.builder import (
        create_arrow_mesh,
        create_box_mesh,
        create_mesh_object,
        create_simple_material,
    )
    from src.scene.environment_query import (
        DynamicsEnvironmentQuery,
        OrientedSurface,
        SurfaceGeometryType,
        create_standard_dynamics_playground_query,
    )

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "CentralizedCompoundTerrainScene"
    scene.render.fps = int(fps)
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    col_surfaces = bpy.data.collections.new("Playground_Surfaces")
    col_visuals = bpy.data.collections.new("Playground_Visuals")
    col_light = bpy.data.collections.new("Playground_Lighting")
    scene.collection.children.link(col_surfaces)
    scene.collection.children.link(col_visuals)
    scene.collection.children.link(col_light)

    mat_ground = create_simple_material("Mat_Ground", (0.35, 0.35, 0.38, 1.0), roughness=0.85)
    mat_ramp = create_simple_material("Mat_Ramp", (0.92, 0.52, 0.12, 1.0), roughness=0.60)
    mat_arrow = create_simple_material("Mat_NormalArrow", (0.0, 0.90, 1.0, 1.0), roughness=0.30)
    mat_tick = create_simple_material("Mat_LaneTick", (0.85, 0.85, 0.85, 1.0), roughness=0.50)

    # Analytical surfaces: pull exact Zone-3 ramps/bridge from create_standard_dynamics_playground_query()
    std_q = create_standard_dynamics_playground_query()
    ramp_up = std_q.get_surface_by_id("ramp_up")
    ramp_top = std_q.get_surface_by_id("ramp_top_platform")
    ramp_down = std_q.get_surface_by_id("ramp_down")
    assert ramp_up is not None and ramp_top is not None and ramp_down is not None

    ramp_up_top_z = 5.0 * math.tan(math.radians(15.0))
    ramp_down_end_y = 18.0 + ramp_up_top_z / math.tan(math.radians(20.0))

    surfaces = [
        OrientedSurface(
            surface_id="approach_flat_ground",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND,
            center=(0.0, 4.5, 0.0),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(6.0, 6.5),
            friction_coeff=0.70,
            allows_regular_support=True,
            description="Approach flat ground Y in [-2.0, 11.0]",
        ),
        ramp_up,
        ramp_top,
        ramp_down,
        OrientedSurface(
            surface_id="runway_flat_ground",
            surface_type=SurfaceGeometryType.HORIZONTAL_GROUND,
            center=(0.0, 34.0, 0.0),
            normal=(0.0, 0.0, 1.0),
            u_axis=(1.0, 0.0, 0.0),
            v_axis=(0.0, 1.0, 0.0),
            half_extents=(6.0, 12.319),
            friction_coeff=0.70,
            allows_regular_support=True,
            description="Exit sprint/run flat runway Y in [21.681, 46.319]",
        ),
    ]
    env = DynamicsEnvironmentQuery(ground_z=0.0, surfaces=surfaces)

    # Matching visual meshes in Playground_Surfaces
    create_box_mesh("Surface_ApproachFlatGround", (-6.0, -2.0, -0.30), (6.0, 11.0, 0.0), col_surfaces, mat_ground)
    create_mesh_object(
        "Surface_Ramp_Up",
        [
            (-3.0, 11.0, 0.0), (3.0, 11.0, 0.0),
            (3.0, 16.0, 0.0), (-3.0, 16.0, 0.0),
            (3.0, 16.0, ramp_up_top_z), (-3.0, 16.0, ramp_up_top_z),
        ],
        [(0, 3, 2, 1), (2, 3, 5, 4), (0, 1, 4, 5), (0, 5, 3), (1, 2, 4)],
        col_surfaces,
        mat_ramp,
    )
    create_box_mesh(
        "Surface_Ramp_TopPlatform",
        (-3.0, 16.0, 0.0),
        (3.0, 18.0, ramp_up_top_z),
        col_surfaces,
        mat_ramp,
    )
    create_mesh_object(
        "Surface_Ramp_Down",
        [
            (-3.0, 18.0, 0.0), (3.0, 18.0, 0.0),
            (3.0, ramp_down_end_y, 0.0), (-3.0, ramp_down_end_y, 0.0),
            (3.0, 18.0, ramp_up_top_z), (-3.0, 18.0, ramp_up_top_z),
        ],
        [(0, 3, 2, 1), (0, 1, 4, 5), (4, 2, 3, 5), (0, 5, 3), (1, 2, 4)],
        col_surfaces,
        mat_ramp,
    )
    create_box_mesh(
        "Surface_RunwayFlatGround",
        (-6.0, ramp_down_end_y, -0.30),
        (6.0, 46.5, 0.0),
        col_surfaces,
        mat_ground,
    )

    for y_tick in (8, 10, 22, 24, 26, 28, 30, 32, 34, 36, 38):
        create_box_mesh(
            f"LaneTick_{y_tick:02d}",
            (-1.8, float(y_tick) - 0.02, 0.001),
            (1.8, float(y_tick) + 0.02, 0.004),
            col_visuals,
            mat_tick,
        )

    for s in surfaces:
        create_arrow_mesh(
            name=f"NormalArrow_{s.surface_id}",
            origin=s.center,
            direction=s.normal,
            length=0.45,
            stem_radius=0.02,
            head_length=0.12,
            head_radius=0.05,
            collection=col_visuals,
            material=mat_arrow,
        )

    for loc, rot, eng in (
        ((12.0, -6.0, 22.0), (math.radians(45.0), math.radians(20.0), math.radians(35.0)), 3.2),
        ((-10.0, 25.0, 15.0), (math.radians(60.0), math.radians(-30.0), math.radians(-45.0)), 1.5),
    ):
        ldata = bpy.data.lights.new("Sun", type="SUN")
        ldata.energy = eng
        lobj = bpy.data.objects.new("Sun", ldata)
        lobj.location = loc
        lobj.rotation_euler = rot
        col_light.objects.link(lobj)

    cfg = PipelineConfig()
    cfg.fps = int(fps)
    parts = build_character(cfg)
    root_obj = bpy.data.objects["CharacterRoot"]
    root_obj.location = Vector((0.0, 8.94, 0.0))
    arm_obj = build_rig(cfg, character_root=root_obj)
    bind_character_to_rig(arm_obj, parts)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj)
    bpy.context.view_layer.update()

    hand_l = hand_r = None
    if with_visual_hands:
        hand_l, hand_r, _ = _setup_diagnostic_hands_and_cameras(arm_obj, root_obj, scene, follow_cam=True)

    return cfg, scene, root_obj, arm_obj, hand_l, hand_r, env


# =============================================================================
# FULL-CHAIN READ-ONLY OBSERVER & LIVE SOLVE TELEMETRY (ZERO frame_set())
# =============================================================================

def capture_whole_body_live_sample(arm_obj, root_obj, bridge_res, planned_pose) -> Dict[str, Any]:
    """Read actual Blender evaluated whole-body transforms directly post-Bridge/WBC without scene.frame_set()."""
    import bpy
    from mathutils import Vector

    vr = load_vr()
    root_mat = root_obj.matrix_world.copy()
    root_inv = root_mat.inverted()
    arm_mat = arm_obj.matrix_world.copy()

    bones_data: Dict[str, Any] = {}
    for bname in BODY_TELEMETRY_BONES:
        pb = arm_obj.pose.bones[bname]
        w_mat = arm_mat @ pb.matrix
        rel_q, rel_e = vr._relative_joint_quat_and_euler(arm_obj, bname)
        bones_data[bname] = {
            "world_quat": [float(v) for v in w_mat.to_3x3().normalized().to_quaternion()],
            "world_head": [float(v) for v in (arm_mat @ pb.head)],
            "world_tail": [float(v) for v in (arm_mat @ pb.tail)],
            "rel_parent_quat": [float(v) for v in rel_q],
            "rel_parent_euler_deg": [math.degrees(rel_e.x), math.degrees(rel_e.y), math.degrees(rel_e.z)],
        }

    wrist_world_L = arm_mat @ arm_obj.pose.bones["forearm.L"].tail
    wrist_world_R = arm_mat @ arm_obj.pose.bones["forearm.R"].tail
    elbow_world_L = arm_mat @ arm_obj.pose.bones["upper_arm.L"].tail
    elbow_world_R = arm_mat @ arm_obj.pose.bones["upper_arm.R"].tail
    ankle_world_L = arm_mat @ arm_obj.pose.bones["shin.L"].tail
    ankle_world_R = arm_mat @ arm_obj.pose.bones["shin.R"].tail

    wrist_root_local_L = root_inv @ wrist_world_L
    wrist_root_local_R = root_inv @ wrist_world_R

    controllers: Dict[str, Any] = {}
    for cname in UPPER_CONTROLLERS:
        cobj = bpy.data.objects[cname]
        c_mat = cobj.matrix_world.copy()
        controllers[cname] = {
            "rotation_mode": str(cobj.rotation_mode),
            "world_pos": [float(v) for v in c_mat.translation],
            "world_quat": [float(v) for v in c_mat.to_3x3().normalized().to_quaternion()],
        }

    influences: Dict[str, float] = {}
    for cname, bname, _ in UPPER_CONSTRAINTS:
        influences[cname] = float(arm_obj.pose.bones[bname].constraints[cname].influence)

    wbc_effs = bridge_res.wbc_result.end_effectors
    eff_summary = {}
    for eid in ("foot_L", "foot_R", "hand_L", "hand_R"):
        efb = wbc_effs.get(eid)
        eff_summary[eid] = (
            {
                "enabled": bool(efb.enabled),
                "weight": float(efb.weight),
                "requested_world_xyz": [float(v) for v in efb.requested_world_xyz],
                "actual_world_xyz": [float(v) for v in efb.actual_world_xyz],
                "position_error_m": float(efb.position_error_m),
                "orientation_error_deg": float(efb.orientation_error_deg) if efb.orientation_error_deg is not None else None,
                "is_reachable": bool(efb.is_reachable),
                "strictly_in_reach": bool(efb.strictly_in_reach),
            }
            if efb is not None
            else None
        )

    pelvis_pb = arm_obj.pose.bones["pelvis"]
    return {
        "frame": int(planned_pose.frame),
        "mode": str(planned_pose.motion_mode.value),
        "is_flight": bool(planned_pose.is_flight),
        "root_world_pos": [float(v) for v in root_mat.translation],
        "root_world_matrix": vr._mat4_to_lists(root_mat),
        "root_world_quat": [float(v) for v in root_mat.to_3x3().normalized().to_quaternion()],
        "pelvis_local_loc": [float(v) for v in pelvis_pb.location],
        "wrist_world_L": [float(v) for v in wrist_world_L],
        "wrist_world_R": [float(v) for v in wrist_world_R],
        "wrist_root_local_L": [float(v) for v in wrist_root_local_L],
        "wrist_root_local_R": [float(v) for v in wrist_root_local_R],
        "elbow_world_L": [float(v) for v in elbow_world_L],
        "elbow_world_R": [float(v) for v in elbow_world_R],
        "elbow_pole_world_L": controllers["ElbowPole.L"]["world_pos"],
        "elbow_pole_world_R": controllers["ElbowPole.R"]["world_pos"],
        "elbow_pole_root_local_L": [float(v) for v in (root_inv @ Vector(controllers["ElbowPole.L"]["world_pos"]))],
        "elbow_pole_root_local_R": [float(v) for v in (root_inv @ Vector(controllers["ElbowPole.R"]["world_pos"]))],
        "ankle_world_L": [float(v) for v in ankle_world_L],
        "ankle_world_R": [float(v) for v in ankle_world_R],
        "end_effectors": eff_summary,
        "bones": bones_data,
        "controllers": controllers,
        "influences": influences,
    }


def _clone_planned_pose_dict(planned) -> Dict[str, Any]:
    return {
        "frame": int(planned.frame),
        "time_seconds": float(planned.time_seconds),
        "root_position": tuple(float(v) for v in planned.root_position),
        "root_yaw_deg": float(planned.root_yaw_deg),
        "speed_mps": float(planned.speed_mps),
        "accel_mps2": float(planned.accel_mps2),
        "motion_mode": str(planned.motion_mode.value),
        "dt": float(planned.dt) if planned.dt is not None else None,
        "pelvis_location": tuple(float(v) for v in planned.pelvis_location),
        "pelvis_rotation_deg": tuple(float(v) for v in planned.pelvis_rotation_deg),
        "spine_rotation_deg": tuple(float(v) for v in planned.spine_rotation_deg),
        "neck_rotation_deg": tuple(float(v) for v in planned.neck_rotation_deg),
        "head_rotation_deg": tuple(float(v) for v in planned.head_rotation_deg),
        "foot_L": {
            "world_xyz": tuple(float(v) for v in planned.foot_L.world_xyz),
            "is_locked": bool(planned.foot_L.is_locked),
            "rotation_deg": tuple(float(v) for v in planned.foot_L.rotation_deg),
            "clamp_reach": bool(planned.foot_L.clamp_reach),
            "clamp_ground": bool(planned.foot_L.clamp_ground),
            "contact_intent": bool(planned.foot_L.contact_intent),
            "surface_id": str(planned.foot_L.surface_id),
            "normal_world": tuple(float(v) for v in planned.foot_L.normal_world),
        },
        "foot_R": {
            "world_xyz": tuple(float(v) for v in planned.foot_R.world_xyz),
            "is_locked": bool(planned.foot_R.is_locked),
            "rotation_deg": tuple(float(v) for v in planned.foot_R.rotation_deg),
            "clamp_reach": bool(planned.foot_R.clamp_reach),
            "clamp_ground": bool(planned.foot_R.clamp_ground),
            "contact_intent": bool(planned.foot_R.contact_intent),
            "surface_id": str(planned.foot_R.surface_id),
            "normal_world": tuple(float(v) for v in planned.foot_R.normal_world),
        },
        "hand_L": (
            {
                "enabled": bool(planned.hand_L.enabled),
                "world_xyz": tuple(float(v) for v in planned.hand_L.world_xyz),
                "rotation_deg": tuple(float(v) for v in planned.hand_L.rotation_deg) if planned.hand_L.rotation_deg else None,
                "pole_hint_world_xyz": tuple(float(v) for v in planned.hand_L.pole_hint_world_xyz) if planned.hand_L.pole_hint_world_xyz else None,
                "clamp_reach": bool(planned.hand_L.clamp_reach),
            }
            if planned.hand_L
            else None
        ),
        "hand_R": (
            {
                "enabled": bool(planned.hand_R.enabled),
                "world_xyz": tuple(float(v) for v in planned.hand_R.world_xyz),
                "rotation_deg": tuple(float(v) for v in planned.hand_R.rotation_deg) if planned.hand_R.rotation_deg else None,
                "pole_hint_world_xyz": tuple(float(v) for v in planned.hand_R.pole_hint_world_xyz) if planned.hand_R.pole_hint_world_xyz else None,
                "clamp_reach": bool(planned.hand_R.clamp_reach),
            }
            if planned.hand_R
            else None
        ),
        "fk_non_upper": {
            str(k): tuple(float(c) for c in v)
            for k, v in planned.fk_joint_rotations_deg.items()
            if not any(str(k).startswith(p) for p in ("upper_arm.", "forearm.", "hand."))
        },
        "fk_L": {
            str(k): tuple(float(c) for c in v)
            for k, v in planned.fk_joint_rotations_deg.items()
            if str(k).endswith(".L")
        },
        "fk_R": {
            str(k): tuple(float(c) for c in v)
            for k, v in planned.fk_joint_rotations_deg.items()
            if str(k).endswith(".R")
        },
        "active_step_index": int(planned.active_step_index),
        "gait_phase": float(planned.gait_phase),
        "is_flight": bool(planned.is_flight),
    }


def install_full_chain_observer(arm_obj, root_obj, capture_live_poses: bool = True):
    """Install read-only wrappers tracing the entire production chain without modifying behavior."""
    from src.motion.framework import MotionPlanner, MotionRuntimeContext
    from src.motion.kinematic_bridge import KinematicBridgeExecutor
    from src.motion.whole_body_controller import WholeBodyController

    orig_planner_exec = MotionPlanner.execute
    orig_compose = MotionRuntimeContext.compose_planned_pose
    orig_bridge_init = KinematicBridgeExecutor.__init__
    orig_bridge_exec = KinematicBridgeExecutor.execute_frame
    orig_wbc_init = WholeBodyController.__init__
    orig_wbc_exec = WholeBodyController.execute_frame

    trace: Dict[str, Any] = {
        "planner_execute_calls": 0,
        "planner_ids": [],
        "compose_calls": 0,
        "context_ids": [],
        "bridge_init_ids": [],
        "bridge_exec_calls": 0,
        "bridge_ids": [],
        "wbc_init_ids": [],
        "wbc_exec_calls": 0,
        "wbc_ids": [],
        "frame_call_order": [],
        "non_upper_integrity_mismatches": [],
        "compose_vs_bridge_mismatches": [],
        "compose_diagnostics": [],
        "planned_stream": [],
        "wbc_stream": [],
        "solve_frames": [],
        "last_composed_by_frame": {},
    }

    NON_UPPER_FIELDS = (
        "frame",
        "time_seconds",
        "root_position",
        "root_yaw_deg",
        "speed_mps",
        "accel_mps2",
        "motion_mode",
        "dt",
        "pelvis_location",
        "pelvis_rotation_deg",
        "spine_rotation_deg",
        "neck_rotation_deg",
        "head_rotation_deg",
        "foot_L",
        "foot_R",
        "fk_non_upper",
        "active_step_index",
        "gait_phase",
        "is_flight",
    )

    @functools.wraps(orig_planner_exec)
    def wrap_planner_exec(self, *args, **kwargs):
        trace["planner_execute_calls"] += 1
        trace["planner_ids"].append(id(self))
        return orig_planner_exec(self, *args, **kwargs)

    @functools.wraps(orig_compose)
    def wrap_compose(self, planned_pose, *args, **kwargs):
        before = _clone_planned_pose_dict(planned_pose)
        trace["frame_call_order"].append(("compose_enter", int(planned_pose.frame)))
        composed_pose, diag = orig_compose(self, planned_pose, *args, **kwargs)
        trace["compose_calls"] += 1
        trace["context_ids"].append(id(self))
        after = _clone_planned_pose_dict(composed_pose)
        for field in NON_UPPER_FIELDS:
            if before[field] != after[field]:
                trace["non_upper_integrity_mismatches"].append({
                    "frame": before["frame"],
                    "field": field,
                    "before": before[field],
                    "after": after[field],
                })
        trace["compose_diagnostics"].append({"frame": int(composed_pose.frame), **diag})
        trace["last_composed_by_frame"][int(composed_pose.frame)] = after
        trace["frame_call_order"].append(("compose_exit", int(composed_pose.frame)))
        return composed_pose, diag

    @functools.wraps(orig_bridge_init)
    def wrap_bridge_init(self, *args, **kwargs):
        orig_bridge_init(self, *args, **kwargs)
        trace["bridge_init_ids"].append(id(self))

    @functools.wraps(orig_wbc_init)
    def wrap_wbc_init(self, *args, **kwargs):
        orig_wbc_init(self, *args, **kwargs)
        trace["wbc_init_ids"].append(id(self))

    @functools.wraps(orig_bridge_exec)
    def wrap_bridge_exec(self, planned, *args, **kwargs):
        trace["frame_call_order"].append(("bridge_enter", int(planned.frame)))
        res = orig_bridge_exec(self, planned, *args, **kwargs)
        trace["bridge_exec_calls"] += 1
        trace["bridge_ids"].append(id(self))
        b_dict = _clone_planned_pose_dict(planned)
        c_dict = trace["last_composed_by_frame"].get(int(planned.frame))
        if c_dict is not None and b_dict != c_dict:
            trace["compose_vs_bridge_mismatches"].append(int(planned.frame))
        trace["planned_stream"].append(b_dict)
        if capture_live_poses:
            trace["solve_frames"].append(capture_whole_body_live_sample(arm_obj, root_obj, res, planned))
        trace["frame_call_order"].append(("bridge_exit", int(planned.frame)))
        return res

    @functools.wraps(orig_wbc_exec)
    def wrap_wbc_exec(self, targets, *args, **kwargs):
        trace["frame_call_order"].append(("wbc_enter", len(trace["wbc_stream"]) + 1))
        wbc = orig_wbc_exec(self, targets, *args, **kwargs)
        trace["wbc_exec_calls"] += 1
        trace["wbc_ids"].append(id(self))
        trace["wbc_stream"].append({
            "call_index": trace["wbc_exec_calls"],
            "success": bool(wbc.success),
            "has_rom_violation": bool(wbc.has_rom_violation),
            "is_all_reachable": bool(wbc.is_all_reachable),
            "max_end_effector_error_m": float(wbc.max_end_effector_error_m),
            "unmet_constraints": [
                {
                    "category": uc.category,
                    "target_name": uc.target_name,
                    "description": uc.description,
                    "error_amount": float(uc.error_amount),
                }
                for uc in wbc.unmet_constraints
            ],
        })
        trace["frame_call_order"].append(("wbc_exit", len(trace["wbc_stream"])))
        return wbc

    MotionPlanner.execute = wrap_planner_exec
    MotionRuntimeContext.compose_planned_pose = wrap_compose
    KinematicBridgeExecutor.__init__ = wrap_bridge_init
    KinematicBridgeExecutor.execute_frame = wrap_bridge_exec
    WholeBodyController.__init__ = wrap_wbc_init
    WholeBodyController.execute_frame = wrap_wbc_exec

    def restore() -> None:
        MotionPlanner.execute = orig_planner_exec
        MotionRuntimeContext.compose_planned_pose = orig_compose
        KinematicBridgeExecutor.__init__ = orig_bridge_init
        KinematicBridgeExecutor.execute_frame = orig_bridge_exec
        WholeBodyController.__init__ = orig_wbc_init
        WholeBodyController.execute_frame = orig_wbc_exec

    return trace, restore


def summarize_call_chain_trace(trace: Dict[str, Any], expected_frames: int) -> Dict[str, Any]:
    unique_planners = len(set(trace["planner_ids"]))
    unique_contexts = len(set(trace["context_ids"]))
    unique_bridges = len(set(trace["bridge_ids"]))
    unique_wbcs = len(set(trace["wbc_ids"]))
    summary = {
        "expected_frames": int(expected_frames),
        "planner_execute_calls": int(trace["planner_execute_calls"]),
        "compose_calls": int(trace["compose_calls"]),
        "bridge_exec_calls": int(trace["bridge_exec_calls"]),
        "wbc_exec_calls": int(trace["wbc_exec_calls"]),
        "unique_planner_instances": unique_planners,
        "unique_context_instances": unique_contexts,
        "unique_bridge_instances": unique_bridges,
        "unique_wbc_instances": unique_wbcs,
        "planner_ids": sorted(set(trace["planner_ids"])),
        "bridge_ids": sorted(set(trace["bridge_ids"])),
        "wbc_ids": sorted(set(trace["wbc_ids"])),
        "non_upper_integrity_mismatches": len(trace["non_upper_integrity_mismatches"]),
        "compose_vs_bridge_mismatches": len(trace["compose_vs_bridge_mismatches"]),
        "all_wbc_success": all(w["success"] for w in trace["wbc_stream"]),
    }
    return summary


# =============================================================================
# WHOLE-BODY MOTION METRICS & REOPEN CONSISTENCY CHECKS
# =============================================================================

def compute_whole_body_interval_metrics(
    solve_frames: List[Dict[str, Any]],
    frame_lo: int,
    frame_hi: int,
) -> Dict[str, Any]:
    vr = load_vr()
    sub = [f for f in solve_frames if frame_lo <= f["frame"] <= frame_hi]
    assert sub, f"Empty slice [{frame_lo}, {frame_hi}]"

    def _bone_span(bname: str) -> float:
        return vr._max_pairwise_quat_span_deg([f["bones"][bname]["rel_parent_quat"] for f in sub])

    root_span_m = vr._max_pairwise_pos_span_m([f["root_world_pos"] for f in sub])
    pelvis_dz_span_m = max(abs(a["pelvis_local_loc"][1] - b["pelvis_local_loc"][1]) for a in sub for b in sub)
    thigh_l_span = _bone_span("thigh.L")
    shin_l_span = _bone_span("shin.L")
    foot_l_span = _bone_span("foot.L")
    thigh_r_span = _bone_span("thigh.R")
    shin_r_span = _bone_span("shin.R")
    foot_r_span = _bone_span("foot.R")

    return {
        "frame_range": [int(frame_lo), int(frame_hi)],
        "frame_count": len(sub),
        "root_world_disp_m": root_span_m,
        "pelvis_local_dz_span_m": pelvis_dz_span_m,
        "pelvis_rel_span_deg": _bone_span("pelvis"),
        "spine_rel_span_deg": _bone_span("spine"),
        "lower_L": {
            "thigh_rel_span_deg": thigh_l_span,
            "shin_rel_span_deg": shin_l_span,
            "foot_rel_span_deg": foot_l_span,
            "ankle_world_span_m": vr._max_pairwise_pos_span_m([f["ankle_world_L"] for f in sub]),
        },
        "lower_R": {
            "thigh_rel_span_deg": thigh_r_span,
            "shin_rel_span_deg": shin_r_span,
            "foot_rel_span_deg": foot_r_span,
            "ankle_world_span_m": vr._max_pairwise_pos_span_m([f["ankle_world_R"] for f in sub]),
        },
        "upper_L": {
            **vr._compute_side_motion_metrics(sub, "L"),
            "elbow_pole_span_m": vr._max_pairwise_pos_span_m([f["elbow_pole_root_local_L"] for f in sub]),
        },
        "upper_R": {
            **vr._compute_side_motion_metrics(sub, "R"),
            "elbow_pole_span_m": vr._max_pairwise_pos_span_m([f["elbow_pole_root_local_R"] for f in sub]),
        },
    }


def verify_blend_reopen_worker(
    blend_path: str,
    solve_frames_json: str,
    expected_markers: int,
    report_json: str,
    frame_start: int = 1,
) -> Dict[str, Any]:
    """Reopen .blend in clean Blender process and compare EVERY frame against live solve poses."""
    import bpy
    from mathutils import Vector
    from mathutils import Quaternion, Vector

    vr = load_vr()
    with open(solve_frames_json, "r", encoding="utf-8") as fp:
        solve_data = json.load(fp)
    solve_frames = solve_data["solve_frames"]
    solve_by_f = {int(r["frame"]): r for r in solve_frames}
    frame_end = frame_start + len(solve_frames) - 1

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_path))
    scene = bpy.context.scene
    arm = bpy.data.objects.get("CharacterArmature")
    root = bpy.data.objects.get("CharacterRoot")
    hand_l = bpy.data.objects.get("Hand_L")
    hand_r = bpy.data.objects.get("Hand_R")

    assert arm is not None and root is not None
    assert len(arm.data.bones) == 19
    assert int(scene.frame_start) == frame_start and int(scene.frame_end) == frame_end
    assert int(scene.frame_current) == frame_start, f"Expected open frame {frame_start}, got {scene.frame_current}"
    assert int(scene.render.fps) == 24
    assert len(scene.timeline_markers) >= expected_markers
    assert hand_l is not None and hand_l.parent == arm and hand_l.parent_bone == "hand.L" and hand_l.animation_data is None
    assert hand_r is not None and hand_r.parent == arm and hand_r.parent_bone == "hand.R" and hand_r.animation_data is None

    slot_id, fcurves = vr._get_slot_fcurves(arm)
    assert slot_id is not None
    fc_by_path = {fc.data_path: fc for fc in fcurves}
    expected_fset = set(range(frame_start, frame_end + 1))
    inf_fcurve_summary = {}
    for cname, _, dp in UPPER_CONSTRAINTS:
        fc = fc_by_path.get(dp)
        assert fc is not None, f"Missing FCurve {dp}"
        assert {int(round(kp.co[0])) for kp in fc.keyframe_points} == expected_fset
        assert sorted({str(kp.interpolation) for kp in fc.keyframe_points}) == ["CONSTANT"]
        inf_fcurve_summary[cname] = {"keyframes": len(fc.keyframe_points), "interpolation": "CONSTANT"}

    all_frames = list(range(frame_start, frame_end + 1))
    orders = [
        ("forward", list(all_frames)),
        ("reverse", list(reversed(all_frames))),
        ("shuffled_seed_20261127", random.Random(20261127).sample(all_frames, len(all_frames))),
    ]

    traversals = []
    for oname, fseq in orders:
        max_p, max_r, max_i = 0.0, 0.0, 0.0
        failures = []
        for f in fseq:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            exp = solve_by_f[f]
            aw = arm.matrix_world
            rw = root.matrix_world

            for lbl, vec, e_xyz in (
                ("root_world_pos", rw.translation, exp["root_world_pos"]),
                ("wrist_world_L", aw @ arm.pose.bones["forearm.L"].tail, exp["wrist_world_L"]),
                ("wrist_world_R", aw @ arm.pose.bones["forearm.R"].tail, exp["wrist_world_R"]),
                ("elbow_world_L", aw @ arm.pose.bones["upper_arm.L"].tail, exp["elbow_world_L"]),
                ("elbow_world_R", aw @ arm.pose.bones["upper_arm.R"].tail, exp["elbow_world_R"]),
                ("elbow_pole_world_L", bpy.data.objects["ElbowPole.L"].matrix_world.translation, exp["elbow_pole_world_L"]),
                ("elbow_pole_world_R", bpy.data.objects["ElbowPole.R"].matrix_world.translation, exp["elbow_pole_world_R"]),
                ("ankle_world_L", aw @ arm.pose.bones["shin.L"].tail, exp["ankle_world_L"]),
                ("ankle_world_R", aw @ arm.pose.bones["shin.R"].tail, exp["ankle_world_R"]),
            ):
                perr = (vec - Vector(e_xyz)).length
                max_p = max(max_p, perr)
                if perr > REOPEN_POS_TOL_M:
                    failures.append({"frame": f, "metric": lbl, "error": perr})

            rq_err = vr._quat_angle_rad(rw.to_3x3().normalized().to_quaternion(), Quaternion(exp["root_world_quat"]))
            max_r = max(max_r, rq_err)
            if rq_err > REOPEN_ROT_TOL_RAD:
                failures.append({"frame": f, "metric": "root_world_quat", "error": rq_err})

            for bname in BODY_TELEMETRY_BONES:
                pb = arm.pose.bones[bname]
                wq = (aw @ pb.matrix).to_3x3().normalized().to_quaternion()
                rerr = vr._quat_angle_rad(wq, Quaternion(exp["bones"][bname]["world_quat"]))
                max_r = max(max_r, rerr)
                if rerr > REOPEN_ROT_TOL_RAD:
                    failures.append({"frame": f, "metric": f"bone_world:{bname}", "error": rerr})

                rel_q, _ = vr._relative_joint_quat_and_euler(arm, bname)
                rel_err = vr._quat_angle_rad(rel_q, Quaternion(exp["bones"][bname]["rel_parent_quat"]))
                max_r = max(max_r, rel_err)
                if rel_err > REOPEN_ROT_TOL_RAD:
                    failures.append({"frame": f, "metric": f"bone_rel:{bname}", "error": rel_err})

            for cname in UPPER_CONTROLLERS:
                cq = bpy.data.objects[cname].matrix_world.to_3x3().normalized().to_quaternion()
                cerr = vr._quat_angle_rad(cq, Quaternion(exp["controllers"][cname]["world_quat"]))
                max_r = max(max_r, cerr)
                if cerr > REOPEN_ROT_TOL_RAD:
                    failures.append({"frame": f, "metric": f"ctrl:{cname}", "error": cerr})

            for cname, bname, _ in UPPER_CONSTRAINTS:
                ival = float(arm.pose.bones[bname].constraints[cname].influence)
                ierr = abs(ival - exp["influences"][cname])
                max_i = max(max_i, ierr)
                if ierr > REOPEN_INF_TOL:
                    failures.append({"frame": f, "metric": f"inf:{cname}", "error": ierr})

        assert not failures, f"{blend_path} ({oname}) reopen mismatch: {failures[:5]}"
        traversals.append({
            "order": oname,
            "frames_checked": len(fseq),
            "max_pos_err_m": max_p,
            "max_rot_err_rad": max_r,
            "max_inf_err": max_i,
            "passed": True,
        })

    out = {
        "passed": True,
        "blend_path": os.path.abspath(blend_path),
        "frame_start": frame_start,
        "frame_end": frame_end,
        "open_frame": int(scene.frame_current),
        "fps": int(scene.render.fps),
        "action_slot_identifier": slot_id,
        "influence_fcurves": inf_fcurve_summary,
        "traversals": traversals,
    }
    os.makedirs(os.path.dirname(os.path.abspath(report_json)), exist_ok=True)
    with open(report_json, "w", encoding="utf-8") as fp:
        json.dump(out, fp, indent=2)
    return out


# =============================================================================
# BRAND-NEW TRAJECTORY SYNTHESIZERS & REAL-RIG ENDPOINT SOLVERS
# =============================================================================

def new_fk_waypoint(side: str, idx: int, seed_offset: float) -> Tuple[Tuple[float, float, float], ...]:
    """Generate fresh non-periodic FK posture strictly inside humanoid ROM limits."""
    ext = load_ext()
    s = 1.0 if side == "L" else -1.0
    p = idx * 1.43 + seed_offset
    ua_x = 36.0 + 52.0 * math.sin(p * 1.21 + 0.4) - 24.0 * math.cos(p * 1.93)
    ua_y = 32.0 * math.cos(p * 1.37 - 0.5 * s) + 12.0 * math.sin(p * 2.27)
    if side == "L":
        ua_z = 34.0 + 44.0 * math.cos(p * 0.83 + 0.6) + 18.0 * math.sin(p * 1.71)
    else:
        ua_z = -38.0 - 44.0 * math.sin(p * 0.89 - 0.5) - 18.0 * math.cos(p * 1.67)
    fa_x = 54.0 + 44.0 * math.cos(p * 1.33 + 0.7) + 14.0 * math.sin(p * 2.11)
    fa_y = 36.0 * math.sin(p * 1.59 - 0.3)
    hd_x = 32.0 * math.cos(p * 1.73 + 0.2)
    hd_y = 10.0 * math.sin(p * 2.03 + 0.9)
    hd_z = 16.0 * math.cos(p * 1.49 - 0.8)
    return ext._clamp_fk_triplet(side, (ua_x, ua_y, ua_z), (fa_x, fa_y, 0.0), (hd_x, hd_y, hd_z))


def new_ik_waypoint(side: str, idx: int, seed_offset: float):
    """Generate fresh non-periodic IK (wrist_local, pole_local, hand_local_deg) waypoint."""
    ext = load_ext()
    sx = -1.0 if side == "L" else 1.0
    p = idx * 1.39 + seed_offset
    wx = sx * (0.27 + 0.17 * math.cos(p * 1.13) + 0.05 * math.sin(p * 1.87))
    wy = 0.17 + 0.21 * math.cos(p * 1.27 + 0.5) - 0.05 * math.sin(p * 2.19)
    wz = 1.28 + 0.22 * math.sin(p * 0.93 + 0.7 * sx) + 0.07 * math.cos(p * 1.69)

    px = sx * (0.35 + 0.10 * math.sin(p * 1.23))
    py = -0.23 - 0.06 * abs(math.cos(p * 1.49))
    pz = 1.20 + 0.09 * math.cos(p * 1.17 + 0.6)

    rx = 26.0 * math.cos(p * 1.61 + 0.3)
    ry = 9.0 * math.sin(p * 1.91 - 0.2)
    rz = 14.0 * math.cos(p * 1.31 + 1.0)
    return ext._clamp_ik_waypoint(side, (wx, wy, wz), (px, py, pz), (rx, ry, rz))


def solve_verified_ik_block(
    side: str,
    start_state: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]],
    spans: List[Tuple[float, float]],
    seed_offset: float,
    pelvis_dz: float = 0.06,
    postures: Sequence[Tuple[float, float, float]] = (
        (0.00, 0.0, 0.0),
        (0.060, -10.0, -2.5),
        (0.115, -20.0, -3.5),
        (0.090, 6.5, -1.5),
    ),
    per_seg_postures: Optional[Sequence[Sequence[Tuple[float, float, float]]]] = None,
):
    """Build verified IK UpperLimbSegments validated across multi-action torso lean & pelvis drop postures."""
    import bpy
    from mathutils import Vector
    from mathutils import Euler, Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.arm_ik import setup_arm_ik, set_hand_ik_target
    from src.motion.upper_limb_trajectory import UpperLimbSegment
    from src.motion.joint_limits import DEFAULT_HUMANOID_ROM_MODEL, extract_evaluated_bone_rotation_rad

    vr = load_vr()
    raw_wp = [new_ik_waypoint(side, i + 1, seed_offset) for i in range(len(spans))]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    parts = build_character(cfg)
    root = bpy.data.objects["CharacterRoot"]
    root.location = (0.0, 0.0, 0.0)
    arm = build_rig(cfg, character_root=root)
    bind_character_to_rig(arm, parts)
    setup_arm_ik(arm)
    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
    bpy.context.view_layer.update()

    def _lerp3(a, b, h):
        return ((1.0 - h) * a[0] + h * b[0], (1.0 - h) * a[1] + h * b[1], (1.0 - h) * a[2] + h * b[2])

    def _wrap_near_deg(deg_xyz, ref_deg_xyz):
        return tuple(a + 360.0 * round((ref - a) / 360.0) for a, ref in zip(deg_xyz, ref_deg_xyz))

    def _clamp_local_wp(w_xyz, p_xyz, r_deg):
        sx = -1.0 if side == "L" else 1.0
        # Centered between upright shoulder (sx*0.24, 0.00, 1.54) and deep sprint shoulder (sx*0.24, 0.16, 1.32)
        sh = (0.26 * sx, 0.10, 1.38)
        dx, dy, dz = w_xyz[0] - sh[0], w_xyz[1] - sh[1], w_xyz[2] - sh[2]
        d = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d < 0.22:
            f = 0.22 / max(d, 1e-6)
            dx, dy, dz = dx * f, dy * f, dz * f
        elif d > 0.38:
            f = 0.38 / d
            dx, dy, dz = dx * f, dy * f, dz * f
        cw = (
            sx * max(0.20, min(0.48, sx * (sh[0] + dx))),
            max(0.26, min(0.52, sh[1] + dy)),
            max(1.06, min(1.42, sh[2] + dz)),
        )
        cp = (
            sx * max(0.26, min(0.46, sx * p_xyz[0])),
            min(-0.20, p_xyz[1]),
            max(1.06, min(1.22, p_xyz[2])),
        )
        cr = (max(-18.0, min(20.0, r_deg[0])), max(-3.0, min(3.0, r_deg[1])), max(-7.0, min(7.0, r_deg[2])))
        return cw, cp, cr

    def _segment_midpoints_safe(cw, cp, cr, nw, np, nr, active_postures) -> Optional[float]:
        worst_margin = 1e9
        for dz_test, spine_deg, pelvis_deg in active_postures:
            arm.pose.bones["pelvis"].location = (0.0, -dz_test, 0.0)
            arm.pose.bones["pelvis"].rotation_mode = "XYZ"
            arm.pose.bones["pelvis"].rotation_euler = (math.radians(pelvis_deg), 0.0, 0.0)
            arm.pose.bones["spine"].rotation_mode = "XYZ"
            arm.pose.bones["spine"].rotation_euler = (math.radians(spine_deg), 0.0, 0.0)
            for h in (0.0, 0.25, 0.50, 0.75, 1.0):
                wh = root.matrix_world @ Vector(_lerp3(cw, nw, h))
                ph = root.matrix_world @ Vector(_lerp3(cp, np, h))
                rh = _lerp3(cr, nr, h)
                st = set_hand_ik_target(
                    arm,
                    side,
                    world_xyz=(wh.x, wh.y, wh.z),
                    hand_rotation_deg=rh,
                    pole_world_xyz=(ph.x, ph.y, ph.z),
                    clamp_reach=False,
                    influence=1.0,
                )
                bpy.context.view_layer.update()
                if (not st["is_reachable"]) or st["target_error"] > 0.003:
                    return None
                rom = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm, use_evaluated_ik=True)
                if [k for k in rom.violations if str(k).endswith(f".{side}")]:
                    return None
                ux, uy, uz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"upper_arm.{side}"]))
                fx, fy, fz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"forearm.{side}"]))
                hx, hy, hz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"hand.{side}"]))
                uz_min, uz_max = (-24.0, 140.0) if side == "L" else (-140.0, 24.0)
                cone_margin = (0.92 - math.hypot(ux / 160.0, uz / 150.0)) * 100.0
                margin = min(
                    ux - (-44.0), 150.0 - ux, 74.0 - abs(uy), uz - uz_min, uz_max - uz, cone_margin,
                    fx - 4.0, 140.0 - fx, 78.0 - abs(fy), 2.5 - abs(fz),
                    hx - (-54.0), 64.0 - hx, 17.5 - abs(hy), 26.0 - abs(hz),
                )
                if margin < 0.0:
                    return None
                worst_margin = min(worst_margin, margin)
        return worst_margin

    segments: List[UpperLimbSegment] = []
    cur_w, cur_p, cur_r = start_state
    safe_home_w = (-0.34 if side == "L" else 0.34, 0.38, 1.24)
    safe_home_p = (-0.38 if side == "L" else 0.38, -0.26, 1.14)
    # Solve reference hand orientation near mid-posture spine tilt (-6 deg) to equalize lean headroom
    ref_spine_deg = sum(p[1] for p in postures) / float(len(postures))

    for seg_idx, ((t_start, dur), (tgt_w, tgt_p, tgt_r_local)) in enumerate(zip(spans, raw_wp)):
        seg_postures = list(per_seg_postures[seg_idx]) if per_seg_postures is not None else list(postures)
        next_postures = (
            list(per_seg_postures[seg_idx + 1])
            if (per_seg_postures is not None and seg_idx + 1 < len(per_seg_postures))
            else []
        )
        end_postures = seg_postures + [p for p in next_postures if p not in seg_postures]
        ref_spine_deg = sum(p[1] for p in seg_postures) / float(len(seg_postures))
        dx, dy, dz = tgt_w[0] - cur_w[0], tgt_w[1] - cur_w[1], tgt_w[2] - cur_w[2]
        step_dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        base_scale = min(1.0, 0.24 / step_dist) if step_dist > 0.24 else 1.0

        chosen = None
        for alpha in (1.0, 0.72, 0.48, 0.28, 0.14):
            s = base_scale * alpha
            cw_raw = (cur_w[0] + s * dx, cur_w[1] + s * dy, cur_w[2] + s * dz)
            cp_raw = (
                cur_p[0] + s * (tgt_p[0] - cur_p[0]),
                cur_p[1] + s * (tgt_p[1] - cur_p[1]),
                cur_p[2] + s * (tgt_p[2] - cur_p[2]),
            )
            for r_scale in (1.0, 0.55, 0.15, 0.0):
                cr_loc = (tgt_r_local[0] * r_scale, tgt_r_local[1] * r_scale, tgt_r_local[2] * r_scale)
                cand_w, cand_p, cand_r_loc = _clamp_local_wp(cw_raw, cp_raw, cr_loc)
                arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
                arm.pose.bones["pelvis"].rotation_euler = (0.0, 0.0, 0.0)
                arm.pose.bones["spine"].rotation_euler = (math.radians(ref_spine_deg), 0.0, 0.0)
                raw_deg = vr._compute_hand_world_rot_for_ik_keypose(arm, side, cand_w, cand_p, cand_r_loc)
                mat = Euler([math.radians(a) for a in raw_deg], "XYZ").to_matrix()
                cur_euler = Euler([math.radians(a) for a in cur_r], "XYZ")
                cand_eulers = [
                    _wrap_near_deg(raw_deg, cur_r),
                    _wrap_near_deg(tuple(math.degrees(a) for a in mat.to_euler("XYZ", cur_euler)), cur_r),
                ]
                for nr in cand_eulers:
                    if (
                        _segment_midpoints_safe(cur_w, cur_p, cur_r, cand_w, cand_p, nr, seg_postures) is not None
                        and _segment_midpoints_safe(cand_w, cand_p, nr, cand_w, cand_p, nr, end_postures) is not None
                    ):
                        chosen = (cand_w, cand_p, nr)
                        break
                if chosen is not None:
                    break
            if chosen is not None:
                break

        if chosen is None:
            sx = -1.0 if side == "L" else 1.0
            anchors = [
                (safe_home_w, safe_home_p),
                (start_state[0], start_state[1]),
                ((0.32 * sx, 0.28, 1.26), safe_home_p),
                ((0.28 * sx, 0.35, 1.32), (0.38 * sx, -0.26, 1.16)),
            ]
            for anc_w, anc_p in anchors:
                hdx, hdy, hdz = anc_w[0] - cur_w[0], anc_w[1] - cur_w[1], anc_w[2] - cur_w[2]
                for s_h in (1.0, 0.70, 0.45, 0.25, 0.12, 0.05, 0.0):
                    cw_raw = (cur_w[0] + s_h * hdx, cur_w[1] + s_h * hdy, cur_w[2] + s_h * hdz)
                    cp_raw = (
                        cur_p[0] + s_h * (anc_p[0] - cur_p[0]),
                        cur_p[1] + s_h * (anc_p[1] - cur_p[1]),
                        cur_p[2] + s_h * (anc_p[2] - cur_p[2]),
                    )
                    cand_w, cand_p, _ = _clamp_local_wp(cw_raw, cp_raw, (0.0, 0.0, 0.0))
                    if s_h == 0.0:
                        cand_w, cand_p = cur_w, cur_p
                    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
                    arm.pose.bones["pelvis"].rotation_euler = (0.0, 0.0, 0.0)
                    arm.pose.bones["spine"].rotation_euler = (math.radians(ref_spine_deg), 0.0, 0.0)
                    raw_deg = vr._compute_hand_world_rot_for_ik_keypose(arm, side, cand_w, cand_p, (0.0, 0.0, 0.0))
                    mat = Euler([math.radians(a) for a in raw_deg], "XYZ").to_matrix()
                    cur_euler = Euler([math.radians(a) for a in cur_r], "XYZ")
                    cand_rots = [
                        _wrap_near_deg(raw_deg, cur_r),
                        _wrap_near_deg(tuple(math.degrees(a) for a in mat.to_euler("XYZ", cur_euler)), cur_r),
                        cur_r,
                    ]
                    for nr in cand_rots:
                        if (
                            _segment_midpoints_safe(cur_w, cur_p, cur_r, cand_w, cand_p, nr, seg_postures) is not None
                            and _segment_midpoints_safe(cand_w, cand_p, nr, cand_w, cand_p, nr, end_postures) is not None
                        ):
                            chosen = (cand_w, cand_p, nr)
                            break
                    if chosen is not None:
                        break
                if chosen is not None:
                    break

        assert chosen is not None, f"Failed to find safe multi-posture IK path for {side} seg {seg_idx}"
        nw, np, nr = chosen
        segments.append(
            UpperLimbSegment(
                mode="IK",
                start_time_sec=float(t_start),
                duration_sec=float(dur),
                wrist_start_xyz=cur_w,
                wrist_end_xyz=nw,
                pole_start_xyz=cur_p,
                pole_end_xyz=np,
                rotation_start_deg=cur_r,
                rotation_end_deg=nr,
                position_space="ROOT_LOCAL",
                clamp_reach=False,
            )
        )
        cur_w, cur_p, cur_r = nw, np, nr
    return segments


def compute_ik_state_from_fk_pose(
    fk_pose: Tuple[Tuple[float, float, float], ...],
    side: str,
    pelvis_dz: float = 0.06,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """Evaluate exact FK pose in an isolated real 19-bone rig to extract continuous IK starting target."""
    import bpy
    from mathutils import Vector
    from mathutils import Euler
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.arm_ik import set_arm_ik_influence, setup_arm_ik

    ext = load_ext()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    parts = build_character(cfg)
    root = bpy.data.objects["CharacterRoot"]
    root.location = (0.0, 0.0, 0.0)
    arm = build_rig(cfg, character_root=root)
    bind_character_to_rig(arm, parts)
    setup_arm_ik(arm, initial_influence=0.0)
    set_arm_ik_influence(arm, side, 0.0)
    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
    for bn, deg in zip((f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}"), fk_pose):
        pb = arm.pose.bones[bn]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = Euler([math.radians(a) for a in deg], "XYZ")
    bpy.context.view_layer.update()
    return ext._extract_ik_endpoint_from_live_arm(arm, root, side)


def probe_real_sequence_poses(
    planner_factory: Callable[[], Tuple[Any, Any, Dict[str, Any]]],
    upper_limb_L: Optional[Tuple[Any, ...]],
    upper_limb_R: Optional[Tuple[Any, ...]],
    sequence_duration_sec: float,
    capture_frames: Sequence[int],
) -> Dict[int, Dict[str, Any]]:
    """Execute a partial real production sequence up to full planner run and extract exact FK/IK poses at target frames."""
    from src.motion.framework import MotionPlanner

    ext = load_ext()
    cfg, env, extras = planner_factory()
    arm_obj = extras["arm_obj"]
    root_obj = extras["root_obj"]
    actions = extras["actions"]
    init_state = extras["initial_state"]
    want = set(capture_frames)
    captured: Dict[int, Dict[str, Any]] = {}

    from src.motion.kinematic_bridge import KinematicBridgeExecutor
    orig_ef = KinematicBridgeExecutor.execute_frame

    @functools.wraps(orig_ef)
    def wrap_ef(self, planned, *args, **kwargs):
        res = orig_ef(self, planned, *args, **kwargs)
        if planned.frame in want:
            captured[int(planned.frame)] = {
                "fk_L": ext._extract_bone_local_fk_deg(arm_obj, "L"),
                "fk_R": ext._extract_bone_local_fk_deg(arm_obj, "R"),
                "ik_L": ext._extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "L"),
                "ik_R": ext._extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "R"),
                "pelvis_local_loc": [float(v) for v in arm_obj.pose.bones["pelvis"].location],
            }
        return res

    KinematicBridgeExecutor.execute_frame = wrap_ef
    try:
        planner = MotionPlanner(
            config=cfg,
            armature_obj=arm_obj,
            environment=env,
            upper_limb_L=upper_limb_L,
            upper_limb_R=upper_limb_R,
            sequence_duration_sec=sequence_duration_sec,
        )
        for act in actions:
            planner.add_action(act)
        planner.execute(initial_state=init_state)
    finally:
        KinematicBridgeExecutor.execute_frame = orig_ef
    return captured
