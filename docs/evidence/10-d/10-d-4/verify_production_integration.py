"""TASK 10-d-4 — Blender 5.1.1 Production Integration Verification Suite.

Orchestrator + isolated Blender 5.1.1 worker harness executing T01..T18 against
the real production stack:
  build_character() -> build_rig() -> bind_character_to_rig() ->
  MotionPlanner -> TerrainWalkAction -> KinematicBridgeExecutor ->
  WholeBodyController -> Rig FK/IK -> EnvironmentQuery / DynamicsEnvironmentQuery

Run via Blender's bundled Python (no args) as orchestrator:
  "C:/Program Files/Blender Foundation/Blender 5.1/5.1/python/bin/python.exe" -B \
      docs/evidence/10-d/10-d-4/verify_production_integration.py

Each test scene is isolated in its own fresh Blender 5.1.1 subprocess
(--factory-startup --python-exit-code 1), except T12 which deliberately tests
repeated generation on the same scene/character inside one Blender process.
T11 reopens each saved .blend asset in a separate isolated Blender process via
docs/evidence/10-d/10-d-4/verify_saved_scene.py.
"""

from __future__ import annotations

import copy
import datetime
import functools
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
BLENDER_PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
THIS_FILE = os.path.abspath(__file__)
EVIDENCE_DIR = os.path.dirname(THIS_FILE)
REPO_ROOT = os.path.abspath(os.path.join(EVIDENCE_DIR, "..", "..", "..", ".."))
VERIFY_SAVED_SCRIPT = os.path.join(EVIDENCE_DIR, "verify_saved_scene.py")
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

SCRATCH_ROOT = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch"
)
BASELINE_DIR = os.path.join(SCRATCH_ROOT, "baseline_5a4603d4")
WORK_DIR = os.path.join(SCRATCH_ROOT, "task10d4_work")

EXPECTED_HEAD = "9cd35faa4992bfd1cd751820495753afc9d9d0ae"
EXPECTED_BLOBS = {
    "src/motion/terrain_walk.py": "d42519fe8e39d149bdcffec3378b5f5ee7601b91",
    "src/motion/kinematic_bridge.py": "9e68e0a6a44bdb538b75b4f4d99b117c1737c358",
    "src/motion/framework.py": "31a9c268e0833a93cc0e498227202256c3274f05",
    "src/motion/whole_body_controller.py": "562de6c0ce1e9009856a7d52ec89cd6d0c012be2",
}
HISTORICAL_BASELINE_COMMIT = "5a4603d4ae62b870050113362f78f6ed8029dfec"

DELIVERABLE_BLENDS = {
    "T02_stationary_fk": os.path.join(OUTPUT_DIR, "task10d_stationary_fk.blend"),
    "T05_bilateral_ik": os.path.join(OUTPUT_DIR, "task10d_bilateral_ik.blend"),
    "T06_walking_upper_limb": os.path.join(OUTPUT_DIR, "task10d_walking_upper_limb.blend"),
    "T10_fk_ik_transition": os.path.join(OUTPUT_DIR, "task10d_fk_ik_transition.blend"),
}


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# =============================================================================
# SHARED WORKER HELPERS (executed inside Blender 5.1.1 processes)
# =============================================================================

def _setup_sys_path(code_root: str) -> None:
    norm_root = os.path.normpath(os.path.abspath(code_root))
    norm_repo = os.path.normpath(os.path.abspath(REPO_ROOT))
    # Strip repo root / script dir if isolating baseline
    cleaned: List[str] = []
    for p in sys.path:
        np = os.path.normpath(os.path.abspath(p)) if p else ""
        if np in (norm_repo, os.path.normpath(EVIDENCE_DIR)):
            continue
        cleaned.append(p)
    sys.path[:] = [norm_root] + cleaned


def _add_flat_inspection_environment(start_pos: Tuple[float, float, float]) -> None:
    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    col = bpy.data.collections.get("Scene_Inspection")
    if col is None:
        col = bpy.data.collections.new("Scene_Inspection")
        scene.collection.children.link(col)

    # Non-intrusive flat reference floor slab (top surface strictly at Z = 0.0)
    import bmesh
    mesh = bpy.data.meshes.new("FlatGround_Ref")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    floor_obj = bpy.data.objects.new("FlatGround_Ref", mesh)
    floor_obj.scale = (16.0, 20.0, 0.20)
    floor_obj.location = (0.0, start_pos[1] + 2.0, -0.10)
    col.objects.link(floor_obj)

    # Sun light
    light_data = bpy.data.lights.new("SceneSun", type="SUN")
    light_data.energy = 2.5
    light_obj = bpy.data.objects.new("SceneSun", light_data)
    light_obj.rotation_euler = (0.6, 0.2, 0.5)
    col.objects.link(light_obj)

    # Camera framed directly at the character
    cam_data = bpy.data.cameras.new("Task10D_InspectCam")
    cam_data.lens = 35.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 150.0
    cam_obj = bpy.data.objects.new("Task10D_InspectCam", cam_data)
    cam_loc = Vector((start_pos[0] + 2.35, start_pos[1] + 2.15, start_pos[2] + 1.55))
    look_at = Vector((start_pos[0], start_pos[1], start_pos[2] + 0.98))
    direction = (look_at - cam_loc).normalized()
    cam_obj.location = cam_loc
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler("XYZ")
    col.objects.link(cam_obj)
    scene.camera = cam_obj


def _build_flat_production_rig(
    start_pos: Tuple[float, float, float] = (0.0, -8.0, 0.0),
    with_inspection_env: bool = True,
):
    import bpy
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.scene.environment_query import EnvironmentQuery

    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    scene = bpy.context.scene
    scene.render.fps = cfg.fps

    parts = build_character(cfg)
    root_obj = bpy.data.objects["CharacterRoot"]
    root_obj.location = start_pos
    arm_obj = build_rig(cfg, character_root=root_obj)
    bind_character_to_rig(arm_obj, parts)
    bpy.context.view_layer.update()

    if with_inspection_env:
        _add_flat_inspection_environment(start_pos)

    env = EnvironmentQuery(ground_z=0.0)
    return cfg, scene, root_obj, arm_obj, parts, env


def _build_terrain_production_rig():
    import bpy
    from mathutils import Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.scene.environment_query import create_standard_dynamics_playground_query
    from src.scene.builder import build_dynamics_playground

    cfg = PipelineConfig()
    env = create_standard_dynamics_playground_query()
    scene, env = build_dynamics_playground(query=env)
    scene.render.fps = cfg.fps

    parts = build_character(cfg)
    root_obj = bpy.data.objects["CharacterRoot"]
    arm_obj = build_rig(cfg, character_root=root_obj)
    bind_character_to_rig(arm_obj, parts)

    col = bpy.data.collections.get("Scene_Inspection")
    if col is None:
        col = bpy.data.collections.new("Scene_Inspection")
        scene.collection.children.link(col)
    cam_data = bpy.data.cameras.new("Task10D_WalkCam")
    cam_data.lens = 32.0
    cam_data.clip_start = 0.05
    cam_data.clip_end = 200.0
    cam_obj = bpy.data.objects.new("Task10D_WalkCam", cam_data)
    cam_loc = Vector((3.30, 11.90, 2.00))
    look_at = Vector((0.0, 10.80, 1.00))
    cam_obj.location = cam_loc
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = (look_at - cam_loc).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
    col.objects.link(cam_obj)
    scene.camera = cam_obj
    bpy.context.view_layer.update()

    return cfg, scene, root_obj, arm_obj, parts, env


def _install_wbc_observer(arm_obj):
    """Non-intrusive observer wrapper around WholeBodyController.execute_frame."""
    from src.motion.whole_body_controller import WholeBodyController

    captured: List[Dict[str, Any]] = []
    orig_execute = WholeBodyController.execute_frame

    @functools.wraps(orig_execute)
    def wrapped(self, *args, **kwargs):
        res = orig_execute(self, *args, **kwargs)
        eff_snapshot = {}
        for eid, fb in res.end_effectors.items():
            eff_snapshot[eid] = {
                "enabled": bool(fb.enabled),
                "weight": float(fb.weight),
                "requested_world_xyz": [float(v) for v in fb.requested_world_xyz],
                "actual_world_xyz": [float(v) for v in fb.actual_world_xyz],
                "position_error_m": float(fb.position_error_m),
                "requested_rotation_deg": (
                    [float(v) for v in fb.requested_rotation_deg]
                    if fb.requested_rotation_deg is not None
                    else None
                ),
                "actual_rotation_deg": (
                    [float(v) for v in fb.actual_rotation_deg]
                    if fb.actual_rotation_deg is not None
                    else None
                ),
                "orientation_error_deg": (
                    float(fb.orientation_error_deg)
                    if fb.orientation_error_deg is not None
                    else None
                ),
                "is_reachable": bool(fb.is_reachable),
                "strictly_in_reach": bool(fb.strictly_in_reach),
                "reach_distance_m": float(fb.reach_distance_m),
                "max_reach_m": float(fb.max_reach_m),
            }
        captured.append({
            "success": bool(res.success),
            "max_end_effector_error_m": float(res.max_end_effector_error_m),
            "has_rom_violation": bool(res.has_rom_violation),
            "is_all_reachable": bool(res.is_all_reachable),
            "root_world_position": [float(v) for v in res.root_world_position],
            "pelvis_world_position": [float(v) for v in res.pelvis_world_position],
            "com_world": [float(v) for v in res.com_result.com_world],
            "com_total_mass_kg": float(res.com_result.total_mass_kg),
            "unmet_constraints": [
                {
                    "target_name": uc.target_name,
                    "category": uc.category,
                    "description": uc.description,
                    "error_amount": float(uc.error_amount),
                }
                for uc in res.unmet_constraints
            ],
            "end_effectors": eff_snapshot,
        })
        return res

    WholeBodyController.execute_frame = wrapped
    return orig_execute, WholeBodyController, captured


def _restore_wbc_observer(orig_execute, cls) -> None:
    cls.execute_frame = orig_execute


def _load_vss():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verify_saved_scene", VERIFY_SAVED_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _capture_evaluated_pose_for_save(
    arm_obj,
    root_obj,
    frame_start: int,
    frame_end: int,
) -> Dict[str, Any]:
    vss = _load_vss()

    frames: List[Dict[str, Any]] = []
    for f in range(frame_start, frame_end + 1):
        frames.append(vss.capture_scene_frame_sample(arm_obj, root_obj, f))
    return {
        "frame_start": int(frame_start),
        "frame_end": int(frame_end),
        "frames": frames,
    }


