# TASK 10-B｜工作包 A：fix-1 / fix-2 既有四项专项事实报告

* **任务编号**：`TASK 10-B｜工作包 A`（`TEST ONLY + EVIDENCE COMMIT`）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试基线 HEAD**：`1022c7369426c61e55b48884a7691ea58fe2b1a2`
* **Blender 版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **目标测试文件及 Git Blob SHA**：`tests/test_task10b_transaction_atomicity.py`（`5c1fc463e4181b700cad335754a5cef610822426`）
* **治理核对**：`origin/master:WORKFLOW_GOVERNANCE.md` 状态为 `APPROVED (正式生效)`

---

## 1. 原始执行命令与冻结测试选择表达式

* **执行可执行文件**：`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`
* **启动参数**：`--background --python-exit-code 1 --python-expr "<$expr>"`（单进程一次性执行，工作目录为仓库根目录）
* **冻结测试选择表达式 `$expr`**：

```python
import runpy,sys,unittest; ns=runpy.run_path('tests/test_task10b_transaction_atomicity.py',run_name='fix1_fix2_targeted'); T=ns['TestArmIKTransactionAtomicity']; names=('test_127_failed_c_rollback_verification_or_recovery_uncertain_records_isolation','test_149_relationship_undo_exception_transitions_to_recovery_uncertain_and_isolates_as_failed_c','test_147_coordinator_grant_binding_and_single_use_enforcement','test_155_verified_recovery_issues_grant_and_single_use_consumed'); suite=unittest.TestSuite(T(n) for n in names); result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2,failfast=True).run(suite); passed=result.wasSuccessful() and result.testsRun==4; print('FIX1_FIX2_TEST_COUNT',result.testsRun); print('FIX1_FIX2_PASS',passed); sys.exit(0 if passed else 1)
```

---

## 2. 四项专项测试真实结果

| 顺序 | 编号 | 测试方法名 (`TestArmIKTransactionAtomicity`) | 实际输出状态 | 判定 |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `TEST-127` | `test_127_failed_c_rollback_verification_or_recovery_uncertain_records_isolation` | `ok` | **PASS** |
| 2 | `TEST-149` | `test_149_relationship_undo_exception_transitions_to_recovery_uncertain_and_isolates_as_failed_c` | `ok` | **PASS** |
| 3 | `TEST-147` | `test_147_coordinator_grant_binding_and_single_use_enforcement` | `ok` | **PASS** |
| 4 | `TEST-155` | `test_155_verified_recovery_issues_grant_and_single_use_consumed` | `ok` | **PASS** |

* **汇总信号**：`Ran 4 tests in 0.521s` / `OK` / `FIX1_FIX2_TEST_COUNT 4` / `FIX1_FIX2_PASS True`
* **Blender 实际退出码**：`0`（`BLENDER_EXIT_CODE=0`）
* **原始证据日志路径**：
  * stdout：`docs/evidence/task10b15/fix1_fix2_targeted_stdout.log`（36 行）
  * stderr：`docs/evidence/task10b15/fix1_fix2_targeted_stderr.log`（0 bytes，空）
* **失败 Traceback**：无（四项均 `ok`，stderr 为空）。
* **范围说明**：`TEST-26`、`TEST-64`、`BUG11`、`BUG12`、`HIST-F06`、`CONTRACT10` 与四级回归均未执行；本报告仅记录四项专项的真实运行事实，不对 `fix-1` 或 `fix-2` 作关闭裁决。

---

## 3. 测试前后 Git 状态与非授权修改核查

* **测试前基线状态**：
  * 分支：`audit/task-10-b-9`；`HEAD`：`1022c7369426c61e55b48884a7691ea58fe2b1a2`
  * `git diff --exit-code`：`0`；`git diff --cached --exit-code`：`0`
  * 既有 7 项未跟踪文件：`P2_R1_recovery.patch`、`Untitled-1.cpp`、`round05_exact_apply.py`、`round05_exact_apply_v2.py`、`round05_exact_apply_v3.py`、`round05_exact_apply_v3_local.py`、`round05_validate_finalize_v3.py`
* **测试后提交前状态**：
  * `git rev-parse HEAD`：`1022c7369426c61e55b48884a7691ea58fe2b1a2`
  * `git diff --exit-code`：`0`；`git diff --cached --exit-code`：`0`
  * 上述 7 项未跟踪文件原封保留，工作区仅新增允许的 3 份证据文件（`docs/evidence/task10b15/fix1_fix2_targeted_stdout.log`、`docs/evidence/task10b15/fix1_fix2_targeted_stderr.log`、`docs/evidence/task10b15/fix1_fix2_targeted_report.md`）。
* **是否发生非授权文件修改**：**否**（生产源码、测试源码、治理文档与 `CORE_REPAIR_LEDGER.md` 均零修改）。
