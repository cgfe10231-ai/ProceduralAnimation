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
> **纪律准则**：仅核对真实代码与测试，严禁主观推断，严禁引用不存在的符号，严禁把未覆盖分支等同于已证实缺陷。

---

## 1. 架构总览与核验结论速览

| 合同编号 | 合同名称 | 责任层级 | 生产源码定位 (`src/rig/arm_ik.py`) | 关联测试集 | 结论 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **CONTRACT-01** | 输入预验证及零写入 | Layer 4 | L77–L127, L5137–L5264 | `test_task10b_input_validation.py` (TEST-01～30) | **VERIFIED** |
| **CONTRACT-02** | 嵌套事务及 `rollback_only` | Layer 1 | L3251–L3261, L4342–L4370 | `test_task10b_transaction_atomicity.py` (TEST-59, 118～123) | **VERIFIED** |
| **CONTRACT-03** | 资源身份与所有权登记 | Layer 3 + Layer 2 | L3322–L3398, L4625–L4726 | `test_task10b_transaction_atomicity.py` (TEST-98, 101, 103, 105, 184) | **VERIFIED** |
| **CONTRACT-04** | 七状态关系日志与恢复 | Layer 2 + Layer 3 + Layer 5 | L1736–L2286, L3262–L3321 | `test_task10b_transaction_atomicity.py` (TEST-107～108, 113～117, 149) | **VERIFIED** |
| **CONTRACT-05** | 约束绑定、删除及恢复 | Layer 4 + Layer 3 + Layer 5 | L1439–L1616, L2288–L3185, L4728–L4943 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-01, 03), `test_task10b_transaction_atomicity.py` (TEST-38, 55, 77～78, 103～106) | **VERIFIED** |
| **CONTRACT-06** | 快照完整性与 FAILED-A | Layer 5 + Layer 1 | L1112–L1437, L1439–L1616, L4415–L4591 | `test_task10b_transaction_atomicity.py` (TEST-31～33, 58, 69, 124～125, 137, 167～173, 185～187) | **VERIFIED** |
| **CONTRACT-07** | FAILED-B/C/D 隔离及解除 | Layer 5 + Layer 1 + Layer 2 | L736–L1062, L2288–L3185, L3842–L4331 | `test_task10b_transaction_atomicity.py` (TEST-126～135, 147～155, 182～183) | **VERIFIED** |
| **CONTRACT-08** | 提交后资源清理 | Layer 1 + Layer 6 + Layer 3 + Layer 2 | L3399–L3670, L4599–L4623 | `test_task10b_transaction_atomicity.py` (TEST-64, 66～67, 81～83, 87～88, 99～100, 146) | **VERIFIED** |
| **CONTRACT-09** | Cleanup Gate 准入及注销 | Layer 1 + Layer 2 | L957–L1062, L3672–L3840 | `test_task10b_transaction_atomicity.py` (TEST-85～87, 112, 129, 136, 144～146) | **VERIFIED** |
| **CONTRACT-10** | Arm IK 与 WBC 的职责边界 | WBC + Layer 4 | `src/motion/whole_body_controller.py`: L303, L424, L434, L657; `src/rig/arm_ik.py`: L4728, L4945, L4977, L5210 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-04), `physics_whole_body_controller`, `physics_arm_ik`, `physics_bridge_contract` | **VERIFIED** |
| **CONTRACT-11** | 左右双臂 Reset 原子性 | Layer 4 + Layer 1 | L4977–L5135, L4342–L4623 | `test_arm_ik_lifecycle_world_transform_contract.py` (TEST-05, 30), `test_task10b_transaction_atomicity.py` (TEST-109～112) | **VERIFIED** |
| **CONTRACT-12** | 外部资源及独立 Armature 保护 | Layer 5 + Layer 6 + Layer 3 + Layer 1 | L418–L734, L1618–L1697, L2288–L2740, L3399–L3599 | `test_task10b_transaction_atomicity.py` (TEST-79～80, 83, 86, 89～91, 94, 96～97, 104～105, 108, 129～130, 156～158, 181, 184) | **VERIFIED** |

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
  - `tests/test_task10b_input_validation.py`：TEST-01 至 TEST-30（全部 30 项测试覆盖边界值、NaN/Inf、越界、非法侧别、非布尔 clamp_reach、错误元数、零场景修改、非 EMPTY 控制器预检替换及父级矩阵共形拒绝）。
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-09, TEST-10, TEST-11。
  - `tests/test_task10b_transaction_atomicity.py`：TEST-111。
