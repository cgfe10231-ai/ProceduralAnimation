"""Procedural Terrain Traversal Scene Assembler & Orchestrator (Task 7A-2).

Assembles the 19-bone character inside DynamicsPlayground, executes continuous
terrain traversal through the authoritative `MotionPlanner`, and produces:
1. Active animation scene ('Scene'):
   - Continuous 19-bone lower-limb traversal over Course B (flat -> 15° ramp -> bridge -> 20° ramp -> flat landing).
   - Dedicated inspection cameras: `Task7A2_RampCam`, `Task7A2_OverviewCam`.
   - Timeline markers for all key traversal stages.
2. Dedicated internal Blender control chain diagnostic scene ('Task7A2_ControlChain_Debug'):
   - Linked 19-bone character, surfaces, and dedicated camera `Task7A2_DebugCam`.
   - Dynamic 3D keyframed visual indicators (Planned foot targets, CoM tracker, Lock indicators, Normal arrow).
   - Dynamic 6-phase HUD diagnostic text boards driven by embedded timeline handler.
3. Persistent embedded telemetry:
   - `scene["task7a2_contact_state_records"]`
   - `scene["task7a2_execution_summary"]`
   - `scene["task7a2_control_chain_diagnostics"]`

Architectural Guardrails:
- Single authoritative writer: MotionPlanner -> MotionAction -> KinematicBridge -> WBC -> Rig.
- Zero string-based naming logic; 100% geometric surface normal and height queries.
- Zero frame exemptions; absolute continuity from start to finish.
"""

from __future__ import annotations

import json
import math
import os
import sys

if "." not in sys.path:
    sys.path.insert(0, ".")
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    ActionExecutionResult,
    ContactConstraintAdapter,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    create_initial_motion_state,
)
from src.motion.terrain_walk import (
    TerrainRouteInput,
    TerrainTraversalSpec,
    TerrainWalkAction,
    pitch_from_surface_normal,
    plan_terrain_footsteps,
)
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET
from src.scene.blender_mesh_query_adapter import (
    BlenderMeshEnvironmentAdapter,
    create_mesh_backed_dynamics_query,
)
from src.scene.environment_query import create_standard_dynamics_playground_query
from src.scene.playground_character_assembly import assemble_character_in_playground
from src.scene.playground_terrain_validation import (
    DEFAULT_MAX_ROOT_DISP_M_AT_24FPS,
    DEFAULT_REFERENCE_FPS,
    compute_max_root_disp_per_frame,
)


def setup_task7a2_cameras_and_markers(
    scene: bpy.types.Scene,
    char_col: bpy.types.Collection,
) -> Dict[str, bpy.types.Object]:
    """Create dedicated inspection cameras and timeline markers for Course B (Ramp)."""
    cam_specs = {
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
        ("Ramp_Start", 1, "Task7A2_RampCam"),
        ("Ramp_UphillAscent", 49, "Task7A2_RampCam"),
        ("Ramp_BridgePlatform", 305, "Task7A2_RampCam"),
        ("Ramp_DownhillDescent", 401, "Task7A2_RampCam"),
        ("Ramp_FlatLanding", 609, "Task7A2_RampCam"),
        ("Ramp_Stop", 685, "Task7A2_RampCam"),
    ]
    for name, frame, cam_key in markers:
        m = scene.timeline_markers.new(name, frame=frame)
        if cam_key in cameras:
            m.camera = cameras[cam_key]

    scene.camera = cameras["Task7A2_RampCam"]
    bpy.context.view_layer.update()
    return cameras


