# TASK 10-B-14 · Production Contract Final Audit Matrix (CONTRACT-01 ～ CONTRACT-12)

> **基线 Commit**：`792262e8e7dc7e19c10444d4ff407cb2a87ad8aa`  
> **审计分支**：`audit/task-10-b-9`  
> **审计时间**：2026-11-08  
> **审计范围**：
> - `src/rig/arm_ik.py`
> - `tests/test_task10b_transaction_atomicity.py`
> - `tests/test_task10b_input_validation.py`
> - `tests/test_arm_ik_lifecycle_world_transform_contract.py`
> - `ARCHITECTURE_SYNC.md` 第 10 节（已批准目标架构）
> - `docs/ARCHITECTURE_CHANGE_GATE.md`  
> **纪律准则**：仅核对真实代码与测试，严禁主观推断，严禁引用不存在的符号，不得将已有的局部成功测试解释为整项合同完全通过。

---

## 1. 合同状态总览与汇总统计

### 1.1 合同状态汇总统计

- **VERIFIED**：5
- **DEFECT**：6
- **UNVERIFIED**：1

### 1.2 十二项合同最终审计状态表

| Contract | Status | Reason | 责任层级 | 生产源码定位 | 关联测试集 |
|---|---|---|---|---|---|
| **CONTRACT-01** | **VERIFIED** | 输入与空间预检、零写入拒绝已有源码和专项测试 | Layer 4 | `src/rig/arm_ik.py`: L77–L127, L5137–L5264 | `test_task10b_input_validation.py` (TEST-01～30) |
| **CONTRACT-02** | **VERIFIED** | 嵌套事务、单快照及 rollback_only 已实现 | Layer 1 | `src/rig/arm_ik.py`: L3251–L3261, L4342–L4370 | `test_task10b_transaction_atomicity.py` (TEST-59, 118～123) |
| **CONTRACT-03** | **DEFECT** | DataBlock 来源授权、同名错误类型对象所有权证明及 Collection 登记时序未完全满足合同 | Layer 3 + Layer 2 | `src/rig/arm_ik.py`: L138–L146, L3322–L3398, L3527–L3578, L4625–L4726 | `test_task10b_transaction_atomicity.py` (TEST-98, 101, 103, 105, 184) |
| **CONTRACT-04** | **DEFECT** | Object Parent、Collection Parent/Child、Constraint Target/Pole Target 尚未全部接入七状态日志 | Layer 2 + Layer 3 + Layer 5 | `src/rig/arm_ik.py`: L144, L1736–L2286, L2374–L2375, L2560–L2564, L2693, L2713, L3262–L3321, L4689, L4870–L4871 | `test_task10b_transaction_atomicity.py` (TEST-107～108, 113～117, 149) |
| **CONTRACT-05** | **DEFECT** | Constraint 创建、删除及目标引用恢复尚未完全通过 Layer 3 授权资源操作 | Layer 4 + Layer 3 + Layer 5 | `src/rig/arm_ik.py`: L1439–L1616, L2288–L3185, L4728–L4943 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-01, 03), `test_task10b_transaction_atomicity.py` (TEST-38, 55, 77～78, 103～106) |
| **CONTRACT-06** | **VERIFIED** | 快照、指纹、零写入证明及 FAILED-A 已实现并测试 | Layer 5 + Layer 1 | `src/rig/arm_ik.py`: L1112–L1437, L1439–L1616, L4415–L4591 | `test_task10b_transaction_atomicity.py` (TEST-31～33, 58, 69, 124～125, 137, 167～173, 185～187) |
| **CONTRACT-07** | **VERIFIED** | FAILED-B/C/D、会话隔离与解除授权主要合同已实现并测试 | Layer 5 + Layer 1 + Layer 2 | `src/rig/arm_ik.py`: L736–L1062, L2288–L3185, L3827–L4331 | `test_task10b_transaction_atomicity.py` (TEST-126～135, 147～155, 182～183) |
| **CONTRACT-08** | **DEFECT** | DataBlock 删除授权及 CleanupOutcome 模型不完整 | Layer 1 + Layer 6 + Layer 3 + Layer 2 | `src/rig/arm_ik.py`: L3399–L3670, L4599–L4623 | `test_task10b_transaction_atomicity.py` (TEST-64, 66～67, 81～83, 87～88, 99～100, 146) |
| **CONTRACT-09** | **DEFECT** | Cleanup 自行更新事务状态，重试路径直接注销待清理记录 | Layer 1 + Layer 2 | `src/rig/arm_ik.py`: L957–L1062, L3590–L3595, L3631–L3840 | `test_task10b_transaction_atomicity.py` (TEST-85～87, 112, 129, 136, 144～146) |
| **CONTRACT-10** | **UNVERIFIED** | WBC 调用链已存在，但完整单帧失败反馈合同未获得专项证明 | WBC + Layer 4 | `src/motion/whole_body_controller.py`: L303, L424, L434, L657; `src/rig/arm_ik.py`: L4728, L4945, L4977, L5210 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-04), `physics_whole_body_controller`, `physics_arm_ik`, `physics_bridge_contract` |
| **CONTRACT-11** | **VERIFIED** | 左右双臂 Reset 共同事务和回滚已实现并测试 | Layer 4 + Layer 1 | `src/rig/arm_ik.py`: L4977–L5135, L4342–L4623 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-05, 30), `test_task10b_transaction_atomicity.py` (TEST-109～112) |
| **CONTRACT-12** | **DEFECT** | 零引用无授权 DataBlock 与同名外部资源的保护合同不完整 | Layer 5 + Layer 6 + Layer 3 + Layer 1 | `src/rig/arm_ik.py`: L418–L734, L1618–L1697, L2288–L2740, L3399–L3599, L4638–L4675 | `test_task10b_transaction_atomicity.py` (TEST-79～80, 83, 86, 89～91, 94, 96～97, 104～105, 108, 129～130, 156～158, 181, 184) |