def _check_delivery_gate_and_save(
    arm_obj,
    root_obj,
    scene,
    frame_start: int,
    frame_end: int,
    wbc_records: List[Dict[str, Any]],
    states: List[Any],
    output_blend_path: Optional[str],
) -> Dict[str, Any]:
    """Fail-closed delivery gate checking real WBC/ROM/bones/animation before saving."""
    import bpy

    if len(states) != (frame_end - frame_start + 1):
        raise RuntimeError(f"Delivery gate rejected: expected {frame_end - frame_start + 1} states, got {len(states)}")
    if any(not rec["success"] for rec in wbc_records):
        bad = [i for i, rec in enumerate(wbc_records) if not rec["success"]]
        raise RuntimeError(f"Delivery gate rejected: WBC failure at frames {bad[:5]}")
    if any(rec["has_rom_violation"] for rec in wbc_records):
        raise RuntimeError("Delivery gate rejected: ROM violation observed in WBC records")
    if len(arm_obj.data.bones) != 19:
        raise RuntimeError(f"Delivery gate rejected: expected 19 bones, got {len(arm_obj.data.bones)}")
    if arm_obj.animation_data is None or arm_obj.animation_data.action is None:
        raise RuntimeError("Delivery gate rejected: missing CharacterArmature animation_data/action")
    if scene.camera is None:
        raise RuntimeError("Delivery gate rejected: missing active inspection camera")

    scene.frame_start = int(frame_start)
    scene.frame_end = int(frame_end)
    measurements = _capture_evaluated_pose_for_save(arm_obj, root_obj, frame_start, frame_end)

    if output_blend_path is not None:
        abs_out = os.path.abspath(output_blend_path)
        os.makedirs(os.path.dirname(abs_out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=abs_out)

    return measurements


def _quat_angle_deg(q1, q2) -> float:
    a = [float(q1.w), float(q1.x), float(q1.y), float(q1.z)]
    b = [float(q2.w), float(q2.x), float(q2.y), float(q2.z)]
    na = math.sqrt(sum(c * c for c in a))
    nb = math.sqrt(sum(c * c for c in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    a = [c / na for c in a]
    b = [c / nb for c in b]
    if sum(x * y for x, y in zip(a, b)) < 0.0:
        b = [-c for c in b]
    diff_norm = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    sum_norm = math.sqrt(sum((x + y) ** 2 for x, y in zip(a, b)))
    return math.degrees(2.0 * math.atan2(diff_norm, sum_norm))


def _mat4_to_lists(m) -> List[List[float]]:
    return [[float(m[r][c]) for c in range(4)] for r in range(4)]


def _extract_upper_fk_deg(arm_obj, side: str) -> Tuple[Tuple[float, float, float], ...]:
    out = []
    for bprefix in ("upper_arm", "forearm", "hand"):
        pb = arm_obj.pose.bones[f"{bprefix}.{side}"]
        e = pb.matrix_basis.to_euler("XYZ")
        out.append((math.degrees(e.x), math.degrees(e.y), math.degrees(e.z)))
    return tuple(out)


def _extract_hand_world_euler_deg(arm_obj, side: str) -> Tuple[float, float, float]:
    pb = arm_obj.pose.bones[f"hand.{side}"]
    w_mat = arm_obj.matrix_world @ pb.matrix
    e = w_mat.to_3x3().normalized().to_euler("XYZ")
    return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))


def _eval_leg_and_arm_bones(arm_obj) -> Dict[str, Any]:
    names = (
        "pelvis",
        "spine",
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
    out: Dict[str, Any] = {}
    arm_w = arm_obj.matrix_world
    for bname in names:
        pb = arm_obj.pose.bones[bname]
        w_mat = arm_w @ pb.matrix
        e = pb.matrix_basis.to_euler("XYZ")
        out[bname] = {
            "world_matrix": _mat4_to_lists(w_mat),
            "basis_euler_deg": [math.degrees(e.x), math.degrees(e.y), math.degrees(e.z)],
            "world_head": [float(v) for v in (arm_w @ pb.head)],
            "world_tail": [float(v) for v in (arm_w @ pb.tail)],
        }
    return out


def _compare_bone_dicts(b1: Dict[str, Any], b2: Dict[str, Any], bone_names: Tuple[str, ...]) -> float:
    max_diff = 0.0
    for bname in bone_names:
        m1 = b1[bname]["world_matrix"]
        m2 = b2[bname]["world_matrix"]
        for r in range(4):
            for c in range(4):
                max_diff = max(max_diff, abs(float(m1[r][c]) - float(m2[r][c])))
    return max_diff


# =============================================================================
# INDIVIDUAL BLENDER WORKER IMPLEMENTATIONS
# =============================================================================

def _worker_T01_run(mode: str, out_json: str) -> None:
    import bpy
    import importlib

    code_root = BASELINE_DIR if mode == "baseline" else REPO_ROOT
    _setup_sys_path(code_root)

    import src.motion.terrain_walk as tw
    import src.motion.kinematic_bridge as kb
    import src.motion.framework as fw
    import src.motion.whole_body_controller as wbc

    for mod in (tw, kb, fw, wbc):
        mod_path = os.path.normpath(os.path.abspath(mod.__file__))
        expected_prefix = os.path.normpath(os.path.abspath(code_root))
        if not mod_path.startswith(expected_prefix):
            raise RuntimeError(f"Module {mod.__name__} loaded from wrong root: {mod_path} vs {expected_prefix}")

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig(
        start_pos=(0.0, -8.0, 0.0), with_inspection_env=False
    )

    route = tw.TerrainRouteInput(
        start_pos=(0.0, -8.0, 0.0),
        target_pos=(0.0, -5.6, 0.0),
        nominal_stride_m=0.30,
        step_frames=12,
        stand_start_frames=6,
        stand_stop_frames=6,
    )
    if mode == "baseline":
        action = tw.TerrainWalkAction(route=route, environment=env, action_name="T01_BaselineWalk")
    else:
        action = tw.TerrainWalkAction(
            route=route,
            environment=env,
            action_name="T01_CurrentWalk",
            upper_limb_L=None,
            upper_limb_R=None,
        )

    import dataclasses
    schedule, total_frames = tw.plan_terrain_footsteps(route, env, start_frame=1)
    sched_dump = [dataclasses.asdict(st) for st in schedule]

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = fw.MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(action)
        init_state = fw.create_initial_motion_state(cfg, start_frame=1, position=route.start_pos)
        res = planner.execute(initial_state=init_state)
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    frame_rows = []
    for idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        contacts = {}
        for k, c in sorted(st.contacts.items()):
            contacts[k] = {
                "limb": str(c.limb),
                "is_locked": bool(c.is_locked),
                "phase": str(c.phase),
                "contact_world_xyz": [float(v) for v in c.contact_world_xyz],
                "current_world_xyz": [float(v) for v in c.current_world_xyz],
                "drift_m": float(c.drift_m),
            }
        frame_rows.append({
            "frame": int(st.frame),
            "time_sec": float(st.time_sec),
            "root_state_pos": [float(v) for v in st.position],
            "root_world_pos": [float(v) for v in root_obj.matrix_world.translation],
            "root_world_matrix": _mat4_to_lists(root_obj.matrix_world),
            "contacts": contacts,
            "bones": _eval_leg_and_arm_bones(arm_obj),
        })

    payload = {
        "mode": mode,
        "code_root": code_root,
        "module_paths": {
            "terrain_walk": os.path.abspath(tw.__file__),
            "kinematic_bridge": os.path.abspath(kb.__file__),
            "framework": os.path.abspath(fw.__file__),
            "whole_body_controller": os.path.abspath(wbc.__file__),
        },
        "total_frames": len(states),
        "planned_total_frames": int(total_frames),
        "schedule": sched_dump,
        "frames": frame_rows,
        "wbc_all_success": all(r["success"] for r in wbc_records),
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp)


def _worker_T02_stationary_fk(out_json: str, meas_json: str) -> None:
    import bpy
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_progress
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    # Reference baseline standing (upper_limb_L=None, upper_limb_R=None) for exact R-arm comparison
    cfg0, sc0, root0, arm0, _, env0 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(
        start_pos=(0.0, -8.0, 0.0),
        target_pos=(0.0, -8.0, 0.0),
        stand_start_frames=18,
        stand_stop_frames=18,
    )
    pl0 = MotionPlanner(config=cfg0, armature_obj=arm0, environment=env0)
    pl0.add_action(TerrainWalkAction(route=route, environment=env0, action_name="T02_HistRef"))
    res0 = pl0.execute(initial_state=create_initial_motion_state(cfg0, start_frame=1, position=route.start_pos))
    ref_r_by_frame = {}
    for st in res0["states"]:
        sc0.frame_set(st.frame)
        bpy.context.view_layer.update()
        ref_r_by_frame[st.frame] = _eval_leg_and_arm_bones(arm0)

    # Fresh production scene for T02 deliverable
    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=True)
    seg_l = UpperLimbSegment(
        mode="FK",
        start_time_sec=0.25,
        duration_sec=0.75,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((65.0, 0.0, 20.0), (45.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        position_space="WORLD",
    )
    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(
            TerrainWalkAction(
                route=route,
                environment=env,
                action_name="T02_StationaryUnilateralFK",
                upper_limb_L=(seg_l,),
                upper_limb_R=None,
            )
        )
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    max_root_drift = 0.0
    max_l_fk_err_deg = 0.0
    max_r_ref_diff = 0.0
    max_inf = 0.0
    l_motion_range_deg = 0.0
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)
        _, h = _evaluate_upper_limb_progress(t, seg_l.start_time_sec, seg_l.duration_sec)
        exp_l = tuple(
            tuple((1.0 - h) * s[c] + h * e[c] for c in range(3))
            for s, e in zip(seg_l.fk_start_deg, seg_l.fk_end_deg)
        )
        act_l = _extract_upper_fk_deg(arm_obj, "L")
        for bi in range(3):
            for ai in range(3):
                max_l_fk_err_deg = max(max_l_fk_err_deg, abs(act_l[bi][ai] - exp_l[bi][ai]))
        l_motion_range_deg = max(l_motion_range_deg, act_l[0][0])
        root_drift = (root_obj.matrix_world.translation - root_obj.matrix_world.translation.__class__((0.0, -8.0, 0.0))).length
        max_root_drift = max(max_root_drift, root_drift)
        cur_bones = _eval_leg_and_arm_bones(arm_obj)
        max_r_ref_diff = max(
            max_r_ref_diff,
            _compare_bone_dicts(cur_bones, ref_r_by_frame[st.frame], ("shoulder.R", "upper_arm.R", "forearm.R", "hand.R")),
        )
        for cname, bname in (("ArmIK.L", "forearm.L"), ("ArmIK.R", "forearm.R"), ("HandRotation.L", "hand.L"), ("HandRotation.R", "hand.R")):
            max_inf = max(max_inf, abs(arm_obj.pose.bones[bname].constraints[cname].influence))

    assert max_l_fk_err_deg <= 1e-3, f"T02 L FK err {max_l_fk_err_deg}"
    assert l_motion_range_deg >= 60.0, f"T02 L arm did not raise as expected: {l_motion_range_deg}"
    assert max_root_drift <= 1e-6, f"T02 root drifted {max_root_drift}"
    assert max_r_ref_diff <= 1e-6, f"T02 R arm differed from baseline: {max_r_ref_diff}"
    assert max_inf <= 1e-6, f"T02 non-zero IK influence: {max_inf}"

    meas = _check_delivery_gate_and_save(
        arm_obj, root_obj, scene, 1, len(states), wbc_records, states, DELIVERABLE_BLENDS["T02_stationary_fk"]
    )
    with open(meas_json, "w", encoding="utf-8") as fp:
        json.dump(meas, fp)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T02",
            "passed": True,
            "total_frames": len(states),
            "max_l_fk_err_deg": max_l_fk_err_deg,
            "l_upper_arm_peak_x_deg": l_motion_range_deg,
            "max_root_drift_m": max_root_drift,
            "max_r_baseline_matrix_diff": max_r_ref_diff,
            "max_constraint_influence": max_inf,
            "blend_path": os.path.abspath(DELIVERABLE_BLENDS["T02_stationary_fk"]),
        }, fp, indent=2)


def _worker_T03_bilateral_fk(out_json: str) -> None:
    import bpy
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_progress
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(
        start_pos=(0.0, -8.0, 0.0),
        target_pos=(0.0, -8.0, 0.0),
        stand_start_frames=24,
        stand_stop_frames=24,
    )
    seg_l = UpperLimbSegment(
        mode="FK",
        start_time_sec=0.20,
        duration_sec=0.80,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((55.0, 10.0, 20.0), (40.0, -15.0, 0.0), (15.0, 0.0, 5.0)),
    )
    seg_r = UpperLimbSegment(
        mode="FK",
        start_time_sec=0.45,
        duration_sec=1.10,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((-25.0, -15.0, -35.0), (60.0, 20.0, 0.0), (-20.0, 0.0, -10.0)),
    )

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name="T03", upper_limb_L=(seg_l,), upper_limb_R=(seg_r,)))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records)
    max_err_l = 0.0
    max_err_r = 0.0
    phase_div_count = 0
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)
        _, hl = _evaluate_upper_limb_progress(t, seg_l.start_time_sec, seg_l.duration_sec)
        _, hr = _evaluate_upper_limb_progress(t, seg_r.start_time_sec, seg_r.duration_sec)
        if abs(hl - hr) > 0.15:
            phase_div_count += 1
        exp_l = tuple(tuple((1.0 - hl) * s[c] + hl * e[c] for c in range(3)) for s, e in zip(seg_l.fk_start_deg, seg_l.fk_end_deg))
        exp_r = tuple(tuple((1.0 - hr) * s[c] + hr * e[c] for c in range(3)) for s, e in zip(seg_r.fk_start_deg, seg_r.fk_end_deg))
        act_l = _extract_upper_fk_deg(arm_obj, "L")
        act_r = _extract_upper_fk_deg(arm_obj, "R")
        for bi in range(3):
            for ai in range(3):
                max_err_l = max(max_err_l, abs(act_l[bi][ai] - exp_l[bi][ai]))
                max_err_r = max(max_err_r, abs(act_r[bi][ai] - exp_r[bi][ai]))

    assert max_err_l <= 1e-3 and max_err_r <= 1e-3, f"T03 FK err L={max_err_l}, R={max_err_r}"
    assert phase_div_count >= 10
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T03",
            "passed": True,
            "total_frames": len(states),
            "max_err_l_deg": max_err_l,
            "max_err_r_deg": max_err_r,
            "divergent_progress_frames": phase_div_count,
        }, fp, indent=2)


def _worker_T04_unilateral_ik(out_json: str) -> None:
    import bpy
    from mathutils import Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_segment
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    # Reference R historical standing
    cfg0, sc0, _, arm0, _, env0 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=18, stand_stop_frames=18)
    pl0 = MotionPlanner(config=cfg0, armature_obj=arm0, environment=env0)
    pl0.add_action(TerrainWalkAction(route=route, environment=env0, action_name="T04_Ref"))
    res0 = pl0.execute(initial_state=create_initial_motion_state(cfg0, start_frame=1, position=route.start_pos))
    ref_r = {}
    for st in res0["states"]:
        sc0.frame_set(st.frame)
        bpy.context.view_layer.update()
        ref_r[st.frame] = _eval_leg_and_arm_bones(arm0)

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    seg_l = UpperLimbSegment(
        mode="IK",
        start_time_sec=0.25,
        duration_sec=0.75,
        wrist_start_xyz=(-0.24, 0.12, 1.05),
        wrist_end_xyz=(-0.24, 0.34, 1.24),
        pole_start_xyz=(-0.32, -0.25, 1.20),
        pole_end_xyz=(-0.32, -0.25, 1.25),
        position_space="ROOT_LOCAL",
        clamp_reach=False,
    )

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name="T04", upper_limb_L=(seg_l,), upper_limb_R=None))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records)
    max_wrist_err = 0.0
    max_r_diff = 0.0
    spurious_contacts = []
    inf_violations = []
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)
        tgt, _ = _evaluate_upper_limb_segment(seg_l, "L", t, st.position, 0.0)
        actual_wrist = arm_obj.matrix_world @ arm_obj.pose.bones["forearm.L"].tail
        err = (actual_wrist - Vector(tgt.world_xyz)).length
        max_wrist_err = max(max_wrist_err, err)

        from src.motion.contact_model import ContactType
        if tgt.contact_intent or tgt.is_locked or tgt.contact_type != ContactType.FREE:
            spurious_contacts.append((st.frame, "planned_hand_L", tgt.contact_intent, tgt.is_locked, tgt.contact_type.value))

        for ck, cs in st.contacts.items():
            if "HAND" in ck.upper() and (cs.is_locked or cs.phase not in ("free", "swing")):
                spurious_contacts.append((st.frame, ck, cs.phase, cs.is_locked))

        inf_vals = {
            "ArmIK.L": arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].influence,
            "ArmIK.R": arm_obj.pose.bones["forearm.R"].constraints["ArmIK.R"].influence,
            "HandRotation.L": arm_obj.pose.bones["hand.L"].constraints["HandRotation.L"].influence,
            "HandRotation.R": arm_obj.pose.bones["hand.R"].constraints["HandRotation.R"].influence,
        }
        expected_inf = {"ArmIK.L": 1.0, "ArmIK.R": 0.0, "HandRotation.L": 1.0, "HandRotation.R": 0.0}
        for k, ev in expected_inf.items():
            if abs(inf_vals[k] - ev) > 1e-6:
                inf_violations.append((st.frame, k, inf_vals[k], ev))

        cur_b = _eval_leg_and_arm_bones(arm_obj)
        max_r_diff = max(max_r_diff, _compare_bone_dicts(cur_b, ref_r[st.frame], ("shoulder.R", "upper_arm.R", "forearm.R", "hand.R")))

    assert max_wrist_err <= 0.005, f"T04 wrist err {max_wrist_err}"
    assert not spurious_contacts, f"T04 spurious hand contacts: {spurious_contacts}"
    assert not inf_violations, f"T04 influence mismatch: {inf_violations}"
    assert max_r_diff <= 1e-6, f"T04 R arm changed: {max_r_diff}"

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T04",
            "passed": True,
            "total_frames": len(states),
            "max_wrist_pos_err_m": max_wrist_err,
            "max_r_baseline_matrix_diff": max_r_diff,
            "spurious_hand_contacts": spurious_contacts,
            "influence_violations": inf_violations,
        }, fp, indent=2)


