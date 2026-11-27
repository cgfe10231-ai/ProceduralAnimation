# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-27
> Task 10-D 生产源码基线：`824c52ec73f86aa3d08245a58297118cb4a9f110`（10-d-5 中央验证提交 `7f14ff722caecadec555194cc7d08f454c94c6c8`，收归分支 `task/10-d` 合并至 `master`）；10-C 历史收归基线 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`；10-B 历史主干合并 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`、回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`、证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`。10-B 六层事务实现及其测试源码未被 10-C / 10-D 修改；10-B 历史验收证据仍对应其原冻结基线。
> **当前状态：Task 10-D（及 Task 10 整体）已完成验收并批准合入 `master`；下一工程节点：Task 11-A FootLock（`FIND-R3-03`），Task 12 继续等待 Task 11 完成。**

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A | `COMPLETED — ARCHIVED` | 已完成 |
| Task 10-B | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-20 原负责人正式验收；六层拆分、回归及双父节点主干合并（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）已完成，不再重新打开 |
| Task 10-C | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-26 收归 `master`；10-D 最终回归已在现行 `kinematic_bridge.py` 复验通过（38/38 + 14/14） |
| Task 10-D | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-27 负责人完成两份中央全身运动 `.blend` 人工视觉验收；最终回归通过，合并至 `master` |
| Task 10（整体） | `COMPLETED` | 10-A / 10-B / 10-C / 10-D 全部完成 |
| Task 11 FootLock | `NEXT — TASK 11-A (FIND-R3-03)` | `FIND-R3-03`、`FIND-R3-04` 仍 OPEN；待后续只读审计启动 |
| Task 12 联合接口闭环 | `BLOCKED — WAITING ON TASK 11` | 继续等待 Task 11 完成，禁止提前开启 |
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
| WBC `CONTRACT10-01..06` | **独立专项追踪（不属于 10-B/10-D 验收要求）** | 历史旧记录（01/05 PASS；02/03/04/06 FAIL）保持保留性质不覆盖；本轮拆分后基线独立专项记录见 `docs/evidence/10b_sixlayer_split/regression/group_e_summary.json`，不扩大职责或宣称 Task 12 完成 |

证据：`docs/evidence/10-d/final_acceptance/`、`docs/evidence/10-d/10-d-5/centralized_verification/`、`docs/evidence/10b_sixlayer_split/regression/`、`docs/evidence/10-c-integration/`；保留历史证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`、`docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`。

## 4. 开放问题与责任边界
- `OPEN_FINDINGS.md` 历史统一登记 **16 项**：14 项历史已关闭，2 项 `FIND-R3-03`、`FIND-R3-04` 仍 OPEN，归属 Task 11。不得据 10-B 测试推断其已经关闭。
- `CORE_REPAIR_LEDGER.md` 的 **21 条冻结记录**为 10-B 专项遗留/合同/证据条目，**不是新增21个独立生产代码BUG**，不得混入16项历史 Finding 编号。
- `ARCHITECTURE_SYNC.md` 第10节的 `CONTRACT-01..12` 是批准的架构合同，不能擅自修改定义或重新分配归属。
- Task 10-B 已于 2026-11-20 获项目负责人正式验收，并已完成六层拆分、回归与主干收归（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`），不再重新打开；WBC 全身帧级合同不列为 10-B 结项门槛，FULL 中九项人工视觉检查仍作为独立待办保留。
- Task 10-C 四个子节点于 2026-11-21 完成历史分支验收（`task/10-c-child4`，`d3d7f135975ac5a2a9b01e2706434d0463a563cd`）；2026-11-26 在六层架构集成基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 复验通过，已 fast-forward 收归 `master`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）。 不再重新打开 10-B / 10-C；不得据 10-C 专项结果宣布 10-D、Task 11、Task 12 或 Phase 7B 已完成。

## 5. Git / 文档边界
- Task 10-B 六层事务架构实现、适配测试及回归证据已于 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e` 合入 `master`（回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`，回归证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`）。Task 10-C 四个子节点于 2026-11-21 完成历史分支验收（`task/10-c-child4`，`d3d7f135975ac5a2a9b01e2706434d0463a563cd`）；2026-11-26 在六层架构集成基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 复验通过，已 fast-forward 收归 `master`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）。
- Task 10-D 冻结生产源码基线 `824c52ec73f86aa3d08245a58297118cb4a9f110`、10-d-5 验证提交 `7f14ff722caecadec555194cc7d08f454c94c6c8` 与最终回归/文档同步经由 `task/10-d` 收归 `master`（历史 10-B 合并 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`，10-C 收归 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`）。
- Task 10（`10-A` / `10-B` / `10-C` / `10-D`）已完成；下一任务为 `Task 11-A FootLock`（`FIND-R3-03`、`FIND-R3-04` 仍 OPEN，Task 12 继续等待 Task 11 完成）；禁止擅自开始 Task 11 或 Task 12 代码修改，Phase 7B / Phase 7C 尚未授权。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
