# 06. 架构迁移方案（Architecture Migration Plan）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`  
> **性质**：受控渐进式重构方案（先接口后实现，严禁一次性重写）  
> **状态**：`PROPOSED — PENDING INDEPENDENT REVIEW`  
> **审计日期**：2026-11-06  

---

## 1. 迁移设计原则

1. **接口不变原则**：所有公开公共 API（签名、返回值、异常语义）保持 100% 绝对一致，外部消费模块（`WholeBodyController`、`PlaygroundCharacterAssembly`、测试用例）零感知。
2. **数学行为零退化原则**：严禁以架构整洁为由修改解算距离、角度、伸展截断、极向放置等任何数学公式。
3. **渐进式隔离与回退保证**：分阶段实施，每个阶段设置独立自动化验证门禁；若任何阶段测试未全量通过，立即回退至上一稳定 SHA。
4. **杜绝循环依赖**：拆分前必须严格评估 Python 模块引用拓扑，保持底层对上层无反向依赖。

---

## 2. 必须保留与不允许改变的组件

### 2.1 必须保留且接口冻结的公共 API
- `setup_arm_ik(armature_obj=None, initial_influence=0.0) -> Dict[str, bpy.types.Object]`
- `set_hand_ik_target(armature_obj, side, world_xyz, hand_rotation_deg=None, pole_world_xyz=None, clamp_reach=True, influence=1.0) -> dict`
- `set_arm_ik_influence(armature_obj=None, side="BOTH", influence=1.0) -> None`
- `reset_arm_ik(armature_obj=None) -> None`
- `get_arm_ik_state(armature_obj, side: str) -> dict`
- `get_pending_arm_rig_cleanup_ids() -> Tuple[str, ...]`
- `retry_pending_arm_rig_cleanup(tx_id: str) -> None`

### 2.2 必须保留的核心常量与几何参数
- `ARM_IK_TARGET_NAMES`, `ARM_POLE_TARGET_NAMES`, `ARM_IK_CONSTRAINT_NAMES`, `HAND_ROT_CONSTRAINT_NAMES`
- 骨骼长度与约束常量：`UPPER_ARM_LENGTH` (0.30), `FOREARM_LENGTH` (0.26), `MAX_ARM_REACH` (0.56), `MIN_ARM_REACH` (0.08)
- 极向放置偏移：`DEFAULT_POLE_BACKWARD_OFFSET` (0.40), `DEFAULT_POLE_OUTWARD_OFFSET` (0.08)

---

## 3. 内部数据结构统一与历史字段迁移清单

当前 `_ArmRigTransactionContext` 存在多轮修订逐步添加的列表字段，建议在统一模型中归一化：

| 历史字段 / 冗余结构 | 当前问题分析 | 拟议统一结构 (PROPOSED) | 兼容迁移映射策略 |
| :--- | :--- | :--- | :--- |
| `created_controller_objects`<br>`created_collections` | 控制器与集合分别使用不同字典格式存储，字段命名不统一（`obj_ref` vs `col_ref`） | `created_resources: Dict[str, List[ResourceRecord]]`<br>按资源类型（`"OBJECT"`, `"COLLECTION"`, `"CONSTRAINT"`）统一记录 | 保留原有属性名作为 property getter，实现对既有代码与测试的 100% 兼容。 |
| `stashed_objects`<br>`stashed_constraints` | 暂存对象包含 `obj_cleaned`, `data_cleaned` 等临时标志，约束暂存则无类似标志 | 统一使用 `StashedResourceRecord`<br>包含 `resource_type`, `original_ref`, `expected_ptr`, `original_name`, `cleanup_state` | 保持 `uncleaned_stashed_*` 列表不变，确保 Phase 3 清理算法无缝对接。 |
| `tx.committed` 属性 | 旧版布尔属性，与 9 状态枚举存在语义重叠 | 明确为只读动态属性：`return self.state in (COMMITTED, CLEANUP_PENDING)` | 彻底保留原有属性，严禁破坏历史外部访问。 |
| 裸写 `reset_arm_ik` | 唯一未经 `_arm_rig_transaction` 保护的写入 API | 在 `reset_arm_ik` 内部接入 `with _arm_rig_transaction(arm):` | 保证无论在复位哪一侧出错，双臂姿态均能原子回滚。 |