- **未覆盖的执行分支**：
  无未覆盖分支。正向取值、边界值及全部异常变体均有直接测试覆盖。
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
  - `tests/test_task10b_transaction_atomicity.py`：
    - TEST-59: 跨 Armature 嵌套事务拒绝。
    - TEST-118: 同 Armature 嵌套共享上下文、单快照并正常提交。
    - TEST-119: 内层被捕获失败标记 `rollback_only` 并强制外层完整回滚。
    - TEST-120: 多级嵌套（Outer $\to$ Nested A $\to$ Nested B）失败向上传播 `rollback_only`。
    - TEST-121: 已标记 `rollback_only` 的上下文拒绝后续嵌套进入。
    - TEST-122: 嵌套失败回滚后，同骨架及独立第二骨架后续事务正常执行。
    - TEST-123: 未捕获内层异常直接冒泡并触发外层单次回滚。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

---

### CONTRACT-03: 资源身份与所有权登记 (Controller & Created DataBlock Provenance Registration)

- **真实生产函数**：
  - `_ArmRigTransactionContext.register_created_controller` (`src/rig/arm_ik.py`: L3322–L3340)
  - `_ArmRigTransactionContext.register_created_constraint` (`src/rig/arm_ik.py`: L3341–L3362)
  - `_ArmRigTransactionContext.register_created_collection` (`src/rig/arm_ik.py`: L3385–L3398)
  - `_get_or_create_empty` (`src/rig/arm_ik.py`: L4625–L4726)
  - `_ensure_character_collection` (`src/rig/arm_ik.py`: L138–L148)
- **调用链**：
  `setup_arm_ik()` $\to$ `_get_or_create_empty()` $\to$ 调用 `bpy.data.objects.new(name, None)` 新建 Empty $\to$ **在向场景/集合链接前**调用 `tx.register_created_controller(obj)` 登记至 `created_controller_objects` $\to$ 验证唯一指针与引用 $\to$ 通过 `_authorized_link_object_to_collection()` 链接到集合。
  回滚调用链：`_rollback_arm_rig_state()` $\to$ 遍历 `tx.created_controller_objects` $\to$ 核验指针与引用相等性 $\to$ 调用 `bpy.data.objects.remove(obj_ref, do_unlink=True)` 物理删除 $\to$ 检查关联 DataBlock 的 `CanDelete(D,t)`。
- **核心不变量**：
  - 新建控制器、约束、集合在创建后、外部链接暴露前立即在活跃事务上下文登记物理身份（活跃引用、C 指针、初始名称）。
  - 重复登记同一指针立即抛出 `RuntimeError`。
  - 删除必须满足非推断铁律：禁止凭名称推断所有权，禁止凭快照差集推断所有权，删除严格限定于事务已登记的自建实体。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：
    - TEST-98: 创建后立即登记，集合链接失败能干净回滚删除新建控制器。
    - TEST-101: 控制器更名、约束暂存、集合新增与 DataBlock 共享的联合身份核验。
    - TEST-103: 事务创建的约束按指针身份识别并在回滚时精准删除。
    - TEST-105: 同名但指针不同的外部约束绝不被误删。
    - TEST-184: 共享 curve 与 armature 数据在回滚/清理中严格受保护。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

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
  `Layer 4 / Layer 3` 发起关系变更 $\to$ `prepare_relationship_mutation()` 建立 `PREPARED` 记录 $\to$ 核验已存在性；若属于 `PRE_EXISTING_ORIGINAL`，直接转入 `NO_EFFECT`（零 C-API 写入，零撤销权） $\to$ 否则转入 `APPLYING` $\to$ 调用 Blender C-API $\to$ 实时 RNA 核查 $\to$ `APPLIED_VERIFIED` $\to$ 业务确认转入 `CONFIRMED`。
  回滚调用链：`_rollback_arm_rig_state()` $\to$ `_authorized_restore_collection_object_relationships()` $\to$ `_authorized_revert_relationship_record()` $\to$ 恢复原引用 $\to$ 核验恢复成功 $\to$ 转入 `REVERTED`。若撤销失败或遇到不可证明冲突，转入 `RECOVERY_UNCERTAIN` $\to$ 导致回滚核验失败并隔离 Armature。
