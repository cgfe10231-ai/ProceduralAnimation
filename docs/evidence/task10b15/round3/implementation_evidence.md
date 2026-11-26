# TASK 10-B-15 (Round 3/6: F14-03 + F14-02) Implementation Evidence

## 1. 概述与基线
- **Task**: TASK 10-B-15, Round 3/6
- **Findings**: F14-03 (Constraint 资源创建/删除 Layer 3 授权操作与身份管理) + F14-02 (Constraint Target / Pole Target 关系日志与 7 状态恢复)
- **基线 Commit**: `2372fc4a3f1bec46e1c46523459db695cdb3224e`
- **分支**: `audit/task-10-b-9`

## 2. 生产代码修改
### 目标文件: `src/rig/arm_ik.py`

#### A. Layer 3 约束创建与删除授权函数 (F14-03)
- **函数**: `_authorized_create_constraint()`
  - 严格校验当前处于合法 ACTIVE 事务。
  - 校验目标 PoseBone 真实存在及约束类型合法性。
  - 调用 `pbone.constraints.new(constraint_type)` 创建约束。
  - 立即向事务登记约束身份记录（包含 `pbone_name`、`constraint_name`、`constraint_type`、活体引用与指针 `as_pointer()`）。
  - 同步记录至 `tx.created_constraints` 与 `tx.all_transaction_constraints`。
- **函数**: `_authorized_remove_constraint()`
  - 严格校验删除授权（ROLLBACK 阶段核验 `created_constraints`，POST_COMMIT_CLEANUP 阶段核验 `stashed_constraints` 与 `uncleaned_stashed_constraints`）。
  - 拒绝删除未授权的外部约束或非本事务托管约束。
  - 严谨处理死引用（`ReferenceError`）与同名替换，防止误删同名外部替换约束。

#### B. Layer 3 约束 Target / Pole Target 授权写入与 7 状态关系日志 (F14-02)
- **函数**: `_authorized_assign_constraint_targets()` 与 `_apply_single_constraint_target_unit()`
  - 严格校验 Target 必须为 Blender Object 实体、Subtarget 必须为字符串或 None。
  - 读取原始 target、subtarget、pole_target、pole_subtarget 并生成初始快照。
  - 创建 7 状态关系突变记录（`CONSTRAINT_TARGET_ASSIGN`、`CONSTRAINT_POLE_TARGET_ASSIGN`），初始状态为 `PREPARED`。
  - 写入活体属性，核验赋值真实生效后迁移至 `APPLIED_VERIFIED`。
  - 事务提交阶段通过 `_confirm_relationship_mutations()` 统一确认为 `CONFIRMED`。

#### C. 回滚时序 Step 0 与关系日志逆向恢复 (F14-02 + F14-03)
- **函数**: `_authorized_revert_relationship_record()`
  - 扩充支持 `CONSTRAINT_TARGET_ASSIGN` 与 `CONSTRAINT_POLE_TARGET_ASSIGN` 类型的逆向恢复。
  - 严格依据记录中的原始指针与对象引用恢复原始 `target`、`subtarget`、`pole_target` 与 `pole_subtarget`。
  - 恢复成功后将状态标定为 `REVERTED`；若逆向写入失败则记录原因并迁移至 `RECOVERY_UNCERTAIN`。
- **回滚时序**:
  - `_rollback_arm_rig_state()` 在执行 Step 1 删除新建控制器 Empty 对象之前，优先执行 **Step 0 约束目标关系逆向恢复**。
  - 确保控制器 Empty 仍处于活体存在状态时逆向解绑或恢复约束引用，杜绝悬垂指针与死引用错误。
  - Step 1 调用 `_authorized_remove_constraint(..., phase="ROLLBACK")` 依身份清理事务新建约束。
  - 后续重试清理 `retry_cleanup()` 委托 `_authorized_remove_constraint(..., phase="POST_COMMIT_CLEANUP")` 安全清理暂存约束。

#### D. `setup_arm_ik()` 统一收敛至 Layer 3 入口
- 替换直接调用 `pbone.constraints.new()`、`pbone.constraints.remove()` 为 `_authorized_create_constraint()` 与 `_authorized_remove_constraint()`。
- 替换直接写入 `con.target`、`con.subtarget`、`con.pole_target`、`con.pole_subtarget` 为 `_authorized_assign_constraint_targets()`。
- 保证无任何旁路直接修改约束或目标引用。

---

## 3. 测试适配与新增

