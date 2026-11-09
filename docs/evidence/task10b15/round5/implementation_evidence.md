# TASK 10-B-15 (Round 5/6: F14-04 CleanupOutcome 与 Coordinator 状态决策权) Implementation Evidence

## 1. 概述与基线
- **Task**: TASK 10-B-15, Round 5/6
- **Finding**: F14-04 (CleanupOutcome 结构化与 Coordinator 独占状态决策权)
- **基线 Commit**: `b03fe2f48b5fe1ac70116334af9e6d77ca5ad232`
- **分支**: `audit/task-10-b-9`

## 2. 生产代码修改
### 目标文件: `src/rig/arm_ik.py`

#### A. 清理结果结构化模型定义
- **枚举**: `_CleanupOutcome(str, Enum)`
  - `CLEANUP_SUCCESS`: 清理成功完成，无残留资源且无报错。
  - `CLEANUP_INCOMPLETE`: 清理未能完全清空暂存资源队列（残留物体或约束计数 > 0）。
  - `CLEANUP_FAILED`: 清理执行中发生未捕获异常或无法证明成功。
- **数据类**: `_CleanupResult` (不可变 frozen dataclass)
  - `transaction_id`: 关联事务全局唯一 ID。
  - `outcome`: `_CleanupOutcome` 枚举值。
  - `errors`: 清理过程中收集到的错误消息元组 `Tuple[str, ...]`。
  - `remaining_objects`: 剩余未清理暂存物体数量。
  - `remaining_constraints`: 剩余未清理暂存约束数量。
  - `cause`: 首个捕获的底层异常实例（用于异常因果链传递）。

#### B. Layer 6 清理器纯化 (`_ArmRigTransactionContext.retry_cleanup`)
- **零状态修改原则**:
  - 彻底移除 `self.state = _ArmRigTransactionState.CLEANUP_PENDING` 与 `self.state = _ArmRigTransactionState.COMMITTED`。
  - 彻底移除直接操作全局 `_PENDING_ARM_RIG_CLEANUPS` 的行为。
- **前置生命周期门禁**:
  - 拦截并拒绝非法状态（`FAILED`, `ROLLING_BACK`, `ROLLED_BACK`, `ACTIVE`, `SNAPSHOTTING`, `CREATED`），抛出明确 `RuntimeError`。
- **异常捕获与计数统计**:
  - 遍历暂存约束与暂存物体，安全记录首个异常至 `first_cause`，按剩余队列长度计算 `remaining_objects` 与 `remaining_constraints`。
  - 严格依据状态返回 `_CleanupResult`。

#### C. Coordinator 独占状态决策函数 (`_coordinator_apply_cleanup_result`)
- **职能**: 事务协调层唯一合法的清理结果判定与生命周期状态转移入口。
- **支持阶段**: `INITIAL_CLEANUP` 与 `PENDING_RETRY`。
- **10 项前置严格校验**:
  1. `result` 类型必须为 `_CleanupResult` 实例。
  2. `result.transaction_id` 必须与 `tx.tx_id` 严格一致。
  3. 事务当前状态必须与所处 phase 匹配（`INITIAL_CLEANUP` 要求 `COMMITTED`；`PENDING_RETRY` 要求 `CLEANUP_PENDING`）。
  4. 严禁 `tx.state == FAILED`（严禁 FAILED $\to$ COMMITTED 转移）。
  5. Armature Session ID 身份与注册表身份严格核对。
  6. Phase 为 `PENDING_RETRY` 时，核验 `_PENDING_ARM_RIG_CLEANUPS` 中存在且必须为同一事务实例（`reg_tx is tx`）。
  7. 报告的剩余资源计数必须与底层 `tx.uncleaned_stashed_objects` / `tx.uncleaned_stashed_constraints` 队列长度完全吻合。
  8. `CLEANUP_SUCCESS` 严禁携带错误列表（`errors` 必须为空）。
  9. `CLEANUP_SUCCESS` 严禁存在残留资源（剩余物体与约束必须均为 0）。
  10. 检查 Armature 隔离记录；清理成功严禁解除关联的 FAILED 隔离记录。
- **状态转移与门禁维护**:
  - 若 `result.outcome == CLEANUP_SUCCESS`:
    - `tx.cleanup_error = None`
    - `tx.state = _ArmRigTransactionState.COMMITTED`
    - 若为 `PENDING_RETRY` 阶段，从 `_PENDING_ARM_RIG_CLEANUPS` 安全注销该条目。
  - 若 `result.outcome` 为 `CLEANUP_INCOMPLETE` 或 `CLEANUP_FAILED`:
    - `tx.state = _ArmRigTransactionState.CLEANUP_PENDING`
    - `tx.cleanup_error = "; ".join(result.errors)`
    - 登记入 `_PENDING_ARM_RIG_CLEANUPS`
    - 抛出包含完整事务上下文的 `RuntimeError`，并通过 `from result.cause` 保留底层异常因果链。

#### D. 调用方入口改造
- **`_arm_rig_transaction` Phase 3**:
  - 执行 `cleanup_result = tx.retry_cleanup()`，随后委托 `_coordinator_apply_cleanup_result(tx, cleanup_result, phase="INITIAL_CLEANUP")` 统一裁决。
- **`retry_pending_arm_rig_cleanup`**:
  - 前置校验 `tx.state == CLEANUP_PENDING`。
  - 执行 `cleanup_result = tx.retry_cleanup()`，随后委托 `_coordinator_apply_cleanup_result(tx, cleanup_result, phase="PENDING_RETRY")` 统一裁决。

---

