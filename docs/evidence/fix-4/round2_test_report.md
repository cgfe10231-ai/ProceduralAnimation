# TASK 10-B / fix-4 — ROUND 2/2 TEST REPORT

- **任务定位**：TASK 10-B / fix-4 — Round 2/2 (TEST ONLY)
- **项目仓库**：`cgfe10231-ai/ProceduralAnimation`
- **分支**：`audit/task-10-b-9`
- **固定基线 HEAD**：`6bb159d291d65ab611ed73701a99c04397343b18`
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md`（已核对状态：`APPROVED`）
- **执行引擎**：`Blender 5.1.1` (build date: `2026-04-14 01:37:22`, commit hash: `b70da489d7f4`, branch: `blender-v5.1-release`, Release)
- **生产/测试代码改动**：**0 字节修改**（`git diff --exit-code` 与 `git diff --cached --exit-code` 均为 `0`）
- **总结状态**：**BLOCKED（组 C1 `tests/test_task10b_input_validation.py` 中的 `TEST-26` 失败，触发“任意失败立即熔断”规则，组 C2 未执行，未进行任何代码/测试修改或成功提交）**

---

## 1. 测试执行总览（按执行组逐项独立可追溯）

### 1.1 专项测试组 A：既有 Constraint 合同 (`tests/test_task10b_transaction_atomicity.py`)

> 原始日志：[round2_group_a_existing_contracts.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/round2_group_a_existing_contracts.log)

| 序号 | 编号 | 测试方法 (`TestArmIKTransactionAtomicity.*`) | 测试数 | 耗时 | 退出码 | 结果 | 原始异常 / 注入触发说明 | 是否发生 FAILED 隔离 | 前后 HEAD |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- |
| 1 | **TEST-38** | `test_38_direct_rollback_constraints` | 1 | 0.260s | `0` | **PASS** | 注入 `RuntimeError("Fault injected in TEST-38")` 被外层捕获，事务正常 `ROLLED_BACK` | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 2 | **TEST-77** | `test_77_destroyed_constraint_identity_is_rejected` | 1 | 0.317s | `0` | **PASS** | 验证器按预期抛出原约束销毁/身份不匹配 `RuntimeError` | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 3 | **TEST-78** | `test_78_destroyed_constraint_causes_rollback_failure` | 1 | 0.388s | `0` | **PASS** | 注入原约束删除与业务故障，回滚正确报错原约束销毁且未捕获未预期异常 | 按既有 TEST-78 合同隔离（测试断言通过） | `6bb159d2...43b18` -> 一致 |
| 4 | **TEST-103** | `test_103_transaction_created_constraint_cleaned_up_by_identity` | 1 | 0.390s | `0` | **PASS** | `setup_arm_ik` R 侧注入故障触发全量回滚，L/R 约束按指针清除 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 5 | **TEST-104** | `test_104_external_constraint_preserved_on_transaction_failure` | 1 | 0.798s | `0` | **PASS** | 注入 `Fault during hand location in TEST-104`，外部 `ExternalCopyRot104` 指针与属性完整保留 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 6 | **TEST-105** | `test_105_same_name_different_identity_constraint_not_erroneously_deleted` | 1 | 0.364s | `0` | **PASS** | `upper_arm.L` 同名 `ArmIK.L` 异指针约束在回滚后 100% 保留 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 7 | **TEST-106** | `test_106_external_constraint_insertion_preserves_original_constraint_order` | 1 | 0.385s | `0` | **PASS** | 注入 `Fault injected in TEST-106`，保留 `ExtFirst106` 且恢复 `ArmIK.L`/`OrigLimit106` 相对顺序 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 8 | **TEST-202** | `test_202_constraints_created_via_layer_3_with_identity_registration` | 1 | 0.364s | `0` | **PASS** | 正常创建并登记 4 条约束，引用/指针/骨骼一致 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 9 | **TEST-203** | `test_203_constraint_fault_after_creation_before_registration_cleaned_up` | 1 | 0.381s | `0` | **PASS** | `character_constraint_after_creation_before_registration` 故障下未登记约束被按指针清除并保留外部约束 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 10 | **TEST-204** | `test_204_constraint_fault_after_registration_before_config_rolls_back` | 1 | 0.394s | `0` | **PASS** | `character_constraint_after_registration_before_config` 故障下已登记约束交由 Layer-3 回滚清除 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 11 | **TEST-205** | `test_205_stashed_constraint_lossless_rollback_recovery` | 1 | 0.370s | `0` | **PASS** | R 侧故障回滚后暂存错型约束引用、指针、名称、mute、顺序无损恢复 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |
| 12 | **TEST-206** | `test_206_external_same_name_constraint_on_other_bone_not_deleted` | 1 | 0.395s | `0` | **PASS** | 回滚与提交清理均未误删 `upper_arm.L` 上同名外部约束 | 否 (`NONE`) | `6bb159d2...43b18` -> 一致 |

**组 A 逐项执行命令模板**：
```powershell
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.<METHOD_NAME>'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```
*组 A 统计：12 项独立运行全部 PASS（12/12 PASS，EXIT_CODE 均为 0）。*

