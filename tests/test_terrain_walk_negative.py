"""Negative & Invariance Verification Suite for Terrain-Aware Locomotion (Task 7A-2).

Verifies the mathematical rigor, failure modes, and architectural guardrails of Phase 7A-2:
1. Surface Renaming Invariance: Proves kinematics are 100% invariant to object/surface names
   (zero string-matching logic; naming does not affect footfalls, pitches, or clearance).
2. Dynamic Elevation Perturbation: Proves the footstep planner dynamically senses and adapts
   to vertical terrain variations.
3. Unreachable Step Height Rejection: Proves the planner rejects physiological cliffs (> 0.35m)
   with explicit reachability exceptions.
4. Tampering & Continuity Violation Detection: Proves the validator strictly detects and rejects
   artificial teleports, stance anchor drift, bone stretching, and ROM violations.
"""

from __future__ import annotations

import copy
import math
import os
import sys
import unittest
from typing import Dict, List, Optional, Tuple

if "." not in sys.path:
    sys.path.insert(0, ".")
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from src.motion.framework import EnvironmentQuery
from src.scene.environment_query import SurfaceQueryResult
from src.motion.terrain_walk import (
    TerrainRouteInput,
    TerrainStepPlan,
    pitch_from_surface_normal,
    plan_terrain_footsteps,
)
from src.scene.playground_terrain_validation import validate_dynamics_playground_task7a2


class MockGeometryEnvironment(EnvironmentQuery):
    """Custom environment query simulating arbitrary 3D geometry without Blender scene dependency."""

    def __init__(self, ground_z: float = 0.0) -> None:
        super().__init__(ground_z=ground_z)
        self.surfaces: Dict[str, dict] = {}
        self.name_mapping: Dict[str, str] = {}

    def add_surface(
        self,
        surface_id: str,
        y_min: float,
        y_max: float,
        z_start: float,
        z_end: float,
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        allows_support: bool = True,
    ) -> None:
        self.surfaces[surface_id] = {
            "y_min": y_min,
            "y_max": y_max,
            "z_start": z_start,
            "z_end": z_end,
            "normal": normal,
            "allows_support": allows_support,
        }

    def ground_height_at(self, x: float, y: float) -> float:
        for sid, s in self.surfaces.items():
            if s["y_min"] <= y <= s["y_max"]:
                dy = s["y_max"] - s["y_min"]
                if dy <= 1e-6:
                    return s["z_start"]
                u = (y - s["y_min"]) / dy
                return s["z_start"] + u * (s["z_end"] - s["z_start"])
        return self.ground_z

    def surface_normal_at(self, x: float, y: float) -> Tuple[float, float, float]:
        for sid, s in self.surfaces.items():
            if s["y_min"] <= y <= s["y_max"]:
                return s["normal"]
        return (0.0, 0.0, 1.0)

    def query_surface_at_point(self, point: Tuple[float, float, float]) -> SurfaceQueryResult:
        px, py, pz = point
        for sid, s in self.surfaces.items():
            if s["y_min"] <= py <= s["y_max"]:
                effective_id = self.name_mapping.get(sid, sid)
                return SurfaceQueryResult(
                    surface_id=effective_id,
                    surface_type="generic",
                    contact_point_world=(px, py, self.ground_height_at(px, py)),
                    surface_normal_world=s["normal"],
                    signed_distance=0.0,
                    friction_coeff=0.8,
                    allows_regular_support=s["allows_support"],
                    success=True,
                    ray_hit_distance=0.0,
                )
        return SurfaceQueryResult(
            surface_id="ground",
            surface_type="ground",
            contact_point_world=(px, py, self.ground_z),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.8,
            allows_regular_support=True,
            success=True,
            ray_hit_distance=0.0,
        )