---

## 2. 合同逐项核验细节

### CONTRACT-01: 输入预验证及零写入 (Input Pre-Validation & Zero-Write Preflight)

- **真实生产函数**：
  - `_validate_influence(val, param_name)` (`src/rig/arm_ik.py`: L77–L86)
  - `_validate_side(side, allow_both, param_name)` (`src/rig/arm_ik.py`: L89–L98)
  - `_validate_vec3(vec, param_name, allow_none)` (`src/rig/arm_ik.py`: L101–L120)
  - `_validate_bool(val, param_name)` (`src/rig/arm_ik.py`: L122–L127)
  - `_resolve_armature(armature_obj)` (`src/rig/arm_ik.py`: L129–L136)
  - `_preflight_arm_ik_parent_transforms(arm, valid_side, root_obj)` (`src/rig/arm_ik.py`: L5137–L5208)
  - `set_hand_ik_target(...)` (`src/rig/arm_ik.py`: L5210–L5264)
  - `setup_arm_ik(...)` (`src/rig/arm_ik.py`: L4728–L4746)
  - `set_arm_ik_influence(...)` (`src/rig/arm_ik.py`: L4945–L4960)
  - `reset_arm_ik(...)` (`src/rig/arm_ik.py`: L4977–L4995)
- **调用链**：
  `Caller (WBC / Test)` $\to$ `set_hand_ik_target` / `setup_arm_ik` / `reset_arm_ik` $\to$ Phase A: `_validate_side()`, `_validate_vec3()`, `_validate_bool()`, `_validate_influence()` $\to$ Phase B: `_depsgraph_update()`, `_preflight_arm_ik_parent_transforms()` $\to$ `validate_effective_parent_transform()` (来自 `src/rig/transform_utils.py`) $\to$ 进入事务执行场景写入。
- **核心不变量**：
  - 所有用户参数（`side`, `world_xyz`, `hand_rotation_deg`, `pole_world_xyz`, `clamp_reach`, `influence`）在任何场景状态读取、修改或事务上下文创建前完成类型、有限性、范围及元数校验。
  - 父级有效变换矩阵 $M_{\mathrm{eff}} = M_{\mathrm{parent}} @ M_{\mathrm{parent\_inverse}}$ 预检必须满足共形变换域（有限数值、纯旋转与正均匀缩放、非奇异 $\det(A) > 0$、剪切误差 $\le 10^{-6}$、仿射行误差 $\le 10^{-6}$）。
  - 拒绝校验时立即抛出 `TypeError` 或 `ValueError`，且保证**绝对零场景写入**（零 Empty 创建、零约束新增/改动、零属性修改）。
- **已存在的具体测试编号**：
  - `tests/test_task10b_input_validation.py`：TEST-01 至 TEST-30。
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-09, TEST-10, TEST-11。
  - `tests/test_task10b_transaction_atomicity.py`：TEST-111。
- **未覆盖的执行分支 / 审计说明**：
  输入与空间预检、零写入拒绝已有源码和专项测试。
- **实际结论**：`VERIFIED`

---

