# 05. 架构驱动影响矩阵（Architecture-Driven Impact Matrix）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`、`src/motion/whole_body_controller.py`、`src/scene/playground_character_assembly.py`  
> **性质**：基于真实调用链与状态依赖的架构驱动双向影响模型  
> **审计日期**：2026-11-06  

---

## 1. 实际系统依赖图（Actual System Dependency Graph）

通过对全工程进行符号分析，确定真实的调用与数据流拓扑关系：

```
[PlannedHandTarget] (motion/framework.py)
        │ (直接依赖 / 单向输入合同)
        ▼
[KinematicBridge] (motion/kinematic_bridge.py)
        │ (直接依赖 / 单向参数打包)
        ▼
[WholeBodyController] (motion/whole_body_controller.py)
   ├── setup_arm_ik ────────────────────┐
   ├── set_hand_ik_target ──────────────┤ (直接调用依赖 / 双向合同)
   ├── set_arm_ik_influence ────────────┤
   ├── get_arm_ik_state ────────────────┤
   └── reset_arm_ik ────────────────────┤
                                        ▼
                             [Arm IK Public API Layer]
                                        │ (直接依赖 / 单向控制)
                                        ▼
                       [Transaction Coordinator Boundary]
                          │                           │
                          │ (生命周期依赖)             │ (共享状态依赖)
                          ▼                           ▼
            [Snapshot & Verification Engine]    [_PENDING_ARM_RIG_CLEANUPS]
                          │                           ▲
                          │ (直接依赖)                 │ (错误流转)
                          ▼                           │
               [Blender Scene Resources] ─────────────┘
             (Objects, Constraints, Collections)
```

---

## 2. 依赖类型定义规则

1. **直接依赖（Direct Dependency）**：显式函数调用、参数传递或返回值消费。
2. **间接依赖（Indirect Dependency）**：通过中间层级连传递的数据或控制流（例如 Bridge $\to$ WBC $\to$ Arm IK）。
3. **共享状态依赖（Shared-State Dependency）**：多个模块同时读写 Blender C 场景中的同一底层实体（如 `CharacterArmature`、`CharacterRoot`、`Character` 集合）。
4. **生命周期依赖（Lifecycle Dependency）**：前置操作的终态决定后置操作的准入性（如 `_assert_arm_rig_cleanup_gate` 阻塞后续业务事务）。
5. **无依赖（No Dependency）**：物理存在于同工程但运行时无交叉的数据或控制流（如 Arm IK 与 Leg IK 的约束链各自独立）。

---

## 3. 架构驱动影响矩阵（逐项审计表）

