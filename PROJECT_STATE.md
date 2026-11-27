# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-27
> Task 11 已验收生产源码基线：`added88a7e27eaaa6d1644473d560c5dcf45bc80`，联合验证与证据提交 `07aec5d8d35e5d77ff956f160840d1c2491b770e`（收归分支 `task/11` 合并至 `master`）；Task 10-D 历史生产源码基线 `824c52ec73f86aa3d08245a58297118cb4a9f110`（10-d-5 中央验证 `7f14ff722caecadec555194cc7d08f454c94c6c8`，收归 `task/10-d`）；10-C 历史收归基线 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`；10-B 历史主干合并 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`、回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`、证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`。10-B 六层事务实现及其测试源码未被 10-C / 10-D / 11 修改。
> **当前状态：Task 11（`11-A` + `11-B`）FootLock 已通过独立源码审计与联合动态验收并合入 `master`，`FIND-R3-03` 与 `FIND-R3-04` 正式关闭（原 16 项历史 Finding 已全部关闭）；下一工程节点：Task 12-A。PKG-5 尚未整体完成，Phase 7B / Phase 7C 尚未授权。**

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A | `COMPLETED — ARCHIVED` | 已完成 |
| Task 10-B | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-20 原负责人正式验收；六层拆分、回归及双父节点主干合并（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）已完成，不再重新打开 |
| Task 10-C | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-26 收归 `master`；10-D 最终回归已在现行 `kinematic_bridge.py` 复验通过（38/38 + 14/14） |
| Task 10-D | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-27 负责人完成两份中央全身运动 `.blend` 人工视觉验收；最终回归通过，合并至 `master` |
| Task 10（整体） | `COMPLETED` | 10-A / 10-B / 10-C / 10-D 全部完成 |
| **Task 11-A FootLock (`FIND-R3-03`)** | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`** | 7 项锁定元数据生命周期、`IDPropertyArray` 脱离快照/回滚/校验闭环完成并合入 `master` |
| **Task 11-B FootLock (`FIND-R3-04`)** | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`** | `get_foot_support_state()` 零副作用纯查询与 `evaluate_foot_support()` 主动支撑维持分离完成（含 BUG-01 修复）并合入 `master` |
| **Task 11（整体）** | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`** | 11-A + 11-B 均通过独立源码审计与联合验收，`FIND-R3-03`、`FIND-R3-04` 正式关闭 |
| Task 12 联合接口闭环 | `NEXT — TASK 12-A (AUDIT READY)` | 下一工程节点；待 ChatGPT 独立审计启动，禁止自行开始编码；PKG-5 尚未整体完成 |
| Phase 7B / Phase 7C | `NOT AUTHORIZED` | 不得越级开启或宣称 7C 动力学合流已完成 |

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
- `src/motion/whole_body_controller.py`：包含手臂 IK 帧级准入、帧状态捕获/恢复及共享事务协调的实现；**代码存在不等于合同专项已通过**。
- `src/motion/kinematic_bridge.py`：PlannedHandTarget 末尾追加 `pole_hint_world_xyz=None` 与 `clamp_reach=True`，保留历史构造兼容；`convert_planned_pose_to_wbc_targets()` 对左右手独立传递字段、仲裁 FK/IK，接触意图独立。`KinematicBridgeExecutor.execute_frame()` 在启用 ROM 截断且 WBC 报告 ROM 违反时通过 `_reconcile_post_rom_feedback()` 重算四末端反馈；Phase 6 保留控制器旋转模式插入关键帧并写入 `ArmIK` / `HandRotation` 约束 `influence`（`CONSTANT` 插值）。
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

证据：`docs/evidence/11/unified_verification/`、`docs/evidence/10-d/final_acceptance/`、`docs/evidence/10-d/10-d-5/centralized_verification/`、`docs/evidence/10b_sixlayer_split/regression/`、`docs/evidence/10-c-integration/`；保留历史证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`、`docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`。

## 4. 开放问题与责任边界
- `OPEN_FINDINGS.md` 历史统一登记 **16 项**：随 Task 11（`11-A` + `11-B`）完成验收，`FIND-R3-03`、`FIND-R3-04` 正式关闭，**原 16 项历史 Finding 已全部关闭（16 闭 0 开）**；其余 14 项历史结论保持不变。
- `CORE_REPAIR_LEDGER.md` 的 **21 条冻结记录**与 `ARCHITECTURE_SYNC.md` 第 10 节 **12 项架构合同 (`CONTRACT-01..12`)** 定义不变，不混入 16 项历史 Finding 编号。
- Task 10（`10-A` / `10-B` / `10-C` / `10-D`）与 Task 11（`11-A` + `11-B`）均已完成验收并合入 `master`，不再重新打开；FULL 中九项历史人工视觉检查待办独立保留。

## 5. Git / 文档边界
- Task 11 已验收生产源码基线 `added88a7e27eaaa6d1644473d560c5dcf45bc80` 及联合测试证据 `07aec5d8d35e5d77ff956f160840d1c2491b770e` 经由 `task/11` 收归 `master`。
- Task 10-D（`824c52ec` / `7f14ff72`）、10-C（`f2501ddc`）、10-B（`c45a40c` / `2f248bf` / `dcf3057`）历史收归记录保持不变。
- Task 11 已完成，`FIND-R3-03`、`FIND-R3-04` 已正式关闭；**下一节点为 `Task 12-A`**（待 ChatGPT 独立审计启动），Task 12 未完成前不得宣称 PKG-5 已整体完成，禁止擅自开始 Task 12 编码，Phase 7B / Phase 7C 保持 `NOT AUTHORIZED`。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
