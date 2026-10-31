"""ProceduralAnimation — PKG-5 / 09 Lower-Limb IK Unit Tests.

Validates Foot IK Ground-Height Contract (FIND-R3-02):
- TEST-1: Flat ground compatibility (default ground_z=None uses world Z=0.0m).
- TEST-2: Root elevation decoupling (CharacterRoot elevation does NOT shift ground baseline).
- TEST-3: Depression / negative elevation terrain (ground_z < 0 correctly clamps to ground_z + ANKLE_REST_Z).
- TEST-4: Elevated platform terrain (ground_z > 0 correctly clamps to ground_z + ANKLE_REST_Z).
- TEST-5: clamp_ground=False bypass (no ground clamping applied regardless of ground_z).
- TEST-6: Root rotation and translation independence (ground clamping strictly uses world Z axis).
- TEST-7: Dual constraint interaction (reach and ground clamping simultaneously satisfied).
- TEST-8: Input validation (non-finite or non-numeric ground_z properly rejected).
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
from mathutils import Euler, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    MAX_LEG_REACH,
    MIN_LEG_REACH,
    POLE_TARGET_NAMES,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)


class TestLegIKGroundHeightContract(unittest.TestCase):
    """Test suite verifying ground height contract and root decoupling in set_foot_ik_target."""

    def setUp(self) -> None:
        """Reset Blender state and build clean character rig for each test."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.config = PipelineConfig()
        self.char_data = build_character(self.config)
        self.root = self.char_data["root"]
        self.parts = self.char_data["parts"]
        self.armature = build_rig(self.config)
        bind_character_to_rig(self.armature, self.parts)
        self.controls = setup_leg_ik(self.armature)

    def test_1_flat_ground_default_compatibility(self) -> None:
        """TEST-1: Default ground_z=None maintains historical flat ground at world Z=0.0m."""
        start_y = self.root.location.y

        # Subtest 1A: Target at exact rest ankle height (0.07m) -> not clamped
        res_rest = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y, ANKLE_REST_Z)
        )
        self.assertFalse(res_rest["clamped_ground"])
        self.assertAlmostEqual(res_rest["applied_world"].z, ANKLE_REST_Z, places=5)
        self.assertEqual(res_rest["ground_z"], 0.0)

        # Subtest 1B: Target above ground -> not clamped
        res_above = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y + 0.1, 0.20)
        )
        self.assertFalse(res_above["clamped_ground"])
        self.assertAlmostEqual(res_above["applied_world"].z, 0.20, places=5)

        # Subtest 1C: Target below ground -> clamped to 0.0 + ANKLE_REST_Z = 0.07m
        res_below = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y, -0.15)
        )
        self.assertTrue(res_below["clamped_ground"])
        self.assertAlmostEqual(res_below["applied_world"].z, ANKLE_REST_Z, places=5)
        self.assertEqual(res_below["ground_z"], 0.0)

    def test_2_root_elevation_decoupling(self) -> None:
        """TEST-2: CharacterRoot elevation does NOT shift ground baseline when ground_z is None."""
        start_y = self.root.location.y

        # Move root upwards to Z = 1.0m
        self.root.location = Vector((0.0, start_y, 1.0))
        bpy.context.view_layer.update()

        # Subtest 2A: With clamp_reach=False, requesting ground ankle height (0.07m).
        # In old code: min_ankle_z was root.z + 0.07 = 1.07m, which clamped 0.07m to 1.07m (clamped_ground=True)!
        # In new code: ground_z=None defaults to 0.0m, min_ankle_z is 0.07m.
        # Ankle height 0.07m is NOT clamped to 1.07m, and clamped_ground is False.
        res_free = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, ANKLE_REST_Z),
            clamp_reach=False,
            clamp_ground=True,
            ground_z=None,
        )
        self.assertFalse(
            res_free["clamped_ground"],
            "Target at Z=0.07m should NOT be clamped to CharacterRoot.z + ANKLE_REST_Z (1.07m)",
        )
        self.assertAlmostEqual(res_free["applied_world"].z, ANKLE_REST_Z, places=5)
        self.assertEqual(res_free["ground_z"], 0.0)

        # Subtest 2B: Even with clamp_reach=True, clamped_ground must reflect world ground (0.0m),
        # NOT CharacterRoot elevation. A target at 0.50m (above 0.07m) must NOT report clamped_ground=True.
        res_reach = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, 0.50),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=None,
        )
        self.assertFalse(
            res_reach["clamped_ground"],
            "Target at Z=0.50m is above flat ground min_ankle_z (0.07m); clamped_ground must be False",
        )

    def test_3_depression_negative_elevation_terrain(self) -> None:
        """TEST-3: Negative elevation terrain (ground_z=-0.20m) clamps to -0.20 + 0.07 = -0.13m."""
        start_y = self.root.location.y
        ground_z = -0.20
        expected_min_ankle_z = ground_z + ANKLE_REST_Z  # -0.13m

        # Subtest 3A: Target below depression floor (-0.25m) with clamp_reach=False -> clamped to -0.13m
        res_free = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.25),
            clamp_reach=False,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_free["clamped_ground"])
        self.assertAlmostEqual(res_free["applied_world"].z, expected_min_ankle_z, places=5)
        self.assertAlmostEqual(res_free["ground_z"], -0.20, places=5)

        # Subtest 3B: Root lowered into depression so -0.13m is naturally within reach
        self.root.location = Vector((0.0, start_y, -0.20))
        bpy.context.view_layer.update()
        res_in_reach = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.25),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_in_reach["clamped_ground"])
        self.assertAlmostEqual(res_in_reach["applied_world"].z, expected_min_ankle_z, places=5)

        # Subtest 3C: Target inside depression but above floor (-0.10m) -> not clamped by ground
        res_valid = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.10),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertFalse(res_valid["clamped_ground"])
        self.assertAlmostEqual(res_valid["applied_world"].z, -0.10, places=5)

    def test_4_elevated_platform_terrain(self) -> None:
        """TEST-4: Elevated platform terrain (ground_z=0.50m) clamps to 0.50 + 0.07 = 0.57m."""
        start_y = self.root.location.y
        ground_z = 0.50
        expected_min_ankle_z = ground_z + ANKLE_REST_Z  # 0.57m

        # Subtest 4A: Target below platform floor (0.35m) with clamp_reach=False -> clamped to 0.57m
        res_free = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, 0.35),
            clamp_reach=False,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_free["clamped_ground"])
        self.assertAlmostEqual(res_free["applied_world"].z, expected_min_ankle_z, places=5)
        self.assertAlmostEqual(res_free["ground_z"], 0.50, places=5)

        # Subtest 4B: Elevate root to Z=0.40m so leg naturally reaches platform
        self.root.location = Vector((0.0, start_y, 0.40))
        bpy.context.view_layer.update()
        res_in_reach = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, 0.35),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_in_reach["clamped_ground"])
        self.assertAlmostEqual(res_in_reach["applied_world"].z, expected_min_ankle_z, places=5)

        # Subtest 4C: Target above platform floor (0.65m) -> not clamped
        res_valid = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, 0.65),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertFalse(res_valid["clamped_ground"])
        self.assertAlmostEqual(res_valid["applied_world"].z, 0.65, places=5)

    def test_5_clamp_ground_false_bypass(self) -> None:
        """TEST-5: clamp_ground=False completely bypasses ground clamping regardless of ground_z."""
        start_y = self.root.location.y

        # Subtest 5A: Below flat ground (Z = -0.10m) with clamp_reach=False, clamp_ground=False
        res_flat = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.10),
            clamp_reach=False,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertFalse(res_flat["clamped_ground"])
        self.assertAlmostEqual(res_flat["applied_world"].z, -0.10, places=5)

        # Subtest 5B: Below elevated ground (ground_z=0.40m, target=0.20m) with clamp_ground=False
        res_elev = set_foot_ik_target(
            self.armature,
            "R",
            (HIP_X_OFFSET, start_y, 0.20),
            clamp_reach=False,
            clamp_ground=False,
            ground_z=0.40,
        )
        self.assertFalse(res_elev["clamped_ground"])
        self.assertAlmostEqual(res_elev["applied_world"].z, 0.20, places=5)

        # Subtest 5C: With clamp_reach=True where target is within reach
        self.root.location = Vector((0.0, start_y, -0.15))
        bpy.context.view_layer.update()
        res_reach = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.05),
            clamp_reach=True,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertFalse(res_reach["clamped_ground"])
        self.assertAlmostEqual(res_reach["applied_world"].z, -0.05, places=5)

    def test_6_root_rotation_independence(self) -> None:
        """TEST-6: Ground clamping strictly uses world Z axis, unaffected by CharacterRoot rotation."""
        # Apply complex 3D rotation and translation to CharacterRoot
        self.root.location = Vector((1.2, -5.0, 0.35))
        self.root.rotation_euler = Euler(
            (math.radians(15.0), math.radians(20.0), math.radians(45.0)), "XYZ"
        )
        bpy.context.view_layer.update()

        ground_z = -0.10
        expected_min_ankle_z = ground_z + ANKLE_REST_Z  # -0.03m
        requested_world = (1.0, -5.0, -0.20)

        # Subtest 6A: Pure ground clamping check with clamp_reach=False
        res_free = set_foot_ik_target(
            self.armature,
            "L",
            requested_world,
            clamp_reach=False,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_free["clamped_ground"])
        # World Z must be exactly min_ankle_z regardless of root rotation
        self.assertAlmostEqual(res_free["applied_world"].z, expected_min_ankle_z, places=5)

        # Subtest 6B: Target placed in reach directly under rotated hip
        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head
        test_ground_z = hip_world.z - 0.70
        test_min_ankle_z = test_ground_z + ANKLE_REST_Z
        res_reach = set_foot_ik_target(
            self.armature,
            "L",
            (hip_world.x, hip_world.y, test_min_ankle_z - 0.05),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=test_ground_z,
        )
        self.assertTrue(res_reach["clamped_ground"])
        self.assertAlmostEqual(res_reach["applied_world"].z, test_min_ankle_z, places=5)

    def test_7_dual_constraint_reach_and_ground_interaction(self) -> None:
        """TEST-7: Boundary interaction when target triggers both reach and ground clamping."""
        start_y = self.root.location.y
        ground_z = 0.0
        min_ankle_z = ground_z + ANKLE_REST_Z

        # Subtest 7A: Target far forward and below ground
        extreme_tgt = (-HIP_X_OFFSET, start_y + 2.5, -0.50)
        res_dual = set_foot_ik_target(
            self.armature,
            "L",
            extreme_tgt,
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_dual["clamped_reach"])
        self.assertTrue(res_dual["clamped_ground"])

        # Applied target must satisfy both constraints:
        # 1. Z >= min_ankle_z
        self.assertGreaterEqual(res_dual["applied_world"].z, min_ankle_z - 1e-5)
        # 2. Euclidean distance from hip <= MAX_LEG_REACH
        dist_from_hip = (res_dual["applied_world"] - res_dual["hip_world"]).length
        self.assertLessEqual(dist_from_hip, MAX_LEG_REACH + 1e-4)

        # FootIK.L location must match applied_world result
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        self.assertLess(
            (ik_obj.location - res_dual["applied_world"]).length,
            1e-5,
            "FootIK.L location must match res_dual applied_world result",
        )

        # Subtest 7B: Target directly under hip (near zero distance) triggering MIN_LEG_REACH
        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head
        res_min = set_foot_ik_target(
            self.armature,
            "L",
            (hip_world.x, hip_world.y, hip_world.z - 0.05),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )
        self.assertTrue(res_min["clamped_reach"])
        dist_min = (res_min["applied_world"] - res_min["hip_world"]).length
        self.assertGreaterEqual(dist_min, MIN_LEG_REACH - 1e-4)
        self.assertLess(
            (ik_obj.location - res_min["applied_world"]).length,
            1e-5,
            "FootIK.L location must match res_min applied_world result",
        )

    def test_8_ground_z_input_validation(self) -> None:
        """TEST-8: Non-finite or invalid type ground_z raises appropriate exceptions."""
        start_y = self.root.location.y
        tgt = (-HIP_X_OFFSET, start_y, 0.20)

        with self.assertRaises(TypeError):
            set_foot_ik_target(self.armature, "L", tgt, ground_z="invalid")

        with self.assertRaises(ValueError):
            set_foot_ik_target(self.armature, "L", tgt, ground_z=float("nan"))

        with self.assertRaises(ValueError):
            set_foot_ik_target(self.armature, "L", tgt, ground_z=float("inf"))

    def test_9_high_platform_infeasible(self) -> None:
        """TEST-9: Infeasible high platform (min_ankle_z > hip_world.z + MAX_LEG_REACH) raises GROUND_REACH_INFEASIBLE."""
        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head
        infeasible_ground_z = 2.00

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES["L"]]
        orig_ik_loc = ik_obj.location.copy()
        orig_pole_loc = pole_obj.location.copy()

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (hip_world.x, hip_world.y, 2.10),
                clamp_reach=True,
                clamp_ground=True,
                ground_z=infeasible_ground_z,
            )

        err_msg = str(ctx.exception)
        self.assertIn("GROUND_REACH_INFEASIBLE", err_msg)
        self.assertIn("min_ankle_z", err_msg)
        self.assertIn("hip_world.z", err_msg)
        self.assertIn("MAX_LEG_REACH", err_msg)

        # Confirm IK targets were NOT modified
        self.assertAlmostEqual((ik_obj.location - orig_ik_loc).length, 0.0, places=5)
        self.assertAlmostEqual((pole_obj.location - orig_pole_loc).length, 0.0, places=5)

    def test_10_max_reach_and_ground_boundary(self) -> None:
        """TEST-10: Target exceeding reach and below ground clamps to valid ground-reach boundary."""
        start_y = self.root.location.y
        ground_z = 0.0
        min_ankle_z = ground_z + ANKLE_REST_Z

        # Target far forward (dist > 2.0m) and below ground (-0.30m)
        extreme_tgt = (-HIP_X_OFFSET, start_y + 2.0, -0.30)
        res = set_foot_ik_target(
            self.armature,
            "L",
            extreme_tgt,
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )

        self.assertTrue(res["clamped_reach"])
        self.assertTrue(res["clamped_ground"])
        self.assertTrue(res["constraints_satisfied"])

        # Applied target must satisfy both constraints
        self.assertGreaterEqual(res["applied_world"].z, min_ankle_z - 1e-5)
        final_dist = (res["applied_world"] - res["hip_world"]).length
        self.assertLessEqual(final_dist, MAX_LEG_REACH + 1e-4)
        self.assertGreaterEqual(final_dist, MIN_LEG_REACH - 1e-4)

        # Verify actual controller position
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        self.assertAlmostEqual((ik_obj.location - res["applied_world"]).length, 0.0, places=5)

    def test_11_min_reach_and_ground_boundary(self) -> None:
        """TEST-11: Target inside MIN_LEG_REACH where vertical elevation penetrates or violates reach."""
        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head

        # Platform elevated such that |zeta_min| = |z_min - h_z| < MIN_LEG_REACH
        elevated_ground_z = hip_world.z - ANKLE_REST_Z
        min_ankle_z = elevated_ground_z + ANKLE_REST_Z

        # Target requested directly at hip (dist = 0.0 < MIN_LEG_REACH)
        res = set_foot_ik_target(
            self.armature,
            "L",
            (hip_world.x, hip_world.y, hip_world.z),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=elevated_ground_z,
        )

        self.assertTrue(res["clamped_reach"])
        self.assertTrue(res["constraints_satisfied"])
        self.assertGreaterEqual(res["applied_world"].z, min_ankle_z - 1e-5)

        final_dist = (res["applied_world"] - res["hip_world"]).length
        self.assertGreaterEqual(final_dist, MIN_LEG_REACH - 1e-4)
        self.assertLessEqual(final_dist, MAX_LEG_REACH + 1e-4)

    def test_12_exact_boundary(self) -> None:
        """TEST-12: Exact feasibility boundary min_ankle_z = hip_world.z + MAX_LEG_REACH and perturbations."""
        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head

        # Exact boundary: min_ankle_z = hip_world.z + MAX_LEG_REACH
        exact_ground_z = hip_world.z + MAX_LEG_REACH - ANKLE_REST_Z
        expected_z = hip_world.z + MAX_LEG_REACH

        # 1. Exact boundary must succeed with single valid solution point
        res = set_foot_ik_target(
            self.armature,
            "L",
            (hip_world.x, hip_world.y, expected_z),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=exact_ground_z,
        )
        self.assertTrue(res["constraints_satisfied"])
        self.assertAlmostEqual(res["applied_world"].x, hip_world.x, places=5)
        self.assertAlmostEqual(res["applied_world"].y, hip_world.y, places=5)
        self.assertAlmostEqual(res["applied_world"].z, expected_z, places=5)

        # 2. Micro-perturbation above boundary (+1e-3m) must be rejected
        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (hip_world.x, hip_world.y, expected_z + 0.01),
                clamp_reach=True,
                clamp_ground=True,
                ground_z=exact_ground_z + 0.001,
            )
        self.assertIn("GROUND_REACH_INFEASIBLE", str(ctx.exception))

        # 3. Micro-perturbation below boundary (-1e-3m) must succeed
        res_below = set_foot_ik_target(
            self.armature,
            "L",
            (hip_world.x, hip_world.y, expected_z - 0.001),
            clamp_reach=True,
            clamp_ground=True,
            ground_z=exact_ground_z - 0.001,
        )
        self.assertTrue(res_below["constraints_satisfied"])

    def test_13_arbitrary_root_rotation(self) -> None:
        """TEST-13: Combined Yaw, Pitch, Roll root rotation uses strictly world-space Z and Euclidean distance."""
        self.root.location = Vector((0.5, -4.0, 0.30))
        self.root.rotation_euler = Euler(
            (math.radians(20.0), math.radians(-15.0), math.radians(35.0)), "XYZ"
        )
        bpy.context.view_layer.update()

        p_thigh = self.armature.pose.bones["thigh.L"]
        hip_world = self.armature.matrix_world @ p_thigh.head
        ground_z = hip_world.z - 0.50
        min_ankle_z = ground_z + ANKLE_REST_Z

        req_world = (hip_world.x + 0.2, hip_world.y + 0.2, min_ankle_z - 0.15)
        res = set_foot_ik_target(
            self.armature,
            "L",
            req_world,
            clamp_reach=True,
            clamp_ground=True,
            ground_z=ground_z,
        )

        self.assertTrue(res["clamped_ground"])
        self.assertTrue(res["constraints_satisfied"])
        self.assertAlmostEqual(res["applied_world"].z, min_ankle_z, places=5)
        dist = (res["applied_world"] - res["hip_world"]).length
        self.assertLessEqual(dist, MAX_LEG_REACH + 1e-4)
        self.assertGreaterEqual(dist, MIN_LEG_REACH - 1e-4)

    def test_14_left_right_leg_symmetry(self) -> None:
        """TEST-14: Mirrored geometric conditions between Left and Right legs produce symmetric results."""
        start_y = self.root.location.y
        ground_z = 0.0

        # Subtest 14A: In-reach forward targets
        res_l = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y + 0.20, 0.25), ground_z=ground_z
        )
        res_r = set_foot_ik_target(
            self.armature, "R", (HIP_X_OFFSET, start_y + 0.20, 0.25), ground_z=ground_z
        )

        self.assertTrue(res_l["constraints_satisfied"])
        self.assertTrue(res_r["constraints_satisfied"])
        self.assertAlmostEqual(res_l["applied_world"].z, res_r["applied_world"].z, places=5)
        self.assertAlmostEqual(res_l["hip_to_target_dist_m"], res_r["hip_to_target_dist_m"], places=5)

        # Subtest 14B: Mirrored clamped extreme targets
        res_l_clamp = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y + 2.0, -0.20), ground_z=ground_z
        )
        res_r_clamp = set_foot_ik_target(
            self.armature, "R", (HIP_X_OFFSET, start_y + 2.0, -0.20), ground_z=ground_z
        )

        self.assertTrue(res_l_clamp["constraints_satisfied"])
        self.assertTrue(res_r_clamp["constraints_satisfied"])
        self.assertAlmostEqual(res_l_clamp["applied_world"].z, res_r_clamp["applied_world"].z, places=5)
        self.assertAlmostEqual(res_l_clamp["hip_to_target_dist_m"], res_r_clamp["hip_to_target_dist_m"], places=5)

    def test_15_disabled_constraints(self) -> None:
        """TEST-15: Disabled constraints (clamp_ground=False, clamp_reach=False) are strictly bypassed."""
        start_y = self.root.location.y

        # Subtest 15A: clamp_ground=False, clamp_reach=True
        self.root.location = Vector((0.0, start_y, -0.15))
        bpy.context.view_layer.update()
        res_no_ground = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.05),
            clamp_reach=True,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertFalse(res_no_ground["clamped_ground"])
        self.assertAlmostEqual(res_no_ground["applied_world"].z, -0.05, places=5)

        # Subtest 15B: clamp_ground=True, clamp_reach=False
        res_no_reach = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 2.0, 0.20),
            clamp_reach=False,
            clamp_ground=True,
            ground_z=0.0,
        )
        self.assertFalse(res_no_reach["clamped_reach"])
        self.assertAlmostEqual(res_no_reach["applied_world"].y, start_y + 2.0, places=5)

        # Subtest 15C: Both False preserves exact requested position
        unconstrained_tgt = (-HIP_X_OFFSET - 0.5, start_y + 3.0, -0.80)
        res_none = set_foot_ik_target(
            self.armature,
            "L",
            unconstrained_tgt,
            clamp_reach=False,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertFalse(res_none["clamped_reach"])
        self.assertFalse(res_none["clamped_ground"])
        self.assertAlmostEqual((res_none["applied_world"] - Vector(unconstrained_tgt)).length, 0.0, places=5)

    def test_16_failure_state_atomicity(self) -> None:
        """TEST-16: Infeasible call leaves FootIK, KneePole, and bone local poses strictly unmodified."""
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES["L"]]
        p_thigh = self.armature.pose.bones["thigh.L"]
        p_shin = self.armature.pose.bones["shin.L"]
        p_foot = self.armature.pose.bones["foot.L"]

        orig_ik_loc = ik_obj.location.copy()
        orig_ik_rot = ik_obj.rotation_euler.copy()
        orig_pole_loc = pole_obj.location.copy()
        orig_thigh_rot = p_thigh.rotation_euler.copy()
        orig_shin_rot = p_shin.rotation_euler.copy()
        orig_foot_rot = p_foot.rotation_euler.copy()

        with self.assertRaises(ValueError):
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, self.root.location.y, 2.5),
                clamp_reach=True,
                clamp_ground=True,
                ground_z=2.5,
            )

        # Assert no state was modified
        self.assertAlmostEqual((ik_obj.location - orig_ik_loc).length, 0.0, places=6)
        self.assertLess(max(abs(a - b) for a, b in zip(ik_obj.rotation_euler, orig_ik_rot)), 1e-6)
        self.assertAlmostEqual((pole_obj.location - orig_pole_loc).length, 0.0, places=6)
        self.assertLess(max(abs(a - b) for a, b in zip(p_thigh.rotation_euler, orig_thigh_rot)), 1e-6)
        self.assertLess(max(abs(a - b) for a, b in zip(p_shin.rotation_euler, orig_shin_rot)), 1e-6)
        self.assertLess(max(abs(a - b) for a, b in zip(p_foot.rotation_euler, orig_foot_rot)), 1e-6)

    def test_17_final_geometric_telemetry(self) -> None:
        """TEST-17: Accurate reporting of constraints_satisfied, ground_clearance_m, and hip_to_target_dist_m."""
        start_y = self.root.location.y

        # Subtest 17A: Normal legal target
        res_legal = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y + 0.1, 0.20), ground_z=0.0
        )
        self.assertTrue(res_legal["constraints_satisfied"])
        expected_clearance = 0.20 - ANKLE_REST_Z
        self.assertAlmostEqual(res_legal["ground_clearance_m"], expected_clearance, places=5)
        expected_dist = (res_legal["applied_world"] - res_legal["hip_world"]).length
        self.assertAlmostEqual(res_legal["hip_to_target_dist_m"], expected_dist, places=5)

        # Subtest 17B: Clamped target
        res_clamp = set_foot_ik_target(
            self.armature, "L", (-HIP_X_OFFSET, start_y + 2.0, -0.30), ground_z=0.0
        )
        self.assertTrue(res_clamp["constraints_satisfied"])
        self.assertAlmostEqual(
            res_clamp["ground_clearance_m"], res_clamp["applied_world"].z - ANKLE_REST_Z, places=5
        )
        self.assertAlmostEqual(
            res_clamp["hip_to_target_dist_m"], (res_clamp["applied_world"] - res_clamp["hip_world"]).length, places=5
        )

    def test_18_original_legal_target_zero_degradation(self) -> None:
        """TEST-18: Original legal standing and swing targets undergo zero degradation or unwanted displacement."""
        start_y = self.root.location.y

        # Stance neutral target
        stance_tgt = (-HIP_X_OFFSET, start_y, ANKLE_REST_Z)
        res_stance = set_foot_ik_target(self.armature, "L", stance_tgt, ground_z=0.0)
        self.assertFalse(res_stance["clamped_ground"])
        self.assertFalse(res_stance["clamped_reach"])
        self.assertAlmostEqual((res_stance["applied_world"] - Vector(stance_tgt)).length, 0.0, places=5)

        # Mid-swing forward step target
        swing_tgt = (-HIP_X_OFFSET, start_y + 0.22, 0.18)
        res_swing = set_foot_ik_target(self.armature, "L", swing_tgt, ground_z=0.0)
        self.assertFalse(res_swing["clamped_ground"])
        self.assertFalse(res_swing["clamped_reach"])
        self.assertAlmostEqual((res_swing["applied_world"] - Vector(swing_tgt)).length, 0.0, places=5)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
