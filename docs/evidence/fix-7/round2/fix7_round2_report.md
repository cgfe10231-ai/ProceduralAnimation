# TASK 10-B｜fix-7 Round 2：修正发现数量后的自动化回归执行报告

## 1. 基线与环境信息

* **仓库与分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试前固定 HEAD**：`1da95568f626d3469943cb686b30ea35baaf092b`
* **Blender 版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **Python 版本**：`3.13.9 (main, Jan 16 2026, 12:29:45) [MSC v.1944 64 bit (AMD64)]`
* **前置 Git Blob SHA 核验结果**：
  * `tests/test_registry.py`：`43acac995be2994596f852460d52ea9f77a99998`（一致）
  * `tests/run_test_suite.py`：`eaa4658fc5b9e7adc15dde80d3cc43857e18bc05`（一致）
  * `tests/test_task10b_transaction_atomicity.py`：`b0f39ea14217b459848ee1100d4b25d4446ad80f`（一致）
  * `tests/test_bug11_datablock_cleanup.py`：`f3a8fcca15784f1e8110b8a9c2258ce3921ba746`（一致）
  * `tests/test_bug12_cross_armature_real_resources.py`：`8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40`（一致）
* **治理状态核对**：`origin/master:WORKFLOW_GOVERNANCE.md` 为 `APPROVED (正式生效)`。
* **上一轮历史证据说明（第 4、9 节）**：
  * 上一轮停止原因为 `224` 与 `223` 的错误计数（原任务将 `TEST-63` 内部的局部函数 `test_hook()` 误计为独立测试方法），并非生产代码测试失败。
  * 上一轮生成的 `docs/evidence/fix-7/atomicity_stdout.log`、`docs/evidence/fix-7/atomicity_stderr.log` 与 `docs/evidence/fix-7/fix7_test_report.md` 均原样保留，未作任何覆盖或修改。

---

## 2. 四组测试结果总表

| 分组 | 冻结数量 | 实际发现数量 | 实际运行数量 | PASS | FAIL | ERROR | SKIPPED | NOT_RUN | 真实进程退出码 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Group A: Atomicity (`TestArmIKTransactionAtomicity`) | 223 | 223 | 98 | 97 | 0 | 1 | 0 | 125 | `1` |
| Group B: BUG11 (`TestBug11TypeADataBlockFaults`) | 8 | `NOT_RUN` | 0 | 0 | 0 | 0 | 0 | 8 | `NOT_RUN` |
| Group C: BUG12 (`TestBug12RealCrossArmaturePending`) | 4 | `NOT_RUN` | 0 | 0 | 0 | 0 | 0 | 4 | `NOT_RUN` |
| Group D: FULL (`get_tests_for_tier(TestTier.FULL)`) | 42 suites | 42 (静态核验) | 0 | 0 | 0 | 0 | 0 | 42 | `NOT_RUN` |

* **执行与熔断说明**：
  * Group A (`TestArmIKTransactionAtomicity`) 发现数量校验通过（`FIX7_R2_GROUP atomicity DISCOVERED 223 EXPECTED 223`，编号 `31`~`253` 连续无缺号、无重复）。
  * 按 `unittest.defaultTestLoader` 字典序依次执行：前 97 项（`test_100` 至 `test_196`）全部 `ok`（`PASS`）。
  * 第 98 项 `test_197_pre_existing_object_added_to_created_controller_objects_rejected` 抛出未捕获 `RuntimeError`（记为 `ERROR`），因 `failfast=True` 立即终止 Group A 其余 125 项（`test_198`~`test_253` 及 `test_31`~`test_99`，全部标记 `NOT_RUN`），Blender 进程返回真实退出码 **`1`**。
  * 遵循第 6 节“任意一组出现真实失败：立即停止，不执行下一组。不允许失败后自动修复。不允许自动重试”及第 7 节“只生成实际执行过的 Group 日志。未运行的 Group 标记 `NOT_RUN`。不得制造空日志冒充已执行”，立即停止，Group B (`BUG11`)、Group C (`BUG12`) 与 Group D (`FULL`) 均未启动（`NOT_RUN`）。