- **核心不变量**：
  - 严格七状态机：`PREPARED`, `APPLYING`, `APPLIED_VERIFIED`, `CONFIRMED`, `NO_EFFECT`, `REVERTED`, `RECOVERY_UNCERTAIN`。
  - 严格十条合法转换转移表（`_LEGAL_RELATIONSHIP_LOG_TRANSITIONS`），非法转换抛出 `RuntimeError`。
  - `PRE_EXISTING_ORIGINAL` 重复链接转为 `NO_EFFECT`，绝对不赋予撤销或解绑权限。
  - 回滚时全部关系记录必须收敛至 `REVERTED` 或 `NO_EFFECT`；任何停留在 `APPLIED_VERIFIED`/`CONFIRMED` 或转入 `RECOVERY_UNCERTAIN` 的记录均判定为回滚核验失败。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：
    - TEST-107: 事务创建的集合链接在回滚时撤销。
    - TEST-108: 事务前已存在的外部集合成员链接在回滚时严格保留。
    - TEST-113: 重复链接已存在关系转换为 `NO_EFFECT` 且无撤销权。
    - TEST-114: C-API 成功但确认前异常记录为 `APPLIED_VERIFIED` 并在回滚中恢复为 `REVERTED`。
    - TEST-115: `APPLYING` 阶段异常且零 RNA 副作用转换为 `NO_EFFECT`。
    - TEST-116: 未捕获解绑异常转为 `RECOVERY_UNCERTAIN` 并触发回滚。
    - TEST-117: 严格校验 7 状态转换 DAG，拒绝非法转换。
    - TEST-149: 关系撤销异常转为 `RECOVERY_UNCERTAIN` 并导致 `FAILED-C` 隔离。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

---

### CONTRACT-05: 约束绑定、删除及恢复 (Constraint Configuration, Identity & Restoration)

- **真实生产函数**：
  - `_ArmRigTransactionContext.register_created_constraint` (`src/rig/arm_ik.py`: L3341–L3362)
  - `_snapshot_arm_rig_state` (`src/rig/arm_ik.py`: L1439–L1616)
  - `_rollback_arm_rig_state` (`src/rig/arm_ik.py`: L2288–L2740)
  - `_verify_arm_rig_state_restored` (`src/rig/arm_ik.py`: L2742–L3185)
  - `setup_arm_ik` (`src/rig/arm_ik.py`: L4728–L4943)
- **调用链**：
  `setup_arm_ik` $\to$ 在 `forearm.{side}` 和 `hand.{side}` 上配置 `ArmIK.{side}` 和 `HandRotation.{side}` $\to$ 新建约束调用 `tx.register_created_constraint(pbone, con)` 登记 $\to$ 设置约束参数（`target`, `pole_target`, `influence`, `pole_angle`, `chain_count`, `use_stretch`）。
  回滚调用链：`_rollback_arm_rig_state` $\to$ 按指针移除新建约束 $\to$ 恢复原约束属性（`influence`, `pole_angle`, `target`, `subtarget`, `pole_target`, `pole_subtarget`） $\to$ 恢复约束相对堆叠顺序 $\to$ `_verify_arm_rig_state_restored` 全字段核验 $\le 10^{-5}$。
