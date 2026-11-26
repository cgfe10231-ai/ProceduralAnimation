# 04. 事务生命周期合同规范（Transaction Lifecycle Contract）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`（L163-L174: `_ArmRigTransactionState` 枚举）  
> **性质**：9 状态生命周期状态机与不可逆边界审计合同  
> **审计日期**：2026-11-06  

---

## 1. 事务状态机全景图

当前生产代码严格维护 9 个显式生命周期状态：

```
                [Start]
                   │
                   ▼
              ┌─────────┐
              │ CREATED │
              └────┬────┘
                   │
                   ▼
           ┌──────────────┐      Snapshot 失败
           │ SNAPSHOTTING ├──────────────────────────┐
           └───────┬──────┘                          │
                   │ 快照成功                         │
                   ▼                                 │
              ┌────────┐       业务突变异常           │
              │ ACTIVE ├─────────────────────────┐   │
              └───┬────┘                         │   │
                  │ 准备提交                      │   │
                  ▼                              │   │
             ┌────────────┐    提交准备阶段异常    │   │
             │ COMMITTING ├──────────────────────┤   │
             └────┬───────┘                      │   │
                  │ 逻辑提交确认                  │   │
                  ▼                              │   │
    ┌───────────────────────────┐                │   │
    │  === 不可逆提交红线 ===   │                │   │
    └─────────────┬─────────────┘                │   │
                  ▼                              │   │
             ┌───────────┐                       │   │
             │ COMMITTED │                       │   │
             └────┬──┬───┘                       │   │
                  │  │                           │   │
      清理完全成功│  │ 清理异常                   │   │
                  │  └───────────────┐           │   │
                  │                  ▼           │   │
                  │        ┌─────────────────┐   │   │
                  │        │ CLEANUP_PENDING │   │   │
                  │        └────────┬────────┘   │   │
                  │                 │            │   │
                  │      重试成功    │ 重试失败   │   │
                  │     ┌───────────┴──────────┐ │   │
                  │     ▼                      │ │   │
                  │ ┌───────────┐              │ │   │
                  │ │ COMMITTED │              │ │   │
                  │ └─────┬─────┘              │ │   │
                  │       │                    │ │   │
                  ▼       ▼                    │ │   │
              [End: COMMITTED]                 ▼ ▼   ▼
                                         ┌──────────────┐
                                         │ ROLLING_BACK │
                                         └───────┬──────┘
                                                 │
                                 ┌───────────────┴───────────────┐
                                 │ 回滚+验证成功                  │ 回滚或验证失败
                                 ▼                               ▼
                          ┌─────────────┐                  ┌────────┐
                          │ ROLLED_BACK │                  │ FAILED │
                          └──────┬──────┘                  └───┬────┘
                                 │                             │
                                 ▼                             ▼
                          [End: Exception]              [End: Fatal Err]
```

---

## 2. 九大状态转换矩阵与操作权限合同

| 状态 | 进入条件 | 允许迁移的下一状态 | 严禁迁移的状态 | 资源操作权限 | 可逆/不可逆边界 | 异常处理职责 | 恢复与重试条件 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CREATED** | `_ArmRigTransactionContext` 实例化完成 | `SNAPSHOTTING`, `FAILED` | `ACTIVE`, `COMMITTING`, `COMMITTED`, `ROLLED_BACK` | 禁止任何场景写入 | 处于进入前阶段（绝对可逆） | 初始化异常直接抛出并清理栈 | 无需重试 |
| **SNAPSHOTTING** | 事务成功压入 `_ACTIVE_TRANSACTION_STACK` | `ACTIVE`, `FAILED` | `COMMITTING`, `COMMITTED`, `ROLLING_BACK`, `ROLLED_BACK` | 绝对只读；允许且仅允许刷新 depsgraph | 绝对可逆（未发生任何业务突变） | 快照生成异常转为 `FAILED`，绝不触发回滚（快照不存在无法回滚） | 外部可修复场景后重新发起新事务 |
| **ACTIVE** | 基线快照捕获成功，进入业务上下文 `yield tx` | `COMMITTING`, `ROLLING_BACK` | `CREATED`, `SNAPSHOTTING`, `COMMITTED`, `ROLLED_BACK` | 允许控制器新建、暂存、修改变换、调整约束 | **关键可逆区间**（所有变更均被快照完全覆盖） | 拦截业务异常，强行转移至 `ROLLING_BACK` | 触发回滚引擎恢复现场 |
| **COMMITTING** | 业务逻辑执行完毕，进入提交准备阶段（Phase 1） | `COMMITTED`, `ROLLING_BACK` | `CREATED`, `SNAPSHOTTING`, `ACTIVE`, `ROLLED_BACK` | 刷新 depsgraph，验证派生数据最终一致性 | **最后可逆边界**（尚未达成逻辑提交） | 拦截准备期异常，强行转移至 `ROLLING_BACK` | 触发回滚引擎恢复现场 |
| **COMMITTED** | 业务与准备无异常，跨过逻辑提交点（Phase 2） | `CLEANUP_PENDING`（清理异常时） | `ROLLING_BACK`, `ROLLED_BACK`, `ACTIVE`, `CREATED` | 允许执行 Doomed 资源物理删除；**严禁回滚！** | **跨越不可逆提交红线** | 进入 Phase 3；若清理失败转入 `CLEANUP_PENDING` | 业务已持久化，仅资源清理可重试 |
| **ROLLING_BACK** | `COMMITTED` 达成前任意阶段发生异常 | `ROLLED_BACK`, `FAILED` | `COMMITTING`, `COMMITTED`, `ACTIVE` | 允许删除自建资源、恢复暂存资源、恢复骨骼约束 | 执行可逆恢复动作 | 捕获底层恢复与验证异常；若恢复中再抛错则置 `FAILED` | 执行 `_verify_arm_rig_state_restored` |
| **ROLLED_BACK** | 回滚执行完毕且全字段比对 100% 吻合 | 无（事务终态） | 任何其他状态 | 严禁对场景继续写入 | 场景已完全恢复至快照状态 | 重新抛出触发回滚的原始异常（`raise orig_exc`） | 场景干净，支持上层重新发起调用 |
| **CLEANUP_PENDING** | Phase 3 提交后清理发生异常，或重试仍失败 | `COMMITTED`（重试成功） | `ROLLING_BACK`, `ROLLED_BACK`, `ACTIVE` | 仅允许通过 `retry_cleanup()` 尝试物理删除暂存资源 | 业务已不可逆提交，仅垃圾回收挂起 | 记录 `cleanup_error` 并向注册表登记 | 调用 `retry_pending_arm_rig_cleanup` |
| **FAILED** | 快照失败、或回滚过程本身崩溃、或核验失败 | 无（致命终态） | 任何其他状态 | 严禁继续写入；场景可能处于半恢复污染状态 | 恢复失败，污染不可逆 | 抛出包含原始异常与恢复异常的复合 `RuntimeError` | 严禁自动重试；必须人工或系统级干预 |

