"""ProceduralAnimation — Environment Gate 01 / Repair Unit 4 Test Suite.

Verifies Real Mesh Contact Elevation, Geometric Compliance, and Surface Consistency:
- U4-T01: Flat Ground Contact: Z=0.0m, normal=(0, 0, 1), surface_id='ground', valid compliance.
- U4-T02: 15° Uphill Ramp Contact: Authentic ramp elevation and sloped surface normal.
- U4-T03: Top Platform Contact: Authentic elevation (1.3397m), normal=(0, 0, 1), surface_id='ramp_top_platform'.
- U4-T04: 20° Downhill Ramp Contact: Authentic downhill elevation and sloped surface normal.
- U4-T05: Alternating Stance & Swing Decoupling: Strict single-stance support type and released swing foot.
- U4-T06: Failed Query Truthfulness: When environment returns no support, no fake Z=0 is generated.
- U4-T07: Counter-Factual Experiment A: Mesh elevation shift (+0.05m) yields exact +0.05m contact Z shift.
- U4-T08: Counter-Factual Experiment B: Slope angle variation yields matching surface normal variation.
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
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.contact_model import (
    ContactLifecycle,
    ContactType,
    SupportType,
)
from src.motion.framework import EnvironmentQuery, SurfaceQueryResult
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, setup_leg_ik
from src.scene.playground_terrain_traversal import create_standard_dynamics_playground_query


class TestEnvironmentGate01Unit4(unittest.TestCase):
    """Test suite for Environment Gate 01 / Unit 4: Real Mesh Contact Elevation & Consistency."""

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
        cls.env = create_standard_dynamics_playground_query()

    def test_u4_t01_flat_ground_contact(self) -> None:
        """T01: Flat ground contact preserves Z=0.0m, normal=(0, 0, 1), and valid compliance."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        flat_y = 10.2
        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, flat_y, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, flat_y, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, flat_y, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(result.success, "Flat ground contact execution must succeed")
        self.assertEqual(len(result.contact_geometry_errors), 0, "Zero contact geometry errors on flat ground")

        # Telemetry verification
        c_l = result.motion_state.contacts.get("foot_l") or result.motion_state.contacts.get("foot_L")
        self.assertAlmostEqual(c_l.contact_world_xyz[2], 0.0, places=4)
        self.assertAlmostEqual(c_l.surface_normal[0], 0.0, places=4)
        self.assertAlmostEqual(c_l.surface_normal[1], 0.0, places=4)
        self.assertAlmostEqual(c_l.surface_normal[2], 1.0, places=4)

        rec_l = bridge.last_multi_contact.contacts["foot_L"]
        self.assertTrue(rec_l.is_active)
        self.assertEqual(rec_l.lifecycle, ContactLifecycle.ESTABLISHED)
        self.assertEqual(bridge.last_multi_contact.support_type, SupportType.DOUBLE_STANCE)

    def test_u4_t02_15deg_ramp_contact(self) -> None:
        """T02: 15° uphill ramp contact records authentic ramp elevation and inclined normal."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        ramp_y = 12.5
        q_ramp = self.env.query_ground_support_at(0.0, ramp_y)
        self.assertTrue(q_ramp.success)
        z_ramp = q_ramp.contact_point_world[2]
        n_ramp = q_ramp.surface_normal_world

        planned = KinematicPlannedPose(
            frame=2,
            time_seconds=0.0833,
            root_position=(0.0, ramp_y, z_ramp),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, ramp_y, z_ramp + ANKLE_REST_Z),
                is_locked=True,
                rotation_deg=(15.0, 0.0, 0.0),
                surface_id=q_ramp.surface_id,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, ramp_y, z_ramp + ANKLE_REST_Z),
                is_locked=True,
                rotation_deg=(15.0, 0.0, 0.0),
                surface_id=q_ramp.surface_id,
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(result.success, "15° ramp contact execution must succeed")
        self.assertEqual(len(result.contact_geometry_errors), 0)

        c_l = result.motion_state.contacts.get("foot_l") or result.motion_state.contacts.get("foot_L")
        # Query ground support at the evaluated foot contact XY
        q_actual = self.env.query_ground_support_at(c_l.contact_world_xyz[0], c_l.contact_world_xyz[1])
        self.assertAlmostEqual(c_l.contact_world_xyz[2], q_actual.contact_point_world[2], places=4)
        # Normal must have uphill incline (ny < 0)
        self.assertLess(c_l.surface_normal[1], -0.20)
        self.assertAlmostEqual((Vector(c_l.surface_normal) - Vector(n_ramp)).length, 0.0, places=3)

    def test_u4_t03_platform_contact(self) -> None:
        """T03: Top platform contact records authentic platform elevation (1.3397m) and surface ID."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        platform_y = 17.0
        q_plat = self.env.query_ground_support_at(0.0, platform_y)
        self.assertTrue(q_plat.success)
        elevated_z = q_plat.contact_point_world[2]
        self.assertAlmostEqual(elevated_z, 1.339746, places=3)

        planned = KinematicPlannedPose(
            frame=3,
            time_seconds=0.1250,
            root_position=(0.0, platform_y, elevated_z),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, platform_y, elevated_z + ANKLE_REST_Z),
                is_locked=True,
                surface_id=q_plat.surface_id,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, platform_y, elevated_z + ANKLE_REST_Z),
                is_locked=True,
                surface_id=q_plat.surface_id,
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(result.success)
        self.assertEqual(len(result.contact_geometry_errors), 0)

        c_l = result.motion_state.contacts.get("foot_l") or result.motion_state.contacts.get("foot_L")
        self.assertAlmostEqual(c_l.contact_world_xyz[2], elevated_z, places=4)
        self.assertAlmostEqual(c_l.surface_normal[2], 1.0, places=4)

        rec_l = bridge.last_multi_contact.contacts["foot_L"]
        self.assertAlmostEqual(rec_l.world_position[2], elevated_z, places=4)
        self.assertEqual(rec_l.surface_id, q_plat.surface_id)

    def test_u4_t04_20deg_downhill_contact(self) -> None:
        """T04: 20° downhill ramp records authentic downhill slope elevation and forward normal."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        downhill_y = 19.5
        q_down = self.env.query_ground_support_at(0.0, downhill_y)
        self.assertTrue(q_down.success)
        z_down = q_down.contact_point_world[2]
        n_down = q_down.surface_normal_world

        planned = KinematicPlannedPose(
            frame=4,
            time_seconds=0.1667,
            root_position=(0.0, downhill_y, z_down),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, downhill_y, z_down + ANKLE_REST_Z),
                is_locked=True,
                rotation_deg=(-20.0, 0.0, 0.0),
                surface_id=q_down.surface_id,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, downhill_y, z_down + ANKLE_REST_Z),
                is_locked=True,
                rotation_deg=(-20.0, 0.0, 0.0),
                surface_id=q_down.surface_id,
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(result.success)
        self.assertEqual(len(result.contact_geometry_errors), 0)

        c_l = result.motion_state.contacts.get("foot_l") or result.motion_state.contacts.get("foot_L")
        q_actual = self.env.query_ground_support_at(c_l.contact_world_xyz[0], c_l.contact_world_xyz[1])
        self.assertAlmostEqual(c_l.contact_world_xyz[2], q_actual.contact_point_world[2], places=4)
        # Downhill normal must have forward component (ny > 0)
        self.assertGreater(c_l.surface_normal[1], 0.25)
        self.assertAlmostEqual((Vector(c_l.surface_normal) - Vector(n_down)).length, 0.0, places=3)

    def test_u4_t05_alternating_stance_swing_decoupling(self) -> None:
        """T05: Alternating steps decouple stance support from swing flight with correct SupportType."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        # Step 1: Left foot stance, Right foot swing
        p1 = KinematicPlannedPose(
            frame=10,
            time_seconds=0.417,
            root_position=(0.0, 10.5, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 10.5, ANKLE_REST_Z),
                is_locked=True,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 10.7, ANKLE_REST_Z + 0.08),
                is_locked=False,
                contact_intent=False,
            ),
        )
        res1 = bridge.execute_frame(p1, keyframe=False)
        self.assertTrue(res1.success)
        mc1 = bridge.last_multi_contact
        self.assertTrue(mc1.contacts["foot_L"].is_active)
        self.assertFalse(mc1.contacts["foot_R"].is_active)
        self.assertEqual(mc1.contacts["foot_R"].lifecycle, ContactLifecycle.RELEASED)
        self.assertEqual(mc1.support_type, SupportType.SINGLE_STANCE_L)
        self.assertNotIn("foot_R", res1.contact_geometry_errors)

        # Step 2: Right foot stance, Left foot swing
        p2 = KinematicPlannedPose(
            frame=26,
            time_seconds=1.083,
            root_position=(0.0, 11.0, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 11.2, ANKLE_REST_Z + 0.08),
                is_locked=False,
                contact_intent=False,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 11.0, ANKLE_REST_Z),
                is_locked=True,
            ),
        )
        res2 = bridge.execute_frame(p2, keyframe=False)
        self.assertTrue(res2.success)
        mc2 = bridge.last_multi_contact
        self.assertFalse(mc2.contacts["foot_L"].is_active)
        self.assertTrue(mc2.contacts["foot_R"].is_active)
        self.assertEqual(mc2.contacts["foot_L"].lifecycle, ContactLifecycle.RELEASED)
        self.assertEqual(mc2.support_type, SupportType.SINGLE_STANCE_R)
        self.assertNotIn("foot_L", res2.contact_geometry_errors)

    def test_u4_t06_failed_query_truthfulness_no_fake_ground(self) -> None:
        """T06: When environment query fails, bridge records truthful failure without faking Z=0.0m."""
        class MockVoidEnvironmentQuery(EnvironmentQuery):
            def query_ground_support_at(self, x: float, y: float, **kwargs) -> SurfaceQueryResult:
                return SurfaceQueryResult(
                    surface_id="none",
                    surface_type="none",
                    contact_point_world=(x, y, -999.0),
                    surface_normal_world=(0.0, 0.0, 1.0),
                    signed_distance=float("inf"),
                    friction_coeff=0.0,
                    allows_regular_support=False,
                    success=False,
                    ray_hit_distance=float("inf"),
                    error_reason="NO_HIT: Void space (no support mesh)",
                    source_type="mock",
                )

        void_env = MockVoidEnvironmentQuery()
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=void_env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 17.0, 1.34),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 17.0, 1.34 + ANKLE_REST_Z),
                is_locked=True,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 17.0, 1.34 + ANKLE_REST_Z),
                is_locked=True,
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)
        # Truthful failure: Must fail and report broken contact without faking Z=0
        self.assertFalse(result.success, "Execution over void must fail")
        self.assertIn("foot_L", result.contact_geometry_errors)
        geom_err = result.contact_geometry_errors["foot_L"]
        self.assertFalse(geom_err.is_valid)
        self.assertIn("NO_SUPPORT_SURFACE", geom_err.violation_reason)
        # Assert contact was NOT faked as established on Z=0
        rec_l = bridge.last_multi_contact.contacts["foot_L"]
        self.assertNotEqual(rec_l.lifecycle, ContactLifecycle.ESTABLISHED)
        self.assertEqual(rec_l.surface_id, "none")

    def test_u4_t07_counterfactual_experiment_a_elevation_variation(self) -> None:
        """T07: Counter-Factual A: Platform elevation shift (+0.05m) produces exact +0.05m contact Z shift."""
        # Baseline execution at 1.339746m
        bridge_base = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )
        base_z = 1.339746
        p_base = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 17.0, base_z),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, 17.0, base_z + ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, 17.0, base_z + ANKLE_REST_Z), is_locked=True),
        )
        res_base = bridge_base.execute_frame(p_base, keyframe=False)
        z0 = res_base.motion_state.contacts["foot_L"].contact_world_xyz[2]

        # Variant environment with +0.05m shift
        delta_z = 0.050
        class VariantShiftedPlatformQuery(EnvironmentQuery):
            def __init__(self, base_query: EnvironmentQuery, delta: float) -> None:
                self.base = base_query
                self.delta = delta

            def query_ground_support_at(self, x: float, y: float, **kwargs) -> SurfaceQueryResult:
                res = self.base.query_ground_support_at(x, y, **kwargs)
                if not res.success:
                    return res
                new_pt = (res.contact_point_world[0], res.contact_point_world[1], res.contact_point_world[2] + self.delta)
                return SurfaceQueryResult(
                    surface_id=res.surface_id,
                    surface_type=res.surface_type,
                    contact_point_world=new_pt,
                    surface_normal_world=res.surface_normal_world,
                    signed_distance=res.signed_distance,
                    friction_coeff=res.friction_coeff,
                    allows_regular_support=res.allows_regular_support,
                    success=res.success,
                    ray_hit_distance=res.ray_hit_distance - self.delta,
                    error_reason=res.error_reason,
                    source_type=res.source_type,
                )

        variant_env = VariantShiftedPlatformQuery(self.env, delta=delta_z)
        bridge_var = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=variant_env,
        )
        var_z = base_z + delta_z
        p_var = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 17.0, var_z),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, 17.0, var_z + ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, 17.0, var_z + ANKLE_REST_Z), is_locked=True),
        )
        res_var = bridge_var.execute_frame(p_var, keyframe=False)
        z_variant = res_var.motion_state.contacts["foot_L"].contact_world_xyz[2]

        measured_delta = z_variant - z0
        self.assertAlmostEqual(measured_delta, delta_z, places=4, msg="Recorded contact Z must shift by exactly +0.05m")

    def test_u4_t08_counterfactual_experiment_b_slope_normal_variation(self) -> None:
        """T08: Counter-Factual B: Slope normal modification yields exact corresponding contact normal."""
        # Baseline normal on ramp
        bridge_base = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )
        q_base = self.env.query_ground_support_at(0.0, 12.5)
        p_base = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 12.5, q_base.contact_point_world[2]),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, 12.5, q_base.contact_point_world[2] + ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, 12.5, q_base.contact_point_world[2] + ANKLE_REST_Z), is_locked=True),
        )
        res_base = bridge_base.execute_frame(p_base, keyframe=False)
        norm_0 = res_base.motion_state.contacts["foot_L"].surface_normal

        # Variant environment with 30° slope normal instead of 15°
        target_variant_normal = (0.0, -math.sin(math.radians(30.0)), math.cos(math.radians(30.0)))
        class VariantSlopeNormalQuery(EnvironmentQuery):
            def __init__(self, base_query: EnvironmentQuery, var_normal: Tuple[float, float, float]) -> None:
                self.base = base_query
                self.var_normal = var_normal

            def query_ground_support_at(self, x: float, y: float, **kwargs) -> SurfaceQueryResult:
                res = self.base.query_ground_support_at(x, y, **kwargs)
                return SurfaceQueryResult(
                    surface_id=res.surface_id,
                    surface_type=res.surface_type,
                    contact_point_world=res.contact_point_world,
                    surface_normal_world=self.var_normal,
                    signed_distance=res.signed_distance,
                    friction_coeff=res.friction_coeff,
                    allows_regular_support=res.allows_regular_support,
                    success=res.success,
                    ray_hit_distance=res.ray_hit_distance,
                    error_reason=res.error_reason,
                    source_type=res.source_type,
                )

        variant_env = VariantSlopeNormalQuery(self.env, var_normal=target_variant_normal)
        bridge_var = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=variant_env,
        )
        p_var = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 12.5, q_base.contact_point_world[2]),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, 12.5, q_base.contact_point_world[2] + ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, 12.5, q_base.contact_point_world[2] + ANKLE_REST_Z), is_locked=True),
        )
        res_var = bridge_var.execute_frame(p_var, keyframe=False)
        norm_var = res_var.motion_state.contacts["foot_L"].surface_normal

        # Prove that normal_var matches target_variant_normal and differs from norm_0
        self.assertAlmostEqual((Vector(norm_var) - Vector(target_variant_normal)).length, 0.0, places=4)
        self.assertGreater((Vector(norm_var) - Vector(norm_0)).length, 0.10)


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEnvironmentGate01Unit4)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
