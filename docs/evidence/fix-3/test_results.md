# TASK 10-B / fix-3 专项测试结果记录 (Test Results)

- **基线分支**：`audit/task-10-b-9`
- **基线 Commit HEAD**：`70ae9478727354accc17491f08f23b856c33902c`
- **Blender 引擎版本**：`Blender 5.1.1` (build date: `2026-04-14 01:37:22`, build hash: `b70da489d7f4`, platform: Windows, Release)
- **治理规范依据**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED, 批准日期: 2026-11-11)

---

## 1. 专项测试结果总表

| 序号 | 测试编号 | 完整 unittest 方法名 | 进程退出码 | 运行耗时 | 测试数量 | 结果判定 | 执行时间 (Local) |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | **TEST-244** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation` | `0` | 0.613s | 1 | **PASS** | 2026-11-16T15:02:14+08:00 |
| 2 | **TEST-136** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_136_cleanup_pending_and_failed_isolation_strictly_separated` | `0` | 0.259s | 1 | **PASS** | 2026-11-16T15:02:25+08:00 |
| 3 | **TEST-242** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback` | `0` | 0.219s | 1 | **PASS** | 2026-11-16T15:03:52+08:00 |
| 4 | **TEST-243** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending` | `0` | 0.229s | 1 | **PASS** | 2026-11-16T15:04:27+08:00 |
| 5 | **TEST-163** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_163_unknown_liveness_preserves_failed_isolation` | `0` | 0.236s | 1 | **PASS** | 2026-11-16T15:05:04+08:00 |
| 6 | **TEST-131** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_131_verified_recovery_deisolates_failed_b_and_failed_c_and_restores_admission` | `0` | 0.232s | 1 | **PASS** | 2026-11-16T15:05:33+08:00 |

---

## 2. 逐项详细记录

### 1. TEST-244
- **测试编号**：TEST-244
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.613s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：预期抛出 `RuntimeError: CLEANUP_PREFLIGHT_REJECTED: transaction <tx_id> is associated with active FAILED isolation`，被 `self.assertRaises(RuntimeError)` 正确捕获并验证异常消息关键词；无未捕获异常。
- **实际执行时间**：`2026-11-16T15:02:14+08:00`

---

### 2. TEST-136
- **测试编号**：TEST-136
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_136_cleanup_pending_and_failed_isolation_strictly_separated`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_136_cleanup_pending_and_failed_isolation_strictly_separated'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.259s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：各阶段预期抛出的业务写入故障与回滚异常均由内部测试上下文捕获验证；最终 Scenario B 中验证 Cleanup Retry 被 Coordinator 拒绝（`CLEANUP_PREFLIGHT_REJECTED`）；无未捕获异常。
- **实际执行时间**：`2026-11-16T15:02:25+08:00`

---

### 3. TEST-242
- **测试编号**：TEST-242
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.219s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：`after_logical_commit` 阶段注入故障由 `self.assertRaises(RuntimeError)` 捕获，验证事务转入 `CLEANUP_PENDING` 且未执行普通回滚；无未捕获异常。
- **实际执行时间**：`2026-11-16T15:03:52+08:00`

---

### 4. TEST-243
- **测试编号**：TEST-243
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.229s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：清理成功后重复调用 `tx.retry_cleanup()` 验证返回 `CLEANUP_ALREADY_COMPLETED` 幂等状态，未抛出异常，无未捕获异常。
- **实际执行时间**：`2026-11-16T15:04:27+08:00`

---

### 5. TEST-163
- **测试编号**：TEST-163
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_163_unknown_liveness_preserves_failed_isolation`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_163_unknown_liveness_preserves_failed_isolation'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.236s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：在 UNKNOWN Liveness 代理下调用 `setup_arm_ik()`，分别被提前 FAILED-B 与 FAILED-C 门禁拒绝并由 `self.assertRaises(RuntimeError)` 捕获匹配；无未捕获异常。
- **实际执行时间**：`2026-11-16T15:05:04+08:00`

---

### 6. TEST-131
- **测试编号**：TEST-131
- **完整 unittest 方法名**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_131_verified_recovery_deisolates_failed_b_and_failed_c_and_restores_admission`
- **Blender 版本**：Blender 5.1.1 (hash `b70da489d7f4`)
- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_131_verified_recovery_deisolates_failed_b_and_failed_c_and_restores_admission'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`0`
- **运行耗时**：`0.232s`
- **测试数量**：`Ran 1 test`
- **判定结果**：`PASS` (0 failures, 0 errors)
- **原始异常摘要**：Part A (FAILED-B) 与 Part B (FAILED-C) 的故障注入由 `self.assertRaises(RuntimeError)` 捕获；解除隔离后写事务成功提交；无未捕获异常。
- **实际执行时间**：`2026-11-16T15:05:33+08:00`
