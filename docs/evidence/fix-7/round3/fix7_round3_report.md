# TASK 10-B｜fix-7 Round 3：剩余 Atomicity 及回归执行报告

## 1. 固定基线与前置校验

* **任务编号**：`10-B / fix-7 / Round 3`（`TEST ONLY + EVIDENCE COMMIT`）
* **仓库与分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **固定基线 HEAD**：`506868cb7b97695b08437fb0068c0f7e61c5a7a7`
* **Blender 版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **Python 版本**：`3.13.9 (main, Jan 16 2026, 12:29:45) [MSC v.1944 64 bit (AMD64)]`
* **前置 Git Blob SHA 核验**：
  * `tests/test_task10b_transaction_atomicity.py`：`0b1643c410601849a99b9afc5c9b8c240b85972c`（一致）
  * `tests/test_bug11_datablock_cleanup.py`：`f3a8fcca15784f1e8110b8a9c2258ce3921ba746`（一致）
  * `tests/test_bug12_cross_armature_real_resources.py`：`8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40`（一致）
  * `tests/test_registry.py`：`43acac995be2994596f852460d52ea9f77a99998`（一致）
  * `tests/run_test_suite.py`：`eaa4658fc5b9e7adc15dde80d3cc43857e18bc05`（一致）
* **治理状态核对**：`origin/master:WORKFLOW_GOVERNANCE.md` 状态为 `APPROVED (正式生效)`。

---

## 2. 前 97 项历史证据只读核验结果（第 3 节）

* 已只读核对 `docs/evidence/fix-7/round2/atomicity_stdout.log` 与 `docs/evidence/fix-7/round2/fix7_round2_report.md`：
  1. `TEST-100`～`TEST-196` 共 **97** 项测试全部 `ok`（`R2_PASSED_COUNT = 97`, `R2_EXPECTED_100_196_MATCH = True`）。
  2. Round 2 唯一非 `ok` 项为第 98 项 `TEST-197`（`R2_NON_OK = [(197, 'ERROR')]`）。
  3. `git diff --name-only 1da95568f626d3469943cb686b30ea35baaf092b..506868cb7b97695b08437fb0068c0f7e61c5a7a7 -- src/` 输出为空（生产源码与当前 `HEAD` 完全一致）。
  4. 最新代码提交 `506868cb7b97695b08437fb0068c0f7e61c5a7a7` 仅修改 `TEST-197` 函数，`TEST-100`～`TEST-196` 函数未发生改动。
* 依第 3、5 节规定，本轮复用前 97 项历史通过证据，未重复执行 `TEST-100`～`TEST-196`，且未修改 `docs/evidence/fix-7/` 及 `docs/evidence/fix-7/round2/` 下的任何历史证据文件。

---

## 3. 本轮各组执行结果与聚合统计（第 5–9 节）

| 项目 | 计划 / 冻结数量 | 实际运行 | PASS | FAIL | ERROR | SKIPPED | NOT_RUN | 进程退出码 | 证据来源 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Round 2 已通过 (`TEST-100`～`196`) | 97 | 97 (历史) | 97 | 0 | 0 | 0 | 0 | (历史 Round 2) | `docs/evidence/fix-7/round2/atomicity_stdout.log` |
| Round 3 Atomicity (`TEST-197`～`253`, `TEST-31`～`99`) | 126 | 31 | 30 | 1 | 0 | 0 | 95 | `1` | `docs/evidence/fix-7/round3/atomicity_remaining_stdout.log` |
| **Atomicity 合计（两轮分批）** | **223** | **128** | **127** | **1** | **0** | **0** | **95** | — | 两轮原始日志（非单次 223 项） |
| Group B: BUG11 (`TestBug11TypeADataBlockFaults`) | 8 | 0 | 0 | 0 | 0 | 0 | 8 | `NOT_RUN` | 未执行（未伪造日志） |
| Group C: BUG12 (`TestBug12RealCrossArmaturePending`) | 4 | 0 | 0 | 0 | 0 | 0 | 4 | `NOT_RUN` | 未执行（未伪造日志） |
| Group D: FULL (`get_tests_for_tier(TestTier.FULL)`) | 42 suites | 0 | 0 | 0 | 0 | 0 | 42 | `NOT_RUN` | 未执行（未伪造日志） |

* **TEST-197 实际结果**：**`ok`（`PASS`）**。
* **剩余 125 项（`TEST-198`～`253` 与 `TEST-31`～`99`）实际结果**：
  * `TEST-198`～`TEST-226`（共 29 项）：全部 **`ok`（`PASS`）**。
  * `TEST-227`（`test_227_collection_child_link_fault_before_c_api_no_effect`）：**`FAIL`**（触发 `failfast=True` 立即终止 Group A）。
  * `TEST-228`～`TEST-253`（26 项）与 `TEST-31`～`TEST-99`（69 项）：共 **95 项 `NOT_RUN`**。
