# TASK 10-B / fix-4 TEST ONLY 阶段定点验收报告 (TEST-38)

- **任务编号**：TASK 10-B / fix-4
- **阶段定位**：TEST ONLY
- **分支**：`audit/task-10-b-9`
- **固定 HEAD**：`780c1eaf4408cdb9af6d86e125258e7fb2e4bcb8`
- **执行引擎**：Blender 5.1.1 (build date: `2026-04-14 01:37:22`, hash: `b70da489d7f4`, Release)
- **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md` (APPROVED)
- **测试类**：`tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity`
- **测试用例**：`test_38_direct_rollback_constraints`

---

## 1. 测试执行总览

| 序号 | 测试编号 | 完整 unittest 方法名 | 执行次数 | 进程退出码 | 运行耗时 | 测试数量 | 判定结果 | 执行状态 |
| :---: | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | **TEST-38** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints` | 1 | `0` | 0.242s (总计 2.198s) | 1 | **OK (PASS)** | 100% 验收通过 |
| 2 | **TEST-106** | `tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_106_external_constraint_insertion_preserves_original_constraint_order` | 0 | N/A | N/A | 0 | **UNEXECUTED** | 熔断保留，由 ChatGPT 下一步单独处理 |

---

## 2. 详细执行命令与完整输出

### 执行命令
```powershell
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```

### 完整控制台原始输出
```text
Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)
[CHARACTER] Built placeholder at start waypoint (0.0, -8.0, 0.0)
[CHARACTER] Parts: Head, Torso, Pelvis, UpperArm_L, UpperArm_R, LowerArm_L, LowerArm_R, UpperLeg_L, UpperLeg_R, LowerLeg_L, LowerLeg_R, Foot_L, Foot_R
[RIG] Created CharacterArmature with 19 bones at (0.0, -8.0, 0.0)
[RIG] Bound 13 character parts to CharacterArmature bones
[IK] Configured two-bone leg IK constraints, knee poles, and foot rotation controls for L/R
test_38_direct_rollback_constraints (tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.test_38_direct_rollback_constraints)
TEST-38: ... ok

----------------------------------------------------------------------
Ran 1 test in 0.242s

OK
```

---

## 3. 验收覆盖核实

实际运行结果已 100% 验证以下全部 13 项标准：
1. **事务合法性**：`with _arm_rig_transaction(self.armature) as tx` 正常进入 `_ArmRigTransactionState.ACTIVE`；
2. **约束授权创建**：调用 `_authorized_create_constraint()` 成功创建 `COPY_ROTATION` 约束 `ExtraCopyRotation_TEST38`；
3. **约束排序变更**：临时约束插入至原始约束之前（索引 0）；
4. **属性扰动真实发生**：原始 `ArmIK.L` 约束的 influence 变更为 0.9，mute 发生翻转；
5. **故障注入正常触发**：主动抛出 `RuntimeError("Fault injected in TEST-38")` 并被 `assertRaises` 捕获；
6. **事务原子回滚**：事务最终状态为 `_ArmRigTransactionState.ROLLED_BACK`；
7. **活动事务栈出栈清空**：`len(_ACTIVE_TRANSACTION_STACK) == 0`；
8. **原始约束身份不变**：`restored.as_pointer() == original_ptr`；
9. **原始约束属性精准恢复**：`influence` 恢复为 0.4，`mute` 恢复为原状态；
10. **约束总数与原始顺序恢复**：`len(p_fore.constraints) == 1`，`p_fore.constraints[0].name == "ArmIK.L"`；
11. **临时约束完全清理**：`ExtraCopyRotation_TEST38` 不在骨骼约束列表中；
12. **无错误隔离与无挂起清理**：`session_id not in _ISOLATED_FAILED_ARMATURES`，`isolation_state == NONE`，`len(get_pending_arm_rig_cleanup_ids()) == 0`，`tx.tx_id not in _PENDING_ARM_RIG_CLEANUPS`；
13. **退出后快照一致性核验**：`_verify_arm_rig_state_restored(self.armature, tx.snapshot)` 校验成功通过。

---

## 4. Git 与证据保护核对

- **当前分支**：`audit/task-10-b-9`
- **当前 HEAD**：`780c1eaf4408cdb9af6d86e125258e7fb2e4bcb8`
- **代码变动**：`git diff --exit-code` 与 `git diff --cached --exit-code` 均为 0（零代码修改）。
- **历史受保护文件**：7 个文件完整保留。
- **本轮证据留存**：
  - [test_38_final_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_final_execution.log)
  - [test_38_final_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_final_test_report.md)
- **历史证据完好保留**：
  - [baseline_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/baseline_test_report.md)
  - [test_38_raw.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_raw.log)
  - [test_38_verification_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_verification_report.md)
  - [test_38_verified_raw.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-4/test_38_verified_raw.log)
