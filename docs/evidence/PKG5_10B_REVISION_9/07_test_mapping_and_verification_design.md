# 07. 测试映射与验证设计（Test Mapping & Verification Design）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`tests/test_task10b_input_validation.py` (TEST-01~30), `tests/test_task10b_transaction_atomicity.py` (TEST-31~102)  
> **性质**：现有 102 项测试对架构合同的完整映射与缺陷深度审计  
> **审计日期**：2026-11-06  

---

## 1. 现有测试套件对架构职责的映射矩阵

当前 102 项专项测试已完整覆盖从输入预检到不可逆提交的整个生命周期：

| 架构职责 | 覆盖测试范围 | 测试项总数 | 核心验证重点 |
| :--- | :--- | :---: | :--- |
| **4. Arm IK Business Operations**<br>(参数预校验与零副作用) | TEST-01 至 TEST-24 | 24 项 | `side` 字符串校验、`world_xyz` 3D 浮点校验、`hand_rotation_deg` 校验、`pole_world_xyz` 校验、`influence` 严格数值校验、`clamp_reach` 布尔校验。全部保证写前阻断与零场景污染。 |
| **3. Resource Operations**<br>(父级预检、类型检查与约束配置) | TEST-25 至 TEST-30 | 6 项 | 控制器存在性预检（Case A/B/C）、有效父级共形变换预检（M_eff 仿射性、行列式、正缩放、正交性）、Empty 类型强制检查。 |
| **1. Transaction Coordinator**<br>(状态流转与单事务原子性) | TEST-31 至 TEST-52 | 22 项 | 基础快照捕获、控制器创建中断回滚、写入中断回滚、约束回滚、嵌套同 Armature 重入复用、跨 Armature 嵌套拒绝。 |
| **5. Snapshot & Verification**<br>(不可变深拷贝与全字段核验) | TEST-53 至 TEST-66, TEST-77, TEST-78 | 16 项 | 控制器 TRS/Parent/Display 恢复验证、约束链完整性比对、Character 集合父子/成员层级验证、约束与对象物理指针丢失/改变报错。 |
| **6. Commit & Cleanup**<br>(三阶段安全协议与不可逆清理) | TEST-67 至 TEST-76, TEST-79 至 TEST-92 | 24 项 | Commit Prepare 失败回滚、提交后异常转入挂起注册表、暂存资源异步清理、DataBlock 引用计数防护、同 Armature 挂起门禁。 |
| **2. State & Ownership Registry**<br>(全生命周期所有权完整性) | TEST-93 至 TEST-102 | 10 项 | 控制器创建即时登记、指针级独占删除、外部同名对象免删保护、暂存约束 ReferenceError 捕获、提交后异常统一路由。 |
| **合计** | **TEST-01 至 TEST-102** | **102 项** | **100% 专项自动化测试全部通过** |

---

## 2. 架构深度审计七大重点检查

经过对 102 项测试代码与生产执行流的逐行比对核查，审计结论如下：

### 1. 是否存在重复测试？
- **审计发现**：
  - TEST-31（基本快照）与 TEST-65（快照不可变深拷贝）存在逻辑递进关系，但 TEST-65 覆盖了更深层次的浅拷贝逃逸检查；
  - TEST-38 与 TEST-83、TEST-96 均涉及约束恢复，但分别关注“约束顺序/属性”、“同名约束不被误删”与“暂存约束指针比对”；
- **结论**：测试用例虽有功能关联，但各自侧重于不同的故障注入分支与边界条件，**不存在无意义的纯冗余测试**。

### 2. 是否存在测试宣称覆盖但未真正触发的路径？
- **审计发现**：
  - 早期 TEST-68（Depsgraph 边界）在 Task 10-B-6 曾因触发计数不准而提前抛错，后续已修正为在真实写后更新点触发并加入断言；
  - 所有包含 `_trigger_fault_injection` 的测试均在测试体内显式断言了故障钩子的命中次数（`call_count >= 1`）。
- **结论**：**所有 102 项测试均真实命中了其宣称的代码分支与故障边界**。

### 3. 是否存在没有测试的资源删除操作？
- **审计发现**：
  - `src/rig/arm_ik.py` 中有两类删除：
    1. 事务内合法删除（自建控制器删除由 TEST-94 覆盖，暂存对象删除由 TEST-71 覆盖，暂存约束删除由 TEST-84 覆盖，自建集合删除由 TEST-76 覆盖）；
    2. 非事务分支历史遗留删除（L1745 与 L1911 中当 `_ACTIVE_TRANSACTION_STACK` 为空时的 `remove` 分支）。
- **结论**：在当前全受事务保护的生产模式下，遗留删除分支无法被正常测试命中。这证明**非事务删除分支为历史冗余死代码，需在架构迁移中安全清理**。

### 4. 是否存在没有恢复责任方的状态修改？
- **审计发现**：
  - `reset_arm_ik()` 目前直接修改控制器世界坐标、骨骼旋转欧拉角与约束 Influence，但未被 `_arm_rig_transaction` 上下文包裹。若在循环中间发生底层 Blender 异常，场景将缺少回滚恢复责任方。
- **结论**：**已将 `reset_arm_ik` 纳入架构迁移方案 Phase 3 的事务化接入计划**。

### 5. 是否存在不满足所有权合同的生产代码？
- **审计发现**：
  - Task 10-B-8 之前，`_get_or_create_empty` 在 `new` 之后未先登记所有权就先调用 `collection.objects.link`；
  - Task 10-B-8 实施后，已改为创建后立即登记（先登记后链接集合），并在 TEST-98 中验证了链接失败时能够通过所有权列表安全清理已创建的 Empty。
- **结论**：**当前代码已 100% 满足所有权优先登记合同**。

### 6. 是否存在无法证明外部修改来源的场景？
- **审计发现**：
  - 若外部代码在事务运行期间向场景插入了同名对象（如注入伪造的 `HandIK.L`），回滚引擎通过 `_find_live_object_by_identity` 识别其指针与快照记录不符，绝不执行覆盖或删除，而是将其归类为“所有权不可证明资源”并记录现场占用错误。
- **结论**：**TEST-102 已明确覆盖并验证了此项外部命名冲突保护合同**。

### 7. 是否存在清理失败后不可恢复的状态？
- **审计发现**：
  - 当 Phase 3 提交后清理发生异常时，事务进入 `CLEANUP_PENDING`，被锁入全局表 `_PENDING_ARM_RIG_CLEANUPS`，且 `_assert_arm_rig_cleanup_gate` 阻止该 Armature 发起新写入；
  - 恢复途径唯一且明确：调用 `retry_pending_arm_rig_cleanup(tx_id)`。重试支持多次幂等执行，直到物理清理成功后自动解锁。
- **结论**：**不存在死锁不可恢复状态，生命周期闭环完整**。