- **核心不变量**：
  - 约束删除必须基于引用与指针身份核验，严禁仅按名称删除。
  - 预先存在的约束（包括外部用户约束）在指针、属性和相对堆叠顺序上保持 100% 完好。
  - 暂存的旧约束在可逆阶段保留，在逻辑提交后的 Phase 3 才执行不可逆清理。
- **已存在的具体测试编号**：
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-01, TEST-03。
  - `tests/test_task10b_transaction_atomicity.py`：TEST-38, TEST-55, TEST-56, TEST-70, TEST-77, TEST-78, TEST-103, TEST-104, TEST-105, TEST-106, TEST-165, TEST-166, TEST-186。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

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
  核验骨架身份 $\to$ `_verify_pre_write_zero_mutation_and_integrity()` 逐字段比对前置指纹、检查非有限值、未读属性与事务自建资源 $\to$ 若 100% 证实零写入且结构完好：Coordinator 归类为 `FAILED-A`，记录审计证据，**不将健康 Armature 置入持久隔离** $\to$ 若无法证实零写入或存在指纹缺失：升级隔离为 `FAILED-C`。
- **核心不变量**：
  - 快照与指纹采集是严格只读的深拷贝，数组为不可变 tuple，杜绝原地 RNA 引用污染。
  - `FAILED-A` 必须具备严格闭环的零写入客观证明（零场景写入、指纹严格相等、零非有限值、零未读属性）。
  - 任何属性读取失败、非有限数值或不完整状态采集均 fail-closed，阻止 `FAILED-A` 并升级为 `FAILED-C`。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-31～33, TEST-58, TEST-69, TEST-74, TEST-124, TEST-125, TEST-137, TEST-167, TEST-168, TEST-169, TEST-170, TEST-171, TEST-172, TEST-173, TEST-177, TEST-179, TEST-180, TEST-185, TEST-186, TEST-187。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

---

### CONTRACT-07: FAILED-B/C/D 隔离及解除 (Rollback Verification Symmetry & Categorized FAILED Session Isolation)

- **真实生产函数**：
  - `_record_armature_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L736–L862)
  - `_issue_coordinator_authorization_grant` (`src/rig/arm_ik.py`: L864–L950)
  - `_clear_or_retire_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L957–L1062)
  - `_rollback_arm_rig_state` (`src/rig/arm_ik.py`: L2288–L2740)
  - `_verify_arm_rig_state_restored` (`src/rig/arm_ik.py`: L2742–L3185)
  - `_verify_armature_deisolation_evidence` (`src/rig/arm_ik.py`: L3842–L4014)
  - `request_armature_deisolation` (`src/rig/arm_ik.py`: L4110–L4220)
  - `retire_dead_armature_tombstone` (`src/rig/arm_ik.py`: L4225–L4331)
- **调用链**：
  业务异常 $\to$ Layer 1 进入 `ROLLING_BACK` $\to$ Layer 5 执行回滚与全字段核验。
  若回滚失败：
  - 回滚执行异常 $\to$ Coordinator 归类为 `FAILED-B`，在 `_ISOLATED_FAILED_ARMATURES` 记录隔离；
  - 核验偏差或 `RECOVERY_UNCERTAIN` $\to$ Coordinator 归类为 `FAILED-C`，记录隔离；
  - 骨架身份销毁/死亡 $\to$ 归类为 `FAILED-D`，记录死亡墓碑 `TOMBSTONED_FAILED_D`。
  解除隔离调用链：
  `request_armature_deisolation()` $\to$ Layer 5 `_verify_armature_deisolation_evidence()` 核验 8 项前置条件 $\to$ Layer 1 签发单次有效授权令 `_issue_coordinator_authorization_grant()` $\to$ Layer 2 `_clear_or_retire_failure_isolation_by_coordinator(authorization_grant=grant)` 清除隔离 $\to$ 登记 `_DEISOLATION_AUDIT_LOG`。
