"""ProceduralAnimation — Environment Gate 01 / Unit 3 / Atomic Repair S1 Test Suite.

Verifies the decoupling of Root forward motion from single-step swing foot interpolation:
- S1-T01: Counter-Factual Proof: Old Root calculation exhibits 100% boundary velocity collapse.
- S1-T02: New Continuous Root Trajectory: 0 boundary collapse anomalies, physical contacts preserved.
- S1-T03: Stride Variation Invariance: Verified on 0.20m and 0.40m strides (zero hardcoding).
- S1-T04: Mathematical Hermite Spline Boundary & Monotonicity Contract.
"""

from __future__ import annotations

import json
import math
import os
import sys
import unittest
from typing import Any, Dict, List, Optional, Tuple

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from mathutils import Vector

from src.config import PipelineConfig
from src.motion.framework import (
    MotionAction,
    MotionMode,
    MotionPlanner,
    MotionState,
    create_initial_motion_state,
)
from src.motion.terrain_walk import (
    TerrainRouteInput,
    TerrainStepPlan,
    TerrainWalkAction,
    _build_continuous_root_forward_spline,
    _evaluate_root_y_hermite,
    plan_terrain_footsteps,
)
from src.scene.environment_query import EnvironmentQuery
from src.scene.playground_terrain_traversal import (
    create_standard_dynamics_playground_query,
    generate_dynamics_playground_environment_gate01_u3_s1_blend,
)
from src.scene.playground_terrain_validation import (
    validate_dynamics_playground_environment_gate01_u3,
)
from tests.verify_environment_gate01_u3_s1 import (
    compute_kinematics,
    analyze_step_boundaries,
    load_telemetry_or_blend,
)


