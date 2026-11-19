# TASK 10-B｜fix-7：最终自动化回归执行报告

## 1. 基线信息

* **仓库与分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试前 HEAD**：`1da95568f626d3469943cb686b30ea35baaf092b`
* **Blender 版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **Python 版本**：`3.13.9 (main, Jan 16 2026, 12:29:45) [MSC v.1944 64 bit (AMD64)]`
* **前置 Git Blob SHA 核验结果**：
  * `tests/test_registry.py`：`43acac995be2994596f852460d52ea9f77a99998`（一致）
  * `tests/run_test_suite.py`：`eaa4658fc5b9e7adc15dde80d3cc43857e18bc05`（一致）
  * `tests/test_task10b_transaction_atomicity.py`：`b0f39ea14217b459848ee1100d4b25d4446ad80f`（一致）
  * `tests/test_bug11_datablock_cleanup.py`：`f3a8fcca15784f1e8110b8a9c2258ce3921ba746`（一致）
  * `tests/test_bug12_cross_armature_real_resources.py`：`8fe2597e2ac4c8cbce6c2feea5e22e4f74349b40`（一致）
* **治理文件状态核对**：
  * `origin/master:WORKFLOW_GOVERNANCE.md`：`APPROVED (正式生效)`
  * `audit/task-10-b-9` 分支本地 `WORKFLOW_GOVERNANCE.md` 仍显示 `DRAFT — PENDING USER APPROVAL` 的历史差异仅作记录，本轮未作修改。

---

## 2. 测试结果总表

| 分组 | 计划数量 | 实际数量 | PASS | FAIL | ERROR | NOT_RUN |
|---|---:|---:|---:|---:|---:|---:|
| Atomicity (`TestArmIKTransactionAtomicity`) | 224 | 发现 223 / 执行 0 | 0 | 1 (发现数量核对不匹配) | 0 | 223 (`NOT_RUN`) |
| BUG11 (`TestBug11TypeADataBlockFaults`) | 8 | 0 (`NOT_RUN`) | 0 | 0 | 0 | 8 (`NOT_RUN`) |
| BUG12 (`TestBug12RealCrossArmaturePending`) | 4 | 0 (`NOT_RUN`) | 0 | 0 | 0 | 4 (`NOT_RUN`) |
| FULL (`get_tests_for_tier(TestTier.FULL)`) | 42 suites | 0 suites (`NOT_RUN`) | 0 | 0 | 0 | 42 (`NOT_RUN`) |

* **说明**：
  * 本轮严格执行第 4、5 节规定：在 Group A (`Atomicity`) 中通过 `unittest.defaultTestLoader.loadTestsFromTestCase(TestArmIKTransactionAtomicity)` 实际发现 **223** 项测试，与第 3.A / 5 节冻结要求数量 **224** 不一致，触发第 5 节“3. 核对发现数量与冻结数量一致……若任一条件不满足，立即停止后续执行”与第 4 节“任一组失败，立即停止，不启动后续测试组。不得修复后继续跑”。
  * 因此 Group A 进程以退出码 `2` 终止，未擅自将冻结阈值 `224` 改为 `223` 重跑；后续 Group B (`BUG11`)、Group C (`BUG12`) 与 Group D (`FULL` 去重并集，含 `QUICK`、`PHYSICS`、`MOTION`) 均严格保持 **`NOT_RUN`**。
  * `CONTRACT10` 的六项 WBC 跨模块专项本轮未执行（`NOT_RUN`，最终归属为 Task 12-A）。

---

## 3. Group A 停止原因与源码只读核实

* **原始 `atomicity_stdout.log` 输出**：
  ```text
  Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)
  FIX7_GROUP atomicity DISCOVERED 223 EXPECTED 224
  ```