- **核心不变量**：
  - 回滚与核验严格对称（容差 $\le 10^{-5}$）。
  - `FAILED-B/C/D` 强制隔离对应会话身份，彻底阻断该骨架后续一切写事务。
  - 解除隔离必须经过 Layer 5 真实证据核验、Layer 1 授权令签发，并提供非空理由。
  - 普通重试清理（`retry_pending_arm_rig_cleanup`）严禁清除 `FAILED` 隔离；`FAILED` 永远禁止转入 `COMMITTED`。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-126～135, TEST-147～155, TEST-182, TEST-183。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

---

### CONTRACT-08: 提交后资源清理 (Irreversible Commit, Authorized DataBlock Cleanup & Coordinator Outcome Evaluation)

- **真实生产函数**：
  - `_ArmRigTransactionContext.retry_cleanup` (`src/rig/arm_ik.py`: L3399–L3599)
  - `retry_pending_arm_rig_cleanup(tx_id)` (`src/rig/arm_ik.py`: L3631–L3670)
  - `_register_pending_arm_rig_cleanup(tx)` (`src/rig/arm_ik.py`: L3610–L3621)
  - `_arm_rig_transaction` Phase 3 (`src/rig/arm_ik.py`: L4599–L4623)
- **调用链**：
  `_arm_rig_transaction` 逻辑提交（状态到达 `COMMITTED`） $\to$ 跨越不可逆提交红线 $\to$ 进入 Phase 3 调用 `tx.retry_cleanup()` 清理暂存约束与对象。
  若清理失败：
  设置 `tx.state = CLEANUP_PENDING` $\to$ 调用 `_register_pending_arm_rig_cleanup(tx)` 登记入门禁字典 $\to$ 抛出复合异常。
  重试调用链：`retry_pending_arm_rig_cleanup(tx_id)` $\to$ `tx.retry_cleanup()` $\to$ 全部成功后从 `_PENDING_ARM_RIG_CLEANUPS` 注销。
- **核心不变量**：
  - 跨越 `COMMITTED` 红线后绝对禁止执行普通回滚。
  - 暂存约束按指针和原引用精确删除，绝不按名称删除同名替代物。
  - DataBlock 删除必须满足 `CanDelete(D,t)`（`Users(D)==0` 且具显式删除授权）。无授权 DataBlock 保留为 `PRESERVED_NO_DELETE_AUTHORITY`，不触发假性清理失败。
  - 必选清理项失败转入 `CLEANUP_PENDING` 并阻断该骨架后续写入，直至重试清理成功。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-64, TEST-66, TEST-67, TEST-81, TEST-82, TEST-83, TEST-87, TEST-88, TEST-99, TEST-100, TEST-146。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

---

### CONTRACT-09: Cleanup Gate 准入及注销 (Unidirectional Admission Gate & Coordinator-Authorized Gate Deregistration)

- **真实生产函数**：
  - `_assert_arm_rig_cleanup_gate(arm, session_record)` (`src/rig/arm_ik.py`: L3672–L3711)
  - `_assert_arm_rig_failed_isolation_gate(arm, session_record)` (`src/rig/arm_ik.py`: L3713–L3747)
  - `query_admission_gate_status(arm, session_id)` (`src/rig/arm_ik.py`: L3749–L3840)
  - `_clear_or_retire_failure_isolation_by_coordinator` (`src/rig/arm_ik.py`: L957–L1062)
- **调用链**：
  `_arm_rig_transaction(arm)` $\to$ `ensure_armature_session_identity(arm)` $\to$ Gate 1: `_assert_arm_rig_cleanup_gate()` 检查 `_PENDING_ARM_RIG_CLEANUPS` $\to$ Gate 2: `_assert_arm_rig_failed_isolation_gate()` 检查 `_ISOLATED_FAILED_ARMATURES` $\to$ Gate 3: 7 项身份核验。
  若存在阻断状态，立即以零写入抛出 `RuntimeError` 拒绝事务进入。
