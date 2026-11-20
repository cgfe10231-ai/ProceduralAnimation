# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-20
> 核验源码基线：`9f7ad1af04c4a542df0e73843be49eb5f8c55136`（`task/10-c-child4`，自 `task/10-c-child3` 分出；生产文件 `src/motion/kinematic_bridge.py` Blob：`9bda0a3f82d679a74b3358e9ebfbc92349e52593`）。此 SHA 是本轮进入前基线，不代表后续文档提交 HEAD。
> **当前任务：Task 10-C / 10-c-child4。** 当前仅授权最终接口验证与证据归档，不允许生产代码修改；Task 10-C 整体尚未完成最终验收。

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A | `COMPLETED — ARCHIVED` | 已完成 |
| Task 10-B | `COMPLETED — OWNER ACCEPTED` | 2026-11-20 负责人正式验收；大型实现暂存 `waiting-split`，未合入 `master` |
| Task 10-C | `10-c-child1 COMPLETED — AUDITED；10-c-child2 COMPLETED — OWNER ACCEPTED；10-c-child3 COMPLETED — OWNER ACCEPTED；10-c-child4 CURRENT — VERIFICATION AUTHORIZED` | 当前仅授权 `10-c-child4` 最终接口验证与证据归档，不允许生产代码修改；Task 10-C 整体尚未完成最终验收 |
| Task 10-D | `BLOCKED — NOT STARTED` | 禁止提前启动 |
| Task 11 FootLock | 未开始 | 仍有两个历史 Finding |
| Task 12 联合接口闭环 | 未开始 | 待前序验收 |
| Phase 7B | `NOT AUTHORIZED` | 不得越级开启 |

### Task 10-C 子节点职责摘要
- `10-c-child1`：接口及合同审计，已完成（`COMPLETED — AUDITED`）。
- `10-c-child2`：PlannedHandTarget新增两项字段，已通过 10/10 专项并获负责人验收（`COMPLETED — OWNER ACCEPTED`；证据：`docs/evidence/10-c-child2/`，原始文件未独立记录退出码、不补造）。
- `10-c-child3`：左右手无损转换及FK/IK仲裁与权重校验，已通过 15/15 专项（Blender 5.1.1，退出码 0）并获负责人验收（`COMPLETED — OWNER ACCEPTED`；证据：`docs/evidence/10-c-child3/`）。
- `10-c-child4`：专项测试及最终验收，当前已授权执行最终接口验证与证据归档，不允许生产代码修改（`CURRENT — VERIFICATION AUTHORIZED`；尚未完成）。

## 2. 源码确认事实
- `src/rig/arm_ik.py`：包含事务协调、资源身份/所有权控制、关系恢复、清理挂起、会话准入与双臂复位相关实现。
- `src/motion/whole_body_controller.py`：包含手臂 IK 帧级准入、帧状态捕获/恢复及共享事务协调的实现；**代码存在不等于合同专项已通过**。
- `src/motion/kinematic_bridge.py`：维持规划目标到 WBC 的现有接口；Task 10-C 的完整双手目标传递验收未完成。
- `src/motion/terrain_walk.py`：仍有基于步态相位的正弦摆臂；Task 10-D 的独立上肢轨迹未完成。
- 19 骨骼生产运动学管线与独立 6-DOF 数值动力学管线尚未完成主循环合流，不能宣称已具备真实受力反馈动力学闭环。

## 3. 测试事实（保留统计单位和时间边界）
| 项目 | 有效结果 | 证据性质 |
|---|---|---|
| Arm IK Input Validation | 30/30 PASS | 既有专项记录；不替代本轮复跑 |
| Atomicity TEST-31～253 | **223/223 PASS** | **历史180项 + 修复后本轮43项，跨批次去重联合覆盖，非同一HEAD全量一次跑** |
| BUG11 | **8/8 PASS** | Type A DataBlock 授权与故障窗口专项 |
| BUG12 | **4/4 PASS** | 已构造真实清理资源的跨 Armature 隔离专项；不外推为所有自然端到端路径均已证实 |
| Collection TEST-225～233 | **9/9 PASS** | 已保存专项证据，部分编号与上方 Atomicity 去重重叠 |
| FULL | **42/42 自动化通过** | 33 PASSED + 9 AUTOMATED_PASS；九项仍需要负责人视觉检查 |
| WBC `CONTRACT10-01..06` | **当前HEAD尚无对应完整重跑结论** | 历史01、05 PASS；历史02、03、04、06 FAIL；后续已有针对性代码修改，不能直接继承旧FAIL或推断当前PASS |

证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`；`docs/evidence/fix-7/remaining_regression/round2/full/test_report.json`。

## 4. 开放问题与责任边界
- `OPEN_FINDINGS.md` 历史统一登记 **16 项**：14 项历史已关闭，2 项 `FIND-R3-03`、`FIND-R3-04` 仍 OPEN，归属 Task 11。不得据 10-B 测试推断其已经关闭。
- `CORE_REPAIR_LEDGER.md` 的 **21 条冻结记录**为 10-B 专项遗留/合同/证据条目，**不是新增21个独立生产代码BUG**，不得混入16项历史 Finding 编号。
- `ARCHITECTURE_SYNC.md` 第10节的 `CONTRACT-01..12` 是批准的架构合同，不能擅自修改定义或重新分配归属。
- Task 10-B 已于 2026-11-20 由项目负责人正式验收（`COMPLETED — OWNER ACCEPTED`）；WBC 全身帧级合同不重新算作 10-B 未完成任务，FULL 中九项人工视觉检查仍作为独立待办保留，不因 10-B 结项自动宣称视觉通过。
- 重构、模块拆分、外层防御壳迁移等后续工程性整理保持冻结，10-B 大型实现暂存 `waiting-split` 等待后续独立拆分，不带入 10-C。

## 5. Git / 文档边界
- Task 10-B已由项目负责人正式验收。大型事务实现及其依赖测试保留于waiting-split；目前未合入master。10-C已完成`10-c-child1`独立源码审计、`10-c-child2`（10/10 PASS）与`10-c-child3`（15/15 PASS，Blender 5.1.1，退出码0）并均获负责人验收，当前进入`10-c-child4`仅授权最终接口验证与证据归档，不允许生产代码修改；Task 10-C整体尚未完成最终验收。
- `master` 核验基线：`a2c9b383b71fb2e84bc453cf4cd7926141d61dd9`；尚未合并本轮审计分支或 `waiting-split`。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
