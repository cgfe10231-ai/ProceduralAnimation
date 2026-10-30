"""Comprehensive Verification Suite for Terrain Planning Contracts (Joint Repair).

Verifies the mathematical rigor, failure modes, and architectural contracts for:
1. Group A: Lateral seam & edge detection sampling position bias (FIND-R2-07).
2. Group B: Unified schedule contract consistency & strict failure semantics (FIND-R2-06).
3. Group C: Bidirectional (+/- Y) corridor traversal, monotonicity, and input validation (FIND-T01-07, max_step_length_m, nominal_stride_m).
4. Group D: Root Hermite spline and swing foot timebase synchronization in Blender (FIND-T01-08).
5. Group E: Spec duration estimation and runtime execution contracts (Finding G).
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from typing import Dict, List, Optional, Tuple

if "." not in sys.path:
    sys.path.insert(0, ".")
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

import bpy
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    ActionExecutionResult,
    ContactConstraintAdapter,
    ContactPointState,
    EnvironmentQuery,
    MotionAction,
    MotionMode,
    MotionRuntimeContext,
    MotionState,
    SurfaceQueryResult,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.terrain_walk import (
    HIP_X_OFFSET,
    MAX_LEG_REACH,
    TerrainRouteInput,
    TerrainStepPlan,
    TerrainTraversalSpec,
    TerrainWalkAction,
    _adjust_footfall_for_seams_and_edges,
    _build_continuous_root_forward_spline,
    _evaluate_root_y_hermite,
    _validate_route_input,
    build_terrain_step_schedule,
    pitch_from_surface_normal,
    plan_terrain_footsteps,
)
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik


class MockFlexibleEnvironment(EnvironmentQuery):
    """Flexible mock environment supporting multiple surface patches and asymmetric seams."""

    def __init__(self, ground_z: float = 0.0) -> None:
        super().__init__(ground_z=ground_z)
        # Patch definition: list of dicts with bounds and properties
        self.patches: List[dict] = []

    def add_patch(
        self,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        z_func=None,
        normal: Tuple[float, float, float] = (0.0, 0.0, 1.0),
        allows_support: bool = True,
        surface_id: str = "patch",
        success: bool = True,
        error_reason: str = "",
    ) -> None:
        self.patches.append({
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "z_func": z_func if z_func else (lambda x, y: 0.0),
            "normal": normal,
            "allows_support": allows_support,
            "surface_id": surface_id,
            "success": success,
            "error_reason": error_reason,
        })

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        for p in self.patches:
            if p["x_min"] <= x <= p["x_max"] and p["y_min"] <= y <= p["y_max"]:
                if not p["success"]:
                    return SurfaceQueryResult(
                        surface_id=p["surface_id"],
                        surface_type="invalid",
                        contact_point_world=(x, y, self.ground_z),
                        surface_normal_world=(0.0, 0.0, 1.0),
                        signed_distance=0.0,
                        friction_coeff=0.0,
                        allows_regular_support=p["allows_support"],
                        success=False,
                        error_reason=p["error_reason"] or "query_ground_support_at raycast missed geometry",
                    )
                z = p["z_func"](x, y)
                return SurfaceQueryResult(
                    surface_id=p["surface_id"],
                    surface_type="patch",
                    contact_point_world=(x, y, z),
                    surface_normal_world=p["normal"],
                    signed_distance=0.0,
                    friction_coeff=0.6,
                    allows_regular_support=p["allows_support"],
                    success=True,
                    source_type="analytic",
                )
        # Default flat ground fallback
        return SurfaceQueryResult(
            surface_id="ground",
            surface_type="ground",
            contact_point_world=(x, y, self.ground_z),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.6,
            allows_regular_support=True,
            success=True,
            source_type="analytic",
        )

    def ground_height_at(self, x: float, y: float) -> float:
        res = self.query_ground_support_at(x, y)
        return res.contact_point_world[2] if res.success else self.ground_z

    def surface_normal_at(self, x: float, y: float) -> Tuple[float, float, float]:
        res = self.query_ground_support_at(x, y)
        return res.surface_normal_world if res.success else (0.0, 0.0, 1.0)


class TestGroupASeamAndLateralSampling(unittest.TestCase):
    """Group A: Seam and Edge Detection Lateral Sampling Position Bias (FIND-R2-07)."""

    def setUp(self) -> None:
        self.env = MockFlexibleEnvironment(ground_z=0.0)

    def test_seam_lateral_position_bias_fixed_step_uses_sw_x(self) -> None:
        """Verify that seam detection samples at true swing foot lateral position `sw_x`.

        Prior to fix: sampled at corridor_x = 0.0. A seam located only on the right foot path
        (x in [0.05, 0.20]) was completely missed when sampling at x=0.0, but correctly detected
        when sampling at sw_x = +0.11.
        """
        # Right foot path (x > 0.05) has a slope seam at y=0.30 (ramp starts at y=0.30)
        # Centerline and left foot path remain completely flat
        ramp_normal = (0.0, -0.342, 0.940)  # ~20 deg slope
        self.env.add_patch(
            x_min=0.05, x_max=0.30,
            y_min=0.30, y_max=1.00,
            z_func=lambda x, y: (y - 0.30) * 0.364,
            normal=ramp_normal,
            allows_support=True,
            surface_id="right_ramp",
        )

        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.90, 0.0),
            nominal_stride_m=0.30,
            step_width_m=0.22,
        )

        sched, _ = plan_terrain_footsteps(route, self.env)
        self.assertGreater(len(sched), 0)

        # Step 0: Swing side is "R", sw_x = +0.11.
        # Straddles seam at y=0.30 (toe at 0.30+0.15=0.45 is on ramp, heel at 0.30-0.07=0.23 is on flat).
        # Must shift y away from 0.30 to seat the entire foot flat!
        step_0 = sched[0]
        self.assertEqual(step_0.swing_side, "R")
        self.assertNotEqual(round(step_0.swing_end_xyz[1], 4), 0.3000,
                            "Step 0 landing Y should be shifted away from seam at y=0.30")
        self.assertAlmostEqual(step_0.swing_end_xyz[1], 0.3800, places=3,
                               msg="Step 0 landing Y should shift forward to >= 0.38m for flat seating")

    def test_asymmetric_seams_only_affected_foot_shifts(self) -> None:
        """Verify asymmetric seam only shifts the foot encountering it."""
        # Seam at y=0.30 only on right foot path
        ramp_normal = (0.0, -0.342, 0.940)
        self.env.add_patch(
            x_min=0.05, x_max=0.30,
            y_min=0.30, y_max=1.50,
            z_func=lambda x, y: (y - 0.30) * 0.364,
            normal=ramp_normal,
            allows_support=True,
            surface_id="right_ramp",
        )

        # Direct function test for left vs right foot
        adj_r = _adjust_footfall_for_seams_and_edges(self.env, sw_x=0.11, y=0.30, corridor_y_min=0.0, corridor_y_max=1.0)
        adj_l = _adjust_footfall_for_seams_and_edges(self.env, sw_x=-0.11, y=0.30, corridor_y_min=0.0, corridor_y_max=1.0)

        self.assertAlmostEqual(adj_r, 0.38, places=3, msg="Right foot must shift away from seam")
        self.assertAlmostEqual(adj_l, 0.30, places=3, msg="Left foot on flat path must NOT shift")

    def test_seam_shift_bounds_both_positive_and_negative_directions(self) -> None:
        """Verify shift candidates are strictly bounded by [min(y_bounds), max(y_bounds)]."""
        # In a negative Y corridor [0.0, -1.0], corridor_y_min=0.0, corridor_y_max=-1.0
        # Shifts must be bounded within [-1.0, 0.0]
        y_out = _adjust_footfall_for_seams_and_edges(
            self.env, sw_x=0.11, y=-0.05, corridor_y_min=0.0, corridor_y_max=-1.0
        )
        self.assertGreaterEqual(y_out, -1.0)
        self.assertLessEqual(y_out, 0.0)

    def test_unsupported_surface_no_valid_shift_raises_value_error(self) -> None:
        """Verify that when no planar or supported shift can be found, ValueError is raised."""
        # Place unsupported pit covering [-0.10, +0.10] around y=0.30
        self.env.add_patch(
            x_min=-0.50, x_max=0.50,
            y_min=0.20, y_max=0.40,
            allows_support=False,
            surface_id="abyss",
        )

        with self.assertRaises(ValueError) as cm:
            _adjust_footfall_for_seams_and_edges(
                self.env, sw_x=0.11, y=0.30, corridor_y_min=0.0, corridor_y_max=1.0
            )
        self.assertIn("straddles unsupported surface boundary", str(cm.exception))


class TestGroupBUnifiedSchedulingContracts(unittest.TestCase):
    """Group B: Schedule Contract Consistency & Strict Failure Semantics (FIND-R2-06)."""

    def setUp(self) -> None:
        self.env = MockFlexibleEnvironment(ground_z=0.0)

    def test_route_and_spec_produce_consistent_steps_on_flat_ground(self) -> None:
        """Verify plan_terrain_footsteps and build_terrain_step_schedule produce equivalent schedules."""
        spec = TerrainTraversalSpec(
            course_id="flat_test",
            start_pos=(0.0, 0.0, 0.0),
            waypoint_y=[0.30, 0.60, 0.90],
            stand_start_frames=4,
            step_frames=8,
            stand_stop_frames=4,
        )
        sched_spec, frames_spec = build_terrain_step_schedule(spec, self.env)

        # Build route that hits same 0.90m target
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.90, 0.0),
            nominal_stride_m=0.30,
            step_width_m=2.0 * HIP_X_OFFSET,
            stand_start_frames=4,
            step_frames=8,
            stand_stop_frames=4,
        )
        sched_route, frames_route = plan_terrain_footsteps(route, self.env)

        # Both schedules must have valid steps and equal start/swing side alternation
        self.assertEqual(len(sched_spec), 3)
        self.assertEqual(sched_spec[0].swing_side, "R")
        self.assertEqual(sched_spec[1].swing_side, "L")
        self.assertEqual(sched_spec[2].swing_side, "R")
        for r_step, s_step in zip(sched_route[:3], sched_spec):
            self.assertEqual(r_step.stance_side, s_step.stance_side)
            self.assertEqual(r_step.swing_side, s_step.swing_side)
            self.assertAlmostEqual(r_step.swing_end_xyz[1], s_step.swing_end_xyz[1], places=4)
            self.assertAlmostEqual(r_step.swing_end_xyz[2], s_step.swing_end_xyz[2], places=4)
            self.assertEqual(r_step.swing_surface_id, s_step.swing_surface_id)

    def test_strict_rejection_on_no_hit_for_both_schedulers(self) -> None:
        """Verify that NO_HIT (success=False) raises explicit ValueError in both schedulers."""
        # Add a patch covering full shift corridor around y=0.30
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=0.15, y_max=0.45,
            success=False,
            error_reason="Geometry missing under footprint",
            surface_id="hole",
        )

        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
            nominal_stride_m=0.30,
        )
        with self.assertRaises(ValueError) as cm_r:
            plan_terrain_footsteps(route, self.env)
        err_r = str(cm_r.exception)
        self.assertTrue("straddles unsupported surface boundary" in err_r or "rejected" in err_r)

        spec = TerrainTraversalSpec(
            course_id="hole_test",
            start_pos=(0.0, 0.0, 0.0),
            waypoint_y=[0.30, 0.60],
        )
        with self.assertRaises(ValueError) as cm_s:
            build_terrain_step_schedule(spec, self.env)
        self.assertIn("rejected", str(cm_s.exception))

    def test_strict_rejection_on_unsupported_surface_for_both_schedulers(self) -> None:
        """Verify that allows_regular_support=False raises explicit ValueError in both schedulers."""
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=0.15, y_max=0.45,
            allows_support=False,
            surface_id="water_hazard",
        )

        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
            nominal_stride_m=0.30,
        )
        with self.assertRaises(ValueError) as cm_r:
            plan_terrain_footsteps(route, self.env)
        self.assertIn("unsupported surface", str(cm_r.exception))

        spec = TerrainTraversalSpec(
            course_id="water_test",
            start_pos=(0.0, 0.0, 0.0),
            waypoint_y=[0.30, 0.60],
        )
        with self.assertRaises(ValueError) as cm_s:
            build_terrain_step_schedule(spec, self.env)
        self.assertIn("unsupported surface", str(cm_s.exception))

    def test_initial_stance_foot_support_failure_rejection(self) -> None:
        """Verify that starting on an unsupported surface is immediately rejected."""
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=-0.20, y_max=0.10,
            allows_support=False,
            surface_id="lava_start",
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
        )
        with self.assertRaises(ValueError) as cm:
            plan_terrain_footsteps(route, self.env)
        self.assertIn("Initial left foot placement", str(cm.exception))

    def test_physiological_elevation_reach_limit_rejection(self) -> None:
        """Verify that vertical drops/rises > 0.35m are rejected."""
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=0.25, y_max=0.80,
            z_func=lambda x, y: 0.50,  # 0.5m cliff
            allows_support=True,
            surface_id="cliff",
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
            nominal_stride_m=0.30,
        )
        with self.assertRaises(ValueError) as cm:
            plan_terrain_footsteps(route, self.env)
        self.assertIn("exceeding physical stepping limit", str(cm.exception))


class TestGroupCBidirectionalAndInputContracts(unittest.TestCase):
    """Group C: Bidirectional Traversal & Input Contracts (FIND-T01-07, max_step_length_m, nominal_stride_m)."""

    def setUp(self) -> None:
        self.env = MockFlexibleEnvironment(ground_z=0.0)

    def test_bidirectional_traversal_step_count_and_coordinate_symmetry(self) -> None:
        """Verify +Y and -Y produce identical step counts and mirrored Y coordinates."""
        dist = 1.20
        stride = 0.30
        route_plus = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, dist, 0.0),
            nominal_stride_m=stride,
        )
        route_minus = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, -dist, 0.0),
            nominal_stride_m=stride,
        )

        sched_p, frames_p = plan_terrain_footsteps(route_plus, self.env)
        sched_m, frames_m = plan_terrain_footsteps(route_minus, self.env)

        self.assertEqual(len(sched_p), len(sched_m), "Step counts must match symmetrically")
        self.assertEqual(frames_p, frames_m, "Total frames must match symmetrically")

        for k in range(len(sched_p)):
            yp = sched_p[k].swing_end_xyz[1]
            ym = sched_m[k].swing_end_xyz[1]
            self.assertAlmostEqual(yp, -ym, places=4, msg=f"Step {k} landing Y must be mirrored")

    def test_negative_y_strictly_monotonic_footsteps_and_spline(self) -> None:
        """Verify negative Y route produces strictly decreasing footsteps and monotonic Hermite root spline."""
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, -1.20, 0.0),
            nominal_stride_m=0.30,
            step_frames=8,
            stand_start_frames=4,
            stand_stop_frames=4,
        )
        sched, total_frames = plan_terrain_footsteps(route, self.env)
        self.assertGreater(len(sched), 0)

        # Footstep landing Y monotonicity
        for k in range(len(sched) - 2):  # Excluding identical closing steps
            self.assertLess(sched[k + 1].swing_end_xyz[1], sched[k].swing_end_xyz[1])

        # Hermite knot velocities must be non-positive for -Y
        fps = 24.0
        knot_frames, knot_y, knot_v = _build_continuous_root_forward_spline(sched, fps)
        for v in knot_v:
            self.assertLessEqual(v, 1e-6, "Knot velocity on -Y must be non-positive")

        # Spline evaluations must be strictly monotonic non-increasing
        eval_ys = []
        for f in range(knot_frames[0], knot_frames[-1] + 1):
            # Find active step_k
            step_k = 0
            for i in range(len(knot_frames) - 1):
                if knot_frames[i] <= f <= knot_frames[i + 1]:
                    step_k = i
                    break
            y_val = _evaluate_root_y_hermite(f, step_k, knot_frames, knot_y, knot_v, fps)
            eval_ys.append(y_val)

        for i in range(len(eval_ys) - 1):
            self.assertLessEqual(eval_ys[i + 1], eval_ys[i] + 1e-6,
                                 f"Root Y must not increase during negative Y traversal at frame {i}")

    def test_nominal_stride_validation_positive_and_finite(self) -> None:
        """Verify nominal_stride_m validation rejects non-positive, NaN, and Inf values."""
        for bad_stride in [0.0, -0.2, float('nan'), float('inf'), None]:
            route = TerrainRouteInput(
                start_pos=(0.0, 0.0, 0.0),
                target_pos=(0.0, 1.0, 0.0),
                nominal_stride_m=bad_stride,
            )
            with self.assertRaises(ValueError):
                _validate_route_input(route)

    def test_max_step_length_m_enforcement(self) -> None:
        """Verify nominal_stride_m is clamped by max_step_length_m and invalid min>max is rejected."""
        # 1. Validation rejection when min_step_length_m > max_step_length_m
        route_invalid = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 1.0, 0.0),
            min_step_length_m=0.50,
            max_step_length_m=0.40,
        )
        with self.assertRaises(ValueError) as cm:
            _validate_route_input(route_invalid)
        self.assertIn("cannot exceed max_step_length_m", str(cm.exception))

    def test_issue_a_case_a_positive_y_alternating(self) -> None:
        """Case A: Positive Y alternating progression bounded strictly by max_step_length_m.

        start_pos = (0, 0, 0), target_pos = (0, 2.0, 0)
        nominal_stride_m = 0.80, max_step_length_m = 0.40
        """
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 2.0, 0.0),
            nominal_stride_m=0.80,
            max_step_length_m=0.40,
        )
        sched, _ = plan_terrain_footsteps(route, self.env)
        self.assertGreater(len(sched), 0)

        displacement_table = []
        for i, step in enumerate(sched):
            expected_swing = "R" if (i % 2 == 0) else "L"
            self.assertEqual(step.swing_side, expected_swing, f"Step {i} must alternate strictly")
            disp = (Vector(step.swing_end_xyz) - Vector(step.swing_start_xyz)).length
            displacement_table.append((i, step.swing_side, round(disp, 4), round(step.swing_end_xyz[1], 4)))

            self.assertLessEqual(
                disp, 0.40 + 1e-4,
                f"Step {i} ({step.swing_side}) displacement {disp:.4f}m exceeds max_step_length_m (0.40m)"
            )
            self.assertNotAlmostEqual(
                disp, 0.80, places=2,
                msg=f"Step {i} ({step.swing_side}) had unconstrained 0.80m displacement!"
            )

        print("\n[Case A Displacement Table]")
        for entry in displacement_table:
            print(f"  Step {entry[0]}: {entry[1]}, disp={entry[2]:.4f}m, landing_y={entry[3]:.4f}m")

        # Both feet must finish at target_pos side-by-side
        self.assertAlmostEqual(sched[-2].swing_end_xyz[1], 2.0, places=3)
        self.assertAlmostEqual(sched[-1].swing_end_xyz[1], 2.0, places=3)

    def test_issue_a_case_b_negative_y_alternating(self) -> None:
        """Case B: Negative Y alternating progression bounded strictly by max_step_length_m and symmetric to Case A.

        start_pos = (0, 2.0, 0), target_pos = (0, 0, 0)
        nominal_stride_m = 0.80, max_step_length_m = 0.40
        """
        route_pos = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 2.0, 0.0),
            nominal_stride_m=0.80,
            max_step_length_m=0.40,
        )
        sched_pos, _ = plan_terrain_footsteps(route_pos, self.env)

        route_neg = TerrainRouteInput(
            start_pos=(0.0, 2.0, 0.0),
            target_pos=(0.0, 0.0, 0.0),
            nominal_stride_m=0.80,
            max_step_length_m=0.40,
        )
        sched_neg, _ = plan_terrain_footsteps(route_neg, self.env)

        self.assertEqual(len(sched_neg), len(sched_pos), "Case B step count must match Case A symmetrically")

        print("\n[Case B Displacement Table]")
        for i, (step_neg, step_pos) in enumerate(zip(sched_neg, sched_pos)):
            expected_swing = "R" if (i % 2 == 0) else "L"
            self.assertEqual(step_neg.swing_side, expected_swing)

            disp_neg = (Vector(step_neg.swing_end_xyz) - Vector(step_neg.swing_start_xyz)).length
            disp_pos = (Vector(step_pos.swing_end_xyz) - Vector(step_pos.swing_start_xyz)).length

            self.assertLessEqual(disp_neg, 0.40 + 1e-4)
            self.assertNotAlmostEqual(disp_neg, 0.80, places=2)
            self.assertAlmostEqual(disp_neg, disp_pos, places=4, msg=f"Step {i} asymmetry between +Y and -Y")
            print(f"  Step {i}: {step_neg.swing_side}, disp={disp_neg:.4f}m, landing_y={step_neg.swing_end_xyz[1]:.4f}m")

        self.assertAlmostEqual(sched_neg[-2].swing_end_xyz[1], 0.0, places=3)
        self.assertAlmostEqual(sched_neg[-1].swing_end_xyz[1], 0.0, places=3)

    def test_issue_a_case_c_closing_steps_semantics(self) -> None:
        """Case C: Closing steps semantics when normal steps would overshoot target.

        Target at 0.70m with nominal_stride_m=0.30, max_step_length_m=0.80.
        Both feet must neatly close at target without overshooting or exceeding max_step_length_m.
        """
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.70, 0.0),
            nominal_stride_m=0.30,
            max_step_length_m=0.80,
        )
        sched, _ = plan_terrain_footsteps(route, self.env)
        self.assertGreaterEqual(len(sched), 2)

        for i, step in enumerate(sched):
            self.assertLessEqual(step.swing_end_xyz[1], 0.70 + 1e-4, f"Step {i} overshot target 0.70m")
            disp = (Vector(step.swing_end_xyz) - Vector(step.swing_start_xyz)).length
            self.assertLessEqual(disp, 0.80 + 1e-4, f"Step {i} exceeded max_step_length_m")

        step_lead_close = sched[-2]
        step_trail_close = sched[-1]
        self.assertAlmostEqual(step_lead_close.swing_end_xyz[1], 0.70, places=3)
        self.assertAlmostEqual(step_trail_close.swing_end_xyz[1], 0.70, places=3)
        self.assertNotEqual(step_lead_close.swing_side, step_trail_close.swing_side)

    def test_issue_a_case_d_seam_adjustment_reverified_against_step_length(self) -> None:
        """Case D: Seam adjustment re-verified against max_step_length_m.

        Seam at y=0.30 causes forward shift to y=0.38.
        When max_step_length_m=0.35, forward shift of 0.38m violates 0.35m limit.
        System must reject forward shift and select compliant shift or clamp.
        """
        ramp_normal = (0.0, -0.342, 0.940)
        self.env.add_patch(
            x_min=0.05, x_max=0.30,
            y_min=0.30, y_max=1.00,
            z_func=lambda x, y: (y - 0.30) * 0.364,
            normal=ramp_normal,
            allows_support=True,
            surface_id="right_ramp_d",
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.90, 0.0),
            nominal_stride_m=0.30,
            step_width_m=0.22,
            max_step_length_m=0.35,
        )
        sched, _ = plan_terrain_footsteps(route, self.env)
        step_0 = sched[0]
        disp_0 = (Vector(step_0.swing_end_xyz) - Vector(step_0.swing_start_xyz)).length
        self.assertLessEqual(disp_0, 0.35 + 1e-4, f"Adjusted step displacement {disp_0:.4f}m exceeds max_step_length_m 0.35m")
        for i, step in enumerate(sched):
            disp = (Vector(step.swing_end_xyz) - Vector(step.swing_start_xyz)).length
            self.assertLessEqual(disp, 0.35 + 1e-4, f"Step {i} displacement {disp:.4f}m exceeds 0.35m")

    def test_issue_a_case_e_unsolvable_reach_gap_defensive_interception(self) -> None:
        """Case E: Defensive interception of unsolvable reach gap without infinite loops.

        A 0.50m chasm between y=0.20 and y=0.70 cannot be stepped into or crossed when max_step_length_m=0.40.
        Must raise explicit ValueError without hanging in infinite loop.
        """
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=0.20, y_max=0.70,
            allows_support=False,
            surface_id="unsolvable_chasm",
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 1.0, 0.0),
            nominal_stride_m=0.30,
            max_step_length_m=0.40,
        )
        with self.assertRaises(ValueError) as cm:
            plan_terrain_footsteps(route, self.env)
        err = str(cm.exception)
        self.assertTrue("rejected" in err or "unsupported" in err or "cannot advance" in err)

    def test_issue_b_counterfactual_support_true_but_success_false_rejected(self) -> None:
        """ISSUE-B: Counterfactual test where allows_regular_support=True but success=False (raycast miss/failure).

        System must strictly require result.success AND result.allows_regular_support for heel, toe, ankle,
        and must never synthesize (0, 0, 1) flat ground fallback.
        """
        self.env.add_patch(
            x_min=-0.5, x_max=0.5,
            y_min=0.20, y_max=0.40,
            allows_support=True,
            success=False,
            error_reason="Counterfactual sensor failure: raycast failed to hit mesh",
            surface_id="sensor_glitch_zone",
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
            nominal_stride_m=0.30,
            max_step_length_m=0.80,
        )
        with self.assertRaises(ValueError) as cm:
            plan_terrain_footsteps(route, self.env)
        err = str(cm.exception)
        self.assertTrue("straddles unsupported surface boundary" in err or "encountered query failure" in err or "rejected" in err)

    def test_non_collinear_x_corridor_rejection(self) -> None:
        """Verify non-collinear X corridor (start X != target X) is strictly rejected."""
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.50, 1.0, 0.0),
        )
        with self.assertRaises(ValueError) as cm:
            _validate_route_input(route)
        self.assertIn("collinear X corridor", str(cm.exception))

    def test_stationary_route_zero_displacement(self) -> None:
        """Verify stationary route (|dy| < 1e-4) returns empty schedule and idle frames."""
        route = TerrainRouteInput(
            start_pos=(0.0, 0.5, 0.0),
            target_pos=(0.0, 0.5, 0.0),
            stand_start_frames=6,
            stand_stop_frames=8,
        )
        sched, frames = plan_terrain_footsteps(route, self.env)
        self.assertEqual(len(sched), 0)
        self.assertEqual(frames, 14)


class TestGroupDRootAndSwingFootSynchronization(unittest.TestCase):
    """Group D: Root and Swing Foot Synchronization in Blender Headless (FIND-T01-08)."""

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
        cls.env = MockFlexibleEnvironment(ground_z=0.0)
        cls.adapter = ContactConstraintAdapter(cls.armature, cls.env)

    def _execute_walk(
        self,
        stand_start_frames: int,
        step_frames: int,
        stand_stop_frames: int,
        nominal_stride_m: float = 0.30,
        target_y: float = 0.30,
    ) -> ActionExecutionResult:
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
            default_fps=self.config.fps,
        )
        ctx = MotionRuntimeContext(
            config=self.config,
            armature_obj=self.armature,
            root_obj=self.root,
            scene=bpy.context.scene,
            environment=self.env,
            contact_adapter=self.adapter,
            pose_applicator=None,
            bridge_executor=bridge,
        )
        init_state = create_initial_motion_state(self.config)
        init_state = init_state.clone_with(position=(0.0, 0.0, 0.0))

        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, target_y, 0.0),
            nominal_stride_m=nominal_stride_m,
            stand_start_frames=stand_start_frames,
            step_frames=step_frames,
            stand_stop_frames=stand_stop_frames,
        )
        action = TerrainWalkAction(route=route, environment=self.env)
        return action.execute(init_state, ctx)

    def test_boundary_condition_2_4_2_executes_without_reachability_failure(self) -> None:
        """Verify the exact 2/4/2 boundary condition passes with 0 reachability violations."""
        result = self._execute_walk(
            stand_start_frames=2,
            step_frames=4,
            stand_stop_frames=2,
            nominal_stride_m=0.30,
            target_y=0.30,
        )
        self.assertEqual(len(result.states), 12)
        self.assertEqual(result.unreachable_count, 0)
        self.assertTrue(result.success)

    def test_cadences_3_4_8_frames_execute_cleanly(self) -> None:
        """Verify multiple gait cadences (dur=3, dur=4, dur=8) all execute without reachability failure."""
        for step_f in [3, 4, 8]:
            result = self._execute_walk(
                stand_start_frames=4,
                step_frames=step_f,
                stand_stop_frames=4,
                nominal_stride_m=0.30,
                target_y=0.30,
            )
            self.assertEqual(result.unreachable_count, 0, f"Cadence dur={step_f} had unreachable frames")
            self.assertTrue(result.success, f"Cadence dur={step_f} had fatal failure")


class TestGroupESpecDurationEstimationAndContracts(unittest.TestCase):
    """Group E: Spec Duration Estimation & Action Contracts (Finding G)."""

    def setUp(self) -> None:
        self.env = MockFlexibleEnvironment(ground_z=0.0)
        self.config = PipelineConfig()

    def test_spec_estimate_duration_frames_no_type_error(self) -> None:
        """Verify action.estimate_duration_frames() with spec does not pass 'fps' and raises no TypeError."""
        spec = TerrainTraversalSpec(
            course_id="spec_test",
            start_pos=(0.0, 0.0, 0.0),
            waypoint_y=[0.30, 0.60],
            stand_start_frames=6,
            step_frames=12,
            stand_stop_frames=6,
        )
        action = TerrainWalkAction(spec=spec, environment=self.env)
        init_state = create_initial_motion_state(self.config)
        init_state = init_state.clone_with(position=(0.0, 0.0, 0.0))

        # Must execute without TypeError: got an unexpected keyword argument 'fps'
        dur = action.estimate_duration_frames(init_state, self.config, environment=self.env)
        # Expected frames: 6 + 2*12 + 6 = 36 frames
        self.assertEqual(dur, 36)

    def test_route_estimate_duration_frames(self) -> None:
        """Verify action.estimate_duration_frames() with route correctly estimates duration."""
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.60, 0.0),
            nominal_stride_m=0.30,
            stand_start_frames=4,
            step_frames=10,
            stand_stop_frames=4,
        )
        action = TerrainWalkAction(route=route, environment=self.env)
        init_state = create_initial_motion_state(self.config)
        init_state = init_state.clone_with(position=(0.0, 0.0, 0.0))

        dur = action.estimate_duration_frames(init_state, self.config, environment=self.env)
        self.assertEqual(dur, 38)  # 4 + 3*10 + 4 = 38 frames


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
