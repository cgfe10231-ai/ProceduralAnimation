"""TASK 10-d-4 — Visual Redelivery Generator & Verifier (Blender 5.1.1).

Builds two 10.0s (240-frame @ 24fps) real-production-chain Blender scenes on the
validated DynamicsPlayground terrain corridor (Y=10.20 -> 11.40m), with
diagnostic Hand_L / Hand_R meshes, left/right color coding, front & oblique
observation cameras, strict solve-time vs post-open verification, mandatory
independent motion gates, and parameter-driven counterfactual proof:

1. output/task10d_full_body_independent_fk.blend
2. output/task10d_full_body_independent_ik.blend

All new evidence files are written strictly under:
  docs/evidence/10-d/10-d-4/visual_redelivery/
"""

from __future__ import annotations

import dataclasses
import datetime
import functools
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple


BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
BLENDER_PYTHON = r"C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe"
THIS_FILE = os.path.abspath(__file__)
REDELIVERY_DIR = os.path.dirname(THIS_FILE)
REPO_ROOT = os.path.abspath(os.path.join(REDELIVERY_DIR, "..", "..", "..", "..", ".."))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
SCRATCH_WORK = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\visual_redelivery_work"
)

EXPECTED_HEAD = "53d506d07b667327d0ed3b4b79dd2d313538877c"
FROZEN_SOURCE_BLOBS = {
    "src/motion/terrain_walk.py": "d42519fe8e39d149bdcffec3378b5f5ee7601b91",
    "src/motion/kinematic_bridge.py": "9e68e0a6a44bdb538b75b4f4d99b117c1737c358",
    "src/motion/framework.py": "31a9c268e0833a93cc0e498227202256c3274f05",
    "src/motion/whole_body_controller.py": "562de6c0ce1e9009856a7d52ec89cd6d0c012be2",
}

DELIVERABLE_FK = os.path.join(OUTPUT_DIR, "task10d_full_body_independent_fk.blend")
DELIVERABLE_IK = os.path.join(OUTPUT_DIR, "task10d_full_body_independent_ik.blend")

