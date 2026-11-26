# TASK 10-B / fix-5 — R2-TAIL-02 TEST REPORT

* **任务编号 / 子任务**：TASK 10-B / fix-5 — `R2-TAIL-02` (TEST ONLY)
* **代码评审门禁**：`CODE REVIEW APPROVED`
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试基准 Commit SHA**：`fcc7537825d430910a4602f3acce125b86d023fb`
* **Blender 版本**：`Blender 5.1.1` (`build date: 2026-04-14 01:37:22`, `hash: b70da489d7f4`, `branch: blender-v5.1-release`, `Release`)
* **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (`APPROVED`)
* **源码与测试零改动证明**：测试执行期间 `src/` 与 `tests/` 零修改（`git diff --exit-code` 与 `git diff --cached --exit-code` 均为 `0`），全部历史未跟踪文件及历史证据保持完好。
* **完整原始日志**：[r2_tail_02_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-5/r2_tail_02_test_execution.log)

---

## 1. 第一组：原有 Collection 专项测试 (`tests/test_task10b_transaction_atomicity.py`)

| 编号 | 完整方法名 (`TestArmIKTransactionAtomicity.*`) | 测试数 | 耗时 | 退出码 | 结果 | 原始异常捕获与资源状态 | 测试前后 SHA |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **TEST-198** | `test_198_collection_creation_fault_before_registration_no_orphan` | 1 | 0.248s | `0` | **PASS** | 预期注入 `RuntimeError("Fault injected before Character collection registration")`，零孤立 Collection 残留 | `fcc75378...23fb` -> 一致 |
| **TEST-199** | `test_199_collection_fault_after_registration_before_link_rolls_back` | 1 | 0.265s | `0` | **PASS** | 预期注入 `RuntimeError("Fault injected after registration before scene link")`，按指针回滚删除已登记 Collection | `fcc75378...23fb` -> 一致 |
| **TEST-200** | `test_200_collection_fault_after_link_rolls_back_parent_child_and_collection` | 1 | 0.239s | `0` | **PASS** | 预期注入 `RuntimeError("Fault injected after scene link")`，解绑父子链接并清理 Collection | `fcc75378...23fb` -> 一致 |
| **TEST-201** | `test_201_pre_existing_character_collection_preserved_on_reentry` | 1 | 0.242s | `0` | **PASS** | 无异常；已有 `Character` Collection 重复初始化保持指针与子级/对象成员不变 | `fcc75378...23fb` -> 一致 |

**组 1 逐项独立执行命令模板**：
```powershell
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.<METHOD_NAME>'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```

---

## 2. 第二组：登记原子性故障注入验证（纯内存 `--python-expr`，无持久测试文件）

