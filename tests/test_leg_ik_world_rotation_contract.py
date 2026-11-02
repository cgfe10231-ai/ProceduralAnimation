"""ProceduralAnimation — PKG-5 / 09-B Unit Tests.

Validates Lower-Limb IK World Rotation Contract and Controller Lifecycle Closure:
- TEST-01: Parentless world rotation (parent=None, non-zero XYZ rotation matches world request).
- TEST-02: Non-zero parent Yaw (parent has yaw rotation, controller world orientation matches world request).
- TEST-03: Composite rotation (composite parent yaw/pitch/roll + composite target yaw/pitch/roll).
- TEST-04: World rotation composition order (proper 3D rotation math, no Euler subtraction, foot_rotation_deg=None level neutral).
- TEST-05: Unlock world matrix preservation (FootIK location/rotation/scale and KneePole location/rotation/scale preserved, parentless).
- TEST-06: Bilateral lifecycle (setup -> lock -> unlock -> normal IK target -> reset preserves parentless invariant).
- TEST-07: Legacy compatibility default call (unlock_foot_contact without reparent_to_root defaults to parentless).
- TEST-08: Explicit illegal request (reparent_to_root=True raises ValueError, preserves transforms, and prevents reparenting).
- TEST-09: Failure atomicity (Phase A failure leaves FootIK, KneePole, and armature pose pristine across all 16 matrix elements).
- TEST-10: Bilateral symmetry & independence (Left and Right controllers operate without mutual contamination).
- TEST-11: Combination of non-zero parent rotation and non-identity matrix_parent_inverse.
- TEST-12: Parent uniform scale achieves requested rotation, and non-uniform scale shear boundary is detected and rejected.
- TEST-13: Unlock handles legacy parented controllers with non-unit scale and non-zero rotation faithfully.
- TEST-14: Shear parent transform rejection (effective parent transform with shear is rejected in Phase A with full failure atomicity).
- TEST-15: Singular parent transform rejection (det == 0 is rejected in Phase A with full failure atomicity).
- TEST-16: Reflection parent transform rejection (det < 0 is rejected in Phase A with full failure atomicity).
- TEST-17: Phase B transaction rollback fault injection (catches fault during Phase B, restores all 4 controllers and 6 bones atomically, and re-raises).
- TEST-18: Small-scale positive uniform scale (A = 0.001*R, det=1e-9 > 0 is accepted without scale rejection).
- TEST-19: Near-threshold non-conformal matrix rejection (1e-6 < epsilon < 1e-4 rejected by Phase A).
- TEST-20: Conformal boundary tolerance acceptance (epsilon <= 1e-6 accepted by Phase A).
- TEST-21: KneePole independent shear rejection (FootIK valid, KneePole shear rejected with KneePole.L in exception).
- TEST-22: Unlock FootIK shear rejection (unlock_foot_contact detects FootIK shear > 1e-4, raises RuntimeError, keeps state pristine and locked).
- TEST-23: Unlock KneePole independent shear rejection (unlock_foot_contact detects KneePole shear > 1e-4 while FootIK is valid, raises RuntimeError, keeps state pristine and locked).
- TEST-24: Unlock transaction rollback and fault injection (injected failure during unlock rolls back all 4 controllers and 6 bones atomically, preserves lock and metadata).
- TEST-25: Effective parent non-finite rejection (_validate_effective_parent_transform rejects NaN and Inf elements).
- TEST-26: Effective parent non-affine rejection (_validate_effective_parent_transform rejects non-affine last row).
- TEST-27: Effective parent degenerate scale rejection (_validate_effective_parent_transform rejects s^2 <= 1e-12 despite det > 0).
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from unittest.mock import patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.foot_contact import (
    evaluate_foot_support,
    get_foot_support_state,
    lock_foot_contact,
    unlock_foot_contact,
)
from src.rig.ik import (
    ANKLE_REST_Z,
    HIP_X_OFFSET,
    IK_TARGET_NAMES,
    POLE_TARGET_NAMES,
    _validate_effective_parent_transform,
    reset_leg_ik,
    set_foot_ik_target,
    setup_leg_ik,
)


def _quat_angle_diff(q1: Quaternion, q2: Quaternion) -> float:
    """Return shortest angular difference in radians between two rotations."""
    # Ensure unit quaternions
    q1_n = q1.normalized()
    q2_n = q2.normalized()
    diff = q1_n.rotation_difference(q2_n)
    return float(diff.angle)


def _max_mat_diff(m1: Matrix, m2: Matrix) -> float:
    """Return maximum absolute difference across all 16 elements of two 4x4 matrices."""
    return max(abs(m1[r][c] - m2[r][c]) for r in range(4) for c in range(4))


_LEG_BONES_6 = (
    "thigh.L", "thigh.R",
    "shin.L", "shin.R",
    "foot.L", "foot.R",
)
_LEG_CTRLS_4 = (
    "FootIK.L", "FootIK.R",
    "KneePole.L", "KneePole.R",
)


def _capture_rig_state(armature: bpy.types.Object) -> dict:
    """Capture full world and local transform state of all 4 controllers (15 fields) and 6 pose bones (8 fields)."""
    state = {"ctrls": {}, "bones": {}}
    for name in _LEG_CTRLS_4:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            state["ctrls"][name] = {
                "matrix_world": obj.matrix_world.copy(),
                "location": obj.location.copy(),
                "rotation_mode": obj.rotation_mode,
                "rotation_euler": obj.rotation_euler.copy(),
                "rotation_quaternion": obj.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(obj.rotation_axis_angle),
                "scale": obj.scale.copy(),
                "parent": obj.parent,
                "matrix_parent_inverse": obj.matrix_parent_inverse.copy(),
                "has_is_locked": "is_locked" in obj,
                "is_locked": obj.get("is_locked"),
                "delta_location": obj.delta_location.copy(),
                "delta_rotation_euler": obj.delta_rotation_euler.copy(),
                "delta_rotation_quaternion": obj.delta_rotation_quaternion.copy(),
                "delta_scale": obj.delta_scale.copy(),
            }
    for name in _LEG_BONES_6:
        p_bone = armature.pose.bones.get(name)
        if p_bone is not None:
            state["bones"][name] = {
                "matrix": p_bone.matrix.copy(),
                "matrix_basis": p_bone.matrix_basis.copy(),
                "location": p_bone.location.copy(),
                "rotation_mode": p_bone.rotation_mode,
                "rotation_euler": p_bone.rotation_euler.copy(),
                "rotation_quaternion": p_bone.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(p_bone.rotation_axis_angle),
                "scale": p_bone.scale.copy(),
            }
    return state


def _assert_rig_state_identical(test_case: unittest.TestCase, saved_state: dict, tol: float = 1e-6) -> None:
    """Assert all 4 controllers (15 fields) and 6 leg pose bones (8 fields) match the saved state within tol."""
    for name, snap in saved_state["ctrls"].items():
        obj = bpy.data.objects.get(name)
        test_case.assertIsNotNone(obj, f"Controller '{name}' missing")
        mat_diff = _max_mat_diff(obj.matrix_world, snap["matrix_world"])
        test_case.assertLess(mat_diff, tol, f"Controller '{name}' matrix_world modified: diff {mat_diff:.6e} >= {tol}")
        test_case.assertLess((obj.location - snap["location"]).length, tol, f"Controller '{name}' location modified")
        test_case.assertEqual(obj.rotation_mode, snap["rotation_mode"], f"Controller '{name}' rotation_mode modified")
        test_case.assertLess(
            (Vector(obj.rotation_euler) - Vector(snap["rotation_euler"])).length,
            tol,
            f"Controller '{name}' rotation_euler modified",
        )
        test_case.assertLess(
            _quat_angle_diff(obj.rotation_quaternion, snap["rotation_quaternion"]),
            tol,
            f"Controller '{name}' rotation_quaternion modified",
        )
        test_case.assertEqual(
            tuple(obj.rotation_axis_angle),
            snap["rotation_axis_angle"],
            f"Controller '{name}' rotation_axis_angle modified",
        )
        test_case.assertLess((obj.scale - snap["scale"]).length, tol, f"Controller '{name}' scale modified")
        test_case.assertIs(obj.parent, snap["parent"], f"Controller '{name}' parent modified")
        p_inv_diff = _max_mat_diff(obj.matrix_parent_inverse, snap["matrix_parent_inverse"])
        test_case.assertLess(p_inv_diff, tol, f"Controller '{name}' matrix_parent_inverse modified: diff {p_inv_diff:.6e} >= {tol}")
        test_case.assertEqual("is_locked" in obj, snap["has_is_locked"], f"Controller '{name}' has_is_locked modified")
        test_case.assertEqual(obj.get("is_locked"), snap["is_locked"], f"Controller '{name}' is_locked modified")
        test_case.assertLess((obj.delta_location - snap["delta_location"]).length, tol, f"Controller '{name}' delta_location modified")
        test_case.assertLess(
            (Vector(obj.delta_rotation_euler) - Vector(snap["delta_rotation_euler"])).length,
            tol,
            f"Controller '{name}' delta_rotation_euler modified",
        )
        test_case.assertLess(
            _quat_angle_diff(obj.delta_rotation_quaternion, snap["delta_rotation_quaternion"]),
            tol,
            f"Controller '{name}' delta_rotation_quaternion modified",
        )
        test_case.assertLess((obj.delta_scale - snap["delta_scale"]).length, tol, f"Controller '{name}' delta_scale modified")

    armature = bpy.data.objects.get("CharacterArmature")
    for name, snap in saved_state["bones"].items():
        p_bone = armature.pose.bones.get(name)
        test_case.assertIsNotNone(p_bone, f"Pose bone '{name}' missing")
        mat_diff = _max_mat_diff(p_bone.matrix, snap["matrix"])
        test_case.assertLess(mat_diff, tol, f"Pose bone '{name}' matrix modified: diff {mat_diff:.6e} >= {tol}")
        mat_basis_diff = _max_mat_diff(p_bone.matrix_basis, snap["matrix_basis"])
        test_case.assertLess(mat_basis_diff, tol, f"Pose bone '{name}' matrix_basis modified: diff {mat_basis_diff:.6e} >= {tol}")
        test_case.assertLess((p_bone.location - snap["location"]).length, tol, f"Pose bone '{name}' location modified")
        test_case.assertEqual(p_bone.rotation_mode, snap["rotation_mode"], f"Pose bone '{name}' rotation_mode modified")
        test_case.assertLess(
            (Vector(p_bone.rotation_euler) - Vector(snap["rotation_euler"])).length,
            tol,
            f"Pose bone '{name}' rotation_euler modified",
        )
        test_case.assertLess(
            _quat_angle_diff(p_bone.rotation_quaternion, snap["rotation_quaternion"]),
            tol,
            f"Pose bone '{name}' rotation_quaternion modified",
        )
        test_case.assertEqual(
            tuple(p_bone.rotation_axis_angle),
            snap["rotation_axis_angle"],
            f"Pose bone '{name}' rotation_axis_angle modified",
        )
        test_case.assertLess((p_bone.scale - snap["scale"]).length, tol, f"Pose bone '{name}' scale modified")


class TestLegIKWorldRotationContract(unittest.TestCase):
    """Test suite verifying world rotation accuracy, controller lifecycle, and failure atomicity."""

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
        bpy.context.view_layer.update()

    def test_01_parentless_world_rotation(self) -> None:
        """TEST-01: When controller parent is None, foot_rotation_deg directly sets world rotation."""
        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must be parentless")

            # World target position and non-zero 3D rotation
            target_pos = (
                -HIP_X_OFFSET if side == "L" else HIP_X_OFFSET,
                self.root.location.y + 0.15,
                0.20,
            )
            req_rot_deg = (15.0, -20.0, 35.0)

            res = set_foot_ik_target(
                self.armature,
                side,
                target_pos,
                foot_rotation_deg=req_rot_deg,
                clamp_ground=False,
                clamp_reach=False,
            )
            bpy.context.view_layer.update()

            expected_world_rot = Euler(
                (math.radians(v) for v in req_rot_deg), "XYZ"
            ).to_quaternion()
            actual_world_rot = ik_obj.matrix_world.to_quaternion()

            diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
            self.assertLess(
                diff_rad,
                1e-4,
                f"Side {side}: World rotation angular error {math.degrees(diff_rad):.4f} deg exceeds tolerance",
            )
            self.assertIsNone(ik_obj.parent)

    def test_02_nonzero_parent_yaw(self) -> None:
        """TEST-02: When parent has non-zero yaw, set_foot_ik_target achieves the requested world rotation."""
        # Create an explicit parent object with yaw rotation
        parent_empty = bpy.data.objects.new("TestParentYaw", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.rotation_euler = Euler((0.0, 0.0, math.radians(45.0)), "XYZ")
        bpy.context.view_layer.update()

        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            # Attach to test parent with identity parent inverse to ensure parent transform actively applies
            ik_obj.parent = parent_empty
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            bpy.context.view_layer.update()

            eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
            eff_angle = _quat_angle_diff(eff_parent.to_quaternion(), Quaternion((1.0, 0.0, 0.0, 0.0)))
            self.assertGreater(eff_angle, 0.1, "Effective parent rotation must be non-zero")

            target_pos = (
                -HIP_X_OFFSET if side == "L" else HIP_X_OFFSET,
                -7.85,
                0.18,
            )
            req_rot_deg = (0.0, 0.0, 30.0)  # World yaw target of 30 deg

            set_foot_ik_target(
                self.armature,
                side,
                target_pos,
                foot_rotation_deg=req_rot_deg,
                clamp_ground=False,
                clamp_reach=False,
            )
            bpy.context.view_layer.update()

            expected_world_rot = Euler(
                (math.radians(v) for v in req_rot_deg), "XYZ"
            ).to_quaternion()
            actual_world_rot = ik_obj.matrix_world.to_quaternion()

            diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
            self.assertLess(
                diff_rad,
                1e-4,
                f"Side {side}: World rotation under parent yaw failed, error={math.degrees(diff_rad):.4f} deg",
            )

            # Cleanup
            ik_obj.parent = None
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)

        bpy.data.objects.remove(parent_empty)

    def test_03_composite_rotation(self) -> None:
        """TEST-03: Combined non-zero yaw, pitch, roll on parent and target simultaneously."""
        parent_empty = bpy.data.objects.new("TestParentComposite", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.5, -7.5, 0.2))
        parent_empty.rotation_euler = Euler(
            (math.radians(12.0), math.radians(-18.0), math.radians(40.0)), "XYZ"
        )
        bpy.context.view_layer.update()

        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            ik_obj.parent = parent_empty
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            bpy.context.view_layer.update()

            # Verify parent rotation has non-zero yaw, pitch, roll
            parent_rot_euler = parent_empty.rotation_euler
            self.assertGreater(abs(parent_rot_euler.x), 0.1)
            self.assertGreater(abs(parent_rot_euler.y), 0.1)
            self.assertGreater(abs(parent_rot_euler.z), 0.1)

            eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
            eff_angle = _quat_angle_diff(eff_parent.to_quaternion(), Quaternion((1.0, 0.0, 0.0, 0.0)))
            self.assertGreater(eff_angle, 0.1, "Effective parent rotation must be non-zero")

            target_pos = (
                -HIP_X_OFFSET if side == "L" else HIP_X_OFFSET,
                -7.80,
                0.22,
            )
            req_rot_deg = (-10.0, 25.0, -30.0)

            set_foot_ik_target(
                self.armature,
                side,
                target_pos,
                foot_rotation_deg=req_rot_deg,
                clamp_ground=False,
                clamp_reach=False,
            )
            bpy.context.view_layer.update()

            expected_world_rot = Euler(
                (math.radians(v) for v in req_rot_deg), "XYZ"
            ).to_quaternion()
            actual_world_rot = ik_obj.matrix_world.to_quaternion()

            diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
            self.assertLess(
                diff_rad,
                1e-4,
                f"Side {side}: Composite 3D rotation failed, error={math.degrees(diff_rad):.4f} deg",
            )

            # Cleanup
            ik_obj.parent = None
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)

        bpy.data.objects.remove(parent_empty)

    def test_04_world_rotation_composition_order_and_none_default(self) -> None:
        """TEST-04: Verify proper 3D rotation matrix inversion (not Euler subtraction) and foot_rotation_deg=None level neutral."""
        parent_empty = bpy.data.objects.new("TestParentOrder", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        # Highly non-trivial non-commuting Euler angles
        parent_rot_deg = (30.0, 45.0, 60.0)
        parent_empty.rotation_euler = Euler(
            (math.radians(v) for v in parent_rot_deg), "XYZ"
        )
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        eff_angle = _quat_angle_diff(eff_parent.to_quaternion(), Quaternion((1.0, 0.0, 0.0, 0.0)))
        self.assertGreater(eff_angle, 0.1, "Effective parent rotation must be non-zero")

        # Part A: With non-zero target rotation
        target_rot_deg = (15.0, -30.0, 20.0)
        set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.9, 0.15),
            foot_rotation_deg=target_rot_deg,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        expected_q = Euler((math.radians(v) for v in target_rot_deg), "XYZ").to_quaternion()
        actual_q = ik_obj.matrix_world.to_quaternion()
        diff_rad = _quat_angle_diff(expected_q, actual_q)
        self.assertLess(diff_rad, 1e-4)

        # Confirm that naïve Euler subtraction (target - parent) WOULD NOT match actual 3D orientation
        naive_subtraction_euler = Euler(
            (math.radians(t - p) for t, p in zip(target_rot_deg, parent_rot_deg)), "XYZ"
        )
        naive_q = (parent_empty.matrix_world.to_3x3() @ naive_subtraction_euler.to_matrix()).to_quaternion()
        naive_diff = _quat_angle_diff(expected_q, naive_q)
        self.assertGreater(
            naive_diff,
            0.05,
            "Naïve Euler subtraction must differ significantly from true non-commutative 3D rotation",
        )

        # Part B: With foot_rotation_deg=None, foot must adhere to neutral level world orientation (0, 0, 0)
        set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.9, 0.15),
            foot_rotation_deg=None,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        neutral_q = Quaternion((1.0, 0.0, 0.0, 0.0))  # Identity rotation
        actual_neutral_q = ik_obj.matrix_world.to_quaternion()
        neutral_diff_rad = _quat_angle_diff(neutral_q, actual_neutral_q)
        self.assertLess(
            neutral_diff_rad,
            1e-4,
            f"foot_rotation_deg=None must produce neutral world rotation (0,0,0), got error={math.degrees(neutral_diff_rad):.4f} deg",
        )

        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_05_unlock_world_matrix_preservation(self) -> None:
        """TEST-05: Unlock preserves world position, orientation, scale, and full 4x4 matrix without jump."""
        for side in ("L", "R"):
            contact_xyz = (-HIP_X_OFFSET if side == "L" else HIP_X_OFFSET, -7.90, 0.0)
            target_rot_deg = (5.0, -8.0, 12.0)

            # Lock foot in ground support
            lock_res = lock_foot_contact(
                self.armature,
                side,
                contact_world_xyz=contact_xyz,
                target_rotation_deg=target_rot_deg,
            )
            bpy.context.view_layer.update()

            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

            self.assertTrue(ik_obj.get("is_locked", False))
            self.assertIsNone(ik_obj.parent)
            self.assertIsNone(pole_obj.parent)

            # Record world transforms while locked
            locked_ik_mat = ik_obj.matrix_world.copy()
            locked_pole_mat = pole_obj.matrix_world.copy()

            # Unlock foot contact
            unlock_res = unlock_foot_contact(self.armature, side)
            bpy.context.view_layer.update()

            unlocked_ik_mat = ik_obj.matrix_world.copy()
            unlocked_pole_mat = pole_obj.matrix_world.copy()

            # Check 4x4 matrix max element diff
            ik_mat_diff = _max_mat_diff(locked_ik_mat, unlocked_ik_mat)
            pole_mat_diff = _max_mat_diff(locked_pole_mat, unlocked_pole_mat)
            self.assertLess(ik_mat_diff, 1e-5, f"Side {side}: FootIK 4x4 matrix error {ik_mat_diff:.6e} exceeds 1e-5")
            self.assertLess(pole_mat_diff, 1e-5, f"Side {side}: KneePole 4x4 matrix error {pole_mat_diff:.6e} exceeds 1e-5")

            # Check positions
            ik_loc_jump = (unlocked_ik_mat.translation - locked_ik_mat.translation).length
            pole_loc_jump = (unlocked_pole_mat.translation - locked_pole_mat.translation).length
            self.assertLess(ik_loc_jump, 1e-5, f"Side {side}: FootIK world position jumped by {ik_loc_jump:.6f}m")
            self.assertLess(pole_loc_jump, 1e-5, f"Side {side}: KneePole world position jumped by {pole_loc_jump:.6f}m")

            # Check rotations
            ik_rot_diff = _quat_angle_diff(locked_ik_mat.to_quaternion(), unlocked_ik_mat.to_quaternion())
            self.assertLess(ik_rot_diff, 1e-4, f"Side {side}: FootIK world orientation jumped by {math.degrees(ik_rot_diff):.4f} deg")

            # Check scale
            ik_scale_diff = (unlocked_ik_mat.to_scale() - locked_ik_mat.to_scale()).length
            pole_scale_diff = (unlocked_pole_mat.to_scale() - locked_pole_mat.to_scale()).length
            self.assertLess(ik_scale_diff, 1e-5, f"Side {side}: FootIK scale jumped by {ik_scale_diff:.6e}")
            self.assertLess(pole_scale_diff, 1e-5, f"Side {side}: KneePole scale jumped by {pole_scale_diff:.6e}")

            # Check architectural invariants
            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must remain parentless after unlock")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} must remain parentless after unlock")
            self.assertFalse(ik_obj.get("is_locked", False), "is_locked must be False after unlock")
            self.assertFalse(unlock_res["is_locked"], "unlock return state must report is_locked=False")

    def test_06_bilateral_lifecycle_parentless_invariant(self) -> None:
        """TEST-06: Full lifecycle: setup -> lock -> unlock -> normal IK target -> reset preserves parent is None."""
        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

            # 1. After setup
            self.assertIsNone(ik_obj.parent, "Setup phase: FootIK must be parentless")
            self.assertIsNone(pole_obj.parent, "Setup phase: KneePole must be parentless")

            # 2. Lock
            contact_xyz = (-HIP_X_OFFSET if side == "L" else HIP_X_OFFSET, -8.0, 0.0)
            lock_foot_contact(self.armature, side, contact_world_xyz=contact_xyz)
            bpy.context.view_layer.update()
            self.assertIsNone(ik_obj.parent, "Lock phase: FootIK must be parentless")
            self.assertIsNone(pole_obj.parent, "Lock phase: KneePole must be parentless")

            # 3. Unlock
            unlock_foot_contact(self.armature, side)
            bpy.context.view_layer.update()
            self.assertIsNone(ik_obj.parent, "Unlock phase: FootIK must be parentless")
            self.assertIsNone(pole_obj.parent, "Unlock phase: KneePole must be parentless")

            # 4. Normal IK target
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET if side == "L" else HIP_X_OFFSET, -7.85, 0.15),
                foot_rotation_deg=(10.0, 0.0, 0.0),
            )
            bpy.context.view_layer.update()
            self.assertIsNone(ik_obj.parent, "Normal IK phase: FootIK must be parentless")
            self.assertIsNone(pole_obj.parent, "Normal IK phase: KneePole must be parentless")

            # 5. Reset
            reset_leg_ik(self.armature)
            bpy.context.view_layer.update()
            self.assertIsNone(ik_obj.parent, "Reset phase: FootIK must be parentless")
            self.assertIsNone(pole_obj.parent, "Reset phase: KneePole must be parentless")

    def test_07_legacy_compatibility_default_call(self) -> None:
        """TEST-07: unlock_foot_contact(arm, side) without reparent_to_root maintains parentless invariant."""
        side = "L"
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

        lock_foot_contact(self.armature, side, contact_world_xyz=(-HIP_X_OFFSET, -8.0, 0.0))
        self.assertTrue(ik_obj.get("is_locked", False))

        # Call with only armature and side (omitting reparent_to_root parameter)
        unlock_foot_contact(self.armature, side)
        bpy.context.view_layer.update()

        self.assertIsNone(ik_obj.parent)
        self.assertIsNone(pole_obj.parent)
        self.assertFalse(ik_obj.get("is_locked", False))

    def test_08_explicit_illegal_request(self) -> None:
        """TEST-08: Explicitly passing reparent_to_root=True must raise ValueError, preserve transforms, and not reparent."""
        side = "R"
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

        lock_foot_contact(self.armature, side, contact_world_xyz=(HIP_X_OFFSET, -8.0, 0.0))

        locked_ik_mat = ik_obj.matrix_world.copy()
        locked_pole_mat = pole_obj.matrix_world.copy()

        with self.assertRaises(ValueError) as ctx:
            unlock_foot_contact(self.armature, side, reparent_to_root=True)

        self.assertIn("reparent_to_root=True is forbidden", str(ctx.exception))
        self.assertIsNone(ik_obj.parent, "Must not have reparented on illegal request")
        self.assertIsNone(pole_obj.parent, "Must not have reparented on illegal request")
        self.assertTrue(ik_obj.get("is_locked", False), "Lock state must remain True on illegal request")
        self.assertLess(_max_mat_diff(ik_obj.matrix_world, locked_ik_mat), 1e-6)
        self.assertLess(_max_mat_diff(pole_obj.matrix_world, locked_pole_mat), 1e-6)

    def test_09_failure_atomicity(self) -> None:
        """TEST-09: Phase A failure preserves FootIK, KneePole, and armature pose pristine across all 16 matrix elements."""
        side = "L"
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
        p_thigh = self.armature.pose.bones["thigh.L"]
        p_shin = self.armature.pose.bones["shin.L"]
        p_foot = self.armature.pose.bones["foot.L"]

        # Initial pristine state
        init_ik_mat = ik_obj.matrix_world.copy()
        init_pole_mat = pole_obj.matrix_world.copy()
        init_thigh_mat = p_thigh.matrix.copy()
        init_shin_mat = p_shin.matrix.copy()
        init_foot_mat = p_foot.matrix.copy()

        def _assert_state_pristine(case_label: str) -> None:
            self.assertLess(_max_mat_diff(ik_obj.matrix_world, init_ik_mat), 1e-6, f"{case_label}: FootIK matrix modified")
            self.assertLess(_max_mat_diff(pole_obj.matrix_world, init_pole_mat), 1e-6, f"{case_label}: KneePole matrix modified")
            self.assertLess(_max_mat_diff(p_thigh.matrix, init_thigh_mat), 1e-6, f"{case_label}: thigh.L matrix modified")
            self.assertLess(_max_mat_diff(p_shin.matrix, init_shin_mat), 1e-6, f"{case_label}: shin.L matrix modified")
            self.assertLess(_max_mat_diff(p_foot.matrix, init_foot_mat), 1e-6, f"{case_label}: foot.L matrix modified")

        # Failure Case 1: Non-finite rotation input
        with self.assertRaises(ValueError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, -8.0, 0.15),
                foot_rotation_deg=(float("nan"), 0.0, 0.0),
            )
        bpy.context.view_layer.update()
        _assert_state_pristine("Case 1 (NaN rotation)")

        # Failure Case 2: Invalid rotation type
        with self.assertRaises(TypeError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, -8.0, 0.15),
                foot_rotation_deg="invalid",
            )
        bpy.context.view_layer.update()
        _assert_state_pristine("Case 2 (Invalid type)")

        # Failure Case 3: Non-finite world_xyz
        with self.assertRaises(ValueError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, float("inf"), 0.15),
                foot_rotation_deg=(0.0, 0.0, 0.0),
            )
        bpy.context.view_layer.update()
        _assert_state_pristine("Case 3 (Inf position)")

    def test_10_bilateral_symmetry_and_independence(self) -> None:
        """TEST-10: Left and Right controllers operate independently without mutual cross-talk."""
        ik_l = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_r = bpy.data.objects[IK_TARGET_NAMES["R"]]
        pole_l = bpy.data.objects[POLE_TARGET_NAMES["L"]]
        pole_r = bpy.data.objects[POLE_TARGET_NAMES["R"]]

        # Set distinct world rotations and targets for L and R
        rot_l_deg = (12.0, -15.0, 20.0)
        rot_r_deg = (-10.0, 25.0, -35.0)

        set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.80, 0.20),
            foot_rotation_deg=rot_l_deg,
        )
        set_foot_ik_target(
            self.armature,
            "R",
            (HIP_X_OFFSET, -7.70, 0.25),
            foot_rotation_deg=rot_r_deg,
        )
        bpy.context.view_layer.update()

        q_l_expected = Euler((math.radians(v) for v in rot_l_deg), "XYZ").to_quaternion()
        q_r_expected = Euler((math.radians(v) for v in rot_r_deg), "XYZ").to_quaternion()

        self.assertLess(_quat_angle_diff(q_l_expected, ik_l.matrix_world.to_quaternion()), 1e-4)
        self.assertLess(_quat_angle_diff(q_r_expected, ik_r.matrix_world.to_quaternion()), 1e-4)

        # Lock Left, Right remains free and can still receive normal IK targets
        lock_foot_contact(self.armature, "L", contact_world_xyz=(-HIP_X_OFFSET, -7.80, 0.0))
        self.assertTrue(ik_l.get("is_locked", False))
        self.assertFalse(ik_r.get("is_locked", False))

        # Modifying Right does not disturb Left locked transform
        locked_l_mat = ik_l.matrix_world.copy()
        new_r_rot_deg = (0.0, 0.0, 45.0)
        set_foot_ik_target(
            self.armature,
            "R",
            (HIP_X_OFFSET, -7.60, 0.30),
            foot_rotation_deg=new_r_rot_deg,
        )
        bpy.context.view_layer.update()

        self.assertLess((ik_l.matrix_world.translation - locked_l_mat.translation).length, 1e-6)
        self.assertLess(_quat_angle_diff(ik_l.matrix_world.to_quaternion(), locked_l_mat.to_quaternion()), 1e-6)

        # Unlock Left
        unlock_foot_contact(self.armature, "L")
        bpy.context.view_layer.update()

        self.assertFalse(ik_l.get("is_locked", False))
        self.assertFalse(ik_r.get("is_locked", False))
        self.assertIsNone(ik_l.parent)
        self.assertIsNone(ik_r.parent)
        self.assertIsNone(pole_l.parent)
        self.assertIsNone(pole_r.parent)

    def test_11_nonzero_parent_inverse_combination(self) -> None:
        """TEST-11: Combination of non-zero parent rotation and non-identity matrix_parent_inverse."""
        parent_empty = bpy.data.objects.new("TestParentCombo", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.2, -7.8, 0.1))
        parent_empty.rotation_euler = Euler((0.0, 0.0, math.radians(45.0)), "XYZ")
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        # Non-identity matrix_parent_inverse (e.g. -10 deg Z rotation)
        ik_obj.matrix_parent_inverse = Euler((0.0, 0.0, math.radians(-10.0)), "XYZ").to_matrix().to_4x4()
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        eff_angle = _quat_angle_diff(eff_parent.to_quaternion(), Quaternion((1.0, 0.0, 0.0, 0.0)))
        parent_angle = _quat_angle_diff(parent_empty.matrix_world.to_quaternion(), Quaternion((1.0, 0.0, 0.0, 0.0)))
        self.assertGreater(eff_angle, 0.1, "Effective parent rotation must be non-zero")
        self.assertGreater(abs(eff_angle - parent_angle), 0.05, "Effective parent must differ from parent alone")

        req_rot_deg = (15.0, -20.0, 30.0)
        set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.85, 0.18),
            foot_rotation_deg=req_rot_deg,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        expected_world_rot = Euler((math.radians(v) for v in req_rot_deg), "XYZ").to_quaternion()
        actual_world_rot = ik_obj.matrix_world.to_quaternion()
        diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
        self.assertLess(diff_rad, 1e-4, f"Combo world rotation error {math.degrees(diff_rad):.4f} deg exceeds tolerance")

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_12_parent_scale_and_shear_boundary(self) -> None:
        """TEST-12: Parent uniform scale achieves requested rotation, and non-uniform scale shear boundary is detected."""
        parent_empty = bpy.data.objects.new("TestParentScale", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        # Part A: Uniform scale (e.g. 1.8) with non-zero rotation
        parent_empty.rotation_euler = Euler((math.radians(20.0), math.radians(-15.0), math.radians(35.0)), "XYZ")
        parent_empty.scale = Vector((1.8, 1.8, 1.8))
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        req_rot_deg = (10.0, 20.0, -15.0)
        set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.85, 0.18),
            foot_rotation_deg=req_rot_deg,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        expected_world_rot = Euler((math.radians(v) for v in req_rot_deg), "XYZ").to_quaternion()
        actual_world_rot = ik_obj.matrix_world.to_quaternion()
        diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
        self.assertLess(diff_rad, 1e-4, f"Uniform parent scale world rotation error {math.degrees(diff_rad):.4f} deg exceeds tolerance")

        # Part B: Non-uniform scale produces non-conformal transform:
        # set_foot_ik_target must reject in Phase A and preserve pristine state atomically.
        parent_empty.scale = Vector((1.5, 2.0, 0.8))
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        g_mat = a_mat.transposed() @ a_mat
        s_sq = (g_mat[0][0] + g_mat[1][1] + g_mat[2][2]) / 3.0
        max_rel_dev = max(abs(g_mat[r][c] - (s_sq if r == c else 0.0)) / s_sq for r in range(3) for c in range(3))
        self.assertGreater(max_rel_dev, 1e-4, "Effective parent matrix must violate conformal condition")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(10.0, 20.0, -15.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        self.assertIn("FootIK.L", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_13_legacy_parented_controller_unlock_preservation(self) -> None:
        """TEST-13: Unlock handles legacy parented controllers with non-unit scale and non-zero rotation faithfully."""
        parent_empty = bpy.data.objects.new("LegacyParent", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((1.0, -8.0, 0.5))
        parent_empty.rotation_euler = Euler((math.radians(15.0), math.radians(20.0), math.radians(-30.0)), "XYZ")
        bpy.context.view_layer.update()

        for side in ("L", "R"):
            ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
            pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

            # Manually simulate legacy parented state with non-unit scale and local rotation
            ik_obj.parent = parent_empty
            ik_obj.matrix_parent_inverse = Matrix.Identity(4)
            ik_obj.location = Vector((-HIP_X_OFFSET if side == "L" else HIP_X_OFFSET, 0.1, 0.07))
            ik_obj.rotation_euler = Euler((math.radians(5.0), math.radians(-10.0), math.radians(15.0)), "XYZ")
            ik_obj.scale = Vector((1.2, 1.2, 1.2))
            ik_obj["is_locked"] = True

            pole_obj.parent = parent_empty
            pole_obj.matrix_parent_inverse = Matrix.Identity(4)
            pole_obj.location = Vector((-HIP_X_OFFSET if side == "L" else HIP_X_OFFSET, 0.3, 0.5))
            pole_obj.rotation_euler = Euler((math.radians(-8.0), math.radians(12.0), math.radians(0.0)), "XYZ")
            pole_obj.scale = Vector((0.9, 0.9, 0.9))
            bpy.context.view_layer.update()

            # Confirm parent transformation was actively contributing
            self.assertGreater((ik_obj.matrix_world.translation - ik_obj.location).length, 0.1)

            # Record pre-unlock world matrices
            pre_ik_mat = ik_obj.matrix_world.copy()
            pre_pole_mat = pole_obj.matrix_world.copy()

            # Unlock
            res = unlock_foot_contact(self.armature, side)
            bpy.context.view_layer.update()

            # Assertions specified in Section 3.4
            self.assertIsNone(ik_obj.parent, f"{ik_obj.name} must be parentless after unlock")
            self.assertIsNone(pole_obj.parent, f"{pole_obj.name} must be parentless after unlock")
            self.assertEqual(ik_obj.matrix_parent_inverse, Matrix.Identity(4))
            self.assertEqual(pole_obj.matrix_parent_inverse, Matrix.Identity(4))

            # Full 4x4 matrix max element diff < 1e-5
            self.assertLess(_max_mat_diff(pre_ik_mat, ik_obj.matrix_world), 1e-5)
            self.assertLess(_max_mat_diff(pre_pole_mat, pole_obj.matrix_world), 1e-5)

            # Position diff < 1e-5 m
            self.assertLess((pre_ik_mat.translation - ik_obj.matrix_world.translation).length, 1e-5)
            self.assertLess((pre_pole_mat.translation - pole_obj.matrix_world.translation).length, 1e-5)

            # Rotation diff < 1e-4 rad
            self.assertLess(_quat_angle_diff(pre_ik_mat.to_quaternion(), ik_obj.matrix_world.to_quaternion()), 1e-4)
            self.assertLess(_quat_angle_diff(pre_pole_mat.to_quaternion(), pole_obj.matrix_world.to_quaternion()), 1e-4)

            # Scale diff < 1e-5
            self.assertLess((pre_ik_mat.to_scale() - ik_obj.matrix_world.to_scale()).length, 1e-5)
            self.assertLess((pre_pole_mat.to_scale() - pole_obj.matrix_world.to_scale()).length, 1e-5)

            # Lock status False
            self.assertFalse(ik_obj.get("is_locked", False))
            self.assertFalse(res["is_locked"])

        bpy.data.objects.remove(parent_empty)

    def test_14_shear_parent_transform_rejection(self) -> None:
        """TEST-14: Effective parent transform with shear is rejected in Phase A with failure atomicity."""
        parent_empty = bpy.data.objects.new("TestParentShear", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.rotation_euler = Euler((0.0, 0.0, math.radians(30.0)), "XYZ")
        parent_empty.scale = Vector((1.0, 1.0, 1.0))
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        # Introduce shear via matrix_parent_inverse
        shear_mat = Matrix((
            (1.0, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        ik_obj.matrix_parent_inverse = shear_mat
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        g_mat = a_mat.transposed() @ a_mat
        s_sq = (g_mat[0][0] + g_mat[1][1] + g_mat[2][2]) / 3.0
        max_rel_dev = max(abs(g_mat[r][c] - (s_sq if r == c else 0.0)) / s_sq for r in range(3) for c in range(3))
        self.assertGreater(max_rel_dev, 1e-4, "Effective parent matrix must have shear violating conformal condition")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(10.0, 20.0, -15.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_15_singular_parent_transform_rejection(self) -> None:
        """TEST-15: Singular effective parent transform (det == 0) is rejected in Phase A with failure atomicity."""
        parent_empty = bpy.data.objects.new("TestParentSingular", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.scale = Vector((1.0, 0.0, 1.0))  # Singular (zero Y scale)
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        self.assertEqual(a_mat.determinant(), 0.0, "Determinant must be zero (singular)")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(0.0, 0.0, 0.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        self.assertIn("singular", str(ctx.exception).lower())
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_16_reflection_parent_transform_rejection(self) -> None:
        """TEST-16: Reflection effective parent transform (det < 0) is rejected in Phase A with failure atomicity."""
        parent_empty = bpy.data.objects.new("TestParentReflection", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.scale = Vector((-1.0, 1.0, 1.0))  # Reflection (det = -1)
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        self.assertLess(a_mat.determinant(), 0.0, "Determinant must be negative (reflection)")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(0.0, 0.0, 0.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    @patch("src.rig.ik.get_leg_ik_state", side_effect=RuntimeError("INJECTED_PHASE_B_FAILURE"))
    def test_17_phase_b_transaction_rollback_fault_injection(self, mock_state) -> None:
        """TEST-17: Phase B transaction rollback catches fault, restores controllers & bones atomically, and re-raises."""
        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(RuntimeError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, self.root.location.y + 0.15, 0.20),
                foot_rotation_deg=(15.0, -20.0, 35.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("INJECTED_PHASE_B_FAILURE", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

    def test_18_small_scale_positive_uniform_scale(self) -> None:
        """TEST-18: Small-scale positive uniform scale (A = 0.001*R, det=1e-9) is accepted and achieves world rotation."""
        parent_empty = bpy.data.objects.new("TestParentSmallScale", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        # Composite 3D rotation R
        parent_empty.rotation_euler = Euler((math.radians(20.0), math.radians(-15.0), math.radians(35.0)), "XYZ")
        parent_empty.scale = Vector((0.001, 0.001, 0.001))
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        det_a = a_mat.determinant()
        self.assertAlmostEqual(det_a, 1e-9, delta=1e-12, msg="det(A) must be 1e-9 for scale=0.001")
        self.assertGreater(det_a, 0.0, "det(A) must be strictly positive")

        req_rot_deg = (15.0, -25.0, 30.0)
        res = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.85, 0.18),
            foot_rotation_deg=req_rot_deg,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        self.assertIsInstance(res, dict, "set_foot_ik_target must return a valid state dict")
        expected_world_rot = Euler((math.radians(v) for v in req_rot_deg), "XYZ").to_quaternion()
        actual_world_rot = ik_obj.matrix_world.to_quaternion()
        diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
        self.assertLess(diff_rad, 1e-4, f"Small scale world rotation error {math.degrees(diff_rad):.4f} deg exceeds tolerance")

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_19_near_threshold_non_conformal_rejection(self) -> None:
        """TEST-19: Effective parent matrix with 1e-6 < epsilon < 1e-4 is rejected by new tolerance (proved vs old 1e-4)."""
        parent_empty = bpy.data.objects.new("TestParentConformalThreshold", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.rotation_euler = Euler((math.radians(10.0), math.radians(20.0), math.radians(-15.0)), "XYZ")
        parent_empty.scale = Vector((1.0, 1.0, 1.0))
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        # Introduce non-conformal deviation: scale_z = 1.000015 yields epsilon ~= 2.0e-5
        ik_obj.matrix_parent_inverse = Matrix.Diagonal(Vector((1.0, 1.0, 1.000015, 1.0)))
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        g_mat = a_mat.transposed() @ a_mat
        s_sq = (g_mat[0][0] + g_mat[1][1] + g_mat[2][2]) / 3.0
        max_rel_dev = max(abs(g_mat[r][c] - (s_sq if r == c else 0.0)) / s_sq for r in range(3) for c in range(3))

        # Explicitly prove condition: 1e-6 < epsilon < 1e-4
        self.assertGreater(max_rel_dev, 1e-6, "Relative deviation must exceed new threshold 1e-6")
        self.assertLess(max_rel_dev, 1e-4, "Relative deviation must be below old threshold 1e-4 (proving old allowed it)")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(10.0, 20.0, -15.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        self.assertIn("non-conformal transform with relative deviation", str(ctx.exception))
        self.assertIn("FootIK.L", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_20_conformal_boundary_tolerance_acceptance(self) -> None:
        """TEST-20: Effective parent matrix within legal numerical boundary (epsilon <= 1e-6) is accepted."""
        parent_empty = bpy.data.objects.new("TestParentConformalLegal", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((0.0, -8.0, 0.0))
        parent_empty.rotation_euler = Euler((math.radians(12.0), math.radians(-18.0), math.radians(24.0)), "XYZ")
        parent_empty.scale = Vector((1.2, 1.2, 1.2))
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = parent_empty
        # Small perturbation right within tolerance: epsilon ~= 5.2e-7 <= 1e-6
        ik_obj.matrix_parent_inverse = Matrix.Diagonal(Vector((1.0, 1.0, 1.0000003, 1.0)))
        bpy.context.view_layer.update()

        eff_parent = parent_empty.matrix_world @ ik_obj.matrix_parent_inverse
        a_mat = Matrix((
            (eff_parent[0][0], eff_parent[0][1], eff_parent[0][2]),
            (eff_parent[1][0], eff_parent[1][1], eff_parent[1][2]),
            (eff_parent[2][0], eff_parent[2][1], eff_parent[2][2]),
        ))
        g_mat = a_mat.transposed() @ a_mat
        s_sq = (g_mat[0][0] + g_mat[1][1] + g_mat[2][2]) / 3.0
        max_rel_dev = max(abs(g_mat[r][c] - (s_sq if r == c else 0.0)) / s_sq for r in range(3) for c in range(3))

        # Explicitly prove condition: epsilon <= 1e-6 and > 0
        self.assertLessEqual(max_rel_dev, 1e-6, "Relative deviation must be within legal tolerance 1e-6")
        self.assertGreater(max_rel_dev, 0.0, "Relative deviation should test non-trivial boundary")

        req_rot_deg = (15.0, -20.0, 30.0)
        res = set_foot_ik_target(
            self.armature,
            "L",
            (-HIP_X_OFFSET, -7.85, 0.18),
            foot_rotation_deg=req_rot_deg,
            clamp_ground=False,
            clamp_reach=False,
        )
        bpy.context.view_layer.update()

        self.assertIsInstance(res, dict, "set_foot_ik_target must return a valid state dict")
        expected_world_rot = Euler((math.radians(v) for v in req_rot_deg), "XYZ").to_quaternion()
        actual_world_rot = ik_obj.matrix_world.to_quaternion()
        diff_rad = _quat_angle_diff(expected_world_rot, actual_world_rot)
        self.assertLess(diff_rad, 1e-4, f"Boundary conformal world rotation error {math.degrees(diff_rad):.4f} deg exceeds tolerance")

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(parent_empty)

    def test_21_kneepole_independent_shear_rejection(self) -> None:
        """TEST-21: KneePole independent shear rejection while FootIK remains pristine and valid."""
        # 1. Setup FootIK in valid parentless state
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)

        # 2. Setup KneePole with parent having non-conformal shear
        pole_parent = bpy.data.objects.new("TestPoleParentShear", None)
        bpy.context.scene.collection.objects.link(pole_parent)
        pole_parent.location = Vector((0.0, -8.0, 0.0))
        pole_parent.rotation_euler = Euler((0.0, 0.0, math.radians(20.0)), "XYZ")
        pole_parent.scale = Vector((1.0, 1.0, 1.0))
        bpy.context.view_layer.update()

        pole_obj = bpy.data.objects[POLE_TARGET_NAMES["L"]]
        pole_obj.parent = pole_parent
        shear_mat = Matrix((
            (1.0, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        pole_obj.matrix_parent_inverse = shear_mat
        bpy.context.view_layer.update()

        # 3. Explicitly prove A_pole^T @ A_pole != s^2 * I before calling production
        eff_pole = pole_parent.matrix_world @ pole_obj.matrix_parent_inverse
        a_pole = Matrix((
            (eff_pole[0][0], eff_pole[0][1], eff_pole[0][2]),
            (eff_pole[1][0], eff_pole[1][1], eff_pole[1][2]),
            (eff_pole[2][0], eff_pole[2][1], eff_pole[2][2]),
        ))
        g_pole = a_pole.transposed() @ a_pole
        s_sq_pole = (g_pole[0][0] + g_pole[1][1] + g_pole[2][2]) / 3.0
        max_rel_dev_pole = max(
            abs(g_pole[r][c] - (s_sq_pole if r == c else 0.0)) / s_sq_pole
            for r in range(3) for c in range(3)
        )
        is_isotropic = all(
            math.isclose(g_pole[r][c], s_sq_pole if r == c else 0.0, abs_tol=1e-5)
            for r in range(3) for c in range(3)
        )
        self.assertFalse(is_isotropic, "A_pole^T @ A_pole must strictly not equal s^2 * I")
        self.assertGreater(max_rel_dev_pole, 1e-4, "KneePole matrix must have non-conformal shear")

        saved_state = _capture_rig_state(self.armature)

        # 4. Invoke real set_foot_ik_target
        with self.assertRaises(ValueError) as ctx:
            set_foot_ik_target(
                self.armature,
                "L",
                (-HIP_X_OFFSET, -7.85, 0.18),
                foot_rotation_deg=(10.0, 20.0, -15.0),
                clamp_ground=False,
                clamp_reach=False,
            )

        # 5. Assertions on the rejection path
        self.assertIn("Phase A effective parent transform validation failed", str(ctx.exception))
        self.assertIn("KneePole.L", str(ctx.exception), "Exception must explicitly identify KneePole.L")
        self.assertNotIn("FootIK.L", str(ctx.exception), "FootIK validation must not trigger before KneePole")

        # 6. Verify atomicity across both controllers and all 6 leg bones
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)

        # Cleanup
        pole_obj.parent = None
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(pole_parent)

    def test_22_unlock_foot_contact_ik_shear_rejection(self) -> None:
        """TEST-22: unlock_foot_contact rejects FootIK non-TRS shear and preserves pristine locked state."""
        lock_foot_contact(self.armature, "L")
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        self.assertTrue(ik_obj.get("is_locked"), "FootIK.L must be locked initially")

        ik_parent = bpy.data.objects.new("TestIKParentShear", None)
        bpy.context.scene.collection.objects.link(ik_parent)
        ik_parent.location = Vector((0.0, -8.0, 0.0))
        ik_obj.parent = ik_parent
        shear_mat = Matrix((
            (1.0, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        ik_obj.matrix_parent_inverse = shear_mat
        bpy.context.view_layer.update()

        # Compute and assert shear deviation before calling unlock
        current_ik_world = ik_obj.matrix_world.copy()
        ik_loc, ik_rot_quat, ik_scale = current_ik_world.decompose()
        ik_reconstructed = Matrix.LocRotScale(ik_loc, ik_rot_quat, ik_scale)
        max_ik_shear = max(abs(current_ik_world[r][c] - ik_reconstructed[r][c]) for r in range(4) for c in range(4))
        self.assertGreater(max_ik_shear, 1e-4, "FootIK matrix must have non-orthogonal shear > 1e-4")

        a_ik = Matrix((
            (current_ik_world[0][0], current_ik_world[0][1], current_ik_world[0][2]),
            (current_ik_world[1][0], current_ik_world[1][1], current_ik_world[1][2]),
            (current_ik_world[2][0], current_ik_world[2][1], current_ik_world[2][2]),
        ))
        g_ik = a_ik.transposed() @ a_ik
        s_sq_ik = (g_ik[0][0] + g_ik[1][1] + g_ik[2][2]) / 3.0
        is_isotropic = all(
            math.isclose(g_ik[r][c], s_sq_ik if r == c else 0.0, abs_tol=1e-4)
            for r in range(3) for c in range(3)
        )
        self.assertFalse(is_isotropic, "A_ik^T @ A_ik must strictly not equal s^2 * I")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(RuntimeError) as ctx:
            unlock_foot_contact(self.armature, "L")

        self.assertIn("ik_obj world matrix contains non-TRS shear", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)
        self.assertTrue(ik_obj.get("is_locked"), "is_locked must remain True after rejection")

        # Cleanup
        ik_obj.parent = None
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(ik_parent)

    def test_23_unlock_foot_contact_pole_shear_rejection(self) -> None:
        """TEST-23: unlock_foot_contact rejects KneePole non-TRS shear independently while FootIK is valid."""
        lock_foot_contact(self.armature, "L")
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES["L"]]
        self.assertTrue(ik_obj.get("is_locked"), "FootIK.L must be locked initially")

        # FootIK has pure TRS (no shear)
        ik_loc, ik_rot_quat, ik_scale = ik_obj.matrix_world.decompose()
        ik_reconstructed = Matrix.LocRotScale(ik_loc, ik_rot_quat, ik_scale)
        max_ik_shear = max(abs(ik_obj.matrix_world[r][c] - ik_reconstructed[r][c]) for r in range(4) for c in range(4))
        self.assertLessEqual(max_ik_shear, 1e-5, "FootIK matrix must have zero or negligible shear")

        # Introduce shear on KneePole
        pole_parent = bpy.data.objects.new("TestPoleParentShearUnlock", None)
        bpy.context.scene.collection.objects.link(pole_parent)
        pole_parent.location = Vector((0.0, -8.0, 0.0))
        pole_obj.parent = pole_parent
        shear_mat = Matrix((
            (1.0, 0.5, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        pole_obj.matrix_parent_inverse = shear_mat
        bpy.context.view_layer.update()

        pole_loc, pole_rot_quat, pole_scale = pole_obj.matrix_world.decompose()
        pole_reconstructed = Matrix.LocRotScale(pole_loc, pole_rot_quat, pole_scale)
        max_pole_shear = max(abs(pole_obj.matrix_world[r][c] - pole_reconstructed[r][c]) for r in range(4) for c in range(4))
        self.assertGreater(max_pole_shear, 1e-4, "KneePole matrix must have non-orthogonal shear > 1e-4")

        saved_state = _capture_rig_state(self.armature)

        with self.assertRaises(RuntimeError) as ctx:
            unlock_foot_contact(self.armature, "L")

        self.assertIn("pole_obj world matrix contains non-TRS shear", str(ctx.exception))
        self.assertNotIn("ik_obj world matrix contains non-TRS shear", str(ctx.exception))
        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)
        self.assertTrue(ik_obj.get("is_locked"), "is_locked must remain True after rejection")

        # Cleanup
        pole_obj.parent = None
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.data.objects.remove(pole_parent)

    def test_24_unlock_foot_contact_post_commit_fault_injection(self) -> None:
        """TEST-24: unlock_foot_contact rolls back all state atomically upon post-commit fault injection."""
        lock_foot_contact(self.armature, "L", target_rotation_deg=(12.0, -15.0, 25.0))
        ik_obj = bpy.data.objects[IK_TARGET_NAMES["L"]]
        self.assertTrue(ik_obj.get("is_locked"), "FootIK.L must be locked initially")
        self.assertIn("locked_ankle_world_xyz", ik_obj, "Lock metadata must be present")
        self.assertIn("contact_world_xyz", ik_obj, "Lock metadata must be present")

        saved_state = _capture_rig_state(self.armature)

        with patch("src.rig.foot_contact.get_foot_support_state", side_effect=RuntimeError("INJECTED_UNLOCK_POST_COMMIT_FAILURE")):
            with self.assertRaises(RuntimeError) as ctx:
                unlock_foot_contact(self.armature, "L")
            self.assertIn("INJECTED_UNLOCK_POST_COMMIT_FAILURE", str(ctx.exception))

        bpy.context.view_layer.update()
        _assert_rig_state_identical(self, saved_state, tol=1e-6)
        self.assertTrue(ik_obj.get("is_locked"), "is_locked must be restored to True")
        self.assertIn("locked_ankle_world_xyz", ik_obj, "Lock metadata must be preserved after rollback")

    def test_25_effective_parent_non_finite_rejection(self) -> None:
        """TEST-25: _validate_effective_parent_transform rejects non-finite elements (NaN and Inf)."""
        nan_mat = Matrix.Identity(4)
        nan_mat[0][1] = float("nan")
        with self.assertRaises(ValueError) as ctx_nan:
            _validate_effective_parent_transform(nan_mat, "TestTargetNaN")
        self.assertIn("non-finite matrix element", str(ctx_nan.exception))

        inf_mat = Matrix.Identity(4)
        inf_mat[2][3] = float("inf")
        with self.assertRaises(ValueError) as ctx_inf:
            _validate_effective_parent_transform(inf_mat, "TestTargetInf")
        self.assertIn("non-finite matrix element", str(ctx_inf.exception))

    def test_26_effective_parent_non_affine_rejection(self) -> None:
        """TEST-26: _validate_effective_parent_transform rejects non-affine last row."""
        non_affine_mat = Matrix.Identity(4)
        non_affine_mat[3][0] = 2e-6
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(non_affine_mat, "TestTargetNonAffine")
        self.assertIn("non-affine matrix", str(ctx.exception))

        non_affine_mat2 = Matrix.Identity(4)
        non_affine_mat2[3][3] = 1.0 + 1e-5
        with self.assertRaises(ValueError) as ctx2:
            _validate_effective_parent_transform(non_affine_mat2, "TestTargetNonAffine2")
        self.assertIn("non-affine matrix", str(ctx2.exception))

    def test_27_effective_parent_degenerate_scale_rejection(self) -> None:
        """TEST-27: _validate_effective_parent_transform rejects degenerate scale s^2 <= 1e-12 with det > 0."""
        s = 5e-7
        small_mat = Matrix((
            (s, 0.0, 0.0, 0.0),
            (0.0, s, 0.0, 0.0),
            (0.0, 0.0, s, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))
        a_3x3 = Matrix((
            (small_mat[0][0], small_mat[0][1], small_mat[0][2]),
            (small_mat[1][0], small_mat[1][1], small_mat[1][2]),
            (small_mat[2][0], small_mat[2][1], small_mat[2][2]),
        ))
        det_a = a_3x3.determinant()
        self.assertGreater(det_a, 0.0, "Determinant is strictly positive")
        g = a_3x3.transposed() @ a_3x3
        s_sq = (g[0][0] + g[1][1] + g[2][2]) / 3.0
        self.assertLessEqual(s_sq, 1e-12, "s^2 must be <= 1e-12 (degenerate scale)")

        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(small_mat, "TestTargetDegenerateScale")
        self.assertIn("degenerate scale", str(ctx.exception))
        self.assertNotIn("singular", str(ctx.exception).lower())
        self.assertNotIn("reflection", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
