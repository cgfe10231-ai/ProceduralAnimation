# TASK 10-B / fix-4 TEST ONLY 阶段定点验收报告 (TEST-106)

- **任务编号**：TASK 10-B / fix-4
- **阶段定位**：TEST ONLY
- **分支**：`audit/task-10-b-9`
- **固定 HEAD**：`6c24372cfc5a1f2f854d5a6599775fc915d73b3b`
- **执行引擎**：Blender 5.1.1 (build date: `2026-04-14 01:37:22`, hash: `b70da489d7f4`, Release)
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED)
- **测试类**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity`
- **测试用例**：`test_106_external_constraint_insertion_preserves_original_constraint_order`

---

## 1. 测试执行总览

| 序号 | 测试编号 | 完整 unittest 方法名 | 执行次数 | 进程退出码 | 运行耗时 | 测试数量 | 判定结果 | 执行状态 |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | **TEST-106** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order` | 1 | `0` | 0.255s (总计 2.198s) | 1 | **OK (PASS)** | 100% 验收通过 |

---

## 2. 详细执行命令与完整输出

### 执行命令
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```

### 完整控制台原始输出
```text
Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)
[CHARACTER] Built placeholder at start waypoint (0.0, -8.0, 0.0)
[CHARACTER] Parts: Head, Torso, Pelvis, UpperArm_L, UpperArm_R, LowerArm_L, LowerArm_R, UpperLeg_L, UpperLeg_R, LowerLeg_L, LowerLeg_R, Foot_L, Foot_R
[RIG] Created CharacterArmature with 19 bones at (0.0, -8.0, 0.0)
[RIG] Bound 13 character parts to CharacterArmature bones
[IK] Configured two-bone leg IK constraints, knee poles, and foot rotation controls for L/R
test_106_external_constraint_insertion_preserves_original_constraint_order (tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order)
TEST-106: Inserting external constraints before/between original constraints maintains relative ordering. ... ok

----------------------------------------------------------------------
Ran 1 test in 0.255s

OK
```

---

## 3. 验收覆盖核实

实际运行结果已 100% 验证以下全部 20 项专项验收标准：

### A. 真实事务准入
1. `_arm_rig_transaction()` 正常进入 `_ArmRigTransactionState.ACTIVE`；
2. Snapshot 在事务进入时正确捕获基线；
3. 完全废除手工伪造事务状态与手动事务栈变动；

### B. 原始 Constraint 保留与顺序恢复
4. `ArmIK.L` 原始引用与底层指针 (`as_pointer()`) 100% 保持不变；
5. `OrigLimit106` 原始引用与底层指针 (`as_pointer()`) 100% 保持不变；
6. 两条原始 Constraint 均完整保留在骨骼约束集合中；
7. 原始约束相对顺序（`ArmIK.L` 在 `OrigLimit106` 之前）成功恢复；

### C. 外部 Constraint 隔离与保留
8. `ExtFirst106` 成功插入至骨骼；
9. 排序扰动在事务运行期真实发生并确认；
10. `ExtFirst106` 属于未经当前事务授权的外部插入，未登记为事务创建资源；
11. Coordinator 回滚后 `ExtFirst106` 依然存在且未被误删；
12. 外部 Constraint 底层指针不变；
13. 外部 Constraint 类型保持 `TRACK_TO`；
14. Constraint 总数精准为原始数量加一（`original_count + 1 == 3`）；

### D. 事务终态与状态一致性
15. 预期注入异常 `RuntimeError("Fault injected in TEST-106")` 成功触发；
16. Coordinator 内部自动执行回滚与关系相对顺序校验；
17. 事务终态为 `_ArmRigTransactionState.ROLLED_BACK`；
18. 活动事务栈正常出栈清空（`len(_ACTIVE_TRANSACTION_STACK) == 0`）；
19. 无残留 `FAILED` 隔离（`session_id not in _ISOLATED_FAILED_ARMATURES`，`isolation_state == NONE`）；
20. 无残留挂起清理（`len(get_pending_arm_rig_cleanup_ids()) == 0`，`tx.tx_id not in _PENDING_ARM_RIG_CLEANUPS`）。

---

## 4. Git 与证据保护核对

- **当前分支**：`audit/task-10-b-9`
- **当前 HEAD**：`6c24372cfc5a1f2f854d5a6599775fc915d73b3b`
- **跟踪代码变动**：`git diff --exit-code` 与 `git diff --cached --exit-code` 均为 0（零代码修改）。
- **历史受保护文件**：7 个文件完整保留。
- **本轮新增证据**：
  - [test_106_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_106_execution.log)
  - [test_106_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_106_test_report.md)
- **TEST-38 历史通过证据（完整无损）**：
  - [baseline_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/baseline_test_report.md)
  - [test_38_raw.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_raw.log)
  - [test_38_verification_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_verification_report.md)
  - [test_38_verified_raw.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_verified_raw.log)
  - [test_38_final_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_final_execution.log)
  - [test_38_final_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_final_test_report.md)
