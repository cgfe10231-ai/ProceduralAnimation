# PROJECT_STATE — 当前项目事实与准入状态

> 状态核验日期：2026-11-19
> 核验源码基线：`ace328d9a9af2684cebefe9890e1081b18128c9d`（`audit/task-10-b-9`）。此 SHA 是核验来源，不代表后续文档提交 HEAD。
> 当前任务：`Task 10-B — FINAL ACCEPTANCE PENDING`，未经负责人裁决不得改写为完成。

## 1. 阶段状态
| 节点 | 当前状态 | 准入 |
|---|---|---|
| PKG-5 / 09-A、09-B（含09-B-4） | 历史已验收 | 保持已完成，不重新打开 |
| Task 10-A | `COMPLETED — ARCHIVED` | 已完成 |
| Task 10-B | fix-7 自动化回归完成；最终合同核验、独立结项待裁决 | 当前唯一收尾节点 |
| Task 10-C | `BLOCKED — NOT STARTED` | 禁止提前启动 |
| Task 10-D | `BLOCKED — NOT STARTED` | 禁止提前启动 |
| Task 11 FootLock | 未开始 | 仍有两个历史 Finding |
| Task 12 联合接口闭环 | 未开始 | 待前序验收 |
| Phase 7B | `NOT AUTHORIZED` | 不得越级开启 |

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
- Task 10-B 结项尚需对齐合同实际证据，并取得负责人最终裁决；不得用 FULL 自动通过代替合同专项或人工视觉验收。
- 重构、模块拆分、外层防御壳迁移等后续工程性整理保持冻结，按原负责人的整体 Task 10 路线与独立授权执行。

## 5. Git / 文档边界
- `master` 核验基线：`a2c9b383b71fb2e84bc453cf4cd7926141d61dd9`；尚未合并本轮审计分支。
- 当前事实优先级：真实源码与对应版本测试证据 → 本文件 / `ARCHITECTURE_SYNC.md` / `OPEN_FINDINGS.md` 相互核对 → `AI_SYNC.md`、`HANDOFF.md` 摘要。
- 历史细节由既有 `CHANGELOG.md`、冻结账本及 `docs/evidence/` 保存；本状态文件不复制旧轮次日志与历史过程。