---

## 3. Group A 真实失败（ERROR）详情

* **失败用例**：`test_197_pre_existing_object_added_to_created_controller_objects_rejected`（`tests/test_task10b_transaction_atomicity.py` 第 7517–7547 行）
* **原始 Traceback（来自 `docs/evidence/fix-7/round2/atomicity_stdout.log` 第 720–736 行）**：

```text
======================================================================
ERROR: test_197_pre_existing_object_added_to_created_controller_objects_rejected (fix7_r2_atomicity.TestArmIKTransactionAtomicity.test_197_pre_existing_object_added_to_created_controller_objects_rejected)
TEST-197: Pre-existing object erroneously added to created_controller_objects denied replacement.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_task10b_transaction_atomicity.py", line 7526, in test_197_pre_existing_object_added_to_created_controller_objects_rejected
    tx.register_created_controller(pre_obj)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^
  File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\src\rig\arm_ik.py", line 6673, in register_created_controller
    raise RuntimeError('Cannot register a pre-existing object as transaction-created')
RuntimeError: Cannot register a pre-existing object as transaction-created

----------------------------------------------------------------------
Ran 98 tests in 8.542s

FAILED (errors=1)
FIX7_R2_GROUP_RESULT atomicity RAN 98 FAILURES 0 ERRORS 1 SKIPPED 0 PASS False
```

* **只读现场事实记录（未作任何修改）**：
  * `TEST-197` 在事务外预创建 `pre_obj = bpy.data.objects.new("HandIK.L", pre_mesh)` 后，于第 7526 行无异常捕获地直接调用 `tx.register_created_controller(pre_obj)`，随后在第 7530 行断言 `_verify_transaction_wrong_type_object_ownership(pre_obj, tx, self.armature)` 返回 `False` 并在第 7534 行调用 `setup_arm_ik(self.armature)`。
  * 当前生产代码 `src/rig/arm_ik.py` 第 6673 行在 `register_created_controller()` 入口即对事务前已存在对象（`obj_ptr in self.entry_object_ptrs`）直接抛出 `RuntimeError('Cannot register a pre-existing object as transaction-created')`，因此第 7526 行直接触发 `ERROR`。

---

## 4. 原始日志路径与文件边界核查

* **本轮 Round 2 实际生成文件**：
  * `docs/evidence/fix-7/round2/atomicity_stdout.log`（736 行，79,447 bytes）
  * `docs/evidence/fix-7/round2/atomicity_stderr.log`（390 行，Blender 后台删除 Armature 用例 `TEST-143`/`158`/`179` 期间的原生 `Failed to add relation "Bone Parent"` 诊断输出）
  * `docs/evidence/fix-7/round2/fix7_round2_report.md`（本报告）
* **上一轮原样保留文件**：
  * `docs/evidence/fix-7/atomicity_stdout.log`
  * `docs/evidence/fix-7/atomicity_stderr.log`
  * `docs/evidence/fix-7/fix7_test_report.md`
* **未生成日志的 `NOT_RUN` 组**：
  * `docs/evidence/fix-7/round2/bug11_stdout.log` / `bug11_stderr.log`：`NOT_RUN`（未生成）
  * `docs/evidence/fix-7/round2/bug12_stdout.log` / `bug12_stderr.log`：`NOT_RUN`（未生成）
  * `docs/evidence/fix-7/round2/full/`：`NOT_RUN`（未生成）
* **是否存在越界修改**：**否**。
  * `git diff --exit-code` = `0`，`git diff --cached --exit-code` = `0`。
  * `src/`、`tests/`、Registry、Runner、治理及架构文档、上一轮 `fix-7` 根目录三份证据以及既有 7 项历史未跟踪文件均零修改。
