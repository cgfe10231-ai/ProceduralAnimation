# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-26
> 主干合并基线：`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`（`master`；六层拆分后回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`，回归证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`）。主干生产及测试源码与拆分后验收版本完全一致。
> **当前任务：Task 10-B 主干收归后文档结项（纯 Markdown 状态同步）；下一工程节点：Task 10-C 受控集成及重新验证（须遵守独立准入规则）。**

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A | `COMPLETED — ARCHIVED` | 已完成 |
| Task 10-B | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER` | 2026-11-20 原负责人正式验收；六层拆分、回归及双父节点主干合并（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）已完成，不再重新打开 |
| Task 10-C | 四个子节点（`10-c-child1..4`）于 2026-11-21 完成历史分支验收 | 保留于 `task/10-c-child4`（HEAD：`d3d7f135975ac5a2a9b01e2706434d0463a563cd`），尚未合入 `master`，尚未在六层架构集成后重新验证；不得将历史验收描述为当前主干验收 |
| Task 10-D | `BLOCKED — NOT STARTED` | 禁止提前启动 |
| Task 11 FootLock | 未开始 | 仍有两个历史 Finding |
| Task 12 联合接口闭环 | 未开始 | 待前序验收 |
| Phase 7B | `NOT AUTHORIZED` | 不得越级开启 |

### Task 10-C 子节点职责摘要
- `10-c-child1`：接口及合同审计，已完成。
- `10-c-child2`：PlannedHandTarget新增两项字段。
- `10-c-child3`：左右手无损转换及FK/IK仲裁。
- `10-c-child4`：专项测试及最终验收。

## 2. 源码确认事实
- `src/rig/arm_ik.py` 与 `src/scene_transaction_integrity/`：前者保留五个公开领域接口及领域配置常量；后者按六层物理架构承载事务协调、注册表与身份控制、受权资源/关系操作、上肢 IK 业务操作、快照/指纹/回滚核验及提交后清理（共 81 个 Python 文件，含包初始化文件），由 `wiring._create_arm_rig_transaction_context()` 装配 15 项显式依赖。
- `src/motion/whole_body_controller.py`：包含手臂 IK 帧级准入、帧状态捕获/恢复及共享事务协调的实现；**代码存在不等于合同专项已通过**。
- `src/motion/kinematic_bridge.py`：主干维持原有规划目标到 WBC 的接口实现；Task 10-C 四个子节点历史分支实现保留于 `task/10-c-child4`（`d3d7f135975ac5a2a9b01e2706434d0463a563cd`），尚未合入 `master` 且未在六层架构集成后重新验证。
- `src/motion/terrain_walk.py`：仍有基于步态相位的正弦摆臂；Task 10-D 的独立上肢轨迹未完成。
- 19 骨骼生产运动学管线与独立 6-DOF 数值动力学管线尚未完成主循环合流，不能宣称已具备真实受力反馈动力学闭环。

## 3. 测试事实（保留统计单位和时间边界）
| 项目 | 有效结果 | 证据性质 |
|---|---|---|
| Input Validation | **30/30 PASS** | 拆分后基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32` 实测，包含于 FULL（不另行重复计数） |
| Atomicity TEST-31～253 | **223/223 PASS** | 拆分后同一冻结源码基线 `2f248bf` 单轮完整执行；Collection TEST-225～233 包含于 Atomicity，不重复计数 |
| BUG11 | **8/8 PASS** | 拆分后基线 `2f248bf` Type A DataBlock 授权与故障窗口专项实测 |
| BUG12 | **4/4 PASS** | 拆分后基线 `2f248bf` 跨 Armature 隔离专项实测；不外推至所有自然端到端路径 |
| FULL | **42/42 自动化通过** | 33 PASSED + 9 AUTOMATED_PASS；九项人工视觉验收仍为独立待办 |
| WBC `CONTRACT10-01..06` | **独立专项追踪（不属于 10-B 验收要求）** | 历史旧记录（01/05 PASS；02/03/04/06 FAIL）保持保留性质不覆盖；本轮拆分后基线独立专项记录见 `docs/evidence/10b_sixlayer_split/regression/group_e_summary.json`，不扩大职责或宣称 Task 12 完成 |

证据：`docs/evidence/10b_sixlayer_split/regression/`（`regression_manifest.json`、`group_a_summary.json`、`group_b_summary.json`、`group_c_summary.json`、`test_report.json`、`frozen_blob_check.json`、`group_e_summary.json`）；保留历史证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`、`docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`。

## 4. 开放问题与责任边界
- `OPEN_FINDINGS.md` 历史统一登记 **16 项**：14 项历史已关闭，2 项 `FIND-R3-03`、`FIND-R3-04` 仍 OPEN，归属 Task 11。不得据 10-B 测试推断其已经关闭。
- `CORE_REPAIR_LEDGER.md` 的 **21 条冻结记录**为 10-B 专项遗留/合同/证据条目，**不是新增21个独立生产代码BUG**，不得混入16项历史 Finding 编号。
- `ARCHITECTURE_SYNC.md` 第10节的 `CONTRACT-01..12` 是批准的架构合同，不能擅自修改定义或重新分配归属。
- Task 10-B 已于 2026-11-20 获项目负责人正式验收，并已完成六层拆分、回归与主干收归（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`），不再重新打开；WBC 全身帧级合同不列为 10-B 结项门槛，FULL 中九项人工视觉检查仍作为独立待办保留。
- 重构、模块拆分与回归结项已经完成并合入 `master`；10-B 相关工程整理不再重新打开，10-C 历史分支仍未合入 `master`，须经受控集成与独立复验。

## 5. Git / 文档边界
- Task 10-B 六层事务架构实现、适配测试及回归证据已于 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e` 合入 `master`（回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`，证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`）。10-C 四个子节点于 2026-11-21 完成历史验收，保留于 `task/10-c-child4`（HEAD `d3d7f135975ac5a2a9b01e2706434d0463a563cd`），尚未合入 `master`，亦未在六层架构集成后重新验证。
- `master` 主干合并后最新源码基线：`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`；下一工程节点为 10-C 受控集成与重新验证（须遵守独立准入规则）。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
