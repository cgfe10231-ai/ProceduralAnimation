# TASK 10-B / fix-4 TEST ONLY 阶段定点验证记录

- **任务编号**：TASK 10-B / fix-4
- **阶段定位**：TEST ONLY
- **分支**：`audit/task-10-b-9`
- **固定 HEAD**：`2ba94d87cb9cb1198545e59e28492d714d15ca99`
- **执行引擎**：Blender 5.1.1 (build date: `2026-04-14 01:37:22`, hash: `b70da489d7f4`)
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED)
- **测试用例**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints`

---

## 1. 执行总览

| 序号 | 测试编号 | 完整 unittest 方法名 | 退出码 | 运行耗时 | 测试数量 | 判定结果 | 执行状态 |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | **TEST-38** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints` | `1` | 0.235s (总计 2.2s) | 1 | **ERROR** | 执行并捕获异常阻断 |
| 2 | **TEST-106** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order` | N/A | N/A | 0 | **UNEXECUTED** | 明确禁止执行 |

---

## 2. TEST-38 详细执行输出

- **实际执行命令**：
  ```powershell
  & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
  ```
- **退出码**：`1`
- **耗时**：`Ran 1 test in 0.235s`
- **测试数量**：`1`
- **结果判定**：`FAILED (errors=1)`
- **首次失败位置**：`tests/test_task10b_transaction_atomicity.py` 第 634 行
  ```python
  _verify_arm_rig_state_restored(self.armature, tx.snapshot, active_tx=tx)
  ```
- **调用栈底层**：`src/rig/arm_ik.py` 第 6015 行，位于 `_verify_arm_rig_state_restored()` 内：
  ```python
  # src/rig/arm_ik.py:5992-5994
  else:
      if _ACTIVE_TRANSACTION_STACK != [active_tx]:
          diffs.append(f"Active transaction stack contains unexpected transactions: {_ACTIVE_TRANSACTION_STACK}")
  ```
- **实际异常类型**：`RuntimeError`
- **完整异常信息**：
  ```text
  RuntimeError: Arm rig rollback verification failed: Active transaction stack contains unexpected transactions: []
  ```

---

## 3. 根因技术分析

1. **事务准入与回滚均已成功完成**：
   - `_arm_rig_transaction()` 成功进入 `ACTIVE`；
   - `_authorized_create_constraint()` 成功创建临时约束并完成排序调整；
   - 故障注入成功触发回滚；
   - 事务状态成功转换为 `_ArmRigTransactionState.ROLLED_BACK`；
   - 活动事务栈 `_ACTIVE_TRANSACTION_STACK` 成功弹出清空（长度为 0）；
   - 前面所有关于约束指针、属性、排序、清理额外约束、无 FAILED 隔离、无 CLEANUP_PENDING 的断言全部 **顺利通过**。
2. **唯一失败点在于测试末尾对验证器的调用参数**：
   - 测试方法末尾调用了 `_verify_arm_rig_state_restored(self.armature, tx.snapshot, active_tx=tx)`；
   - 生产函数 `_verify_arm_rig_state_restored` 的合同为：
     - 若传入 `active_tx`（非 None），函数期望该事务当前仍处于活动栈中（即 `_ACTIVE_TRANSACTION_STACK == [active_tx]`）；
     - 若未传入 `active_tx` 或为 `None`，函数校验 `len(_ACTIVE_TRANSACTION_STACK) == 0`；
   - 由于此时事务已完成回滚并退出上下文管理器，`_ACTIVE_TRANSACTION_STACK` 正确为空 `[]`，因此传入 `active_tx=tx` 导致检验器判定栈状态不符。

---

## 4. 阶段纪律与熔断

- 依据 TEST ONLY 阶段纪律，严禁擅自修改测试代码或生产代码。
- 严禁执行 TEST-106。
- 现场保持完整，等待 ChatGPT 审计裁决。