## 3. 测试套件与新增用例

### A. 历史测试调用点迁移
- 对直接调用 `tx.retry_cleanup()` 的 6 处历史测试进行统一适配（详见 `test_change_audit.md`）：
  - `TEST-66`, `TEST-67`, `TEST-192`, `TEST-208`: 迁移为 `retry_pending_arm_rig_cleanup(tx.tx_id)`。
  - `TEST-88`, `TEST-97`: 设置 `tx.state = CLEANUP_PENDING`，直接断言 Layer 6 返回的 `_CleanupResult`。

### B. 新增专项测试 (TEST-234 至 TEST-245，共 12 项)
| 编号 | 测试用例 | 验证核心行为 | 结果 |
|---|---|---|---|
| **TEST-234** | `test_234_layer6_retry_cleanup_returns_result_without_state_mutation` | Layer 6 返回 CLEANUP_SUCCESS，不直接修改状态 | **PASS** |
| **TEST-235** | `test_235_initial_cleanup_failure_coordinator_sets_cleanup_pending_and_chains_cause` | 初次清理失败，Coordinator 设 CLEANUP_PENDING、登记门禁并抛出原始异常链 | **PASS** |
| **TEST-236** | `test_236_pending_retry_failure_preserves_state_and_pending_gate_with_chain` | Pending Retry 再次失败，状态和 Pending Gate 保留，异常明确传播 | **PASS** |
| **TEST-237** | `test_237_pending_retry_success_coordinator_transitions_committed_and_unregisters` | Pending Retry 成功，Coordinator 转入 COMMITTED，并准确注销对应注册表条目 | **PASS** |
| **TEST-238** | `test_238_failed_transaction_rejected_by_cleanup_isolation_preserved` | FAILED-B/C/D 不得通过 Cleanup 转换为 COMMITTED；原隔离记录完全保留 | **PASS** |
| **TEST-239** | `test_239_pending_registry_invalid_state_or_identity_rejects_and_refuses_pop` | Pending Registry 存在错误状态或错误事务身份时，必须抛出异常，不得注销 | **PASS** |
| **TEST-240** | `test_240_forged_cleanup_success_with_remaining_resources_rejected_by_coordinator` | 伪造 CLEANUP_SUCCESS 但仍有未完成资源，Coordinator 必须拒绝成功结论 | **PASS** |
| **TEST-241** | `test_241_cross_armature_cannot_borrow_cleanup_result_or_pending_gate` | 其他 Armature 的事务不得借用当前事务的 Cleanup Result 或 Pending Gate | **PASS** |
| **TEST-242** | `test_242_fault_after_logical_commit_before_layer6_enters_cleanup_pending_no_rollback` | after_logical_commit 故障发生在清理器运行前，仍进入 CLEANUP_PENDING，不能执行普通回滚 | **PASS** |
| **TEST-243** | `test_243_repeated_cleanup_after_success_is_idempotent_no_ghost_pending` | 清理成功后的重复请求不得重复删除资源、重复登记或产生幽灵 Pending | **PASS** |
| **TEST-244** | `test_244_cleanup_retry_does_not_clear_concurrent_failed_isolation` | CLEANUP_PENDING 与 FAILED 隔离同时存在时，清理重试不得清除 FAILED 隔离 | **PASS** |
| **TEST-245** | `test_245_partial_cleanup_progress_preserved_subsequent_retry_only_processes_remaining` | 资源清理发生部分成功后抛异常，保留已完成进度，下一次重试只处理剩余资源 | **PASS** |

---

## 4. 全套验证汇总

| 验证项 | 预期数量 | 实际执行 | 结果 | 耗时 |
|---|---|---|---|---|
| **Atomicity Suite** | 215 | 215 | **215 PASS (0 FAIL, 0 ERR)** | 14.75s |
| **Input Validation** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 2.35s |
| **Lifecycle Contract** | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 3.94s |
| **Tier Quick** | 19 | 19 | **19 PASS (0 FAIL, 0 ERR)** | 47.15s |
| **Tier Physics** | 27 | 27 | **27 PASS (0 FAIL, 0 ERR)** | 109.34s |
| **Tier Motion** | 12 | 12 | **12 PASS (0 FAIL, 0 ERR)** | 53.45s |
| **Tier Full** | 42 | 42 | **42 PASS (0 FAIL, 0 ERR)** | 167.82s |
| **Architecture Gate** | 6 | 6 | **6 PASS (0 FAIL, 0 ERR)** | 1.15s |
| **总计** | 381 | 381 | **100% PASS** | - |

---

## 5. 遗留项状态追踪
根据项目指令，下列 11 项历史遗留项维持 **OPEN**，冻结至 6/6 集中处理：
- `R1-TAIL-01`: Type B 授权来源真实性核验
- `R1-TAIL-02`: Type A 合法授权删除验证
- `R1-TAIL-03`: 授权删除异常分支覆盖
- `R2-TAIL-01`: 错误类型对象被替换后的 DataBlock 授权链路
- `R2-TAIL-02`: 集合成员链接恢复异常分支覆盖
- `R3-TAIL-01`: Layer 3 约束移除在非法 phase 时的显式拦截覆盖
- `R4-TAIL-01`: 矩阵非等比缩放的显式分解告警覆盖
- `R4-TAIL-02`: 集合循环挂载检测深度与耗时基准
- `R4-TAIL-03`: 多场景间同一集合解绑一致性核验
- `R4-TAIL-04`: 跨 Armature 约束父级非等比矩阵变换一致性
- `R4-TAIL-05`: 复杂多约束双向级联解绑恢复覆盖
