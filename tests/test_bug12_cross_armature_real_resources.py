"""BUG-12 / HIST-F06: real Blender pending-resource isolation across Armatures.

Additive regression contracts only. Run with the unified Blender suite, not during
BUG-12 patch installation. No production code, original test, or runner changes.
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


class TestBug12RealCrossArmaturePending(unittest.TestCase):
    """Every pending record contains genuine, still-live Blender Objects/Constraints."""

    @staticmethod
    def _reset_state():
        arm_ik._clear_test_fault_injection_hook()
        arm_ik._clear_test_depsgraph_updater()
        for attr in (
            "_PENDING_ARM_RIG_CLEANUPS", "_ISOLATED_FAILED_ARMATURES",
            "_MANAGED_ARMATURE_IDENTITIES", "_ARCHIVED_FAILED_D_TOMBSTONES",
            "_FAILED_A_AUDIT_RECORDS", "_DEISOLATION_AUDIT_LOG",
        ):
            getattr(arm_ik, attr).clear()
        arm_ik._clear_coordinator_authorization_grants()

    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self._reset_state()
        cfg = PipelineConfig()
        char = build_character(cfg)
        self.arm_a = build_rig(cfg)
        bind_character_to_rig(self.arm_a, char["parts"])
        setup_leg_ik(self.arm_a)
        reset_leg_ik(self.arm_a)
        reset_pose(self.arm_a)
        # Separate Blender Object and Armature datablock, not a second name for A.
        self.arm_b = self.arm_a.copy()
        self.arm_b.data = self.arm_a.data.copy()
        self.arm_b.name = "BUG12_IndependentArmatureB"
        bpy.context.scene.collection.objects.link(self.arm_b)
        bpy.context.view_layer.update()
        self.assertNotEqual(int(self.arm_a.as_pointer()), int(self.arm_b.as_pointer()))
        self.assertNotEqual(int(self.arm_a.data.as_pointer()), int(self.arm_b.data.as_pointer()))
        self.assertIsNotNone(self.arm_a.pose.bones.get("forearm.L"))
        self.assertIsNotNone(self.arm_b.pose.bones.get("forearm.L"))

    def tearDown(self):
        self._reset_state()

    @staticmethod
    def _object_present(ptr):
        return any(int(o.as_pointer()) == ptr for o in bpy.data.objects)

    @staticmethod
    def _mesh_present(ptr):
        return any(int(m.as_pointer()) == ptr for m in bpy.data.meshes)

    @staticmethod
    def _constraint_present(pbone, ptr):
        return any(int(c.as_pointer()) == ptr for c in pbone.constraints)

    def _make_real_pending(self, arm, label):
        """Physically create and stage an Object, Mesh, and PoseBone Constraint.

        Stash records have the same schema as the production stashing path.
        A deterministic fault prevents BOTH actual C-API removals, retaining
        genuine resources in CLEANUP_PENDING for cross-Armature verification.
        """
        pbone = arm.pose.bones["forearm.L"]
        mesh = bpy.data.meshes.new(f"BUG12_Mesh_{label}")
        obj = bpy.data.objects.new(f"BUG12_Object_{label}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        con = pbone.constraints.new(type="LIMIT_ROTATION")
        con.name = f"BUG12_Constraint_{label}"
        obj_ptr = int(obj.as_pointer())
        mesh_ptr = int(mesh.as_pointer())
        con_ptr = int(con.as_pointer())
        captured = []
        original_obj_name = obj.name
        original_con_name = con.name

        def inject(stage, ctx):
            if (stage == "during_constraint_removal"
                    and ctx.get("phase") == "POST_COMMIT_CLEANUP"
                    and ctx.get("record", {}).get("con_ptr") == con_ptr):
                raise RuntimeError(f"BUG12 blocked actual constraint cleanup {label}")
            if (stage == "during_cleanup_object_removal"
                    and ctx.get("stashed", {}).get("stashed_obj_ptr") == obj_ptr):
                raise RuntimeError(f"BUG12 blocked actual object cleanup {label}")

        arm_ik._set_test_fault_injection_hook(inject)
        try:
            with self.assertRaisesRegex(RuntimeError, "BUG12 blocked actual"):
                with arm_ik._arm_rig_transaction(arm) as tx:
                    captured.append(tx)
                    orig_mute = bool(con.mute)
                    orig_index = list(pbone.constraints).index(con)
                    con.name = f"__stashed_bug12_constraint_{label}"
                    con.mute = True
                    tx.stashed_constraints.append({
                        "pbone": pbone, "con": con, "con_ptr": con_ptr,
                        "orig_name": original_con_name, "orig_mute": orig_mute,
                        "orig_idx": orig_index,
                    })
                    obj.name = f"__stashed_bug12_object_{label}"
                    tx.stashed_objects.append({
                        "original_name": original_obj_name,
                        "stashed_obj": obj, "stashed_obj_ptr": obj_ptr,
                        "stashed_data": mesh, "stashed_data_ptr": mesh_ptr,
                        "stashed_data_name": mesh.name,
                        "collections": [c.name for c in obj.users_collection],
                        "collection_refs": list(obj.users_collection),
                        "collection_ptrs": [int(c.as_pointer()) for c in obj.users_collection],
                        "obj_cleaned": False, "data_cleaned": False,
                    })
        finally:
            arm_ik._clear_test_fault_injection_hook()
        self.assertEqual(len(captured), 1)
        tx = captured[0]
        resource = {
            "arm": arm, "tx": tx, "obj": obj, "obj_ptr": obj_ptr,
            "mesh_ptr": mesh_ptr, "pbone": pbone, "con_ptr": con_ptr,
        }
        self._assert_pending_live(resource)
        return resource

    def _assert_pending_live(self, resource):
        tx = resource["tx"]
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.CLEANUP_PENDING)
        self.assertIs(arm_ik._PENDING_ARM_RIG_CLEANUPS.get(tx.tx_id), tx)
        self.assertEqual(len(tx.uncleaned_stashed_constraints), 1)
        self.assertEqual(len(tx.uncleaned_stashed_objects), 1)
        self.assertTrue(self._object_present(resource["obj_ptr"]))
        self.assertTrue(self._mesh_present(resource["mesh_ptr"]))
        self.assertTrue(self._constraint_present(resource["pbone"], resource["con_ptr"]))

    def _assert_cleaned_only(self, resource):
        tx = resource["tx"]
        self.assertEqual(tx.state, arm_ik._ArmRigTransactionState.COMMITTED)
        self.assertNotIn(tx.tx_id, arm_ik._PENDING_ARM_RIG_CLEANUPS)
        self.assertFalse(self._object_present(resource["obj_ptr"]))
        self.assertFalse(self._constraint_present(resource["pbone"], resource["con_ptr"]))
        # No Type-A authorization exists for this external Mesh; physical ID
        # MUST be preserved, including when its user count reaches zero.
        self.assertTrue(self._mesh_present(resource["mesh_ptr"]))
        self.assertIn("PRESERVED_NO_DELETE_AUTHORITY", [
            item.get("status") for item in tx.datablock_cleanup_outcomes
        ])

    def _make_pair(self):
        a = self._make_real_pending(self.arm_a, "A")
        b = self._make_real_pending(self.arm_b, "B")
        self.assertNotEqual(a["tx"].session_id, b["tx"].session_id)
        self.assertNotEqual(a["tx"].tx_id, b["tx"].tx_id)
        self.assertNotEqual(a["obj_ptr"], b["obj_ptr"])
        self.assertNotEqual(a["con_ptr"], b["con_ptr"])
        self.assertEqual(len(arm_ik._PENDING_ARM_RIG_CLEANUPS), 2)
        return a, b

    def test_bug12_01_retry_a_deletes_only_a_real_resources(self):
        a, b = self._make_pair()
        arm_ik.retry_pending_arm_rig_cleanup(a["tx"].tx_id)
        self._assert_cleaned_only(a)
        self._assert_pending_live(b)
        self.assertEqual(len(arm_ik._PENDING_ARM_RIG_CLEANUPS), 1)
        arm_ik.retry_pending_arm_rig_cleanup(b["tx"].tx_id)
        self._assert_cleaned_only(b)
        self.assertEqual(len(arm_ik._PENDING_ARM_RIG_CLEANUPS), 0)

    def test_bug12_02_pending_both_gates_and_healthy_third_armature(self):
        a, b = self._make_pair()
        for pending in (a, b):
            with self.assertRaisesRegex(RuntimeError, "unresolved cleanup"):
                with arm_ik._arm_rig_transaction(pending["arm"]):
                    self.fail("Pending Armature unexpectedly entered ACTIVE transaction")
            self._assert_pending_live(pending)
        data_c = bpy.data.armatures.new("BUG12_IndependentDataC")
        arm_c = bpy.data.objects.new("BUG12_IndependentArmatureC", data_c)
        bpy.context.scene.collection.objects.link(arm_c)
        with arm_ik._arm_rig_transaction(arm_c) as healthy_tx:
            self.assertEqual(healthy_tx.state, arm_ik._ArmRigTransactionState.ACTIVE)
        self.assertEqual(healthy_tx.state, arm_ik._ArmRigTransactionState.COMMITTED)
        self._assert_pending_live(a)
        self._assert_pending_live(b)
        arm_ik.retry_pending_arm_rig_cleanup(b["tx"].tx_id)
        self._assert_cleaned_only(b)
        self._assert_pending_live(a)
        arm_ik.retry_pending_arm_rig_cleanup(a["tx"].tx_id)
        self._assert_cleaned_only(a)

    def test_bug12_03_foreign_constraint_and_cleanup_result_cannot_be_borrowed(self):
        a, b = self._make_pair()
        # A's exact live Constraint record is NOT a deletion grant for B.
        alien_record = a["tx"].uncleaned_stashed_constraints[0]
        with self.assertRaisesRegex(RuntimeError, "Unauthorized constraint removal"):
            arm_ik._authorized_remove_constraint(
                pbone=b["pbone"], con_record_or_ref=alien_record,
                phase="POST_COMMIT_CLEANUP", active_tx=b["tx"],
            )
        self._assert_pending_live(a)
        self._assert_pending_live(b)
        # Likewise a result bearing B's transaction ID cannot advance A.
        foreign_result = arm_ik._CleanupResult(
            transaction_id=b["tx"].tx_id,
            outcome=arm_ik._CleanupOutcome.CLEANUP_SUCCESS,
            errors=(), remaining_objects=0, remaining_constraints=0,
        )
        with self.assertRaisesRegex(RuntimeError, "transaction_id mismatch"):
            arm_ik._coordinator_apply_cleanup_result(
                a["tx"], foreign_result, phase="PENDING_RETRY",
            )
        self._assert_pending_live(a)
        self._assert_pending_live(b)
        arm_ik.retry_pending_arm_rig_cleanup(a["tx"].tx_id)
        arm_ik.retry_pending_arm_rig_cleanup(b["tx"].tx_id)
        self._assert_cleaned_only(a)
        self._assert_cleaned_only(b)

    def test_bug12_04_failed_retry_a_keeps_b_real_resources_untouched(self):
        a, b = self._make_pair()
        a_con_ptr = a["con_ptr"]
        def fail_a_only(stage, ctx):
            if (stage == "during_constraint_removal"
                    and ctx.get("phase") == "POST_COMMIT_CLEANUP"
                    and ctx.get("record", {}).get("con_ptr") == a_con_ptr):
                raise RuntimeError("BUG12 repeat fault on A only")
            if (stage == "during_cleanup_object_removal"
                    and ctx.get("stashed", {}).get("stashed_obj_ptr") == a["obj_ptr"]):
                raise RuntimeError("BUG12 repeat object fault on A only")

        arm_ik._set_test_fault_injection_hook(fail_a_only)
        try:
            with self.assertRaisesRegex(RuntimeError, "BUG12 repeat"):
                arm_ik.retry_pending_arm_rig_cleanup(a["tx"].tx_id)
        finally:
            arm_ik._clear_test_fault_injection_hook()
        self._assert_pending_live(a)
        self._assert_pending_live(b)
        arm_ik.retry_pending_arm_rig_cleanup(b["tx"].tx_id)
        self._assert_cleaned_only(b)
        self._assert_pending_live(a)
        arm_ik.retry_pending_arm_rig_cleanup(a["tx"].tx_id)
        self._assert_cleaned_only(a)


if __name__ == "__main__":
    args = [sys.argv[0]]
    if "--" in sys.argv:
        args.extend(sys.argv[sys.argv.index("--") + 1:])
    else:
        args.append("-v")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(TestBug12RealCrossArmaturePending)
    )
    sys.exit(0 if result.wasSuccessful() else 1)
