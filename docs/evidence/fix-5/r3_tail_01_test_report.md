# TASK 10-B / fix-5 — R3-TAIL-01 TEST REPORT

* **任务编号 / 子任务**：TASK 10-B / fix-5 — `R3-TAIL-01` (TEST ONLY)
* **冻结问题描述**：`R3-TAIL-01` — Constraint 创建登记异常与补救清理不完整（验收合同：创建 → 立即登记 → 授权配置；失败时只能清理具有可信创建身份的 Constraint；清理失败必须显式传播异常）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试基准 Commit SHA**：`e039874e7c82c447e4ea57c77b77b27a63f6d114`
* **Blender 版本**：`Blender 5.1.1` (`build date: 2026-04-14 01:37:22`, `hash: b70da489d7f4`, `branch: blender-v5.1-release`, `Release`)
* **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (`APPROVED`)
* **源码与测试零改动证明**：测试前后 `git diff --exit-code` 与 `git diff --cached --exit-code` 均为 `0`，`src/` 与 `tests/` 零修改；既有 `docs/evidence/fix-5/r2_tail_02_*`、`docs/evidence/fix-4/*` 及全部历史未跟踪文件保持原状。
* **完整原始日志**：[r3_tail_01_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-5/r3_tail_01_test_execution.log)

---

## 1. 第一组：已有 Constraint 专项测试 (`tests/test_task10b_transaction_atomicity.py`)

执行结果：**7/7 PASS** (`FAIL: 0`, `NOT EXECUTED: 0`)

| 编号 | 完整方法名 (`TestArmIKTransactionAtomicity.*`) | 测试数 | 耗时 | 退出码 | 状态 | 观察到的验证结果 | 测试前后 SHA |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **TEST-202** | `test_202_constraints_created_via_layer_3_with_identity_registration` | 1 | 0.239s | `0` | **PASS** | `ArmIK.L`、`ArmIK.R`、`HandRotation.L`、`HandRotation.R` 通过 Layer 3 创建并按真实指针身份登记 | `e039874e...d114` -> 一致 |
| **TEST-203** | `test_203_constraint_fault_after_creation_before_registration_cleaned_up` | 1 | 0.236s | `0` | **PASS** | 创建后登记前故障按指针清理新建实例，保留外部 `ExternalLimit203` | `e039874e...d114` -> 一致 |
| **TEST-204** | `test_204_constraint_fault_after_registration_before_config_rolls_back` | 1 | 0.248s | `0` | **PASS** | 登记后配置前故障通过 Layer 5 → Layer 3 回滚删除已登记 `ArmIK.L`，保留 `PreExistingExt204` | `e039874e...d114` -> 一致 |
| **TEST-205** | `test_205_stashed_constraint_lossless_rollback_recovery` | 1 | 0.244s | `0` | **PASS** | 原有暂存 Constraint 在回滚后无损恢复（ref、ptr、name、mute、顺序） | `e039874e...d114` -> 一致 |
| **TEST-206** | `test_206_external_same_name_constraint_on_other_bone_not_deleted` | 1 | 0.226s | `0` | **PASS** | 其他 PoseBone 上的外部同名 Constraint (`ArmIK.L`) 在回滚或清理中绝不误删 | `e039874e...d114` -> 一致 |
| **TEST-207** | `test_207_stashed_constraint_cleanup_only_removes_authorized_identity` | 1 | 0.222s | `0` | **PASS** | 提交后清理仅删除获授权身份的暂存 Constraint，同名替换对象保留 | `e039874e...d114` -> 一致 |
| **TEST-208** | `test_208_constraint_cleanup_fault_enters_cleanup_pending_and_retry_succeeds` | 1 | 0.224s | `0` | **PASS** | 提交后清理故障进入 `CLEANUP_PENDING`，后续重试幂等收敛 | `e039874e...d114` -> 一致 |

**组 1 逐项独立执行命令模板**：
```powershell
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.<METHOD_NAME>'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```

---

## 2. 第二组：创建登记故障窗口验证（纯内存 `--python-expr`，无持久测试文件）