def _worker_T05_bilateral_ik(out_json: str, meas_json: str) -> None:
    import bpy
    from mathutils import Euler, Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_segment
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=True)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=24, stand_stop_frames=24)

    seg_l = UpperLimbSegment(
        mode="IK",
        start_time_sec=0.20,
        duration_sec=0.90,
        wrist_start_xyz=(-0.24, 0.14, 1.06),
        wrist_end_xyz=(-0.26, 0.34, 1.26),
        pole_start_xyz=(-0.34, -0.25, 1.20),
        pole_end_xyz=(-0.38, -0.22, 1.26),
        rotation_start_deg=(15.0, 0.0, 4.0),
        rotation_end_deg=(42.0, 6.0, -4.0),
        position_space="ROOT_LOCAL",
        clamp_reach=False,
    )
    seg_r = UpperLimbSegment(
        mode="IK",
        start_time_sec=0.35,
        duration_sec=1.05,
        wrist_start_xyz=(0.24, 0.12, 1.05),
        wrist_end_xyz=(0.28, 0.32, 1.22),
        pole_start_xyz=(0.34, -0.25, 1.20),
        pole_end_xyz=(0.40, -0.20, 1.24),
        rotation_start_deg=(12.0, -4.0, -3.0),
        rotation_end_deg=(38.0, -6.0, 5.0),
        position_space="ROOT_LOCAL",
        clamp_reach=False,
    )

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name="T05_BilateralIK", upper_limb_L=(seg_l,), upper_limb_R=(seg_r,)))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records)
    max_pos_err = {"L": 0.0, "R": 0.0}
    max_rot_err = {"L": 0.0, "R": 0.0}
    max_pole_err = {"L": 0.0, "R": 0.0}
    max_inf_err = 0.0

    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)
        for side, seg in (("L", seg_l), ("R", seg_r)):
            tgt, _ = _evaluate_upper_limb_segment(seg, side, t, st.position, 0.0)
            actual_wrist = arm_obj.matrix_world @ arm_obj.pose.bones[f"forearm.{side}"].tail
            pos_err = (actual_wrist - Vector(tgt.world_xyz)).length
            max_pos_err[side] = max(max_pos_err[side], pos_err)

            q_tgt = Euler([math.radians(a) for a in tgt.rotation_deg], "XYZ").to_quaternion()
            q_act = (arm_obj.matrix_world @ arm_obj.pose.bones[f"hand.{side}"].matrix).to_3x3().normalized().to_quaternion()
            rot_err = _quat_angle_deg(q_tgt, q_act)
            max_rot_err[side] = max(max_rot_err[side], rot_err)

            pole_pos = bpy.data.objects[f"ElbowPole.{side}"].matrix_world.translation
            max_pole_err[side] = max(max_pole_err[side], (pole_pos - Vector(tgt.pole_hint_world_xyz)).length)

        for cname, bname in (("ArmIK.L", "forearm.L"), ("ArmIK.R", "forearm.R"), ("HandRotation.L", "hand.L"), ("HandRotation.R", "hand.R")):
            max_inf_err = max(max_inf_err, abs(arm_obj.pose.bones[bname].constraints[cname].influence - 1.0))

    assert max_pos_err["L"] <= 0.005 and max_pos_err["R"] <= 0.005
    assert max_rot_err["L"] <= 1.0 and max_rot_err["R"] <= 1.0
    assert max_pole_err["L"] <= 1e-5 and max_pole_err["R"] <= 1e-5
    assert max_inf_err <= 1e-6

    meas = _check_delivery_gate_and_save(
        arm_obj, root_obj, scene, 1, len(states), wbc_records, states, DELIVERABLE_BLENDS["T05_bilateral_ik"]
    )
    with open(meas_json, "w", encoding="utf-8") as fp:
        json.dump(meas, fp)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T05",
            "passed": True,
            "total_frames": len(states),
            "max_wrist_pos_err_m": max_pos_err,
            "max_hand_rot_err_deg": max_rot_err,
            "max_pole_ctrl_err_m": max_pole_err,
            "max_influence_err_from_1": max_inf_err,
            "blend_path": os.path.abspath(DELIVERABLE_BLENDS["T05_bilateral_ik"]),
        }, fp, indent=2)


def _worker_T06_run(with_upper: bool, out_json: str, meas_json: Optional[str] = None) -> None:
    import bpy
    from mathutils import Euler, Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import (
        TerrainRouteInput,
        TerrainWalkAction,
        UpperLimbSegment,
        _evaluate_upper_limb_progress,
        _evaluate_upper_limb_segment,
        plan_terrain_footsteps,
    )
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, env = _build_terrain_production_rig()
    route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30,
        step_frames=16,
        stand_start_frames=6,
        stand_stop_frames=6,
    )

    seg_l = UpperLimbSegment(
        mode="IK",
        start_time_sec=0.50,
        duration_sec=1.80,
        wrist_start_xyz=(-0.24, 0.14, 1.06),
        wrist_end_xyz=(-0.24, 0.32, 1.24),
        pole_start_xyz=(-0.34, -0.25, 1.20),
        pole_end_xyz=(-0.36, -0.22, 1.26),
        rotation_start_deg=(15.0, 0.0, 0.0),
        rotation_end_deg=(38.0, 4.0, 4.0),
        position_space="ROOT_LOCAL",
        clamp_reach=False,
    )
    seg_r = UpperLimbSegment(
        mode="FK",
        start_time_sec=0.35,
        duration_sec=1.60,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((42.0, -5.0, -18.0), (45.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
        position_space="WORLD",
    )

    import dataclasses
    schedule, total_frames = plan_terrain_footsteps(route, env, start_frame=1)
    sched_dump = [dataclasses.asdict(st) for st in schedule]

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        action = TerrainWalkAction(
            route=route,
            environment=env,
            action_name="T06_WalkingUpperLimb" if with_upper else "T06_WalkingBaseline",
            upper_limb_L=(seg_l,) if with_upper else None,
            upper_limb_R=(seg_r,) if with_upper else None,
        )
        planner.add_action(action)
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records), "WBC failed in T06 terrain walk"

    max_l_wrist_err = 0.0
    max_l_rot_err = 0.0
    max_r_fk_err = 0.0
    frame_rows = []
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)
        if with_upper:
            tgt_l, _ = _evaluate_upper_limb_segment(seg_l, "L", t, st.position, 0.0)
            w_act = arm_obj.matrix_world @ arm_obj.pose.bones["forearm.L"].tail
            max_l_wrist_err = max(max_l_wrist_err, (w_act - Vector(tgt_l.world_xyz)).length)
            q_tgt = Euler([math.radians(a) for a in tgt_l.rotation_deg], "XYZ").to_quaternion()
            q_act = (arm_obj.matrix_world @ arm_obj.pose.bones["hand.L"].matrix).to_3x3().normalized().to_quaternion()
            max_l_rot_err = max(max_l_rot_err, _quat_angle_deg(q_tgt, q_act))

            _, hr = _evaluate_upper_limb_progress(t, seg_r.start_time_sec, seg_r.duration_sec)
            exp_r = tuple(tuple((1.0 - hr) * s[c] + hr * e[c] for c in range(3)) for s, e in zip(seg_r.fk_start_deg, seg_r.fk_end_deg))
            act_r = _extract_upper_fk_deg(arm_obj, "R")
            for bi in range(3):
                for ai in range(3):
                    max_r_fk_err = max(max_r_fk_err, abs(act_r[bi][ai] - exp_r[bi][ai]))

        contacts = {
            k: {
                "limb": str(c.limb),
                "is_locked": bool(c.is_locked),
                "phase": str(c.phase),
                "contact_world_xyz": [float(v) for v in c.contact_world_xyz],
                "current_world_xyz": [float(v) for v in c.current_world_xyz],
                "drift_m": float(c.drift_m),
            }
            for k, c in sorted(st.contacts.items())
        }
        bones_all = _eval_leg_and_arm_bones(arm_obj)
        leg_bones = {b: bones_all[b] for b in ("pelvis", "thigh.L", "shin.L", "foot.L", "thigh.R", "shin.R", "foot.R")}
        frame_rows.append({
            "frame": int(st.frame),
            "time_sec": float(st.time_sec),
            "root_world_pos": [float(v) for v in root_obj.matrix_world.translation],
            "root_world_matrix": _mat4_to_lists(root_obj.matrix_world),
            "com_world": wbc_records[f_idx]["com_world"],
            "contacts": contacts,
            "leg_bones": leg_bones,
        })

    if with_upper:
        assert max_l_wrist_err <= 0.005, f"T06 L wrist err {max_l_wrist_err}"
        assert max_l_rot_err <= 1.0, f"T06 L hand rot err {max_l_rot_err}"
        assert max_r_fk_err <= 1e-3, f"T06 R FK err {max_r_fk_err}"
        assert meas_json is not None
        meas = _check_delivery_gate_and_save(
            arm_obj, root_obj, scene, 1, len(states), wbc_records, states, DELIVERABLE_BLENDS["T06_walking_upper_limb"]
        )
        with open(meas_json, "w", encoding="utf-8") as fp:
            json.dump(meas, fp)

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "with_upper": with_upper,
            "total_frames": len(states),
            "schedule": sched_dump,
            "max_l_wrist_err_m": max_l_wrist_err,
            "max_l_rot_err_deg": max_l_rot_err,
            "max_r_fk_err_deg": max_r_fk_err,
            "frames": frame_rows,
        }, fp)


def _run_fk_ik_combo(combo_name: str, fk_side: str, ik_side: str) -> Dict[str, Any]:
    import bpy
    from mathutils import Euler, Vector
    from src.motion.terrain_walk import (
        TerrainRouteInput,
        TerrainWalkAction,
        UpperLimbSegment,
        _evaluate_upper_limb_progress,
        _evaluate_upper_limb_segment,
    )
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=18, stand_stop_frames=18)

    sign_fk = -1.0 if fk_side == "L" else 1.0
    sign_ik = -1.0 if ik_side == "L" else 1.0

    seg_fk = UpperLimbSegment(
        mode="FK",
        start_time_sec=0.20,
        duration_sec=0.85,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((50.0, 0.0, -18.0 * sign_fk), (38.0, 0.0, 0.0), (10.0, 0.0, 0.0)),
    )
    seg_ik = UpperLimbSegment(
        mode="IK",
        start_time_sec=0.30,
        duration_sec=0.80,
        wrist_start_xyz=(0.24 * sign_ik, 0.12, 1.05),
        wrist_end_xyz=(0.26 * sign_ik, 0.34, 1.24),
        pole_start_xyz=(0.34 * sign_ik, -0.25, 1.20),
        pole_end_xyz=(0.36 * sign_ik, -0.22, 1.25),
        rotation_start_deg=(15.0, 0.0, 0.0),
        rotation_end_deg=(40.0, 4.0 * sign_ik, -4.0 * sign_ik),
        position_space="ROOT_LOCAL",
        clamp_reach=False,
    )

    kwargs = {
        f"upper_limb_{fk_side}": (seg_fk,),
        f"upper_limb_{ik_side}": (seg_ik,),
    }
    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name=combo_name, **kwargs))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records)
    max_fk_err = 0.0
    max_ik_pos_err = 0.0
    max_ik_rot_err = 0.0
    max_inf_err = 0.0
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)

        _, hfk = _evaluate_upper_limb_progress(t, seg_fk.start_time_sec, seg_fk.duration_sec)
        exp_fk = tuple(tuple((1.0 - hfk) * s[c] + hfk * e[c] for c in range(3)) for s, e in zip(seg_fk.fk_start_deg, seg_fk.fk_end_deg))
        act_fk = _extract_upper_fk_deg(arm_obj, fk_side)
        for bi in range(3):
            for ai in range(3):
                max_fk_err = max(max_fk_err, abs(act_fk[bi][ai] - exp_fk[bi][ai]))

        tgt_ik, _ = _evaluate_upper_limb_segment(seg_ik, ik_side, t, st.position, 0.0)
        act_w = arm_obj.matrix_world @ arm_obj.pose.bones[f"forearm.{ik_side}"].tail
        max_ik_pos_err = max(max_ik_pos_err, (act_w - Vector(tgt_ik.world_xyz)).length)
        q_tgt = Euler([math.radians(a) for a in tgt_ik.rotation_deg], "XYZ").to_quaternion()
        q_act = (arm_obj.matrix_world @ arm_obj.pose.bones[f"hand.{ik_side}"].matrix).to_3x3().normalized().to_quaternion()
        max_ik_rot_err = max(max_ik_rot_err, _quat_angle_deg(q_tgt, q_act))

        exp_inf = {
            f"ArmIK.{fk_side}": 0.0,
            f"HandRotation.{fk_side}": 0.0,
            f"ArmIK.{ik_side}": 1.0,
            f"HandRotation.{ik_side}": 1.0,
        }
        for cname, bname in ((f"ArmIK.{fk_side}", f"forearm.{fk_side}"), (f"HandRotation.{fk_side}", f"hand.{fk_side}"), (f"ArmIK.{ik_side}", f"forearm.{ik_side}"), (f"HandRotation.{ik_side}", f"hand.{ik_side}")):
            max_inf_err = max(max_inf_err, abs(arm_obj.pose.bones[bname].constraints[cname].influence - exp_inf[cname]))

    assert max_fk_err <= 1e-3
    assert max_ik_pos_err <= 0.005
    assert max_ik_rot_err <= 1.0
    assert max_inf_err <= 1e-6
    return {
        "test_id": combo_name,
        "passed": True,
        "fk_side": fk_side,
        "ik_side": ik_side,
        "max_fk_err_deg": max_fk_err,
        "max_ik_pos_err_m": max_ik_pos_err,
        "max_ik_rot_err_deg": max_ik_rot_err,
        "max_influence_err": max_inf_err,
    }


def _worker_T07_left_fk_right_ik(out_json: str) -> None:
    _setup_sys_path(REPO_ROOT)
    r = _run_fk_ik_combo("T07", "L", "R")
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(r, fp, indent=2)


def _worker_T08_left_ik_right_fk(out_json: str) -> None:
    _setup_sys_path(REPO_ROOT)
    r = _run_fk_ik_combo("T08", "R", "L")
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(r, fp, indent=2)


