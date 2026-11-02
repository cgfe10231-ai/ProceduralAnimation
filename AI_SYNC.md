# AI_SYNC：当前工程状态与跨 AI 交接卡片

> **项目**：ProceduralAnimation
>
> **最新已验证工程证据基准**：PKG-5 / Task 10-B-1 交付归档 (`docs/evidence/PKG5_10B1/`)
>
> **当前分支**：`master`
>
> **最近完成节点**：PKG-5 / Task 10-A（10-A-1 至 10-A-4 归档验收）
>
> **当前实现节点**：PKG-5 / Task 10-B / 10-B-1 (Arm IK 输入预验证与零副作用合同)
>
> **当前节点状态**：`10-B-1 IMPLEMENTED — TESTED — ARCHIVED — PENDING INDEPENDENT AUDIT`
>
> **下一执行节点**：PKG-5 / Task 10-B-2 (Arm IK 事务快照、故障注入与完整回滚)
>
> **下一节点状态**：`READY TO IMPLEMENT`

---

## 1. 当前工程状态

PKG-5 / Task 10-A（Arm IK 初始化幂等、控制器生命周期与有效父级变换合同）已通过 10-A-1 至 10-A-4 完整验收归档。

PKG-5 / Task 10-B-1（Arm IK 输入预验证与零副作用保障合同）已完成代码实现、24 项独立测试覆盖、10-A 回归测试、全四级分层回归（Quick 19, Physics 27, Motion 12, Full 42）以及完整测试证据归档。

下一项子任务为 `10-b-2`（事务快照、故障注入与完整回滚），不得提前进入 10-C。

## 2. 10-B-1 已验证交付

### 生产代码

- `src/rig/arm_ik.py`

### 测试代码

- `tests/test_task10b_input_validation.py`
- `tests/test_registry.py`

### 关键实现

1. `_validate_influence()`：严格校验浮点数在 $[0.0, 1.0]$ 区间内，拒绝非有限值（NaN, +Inf, -Inf）、负数、超界数及布尔值。
2. `_validate_side()`：严格校验手臂侧向标识为 `'L'`, `'R'`（及可选 `'BOTH'`），拒绝非字符串或未知侧向。
3. `_validate_vec3()`：严格校验 3 元素实数序列，分量必须有限，拒绝错误维度、字典、字符串与布尔值。
4. `_validate_bool()`：严格校验布尔类型，拒绝整数（0, 1）、字符串等伪布尔值。
5. `setup_arm_ik()`：在获取骨架、集合或创建 Empty/Constraint 之前预先校验 `initial_influence`，非法输入保证场景零突变。
6. `set_hand_ik_target()`：在 Phase A1 依赖图更新、未初始化检测与任何写入前，完成全部用户参数校验；非法输入绝不触发自动初始化，现有场景状态 100% 保持；Phase A3 对派生目标坐标及局部四元数进行严格有限性核验。
7. `set_arm_ik_influence()`：在任何写入前校验参数，并同时对称更新 ArmIK 和 HandRotation 约束权重，保持 L/R 独立性。

### 测试证据

证据目录：

`docs/evidence/PKG5_10B1/`

专项测试：

- 10-B-1 Input Validation (`test_task10b_input_validation.py`)：24/24 PASS (1.997s)。
- 10-A World Transform & Lifecycle (`test_arm_ik_lifecycle_world_transform_contract.py`)：30/30 PASS (4.439s)。
- C2 Final Inspector：6 项验证器自测试通过，文档与符号检查通过。

分层回归：

- Quick：19/19 (48.13s)。
- Physics：27/27 (107.51s)。
- Motion：12/12 (48.45s)。
- Full：42/42 (158.96s)。

四级运行均为退出码 0，FAIL 0，ERROR 0，SKIPPED 0，NOT_RUN 0。

其中 `AUTOMATED_PASS` 必须与普通 PASS 区分；相关视觉检查不得被宣称为已经完成。

## 4. Finding 当前状态

- `FIND-R3-01`：`FIXED / VERIFIED`。
- `FIND-R3-03`：`OPEN`，归属 Task 11 FootLock。
- `FIND-R3-04`：`OPEN`，归属 Task 11 FootLock。

Finding 总数维持 16 项：14 项关闭，2 项未关闭。

09-B-4 没有创建新的 Finding ID，也没有关闭 FIND-R3-03 或 FIND-R3-04。

## 5. PKG-5 后续顺序

1. 09-B：已完成，09-B-4 已验收。
2. 10：Upper-Limb IK/FK，10-A 已完成，10-B-1 已实现并测试，下一具体子任务为 `10-b-2`。
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

下一步只允许启动 `10-b-2`。

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
