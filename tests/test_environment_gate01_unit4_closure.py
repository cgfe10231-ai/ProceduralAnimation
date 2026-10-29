"""ProceduralAnimation — Environment Gate 01 / Unit 4 Final Closure Test Suite.

Verifies the final two contact contract verification gaps:
- U4-CLOSE-01: When success=True but allows_regular_support=False, no valid foot support must be established.
- U4-CLOSE-02: In real Mesh mode without valid support, no fake contact must be synthesized from default analytical ground.
  - Case A: Empty Mesh collection
  - Case B: Foot not on any support surface (void / no mesh under foot)
  - Case C: Hitting non-support surface (allows_regular_support=False)
  - Case D: Both feet have no valid support (full contact state check)
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
from src.scene.environment_query import DynamicsEnvironmentQuery
from src.scene.playground_terrain_traversal import create_standard_dynamics_playground_query


class MockNonSupportEnvironment:
    """Controlled environment returning success=True, allows_regular_support=False."""

    def __init__(self, surface_id: str = "mesh:non_support_surface", surface_type: str = "wall"):
        self.surface_id = surface_id
        self.surface_type = surface_type
        self.query_log: List[Tuple[float, float]] = []

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        self.query_log.append((x, y))
        return SurfaceQueryResult(
            surface_id=self.surface_id,
            surface_type=self.surface_type,
            contact_point_world=(x, y, 1.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.5,
            allows_regular_support=False,
            success=True,
            source_type="mesh",
            error_reason=f"NON_SUPPORT_SURFACE: surface '{self.surface_id}' does not allow regular support",
        )


class MockVoidEnvironment:
    """Controlled environment returning failure (no mesh / void)."""

    def __init__(self):
        self.query_log: List[Tuple[float, float]] = []

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
        self.query_log.append((x, y))
        return SurfaceQueryResult(
            surface_id="none",
            surface_type="none",
            contact_point_world=(x, y, 0.0),
            surface_normal_world=(0.0, 0.0, 1.0),
            signed_distance=0.0,
            friction_coeff=0.0,
            allows_regular_support=False,
            success=False,
            source_type="mesh",
            error_reason=f"NO_HIT: ray from ({x:.2f}, {y:.2f}, {start_z:.2f}) did not intersect any support surface",
        )


class TestEnvironmentGate01Unit4Closure(unittest.TestCase):
    """Test suite for Environment Gate 01 / Unit 4 Final Closure."""

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

    def test_u4_close_01_non_support_surface_rejected(self) -> None:
        """U4-CLOSE-01: When success=True but allows_regular_support=False, no valid foot support must be established."""
        env = MockNonSupportEnvironment(surface_id="mesh:non_support_surface", surface_type="wall")
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 0.0, 1.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 0.0, 1.0 + ANKLE_REST_Z),
                is_locked=True,
                surface_id="mesh:non_support_surface",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 0.0, 1.0 + ANKLE_REST_Z),
                is_locked=True,
                surface_id="mesh:non_support_surface",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)

        # 1. Execution must NOT be considered successful
        self.assertFalse(
            result.success,
            "Execution must fail when locked foot targets a non-support surface",
        )

        # 2. Geometry errors must be reported for the locked feet
        self.assertIn("foot_L", result.contact_geometry_errors, "foot_L must be flagged with contact geometry error")
        self.assertIn("foot_R", result.contact_geometry_errors, "foot_R must be flagged with contact geometry error")

        # 3. Active contacts must NOT contain the non-support foot
        multi = bridge.last_multi_contact
        self.assertIsNotNone(multi, "MultiContactState must exist")
        self.assertNotIn("foot_L", multi.active_contacts, "foot_L must NOT be an active established contact")
        self.assertNotIn("foot_R", multi.active_contacts, "foot_R must NOT be an active established contact")

        # 4. Support type must NOT be DOUBLE_STANCE
        self.assertNotEqual(
            multi.support_type,
            SupportType.DOUBLE_STANCE,
            "Must NOT report DOUBLE_STANCE on non-support surfaces",
        )
        self.assertEqual(
            multi.support_type,
            SupportType.FLIGHT,
            "Support type must be FLIGHT when neither foot has regular support",
        )

        # 5. Lifecycle of contacts must be BROKEN
        self.assertEqual(
            multi.contacts["foot_L"].lifecycle,
            ContactLifecycle.BROKEN,
            "Contact lifecycle must be BROKEN on non-support surface",
        )
        self.assertEqual(
            multi.contacts["foot_R"].lifecycle,
            ContactLifecycle.BROKEN,
            "Contact lifecycle must be BROKEN on non-support surface",
        )

    def test_u4_close_02_case_a_empty_mesh_collection(self) -> None:
        """U4-CLOSE-02 Case A: Real Mesh adapter connected with empty mesh collection."""
        from src.scene.blender_mesh_query_adapter import BlenderMeshEnvironmentAdapter
        adapter = BlenderMeshEnvironmentAdapter(collection_names=["NonExistentEmptyCollection"])
        env = DynamicsEnvironmentQuery(mesh_adapter=adapter, prefer_mesh=True)
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 0.0, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 0.0, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 0.0, ANKLE_REST_Z),
                is_locked=False,
                surface_id="free",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)

        # Execution must fail
        self.assertFalse(result.success, "Must fail when querying empty mesh collection")
        self.assertIn("foot_L", result.contact_geometry_errors)

        # Must not establish contact
        multi = bridge.last_multi_contact
        self.assertNotIn("foot_L", multi.active_contacts)
        self.assertEqual(multi.contacts["foot_L"].lifecycle, ContactLifecycle.BROKEN)
        self.assertNotEqual(multi.contacts["foot_L"].surface_id, "ground", "Must not assign fake ground surface_id")
        self.assertEqual(multi.contacts["foot_L"].surface_id, "none")
        self.assertEqual(multi.support_type, SupportType.FLIGHT)

    def test_u4_close_02_case_b_foot_outside_support_surface(self) -> None:
        """U4-CLOSE-02 Case B: Environment has meshes, but foot is outside (over void)."""
        env = MockVoidEnvironment()
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, -100.0, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, -100.0, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, -100.0, ANKLE_REST_Z),
                is_locked=False,
                surface_id="free",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)

        self.assertFalse(result.success, "Must fail when foot is over void")
        self.assertIn("foot_L", result.contact_geometry_errors)

        multi = bridge.last_multi_contact
        self.assertNotIn("foot_L", multi.active_contacts)
        self.assertEqual(multi.contacts["foot_L"].lifecycle, ContactLifecycle.BROKEN)
        self.assertEqual(multi.contacts["foot_L"].surface_id, "none")
        self.assertEqual(multi.support_type, SupportType.FLIGHT)

    def test_u4_close_02_case_c_hitting_non_support_mesh(self) -> None:
        """U4-CLOSE-02 Case C: Mesh is hit, but allows_regular_support=False."""
        env = MockNonSupportEnvironment(surface_id="mesh:barrier_wall", surface_type="obstacle")
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 5.0, 0.5),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 5.0, 0.5 + ANKLE_REST_Z),
                is_locked=True,
                surface_id="mesh:barrier_wall",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 5.0, 0.5 + ANKLE_REST_Z),
                is_locked=False,
                surface_id="free",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)

        self.assertFalse(result.success, "Must fail when foot hits non-support mesh")
        self.assertIn("foot_L", result.contact_geometry_errors)

        multi = bridge.last_multi_contact
        self.assertNotIn("foot_L", multi.active_contacts)
        self.assertEqual(multi.contacts["foot_L"].lifecycle, ContactLifecycle.BROKEN)
        self.assertEqual(multi.contacts["foot_L"].surface_id, "none")
        self.assertEqual(multi.support_type, SupportType.FLIGHT)

    def test_u4_close_02_case_d_both_feet_no_support(self) -> None:
        """U4-CLOSE-02 Case D: Both feet locked, but neither has valid support."""
        env = MockVoidEnvironment()
        bridge = KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=env,
        )

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, 0.0, 0.0),
            foot_L=PlannedFootTarget(
                world_xyz=(-0.11, 0.0, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
            foot_R=PlannedFootTarget(
                world_xyz=(0.11, 0.0, ANKLE_REST_Z),
                is_locked=True,
                surface_id="ground",
            ),
        )

        result = bridge.execute_frame(planned, keyframe=False)

        self.assertFalse(result.success)
        self.assertEqual(len(result.contact_geometry_errors), 2)
        self.assertIn("foot_L", result.contact_geometry_errors)
        self.assertIn("foot_R", result.contact_geometry_errors)

        multi = bridge.last_multi_contact
        self.assertEqual(len(multi.active_contacts), 0, "No active contacts when both queries fail")
        self.assertEqual(multi.support_type, SupportType.FLIGHT, "Support type must be FLIGHT, not DOUBLE_STANCE")
        self.assertEqual(multi.contacts["foot_L"].lifecycle, ContactLifecycle.BROKEN)
        self.assertEqual(multi.contacts["foot_R"].lifecycle, ContactLifecycle.BROKEN)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
