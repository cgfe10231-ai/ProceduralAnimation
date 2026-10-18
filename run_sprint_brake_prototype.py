"""Task 6D runner: chained sprint start + sprint braking & sudden stop via MotionPlanner.
Saves isolated output/character_sprint_brake_prototype.blend and key previews."""

import os
import sys

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import PipelineConfig
from src.motion.forward_walk_prototype import _ensure_scene_with_ik_rig
from src.motion.sprint_brake import run_task6d_via_motion_framework
from src.render import configure_render


def run_sprint_brake_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()
    print("=" * 74)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 6D SPRINT BRAKING & SUDDEN STOP")
    print("=" * 74)

    arm_obj = _ensure_scene_with_ik_rig(config)
    plan = run_task6d_via_motion_framework(config, arm_obj, include_sprint_start=True)
    records = plan["frame_records"]
    fin = plan["final_state"]

    print(f"[TASK6D] Total actions: {len(plan['action_results'])} ({plan['action_names']})")
    print(f"[TASK6D] Total frames: {plan['total_frames']} (Timeline {records[0]['frame']}..{records[-1]['frame']})")
    print(f"[TASK6D] Total displacement: {plan['total_root_displacement']:.4f}m (Y {records[0]['root_y']:.4f} -> {records[-1]['root_y']:.4f})")
    print(f"[TASK6D] Peak speed: {plan['peak_speed_mps']:.4f}m/s, Final speed: {fin.velocity[1]:.4f}m/s")
    print(f"[TASK6D] Final state: mode={fin.mode.value} v={fin.velocity} pos={fin.position} contacts={list(fin.contacts.keys())}")

    brake_records = [r for r in records if r["frame"] >= 115]
    l_dr = max(r["state_l"]["ankle_bone_drift"] for r in brake_records if r["phase_l"] == "stance")
    r_dr = max(r["state_r"]["ankle_bone_drift"] for r in brake_records if r["phase_r"] == "stance")
    print(f"[TASK6D] Brake stance drift L={l_dr:.6f}m R={r_dr:.6f}m")

    start_x, start_y, _ = config.character_path_points[0]
    configure_render(config)
    scene = bpy.context.scene
    cam = bpy.data.objects.get("PipelineCamera")
    tgt = bpy.data.objects.get("CameraLookAtTarget")
    for obj in (cam, tgt):
        if obj and obj.animation_data:
            obj.animation_data_clear()

    previews = []
    for pf in config.sprint_brake_preview_frames:
        scene.frame_set(pf)
        ry = records[pf - 1]["root_y"]
        if cam and tgt:
            cam.location = Vector((start_x - 3.6, ry + 3.9, 1.5))
            tgt.location = Vector((start_x, ry + 0.3, 0.88))
        bpy.context.view_layer.update()
        path = config.get_sprint_brake_preview_path(pf)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        previews.append(path)
        print(f"[TASK6D] Preview frame {pf:04d}: {path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()
    blend_path = config.sprint_brake_blend_path

    # Protection: Refuse to overwrite any prior prototype blend files
    prior_blends = (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
        config.walk_cycle_blend_path,
        config.forward_walk_blend_path,
        config.start_stop_blend_path,
        config.motion_framework_blend_path,
        config.run_blend_path,
        config.sprint_blend_path,
    )
    for prot in prior_blends:
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(prot)):
            raise RuntimeError(f"Refusing to overwrite prior prototype {prot}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK6D] Blend written: {blend_path}")
    print("[TASK6D] COMPLETED SUCCESSFULLY")
    return {"blend_path": blend_path, "preview_paths": previews}


if __name__ == "__main__":
    try:
        run_sprint_brake_prototype()
    except Exception as exc:
        print(f"[TASK6D_FATAL_ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