def _worker_T09_multisegment(out_json: str) -> None:
    import bpy
    from mathutils import Euler, Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_progress
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=34, stand_stop_frames=34)

    # 68 frames => t in [0, 67/24 = 2.7917s]
    fk1 = UpperLimbSegment(
        mode="FK", start_time_sec=0.35, duration_sec=0.60,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=((45.0, 0.0, 15.0), (35.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
    )
    fk2 = UpperLimbSegment(
        mode="FK", start_time_sec=1.55, duration_sec=0.70,
        fk_start_deg=((45.0, 0.0, 15.0), (35.0, 0.0, 0.0), (5.0, 0.0, 0.0)),
        fk_end_deg=((80.0, 0.0, 28.0), (65.0, 0.0, 0.0), (15.0, 0.0, 0.0)),
    )

    ik1 = UpperLimbSegment(
        mode="IK", start_time_sec=0.30, duration_sec=0.60,
        wrist_start_xyz=(0.24, 0.12, 1.05), wrist_end_xyz=(0.24, 0.30, 1.20),
        pole_start_xyz=(0.34, -0.25, 1.20), pole_end_xyz=(0.36, -0.24, 1.24),
        rotation_start_deg=(12.0, 0.0, 0.0), rotation_end_deg=(30.0, 0.0, 0.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )
    ik2 = UpperLimbSegment(
        mode="IK", start_time_sec=1.50, duration_sec=0.70,
        wrist_start_xyz=(0.24, 0.30, 1.20), wrist_end_xyz=(0.26, 0.34, 1.28),
        pole_start_xyz=(0.36, -0.24, 1.24), pole_end_xyz=(0.36, -0.24, 1.26),
        rotation_start_deg=(30.0, 0.0, 0.0), rotation_end_deg=(42.0, 0.0, 0.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name="T09_MultiSeg", upper_limb_L=(fk1, fk2), upper_limb_R=(ik1, ik2)))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records)
    regions_seen = {"pre": 0, "seg1": 0, "gap": 0, "seg2": 0, "post": 0}
    max_fk_err = 0.0
    max_ik_err = 0.0
    max_gap_hold_drift_deg = 0.0
    for f_idx, st in enumerate(states):
        scene.frame_set(st.frame)
        bpy.context.view_layer.update()
        t = f_idx / float(cfg.fps)

        if t < fk1.start_time_sec:
            regions_seen["pre"] += 1
            exp_l = fk1.fk_start_deg
        elif t <= fk1.start_time_sec + fk1.duration_sec:
            regions_seen["seg1"] += 1
            _, h = _evaluate_upper_limb_progress(t, fk1.start_time_sec, fk1.duration_sec)
            exp_l = tuple(tuple((1.0 - h) * s[c] + h * e[c] for c in range(3)) for s, e in zip(fk1.fk_start_deg, fk1.fk_end_deg))
        elif t < fk2.start_time_sec:
            regions_seen["gap"] += 1
            exp_l = fk1.fk_end_deg
            act_l = _extract_upper_fk_deg(arm_obj, "L")
            for bi in range(3):
                for ai in range(3):
                    max_gap_hold_drift_deg = max(max_gap_hold_drift_deg, abs(act_l[bi][ai] - fk1.fk_end_deg[bi][ai]))
        elif t <= fk2.start_time_sec + fk2.duration_sec:
            regions_seen["seg2"] += 1
            _, h = _evaluate_upper_limb_progress(t, fk2.start_time_sec, fk2.duration_sec)
            exp_l = tuple(tuple((1.0 - h) * s[c] + h * e[c] for c in range(3)) for s, e in zip(fk2.fk_start_deg, fk2.fk_end_deg))
        else:
            regions_seen["post"] += 1
            exp_l = fk2.fk_end_deg

        act_l = _extract_upper_fk_deg(arm_obj, "L")
        for bi in range(3):
            for ai in range(3):
                max_fk_err = max(max_fk_err, abs(act_l[bi][ai] - exp_l[bi][ai]))

        # Right IK checks across same 5 windows
        seg_r = ik1 if t < ik2.start_time_sec else ik2
        _, hr = _evaluate_upper_limb_progress(t, seg_r.start_time_sec, seg_r.duration_sec)
        exp_r_w_local = Vector(tuple((1.0 - hr) * seg_r.wrist_start_xyz[c] + hr * seg_r.wrist_end_xyz[c] for c in range(3)))
        exp_r_w = Vector(st.position) + exp_r_w_local
        act_r_w = arm_obj.matrix_world @ arm_obj.pose.bones["forearm.R"].tail
        max_ik_err = max(max_ik_err, (act_r_w - exp_r_w).length)

    assert all(v >= 4 for v in regions_seen.values()), f"Not all 5 time regions well-covered: {regions_seen}"
    assert max_fk_err <= 1e-3, f"T09 FK err {max_fk_err}"
    assert max_gap_hold_drift_deg <= 1e-3, f"T09 gap failed to hold prior target: {max_gap_hold_drift_deg}"
    assert max_ik_err <= 0.005, f"T09 IK err {max_ik_err}"

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T09",
            "passed": True,
            "regions_frame_counts": regions_seen,
            "max_fk_err_deg": max_fk_err,
            "max_gap_hold_drift_deg": max_gap_hold_drift_deg,
            "max_ik_err_m": max_ik_err,
        }, fp, indent=2)


def _worker_T10_fk_ik_transition(out_json: str, meas_json: str) -> None:
    import bpy
    from mathutils import Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    # Step 1: Pre-probe 1 — Real production FK solve of Pose A to obtain matching IK endpoints
    fk_pose_A = ((48.0, 0.0, 12.0), (42.0, 0.0, 0.0), (8.0, 0.0, 0.0))
    cfg1, sc1, root1, arm1, _, env1 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    r_probe = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=2, stand_stop_frames=2)
    seg_probe_a = UpperLimbSegment(mode="FK", start_time_sec=0.0, duration_sec=1.0 / 24.0, fk_start_deg=fk_pose_A, fk_end_deg=fk_pose_A)
    p1 = MotionPlanner(config=cfg1, armature_obj=arm1, environment=env1)
    p1.add_action(TerrainWalkAction(route=r_probe, environment=env1, action_name="ProbeA", upper_limb_L=(seg_probe_a,)))
    p1.execute(initial_state=create_initial_motion_state(cfg1, start_frame=1, position=r_probe.start_pos))
    sc1.frame_set(2)
    bpy.context.view_layer.update()
    root_inv_1 = root1.matrix_world.inverted()
    arm_w_1 = arm1.matrix_world
    shoulder_A = root_inv_1 @ (arm_w_1 @ arm1.pose.bones["upper_arm.L"].head)
    elbow_A = root_inv_1 @ (arm_w_1 @ arm1.pose.bones["upper_arm.L"].tail)
    wrist_A = root_inv_1 @ (arm_w_1 @ arm1.pose.bones["forearm.L"].tail)
    sw = (wrist_A - shoulder_A).normalized()
    se = elbow_A - shoulder_A
    perp = se - sw * se.dot(sw)
    pole_A = elbow_A + 0.30 * perp.normalized()
    rot_A_deg = _extract_hand_world_euler_deg(arm1, "L")
    wrist_A_local = tuple(float(v) for v in wrist_A)
    pole_A_local = tuple(float(v) for v in pole_A)

    # Step 2: Pre-probe 2 — Real production IK solve of Pose B to obtain matching FK angles
    wrist_B_local = (-0.22, 0.28, 1.32)
    pole_B_local = (-0.36, -0.22, 1.24)
    rot_B_deg = (35.0, 5.0, -4.0)
    cfg2, sc2, root2, arm2, _, env2 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    seg_probe_b = UpperLimbSegment(
        mode="IK", start_time_sec=0.0, duration_sec=1.0 / 24.0,
        wrist_start_xyz=wrist_B_local, wrist_end_xyz=wrist_B_local,
        pole_start_xyz=pole_B_local, pole_end_xyz=pole_B_local,
        rotation_start_deg=rot_B_deg, rotation_end_deg=rot_B_deg,
        position_space="ROOT_LOCAL", clamp_reach=False,
    )
    p2 = MotionPlanner(config=cfg2, armature_obj=arm2, environment=env2)
    p2.add_action(TerrainWalkAction(route=r_probe, environment=env2, action_name="ProbeB", upper_limb_L=(seg_probe_b,)))
    p2.execute(initial_state=create_initial_motion_state(cfg2, start_frame=1, position=r_probe.start_pos))
    sc2.frame_set(2)
    bpy.context.view_layer.update()
    # Extract solved local rotations via pb.matrix (pose-space) / pb.matrix_basis!
    # Wait: in FK mode, constraints ArmIK/HandRotation have influence=0, so pb.matrix_basis
    # directly equals the solved pose rotation when there are no other constraints!
    # Let's extract rotation relative to rest (pb.bone.matrix_local vs pb.matrix) cleanly:
    fk_pose_B_list = []
    for bname in ("upper_arm.L", "forearm.L", "hand.L"):
        pb = arm2.pose.bones[bname]
        # Convert evaluated pose bone matrix back to local Euler relative to parent rest:
        if pb.parent is not None:
            rel_rest = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
            rel_pose = pb.parent.matrix.inverted() @ pb.matrix
            local_rot_mat = rel_rest.inverted() @ rel_pose
        else:
            local_rot_mat = pb.bone.matrix_local.inverted() @ pb.matrix
        e = local_rot_mat.to_3x3().normalized().to_euler("XYZ")
        fk_pose_B_list.append((math.degrees(e.x), math.degrees(e.y), math.degrees(e.z)))
    fk_pose_B = tuple(fk_pose_B_list)

    # Step 3: Build fresh isolated scene & execute FK -> IK -> FK
    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=True)
    fps = float(cfg.fps)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=28, stand_stop_frames=28)

    # Frame timeline (1..56, f_idx 0..55):
    # seg0 (FK): f_idx 4..16 (t=4/24..16/24), holds Pose A through f_idx 19 (Frame 20)
    # seg1 (IK): f_idx 20..36 (t=20/24..36/24), holds Pose B through f_idx 39 (Frame 40)
    # seg2 (FK): f_idx 40..52 (t=40/24..52/24), returns to rest
    seg0 = UpperLimbSegment(
        mode="FK", start_time_sec=4.0 / fps, duration_sec=12.0 / fps,
        fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        fk_end_deg=fk_pose_A,
    )
    seg1 = UpperLimbSegment(
        mode="IK", start_time_sec=20.0 / fps, duration_sec=16.0 / fps,
        wrist_start_xyz=wrist_A_local, wrist_end_xyz=wrist_B_local,
        pole_start_xyz=pole_A_local, pole_end_xyz=pole_B_local,
        rotation_start_deg=rot_A_deg, rotation_end_deg=rot_B_deg,
        position_space="ROOT_LOCAL", clamp_reach=False,
    )
    seg2 = UpperLimbSegment(
        mode="FK", start_time_sec=40.0 / fps, duration_sec=12.0 / fps,
        fk_start_deg=fk_pose_B,
        fk_end_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
    )

    orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(TerrainWalkAction(route=route, environment=env, action_name="T10_FK_IK_FK", upper_limb_L=(seg0, seg1, seg2), upper_limb_R=None))
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    states = res["states"]
    assert all(r["success"] for r in wbc_records), f"WBC failure in T10: {[r['unmet_constraints'] for r in wbc_records if not r['success']]}"

    def _sample_boundary(frame_num: int) -> Dict[str, Any]:
        scene.frame_set(frame_num)
        bpy.context.view_layer.update()
        aw = arm_obj.matrix_world
        wrist = aw @ arm_obj.pose.bones["forearm.L"].tail
        elbow = aw @ arm_obj.pose.bones["upper_arm.L"].tail
        bone_mats = {b: (aw @ arm_obj.pose.bones[b].matrix).to_3x3().normalized().to_quaternion() for b in ("upper_arm.L", "forearm.L", "hand.L")}
        bone_euler_deg = {}
        for b in ("upper_arm.L", "forearm.L", "hand.L"):
            e = (aw @ arm_obj.pose.bones[b].matrix).to_3x3().normalized().to_euler("XYZ")
            bone_euler_deg[b] = [math.degrees(e.x), math.degrees(e.y), math.degrees(e.z)]
        return {
            "frame": frame_num,
            "wrist_world": [float(v) for v in wrist],
            "elbow_world": [float(v) for v in elbow],
            "bone_world_quats": bone_mats,
            "bone_world_euler_deg": bone_euler_deg,
            "arm_ik_influence": float(arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].influence),
            "hand_rot_influence": float(arm_obj.pose.bones["hand.L"].constraints["HandRotation.L"].influence),
        }

    def _diff_boundary(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        wrist_d = (Vector(a["wrist_world"]) - Vector(b["wrist_world"])).length
        elbow_d = (Vector(a["elbow_world"]) - Vector(b["elbow_world"])).length
        rot_deltas_deg = {bn: _quat_angle_deg(a["bone_world_quats"][bn], b["bone_world_quats"][bn]) for bn in ("upper_arm.L", "forearm.L", "hand.L")}
        max_rot_d = max(rot_deltas_deg.values())
        return {
            "before_frame": a["frame"],
            "after_frame": b["frame"],
            "wrist_delta_m": wrist_d,
            "elbow_delta_m": elbow_d,
            "bone_rot_deltas_deg": rot_deltas_deg,
            "max_rot_delta_deg": max_rot_d,
            "before_arm_ik_influence": a["arm_ik_influence"],
            "after_arm_ik_influence": b["arm_ik_influence"],
            "before_hand_rot_influence": a["hand_rot_influence"],
            "after_hand_rot_influence": b["hand_rot_influence"],
            "before_wrist_world": a["wrist_world"],
            "after_wrist_world": b["wrist_world"],
            "before_elbow_world": a["elbow_world"],
            "after_elbow_world": b["elbow_world"],
            "before_bone_euler_deg": a["bone_world_euler_deg"],
            "after_bone_euler_deg": b["bone_world_euler_deg"],
        }

    # FK -> IK: frame 20 -> 21; IK -> FK: frame 40 -> 41
    fk_to_ik = _diff_boundary(_sample_boundary(20), _sample_boundary(21))
    ik_to_fk = _diff_boundary(_sample_boundary(40), _sample_boundary(41))

    assert fk_to_ik["before_arm_ik_influence"] == 0.0 and fk_to_ik["after_arm_ik_influence"] == 1.0
    assert ik_to_fk["before_arm_ik_influence"] == 1.0 and ik_to_fk["after_arm_ik_influence"] == 0.0
    assert fk_to_ik["wrist_delta_m"] <= 0.005 and fk_to_ik["elbow_delta_m"] <= 0.005 and fk_to_ik["max_rot_delta_deg"] <= 1.0, fk_to_ik
    assert ik_to_fk["wrist_delta_m"] <= 0.005 and ik_to_fk["elbow_delta_m"] <= 0.005 and ik_to_fk["max_rot_delta_deg"] <= 1.0, ik_to_fk

    meas = _check_delivery_gate_and_save(
        arm_obj, root_obj, scene, 1, len(states), wbc_records, states, DELIVERABLE_BLENDS["T10_fk_ik_transition"]
    )
    with open(meas_json, "w", encoding="utf-8") as fp:
        json.dump(meas, fp)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T10",
            "passed": True,
            "total_frames": len(states),
            "pre_solved_pose_a_wrist_local": list(wrist_A_local),
            "pre_solved_pose_a_rot_deg": list(rot_A_deg),
            "pre_solved_pose_b_fk_deg": [list(x) for x in fk_pose_B],
            "fk_to_ik_transition": fk_to_ik,
            "ik_to_fk_transition": ik_to_fk,
            "blend_path": os.path.abspath(DELIVERABLE_BLENDS["T10_fk_ik_transition"]),
        }, fp, indent=2)