* **执行命令**：`"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr <IN_MEMORY_EXPR>`（完整脚本原文与输出见 [r3_tail_01_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-5/r3_tail_01_test_execution.log#L161-L768)）
* **测试类**：`TestR3Tail01Group2FaultWindows`
* **退出码**：`0`（`Ran 8 tests in 0.676s`，`OK`）
* **测试前后 SHA**：`e039874e7c82c447e4ea57c77b77b27a63f6d114` -> `e039874e7c82c447e4ea57c77b77b27a63f6d114`
* **结果汇总**：**A–F（8/8 子用例）全部 PASS** (`FAIL: 0`, `NOT EXECUTED: 0`)

| 窗口 | 测试方法 | 状态 | 故障注入窗口与验证结果 | 资源与外部约束保护结论 |
| :---: | :--- | :---: | :--- | :--- |
| **A** | `test_A_failure_before_receipt_write` | **PASS** | `_RaiseBeforeSetitemDict.__setitem__` 在 `_constraint_creation_receipts` 写入前抛出 `INJECTED_BEFORE_RECEIPT_WRITE`；异常向上传播至事务外层；`tx.state == ROLLED_BACK` | 新建 `ArmIK.L` 被即时清理（`forearm.L` 仅余 `ExtPreA`），`_constraint_creation_receipts` 与 `created_constraints` 均为空，`ExtPreA` 与 `upper_arm.L` 上同名外部 `ArmIK.L` 保持原引用及指针 |
| **B** | `test_B_failure_after_receipt_write` | **PASS** | `_RaiseAfterSetitemDict.__setitem__` 确认 `key in self` 写入后再抛出 `INJECTED_AFTER_RECEIPT_WRITE`；真实 `_cleanup_failed_constraint_creation` 被触发一次，并调用 `pbone.constraints.remove` 删除新建实例且从 `_constraint_creation_receipts` 撤销该指针 | `forearm.L` 无 `ArmIK.L` 及该指针残留，无孤立凭据残留；`ExtPreB` 与 `upper_arm.L` 上同名外部 `ArmIK.L` 保持完整 |
| **C** | `test_C_failure_before_registry_append` | **PASS** | `_RaiseBeforeAppendList.append` 在 `created_constraints.append()` 写入前抛出 `INJECTED_BEFORE_REGISTRY_APPEND` 并传播；真实 `_cleanup_failed_constraint_creation` 执行清理并撤销凭据 | `created_constraints` 长度为 0（无非法登记记录），`_constraint_creation_receipts` 长度为 0，新建 Constraint 从 `forearm.L` 删除；外部 `ExtPreC` 与 `upper_arm.L` 的 `ArmIK.L` 完整保留 |
| **D** | `test_D_failure_after_registry_append` | **PASS** | `_RaiseAfterAppendList.append` 追加记录后再抛出 `INJECTED_AFTER_REGISTRY_APPEND`；`_cleanup_failed_constraint_creation` 识别到已登记记录，保持 `forearm.L` 列表为 `['ExtFirstD', 'ExtSecondD', 'ArmIK.L']` 未重复删除；外层事务由 Layer 5 `_rollback_arm_rig_state` 调用 Layer 3 `_authorized_remove_constraint(phase='ROLLBACK')` 完成唯一一次删除，`tx.state == ROLLED_BACK` | 新建 `ArmIK.L`（及指针）彻底清除；`forearm.L` 恢复精确顺序 `['ExtFirstD', 'ExtSecondD']`，两者 `ref`/`as_pointer()`/`type`/`mute`/`influence` 与 `upper_arm.L` 的 `ArmIK.L` 全部零漂移 |
| **E1** | `test_E1_cleanup_failure_real_authority_unproven` | **PASS** | 通过内置 `character_constraint_after_creation_before_registration` 钩子将 `tx._constraint_creation_receipts` 破坏为非 `dict` 并抛出 `ORIGINAL_CREATION_FAULT_E1`；**未替换 `_cleanup_failed_constraint_creation`**，真实触发第 3214 行 `CONSTRAINT_CREATION_CLEANUP_AUTHORITY_UNPROVEN: receipt ledger malformed`；外层封装为 `CONSTRAINT_CREATION_CLEANUP_FAILED` 并保留原异常、`清理异常` 与 `__cause__`；事务终态 `FAILED`（拒绝 `ROLLED_BACK`）。*注：本子用例验证的是真实权限校验失败拦截，非 Blender C-API `constraints.remove()` 底层删除报错* | 未扩大删除权限：`ExtPreE1` 与 `upper_arm.L` 的同名 `ArmIK.L` 保持原引用及指针不变 |
| **E2** | `test_E2_ERROR_PROPAGATION_ONLY_monkeypatched_cleanup` | **PASS** | **`ERROR_PROPAGATION_ONLY`**：内存态临时替换 `arm_ik._cleanup_failed_constraint_creation` 抛出 `SIMULATED_CLEANUP_EXC_E2` 同时注入 `ORIGINAL_CREATION_FAULT_E2`；验证 `CONSTRAINT_CREATION_CLEANUP_FAILED` 同时包含原异常与补偿异常、保留 `__cause__`，且事务进入 `FAILED`（绝不标为 `ROLLED_BACK`）。*严格声明：按治理约定标注为 `ERROR_PROPAGATION_ONLY`，不宣称为真实 Blender 物理删除失败验证* | 未扩大删除权限：`ExtPreE2` 与 `upper_arm.L` 的 `ArmIK.L` 原封保留 |
| **F1** | `test_F1_missing_receipt_rejects_deletion` | **PASS** | 正常创建并登记后删除 `_constraint_creation_receipts[new_ptr]` 再抛出 `FAULT_TRIGGER_ROLLBACK_F1`；Layer 5 预检拒绝未经凭据证明的删除，抛出 `Rollback constraint restoration failed` 并保留 `FAULT_TRIGGER_ROLLBACK_F1` 为 `__cause__`，事务终态 `FAILED`（非 `ROLLED_BACK`） | 不按名称替代删除：`ExtPreF1` 与 `upper_arm.L` 上的同名 `ArmIK.L`（以及未获凭据证明的 `new_con`）均未被非法删除 |
| **F2** | `test_F2_corrupted_receipt_and_same_name_bone_refuses_deletion` | **PASS** | 篡改 `tx._constraint_creation_receipts[new_ptr]` 的 PoseBone 为 `upper_arm.L` 且印章对象不匹配后触发回滚；在 `during_rollback_execution` 钩子中直接探测两次 Layer 3 `_authorized_remove_constraint(p_upper, ..., phase='ROLLBACK')` 均明确拒绝；Layer 5 拒绝回滚，保留 `FAULT_TRIGGER_ROLLBACK_F2` 与拒绝原因，事务终态 `FAILED` | 不按名称或跨骨骼替代删除：`upper_arm.L` 上同名外部 `ArmIK.L` 与 `forearm.L` 上 `ExtPreF2` 均保持原引用及指针不变 |

---

## 3. 第三组：原有 Constraint 保护性验证 (`tests/test_task10b_transaction_atomicity.py`)

执行结果：**5/5 PASS** (`FAIL: 0`, `NOT EXECUTED: 0`)

| 编号 | 完整方法名 (`TestArmIKTransactionAtomicity.*`) | 测试数 | 耗时 | 退出码 | 状态 | 观察到的验证结果 | 测试前后 SHA |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **TEST-38** | `test_38_direct_rollback_constraints` | 1 | 0.243s | `0` | **PASS** | 直接回滚恢复约束数量、顺序、类型、名称、目标与影响力 | `e039874e...d114` -> 一致 |
| **TEST-103** | `test_103_transaction_created_constraint_cleaned_up_by_identity` | 1 | 0.226s | `0` | **PASS** | 事务内新建 Constraint 在回滚时按指针身份完全清除，快照状态还原 | `e039874e...d114` -> 一致 |
| **TEST-104** | `test_104_external_constraint_preserved_on_transaction_failure` | 1 | 0.241s | `0` | **PASS** | 事务失败后外部约束 `ExternalCopyRot104` 引用、指针及属性完整保留 | `e039874e...d114` -> 一致 |
| **TEST-105** | `test_105_same_name_different_identity_constraint_not_erroneously_deleted` | 1 | 0.234s | `0` | **PASS** | 同名不同指针身份 Constraint 绝不被回滚误删 | `e039874e...d114` -> 一致 |
| **TEST-106** | `test_106_external_constraint_insertion_preserves_original_constraint_order` | 1 | 0.249s | `0` | **PASS** | 在真实 Coordinator 事务中插入外部约束并扰动顺序，回滚后外部约束保留且原约束相对顺序恢复 | `e039874e...d114` -> 一致 |

---

## 4. 状态分类总览与约束核对

* **PASS**：第一组 7/7（`TEST-202`..`TEST-208`）；第二组 A–F 8/8（含 `E1` 真实权限拦截及明确标注 `ERROR_PROPAGATION_ONLY` 的 `E2`）；第三组 5/5（`TEST-38`, `TEST-103`..`TEST-106`）。
* **FAIL**：`0` 项。
* **NOT EXECUTED**：四级全量回归按任务要求 `NOT EXECUTED`（本轮仅执行 R3-TAIL-01 专项三组测试，未触摸 `TEST-26`、`R2-TAIL-02` 或生产源码）。
* **架构与修改约束确认**：
  * 未修改 `src/`、`tests/`、`WORKFLOW_GOVERNANCE.md` 或任何架构文档；
  * 未创建 `apply_*.py`、`*.patch`、`*.diff` 或持久测试脚本；
  * 未合并 `master`，未自行关闭 `R3-TAIL-01`，停止并等待 ChatGPT 独立验收。
