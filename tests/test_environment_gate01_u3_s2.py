"""ProceduralAnimation — Environment Gate 01 / Unit 3 / Atomic Repair S2 Test Suite.

Verifies the Swing-to-Stance Landing Continuity Repair:
- S2-T01: Counter-Factual Proof: Baseline data exhibits 40.4mm vertical drop at Frame 188->189.
- S2-T02: Frame 188->189 Landing Continuity: Planned target diff <= 1e-4m and armature diff <= 1e-4m.
- S2-T03: All 42 Boundaries Contract: 100% of step transitions meet <= 1e-4m tolerance.
- S2-T04: Reopened Blend Physical Validation: 0 ROM violations, 0 terrain penetrations, 0 bone stretch.
- S2-T05: Pure Math Swing Clearance Contract: Boundary C0 continuity at alpha=0 and alpha=1.
- S2-T06: Unit 3-S1 Root Continuity Regression: Zero velocity collapse, steady forward progress.
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

from src.motion.terrain_walk import (
    TerrainRouteInput,
    TerrainStepPlan,
    TerrainWalkAction,
    _compute_swing_clearance_z,
    plan_terrain_footsteps,
)
from src.scene.playground_terrain_traversal import (
    create_standard_dynamics_playground_query,
    generate_dynamics_playground_environment_gate01_u3_s2_blend,
)
from src.scene.playground_terrain_validation import (
    validate_dynamics_playground_environment_gate01_u3,
)
from tests.verify_environment_gate01_u3_s1 import (
    compute_kinematics,
    analyze_step_boundaries,
    load_telemetry_or_blend,
)
from tests.verify_environment_gate01_u3_s2 import (
    extract_landing_boundaries,
    compare_landing_boundaries,
)


class TestEnvironmentGate01Unit3S2(unittest.TestCase):
    """Test suite verifying Swing-to-Stance Landing Continuity repair (Unit 3-S2)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.u3_s2_blend = os.path.abspath("output/dynamics_playground_environment_gate01_u3_s2.blend")
        cls.evidence_dir = os.path.abspath("docs/evidence/environment_gate01_u3_s2")
        cls.before_json = os.path.join(cls.evidence_dir, "landing_boundary_before.json")
        cls.after_json = os.path.join(cls.evidence_dir, "landing_boundary_after.json")
        cls.comparison_json = os.path.join(cls.evidence_dir, "landing_boundary_comparison.json")
        cls.telemetry_json = os.path.join(cls.evidence_dir, "u3_control_chain_diagnostics.json")

        if not os.path.exists(cls.u3_s2_blend):
            generate_dynamics_playground_environment_gate01_u3_s2_blend(
                output_blend_path=cls.u3_s2_blend,
                evidence_dir=cls.evidence_dir,
            )

    def test_s2_t01_before_boundary_snap_proof(self) -> None:
        """T01: Mathematically prove the baseline suffered from 40.4mm drop at Frame 188->189."""
        if not os.path.exists(self.before_json):
            self.skipTest("Baseline before JSON not found.")

        with open(self.before_json, "r", encoding="utf-8") as f:
            before_data = json.load(f)

        self.assertEqual(len(before_data), 42)

        # Locate frame 188 -> 189 boundary
        b188 = None
        for b in before_data:
            if b["frame_last_swing"] == 188:
                b188 = b
                break

        self.assertIsNotNone(b188)
        self.assertEqual(b188["swing_side"], "R")
        # Target diff before fix was ~40.4 mm (0.0404 m)
        self.assertGreater(b188["target_diff_m"], 0.035)
        self.assertLess(b188["target_diff_m"], 0.045)
        # IK difference before fix was ~40.4 mm
        self.assertGreater(b188["ik_diff_m"], 0.035)
        self.assertLess(b188["ik_diff_m"], 0.045)

    def test_s2_t02_frame_188_189_landing_continuity(self) -> None:
        """T02: Prove that Frame 188->189 landing discontinuity is completely eliminated."""
        boundaries = extract_landing_boundaries(self.u3_s2_blend, self.telemetry_json)
        self.assertEqual(len(boundaries), 42)

        b188 = None
        for b in boundaries:
            if b["frame_last_swing"] == 188:
                b188 = b
                break

        self.assertIsNotNone(b188)
        self.assertEqual(b188["swing_side"], "R")
        # Contract: target diff <= 1e-4 m (0.1 mm)
        self.assertLessEqual(b188["target_diff_m"], 1.0e-4)
        self.assertLessEqual(b188["ik_diff_m"], 1.0e-4)

    def test_s2_t03_all_42_boundaries_continuity_contract(self) -> None:
        """T03: Prove that 100% of all 42 step boundaries satisfy <= 1e-4m tolerance."""
        boundaries = extract_landing_boundaries(self.u3_s2_blend, self.telemetry_json)
        self.assertEqual(len(boundaries), 42)

        max_target_diff = 0.0
        max_ik_diff = 0.0
        for b in boundaries:
            t_diff = b["target_diff_m"]
            ik_diff = b["ik_diff_m"]
            max_target_diff = max(max_target_diff, t_diff)
            max_ik_diff = max(max_ik_diff, ik_diff)
            self.assertLessEqual(
                t_diff, 1.0e-4,
                f"Step {b['step_k']} ({b['frame_last_swing']}->{b['frame_first_stance']}) target diff {t_diff:.6f}m exceeds 1e-4m"
            )
            self.assertLessEqual(
                ik_diff, 1.0e-4,
                f"Step {b['step_k']} ({b['frame_last_swing']}->{b['frame_first_stance']}) ik diff {ik_diff:.6f}m exceeds 1e-4m"
            )

        # Planned target difference across all boundaries is exactly 0.0
        self.assertLessEqual(max_target_diff, 1.0e-6)
        # Actual armature difference across all boundaries is <= 1e-4m (0.1 mm)
        self.assertLessEqual(max_ik_diff, 1.0e-4)

    def test_s2_t04_reopened_blend_physical_validation(self) -> None:
        """T04: Validate physical and anatomical constraints on reopened S2 blend file."""
        val_report = validate_dynamics_playground_environment_gate01_u3(self.u3_s2_blend)
        self.assertEqual(val_report["status"], "PASS")
        self.assertEqual(val_report["total_rom_violations"], 0)
        self.assertEqual(val_report["total_terrain_penetrations"], 0)
        self.assertLess(val_report["max_locked_ankle_drift_m"], 0.0001)
        self.assertLess(val_report["max_bone_stretch_m"], 0.0001)
        self.assertLess(val_report["max_root_velocity_m_per_frame"], 0.05)

    def test_s2_t05_pure_math_swing_clearance_helper(self) -> None:
        """T05: Test pure math helper _compute_swing_clearance_z contract."""
        z_base_start = 1.0
        z_base_end = 2.0
        arc = 0.12
        # Ground support high bump (0.5m higher than base)
        z_obstacle = 2.5

        # Boundary takeoff: alpha = 0.0
        z_0 = _compute_swing_clearance_z(
            step_alpha=0.0,
            z_base=z_base_start,
            arc_z=0.0,
            z_terr_foot=z_obstacle,
            min_clearance_amp=0.045,
        )
        self.assertAlmostEqual(z_0, z_base_start, places=7)

        # Boundary landing: alpha = 1.0
        z_1 = _compute_swing_clearance_z(
            step_alpha=1.0,
            z_base=z_base_end,
            arc_z=0.0,
            z_terr_foot=z_obstacle,
            min_clearance_amp=0.045,
        )
        self.assertAlmostEqual(z_1, z_base_end, places=7)

        # Mid-swing: alpha = 0.5
        z_mid_base = 0.5 * (z_base_start + z_base_end)
        z_mid = _compute_swing_clearance_z(
            step_alpha=0.5,
            z_base=z_mid_base,
            arc_z=arc,
            z_terr_foot=z_obstacle,
            min_clearance_amp=0.045,
        )
        # Mid-swing must clear the obstacle
        self.assertGreaterEqual(z_mid, z_obstacle + 0.045 - 1e-6)

    def test_s2_t06_root_continuity_regression_preservation(self) -> None:
        """T06: Regression test: Prove Unit 3-S1 Root continuity is 100% preserved."""
        frames = load_telemetry_or_blend(self.u3_s2_blend, self.telemetry_json)
        self.assertEqual(len(frames), 700)

        velocities, accelerations = compute_kinematics(frames)
        report = analyze_step_boundaries(frames, velocities)

        # 0 boundary velocity collapse anomalies
        self.assertEqual(report["total_step_boundaries"], 41)
        self.assertEqual(report["anomalies_detected"], 0)

        # Boundary forward speed is steady (> 0.20 m/s)
        self.assertGreater(report["minimum_boundary_velocity_m_s"], 0.20)
        self.assertGreater(report["mean_boundary_velocity_m_s"], 0.35)

        # Strict monotonicity: forward velocity is non-negative everywhere
        for v in velocities:
            self.assertGreaterEqual(v["v_forward"], -1e-6, f"Backward motion at frame {v['frame']}: {v['v_forward']}")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
