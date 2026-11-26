# TASK 10-B / fix-4 修复前定点基线验证记录 (Baseline Test Report)

- **基线分支**：`audit/task-10-b-9`
- **基线 Commit HEAD**：`74e301bd3c53a5a09dd6f90316ae5685888348e4`
- **执行环境**：
  - 操作系统：Windows (PowerShell)
  - 引擎版本：Blender 5.1.1 (build date: `2026-04-14 01:37:22`, build hash: `b70da489d7f4`, Release)
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED, 2026-11-11)
- **阶段定位**：fix-4 修复前基线摸底验证 (TEST ONLY)

---

## 1. 测试执行情况总览

| 序号 | 测试编号 | 完整 unittest 方法名 | 进程退出码 | 运行耗时 | 测试数量 | 判定结果 | 执行状态 |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | **TEST-38** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints` | `1` | 0.260s | 1 | **ERROR** | 已执行，因回滚权限校验失败 |
| 2 | **TEST-106** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order` | N/A | N/A | 0 | **UNEXECUTED** | 熔断未执行 (因 TEST-38 失败) |

---

## 2. TEST-38 详细执行记录

- **测试编号**：TEST-38
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints`
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`1`
- **运行耗时**：`0.260s`
- **测试数量**：`Ran 1 test`
- **结果判定**：`FAILED (errors=1)`
- **首次失败位置**：[`tests/test_task10b_transaction_atomicity.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py#L600) 第 600 行（在调用 `_rollback_arm_rig_state()` 时抛出）
- **根因及异常信息**：
  在 [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L5570) 的 `_rollback_arm_rig_state()` 中：
  ```text
  RuntimeError: Rollback constraint restoration failed: Created controller entry-pointer baseline is unavailable; Controller recovery rejected: unsupported transaction state <_ArmRigTransactionState.CREATED: 'CREATED'> for 'HandIK.L'; Controller recovery rejected: unsupported transaction state <_ArmRigTransactionState.CREATED: 'CREATED'> for 'HandIK.R'; Controller recovery rejected: unsupported transaction state <_ArmRigTransactionState.CREATED: 'CREATED'> for 'ElbowPole.L'; Controller recovery rejected: unsupported transaction state <_ArmRigTransactionState.CREATED: 'CREATED'> for 'ElbowPole.R'; COLLECTION_ROLLBACK_AUTHORITY_UNPROVEN: Collection entry baseline unavailable; refusing all Collection child undo/deletion
  ```
  **失败机制**：
  TEST-38 使用了人工构造的模拟事务上下文 `tx = _ArmRigTransactionContext(self.armature)`，直接调用 `_rollback_arm_rig_state(self.armature, snap, active_tx=tx)`。由于该 mock transaction 尚未经过正常事务入场流程（未进入 ACTIVE 状态，未捕获 `entry_collection_ptrs` 和控制器的 entry-pointer baseline），导致触发了严格的回滚权限防御门禁（`Created controller entry-pointer baseline is unavailable`、`unsupported transaction state CREATED` 以及 `COLLECTION_ROLLBACK_AUTHORITY_UNPROVEN`），最终阻断了回滚。

---

## 3. TEST-106 熔断未执行说明

- **熔断规则**：严格执行“TEST-38 失败：立即停止，不运行 TEST-106”。
- **状态**：未执行（UNEXECUTED），不预设或虚报通过。

---

## 4. 现场 Git 状态核验

- **测试前 HEAD**：`74e301bd3c53a5a09dd6f90316ae5685888348e4`
- **当前测试后 HEAD**：`74e301bd3c53a5a09dd6f90316ae5685888348e4`
- **受跟踪文件状态**：`git diff` 与 `git diff --cached` 均为零差异，没有任何生产代码或测试代码受到修改。
- **七个受保护未跟踪文件**：完整保留，未被删除或修改。
