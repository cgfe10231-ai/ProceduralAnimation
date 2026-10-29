"""ProceduralAnimation — Regression Test Suite for FIND-R2-02.

Validates that TerrainWalkAction preserves actual contact state returned by KinematicBridgeExecutor:
- Case A: Normal dual-foot walk contact state verification (Bridge contacts preserved).
- Case B: Discrepancy between planned target and actual contact position (actual contact point retained, e.g. z=1.3397).
- Case C: Real contact failure / broken stance scenario (broken/released is_locked=False preserved, not masked).
- Case D: Upper limb contact preservation scenario (hand_L/hand_R preserved, not overwritten/dropped).
- Case E: Action chain final state preservation (result.final_state.contacts matches result.states[-1].contacts).
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

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.framework import (
    BlenderPoseApplicator,
    ContactConstraintAdapter,
    ContactPointState,
    MotionRuntimeContext,
    SurfaceQueryResult,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.rig.arm_ik import setup_arm_ik
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import setup_leg_ik


class MockFlatGroundEnvironment:
    """Standard planar ground environment for regression testing."""

    def __init__(self, ground_z: float = 0.0):
        self.ground_z = ground_z

    def ground_height_at(self, x: float, y: float) -> float:
        return self.ground_z

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


class InspectableBridgeExecutor(KinematicBridgeExecutor):
    """Bridge executor wrapper that allows intercepting or inspecting returned motion states."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_res = None
        self.intercept = False
        self.injected_contacts: Dict[str, ContactPointState] = {}

    def execute_frame(self, planned, *args, **kwargs):
        res = super().execute_frame(planned, *args, **kwargs)
        if self.intercept:
            for limb_key, contact_state in self.injected_contacts.items():
                res.motion_state.contacts[limb_key] = contact_state
        self.last_res = res
        return res