* **原始 `atomicity_stderr.log` 输出**：`0 bytes`（空）
* **源码 AST 只读核实**：
  * 对 `tests/test_task10b_transaction_atomicity.py`（Blob SHA `b0f39ea14217b459848ee1100d4b25d4446ad80f`）中的 `TestArmIKTransactionAtomicity` 进行只读 AST 解析：
  * 类内全部 `def test_*` 方法共 **223** 个，首项为 `test_31_snapshot_fidelity_controllers`（编号 `31`），末项为 `test_253_concurrent_pending_records_on_distinct_armatures`（编号 `253`）。
  * 区间 `[31, 253]` 内无任何跳号（`MISSING_NUMBERS_IN_31_253 = []`）、无重号（`DUPLICATE_NUMBERS = []`）、无非编号 `test_*` 方法；按闭区间整数计数为 $253 - 31 + 1 = 223$ 项，与冻结指令中的 `224` 存在 1 项算术差值。

---

## 4. 额外检查项（第 8 节）

1. **FULL Tier 去重映射核验（只读静态核验，实际运行状态为 `NOT_RUN`）**：
   * `get_tests_for_tier(TestTier.FULL)` 返回 **42** 个唯一测试套件（`42` 个唯一 `test_id`、`42` 个唯一 `script_path`）。
   * 等于 `QUICK (19) ∪ PHYSICS (27) ∪ MOTION (12)` 的有序去重并集（`EQUALS_QPM_UNION = True`），且与 `LEGACY`-only 测试无交集（`LEGACY_ONLY_OVERLAP = 0`）。
   * 42 项映射清单：
     1. `architecture_integrity_gate` (`tests/test_architecture_integrity_gate.py`, `python`, `['quick', 'full']`, `visual=False`)
     2. `spatial_layout_clearance` (`tests/test_task3_spatial.py`, `blender_headless`, `['quick', 'full', 'legacy']`, `visual=False`)
     3. `dynamics_environment_query` (`tests/verify_task6gd_dynamics_playground.py`, `python`, `['quick', 'physics', 'full']`, `visual=False`)
     4. `contact_dynamics_math` (`tests/verify_task6gd_contact_dynamics.py`, `python`, `['quick', 'physics', 'full']`, `visual=False`)
     5. `contact_force_solver` (`tests/verify_task6gd_contact_force_solver.py`, `python`, `['quick', 'physics', 'full']`, `visual=False`)
     6. `forward_dynamics` (`tests/verify_task6gd_forward_dynamics.py`, `python`, `['quick', 'physics', 'full']`, `visual=False`)
     7. `closed_loop_dynamics` (`tests/verify_task6gd_closed_loop_dynamics.py`, `python`, `['quick', 'physics', 'full']`, `visual=False`)
     8. `runner_unit_tests` (`tests/test_runner_unit.py`, `python`, `['quick', 'full']`, `visual=False`)
     9. `physics_joint_limits` (`tests/verify_task6fc_joint_limits.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     10. `physics_rigid_link_com` (`tests/verify_task6fb_rigid_link.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     11. `mesh_environment_query` (`tests/test_mesh_environment_query.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     12. `task7a2_p0_teleport_regression` (`tests/test_p0_frame226_teleport_regression.py`, `blender_headless`, `['quick', 'motion', 'full']`, `visual=False`)
     13. `task7a2_negative_invariance` (`tests/test_terrain_walk_negative.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     14. `environment_gate01_unit3` (`tests/test_environment_gate01_unit3.py`, `blender_headless`, `['quick', 'motion', 'full']`, `visual=True`)
     15. `environment_gate01_u3_s1` (`tests/test_environment_gate01_u3_s1.py`, `blender_headless`, `['quick', 'motion', 'full']`, `visual=True`)
     16. `environment_gate01_u3_s2` (`tests/test_environment_gate01_u3_s2.py`, `blender_headless`, `['quick', 'motion', 'full']`, `visual=True`)
     17. `environment_gate01_unit4` (`tests/test_environment_gate01_unit4.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     18. `environment_gate01_unit4_closure` (`tests/test_environment_gate01_unit4_closure.py`, `blender_headless`, `['quick', 'physics', 'full']`, `visual=False`)
     19. `terrain_planning_contract` (`tests/test_terrain_planning_contract.py`, `blender_headless`, `['quick', 'motion', 'full']`, `visual=False`)
     20. `physics_whole_body_controller` (`tests/verify_task6fd_whole_body_controller.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     21. `physics_arm_ik` (`tests/verify_task6fa_arm_ik.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     22. `physics_body_kinematics` (`tests/verify_task6ga_body_kinematics.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     23. `physics_body_inertia` (`tests/verify_task6gb_body_inertia.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     24. `physics_contact_model` (`tests/verify_task6gc_contact_model.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     25. `contact_model_geometry_support_contract` (`tests/test_contact_model_geometry_support_contract.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     26. `leg_ik_worldspace_init_reset` (`tests/test_leg_ik_worldspace_init_reset.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     27. `leg_ik_ground_height_contract` (`tests/test_leg_ik_ground_height_contract.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     28. `leg_ik_world_rotation_contract` (`tests/test_leg_ik_world_rotation_contract.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     29. `arm_ik_lifecycle_world_transform_contract` (`tests/test_arm_ik_lifecycle_world_transform_contract.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     30. `arm_ik_input_validation_contract` (`tests/test_task10b_input_validation.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     31. `physics_bridge_contract` (`tests/verify_task6gc_r3b1_bridge.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     32. `dynamics_playground_blend` (`tests/verify_task6gd_playground_blend.py`, `blender_headless`, `['physics', 'full']`, `visual=True`)
     33. `playground_dynamics_states` (`tests/verify_task6gd_playground_dynamics.py`, `blender_headless`, `['physics', 'full']`, `visual=True`)
     34. `visual_evidence_telemetry` (`tests/verify_task6gd_visual_telemetry.py`, `python`, `['physics', 'full']`, `visual=True`)
     35. `contact_elevation_gap_repro` (`tests/test_contact_elevation_gap_repro.py`, `blender_headless`, `['physics', 'full']`, `visual=False`)
     36. `motion_walk_r3b2` (`tests/verify_r3b2_walk_action.py`, `blender_headless`, `['motion', 'full']`, `visual=False`)
     37. `motion_run_r3b2` (`tests/verify_r3b2_run_action.py`, `blender_headless`, `['motion', 'full']`, `visual=False`)
     38. `motion_sprint_start_r3b2` (`tests/verify_r3b2_sprint_start.py`, `blender_headless`, `['motion', 'full']`, `visual=False`)
     39. `motion_sprint_brake_r3b2` (`tests/verify_r3b2_sprint_brake.py`, `blender_headless`, `['motion', 'full']`, `visual=False`)
     40. `integration_unified_motion` (`tests/verify_unified_motion_integration.py`, `blender_headless`, `['motion', 'full']`, `visual=True`)
     41. `task7a1_character_playground` (`tests/verify_task7a1_character_playground.py`, `blender_headless`, `['motion', 'full']`, `visual=True`)
     42. `task7a2_terrain_traversal` (`tests/verify_task7a2_terrain_traversal.py`, `blender_headless`, `['motion', 'full']`, `visual=True`)
2. **全部原始日志路径**：
   * `docs/evidence/fix-7/atomicity_stdout.log`（已生成，2 行）
   * `docs/evidence/fix-7/atomicity_stderr.log`（已生成，0 bytes）
   * `bug11_stdout.log`、`bug11_stderr.log`、`bug12_stdout.log`、`bug12_stderr.log` 及 `full/`：因对应测试组为 `NOT_RUN`，依据第 7 节“没有执行的测试组不得伪造日志”未生成。
3. **每个进程的退出码**：
   * Group A (`atomicity`) Blender 进程退出码：`2`
   * Group B (`bug11`)、Group C (`bug12`)、Group D (`full`)：`NOT_RUN`（未启动进程）
4. **运行器自身是否出现异常**：否（`TestSuiteRunner` 未启动）。
5. **是否修改了任何已跟踪文件**：否（`git diff --exit-code` = `0`，`git diff --cached --exit-code` = `0`）。
6. **是否产生非预期资产**：否（仅在 `docs/evidence/fix-7/` 下生成 `atomicity_stdout.log`、`atomicity_stderr.log` 与 `fix7_test_report.md`；既有 7 项历史未跟踪文件保持原状）。
7. **是否存在视觉验收待办**：是。FULL Tier 中共有 9 项 `is_visual_acceptance=True` 的套件（序号 14、15、16、32、33、34、40、41、42），本轮均处于 `NOT_RUN` 状态，且即便自动化通过也仍需人工视觉验收。
