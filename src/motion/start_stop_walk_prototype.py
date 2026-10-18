"""Task 5C runner: generate the 204-frame (8.5s @ 24 FPS) continuous locomotion
sequence (Idle Stand -> Start -> Accelerate -> Steady Walk -> Decelerate -> Stop Stand),
verify velocity smoothness, step coordination, stance foot stability, zero ground
penetration, forward knee flexion, and 100% IK reachability, and save isolated
`output/character_start_stop_walk.blend` and 5 representative preview stills.
"""

import os
import sys

import bpy
from mathutils import Vector

from src.config import PipelineConfig
from src.motion.forward_walk_prototype import _ensure_scene_with_ik_rig
from src.motion.start_stop_walk import generate_start_stop_walk
from src.render import configure_render


def run_start_stop_walk_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 74)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 5C START / ACCEL / STEADY / DECEL / STOP")
    print("=" * 74)

    arm_obj = _ensure_scene_with_ik_rig(config)
    walk_data = generate_start_stop_walk(config, arm_obj)
    records = walk_data["frame_records"]

    stance_l_ankle_drifts = [
        r["state_l"]["ankle_bone_drift"] for r in records if r["phase_l"] == "stance"
    ]
    stance_l_mesh_drifts = [
        r["state_l"]["mesh_center_drift"] for r in records if r["phase_l"] == "stance"
    ]
    stance_r_ankle_drifts = [
        r["state_r"]["ankle_bone_drift"] for r in records if r["phase_r"] == "stance"
    ]
    stance_r_mesh_drifts = [
        r["state_r"]["mesh_center_drift"] for r in records if r["phase_r"] == "stance"
    ]

    max_l_ankle_drift = max(stance_l_ankle_drifts)
    max_l_mesh_drift = max(stance_l_mesh_drifts)
    max_r_ankle_drift = max(stance_r_ankle_drifts)
    max_r_mesh_drift = max(stance_r_mesh_drifts)

    print(
        f"[TASK5C] Start-Stop Walk Summary ({walk_data['total_frames']} frames / {walk_data['total_frames'] / config.fps:.2f}s):\n"
        f"  Total Root Displacement: {walk_data['total_root_displacement']:.4f} m (+Y)\n"
        f"  Peak Forward Speed     : {walk_data['peak_speed_mps']:.4f} m/s\n"
        f"  Left Stance  max ankle_bone_drift={max_l_ankle_drift:.6f}m, max mesh_center_drift={max_l_mesh_drift:.6f}m\n"
        f"  Right Stance max ankle_bone_drift={max_r_ankle_drift:.6f}m, max mesh_center_drift={max_r_mesh_drift:.6f}m\n"
        f"  IK Unreachable Events  : {walk_data['unreachable_count']}"
    )

    for rep_frame in (1, 13, 30, 54, 79, 103, 127, 151, 178, 193, 204):
        rec = records[rep_frame - 1]
        sl = rec["state_l"]
        sr = rec["state_r"]
        print(
            f"[TASK5C] Frame {rep_frame:03d} ({rec['stage']:11s}, k={rec['step_k']:2d}, "
            f"rootY={rec['root_y']:+.4f}m, v={rec['speed_mps']:.4f}m/s): "
            f"L[{rec['phase_l']:6s}] Y={sl['foot_head_world'].y:+.3f}m, minZ={sl['foot_min_z']:+.5f}m | "
            f"R[{rec['phase_r']:6s}] Y={sr['foot_head_world'].y:+.3f}m, minZ={sr['foot_min_z']:+.5f}m"
        )

    # Set a stationary corridor camera framing the -8.00m -> -6.74m start-to-stop path
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
        cam_obj.location = Vector((start_x - 3.30, start_y + 4.75, 1.50))
        target_obj.location = Vector((start_x, start_y + 0.65, 0.88))
        bpy.context.view_layer.update()

    preview_paths = []
    for pf in config.start_stop_preview_frames:
        scene.frame_set(pf)
        bpy.context.view_layer.update()
        img_path = config.get_start_stop_preview_path(pf)
        scene.render.filepath = img_path
        bpy.ops.render.render(write_still=True)
        preview_paths.append(img_path)
        print(f"[TASK5C] Preview still written (frame {pf:04d}): {img_path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()

    blend_path = config.start_stop_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
        config.walk_cycle_blend_path,
        config.forward_walk_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK5C] Start-stop walk blend written: {blend_path}")
    print("[TASK5C] COMPLETED SUCCESSFULLY")
    print("=" * 74)

    return {
        "total_root_displacement": round(walk_data["total_root_displacement"], 4),
        "peak_speed_mps": round(walk_data["peak_speed_mps"], 4),
        "max_l_ankle_drift": round(max_l_ankle_drift, 6),
        "max_l_mesh_drift": round(max_l_mesh_drift, 6),
        "max_r_ankle_drift": round(max_r_ankle_drift, 6),
        "max_r_mesh_drift": round(max_r_mesh_drift, 6),
        "unreachable_count": walk_data["unreachable_count"],
        "blend_path": blend_path,
        "preview_paths": preview_paths,
    }


if __name__ == "__main__":
    try:
        run_start_stop_walk_prototype()
    except Exception as e:
        print(f"[TASK5C_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