def _worker_T12_regen_and_bug01(out_json: str) -> None:
    import bpy
    from mathutils import Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state
    vss = _load_vss()

    cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)

    # Pass 1: Long animation (50 frames)
    r1 = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=25, stand_stop_frames=25)
    p1 = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
    p1.add_action(
        TerrainWalkAction(
            route=r1, environment=env, action_name="T12_Long",
            upper_limb_L=(UpperLimbSegment(mode="IK", start_time_sec=0.2, duration_sec=1.5, wrist_start_xyz=(-0.24, 0.12, 1.05), wrist_end_xyz=(-0.26, 0.34, 1.24), pole_start_xyz=(-0.34, -0.25, 1.20), pole_end_xyz=(-0.38, -0.22, 1.25), rotation_start_deg=(10.0, 0.0, 0.0), rotation_end_deg=(35.0, 5.0, 0.0), position_space="ROOT_LOCAL", clamp_reach=False),),
            upper_limb_R=(UpperLimbSegment(mode="FK", start_time_sec=0.3, duration_sec=1.4, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((40,0,-15),(30,0,0),(5,0,0))),),
        )
    )
    res1 = p1.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=r1.start_pos))
    assert len(res1["states"]) == 50

    # Pass 2: Shorter different animation (24 frames) on SAME CharacterArmature & scene
    r2 = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=12, stand_stop_frames=12)
    seg_l2 = UpperLimbSegment(mode="FK", start_time_sec=0.1, duration_sec=0.7, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((55,0,20),(42,0,0),(8,0,0)))
    seg_r2 = UpperLimbSegment(mode="IK", start_time_sec=0.15, duration_sec=0.7, wrist_start_xyz=(0.24, 0.14, 1.08), wrist_end_xyz=(0.26, 0.32, 1.26), pole_start_xyz=(0.34, -0.25, 1.20), pole_end_xyz=(0.38, -0.20, 1.25), rotation_start_deg=(12.0, 0.0, 0.0), rotation_end_deg=(38.0, -4.0, 3.0), position_space="ROOT_LOCAL", clamp_reach=False)

    orig_exec, wbc_cls, wbc_records2 = _install_wbc_observer(arm_obj)
    try:
        p2 = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        p2.add_action(TerrainWalkAction(route=r2, environment=env, action_name="T12_Short", upper_limb_L=(seg_l2,), upper_limb_R=(seg_r2,)))
        res2 = p2.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=r2.start_pos))
    finally:
        _restore_wbc_observer(orig_exec, wbc_cls)

    assert len(res2["states"]) == 24 and all(r["success"] for r in wbc_records2)

    # Check 4 controllers & current Armature Action have NO keyframes > 24
    stale_keys: List[Dict[str, Any]] = []
    for obj_name in ("CharacterArmature", "HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
        obj = bpy.data.objects[obj_name]
        _, fcurves = vss._get_slot_fcurves(obj)
        for fc in fcurves:
            gt24 = [float(kp.co[0]) for kp in fc.keyframe_points if float(kp.co[0]) > 24.0 + 1e-6]
            if gt24:
                stale_keys.append({"object": obj_name, "data_path": fc.data_path, "stale_frames": gt24})
    assert not stale_keys, f"Stale keyframes > 24 detected: {stale_keys}"

    # Verify Pass 2 playback at end frame 24 reflects seg_l2 FK and seg_r2 IK
    scene.frame_set(24)
    bpy.context.view_layer.update()
    act_l24 = _extract_upper_fk_deg(arm_obj, "L")
    assert abs(act_l24[0][0] - 55.0) <= 1e-3 and abs(arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].influence) <= 1e-6
    act_r24_w = arm_obj.matrix_world @ arm_obj.pose.bones["forearm.R"].tail
    exp_r24_w = Vector(res2["states"][-1].position) + Vector(seg_r2.wrist_end_xyz)
    assert (act_r24_w - exp_r24_w).length <= 0.005

    # BUG-01 Check A: Same controller accessed via different RNA paths has identical identity & as_pointer()
    c_ik_l = arm_obj.pose.bones["forearm.L"].constraints["ArmIK.L"].target
    c_rot_l = arm_obj.pose.bones["hand.L"].constraints["HandRotation.L"].target
    c_obj_l = bpy.data.objects["HandIK.L"]
    ptr_match_l = (c_ik_l == c_rot_l == c_obj_l) and (c_ik_l.as_pointer() == c_rot_l.as_pointer() == c_obj_l.as_pointer())
    assert ptr_match_l, "RNA pointer/equality mismatch for HandIK.L"

    c_ik_r = arm_obj.pose.bones["forearm.R"].constraints["ArmIK.R"].target
    c_rot_r = arm_obj.pose.bones["hand.R"].constraints["HandRotation.R"].target
    c_obj_r = bpy.data.objects["HandIK.R"]
    ptr_match_r = (c_ik_r == c_rot_r == c_obj_r) and (c_ik_r.as_pointer() == c_rot_r.as_pointer() == c_obj_r.as_pointer())
    assert ptr_match_r, "RNA pointer/equality mismatch for HandIK.R"

    # BUG-01 Check B & C: OtherArmature borrowing HandIK.L (bone-level) and ElbowPole.L (object-level)
    other_arm_data = bpy.data.armatures.new("OtherArmatureData")
    other_arm = bpy.data.objects.new("OtherArmature", other_arm_data)
    bpy.context.scene.collection.objects.link(other_arm)
    bpy.context.view_layer.objects.active = other_arm
    bpy.ops.object.mode_set(mode="EDIT")
    eb = other_arm_data.edit_bones.new("other_bone")
    eb.head = (1.0, 0.0, 0.0)
    eb.tail = (1.0, 0.0, 0.5)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Give OtherArmature its own keyframed animation data
    other_arm.location = (1.0, 2.0, 0.0)
    other_arm.keyframe_insert(data_path="location", frame=1)
    other_arm.location = (1.5, 2.5, 0.0)
    other_arm.keyframe_insert(data_path="location", frame=10)
    orig_other_action = other_arm.animation_data.action
    _, orig_other_fcs = vss._get_slot_fcurves(other_arm)
    orig_other_fc_count = len(orig_other_fcs)
    assert orig_other_fc_count > 0

    # B: Bone-level constraint borrowing HandIK.L
    bone_con = other_arm.pose.bones["other_bone"].constraints.new("COPY_LOCATION")
    bone_con.target = bpy.data.objects["HandIK.L"]
    bone_conflict_err = None
    try:
        px = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        px.add_action(TerrainWalkAction(route=r2, environment=env, action_name="ShouldRejectBone"))
        px.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=r2.start_pos))
    except Exception as exc:
        bone_conflict_err = f"{type(exc).__name__}: {exc}"
    assert bone_conflict_err is not None, "BUG-01 bone-level ownership conflict was NOT rejected!"
    _, after_b_fcs = vss._get_slot_fcurves(other_arm)
    assert other_arm.animation_data is not None and other_arm.animation_data.action == orig_other_action
    assert len(after_b_fcs) == orig_other_fc_count

    # Swap to C: Object-level constraint borrowing ElbowPole.L
    other_arm.pose.bones["other_bone"].constraints.remove(bone_con)
    obj_con = other_arm.constraints.new("COPY_LOCATION")
    obj_con.target = bpy.data.objects["ElbowPole.L"]
    obj_conflict_err = None
    try:
        py = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        py.add_action(TerrainWalkAction(route=r2, environment=env, action_name="ShouldRejectObject"))
        py.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=r2.start_pos))
    except Exception as exc:
        obj_conflict_err = f"{type(exc).__name__}: {exc}"
    assert obj_conflict_err is not None, "BUG-01 object-level ownership conflict was NOT rejected!"
    _, after_o_fcs = vss._get_slot_fcurves(other_arm)
    assert other_arm.animation_data is not None and other_arm.animation_data.action == orig_other_action
    assert len(after_o_fcs) == orig_other_fc_count

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T12",
            "passed": True,
            "pass1_frames": 50,
            "pass2_frames": 24,
            "stale_keyframes_gt24": stale_keys,
            "rna_pointer_identity_L": ptr_match_l,
            "rna_pointer_identity_R": ptr_match_r,
            "bug01_bone_conflict_error": bone_conflict_err,
            "bug01_object_conflict_error": obj_conflict_err,
            "other_armature_animation_preserved": True,
        }, fp, indent=2)


def _worker_T13_invalid_rejection(out_json: str) -> None:
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state
    from src.motion.kinematic_bridge import KinematicBridgeExecutor
    from src.motion.whole_body_controller import WholeBodyController

    cfg, _, _, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=12, stand_stop_frames=12)

    valid_fk_a = UpperLimbSegment(mode="FK", start_time_sec=0.1, duration_sec=0.3, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((30,0,0),(20,0,0),(0,0,0)))
    valid_fk_b = UpperLimbSegment(mode="FK", start_time_sec=0.5, duration_sec=0.3, fk_start_deg=((30,0,0),(20,0,0),(0,0,0)), fk_end_deg=((10,0,0),(10,0,0),(0,0,0)))

    ik_base = dict(mode="IK", start_time_sec=0.1, duration_sec=0.3, wrist_start_xyz=(-0.24, 0.12, 1.05), wrist_end_xyz=(-0.24, 0.28, 1.20), position_space="ROOT_LOCAL")

    cases = [
        ("empty_tuple", lambda: TerrainWalkAction(route=route, environment=env, upper_limb_L=())),
        ("invalid_container_list", lambda: TerrainWalkAction(route=route, environment=env, upper_limb_L=[valid_fk_a])),
        ("invalid_element_type", lambda: TerrainWalkAction(route=route, environment=env, upper_limb_L=("bad_element",))),
        ("unordered_segments", lambda: TerrainWalkAction(route=route, environment=env, upper_limb_L=(valid_fk_b, valid_fk_a))),
        ("overlapping_segments", lambda: TerrainWalkAction(
            route=route, environment=env,
            upper_limb_L=(
                valid_fk_a,
                UpperLimbSegment(mode="FK", start_time_sec=0.35, duration_sec=0.4, fk_start_deg=((30,0,0),(20,0,0),(0,0,0)), fk_end_deg=((10,0,0),(10,0,0),(0,0,0))),
            ),
        )),
        ("out_of_action_time_range", lambda: TerrainWalkAction(
            route=route, environment=env,
            upper_limb_L=(
                UpperLimbSegment(mode="FK", start_time_sec=0.6, duration_sec=0.8, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((20,0,0),(10,0,0),(0,0,0))),
            ),
        )),
        ("same_mode_endpoint_mismatch", lambda: TerrainWalkAction(
            route=route, environment=env,
            upper_limb_L=(
                valid_fk_a,
                UpperLimbSegment(mode="FK", start_time_sec=0.5, duration_sec=0.3, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((15,0,0),(10,0,0),(0,0,0))),
            ),
        )),
        ("same_mode_space_conflict", lambda: TerrainWalkAction(
            route=route, environment=env,
            upper_limb_L=(
                UpperLimbSegment(**{**ik_base, "start_time_sec": 0.1, "duration_sec": 0.3, "position_space": "ROOT_LOCAL"}),
                UpperLimbSegment(mode="IK", start_time_sec=0.5, duration_sec=0.3, wrist_start_xyz=(-0.24, 0.28, 1.20), wrist_end_xyz=(-0.24, 0.32, 1.24), position_space="WORLD"),
            ),
        )),
        ("same_mode_optional_rot_pole_mismatch", lambda: TerrainWalkAction(
            route=route, environment=env,
            upper_limb_L=(
                UpperLimbSegment(**ik_base),
                UpperLimbSegment(mode="IK", start_time_sec=0.5, duration_sec=0.3, wrist_start_xyz=(-0.24, 0.28, 1.20), wrist_end_xyz=(-0.24, 0.32, 1.24), rotation_start_deg=(10.0, 0.0, 0.0), rotation_end_deg=(20.0, 0.0, 0.0), position_space="ROOT_LOCAL"),
            ),
        )),
    ]

    orig_wbc = WholeBodyController.execute_frame
    orig_bridge = KinematicBridgeExecutor.execute_frame
    exec_counter = {"wbc": 0, "bridge": 0}

    @functools.wraps(orig_wbc)
    def spy_wbc(self, *args, **kwargs):
        exec_counter["wbc"] += 1
        return orig_wbc(self, *args, **kwargs)

    @functools.wraps(orig_bridge)
    def spy_bridge(self, *args, **kwargs):
        exec_counter["bridge"] += 1
        return orig_bridge(self, *args, **kwargs)

    WholeBodyController.execute_frame = spy_wbc
    KinematicBridgeExecutor.execute_frame = spy_bridge
    subcases = []
    try:
        for name, factory in cases:
            exec_counter["wbc"] = 0
            exec_counter["bridge"] = 0
            err_msg = None
            try:
                act = factory()
                planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
                planner.add_action(act)
                planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
            except (TypeError, ValueError) as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
            assert err_msg is not None, f"Invalid case {name} did NOT raise!"
            assert exec_counter["wbc"] == 0 and exec_counter["bridge"] == 0, f"Case {name} executed frames before rejecting: {exec_counter}"
            subcases.append({
                "case": name,
                "rejected": True,
                "error": err_msg,
                "wbc_frames_executed": exec_counter["wbc"],
                "bridge_frames_executed": exec_counter["bridge"],
            })
    finally:
        WholeBodyController.execute_frame = orig_wbc
        KinematicBridgeExecutor.execute_frame = orig_bridge

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({"test_id": "T13", "passed": True, "subcases": subcases}, fp, indent=2)


