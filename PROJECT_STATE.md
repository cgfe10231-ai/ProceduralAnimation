# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-28
> **Task 12 / PKG-5 已验收冻结基线**：冻结生产源码基线 `eee276b39d204ccd46f4c17f37a09ec483bfcbae`，冻结测试基线 `90f4628a0c4212f4bb0468941cdde362cd68bef2`，最终验收证据提交 `e15d342b805ef45e7d54db2edf1c2804973e81a7`（收归分支 `task/12` 合并至 `master`）；Task 7B-1 专项验收提交 `fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`、Task 7B-2 专项验收提交 `a92280bbcb2243f0b43edd10b61bbadb39c72869`（保留于 `task/7b-1` → `task/7b-2` → `task/7b-3` → `task/7b-4` 连续子分支，未合入 `master`）；Task 11 历史基线：`added88a7e27eaaa6d1644473d560c5dcf45bc80` / `07aec5d8d35e5d77ff956f160840d1c2491b770e`（收归 `task/11`）；Task 10-D 历史基线 `824c52ec73f86aa3d08245a58297118cb4a9f110` / `7f14ff722caecadec555194cc7d08f454c94c6c8`（收归 `task/10-d`）；10-C 历史收归基线 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`；10-B 历史主干合并 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`、回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`、证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`。 Task 7B-3 专项最终证据：`d9862ada5c392080a03efb38ea7f2e90201580d2`。
> **当前状态：`Task 12 / PKG-5` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`d16454528e28b46e9cc60f9f6e1a10a7241eb551`）；原 16 项历史 Finding 已全部关闭（16 CLOSED / 0 OPEN）；`Task 7B-1` `COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`（`BUG-01 CLOSED`）；`Task 7B-2` `COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`（`BUG-01、BUG-02 CLOSED`）；`Task 7B-3`：`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`（20/20 PASS，`d9862ada`）；当前节点：`Task 7B-4`（`FINAL INTEGRATION ACCEPTANCE — OWNER AUTHORIZED`，分支 `task/7b-4`）。仅允许联合专项、相关独立回归、四级回归及证据归档。生产源码、测试脚本和永久规范保持只读。Phase 7B 尚未合入 `master`，须等待独立最终验收及负责人合并批准。`Phase 7C` 保持 `NOT AUTHORIZED`。**

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A / 10-B / 10-C / 10-D | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | Task 10 整体 `COMPLETED`，10-B 六层拆分、10-C、10-D 均收归 `master`，不再重新打开 |
| Task 11-A / 11-B (`FIND-R3-03` / `FIND-R3-04`) | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | FootLock 元数据生命周期与纯查询/支撑维持分离完成并合入 `master` |
| **Task 12-A / 12-B / 12-C / 12-D** | **`COMPLETED`** | 12-A WBC 单帧与 ROM 后反馈收敛、12-B Bridge 提交门禁与 `effective_dt` 校验、12-C 所有权收敛、12-D 联合专项与四级最终回归全通过（`BUG-01 CLOSED`） |
| **Task 12 / PKG-5（整体）** | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`** | 已通过独立验收并由负责人批准合入 `master` |
| **Task 7B-1** | **`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`** | Blender 5.1.1 专项 `T01–T12` `12/12 PASS`（`FAILED/SKIPPED/NOT_RUN=0`, `rc=0`）；`BUG-01 CLOSED`；生产源码零修改，证据提交 `fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`（`docs/evidence/7b-1/verification/`）；**未合入 `master`**，待 `7B-4` 整体合入 |
| **Task 7B-2** | **`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`** | Blender 5.1.1 专项 `T01–T14` 全部通过（`14 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`，退出码 `0`）；`BUG-01`、`BUG-02` `CLOSED`；`src/motion/contact_model.py::compute_hand_target_from_surface()`（Blob `267c6c997e0c02cd5f76b2936fc2c975ae50cf07`）与 `tests/verify_task7b2_hand_target_geometry.py`（Blob `b8381a354fc4e7e05e4b3c7013256baafa038aa4`）；证据提交 `a92280bbcb2243f0b43edd10b61bbadb39c72869`（`docs/evidence/7b-2/verification/`）；**未合入 `master`**，待 `7B-4` 整体合入 |
| **Task 7B-3** | **`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`** | Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。第一轮证据提交 `238383869203aaa39218d2695c2592bd80d44a2e`，`docs/evidence/7b-3/verification/`；第二轮证据提交 `d9862ada5c392080a03efb38ea7f2e90201580d2`，`docs/evidence/7b-3/verification_round2/`。 |
| **Task 7B-4** | **`FINAL INTEGRATION ACCEPTANCE — OWNER AUTHORIZED`** | 仅允许联合专项、相关独立回归、四级回归及证据归档。生产源码、测试脚本和永久规范保持只读。Phase 7B 尚未合入 `master`，须等待独立最终验收及负责人合并批准。`Phase 7C` 保持 `NOT AUTHORIZED`。 |
| Phase 7C | `NOT AUTHORIZED` | 19 骨骼运动学管线与 6-DOF 数值动力学管线仍然独立，尚未完成 7C 合流 |

### Task 10-C 子节点职责摘要
- `10-c-child1`：接口及合同审计，已完成。
- `10-c-child2`：PlannedHandTarget 两项字段，已实现并复验。
- `10-c-child3`：左右手无损转换及 FK/IK 仲裁，已实现并复验。
- `10-c-child4`：专项及历史兼容复验、ROM 截断后 Bridge 反馈同步，已通过。

### Task 10-D 子节点职责摘要
- `10-d-1` / `10-d-2` / `10-d-3`：独立上肢时间参数化、五次平滑与无状态 FK/IK 分段目标求值，已验收并由 `10-d-5` 收敛至 `src/motion/upper_limb_trajectory.py`。
- `10-d-4`：独立上肢轨迹接入生产链、Phase 6 约束权重 `CONSTANT` 关键帧持久化及控制器重复执行清理，已验收。
- `10-d-5`：中央全身控制调度收敛，通过 `MotionPlanner -> MotionRuntimeContext.compose_planned_pose() -> KinematicPlannedPose` 统一下发至五种生产 `MotionAction`，并完成 T01–T17（17/17 PASS）及两份场景人工视觉验收（2026-11-27）。

## 2. 源码确认事实
- `src/rig/arm_ik.py` 与 `src/scene_transaction_integrity/`：前者保留五个公开领域接口及领域配置常量；后者按六层物理架构承载事务协调、注册表与身份控制、受权资源/关系操作、上肢 IK 业务操作、快照/指纹/回滚核验及提交后清理（共 81 个 Python 文件，含包初始化文件），由 `wiring._create_arm_rig_transaction_context()` 装配 15 项显式依赖。
- `src/motion/whole_body_controller.py`（Blob `230a86acaa92b580c5c0aad0e0cdacd7df224a7a`）：Task 12-A 完成 ROM 截断后最终四肢/CoM 测量重算、`ROM_CONFLICT` 使用真实请求目标误差及失败状态原子恢复；**ROM 后最终反馈所有权已正式收归 WBC 独占**。
- `src/motion/kinematic_bridge.py`（Blob `4f9cc856b9c9b34c59dd4c6a4f0cee1e1d86ef96`）：PlannedHandTarget 保留 `pole_hint_world_xyz=None` 与 `clamp_reach=True`，`convert_planned_pose_to_wbc_targets()` 无损传递并仲裁 FK/IK；Task 12-B 确立 `effective_dt` 准入门禁与 WBC/ContactModel 失败禁止提交跨帧 7 项状态（`_last_time_sec`、`_last_frame`、`last_multi_contact`、`last_active_limb_targets`、`kinematics_tracker`）；Task 12-C 清除废弃的 `_reconcile_post_rom_feedback()`（ROM 后最终反馈不再在 Bridge 重复拼接），`tracking_errors`/`rom_violations`/`unmet_constraints` 统一读取 WBC 最终结果；Phase 6 写入控制器与约束 `influence`（`CONSTANT` 插值），底层关键帧故障时可能残留部分 F-Curve（七项 Bridge 提交状态保持干净）。
- `src/motion/body_kinematics.py`（Blob `e204793ca3a326a798f75a66e24e98a945e53be7`）与 `src/motion/body_inertia.py`（Blob `0cd7efadf265072fd1665615815792f41b792f1b`）：Task 12-C 统一有效支撑接触过滤与时空快照一致性。
- `src/motion/contact_model.py`（Blob `267c6c997e0c02cd5f76b2936fc2c975ae50cf07`）：在既有 `ContactRecord`、`MultiContactState` 与 `DEFAULT_LIMB_LOCAL_ANCHORS` 基础上，Task 7B-2 新增并验收单一无状态纯几何转换函数 `compute_hand_target_from_surface()`（严格校验 `mesh:<object_name>:<polygon_index>` 与 float64 归一化切平面投影，不访问 `bpy`、不建立接触、不执行 IK/ROM）。
- `src/motion/upper_limb_trajectory.py`：公共无状态上肢轨迹模块，定义 `UpperLimbSegment`、`_evaluate_upper_limb_progress()`、`_validate_upper_limb_vector()`、`_evaluate_upper_limb_segment()`、`validate_upper_limb_segment_sequence()`；`src/motion/terrain_walk.py` 保留兼容重导出。
- `src/motion/framework.py`、`terrain_walk.py`、`run_cycle.py`、`sprint_start.py`、`sprint_brake.py`：五种生产 `MotionAction`（`StartStopWalkAction`、`TerrainWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）均通过 `MotionRuntimeContext.compose_planned_pose()` 消费中央 `upper_limb_L/R` 轨迹并沿唯一 `Bridge -> WBC -> Rig -> MotionState` 链执行；无独立上肢输入时历史动作零退化。`MotionPlanner.execute()` 在执行前验证所有权后清空 `HandIK`/`ElbowPole` 历史动画曲线。
- `src/rig/ik.py`（Blob `f1492c748f8f143041bc6ed4b29d9529824d527f`）：定义共享 7 键常量 `FOOT_LOCK_METADATA_KEYS`；`setup_leg_ik()` 与 `reset_leg_ik()` 清理 7 项元数据；`_snapshot_leg_rig_state()` 与 `_rollback_leg_rig_state()` 脱离 Blender `IDPropertyArray` 完整捕获、恢复及核验 `FootIK.L/R` 的 7 项元数据存在性与值（不伪造缺失键，保留无关自定义属性）；`get_leg_ik_state(..., *, update_scene: bool = True)` 区分默认场景刷新与无刷新读取路径。
- `src/rig/foot_contact.py`（Blob `0b74e83a835362e9ff400106847a6f6c83dd18fc`）：`lock_foot_contact()` 先全量写入 7 项 `FOOT_LOCK_METADATA_KEYS` 再最后发布 `is_locked=True`；`unlock_foot_contact()` 在 Phase B 事务内清理 7 项元数据并显式执行 `_apply_ik_prebend_hint()` 与 `view_layer.update()` 后返回 `get_foot_support_state()`；`get_foot_support_state()` 收敛为零副作用纯查询（缺失 `FootIK`/`KneePole` 直接拒绝、不创建资源；锁定态严格校验全部 7 项格式与有限性；解锁态不消费亦不清理残留字段）；`evaluate_foot_support()` 保留主动支撑维持，先只读核验已有锁定控制器与 7 项快照完整性再进入维护写入并委托 `get_foot_support_state()`。
- `src/scene/playground_character_assembly.py`（Blob `5bb437d92cbd0d2816fffcae52ae026b35ceb0a4`）：Stage D 在 `bridge.execute_frame()` 后调用纯查询 `get_foot_support_state(arm_obj, "L")`，不再重复执行主动支撑维护。
- 19 骨骼生产运动学管线与独立 6-DOF 数值动力学管线尚未完成主循环合流，不能宣称已具备真实受力反馈动力学闭环。

