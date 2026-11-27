"""TASK 10-d-5 — Unified Procedural Motion Showcase Generator & Verifier (Blender 5.1.1).

Integrates historical locomotion actions with Task 10-D independent bilateral
upper-limb FK/IK control inside ONE single MotionPlanner.execute() run, using
ONE character, ONE 19-bone rig, ONE EnvironmentQuery(ground_z=0.0) flat ground,
and ONE continuous timeline:

  Stage A: TerrainWalkAction (stationary standing, 10.0s = 240 frames)
           Bilateral independent FK / IK / mixed upper-limb motion (upper_arm, forearm, hand)
  Stage B: StartStopWalkAction (8.5s = 204 frames)
           Idle -> acceleration -> steady walk -> deceleration -> stop
  Stage C: TerrainWalkAction (flat walk 6.00m, 17.0s = 408 frames)
           Bilateral independent FK / IK / mixed upper-limb motion at varied speeds & targets
  Stage D: SprintStartAction (4.75s = 114 frames)
           Prep crouch -> push-off -> acceleration -> steady sprint (2.0 m/s)
  Stage E: SprintBrakeAction (2.0s = 48 frames)
           Braking steps -> full stop (direct MotionState handoff from Stage D)
  Stage F: TerrainWalkAction (stationary post-stop, 8.0s = 192 frames)
           Independent bilateral FK/IK upper-limb motion after Root stops
  Stage G: RunAction (cycles=8, 8.0s = 192 frames)
           8 complete run cycles (stance, 80 airborne flight frames, historical FK arm swing)

Deliverable Blender asset:
  output/task10d_unified_motion_showcase.blend

Evidence & verification outputs:
  docs/evidence/10-d/10-d-5/unified_motion_showcase/
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import importlib.util
import json
import math
import os
import random
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
BLENDER_PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
THIS_FILE = os.path.abspath(__file__)
SHOWCASE_DIR = os.path.dirname(THIS_FILE)
REPO_ROOT = os.path.abspath(os.path.join(SHOWCASE_DIR, "..", "..", "..", "..", ".."))
REDELIVERY_SCRIPT = os.path.abspath(
    os.path.join(SHOWCASE_DIR, "..", "..", "10-d-4", "visual_redelivery", "generate_visual_redelivery.py")
)
EXTENDED_SCRIPT = os.path.abspath(
    os.path.join(SHOWCASE_DIR, "..", "..", "10-d-4", "extended_visual_delivery", "generate_extended_visual_delivery.py")
)
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
SCRATCH_WORK = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\unified_showcase_work"
)

EXPECTED_HEAD = "870e57e8cc398f40a28e93e8a99a1e86e6146449"
FROZEN_SOURCE_BLOBS = {
    "src/motion/terrain_walk.py": "d42519fe8e39d149bdcffec3378b5f5ee7601b91",
    "src/motion/kinematic_bridge.py": "9e68e0a6a44bdb538b75b4f4d99b117c1737c358",
    "src/motion/framework.py": "31a9c268e0833a93cc0e498227202256c3274f05",
    "src/motion/whole_body_controller.py": "562de6c0ce1e9009856a7d52ec89cd6d0c012be2",
    "src/motion/run_cycle.py": "283f1ef8d21264a7da5b7c556aae2fedcd6fd604",
    "src/motion/sprint_start.py": "e550409cd37f6175b538bea26fdc65d570976b8b",
    "src/motion/sprint_brake.py": "98363c0f3aa07162ac181e6d4903cb338674a556",
}

DELIVERABLE_BLEND = os.path.join(OUTPUT_DIR, "task10d_unified_motion_showcase.blend")

ALL_VERIFIED_BONES = (
    "pelvis",
    "spine",
    "shoulder.L",
    "upper_arm.L",
    "forearm.L",
    "hand.L",
    "shoulder.R",
    "upper_arm.R",
    "forearm.R",
    "hand.R",
    "thigh.L",
    "shin.L",
    "foot.L",
    "thigh.R",
    "shin.R",
    "foot.R",
)


def _setup_sys_path() -> None:
    norm_repo = os.path.normpath(REPO_ROOT)
    if norm_repo not in [os.path.normpath(os.path.abspath(p)) for p in sys.path if p]:
        sys.path.insert(0, REPO_ROOT)


def _load_module(mod_name: str, path: str):
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None, f"Cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# =============================================================================
# FLAT GROUND SCENE ASSEMBLY (REAL PRODUCTION CHARACTER + 19-BONE RIG + HAND MESHES)
# =============================================================================

def _assemble_flat_showcase_scene(vr, ev, with_decor: bool = True):
    """Build single flat-ground production scene with diagnostic visuals & follow cameras."""
    import bpy
    from mathutils import Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.pose import reset_pose
    from src.rig.ik import setup_leg_ik
    from src.rig.arm_ik import setup_arm_ik
    from src.motion.framework import EnvironmentQuery

    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    scene = bpy.context.scene
    scene.render.fps = cfg.fps
    env = EnvironmentQuery(ground_z=0.0)

    # World background
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs[0].default_value = (0.12, 0.14, 0.18, 1.0)
        bg.inputs[1].default_value = 0.8

    # Flat GroundPlane at Z=0.0 matching EnvironmentQuery(ground_z=0.0)
    env_col = bpy.data.collections.new("Environment")
    scene.collection.children.link(env_col)
    bpy.ops.mesh.primitive_plane_add(size=100.0, location=(0.0, 0.0, 0.0))
    ground_obj = bpy.context.active_object
    ground_obj.name = "GroundPlane"
    for c in list(ground_obj.users_collection):
        c.objects.unlink(ground_obj)
    env_col.objects.link(ground_obj)

    mat_ground = vr._make_diagnostic_material("Showcase_FlatGround", (0.20, 0.22, 0.26, 1.0))
    ground_obj.data.materials.append(mat_ground)

    if with_decor:
        decor_col = bpy.data.collections.new("Showcase_EnvironmentDecor")
        scene.collection.children.link(decor_col)
        mat_stripe = vr._make_diagnostic_material("Showcase_DistanceStripe", (0.38, 0.42, 0.48, 1.0))
        mat_lane = vr._make_diagnostic_material("Showcase_TrackBorder", (0.28, 0.36, 0.46, 1.0))

        # Side lane border rails along Y=-14..+14 so forward progress is crystal clear
        for sx in (-1.2, 1.2):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(sx, 0.0, 0.002))
            rail = bpy.context.active_object
            rail.name = f"TrackRail_{'L' if sx < 0 else 'R'}"
            rail.scale = (0.04, 30.0, 0.004)
            for c in list(rail.users_collection):
                c.objects.unlink(rail)
            decor_col.objects.link(rail)
            rail.data.materials.append(mat_lane)

        # Meter ruler ticks every 2m along track
        for ym in range(-14, 15, 2):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, float(ym), 0.0015))
            tick = bpy.context.active_object
            tick.name = f"MeterTick_{ym:+03d}"
            tick.scale = (2.2, 0.04, 0.003)
            for c in list(tick.users_collection):
                c.objects.unlink(tick)
            decor_col.objects.link(tick)
            tick.data.materials.append(mat_stripe)

    # Real Character & 19-Bone Armature
    parts = build_character(cfg)
    root_obj = bpy.data.objects["CharacterRoot"]
    arm_obj = build_rig(cfg, character_root=root_obj)
    bind_character_to_rig(arm_obj, parts)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    setup_arm_ik(arm_obj)
    bpy.context.view_layer.update()

    # Diagnostic colors + BONE-parented Hand_L / Hand_R
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

    char_col = bpy.data.collections["Character"]
    hand_l = vr._build_asymmetric_hand_mesh(arm_obj, "L", char_col, mat_left, mat_dorsal)
    hand_r = vr._build_asymmetric_hand_mesh(arm_obj, "R", char_col, mat_right, mat_dorsal)

    # Lights
    light_col = bpy.data.collections.new("Showcase_Lights")
    scene.collection.children.link(light_col)
    sun_data = bpy.data.lights.new(name="PipelineSunLight", type="SUN")
    sun_data.energy = 2.6
    sun_obj = bpy.data.objects.new("PipelineSunLight", sun_data)
    sun_obj.location = Vector((5.0, -10.0, 10.0))
    sun_obj.rotation_euler = (math.radians(45.0), math.radians(15.0), math.radians(30.0))
    light_col.objects.link(sun_obj)

    fill_data = bpy.data.lights.new(name="ShowcaseFillLight", type="SUN")
    fill_data.energy = 0.8
    fill_obj = bpy.data.objects.new("ShowcaseFillLight", fill_data)
    fill_obj.rotation_euler = (math.radians(-35.0), math.radians(-20.0), math.radians(-140.0))
    light_col.objects.link(fill_obj)

    # Cameras attached to Root follow pivot
    cam_col = bpy.data.collections.new("VisualRedelivery_Cameras")
    scene.collection.children.link(cam_col)
    cameras = {}
    for cname, loc_xyz, look_xyz, lens in (
        ("Visual_FrontCam", (0.0, -6.80, 1.48), (0.0, -12.0, 1.00), 28.0),
        ("Visual_ObliqueSideCam", (4.20, -7.60, 2.25), (0.0, -11.85, 1.00), 26.0),
    ):
        cdata = bpy.data.cameras.new(cname)
        cdata.lens = lens
        cdata.clip_start = 0.05
        cdata.clip_end = 250.0
        cobj = bpy.data.objects.new(cname, cdata)
        loc = Vector(loc_xyz)
        tgt = Vector(look_xyz)
        cobj.location = loc
        cobj.rotation_mode = "XYZ"
        cobj.rotation_euler = (tgt - loc).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
        cam_col.objects.link(cobj)
        cameras[cname] = cobj

    scene.camera = cameras["Visual_ObliqueSideCam"]
    ev._attach_root_follow_camera(scene, root_obj, cameras["Visual_ObliqueSideCam"])
    bpy.context.view_layer.update()
    return cfg, scene, root_obj, arm_obj, hand_l, hand_r, env


# =============================================================================
# FLAT-GROUND EXACT FK <-> IK BOUNDARY PRE-PROBING
# =============================================================================

def _probe_flat_exact_state(
    vr,
    ev,
    route,
    segs_l: Optional[Tuple[Any, ...]],
    segs_r: Optional[Tuple[Any, ...]],
    target_frames: Dict[str, int],
) -> Dict[str, Dict[str, Any]]:
    """Run TerrainWalkAction on flat EnvironmentQuery(ground_z=0.0) & capture exact endpoints."""
    from src.motion.terrain_walk import TerrainWalkAction
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, _, env = _assemble_flat_showcase_scene(vr, ev, with_decor=False)
    want_set = set(target_frames.values())
    orig_ef, kb_cls, _, _, _ = vr._install_solve_observer(arm_obj, root_obj)

    live_endpoints: Dict[int, Dict[str, Any]] = {}
    wrapped_inner = kb_cls.execute_frame

    def capture_hook(self, planned, *args, **kwargs):
        res = wrapped_inner(self, planned, *args, **kwargs)
        if planned.frame in want_set:
            live_endpoints[planned.frame] = {
                "fk_L": ev._extract_bone_local_fk_deg(arm_obj, "L"),
                "fk_R": ev._extract_bone_local_fk_deg(arm_obj, "R"),
                "ik_L": ev._extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "L"),
                "ik_R": ev._extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "R"),
                "root_pos": [float(v) for v in root_obj.matrix_world.translation],
            }
        return res

    kb_cls.execute_frame = capture_hook
    try:
        pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        pl.add_action(
            TerrainWalkAction(
                route=route,
                environment=env,
                action_name="FlatBoundaryProbe",
                upper_limb_L=segs_l,
                upper_limb_R=segs_r,
            )
        )
        pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        kb_cls.execute_frame = orig_ef

    return {label: live_endpoints[fnum] for label, fnum in target_frames.items()}


def _probe_flat_fk_ik_junctions(
    vr,
    ev,
    route,
    arm_pose_root_xyz: Tuple[float, float, float],
    pelvis_dz: float,
    l_after_frame: int,
    r_after_frame: int,
    l_target,
    r_target,
):
    """Pre-solve exact matching (fk_A, ik_A) pairs on flat EnvironmentQuery(ground_z=0.0)."""
    import bpy
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.arm_ik import setup_arm_ik
    from src.motion.terrain_walk import UpperLimbSegment

    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    parts = build_character(cfg)
    root = bpy.data.objects["CharacterRoot"]
    root.location = arm_pose_root_xyz
    arm = build_rig(cfg, character_root=root)
    bind_character_to_rig(arm, parts)
    setup_arm_ik(arm)
    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
    bpy.context.view_layer.update()

    w_L, p_L, r_loc_L = ev._clamp_ik_waypoint("L", *l_target)
    w_R, p_R, r_loc_R = ev._clamp_ik_waypoint("R", *r_target)
    rot_L = vr._compute_hand_world_rot_for_ik_keypose(arm, "L", w_L, p_L, r_loc_L)
    rot_R = vr._compute_hand_world_rot_for_ik_keypose(arm, "R", w_R, p_R, r_loc_R)

    hold_l = (
        UpperLimbSegment(
            mode="IK", start_time_sec=0.0, duration_sec=0.10,
            wrist_start_xyz=w_L, wrist_end_xyz=w_L,
            pole_start_xyz=p_L, pole_end_xyz=p_L,
            rotation_start_deg=rot_L, rotation_end_deg=rot_L,
            position_space="ROOT_LOCAL", clamp_reach=False,
        ),
    )
    hold_r = (
        UpperLimbSegment(
            mode="IK", start_time_sec=0.0, duration_sec=0.10,
            wrist_start_xyz=w_R, wrist_end_xyz=w_R,
            pole_start_xyz=p_R, pole_end_xyz=p_R,
            rotation_start_deg=rot_R, rotation_end_deg=rot_R,
            position_space="ROOT_LOCAL", clamp_reach=False,
        ),
    )
    res = _probe_flat_exact_state(vr, ev, route, hold_l, hold_r, {"L_after": l_after_frame, "R_after": r_after_frame})
    return {
        "fk_A_L": res["L_after"]["fk_L"],
        "ik_A_L": (w_L, p_L, rot_L),
        "fk_A_R": res["R_after"]["fk_R"],
        "ik_A_R": (w_R, p_R, rot_R),
    }


def _probe_chain_terminal_positions(vr, ev, stage_a_route, stage_c_route):
    """Run isolated flat MotionPlanner for A->B->C->D->E to get exact terminal Root position for Stage F."""
    from src.motion.terrain_walk import TerrainWalkAction
    from src.motion.framework import MotionPlanner, StartStopWalkAction, create_initial_motion_state
    from src.motion.sprint_start import SprintStartAction
    from src.motion.sprint_brake import SprintBrakeAction

    cfg, scene, root_obj, arm_obj, _, _, env = _assemble_flat_showcase_scene(vr, ev, with_decor=False)
    pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
    pl.add_action(TerrainWalkAction(route=stage_a_route, environment=env, action_name="StageA_Probe"))
    pl.add_action(StartStopWalkAction())
    pl.add_action(TerrainWalkAction(route=stage_c_route, environment=env, action_name="StageC_Probe"))
    pl.add_action(SprintStartAction())
    pl.add_action(SprintBrakeAction())
    res = pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=stage_a_route.start_pos))
    # ar indices: 0=StageA, 1=start_stop_walk, 2=StageC, 3=sprint_start, 4=sprint_brake
    return {
        "StageB_end": [float(v) for v in res["action_results"][1].final_state.position],
        "StageE_end": [float(v) for v in res["action_results"][4].final_state.position],
    }


# =============================================================================
# BILATERAL UPPER-LIMB SCHEDULES FOR STAGE A, STAGE C, AND STAGE F
# =============================================================================

def _build_stage_a_config(vr, ev, start_pos: Tuple[float, float, float]):
    """Stage A (240 frames = 10.0s, stationary): bilateral FK / IK / mixed upper-limb showcase."""
    from src.motion.terrain_walk import TerrainRouteInput, UpperLimbSegment

    route = TerrainRouteInput(
        start_pos=start_pos,
        target_pos=start_pos,
        stand_start_frames=240,
        stand_stop_frames=0,
    )

    # Staggered switch timeline within [0.00 .. 10.00s]:
    #   R FK -> IK at t = 54/24 = 2.25s (local frame 55)
    #   L FK -> IK at t = 96/24 = 4.00s (local frame 97)
    #   R IK -> FK at t = 150/24 = 6.25s (local frame 151)
    #   L IK -> FK at t = 192/24 = 8.00s (local frame 193)
    # Covers: Both FK -> L FK+R IK -> Both IK -> L IK+R FK -> Both FK
    # Ends in FK at StartStopWalkAction entry angles: ((0,0,-4),(0,0,0),(0,0,0)) / ((0,0,4),(0,0,0),(0,0,0))

    start_l = ((0.0, 0.0, -4.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    start_r = ((0.0, 0.0, 4.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    junc = _probe_flat_fk_ik_junctions(
        vr, ev, route, start_pos, 0.035,
        l_after_frame=97, r_after_frame=55,
        l_target=((-0.26, 0.30, 1.34), (-0.36, -0.22, 1.22), (18.0, 3.0, 6.0)),
        r_target=((0.30, 0.28, 1.32), (0.38, -0.22, 1.22), (-16.0, -3.0, -6.0)),
    )

    l_fk1 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=0.05, duration_sec=1.05,
            fk_start_deg=start_l,
            fk_end_deg=ev._clamp_fk_triplet("L", (46.0, 18.0, 28.0), (54.0, -24.0, 0.0), (24.0, 8.0, 12.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.10, duration_sec=1.05,
            fk_start_deg=ev._clamp_fk_triplet("L", (46.0, 18.0, 28.0), (54.0, -24.0, 0.0), (24.0, 8.0, 12.0)),
            fk_end_deg=ev._clamp_fk_triplet("L", (82.0, -22.0, 62.0), (88.0, 26.0, 0.0), (-26.0, -8.0, -14.0)),
        ),
        # Hold [2.15..2.85] while R transitions & starts moving in IK
        UpperLimbSegment(
            mode="FK", start_time_sec=2.85, duration_sec=1.10,
            fk_start_deg=ev._clamp_fk_triplet("L", (82.0, -22.0, 62.0), (88.0, 26.0, 0.0), (-26.0, -8.0, -14.0)),
            fk_end_deg=junc["fk_A_L"],
        ),
    ]
    r_fk1 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=0.10, duration_sec=0.70,
            fk_start_deg=start_r,
            fk_end_deg=ev._clamp_fk_triplet("R", (64.0, -20.0, -44.0), (74.0, 28.0, 0.0), (-28.0, -8.0, 12.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=0.80, duration_sec=0.70,
            fk_start_deg=ev._clamp_fk_triplet("R", (64.0, -20.0, -44.0), (74.0, 28.0, 0.0), (-28.0, -8.0, 12.0)),
            fk_end_deg=ev._clamp_fk_triplet("R", (-12.0, 26.0, -76.0), (36.0, -26.0, 0.0), (30.0, 9.0, -14.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.50, duration_sec=0.70,
            fk_start_deg=ev._clamp_fk_triplet("R", (-12.0, 26.0, -76.0), (36.0, -26.0, 0.0), (30.0, 9.0, -14.0)),
            fk_end_deg=junc["fk_A_R"],
        ),
    ]

    l_ik_raw = [
        ((-0.44, 0.24, 1.44), (-0.42, -0.24, 1.18), (22.0, 3.0, 7.0)),
        ((-0.18, 0.42, 1.24), (-0.30, -0.26, 1.12), (-20.0, -3.0, -7.0)),
        ((-0.38, 0.30, 1.48), (-0.40, -0.22, 1.24), (16.0, 2.0, 5.0)),
        ((-0.26, 0.26, 1.26), (-0.32, -0.24, 1.16), (-14.0, -2.0, -4.0)),
    ]
    r_ik_raw = [
        ((0.18, 0.40, 1.46), (0.34, -0.24, 1.22), (-22.0, -3.0, -7.0)),
        ((0.46, 0.22, 1.22), (0.42, -0.26, 1.10), (20.0, 3.0, 7.0)),
        ((0.28, 0.34, 1.48), (0.36, -0.22, 1.24), (-16.0, -2.0, -5.0)),
        ((0.36, 0.24, 1.26), (0.34, -0.24, 1.16), (12.0, 2.0, 4.0)),
    ]
    l_ik_spans = [(4.00, 1.00), (5.00, 1.00), (6.00, 0.95), (6.95, 1.00)]
    r_ik_spans = [(2.25, 0.95), (3.20, 1.00), (4.20, 1.00), (5.20, 1.00)]

    l_ik_segs = ev._solve_verified_ik_segments(vr, start_pos, 0.035, "L", junc["ik_A_L"], l_ik_spans, l_ik_raw)
    r_ik_segs = ev._solve_verified_ik_segments(vr, start_pos, 0.035, "R", junc["ik_A_R"], r_ik_spans, r_ik_raw)

    sw_end = _probe_flat_exact_state(
        vr, ev, route, tuple(l_fk1 + l_ik_segs), tuple(r_fk1 + r_ik_segs),
        {"L_ik_end": 192, "R_ik_end": 150},
    )
    fk_B_L = sw_end["L_ik_end"]["fk_L"]
    fk_B_R = sw_end["R_ik_end"]["fk_R"]

    l_fk2 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=8.00, duration_sec=0.95,
            fk_start_deg=fk_B_L,
            fk_end_deg=ev._clamp_fk_triplet("L", (52.0, -18.0, 48.0), (68.0, 22.0, 0.0), (22.0, 7.0, 10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=8.95, duration_sec=1.00,
            fk_start_deg=ev._clamp_fk_triplet("L", (52.0, -18.0, 48.0), (68.0, 22.0, 0.0), (22.0, 7.0, 10.0)),
            fk_end_deg=start_l,
        ),
    ]
    r_fk2 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=6.25, duration_sec=0.90,
            fk_start_deg=fk_B_R,
            fk_end_deg=ev._clamp_fk_triplet("R", (76.0, 20.0, -52.0), (84.0, -24.0, 0.0), (-26.0, -7.0, -12.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=7.15, duration_sec=0.90,
            fk_start_deg=ev._clamp_fk_triplet("R", (76.0, 20.0, -52.0), (84.0, -24.0, 0.0), (-26.0, -7.0, -12.0)),
            fk_end_deg=ev._clamp_fk_triplet("R", (18.0, -18.0, -18.0), (38.0, 18.0, 0.0), (18.0, 5.0, 8.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=8.05, duration_sec=1.10,
            fk_start_deg=ev._clamp_fk_triplet("R", (18.0, -18.0, -18.0), (38.0, 18.0, 0.0), (18.0, 5.0, 8.0)),
            fk_end_deg=start_r,
        ),
    ]
    return (
        route,
        tuple(l_fk1 + l_ik_segs + l_fk2),
        tuple(r_fk1 + r_ik_segs + r_fk2),
        {
            "L": [{"type": "FK_to_IK", "local_before": 96, "local_after": 97}, {"type": "IK_to_FK", "local_before": 192, "local_after": 193}],
            "R": [{"type": "FK_to_IK", "local_before": 54, "local_after": 55}, {"type": "IK_to_FK", "local_before": 150, "local_after": 151}],
        },
    )


def _build_stage_c_config(vr, ev, start_pos: Tuple[float, float, float]):
    """Stage C (408 frames = 17.0s, flat walk +6.00m): bilateral FK/IK/mixed motion at varied speeds."""
    from src.motion.terrain_walk import TerrainRouteInput, UpperLimbSegment

    target_pos = (start_pos[0], start_pos[1] + 6.00, start_pos[2])
    route = TerrainRouteInput(
        start_pos=start_pos,
        target_pos=target_pos,
        nominal_stride_m=0.30,
        step_frames=18,
        stand_start_frames=24,
        stand_stop_frames=24,
    )
    # 20 steps * 18f = 360 walk frames (frames 25..384, t=1.00s..16.00s) + 24 + 24 = 408 frames (17.0s)
    # Switches all staggered DURING walking:
    #   R FK -> IK at t = 4.00s (local frame 97)
    #   L FK -> IK at t = 7.00s (local frame 169, walk step boundary 24+8*18=168)
    #   R IK -> FK at t = 11.50s (local frame 277, walk step boundary 24+14*18=276)
    #   L IK -> FK at t = 14.50s (local frame 349, walk step boundary 24+18*18=348)
    # Entry matches StartStopWalk end: ((0,0,-4),(0,0,0),(0,0,0)) / ((0,0,4),(0,0,0),(0,0,0))
    # Exit matches SprintStart start:  ((0,0,-5),(0,0,0),(0,0,0)) / ((0,0,5),(0,0,0),(0,0,0))

    in_l = ((0.0, 0.0, -4.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    in_r = ((0.0, 0.0, 4.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    out_l = ((0.0, 0.0, -5.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    out_r = ((0.0, 0.0, 5.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    junc = _probe_flat_fk_ik_junctions(
        vr, ev, route, start_pos, 0.035,
        l_after_frame=169, r_after_frame=97,
        l_target=((-0.28, 0.30, 1.32), (-0.36, -0.22, 1.20), (16.0, 2.0, 5.0)),
        r_target=((0.30, 0.28, 1.34), (0.36, -0.22, 1.22), (-16.0, -2.0, -5.0)),
    )

    l_fk1_poses = [in_l] + [ev._generate_fk_pose_sample("L", i + 1, 0.45) for i in range(5)] + [junc["fk_A_L"]]
    l_fk1_spans = [(0.10, 0.90), (1.00, 1.15), (2.15, 0.70), (3.60, 0.95), (4.55, 1.20), (5.75, 1.20)]  # hold [2.85..3.60]
    l_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk1_spans[i][0], duration_sec=l_fk1_spans[i][1], fk_start_deg=l_fk1_poses[i], fk_end_deg=l_fk1_poses[i + 1])
        for i in range(6)
    ]

    r_fk1_poses = [in_r] + [ev._generate_fk_pose_sample("R", i + 1, 1.85) for i in range(4)] + [junc["fk_A_R"]]
    r_fk1_spans = [(0.15, 0.65), (0.80, 0.75), (1.55, 0.80), (2.35, 0.80), (3.15, 0.80)]
    r_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk1_spans[i][0], duration_sec=r_fk1_spans[i][1], fk_start_deg=r_fk1_poses[i], fk_end_deg=r_fk1_poses[i + 1])
        for i in range(5)
    ]

    l_ik_raw = [ev._generate_ik_waypoint_sample("L", i + 1, 0.80) for i in range(6)]
    r_ik_raw = [ev._generate_ik_waypoint_sample("R", i + 1, 2.35) for i in range(7)]
    l_ik_spans = [(7.00, 1.10), (8.10, 1.25), (9.35, 1.05), (10.40, 1.30), (11.70, 1.20), (12.90, 1.55)]  # ends 14.45 -> hold at 14.50
    r_ik_spans = [(4.00, 0.85), (4.85, 1.05), (5.90, 1.15), (7.05, 0.90), (8.60, 0.95), (9.55, 0.95), (10.50, 0.95)]  # hold [7.95..8.60], ends 11.45

    l_ik_segs = ev._solve_verified_ik_segments(vr, start_pos, 0.035, "L", junc["ik_A_L"], l_ik_spans, l_ik_raw)
    r_ik_segs = ev._solve_verified_ik_segments(vr, start_pos, 0.035, "R", junc["ik_A_R"], r_ik_spans, r_ik_raw)

    sw_end = _probe_flat_exact_state(
        vr, ev, route, tuple(l_fk1 + l_ik_segs), tuple(r_fk1 + r_ik_segs),
        {"L_ik_end": 348, "R_ik_end": 276},
    )
    fk_B_L = sw_end["L_ik_end"]["fk_L"]
    fk_B_R = sw_end["R_ik_end"]["fk_R"]

    l_fk2_poses = [fk_B_L, ev._generate_fk_pose_sample("L", 12, 0.95), out_l]
    l_fk2_spans = [(14.50, 1.20), (15.70, 1.20)]  # ends 16.90s
    l_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk2_spans[i][0], duration_sec=l_fk2_spans[i][1], fk_start_deg=l_fk2_poses[i], fk_end_deg=l_fk2_poses[i + 1])
        for i in range(2)
    ]

    r_fk2_poses = [fk_B_R] + [ev._generate_fk_pose_sample("R", i + 10, 0.55) for i in range(4)] + [out_r]
    r_fk2_spans = [(11.50, 1.00), (12.50, 1.05), (13.55, 1.05), (14.60, 1.10), (15.70, 1.20)]  # ends 16.90s
    r_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk2_spans[i][0], duration_sec=r_fk2_spans[i][1], fk_start_deg=r_fk2_poses[i], fk_end_deg=r_fk2_poses[i + 1])
        for i in range(5)
    ]

    return (
        route,
        tuple(l_fk1 + l_ik_segs + l_fk2),
        tuple(r_fk1 + r_ik_segs + r_fk2),
        {
            "L": [{"type": "FK_to_IK", "local_before": 168, "local_after": 169}, {"type": "IK_to_FK", "local_before": 348, "local_after": 349}],
            "R": [{"type": "FK_to_IK", "local_before": 96, "local_after": 97}, {"type": "IK_to_FK", "local_before": 276, "local_after": 277}],
        },
    )


def _build_stage_f_config(vr, ev, stop_pos: Tuple[float, float, float]):
    """Stage F (192 frames = 8.0s, stationary at stop_pos): post-stop bilateral FK/IK showcase."""
    from src.motion.terrain_walk import TerrainRouteInput, UpperLimbSegment

    route = TerrainRouteInput(
        start_pos=stop_pos,
        target_pos=stop_pos,
        stand_start_frames=192,
        stand_stop_frames=0,
    )
    # SprintBrake end -> ((0,0,-5),(10,0,0),(0,0,0)) / ((0,0,5),(10,0,0),(0,0,0))
    # RunAction tau=0  -> ((0,0,-5),(65,0,0),(0,0,0)) / ((0,0,5),(65,0,0),(0,0,0))
    # Staggered switches:
    #   L FK -> IK at t = 2.00s (local frame 49)
    #   R FK -> IK at t = 3.25s (local frame 79)
    #   L IK -> FK at t = 5.50s (local frame 133)
    #   R IK -> FK at t = 6.75s (local frame 163)

    in_l = ((0.0, 0.0, -5.0), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    in_r = ((0.0, 0.0, 5.0), (10.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    out_l = ((0.0, 0.0, -5.0), (65.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    out_r = ((0.0, 0.0, 5.0), (65.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    junc = _probe_flat_fk_ik_junctions(
        vr, ev, route, stop_pos, 0.035,
        l_after_frame=49, r_after_frame=79,
        l_target=((-0.30, 0.28, 1.34), (-0.36, -0.22, 1.22), (16.0, 2.0, 5.0)),
        r_target=((0.28, 0.30, 1.32), (0.36, -0.22, 1.20), (-16.0, -2.0, -5.0)),
    )

    l_fk1 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=0.05, duration_sec=0.95,
            fk_start_deg=in_l,
            fk_end_deg=ev._clamp_fk_triplet("L", (68.0, 24.0, 42.0), (74.0, -26.0, 0.0), (26.0, 8.0, 12.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.00, duration_sec=0.95,
            fk_start_deg=ev._clamp_fk_triplet("L", (68.0, 24.0, 42.0), (74.0, -26.0, 0.0), (26.0, 8.0, 12.0)),
            fk_end_deg=junc["fk_A_L"],
        ),
    ]
    r_fk1 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=0.10, duration_sec=1.05,
            fk_start_deg=in_r,
            fk_end_deg=ev._clamp_fk_triplet("R", (32.0, -24.0, -64.0), (48.0, 24.0, 0.0), (-24.0, -8.0, -10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.15, duration_sec=1.00,
            fk_start_deg=ev._clamp_fk_triplet("R", (32.0, -24.0, -64.0), (48.0, 24.0, 0.0), (-24.0, -8.0, -10.0)),
            fk_end_deg=ev._clamp_fk_triplet("R", (86.0, 18.0, -28.0), (92.0, -24.0, 0.0), (24.0, 6.0, 10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=2.15, duration_sec=1.05,
            fk_start_deg=ev._clamp_fk_triplet("R", (86.0, 18.0, -28.0), (92.0, -24.0, 0.0), (24.0, 6.0, 10.0)),
            fk_end_deg=junc["fk_A_R"],
        ),
    ]

    l_ik_raw = [
        ((-0.42, 0.24, 1.44), (-0.42, -0.24, 1.18), (22.0, 3.0, 7.0)),
        ((-0.18, 0.40, 1.24), (-0.30, -0.26, 1.12), (-20.0, -3.0, -7.0)),
        ((-0.36, 0.28, 1.44), (-0.38, -0.22, 1.22), (14.0, 2.0, 5.0)),
    ]
    r_ik_raw = [
        ((0.18, 0.40, 1.44), (0.32, -0.24, 1.22), (-20.0, -3.0, -6.0)),
        ((0.44, 0.24, 1.22), (0.42, -0.26, 1.10), (18.0, 3.0, 6.0)),
        ((0.26, 0.34, 1.46), (0.36, -0.22, 1.22), (-14.0, -2.0, -4.0)),
    ]
    l_ik_spans = [(2.00, 1.15), (3.15, 1.15), (4.30, 1.15)]
    r_ik_spans = [(3.25, 1.15), (4.40, 1.15), (5.55, 1.15)]

    l_ik_segs = ev._solve_verified_ik_segments(vr, stop_pos, 0.035, "L", junc["ik_A_L"], l_ik_spans, l_ik_raw)
    r_ik_segs = ev._solve_verified_ik_segments(vr, stop_pos, 0.035, "R", junc["ik_A_R"], r_ik_spans, r_ik_raw)

    sw_end = _probe_flat_exact_state(
        vr, ev, route, tuple(l_fk1 + l_ik_segs), tuple(r_fk1 + r_ik_segs),
        {"L_ik_end": 132, "R_ik_end": 162},
    )
    fk_B_L = sw_end["L_ik_end"]["fk_L"]
    fk_B_R = sw_end["R_ik_end"]["fk_R"]

    l_fk2 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=5.50, duration_sec=1.20,
            fk_start_deg=fk_B_L,
            fk_end_deg=ev._clamp_fk_triplet("L", (40.0, 12.0, 18.0), (88.0, -18.0, 0.0), (18.0, 6.0, 8.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=6.70, duration_sec=1.20,
            fk_start_deg=ev._clamp_fk_triplet("L", (40.0, 12.0, 18.0), (88.0, -18.0, 0.0), (18.0, 6.0, 8.0)),
            fk_end_deg=out_l,
        ),
    ]
    r_fk2 = [
        UpperLimbSegment(
            mode="FK", start_time_sec=6.75, duration_sec=1.15,
            fk_start_deg=fk_B_R,
            fk_end_deg=out_r,
        ),
    ]
    return (
        route,
        tuple(l_fk1 + l_ik_segs + l_fk2),
        tuple(r_fk1 + r_ik_segs + r_fk2),
        {
            "L": [{"type": "FK_to_IK", "local_before": 48, "local_after": 49}, {"type": "IK_to_FK", "local_before": 132, "local_after": 133}],
            "R": [{"type": "FK_to_IK", "local_before": 78, "local_after": 79}, {"type": "IK_to_FK", "local_before": 162, "local_after": 163}],
        },
    )


# =============================================================================
# FULL-BODY SOLVE-TIME OBSERVER (NO frame_set, NO view_layer.update DURING SOLVE)
# =============================================================================

def _capture_full_solve_sample(vr, arm_obj, root_obj, frame: int) -> Dict[str, Any]:
    root_mat = root_obj.matrix_world.copy()
    root_inv = root_mat.inverted()
    arm_mat = arm_obj.matrix_world.copy()

    bones_data: Dict[str, Any] = {}
    for bname in ALL_VERIFIED_BONES:
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
    foot_tail_L = arm_mat @ arm_obj.pose.bones["foot.L"].tail
    foot_tail_R = arm_mat @ arm_obj.pose.bones["foot.R"].tail

    import bpy
    controllers: Dict[str, Any] = {}
    for cname in vr.UPPER_CONTROLLERS:
        cobj = bpy.data.objects[cname]
        cm = cobj.matrix_world.copy()
        controllers[cname] = {
            "world_pos": [float(v) for v in cm.translation],
            "world_quat": [float(v) for v in cm.to_3x3().normalized().to_quaternion()],
        }

    influences: Dict[str, float] = {}
    for cname, bname, _ in vr.UPPER_CONSTRAINTS:
        influences[cname] = float(arm_obj.pose.bones[bname].constraints[cname].influence)

    return {
        "frame": int(frame),
        "root_world_pos": [float(v) for v in root_mat.translation],
        "root_world_matrix": vr._mat4_to_lists(root_mat),
        "root_world_quat": [float(v) for v in root_mat.to_3x3().normalized().to_quaternion()],
        "wrist_world_L": [float(v) for v in wrist_world_L],
        "wrist_world_R": [float(v) for v in wrist_world_R],
        "wrist_root_local_L": [float(v) for v in (root_inv @ wrist_world_L)],
        "wrist_root_local_R": [float(v) for v in (root_inv @ wrist_world_R)],
        "elbow_world_L": [float(v) for v in elbow_world_L],
        "elbow_world_R": [float(v) for v in elbow_world_R],
        "ankle_world_L": [float(v) for v in ankle_world_L],
        "ankle_world_R": [float(v) for v in ankle_world_R],
        "foot_tail_L": [float(v) for v in foot_tail_L],
        "foot_tail_R": [float(v) for v in foot_tail_R],
        "elbow_pole_world_L": controllers["ElbowPole.L"]["world_pos"],
        "elbow_pole_world_R": controllers["ElbowPole.R"]["world_pos"],
        "bones": bones_data,
        "controllers": controllers,
        "influences": influences,
    }


def _install_showcase_observer(vr, arm_obj, root_obj):
    from src.motion.kinematic_bridge import KinematicBridgeExecutor

    solve_frames: List[Dict[str, Any]] = []
    physics_frames: List[Dict[str, Any]] = []
    wbc_frames: List[Dict[str, Any]] = []
    planned_frames: List[Dict[str, Any]] = []
    orig_ef = KinematicBridgeExecutor.execute_frame

    @functools.wraps(orig_ef)
    def wrapped(self, planned, *args, **kwargs):
        res = orig_ef(self, planned, *args, **kwargs)
        ms = res.motion_state
        p = ms.params
        wbc = res.wbc_result

        live = _capture_full_solve_sample(vr, arm_obj, root_obj, planned.frame)
        solve_frames.append(live)

        prev_vel = getattr(getattr(self, "kinematics_tracker", None), "_prev_velocity", None)
        com_acc = (
            [float(v) for v in prev_vel.com_linear_acceleration]
            if (prev_vel is not None and hasattr(prev_vel, "com_linear_acceleration"))
            else [0.0, 0.0, 0.0]
        )

        physics_frames.append({
            "frame": int(planned.frame),
            "time_sec": float(ms.time_sec),
            "mode": str(ms.mode.value),
            "gait_phase": str(ms.gait_phase),
            "is_airborne": bool(ms.is_airborne),
            "support_type": str(res.support_type),
            "supporting_limbs": list(p.get("supporting_limbs", ())),
            "active_contact_count": int(p.get("active_contact_count", 0)),
            "com_world": [float(v) for v in res.com_world],
            "planned_linear_velocity": [float(v) for v in ms.velocity],
            "planned_linear_acceleration": [float(v) for v in ms.acceleration],
            "com_linear_velocity": [float(v) for v in p.get("com_linear_velocity", (0.0, 0.0, 0.0))],
            "com_linear_acceleration": com_acc,
            "root_derived_linear_velocity": [float(v) for v in p.get("root_derived_linear_velocity", (0.0, 0.0, 0.0))],
            "angular_momentum_com": [float(v) for v in p.get("angular_momentum_com", (0.0, 0.0, 0.0))],
            "angular_momentum_magnitude": float(p.get("angular_momentum_magnitude", 0.0)),
            "foot_L_locked": bool(planned.foot_L.is_locked) if planned.foot_L else None,
            "foot_R_locked": bool(planned.foot_R.is_locked) if planned.foot_R else None,
            "foot_L_planned": [float(v) for v in planned.foot_L.world_xyz] if planned.foot_L else None,
            "foot_R_planned": [float(v) for v in planned.foot_R.world_xyz] if planned.foot_R else None,
            "foot_L_drift_m": float(ms.contacts["foot_l"].drift_m) if "foot_l" in ms.contacts else 0.0,
            "foot_R_drift_m": float(ms.contacts["foot_r"].drift_m) if "foot_r" in ms.contacts else 0.0,
            "pelvis_location": [float(v) for v in planned.pelvis_location],
            "pelvis_rotation_deg": [float(v) for v in planned.pelvis_rotation_deg],
            "spine_rotation_deg": [float(v) for v in planned.spine_rotation_deg],
        })

        planned_frames.append({
            "frame": int(planned.frame),
            "hand_L_enabled": bool(planned.hand_L and planned.hand_L.enabled),
            "hand_R_enabled": bool(planned.hand_R and planned.hand_R.enabled),
            "hand_L_world_xyz": [float(v) for v in planned.hand_L.world_xyz] if planned.hand_L else None,
            "hand_R_world_xyz": [float(v) for v in planned.hand_R.world_xyz] if planned.hand_R else None,
        })

        wbc_frames.append({
            "frame": int(planned.frame),
            "success": bool(res.success and wbc.success),
            "has_rom_violation": bool(wbc.has_rom_violation),
            "is_all_reachable": bool(wbc.is_all_reachable),
            "max_end_effector_error_m": float(wbc.max_end_effector_error_m),
            "tracking_errors_m": {k: float(v) for k, v in res.tracking_errors.items()},
            "unmet_constraints": [
                {"category": uc.category, "target_name": uc.target_name, "error_amount": float(uc.error_amount)}
                for uc in wbc.unmet_constraints
            ],
        })
        return res

    KinematicBridgeExecutor.execute_frame = wrapped
    return orig_ef, KinematicBridgeExecutor, solve_frames, physics_frames, wbc_frames, planned_frames


# =============================================================================
# BOUNDARY & TELEMETRY ANALYSIS HELPERS
# =============================================================================

def _vec_dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def _compute_action_boundary(
    vr,
    name: str,
    prev_sf: Dict[str, Any],
    next_sf: Dict[str, Any],
    prev_ph: Dict[str, Any],
    next_ph: Dict[str, Any],
) -> Dict[str, Any]:
    from mathutils import Quaternion

    max_rel_deg = 0.0
    max_rel_bone = ""
    max_world_deg = 0.0
    max_world_bone = ""
    per_bone = {}
    for bname in ALL_VERIFIED_BONES:
        rel_d = math.degrees(vr._quat_angle_rad(Quaternion(prev_sf["bones"][bname]["rel_parent_quat"]), Quaternion(next_sf["bones"][bname]["rel_parent_quat"])))
        w_d = math.degrees(vr._quat_angle_rad(Quaternion(prev_sf["bones"][bname]["world_quat"]), Quaternion(next_sf["bones"][bname]["world_quat"])))
        per_bone[bname] = {"rel_deg": rel_d, "world_deg": w_d}
        if rel_d > max_rel_deg:
            max_rel_deg = rel_d
            max_rel_bone = bname
        if w_d > max_world_deg:
            max_world_deg = w_d
            max_world_bone = bname

    upper_rel_deg = max(per_bone[b]["rel_deg"] for b in vr.UPPER_LIMB_BONES)
    foot_l_head_delta = _vec_dist(prev_sf["bones"]["foot.L"]["world_head"], next_sf["bones"]["foot.L"]["world_head"])
    foot_r_head_delta = _vec_dist(prev_sf["bones"]["foot.R"]["world_head"], next_sf["bones"]["foot.R"]["world_head"])
    wrist_l_local_delta = _vec_dist(prev_sf["wrist_root_local_L"], next_sf["wrist_root_local_L"])
    wrist_r_local_delta = _vec_dist(prev_sf["wrist_root_local_R"], next_sf["wrist_root_local_R"])

    return {
        "boundary": name,
        "prev_frame": int(prev_sf["frame"]),
        "next_frame": int(next_sf["frame"]),
        "prev_mode": prev_ph["mode"],
        "next_mode": next_ph["mode"],
        "root_pos_delta_m": _vec_dist(prev_sf["root_world_pos"], next_sf["root_world_pos"]),
        "com_delta_m": _vec_dist(prev_ph["com_world"], next_ph["com_world"]),
        "pelvis_location_delta_m": _vec_dist(prev_ph["pelvis_location"], next_ph["pelvis_location"]),
        "planned_vel_prev_mps": prev_ph["planned_linear_velocity"],
        "planned_vel_next_mps": next_ph["planned_linear_velocity"],
        "com_vel_prev_mps": prev_ph["com_linear_velocity"],
        "com_vel_next_mps": next_ph["com_linear_velocity"],
        "foot_L_head_delta_m": foot_l_head_delta,
        "foot_R_head_delta_m": foot_r_head_delta,
        "wrist_root_local_delta_L_m": wrist_l_local_delta,
        "wrist_root_local_delta_R_m": wrist_r_local_delta,
        "max_upper_limb_rel_rot_deg": upper_rel_deg,
        "max_full_body_rel_rot_deg": max_rel_deg,
        "max_full_body_rel_rot_bone": max_rel_bone,
        "max_full_body_world_rot_deg": max_world_deg,
        "max_full_body_world_rot_bone": max_world_bone,
        "influence_deltas": {
            cname: abs(next_sf["influences"][cname] - prev_sf["influences"][cname])
            for cname, _, _ in vr.UPPER_CONSTRAINTS
        },
        "per_bone_deg": per_bone,
    }


def _summarize_stage_physics(stage_label: str, action_name: str, solve_slice: List[Dict[str, Any]], phys_slice: List[Dict[str, Any]], wbc_slice: List[Dict[str, Any]], vr) -> Dict[str, Any]:
    start_pos = solve_slice[0]["root_world_pos"]
    end_pos = solve_slice[-1]["root_world_pos"]
    com_zs = [p["com_world"][2] for p in phys_slice]
    com_speeds = [math.sqrt(sum(c * c for c in p["com_linear_velocity"])) for p in phys_slice]
    com_accs = [math.sqrt(sum(c * c for c in p["com_linear_acceleration"])) for p in phys_slice]
    ang_mags = [p["angular_momentum_magnitude"] for p in phys_slice]
    airborne_frames = [p["frame"] for p in phys_slice if p["is_airborne"]]
    support_counts: Dict[str, int] = {}
    for p in phys_slice:
        st = p["support_type"]
        support_counts[st] = support_counts.get(st, 0) + 1

    max_ee_err = max(w["max_end_effector_error_m"] for w in wbc_slice)
    rom_viol_count = sum(1 for w in wbc_slice if w["has_rom_violation"])
    unreachable_count = sum(1 for w in wbc_slice if not w["is_all_reachable"])
    l_metrics = vr._compute_side_motion_metrics(solve_slice, "L")
    r_metrics = vr._compute_side_motion_metrics(solve_slice, "R")

    return {
        "stage": stage_label,
        "action_name": action_name,
        "frame_start": int(solve_slice[0]["frame"]),
        "frame_end": int(solve_slice[-1]["frame"]),
        "frame_count": len(solve_slice),
        "duration_sec": round(len(solve_slice) / 24.0, 6),
        "start_root_pos": start_pos,
        "end_root_pos": end_pos,
        "root_displacement_y_m": float(end_pos[1] - start_pos[1]),
        "com_z_min_m": min(com_zs),
        "com_z_max_m": max(com_zs),
        "com_speed_min_mps": min(com_speeds),
        "com_speed_max_mps": max(com_speeds),
        "com_accel_max_mps2": max(com_accs),
        "angular_momentum_max": max(ang_mags),
        "support_type_counts": support_counts,
        "airborne_frame_count": len(airborne_frames),
        "airborne_frames": airborne_frames,
        "max_end_effector_error_m": max_ee_err,
        "rom_violation_frames": rom_viol_count,
        "unreachable_frames": unreachable_count,
        "upper_limb_metrics_L": l_metrics,
        "upper_limb_metrics_R": r_metrics,
    }


# =============================================================================
# GENERATION & VERIFICATION WORKERS
# =============================================================================

def _worker_generate(blend_out: str, dump_json: str) -> None:
    import bpy
    _setup_sys_path()
    vr = _load_module("vr_mod", REDELIVERY_SCRIPT)
    ev = _load_module("ev_mod", EXTENDED_SCRIPT)

    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
    from src.motion.framework import MotionPlanner, StartStopWalkAction, create_initial_motion_state
    from src.motion.sprint_start import SprintStartAction
    from src.motion.sprint_brake import SprintBrakeAction
    from src.motion.run_cycle import RunAction

    start_pos = (0.0, -12.0, 0.0)
    # Stage A & C geometric routes for initial terminal-position pre-probe
    stage_a_route_probe = TerrainRouteInput(start_pos=start_pos, target_pos=start_pos, stand_start_frames=240, stand_stop_frames=0)
    stage_c_route_probe = TerrainRouteInput(
        start_pos=(0.0, -10.74, 0.0),
        target_pos=(0.0, -4.74, 0.0),
        nominal_stride_m=0.30,
        step_frames=18,
        stand_start_frames=24,
        stand_stop_frames=24,
    )
    pre_ends = _probe_chain_terminal_positions(vr, ev, stage_a_route_probe, stage_c_route_probe)
    stage_b_end = tuple(pre_ends["StageB_end"])
    stage_e_end = tuple(pre_ends["StageE_end"])

    # Build verified per-stage upper-limb schedules via real pipeline pre-probes
    route_a, segs_a_l, segs_a_r, switches_a = _build_stage_a_config(vr, ev, start_pos)
    route_c, segs_c_l, segs_c_r, switches_c = _build_stage_c_config(vr, ev, stage_b_end)
    route_f, segs_f_l, segs_f_r, switches_f = _build_stage_f_config(vr, ev, stage_e_end)

    # Assemble single final flat production scene and execute ALL 7 actions in ONE MotionPlanner.execute()
    cfg, scene, root_obj, arm_obj, hand_l, hand_r, env = _assemble_flat_showcase_scene(vr, ev, with_decor=True)
    orig_ef, kb_cls, solve_frames, physics_frames, wbc_frames, planned_frames = _install_showcase_observer(vr, arm_obj, root_obj)

    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route_a, environment=env, action_name="StageA_StandingUpperLimb", upper_limb_L=segs_a_l, upper_limb_R=segs_a_r))
        planner.add_action(StartStopWalkAction())
        planner.add_action(TerrainWalkAction(route=route_c, environment=env, action_name="StageC_WalkUpperLimb", upper_limb_L=segs_c_l, upper_limb_R=segs_c_r))
        planner.add_action(SprintStartAction())
        planner.add_action(SprintBrakeAction())
        planner.add_action(TerrainWalkAction(route=route_f, environment=env, action_name="StageF_PostStopUpperLimb", upper_limb_L=segs_f_l, upper_limb_R=segs_f_r))
        planner.add_action(RunAction(cycles=8))

        plan_res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=start_pos))
    finally:
        kb_cls.execute_frame = orig_ef

    total_frames = int(plan_res["total_frames"])
    assert len(solve_frames) == total_frames
    assert int(plan_res["unreachable_count"]) == 0, f"Unexpected unreachable_count={plan_res['unreachable_count']}"
    assert all(w["success"] for w in wbc_frames), "At least one frame failed WBC/Bridge!"

    solve_by_f = {sf["frame"]: sf for sf in solve_frames}
    phys_by_f = {pf["frame"]: pf for pf in physics_frames}
    wbc_by_f = {wf["frame"]: wf for wf in wbc_frames}

    # Gather exact action frame spans & summary
    stage_specs = []
    stage_codes = ["StageA", "StageB", "StageC", "StageD", "StageE", "StageF", "StageG"]
    for scode, ar in zip(stage_codes, plan_res["action_results"]):
        f0 = ar.states[0].frame
        f1 = ar.states[-1].frame
        s_slice = [solve_by_f[f] for f in range(f0, f1 + 1)]
        p_slice = [phys_by_f[f] for f in range(f0, f1 + 1)]
        w_slice = [wbc_by_f[f] for f in range(f0, f1 + 1)]
        stage_specs.append(_summarize_stage_physics(scode, ar.action_name, s_slice, p_slice, w_slice, vr))

    # Action boundaries (6 transitions)
    action_boundaries = []
    for i in range(len(stage_specs) - 1):
        prev_st = stage_specs[i]
        next_st = stage_specs[i + 1]
        pf = prev_st["frame_end"]
        nf = next_st["frame_start"]
        b_label = f"{prev_st['stage']}->{next_st['stage']}"
        action_boundaries.append(
            _compute_action_boundary(vr, b_label, solve_by_f[pf], solve_by_f[nf], phys_by_f[pf], phys_by_f[nf])
        )

    # Upper-limb FK <-> IK switch continuity checks inside Stages A, C, F
    upper_switch_checks = []
    for st_code, f_start, sw_dict in (
        ("StageA", stage_specs[0]["frame_start"], switches_a),
        ("StageC", stage_specs[2]["frame_start"], switches_c),
        ("StageF", stage_specs[5]["frame_start"], switches_f),
    ):
        for side, sw_list in sw_dict.items():
            for sw in sw_list:
                gf_prev = f_start + sw["local_before"] - 1
                gf_next = f_start + sw["local_after"] - 1
                ev_res = ev._evaluate_switch_boundary(solve_by_f, vr, side, {
                    "type": sw["type"],
                    "before_frame": gf_prev,
                    "after_frame": gf_next,
                })
                ev_res["stage"] = st_code
                ev_res["side"] = side
                upper_switch_checks.append(ev_res)

    # Stage timeline markers & open state = Frame 1
    markers = [(f"{st['stage']}_{st['action_name']}", st["frame_start"]) for st in stage_specs]
    markers.append(("Showcase_End", total_frames))
    ev._add_timeline_markers(scene, markers)

    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.render.fps = cfg.fps
    scene.frame_set(1)
    bpy.context.view_layer.update()

    os.makedirs(os.path.dirname(blend_out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend_out)
    b1 = blend_out + "1"
    if os.path.exists(b1):
        os.remove(b1)

    # Bilateral upper-limb checks on A, C, F
    for idx in (0, 2, 5):
        st = stage_specs[idx]
        for s_key in ("upper_limb_metrics_L", "upper_limb_metrics_R"):
            m = st[s_key]
            assert m["upper_arm_rel_span_deg"] >= 20.0, f"{st['stage']} {s_key} upper_arm span {m['upper_arm_rel_span_deg']}"
            assert m["forearm_rel_span_deg"] >= 20.0, f"{st['stage']} {s_key} forearm span {m['forearm_rel_span_deg']}"
            assert m["hand_rel_span_deg"] >= 15.0, f"{st['stage']} {s_key} hand span {m['hand_rel_span_deg']}"
            assert m["wrist_root_local_span_m"] >= 0.15, f"{st['stage']} {s_key} wrist local span {m['wrist_root_local_span_m']}"

    # Stage G Run checks
    stage_g = stage_specs[6]
    assert stage_g["frame_count"] == 192
    assert stage_g["airborne_frame_count"] == 80, f"Expected 80 flight frames for 8 run cycles, got {stage_g['airborne_frame_count']}"

    # Effective segments count
    eff_a_l, _ = ev._count_effective_segments(segs_a_l)
    eff_a_r, _ = ev._count_effective_segments(segs_a_r)
    eff_c_l, _ = ev._count_effective_segments(segs_c_l)
    eff_c_r, _ = ev._count_effective_segments(segs_c_r)
    eff_f_l, _ = ev._count_effective_segments(segs_f_l)
    eff_f_r, _ = ev._count_effective_segments(segs_f_r)

    payload = {
        "blend_path": blend_out,
        "blender_version": bpy.app.version_string,
        "fps": cfg.fps,
        "frame_start": 1,
        "frame_end": total_frames,
        "total_frames": total_frames,
        "total_duration_sec": round(total_frames / float(cfg.fps), 6),
        "total_root_displacement_m": float(plan_res["total_root_displacement"]),
        "unreachable_count": int(plan_res["unreachable_count"]),
        "run_action_note": "RunAction in Stage G executes historical lower-limb sprint/run cycle + historical FK arm swing; RunAction does NOT support UpperLimbSegment independent control yet.",
        "upper_limb_segment_counts": {
            "StageA": {"L": eff_a_l, "R": eff_a_r},
            "StageC": {"L": eff_c_l, "R": eff_c_r},
            "StageF": {"L": eff_f_l, "R": eff_f_r},
        },
        "stage_summaries": stage_specs,
        "action_boundaries": action_boundaries,
        "upper_limb_switch_boundaries": upper_switch_checks,
        "markers": [{"name": n, "frame": f} for n, f in markers],
        "solve_frames": solve_frames,
        "physics_frames": physics_frames,
        "wbc_frames": wbc_frames,
        "planned_frames": planned_frames,
    }
    os.makedirs(os.path.dirname(dump_json), exist_ok=True)
    with open(dump_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)


def _worker_reopen(blend_path: str, dump_json: str, out_json: str) -> None:
    import bpy
    from mathutils import Quaternion, Vector
    _setup_sys_path()
    vr = _load_module("vr_mod", REDELIVERY_SCRIPT)

    with open(dump_json, "r", encoding="utf-8") as fp:
        solve_data = json.load(fp)
    solve_by_f = {sf["frame"]: sf for sf in solve_data["solve_frames"]}
    frame_start = int(solve_data["frame_start"])
    frame_end = int(solve_data["frame_end"])

    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.context.scene
    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    hand_l = bpy.data.objects.get("Hand_L")
    hand_r = bpy.data.objects.get("Hand_R")

    assert arm_obj is not None and root_obj is not None
    assert len(arm_obj.data.bones) == 19
    assert int(scene.frame_start) == frame_start and int(scene.frame_end) == frame_end
    open_state_snapshot = {
        "frame_current": int(scene.frame_current),
        "frame_start": int(scene.frame_start),
        "frame_end": int(scene.frame_end),
        "fps": int(scene.render.fps),
        "active_camera": scene.camera.name if scene.camera is not None else None,
        "markers": [{"name": m.name, "frame": int(m.frame)} for m in scene.timeline_markers],
    }
    assert open_state_snapshot["frame_current"] == 1, f"Expected frame_current==1 on open, got {open_state_snapshot['frame_current']}"
    assert open_state_snapshot["fps"] == 24
    assert scene.camera is not None and scene.camera.name == "Visual_ObliqueSideCam"
    assert bpy.data.objects.get("Visual_FrontCam") is not None
    assert hand_l is not None and hand_l.parent == arm_obj and hand_l.parent_bone == "hand.L" and hand_l.animation_data is None
    assert hand_r is not None and hand_r.parent == arm_obj and hand_r.parent_bone == "hand.R" and hand_r.animation_data is None

    slot_id, fcurves = vr._get_slot_fcurves(arm_obj)
    assert slot_id is not None
    fc_by_path = {fc.data_path: fc for fc in fcurves}
    expected_set = set(range(frame_start, frame_end + 1))
    inf_fcurve_summary = {}
    for cname, _, dp in vr.UPPER_CONSTRAINTS:
        fc = fc_by_path.get(dp)
        assert fc is not None, f"Missing FCurve {dp}"
        kp_frames = {int(round(kp.co[0])) for kp in fc.keyframe_points}
        kp_interps = sorted({str(kp.interpolation) for kp in fc.keyframe_points})
        assert kp_frames == expected_set
        assert kp_interps == ["CONSTANT"]
        inf_fcurve_summary[cname] = {"keyframe_count": len(fc.keyframe_points), "interpolations": kp_interps}

    base_frames = list(range(frame_start, frame_end + 1))
    orders = [
        ("forward", list(base_frames)),
        ("reverse", list(reversed(base_frames))),
        ("shuffled_seed_20261127", random.Random(20261127).sample(base_frames, len(base_frames))),
    ]
    pos_tol = 1e-5
    rot_tol = 1e-4
    inf_tol = 1e-6

    traversal_reports = []
    for order_name, fseq in orders:
        max_pos_err = 0.0
        max_rot_err = 0.0
        max_inf_err = 0.0
        failures = []
        for f in fseq:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            exp = solve_by_f[f]
            arm_mat = arm_obj.matrix_world.copy()
            root_mat = root_obj.matrix_world.copy()

            checks_pos = (
                ("root_world_pos", root_mat.translation, exp["root_world_pos"]),
                ("wrist_world_L", arm_mat @ arm_obj.pose.bones["forearm.L"].tail, exp["wrist_world_L"]),
                ("wrist_world_R", arm_mat @ arm_obj.pose.bones["forearm.R"].tail, exp["wrist_world_R"]),
                ("elbow_world_L", arm_mat @ arm_obj.pose.bones["upper_arm.L"].tail, exp["elbow_world_L"]),
                ("elbow_world_R", arm_mat @ arm_obj.pose.bones["upper_arm.R"].tail, exp["elbow_world_R"]),
                ("ankle_world_L", arm_mat @ arm_obj.pose.bones["shin.L"].tail, exp["ankle_world_L"]),
                ("ankle_world_R", arm_mat @ arm_obj.pose.bones["shin.R"].tail, exp["ankle_world_R"]),
                ("elbow_pole_world_L", bpy.data.objects["ElbowPole.L"].matrix_world.translation, exp["elbow_pole_world_L"]),
                ("elbow_pole_world_R", bpy.data.objects["ElbowPole.R"].matrix_world.translation, exp["elbow_pole_world_R"]),
            )
            for lbl, a_vec, e_xyz in checks_pos:
                perr = (a_vec - Vector(e_xyz)).length
                max_pos_err = max(max_pos_err, perr)
                if perr > pos_tol:
                    failures.append({"frame": f, "metric": lbl, "error": perr})

            rq_err = vr._quat_angle_rad(root_mat.to_3x3().normalized().to_quaternion(), Quaternion(exp["root_world_quat"]))
            max_rot_err = max(max_rot_err, rq_err)
            if rq_err > rot_tol:
                failures.append({"frame": f, "metric": "root_world_quat", "error": rq_err})

            for bname in ALL_VERIFIED_BONES:
                pb = arm_obj.pose.bones[bname]
                wq = (arm_mat @ pb.matrix).to_3x3().normalized().to_quaternion()
                rerr = vr._quat_angle_rad(wq, Quaternion(exp["bones"][bname]["world_quat"]))
                max_rot_err = max(max_rot_err, rerr)
                if rerr > rot_tol:
                    failures.append({"frame": f, "metric": f"bone_world:{bname}", "error": rerr})
                rel_q, _ = vr._relative_joint_quat_and_euler(arm_obj, bname)
                rel_err = vr._quat_angle_rad(rel_q, Quaternion(exp["bones"][bname]["rel_parent_quat"]))
                max_rot_err = max(max_rot_err, rel_err)
                if rel_err > rot_tol:
                    failures.append({"frame": f, "metric": f"bone_rel:{bname}", "error": rel_err})

            for cname in vr.UPPER_CONTROLLERS:
                cobj = bpy.data.objects[cname]
                cm = cobj.matrix_world
                c_pe = (cm.translation - Vector(exp["controllers"][cname]["world_pos"])).length
                c_re = vr._quat_angle_rad(cm.to_3x3().normalized().to_quaternion(), Quaternion(exp["controllers"][cname]["world_quat"]))
                max_pos_err = max(max_pos_err, c_pe)
                max_rot_err = max(max_rot_err, c_re)
                if c_pe > pos_tol or c_re > rot_tol:
                    failures.append({"frame": f, "metric": f"ctrl:{cname}", "pos_err": c_pe, "rot_err": c_re})

            for cname, bname, _ in vr.UPPER_CONSTRAINTS:
                inf = float(arm_obj.pose.bones[bname].constraints[cname].influence)
                ie = abs(inf - float(exp["influences"][cname]))
                max_inf_err = max(max_inf_err, ie)
                if ie > inf_tol:
                    failures.append({"frame": f, "metric": f"inf:{cname}", "error": ie})

        assert not failures, f"Reopen failures in {order_name}: {failures[:5]}"
        traversal_reports.append({
            "order": order_name,
            "frames_checked": len(fseq),
            "max_pos_err_m": max_pos_err,
            "max_rot_err_rad": max_rot_err,
            "max_inf_err": max_inf_err,
            "failure_count": 0,
        })

    result = {
        "blend_path": blend_path,
        "blend_sha256": _sha256_file(blend_path),
        "blend_size_bytes": os.path.getsize(blend_path),
        "bone_count": len(arm_obj.data.bones),
        "action_slot_identifier": slot_id,
        "influence_fcurve_summary": inf_fcurve_summary,
        "open_state": open_state_snapshot,
        "reopen_traversal_reports": traversal_reports,
    }
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

def _run_blender_worker(args_list: List[str]) -> Tuple[int, str, str]:
    cmd = [BLENDER_EXE, "--background", "--python-exit-code", "1", "--python", THIS_FILE, "--"] + args_list
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=600, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    if "--worker" in sys.argv:
        widx = sys.argv.index("--worker")
        mode = sys.argv[widx + 1]
        if mode == "generate":
            _worker_generate(sys.argv[widx + 2], sys.argv[widx + 3])
            return 0
        elif mode == "reopen":
            _worker_reopen(sys.argv[widx + 2], sys.argv[widx + 3], sys.argv[widx + 4])
            return 0
        else:
            raise ValueError(f"Unknown worker mode: {mode}")

    os.makedirs(SHOWCASE_DIR, exist_ok=True)
    os.makedirs(SCRATCH_WORK, exist_ok=True)

    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    assert git_head == EXPECTED_HEAD, f"HEAD mismatch: {git_head} != {EXPECTED_HEAD}"
    blob_hashes = {}
    for rel, expected_blob in FROZEN_SOURCE_BLOBS.items():
        actual_blob = subprocess.check_output(["git", "rev-parse", f"HEAD:{rel}"], cwd=REPO_ROOT, text=True).strip()
        assert actual_blob == expected_blob, f"Blob mismatch for {rel}: {actual_blob} != {expected_blob}"
        blob_hashes[rel] = actual_blob

    solve_dump = os.path.join(SCRATCH_WORK, "unified_solve.json")
    reopen_dump = os.path.join(SCRATCH_WORK, "unified_reopen.json")

    rc_gen, out_gen, err_gen = _run_blender_worker(["--worker", "generate", DELIVERABLE_BLEND, solve_dump])
    rc_re, out_re, err_re = (0, "", "")
    if rc_gen == 0:
        rc_re, out_re, err_re = _run_blender_worker(["--worker", "reopen", DELIVERABLE_BLEND, solve_dump, reopen_dump])

    with open(os.path.join(SHOWCASE_DIR, "stdout.log"), "w", encoding="utf-8") as fp:
        fp.write("=== GENERATE STDOUT ===\n" + out_gen + "\n=== REOPEN STDOUT ===\n" + out_re)
    with open(os.path.join(SHOWCASE_DIR, "stderr.log"), "w", encoding="utf-8") as fp:
        fp.write("=== GENERATE STDERR ===\n" + err_gen + "\n=== REOPEN STDERR ===\n" + err_re)

    if rc_gen != 0 or rc_re != 0:
        raise RuntimeError(f"Showcase worker failed: rc_gen={rc_gen}, rc_re={rc_re}\nSTDERR_GEN:\n{err_gen[-1500:]}\nSTDERR_RE:\n{err_re[-1500:]}")

    with open(solve_dump, "r", encoding="utf-8") as fp:
        solve_data = json.load(fp)
    with open(reopen_dump, "r", encoding="utf-8") as fp:
        reopen_data = json.load(fp)

    motion_report = {
        "task": "10-d-5",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_head": git_head,
        "frozen_source_blobs": blob_hashes,
        "environment": "EnvironmentQuery(ground_z=0.0)",
        "blend_path": solve_data["blend_path"],
        "blender_version": solve_data["blender_version"],
        "fps": solve_data["fps"],
        "frame_start": solve_data["frame_start"],
        "frame_end": solve_data["frame_end"],
        "total_frames": solve_data["total_frames"],
        "total_duration_sec": solve_data["total_duration_sec"],
        "total_root_displacement_m": solve_data["total_root_displacement_m"],
        "unreachable_count": solve_data["unreachable_count"],
        "run_action_note": solve_data["run_action_note"],
        "upper_limb_segment_counts": solve_data["upper_limb_segment_counts"],
        "stage_summaries": solve_data["stage_summaries"],
        "markers": solve_data["markers"],
    }
    boundary_report = {
        "task": "10-d-5",
        "git_head": git_head,
        "action_boundaries": solve_data["action_boundaries"],
        "upper_limb_switch_boundaries": solve_data["upper_limb_switch_boundaries"],
    }
    physics_telemetry = {
        "task": "10-d-5",
        "git_head": git_head,
        "note": "Real solve-time kinematics/inertia/contact telemetry recorded during MotionPlanner.execute(); not claimed as closed-loop rigid-body simulation.",
        "stage_summaries": [
            {
                k: st[k]
                for k in (
                    "stage", "action_name", "frame_start", "frame_end",
                    "com_z_min_m", "com_z_max_m", "com_speed_min_mps", "com_speed_max_mps",
                    "com_accel_max_mps2", "angular_momentum_max", "support_type_counts",
                    "airborne_frame_count", "max_end_effector_error_m", "rom_violation_frames",
                )
            }
            for st in solve_data["stage_summaries"]
        ],
        "per_frame_telemetry": solve_data["physics_frames"],
    }
    blend_artifacts = {
        "task": "10-d-5",
        "git_head": git_head,
        "deliverable": reopen_data,
        "visual_verification_ready": True,
        "passed_all_reopen_orders": True,
    }
    solve_time_poses = {
        "task": "10-d-5",
        "git_head": git_head,
        "total_frames": solve_data["total_frames"],
        "solve_frames": solve_data["solve_frames"],
        "wbc_frames": solve_data["wbc_frames"],
    }

    for fname, obj in (
        ("motion_report.json", motion_report),
        ("boundary_report.json", boundary_report),
        ("physics_telemetry.json", physics_telemetry),
        ("blend_artifacts.json", blend_artifacts),
        ("solve_time_poses.json", solve_time_poses),
    ):
        with open(os.path.join(SHOWCASE_DIR, fname), "w", encoding="utf-8") as fp:
            json.dump(obj, fp, indent=2)

    print(f"SHOWCASE OK: total_frames={motion_report['total_frames']} ({motion_report['total_duration_sec']}s), displacement={motion_report['total_root_displacement_m']:.5f}m, unreachable={motion_report['unreachable_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
