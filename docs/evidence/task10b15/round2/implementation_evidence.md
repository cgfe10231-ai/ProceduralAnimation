# TASK 10-B-15 (Round 2/6: F14-05 + F14-06) Implementation Evidence

## 1. 概述与基线
- **Task**: TASK 10-B-15, Round 2/6
- **Findings**: F14-05 (修复错误类型对象的所有权判断) + F14-06 (修复 Collection 创建登记顺序)
- **基线 Commit**: `60159bc44ae6557f430cbe966668295dce5c3c90`
- **分支**: `audit/task-10-b-9`

## 2. 生产代码修改
### 目标文件: `src/rig/arm_ik.py`

#### A. 统一异常类定义
- **行号**: L217-L218
- **定义**:
  ```python
  class ExternalControllerNameConflictError(RuntimeError, ValueError):
      """Raised when pre-existing external object conflicts with controller names without transaction ownership."""
      pass
  ```
  双重继承保证在输入验证层作为 `ValueError` 捕获、在事务原子性层作为 `RuntimeError` 捕获。

#### B. Collection 创建登记顺序修复 (F14-06)
- **函数**: `_ensure_character_collection` (L138-L197)
- **修改**:
  - 严格遵循**创建 → 身份登记 → 授权链接**顺序执行：
    1. 确认处于合法 ACTIVE 事务。
    2. 创建集合: `col = bpy.data.collections.new("Character")`。
    3. 触发故障点: `character_collection_before_registration`。
    4. 身份登记: 立即向事务登记 `register_created_collection(col)`，校验引用与指针。
    5. 触发故障点: `character_collection_after_registration_before_link`。
    6. 授权链接: 登记成功后调用 `scene.collection.children.link(col)` 并校验父子链接真实存在。
    7. 触发故障点: `character_collection_after_link`。
  - **异常窗口保护**: 若在创建后、登记前/中发生异常，通过指针核验该集合尚未被链接且 `users == 0`，安全执行 `bpy.data.collections.remove(col)`，杜绝孤立集合残留并如实传播原始异常。

#### C. 事务入口对象指针基线记录 (F14-05)
- **上下文容器**: `_ArmRigTransactionContext.__init__` (L3346) 新增 `self.entry_object_ptrs: Optional[FrozenSet[int]] = None`。
- **事务入口**: `_arm_rig_transaction()` (L4683-L4685) 在进入 `ACTIVE` 状态前，复用 `_capture_pre_snapshot_structural_fingerprint()` 已获取的 `all_object_ptrs` 指纹保存不可变基线：
  ```python
  tx.entry_object_ptrs = pre_snap_fp.get("all_object_ptrs")
  ```

#### D. 错误类型对象事务所有权 8 项严格校验 (F14-05)
- **函数**: `_verify_transaction_wrong_type_object_ownership(obj, tx, arm)` (L4884-L4943)
- **必须同时满足的 8 项条件**:
  1. 当前存在且状态为 `ACTIVE` 的事务。
  2. 对象已登记于当前事务的 `created_controller_objects`。
  3. 登记的 `obj_ref` 与活体对象是同一实体 (`is`)。
  4. 登记的 `obj_ptr` 与当前活体指针一致 (`as_pointer()`)。
  5. 对象真实存在于 `bpy.data.objects`。
  6. **对象指针不存在于事务入口原始指针集合** (`obj_ptr not in tx.entry_object_ptrs`)。
  7. 当前事务与目标 Armature 会话身份一致 (`tx.arm is arm`)。
  8. 未发生 `ReferenceError` 或无法证明的状态。

#### E. 控制器替换点严格校验 (F14-05)
- **函数**: `_get_or_create_empty(name, root_obj, tx, arm)` (L4962-L4969)
- **修改**: 若存在同名非 EMPTY 对象，严禁凭名称直接暂存替换；调用 `_verify_transaction_wrong_type_object_ownership()` 进行 8 条件核验。未通过校验时直接抛出 `ExternalControllerNameConflictError("EXTERNAL_CONTROLLER_NAME_CONFLICT: ...")`，拒绝修改对象名称、数据块、Parent 及集合关系。

