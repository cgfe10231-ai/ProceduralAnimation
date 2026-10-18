"""Task 6B runner: execute the 96-frame (4 cycles x 24 frames, 4.0s @ 24 FPS) procedural
forward running prototype (`RunAction`) via `MotionPlanner`, log key metrics, render
representative preview stills (`frames 4, 10, 16, 22, 58`), and save isolated
`output/character_run_prototype.blend`.
"""

import os
import sys

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import PipelineConfig
from src.motion.forward_walk_prototype import _ensure_scene_with_ik_rig
from src.motion.run_cycle import run_task6b_via_motion_framework
from src.render import configure_render


def run_run_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 74)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 6B PROCEDURAL RUNNING (RunAction)")
    print("=" * 74)

    arm_obj = _ensure_scene_with_ik_rig(config)
    plan_data = run_task6b_via_motion_framework(config, arm_obj)
    records = plan_data["frame_records"]
    action_res = plan_data["action_results"][0]
    metrics = action_res.metrics

    stance_l_ankle_drifts = [
        r["state_l"]["ankle_bone_drift"] for r in records if r["phase_l"] == "stance"
    ]
    stance_r_ankle_drifts = [
        r["state_r"]["ankle_bone_drift"] for r in records if r["phase_r"] == "stance"
    ]
    stance_l_mesh_drifts = [
        r["state_l"]["mesh_center_drift"] for r in records if r["phase_l"] == "stance"
    ]
    stance_r_mesh_drifts = [
        r["state_r"]["mesh_center_drift"] for r in records if r["phase_r"] == "stance"
    ]
    max_l_ankle_drift = max(stance_l_ankle_drifts)
    max_r_ankle_drift = max(stance_r_ankle_drifts)
    max_l_mesh_drift = max(stance_l_mesh_drifts)
    max_r_mesh_drift = max(stance_r_mesh_drifts)

    flight_records = [r for r in records if r["is_airborne"]]
    min_flight_foot_z_l = min(r["state_l"]["foot_min_z"] for r in flight_records)
    min_flight_foot_z_r = min(r["state_r"]["foot_min_z"] for r in flight_records)
    max_flight_foot_z_l = max(r["state_l"]["foot_min_z"] for r in flight_records)
    max_flight_foot_z_r = max(r["state_r"]["foot_min_z"] for r in flight_records)

    print(
        f"[TASK6B] Procedural Run Summary ({plan_data['total_frames']} frames / {plan_data['total_frames'] / config.fps:.2f}s):\n"
        f"  Action Executed        : {plan_data['action_names']} via MotionPlanner\n"
        f"  Forward Speed          : {metrics['speed_mps']:.4f} m/s (vs Walk 0.2400 m/s)\n"
        f"  Step / Stride Length   : step={metrics['step_length']:.4f} m, stride={metrics['stride_length']:.4f} m\n"
        f"  Cycle Structure        : {metrics['cycle_frames']} frames ({metrics['cycle_frames'] / config.fps:.2f}s) = "
        f"7f stance_L + 5f flight_1 + 7f stance_R + 5f flight_2\n"
        f"  Airborne Time per Cycle: {2 * metrics['flight_frames_per_step']} frames "
        f"({(2 * metrics['flight_frames_per_step']) / config.fps:.4f}s, {100.0 * (2 * metrics['flight_frames_per_step']) / metrics['cycle_frames']:.1f}% of cycle)\n"
        f"  Total Airborne Frames  : {metrics['airborne_frames_total']} / {plan_data['total_frames']} frames\n"
        f"  Flight Foot Clearance  : L min_z in [{min_flight_foot_z_l:+.4f}, {max_flight_foot_z_l:+.4f}] m, "
        f"R min_z in [{min_flight_foot_z_r:+.4f}, {max_flight_foot_z_r:+.4f}] m\n"
        f"  Total Root Displacement: {plan_data['total_root_displacement']:.4f} m (+Y)\n"
        f"  Left Stance  max ankle_drift={max_l_ankle_drift:.6f}m, max mesh_drift={max_l_mesh_drift:.6f}m\n"
        f"  Right Stance max ankle_drift={max_r_ankle_drift:.6f}m, max mesh_drift={max_r_mesh_drift:.6f}m\n"
        f"  IK Unreachable Events  : {plan_data['unreachable_count']}"
    )

    for rep_frame in (1, 4, 7, 10, 13, 16, 19, 22, 25, 58, 96):
        rec = records[rep_frame - 1]
        sl = rec["state_l"]
        sr = rec["state_r"]
        print(
            f"[TASK6B] Frame {rep_frame:03d} ({rec['cycle_phase']:8s}, air={str(rec['is_airborne']):5s}, "
            f"rootY={rec['root_y']:+.4f}m, pelvis_dZ={rec['pelvis_dz']:+.4f}m): "
            f"L[{rec['phase_l']:6s}] Y={sl['foot_head_world'].y:+.3f}m, minZ={sl['foot_min_z']:+.4f}m | "
            f"R[{rec['phase_r']:6s}] Y={sr['foot_head_world'].y:+.3f}m, minZ={sr['foot_min_z']:+.4f}m"
        )

    start_x, start_y, _ = config.character_path_points[0]
    configure_render(config)
    scene = bpy.context.scene

    cam_obj = bpy.data.objects.get("PipelineCamera")
    target_obj = bpy.data.objects.get("CameraLookAtTarget")
    if cam_obj and target_obj:
        if cam_obj.animation_data:
            cam_obj.animation_data_clear()
        if target_obj.animation_data:
            target_obj.animation_data_clear()
        # Frame the -8.0m -> -4.4375m running corridor from a 3/4 side-front angle
        cam_obj.location = Vector((start_x - 3.60, start_y + 5.60, 1.55))
        target_obj.location = Vector((start_x, start_y + 1.65, 0.88))
        bpy.context.view_layer.update()

    preview_paths = []
    for pf in config.run_preview_frames:
        scene.frame_set(pf)
        bpy.context.view_layer.update()
        img_path = config.get_run_preview_path(pf)
        scene.render.filepath = img_path
        bpy.ops.render.render(write_still=True)
        preview_paths.append(img_path)
        print(f"[TASK6B] Preview still written (frame {pf:04d}): {img_path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()

    blend_path = config.run_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
        config.walk_cycle_blend_path,
        config.forward_walk_blend_path,
        config.start_stop_blend_path,
        config.motion_framework_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK6B] Run prototype blend written: {blend_path}")
    print("[TASK6B] COMPLETED SUCCESSFULLY")
    print("=" * 74)

    return {
        "speed_mps": round(metrics["speed_mps"], 4),
        "step_length": round(metrics["step_length"], 4),
        "stride_length": round(metrics["stride_length"], 4),
        "cycle_frames": metrics["cycle_frames"],
        "airborne_frames_total": metrics["airborne_frames_total"],
        "total_root_displacement": round(plan_data["total_root_displacement"], 4),
        "max_l_ankle_drift": round(max_l_ankle_drift, 6),
        "max_r_ankle_drift": round(max_r_ankle_drift, 6),
        "min_flight_foot_z_l": round(min_flight_foot_z_l, 5),
        "min_flight_foot_z_r": round(min_flight_foot_z_r, 5),
        "unreachable_count": plan_data["unreachable_count"],
        "blend_path": blend_path,
        "preview_paths": preview_paths,
    }


if __name__ == "__main__":
    try:
        run_run_prototype()
    except Exception as exc:
        print(f"[TASK6B_FATAL_ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
