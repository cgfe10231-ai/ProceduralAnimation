"""Contract verification suite for Arm IK Initialization Idempotency and Effective Parent Transform (Task 10-A / 10-a-1, 10-a-2 & 10-a-3).

Tests:
- TEST-01: First-time initialization creates all 4 Empty controls and 4 constraints with correct initial influence.
- TEST-02: Re-initialization preserves existing controller objects, parents, matrices, locations, and rotations.
- TEST-03: Re-initialization preserves existing constraint instances, influences, and configurations without recreation.
- TEST-04: WholeBodyController repeated instantiation does not overwrite active arm targets or influences.
- TEST-05: Explicit reset_arm_ik restores neutral rest pose and 0.0 influence, and subsequent setup does not corrupt it.
- TEST-06: Parentless world space control preserves target translation, pole placement, and world rotation.
- TEST-07: Non-identity matrix_parent_inverse with rotation and uniform scale inverts correctly without cross-arm interference.
- TEST-08: HandIK and ElbowPole controllers with distinct effective parent transforms resolve independently.
- TEST-09: Supported effective parent domain accepts pure rotation, positive uniform scale, and arbitrary finite translation.
- TEST-10: Unsupported effective parent domain rejects NaN, Inf, non-affine, reflection, singular, degenerate scale, and shear.
- TEST-11: Phase A validation rejection leaves all controllers, pose bones, and constraint influences completely unpolluted.
- TEST-12: Zero regression against existing 09-B Leg IK world rotation contract (all 27 tests pass).
- TEST-13: Parent transform mutations without manual view_layer.update() are refreshed internally before validation.
- TEST-14: HandIK target preserves XYZ rotation mode with world transform contract.
- TEST-15: HandIK target preserves XZY rotation mode with world transform contract.
- TEST-16: HandIK target preserves YXZ rotation mode with world transform contract.
- TEST-17: HandIK target preserves YZX rotation mode with world transform contract.
- TEST-18: HandIK target preserves ZXY rotation mode with world transform contract.
- TEST-19: HandIK target preserves ZYX rotation mode with world transform contract.
- TEST-20: HandIK target preserves QUATERNION rotation mode with world transform contract.
- TEST-21: HandIK target preserves AXIS_ANGLE rotation mode with world transform contract.
- TEST-22: reset_arm_ik under distinct non-identity parents and inverses restores neutral world transforms.
- TEST-23: reset_arm_ik preserves XYZ rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-24: reset_arm_ik preserves XZY rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-25: reset_arm_ik preserves YXZ rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-26: reset_arm_ik preserves YZX rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-27: reset_arm_ik preserves ZXY rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-28: reset_arm_ik preserves ZYX rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-29: reset_arm_ik preserves QUATERNION rotation mode on HandIK and ElbowPole with neutral transforms.
- TEST-30: reset_arm_ik preserves AXIS_ANGLE rotation mode on HandIK and ElbowPole with neutral transforms.
"""

