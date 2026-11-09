# TASK 10-B-15 (Round 4/6: F14-02 Object Parent 与 Collection Parent/Child 关系授权闭环) Implementation Evidence

## 1. 概述与基线
- **Task**: TASK 10-B-15, Round 4/6
- **Finding**: F14-02 (Object Parent Assignment, Matrix Parent Inverse Assignment, Collection Child Link, Collection Child Unlink 关系授权闭环与七状态日志)
- **基线 Commit**: `4d1091ccafa52ac8be2dd261a258a76017282c5e`
- **分支**: `audit/task-10-b-9`

## 2. 生产代码修改
### 目标文件: `src/rig/arm_ik.py`

#### A. Layer 3 辅助与关系操作函数
- **函数**: `_matrix_equals(m1, m2, tol=1e-5)`
  - 矩阵逐元素容差比对，支持 None 检查与维度保护。
- **函数**: `_is_child_collection_linked_by_identity(parent, child, child_ptr=None)`
  - 按对象与指针身份验证 child 是否已被挂载在 parent 下。
- **函数**: `_is_collection_descendant_of(candidate_child, candidate_ancestor, visited=None)`
  - 递归环路检测，防止集合循环挂载。
- **函数**: `_authorized_assign_object_parent(obj, parent, matrix_parent_inverse=None, active_tx=None)`
  - 完整执行第 3.3 节前置 10 项校验（ACTIVE 事务、live 引用、live pointer、空物体类型、事务权限、Parent 活体、跨 Armature 校验、无自我/循环父级、矩阵共形、Armature Session 匹配、rollback_only 检查）。
  - 执行 3 阶段变更协议：`PREPARE` $\to$ `APPLY`（支持故障注入点 `object_parent_before_write`、`object_parent_after_parent_before_inverse`） $\to$ `CONFIRM`（支持故障注入点 `object_parent_before_confirm`）。
  - 若 parent 与 matrix_parent_inverse 无变动，判定为 `NO_EFFECT`，零多余状态流转，底层零写入。
- **函数**: `_authorized_link_child_collection(parent_collection, child_collection, active_tx=None, category="TX_ADDED")`
  - 执行集合父子挂载 3 阶段协议。若已挂载则判定为 `NO_EFFECT`。支持注入点 `collection_child_link_during_apply_before_c_api` 与 `collection_child_link_before_confirm`。
- **函数**: `_authorized_unlink_child_collection(parent_collection, child_collection, active_tx=None, category="TX_UNLINKED_ORIGINAL")`
  - 执行集合父子解绑 3 阶段协议。
- **函数**: `_authorized_restore_relationship(active_tx, snapshot, restoration_errors, mutation_type=None)`
  - 逆序调度关系恢复。

#### B. 生产管线调用入口替换
- **`_get_or_create_empty()`**:
  - 替换原有的直接赋值 `obj.parent = parent; obj.matrix_parent_inverse = Matrix.Identity(4)` 为 `_authorized_assign_object_parent(obj=obj, parent=parent, matrix_parent_inverse=Matrix.Identity(4), active_tx=active_tx)`。
- **`_ensure_character_collection()`**:
  - 替换原有的直接挂载 `scene.collection.children.link(col)` 为 `_authorized_link_child_collection(scene.collection, col, active_tx=active_tx)`。

#### C. 快照与回滚时序协议升级
- **`_capture_snapshot()`**:
  - `character_collection` 快照增加 `parent_ptrs` 与 `child_ptrs` 数组。
  - `controllers` 快照增加 `parent_ptr` 字段。
- **`_rollback_arm_rig_state()`**:
  - **Step 0**: 优先恢复约束目标关系。
  - **Step 0.5**: 优先逆向恢复 `OBJECT_PARENT_ASSIGN` 关系（在控制器 Empty 对象被物理删除之前完成父级解绑与矩阵重置）。
  - **Step 1**: 控制器恢复时，若已被 Step 0.5 恢复则跳过二次写入；未恢复则按快照核验 Parent 指针身份。
  - **Step 3.0**: 倒序逆向恢复 `COLLECTION_CHILD_LINK` 与 `COLLECTION_CHILD_UNLINK` 关系。
  - **Step 3.1**: 执行第 9.2 节外部依赖检查（核验 target_col 是否包含未受管 object、外部 child collection 或除 `initial_parent` 之外的外部 parent）；若存在外部依赖，拒绝删除并记入 `restoration_errors`；若无外部依赖，安全从合法父级 unlink 后执行 `bpy.data.collections.remove`。

---

## 3. 测试套件与新增用例

### A. 现有测试调整 (`tests/test_task10b_transaction_atomicity.py`)
- **TEST-116**: 适配 `tx.prepared_relationship_mutations` 包含 `COLLECTION_OBJECT_LINK` 与 `OBJECT_PARENT_ASSIGN` 2 项记录，断言 2 项记录均在回滚时进入 `REVERTED`。

