"""ProceduralAnimation — Regression Test Suite for FIND-R2-01.

Validates hand contact lifecycle state mapping in KinematicBridgeExecutor:
- Case A: Normal reaching (enabled=True, contact_intent=False) -> ContactType.FREE, ContactLifecycle.RELEASED
- Case B: Contact candidate (enabled=True, contact_intent=True, is_locked=False, dist > 0.015m) -> ContactLifecycle.CANDIDATE (NOT TOUCHDOWN)
- Case C: Contact established (enabled=True, contact_intent=True, dist <= 0.015m) -> ContactLifecycle.ESTABLISHED
- Case D: Explicit lock (enabled=True, is_locked=True) -> ContactLifecycle.ESTABLISHED
"""

from __future__ import annotations

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
    PlannedHandTarget,
)
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import ANKLE_REST_Z, setup_leg_ik


class MockFlatGroundEnvironment:
    """Standard planar ground environment for regression testing."""

    def __init__(self, ground_z: float = 0.0):
        self.ground_z = ground_z

    def query_ground_support_at(
        self,
        x: float,
        y: float,
        start_z: float = 50.0,
        max_fall: float = 100.0,
    ) -> SurfaceQueryResult:
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


class TestFindR201HandContactLifecycle(unittest.TestCase):
    """Targeted regression test for FIND-R2-01 hand contact lifecycle."""

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
        cls.env = MockFlatGroundEnvironment(ground_z=0.0)
        # Anatomically reachable forward reaching hand pose
        cls.reach_target = (-0.24, -7.65, 1.35)

    def _create_bridge(self) -> KinematicBridgeExecutor:
        return KinematicBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
        )

    def test_case_a_hand_reaching_no_contact_intent(self) -> None:
        """Case A: Normal reaching (enabled=True, contact_intent=False)."""
        bridge = self._create_bridge()
        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, -8.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            hand_L=PlannedHandTarget(
                world_xyz=self.reach_target,
                enabled=True,
                contact_intent=False,
                is_locked=False,
            ),
        )

        res = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(res.success, f"Frame failed: {res.unmet_constraints}")
        mc = res.multi_contact
        self.assertIn("hand_L", mc.contacts)
        hand_c = mc.contacts["hand_L"]
        self.assertEqual(hand_c.contact_type, ContactType.FREE)
        self.assertEqual(hand_c.lifecycle, ContactLifecycle.RELEASED)
        self.assertNotIn("hand_L", mc.active_contacts)
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)

    def test_case_b_hand_contact_candidate(self) -> None:
        """Case B: Hand contact candidate (enabled=True, contact_intent=True, is_locked=False, dist > 0.015m)."""
        bridge = self._create_bridge()
        # In candidate phase, hand is approaching surface (weight=0.0, distance > 0.015m)
        candidate_target = (-0.24, -7.75, 1.30)

        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, -8.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            hand_L=PlannedHandTarget(
                world_xyz=candidate_target,
                enabled=True,
                contact_intent=True,
                is_locked=False,
                weight=0.0,
                surface_id="obstacle_vault",
            ),
        )

        # Before fix, this line MUST raise AttributeError: type object 'ContactLifecycle' has no attribute 'TOUCHDOWN'
        res = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(res.success, f"Frame failed: {res.unmet_constraints}")
        mc = res.multi_contact
        self.assertIn("hand_L", mc.contacts)
        hand_c = mc.contacts["hand_L"]
        self.assertEqual(hand_c.lifecycle, ContactLifecycle.CANDIDATE)
        self.assertFalse(hand_c.is_active)
        self.assertNotIn("hand_L", mc.active_contacts)
        # Candidate contact must NOT corrupt support type into hand support
        self.assertEqual(mc.support_type, SupportType.DOUBLE_STANCE)

    def test_case_c_hand_contact_established_within_threshold(self) -> None:
        """Case C: Hand reaching within contact surface threshold (dist <= 0.015m)."""
        bridge = self._create_bridge()
        # First ensure hand is at reach target
        planned_reach = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, -8.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            hand_L=PlannedHandTarget(
                world_xyz=self.reach_target,
                enabled=True,
                contact_intent=False,
                is_locked=False,
            ),
        )
        bridge.execute_frame(planned_reach, keyframe=False)

        # Contact target at reached hand position (dist <= 0.015m)
        planned_contact = KinematicPlannedPose(
            frame=2,
            time_seconds=0.0833,
            root_position=(0.0, -8.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            hand_L=PlannedHandTarget(
                world_xyz=self.reach_target,
                enabled=True,
                contact_intent=True,
                is_locked=False,
                surface_id="obstacle_vault",
            ),
        )

        res = bridge.execute_frame(planned_contact, keyframe=False)
        self.assertTrue(res.success, f"Frame failed: {res.unmet_constraints}")
        mc = res.multi_contact
        self.assertIn("hand_L", mc.contacts)
        hand_c = mc.contacts["hand_L"]
        self.assertEqual(hand_c.lifecycle, ContactLifecycle.ESTABLISHED)
        self.assertTrue(hand_c.is_active)
        self.assertIn("hand_L", mc.active_contacts)
        self.assertEqual(mc.support_type, SupportType.MULTI_SURFACE)

    def test_case_d_hand_contact_explicit_lock(self) -> None:
        """Case D: Hand explicitly locked in world space (enabled=True, is_locked=True)."""
        bridge = self._create_bridge()
        planned = KinematicPlannedPose(
            frame=1,
            time_seconds=0.0417,
            root_position=(0.0, -8.0, 0.0),
            foot_L=PlannedFootTarget(world_xyz=(-0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            foot_R=PlannedFootTarget(world_xyz=(0.11, -8.0, ANKLE_REST_Z), is_locked=True),
            hand_L=PlannedHandTarget(
                world_xyz=self.reach_target,
                enabled=True,
                is_locked=True,
                surface_id="ledge_bar",
            ),
        )

        res = bridge.execute_frame(planned, keyframe=False)
        self.assertTrue(res.success, f"Frame failed: {res.unmet_constraints}")
        mc = res.multi_contact
        self.assertIn("hand_L", mc.contacts)
        hand_c = mc.contacts["hand_L"]
        self.assertEqual(hand_c.lifecycle, ContactLifecycle.ESTABLISHED)
        self.assertTrue(hand_c.is_active)
        self.assertIn("hand_L", mc.active_contacts)
        self.assertEqual(mc.support_type, SupportType.MULTI_SURFACE)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
