"""Playground Character Integration & Orchestration Entry Point (Task 7A-1).

Orchestrates the 19-bone character integration into `DynamicsPlayground`, modularly
delegating to:
1. `src.scene.playground_character_assembly`:
   Character assembly, scene inventory, stages A..D, math checks, and stage E execution.
2. `src.scene.playground_asset_preservation`:
   Baseline snapshot capture, deep mesh/topology/F-curve/73-frame trajectory comparison.
3. `src.scene.playground_kinematic_validation`:
   Read-only 204-frame reopen evaluation, contact state recovery, continuity and CoM.
4. `src.scene.playground_evidence_exporter`:
   PNG rendering, GIF binary frame count inspection, and 204-frame GIF rendering.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import bpy

from src.config import PipelineConfig
from src.scene.environment_query import create_standard_dynamics_playground_query

# Backward compatibility re-exports from modular sub-components
from src.scene.playground_asset_preservation import (
    EXPECTED_CHARACTER_OBJECTS,
    PROTECTED_PLAYGROUND_COLLECTIONS,
    capture_deep_playground_snapshot,
    get_action_fcurves,
    verify_derived_blend_against_deep_snapshot,
)
from src.scene.playground_character_assembly import (
    _setup_character_inspection_cameras,
    assemble_character_in_playground,
    inspect_scene_and_character_inventory,
    run_mathematical_consistency_verifications,
    run_minimal_control_stages_verification,
    run_stage_e_continuous_walk_in_playground,
    snapshot_playground_baseline,
)
from src.scene.playground_evidence_exporter import (
    _load_png_to_numpy_rgba,
    _render_camera_to_png,
    count_gif_frames,
    export_verification_report_json,
    render_reopened_204_frame_walk_gif,
)
from src.scene.playground_kinematic_validation import (
    _quat_geodesic_angle_deg,
    recover_and_verify_contact_states_from_blend,
    validate_reopened_task7a1_blend,
)


def execute_task7a1_pipeline(
    source_playground_blend: Optional[str] = None,
    output_derived_blend: Optional[str] = None,
    evidence_dir: Optional[str] = None,
    render_visuals: bool = True,
) -> Dict[str, Any]:
    """Load `output/dynamics_playground.blend`, integrate the real 19-bone character,
    execute all Task 7A-1 control and mathematical verifications, save the derived
    playable `.blend` scene (`output/dynamics_playground_task7a1.blend`), then reopen
    the saved `.blend` read-only to execute the 204-frame continuous GIF render,
    204-frame full mathematical validation (`full_frame_validation.json`), and deep
    playground preservation diff.
    """
    config = PipelineConfig()
    src_blend = source_playground_blend or os.path.join(
        config.project_root, "output", "dynamics_playground.blend"
    )
    out_blend = output_derived_blend or os.path.join(
        config.project_root, "output", "dynamics_playground_task7a1.blend"
    )
    ev_dir = evidence_dir or os.path.join(
        config.project_root, "docs", "evidence", "task7a1"
    )
    os.makedirs(ev_dir, exist_ok=True)

    if not os.path.isfile(src_blend):
        raise FileNotFoundError(f"Authoritative playground blend not found: {src_blend}")

    # 1. Open authoritative dynamics_playground.blend (read-only on source file) & take deep snapshot
    bpy.ops.wm.open_mainfile(filepath=src_blend)
    scene = bpy.context.scene
    baseline_snap = snapshot_playground_baseline(scene)
    deep_baseline_snap = capture_deep_playground_snapshot(scene)

    # 2. Assemble real 19-bone character into 'Character' collection
    asm = assemble_character_in_playground(config)
    arm_obj = asm["armature"]
    root_obj = asm["root"]
    cameras = asm["cameras"]
    env_query = create_standard_dynamics_playground_query()

    # 3. Inspect scene, 19 bones, 13 mesh parts, and 8 IK/FK controllers
    inventory_report = inspect_scene_and_character_inventory(baseline_snap)

    # 4. Run minimal control closed-loop stages (A, B, C, D)
    stages_abcd_report = run_minimal_control_stages_verification(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
        cameras=cameras,
        evidence_dir=ev_dir,
        render_images=render_visuals,
    )

    # 5. Run mathematical consistency verifications
    math_report = run_mathematical_consistency_verifications(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
    )

    # 6. Run Stage E continuous StartStopWalkAction in playground & save derived blend
    stage_e_report = run_stage_e_continuous_walk_in_playground(
        arm_obj=arm_obj,
        root_obj=root_obj,
        config=config,
        env_query=env_query,
        cameras=cameras,
        output_blend_path=out_blend,
        evidence_dir=ev_dir,
        render_visuals=render_visuals,
    )

    # 7. Verify post-execution playground station integrity
    post_snap = snapshot_playground_baseline(scene)
    stations_intact_after_walk = (
        post_snap["collection_object_counts"] == baseline_snap["collection_object_counts"]
        and post_snap["station_f1"] == baseline_snap["station_f1"]
        and post_snap["station_f73"] == baseline_snap["station_f73"]
    )

    # 8. Reopen saved `output/dynamics_playground_task7a1.blend` read-only to render 204-frame continuous GIF
    gif_path = os.path.join(ev_dir, "task7a1_walk_preview.gif")
    if render_visuals:
        gif_inspection = render_reopened_204_frame_walk_gif(
            derived_blend_path=out_blend,
            gif_output_path=gif_path,
            res_x=320,
            res_y=240,
            delay_cs=4,
        )
    else:
        gif_inspection = count_gif_frames(gif_path)
    stage_e_report["gif_inspection"] = gif_inspection

    # 9. Reopen saved `output/dynamics_playground_task7a1.blend` read-only for 204-frame mathematical validation
    full_frame_json_path = os.path.join(ev_dir, "full_frame_validation.json")
    reopen_validation = validate_reopened_task7a1_blend(
        derived_blend_path=out_blend,
        output_json_path=full_frame_json_path,
        config=config,
    )

    # 10. Reopen saved `output/dynamics_playground_task7a1.blend` read-only for deep asset preservation diff
    deep_asset_diff = verify_derived_blend_against_deep_snapshot(
        deep_baseline=deep_baseline_snap,
        derived_blend_path=out_blend,
    )

    full_report = {
        "task_id": "Task 7A-1",
        "source_playground_blend": os.path.relpath(src_blend, config.project_root).replace("\\", "/"),
        "derived_task7a1_blend": os.path.relpath(out_blend, config.project_root).replace("\\", "/"),
        "full_frame_validation_json": os.path.relpath(full_frame_json_path, config.project_root).replace("\\", "/"),
        "playground_stations_intact_after_walk": stations_intact_after_walk,
        "deep_asset_preservation": deep_asset_diff,
        "reopen_204_frame_validation_summary": {
            "verdict": reopen_validation["verdict"],
            "total_evaluated_frames": reopen_validation["total_evaluated_frames"],
            "root_translation_continuity": reopen_validation["root_translation_continuity"],
            "bone_rotation_continuity": {
                k: v
                for k, v in reopen_validation["bone_rotation_continuity"].items()
                if k != "all_bones"
            },
            "support_foot_and_contact_lifecycle": reopen_validation["support_foot_and_contact_lifecycle"],
            "com_and_rigid_body_geometry": reopen_validation["com_and_rigid_body_geometry"],
        },
        "inventory": inventory_report,
        "minimal_control_stages": {
            "stage_A_static_standing": stages_abcd_report["stage_A_static_standing"],
            "stage_B_root_displacement": stages_abcd_report["stage_B_root_displacement"],
            "stage_C_single_foot_ik": stages_abcd_report["stage_C_single_foot_ik"],
            "stage_D_support_foot_lock": stages_abcd_report["stage_D_support_foot_lock"],
            "stage_E_continuous_walk": stage_e_report,
        },
        "mathematical_consistency": math_report,
    }

    report_json_path = os.path.join(ev_dir, "task7a1_verification_report.json")
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    return full_report