### B. 新增专项测试 (TEST-217 至 TEST-233，共 17 项)
| 编号 | 测试用例 | 验证核心行为 | 结果 |
|---|---|---|---|
| **TEST-217** | `test_217_hand_ik_parent_and_inverse_layer3_confirmed` | HandIK Parent 及 Matrix Parent Inverse Layer 3 写入及 7 状态 CONFIRMED | **PASS** |
| **TEST-218** | `test_218_parent_and_inverse_unchanged_transitions_to_no_effect` | Parent 及 Inverse 无变动判定为 NO_EFFECT，底层零写入 | **PASS** |
| **TEST-219** | `test_219_invalid_parent_rejected_controller_untouched` | 非法 Parent 对象（跨 Armature）被拒绝，Controller 维持原状 | **PASS** |
| **TEST-220** | `test_220_fault_before_parent_write_transitions_to_no_effect` | 写入前故障注入（object_parent_before_write）判定为 NO_EFFECT | **PASS** |
| **TEST-221** | `test_221_fault_after_parent_before_inverse_rollback_restores_initial` | parent 写入后 inverse 写入前故障，置为 APPLIED_VERIFIED 并回滚 | **PASS** |
| **TEST-222** | `test_222_fault_after_inverse_before_confirm_reverts_with_matrix_diff` | inverse 写入后 confirm 前故障，回滚至 REVERTED 且矩阵差异 $\le 1\text{e-}5$ | **PASS** |
| **TEST-223** | `test_223_original_parent_destroyed_enters_recovery_uncertain` | 原 parent 物理销毁，回滚记录 RECOVERY_UNCERTAIN 并隔离 | **PASS** |
| **TEST-224** | `test_224_external_unowned_object_parent_assignment_rejected` | 未经事务登记的外部 Object 指定父级被 Layer 3 拒绝 | **PASS** |
| **TEST-225** | `test_225_character_collection_scene_link_has_tx_added_and_confirms` | Character 集合挂载到 Scene 记录 TX_ADDED 并 CONFIRMED | **PASS** |
| **TEST-226** | `test_226_pre_existing_collection_child_link_transitions_to_no_effect` | 重复挂载已存在 Child Collection 判定为 NO_EFFECT | **PASS** |
| **TEST-227** | `test_227_collection_child_link_fault_before_c_api_no_effect` | 挂载 C-API 前故障判定为 NO_EFFECT，无残留挂载 | **PASS** |
| **TEST-228** | `test_228_collection_child_link_fault_before_confirm_reverts` | 挂载 confirm 前故障标记 APPLIED_VERIFIED，回滚成功 unlink 并 REVERTED | **PASS** |
| **TEST-229** | `test_229_authorized_unlinked_child_collection_restored_on_rollback` | 事务内 unlink 的已有 Child Collection 在回滚时重新 link 回原父级 | **PASS** |
| **TEST-230** | `test_230_external_second_parent_preserved_on_rollback` | 外部挂载第二个父级（双重父级），回滚时不删除集合，保留外部关系 | **PASS** |
| **TEST-231** | `test_231_renamed_collection_with_same_name_replacement_preserved` | 集合重命名且原名被外部占用，回滚时不破坏外部同名集合，按指针清理 | **PASS** |
| **TEST-232** | `test_232_created_collection_with_external_members_refuses_deletion` | 集合添加外部 unmanaged object，回滚时拒绝删除并安全报错 | **PASS** |
| **TEST-233** | `test_233_joint_bilateral_rollback_parent_collection_child_constraint_targets` | 联合回滚：同时包含 Parent、Collection Child 及 Constraint Target 变更，100% 恢复初始快照 | **PASS** |

---

## 4. 全套验证汇总

| 验证项 | 预期数量 | 实际执行 | 结果 | 耗时 |
|---|---|---|---|---|
| **Atomicity Suite** | 203 | 203 | **203 PASS (0 FAIL, 0 ERR)** | 13.84s |
| **Input Validation** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 2.30s |
| **Lifecycle Contract** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 4.00s |
| **Tier Quick** | 19 | 19 | **19 PASS (0 FAIL, 0 ERR)** | 47.91s |
| **Tier Physics** | 27 | 27 | **27 PASS (0 FAIL, 0 ERR)** | 104.82s |
| **Tier Motion** | 12 | 12 | **12 PASS (0 FAIL, 0 ERR)** | 54.24s |
| **Tier Full** | 42 | 42 | **42 PASS (0 FAIL, 0 ERR)** | 164.92s |
| **Architecture Gate** | 6 | 6 | **6 PASS (0 FAIL, 0 ERR)** | 1.15s |
| **总计** | 369 | 369 | **100% PASS** | - |

---

## 5. 遗留项状态追踪
根据项目指令，下列历史遗留项维持 **OPEN**，冻结至 6/6 集中处理：
- `R1-TAIL-01`: Type B 授权来源真实性核验
- `R1-TAIL-02`: Type A 合法授权删除验证
- `R1-TAIL-03`: 授权删除异常分支覆盖
- `R2-TAIL-01`: 错误类型对象被替换后的 DataBlock 授权链路
- `R2-TAIL-02`: 集合成员链接恢复异常分支覆盖
- `R3-TAIL-01`: Layer 3 约束移除在非法 phase 时的显式拦截覆盖
- `R3-TAIL-02`: Target 关系逆向恢复中同名非活体替换异常分支覆盖
- `R3-TAIL-03`: 暂存约束重试清理中指针校验与幂等性边界覆盖