### CONTRACT-02: 嵌套事务及 `rollback_only` (Same-Armature Nested Transaction & Failure Propagation)

- **真实生产函数**：
  - `_arm_rig_transaction(arm)` (`src/rig/arm_ik.py`: L4342–L4370)
  - `_ArmRigTransactionContext.mark_rollback_only(reason)` (`src/rig/arm_ik.py`: L3251–L3261)
- **调用链**：
  `Caller` $\to$ `_arm_rig_transaction(arm)` $\to$ 检查 `_ACTIVE_TRANSACTION_STACK`:
  1. 若非空且 `outer_tx.arm != arm`：抛出 `RuntimeError("Cross-armature nested transaction rejected...")`；
  2. 若 `outer_tx.state != ACTIVE`：抛出 `RuntimeError("Nested transaction rejected: outer transaction is in state...")`；
  3. 若 `outer_tx.rollback_only == True`：抛出 `RuntimeError("Nested transaction rejected: outer transaction is already marked rollback_only...")`；
  4. 复用 `outer_tx` 产出上下文（栈深保持为 1，不重复捕获快照，不触发独立提交）；
  5. 捕获内层异常：调用 `outer_tx.mark_rollback_only(...)` 并向上重抛；
  6. 外层事务退出时核验 `if tx.rollback_only: raise RuntimeError(...)` $\to$ 触发外层完整回滚。
- **核心不变量**：
  - 单一 Armature 会话身份上的重入请求严格复用外层事务上下文，栈深恒为 1，共享单一基准快照。
  - 严禁跨 Armature 嵌套调用。
  - 内层操作失败（无论是否被上层 `try/except` 捕获）单调标记 `rollback_only = True` 并保留首个失败原因。
  - 被污染的 `rollback_only` 事务禁止后续嵌套执行。
  - 外层提交门禁拒绝提交并强制转入 `ROLLING_BACK`，杜绝内层失败静默提交。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-59, TEST-118, TEST-119, TEST-120, TEST-121, TEST-122, TEST-123, TEST-183。
- **未覆盖的执行分支 / 审计说明**：
  嵌套事务、单快照及 `rollback_only` 已实现。
- **实际结论**：`VERIFIED`

---

### CONTRACT-03: 资源身份与所有权登记 (Controller & Created DataBlock Provenance Registration)

- **真实生产函数**：
  - `_ArmRigTransactionContext.register_created_controller` (`src/rig/arm_ik.py`: L3322–L3340)
  - `_ArmRigTransactionContext.register_created_constraint` (`src/rig/arm_ik.py`: L3341–L3362)
  - `_ArmRigTransactionContext.register_created_collection` (`src/rig/arm_ik.py`: L3385–L3398)
  - `_get_or_create_empty` (`src/rig/arm_ik.py`: L4625–L4726)
  - `_ensure_character_collection` (`src/rig/arm_ik.py`: L138–L148)
  - `_ArmRigTransactionContext.retry_cleanup` (`src/rig/arm_ik.py`: L3527–L3578)
- **调用链**：
  `setup_arm_ik()` $\to$ `_get_or_create_empty()` $\to$ 新建 Empty 调用 `tx.register_created_controller(obj)` 登记，并通过 `_authorized_link_object_to_collection()` 链接集合；`_ensure_character_collection()` 创建集合并链接至 `scene.collection.children` 后调用 `register_created_collection()`。
- **核心不变量**：
  - 新建控制器、约束、集合及 Type A 事务新建 DataBlock 必须在创建后、外部链接前立即在 `active_tx` 登记引用与指针身份及显式授权。
  - 删除与暂存必须满足非推断铁律：禁止凭名称推断所有权，禁止凭零引用推断 DataBlock 删除权。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-98, TEST-101, TEST-103, TEST-105, TEST-184。
- **已确认架构缺口与未覆盖分支**：
  - **F14-01 (`src/rig/arm_ik.py:3527–3578`)**：DataBlock 删除主要依据 `users == 0`，缺少 `AuthorizedCleanup(D,t)` 显式来源授权记录证明，且未实现 `PRESERVED_NO_DELETE_AUTHORITY`。
  - **F14-05 (`src/rig/arm_ik.py:4638–4675`)**：`_get_or_create_empty` 通过 `bpy.data.objects.get(name)` 取得同名错误类型对象后直接进入暂存和后续废弃流程，缺少充分所有权证明。
  - **F14-06 (`src/rig/arm_ik.py:138–146`)**：`_ensure_character_collection` 先执行 `scene.collection.children.link(col)`，后执行 `register_created_collection()`，违反“创建后、外部链接前登记所有权”的批准顺序（实际异常残留仍需专项测试）。
