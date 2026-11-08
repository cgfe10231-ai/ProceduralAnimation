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
import json
import os
import sys
import unittest
from typing import Any, Dict, List, Optional

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
    ArmatureSessionIdentityRecord,
    _ACTIVE_TRANSACTION_STACK,
    _ARCHIVED_FAILED_D_TOMBSTONES,
    _ArmatureIsolationState,
    _ArmatureLivenessStatus,
    _ArmRigTransactionContext,
    _ArmRigTransactionState,
    _COORDINATOR_AUTHORIZATION_GRANTS,
    _DEISOLATION_AUDIT_LOG,
    _FAILED_A_AUDIT_RECORDS,
    _FailedTransactionClass,
    _ISOLATED_FAILED_ARMATURES,
    _MANAGED_ARMATURE_IDENTITIES,
    _PENDING_ARM_RIG_CLEANUPS,
    _RelationshipOperationState,
    _arm_rig_transaction,
    _assert_arm_rig_cleanup_gate,
    _assert_arm_rig_failed_isolation_gate,
    _authorized_link_object_to_collection,
    _check_original_object_liveness,
    _clear_coordinator_authorization_grants,
    _clear_or_retire_failure_isolation_by_coordinator,
    _clear_test_depsgraph_updater,
    _clear_test_fault_injection_hook,
    _depsgraph_update,
    _issue_coordinator_authorization_grant,
    _rollback_arm_rig_state,
    _set_test_depsgraph_updater,
    _set_test_fault_injection_hook,
    _snapshot_arm_rig_state,
    _verify_arm_rig_state_restored,
    _verify_armature_session_identity_record,
    ensure_armature_session_identity,
    get_arm_ik_state,
    get_pending_arm_rig_cleanup_ids,
    query_admission_gate_status,
    request_armature_deisolation,
    reset_arm_ik,
    retire_dead_armature_tombstone,
    retry_pending_arm_rig_cleanup,
    set_arm_ik_influence,
    set_hand_ik_target,
    setup_arm_ik,
    verify_armature_deisolation_evidence,
)
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose

_TEST_137_TO_149_RUNTIME_EVIDENCE: Dict[str, Dict[str, Any]] = {}


