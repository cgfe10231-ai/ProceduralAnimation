# TASK 10-B｜工作包 B：历史测试前置修正与六项专项验证报告

* **任务编号**：`TASK 10-B｜工作包 B`（`TEST CORRECTION + TARGETED VERIFICATION`）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **精确测试基线 HEAD**：`da85f69dd6e08e4535b55e839e1c3f6eaca7b9e5`
* **前置核验 Git Blob SHA**：
  * `tests/test_task10b_input_validation.py`（修改前）：`ad06b329d3219f1814158cafc89445b9c6f865f9`
  * `tests/test_task10b_transaction_atomicity.py`（修改前）：`5c1fc463e4181b700cad335754a5cef610822426`
  * `tests/test_bug12_cross_armature_real_resources.py`（只读未改）：`8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40`
* **Blender 版本与退出码**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)` / 进程退出码 `0`（`BLENDER_EXIT_CODE=0`）

---

## 1. 两处测试修改的实际 Diff

### 1.1 `tests/test_task10b_input_validation.py`（`TEST-26`）

```diff
diff --git a/tests/test_task10b_input_validation.py b/tests/test_task10b_input_validation.py
index ad06b32..548b46f 100644
--- a/tests/test_task10b_input_validation.py
+++ b/tests/test_task10b_input_validation.py
@@ -667,8 +667,8 @@ class TestArmIKInputValidationContract(unittest.TestCase):
 
         Preconditions:
         - Character and Armature built, leg IK setup.
-        - Manually create a valid HandIK.L empty.
-        - Confirm ElbowPole.L, HandIK.R, ElbowPole.R are missing.
+        - Pre-existing valid HandIK.L empty with a genuine IK constraint binding on forearm.L.
+        - ElbowPole.L, HandIK.R, ElbowPole.R remain uninitialized.
         Setup:
         - Set initialization parent (root_obj) scale to reflection (-1.0, 1.0, 1.0).
         - Update dependency graph.
@@ -678,10 +678,8 @@ class TestArmIKInputValidationContract(unittest.TestCase):
         Assertions:
         - Raises ValueError from reflection rejection (det(A) < 0).
         - Post-call snapshot equals pre-call snapshot exactly.
-        - ElbowPole.L is NOT created.
-        - HandIK.R and ElbowPole.R are NOT created.
-        - No constraints created on any pose bones.
-        - Existing HandIK.L remains 100% unchanged.
+        - ElbowPole.L, HandIK.R, and ElbowPole.R are NOT created.
+        - Existing forearm.L IK binding, HandIK.L controller, and scene snapshot remain 100% unchanged.
         """
         hand_l = bpy.data.objects.new("HandIK.L", None)
         hand_l.empty_display_size = 0.08
@@ -689,6 +687,14 @@ class TestArmIKInputValidationContract(unittest.TestCase):
         hand_l.location = (0.35, -0.1, 1.1)
         bpy.context.scene.collection.objects.link(hand_l)
 
+        # [2026-11-18] TEST-26: Establish genuine Armature ownership for the
+        # existing partial-init HandIK.L before checking reflection rejection.
+        forearm_l = self.armature.pose.bones["forearm.L"]
+        existing_ik = forearm_l.constraints.new(type="IK")
+        existing_ik.name = ARM_IK_CONSTRAINT_NAMES["L"]
+        existing_ik.target = hand_l
+        existing_ik_ptr = int(existing_ik.as_pointer())
+
         for ctrl_name in ("HandIK.R", "ElbowPole.L", "ElbowPole.R"):
             self.assertNotIn(ctrl_name, bpy.data.objects)
 
@@ -720,8 +726,27 @@ class TestArmIKInputValidationContract(unittest.TestCase):
         for side in ("L", "R"):
             p_fore = self.armature.pose.bones[f"forearm.{side}"]
             p_hand = self.armature.pose.bones[f"hand.{side}"]
-            self.assertNotIn(ARM_IK_CONSTRAINT_NAMES[side], p_fore.constraints)
-            self.assertNotIn(HAND_ROT_CONSTRAINT_NAMES[side], p_hand.constraints)
+
+            if side == "L":
+                self.assertIn(ARM_IK_CONSTRAINT_NAMES["L"], p_fore.constraints)
+
+                restored_ik = p_fore.constraints[ARM_IK_CONSTRAINT_NAMES["L"]]
+
+                self.assertEqual(
+                    int(restored_ik.as_pointer()),
+                    existing_ik_ptr
+                )
+                self.assertEqual(restored_ik.target, hand_l)
+            else:
+                self.assertNotIn(
+                    ARM_IK_CONSTRAINT_NAMES[side],
+                    p_fore.constraints
+                )
+
+            self.assertNotIn(
+                HAND_ROT_CONSTRAINT_NAMES[side],
+                p_hand.constraints
+            )
```

### 1.2 `tests/test_task10b_transaction_atomicity.py`（`TEST-64`）

```diff
diff --git a/tests/test_task10b_transaction_atomicity.py b/tests/test_task10b_transaction_atomicity.py
index 5c1fc46..b0f39ea 100644
--- a/tests/test_task10b_transaction_atomicity.py
+++ b/tests/test_task10b_transaction_atomicity.py
@@ -1492,69 +1492,155 @@ class TestArmIKTransactionAtomicity(unittest.TestCase):
         self.assertEqual(called, ["test_stage_dummy"])
 
     def test_64_commit_cleanup_failure_and_datablock_lifecycle(self) -> None:
-        """TEST-64: Commit cleanup removes orphaned Data Blocks, preserves shared Data Blocks, and reports cleanup errors.
+        """TEST-64: Combined Mesh/Curve cleanup failure preserves both DataBlocks."""
+
+        # [2026-11-18] TEST-64: Verify the unique combined Mesh + shared Curve
+        # cleanup boundary without repeating the single-resource TEST-66 path.
 
