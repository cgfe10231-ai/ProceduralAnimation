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
import random
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


def independent_numerical_oracle(
    hip_world: Vector,
    requested_world: Vector,
    ground_z: float | None,
    clamp_reach: bool,
    clamp_ground: bool,
    grid_res_m: float = 0.003,
) -> dict:
    """Independent numerical reference Oracle for 3D Ground x Reach constraint solving."""
    min_ankle_z = (0.0 if ground_z is None else ground_z) + ANKLE_REST_Z
    zeta_min = min_ankle_z - hip_world.z

    req = Vector(requested_world)
    v_from_hip = req - hip_world
    horiz_vec = Vector((v_from_hip.x, v_from_hip.y, 0.0))
    rho_r = horiz_vec.length
    z_r = v_from_hip.z

    if rho_r > 1e-6:
        u_horiz = horiz_vec / rho_r
    else:
        u_horiz = Vector((0.0, 1.0, 0.0))

    if not clamp_reach and not clamp_ground:
        return {
            "feasible": True,
            "applied_world": req.copy(),
            "dist_to_req": 0.0,
        }

    if clamp_ground and not clamp_reach:
        applied = req.copy()
        if applied.z < min_ankle_z:
            applied.z = min_ankle_z
        return {
            "feasible": True,
            "applied_world": applied,
            "dist_to_req": (applied - req).length,
        }

    if clamp_reach and not clamp_ground:
        d = v_from_hip.length
        if d > MAX_LEG_REACH:
            applied = hip_world + (v_from_hip / d) * MAX_LEG_REACH if d > 1e-6 else hip_world + Vector((0.0, 0.0, -1.0)) * MAX_LEG_REACH
        elif d < MIN_LEG_REACH:
            applied = hip_world + (v_from_hip / d) * MIN_LEG_REACH if d > 1e-6 else hip_world + Vector((0.0, 0.0, -1.0)) * MIN_LEG_REACH
        else:
            applied = req.copy()
        return {
            "feasible": True,
            "applied_world": applied,
            "dist_to_req": (applied - req).length,
        }

    # Mode D: Both enabled
    if zeta_min > MAX_LEG_REACH + 1e-6:
        return {"feasible": False, "applied_world": None, "dist_to_req": float("inf")}

    best_rho = 0.0
    best_z = 0.0
    min_d_sq = float("inf")

    # 1. Check if requested is already feasible
    if z_r >= zeta_min - 1e-6:
        d_req = math.sqrt(rho_r * rho_r + z_r * z_r)
        if MIN_LEG_REACH - 1e-6 <= d_req <= MAX_LEG_REACH + 1e-6:
            return {
                "feasible": True,
                "applied_world": req.copy(),
                "dist_to_req": 0.0,
            }

    # 2. Dense Boundary search:
    # A. Ground segment z = zeta_min
    if -MAX_LEG_REACH - 1e-6 <= zeta_min <= MAX_LEG_REACH + 1e-6:
        rho_g_max = math.sqrt(max(0.0, MAX_LEG_REACH**2 - zeta_min**2))
        rho_g_min = math.sqrt(max(0.0, MIN_LEG_REACH**2 - zeta_min**2)) if abs(zeta_min) <= MIN_LEG_REACH else 0.0
        n_pts = max(10, int((rho_g_max - rho_g_min) / 0.001))
        for i in range(n_pts + 1):
            rho = rho_g_min + (rho_g_max - rho_g_min) * (i / n_pts)
            z = zeta_min
            d_sq = (rho - rho_r)**2 + (z - z_r)**2
            if d_sq < min_d_sq:
                min_d_sq = d_sq
                best_rho, best_z = rho, z

    # B. Outer arc
    sin_theta_min = max(-1.0, min(1.0, zeta_min / MAX_LEG_REACH))
    theta_start = math.asin(sin_theta_min)
    theta_end = math.pi - theta_start
    n_pts_arc = 1500
    for i in range(n_pts_arc + 1):
        th = theta_start + (theta_end - theta_start) * (i / n_pts_arc)
        z = MAX_LEG_REACH * math.sin(th)
        rho = MAX_LEG_REACH * math.cos(th)
        if rho < 0.0:
            continue
        d_sq = (rho - rho_r)**2 + (z - z_r)**2
        if d_sq < min_d_sq:
            min_d_sq = d_sq
            best_rho, best_z = rho, z

    # C. Inner arc
    if zeta_min <= MIN_LEG_REACH:
        sin_in_min = max(-1.0, min(1.0, zeta_min / MIN_LEG_REACH)) if abs(zeta_min) <= MIN_LEG_REACH else -1.0
        th_in_start = math.asin(sin_in_min)
        th_in_end = math.pi - th_in_start
        for i in range(n_pts_arc + 1):
            th = th_in_start + (th_in_end - th_in_start) * (i / n_pts_arc)
            z = MIN_LEG_REACH * math.sin(th)
            rho = MIN_LEG_REACH * math.cos(th)
            if rho < 0.0:
                continue
            d_sq = (rho - rho_r)**2 + (z - z_r)**2
            if d_sq < min_d_sq:
                min_d_sq = d_sq
                best_rho, best_z = rho, z

    # D. 2D grid interior check
    z_lo = max(zeta_min, -MAX_LEG_REACH)
    z_hi = MAX_LEG_REACH
    nz = max(5, int((z_hi - z_lo) / grid_res_m))
    nrho = max(5, int(MAX_LEG_REACH / grid_res_m))
    for iz in range(nz + 1):
        z = z_lo + (z_hi - z_lo) * (iz / nz)
        for irho in range(nrho + 1):
            rho = MAX_LEG_REACH * (irho / nrho)
            r2 = rho * rho + z * z
            if MIN_LEG_REACH**2 - 1e-5 <= r2 <= MAX_LEG_REACH**2 + 1e-5:
                d_sq = (rho - rho_r)**2 + (z - z_r)**2
                if d_sq < min_d_sq:
                    min_d_sq = d_sq
                    best_rho, best_z = rho, z

    applied_world = Vector((
        hip_world.x + u_horiz.x * best_rho,
        hip_world.y + u_horiz.y * best_rho,
        hip_world.z + best_z,
    ))

    return {
        "feasible": True,
        "applied_world": applied_world,
        "dist_to_req": math.sqrt(min_d_sq),
    }


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

    def _verify_8_fields(
        self,
        res: dict,
        ik_obj: bpy.types.Object,
        side: str,
        min_ankle_z: float,
    ) -> None:
        """Helper verifying all 8 fields of set_foot_ik_target return dictionary."""
        self.assertIn("requested_world", res)
        self.assertIn("applied_world", res)
        self.assertIn("hip_world", res)
        self.assertIn("clamped_reach", res)
        self.assertIn("clamped_ground", res)
        self.assertIn("ground_z", res)
        self.assertIn("constraints_satisfied", res)
        self.assertIn("ground_clearance_m", res)
        self.assertIn("hip_to_target_dist_m", res)

        # FootIK world translation must match applied_world
        ik_world_pos = ik_obj.matrix_world.translation
        self.assertAlmostEqual((ik_world_pos - res["applied_world"]).length, 0.0, places=5)

        # Hip world translation must match pose bone
        p_thigh = self.armature.pose.bones[f"thigh.{side}"]
        actual_hip = self.armature.matrix_world @ p_thigh.head
        self.assertAlmostEqual((actual_hip - res["hip_world"]).length, 0.0, places=5)

        # Length must match
        expected_len = (res["applied_world"] - res["hip_world"]).length
        self.assertAlmostEqual(res["hip_to_target_dist_m"], expected_len, places=5)

        # Ground clearance must match
        expected_clearance = res["applied_world"].z - min_ankle_z
        self.assertAlmostEqual(res["ground_clearance_m"], expected_clearance, places=5)

    def test_19_complete_geometric_boundary_taxonomy(self) -> None:
        """TEST-19: Complete geometric boundary taxonomy covering Categories A through T."""
        start_y = self.root.location.y
        p_thigh_l = self.armature.pose.bones["thigh.L"]
        hip_l = self.armature.matrix_world @ p_thigh_l.head
        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]

        # Category A: Infeasible domain (zeta_min > MAX_LEG_REACH)
        with self.assertRaises(ValueError) as cm:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, start_y, 2.5),
                ground_z=hip_l.z + MAX_LEG_REACH - ANKLE_REST_Z + 0.1,
            )
        self.assertIn("GROUND_REACH_INFEASIBLE", str(cm.exception))

        # Category B: Top single apex point (zeta_min = MAX_LEG_REACH)
        gz_b = hip_l.z + MAX_LEG_REACH - ANKLE_REST_Z
        res_b = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.2, hip_l.z + MAX_LEG_REACH + 0.1),
            ground_z=gz_b,
        )
        self.assertTrue(res_b["constraints_satisfied"])
        self._verify_8_fields(res_b, ik_l, "L", gz_b + ANKLE_REST_Z)
        self.assertAlmostEqual(res_b["applied_world"].z, hip_l.z + MAX_LEG_REACH, places=5)
        self.assertAlmostEqual(res_b["applied_world"].x, hip_l.x, places=5)
        self.assertAlmostEqual(res_b["applied_world"].y, hip_l.y, places=5)

        # Category C: High platform intersection (0 < zeta_min < MAX_LEG_REACH)
        zeta_c = 0.40
        gz_c = hip_l.z + zeta_c - ANKLE_REST_Z
        res_c = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 1.0, hip_l.z + 0.60),
            ground_z=gz_c,
        )
        self.assertTrue(res_c["constraints_satisfied"])
        self._verify_8_fields(res_c, ik_l, "L", gz_c + ANKLE_REST_Z)
        self.assertGreaterEqual(res_c["applied_world"].z, gz_c + ANKLE_REST_Z - 1e-5)
        self.assertLessEqual(res_c["hip_to_target_dist_m"], MAX_LEG_REACH + 1e-4)

        # Category D: Ground passes through hip (zeta_min = 0.0)
        gz_d = hip_l.z - ANKLE_REST_Z
        res_d = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.3, hip_l.z - 0.2),
            ground_z=gz_d,
        )
        self.assertTrue(res_d["constraints_satisfied"])
        self._verify_8_fields(res_d, ik_l, "L", gz_d + ANKLE_REST_Z)
        self.assertAlmostEqual(res_d["applied_world"].z, hip_l.z, places=5)
        self.assertGreaterEqual(res_d["hip_to_target_dist_m"], MIN_LEG_REACH - 1e-4)
        self.assertLessEqual(res_d["hip_to_target_dist_m"], MAX_LEG_REACH + 1e-4)

        # Category E: Ground cuts inner sphere (0 < |zeta_min| < MIN_LEG_REACH)
        zeta_e = -0.10
        gz_e = hip_l.z + zeta_e - ANKLE_REST_Z
        res_e = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, hip_l.z - 0.05),
            ground_z=gz_e,
        )
        self.assertTrue(res_e["constraints_satisfied"])
        self._verify_8_fields(res_e, ik_l, "L", gz_e + ANKLE_REST_Z)
        self.assertGreaterEqual(res_e["applied_world"].z, gz_e + ANKLE_REST_Z - 1e-5)
        self.assertGreaterEqual(res_e["hip_to_target_dist_m"], MIN_LEG_REACH - 1e-4)

        # Category F: Inner sphere bottom tangent point (zeta_min = -MIN_LEG_REACH)
        zeta_f = -MIN_LEG_REACH
        gz_f = hip_l.z + zeta_f - ANKLE_REST_Z
        res_f = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, hip_l.z - 0.30),
            ground_z=gz_f,
        )
        self.assertTrue(res_f["constraints_satisfied"])
        self._verify_8_fields(res_f, ik_l, "L", gz_f + ANKLE_REST_Z)

        # Category G: Ground cuts outer sphere below inner sphere (-MAX_LEG_REACH < zeta_min < -MIN_LEG_REACH)
        zeta_g = -0.50
        gz_g = hip_l.z + zeta_g - ANKLE_REST_Z
        res_g = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.1, hip_l.z - 0.70),
            ground_z=gz_g,
        )
        self.assertTrue(res_g["constraints_satisfied"])
        self._verify_8_fields(res_g, ik_l, "L", gz_g + ANKLE_REST_Z)
        self.assertAlmostEqual(res_g["applied_world"].z, gz_g + ANKLE_REST_Z, places=5)

        # Category H: Outer sphere bottom tangent point (zeta_min = -MAX_LEG_REACH)
        zeta_h = -MAX_LEG_REACH
        gz_h = hip_l.z + zeta_h - ANKLE_REST_Z
        res_h = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.3, hip_l.z - 0.20),
            ground_z=gz_h,
        )
        self.assertTrue(res_h["constraints_satisfied"])
        self._verify_8_fields(res_h, ik_l, "L", gz_h + ANKLE_REST_Z)

        # Category I: Extremely low ground (zeta_min < -MAX_LEG_REACH)
        gz_i = hip_l.z - MAX_LEG_REACH - 1.0
        res_i = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.3, hip_l.z - 0.20),
            ground_z=gz_i,
        )
        self.assertTrue(res_i["constraints_satisfied"])
        self._verify_8_fields(res_i, ik_l, "L", gz_i + ANKLE_REST_Z)
        self.assertFalse(res_i["clamped_ground"])

        # Category J: Requested point equals hip
        res_j = set_foot_ik_target(
            self.armature,
            "L",
            tuple(hip_l),
            ground_z=0.0,
        )
        self.assertTrue(res_j["constraints_satisfied"])
        self._verify_8_fields(res_j, ik_l, "L", ANKLE_REST_Z)
        self.assertAlmostEqual(res_j["hip_to_target_dist_m"], MIN_LEG_REACH, places=5)
        self.assertTrue(res_j["clamped_reach"])

        # Category K: Requested point itself strictly legal
        legal_tgt = (-HIP_X_OFFSET, start_y + 0.2, 0.25)
        res_k = set_foot_ik_target(self.armature, "L", legal_tgt, ground_z=0.0)
        self.assertTrue(res_k["constraints_satisfied"])
        self._verify_8_fields(res_k, ik_l, "L", ANKLE_REST_Z)
        self.assertFalse(res_k["clamped_ground"])
        self.assertFalse(res_k["clamped_reach"])
        self.assertAlmostEqual((res_k["applied_world"] - Vector(legal_tgt)).length, 0.0, places=6)

        # Category L: Target below ground and too far away (steep downward with cutting ground)
        gz_l = 0.20
        min_z_l = gz_l + ANKLE_REST_Z
        res_l = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 0.10, 0.0),
            ground_z=gz_l,
        )
        self.assertTrue(res_l["constraints_satisfied"])
        self._verify_8_fields(res_l, ik_l, "L", min_z_l)
        self.assertTrue(res_l["clamped_ground"])
        self.assertAlmostEqual(res_l["applied_world"].z, min_z_l, places=5)

        # Category M: Target below ground and too close
        res_m = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.10),
            ground_z=0.0,
        )
        self.assertTrue(res_m["constraints_satisfied"])
        self._verify_8_fields(res_m, ik_l, "L", ANKLE_REST_Z)
        self.assertTrue(res_m["clamped_ground"])
        self.assertGreaterEqual(res_m["hip_to_target_dist_m"], MIN_LEG_REACH - 1e-4)

        # Category N: Target above ground but too far away
        res_n = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 1.5, 0.30),
            ground_z=0.0,
        )
        self.assertTrue(res_n["constraints_satisfied"])
        self._verify_8_fields(res_n, ik_l, "L", ANKLE_REST_Z)
        self.assertTrue(res_n["clamped_reach"])
        self.assertAlmostEqual(res_n["hip_to_target_dist_m"], MAX_LEG_REACH, places=5)

        # Category O: Target above ground but too close
        res_o = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, hip_l.z - 0.05),
            ground_z=0.0,
        )
        self.assertTrue(res_o["constraints_satisfied"])
        self._verify_8_fields(res_o, ik_l, "L", ANKLE_REST_Z)
        self.assertTrue(res_o["clamped_reach"])
        self.assertAlmostEqual(res_o["hip_to_target_dist_m"], MIN_LEG_REACH, places=5)

        # Category P: Only Ground enabled
        res_p = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 2.0, -0.20),
            clamp_reach=False,
            clamp_ground=True,
            ground_z=0.0,
        )
        self.assertTrue(res_p["constraints_satisfied"])
        self._verify_8_fields(res_p, ik_l, "L", ANKLE_REST_Z)
        self.assertTrue(res_p["clamped_ground"])
        self.assertFalse(res_p["clamped_reach"])
        self.assertAlmostEqual(res_p["applied_world"].z, ANKLE_REST_Z, places=5)
        self.assertGreater(res_p["hip_to_target_dist_m"], MAX_LEG_REACH)

        # Category Q: Only Reach enabled
        res_q = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y, -0.20),
            clamp_reach=True,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertTrue(res_q["constraints_satisfied"])
        self._verify_8_fields(res_q, ik_l, "L", ANKLE_REST_Z)
        self.assertFalse(res_q["clamped_ground"])
        self.assertTrue(res_q["clamped_reach"])
        self.assertLess(res_q["applied_world"].z, ANKLE_REST_Z)

        # Category R: Both disabled
        res_r = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, start_y + 3.0, -1.0),
            clamp_reach=False,
            clamp_ground=False,
            ground_z=0.0,
        )
        self.assertTrue(res_r["constraints_satisfied"])
        self._verify_8_fields(res_r, ik_l, "L", ANKLE_REST_Z)
        self.assertFalse(res_r["clamped_ground"])
        self.assertFalse(res_r["clamped_reach"])
        self.assertAlmostEqual(res_r["applied_world"].z, -1.0, places=5)

        # Category S: Left and right leg mirroring
        res_s_l = set_foot_ik_target(self.armature, "L", (-HIP_X_OFFSET, start_y + 0.3, 0.15), ground_z=0.0)
        ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
        res_s_r = set_foot_ik_target(self.armature, "R", (+HIP_X_OFFSET, start_y + 0.3, 0.15), ground_z=0.0)
        self._verify_8_fields(res_s_l, ik_l, "L", ANKLE_REST_Z)
        self._verify_8_fields(res_s_r, ik_r, "R", ANKLE_REST_Z)
        self.assertAlmostEqual(res_s_l["applied_world"].x, -res_s_r["applied_world"].x, places=5)
        self.assertAlmostEqual(res_s_l["applied_world"].y, res_s_r["applied_world"].y, places=5)
        self.assertAlmostEqual(res_s_l["applied_world"].z, res_s_r["applied_world"].z, places=5)

        # Category T: Root translation, yaw, pitch, roll
        self.root.location = Vector((2.0, 3.0, 0.5))
        self.root.rotation_euler = Euler((math.radians(20), math.radians(-15), math.radians(35)), "XYZ")
        bpy.context.view_layer.update()
        p_thigh_rot = self.armature.pose.bones["thigh.L"]
        hip_rot = self.armature.matrix_world @ p_thigh_rot.head

        # T1: Ground plane within reach under rotated hip
        gz_t1 = hip_rot.z - 0.65
        min_z_t1 = gz_t1 + ANKLE_REST_Z
        res_t1 = set_foot_ik_target(
            self.armature,
            "L",
            (hip_rot.x, hip_rot.y, gz_t1 - 0.10),
            ground_z=gz_t1,
        )
        self.assertTrue(res_t1["constraints_satisfied"])
        self._verify_8_fields(res_t1, ik_l, "L", min_z_t1)
        self.assertTrue(res_t1["clamped_ground"])
        self.assertAlmostEqual(res_t1["applied_world"].z, min_z_t1, places=5)

        # T2: Flat ground 0.0m with elevated root, target below ground
        res_t2 = set_foot_ik_target(
            self.armature,
            "L",
            (hip_rot.x, hip_rot.y + 0.3, -0.10),
            ground_z=0.0,
        )
        self.assertTrue(res_t2["constraints_satisfied"])
        self._verify_8_fields(res_t2, ik_l, "L", ANKLE_REST_Z)
        self.assertGreaterEqual(res_t2["applied_world"].z, ANKLE_REST_Z - 1e-5)
        self.assertLessEqual(res_t2["hip_to_target_dist_m"], MAX_LEG_REACH + 1e-4)

    def test_20_independent_numerical_oracle_parametric(self) -> None:
        """TEST-20: Independent numerical Oracle cross-validation across parametric grid and random trials."""
        start_y = self.root.location.y
        p_thigh_l = self.armature.pose.bones["thigh.L"]
        hip_l = self.armature.matrix_world @ p_thigh_l.head

        ground_heights = [-0.20, 0.0, 0.30]
        clamp_modes = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]
        test_offsets = [
            (0.0, 0.20, 0.10),    # inside shell
            (0.0, 1.20, -0.40),   # far and below
            (0.0, 0.05, -0.50),   # steep downward
            (0.0, 0.0, -0.05),    # inside inner sphere
            (0.0, 1.50, 0.50),    # far forward above ground
        ]

        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]

        for gz in ground_heights:
            for cr, cg in clamp_modes:
                for dx, dy, dz in test_offsets:
                    tgt = (hip_l.x + dx, hip_l.y + dy, dz)
                    res = set_foot_ik_target(
                        self.armature,
                        "L",
                        tgt,
                        clamp_reach=cr,
                        clamp_ground=cg,
                        ground_z=gz,
                    )
                    oracle_res = independent_numerical_oracle(
                        hip_l, Vector(tgt), gz, cr, cg
                    )
                    self.assertTrue(res["constraints_satisfied"])
                    self._verify_8_fields(res, ik_l, "L", gz + ANKLE_REST_Z)

                    # Compare distance to requested between analytical and oracle
                    d_prod = (res["applied_world"] - Vector(tgt)).length
                    d_oracle = oracle_res["dist_to_req"]
                    self.assertLess(
                        abs(d_prod - d_oracle),
                        0.005,
                        f"Mismatch with Oracle: d_prod={d_prod:.5f}, d_oracle={d_oracle:.5f} for tgt={tgt}, gz={gz}, cr={cr}, cg={cg}",
                    )

        # 30 Pseudo-random trials with fixed seed
        rng = random.Random(42)
        for i in range(30):
            gz = rng.uniform(-0.3, 0.4)
            cr = rng.choice([True, False])
            cg = rng.choice([True, False])
            side = rng.choice(["L", "R"])
            p_thigh_s = self.armature.pose.bones[f"thigh.{side}"]
            hip_s = self.armature.matrix_world @ p_thigh_s.head
            ik_s = bpy.data.objects[IK_TARGET_NAMES[side]]

            tgt = (
                hip_s.x + rng.uniform(-0.4, 0.4),
                hip_s.y + rng.uniform(-0.5, 1.0),
                rng.uniform(-0.5, 0.8),
            )

            res = set_foot_ik_target(
                self.armature,
                side,
                tgt,
                clamp_reach=cr,
                clamp_ground=cg,
                ground_z=gz,
            )
            oracle_res = independent_numerical_oracle(
                hip_s, Vector(tgt), gz, cr, cg
            )
            self.assertTrue(res["constraints_satisfied"])
            self._verify_8_fields(res, ik_s, side, gz + ANKLE_REST_Z)

            d_prod = (res["applied_world"] - Vector(tgt)).length
            d_oracle = oracle_res["dist_to_req"]
            self.assertLess(
                abs(d_prod - d_oracle),
                0.005,
                f"Random trial {i} mismatch: d_prod={d_prod:.5f}, d_oracle={d_oracle:.5f}",
            )


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
