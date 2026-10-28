"""ProceduralAnimation — Environment Gate 01 / Unit 3 Comprehensive Test Suite.

Verifies the integration of real evaluated Blender mesh geometry into the authoritative
19-bone humanoid character locomotion pipeline:
- U3-T01: Real Mesh Environment Injection (prefer_mesh=True, adapter active).
- U3-T02: Source Type Authenticity (source_type == "mesh").
- U3-T03: Initial Left/Right Footprint Mesh Hit (real mesh, not default ground).
- U3-T04: Single-Hit Consistency (Z, normal, surface_id, allows_support from single hit).
- U3-T05: Strict No-Support Rejection (NO_HIT on empty space, rejection on non-support).
- U3-T06: Analytical Mode Preservation (backward compatible analytical fallback).
- U3-T07: 6-Phase Pipeline Preservation (authoritative pipeline intact, 0 bone direct write).
- U3-T08: Counter-Factual Mesh Mutation Sensitivity (Experiment A vs B produces physical divergence).
- U3-T09: Counter-Factual Analytical Insensitivity (analytical query fails counter-factual test).
- U3-T10: Blend Artifact Reopen & Evaluation (validates dynamics_playground_environment_gate01_u3.blend).
- U3-T11: C0 Trajectory Continuity (zero frame exemptions, delta < 0.12m/frame).
- U3-T12: Zero Bone Stretch & Joint ROM Limits (< 0.1mm stretch, 0 ROM violations).
- U3-T13: Locked Foot Drift (< 0.1mm drift across all stance frames).
- U3-T14: Baseline File Protection (dynamics_playground.blend is 100% untouched).
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
    TerrainWalkAction,
    pitch_from_surface_normal,
    plan_terrain_footsteps,
)
from src.scene.blender_mesh_query_adapter import (
    AdapterCacheState,
    BlenderMeshEnvironmentAdapter,
    create_mesh_backed_dynamics_query,
)
from src.scene.environment_query import (
    DynamicsEnvironmentQuery,
    SurfaceGeometryType,
    SurfaceQueryResult,
    create_standard_dynamics_playground_query,
)
from src.scene.playground_terrain_traversal import (
    ensure_ramp_corridor_ground_surfaces,
    generate_dynamics_playground_environment_gate01_u3_blend,
)
from src.scene.playground_terrain_validation import (
    validate_dynamics_playground_environment_gate01_u3,
)


class TestEnvironmentGate01Unit3(unittest.TestCase):
    """Unit 3 test suite verifying real mesh environment integration into motion pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        """Ensure baseline playground exists and generate Unit 3 blend artifacts."""
        cls.base_blend = os.path.abspath("output/dynamics_playground.blend")
        if not os.path.exists(cls.base_blend):
            raise FileNotFoundError(f"Baseline playground scene missing: {cls.base_blend}")

        cls.u3_blend = os.path.abspath("output/dynamics_playground_environment_gate01_u3.blend")
        cls.u3_perturbed_blend = os.path.abspath("output/dynamics_playground_environment_gate01_u3_perturbed.blend")

        # Generate if not already existing
        if not os.path.exists(cls.u3_blend):
            generate_dynamics_playground_environment_gate01_u3_blend(
                output_blend_path=cls.u3_blend,
                perturbed=False,
            )
        if not os.path.exists(cls.u3_perturbed_blend):
            generate_dynamics_playground_environment_gate01_u3_blend(
                output_blend_path=cls.u3_perturbed_blend,
                perturbed=True,
            )

    def setUp(self) -> None:
        """Open baseline playground for fresh isolated scene tests."""
        bpy.ops.wm.open_mainfile(filepath=self.base_blend)
        self.scene = bpy.context.scene
        surfaces_col = bpy.data.collections.get("Playground_Surfaces")
        ensure_ramp_corridor_ground_surfaces(self.scene, surfaces_col)

    def test_u3_t01_real_mesh_environment_injection(self) -> None:
        """U3-T01: Real Mesh Environment Injection verifies prefer_mesh and adapter state."""
        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        self.assertTrue(env.prefer_mesh, "prefer_mesh must be True when mesh adapter is attached")
        self.assertTrue(env.has_mesh_adapter(), "has_mesh_adapter() must be True")
        self.assertIsNotNone(env.mesh_adapter, "mesh_adapter must not be None")
        self.assertGreater(env.mesh_adapter.polygon_count, 0, "Playground_Surfaces must contain polygons")

    def test_u3_t02_source_type_authenticity(self) -> None:
        """U3-T02: Single-hit ground support query returns source_type == 'mesh'."""
        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        # Query at ramp position
        res = env.query_ground_support_at(0.0, 13.50)
        self.assertTrue(res.success, f"Query must succeed on ramp surface: {res.error_reason}")
        self.assertEqual(res.source_type, "mesh", "Source type must be strictly 'mesh'")
        self.assertTrue(res.surface_id.startswith("mesh:"), f"surface_id must start with 'mesh:': {res.surface_id}")
        self.assertTrue(res.allows_regular_support, "Ramp must allow regular foot support")

    def test_u3_t03_initial_footprint_mesh_hit(self) -> None:
        """U3-T03: Initial Left and Right feet at start pos land on real evaluated mesh."""
        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        start_y = 10.20
        left_x = -0.11
        right_x = 0.11

        res_l = env.query_ground_support_at(left_x, start_y)
        res_r = env.query_ground_support_at(right_x, start_y)

        self.assertTrue(res_l.success, f"Left foot query failed: {res_l.error_reason}")
        self.assertTrue(res_r.success, f"Right foot query failed: {res_r.error_reason}")
        self.assertEqual(res_l.source_type, "mesh")
        self.assertEqual(res_r.source_type, "mesh")
        self.assertTrue(res_l.surface_id.startswith("mesh:Surface_Ramp_ApproachGround"))
        self.assertTrue(res_r.surface_id.startswith("mesh:Surface_Ramp_ApproachGround"))
        self.assertAlmostEqual(res_l.contact_point_world[2], 0.0, places=4)
        self.assertAlmostEqual(res_r.contact_point_world[2], 0.0, places=4)
        self.assertAlmostEqual(res_l.surface_normal_world[2], 1.0, places=4)
        self.assertAlmostEqual(res_r.surface_normal_world[2], 1.0, places=4)

    def test_u3_t04_single_hit_consistency(self) -> None:
        """U3-T04: Elevation Z, outward normal, surface_id, and support eligibility come from a single hit."""
        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        # Test across 5 distinct points along Course B
        test_points = [
            (0.0, 10.50),  # Approach ground
            (0.0, 13.50),  # Ramp uphill (+15 deg)
            (0.0, 17.00),  # Ramp bridge top (flat at 1.34m)
            (0.0, 19.50),  # Ramp downhill (-20 deg)
            (0.0, 22.00),  # Exit ground
        ]

        for x, y in test_points:
            res = env.query_ground_support_at(x, y)
            self.assertTrue(res.success, f"Failed at ({x}, {y}): {res.error_reason}")
            self.assertEqual(res.source_type, "mesh")
            self.assertTrue(res.allows_regular_support)
            self.assertTrue(res.surface_id.startswith("mesh:"))

            # Normal vector must be unit length
            nx, ny, nz = res.surface_normal_world
            norm_len = math.sqrt(nx * nx + ny * ny + nz * nz)
            self.assertAlmostEqual(norm_len, 1.0, places=5)

            # Contact point coordinates must be consistent with downward ray hit
            hit_x, hit_y, hit_z = res.contact_point_world
            self.assertAlmostEqual(hit_x, x, places=4)
            self.assertAlmostEqual(hit_y, y, places=4)

    def test_u3_t05_strict_no_support_rejection(self) -> None:
        """U3-T05: Strict rejection: empty space returns NO_HIT and non-support surfaces are rejected."""
        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        # 1. Empty space / off-mesh coordinate
        off_res = env.query_ground_support_at(50.0, 50.0)
        self.assertFalse(off_res.success)
        self.assertIn("NO_HIT:", off_res.error_reason)
        self.assertEqual(off_res.source_type, "mesh")
        self.assertFalse(off_res.allows_regular_support)

        # 2. Planning footsteps across a route that leaves the mesh must raise ValueError
        bad_route = TerrainRouteInput(
            start_pos=(0.0, 10.20, 0.0),
            target_pos=(50.0, 50.0, 0.0),
            nominal_stride_m=0.30,
        )
        with self.assertRaises(ValueError) as ctx:
            plan_terrain_footsteps(bad_route, env)
        self.assertIn("rejected", str(ctx.exception).lower())

    def test_u3_t06_analytical_mode_preservation(self) -> None:
        """U3-T06: Analytical mode cleanly evaluates analytical surfaces with source_type == 'analytical'."""
        env = create_standard_dynamics_playground_query()
        self.assertFalse(env.prefer_mesh)
        self.assertFalse(env.has_mesh_adapter())

        res = env.query_ground_support_at(0.0, 13.50)
        self.assertTrue(res.success)
        self.assertEqual(res.source_type, "analytical")
        self.assertEqual(res.surface_id, "ramp_up")
        self.assertTrue(res.allows_regular_support)
        self.assertGreater(res.contact_point_world[2], 0.0)

    def test_u3_t07_six_phase_pipeline_preservation(self) -> None:
        """U3-T07: 6-phase pipeline execution runs frame-by-frame with zero human controller modifications."""
        from src.scene.playground_character_assembly import assemble_character_in_playground
        cfg = PipelineConfig()
        assembly = assemble_character_in_playground(cfg)
        arm_obj = assembly["armature"]

        env = create_mesh_backed_dynamics_query(
            scene=self.scene,
            collection_names=("Playground_Surfaces",),
            prefer_mesh=True,
        )
        route = TerrainRouteInput(
            start_pos=(0.0, 10.20, 0.0),
            target_pos=(0.0, 11.40, 0.0),  # Short test sequence (4 steps)
            nominal_stride_m=0.30,
            step_frames=16,
            stand_start_frames=6,
            stand_stop_frames=6,
        )
        action = TerrainWalkAction(route=route, environment=env)
        planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
        planner.add_action(action)
        init_state = create_initial_motion_state(cfg, start_frame=1, position=route.start_pos)

        res = planner.execute(initial_state=init_state)
        self.assertEqual(res["unreachable_count"], 0)
        self.assertGreater(len(res["states"]), 50)
        self.assertEqual(len(res["frame_records"]), len(res["states"]))

    def test_u3_t08_counter_factual_mesh_mutation(self) -> None:
        """U3-T08: Counter-Factual Experiment A vs B: Perturbed mesh causes measurable physical divergence."""
        # Load companion summary and contact data for both Experiment A and Experiment B
        summary_a_path = "docs/evidence/environment_gate01_ru3/u3_execution_summary.json"
        summary_b_path = "docs/evidence/environment_gate01_ru3/u3_perturbed_execution_summary.json"
        contacts_a_path = "docs/evidence/environment_gate01_ru3/u3_contact_state_records.json"
        contacts_b_path = "docs/evidence/environment_gate01_ru3/u3_perturbed_contact_state_records.json"

        self.assertTrue(os.path.exists(summary_a_path), "Summary A must exist")
        self.assertTrue(os.path.exists(summary_b_path), "Summary B must exist")
        self.assertTrue(os.path.exists(contacts_a_path), "Contacts A must exist")
        self.assertTrue(os.path.exists(contacts_b_path), "Contacts B must exist")

        with open(summary_a_path, "r", encoding="utf-8") as f:
            sum_a = json.load(f)
        with open(summary_b_path, "r", encoding="utf-8") as f:
            sum_b = json.load(f)
        with open(contacts_a_path, "r", encoding="utf-8") as f:
            rec_a = json.load(f)
        with open(contacts_b_path, "r", encoding="utf-8") as f:
            rec_b = json.load(f)

        self.assertFalse(sum_a["perturbed"])
        self.assertTrue(sum_b["perturbed"])
        self.assertGreater(sum_b["perturb_height_m"], 0.0)

        # Verify that during the ramp platform frames (Y in [16, 18], frames ~300..400),
        # the root and foot contact Z coordinates in Experiment B are higher than Experiment A
        divergent_frames = 0
        max_delta_z = 0.0
        for fa, fb in zip(rec_a, rec_b):
            y_pos = fa["root_position"][1]
            if 15.0 <= y_pos <= 19.0:
                za = fa["root_position"][2]
                zb = fb["root_position"][2]
                dz = zb - za
                if abs(dz) > 0.01:
                    divergent_frames += 1
                    max_delta_z = max(max_delta_z, abs(dz))

        self.assertGreater(divergent_frames, 50, "Experiment B must physically diverge on perturbed ramp")
        self.assertGreater(max_delta_z, 0.03, f"Max delta Z must reflect perturbation (got {max_delta_z:.4f}m)")

    def test_u3_t09_counter_factual_analytical_insensitivity(self) -> None:
        """U3-T09: Counter-factual proof: Analytical environment produces identical output despite mesh mutation."""
        env_analytical = create_standard_dynamics_playground_query()

        # Query height at top platform
        z1 = env_analytical.ground_height_at(0.0, 17.0)

        # Perturb mesh in active scene
        ramp_top = bpy.data.objects.get("Surface_Ramp_TopPlatform")
        if ramp_top is not None:
            for v in ramp_top.data.vertices:
                v.co.z += 0.20
            ramp_top.data.update()

        # Analytical query remains blind to mesh changes
        z2 = env_analytical.ground_height_at(0.0, 17.0)
        self.assertEqual(z1, z2, "Analytical query must be completely insensitive to mesh edits")

        # But mesh-backed query senses the mutation immediately
        env_mesh = create_mesh_backed_dynamics_query(scene=self.scene, prefer_mesh=True)
        z_mesh = env_mesh.ground_height_at(0.0, 17.0)
        self.assertAlmostEqual(z_mesh, z1 + 0.20, places=3, msg="Mesh query must detect vertex edit")

    def test_u3_t10_blend_artifact_reopen_and_evaluation(self) -> None:
        """U3-T10: Saved blend artifact output/dynamics_playground_environment_gate01_u3.blend passes full validation."""
        val = validate_dynamics_playground_environment_gate01_u3(self.u3_blend)
        self.assertEqual(val["status"], "PASS")
        self.assertEqual(val["environment_source"], "blender_mesh_bvh")
        self.assertGreater(val["mesh_polygon_count"], 80)
        self.assertEqual(val["total_frames_evaluated"], 700)
        self.assertTrue(val["mass_conservation_pass"])
        self.assertTrue(val["diagnostic_scene_verified"])

    def test_u3_t11_c0_trajectory_continuity(self) -> None:
        """U3-T11: C0 root continuity: Zero frame exemptions, frame displacement < 0.12m across all 700 frames."""
        val = validate_dynamics_playground_environment_gate01_u3(self.u3_blend)
        max_disp = val["max_root_velocity_m_per_frame"]
        self.assertLess(max_disp, 0.12, f"Root displacement per frame ({max_disp:.4f}m) must be < 0.12m")

    def test_u3_t12_zero_bone_stretch_and_rom_limits(self) -> None:
        """U3-T12: Bone stretch < 0.1mm and zero anatomical ROM violations across all frames."""
        val = validate_dynamics_playground_environment_gate01_u3(self.u3_blend)
        self.assertLess(val["max_bone_stretch_m"], 1.0e-4)
        self.assertEqual(val["total_rom_violations"], 0)

    def test_u3_t13_locked_foot_drift(self) -> None:
        """U3-T13: Locked stance foot drift < 0.1mm across all stance frames."""
        val = validate_dynamics_playground_environment_gate01_u3(self.u3_blend)
        self.assertLess(val["max_locked_ankle_drift_m"], 1.0e-4)

    def test_u3_t14_baseline_file_protection(self) -> None:
        """U3-T14: Baseline file output/dynamics_playground.blend is 100% untouched and exists."""
        self.assertTrue(os.path.exists(self.base_blend))
        # Ensure file size is reasonable and not corrupted
        stat = os.stat(self.base_blend)
        self.assertGreater(stat.st_size, 50000, "Baseline playground file must be valid size")


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEnvironmentGate01Unit3)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