---

### 1.2 专项测试组 B：本轮新增合同的负向验证（纯内存 Blender `--python-expr` 执行，无新增持久测试文件）

> 原始日志：[round2_group_b_negative_contracts.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/round2_group_b_negative_contracts.log)

| 序号 | 验证编号 | 内存测试方法 (`NegativeFix4Verification.*`) | 测试数 | 耗时 | 退出码 | 结果 | 前后 HEAD |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | **B1** | `test_b1_whole_table_precheck_blocks_partial_deletion` | 1 | (合跑 2 项共 0.549s) | `0` | **PASS** | `6bb159d2...43b18` -> 一致 |
| 2 | **B2** | `test_b2_invalid_receipt_ledger_blocks_creation_before_c_api` | 1 | (合跑 2 项共 0.549s) | `0` | **PASS** | `6bb159d2...43b18` -> 一致 |

#### 验证 B1 原始运行时证据：
- **故障注入前 Constraint 数量与指针集合**：
  - `forearm.L` (2 条): `[('OrigPreCheckL_B1', 1807984928888), ('TxCon1_B1', 1807984920600)]`
  - `forearm.R` (2 条): `[('OrigPreCheckR_B1', 1807984928664), ('TxCon2_B1', 1807984920824)]`
- **扰动与触发**：在 `ACTIVE` 事务内将第 2 条登记记录 `tx.created_constraints[1]['bone_name']` 篡改为 `'upper_arm.R'`（使其与真实所属 `PoseBone('forearm.R')` 不一致），随后触发 `RuntimeError('Injected fault in negative B1 test')`。
- **实际传播异常**：
  ```text
  Arm rig transaction failed with RuntimeError: Injected fault in negative B1 test, AND rollback verification failed with RuntimeError: Rollback constraint restoration failed: Constraint rollback rejected: PoseBone reference mismatch for bone 'upper_arm.R' (ptr=1807984920824); Constraint rollback rejected: receipt pose bone reference mismatch for ptr=1807984920824
  ```
- **回滚失败后 Constraint 数量与指针集合（零部分删除）**：
  - `forearm.L` (2 条): `[('OrigPreCheckL_B1', 1807984928888), ('TxCon1_B1', 1807984920600)]` —— 排在遍历顺序前方的第 1 条事务创建约束 `TxCon1_B1` 未被提前删除，原始约束 `OrigPreCheckL_B1` 保持不变。
  - `forearm.R` (2 条): `[('OrigPreCheckR_B1', 1807984928664), ('TxCon2_B1', 1807984920824)]` —— 第 2 条事务创建约束 `TxCon2_B1` 及原始约束 `OrigPreCheckR_B1` 均未被删除。
- **Coordinator 终态与 FAILED 隔离**：
  - `tx.state == _ArmRigTransactionState.FAILED`（未伪报 `ROLLED_BACK`）
  - `session_rec.isolation_state == _ArmatureIsolationState.ISOLATED_FAILED_B`
  - `session_id in _ISOLATED_FAILED_ARMATURES`，后续写操作被 `FAILED-B` 门禁拒绝，`_ACTIVE_TRANSACTION_STACK` 已清空。

#### 验证 B2 原始运行时证据：
- **进入前与扰动前 Constraint 数量与指针集合**：
  - `forearm.L` (1 条): `[('OrigPreCheckL_B2', 1807984920376)]`
  - `_authorized_create_constraint` 中 `pbone.constraints.new(...)` 真实源码行号：`C_API_LINE: 3365`
- **三条负向用例实际抛错行号及异常**：
  1. `NON_DICT_LEDGER` (`_constraint_creation_receipts = ['corrupt_list']`)：在 `_authorized_create_constraint:3342` 抛出 `CONSTRAINT_CREATION_RECEIPT_LEDGER_UNAVAILABLE`（严格早于第 `3365` 行 C-API）。
  2. `MALFORMED_ENTRY_LEDGER` (`_constraint_creation_receipts = {-1: ('bad_len',)}`)：在 `_authorized_create_constraint:3342` 抛出 `CONSTRAINT_CREATION_RECEIPT_LEDGER_UNAVAILABLE`（严格早于第 `3365` 行 C-API）。
  3. `MISSING_SEAL` (`_constraint_receipt_seal = None`)：在 `_authorized_create_constraint:3346` 抛出 `CONSTRAINT_CREATION_RECEIPT_SEAL_UNAVAILABLE`（严格早于第 `3365` 行 C-API）。
- **事后现场恢复与零残留**：
  - 测试后恢复原有 Ledger/Seal 测试状态，事务正常提交（`COMMITTED`），`_ACTIVE_TRANSACTION_STACK` 清空，**未发生 FAILED 隔离**。
  - 退出后 `forearm.L` (1 条): `[('OrigPreCheckL_B2', 1807984920376)]`，零新增未登记资源。