- **实际结论**：`DEFECT`（DataBlock 来源授权、同名错误类型对象所有权证明及 Collection 登记时序未完全满足合同）

---

### CONTRACT-04: 七状态关系日志与恢复 (Relationship Mutation 7-State Log & Evidence-Based Rollback)

- **真实生产函数**：
  - `_ArmRigTransactionContext.prepare_relationship_mutation` (`src/rig/arm_ik.py`: L3262–L3298)
  - `_ArmRigTransactionContext.update_relationship_mutation_state` (`src/rig/arm_ik.py`: L3299–L3321)
  - `_authorized_link_object_to_collection` (`src/rig/arm_ik.py`: L1736–L1863)
  - `_authorized_unlink_object_from_collection` (`src/rig/arm_ik.py`: L1864–L1988)
  - `_authorized_revert_relationship_record` (`src/rig/arm_ik.py`: L1989–L2159)
  - `_authorized_restore_collection_object_relationships` (`src/rig/arm_ik.py`: L2196–L2286)
- **调用链**：
  `Collection ↔ Object` 关系变更通过 `_authorized_link_object_to_collection` / `_authorized_unlink_object_from_collection` 写入 `prepared_relationship_mutations` 七状态日志，并在回滚时通过 `_authorized_restore_collection_object_relationships` 撤销为 `REVERTED`。
- **核心不变量**：
  - 全部关系引用修改（包括 `Collection ↔ Object`、`Collection Parent/Child`、`Object.parent`、`Constraint.target` / `pole_target`）无论正向修改还是回滚恢复，均须经由 Layer 3 执行并遵循 7 状态日志与 10 条合法状态转换。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-107, TEST-108, TEST-113, TEST-114, TEST-115, TEST-116, TEST-117, TEST-149。
- **已确认架构缺口与未覆盖分支**：
  - **F14-02 (`src/rig/arm_ik.py:144, 2374–2375, 2560–2564, 2693, 2713, 4689, 4870–4871`)**：当前仅 `Collection ↔ Object` 接入了七状态日志；`Object Parent`、`Constraint Target/Pole Target`、`Collection Parent/Child` 仍存在直接赋值或直接 link/unlink 路径，未全部经过相同授权与七状态关系记录流程。
  - **F14-06 (`src/rig/arm_ik.py:138–146`)**：Collection 创建与父子集合链接顺序未遵循先登记后链接。
- **实际结论**：`DEFECT`（Object Parent、Collection Parent/Child、Constraint Target/Pole Target 尚未全部接入七状态日志）

---

### CONTRACT-05: 约束绑定、删除及恢复 (Constraint Configuration, Identity & Restoration)

- **真实生产函数**：
  - `_ArmRigTransactionContext.register_created_constraint` (`src/rig/arm_ik.py`: L3341–L3362)
  - `_snapshot_arm_rig_state` (`src/rig/arm_ik.py`: L1439–L1616)
  - `_rollback_arm_rig_state` (`src/rig/arm_ik.py`: L2288–L2740)
  - `_verify_arm_rig_state_restored` (`src/rig/arm_ik.py`: L2742–L3185)
  - `setup_arm_ik` (`src/rig/arm_ik.py`: L4728–L4943)
- **调用链**：
  `setup_arm_ik` 在 `forearm.{side}` 和 `hand.{side}` 上配置 `ArmIK.{side}` 和 `HandRotation.{side}`，登记 `register_created_constraint`，设置目标与数值属性；回滚时由 `_rollback_arm_rig_state` 按指针移除新建约束并恢复快照记录的约束属性与顺序。
- **核心不变量**：
  - 约束的创建、删除以及 `target` / `pole_target` 关系绑定与恢复必须统一通过 Layer 3 授权资源操作接口配合 Layer 2 七状态日志执行；外部约束及其相对顺序严格受保护。
- **已存在的具体测试编号**：
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-01, TEST-03。
  - `tests/test_task10b_transaction_atomicity.py`：TEST-38, TEST-55, TEST-56, TEST-70, TEST-77, TEST-78, TEST-103, TEST-104, TEST-105, TEST-106, TEST-165, TEST-166, TEST-186。