### A. 现有测试适配 (`tests/test_task10b_transaction_atomicity.py`)
- **TEST-113**: 适配 `tx.prepared_relationship_mutations` 包含 Collection 链接与 Constraint Target 赋值两类记录，按类别分别断言 Collection 变更状态。
- **TEST-117**: 适配状态映射构建逻辑，过滤 `COLLECTION_OBJECT_LINK` 记录以准确比对控制器集合关系状态。

### B. 新增专项测试 (TEST-202 至 TEST-216，共 15 项)
| 编号 | 测试用例 | 验证核心行为 | 结果 |
|---|---|---|---|
| **TEST-202** | `test_202_authorized_ik_constraint_creation_registered_with_live_pointer` | Layer 3 创建 IK 约束并登记 live pointer | **PASS** |
| **TEST-203** | `test_203_authorized_copy_rotation_constraint_creation_registered` | Layer 3 创建 Copy Rotation 约束并登记 | **PASS** |
| **TEST-204** | `test_204_unauthorized_constraint_deletion_rejected` | 未授权约束删除被拒绝抛出异常 | **PASS** |
| **TEST-205** | `test_205_transaction_created_constraint_removed_by_identity_on_rollback` | 回滚时按身份准确删除事务新建约束 | **PASS** |
| **TEST-206** | `test_206_pre_existing_constraint_on_forearm_preserved_on_rollback` | 前臂预存约束在回滚中严格保留 | **PASS** |
| **TEST-207** | `test_207_stashed_constraint_removed_via_layer3_in_post_commit_cleanup` | 提交后清理通过 Layer 3 删除暂存约束 | **PASS** |
| **TEST-208** | `test_208_constraint_cleanup_fault_enters_cleanup_pending_and_retry_succeeds` | 清理约束故障进入 CLEANUP_PENDING 且重试成功 | **PASS** |
| **TEST-209** | `test_209_ik_target_assignment_7_state_logging_confirmed` | IK Target 赋值生成 7 状态日志并于提交时确认 | **PASS** |
| **TEST-210** | `test_210_ik_pole_target_assignment_and_pole_subtarget_logging` | Pole Target 与 Pole Subtarget 赋值记录并回滚恢复 | **PASS** |
| **TEST-211** | `test_211_copy_rotation_target_assignment_preserves_wrist_constraints` | Copy Rotation Target 赋值记录并保护手腕约束 | **PASS** |
| **TEST-212** | `test_212_rollback_step0_target_reversion_prior_to_controller_cleanup` | Step 0 在控制器删除前恢复 Target 关系 | **PASS** |
| **TEST-213** | `test_213_target_assignment_invalid_target_type_rejected_zero_mutation` | 非 Object Target 赋值预检拒绝，零场景突变 | **PASS** |
| **TEST-214** | `test_214_target_assignment_apply_failure_transitions_to_no_effect` | 应用失败安全迁移至 NO_EFFECT | **PASS** |
| **TEST-215** | `test_215_target_assignment_rollback_failure_marks_uncertain_and_enters_isolation` | 回滚恢复失败标记 UNCERTAIN 并隔离 | **PASS** |
| **TEST-216** | `test_216_setup_arm_ik_bilateral_target_relationships_confirmed_on_commit` | 双侧 Arm IK 建立 6 项 Target 关系并全量确认 | **PASS** |

---

## 4. 全套验证汇总

| 验证项 | 预期数量 | 实际执行 | 结果 | 耗时 |
|---|---|---|---|---|
| **Atomicity Suite** | 186 | 186 | **186 PASS (0 FAIL, 0 ERR)** | 14.02s |
| **Input Validation** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 2.41s |
| **Lifecycle Contract** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 4.23s |
| **Tier Quick** | 19 | 19 | **19 PASS (0 FAIL, 0 ERR)** | 50.86s |
| **Tier Physics** | 27 | 27 | **27 PASS (0 FAIL, 0 ERR)** | 108.78s |
| **Tier Motion** | 12 | 12 | **12 PASS (0 FAIL, 0 ERR)** | 52.37s |
| **Tier Full** | 42 | 42 | **42 PASS (0 FAIL, 0 ERR)** | 167.88s |
| **Architecture Gate** | 6 | 6 | **6 PASS (0 FAIL, 0 ERR)** | 1.24s |
| **总计** | 352 | 352 | **100% PASS** | - |

---

## 5. 遗留项状态追踪
根据项目指令，下列历史遗留项维持 **OPEN**，冻结至 6/6 集中处理：
- `R1-TAIL-01`: Type B 授权来源真实性核验
- `R1-TAIL-02`: Type A 合法授权删除验证
- `R1-TAIL-03`: 授权删除异常分支覆盖
- `R2-TAIL-01`: 错误类型对象被替换后的 DataBlock 授权链路
- `R2-TAIL-02`: 集合成员链接恢复异常分支覆盖