---

### 1.3 专项测试组 C：已有输入与生命周期回归

> 原始日志：[round2_group_c_regression.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/round2_group_c_regression.log)

| 序号 | 模块 | 完整执行命令 | 测试数 | 耗时 | 退出码 | 结果 | 详情 | 前后 HEAD |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| 1 | **C1 (`tests/test_task10b_input_validation.py`)** | `"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python tests\test_task10b_input_validation.py` | 30 | 5.046s | `1` | **FAIL (1 failed)** | **TEST-01 ~ TEST-25, TEST-27 ~ TEST-30 共 29 项通过；TEST-26 失败** | `6bb159d2...43b18` -> 一致 |
| 2 | **C2 (`tests/test_arm_ik_lifecycle_world_transform_contract.py`)** | 未执行（因 C1 失败触发熔断） | 0 | N/A | N/A | **UNEXECUTED** | 按“任意失败立即停止”纪律终止后续运行 | `6bb159d2...43b18` |

#### 组 C1 (`TEST-26`) 原始失败堆栈与只读调查事实：
- **失败用例**：`test_26_partial_init_invalid_new_parent_has_zero_scene_mutation` ([tests/test_task10b_input_validation.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_input_validation.py#L670-L725))
- **原始 Traceback**：
  ```text
  FAIL: test_26_partial_init_invalid_new_parent_has_zero_scene_mutation (__main__.TestArmIKInputValidationContract.test_26_partial_init_invalid_new_parent_has_zero_scene_mutation)
  TEST-26: Partially initialized arm IK with invalid new parent transform causes zero mutation.
  ----------------------------------------------------------------------
  Traceback (most recent call last):
    File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\tests\test_task10b_input_validation.py", line 711, in test_26_partial_init_invalid_new_parent_has_zero_scene_mutation
      self.assertIn("reflection", str(cm.exception).lower())
      ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  AssertionError: 'reflection' not found in "external_controller_name_conflict: set_hand_ik_target: controller 'handik.l' is present without a verified owning armature/transaction binding"
  ```
- **只读源码排查确认（未改动任何代码）**：
  1. `TEST-26` 第 686–697 行手工创建了无 Armature 约束绑定的独立 Empty 对象 `"HandIK.L"`（未通过 `setup_arm_ik` 绑定至 `self.armature` 骨骼约束），随后将 `root_obj.scale` 设为 `(-1.0, 1.0, 1.0)` 并调用 `set_hand_ik_target(...)`，预期因有效父矩阵反射检查触发包含 `"reflection"` 的 `ValueError`。
  2. `set_hand_ik_target()` 调用的 `_preflight_arm_ik_parent_transforms()`（[src/rig/arm_ik.py#L9285](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L9285)）先于反射矩阵验证执行 `_require_existing_arm_ik_controller_ownership(arm, scope='_preflight_arm_ik_parent_transforms')`（[src/rig/arm_ik.py#L2560-L2598](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L2560-L2598)，源自历史提交 `d917b30 fix: BUG-01 existing controller ownership admission`）。
  3. 因 `"HandIK.L"` 缺乏与 Armature 约束绑定且不在活动事务内，`_require_existing_arm_ik_controller_ownership()` 优先抛出 `ExternalControllerNameConflictError`（多重继承自 `(RuntimeError, ValueError)`，[src/rig/arm_ik.py#L303](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L303)），故被 `with self.assertRaises(ValueError)` 捕获后在第 711 行断言 `'reflection'` 失败。
  4. 同模块内与新所有权准入已对齐的 `TEST-28`、`TEST-29`、`TEST-30` 在本次执行中均为 `ok`。本次失败发生在 Controller 所有权准入门禁与 `TEST-26` 旧测试前置条件冲突处，与 fix-4 的 Constraint 凭据修复无直接代码更改冲突，但属于既有回归门禁失败，已严格依规立即熔断并停止。

---

## 2. 最终 Git 与工作区状态

- **当前分支**：`audit/task-10-b-9`
- **本地与远程 HEAD**：`6bb159d291d65ab611ed73701a99c04397343b18`（未推进，未在测试失败状态下创建提交）
- **生产代码及测试代码修改状态**：`git diff --exit-code` 与 `git diff --cached --exit-code` 均为 0（零修改）
- **本轮新增证据文件（`docs/evidence/fix-4/`，保留历史 8 份档案完好）**：
  - `docs/evidence/fix-4/round2_group_a_existing_contracts.log`
  - `docs/evidence/fix-4/round2_group_b_negative_contracts.log`
  - `docs/evidence/fix-4/round2_group_c_regression.log`
  - `docs/evidence/fix-4/round2_test_report.md`
- **七个历史受保护未跟踪文件**：原样保留（`P2_R1_recovery.patch`, `Untitled-1.cpp`, `round05_exact_apply.py`, `round05_exact_apply_v2.py`, `round05_exact_apply_v3.py`, `round05_exact_apply_v3_local.py`, `round05_validate_finalize_v3.py`）。