UPPER_LIMB_BONES = (
    "shoulder.L",
    "upper_arm.L",
    "forearm.L",
    "hand.L",
    "shoulder.R",
    "upper_arm.R",
    "forearm.R",
    "hand.R",
)
UPPER_CONTROLLERS = ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R")
UPPER_CONSTRAINTS = (
    ("ArmIK.L", "forearm.L", 'pose.bones["forearm.L"].constraints["ArmIK.L"].influence'),
    ("ArmIK.R", "forearm.R", 'pose.bones["forearm.R"].constraints["ArmIK.R"].influence'),
    ("HandRotation.L", "hand.L", 'pose.bones["hand.L"].constraints["HandRotation.L"].influence'),
    ("HandRotation.R", "hand.R", 'pose.bones["hand.R"].constraints["HandRotation.R"].influence'),
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _setup_sys_path() -> None:
    norm_repo = os.path.normpath(REPO_ROOT)
    if norm_repo not in [os.path.normpath(os.path.abspath(p)) for p in sys.path if p]:
        sys.path.insert(0, REPO_ROOT)


# =============================================================================
# NUMERICAL GEOMETRY & RELATIVE ROTATION HELPERS
# =============================================================================

def _quat_angle_rad(q1, q2) -> float:
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
    return 2.0 * math.atan2(diff_norm, sum_norm)


def _mat4_to_lists(m) -> List[List[float]]:
    return [[float(m[r][c]) for c in range(4)] for r in range(4)]


def _relative_joint_quat_and_euler(arm_obj, bone_name: str):
    """Return actual evaluated rotation of pose bone relative to its parent rest frame."""
    pb = arm_obj.pose.bones[bone_name]
    if pb.parent is not None:
        rel_rest = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
        rel_pose = pb.parent.matrix.inverted() @ pb.matrix
        local_rot_mat = rel_rest.inverted() @ rel_pose
    else:
        local_rot_mat = pb.bone.matrix_local.inverted() @ pb.matrix
    rot3 = local_rot_mat.to_3x3().normalized()
    return rot3.to_quaternion(), rot3.to_euler("XYZ")


def _max_pairwise_quat_span_deg(quats: List[Any]) -> float:
    from mathutils import Quaternion

    max_rad = 0.0
    for i in range(len(quats)):
        qi = Quaternion(quats[i])
        for j in range(i + 1, len(quats)):
            qj = Quaternion(quats[j])
            ang = _quat_angle_rad(qi, qj)
            if ang > max_rad:
                max_rad = ang
    return math.degrees(max_rad)


def _max_pairwise_pos_span_m(pts: List[List[float]]) -> float:
    max_d = 0.0
    for i in range(len(pts)):
        ax, ay, az = pts[i]
        for j in range(i + 1, len(pts)):
            bx, by, bz = pts[j]
            d = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
            if d > max_d:
                max_d = d
    return max_d


def _get_slot_fcurves(obj):
    anim = obj.animation_data
    if anim is None or anim.action is None:
        return (None, [])
    action = anim.action
    slot = getattr(anim, "action_slot", None)
    slot_id = getattr(slot, "identifier", None) if slot is not None else None
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if slot is not None and hasattr(strip, "channelbag"):
                    cb = strip.channelbag(slot)
                    if cb is not None:
                        fcurves.extend(list(cb.fcurves))
                elif hasattr(strip, "channelbags"):
                    for cb in strip.channelbags:
                        fcurves.extend(list(cb.fcurves))
    elif hasattr(action, "fcurves"):
        fcurves.extend(list(action.fcurves))
    return (slot_id, fcurves)


# =============================================================================
# DIAGNOSTIC HAND MESHES, COLORS, AND OBSERVATION CAMERAS
# =============================================================================

def _make_diagnostic_material(name: str, rgba: Tuple[float, float, float, float]):
    import bpy

    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def _build_asymmetric_hand_mesh(
    arm_obj,
    side: str,
    char_col,
    hand_mat,
    thumb_mat,
):
    """Construct asymmetric diagnostic Hand_L/Hand_R bound strictly to hand.L/hand.R."""
    import bpy
    import bmesh
    from mathutils import Matrix, Vector

    obj_name = f"Hand_{side}"
    bone_name = f"hand.{side}"
    bone = arm_obj.data.bones[bone_name]
    sign_x = -1.0 if side == "L" else 1.0

    # Build asymmetric palm + dorsal/palmar orientation wedges + protruding thumb in bmesh.
    # Coordinates defined around bone center at rest:
    #   hand.{side} head=(±0.24, 0, 0.98), tail=(±0.24, 0, 0.88) in arm/root rest space.
    bm = bmesh.new()

    # 1. Main asymmetric tapered palm block: Z in [-0.055, +0.045] around center (Z=0.93),
    #    wider anteriorly (+Y=+0.036, -Y=-0.028) and tapered radially/ulnarly so front vs back is obvious.
    palm_verts = [
        # Top (wrist end, Z = +0.045)
        bm.verts.new((sign_x * -0.015, -0.028, 0.045)),
        bm.verts.new((sign_x * 0.016, -0.028, 0.045)),
        bm.verts.new((sign_x * 0.016, 0.034, 0.045)),
        bm.verts.new((sign_x * -0.015, 0.034, 0.045)),
        # Bottom (knuckle/finger tip end, Z = -0.058), angled + narrower on -Y (little-finger side)
        bm.verts.new((sign_x * -0.011, -0.024, -0.046)),
        bm.verts.new((sign_x * 0.012, -0.024, -0.046)),
        bm.verts.new((sign_x * 0.012, 0.038, -0.062)),
        bm.verts.new((sign_x * -0.011, 0.038, -0.062)),
    ]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    for fidx in faces:
        bm.faces.new([palm_verts[i] for i in fidx])

    # 2. Protruding Thumb on the anterior (+Y) radial side so palm-normal & axial twist pop visually
    t_verts = [
        bm.verts.new((sign_x * -0.018, 0.030, 0.028)),
        bm.verts.new((sign_x * 0.008, 0.030, 0.028)),
        bm.verts.new((sign_x * 0.008, 0.072, -0.005)),
        bm.verts.new((sign_x * -0.018, 0.072, -0.005)),
        bm.verts.new((sign_x * -0.018, 0.030, 0.002)),
        bm.verts.new((sign_x * 0.008, 0.030, 0.002)),
        bm.verts.new((sign_x * 0.006, 0.068, -0.024)),
        bm.verts.new((sign_x * -0.016, 0.068, -0.024)),
    ]
    for fidx in faces:
        bm.faces.new([t_verts[i] for i in fidx])

    # 3. Distinct dorsal crest (outer side -sign_x) to distinguish dorsal vs palmar faces clearly
    d_verts = [
        bm.verts.new((sign_x * 0.016, -0.016, 0.030)),
        bm.verts.new((sign_x * 0.026, -0.008, 0.022)),
        bm.verts.new((sign_x * 0.026, 0.020, 0.022)),
        bm.verts.new((sign_x * 0.016, 0.024, 0.030)),
        bm.verts.new((sign_x * 0.013, -0.014, -0.026)),
        bm.verts.new((sign_x * 0.022, -0.006, -0.020)),
        bm.verts.new((sign_x * 0.022, 0.020, -0.020)),
        bm.verts.new((sign_x * 0.013, 0.024, -0.026)),
    ]
    for fidx in faces:
        f = bm.faces.new([d_verts[i] for i in fidx])
        f.material_index = 1

    mesh = bpy.data.meshes.new(obj_name)
    bm.to_mesh(mesh)
    bm.free()

    hand_obj = bpy.data.objects.new(obj_name, mesh)
    hand_obj.data.materials.append(hand_mat)
    hand_obj.data.materials.append(thumb_mat)
    char_col.objects.link(hand_obj)

    # Rest world transform at midpoint of hand.{side}: (arm_world) * ((head + tail)/2)
    rest_mid_local = 0.5 * (bone.head_local + bone.tail_local)
    rest_world_matrix = arm_obj.matrix_world @ Matrix.Translation(rest_mid_local)

    # Exact BONE-parent binding matching src/rig/builder.py bind_character_to_rig()
    bone_rest_tail_world = (
        arm_obj.matrix_world
        @ Matrix.Translation(bone.tail_local - bone.head_local)
        @ bone.matrix_local
    )
    hand_obj.parent = arm_obj
    hand_obj.parent_type = "BONE"
    hand_obj.parent_bone = bone_name
    hand_obj.matrix_parent_inverse = bone_rest_tail_world.inverted() @ rest_world_matrix
    hand_obj.location = Vector((0.0, 0.0, 0.0))
    hand_obj.rotation_euler = (0.0, 0.0, 0.0)
    hand_obj.scale = Vector((1.0, 1.0, 1.0))
    hand_obj.animation_data_clear()
    return hand_obj


def _assemble_visual_terrain_scene():
    """Assemble real playground terrain, 19-bone character rig, diagnostic hands, colors & cameras."""
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
    bpy.context.view_layer.update()

    # Diagnostic left vs right upper-limb colors + asymmetric Hand_L / Hand_R
    mat_left = _make_diagnostic_material("VisualDiag_LeftArm", (0.12, 0.56, 0.96, 1.0))
    mat_right = _make_diagnostic_material("VisualDiag_RightArm", (0.96, 0.42, 0.12, 1.0))
    mat_dorsal = _make_diagnostic_material("VisualDiag_HandDorsalAccent", (0.95, 0.92, 0.18, 1.0))

    for pname in ("UpperArm_L", "LowerArm_L"):
        pobj = bpy.data.objects[pname]
        pobj.data.materials.clear()
        pobj.data.materials.append(mat_left)
    for pname in ("UpperArm_R", "LowerArm_R"):
        pobj = bpy.data.objects[pname]
        pobj.data.materials.clear()
        pobj.data.materials.append(mat_right)

    char_col = bpy.data.collections["Character"]
    hand_l = _build_asymmetric_hand_mesh(arm_obj, "L", char_col, mat_left, mat_dorsal)
    hand_r = _build_asymmetric_hand_mesh(arm_obj, "R", char_col, mat_right, mat_dorsal)

    # Front & oblique-side cameras framed across corridor Y in [10.20, 11.40], full body visible
    cam_col = bpy.data.collections.get("VisualRedelivery_Cameras")
    if cam_col is None:
        cam_col = bpy.data.collections.new("VisualRedelivery_Cameras")
        scene.collection.children.link(cam_col)

    cam_specs = {
        "Visual_FrontCam": {
            "location": (0.0, 15.60, 1.45),
            "look_at": (0.0, 10.75, 1.02),
            "lens": 30.0,
        },
        "Visual_ObliqueSideCam": {
            "location": (3.85, 14.55, 2.05),
            "look_at": (0.0, 10.75, 1.02),
            "lens": 28.0,
        },
    }
    cameras = {}
    for cname, spec in cam_specs.items():
        cdata = bpy.data.cameras.new(cname)
        cdata.lens = spec["lens"]
        cdata.clip_start = 0.05
        cdata.clip_end = 200.0
        cobj = bpy.data.objects.new(cname, cdata)
        loc = Vector(spec["location"])
        tgt = Vector(spec["look_at"])
        cobj.location = loc
        cobj.rotation_mode = "XYZ"
        cobj.rotation_euler = (tgt - loc).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
        cam_col.objects.link(cobj)
        cameras[cname] = cobj

    scene.camera = cameras["Visual_ObliqueSideCam"]
    bpy.context.view_layer.update()

    return cfg, scene, root_obj, arm_obj, hand_l, hand_r, env


# =============================================================================
# LIVE SOLVE-TIME TELEMETRY CAPTURE (NO frame_set, NO re-solve)
# =============================================================================

def _capture_live_solve_sample(arm_obj, root_obj, frame: int) -> Dict[str, Any]:
    """Read actual Blender evaluated transforms directly after Bridge/WBC frame execution."""
    import bpy

    # Note: WholeBodyController.execute_frame() already ran bpy.context.view_layer.update()
    # before Phase 6 keyframe_insert(). Do NOT call scene.frame_set() or view_layer.update()
    # after keyframe_insert(), which would re-evaluate the Action at scene.frame_current=1.

    root_mat = root_obj.matrix_world.copy()
    root_inv = root_mat.inverted()
    arm_mat = arm_obj.matrix_world.copy()

    bones_data: Dict[str, Any] = {}
    for bname in UPPER_LIMB_BONES:
        pb = arm_obj.pose.bones[bname]
        w_mat = arm_mat @ pb.matrix
        rel_q, rel_e = _relative_joint_quat_and_euler(arm_obj, bname)
        bones_data[bname] = {
            "world_matrix": _mat4_to_lists(w_mat),
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

    return {
        "frame": int(frame),
        "root_world_pos": [float(v) for v in root_mat.translation],
        "root_world_matrix": _mat4_to_lists(root_mat),
        "root_world_quat": [float(v) for v in root_mat.to_3x3().normalized().to_quaternion()],
        "wrist_world_L": [float(v) for v in wrist_world_L],
        "wrist_world_R": [float(v) for v in wrist_world_R],
        "wrist_root_local_L": [float(v) for v in wrist_root_local_L],
        "wrist_root_local_R": [float(v) for v in wrist_root_local_R],
        "elbow_world_L": [float(v) for v in elbow_world_L],
        "elbow_world_R": [float(v) for v in elbow_world_R],
        "elbow_pole_world_L": controllers["ElbowPole.L"]["world_pos"],
        "elbow_pole_world_R": controllers["ElbowPole.R"]["world_pos"],
        "bones": bones_data,
        "controllers": controllers,
        "influences": influences,
    }


def _install_solve_observer(arm_obj, root_obj):
    """Wrap KinematicBridgeExecutor.execute_frame to record live solve poses + planned targets + WBC."""
    from src.motion.kinematic_bridge import KinematicBridgeExecutor

    solve_frames: List[Dict[str, Any]] = []
    planned_stream: List[Dict[str, Any]] = []
    wbc_stream: List[Dict[str, Any]] = []
    orig_ef = KinematicBridgeExecutor.execute_frame

    @functools.wraps(orig_ef)
    def wrapped(self, planned, *args, **kwargs):
        res = orig_ef(self, planned, *args, **kwargs)
        live = _capture_live_solve_sample(arm_obj, root_obj, planned.frame)
        solve_frames.append(live)
        planned_stream.append({
            "frame": int(planned.frame),
            "time_seconds": float(planned.time_seconds),
            "root_position": [float(v) for v in planned.root_position],
            "foot_L": [float(v) for v in planned.foot_L.world_xyz] if planned.foot_L else None,
            "foot_R": [float(v) for v in planned.foot_R.world_xyz] if planned.foot_R else None,
            "hand_L": (
                {
                    "enabled": bool(planned.hand_L.enabled),
                    "world_xyz": [float(v) for v in planned.hand_L.world_xyz],
                    "rotation_deg": [float(v) for v in planned.hand_L.rotation_deg] if planned.hand_L.rotation_deg else None,
                    "pole_hint_world_xyz": [float(v) for v in planned.hand_L.pole_hint_world_xyz] if planned.hand_L.pole_hint_world_xyz else None,
                }
                if planned.hand_L
                else None
            ),
            "hand_R": (
                {
                    "enabled": bool(planned.hand_R.enabled),
                    "world_xyz": [float(v) for v in planned.hand_R.world_xyz],
                    "rotation_deg": [float(v) for v in planned.hand_R.rotation_deg] if planned.hand_R.rotation_deg else None,
                    "pole_hint_world_xyz": [float(v) for v in planned.hand_R.pole_hint_world_xyz] if planned.hand_R.pole_hint_world_xyz else None,
                }
                if planned.hand_R
                else None
            ),
            "fk_L": {k: [float(v) for v in val] for k, val in planned.fk_joint_rotations_deg.items() if k.endswith(".L")},
            "fk_R": {k: [float(v) for v in val] for k, val in planned.fk_joint_rotations_deg.items() if k.endswith(".R")},
        })
        wbc = res.wbc_result
        wbc_stream.append({
            "frame": int(planned.frame),
            "success": bool(res.success and wbc.success),
            "has_rom_violation": bool(wbc.has_rom_violation),
            "is_all_reachable": bool(wbc.is_all_reachable),
            "max_end_effector_error_m": float(wbc.max_end_effector_error_m),
            "unmet_constraints": [
                {"category": uc.category, "target_name": uc.target_name, "description": uc.description, "error_amount": float(uc.error_amount)}
                for uc in wbc.unmet_constraints
            ],
        })
        return res

    KinematicBridgeExecutor.execute_frame = wrapped
    return orig_ef, KinematicBridgeExecutor, solve_frames, planned_stream, wbc_stream


# =============================================================================
# MOTION METRICS & INTERVAL VERIFICATION
# =============================================================================

def _compute_side_motion_metrics(solve_frames: List[Dict[str, Any]], side: str) -> Dict[str, Any]:
    upper_quats = [f["bones"][f"upper_arm.{side}"]["rel_parent_quat"] for f in solve_frames]
    forearm_quats = [f["bones"][f"forearm.{side}"]["rel_parent_quat"] for f in solve_frames]
    hand_quats = [f["bones"][f"hand.{side}"]["rel_parent_quat"] for f in solve_frames]
    wrist_local = [f[f"wrist_root_local_{side}"] for f in solve_frames]

    return {
        "upper_arm_rel_span_deg": _max_pairwise_quat_span_deg(upper_quats),
        "forearm_rel_span_deg": _max_pairwise_quat_span_deg(forearm_quats),
        "hand_rel_span_deg": _max_pairwise_quat_span_deg(hand_quats),
        "wrist_root_local_span_m": _max_pairwise_pos_span_m(wrist_local),
    }


def _slice_interval_metrics(
    solve_frames: List[Dict[str, Any]],
    frame_lo: int,
    frame_hi: int,
) -> Dict[str, Any]:
    sub = [f for f in solve_frames if frame_lo <= f["frame"] <= frame_hi]
    root_span = _max_pairwise_pos_span_m([f["root_world_pos"] for f in sub])
    l_metrics = _compute_side_motion_metrics(sub, "L")
    r_metrics = _compute_side_motion_metrics(sub, "R")
    return {
        "frame_range": [frame_lo, frame_hi],
        "frame_count": len(sub),
        "root_world_disp_m": root_span,
        "L": l_metrics,
        "R": r_metrics,
    }


def _assert_scene_motion_gates(
    solve_frames: List[Dict[str, Any]],
    wbc_stream: List[Dict[str, Any]],
    expected_mode: str,
) -> Dict[str, Any]:
    assert len(solve_frames) == 240, f"Expected 240 frames (10.0s @ 24fps), got {len(solve_frames)}"
    failed_wbc = [r for r in wbc_stream if not r["success"]]
    assert not failed_wbc, f"WBC/Bridge failures observed: {failed_wbc[:3]}"

    full_L = _compute_side_motion_metrics(solve_frames, "L")
    full_R = _compute_side_motion_metrics(solve_frames, "R")

    for side_lbl, m in (("L", full_L), ("R", full_R)):
        assert m["upper_arm_rel_span_deg"] >= 25.0, f"{side_lbl} upper_arm span {m['upper_arm_rel_span_deg']} < 25 deg"
        assert m["forearm_rel_span_deg"] >= 25.0, f"{side_lbl} forearm span {m['forearm_rel_span_deg']} < 25 deg"
        assert m["hand_rel_span_deg"] >= 20.0, f"{side_lbl} hand span {m['hand_rel_span_deg']} < 20 deg"
        assert m["wrist_root_local_span_m"] >= 0.15, f"{side_lbl} wrist local disp {m['wrist_root_local_span_m']} < 0.15m"

    # Expected influence per mode
    exp_inf = 0.0 if expected_mode == "FK" else 1.0
    max_inf_err = 0.0
    for rec in solve_frames:
        for cname, _, _ in UPPER_CONSTRAINTS:
            max_inf_err = max(max_inf_err, abs(rec["influences"][cname] - exp_inf))
    assert max_inf_err <= 1e-6, f"Constraint influence err {max_inf_err}"

    # Validated walk timeline (stand_start=80, walk 5*16=80, stand_stop=80 -> 240 frames = 10.0s @ 24fps):
    # Interval A: frames 8..67 (0.29s..2.75s, standing, both arms actively moving)
    # Interval B: frames 81..103 (3.33s..4.25s, walking starts at 81, both arms hold specified pose/target)
    # Interval C: frames 108..154 (4.46s..6.38s, walking continues, both arms simultaneously moving)
    # Post-walk:  frames 165..235 (6.83s..9.75s, walking stopped at 161, both arms continue moving & retracting)
    iv_a = _slice_interval_metrics(solve_frames, 8, 67)
    iv_b = _slice_interval_metrics(solve_frames, 81, 103)
    iv_c = _slice_interval_metrics(solve_frames, 108, 154)
    iv_post = _slice_interval_metrics(solve_frames, 165, 235)

    # Check A: Root stationary, both arms move significantly
    assert iv_a["root_world_disp_m"] <= 1e-5, f"Interval A root moved: {iv_a['root_world_disp_m']}"
    assert iv_a["L"]["wrist_root_local_span_m"] >= 0.15 and iv_a["R"]["wrist_root_local_span_m"] >= 0.15

    # Check B: Root walks, both arms hold specified pose (FK joint angles) or target (IK root-local wrist)
    assert iv_b["root_world_disp_m"] >= 0.20, f"Interval B root did not walk: {iv_b['root_world_disp_m']}"
    if expected_mode == "FK":
        for slbl in ("L", "R"):
            assert iv_b[slbl]["upper_arm_rel_span_deg"] <= 0.05, f"Interval B {slbl} upper_arm FK drifted: {iv_b[slbl]}"
            assert iv_b[slbl]["forearm_rel_span_deg"] <= 0.05, f"Interval B {slbl} forearm FK drifted: {iv_b[slbl]}"
            assert iv_b[slbl]["hand_rel_span_deg"] <= 0.05, f"Interval B {slbl} hand FK drifted: {iv_b[slbl]}"
    else:
        assert iv_b["L"]["wrist_root_local_span_m"] <= 0.005, f"Interval B L wrist drifted during IK hold: {iv_b['L']}"
        assert iv_b["R"]["wrist_root_local_span_m"] <= 0.005, f"Interval B R wrist drifted during IK hold: {iv_b['R']}"

    # Check C: Root walks AND both arms execute independent motion simultaneously
    assert iv_c["root_world_disp_m"] >= 0.20, f"Interval C root did not walk: {iv_c['root_world_disp_m']}"
    assert iv_c["L"]["wrist_root_local_span_m"] >= 0.10 and iv_c["R"]["wrist_root_local_span_m"] >= 0.10

    # Check Post-walk: Root stationary AND both arms continue moving & retracting
    assert iv_post["root_world_disp_m"] <= 1e-5, f"Post-walk root moved: {iv_post['root_world_disp_m']}"
    assert iv_post["L"]["wrist_root_local_span_m"] >= 0.15 and iv_post["R"]["wrist_root_local_span_m"] >= 0.15

    return {
        "expected_mode": expected_mode,
        "total_frames": len(solve_frames),
        "max_influence_err": max_inf_err,
        "full_timeline_L": full_L,
        "full_timeline_R": full_R,
        "interval_A_stand_both_arms_move": iv_a,
        "interval_B_walk_both_arms_hold": iv_b,
        "interval_C_walk_both_arms_move": iv_c,
        "interval_post_walk_arms_move_and_retract": iv_post,
    }


# =============================================================================
# SCENE SPECIFICATIONS (SCENE 1: BILATERAL FK, SCENE 2: BILATERAL IK)
# =============================================================================

def _make_terrain_route():
    from src.motion.terrain_walk import TerrainRouteInput

    # Validated T06 route: 5 planned steps * 16 = 80 walk frames + 80 start + 80 stop = 240 frames (10.0s @ 24fps)
    # Frames 1..80 (0.00..3.29s): Stand; Frames 81..160 (3.33..6.63s): Walk Y=10.20->11.40; Frames 161..240 (6.67..9.96s): Stand
    return TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30,
        step_frames=16,
        stand_start_frames=80,
        stand_stop_frames=80,
    )


def _make_fk_segments():
    from src.motion.terrain_walk import UpperLimbSegment

    # Left arm (5 segments): distinct start/durations & directions vs Right
    segs_l = (
        UpperLimbSegment(
            mode="FK", start_time_sec=0.20, duration_sec=1.20,
            fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((65.0, 15.0, 30.0), (55.0, 20.0, 0.0), (25.0, 10.0, 12.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.45, duration_sec=1.35,
            fk_start_deg=((65.0, 15.0, 30.0), (55.0, 20.0, 0.0), (25.0, 10.0, 12.0)),
            fk_end_deg=((40.0, -35.0, 75.0), (105.0, -30.0, 0.0), (-30.0, -10.0, -15.0)),
        ),
        # Holds end pose across [2.80s, 4.35s], spanning walk onset (3.33s..4.35s = frames 81..104)
        UpperLimbSegment(
            mode="FK", start_time_sec=4.35, duration_sec=1.95,
            fk_start_deg=((40.0, -35.0, 75.0), (105.0, -30.0, 0.0), (-30.0, -10.0, -15.0)),
            fk_end_deg=((110.0, 25.0, 15.0), (40.0, 35.0, 0.0), (35.0, 8.0, 18.0)),
        ),
        # Post-walk independent reconfiguration
        UpperLimbSegment(
            mode="FK", start_time_sec=6.75, duration_sec=1.35,
            fk_start_deg=((110.0, 25.0, 15.0), (40.0, 35.0, 0.0), (35.0, 8.0, 18.0)),
            fk_end_deg=((35.0, -15.0, 50.0), (85.0, -10.0, 0.0), (-15.0, -8.0, -12.0)),
        ),
        # Independent retraction to rest
        UpperLimbSegment(
            mode="FK", start_time_sec=8.20, duration_sec=1.40,
            fk_start_deg=((35.0, -15.0, 50.0), (85.0, -10.0, 0.0), (-15.0, -8.0, -12.0)),
            fk_end_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),
    )

    # Right arm (5 segments): staggered start/duration, backward extension / lateral sweep / cross-chest (non-mirrored)
    segs_r = (
        UpperLimbSegment(
            mode="FK", start_time_sec=0.35, duration_sec=1.20,
            fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((-30.0, -25.0, -45.0), (70.0, -25.0, 0.0), (-35.0, -12.0, 10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.65, duration_sec=1.25,
            fk_start_deg=((-30.0, -25.0, -45.0), (70.0, -25.0, 0.0), (-35.0, -12.0, 10.0)),
            fk_end_deg=((85.0, 30.0, 15.0), (45.0, 30.0, 0.0), (30.0, 12.0, -18.0)),
        ),
        # Holds end pose across [2.90s, 4.45s], spanning walk onset (3.33s..4.45s = frames 81..107)
        UpperLimbSegment(
            mode="FK", start_time_sec=4.45, duration_sec=2.05,
            fk_start_deg=((85.0, 30.0, 15.0), (45.0, 30.0, 0.0), (30.0, 12.0, -18.0)),
            fk_end_deg=((20.0, -20.0, -95.0), (95.0, -20.0, 0.0), (-25.0, -8.0, 15.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=6.90, duration_sec=1.40,
            fk_start_deg=((20.0, -20.0, -95.0), (95.0, -20.0, 0.0), (-25.0, -8.0, 15.0)),
            fk_end_deg=((55.0, 15.0, -25.0), (30.0, 20.0, 0.0), (20.0, 5.0, -10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=8.40, duration_sec=1.35,
            fk_start_deg=((55.0, 15.0, -25.0), (30.0, 20.0, 0.0), (20.0, 5.0, -10.0)),
            fk_end_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),
    )
    return segs_l, segs_r


def _compute_hand_world_rot_for_ik_keypose(
    arm_obj,
    side: str,
    wrist_local: Tuple[float, float, float],
    pole_local: Tuple[float, float, float],
    desired_local_wrist_deg: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Derive geometrically valid world hand rotation from actual Blender 2-bone IK forearm pose."""
    import bpy
    from mathutils import Euler, Vector
    from src.rig.arm_ik import set_hand_ik_target

    root_obj = bpy.data.objects["CharacterRoot"]
    w_xyz = tuple(root_obj.matrix_world @ Vector(wrist_local))
    p_xyz = tuple(root_obj.matrix_world @ Vector(pole_local))
    set_hand_ik_target(
        arm_obj,
        side,
        world_xyz=w_xyz,
        hand_rotation_deg=None,
        pole_world_xyz=p_xyz,
        clamp_reach=False,
        influence=1.0,
    )
    bpy.context.view_layer.update()
    pb_fore = arm_obj.pose.bones[f"forearm.{side}"]
    # Compute hand rest-to-forearm relative rotation (in this rig hand.L/R is collinear with forearm.L/R -> identity,
    # compute generally from rest bone locals so it matches bone conventions strictly)
    pb_hand = arm_obj.pose.bones[f"hand.{side}"]
    rel_rest = (pb_fore.bone.matrix_local.inverted() @ pb_hand.bone.matrix_local).to_3x3().normalized()
    fore_world_rot = (arm_obj.matrix_world @ pb_fore.matrix).to_3x3().normalized()
    local_wrist_rot = Euler([math.radians(a) for a in desired_local_wrist_deg], "XYZ").to_matrix()
    target_hand_world = fore_world_rot @ rel_rest @ local_wrist_rot
    e = target_hand_world.to_euler("XYZ")
    return (math.degrees(e.x), math.degrees(e.y), math.degrees(e.z))


def _make_ik_segments(variant: str = "nominal"):
    import bpy
    from src.motion.terrain_walk import UpperLimbSegment
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.arm_ik import setup_arm_ik

    # Keyposes constructed strictly within [MIN_ARM_REACH=0.08, MAX_ARM_REACH=0.56] around shoulders
    # and validated against real rig forearm geometry in an isolated probe before building segments.
    if variant == "nominal":
        l1_start_t, l1_dur = 0.20, 1.20
        l1_end_w = (-0.22, 0.36, 1.26)
        l2_end_w = (-0.48, 0.16, 1.38)
    else:
        l1_start_t, l1_dur = 0.40, 1.05
        l1_end_w = (-0.16, 0.34, 1.38)
        l2_end_w = (-0.44, 0.22, 1.48)

    # Waypoints: (wrist_local, pole_local, desired_anatomical_wrist_deg_within_hand_ROM)
    # hand.L/R ROM: X[-60, 70], Y[-20, 20], Z[-30, 30]
    kp_L = [
        ((-0.24, 0.08, 1.04), (-0.32, -0.24, 1.20), (-5.0, 0.0, 0.0)),
        (l1_end_w, (-0.34, -0.20, 1.25), (32.0, 10.0, 14.0)),
        (l2_end_w, (-0.44, -0.22, 1.22), (-28.0, -10.0, -16.0)),
        ((-0.18, 0.32, 1.14), (-0.32, -0.24, 1.18), (28.0, 10.0, 12.0)),
        ((-0.28, 0.26, 1.54), (-0.38, -0.18, 1.26), (-22.0, -8.0, -14.0)),
        ((-0.24, 0.08, 1.04), (-0.32, -0.24, 1.20), (-5.0, 0.0, 0.0)),
    ]
    kp_R = [
        ((0.24, 0.08, 1.04), (0.32, -0.24, 1.20), (-5.0, 0.0, 0.0)),
        ((0.48, 0.14, 1.24), (0.42, -0.22, 1.18), (30.0, -10.0, -15.0)),
        ((0.26, 0.28, 1.52), (0.36, -0.18, 1.24), (-26.0, 10.0, 16.0)),
        ((0.20, 0.34, 1.16), (0.32, -0.24, 1.18), (26.0, -8.0, -12.0)),
        ((0.46, 0.18, 1.36), (0.44, -0.20, 1.22), (-20.0, 8.0, 12.0)),
        ((0.24, 0.08, 1.04), (0.32, -0.24, 1.20), (-5.0, 0.0, 0.0)),
    ]

    # Solve exact hand world orientations in a temporary isolated probe scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pcfg = PipelineConfig()
    pparts = build_character(pcfg)
    proot = bpy.data.objects["CharacterRoot"]
    proot.location = (0.0, 10.20, 0.0)
    parm = build_rig(pcfg, character_root=proot)
    bind_character_to_rig(parm, pparts)
    setup_arm_ik(parm)
    # Account for typical uphill pelvis drop (~0.06m) via midpoint shoulder height probe
    parm.pose.bones["pelvis"].location = (0.0, -0.05, 0.0)
    rot_L = [_compute_hand_world_rot_for_ik_keypose(parm, "L", w, p, r) for w, p, r in kp_L]
    rot_R = [_compute_hand_world_rot_for_ik_keypose(parm, "R", w, p, r) for w, p, r in kp_R]

    times_L = [(l1_start_t, l1_dur), (1.45, 1.35), (4.35, 1.95), (6.75, 1.35), (8.20, 1.40)]
    times_R = [(0.35, 1.20), (1.65, 1.25), (4.45, 2.05), (6.90, 1.40), (8.40, 1.35)]

    segs_l = tuple(
        UpperLimbSegment(
            mode="IK",
            start_time_sec=times_L[i][0],
            duration_sec=times_L[i][1],
            wrist_start_xyz=kp_L[i][0],
            wrist_end_xyz=kp_L[i + 1][0],
            pole_start_xyz=kp_L[i][1],
            pole_end_xyz=kp_L[i + 1][1],
            rotation_start_deg=rot_L[i],
            rotation_end_deg=rot_L[i + 1],
            position_space="ROOT_LOCAL",
            clamp_reach=False,
        )
        for i in range(5)
    )
    segs_r = tuple(
        UpperLimbSegment(
            mode="IK",
            start_time_sec=times_R[i][0],
            duration_sec=times_R[i][1],
            wrist_start_xyz=kp_R[i][0],
            wrist_end_xyz=kp_R[i + 1][0],
            pole_start_xyz=kp_R[i][1],
            pole_end_xyz=kp_R[i + 1][1],
            rotation_start_deg=rot_R[i],
            rotation_end_deg=rot_R[i + 1],
            position_space="ROOT_LOCAL",
            clamp_reach=False,
        )
        for i in range(5)
    )
    return segs_l, segs_r


# =============================================================================
# BLENDER WORKER ENTRYPOINTS
# =============================================================================

def _worker_generate_scene(mode: str, variant: str, blend_out: Optional[str], dump_json: str) -> None:
    import bpy
    _setup_sys_path()
    from src.motion.terrain_walk import TerrainWalkAction, plan_terrain_footsteps
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    if mode == "FK":
        segs_l, segs_r = _make_fk_segments()
    elif mode == "IK":
        segs_l, segs_r = _make_ik_segments(variant=variant)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    cfg, scene, root_obj, arm_obj, hand_l, hand_r, env = _assemble_visual_terrain_scene()
    route = _make_terrain_route()
    schedule, planned_total = plan_terrain_footsteps(route, env, start_frame=1)

    orig_ef, kb_cls, solve_frames, planned_stream, wbc_stream = _install_solve_observer(arm_obj, root_obj)
    try:
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        action = TerrainWalkAction(
            route=route,
            environment=env,
            action_name=f"Task10D_FullBody_{mode}_{variant}",
            upper_limb_L=segs_l,
            upper_limb_R=segs_r,
        )
        planner.add_action(action)
        res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        kb_cls.execute_frame = orig_ef

    states = res["states"]
    motion_metrics = _assert_scene_motion_gates(solve_frames, wbc_stream, expected_mode=mode)

    # Confirm Hand_L / Hand_R bound strictly to hand.L / hand.R with zero keyframed animation
    assert hand_l.parent == arm_obj and hand_l.parent_type == "BONE" and hand_l.parent_bone == "hand.L"
    assert hand_r.parent == arm_obj and hand_r.parent_type == "BONE" and hand_r.parent_bone == "hand.R"
    assert hand_l.animation_data is None and hand_r.animation_data is None
    assert len(arm_obj.data.bones) == 19

    # Save .blend positioned at frame 1 with active oblique camera
    saved_info = None
    if blend_out is not None:
        scene.frame_start = 1
        scene.frame_end = len(states)
        scene.frame_set(1)
        bpy.context.view_layer.update()

        abs_blend = os.path.abspath(blend_out)
        os.makedirs(os.path.dirname(abs_blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=abs_blend)
        # Clean Blender backup .blend1 if created
        b1 = abs_blend + "1"
        if os.path.exists(b1):
            os.remove(b1)
        saved_info = {
            "path": abs_blend,
            "relative_path": os.path.relpath(abs_blend, REPO_ROOT).replace("\\", "/"),
            "size_bytes": os.path.getsize(abs_blend),
            "sha256": _sha256_file(abs_blend),
            "frame_start": 1,
            "frame_end": len(states),
            "frame_count": len(states),
        }

    # Also capture foot contacts from states for counterfactual verification
    contacts_stream = [
        {
            "frame": int(st.frame),
            "foot_L": {
                "is_locked": bool(st.contacts["foot_L"].is_locked),
                "phase": str(st.contacts["foot_L"].phase),
                "contact_world_xyz": [float(v) for v in st.contacts["foot_L"].contact_world_xyz],
            },
            "foot_R": {
                "is_locked": bool(st.contacts["foot_R"].is_locked),
                "phase": str(st.contacts["foot_R"].phase),
                "contact_world_xyz": [float(v) for v in st.contacts["foot_R"].contact_world_xyz],
            },
        }
        for st in states
    ]

    os.makedirs(os.path.dirname(os.path.abspath(dump_json)), exist_ok=True)
    with open(dump_json, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "mode": mode,
                "variant": variant,
                "planned_total_frames": int(planned_total),
                "schedule": [dataclasses.asdict(s) for s in schedule],
                "motion_metrics": motion_metrics,
                "saved_asset": saved_info,
                "solve_frames": solve_frames,
                "planned_stream": planned_stream,
                "contacts_stream": contacts_stream,
                "wbc_all_success": all(w["success"] for w in wbc_stream),
            },
            fp,
            indent=2,
        )


def _worker_reopen_compare(blend_path: str, solve_dump_json: str, expected_mode: str, report_json: str) -> None:
    """Reopen saved .blend in isolated Blender 5.1.1 process & verify vs solve-time poses."""
    import bpy
    from mathutils import Quaternion, Vector

    with open(solve_dump_json, "r", encoding="utf-8") as fp:
        solve_data = json.load(fp)
    solve_by_frame = {int(rec["frame"]): rec for rec in solve_data["solve_frames"]}
    frame_start = 1
    frame_end = len(solve_data["solve_frames"])

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_path))
    scene = bpy.context.scene
    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")
    hand_l = bpy.data.objects.get("Hand_L")
    hand_r = bpy.data.objects.get("Hand_R")

    assert arm_obj is not None and root_obj is not None
    assert len(arm_obj.data.bones) == 19
    assert int(scene.frame_start) == frame_start and int(scene.frame_end) == frame_end
    assert int(scene.frame_current) == 1, f"Expected .blend to open at frame 1, got {scene.frame_current}"
    assert int(scene.render.fps) == 24
    assert scene.camera is not None and scene.camera.name in ("Visual_ObliqueSideCam", "Visual_FrontCam")
    assert bpy.data.objects.get("Visual_FrontCam") is not None
    assert bpy.data.objects.get("Visual_ObliqueSideCam") is not None
    assert hand_l is not None and hand_l.parent == arm_obj and hand_l.parent_bone == "hand.L" and hand_l.animation_data is None
    assert hand_r is not None and hand_r.parent == arm_obj and hand_r.parent_bone == "hand.R" and hand_r.animation_data is None

    # Action Slot FCurve check (all 4 upper-limb constraint influences CONSTANT across 1..240)
    slot_id, fcurves = _get_slot_fcurves(arm_obj)
    assert slot_id is not None
    fc_by_path = {fc.data_path: fc for fc in fcurves}
    expected_frame_set = set(range(frame_start, frame_end + 1))
    inf_fcurve_summary = {}
    for cname, _, dp in UPPER_CONSTRAINTS:
        fc = fc_by_path.get(dp)
        assert fc is not None, f"Missing influence FCurve {dp}"
        kp_frames = {int(round(kp.co[0])) for kp in fc.keyframe_points}
        kp_interps = sorted({str(kp.interpolation) for kp in fc.keyframe_points})
        assert kp_frames == expected_frame_set
        assert kp_interps == ["CONSTANT"]
        inf_fcurve_summary[cname] = {
            "keyframe_count": len(fc.keyframe_points),
            "interpolations": kp_interps,
        }

    # Replay across Forward, Reverse, and Fixed-Seed Shuffled orders comparing strictly against
    # live solve-time measurements captured DURING Bridge/WBC execution (Section 7!).
    base_frames = list(range(frame_start, frame_end + 1))
    orders = [
        ("forward", list(base_frames)),
        ("reverse", list(reversed(base_frames))),
        ("shuffled_seed_20261126", random.Random(20261126).sample(base_frames, len(base_frames))),
    ]

    pos_tol = 1e-5
    rot_tol = 1e-4
    inf_tol = 1e-6

    traversal_reports = []
    forward_playback_samples = []
    for order_name, fseq in orders:
        max_pos_err = 0.0
        max_rot_err = 0.0
        max_inf_err = 0.0
        failures = []
        for f in fseq:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            exp = solve_by_frame[f]
            arm_mat = arm_obj.matrix_world.copy()
            root_mat = root_obj.matrix_world.copy()

            # Check positions: root, wrist L/R, elbow L/R, ElbowPole L/R
            act_wL = arm_mat @ arm_obj.pose.bones["forearm.L"].tail
            act_wR = arm_mat @ arm_obj.pose.bones["forearm.R"].tail
            act_eL = arm_mat @ arm_obj.pose.bones["upper_arm.L"].tail
            act_eR = arm_mat @ arm_obj.pose.bones["upper_arm.R"].tail
            act_pL = bpy.data.objects["ElbowPole.L"].matrix_world.translation
            act_pR = bpy.data.objects["ElbowPole.R"].matrix_world.translation

            for lbl, a_vec, e_xyz in (
                ("root_world_pos", root_mat.translation, exp["root_world_pos"]),
                ("wrist_world_L", act_wL, exp["wrist_world_L"]),
                ("wrist_world_R", act_wR, exp["wrist_world_R"]),
                ("elbow_world_L", act_eL, exp["elbow_world_L"]),
                ("elbow_world_R", act_eR, exp["elbow_world_R"]),
                ("elbow_pole_world_L", act_pL, exp["elbow_pole_world_L"]),
                ("elbow_pole_world_R", act_pR, exp["elbow_pole_world_R"]),
            ):
                perr = (a_vec - Vector(e_xyz)).length
                max_pos_err = max(max_pos_err, perr)
                if perr > pos_tol:
                    failures.append({"frame": f, "metric": lbl, "error": perr})

            # Check rotations: root, 8 upper-limb bones (world & rel-parent), 4 controllers
            rq_err = _quat_angle_rad(root_mat.to_3x3().normalized().to_quaternion(), Quaternion(exp["root_world_quat"]))
            max_rot_err = max(max_rot_err, rq_err)
            if rq_err > rot_tol:
                failures.append({"frame": f, "metric": "root_world_quat", "error": rq_err})

            for bname in UPPER_LIMB_BONES:
                pb = arm_obj.pose.bones[bname]
                wq = (arm_mat @ pb.matrix).to_3x3().normalized().to_quaternion()
                rerr = _quat_angle_rad(wq, Quaternion(exp["bones"][bname]["world_quat"]))
                max_rot_err = max(max_rot_err, rerr)
                if rerr > rot_tol:
                    failures.append({"frame": f, "metric": f"bone_world:{bname}", "error": rerr})

                rel_q, _ = _relative_joint_quat_and_euler(arm_obj, bname)
                rel_err = _quat_angle_rad(rel_q, Quaternion(exp["bones"][bname]["rel_parent_quat"]))
                max_rot_err = max(max_rot_err, rel_err)
                if rel_err > rot_tol:
                    failures.append({"frame": f, "metric": f"bone_rel:{bname}", "error": rel_err})

            for cname in UPPER_CONTROLLERS:
                cq = bpy.data.objects[cname].matrix_world.to_3x3().normalized().to_quaternion()
                cerr = _quat_angle_rad(cq, Quaternion(exp["controllers"][cname]["world_quat"]))
                max_rot_err = max(max_rot_err, cerr)
                if cerr > rot_tol:
                    failures.append({"frame": f, "metric": f"ctrl:{cname}", "error": cerr})

            for cname, bname, _ in UPPER_CONSTRAINTS:
                ival = float(arm_obj.pose.bones[bname].constraints[cname].influence)
                ierr = abs(ival - exp["influences"][cname])
                max_inf_err = max(max_inf_err, ierr)
                if ierr > inf_tol:
                    failures.append({"frame": f, "metric": f"inf:{cname}", "error": ierr})

            if order_name == "forward":
                forward_playback_samples.append({
                    "frame": f,
                    "root_world_pos": [float(v) for v in root_mat.translation],
                    "wrist_world_L": [float(v) for v in act_wL],
                    "wrist_world_R": [float(v) for v in act_wR],
                    "elbow_world_L": [float(v) for v in act_eL],
                    "elbow_world_R": [float(v) for v in act_eR],
                    "influences": {
                        cname: float(arm_obj.pose.bones[bname].constraints[cname].influence)
                        for cname, bname, _ in UPPER_CONSTRAINTS
                    },
                })

        assert not failures, f"{blend_path} ({order_name}) solve-vs-reopen mismatch: {failures[:5]}"
        traversal_reports.append({
            "order": order_name,
            "frames_checked": len(fseq),
            "max_pos_err_m": max_pos_err,
            "max_rot_err_rad": max_rot_err,
            "max_inf_err": max_inf_err,
            "passed": True,
        })

    os.makedirs(os.path.dirname(os.path.abspath(report_json)), exist_ok=True)
    with open(report_json, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "passed": True,
                "blend_path": os.path.abspath(blend_path),
                "expected_mode": expected_mode,
                "open_frame": 1,
                "fps": int(scene.render.fps),
                "cameras": ["Visual_FrontCam", "Visual_ObliqueSideCam"],
                "active_camera": scene.camera.name,
                "action_slot_identifier": slot_id,
                "influence_fcurves": inf_fcurve_summary,
                "solve_vs_reopen_traversals": traversal_reports,
                "playback_key_samples_count": len(forward_playback_samples),
                "forward_playback_frames": forward_playback_samples,
            },
            fp,
            indent=2,
        )


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
    if task == "generate":
        _worker_generate_scene(
            mode=cli["mode"],
            variant=cli.get("variant", "nominal"),
            blend_out=cli.get("blend"),
            dump_json=cli["out"],
        )
    elif task == "reopen":
        _worker_reopen_compare(
            blend_path=cli["blend"],
            solve_dump_json=cli["solve"],
            expected_mode=cli["mode"],
            report_json=cli["out"],
        )
    else:
        raise ValueError(f"Unknown worker task: {task}")
    print(f"REDELIVERY_WORKER_OK {task}")
    return 0


# =============================================================================
# COORDINATOR
# =============================================================================

def _run_subprocess(cmd: List[str], label: str, stdout_chunks: List[str], stderr_chunks: List[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    hdr = f"\n=== [{label}] cmd: {' '.join(cmd)} (rc={proc.returncode}) ===\n"
    stdout_chunks.append(hdr + (proc.stdout or ""))
    if proc.stderr:
        stderr_chunks.append(hdr + proc.stderr)
    return proc


def _verify_counterfactual(nominal_json: str, cf_json: str) -> Dict[str, Any]:
    with open(nominal_json, "r", encoding="utf-8") as fp:
        nom = json.load(fp)
    with open(cf_json, "r", encoding="utf-8") as fp:
        cf = json.load(fp)

    assert nom["schedule"] == cf["schedule"], "Lower-limb terrain schedule changed!"
    assert nom["contacts_stream"] == cf["contacts_stream"], "Foot contact contracts changed!"
    assert len(nom["planned_stream"]) == len(cf["planned_stream"])

    max_right_target_diff = 0.0
    max_foot_target_diff = 0.0
    max_root_diff = 0.0
    max_left_wrist_diff = 0.0
    max_left_bone_diff_deg = 0.0

    for pn, pc, sn, sc in zip(nom["planned_stream"], cf["planned_stream"], nom["solve_frames"], cf["solve_frames"]):
        assert pn["frame"] == pc["frame"]
        assert pn["fk_R"] == pc["fk_R"]
        assert (pn["hand_R"] is not None) and (pc["hand_R"] is not None)
        for k in range(3):
            max_root_diff = max(max_root_diff, abs(pn["root_position"][k] - pc["root_position"][k]))
            max_foot_target_diff = max(
                max_foot_target_diff,
                abs(pn["foot_L"][k] - pc["foot_L"][k]),
                abs(pn["foot_R"][k] - pc["foot_R"][k]),
            )
            max_right_target_diff = max(
                max_right_target_diff,
                abs(pn["hand_R"]["world_xyz"][k] - pc["hand_R"]["world_xyz"][k]),
                abs(pn["hand_R"]["rotation_deg"][k] - pc["hand_R"]["rotation_deg"][k]),
                abs(pn["hand_R"]["pole_hint_world_xyz"][k] - pc["hand_R"]["pole_hint_world_xyz"][k]),
            )
        w_d = math.sqrt(sum((sn["wrist_root_local_L"][k] - sc["wrist_root_local_L"][k]) ** 2 for k in range(3)))
        max_left_wrist_diff = max(max_left_wrist_diff, w_d)
        for bn in ("upper_arm.L", "forearm.L"):
            for k in range(3):
                max_left_bone_diff_deg = max(
                    max_left_bone_diff_deg,
                    abs(sn["bones"][bn]["rel_parent_euler_deg"][k] - sc["bones"][bn]["rel_parent_euler_deg"][k]),
                )

    assert max_root_diff == 0.0 and max_foot_target_diff == 0.0 and max_right_target_diff == 0.0
    assert max_left_wrist_diff >= 0.08 and max_left_bone_diff_deg >= 10.0

    return {
        "passed": True,
        "schedule_exact_match": True,
        "foot_contacts_exact_match": True,
        "max_root_planned_diff_m": max_root_diff,
        "max_foot_planned_diff_m": max_foot_target_diff,
        "max_right_arm_planned_diff": max_right_target_diff,
        "max_left_wrist_counterfactual_delta_m": max_left_wrist_diff,
        "max_left_bone_counterfactual_delta_deg": max_left_bone_diff_deg,
    }


def _run_coordinator() -> int:
    os.makedirs(SCRATCH_WORK, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(REDELIVERY_DIR, exist_ok=True)

    stdout_chunks: List[str] = []
    stderr_chunks: List[str] = []

    ver_proc = _run_subprocess([BLENDER_EXE, "--version"], "blender_version", stdout_chunks, stderr_chunks)
    if ver_proc.returncode != 0 or "Blender 5.1.1" not in ver_proc.stdout:
        raise RuntimeError(f"Expected Blender 5.1.1, got: {ver_proc.stdout}")

    actual_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if actual_head != EXPECTED_HEAD:
        raise RuntimeError(f"HEAD mismatch: {actual_head} != {EXPECTED_HEAD}")

    actual_blobs = {}
    for rp, eb in FROZEN_SOURCE_BLOBS.items():
        b = subprocess.run(["git", "hash-object", rp], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if b != eb:
            raise RuntimeError(f"Blob mismatch {rp}: {b} != {eb}")
        actual_blobs[rp] = b

    def _run_blender(label: str, args: List[str]) -> None:
        cmd = [BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1", "--python", THIS_FILE, "--", *args]
        p = _run_subprocess(cmd, label, stdout_chunks, stderr_chunks)
        if p.returncode != 0:
            raise RuntimeError(f"Blender job '{label}' failed (rc={p.returncode})\n{p.stderr}")

    exit_code = 0
    report: Dict[str, Any] = {}
    solve_poses_archive: Dict[str, Any] = {}

    try:
        # 1. Generate Scene 1 (Bilateral FK) + Capture Solve-Time Poses
        fk_solve_json = os.path.join(SCRATCH_WORK, "fk_solve.json")
        _run_blender("generate_fk_scene", ["--worker", "generate", "--mode", "FK", "--variant", "nominal", "--blend", DELIVERABLE_FK, "--out", fk_solve_json])

        # 2. Reopen Scene 1 in isolated Blender process & verify against solve-time poses
        fk_reopen_json = os.path.join(SCRATCH_WORK, "fk_reopen.json")
        _run_blender("reopen_fk_scene", ["--worker", "reopen", "--mode", "FK", "--blend", DELIVERABLE_FK, "--solve", fk_solve_json, "--out", fk_reopen_json])

        # 3. Generate Scene 2 (Bilateral IK) + Capture Solve-Time Poses
        ik_solve_json = os.path.join(SCRATCH_WORK, "ik_solve.json")
        _run_blender("generate_ik_scene", ["--worker", "generate", "--mode", "IK", "--variant", "nominal", "--blend", DELIVERABLE_IK, "--out", ik_solve_json])

        # 4. Reopen Scene 2 in isolated Blender process & verify against solve-time poses
        ik_reopen_json = os.path.join(SCRATCH_WORK, "ik_reopen.json")
        _run_blender("reopen_ik_scene", ["--worker", "reopen", "--mode", "IK", "--blend", DELIVERABLE_IK, "--solve", ik_solve_json, "--out", ik_reopen_json])

        # 5. Parameter-driven Counterfactual Proof on same terrain route (Left IK target/timing varied)
        cf_solve_json = os.path.join(SCRATCH_WORK, "ik_cf_solve.json")
        _run_blender("counterfactual_ik_left", ["--worker", "generate", "--mode", "IK", "--variant", "counterfactual_L", "--out", cf_solve_json])
        cf_report = _verify_counterfactual(ik_solve_json, cf_solve_json)

        with open(fk_solve_json, "r", encoding="utf-8") as fp:
            fk_solve = json.load(fp)
        with open(fk_reopen_json, "r", encoding="utf-8") as fp:
            fk_reopen = json.load(fp)
        with open(ik_solve_json, "r", encoding="utf-8") as fp:
            ik_solve = json.load(fp)
        with open(ik_reopen_json, "r", encoding="utf-8") as fp:
            ik_reopen = json.load(fp)

        fk_playback_frames = fk_reopen.pop("forward_playback_frames")
        ik_playback_frames = ik_reopen.pop("forward_playback_frames")
        with open(os.path.join(REDELIVERY_DIR, "reopen_playback_poses.json"), "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "task10d_full_body_independent_fk": fk_playback_frames,
                    "task10d_full_body_independent_ik": ik_playback_frames,
                },
                fp,
                indent=2,
            )

        solve_poses_archive = {
            "task10d_full_body_independent_fk": {
                "frame_count": len(fk_solve["solve_frames"]),
                "frames": fk_solve["solve_frames"],
            },
            "task10d_full_body_independent_ik": {
                "frame_count": len(ik_solve["solve_frames"]),
                "frames": ik_solve["solve_frames"],
            },
        }
        with open(os.path.join(REDELIVERY_DIR, "solve_time_poses.json"), "w", encoding="utf-8") as fp:
            json.dump(solve_poses_archive, fp, indent=2)

        assets = {
            "task10d_full_body_independent_fk": fk_solve["saved_asset"],
            "task10d_full_body_independent_ik": ik_solve["saved_asset"],
        }
        with open(os.path.join(REDELIVERY_DIR, "blend_artifacts.json"), "w", encoding="utf-8") as fp:
            json.dump(assets, fp, indent=2)

        report = {
            "task_id": "TASK 10-d-4 Visual Redelivery",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_head": actual_head,
            "source_blobs": actual_blobs,
            "blender_executable": BLENDER_EXE,
            "command": f'"{BLENDER_PYTHON}" -B docs/evidence/10-d/10-d-4/visual_redelivery/generate_visual_redelivery.py',
            "passed": True,
            "scene_1_fk": {
                "asset": fk_solve["saved_asset"],
                "motion_metrics": fk_solve["motion_metrics"],
                "reopen_verification": fk_reopen,
            },
            "scene_2_ik": {
                "asset": ik_solve["saved_asset"],
                "motion_metrics": ik_solve["motion_metrics"],
                "reopen_verification": ik_reopen,
            },
            "parameter_driven_counterfactual": cf_report,
        }
        with open(os.path.join(REDELIVERY_DIR, "motion_report.json"), "w", encoding="utf-8") as fp:
            json.dump(report, fp, indent=2)

    except Exception as exc:
        exit_code = 1
        stderr_chunks.append(f"\n[REDELIVERY FAILURE] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n")

    stdout_chunks.append(f"\nREDELIVERY_SUMMARY exit_code={exit_code}\n")
    with open(os.path.join(REDELIVERY_DIR, "stdout.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stdout_chunks))
    with open(os.path.join(REDELIVERY_DIR, "stderr.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(stderr_chunks))

    print(f"REDELIVERY_SUMMARY exit_code={exit_code}")
    if exit_code != 0:
        print("FAILED - inspect visual_redelivery/stderr.log", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    if "--" in sys.argv and "--worker" in sys.argv[sys.argv.index("--") + 1 :]:
        raise SystemExit(_dispatch_worker(sys.argv[sys.argv.index("--") + 1 :]))
    raise SystemExit(_run_coordinator())