#### F. 入口预检安全防线 (F14-05)
- **入口 A**: `setup_arm_ik()` (L5072-L5085) 在进入新事务前预检四个控制器名称，若存在无法证明所有权的非 EMPTY 对象，直接抛出 `EXTERNAL_CONTROLLER_NAME_CONFLICT`，实现零场景写入拒绝。
- **入口 B**: `_preflight_arm_ik_parent_transforms()` (L5502-L5515) 纠正此前自动初始化的错误假设，在触发任何业务写入前对四个控制器名称执行相同所有权校验，杜绝单侧修改后在对侧失败的半初始化。

---

## 3. 原有测试断言与受控场景适配

### A. Input Validation 专项测试 (`tests/test_task10b_input_validation.py`)
- **TEST-28 (`test_28_requested_wrong_type_controller_auto_replaced`)**:
  - 原测试预期请求侧错误类型对象被自动替换。
  - 现更新为：验证预存在的外部 Mesh 对象占用 `HandIK.L` 时，`set_hand_ik_target()` 写前预检拒绝，抛出 `EXTERNAL_CONTROLLER_NAME_CONFLICT`。
  - 全面核验 8 维零场景突变（对象指针、数据块指针、Parent、Collection、TRS、无新建控制器、无新建骨骼约束、事务栈及 Cleanup Gate 状态）。
- **TEST-29 (`test_29_wrong_type_other_side_controller_preflight`)**:
  - 原测试预期预检忽略对侧错误类型对象。
  - 现更新为：验证对侧错误类型控制器在自动初始化预检中被拒绝，抛出 `EXTERNAL_CONTROLLER_NAME_CONFLICT`，四个控制器及骨骼约束零业务写入。
- **TEST-30 (`test_30_wrong_type_pole_controller_auto_replaced`)**:
  - 原测试预期请求侧错误类型 Pole 被自动替换。
  - 现更新为：验证错误类型 ElbowPole 预检拒绝，抛出 `EXTERNAL_CONTROLLER_NAME_CONFLICT`，原对象与 DataBlock 完整保留，零新增约束。

### B. Atomicity 专项测试 (`tests/test_task10b_transaction_atomicity.py`)
- **TEST-35 (`test_35_direct_rollback_wrong_type_controller`)**:
  - 验证事务前外部错误类型对象在调用 `setup_arm_ik()` 时被拒绝并抛出 `EXTERNAL_CONTROLLER_NAME_CONFLICT`，原对象、DataBlock、Parent、Collection、TRS 完整保留。
- **TEST-40 (`test_40_fault_injection_setup_arm_ik_after_controller_replaced`)**:
  - 保留替换后故障注入回滚验证，适配为在真实外层事务 ACTIVE 阶段创建并登记的测试用错误类型对象，验证回滚后原场景完整恢复。
- **TEST-65 (`test_65_reversible_commit_preparation_failure_rolls_back`)**:
  - 保留 Phase 1 提交准备故障回滚验证，适配为在真实外层事务 ACTIVE 阶段创建并登记的测试用错误类型对象，验证 Phase 1 失败回滚干净，活动事务栈恢复为空。
- **原有 Cleanup 测试受控场景统一适配 (TEST-64, 66, 67, 81, 82, 83, 92, 102, 136, 184, 188～193)**:
  - 遵循统一受控模式：DataBlock 在事务前准备好，进入真实 `_arm_rig_transaction(self.armature)`，在事务 ACTIVE 后创建测试用错误类型 Object 并登记至 `created_controller_objects`，调用 `_authorized_link_object_to_collection(collection, obj, tx)` 建立合法关系，在同一外层事务内调用 `setup_arm_ik()`，由外层事务执行真正 Commit/Cleanup/Retry 行为。
  - 完整保留各测试原有的无授权 DataBlock 保留、`CLEANUP_PENDING` 状态机、重试收敛性、Pending 门禁注销与共享资源保护断言。

---

## 4. 新增专项测试结果 (Atomicity TEST-194～TEST-201)