-        Note: TEST-64 focuses specifically on data block reference counting and cleanup
-        error reporting. Complementary test TEST-66 verifies transaction state transitions
-        (COMMITTED / CLEANUP_PENDING) and retry_cleanup() idempotency.
-        """
-        # 1. Create DataBlocks before transaction
         mesh_data = bpy.data.meshes.new("DoomedMesh")
-        mesh_data_ptr = mesh_data.as_pointer()
+        mesh_ptr = int(mesh_data.as_pointer())
+
         curve_data = bpy.data.curves.new("SharedCurve", type="CURVE")
+        curve_ptr = int(curve_data.as_pointer())
+
         sharing_obj = bpy.data.objects.new("SharingCurveObj", curve_data)
         bpy.context.scene.collection.objects.link(sharing_obj)
 
         self.assertGreater(curve_data.users, 0)
 
-        # 2 & 3: Successful transaction commit with transaction-created wrong-type controllers
-        with _arm_rig_transaction(self.armature) as tx:
-            wrong_mesh_obj = bpy.data.objects.new("HandIK.L", mesh_data)
-            tx.register_created_controller(wrong_mesh_obj)
-            _authorized_link_object_to_collection(bpy.context.scene.collection, wrong_mesh_obj, tx)
+        captured_cleanup = []
 
-            wrong_curve_obj = bpy.data.objects.new("ElbowPole.L", curve_data)
-            tx.register_created_controller(wrong_curve_obj)
-            _authorized_link_object_to_collection(bpy.context.scene.collection, wrong_curve_obj, tx)
+        def fault_hook(stage: str, ctx: dict) -> None:
+            if stage == "during_commit_cleanup":
+                captured_cleanup.append(ctx["tx"])
+                raise RuntimeError("Simulated commit cleanup failure")
 
-            self.assertGreater(curve_data.users, 1)
+        _set_test_fault_injection_hook(fault_hook)
 
-            setup_arm_ik(self.armature)
+        try:
+            with self.assertRaisesRegex(
+                RuntimeError,
+                "Simulated commit cleanup failure"
+            ):
+                with _arm_rig_transaction(self.armature) as tx:
 
-        # Wrong-type controller HandIK.L is replaced with an EMPTY
-        self.assertEqual(bpy.data.objects["HandIK.L"].type, "EMPTY")
+                    wrong_mesh_obj = bpy.data.objects.new(
+                        "HandIK.L",
+                        mesh_data
+                    )
+                    tx.register_created_controller(wrong_mesh_obj)
 
-        # Doomed mesh data block has NO delete authority -> MUST be preserved
-        self.assertIn("DoomedMesh", bpy.data.meshes)
-        preserved_mesh = bpy.data.meshes["DoomedMesh"]
-        self.assertEqual(preserved_mesh.as_pointer(), mesh_data_ptr)
-        self.assertEqual(preserved_mesh.users, 0)
+                    _authorized_link_object_to_collection(
+                        bpy.context.scene.collection,
+                        wrong_mesh_obj,
+                        tx
+                    )
 
-        # Unauthorized preservation does NOT trigger cleanup pending
-        self.assertEqual(len(get_pending_arm_rig_cleanup_ids()), 0)
+                    wrong_curve_obj = bpy.data.objects.new(
+                        "ElbowPole.L",
+                        curve_data
+                    )
+                    tx.register_created_controller(wrong_curve_obj)
+
+                    _authorized_link_object_to_collection(
+                        bpy.context.scene.collection,
+                        wrong_curve_obj,
+                        tx
+                    )
+
+                    self.assertGreater(curve_data.users, 1)
+
+                    setup_arm_ik(self.armature)
+
+        finally:
+            _clear_test_fault_injection_hook()
+
+        self.assertEqual(len(captured_cleanup), 1)
+        self.assertIs(captured_cleanup[0], tx)
+
+        self.assertEqual(
+            tx.state,
+            _ArmRigTransactionState.CLEANUP_PENDING
+        )
+
+        self.assertIn(
+            tx.tx_id,
+            get_pending_arm_rig_cleanup_ids()
+        )
+
+        self.assertGreaterEqual(
+            len(tx.uncleaned_stashed_objects),
+            2
+        )
+
+        # Both active controllers have already been replaced.
+        self.assertEqual(
+            bpy.data.objects["HandIK.L"].type,
+            "EMPTY"
+        )
+        self.assertEqual(
+            bpy.data.objects["ElbowPole.L"].type,
+            "EMPTY"
+        )
+
+        # The failed cleanup must not destroy either original DataBlock.
+        self.assertIn("DoomedMesh", bpy.data.meshes)
+        self.assertEqual(
+            int(bpy.data.meshes["DoomedMesh"].as_pointer()),
+            mesh_ptr
+        )
 
-        # Shared curve object replaced with an EMPTY, but shared curve data block preserved!
-        self.assertEqual(bpy.data.objects["ElbowPole.L"].type, "EMPTY")
         self.assertIn("SharedCurve", bpy.data.curves)
-        self.assertIs(sharing_obj.data, curve_data)
+        self.assertEqual(
+            int(bpy.data.curves["SharedCurve"].as_pointer()),
+            curve_ptr
+        )
+        self.assertEqual(sharing_obj.data, curve_data)
 
-        # 4. Injected commit cleanup failure reports explicit RuntimeError
-        def fault_hook(stage: str, ctx: dict) -> None:
-            if stage == "during_commit_cleanup":
-                raise RuntimeError("Simulated commit cleanup failure")
+        # Retry the real Coordinator-owned cleanup.
+        retry_pending_arm_rig_cleanup(tx.tx_id)
 
-        _set_test_fault_injection_hook(fault_hook)
+        self.assertEqual(
+            tx.state,
+            _ArmRigTransactionState.COMMITTED
+        )
 
-        # Add another wrong-type object to trigger commit cleanup
-        mesh_data_2 = bpy.data.meshes.new("DoomedMesh2")
+        self.assertNotIn(
+            tx.tx_id,
+            get_pending_arm_rig_cleanup_ids()
+        )
 
-        with self.assertRaises(RuntimeError) as cm:
-            with _arm_rig_transaction(self.armature) as tx2:
-                wrong_obj_2 = bpy.data.objects.new("HandIK.R", mesh_data_2)
-                tx2.register_created_controller(wrong_obj_2)
-                _authorized_link_object_to_collection(bpy.context.scene.collection, wrong_obj_2, tx2)
-                setup_arm_ik(self.armature)
-        self.assertIn("Simulated commit cleanup failure", str(cm.exception))
+        self.assertEqual(len(tx.uncleaned_stashed_objects), 0)
+
+        # Neither DataBlock has deletion authority.
+        self.assertIn("DoomedMesh", bpy.data.meshes)
+        self.assertEqual(
+            int(bpy.data.meshes["DoomedMesh"].as_pointer()),
+            mesh_ptr
+        )
+        self.assertEqual(bpy.data.meshes["DoomedMesh"].users, 0)
+
+        self.assertIn("SharedCurve", bpy.data.curves)
+        self.assertEqual(
+            int(bpy.data.curves["SharedCurve"].as_pointer()),
+            curve_ptr
+        )
+        self.assertEqual(sharing_obj.data, curve_data)
+        self.assertGreaterEqual(curve_data.users, 1)
+
+        outcomes = [
+            item for item in tx.datablock_cleanup_outcomes
+            if item.get("resource_name") == "DoomedMesh"
+        ]
+
+        self.assertTrue(
+            any(
+                item.get("status") == "PRESERVED_NO_DELETE_AUTHORITY"
+                for item in outcomes
+            )
+        )
+
+        self.assertEqual(len(_ACTIVE_TRANSACTION_STACK), 0)
```

---

## 2. 六项专项测试真实结果与原始日志

| 顺序 | 编号 | 测试类 / 方法 | 实际输出状态 | 判定 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `TEST-26` | `TestArmIKInputValidationContract.test_26_partial_init_invalid_new_parent_has_zero_scene_mutation` | `ok` | **PASS** |
| 2 | `TEST-64` | `TestArmIKTransactionAtomicity.test_64_commit_cleanup_failure_and_datablock_lifecycle` | `ok` | **PASS** |
| 3 | `BUG12-01` | `TestBug12RealCrossArmaturePending.test_bug12_01_retry_a_deletes_only_a_real_resources` | `ok` | **PASS** |
| 4 | `BUG12-02` | `TestBug12RealCrossArmaturePending.test_bug12_02_pending_both_gates_and_healthy_third_armature` | `ok` | **PASS** |
| 5 | `BUG12-03` | `TestBug12RealCrossArmaturePending.test_bug12_03_foreign_constraint_and_cleanup_result_cannot_be_borrowed` | `ok` | **PASS** |
| 6 | `BUG12-04` | `TestBug12RealCrossArmaturePending.test_bug12_04_failed_retry_a_keeps_b_real_resources_untouched` | `ok` | **PASS** |

* **汇总信号**：`Ran 6 tests in 0.581s` / `OK` / `FIX_B_TEST_COUNT 6` / `FIX_B_PASS True`
* **Blender 退出码**：`0`（`BLENDER_EXIT_CODE=0`）
* **原始证据日志路径**：
  * stdout：`docs/evidence/task10b15/work_package_b_stdout.log`（46 行）
  * stderr：`docs/evidence/task10b15/work_package_b_stderr.log`（0 bytes，空）

---

## 3. BUG12 资源形成路径边界说明（Section 五 & 七）

* `tests/test_bug12_cross_armature_real_resources.py`（Git Blob SHA 保持 `8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40` 未修改）中的 `_make_real_pending(arm, label)` 为每副 Armature 物理创建真实的 Blender `Mesh`（`BUG12_Mesh_{label}`）、`Object`（`BUG12_Object_{label}`）与 `forearm.L` PoseBone `LIMIT_ROTATION` `Constraint`（`BUG12_Constraint_{label}`）。
* 在 `arm_ik._arm_rig_transaction(arm)` 上下文中，测试代码主动将上述真实对象与真实约束按照生产暂存记录结构追加至 `tx.stashed_constraints` 与 `tx.stashed_objects`，并通过 `during_constraint_removal` 与 `during_cleanup_object_removal` 故障注入钩子阻止初始 C-API 删除，使 `arm_a` 与 `arm_b` 同时进入持有真实待清理 Blender Object/Constraint 的 `CLEANUP_PENDING` 状态。
* **证据边界**：`BUG12-01`~`BUG12-04` 真实证明了双 Armature 各自持有真实待清理 Blender Object/Constraint 时的清理重试隔离、跨 Armature 门禁隔离、跨 Armature 约束删除授权与 `_CleanupResult` 防借用以及无 Type-A 删除授权外部 Mesh（`PRESERVED_NO_DELETE_AUTHORITY`）保留行为；**该路径由测试在事务内主动构造暂存记录形成，并非通过两条完整 `setup_arm_ik()` 路径自然形成的双侧 Pending**。

---

## 4. 未运行项目与越界修改核查

* **未运行项目 (`NOT EXECUTED`)**：
  * 全量测试 / 四级回归：`NOT EXECUTED`
  * 已通过的 `TEST-127` / `TEST-149` / `TEST-147` / `TEST-155`：`NOT EXECUTED`
  * `fix6-bug3` 冻结专项（`fix6-bug3_round1_frozen.py` / `TEST-249`~`253`）：`NOT EXECUTED`
  * `fix-7` 及其他范围外测试：`NOT EXECUTED`
* **是否发生越界修改**：**否**。
  * `src/` 下所有生产代码：零修改。
  * `tests/test_bug12_cross_armature_real_resources.py` 及其他测试文件、测试注册表和运行器：零修改。
  * `CORE_REPAIR_LEDGER.md`、架构及治理文件、其他历史证据与既有 7 项未跟踪文件：零修改。
  * 仅修改 `tests/test_task10b_input_validation.py`（`TEST-26`）与 `tests/test_task10b_transaction_atomicity.py`（`TEST-64`），并新增本轮 3 份证据文件。
