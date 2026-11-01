"""ProceduralAnimation — PKG-5 / 09-B Unit Tests.

Validates Lower-Limb IK World Rotation Contract and Controller Lifecycle Closure:
- TEST-01: Parentless world rotation (parent=None, non-zero XYZ rotation matches world request).
- TEST-02: Non-zero parent Yaw (parent has yaw rotation, controller world orientation matches world request).
- TEST-03: Composite rotation (composite parent yaw/pitch/roll + composite target yaw/pitch/roll).
- TEST-04: World rotation composition order (proper 3D rotation math, no Euler subtraction, foot_rotation_deg=None level neutral).
- TEST-05: Unlock world matrix preservation (FootIK location/rotation and KneePole location preserved, parentless).
- TEST-06: Bilateral lifecycle (setup -> lock -> unlock -> normal IK target -> reset preserves parentless invariant).
- TEST-07: Legacy compatibility default call (unlock_foot_contact without reparent_to_root defaults to parentless).
- TEST-08: Explicit illegal request (reparent_to_root=True raises ValueError and prevents reparenting).
- TEST-09: Failure atomicity (Phase A failure leaves FootIK, KneePole, and armature pose pristine).
- TEST-10: Bilateral symmetry & independence (Left and Right controllers operate without mutual contamination).
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
            # Temporarily attach to test parent
            ik_obj.parent = parent_empty
            ik_obj.matrix_parent_inverse = parent_empty.matrix_world.inverted()
            bpy.context.view_layer.update()

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
            ik_obj.matrix_parent_inverse = parent_empty.matrix_world.inverted()
            bpy.context.view_layer.update()

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
        ik_obj.matrix_parent_inverse = parent_empty.matrix_world.inverted()
        bpy.context.view_layer.update()

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
        """TEST-05: Unlock preserves world position and orientation of FootIK and KneePole without jump."""
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

            # Check positions
            ik_loc_jump = (unlocked_ik_mat.translation - locked_ik_mat.translation).length
            pole_loc_jump = (unlocked_pole_mat.translation - locked_pole_mat.translation).length

            self.assertLess(
                ik_loc_jump,
                1e-5,
                f"Side {side}: FootIK world position jumped on unlock by {ik_loc_jump:.6f}m",
            )
            self.assertLess(
                pole_loc_jump,
                1e-5,
                f"Side {side}: KneePole world position jumped on unlock by {pole_loc_jump:.6f}m",
            )

            # Check rotations
            ik_rot_diff = _quat_angle_diff(
                locked_ik_mat.to_quaternion(), unlocked_ik_mat.to_quaternion()
            )
            self.assertLess(
                ik_rot_diff,
                1e-4,
                f"Side {side}: FootIK world orientation jumped on unlock by {math.degrees(ik_rot_diff):.4f} deg",
            )

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
        """TEST-08: Explicitly passing reparent_to_root=True must raise ValueError and not reparent."""
        side = "R"
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]

        lock_foot_contact(self.armature, side, contact_world_xyz=(HIP_X_OFFSET, -8.0, 0.0))

        with self.assertRaises(ValueError) as ctx:
            unlock_foot_contact(self.armature, side, reparent_to_root=True)

        self.assertIn("reparent_to_root=True is forbidden", str(ctx.exception))
        self.assertIsNone(ik_obj.parent, "Must not have reparented on illegal request")
        self.assertIsNone(pole_obj.parent, "Must not have reparented on illegal request")

    def test_09_failure_atomicity(self) -> None:
        """TEST-09: Phase A failure preserves FootIK, KneePole, and armature pose pristine."""
        side = "L"
        ik_obj = bpy.data.objects[IK_TARGET_NAMES[side]]
        pole_obj = bpy.data.objects[POLE_TARGET_NAMES[side]]
        p_thigh = self.armature.pose.bones["thigh.L"]

        # Initial pristine state
        init_ik_mat = ik_obj.matrix_world.copy()
        init_pole_mat = pole_obj.matrix_world.copy()
        init_thigh_mat = p_thigh.matrix.copy()

        # Failure Case 1: Non-finite rotation input
        with self.assertRaises(ValueError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, -8.0, 0.15),
                foot_rotation_deg=(float("nan"), 0.0, 0.0),
            )
        bpy.context.view_layer.update()

        self.assertLess((ik_obj.matrix_world.translation - init_ik_mat.translation).length, 1e-6)
        self.assertLess(_quat_angle_diff(ik_obj.matrix_world.to_quaternion(), init_ik_mat.to_quaternion()), 1e-6)
        self.assertLess((pole_obj.matrix_world.translation - init_pole_mat.translation).length, 1e-6)
        self.assertLess((p_thigh.matrix.translation - init_thigh_mat.translation).length, 1e-6)

        # Failure Case 2: Invalid rotation type
        with self.assertRaises(TypeError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, -8.0, 0.15),
                foot_rotation_deg="invalid",
            )
        bpy.context.view_layer.update()

        self.assertLess((ik_obj.matrix_world.translation - init_ik_mat.translation).length, 1e-6)
        self.assertLess(_quat_angle_diff(ik_obj.matrix_world.to_quaternion(), init_ik_mat.to_quaternion()), 1e-6)

        # Failure Case 3: Non-finite world_xyz
        with self.assertRaises(ValueError):
            set_foot_ik_target(
                self.armature,
                side,
                (-HIP_X_OFFSET, float("inf"), 0.15),
                foot_rotation_deg=(0.0, 0.0, 0.0),
            )
        bpy.context.view_layer.update()

        self.assertLess((ik_obj.matrix_world.translation - init_ik_mat.translation).length, 1e-6)
        self.assertLess(_quat_angle_diff(ik_obj.matrix_world.to_quaternion(), init_ik_mat.to_quaternion()), 1e-6)

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


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
