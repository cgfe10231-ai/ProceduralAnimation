"""ProceduralAnimation — Targeted & Real Integration Test Suite for Scene Execution & Save Gate (FIND-R4-01).

Validates that:
1. When MotionPlanner reports success=False, save gate must raise RuntimeError and NOT save blend.
2. When unreachable targets exist (unreachable_count > 0), save gate must raise and NOT save blend.
3. When fatal constraints are violated, save gate raises RuntimeError and refuses to save .blend.
4. Continuity threshold reuses authoritative 0.12m @ 24 FPS (2.88 m/s) contract across flat walk,
   ramp walk, real teleportation (e.g. 0.25m jump), frame gaps, boundary values, and FPS scaling.
5. Real Normal Scene Integration: executes real MotionPlanner pipeline, passes gate, writes .blend
   to disk, reopens .blend and verifies action records, scene metadata, and full validation match.
6. Real Failed Scene Integration: refuses to save, preserves pre-existing .blend file (SHA-256
   unchanged), preserves failure details, and writes zero counterfeit metadata or output files.
7. Validation consistency: locked stance foot over None support surface is caught as a violation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sys
import unittest
from unittest.mock import patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy

from src.config import PipelineConfig
from src.motion.framework import MotionPlanner, create_initial_motion_state
from src.motion.terrain_walk import TerrainRouteInput
from src.scene.playground_terrain_traversal import (
    generate_dynamics_playground_environment_gate01_u3_blend,
    generate_dynamics_playground_task7a2_corrected_blend,
    verify_scene_execution_gate,
)
from src.scene.playground_terrain_validation import (
    DEFAULT_MAX_ROOT_DISP_M_AT_24FPS,
    DEFAULT_REFERENCE_FPS,
    compute_max_root_disp_per_frame,
    validate_dynamics_playground_task7a2,
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class TestSceneSaveGate(unittest.TestCase):
    """Targeted & real integration regression test suite for Scene Execution & Save Gate."""

    def setUp(self) -> None:
        self.test_blend_path = os.path.abspath("output/test_gate_fail_delivery.blend")
        self.evidence_dir = os.path.abspath("output/test_gate_evidence")
        self.fail_evidence_dir = os.path.abspath("output/test_gate_fail_evidence")
        if os.path.exists(self.test_blend_path):
            os.remove(self.test_blend_path)
        if os.path.exists(self.evidence_dir):
            shutil.rmtree(self.evidence_dir, ignore_errors=True)
        if os.path.exists(self.fail_evidence_dir):
            shutil.rmtree(self.fail_evidence_dir, ignore_errors=True)
        os.makedirs(self.evidence_dir, exist_ok=True)

    def tearDown(self) -> None:
        for p in (self.test_blend_path, f"{self.test_blend_path}1"):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
        for d in (self.evidence_dir, self.fail_evidence_dir):
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)

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
            # Confirm no counterfeit metadata was written to active scene
            self.assertNotIn("task7a2_execution_summary", bpy.context.scene)

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
            self.assertNotIn("environment_gate01_u3_summary", bpy.context.scene)

    def test_03_verify_scene_execution_gate_contract(self) -> None:
        """3. Unit test for verify_scene_execution_gate helper across various failure categories."""
        cfg = PipelineConfig()
        s0 = create_initial_motion_state(cfg, start_frame=1, position=(0.0, -8.0, 0.0))
        s1 = s0.clone_with(frame=2, position=(0.0, -7.95, 0.0))
        s_gap = s0.clone_with(frame=4, position=(0.0, -7.90, 0.0))      # Gap
        s_teleport = s0.clone_with(frame=2, position=(0.0, 10.0, 0.0))  # Teleport 18.0m

        clean_res = {
            "success": True,
            "unreachable_count": 0,
            "fatal_unmet_constraints": [],
            "action_failure": None,
        }
        passed, reasons = verify_scene_execution_gate(clean_res, [s0, s1])
        self.assertTrue(passed)
        self.assertEqual(len(reasons), 0)

        passed_gap, reasons_gap = verify_scene_execution_gate(clean_res, [s0, s_gap])
        self.assertFalse(passed_gap)
        self.assertTrue(any("gap" in r for r in reasons_gap))

        passed_tele, reasons_tele = verify_scene_execution_gate(clean_res, [s0, s_teleport])
        self.assertFalse(passed_tele)
        self.assertTrue(any("spatial jump" in r for r in reasons_tele))

        fatal_res = {
            "success": False,
            "unreachable_count": 0,
            "fatal_unmet_constraints": [{"category": "FOOT_CONTACT_FAILURE"}],
            "action_failure": None,
        }
        passed_fatal, reasons_fatal = verify_scene_execution_gate(fatal_res, [s0, s1])
        self.assertFalse(passed_fatal)
        self.assertTrue(any("fatal_unmet_constraints" in r for r in reasons_fatal))

    def test_04_continuity_threshold_matrix_and_fps_scaling(self) -> None:
        """4. Verify authoritative C0 continuity threshold (0.12m @ 24 FPS) across all 6 required scenarios."""
        cfg = PipelineConfig()
        clean_res = {
            "success": True,
            "unreachable_count": 0,
            "fatal_unmet_constraints": [],
            "action_failure": None,
        }
        self.assertAlmostEqual(DEFAULT_MAX_ROOT_DISP_M_AT_24FPS, 0.12, places=6)
        self.assertAlmostEqual(DEFAULT_REFERENCE_FPS, 24.0, places=6)

        # (1) Normal flat walk (~0.035m/frame @ 24 FPS)
        flat_states = [
            create_initial_motion_state(cfg, start_frame=1 + i, position=(0.0, i * 0.035, 0.0))
            for i in range(20)
        ]
        passed_flat, reasons_flat = verify_scene_execution_gate(clean_res, flat_states, fps=24.0)
        self.assertTrue(passed_flat, f"Normal flat walk must pass: {reasons_flat}")

        # (2) Normal 16-deg ramp walk (~0.030m Y, ~0.0086m Z -> ~0.0312m 3D step @ 24 FPS)
        ramp_angle = math.radians(16.0)
        ramp_states = [
            create_initial_motion_state(
                cfg,
                start_frame=1 + i,
                position=(0.0, 11.0 + i * 0.030, i * 0.030 * math.tan(ramp_angle)),
            )
            for i in range(20)
        ]
        passed_ramp, reasons_ramp = verify_scene_execution_gate(clean_res, ramp_states, fps=24.0)
        self.assertTrue(passed_ramp, f"Normal ramp walk must pass: {reasons_ramp}")

        # (3) Real single-frame teleportation (0.25m jump at frame 227, < 1.0m old threshold but > 0.12m)
        s226 = create_initial_motion_state(cfg, start_frame=226, position=(0.0, 15.0, 0.50))
        s227 = s226.clone_with(frame=227, position=(0.0, 15.25, 0.50))
        passed_tele, reasons_tele = verify_scene_execution_gate(clean_res, [s226, s227], fps=24.0)
        self.assertFalse(passed_tele, "0.25m single-frame teleportation must be rejected by 0.12m gate")
        self.assertTrue(any("0.2500m (> 0.1200m @ 24.0fps)" in r for r in reasons_tele))

        # (4) Non-consecutive frame numbers (frame 10 -> frame 12)
        s10 = create_initial_motion_state(cfg, start_frame=10, position=(0.0, 1.0, 0.0))
        s12 = s10.clone_with(frame=12, position=(0.0, 1.02, 0.0))
        passed_gap, reasons_gap = verify_scene_execution_gate(clean_res, [s10, s12], fps=24.0)
        self.assertFalse(passed_gap)
        self.assertTrue(any("frame gap detected between frame 10 and 12" in r for r in reasons_gap))

        # (5) Near-boundary motion at 24 FPS (0.119m passes, 0.120m passes, 0.121m fails)
        sb0 = create_initial_motion_state(cfg, start_frame=1, position=(0.0, 0.0, 0.0))
        sb_pass1 = sb0.clone_with(frame=2, position=(0.0, 0.119, 0.0))
        sb_pass2 = sb0.clone_with(frame=2, position=(0.0, 0.120, 0.0))
        sb_fail = sb0.clone_with(frame=2, position=(0.0, 0.121, 0.0))
        self.assertTrue(verify_scene_execution_gate(clean_res, [sb0, sb_pass1], fps=24.0)[0])
        self.assertTrue(verify_scene_execution_gate(clean_res, [sb0, sb_pass2], fps=24.0)[0])
        self.assertFalse(verify_scene_execution_gate(clean_res, [sb0, sb_fail], fps=24.0)[0])

        # (6) Applicability across different FPS configurations (48 FPS -> 0.06m limit; 12 FPS -> 0.24m limit)
        self.assertAlmostEqual(compute_max_root_disp_per_frame(fps=48.0), 0.06, places=6)
        self.assertAlmostEqual(compute_max_root_disp_per_frame(fps=12.0), 0.24, places=6)
        s_0055 = sb0.clone_with(frame=2, position=(0.0, 0.055, 0.0))
        s_0065 = sb0.clone_with(frame=2, position=(0.0, 0.065, 0.0))
        self.assertTrue(verify_scene_execution_gate(clean_res, [sb0, s_0055], fps=48.0)[0])
        self.assertFalse(verify_scene_execution_gate(clean_res, [sb0, s_0065], fps=48.0)[0])

        s_022 = sb0.clone_with(frame=2, position=(0.0, 0.22, 0.0))
        s_025 = sb0.clone_with(frame=2, position=(0.0, 0.25, 0.0))
        self.assertTrue(verify_scene_execution_gate(clean_res, [sb0, s_022], fps=12.0)[0])
        self.assertFalse(verify_scene_execution_gate(clean_res, [sb0, s_025], fps=12.0)[0])

    def test_05_real_scene_pipeline_normal_and_failed_delivery_preserving_existing_blend(self) -> None:
        """5. Real end-to-end scene execution & save gate integration test (normal + failure overwrite protection)."""
        # =====================================================================
        # Chain 1: Normal Real MotionPlanner Execution -> Gate Pass -> Disk Save -> Reopen & Validate
        # =====================================================================
        valid_route = TerrainRouteInput(
            start_pos=(0.0, 10.20, 0.0),
            target_pos=(0.0, 15.80, 0.0),
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
        res = generate_dynamics_playground_task7a2_corrected_blend(
            output_blend_path=self.test_blend_path,
            evidence_dir=self.evidence_dir,
            route=valid_route,
        )
        self.assertTrue(res["planner_result"]["success"])
        self.assertTrue(res["summary"]["gate_passed"])
        self.assertTrue(res["summary"]["continuous_without_exemption"])
        self.assertEqual(res["summary"]["gate_failure_reasons"], [])
        self.assertTrue(os.path.exists(self.test_blend_path), "Real .blend file must be written to disk")
        valid_size = os.path.getsize(self.test_blend_path)
        self.assertGreater(valid_size, 100_000, "Saved .blend file must be a real non-empty scene")
        valid_sha256 = _sha256_file(self.test_blend_path)

        # Reopen the saved .blend file in a clean session and verify scene structure, animation, and metadata match
        bpy.ops.wm.open_mainfile(filepath=self.test_blend_path)
        reopened_scene = bpy.context.scene
        self.assertIsNotNone(bpy.data.objects.get("CharacterArmature"))
        self.assertIsNotNone(bpy.data.objects.get("CharacterRoot"))
        self.assertIsNotNone(bpy.data.scenes.get("Task7A2_ControlChain_Debug"))

        reopened_summary = json.loads(reopened_scene["task7a2_execution_summary"])
        reopened_contacts = json.loads(reopened_scene["task7a2_contact_state_records"])
        reopened_diag = json.loads(reopened_scene["task7a2_control_chain_diagnostics"])
        self.assertEqual(reopened_summary["total_frames"], res["total_frames"])
        self.assertTrue(reopened_summary["gate_passed"])
        self.assertTrue(reopened_summary["continuous_without_exemption"])
        self.assertEqual(reopened_summary["unreachable_count"], 0)
        self.assertEqual(len(reopened_contacts), res["total_frames"])
        self.assertEqual(len(reopened_diag), res["total_frames"])

        # Verify evaluated root trajectory in reopened .blend matches recorded states and C0 continuity gate
        root_obj = bpy.data.objects["CharacterRoot"]
        prev_pos = None
        for idx, rec in enumerate(reopened_contacts):
            reopened_scene.frame_set(rec["frame"])
            bpy.context.view_layer.update()
            cur_pos = root_obj.matrix_world.translation.copy()
            self.assertAlmostEqual(cur_pos.y, rec["root_position"][1], places=3)
            if prev_pos is not None:
                step_disp = (cur_pos - prev_pos).length
                self.assertLessEqual(step_disp, DEFAULT_MAX_ROOT_DISP_M_AT_24FPS + 1e-6)
            prev_pos = cur_pos

        # =====================================================================
        # Chain 2A: Real Unmocked Execution Failure Targeting Existing .blend -> Protects Existing File
        # =====================================================================
        with self.assertRaises(RuntimeError) as ctx_real:
            generate_dynamics_playground_task7a2_corrected_blend(
                output_blend_path=self.test_blend_path,
                evidence_dir=self.fail_evidence_dir,
            )
        self.assertIn("ROM_VIOLATION", str(ctx_real.exception))
        self.assertEqual(_sha256_file(self.test_blend_path), valid_sha256)
        self.assertFalse(
            os.path.exists(os.path.join(self.fail_evidence_dir, "task7a2_execution_summary.json")),
        )
        self.assertNotIn("task7a2_execution_summary", bpy.context.scene)

        # =====================================================================
        # Chain 2B: Gate-Level Continuity Failure (0.25m Teleport) Targeting Existing .blend -> Protects Existing File
        # =====================================================================
        corrupted_planner_result = dict(res["planner_result"])
        corrupted_states = list(res["planner_result"]["states"])
        s100 = corrupted_states[99]
        corrupted_states[100] = corrupted_states[100].clone_with(
            position=(s100.position[0], s100.position[1] + 0.25, s100.position[2])
        )
        corrupted_planner_result["states"] = corrupted_states

        with patch.object(MotionPlanner, "execute", return_value=corrupted_planner_result):
            with self.assertRaises(RuntimeError) as ctx:
                generate_dynamics_playground_task7a2_corrected_blend(
                    output_blend_path=self.test_blend_path,
                    evidence_dir=self.fail_evidence_dir,
                    route=valid_route,
                )

        err_msg = str(ctx.exception)
        self.assertIn("failed gate verification", err_msg)
        self.assertIn("spatial jump", err_msg)
        self.assertIn("frame 101", err_msg)

        # Verify pre-existing .blend file on disk was NOT overwritten or corrupted
        self.assertTrue(os.path.exists(self.test_blend_path))
        self.assertEqual(os.path.getsize(self.test_blend_path), valid_size)
        self.assertEqual(
            _sha256_file(self.test_blend_path),
            valid_sha256,
            "Pre-existing valid .blend file must NOT be overwritten when gate verification fails!",
        )

        # Verify no counterfeit companion JSON files were written into fail_evidence_dir
        self.assertFalse(
            os.path.exists(os.path.join(self.fail_evidence_dir, "task7a2_execution_summary.json")),
            "Failed execution must not write companion summary JSON",
        )
        # Verify in-memory scene did not receive counterfeit summary metadata during failed run
        self.assertNotIn("task7a2_execution_summary", bpy.context.scene)

    def test_06_stance_foot_off_support_validation_guard(self) -> None:
        """6. Verify playground_terrain_validation catches locked stance foot when ground_height_at returns None."""
        from src.scene.environment_query import DynamicsEnvironmentQuery

        # Mock ground_height_at to return None for X < 0 (left foot in stance at frame 1)
        with patch.object(
            DynamicsEnvironmentQuery,
            "ground_height_at",
            autospec=True,
            side_effect=lambda self_env, x, y: None if x < 0.0 else 0.0,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                validate_dynamics_playground_task7a2(
                    blend_path="output/dynamics_playground_task7a2_corrected.blend"
                )
            self.assertIn("terrain mesh penetrations", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