- **已确认架构缺口与未覆盖分支**：
  - **F14-02 (`src/rig/arm_ik.py:2560–2564, 4870–4871`)**：`Constraint Target/Pole Target` 的正向绑定与回滚恢复尚未接入 Layer 3 授权操作与七状态关系日志。
  - **F14-03 (`src/rig/arm_ik.py:4830–4930`)**：Constraint 创建、删除仍存在业务层直接调用 Blender API（如 `pbone.constraints.new` / `remove`）的路径；虽有身份登记和回滚测试，但未完全收敛至批准的 Layer 3 授权资源操作职责。
- **实际结论**：`DEFECT`（Constraint 创建、删除及目标引用恢复尚未完全通过 Layer 3 授权资源操作）

---

### CONTRACT-06: 快照完整性与 FAILED-A (Snapshot Integrity, Zero-Mutation Capture & FAILED-A Classification)

- **真实生产函数**：
  - `_capture_pre_snapshot_structural_fingerprint(arm)` (`src/rig/arm_ik.py`: L1200–L1345)
  - `_verify_pre_write_zero_mutation_and_integrity(arm, pre_fp, tx)` (`src/rig/arm_ik.py`: L1347–L1437)
  - `_snapshot_arm_rig_state(arm)` (`src/rig/arm_ik.py`: L1439–L1616)
  - `_clone_snapshot_property_value(val)` (`src/rig/arm_ik.py`: L1112–L1127)
  - `_freeze_fingerprint_property_value(val)` (`src/rig/arm_ik.py`: L1129–L1178)
  - `_has_nan_or_inf(val)` (`src/rig/arm_ik.py`: L1180–L1198)
  - `_arm_rig_transaction(arm)` (`src/rig/arm_ik.py`: L4415–L4429, L4537–L4591)
- **调用链**：
  `_arm_rig_transaction` $\to$ 入口调用 `_capture_pre_snapshot_structural_fingerprint(arm)` 冻结深拷贝指纹 $\to$ 状态转为 `SNAPSHOTTING` $\to$ `_snapshot_arm_rig_state(arm)` 捕获基准快照 $\to$ 状态转为 `ACTIVE`。
  若在进入 `ACTIVE` 前发生异常：
  核验骨架身份 $\to$ `_verify_pre_write_zero_mutation_and_integrity()` 逐字段比对前置指纹、检查非有限值、未读属性与事务自建资源 $\to$ 若 100% 证实零写入且结构完好：Coordinator 归类为 `FAILED-A`，**不将健康 Armature 置入持久隔离** $\to$ 若无法证实零写入或存在指纹缺失：升级隔离为 `FAILED-C`。
- **核心不变量**：
  - 快照与指纹采集是严格只读的深拷贝，数组为不可变 tuple，杜绝原地 RNA 引用污染。
  - `FAILED-A` 必须具备严格闭环的零写入客观证明（零场景写入、指纹严格相等、零非有限值、零未读属性）。
  - 任何属性读取失败、非有限数值或不完整状态采集均 fail-closed，阻止 `FAILED-A` 并升级为 `FAILED-C`。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-31～33, TEST-58, TEST-69, TEST-74, TEST-124, TEST-125, TEST-137, TEST-167, TEST-168, TEST-169, TEST-170, TEST-171, TEST-172, TEST-173, TEST-177, TEST-179, TEST-180, TEST-185, TEST-186, TEST-187。
- **未覆盖的执行分支 / 审计说明**：
  快照、指纹、零写入证明及 FAILED-A 已实现并测试。
- **实际结论**：`VERIFIED`

---

### CONTRACT-07: FAILED-B/C/D 隔离及解除 (Rollback Verification Symmetry & Categorized FAILED Session Isolation)

- **真实生产函数**：
  - `_record_armature_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L736–L862)
  - `_issue_coordinator_authorization_grant` (`src/rig/arm_ik.py`: L864–L950)
  - `_clear_or_retire_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L957–L1062)
  - `_rollback_arm_rig_state` (`src/rig/arm_ik.py`: L2288–L2740)
  - `_verify_arm_rig_state_restored` (`src/rig/arm_ik.py`: L2742–L3185)
  - `verify_armature_deisolation_evidence` (`src/rig/arm_ik.py`: L3827–L4014)
  - `_verify_dead_armature_tombstone_retirement_evidence` (`src/rig/arm_ik.py`: L4016–L4107)
  - `request_armature_deisolation` (`src/rig/arm_ik.py`: L4110–L4222)
  - `retire_dead_armature_tombstone` (`src/rig/arm_ik.py`: L4225–L4331)
