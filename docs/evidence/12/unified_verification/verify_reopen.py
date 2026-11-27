"""TASK 12-D B20 & Section 11: Automated Blender Save & Independent Process Reopen Verification.

Dual-mode script:
1. Producer / Orchestrator (default):
   "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P docs/evidence/12/unified_verification/verify_reopen.py
2. Independent Reopen Worker:
   "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b <blend_file> -P docs/evidence/12/unified_verification/verify_reopen.py -- --verify <spec.json> <out.json>
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import EnvironmentQuery, MotionPlanner, create_initial_motion_state
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import UpperLimbSegment
from src.rig.arm_ik import ARM_IK_CONSTRAINT_NAMES, HAND_ROT_CONSTRAINT_NAMES, setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, setup_leg_ik
from src.rig.pose import reset_pose

BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
SCRATCH_REOPEN_DIR = (
    r"C:\Users\64701\.gemini\antigravity\brain\195cba67-abc9-47a3-9c96-4bd0bab568e0\scratch\task12_reopen_scenes"
)
OUTPUT_JSON = os.path.join(THIS_DIR, "reopen_results.json")

CONTROLLERS_8 = (
    "FootIK.L",
    "FootIK.R",
    "KneePole.L",
    "KneePole.R",
    "HandIK.L",
    "HandIK.R",
    "ElbowPole.L",
    "ElbowPole.R",
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_fcurves_for(obj: Optional[bpy.types.Object]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if obj is None or obj.animation_data is None or obj.animation_data.action is None:
        return out
    adt = obj.animation_data
    act = adt.action
    groups = []
    if hasattr(act, "layers") and adt.action_slot is not None:
        for layer in act.layers:
            for strip in layer.strips:
                cb = strip.channelbag(adt.action_slot)
                if cb is not None:
                    groups.append(cb.fcurves)
    elif hasattr(act, "fcurves"):
        groups.append(act.fcurves)
    for fcurves in groups:
        for fc in fcurves:
            entry = out.setdefault(fc.data_path, {"frames": [], "interps": {}})
            for kp in fc.keyframe_points:
                fr = round(float(kp.co[0]), 4)
                entry["frames"].append(fr)
                entry["interps"][str(fr)] = str(kp.interpolation)
    for entry in out.values():
        entry["frames"] = sorted(set(entry["frames"]))
    return out


def _sample_scene_at_frame(frame: int) -> Dict[str, Any]:
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()

    arm = bpy.data.objects["CharacterArmature"]
    root = bpy.data.objects["CharacterRoot"]

    bones_snap: Dict[str, Any] = {}
    for pb in arm.pose.bones:
        wmat = arm.matrix_world @ pb.matrix
        bones_snap[pb.name] = {
            "head_world": [float(v) for v in (arm.matrix_world @ pb.head)],
            "tail_world": [float(v) for v in (arm.matrix_world @ pb.tail)],
            "rot_euler": [float(v) for v in pb.rotation_euler],
            "wmat_diag": [float(wmat[i][i]) for i in range(4)],
        }

    ctrls_snap: Dict[str, Any] = {}
    for cname in CONTROLLERS_8:
        cobj = bpy.data.objects[cname]
        rmode = str(cobj.rotation_mode)
        rvals = (
            [float(v) for v in cobj.rotation_quaternion]
            if rmode == "QUATERNION"
            else [float(v) for v in cobj.rotation_axis_angle]
            if rmode == "AXIS_ANGLE"
            else [float(v) for v in cobj.rotation_euler]
        )
        ctrls_snap[cname] = {
            "location": [float(v) for v in cobj.location],
            "rotation_mode": rmode,
            "rot_vals": rvals,
        }

    infs_snap: Dict[str, float] = {}
    for side in ("L", "R"):
        infs_snap[f"ArmIK.{side}"] = float(arm.pose.bones[f"forearm.{side}"].constraints[ARM_IK_CONSTRAINT_NAMES[side]].influence)
        infs_snap[f"HandRotation.{side}"] = float(arm.pose.bones[f"hand.{side}"].constraints[HAND_ROT_CONSTRAINT_NAMES[side]].influence)

    return {
        "root_loc": [float(v) for v in root.location],
        "root_rot": [float(v) for v in root.rotation_euler],
        "bone_count": len(arm.pose.bones),
        "bones": bones_snap,
        "controllers": ctrls_snap,
        "influences": infs_snap,
    }


def _verify_worker(spec_path: str, out_path: str) -> int:
    with open(spec_path, "r", encoding="utf-8") as fp:
        spec = json.load(fp)

    arm = bpy.data.objects.get("CharacterArmature")
    root = bpy.data.objects.get("CharacterRoot")
    assert arm is not None and root is not None
    assert len(arm.pose.bones) == 19, f"Expected 19 bones, got {len(arm.pose.bones)}"

    # Verify FCurves & absence of any rejected/failed frame
    arm_fcs = _collect_fcurves_for(arm)
    root_fcs = _collect_fcurves_for(root)
    rejected_frames = [float(f) for f in spec["rejected_frames"]]
    expected_frames = [float(f) for f in spec["committed_frames"]]

    for owner_name, fc_map in [("root", root_fcs), ("arm", arm_fcs)] + [(c, _collect_fcurves_for(bpy.data.objects[c])) for c in CONTROLLERS_8]:
        for dp, info in fc_map.items():
            for rf in rejected_frames:
                assert rf not in info["frames"], f"Rejected frame {rf} polluted FCurve {owner_name}.{dp}"
            assert info["frames"] == expected_frames, f"Frame set mismatch on {owner_name}.{dp}: {info['frames']} != {expected_frames}"

    # Verify 4 influence FCurves interpolation == CONSTANT
    for side in ("L", "R"):
        for dp in (
            f'pose.bones["forearm.{side}"].constraints["{ARM_IK_CONSTRAINT_NAMES[side]}"].influence',
            f'pose.bones["hand.{side}"].constraints["{HAND_ROT_CONSTRAINT_NAMES[side]}"].influence',
        ):
            assert dp in arm_fcs, f"Missing influence FCurve {dp}"
            for fr_str, interp in arm_fcs[dp]["interps"].items():
                assert interp == "CONSTANT", f"Influence {dp} at frame {fr_str} is {interp}, expected CONSTANT"

    # Compare per-frame evaluated transforms on sampled frames
    max_pos_diff = 0.0
    max_rot_diff = 0.0
    max_inf_diff = 0.0
    for fr_str, expected_snap in spec["frame_snapshots"].items():
        actual_snap = _sample_scene_at_frame(int(fr_str))
        assert actual_snap["bone_count"] == expected_snap["bone_count"]
        for a, e in zip(actual_snap["root_loc"], expected_snap["root_loc"]):
            max_pos_diff = max(max_pos_diff, abs(a - e))
        for a, e in zip(actual_snap["root_rot"], expected_snap["root_rot"]):
            max_rot_diff = max(max_rot_diff, abs(a - e))
        for bname, eb in expected_snap["bones"].items():
            ab = actual_snap["bones"][bname]
            for key in ("head_world", "tail_world"):
                for a, e in zip(ab[key], eb[key]):
                    max_pos_diff = max(max_pos_diff, abs(a - e))
            for a, e in zip(ab["rot_euler"], eb["rot_euler"]):
                max_rot_diff = max(max_rot_diff, abs(a - e))
        for cname, ec in expected_snap["controllers"].items():
            ac = actual_snap["controllers"][cname]
            assert ac["rotation_mode"] == ec["rotation_mode"]
            for a, e in zip(ac["location"], ec["location"]):
                max_pos_diff = max(max_pos_diff, abs(a - e))
            for a, e in zip(ac["rot_vals"], ec["rot_vals"]):
                max_rot_diff = max(max_rot_diff, abs(a - e))
        for iname, ei in expected_snap["influences"].items():
            max_inf_diff = max(max_inf_diff, abs(actual_snap["influences"][iname] - ei))

    assert max_pos_diff < 1e-5, f"Reopen pos diff={max_pos_diff}"
    assert max_rot_diff < 1e-4, f"Reopen rot diff={max_rot_diff}"
    assert max_inf_diff < 1e-6, f"Reopen influence diff={max_inf_diff}"

    out = {
        "passed": True,
        "committed_frames_count": len(expected_frames),
        "rejected_frames_absent": spec["rejected_frames"],
        "max_pos_diff_m": max_pos_diff,
        "max_rot_diff_rad": max_rot_diff,
        "max_inf_diff": max_inf_diff,
    }
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(out, fp, indent=2)
    return 0


def _build_scene_1(out_blend: str) -> Dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    root = arm.parent or bpy.data.objects["CharacterRoot"]
    root.location = Vector((0.0, -8.0, 0.0))
    bpy.context.view_layer.update()

    bridge = KinematicBridgeExecutor(armature_obj=arm, root_obj=root)
    t_accum = 0.0
    for f in range(1, 13):
        if f == 6:
            # Inject mid-sequence failure at Frame 6 (ROM violation) before retrying cleanly
            bad_p = KinematicPlannedPose(
                frame=6,
                time_seconds=t_accum + (0.04 if f > 1 else 0.0),
                root_position=(0.0, -8.0 + 0.015 * (f - 1), 0.0),
                spine_rotation_deg=(85.0, 0.0, 0.0),
                foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
                foot_R=PlannedFootTarget((HIP_X_OFFSET, -8.0 + 0.02 * f, ANKLE_REST_Z + 0.02), is_locked=False),
            )
            assert bridge.execute_frame(bad_p, keyframe=True).success is False
        dt_f = 0.04 if f % 2 == 0 else 0.05
        if f > 1:
            t_accum += dt_f
        hand_l = PlannedHandTarget((-0.25, -7.70 + 0.02 * f, 1.24), enabled=(f >= 7), weight=1.0 if f >= 7 else 0.0)
        hand_r = PlannedHandTarget((0.25, -7.75 + 0.02 * f, 1.24), enabled=(f <= 6), weight=1.0 if f <= 6 else 0.0)
        p = KinematicPlannedPose(
            frame=f,
            time_seconds=t_accum,
            dt=dt_f,
            root_position=(0.0, -8.0 + 0.015 * (f - 1), 0.0),
            pelvis_location=(0.0, -0.02, 0.0),
            foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget((HIP_X_OFFSET, -8.0 + 0.015 * f, ANKLE_REST_Z + (0.02 if f > 1 else 0.0)), is_locked=(f == 1)),
            hand_L=hand_l,
            hand_R=hand_r,
            fk_joint_rotations_deg={
                "upper_arm.L": (10.0, 0.0, -4.0),
                "upper_arm.R": (-10.0, 0.0, 4.0),
            },
        )
        assert bridge.execute_frame(p, keyframe=True).success

    # Trailing rejected Frame 13 (must leave ZERO keyframes at frame 13)
    bad_tail = KinematicPlannedPose(
        frame=13,
        time_seconds=t_accum + 0.04,
        root_position=(0.0, -7.80, 0.0),
        foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), is_locked=True),
        foot_R=PlannedFootTarget((HIP_X_OFFSET, -5.0, ANKLE_REST_Z), is_locked=False, clamp_reach=False),
    )
    assert bridge.execute_frame(bad_tail, keyframe=True).success is False

    spec = {
        "committed_frames": list(range(1, 13)),
        "rejected_frames": [13],
        "frame_snapshots": {
            "1": _sample_scene_at_frame(1),
            "6": _sample_scene_at_frame(6),
            "12": _sample_scene_at_frame(12),
        },
    }
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    spec["blend_file"] = out_blend
    spec["blend_size_bytes"] = os.path.getsize(out_blend)
    spec["blend_sha256"] = _sha256_file(out_blend)
    return spec


def _build_scene_2(out_blend: str) -> Dict[str, Any]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    bpy.context.view_layer.update()

    env = EnvironmentQuery(ground_z=0.0)
    tw = TerrainWalkAction(
        route=TerrainRouteInput(start_pos=(0.0, -8.0, 0.0), target_pos=(0.0, -7.2, 0.0), nominal_stride_m=0.35),
        environment=env,
    )
    init_st = create_initial_motion_state(cfg, start_frame=1)
    dur = tw.estimate_duration_frames(init_st, cfg, environment=env)
    sec = (dur - 1) / float(cfg.fps)
    planner = MotionPlanner(
        cfg,
        armature_obj=arm,
        environment=env,
        sequence_duration_sec=sec,
        upper_limb_L=(
            UpperLimbSegment(
                mode="IK",
                start_time_sec=0.0,
                duration_sec=sec,
                wrist_start_xyz=(-0.24, 0.25, 1.24),
                wrist_end_xyz=(-0.24, 0.30, 1.26),
                position_space="ROOT_LOCAL",
            ),
        ),
        upper_limb_R=(
            UpperLimbSegment(
                mode="FK",
                start_time_sec=0.0,
                duration_sec=sec,
                fk_start_deg=((10.0, 0.0, -4.0), (15.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                fk_end_deg=((18.0, 0.0, -6.0), (22.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ),
        ),
    )
    planner.add_action(tw)
    res = planner.execute(initial_state=init_st)
    frames = [s.frame for s in res["states"]]
    mid_f = frames[len(frames) // 2]
    spec = {
        "committed_frames": frames,
        "rejected_frames": [frames[-1] + 5],
        "frame_snapshots": {
            str(frames[0]): _sample_scene_at_frame(frames[0]),
            str(mid_f): _sample_scene_at_frame(mid_f),
            str(frames[-1]): _sample_scene_at_frame(frames[-1]),
        },
    }
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)
    spec["blend_file"] = out_blend
    spec["blend_size_bytes"] = os.path.getsize(out_blend)
    spec["blend_sha256"] = _sha256_file(out_blend)
    return spec


def _run_orchestrator() -> int:
    os.makedirs(SCRATCH_REOPEN_DIR, exist_ok=True)
    report: Dict[str, Any] = {}
    all_ok = True
    try:
        for scene_id, builder in (
            ("scene1_bridge_mixed_retry", _build_scene_1),
            ("scene2_terrain_bilateral", _build_scene_2),
        ):
            blend_path = os.path.join(SCRATCH_REOPEN_DIR, f"{scene_id}.blend")
            spec_path = os.path.join(SCRATCH_REOPEN_DIR, f"{scene_id}_spec.json")
            worker_out = os.path.join(SCRATCH_REOPEN_DIR, f"{scene_id}_reopen_out.json")
            spec = builder(blend_path)
            with open(spec_path, "w", encoding="utf-8") as fp:
                json.dump(spec, fp, indent=2)

            cmd = [BLENDER_EXE, "-b", blend_path, "-P", __file__, "--", "--verify", spec_path, worker_out]
            proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode != 0:
                raise RuntimeError(f"Reopen worker failed for {scene_id} (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
            with open(worker_out, "r", encoding="utf-8") as fp:
                reopen_res = json.load(fp)
            assert reopen_res["passed"] is True
            report[scene_id] = {
                "blend_file": blend_path,
                "blend_size_bytes": spec["blend_size_bytes"],
                "blend_sha256": spec["blend_sha256"],
                "reopen_verification": reopen_res,
            }
            print(f"[PASS] {scene_id}: size={spec['blend_size_bytes']}B sha256={spec['blend_sha256'][:12]}... reopen={reopen_res}")
    except Exception as exc:
        all_ok = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        print(f"[FAIL] verify_reopen: {exc}", file=sys.stderr)
        traceback.print_exc()

    payload = {
        "group": "B20 & Section 11 — Automated Blender Save & Independent Process Reopen",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "visual_acceptance_status": "OWNER WAIVED",
        "passed": all_ok,
        "scenes": report,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if len(args) >= 3 and args[0] == "--verify":
            raise SystemExit(_verify_worker(args[1], args[2]))
    raise SystemExit(_run_orchestrator())