---

## 3. 十大重点边界与故障注入场景审计

| 序号 | 故障与边缘场景 | 触发阶段与代码位置 | 实际状态转移 | 资源处理与所有权行为 | 最终场景与测试证据 |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **1** | **Snapshot 创建失败** | `during_snapshot_creation`<br>(L249) | `SNAPSHOTTING` $\to$ `FAILED` | 此时未发生任何业务写入；不执行回滚；事务出栈。 | 场景无污染，抛出 Snapshot 异常。<br>对应测试：TEST-65 |
| **2** | **Controller 创建失败** | `setup_arm_ik_after_first_controller`<br>(L1841) | `ACTIVE` $\to$ `ROLLING_BACK` $\to$ `ROLLED_BACK` | 已创建的 `HandIK.L` 在所有权表中有登记，回滚时按物理指针彻底删除。 | 场景完全恢复，无孤儿 Empty。<br>对应测试：TEST-36, TEST-94 |
| **3** | **Collection 链接失败** | `get_or_create_empty_after_register`<br>(L1754) | `ACTIVE` $\to$ `ROLLING_BACK` $\to$ `ROLLED_BACK` | Empty 对象在 `bpy.data.objects.new` 成功后已立即登记所有权，即便链接集合抛错，回滚仍能精准找到该对象并物理删除。 | 消除未链接孤儿 Empty。<br>对应测试：TEST-98 |
| **4** | **Constraint 创建失败** | `setup_arm_ik_after_constraints_or_prebend`<br>(L2006) | `ACTIVE` $\to$ `ROLLING_BACK` $\to$ `ROLLED_BACK` | 新建约束不在快照 `saved_con_refs` 中，被物理删除；暂存约束恢复原名和 Mute。 | 约束链完全恢复基线。<br>对应测试：TEST-38, TEST-83 |
| **5** | **Commit Prepare 失败** | `before_commit_prepare` / `during_commit_prepare`<br>(L1638, L1641) | `COMMITTING` $\to$ `ROLLING_BACK` $\to$ `ROLLED_BACK` | 处于最后可逆边界，尚未标记 `COMMITTED`，安全触发全量回滚。 | 业务提交被撤销，现场核验一致。<br>对应测试：TEST-67, TEST-68 |
| **6** | **Logical Commit 后异常** | `after_logical_commit`<br>(L1688) | `COMMITTED` $\to$ `CLEANUP_PENDING` | 业务已不可逆提交，**严禁回滚**；直接转入 `CLEANUP_PENDING` 并登记注册表。 | 场景业务保留，暂存资源等待后续清理。<br>对应测试：TEST-97 |
| **7** | **Cleanup 部分成功** | `during_cleanup_datablock_removal`<br>(L1443) | `COMMITTED` $\to$ `CLEANUP_PENDING` | 暂存 Object 删除成功，但 DataBlock 删除失败；Object 标记为 cleaned，DataBlock 保留在未清理列表。 | 细粒度跟踪，防止重复删除已成功项。<br>对应测试：TEST-73, TEST-75 |
| **8** | **Retry Cleanup 失败** | `retry_pending_arm_rig_cleanup`<br>(L1543-L1570) | 保持 `CLEANUP_PENDING` | 仍保留在 `_PENDING_ARM_RIG_CLEANUPS` 中，更新错误信息。 | 门禁继续拦截对该 Armature 的新写入。<br>对应测试：TEST-80, TEST-85 |
| **9** | **Retry Cleanup 成功** | `retry_pending_arm_rig_cleanup`<br>(L1555-L1568) | `CLEANUP_PENDING` $\to$ `COMMITTED` | 所有未清理列表清空，从 `_PENDING_ARM_RIG_CLEANUPS` 弹出并注销。 | 门禁解除，允许后续正常写入。<br>对应测试：TEST-81, TEST-86 |
| **10** | **连续事务与嵌套事务** | 连续独立调用 或 同 Armature 重入调用 (L1610-L1618) | 外层独占 `_ACTIVE_TRANSACTION_STACK`；内层复用 outer_tx | 跨 Armature 拒绝；同一 Armature 外层事务维护单一真实快照，内层调用共享上下文。 | 嵌套完全透明无二次快照污染。<br>对应测试：TEST-49, TEST-50, TEST-101 |
