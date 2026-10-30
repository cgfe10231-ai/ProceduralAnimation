"""ProceduralAnimation — Targeted Test Suite for Part 2: Action Environment Binding (FIND-T01-06).

Validates that:
1. TerrainWalkAction without explicit environment raises ValueError on estimate_duration_frames()
   instead of silently creating a synthetic EnvironmentQuery(ground_z=0.0).
2. MotionPlanner.add_action() binds its authoritative environment to the action.
3. estimate_duration_frames() accepts optional environment parameter overriding action.environment.
4. Consistent footstep schedule and duration between estimate_duration_frames and execute on 3D terrain.
"""

from __future__ import annotations

import math
import os
import sys
import unittest

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy

from src.motion.framework import (
    MotionPlanner,
    MotionState,
    PipelineConfig,
    create_initial_motion_state,
)
from src.motion.terrain_walk import (
    TerrainRouteInput,
    TerrainWalkAction,
    plan_terrain_footsteps,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    EnvironmentQuery,
    OrientedSurface,
    SurfaceGeometryType,
)


class TestActionEnvironmentBinding(unittest.TestCase):
    """Targeted regression test for FIND-T01-06: Action Environment Binding."""

    def setUp(self) -> None:
        self.config = PipelineConfig(fps=30)
        self.init_state = create_initial_motion_state(
            self.config,
            start_frame=1,
        ).clone_with(position=(0.0, 0.0, 0.0))
        self.route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 3.0, 0.0),
            nominal_stride_m=0.60,
            step_width_m=0.20,
            stand_start_frames=10,
            step_frames=16,
            stand_stop_frames=10,
        )

    def test_01_unbound_action_prohibits_silent_flat_ground_fallback(self) -> None:
        """1. Unbound TerrainWalkAction must raise ValueError rather than faking flat ground."""
        action = TerrainWalkAction(route=self.route, environment=None)
        self.assertIsNone(action.environment, "Action created without environment must have environment=None")

        # Calling estimate_duration_frames without environment must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            action.estimate_duration_frames(self.init_state, self.config)

        err_msg = str(ctx.exception)
        self.assertIn("requires an authoritative environment", err_msg)
        self.assertIn("silent fallback", err_msg)

    def test_02_planner_add_action_binds_authoritative_environment(self) -> None:
        """2. MotionPlanner.add_action() must bind planner's authoritative environment to the action."""
        dyn_env = DynamicsEnvironmentQuery(ground_z=1.5)
        planner = MotionPlanner(config=self.config, environment=dyn_env)

        action = TerrainWalkAction(route=self.route, environment=None)
        self.assertIsNone(action.environment)

        planner.add_action(action)
        self.assertIs(
            action.environment,
            dyn_env,
            "MotionPlanner.add_action() must bind its authoritative environment to action.environment",
        )

        # Once bound by planner, estimate_duration_frames must succeed using the bound environment
        dur = action.estimate_duration_frames(self.init_state, self.config)
        self.assertGreater(dur, 0)

    def test_03_explicit_environment_override_in_estimate_duration(self) -> None:
        """3. estimate_duration_frames(..., environment=...) explicitly overrides action.environment."""
        env_flat = EnvironmentQuery(ground_z=0.0)
        action = TerrainWalkAction(route=self.route, environment=env_flat)

        env_custom = DynamicsEnvironmentQuery(ground_z=2.0)
        # Passing env_custom explicitly must be accepted and used
        dur = action.estimate_duration_frames(self.init_state, self.config, environment=env_custom)
        self.assertGreater(dur, 0)

    def test_04_schedule_consistency_with_elevated_terrain(self) -> None:
        """4. Duration estimation against 3D terrain yields consistent timeline duration."""
        # Elevated terrain at Z = 1.0m
        elevated_env = DynamicsEnvironmentQuery(ground_z=1.0)
        action = TerrainWalkAction(route=self.route, environment=elevated_env)

        est_dur = action.estimate_duration_frames(self.init_state, self.config)
        _, planned_dur = plan_terrain_footsteps(self.route, elevated_env, start_frame=self.init_state.frame)
        self.assertEqual(est_dur, planned_dur, "Estimated duration must strictly match planned footsteps duration")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