def setup_control_chain_debug_scene(
    scene_main: bpy.types.Scene,
    char_col: bpy.types.Collection,
    frame_records: List[dict],
) -> bpy.types.Scene:
    """Construct dedicated 'Task7A2_ControlChain_Debug' scene in the same .blend."""
    debug_scene_name = "Task7A2_ControlChain_Debug"
    debug_scene = bpy.data.scenes.get(debug_scene_name)
    if debug_scene is None:
        debug_scene = bpy.data.scenes.new(debug_scene_name)

    debug_scene.frame_start = scene_main.frame_start
    debug_scene.frame_end = scene_main.frame_end
    debug_scene.render.fps = scene_main.render.fps

    # Link surfaces collection and character collection into debug scene
    surfaces_col = bpy.data.collections.get("Playground_Surfaces")
    if surfaces_col and surfaces_col.name not in debug_scene.collection.children:
        debug_scene.collection.children.link(surfaces_col)
    if char_col and char_col.name not in debug_scene.collection.children:
        debug_scene.collection.children.link(char_col)

    # Create dedicated Debug Visualization collection
    debug_col = bpy.data.collections.get("Task7A2_Debug_Visualization")
    if debug_col is None:
        debug_col = bpy.data.collections.new("Task7A2_Debug_Visualization")
    if debug_col.name not in debug_scene.collection.children:
        debug_scene.collection.children.link(debug_col)

    # 1. Dedicated Debug Camera
    cam_name = "Task7A2_DebugCam"
    debug_cam_obj = bpy.data.objects.get(cam_name)
    if debug_cam_obj is None:
        cam_data = bpy.data.cameras.new(cam_name)
        debug_cam_obj = bpy.data.objects.new(cam_name, cam_data)
        debug_col.objects.link(debug_cam_obj)
    debug_cam_obj.data.lens = 28.0
    debug_cam_obj.location = Vector((4.50, 15.00, 2.80))
    direction = (Vector((0.0, 16.50, 1.00)) - debug_cam_obj.location).normalized()
    debug_cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler("XYZ")
    debug_scene.camera = debug_cam_obj

    # 2. 3D Keyframed Visual Indicators
    def _get_or_create_empty(name: str, display_type: str = "SPHERE", size: float = 0.10) -> bpy.types.Object:
        obj = bpy.data.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name, None)
            obj.empty_display_type = display_type
            obj.empty_display_size = size
            debug_col.objects.link(obj)
        return obj

    empty_tgt_l = _get_or_create_empty("Debug_TargetFoot_L", "SPHERE", 0.08)
    empty_tgt_r = _get_or_create_empty("Debug_TargetFoot_R", "SPHERE", 0.08)
    empty_com = _get_or_create_empty("Debug_CoM_Tracker", "CIRCLE", 0.12)
    empty_lock_l = _get_or_create_empty("Debug_LockIndicator_L", "SINGLE_ARROW", 0.15)
    empty_lock_r = _get_or_create_empty("Debug_LockIndicator_R", "SINGLE_ARROW", 0.15)

    # Keyframe indicators across all frames
    for rec in frame_records:
        f = rec["frame"]
        mp = rec.get("motion_planning", {})
        act = rec.get("actual_armature", {})
        val = rec.get("validation", {})
        wbc = rec.get("whole_body_controller", {})

        # Planned foot targets
        fl_xyz = mp.get("planned_foot_L", [0, 0, 0])
        fr_xyz = mp.get("planned_foot_R", [0, 0, 0])
        empty_tgt_l.location = Vector(fl_xyz)
        empty_tgt_l.keyframe_insert("location", frame=f)
        empty_tgt_r.location = Vector(fr_xyz)
        empty_tgt_r.keyframe_insert("location", frame=f)

        # CoM Tracker
        com_xyz = act.get("com_world", [0, 0, 0])
        empty_com.location = Vector(com_xyz)
        empty_com.keyframe_insert("location", frame=f)

        # Lock Indicators: point upward when locked, shrink when unlocked
        l_locked = wbc.get("foot_L_locked", False)
        r_locked = wbc.get("foot_R_locked", False)
        empty_lock_l.location = Vector(fl_xyz)
        empty_lock_l.scale = Vector((1.0, 1.0, 1.0)) if l_locked else Vector((0.001, 0.001, 0.001))
        empty_lock_l.keyframe_insert("location", frame=f)
        empty_lock_l.keyframe_insert("scale", frame=f)

        empty_lock_r.location = Vector(fr_xyz)
        empty_lock_r.scale = Vector((1.0, 1.0, 1.0)) if r_locked else Vector((0.001, 0.001, 0.001))
        empty_lock_r.keyframe_insert("location", frame=f)
        empty_lock_r.keyframe_insert("scale", frame=f)

    # 3. 6 Structured HUD Diagnostic Text Boards
    hud_stages = [
        ("HUD_Stage_01_Environment", (2.8, 13.8, 3.2), "[ENVIRONMENT] Surface: ramp_up | Height: 0.0m | Pitch: 15.0 deg"),
        ("HUD_Stage_02_MotionPlanning", (2.8, 14.1, 3.0), "[MOTION PLANNING] Action: TerrainWalk | Step: steady | Phase: L=stance R=swing"),
        ("HUD_Stage_03_KinematicBridge", (2.8, 14.4, 2.8), "[KINEMATIC BRIDGE] Root Target: (0, 12, 0.3) | Pelvis Offset: (0, 0, -0.063)"),
        ("HUD_Stage_04_WholeBodyController", (2.8, 14.7, 2.6), "[WHOLE BODY CONTROLLER] Reachable: True | Foot Lock: L=True R=False | Unmet: 0"),
        ("HUD_Stage_05_ActualArmature", (2.8, 15.0, 2.4), "[ACTUAL ARMATURE] CoM: (0, 12, 1.1) | Mass: 70.0kg | ROM: 0 violations"),
        ("HUD_Stage_06_Validation", (2.8, 15.3, 2.2), "[VALIDATION METRICS] Stance Drift: 0.000000m | Stretch: 0.000001m | STATUS: PASS"),
    ]

    for txt_name, loc, initial_body in hud_stages:
        txt_obj = bpy.data.objects.get(txt_name)
        if txt_obj is None:
            curve_data = bpy.data.curves.new(txt_name, "FONT")
            txt_obj = bpy.data.objects.new(txt_name, curve_data)
            debug_col.objects.link(txt_obj)
        txt_obj.data.body = initial_body
        txt_obj.data.size = 0.08
        txt_obj.location = Vector(loc)
        # Face the debug camera
        dir_to_cam = (debug_cam_obj.location - txt_obj.location).normalized()
        txt_obj.rotation_euler = dir_to_cam.to_track_quat("Z", "Y").to_euler("XYZ")

    # 4. Embed Interactive Frame-Change Driver Script
    driver_script_name = "task7a2_debug_hud_driver.py"
    driver_text = bpy.data.texts.get(driver_script_name)
    if driver_text is None:
        driver_text = bpy.data.texts.new(driver_script_name)
    driver_text.from_string('''
import bpy
import json

def update_debug_hud(scene):
    if scene.name != "Task7A2_ControlChain_Debug":
        return
    records_str = scene.get("task7a2_control_chain_diagnostics", "")
    if not records_str:
        return
    try:
        records = json.loads(records_str)
    except Exception:
        return
    frame = scene.frame_current
    rec = next((r for r in records if r["frame"] == frame), None)
    if rec is None:
        return

    # Update HUD text objects
    env_txt = bpy.data.objects.get("HUD_Stage_01_Environment")
    if env_txt:
        e = rec.get("environment", {})
        env_txt.data.body = f"[1. ENVIRONMENT]\\nQuery: {e.get('query_pos')}\\nTerrain Z: {e.get('terrain_height')}m | Pitch: {e.get('slope_pitch_deg')} deg"

    mp_txt = bpy.data.objects.get("HUD_Stage_02_MotionPlanning")
    if mp_txt:
        m = rec.get("motion_planning", {})
        mp_txt.data.body = f"[2. MOTION PLANNING]\\nAction: {m.get('action_name')} | Step: {m.get('active_step_k')}\\nPhase: L={m.get('phase_L')} R={m.get('phase_R')}"

    kb_txt = bpy.data.objects.get("HUD_Stage_03_KinematicBridge")
    if kb_txt:
        k = rec.get("kinematic_bridge", {})
        kb_txt.data.body = f"[3. KINEMATIC BRIDGE]\\nRoot: {k.get('root_target')}\\nPelvis dz: {k.get('pelvis_offset')}"

    wbc_txt = bpy.data.objects.get("HUD_Stage_04_WholeBodyController")
    if wbc_txt:
        w = rec.get("whole_body_controller", {})
        wbc_txt.data.body = f"[4. WHOLE BODY CONTROLLER]\\nReachable: {w.get('is_all_reachable')} | Lock L/R: {w.get('foot_L_locked')}/{w.get('foot_R_locked')}"

    arm_txt = bpy.data.objects.get("HUD_Stage_05_ActualArmature")
    if arm_txt:
        a = rec.get("actual_armature", {})
        arm_txt.data.body = f"[5. ACTUAL ARMATURE]\\nCoM: {a.get('com_world')} | Mass: {a.get('mass_kg')} kg"

    val_txt = bpy.data.objects.get("HUD_Stage_06_Validation")
    if val_txt:
        v = rec.get("validation", {})
        val_txt.data.body = f"[6. VALIDATION METRICS]\\nDrift L: {v.get('drift_L_m'):.6f}m | Reach: L={v.get('reach_L')} R={v.get('reach_R')}\\nSTATUS: {'PASS' if v.get('pass') else 'FAIL'}"

if update_debug_hud not in bpy.app.handlers.frame_change_post:
    bpy.app.handlers.frame_change_post.append(update_debug_hud)
''')
    driver_text.use_module = True

    return debug_scene


