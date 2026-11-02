# HANDOFF：项目交接说明

> 本文件只记录当前已核实工程状态、任务顺序和重要边界。
>
> 历史测试报告、历史审计快照和旧交接内容不得覆盖当前代码事实。

---

## 1. 当前状态

- 项目：ProceduralAnimation。
- 分支：`master`。
- 最近完成节点：PKG-5 / 09-B-4。
- 验收状态：`ACCEPTED — VERIFIED`。
- 下一节点：PKG-5 / Task 10 — Upper-Limb IK/FK。
- Task 10 状态：`ROUTE FROZEN — IMPLEMENTATION NOT STARTED`。

09-B-4 已经完成生产代码修复、测试扩充、专项测试、分层回归及证据归档。

不得继续将 09-B-4 描述为未完成。

不得创建 09-B-5。

## 2. 09-B-4 交付证据

接受依据：

- 生产修复：`52d66dfd529627a9fbc8bae6ffcf6f4fee6c64d8`
- TEST-24 断言补充：`3881aaadd58f76ffce18faf5d9e880bc49b82f97`
- 测试证据归档：`0b42cb1d7dc685d1be7210bc1280519658f85809`

证据目录：

`docs/evidence/PKG5_09B4/`

专项测试：

| 测试 | 结果 |
|---|---:|
| 09-B World Rotation | 27/27 PASS |
| 09-A Ground Height | 20/20 PASS |
| 08 Worldspace Init/Reset | 6/6 PASS |
| C2 Final Inspector | 6 项自测试 PASS，文档符号检查 PASS |

分层测试：

| Tier | 套件数 | 状态 |
|---|---:|---|
| Quick | 19/19 | 退出码 0 |
| Physics | 25/25 | 退出码 0 |
| Motion | 12/12 | 退出码 0 |
| Full | 40/40 | 退出码 0 |

所有分层测试均为 FAIL 0、SKIPPED 0、NOT_RUN 0。

必须保留 `AUTOMATED_PASS` 与普通 `PASS` 的区别。9 项视觉检查状态不得误写为视觉验收完成。

## 3. 当前 Finding 状态

| Finding | 状态 | 负责节点 |
|---|---|---|
| FIND-R3-01 | FIXED / VERIFIED | 已完成 |
| FIND-R3-03 | OPEN | Task 11 |
| FIND-R3-04 | OPEN | Task 11 |

Finding 总数维持 16 项，14 项关闭，2 项开放。

09-B-4 没有修改 FIND-R3-03、FIND-R3-04 的修复范围。

## 4. 后续任务顺序

| 顺序 | 任务 | 状态 |
|---|---|---|
| 09-B | Lower-Limb World Rotation | `ACCEPTED — VERIFIED` |
| 10 | Upper-Limb IK/FK | `ROUTE FROZEN — IMPLEMENTATION NOT STARTED` |
| 11 | FootLock | `PLANNED — NOT STARTED` |
| 12 | PKG-5 综合接口闭环 | `BLOCKED BY TASK 10 / TASK 11 ACCEPTANCE` |

下一具体子任务：

`10-a-1`

Task 10 / 11 / 12 的权威分工以 `ARCHITECTURE_SYNC.md` Section 4.2—4.5 为准。

问题及审计依据以 `OPEN_FINDINGS.md` Section 10.3 和现有 FIND-R3-03 / FIND-R3-04 记录为准。

## 5. Task 10 路线

Task 10 正式范围：

`Upper-Limb IK/FK — 双臂接口合同、独立控制与轨迹解耦`

| 模块 | 职责 |
|---|---|
| 10-A | Rig 初始化、控制器生命周期、有效父级矩阵与世界空间合同 |
| 10-B | 输入预验证、事务回滚、Influence 与异常安全合同 |
| 10-C | PlannedHandTarget、Bridge、WBC 无损接口、FK/IK 仲裁、ROM 与目标反馈 |
| 10-D | 独立上肢轨迹、TerrainWalk 摆臂解耦、历史动作兼容和视觉验收 |

当前静态审计候选包括：

- Arm IK 初始化可能重置活动控制器状态。
- 世界空间反解没有完整纳入 `matrix_parent_inverse`。
- 输入预验证与完整事务回滚合同尚未建立。
- Influence / WBC 权重边界语义需要统一。
- PlannedHandTarget 缺少 Pole Hint 和 Reach Clamp 完整传递字段。
- TerrainWalk 上肢轨迹仍与下肢步态相位耦合。
- 手部目标语义必须统一为腕部位置和手部骨骼朝向。
- 原生 IK 与 Joint ROM 肘关节边界需要验证。

以上问题必须依据 `OPEN_FINDINGS.md` Section 10.3 逐项核验，不得未经复现直接登记新 Finding。

## 6. Task 11 与 Task 12

### Task 11：FootLock

| 模块 | 职责 |
|---|---|
| 11-A | 锁定元数据、快照失效、Unlock / Reset / Relock 生命周期；负责 FIND-R3-03 |
| 11-B | 只读查询与显式支撑维持副作用分离；负责 FIND-R3-04 |

不得简单清除全部元数据，不得删除现有必要的支撑维持写入。

### Task 12：跨模块联合闭环

| 模块 | 职责 |
|---|---|
| 12-A | WBC 单帧写入与失败原子性 |
| 12-B | Bridge 帧提交与失败传播 |
| 12-C | 跨模块状态所有权和数据合同 |
| 12-D | 系统级连续动作、历史回归和联合验收 |

Task 12 必须等待 Task 10 和 Task 11 独立接受。

Phase 7B 在 Task 10、11、12 全部独立及联合验收通过，并获得负责人明确批准前，始终保持 `NOT AUTHORIZED`。

## 7. Phase 7 准入

Phase 7B 仍为 `NOT AUTHORIZED`。

完成 Task 10、11、12 的独立审查与联合验收，并获得项目负责人明确批准之前，不得进入 Phase 7B。

Phase 7B 为：

`Upper-Limb Independent Motion & End-Effector Target Verification`

Phase 7C 才是 Pipeline A / Pipeline B 的未来合流阶段。

## 8. 权威文件与历史文件

当前状态与架构：

- `PROJECT_STATE.md`
- `ARCHITECTURE_SYNC.md`
- `docs/audit/production_interface/OPEN_FINDINGS.md`

跨会话摘要：

- `AI_SYNC.md`
- `HANDOFF.md`

架构规范：

- `ARCHITECTURE.md`
- `docs/ARCHITECTURE_CHANGE_GATE.md`

历史审计和历史证据：

- 仅作为对应提交、代码版本和审计日期的历史记录。
- 不得把其中的旧行号、旧函数签名、旧任务状态当作当前事实。
- 使用前必须重新核对当前源码和状态权威文件。

`ARCHITECTURE.md` 与 `DECISIONS.md` 继续受保护，不得擅自重写。
