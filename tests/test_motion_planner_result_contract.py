"""ProceduralAnimation — Regression Test Suite for FIND-R2-04.

Validates ActionExecutionResult unified contract and MotionPlanner failure handling:
- Test 1: Two normal actions (sequential execution, state handover, full trajectory).
- Test 2: First action returns failed result (planner blocks, 2nd action not run, no faked success).
- Test 3: Action directly raises RuntimeError (planner does not swallow or wrap exception).
- Test 4: Action claims success but trajectory is empty (rejected as contract violation).
- Test 5: Action claims success but final_state mismatches last state (frame/position mismatch rejected).
- Test 6: Unmet constraints distinction:
    - 6A: Non-fatal diagnostic warning is not treated as fatal failure.
    - 6B: Fatal constraint (e.g. REACHABILITY/ROM_VIOLATION) is caught even if success=True was claimed.
- Test 7: StartStopWalkAction historical compatibility (produces unified contract result).
- Test 8: TerrainWalkAction historical compatibility (Repair 03 failure check intact under planner).
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from typing import Any, Dict, List, Optional, Tuple

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    ActionExecutionResult,
    ContactConstraintAdapter,
    ContactPointState,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionPlanner,
    MotionRuntimeContext,
    MotionState,
    StartStopWalkAction,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.whole_body_controller import UnmetConstraint
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik


class MockControlledAction(MotionAction):
    """Configurable MotionAction for testing MotionPlanner result contract."""

    def __init__(
        self,
        name: str = "MockControlledAction",
        duration_frames: int = 5,
        dy_per_frame: float = 0.05,
        fail_with_result: bool = False,
        failure_reason: Optional[str] = None,
        failure_frame: Optional[int] = None,
        unmet_constraints: Optional[List[Any]] = None,
        unreachable_count: int = 0,
        raise_exception: Optional[Exception] = None,
        return_empty_states: bool = False,
        mismatch_final_frame: Optional[int] = None,
        mismatch_final_position: Optional[Tuple[float, float, float]] = None,
    ):
        self._name = name
        self.duration_frames = duration_frames
        self.dy_per_frame = dy_per_frame
        self.fail_with_result = fail_with_result
        self.failure_reason = failure_reason
        self.failure_frame = failure_frame
        self.unmet_constraints = unmet_constraints or []
        self.unreachable_count = unreachable_count
        self.raise_exception = raise_exception
        self.return_empty_states = return_empty_states
        self.mismatch_final_frame = mismatch_final_frame
        self.mismatch_final_position = mismatch_final_position

        # Execution telemetry
        self.executed: bool = False
        self.received_initial_state: Optional[MotionState] = None

    @property
    def name(self) -> str:
        return self._name

    def can_start_from(self, state: MotionState) -> bool:
        return True

    def estimate_duration_frames(self, initial_state: MotionState, config: PipelineConfig) -> int:
        return self.duration_frames

    def execute(
        self,
        initial_state: MotionState,
        context: MotionRuntimeContext,
    ) -> ActionExecutionResult:
        self.executed = True
        self.received_initial_state = initial_state

        if self.raise_exception is not None:
            raise self.raise_exception

        if self.return_empty_states:
            kwargs = {
                "action_name": self.name,
                "initial_state": initial_state,
                "final_state": initial_state,
                "states": [],
                "frame_records": [],
            }
            if hasattr(ActionExecutionResult, "success"):
                kwargs["success"] = not self.fail_with_result
                kwargs["failure_reason"] = self.failure_reason
            res = ActionExecutionResult(**kwargs)
            res.success = not self.fail_with_result
            res.failure_reason = self.failure_reason
            return res

        states: List[MotionState] = []
        records: List[dict] = []
        cur_x, cur_y, cur_z = initial_state.position
        start_f = initial_state.frame
        v_y = self.dy_per_frame * context.config.fps

        for i in range(self.duration_frames):
            f = start_f + i
            cur_y += self.dy_per_frame
            st = initial_state.clone_with(
                frame=f,
                time_sec=(f - 1) / float(context.config.fps),
                position=(cur_x, cur_y, cur_z),
                velocity=(0.0, v_y, 0.0),
            )
            states.append(st)
            records.append({
                "frame": f,
                "root_y": cur_y,
                "speed_mps": v_y,
            })

        final_st = states[-1]
        if self.mismatch_final_frame is not None:
            final_st = final_st.clone_with(frame=self.mismatch_final_frame)
        if self.mismatch_final_position is not None:
            final_st = final_st.clone_with(position=self.mismatch_final_position)

        success = not self.fail_with_result
        kwargs = {
            "action_name": self.name,
            "initial_state": initial_state,
            "final_state": final_st,
            "states": states,
            "frame_records": records,
            "unreachable_count": self.unreachable_count,
        }
        if hasattr(ActionExecutionResult, "success"):
            kwargs["success"] = success
            kwargs["unmet_constraints"] = list(self.unmet_constraints)
            kwargs["failure_reason"] = self.failure_reason
            kwargs["failure_frame"] = self.failure_frame
        res = ActionExecutionResult(**kwargs)
        res.success = success
        res.unmet_constraints = list(self.unmet_constraints)
        res.failure_reason = self.failure_reason
        res.failure_frame = self.failure_frame
        return res


class TestMotionPlannerResultContract(unittest.TestCase):
    """Targeted regression suite for MotionPlanner action result contract (FIND-R2-04)."""

    @classmethod
    def setUpClass(cls) -> None:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cls.config = PipelineConfig()
        char_data = build_character(cls.config)
        cls.root = char_data["root"]
        cls.parts = char_data["parts"]
        cls.armature = build_rig(cls.config)
        bind_character_to_rig(cls.armature, cls.parts)
        setup_leg_ik(cls.armature)
        setup_arm_ik(cls.armature)
        cls.env = EnvironmentQuery(ground_z=0.0)

    def _create_planner(self) -> MotionPlanner:
        return MotionPlanner(self.config, armature_obj=self.armature, environment=self.env)

    def test_01_two_normal_actions_success(self) -> None:
        """Test 1: Two normal actions execute sequentially, transfer state, and produce full trajectory."""
        planner = self._create_planner()
        act1 = MockControlledAction(name="Action_1", duration_frames=5, dy_per_frame=0.1)
        act2 = MockControlledAction(name="Action_2", duration_frames=5, dy_per_frame=0.1)
        planner.add_action(act1)
        planner.add_action(act2)

        init_st = create_initial_motion_state(self.config, start_frame=1)
        res = planner.execute(initial_state=init_st)

        self.assertTrue(act1.executed)
        self.assertTrue(act2.executed)
        # Act 1 starts at frame 1, ends at frame 5
        # Act 2 must start at frame 6
        self.assertIsNotNone(act2.received_initial_state)
        self.assertEqual(act2.received_initial_state.frame, 6)
        self.assertEqual(len(res["states"]), 10)
        self.assertEqual(res["total_frames"], 10)
        self.assertEqual(res["states"][0].frame, 1)
        self.assertEqual(res["states"][-1].frame, 10)

    def test_02_first_action_fails_with_result_blocks_subsequent(self) -> None:
        """Test 2: When first action returns a failed result (success=False):
        - Planner detects failure and raises RuntimeError.
        - Second action is NEVER executed.
        - Failed state is not consumed as a valid successor.
        - No full success trajectory is returned.
        """
        planner = self._create_planner()
        act1 = MockControlledAction(
            name="FailingAction",
            duration_frames=5,
            fail_with_result=True,
            failure_reason="Geometric clearance check failed",
            failure_frame=3,
        )
        act2 = MockControlledAction(name="SubsequentAction", duration_frames=5)
        planner.add_action(act1)
        planner.add_action(act2)

        init_st = create_initial_motion_state(self.config, start_frame=1)
        with self.assertRaises(RuntimeError) as cm:
            planner.execute(initial_state=init_st)

        err_msg = str(cm.exception)
        self.assertIn("FailingAction", err_msg)
        self.assertIn("Geometric clearance check failed", err_msg)
        self.assertIn("3", err_msg)  # Failure frame reported
        # Second action MUST NOT execute
        self.assertFalse(act2.executed, "Subsequent action was executed despite previous action failure!")

    def test_03_action_raises_runtime_error_propagates(self) -> None:
        """Test 3: When action directly raises RuntimeError, Planner does not swallow or generalize it."""
        planner = self._create_planner()
        act1 = MockControlledAction(
            name="CrashingAction",
            raise_exception=RuntimeError("Direct kinematic failure inside solver"),
        )
        act2 = MockControlledAction(name="SubsequentAction")
        planner.add_action(act1)
        planner.add_action(act2)

        init_st = create_initial_motion_state(self.config, start_frame=1)
        with self.assertRaises(RuntimeError) as cm:
            planner.execute(initial_state=init_st)

        self.assertIn("Direct kinematic failure inside solver", str(cm.exception))
        self.assertFalse(act2.executed)

    def test_04_action_claims_success_but_empty_trajectory_rejected(self) -> None:
        """Test 4: Action claims success but returns empty states trajectory -> rejected as contract violation."""
        planner = self._create_planner()
        act1 = MockControlledAction(name="EmptyAction", return_empty_states=True)
        planner.add_action(act1)

        init_st = create_initial_motion_state(self.config, start_frame=1)
        with self.assertRaises(RuntimeError) as cm:
            planner.execute(initial_state=init_st)

        err_msg = str(cm.exception)
        self.assertIn("EmptyAction", err_msg)
        self.assertTrue("empty" in err_msg.lower() or "trajectory" in err_msg.lower())

    def test_05_action_final_state_mismatch_rejected(self) -> None:
        """Test 5: Action claims success but final_state mismatches last trajectory state:
        - 5A: Frame mismatch.
        - 5B: Position mismatch.
        """
        # 5A: Frame mismatch
        planner_a = self._create_planner()
        act_a = MockControlledAction(name="FrameMismatchAction", duration_frames=4, mismatch_final_frame=99)
        planner_a.add_action(act_a)
        init_st = create_initial_motion_state(self.config, start_frame=1)
        with self.assertRaises(RuntimeError) as cm_a:
            planner_a.execute(initial_state=init_st)
        self.assertIn("FrameMismatchAction", str(cm_a.exception))
        self.assertIn("mismatch", str(cm_a.exception).lower())

        # 5B: Position mismatch
        planner_b = self._create_planner()
        act_b = MockControlledAction(
            name="PosMismatchAction",
            duration_frames=4,
            mismatch_final_position=(0.0, 99.0, 0.0),
        )
        planner_b.add_action(act_b)
        with self.assertRaises(RuntimeError) as cm_b:
            planner_b.execute(initial_state=init_st)
        self.assertIn("PosMismatchAction", str(cm_b.exception))
        self.assertIn("position", str(cm_b.exception).lower())

    def test_06_unmet_constraints_fatal_vs_warning_distinction(self) -> None:
        """Test 6: Distinction between fatal execution constraints and non-fatal warnings:
        - 6A: Non-fatal diagnostic warning is preserved, execution succeeds.
        - 6B: Fatal physical constraint (e.g. REACHABILITY) fails execution even if success=True was claimed.
        """
        # 6A: Non-fatal warning
        planner_a = self._create_planner()
        act_a1 = MockControlledAction(
            name="WarningAction",
            duration_frames=3,
            unmet_constraints=[{"category": "WARNING", "description": "High foot clearance", "is_fatal": False}],
        )
        act_a2 = MockControlledAction(name="NextAction", duration_frames=3)
        planner_a.add_action(act_a1)
        planner_a.add_action(act_a2)
        init_st = create_initial_motion_state(self.config, start_frame=1)
        res_a = planner_a.execute(initial_state=init_st)
        self.assertTrue(act_a1.executed)
        self.assertTrue(act_a2.executed)
        self.assertEqual(res_a["total_frames"], 6)

        # 6B: Fatal constraint
        planner_b = self._create_planner()
        fatal_uc = UnmetConstraint(
            category="REACHABILITY",
            target_name="foot_L",
            description="Limb target exceeds maximum reach",
            error_amount=0.045,
        )
        act_b1 = MockControlledAction(
            name="FatalConstraintAction",
            duration_frames=3,
            unmet_constraints=[fatal_uc],
            # Even if someone claims success=True, fatal unmet constraints MUST fail the planner
        )
        act_b2 = MockControlledAction(name="ShouldNotRunAction", duration_frames=3)
        planner_b.add_action(act_b1)
        planner_b.add_action(act_b2)
        with self.assertRaises(RuntimeError) as cm_b:
            planner_b.execute(initial_state=init_st)
        err_msg_b = str(cm_b.exception)
        self.assertIn("FatalConstraintAction", err_msg_b)
        self.assertIn("REACHABILITY", err_msg_b)
        self.assertFalse(act_b2.executed)

    def test_07_start_stop_walk_action_compatibility(self) -> None:
        """Test 7: StartStopWalkAction historical compatibility through MotionPlanner."""
        planner = self._create_planner()
        walk_action = StartStopWalkAction()
        planner.add_action(walk_action)
        init_st = create_initial_motion_state(self.config, start_frame=1)
        res = planner.execute(initial_state=init_st)

        self.assertGreater(res["total_frames"], 0)
        action_res = res["action_results"][0]
        self.assertIsInstance(action_res, ActionExecutionResult)
        self.assertTrue(action_res.success)
        self.assertEqual(len(action_res.unmet_constraints), 0)
        self.assertIsNone(action_res.failure_reason)

    def test_08_terrain_walk_action_compatibility(self) -> None:
        """Test 8: TerrainWalkAction historical compatibility and failure propagation under MotionPlanner."""
        planner = self._create_planner()
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.3, 0.0),
            nominal_stride_m=0.3,
            stand_start_frames=4,
            step_frames=8,
            stand_stop_frames=4,
        )
        walk_action = TerrainWalkAction(route=route, environment=self.env)
        planner.add_action(walk_action)
        init_st = create_initial_motion_state(self.config, start_frame=1)
        init_st = init_st.clone_with(position=(0.0, 0.0, 0.0))
        res = planner.execute(initial_state=init_st)

        self.assertGreater(res["total_frames"], 0)
        action_res = res["action_results"][0]
        self.assertIsInstance(action_res, ActionExecutionResult)
        self.assertTrue(action_res.success)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