def verify_scene_execution_gate(
    planner_result: Dict[str, Any],
    all_states: List[MotionState],
    fps: float = DEFAULT_REFERENCE_FPS,
    max_root_disp_m: Optional[float] = None,
) -> Tuple[bool, List[str]]:
    """Verify motion execution quality before permitting .blend file saving or delivery.

    Reuses the authoritative C0 root continuity threshold from playground_terrain_validation
    (0.12m @ 24 FPS = 2.88 m/s max root velocity, scaled by fps when max_root_disp_m is None).

    Returns:
        (is_passed, failure_reasons)
    """
    reasons: List[str] = []
    disp_limit_m = compute_max_root_disp_per_frame(fps=fps, max_root_disp_m=max_root_disp_m)

    if not planner_result.get("success", False):
        reasons.append("planner_result['success'] is False")

    unreachable = planner_result.get("unreachable_count", 0)
    if unreachable > 0:
        reasons.append(f"unreachable_count is {unreachable} (> 0)")

    fatal_constraints = planner_result.get("fatal_unmet_constraints", [])
    if fatal_constraints:
        reasons.append(f"fatal_unmet_constraints count is {len(fatal_constraints)}")

    action_failure = planner_result.get("action_failure")
    if action_failure:
        reasons.append(f"action_failure reported: {action_failure}")

    if not all_states:
        reasons.append("no motion states produced")
    else:
        # Check frame continuity: consecutive frames without gaps
        for i in range(1, len(all_states)):
            prev_s = all_states[i - 1]
            curr_s = all_states[i]
            if curr_s.frame != prev_s.frame + 1:
                reasons.append(f"frame gap detected between frame {prev_s.frame} and {curr_s.frame}")
                break
            # Check spatial C0 continuity against authoritative per-frame threshold
            dx = curr_s.position[0] - prev_s.position[0]
            dy = curr_s.position[1] - prev_s.position[1]
            dz = curr_s.position[2] - prev_s.position[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist > disp_limit_m + 1e-9:
                reasons.append(
                    f"spatial jump of {dist:.4f}m (> {disp_limit_m:.4f}m @ {fps:.1f}fps) detected at frame {curr_s.frame}"
                )
                break

    is_passed = (len(reasons) == 0)
    return is_passed, reasons


def generate_dynamics_playground_task7a2_corrected_blend(
    output_blend_path: str = "output/dynamics_playground_task7a2_corrected.blend",
    evidence_dir: str = "docs/evidence/task7a2",
    route: Optional[TerrainRouteInput] = None,
) -> Dict[str, Any]:
    """Execute corrected Task 7A-2 pipeline using authoritative MotionPlanner."""
    os.makedirs(evidence_dir, exist_ok=True)
    cfg = PipelineConfig()

    # 1. Open baseline dynamics playground scene
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

    # 3. Setup cameras and timeline markers for active animation scene
    cameras = setup_task7a2_cameras_and_markers(scene, char_col)

    # 4. Construct terrain environment query
    env = create_standard_dynamics_playground_query()

    # 5. Build continuous Course B (Ramp) route input
    if route is None:
        route = TerrainRouteInput(
            start_pos=(0.0, 10.20, 0.0),
            target_pos=(0.0, 22.40, 0.0),
            nominal_stride_m=0.30,
            step_frames=16,
            stand_start_frames=12,
            stand_stop_frames=16,
            base_clearance_m=0.12,
            pelvis_drop_uphill_m=0.088,
            pelvis_drop_downhill_m=0.098,
            pelvis_drop_flat_m=0.035,
            torso_lean_uphill_deg=6.0,
            torso_lean_downhill_deg=-2.5,
        )
    action = TerrainWalkAction(route=route, environment=env, action_name="TerrainWalk_CourseB_Continuous")

    # 6. Execute through AUTHORITATIVE MotionPlanner
    planner = MotionPlanner(
        config=cfg,
        armature_obj=arm_obj,
        environment=env,
    )
    planner.add_action(action)

    init_state = create_initial_motion_state(
        cfg,
        start_frame=1,
        position=route.start_pos,
    )
    planner_result = planner.execute(initial_state=init_state)

    all_states: List[MotionState] = planner_result["states"]
    all_frame_records: List[dict] = planner_result["frame_records"]
    total_frames = len(all_states)

    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.frame_set(1)

    # 7. Setup Dedicated Internal Blender Diagnostic Scene
    debug_scene = setup_control_chain_debug_scene(scene, char_col, all_frame_records)

    # 8. Check locked foot contact drift
    max_drift = 0.0
    for s in all_states:
        for limb, c in s.contacts.items():
            if c.is_locked:
                max_drift = max(max_drift, c.drift_m)

    # 9. Serialize and embed metadata into scene ID properties on BOTH scenes
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

    is_gate_passed, gate_failure_reasons = verify_scene_execution_gate(
        planner_result,
        all_states,
        fps=float(cfg.fps),
    )
    if not is_gate_passed:
        raise RuntimeError(
            f"generate_dynamics_playground_task7a2_corrected_blend failed gate verification: "
            f"{'; '.join(gate_failure_reasons)}. Saving .blend delivery artifact prohibited."
        )

    continuous_without_exemption = is_gate_passed
    contact_json_str = json.dumps(contact_records_serialized)

    summary_data = {
        "task": "Task 7A-2 Corrected",
        "total_frames": total_frames,
        "max_locked_ankle_drift_m": max_drift,
        "unreachable_count": planner_result["unreachable_count"],
        "route": {
            "start_pos": list(route.start_pos),
            "target_pos": list(route.target_pos),
            "nominal_stride_m": route.nominal_stride_m,
            "total_steps": len(planner_result["step_schedule"]),
        },
        "continuous_without_exemption": continuous_without_exemption,
        "gate_passed": is_gate_passed,
        "gate_failure_reasons": gate_failure_reasons,
        "diagnostic_scene": debug_scene.name,
    }
    summary_json_str = json.dumps(summary_data)
    diag_json_str = json.dumps(all_frame_records)

    for target_scene in [scene, debug_scene]:
        target_scene["task7a2_contact_state_records"] = contact_json_str
        target_scene["task7a2_execution_summary"] = summary_json_str
        target_scene["task7a2_control_chain_diagnostics"] = diag_json_str

    # 10. Save derived corrected blend artifact
    abs_blend_out = os.path.abspath(output_blend_path)
    bpy.ops.wm.save_as_mainfile(filepath=abs_blend_out, check_existing=False)

    # 11. Save companion JSON files
    json_records_path = os.path.join(evidence_dir, "task7a2_contact_state_records.json")
    with open(json_records_path, "w", encoding="utf-8") as f:
        json.dump(contact_records_serialized, f, indent=2)

    json_summary_path = os.path.join(evidence_dir, "task7a2_execution_summary.json")
    with open(json_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    json_diag_path = os.path.join(evidence_dir, "task7a2_control_chain_diagnostics.json")
    with open(json_diag_path, "w", encoding="utf-8") as f:
        json.dump(all_frame_records, f, indent=2)

    return {
        "output_blend_path": abs_blend_out,
        "total_frames": total_frames,
        "max_locked_ankle_drift_m": max_drift,
        "summary": summary_data,
        "planner_result": planner_result,
    }


def ensure_ramp_corridor_ground_surfaces(
    scene: bpy.types.Scene,
    col: Optional[bpy.types.Collection] = None,
) -> List[bpy.types.Object]:
    """Ensure ground support mesh slabs exist for Course B (Ramp) approach and exit landing.

    Guarantees 100% authentic mesh geometry for footsteps at Y in [9.5, 11.0] and [21.68, 23.5]
    without modifying the frozen baseline dynamics_playground.blend asset on disk.
    """
    if col is None:
        col = bpy.data.collections.get("Playground_Surfaces")
        if col is None:
            col = scene.collection

    mat_ground = bpy.data.materials.get("Mat_Ground")
    created: List[bpy.types.Object] = []

    # 1. Approach slab: X in [-3, 3], Y in [9.5, 11.0], Z in [-0.30, 0.0]
    app_name = "Surface_Ramp_ApproachGround"
    app_obj = bpy.data.objects.get(app_name)
    if app_obj is None:
        mesh = bpy.data.meshes.new(app_name)
        app_obj = bpy.data.objects.new(app_name, mesh)
        col.objects.link(app_obj)
        verts = [
            (-3.0, 9.5, -0.30), (3.0, 9.5, -0.30), (3.0, 11.0, -0.30), (-3.0, 11.0, -0.30),
            (-3.0, 9.5, 0.0), (3.0, 9.5, 0.0), (3.0, 11.0, 0.0), (-3.0, 11.0, 0.0),
        ]
        faces = [
            (0, 3, 2, 1), # Bottom (-Z)
            (4, 5, 6, 7), # Top (+Z)
            (0, 1, 5, 4), # Front (-Y)
            (2, 3, 7, 6), # Back (+Y)
            (0, 4, 7, 3), # Left (-X)
            (1, 2, 6, 5), # Right (+X)
        ]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        if mat_ground:
            app_obj.data.materials.append(mat_ground)
        created.append(app_obj)

    # 2. Exit slab: X in [-3, 3], Y in [21.68, 23.5], Z in [-0.30, 0.0]
    exit_name = "Surface_Ramp_ExitGround"
    exit_obj = bpy.data.objects.get(exit_name)
    if exit_obj is None:
        mesh = bpy.data.meshes.new(exit_name)
        exit_obj = bpy.data.objects.new(exit_name, mesh)
        col.objects.link(exit_obj)
        verts = [
            (-3.0, 21.68, -0.30), (3.0, 21.68, -0.30), (3.0, 23.5, -0.30), (-3.0, 23.5, -0.30),
            (-3.0, 21.68, 0.0), (3.0, 21.68, 0.0), (3.0, 23.5, 0.0), (-3.0, 23.5, 0.0),
        ]
        faces = [
            (0, 3, 2, 1), # Bottom (-Z)
            (4, 5, 6, 7), # Top (+Z)
            (0, 1, 5, 4), # Front (-Y)
            (2, 3, 7, 6), # Back (+Y)
            (0, 4, 7, 3), # Left (-X)
            (1, 2, 6, 5), # Right (+X)
        ]
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        if mat_ground:
            exit_obj.data.materials.append(mat_ground)
        created.append(exit_obj)

    return created


def apply_ramp_mesh_perturbation(
    delta_z: float = 0.05,
) -> Dict[str, Any]:
    """Perturb ramp mesh geometry in active scene to enable counter-factual verification.

    Smoothly elevates the top walking surface of Ramp_Up, Ramp_TopPlatform, and Ramp_Down
    while keeping the ground contact base at Z=0.0m intact.
    """
    ramp_up = bpy.data.objects.get("Surface_Ramp_Up")
    ramp_top = bpy.data.objects.get("Surface_Ramp_TopPlatform")
    ramp_down = bpy.data.objects.get("Surface_Ramp_Down")

    modified: Dict[str, Any] = {}
    if ramp_up is not None:
        for v in ramp_up.data.vertices:
            if v.co.z > 0.5:
                v.co.z += delta_z
        ramp_up.data.update()
        modified["ramp_up"] = True

    if ramp_top is not None:
        for v in ramp_top.data.vertices:
            if v.co.z > 0.5:
                v.co.z += delta_z
        ramp_top.data.update()
        modified["ramp_top"] = True

    if ramp_down is not None:
        for v in ramp_down.data.vertices:
            if v.co.z > 0.5:
                v.co.z += delta_z
        ramp_down.data.update()
        modified["ramp_down"] = True

    return modified


def generate_dynamics_playground_environment_gate01_u3_blend(
    output_blend_path: str = "output/dynamics_playground_environment_gate01_u3.blend",
    evidence_dir: str = "docs/evidence/environment_gate01_ru3",
    perturbed: bool = False,
    perturb_height_m: float = 0.08,
    route: Optional[TerrainRouteInput] = None,
) -> Dict[str, Any]:
    """Execute Environment Gate 01 / Unit 3 pipeline: Real Mesh BVH Environment -> 19-Bone Motion Pipeline."""
    os.makedirs(evidence_dir, exist_ok=True)
    cfg = PipelineConfig()

    # 1. Open baseline dynamics playground scene
    base_blend = os.path.abspath("output/dynamics_playground.blend")
    if not os.path.exists(base_blend):
        raise FileNotFoundError(f"Baseline playground scene not found: {base_blend}")
    bpy.ops.wm.open_mainfile(filepath=base_blend)

    # 2. Ensure real ground support slabs exist for approach and exit
    scene = bpy.context.scene
    surfaces_col = bpy.data.collections.get("Playground_Surfaces")
    ensure_ramp_corridor_ground_surfaces(scene, surfaces_col)

    # 3. Apply counter-factual geometric perturbation if requested
    if perturbed:
        apply_ramp_mesh_perturbation(delta_z=perturb_height_m)

    # 4. Assemble 19-bone character and rig
    assembly = assemble_character_in_playground(cfg)
    arm_obj = assembly["armature"]
    root_obj = assembly["root"]
    char_col = assembly["collection"]

    # 5. Setup cameras and timeline markers for active animation scene
    cameras = setup_task7a2_cameras_and_markers(scene, char_col)

    # 6. Construct REAL MESH-BACKED terrain environment query
    env = create_mesh_backed_dynamics_query(
        scene=scene,
        collection_names=("Playground_Surfaces",),
        prefer_mesh=True,
    )

    # 7. Build continuous Course B (Ramp) route input
    if route is None:
        route = TerrainRouteInput(
            start_pos=(0.0, 10.20, 0.0),
            target_pos=(0.0, 22.40, 0.0),
            nominal_stride_m=0.30,
            step_frames=16,
            stand_start_frames=12,
            stand_stop_frames=16,
            base_clearance_m=0.12,
            pelvis_drop_uphill_m=0.088,
            pelvis_drop_downhill_m=0.098,
            pelvis_drop_flat_m=0.035,
            torso_lean_uphill_deg=6.0,
            torso_lean_downhill_deg=-2.5,
        )
    action_name = "TerrainWalk_CourseB_Mesh_Perturbed" if perturbed else "TerrainWalk_CourseB_MeshBacked"
    action = TerrainWalkAction(route=route, environment=env, action_name=action_name)

    # 8. Execute through AUTHORITATIVE MotionPlanner
    planner = MotionPlanner(
        config=cfg,
        armature_obj=arm_obj,
        environment=env,
    )
    planner.add_action(action)

    init_state = create_initial_motion_state(
        cfg,
        start_frame=1,
        position=route.start_pos,
    )
    planner_result = planner.execute(initial_state=init_state)

    all_states: List[MotionState] = planner_result["states"]
    all_frame_records: List[dict] = planner_result["frame_records"]
    total_frames = len(all_states)

    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.frame_set(1)

    # 9. Setup Dedicated Internal Blender Diagnostic Scene
    debug_scene = setup_control_chain_debug_scene(scene, char_col, all_frame_records)

    # 10. Check locked foot contact drift
    max_drift = 0.0
    for s in all_states:
        for limb, c in s.contacts.items():
            if c.is_locked:
                max_drift = max(max_drift, c.drift_m)

    # 11. Serialize and embed metadata into scene ID properties on BOTH scenes
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

    is_gate_passed, gate_failure_reasons = verify_scene_execution_gate(
        planner_result,
        all_states,
        fps=float(cfg.fps),
    )
    if not is_gate_passed:
        raise RuntimeError(
            f"generate_dynamics_playground_environment_gate01_u3_blend failed gate verification: "
            f"{'; '.join(gate_failure_reasons)}. Saving .blend delivery artifact prohibited."
        )

    continuous_without_exemption = is_gate_passed
    contact_json_str = json.dumps(contact_records_serialized)

    summary_data = {
        "task": "Environment Gate 01 / Unit 3",
        "perturbed": perturbed,
        "perturb_height_m": perturb_height_m if perturbed else 0.0,
        "environment_source": "blender_mesh_bvh",
        "mesh_collection": "Playground_Surfaces",
        "total_frames": total_frames,
        "max_locked_ankle_drift_m": max_drift,
        "unreachable_count": planner_result["unreachable_count"],
        "route": {
            "start_pos": list(route.start_pos),
            "target_pos": list(route.target_pos),
            "nominal_stride_m": route.nominal_stride_m,
            "total_steps": len(planner_result["step_schedule"]),
        },
        "continuous_without_exemption": continuous_without_exemption,
        "gate_passed": is_gate_passed,
        "gate_failure_reasons": gate_failure_reasons,
        "diagnostic_scene": debug_scene.name,
    }
    summary_json_str = json.dumps(summary_data)
    diag_json_str = json.dumps(all_frame_records)

    for target_scene in [scene, debug_scene]:
        target_scene["environment_gate01_u3_summary"] = summary_json_str
        target_scene["environment_gate01_u3_contacts"] = contact_json_str
        target_scene["task7a2_contact_state_records"] = contact_json_str
        target_scene["task7a2_execution_summary"] = summary_json_str
        target_scene["task7a2_control_chain_diagnostics"] = diag_json_str

    # 12. Save derived mesh-driven blend artifact
    abs_blend_out = os.path.abspath(output_blend_path)
    bpy.ops.wm.save_as_mainfile(filepath=abs_blend_out, check_existing=False)

    # 13. Save companion JSON files
    prefix = "u3_perturbed_" if perturbed else "u3_"
    json_records_path = os.path.join(evidence_dir, f"{prefix}contact_state_records.json")
    with open(json_records_path, "w", encoding="utf-8") as f:
        json.dump(contact_records_serialized, f, indent=2)

    json_summary_path = os.path.join(evidence_dir, f"{prefix}execution_summary.json")
    with open(json_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    json_diag_path = os.path.join(evidence_dir, f"{prefix}control_chain_diagnostics.json")
    with open(json_diag_path, "w", encoding="utf-8") as f:
        json.dump(all_frame_records, f, indent=2)

    return {
        "output_blend_path": abs_blend_out,
        "total_frames": total_frames,
        "max_locked_ankle_drift_m": max_drift,
        "summary": summary_data,
        "planner_result": planner_result,
        "step_schedule": planner_result["step_schedule"],
    }


def generate_dynamics_playground_environment_gate01_u3_s1_blend(
    output_blend_path: str = "output/dynamics_playground_environment_gate01_u3_s1.blend",
    evidence_dir: str = "docs/evidence/environment_gate01_u3_s1",
) -> Dict[str, Any]:
    """Execute Environment Gate 01 / Unit 3 / Atomic Repair S1 pipeline.

    Generates 700-frame continuous locomotion scene with decoupled, C1-continuous Root forward motion.
    """
    return generate_dynamics_playground_environment_gate01_u3_blend(
        output_blend_path=output_blend_path,
        evidence_dir=evidence_dir,
        perturbed=False,
    )


def generate_dynamics_playground_environment_gate01_u3_s2_blend(
    output_blend_path: str = "output/dynamics_playground_environment_gate01_u3_s2.blend",
    evidence_dir: str = "docs/evidence/environment_gate01_u3_s2",
) -> Dict[str, Any]:
    """Execute Environment Gate 01 / Unit 3 / Atomic Repair S2 pipeline.

    Generates 700-frame continuous locomotion scene with continuous Swing->Stance landing targets.
    """
    return generate_dynamics_playground_environment_gate01_u3_blend(
        output_blend_path=output_blend_path,
        evidence_dir=evidence_dir,
        perturbed=False,
    )


if __name__ == "__main__":
    res = generate_dynamics_playground_task7a2_corrected_blend()
    print(f"[SUCCESS] Generated Task 7A-2 corrected blend: {res['output_blend_path']} ({res['total_frames']} frames)")
