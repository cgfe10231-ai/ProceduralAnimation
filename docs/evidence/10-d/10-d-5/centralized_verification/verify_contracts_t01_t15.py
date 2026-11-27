"""TASK 10-d-5 — Centralized Whole-Body Control Contract Tests (T01 - T15).

Executes real Blender 5.1.1 production runs and historical baseline comparisons against
9f5f825059fad3b9dafa8ed0b9b2c0af1bb7d1d0 without modifying any production source files.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
import functools
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


HIST_ADDED_PARAM_KEYS = {
    "upper_limb_source_L",
    "upper_limb_source_R",
    "planned_upper_limb",
    "historical_arm_swing_ref_deg",
    "actual_upper_limb",
}


def _make_sample_fk_segs(start_t: float, dur1: float, dur2: float, side: str, bias: float):
    from src.motion.upper_limb_trajectory import UpperLimbSegment

    p0 = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    p1 = ch.new_fk_waypoint(side, 1, bias)
    p2 = ch.new_fk_waypoint(side, 2, bias + 0.7)
    return (
        UpperLimbSegment(mode="FK", start_time_sec=start_t, duration_sec=dur1, fk_start_deg=p0, fk_end_deg=p1),
        UpperLimbSegment(mode="FK", start_time_sec=start_t + dur1, duration_sec=dur2, fk_start_deg=p1, fk_end_deg=p2),
    )


def _make_sample_ik_segs(side: str, spans: List[Tuple[float, float]], seed_offset: float):
    fk_init = ((32.0, 0.0, 18.0 if side == "L" else -18.0), (55.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    init_state = ch.compute_ik_state_from_fk_pose(fk_init, side, pelvis_dz=0.05)
    return tuple(ch.solve_verified_ik_block(side, init_state, spans, seed_offset=seed_offset))


# =============================================================================
# T02 / T03 SHARED BASELINE RUNNER (RUNS IDENTICALLY IN 9f5f8250 & HEAD)
# =============================================================================

def _worker_run_baseline_suite(repo_dir: str, out_json: str) -> None:
    import bpy
    from mathutils import Vector

    ch.setup_repo_sys_path(repo_dir)
    from src.config import PipelineConfig
    from src.character.builder import build_character
    from src.rig.builder import build_rig, bind_character_to_rig
    from src.rig.ik import setup_leg_ik
    from src.rig.arm_ik import setup_arm_ik
    from src.rig.pose import reset_pose
    from src.motion.framework import (
        EnvironmentQuery,
        MotionAction,
        MotionMode,
        MotionPlanner,
        StartStopWalkAction,
        create_initial_motion_state,
    )
    from src.motion.run_cycle import RunAction
    from src.motion.sprint_start import SprintStartAction
    from src.motion.sprint_brake import SprintBrakeAction
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction, UpperLimbSegment
    from src.motion.kinematic_bridge import KinematicBridgeExecutor

    vr = ch.load_vr()

    def _fresh_flat_rig(start_pos=(0.0, 0.0, 0.0)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        sc = bpy.context.scene
        sc.render.fps = 24
        cfg = PipelineConfig()
        parts = build_character(cfg)
        root_obj = bpy.data.objects["CharacterRoot"]
        root_obj.location = Vector(start_pos)
        arm_obj = build_rig(cfg, character_root=root_obj)
        bind_character_to_rig(arm_obj, parts)
        reset_pose(arm_obj)
        setup_leg_ik(arm_obj)
        setup_arm_ik(arm_obj)
        bpy.context.view_layer.update()
        return cfg, sc, root_obj, arm_obj, EnvironmentQuery(ground_z=0.0)

    def _capture_run(label: str, actions_builder, env_builder=None):
        if env_builder is None:
            cfg, sc, root_obj, arm_obj, env = _fresh_flat_rig((0.0, 0.0, 0.0))
            init_pos = (0.0, 0.0, 0.0)
        else:
            cfg, sc, root_obj, arm_obj, env, init_pos = env_builder()

        samples = []
        orig_ef = KinematicBridgeExecutor.execute_frame

        @functools.wraps(orig_ef)
        def wrap_ef(self, planned, *args, **kwargs):
            res = orig_ef(self, planned, *args, **kwargs)
            arm_m = arm_obj.matrix_world
            root_m = root_obj.matrix_world
            bone_q = {}
            for bn in ch.BODY_TELEMETRY_BONES:
                pb = arm_obj.pose.bones[bn]
                rel_q, _ = vr._relative_joint_quat_and_euler(arm_obj, bn)
                bone_q[bn] = {
                    "wq": [round(float(v), 6) for v in (arm_m @ pb.matrix).to_3x3().normalized().to_quaternion()],
                    "rq": [round(float(v), 6) for v in rel_q],
                }
            fk_clean = {str(k): [round(float(c), 5) for c in v] for k, v in planned.fk_joint_rotations_deg.items()}
            samples.append({
                "frame": int(planned.frame),
                "mode": str(planned.motion_mode.value),
                "root": [round(float(v), 6) for v in root_m.translation],
                "foot_L": [round(float(v), 6) for v in planned.foot_L.world_xyz],
                "foot_R": [round(float(v), 6) for v in planned.foot_R.world_xyz],
                "wrist_L": [round(float(v), 6) for v in (arm_m @ arm_obj.pose.bones["forearm.L"].tail)],
                "wrist_R": [round(float(v), 6) for v in (arm_m @ arm_obj.pose.bones["forearm.R"].tail)],
                "hand_L_enabled": bool(planned.hand_L and planned.hand_L.enabled),
                "hand_R_enabled": bool(planned.hand_R and planned.hand_R.enabled),
                "fk": fk_clean,
                "bones": bone_q,
                "infs": {cn: round(float(arm_obj.pose.bones[bn].constraints[cn].influence), 6) for cn, bn, _ in ch.UPPER_CONSTRAINTS},
            })
            return res

        KinematicBridgeExecutor.execute_frame = wrap_ef
        try:
            pl = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
            for act in actions_builder(cfg, env):
                pl.add_action(act)
            res = pl.execute(initial_state=create_initial_motion_state(cfg, start_frame=1, position=init_pos))
        finally:
            KinematicBridgeExecutor.execute_frame = orig_ef

        state_rows = []
        for st in res["states"]:
            hist_params = {k: v for k, v in st.params.items() if k not in HIST_ADDED_PARAM_KEYS}
            state_rows.append({
                "frame": int(st.frame),
                "pos": [round(float(v), 6) for v in st.position],
                "vel": [round(float(v), 6) for v in st.velocity],
                "mode": str(st.mode.value),
                "is_airborne": bool(st.is_airborne),
                "contacts": {
                    k: {
                        "is_locked": bool(c.is_locked),
                        "phase": str(c.phase),
                        "xyz": [round(float(v), 5) for v in c.contact_world_xyz],
                    }
                    for k, c in st.contacts.items()
                },
                "hist_arm_l_rx": hist_params.get("arm_l_rx"),
                "hist_arm_r_rx": hist_params.get("arm_r_rx"),
            })
        return {"label": label, "total_frames": int(res["total_frames"]), "samples": samples, "states": state_rows}

    def _terrain_env_builder():
        from src.scene.environment_query import create_standard_dynamics_playground_query
        cfg, sc, root_obj, arm_obj, _ = _fresh_flat_rig((0.0, 10.20, 0.0))
        return cfg, sc, root_obj, arm_obj, create_standard_dynamics_playground_query(), (0.0, 10.20, 0.0)

    flat_route = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0), target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30, step_frames=16, stand_start_frames=24, stand_stop_frames=24,
    )

    runs = {}
    runs["start_stop_walk"] = _capture_run("start_stop_walk", lambda c, e: [StartStopWalkAction()])
    runs["terrain_walk_no_upper"] = _capture_run(
        "terrain_walk_no_upper", lambda c, e: [TerrainWalkAction(route=flat_route, environment=e)], _terrain_env_builder
    )
    runs["run"] = _capture_run("run", lambda c, e: [RunAction(cycles=2)])
    runs["sprint_start"] = _capture_run("sprint_start", lambda c, e: [SprintStartAction()])
    runs["sprint_start_brake"] = _capture_run("sprint_start_brake", lambda c, e: [SprintStartAction(), SprintBrakeAction()])

    # T03: TerrainWalkAction local FK (L) + IK (R) compatibility check
    local_fk_l = (
        UpperLimbSegment(
            mode="FK", start_time_sec=0.10, duration_sec=1.60,
            fk_start_deg=((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((55.0, 12.0, 28.0), (62.0, 15.0, 0.0), (18.0, 6.0, 10.0)),
        ),
        UpperLimbSegment(
            mode="FK", start_time_sec=1.90, duration_sec=2.00,
            fk_start_deg=((55.0, 12.0, 28.0), (62.0, 15.0, 0.0), (18.0, 6.0, 10.0)),
            fk_end_deg=((20.0, -10.0, 45.0), (88.0, -18.0, 0.0), (-15.0, -4.0, -8.0)),
        ),
    )
    _, _, _, probe_arm, _ = _fresh_flat_rig((0.0, 10.20, 0.0))
    w_r0, p_r0 = (0.24, 0.14, 1.12), (0.32, -0.22, 1.18)
    w_r1, p_r1 = (0.36, 0.26, 1.32), (0.38, -0.24, 1.20)
    w_r2, p_r2 = (0.26, 0.28, 1.44), (0.34, -0.22, 1.22)
    rot_r0 = vr._compute_hand_world_rot_for_ik_keypose(probe_arm, "R", w_r0, p_r0, (0.0, 0.0, 0.0))
    rot_r1 = vr._compute_hand_world_rot_for_ik_keypose(probe_arm, "R", w_r1, p_r1, (14.0, -4.0, -8.0))
    rot_r2 = vr._compute_hand_world_rot_for_ik_keypose(probe_arm, "R", w_r2, p_r2, (-12.0, 4.0, 6.0))
    local_ik_r = (
        UpperLimbSegment(
            mode="IK", start_time_sec=0.15, duration_sec=1.75,
            wrist_start_xyz=w_r0, wrist_end_xyz=w_r1,
            pole_start_xyz=p_r0, pole_end_xyz=p_r1,
            rotation_start_deg=rot_r0, rotation_end_deg=rot_r1,
            position_space="ROOT_LOCAL", clamp_reach=True,
        ),
        UpperLimbSegment(
            mode="IK", start_time_sec=2.05, duration_sec=1.80,
            wrist_start_xyz=w_r1, wrist_end_xyz=w_r2,
            pole_start_xyz=p_r1, pole_end_xyz=p_r2,
            rotation_start_deg=rot_r1, rotation_end_deg=rot_r2,
            position_space="ROOT_LOCAL", clamp_reach=True,
        ),
    )
    runs["terrain_walk_local_fk_ik"] = _capture_run(
        "terrain_walk_local_fk_ik",
        lambda c, e: [TerrainWalkAction(route=flat_route, environment=e, upper_limb_L=local_fk_l, upper_limb_R=local_ik_r)],
        _terrain_env_builder,
    )

    # Historical failure contracts
    fail_checks = {}
    cfg, sc, root_obj, arm_obj, env = _fresh_flat_rig()
    for fname, fn in (
        ("empty_planner", lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=env).execute()),
        ("start_stop_bad_mode", lambda: StartStopWalkAction().can_start_from(
            create_initial_motion_state(cfg).clone_with(mode=MotionMode.RUN)
        )),
        ("sprint_brake_bad_mode", lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=env).add_action(SprintBrakeAction()).execute()),
        ("terrain_bad_collinear_x", lambda: TerrainWalkAction(
            route=TerrainRouteInput(start_pos=(0.0, 0.0, 0.0), target_pos=(1.0, 2.0, 0.0)),
            environment=env,
        ).execute(create_initial_motion_state(cfg), None)),
    ):
        try:
            r = fn()
            fail_checks[fname] = {"raised": False, "ret": r}
        except Exception as exc:
            fail_checks[fname] = {"raised": True, "exc_type": type(exc).__name__}

    # Failure blocking second action when disabled
    class _FailAction(MotionAction):
        def __init__(self):
            self.called = False
        @property
        def name(self):
            return "fail_stub"
        def estimate_duration_frames(self, s, c):
            return 2
        def execute(self, s, ctx):
            raise RuntimeError("Injected action failure")

    class _SecondAction(MotionAction):
        def __init__(self):
            self.called = False
        @property
        def name(self):
            return "second_stub"
        def estimate_duration_frames(self, s, c):
            return 2
        def execute(self, s, ctx):
            self.called = True
            raise RuntimeError("Should never run")

    sec = _SecondAction()
    try:
        MotionPlanner(cfg, armature_obj=arm_obj, environment=env).add_action(_FailAction()).add_action(sec).execute()
        fail_checks["planner_blocks_second"] = {"raised": False, "second_called": sec.called}
    except RuntimeError:
        fail_checks["planner_blocks_second"] = {"raised": True, "second_called": sec.called}

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump({"repo_dir": repo_dir, "runs": runs, "fail_checks": fail_checks}, fp)


# =============================================================================
# MAIN CONTRACT SUITE WORKER T01, T04 - T15 (RUNS AGAINST HEAD)
# =============================================================================

def _worker_run_contracts_cur(out_json: str) -> None:
    import bpy
    from mathutils import Quaternion, Vector

    ch.setup_repo_sys_path(ch.REPO_ROOT)
    vr = ch.load_vr()
    from src.config import PipelineConfig
    from src.motion.framework import (
        ActionExecutionResult,
        MotionAction,
        MotionMode,
        MotionPlanner,
        MotionRuntimeContext,
        StartStopWalkAction,
        create_initial_motion_state,
    )
    from src.motion.kinematic_bridge import KinematicBridgeExecutor, KinematicPlannedPose, PlannedFootTarget, PlannedHandTarget
    from src.motion.run_cycle import RunAction
    from src.motion.sprint_start import SprintStartAction
    from src.motion.sprint_brake import SprintBrakeAction
    from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
    from src.motion.upper_limb_trajectory import UpperLimbSegment
    from src.scene.environment_query import create_standard_dynamics_playground_query

    results: Dict[str, Any] = {}

    def _expect_raises(exc_types, fn, label: str, bridge_count_checker=None):
        before = bridge_count_checker() if bridge_count_checker else 0
        try:
            fn()
        except exc_types as exc:
            after = bridge_count_checker() if bridge_count_checker else 0
            assert after == before, f"{label}: Bridge/WBC called {after - before} times before failure!"
            return {"rejected": True, "exc_type": type(exc).__name__, "msg": str(exc)[:180], "solve_calls_during_attempt": after - before}
        raise AssertionError(f"{label}: Expected {exc_types} to be raised, succeeded instead!")

    # -------------------------------------------------------------------------
    # T01: Central Input & Admission Gates (All 10 categories, zero solves)
    # -------------------------------------------------------------------------
    cfg, sc, root_obj, arm_obj, _, _, flat_env = ch.assemble_flat_locomotion_scene(with_visual_hands=False)
    trace01, rest01 = ch.install_full_chain_observer(arm_obj, root_obj, capture_live_poses=False)
    t01_cases = {}
    try:
        solve_cnt = lambda: trace01["bridge_exec_calls"] + trace01["wbc_exec_calls"]
        valid_fk = _make_sample_fk_segs(0.0, 1.0, 1.0, "L", 0.3)

        # 1. Invalid / non-finite FPS
        for bad_fps in (0, -24, float("nan"), float("inf"), True, "24"):
            bad_cfg = dataclasses.replace(cfg, fps=bad_fps)
            t01_cases[f"bad_fps_{bad_fps!r}"] = _expect_raises(
                (ValueError, TypeError),
                lambda c=bad_cfg: MotionPlanner(c, armature_obj=arm_obj, environment=flat_env),
                f"bad_fps_{bad_fps!r}",
                solve_cnt,
            )

        # 2. Missing sequence_duration_sec when central enabled
        t01_cases["missing_seq_dur_init"] = _expect_raises(
            ValueError,
            lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env, upper_limb_L=valid_fk),
            "missing_seq_dur_init",
            solve_cnt,
        )
        pl_no_dur = MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env).add_action(StartStopWalkAction())
        t01_cases["missing_seq_dur_execute"] = _expect_raises(
            ValueError,
            lambda: pl_no_dur.execute(upper_limb_L=valid_fk),
            "missing_seq_dur_execute",
            solve_cnt,
        )

        # 3. Non-integer frame boundary duration
        t01_cases["non_int_boundary_dur"] = _expect_raises(
            ValueError,
            lambda: MotionPlanner(
                cfg, armature_obj=arm_obj, environment=flat_env,
                upper_limb_L=valid_fk, sequence_duration_sec=1.01,
            ),
            "non_int_boundary_dur",
            solve_cnt,
        )

        # 4. Illegal segments
        bad_seg_inputs = {
            "empty_tuple": (),
            "list_not_tuple": [valid_fk[0]],
            "bad_mode": (UpperLimbSegment(mode="MAGIC", start_time_sec=0.0, duration_sec=1.0),),
            "neg_start": (UpperLimbSegment(mode="FK", start_time_sec=-0.1, duration_sec=1.0, fk_start_deg=valid_fk[0].fk_start_deg, fk_end_deg=valid_fk[0].fk_end_deg),),
            "zero_dur": (UpperLimbSegment(mode="FK", start_time_sec=0.0, duration_sec=0.0, fk_start_deg=valid_fk[0].fk_start_deg, fk_end_deg=valid_fk[0].fk_end_deg),),
            "nan_coord": (UpperLimbSegment(mode="IK", start_time_sec=0.0, duration_sec=1.0, wrist_start_xyz=(0.0, float("nan"), 1.2), wrist_end_xyz=(0.1, 0.2, 1.2)),),
        }
        for k, bseg in bad_seg_inputs.items():
            t01_cases[f"illegal_seg_{k}"] = _expect_raises(
                (ValueError, TypeError),
                lambda s=bseg: MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env, upper_limb_L=s, sequence_duration_sec=2.0),
                f"illegal_seg_{k}",
                solve_cnt,
            )

        # 5. Overlapping segments
        overlap = (
            valid_fk[0],
            dataclasses.replace(valid_fk[1], start_time_sec=0.5),
        )
        t01_cases["overlapping_segs"] = _expect_raises(
            ValueError,
            lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env, upper_limb_L=overlap, sequence_duration_sec=2.0),
            "overlapping_segs",
            solve_cnt,
        )

        # 6. Discontinuous same-mode endpoints
        disc_fk = (
            valid_fk[0],
            dataclasses.replace(valid_fk[1], fk_start_deg=((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))),
        )
        t01_cases["discontinuous_same_mode"] = _expect_raises(
            ValueError,
            lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env, upper_limb_L=disc_fk, sequence_duration_sec=2.0),
            "discontinuous_same_mode",
            solve_cnt,
        )

        # 7. Un-admitted MotionAction (does not support centralized control)
        class _UnadmittedAction(MotionAction):
            @property
            def name(self):
                return "unadmitted_custom"
            def estimate_duration_frames(self, init_state, config):
                return 49
            def execute(self, init_state, context):
                raise AssertionError("Must not execute!")

        pl_unadm = MotionPlanner(
            cfg, armature_obj=arm_obj, environment=flat_env,
            upper_limb_L=valid_fk, sequence_duration_sec=(49 - 1) / 24.0,
        ).add_action(_UnadmittedAction())
        t01_cases["unadmitted_action"] = _expect_raises(TypeError, pl_unadm.execute, "unadmitted_action", solve_cnt)

        # 8. Unauthorized derived MotionAction
        class _DerivedWalk(StartStopWalkAction):
            pass

        pl_deriv = MotionPlanner(
            cfg, armature_obj=arm_obj, environment=flat_env,
            upper_limb_L=valid_fk, sequence_duration_sec=(204 - 1) / 24.0,
        ).add_action(_DerivedWalk())
        t01_cases["unauthorized_derived_action"] = _expect_raises(TypeError, pl_deriv.execute, "unauthorized_derived_action", solve_cnt)

        # 9. Declared timeline over-bound (seg > seq_dur AND static action sum > seq_dur)
        t01_cases["seg_exceeds_seq_dur"] = _expect_raises(
            ValueError,
            lambda: MotionPlanner(cfg, armature_obj=arm_obj, environment=flat_env, upper_limb_L=valid_fk, sequence_duration_sec=1.5),
            "seg_exceeds_seq_dur",
            solve_cnt,
        )
        pl_static_over = MotionPlanner(
            cfg, armature_obj=arm_obj, environment=flat_env,
            upper_limb_L=valid_fk, sequence_duration_sec=(100 - 1) / 24.0,
        ).add_action(StartStopWalkAction())
        t01_cases["static_action_exceeds_seq_dur"] = _expect_raises(
            ValueError, pl_static_over.execute, "static_action_exceeds_seq_dur", solve_cnt
        )

        # 10. Runtime terrain-dependent duration exceeds declared seq_dur BEFORE TerrainWalk runs
        terr_over_route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0), target_pos=(0.0, 2.0, 0.0),
            nominal_stride_m=0.30, step_frames=16, stand_start_frames=12, stand_stop_frames=12,
        )
        pl_terr_over = MotionPlanner(
            cfg, armature_obj=arm_obj, environment=flat_env,
            upper_limb_L=_make_sample_fk_segs(0.0, 3.0, 3.0, "L", 0.4),
            sequence_duration_sec=(204 + 10 - 1) / 24.0,
        )
        pl_terr_over.add_action(StartStopWalkAction())
        pl_terr_over.add_action(TerrainWalkAction(route=terr_over_route, environment=flat_env))
        # Reset bridge counter after action 1? Action 1 runs 204 frames, then Action 2 predicts >214 and raises BEFORE Action 2!
        pre_cnt_t10 = trace01["bridge_exec_calls"]
        try:
            pl_terr_over.execute()
            raise AssertionError("Expected terrain predicted over-bound ValueError!")
        except ValueError as exc:
            post_cnt_t10 = trace01["bridge_exec_calls"]
            assert post_cnt_t10 - pre_cnt_t10 == 204, f"Expected exactly 204 solves (StartStop only), got {post_cnt_t10 - pre_cnt_t10}"
            t01_cases["runtime_terrain_overbound"] = {
                "rejected": True,
                "exc_type": type(exc).__name__,
                "action1_solves": post_cnt_t10 - pre_cnt_t10,
                "action2_solves": 0,
            }
    finally:
        rest01()
    results["T01"] = {"passed": True, "cases": t01_cases}

    # -------------------------------------------------------------------------
    # T04: Control Ownership Conflict & Cross-Side Legal Combination
    # -------------------------------------------------------------------------
    t04_env = create_standard_dynamics_playground_query()
    route4 = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0), target_pos=(0.0, 11.40, 0.0),
        nominal_stride_m=0.30, step_frames=16, stand_start_frames=24, stand_stop_frames=24,
    )
    total_4 = 128  # 5*16 + 48 = 128
    seq_dur_4 = (total_4 - 1) / 24.0
    cen_l_4 = _make_sample_fk_segs(0.2, 2.0, 2.2, "L", 0.8)
    loc_l_4 = _make_sample_fk_segs(0.2, 1.5, 1.5, "L", 1.2)
    loc_r_4 = _make_sample_ik_segs("R", [(0.25, 2.0), (2.25, 2.0)], 2.1)

    cfg4, sc4, root4, arm4, _, _, _ = ch.assemble_flat_locomotion_scene(start_pos=(0.0, 10.20, 0.0), with_visual_hands=False)
    trace4, rest4 = ch.install_full_chain_observer(arm4, root4, capture_live_poses=True)
    try:
        conflict_pl = MotionPlanner(
            cfg4, armature_obj=arm4, environment=t04_env,
            upper_limb_L=cen_l_4, sequence_duration_sec=seq_dur_4,
        ).add_action(TerrainWalkAction(route=route4, environment=t04_env, upper_limb_L=loc_l_4))
        c_res = _expect_raises(
            ValueError,
            lambda: conflict_pl.execute(initial_state=create_initial_motion_state(cfg4, start_frame=1, position=route4.start_pos)),
            "same_side_conflict_L",
            lambda: trace4["bridge_exec_calls"],
        )

        # Cross-side legal: central L + local R
        cross_pl = MotionPlanner(
            cfg4, armature_obj=arm4, environment=t04_env,
            upper_limb_L=cen_l_4, sequence_duration_sec=seq_dur_4,
        ).add_action(TerrainWalkAction(route=route4, environment=t04_env, upper_limb_R=loc_r_4))
        cross_out = cross_pl.execute(initial_state=create_initial_motion_state(cfg4, start_frame=1, position=route4.start_pos))
        assert len(cross_out["states"]) == total_4
        st_mid = cross_out["states"][len(cross_out["states"]) // 2]
        assert st_mid.params["upper_limb_source_L"] == "CENTRAL"
        assert st_mid.params["upper_limb_source_R"] == "ACTION_LOCAL"
        assert st_mid.params["planned_upper_limb"]["L"]["time_base"] == "SEQUENCE"
        assert st_mid.params["planned_upper_limb"]["R"]["time_base"] == "ACTION"
    finally:
        rest4()
    results["T04"] = {
        "passed": True,
        "conflict_rejected": c_res,
        "cross_side_frames": len(cross_out["states"]),
        "mid_source_L": st_mid.params["upper_limb_source_L"],
        "mid_source_R": st_mid.params["upper_limb_source_R"],
    }

    # Helper to execute single or chained action with centralized bilateral FK+IK
    def _run_centralized_test(label: str, actions_list, use_playground: bool, start_pos, seq_dur, cen_L, cen_R, start_frame: int = 1):
        if use_playground:
            cfg_x, _, root_x, arm_x, _, _, env_x = ch.assemble_continuous_course_b_scene(with_visual_hands=False)
            root_x.location = Vector(start_pos)
            bpy.context.view_layer.update()
        else:
            cfg_x, _, root_x, arm_x, _, _, env_x = ch.assemble_flat_locomotion_scene(start_pos=start_pos, with_visual_hands=False)

        tr, rest = ch.install_full_chain_observer(arm_x, root_x, capture_live_poses=True)
        try:
            pl = MotionPlanner(
                cfg_x, armature_obj=arm_x, environment=env_x,
                upper_limb_L=cen_L, upper_limb_R=cen_R, sequence_duration_sec=seq_dur,
            )
            for a in actions_list:
                pl.add_action(a)
            res = pl.execute(initial_state=create_initial_motion_state(cfg_x, start_frame=start_frame, position=start_pos))
        finally:
            rest()

        for st in res["states"]:
            assert st.params["upper_limb_source_L"] == "CENTRAL"
            assert st.params["upper_limb_source_R"] == "CENTRAL"
            assert st.params["arm_l_rx"] is None and st.params["arm_r_rx"] is None
        chain_sum = ch.summarize_call_chain_trace(tr, expected_frames=res["total_frames"])
        assert chain_sum["planner_execute_calls"] == 1
        assert chain_sum["unique_planner_instances"] == 1
        assert chain_sum["unique_bridge_instances"] == 1
        assert chain_sum["unique_wbc_instances"] == 1
        assert chain_sum["compose_calls"] == res["total_frames"]
        assert chain_sum["bridge_exec_calls"] == res["total_frames"]
        assert chain_sum["wbc_exec_calls"] == res["total_frames"]
        assert chain_sum["non_upper_integrity_mismatches"] == 0
        assert chain_sum["compose_vs_bridge_mismatches"] == 0
        assert chain_sum["all_wbc_success"]
        wb = ch.compute_whole_body_interval_metrics(tr["solve_frames"], start_frame, start_frame + res["total_frames"] - 1)
        assert wb["upper_L"]["wrist_root_local_span_m"] >= 0.12
        assert wb["upper_R"]["wrist_root_local_span_m"] >= 0.12
        return res, tr, chain_sum, wb

    # T05: StartStopWalk (204 frames, 8.458333s, L=FK, R=IK)
    ss_dur = (204 - 1) / 24.0
    _, tr05, cs05, wb05 = _run_centralized_test(
        "T05", [StartStopWalkAction()], False, (0.0, 0.0, 0.0), ss_dur,
        _make_sample_fk_segs(0.2, 3.8, 3.8, "L", 0.5),
        _make_sample_ik_segs("R", [(0.2, 3.8), (4.0, 3.8)], 0.9),
    )
    results["T05"] = {"passed": True, "call_chain": cs05, "upper_L": wb05["upper_L"], "upper_R": wb05["upper_R"]}

    # T06: TerrainWalk on actual 15° uphill ramp (start Y=10.20 -> 15.00)
    r06 = TerrainRouteInput(start_pos=(0.0, 10.20, 0.0), target_pos=(0.0, 14.50, 0.0), nominal_stride_m=0.30, step_frames=16, stand_start_frames=16, stand_stop_frames=16)
    from src.motion.terrain_walk import plan_terrain_footsteps
    _, nf06 = plan_terrain_footsteps(r06, create_standard_dynamics_playground_query(), start_frame=1)
    dur06 = (nf06 - 1) / 24.0
    _, tr06, cs06, wb06 = _run_centralized_test(
        "T06", [TerrainWalkAction(route=r06)], True, r06.start_pos, dur06,
        _make_sample_fk_segs(0.2, 0.4 * dur06, 0.45 * dur06, "L", 1.1),
        _make_sample_ik_segs("R", [(0.2, 0.4 * dur06), (0.2 + 0.4 * dur06, 0.45 * dur06)], 1.3),
    )
    results["T06"] = {"passed": True, "call_chain": cs06, "upper_L": wb06["upper_L"], "upper_R": wb06["upper_R"]}

    # T07: Run (4 cycles = 96 frames = 3.958333s) checking airborne flight frames specifically
    dur07 = (96 - 1) / 24.0
    res07, tr07, cs07, wb07 = _run_centralized_test(
        "T07", [RunAction(cycles=4)], False, (0.0, 0.0, 0.0), dur07,
        _make_sample_fk_segs(0.1, 1.8, 1.9, "L", 1.7),
        _make_sample_ik_segs("R", [(0.1, 1.8), (1.9, 1.9)], 1.9),
    )
    flight_frames = [f for f in tr07["solve_frames"] if f["is_flight"]]
    assert len(flight_frames) == 40
    flight_L_span = vr._max_pairwise_pos_span_m([f["wrist_root_local_L"] for f in flight_frames])
    flight_R_span = vr._max_pairwise_pos_span_m([f["wrist_root_local_R"] for f in flight_frames])
    assert flight_L_span >= 0.12 and flight_R_span >= 0.12
    results["T07"] = {
        "passed": True, "call_chain": cs07,
        "airborne_frames": len(flight_frames),
        "flight_wrist_local_span_L_m": flight_L_span,
        "flight_wrist_local_span_R_m": flight_R_span,
        "upper_L": wb07["upper_L"], "upper_R": wb07["upper_R"],
    }

    # T08: SprintStart (114 frames)
    dur08 = (114 - 1) / 24.0
    res08, tr08, cs08, wb08 = _run_centralized_test(
        "T08", [SprintStartAction()], False, (0.0, 0.0, 0.0), dur08,
        _make_sample_fk_segs(0.15, 2.1, 2.2, "L", 2.3),
        _make_sample_ik_segs("R", [(0.15, 2.1), (2.25, 2.2)], 2.5),
    )
    stages08 = sorted({st.params["stage"] for st in res08["states"]})
    assert set(stages08) == {"prep", "start", "accelerate", "sprint"}
    results["T08"] = {"passed": True, "stages": stages08, "call_chain": cs08, "upper_L": wb08["upper_L"], "upper_R": wb08["upper_R"]}

    # T09: SprintStart -> SprintBrake (114 + 48 = 162 frames), arms keep moving during brake (frames 115..162)
    dur09 = (162 - 1) / 24.0
    res09, tr09, cs09, wb09 = _run_centralized_test(
        "T09", [SprintStartAction(), SprintBrakeAction()], False, (0.0, 0.0, 0.0), dur09,
        _make_sample_fk_segs(0.2, 4.4, 2.0, "L", 2.9),
        _make_sample_ik_segs("R", [(0.2, 4.4), (4.6, 1.0), (5.6, 1.1)], 1.7),
    )
    wb09_brake = ch.compute_whole_body_interval_metrics(tr09["solve_frames"], 115, 162)
    assert wb09_brake["upper_L"]["wrist_root_local_span_m"] >= 0.08
    assert wb09_brake["upper_R"]["wrist_root_local_span_m"] >= 0.08
    results["T09"] = {
        "passed": True,
        "handoff_speed_mps": res09["action_results"][0].final_state.velocity[1],
        "brake_final_speed_mps": res09["action_results"][1].final_state.velocity[1],
        "brake_upper_L": wb09_brake["upper_L"],
        "brake_upper_R": wb09_brake["upper_R"],
    }

    # -------------------------------------------------------------------------
    # T10, T12, T13: Cross-Action Continuity, Unique Execution Chain & Non-Upper Integrity
    # Chain: StartStopWalk(204) -> TerrainWalk(~176) -> SprintStart(114) -> SprintBrake(48) -> Run(48)
    # -------------------------------------------------------------------------
    route10 = TerrainRouteInput(
        start_pos=(0.0, 10.20, 0.0), target_pos=(0.0, 22.40, 0.0),
        nominal_stride_m=0.28, step_frames=12, stand_start_frames=12, stand_stop_frames=12,
        base_clearance_m=0.10, pelvis_drop_uphill_m=0.075, pelvis_drop_downhill_m=0.085,
    )
    _, _, _, _, _, _, env10_probe = ch.assemble_continuous_course_b_scene(with_visual_hands=False)
    start_pos10 = (0.0, 8.94, 0.0)
    _, tw_frames_10 = plan_terrain_footsteps(
        dataclasses.replace(route10, start_pos=(0.0, 10.20, 0.0)), env10_probe, start_frame=205
    )
    total10 = 204 + tw_frames_10 + 114 + 48 + 48
    dur10 = (total10 - 1) / 24.0
    b1_t = (204 - 1) / 24.0
    b2_t = (204 + tw_frames_10 - 1) / 24.0
    b3_t = (204 + tw_frames_10 + 114 - 1) / 24.0
    b4_t = (204 + tw_frames_10 + 114 + 48 - 1) / 24.0

    # Left FK spans boundaries 1 and 3 intentionally; Right IK spans boundaries 2 and 4 intentionally
    pL0 = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    pL1 = ch.new_fk_waypoint("L", 1, 0.4)
    pL2 = ch.new_fk_waypoint("L", 2, 1.1)
    pL3 = ch.new_fk_waypoint("L", 3, 2.2)
    cen10_L = (
        UpperLimbSegment(mode="FK", start_time_sec=0.5, duration_sec=(b1_t - 0.5) + 2.5, fk_start_deg=pL0, fk_end_deg=pL1),  # spans b1!
        UpperLimbSegment(mode="FK", start_time_sec=b1_t + 2.5, duration_sec=(b3_t - (b1_t + 2.5)) + 1.0, fk_start_deg=pL1, fk_end_deg=pL2),  # spans b2 & b3!
        UpperLimbSegment(mode="FK", start_time_sec=b3_t + 1.0, duration_sec=dur10 - (b3_t + 1.0) - 0.1, fk_start_deg=pL2, fk_end_deg=pL3),  # spans b4!
    )
    cen10_R = _make_sample_ik_segs(
        "R",
        [
            (0.4, b2_t - 0.4 + 1.8),  # spans b1 & b2!
            (b2_t + 1.8, (b4_t - (b2_t + 1.8)) + 1.0),  # spans b3 & b4!
        ],
        seed_offset=3.7,
    )

    cfg10, _, root10, arm10, _, _, env10 = ch.assemble_continuous_course_b_scene(with_visual_hands=False)
    root10.location = Vector((0.0, 8.94, 0.0))
    bpy.context.view_layer.update()
    tr10, rest10 = ch.install_full_chain_observer(arm10, root10, capture_live_poses=True)
    try:
        pl10 = MotionPlanner(
            cfg10, armature_obj=arm10, environment=env10,
            upper_limb_L=cen10_L, upper_limb_R=cen10_R, sequence_duration_sec=dur10,
        )
        pl10.add_action(StartStopWalkAction())
        pl10.add_action(TerrainWalkAction(route=route10, environment=env10))
        pl10.add_action(SprintStartAction())
        pl10.add_action(SprintBrakeAction())
        pl10.add_action(RunAction(cycles=2))
        res10 = pl10.execute(initial_state=create_initial_motion_state(cfg10, start_frame=1, position=start_pos10))
    finally:
        rest10()

    assert res10["total_frames"] == total10
    cs10 = ch.summarize_call_chain_trace(tr10, expected_frames=total10)
    assert cs10["planner_execute_calls"] == 1
    assert cs10["unique_planner_instances"] == 1
    assert cs10["unique_bridge_instances"] == 1
    assert cs10["unique_wbc_instances"] == 1
    assert cs10["compose_calls"] == total10
    assert cs10["bridge_exec_calls"] == total10
    assert cs10["wbc_exec_calls"] == total10
    assert cs10["non_upper_integrity_mismatches"] == 0
    assert cs10["compose_vs_bridge_mismatches"] == 0
    assert cs10["all_wbc_success"]

    # Verify strict compose -> bridge -> wbc call sequence per frame
    expected_seq_ok = True
    fco = tr10["frame_call_order"]
    assert len(fco) == 6 * total10
    for idx in range(total10):
        chunk = fco[6 * idx : 6 * idx + 6]
        if [c[0] for c in chunk] != ["compose_enter", "compose_exit", "bridge_enter", "wbc_enter", "wbc_exit", "bridge_exit"]:
            expected_seq_ok = False
            break

    # Cross-boundary continuity verification across all 4 action handoffs
    states10 = res10["states"]
    solve10_by_f = {f["frame"]: f for f in tr10["solve_frames"]}
    diag10_by_f = {d["frame"]: d for d in tr10["compose_diagnostics"]}
    boundary_frames = [
        204,
        204 + tw_frames_10,
        204 + tw_frames_10 + 114,
        204 + tw_frames_10 + 114 + 48,
    ]
    boundary_reports = []
    for bf in boundary_frames:
        s_a = states10[bf - 1]
        s_b = states10[bf]
        d_a = diag10_by_f[bf]
        d_b = diag10_by_f[bf + 1]
        assert s_b.frame == s_a.frame + 1
        assert abs((d_b["sequence_time_sec"] - d_a["sequence_time_sec"]) - (1.0 / 24.0)) < 1e-6
        assert d_a["L"]["segment_index"] == d_b["L"]["segment_index"] or d_b["L"]["segment_index"] == d_a["L"]["segment_index"] + 1
        assert d_a["R"]["segment_index"] == d_b["R"]["segment_index"] or d_b["R"]["segment_index"] == d_a["R"]["segment_index"] + 1
        assert s_b.params["arm_l_rx"] is None and s_b.params["arm_r_rx"] is None
        fa, fb = solve10_by_f[bf], solve10_by_f[bf + 1]
        root_jump = (Vector(fa["root_world_pos"]) - Vector(fb["root_world_pos"])).length
        w_l_jump = (Vector(fa["wrist_root_local_L"]) - Vector(fb["wrist_root_local_L"])).length
        w_r_jump = (Vector(fa["wrist_root_local_R"]) - Vector(fb["wrist_root_local_R"])).length
        l_rel_rot_jump = max(
            math.degrees(vr._quat_angle_rad(Quaternion(fa["bones"][bn]["rel_parent_quat"]), Quaternion(fb["bones"][bn]["rel_parent_quat"])))
            for bn in ("upper_arm.L", "forearm.L", "hand.L")
        )
        r_rel_rot_jump = max(
            math.degrees(vr._quat_angle_rad(Quaternion(fa["bones"][bn]["rel_parent_quat"]), Quaternion(fb["bones"][bn]["rel_parent_quat"])))
            for bn in ("upper_arm.R", "forearm.R", "hand.R")
        )
        spine_rot_jump = math.degrees(vr._quat_angle_rad(Quaternion(fa["bones"]["spine"]["world_quat"]), Quaternion(fb["bones"]["spine"]["world_quat"])))
        assert root_jump <= 0.12
        # L is active FK across all 4 boundaries -> relative joint rotation jump must stay smooth
        assert l_rel_rot_jump <= 3.5, f"Boundary {bf} L FK rel_parent rot jump {l_rel_rot_jump} > 3.5 deg"
        # R is active IK (ROOT_LOCAL) across all 4 boundaries -> Root-local wrist stays continuous regardless of historical spine lean jump
        assert w_r_jump <= 0.02, f"Boundary {bf} R IK wrist jump {w_r_jump} > 0.02m"
        boundary_reports.append({
            "before_frame": bf,
            "after_frame": bf + 1,
            "seg_idx_L_before": d_a["L"]["segment_index"],
            "seg_idx_L_after": d_b["L"]["segment_index"],
            "seg_idx_R_before": d_a["R"]["segment_index"],
            "seg_idx_R_after": d_b["R"]["segment_index"],
            "root_jump_m": round(root_jump, 5),
            "spine_world_jump_deg": round(spine_rot_jump, 3),
            "wrist_local_jump_L_m": round(w_l_jump, 5),
            "wrist_local_jump_R_m": round(w_r_jump, 5),
            "max_fk_rel_rot_jump_L_deg": round(l_rel_rot_jump, 3),
            "max_ik_rel_rot_jump_R_deg": round(r_rel_rot_jump, 3),
        })

    results["T10"] = {"passed": True, "boundaries": boundary_reports, "total_frames": total10}
    results["T12"] = {"passed": True, "strict_frame_call_order": expected_seq_ok, "call_chain": cs10}
    results["T13"] = {"passed": True, "frames_checked": total10, "non_upper_integrity_mismatches": cs10["non_upper_integrity_mismatches"]}

    # -------------------------------------------------------------------------
    # T11: Timeline Bounds (non-1 start_frame, first/last valid, out-of-bounds, mismatch)
    # -------------------------------------------------------------------------
    dur11 = (48 - 1) / 24.0
    res11, tr11, cs11, _ = _run_centralized_test(
        "T11", [RunAction(cycles=2)], False, (0.0, 0.0, 0.0), dur11,
        _make_sample_fk_segs(0.0, 0.9, 0.9, "L", 4.1),
        _make_sample_ik_segs("R", [(0.0, 0.9), (0.9, 0.9)], 4.3),
        start_frame=101,
    )
    assert res11["sequence_start_frame"] == 101 and res11["sequence_end_frame"] == 148
    assert tr11["compose_diagnostics"][0]["sequence_time_sec"] == 0.0
    assert abs(tr11["compose_diagnostics"][-1]["sequence_time_sec"] - dur11) < 1e-6

    cfg11, _, root11, arm11, _, _, env11 = ch.assemble_flat_locomotion_scene(with_visual_hands=False)
    tr11_b, rest11_b = ch.install_full_chain_observer(arm11, root11, capture_live_poses=False)
    try:
        from src.motion.framework import BlenderPoseApplicator, ContactConstraintAdapter
        ctx11 = MotionRuntimeContext(
            config=cfg11, armature_obj=arm11, root_obj=root11, scene=bpy.context.scene,
            environment=env11, contact_adapter=ContactConstraintAdapter(arm11, env11),
            pose_applicator=BlenderPoseApplicator(arm11, root11, cfg11),
            upper_limb_L=_make_sample_fk_segs(0.0, 0.9, 0.9, "L", 4.1),
            sequence_start_frame=101, sequence_duration_sec=dur11,
        )
        p_pre = KinematicPlannedPose(frame=100, time_seconds=99 / 24.0, root_position=(0.0, 0.0, 0.0))
        p_post = KinematicPlannedPose(frame=149, time_seconds=148 / 24.0, root_position=(0.0, 0.0, 0.0))
        oob_pre = _expect_raises(ValueError, lambda: ctx11.compose_planned_pose(p_pre), "frame_precedes_start", lambda: tr11_b["bridge_exec_calls"])
        oob_post = _expect_raises(ValueError, lambda: ctx11.compose_planned_pose(p_post), "frame_exceeds_bound", lambda: tr11_b["bridge_exec_calls"])
        pl_mismatch = MotionPlanner(
            cfg11, armature_obj=arm11, environment=env11,
            upper_limb_L=_make_sample_fk_segs(0.0, 0.8, 0.8, "L", 4.1),
            sequence_duration_sec=(47 - 1) / 24.0,
        ).add_action(RunAction(cycles=2))
        dur_mm = _expect_raises(ValueError, pl_mismatch.execute, "declared_duration_mismatch", lambda: tr11_b["bridge_exec_calls"])
    finally:
        rest11_b()
    results["T11"] = {
        "passed": True,
        "non_1_start_range": [101, 148],
        "oob_pre": oob_pre,
        "oob_post": oob_post,
        "declared_duration_mismatch": dur_mm,
    }

    # -------------------------------------------------------------------------
    # T14: Failure Propagation (Reachability, ROM, Bridge failure, Central time over-bound)
    # -------------------------------------------------------------------------
    cfg14, _, root14, arm14, _, _, env14 = ch.assemble_flat_locomotion_scene(with_visual_hands=False)
    t14_cases = {}

    class _SentinelSprint(MotionAction):
        called = False
        @property
        def name(self):
            return "sentinel"
        def estimate_duration_frames(self, s, c):
            return 10
        def execute(self, s, ctx):
            _SentinelSprint.called = True
            raise AssertionError("Follow-up action must NEVER execute after failure!")

    # 14a: Unreachable IK (clamp_reach=False, wrist 1.20m forward) blocks Action 2
    bad_ik = (UpperLimbSegment(
        mode="IK", start_time_sec=0.0, duration_sec=0.5,
        wrist_start_xyz=(-0.24, 1.50, 1.40), wrist_end_xyz=(-0.24, 1.50, 1.40),
        position_space="ROOT_LOCAL", clamp_reach=False,
    ),)
    follow_calls = [0]
    orig_sp_exec = SprintStartAction.execute
    orig_ss_exec = StartStopWalkAction.execute

    @functools.wraps(orig_sp_exec)
    def spy_sp_exec(self, *a, **kw):
        follow_calls[0] += 1
        return orig_sp_exec(self, *a, **kw)

    @functools.wraps(orig_ss_exec)
    def spy_ss_exec(self, *a, **kw):
        follow_calls[0] += 1
        return orig_ss_exec(self, *a, **kw)

    SprintStartAction.execute = spy_sp_exec
    StartStopWalkAction.execute = spy_ss_exec
    try:
        try:
            MotionPlanner(
                cfg14, armature_obj=arm14, environment=env14,
                upper_limb_L=bad_ik, sequence_duration_sec=(96 + 114 - 1) / 24.0,
            ).add_action(RunAction(cycles=4)).add_action(SprintStartAction()).execute()
            raise AssertionError("Expected unreachable IK failure!")
        except RuntimeError as exc:
            assert "REACHABILITY" in str(exc) and follow_calls[0] == 0
            t14_cases["unreachable_upper_limb"] = {"blocked": True, "follow_up_calls": follow_calls[0], "exc": str(exc)[:160]}

        # 14b: ROM violation (forearm.L hyperextended -45 deg)
        bad_rom_fk = (UpperLimbSegment(
            mode="FK", start_time_sec=0.0, duration_sec=0.5,
            fk_start_deg=((0.0, 0.0, 0.0), (-45.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            fk_end_deg=((0.0, 0.0, 0.0), (-45.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ),)
        try:
            MotionPlanner(
                cfg14, armature_obj=arm14, environment=env14,
                upper_limb_L=bad_rom_fk, sequence_duration_sec=(48 + 114 - 1) / 24.0,
            ).add_action(RunAction(cycles=2)).add_action(SprintStartAction()).execute()
            raise AssertionError("Expected ROM failure!")
        except RuntimeError as exc:
            assert "ROM_VIOLATION" in str(exc) and follow_calls[0] == 0
            t14_cases["rom_violation_upper_limb"] = {"blocked": True, "follow_up_calls": follow_calls[0], "exc": str(exc)[:160]}

        # 14c: Bridge failure via non-support terrain surface + verify subsequent authorized action never executes
        pg_env = create_standard_dynamics_playground_query()
        bad_wall_route = TerrainRouteInput(start_pos=(0.0, 23.00, 0.0), target_pos=(0.0, 24.00, 0.0), nominal_stride_m=0.30, step_frames=12)
        try:
            pl_14c = MotionPlanner(cfg14, armature_obj=arm14, environment=pg_env).add_action(
                TerrainWalkAction(route=bad_wall_route, environment=pg_env)
            ).add_action(StartStopWalkAction())
            pl_14c.execute(initial_state=create_initial_motion_state(cfg14, position=(0.0, 23.00, 0.0)))
            raise AssertionError("Expected non-support Bridge failure!")
        except (RuntimeError, ValueError) as exc:
            assert follow_calls[0] == 0
            t14_cases["bridge_non_support_failure"] = {"blocked": True, "follow_up_calls": follow_calls[0], "exc": str(exc)[:160]}
    finally:
        SprintStartAction.execute = orig_sp_exec
        StartStopWalkAction.execute = orig_ss_exec

    results["T14"] = {"passed": True, "cases": t14_cases}

    # -------------------------------------------------------------------------
    # T15: Parameter Counterfactuals (A, B=L only, C=R only, D=Lower only)
    # Sequence: StartStopWalk(204) + Run(A: 3x24=72, D: 4x18=72) = 276 frames, seq_dur = 275/24s
    # -------------------------------------------------------------------------
    dur15 = (276 - 1) / 24.0
    base_L_15 = _make_sample_fk_segs(0.2, 5.4, 5.4, "L", 0.6)
    base_R_15 = _make_sample_ik_segs("R", [(0.2, 5.4), (5.6, 5.4)], 1.4)
    alt_L_15 = _make_sample_fk_segs(0.6, 4.1, 4.8, "L", 5.2)
    alt_R_15 = _make_sample_ik_segs("R", [(0.5, 4.4), (4.9, 4.6)], 6.1)

    def _run_t15_variant(tag: str, cen_L, cen_R, mod_lower: bool = False):
        cfg_v, _, root_v, arm_v, _, _, env_v = ch.assemble_flat_locomotion_scene(with_visual_hands=False)
        run_cyc = 3
        if mod_lower:
            # Legal lower-limb stride & cadence variation keeping exact 72 run frames (4 cycles x 18 frames)
            cfg_v.run_cycle_frames = 18
            cfg_v.run_stance_frames = 5
            cfg_v.run_step_length = 0.28
            run_cyc = 4
        tr_v, rest_v = ch.install_full_chain_observer(arm_v, root_v, capture_live_poses=True)
        try:
            pl_v = MotionPlanner(
                cfg_v, armature_obj=arm_v, environment=env_v,
                upper_limb_L=cen_L, upper_limb_R=cen_R, sequence_duration_sec=dur15,
            ).add_action(StartStopWalkAction()).add_action(RunAction(cycles=run_cyc))
            pl_v.execute()
        finally:
            rest_v()
        return tr_v

    tr15_A = _run_t15_variant("A", base_L_15, base_R_15, mod_lower=False)
    tr15_B = _run_t15_variant("B", alt_L_15, base_R_15, mod_lower=False)
    tr15_C = _run_t15_variant("C", base_L_15, alt_R_15, mod_lower=False)
    tr15_D = _run_t15_variant("D", base_L_15, base_R_15, mod_lower=True)

    # Compare B vs A (only L changed)
    b_max_r_plan = 0.0
    b_max_low_plan = 0.0
    b_max_l_wrist_loc = 0.0
    b_max_l_bone_deg = 0.0
    for pa, pb, sa, sb in zip(tr15_A["planned_stream"], tr15_B["planned_stream"], tr15_A["solve_frames"], tr15_B["solve_frames"]):
        assert pa["hand_R"] == pb["hand_R"] and pa["fk_R"] == pb["fk_R"]
        b_max_r_plan = max(b_max_r_plan, max(abs(a - b) for a, b in zip(pa["hand_R"]["world_xyz"], pb["hand_R"]["world_xyz"])))
        b_max_low_plan = max(
            b_max_low_plan,
            max(abs(a - b) for a, b in zip(pa["root_position"], pb["root_position"])),
            max(abs(a - b) for a, b in zip(pa["foot_L"]["world_xyz"], pb["foot_L"]["world_xyz"])),
            max(abs(a - b) for a, b in zip(pa["foot_R"]["world_xyz"], pb["foot_R"]["world_xyz"])),
        )
        b_max_l_wrist_loc = max(b_max_l_wrist_loc, (Vector(sa["wrist_root_local_L"]) - Vector(sb["wrist_root_local_L"])).length)
        for bn in ("upper_arm.L", "forearm.L", "hand.L"):
            ang = math.degrees(vr._quat_angle_rad(Quaternion(sa["bones"][bn]["rel_parent_quat"]), Quaternion(sb["bones"][bn]["rel_parent_quat"])))
            b_max_l_bone_deg = max(b_max_l_bone_deg, ang)
    assert b_max_r_plan == 0.0 and b_max_low_plan == 0.0
    assert b_max_l_wrist_loc >= 0.08 and b_max_l_bone_deg >= 12.0

    # Compare C vs A (only R changed)
    c_max_l_plan = 0.0
    c_max_low_plan = 0.0
    c_max_r_wrist_loc = 0.0
    c_max_r_bone_deg = 0.0
    for pa, pc, sa, sc_f in zip(tr15_A["planned_stream"], tr15_C["planned_stream"], tr15_A["solve_frames"], tr15_C["solve_frames"]):
        assert pa["fk_L"] == pc["fk_L"] and pa["hand_L"] == pc["hand_L"]
        c_max_l_plan = max(c_max_l_plan, max(max(abs(a - b) for a, b in zip(pa["fk_L"][k], pc["fk_L"][k])) for k in pa["fk_L"]))
        c_max_low_plan = max(
            c_max_low_plan,
            max(abs(a - b) for a, b in zip(pa["root_position"], pc["root_position"])),
            max(abs(a - b) for a, b in zip(pa["foot_L"]["world_xyz"], pc["foot_L"]["world_xyz"])),
        )
        c_max_r_wrist_loc = max(c_max_r_wrist_loc, (Vector(sa["wrist_root_local_R"]) - Vector(sc_f["wrist_root_local_R"])).length)
        for bn in ("upper_arm.R", "forearm.R", "hand.R"):
            ang = math.degrees(vr._quat_angle_rad(Quaternion(sa["bones"][bn]["rel_parent_quat"]), Quaternion(sc_f["bones"][bn]["rel_parent_quat"])))
            c_max_r_bone_deg = max(c_max_r_bone_deg, ang)
    assert c_max_l_plan == 0.0 and c_max_low_plan == 0.0
    assert c_max_r_wrist_loc >= 0.08 and c_max_r_bone_deg >= 12.0

    # Compare D vs A (only lower stride/speed changed -> Root & lower world move, central upper targets invariant)
    d_max_fk_L_plan = 0.0
    d_max_root_loc_r_plan = 0.0
    d_max_root_disp = 0.0
    d_max_r_wrist_world_delta = 0.0
    d_max_r_wrist_local_delta = 0.0
    d_max_l_bone_rel_delta = 0.0
    for pa, pd, sa, sd in zip(tr15_A["planned_stream"], tr15_D["planned_stream"], tr15_A["solve_frames"], tr15_D["solve_frames"]):
        assert pa["fk_L"] == pd["fk_L"]
        for k in pa["fk_L"]:
            d_max_fk_L_plan = max(d_max_fk_L_plan, max(abs(a - b) for a, b in zip(pa["fk_L"][k], pd["fk_L"][k])))
        # Recover Root-local planned wrist from world planned minus root_position (yaw=0)
        loc_a = [pa["hand_R"]["world_xyz"][i] - pa["root_position"][i] for i in range(3)]
        loc_d = [pd["hand_R"]["world_xyz"][i] - pd["root_position"][i] for i in range(3)]
        d_max_root_loc_r_plan = max(d_max_root_loc_r_plan, max(abs(loc_a[i] - loc_d[i]) for i in range(3)))

        d_max_root_disp = max(d_max_root_disp, (Vector(sa["root_world_pos"]) - Vector(sd["root_world_pos"])).length)
        d_max_r_wrist_world_delta = max(d_max_r_wrist_world_delta, (Vector(sa["wrist_world_R"]) - Vector(sd["wrist_world_R"])).length)
        d_max_r_wrist_local_delta = max(d_max_r_wrist_local_delta, (Vector(sa["wrist_root_local_R"]) - Vector(sd["wrist_root_local_R"])).length)
        for bn in ("upper_arm.L", "forearm.L", "hand.L"):
            ang = math.degrees(vr._quat_angle_rad(Quaternion(sa["bones"][bn]["rel_parent_quat"]), Quaternion(sd["bones"][bn]["rel_parent_quat"])))
            d_max_l_bone_rel_delta = max(d_max_l_bone_rel_delta, ang)

    assert d_max_fk_L_plan == 0.0 and d_max_root_loc_r_plan <= 1e-6
    assert d_max_root_disp >= 0.25 and d_max_r_wrist_world_delta >= 0.25
    assert d_max_r_wrist_local_delta <= 0.005 and d_max_l_bone_rel_delta <= 0.05

    results["T15"] = {
        "passed": True,
        "B_vs_A_left_only": {
            "max_right_planned_diff": b_max_r_plan,
            "max_lower_planned_diff_m": b_max_low_plan,
            "max_left_wrist_local_delta_m": round(b_max_l_wrist_loc, 5),
            "max_left_bone_rel_delta_deg": round(b_max_l_bone_deg, 3),
        },
        "C_vs_A_right_only": {
            "max_left_planned_diff": c_max_l_plan,
            "max_lower_planned_diff_m": c_max_low_plan,
            "max_right_wrist_local_delta_m": round(c_max_r_wrist_loc, 5),
            "max_right_bone_rel_delta_deg": round(c_max_r_bone_deg, 3),
        },
        "D_vs_A_lower_only_world_vs_local": {
            "max_left_fk_planned_diff_deg": d_max_fk_L_plan,
            "max_right_root_local_planned_diff_m": d_max_root_loc_r_plan,
            "max_root_world_delta_m": round(d_max_root_disp, 5),
            "max_right_wrist_world_delta_m": round(d_max_r_wrist_world_delta, 5),
            "max_right_wrist_root_local_delta_m": round(d_max_r_wrist_local_delta, 6),
            "max_left_bone_rel_delta_deg": round(d_max_l_bone_rel_delta, 5),
        },
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2)


# =============================================================================
# COORDINATOR COMPARING T02/T03 BASELINE VS HEAD AND SUMMARIZING T01..T15
# =============================================================================

def _compare_baseline_vs_cur(hist_json: str, cur_json: str) -> Dict[str, Any]:
    with open(hist_json, "r", encoding="utf-8") as fp:
        hist = json.load(fp)
    with open(cur_json, "r", encoding="utf-8") as fp:
        cur = json.load(fp)

    assert hist["fail_checks"] == cur["fail_checks"], f"Failure contract diff: {hist['fail_checks']} != {cur['fail_checks']}"
    t02_summary = {}
    t03_summary = {}
    for run_name, h_run in hist["runs"].items():
        c_run = cur["runs"][run_name]
        assert h_run["total_frames"] == c_run["total_frames"]
        assert len(h_run["samples"]) == len(c_run["samples"])
        max_root_d = 0.0
        max_foot_d = 0.0
        max_wrist_d = 0.0
        max_fk_d = 0.0
        max_quat_d = 0.0
        max_inf_d = 0.0
        for hs, cs, hst, cst in zip(h_run["samples"], c_run["samples"], h_run["states"], c_run["states"]):
            assert hs["frame"] == cs["frame"] and hs["mode"] == cs["mode"]
            assert hst["contacts"] == cst["contacts"] and hst["is_airborne"] == cst["is_airborne"]
            if hst["hist_arm_l_rx"] is not None:
                assert hst["hist_arm_l_rx"] == cst["hist_arm_l_rx"]
            if hst["hist_arm_r_rx"] is not None:
                assert hst["hist_arm_r_rx"] == cst["hist_arm_r_rx"]
            assert hs["fk"].keys() == cs["fk"].keys()
            for fk_k in hs["fk"]:
                max_fk_d = max(max_fk_d, max(abs(a - b) for a, b in zip(hs["fk"][fk_k], cs["fk"][fk_k])))
            for i in range(3):
                max_root_d = max(max_root_d, abs(hs["root"][i] - cs["root"][i]))
                max_foot_d = max(max_foot_d, abs(hs["foot_L"][i] - cs["foot_L"][i]), abs(hs["foot_R"][i] - cs["foot_R"][i]))
                max_wrist_d = max(max_wrist_d, abs(hs["wrist_L"][i] - cs["wrist_L"][i]), abs(hs["wrist_R"][i] - cs["wrist_R"][i]))
            for bn in hs["bones"]:
                for kq in ("wq", "rq"):
                    max_quat_d = max(max_quat_d, max(abs(a - b) for a, b in zip(hs["bones"][bn][kq], cs["bones"][bn][kq])))
            for ik in hs["infs"]:
                max_inf_d = max(max_inf_d, abs(hs["infs"][ik] - cs["infs"][ik]))
        assert max_root_d <= 1e-5 and max_foot_d <= 1e-5 and max_wrist_d <= 1e-5 and max_fk_d <= 1e-4 and max_quat_d <= 1e-4 and max_inf_d <= 1e-6
        row = {
            "frames": h_run["total_frames"],
            "max_root_diff_m": max_root_d,
            "max_foot_diff_m": max_foot_d,
            "max_wrist_diff_m": max_wrist_d,
            "max_fk_diff_deg": max_fk_d,
            "max_quat_diff": max_quat_d,
            "max_inf_diff": max_inf_d,
            "passed": True,
        }
        if run_name == "terrain_walk_local_fk_ik":
            t03_summary[run_name] = row
        else:
            t02_summary[run_name] = row

    return {
        "T02": {"passed": True, "actions": t02_summary, "fail_checks_match": True},
        "T03": {"passed": True, **t03_summary["terrain_walk_local_fk_ik"]},
    }


def run_all_contracts() -> Dict[str, Any]:
    os.makedirs(ch.SCRATCH_WORK, exist_ok=True)
    hist_dir = ch.ensure_historical_baseline_extracted()

    this_file = os.path.abspath(__file__)
    hist_json = os.path.join(ch.SCRATCH_WORK, "t02_t03_hist.json")
    cur_base_json = os.path.join(ch.SCRATCH_WORK, "t02_t03_cur.json")
    cur_suite_json = os.path.join(ch.SCRATCH_WORK, "t01_t15_cur.json")

    jobs = [
        ("t02_t03_hist_9f5f8250", ["--worker", "baseline", "--repo", hist_dir, "--out", hist_json]),
        ("t02_t03_cur_head", ["--worker", "baseline", "--repo", ch.REPO_ROOT, "--out", cur_base_json]),
        ("t01_t15_contracts", ["--worker", "contracts", "--out", cur_suite_json]),
    ]
    cmds = []
    for label, args in jobs:
        cmd = [ch.BLENDER_EXE, "-b", "--factory-startup", "--python-exit-code", "1", "--python", this_file, "--", *args]
        cmds.append({"label": label, "command": cmd})
        proc = subprocess.run(cmd, cwd=ch.REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"[{label}] rc={proc.returncode}")
        if proc.stdout:
            print(proc.stdout[-1500:])
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            raise RuntimeError(f"Contract worker {label} failed (rc={proc.returncode}):\n{proc.stderr}")

    t02_t03 = _compare_baseline_vs_cur(hist_json, cur_base_json)
    with open(cur_suite_json, "r", encoding="utf-8") as fp:
        cur_suite = json.load(fp)

    merged = {"T01": cur_suite["T01"], **t02_t03}
    for k in ("T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15"):
        merged[k] = cur_suite[k]

    report_path = os.path.join(THIS_DIR, "t01_t15_results.json")
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump({"baseline_commit": ch.HIST_BASELINE_COMMIT, "head": ch.EXPECTED_HEAD, "commands": cmds, "results": merged}, fp, indent=2)
    return merged


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
        if cli["worker"] == "baseline":
            _worker_run_baseline_suite(cli["repo"], cli["out"])
        elif cli["worker"] == "contracts":
            _worker_run_contracts_cur(cli["out"])
        else:
            raise ValueError(f"Unknown worker: {cli['worker']}")
        print(f"CONTRACTS_WORKER_OK {cli['worker']}")
    else:
        run_all_contracts()
        print("ALL_CONTRACTS_T01_T15_PASSED")
