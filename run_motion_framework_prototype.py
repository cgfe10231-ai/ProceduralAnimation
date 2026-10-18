"""Task 6A runner: execute the Task 5C start -> accelerate -> steady -> decelerate -> stop
locomotion flow through the extensible `MotionPlanner` + `StartStopWalkAction` framework,
verify state transitions and metrics, and save isolated `output/character_motion_framework_5c.blend`
and `output/preview_motion_framework_5c.png`.
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
from src.motion.framework import run_task5c_via_motion_framework
from src.render import configure_render


def run_motion_framework_prototype(config: PipelineConfig = None) -> dict:
    if config is None:
        config = PipelineConfig()

    print("=" * 74)
    print("PROCEDURAL ANIMATION PIPELINE: TASK 6A MOTION SYSTEM FOUNDATION (5C ADAPTER)")
    print("=" * 74)

    arm_obj = _ensure_scene_with_ik_rig(config)
    plan_data = run_task5c_via_motion_framework(config, arm_obj)
    records = plan_data["frame_records"]
    states = plan_data["states"]
    init_state = plan_data["initial_state"]
    final_state = plan_data["final_state"]

    stance_l_ankle_drifts = [
        r["state_l"]["ankle_bone_drift"] for r in records if r["phase_l"] == "stance"
    ]
    stance_r_ankle_drifts = [
        r["state_r"]["ankle_bone_drift"] for r in records if r["phase_r"] == "stance"
    ]
    max_l_ankle_drift = max(stance_l_ankle_drifts)
    max_r_ankle_drift = max(stance_r_ankle_drifts)

    modes_seen = []
    for st in states:
        if not modes_seen or modes_seen[-1] != st.mode.value:
            modes_seen.append(st.mode.value)

    print(
        f"[TASK6A] MotionPlanner Summary ({plan_data['total_frames']} frames / {plan_data['total_frames'] / config.fps:.2f}s):\n"
        f"  Actions Executed       : {plan_data['action_names']}\n"
        f"  Initial MotionState    : frame={init_state.frame}, pos={init_state.position}, mode={init_state.mode.value}, v={init_state.velocity}\n"
        f"  Final MotionState      : frame={final_state.frame}, pos={final_state.position}, mode={final_state.mode.value}, v={final_state.velocity}\n"
        f"  Mode Transition Chain  : {' -> '.join(modes_seen)}\n"
        f"  Total Root Displacement: {plan_data['total_root_displacement']:.4f} m (+Y)\n"
        f"  Peak Forward Speed     : {plan_data['peak_speed_mps']:.4f} m/s\n"
        f"  Left Stance Max Drift  : {max_l_ankle_drift:.6f} m\n"
        f"  Right Stance Max Drift : {max_r_ankle_drift:.6f} m\n"
        f"  IK Unreachable Events  : {plan_data['unreachable_count']}"
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
        cam_obj.location = Vector((start_x - 3.30, start_y + 4.75, 1.50))
        target_obj.location = Vector((start_x, start_y + 0.65, 0.88))
        bpy.context.view_layer.update()

    # Render representative steady-walk mid-frame preview (frame 103)
    scene.frame_set(103)
    bpy.context.view_layer.update()
    preview_path = config.motion_framework_preview_path
    scene.render.filepath = preview_path
    bpy.ops.render.render(write_still=True)
    print(f"[TASK6A] Preview still written (frame 0103): {preview_path}")

    scene.frame_set(1)
    bpy.context.view_layer.update()

    blend_path = config.motion_framework_blend_path
    for protected_path in (
        config.blend_file_path,
        config.character_blend_path,
        config.character_rig_blend_path,
        config.character_ik_blend_path,
        config.character_foot_contact_blend_path,
        config.walk_cycle_blend_path,
        config.forward_walk_blend_path,
        config.start_stop_blend_path,
    ):
        if os.path.normcase(os.path.abspath(blend_path)) == os.path.normcase(os.path.abspath(protected_path)):
            raise RuntimeError(f"Refusing to overwrite protected blend file: {protected_path}")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[TASK6A] Motion framework blend written: {blend_path}")
    print("[TASK6A] COMPLETED SUCCESSFULLY")
    print("=" * 74)

    return {
        "total_root_displacement": round(plan_data["total_root_displacement"], 4),
        "peak_speed_mps": round(plan_data["peak_speed_mps"], 4),
        "max_l_ankle_drift": round(max_l_ankle_drift, 6),
        "max_r_ankle_drift": round(max_r_ankle_drift, 6),
        "unreachable_count": plan_data["unreachable_count"],
        "mode_transitions": modes_seen,
        "blend_path": blend_path,
        "preview_path": preview_path,
    }


if __name__ == "__main__":
    try:
        run_motion_framework_prototype()
    except Exception as exc:
        print(f"[TASK6A_FATAL_ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
