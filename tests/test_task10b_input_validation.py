"""Contract verification suite for Arm IK Input Pre-Validation & Zero-Side-Effect Contract (Task 10-B / 10-b-1 & 10-b-2).

Tests:
- TEST-01: setup_arm_ik accepts valid influence boundaries (0.0, 0.5, 1.0).
- TEST-02: setup_arm_ik rejects non-finite influence values (NaN, +Inf, -Inf).
- TEST-03: setup_arm_ik rejects negative influence values (< 0.0).
- TEST-04: setup_arm_ik rejects excessive influence values (> 1.0).
- TEST-05: setup_arm_ik invalid inputs cause zero scene mutation (no Empties, no constraints).
- TEST-06: set_hand_ik_target rejects invalid side identifiers.
- TEST-07: set_hand_ik_target rejects world_xyz with wrong arity or type.
- TEST-08: set_hand_ik_target rejects non-finite world_xyz coordinates.
- TEST-09: set_hand_ik_target rejects hand_rotation_deg with wrong arity or type.
- TEST-10: set_hand_ik_target rejects non-finite hand_rotation_deg values.
- TEST-11: set_hand_ik_target rejects pole_world_xyz with wrong arity or type.
- TEST-12: set_hand_ik_target rejects non-finite pole_world_xyz coordinates.
- TEST-13: set_hand_ik_target rejects non-finite influence values.
- TEST-14: set_hand_ik_target rejects out-of-range influence values.
- TEST-15: set_hand_ik_target rejects non-boolean clamp_reach values.
- TEST-16: set_hand_ik_target with invalid inputs does NOT auto-initialize arm IK.
- TEST-17: set_hand_ik_target with invalid inputs leaves existing scene and IK state completely unchanged.
- TEST-18: set_arm_ik_influence rejects invalid side identifiers.
- TEST-19: set_arm_ik_influence rejects non-finite influence values.
- TEST-20: set_arm_ik_influence rejects out-of-range influence values.
- TEST-21: set_arm_ik_influence invalid inputs cause zero mutation on existing influences.
- TEST-22: set_arm_ik_influence preserves independent L/R state updates and accepts BOTH.
- TEST-23: set_hand_ik_target accepts valid boolean clamp_reach modes (True and False).
- TEST-24: set_hand_ik_target preserves symmetric influence weight consistency across constraints.
- TEST-25: set_hand_ik_target with invalid auto-init parent transform causes zero scene mutation.
- TEST-26: set_hand_ik_target with partially initialized state and invalid new parent causes zero mutation.
- TEST-27: set_hand_ik_target first-time auto-initialization succeeds under valid conformal parent transforms.
"""

import math
import os
import sys
import unittest

import bpy
from mathutils import Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    HAND_ROT_CONSTRAINT_NAMES,
    get_arm_ik_state,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