class TestArmIKTransactionAtomicity(unittest.TestCase):
    """Test suite verifying Arm IK transaction snapshot, atomic rollback, and fault resilience."""

    def setUp(self) -> None:
        """Reset Blender state, clear hooks, and build fresh character rig."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _clear_test_fault_injection_hook()
        _clear_test_depsgraph_updater()
        # Test fixture isolation only across read_factory_settings resets (not a production recovery mechanism)
        _PENDING_ARM_RIG_CLEANUPS.clear()
        _ISOLATED_FAILED_ARMATURES.clear()
        _MANAGED_ARMATURE_IDENTITIES.clear()
        _ARCHIVED_FAILED_D_TOMBSTONES.clear()
        _FAILED_A_AUDIT_RECORDS.clear()
        _DEISOLATION_AUDIT_LOG.clear()
        _clear_coordinator_authorization_grants()
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
        """Ensure fault injection hooks, depsgraph updaters, and test fixture registries are cleared."""
        _clear_test_fault_injection_hook()
        _clear_test_depsgraph_updater()
        _PENDING_ARM_RIG_CLEANUPS.clear()
        _ISOLATED_FAILED_ARMATURES.clear()
        _MANAGED_ARMATURE_IDENTITIES.clear()
        _ARCHIVED_FAILED_D_TOMBSTONES.clear()
        _FAILED_A_AUDIT_RECORDS.clear()
        _DEISOLATION_AUDIT_LOG.clear()
        _clear_coordinator_authorization_grants()

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

        # Create controllers and constraints under transaction
        with self.assertRaises(RuntimeError):
            with _arm_rig_transaction(self.armature):
                setup_arm_ik(self.armature, initial_influence=0.5)
                for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
                    self.assertIn(c_name, bpy.data.objects)
                self.assertIn("Character", bpy.data.collections)
                raise RuntimeError("Trigger rollback of uninitialized scene")

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
        """
        TEST-38:
        Restore original constraint identity, order,
        properties and remove transaction-added constraints.

        Physical destruction of an original constraint
        is covered separately by TEST-77 and TEST-78.
        """

        setup_arm_ik(
            self.armature,
            initial_influence=0.4,
        )

        snap = _snapshot_arm_rig_state(self.armature)

        p_fore = self.armature.pose.bones["forearm.L"]

        original = p_fore.constraints["ArmIK.L"]
        original_ptr = original.as_pointer()

        original_mute = original.mute
        original_influence = original.influence

        # Mutate the original constraint without destroying it.
        original.influence = 0.9
        original.mute = not original_mute

        # Add an extraneous constraint.
        extra = p_fore.constraints.new(type="TRACK_TO")
        extra.name = "ExtraTrack_TEST38"

        # Move the extra constraint before the original.
        extra_idx = list(p_fore.constraints).index(extra)
        p_fore.constraints.move(extra_idx, 0)

        bpy.context.view_layer.update()

        # Confirm the test actually changed the scene.
        self.assertEqual(
            p_fore.constraints[0].name,
            "ExtraTrack_TEST38",
        )

        self.assertAlmostEqual(
            original.influence,
            0.9,
            places=5,
        )

        # Register extra constraint as transaction-created on mock transaction context
        tx = _ArmRigTransactionContext(self.armature)
        tx.snapshot = snap
        tx.register_created_constraint(p_fore, extra)

        _ACTIVE_TRANSACTION_STACK.append(tx)
        try:
            # Execute rollback.
            _rollback_arm_rig_state(
                self.armature,
                snap,
                active_tx=tx,
            )

            _verify_arm_rig_state_restored(
                self.armature,
                snap,
                active_tx=tx,
            )
        finally:
            _ACTIVE_TRANSACTION_STACK.pop()

        # Original assertions: count, name, type, influence.
        self.assertEqual(
            len(p_fore.constraints),
            1,
        )

        restored = p_fore.constraints[0]

        self.assertEqual(
            restored.name,
            "ArmIK.L",
        )

        self.assertEqual(
            restored.type,
            "IK",
        )

        self.assertAlmostEqual(
            restored.influence,
            0.4,
            places=5,
        )

        # Additional strict identity assertions.
        self.assertEqual(
            restored.as_pointer(),
            original_ptr,
        )

        self.assertAlmostEqual(
            restored.influence,
            original_influence,
            places=5,
        )

        self.assertEqual(
            restored.mute,
            original_mute,
        )

        self.assertNotIn(
            "ExtraTrack_TEST38",
            [c.name for c in p_fore.constraints],
        )

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

        original_location = (
            bpy.data.objects["HandIK.L"]
            .location.copy()
        )

        original_update = bpy.context.view_layer.update
        call_count = [0]
        write_observed = [False]

        def failing_updater():
            call_count[0] += 1

            # Call 1: Phase B preflight
            # Call 2: Snapshot creation
            # Call 3: After transaction has written state
            if call_count[0] == 3:
                ctrl = bpy.data.objects.get("HandIK.L")

                if ctrl is None:
                    raise AssertionError(
                        "TEST-68: HandIK.L missing at post-write update"
                    )

                location_after_write = ctrl.location.copy()

                location_difference = (
                    location_after_write - original_location
                ).length

                if location_difference <= 1e-5:
                    raise AssertionError(
                        "TEST-68: post-write update reached "
                        "without actual controller mutation; "
                        f"location_difference={location_difference}"
                    )

                write_observed[0] = True

                raise RuntimeError(
                    "TEST-68 dependency graph post-write failure"
                )

            original_update()

        _set_test_depsgraph_updater(failing_updater)
        try:
            y_pos = self.root.location.y + 0.15
            target_pos = (-0.32, y_pos, 1.20)
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.88)
            self.assertIn("TEST-68 dependency graph post-write failure", str(cm.exception))
        finally:
            _clear_test_depsgraph_updater()

        # Assert post-write failure occurred
        self.assertTrue(write_observed[0])
        self.assertGreaterEqual(call_count[0], 3)

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
        # 3. External addition parent_col3 link is preserved on rollback (Task 10-B-7 ownership isolation)
        self.assertIn("Character", parent_col3.children)

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

    # -------------------------------------------------------------------------
    # Task 10-B-6 Extended Tests (TEST-77 to TEST-84)
    # -------------------------------------------------------------------------

    def test_77_destroyed_constraint_identity_is_rejected(self) -> None:
        """TEST-77: Verifier explicitly rejects substitute constraint after original constraint destruction."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        snap = _snapshot_arm_rig_state(self.armature)

        p_fore = self.armature.pose.bones["forearm.L"]
        orig_con = p_fore.constraints["ArmIK.L"]
        orig_ptr = orig_con.as_pointer()

        # Destroy original constraint
        p_fore.constraints.remove(orig_con)

        # Allocate a temporary dummy to prevent allocator from reusing the same heap block
        dummy = p_fore.constraints.new(type="LIMIT_ROTATION")
        substitute = p_fore.constraints.new(type="IK")
        p_fore.constraints.remove(dummy)
        substitute.name = "ArmIK.L"
        substitute.influence = 0.5
        substitute.target = bpy.data.objects["HandIK.L"]
        substitute.pole_target = bpy.data.objects["ElbowPole.L"]
        substitute.chain_count = 2

        bpy.context.view_layer.update()

        # Substitute must have a different pointer
        self.assertNotEqual(substitute.as_pointer(), orig_ptr)

        # Verifier MUST reject the substitute constraint
        with self.assertRaises(RuntimeError) as cm:
            _verify_arm_rig_state_restored(self.armature, snap)

        err_msg = str(cm.exception)
        self.assertTrue(
            "identity mismatch" in err_msg or "original constraint destroyed" in err_msg or "identity pointer mismatch" in err_msg,
            f"Expected identity rejection in error message: {err_msg}",
        )

    def test_78_destroyed_constraint_causes_rollback_failure(self) -> None:
        """TEST-78: Destruction of original constraint during transaction causes rollback to report identity failure."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        p_fore = self.armature.pose.bones["forearm.L"]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                if "ArmIK.L" in p_fore.constraints:
                    p_fore.constraints.remove(p_fore.constraints["ArmIK.L"])
                raise RuntimeError("Primary transaction business fault")

        _set_test_fault_injection_hook(fault_hook)
        try:
            y_pos = self.root.location.y + 0.15
            target_pos = (-0.32, y_pos, 1.20)
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=target_pos, influence=0.8)

            err_msg = str(cm.exception)
            self.assertIn("Primary transaction business fault", err_msg)
            self.assertTrue(
                "Original constraint" in err_msg or "constraint" in err_msg or "rollback" in err_msg,
                f"Expected constraint restoration failure in: {err_msg}",
            )
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        finally:
            _clear_test_fault_injection_hook()

    def test_79_external_character_collection_creation_preserved(self) -> None:
        """TEST-79: External Character collection created during transaction is preserved on rollback."""
        # 1. Ensure initial scene does not have Character collection
        char_col = bpy.data.collections.get("Character")
        if char_col is not None:
            for parent in list(bpy.data.collections):
                if char_col.name in parent.children:
                    parent.children.unlink(char_col)
            for scene in list(bpy.data.scenes):
                if char_col.name in scene.collection.children:
                    scene.collection.children.unlink(char_col)
            bpy.data.collections.remove(char_col)

        self.assertNotIn("Character", bpy.data.collections)

        external_col = [None]
        external_ptr = [None]
        owned_col_ptr = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage != "setup_arm_ik_after_first_controller":
                return

            owned = bpy.data.collections.get("Character")
            if owned is None:
                raise AssertionError(
                    "TEST-79: transaction did not create Character"
                )

            owned_col_ptr[0] = owned.as_pointer()

            # Release the original name without destroying
            # the transaction-owned collection.
            owned.name = "Character_TX_79"

            # External code now creates a different Collection
            # with the original name.
            ext = bpy.data.collections.new("Character")
            bpy.context.scene.collection.children.link(ext)

            external_col[0] = ext
            external_ptr[0] = ext.as_pointer()

            if external_ptr[0] == owned_col_ptr[0]:
                raise AssertionError(
                    "TEST-79: external and transaction-owned "
                    "collections unexpectedly share identity"
                )

            raise RuntimeError(
                "TEST-79 injected rollback failure"
            )

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("TEST-79 injected rollback failure", str(cm.exception))

            # Required assertions (Task 10-B-7 Section 6.2)
            self.assertIsNotNone(external_col[0])
            self.assertIn("Character", bpy.data.collections)
            self.assertEqual(
                bpy.data.collections["Character"].as_pointer(),
                external_ptr[0],
            )

            # 1. Transaction-owned original collection is cleaned up
            self.assertNotIn("Character_TX_79", bpy.data.collections)
            self.assertFalse(
                any(c.as_pointer() == owned_col_ptr[0] for c in bpy.data.collections)
            )

            # 2. External Collection's parent link is preserved
            self.assertIn("Character", bpy.context.scene.collection.children)
            self.assertEqual(
                bpy.context.scene.collection.children["Character"].as_pointer(),
                external_ptr[0],
            )

            # 3. Active transaction stack is empty
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

            # 4. No lingering transaction controllers
            for c_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
                self.assertNotIn(c_name, bpy.data.objects)

        finally:
            _clear_test_fault_injection_hook()
            for c_name in ("Character_TX_79", "Character"):
                c = bpy.data.collections.get(c_name)
                if c is not None:
                    for parent in list(bpy.data.collections):
                        if c.name in parent.children:
                            parent.children.unlink(c)
                    for scene in list(bpy.data.scenes):
                        if c.name in scene.collection.children:
                            scene.collection.children.unlink(c)
                    bpy.data.collections.remove(c)

    def test_80_external_character_collection_members_preserved(self) -> None:
        """TEST-80: External object members added to Character collection during transaction are preserved on rollback."""
        setup_arm_ik(self.armature)
        char_col = bpy.data.collections["Character"]
        original_member_ptrs = {o.as_pointer() for o in char_col.objects}

        external_obj = [None]
        external_ptr = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                ext_mesh = bpy.data.meshes.new("ExternalPropMesh80")
                ext_o = bpy.data.objects.new("ExternalProp80", ext_mesh)
                char_col.objects.link(ext_o)
                external_obj[0] = ext_o
                external_ptr[0] = ext_o.as_pointer()
                raise RuntimeError("Fault injected after external member linked")

        _set_test_fault_injection_hook(fault_hook)
        try:
            y_pos = self.root.location.y + 0.15
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))

            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
            current_member_ptrs = {o.as_pointer() for o in char_col.objects}
            for optr in original_member_ptrs:
                self.assertIn(optr, current_member_ptrs)

            self.assertIn(external_ptr[0], current_member_ptrs)
            self.assertIn("ExternalProp80", char_col.objects)
        finally:
            _clear_test_fault_injection_hook()

    def test_81_cleanup_pending_registry_and_retry(self) -> None:
        """TEST-81: Phase 3 cleanup failure registers pending cleanup; queryable and retriable without test callbacks."""
        wrong_mesh = bpy.data.meshes.new("DoomedMesh81")
        wrong_obj = bpy.data.objects.new("HandIK.L", wrong_mesh)
        bpy.data.collections["Character"].objects.link(wrong_obj)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Simulated Phase 3 irreversible cleanup crash")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)

            self.assertIn("irreversible cleanup failed", str(cm.exception))

            pending_ids = get_pending_arm_rig_cleanup_ids()
            self.assertGreaterEqual(len(pending_ids), 1)

            target_tx_id = pending_ids[0]
            _clear_test_fault_injection_hook()

            retry_pending_arm_rig_cleanup(target_tx_id)
            self.assertNotIn(target_tx_id, get_pending_arm_rig_cleanup_ids())
        finally:
            _clear_test_fault_injection_hook()

    def test_82_partial_cleanup_object_removed_datablock_failure_and_retry(self) -> None:
        """TEST-82: Object removed but datablock removal fails; pending state retained and retried without RNA error."""
        exclusive_mesh = bpy.data.meshes.new("ExclusiveMesh82")
        exclusive_mesh_ptr = exclusive_mesh.as_pointer()
        wrong_obj = bpy.data.objects.new("HandIK.L", exclusive_mesh)
        wrong_obj_ptr = wrong_obj.as_pointer()
        bpy.data.collections["Character"].objects.link(wrong_obj)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_cleanup_datablock_removal":
                raise RuntimeError("Injected datablock cleanup failure after object removal")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                setup_arm_ik(self.armature)

            pending_ids = get_pending_arm_rig_cleanup_ids()
            self.assertGreaterEqual(len(pending_ids), 1)
            target_id = pending_ids[0]

            obj_still_alive = any(o.as_pointer() == wrong_obj_ptr for o in bpy.data.objects)
            self.assertFalse(obj_still_alive, "Object should have been removed before datablock stage")

            mesh_still_alive = any(m.as_pointer() == exclusive_mesh_ptr for m in bpy.data.meshes)
            self.assertTrue(mesh_still_alive, "Mesh datablock should remain pending cleanup")

            _clear_test_fault_injection_hook()
            retry_pending_arm_rig_cleanup(target_id)

            mesh_alive_after_retry = any(m.as_pointer() == exclusive_mesh_ptr for m in bpy.data.meshes)
            self.assertFalse(mesh_alive_after_retry, "Mesh datablock should be cleaned up on retry")

            self.assertNotIn(target_id, get_pending_arm_rig_cleanup_ids())
        finally:
            _clear_test_fault_injection_hook()

    def test_83_datablock_shared_users_and_same_name_replacement_preserved(self) -> None:
        """TEST-83: Shared datablock with users > 0 and same-name different-identity resources are preserved."""
        shared_mesh = bpy.data.meshes.new("SharedPropMesh83")
        shared_mesh_ptr = shared_mesh.as_pointer()

        wrong_obj = bpy.data.objects.new("HandIK.L", shared_mesh)
        bpy.data.collections["Character"].objects.link(wrong_obj)

        external_user = bpy.data.objects.new("ExternalBackgroundObj83", shared_mesh)
        bpy.context.scene.collection.objects.link(external_user)

        self.assertGreater(shared_mesh.users, 1)

        setup_arm_ik(self.armature)

        self.assertIn("SharedPropMesh83", bpy.data.meshes)
        self.assertEqual(bpy.data.meshes["SharedPropMesh83"].as_pointer(), shared_mesh_ptr)
        self.assertEqual(bpy.data.meshes["SharedPropMesh83"].users, 1)

        new_mesh = bpy.data.meshes.new("SharedPropMesh83")
        self.assertNotEqual(new_mesh.as_pointer(), shared_mesh_ptr)

        y_pos = self.root.location.y + 0.15
        state = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
        self.assertIsNotNone(state)
        self.assertTrue(any(m.as_pointer() == shared_mesh_ptr for m in bpy.data.meshes))
        self.assertTrue(any(m.as_pointer() == new_mesh.as_pointer() for m in bpy.data.meshes))

        bpy.data.objects.remove(external_user, do_unlink=True)
        bpy.data.meshes.remove(shared_mesh, do_unlink=True)
        bpy.data.meshes.remove(new_mesh, do_unlink=True)

    def test_84_sequential_transactions_failure_recovery_isolation(self) -> None:
        """TEST-84: Sequential transaction failure and recovery proves snapshot isolation, no leaks, and clean re-entry."""
        snap1 = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Injected failure in TX 1")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        target1 = (-0.32, y_pos, 1.20)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=target1)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        _verify_arm_rig_state_restored(self.armature, snap1)

        target2 = (0.32, y_pos, 1.20)
        state2 = set_hand_ik_target(self.armature, side="R", world_xyz=target2, influence=0.95)
        self.assertIsNotNone(state2)
        self.assertTrue(state2["is_reachable"])

        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        target3 = (-0.28, y_pos, 1.15)
        state3 = set_hand_ik_target(self.armature, side="L", world_xyz=target3, influence=0.85)
        self.assertIsNotNone(state3)
        self.assertTrue(state3["is_reachable"])
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        snap_final = _snapshot_arm_rig_state(self.armature)
        _verify_arm_rig_state_restored(self.armature, snap_final)

    def test_85_same_armature_cleanup_pending_blocks_new_transaction(self) -> None:
        """TEST-85: Reject new independent writes while same Armature owns an unresolved committed cleanup."""
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Injected cleanup failure for TEST-85")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Injected cleanup failure for TEST-85", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Confirm that Cleanup Pending is registered on this armature
        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertGreater(len(pending_ids), 0)

        # Now attempt to initiate a new independent write on the SAME armature
        with self.assertRaises(RuntimeError) as cm_block:
            setup_arm_ik(self.armature)
        self.assertIn("Arm IK write blocked: unresolved cleanup for the same Armature", str(cm_block.exception))

        # Also verify set_hand_ik_target is blocked
        y_pos = self.root.location.y + 0.15
        with self.assertRaises(RuntimeError) as cm_block2:
            set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
        self.assertIn("Arm IK write blocked: unresolved cleanup for the same Armature", str(cm_block2.exception))

        # Prove blocking occurred before any transaction mutation (active stack depth 0)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_86_unrelated_armature_not_blocked_by_pending_cleanup(self) -> None:
        """TEST-86: Unresolved cleanup on Armature A does not block independent writes on Armature B."""
        setup_arm_ik(self.armature)

        # Manually register a mock Cleanup Pending transaction on Armature A
        tx_a = _ArmRigTransactionContext(self.armature)
        tx_a.state = _ArmRigTransactionState.CLEANUP_PENDING
        tx_a.uncleaned_stashed_objects.append({"obj_cleaned": False, "original_name": "Mock86"})
        _PENDING_ARM_RIG_CLEANUPS[tx_a.tx_id] = tx_a

        # Create independent Armature B
        arm_b_data = bpy.data.armatures.new("ArmBData_86")
        arm_b = bpy.data.objects.new("ArmatureB_86", arm_b_data)
        bpy.context.scene.collection.objects.link(arm_b)

        # Armature B should NOT be blocked
        try:
            with _arm_rig_transaction(arm_b) as tx_b:
                self.assertIsNotNone(tx_b)
                self.assertEqual(tx_b.arm, arm_b)
                self.assertEqual(tx_b.state, _ArmRigTransactionState.ACTIVE)
        finally:
            bpy.data.objects.remove(arm_b, do_unlink=True)
            bpy.data.armatures.remove(arm_b_data, do_unlink=True)
            _PENDING_ARM_RIG_CLEANUPS.clear()

    def test_87_pending_cleanup_retry_success_restores_write_admission(self) -> None:
        """TEST-87: Retrying pending cleanup to completion clears registry and allows new write transactions."""
        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Injected cleanup failure for TEST-87")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Injected cleanup failure for TEST-87", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertEqual(len(pending_ids), 1)
        tx_id = pending_ids[0]

        # Verify admission is blocked
        with self.assertRaises(RuntimeError) as cm_block:
            setup_arm_ik(self.armature)
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_block.exception))

        # Retry pending cleanup without fault injection -> should succeed and unregister
        retry_pending_arm_rig_cleanup(tx_id)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        # Now public write API should succeed cleanly
        y_pos = self.root.location.y + 0.15
        state = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
        self.assertIsNotNone(state)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_88_stashed_constraint_same_name_replacement_not_erroneously_deleted(self) -> None:
        """TEST-88: Stashed constraint cleanup matches by pointer identity and does not remove same-name substitute."""
        setup_arm_ik(self.armature)
        p_fore = self.armature.pose.bones["forearm.L"]
        original_con = p_fore.constraints["ArmIK.L"]
        original_ptr = original_con.as_pointer()

        # Create a transaction context and register a stashed constraint with an obsolete pointer
        tx = _ArmRigTransactionContext(self.armature)
        obsolete_ptr = original_ptr + 999999  # distinct pointer
        stashed_record = {
            "pbone": p_fore,
            "con_ptr": obsolete_ptr,
            "orig_name": "ArmIK.L",
        }
        tx.uncleaned_stashed_constraints.append(stashed_record)

        # Execute retry_cleanup()
        tx.retry_cleanup()

        # The live ArmIK.L constraint must NOT have been removed because pointers differ
        self.assertIn("ArmIK.L", p_fore.constraints)
        self.assertEqual(p_fore.constraints["ArmIK.L"].as_pointer(), original_ptr)
        # The uncleaned list should have removed the record since target was absent
        self.assertEqual(len(tx.uncleaned_stashed_constraints), 0)

    def test_89_original_character_collection_rename_restores_identity_and_name(self) -> None:
        """TEST-89: Character collection renamed during transaction is restored by identity and name without phantom."""
        char_col = bpy.data.collections.get("Character")
        if char_col is None:
            char_col = bpy.data.collections.new("Character")
            bpy.context.scene.collection.children.link(char_col)

        orig_ptr = char_col.as_pointer()
        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                c = bpy.data.collections.get("Character")
                if c is not None:
                    c.name = "Character_Renamed_89"
                raise RuntimeError("Inject fault for TEST-89")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Inject fault for TEST-89", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Assertions
        self.assertIn("Character", bpy.data.collections)
        self.assertNotIn("Character_Renamed_89", bpy.data.collections)
        self.assertEqual(bpy.data.collections["Character"].as_pointer(), orig_ptr)
        self.assertIn("Character", bpy.context.scene.collection.children)
        self.assertEqual(
            len([c for c in bpy.data.collections if c.name == "Character"]),
            1,
        )
        _verify_arm_rig_state_restored(self.armature, snap)

    def test_90_original_parent_collection_rename_restored_by_identity(self) -> None:
        """TEST-90: Parent collection renamed during transaction is restored by identity reference without relying on name."""
        char_col = bpy.data.collections["Character"]
        p_col = bpy.data.collections.new("ParentCol_90")
        bpy.context.scene.collection.children.link(p_col)
        p_col.children.link(char_col)

        p_col_ptr = p_col.as_pointer()
        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                p = bpy.data.collections.get("ParentCol_90")
                if p is not None:
                    p.name = "ParentCol_90_Renamed"
                    c = bpy.data.collections.get("Character")
                    if c is not None and any(child.as_pointer() == c.as_pointer() for child in p.children):
                        p.children.unlink(c)
                raise RuntimeError("Inject fault for TEST-90")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Inject fault for TEST-90", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Verification: link restored to p_col even though p_col is renamed!
        self.assertTrue(
            any(child.as_pointer() == char_col.as_pointer() for child in p_col.children)
        )
        self.assertEqual(p_col.as_pointer(), p_col_ptr)

        # Cleanup
        bpy.context.scene.collection.children.unlink(p_col)
        bpy.data.collections.remove(p_col)

    def test_91_external_child_collection_preserved_on_rollback(self) -> None:
        """TEST-91: External child collection added to Character collection during transaction is preserved on rollback."""
        setup_arm_ik(self.armature)
        char_col = bpy.data.collections["Character"]
        initial_child = bpy.data.collections.new("Initial_Child_91")
        char_col.children.link(initial_child)

        snap = _snapshot_arm_rig_state(self.armature)

        external_child = [None]
        external_child_ptr = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                ext_child = bpy.data.collections.new("External_Child_91")
                c = bpy.data.collections["Character"]
                c.children.link(ext_child)
                external_child[0] = ext_child
                external_child_ptr[0] = ext_child.as_pointer()
                raise RuntimeError("Inject fault for TEST-91")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
            self.assertIn("Inject fault for TEST-91", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Both original child and external child must be linked to Character
        self.assertIn("Initial_Child_91", [c.name for c in char_col.children])
        self.assertIn("External_Child_91", [c.name for c in char_col.children])
        self.assertEqual(
            bpy.data.collections["External_Child_91"].as_pointer(),
            external_child_ptr[0],
        )

        # Cleanup
        char_col.children.unlink(initial_child)
        bpy.data.collections.remove(initial_child)
        char_col.children.unlink(external_child[0])
        bpy.data.collections.remove(external_child[0])

    def test_92_full_lifecycle_and_continuous_transaction_integration(self) -> None:
        """TEST-92: Comprehensive sequence of snapshot, rollback, commit, cleanup failure, admission gate, retry, and re-entry."""
        # 1. Initial rig setup
        setup_arm_ik(self.armature)
        snap1 = _snapshot_arm_rig_state(self.armature)

        # 2. Normal transaction
        y_pos = self.root.location.y + 0.15
        state1 = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
        self.assertIsNotNone(state1)
        self.assertTrue(state1["is_reachable"])

        # 3. Injected reversible fault and rollback
        snap2 = _snapshot_arm_rig_state(self.armature)

        def fault_hook_rb(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Injected reversible failure in TEST-92")

        _set_test_fault_injection_hook(fault_hook_rb)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.25, y_pos, 1.10))
        finally:
            _clear_test_fault_injection_hook()

        _verify_arm_rig_state_restored(self.armature, snap2)

        # 4. Replace controller, commit successfully but inject Phase 3 cleanup failure
        old_hand = bpy.data.objects["HandIK.L"]
        mesh_data = bpy.data.meshes.new("DoomedMesh92")
        wrong_obj = bpy.data.objects.new("HandIK.L", mesh_data)
        bpy.data.objects.remove(old_hand, do_unlink=True)
        bpy.context.scene.collection.objects.link(wrong_obj)

        def fault_hook_clean(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Injected Phase 3 cleanup failure in TEST-92")

        _set_test_fault_injection_hook(fault_hook_clean)
        try:
            with self.assertRaises(RuntimeError) as cm_cf:
                setup_arm_ik(self.armature)
            self.assertIn("Injected Phase 3 cleanup failure in TEST-92", str(cm_cf.exception))
        finally:
            _clear_test_fault_injection_hook()

        # 5. Verify Cleanup Pending and write admission blocking
        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertEqual(len(pending_ids), 1)
        tx_id = pending_ids[0]

        with self.assertRaises(RuntimeError) as cm_gate:
            set_hand_ik_target(self.armature, side="R", world_xyz=(0.32, y_pos, 1.20))
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_gate.exception))

        # 6. Retry pending cleanup to completion
        retry_pending_arm_rig_cleanup(tx_id)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        # 7. Resume normal writes
        state_r = set_hand_ik_target(self.armature, side="R", world_xyz=(0.32, y_pos, 1.20))
        self.assertIsNotNone(state_r)
        self.assertTrue(state_r["is_reachable"])

        # 8. Assert absolute state integrity
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)
        snap_final = _snapshot_arm_rig_state(self.armature)
        _verify_arm_rig_state_restored(self.armature, snap_final)

    def test_93_transaction_created_controller_renamed_cleaned_by_identity(self) -> None:
        """TEST-93: Transaction creates HandIK.L, then renames it; failure deletes by identity without residual."""
        old_hand = bpy.data.objects.get("HandIK.L")
        if old_hand is not None:
            bpy.data.objects.remove(old_hand, do_unlink=True)

        unrelated = bpy.data.objects.new("UnrelatedObj93", None)
        bpy.context.scene.collection.objects.link(unrelated)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                hand = bpy.data.objects.get("HandIK.L")
                if hand is not None:
                    hand.name = "HandIK_Renamed_93"
                raise RuntimeError("Fault injected in TEST-93 after renaming controller")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Fault injected in TEST-93", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNone(bpy.data.objects.get("HandIK_Renamed_93"))
        self.assertIsNone(bpy.data.objects.get("HandIK.L"))
        self.assertIsNotNone(bpy.data.objects.get("UnrelatedObj93"))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        bpy.data.objects.remove(unrelated, do_unlink=True)

    def test_94_external_same_name_controller_preserved_when_transaction_controller_renamed(self) -> None:
        """TEST-94: Transaction controller renamed, external creates same-name HandIK.L; rollback cleans tx object and preserves external."""
        old_hand = bpy.data.objects.get("HandIK.L")
        if old_hand is not None:
            bpy.data.objects.remove(old_hand, do_unlink=True)

        external_ptr = [None]
        external_mesh = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                hand = bpy.data.objects.get("HandIK.L")
                if hand is not None:
                    hand.name = "HandIK_TX_Renamed_94"
                mesh_data = bpy.data.meshes.new("Mesh_94")
                external_obj = bpy.data.objects.new("HandIK.L", mesh_data)
                bpy.context.scene.collection.objects.link(external_obj)
                external_ptr[0] = external_obj.as_pointer()
                external_mesh[0] = mesh_data
                raise RuntimeError("Fault injected in TEST-94 after external creation")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Fault injected in TEST-94", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNone(bpy.data.objects.get("HandIK_TX_Renamed_94"))
        ext_live = bpy.data.objects.get("HandIK.L")
        self.assertIsNotNone(ext_live)
        self.assertEqual(ext_live.as_pointer(), external_ptr[0])
        self.assertIsNotNone(bpy.data.meshes.get("Mesh_94"))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        bpy.data.objects.remove(ext_live, do_unlink=True)
        if external_mesh[0] is not None and "Mesh_94" in bpy.data.meshes:
            bpy.data.meshes.remove(external_mesh[0])

    def test_95_original_controller_physically_destroyed_fails_restoration(self) -> None:
        """TEST-95: Original controller physically destroyed during transaction fails identity restoration without substitutes."""
        setup_arm_ik(self.armature)
        unrelated = bpy.data.objects.new("UnrelatedObj95", None)
        bpy.context.scene.collection.objects.link(unrelated)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                ctrl = bpy.data.objects.get("HandIK.L")
                if ctrl is not None:
                    bpy.data.objects.remove(ctrl, do_unlink=True)
                raise RuntimeError("Primary business fault in TEST-95")

        _set_test_fault_injection_hook(fault_hook)
        try:
            y_pos = self.root.location.y + 0.15
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
            err_msg = str(cm.exception)
            self.assertIn("Primary business fault in TEST-95", err_msg)
            self.assertTrue(
                "Original controller identity lost" in err_msg or "restoration failed" in err_msg or "rollback" in err_msg,
                f"Expected identity loss in error message: {err_msg}"
            )
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNone(bpy.data.objects.get("HandIK.L"))
        self.assertIsNotNone(bpy.data.objects.get("UnrelatedObj95"))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        bpy.data.objects.remove(unrelated, do_unlink=True)

    def test_96_original_controller_name_occupied_by_external_object_fails_restoration(self) -> None:
        """TEST-96: Original controller renamed and original name occupied by external object fails restoration without overwriting."""
        setup_arm_ik(self.armature)
        hand_orig = bpy.data.objects["HandIK.L"]
        hand_orig_ptr = hand_orig.as_pointer()
        ext_holder = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                hand_orig.name = "HandIK_Original_Renamed_96"
                ext_obj = bpy.data.objects.new("HandIK.L", None)
                bpy.context.scene.collection.objects.link(ext_obj)
                ext_holder[0] = ext_obj
                raise RuntimeError("Primary business fault in TEST-96")

        _set_test_fault_injection_hook(fault_hook)
        try:
            y_pos = self.root.location.y + 0.15
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
            err_msg = str(cm.exception)
            self.assertIn("Primary business fault in TEST-96", err_msg)
            self.assertTrue(
                "occupied by another object" in err_msg or "restoration failed" in err_msg or "rollback" in err_msg,
                f"Expected name occupation error in: {err_msg}"
            )
        finally:
            _clear_test_fault_injection_hook()

        live_occupied = bpy.data.objects.get("HandIK.L")
        self.assertIsNotNone(live_occupied)
        self.assertEqual(live_occupied.as_pointer(), ext_holder[0].as_pointer())
        live_orig = bpy.data.objects.get("HandIK_Original_Renamed_96")
        self.assertIsNotNone(live_orig)
        self.assertEqual(live_orig.as_pointer(), hand_orig_ptr)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        bpy.data.objects.remove(live_occupied, do_unlink=True)
        bpy.data.objects.remove(live_orig, do_unlink=True)

    def test_97_stashed_constraint_reference_invalid_with_same_name_replacement(self) -> None:
        """TEST-97: Stashed constraint original reference becomes invalid with live same-name replacement; cleanup fails without deleting replacement."""
        setup_arm_ik(self.armature)
        p_fore = self.armature.pose.bones["forearm.L"]

        dummy_con = p_fore.constraints.new(type="LIMIT_ROTATION")
        dummy_con.name = "Stashed_Con_97"
        dummy_ptr = dummy_con.as_pointer()

        tx = _ArmRigTransactionContext(self.armature)
        stashed_record = {
            "pbone": p_fore,
            "con": dummy_con,
            "con_ptr": dummy_ptr,
            "orig_name": "Stashed_Con_97",
            "orig_mute": False,
        }
        tx.stashed_constraints.append(stashed_record)
        tx.uncleaned_stashed_constraints.append(stashed_record)

        p_fore.constraints.remove(dummy_con)

        replacement = p_fore.constraints.new(type="LIMIT_ROTATION")
        replacement.name = "Stashed_Con_97"
        replacement_ptr = replacement.as_pointer()

        with self.assertRaises(RuntimeError) as cm:
            tx.retry_cleanup()

        self.assertIn("original reference invalid", str(cm.exception))
        self.assertIn("Stashed_Con_97", p_fore.constraints)
        self.assertEqual(p_fore.constraints["Stashed_Con_97"].as_pointer(), replacement_ptr)
        self.assertEqual(len(tx.uncleaned_stashed_constraints), 1)

        p_fore.constraints.remove(replacement)

    def test_98_controller_registered_before_collection_link_failure(self) -> None:
        """TEST-98: Controller registration occurs immediately after creation; collection link failure rolls back cleanly."""
        old_hand = bpy.data.objects.get("HandIK.L")
        if old_hand is not None:
            bpy.data.objects.remove(old_hand, do_unlink=True)

        char_col = bpy.data.collections.get("Character")
        if char_col is None:
            char_col = bpy.data.collections.new("Character")
            bpy.context.scene.collection.children.link(char_col)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "get_or_create_empty_after_register" and ctx.get("name") == "HandIK.L":
                raise RuntimeError("Simulated collection.objects.link failure in TEST-98")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Simulated collection.objects.link failure in TEST-98", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNone(bpy.data.objects.get("HandIK.L"))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_99_exception_after_logical_commit_enters_cleanup_pending(self) -> None:
        """TEST-99: Exception at after_logical_commit enters CLEANUP_PENDING without ordinary rollback; retry succeeds."""
        setup_arm_ik(self.armature)
        y_pos = self.root.location.y + 0.15
        target_pos = (-0.32, y_pos, 1.20)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "after_logical_commit":
                raise RuntimeError("Crash after logical commit in TEST-99")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=target_pos)
            self.assertIn("post-commit cleanup failed", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertEqual(len(pending_ids), 1)
        tx_id = pending_ids[0]

        hand_ik = bpy.data.objects["HandIK.L"]
        self.assertAlmostEqual(hand_ik.matrix_world.translation.x, target_pos[0], places=3)
        self.assertAlmostEqual(hand_ik.matrix_world.translation.y, target_pos[1], places=3)
        self.assertAlmostEqual(hand_ik.matrix_world.translation.z, target_pos[2], places=3)

        with self.assertRaises(RuntimeError) as cm_gate:
            set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_gate.exception))

        retry_pending_arm_rig_cleanup(tx_id)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        state = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
        self.assertIsNotNone(state)
        self.assertTrue(state["is_reachable"])

    def test_100_reversible_vs_post_commit_failure_boundaries(self) -> None:
        """TEST-100: Reversible stages rollback state; post-commit stages enter CLEANUP_PENDING without duplicate rollback."""
        setup_arm_ik(self.armature)
        y_pos = self.root.location.y + 0.15

        for stage_name in ("before_commit_prepare", "during_commit_prepare"):
            snap_before = _snapshot_arm_rig_state(self.armature)

            def fault_hook(stage: str, ctx: dict) -> None:
                if stage == stage_name:
                    raise RuntimeError(f"Simulated fault at {stage_name}")

            _set_test_fault_injection_hook(fault_hook)
            try:
                with self.assertRaises(RuntimeError) as cm:
                    set_hand_ik_target(self.armature, side="L", world_xyz=(-0.25, y_pos, 1.10))
                self.assertIn(f"Simulated fault at {stage_name}", str(cm.exception))
            finally:
                _clear_test_fault_injection_hook()

            _verify_arm_rig_state_restored(self.armature, snap_before)
            self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        for stage_name in ("after_logical_commit", "during_commit_cleanup"):
            target_coord = (-0.31, y_pos, 1.18)

            def fault_hook_post(stage: str, ctx: dict) -> None:
                if stage == stage_name:
                    raise RuntimeError(f"Simulated fault at {stage_name}")

            _set_test_fault_injection_hook(fault_hook_post)
            try:
                with self.assertRaises(RuntimeError) as cm:
                    set_hand_ik_target(self.armature, side="L", world_xyz=target_coord)
                self.assertIn("post-commit cleanup failed", str(cm.exception))
            finally:
                _clear_test_fault_injection_hook()

            hand_ctrl = bpy.data.objects["HandIK.L"]
            self.assertAlmostEqual(hand_ctrl.location.x, target_coord[0], places=3)

            pending = get_pending_arm_rig_cleanup_ids()
            self.assertEqual(len(pending), 1)
            retry_pending_arm_rig_cleanup(pending[0])
            self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_101_joint_multi_resource_identity_and_ownership_verification(self) -> None:
        """TEST-101: Joint simulation of controller rename, constraint stash, collection addition, and datablock sharing."""
        setup_arm_ik(self.armature)
        char_col = bpy.data.collections["Character"]

        shared_mesh = bpy.data.meshes.new("SharedMesh101")
        ext_obj = bpy.data.objects.new("ExternalObj101", shared_mesh)
        char_col.objects.link(ext_obj)
        ext_obj_ptr = ext_obj.as_pointer()
        shared_mesh_ptr = shared_mesh.as_pointer()

        p_fore = self.armature.pose.bones["forearm.L"]
        orig_con_ptr = p_fore.constraints["ArmIK.L"].as_pointer()

        ext_member2_ptr = [None]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                hand_ik = bpy.data.objects.get("HandIK.L")
                if hand_ik is not None:
                    hand_ik.name = "HandIK_L_Mutated_101"

                ext_member2 = bpy.data.objects.new("ExternalMember2_101", None)
                char_col.objects.link(ext_member2)
                ext_member2_ptr[0] = ext_member2.as_pointer()

                raise RuntimeError("Fault injected in TEST-101 joint simulation")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
            self.assertIn("Fault injected in TEST-101", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        hand_live = bpy.data.objects.get("HandIK.L")
        self.assertIsNotNone(hand_live)
        self.assertIsNone(bpy.data.objects.get("HandIK_L_Mutated_101"))

        self.assertEqual(p_fore.constraints["ArmIK.L"].as_pointer(), orig_con_ptr)

        char_obj_names = [o.name for o in char_col.objects]
        self.assertIn("ExternalObj101", char_obj_names)
        self.assertIn("ExternalMember2_101", char_obj_names)
        self.assertEqual(bpy.data.objects["ExternalObj101"].as_pointer(), ext_obj_ptr)
        self.assertEqual(bpy.data.objects["ExternalMember2_101"].as_pointer(), ext_member2_ptr[0])

        self.assertIn("SharedMesh101", bpy.data.meshes)
        self.assertEqual(bpy.data.meshes["SharedMesh101"].as_pointer(), shared_mesh_ptr)

        ext_m2 = bpy.data.objects.get("ExternalMember2_101")
        if ext_m2:
            bpy.data.objects.remove(ext_m2, do_unlink=True)
        bpy.data.objects.remove(ext_obj, do_unlink=True)
        if "SharedMesh101" in bpy.data.meshes:
            bpy.data.meshes.remove(shared_mesh)

    def test_102_continuous_full_lifecycle_and_reentry(self) -> None:
        """TEST-102: End-to-end full continuous lifecycle covering all 9 states, admission gates, and resource classes."""
        y_pos = self.root.location.y + 0.15

        # 1. Initial setup
        setup_arm_ik(self.armature)
        char_col = bpy.data.collections["Character"]
        self.assertIsNotNone(char_col)

        # 2. Snapshot
        snap1 = _snapshot_arm_rig_state(self.armature)

        # 3. Transaction write with injected failure -> Rollback
        def fault_hook_rb(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Step 3 failure in TEST-102")

        _set_test_fault_injection_hook(fault_hook_rb)
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.25, y_pos, 1.10))
            self.assertIn("Step 3 failure in TEST-102", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # 4. Verify rollback
        _verify_arm_rig_state_restored(self.armature, snap1)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # 5. Replace controller with wrong-type mesh object sharing a datablock
        shared_mesh = bpy.data.meshes.new("DoomedMesh102")
        old_hand_r = bpy.data.objects["HandIK.R"]
        bpy.data.objects.remove(old_hand_r, do_unlink=True)
        wrong_obj = bpy.data.objects.new("HandIK.R", shared_mesh)
        char_col.objects.link(wrong_obj)

        # 6. Commit setup_arm_ik but inject post-commit cleanup failure
        def fault_hook_clean(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Step 6 cleanup failure in TEST-102")

        _set_test_fault_injection_hook(fault_hook_clean)
        try:
            with self.assertRaises(RuntimeError) as cm_cf:
                setup_arm_ik(self.armature)
            self.assertIn("post-commit cleanup failed", str(cm_cf.exception))
        finally:
            _clear_test_fault_injection_hook()

        # 7. CLEANUP_PENDING verification and write admission blocking
        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertEqual(len(pending_ids), 1)
        tx_id = pending_ids[0]

        with self.assertRaises(RuntimeError) as cm_gate:
            set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_gate.exception))

        # 8. Retry pending cleanup to completion
        retry_pending_arm_rig_cleanup(tx_id)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        # 9. Re-entry - normal write succeeds
        state_l = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20))
        self.assertIsNotNone(state_l)
        self.assertTrue(state_l["is_reachable"])

        state_r = set_hand_ik_target(self.armature, side="R", world_xyz=(0.32, y_pos, 1.20))
        self.assertIsNotNone(state_r)
        self.assertTrue(state_r["is_reachable"])

        # 10. Final state inspection across all controllers, constraints, and collections
        for ctrl_name in ("HandIK.L", "HandIK.R", "ElbowPole.L", "ElbowPole.R"):
            obj = bpy.data.objects.get(ctrl_name)
            self.assertIsNotNone(obj)
            self.assertEqual(obj.type, "EMPTY")

        for b_name in ("forearm.L", "forearm.R"):
            pbone = self.armature.pose.bones[b_name]
            self.assertIn("ArmIK" + b_name[-2:], pbone.constraints)

        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        snap_final = _snapshot_arm_rig_state(self.armature)
        _verify_arm_rig_state_restored(self.armature, snap_final)

    # -------------------------------------------------------------------------
    # Task 10-B-9 Extended Tests (TEST-103 to TEST-112)
    # -------------------------------------------------------------------------

    def test_103_transaction_created_constraint_cleaned_up_by_identity(self) -> None:
        """TEST-103: Transaction-created constraints are identified and removed by pointer identity upon rollback."""
        snap_initial = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend" and ctx.get("side") == "R":
                raise RuntimeError("Fault after R constraint creation in TEST-103")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.6)
            self.assertIn("Fault after R constraint creation in TEST-103", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Both L and R created constraints must be completely unlinked and removed
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        self.assertNotIn("ArmIK.L", p_fore_l.constraints)
        self.assertNotIn("ArmIK.R", p_fore_r.constraints)

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_104_external_constraint_preserved_on_transaction_failure(self) -> None:
        """TEST-104: External constraints on rig bones are strictly preserved when an arm transaction aborts."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        # Add external constraint on forearm.L
        p_fore = self.armature.pose.bones["forearm.L"]
        ext_con = p_fore.constraints.new(type="COPY_ROTATION")
        ext_con.name = "ExternalCopyRot104"
        ext_con.influence = 0.73
        ext_ptr = ext_con.as_pointer()
        bpy.context.view_layer.update()

        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault during hand location in TEST-104")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15), influence=0.9)
            self.assertIn("Fault during hand location in TEST-104", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # External constraint must still exist with unchanged identity and properties
        self.assertIn("ExternalCopyRot104", p_fore.constraints)
        live_ext = p_fore.constraints["ExternalCopyRot104"]
        self.assertEqual(live_ext.as_pointer(), ext_ptr)
        self.assertAlmostEqual(live_ext.influence, 0.73, places=5)

        _verify_arm_rig_state_restored(self.armature, snap)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_105_same_name_different_identity_constraint_not_erroneously_deleted(self) -> None:
        """TEST-105: Same-name constraint with different identity pointer is never deleted by rollback."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        # Add a constraint named 'ArmIK.L' on another bone (upper_arm.L)
        p_up = self.armature.pose.bones["upper_arm.L"]
        alien_con = p_up.constraints.new(type="LIMIT_ROTATION")
        alien_con.name = "ArmIK.L"
        alien_con.use_limit_x = True
        alien_ptr = alien_con.as_pointer()
        bpy.context.view_layer.update()

        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault in TEST-105")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
            self.assertIn("Fault in TEST-105", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # The alien constraint on upper_arm.L must be 100% untouched
        self.assertIn("ArmIK.L", p_up.constraints)
        live_alien = p_up.constraints["ArmIK.L"]
        self.assertEqual(live_alien.as_pointer(), alien_ptr)
        self.assertTrue(live_alien.use_limit_x)

        _verify_arm_rig_state_restored(self.armature, snap)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_106_external_constraint_insertion_preserves_original_constraint_order(self) -> None:
        """TEST-106: Inserting external constraints before/between original constraints maintains relative ordering."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        p_fore = self.armature.pose.bones["forearm.L"]
        # Add a second constraint so we have multiple original constraints
        orig_limit = p_fore.constraints.new(type="LIMIT_ROTATION")
        orig_limit.name = "OrigLimit106"
        bpy.context.view_layer.update()

        snap = _snapshot_arm_rig_state(self.armature)

        # Invert original constraint order: move OrigLimit106 before ArmIK.L
        p_fore.constraints.move(1, 0)
        # Add an external constraint at index 0
        ext_first = p_fore.constraints.new(type="TRACK_TO")
        ext_first.name = "ExtFirst106"
        p_fore.constraints.move(len(p_fore.constraints) - 1, 0)
        bpy.context.view_layer.update()

        # Execute mock transaction rollback
        tx = _ArmRigTransactionContext(self.armature)
        tx.snapshot = snap
        _ACTIVE_TRANSACTION_STACK.append(tx)
        try:
            _rollback_arm_rig_state(self.armature, snap, active_tx=tx)
            _verify_arm_rig_state_restored(self.armature, snap, active_tx=tx)
        finally:
            _ACTIVE_TRANSACTION_STACK.pop()

        # ArmIK.L must come before OrigLimit106 again
        c_names = [c.name for c in p_fore.constraints]
        self.assertIn("ArmIK.L", c_names)
        self.assertIn("OrigLimit106", c_names)
        self.assertLess(c_names.index("ArmIK.L"), c_names.index("OrigLimit106"))
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_107_transaction_created_collection_link_undone_on_failure(self) -> None:
        """TEST-107: Controller collection links created within a transaction are unlinked on rollback."""
        snap_initial = _snapshot_arm_rig_state(self.armature)
        char_col = bpy.data.collections.get("Character")
        self.assertIsNotNone(char_col)
        initial_member_count = len(char_col.objects)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                raise RuntimeError("Fault after first controller in TEST-107")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Fault after first controller in TEST-107", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Character collection must not retain any leaked objects or links
        self.assertEqual(len(char_col.objects), initial_member_count)
        self.assertNotIn("HandIK.L", char_col.objects)
        self.assertNotIn("HandIK.L", bpy.data.objects)

        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_108_external_collection_member_link_preserved_on_rollback(self) -> None:
        """TEST-108: External collection members linked before transaction are not unlinked during rollback."""
        setup_arm_ik(self.armature, initial_influence=0.5)

        char_col = bpy.data.collections.get("Character")
        ext_mesh = bpy.data.meshes.new("ExternalMesh108")
        ext_obj = bpy.data.objects.new("ExternalMember108", ext_mesh)
        char_col.objects.link(ext_obj)
        ext_ptr = ext_obj.as_pointer()
        bpy.context.view_layer.update()

        snap = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Fault in TEST-108")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
            self.assertIn("Fault in TEST-108", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # ext_obj must remain securely linked inside Character collection
        self.assertIn("ExternalMember108", char_col.objects)
        self.assertEqual(char_col.objects["ExternalMember108"].as_pointer(), ext_ptr)

        _verify_arm_rig_state_restored(self.armature, snap)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Clean up external test object
        bpy.data.objects.remove(ext_obj, do_unlink=True)
        bpy.data.meshes.remove(ext_mesh, do_unlink=True)

    def test_109_reset_arm_ik_left_write_failure_restores_bilateral_state(self) -> None:
        """TEST-109: reset_arm_ik left-side write failure triggers bilateral rollback preserving pre-reset pose."""
        setup_arm_ik(self.armature, initial_influence=0.8)
        y_pos = self.root.location.y + 0.15
        set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20), influence=0.85)
        set_hand_ik_target(self.armature, side="R", world_xyz=(0.32, y_pos, 1.20), influence=0.85)

        snap_before_reset = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "reset_arm_ik_after_influence_l":
                raise RuntimeError("Fault after Left reset write in TEST-109")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                reset_arm_ik(self.armature)
            self.assertIn("Fault after Left reset write in TEST-109", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Both Left and Right influences and positions must be completely restored
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        self.assertAlmostEqual(p_fore_l.constraints["ArmIK.L"].influence, 0.85, places=4)
        self.assertAlmostEqual(p_fore_r.constraints["ArmIK.R"].influence, 0.85, places=4)

        _verify_arm_rig_state_restored(self.armature, snap_before_reset)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_110_reset_arm_ik_right_write_failure_restores_bilateral_state(self) -> None:
        """TEST-110: reset_arm_ik right-side write failure restores both left and right sides via atomic rollback."""
        setup_arm_ik(self.armature, initial_influence=0.7)
        y_pos = self.root.location.y + 0.15
        set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15), influence=0.75)
        set_hand_ik_target(self.armature, side="R", world_xyz=(0.30, y_pos, 1.15), influence=0.75)

        snap_before_reset = _snapshot_arm_rig_state(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "reset_arm_ik_after_influence_r":
                raise RuntimeError("Fault after Right reset write in TEST-110")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                reset_arm_ik(self.armature)
            self.assertIn("Fault after Right reset write in TEST-110", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        # Left side was mutated first, but atomic rollback must revert Left side as well as Right side
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        self.assertAlmostEqual(p_fore_l.constraints["ArmIK.L"].influence, 0.75, places=4)
        self.assertAlmostEqual(p_fore_r.constraints["ArmIK.R"].influence, 0.75, places=4)

        _verify_arm_rig_state_restored(self.armature, snap_before_reset)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_111_reset_arm_ik_parent_preflight_failure_zero_business_writes(self) -> None:
        """TEST-111: reset_arm_ik aborts on parent transform preflight failure before performing any scene writes."""
        setup_arm_ik(self.armature, initial_influence=0.88)
        snap_before = _snapshot_arm_rig_state(self.armature)

        # Corrupt parent transform by setting root scale to 0 (non-invertible matrix)
        self.root.scale = Vector((0.0, 0.0, 0.0))
        bpy.context.view_layer.update()

        try:
            with self.assertRaises(ValueError) as cm:
                reset_arm_ik(self.armature)
            self.assertTrue("singular matrix" in str(cm.exception).lower() or "zero determinant" in str(cm.exception).lower())
        finally:
            self.root.scale = Vector((1.0, 1.0, 1.0))
            bpy.context.view_layer.update()

        # Zero business writes: bone influences and controllers remain unchanged
        p_fore_l = self.armature.pose.bones["forearm.L"]
        p_fore_r = self.armature.pose.bones["forearm.R"]
        self.assertAlmostEqual(p_fore_l.constraints["ArmIK.L"].influence, 0.88, places=4)
        self.assertAlmostEqual(p_fore_r.constraints["ArmIK.R"].influence, 0.88, places=4)

        _verify_arm_rig_state_restored(self.armature, snap_before)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_112_joint_regression_reset_constraint_collection_cleanup_pending(self) -> None:
        """TEST-112: Joint regression verifying reset atomicity, constraint rollback, and cleanup pending gate."""
        setup_arm_ik(self.armature, initial_influence=0.6)
        y_pos = self.root.location.y + 0.15

        # 1. External object in Character collection
        char_col = bpy.data.collections.get("Character")
        ext_mesh = bpy.data.meshes.new("Mesh112")
        ext_obj = bpy.data.objects.new("ExternalProp112", ext_mesh)
        char_col.objects.link(ext_obj)
        ext_ptr = ext_obj.as_pointer()

        # 2. External constraint on forearm.L
        p_fore_l = self.armature.pose.bones["forearm.L"]
        ext_con = p_fore_l.constraints.new(type="LIMIT_ROTATION")
        ext_con.name = "ExtLimit112"
        ext_con_ptr = ext_con.as_pointer()
        bpy.context.view_layer.update()

        # 3. Successful pose mutation
        set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15), influence=0.8)
        set_hand_ik_target(self.armature, side="R", world_xyz=(0.30, y_pos, 1.15), influence=0.8)

        snap_active = _snapshot_arm_rig_state(self.armature)

        # 4. Injected reset failure -> bilateral rollback
        def fault_hook_reset(stage: str, ctx: dict) -> None:
            if stage == "reset_arm_ik_after_influence_l":
                raise RuntimeError("Injected fault during reset in TEST-112")

        _set_test_fault_injection_hook(fault_hook_reset)
        try:
            with self.assertRaises(RuntimeError):
                reset_arm_ik(self.armature)
        finally:
            _clear_test_fault_injection_hook()

        # Verify full state preserved after failed reset
        _verify_arm_rig_state_restored(self.armature, snap_active)
        self.assertEqual(char_col.objects["ExternalProp112"].as_pointer(), ext_ptr)
        self.assertEqual(p_fore_l.constraints["ExtLimit112"].as_pointer(), ext_con_ptr)

        # 5. Clean reset succeeds
        reset_arm_ik(self.armature)
        self.assertAlmostEqual(p_fore_l.constraints["ArmIK.L"].influence, 0.0, places=4)
        self.assertAlmostEqual(self.armature.pose.bones["forearm.R"].constraints["ArmIK.R"].influence, 0.0, places=4)
        # External objects and constraints still intact
        self.assertEqual(char_col.objects["ExternalProp112"].as_pointer(), ext_ptr)
        self.assertEqual(p_fore_l.constraints["ExtLimit112"].as_pointer(), ext_con_ptr)

        # 6. Verify CLEANUP_PENDING gate blocks reset_arm_ik and mutations
        snap_after_reset = _snapshot_arm_rig_state(self.armature)
        fake_tx = _ArmRigTransactionContext(self.armature)
        fake_tx.state = _ArmRigTransactionState.CLEANUP_PENDING
        fake_tx.uncleaned_stashed_objects.append({"original_name": "Ghost112", "obj_cleaned": False, "data_cleaned": False})
        from src.rig.arm_ik import _register_pending_arm_rig_cleanup
        _register_pending_arm_rig_cleanup(fake_tx)

        with self.assertRaises(RuntimeError) as cm_blocked:
            reset_arm_ik(self.armature)
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_blocked.exception))

        with self.assertRaises(RuntimeError) as cm_blocked2:
            set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15))
        self.assertIn("Arm IK write blocked: unresolved cleanup", str(cm_blocked2.exception))

        # Clear gate and clean up test fixtures
        _PENDING_ARM_RIG_CLEANUPS.clear()
        _verify_arm_rig_state_restored(self.armature, snap_after_reset)

        p_fore_l.constraints.remove(ext_con)
        bpy.data.objects.remove(ext_obj, do_unlink=True)
        bpy.data.meshes.remove(ext_mesh, do_unlink=True)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    # -------------------------------------------------------------------------
    # Task 10-B-11 Relationship Log & Ownership Tests (TEST-113 to TEST-117)
    # -------------------------------------------------------------------------

    def test_113_pre_existing_collection_link_transitions_to_no_effect_without_revocation_authority(self) -> None:
        """TEST-113: Duplicate link on PRE_EXISTING_ORIGINAL transitions PREPARED -> NO_EFFECT without revocation authority."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        char_col = bpy.data.collections["Character"]
        hand_l = bpy.data.objects["HandIK.L"]
        hand_l_ptr = hand_l.as_pointer()
        snap_initial = _snapshot_arm_rig_state(self.armature)

        captured_tx = []
        observed_prepared_states = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "relationship_link_after_prepare":
                op = ctx.get("op", {})
                observed_prepared_states.append(op.get("operation_state"))
            elif stage == "setup_arm_ik_after_constraints_or_prebend" and ctx.get("side") == "R":
                if _ACTIVE_TRANSACTION_STACK:
                    captured_tx.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Fault in TEST-113 after idempotent controller link checks")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.9)
            self.assertIn("Fault in TEST-113", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]

        # All 4 existing controllers were already linked (PRE_EXISTING_ORIGINAL)
        self.assertEqual(len(tx.created_collection_links), 0)
        self.assertEqual(len(tx.prepared_relationship_mutations), 4)
        self.assertTrue(all(s == _RelationshipOperationState.PREPARED for s in observed_prepared_states))

        required_fields = {
            "operation_id",
            "transaction_id",
            "source_reference",
            "target_reference",
            "source_identity",
            "target_identity",
            "original_relationship_state",
            "intended_mutation",
            "operation_state",
        }
        for rec in tx.prepared_relationship_mutations:
            self.assertTrue(required_fields.issubset(rec.keys()))
            self.assertEqual(rec["transaction_id"], tx.tx_id)
            self.assertEqual(rec["intended_mutation"], "COLLECTION_OBJECT_LINK")
            self.assertEqual(rec["original_relationship_state"]["category"], "PRE_EXISTING_ORIGINAL")
            self.assertTrue(rec["original_relationship_state"]["linked"])
            self.assertEqual(rec["operation_state"], _RelationshipOperationState.NO_EFFECT)

        # Original collection link must remain 100% preserved after rollback
        self.assertIn("HandIK.L", char_col.objects)
        self.assertEqual(char_col.objects["HandIK.L"].as_pointer(), hand_l_ptr)
        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_114_apply_succeeded_before_confirm_exception_safely_reverted_on_rollback(self) -> None:
        """TEST-114: Exception after C-API link apply (before CONFIRM) logs APPLIED_VERIFIED and reverts to REVERTED on rollback."""
        snap_initial = _snapshot_arm_rig_state(self.armature)
        char_col = bpy.data.collections["Character"]
        initial_member_ptrs = {o.as_pointer() for o in char_col.objects}

        for fault_stage in ("relationship_link_during_apply_after_c_api", "relationship_link_before_confirm"):
            captured_ops = []

            def fault_hook(stage: str, ctx: dict, target_stage: str = fault_stage) -> None:
                if stage == target_stage and ctx.get("name") == "HandIK.L":
                    captured_ops.append(ctx["op"])
                    raise RuntimeError(f"Injected fault at {target_stage} in TEST-114")

            _set_test_fault_injection_hook(fault_hook)
            try:
                with self.assertRaises(RuntimeError) as cm:
                    setup_arm_ik(self.armature)
                self.assertIn(f"Injected fault at {fault_stage} in TEST-114", str(cm.exception))
            finally:
                _clear_test_fault_injection_hook()

            self.assertEqual(len(captured_ops), 1)
            op_rec = captured_ops[0]
            # Rollback must have reverted the APPLIED_VERIFIED relationship to REVERTED
            self.assertEqual(op_rec[" intended_mutation" if " intended_mutation" in op_rec else "intended_mutation"], "COLLECTION_OBJECT_LINK")
            self.assertEqual(op_rec["original_relationship_state"]["category"], "TX_ADDED")
            self.assertEqual(op_rec["operation_state"], _RelationshipOperationState.REVERTED)

            # Zero residual link or controller in scene
            self.assertNotIn("HandIK.L", char_col.objects)
            self.assertNotIn("HandIK.L", bpy.data.objects)
            self.assertEqual({o.as_pointer() for o in char_col.objects}, initial_member_ptrs)
            _verify_arm_rig_state_restored(self.armature, snap_initial)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_115_apply_exception_with_zero_side_effect_transitions_log_to_no_effect(self) -> None:
        """TEST-115: Exception during APPLYING before C-API link with zero RNA side effect transitions log to NO_EFFECT."""
        snap_initial = _snapshot_arm_rig_state(self.armature)
        char_col = bpy.data.collections["Character"]
        captured_ops = []
        observed_applying_state = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "relationship_link_during_apply_before_c_api" and ctx.get("name") == "HandIK.L":
                op = ctx["op"]
                observed_applying_state.append(op["operation_state"])
                captured_ops.append(op)
                raise RuntimeError("Fault during APPLYING before C-API link in TEST-115")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Fault during APPLYING before C-API link in TEST-115", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(observed_applying_state, [_RelationshipOperationState.APPLYING])
        self.assertEqual(len(captured_ops), 1)
        self.assertEqual(captured_ops[0]["operation_state"], _RelationshipOperationState.NO_EFFECT)

        self.assertNotIn("HandIK.L", char_col.objects)
        self.assertNotIn("HandIK.L", bpy.data.objects)
        _verify_arm_rig_state_restored(self.armature, snap_initial)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_116_external_same_name_object_and_external_collection_link_protected_on_rollback(self) -> None:
        """TEST-116: External same-name object and EXTERNAL_ADDED collection link are never unlinked or deleted on rollback."""
        char_col = bpy.data.collections["Character"]
        ext_same_name_ptr = [None]
        ext_member_ptr = [None]
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                tx = _ACTIVE_TRANSACTION_STACK[-1]
                captured_tx.append(tx)
                # Rename transaction-created HandIK.L and create an external same-name HandIK.L linked to Character
                tx_hand = bpy.data.objects["HandIK.L"]
                tx_hand.name = "HandIK_L_TX_Owned_116"

                ext_same = bpy.data.objects.new("HandIK.L", None)
                char_col.objects.link(ext_same)
                ext_same_name_ptr[0] = ext_same.as_pointer()

                ext_other = bpy.data.objects.new("ExternalAddedMember116", None)
                char_col.objects.link(ext_other)
                ext_member_ptr[0] = ext_other.as_pointer()

                raise RuntimeError("Fault injected in TEST-116 after external links")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            self.assertIn("Fault injected in TEST-116", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(len(tx.prepared_relationship_mutations), 1)
        self.assertEqual(tx.prepared_relationship_mutations[0]["operation_state"], _RelationshipOperationState.REVERTED)

        # Transaction-owned controller was unlinked and deleted
        self.assertIsNone(bpy.data.objects.get("HandIK_L_TX_Owned_116"))

        # External same-name HandIK.L and ExternalAddedMember116 remain linked in Character collection
        self.assertIn("HandIK.L", char_col.objects)
        self.assertEqual(char_col.objects["HandIK.L"].as_pointer(), ext_same_name_ptr[0])
        self.assertIn("ExternalAddedMember116", char_col.objects)
        self.assertEqual(char_col.objects["ExternalAddedMember116"].as_pointer(), ext_member_ptr[0])

        bpy.data.objects.remove(bpy.data.objects["HandIK.L"], do_unlink=True)
        bpy.data.objects.remove(bpy.data.objects["ExternalAddedMember116"], do_unlink=True)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_117_rollback_verifies_relationship_log_terminal_states_and_reports_recovery_uncertain(self) -> None:
        """TEST-117: Rollback verifies all relationship log entries reach NO_EFFECT/REVERTED and raises on RECOVERY_UNCERTAIN."""
        # Part A: Mixed PRE_EXISTING_ORIGINAL (NO_EFFECT) and TX_ADDED (REVERTED) in a single transaction rollback
        setup_arm_ik(self.armature, initial_influence=0.5)
        char_col = bpy.data.collections["Character"]
        # Unlink HandIK.R before transaction so HandIK.L is PRE_EXISTING_ORIGINAL and HandIK.R is TX_ADDED
        hand_r = bpy.data.objects["HandIK.R"]
        char_col.objects.unlink(hand_r)
        snap_mixed = _snapshot_arm_rig_state(self.armature)

        captured_tx_a = []

        def fault_hook_a(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend" and ctx.get("side") == "R":
                captured_tx_a.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Fault in TEST-117 Part A")

        _set_test_fault_injection_hook(fault_hook_a)
        try:
            with self.assertRaises(RuntimeError) as cm_a:
                setup_arm_ik(self.armature, initial_influence=0.8)
            self.assertIn("Fault in TEST-117 Part A", str(cm_a.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx_a), 1)
        tx_a = captured_tx_a[0]
        states_by_name = {
            rec["target_identity"]["name"]: rec["operation_state"]
            for rec in tx_a.prepared_relationship_mutations
        }
        self.assertEqual(states_by_name["HandIK.L"], _RelationshipOperationState.NO_EFFECT)
        self.assertEqual(states_by_name["ElbowPole.L"], _RelationshipOperationState.NO_EFFECT)
        self.assertEqual(states_by_name["HandIK.R"], _RelationshipOperationState.REVERTED)
        self.assertEqual(states_by_name["ElbowPole.R"], _RelationshipOperationState.NO_EFFECT)
        _verify_arm_rig_state_restored(self.armature, snap_mixed)

        # Restore HandIK.R link for Part B
        char_col.objects.link(hand_r)
        snap_clean = _snapshot_arm_rig_state(self.armature)

        # Part B: Fault during relationship rollback undo transitions record to RECOVERY_UNCERTAIN and raises RuntimeError
        char_col.objects.unlink(hand_r)
        captured_tx_b = []

        def fault_hook_b(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend" and ctx.get("side") == "R":
                captured_tx_b.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary business fault in TEST-117 Part B")
            elif stage == "during_relationship_rollback_undo":
                op = ctx.get("op", {})
                if op.get("target_identity", {}).get("name") == "HandIK.R":
                    raise RuntimeError("Simulated C-API unlink failure during rollback")

        _set_test_fault_injection_hook(fault_hook_b)
        try:
            with self.assertRaises(RuntimeError) as cm_b:
                setup_arm_ik(self.armature, initial_influence=0.9)
            err_msg = str(cm_b.exception)
            self.assertIn("Primary business fault in TEST-117 Part B", err_msg)
            self.assertIn("rollback verification failed", err_msg)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx_b), 1)
        tx_b = captured_tx_b[0]
        self.assertEqual(tx_b.state, _ArmRigTransactionState.FAILED)
        hand_r_ops = [
            r for r in tx_b.prepared_relationship_mutations
            if r["target_identity"]["name"] == "HandIK.R"
        ]
        self.assertEqual(len(hand_r_ops), 1)
        self.assertEqual(hand_r_ops[0]["operation_state"], _RelationshipOperationState.RECOVERY_UNCERTAIN)

        # Part C: Direct verifier check rejects any transaction context containing a RECOVERY_UNCERTAIN record
        _ACTIVE_TRANSACTION_STACK.append(tx_b)
        try:
            with self.assertRaises(RuntimeError) as cm_c:
                _verify_arm_rig_state_restored(self.armature, snap_clean, active_tx=tx_b)
            self.assertIn("RECOVERY_UNCERTAIN", str(cm_c.exception))
        finally:
            _ACTIVE_TRANSACTION_STACK.pop()

        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_118_normal_same_armature_nested_transaction(self) -> None:
        """TEST-118: Normal same-Armature nested transaction shares outer context, snapshots once, and commits."""
        setup_arm_ik(self.armature, initial_influence=0.3)
        snapshot_calls = [0]
        orig_snapshot_fn = sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state

        def counting_snapshot(arm):
            snapshot_calls[0] += 1
            return orig_snapshot_fn(arm)

        sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = counting_snapshot
        try:
            with _arm_rig_transaction(self.armature) as outer_tx:
                self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 1)
                self.assertFalse(outer_tx.rollback_only)
                self.assertIsNone(outer_tx.rollback_only_reason)

                with _arm_rig_transaction(self.armature) as inner_tx:
                    self.assertIs(inner_tx, outer_tx)
                    self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 1)
                    set_arm_ik_influence(self.armature, "L", 0.75)

                self.assertFalse(outer_tx.rollback_only)
                self.assertIsNone(outer_tx.rollback_only_reason)
                self.assertEqual(outer_tx.state, _ArmRigTransactionState.ACTIVE)
        finally:
            sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = orig_snapshot_fn

        self.assertEqual(snapshot_calls[0], 1)
        self.assertFalse(outer_tx.rollback_only)
        self.assertEqual(outer_tx.state, _ArmRigTransactionState.COMMITTED)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.75, places=6
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["hand.L"].constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.75, places=6
        )

    def test_119_inner_exception_caught_by_outer_forces_rollback(self) -> None:
        """TEST-119: Inner nested failure caught by outer caller marks rollback_only and forces full outer rollback."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        initial_snapshot = _snapshot_arm_rig_state(self.armature)
        observed_states = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences":
                raise RuntimeError("Injected inner nested failure in TEST-119")
            if stage in ("before_commit_prepare", "during_commit_prepare", "after_logical_commit"):
                observed_states.append(stage)

        _set_test_fault_injection_hook(fault_hook)
        outer_tx_ref = None
        try:
            with self.assertRaises(RuntimeError) as outer_cm:
                with _arm_rig_transaction(self.armature) as tx:
                    outer_tx_ref = tx
                    try:
                        set_arm_ik_influence(self.armature, "L", 0.9)
                    except RuntimeError as caught_inner:
                        self.assertIn("Injected inner nested failure in TEST-119", str(caught_inner))
                    # Verify rollback_only was marked immediately upon inner failure
                    self.assertTrue(tx.rollback_only)
                    self.assertIsNotNone(tx.rollback_only_reason)
                    self.assertIn("Injected inner nested failure in TEST-119", tx.rollback_only_reason)
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNotNone(outer_tx_ref)
        self.assertTrue(outer_tx_ref.rollback_only)
        self.assertIn("rollback_only", str(outer_cm.exception))
        self.assertIn("Injected inner nested failure in TEST-119", str(outer_cm.exception))
        self.assertEqual(outer_tx_ref.state, _ArmRigTransactionState.ROLLED_BACK)
        self.assertEqual(observed_states, [])

        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.4, places=6
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["hand.L"].constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence, 0.4, places=6
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.R"].constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.4, places=6
        )
        self.assertAlmostEqual(
            self.armature.pose.bones["hand.R"].constraints[HAND_ROT_CONSTRAINT_NAMES["R"]].influence, 0.4, places=6
        )

        _verify_arm_rig_state_restored(self.armature, initial_snapshot)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)

    def test_120_multi_level_same_armature_nested_transaction_failure(self) -> None:
        """TEST-120: Multi-level same-Armature nested failure (Outer -> Nested A -> Nested B) propagates rollback_only."""
        setup_arm_ik(self.armature, initial_influence=0.25)
        initial_snapshot = _snapshot_arm_rig_state(self.armature)
        tx_snapshot_calls = [0]
        orig_snapshot_fn = sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state

        def counting_snapshot(arm):
            if _ACTIVE_TRANSACTION_STACK and _ACTIVE_TRANSACTION_STACK[-1].state == _ArmRigTransactionState.SNAPSHOTTING:
                tx_snapshot_calls[0] += 1
            return orig_snapshot_fn(arm)

        sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = counting_snapshot
        outer_tx_ref = None
        try:
            with self.assertRaises(RuntimeError) as outer_cm:
                with _arm_rig_transaction(self.armature) as outer_tx:
                    outer_tx_ref = outer_tx
                    pbone_forearm_l = self.armature.pose.bones["forearm.L"]
                    pbone_hand_l = self.armature.pose.bones["hand.L"]
                    pbone_forearm_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence = 0.6

                    with _arm_rig_transaction(self.armature) as nested_a:
                        self.assertIs(nested_a, outer_tx)
                        self.assertIs(nested_a.snapshot, outer_tx.snapshot)
                        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 1)
                        try:
                            with _arm_rig_transaction(self.armature) as nested_b:
                                self.assertIs(nested_b, outer_tx)
                                self.assertIs(nested_b.snapshot, outer_tx.snapshot)
                                self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 1)
                                pbone_hand_l.constraints[HAND_ROT_CONSTRAINT_NAMES["L"]].influence = 0.85
                                raise RuntimeError("Deep nested B failure in TEST-120")
                        except RuntimeError as caught_b:
                            self.assertIn("Deep nested B failure in TEST-120", str(caught_b))

                        self.assertTrue(outer_tx.rollback_only)
                        self.assertIn("Deep nested B failure in TEST-120", outer_tx.rollback_only_reason)
        finally:
            sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = orig_snapshot_fn

        self.assertEqual(tx_snapshot_calls[0], 1)
        self.assertIsNotNone(outer_tx_ref)
        self.assertTrue(outer_tx_ref.rollback_only)
        self.assertEqual(outer_tx_ref.state, _ArmRigTransactionState.ROLLED_BACK)
        self.assertIn("Deep nested B failure in TEST-120", str(outer_cm.exception))
        _verify_arm_rig_state_restored(self.armature, initial_snapshot)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_121_poisoned_rollback_only_transaction_rejects_subsequent_nested_writes(self) -> None:
        """TEST-121: Poisoned rollback_only transaction rejects subsequent nested entries before body execution."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        initial_snapshot = _snapshot_arm_rig_state(self.armature)
        second_body_executed = [False]

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences":
                raise RuntimeError("First nested failure reason in TEST-121")

        _set_test_fault_injection_hook(fault_hook)
        outer_tx_ref = None
        try:
            with self.assertRaises(RuntimeError) as outer_cm:
                with _arm_rig_transaction(self.armature) as outer_tx:
                    outer_tx_ref = outer_tx
                    try:
                        set_arm_ik_influence(self.armature, "L", 0.9)
                    except RuntimeError:
                        pass

                    self.assertTrue(outer_tx.rollback_only)
                    first_reason = outer_tx.rollback_only_reason
                    self.assertIn("First nested failure reason in TEST-121", first_reason)

                    # Clear fault hook and verify second nested transaction is rejected at admission
                    _clear_test_fault_injection_hook()
                    pbone_r = self.armature.pose.bones["forearm.R"]
                    r_before = pbone_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence

                    with self.assertRaises(RuntimeError) as second_cm:
                        with _arm_rig_transaction(self.armature):
                            second_body_executed[0] = True
                            pbone_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence = 0.99

                    self.assertIn("already marked rollback_only", str(second_cm.exception))
                    self.assertFalse(second_body_executed[0])
                    self.assertAlmostEqual(
                        pbone_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, r_before, places=6
                    )
                    # Also verify public helper using nested transaction is rejected at admission
                    with self.assertRaises(RuntimeError):
                        set_arm_ik_influence(self.armature, "R", 0.99)
                    self.assertAlmostEqual(
                        pbone_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, r_before, places=6
                    )

                    # Verify rollback_only remains True and first failure reason was preserved
                    self.assertTrue(outer_tx.rollback_only)
                    self.assertEqual(outer_tx.rollback_only_reason, first_reason)
        finally:
            _clear_test_fault_injection_hook()

        self.assertIsNotNone(outer_tx_ref)
        self.assertEqual(outer_tx_ref.state, _ArmRigTransactionState.ROLLED_BACK)
        self.assertIn("First nested failure reason in TEST-121", str(outer_cm.exception))
        _verify_arm_rig_state_restored(self.armature, initial_snapshot)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_122_normal_admission_restored_after_rollback(self) -> None:
        """TEST-122: After nested-failure rollback, subsequent transactions on same and second Armature succeed."""
        setup_arm_ik(self.armature, initial_influence=0.35)
        initial_snapshot = _snapshot_arm_rig_state(self.armature)

        # Create an independent second Armature to verify isolation
        arm_b_data = bpy.data.armatures.new("IndependentArmB_122_Data")
        arm_b = bpy.data.objects.new("IndependentArmB_122", arm_b_data)
        bpy.context.scene.collection.objects.link(arm_b)

        try:
            def fault_hook(stage: str, ctx: dict) -> None:
                if stage == "set_arm_ik_influence_between_influences":
                    raise RuntimeError("Transient nested fault in TEST-122")

            _set_test_fault_injection_hook(fault_hook)
            failed_tx = None
            try:
                with self.assertRaises(RuntimeError):
                    with _arm_rig_transaction(self.armature) as tx1:
                        failed_tx = tx1
                        try:
                            set_arm_ik_influence(self.armature, "L", 0.8)
                        except RuntimeError:
                            pass
            finally:
                _clear_test_fault_injection_hook()

            self.assertIsNotNone(failed_tx)
            self.assertEqual(failed_tx.state, _ArmRigTransactionState.ROLLED_BACK)
            _verify_arm_rig_state_restored(self.armature, initial_snapshot)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

            # Start a brand new transaction on the same Armature
            with _arm_rig_transaction(self.armature) as tx2:
                self.assertIsNot(tx2, failed_tx)
                self.assertNotEqual(tx2.tx_id, failed_tx.tx_id)
                self.assertFalse(tx2.rollback_only)
                self.assertIsNone(tx2.rollback_only_reason)
                set_arm_ik_influence(self.armature, "BOTH", 0.65)

            self.assertEqual(tx2.state, _ArmRigTransactionState.COMMITTED)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
            pbone_l = self.armature.pose.bones["forearm.L"]
            pbone_r = self.armature.pose.bones["forearm.R"]
            self.assertAlmostEqual(pbone_l.constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence, 0.65, places=6)
            self.assertAlmostEqual(pbone_r.constraints[ARM_IK_CONSTRAINT_NAMES["R"]].influence, 0.65, places=6)

            # Verify independent second Armature is unaffected and can enter its own transaction
            with _arm_rig_transaction(arm_b) as tx_b:
                self.assertFalse(tx_b.rollback_only)
            self.assertEqual(tx_b.state, _ArmRigTransactionState.COMMITTED)
            self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        finally:
            if arm_b.name in bpy.data.objects:
                bpy.data.objects.remove(arm_b, do_unlink=True)
            if arm_b_data.name in bpy.data.armatures:
                bpy.data.armatures.remove(arm_b_data, do_unlink=True)

    def test_123_uncaught_inner_exception_preserves_historical_propagation_and_rollback(self) -> None:
        """TEST-123: Uncaught inner exception propagates original error directly and triggers single outer rollback."""
        setup_arm_ik(self.armature, initial_influence=0.45)
        initial_snapshot = _snapshot_arm_rig_state(self.armature)
        rollback_calls = [0]
        orig_rollback_fn = sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state

        def counting_rollback(arm, snapshot, tx=None):
            rollback_calls[0] += 1
            return orig_rollback_fn(arm, snapshot, tx)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences":
                raise ValueError("Original uncaught inner ValueError in TEST-123")

        sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state = counting_rollback
        _set_test_fault_injection_hook(fault_hook)
        outer_tx_ref = None
        try:
            with self.assertRaises(ValueError) as cm:
                with _arm_rig_transaction(self.armature) as outer_tx:
                    outer_tx_ref = outer_tx
                    set_arm_ik_influence(self.armature, "L", 0.95)
        finally:
            _clear_test_fault_injection_hook()
            sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state = orig_rollback_fn

        self.assertEqual(str(cm.exception), "Original uncaught inner ValueError in TEST-123")
        self.assertIsNotNone(outer_tx_ref)
        self.assertTrue(outer_tx_ref.rollback_only)
        self.assertIn("Original uncaught inner ValueError in TEST-123", outer_tx_ref.rollback_only_reason)
        self.assertEqual(outer_tx_ref.state, _ArmRigTransactionState.ROLLED_BACK)
        self.assertEqual(rollback_calls[0], 1)
        _verify_arm_rig_state_restored(self.armature, initial_snapshot)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    # -------------------------------------------------------------------------
    # Task 10-B-13 FAILED Classification, Session Identity & Recovery Admission Tests (TEST-124 to TEST-136)
    # -------------------------------------------------------------------------

    def test_124_failed_a_pre_write_snapshot_abort_verified_zero_mutation_no_isolation(self) -> None:
        """TEST-124: FAILED-A pre-write snapshot abort with verified zero mutation does not isolate healthy Armature."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        snap_before = _snapshot_arm_rig_state(self.armature)
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                raise RuntimeError("Injected pre-write snapshot fault in TEST-124")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.5)
            self.assertIn("Injected pre-write snapshot fault in TEST-124", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_A.value)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # FAILED-A must NOT isolate the healthy Armature
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.NONE)
        self.assertEqual(session_rec.liveness_status, _ArmatureLivenessStatus.ALIVE_VERIFIED)
        self.assertGreaterEqual(len(_FAILED_A_AUDIT_RECORDS), 1)
        self.assertEqual(_FAILED_A_AUDIT_RECORDS[-1]["transaction_id"], tx.tx_id)
        self.assertEqual(_FAILED_A_AUDIT_RECORDS[-1]["registry_session_id"], session_id)
        self.assertEqual(_FAILED_A_AUDIT_RECORDS[-1]["failure_class"], "FAILED-A")
        _verify_arm_rig_state_restored(self.armature, snap_before)

        # Subsequent write transaction on the same Armature must be admitted and commit normally
        controls = setup_arm_ik(self.armature, initial_influence=0.6)
        self.assertIsNotNone(controls)
        gate_status = query_admission_gate_status(arm=self.armature)
        self.assertTrue(gate_status["can_admit"])
        self.assertFalse(gate_status["failed_isolation_blocked"])

    def test_125_pre_write_abort_without_zero_mutation_proof_isolated_as_failed_c(self) -> None:
        """TEST-125: Pre-ACTIVE abort without zero-mutation proof or trusted snapshot is isolated as FAILED-C."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                tx = ctx.get("tx")
                if tx is not None:
                    captured_tx.append(tx)
                # Mutate pose bone before snapshot completes so pre-write zero-mutation proof fails while tx.snapshot is None
                self.armature.pose.bones["forearm.L"].location.x += 0.25
                raise RuntimeError("Pre-write fault with unverified mutation in TEST-125")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature)
            err_msg = str(cm.exception)
            self.assertIn("Pre-write fault with unverified mutation in TEST-125", err_msg)
            self.assertIn("FAILED-C", err_msg)
            self.assertIn(session_id, err_msg)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertIsNone(tx.snapshot)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Must be isolated as FAILED-C with snapshot_trusted=False and RECOVERY_EVIDENCE_INSUFFICIENT
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        iso_rec = _ISOLATED_FAILED_ARMATURES[session_id]
        self.assertEqual(iso_rec["failure_class"], "FAILED-C")
        self.assertEqual(iso_rec["isolation_state"], "ISOLATED_FAILED_C")
        self.assertIsNone(iso_rec["snapshot_reference"])
        self.assertFalse(iso_rec["snapshot_trusted"])
        self.assertEqual(iso_rec["evidence_status"], "RECOVERY_EVIDENCE_INSUFFICIENT")

        # Subsequent write transaction must be rejected by FAILED Isolation Gate before SNAPSHOTTING
        with self.assertRaises(RuntimeError) as cm_gate:
            setup_arm_ik(self.armature)
        self.assertIn("FAILED-C", str(cm_gate.exception))
        self.assertIn(tx.tx_id, str(cm_gate.exception))
        self.assertIn(session_id, str(cm_gate.exception))

    def test_126_failed_b_rollback_execution_failure_records_isolation(self) -> None:
        """TEST-126: FAILED-B rollback execution exception isolates Armature in _ISOLATED_FAILED_ARMATURES."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                captured_tx.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-126")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Secondary rollback execution fault in TEST-126")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20), influence=0.85)
            self.assertIn("Primary write fault in TEST-126", str(cm.exception))
            self.assertIn("Secondary rollback execution fault in TEST-126", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_B.value)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)
        iso_rec = _ISOLATED_FAILED_ARMATURES[session_id]
        self.assertEqual(iso_rec["registry_session_id"], session_id)
        self.assertEqual(iso_rec["transaction_id"], tx.tx_id)
        self.assertEqual(iso_rec["failure_class"], "FAILED-B")
        self.assertEqual(iso_rec["isolation_state"], "ISOLATED_FAILED_B")
        self.assertEqual(iso_rec["liveness_status"], "ALIVE_VERIFIED")
        self.assertEqual(iso_rec["registration_pointer"], self.armature.as_pointer())
        self.assertEqual(iso_rec["original_data_pointer"], self.armature.data.as_pointer())
        self.assertIn("Primary write fault in TEST-126", iso_rec["primary_exception"])
        self.assertIn("Secondary rollback execution fault in TEST-126", iso_rec["secondary_exception"])
        self.assertIsNotNone(iso_rec["snapshot_reference"])
        self.assertTrue(iso_rec["snapshot_trusted"])

        # Subsequent write call must be blocked before SNAPSHOTTING
        with self.assertRaises(RuntimeError) as cm_block:
            set_arm_ik_influence(self.armature, "L", 0.5)
        self.assertIn("FAILED-B", str(cm_block.exception))
        self.assertIn(tx.tx_id, str(cm_block.exception))
        self.assertIn(session_id, str(cm_block.exception))

    def test_127_failed_c_rollback_verification_or_recovery_uncertain_records_isolation(self) -> None:
        """TEST-127: FAILED-C post-rollback verification failure or RECOVERY_UNCERTAIN isolates Armature."""
        # Part A: Post-rollback verification failure
        setup_arm_ik(self.armature, initial_influence=0.3)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx_a = []

        def fault_hook_a(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                captured_tx_a.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-127A")
            elif stage == "during_rollback_verification":
                raise RuntimeError("Post-rollback verifier discrepancy in TEST-127A")

        _set_test_fault_injection_hook(fault_hook_a)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError) as cm_a:
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15), influence=0.8)
            self.assertIn("Primary write fault in TEST-127A", str(cm_a.exception))
            self.assertIn("Post-rollback verifier discrepancy in TEST-127A", str(cm_a.exception))
        finally:
            _clear_test_fault_injection_hook()

        tx_a = captured_tx_a[0]
        self.assertEqual(tx_a.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx_a.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_ISOLATED_FAILED_ARMATURES[session_id]["failure_class"], "FAILED-C")

        # De-isolate Part A after verification so we can test Part B on the same Armature
        deiso_a = request_armature_deisolation(self.armature, reason="Clear Part A in TEST-127")
        self.assertTrue(deiso_a["approved"])

        # Part B: Relationship operation log RECOVERY_UNCERTAIN during rollback
        char_col = bpy.data.collections["Character"]
        hand_r = bpy.data.objects["HandIK.R"]
        char_col.objects.unlink(hand_r)
        captured_tx_b = []

        def fault_hook_b(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_constraints_or_prebend" and ctx.get("side") == "R":
                captured_tx_b.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary fault in TEST-127B")
            elif stage == "during_relationship_rollback_undo":
                op = ctx.get("op", {})
                if op.get("target_identity", {}).get("name") == "HandIK.R":
                    raise RuntimeError("Relationship undo failure in TEST-127B")

        _set_test_fault_injection_hook(fault_hook_b)
        try:
            with self.assertRaises(RuntimeError) as cm_b:
                setup_arm_ik(self.armature, initial_influence=0.9)
            self.assertIn("Primary fault in TEST-127B", str(cm_b.exception))
            self.assertIn("RECOVERY_UNCERTAIN", str(cm_b.exception))
        finally:
            _clear_test_fault_injection_hook()

        tx_b = captured_tx_b[0]
        self.assertEqual(tx_b.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx_b.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        iso_b = _ISOLATED_FAILED_ARMATURES[session_id]
        self.assertEqual(iso_b["failure_class"], "FAILED-C")
        self.assertEqual(len(iso_b["recovery_uncertain_operations"]), 1)

    def test_128_isolated_armature_renamed_still_rejected_before_snapshotting(self) -> None:
        """TEST-128: Isolated Armature renamed after FAILED-B/C is still recognized by session identity and rejected before SNAPSHOTTING."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        session_rec = ensure_armature_session_identity(self.armature)
        orig_session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                captured_tx.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary fault in TEST-128")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback fault in TEST-128")

        _set_test_fault_injection_hook(fault_hook)
        y_pos = self.root.location.y + 0.15
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20), influence=0.8)
        finally:
            _clear_test_fault_injection_hook()

        tx = captured_tx[0]
        # Rename both the Armature Object and its Armature DataBlock
        self.armature.name = "CharacterArmature_Renamed_128"
        self.armature.data.name = "ArmatureData_Renamed_128"

        # Session identity must remain identical after rename
        resolved_after_rename = ensure_armature_session_identity(self.armature)
        self.assertIs(resolved_after_rename, session_rec)
        self.assertEqual(resolved_after_rename.registry_session_id, orig_session_id)

        # Count snapshot invocations to prove rejection happens strictly BEFORE SNAPSHOTTING
        snapshot_calls = [0]
        orig_snapshot_fn = sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state

        def counting_snapshot(arm):
            snapshot_calls[0] += 1
            return orig_snapshot_fn(arm)

        sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = counting_snapshot
        try:
            for write_fn in (
                lambda: setup_arm_ik(self.armature),
                lambda: set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.15)),
                lambda: set_arm_ik_influence(self.armature, "BOTH", 0.2),
                lambda: reset_arm_ik(self.armature),
            ):
                with self.assertRaises(RuntimeError) as cm_gate:
                    write_fn()
                err = str(cm_gate.exception)
                self.assertIn("FAILED-B", err)
                self.assertIn(tx.tx_id, err)
                self.assertIn(orig_session_id, err)
        finally:
            sys.modules["src.rig.arm_ik"]._snapshot_arm_rig_state = orig_snapshot_fn

        self.assertEqual(snapshot_calls[0], 0)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

    def test_129_other_healthy_armature_unaffected_by_isolated_armature(self) -> None:
        """TEST-129: Other healthy Armature executes transactions normally while Armature A is isolated."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        session_a = ensure_armature_session_identity(self.armature)

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences":
                raise RuntimeError("Primary fault on Armature A in TEST-129")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback fault on Armature A in TEST-129")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                set_arm_ik_influence(self.armature, "L", 0.9)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(session_a.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)
        self.assertIn(session_a.registry_session_id, _ISOLATED_FAILED_ARMATURES)

        # Build independent Armature B with the 6 required upper-limb bones
        arm_b_data = bpy.data.armatures.new("ArmB_Data_129")
        arm_b = bpy.data.objects.new("CharacterArmature_B_129", arm_b_data)
        bpy.context.scene.collection.objects.link(arm_b)
        bpy.context.view_layer.objects.active = arm_b
        bpy.ops.object.mode_set(mode="EDIT")
        for b_name in ("upper_arm.L", "upper_arm.R", "forearm.L", "forearm.R", "hand.L", "hand.R"):
            eb = arm_b_data.edit_bones.new(b_name)
            eb.head = (0.0, 0.0, 1.0)
            eb.tail = (0.0, 0.0, 1.25)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.context.view_layer.objects.active = self.armature
        bpy.context.view_layer.update()

        try:
            session_b = ensure_armature_session_identity(arm_b)
            self.assertNotEqual(session_b.registry_session_id, session_a.registry_session_id)
            self.assertEqual(session_b.isolation_state, _ArmatureIsolationState.NONE)

            with _arm_rig_transaction(arm_b) as tx_b:
                arm_b.pose.bones["forearm.L"].location.y = 0.05
            self.assertEqual(tx_b.state, _ArmRigTransactionState.COMMITTED)
            self.assertAlmostEqual(arm_b.pose.bones["forearm.L"].location.y, 0.05, places=6)

            # Armature A remains isolated and blocked
            self.assertIn(session_a.registry_session_id, _ISOLATED_FAILED_ARMATURES)
            with self.assertRaises(RuntimeError) as cm_a:
                set_arm_ik_influence(self.armature, "L", 0.2)
            self.assertIn(session_a.registry_session_id, str(cm_a.exception))
        finally:
            if arm_b.name in bpy.data.objects:
                bpy.data.objects.remove(arm_b, do_unlink=True)
            if arm_b_data.name in bpy.data.armatures:
                bpy.data.armatures.remove(arm_b_data, do_unlink=True)

    def test_130_failed_d_armature_destroyed_during_active_records_tombstone_without_rollback(self) -> None:
        """TEST-130: FAILED-D Armature destroyed during ACTIVE skips rollback on dead object, records tombstone, and isolates from same-name replacement."""
        session_orig = ensure_armature_session_identity(self.armature)
        orig_session_id = session_orig.registry_session_id
        orig_arm_ptr = session_orig.registration_pointer
        orig_data_ptr = session_orig.original_data_pointer

        rollback_calls = [0]
        orig_rollback_fn = sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state

        def counting_rollback(arm, snapshot, tx=None):
            rollback_calls[0] += 1
            return orig_rollback_fn(arm, snapshot, tx)

        sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state = counting_rollback
        captured_tx = []
        try:
            with self.assertRaises(RuntimeError) as cm:
                with _arm_rig_transaction(self.armature) as tx:
                    captured_tx.append(tx)
                    bpy.data.objects.remove(self.armature, do_unlink=True)
                    raise RuntimeError("Armature destroyed inside ACTIVE in TEST-130")
            err_msg = str(cm.exception)
            self.assertIn("Armature destroyed inside ACTIVE in TEST-130", err_msg)
            self.assertIn(orig_session_id, err_msg)
        finally:
            sys.modules["src.rig.arm_ik"]._rollback_arm_rig_state = orig_rollback_fn

        # Must NOT have executed _rollback_arm_rig_state on the dead Armature
        self.assertEqual(rollback_calls[0], 0)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_D.value)

        # Verify Tombstone state
        self.assertEqual(session_orig.liveness_status, _ArmatureLivenessStatus.INVALIDATED_DEAD)
        self.assertFalse(session_orig.in_live_blender_collection)
        self.assertEqual(session_orig.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)
        self.assertIsNotNone(session_orig.tombstone_record)
        self.assertIn(orig_session_id, _ISOLATED_FAILED_ARMATURES)
        iso_rec = _ISOLATED_FAILED_ARMATURES[orig_session_id]
        self.assertEqual(iso_rec["failure_class"], "FAILED-D")
        self.assertEqual(iso_rec["isolation_state"], "TOMBSTONED_FAILED_D")
        self.assertEqual(iso_rec["registration_pointer"], orig_arm_ptr)
        self.assertEqual(iso_rec["original_data_pointer"], orig_data_ptr)

        # Create a new Armature with the exact same name "CharacterArmature"
        new_arm = build_rig(self.config)
        self.assertEqual(new_arm.name, "CharacterArmature")
        session_new = ensure_armature_session_identity(new_arm)
        self.assertNotEqual(session_new.registry_session_id, orig_session_id)
        self.assertEqual(session_new.isolation_state, _ArmatureIsolationState.NONE)

        # Old tombstone remains in _ISOLATED_FAILED_ARMATURES untouched
        self.assertIn(orig_session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_ISOLATED_FAILED_ARMATURES[orig_session_id]["isolation_state"], "TOMBSTONED_FAILED_D")

    def test_131_verified_recovery_deisolates_failed_b_and_failed_c_and_restores_admission(self) -> None:
        """TEST-131: Full recovery verification de-isolates FAILED-B and FAILED-C Armature and restores write admission."""
        setup_arm_ik(self.armature, initial_influence=0.35)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        y_pos = self.root.location.y + 0.15

        # Part A: FAILED-B -> manual restoration -> verified de-isolation -> new write commits
        captured_tx_b = []

        def fault_hook_b(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                captured_tx_b.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-131A")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback execution fault in TEST-131A")

        _set_test_fault_injection_hook(fault_hook_b)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20), influence=0.8)
        finally:
            _clear_test_fault_injection_hook()

        tx_b = captured_tx_b[0]
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)

        # Restore scene to match tx_b.snapshot
        _rollback_arm_rig_state(self.armature, tx_b.snapshot, tx_b)
        _depsgraph_update()

        res_b = request_armature_deisolation(self.armature, reason="Restored state verified in TEST-131A")
        self.assertTrue(res_b["approved"])
        self.assertEqual(res_b["isolation_state"], "NONE")
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.NONE)
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["decision"], "APPROVED")
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["registry_session_id"], session_id)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["transaction_id"], tx_b.tx_id)

        # Verify write admission is restored
        state_after_b = set_hand_ik_target(self.armature, side="L", world_xyz=(-0.30, y_pos, 1.18), influence=0.75)
        self.assertIsNotNone(state_after_b)

        # Part B: FAILED-C -> verified de-isolation -> new write commits
        captured_tx_c = []

        def fault_hook_c(stage: str, ctx: dict) -> None:
            if stage == "set_arm_ik_influence_between_influences":
                captured_tx_c.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-131B")
            elif stage == "during_rollback_verification":
                raise RuntimeError("Verification fault in TEST-131B")

        _set_test_fault_injection_hook(fault_hook_c)
        try:
            with self.assertRaises(RuntimeError):
                set_arm_ik_influence(self.armature, "L", 0.95)
        finally:
            _clear_test_fault_injection_hook()

        tx_c = captured_tx_c[0]
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)

        res_c = request_armature_deisolation(self.armature, reason="Post-rollback state verified in TEST-131B")
        self.assertTrue(res_c["approved"])
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.NONE)
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["decision"], "APPROVED")
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["transaction_id"], tx_c.tx_id)

        set_arm_ik_influence(self.armature, "BOTH", 0.55)
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence,
            0.55,
            places=5,
        )

    def test_132_incomplete_recovery_deisolation_rejected_with_audit_log(self) -> None:
        """TEST-132: De-isolation request is rejected when scene state has not been fully restored to snapshot."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        y_pos = self.root.location.y + 0.15

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Primary write fault in TEST-132")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Abort rollback before restoring HandIK.L location in TEST-132")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.35, y_pos, 1.25), influence=0.9)
        finally:
            _clear_test_fault_injection_hook()

        # HandIK.L location is still mutated because rollback aborted at start
        res = request_armature_deisolation(self.armature, reason="Premature deisolation attempt in TEST-132")
        self.assertFalse(res["approved"])
        self.assertEqual(res["action"], "REJECTED")
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["decision"], "REJECTED")
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["registry_session_id"], session_id)
        self.assertEqual(res["evidence"]["status"], "RECOVERY_VERIFICATION_FAILED")

        # Confirm raise_on_reject=True raises RuntimeError
        with self.assertRaises(RuntimeError) as cm_rej:
            request_armature_deisolation(
                self.armature,
                reason="Premature deisolation with raise_on_reject",
                raise_on_reject=True,
            )
        self.assertIn("RECOVERY_VERIFICATION_FAILED", str(cm_rej.exception))

        # Write admission remains blocked
        with self.assertRaises(RuntimeError) as cm_gate:
            set_arm_ik_influence(self.armature, "L", 0.1)
        self.assertIn("FAILED-B", str(cm_gate.exception))

    def test_133_missing_snapshot_deisolation_rejected_as_recovery_evidence_insufficient(self) -> None:
        """TEST-133: Missing trusted snapshot returns RECOVERY_EVIDENCE_INSUFFICIENT and rejects de-isolation even if structure looks normal."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        orig_loc_x = self.armature.pose.bones["forearm.L"].location.x

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                self.armature.pose.bones["forearm.L"].location.x += 0.15
                raise RuntimeError("Snapshot aborted after bone mutation in TEST-133")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                setup_arm_ik(self.armature)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIsNone(_ISOLATED_FAILED_ARMATURES[session_id]["snapshot_reference"])
        self.assertFalse(_ISOLATED_FAILED_ARMATURES[session_id]["snapshot_trusted"])

        # Manually restore bone location so the live Armature looks completely normal
        self.armature.pose.bones["forearm.L"].location.x = orig_loc_x
        _depsgraph_update()

        # Layer 5 must still report RECOVERY_EVIDENCE_INSUFFICIENT because no trusted snapshot exists
        evidence = verify_armature_deisolation_evidence(arm=self.armature)
        self.assertFalse(evidence["can_deisolate"])
        self.assertEqual(evidence["status"], "RECOVERY_EVIDENCE_INSUFFICIENT")
        self.assertEqual(evidence["case"], "CASE_2_NO_TRUSTED_SNAPSHOT")

        res = request_armature_deisolation(self.armature, reason="Attempt deisolation without snapshot in TEST-133")
        self.assertFalse(res["approved"])
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["decision"], "REJECTED")
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["verification_status"], "RECOVERY_EVIDENCE_INSUFFICIENT")

    def test_134_direct_isolation_dict_tampering_without_coordinator_verification_rejected(self) -> None:
        """TEST-134: Direct tampering with _ISOLATED_FAILED_ARMATURES or calling Layer 2 without verified evidence cannot bypass isolation."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        y_pos = self.root.location.y + 0.15

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                raise RuntimeError("Primary write fault in TEST-134")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback fault in TEST-134")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.33, y_pos, 1.22), influence=0.85)
        finally:
            _clear_test_fault_injection_hook()

        # 1. Calling Layer 2 _clear_or_retire_failure_isolation_by_coordinator with unverified evidence must raise RuntimeError
        with self.assertRaises(RuntimeError) as cm_l2:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id=session_id,
                action="CLEAR_TO_NONE",
                reason="Bypass attempt",
                verification_evidence={"can_deisolate": False},
            )
        self.assertIn("Layer 2 rejected de-isolation", str(cm_l2.exception))

        # 2. Directly popping from _ISOLATED_FAILED_ARMATURES without Coordinator de-isolation leaves session_rec.isolation_state == ISOLATED_FAILED_B
        saved_iso_entry = _ISOLATED_FAILED_ARMATURES.pop(session_id)
        try:
            self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)
            with self.assertRaises(RuntimeError) as cm_gate:
                set_arm_ik_influence(self.armature, "L", 0.3)
            self.assertIn("ISOLATED_FAILED_B", str(cm_gate.exception))
            self.assertIn(session_id, str(cm_gate.exception))
        finally:
            _ISOLATED_FAILED_ARMATURES[session_id] = saved_iso_entry

    def test_135_failed_d_tombstone_cannot_return_to_active_and_retires_to_archived(self) -> None:
        """TEST-135: FAILED-D tombstone rejects de-isolation, verifies residual objects before retirement, and transitions to ARCHIVED_RETIRED."""
        session_dead = ensure_armature_session_identity(self.armature)
        dead_session_id = session_dead.registry_session_id

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                # HandIK.L has been created and registered on tx; now destroy the Armature
                bpy.data.objects.remove(self.armature, do_unlink=True)
                raise RuntimeError("Armature destroyed after HandIK.L creation in TEST-135")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError):
                setup_arm_ik(self.armature)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(session_dead.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)
        self.assertIn(dead_session_id, _ISOLATED_FAILED_ARMATURES)

        # Create a replacement Armature with the same name "CharacterArmature"
        replacement_arm = build_rig(self.config)
        self.assertEqual(replacement_arm.name, "CharacterArmature")
        session_replacement = ensure_armature_session_identity(replacement_arm)
        self.assertNotEqual(session_replacement.registry_session_id, dead_session_id)

        # 1. Attempting to de-isolate the dead session (even passing replacement_arm) must be rejected
        deiso_attempt = request_armature_deisolation(
            replacement_arm,
            reason="Attempt to revive FAILED-D tombstone in TEST-135",
            session_id=dead_session_id,
        )
        self.assertFalse(deiso_attempt["approved"])
        self.assertEqual(deiso_attempt["evidence"]["status"], "REJECTED_DEAD_ARMATURE_TOMBSTONE")
        self.assertEqual(session_dead.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)

        # 2. Attempting to retire tombstone while residual transaction-created HandIK.L still exists must be rejected
        self.assertIsNotNone(bpy.data.objects.get("HandIK.L"))
        retire_early = retire_dead_armature_tombstone(
            dead_session_id,
            reason="Attempt retirement while residual HandIK.L exists in TEST-135",
        )
        self.assertFalse(retire_early["approved"])
        self.assertEqual(retire_early["evidence"]["status"], "TOMBSTONE_RETIREMENT_REJECTED")
        self.assertEqual(session_dead.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)
        self.assertIn(dead_session_id, _ISOLATED_FAILED_ARMATURES)

        # 3. Clean up residual transaction-created HandIK.L, then retire tombstone
        bpy.data.objects.remove(bpy.data.objects["HandIK.L"], do_unlink=True)
        retire_ok = retire_dead_armature_tombstone(
            dead_session_id,
            reason="All residual resources cleaned in TEST-135",
        )
        self.assertTrue(retire_ok["approved"])
        self.assertEqual(retire_ok["action"], "ARCHIVED_RETIRED")
        self.assertEqual(session_dead.isolation_state, _ArmatureIsolationState.ARCHIVED_RETIRED)
        self.assertEqual(session_dead.lifecycle_stage, "ARCHIVED_RETIRED")
        self.assertNotIn(dead_session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertIn(dead_session_id, _ARCHIVED_FAILED_D_TOMBSTONES)
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["decision"], "APPROVED")
        self.assertEqual(_DEISOLATION_AUDIT_LOG[-1]["operation"], "RETIRE_DEAD_TOMBSTONE")

        # 4. Archived tombstone can never be revived to active status
        revive_archived = request_armature_deisolation(
            None,
            reason="Attempt to revive ARCHIVED_RETIRED tombstone",
            session_id=dead_session_id,
        )
        self.assertFalse(revive_archived["approved"])
        self.assertEqual(revive_archived["evidence"]["status"], "REJECTED_ARCHIVED_TOMBSTONE")

        # 5. Replacement Armature operates cleanly under its own session identity
        controls_new = setup_arm_ik(replacement_arm, initial_influence=0.5)
        self.assertIsNotNone(controls_new)

    def test_136_cleanup_pending_and_failed_isolation_strictly_separated(self) -> None:
        """TEST-136: CLEANUP_PENDING and FAILED isolation remain strictly separated without cross-clearing or FAILED -> COMMITTED."""
        setup_arm_ik(self.armature, initial_influence=0.4)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        y_pos = self.root.location.y + 0.15

        # 1. Trigger FAILED-B transaction
        captured_failed_tx = []

        def fault_hook_failed(stage: str, ctx: dict) -> None:
            if stage == "set_hand_ik_target_after_hand_location":
                captured_failed_tx.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-136")
            elif stage == "during_rollback_execution":
                raise RuntimeError("Rollback fault in TEST-136")

        _set_test_fault_injection_hook(fault_hook_failed)
        try:
            with self.assertRaises(RuntimeError):
                set_hand_ik_target(self.armature, side="L", world_xyz=(-0.32, y_pos, 1.20), influence=0.8)
        finally:
            _clear_test_fault_injection_hook()

        tx_failed = captured_failed_tx[0]
        self.assertEqual(tx_failed.state, _ArmRigTransactionState.FAILED)

        # retry_pending_arm_rig_cleanup and tx.retry_cleanup() must reject FAILED transactions and never transition FAILED -> COMMITTED
        with self.assertRaises(RuntimeError) as cm_retry1:
            retry_pending_arm_rig_cleanup(tx_failed.tx_id)
        self.assertIn("FAILED", str(cm_retry1.exception))
        with self.assertRaises(RuntimeError) as cm_retry2:
            tx_failed.retry_cleanup()
        self.assertIn("FAILED -> COMMITTED transition is strictly forbidden", str(cm_retry2.exception))
        self.assertEqual(tx_failed.state, _ArmRigTransactionState.FAILED)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        # Restore scene and de-isolate so we can create a real CLEANUP_PENDING record
        _rollback_arm_rig_state(self.armature, tx_failed.snapshot, tx_failed)
        _depsgraph_update()
        self.assertTrue(request_armature_deisolation(self.armature, reason="Restore before cleanup test in TEST-136")["approved"])

        # 2. Trigger a real CLEANUP_PENDING transaction on self.armature
        old_hand = bpy.data.objects["HandIK.L"]
        bpy.data.objects.remove(old_hand, do_unlink=True)
        doomed_mesh = bpy.data.meshes.new("DoomedMesh136")
        wrong_obj = bpy.data.objects.new("HandIK.L", doomed_mesh)
        bpy.data.collections["Character"].objects.link(wrong_obj)

        def fault_hook_cleanup(stage: str, ctx: dict) -> None:
            if stage == "during_commit_cleanup":
                raise RuntimeError("Phase 3 cleanup failure in TEST-136")

        _set_test_fault_injection_hook(fault_hook_cleanup)
        try:
            with self.assertRaises(RuntimeError):
                setup_arm_ik(self.armature)
        finally:
            _clear_test_fault_injection_hook()

        pending_ids = get_pending_arm_rig_cleanup_ids()
        self.assertEqual(len(pending_ids), 1)
        cleanup_tx_id = pending_ids[0]
        cleanup_tx = _PENDING_ARM_RIG_CLEANUPS[cleanup_tx_id]

        # 3. Also record a FAILED-C isolation on the same Armature (simulating coexistence of CLEANUP_PENDING and FAILED)
        snap_current = _snapshot_arm_rig_state(self.armature)
        coexisting_failed_tx = _ArmRigTransactionContext(self.armature, session_record=session_rec)
        coexisting_failed_tx.state = _ArmRigTransactionState.FAILED
        coexisting_failed_tx.snapshot = snap_current
        from src.rig.arm_ik import _record_armature_failure_isolation_by_coordinator
        _record_armature_failure_isolation_by_coordinator(
            session_rec=session_rec,
            tx=coexisting_failed_tx,
            failure_class=_FailedTransactionClass.FAILED_C,
            primary_exception=RuntimeError("Coexisting FAILED-C in TEST-136"),
            secondary_exception=RuntimeError("Verifier fault in TEST-136"),
            evidence_status="SNAPSHOT_AVAILABLE",
        )

        # De-isolation must be rejected while CLEANUP_PENDING is unresolved (Case 1 Condition 8), and must NOT clear _PENDING_ARM_RIG_CLEANUPS
        deiso_while_cleanup = request_armature_deisolation(
            self.armature,
            reason="Attempt deisolation while CLEANUP_PENDING exists in TEST-136",
        )
        self.assertFalse(deiso_while_cleanup["approved"])
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 1)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        # Resolving CLEANUP_PENDING via retry_pending_arm_rig_cleanup transitions cleanup_tx -> COMMITTED,
        # but must NOT clear FAILED isolation!
        retry_pending_arm_rig_cleanup(cleanup_tx_id)
        self.assertEqual(cleanup_tx.state, _ArmRigTransactionState.COMMITTED)
        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)

        # New write is STILL blocked by Gate 2 (FAILED Isolation Gate)
        with self.assertRaises(RuntimeError) as cm_still_blocked:
            set_arm_ik_influence(self.armature, "L", 0.5)
        self.assertIn("FAILED-C", str(cm_still_blocked.exception))

        # Now de-isolate FAILED-C after CLEANUP_PENDING has been resolved
        deiso_final = request_armature_deisolation(
            self.armature,
            reason="De-isolate after CLEANUP_PENDING resolved in TEST-136",
        )
        self.assertTrue(deiso_final["approved"])
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.NONE)
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)

        # Now new write passes both gates and commits cleanly
        set_arm_ik_influence(self.armature, "BOTH", 0.7)
        self.assertAlmostEqual(
            self.armature.pose.bones["forearm.L"].constraints[ARM_IK_CONSTRAINT_NAMES["L"]].influence,
            0.7,
            places=5,
        )

    # -------------------------------------------------------------------------
    # Audit Corrections Tests (TEST-137 to TEST-149)
    # -------------------------------------------------------------------------

    def test_137_sub_micro_pose_mutation_detected_without_rounding_isolated_as_failed_c(self) -> None:
        """TEST-137: Sub-micro pose mutation (2e-7) during snapshot is NOT masked by rounding and isolates as FAILED-C."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                pbone = self.armature.pose.bones["forearm.L"]
                pbone.location[0] += 2e-7
                raise RuntimeError("Injected sub-micro mutation fault in TEST-137")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.5)
            self.assertIn("classified as FAILED-C", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Subsequent write is strictly blocked by Gate 2 (FAILED Isolation Gate)
        with self.assertRaises(RuntimeError) as cm_blocked:
            set_arm_ik_influence(self.armature, "L", 0.7)
        self.assertIn("FAILED-C", str(cm_blocked.exception))

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-137"] = {
            "test_method": "test_137_sub_micro_pose_mutation_detected_without_rounding_isolated_as_failed_c",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "REJECTED_BEFORE_SNAPSHOTTING",
            "mutation_detected": "sub_micro_pose_delta_2e-7",
        }

    def test_138_constraint_pole_angle_mutation_detected_and_isolated_as_failed_c(self) -> None:
        """TEST-138: Mutation to constraint pole_angle during snapshot is detected by unrounded fingerprint and isolates as FAILED-C."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                con = self.armature.pose.bones["forearm.L"].constraints.get(ARM_IK_CONSTRAINT_NAMES["L"])
                if con is not None:
                    con.pole_angle += 0.05
                raise RuntimeError("Injected constraint mutation fault in TEST-138")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                reset_arm_ik(self.armature)
            self.assertIn("classified as FAILED-C", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-138"] = {
            "test_method": "test_138_constraint_pole_angle_mutation_detected_and_isolated_as_failed_c",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "REJECTED_BEFORE_SNAPSHOTTING",
            "mutation_detected": "constraint_pole_angle_delta_0.05",
        }

    def test_139_controller_matrix_parent_inverse_mutation_detected_and_isolated_as_failed_c(self) -> None:
        """TEST-139: Mutation to controller matrix_parent_inverse during snapshot is detected and isolates as FAILED-C."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                c_obj = bpy.data.objects.get(ARM_IK_TARGET_NAMES["L"])
                if c_obj is not None:
                    mat = c_obj.matrix_parent_inverse.copy()
                    mat[0][3] += 0.05
                    c_obj.matrix_parent_inverse = mat
                raise RuntimeError("Injected matrix_parent_inverse mutation fault in TEST-139")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                reset_arm_ik(self.armature)
            self.assertIn("classified as FAILED-C", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-139"] = {
            "test_method": "test_139_controller_matrix_parent_inverse_mutation_detected_and_isolated_as_failed_c",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "REJECTED_BEFORE_SNAPSHOTTING",
            "mutation_detected": "controller_matrix_parent_inverse_delta_0.05",
        }

    def test_140_clean_snapshot_abort_genuine_zero_mutation_classified_as_failed_a(self) -> None:
        """TEST-140: Clean snapshot abort with genuine zero mutation verifies as FAILED-A without isolating healthy Armature."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_snapshot_creation":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                raise RuntimeError("Clean pre-write snapshot abort in TEST-140")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.5)
            self.assertIn("Clean pre-write snapshot abort in TEST-140", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_A.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.NONE)
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Subsequent write must be admitted and succeed cleanly
        controls = setup_arm_ik(self.armature, initial_influence=0.6)
        self.assertIsNotNone(controls)
        self.assertEqual(session_rec.lifecycle_stage, "NORMAL_TERMINAL")

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-140"] = {
            "test_method": "test_140_clean_snapshot_abort_genuine_zero_mutation_classified_as_failed_a",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "ADMITTED_AND_COMMITTED",
            "recovery_result": "PRE_WRITE_ZERO_MUTATION_VERIFIED",
        }

    def test_141_pre_snapshot_fingerprint_capture_failure_fails_closed(self) -> None:
        """TEST-141: Pre-snapshot fingerprint capture failure fails closed, isolates as FAILED-C, and leaves no stack leak."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "during_pre_snapshot_fingerprint":
                if ctx.get("tx") is not None:
                    captured_tx.append(ctx["tx"])
                raise RuntimeError("Injected fingerprint capture fault in TEST-141")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.5)
            self.assertIn("classified as FAILED-C", str(cm.exception))
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        self.assertEqual(tx.state, _ArmRigTransactionState.FAILED)
        self.assertEqual(tx.failure_class, _FailedTransactionClass.FAILED_C.value)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)

        # Subsequent write blocked
        with self.assertRaises(RuntimeError) as cm_blocked:
            setup_arm_ik(self.armature)
        self.assertIn("FAILED-C", str(cm_blocked.exception))

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-141"] = {
            "test_method": "test_141_pre_snapshot_fingerprint_capture_failure_fails_closed",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "REJECTED_BEFORE_SNAPSHOTTING",
            "recovery_result": "ISOLATED_WITH_RECOVERY_EVIDENCE_INSUFFICIENT",
        }

    def test_142_armature_alive_with_replaced_datablock_cannot_retire_tombstone(self) -> None:
        """TEST-142: Armature object physically alive with replaced DataBlock cannot retire tombstone (ObjectExists == True)."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Replace armature data block (invalidating session identity while object still physically exists)
        new_arm_data = bpy.data.armatures.new("SubstitutedArmatureData_142")
        self.armature.data = new_arm_data

        # Attempting write triggers admission rejection (Condition 7 fails), isolating as FAILED-D
        with self.assertRaises(RuntimeError) as cm_admission:
            setup_arm_ik(self.armature)
        self.assertIn("FAILED-D", str(cm_admission.exception))
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)

        # Physical object still exists in bpy.data.objects!
        liveness = _check_original_object_liveness(session_rec)
        self.assertTrue(liveness["object_exists"])
        self.assertTrue(session_rec.in_live_blender_collection)

        # Attempting to retire tombstone while object physically exists must be strictly rejected
        retire_attempt = retire_dead_armature_tombstone(
            session_id,
            reason="Illegal attempt to retire tombstone while object exists in TEST-142",
        )
        self.assertFalse(retire_attempt["approved"])
        self.assertEqual(retire_attempt["evidence"]["status"], "TOMBSTONE_RETIREMENT_REJECTED")
        self.assertTrue(any("still exists in bpy.data.objects" in r for r in retire_attempt["evidence"]["reasons"]))
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-142"] = {
            "test_method": "test_142_armature_alive_with_replaced_datablock_cannot_retire_tombstone",
            "status": "PASS",
            "transaction_id": "admission_gate_rejection",
            "registry_session_id": session_id,
            "failure_class": "FAILED-D",
            "isolation_state": session_rec.isolation_state.value,
            "admission_result": "REJECTED_BEFORE_SNAPSHOTTING",
            "object_exists": True,
            "tombstone_retirement": "REJECTED_OBJECT_ALIVE",
        }

    def test_143_genuine_deletion_of_original_armature_allows_valid_tombstone_retirement(self) -> None:
        """TEST-143: Genuine deletion of original Armature object from bpy.data.objects permits retirement to ARCHIVED_RETIRED."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Replace data and isolate as FAILED-D
        self.armature.data = bpy.data.armatures.new("TempData_143")
        with self.assertRaises(RuntimeError):
            setup_arm_ik(self.armature)
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)

        # Now genuinely remove the object from bpy.data.objects
        bpy.data.objects.remove(self.armature, do_unlink=True)
        liveness = _check_original_object_liveness(session_rec)
        self.assertFalse(liveness["object_exists"])

        # Retirement must now succeed
        retire_res = retire_dead_armature_tombstone(
            session_id,
            reason="Legitimate retirement after genuine Armature object removal in TEST-143",
        )
        self.assertTrue(retire_res["approved"])
        self.assertEqual(retire_res["action"], "ARCHIVED_RETIRED")
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ARCHIVED_RETIRED)
        self.assertNotIn(session_id, _ISOLATED_FAILED_ARMATURES)
        self.assertIn(session_id, _ARCHIVED_FAILED_D_TOMBSTONES)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-143"] = {
            "test_method": "test_143_genuine_deletion_of_original_armature_allows_valid_tombstone_retirement",
            "status": "PASS",
            "transaction_id": "admission_gate_rejection",
            "registry_session_id": session_id,
            "failure_class": "FAILED-D",
            "isolation_state": session_rec.isolation_state.value,
            "object_exists": False,
            "tombstone_retirement": "APPROVED_ARCHIVED_RETIRED",
        }

    def test_144_same_name_replacement_armature_receives_new_uuid_and_cannot_reuse_dead_session(self) -> None:
        """TEST-144: Same-name replacement Armature receives new UUID and cannot reuse or de-isolate old dead session."""
        session_dead = ensure_armature_session_identity(self.armature)
        dead_session_id = session_dead.registry_session_id

        # Destroy original Armature
        bpy.data.objects.remove(self.armature, do_unlink=True)
        _ = _verify_armature_session_identity_record(session_dead)
        session_dead.isolation_state = _ArmatureIsolationState.TOMBSTONED_FAILED_D
        _ISOLATED_FAILED_ARMATURES[dead_session_id] = {
            "registry_session_id": dead_session_id,
            "failure_class": _FailedTransactionClass.FAILED_D.value,
            "isolation_state": _ArmatureIsolationState.TOMBSTONED_FAILED_D.value,
        }

        # Build new Armature with exact same name
        replacement_arm = build_rig(self.config)
        self.assertEqual(replacement_arm.name, "CharacterArmature")

        # Must get a new session identity record with distinct UUID
        new_session = ensure_armature_session_identity(replacement_arm)
        self.assertNotEqual(new_session.registry_session_id, dead_session_id)
        self.assertEqual(new_session.isolation_state, _ArmatureIsolationState.NONE)

        # De-isolation on dead session using new Armature is rejected
        deiso_dead = request_armature_deisolation(
            replacement_arm,
            reason="Attempt to revive old session with replacement object in TEST-144",
            session_id=dead_session_id,
        )
        self.assertFalse(deiso_dead["approved"])
        self.assertEqual(deiso_dead["evidence"]["status"], "REJECTED_DEAD_ARMATURE_TOMBSTONE")

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-144"] = {
            "test_method": "test_144_same_name_replacement_armature_receives_new_uuid_and_cannot_reuse_dead_session",
            "status": "PASS",
            "dead_session_id": dead_session_id,
            "replacement_session_id": new_session.registry_session_id,
            "deisolation_result": "REJECTED_DEAD_ARMATURE_TOMBSTONE",
        }

    def test_145_forged_can_deisolate_dict_passed_directly_to_layer2_rejected(self) -> None:
        """TEST-145: Forged dict {'can_deisolate': True} passed directly to Layer 2 is rejected."""
        setup_arm_ik(self.armature, initial_influence=0.5)
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Put session into ISOLATED_FAILED_B
        session_rec.isolation_state = _ArmatureIsolationState.ISOLATED_FAILED_B
        _ISOLATED_FAILED_ARMATURES[session_id] = {
            "registry_session_id": session_id,
            "failure_class": _FailedTransactionClass.FAILED_B.value,
            "isolation_state": _ArmatureIsolationState.ISOLATED_FAILED_B.value,
        }

        # Passing forged plain dict without Coordinator grant must raise RuntimeError
        with self.assertRaises(RuntimeError) as cm_forged:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id=session_id,
                action="CLEAR_TO_NONE",
                reason="Direct forgery attempt in TEST-145",
                authorization_grant={"can_deisolate": True},
            )
        self.assertIn("invalid or missing Coordinator authorization grant", str(cm_forged.exception))
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_B)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-145"] = {
            "test_method": "test_145_forged_can_deisolate_dict_passed_directly_to_layer2_rejected",
            "status": "PASS",
            "registry_session_id": session_id,
            "attack_type": "FORGED_CAN_DEISOLATE_DICT",
            "enforcement_result": "REJECTED_INVALID_OR_MISSING_GRANT",
        }

    def test_146_forged_can_retire_dict_passed_directly_to_layer2_rejected(self) -> None:
        """TEST-146: Forged dict {'can_retire': True} passed directly to Layer 2 is rejected."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Put session into TOMBSTONED_FAILED_D
        session_rec.isolation_state = _ArmatureIsolationState.TOMBSTONED_FAILED_D
        _ISOLATED_FAILED_ARMATURES[session_id] = {
            "registry_session_id": session_id,
            "failure_class": _FailedTransactionClass.FAILED_D.value,
            "isolation_state": _ArmatureIsolationState.TOMBSTONED_FAILED_D.value,
        }

        # Passing forged plain dict must raise RuntimeError
        with self.assertRaises(RuntimeError) as cm_forged:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id=session_id,
                action="ARCHIVE_TOMBSTONE",
                reason="Direct retirement forgery in TEST-146",
                authorization_grant={"can_retire": True},
            )
        self.assertIn("invalid or missing Coordinator authorization grant", str(cm_forged.exception))
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.TOMBSTONED_FAILED_D)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-146"] = {
            "test_method": "test_146_forged_can_retire_dict_passed_directly_to_layer2_rejected",
            "status": "PASS",
            "registry_session_id": session_id,
            "attack_type": "FORGED_CAN_RETIRE_DICT",
            "enforcement_result": "REJECTED_INVALID_OR_MISSING_GRANT",
        }

    def test_147_coordinator_grant_binding_and_single_use_enforcement(self) -> None:
        """TEST-147: Coordinator grant enforces cross-session rejection, cross-action rejection, and single-use consumption."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # Put session into ISOLATED_FAILED_B
        session_rec.isolation_state = _ArmatureIsolationState.ISOLATED_FAILED_B
        _ISOLATED_FAILED_ARMATURES[session_id] = {
            "registry_session_id": session_id,
            "failure_class": _FailedTransactionClass.FAILED_B.value,
            "isolation_state": _ArmatureIsolationState.ISOLATED_FAILED_B.value,
        }

        # Issue genuine grant for session_id
        grant = _issue_coordinator_authorization_grant(
            session_id=session_id,
            tx_id="tx_test_147",
            failure_class=_FailedTransactionClass.FAILED_B.value,
            current_isolation_state=_ArmatureIsolationState.ISOLATED_FAILED_B.value,
            transition_action="CLEAR_TO_NONE",
            evidence_status="VERIFIED",
        )
        issued_grant_id = grant["grant_id"]

        # 1. Cross-session rejection: passing grant with different session_id raises RuntimeError
        with self.assertRaises(RuntimeError) as cm_cross_session:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id="wrong_session_id",
                action="CLEAR_TO_NONE",
                reason="Cross-session attack",
                authorization_grant=grant,
            )
        self.assertIn("not found in active isolation registry", str(cm_cross_session.exception))

        # 2. Cross-action rejection: passing grant with mismatched transition_action raises RuntimeError
        with self.assertRaises(RuntimeError) as cm_cross_action:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id=session_id,
                action="ARCHIVE_TOMBSTONE",
                reason="Cross-action attack",
                authorization_grant=grant,
            )
        self.assertIn("grant action mismatch", str(cm_cross_action.exception))

        # 3. Legitimate single use succeeds
        res = _clear_or_retire_failure_isolation_by_coordinator(
            session_id=session_id,
            action="CLEAR_TO_NONE",
            reason="Legitimate single use in TEST-147",
            authorization_grant=grant,
        )
        self.assertEqual(res["new_isolation_state"], _ArmatureIsolationState.NONE.value)
        self.assertTrue(grant["consumed"])

        # 4. Reusing the exact same grant raises RuntimeError (grant already consumed/removed)
        session_rec.isolation_state = _ArmatureIsolationState.ISOLATED_FAILED_B
        _ISOLATED_FAILED_ARMATURES[session_id] = {
            "registry_session_id": session_id,
            "failure_class": _FailedTransactionClass.FAILED_B.value,
            "isolation_state": _ArmatureIsolationState.ISOLATED_FAILED_B.value,
        }
        with self.assertRaises(RuntimeError) as cm_reuse:
            _clear_or_retire_failure_isolation_by_coordinator(
                session_id=session_id,
                action="CLEAR_TO_NONE",
                reason="Replay attack",
                authorization_grant=grant,
            )
        self.assertIn("invalid or missing Coordinator authorization grant", str(cm_reuse.exception))

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-147"] = {
            "test_method": "test_147_coordinator_grant_binding_and_single_use_enforcement",
            "status": "PASS",
            "registry_session_id": session_id,
            "grant_id": issued_grant_id,
            "cross_session_rejected": True,
            "cross_action_rejected": True,
            "single_use_consumed": True,
            "replay_rejected": True,
        }

    def test_148_non_empty_reason_required_for_deisolation_and_tombstone_retirement(self) -> None:
        """TEST-148: Non-empty reason string is strictly required for request_armature_deisolation and retire_dead_armature_tombstone."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id

        # 1. request_armature_deisolation rejects invalid reasons
        for bad_reason in (None, "", "   ", "\t\n"):
            res = request_armature_deisolation(self.armature, reason=bad_reason, session_id=session_id)
            self.assertFalse(res["approved"])
            self.assertTrue(any("reason must be a non-empty string" in r for r in res.get("reasons", [])))

            with self.assertRaises(ValueError):
                request_armature_deisolation(self.armature, reason=bad_reason, session_id=session_id, raise_on_reject=True)

        # 2. retire_dead_armature_tombstone rejects invalid reasons
        for bad_reason in (None, "", "   ", "\t\n"):
            res = retire_dead_armature_tombstone(session_id, reason=bad_reason)
            self.assertFalse(res["approved"])
            self.assertTrue(any("reason must be a non-empty string" in r for r in res.get("reasons", [])))

            with self.assertRaises(ValueError):
                retire_dead_armature_tombstone(session_id, reason=bad_reason, raise_on_reject=True)

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-148"] = {
            "test_method": "test_148_non_empty_reason_required_for_deisolation_and_tombstone_retirement",
            "status": "PASS",
            "registry_session_id": session_id,
            "invalid_reasons_tested": ["None", "empty_str", "spaces", "whitespace"],
            "deisolation_rejected": True,
            "retirement_rejected": True,
            "value_error_raised_on_flag": True,
        }

    def test_149_relationship_undo_exception_transitions_to_recovery_uncertain_and_isolates_as_failed_c(self) -> None:
        """TEST-149: Relationship undo exception transitions operation to RECOVERY_UNCERTAIN and isolates session as FAILED-C."""
        session_rec = ensure_armature_session_identity(self.armature)
        session_id = session_rec.registry_session_id
        captured_tx = []

        def fault_hook(stage: str, ctx: dict) -> None:
            if stage == "setup_arm_ik_after_first_controller":
                if _ACTIVE_TRANSACTION_STACK:
                    captured_tx.append(_ACTIVE_TRANSACTION_STACK[-1])
                raise RuntimeError("Primary write fault in TEST-149")
            elif stage == "during_relationship_rollback_undo":
                raise RuntimeError("Undo fault in TEST-149")

        _set_test_fault_injection_hook(fault_hook)
        try:
            with self.assertRaises(RuntimeError) as cm:
                setup_arm_ik(self.armature, initial_influence=0.5)
            exc_str = str(cm.exception)
            self.assertIn("Primary write fault in TEST-149", exc_str)
            self.assertIn("rollback verification failed", exc_str)
        finally:
            _clear_test_fault_injection_hook()

        self.assertEqual(len(captured_tx), 1)
        tx = captured_tx[0]
        # Session must be isolated as FAILED-C
        self.assertEqual(session_rec.isolation_state, _ArmatureIsolationState.ISOLATED_FAILED_C)
        self.assertIn(session_id, _ISOLATED_FAILED_ARMATURES)
        iso_rec = _ISOLATED_FAILED_ARMATURES[session_id]
        self.assertEqual(iso_rec["failure_class"], _FailedTransactionClass.FAILED_C.value)

        # Confirm that the operation is recorded in recovery_uncertain_operations
        uncertain_ops = iso_rec.get("recovery_uncertain_operations", [])
        self.assertGreaterEqual(len(uncertain_ops), 1)

        # Subsequent write must be rejected by FAILED Isolation Gate
        with self.assertRaises(RuntimeError) as cm_blocked:
            setup_arm_ik(self.armature, initial_influence=0.5)
        self.assertIn("FAILED-C", str(cm_blocked.exception))

        _TEST_137_TO_149_RUNTIME_EVIDENCE["TEST-149"] = {
            "test_method": "test_149_relationship_undo_exception_transitions_to_recovery_uncertain_and_isolates_as_failed_c",
            "status": "PASS",
            "transaction_id": tx.tx_id,
            "registry_session_id": session_id,
            "failure_class": tx.failure_class,
            "isolation_state": session_rec.isolation_state.value,
            "recovery_uncertain_ops_count": len(uncertain_ops),
            "preserves_primary_and_rollback_exceptions": True,
            "subsequent_write_blocked": True,
        }


if __name__ == "__main__":
    args = [sys.argv[0]]
    if "--" in sys.argv:
        args.extend(sys.argv[sys.argv.index("--") + 1:])
    else:
        args.append("-v")
    runner = unittest.TextTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestArmIKTransactionAtomicity)
    result = runner.run(suite)
    if _TEST_137_TO_149_RUNTIME_EVIDENCE:
        out_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(out_dir, exist_ok=True)
        ev_path = os.path.join(out_dir, "audit_13_r1_runtime_evidence.json")
        with open(ev_path, "w", encoding="utf-8") as f:
            json.dump(_TEST_137_TO_149_RUNTIME_EVIDENCE, f, indent=2)
    sys.exit(0 if result.wasSuccessful() else 1)