def _worker_T14_non1_start_frame(out_json: str) -> None:
    import bpy
    from mathutils import Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=18, stand_stop_frames=18)
    seg_l = UpperLimbSegment(mode="FK", start_time_sec=0.25, duration_sec=0.75, fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((55,0,20),(40,0,0),(10,0,0)))
    seg_r = UpperLimbSegment(
        mode="IK", start_time_sec=0.20, duration_sec=0.80,
        wrist_start_xyz=(0.24, 0.12, 1.05), wrist_end_xyz=(0.26, 0.34, 1.24),
        pole_start_xyz=(0.34, -0.25, 1.20), pole_end_xyz=(0.38, -0.22, 1.26),
        rotation_start_deg=(12.0, 0.0, 0.0), rotation_end_deg=(38.0, -5.0, 4.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )

    # Run A: Start at frame 1 (frames 1..36)
    cfg1, sc1, _, arm1, _, env1 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    p1 = MotionPlanner(config=cfg1, armature_obj=arm1, environment=env1)
    p1.add_action(TerrainWalkAction(route=route, environment=env1, action_name="T14_Start1", upper_limb_L=(seg_l,), upper_limb_R=(seg_r,)))
    res1 = p1.execute(initial_state=create_initial_motion_state(cfg1, start_frame=1, position=route.start_pos))
    poses1 = []
    for st in res1["states"]:
        sc1.frame_set(st.frame)
        bpy.context.view_layer.update()
        poses1.append({
            "frame": st.frame,
            "time_sec": float(st.time_sec),
            "l_fk": _extract_upper_fk_deg(arm1, "L"),
            "r_ctrl": [float(v) for v in bpy.data.objects["HandIK.R"].matrix_world.translation],
            "r_wrist": [float(v) for v in (arm1.matrix_world @ arm1.pose.bones["forearm.R"].tail)],
            "r_hand_euler": list(_extract_hand_world_euler_deg(arm1, "R")),
        })

    # Run B: Chained after 100-frame precursor so second action starts at frame 101 (global timeline 1..136)
    cfg2, sc2, _, arm2, _, env2 = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    pre_route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=50, stand_stop_frames=50)
    p2 = MotionPlanner(config=cfg2, armature_obj=arm2, environment=env2)
    p2.add_action(TerrainWalkAction(route=pre_route, environment=env2, action_name="T14_Precursor_1_to_100"))
    p2.add_action(TerrainWalkAction(route=route, environment=env2, action_name="T14_Start101", upper_limb_L=(seg_l,), upper_limb_R=(seg_r,)))
    res2 = p2.execute(initial_state=create_initial_motion_state(cfg2, start_frame=1, position=route.start_pos))
    states2 = res2["states"]
    assert len(states2) == 136
    # Verify global frame & time continuity at 100 -> 101
    assert states2[99].frame == 100 and states2[100].frame == 101
    assert abs((states2[100].time_sec - states2[99].time_sec) - (1.0 / cfg2.fps)) <= 1e-12

    max_l_diff = 0.0
    max_r_ctrl_diff = 0.0
    max_r_wrist_diff = 0.0
    max_r_rot_diff = 0.0
    for idx in range(36):
        st2 = states2[100 + idx]
        assert st2.frame == 101 + idx
        sc2.frame_set(st2.frame)
        bpy.context.view_layer.update()
        l2 = _extract_upper_fk_deg(arm2, "L")
        r2_ctrl = Vector(bpy.data.objects["HandIK.R"].matrix_world.translation)
        r2_w = Vector(arm2.matrix_world @ arm2.pose.bones["forearm.R"].tail)
        r2_e = _extract_hand_world_euler_deg(arm2, "R")
        for bi in range(3):
            for ai in range(3):
                max_l_diff = max(max_l_diff, abs(l2[bi][ai] - poses1[idx]["l_fk"][bi][ai]))
        max_r_ctrl_diff = max(max_r_ctrl_diff, (r2_ctrl - Vector(poses1[idx]["r_ctrl"])).length)
        max_r_wrist_diff = max(max_r_wrist_diff, (r2_w - Vector(poses1[idx]["r_wrist"])).length)
        for ai in range(3):
            max_r_rot_diff = max(max_r_rot_diff, abs(r2_e[ai] - poses1[idx]["r_hand_euler"][ai]))

    assert max_l_diff <= 1e-4 and max_r_ctrl_diff <= 1e-6 and max_r_wrist_diff <= 1e-4 and max_r_rot_diff <= 1e-3, (
        f"T14 mismatch: max_l_diff={max_l_diff}, max_r_ctrl_diff={max_r_ctrl_diff}, max_r_wrist_diff={max_r_wrist_diff}, max_r_rot_diff={max_r_rot_diff}"
    )

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T14",
            "passed": True,
            "run1_frames": [1, 36],
            "run2_total_frames": len(states2),
            "action2_frames": [101, 136],
            "frame_100_to_101_dt_sec": float(states2[100].time_sec - states2[99].time_sec),
            "max_local_time_l_fk_diff_deg": max_l_diff,
            "max_local_time_r_ctrl_target_diff_m": max_r_ctrl_diff,
            "max_local_time_r_wrist_diff_m": max_r_wrist_diff,
            "max_local_time_r_hand_rot_diff_deg": max_r_rot_diff,
        }, fp, indent=2)


def _worker_T15_rotation_modes(out_json: str, temp_blend_a: str, temp_blend_b: str, meas_a: str, meas_b: str) -> None:
    import bpy
    from mathutils import Euler
    _setup_sys_path(REPO_ROOT)
    from src.rig.arm_ik import setup_arm_ik
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment, _evaluate_upper_limb_segment
    from src.motion.framework import MotionPlanner, create_initial_motion_state
    vss = _load_vss()

    cases = [
        (
            "config_A",
            {"HandIK.L": "XYZ", "HandIK.R": "YXZ", "ElbowPole.L": "QUATERNION", "ElbowPole.R": "AXIS_ANGLE"},
            temp_blend_a,
            meas_a,
        ),
        (
            "config_B",
            {"HandIK.L": "QUATERNION", "HandIK.R": "AXIS_ANGLE", "ElbowPole.L": "XYZ", "ElbowPole.R": "ZYX"},
            temp_blend_b,
            meas_b,
        ),
    ]

    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=12, stand_stop_frames=12)
    seg_l = UpperLimbSegment(
        mode="IK", start_time_sec=0.1, duration_sec=0.7,
        wrist_start_xyz=(-0.24, 0.14, 1.06), wrist_end_xyz=(-0.26, 0.34, 1.24),
        pole_start_xyz=(-0.34, -0.25, 1.20), pole_end_xyz=(-0.38, -0.20, 1.26),
        rotation_start_deg=(14.0, 3.0, 4.0), rotation_end_deg=(38.0, 6.0, -5.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )
    seg_r = UpperLimbSegment(
        mode="IK", start_time_sec=0.1, duration_sec=0.7,
        wrist_start_xyz=(0.24, 0.14, 1.06), wrist_end_xyz=(0.26, 0.34, 1.24),
        pole_start_xyz=(0.34, -0.25, 1.20), pole_end_xyz=(0.38, -0.20, 1.26),
        rotation_start_deg=(12.0, -3.0, -4.0), rotation_end_deg=(36.0, -5.0, 5.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )

    cfg_reports = []
    for label, mode_map, bpath, mpath in cases:
        cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=True)
        setup_arm_ik(arm_obj)
        for cname, rmode in mode_map.items():
            bpy.data.objects[cname].rotation_mode = rmode

        orig_exec, wbc_cls, wbc_records = _install_wbc_observer(arm_obj)
        try:
            pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
            pl.add_action(TerrainWalkAction(route=route, environment=env, action_name=f"T15_{label}", upper_limb_L=(seg_l,), upper_limb_R=(seg_r,)))
            res = pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
        finally:
            _restore_wbc_observer(orig_exec, wbc_cls)

        states = res["states"]
        assert all(r["success"] for r in wbc_records)
        # Verify rotation_mode preserved + channel keyframed + world orientation matches target
        max_ctrl_rot_err_deg = 0.0
        channel_fcurve_paths = {}
        expected_dp = {
            "XYZ": "rotation_euler",
            "YXZ": "rotation_euler",
            "ZYX": "rotation_euler",
            "QUATERNION": "rotation_quaternion",
            "AXIS_ANGLE": "rotation_axis_angle",
        }
        for cname, exp_rmode in mode_map.items():
            cobj = bpy.data.objects[cname]
            assert cobj.rotation_mode == exp_rmode, f"{cname} mode mutated to {cobj.rotation_mode}"
            _, fcurves = vss._get_slot_fcurves(cobj)
            dps = sorted({fc.data_path for fc in fcurves})
            assert expected_dp[exp_rmode] in dps, f"{cname} missing FCurve for {expected_dp[exp_rmode]}: {dps}"
            channel_fcurve_paths[cname] = dps

        for f_idx, st in enumerate(states):
            scene.frame_set(st.frame)
            bpy.context.view_layer.update()
            t = f_idx / float(cfg.fps)
            for side, seg in (("L", seg_l), ("R", seg_r)):
                tgt, _ = _evaluate_upper_limb_segment(seg, side, t, st.position, 0.0)
                q_tgt = Euler([math.radians(a) for a in tgt.rotation_deg], "XYZ").to_quaternion()
                q_ctrl = bpy.data.objects[f"HandIK.{side}"].matrix_world.to_3x3().normalized().to_quaternion()
                max_ctrl_rot_err_deg = max(max_ctrl_rot_err_deg, _quat_angle_deg(q_tgt, q_ctrl))

        assert max_ctrl_rot_err_deg <= 0.1
        meas = _check_delivery_gate_and_save(arm_obj, root_obj, scene, 1, len(states), wbc_records, states, bpath)
        with open(mpath, "w", encoding="utf-8") as fp:
            json.dump({label: meas}, fp)
        cfg_reports.append({
            "config": label,
            "rotation_modes": mode_map,
            "channel_fcurve_paths": channel_fcurve_paths,
            "max_controller_rot_err_deg": max_ctrl_rot_err_deg,
            "temp_blend": os.path.abspath(bpath),
        })

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({"test_id": "T15", "pre_save_configs": cfg_reports}, fp, indent=2)


def _worker_T16_keyframe_false(out_json: str) -> None:
    import bpy
    _setup_sys_path(REPO_ROOT)
    from src.motion.kinematic_bridge import (
        KinematicBridgeExecutor,
        KinematicPlannedPose,
        PlannedFootTarget,
        PlannedHandTarget,
    )
    from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, setup_leg_ik
    from src.rig.arm_ik import setup_arm_ik
    from src.motion.framework import MotionMode, MotionPlanner, create_initial_motion_state
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.contact_model import ContactType
    vss = _load_vss()

    def _snapshot_all_fcurves(arm_obj):
        snap = {}
        for obj_name in ("CharacterArmature", "HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            obj = bpy.data.objects.get(obj_name)
            if obj is None or obj.animation_data is None or obj.animation_data.action is None:
                snap[obj_name] = None
                continue
            _, fcurves = vss._get_slot_fcurves(obj)
            fc_dump = []
            for fc in sorted(fcurves, key=lambda c: (c.data_path, c.array_index)):
                fc_dump.append({
                    "data_path": fc.data_path,
                    "array_index": int(fc.array_index),
                    "kps": [[float(kp.co[0]), float(kp.co[1]), str(kp.interpolation)] for kp in fc.keyframe_points],
                })
            snap[obj_name] = fc_dump
        return snap

    # Subcase A: Fresh un-keyframed rig + execute_frame(..., keyframe=False)
    cfgA, scA, rootA, armA, _, envA = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    setup_leg_ik(armA)
    setup_arm_ik(armA)
    bridgeA = KinematicBridgeExecutor(armature_obj=armA, root_obj=rootA, environment=envA, default_fps=cfgA.fps)
    foot_l_stand = PlannedFootTarget(world_xyz=(-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True)
    foot_r_stand = PlannedFootTarget(world_xyz=(HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True)
    poseA = KinematicPlannedPose(
        frame=5,
        time_seconds=4.0 / 24.0,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        motion_mode=MotionMode.IDLE,
        pelvis_location=(0.0, -0.035, 0.0),
        foot_L=foot_l_stand,
        foot_R=foot_r_stand,
        hand_L=PlannedHandTarget(
            world_xyz=(-0.24, -7.68, 1.24),
            rotation_deg=(35.0, 0.0, 0.0),
            enabled=True,
            pole_hint_world_xyz=(-0.34, -8.25, 1.22),
            contact_type=ContactType.FREE,
            clamp_reach=False,
        ),
        fk_joint_rotations_deg={"upper_arm.R": (40.0, 0.0, -10.0), "forearm.R": (35.0, 0.0, 0.0)},
    )
    bresA = bridgeA.execute_frame(poseA, keyframe=False)
    assert bresA.success, f"poseA failed: {bresA.wbc_result.unmet_constraints}"
    snapA = _snapshot_all_fcurves(armA)
    assert all(v is None for v in snapA.values()), f"keyframe=False created animation_data: {snapA}"

    # Subcase B: Already-animated rig + execute_frame(..., keyframe=False) leaves existing curves unchanged
    cfgB, scB, rootB, armB, _, envB = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=12, stand_stop_frames=12)
    plB = MotionPlanner(config=cfgB, armature_obj=armB, environment=envB)
    plB.add_action(TerrainWalkAction(
        route=route, environment=envB, action_name="T16_PreAnim",
        upper_limb_L=(UpperLimbSegment(mode="IK", start_time_sec=0.1, duration_sec=0.7, wrist_start_xyz=(-0.24, 0.12, 1.05), wrist_end_xyz=(-0.24, 0.28, 1.20), pole_start_xyz=(-0.34, -0.25, 1.20), pole_end_xyz=(-0.34, -0.25, 1.22), rotation_start_deg=(10,0,0), rotation_end_deg=(28,0,0), position_space="ROOT_LOCAL", clamp_reach=False),),
    ))
    plB.execute(initial_state=create_initial_motion_state(cfgB, start_frame=1, position=route.start_pos))
    before_snap = _snapshot_all_fcurves(armB)

    bridgeB = KinematicBridgeExecutor(armature_obj=armB, root_obj=rootB, environment=envB, default_fps=cfgB.fps)
    poseB = KinematicPlannedPose(
        frame=10,
        time_seconds=9.0 / 24.0,
        root_position=(0.0, -8.0, 0.0),
        root_yaw_deg=0.0,
        motion_mode=MotionMode.IDLE,
        pelvis_location=(0.0, -0.035, 0.0),
        foot_L=foot_l_stand,
        foot_R=foot_r_stand,
        hand_L=PlannedHandTarget(
            world_xyz=(-0.26, -7.66, 1.24),
            rotation_deg=(38.0, 0.0, 0.0),
            enabled=True,
            pole_hint_world_xyz=(-0.36, -8.24, 1.24),
            contact_type=ContactType.FREE,
            clamp_reach=False,
        ),
    )
    bresB = bridgeB.execute_frame(poseB, keyframe=False)
    assert bresB.success, f"poseB failed: {bresB.wbc_result.unmet_constraints}"
    after_snap = _snapshot_all_fcurves(armB)
    assert before_snap == after_snap, "keyframe=False mutated existing animation FCurves!"

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({
            "test_id": "T16",
            "passed": True,
            "fresh_rig_animation_data_all_none": True,
            "existing_curves_unchanged_exact": True,
            "existing_fcurve_counts": {k: len(v) if v else 0 for k, v in after_snap.items()},
        }, fp, indent=2)


def _worker_T17_counterfactuals(out_json: str) -> None:
    import bpy
    from mathutils import Vector
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state
    from src.motion.kinematic_bridge import KinematicBridgeExecutor

    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=24, stand_stop_frames=24)
    base_l = UpperLimbSegment(
        mode="IK", start_time_sec=0.25, duration_sec=0.60,
        wrist_start_xyz=(-0.24, 0.14, 1.06), wrist_end_xyz=(-0.24, 0.28, 1.20),
        pole_start_xyz=(-0.34, -0.25, 1.20), pole_end_xyz=(-0.34, -0.25, 1.22),
        rotation_start_deg=(12.0, 0.0, 0.0), rotation_end_deg=(30.0, 0.0, 0.0),
        position_space="ROOT_LOCAL", clamp_reach=False,
    )
    base_r = UpperLimbSegment(
        mode="FK", start_time_sec=0.30, duration_sec=0.70,
        fk_start_deg=((0,0,0),(0,0,0),(0,0,0)), fk_end_deg=((45,0,-15),(35,0,0),(5,0,0)),
    )

    def _run_variant(seg_l: UpperLimbSegment):
        cfg, scene, root_obj, arm_obj, _, env = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
        planned_r_hands = []
        planned_feet = []
        orig_ef = KinematicBridgeExecutor.execute_frame

        @functools.wraps(orig_ef)
        def obs_ef(self, planned, *args, **kwargs):
            planned_r_hands.append({
                "hand_R": planned.hand_R.world_xyz if planned.hand_R else None,
                "fk_R": {k: v for k, v in planned.fk_joint_rotations_deg.items() if k.endswith(".R")},
            })
            planned_feet.append({
                "foot_L": planned.foot_L.world_xyz if planned.foot_L else None,
                "foot_R": planned.foot_R.world_xyz if planned.foot_R else None,
            })
            return orig_ef(self, planned, *args, **kwargs)

        KinematicBridgeExecutor.execute_frame = obs_ef
        try:
            pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
            pl.add_action(TerrainWalkAction(route=route, environment=env, action_name="T17", upper_limb_L=(seg_l,), upper_limb_R=(base_r,)))
            res = pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
        finally:
            KinematicBridgeExecutor.execute_frame = orig_ef

        wrists = []
        l_quats = []
        for st in res["states"]:
            scene.frame_set(st.frame)
            bpy.context.view_layer.update()
            wrists.append([float(v) for v in (arm_obj.matrix_world @ arm_obj.pose.bones["forearm.L"].tail)])
            l_quats.append([
                (arm_obj.matrix_world @ arm_obj.pose.bones[bn].matrix).to_3x3().normalized().to_quaternion()
                for bn in ("upper_arm.L", "forearm.L", "hand.L")
            ])
        return wrists, l_quats, planned_r_hands, planned_feet

    w0, q0, pr0, pf0 = _run_variant(base_l)
    variants = [
        ("target_position_shift", UpperLimbSegment(**{**base_l.__dict__, "wrist_end_xyz": (-0.28, 0.36, 1.30)})),
        ("start_time_shift", UpperLimbSegment(**{**base_l.__dict__, "start_time_sec": 0.65})),
        ("duration_shift", UpperLimbSegment(**{**base_l.__dict__, "duration_sec": 1.15})),
    ]
    reports = []
    for vname, vseg in variants:
        wv, qv, prv, pfv = _run_variant(vseg)
        max_wrist_delta = max((Vector(a) - Vector(b)).length for a, b in zip(w0, wv))
        max_rot_delta = max(
            _quat_angle_deg(qa, qb)
            for row_a, row_b in zip(q0, qv)
            for qa, qb in zip(row_a, row_b)
        )
        assert prv == pr0, f"{vname}: right planned target changed!"
        assert pfv == pf0, f"{vname}: lower limb plan changed!"
        assert max_wrist_delta >= 0.04 and max_rot_delta >= 5.0, f"{vname}: insufficient counterfactual change: wrist={max_wrist_delta}, rot={max_rot_delta}"
        reports.append({
            "variant": vname,
            "max_l_wrist_delta_m": max_wrist_delta,
            "max_l_bone_deg_delta": max_rot_delta,
            "right_planned_identical": True,
            "lower_limb_planned_identical": True,
        })

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({"test_id": "T17", "passed": True, "variants": reports}, fp, indent=2)


def _worker_T18_failure_propagation(out_json: str) -> None:
    _setup_sys_path(REPO_ROOT)
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    route = TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -8.0, 0.0), stand_start_frames=6, stand_stop_frames=6)
    unblocked_test_blend = os.path.join(OUTPUT_DIR, "task10d_SHOULD_NOT_EXIST_T18.blend")
    if os.path.exists(unblocked_test_blend):
        os.remove(unblocked_test_blend)

    subcases = []

    # Subcase A: Unreachable wrist target with clamp_reach=False
    cfgA, scA, rootA, armA, _, envA = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    orig_execA, wbc_clsA, wbc_recA = _install_wbc_observer(armA)
    exc_A = None
    gate_blocked_A = False
    try:
        plA = MotionPlanner(config=cfgA, armature_obj=armA, environment=envA)
        plA.add_action(TerrainWalkAction(
            route=route, environment=envA, action_name="T18_Unreachable",
            upper_limb_L=(UpperLimbSegment(
                mode="IK", start_time_sec=0.0, duration_sec=0.4,
                wrist_start_xyz=(-0.24, 0.14, 1.06),
                wrist_end_xyz=(-0.24, 1.35, 1.54),  # ~1.35m >> MAX_ARM_REACH (0.56m)
                position_space="ROOT_LOCAL", clamp_reach=False,
            ),),
        ))
        resA = plA.execute(initial_state=create_initial_motion_state(cfgA, start_frame=1, position=route.start_pos))
        _check_delivery_gate_and_save(armA, rootA, scA, 1, 12, wbc_recA, resA["states"], unblocked_test_blend)
    except Exception as exc:
        exc_A = f"{type(exc).__name__}: {exc}"
        gate_blocked_A = True
    finally:
        _restore_wbc_observer(orig_execA, wbc_clsA)

    assert exc_A is not None and gate_blocked_A and not os.path.exists(unblocked_test_blend)
    assert any((not r["success"] and not r["is_all_reachable"]) for r in wbc_recA), f"Expected real WBC reachability failure, got {wbc_recA}"
    subcases.append({
        "case": "unreachable_wrist_clamp_false",
        "exception": exc_A,
        "wbc_failure_observed": True,
        "wbc_failed_records": [r for r in wbc_recA if not r["success"]],
        "save_gate_blocked": gate_blocked_A,
        "blend_saved": os.path.exists(unblocked_test_blend),
    })

    # Subcase B: ROM-violating FK target (forearm.L hyperextension -45 deg vs min -2 deg)
    cfgB, scB, rootB, armB, _, envB = _build_flat_production_rig((0.0, -8.0, 0.0), with_inspection_env=False)
    orig_execB, wbc_clsB, wbc_recB = _install_wbc_observer(armB)
    exc_B = None
    gate_blocked_B = False
    try:
        plB = MotionPlanner(config=cfgB, armature_obj=armB, environment=envB)
        plB.add_action(TerrainWalkAction(
            route=route, environment=envB, action_name="T18_ROMViolation",
            upper_limb_L=(UpperLimbSegment(
                mode="FK", start_time_sec=0.0, duration_sec=0.4,
                fk_start_deg=((0,0,0),(0,0,0),(0,0,0)),
                fk_end_deg=((0,0,0),(-45.0,0,0),(0,0,0)),
            ),),
        ))
        resB = plB.execute(initial_state=create_initial_motion_state(cfgB, start_frame=1, position=route.start_pos))
        _check_delivery_gate_and_save(armB, rootB, scB, 1, 12, wbc_recB, resB["states"], unblocked_test_blend)
    except Exception as exc:
        exc_B = f"{type(exc).__name__}: {exc}"
        gate_blocked_B = True
    finally:
        _restore_wbc_observer(orig_execB, wbc_clsB)

    assert exc_B is not None and gate_blocked_B and not os.path.exists(unblocked_test_blend)
    assert any((not r["success"] and r["has_rom_violation"]) for r in wbc_recB), f"Expected real WBC ROM failure, got {wbc_recB}"
    subcases.append({
        "case": "rom_violating_fk_hyperextension",
        "exception": exc_B,
        "wbc_failure_observed": True,
        "wbc_failed_records": [r for r in wbc_recB if not r["success"]],
        "save_gate_blocked": gate_blocked_B,
        "blend_saved": os.path.exists(unblocked_test_blend),
    })

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({"test_id": "T18", "passed": True, "subcases": subcases}, fp, indent=2)