## 3. 测试事实（保留统计单位和时间边界）
| 项目 | 有效结果 | 证据性质 |
|---|---|---|
| Input Validation | **30/30 PASS** | 拆分后基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32` 实测，包含于 FULL（不另行重复计数） |
| Atomicity TEST-31～253 | **223/223 PASS** | 拆分后同一冻结源码基线 `2f248bf` 单轮完整执行；Collection TEST-225～233 包含于 Atomicity，不重复计数 |
| BUG11 | **8/8 PASS** | 拆分后基线 `2f248bf` Type A DataBlock 授权与故障窗口专项实测 |
| BUG12 | **4/4 PASS** | 拆分后基线 `2f248bf` 跨 Armature 隔离专项实测；不外推至所有自然端到端路径 |
| FULL | **42/42 自动化通过** | 33 PASSED + 9 AUTOMATED_PASS；九项人工视觉验收仍为独立待办 |
| 10-D 最终回归 `quick` / `physics` / `motion` / `full` | **19/19、27/27、12/12、42/42 PASS** (`rc=0`) | `824c52ec` 当前生产实测（`full` 含 33 PASSED + 9 AUTOMATED_PASS；九项历史人工视觉待办独立保留）；证据：`docs/evidence/10-d/final_acceptance/` |
| 迁移/受影响专项当前实现复验 | **10-C 38/38 + 10-d-2 12/12 + 10-d-3 18/18(T15 68/68) + 10-d-4 清理 PASS** | `824c52ec` 当前生产代码实测（另含 `physics_bridge_contract` 14/14），`docs/evidence/10-d/final_acceptance/migrated_checks/` |
| 10-d-5 中央全身控制专项（T01–T17） | **17/17 PASS** (`rc=0`) | Blender 5.1.1 实测 + 历史基线 `9f5f8250` 对照，`docs/evidence/10-d/10-d-5/centralized_verification/` |
| 10-D 人工视觉验收（2026-11-27） | **2/2 OWNER APPROVED** | 仅登记 `output/task10d_centralized_whole_body.blend`（1026f）与 `output/task10d_running_whole_body.blend`（528f） |
| Task 11 联合专项与连续生产链（`added88a7e`） | **A01–A19 `19/19`、B01–B20 `20/20`（B08 37 子项全过）、联合专项 `38/38`、A16 两场景重开 `PASS`** | Blender 5.1.1 实测；五种生产动作 542 帧（含 `StartStopWalkAction` 中央双侧独立上肢轨迹）、支撑状态转换 44 次、锁脚控制器最大漂移 `0`；证据：`docs/evidence/11/unified_verification/` |
| Task 11 历史专项与 WBC 复验（`added88a7e`） | **WBC `CONTRACT10-01..06` `6/6`、`09-B-4` `27/27`、地面高度 `20/20`、初始化/重置 `6/6`、`legacy_foot_contact` `PASS`** | `tests/test_task10b_wbc_failure_contract.py`、`regression_physics/`、`legacy_foot_contact/`（原 `.blend` SHA-256 不变）；`GROUP E` 历史旧记录继续保留追溯 |
| **Task 11 最终四级 `--fail-fast` 回归（`added88a7e`）** | **`quick` `19/19` (16 PASSED + 3 AUTOMATED_PASS)、`physics` `27/27` (24 PASSED + 3 AUTOMATED_PASS)、`motion` `12/12` (6 PASSED + 6 AUTOMATED_PASS)、`full` `42/42` (33 PASSED + 9 AUTOMATED_PASS)** | 全部 `rc=0`、0 FAIL/SKIPPED/NOT_RUN；`AUTOMATED_PASS` 不登记为人工视觉验收；证据：`docs/evidence/11/unified_verification/regression_*/test_report.json` |

| Task 12 联合专项（`eee276b39d` / `90f4628a0c`） | **WBC A01–A20 `20/20`、Bridge B01–B19 `19/19`、C01–C16+10-C Retirement `17/17`、连续生产链 `PASS`、B20 重开 `2/2 PASS`** | Blender 5.1.1 实测（`docs/evidence/12/final_acceptance/phase1_task12/`）；B19 保留部分 F-Curve 残余风险记录；视觉验收登记为 `OWNER WAIVED` |
| Task 12 历史合同复验 | **WBC `6/6`、10-D T01–T15 `15/15`、Task 11 FootLock `38/38`、09-B `27/27`、地面高度 `20/20`、初始化/重置 `6/6`、历史 Bridge `14/14`** | `docs/evidence/12/final_acceptance/phase2_historical/` 与 `regression_physics/`；10-D 复验 JSON 的 `head` 引用旧固定常量但实际 Worker 运行于当前仓库（原始报告未篡改） |
| **Task 12 最终四级 `--fail-fast` 回归** | **`quick` `19/19` (16P+3AP)、`physics` `27/27` (24P+3AP)、`motion` `12/12` (6P+6AP)、`full` `42/42` (33P+9AP)** | 全部 `rc=0`，`FAILED=SKIPPED=NOT_RUN=0`；`docs/evidence/12/final_acceptance/phase3_regression/`；BUG-01 过程证据保全于 `docs/evidence/12/unified_verification/`（`c9c9a2d`） |

| **Task 7B-1 专项验证（`fcb35bd5`）** | **T01–T12 `12/12 PASS`** (`rc=0`) | Blender 5.1.1 实测（`FAILED=SKIPPED=NOT_RUN=0`），生产源码零修改，证据：`docs/evidence/7b-1/verification/`；未重跑四级回归，待 `7B-4` 统一回归并合入 `master` |
| **Task 7B-2 专项验证（`a92280bb`）** | **T01–T14 `14/14 PASS`** (`rc=0`) | Blender 5.1.1 实测（`14 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`，`BUG-01`、`BUG-02 CLOSED`），证据：`docs/evidence/7b-2/verification/`；待 `7B-4` 统一完成联合验收与四级回归后合入 `master` |
| **Task 7B-3 专项验证（`d9862ada`）** | **T01–T20 两轮累计 20/20 PASS** | Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。第一轮证据提交 `238383869203aaa39218d2695c2592bd80d44a2e`，`docs/evidence/7b-3/verification/`；第二轮证据提交 `d9862ada5c392080a03efb38ea7f2e90201580d2`，`docs/evidence/7b-3/verification_round2/`。 |

证据：`docs/evidence/7b-3/verification/`、`docs/evidence/7b-3/verification_round2/`、`docs/evidence/7b-2/verification/`、`docs/evidence/7b-1/verification/`、`docs/evidence/12/final_acceptance/`、`docs/evidence/12/unified_verification/`、`docs/evidence/11/unified_verification/`、`docs/evidence/10-d/final_acceptance/`、`docs/evidence/10-d/10-d-5/centralized_verification/`、`docs/evidence/10b_sixlayer_split/regression/`、`docs/evidence/10-c-integration/`；保留历史证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`、`docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`。