---

## 4. 职责物理组织方案分析（单文件重整 vs 独立模块）

经过对调用链与依赖关系的严格审查，提出两种方案评估：

| 评估维度 | 方案 A：单文件分节重整（推荐首选） | 方案 B：拆分为多模块（备选需批准） |
| :--- | :--- | :--- |
| **文件架构** | 保持单一 `src/rig/arm_ik.py`，但内部严格按 6 大职责划分为 6 个显式 Section 注释区。 | 拆分为：<br>1. `src/rig/arm_ik_tx.py` (事务与注册表)<br>2. `src/rig/arm_ik_snapshot.py` (快照与核验)<br>3. `src/rig/arm_ik.py` (公共业务 API) |
| **循环依赖风险** | **零风险**（单模块内部符号顺序排布即可完全杜绝循环依赖）。 | **中等风险**（`arm_ik.py` 业务层需要调用事务层，事务层回滚需要调用资源层与领域重置逻辑）。 |
| **向后兼容性** | **100% 完全兼容**（无需变动任何 `import` 路径或 `__init__.py`）。 | 需要在 `arm_ik.py` 中做大范围符号重新导入（re-export）。 |
| **Git 审计成本** | 变更清晰，只涉及函数位置重排和内部统一，Diff 可追溯。 | 大面积文件新建与删除，导致历史 `git blame` 追踪断裂。 |
| **推荐结论** | **推荐采用方案 A**（先在单文件内完成逻辑解耦与数据结构统一，待 Task 12 联合验收后再评估是否物理拆分）。 | 需用户书面批准并修改 `DECISIONS.md` 后方可实施。 |

---

## 5. 分阶段迁移执行顺序与回退条件

```
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1：结构统一与Section化重排 (原文件内部逻辑归类，对外零影响)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 门禁：TEST-01~102 全部通过
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 2：资源所有权字典归一化 (引入 ResourceRecord 契约，保留旧属性兼容) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 门禁：TEST-93~102 及 Tier Quick 通过
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 3：补齐 reset_arm_ik 事务原子保护 (消除裸写场景残留)               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 门禁：全套回归 (Tier Quick, Physics, Motion, Full) 全部 0 缺陷
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 4：清理无事务历史死代码 (安全移除 unreachable 遗留分支)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 门禁：全套 238 项自动化测试 100% PASS
                                    ▼
                        [迁移完成 — 提交独立审查]
```

### 5.1 阶段详细计划

- **Phase 1：内部职责分区重排**
  - **任务**：不改变任何函数实现，仅调整函数排布顺序，划分为 Coordinator、Registry、Resources、Operations、Snapshot、Commit 六个部分。
  - **回退条件**：出现语法错误或导入错误立即 `git checkout`。
  - **验证测试**：TEST-01 至 TEST-102 (102/102 PASS)。
- **Phase 2：所有权结构兼容归一化**
  - **任务**：在 `_ArmRigTransactionContext` 中统一登记模型，并通过 `@property` 兼容映射旧有 `created_controller_objects` 等属性。
  - **回退条件**：属性访问异常或 TEST-93~102 出现任何失败立即回退。
  - **验证测试**：TEST-93 至 TEST-102 专项验证。
- **Phase 3：`reset_arm_ik` 事务化接入**
  - **任务**：在 `reset_arm_ik` 中添加 `with _arm_rig_transaction(arm):` 保护块。
  - **回退条件**：`reset_arm_ik` 出现递归锁或性能开销超标立即回退。
  - **验证测试**：Task 10-A 30 项回归及 Tier Motion 动作测试。
- **Phase 4：消除冗余非事务死代码**
  - **任务**：清理 `_get_or_create_empty` 中无事务时的直接 remove 分支。
  - **回退条件**：代码审查发现仍有未受事务保护的调用者时立即终止。
  - **验证测试**：全仓分层回归（Quick, Physics, Motion, Full 全部 100% PASS）。