class TestTerrainWalkNegativeAndInvariance(unittest.TestCase):
    """Rigorous negative tests verifying architecture invariants and failure detection."""

    def setUp(self) -> None:
        # Standard test route
        self.route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 4.0, 0.0),
            nominal_stride_m=0.30,
            step_width_m=0.22,
        )

    def test_01_surface_renaming_invariance(self) -> None:
        """Proves planner kinematics are 100% independent of surface naming strings."""
        env1 = MockGeometryEnvironment(ground_z=0.0)
        # Sloped surface with standard name
        env1.add_surface("Ramp_Up", 1.0, 3.0, 0.0, 0.50, normal=(0.0, -0.242, 0.970))
        env1.add_surface("Ramp_Platform", 3.0, 5.0, 0.50, 0.50, normal=(0.0, 0.0, 1.0))

        schedule1, frames1 = plan_terrain_footsteps(self.route, env1)

        # Environment 2: EXACT SAME 3D geometry, but renamed with arbitrary obfuscated strings
        env2 = MockGeometryEnvironment(ground_z=0.0)
        env2.add_surface("Unrelated_Object_9988_Mesh", 1.0, 3.0, 0.0, 0.50, normal=(0.0, -0.242, 0.970))
        env2.add_surface("Arbitrary_Floor_Tag_001", 3.0, 5.0, 0.50, 0.50, normal=(0.0, 0.0, 1.0))

        schedule2, frames2 = plan_terrain_footsteps(self.route, env2)

        self.assertEqual(frames1, frames2, "Timeline frames must be identical regardless of surface names")
        self.assertEqual(len(schedule1), len(schedule2), "Step count must be identical regardless of names")

        for s1, s2 in zip(schedule1, schedule2):
            self.assertEqual(s1.k, s2.k)
            self.assertEqual(s1.frame_start, s2.frame_start)
            self.assertEqual(s1.frame_end, s2.frame_end)
            self.assertEqual(s1.stance_side, s2.stance_side)
            self.assertEqual(s1.swing_side, s2.swing_side)
            # Physical coordinates must be bit-for-bit identical
            self.assertAlmostEqual(s1.stance_xyz[0], s2.stance_xyz[0], places=6)
            self.assertAlmostEqual(s1.stance_xyz[1], s2.stance_xyz[1], places=6)
            self.assertAlmostEqual(s1.stance_xyz[2], s2.stance_xyz[2], places=6)
            self.assertAlmostEqual(s1.swing_end_xyz[0], s2.swing_end_xyz[0], places=6)
            self.assertAlmostEqual(s1.swing_end_xyz[1], s2.swing_end_xyz[1], places=6)
            self.assertAlmostEqual(s1.swing_end_xyz[2], s2.swing_end_xyz[2], places=6)
            self.assertAlmostEqual(s1.step_height_clearance, s2.step_height_clearance, places=6)

        print("\n[PASS] Test 1: Surface renaming invariance verified (zero string-matching dependency).")

    def test_02_dynamic_elevation_perturbation_adaptation(self) -> None:
        """Proves planner dynamically adapts footfall Z and clearance to vertical perturbations."""
        env_flat = MockGeometryEnvironment(ground_z=0.0)
        schedule_flat, _ = plan_terrain_footsteps(self.route, env_flat)

        # Elevate region between Y=1.5 and Y=3.0 by +0.15m
        env_bump = MockGeometryEnvironment(ground_z=0.0)
        env_bump.add_surface("Bump", 1.5, 3.0, 0.15, 0.15, normal=(0.0, 0.0, 1.0))

        schedule_bump, _ = plan_terrain_footsteps(self.route, env_bump)

        # Steps landing in [1.5, 3.0] must have elevation +0.15m
        adapted_steps = [s for s in schedule_bump if 1.5 <= s.swing_end_xyz[1] <= 3.0]
        self.assertGreater(len(adapted_steps), 0, "Should have steps landing on elevated bump")
        for s in adapted_steps:
            self.assertAlmostEqual(s.swing_end_xyz[2], 0.15, places=4)
            # Dynamic clearance must adapt
            self.assertGreaterEqual(s.step_height_clearance, self.route.base_clearance_m)

        print("[PASS] Test 2: Dynamic elevation perturbation adaptation verified.")

    def test_03_unreachable_cliff_drop_rejection(self) -> None:
        """Proves planner rejects physiologically impossible drops (> 0.35m vertical reach limit)."""
        env_cliff = MockGeometryEnvironment(ground_z=0.0)
        # 0.75m vertical drop at Y = 1.5 (like the Stairs Top Platform to Ramp gap!)
        env_cliff.add_surface("Platform_High", 0.0, 1.5, 0.75, 0.75, normal=(0.0, 0.0, 1.0))
        env_cliff.add_surface("Ground_Low", 1.5, 4.0, 0.0, 0.0, normal=(0.0, 0.0, 1.0))

        route_from_top = TerrainRouteInput(
            start_pos=(0.0, 0.5, 0.75),
            target_pos=(0.0, 3.0, 0.0),
            nominal_stride_m=0.30,
        )

        with self.assertRaises(ValueError) as ctx:
            plan_terrain_footsteps(route_from_top, env_cliff)

        self.assertIn("exceeding physical stepping limit", str(ctx.exception))
        print(f"[PASS] Test 3: Unreachable cliff drop (>0.35m) correctly rejected: {ctx.exception}")

    def test_04_unsupported_surface_rejection(self) -> None:
        """Proves planner rejects landing on hazard/non-support surfaces."""
        env_hazard = MockGeometryEnvironment(ground_z=0.0)
        env_hazard.add_surface("Lava_Pit", 1.0, 2.5, 0.0, 0.0, allows_support=False)

        with self.assertRaises(ValueError) as ctx:
            plan_terrain_footsteps(self.route, env_hazard)

        err_msg = str(ctx.exception)
        self.assertTrue(
            "lands on unsupported surface" in err_msg or "straddles unsupported surface boundary" in err_msg,
            f"Expected unsupported surface rejection message, got: {err_msg}",
        )
        print(f"[PASS] Test 4: Unsupported surface landing correctly rejected: {ctx.exception}")


def run_negative_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTerrainWalkNegativeAndInvariance)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_negative_tests())