* **执行命令**：通过 Blender 5.1.1 `--background --python-exit-code 1 --python-expr $pyExpr` 执行内存测试类 `R2Tail02CollectionAtomicityFaultTests`（完整脚本与原文输出见 [r2_tail_02_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-5/r2_tail_02_test_execution.log#L89-L471)）。
* **退出码**：`0`（`Ran 7 tests in 0.626s`，`OK`）。
* **测试前后 SHA**：`fcc7537825d430910a4602f3acce125b86d023fb` -> `fcc7537825d430910a4602f3acce125b86d023fb`。

| 项目 | 测试方法 | 结果 | 原始异常 | 内存登记前后状态对比 | 记录残留 | 非授权删除 |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: |
| **A** | `test_A_normal_collection_registration` | **PASS** | 无异常；事务正常 `COMMITTED` | 前：`reg_len=0, rc_len=0`<br>后：`[{'col_ref': TxColA_R2T02, 'col_ptr': 2746224726792, ...}]`, `receipt_keys=[2746224726792]` | 无 | 无 |
| **B** | `test_B_registry_append_failure_leaves_zero_residual` | **PASS** | `Injected fault BEFORE registry.append` 原样传播 | 前：`reg_len=1, rc_keys=[2746226302856]`<br>后：`reg_len=1, rc_keys=[2746226302856]`（先有 `PriorCol_B` 原对象保留） | 无 | 无 (`TargetCol_B` 未被 Layer 2 删除) |
| **C** | `test_C_fault_after_registry_append_undoes_only_current_record` | **PASS** | `Injected fault AFTER registry.append` 原样传播 | 前：`reg_ptrs=[2746195143048], rc_keys=[2746195143048]`<br>后：`reg_ptrs=[2746195143048], rc_keys=[2746195143048]`（仅撤销当前新记录） | 无 | 无 |
| **D** | `test_D_fault_before_receipt_write_undoes_registry_and_propagates` | **PASS** | `Injected fault BEFORE receipt.__setitem__` 原样传播（端到端 `_ensure_character_collection()` 亦仅抛出该原异常，无 `COLLECTION_CREATION_CLEANUP_FAILED`） | `[D1]` 前：`reg_ptrs=[2746283234056], rc_keys=[2746283234056]`<br>`[D1]` 后：`reg_ptrs=[2746283234056], rc_keys=[2746283234056]`<br>`[D2]` Layer 3 自动清除了未登记 `"Character"` | 无 | 无（`PriorCol_D` 完整保留） |
| **E** | `test_E_fault_after_receipt_write_undoes_both_and_preserves_prior` | **PASS** | `Injected fault AFTER receipt.__setitem__` 原样传播 | 前：`reg_ptrs=[2746268309512], rc_keys=[2746268309512]`<br>后：`reg_ptrs=[2746268309512], rc_keys=[2746268309512]`（本次双边写入均被撤销） | 无 | 无 |
| **F** | `test_F_undo_failure_propagates_dual_exceptions` | **PASS** | `[F1] COLLECTION_REGISTRATION_ROLLBACK_FAILED: original=RuntimeError: Injected fault BEFORE receipt.__setitem__; rollback=RuntimeError: Injected registry.pop failure during undo`<br>`[F2] COLLECTION_REGISTRATION_ROLLBACK_FAILED: original=RuntimeError: Injected fault AFTER receipt.__setitem__; rollback=RuntimeError: Injected receipt.pop failure during undo` | 明确失败，未报告登记成功，未伪造完整恢复状态 | 不适用（显式报错拒绝伪装一致） | 无 |
| **G** | `test_G_external_and_other_tx_resources_protected` | **PASS** | 预存在外部 Collection 抛出 `COLLECTION_OWNERSHIP_UNPROVEN: Collection was not created after transaction entry`；后续事务内写失败回滚，抛出 `Injected fault BEFORE receipt.__setitem__` 且 `tx.state == ROLLED_BACK` | 外部 `OrigExtCol_G` 与独立 `other_tx` 的登记/凭据均维持原对象引用与指针不变 | 无 | 无（未误删 `OrigExtCol_G` 或 `TxFailCol_G`） |

---

## 3. 第三组：保护性回归测试 (`tests/test_task10b_transaction_atomicity.py`)

| 编号 | 完整方法名 (`TestArmIKTransactionAtomicity.*`) | 测试数 | 耗时 | 退出码 | 结果 | 原始异常捕获与说明 | 测试前后 SHA |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| **TEST-202** | `test_202_constraints_created_via_layer_3_with_identity_registration` | 1 | 0.241s | `0` | **PASS** | 无异常；Constraint 创建与身份登记完全正常 | `fcc75378...23fb` -> 一致 |
| **TEST-203** | `test_203_constraint_fault_after_creation_before_registration_cleaned_up` | 1 | 0.259s | `0` | **PASS** | 预期注入登记前 Constraint 故障并按指针清理，保留外部 Constraint | `fcc75378...23fb` -> 一致 |
| **TEST-204** | `test_204_constraint_fault_after_registration_before_config_rolls_back` | 1 | 0.245s | `0` | **PASS** | 预期注入配置前故障并由 Layer-3 回滚清除已登记 Constraint | `fcc75378...23fb` -> 一致 |
| **TEST-207** | `test_207_stashed_constraint_cleanup_only_removes_authorized_identity` | 1 | 0.246s | `0` | **PASS** | 提交清理仅删除获授权身份的暂存 Constraint，同名替换保留 | `fcc75378...23fb` -> 一致 |
| **TEST-208** | `test_208_constraint_cleanup_fault_enters_cleanup_pending_and_retry_succeeds` | 1 | 0.239s | `0` | **PASS** | 清理故障进入 `CLEANUP_PENDING`，重试清理幂等收敛成功 | `fcc75378...23fb` -> 一致 |

---

## 4. 验收准则核对汇总

1. 原有 Collection 测试全部通过：**4/4 PASS** (`TEST-198`, `TEST-199`, `TEST-200`, `TEST-201`)。
2. 登记原子性故障验证全部通过：**7/7 PASS** (`A`, `B`, `C`, `D`, `E`, `F`, `G`)。
3. 保护性回归测试全部通过：**5/5 PASS** (`TEST-202`, `TEST-203`, `TEST-204`, `TEST-207`, `TEST-208`)。
4. 已有登记记录、其他事务记录与外部原始 Collection 均得到保护，未产生任何单边残留或非授权物理删除。
5. 原始登记异常与双重撤销失败异常均清晰传播，无异常吞没。
6. 未修改任何生产源码、测试代码、测试断言或治理文件；未运行 `TEST-26` 修改或四级全量回归。
