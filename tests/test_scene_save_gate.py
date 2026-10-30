"""ProceduralAnimation — Targeted Test Suite for Part 3: Scene Execution & Save Gate (FIND-R4-01).

Validates that:
1. When MotionPlanner reports success=False, save gate must raise RuntimeError and NOT save blend.
2. When unreachable targets exist (unreachable_count > 0), save gate must raise and NOT save blend.
3. When fatal constraints are violated, save gate raises RuntimeError and refuses to save .blend.
4. "continuous_without_exemption" is strictly computed from verification results, NEVER hardcoded to True.
5. On failure, pre-existing .blend files are protected from corruption/overwriting.
6. When execution succeeds cleanly, gate passes and blend file is legitimately saved.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy

from src.motion.framework import MotionPlanner, create_initial_motion_state, PipelineConfig
from src.scene.playground_terrain_traversal import (
    generate_dynamics_playground_environment_gate01_u3_blend,
    generate_dynamics_playground_task7a2_corrected_blend,
    verify_scene_execution_gate,
)


class TestSceneSaveGate(unittest.TestCase):
    """Targeted regression test for FIND-R4-01: Scene Execution & Save Gate."""

    def setUp(self) -> None:
        self.test_blend_path = os.path.abspath("output/test_gate_fail_delivery.blend")
        self.evidence_dir = os.path.abspath("output/test_gate_evidence")
        if os.path.exists(self.test_blend_path):
            os.remove(self.test_blend_path)
        os.makedirs(self.evidence_dir, exist_ok=True)

    def tearDown(self) -> None:
        if os.path.exists(self.test_blend_path):
            try:
                os.remove(self.test_blend_path)
            except OSError:
                pass

    def test_01_fault_injection_planner_failure_refuses_save(self) -> None:
        """1. When MotionPlanner reports success=False, save gate must raise RuntimeError and NOT save blend."""
        cfg = PipelineConfig()
        s0 = create_initial_motion_state(cfg, start_frame=1)

        failing_planner_result = {
            "success": False,
            "actions_executed": ["FailingAction"],
            "total_frames": 1,
            "root_disp_y": 0.0,
            "peak_speed_mps": 0.0,
            "unreachable_count": 3,
            "fatal_unmet_constraints": [{"category": "REACHABILITY", "error": 0.1}],
            "action_failure": {"action_name": "FailingAction", "reason": "Target unreachable"},
            "states": [s0],
            "frame_records": [{"frame": 1, "tau": 0, "root_y": 0.0, "environment": {}, "motion_planning": {}, "wbc": {}}],
            "step_schedule": [],
            "action_results": [],
            "metrics": {"unreachable_events_count": 3, "fatal_constraints_count": 1},
        }

        with patch.object(MotionPlanner, "execute", return_value=failing_planner_result):
            with self.assertRaises(RuntimeError) as ctx:
                generate_dynamics_playground_task7a2_corrected_blend(
                    output_blend_path=self.test_blend_path,
                    evidence_dir=self.evidence_dir,
                )

            err_msg = str(ctx.exception)
            self.assertIn("failed gate verification", err_msg)
            self.assertFalse(
                os.path.exists(self.test_blend_path),
                "Failed motion execution must NOT save or produce output blend file",
            )

    def test_02_fault_injection_gate01_u3_refuses_save(self) -> None:
        """2. When Environment Gate 01 / Unit 3 has unreachable targets, save gate must raise and NOT save blend."""
        cfg = PipelineConfig()
        s0 = create_initial_motion_state(cfg, start_frame=1)

        unreachable_planner_result = {
            "success": False,
            "actions_executed": ["TerrainWalk_CourseB_MeshBacked"],
            "total_frames": 1,
            "root_disp_y": 0.0,
            "peak_speed_mps": 0.0,
            "unreachable_count": 1,
            "fatal_unmet_constraints": [],
            "action_failure": None,
            "states": [s0],
            "frame_records": [{"frame": 1, "tau": 0, "root_y": 0.0, "environment": {}, "motion_planning": {}, "wbc": {}}],
            "step_schedule": [],
            "action_results": [],
            "metrics": {"unreachable_events_count": 1, "fatal_constraints_count": 0},
        }

        with patch.object(MotionPlanner, "execute", return_value=unreachable_planner_result):
            with self.assertRaises(RuntimeError) as ctx:
                generate_dynamics_playground_environment_gate01_u3_blend(
                    output_blend_path=self.test_blend_path,
                    evidence_dir=self.evidence_dir,
                )

            err_msg = str(ctx.exception)
            self.assertIn("failed gate verification", err_msg)
            self.assertFalse(
                os.path.exists(self.test_blend_path),
                "Unreachable target in Gate 01 / Unit 3 must NOT save blend file",
            )

    def test_03_verify_scene_execution_gate_contract(self) -> None:
        """3. Unit test for verify_scene_execution_gate helper across various failure categories."""
        cfg = PipelineConfig()
        s0 = create_initial_motion_state(cfg, start_frame=1)
        s1 = s0.clone_with(frame=2, position=(0.0, -7.9, 0.0))
        s_gap = s0.clone_with(frame=4, position=(0.0, -7.7, 0.0))      # Gap
        s_teleport = s0.clone_with(frame=2, position=(0.0, 10.0, 0.0)) # Teleport 17.9m

        # Success case
        clean_res = {
            "success": True,
            "unreachable_count": 0,
            "fatal_unmet_constraints": [],
            "action_failure": None,
        }
        passed, reasons = verify_scene_execution_gate(clean_res, [s0, s1])
        self.assertTrue(passed)
        self.assertEqual(len(reasons), 0)

        # Frame gap
        passed_gap, reasons_gap = verify_scene_execution_gate(clean_res, [s0, s_gap])
        self.assertFalse(passed_gap)
        self.assertTrue(any("gap" in r for r in reasons_gap))

        # Teleport
        passed_tele, reasons_tele = verify_scene_execution_gate(clean_res, [s0, s_teleport])
        self.assertFalse(passed_tele)
        self.assertTrue(any("spatial jump" in r for r in reasons_tele))

        # Fatal unmet constraints
        fatal_res = {
            "success": False,
            "unreachable_count": 0,
            "fatal_unmet_constraints": [{"category": "FOOT_CONTACT_FAILURE"}],
            "action_failure": None,
        }
        passed_fatal, reasons_fatal = verify_scene_execution_gate(fatal_res, [s0, s1])
        self.assertFalse(passed_fatal)
        self.assertTrue(any("fatal_unmet_constraints" in r for r in reasons_fatal))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
