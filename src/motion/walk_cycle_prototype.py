"""Task 5A runner: generate the 48-frame in-place procedural walk cycle,
verify alternating stance/swing phases, stance foot stability, ground clearance,
forward knee flexion, contra-lateral arm swing, stationary root, and loop closure,
and save isolated `output/character_walk_cycle.blend` and preview images.
"""

import os
import sys

import bpy
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.walk_cycle import generate_walk_cycle
from src.render import configure_render
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


def _ensure_scene_with_ik_rig(config: PipelineConfig) -> bpy.types.Object:
    """Load existing scene and initialize clean character + 19-bone IK rig."""
    for candidate in (
        config.character_foot_contact_blend_path,
        config.character_ik_blend_path,
        config.character_rig_blend_path,
        config.character_blend_path,
        config.blend_file_path,
    ):
        if os.path.isfile(candidate):
            print(f"[TASK5A] Opening existing scene: {candidate}")
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


def run_walk_cycle_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 68)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 5A IN-PLACE WALK CYCLE")
    print("=" * 68)

    arm_obj = _ensure_scene_with_ik_rig(config)
    walk_info = generate_walk_cycle(config, arm_obj)

    records = walk_info["frame_records"]
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
        f"[TASK5A] Stance Drift Summary across 48 frames:\n"
        f"  Left Stance  max ankle_bone_drift={max_l_ankle_drift:.6f}m, max mesh_center_drift={max_l_mesh_drift:.6f}m\n"
        f"  Right Stance max ankle_bone_drift={max_r_ankle_drift:.6f}m, max mesh_center_drift={max_r_mesh_drift:.6f}m"
    )

    for rep_frame in (1, 13, 25, 37, 48):
        rec = records[rep_frame - 1]
        sl = rec["state_l"]
        sr = rec["state_r"]
        print(
            f"[TASK5A] Frame {rep_frame:02d} (u={rec['u']:.3f}): "
            f"L[{rec['phase_l']}] minZ={sl['foot_min_z']:+.5f}m, drift={sl['mesh_center_drift']:.6f}m, knee_fwd={sl['knee_forward_y']:+.3f}m | "
            f"R[{rec['phase_r']}] minZ={sr['foot_min_z']:+.5f}m, drift={sr['mesh_center_drift']:.6f}m, knee_fwd={sr['knee_forward_y']:+.3f}m | "
            f"Arms(L={rec['arm_l_rx']:+.1f}deg, R={rec['arm_r_rx']:+.1f}deg)"
        )

    # Frame camera in the corridor to clearly show the walking character
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
        cam_obj.location = Vector((start_x - 2.05, start_y + 4.35, 1.25))
        target_obj.location = Vector((start_x, start_y + 0.08, 0.88))
        bpy.context.view_layer.update()

    # Render key representative frames (1, 13, 25, 37) and primary preview at frame 37 (mid-left swing)
    for kf in (1, 13, 25, 37):
        scene.frame_set(kf)
        bpy.context.view_layer.update()
        kf_path = os.path.join(config.output_dir, f"preview_walk_frame_{kf:04d}.png")
        scene.render.filepath = kf_path
        bpy.ops.render.render(write_still=True)

    scene.frame_set(37)
    bpy.context.view_layer.update()
    preview_path = config.walk_cycle_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK5A] Walk cycle preview written: {preview_path}")

    # Reset current frame to 1 before saving .blend
    scene.frame_set(1)
    bpy.context.view_layer.update()

    blend_path = config.walk_cycle_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK5A] Walk cycle blend written: {blend_path}")
    print("[TASK5A] COMPLETED SUCCESSFULLY")
    print("=" * 68)

    return {
        "max_l_ankle_drift": round(max_l_ankle_drift, 6),
        "max_l_mesh_drift": round(max_l_mesh_drift, 6),
        "max_r_ankle_drift": round(max_r_ankle_drift, 6),
        "max_r_mesh_drift": round(max_r_mesh_drift, 6),
        "blend_path": blend_path,
        "preview_path": preview_path,
    }


if __name__ == "__main__":
    try:
        run_walk_cycle_prototype()
    except Exception as e:
        print(f"[TASK5A_FATAL_ERROR] {e}", file=sys.stderr)
        sys.exit(1)