| 测试用例编号 | 必须覆盖的行为 | 实际执行结果 |
|---|---|---|
| **TEST-194** (`test_194_external_mesh_occupying_handik_l_rejected_by_setup`) | 事务前外部 Mesh 占用 HandIK.L，setup 拒绝，全部外部资源原样保留 | **PASS (ok)** |
| **TEST-195** (`test_195_opposite_elbowpole_curve_preflight_rejected_by_hand_target`) | 对侧 ElbowPole.R 被外部 Curve 占用，set_hand_ik_target 自动初始化预检拒绝，零业务写入 | **PASS (ok)** |
| **TEST-196** (`test_196_transaction_created_wrong_type_object_safely_replaced`) | 当前事务新建并登记的错误类型 Object，允许按身份安全替换；无授权 DataBlock 仍保留 | **PASS (ok)** |
| **TEST-197** (`test_197_pre_existing_object_added_to_created_controller_objects_rejected`) | 事务前已有对象即使被错误追加进 created_controller_objects，也不得获得替换权 | **PASS (ok)** |
| **TEST-198** (`test_198_collection_creation_fault_before_registration_no_orphan`) | Collection 创建成功后、登记前注入失败，检查零孤立 Collection 残留及真实错误传播 | **PASS (ok)** |
| **TEST-199** (`test_199_collection_fault_after_registration_before_link_rolls_back`) | Collection 登记后、场景链接前注入失败，核验事务回滚删除精确身份 | **PASS (ok)** |
| **TEST-200** (`test_200_collection_fault_after_link_rolls_back_parent_child_and_collection`) | Collection 场景链接后注入失败，核验父子链接和新建 Collection 完整回滚 | **PASS (ok)** |
| **TEST-201** (`test_201_pre_existing_character_collection_preserved_on_reentry`) | 已存在的 Character Collection 重复调用时身份、成员与父子关系保持不变 | **PASS (ok)** |

---

## 5. 完整验证结果汇总

| 测试套件 | 计划测试数 | 实际执行数 | 通过数 | 失败数 | 退出码 | 耗时 | 证据日志 |
|---|---:|---:|---:|---:|---:|---:|---|
| **Atomicity 专项测试** | 171 | 171 | 171 | 0 | 0 | 13.01s | `docs/evidence/task10b15/round2/atomicity.log` |
| **Input Validation 专项测试** | 30 | 30 | 30 | 0 | 0 | 2.51s | `docs/evidence/task10b15/round2/input_validation.log` |
| **Lifecycle 专项测试** | 30 | 30 | 30 | 0 | 0 | 4.18s | `docs/evidence/task10b15/round2/lifecycle.log` |
| **Architecture Integrity Gate** | 6 | 6 | 6 | 0 | 0 | 1.17s | `docs/evidence/task10b15/round2/architecture_integrity_gate.log` |
| **Quick 级别回归测试** | 19 | 19 | 19 | 0 | 0 | 48.80s | `docs/evidence/task10b15/round2/tier_quick.log` |
| **Physics 级别回归测试** | 27 | 27 | 27 | 0 | 0 | 111.11s | `docs/evidence/task10b15/round2/tier_physics.log` |
| **Motion 级别回归测试** | 12 | 12 | 12 | 0 | 0 | 52.62s | `docs/evidence/task10b15/round2/tier_motion.log` |
| **Full 级别回归测试** | 42 | 42 | 42 | 0 | 0 | 167.78s | `docs/evidence/task10b15/round2/tier_full.log` |

---

## 6. 遗留项与范围保护说明
1. **1/6 遗留项说明**:
   - R1-TAIL-01 (Type B 授权来源真实性)、R1-TAIL-02 (Type A 合法授权删除验证)、R1-TAIL-03 (授权删除异常分支覆盖) 维持 **OPEN** 状态，严格遵照指令留到 6/6 统一处理。
   - 本轮未触碰任何 DataBlock 授权核心逻辑。
2. **其余 Finding 状态**:
   - F14-02、F14-03、F14-04 维持既有状态，本轮不予处理，严禁跨轮修复。
3. **未越权承诺**:
   - 未改动任何 WBC、IK 求解数学、关系日志状态机、Coordinator 所有权逻辑。
   - 未修改历史 10-B-14 审计文件。