- **调用链**：
  业务异常 $\to$ Layer 1 进入 `ROLLING_BACK` $\to$ Layer 5 执行回滚与全字段核验。
  若回滚失败：
  - 回滚执行异常 $\to$ Coordinator 归类为 `FAILED-B`，在 `_ISOLATED_FAILED_ARMATURES` 记录隔离；
  - 核验偏差或 `RECOVERY_UNCERTAIN` $\to$ Coordinator 归类为 `FAILED-C`，记录隔离；
  - 骨架确认物理不存在（`ABSENT`） $\to$ 归类为 `FAILED-D`，记录死亡墓碑 `TOMBSTONED_FAILED_D`。
  解除隔离调用链：
  `request_armature_deisolation()` $\to$ Layer 5 `verify_armature_deisolation_evidence()` 核验 8 项前置条件 $\to$ Layer 1 签发单次有效授权令 `_issue_coordinator_authorization_grant()` $\to$ Layer 2 `_clear_or_retire_failure_isolation_by_coordinator(authorization_grant=grant)` 清除隔离 $\to$ 登记 `_DEISOLATION_AUDIT_LOG`。
- **核心不变量**：
  - 回滚与核验严格对称（容差 $\le 10^{-5}$）。
  - `FAILED-B/C/D` 强制隔离对应会话身份，阻断该骨架后续写事务。
  - 解除隔离必须经过 Layer 5 `verify_armature_deisolation_evidence` 核验、Layer 1 显式授权令签发，并提供非空理由。
  - 普通重试清理（`retry_pending_arm_rig_cleanup`）严禁清除 `FAILED` 隔离；`FAILED` 永远禁止转入 `COMMITTED`。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-126～135, TEST-147～155, TEST-156～164, TEST-174～178, TEST-181～183。
- **未覆盖的执行分支 / 审计说明**：
  FAILED-B/C/D、会话隔离与解除授权主要合同已实现并测试（注：历史 F-03 中关于未消费授权记录的 TTL/定期清理机制尚未单独实现）。
- **实际结论**：`VERIFIED`

---

### CONTRACT-08: 提交后资源清理 (Irreversible Commit, Authorized DataBlock Cleanup & Coordinator Outcome Evaluation)

- **真实生产函数**：
  - `_ArmRigTransactionContext.retry_cleanup` (`src/rig/arm_ik.py`: L3399–L3599)
  - `retry_pending_arm_rig_cleanup(tx_id)` (`src/rig/arm_ik.py`: L3631–L3670)
  - `_register_pending_arm_rig_cleanup(tx)` (`src/rig/arm_ik.py`: L3610–L3621)
  - `_arm_rig_transaction` Phase 3 (`src/rig/arm_ik.py`: L4599–L4623)
- **调用链**：
  `_arm_rig_transaction` 逻辑提交（状态到达 `COMMITTED`） $\to$ 进入 Phase 3 调用 `tx.retry_cleanup()` 清理暂存约束与对象；若抛出异常则置为 `CLEANUP_PENDING` 并登记 `_PENDING_ARM_RIG_CLEANUPS`。
- **核心不变量**：
  - 跨越 `COMMITTED` 红线后绝对禁止执行普通回滚。
  - DataBlock 删除必须满足 `CanDelete(D,t)`（显式删除授权 + 身份核验 + `Users(D)==0` + 无保护依赖）；无授权 Type B 与 Type C DataBlock 必须保留并标记为 `PRESERVED_NO_DELETE_AUTHORITY` 终态。
  - Layer 6 应返回结构化 `CleanupOutcome` 由 Layer 1 Coordinator 评估并决定事务状态与门禁。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-64, TEST-66, TEST-67, TEST-81, TEST-82, TEST-83, TEST-87, TEST-88, TEST-99, TEST-100, TEST-146, TEST-184。
- **已确认架构缺口与未覆盖分支**：
  - **F14-01 (`src/rig/arm_ik.py:3527–3578`)**：DataBlock 删除主要依赖 `users == 0`，缺少 `AuthorizedCleanup(D,t)` 显式授权核验，将 `ReferenceError` 转换为 `user_count = 0`，且未实现 `PRESERVED_NO_DELETE_AUTHORITY` 终态。
  - **F14-04 (`src/rig/arm_ik.py:3590–3595, 3631–3670`)**：`retry_cleanup()` 未采用返回 `CleanupOutcome` 枚举交由 Coordinator 裁决的模型，而是直接修改 `self.state` 并抛出异常。
- **实际结论**：`DEFECT`（DataBlock 删除授权及 CleanupOutcome 模型不完整）

---

### CONTRACT-09: Cleanup Gate 准入及注销 (Unidirectional Admission Gate & Coordinator-Authorized Gate Deregistration)

