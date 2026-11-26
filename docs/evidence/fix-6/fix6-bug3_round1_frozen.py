"""Task 10-B fix6-bug3 / Round 1: immutable, test-only bidirectional resource-isolation check."""
import os
import sys
import unittest

import bpy

sys.path.insert(0, os.path.abspath("."))
import src.rig.arm_ik as ai
from src.config import PipelineConfig
from src.character.builder import build_character
from src.rig.builder import build_rig, bind_character_to_rig
from src.rig.ik import setup_leg_ik, reset_leg_ik
from src.rig.pose import reset_pose


def make_fixture():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    cfg = PipelineConfig()
    character = build_character(cfg)
    arm_a = build_rig(cfg)
    arm_b_data = arm_a.data.copy()
    arm_b_data.name = "Fix6Bug3ArmBData"
    arm_b = bpy.data.objects.new("Fix6Bug3ArmB", arm_b_data)
    root_b = bpy.data.objects.new("Fix6Bug3RootB", None)
    bpy.context.scene.collection.objects.link(root_b)
    bpy.context.scene.collection.objects.link(arm_b)
    arm_b.parent = root_b
    arm_b.location = (2.0, 0.0, 0.0)
    bind_character_to_rig(arm_a, character["parts"])
    setup_leg_ik(arm_a)
    reset_leg_ik(arm_a)
    reset_pose(arm_a)
    reset_pose(arm_b)
    bpy.context.view_layer.update()
    assert len(arm_b.data.bones) == 19
    return arm_a, arm_b


