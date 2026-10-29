"""ProceduralAnimation — Regression Test Suite for FIND-R2-03.

Validates execution failure propagation and contract enforcement in TerrainWalkAction:
- Case A: Bridge overall success (success=True, motion_state valid) -> normal execution.
- Case B: WBC reachability failure (success=False, is_all_reachable=False) -> immediate block and RuntimeError.
- Case C: WBC reachable, but contact geometry failure (success=False, is_all_reachable=True, unmet contact geometry) -> immediate block and RuntimeError.
- Case D: Joint ROM failure (success=False, unmet ROM constraints) -> immediate block and RuntimeError.
- Case E: Bridge returns motion_state=None -> explicit contract exception (RuntimeError).
- Case F: Normal continuous scene regression -> confirms clean execution without spurious failure.
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
from src.motion.contact_model import GeometricConstraintResult
from src.motion.framework import (
    BlenderPoseApplicator,
    ContactConstraintAdapter,
    MotionRuntimeContext,
    SurfaceQueryResult,
    create_initial_motion_state,
)
from src.motion.kinematic_bridge import KinematicBridgeExecutor
from src.motion.terrain_walk import TerrainRouteInput, TerrainWalkAction
from src.motion.whole_body_controller import UnmetConstraint
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


class FaultInjectingBridgeExecutor(KinematicBridgeExecutor):
    """Bridge executor wrapper that injects controlled failure modes into execute_frame."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure_mode: str = "none"

    def execute_frame(self, planned, *args, **kwargs):
        res = super().execute_frame(planned, *args, **kwargs)

        if self.failure_mode == "wbc_unreachable":
            uc = UnmetConstraint(
                category="REACHABILITY",
                target_name="foot_L",
                description="Target exceeds maximum leg reach (0.820m > 0.820m)",
                error_amount=0.08,
            )
            res.wbc_result.is_all_reachable = False
            res.wbc_result.success = False
            res.unmet_constraints.append(uc)
            res.success = False

        elif self.failure_mode == "contact_geom_fail":
            geom_err = GeometricConstraintResult(
                is_valid=False,
                total_position_error_m=0.035,
                distance_normal_m=0.035,
                penetration_depth_m=0.0,
                tangential_slip_m=0.0,
                violation_reason="CONTACT_GEOMETRY: Foot sole detached from terrain surface",
            )
            uc = UnmetConstraint(
                category="CONTACT_GEOMETRY",
                target_name="foot_L",
                description="Contact geometric constraint violated: Foot sole detached from terrain surface",
                error_amount=0.035,
            )
            res.contact_geometry_errors["foot_L"] = geom_err
            res.unmet_constraints.append(uc)
            res.wbc_result.is_all_reachable = True  # WBC is reachable, but geometry fails
            res.success = False

        elif self.failure_mode == "rom_fail":
            uc = UnmetConstraint(
                category="JOINT_ROM",
                target_name="knee.L",
                description="Knee flexion angle 155.0 deg exceeds maximum ROM limit (145.0 deg)",
                error_amount=10.0,
            )
            res.rom_violations["knee.L"] = {"angle": 155.0, "max": 145.0}
            res.unmet_constraints.append(uc)
            res.success = False

        elif self.failure_mode == "motion_state_none":
            res.motion_state = None

        return res


class TestTerrainWalkFailurePropagation(unittest.TestCase):
    """Targeted regression test suite verifying failure propagation in TerrainWalkAction."""

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

    def _execute_walk(self, failure_mode: str = "none") -> Any:
        bridge = FaultInjectingBridgeExecutor(
            armature_obj=self.armature,
            root_obj=self.root,
            environment=self.env,
            default_fps=self.config.fps,
        )
        bridge.failure_mode = failure_mode

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

        init_state = create_initial_motion_state(self.config).clone_with(position=(0.0, 0.0, 0.0))
        route = TerrainRouteInput(
            start_pos=(0.0, 0.0, 0.0),
            target_pos=(0.0, 0.3, 0.0),
            nominal_stride_m=0.3,
            stand_start_frames=4,
            step_frames=8,
            stand_stop_frames=4,
        )
        action = TerrainWalkAction(route=route, environment=self.env)
        return action.execute(init_state, ctx)

    def test_case_a_bridge_overall_success(self) -> None:
        """Case A: When Bridge succeeds and motion_state is valid, TerrainWalk executes normally."""
        result = self._execute_walk(failure_mode="none")
        self.assertGreater(len(result.states), 0)
        self.assertEqual(result.unreachable_count, 0)
        self.assertIsNotNone(result.final_state)

    def test_case_b_wbc_unreachable_failure(self) -> None:
        """Case B: When WBC reachability fails, TerrainWalkAction must raise RuntimeError immediately."""
        with self.assertRaises(RuntimeError) as cm:
            self._execute_walk(failure_mode="wbc_unreachable")

        err_msg = str(cm.exception)
        self.assertIn("failed at Frame", err_msg)
        self.assertIn("REACHABILITY", err_msg)
        self.assertIn("foot_L", err_msg)

    def test_case_c_contact_geometry_failure_when_wbc_reachable(self) -> None:
        """Case C: When WBC is reachable but contact geometry fails, TerrainWalkAction must raise RuntimeError."""
        with self.assertRaises(RuntimeError) as cm:
            self._execute_walk(failure_mode="contact_geom_fail")

        err_msg = str(cm.exception)
        self.assertIn("failed at Frame", err_msg)
        self.assertIn("CONTACT_GEOMETRY", err_msg)
        self.assertIn("foot_L", err_msg)

    def test_case_d_joint_rom_failure(self) -> None:
        """Case D: When ROM limits fail, TerrainWalkAction must raise RuntimeError immediately."""
        with self.assertRaises(RuntimeError) as cm:
            self._execute_walk(failure_mode="rom_fail")

        err_msg = str(cm.exception)
        self.assertIn("failed at Frame", err_msg)
        self.assertIn("JOINT_ROM", err_msg)
        self.assertIn("knee.L", err_msg)

    def test_case_e_motion_state_none_contract_exception(self) -> None:
        """Case E: When Bridge returns motion_state=None, an explicit contract exception must be raised."""
        with self.assertRaises(RuntimeError) as cm:
            self._execute_walk(failure_mode="motion_state_none")

        err_msg = str(cm.exception)
        self.assertIn("motion_state=None", err_msg)

    def test_case_f_normal_continuous_scene_regression(self) -> None:
        """Case F: Standard multi-step walking executes to completion without false failure."""
        result = self._execute_walk(failure_mode="none")
        self.assertEqual(len(result.states), 24)
        self.assertEqual(result.states[0].frame, 1)
        self.assertEqual(result.states[-1].frame, 24)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