- **真实生产函数**：
  - `_assert_arm_rig_cleanup_gate(arm, session_record)` (`src/rig/arm_ik.py`: L3672–L3711)
  - `_assert_arm_rig_failed_isolation_gate(arm, session_record)` (`src/rig/arm_ik.py`: L3713–L3747)
  - `query_admission_gate_status(arm, session_id)` (`src/rig/arm_ik.py`: L3749–L3824)
  - `retry_pending_arm_rig_cleanup(tx_id)` (`src/rig/arm_ik.py`: L3631–L3670)
  - `_clear_or_retire_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L957–L1062)
- **调用链**：
  `_arm_rig_transaction(arm)` $\to$ `ensure_armature_session_identity(arm)` $\to$ Gate 1: `_assert_arm_rig_cleanup_gate()` $\to$ Gate 2: `_assert_arm_rig_failed_isolation_gate()` $\to$ Gate 3: 7 项身份核验。
  重试清理：`retry_pending_arm_rig_cleanup(tx_id)` $\to$ `tx.retry_cleanup()` $\to$ `_PENDING_ARM_RIG_CLEANUPS.pop(tx_id, None)`。
- **核心不变量**：
  - Layer 1 Coordinator 单向查询 Layer 2 准入门禁状态。
  - 同一 Armature 存在未解决 `CLEANUP_PENDING` 或活跃 `FAILED-B/C/D` 隔离时阻断新写事务。
  - 唯一状态与门禁决策权归属 Layer 1 Coordinator，Layer 6 严禁自行修改生命周期状态或自行注销 `CLEANUP_PENDING` 门禁。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-85, TEST-86, TEST-87, TEST-112, TEST-129, TEST-136, TEST-144, TEST-145, TEST-146。
- **已确认架构缺口与未覆盖分支**：
  - **F14-04 (`src/rig/arm_ik.py:3590–3595, 3631–3670`)**：`tx.retry_cleanup()` 直接在内部执行 `self.state = _ArmRigTransactionState.CLEANUP_PENDING` 或 `self.state = _ArmRigTransactionState.COMMITTED`；`retry_pending_arm_rig_cleanup()` 直接执行 `_PENDING_ARM_RIG_CLEANUPS.pop(tx_id, None)`，未收敛至 Coordinator 独占状态决策和门禁注销的批准合同。
  - 历史 **F-06**：`CLEANUP_PENDING` 下双臂及跨 Armature 门禁完整联合覆盖尚未补充独立专项测试。
- **实际结论**：`DEFECT`（Cleanup 自行更新事务状态，重试路径直接注销待清理记录）

---

### CONTRACT-10: Arm IK 与 WBC 的职责边界 (WBC / Arm IK Cross-Module Interface)

- **真实生产函数**：
  - `src/motion/whole_body_controller.py`:
    - `WholeBodyController.__init__` (`src/motion/whole_body_controller.py`: L303)
    - `WholeBodyController._solve_arm_ik` (`src/motion/whole_body_controller.py`: L424, L434)
    - `WholeBodyController.reset` (`src/motion/whole_body_controller.py`: L657)
  - `src/rig/arm_ik.py`:
    - `setup_arm_ik` (`src/rig/arm_ik.py`: L4728)
    - `set_hand_ik_target` (`src/rig/arm_ik.py`: L5210)
    - `set_arm_ik_influence` (`src/rig/arm_ik.py`: L4945)
    - `reset_arm_ik` (`src/rig/arm_ik.py`: L4977)
    - `get_arm_ik_state` (`src/rig/arm_ik.py`: L5072)
- **调用链**：
  `KinematicBridge` $\to$ `WholeBodyController.execute_frame()` $\to$ `_solve_arm_ik()` $\to$ 调用 `set_hand_ik_target` 或 `set_arm_ik_influence`。
- **核心不变量**：
  - WBC 依赖 Arm IK 获取单帧可达性反馈与零副作用异常安全性；Arm IK 抛出的准入拒绝或事务失败向 WBC 明确报告单帧规划失败，不静默泄漏半提交状态。
- **已存在的具体测试编号**：
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-04（WBC 重构不重置 Arm IK 状态）。
  - 四级回归套件：`physics_whole_body_controller`, `physics_arm_ik`, `physics_bridge_contract`。
- **未覆盖的执行分支 / 审计说明**：
  WBC 调用链已存在，但 Arm IK 抛出准入阻断（`CLEANUP_PENDING` / `FAILED-B/C/D`）或事务失败时与 WBC 单帧失败反馈、状态回退的完整跨模块合同尚未建立专项测试证明。
- **实际结论**：`UNVERIFIED`（WBC 调用链已存在，但完整单帧失败反馈合同未获得专项证明）

---

### CONTRACT-11: 左右双臂 Reset 原子性 (Bilateral Reset Atomic Transaction)

- **真实生产函数**：
  - `reset_arm_ik(armature_obj)` (`src/rig/arm_ik.py`: L4977–L5135)
  - `_arm_rig_transaction(arm)` (`src/rig/arm_ik.py`: L4342–L4623)
- **调用链**：
  `reset_arm_ik()` $\to$
  1. 解析 Armature 并对 4 个控制器执行父级共形预检（L4980–L5000）；
  2. 进入 `with _arm_rig_transaction(arm):` 获取单一基准快照；
  3. 左臂按 5 步顺序写入（HandIK $\to$ ElbowPole $\to$ PoseBones 中立角 $\to$ Influences 归零 $\to$ Prebend Hint）；
  4. 右臂按 5 步顺序写入（HandIK $\to$ ElbowPole $\to$ PoseBones 中立角 $\to$ Influences 归零 $\to$ Prebend Hint）；
  5. 提交准备更新依赖图并逻辑提交。若任何一步发生异常，双臂共同回滚至复位前状态。
- **核心不变量**：
  - 双臂共同原子性：左右臂复位隶属同一事务，严禁出现“左臂已复位、右臂未复位”的半重置状态。
  - 预检失败零写入。
  - 嵌套在外部事务内调用时，失败标记 `outer_tx.rollback_only = True`。
- **已存在的具体测试编号**：
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-05, TEST-30。
  - `tests/test_task10b_transaction_atomicity.py`：TEST-109, TEST-110, TEST-111, TEST-112。
- **未覆盖的执行分支 / 审计说明**：
  左右双臂 Reset 共同事务和回滚已实现并测试。
- **实际结论**：`VERIFIED`

---

### CONTRACT-12: 外部资源及独立 Armature 保护 (External Resource, Unproven DataBlock & New Armature Isolation Protection)

- **真实生产函数**：
  - `_verify_armature_session_identity_record` (`src/rig/arm_ik.py`: L418–L615)
  - `_sweep_dead_managed_armature_identities` (`src/rig/arm_ik.py`: L617–L654)
  - `ensure_armature_session_identity` (`src/rig/arm_ik.py`: L656–L734)
  - `_find_live_object_by_identity` (`src/rig/arm_ik.py`: L1618–L1645)
  - `_find_live_collection_by_identity` (`src/rig/arm_ik.py`: L1647–L1697)
  - `_rollback_arm_rig_state` (`src/rig/arm_ik.py`: L2288–L2740)
  - `_ArmRigTransactionContext.retry_cleanup` (`src/rig/arm_ik.py`: L3399–L3599)
  - `_get_or_create_empty` (`src/rig/arm_ik.py`: L4638–L4675)
- **调用链**：
  回滚、清理与控制器获取阶段检查资源身份，并对死亡 Armature 维护 `TOMBSTONED_FAILED_D` 墓碑与新骨架会话隔离。
- **核心不变量**：
  - 外部资源（未登记对象/约束/集合、无显式删除授权的 Type B DataBlock、即使 `users == 0` 的 Type C DataBlock、以及外部同名非 Empty 对象）严格免受未授权暂存、解绑或物理删除；`FAILED-D` 死亡墓碑绝不阻断新建独立 Armature。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-79, TEST-80, TEST-83, TEST-86, TEST-89, TEST-90, TEST-91, TEST-94, TEST-96, TEST-97, TEST-104, TEST-105, TEST-108, TEST-129, TEST-130, TEST-156, TEST-157, TEST-158, TEST-181, TEST-184。
- **已确认架构缺口与未覆盖分支**：
  - **F14-01 (`src/rig/arm_ik.py:3527–3578`)**：DataBlock 清理仅凭 `users == 0`（且将 `ReferenceError` 视为 `0`）执行物理删除，未验证 `AuthorizedCleanup(D,t)`，无法保护零引用的无授权外部/既有 DataBlock。
  - **F14-05 (`src/rig/arm_ik.py:4638–4675`)**：`_get_or_create_empty` 对同名非 `EMPTY` 对象未验证 Rig 历史所有权即直接暂存改名并在提交后销毁，违反同名外部资源保护合同。
- **实际结论**：`DEFECT`（零引用无授权 DataBlock 与同名外部资源的保护合同不完整）
