"""DynamicsPlayground Continuous Terrain Locomotion Pipeline (Task 7A-2).

Coordinates the generation and keyframing of the complete continuous 926-frame
terrain traversal animation for the 19-bone character on DynamicsPlayground:
- Course C: Stairs Traversal (Frames 1..226, 9.42s @ 24 FPS)
  Flat ground approach (Y=4.95 -> 5.80) -> 5 stair steps ascent (Y=5.80 -> 7.35, Z=0.0 -> 0.75) ->
  Top landing platform traversal (Y=7.35 -> 7.95, Z=0.75) -> Clean double-stance stop.
- Course B: Sloped Ramp Traversal (Frames 227..926, 29.17s @ 24 FPS)
  Flat ground approach (Y=10.20 -> 11.00) -> 15° Uphill ramp ascent (Y=11.00 -> 16.00, Z=0.0 -> 1.34) ->
  Elevated connector bridge traversal (Y=16.00 -> 18.00, Z=1.34) -> 20° Downhill ramp descent
  (Y=18.00 -> 21.68, Z=1.34 -> 0.0) -> Flat landing traversal (Y=21.68 -> 22.40, Z=0.0) ->
  Clean double-stance stop.

Produces:
- `output/dynamics_playground_task7a2.blend` (playable animation in Blender 5.1.1)
- `docs/evidence/task7a2/task7a2_contact_state_records.json`
- `docs/evidence/task7a2/task7a2_execution_summary.json`
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Vector

from src.config import PipelineConfig
from src.motion.framework import (
    BlenderPoseApplicator,
    ContactConstraintAdapter,
    MotionPlanner,
    MotionRuntimeContext,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.terrain_walk import (
    TerrainTraversalSpec,
    TerrainWalkAction,
    build_terrain_step_schedule,
)
from src.scene.environment_query import create_standard_dynamics_playground_query
from src.scene.playground_character_assembly import assemble_character_in_playground


def setup_task7a2_cameras_and_markers(
    scene: bpy.types.Scene,
    char_col: bpy.types.Collection,
) -> Dict[str, bpy.types.Object]:
    """Create dedicated cameras and timeline markers for Course C (Stairs) and Course B (Ramp)."""
    cam_specs = {
        "Task7A2_StairsCam": {
            "location": (2.80, 5.20, 1.65),
            "look_at": (0.0, 6.80, 0.70),
            "lens": 35.0,
        },
        "Task7A2_RampCam": {
            "location": (5.20, 15.00, 2.50),
            "look_at": (0.0, 16.50, 1.10),
            "lens": 32.0,
        },
        "Task7A2_OverviewCam": {
            "location": (7.50, 11.00, 4.20),
            "look_at": (0.0, 14.00, 0.80),
            "lens": 28.0,
        },
    }

    cameras: Dict[str, bpy.types.Object] = {}
    for cam_name, spec in cam_specs.items():
        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj is None:
            cam_data = bpy.data.cameras.new(cam_name)
            cam_obj = bpy.data.objects.new(cam_name, cam_data)
            char_col.objects.link(cam_obj)
        else:
            cam_data = cam_obj.data

        cam_data.lens = spec["lens"]
        cam_data.clip_start = 0.05
        cam_data.clip_end = 200.0
        loc = Vector(spec["location"])
        target = Vector(spec["look_at"])
        direction = (target - loc).normalized()
        rot_quat = direction.to_track_quat("-Z", "Y")
        cam_obj.location = loc
        cam_obj.rotation_mode = "XYZ"
        cam_obj.rotation_euler = rot_quat.to_euler("XYZ")
        cameras[cam_name] = cam_obj

    # Configure timeline markers
    scene.timeline_markers.clear()
    markers = [
        ("Stairs_Start", 1, "Task7A2_StairsCam"),
        ("Stairs_Climb", 49, "Task7A2_StairsCam"),
        ("Stairs_TopPlatform", 157, "Task7A2_StairsCam"),
        ("Stairs_Stop", 211, "Task7A2_StairsCam"),
        ("Ramp_Start", 227, "Task7A2_RampCam"),
        ("Ramp_UphillAscent", 275, "Task7A2_RampCam"),
        ("Ramp_BridgePlatform", 531, "Task7A2_RampCam"),
        ("Ramp_DownhillDescent", 627, "Task7A2_RampCam"),
        ("Ramp_FlatLanding", 835, "Task7A2_RampCam"),
        ("Ramp_Stop", 911, "Task7A2_RampCam"),
    ]
    for name, frame, cam_key in markers:
        m = scene.timeline_markers.new(name, frame=frame)
        if cam_key in cameras:
            m.camera = cameras[cam_key]

    # Default active camera initially set to Stairs camera
    scene.camera = cameras["Task7A2_StairsCam"]
    bpy.context.view_layer.update()
    return cameras


def build_task7a2_specs() -> Tuple[TerrainTraversalSpec, TerrainTraversalSpec]:
    """Construct mathematical trajectory specifications for Course C (Stairs) and Course B (Ramp)."""
    # Course C: 5 stair steps (rise 0.15m, tread 0.30m)
    waypoint_stairs = [
        5.20,  # step 0 R (flat ground approach, lead=0.30)
        5.50,  # step 1 L (flat ground approach, lead=0.30)
        5.80,  # step 2 R (flat ground immediately before step 1, lead=0.30)
        6.10,  # step 3 L (Stair Step 1, z=0.15, lead=0.30)
        6.40,  # step 4 R (Stair Step 2, z=0.30, lead=0.30)
        6.70,  # step 5 L (Stair Step 3, z=0.45, lead=0.30)
        7.00,  # step 6 R (Stair Step 4, z=0.60, lead=0.30)
        7.30,  # step 7 L (Stair Step 5, z=0.75, lead=0.30)
        7.65,  # step 8 R (Stair Top Platform, z=0.75, lead=0.35)
        7.95,  # step 9 L (Stair Top Platform, z=0.75, lead=0.30)
        7.95,  # step 10 R closing step (lands side-by-side on top platform)
    ]
    spec_stairs = TerrainTraversalSpec(
        course_id="stairs",
        start_pos=(0.0, 4.90, 0.0),
        waypoint_y=waypoint_stairs,
        stand_start_frames=12,
        step_frames=18,
        stand_stop_frames=16,
        base_clearance_stairs=0.16,
        pelvis_drop_stairs=0.12,
    )

    # Course B: 15° uphill ramp, elevated bridge, 20° downhill ramp, flat landing
    waypoint_ramps = [
        10.50, # step 0 R (flat ground approach, lead=0.30)
        10.80, # step 1 L (flat ground approach, lead=0.30, toe at 10.95 < 11.00)
        11.10, # step 2 R (15° uphill ramp ascent, lead=0.30, heel at 11.03 > 11.00)
        11.40, # step 3 L (uphill)
        11.70, # step 4 R (uphill)
        12.00, # step 5 L (uphill)
        12.30, # step 6 R (uphill)
        12.60, # step 7 L (uphill)
        12.90, # step 8 R (uphill)
        13.20, # step 9 L (uphill)
        13.50, # step 10 R (uphill)
        13.80, # step 11 L (uphill)
        14.10, # step 12 R (uphill)
        14.40, # step 13 L (uphill)
        14.70, # step 14 R (uphill)
        15.00, # step 15 L (uphill)
        15.28, # step 16 R (uphill)
        15.56, # step 17 L (uphill near crest)
        15.84, # step 18 R (uphill crest approach, toe at 15.99 < 16.00)
        16.08, # step 19 L (elevated bridge platform, heel at 16.01 > 16.00, z=1.34)
        16.35, # step 20 R (bridge platform, z=1.34)
        16.65, # step 21 L (bridge platform, z=1.34)
        16.95, # step 22 R (bridge platform, z=1.34)
        17.25, # step 23 L (bridge platform, z=1.34)
        17.55, # step 24 R (bridge platform, z=1.34)
        17.80, # step 25 L (bridge platform near descent, toe at 17.95 < 18.00)
        18.15, # step 26 R (-20° downhill ramp descent, heel at 18.08 > 18.00, z≈1.28)
        18.45, # step 27 L (downhill)
        18.75, # step 28 R (downhill)
        19.05, # step 29 L (downhill)
        19.35, # step 30 R (downhill)
        19.65, # step 31 L (downhill)
        19.95, # step 32 R (downhill)
        20.25, # step 33 L (downhill)
        20.55, # step 34 R (downhill)
        20.85, # step 35 L (downhill)
        21.15, # step 36 R (downhill)
        21.48, # step 37 L (downhill near base, toe at 21.63 < 21.681)
        21.78, # step 38 R (flat landing, heel at 21.71 > 21.681, z=0.0)
        22.10, # step 39 L (flat landing, z=0.0)
        22.40, # step 40 R (flat landing, z=0.0)
        22.40, # step 41 L closing step (lands side-by-side on flat ground)
    ]
    spec_ramps = TerrainTraversalSpec(
        course_id="ramps",
        start_pos=(0.0, 10.20, 0.0),
        waypoint_y=waypoint_ramps,
        stand_start_frames=12,
        step_frames=16,
        stand_stop_frames=16,
        base_clearance_ramp=0.12,
        pelvis_drop_slope=0.08,
        pelvis_drop_uphill=0.063,
        pelvis_drop_downhill=0.095,
        pelvis_drop_flat=0.03,
        torso_lean_uphill_deg=6.0,
        torso_lean_downhill_deg=-2.5,
    )

    return spec_stairs, spec_ramps


def generate_dynamics_playground_task7a2_blend(
    output_blend_path: str = "output/dynamics_playground_task7a2.blend",
    evidence_dir: str = "docs/evidence/task7a2",
    config: Optional[PipelineConfig] = None,
) -> Dict[str, Any]:
    """Execute complete Task 7A-2 terrain traversal pipeline and save derived .blend artifact."""
    cfg = config or PipelineConfig()
    os.makedirs(os.path.dirname(os.path.abspath(output_blend_path)), exist_ok=True)
    os.makedirs(os.path.abspath(evidence_dir), exist_ok=True)

    # 1. Load baseline DynamicsPlayground (read-only base)
    base_blend = os.path.abspath("output/dynamics_playground.blend")
    if not os.path.exists(base_blend):
        raise FileNotFoundError(f"Baseline playground scene not found: {base_blend}")
    bpy.ops.wm.open_mainfile(filepath=base_blend)

    # 2. Assemble 19-bone character and rig
    assembly = assemble_character_in_playground(cfg)
    arm_obj = assembly["armature"]
    root_obj = assembly["root"]
    char_col = assembly["collection"]
    scene = bpy.context.scene

    # 3. Setup Task 7A-2 cameras and timeline markers
    cameras = setup_task7a2_cameras_and_markers(scene, char_col)

    # 4. Construct terrain environment query
    env = create_standard_dynamics_playground_query()

    # 5. Build action specifications
    spec_stairs, spec_ramps = build_task7a2_specs()
    action_stairs = TerrainWalkAction(spec_stairs)
    action_ramps = TerrainWalkAction(spec_ramps)

    # 6. Initialize Bridge Executor and Runtime Context
    bridge = KinematicBridgeExecutor(
        armature_obj=arm_obj,
        root_obj=root_obj,
        environment=env,
        default_fps=cfg.fps,
    )
    context = MotionRuntimeContext(
        config=cfg,
        armature_obj=arm_obj,
        root_obj=root_obj,
        scene=scene,
        environment=env,
        contact_adapter=ContactConstraintAdapter(arm_obj, env),
        pose_applicator=BlenderPoseApplicator(arm_obj, root_obj, cfg),
        bridge_executor=bridge,
    )

    # 7. Execute Course C: Stairs Traversal (Frames 1..226)
    init_state_stairs = create_initial_motion_state(
        cfg,
        start_frame=1,
        position=spec_stairs.start_pos,
    )
    res_stairs = action_stairs.execute(init_state_stairs, context)

    # 8. Execute Course B: Ramp Traversal (Frames 227..926)
    bridge.reset()
    init_state_ramps = create_initial_motion_state(
        cfg,
        start_frame=res_stairs.final_state.frame + 1,
        position=spec_ramps.start_pos,
    )
    res_ramps = action_ramps.execute(init_state_ramps, context)

    all_states = res_stairs.states + res_ramps.states
    all_frame_records = res_stairs.frame_records + res_ramps.frame_records
    total_frames = len(all_states)

    # Set scene playback range
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.frame_set(1)

    # 9. Verify locked foot contact drift
    max_drift = 0.0
    for s in all_states:
        for limb, c in s.contacts.items():
            if c.is_locked:
                max_drift = max(max_drift, c.drift_m)

    # 10. Serialize and embed contact state records into Blender scene ID properties
    contact_records_serialized = []
    for s in all_states:
        contact_records_serialized.append({
            "frame": s.frame,
            "time_sec": round(s.time_sec, 4),
            "root_position": [round(v, 4) for v in s.position],
            "mode": s.mode.value,
            "contacts": {
                limb: {
                    "is_locked": c.is_locked,
                    "phase": c.phase,
                    "contact_xyz": [round(v, 4) for v in c.contact_world_xyz],
                    "drift_m": round(c.drift_m, 6),
                    "is_reachable": c.is_reachable,
                }
                for limb, c in s.contacts.items()
            },
        })

    scene["task7a2_contact_state_records"] = json.dumps(contact_records_serialized)
    summary_data = {
        "task": "Task 7A-2",
        "total_frames": total_frames,
        "stairs_frames": len(res_stairs.states),
        "ramps_frames": len(res_ramps.states),
        "max_locked_ankle_drift_m": max_drift,
        "unreachable_count": res_stairs.unreachable_count + res_ramps.unreachable_count,
        "courses": {
            "stairs": {
                "start_frame": res_stairs.initial_state.frame,
                "end_frame": res_stairs.final_state.frame,
                "steps": len(res_stairs.step_schedule),
                "total_disp_y": res_stairs.metrics["total_disp_y"],
                "total_disp_z": res_stairs.metrics["total_disp_z"],
            },
            "ramps": {
                "start_frame": res_ramps.initial_state.frame,
                "end_frame": res_ramps.final_state.frame,
                "steps": len(res_ramps.step_schedule),
                "total_disp_y": res_ramps.metrics["total_disp_y"],
                "total_disp_z": res_ramps.metrics["total_disp_z"],
            },
        },
    }
    scene["task7a2_execution_summary"] = json.dumps(summary_data)

    # 11. Save derived blend artifact
    abs_blend_out = os.path.abspath(output_blend_path)
    bpy.ops.wm.save_as_mainfile(filepath=abs_blend_out, check_existing=False)

    # 12. Save companion JSON files
    json_records_path = os.path.join(evidence_dir, "task7a2_contact_state_records.json")
    with open(json_records_path, "w", encoding="utf-8") as f:
        json.dump(contact_records_serialized, f, indent=2)

    json_summary_path = os.path.join(evidence_dir, "task7a2_execution_summary.json")
    with open(json_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    return {
        "output_blend_path": abs_blend_out,
        "total_frames": total_frames,
        "max_locked_ankle_drift_m": max_drift,
        "summary": summary_data,
        "stairs_result": res_stairs,
        "ramps_result": res_ramps,
    }
