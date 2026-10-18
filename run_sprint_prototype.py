"""Task 6C runner: explosive start + sprint via MotionPlanner + SprintStartAction.
Saves isolated output/character_sprint_start_prototype.blend and key previews."""

import os
import sys

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import PipelineConfig
from src.motion.forward_walk_prototype import _ensure_scene_with_ik_rig
from src.motion.sprint_start import run_task6c_via_motion_framework
from src.render import configure_render


def run_sprint_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()
    print("=" * 74)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 6C EXPLOSIVE START & SPRINT")
    print("=" * 74)

    arm_obj = _ensure_scene_with_ik_rig(config)
    plan = run_task6c_via_motion_framework(config, arm_obj)
    res = plan["action_results"][0]
    records = plan["frame_records"]
    fin = plan["final_state"]
    print(f"[TASK6C] frames={plan['total_frames']} disp={plan['total_root_displacement']:.4f}m "
          f"peak_v={plan['peak_speed_mps']:.4f}m/s unreachable={plan['unreachable_count']}")
    print(f"[TASK6C] Final state: mode={fin.mode.value} v={fin.velocity} frame={fin.frame} gait_phase={fin.gait_phase:.3f}")
    for st in res.step_schedule:
        print(f"[TASK6C] step {st['k']:2d} tau={st['tau_start']:3d} D={st['duration_frames']:2d} "
              f"S={st['stance_frames']} F={st['flight_frames']} L={st['step_length']:.3f}m "
              f"cad={st['cadence_steps_per_s']:.2f}/s v0={st['speed_at_start']:.3f}")
    l_dr = max(r["state_l"]["ankle_bone_drift"] for r in records if r["phase_l"] == "stance")
    r_dr = max(r["state_r"]["ankle_bone_drift"] for r in records if r["phase_r"] == "stance")
    print(f"[TASK6C] stance drift L={l_dr:.6f} R={r_dr:.6f}")

    start_x, start_y, _ = config.character_path_points[0]
    configure_render(config)
    scene = bpy.context.scene
    cam = bpy.data.objects.get("PipelineCamera")
    tgt = bpy.data.objects.get("CameraLookAtTarget")
    for obj in (cam, tgt):
        if obj and obj.animation_data:
            obj.animation_data_clear()
    previews = []
    for pf in config.sprint_preview_frames:
        scene.frame_set(pf)
        ry = records[pf - 1]["root_y"]
        if cam and tgt:
            cam.location = Vector((start_x - 3.6, ry + 3.9, 1.5))
            tgt.location = Vector((start_x, ry + 0.3, 0.88))
        bpy.context.view_layer.update()
        path = config.get_sprint_preview_path(pf)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        previews.append(path)
        print(f"[TASK6C] Preview {pf}: {path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()
    blend_path = config.sprint_blend_path
    for prot in (config.blend_file_path, config.character_blend_path, config.character_rig_blend_path,
                 config.character_ik_blend_path, config.character_foot_contact_blend_path,
                 config.walk_cycle_blend_path, config.forward_walk_blend_path, config.start_stop_blend_path,
                 config.motion_framework_blend_path, config.run_blend_path):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(prot)):
            raise RuntimeError(f"Refusing to overwrite {prot}")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK6C] Blend written: {blend_path}")
    print("[TASK6C] COMPLETED SUCCESSFULLY")
    return {"blend_path": blend_path, "preview_paths": previews}


if __name__ == "__main__":
    try:
        run_sprint_prototype()
    except Exception as exc:
        print(f"[TASK6C_FATAL_ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
