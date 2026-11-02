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
- Task 10 状态：`READY FOR TASK CARD — NOT STARTED`。

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
| 09-B | Lower-Limb World Rotation | 已完成，09-B-4 已验收 |
| 10 | Upper-Limb IK/FK | 下一任务，等待正式任务卡 |
| 11 | FootLock | 待修复 |
| 12 | PKG-5 综合接口闭环 | 待执行 |

Task 10 不得在没有正式任务卡的情况下启动。

## 5. Task 10 方向

Task 10 的范围是：

`Upper-Limb IK/FK — 双臂接口合同与独立轨迹控制`

必须复用现有 `src/rig/arm_ik.py` 与 WBC。

重点包括：

- 双臂独立三维目标。
- 手部末端世界空间目标与姿态。
- FK 摆臂与独立 IK 目标的职责边界。
- 手肘 pole、手腕旋转、可达性、ROM。
- 有效父级矩阵与世界空间合同。
- 非有限输入与失败原子性。
- 不得重复创建第二套 IK/FK、WBC 或控制器。

以上仅是 Task 10 的规划范围，不构成生产代码修改授权。

## 6. Task 11 与 Task 12

Task 11 必须处理：

- FIND-R3-03：锁定元数据生命周期与重置残留。
- FIND-R3-04：状态查询与支撑维持函数之间的写入副作用边界。

Task 12 必须执行跨模块联合审计与回归，不得仅将专项测试数量相加作为验收。

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
