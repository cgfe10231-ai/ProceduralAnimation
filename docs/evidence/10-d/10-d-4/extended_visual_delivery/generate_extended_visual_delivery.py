"""TASK 10-d-4 — Extended Bilateral & Long-Duration Visual Delivery (Blender 5.1.1).

Reuses visual_redelivery/generate_visual_redelivery.py (unchanged) to build and
verify two extended procedural animation scenes strictly through the frozen
production pipeline (TerrainWalkAction -> MotionPlanner -> KinematicBridgeExecutor
-> WholeBodyController -> Rig FK/IK):

1. Scene 3: output/task10d_complex_bilateral_motion.blend
   - 24 FPS, 480 frames (20.0s)
   - >= 16 non-zero effective motion segments per side
   - Covers FK+FK, FK+IK, IK+IK, IK+FK on one continuous timeline
   - Both sides execute >= 1 FK -> IK -> FK cycle at staggered switch times
   - Pre-solved mode-switch endpoints (no bone overrides)

2. Scene 4: output/task10d_long_continuous_motion.blend
   - 24 FPS, 1440 frames (60.0s)
   - Full Task 7A-2 Course B terrain route (0.0, 10.20, 0.0) -> (0.0, 22.40, 0.0)
   - 936 walking frames (65.0% >= 50%) + 216 start stand + 288 stop stand = 1440 frames
   - >= 40 non-zero effective motion segments per side (>= 75% active duration)
   - Distinct motion combinations every 10s, staggered FK/IK switches, walking holds &
     recovery, post-walk continuous upper-limb motion, Root-following camera, markers

All new files live strictly under:
  docs/evidence/10-d/10-d-4/extended_visual_delivery/
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import importlib.util
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
EXTENDED_DIR = os.path.dirname(THIS_FILE)
REPO_ROOT = os.path.abspath(os.path.join(EXTENDED_DIR, "..", "..", "..", "..", ".."))
REDELIVERY_SCRIPT = os.path.abspath(
    os.path.join(EXTENDED_DIR, "..", "visual_redelivery", "generate_visual_redelivery.py")
)
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")
SCRATCH_WORK = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\extended_visual_work"
)

EXPECTED_HEAD = "0570d21c69e84811cdb01f154aa1a1c1151a6047"
EXPECTED_REUSED_BLOB = "d3d0f0e521dc0ce20d0a013608346b3c5caa8d30"
FROZEN_SOURCE_BLOBS = {
    "src/motion/terrain_walk.py": "d42519fe8e39d149bdcffec3378b5f5ee7601b91",
    "src/motion/kinematic_bridge.py": "9e68e0a6a44bdb538b75b4f4d99b117c1737c358",
    "src/motion/framework.py": "31a9c268e0833a93cc0e498227202256c3274f05",
    "src/motion/whole_body_controller.py": "562de6c0ce1e9009856a7d52ec89cd6d0c012be2",
}

DELIVERABLE_SCENE3 = os.path.join(OUTPUT_DIR, "task10d_complex_bilateral_motion.blend")
DELIVERABLE_SCENE4 = os.path.join(OUTPUT_DIR, "task10d_long_continuous_motion.blend")


def _load_vr():
    spec = importlib.util.spec_from_file_location("visual_redelivery_mod", REDELIVERY_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def _extract_bone_local_fk_deg(arm_obj, side: str) -> Tuple[Tuple[float, float, float], ...]:
    out = []
    for bname in (f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}"):
        pb = arm_obj.pose.bones[bname]
        if pb.parent is not None:
            rel_rest = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
            rel_pose = pb.parent.matrix.inverted() @ pb.matrix
            local_rot_mat = rel_rest.inverted() @ rel_pose
        else:
            local_rot_mat = pb.bone.matrix_local.inverted() @ pb.matrix
        e = local_rot_mat.to_3x3().normalized().to_euler("XYZ")
        out.append((math.degrees(e.x), math.degrees(e.y), math.degrees(e.z)))
    return tuple(out)


def _extract_ik_endpoint_from_live_arm(arm_obj, root_obj, side: str):
    from mathutils import Vector

    root_inv = root_obj.matrix_world.inverted()
    arm_w = arm_obj.matrix_world
    shoulder = root_inv @ (arm_w @ arm_obj.pose.bones[f"upper_arm.{side}"].head)
    elbow = root_inv @ (arm_w @ arm_obj.pose.bones[f"upper_arm.{side}"].tail)
    wrist = root_inv @ (arm_w @ arm_obj.pose.bones[f"forearm.{side}"].tail)

    sw = (wrist - shoulder)
    if sw.length > 1e-6:
        sw_dir = sw.normalized()
        se = elbow - shoulder
        perp = se - sw_dir * se.dot(sw_dir)
        pole_dir = perp.normalized() if perp.length > 1e-4 else Vector((-0.25 if side == "L" else 0.25, -0.8, 0.0)).normalized()
    else:
        pole_dir = Vector((-0.25 if side == "L" else 0.25, -0.8, 0.0)).normalized()
    pole_local = elbow + 0.30 * pole_dir

    pb_hand = arm_obj.pose.bones[f"hand.{side}"]
    hand_e = (arm_w @ pb_hand.matrix).to_3x3().normalized().to_euler("XYZ")
    return (
        tuple(float(v) for v in wrist),
        tuple(float(v) for v in pole_local),
        (math.degrees(hand_e.x), math.degrees(hand_e.y), math.degrees(hand_e.z)),
    )


def _add_timeline_markers(scene, markers: List[Tuple[str, int]]) -> None:
    scene.timeline_markers.clear()
    for name, frame in markers:
        scene.timeline_markers.new(name, frame=int(frame))


def _attach_root_follow_camera(scene, root_obj, cam_obj) -> None:
    """Follow CharacterRoot translation cleanly without modifying CharacterRoot or controllers."""
    import bpy
    from mathutils import Vector

    cam_col = bpy.data.collections.get("VisualRedelivery_Cameras")
    if cam_col is None:
        cam_col = bpy.data.collections.new("VisualRedelivery_Cameras")
        scene.collection.children.link(cam_col)

    pivot = bpy.data.objects.new("Camera_RootFollow_Pivot", None)
    pivot.empty_display_type = "PLAIN_AXES"
    pivot.empty_display_size = 0.05
    pivot.location = root_obj.matrix_world.translation.copy()
    cam_col.objects.link(pivot)

    con = pivot.constraints.new("COPY_LOCATION")
    con.target = root_obj
    con.use_x = True
    con.use_y = True
    con.use_z = True

    cam_obj.parent = pivot
    offset_loc = Vector((4.20, 4.40, 2.25))
    look_target = Vector((0.0, 0.15, 1.00))
    cam_obj.location = offset_loc
    cam_obj.rotation_mode = "XYZ"
    cam_obj.rotation_euler = (look_target - offset_loc).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
    cam_obj.data.lens = 26.0

    # Also keep FrontCam following Root along -Y so front view stays framed across 12.2m walk
    front_cam = bpy.data.objects.get("Visual_FrontCam")
    if front_cam is not None:
        front_cam.parent = pivot
        f_off = Vector((0.0, 5.20, 1.48))
        f_look = Vector((0.0, 0.0, 1.00))
        front_cam.location = f_off
        front_cam.rotation_mode = "XYZ"
        front_cam.rotation_euler = (f_look - f_off).normalized().to_track_quat("-Z", "Y").to_euler("XYZ")
        front_cam.data.lens = 28.0


# =============================================================================
# DETERMINISTIC NON-PERIODIC TRAJECTORY GENERATORS (FK & IK)
# =============================================================================

def _clamp_fk_triplet(side: str, ua: Tuple[float, float, float], fa: Tuple[float, float, float], hd: Tuple[float, float, float]):
    # Strict safety margins well inside DEFAULT_HUMANOID_ROM_MODEL bounds
    ua_x = max(-38.0, min(125.0, ua[0]))
    ua_y = max(-45.0, min(45.0, ua[1]))
    if side == "L":
        ua_z = max(-18.0, min(110.0, ua[2]))
    else:
        ua_z = max(-110.0, min(18.0, ua[2]))
    # Keep elliptical cone safe: ensure sqrt((pitch/160)^2 + (yaw/150)^2) <= 0.85
    scale = math.hypot(ua_x / 160.0, ua_z / 150.0)
    if scale > 0.82:
        ua_x *= 0.82 / scale
        ua_z *= 0.82 / scale

    fa_x = max(8.0, min(118.0, fa[0]))
    fa_y = max(-50.0, min(50.0, fa[1]))
    hd_x = max(-40.0, min(45.0, hd[0]))
    hd_y = max(-12.0, min(12.0, hd[1]))
    hd_z = max(-20.0, min(20.0, hd[2]))
    return ((ua_x, ua_y, ua_z), (fa_x, fa_y, 0.0), (hd_x, hd_y, hd_z))


def _clamp_ik_waypoint(side: str, w_xyz: Tuple[float, float, float], p_xyz: Tuple[float, float, float], r_deg: Tuple[float, float, float]):
    sx = -1.0 if side == "L" else 1.0
    sh = (0.24 * sx, 0.0, 1.46)
    dx, dy, dz = w_xyz[0] - sh[0], w_xyz[1] - sh[1], w_xyz[2] - sh[2]
    d = math.sqrt(dx * dx + dy * dy + dz * dz)
    # Keep strictly inside [0.22, 0.48] so reach <= 0.56m even under max pelvis drop/torso lean
    if d < 0.27:
        f = 0.27 / max(d, 1e-6)
        dx, dy, dz = dx * f, dy * f, dz * f
    elif d > 0.40:
        f = 0.40 / d
        dx, dy, dz = dx * f, dy * f, dz * f
    cw = (
        sx * max(0.12, min(0.48, sx * (sh[0] + dx))),
        max(0.04, sh[1] + dy),
        max(1.04, min(1.56, sh[2] + dz)),
    )
    cp = (
        sx * max(0.24, min(0.46, sx * p_xyz[0])),
        min(-0.20, p_xyz[1]),
        max(1.04, min(1.24, p_xyz[2])),
    )
    cr = (max(-26.0, min(30.0, r_deg[0])), max(-4.0, min(4.0, r_deg[1])), max(-9.0, min(9.0, r_deg[2])))
    return cw, cp, cr


def _generate_fk_pose_sample(side: str, idx: int, phase_bias: float) -> Tuple[Tuple[float, float, float], ...]:
    """Generate rich, non-periodic, non-mirrored FK posture well inside joint ROM."""
    s = 1.0 if side == "L" else -1.0
    t = idx * 1.17 + phase_bias
    ua_x = 42.0 + 48.0 * math.sin(t * 1.13) + 22.0 * math.cos(t * 1.79)
    ua_y = 28.0 * math.sin(t * 1.41 + 0.7 * s) + 10.0 * math.cos(t * 2.13)
    if side == "L":
        ua_z = 38.0 + 42.0 * math.sin(t * 0.91 + 0.4) + 16.0 * math.cos(t * 1.63)
    else:
        ua_z = -42.0 - 42.0 * math.cos(t * 0.97 - 0.3) + 16.0 * math.sin(t * 1.71)
    fa_x = 58.0 + 42.0 * math.sin(t * 1.29 + 1.1) + 12.0 * math.cos(t * 2.07)
    fa_y = 32.0 * math.cos(t * 1.53 + 0.5)
    hd_x = 30.0 * math.sin(t * 1.67 + 0.3)
    hd_y = 9.0 * math.cos(t * 1.91 + 0.8)
    hd_z = 15.0 * math.sin(t * 1.37 - 0.6)
    return _clamp_fk_triplet(side, (ua_x, ua_y, ua_z), (fa_x, fa_y, 0.0), (hd_x, hd_y, hd_z))


def _generate_ik_waypoint_sample(side: str, idx: int, phase_bias: float):
    """Generate rich, non-periodic, multi-directional IK waypoint (anterior/lateral/posterior/up/down)."""
    sx = -1.0 if side == "L" else 1.0
    t = idx * 1.23 + phase_bias
    # Multi-directional workspace sweeps: lateral outward, cross-body, anterior reach, slight posterior, elevation/drop
    wx = sx * (0.28 + 0.16 * math.sin(t * 1.07) - 0.06 * math.cos(t * 1.81))
    wy = 0.16 + 0.22 * math.sin(t * 1.31 + 0.6) + 0.06 * math.cos(t * 2.09)
    wz = 1.30 + 0.22 * math.cos(t * 0.89 + 0.4 * sx) + 0.08 * math.sin(t * 1.73)

    # Distinct elbow pole changes per side
    px = sx * (0.36 + 0.10 * math.cos(t * 1.19))
    py = -0.22 - 0.06 * abs(math.sin(t * 1.43))
    pz = 1.22 + 0.10 * math.sin(t * 1.11 + 0.9)

    # Multi-axis local wrist target (mapped later to exact forearm world orientation!)
    rx = 26.0 * math.sin(t * 1.57 + 0.5)
    ry = 9.0 * math.cos(t * 1.83 - 0.4)
    rz = 14.0 * math.sin(t * 1.27 + 1.2)
    return _clamp_ik_waypoint(side, (wx, wy, wz), (px, py, pz), (rx, ry, rz))


def _solve_verified_ik_segments(
    vr,
    arm_pose_root_xyz: Tuple[float, float, float],
    pelvis_dz: float,
    side: str,
    start_state: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]],
    spans: List[Tuple[float, float]],
    raw_waypoints: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]],
):
    """Build IK UpperLimbSegments sequentially, verifying every midpoint against real Rig IK & ROM."""
    import bpy
    from mathutils import Euler, Vector
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.arm_ik import setup_arm_ik, set_hand_ik_target
    from src.motion.terrain_walk import UpperLimbSegment
    from src.motion.joint_limits import DEFAULT_HUMANOID_ROM_MODEL, extract_evaluated_bone_rotation_rad

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

    def _lerp3(a, b, h):
        return ((1.0 - h) * a[0] + h * b[0], (1.0 - h) * a[1] + h * b[1], (1.0 - h) * a[2] + h * b[2])

    def _wrap_near_deg(deg_xyz, ref_deg_xyz):
        return tuple(
            a + 360.0 * round((ref - a) / 360.0)
            for a, ref in zip(deg_xyz, ref_deg_xyz)
        )

    def _segment_midpoints_safe(cw, cp, cr, nw, np, nr) -> Optional[float]:
        worst_margin = 1e9
        for dz_test, spine_deg, pelvis_deg in ((0.00, 0.0, 0.0), (0.090, 10.0, -3.0), (0.075, -2.5, -4.0)):
            arm.pose.bones["pelvis"].location = (0.0, -dz_test, 0.0)
            arm.pose.bones["pelvis"].rotation_mode = "XYZ"
            arm.pose.bones["pelvis"].rotation_euler = (math.radians(pelvis_deg), 0.0, 0.0)
            arm.pose.bones["spine"].rotation_mode = "XYZ"
            arm.pose.bones["spine"].rotation_euler = (math.radians(spine_deg), 0.0, 0.0)
            for h in (0.20, 0.45, 0.70, 1.0):
                wh = root.matrix_world @ Vector(_lerp3(cw, nw, h))
                ph = root.matrix_world @ Vector(_lerp3(cp, np, h))
                rh = _lerp3(cr, nr, h)
                set_hand_ik_target(
                    arm, side,
                    world_xyz=(wh.x, wh.y, wh.z),
                    hand_rotation_deg=rh,
                    pole_world_xyz=(ph.x, ph.y, ph.z),
                    clamp_reach=False,
                    influence=1.0,
                )
                bpy.context.view_layer.update()
                rom = DEFAULT_HUMANOID_ROM_MODEL.validate_armature_pose(arm, use_evaluated_ik=True)
                arm_viols = [k for k in rom.violations if str(k).endswith(f".{side}")]
                if arm_viols:
                    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
                    arm.pose.bones["pelvis"].rotation_euler = (0.0, 0.0, 0.0)
                    arm.pose.bones["spine"].rotation_euler = (0.0, 0.0, 0.0)
                    return None
                ux, uy, uz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"upper_arm.{side}"]))
                fx, fy, fz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"forearm.{side}"]))
                hx, hy, hz = (math.degrees(v) for v in extract_evaluated_bone_rotation_rad(arm.pose.bones[f"hand.{side}"]))
                uz_min, uz_max = (-18.0, 134.0) if side == "L" else (-134.0, 18.0)
                cone_margin = (0.88 - math.hypot(ux / 160.0, uz / 150.0)) * 100.0
                ua_margin = min(ux - (-38.0), 144.0 - ux, 65.0 - abs(uy), uz - uz_min, uz_max - uz, cone_margin)
                fa_margin = min(fx - 14.0, 136.0 - fx, 68.0 - abs(fy), 1.7 - abs(fz))
                hd_margin = min(hx - (-48.0), 58.0 - hx, 10.5 - abs(hy), 21.0 - abs(hz))
                margin = min(ua_margin, fa_margin, hd_margin)
                if margin < 0.0:
                    arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
                    arm.pose.bones["pelvis"].rotation_euler = (0.0, 0.0, 0.0)
                    arm.pose.bones["spine"].rotation_euler = (0.0, 0.0, 0.0)
                    return None
                if margin < worst_margin:
                    worst_margin = margin
        arm.pose.bones["pelvis"].location = (0.0, -abs(pelvis_dz), 0.0)
        arm.pose.bones["pelvis"].rotation_euler = (0.0, 0.0, 0.0)
        arm.pose.bones["spine"].rotation_euler = (0.0, 0.0, 0.0)
        return worst_margin

    segments: List[UpperLimbSegment] = []
    cur_w, cur_p, cur_r = start_state
    safe_home_w = (-0.28 if side == "L" else 0.28, 0.24, 1.30)
    safe_home_p = (-0.34 if side == "L" else 0.34, -0.24, 1.18)
    for seg_idx, ((t_start, dur), (tgt_w, tgt_p, tgt_r_local)) in enumerate(zip(spans, raw_waypoints)):
        # Limit maximum single-step Cartesian excursion so 2-bone IK forearm rotation matches Euler path closely
        dx, dy, dz = tgt_w[0] - cur_w[0], tgt_w[1] - cur_w[1], tgt_w[2] - cur_w[2]
        step_dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        base_scale = min(1.0, 0.25 / step_dist) if step_dist > 0.25 else 1.0

        chosen = None
        for alpha in (1.0, 0.72, 0.48, 0.28, 0.14):
            s = base_scale * alpha
            cand_w_raw = (cur_w[0] + s * dx, cur_w[1] + s * dy, cur_w[2] + s * dz)
            cand_p_raw = (
                cur_p[0] + s * (tgt_p[0] - cur_p[0]),
                cur_p[1] + s * (tgt_p[1] - cur_p[1]),
                cur_p[2] + s * (tgt_p[2] - cur_p[2]),
            )
            for r_scale in (1.0, 0.55, 0.15, 0.0):
                cand_r_local = (tgt_r_local[0] * r_scale, tgt_r_local[1] * r_scale, tgt_r_local[2] * r_scale)
                cand_w, cand_p, cand_r_local = _clamp_ik_waypoint(side, cand_w_raw, cand_p_raw, cand_r_local)
                raw_deg = vr._compute_hand_world_rot_for_ik_keypose(arm, side, cand_w, cand_p, cand_r_local)
                mat = Euler([math.radians(a) for a in raw_deg], "XYZ").to_matrix()
                cur_euler = Euler([math.radians(a) for a in cur_r], "XYZ")
                cand_eulers = [
                    _wrap_near_deg(raw_deg, cur_r),
                    _wrap_near_deg(tuple(math.degrees(a) for a in mat.to_euler("XYZ", cur_euler)), cur_r),
                ]
                for nr in cand_eulers:
                    margin = _segment_midpoints_safe(cur_w, cur_p, cur_r, cand_w, cand_p, nr)
                    if margin is not None:
                        chosen = (cand_w, cand_p, nr)
                        break
                if chosen is not None:
                    break
            if chosen is not None:
                break
        if chosen is None:
            # Steer smoothly toward central safe workspace home pose and verify midpoints!
            hdx, hdy, hdz = safe_home_w[0] - cur_w[0], safe_home_w[1] - cur_w[1], safe_home_w[2] - cur_w[2]
            for s_h in (1.0, 0.70, 0.45, 0.25):
                cand_w, cand_p, _ = _clamp_ik_waypoint(
                    side,
                    (cur_w[0] + s_h * hdx, cur_w[1] + s_h * hdy, cur_w[2] + s_h * hdz),
                    (cur_p[0] + s_h * (safe_home_p[0] - cur_p[0]), cur_p[1] + s_h * (safe_home_p[1] - cur_p[1]), cur_p[2] + s_h * (safe_home_p[2] - cur_p[2])),
                    (0.0, 0.0, 0.0),
                )
                raw_deg = vr._compute_hand_world_rot_for_ik_keypose(arm, side, cand_w, cand_p, (0.0, 0.0, 0.0))
                nr = _wrap_near_deg(raw_deg, cur_r)
                if _segment_midpoints_safe(cur_w, cur_p, cur_r, cand_w, cand_p, nr) is not None:
                    chosen = (cand_w, cand_p, nr)
                    break
        assert chosen is not None, f"Failed to find safe IK midpoint path for {side} seg {seg_idx}"

        nw, np, nr = chosen
        segments.append(
            UpperLimbSegment(
                mode="IK",
                start_time_sec=t_start,
                duration_sec=dur,
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


# =============================================================================
# PRE-PROBE SOLVER FOR EXACT FK <-> IK BOUNDARY MATCHING
# =============================================================================

def _probe_exact_state_at_frame(
    vr,
    route,
    segs_l: Optional[Tuple[Any, ...]],
    segs_r: Optional[Tuple[Any, ...]],
    target_frames: Dict[str, int],
) -> Dict[str, Dict[str, Any]]:
    """Run real production pipeline in isolated scene up to max target_frame and extract exact poses."""
    import bpy
    from src.motion.terrain_walk import TerrainWalkAction
    from src.motion.framework import MotionPlanner, create_initial_motion_state

    cfg, scene, root_obj, arm_obj, _, _, env = vr._assemble_visual_terrain_scene()
    captured: Dict[str, Dict[str, Any]] = {}
    want_set = set(target_frames.values())
    orig_ef, kb_cls, solve_frames, _, _ = vr._install_solve_observer(arm_obj, root_obj)

    # Also capture exact live FK/IK bridge endpoints at requested frames without frame_set()
    live_endpoints: Dict[int, Dict[str, Any]] = {}
    wrapped_inner = kb_cls.execute_frame

    def capture_hook(self, planned, *args, **kwargs):
        res = wrapped_inner(self, planned, *args, **kwargs)
        if planned.frame in want_set:
            live_endpoints[planned.frame] = {
                "fk_L": _extract_bone_local_fk_deg(arm_obj, "L"),
                "fk_R": _extract_bone_local_fk_deg(arm_obj, "R"),
                "ik_L": _extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "L"),
                "ik_R": _extract_ik_endpoint_from_live_arm(arm_obj, root_obj, "R"),
                "root_pos": [float(v) for v in root_obj.matrix_world.translation],
            }
        return res

    kb_cls.execute_frame = capture_hook
    try:
        pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        pl.add_action(TerrainWalkAction(route=route, environment=env, action_name="BoundaryProbe", upper_limb_L=segs_l, upper_limb_R=segs_r))
        pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        kb_cls.execute_frame = orig_ef

    for label, fnum in target_frames.items():
        captured[label] = live_endpoints[fnum]
    return captured


def _probe_fk_ik_junctions(
    vr,
    route,
    arm_pose_root_xyz: Tuple[float, float, float],
    pelvis_dz: float,
    l_after_frame: int,
    r_after_frame: int,
    l_target: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]],
    r_target: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]],
):
    """Solve desired IK junction targets in real pipeline to get exact matching (fk_A, ik_A) pairs."""
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

    w_L, p_L, r_loc_L = _clamp_ik_waypoint("L", *l_target)
    w_R, p_R, r_loc_R = _clamp_ik_waypoint("R", *r_target)
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
    res = _probe_exact_state_at_frame(
        vr, route, hold_l, hold_r, {"L_after": l_after_frame, "R_after": r_after_frame}
    )
    return {
        "fk_A_L": res["L_after"]["fk_L"],
        "ik_A_L": (w_L, p_L, rot_L),
        "fk_A_R": res["R_after"]["fk_R"],
        "ik_A_R": (w_R, p_R, rot_R),
    }


# =============================================================================
# SCENE 3: COMPLEX BILATERAL MOTION (480 FRAMES = 20.0s @ 24fps)
# =============================================================================

def _build_scene3_schedule_and_segments(vr):
    """Build Scene 3 (480 frames, >=16 effective segments/side, all 4 mode combos, FK->IK->FK both sides)."""
    from src.motion.terrain_walk import TerrainRouteInput, UpperLimbSegment

    fps = 24.0
    # Route: 80 walk frames (frames 201..280, t=8.33s..11.67s) + 200 stand_start + 200 stand_stop = 480 frames (20.0s)
    route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30,
        step_frames=16,
        stand_start_frames=200,
        stand_stop_frames=200,
    )

    # Staggered mode switch boundaries (no simultaneous switch!):
    #   R FK -> IK at t = 84/24 = 3.50s (frame 85)
    #   L FK -> IK at t = 144/24 = 6.00s (frame 145)
    #   R IK -> FK at t = 288/24 = 12.00s (frame 289, stand_stop)
    #   L IK -> FK at t = 360/24 = 15.00s (frame 361, stand_stop)
    # Mode matrix covered:
    #   [0.00..3.50]   L=FK, R=FK  (Both FK)
    #   [3.50..6.00]   L=FK, R=IK  (L FK, R IK)
    #   [6.00..12.00]  L=IK, R=IK  (Both IK)
    #   [12.00..15.00] L=IK, R=FK  (L IK, R FK)
    #   [15.00..20.00] L=FK, R=FK  (Both FK)

    # ---- Step 1: Solve exact FK<->IK junction pairs & build initial FK blocks ----
    neutral_fk = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    junc = _probe_fk_ik_junctions(
        vr, route, (0.0, 10.20, 0.0), 0.05,
        l_after_frame=145, r_after_frame=85,
        l_target=((-0.28, 0.30, 1.32), (-0.36, -0.22, 1.22), (16.0, 2.0, 5.0)),
        r_target=((0.32, 0.28, 1.36), (0.38, -0.22, 1.24), (-16.0, -2.0, -5.0)),
    )
    fk_A_L = junc["fk_A_L"]
    fk_A_R = junc["fk_A_R"]
    wA_L, pA_L, rotA_L = junc["ik_A_L"]
    wA_R, pA_R, rotA_R = junc["ik_A_R"]

    # L initial FK (0.00 .. 6.00s): 6 effective non-zero segments, including a hold gap [3.35s..4.55s] while R moves!
    l_fk1_poses = [neutral_fk] + [_generate_fk_pose_sample("L", i + 1, 0.25) for i in range(5)] + [fk_A_L]
    l_fk1_times = [
        (0.15, 0.75),  # L01
        (0.90, 0.80),  # L02
        (1.70, 0.80),  # L03
        (2.50, 0.85),  # L04 -> holds [3.35..4.55] while R switches & moves!
        (4.55, 0.70),  # L05 (active while R holds [4.60..5.80])
        (5.25, 0.70),  # L06 -> Pose A_L ready by 5.95s
    ]
    segs_l_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk1_times[i][0], duration_sec=l_fk1_times[i][1], fk_start_deg=l_fk1_poses[i], fk_end_deg=l_fk1_poses[i + 1])
        for i in range(6)
    ]

    # R initial FK (0.00 .. 3.50s): 4 effective non-zero segments with staggered timings
    r_fk1_poses = [neutral_fk] + [_generate_fk_pose_sample("R", i + 1, 1.35) for i in range(3)] + [fk_A_R]
    r_fk1_times = [
        (0.30, 0.75),  # R01
        (1.05, 0.80),  # R02
        (1.85, 0.80),  # R03
        (2.65, 0.80),  # R04 -> Pose A_R ready by 3.45s
    ]
    segs_r_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk1_times[i][0], duration_sec=r_fk1_times[i][1], fk_start_deg=r_fk1_poses[i], fk_end_deg=r_fk1_poses[i + 1])
        for i in range(4)
    ]

    # ---- Step 2: Construct IK blocks from exact FK->IK matched endpoints, probe IK->FK ----

    # L IK (6.00 .. 15.00s): 9 non-zero segments, with hold [12.10..13.30s] while R switches to FK & moves!
    l_ik_wp_raw = [_generate_ik_waypoint_sample("L", i + 1, 0.4) for i in range(9)]
    l_ik_times = [
        (6.00, 0.85),   # L07 (starts exact match at 6.00s = f_idx 144 -> frame 145)
        (6.85, 0.80),   # L08
        (7.65, 0.75),   # L09
        (8.40, 0.90),   # L10 (during walk)
        (9.30, 0.90),   # L11 (during walk)
        (10.20, 0.95),  # L12 (during walk)
        (11.15, 0.95),  # L13 -> holds [12.10..13.30s] while R moves in FK!
        (13.30, 0.85),  # L14
        (14.15, 0.80),  # L15 -> Pose B_L ready by 14.95s
    ]
    segs_l_ik = _solve_verified_ik_segments(
        vr, (0.0, 10.20, 0.0), 0.05, "L", (wA_L, pA_L, rotA_L), l_ik_times, l_ik_wp_raw
    )

    # R IK (3.50 .. 12.00s): 9 non-zero segments, with hold [4.50..5.70s] while L moves!
    r_ik_wp_raw = [_generate_ik_waypoint_sample("R", i + 1, 1.7) for i in range(9)]
    r_ik_times = [
        (3.50, 1.00),   # R05 (starts exact match at 3.50s -> active while L holds!)
        # Holds [4.50..5.70s] while L moves!
        (5.70, 0.80),   # R06
        (6.50, 0.85),   # R07
        (7.35, 0.90),   # R08
        (8.25, 0.85),   # R09 (during walk)
        (9.10, 0.85),   # R10 (during walk)
        (9.95, 0.70),   # R11 (during walk)
        (10.65, 0.65),  # R12 (during walk)
        (11.30, 0.65),  # R13 -> Pose B_R ready by 11.95s
    ]
    segs_r_ik = _solve_verified_ik_segments(
        vr, (0.0, 10.20, 0.0), 0.05, "R", (wA_R, pA_R, rotA_R), r_ik_times, r_ik_wp_raw
    )

    probe2 = _probe_exact_state_at_frame(
        vr, route,
        tuple(segs_l_fk1 + segs_l_ik),
        tuple(segs_r_fk1 + segs_r_ik),
        {"R_ik_to_fk": 288, "L_ik_to_fk": 360},
    )

    # ---- Step 3: Final FK blocks from exact IK->FK matched endpoints ----
    fk_B_L = probe2["L_ik_to_fk"]["fk_L"]
    fk_B_R = probe2["R_ik_to_fk"]["fk_R"]

    # L final FK (15.00 .. 19.90s): 5 non-zero segments ending cleanly at neutral
    l_fk2_poses = [fk_B_L] + [_generate_fk_pose_sample("L", i + 20, 0.9) for i in range(4)] + [neutral_fk]
    l_fk2_times = [
        (15.00, 0.95),  # L16
        (15.95, 0.95),  # L17
        (16.90, 0.95),  # L18
        (17.85, 0.95),  # L19
        (18.80, 1.05),  # L20 -> retract to neutral
    ]
    segs_l_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk2_times[i][0], duration_sec=l_fk2_times[i][1], fk_start_deg=l_fk2_poses[i], fk_end_deg=l_fk2_poses[i + 1])
        for i in range(5)
    ]

    # R final FK (12.00 .. 19.90s): 7 non-zero segments (first 2 active during L hold [12.10..13.30s]!)
    r_fk2_poses = [fk_B_R] + [_generate_fk_pose_sample("R", i + 20, 2.1) for i in range(6)] + [neutral_fk]
    r_fk2_times = [
        (12.00, 0.85),  # R14 (active while L holds!)
        (12.85, 0.95),  # R15
        (13.80, 1.00),  # R16
        (14.80, 1.00),  # R17
        (15.80, 1.00),  # R18
        (16.80, 1.50),  # R19
        (18.30, 1.55),  # R20 -> staggered retract ending 19.85s
    ]
    segs_r_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk2_times[i][0], duration_sec=r_fk2_times[i][1], fk_start_deg=r_fk2_poses[i], fk_end_deg=r_fk2_poses[i + 1])
        for i in range(7)
    ]

    all_l = tuple(segs_l_fk1 + segs_l_ik + segs_l_fk2)  # 6 + 9 + 5 = 20 non-zero segments!
    all_r = tuple(segs_r_fk1 + segs_r_ik + segs_r_fk2)  # 4 + 9 + 7 = 20 non-zero segments!

    markers = [
        ("S3_BothFK_Start", 1),
        ("S3_R_FK_to_IK", 85),
        ("S3_L_FK_to_IK_BothIK", 145),
        ("S3_Walk_Start", 201),
        ("S3_Walk_Stop", 281),
        ("S3_R_IK_to_FK", 289),
        ("S3_L_IK_to_FK_BothFK", 361),
        ("S3_End", 480),
    ]
    mode_switches = {
        "L": [
            {"type": "FK_to_IK", "before_frame": 144, "after_frame": 145, "time_sec": 6.00},
            {"type": "IK_to_FK", "before_frame": 360, "after_frame": 361, "time_sec": 15.00},
        ],
        "R": [
            {"type": "FK_to_IK", "before_frame": 84, "after_frame": 85, "time_sec": 3.50},
            {"type": "IK_to_FK", "before_frame": 288, "after_frame": 289, "time_sec": 12.00},
        ],
    }
    stages = [
        ("stage_01_both_fk_0_3.5s", 1, 84),
        ("stage_02_L_fk_R_ik_3.5_6s", 85, 144),
        ("stage_03_both_ik_stand_6_8.3s", 145, 200),
        ("stage_04_both_ik_walk_8.3_11.7s", 201, 280),
        ("stage_05_L_ik_R_fk_12_15s", 289, 360),
        ("stage_06_both_fk_retract_15_20s", 361, 480),
    ]
    return route, all_l, all_r, markers, mode_switches, stages


# =============================================================================
# SCENE 4: LONG CONTINUOUS MOTION (1440 FRAMES = 60.0s @ 24fps)
# =============================================================================

def _build_scene4_schedule_and_segments(vr):
    """Build Scene 4 (1440 frames = 60s, Course B 10.20->22.40m, >=40 segs/side, >=75% active)."""
    from src.motion.terrain_walk import TerrainRouteInput, UpperLimbSegment, plan_terrain_footsteps
    from src.scene.environment_query import create_standard_dynamics_playground_query

    env = create_standard_dynamics_playground_query()
    probe_route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 22.40, 0.0),
        nominal_stride_m=0.24,
        step_frames=18,
        stand_start_frames=0,
        stand_stop_frames=0,
        base_clearance_m=0.10,
        pelvis_drop_uphill_m=0.075,
        pelvis_drop_downhill_m=0.085,
    )
    sched, walk_frames = plan_terrain_footsteps(probe_route, env, start_frame=1)
    # 52 steps * 18 frames = 936 walk frames (65.0% of 1440 >= 50%)!
    assert walk_frames == 936, f"Expected 936 walk frames for Course B, got {walk_frames}"
    stand_start = 216  # 9.000s (frames 1..216)
    stand_stop = 1440 - walk_frames - stand_start  # 288 frames = 12.000s (frames 1153..1440)
    assert stand_start + walk_frames + stand_stop == 1440

    route = dataclasses.replace(probe_route, stand_start_frames=stand_start, stand_stop_frames=stand_stop)
    neutral_fk = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    # Staggered FK/IK mode switches across 60s:
    #   L: FK [0..6.00s] -> IK [6.00..39.00s] -> FK [39.00..60.00s]
    #      (Switch L_fk_to_ik at frame 144->145 [t=6.00s, stand_start],
    #       L_ik_to_fk at frame 936->937 [t=39.00s, during walk step boundary!])
    #   R: FK [0..18.00s] -> IK [18.00..50.00s] -> FK [50.00..60.00s]
    #      (Switch R_fk_to_ik at frame 432->433 [t=18.00s, during walk step boundary!],
    #       R_ik_to_fk at frame 1200->1201 [t=50.00s, stand_stop])
    # Notice ALL 4 mode combinations & staggered switches:
    #   [0..6]    FK+FK
    #   [6..18]   IK+FK (crosses walk start at 9.0s)
    #   [18..39]  IK+IK (walking ramps + bridge + holds/recovery)
    #   [39..50]  FK+IK (walking ramp down + stop at 48.0s)
    #   [50..60]  FK+FK (post-walk continuation + retract)

    # ---- Step 1: Solve exact FK<->IK junction pairs & initial FK segments ----
    junc_s4 = _probe_fk_ik_junctions(
        vr, route, (0.0, 10.20, 0.0), 0.075,
        l_after_frame=145, r_after_frame=433,
        l_target=((-0.28, 0.30, 1.32), (-0.36, -0.22, 1.22), (14.0, 2.0, 4.0)),
        r_target=((0.32, 0.28, 1.34), (0.38, -0.22, 1.24), (-14.0, -2.0, -4.0)),
    )
    fk_A_L = junc_s4["fk_A_L"]
    fk_A_R = junc_s4["fk_A_R"]
    wA_L, pA_L, rotA_L = junc_s4["ik_A_L"]
    wA_R, pA_R, rotA_R = junc_s4["ik_A_R"]

    # L FK1 [0.00 .. 6.00s]: 5 non-zero segments (active 5.7s)
    l_fk1_poses = [neutral_fk] + [_generate_fk_pose_sample("L", i + 1, 0.15) for i in range(4)] + [fk_A_L]
    l_fk1_spans = [(0.20, 1.15), (1.35, 1.15), (2.50, 1.15), (3.65, 1.15), (4.80, 1.15)]  # ends 5.95s
    segs_l_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk1_spans[i][0], duration_sec=l_fk1_spans[i][1], fk_start_deg=l_fk1_poses[i], fk_end_deg=l_fk1_poses[i + 1])
        for i in range(5)
    ]

    # R FK1 [0.00 .. 18.00s]: 13 non-zero segments (active 16.0s; includes hold [10.80..12.60s] during early ramp walk)
    r_fk1_poses = [neutral_fk] + [_generate_fk_pose_sample("R", i + 1, 1.05) for i in range(12)] + [fk_A_R]
    r_fk1_spans = [
        (0.30, 1.15), (1.45, 1.15), (2.60, 1.15), (3.75, 1.15), (4.90, 1.15),
        (6.05, 1.15), (7.20, 1.20), (8.40, 1.20), (9.60, 1.20),
        # Hold [10.80..12.60s] (1.8s hold during early uphill ramp while L moves in IK!)
        (12.60, 1.35), (13.95, 1.35), (15.30, 1.35), (16.65, 1.30),  # ends 17.95s
    ]
    segs_r_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk1_spans[i][0], duration_sec=r_fk1_spans[i][1], fk_start_deg=r_fk1_poses[i], fk_end_deg=r_fk1_poses[i + 1])
        for i in range(13)
    ]

    # ---- Step 2: IK segments starting from matched junction endpoints ----

    # L IK [6.00 .. 39.00s]: 25 non-zero segments covering [6..39s] with one walk hold [22.25..24.25s] (active 30.95s!)
    l_ik_spans = []
    t_cur = 6.00
    for idx in range(25):
        if idx == 13:
            # Explicit 2.0s hold during walking (22.25..24.25s) while R continues moving, then resume!
            t_cur += 2.00
        dur = 1.25 if idx < 24 else 0.95  # 13*1.25 + 2.00 + 11*1.25 + 0.95 = 6.00 + 32.95 = 38.95s!
        l_ik_spans.append((round(t_cur, 6), dur))
        t_cur += dur

    l_ik_wp_raw = [_generate_ik_waypoint_sample("L", i + 1, 0.55) for i in range(25)]
    segs_l_ik = _solve_verified_ik_segments(
        vr, (0.0, 10.20, 0.0), 0.045, "L", (wA_L, pA_L, rotA_L), l_ik_spans, l_ik_wp_raw
    )

    # R IK [18.00 .. 50.00s]: 25 non-zero segments covering [18..50s] with one walk hold [30.00..32.00s] (active 30.0s!)
    r_ik_spans = []
    t_cur = 18.00
    for idx in range(25):
        if idx == 10:
            # Explicit 2.0s hold during walking (30.00..32.00s) while L moves, then resume!
            t_cur += 2.00
        dur = 1.20 if idx < 24 else 1.15  # ends 49.95s!
        r_ik_spans.append((round(t_cur, 6), dur))
        t_cur += dur

    r_ik_wp_raw = [_generate_ik_waypoint_sample("R", i + 1, 2.05) for i in range(25)]
    segs_r_ik = _solve_verified_ik_segments(
        vr, (0.0, 10.20, 0.0), 0.045, "R", (wA_R, pA_R, rotA_R), r_ik_spans, r_ik_wp_raw
    )

    probe_s4_2 = _probe_exact_state_at_frame(
        vr, route,
        tuple(segs_l_fk1 + segs_l_ik),
        tuple(segs_r_fk1 + segs_r_ik),
        {"L_ik_to_fk": 936, "R_ik_to_fk": 1200},
    )

    # ---- Step 3: Final FK blocks from exact IK->FK probed endpoints ----
    fk_B_L = probe_s4_2["L_ik_to_fk"]["fk_L"]
    fk_B_R = probe_s4_2["R_ik_to_fk"]["fk_R"]

    # L FK2 [39.00 .. 59.70s]: 18 non-zero segments (20.70s active, ends at neutral)
    l_fk2_poses = [fk_B_L] + [_generate_fk_pose_sample("L", i + 40, 1.45) for i in range(17)] + [neutral_fk]
    l_fk2_spans = []
    t_cur = 39.00
    for i in range(18):
        dur = 1.15  # 39.00 + 18*1.15 = 59.70s!
        l_fk2_spans.append((round(t_cur, 6), dur))
        t_cur += dur
    segs_l_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk2_spans[i][0], duration_sec=l_fk2_spans[i][1], fk_start_deg=l_fk2_poses[i], fk_end_deg=l_fk2_poses[i + 1])
        for i in range(18)
    ]

    # R FK2 [50.00 .. 59.90s]: 8 non-zero segments (9.90s active, staggered finish at 59.90s)
    r_fk2_poses = [fk_B_R] + [_generate_fk_pose_sample("R", i + 40, 2.75) for i in range(7)] + [neutral_fk]
    r_fk2_spans = []
    t_cur = 50.00
    for i in range(8):
        dur = 1.20 if i < 7 else 1.50  # 50.00 + 7*1.20 + 1.50 = 59.90s!
        r_fk2_spans.append((round(t_cur, 6), dur))
        t_cur += dur
    segs_r_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk2_spans[i][0], duration_sec=r_fk2_spans[i][1], fk_start_deg=r_fk2_poses[i], fk_end_deg=r_fk2_poses[i + 1])
        for i in range(8)
    ]

    all_l = tuple(segs_l_fk1 + segs_l_ik + segs_l_fk2)  # 5 + 25 + 18 = 48 non-zero segments!
    all_r = tuple(segs_r_fk1 + segs_r_ik + segs_r_fk2)  # 13 + 25 + 8 = 46 non-zero segments!

    markers = [
        ("S4_StandPrep_BothFK", 1),
        ("S4_L_FK_to_IK", 145),
        ("S4_WalkStart_RampUp", 217),
        ("S4_R_FK_to_IK", 433),
        ("S4_L_WalkHold_Resume", 577),
        ("S4_R_WalkHold_Resume", 769),
        ("S4_L_IK_to_FK", 937),
        ("S4_WalkStop_FlatExit", 1153),
        ("S4_R_IK_to_FK", 1201),
        ("S4_Final_Retract", 1440),
    ]
    mode_switches = {
        "L": [
            {"type": "FK_to_IK", "before_frame": 144, "after_frame": 145, "time_sec": 6.00},
            {"type": "IK_to_FK", "before_frame": 936, "after_frame": 937, "time_sec": 39.00},
        ],
        "R": [
            {"type": "FK_to_IK", "before_frame": 432, "after_frame": 433, "time_sec": 18.00},
            {"type": "IK_to_FK", "before_frame": 1200, "after_frame": 1201, "time_sec": 50.00},
        ],
    }
    stages = [
        ("win_00_10s", 1, 240),
        ("win_10_20s", 241, 480),
        ("win_20_30s", 481, 720),
        ("win_30_40s", 721, 960),
        ("win_40_50s", 961, 1200),
        ("win_50_60s", 1201, 1440),
    ]
    return route, all_l, all_r, markers, mode_switches, stages


# =============================================================================
# VERIFICATION & WORKER EXECUTION
# =============================================================================

def _count_effective_segments(segs) -> Tuple[int, float]:
    count = 0
    total_dur = 0.0
    for s in segs:
        if s.mode == "FK":
            diff = max(abs(s.fk_end_deg[b][a] - s.fk_start_deg[b][a]) for b in range(3) for a in range(3))
            is_eff = diff > 1e-3
        else:
            wdiff = math.sqrt(sum((s.wrist_end_xyz[k] - s.wrist_start_xyz[k]) ** 2 for k in range(3)))
            pdiff = math.sqrt(sum((s.pole_end_xyz[k] - s.pole_start_xyz[k]) ** 2 for k in range(3))) if s.pole_start_xyz and s.pole_end_xyz else 0.0
            rdiff = max(abs(s.rotation_end_deg[k] - s.rotation_start_deg[k]) for k in range(3)) if s.rotation_start_deg and s.rotation_end_deg else 0.0
            is_eff = (wdiff > 1e-3) or (pdiff > 1e-3) or (rdiff > 1e-2)
        if is_eff:
            count += 1
            total_dur += float(s.duration_sec)
    return count, total_dur


def _evaluate_switch_boundary(solve_frames_by_f: Dict[int, Dict[str, Any]], vr, side: str, sw: Dict[str, Any]) -> Dict[str, Any]:
    from mathutils import Matrix, Vector

    a = solve_frames_by_f[sw["before_frame"]]
    b = solve_frames_by_f[sw["after_frame"]]
    root_d = (Vector(a["root_world_pos"]) - Vector(b["root_world_pos"])).length
    wrist_d = (Vector(a[f"wrist_world_{side}"]) - Vector(b[f"wrist_world_{side}"])).length
    elbow_d = (Vector(a[f"elbow_world_{side}"]) - Vector(b[f"elbow_world_{side}"])).length
    max_rot_d = 0.0
    for bn in (f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}"):
        ang = math.degrees(_quat_angle_safe(vr, a["bones"][bn]["world_quat"], b["bones"][bn]["world_quat"]))
        max_rot_d = max(max_rot_d, ang)

    if root_d <= 1e-5:
        assert wrist_d <= 0.005, f"Switch {side} {sw} wrist jump {wrist_d}m > 0.005m"
        assert elbow_d <= 0.005, f"Switch {side} {sw} elbow jump {elbow_d}m > 0.005m"
        assert max_rot_d <= 1.0, f"Switch {side} {sw} world rot jump {max_rot_d}deg > 1.0deg"

    w_loc_d = (Vector(a[f"wrist_root_local_{side}"]) - Vector(b[f"wrist_root_local_{side}"])).length
    e_loc_a = Matrix([tuple(r) for r in a["root_world_matrix"]]).inverted() @ Vector(a[f"elbow_world_{side}"])
    e_loc_b = Matrix([tuple(r) for r in b["root_world_matrix"]]).inverted() @ Vector(b[f"elbow_world_{side}"])
    e_loc_d = (e_loc_a - e_loc_b).length
    max_rel_rot_d = 0.0
    for bn in (f"upper_arm.{side}", f"forearm.{side}", f"hand.{side}"):
        ang = math.degrees(_quat_angle_safe(vr, a["bones"][bn]["rel_parent_quat"], b["bones"][bn]["rel_parent_quat"]))
        max_rel_rot_d = max(max_rel_rot_d, ang)

    assert w_loc_d <= 0.005 and e_loc_d <= 0.005 and max_rel_rot_d <= 1.0, (
        f"Switch {side} {sw} root-local discontinuity: wrist_loc={w_loc_d}, elbow_loc={e_loc_d}, rel_rot={max_rel_rot_d}"
    )
    return {
        **sw,
        "root_world_delta_m": root_d,
        "wrist_world_delta_m": wrist_d,
        "elbow_world_delta_m": elbow_d,
        "wrist_root_local_delta_m": w_loc_d,
        "elbow_root_local_delta_m": e_loc_d,
        "max_world_rot_delta_deg": max_rot_d,
        "max_rel_rot_delta_deg": max_rel_rot_d,
        "before_arm_ik_influence": a["influences"][f"ArmIK.{side}"],
        "after_arm_ik_influence": b["influences"][f"ArmIK.{side}"],
    }


def _quat_angle_safe(vr, q1_list, q2_list) -> float:
    from mathutils import Quaternion

    return vr._quat_angle_rad(Quaternion(q1_list), Quaternion(q2_list))


def _worker_generate(scene_id: str, blend_out: str, dump_json: str) -> None:
    import bpy
    _setup_sys_path()
    vr = _load_vr()
    from src.motion.terrain_walk import TerrainWalkAction
    from src.motion.framework import MotionPlanner, create_initial_motion_state
    from src.scene.playground_terrain_traversal import ensure_ramp_corridor_ground_surfaces

    if scene_id == "scene3":
        route, segs_l, segs_r, markers, mode_switches, stages = _build_scene3_schedule_and_segments(vr)
        expected_frames = 480
        min_eff_segs = 16
        follow_cam = False
    elif scene_id == "scene4":
        route, segs_l, segs_r, markers, mode_switches, stages = _build_scene4_schedule_and_segments(vr)
        expected_frames = 1440
        min_eff_segs = 40
        follow_cam = True
    else:
        raise ValueError(f"Unknown scene_id: {scene_id}")

    cfg, scene, root_obj, arm_obj, hand_l, hand_r, env = vr._assemble_visual_terrain_scene()
    if follow_cam:
        ensure_ramp_corridor_ground_surfaces(scene, bpy.data.collections["Playground_Surfaces"])

    orig_ef, kb_cls, solve_frames, _, wbc_stream = vr._install_solve_observer(arm_obj, root_obj)
    try:
        pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        pl.add_action(
            TerrainWalkAction(
                route=route,
                environment=env,
                action_name=f"Task10D_{scene_id}",
                upper_limb_L=segs_l,
                upper_limb_R=segs_r,
            )
        )
        res = pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=route.start_pos))
    finally:
        kb_cls.execute_frame = orig_ef

    states = res["states"]
    assert len(states) == expected_frames and len(solve_frames) == expected_frames
    assert all(w["success"] for w in wbc_stream), f"WBC failed in {scene_id}"

    # Verify effective segments, global/per-stage motion gates, mode combinations & switch boundaries
    eff_l_cnt, eff_l_dur = _count_effective_segments(segs_l)
    eff_r_cnt, eff_r_dur = _count_effective_segments(segs_r)
    assert eff_l_cnt >= min_eff_segs and eff_r_cnt >= min_eff_segs

    if scene_id == "scene4":
        total_sec = expected_frames / float(cfg.fps)
        assert eff_l_dur >= 0.75 * total_sec and eff_r_dur >= 0.75 * total_sec

    full_l = vr._compute_side_motion_metrics(solve_frames, "L")
    full_r = vr._compute_side_motion_metrics(solve_frames, "R")
    for slbl, fm in (("L", full_l), ("R", full_r)):
        assert fm["upper_arm_rel_span_deg"] >= 25.0
        assert fm["forearm_rel_span_deg"] >= 25.0
        assert fm["hand_rel_span_deg"] >= 20.0
        assert fm["wrist_root_local_span_m"] >= 0.15

    stage_metrics = {}
    for st_name, f_lo, f_hi in stages:
        sm = vr._slice_interval_metrics(solve_frames, f_lo, f_hi)
        # Ensure active bilateral motion inside EVERY stage / 10s window (not concentrated in 1 burst)
        assert sm["L"]["wrist_root_local_span_m"] >= 0.10 and sm["R"]["wrist_root_local_span_m"] >= 0.10, (
            f"Inactive stage {st_name}: {sm}"
        )
        assert sm["L"]["upper_arm_rel_span_deg"] >= 10.0 and sm["R"]["upper_arm_rel_span_deg"] >= 10.0
        stage_metrics[st_name] = sm

    # Mode combinations present check across solve_frames
    seen_combos = set()
    for sf in solve_frames:
        l_ik = sf["influences"]["ArmIK.L"] > 0.5
        r_ik = sf["influences"]["ArmIK.R"] > 0.5
        seen_combos.add(("IK" if l_ik else "FK", "IK" if r_ik else "FK"))
    assert seen_combos == {("FK", "FK"), ("FK", "IK"), ("IK", "IK"), ("IK", "FK")}, f"Missing combos: {seen_combos}"

    solve_by_f = {int(f["frame"]): f for f in solve_frames}
    switch_reports = {
        side: [_evaluate_switch_boundary(solve_by_f, vr, side, sw) for sw in sw_list]
        for side, sw_list in mode_switches.items()
    }

    # Camera follow (only in Scene 4 after solve!), timeline markers, and Frame 1 open state
    _add_timeline_markers(scene, markers)
    if follow_cam:
        _attach_root_follow_camera(scene, root_obj, scene.camera)

    scene.frame_start = 1
    scene.frame_end = expected_frames
    scene.frame_set(1)
    bpy.context.view_layer.update()

    abs_blend = os.path.abspath(blend_out)
    os.makedirs(os.path.dirname(abs_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=abs_blend)
    b1 = abs_blend + "1"
    if os.path.exists(b1):
        os.remove(b1)

    walk_frames_count = expected_frames - route.stand_start_frames - route.stand_stop_frames
    summary = {
        "scene_id": scene_id,
        "asset": {
            "path": abs_blend,
            "relative_path": os.path.relpath(abs_blend, REPO_ROOT).replace("\\", "/"),
            "size_bytes": os.path.getsize(abs_blend),
            "sha256": _sha256_file(abs_blend),
            "frame_start": 1,
            "frame_end": expected_frames,
            "frame_count": expected_frames,
            "duration_sec": expected_frames / float(cfg.fps),
        },
        "effective_segments": {
            "L_count": eff_l_cnt,
            "L_active_sec": eff_l_dur,
            "L_active_ratio": eff_l_dur / (expected_frames / float(cfg.fps)),
            "R_count": eff_r_cnt,
            "R_active_sec": eff_r_dur,
            "R_active_ratio": eff_r_dur / (expected_frames / float(cfg.fps)),
        },
        "walking_stats": {
            "route_start": list(route.start_pos),
            "route_target": list(route.target_pos),
            "walk_frames": walk_frames_count,
            "walk_sec": walk_frames_count / float(cfg.fps),
            "walk_ratio": walk_frames_count / float(expected_frames),
        },
        "mode_combinations_observed": sorted([list(c) for c in seen_combos]),
        "mode_switches": switch_reports,
        "full_timeline_L": full_l,
        "full_timeline_R": full_r,
        "stage_metrics": stage_metrics,
        "markers_count": len(markers),
        "solve_frames": solve_frames,
    }

    os.makedirs(os.path.dirname(os.path.abspath(dump_json)), exist_ok=True)
    with open(dump_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, separators=(",", ":"))


def _worker_reopen(blend_path: str, solve_json: str, out_json: str) -> None:
    import bpy
    from mathutils import Quaternion, Vector
    vr = _load_vr()

    with open(solve_json, "r", encoding="utf-8") as fp:
        solve_data = json.load(fp)
    solve_frames = solve_data["solve_frames"]
    solve_by_f = {int(r["frame"]): r for r in solve_frames}
    frame_end = len(solve_frames)

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_path))
    scene = bpy.context.scene
    arm = bpy.data.objects["CharacterArmature"]
    root = bpy.data.objects["CharacterRoot"]
    hand_l = bpy.data.objects["Hand_L"]
    hand_r = bpy.data.objects["Hand_R"]

    assert len(arm.data.bones) == 19
    assert int(scene.frame_start) == 1 and int(scene.frame_end) == frame_end
    assert int(scene.frame_current) == 1
    assert int(scene.render.fps) == 24
    assert len(scene.timeline_markers) == solve_data["markers_count"]
    assert hand_l.parent == arm and hand_l.parent_bone == "hand.L" and hand_l.animation_data is None
    assert hand_r.parent == arm and hand_r.parent_bone == "hand.R" and hand_r.animation_data is None

    slot_id, fcurves = vr._get_slot_fcurves(arm)
    assert slot_id is not None
    fc_by_path = {fc.data_path: fc for fc in fcurves}
    expected_fset = set(range(1, frame_end + 1))
    inf_checks = {}
    for cname, _, dp in vr.UPPER_CONSTRAINTS:
        fc = fc_by_path.get(dp)
        assert fc is not None
        assert {int(round(kp.co[0])) for kp in fc.keyframe_points} == expected_fset
        assert sorted({str(kp.interpolation) for kp in fc.keyframe_points}) == ["CONSTANT"]
        inf_checks[cname] = {"keyframes": len(fc.keyframe_points), "interpolation": "CONSTANT"}

    all_frames = list(range(1, frame_end + 1))
    orders = [
        ("forward", list(all_frames)),
        ("reverse", list(reversed(all_frames))),
        ("shuffled_seed_20261126", random.Random(20261126).sample(all_frames, len(all_frames))),
    ]

    pos_tol, rot_tol, inf_tol = 1e-5, 1e-4, 1e-6
    traversals = []
    for oname, fseq in orders:
        max_p, max_r, max_i = 0.0, 0.0, 0.0
        for f in fseq:
            scene.frame_set(f)
            bpy.context.view_layer.update()
            exp = solve_by_f[f]
            aw = arm.matrix_world
            rw = root.matrix_world

            for vec, e_xyz in (
                (rw.translation, exp["root_world_pos"]),
                (aw @ arm.pose.bones["forearm.L"].tail, exp["wrist_world_L"]),
                (aw @ arm.pose.bones["forearm.R"].tail, exp["wrist_world_R"]),
                (aw @ arm.pose.bones["upper_arm.L"].tail, exp["elbow_world_L"]),
                (aw @ arm.pose.bones["upper_arm.R"].tail, exp["elbow_world_R"]),
                (bpy.data.objects["ElbowPole.L"].matrix_world.translation, exp["elbow_pole_world_L"]),
                (bpy.data.objects["ElbowPole.R"].matrix_world.translation, exp["elbow_pole_world_R"]),
            ):
                perr = (vec - Vector(e_xyz)).length
                max_p = max(max_p, perr)
                assert perr <= pos_tol, f"{blend_path} ({oname}) f={f} pos err={perr}"

            r_rq = vr._quat_angle_rad(rw.to_3x3().normalized().to_quaternion(), Quaternion(exp["root_world_quat"]))
            max_r = max(max_r, r_rq)
            assert r_rq <= rot_tol

            for bn in vr.UPPER_LIMB_BONES:
                pb = arm.pose.bones[bn]
                wq = (aw @ pb.matrix).to_3x3().normalized().to_quaternion()
                re1 = vr._quat_angle_rad(wq, Quaternion(exp["bones"][bn]["world_quat"]))
                rel_q, _ = vr._relative_joint_quat_and_euler(arm, bn)
                re2 = vr._quat_angle_rad(rel_q, Quaternion(exp["bones"][bn]["rel_parent_quat"]))
                max_r = max(max_r, re1, re2)
                assert re1 <= rot_tol and re2 <= rot_tol, f"{blend_path} ({oname}) f={f} {bn} rot err={max(re1, re2)}"

            for cn in vr.UPPER_CONTROLLERS:
                cq = bpy.data.objects[cn].matrix_world.to_3x3().normalized().to_quaternion()
                ce = vr._quat_angle_rad(cq, Quaternion(exp["controllers"][cn]["world_quat"]))
                max_r = max(max_r, ce)
                assert ce <= rot_tol

            for cname, bname, _ in vr.UPPER_CONSTRAINTS:
                ie = abs(float(arm.pose.bones[bname].constraints[cname].influence) - exp["influences"][cname])
                max_i = max(max_i, ie)
                assert ie <= inf_tol

        traversals.append({
            "order": oname,
            "frames_checked": len(fseq),
            "max_pos_err_m": max_p,
            "max_rot_err_rad": max_r,
            "max_inf_err": max_i,
            "passed": True,
        })

    os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "passed": True,
                "blend_path": os.path.abspath(blend_path),
                "action_slot": slot_id,
                "influence_fcurves": inf_checks,
                "solve_vs_reopen_traversals": traversals,
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
        _worker_generate(cli["scene"], cli["blend"], cli["out"])
    elif task == "reopen":
        _worker_reopen(cli["blend"], cli["solve"], cli["out"])
    else:
        raise ValueError(f"Unknown worker task: {task}")
    print(f"EXTENDED_WORKER_OK {task}")
    return 0


# =============================================================================
# COORDINATOR
# =============================================================================

def _run_subprocess(cmd: List[str], label: str, out_chunks: List[str], err_chunks: List[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    hdr = f"\n=== [{label}] cmd: {' '.join(cmd)} (rc={proc.returncode}) ===\n"
    out_chunks.append(hdr + (proc.stdout or ""))
    if proc.stderr:
        err_chunks.append(hdr + proc.stderr)
    return proc


def _run_coordinator() -> int:
    os.makedirs(SCRATCH_WORK, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(EXTENDED_DIR, exist_ok=True)

    out_chunks: List[str] = []
    err_chunks: List[str] = []

    ver = _run_subprocess([BLENDER_EXE, "--version"], "blender_version", out_chunks, err_chunks)
    if ver.returncode != 0 or "Blender 5.1.1" not in ver.stdout:
        raise RuntimeError(f"Expected Blender 5.1.1: {ver.stdout}")

    actual_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if actual_head != EXPECTED_HEAD:
        raise RuntimeError(f"HEAD mismatch: {actual_head} != {EXPECTED_HEAD}")

    reused_blob = subprocess.run(["git", "hash-object", REDELIVERY_SCRIPT], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if reused_blob != EXPECTED_REUSED_BLOB:
        raise RuntimeError(f"Reused script blob mismatch: {reused_blob} != {EXPECTED_REUSED_BLOB}")

    actual_blobs = {}
    for rp, eb in FROZEN_SOURCE_BLOBS.items():
        b = subprocess.run(["git", "hash-object", rp], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if b != eb:
            raise RuntimeError(f"Frozen source blob mismatch {rp}: {b} != {eb}")
        actual_blobs[rp] = b

    def _run_blender(label: str, args: List[str]) -> None:
        cmd = [BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1", "--python", THIS_FILE, "--", *args]
        p = _run_subprocess(cmd, label, out_chunks, err_chunks)
        if p.returncode != 0:
            raise RuntimeError(f"Blender job '{label}' failed (rc={p.returncode})\n{p.stderr}")

    exit_code = 0
    try:
        s3_json = os.path.join(SCRATCH_WORK, "s3_solve.json")
        s3_reopen_json = os.path.join(SCRATCH_WORK, "s3_reopen.json")
        _run_blender("generate_scene3", ["--worker", "generate", "--scene", "scene3", "--blend", DELIVERABLE_SCENE3, "--out", s3_json])
        _run_blender("reopen_scene3", ["--worker", "reopen", "--blend", DELIVERABLE_SCENE3, "--solve", s3_json, "--out", s3_reopen_json])

        s4_json = os.path.join(SCRATCH_WORK, "s4_solve.json")
        s4_reopen_json = os.path.join(SCRATCH_WORK, "s4_reopen.json")
        _run_blender("generate_scene4", ["--worker", "generate", "--scene", "scene4", "--blend", DELIVERABLE_SCENE4, "--out", s4_json])
        _run_blender("reopen_scene4", ["--worker", "reopen", "--blend", DELIVERABLE_SCENE4, "--solve", s4_json, "--out", s4_reopen_json])

        with open(s3_json, "r", encoding="utf-8") as fp:
            s3 = json.load(fp)
        with open(s3_reopen_json, "r", encoding="utf-8") as fp:
            s3_r = json.load(fp)
        with open(s4_json, "r", encoding="utf-8") as fp:
            s4 = json.load(fp)
        with open(s4_reopen_json, "r", encoding="utf-8") as fp:
            s4_r = json.load(fp)

        # Persist compact unrounded solve-time poses for full traceability
        with open(os.path.join(EXTENDED_DIR, "solve_time_poses.json"), "w", encoding="utf-8") as fp:
            json.dump(
                {
                    "task10d_complex_bilateral_motion": s3.pop("solve_frames"),
                    "task10d_long_continuous_motion": s4.pop("solve_frames"),
                },
                fp,
                separators=(",", ":"),
            )

        artifacts = {
            "task10d_complex_bilateral_motion": s3["asset"],
            "task10d_long_continuous_motion": s4["asset"],
        }
        with open(os.path.join(EXTENDED_DIR, "blend_artifacts.json"), "w", encoding="utf-8") as fp:
            json.dump(artifacts, fp, indent=2)

        report = {
            "task_id": "TASK 10-d-4 Extended Visual Delivery",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "git_head": actual_head,
            "reused_script": "docs/evidence/10-d/10-d-4/visual_redelivery/generate_visual_redelivery.py",
            "reused_script_blob": reused_blob,
            "source_blobs": actual_blobs,
            "command": f'"{BLENDER_PYTHON}" -B docs/evidence/10-d/10-d-4/extended_visual_delivery/generate_extended_visual_delivery.py',
            "passed": True,
            "scene_3_complex_bilateral": {
                **s3,
                "reopen_verification": s3_r,
            },
            "scene_4_long_continuous": {
                **s4,
                "reopen_verification": s4_r,
            },
        }
        with open(os.path.join(EXTENDED_DIR, "motion_report.json"), "w", encoding="utf-8") as fp:
            json.dump(report, fp, indent=2)

    except Exception as exc:
        exit_code = 1
        err_chunks.append(f"\n[EXTENDED DELIVERY FAILURE] {type(exc).__name__}: {exc}\n{traceback.format_exc()}\n")

    out_chunks.append(f"\nEXTENDED_DELIVERY_SUMMARY exit_code={exit_code}\n")
    with open(os.path.join(EXTENDED_DIR, "stdout.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(out_chunks))
    with open(os.path.join(EXTENDED_DIR, "stderr.log"), "w", encoding="utf-8") as fp:
        fp.write("".join(err_chunks))

    print(f"EXTENDED_DELIVERY_SUMMARY exit_code={exit_code}")
    if exit_code != 0:
        print("FAILED - inspect extended_visual_delivery/stderr.log", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    if "--" in sys.argv and "--worker" in sys.argv[sys.argv.index("--") + 1 :]:
        raise SystemExit(_dispatch_worker(sys.argv[sys.argv.index("--") + 1 :]))
    raise SystemExit(_run_coordinator())
