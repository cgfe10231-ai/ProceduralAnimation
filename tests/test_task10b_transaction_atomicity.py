"""Contract verification suite for Arm IK Production Transaction Snapshot & Atomicity (Task 10-B / Revision 4).

Tests:
- TEST-31: Snapshot fidelity: covers 4 controllers (existence, type, Data Block, Parent,
           matrix_parent_inverse, TRS, rotation_mode, collections) with zero scene mutation.
- TEST-32: Snapshot fidelity: covers 6 upper-limb pose bones (all transform properties,
           IK locks, and IK limits).
- TEST-33: Snapshot fidelity: covers constraint configuration, ordering, targets, and
           Character collection hierarchy.
- TEST-34: Direct rollback on uninitialized scene: removes 4 controllers, constraints,
           and created Character collection.
- TEST-35: Direct rollback with wrong-type controller: restores original object type,
           data block, name, parent, and collection memberships.
- TEST-36: Direct rollback on initialized scene: restores controller parent,
           matrix_parent_inverse, TRS, and rotation mode.
- TEST-37: Direct rollback on 6 pose bones: restores rotation mode, channels,
           location, scale, IK locks, and limits.
- TEST-38: Direct rollback on constraints: restores count, order, types, names,
           targets, pole targets, and influences.
- TEST-39: Fault injection in setup_arm_ik() after first controller created -> rolls back.
- TEST-40: Fault injection in setup_arm_ik() after wrong-type controller replaced -> restores original object.
- TEST-41: Fault injection in setup_arm_ik() after constraints/pre-bend modified -> restores clean state.
- TEST-42: Fault injection in set_hand_ik_target() during auto-init -> rolls back to uninitialized state.
- TEST-43: Fault injection in set_hand_ik_target() after HandIK location written -> restores location.
- TEST-44: Fault injection in set_hand_ik_target() after HandIK rotation written -> restores rotation.
- TEST-45: Fault injection in set_hand_ik_target() after ElbowPole location written -> restores pole location.
- TEST-46: Fault injection in set_hand_ik_target() between ArmIK and HandRotation influences -> influences restored in sync.
- TEST-47: Fault injection in set_hand_ik_target() after HandRotation influence modified -> rolls back all state.
- TEST-48: Fault injection in set_hand_ik_target() during view_layer.update / get_arm_ik_state() -> revokes all writes.
- TEST-49: Fault injection in set_arm_ik_influence(side="L") mid-write -> L influences restored, R unaffected.
- TEST-50: Fault injection in set_arm_ik_influence(side="BOTH") mid-write -> all 4 constraint influences restored.
- TEST-51: Success path fresh & re-entrant calls across all 8 rotation modes (6 Eulers, QUATERNION, AXIS_ANGLE).
- TEST-52: Success after failure recovery; explicit failure report if rollback verification fails.
- TEST-53: Comprehensive 4-controller transform fidelity test.
- TEST-54: Controller empty_display_type and empty_display_size fidelity test.
- TEST-55: 6 pose bones comprehensive transform & limits fidelity test.
- TEST-56: 4 constraints full properties fidelity test.
- TEST-57: Character collection hierarchy & parent-child linkages recovery.
- TEST-58: Fault injection during during_snapshot_controllers.
- TEST-59: Fault injection during during_snapshot_pose_bones.
- TEST-60: Fault injection during during_snapshot_constraints.
- TEST-61: Fault injection during set_hand_ik_target_during_depsgraph_update (pre-update hook).
- TEST-62: Direct set_hand_ik_target() on uninitialized scene succeeds; subsequent failure rolls back.
- TEST-63: Fault injection interface privacy & cleanliness test.
- TEST-64: Commit cleanup removes orphaned Data Blocks, preserves shared Data Blocks, reports errors.
- TEST-65: Phase 1 (Reversible Commit Preparation) failure triggers full atomic rollback.
- TEST-66: Phase 3 (Irreversible Resource Cleanup) failure leaves rig COMMITTED with retry capability.
- TEST-67: Partial cleanup failure prevents duplicate deletions, protects shared resources, and converges on retry.
- TEST-68: Exception at _DEPSGRAPH_UPDATER call boundary propagates and triggers complete atomic rollback.
- TEST-69: Snapshot arrays are immutable tuples, immune to in-place RNA mutations, and restored properly.
- TEST-70: Failure during constraint property restoration aggregates dual exceptions with exact context.
- TEST-71: Rollback protects collections created externally during transaction while removing transaction collections.
- TEST-72: Character collection with multiple parents, renamed or reparented in transaction, is restored 100%.
- TEST-73: Stashed wrong-type constraints and unrelated custom constraints preserve identities and order on rollback.
- TEST-74: Sequential snapshot failure -> write failure -> clean rollback -> normal setup -> idempotent re-run.
- TEST-75: Failure on L side set_hand_ik_target isolates R side completely and protects shared datablock.
- TEST-76: Verifier captures 6 distinct corruption dimensions with exact field names without mutating scene.
"""

import math
import os
import sys
import unittest

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

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
    _ACTIVE_TRANSACTION_STACK,
    _ArmRigTransactionState,
    _arm_rig_transaction,
    _clear_test_depsgraph_updater,
    _clear_test_fault_injection_hook,
    _depsgraph_update,
    _rollback_arm_rig_state,
    _set_test_depsgraph_updater,
    _set_test_fault_injection_hook,
    _snapshot_arm_rig_state,
    _verify_arm_rig_state_restored,
    get_arm_ik_state,
    reset_arm_ik,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


