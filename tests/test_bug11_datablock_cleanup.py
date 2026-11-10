"""BUG-11 / R1-TAIL-03: Type-A DataBlock deletion fault-window contracts.

Strictly additive tests. Do not run until the user's unified Blender regression.
This suite never changes the original test_task10b_transaction_atomicity.py.
"""
import os
import sys
import unittest

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.rig.arm_ik as arm_ik
from src.character.builder import build_character
from src.config import PipelineConfig
from src.rig.builder import bind_character_to_rig, build_rig
from src.rig.ik import reset_leg_ik, setup_leg_ik
from src.rig.pose import reset_pose


class TestBug11TypeADataBlockFaults(unittest.TestCase):
    """Real Blender object/datablock checks; never use fake PASS or xfail."""

    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self._reset_agent_state()
        config = PipelineConfig()
        char_data = build_character(config)
        self.armature = build_rig(config)
        bind_character_to_rig(self.armature, char_data["parts"])
        setup_leg_ik(self.armature)
        reset_leg_ik(self.armature)
        reset_pose(self.armature)
        bpy.context.view_layer.update()
        self.last_tx = None

    def tearDown(self):
        self._reset_agent_state()

    @staticmethod
    def _reset_agent_state():
        arm_ik._clear_test_fault_injection_hook()
        arm_ik._clear_test_depsgraph_updater()
        for field in (
            "_PENDING_ARM_RIG_CLEANUPS", "_ISOLATED_FAILED_ARMATURES",
            "_MANAGED_ARMATURE_IDENTITIES", "_ARCHIVED_FAILED_D_TOMBSTONES",
            "_FAILED_A_AUDIT_RECORDS", "_DEISOLATION_AUDIT_LOG",
        ):
            getattr(arm_ik, field).clear()
        arm_ik._clear_coordinator_authorization_grants()

    def _make_replacement(self, *, mutate_before_setup=None):
        """Produce an independently receipted Type-A Mesh in a genuine pending cleanup path."""
        with arm_ik._arm_rig_transaction(self.armature) as tx:
            self.last_tx = tx
            mesh = arm_ik._authorized_create_type_a_mesh("BUG11_TypeA_Mesh", tx)
            ptr = int(mesh.as_pointer())
            object_ref = bpy.data.objects.new("HandIK.L", mesh)
            tx.register_created_controller(object_ref)
            arm_ik._authorized_link_object_to_collection(
                bpy.context.scene.collection, object_ref, tx,
            )
            if mutate_before_setup is not None:
                mutate_before_setup(tx, mesh)
            arm_ik.setup_arm_ik(self.armature)
        return tx, mesh, ptr

    @staticmethod
    def _exists(ptr):
        return any(int(m.as_pointer()) == ptr for m in bpy.data.meshes)

    def _assert_pending(self, tx, ptr):
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.CLEANUP_PENDING)
        self.assertIn(tx.tx_id, arm_ik._PENDING_ARM_RIG_CLEANUPS)
        self.assertTrue(self._exists(ptr), "pending deletion must retain original Mesh")
        self.assertNotIn("HandIK.L", [o.name for o in bpy.data.objects if o.type == "MESH"])

    def _retry_and_expect_deleted(self, tx, ptr):
        arm_ik.retry_pending_arm_rig_cleanup(tx.tx_id)
        self.assertFalse(self._exists(ptr), "authorized retry must delete only original Mesh")
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.COMMITTED)
        self.assertNotIn(tx.tx_id, arm_ik._PENDING_ARM_RIG_CLEANUPS)

    def test_bug11_01_valid_type_a_positive_control(self):
        tx, _, ptr = self._make_replacement()
        self.assertFalse(self._exists(ptr))
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.COMMITTED)
        statuses = [r.get("status") for r in tx.datablock_cleanup_outcomes]
        self.assertIn("PHYSICALLY_DELETED", statuses)

    def test_bug11_02_fault_before_authorization_then_retry(self):
        def fault(stage, ctx):
            if stage == "during_cleanup_datablock_removal":
                raise RuntimeError("BUG11 injected before DataBlock authorization")
        arm_ik._set_test_fault_injection_hook(fault)
        with self.assertRaisesRegex(RuntimeError, "BUG11 injected before DataBlock authorization"):
            self._make_replacement()
        tx = self.last_tx
        ptr = next(iter(tx._type_a_datablock_receipts))
        self._assert_pending(tx, ptr)
        arm_ik._clear_test_fault_injection_hook()
        self._retry_and_expect_deleted(tx, ptr)

    def test_bug11_03_fault_after_authorization_before_physical_remove(self):
        outsider = bpy.data.meshes.new("BUG11_External_Preserved")
        outsider_ptr = int(outsider.as_pointer())
        observed = []
        def fault(stage, ctx):
            if stage == "during_cleanup_datablock_after_auth_before_remove":
                observed.append((ctx["data_ptr"], ctx["tx"].tx_id))
                raise RuntimeError("BUG11 injected after authority before removal")
        arm_ik._set_test_fault_injection_hook(fault)
        with self.assertRaisesRegex(RuntimeError, "BUG11 injected after authority before removal"):
            self._make_replacement()
        tx = self.last_tx
        ptr = next(iter(tx._type_a_datablock_receipts))
        self.assertEqual(observed, [(ptr, tx.tx_id)])
        self._assert_pending(tx, ptr)
        self.assertTrue(self._exists(outsider_ptr), "no cross-DataBlock deletion")
        arm_ik._clear_test_fault_injection_hook()
        self._retry_and_expect_deleted(tx, ptr)
        self.assertTrue(self._exists(outsider_ptr), "unrelated Mesh remains live")

    def test_bug11_04_fault_after_physical_remove_no_double_delete(self):
        observed = []
        def fault(stage, ctx):
            if stage == "during_cleanup_datablock_after_remove_before_verify":
                observed.append(ctx["data_ptr"])
                raise RuntimeError("BUG11 injected after physical removal")
        arm_ik._set_test_fault_injection_hook(fault)
        with self.assertRaisesRegex(RuntimeError, "BUG11 injected after physical removal"):
            self._make_replacement()
        tx = self.last_tx
        ptr = next(iter(tx._type_a_datablock_receipts))
        self.assertEqual(observed, [ptr])
        self.assertFalse(self._exists(ptr), "C-API already removed Mesh")
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.CLEANUP_PENDING)
        arm_ik._clear_test_fault_injection_hook()
        self._retry_and_expect_deleted(tx, ptr)
        self.assertEqual(observed, [ptr], "retry must not double-delete")

    def test_bug11_05_forged_auth_pointer_refuses_then_recovers(self):
        def mutate(stage, ctx):
            if stage == "during_commit_cleanup":
                tx = ctx["tx"]
                auth = next(a for a in tx.datablock_authorizations
                            if a.get("provenance") == "TYPE_A_TX_CREATED")
                auth["original_pointer"] = -123456
        arm_ik._set_test_fault_injection_hook(mutate)
        with self.assertRaises(RuntimeError):
            self._make_replacement()
        tx = self.last_tx
        ptr = next(iter(tx._type_a_datablock_receipts))
        self._assert_pending(tx, ptr)
        self.assertTrue(any(not o.get("data_cleaned") for o in tx.uncleaned_stashed_objects))
        for auth in tx.datablock_authorizations:
            if auth.get("provenance") == "TYPE_A_TX_CREATED":
                auth["original_pointer"] = ptr
        arm_ik._clear_test_fault_injection_hook()
        self._retry_and_expect_deleted(tx, ptr)

    def test_bug11_06_mismatched_receipt_refuses_then_recovers(self):
        actual_receipt = {}
        def mutate(stage, ctx):
            if stage == "during_commit_cleanup":
                tx = ctx["tx"]
                ptr, receipt = next(iter(tx._type_a_datablock_receipts.items()))
                actual_receipt["ptr"] = ptr
                actual_receipt["receipt"] = receipt
                tx._type_a_datablock_receipts[ptr] = (receipt[0], receipt[1], "wrong-tx", receipt[3])
        arm_ik._set_test_fault_injection_hook(mutate)
        with self.assertRaises(RuntimeError):
            self._make_replacement()
        tx = self.last_tx
        ptr = actual_receipt["ptr"]
        self._assert_pending(tx, ptr)
        tx._type_a_datablock_receipts[ptr] = actual_receipt["receipt"]
        arm_ik._clear_test_fault_injection_hook()
        self._retry_and_expect_deleted(tx, ptr)

    def test_bug11_07_second_live_user_blocks_then_retry(self):
        foreign = []
        def extra_user(tx, mesh):
            obj = bpy.data.objects.new("BUG11_OtherMeshUser", mesh)
            bpy.context.scene.collection.objects.link(obj)
            foreign.append(obj)
        with self.assertRaises(RuntimeError):
            self._make_replacement(mutate_before_setup=extra_user)
        tx = self.last_tx
        ptr = next(iter(tx._type_a_datablock_receipts))
        self._assert_pending(tx, ptr)
        self.assertTrue(self._exists(ptr))
        self.assertIsNotNone(bpy.data.objects.get("BUG11_OtherMeshUser"))
        bpy.data.objects.remove(foreign[0], do_unlink=True)
        self._retry_and_expect_deleted(tx, ptr)

    def test_bug11_08_zero_user_without_authorization_is_preserved(self):
        def remove_authority(stage, ctx):
            if stage == "during_commit_cleanup":
                ctx["tx"].datablock_authorizations.clear()
        arm_ik._set_test_fault_injection_hook(remove_authority)
        tx, _, ptr = self._make_replacement()
        self.assertTrue(self._exists(ptr), "no authority must never delete")
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.COMMITTED)
        self.assertIn("PRESERVED_NO_DELETE_AUTHORITY",
                      [r.get("status") for r in tx.datablock_cleanup_outcomes])


if __name__ == "__main__":
    unittest.main()
