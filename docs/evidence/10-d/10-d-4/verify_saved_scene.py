"""Standalone Blender 5.1.1 post-save scene verifier for TASK 10-d-4.

Opens a saved .blend file via bpy.ops.wm.open_mainfile() in an isolated
Blender process and verifies WITHOUT re-running MotionPlanner or
WholeBodyController:
1. Scene / character / rig / controller invariants (19 bones, camera framing,
   timeline coverage, FK/IK controllers and constraints preserved).
2. Action Slot / Channelbag FCurves for the four upper-limb constraint
   influences (existence, full frame keyframe coverage, CONSTANT interpolation).
3. T11 frame-by-frame playback fidelity across Forward, Reverse, and
   Fixed-Seed Shuffled scene.frame_set() traversal orders against raw-precision
   pre-save measurements.
4. Optional T15 rotation_mode & controller channel verification mode.
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector


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

UPPER_LIMB_CONTROLLERS = ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R")
LEG_IK_CONTROLLERS = ("FootIK.L", "FootIK.R", "KneePole.L", "KneePole.R")

UPPER_LIMB_CONSTRAINT_SPECS = (
    ("ArmIK.L", "forearm.L", 'pose.bones["forearm.L"].constraints["ArmIK.L"].influence'),
    ("ArmIK.R", "forearm.R", 'pose.bones["forearm.R"].constraints["ArmIK.R"].influence'),
    ("HandRotation.L", "hand.L", 'pose.bones["hand.L"].constraints["HandRotation.L"].influence'),
    ("HandRotation.R", "hand.R", 'pose.bones["hand.R"].constraints["HandRotation.R"].influence'),
)


def _quat_angle_rad(q1: Quaternion, q2: Quaternion) -> float:
    """Numerically stable shortest rotation angle (rad) without acos float32 ULP amplification."""
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


def _matrix_to_lists(mat: Matrix) -> List[List[float]]:
    return [[float(mat[r][c]) for c in range(4)] for r in range(4)]


def _lists_to_matrix(rows: List[List[float]]) -> Matrix:
    return Matrix([tuple(float(v) for v in row) for row in rows])


def _get_slot_fcurves(obj: bpy.types.Object) -> Tuple[Optional[str], List[Any]]:
    anim = obj.animation_data
    if anim is None or anim.action is None:
        return (None, [])
    action = anim.action
    slot = getattr(anim, "action_slot", None)
    slot_id = getattr(slot, "identifier", None) if slot is not None else None
    fcurves: List[Any] = []
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


def _extract_controller_rot_channel(obj: bpy.types.Object) -> Tuple[str, List[float]]:
    mode = str(obj.rotation_mode)
    if mode == "QUATERNION":
        vals = [float(v) for v in obj.rotation_quaternion]
    elif mode == "AXIS_ANGLE":
        vals = [float(v) for v in obj.rotation_axis_angle]
    else:
        vals = [float(v) for v in obj.rotation_euler]
    return (mode, vals)


def capture_scene_frame_sample(arm_obj: bpy.types.Object, root_obj: bpy.types.Object, frame: int) -> Dict[str, Any]:
    """Capture raw unrounded evaluated transforms, bones, controllers, and influences."""
    bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()

    root_mat = root_obj.matrix_world.copy()
    arm_mat = arm_obj.matrix_world.copy()

    bones_data: Dict[str, Any] = {}
    for bname in UPPER_LIMB_BONES:
        pb = arm_obj.pose.bones[bname]
        w_mat = arm_mat @ pb.matrix
        bones_data[bname] = {
            "world_matrix": _matrix_to_lists(w_mat),
            "world_quat": [float(v) for v in w_mat.to_3x3().normalized().to_quaternion()],
            "world_head": [float(v) for v in (arm_mat @ pb.head)],
            "world_tail": [float(v) for v in (arm_mat @ pb.tail)],
            "basis_euler_xyz_rad": [float(v) for v in pb.matrix_basis.to_euler("XYZ")],
        }

    wrist_world_L = [float(v) for v in (arm_mat @ arm_obj.pose.bones["forearm.L"].tail)]
    wrist_world_R = [float(v) for v in (arm_mat @ arm_obj.pose.bones["forearm.R"].tail)]
    elbow_world_L = [float(v) for v in (arm_mat @ arm_obj.pose.bones["upper_arm.L"].tail)]
    elbow_world_R = [float(v) for v in (arm_mat @ arm_obj.pose.bones["upper_arm.R"].tail)]

    controllers: Dict[str, Any] = {}
    for cname in UPPER_LIMB_CONTROLLERS:
        cobj = bpy.data.objects[cname]
        c_mat = cobj.matrix_world.copy()
        rmode, rvals = _extract_controller_rot_channel(cobj)
        controllers[cname] = {
            "rotation_mode": rmode,
            "rotation_channel": rvals,
            "world_pos": [float(v) for v in c_mat.translation],
            "world_quat": [float(v) for v in c_mat.to_3x3().normalized().to_quaternion()],
            "world_matrix": _matrix_to_lists(c_mat),
        }

    influences: Dict[str, float] = {}
    for cname, bname, _ in UPPER_LIMB_CONSTRAINT_SPECS:
        con = arm_obj.pose.bones[bname].constraints[cname]
        influences[cname] = float(con.influence)

    return {
        "frame": int(frame),
        "root_world_pos": [float(v) for v in root_mat.translation],
        "root_world_matrix": _matrix_to_lists(root_mat),
        "root_world_quat": [float(v) for v in root_mat.to_3x3().normalized().to_quaternion()],
        "wrist_world_L": wrist_world_L,
        "wrist_world_R": wrist_world_R,
        "elbow_world_L": elbow_world_L,
        "elbow_world_R": elbow_world_R,
        "elbow_pole_world_L": controllers["ElbowPole.L"]["world_pos"],
        "elbow_pole_world_R": controllers["ElbowPole.R"]["world_pos"],
        "bones": bones_data,
        "controllers": controllers,
        "influences": influences,
    }


def _check_traversal_order(
    order_name: str,
    frames: List[int],
    arm_obj: bpy.types.Object,
    root_obj: bpy.types.Object,
    expected_by_frame: Dict[int, Dict[str, Any]],
    pos_tol_m: float = 1e-5,
    rot_tol_rad: float = 1e-4,
    inf_tol: float = 1e-6,
) -> Dict[str, Any]:
    max_pos_err = 0.0
    max_rot_err = 0.0
    max_inf_err = 0.0
    failures: List[Dict[str, Any]] = []

    for f in frames:
        exp = expected_by_frame[f]
        actual = capture_scene_frame_sample(arm_obj, root_obj, f)

        # Position checks: root, wrist L/R, elbow L/R, ElbowPole L/R
        pos_pairs = [
            ("root_world_pos", exp["root_world_pos"], actual["root_world_pos"]),
            ("wrist_world_L", exp["wrist_world_L"], actual["wrist_world_L"]),
            ("wrist_world_R", exp["wrist_world_R"], actual["wrist_world_R"]),
            ("elbow_world_L", exp["elbow_world_L"], actual["elbow_world_L"]),
            ("elbow_world_R", exp["elbow_world_R"], actual["elbow_world_R"]),
            ("elbow_pole_world_L", exp["elbow_pole_world_L"], actual["elbow_pole_world_L"]),
            ("elbow_pole_world_R", exp["elbow_pole_world_R"], actual["elbow_pole_world_R"]),
        ]
        for label, e_xyz, a_xyz in pos_pairs:
            err = (Vector(a_xyz) - Vector(e_xyz)).length
            max_pos_err = max(max_pos_err, err)
            if err > pos_tol_m:
                failures.append({
                    "frame": f,
                    "metric": label,
                    "error": err,
                    "tolerance": pos_tol_m,
                    "expected": e_xyz,
                    "actual": a_xyz,
                })

        # Rotation checks: root, 8 upper-limb bones, 4 controllers
        rot_pairs: List[Tuple[str, Quaternion, Quaternion]] = [
            ("root_world_quat", Quaternion(exp["root_world_quat"]), Quaternion(actual["root_world_quat"]))
        ]
        for bname in UPPER_LIMB_BONES:
            rot_pairs.append((
                f"bone:{bname}",
                Quaternion(exp["bones"][bname]["world_quat"]),
                Quaternion(actual["bones"][bname]["world_quat"]),
            ))
        for cname in UPPER_LIMB_CONTROLLERS:
            rot_pairs.append((
                f"controller:{cname}",
                Quaternion(exp["controllers"][cname]["world_quat"]),
                Quaternion(actual["controllers"][cname]["world_quat"]),
            ))
            if exp["controllers"][cname]["rotation_mode"] != actual["controllers"][cname]["rotation_mode"]:
                failures.append({
                    "frame": f,
                    "metric": f"controller:{cname}.rotation_mode",
                    "expected": exp["controllers"][cname]["rotation_mode"],
                    "actual": actual["controllers"][cname]["rotation_mode"],
                })

        for label, e_q, a_q in rot_pairs:
            r_err = _quat_angle_rad(e_q, a_q)
            max_rot_err = max(max_rot_err, r_err)
            if r_err > rot_tol_rad:
                failures.append({
                    "frame": f,
                    "metric": label,
                    "error": r_err,
                    "tolerance": rot_tol_rad,
                })

        # Influence checks
        for cname, _, _ in UPPER_LIMB_CONSTRAINT_SPECS:
            i_err = abs(actual["influences"][cname] - exp["influences"][cname])
            max_inf_err = max(max_inf_err, i_err)
            if i_err > inf_tol:
                failures.append({
                    "frame": f,
                    "metric": f"influence:{cname}",
                    "error": i_err,
                    "tolerance": inf_tol,
                    "expected": exp["influences"][cname],
                    "actual": actual["influences"][cname],
                })

    return {
        "order": order_name,
        "frames_checked": len(frames),
        "max_pos_err_m": max_pos_err,
        "max_rot_err_rad": max_rot_err,
        "max_inf_err": max_inf_err,
        "failure_count": len(failures),
        "failures": failures,
        "passed": len(failures) == 0,
    }


def verify_saved_blend(
    blend_path: str,
    measurements_path: str,
    scene_key: str,
    shuffle_seed: int = 20261126,
    check_influences_fcurves: bool = True,
) -> Dict[str, Any]:
    with open(measurements_path, "r", encoding="utf-8") as fp:
        all_measurements = json.load(fp)
    if scene_key not in all_measurements:
        raise KeyError(f"Scene key {scene_key!r} missing from {measurements_path}")

    scene_data = all_measurements[scene_key]
    frame_start = int(scene_data["frame_start"])
    frame_end = int(scene_data["frame_end"])
    expected_frames: Dict[int, Dict[str, Any]] = {
        int(rec["frame"]): rec for rec in scene_data["frames"]
    }

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_path))
    scene = bpy.context.scene
    arm_obj = bpy.data.objects.get("CharacterArmature")
    root_obj = bpy.data.objects.get("CharacterRoot")

    invariants: Dict[str, Any] = {
        "blend_path": os.path.abspath(blend_path),
        "scene_key": scene_key,
        "armature_present": arm_obj is not None and arm_obj.type == "ARMATURE",
        "root_present": root_obj is not None,
        "bone_count": len(arm_obj.data.bones) if arm_obj is not None else 0,
        "timeline_frame_start": int(scene.frame_start),
        "timeline_frame_end": int(scene.frame_end),
        "expected_frame_start": frame_start,
        "expected_frame_end": frame_end,
        "has_animation_data": bool(arm_obj and arm_obj.animation_data and arm_obj.animation_data.action),
        "has_active_camera": scene.camera is not None and scene.camera.type == "CAMERA",
        "camera_name": scene.camera.name if scene.camera is not None else None,
        "missing_upper_controllers": [
            c for c in UPPER_LIMB_CONTROLLERS if bpy.data.objects.get(c) is None
        ],
        "missing_leg_controllers": [
            c for c in LEG_IK_CONTROLLERS if bpy.data.objects.get(c) is None
        ],
        "missing_upper_constraints": [],
    }

    if arm_obj is not None:
        for cname, bname, _ in UPPER_LIMB_CONSTRAINT_SPECS:
            pb = arm_obj.pose.bones.get(bname)
            if pb is None or cname not in pb.constraints:
                invariants["missing_upper_constraints"].append(f"{bname}/{cname}")

    assert invariants["armature_present"], "CharacterArmature missing after open_mainfile"
    assert invariants["root_present"], "CharacterRoot missing after open_mainfile"
    assert invariants["bone_count"] == 19, f"Expected 19 bones, got {invariants['bone_count']}"
    assert invariants["timeline_frame_start"] == frame_start
    assert invariants["timeline_frame_end"] == frame_end
    assert invariants["has_animation_data"], "Armature animation_data/action missing"
    assert invariants["has_active_camera"], "Scene active camera missing"
    assert not invariants["missing_upper_controllers"], f"Missing upper controllers: {invariants['missing_upper_controllers']}"
    assert not invariants["missing_leg_controllers"], f"Missing leg controllers: {invariants['missing_leg_controllers']}"
    assert not invariants["missing_upper_constraints"], f"Missing upper constraints: {invariants['missing_upper_constraints']}"

    # Action Slot / Channelbag Influence FCurve verification
    slot_id, fcurves = _get_slot_fcurves(arm_obj)
    fc_by_path = {fc.data_path: fc for fc in fcurves}
    expected_frame_set = set(range(frame_start, frame_end + 1))

    influence_fcurve_checks: Dict[str, Any] = {}
    if check_influences_fcurves:
        assert slot_id is not None, "Armature action_slot missing in opened Blender 5.1.1 scene"
        for cname, _, data_path in UPPER_LIMB_CONSTRAINT_SPECS:
            fc = fc_by_path.get(data_path)
            assert fc is not None, f"Missing FCurve in active Action Slot for {data_path}"
            kp_frames = [int(round(kp.co[0])) for kp in fc.keyframe_points]
            kp_interps = sorted({str(kp.interpolation) for kp in fc.keyframe_points})
            missing_cov = sorted(expected_frame_set - set(kp_frames))
            extra_cov = sorted(set(kp_frames) - expected_frame_set)
            assert not missing_cov, f"{cname} FCurve missing frames: {missing_cov}"
            assert not extra_cov, f"{cname} FCurve has unexpected extra frames: {extra_cov}"
            assert kp_interps == ["CONSTANT"], f"{cname} expected CONSTANT interpolation only, got {kp_interps}"
            influence_fcurve_checks[cname] = {
                "data_path": data_path,
                "keyframe_count": len(fc.keyframe_points),
                "min_frame": min(kp_frames),
                "max_frame": max(kp_frames),
                "interpolations": kp_interps,
                "passed": True,
            }

    forward_frames = list(range(frame_start, frame_end + 1))
    reverse_frames = list(reversed(forward_frames))
    shuffled_frames = list(forward_frames)
    random.Random(shuffle_seed).shuffle(shuffled_frames)

    traversals = [
        _check_traversal_order("forward", forward_frames, arm_obj, root_obj, expected_frames),
        _check_traversal_order("reverse", reverse_frames, arm_obj, root_obj, expected_frames),
        _check_traversal_order(f"shuffled_seed_{shuffle_seed}", shuffled_frames, arm_obj, root_obj, expected_frames),
    ]
    all_traversals_passed = all(t["passed"] for t in traversals)
    assert all_traversals_passed, f"Playback traversal mismatch: {traversals}"

    return {
        "passed": True,
        "invariants": invariants,
        "action_slot_identifier": slot_id,
        "influence_fcurve_checks": influence_fcurve_checks,
        "traversals": traversals,
    }


def _parse_cli(argv: List[str]) -> Dict[str, str]:
    args: Dict[str, str] = {}
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--") and i + 1 < len(argv):
            args[tok[2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return args


def main() -> int:
    argv = sys.argv
    if "--" not in argv:
        raise RuntimeError("Usage: blender ... --python verify_saved_scene.py -- --blend <path> --measurements <json> --scene-key <key> --report <json>")
    cli = _parse_cli(argv[argv.index("--") + 1 :])
    check_inf = cli.get("check-influences", "1") != "0"
    seed = int(cli.get("seed", "20261126"))
    result = verify_saved_blend(
        blend_path=cli["blend"],
        measurements_path=cli["measurements"],
        scene_key=cli["scene-key"],
        shuffle_seed=seed,
        check_influences_fcurves=check_inf,
    )
    report_path = cli.get("report")
    if report_path:
        os.makedirs(os.path.dirname(os.path.abspath(report_path)), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as fp:
            json.dump(result, fp, indent=2)
    print(f"VERIFY_SAVED_SCENE_PASS {cli['scene-key']} -> {os.path.abspath(cli['blend'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