class TestEnvironmentGate01Unit3S1(unittest.TestCase):
    """Test suite verifying Root forward motion continuity repair (Unit 3-S1)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.u3_blend = os.path.abspath("output/dynamics_playground_environment_gate01_u3.blend")
        cls.u3_s1_blend = os.path.abspath("output/dynamics_playground_environment_gate01_u3_s1.blend")
        cls.evidence_dir = os.path.abspath("docs/evidence/environment_gate01_u3_s1")

        if not os.path.exists(cls.u3_s1_blend):
            generate_dynamics_playground_environment_gate01_u3_s1_blend(
                output_blend_path=cls.u3_s1_blend,
                evidence_dir=cls.evidence_dir,
            )

    def test_s1_t01_old_root_velocity_collapse_proof(self) -> None:
        """T01: Mathematically prove that the baseline Unit 3 Root experienced velocity collapse."""
        if not os.path.exists(self.u3_blend):
            self.skipTest("Baseline Unit 3 blend not found.")

        u3_json = os.path.join(repo_root, "docs/evidence/environment_gate01_ru3/u3_control_chain_diagnostics.json")
        frames = load_telemetry_or_blend(self.u3_blend, u3_json)
        self.assertEqual(len(frames), 700)

        velocities, accelerations = compute_kinematics(frames)
        report = analyze_step_boundaries(frames, velocities)

        # Proves 100% of internal boundaries suffered from velocity collapse
        self.assertEqual(report["total_step_boundaries"], 41)
        self.assertEqual(report["anomalies_detected"], 41)
        self.assertTrue(report["hypothesis_confirmed"])

        # Baseline minimum boundary speed was < 0.05 m/s (~0.0346 m/s)
        self.assertLess(report["minimum_boundary_velocity_m_s"], 0.05)
        self.assertLess(report["mean_boundary_velocity_m_s"], 0.10)

    def test_s1_t02_new_root_continuity_and_foot_contacts(self) -> None:
        """T02: Prove that new Root motion eliminates all boundary collapse anomalies with zero contact degradation."""
        s1_json = os.path.join(self.evidence_dir, "u3_control_chain_diagnostics.json")
        frames = load_telemetry_or_blend(self.u3_s1_blend, s1_json)
        self.assertEqual(len(frames), 700)

        velocities, accelerations = compute_kinematics(frames)
        report = analyze_step_boundaries(frames, velocities)

        # 0 boundary velocity collapse anomalies
        self.assertEqual(report["total_step_boundaries"], 41)
        self.assertEqual(report["anomalies_detected"], 0)

        # Boundary forward speed is healthy and steady
        self.assertGreater(report["minimum_boundary_velocity_m_s"], 0.20)
        self.assertGreater(report["mean_boundary_velocity_m_s"], 0.35)

        # Strict monotonicity: forward velocity is non-negative everywhere
        for v in velocities:
            self.assertGreaterEqual(v["v_forward"], -1e-6, f"Backward motion at frame {v['frame']}: {v['v_forward']}")

        # Reopen and validate blend artifact
        val_report = validate_dynamics_playground_environment_gate01_u3(self.u3_s1_blend)
        self.assertEqual(val_report["status"], "PASS")
        self.assertEqual(val_report["total_rom_violations"], 0)
        self.assertEqual(val_report["total_terrain_penetrations"], 0)
        self.assertLess(val_report["max_locked_ankle_drift_m"], 0.0001)
        self.assertLess(val_report["max_bone_stretch_m"], 0.0001)
        self.assertLess(val_report["max_root_velocity_m_per_frame"], 0.05)

    def test_s1_t03_stride_variation_invariance(self) -> None:
        """T03: Prove the new Root spline works for varying strides without hardcoded coordinates."""
        env = create_standard_dynamics_playground_query()

        for stride in [0.20, 0.40]:
            route = TerrainRouteInput(
                start_pos=(0.0, 10.2, 0.0),
                target_pos=(0.0, 15.0, 0.0),
                nominal_stride_m=stride,
                stand_start_frames=12,
                step_frames=16,
                stand_stop_frames=16,
            )
            schedule, total_frames = plan_terrain_footsteps(route, env, start_frame=1)
            self.assertGreater(len(schedule), 3)

            knot_f, knot_y, knot_v = _build_continuous_root_forward_spline(schedule, fps=24.0)
            self.assertEqual(len(knot_f), len(schedule) + 1)
            self.assertEqual(len(knot_y), len(schedule) + 1)
            self.assertEqual(len(knot_v), len(schedule) + 1)

            # Check boundary velocities are continuous and positive in steady-state
            for k in range(1, len(schedule)):
                self.assertGreater(knot_v[k], 0.0)

            # Sample Root positions across all frames
            prev_y = knot_y[0]
            max_dist_st = 0.0
            for step in schedule:
                dur = step.duration_frames
                dur_sec = dur / 24.0
                st_y = step.stance_xyz[1]
                for f in range(step.frame_start, step.frame_end):
                    ry = _evaluate_root_y_hermite(
                        current_frame=f,
                        step_k=step.k,
                        knot_frames=knot_f,
                        knot_y=knot_y,
                        knot_v=knot_v,
                        fps=24.0,
                    )
                    self.assertGreaterEqual(ry, prev_y - 1e-6, f"Root moved backwards at step {step.k}, frame {f}")
                    prev_y = ry
                    d_st = abs(ry - st_y)
                    if d_st > max_dist_st:
                        max_dist_st = d_st

            # Ensure Root stays within physiological reachability from stance foot (< 0.35m)
            self.assertLess(max_dist_st, 0.35)

    def test_s1_t04_hermite_boundary_properties(self) -> None:
        """T04: Verify pure mathematical properties of monotonic cubic Hermite evaluation."""
        knot_f = [10, 26]
        knot_y = [5.0, 5.5]
        knot_v = [0.3, 0.3]
        fps = 24.0

        # Boundary at u=0
        y_start = _evaluate_root_y_hermite(10, 0, knot_f, knot_y, knot_v, fps)
        self.assertAlmostEqual(y_start, 5.0, places=6)

        # Boundary at u=1
        y_end = _evaluate_root_y_hermite(26, 0, knot_f, knot_y, knot_v, fps)
        self.assertAlmostEqual(y_end, 5.5, places=6)

        # Midpoint is strictly between y0 and y1
        y_mid = _evaluate_root_y_hermite(18, 0, knot_f, knot_y, knot_v, fps)
        self.assertGreater(y_mid, 5.0)
        self.assertLess(y_mid, 5.5)

        # Out of bounds clamps safely
        self.assertAlmostEqual(_evaluate_root_y_hermite(5, -1, knot_f, knot_y, knot_v, fps), 5.0)
        self.assertAlmostEqual(_evaluate_root_y_hermite(30, 10, knot_f, knot_y, knot_v, fps), 5.5)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
