# AI_SYNC：当前工程状态与跨 AI 交接卡片

> **项目**：ProceduralAnimation
>
> **最新已验证工程证据基准**：`c634252240b231f1d3ff1e7425ec9761c21ff83f` (`docs/evidence/PKG5_10B1/`)
>
> **当前分支**：`master`
>
> **最近完成节点**：PKG-5 / Task 10-A（10-A-1 至 10-A-4 归档验收）
>
> **当前实现与修复节点**：PKG-5 / Task 10-B / Task 10-B-2 与 Task 10-B-3 (Arm IK 控制器类型识别、预检矩阵一致性与证据归档修复)
>
> **当前节点状态**：`10-B-3 IMPLEMENTED — TESTED — ARCHIVED`（整体 10-B-1 仍保持 `PENDING INDEPENDENT AUDIT`）
>
> **下一执行节点**：等待 10-B 独立审计验收；待批准后准入后续任务
>
> **下一节点状态**：`WAITING INDEPENDENT AUDIT / NOT STARTED`

---

## 1. 当前工程状态

PKG-5 / Task 10-A（Arm IK 初始化幂等、控制器生命周期与有效父级变换合同）已通过 10-A-1 至 10-A-4 完整验收归档。

PKG-5 / Task 10-B-2 修复了 `set_hand_ik_target` 在自动初始化时有效父级变换预检缺失导致的零副作用合同破坏。建立了严格的 Phase A（输入参数预验证）$\to$ Phase B（零突变控制器与环境预检）$\to$ Phase C（自动初始化）$\to$ Phase D（目标计算与提交）执行顺序。

PKG-5 / Task 10-B-3 进一步修复了控制器类型未校验导致错误对象被视作有效、替换非 Empty 时预检矩阵不一致的缺陷：
1. 明确控制器有效性充分必要条件：`obj is not None and obj.type == "EMPTY"`。
2. 针对类型错误对象（Case C），预先计算新 Empty 的预期有效父级矩阵（`root_obj.matrix_world @ Matrix.Identity(4)`），绝不调用即将销毁对象的非共形父级矩阵。
3. 保证返回的 `(needs_auto_init, eff_ik_mat, eff_pole_mat)` 与最终生成的有效控制器物理矩阵完全一致。
4. 扩充 `_capture_scene_snapshot()` 覆盖对象、集合层级与约束所有关键字段，新增 TEST-28 至 TEST-30（专项测试扩充至 30 项测试）。

全套件 30 项专项测试、10-A 回归测试（30/30）、全四级分层回归（Quick 19, Physics 27, Motion 12, Full 42）均已验证通过并归档报告。
整体 10-B-1 保持 `PENDING INDEPENDENT AUDIT`，下一阶段在获得独立审计批准后准入后续任务。

## 2. 10-B-1 / 10-B-2 / 10-B-3 已验证交付

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
6. `set_hand_ik_target()`：在 Phase A 校验失败时绝不触发自动初始化，现有场景状态 100% 保持；Phase A3 对派生目标坐标及局部四元数进行严格有限性核验。
7. `set_arm_ik_influence()`：在任何写入前校验参数，并同时对称更新 ArmIK 和 HandRotation 约束权重，保持 L/R 独立性。
8. `_preflight_arm_ik_parent_transforms()`（10-B-2 & 10-B-3）：在触发自动初始化前，预先校验已存在及待创建控制器的有效父级矩阵（$M_{\text{eff}} = M_{\text{parent}} \cdot I_4$），非法时在零场景写入前直接抛出 `ValueError`，杜绝部分场景污染；正确识别非 Empty 对象并一致化预期矩阵。

### 测试证据

证据目录：

`docs/evidence/PKG5_10B1/`

归档报告：

- [`task10b1_autoinit_preflight_fix_report.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B1/task10b1_autoinit_preflight_fix_report.md)
- [`task10b3_test_execution_report.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/PKG5_10B1/task10b3_test_execution_report.md)

专项测试：

- 10-B-3 Input Validation & Preflight (`test_task10b_input_validation.py`)：30/30 PASS (2.524s)。
- 10-A World Transform & Lifecycle (`test_arm_ik_lifecycle_world_transform_contract.py`)：30/30 PASS (3.971s)。
- C2 Final Inspector：6 项验证器自测试通过，文档与符号检查通过。

分层回归：

- Quick：19/19，退出码 0 (47.37s)。
- Physics：27/27，退出码 0 (102.20s)。
- Motion：12/12，退出码 0 (47.93s)。
- Full：42/42，退出码 0 (154.49s)。

- Quick：19/19 (50.44s)。
- Physics：27/27 (109.13s)。
- Motion：12/12 (48.60s)。
- Full：42/42 (156.51s)。

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