| Source (源节点) | Target (目标节点) | Dependency (真实依赖) | Direction (方向) | Contract (必须保持的不变量) | Failure Propagation (失败传播) | Rollback Responsibility (恢复责任方) | Verification (对应测试) | Evidence (源码位置与证据) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `set_hand_ik_target` | `_preflight_arm_ik_parent_transforms` | 直接依赖 | 单向 (Caller $\to$ Callee) | 场景写入前必须完成有效父级共形变换预检，Phase A/B 绝对零副作用 | Preflight 抛出 `RuntimeError`，阻止进入事务，上层收到明确异常 | 自然零副作用（无需回滚） | TEST-13 至 TEST-24, TEST-30 | `arm_ik.py:2303-2305`<br>`test_task10b_input_validation.py` |
| `set_hand_ik_target` | `setup_arm_ik` | 直接依赖 / 嵌套事务 | 双向 | 控制器或约束缺失时自动初始化，共享外层事务上下文，不得产生二次快照冲突 | `setup_arm_ik` 内部失败由外层事务捕获并执行完整回滚 | 外层 `_arm_rig_transaction` 统一负责 | TEST-25, TEST-36, TEST-98 | `arm_ik.py:2376-2378`<br>`test_task10b_transaction_atomicity.py` |
| `setup_arm_ik` | `_get_or_create_empty` | 直接依赖 | 单向 (Caller $\to$ Callee) | 控制器创建后必须立即向事务登记所有权，且链接至 Character 集合，维持 conformal TRS | 创建或链接失败抛出异常，触发自建控制器物理删除 | `_rollback_arm_rig_state` (按指针清理) | TEST-93, TEST-94, TEST-98 | `arm_ik.py:1833-1850, 1750-1755`<br>`test_task10b_transaction_atomicity.py` |
| `_get_or_create_empty` | `_ArmRigTransactionContext` | 直接依赖 / 注册 | 单向 (Callee $\to$ Registry) | 事务 `created_controller_objects` 必须精确记录对象指针，严禁重复登记 | 登记异常阻断 Empty 创建流程，向外抛出 | 事务协调器捕获触发清理 | TEST-93, TEST-101 | `arm_ik.py:1283-1301, 1753`<br>`test_task10b_transaction_atomicity.py` |
| `setup_arm_ik` | `p_fore.constraints` / `p_hand.constraints` | 直接依赖 / 突变 | 双向 | 原有约束 Influence 与配置幂等保留；冲突类型约束暂存隔离；初始 Influence $\in [0, 1]$ | 约束新建或配置失败触发回滚，删除新建约束并恢复暂存约束 | `_rollback_arm_rig_state` (核对 `saved_con_refs`) | TEST-38, TEST-83, TEST-100 | `arm_ik.py:1887-2000, 584-600`<br>`test_task10b_transaction_atomicity.py` |
| `_arm_rig_transaction` | `_snapshot_arm_rig_state` | 直接依赖 / 捕获 | 单向 (Caller $\to$ Engine) | 捕获不可变深拷贝（含 TRS、Euler/Quat、约束及集合全拓扑），绝对只读零修改 | 快照属性读取失败直接转入 `FAILED`，绝不回滚 | 无需回滚（场景未受写污染） | TEST-65, TEST-66 | `arm_ik.py:1629, 244-409`<br>`test_task10b_transaction_atomicity.py` |
| `_arm_rig_transaction` | `_verify_arm_rig_state_restored` | 直接依赖 / 核验 | 单向 (Caller $\to$ Engine) | 回滚后必须逐字段核验（容差 $10^{-5}$，指针严格匹配），不符则一票否决 | 比对有任何差异抛出 `RuntimeError`，事务标记为 `FAILED` | 记录复合异常，宣告不可逆恢复失败 | TEST-53 至 TEST-64, TEST-77, TEST-78 | `arm_ik.py:1658, 858-1257`<br>`test_task10b_transaction_atomicity.py` |
| `_arm_rig_transaction` (Phase 3) | `_PENDING_ARM_RIG_CLEANUPS` | 生命周期依赖 / 错误流转 | 双向 | 提交后清理失败必须登记到全局注册表，阻断该 Armature 后续新写入；重试成功后注销 | 清理失败抛出提交后异常，不影响已提交业务数据 | 由 `retry_pending_arm_rig_cleanup` 负责后续清理 | TEST-79, TEST-80, TEST-85, TEST-86 | `arm_ik.py:1696-1704, 1516-1603`<br>`test_task10b_transaction_atomicity.py` |
| `_assert_arm_rig_cleanup_gate` | `_arm_rig_transaction` | 生命周期依赖 / 门禁 | 单向 (Gate $\to$ Transaction) | 同一 Armature 存在未决 `CLEANUP_PENDING` 时绝对拒绝新事务开启 | 抛出 `RuntimeError`，新事务根本无法进入初始化阶段 | 无需回滚（写入被完全阻断） | TEST-85, TEST-86 | `arm_ik.py:1571-1603, 1622`<br>`test_task10b_transaction_atomicity.py` |
| `WholeBodyController` | `arm_ik.py` (公开 API) | 间接依赖 / 跨层消费 | 双向合同 | WBC 单帧姿态求解依赖 Arm IK 提供准确的末端到达反馈与零副作用回滚保证 | Arm IK 异常向 WBC 抛出，WBC 判定单帧求解失败 | Arm IK 内部保证场景干净，WBC 负责向上游报告帧失败 | WBC 单元回归 / Tier Motion / Full | `whole_body_controller.py:303, 424, 434, 524, 657`<br>`06_tier_motion.log` |
| `reset_arm_ik` | `CharacterArmature` / `Controls` | 共享状态依赖 (无事务) | 单向写入 | 将双臂约束 Influence 归 0，控制器恢复 neutral rest；按有效父级矩阵变换 | 发生异常场景直接停留在部分 reset 状态（**架构发现：当前缺陷**） | **当前无恢复责任方**（缺少事务保护） | TEST-06 (10-A), PROTOTYPE | `arm_ik.py:2044-2104` |
| 外部非 Empty 命名占用 | `_rollback_arm_rig_state` | 外部命名冲突 (Unprovable) | 单向保护 | 外部同名对象指针不符时，绝不误删外部对象，保护其成员与属性 | 记录恢复错误并中止覆盖，向外报告现场被占用 | 报错保护现场，拒绝盲目覆盖 | TEST-102 | `arm_ik.py:501-510`<br>`test_task10b_transaction_atomicity.py` |

---

## 4. 关键架构发现与隐患审计

1. **`reset_arm_ik` 缺乏事务保护**：
   - 依赖分析表明，`setup_arm_ik`、`set_hand_ik_target` 与 `set_arm_ik_influence` 均已接入 `_arm_rig_transaction` 保护，但 `reset_arm_ik()` 仍是裸写执行。若在重置左臂后、重置右臂前发生异常，场景将留下半重置状态。
2. **非事务分支的历史遗留代码**：
   - `_get_or_create_empty`（L1745）与 `setup_arm_ik`（L1911, 1930, 1971, 1990）中存在 `else: bpy.data.objects.remove(obj)` / `p_fore.constraints.remove(con)` 等无事务分支。在当前全系统均受事务保护的前提下，这些分支永远不会被执行，属于冗余死代码。
3. **DataBlock 级联垃圾回收边界**：
   - 依赖矩阵清晰证明，DataBlock 清理必须受 `user_count == 0` 严格保护；若外部材质或对象共享该数据块，则禁止删除。这一不变量在 TEST-74 中已通过核验。
