# TASK 10-B / fix-7 — Remaining Full Regression Report (Fail-Fast Circuit Breaker Triggered at Group A / TEST-57)

## 1. 固定基线与环境核验

- **仓库**：`cgfe10231-ai/ProceduralAnimation`
- **分支**：`audit/task-10-b-9`
- **固定基线 HEAD**：`5f6357a780b010e7ae445c6bb3c1150a3f9d952c`
- **治理状态**：`origin/master:WORKFLOW_GOVERNANCE.md` 为 `APPROVED (正式生效)`
- **运行环境**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)` / 内嵌 `Python 3.13.9`
- **启动器**：Windows PowerShell 5.1 `System.Diagnostics.ProcessStartInfo` 使用 `$psi.Arguments`（`--background --python-exit-code 1 --python "<tempScriptPath>"`）与 `ReadToEndAsync()` 双流异步捕获。

### 冻结文件 Git Blob 核验（全部一致）

| 文件 | 预期 / 实测 Git Blob SHA | 状态 |
|---|---|---|
| `tests/test_task10b_transaction_atomicity.py` | `1bfb615129a0f83521e6c49cd2802456bb87bd15` | MATCH |
| `tests/test_bug11_datablock_cleanup.py` | `f3a8fcca15784f1e8110b8a9c2258ce3921ba746` | MATCH |
| `tests/test_bug12_cross_armature_real_resources.py` | `8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40` | MATCH |
| `tests/test_registry.py` | `43acac995be2994596f852460d52ea9f77a99998` | MATCH |
| `tests/run_test_suite.py` | `eaa4658fc5b9e7adc15dde80d3cc43857e18bc05` | MATCH |
| `src/rig/arm_ik.py` | `bedbcda220af8d47d11b5400de8a56375019eba4` | MATCH |

---

## 2. 历史 134 项有效 PASS 证据只读核验

已对三份归档原始日志执行只读解析校验，确认 `TEST-100`～`TEST-233` 共 **134** 项均有真实 `ok` 记录且无缺口：

| 历史范围 | 有效去重计数 | 原始证据日志 | 只读核验结果 |
|---|---:|---|---|
| `TEST-100`～`TEST-196` | `97` | `docs/evidence/fix-7/round2/atomicity_stdout.log` | 97 项全部 `ok`（随后在 `TEST-197` 处 `ERROR` 停止） |
| `TEST-197`～`TEST-226` | `30` | `docs/evidence/fix-7/round3/atomicity_remaining_stdout.log` | 30 项全部 `ok`（随后在 `TEST-227` 处 `FAIL` 停止） |
| `TEST-227`～`TEST-233` | `7` | `docs/evidence/fix-7/collection_targeted/round2/test_stdout.log` | 日志包含 `TEST-225`～`TEST-233` 共 9 项 `ok`；`TEST-225`、`226` 已在 round3 计入，本表去重后计入新增 7 项 |
| **历史合计** | **`134`** | 去重并集覆盖 `TEST-100`～`TEST-233` | **VALID (`EXACT_100_233=True`)** |

---

## 3. 各组执行总览与退出码

> 统计单位说明：Group A（Atomicity）、Group B（BUG11）、Group C（BUG12）以独立 `unittest` **测试方法数**计量；Group D（FULL）以 `TestTier.FULL` 注册表**唯一套件数**计量，二者不得简单相加。

| 组别 | 目标范围 | 统计单位 | 计划数 | 实际执行 | PASS | FAIL | ERROR | SKIPPED | NOT_RUN | 真实退出码 | 完整原始日志路径 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| **Group A** | Atomicity 剩余 (`TEST-234`～`253`, `TEST-31`～`99`) | 测试方法 | `89` | `47` | `46` | `1` | `0` | `0` | `42` | `1` | `docs/evidence/fix-7/remaining_regression/atomicity_stdout.log`<br>`docs/evidence/fix-7/remaining_regression/atomicity_stderr.log` |
| **Group B** | `tests/test_bug11_datablock_cleanup.py` (`TestBug11TypeADataBlockFaults`) | 测试方法 | `8` | `0` | `0` | `0` | `0` | `0` | `8` | `NOT_RUN` | 未执行（按规则不生成空日志） |
| **Group C** | `tests/test_bug12_cross_armature_real_resources.py` (`TestBug12RealCrossArmaturePending`) | 测试方法 | `4` | `0` | `0` | `0` | `0` | `0` | `4` | `NOT_RUN` | 未执行（按规则不生成空日志） |
| **Group D** | `TestTier.FULL` 注册表 | 唯一套件 | `42` | `0` | `0` | `0` | `0` | `0` | `42` | `NOT_RUN` | 未执行（按规则不生成空日志） |

---

## 4. Group A 失败详情（触发熔断）

- **失败用例**：`TEST-57` — `test_57_collection_hierarchy_full_recovery`
- **执行停止点**：`Ran 47 tests in 3.737s` / `FAILED (failures=1)` / `FIX7_REMAINING_EXECUTED 47` / `FIX7_REMAINING_PASS False`
- **Blender 进程真实退出码**：`1`
- **`atomicity_stderr.log`**：0 字节（空）

### 原始异常与完整堆栈（摘自 `atomicity_stdout.log`）

```text
======================================================================
FAIL: test_57_collection_hierarchy_full_recovery (fix7_remaining_atomicity.TestArmIKTransactionAtomicity.test_57_collection_hierarchy_full_recovery)
TEST-57: Full recovery of multi-level nested collection hierarchy and scene linkages after transaction rollback.
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tests/test_task10b_transaction_atomicity.py", line 1294, in test_57_collection_hierarchy_full_recovery
    self.assertNotIn("RogueCol", bpy.data.collections)
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'RogueCol' unexpectedly found in <bpy_collection[4], BlendDataCollections>

