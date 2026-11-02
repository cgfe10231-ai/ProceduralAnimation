# AI_SYNC：当前工程状态与跨 AI 交接卡片

> **项目**：ProceduralAnimation
>
> **最新已验证工程证据基准**：`0b42cb1d7dc685d1be7210bc1280519658f85809`
>
> **当前分支**：`master`
>
> **最近完成节点**：PKG-5 / 09-B / 09-B-4
>
> **最近完成节点状态**：`ACCEPTED — VERIFIED`
>
> **下一执行节点**：PKG-5 / Task 10 — Upper-Limb IK/FK
>
> **下一节点状态**：`ROUTE FROZEN — IMPLEMENTATION NOT STARTED`

---

## 1. 当前工程状态

PKG-5 / 09-B 下肢 IK 世界旋转、有效父级变换域、控制器完整状态恢复与解锁事务原子性补强已经完成。

09-B-4 的生产修复、测试断言补充、独立专项测试和分层回归均已完成。

不得继续把当前 09-B 描述为未修复或等待验收。

下一项工作是 Task 10，不得创建 09-B-5。

## 2. 09-B-4 已验证交付

### 生产代码

- `src/rig/ik.py`
- `src/rig/foot_contact.py`

### 测试代码

- `tests/test_leg_ik_world_rotation_contract.py`

### 关键实现

1. `_snapshot_leg_rig_state()` 捕获 4 个腿部控制器与 6 根下肢骨骼状态。
2. 控制器快照覆盖 15 个字段。
3. 骨骼快照覆盖 8 个字段。
4. `_rollback_leg_rig_state()` 恢复并逐项核验快照状态。
5. `unlock_foot_contact()` 的 Phase B 修改过程具备事务回滚。
6. FootIK 与 KneePole 的剪切矩阵分别进行拒绝测试。
7. 解锁阶段发生异常时，恢复控制器、骨骼、锁定状态与元数据。

### 有效父级变换数学支持域

有效父级矩阵：

`M_eff = M_parent @ matrix_parent_inverse`

当前生产实现：

- 非有限矩阵元素：拒绝。
- 非仿射矩阵：拒绝，最后一行容差 `1e-6`。
- `det(A) < 0`：拒绝镜像反射。
- `det(A) == 0`：拒绝奇异矩阵。
- `s_sq <= 1e-12`：拒绝退化尺度。
- Gram 矩阵相对偏差 `> 1e-6`：拒绝非共形变换。
- 支持纯旋转与正均匀缩放和旋转的组合。

不得把行列式条件写成 `det <= 1e-7`。
不得把 Gram 矩阵容差写成 `1e-4`。

### 测试范围

`tests/test_leg_ik_world_rotation_contract.py` 包含 TEST-01 至 TEST-27。

重点覆盖：

- TEST-17：完整状态事务回滚。
- TEST-22：FootIK 解锁剪切拒绝。
- TEST-23：KneePole 独立解锁剪切拒绝。
- TEST-24：解锁提交后故障注入、完整回滚及七项锁定元数据逐项相等性。
- TEST-25：NaN / Inf 矩阵拒绝。
- TEST-26：非仿射矩阵拒绝。
- TEST-27：正行列式退化尺度拒绝。

## 3. 09-B-4 测试证据

证据目录：

`docs/evidence/PKG5_09B4/`

专项测试：

- World Rotation：27/27 PASS。
- Ground Height：20/20 PASS。
- Worldspace Init/Reset：6/6 PASS。
- C2 Final Inspector：6 项验证器自测试通过，文档与符号检查通过。

分层回归：

- Quick：19/19。
- Physics：25/25。
- Motion：12/12。
- Full：40/40。

四级运行均为退出码 0，FAIL 0，SKIPPED 0，NOT_RUN 0。

其中 `AUTOMATED_PASS` 必须与普通 PASS 区分；相关视觉检查不得被宣称为已经完成。

## 4. Finding 当前状态

- `FIND-R3-01`：`FIXED / VERIFIED`。
- `FIND-R3-03`：`OPEN`，归属 Task 11 FootLock。
- `FIND-R3-04`：`OPEN`，归属 Task 11 FootLock。

Finding 总数维持 16 项：14 项关闭，2 项未关闭。

09-B-4 没有创建新的 Finding ID，也没有关闭 FIND-R3-03 或 FIND-R3-04。

## 5. PKG-5 后续顺序

1. 09-B：已完成，09-B-4 已验收。
2. 10：Upper-Limb IK/FK，架构路线已冻结，下一具体子任务为 `10-a-1`。
3. 11：FootLock，处理 FIND-R3-03 / FIND-R3-04。
4. 12：PKG-5 跨模块接口闭环与联合验收。

Task 10 模块：
- 10-A：Rig 初始化、生命周期与世界空间矩阵。
- 10-B：输入验证、事务回滚与 Influence 合同。
- 10-C：Bridge / WBC 手部目标无损接口、FK/IK 仲裁与 ROM。
- 10-D：独立上肢轨迹、TerrainWalk 摆臂解耦、历史动作兼容。

Task 11 模块：
- 11-A：锁定元数据生命周期。
- 11-B：只读查询与支撑维持副作用分离。

Task 12 模块：
- 12-A：WBC 单帧合同。
- 12-B：Bridge 帧提交合同。
- 12-C：跨模块状态所有权。
- 12-D：系统级连续动作与联合回归。

技术细节与问题清单：
- `ARCHITECTURE_SYNC.md` Section 4.2—4.5
- `docs/audit/production_interface/OPEN_FINDINGS.md` Section 10.3

下一步只允许启动 `10-a-1`。

Phase 7B 继续保持 `NOT AUTHORIZED`。

## 6. Phase 7 准入

Phase 7B 当前仍为：

`NOT AUTHORIZED`

必须先完成 Task 10、Task 11、Task 12 的独立验收及联合验收，并取得项目负责人明确批准。

Phase 7B：

`Upper-Limb Independent Motion & End-Effector Target Verification`

Phase 7C：

`Pipeline A / Pipeline B Confluence`

不得混淆两者。

## 7. 文档和架构边界

当前状态权威文件：

- `PROJECT_STATE.md`
- `ARCHITECTURE_SYNC.md`
- `docs/audit/production_interface/OPEN_FINDINGS.md`

交接摘要：

- `HANDOFF.md`
- `AI_SYNC.md`

架构规范：

- `ARCHITECTURE.md`
- `docs/ARCHITECTURE_CHANGE_GATE.md`

历史决策：

- `DECISIONS.md`

历史审计报告、旧路线图、历史测试证据均不得覆盖当前源码和当前状态文件。

`ARCHITECTURE.md` 与 `DECISIONS.md` 保持保护状态。

本卡片只表示当前已核验的工程事实。每次新任务启动时，仍须重新检查真实 Git HEAD 与工作区。