* **Atomicity 223 项联合覆盖结论**：
  * **未达到 `ATOMICITY_COVERAGE_223_OF_223_PASS`**（当前两轮联合累计 `127 PASS`、`1 FAIL`、`0 ERROR`、`95 NOT_RUN`）。
* **BUG11 八项结果**：**`NOT_RUN`**（共 8 项 `NOT_RUN`，依第 5.3 与第 6 节规定在 Group A 失败后立即停止，未启动 Group B）。
* **BUG12 四项结果**：**`NOT_RUN`**（共 4 项 `NOT_RUN`，未启动 Group C）。
* **FULL 42 套件结果**：**`NOT_RUN`**（共 42 个套件 `NOT_RUN`，未启动 Group D）。

---

## 4. FAIL / ERROR / NOT_RUN 明细（第 10、12 节）

### 4.1 真实失败项（`FAIL`：1 项；`ERROR`：0 项）

* **失败测试**：`TestArmIKTransactionAtomicity.test_227_collection_child_link_fault_before_c_api_no_effect`（`tests/test_task10b_transaction_atomicity.py` 第 8523–8550 行）
* **原始 Traceback（来自 `docs/evidence/fix-7/round3/atomicity_remaining_stdout.log` 第 221–237 行）**：

```text
======================================================================
FAIL: test_227_collection_child_link_fault_before_c_api_no_effect (fix7_round3_atomicity.TestArmIKTransactionAtomicity.test_227_collection_child_link_fault_before_c_api_no_effect)
TEST-227: Collection child link fault before C-API -> NO_EFFECT.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_task10b_transaction_atomicity.py", line 8543, in test_227_collection_child_link_fault_before_c_api_no_effect
    self.assertIn("Fault injected in TEST-227", str(cm.exception))
    ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'Fault injected in TEST-227' not found in 'COLLECTION_RELATION_OWNERSHIP_UNPROVEN: child is not a live TX-created Collection'

----------------------------------------------------------------------
Ran 31 tests in 2.378s

FAILED (failures=1)
Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)
FIX7_R3_ATOMICITY_TEST_COUNT 31
FIX7_R3_ATOMICITY_PASS False
```

* **遵循第 10 节规则**：仅保留真实失败日志与原始输出，不自行判定归因、不修改测试或生产代码、不重跑。

### 4.2 未运行项目（`NOT_RUN`）

1. **Group A 剩余 95 项**：`TEST-228`～`TEST-253`（26 项）及 `TEST-31`～`TEST-99`（69 项）。
2. **Group B (`BUG11`)**：全部 8 项 `NOT_RUN`。
3. **Group C (`BUG12`)**：全部 4 项 `NOT_RUN`。
4. **Group D (`FULL Tier`)**：全部 42 个唯一套件 `NOT_RUN`。

---

## 5. 原始日志路径、非授权修改核查与视觉验收待办

* **全部原始日志路径**：
  * 本轮 `round3/` 实际生成：
    * `docs/evidence/fix-7/round3/atomicity_remaining_stdout.log`（237 行）
    * `docs/evidence/fix-7/round3/atomicity_remaining_stderr.log`（0 bytes，空）
    * `docs/evidence/fix-7/round3/fix7_round3_report.md`（本报告）
  * 未执行的 `bug11_stdout.log`、`bug11_stderr.log`、`bug12_stdout.log`、`bug12_stderr.log` 与 `full/` 依第 4 节规定未生成。
  * 历史保留日志（未改动）：`docs/evidence/fix-7/round2/atomicity_stdout.log`、`docs/evidence/fix-7/round2/atomicity_stderr.log`、`docs/evidence/fix-7/round2/fix7_round2_report.md`、`docs/evidence/fix-7/atomicity_stdout.log`、`docs/evidence/fix-7/atomicity_stderr.log`、`docs/evidence/fix-7/fix7_test_report.md`。
* **是否出现非授权修改**：**否**。
  * `git diff --exit-code` = `0`，`git diff --cached --exit-code` = `0`。
  * `src/`、`tests/`、Runner、Registry、治理文档、历史 `fix-7` / `round2` 证据及既有 7 项未跟踪资产均零修改。
* **视觉验收待办**：
  * `VISUAL_ACCEPTANCE_PENDING`（FULL Tier 全部 42 个套件含 9 项 `is_visual_acceptance=True` 套件本轮均为 `NOT_RUN`，未完成人工视觉验收）。
* **Git 提交与远程同步记录**：
  * 基线 HEAD：`506868cb7b97695b08437fb0068c0f7e61c5a7a7`；归档本报告与 `round3/` 日志后的最新 Commit SHA 与远程 `origin/audit/task-10-b-9` SHA 见本轮最终交付卡片。
