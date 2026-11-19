# TASK 10-B / fix-7 — Remaining Regression Completion Report (Round 2)

## 1. 测试前基线与环境信息

- **仓库**：`cgfe10231-ai/ProceduralAnimation`
- **分支**：`audit/task-10-b-9`
- **本轮测试前冻结 HEAD**：`b079af341aa032ac1f272fc354cdc5ab51a73a60`
- **治理状态**：`origin/master:WORKFLOW_GOVERNANCE.md` 为 `APPROVED (正式生效)`
- **`master` / `origin/master` 基线**：`a2c9b383b71fb2e84bc453cf4cd7926141d61dd9`（全程未修改、未合并）
- **运行环境**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)` / 内嵌 `Python 3.13.9`
- **启动器**：Windows PowerShell 5.1 `System.Diagnostics.ProcessStartInfo` 使用 `$psi.Arguments`（禁止 `ArgumentList`）与 `ReadToEndAsync()` 双流异步捕获。

### 冻结源码文件 Git Blob 核验（测试前后均一致）

| 文件 | 冻结 Git Blob SHA | 测试前后校验 |
|---|---|---|
| `tests/test_task10b_transaction_atomicity.py` | `df55b46ad3b189b20e1b947bc80731ba45e78fd3` | MATCH |
| `tests/test_bug11_datablock_cleanup.py` | `f3a8fcca15784f1e8110b8a9c2258ce3921ba746` | MATCH |
| `tests/test_bug12_cross_armature_real_resources.py` | `8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40` | MATCH |
| `tests/test_registry.py` | `43acac995be2994596f852460d52ea9f77a99998` | MATCH |
| `tests/run_test_suite.py` | `eaa4658fc5b9e7adc15dde80d3cc43857e18bc05` | MATCH |
| `src/rig/arm_ik.py` | `bedbcda220af8d47d11b5400de8a56375019eba4` | MATCH |

---

## 2. 历史 180 项有效 Atomicity PASS 证据（只读核验）

已只读解析四份历史日志，确认 `TEST-31`～`56` 与 `TEST-100`～`253` 共 **180** 项均具有真实 `ok` 记录且历史 `TEST-57` 的 `FAIL` 未计入历史 PASS：

| 范围 | 去重有效数 | 归档日志路径 | 只读核验说明 |
|---|---:|---|---|
| `TEST-100`～`196` | `97` | `docs/evidence/fix-7/round2/atomicity_stdout.log` | 97 项 `ok`（随后在 `TEST-197` 停止） |
| `TEST-197`～`226` | `30` | `docs/evidence/fix-7/round3/atomicity_remaining_stdout.log` | 30 项 `ok`（随后在 `TEST-227` 停止） |
| `TEST-227`～`233` | `7` | `docs/evidence/fix-7/collection_targeted/round2/test_stdout.log` | 日志包含 `TEST-225`～`233` 共 9 项 `ok`；`TEST-225`、`226` 已在 round3 计数，此处去重计 7 项 |
| `TEST-234`～`253` | `20` | `docs/evidence/fix-7/remaining_regression/atomicity_stdout.log` | 20 项 `ok` |
| `TEST-31`～`56` | `26` | `docs/evidence/fix-7/remaining_regression/atomicity_stdout.log` | 26 项 `ok`（原日志中 `TEST-57` 为 `FAIL`，未计入历史 PASS） |
| **历史有效合计** | **`180`** | 去重并集 = `TEST-31..56 ∪ TEST-100..253` | **VALID (`EXACT_180=True`, `TEST57_IN_UNION=False`)** |

---

## 3. 四组顺序执行总览与退出码

> 统计单位说明：Group A（Atomicity）、Group B（BUG11）、Group C（BUG12）以独立 `unittest` **测试方法数**计量；Group D（FULL）以 `TestTier.FULL` 注册表**唯一套件数**计量。二者为不同统计单位，未做简单相加。

| 组别 | 范围 | 统计单位 | 计划 | 实际执行 | PASS / AUTOMATED_PASS | FAIL | ERROR | SKIPPED | NOT_RUN | 真实退出码 | 原始日志路径 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Group A** | Atomicity 剩余 (`TEST-57`～`99`) | 测试方法 | `43` | `43` | `43` (`PASS`) | `0` | `0` | `0` | `0` | `0` | `docs/evidence/fix-7/remaining_regression/round2/atomicity_stdout.log`<br>`docs/evidence/fix-7/remaining_regression/round2/atomicity_stderr.log` |
| **Group B** | `tests/test_bug11_datablock_cleanup.py` (`TestBug11TypeADataBlockFaults`) | 测试方法 | `8` | `8` | `8` (`PASS`) | `0` | `0` | `0` | `0` | `0` | `docs/evidence/fix-7/remaining_regression/round2/bug11_stdout.log`<br>`docs/evidence/fix-7/remaining_regression/round2/bug11_stderr.log` |
| **Group C** | `tests/test_bug12_cross_armature_real_resources.py` (`TestBug12RealCrossArmaturePending`) | 测试方法 | `4` | `4` | `4` (`PASS`) | `0` | `0` | `0` | `0` | `0` | `docs/evidence/fix-7/remaining_regression/round2/bug12_stdout.log`<br>`docs/evidence/fix-7/remaining_regression/round2/bug12_stderr.log` |
| **Group D** | `TestTier.FULL` (`TestSuiteRunner`, `fail_fast=True`, `timeout_multiplier=1.0`) | 唯一套件 | `42` | `42` | `42` (`33 PASSED` + `9 AUTOMATED_PASS`) | `0` | `0` | `0` | `0` | `0` | `docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`<br>`docs/evidence/fix-7/remaining_regression/round2/full/test_report.md`<br>`docs/evidence/fix-7/remaining_regression/round2/full/full_console.log`<br>`docs/evidence/fix-7/remaining_regression/round2/full/raw/<test_id>_{stdout,stderr}.log` (84 files) |

---

## 4. Group A 详情：Atomicity 剩余 43 项 (`TEST-57`～`99`)

- **选择器校验**：`FIX7_SELECTED [57, 58, ..., 99]`（43 项，与历史 180 项零交集）
- **`unittest` 输出**：`Ran 43 tests in 3.036s` / `OK`
- **标记核验**：`FIX7_EXECUTED 43` / `FIX7_PASS True`
- **Blender 退出码**：`0`（`atomicity_stderr.log` 为 0 字节）
- **结果明细**：`TEST-57`（修正后）及 `TEST-58`～`TEST-99` 共 **43 项全部 `PASS`**（`FAIL=0`, `ERROR=0`, `SKIPPED=0`, `NOT_RUN=0`）。

### Atomicity 223 项联合覆盖结论

- 历史有效 PASS：`180`（`TEST-31`～`56`、`TEST-100`～`253`）
- 本轮 PASS：`43`（`TEST-57`～`99`）
- 联合去重有效 PASS：**`223 / 223`**
- 结论标记：**`ATOMICITY_COVERAGE_223_OF_223_PASS`**

---

## 5. Group B 详情：BUG11（8 项）

- **发现数量校验**：`FIX7_BUG11_DISCOVERED 8`
- **`unittest` 输出**：`Ran 8 tests in 0.653s` / `OK`
- **标记核验**：`FIX7_BUG11_EXECUTED 8` / `FIX7_BUG11_PASS True`
- **Blender 退出码**：`0`（`bug11_stderr.log` 为 0 字节）

| 序号 | 测试方法名 | 结果 |
|---:|---|---|
| 1 | `test_bug11_01_valid_type_a_positive_control` | `PASS` |
| 2 | `test_bug11_02_fault_before_authorization_then_retry` | `PASS` |
| 3 | `test_bug11_03_fault_after_authorization_before_physical_remove` | `PASS` |
| 4 | `test_bug11_04_fault_after_physical_remove_no_double_delete` | `PASS` |
| 5 | `test_bug11_05_forged_auth_pointer_refuses_then_recovers` | `PASS` |
| 6 | `test_bug11_06_mismatched_receipt_refuses_then_recovers` | `PASS` |
| 7 | `test_bug11_07_second_live_user_blocks_then_retry` | `PASS` |
| 8 | `test_bug11_08_zero_user_without_authorization_is_preserved` | `PASS` |

---

## 6. Group C 详情：BUG12（4 项）

- **发现数量校验**：`FIX7_BUG12_DISCOVERED 4`
- **`unittest` 输出**：`Ran 4 tests in 0.413s` / `OK`
- **标记核验**：`FIX7_BUG12_EXECUTED 4` / `FIX7_BUG12_PASS True`
- **Blender 退出码**：`0`（`bug12_stderr.log` 为 0 字节）

| 序号 | 测试方法名 | 结果 |
|---:|---|---|
| 1 | `test_bug12_01_retry_a_deletes_only_a_real_resources` | `PASS` |
| 2 | `test_bug12_02_pending_both_gates_and_healthy_third_armature` | `PASS` |
| 3 | `test_bug12_03_foreign_constraint_and_cleanup_result_cannot_be_borrowed` | `PASS` |
| 4 | `test_bug12_04_failed_retry_a_keeps_b_real_resources_untouched` | `PASS` |

---

## 7. Group D 详情：FULL（42 个唯一套件）

- **去重与边界核验**：
  - `Planned = 42`，42 个唯一 `test_id`，42 个唯一 `script_path`。
  - 精确等于 `QUICK`（19 项）、`PHYSICS`（27 项）、`MOTION`（12 项）的去重并集，每个套件仅执行一次，未单独重复运行 `QUICK`、`PHYSICS`、`MOTION`。
  - 不包含任何 `LEGACY`-only 套件，不包含 Group A/B/C 的测试脚本。
- **Runner 配置**：`TestSuiteRunner.run_suite(tests)`，`fail_fast=True`，`timeout_multiplier=1.0`。
- **汇总指标**（来自 `full/test_report.json`）：
  - `total_planned`: `42`
  - `total_executed`: `42`
  - `passed_count`: `42`（其中 `33 PASSED` + `9 AUTOMATED_PASS`）
  - `failed_count`: `0`
  - `skipped_count`: `0`（`required_skipped_count`: `0`，`optional_skipped_count`: `0`）
  - `not_run_count`: `0`
  - `total_duration_sec`: `158.42`
  - `metadata.all_success`: `true`
  - 进程退出码：`0`
- **原始日志完整性**：`docs/evidence/fix-7/remaining_regression/round2/full/raw/` 共保存 `84` 份完整原始日志（42 份 `<test_id>_stdout.log` + 42 份 `<test_id>_stderr.log`，直接取自 `TestExecutionResult.stdout` 与 `TestExecutionResult.stderr`）。

### 42 个唯一套件完整执行明细

| 序号 | `test_id` | Tier 覆盖归属 | Runner | 状态 | 退出码 | 耗时(s) | 原始日志字节 (stdout / stderr) | 视觉验收状态 |
|---:|---|---|---|---|---:|---:|---|---|
| 01 | `architecture_integrity_gate` | `quick, full` | `python` | `PASSED` | `0` | `2.48` | `226 / 0` | `-` |
| 02 | `spatial_layout_clearance` | `quick, full, legacy` | `blender_headless` | `PASSED` | `0` | `1.68` | `519 / 0` | `-` |
| 03 | `dynamics_environment_query` | `quick, physics, full` | `python` | `PASSED` | `0` | `0.60` | `0 / 117` | `-` |
| 04 | `contact_dynamics_math` | `quick, physics, full` | `python` | `PASSED` | `0` | `0.58` | `0 / 122` | `-` |
| 05 | `contact_force_solver` | `quick, physics, full` | `python` | `PASSED` | `0` | `0.67` | `0 / 154` | `-` |
| 06 | `forward_dynamics` | `quick, physics, full` | `python` | `PASSED` | `0` | `0.59` | `0 / 126` | `-` |
| 07 | `closed_loop_dynamics` | `quick, physics, full` | `python` | `PASSED` | `0` | `1.12` | `0 / 135` | `-` |
| 08 | `runner_unit_tests` | `quick, full` | `python` | `PASSED` | `0` | `1.23` | `0 / 115` | `-` |
| 09 | `physics_joint_limits` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `1.57` | `4810 / 0` | `-` |
| 10 | `physics_rigid_link_com` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `1.58` | `3099 / 0` | `-` |
| 11 | `mesh_environment_query` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `4.29` | `191 / 10106` | `-` |
| 12 | `task7a2_p0_teleport_regression` | `quick, motion, full` | `blender_headless` | `PASSED` | `0` | `2.13` | `1583 / 0` | `-` |
| 13 | `task7a2_negative_invariance` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `1.67` | `631 / 972` | `-` |
| 14 | `environment_gate01_unit3` | `quick, motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `13.50` | `3291 / 3164` | `VISUAL_ACCEPTANCE_PENDING` |
| 15 | `environment_gate01_u3_s1` | `quick, motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `4.32` | `216 / 107` | `VISUAL_ACCEPTANCE_PENDING` |
| 16 | `environment_gate01_u3_s2` | `quick, motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `4.31` | `216 / 109` | `VISUAL_ACCEPTANCE_PENDING` |
| 17 | `environment_gate01_unit4` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `1.93` | `1428 / 1895` | `-` |
| 18 | `environment_gate01_unit4_closure` | `quick, physics, full` | `blender_headless` | `PASSED` | `0` | `1.89` | `963 / 296` | `-` |
| 19 | `terrain_planning_contract` | `quick, motion, full` | `blender_headless` | `PASSED` | `0` | `2.19` | `1946 / 317` | `-` |
| 20 | `physics_whole_body_controller` | `physics, full` | `blender_headless` | `PASSED` | `0` | `1.66` | `4131 / 0` | `-` |
| 21 | `physics_arm_ik` | `physics, full` | `blender_headless` | `PASSED` | `0` | `1.58` | `3468 / 0` | `-` |
| 22 | `physics_body_kinematics` | `physics, full` | `blender_headless` | `PASSED` | `0` | `2.52` | `4907 / 0` | `-` |
| 23 | `physics_body_inertia` | `physics, full` | `blender_headless` | `PASSED` | `0` | `11.12` | `11124 / 0` | `-` |
| 24 | `physics_contact_model` | `physics, full` | `blender_headless` | `PASSED` | `0` | `21.84` | `10659 / 0` | `-` |
| 25 | `contact_model_geometry_support_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `1.82` | `591 / 308` | `-` |
| 26 | `leg_ik_worldspace_init_reset` | `physics, full` | `blender_headless` | `PASSED` | `0` | `2.06` | `2776 / 297` | `-` |
| 27 | `leg_ik_ground_height_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `3.59` | `8801 / 312` | `-` |
| 28 | `leg_ik_world_rotation_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `3.46` | `11860 / 6689` | `-` |
| 29 | `arm_ik_lifecycle_world_transform_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `5.43` | `25063 / 7646` | `-` |
| 30 | `arm_ik_input_validation_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `3.83` | `14891 / 7343` | `-` |
| 31 | `physics_bridge_contract` | `physics, full` | `blender_headless` | `PASSED` | `0` | `21.61` | `10008 / 0` | `-` |
| 32 | `dynamics_playground_blend` | `physics, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `1.47` | `1235 / 0` | `VISUAL_ACCEPTANCE_PENDING` |
| 33 | `playground_dynamics_states` | `physics, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `3.06` | `191 / 108` | `VISUAL_ACCEPTANCE_PENDING` |
| 34 | `visual_evidence_telemetry` | `physics, full` | `python` | `AUTOMATED_PASS` | `0` | `0.34` | `0 / 108` | `VISUAL_ACCEPTANCE_PENDING` |
| 35 | `contact_elevation_gap_repro` | `physics, full` | `blender_headless` | `PASSED` | `0` | `1.84` | `1060 / 331` | `-` |
| 36 | `motion_walk_r3b2` | `motion, full` | `blender_headless` | `PASSED` | `0` | `5.61` | `2576 / 0` | `-` |
| 37 | `motion_run_r3b2` | `motion, full` | `blender_headless` | `PASSED` | `0` | `3.69` | `2597 / 0` | `-` |
| 38 | `motion_sprint_start_r3b2` | `motion, full` | `blender_headless` | `PASSED` | `0` | `4.32` | `2665 / 0` | `-` |
| 39 | `motion_sprint_brake_r3b2` | `motion, full` | `blender_headless` | `PASSED` | `0` | `2.51` | `1792 / 0` | `-` |
| 40 | `integration_unified_motion` | `motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `1.48` | `1475 / 0` | `VISUAL_ACCEPTANCE_PENDING` |
| 41 | `task7a1_character_playground` | `motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `2.74` | `1019 / 4021` | `VISUAL_ACCEPTANCE_PENDING` |
| 42 | `task7a2_terrain_traversal` | `motion, full` | `blender_headless` | `AUTOMATED_PASS` | `0` | `2.51` | `3052 / 0` | `VISUAL_ACCEPTANCE_PENDING` |

---

## 8. FAIL / ERROR / SKIPPED / NOT_RUN 清单

- **FAIL**：`0`（无）
- **ERROR**：`0`（无）
- **SKIPPED**：`0`（无；`required_skipped = 0`, `optional_skipped = 0`）
- **NOT_RUN**：`0`（无）

---

## 9. 验收结论与视觉验收待办

- **Atomicity 联合覆盖结论**：`ATOMICITY_COVERAGE_223_OF_223_PASS`（历史 180 + 本轮 43 = 223/223）
- **FULL 自动化验收结论**：`AUTOMATED_REGRESSION_COMPLETE`（42/42 唯一套件全部通过，`metadata.all_success = true`；不自动宣告 10-B 结项或人工视觉验收完成）
- **视觉验收待办（9 项 `AUTOMATED_PASS`，均保持 `VISUAL_ACCEPTANCE_PENDING`）**：
  1. `environment_gate01_unit3`
  2. `environment_gate01_u3_s1`
  3. `environment_gate01_u3_s2`
  4. `dynamics_playground_blend`
  5. `playground_dynamics_states`
  6. `visual_evidence_telemetry`
  7. `integration_unified_motion`
  8. `task7a1_character_playground`
  9. `task7a2_terrain_traversal`

---

## 10. 未授权修改核查与分支保护

- **是否出现未授权修改**：**否**
  - `git diff --exit-code` = `0`，`git diff --cached --exit-code` = `0`。
  - 6 项冻结文件 Git Blob 零变更，历史证据目录只读保留，7 项历史未跟踪文件保持原状。
- **`master` 分支状态**：保持未修改（`a2c9b383b71fb2e84bc453cf4cd7926141d61dd9`）。
- **新增证据目录**：`docs/evidence/fix-7/remaining_regression/round2/`。

---

## 11. 最终状态

`FIX7_AUTOMATED_REGRESSION_PASS_WAITING_FOR_CHATGPT_AUDIT`