class TestFix6Bug3Round1(unittest.TestCase):
    def setUp(self):
        ai._clear_test_fault_injection_hook()
        ai._clear_test_depsgraph_updater()
        ai._PENDING_ARM_RIG_CLEANUPS.clear()
        ai._ISOLATED_FAILED_ARMATURES.clear()
        ai._MANAGED_ARMATURE_IDENTITIES.clear()
        ai._ARCHIVED_FAILED_D_TOMBSTONES.clear()
        ai._FAILED_A_AUDIT_RECORDS.clear()
        ai._DEISOLATION_AUDIT_LOG.clear()
        ai._clear_coordinator_authorization_grants()
        self.arm_a, self.arm_b = make_fixture()

    def tearDown(self):
        ai._clear_test_fault_injection_hook()
        ai._clear_test_depsgraph_updater()
        ai._PENDING_ARM_RIG_CLEANUPS.clear()
        ai._ISOLATED_FAILED_ARMATURES.clear()
        ai._MANAGED_ARMATURE_IDENTITIES.clear()
        ai._ARCHIVED_FAILED_D_TOMBSTONES.clear()
        ai._FAILED_A_AUDIT_RECORDS.clear()
        ai._DEISOLATION_AUDIT_LOG.clear()
        ai._clear_coordinator_authorization_grants()

    def verify_direction(self, owner, foreign, direction):
        owner_session = ai.ensure_armature_session_identity(owner)
        foreign_session = ai.ensure_armature_session_identity(foreign)
        self.assertNotEqual(owner.as_pointer(), foreign.as_pointer())
        self.assertNotEqual(owner_session.registry_session_id, foreign_session.registry_session_id)
        self.assertNotIn("HandIK.L", bpy.data.objects)

        external = bpy.data.meshes.new("Fix6Bug3R1_External_" + direction)
        external_ptr = int(external.as_pointer())
        tx_holder = []
        record = {}
        hook_calls = []
        base_name = "Fix6Bug3R1_Shared_" + direction

        def before_remove(stage, ctx):
            if stage == "during_cleanup_datablock_after_auth_before_remove":
                self.assertIs(ctx.get("tx"), tx_holder[0])
                self.assertEqual(int(ctx.get("data_ptr")), record["pointer"])
                self.assertEqual(int(ctx["data"].users), 0)
                hook_calls.append(stage)
                raise RuntimeError("FIX6_BUG3_R1_EXPECTED_BEFORE_REMOVE")

        ai._set_test_fault_injection_hook(before_remove)
        try:
            with self.assertRaises(RuntimeError) as raised:
                with ai._arm_rig_transaction(owner) as tx_owner:
                    tx_holder.append(tx_owner)
                    prior = {int(m.as_pointer()) for m in bpy.data.meshes}
                    mesh_owner = ai._authorized_create_type_a_mesh(base_name, tx_owner)
                    record["pointer"] = int(mesh_owner.as_pointer())
                    record["name"] = mesh_owner.name
                    self.assertNotIn(record["pointer"], prior)
                    self.assertEqual(int(mesh_owner.users), 0)
                    wrong_type = bpy.data.objects.new("HandIK.L", mesh_owner)
                    self.assertEqual(wrong_type.name, "HandIK.L")
                    tx_owner.register_created_controller(wrong_type)
                    ai._authorized_link_object_to_collection(
                        bpy.context.scene.collection, wrong_type, active_tx=tx_owner
                    )
                    ai.setup_arm_ik(owner, initial_influence=0.5)
        finally:
            ai._clear_test_fault_injection_hook()

        tx_owner = tx_holder[0]
        owner_ptr = record["pointer"]
        self.assertEqual(len(hook_calls), 1)
        self.assertIn("FIX6_BUG3_R1_EXPECTED_BEFORE_REMOVE", str(raised.exception))
        self.assertEqual(tx_owner.state, ai._ArmRigTransactionState.CLEANUP_PENDING)
        self.assertIs(ai._PENDING_ARM_RIG_CLEANUPS[tx_owner.tx_id], tx_owner)
        self.assertEqual(len(tx_owner.uncleaned_stashed_objects), 1)
        self.assertEqual(tx_owner.uncleaned_stashed_objects[0]["stashed_data_ptr"], owner_ptr)
        self.assertTrue(any(m.as_pointer() == owner_ptr for m in bpy.data.meshes))
        self.assertTrue(ai.query_admission_gate_status(owner)["cleanup_pending_blocked"])
        self.assertFalse(ai.query_admission_gate_status(foreign)["cleanup_pending_blocked"])
        with self.assertRaisesRegex(RuntimeError, "unresolved cleanup"):
            ai.set_arm_ik_influence(owner, side="L", influence=0.25)

        with ai._arm_rig_transaction(foreign) as tx_foreign:
            self.assertNotEqual(tx_foreign.tx_id, tx_owner.tx_id)
            mesh_foreign = ai._authorized_create_type_a_mesh(base_name, tx_foreign)
            foreign_ptr = int(mesh_foreign.as_pointer())
            foreign_name = str(mesh_foreign.name)
            self.assertNotEqual(foreign_ptr, owner_ptr)
            self.assertNotEqual(foreign_name, record["name"])
            receipt_foreign = tx_foreign._type_a_datablock_receipts[foreign_ptr]
            self.assertEqual(receipt_foreign[1], foreign_session.registry_session_id)
            self.assertEqual(receipt_foreign[2], tx_foreign.tx_id)
            self.assertIs(receipt_foreign[3], tx_foreign._type_a_datablock_receipt_seal)
        self.assertEqual(tx_foreign.state, ai._ArmRigTransactionState.COMMITTED)
        self.assertEqual(len(tx_foreign.uncleaned_stashed_objects), 0)
        self.assertEqual(tx_owner.state, ai._ArmRigTransactionState.CLEANUP_PENDING)
        self.assertTrue(any(m.as_pointer() == foreign_ptr for m in bpy.data.meshes))

        ai.retry_pending_arm_rig_cleanup(tx_owner.tx_id)
        self.assertEqual(tx_owner.state, ai._ArmRigTransactionState.COMMITTED)
        self.assertNotIn(tx_owner.tx_id, ai._PENDING_ARM_RIG_CLEANUPS)
        self.assertEqual(len(ai.get_pending_arm_rig_cleanup_ids()), 0)
        self.assertFalse(any(m.as_pointer() == owner_ptr for m in bpy.data.meshes))
        self.assertTrue(any(m.as_pointer() == foreign_ptr and m == mesh_foreign for m in bpy.data.meshes))
        self.assertTrue(any(m.as_pointer() == external_ptr and m == external for m in bpy.data.meshes))
        self.assertEqual(tx_foreign._type_a_datablock_receipts[foreign_ptr], receipt_foreign)
        self.assertEqual(len(tx_foreign.datablock_cleanup_outcomes), 0)
        outcomes = [o for o in tx_owner.datablock_cleanup_outcomes
                    if o.get("resource_pointer") == owner_ptr]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["status"], "PHYSICALLY_DELETED")
        self.assertEqual(outcomes[0]["tx_id"], tx_owner.tx_id)
        self.assertFalse(ai.query_admission_gate_status(owner)["cleanup_pending_blocked"])
        self.assertFalse(ai.query_admission_gate_status(foreign)["cleanup_pending_blocked"])
        print("FIX6_BUG3_R1_DIRECTION_PASS", direction,
              "owner_tx", tx_owner.tx_id, "foreign_tx", tx_foreign.tx_id,
              "owner_deleted_pointer", owner_ptr,
              "foreign_preserved_pointer", foreign_ptr,
              "external_preserved_pointer", external_ptr,
              "owner_outcome", outcomes[0])

    def test_01_a_is_cleanup_owner_b_protected(self):
        self.verify_direction(self.arm_a, self.arm_b, "A_TO_B")

    def test_02_b_is_cleanup_owner_a_protected(self):
        self.verify_direction(self.arm_b, self.arm_a, "B_TO_A")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestFix6Bug3Round1)
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    print("FIX6_BUG3_R1_TESTS_RUN", result.testsRun)
    print("FIX6_BUG3_R1_SUCCESS", result.wasSuccessful() and result.testsRun == 2)
    sys.exit(0 if result.wasSuccessful() and result.testsRun == 2 else 1)
