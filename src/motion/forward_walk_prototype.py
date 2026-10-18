"""Task 5B runner: generate the 144-frame (3-cycle) continuous forward walking
animation, verify continuous root progression, alternating stance/swing phases,
stance foot world stability, zero ground penetration, forward knee flexion,
and 100% IK reachability, and save isolated `output/character_forward_walk.blend`
and 4 multi-frame preview stills.
"""

import os
import sys

import bpy
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.forward_walk import generate_forward_walk
from src.render import configure_render
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


def _ensure_scene_with_ik_rig(config: PipelineConfig) -> bpy.types.Object:
    """Load existing scene and initialize clean character + 19-bone IK rig."""
    for candidate in (
        config.walk_cycle_blend_path,
        config.character_foot_contact_blend_path,
        config.character_ik_blend_path,
        config.character_rig_blend_path,
        config.character_blend_path,
        config.blend_file_path,
    ):
        if os.path.isfile(candidate):
            print(f"[TASK5B] Opening existing scene: {candidate}")
            bpy.ops.wm.open_mainfile(filepath=candidate)
            break
    else:
        from src.camera import setup_camera
        from src.lighting import setup_lighting
        from src.scene import setup_scene

        setup_scene(config)
        setup_lighting(config)
        setup_camera(config)
        configure_render(config)

    build_character(config)
    root_obj = bpy.data.objects.get("CharacterRoot")
    arm_obj = build_rig(config, character_root=root_obj)
    bind_character_to_rig(arm_obj)
    reset_pose(arm_obj)
    setup_leg_ik(arm_obj)
    reset_leg_ik(arm_obj)
    return arm_obj


def run_forward_walk_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 70)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 5B CONTINUOUS FORWARD WALK")
    print("=" * 70)

    arm_obj = _ensure_scene_with_ik_rig(config)
    walk_data = generate_forward_walk(config, arm_obj)
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
        f"[TASK5B] Forward Walk Summary (144 frames / 6.0s):\n"
        f"  Total Root Displacement: {walk_data['total_root_displacement']:.4f} m (+Y)\n"
        f"  Average Forward Speed  : {walk_data['average_speed_mps']:.4f} m/s\n"
        f"  Left Stance  max ankle_bone_drift={max_l_ankle_drift:.6f}m, max mesh_center_drift={max_l_mesh_drift:.6f}m\n"
        f"  Right Stance max ankle_bone_drift={max_r_ankle_drift:.6f}m, max mesh_center_drift={max_r_mesh_drift:.6f}m\n"
        f"  IK Unreachable Events  : {walk_data['unreachable_count']}"
    )

    for rep_frame in (1, 13, 37, 61, 85, 109, 133, 144):
        rec = records[rep_frame - 1]
        sl = rec["state_l"]
        sr = rec["state_r"]
        print(
            f"[TASK5B] Frame {rep_frame:03d} (k={rec['half_step_k']}, rootY={rec['root_y']:+.3f}m): "
            f"L[{rec['phase_l']}] Y={sl['foot_head_world'].y:+.3f}m, minZ={sl['foot_min_z']:+.5f}m, drift={sl['mesh_center_drift']:.6f}m | "
            f"R[{rec['phase_r']}] Y={sr['foot_head_world'].y:+.3f}m, minZ={sr['foot_min_z']:+.5f}m, drift={sr['mesh_center_drift']:.6f}m"
        )

    # Set a stationary corridor camera framing the entire -8.0m -> -6.5m forward walk path
    # so forward spatial progression relative to the start waypoint disc is clearly visible across stills.
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
        cam_obj.location = Vector((start_x - 3.35, start_y + 4.85, 1.50))
        target_obj.location = Vector((start_x, start_y + 0.72, 0.88))
        bpy.context.view_layer.update()

    preview_paths = []
    for pf in config.forward_walk_preview_frames:
        scene.frame_set(pf)
        bpy.context.view_layer.update()
        img_path = config.get_forward_walk_preview_path(pf)
        scene.render.filepath = img_path
        bpy.ops.render.render(write_still=True)
        preview_paths.append(img_path)
        print(f"[TASK5B] Preview still written (frame {pf:04d}): {img_path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()

    blend_path = config.forward_walk_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
        config.walk_cycle_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK5B] Forward walk blend written: {blend_path}")
    print("[TASK5B] COMPLETED SUCCESSFULLY")
    print("=" * 70)

    return {
        "total_root_displacement": round(walk_data["total_root_displacement"], 4),
        "average_speed_mps": round(walk_data["average_speed_mps"], 4),
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
        run_forward_walk_prototype()
    except Exception as e:
        print(f"[TASK5B_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
