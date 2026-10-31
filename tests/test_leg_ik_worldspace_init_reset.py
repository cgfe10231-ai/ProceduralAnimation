"""ProceduralAnimation — PKG-5 / WS-01 Unit Tests.

Validates Leg IK Controller World-Space Initialization and Reset Invariant:
- TEST-1: First-time initialization (parent is None, correct world coordinates).
- TEST-2: Root non-zero translation (controllers match root neutral target, not world origin).
- TEST-3: Root non-zero rotation (FootIK, KneePole, and orientation match transformed root).
- TEST-4: Recovery of existing parented controller objects (unparented to parent is None).
- TEST-5: Reset behavior from displaced poses and repeated reset without cumulative drift.
- TEST-6: Subsequent root motion does not drag world-space independent controllers.
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
from mathutils import Euler, Matrix, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    KNEE_REST_Z,
    POLE_FORWARD_OFFSET,
    POLE_TARGET_NAMES,
    reset_leg_ik,
    setup_leg_ik,
)


class TestLegIKWorldspaceInitReset(unittest.TestCase):
    """Test suite verifying world-space independence of FootIK and KneePole controllers."""

    def setUp(self) -> None:
        """Reset Blender state and build clean character rig for each test."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.config = PipelineConfig()
        self.char_data = build_character(self.config)
        self.root = self.char_data["root"]
        self.parts = self.char_data["parts"]
        self.armature = build_rig(self.config)
        bind_character_to_rig(self.armature, self.parts)

    def test_1_first_time_initialization(self) -> None:
        """TEST-1: First-time setup_leg_ik creates unparented controllers at correct world coordinates."""
        controls = setup_leg_ik(self.armature)

        # Base root start location is typically (0.0, -8.0, 0.0) from PipelineConfig
        root_mat = self.root.matrix_world.copy()

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = controls[IK_TARGET_NAMES[side]]
            pole_obj = controls[POLE_TARGET_NAMES[side]]

            # 1. Controller parent must be strictly None
            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must have parent is None on initialization")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} must have parent is None on initialization")

            # 2. Expected world position transformed from root neutral stance
            expected_ik_world = root_mat @ Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            expected_pole_world = root_mat @ Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

            self.assertLess(
                (ik_obj.location - expected_ik_world).length,
                1e-5,
                f"{ik_obj.name} location {ik_obj.location} differs from expected world {expected_ik_world}",
            )
            self.assertLess(
                (ik_obj.matrix_world.translation - expected_ik_world).length,
                1e-5,
                f"{ik_obj.name} matrix_world differs from expected {expected_ik_world}",
            )
            self.assertLess(
                (pole_obj.location - expected_pole_world).length,
                1e-5,
                f"{pole_obj.name} location {pole_obj.location} differs from expected world {expected_pole_world}",
            )
            self.assertLess(
                (pole_obj.matrix_world.translation - expected_pole_world).length,
                1e-5,
                f"{pole_obj.name} matrix_world differs from expected {expected_pole_world}",
            )

    def test_2_root_nonzero_translation(self) -> None:
        """TEST-2: Root placed away from origin initializes controllers matching root, not world origin."""
        # Translate CharacterRoot to arbitrary 3D position
        self.root.location = Vector((2.5, 3.0, 1.2))
        bpy.context.view_layer.update()

        controls = setup_leg_ik(self.armature)
        root_mat = self.root.matrix_world.copy()

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = controls[IK_TARGET_NAMES[side]]
            pole_obj = controls[POLE_TARGET_NAMES[side]]

            self.assertIsNone(ik_obj.parent)
            self.assertIsNone(pole_obj.parent)

            expected_ik_world = root_mat @ Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            expected_pole_world = root_mat @ Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

            # Must match translated root target
            self.assertLess((ik_obj.location - expected_ik_world).length, 1e-5)
            self.assertLess((pole_obj.location - expected_pole_world).length, 1e-5)

            # Must NOT mistakenly stay at root-local offset around world origin (0, 0, 0)
            local_origin_ik = Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            self.assertGreater((ik_obj.location - local_origin_ik).length, 1.0)

    def test_3_root_nonzero_rotation(self) -> None:
        """TEST-3: Root non-zero yaw transforms FootIK/KneePole position and orientation correctly."""
        # Position CharacterRoot with arbitrary yaw angle (e.g. 35 degrees) and translation
        yaw_rad = math.radians(35.0)
        self.root.location = Vector((1.0, -5.0, 0.5))
        self.root.rotation_euler = Euler((0.0, 0.0, yaw_rad), "XYZ")
        bpy.context.view_layer.update()

        controls = setup_leg_ik(self.armature)
        root_mat = self.root.matrix_world.copy()
        root_rot = root_mat.to_euler("XYZ")

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = controls[IK_TARGET_NAMES[side]]
            pole_obj = controls[POLE_TARGET_NAMES[side]]

            self.assertIsNone(ik_obj.parent)
            self.assertIsNone(pole_obj.parent)

            expected_ik_world = root_mat @ Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            expected_pole_world = root_mat @ Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

            # World positions must match rotated root frame
            self.assertLess((ik_obj.location - expected_ik_world).length, 1e-5)
            self.assertLess((pole_obj.location - expected_pole_world).length, 1e-5)

            # World orientation must match root rotation
            self.assertLess(abs(ik_obj.rotation_euler.z - root_rot.z), 1e-5)
            self.assertLess(abs(pole_obj.rotation_euler.z - root_rot.z), 1e-5)

    def test_4_existing_parented_object_recovery(self) -> None:
        """TEST-4: Existing controller objects previously parented to root are cleanly unparented."""
        # First setup
        controls = setup_leg_ik(self.armature)

        # Artificially parent controllers to CharacterRoot (simulating legacy scene or reparenting)
        for side in ("L", "R"):
            ik_obj = controls[IK_TARGET_NAMES[side]]
            pole_obj = controls[POLE_TARGET_NAMES[side]]
            ik_obj.parent = self.root
            pole_obj.parent = self.root
            bpy.context.view_layer.update()
            self.assertIsNotNone(ik_obj.parent)
            self.assertIsNotNone(pole_obj.parent)

        # Re-run setup_leg_ik: must unparent existing objects and restore correct world coordinates
        recovered_controls = setup_leg_ik(self.armature)
        root_mat = self.root.matrix_world.copy()

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = recovered_controls[IK_TARGET_NAMES[side]]
            pole_obj = recovered_controls[POLE_TARGET_NAMES[side]]

            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} failed to unparent on recovery setup")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} failed to unparent on recovery setup")

            expected_ik_world = root_mat @ Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            expected_pole_world = root_mat @ Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

            self.assertLess((ik_obj.location - expected_ik_world).length, 1e-5)
            self.assertLess((pole_obj.location - expected_pole_world).length, 1e-5)

    def test_5_reset_behavior_and_no_cumulative_drift(self) -> None:
        """TEST-5: reset_leg_ik unparents, restores neutral standing pose, and has zero cumulative drift."""
        setup_leg_ik(self.armature)

        # Displace controllers away from neutral and optionally re-parent
        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
            ik_obj.location += Vector((0.2, 0.3, 0.1))
            pole_obj.location += Vector((0.1, 0.2, -0.05))
            # Simulate dirty state with parent attached
            ik_obj.parent = self.root
            pole_obj.parent = self.root
        bpy.context.view_layer.update()

        # Execute reset_leg_ik
        reset_leg_ik(self.armature)
        root_mat = self.root.matrix_world.copy()
        root_rot = root_mat.to_euler("XYZ")

        for side, sign in (("L", -1.0), ("R", 1.0)):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must have parent is None after reset")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} must have parent is None after reset")

            expected_ik_world = root_mat @ Vector((sign * HIP_X_OFFSET, 0.0, ANKLE_REST_Z))
            expected_pole_world = root_mat @ Vector((sign * HIP_X_OFFSET, POLE_FORWARD_OFFSET, KNEE_REST_Z))

            self.assertLess((ik_obj.location - expected_ik_world).length, 1e-5)
            self.assertLess((pole_obj.location - expected_pole_world).length, 1e-5)
            self.assertLess(abs(ik_obj.rotation_euler.z - root_rot.z), 1e-5)

        # Record locations after first reset
        first_reset_ik = {side: bpy.data.objects[IK_TARGET_NAMES[side]].location.copy() for side in ("L", "R")}
        first_reset_pole = {side: bpy.data.objects[POLE_TARGET_NAMES[side]].location.copy() for side in ("L", "R")}

        # Perform 5 consecutive resets: must have zero cumulative drift
        for _ in range(5):
            reset_leg_ik(self.armature)

        for side in ("L", "R"):
            cur_ik = bpy.data.objects[IK_TARGET_NAMES[side]].location
            cur_pole = bpy.data.objects[POLE_TARGET_NAMES[side]].location
            self.assertLess(
                (cur_ik - first_reset_ik[side]).length,
                1e-6,
                f"Cumulative drift detected on {IK_TARGET_NAMES[side]} across repeated resets",
            )
            self.assertLess(
                (cur_pole - first_reset_pole[side]).length,
                1e-6,
                f"Cumulative drift detected on {POLE_TARGET_NAMES[side]} across repeated resets",
            )

    def test_6_subsequent_root_motion_does_not_drag_controllers(self) -> None:
        """TEST-6: Moving CharacterRoot does NOT drag independent world-space controllers."""
        setup_leg_ik(self.armature)

        # Snapshot initial world coordinates of controllers
        init_ik_locs = {side: bpy.data.objects[IK_TARGET_NAMES[side]].location.copy() for side in ("L", "R")}
        init_pole_locs = {side: bpy.data.objects[POLE_TARGET_NAMES[side]].location.copy() for side in ("L", "R")}

        # Move and rotate CharacterRoot (e.g. character walks or turns)
        self.root.location += Vector((0.5, 1.2, 0.3))
        self.root.rotation_euler.z += math.radians(25.0)
        bpy.context.view_layer.update()

        # Without explicit leg IK control commands, world-space independent controllers must stay in place
        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must remain parent is None")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} must remain parent is None")

            # Location must remain exactly at initial world coordinates (not dragged by root)
            self.assertLess(
                (ik_obj.location - init_ik_locs[side]).length,
                1e-6,
                f"{ik_obj.name} was dragged by CharacterRoot translation/rotation!",
            )
            self.assertLess(
                (pole_obj.location - init_pole_locs[side]).length,
                1e-6,
                f"{pole_obj.name} was dragged by CharacterRoot translation/rotation!",
            )


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