class TestArmIKInputValidationContract(unittest.TestCase):
    """Test suite verifying Arm IK input pre-validation and zero-side-effect contracts."""

    def setUp(self) -> None:
        """Reset Blender state and build fresh character rig for each test."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.config = PipelineConfig()
        self.char_data = build_character(self.config)
        self.root = self.char_data["root"]
        self.parts = self.char_data["parts"]
        self.armature = build_rig(self.config)
        bind_character_to_rig(self.armature, self.parts)
        setup_leg_ik(self.armature)
        reset_leg_ik(self.armature)
        reset_pose(self.armature)
        bpy.context.view_layer.update()

    # -------------------------------------------------------------------------
    # setup_arm_ik Validation Tests (TEST-01 to TEST-05)
    # -------------------------------------------------------------------------

    def test_01_setup_accepts_influence_boundaries(self) -> None:
        """TEST-01: setup_arm_ik accepts valid influence boundaries (0.0, 0.5, 1.0)."""
        for valid_val in (0.0, 0.5, 1.0, 0, 1):
            with self.subTest(valid_influence=valid_val):
                bpy.ops.wm.read_factory_settings(use_empty=True)
                char_data = build_character(self.config)
                arm = build_rig(self.config)
                bind_character_to_rig(arm, char_data["parts"])
                setup_arm_ik(arm, initial_influence=valid_val)

                p_fore = arm.pose.bones["forearm.L"]
                p_hand = arm.pose.bones["hand.L"]
                expected = float(valid_val)
                self.assertAlmostEqual(p_fore.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, expected, places=5)
                self.assertAlmostEqual(p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, expected, places=5)

    def test_02_setup_rejects_non_finite_influence(self) -> None:
        """TEST-02: setup_arm_ik rejects non-finite influence values (NaN, +Inf, -Inf)."""
        for invalid_val in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid_influence=invalid_val):
                with self.assertRaises(ValueError):
                    setup_arm_ik(self.armature, initial_influence=invalid_val)

    def test_03_setup_rejects_influence_below_zero(self) -> None:
        """TEST-03: setup_arm_ik rejects negative influence values (< 0.0)."""
        for invalid_val in (-0.0001, -0.01, -0.5, -1.0, -100.0):
            with self.subTest(invalid_influence=invalid_val):
                with self.assertRaises(ValueError):
                    setup_arm_ik(self.armature, initial_influence=invalid_val)

    def test_04_setup_rejects_influence_above_one(self) -> None:
        """TEST-04: setup_arm_ik rejects excessive influence values (> 1.0)."""
        for invalid_val in (1.0001, 1.01, 1.5, 2.0, 100.0):
            with self.subTest(invalid_influence=invalid_val):
                with self.assertRaises(ValueError):
                    setup_arm_ik(self.armature, initial_influence=invalid_val)

    def test_05_setup_invalid_input_has_zero_scene_mutation(self) -> None:
        """TEST-05: setup_arm_ik invalid inputs cause zero scene mutation (no Empties, no constraints)."""
        objs_before = set(bpy.data.objects.keys())
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]
        fore_con_count_before = len(p_fore_l.constraints)
        hand_con_count_before = len(p_hand_l.constraints)

        # Attempt multiple illegal invocations
        for illegal in (-0.1, 1.2, float("nan"), float("inf"), "invalid_str", None, [0.5]):
            with self.assertRaises((ValueError, TypeError)):
                setup_arm_ik(self.armature, initial_influence=illegal)

        # Verify absolutely no scene objects or constraints were created
        self.assertEqual(set(bpy.data.objects.keys()), objs_before)
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)
        self.assertEqual(len(p_fore_l.constraints), fore_con_count_before)
        self.assertEqual(len(p_hand_l.constraints), hand_con_count_before)

    # -------------------------------------------------------------------------
    # set_hand_ik_target Validation Tests (TEST-06 to TEST-17)
    # -------------------------------------------------------------------------

    def test_06_hand_target_rejects_invalid_side(self) -> None:
        """TEST-06: set_hand_ik_target rejects invalid side identifiers."""
        valid_pos = (0.35, -0.1, 1.1)
        for invalid_side in ("X", "LEFT", "RIGHT", "both", "l_hand", "", "  ", 1, 0, None, [], {}):
            with self.subTest(side=invalid_side):
                with self.assertRaises((ValueError, TypeError)):
                    set_hand_ik_target(self.armature, invalid_side, valid_pos)

    def test_07_hand_target_rejects_world_xyz_wrong_arity(self) -> None:
        """TEST-07: set_hand_ik_target rejects world_xyz with wrong arity or type."""
        for invalid_xyz in (
            (1.0, 2.0),
            (1.0, 2.0, 3.0, 4.0),
            (),
            [],
            [1.0],
            [1.0, 2.0],
            [1.0, 2.0, 3.0, 4.0],
            "0.3, 0.0, 1.0",
            123,
            None,
            {"x": 1, "y": 2, "z": 3},
        ):
            with self.subTest(world_xyz=invalid_xyz):
                with self.assertRaises((ValueError, TypeError)):
                    set_hand_ik_target(self.armature, "L", invalid_xyz)

    def test_08_hand_target_rejects_world_xyz_non_finite(self) -> None:
        """TEST-08: set_hand_ik_target rejects non-finite world_xyz coordinates."""
        for non_finite in (
            (float("nan"), 0.0, 1.0),
            (0.3, float("inf"), 1.0),
            (0.3, 0.0, float("-inf")),
            [float("nan"), float("inf"), 1.0],
        ):
            with self.subTest(world_xyz=non_finite):
                with self.assertRaises(ValueError):
                    set_hand_ik_target(self.armature, "L", non_finite)

    def test_09_hand_target_rejects_rotation_wrong_arity(self) -> None:
        """TEST-09: set_hand_ik_target rejects hand_rotation_deg with wrong arity or type."""
        valid_pos = (0.35, -0.1, 1.1)
        for invalid_rot in (
            (1.0, 2.0),
            (1.0, 2.0, 3.0, 4.0),
            (),
            [],
            [1.0],
            "rot_xyz",
            45,
            True,
            {"pitch": 10},
        ):
            with self.subTest(rot=invalid_rot):
                with self.assertRaises((ValueError, TypeError)):
                    set_hand_ik_target(self.armature, "L", valid_pos, hand_rotation_deg=invalid_rot)

    def test_10_hand_target_rejects_rotation_non_finite(self) -> None:
        """TEST-10: set_hand_ik_target rejects non-finite hand_rotation_deg values."""
        valid_pos = (0.35, -0.1, 1.1)
        for non_finite in (
            (float("nan"), 0.0, 0.0),
            (0.0, float("inf"), 0.0),
            (0.0, 0.0, float("-inf")),
        ):
            with self.subTest(rot=non_finite):
                with self.assertRaises(ValueError):
                    set_hand_ik_target(self.armature, "L", valid_pos, hand_rotation_deg=non_finite)

    def test_11_hand_target_rejects_pole_wrong_arity(self) -> None:
        """TEST-11: set_hand_ik_target rejects pole_world_xyz with wrong arity or type."""
        valid_pos = (0.35, -0.1, 1.1)
        for invalid_pole in (
            (1.0, 2.0),
            (1.0, 2.0, 3.0, 4.0),
            (),
            [],
            [1.0, 2.0],
            "pole_xyz",
            123,
            False,
        ):
            with self.subTest(pole=invalid_pole):
                with self.assertRaises((ValueError, TypeError)):
                    set_hand_ik_target(self.armature, "L", valid_pos, pole_world_xyz=invalid_pole)

    def test_12_hand_target_rejects_pole_non_finite(self) -> None:
        """TEST-12: set_hand_ik_target rejects non-finite pole_world_xyz coordinates."""
        valid_pos = (0.35, -0.1, 1.1)
        for non_finite in (
            (float("nan"), 0.0, 1.0),
            (0.3, float("inf"), 1.0),
            (0.3, 0.0, float("-inf")),
        ):
            with self.subTest(pole=non_finite):
                with self.assertRaises(ValueError):
                    set_hand_ik_target(self.armature, "L", valid_pos, pole_world_xyz=non_finite)

    def test_13_hand_target_rejects_non_finite_influence(self) -> None:
        """TEST-13: set_hand_ik_target rejects non-finite influence values."""
        valid_pos = (0.35, -0.1, 1.1)
        for non_finite in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(influence=non_finite):
                with self.assertRaises((ValueError, TypeError)):
                    set_hand_ik_target(self.armature, "L", valid_pos, influence=non_finite)

    def test_14_hand_target_rejects_out_of_range_influence(self) -> None:
        """TEST-14: set_hand_ik_target rejects out-of-range influence values."""
        valid_pos = (0.35, -0.1, 1.1)
        for out_val in (-0.01, -1.0, 1.01, 2.0, 10.0):
            with self.subTest(influence=out_val):
                with self.assertRaises(ValueError):
                    set_hand_ik_target(self.armature, "L", valid_pos, influence=out_val)

    def test_15_hand_target_rejects_non_boolean_clamp_reach(self) -> None:
        """TEST-15: set_hand_ik_target rejects non-boolean clamp_reach values."""
        valid_pos = (0.35, -0.1, 1.1)
        for invalid_clamp in (0, 1, 2, -1, 1.0, "True", "False", None, [], {}):
            with self.subTest(clamp_reach=invalid_clamp):
                with self.assertRaises(TypeError):
                    set_hand_ik_target(self.armature, "L", valid_pos, clamp_reach=invalid_clamp)

    def test_16_invalid_hand_target_does_not_auto_initialize(self) -> None:
        """TEST-16: set_hand_ik_target with invalid inputs does NOT auto-initialize arm IK."""
        # Pre-condition: Arm IK has not been setup
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        # Call with invalid world_xyz
        with self.assertRaises(ValueError):
            set_hand_ik_target(self.armature, "L", (float("nan"), 0.0, 1.0))

        # Call with invalid side
        with self.assertRaises(ValueError):
            set_hand_ik_target(self.armature, "INVALID", (0.35, -0.1, 1.1))

        # Call with invalid influence
        with self.assertRaises(ValueError):
            set_hand_ik_target(self.armature, "L", (0.35, -0.1, 1.1), influence=-0.5)

        # Call with invalid clamp_reach
        with self.assertRaises(TypeError):
            set_hand_ik_target(self.armature, "L", (0.35, -0.1, 1.1), clamp_reach=1)

        # Verify no controllers or constraints were created
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]
        self.assertNotIn(ARM_IK_CONSTRAINT_NAMES["L"], p_fore_l.constraints)
        self.assertNotIn(HAND_ROT_CONSTRAINT_NAMES["L"], p_hand_l.constraints)

    def test_17_invalid_hand_target_leaves_existing_state_unchanged(self) -> None:
        """TEST-17: set_hand_ik_target with invalid inputs leaves existing scene and IK state completely unchanged."""
        # Establish known valid active state
        setup_arm_ik(self.armature, initial_influence=0.7)
        initial_pos = (0.35, -0.1, 1.1)
        initial_rot = (15.0, -10.0, 25.0)
        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=initial_pos,
            hand_rotation_deg=initial_rot,
            influence=0.7,
            clamp_reach=True,
        )

        ik_l = bpy.data.objects["HandIK.L"]
        pole_l = bpy.data.objects["ElbowPole.L"]
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]

        snap_ik_loc = ik_l.location.copy()
        snap_ik_rot = ik_l.rotation_euler.copy()
        snap_pole_loc = pole_l.location.copy()
        snap_fore_inf = p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence
        snap_hand_inf = p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence
        snap_state = get_arm_ik_state(self.armature, "L")

        # Attempt diverse illegal invocations
        illegal_calls = [
            lambda: set_hand_ik_target(self.armature, "INVALID", (0.4, 0.0, 1.0)),
            lambda: set_hand_ik_target(self.armature, "L", (float("nan"), 0.0, 1.0)),
            lambda: set_hand_ik_target(self.armature, "L", (0.4, 0.0, 1.0), hand_rotation_deg=(float("inf"), 0.0, 0.0)),
            lambda: set_hand_ik_target(self.armature, "L", (0.4, 0.0, 1.0), pole_world_xyz=(1.0, 2.0)),
            lambda: set_hand_ik_target(self.armature, "L", (0.4, 0.0, 1.0), clamp_reach="invalid"),
            lambda: set_hand_ik_target(self.armature, "L", (0.4, 0.0, 1.0), influence=1.5),
        ]

        for call in illegal_calls:
            with self.assertRaises((ValueError, TypeError)):
                call()

            # State must remain bit-for-bit unchanged
            self.assertEqual(ik_l.location, snap_ik_loc)
            self.assertEqual(ik_l.rotation_euler, snap_ik_rot)
            self.assertEqual(pole_l.location, snap_pole_loc)
            self.assertEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, snap_fore_inf)
            self.assertEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, snap_hand_inf)

            curr_state = get_arm_ik_state(self.armature, "L")
            self.assertEqual(curr_state["ik_influence"], snap_state["ik_influence"])
            self.assertEqual(curr_state["rot_influence"], snap_state["rot_influence"])

    # -------------------------------------------------------------------------
    # set_arm_ik_influence Validation Tests (TEST-18 to TEST-22)
    # -------------------------------------------------------------------------

    def test_18_influence_setter_rejects_invalid_side(self) -> None:
        """TEST-18: set_arm_ik_influence rejects invalid side identifiers."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        for invalid_side in ("INVALID", "X", "LEFT", "RIGHT", "", "  ", 42, None, []):
            with self.subTest(side=invalid_side):
                with self.assertRaises((ValueError, TypeError)):
                    set_arm_ik_influence(self.armature, invalid_side, 0.5)

    def test_19_influence_setter_rejects_non_finite_values(self) -> None:
        """TEST-19: set_arm_ik_influence rejects non-finite influence values."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        for non_finite in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(influence=non_finite):
                with self.assertRaises((ValueError, TypeError)):
                    set_arm_ik_influence(self.armature, "L", non_finite)

    def test_20_influence_setter_rejects_out_of_range_values(self) -> None:
        """TEST-20: set_arm_ik_influence rejects out-of-range influence values."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        for out_val in (-0.05, -1.0, 1.05, 2.0, 50.0):
            with self.subTest(influence=out_val):
                with self.assertRaises(ValueError):
                    set_arm_ik_influence(self.armature, "L", out_val)

    def test_21_influence_setter_invalid_input_has_zero_mutation(self) -> None:
        """TEST-21: set_arm_ik_influence invalid inputs cause zero mutation on existing influences."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        set_arm_ik_influence(self.armature, "L", 0.7)
        set_arm_ik_influence(self.armature, "R", 0.4)

        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        p_hand_r = self.armature.pose.bones["hand.R"]

        # Attempt illegal influence setters
        for illegal_args in (
            ("X", 0.9),
            ("L", float("nan")),
            ("R", float("inf")),
            ("BOTH", -0.2),
            ("BOTH", 1.8),
            (123, 0.5),
        ):
            with self.assertRaises((ValueError, TypeError)):
                set_arm_ik_influence(self.armature, illegal_args[0], illegal_args[1])

            # Verify influences remain unchanged
            self.assertAlmostEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.7, places=5)
            self.assertAlmostEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.7, places=5)
            self.assertAlmostEqual(p_fore_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.4, places=5)
            self.assertAlmostEqual(p_hand_r.constraints[HAND_ROT_CONSTRAINT_NAMES["R"]].influence, 0.4, places=5)

    def test_22_valid_influence_setter_preserves_left_right_independence(self) -> None:
        """TEST-22: set_arm_ik_influence preserves independent L/R state updates and accepts BOTH."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        p_hand_r = self.armature.pose.bones["hand.R"]

        # Set L to 0.8 -> R remains 0.5
        set_arm_ik_influence(self.armature, "L", 0.8)
        self.assertAlmostEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.8, places=5)
        self.assertAlmostEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.8, places=5)
        self.assertAlmostEqual(p_fore_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.5, places=5)
        self.assertAlmostEqual(p_hand_r.constraints[HAND_ROT_CONSTRAINT_NAMES["R"]].influence, 0.5, places=5)

        # Set R to 0.2 -> L remains 0.8
        set_arm_ik_influence(self.armature, "R", 0.2)
        self.assertAlmostEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.8, places=5)
        self.assertAlmostEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.8, places=5)
        self.assertAlmostEqual(p_fore_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.2, places=5)
        self.assertAlmostEqual(p_hand_r.constraints[HAND_ROT_CONSTRAINT_NAMES["R"]].influence, 0.2, places=5)

        # Set BOTH to 0.65 -> both become 0.65
        set_arm_ik_influence(self.armature, "BOTH", 0.65)
        self.assertAlmostEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.65, places=5)
        self.assertAlmostEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.65, places=5)
        self.assertAlmostEqual(p_fore_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.65, places=5)
        self.assertAlmostEqual(p_hand_r.constraints[HAND_ROT_CONSTRAINT_NAMES["R"]].influence, 0.65, places=5)

    # -------------------------------------------------------------------------
    # Hand Target Valid Invariant Tests (TEST-23 to TEST-24)
    # -------------------------------------------------------------------------

    def test_23_valid_hand_target_accepts_boolean_clamp_modes(self) -> None:
        """TEST-23: set_hand_ik_target accepts valid boolean clamp_reach modes (True and False)."""
        setup_arm_ik(self.armature, initial_influence=1.0)
        valid_pos = (0.35, -0.1, 1.1)

        state_true = set_hand_ik_target(self.armature, "L", valid_pos, clamp_reach=True)
        self.assertIsInstance(state_true["clamped_reach"], bool)

        state_false = set_hand_ik_target(self.armature, "L", valid_pos, clamp_reach=False)
        self.assertIsInstance(state_false["clamped_reach"], bool)
        self.assertFalse(state_false["clamped_reach"])

    def test_24_valid_hand_target_preserves_weight_consistency(self) -> None:
        """TEST-24: set_hand_ik_target preserves symmetric influence weight consistency across constraints."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        valid_pos = (0.35, -0.1, 1.1)
        target_inf = 0.65

        state = set_hand_ik_target(self.armature, "L", valid_pos, influence=target_inf)

        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]

        ik_inf = p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence
        rot_inf = p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence

        self.assertAlmostEqual(ik_inf, target_inf, places=5)
        self.assertAlmostEqual(rot_inf, target_inf, places=5)
        self.assertAlmostEqual(state["ik_influence"], target_inf, places=5)
        self.assertAlmostEqual(state["rot_influence"], target_inf, places=5)

    # -------------------------------------------------------------------------
    # Auto-init Preflight and Zero-Mutation Tests (TEST-25 to TEST-27, Task 10-B-2)
    # -------------------------------------------------------------------------

    def _capture_scene_snapshot(self) -> dict:
        """Capture comprehensive snapshot of scene objects, collections, and arm pose bones.

        Covers all elements specified in Task 10-B-2 Section 5:
        - Scene objects: name, type, parent, location, rotation_mode, euler, quat, axis_angle,
          scale, matrix_parent_inverse, matrix_world.
        - Collections: name, member objects.
        - PoseBones (upper_arm, forearm, hand L/R): location, rotation_mode, euler, quat,
          axis_angle, scale, matrix_basis, IK lock/limit properties, constraints configuration.
        """
        objs_snap = {}
        for obj in bpy.data.objects:
            objs_snap[obj.name] = {
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "location": tuple(round(v, 7) for v in obj.location),
                "rotation_mode": obj.rotation_mode,
                "rotation_euler": tuple(round(v, 7) for v in obj.rotation_euler),
                "rotation_quaternion": tuple(round(v, 7) for v in obj.rotation_quaternion),
                "rotation_axis_angle": tuple(round(v, 7) for v in obj.rotation_axis_angle),
                "scale": tuple(round(v, 7) for v in obj.scale),
                "matrix_parent_inverse": tuple(tuple(round(v, 7) for v in row) for row in obj.matrix_parent_inverse),
                "matrix_world": tuple(tuple(round(v, 7) for v in row) for row in obj.matrix_world),
            }

        cols_snap = {}
        for col in bpy.data.collections:
            cols_snap[col.name] = sorted([o.name for o in col.objects])

        bones_snap = {}
        arm = self.armature
        bone_names = ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R")
        for b_name in bone_names:
            pb = arm.pose.bones.get(b_name)
            if pb:
                con_list = []
                for con in pb.constraints:
                    target_name = con.target.name if hasattr(con, "target") and con.target else None
                    pole_name = con.pole_target.name if hasattr(con, "pole_target") and con.pole_target else None
                    inf = round(con.influence, 7) if hasattr(con, "influence") else None
                    con_list.append({
                        "name": con.name,
                        "type": con.type,
                        "target": target_name,
                        "pole_target": pole_name,
                        "influence": inf,
                    })
                bones_snap[b_name] = {
                    "location": tuple(round(v, 7) for v in pb.location),
                    "rotation_mode": pb.rotation_mode,
                    "rotation_euler": tuple(round(v, 7) for v in pb.rotation_euler),
                    "rotation_quaternion": tuple(round(v, 7) for v in pb.rotation_quaternion),
                    "rotation_axis_angle": tuple(round(v, 7) for v in pb.rotation_axis_angle),
                    "scale": tuple(round(v, 7) for v in pb.scale),
                    "matrix_basis": tuple(tuple(round(v, 7) for v in row) for row in pb.matrix_basis),
                    "lock_ik_x": getattr(pb, "lock_ik_x", None),
                    "lock_ik_y": getattr(pb, "lock_ik_y", None),
                    "lock_ik_z": getattr(pb, "lock_ik_z", None),
                    "use_ik_limit_x": getattr(pb, "use_ik_limit_x", None),
                    "use_ik_limit_y": getattr(pb, "use_ik_limit_y", None),
                    "use_ik_limit_z": getattr(pb, "use_ik_limit_z", None),
                    "ik_min_x": getattr(pb, "ik_min_x", None),
                    "ik_max_x": getattr(pb, "ik_max_x", None),
                    "ik_min_y": getattr(pb, "ik_min_y", None),
                    "ik_max_y": getattr(pb, "ik_max_y", None),
                    "ik_min_z": getattr(pb, "ik_min_z", None),
                    "ik_max_z": getattr(pb, "ik_max_z", None),
                    "constraints": con_list,
                }

        return {
            "objects": objs_snap,
            "collections": cols_snap,
            "pose_bones": bones_snap,
        }

    def _assert_scene_snapshot_unchanged(self, snap_before: dict, snap_after: dict) -> None:
        """Assert that scene objects, collections, and pose bones are bit-for-bit unchanged."""
        self.assertEqual(
            set(snap_before["objects"].keys()),
            set(snap_after["objects"].keys()),
            "Scene object set changed!"
        )
        for obj_name, b_info in snap_before["objects"].items():
            a_info = snap_after["objects"][obj_name]
            self.assertEqual(b_info, a_info, f"Object '{obj_name}' transform or state mutated!")

        self.assertEqual(
            snap_before["collections"],
            snap_after["collections"],
            "Collections mutated!"
        )
        self.assertEqual(
            snap_before["pose_bones"],
            snap_after["pose_bones"],
            "PoseBone transforms, IK limits, or constraints mutated!"
        )

    def test_25_auto_init_invalid_parent_has_zero_scene_mutation(self) -> None:
        """TEST-25: Uninitialized arm IK with invalid parent transform causes zero scene mutation.

        Preconditions:
        - Character and Armature built, leg IK setup, arm IK uninitialized.
        - Confirm HandIK.L, HandIK.R, ElbowPole.L, ElbowPole.R all do not exist.
        Setup:
        - Set initialization parent (root_obj) scale to non-conformal (1.0, 2.0, 1.0).
        - Update dependency graph.
        - Capture full scene snapshot.
        Action:
        - Call set_hand_ik_target with valid target coordinates.
        Assertions:
        - Raises ValueError from effective parent transform validation (non-conformal transform).
        - Post-call snapshot equals pre-call snapshot exactly.
        - No HandIK or ElbowPole empties exist.
        - No IK or HandRotation constraints exist on pose bones.
        """
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        root_obj = self.armature.parent or bpy.data.objects.get("CharacterRoot")
        self.assertIsNotNone(root_obj)
        root_obj.scale = (1.0, 2.0, 1.0)
        bpy.context.view_layer.update()

        snap_before = self._capture_scene_snapshot()

        with self.assertRaises(ValueError) as cm:
            set_hand_ik_target(
                self.armature,
                "L",
                world_xyz=(0.35, -0.1, 1.1),
                hand_rotation_deg=(0.0, 0.0, 0.0),
                influence=1.0,
            )

        self.assertIn("non-conformal transform", str(cm.exception))

        snap_after = self._capture_scene_snapshot()
        self._assert_scene_snapshot_unchanged(snap_before, snap_after)

        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]
            self.assertNotIn(ARM_IK_CONSTRAINT_NAMES[side], p_fore.constraints)
            self.assertNotIn(HAND_ROT_CONSTRAINT_NAMES[side], p_hand.constraints)

    def test_26_partial_init_invalid_new_parent_has_zero_scene_mutation(self) -> None:
        """TEST-26: Partially initialized arm IK with invalid new parent transform causes zero mutation.

        Preconditions:
        - Character and Armature built, leg IK setup.
        - Manually create a valid HandIK.L empty.
        - Confirm ElbowPole.L, HandIK.R, ElbowPole.R are missing.
        Setup:
        - Set initialization parent (root_obj) scale to reflection (-1.0, 1.0, 1.0).
        - Update dependency graph.
        - Capture full scene snapshot.
        Action:
        - Call set_hand_ik_target for L side with valid target coordinates.
        Assertions:
        - Raises ValueError from reflection rejection (det(A) < 0).
        - Post-call snapshot equals pre-call snapshot exactly.
        - ElbowPole.L is NOT created.
        - HandIK.R and ElbowPole.R are NOT created.
        - No constraints created on any pose bones.
        - Existing HandIK.L remains 100% unchanged.
        """
        hand_l = bpy.data.objects.new("HandIK.L", None)
        hand_l.empty_display_size = 0.08
        hand_l.empty_display_type = "SPHERE"
        hand_l.location = (0.35, -0.1, 1.1)
        bpy.context.scene.collection.objects.link(hand_l)

        for ctrl_name in ("HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        root_obj = self.armature.parent or bpy.data.objects.get("CharacterRoot")
        self.assertIsNotNone(root_obj)
        root_obj.scale = (-1.0, 1.0, 1.0)
        bpy.context.view_layer.update()

        snap_before = self._capture_scene_snapshot()

        with self.assertRaises(ValueError) as cm:
            set_hand_ik_target(
                self.armature,
                "L",
                world_xyz=(0.35, -0.1, 1.1),
                hand_rotation_deg=(0.0, 0.0, 0.0),
                influence=1.0,
            )

        self.assertIn("reflection", str(cm.exception).lower())

        snap_after = self._capture_scene_snapshot()
        self._assert_scene_snapshot_unchanged(snap_before, snap_after)

        self.assertIn("HandIK.L", bpy.data.objects)
        for ctrl_name in ("HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]
            self.assertNotIn(ARM_IK_CONSTRAINT_NAMES[side], p_fore.constraints)
            self.assertNotIn(HAND_ROT_CONSTRAINT_NAMES[side], p_hand.constraints)

    def test_27_valid_parent_first_time_auto_init_succeeds(self) -> None:
        """TEST-27: First-time auto-initialization succeeds under valid conformal parent transforms.

        Preconditions:
        - Character and Armature built, leg IK setup, arm IK uninitialized.
        - Confirm 4 arm IK controllers do not exist.
        Action:
        - Call set_hand_ik_target with valid target and default valid parent.
        Assertions:
        - API returns valid state dict.
        - All 4 controllers exist in bpy.data.objects.
        - IK and Copy Rotation constraints created on both L and R bones.
        - HandIK.L world translation matches applied_world.
        - ElbowPole.L coordinates are finite.
        - ArmIK and HandRotation constraint influences match requested influence.
        - Returned state matches scene data.
        """
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(ctrl_name, bpy.data.objects)

        target_xyz = (0.35, -0.1, 1.1)
        target_rot = (10.0, 20.0, 30.0)
        target_inf = 0.85

        state = set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_xyz,
            hand_rotation_deg=target_rot,
            influence=target_inf,
            clamp_reach=True,
        )

        self.assertIsInstance(state, dict)
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(ctrl_name, bpy.data.objects)

        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]
            self.assertIn(ARM_IK_CONSTRAINT_NAMES[side], p_fore.constraints)
            self.assertIn(HAND_ROT_CONSTRAINT_NAMES[side], p_hand.constraints)

        ik_l = bpy.data.objects["HandIK.L"]
        pole_l = bpy.data.objects["ElbowPole.L"]

        self.assertAlmostEqual(ik_l.matrix_world.translation.x, state["applied_world"].x, places=5)
        self.assertAlmostEqual(ik_l.matrix_world.translation.y, state["applied_world"].y, places=5)
        self.assertAlmostEqual(ik_l.matrix_world.translation.z, state["applied_world"].z, places=5)

        for c in pole_l.matrix_world.translation:
            self.assertTrue(math.isfinite(c))

        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_hand_l = self.armature.pose.bones["hand.L"]
        self.assertAlmostEqual(p_fore_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, target_inf, places=5)
        self.assertAlmostEqual(p_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, target_inf, places=5)
        self.assertAlmostEqual(state["ik_influence"], target_inf, places=5)
        self.assertAlmostEqual(state["rot_influence"], target_inf, places=5)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