## 4. 开放问题与责任边界
- `OPEN_FINDINGS.md` 历史统一登记 **16 项**：**16 CLOSED / 0 OPEN**（其余 14 项历史结论与 `FIND-R3-03`/`FIND-R3-04` 关闭状态均保持不变）。
- `CORE_REPAIR_LEDGER.md` 的 **21 条冻结记录**与 `ARCHITECTURE_SYNC.md` 第 10 节 **12 项架构合同 (`CONTRACT-01..12`)** 保持原定义不变。
- Task 10、Task 11、**Task 12 / PKG-5** 均已完成验收并合入 `master`；**`Task 12-D BUG-01` 已关闭（`CLOSED`）**；历史九项人工视觉待办（含 10-D 两份已验收场景）与 Task 12 `OWNER WAIVED` 分别保留。

## 5. Git / 文档边界
- **Task 12 / PKG-5** 冻结生产基线 `eee276b39d204ccd46f4c17f37a09ec483bfcbae`、冻结测试基线 `90f4628a0c4212f4bb0468941cdde362cd68bef2`、最终验收证据提交 `e15d342b805ef45e7d54db2edf1c2804973e81a7` 经由 `task/12` 收归 `master`。
- Task 11（`added88a7e` / `07aec5d8`）、Task 10-D（`824c52ec` / `7f14ff72`）、10-C（`f2501ddc`）、10-B（`c45a40c` / `2f248bf` / `dcf3057`）历史收归记录保持不变。
- **`Task 7B-1`：`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`**（专项测试基线 `776f6de3aa8fd4cad0d4bd163481e12ee09b6382`、`tests/verify_task7b1_environment_targets.py` Blob `c62fa1626c92aa9a81757156af9b8e9e5e0e1ef9`、证据提交 `fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`，尚未合入 `master`）。
- **`Task 7B-2`：`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`**（专项测试基线 `6a7779c574ece598b85ca7cb03b784bcb3c9f35a`、`src/motion/contact_model.py` Blob `267c6c997e0c02cd5f76b2936fc2c975ae50cf07`、`tests/verify_task7b2_hand_target_geometry.py` Blob `b8381a354fc4e7e05e4b3c7013256baafa038aa4`、证据提交 `a92280bbcb2243f0b43edd10b61bbadb39c72869`、`docs/evidence/7b-2/verification/`，`BUG-01、BUG-02 CLOSED`，尚未合入 `master`）。
- `Task 7B-3`：`COMPLETED — OWNER ACCEPTED — PENDING PHASE 7B MERGE`。Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。第一轮证据提交 `238383869203aaa39218d2695c2592bd80d44a2e`，`docs/evidence/7b-3/verification/`；第二轮证据提交 `d9862ada5c392080a03efb38ea7f2e90201580d2`，`docs/evidence/7b-3/verification_round2/`。
- 当前节点：`Task 7B-4`（`FINAL INTEGRATION ACCEPTANCE — OWNER AUTHORIZED`，分支 `task/7b-4`）。仅允许联合专项、相关独立回归、四级回归及证据归档。生产源码、测试脚本和永久规范保持只读。Phase 7B 尚未合入 `master`，须等待独立最终验收及负责人合并批准。`Phase 7C` 保持 `NOT AUTHORIZED`。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