----------------------------------------------------------------------
Ran 47 tests in 3.737s

FAILED (failures=1)
FIX7_REMAINING_EXECUTED 47
FIX7_REMAINING_PASS False
```

### 严格熔断执行说明

- 按照第 8 节失败熔断规则（`A → B → C → D` 顺序准入），Group A 在 `TEST-57` 发生 `FAIL` 且退出码为 `1` 后立即停止。
- 未进行任何自动重试、代码修改或断言变更；Group B（BUG11）、Group C（BUG12）及 Group D（FULL）均未启动，全部标记为 `NOT_RUN`，且未生成未执行组的空日志。

---

## 5. Group A 全部 89 项明细（按选择器实际执行顺序）

| 序号 | 测试编号 | 测试方法名 | 实际结果 |
|---:|---|---|---|
| 1 | `TEST-234` | `test_234_layer6_returns_cleanup_success_without_state_mutation` | `PASS` |
| 2 | `TEST-235` | `test_235_initial_cleanup_failure_coordinator_sets_cleanup_pending_and_chains_cause` | `PASS` |
| 3 | `TEST-236` | `test_236_pending_retry_failure_preserves_state_and_pending_gate_with_chain` | `PASS` |
| 4 | `TEST-237` | `test_237_pending_retry_success_coordinator_transitions_committed_and_unregisters` | `PASS` |
| 5 | `TEST-238` | `test_238_failed_transaction_rejected_by_cleanup_isolation_preserved` | `PASS` |
| 6 | `TEST-239` | `test_239_pending_registry_invalid_state_or_identity_rejects_and_refuses_pop` | `PASS` |
| 7 | `TEST-240` | `test_240_forged_cleanup_success_with_remaining_resources_rejected_by_coordinator` | `PASS` |
| 8 | `TEST-241` | `test_241_cross_armature_cannot_borrow_cleanup_result_or_pending_gate` | `PASS` |
| 9 | `TEST-242` | `test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback` | `PASS` |
| 10 | `TEST-243` | `test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending` | `PASS` |
| 11 | `TEST-244` | `test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation` | `PASS` |
| 12 | `TEST-245` | `test_245_partial_cleanup_progress_preserved_subsequent_retry_only_processes_remaining` | `PASS` |
| 13 | `TEST-246` | `test_246_cleanup_pending_blocks_bilateral_reset` | `PASS` |
| 14 | `TEST-247` | `test_247_all_bilateral_write_entrypoints_blocked_under_cleanup_pending` | `PASS` |
| 15 | `TEST-248` | `test_248_reinitialization_under_pending_cannot_bypass_gate` | `PASS` |
| 16 | `TEST-249` | `test_249_armature_a_pending_does_not_block_independent_armature_b` | `PASS` |
| 17 | `TEST-250` | `test_250_alternating_execution_pending_a_and_healthy_b` | `PASS` |
| 18 | `TEST-251` | `test_251_retry_cleanup_failure_on_a_preserves_b_admission` | `PASS` |
| 19 | `TEST-252` | `test_252_a_cleanup_success_restores_bilateral_reset_admission` | `PASS` |
| 20 | `TEST-253` | `test_253_concurrent_pending_records_on_distinct_armatures` | `PASS` |
| 21 | `TEST-31` | `test_31_snapshot_fidelity_controllers` | `PASS` |
| 22 | `TEST-32` | `test_32_snapshot_fidelity_pose_bones` | `PASS` |
| 23 | `TEST-33` | `test_33_snapshot_fidelity_constraints_and_collection` | `PASS` |
| 24 | `TEST-34` | `test_34_direct_rollback_uninitialized_scene` | `PASS` |
| 25 | `TEST-35` | `test_35_direct_rollback_wrong_type_controller` | `PASS` |
| 26 | `TEST-36` | `test_36_direct_rollback_initialized_scene_controllers` | `PASS` |
| 27 | `TEST-37` | `test_37_direct_rollback_pose_bones` | `PASS` |
| 28 | `TEST-38` | `test_38_direct_rollback_constraints` | `PASS` |
| 29 | `TEST-39` | `test_39_fault_injection_setup_arm_ik_after_first_controller` | `PASS` |
| 30 | `TEST-40` | `test_40_fault_injection_setup_arm_ik_after_controller_replaced` | `PASS` |
| 31 | `TEST-41` | `test_41_fault_injection_setup_arm_ik_after_constraints_or_prebend` | `PASS` |
| 32 | `TEST-42` | `test_42_fault_injection_set_hand_ik_target_during_auto_init` | `PASS` |
| 33 | `TEST-43` | `test_43_fault_injection_set_hand_ik_target_after_hand_location` | `PASS` |
| 34 | `TEST-44` | `test_44_fault_injection_set_hand_ik_target_after_hand_rotation` | `PASS` |
| 35 | `TEST-45` | `test_45_fault_injection_set_hand_ik_target_after_pole_location` | `PASS` |
| 36 | `TEST-46` | `test_46_fault_injection_set_hand_ik_target_between_influences` | `PASS` |
| 37 | `TEST-47` | `test_47_fault_injection_set_hand_ik_target_after_rot_influence` | `PASS` |
| 38 | `TEST-48` | `test_48_fault_injection_set_hand_ik_target_during_state_read` | `PASS` |
| 39 | `TEST-49` | `test_49_fault_injection_set_arm_ik_influence_side_l` | `PASS` |
| 40 | `TEST-50` | `test_50_fault_injection_set_arm_ik_influence_side_both` | `PASS` |
| 41 | `TEST-51` | `test_51_success_path_fresh_and_reentrant_across_8_rotation_modes` | `PASS` |
| 42 | `TEST-52` | `test_52_success_after_failure_recovery_and_explicit_verification_error` | `PASS` |
| 43 | `TEST-53` | `test_53_controller_full_fields_verification` | `PASS` |
| 44 | `TEST-54` | `test_54_bone_full_fields_verification` | `PASS` |
| 45 | `TEST-55` | `test_55_constraints_full_fields_verification` | `PASS` |
| 46 | `TEST-56` | `test_56_wrong_type_and_unrelated_constraints_lossless_recovery` | `PASS` |
| 47 | `TEST-57` | `test_57_collection_hierarchy_full_recovery` | `FAIL` |
| 48 | `TEST-58` | `test_58_snapshot_failure_clears_active_transaction_stack` | `NOT_RUN` |
| 49 | `TEST-59` | `test_59_cross_armature_nested_transaction_rejection` | `NOT_RUN` |
| 50 | `TEST-60` | `test_60_get_arm_ik_state_internal_exception_triggers_rollback` | `NOT_RUN` |
| 51 | `TEST-61` | `test_61_depsgraph_update_exception_triggers_rollback` | `NOT_RUN` |
| 52 | `TEST-62` | `test_62_first_time_autoinit_success_path_and_failure_resilience` | `NOT_RUN` |
| 53 | `TEST-63` | `test_63_fault_injection_public_interface_boundary` | `NOT_RUN` |
| 54 | `TEST-64` | `test_64_commit_cleanup_failure_and_datablock_lifecycle` | `NOT_RUN` |
| 55 | `TEST-65` | `test_65_reversible_commit_preparation_failure_rolls_back` | `NOT_RUN` |
| 56 | `TEST-66` | `test_66_irreversible_cleanup_failure_semantics_and_retry` | `NOT_RUN` |
| 57 | `TEST-67` | `test_67_partial_cleanup_failure_and_convergence` | `NOT_RUN` |
| 58 | `TEST-68` | `test_68_depsgraph_update_call_boundary_exception_rollback` | `NOT_RUN` |
| 59 | `TEST-69` | `test_69_snapshot_array_immutability_and_independence` | `NOT_RUN` |
| 60 | `TEST-70` | `test_70_rna_property_restoration_failure_error_aggregation` | `NOT_RUN` |
| 61 | `TEST-71` | `test_71_external_collection_protection_during_rollback` | `NOT_RUN` |
| 62 | `TEST-72` | `test_72_collection_rename_and_multi_parent_restoration` | `NOT_RUN` |
| 63 | `TEST-73` | `test_73_stashed_constraint_identity_and_ordering` | `NOT_RUN` |
| 64 | `TEST-74` | `test_74_sequential_failures_and_subsequent_success_avalanche_protection` | `NOT_RUN` |
| 65 | `TEST-75` | `test_75_side_isolation_and_shared_resource_protection` | `NOT_RUN` |
| 66 | `TEST-76` | `test_76_validator_corruption_detection` | `NOT_RUN` |
| 67 | `TEST-77` | `test_77_destroyed_constraint_identity_is_rejected` | `NOT_RUN` |
| 68 | `TEST-78` | `test_78_destroyed_constraint_causes_rollback_failure` | `NOT_RUN` |
| 69 | `TEST-79` | `test_79_external_character_collection_creation_preserved` | `NOT_RUN` |
| 70 | `TEST-80` | `test_80_external_character_collection_members_preserved` | `NOT_RUN` |
| 71 | `TEST-81` | `test_81_cleanup_pending_registry_and_retry` | `NOT_RUN` |
| 72 | `TEST-82` | `test_82_partial_cleanup_object_removed_datablock_failure_and_retry` | `NOT_RUN` |
| 73 | `TEST-83` | `test_83_datablock_shared_users_and_same_name_replacement_preserved` | `NOT_RUN` |
| 74 | `TEST-84` | `test_84_sequential_transactions_failure_recovery_isolation` | `NOT_RUN` |
| 75 | `TEST-85` | `test_85_same_armature_cleanup_pending_blocks_new_transaction` | `NOT_RUN` |
| 76 | `TEST-86` | `test_86_unrelated_armature_not_blocked_by_pending_cleanup` | `NOT_RUN` |
| 77 | `TEST-87` | `test_87_pending_cleanup_retry_success_restores_write_admission` | `NOT_RUN` |
| 78 | `TEST-88` | `test_88_stashed_constraint_same_name_replacement_not_erroneously_deleted` | `NOT_RUN` |
| 79 | `TEST-89` | `test_89_original_character_collection_rename_restores_identity_and_name` | `NOT_RUN` |
| 80 | `TEST-90` | `test_90_original_parent_collection_rename_restored_by_identity` | `NOT_RUN` |
| 81 | `TEST-91` | `test_91_external_child_collection_preserved_on_rollback` | `NOT_RUN` |
| 82 | `TEST-92` | `test_92_full_lifecycle_and_continuous_transaction_integration` | `NOT_RUN` |
| 83 | `TEST-93` | `test_93_transaction_created_controller_renamed_cleaned_by_identity` | `NOT_RUN` |
| 84 | `TEST-94` | `test_94_external_same_name_controller_preserved_when_transaction_controller_renamed` | `NOT_RUN` |
| 85 | `TEST-95` | `test_95_original_controller_physically_destroyed_fails_restoration` | `NOT_RUN` |
| 86 | `TEST-96` | `test_96_original_controller_name_occupied_by_external_object_fails_restoration` | `NOT_RUN` |
| 87 | `TEST-97` | `test_97_stashed_constraint_reference_invalid_with_same_name_replacement` | `NOT_RUN` |
| 88 | `TEST-98` | `test_98_controller_registered_before_collection_link_failure` | `NOT_RUN` |
| 89 | `TEST-99` | `test_99_exception_after_logical_commit_enters_cleanup_pending` | `NOT_RUN` |

---

## 6. 联合覆盖结论与验收状态

- **Atomicity 223 项联合覆盖结论**：
  - 历史有效 PASS：`134`（`TEST-100`～`233`）
  - 本轮 PASS：`46`（`TEST-234`～`253`、`TEST-31`～`56`）
  - 合计 PASS：`180 / 223`
  - 合计 FAIL：`1 / 223`（`TEST-57`）
  - 合计 ERROR：`0 / 223`
  - 合计 SKIPPED：`0 / 223`
  - 合计 NOT_RUN：`42 / 223`（`TEST-58`～`99`）
  - **结论**：**INCOMPLETE / FAILED**（未达成 `ATOMICITY_COVERAGE_223_OF_223_PASS`）
- **BUG11 (8 项)**：`NOT_RUN`（`0 / 8`，因 Group A 失败熔断未启动）
- **BUG12 (4 项)**：`NOT_RUN`（`0 / 4`，因 Group A 失败熔断未启动）
- **FULL 42 套件自动化验收结论**：`NOT_RUN`（`0 / 42`，因 Group A 失败熔断未启动；未达成 `AUTOMATED_REGRESSION_COMPLETE`）
- **视觉验收待办**：`VISUAL_ACCEPTANCE_PENDING`（FULL 套件尚未执行，人工视觉验收尚未开展）

---

## 7. 越界修改与 Git 分支核查

- **是否存在越界修改**：**否**
  - `git diff --exit-code`：`0`
  - `git diff --cached --exit-code`：`0`
  - 6 个冻结文件 Git Blob 与测试前完全一致。
  - 历史证据目录（`docs/evidence/fix-7/round2/`、`docs/evidence/fix-7/round3/`、`docs/evidence/fix-7/collection_targeted/`）保持只读未改动。
  - 7 项历史未跟踪文件保持原状。
- **`master` 分支保护**：`master` 与 `origin/master` 均保持在 `a2c9b383b71fb2e84bc453cf4cd7926141d61dd9`，未做任何修改或合并。
- **证据归档范围**：仅新增提交 `docs/evidence/fix-7/remaining_regression/`（包含 `fix7_remaining_report.md`、`atomicity_stdout.log`、`atomicity_stderr.log`）。

---

## 8. 最终状态

`FIX7_REGRESSION_FAILED_WAITING_FOR_CHATGPT_AUDIT`
