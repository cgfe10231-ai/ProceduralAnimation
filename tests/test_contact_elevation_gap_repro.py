"""Verified Post-Fix Test for KinematicBridge Foot Contact Elevation Gap & Surface Consistency.

Task: Environment Gate 01 / Repair Unit 4.
Target: `src/motion/kinematic_bridge.py` lines 390-440 & 530-580.

Fix Summary:
1. `KinematicBridgeExecutor.execute_frame()` dynamically queries `self.environment.query_ground_support_at()`
   to obtain the authentic 3D surface elevation and surface normal for locked stance feet.
2. The hardcoded `Z=0.0m` flattening is completely eliminated.
3. `EnvironmentalSurface` is populated dynamically from evaluated environment queries.
4. Body contact anchors are evaluated through the bone's world matrix with calibrated sole offset.
5. `last_multi_contact` and `last_active_limb_targets` are recorded on the executor and attached
   to `BridgeExecutionResult.multi_contact`.

This test:
1. Configures a stance contact on an elevated platform (Z = 1.3397m, e.g. Ramp Bridge Platform).
2. Executes through the real production `KinematicBridgeExecutor.execute_frame()`.
3. Asserts that `result.motion_state.contacts['foot_L'].contact_world_xyz[2]` equals the true 3D surface elevation.
4. Asserts that `bridge.last_multi_contact.contacts['foot_L'].world_position[2]` equals the true 3D surface elevation.
5. Asserts that geometric constraint checking reports valid contact with zero excessive gap.
"""

import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import unittest
import bpy
from mathutils import Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.contact_model import ContactLifecycle, ContactType
from src.motion.kinematic_bridge import (
    KinematicBridgeExecutor,
    KinematicPlannedPose,
    PlannedFootTarget,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik, ANKLE_REST_Z
from src.scene.playground_terrain_traversal import create_standard_dynamics_playground_query


class TestContactElevationGapRepro(unittest.TestCase):
    """Verify foot contact target elevation and surface consistency in KinematicBridge."""

    @classmethod
    def setUpClass(cls):
        # Reset Blender to clean state
        bpy.ops.wm.read_factory_settings(use_empty=True)
        cls.config = PipelineConfig()
        char_data = build_character(cls.config)
        cls.root = char_data["root"]
        cls.parts = char_data["parts"]
        cls.armature = build_rig(cls.config)
        bind_character_to_rig(cls.armature, cls.parts)
        setup_leg_ik(cls.armature)
        cls.env = create_standard_dynamics_playground_query()

    def test_verify_locked_foot_elevation_preservation(self):
        """Verify that locked foot contact targets preserve authentic 3D mesh surface elevation."""
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

        elevated_z = 1.339746  # Exact elevation of Dynamics Playground Bridge Platform
        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 17.0, elevated_z),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 17.0, elevated_z + ANKLE_REST_Z),
                is_locked=True,
                surface_id="ramp_top_platform",
                contact_intent=True,
                contact_type=ContactType.UNILATERAL,
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 17.0, elevated_z + ANKLE_REST_Z),
                is_locked=True,
                surface_id="ramp_top_platform",
                contact_intent=True,
                contact_type=ContactType.UNILATERAL,
            ),
        )

        # Execute bridge frame through real production pipeline
        result = bridge.execute_frame(planned, keyframe=False)

        # 1. Verify MotionState legacy contact telemetry
        contact_l = result.motion_state.contacts.get("foot_l") or result.motion_state.contacts.get("foot_L")
        self.assertIsNotNone(contact_l, "foot_L missing from motion_state.contacts")
        recorded_ms_z = contact_l.contact_world_xyz[2]

        # 2. Verify MultiContactState telemetry on bridge executor and execution result
        self.assertIsNotNone(bridge.last_multi_contact, "bridge.last_multi_contact was not recorded")
        self.assertIsNotNone(result.multi_contact, "result.multi_contact was not populated")
        rec_l = bridge.last_multi_contact.contacts.get("foot_L")
        self.assertIsNotNone(rec_l, "foot_L missing from last_multi_contact.contacts")
        recorded_mc_z = rec_l.world_position[2]

        discrepancy_ms = abs(elevated_z - recorded_ms_z)
        discrepancy_mc = abs(elevated_z - recorded_mc_z)

        print("\n" + "=" * 70)
        print("CONTACT ELEVATION POST-FIX VERIFICATION EVIDENCE:")
        print(f"  True Evaluated Platform Ground Z: {elevated_z:.6f} m")
        print(f"  MotionState Recorded Contact Z:   {recorded_ms_z:.6f} m (Diff: {discrepancy_ms:.6e} m)")
        print(f"  MultiContact Recorded Target Z:   {recorded_mc_z:.6f} m (Diff: {discrepancy_mc:.6e} m)")
        print(f"  Contact Geometry Errors:          {result.contact_geometry_errors}")
        print(f"  Overall Execution Success:        {result.success}")
        print("=" * 70)

        # Assert zero flattening to 0.0m
        self.assertGreater(recorded_ms_z, 1.0, "Contact Z must not be flattened to 0.0m")
        self.assertGreater(recorded_mc_z, 1.0, "Contact Z must not be flattened to 0.0m")

        # Assert elevation agreement with evaluated surface within 1e-4m
        self.assertLess(discrepancy_ms, 1e-4, f"MotionState Z discrepancy {discrepancy_ms:.6e}m exceeds 1e-4m")
        self.assertLess(discrepancy_mc, 1e-4, f"MultiContact Z discrepancy {discrepancy_mc:.6e}m exceeds 1e-4m")

        # Assert geometric compliance
        self.assertEqual(len(result.contact_geometry_errors), 0, f"Unexpected geometric errors: {result.contact_geometry_errors}")
        self.assertTrue(result.success, "Bridge execution must succeed for valid stance foot contact on platform")


def run_tests() -> int:
    suite = unittest.TestLoader().loadTestsFromTestCase(TestContactElevationGapRepro)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
