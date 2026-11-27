"""TASK 12-D Section 10: Continuous Production Chain Verification.

Executes all 5 production MotionActions via MotionPlanner -> KinematicBridgeExecutor ->
WholeBodyController -> Rig -> MotionState, including bilateral independent upper-limb
FK/IK mode combinations, lock/unlock transitions, action handoffs, unequal dt, failure stop
& retry, and reset + re-execute.

Run via real Blender 5.1.1:
    "C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe" -b -P docs/evidence/12/unified_verification/verify_continuous_motion.py
"""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
import traceback
from typing import Any, Dict, List
from unittest.mock import patch

import bpy
from mathutils import Vector

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import src.motion.whole_body_controller as wbc_mod
from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    EnvironmentQuery,
    MotionMode,
    MotionPlanner,
    StartStopWalkAction,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
    PlannedHandTarget,
)
from src.motion.run_cycle import RunAction
from src.motion.sprint_brake import SprintBrakeAction
from src.motion.sprint_start import SprintStartAction
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.upper_limb_trajectory import UpperLimbSegment
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, HIP_X_OFFSET, setup_leg_ik
from src.rig.pose import reset_pose

OUTPUT_JSON = os.path.join(THIS_DIR, "continuous_results.json")


def _clean_scene() -> tuple[PipelineConfig, bpy.types.Object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    build_character(cfg)
    arm = build_rig(cfg)
    bind_character_to_rig(arm)
    reset_pose(arm)
    setup_leg_ik(arm)
    setup_arm_ik(arm, initial_influence=0.0)
    bpy.context.view_layer.update()
    return cfg, arm


def main() -> int:
    report: Dict[str, Any] = {}
    all_ok = True
    try:
        # 1. Central bilateral FK/FK, FK/IK, IK/FK, IK/IK across chained StartStopWalk + TerrainWalk
        cfg, arm = _clean_scene()
        env = EnvironmentQuery(ground_z=0.0)
        start_ss = StartStopWalkAction()
        start_state = create_initial_motion_state(cfg, start_frame=1)
        ss_dur = start_ss.estimate_duration_frames(start_state, cfg)
        ss_end_y = start_state.position[1] + 1.26

        tw_action = TerrainWalkAction(
            route=TerrainRouteInput(start_pos=(0.0, ss_end_y, 0.0), target_pos=(0.0, ss_end_y + 0.90, 0.0), nominal_stride_m=0.35),
            environment=env,
        )
        tw_entry_state = start_state.clone_with(frame=ss_dur, position=(0.0, ss_end_y, 0.0))
        tw_dur = tw_action.estimate_duration_frames(tw_entry_state, cfg, environment=env)
        total_sec = (ss_dur + tw_dur - 1) / float(cfg.fps)

        # Cover all 4 modes across sequence timeline:
        # [0..t1): FK/FK, [t1..t2): IK/FK, [t2..t3): FK/IK, [t3..total_sec]: IK/IK
        t1 = (ss_dur * 0.25) / float(cfg.fps)
        t2 = (ss_dur * 0.65) / float(cfg.fps)
        t3 = (ss_dur + tw_dur * 0.35) / float(cfg.fps)
        upper_l = (
            UpperLimbSegment(
                mode="FK",
                start_time_sec=0.0,
                duration_sec=t1,
                fk_start_deg=((8.0, 0.0, 4.0), (15.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                fk_end_deg=((12.0, 0.0, 4.0), (18.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ),
            UpperLimbSegment(
                mode="IK",
                start_time_sec=t1,
                duration_sec=t2 - t1,
                wrist_start_xyz=(-0.25, 0.25, 1.22),
                wrist_end_xyz=(-0.25, 0.30, 1.24),
                position_space="ROOT_LOCAL",
            ),
            UpperLimbSegment(
                mode="FK",
                start_time_sec=t2,
                duration_sec=t3 - t2,
                fk_start_deg=((12.0, 0.0, 4.0), (18.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                fk_end_deg=((16.0, 0.0, 4.0), (20.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ),
            UpperLimbSegment(
                mode="IK",
                start_time_sec=t3,
                duration_sec=total_sec - t3,
                wrist_start_xyz=(-0.25, 0.25, 1.22),
                wrist_end_xyz=(-0.25, 0.28, 1.24),
                position_space="ROOT_LOCAL",
            ),
        )
        upper_r = (
            UpperLimbSegment(
                mode="FK",
                start_time_sec=0.0,
                duration_sec=t1,
                fk_start_deg=((8.0, 0.0, -4.0), (15.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                fk_end_deg=((10.0, 0.0, -4.0), (16.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ),
            UpperLimbSegment(
                mode="FK",
                start_time_sec=t1,
                duration_sec=t2 - t1,
                fk_start_deg=((10.0, 0.0, -4.0), (16.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
                fk_end_deg=((14.0, 0.0, -4.0), (18.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            ),
            UpperLimbSegment(
                mode="IK",
                start_time_sec=t2,
                duration_sec=t3 - t2,
                wrist_start_xyz=(0.25, 0.25, 1.22),
                wrist_end_xyz=(0.25, 0.30, 1.24),
                position_space="ROOT_LOCAL",
            ),
            UpperLimbSegment(
                mode="IK",
                start_time_sec=t3,
                duration_sec=total_sec - t3,
                wrist_start_xyz=(0.25, 0.30, 1.24),
                wrist_end_xyz=(0.25, 0.28, 1.24),
                position_space="ROOT_LOCAL",
            ),
        )

        counts = {"bridge_calls": 0, "wbc_calls": 0, "com_calls": 0}
        orig_com = wbc_mod.compute_whole_body_com
        orig_bridge = KinematicBridgeExecutor.execute_frame

        def spy_com(*a, **kw):
            counts["com_calls"] += 1
            return orig_com(*a, **kw)

        def spy_bridge(self_b, planned, *a, **kw):
            counts["bridge_calls"] += 1
            return orig_bridge(self_b, planned, *a, **kw)

        planner = MotionPlanner(cfg, armature_obj=arm, environment=env, sequence_duration_sec=total_sec, upper_limb_L=upper_l, upper_limb_R=upper_r)
        planner.add_action(start_ss)
        planner.add_action(tw_action)
        WholeBodyControllerCls = wbc_mod.WholeBodyController
        orig_wbc = WholeBodyControllerCls.execute_frame

        def spy_wbc(self_w, *a, **kw):
            counts["wbc_calls"] += 1
            return orig_wbc(self_w, *a, **kw)

        with patch.object(wbc_mod, "compute_whole_body_com", side_effect=spy_com), patch.object(
            KinematicBridgeExecutor, "execute_frame", autospec=True, side_effect=spy_bridge
        ), patch.object(WholeBodyControllerCls, "execute_frame", autospec=True, side_effect=spy_wbc):
            chain_res = planner.execute(initial_state=start_state)

        states = chain_res["states"]
        n_frames = len(states)
        assert n_frames == ss_dur + tw_dur
        assert counts["bridge_calls"] == n_frames and counts["wbc_calls"] == n_frames and counts["com_calls"] == n_frames, (
            f"Call count mismatch: {counts} vs {n_frames}"
        )
        # Verify action boundary handoff continuity + all 4 FK/IK combinations exercised
        ar_l = chain_res["action_results"][0]
        ar_r = chain_res["action_results"][1]
        assert ar_r.initial_state.frame == ar_l.final_state.frame + 1
        assert math.dist(ar_r.initial_state.position, ar_l.final_state.position) < 1e-4
        modes_seen = {
            (s.params["planned_upper_limb"]["L"]["mode"], s.params["planned_upper_limb"]["R"]["mode"])
            for s in states
        }
        assert modes_seen == {("FK", "FK"), ("IK", "FK"), ("FK", "IK"), ("IK", "IK")}, f"Modes seen: {modes_seen}"

        # Lock/unlock transitions seen in foot contacts
        foot_l_locks = [s.contacts["foot_L"].is_locked for s in states]
        transitions = sum(1 for i in range(1, len(foot_l_locks)) if foot_l_locks[i] != foot_l_locks[i - 1])
        assert transitions >= 2, f"Expected lock/unlock transitions on foot_L, got {transitions}"

        report["chained_walk_plus_terrain"] = {
            "frames": n_frames,
            "counts": counts,
            "modes_seen": sorted([list(m) for m in modes_seen]),
            "foot_L_lock_transitions": transitions,
        }

        # 2. Chained Run -> SprintStart -> SprintBrake production actions
        cfg, arm = _clean_scene()
        p_run = MotionPlanner(cfg, armature_obj=arm)
        p_run.add_action(RunAction(cycles=1))
        r_run = p_run.execute()

        cfg, arm = _clean_scene()
        p_sp = MotionPlanner(cfg, armature_obj=arm)
        p_sp.add_action(SprintStartAction())
        p_sp.add_action(SprintBrakeAction())
        r_sp = p_sp.execute()

        report["run_and_sprint_chain"] = {
            "run_frames": len(r_run["states"]),
            "sprint_chain_frames": len(r_sp["states"]),
            "sprint_boundary_pos_diff_m": round(
                math.dist(r_sp["action_results"][0].final_state.position, r_sp["action_results"][1].initial_state.position),
                8,
            ),
        }

        # 3. Reset + Re-execute + unequal dt + failed frame retry
        cfg, arm = _clean_scene()
        bridge = KinematicBridgeExecutor(armature_obj=arm)
        assert bridge.execute_frame(
            KinematicPlannedPose(1, 0.0, (0.0, -8.0, 0.0), foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True), foot_R=PlannedFootTarget((HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True)),
            keyframe=False,
        ).success
        bridge.reset()
        bridge.controller.reset_all_controls()
        assert bridge._last_frame is None and len(bridge.kinematics_tracker._history) == 0

        # Unequal dt execution (0.02s -> fail -> retry -> 0.06s)
        assert bridge.execute_frame(
            KinematicPlannedPose(1, 0.0, (0.0, -8.0, 0.0), pelvis_location=(0.0, -0.02, 0.0), dt=0.02, foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True), foot_R=PlannedFootTarget((HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True)),
            keyframe=False,
        ).success
        assert bridge.execute_frame(
            KinematicPlannedPose(2, 0.06, (0.0, -7.98, 0.0), pelvis_location=(0.0, -0.02, 0.0), spine_rotation_deg=(85.0, 0.0, 0.0), foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True), foot_R=PlannedFootTarget((HIP_X_OFFSET, -7.98, ANKLE_REST_Z), False)),
            keyframe=False,
        ).success is False
        r_retry = bridge.execute_frame(
            KinematicPlannedPose(2, 0.06, (0.0, -7.98, 0.0), pelvis_location=(0.0, -0.02, 0.0), foot_L=PlannedFootTarget((-HIP_X_OFFSET, -8.0, ANKLE_REST_Z), True), foot_R=PlannedFootTarget((HIP_X_OFFSET, -7.98, ANKLE_REST_Z), False)),
            keyframe=False,
        )
        assert r_retry.success and math.isclose(r_retry.motion_state.params["dt_seconds"], 0.06, abs_tol=1e-7)
        report["reset_unequal_dt_retry"] = {
            "reset_clean": True,
            "retried_dt_sec": round(r_retry.motion_state.params["dt_seconds"], 6),
        }

        print(f"[PASS] Continuous Production Chain: {report}")
    except Exception as exc:
        all_ok = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        print(f"[FAIL] Continuous Production Chain: {exc}", file=sys.stderr)
        traceback.print_exc()

    payload = {
        "group": "Section 10 — Continuous Production Chain Verification",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "passed": all_ok,
        "report": report,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