- **核心不变量**：
  - Layer 1 Coordinator 单向查询 Layer 2 准入门禁状态。
  - 同一 Armature 存在未解决 `CLEANUP_PENDING` 或活跃 `FAILED-B/C/D` 隔离时，彻底阻断新写事务。
  - 骨架 A 的未解决状态绝不阻断健康骨架 B。
  - 门禁的清除和注销必须经由 Coordinator 严格授权（重试成功或签发授权令），Layer 6 和 Layer 2 严禁自行注销门禁。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-85, TEST-86, TEST-87, TEST-112, TEST-129, TEST-136, TEST-144, TEST-145, TEST-146。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

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
  `KinematicBridge` $\to$ `WholeBodyController.execute_frame()` $\to$ `_solve_arm_ik()` $\to$
  - 当手部启用时：调用 `set_hand_ik_target(arm, side, world_xyz, hand_rotation_deg, pole_world_xyz, clamp_reach, influence)`；
  - 当手部禁用时：调用 `set_arm_ik_influence(arm, side, influence=0.0)`；
  - 收集末端可达性与位置/姿态误差反馈。
  - WBC 重新实例化调用 `setup_arm_ik(initial_influence=0.0)`，具备幂等性，不重置运行姿态。
- **核心不变量**：
  - WBC 是姿态协调层，负责左右肢体目标分发，绝不直接操作上肢骨骼姿态，统一委托给 Arm IK 公开接口。
  - Arm IK 负责底层世界空间逆解、父级共形约束与事务保护；当发生错误时，向 WBC 明确报告失败，绝不残留半提交状态。
  - 架构边界清晰，无双写竞争。
- **已存在的具体测试编号**：
  - `tests/test_arm_ik_lifecycle_world_transform_contract.py`：TEST-04（WBC 重构不重置 Arm IK 状态）。
  - 四级回归套件：`physics_whole_body_controller`, `physics_arm_ik`, `physics_bridge_contract`。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`

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
  - `tests/test_task10b_transaction_atomicity.py`：
    - TEST-109: 左臂复位写入失败触发双臂完整回滚。
    - TEST-110: 右臂复位写入失败触发双臂完整回滚。
    - TEST-111: 父级变换预检失败零写入。
    - TEST-112: 双臂复位、约束回滚与清理门禁联合回归。
- **未覆盖的执行分支**：
  无。
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
- **调用链**：
  回滚/清理/注册执行阶段：
  - 遇到非本事务新建实体，检查 `obj_ptr` / `con_ptr` / `col_ptr`，未匹配则视为外部资源，严禁修改或删除；
  - 外部约束、集合成员、外部父子集合层级受保护；
  - 无显式删除授权的 DataBlock 保留为 `PRESERVED_NO_DELETE_AUTHORITY`；
  - 骨架死亡后分配 `TOMBSTONED_FAILED_D` 墓碑。随后新创建的同名或复用地址的独立骨架通过 `ensure_armature_session_identity()` 获得全新 `registry_session_id`，不受死亡骨架墓碑阻断。
- **核心不变量**：
  - 外部场景资源（未登记对象、约束、集合、外部 DataBlock）绝对免受破坏。
  - 名称冲突绝不篡改所有权。
  - `CanDelete(D,t)` 定理严格保护零引用外部 DataBlock。
  - `FAILED-D` 墓碑绝不误伤新建独立骨架。
- **已存在的具体测试编号**：
  - `tests/test_task10b_transaction_atomicity.py`：TEST-79, TEST-80, TEST-83, TEST-86, TEST-89, TEST-90, TEST-91, TEST-94, TEST-96, TEST-97, TEST-104, TEST-105, TEST-108, TEST-129, TEST-130, TEST-156, TEST-157, TEST-158, TEST-181, TEST-184。
- **未覆盖的执行分支**：
  无。
- **实际结论**：`VERIFIED`