class TestFindR202ContactStateOwnership(unittest.TestCase):
    """Targeted regression test for FIND-R2-02 contact state ownership."""

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
        cls.adapter = ContactConstraintAdapter(cls.armature, cls.env)
        cls.applicator = BlenderPoseApplicator(cls.armature, cls.root, cls.config)

    def _execute_walk(
        self,
        intercept: bool = False,
        injected_contacts: Optional[Dict[str, ContactPointState]] = None,
    ) -> Tuple[Any, InspectableBridgeExecutor]:
        bridge = InspectableBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
            default_fps=self.config.fps,
        )
        bridge.intercept = intercept
        bridge.injected_contacts = injected_contacts or {}

        ctx = MotionRuntimeContext(
            config=self.config,
            armature_obj=self.armature,
            root_obj=self.root,
            scene=bpy.context.scene,
            environment=self.env,
            contact_adapter=self.adapter,
            pose_applicator=self.applicator,
            bridge_executor=bridge,
        )

        init_state = create_initial_motion_state(self.config)
        init_state = init_state.clone_with(position=(0.0, 0.0, 0.0))

        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.3, 0.0),
            nominal_stride_m=0.3,
            stand_start_frames=2,
            step_frames=4,
            stand_stop_frames=2,
        )
        action = TerrainWalkAction(route=route, environment=self.env)
        result = action.execute(init_state, ctx)
        return result, bridge

    def test_case_a_normal_walk_contact_state_ownership(self) -> None:
        """Case A: Normal walk preserves actual contact state produced by KinematicBridgeExecutor."""
        result, bridge = self._execute_walk(intercept=False)
        self.assertGreater(len(result.states), 0)

        # In every frame, ms.contacts must come from bridge_res.motion_state.contacts
        # and planned step schedule parameters must be preserved in ms.params
        last_ms = result.states[-1]
        self.assertIn("foot_L", last_ms.contacts)
        self.assertIn("foot_R", last_ms.contacts)

        # Verify planned metadata is stored in ms.params
        self.assertIn("planned_phase_l", last_ms.params)
        self.assertIn("planned_phase_r", last_ms.params)
        self.assertIn("planned_locked_l", last_ms.params)
        self.assertIn("planned_locked_r", last_ms.params)
        self.assertIn("planned_target_l", last_ms.params)
        self.assertIn("planned_target_r", last_ms.params)

        # Verify last frame contacts object identity matches Bridge's output
        self.assertIs(last_ms.contacts, bridge.last_res.motion_state.contacts)

    def test_case_b_planned_vs_actual_contact_position_discrepancy(self) -> None:
        """Case B: Actual contact point returned by Bridge (z=1.3397) is preserved over planned target."""
        actual_pos = (0.0, 0.0, 1.3397)
        injected = {
            "foot_L": ContactPointState(
                limb="foot_L",
                phase="stance",
                is_locked=True,
                contact_world_xyz=actual_pos,
                current_world_xyz=actual_pos,
                surface_normal=(0.0, 0.0, 1.0),
            )
        }
        result, _ = self._execute_walk(intercept=True, injected_contacts=injected)
        self.assertGreater(len(result.states), 0)

        first_ms = result.states[0]
        self.assertAlmostEqual(
            first_ms.contacts["foot_L"].contact_world_xyz[2],
            1.3397,
            places=4,
            msg="Actual contact Z=1.3397 must NOT be overwritten by planned target Z=0.0",
        )

    def test_case_c_contact_failure_broken_stance_preserved(self) -> None:
        """Case C: Real contact detachment/failure (is_locked=False) is preserved, not masked as True."""
        injected = {
            "foot_L": ContactPointState(
                limb="foot_L",
                phase="swing",
                is_locked=False,
                contact_world_xyz=(0.0, 0.0, 0.0),
                current_world_xyz=(0.0, 0.0, 0.0),
                surface_normal=(0.0, 0.0, 1.0),
            )
        }
        result, _ = self._execute_walk(intercept=True, injected_contacts=injected)
        self.assertGreater(len(result.states), 0)

        first_ms = result.states[0]
        self.assertFalse(
            first_ms.contacts["foot_L"].is_locked,
            "Contact failure (is_locked=False) must NOT be masked as True by planner intent",
        )

    def test_case_d_upper_limb_contact_preservation(self) -> None:
        """Case D: Upper limb contacts returned by Bridge are preserved, not erased."""
        injected = {
            "hand_L": ContactPointState(
                limb="hand_L",
                phase="stance",
                is_locked=True,
                contact_world_xyz=(-0.25, 0.0, 1.1),
                current_world_xyz=(-0.25, 0.0, 1.1),
                surface_normal=(0.0, 0.0, 1.0),
            )
        }
        result, _ = self._execute_walk(intercept=True, injected_contacts=injected)
        self.assertGreater(len(result.states), 0)

        first_ms = result.states[0]
        self.assertIn(
            "hand_L",
            first_ms.contacts,
            "Upper limb contact 'hand_L' must NOT be discarded by foot-only c_dict",
        )
        self.assertTrue(first_ms.contacts["hand_L"].is_locked)
        self.assertAlmostEqual(first_ms.contacts["hand_L"].contact_world_xyz[0], -0.25, places=4)

    def test_case_e_action_chain_final_state_preservation(self) -> None:
        """Case E: Action chain final_state retains Bridge actual contacts for subsequent actions."""
        injected = {
            "hand_L": ContactPointState(
                limb="hand_L",
                phase="stance",
                is_locked=True,
                contact_world_xyz=(-0.25, 0.0, 1.1),
                current_world_xyz=(-0.25, 0.0, 1.1),
                surface_normal=(0.0, 0.0, 1.0),
            ),
            "foot_L": ContactPointState(
                limb="foot_L",
                phase="stance",
                is_locked=True,
                contact_world_xyz=(0.0, 0.0, 1.3397),
                current_world_xyz=(0.0, 0.0, 1.3397),
                surface_normal=(0.0, 0.0, 1.0),
            ),
        }
        result, _ = self._execute_walk(intercept=True, injected_contacts=injected)
        self.assertGreater(len(result.states), 0)

        final_state = result.final_state
        self.assertIn("hand_L", final_state.contacts)
        self.assertAlmostEqual(final_state.contacts["foot_L"].contact_world_xyz[2], 1.3397, places=4)
        self.assertEqual(final_state.contacts, result.states[-1].contacts)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