def _dispatch_worker(args: List[str]) -> int:
    cli = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args):
            cli[args[i][2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    task = cli["worker"]
    if task == "T01_baseline":
        _worker_T01_run("baseline", cli["out"])
    elif task == "T01_current":
        _worker_T01_run("current", cli["out"])
    elif task == "T02":
        _worker_T02_stationary_fk(cli["out"], cli["meas"])
    elif task == "T03":
        _worker_T03_bilateral_fk(cli["out"])
    elif task == "T04":
        _worker_T04_unilateral_ik(cli["out"])
    elif task == "T05":
        _worker_T05_bilateral_ik(cli["out"], cli["meas"])
    elif task == "T06_baseline":
        _worker_T06_run(False, cli["out"], None)
    elif task == "T06":
        _worker_T06_run(True, cli["out"], cli["meas"])
    elif task == "T07":
        _worker_T07_left_fk_right_ik(cli["out"])
    elif task == "T08":
        _worker_T08_left_ik_right_fk(cli["out"])
    elif task == "T09":
        _worker_T09_multisegment(cli["out"])
    elif task == "T10":
        _worker_T10_fk_ik_transition(cli["out"], cli["meas"])
    elif task == "T12":
        _worker_T12_regen_and_bug01(cli["out"])
    elif task == "T13":
        _worker_T13_invalid_rejection(cli["out"])
    elif task == "T14":
        _worker_T14_non1_start_frame(cli["out"])
    elif task == "T15":
        _worker_T15_rotation_modes(cli["out"], cli["blenda"], cli["blendb"], cli["measa"], cli["measb"])
    elif task == "T16":
        _worker_T16_keyframe_false(cli["out"])
    elif task == "T17":
        _worker_T17_counterfactuals(cli["out"])
    elif task == "T18":
        _worker_T18_failure_propagation(cli["out"])
    else:
        raise ValueError(f"Unknown worker task: {task}")
    print(f"WORKER_OK {task}")
    return 0


# =============================================================================
# COORDINATOR (runs outside Blender, invokes isolated Blender 5.1.1 processes)
# =============================================================================

def _run_subprocess(cmd: List[str], label: str, stdout_chunks: List[str], stderr_chunks: List[str], cwd: str = REPO_ROOT) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    hdr = f"\n=== [{label}] cmd: {' '.join(cmd)} (rc={proc.returncode}) ===\n"
    stdout_chunks.append(hdr + (proc.stdout or ""))
    if proc.stderr:
        stderr_chunks.append(hdr + proc.stderr)
    return proc


def _compare_t01(base_json: str, curr_json: str) -> Dict[str, Any]:
    with open(base_json, "r", encoding="utf-8") as fp:
        b = json.load(fp)
    with open(curr_json, "r", encoding="utf-8") as fp:
        c = json.load(fp)

    assert b["total_frames"] == c["total_frames"]
    assert b["schedule"] == c["schedule"], "T01 schedule mismatch"

    max_time_diff = 0.0
    max_root_pos_diff = 0.0
    max_root_mat_diff = 0.0
    max_leg_diff = 0.0
    max_arm_diff = 0.0
    max_contact_diff = 0.0
    leg_names = ("thigh.L", "shin.L", "foot.L", "thigh.R", "shin.R", "foot.R")
    arm_names = ("shoulder.L", "upper_arm.L", "forearm.L", "hand.L", "shoulder.R", "upper_arm.R", "forearm.R", "hand.R")

    for bf, cf in zip(b["frames"], c["frames"]):
        assert bf["frame"] == cf["frame"]
        max_time_diff = max(max_time_diff, abs(bf["time_sec"] - cf["time_sec"]))
        for k in range(3):
            max_root_pos_diff = max(max_root_pos_diff, abs(bf["root_world_pos"][k] - cf["root_world_pos"][k]))
        for r in range(4):
            for col in range(4):
                max_root_mat_diff = max(max_root_mat_diff, abs(bf["root_world_matrix"][r][col] - cf["root_world_matrix"][r][col]))
        max_leg_diff = max(max_leg_diff, _compare_bone_dicts(bf["bones"], cf["bones"], leg_names))
        max_arm_diff = max(max_arm_diff, _compare_bone_dicts(bf["bones"], cf["bones"], arm_names))

        assert set(bf["contacts"].keys()) == set(cf["contacts"].keys())
        for ck in bf["contacts"]:
            bc, cc = bf["contacts"][ck], cf["contacts"][ck]
            assert bc["limb"] == cc["limb"] and bc["is_locked"] == cc["is_locked"] and bc["phase"] == cc["phase"]
            for k in range(3):
                max_contact_diff = max(max_contact_diff, abs(bc["current_world_xyz"][k] - cc["current_world_xyz"][k]))
                max_contact_diff = max(max_contact_diff, abs(bc["contact_world_xyz"][k] - cc["contact_world_xyz"][k]))

    assert max_time_diff <= 1e-12
    assert max_root_pos_diff <= 1e-6 and max_root_mat_diff <= 1e-6
    assert max_leg_diff <= 1e-6 and max_arm_diff <= 1e-6 and max_contact_diff <= 1e-6

    return {
        "test_id": "T01",
        "passed": True,
        "total_frames": c["total_frames"],
        "baseline_commit": HISTORICAL_BASELINE_COMMIT,
        "baseline_module_paths": b["module_paths"],
        "current_module_paths": c["module_paths"],
        "schedule_exact_match": True,
        "max_time_diff_sec": max_time_diff,
        "max_root_pos_diff_m": max_root_pos_diff,
        "max_root_matrix_diff": max_root_mat_diff,
        "max_leg_bone_matrix_diff": max_leg_diff,
        "max_arm_bone_matrix_diff": max_arm_diff,
        "max_contact_pos_diff_m": max_contact_diff,
    }


def _compare_t06(base_json: str, walk_json: str) -> Dict[str, Any]:
    with open(base_json, "r", encoding="utf-8") as fp:
        b = json.load(fp)
    with open(walk_json, "r", encoding="utf-8") as fp:
        w = json.load(fp)

    assert b["total_frames"] == w["total_frames"]
    assert b["schedule"] == w["schedule"]
    max_root_mat_diff = 0.0
    max_leg_diff = 0.0
    max_com_delta = 0.0
    leg_names = ("pelvis", "thigh.L", "shin.L", "foot.L", "thigh.R", "shin.R", "foot.R")
    for bf, wf in zip(b["frames"], w["frames"]):
        assert bf["frame"] == wf["frame"] and abs(bf["time_sec"] - wf["time_sec"]) <= 1e-12
        for r in range(4):
            for c in range(4):
                max_root_mat_diff = max(max_root_mat_diff, abs(bf["root_world_matrix"][r][c] - wf["root_world_matrix"][r][c]))
        max_leg_diff = max(max_leg_diff, _compare_bone_dicts(bf["leg_bones"], wf["leg_bones"], leg_names))
        assert set(bf["contacts"].keys()) == set(wf["contacts"].keys())
        for fk in ("foot_L", "foot_R"):
            assert bf["contacts"][fk] == wf["contacts"][fk], f"Foot contact {fk} changed at frame {bf['frame']}: {bf['contacts'][fk]} vs {wf['contacts'][fk]}"
        for hk in ("hand_L", "hand_R"):
            hc = wf["contacts"][hk]
            assert not hc["is_locked"] and hc["phase"] in ("free", "swing"), f"Unexpected hand lock/contact at frame {wf['frame']}: {hc}"
        com_d = math.sqrt(sum((bf["com_world"][k] - wf["com_world"][k]) ** 2 for k in range(3)))
        max_com_delta = max(max_com_delta, com_d)

    assert max_root_mat_diff <= 1e-6 and max_leg_diff <= 1e-6
    assert max_com_delta > 0.001, f"Expected real physical CoM change from independent upper-limb motion, got {max_com_delta}"
    return {
        "test_id": "T06",
        "passed": True,
        "total_frames": w["total_frames"],
        "schedule_exact_match": True,
        "max_root_matrix_diff": max_root_mat_diff,
        "max_leg_bone_matrix_diff": max_leg_diff,
        "max_l_wrist_err_m": w["max_l_wrist_err_m"],
        "max_l_rot_err_deg": w["max_l_rot_err_deg"],
        "max_r_fk_err_deg": w["max_r_fk_err_deg"],
        "max_whole_body_com_delta_m": max_com_delta,
        "blend_path": os.path.abspath(DELIVERABLE_BLENDS["T06_walking_upper_limb"]),
    }


def _run_coordinator() -> int:
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []

    # 1. Verify Blender 5.1.1, Git HEAD, and frozen blobs
    ver_proc = _run_subprocess([BLENDER_EXE, "--version"], "blender_version", stdout_chunks, stderr_chunks)
    if ver_proc.returncode != 0 or "Blender 5.1.1" not in ver_proc.stdout:
        raise RuntimeError(f"Expected Blender 5.1.1, got: {ver_proc.stdout}")
    blender_version_str = ver_proc.stdout.strip()

    head_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    actual_head = head_proc.stdout.strip()
    if actual_head != EXPECTED_HEAD:
        raise RuntimeError(f"HEAD mismatch: {actual_head} != {EXPECTED_HEAD}")

    actual_blobs: Dict[str, str] = {}
    for rel_path, exp_blob in EXPECTED_BLOBS.items():
        bp = subprocess.run(["git", "hash-object", rel_path], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        blob = bp.stdout.strip()
        if blob != exp_blob:
            raise RuntimeError(f"Blob mismatch for {rel_path}: {blob} != {exp_blob}")
        actual_blobs[rel_path] = blob

    results: Dict[str, Dict[str, Any]] = {}
    all_tests_ordered = [f"T{i:02d}" for i in range(1, 19)]
    for tid in all_tests_ordered:
        results[tid] = {"test_id": tid, "status": "NOT_RUN", "passed": False}

    def _run_blender_worker(task_name: str, extra_args: List[str]) -> None:
        cmd = [
            BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1",
            "--python", THIS_FILE, "--", "--worker", task_name, *extra_args,
        ]
        p = _run_subprocess(cmd, f"worker:{task_name}", stdout_chunks, stderr_chunks)
        if p.returncode != 0:
            raise RuntimeError(f"Blender worker {task_name} failed with exit code {p.returncode}\n{p.stderr}")

    frame_measurements: Dict[str, Any] = {}
    exit_code = 0

    try:
        # T01
        b_out = os.path.join(WORK_DIR, "t01_base.json")
        c_out = os.path.join(WORK_DIR, "t01_curr.json")
        _run_blender_worker("T01_baseline", ["--out", b_out])
        _run_blender_worker("T01_current", ["--out", c_out])
        t01_res = _compare_t01(b_out, c_out)
        results["T01"] = {"status": "PASS", **t01_res}

        # T02
        t02_out = os.path.join(WORK_DIR, "t02.json")
        t02_meas = os.path.join(WORK_DIR, "meas_t02.json")
        _run_blender_worker("T02", ["--out", t02_out, "--meas", t02_meas])
        with open(t02_out, "r", encoding="utf-8") as fp:
            results["T02"] = {"status": "PASS", **json.load(fp)}
        with open(t02_meas, "r", encoding="utf-8") as fp:
            frame_measurements["T02_stationary_fk"] = json.load(fp)

        # T03
        t03_out = os.path.join(WORK_DIR, "t03.json")
        _run_blender_worker("T03", ["--out", t03_out])
        with open(t03_out, "r", encoding="utf-8") as fp:
            results["T03"] = {"status": "PASS", **json.load(fp)}

        # T04
        t04_out = os.path.join(WORK_DIR, "t04.json")
        _run_blender_worker("T04", ["--out", t04_out])
        with open(t04_out, "r", encoding="utf-8") as fp:
            results["T04"] = {"status": "PASS", **json.load(fp)}

        # T05
        t05_out = os.path.join(WORK_DIR, "t05.json")
        t05_meas = os.path.join(WORK_DIR, "meas_t05.json")
        _run_blender_worker("T05", ["--out", t05_out, "--meas", t05_meas])
        with open(t05_out, "r", encoding="utf-8") as fp:
            results["T05"] = {"status": "PASS", **json.load(fp)}
        with open(t05_meas, "r", encoding="utf-8") as fp:
            frame_measurements["T05_bilateral_ik"] = json.load(fp)

        # T06
        t06_b = os.path.join(WORK_DIR, "t06_base.json")
        t06_w = os.path.join(WORK_DIR, "t06_walk.json")
        t06_meas = os.path.join(WORK_DIR, "meas_t06.json")
        _run_blender_worker("T06_baseline", ["--out", t06_b])
        _run_blender_worker("T06", ["--out", t06_w, "--meas", t06_meas])
        results["T06"] = {"status": "PASS", **_compare_t06(t06_b, t06_w)}
        with open(t06_meas, "r", encoding="utf-8") as fp:
            frame_measurements["T06_walking_upper_limb"] = json.load(fp)

        # T07
        t07_out = os.path.join(WORK_DIR, "t07.json")
        _run_blender_worker("T07", ["--out", t07_out])
        with open(t07_out, "r", encoding="utf-8") as fp:
            results["T07"] = {"status": "PASS", **json.load(fp)}

        # T08
        t08_out = os.path.join(WORK_DIR, "t08.json")
        _run_blender_worker("T08", ["--out", t08_out])
        with open(t08_out, "r", encoding="utf-8") as fp:
            results["T08"] = {"status": "PASS", **json.load(fp)}

        # T09
        t09_out = os.path.join(WORK_DIR, "t09.json")
        _run_blender_worker("T09", ["--out", t09_out])
        with open(t09_out, "r", encoding="utf-8") as fp:
            results["T09"] = {"status": "PASS", **json.load(fp)}

        # T10
        t10_out = os.path.join(WORK_DIR, "t10.json")
        t10_meas = os.path.join(WORK_DIR, "meas_t10.json")
        _run_blender_worker("T10", ["--out", t10_out, "--meas", t10_meas])
        with open(t10_out, "r", encoding="utf-8") as fp:
            results["T10"] = {"status": "PASS", **json.load(fp)}
        with open(t10_meas, "r", encoding="utf-8") as fp:
            frame_measurements["T10_fk_ik_transition"] = json.load(fp)

        # Persist frame_measurements.json BEFORE T11 isolated reopen checks
        meas_path = os.path.join(EVIDENCE_DIR, "frame_measurements.json")
        with open(meas_path, "w", encoding="utf-8") as fp:
            json.dump(frame_measurements, fp, indent=2)

        # T11: Isolated Blender reopen verification on all 4 deliverables
        t11_assets = {}
        for skey, bpath in DELIVERABLE_BLENDS.items():
            rep_path = os.path.join(WORK_DIR, f"reopen_{skey}.json")
            cmd = [
                BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1",
                "--python", VERIFY_SAVED_SCRIPT, "--",
                "--blend", bpath,
                "--measurements", meas_path,
                "--scene-key", skey,
                "--report", rep_path,
            ]
            p = _run_subprocess(cmd, f"T11_reopen:{skey}", stdout_chunks, stderr_chunks)
            if p.returncode != 0:
                raise RuntimeError(f"T11 reopen check failed for {skey}: {p.stderr}")
            with open(rep_path, "r", encoding="utf-8") as fp:
                t11_assets[skey] = json.load(fp)
        results["T11"] = {"test_id": "T11", "status": "PASS", "passed": True, "assets": t11_assets}

        # T12
        t12_out = os.path.join(WORK_DIR, "t12.json")
        _run_blender_worker("T12", ["--out", t12_out])
        with open(t12_out, "r", encoding="utf-8") as fp:
            results["T12"] = {"status": "PASS", **json.load(fp)}

        # T13
        t13_out = os.path.join(WORK_DIR, "t13.json")
        _run_blender_worker("T13", ["--out", t13_out])
        with open(t13_out, "r", encoding="utf-8") as fp:
            results["T13"] = {"status": "PASS", **json.load(fp)}

        # T14
        t14_out = os.path.join(WORK_DIR, "t14.json")
        _run_blender_worker("T14", ["--out", t14_out])
        with open(t14_out, "r", encoding="utf-8") as fp:
            results["T14"] = {"status": "PASS", **json.load(fp)}

        # T15 (run + reopen check on both temp blends in isolated Blender processes)
        t15_out = os.path.join(WORK_DIR, "t15.json")
        tb_a = os.path.join(WORK_DIR, "t15_config_a.blend")
        tb_b = os.path.join(WORK_DIR, "t15_config_b.blend")
        ma = os.path.join(WORK_DIR, "t15_meas_a.json")
        mb = os.path.join(WORK_DIR, "t15_meas_b.json")
        _run_blender_worker("T15", ["--out", t15_out, "--blenda", tb_a, "--blendb", tb_b, "--measa", ma, "--measb", mb])
        with open(t15_out, "r", encoding="utf-8") as fp:
            t15_data = json.load(fp)
        reopen_reports = {}
        for lbl, bpath, mpath in (("config_A", tb_a, ma), ("config_B", tb_b, mb)):
            rpath = os.path.join(WORK_DIR, f"t15_reopen_{lbl}.json")
            cmd = [
                BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1",
                "--python", VERIFY_SAVED_SCRIPT, "--",
                "--blend", bpath,
                "--measurements", mpath,
                "--scene-key", lbl,
                "--report", rpath,
            ]
            p = _run_subprocess(cmd, f"T15_reopen:{lbl}", stdout_chunks, stderr_chunks)
            if p.returncode != 0:
                raise RuntimeError(f"T15 reopen check failed for {lbl}: {p.stderr}")
            with open(rpath, "r", encoding="utf-8") as fp:
                reopen_reports[lbl] = json.load(fp)
        t15_data["reopen_verification"] = reopen_reports
        t15_data["passed"] = True
        results["T15"] = {"status": "PASS", **t15_data}

        # T16
        t16_out = os.path.join(WORK_DIR, "t16.json")
        _run_blender_worker("T16", ["--out", t16_out])
        with open(t16_out, "r", encoding="utf-8") as fp:
            results["T16"] = {"status": "PASS", **json.load(fp)}

        # T17
        t17_out = os.path.join(WORK_DIR, "t17.json")
        _run_blender_worker("T17", ["--out", t17_out])
        with open(t17_out, "r", encoding="utf-8") as fp:
            results["T17"] = {"status": "PASS", **json.load(fp)}

        # T18
        t18_out = os.path.join(WORK_DIR, "t18.json")
        _run_blender_worker("T18", ["--out", t18_out])
        with open(t18_out, "r", encoding="utf-8") as fp:
            results["T18"] = {"status": "PASS", **json.load(fp)}

    except Exception as exc:
        exit_code = 1
        stderr_chunks.append(f"\n[COORDINATOR FAILURE] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n")

    # Write blend_artifacts.json for any generated deliverables
    blend_artifacts: Dict[str, Any] = {}
    for skey, bpath in DELIVERABLE_BLENDS.items():
        if os.path.exists(bpath):
            meas_entry = frame_measurements.get(skey, {})
            blend_artifacts[skey] = {
                "path": os.path.abspath(bpath),
                "relative_path": os.path.relpath(bpath, REPO_ROOT).replace("\\", "/"),
                "size_bytes": os.path.getsize(bpath),
                "sha256": _sha256_file(bpath),
                "frame_start": meas_entry.get("frame_start"),
                "frame_end": meas_entry.get("frame_end"),
                "frame_count": len(meas_entry.get("frames", [])),
            }

    with open(os.path.join(EVIDENCE_DIR, "blend_artifacts.json"), "w", encoding="utf-8") as fp:
        json.dump(blend_artifacts, fp, indent=2)

    passed_count = sum(1 for r in results.values() if r.get("passed"))
    summary_line = f"\nSUMMARY: {passed_count}/{len(all_tests_ordered)} passed, exit_code={exit_code}\n"
    stdout_chunks.append(summary_line)

    with open(os.path.join(EVIDENCE_DIR, "stdout.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stdout_chunks))
    with open(os.path.join(EVIDENCE_DIR, "stderr.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stderr_chunks))

    manifest = {
        "task_id": "TASK 10-d-4",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "branch": "task/10-d",
        "git_head": actual_head,
        "historical_baseline_commit": HISTORICAL_BASELINE_COMMIT,
        "historical_baseline_dir": BASELINE_DIR,
        "source_blobs": actual_blobs,
        "blender_executable": BLENDER_EXE,
        "blender_version": blender_version_str,
        "command": f'"{BLENDER_PYTHON}" -B docs/evidence/10-d/10-d-4/verify_production_integration.py',
        "exit_code": exit_code,
        "passed_count": passed_count,
        "total_tests": len(all_tests_ordered),
    }
    with open(os.path.join(EVIDENCE_DIR, "execution_manifest.json"), "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2)

    with open(os.path.join(EVIDENCE_DIR, "results.json"), "w", encoding="utf-8") as fp:
        json.dump({"manifest": manifest, "tests": results}, fp, indent=2)

    print(summary_line.strip())
    if exit_code != 0:
        print("FAILED - inspect stderr.log and results.json", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    if "--" in sys.argv and "--worker" in sys.argv[sys.argv.index("--") + 1 :]:
        raise SystemExit(_dispatch_worker(sys.argv[sys.argv.index("--") + 1 :]))
    raise SystemExit(_run_coordinator())