import io
import math
import os
import sys
import unittest
from typing import Dict

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.character.builder import build_character
from src.config import PipelineConfig
from src.motion.whole_body_controller import WholeBodyController
from src.rig.arm_ik import (
    ARM_IK_CONSTRAINT_NAMES,
    ARM_IK_TARGET_NAMES,
    ARM_POLE_TARGET_NAMES,
    DEFAULT_POLE_BACKWARD_OFFSET,
    DEFAULT_POLE_OUTWARD_OFFSET,
    ELBOW_REST_Z,
    HAND_ROT_CONSTRAINT_NAMES,
    MAX_ARM_REACH,
    MIN_ARM_REACH,
    SHOULDER_REST_Z,
    SHOULDER_X_OFFSET,
    WRIST_REST_Z,
    get_arm_ik_state,
    reset_arm_ik,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


class TestArmIKLifecycleWorldTransformContract(unittest.TestCase):
    """Test suite verifying Arm IK initialization idempotency, lifecycle, and effective parent transform contracts."""

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

    def test_01_first_time_initialization(self) -> None:
        """TEST-01: First-time initialization creates 4 controllers and 4 constraints with specified initial influence."""
        init_influence = 0.35
        controls = setup_arm_ik(self.armature, initial_influence=init_influence)

        # 4 controllers must exist as valid empties
        for name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(name, controls)
            obj = bpy.data.objects.get(name)
            self.assertIsNotNone(obj, f"Controller '{name}' must exist in bpy.data.objects")
            self.assertEqual(obj.type, "EMPTY")

        # Check constraint types, configurations, and initial influence
        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]

            ik_con = p_fore.constraints.get(ARM_IK_CONSTRAINT_NAMES[side])
            self.assertIsNotNone(ik_con)
            self.assertEqual(ik_con.type, "IK")
            self.assertEqual(ik_con.target, controls[ARM_IK_TARGET_NAMES[side]])
            self.assertEqual(ik_con.pole_target, controls[ARM_POLE_TARGET_NAMES[side]])
            self.assertEqual(ik_con.chain_count, 2)
            self.assertFalse(ik_con.use_stretch)
            self.assertAlmostEqual(ik_con.influence, init_influence, places=5)

            rot_con = p_hand.constraints.get(HAND_ROT_CONSTRAINT_NAMES[side])
            self.assertIsNotNone(rot_con)
            self.assertEqual(rot_con.type, "COPY_ROTATION")
            self.assertEqual(rot_con.target, controls[ARM_IK_TARGET_NAMES[side]])
            self.assertEqual(rot_con.target_space, "WORLD")
            self.assertEqual(rot_con.owner_space, "WORLD")
            self.assertAlmostEqual(rot_con.influence, init_influence, places=5)

            # Ensure exactly 1 IK constraint on forearm and 1 COPY_ROTATION on hand
            ik_count = sum(1 for c in p_fore.constraints if c.name == ARM_IK_CONSTRAINT_NAMES[side])
            rot_count = sum(1 for c in p_hand.constraints if c.name == HAND_ROT_CONSTRAINT_NAMES[side])
            self.assertEqual(ik_count, 1)
            self.assertEqual(rot_count, 1)

    def test_02_reinitialization_preserves_controllers(self) -> None:
        """TEST-02: Calling setup_arm_ik again must not overwrite existing controller transforms, parents, or targets."""
        setup_arm_ik(self.armature, initial_influence=0.0)

        # Set active positions and rotations on left and right arms
        pos_l = (-0.35, self.root.location.y + 0.20, 1.30)
        rot_l = (15.0, 30.0, -10.0)
        pole_l = (-0.50, self.root.location.y - 0.30, 1.20)
        set_hand_ik_target(self.armature, "L", pos_l, hand_rotation_deg=rot_l, pole_world_xyz=pole_l, influence=1.0)

        pos_r = (0.28, self.root.location.y - 0.15, 1.10)
        rot_r = (-20.0, 10.0, 45.0)
        pole_r = (0.45, self.root.location.y - 0.40, 1.15)
        set_hand_ik_target(self.armature, "R", pos_r, hand_rotation_deg=rot_r, pole_world_xyz=pole_r, influence=1.0)
        bpy.context.view_layer.update()

        # Capture snapshot of all 4 controllers
        ctrl_snap: Dict[str, dict] = {}
        ctrl_names = ["HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"]
        for cname in ctrl_names:
            obj = bpy.data.objects[cname]
            ctrl_snap[cname] = {
                "parent": obj.parent,
                "matrix_parent_inverse": obj.matrix_parent_inverse.copy(),
                "matrix_world": obj.matrix_world.copy(),
                "location": obj.location.copy(),
                "rotation_euler": obj.rotation_euler.copy(),
                "scale": obj.scale.copy(),
            }

        # Re-run setup_arm_ik with initial_influence=0.0
        setup_arm_ik(self.armature, initial_influence=0.0)
        bpy.context.view_layer.update()

        # Verify all controllers retained their exact transform state
        for cname in ctrl_names:
            obj = bpy.data.objects[cname]
            snap = ctrl_snap[cname]
            self.assertEqual(obj.parent, snap["parent"], f"{cname} parent must not be modified on re-init")
            for r in range(4):
                for c in range(4):
                    self.assertAlmostEqual(
                        obj.matrix_parent_inverse[r][c], snap["matrix_parent_inverse"][r][c], places=6
                    )
                    self.assertAlmostEqual(obj.matrix_world[r][c], snap["matrix_world"][r][c], places=5)
            self.assertAlmostEqual((obj.location - snap["location"]).length, 0.0, places=6)
            self.assertAlmostEqual((Vector(obj.rotation_euler) - Vector(snap["rotation_euler"])).length, 0.0, places=6)
            self.assertAlmostEqual((obj.scale - snap["scale"]).length, 0.0, places=6)

    def test_03_reinitialization_preserves_constraint_instances(self) -> None:
        """TEST-03: Re-initialization preserves constraint object instances, influences, and does not duplicate constraints."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        set_arm_ik_influence(self.armature, "L", influence=0.85)
        set_arm_ik_influence(self.armature, "R", influence=0.45)

        # Capture constraint identities and configurations
        snap_con = {}
        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]
            ik_c = p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[side]]
            rot_c = p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[side]]
            snap_con[f"IK_{side}"] = (ik_c.as_pointer(), ik_c.influence, ik_c.target, ik_c.pole_target)
            snap_con[f"ROT_{side}"] = (rot_c.as_pointer(), rot_c.influence, rot_c.target)

        # Re-initialize multiple times
        setup_arm_ik(self.armature, initial_influence=0.0)
        setup_arm_ik(self.armature, initial_influence=0.0)

        # Verify identical constraint instances and preserved influence
        for side in ("L", "R"):
            p_fore = self.armature.pose.bones[f"forearm.{side}"]
            p_hand = self.armature.pose.bones[f"hand.{side}"]
            ik_c = p_fore.constraints[ARM_IK_CONSTRAINT_NAMES[side]]
            rot_c = p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES[side]]

            ik_ptr, ik_inf, ik_tgt, ik_pole = snap_con[f"IK_{side}"]
            rot_ptr, rot_inf, rot_tgt = snap_con[f"ROT_{side}"]

            self.assertEqual(ik_c.as_pointer(), ik_ptr, f"ArmIK.{side} instance must not be recreated")
            self.assertAlmostEqual(ik_c.influence, ik_inf, places=5, msg=f"ArmIK.{side} influence must not be overwritten")
            self.assertEqual(ik_c.target, ik_tgt)
            self.assertEqual(ik_c.pole_target, ik_pole)

            self.assertEqual(rot_c.as_pointer(), rot_ptr, f"HandRotation.{side} instance must not be recreated")
            self.assertAlmostEqual(rot_c.influence, rot_inf, places=5, msg=f"HandRotation.{side} influence must not be overwritten")
            self.assertEqual(rot_c.target, rot_tgt)

            # Constraint counts must remain 1
            self.assertEqual(sum(1 for c in p_fore.constraints if c.name == ARM_IK_CONSTRAINT_NAMES[side]), 1)
            self.assertEqual(sum(1 for c in p_hand.constraints if c.name == HAND_ROT_CONSTRAINT_NAMES[side]), 1)

    def test_04_wbc_reconstruction_does_not_reset_arm_ik(self) -> None:
        """TEST-04: Constructing a new WholeBodyController instance must not reset active arm IK targets or influence."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        set_hand_ik_target(self.armature, "L", (-0.30, self.root.location.y + 0.15, 1.25), hand_rotation_deg=(10.0, 0.0, 0.0), influence=0.9)
        set_hand_ik_target(self.armature, "R", (0.30, self.root.location.y - 0.10, 1.15), hand_rotation_deg=(-15.0, 0.0, 0.0), influence=0.7)
        bpy.context.view_layer.update()

        st_l_before = get_arm_ik_state(self.armature, "L")
        st_r_before = get_arm_ik_state(self.armature, "R")

        # Construct new WBC (which calls setup_arm_ik internally)
        _wbc = WholeBodyController(self.armature)
        bpy.context.view_layer.update()

        st_l_after = get_arm_ik_state(self.armature, "L")
        st_r_after = get_arm_ik_state(self.armature, "R")

        self.assertAlmostEqual(st_l_after["ik_influence"], 0.9, places=5)
        self.assertAlmostEqual(st_r_after["ik_influence"], 0.7, places=5)
        self.assertAlmostEqual((st_l_after["wrist_world"] - st_l_before["wrist_world"]).length, 0.0, places=5)
        self.assertAlmostEqual((st_r_after["wrist_world"] - st_r_before["wrist_world"]).length, 0.0, places=5)
        self.assertAlmostEqual((st_l_after["target_world"] - st_l_before["target_world"]).length, 0.0, places=6)
        self.assertAlmostEqual((st_r_after["target_world"] - st_r_before["target_world"]).length, 0.0, places=6)

    def test_05_explicit_reset_contract(self) -> None:
        """TEST-05: reset_arm_ik explicitly restores neutral targets, bone rest pose, and influence=0.0."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        set_hand_ik_target(self.armature, "L", (-0.32, self.root.location.y + 0.20, 1.20), influence=1.0)
        set_hand_ik_target(self.armature, "R", (0.32, self.root.location.y + 0.20, 1.20), influence=1.0)
        bpy.context.view_layer.update()

        # Explicit reset
        reset_arm_ik(self.armature)
        bpy.context.view_layer.update()

        st_l = get_arm_ik_state(self.armature, "L")
        st_r = get_arm_ik_state(self.armature, "R")

        self.assertAlmostEqual(st_l["ik_influence"], 0.0, places=6)
        self.assertAlmostEqual(st_r["ik_influence"], 0.0, places=6)
        self.assertAlmostEqual(st_l["rot_influence"], 0.0, places=6)
        self.assertAlmostEqual(st_r["rot_influence"], 0.0, places=6)

        # Check controllers returned to neutral
        ik_l = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        self.assertAlmostEqual(ik_l.location.x, -SHOULDER_X_OFFSET, places=5)
        self.assertAlmostEqual(ik_l.location.y, 0.0, places=5)
        self.assertAlmostEqual(ik_l.location.z, WRIST_REST_Z, places=5)

        # Re-running setup_arm_ik after reset must keep it in the neutral reset state
        setup_arm_ik(self.armature, initial_influence=0.0)
        bpy.context.view_layer.update()
        st_l2 = get_arm_ik_state(self.armature, "L")
        self.assertAlmostEqual(st_l2["ik_influence"], 0.0, places=6)

    def test_06_parentless_worldspace_path(self) -> None:
        """TEST-06: HandIK and ElbowPole with parent=None set absolute world coordinates without parent dependence."""
        setup_arm_ik(self.armature, initial_influence=0.0)

        # Unparent all arm controllers
        for name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            obj = bpy.data.objects[name]
            obj.parent = None
            obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        target_l = (-0.28, self.root.location.y + 0.18, 1.25)
        pole_l = (-0.48, self.root.location.y - 0.35, 1.20)
        rot_deg = (15.0, -20.0, 35.0)

        res = set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_l,
            hand_rotation_deg=rot_deg,
            pole_world_xyz=pole_l,
            influence=1.0,
        )

        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]

        # Controller world position match within 1e-6
        self.assertAlmostEqual((ik_obj.matrix_world.translation - Vector(target_l)).length, 0.0, places=6)
        self.assertAlmostEqual((pole_obj.matrix_world.translation - Vector(pole_l)).length, 0.0, places=6)

        # Hand orientation error <= 1e-4 rad
        req_rot_mat = Euler((math.radians(v) for v in rot_deg), "XYZ").to_matrix()
        actual_rot_mat = ik_obj.matrix_world.to_3x3()
        rad_diff = req_rot_mat.to_quaternion().rotation_difference(actual_rot_mat.to_quaternion()).angle
        self.assertLessEqual(rad_diff, 1e-4)
        self.assertLessEqual(res["target_error"], 1e-3)

    def test_07_non_identity_matrix_parent_inverse(self) -> None:
        """TEST-07: Effective parent with rotation, positive uniform scale, and non-identity matrix_parent_inverse."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]

        # Create custom parent object with rotation and scale = 1.5
        parent_empty = bpy.data.objects.new("CustomArmParent", None)
        bpy.context.scene.collection.objects.link(parent_empty)
        parent_empty.location = Vector((1.0, self.root.location.y + 2.0, 0.5))
        parent_empty.rotation_euler = Euler((math.radians(30.0), math.radians(-15.0), math.radians(45.0)), "XYZ")
        parent_empty.scale = Vector((1.5, 1.5, 1.5))

        ik_obj.parent = parent_empty
        # Set non-identity matrix_parent_inverse (rotated and translated)
        inv_euler = Euler((math.radians(-10.0), math.radians(20.0), math.radians(5.0)), "XYZ")
        ik_obj.matrix_parent_inverse = Matrix.LocRotScale(Vector((0.2, -0.3, 0.1)), inv_euler, Vector((1.0, 1.0, 1.0)))
        bpy.context.view_layer.update()

        target_l = (-0.30, self.root.location.y + 0.20, 1.28)
        rot_deg = (-25.0, 15.0, 10.0)
        res = set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_l,
            hand_rotation_deg=rot_deg,
            influence=1.0,
        )

        # Verification of world position and orientation
        self.assertAlmostEqual((ik_obj.matrix_world.translation - Vector(target_l)).length, 0.0, places=5)
        actual_rot = ik_obj.matrix_world.to_quaternion()
        req_rot = Euler((math.radians(v) for v in rot_deg), "XYZ").to_matrix().to_quaternion()
        self.assertLessEqual(req_rot.rotation_difference(actual_rot).angle, 1e-4)

        # Right arm must be completely unaffected
        ik_r = bpy.data.objects[ARM_IK_TARGET_NAMES["R"]]
        self.assertNotEqual(ik_r.parent, parent_empty)

    def test_08_independent_parent_matrices_for_hand_and_pole(self) -> None:
        """TEST-08: HandIK and ElbowPole with distinct parents and transforms resolve independently without crosstalk."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]

        p_hand_custom = bpy.data.objects.new("ParentHand", None)
        p_pole_custom = bpy.data.objects.new("ParentPole", None)
        bpy.context.scene.collection.objects.link(p_hand_custom)
        bpy.context.scene.collection.objects.link(p_pole_custom)

        p_hand_custom.location = Vector((0.5, self.root.location.y + 0.2, 1.0))
        p_hand_custom.rotation_euler = Euler((math.radians(15.0), 0.0, 0.0), "XYZ")
        p_hand_custom.scale = Vector((1.2, 1.2, 1.2))

        p_pole_custom.location = Vector((-0.4, self.root.location.y - 0.6, 0.8))
        p_pole_custom.rotation_euler = Euler((0.0, math.radians(-30.0), math.radians(20.0)), "XYZ")
        p_pole_custom.scale = Vector((0.8, 0.8, 0.8))

        ik_obj.parent = p_hand_custom
        ik_obj.matrix_parent_inverse = Matrix.Identity(4)
        pole_obj.parent = p_pole_custom
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)
        bpy.context.view_layer.update()

        target_l = (-0.32, self.root.location.y + 0.15, 1.20)
        pole_l = (-0.50, self.root.location.y - 0.40, 1.15)
        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_l,
            pole_world_xyz=pole_l,
            influence=1.0,
        )

        self.assertAlmostEqual((ik_obj.matrix_world.translation - Vector(target_l)).length, 0.0, places=5)
        self.assertAlmostEqual((pole_obj.matrix_world.translation - Vector(pole_l)).length, 0.0, places=5)

    def test_09_supported_effective_parent_domain(self) -> None:
        """TEST-09: Validates acceptance of pure rotation, uniform scaling, and arbitrary translation."""
        from src.rig.ik import _validate_effective_parent_transform

        # Pure rotation
        rot_mat = Matrix.Rotation(math.radians(45.0), 4, "Z")
        _validate_effective_parent_transform(rot_mat, "PureRot")

        # Positive uniform scale with rotation and translation
        scale_mat = Matrix.Diagonal((2.5, 2.5, 2.5, 1.0))
        combo = rot_mat @ scale_mat
        combo[0][3] = 12.34
        combo[1][3] = -56.78
        combo[2][3] = 90.12
        _validate_effective_parent_transform(combo, "UniformScaleRotTrans")

        # Boundary small scale s^2 > 1e-12 (e.g. s = 2e-6, s^2 = 4e-12)
        s_small = 2e-6
        small_mat = Matrix.Diagonal((s_small, s_small, s_small, 1.0))
        _validate_effective_parent_transform(small_mat, "SmallScaleBoundary")

    def test_10_rejected_effective_parent_domain(self) -> None:
        """TEST-10: Validates rejection of NaN, Inf, non-affine, reflection, singular, degenerate scale, and shear."""
        from src.rig.ik import _validate_effective_parent_transform

        # NaN
        nan_m = Matrix.Identity(4)
        nan_m[1][2] = float("nan")
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(nan_m, "NaN")
        self.assertIn("non-finite matrix element", str(ctx.exception))

        # Inf
        inf_m = Matrix.Identity(4)
        inf_m[0][0] = float("inf")
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(inf_m, "Inf")
        self.assertIn("non-finite matrix element", str(ctx.exception))

        # Non-affine bottom row
        na_m = Matrix.Identity(4)
        na_m[3][1] = 2e-5
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(na_m, "NonAffine")
        self.assertIn("non-affine matrix", str(ctx.exception))

        # Reflection (det < 0)
        ref_m = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(ref_m, "Reflection")
        self.assertIn("reflection", str(ctx.exception).lower())

        # Singular (det == 0)
        sing_m = Matrix.Diagonal((1.0, 0.0, 1.0, 1.0))
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(sing_m, "Singular")
        self.assertIn("singular", str(ctx.exception).lower())

        # Degenerate scale s^2 <= 1e-12 with det > 0
        s_deg = 5e-7
        deg_m = Matrix.Diagonal((s_deg, s_deg, s_deg, 1.0))
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(deg_m, "DegenerateScale")
        self.assertIn("degenerate scale", str(ctx.exception))

        # Non-uniform scale (1.0, 2.0, 1.0)
        nus_m = Matrix.Diagonal((1.0, 2.0, 1.0, 1.0))
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(nus_m, "NonUniformScale")
        self.assertIn("non-conformal transform", str(ctx.exception))

        # Shear
        shear_m = Matrix.Identity(4)
        shear_m[0][1] = 0.5
        with self.assertRaises(ValueError) as ctx:
            _validate_effective_parent_transform(shear_m, "Shear")
        self.assertIn("non-conformal transform", str(ctx.exception))

    def test_11_rejection_leaves_state_unpolluted(self) -> None:
        """TEST-11: Phase A validation rejection raises exception before mutating controllers, bones, or constraints."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]

        # Set up an initial active pose and target so state is non-neutral
        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=(-0.30, self.root.location.y + 0.15, 1.25),
            hand_rotation_deg=(10.0, -15.0, 20.0),
            influence=0.8,
        )
        bpy.context.view_layer.update()

        # Create illegal shear parent
        shear_parent = bpy.data.objects.new("ShearParent", None)
        bpy.context.scene.collection.objects.link(shear_parent)
        shear_parent.location = Vector((1.0, self.root.location.y + 2.0, 3.0))
        ik_obj.parent = shear_parent

        # Set non-identity matrix_parent_inverse with shear
        shear_mat = Matrix.Identity(4)
        shear_mat[0][1] = 0.8
        shear_mat[0][3] = 0.5
        ik_obj.matrix_parent_inverse = shear_mat

        # Also give ElbowPole a valid parent with non-identity transform
        valid_pole_parent = bpy.data.objects.new("PoleParent", None)
        bpy.context.scene.collection.objects.link(valid_pole_parent)
        valid_pole_parent.location = Vector((-0.5, self.root.location.y - 0.5, 1.0))
        pole_obj.parent = valid_pole_parent
        pole_obj.matrix_parent_inverse = Matrix.Identity(4)

        # Synchronize dependency graph so illegal parent is established in Blender
        bpy.context.view_layer.update()

        # FULL SNAPSHOT OF STATE AFTER SETUP, BEFORE CALLING set_hand_ik_target
        ik_snap = {
            "parent": ik_obj.parent,
            "matrix_parent_inverse": ik_obj.matrix_parent_inverse.copy(),
            "matrix_world": ik_obj.matrix_world.copy(),
            "location": ik_obj.location.copy(),
            "rotation_mode": ik_obj.rotation_mode,
            "rotation_euler": ik_obj.rotation_euler.copy(),
            "rotation_quaternion": ik_obj.rotation_quaternion.copy(),
            "rotation_axis_angle": tuple(ik_obj.rotation_axis_angle),
            "scale": ik_obj.scale.copy(),
        }
        pole_snap = {
            "parent": pole_obj.parent,
            "matrix_parent_inverse": pole_obj.matrix_parent_inverse.copy(),
            "matrix_world": pole_obj.matrix_world.copy(),
            "location": pole_obj.location.copy(),
            "rotation_mode": pole_obj.rotation_mode,
            "rotation_euler": pole_obj.rotation_euler.copy(),
            "rotation_quaternion": pole_obj.rotation_quaternion.copy(),
            "rotation_axis_angle": tuple(pole_obj.rotation_axis_angle),
            "scale": pole_obj.scale.copy(),
        }

        bone_snap = {}
        for bname in ("upper_arm.L", "forearm.L", "hand.L"):
            pb = self.armature.pose.bones[bname]
            bone_snap[bname] = {
                "rotation_mode": pb.rotation_mode,
                "location": pb.location.copy(),
                "rotation_euler": pb.rotation_euler.copy(),
                "rotation_quaternion": pb.rotation_quaternion.copy(),
                "rotation_axis_angle": tuple(pb.rotation_axis_angle),
                "scale": pb.scale.copy(),
                "matrix_basis": pb.matrix_basis.copy(),
                "matrix": pb.matrix.copy(),
            }

        p_fore = self.armature.pose.bones["forearm.L"]
        p_hand = self.armature.pose.bones["hand.L"]
        ik_con = p_fore.constraints[ARM_IK_CONSTRAINT_NAMES["L"]]
        rot_con = p_hand.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]]

        con_snap = {
            "ik_ptr": ik_con.as_pointer(),
            "ik_target": ik_con.target,
            "ik_pole_target": ik_con.pole_target,
            "ik_influence": ik_con.influence,
            "rot_ptr": rot_con.as_pointer(),
            "rot_target": rot_con.target,
            "rot_influence": rot_con.influence,
        }

        # Target call MUST raise ValueError during Phase A validation
        with self.assertRaises(ValueError) as ctx:
            set_hand_ik_target(
                self.armature,
                "L",
                world_xyz=(-0.25, self.root.location.y + 0.20, 1.30),
                hand_rotation_deg=(20.0, 0.0, -10.0),
                influence=1.0,
            )
        self.assertIn("non-conformal transform", str(ctx.exception))

        # Check HandIK state completely unpolluted
        self.assertEqual(ik_obj.parent, ik_snap["parent"])
        for r in range(4):
            for c in range(4):
                self.assertEqual(ik_obj.matrix_parent_inverse[r][c], ik_snap["matrix_parent_inverse"][r][c])
                self.assertEqual(ik_obj.matrix_world[r][c], ik_snap["matrix_world"][r][c])
        self.assertEqual(ik_obj.location, ik_snap["location"])
        self.assertEqual(ik_obj.rotation_mode, ik_snap["rotation_mode"])
        self.assertEqual(ik_obj.rotation_euler, ik_snap["rotation_euler"])
        self.assertEqual(ik_obj.rotation_quaternion, ik_snap["rotation_quaternion"])
        self.assertEqual(tuple(ik_obj.rotation_axis_angle), ik_snap["rotation_axis_angle"])
        self.assertEqual(ik_obj.scale, ik_snap["scale"])

        # Check ElbowPole state completely unpolluted
        self.assertEqual(pole_obj.parent, pole_snap["parent"])
        for r in range(4):
            for c in range(4):
                self.assertEqual(pole_obj.matrix_parent_inverse[r][c], pole_snap["matrix_parent_inverse"][r][c])
                self.assertEqual(pole_obj.matrix_world[r][c], pole_snap["matrix_world"][r][c])
        self.assertEqual(pole_obj.location, pole_snap["location"])
        self.assertEqual(pole_obj.rotation_mode, pole_snap["rotation_mode"])
        self.assertEqual(pole_obj.rotation_euler, pole_snap["rotation_euler"])
        self.assertEqual(pole_obj.rotation_quaternion, pole_snap["rotation_quaternion"])
        self.assertEqual(tuple(pole_obj.rotation_axis_angle), pole_snap["rotation_axis_angle"])
        self.assertEqual(pole_obj.scale, pole_snap["scale"])

        # Check PoseBones
        for bname in ("upper_arm.L", "forearm.L", "hand.L"):
            pb = self.armature.pose.bones[bname]
            snap_b = bone_snap[bname]
            self.assertEqual(pb.rotation_mode, snap_b["rotation_mode"])
            self.assertEqual(pb.location, snap_b["location"])
            self.assertEqual(pb.rotation_euler, snap_b["rotation_euler"])
            self.assertEqual(pb.rotation_quaternion, snap_b["rotation_quaternion"])
            self.assertEqual(tuple(pb.rotation_axis_angle), snap_b["rotation_axis_angle"])
            self.assertEqual(pb.scale, snap_b["scale"])
            for r in range(4):
                for c in range(4):
                    self.assertEqual(pb.matrix_basis[r][c], snap_b["matrix_basis"][r][c])
                    self.assertEqual(pb.matrix[r][c], snap_b["matrix"][r][c])

        # Check Constraints
        self.assertEqual(ik_con.as_pointer(), con_snap["ik_ptr"])
        self.assertEqual(ik_con.target, con_snap["ik_target"])
        self.assertEqual(ik_con.pole_target, con_snap["ik_pole_target"])
        self.assertEqual(ik_con.influence, con_snap["ik_influence"])

        self.assertEqual(rot_con.as_pointer(), con_snap["rot_ptr"])
        self.assertEqual(rot_con.target, con_snap["rot_target"])
        self.assertEqual(rot_con.influence, con_snap["rot_influence"])

    def test_12_regression_compatibility_leg_ik(self) -> None:
        """TEST-12: Zero regression against existing 09-B Leg IK contract (all 27 tests pass)."""
        from tests.test_leg_ik_world_rotation_contract import TestLegIKWorldRotationContract

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestLegIKWorldRotationContract)
        stream = io.StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=1)
        result = runner.run(suite)

        self.assertEqual(result.testsRun, 27, "All 27 leg IK world rotation tests must run")
        self.assertEqual(len(result.failures), 0, f"Leg IK failures: {result.failures}")
        self.assertEqual(len(result.errors), 0, f"Leg IK errors: {result.errors}")

    def test_13_effective_parent_stale_depgraph_update(self) -> None:
        """TEST-13: Parent transform mutations without manual view_layer.update() are refreshed internally before validation."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]

        parent = bpy.data.objects.new("StaleDepgraphParent", None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = Vector((1.0, self.root.location.y - 1.0, 2.0))
        parent.rotation_euler = Euler((math.radians(10.0), 0.0, 0.0), "XYZ")
        parent.scale = Vector((1.2, 1.2, 1.2))
        ik_obj.parent = parent
        pole_obj.parent = parent
        bpy.context.view_layer.update()

        # Mutate parent object transforms WITHOUT calling view_layer.update()
        parent.location = Vector((3.5, self.root.location.y + 2.0, -1.0))
        parent.rotation_euler = Euler((math.radians(25.0), math.radians(-35.0), math.radians(50.0)), "XYZ")
        parent.scale = Vector((1.5, 1.5, 1.5))
        # Note: view_layer.update() is intentionally NOT called here!

        target_l = (-0.30, self.root.location.y + 0.18, 1.25)
        pole_l = (-0.48, self.root.location.y - 0.35, 1.20)
        rot_deg = (15.0, -20.0, 35.0)

        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_l,
            hand_rotation_deg=rot_deg,
            pole_world_xyz=pole_l,
            influence=1.0,
        )

        # Final world positions must match requested targets
        self.assertAlmostEqual((ik_obj.matrix_world.translation - Vector(target_l)).length, 0.0, places=5)
        self.assertAlmostEqual((pole_obj.matrix_world.translation - Vector(pole_l)).length, 0.0, places=5)

        # Hand world orientation error <= 1e-4 rad
        req_rot = Euler((math.radians(v) for v in rot_deg), "XYZ").to_matrix().to_quaternion()
        actual_rot = ik_obj.matrix_world.to_quaternion()
        self.assertLessEqual(req_rot.rotation_difference(actual_rot).angle, 1e-4)

    def _verify_rotation_mode_set_target(self, mode: str) -> None:
        """Helper to verify that set_hand_ik_target preserves the specified rotation_mode."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]

        # Custom parent with non-zero translation, non-zero rotation, and positive uniform scale
        parent = bpy.data.objects.new(f"RotModeParent_{mode}", None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = Vector((0.8, self.root.location.y + 0.5, 1.2))
        parent.rotation_euler = Euler((math.radians(20.0), math.radians(-30.0), math.radians(45.0)), "XYZ")
        parent.scale = Vector((1.4, 1.4, 1.4))

        # Set non-identity matrix_parent_inverse containing rotation and translation
        ik_obj.parent = parent
        inv_euler = Euler((math.radians(10.0), math.radians(-15.0), math.radians(25.0)), "XYZ")
        expected_inv = Matrix.LocRotScale(Vector((0.1, -0.2, 0.15)), inv_euler, Vector((1.0, 1.0, 1.0)))
        ik_obj.matrix_parent_inverse = expected_inv.copy()

        # Set rotation_mode to the specified mode under test
        ik_obj.rotation_mode = mode
        bpy.context.view_layer.update()

        target_l = (-0.28, self.root.location.y + 0.20, 1.26)
        rot_deg = (30.0, -40.0, 20.0)
        expected_rot_quat = Euler((math.radians(v) for v in rot_deg), "XYZ").to_matrix().to_quaternion()

        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=target_l,
            hand_rotation_deg=rot_deg,
            influence=1.0,
        )

        # 1. Assert rotation_mode is completely preserved
        self.assertEqual(ik_obj.rotation_mode, mode, f"rotation_mode must remain {mode}")

        # 2. Assert parent reference and matrix_parent_inverse are not mutated by interface
        self.assertEqual(ik_obj.parent, parent, "Parent reference must not be changed")
        for r in range(4):
            for c in range(4):
                self.assertAlmostEqual(
                    ik_obj.matrix_parent_inverse[r][c],
                    expected_inv[r][c],
                    places=6,
                    msg=f"matrix_parent_inverse element ({r}, {c}) mutated",
                )

        # 3. Assert final world position matches requested target <= 1e-5 m
        pos_err = (ik_obj.matrix_world.translation - Vector(target_l)).length
        self.assertAlmostEqual(pos_err, 0.0, places=5, msg=f"World position error {pos_err:.6e} > 1e-5 m")

        # 4. Assert final world rotation matches requested rotation <= 1e-4 rad
        actual_rot_quat = ik_obj.matrix_world.to_quaternion()
        ang_err = expected_rot_quat.rotation_difference(actual_rot_quat).angle
        self.assertLessEqual(ang_err, 1e-4, f"Mode {mode} world rotation error {ang_err:.6e} > 1e-4 rad")

    def test_14_rotation_mode_xyz(self) -> None:
        """TEST-14: HandIK target preserves XYZ rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("XYZ")

    def test_15_rotation_mode_xzy(self) -> None:
        """TEST-15: HandIK target preserves XZY rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("XZY")

    def test_16_rotation_mode_yxz(self) -> None:
        """TEST-16: HandIK target preserves YXZ rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("YXZ")

    def test_17_rotation_mode_yzx(self) -> None:
        """TEST-17: HandIK target preserves YZX rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("YZX")

    def test_18_rotation_mode_zxy(self) -> None:
        """TEST-18: HandIK target preserves ZXY rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("ZXY")

    def test_19_rotation_mode_zyx(self) -> None:
        """TEST-19: HandIK target preserves ZYX rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("ZYX")

    def test_20_rotation_mode_quaternion(self) -> None:
        """TEST-20: HandIK target preserves QUATERNION rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("QUATERNION")

    def test_21_rotation_mode_axis_angle(self) -> None:
        """TEST-21: HandIK target preserves AXIS_ANGLE rotation mode with world transform contract."""
        self._verify_rotation_mode_set_target("AXIS_ANGLE")

    def test_22_reset_distinct_non_identity_parent_inverses(self) -> None:
        """TEST-22: reset_arm_ik under distinct non-identity parents and inverses restores neutral world transforms."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]

        p_fore = self.armature.pose.bones["forearm.L"]
        p_hand_bone = self.armature.pose.bones["hand.L"]
        ik_con = p_fore.constraints[ARM_IK_CONSTRAINT_NAMES["L"]]
        rot_con = p_hand_bone.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]]

        ik_obj_ptr = ik_obj.as_pointer()
        pole_obj_ptr = pole_obj.as_pointer()
        ik_con_ptr = ik_con.as_pointer()
        rot_con_ptr = rot_con.as_pointer()

        # Two distinct parent objects with non-zero translation, rotation, and positive uniform scale
        p_hand = bpy.data.objects.new("ResetParentHand_A", None)
        p_pole = bpy.data.objects.new("ResetParentPole_B", None)
        bpy.context.scene.collection.objects.link(p_hand)
        bpy.context.scene.collection.objects.link(p_pole)

        p_hand.location = Vector((0.6, self.root.location.y + 0.3, 1.1))
        p_hand.rotation_euler = Euler((math.radians(15.0), math.radians(-25.0), math.radians(35.0)), "XYZ")
        p_hand.scale = Vector((1.3, 1.3, 1.3))

        p_pole.location = Vector((-0.5, self.root.location.y - 0.7, 0.9))
        p_pole.rotation_euler = Euler((math.radians(-20.0), math.radians(15.0), math.radians(-10.0)), "XYZ")
        p_pole.scale = Vector((0.7, 0.7, 0.7))

        # Independent non-identity matrix_parent_inverse matrices with non-zero translation, rotation, and uniform scale
        ik_obj.parent = p_hand
        inv_euler_hand = Euler((math.radians(-12.0), math.radians(18.0), math.radians(5.0)), "XYZ")
        hand_inv_mat = Matrix.LocRotScale(Vector((0.15, -0.25, 0.1)), inv_euler_hand, Vector((1.1, 1.1, 1.1)))
        ik_obj.matrix_parent_inverse = hand_inv_mat.copy()

        pole_obj.parent = p_pole
        inv_euler_pole = Euler((math.radians(14.0), math.radians(-10.0), math.radians(22.0)), "XYZ")
        pole_inv_mat = Matrix.LocRotScale(Vector((-0.2, 0.18, -0.12)), inv_euler_pole, Vector((0.9, 0.9, 0.9)))
        pole_obj.matrix_parent_inverse = pole_inv_mat.copy()

        bpy.context.view_layer.update()

        # Set active non-neutral targets
        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=(-0.35, self.root.location.y + 0.25, 1.35),
            hand_rotation_deg=(25.0, 10.0, -15.0),
            pole_world_xyz=(-0.55, self.root.location.y - 0.40, 1.15),
            influence=1.0,
        )
        bpy.context.view_layer.update()

        # Save controllers' parent, matrix_parent_inverse, and rotation_mode
        saved_ik_parent = ik_obj.parent
        saved_ik_inv = ik_obj.matrix_parent_inverse.copy()
        saved_ik_rot_mode = ik_obj.rotation_mode

        saved_pole_parent = pole_obj.parent
        saved_pole_inv = pole_obj.matrix_parent_inverse.copy()
        saved_pole_rot_mode = pole_obj.rotation_mode

        # Execute reset_arm_ik and synchronize dependency graph
        reset_arm_ik(self.armature)
        bpy.context.view_layer.update()

        # HandIK assertions:
        self.assertEqual(ik_obj.parent, saved_ik_parent)
        for r in range(4):
            for c in range(4):
                self.assertEqual(ik_obj.matrix_parent_inverse[r][c], saved_ik_inv[r][c])
        self.assertEqual(ik_obj.rotation_mode, saved_ik_rot_mode)

        root_mat = self.root.matrix_world
        expected_hand_world = root_mat @ Vector((-SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
        self.assertAlmostEqual((ik_obj.matrix_world.translation - expected_hand_world).length, 0.0, places=5)

        expected_hand_rot_quat = root_mat.to_quaternion()
        hand_rot_err = ik_obj.matrix_world.to_quaternion().rotation_difference(expected_hand_rot_quat).angle
        self.assertLessEqual(hand_rot_err, 1e-4)

        # ElbowPole assertions:
        self.assertEqual(pole_obj.parent, saved_pole_parent)
        for r in range(4):
            for c in range(4):
                self.assertEqual(pole_obj.matrix_parent_inverse[r][c], saved_pole_inv[r][c])
        self.assertEqual(pole_obj.rotation_mode, saved_pole_rot_mode)

        expected_pole_world = root_mat @ Vector((
            -(SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
            -DEFAULT_POLE_BACKWARD_OFFSET,
            ELBOW_REST_Z,
        ))
        self.assertAlmostEqual((pole_obj.matrix_world.translation - expected_pole_world).length, 0.0, places=5)

        expected_pole_rot_quat = Quaternion()
        pole_rot_err = pole_obj.matrix_world.to_quaternion().rotation_difference(expected_pole_rot_quat).angle
        self.assertLessEqual(pole_rot_err, 1e-4)

        # Constraints and object pointers assertions:
        self.assertAlmostEqual(ik_con.influence, 0.0, places=6)
        self.assertAlmostEqual(rot_con.influence, 0.0, places=6)
        self.assertEqual(ik_obj.as_pointer(), ik_obj_ptr, "HandIK Empty must not be recreated")
        self.assertEqual(pole_obj.as_pointer(), pole_obj_ptr, "ElbowPole Empty must not be recreated")
        self.assertEqual(ik_con.as_pointer(), ik_con_ptr, "ArmIK constraint must not be recreated")
        self.assertEqual(rot_con.as_pointer(), rot_con_ptr, "HandRotation constraint must not be recreated")

    def _verify_reset_rotation_mode(self, mode: str) -> None:
        """Helper to verify that reset_arm_ik preserves the specified rotation_mode on HandIK and ElbowPole."""
        setup_arm_ik(self.armature, initial_influence=0.0)

        # Rotate CharacterRoot so neutral world orientation is non-identity
        self.root.rotation_euler = Euler((math.radians(18.0), math.radians(-12.0), math.radians(25.0)), "XYZ")
        bpy.context.view_layer.update()

        ik_obj = bpy.data.objects[ARM_IK_TARGET_NAMES["L"]]
        pole_obj = bpy.data.objects[ARM_POLE_TARGET_NAMES["L"]]
        ik_obj.rotation_mode = mode
        pole_obj.rotation_mode = mode
        bpy.context.view_layer.update()

        # Set active non-neutral targets
        p_up = self.armature.pose.bones["upper_arm.L"]
        shoulder_world = self.armature.matrix_world @ p_up.head
        target_world = shoulder_world + self.root.matrix_world.to_3x3() @ Vector((0.0, 0.25, -0.20))
        pole_target_world = shoulder_world + self.root.matrix_world.to_3x3() @ Vector((-0.20, -0.30, -0.15))

        set_hand_ik_target(
            self.armature,
            "L",
            world_xyz=tuple(target_world),
            hand_rotation_deg=(35.0, -15.0, 45.0),
            pole_world_xyz=tuple(pole_target_world),
            influence=1.0,
        )
        bpy.context.view_layer.update()

        # Reset arm IK
        reset_arm_ik(self.armature)
        bpy.context.view_layer.update()

        # 1. Assert rotation_mode is preserved on both controllers
        self.assertEqual(ik_obj.rotation_mode, mode, f"HandIK rotation_mode must remain {mode}")
        self.assertEqual(pole_obj.rotation_mode, mode, f"ElbowPole rotation_mode must remain {mode}")

        # 2. Expected neutral targets
        root_mat = self.root.matrix_world
        expected_hand_world = root_mat @ Vector((-SHOULDER_X_OFFSET, 0.0, WRIST_REST_Z))
        expected_pole_world = root_mat @ Vector((
            -(SHOULDER_X_OFFSET + DEFAULT_POLE_OUTWARD_OFFSET),
            -DEFAULT_POLE_BACKWARD_OFFSET,
            ELBOW_REST_Z,
        ))
        expected_hand_rot_quat = root_mat.to_quaternion()
        expected_pole_rot_quat = Quaternion()

        # 3. Assert world translations recovered to neutral
        self.assertAlmostEqual((ik_obj.matrix_world.translation - expected_hand_world).length, 0.0, places=5)
        self.assertAlmostEqual((pole_obj.matrix_world.translation - expected_pole_world).length, 0.0, places=5)

        # 4. Assert world orientations
        hand_rot_err = ik_obj.matrix_world.to_quaternion().rotation_difference(expected_hand_rot_quat).angle
        self.assertLessEqual(hand_rot_err, 1e-4, f"HandIK mode {mode} reset rotation error {hand_rot_err:.6e} > 1e-4 rad")

        pole_rot_err = pole_obj.matrix_world.to_quaternion().rotation_difference(expected_pole_rot_quat).angle
        self.assertLessEqual(pole_rot_err, 1e-4, f"ElbowPole mode {mode} reset rotation error {pole_rot_err:.6e} > 1e-4 rad")

        # 5. Assert constraint influences returned to 0.0
        p_fore = self.armature.pose.bones["forearm.L"]
        p_hand_bone = self.armature.pose.bones["hand.L"]
        self.assertAlmostEqual(p_fore.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.0, places=6)
        self.assertAlmostEqual(p_hand_bone.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.0, places=6)

    def test_23_reset_rotation_mode_xyz(self) -> None:
        """TEST-23: reset_arm_ik preserves XYZ rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("XYZ")

    def test_24_reset_rotation_mode_xzy(self) -> None:
        """TEST-24: reset_arm_ik preserves XZY rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("XZY")

    def test_25_reset_rotation_mode_yxz(self) -> None:
        """TEST-25: reset_arm_ik preserves YXZ rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("YXZ")

    def test_26_reset_rotation_mode_yzx(self) -> None:
        """TEST-26: reset_arm_ik preserves YZX rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("YZX")

    def test_27_reset_rotation_mode_zxy(self) -> None:
        """TEST-27: reset_arm_ik preserves ZXY rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("ZXY")

    def test_28_reset_rotation_mode_zyx(self) -> None:
        """TEST-28: reset_arm_ik preserves ZYX rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("ZYX")

    def test_29_reset_rotation_mode_quaternion(self) -> None:
        """TEST-29: reset_arm_ik preserves QUATERNION rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("QUATERNION")

    def test_30_reset_rotation_mode_axis_angle(self) -> None:
        """TEST-30: reset_arm_ik preserves AXIS_ANGLE rotation mode on HandIK and ElbowPole with neutral transforms."""
        self._verify_reset_rotation_mode("AXIS_ANGLE")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