class TestArmIKTransactionAtomicity(unittest.TestCase):
    """Test suite verifying Arm IK transaction snapshot, atomic rollback, and fault resilience."""

    def setUp(self) -> None:
        """Reset Blender state, clear hooks, and build fresh character rig."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _clear_test_fault_injection_hook()
        _clear_test_depsgraph_updater()
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

    def tearDown(self) -> None:
        """Ensure fault injection hooks and depsgraph updaters are cleared."""
        _clear_test_fault_injection_hook()
        _clear_test_depsgraph_updater()

    # -------------------------------------------------------------------------
    # Snapshot Fidelity Tests (TEST-31 to TEST-33)
    # -------------------------------------------------------------------------

    def test_31_snapshot_fidelity_controllers(self) -> None:
        """TEST-31: Snapshot covers 4 controllers, data blocks, parent, TRS, mode, collections with zero mutation."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        bpy.context.view_layer.update()

        objs_before = set(bpy.data.objects.keys())
        bones_rot_before = {
            b.name: (b.rotation_mode, tuple(b.rotation_euler))
            for b in self.armature.pose.bones
        }

        snap = _snapshot_arm_rig_state(self.armature)

        # Verify zero mutation occurred during snapshot
        self.assertEqual(set(bpy.data.objects.keys()), objs_before)
        for b in self.armature.pose.bones:
            self.assertEqual(
                (b.rotation_mode, tuple(b.rotation_euler)),
                bones_rot_before[b.name],
            )

        ctrls = snap["controllers"]
        for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(c_name, ctrls)
            cs = ctrls[c_name]
            self.assertTrue(cs["exists"])
            self.assertEqual(cs["type"], "EMPTY")
            self.assertIsNotNone(cs["obj_ref"])
            self.assertEqual(cs["obj_name"], c_name)
            self.assertEqual(cs["parent"], self.root)
            self.assertIsInstance(cs["matrix_parent_inverse"], Matrix)
            self.assertIsInstance(cs["location"], Vector)
            self.assertIn(cs["rotation_mode"], ("XYZ", "QUATERNION", "AXIS_ANGLE"))
            self.assertIsInstance(cs["scale"], Vector)
            self.assertIsInstance(cs["matrix_world"], Matrix)
            self.assertIn("Character", cs["collections"])

    def test_32_snapshot_fidelity_pose_bones(self) -> None:
        """TEST-32: Snapshot covers 6 upper-limb pose bones with transform properties, IK locks, and limits."""
        setup_arm_ik(self.armature)
        snap = _snapshot_arm_rig_state(self.armature)
        bones = snap["pose_bones"]

        for b_name in ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R"):
            self.assertIn(b_name, bones)
            bs = bones[b_name]
            self.assertIsInstance(bs["location"], Vector)
            self.assertEqual(bs["rotation_mode"], "XYZ")
            self.assertIsInstance(bs["rotation_euler"], Euler)
            self.assertIsInstance(bs["scale"], Vector)
            self.assertIsInstance(bs["matrix_basis"], Matrix)
            self.assertIn("lock_ik_x", bs)
            self.assertIn("use_ik_limit_x", bs)
            self.assertIn("ik_min_x", bs)
            self.assertIn("ik_max_x", bs)

        # Check elbow anatomical limit fidelity
        self.assertTrue(bones["forearm.L"]["use_ik_limit_x"])
        self.assertAlmostEqual(bones["forearm.L"]["ik_min_x"], 0.0, places=4)
        self.assertAlmostEqual(bones["forearm.L"]["ik_max_x"], math.radians(150.0), places=4)
        self.assertTrue(bones["forearm.L"]["lock_ik_y"])
        self.assertTrue(bones["forearm.L"]["lock_ik_z"])

    def test_33_snapshot_fidelity_constraints_and_collection(self) -> None:
        """TEST-33: Snapshot covers constraint configurations, ordering, targets, and Character collection."""
        setup_arm_ik(self.armature, initial_influence=0.75)
        snap = _snapshot_arm_rig_state(self.armature)

        char_col = snap["character_collection"]
        self.assertTrue(char_col["existed"])
        self.assertTrue(char_col["children_of_scene"])
        self.assertIn("HandIK.L", char_col["object_names"])
        self.assertIn("ElbowPole.R", char_col["object_names"])

        forearm_l_cons = snap["pose_bones"]["forearm.L"]["constraints"]
        self.assertEqual(len(forearm_l_cons), 1)
        ik_con = forearm_l_cons[0]
        self.assertEqual(ik_con["name"], "ArmIK.L")
        self.assertEqual(ik_con["type"], "IK")
        self.assertAlmostEqual(ik_con["influence"], 0.75, places=5)
        self.assertEqual(ik_con["chain_count"], 2)
        self.assertAlmostEqual(ik_con["pole_angle"], math.radians(-90.0), places=4)

        hand_l_cons = snap["pose_bones"]["hand.L"]["constraints"]
        self.assertEqual(len(hand_l_cons), 1)
        rot_con = hand_l_cons[0]
        self.assertEqual(rot_con["name"], "HandRotation.L")
        self.assertEqual(rot_con["type"], "COPY_ROTATION")
        self.assertAlmostEqual(rot_con["influence"], 0.75, places=5)

    # -------------------------------------------------------------------------
    # Direct Rollback Fidelity Tests (TEST-34 to TEST-38)
    # -------------------------------------------------------------------------

    def test_34_direct_rollback_uninitialized_scene(self) -> None:
        """TEST-34: Rollback on uninitialized scene removes 4 controllers, constraints, and created Character col."""
        # Unlink Character collection to test uninitialized collection cleanup
        col = bpy.data.collections.get("Character")
        if col is not None:
            if col.name in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.unlink(col)
            bpy.data.collections.remove(col)
        bpy.context.view_layer.update()

        snap_initial = _snapshot_arm_rig_state(self.armature)
        self.assertFalse(snap_initial["character_collection"]["existed"])

        # Create controllers and constraints
        setup_arm_ik(self.armature, initial_influence=0.5)
        for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(c_name, bpy.data.objects)

        # Rollback directly
        _rollback_arm_rig_state(self.armature, snap_initial)
        _verify_arm_rig_state_restored(self.armature, snap_initial)

        # Verify controllers and constraints removed, Character collection removed
        for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertNotIn(c_name, bpy.data.objects)
        self.assertNotIn("Character", bpy.data.collections)
        self.assertEqual(len(self.armature.pose.bones["forearm.L"].constraints), 0)

    def test_35_direct_rollback_wrong_type_controller(self) -> None:
        """TEST-35: Rollback on wrong-type controller restores original object type, data block, and collections."""
        mesh_data = bpy.data.meshes.new("OriginalHandIKMesh")
        wrong_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.context.scene.collection.objects.link(wrong_obj)
        wrong_obj.location = Vector((1.0, 2.0, 3.0))

        snap = _snapshot_arm_rig_state(self.armature)
        self.assertTrue(snap["controllers"]["HandIK.L"]["exists"])
        self.assertEqual(snap["controllers"]["HandIK.L"]["type"], "MESH")

        # Execute setup under transaction which replaces wrong-type object
        with self.assertRaises(RuntimeError):
            with _arm_rig_transaction(self.armature):
                setup_arm_ik(self.armature)
                # Verify that inside the transaction, HandIK.L is now an Empty
                curr_empty = bpy.data.objects.get("HandIK.L")
                self.assertIsNotNone(curr_empty)
                self.assertEqual(curr_empty.type, "EMPTY")
                raise RuntimeError("Fault injected to trigger rollback")

        # After rollback, verify original object reference, datablock, and type are restored
        restored_obj = bpy.data.objects.get("HandIK.L")
        self.assertIsNotNone(restored_obj)
        self.assertEqual(restored_obj.type, "MESH")
        self.assertIs(restored_obj, wrong_obj)
        self.assertIs(restored_obj.data, mesh_data)
        self.assertIn(restored_obj.name, bpy.context.scene.collection.objects)
        self.assertAlmostEqual((restored_obj.location - Vector((1.0, 2.0, 3.0))).length, 0.0, places=5)
        _verify_arm_rig_state_restored(self.armature, snap)

    def test_36_direct_rollback_initialized_scene_controllers(self) -> None:
        """TEST-36: Rollback on initialized scene restores controller transforms, parents, and rotation modes."""
        setup_arm_ik(self.armature, initial_influence=0.2)
        snap = _snapshot_arm_rig_state(self.armature)

        # Mutate controller properties
        ik_l = bpy.data.objects["HandIK.L"]
        ik_l.location = Vector((9.9, 8.8, 7.7))
        ik_l.rotation_mode = "ZYX"
        ik_l.rotation_euler = Euler((0.5, 0.5, 0.5), "ZYX")
        ik_l.parent = None
        ik_l.matrix_parent_inverse = Matrix.Scale(2.0, 4)
        bpy.context.view_layer.update()

        _rollback_arm_rig_state(self.armature, snap)
        _verify_arm_rig_state_restored(self.armature, snap)

        self.assertEqual(ik_l.parent, self.root)
        self.assertEqual(ik_l.rotation_mode, "XYZ")
        self.assertAlmostEqual((ik_l.location - snap["controllers"]["HandIK.L"]["location"]).length, 0.0, places=5)

    def test_37_direct_rollback_pose_bones(self) -> None:
        """TEST-37: Rollback on pose bones restores rotation mode, limits, locks, and transforms."""
        setup_arm_ik(self.armature)
        snap = _snapshot_arm_rig_state(self.armature)

        p_fore = self.armature.pose.bones["forearm.L"]
        p_fore.rotation_mode = "QUATERNION"
        p_fore.rotation_quaternion = Quaternion((0.5, 0.5, 0.5, 0.5))
        p_fore.lock_ik_x = True
        p_fore.use_ik_limit_x = False
        p_fore.ik_max_x = math.radians(45.0)
        bpy.context.view_layer.update()

        _rollback_arm_rig_state(self.armature, snap)
        _verify_arm_rig_state_restored(self.armature, snap)

        self.assertEqual(p_fore.rotation_mode, "XYZ")
        self.assertFalse(p_fore.lock_ik_x)
        self.assertTrue(p_fore.use_ik_limit_x)
        self.assertAlmostEqual(p_fore.ik_max_x, math.radians(150.0), places=4)

    def test_38_direct_rollback_constraints(self) -> None:
        """TEST-38: Rollback on constraints restores constraint counts, order, types, and influences."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        snap = _snapshot_arm_rig_state(self.armature)

        p_fore = self.armature.pose.bones["forearm.L"]
        # Delete existing IK constraint
        for con in list(p_fore.constraints):
            p_fore.constraints.remove(con)
        # Add extraneous constraint
        p_fore.constraints.new(type="TRACK_TO")
        bpy.context.view_layer.update()

        _rollback_arm_rig_state(self.armature, snap)
        _verify_arm_rig_state_restored(self.armature, snap)

        self.assertEqual(len(p_fore.constraints), 1)
        self.assertEqual(p_fore.constraints[0].name, "ArmIK.L")
        self.assertEqual(p_fore.constraints[0].type, "IK")
        self.assertAlmostEqual(p_fore.constraints[0].influence, 0.4, places=5)

    # -------------------------------------------------------------------------
    # Fault Injection Tests (TEST-39 to TEST-50)
    # -------------------------------------------------------------------------

    def test_39_fault_injection_setup_arm_ik_after_first_controller(self) -> None:
        """TEST-39: Fault injection in setup_arm_ik() after first controller created rolls back completely."""
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                # Verify that the write actually happened before raising
                self.assertIn("HandIK.L", bpy.data.objects)
                raise RuntimeError("Fault injected after HandIK.L creation")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault injected after HandIK.L creation", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertNotIn("HandIK.L", bpy.data.objects)
        self.assertNotIn("ElbowPole.L", bpy.data.objects)

    def test_40_fault_injection_setup_arm_ik_after_controller_replaced(self) -> None:
        """TEST-40: Fault injection in setup_arm_ik() after wrong-type controller replaced restores original object."""
        mesh_data = bpy.data.meshes.new("WrongTypeMesh")
        mesh_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.context.scene.collection.objects.link(mesh_obj)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_controller_replaced":
                raise RuntimeError("Fault injected after wrong controller replaced")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault injected after wrong controller replaced", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        restored = bpy.data.objects.get("HandIK.L")
        self.assertIs(restored, mesh_obj)
        self.assertIs(restored.data, mesh_data)

    def test_41_fault_injection_setup_arm_ik_after_constraints_or_prebend(self) -> None:
        """TEST-41: Fault injection in setup_arm_ik() after constraints/pre-bend modified restores state."""
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend":
                # Verify constraints and pre-bend were actually written
                self.assertIn("ArmIK.L", self.armature.pose.bones["forearm.L"].constraints)
                raise RuntimeError("Fault injected after constraints created")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault injected after constraints created", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(len(self.armature.pose.bones["forearm.L"].constraints), 0)

    def test_42_fault_injection_set_hand_ik_target_during_auto_init(self) -> None:
        """TEST-42: Fault injection in set_hand_ik_target() during auto-init rolls back to uninitialized state."""
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_during_auto_init":
                # Triggered when auto-init creates first controller
                self.assertIn("HandIK.L", bpy.data.objects)
                raise RuntimeError("Fault injected during auto-init")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=(0.3, -0.1, 1.1))
        self.assertIn("Fault injected during auto-init", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertNotIn("HandIK.L", bpy.data.objects)

    def test_43_fault_injection_set_hand_ik_target_after_hand_location(self) -> None:
        """TEST-43: Fault injection in set_hand_ik_target() after HandIK Location written restores location."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        snap_initial = _snapshot_arm_rig_state(self.armature)
        orig_loc = bpy.data.objects["HandIK.L"].location.copy()

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                # Verify location has actually changed before raising
                curr_loc = bpy.data.objects["HandIK.L"].location
                self.assertNotEqual(curr_loc, orig_loc)
                raise RuntimeError("Fault injected after HandIK location written")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=(0.4, -0.3, 1.2))
        self.assertIn("Fault injected after HandIK location written", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertAlmostEqual((bpy.data.objects["HandIK.L"].location - orig_loc).length, 0.0, places=5)

    def test_44_fault_injection_set_hand_ik_target_after_hand_rotation(self) -> None:
        """TEST-44: Fault injection in set_hand_ik_target() after HandIK Rotation written restores rotation."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        snap_initial = _snapshot_arm_rig_state(self.armature)
        orig_rot = tuple(bpy.data.objects["HandIK.L"].rotation_euler)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_rotation":
                curr_rot = tuple(bpy.data.objects["HandIK.L"].rotation_euler)
                self.assertNotEqual(curr_rot, orig_rot)
                raise RuntimeError("Fault injected after HandIK rotation written")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(
                self.armature,
                side="L",
                world_xyz=(0.4, -0.3, 1.2),
                hand_rotation_deg=(45.0, 30.0, 60.0),
            )
        self.assertIn("Fault injected after HandIK rotation written", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(tuple(bpy.data.objects["HandIK.L"].rotation_euler), orig_rot)

    def test_45_fault_injection_set_hand_ik_target_after_pole_location(self) -> None:
        """TEST-45: Fault injection in set_hand_ik_target() after ElbowPole Location written restores pole."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        snap_initial = _snapshot_arm_rig_state(self.armature)
        orig_pole_loc = bpy.data.objects["ElbowPole.L"].location.copy()

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_pole_location":
                curr_loc = bpy.data.objects["ElbowPole.L"].location
                self.assertNotEqual(curr_loc, orig_pole_loc)
                raise RuntimeError("Fault injected after ElbowPole location written")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(
                self.armature,
                side="L",
                world_xyz=(0.4, -0.3, 1.2),
                pole_world_xyz=(0.6, -0.8, 1.3),
            )
        self.assertIn("Fault injected after ElbowPole location written", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertAlmostEqual(
            (bpy.data.objects["ElbowPole.L"].location - orig_pole_loc).length, 0.0, places=5
        )

    def test_46_fault_injection_set_hand_ik_target_between_influences(self) -> None:
        """TEST-46: Fault injection between ArmIK and HandRotation influence writes keeps influences in sync."""
        setup_arm_ik(self.armature, initial_influence=0.1)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_between_influences":
                # ArmIK influence was set to 0.9, but HandRotation not yet set
                self.assertAlmostEqual(
                    self.armature.pose.bones["forearm.L"].constraints["ArmIK.L"].influence,
                    0.9,
                    places=4,
                )
                raise RuntimeError("Fault injected between influence updates")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=(0.35, -0.1, 1.2), influence=0.9)
        self.assertIn("Fault injected between influence updates", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        # Verify influences remain in sync at original 0.1
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints["ArmIK.L"].influence,
            0.1,
            places=4,
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["hand.L"].constraints["HandRotation.L"].influence,
            0.1,
            places=4,
        )

    def test_47_fault_injection_set_hand_ik_target_after_rot_influence(self) -> None:
        """TEST-47: Fault injection after HandRotation influence modified rolls back all writes."""
        setup_arm_ik(self.armature, initial_influence=0.2)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_rot_influence":
                raise RuntimeError("Fault injected after rot influence update")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=(0.35, -0.1, 1.2), influence=0.85)
        self.assertIn("Fault injected after rot influence update", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_48_fault_injection_set_hand_ik_target_during_state_read(self) -> None:
        """TEST-48: Fault injection during view_layer.update / get_arm_ik_state revokes all prior writes."""
        setup_arm_ik(self.armature, initial_influence=0.0)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_during_state_read":
                raise RuntimeError("Fault injected during state read")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=(0.35, -0.2, 1.1), influence=0.9)
        self.assertIn("Fault injected during state read", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_49_fault_injection_set_arm_ik_influence_side_l(self) -> None:
        """TEST-49: Fault injection in set_arm_ik_influence(side='L') mid-write restores L and leaves R intact."""
        setup_arm_ik(self.armature, initial_influence=0.3)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences" and ctx.get("side") == "L":
                raise RuntimeError("Fault injected mid-write on side L")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_arm_ik_influence(self.armature, side="L", influence=0.8)
        self.assertIn("Fault injected mid-write on side L", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints["ArmIK.L"].influence,
            0.3,
            places=4,
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.R"].constraints["ArmIK.R"].influence,
            0.3,
            places=4,
        )

    def test_50_fault_injection_set_arm_ik_influence_side_both(self) -> None:
        """TEST-50: Fault injection in set_arm_ik_influence(side='BOTH') restores all 4 constraints without half-update."""
        setup_arm_ik(self.armature, initial_influence=0.25)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_sides":
                # L was updated, R not yet updated
                self.assertAlmostEqual(
                    self.armature.pose.bones["forearm.L"].constraints["ArmIK.L"].influence,
                    0.95,
                    places=4,
                )
                raise RuntimeError("Fault injected between side L and side R")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_arm_ik_influence(self.armature, side="BOTH", influence=0.95)
        self.assertIn("Fault injected between side L and side R", str(cm.exception))

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        for s in ("L", "R"):
            self.assertAlmostEqual(
                self.armature.pose.bones[f"forearm.{s}"].constraints[f"ArmIK.{s}"].influence,
                0.25,
                places=4,
            )
            self.assertAlmostEqual(
                self.armature.pose.bones[f"hand.{s}"].constraints[f"HandRotation.{s}"].influence,
                0.25,
                places=4,
            )

    # -------------------------------------------------------------------------
    # Lifecycle & Edge Condition Tests (TEST-51 to TEST-52)
    # -------------------------------------------------------------------------

    def test_51_success_path_fresh_and_reentrant_across_8_rotation_modes(self) -> None:
        """TEST-51: Success path fresh & re-entrant calls across all 8 rotation modes (6 Eulers, QUAT, AXIS_ANGLE)."""
        modes = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX", "QUATERNION", "AXIS_ANGLE")

        for mode in modes:
            with self.subTest(rotation_mode=mode):
                # Fresh auto-init call
                bpy.ops.wm.read_factory_settings(use_empty=True)
                char_data = build_character(self.config)
                arm = build_rig(self.config)
                bind_character_to_rig(arm, char_data["parts"])
                setup_leg_ik(arm)

                # Set desired rotation mode on target controller before call
                setup_arm_ik(arm)
                bpy.data.objects["HandIK.L"].rotation_mode = mode
                bpy.data.objects["HandIK.R"].rotation_mode = mode

                # Call for Left side
                y_pos = char_data["root"].location.y + 0.15
                state_l = set_hand_ik_target(
                    arm,
                    side="L",
                    world_xyz=(-0.32, y_pos, 1.20),
                    hand_rotation_deg=(20.0, 30.0, -10.0),
                    influence=1.0,
                )
                self.assertTrue(state_l["is_reachable"])
                self.assertLess(state_l["target_error"], 0.05)
                self.assertEqual(bpy.data.objects["HandIK.L"].rotation_mode, mode)

                # Re-entrant call for Right side
                state_r = set_hand_ik_target(
                    arm,
                    side="R",
                    world_xyz=(0.32, y_pos, 1.20),
                    hand_rotation_deg=(-20.0, -30.0, 10.0),
                    influence=1.0,
                )
                self.assertTrue(state_r["is_reachable"])
                self.assertLess(state_r["target_error"], 0.05)
                self.assertEqual(bpy.data.objects["HandIK.R"].rotation_mode, mode)

    def test_52_success_after_failure_recovery_and_explicit_verification_error(self) -> None:
        """TEST-52: Success after recovery; explicit failure report if rollback verification fails."""
        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        # 1. Trigger a transaction failure and rollback
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Transient injected fault")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError):
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos)

        # Clear fault hook and verify subsequent call succeeds completely
        _clear_test_fault_injection_hook()
        state = set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=1.0)
        self.assertIsNotNone(state)
        self.assertTrue(state["is_reachable"])
        self.assertLess(state["target_error"], 0.05)

        # 2. Simulate rollback verification failure by tampering with restored state during rollback
        def corrupting_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Primary transaction failure")
            elif stage == "during_rollback_verification":
                # Tamper with restored controller location to trigger verification mismatch
                if "HandIK.L" in bpy.data.objects:
                    bpy.data.objects["HandIK.L"].location += Vector((1.0, 1.0, 1.0))

        _set_test_fault_injection_hook(corrupting_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos)

        err_msg = str(cm.exception)
        # Must explicitly report both primary failure and verification failure
        self.assertIn("Primary transaction failure", err_msg)
        self.assertIn("rollback verification failed", err_msg)
        self.assertIn("Arm rig transaction failed with RuntimeError", err_msg)

    # -------------------------------------------------------------------------
    # Independent Audit Correction Tests (TEST-53 to TEST-64)
    # -------------------------------------------------------------------------

    def test_53_controller_full_fields_verification(self) -> None:
        """TEST-53: _verify_arm_rig_state_restored() detects tampering on controller matrix_parent_inverse, Eulers, Quat, AxisAngle, matrix_world."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        ctrl = bpy.data.objects["HandIK.L"]
        ctrl.rotation_mode = "AXIS_ANGLE"
        ctrl.rotation_axis_angle = (0.5, 0.0, 1.0, 0.0)
        bpy.context.view_layer.update()
        snap = _snapshot_arm_rig_state(self.armature)

        # 1. matrix_parent_inverse tampering
        orig_val = ctrl.matrix_parent_inverse[0][0]
        ctrl.matrix_parent_inverse[0][0] += 0.5
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("HandIK.L", str(cm.exception))
        self.assertIn("matrix_parent_inverse", str(cm.exception))
        ctrl.matrix_parent_inverse[0][0] = orig_val

        # 2. rotation_euler tampering
        ctrl.rotation_mode = "XYZ"
        bpy.context.view_layer.update()
        snap_euler = _snapshot_arm_rig_state(self.armature)
        ctrl.rotation_euler.x += 0.2
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap_euler)
        self.assertIn("HandIK.L", str(cm.exception))
        self.assertIn("rotation_euler", str(cm.exception))
        ctrl.rotation_euler.x -= 0.2

        # 3. rotation_quaternion tampering
        ctrl.rotation_mode = "QUATERNION"
        bpy.context.view_layer.update()
        snap_quat = _snapshot_arm_rig_state(self.armature)
        ctrl.rotation_quaternion.w += 0.3
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap_quat)
        self.assertIn("HandIK.L", str(cm.exception))
        self.assertIn("rotation_quaternion", str(cm.exception))
        ctrl.rotation_quaternion.w -= 0.3

        # 4. rotation_axis_angle tampering
        ctrl.rotation_mode = "AXIS_ANGLE"
        bpy.context.view_layer.update()
        snap_axis = _snapshot_arm_rig_state(self.armature)
        ctrl.rotation_axis_angle[0] += 0.4
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap_axis)
        self.assertIn("HandIK.L", str(cm.exception))
        self.assertIn("rotation_axis_angle", str(cm.exception))
        ctrl.rotation_axis_angle[0] -= 0.4

        # 5. matrix_world tampering
        orig_w = ctrl.matrix_world[1][1]
        ctrl.matrix_world[1][1] += 0.5
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap_axis)
        self.assertIn("HandIK.L", str(cm.exception))
        self.assertIn("matrix_world", str(cm.exception))
        ctrl.matrix_world[1][1] = orig_w

    def test_54_bone_full_fields_verification(self) -> None:
        """TEST-54: _verify_arm_rig_state_restored() detects tampering on all 6 bones (Eulers, Quat, AxisAngle, matrix_basis)."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        bone_names = ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R")

        for b_name in bone_names:
            pbone = self.armature.pose.bones[b_name]
            pbone.rotation_mode = "XYZ"
            bpy.context.view_layer.update()
            snap = _snapshot_arm_rig_state(self.armature)

            # rotation_euler
            pbone.rotation_euler.x += 0.2
            with self.assertRaises(RuntimeError) as cm:
                _verify_arm_rig_state_restored(self.armature, snap)
            self.assertIn(b_name, str(cm.exception))
            self.assertIn("rotation_euler", str(cm.exception))
            pbone.rotation_euler.x -= 0.2

            # rotation_quaternion
            pbone.rotation_mode = "QUATERNION"
            bpy.context.view_layer.update()
            snap_q = _snapshot_arm_rig_state(self.armature)
            pbone.rotation_quaternion.w += 0.2
            with self.assertRaises(RuntimeError) as cm:
                _verify_arm_rig_state_restored(self.armature, snap_q)
            self.assertIn(b_name, str(cm.exception))
            self.assertIn("rotation_quaternion", str(cm.exception))
            pbone.rotation_quaternion.w -= 0.2

            # rotation_axis_angle
            pbone.rotation_mode = "AXIS_ANGLE"
            bpy.context.view_layer.update()
            snap_a = _snapshot_arm_rig_state(self.armature)
            pbone.rotation_axis_angle[0] += 0.3
            with self.assertRaises(RuntimeError) as cm:
                _verify_arm_rig_state_restored(self.armature, snap_a)
            self.assertIn(b_name, str(cm.exception))
            self.assertIn("rotation_axis_angle", str(cm.exception))
            pbone.rotation_axis_angle[0] -= 0.3

            # matrix_basis
            orig_m = pbone.matrix_basis[0][0]
            pbone.matrix_basis[0][0] += 0.5
            with self.assertRaises(RuntimeError) as cm:
                _verify_arm_rig_state_restored(self.armature, snap_a)
            self.assertIn(b_name, str(cm.exception))
            self.assertIn("matrix_basis", str(cm.exception))
            pbone.matrix_basis[0][0] = orig_m

    def test_55_constraints_full_fields_verification(self) -> None:
        """TEST-55: _verify_arm_rig_state_restored() detects tampering on IK and COPY_ROTATION specific parameters."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        snap = _snapshot_arm_rig_state(self.armature)

        # 1. IK constraint on forearm.L
        ik_con = self.armature.pose.bones["forearm.L"].constraints["ArmIK.L"]

        # chain_count
        ik_con.chain_count = 3
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("chain_count", str(cm.exception))
        ik_con.chain_count = 2

        # pole_angle
        ik_con.pole_angle += 0.5
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("pole_angle", str(cm.exception))
        ik_con.pole_angle -= 0.5

        # target
        orig_t = ik_con.target
        ik_con.target = None
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("target", str(cm.exception))
        ik_con.target = orig_t

        # pole_target
        orig_pt = ik_con.pole_target
        ik_con.pole_target = None
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("pole_target", str(cm.exception))
        ik_con.pole_target = orig_pt

        # use_stretch
        ik_con.use_stretch = True
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("use_stretch", str(cm.exception))
        ik_con.use_stretch = False

        # 2. COPY_ROTATION on hand.L
        rot_con = self.armature.pose.bones["hand.L"].constraints["HandRotation.L"]

        # target_space
        rot_con.target_space = "LOCAL"
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("target_space", str(cm.exception))
        rot_con.target_space = "WORLD"

        # owner_space
        rot_con.owner_space = "LOCAL"
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("owner_space", str(cm.exception))
        rot_con.owner_space = "WORLD"

        # mix_mode
        rot_con.mix_mode = "BEFORE"
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("mix_mode", str(cm.exception))
        rot_con.mix_mode = "REPLACE"

        # use_x
        rot_con.use_x = False
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("use_x", str(cm.exception))
        rot_con.use_x = True

        # invert_y
        rot_con.invert_y = True
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("invert_y", str(cm.exception))
        rot_con.invert_y = False

    def test_56_wrong_type_and_unrelated_constraints_lossless_recovery(self) -> None:
        """TEST-56: Lossless recovery of preexisting unrelated and wrong-type constraints after transaction rollback."""
        p_fore = self.armature.pose.bones["forearm.L"]

        # Add unrelated constraint (e.g. LIMIT_ROTATION)
        unrelated = p_fore.constraints.new(type="LIMIT_ROTATION")
        unrelated.name = "CustomLimitRot"
        unrelated.use_limit_x = True
        unrelated.min_x = math.radians(-30.0)
        unrelated.max_x = math.radians(60.0)

        # Add wrong-type constraint with target name ArmIK.L (e.g. COPY_LOCATION targeting CharacterRoot)
        wrong_con = p_fore.constraints.new(type="COPY_LOCATION")
        wrong_con.name = "ArmIK.L"
        wrong_con.target = self.root
        wrong_con.use_x = True
        wrong_con.use_y = False
        wrong_con.use_z = True
        wrong_con.influence = 0.77

        snap_initial = _snapshot_arm_rig_state(self.armature)

        # Fault injection after setup_arm_ik modifies constraints
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend":
                raise RuntimeError("Fault injected during constraint setup")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault injected during constraint setup", str(cm.exception))

        # Verification after rollback:
        # 1. Unrelated constraint retained identity and attributes
        self.assertIn("CustomLimitRot", p_fore.constraints)
        c_unrel = p_fore.constraints["CustomLimitRot"]
        self.assertEqual(c_unrel, unrelated)
        self.assertEqual(c_unrel.as_pointer(), unrelated.as_pointer())
        self.assertEqual(c_unrel.type, "LIMIT_ROTATION")
        self.assertTrue(c_unrel.use_limit_x)
        self.assertAlmostEqual(c_unrel.min_x, math.radians(-30.0), places=4)

        # 2. Wrong-type constraint retained identity and attributes
        self.assertIn("ArmIK.L", p_fore.constraints)
        c_wrong = p_fore.constraints["ArmIK.L"]
        self.assertEqual(c_wrong, wrong_con)
        self.assertEqual(c_wrong.as_pointer(), wrong_con.as_pointer())
        self.assertEqual(c_wrong.type, "COPY_LOCATION")
        self.assertIs(c_wrong.target, self.root)
        self.assertAlmostEqual(c_wrong.influence, 0.77, places=4)

        # 3. Full rig state verification matches initial snapshot
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_57_collection_hierarchy_full_recovery(self) -> None:
        """TEST-57: Full recovery of multi-level nested collection hierarchy and scene linkages after transaction rollback."""
        # Setup multi-level collection hierarchy: Scene -> OuterCol -> InnerCol -> Character
        outer_col = bpy.data.collections.new("OuterCol")
        inner_col = bpy.data.collections.new("InnerCol")
        bpy.context.scene.collection.children.link(outer_col)
        outer_col.children.link(inner_col)

        char_col = bpy.data.collections.get("Character")
        if char_col is None:
            char_col = bpy.data.collections.new("Character")
        if char_col.name in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.unlink(char_col)
        inner_col.children.link(char_col)

        bpy.context.view_layer.update()
        snap_initial = _snapshot_arm_rig_state(self.armature)

        # Inside transaction: create a new collection, reparent Character, and inject error
        with self.assertRaises(RuntimeError):
            with _arm_rig_transaction(self.armature) as tx:
                rogue_col = bpy.data.collections.new("RogueCol")
                bpy.context.scene.collection.children.link(rogue_col)
                tx.register_created_collection(rogue_col, initial_parent=bpy.context.scene.collection)
                setup_arm_ik(self.armature)
                raise RuntimeError("Fault inside transaction with modified collections")

        # Verify:
        # 1. RogueCol removed
        self.assertNotIn("RogueCol", bpy.data.collections)

        # 2. Character still child of InnerCol and NOT in scene root
        self.assertIn(char_col.name, inner_col.children)
        self.assertNotIn(char_col.name, bpy.context.scene.collection.children)

        # 3. OuterCol and InnerCol hierarchy preserved
        self.assertIn(outer_col.name, bpy.context.scene.collection.children)
        self.assertIn(inner_col.name, outer_col.children)

        # 4. _verify_arm_rig_state_restored succeeds
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_58_snapshot_failure_clears_active_transaction_stack(self) -> None:
        """TEST-58: Fault during _snapshot_arm_rig_state() completely cleans up transaction stack allowing subsequent calls."""
        from src.rig.arm_ik import _ACTIVE_TRANSACTION_STACK

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                raise RuntimeError("Fault during snapshot capture")

        _set_test_fault_injection_hook(fault_hook)

        # First call fails at snapshot creation
        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault during snapshot capture", str(cm.exception))

        # Stack must be completely empty
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Clear fault hook
        _clear_test_fault_injection_hook()

        # Subsequent call must succeed completely without stale transaction state
        controls = setup_arm_ik(self.armature)
        self.assertIsNotNone(controls)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Verify that a subsequent failing call can still take a fresh snapshot and rollback cleanly
        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)
        snap_fresh = _snapshot_arm_rig_state(self.armature)

        def fault_hook_step(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault after location write")

        _set_test_fault_injection_hook(fault_hook_step)
        with self.assertRaises(RuntimeError):
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos)

        _verify_arm_rig_state_restored(self.armature, snap_fresh)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_59_cross_armature_nested_transaction_rejection(self) -> None:
        """TEST-59: Cross-armature nested transaction call is rejected without mutating either armature."""
        # Create second independent armature without disturbing self.armature
        arm_data_b = bpy.data.armatures.new("CharacterArmature_B_Data")
        arm_b = bpy.data.objects.new("CharacterArmature_B", arm_data_b)
        bpy.context.scene.collection.objects.link(arm_b)
        bpy.context.view_layer.objects.active = arm_b
        bpy.ops.object.mode_set(mode="EDIT")
        for b_name in ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R"):
            eb = arm_data_b.edit_bones.new(b_name)
            eb.head = (0.0, 0.0, 1.0)
            eb.tail = (0.0, 0.0, 1.2)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.context.view_layer.objects.active = self.armature
        bpy.context.view_layer.update()

        snap_a = _snapshot_arm_rig_state(self.armature)
        snap_b = _snapshot_arm_rig_state(arm_b)

        # Start transaction on armature A, and attempt nested transaction on armature B
        with _arm_rig_transaction(self.armature):
            with self.assertRaises(RuntimeError) as cm:
                with _arm_rig_transaction(arm_b):
                    pass
            self.assertIn("Cross-armature nested transaction rejected", str(cm.exception))

        # Assert armature B was never mutated
        _verify_arm_rig_state_restored(arm_b, snap_b)
        _verify_arm_rig_state_restored(self.armature, snap_a)

    def test_60_get_arm_ik_state_internal_exception_triggers_rollback(self) -> None:
        """TEST-60: Genuine exception inside get_arm_ik_state() after full writes triggers complete rollback and bubbles up."""
        setup_arm_ik(self.armature, initial_influence=0.2)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        # Monkeypatch get_arm_ik_state inside src.rig.arm_ik
        import src.rig.arm_ik as arm_ik_mod
        orig_getter = arm_ik_mod.get_arm_ik_state

        def crashing_getter(arm, side):
            raise RuntimeError("Genuine internal getter error")

        arm_ik_mod.get_arm_ik_state = crashing_getter
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.9)
            self.assertIn("Genuine internal getter error", str(cm.exception))
        finally:
            arm_ik_mod.get_arm_ik_state = orig_getter

        # Verify complete rollback
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_61_depsgraph_update_exception_triggers_rollback(self) -> None:
        """TEST-61: Exception during dependency graph update stage rolls back all writes.

        Note: This test verifies the fault injection hook positioned immediately before
        the dependency graph update call. In contrast, TEST-68 tests the actual
        _DEPSGRAPH_UPDATER call boundary adapter exception handling. The two tests
        complement each other.
        """
        setup_arm_ik(self.armature, initial_influence=0.1)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_during_depsgraph_update":
                raise RuntimeError("DepsGraph evaluation failed")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.85)
        self.assertIn("DepsGraph evaluation failed", str(cm.exception))

        # Verify complete rollback
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_62_first_time_autoinit_success_path_and_failure_resilience(self) -> None:
        """TEST-62: Direct set_hand_ik_target() on uninitialized scene succeeds; subsequent failure call rolls back."""
        # Uninitialized scene: no controllers or arm constraints
        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        # Direct set_hand_ik_target() with full influence for reach accuracy
        state = set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=1.0)

        # 1. Verify success results
        self.assertIsNotNone(state)
        self.assertTrue(state["is_reachable"])
        self.assertLess(state["target_error"], 0.05)
        self.assertAlmostEqual(state["ik_influence"], 1.0, places=4)

        # Verify controllers created as valid EMPTYs
        for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(c_name, bpy.data.objects)
            self.assertEqual(bpy.data.objects[c_name].type, "EMPTY")

        # Right side did not receive unexpected target write
        self.assertAlmostEqual(self.armature.pose.bones["forearm.R"].constraints["ArmIK.R"].influence, 1.0, places=4)

        # 2. Subsequent failure call rolls back to post-autoinit state
        snap_post_init = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault in subsequent call")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError):
            set_hand_ik_target(self.armature, side="R", world_xyz=(0.32, y_pos, 1.20))

        _verify_arm_rig_state_restored(self.armature, snap_post_init)

    def test_63_fault_injection_public_interface_boundary(self) -> None:
        """TEST-63: Fault injection functions are strictly private; hooks do not leak across exceptions and tests."""
        import src.rig.arm_ik as arm_ik_mod

        # Verify old public names do not exist
        self.assertFalse(hasattr(arm_ik_mod, "set_fault_injection_hook"))
        self.assertFalse(hasattr(arm_ik_mod, "clear_fault_injection_hook"))

        # Verify private test functions exist
        self.assertTrue(hasattr(arm_ik_mod, "_set_test_fault_injection_hook"))
        self.assertTrue(hasattr(arm_ik_mod, "_clear_test_fault_injection_hook"))

        # Verify hook is cleared and does not leak
        called = []
        def test_hook(stage: str, ctx: dict) -> None:
            called.append(stage)

        _set_test_fault_injection_hook(test_hook)
        arm_ik_mod._trigger_fault_injection("test_stage_dummy")
        self.assertEqual(called, ["test_stage_dummy"])

        _clear_test_fault_injection_hook()
        arm_ik_mod._trigger_fault_injection("test_stage_dummy_2")
        self.assertEqual(called, ["test_stage_dummy"])

    def test_64_commit_cleanup_failure_and_datablock_lifecycle(self) -> None:
        """TEST-64: Commit cleanup removes orphaned Data Blocks, preserves shared Data Blocks, and reports cleanup errors.

        Note: TEST-64 focuses specifically on data block reference counting and cleanup
        error reporting. Complementary test TEST-66 verifies transaction state transitions
        (COMMITTED / CLEANUP_PENDING) and retry_cleanup() idempotency.
        """
        # 1. Create wrong-type HandIK.L with MESH data block
        mesh_data = bpy.data.meshes.new("DoomedMesh")
        wrong_mesh_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.context.scene.collection.objects.link(wrong_mesh_obj)

        # 2. Create wrong-type ElbowPole.L with CURVE data block that is shared with another object
        curve_data = bpy.data.curves.new("SharedCurve", type="CURVE")
        wrong_curve_obj = bpy.data.objects.new("ElbowPole.L", curve_data)
        bpy.context.scene.collection.objects.link(wrong_curve_obj)

        sharing_obj = bpy.data.objects.new("SharingCurveObj", curve_data)
        bpy.context.scene.collection.objects.link(sharing_obj)

        self.assertGreater(curve_data.users, 1)

        # 3. Successful transaction commit
        setup_arm_ik(self.armature)

        # Doomed mesh data block must be cleaned up, and controller must now be an EMPTY
        self.assertNotIn("DoomedMesh", bpy.data.meshes)
        self.assertEqual(bpy.data.objects["HandIK.L"].type, "EMPTY")

        # Shared curve object replaced with an EMPTY, but shared curve data block preserved!
        self.assertEqual(bpy.data.objects["ElbowPole.L"].type, "EMPTY")
        self.assertIn("SharedCurve", bpy.data.curves)
        self.assertIs(sharing_obj.data, curve_data)

        # 4. Injected commit cleanup failure reports explicit RuntimeError
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Simulated commit cleanup failure")

        _set_test_fault_injection_hook(fault_hook)

        # Add another wrong-type object to trigger commit cleanup
        mesh_data_2 = bpy.data.meshes.new("DoomedMesh2")
        wrong_obj_2 = bpy.data.objects.new("HandIK.R", mesh_data_2)
        bpy.context.scene.collection.objects.link(wrong_obj_2)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Simulated commit cleanup failure", str(cm.exception))

    def test_65_reversible_commit_preparation_failure_rolls_back(self) -> None:
        """TEST-65: Reversible commit preparation failure (Phase 1) rolls back without destroying stashed resources."""
        # 1. Setup initial state with a wrong-type controller to verify it's stashed and restored intact
        mesh_data = bpy.data.meshes.new("TestMesh65")
        mesh_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.context.scene.collection.objects.link(mesh_obj)
        orig_obj_ptr = mesh_obj.as_pointer()
        orig_data_ptr = mesh_data.as_pointer()

        snap_initial = _snapshot_arm_rig_state(self.armature)

        # 2. Inject failure at Phase 1 before_commit_prepare
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "before_commit_prepare":
                raise RuntimeError("Simulated Phase 1 preparation failure")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Simulated Phase 1 preparation failure", str(cm.exception))

        # 3. Assertions
        # Stashed wrong-type object and mesh data block identities must NOT be destroyed
        self.assertIn("HandIK.L", bpy.data.objects)
        restored_obj = bpy.data.objects["HandIK.L"]
        self.assertEqual(restored_obj.as_pointer(), orig_obj_ptr)
        self.assertEqual(restored_obj.type, "MESH")
        self.assertIn("TestMesh65", bpy.data.meshes)
        self.assertEqual(restored_obj.data.as_pointer(), orig_data_ptr)

        # Active transaction stack restored to empty
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Full rig restoration verification passes
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_66_irreversible_cleanup_failure_semantics_and_retry(self) -> None:
        """TEST-66: Irreversible cleanup failure (Phase 3) leaves rig COMMITTED, tracks uncleaned resources, and retries cleanly."""
        # 1. Add a wrong-type object that requires cleanup
        mesh_data = bpy.data.meshes.new("DoomedMesh66")
        wrong_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.context.scene.collection.objects.link(wrong_obj)

        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                captured_tx.append(ctx["tx"])
                raise RuntimeError("Simulated Phase 3 irreversible cleanup failure")

        _set_test_fault_injection_hook(fault_hook)

        # 2. Call setup_arm_ik() -> must raise RuntimeError because cleanup failed
        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Simulated Phase 3 irreversible cleanup failure", str(cm.exception))

        # 3. Verify transaction state and semantics
        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.CLEANUP_PENDING)
        self.assertTrue(tx.committed)
        self.assertIsNotNone(tx.cleanup_error)
        self.assertIn("Simulated Phase 3 irreversible cleanup failure", tx.cleanup_error)

        # Business rig is committed: HandIK.L is now the active EMPTY controller!
        active_controller = bpy.data.objects.get("HandIK.L")
        self.assertIsNotNone(active_controller)
        self.assertEqual(active_controller.type, "EMPTY")
        self.assertNotEqual(active_controller, wrong_obj)

        # Original doomed object is tracked in uncleaned resources
        self.assertGreater(len(tx.uncleaned_stashed_objects), 0)
        stashed_names = [s["original_name"] for s in tx.uncleaned_stashed_objects]
        self.assertIn("HandIK.L", stashed_names)

        # 4. Clear the fault hook and execute idempotent retry
        _clear_test_fault_injection_hook()
        tx.retry_cleanup()

        # After retry, transaction converges to COMMITTED with no cleanup error
        self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)
        self.assertIsNone(tx.cleanup_error)
        self.assertEqual(len(tx.uncleaned_stashed_objects), 0)
        self.assertNotIn("DoomedMesh66", bpy.data.meshes)

        # Second retry is idempotent and harmless
        tx.retry_cleanup()
        self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)

    def test_67_partial_cleanup_failure_and_convergence(self) -> None:
        """TEST-67: Partial cleanup failure prevents duplicate deletions, protects shared resources, and converges on retry."""
        # Setup 2 wrong-type controllers:
        # 1) HandIK.L with exclusive mesh
        mesh_excl = bpy.data.meshes.new("ExclMesh67")
        wrong_l = bpy.data.objects.new("HandIK.L", mesh_excl)
        bpy.context.scene.collection.objects.link(wrong_l)

        # 2) HandIK.R with shared curve
        curve_shared = bpy.data.curves.new("SharedCurve67", type="CURVE")
        wrong_r = bpy.data.objects.new("HandIK.R", curve_shared)
        bpy.context.scene.collection.objects.link(wrong_r)

        other_obj = bpy.data.objects.new("OtherObj67", curve_shared)
        bpy.context.scene.collection.objects.link(other_obj)
        self.assertGreaterEqual(curve_shared.users, 2)

        # Setup 2 wrong-type constraints on forearm.L
        pbone_l = self.armature.pose.bones["forearm.L"]
        stashed_con1 = pbone_l.constraints.new(type="LIMIT_ROTATION")
        stashed_con1.name = "ArmIK.L"
        stashed_con2 = pbone_l.constraints.new(type="TRACK_TO")
        stashed_con2.name = "ArmIK.L_Extra"

        captured_tx = []
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                tx = ctx["tx"]
                captured_tx.append(tx)
                # Simulate partial cleanup: remove wrong_l and mesh_excl manually, then pop from uncleaned_stashed_objects
                for st in list(tx.uncleaned_stashed_objects):
                    if st.get("original_name") == "HandIK.L":
                        obj = st.get("stashed_obj")
                        if obj and obj.name in bpy.data.objects:
                            bpy.data.objects.remove(obj, do_unlink=True)
                        mesh = st.get("stashed_data")
                        if mesh and mesh.name in bpy.data.meshes:
                            bpy.data.meshes.remove(mesh, do_unlink=True)
                        tx.uncleaned_stashed_objects.remove(st)
                        break
                raise RuntimeError("Simulated partial commit cleanup failure")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Simulated partial commit cleanup failure", str(cm.exception))

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.CLEANUP_PENDING)

        # Verify partial cleanup results:
        # wrong_l (exclusive mesh) was cleaned up, wrong_r still pending
        self.assertNotIn("ExclMesh67", bpy.data.meshes)
        self.assertIn("SharedCurve67", bpy.data.curves)
        self.assertIs(other_obj.data, curve_shared)

        # Retry cleanup converges cleanly
        _clear_test_fault_injection_hook()
        tx.retry_cleanup()
        self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)
        self.assertEqual(len(tx.uncleaned_stashed_objects), 0)
        self.assertEqual(len(tx.uncleaned_stashed_constraints), 0)
        self.assertIn("SharedCurve67", bpy.data.curves)
        self.assertEqual(other_obj.data, curve_shared)

    def test_68_depsgraph_update_call_boundary_exception_rollback(self) -> None:
        """TEST-68: Exception at _DEPSGRAPH_UPDATER call boundary propagates and triggers complete atomic rollback."""
        setup_arm_ik(self.armature, initial_influence=0.2)
        snap_initial = _snapshot_arm_rig_state(self.armature)

        # Call boundary failure injection: fail on first call during forward transaction, then succeed during rollback
        call_count = [0]
        def failing_updater():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Depsgraph call boundary crash")
            bpy.context.view_layer.update()

        _set_test_depsgraph_updater(failing_updater)
        try:
            y_pos = self.root.location.y + 0.15
            target_pos = (-0.32, y_pos, 1.20)
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.88)
            self.assertIn("Depsgraph call boundary crash", str(cm.exception))
        finally:
            _clear_test_depsgraph_updater()

        # All writes prior to depsgraph update rolled back atomically
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        _verify_arm_rig_state_restored(self.armature, snap_initial)

    def test_69_snapshot_array_immutability_and_independence(self) -> None:
        """TEST-69: Snapshot arrays are immutable tuples, immune to in-place RNA mutations, and restored properly."""
        from src.rig.arm_ik import _clone_snapshot_property_value
        setup_arm_ik(self.armature, initial_influence=0.5)

        snap = _snapshot_arm_rig_state(self.armature)

        # Assert snapshot stored immutable tuples for array properties (rotation_axis_angle, etc.)
        pbone = self.armature.pose.bones["forearm.L"]
        stored_axis_angle = snap["pose_bones"]["forearm.L"]["rotation_axis_angle"]
        self.assertIsInstance(stored_axis_angle, tuple)

        # Verify _clone_snapshot_property_value creates independent immutable tuple
        raw_list = [10.0, 20.0, 30.0]
        cloned_tuple = _clone_snapshot_property_value(raw_list)
        self.assertIsInstance(cloned_tuple, tuple)
        self.assertEqual(cloned_tuple, (10.0, 20.0, 30.0))
        raw_list[0] = 999.0
        self.assertEqual(cloned_tuple[0], 10.0)

        # In-place mutate pbone rotation_axis_angle RNA array
        orig_angle = pbone.rotation_axis_angle[0]
        pbone.rotation_axis_angle[0] = orig_angle + 1.57
        # Snapshot tuple must remain strictly unaffected
        self.assertEqual(snap["pose_bones"]["forearm.L"]["rotation_axis_angle"][0], stored_axis_angle[0])

        # In-place mutate pbone location Vector and matrix_basis Matrix
        orig_snap_loc = snap["pose_bones"]["forearm.L"]["location"].copy()
        pbone.location.x += 10.0
        self.assertEqual(snap["pose_bones"]["forearm.L"]["location"].x, orig_snap_loc.x)

        # Rollback recovers original values
        _rollback_arm_rig_state(self.armature, snap)
        self.assertAlmostEqual(pbone.rotation_axis_angle[0], orig_angle, places=5)
        self.assertAlmostEqual(pbone.location.x, orig_snap_loc.x, places=5)
        _verify_arm_rig_state_restored(self.armature, snap)

    def test_70_rna_property_restoration_failure_error_aggregation(self) -> None:
        """TEST-70: Failure during constraint property restoration aggregates dual exceptions with exact context."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        # Inject failure on restoration of generic property
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Primary forward transaction error")
            elif stage == "during_constraint_property_restore":
                if ctx.get("bone") == "forearm.L" and ctx.get("con") == "ArmIK.L":
                    raise ValueError("Simulated RNA property write rejection")

        _set_test_fault_injection_hook(fault_hook)

        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.9)

        err_msg = str(cm.exception)
        # Dual exception aggregation: both primary and restoration errors present
        self.assertIn("Primary forward transaction error", err_msg)
        self.assertIn("Simulated RNA property write rejection", err_msg)
        # Detailed context reported: bone, constraint, property
        self.assertIn("forearm.L", err_msg)
        self.assertIn("ArmIK.L", err_msg)

        # Active transaction stack cleaned up
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_71_external_collection_protection_during_rollback(self) -> None:
        """TEST-71: Rollback protects collections created externally during transaction while removing transaction collections."""
        setup_arm_ik(self.armature)
        snap = _snapshot_arm_rig_state(self.armature)

        ext_col_name = "ExternalThirdPartyCol71"
        ext_obj_name = "ExternalObj71"

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                # Simulate external code creating a collection and object concurrently
                ext_col = bpy.data.collections.new(ext_col_name)
                bpy.context.scene.collection.children.link(ext_col)
                ext_obj = bpy.data.objects.new(ext_obj_name, None)
                ext_col.objects.link(ext_obj)
                raise RuntimeError("Crash inside transaction write")

        _set_test_fault_injection_hook(fault_hook)

        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.8)
        self.assertIn("Crash inside transaction write", str(cm.exception))

        # External collection and its object must be strictly protected!
        self.assertIn(ext_col_name, bpy.data.collections)
        self.assertIn(ext_col_name, bpy.context.scene.collection.children)
        ext_col = bpy.data.collections[ext_col_name]
        self.assertIn(ext_obj_name, ext_col.objects)

        # Rig state restored
        _verify_arm_rig_state_restored(self.armature, snap)

        # Clean up external test artifacts
        bpy.data.objects.remove(bpy.data.objects[ext_obj_name], do_unlink=True)
        bpy.context.scene.collection.children.unlink(ext_col)
        bpy.data.collections.remove(ext_col)

    def test_72_collection_rename_and_multi_parent_restoration(self) -> None:
        """TEST-72: Character collection with multiple parents, renamed or reparented in transaction, is restored 100%."""
        char_col = bpy.data.collections["Character"]

        parent_col2 = bpy.data.collections.new("ParentCol2_72")
        bpy.context.scene.collection.children.link(parent_col2)
        parent_col2.children.link(char_col)

        parent_col3 = bpy.data.collections.new("ParentCol3_72")
        bpy.context.scene.collection.children.link(parent_col3)

        char_col_ptr = char_col.as_pointer()
        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                # Alter parents and rename Character collection
                c = bpy.data.collections.get("Character")
                if c is not None:
                    if c.name in parent_col2.children:
                        parent_col2.children.unlink(c)
                    parent_col3.children.link(c)
                    c.name = "Character_Mutated72"
                raise RuntimeError("Fault during transaction")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault during transaction", str(cm.exception))

        # Verify restoration:
        # 1. Collection name is Character and pointer unchanged
        self.assertIn("Character", bpy.data.collections)
        restored_char = bpy.data.collections["Character"]
        self.assertEqual(restored_char.as_pointer(), char_col_ptr)

        # 2. Both original parents restored: scene.collection and parent_col2
        self.assertIn("Character", bpy.context.scene.collection.children)
        self.assertIn("Character", parent_col2.children)
        self.assertNotIn("Character", parent_col3.children)

        # Clean up additional collections
        bpy.context.scene.collection.children.unlink(parent_col2)
        bpy.data.collections.remove(parent_col2)
        bpy.context.scene.collection.children.unlink(parent_col3)
        bpy.data.collections.remove(parent_col3)

    def test_73_stashed_constraint_identity_and_ordering(self) -> None:
        """TEST-73: Stashed wrong-type constraints and unrelated custom constraints preserve identities and order on rollback."""
        pbone = self.armature.pose.bones["forearm.L"]

        con1 = pbone.constraints.new(type="COPY_LOCATION")
        con1.name = "MyCustomLoc73"
        con1.influence = 0.72
        con1.mute = False
        con1_ptr = con1.as_pointer()

        con2 = pbone.constraints.new(type="LIMIT_ROTATION")
        con2.name = "ArmIK.L"  # Wrong-type constraint with target name
        con2.influence = 0.55
        con2.mute = True
        con2_ptr = con2.as_pointer()

        con3 = pbone.constraints.new(type="TRACK_TO")
        con3.name = "MyCustomTrack73"
        con3.influence = 0.41
        con3.mute = True
        con3_ptr = con3.as_pointer()

        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend":
                raise RuntimeError("Fault after constraints setup")

        _set_test_fault_injection_hook(fault_hook)

        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault after constraints setup", str(cm.exception))

        # Check constraint count, names, identities, ordering, and properties
        self.assertEqual(len(pbone.constraints), 3)
        names = [c.name for c in pbone.constraints]
        self.assertEqual(names, ["MyCustomLoc73", "ArmIK.L", "MyCustomTrack73"])

        self.assertEqual(pbone.constraints[0].as_pointer(), con1_ptr)
        self.assertEqual(pbone.constraints[1].as_pointer(), con2_ptr)
        self.assertEqual(pbone.constraints[2].as_pointer(), con3_ptr)

        self.assertEqual(pbone.constraints[1].type, "LIMIT_ROTATION")
        self.assertTrue(pbone.constraints[1].mute)
        self.assertAlmostEqual(pbone.constraints[1].influence, 0.55, places=5)

        _verify_arm_rig_state_restored(self.armature, snap)

    def test_74_sequential_failures_and_subsequent_success_avalanche_protection(self) -> None:
        """TEST-74: Sequential snapshot failure -> write failure -> clean rollback -> normal setup -> idempotent re-run."""
        # 1. Snapshot failure
        def fault_snapshot(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                raise RuntimeError("Fault in snapshot stage")

        _set_test_fault_injection_hook(fault_snapshot)
        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault in snapshot stage", str(cm.exception))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # 2. Write failure
        def fault_write(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                raise RuntimeError("Fault in write stage")

        _set_test_fault_injection_hook(fault_write)
        with self.assertRaises(RuntimeError) as cm:
            setup_arm_ik(self.armature)
        self.assertIn("Fault in write stage", str(cm.exception))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # 3. Clear hook and run normal setup_arm_ik()
        _clear_test_fault_injection_hook()
        setup_arm_ik(self.armature, initial_influence=0.7)

        # Verify rig is properly setup
        for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            self.assertIn(c_name, bpy.data.objects)
            self.assertEqual(bpy.data.objects[c_name].type, "EMPTY")

        snap_valid = _snapshot_arm_rig_state(self.armature)

        # 4. Idempotent re-run
        setup_arm_ik(self.armature, initial_influence=0.7)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        _verify_arm_rig_state_restored(self.armature, snap_valid)

    def test_75_side_isolation_and_shared_resource_protection(self) -> None:
        """TEST-75: Failure on L side set_hand_ik_target isolates R side completely and protects shared datablock."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        # Create shared curve datablock referenced by R side custom object
        shared_curve = bpy.data.curves.new("SharedCurve75", type="CURVE")
        user1 = bpy.data.objects.new("CurveUser1_75", shared_curve)
        user2 = bpy.data.objects.new("CurveUser2_75", shared_curve)
        bpy.context.scene.collection.objects.link(user1)
        bpy.context.scene.collection.objects.link(user2)
        initial_users = shared_curve.users
        self.assertGreaterEqual(initial_users, 2)

        # Assign custom property to R controller
        bpy.data.objects["HandIK.R"]["r_tag"] = "SideR_Value"
        r_loc_before = bpy.data.objects["HandIK.R"].location.copy()
        r_con_influence = self.armature.pose.bones["forearm.R"].constraints["ArmIK.R"].influence

        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault during L hand target write")

        _set_test_fault_injection_hook(fault_hook)

        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        with self.assertRaises(RuntimeError) as cm:
            set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.95)
        self.assertIn("Fault during L hand target write", str(cm.exception))

        # 1. R side is 100% untouched
        self.assertEqual(bpy.data.objects["HandIK.R"]["r_tag"], "SideR_Value")
        self.assertEqual(bpy.data.objects["HandIK.R"].location, r_loc_before)
        self.assertEqual(self.armature.pose.bones["forearm.R"].constraints["ArmIK.R"].influence, r_con_influence)

        # 2. Shared curve datablock is intact with users count preserved
        self.assertIn("SharedCurve75", bpy.data.curves)
        self.assertEqual(shared_curve.users, initial_users)

        # 3. Overall rig restored to snapshot
        _verify_arm_rig_state_restored(self.armature, snap_initial)

        # Clean up test objects
        bpy.data.objects.remove(user1, do_unlink=True)
        bpy.data.objects.remove(user2, do_unlink=True)
        bpy.data.curves.remove(shared_curve, do_unlink=True)

    def test_76_validator_corruption_detection(self) -> None:
        """TEST-76: Verifier captures 6 distinct corruption dimensions with exact field names without mutating scene."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        snap = _snapshot_arm_rig_state(self.armature)

        # Baseline: verifier must pass initially
        _verify_arm_rig_state_restored(self.armature, snap)

        # Dimension 1: Controller object identity pointer mismatch
        old_c = bpy.data.objects["HandIK.L"]
        old_c.name = "HandIK.L_temp_76"
        new_c = bpy.data.objects.new("HandIK.L", None)
        bpy.context.scene.collection.objects.link(new_c)
        with self.assertRaises((RuntimeError, AssertionError)) as cm1:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("identity mismatch", str(cm1.exception))
        # Restore old object for next checks
        bpy.data.objects.remove(new_c, do_unlink=True)
        old_c.name = "HandIK.L"
        _verify_arm_rig_state_restored(self.armature, snap)

        # Dimension 2: Constraint property difference
        snap_corrupt = _snapshot_arm_rig_state(self.armature)
        snap_corrupt["pose_bones"]["forearm.L"]["constraints"][0]["pole_angle"] += 0.005  # diff > 1e-5
        with self.assertRaises((RuntimeError, AssertionError)) as cm2:
            _verify_arm_rig_state_restored(self.armature, snap_corrupt)
        self.assertIn("pole_angle", str(cm2.exception))
        _verify_arm_rig_state_restored(self.armature, snap)

        # Dimension 3: Constraint ordering reversed
        pbone = self.armature.pose.bones["forearm.L"]
        extra_con = pbone.constraints.new(type="COPY_ROTATION")
        extra_con.name = "ExtraCon76"
        snap_order = _snapshot_arm_rig_state(self.armature)
        pbone.constraints.move(1, 0)  # swap order
        with self.assertRaises((RuntimeError, AssertionError)) as cm3:
            _verify_arm_rig_state_restored(self.armature, snap_order)
        self.assertIn("constraint", str(cm3.exception))
        pbone.constraints.remove(extra_con)
        _rollback_arm_rig_state(self.armature, snap)
        _verify_arm_rig_state_restored(self.armature, snap)

        # Dimension 4: Character collection link unlinked
        char_col = bpy.data.collections["Character"]
        bpy.context.scene.collection.children.unlink(char_col)
        with self.assertRaises((RuntimeError, AssertionError)) as cm4:
            _verify_arm_rig_state_restored(self.armature, snap)
        self.assertIn("Character collection", str(cm4.exception))
        bpy.context.scene.collection.children.link(char_col)
        _verify_arm_rig_state_restored(self.armature, snap)

        # Dimension 5: DataBlock identity change
        # Corrupt data_ref expectation in snapshot
        snap_data_corrupt = _snapshot_arm_rig_state(self.armature)
        snap_data_corrupt["controllers"]["HandIK.L"]["data_ref"] = 999999999
        with self.assertRaises((RuntimeError, AssertionError)) as cm5:
            _verify_arm_rig_state_restored(self.armature, snap_data_corrupt)
        self.assertIn("data_ref identity mismatch", str(cm5.exception))

        # Dimension 6: Active transaction stack violation
        _ACTIVE_TRANSACTION_STACK.append("dummy_tx")
        try:
            with self.assertRaises((RuntimeError, AssertionError)) as cm6:
                _verify_arm_rig_state_restored(self.armature, snap)
            self.assertIn("Active transaction stack", str(cm6.exception))
        finally:
            _ACTIVE_TRANSACTION_STACK.pop()

        # Final check: verifier leaves rig 100% clean and passing
        _verify_arm_rig_state_restored(self.armature, snap)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], "-v"])
