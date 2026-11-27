"""TASK 10-d-5 — Scene 1 & Scene 2 Generators + T16 Reopen Persistence + Section 7 Gates.

Generates two brand-new 19-bone Blender 5.1.1 assets strictly via centralized
MotionPlanner -> MotionRuntimeContext -> MotionAction -> compose_planned_pose
-> KinematicBridgeExecutor -> WholeBodyController -> Rig:

1. output/task10d_centralized_whole_body.blend (30-45s continuous 5-action compound locomotion)
2. output/task10d_running_whole_body.blend (>= 20s continuous RunAction with decoupled upper limbs)
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import math
import os
import subprocess
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import common_helpers as ch


SCENE1_BLEND = os.path.join(ch.OUTPUT_DIR, "task10d_centralized_whole_body.blend")
SCENE2_BLEND = os.path.join(ch.OUTPUT_DIR, "task10d_running_whole_body.blend")


def _serialize_segments(segs) -> List[Dict[str, Any]]:
    return [dataclasses.asdict(s) for s in segs]


def _make_even_spans(start_t: float, end_t: float, count: int, seed_offset: float) -> List[Tuple[float, float]]:
    """Partition [start_t, end_t] into `count` exact contiguous spans with deterministic non-uniform lengths."""
    weights = [1.0 + 0.18 * math.sin(i * 1.37 + seed_offset) for i in range(count)]
    total_w = sum(weights)
    spans: List[Tuple[float, float]] = []
    cur = float(start_t)
    total_dur = float(end_t - start_t)
    for i, w in enumerate(weights):
        if i == count - 1:
            dur = round(end_t - cur, 6)
        else:
            dur = round(total_dur * (w / total_w), 4)
        spans.append((round(cur, 6), dur))
        cur += dur
    return spans


# =============================================================================
# SCENE 1 BUILDER: 5-ACTION CENTRALIZED WHOLE-BODY COMPOUND SEQUENCE
# =============================================================================

def _build_scene1_actions_and_specs():
    import bpy
    from src.motion.framework import StartStopWalkAction, create_initial_motion_state
    from src.motion.run_cycle import RunAction
    from src.motion.sprint_brake import SprintBrakeAction
    from src.motion.sprint_start import SprintStartAction
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, plan_terrain_footsteps
    from src.motion.upper_limb_trajectory import UpperLimbSegment
    from src.scene.environment_query import create_standard_dynamics_playground_query

    route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0),
        target_pos=(0.0, 22.40, 0.0),
        nominal_stride_m=0.28,
        step_frames=12,
        stand_start_frames=12,
        stand_stop_frames=12,
        base_clearance_m=0.10,
        pelvis_drop_uphill_m=0.075,
        pelvis_drop_downhill_m=0.085,
        pelvis_drop_flat_m=0.035,
    )

    _, _, _, _, _, _, pg_probe_env = ch.assemble_continuous_course_b_scene(with_visual_hands=False)
    _, tw_frames = plan_terrain_footsteps(route, pg_probe_env, start_frame=205)

    n_ss = 204
    n_tw = tw_frames
    n_sp_st = 114
    n_sp_br = 48
    n_run = 4 * 24  # 96 frames = 4.00s (total sequence cleanly inside 30-45s)
    total_frames = n_ss + n_tw + n_sp_st + n_sp_br + n_run
    fps = 24.0
    total_sec = (total_frames - 1) / fps

    b1_frame = n_ss  # boundary between StartStop & TerrainWalk: frame b1_frame -> b1_frame+1
    b2_frame = n_ss + n_tw
    b3_frame = b2_frame + n_sp_st
    b4_frame = b3_frame + n_sp_br

    # Staggered switch times cleanly inside actions (far from boundaries so segments span boundaries!):
    f_L_sw1 = 157   # t = 6.50s (during StartStopWalk decel)
    f_R_sw1 = 289   # t = 12.00s (during TerrainWalk ramp approach/uphill)
    f_L_sw2 = b2_frame + 49  # inside SprintStart accel
    f_R_sw2 = b4_frame + 31  # inside RunAction cycle 2

    t_L_sw1 = (f_L_sw1 - 1) / fps
    t_R_sw1 = (f_R_sw1 - 1) / fps
    t_L_sw2 = (f_L_sw2 - 1) / fps
    t_R_sw2 = (f_R_sw2 - 1) / fps

    def _planner_factory():
        cfg, sc, root_obj, arm_obj, _, _, env = ch.assemble_continuous_course_b_scene(with_visual_hands=False)
        acts = [
            StartStopWalkAction(),
            TerrainWalkAction(route=route, environment=env, action_name="Central_TerrainWalk"),
            SprintStartAction(),
            SprintBrakeAction(),
            RunAction(cycles=4),
        ]
        init_st = create_initial_motion_state(cfg, start_frame=1, position=(0.0, 8.94, 0.0))
        return cfg, env, {"arm_obj": arm_obj, "root_obj": root_obj, "actions": acts, "initial_state": init_st}

    # --- Phase A: Initial FK blocks up to f_sw1 + padding so junction probe reads exact frame posture ---
    neutral_fk = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    pre_ik_fk_L = ((38.0, 0.0, 20.0), (62.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    pre_ik_fk_R = ((38.0, 0.0, -20.0), (62.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    l_fk1_spans = _make_even_spans(0.15, t_L_sw1, 5, seed_offset=0.31)
    l_fk1_poses = [neutral_fk] + [ch.new_fk_waypoint("L", i + 1, 0.45) for i in range(4)] + [pre_ik_fk_L]
    l_fk1_probe = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk1_spans[i][0], duration_sec=l_fk1_spans[i][1], fk_start_deg=l_fk1_poses[i], fk_end_deg=l_fk1_poses[i + 1])
        for i in range(5)
    ]
    # Add short hold extending across f_L_sw1 for exact probe
    l_fk1_probe_ext = tuple(l_fk1_probe + [
        UpperLimbSegment(mode="FK", start_time_sec=t_L_sw1, duration_sec=total_sec - t_L_sw1, fk_start_deg=l_fk1_poses[-1], fk_end_deg=l_fk1_poses[-1])
    ])

    r_fk1_spans = _make_even_spans(0.25, t_R_sw1, 9, seed_offset=1.12)
    r_fk1_poses = [neutral_fk] + [ch.new_fk_waypoint("R", i + 1, 1.75) for i in range(8)] + [pre_ik_fk_R]
    r_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk1_spans[i][0], duration_sec=r_fk1_spans[i][1], fk_start_deg=r_fk1_poses[i], fk_end_deg=r_fk1_poses[i + 1])
        for i in range(9)
    ]
    r_fk1_probe_ext = tuple(r_fk1 + [
        UpperLimbSegment(mode="FK", start_time_sec=t_R_sw1, duration_sec=total_sec - t_R_sw1, fk_start_deg=r_fk1_poses[-1], fk_end_deg=r_fk1_poses[-1])
    ])

    junc1 = ch.probe_real_sequence_poses(
        _planner_factory, l_fk1_probe_ext, r_fk1_probe_ext, total_sec, [f_L_sw1, f_R_sw1]
    )
    ik_start_L = junc1[f_L_sw1]["ik_L"]
    ik_start_R = junc1[f_R_sw1]["ik_R"]

    # --- Phase B: Verified IK blocks spanning [t_sw1 .. t_sw2], crossing boundaries! ---
    def _postures_for_spans(sp_list):
        t_b2 = (b2_frame - 1) / fps
        t_b3 = (b3_frame - 1) / fps
        t_b4 = (b4_frame - 1) / fps
        out = []
        for ts, dur in sp_list:
            te = ts + dur
            pts = []
            if ts <= t_b2 + 0.5:
                pts.extend([(0.00, 0.0, 0.0), (0.045, -4.0, -1.5)])
            if te >= t_b2 - 0.5 and ts <= t_b3 + 0.5:
                pts.extend([(0.060, -12.0, -2.5), (0.115, -20.0, -3.5)])
            if te >= t_b3 - 0.5 and ts <= t_b4 + 0.5:
                pts.extend([(0.050, -4.0, -1.5), (0.090, 6.5, -1.5)])
            if te >= t_b4 - 0.5:
                pts.extend([(0.046, -10.0, -2.5), (0.072, -11.5, -3.5)])
            if not pts:
                pts = [(0.045, -4.0, -1.5)]
            out.append(tuple(pts))
        return out

    l_ik_spans = _make_even_spans(t_L_sw1, t_L_sw2, 16, seed_offset=2.03)
    l_ik_segs = ch.solve_verified_ik_block(
        "L", ik_start_L, l_ik_spans, seed_offset=2.03, pelvis_dz=0.06,
        per_seg_postures=_postures_for_spans(l_ik_spans),
    )

    r_ik_spans = _make_even_spans(t_R_sw1, t_R_sw2, 15, seed_offset=3.41)
    r_ik_segs = ch.solve_verified_ik_block(
        "R", ik_start_R, r_ik_spans, seed_offset=3.41, pelvis_dz=0.06,
        per_seg_postures=_postures_for_spans(r_ik_spans),
    )

    # Probe exact FK poses at IK->FK switches f_L_sw2 and f_R_sw2
    l_until_sw2 = tuple(l_fk1_probe + l_ik_segs + [
        UpperLimbSegment(
            mode="IK", start_time_sec=t_L_sw2, duration_sec=total_sec - t_L_sw2,
            wrist_start_xyz=l_ik_segs[-1].wrist_end_xyz, wrist_end_xyz=l_ik_segs[-1].wrist_end_xyz,
            pole_start_xyz=l_ik_segs[-1].pole_end_xyz, pole_end_xyz=l_ik_segs[-1].pole_end_xyz,
            rotation_start_deg=l_ik_segs[-1].rotation_end_deg, rotation_end_deg=l_ik_segs[-1].rotation_end_deg,
            position_space="ROOT_LOCAL", clamp_reach=False,
        )
    ])
    r_until_sw2 = tuple(r_fk1 + r_ik_segs + [
        UpperLimbSegment(
            mode="IK", start_time_sec=t_R_sw2, duration_sec=total_sec - t_R_sw2,
            wrist_start_xyz=r_ik_segs[-1].wrist_end_xyz, wrist_end_xyz=r_ik_segs[-1].wrist_end_xyz,
            pole_start_xyz=r_ik_segs[-1].pole_end_xyz, pole_end_xyz=r_ik_segs[-1].pole_end_xyz,
            rotation_start_deg=r_ik_segs[-1].rotation_end_deg, rotation_end_deg=r_ik_segs[-1].rotation_end_deg,
            position_space="ROOT_LOCAL", clamp_reach=False,
        )
    ])
    junc2 = ch.probe_real_sequence_poses(
        _planner_factory, l_until_sw2, r_until_sw2, total_sec, [f_L_sw2, f_R_sw2]
    )
    fk2_start_L = junc2[f_L_sw2]["fk_L"]
    fk2_start_R = junc2[f_R_sw2]["fk_R"]

    # --- Phase C: Final FK blocks [t_sw2 .. end], cleanly exceeding >= 24 segments total per side ---
    l_fk2_spans = _make_even_spans(t_L_sw2, total_sec - 0.10, 7, seed_offset=4.19)
    l_fk2_poses = [fk2_start_L] + [ch.new_fk_waypoint("L", i + 30, 4.19) for i in range(6)] + [neutral_fk]
    l_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk2_spans[i][0], duration_sec=l_fk2_spans[i][1], fk_start_deg=l_fk2_poses[i], fk_end_deg=l_fk2_poses[i + 1])
        for i in range(7)
    ]

    r_fk2_spans = _make_even_spans(t_R_sw2, total_sec - 0.05, 5, seed_offset=5.27)
    r_fk2_poses = [fk2_start_R] + [ch.new_fk_waypoint("R", i + 30, 5.27) for i in range(4)] + [neutral_fk]
    r_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk2_spans[i][0], duration_sec=r_fk2_spans[i][1], fk_start_deg=r_fk2_poses[i], fk_end_deg=r_fk2_poses[i + 1])
        for i in range(5)
    ]

    segs_L = tuple(l_fk1_probe + l_ik_segs + l_fk2)  # 5 + 16 + 7 = 28 segments >= 24!
    segs_R = tuple(r_fk1 + r_ik_segs + r_fk2)        # 9 + 15 + 5 = 29 segments >= 24!

    stages = [
        ("StartStopWalk", 1, b1_frame),
        ("TerrainWalk", b1_frame + 1, b2_frame),
        ("SprintStart", b2_frame + 1, b3_frame),
        ("SprintBrake", b3_frame + 1, b4_frame),
        ("Run", b4_frame + 1, total_frames),
    ]
    markers = [
        ("S1_StartStopWalk", 1),
        ("S1_L_FK_to_IK", f_L_sw1),
        ("S1_TerrainWalk", b1_frame + 1),
        ("S1_R_FK_to_IK", f_R_sw1),
        ("S1_SprintStart", b2_frame + 1),
        ("S1_L_IK_to_FK", f_L_sw2),
        ("S1_SprintBrake", b3_frame + 1),
        ("S1_Run", b4_frame + 1),
        ("S1_R_IK_to_FK", f_R_sw2),
        ("S1_End", total_frames),
    ]
    boundaries = [b1_frame, b2_frame, b3_frame, b4_frame]
    return {
        "route": route,
        "run_cycles": 4,
        "total_frames": total_frames,
        "total_sec": total_sec,
        "segs_L": segs_L,
        "segs_R": segs_R,
        "stages": stages,
        "markers": markers,
        "boundaries": boundaries,
        "switches": {"f_L_sw1": f_L_sw1, "f_R_sw1": f_R_sw1, "f_L_sw2": f_L_sw2, "f_R_sw2": f_R_sw2},
    }


# =============================================================================
# SCENE 2 BUILDER: >= 20s CONTINUOUS RUNNING WITH DECOUPLED UPPER LIMBS
# =============================================================================

def _build_scene2_actions_and_specs():
    from src.motion.framework import create_initial_motion_state
    from src.motion.run_cycle import RunAction
    from src.motion.upper_limb_trajectory import UpperLimbSegment

    run_cycles = 22  # 22 * 24 = 528 frames = 22.00s >= 20.0s!
    total_frames = run_cycles * 24
    fps = 24.0
    total_sec = (total_frames - 1) / fps

    f_L_sw1 = 97    # t = 4.00s
    f_R_sw1 = 181   # t = 7.50s
    f_L_sw2 = 349   # t = 14.50s
    f_R_sw2 = 433   # t = 18.00s

    t_L_sw1 = (f_L_sw1 - 1) / fps
    t_R_sw1 = (f_R_sw1 - 1) / fps
    t_L_sw2 = (f_L_sw2 - 1) / fps
    t_R_sw2 = (f_R_sw2 - 1) / fps

    def _planner_factory():
        cfg, sc, root_obj, arm_obj, _, _, env = ch.assemble_flat_locomotion_scene(with_visual_hands=False)
        acts = [RunAction(cycles=run_cycles)]
        init_st = create_initial_motion_state(cfg, start_frame=1, position=(0.0, 0.0, 0.0))
        return cfg, env, {"arm_obj": arm_obj, "root_obj": root_obj, "actions": acts, "initial_state": init_st}

    neutral_fk = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    pre_ik_fk_L = ((38.0, 0.0, 20.0), (62.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    pre_ik_fk_R = ((38.0, 0.0, -20.0), (62.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    l_fk1_spans = _make_even_spans(0.10, t_L_sw1, 4, seed_offset=6.05)
    l_fk1_poses = [neutral_fk] + [ch.new_fk_waypoint("L", i + 1, 6.15) for i in range(3)] + [pre_ik_fk_L]
    l_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk1_spans[i][0], duration_sec=l_fk1_spans[i][1], fk_start_deg=l_fk1_poses[i], fk_end_deg=l_fk1_poses[i + 1])
        for i in range(4)
    ]
    l_fk1_ext = tuple(l_fk1 + [
        UpperLimbSegment(mode="FK", start_time_sec=t_L_sw1, duration_sec=total_sec - t_L_sw1, fk_start_deg=l_fk1_poses[-1], fk_end_deg=l_fk1_poses[-1])
    ])

    r_fk1_spans = _make_even_spans(0.20, t_R_sw1, 7, seed_offset=7.11)
    r_fk1_poses = [neutral_fk] + [ch.new_fk_waypoint("R", i + 1, 7.21) for i in range(6)] + [pre_ik_fk_R]
    r_fk1 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk1_spans[i][0], duration_sec=r_fk1_spans[i][1], fk_start_deg=r_fk1_poses[i], fk_end_deg=r_fk1_poses[i + 1])
        for i in range(7)
    ]
    r_fk1_ext = tuple(r_fk1 + [
        UpperLimbSegment(mode="FK", start_time_sec=t_R_sw1, duration_sec=total_sec - t_R_sw1, fk_start_deg=r_fk1_poses[-1], fk_end_deg=r_fk1_poses[-1])
    ])

    junc1 = ch.probe_real_sequence_poses(_planner_factory, l_fk1_ext, r_fk1_ext, total_sec, [f_L_sw1, f_R_sw1])

    run_postures = ((0.020, -8.5, -1.5), (0.046, -10.0, -2.5), (0.072, -11.5, -3.5))
    l_ik_spans = _make_even_spans(t_L_sw1, t_L_sw2, 9, seed_offset=8.07)
    l_ik = ch.solve_verified_ik_block("L", junc1[f_L_sw1]["ik_L"], l_ik_spans, seed_offset=8.07, pelvis_dz=0.05, postures=run_postures)

    r_ik_spans = _make_even_spans(t_R_sw1, t_R_sw2, 9, seed_offset=9.13)
    r_ik = ch.solve_verified_ik_block("R", junc1[f_R_sw1]["ik_R"], r_ik_spans, seed_offset=9.13, pelvis_dz=0.05, postures=run_postures)

    l_ext2 = tuple(l_fk1 + l_ik + [
        UpperLimbSegment(
            mode="IK", start_time_sec=t_L_sw2, duration_sec=total_sec - t_L_sw2,
            wrist_start_xyz=l_ik[-1].wrist_end_xyz, wrist_end_xyz=l_ik[-1].wrist_end_xyz,
            pole_start_xyz=l_ik[-1].pole_end_xyz, pole_end_xyz=l_ik[-1].pole_end_xyz,
            rotation_start_deg=l_ik[-1].rotation_end_deg, rotation_end_deg=l_ik[-1].rotation_end_deg,
            position_space="ROOT_LOCAL", clamp_reach=False,
        )
    ])
    r_ext2 = tuple(r_fk1 + r_ik + [
        UpperLimbSegment(
            mode="IK", start_time_sec=t_R_sw2, duration_sec=total_sec - t_R_sw2,
            wrist_start_xyz=r_ik[-1].wrist_end_xyz, wrist_end_xyz=r_ik[-1].wrist_end_xyz,
            pole_start_xyz=r_ik[-1].pole_end_xyz, pole_end_xyz=r_ik[-1].pole_end_xyz,
            rotation_start_deg=r_ik[-1].rotation_end_deg, rotation_end_deg=r_ik[-1].rotation_end_deg,
            position_space="ROOT_LOCAL", clamp_reach=False,
        )
    ])
    junc2 = ch.probe_real_sequence_poses(_planner_factory, l_ext2, r_ext2, total_sec, [f_L_sw2, f_R_sw2])

    l_fk2_spans = _make_even_spans(t_L_sw2, total_sec - 0.10, 7, seed_offset=10.17)
    l_fk2_poses = [junc2[f_L_sw2]["fk_L"]] + [ch.new_fk_waypoint("L", i + 40, 10.27) for i in range(6)] + [neutral_fk]
    l_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=l_fk2_spans[i][0], duration_sec=l_fk2_spans[i][1], fk_start_deg=l_fk2_poses[i], fk_end_deg=l_fk2_poses[i + 1])
        for i in range(7)
    ]

    r_fk2_spans = _make_even_spans(t_R_sw2, total_sec - 0.05, 4, seed_offset=11.23)
    r_fk2_poses = [junc2[f_R_sw2]["fk_R"]] + [ch.new_fk_waypoint("R", i + 40, 11.33) for i in range(3)] + [neutral_fk]
    r_fk2 = [
        UpperLimbSegment(mode="FK", start_time_sec=r_fk2_spans[i][0], duration_sec=r_fk2_spans[i][1], fk_start_deg=r_fk2_poses[i], fk_end_deg=r_fk2_poses[i + 1])
        for i in range(4)
    ]

    segs_L = tuple(l_fk1 + l_ik + l_fk2)  # 4 + 9 + 7 = 20 segments >= 16!
    segs_R = tuple(r_fk1 + r_ik + r_fk2)  # 7 + 9 + 4 = 20 segments >= 16!

    stages = [
        ("win_00_04s_FK_FK", 1, f_L_sw1 - 1),
        ("win_04_07s_IK_FK", f_L_sw1, f_R_sw1 - 1),
        ("win_07_14s_IK_IK", f_R_sw1, f_L_sw2 - 1),
        ("win_14_18s_FK_IK", f_L_sw2, f_R_sw2 - 1),
        ("win_18_22s_FK_FK", f_R_sw2, total_frames),
    ]
    markers = [
        ("S2_Run_BothFK", 1),
        ("S2_L_FK_to_IK", f_L_sw1),
        ("S2_R_FK_to_IK", f_R_sw1),
        ("S2_MidRun_BothIK", 264),
        ("S2_L_IK_to_FK", f_L_sw2),
        ("S2_R_IK_to_FK", f_R_sw2),
        ("S2_End", total_frames),
    ]
    return {
        "run_cycles": run_cycles,
        "total_frames": total_frames,
        "total_sec": total_sec,
        "segs_L": segs_L,
        "segs_R": segs_R,
        "stages": stages,
        "markers": markers,
        "switches": {"f_L_sw1": f_L_sw1, "f_R_sw1": f_R_sw1, "f_L_sw2": f_L_sw2, "f_R_sw2": f_R_sw2},
    }


# =============================================================================
# BLENDER WORKER GENERATION & VERIFICATION
# =============================================================================

def _worker_generate_scene(scene_tag: str, blend_out: str, inputs_out: str, report_out: str, solve_dump_out: str) -> None:
    import bpy
    ch.setup_repo_sys_path(ch.REPO_ROOT)
    vr = ch.load_vr()
    ext = ch.load_ext()

    from src.motion.framework import MotionPlanner, StartStopWalkAction, create_initial_motion_state
    from src.motion.run_cycle import RunAction
    from src.motion.sprint_brake import SprintBrakeAction
    from src.motion.sprint_start import SprintStartAction
    from src.motion.terrain_walk import TerrainWalkAction

    if scene_tag == "scene1":
        spec = _build_scene1_actions_and_specs()
        cfg, scene, root_obj, arm_obj, hand_l, hand_r, env = ch.assemble_continuous_course_b_scene(fps=24, with_visual_hands=True)
        init_pos = (0.0, 8.94, 0.0)
        actions = [
            StartStopWalkAction(),
            TerrainWalkAction(route=spec["route"], environment=env, action_name="Central_TerrainWalk"),
            SprintStartAction(),
            SprintBrakeAction(),
            RunAction(cycles=spec["run_cycles"]),
        ]
        min_segs = 24
        input_payload = {
            "scene_id": "scene1_centralized_whole_body",
            "fps": 24,
            "total_frames": spec["total_frames"],
            "sequence_duration_sec": spec["total_sec"],
            "initial_position": list(init_pos),
            "actions": ["StartStopWalkAction", "TerrainWalkAction", "SprintStartAction", "SprintBrakeAction", f"RunAction(cycles={spec['run_cycles']})"],
            "terrain_route": dataclasses.asdict(spec["route"]),
            "upper_limb_L": _serialize_segments(spec["segs_L"]),
            "upper_limb_R": _serialize_segments(spec["segs_R"]),
        }
    elif scene_tag == "scene2":
        spec = _build_scene2_actions_and_specs()
        cfg, scene, root_obj, arm_obj, hand_l, hand_r, env = ch.assemble_flat_locomotion_scene(fps=24, start_pos=(0.0, 0.0, 0.0), with_visual_hands=True)
        init_pos = (0.0, 0.0, 0.0)
        actions = [RunAction(cycles=spec["run_cycles"])]
        min_segs = 16
        input_payload = {
            "scene_id": "scene2_running_whole_body",
            "fps": 24,
            "total_frames": spec["total_frames"],
            "sequence_duration_sec": spec["total_sec"],
            "initial_position": list(init_pos),
            "actions": [f"RunAction(cycles={spec['run_cycles']})"],
            "run_config": {
                "run_cycles": spec["run_cycles"],
                "run_step_length": cfg.run_step_length,
                "run_step_height": cfg.run_step_height,
                "run_stance_frames": cfg.run_stance_frames,
                "run_cycle_frames": cfg.run_cycle_frames,
            },
            "upper_limb_L": _serialize_segments(spec["segs_L"]),
            "upper_limb_R": _serialize_segments(spec["segs_R"]),
        }
    else:
        raise ValueError(f"Unknown scene_tag: {scene_tag}")

    os.makedirs(os.path.dirname(os.path.abspath(inputs_out)), exist_ok=True)
    with open(inputs_out, "w", encoding="utf-8") as fp:
        json.dump(input_payload, fp, indent=2)
    input_sha256 = ch.sha256_file(inputs_out)

    trace, restore = ch.install_full_chain_observer(arm_obj, root_obj, capture_live_poses=True)
    try:
        planner = MotionPlanner(
            config=cfg,
            armature_obj=arm_obj,
            environment=env,
            upper_limb_L=spec["segs_L"],
            upper_limb_R=spec["segs_R"],
            sequence_duration_sec=spec["total_sec"],
        )
        for act in actions:
            planner.add_action(act)
        plan_res = planner.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=init_pos))
    finally:
        restore()

    total_frames = spec["total_frames"]
    solve_frames = trace["solve_frames"]
    assert plan_res["total_frames"] == total_frames and len(solve_frames) == total_frames

    chain_sum = ch.summarize_call_chain_trace(trace, expected_frames=total_frames)
    assert chain_sum["planner_execute_calls"] == 1
    assert chain_sum["unique_planner_instances"] == 1
    assert chain_sum["unique_bridge_instances"] == 1
    assert chain_sum["unique_wbc_instances"] == 1
    assert chain_sum["compose_calls"] == total_frames
    assert chain_sum["bridge_exec_calls"] == total_frames
    assert chain_sum["wbc_exec_calls"] == total_frames
    assert chain_sum["non_upper_integrity_mismatches"] == 0
    assert chain_sum["compose_vs_bridge_mismatches"] == 0
    assert chain_sum["all_wbc_success"]

    eff_l_cnt, eff_l_dur = ext._count_effective_segments(spec["segs_L"])
    eff_r_cnt, eff_r_dur = ext._count_effective_segments(spec["segs_R"])
    assert eff_l_cnt >= min_segs and eff_r_cnt >= min_segs
    total_sec = total_frames / 24.0
    assert eff_l_dur >= 0.75 * total_sec and eff_r_dur >= 0.75 * total_sec, (
        f"Active ratio too low: L={eff_l_dur/total_sec:.3f}, R={eff_r_dur/total_sec:.3f}"
    )

    # Check mode combinations covered
    seen_combos = set()
    for sf in solve_frames:
        l_ik = sf["influences"]["ArmIK.L"] > 0.5
        r_ik = sf["influences"]["ArmIK.R"] > 0.5
        seen_combos.add(("IK" if l_ik else "FK", "IK" if r_ik else "FK"))
    assert seen_combos == {("FK", "FK"), ("FK", "IK"), ("IK", "IK"), ("IK", "FK")}, f"Missing mode combos: {seen_combos}"

    # Verify independent sources on EVERY frame
    for st in plan_res["states"]:
        assert st.params["upper_limb_source_L"] == "CENTRAL"
        assert st.params["upper_limb_source_R"] == "CENTRAL"
        assert st.params["arm_l_rx"] is None and st.params["arm_r_rx"] is None

    # Whole-body metrics across full timeline AND per stage
    full_wb = ch.compute_whole_body_interval_metrics(solve_frames, 1, total_frames)
    for slbl in ("upper_L", "upper_R"):
        assert full_wb[slbl]["upper_arm_rel_span_deg"] >= 25.0
        assert full_wb[slbl]["forearm_rel_span_deg"] >= 25.0
        assert full_wb[slbl]["hand_rel_span_deg"] >= 20.0
        assert full_wb[slbl]["wrist_root_local_span_m"] >= 0.15

    stage_metrics = {}
    for st_name, f_lo, f_hi in spec["stages"]:
        sm = ch.compute_whole_body_interval_metrics(solve_frames, f_lo, f_hi)
        print(
            f"[STAGE_METRICS] {st_name} frames={f_lo}..{f_hi} "
            f"L(ua={sm['upper_L']['upper_arm_rel_span_deg']:.1f}, fa={sm['upper_L']['forearm_rel_span_deg']:.1f}, "
            f"hd={sm['upper_L']['hand_rel_span_deg']:.1f}, w={sm['upper_L']['wrist_root_local_span_m']:.3f}) "
            f"R(ua={sm['upper_R']['upper_arm_rel_span_deg']:.1f}, fa={sm['upper_R']['forearm_rel_span_deg']:.1f}, "
            f"hd={sm['upper_R']['hand_rel_span_deg']:.1f}, w={sm['upper_R']['wrist_root_local_span_m']:.3f})"
        )
        assert sm["upper_L"]["wrist_root_local_span_m"] >= 0.10, f"{st_name} L wrist span too small: {sm['upper_L']}"
        assert sm["upper_R"]["wrist_root_local_span_m"] >= 0.10, f"{st_name} R wrist span too small: {sm['upper_R']}"
        assert sm["upper_L"]["upper_arm_rel_span_deg"] >= 8.0, f"{st_name} L ua span too small: {sm['upper_L']}"
        assert sm["upper_R"]["upper_arm_rel_span_deg"] >= 8.0, f"{st_name} R ua span too small: {sm['upper_R']}"
        assert max(sm["upper_L"]["upper_arm_rel_span_deg"], sm["upper_L"]["forearm_rel_span_deg"]) >= 12.0
        assert max(sm["upper_R"]["upper_arm_rel_span_deg"], sm["upper_R"]["forearm_rel_span_deg"]) >= 12.0
        stage_metrics[st_name] = sm

    # Scene-specific checks
    extra_checks: Dict[str, Any] = {}
    if scene_tag == "scene1":
        # Verify both L & R cross at least one MotionAction boundary within an active non-zero segment
        diag_by_f = {d["frame"]: d for d in trace["compose_diagnostics"]}
        crossed_L = 0
        crossed_R = 0
        for bf in spec["boundaries"]:
            if diag_by_f[bf]["L"]["segment_index"] == diag_by_f[bf + 1]["L"]["segment_index"]:
                crossed_L += 1
            if diag_by_f[bf]["R"]["segment_index"] == diag_by_f[bf + 1]["R"]["segment_index"]:
                crossed_R += 1
        assert crossed_L >= 1 and crossed_R >= 1
        extra_checks["action_boundaries_crossed"] = {"L": crossed_L, "R": crossed_R}
    elif scene_tag == "scene2":
        flight_frames = [f for f in solve_frames if f["is_flight"]]
        assert len(flight_frames) == spec["run_cycles"] * 10
        fl_span_L = vr._max_pairwise_pos_span_m([f["wrist_root_local_L"] for f in flight_frames])
        fl_span_R = vr._max_pairwise_pos_span_m([f["wrist_root_local_R"] for f in flight_frames])
        assert fl_span_L >= 0.25 and fl_span_R >= 0.25
        # Verify ElbowPole moved significantly during IK stages
        assert full_wb["upper_L"]["elbow_pole_span_m"] >= 0.05
        assert full_wb["upper_R"]["elbow_pole_span_m"] >= 0.05
        extra_checks["airborne_flight_frames"] = len(flight_frames)
        extra_checks["airborne_wrist_local_span_L_m"] = fl_span_L
        extra_checks["airborne_wrist_local_span_R_m"] = fl_span_R

    # Check diagnostic hand meshes untouched by keyframing
    assert len(arm_obj.data.bones) == 19
    assert hand_l.parent == arm_obj and hand_l.parent_bone == "hand.L" and hand_l.animation_data is None
    assert hand_r.parent == arm_obj and hand_r.parent_bone == "hand.R" and hand_r.animation_data is None

    # Set timeline markers and open at Frame 1
    ext._add_timeline_markers(scene, spec["markers"])
    scene.frame_start = 1
    scene.frame_end = total_frames
    scene.frame_set(1)
    bpy.context.view_layer.update()

    abs_blend = os.path.abspath(blend_out)
    os.makedirs(os.path.dirname(abs_blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=abs_blend)
    b1 = abs_blend + "1"
    if os.path.exists(b1):
        os.remove(b1)

    asset_info = {
        "path": abs_blend,
        "relative_path": os.path.relpath(abs_blend, ch.REPO_ROOT).replace("\\", "/"),
        "size_bytes": os.path.getsize(abs_blend),
        "sha256": ch.sha256_file(abs_blend),
        "frame_start": 1,
        "frame_end": total_frames,
        "frame_count": total_frames,
        "fps": 24,
        "duration_sec": round(total_frames / 24.0, 4),
    }

    with open(solve_dump_out, "w", encoding="utf-8") as fp:
        json.dump({"solve_frames": solve_frames}, fp, separators=(",", ":"))

    summary = {
        "scene_tag": scene_tag,
        "asset": asset_info,
        "input_file": os.path.relpath(inputs_out, ch.REPO_ROOT).replace("\\", "/"),
        "input_sha256": input_sha256,
        "effective_segments": {
            "L_count": eff_l_cnt,
            "L_active_sec": round(eff_l_dur, 4),
            "L_active_ratio": round(eff_l_dur / total_sec, 4),
            "R_count": eff_r_cnt,
            "R_active_sec": round(eff_r_dur, 4),
            "R_active_ratio": round(eff_r_dur / total_sec, 4),
        },
        "mode_combinations_observed": sorted([list(c) for c in seen_combos]),
        "switches": spec["switches"],
        "markers_count": len(spec["markers"]),
        "call_chain": chain_sum,
        "full_timeline_whole_body": full_wb,
        "stage_metrics": stage_metrics,
        "extra_checks": extra_checks,
    }
    with open(report_out, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2)


def generate_and_verify_both_scenes() -> Dict[str, Any]:
    os.makedirs(ch.SCRATCH_WORK, exist_ok=True)
    os.makedirs(ch.OUTPUT_DIR, exist_ok=True)
    this_file = os.path.abspath(__file__)

    out_summary: Dict[str, Any] = {}
    for tag, blend_path, inputs_path, report_name, reopen_name in (
        (
            "scene1",
            SCENE1_BLEND,
            os.path.join(THIS_DIR, "scene1_inputs.json"),
            "scene1_metrics.json",
            "scene1_reopen.json",
        ),
        (
            "scene2",
            SCENE2_BLEND,
            os.path.join(THIS_DIR, "scene2_inputs.json"),
            "scene2_metrics.json",
            "scene2_reopen.json",
        ),
    ):
        report_path = os.path.join(THIS_DIR, report_name)
        reopen_path = os.path.join(THIS_DIR, reopen_name)
        solve_dump = os.path.join(ch.SCRATCH_WORK, f"{tag}_solve_frames.json")

        cmd_gen = [
            ch.BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1", "--python", this_file, "--",
            "--worker", "generate", "--scene", tag,
            "--blend", blend_path, "--inputs", inputs_path, "--report", report_path, "--solve", solve_dump,
        ]
        p_gen = subprocess.run(cmd_gen, cwd=ch.REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"[generate_{tag}] rc={p_gen.returncode}")
        if p_gen.stdout:
            print(p_gen.stdout[-1200:])
        if p_gen.returncode != 0:
            raise RuntimeError(f"Scene generation {tag} failed (rc={p_gen.returncode}):\n{p_gen.stderr}")

        with open(report_path, "r", encoding="utf-8") as fp:
            s_rep = json.load(fp)

        cmd_re = [
            ch.BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1", "--python", this_file, "--",
            "--worker", "reopen", "--blend", blend_path, "--solve", solve_dump,
            "--markers", str(s_rep["markers_count"]), "--out", reopen_path,
        ]
        p_re = subprocess.run(cmd_re, cwd=ch.REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"[reopen_{tag}] rc={p_re.returncode}")
        if p_re.returncode != 0:
            raise RuntimeError(f"Scene reopen {tag} failed (rc={p_re.returncode}):\n{p_re.stderr}")

        with open(reopen_path, "r", encoding="utf-8") as fp:
            r_rep = json.load(fp)

        out_summary[tag] = {
            "generate_command": cmd_gen,
            "reopen_command": cmd_re,
            "summary": s_rep,
            "reopen_verification": r_rep,
        }

    return out_summary


if __name__ == "__main__":
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        cli = {}
        i = 0
        while i < len(args):
            if args[i].startswith("--") and i + 1 < len(args):
                cli[args[i][2:]] = args[i + 1]
                i += 2
            else:
                i += 1
        if cli["worker"] == "generate":
            _worker_generate_scene(cli["scene"], cli["blend"], cli["inputs"], cli["report"], cli["solve"])
        elif cli["worker"] == "reopen":
            ch.verify_blend_reopen_worker(cli["blend"], cli["solve"], int(cli["markers"]), cli["out"], frame_start=1)
        else:
            raise ValueError(f"Unknown worker: {cli['worker']}")
        print(f"SCENE_WORKER_OK {cli['worker']}")
    else:
        generate_and_verify_both_scenes()
        print("SCENES_AND_REOPEN_PASSED")
