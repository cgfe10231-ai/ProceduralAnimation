# 02. 架构职责边界映射报告（Architectural Responsibility Boundaries）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`  
> **性质**：六大架构职责逻辑解耦映射（不增加新 Python 文件）  
> **审计日期**：2026-11-06  

---

## 1. 架构职责概览

当前 `src/rig/arm_ik.py` 将事务控制、资源管理、数学求解、数据快照与异常清理全部汇聚于单一大文件（2414 行）。为彻底消除局部补丁的偶合缺陷，将现有逻辑映射为 6 个明确解耦的职责边界：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      1. Transaction Coordinator                         │
│               (_arm_rig_transaction, 门禁检查, 嵌套控制)                  │
└────────────┬───────────────────────────────────────────────┬────────────┘
             │                                               │
             ▼                                               ▼
┌─────────────────────────┐                     ┌─────────────────────────┐
│   5. Snapshot & Verify  │                     │   6. Commit & Cleanup   │
│ (_snapshot, _verify,   │                     │ (retry_cleanup,         │
│  _clone_prop, _vec_diff)│                     │  _PENDING_REGISTRY)     │
└────────────┬────────────┘                     └────────────┬────────────┘
             │                                               │
             ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     2. State & Ownership Registry                       │
│    (_ArmRigTransactionContext, created_*, stashed_*, identity_matcher)  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         3. Resource Operations                          │
│     (_get_or_create_empty, _ensure_col, _find_live_*, direct CRUD)      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     4. Arm IK Business Operations                       │
│  (setup_arm_ik, set_hand_ik_target, set_arm_ik_influence, reset_arm_ik)│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 六大职责边界逐项审计合同

### 职责 1：Transaction Coordinator（事务协调器）

- **当前对应函数/结构**：
  - `_arm_rig_transaction(arm: bpy.types.Object)` (L1605-L1705)
  - `_assert_arm_rig_cleanup_gate(arm: bpy.types.Object)` (L1571-L1603)
  - `_ACTIVE_TRANSACTION_STACK: List[_ArmRigTransactionContext]` (L1510)
- **当前调用者**：
  - `setup_arm_ik()` (L1823)
  - `set_hand_ik_target()` (L2375)
  - `set_arm_ik_influence()` (L2029)
- **当前被调用者**：
  - `_assert_arm_rig_cleanup_gate`
  - `_snapshot_arm_rig_state`
  - `_rollback_arm_rig_state`
  - `_verify_arm_rig_state_restored`
  - `_depsgraph_update`
  - `tx.retry_cleanup`
  - `_register_pending_arm_rig_cleanup`
- **输入数据**：
  - `arm: bpy.types.Object`（目标 Armature 引用）
- **输出数据**：
  - `yield tx: _ArmRigTransactionContext`（事务上下文）
- **持有的状态**：
  - 全局活跃事务栈 `_ACTIVE_TRANSACTION_STACK`
  - 事务生命周期状态机推进（`CREATED` $\to$ `SNAPSHOTTING` $\to$ `ACTIVE` $\to$ `COMMITTING` $\to$ `COMMITTED` / `ROLLING_BACK` $\to$ `ROLLED_BACK` / `CLEANUP_PENDING` / `FAILED`）
- **允许执行的资源操作**：
  - 无直接 Blender 场景资源增删查改权限；
  - 仅允许驱动下游模块在特定生命周期阶段执行对应资源操作；
  - 允许触发 Dependency Graph 刷新。
- **禁止执行的资源操作**：
  - 严禁直接调用 `bpy.data.objects.new/remove`、`constraints.new/remove` 或集合操作；
  - 严禁篡改骨骼姿态、控制器变换或约束 Influence。
- **异常处理职责**：
  - 拦截业务操作中发生的所有异常；
  - 区分提交前失败（触发回滚与全字段核验）与提交后失败（触发挂起清理）；
  - 维护复合异常链（`raise ... from orig_exc`），杜绝吞匿任何原始异常。
- **生命周期边界**：
  - 入口：受保护业务函数进入 `with _arm_rig_transaction(arm)` 语句；
  - 出口：`finally` 块清空当前事务出栈，并完成 Phase 3 提交清理或挂起登记。

---

### 职责 2：State & Ownership Registry（状态与所有权注册表）

- **当前对应函数/结构**：
  - `_ArmRigTransactionContext` 类 (L1259-L1509)
  - `_ArmRigTransactionState` 枚举 (L163-L174)
  - `register_created_controller(obj: bpy.types.Object)` (L1283-L1301)
  - `register_created_collection(col, initial_parent)` (L1302-L1315)
  - `_PENDING_ARM_RIG_CLEANUPS: Dict[str, _ArmRigTransactionContext]` (L1516-L1519)
  - `_register_pending_arm_rig_cleanup(tx)` (L1522-L1533)
  - `get_pending_arm_rig_cleanup_ids()` (L1535-L1541)
- **当前调用者**：
  - `_arm_rig_transaction`、`_ensure_character_collection`、`_get_or_create_empty`、`setup_arm_ik`
- **当前被调用者**：
  - `uuid.uuid4()`、`bpy.types.Object.as_pointer()`
- **输入数据**：
  - 控制器活体对象、集合活体对象、暂存对象/约束字典记录
- **输出数据**：
  - 已登记所有权列表（`created_controller_objects`, `created_collections`, `stashed_objects`, `stashed_constraints`, `uncleaned_*`）
  - 事务标识 `tx_id`、当前状态 `state`、挂起事务 ID 元组
- **持有的状态**：
  - 单个事务内的物理指针与对象引用所有权账本；
  - 全局已提交待清理事务注册表 `_PENDING_ARM_RIG_CLEANUPS`。
- **允许执行的资源操作**：
  - 只读检查对象和约束的指针与引用属性；
  - 登记、注销内部所有权条目。
- **禁止执行的资源操作**：
  - 严禁在此注册表中直接执行 `bpy.data` 的物理创建或删除；
  - 严禁隐式修改任何场景属性。
- **异常处理职责**：
  - 校验注册条目的合法性（如重复注册抛出 `RuntimeError`，非法状态登记抛出 `RuntimeError`）。
- **生命周期边界**：
  - 事务初始化时建立，随上下文销毁；若进入 `CLEANUP_PENDING` 则生命周期延长至全局注册表中，直至被 `retry_pending_arm_rig_cleanup` 完全释放。

---

### 职责 3：Resource Operations（底层资源操作引擎）

- **当前对应函数/结构**：
  - `_get_or_create_empty` (L1707-L1772)
  - `_ensure_character_collection` (L137-L147)
  - `_find_collection_by_name` (L149-L157)
  - `_find_live_object_by_identity` (L411-L438)
  - 回滚资源删除与恢复段落 (L440-L856)
- **当前调用者**：
  - `setup_arm_ik`、`_arm_rig_transaction`、`reset_arm_ik`
- **当前被调用者**：
  - `bpy.data.objects.new/remove`、`bpy.data.collections.new/remove`、`collection.objects.link/unlink`、`collection.children.link/unlink`、`pbone.constraints.new/remove`
- **输入数据**：
  - 资源名称、显示类型、尺寸、父级对象、目标集合、待恢复快照字典
- **输出数据**：
  - 创建或解析出的活体 `bpy.types.Object`、`bpy.types.Collection`、`bpy.types.Constraint`
- **持有的状态**：
  - 无持久内存状态，直接与 Blender C-API 交互。
- **允许执行的资源操作**：
  - 经协调器或所有权注册表授权的资源创建、删除、重命名、链接与解绑。
- **禁止执行的资源操作**：
  - 严禁脱离所有权授权私自删除同名对象（严禁按名误删！）；
  - 严禁在未登记所有权前向场景链接新建对象；
  - 严禁在回滚时删除非本事务创建的集合或控制器。
- **异常处理职责**：
  - 捕获底层 C-API 包装器失效异常（`ReferenceError`）；
  - 汇总恢复过程中的错误（`restoration_errors: List[str]`）并在操作结束时统一抛出。
- **生命周期边界**：
  - 单次函数调用内即时生效，受外部事务协调器控制。

---

### 职责 4：Arm IK Business Operations（手臂 IK 领域业务操作）

- **当前对应函数/结构**：
  - `setup_arm_ik` (L1799-L2010)
  - `set_hand_ik_target` (L2253-L2414)
  - `set_arm_ik_influence` (L2012-L2042)
  - `reset_arm_ik` (L2044-L2104)
  - `get_arm_ik_state` (L2106-L2178)
  - 输入验证辅助：`_validate_side`, `_validate_vec3`, `_validate_influence`, `_validate_bool`, `_resolve_armature`, `_preflight_arm_ik_parent_transforms`
  - 姿态辅助：`_apply_arm_ik_prebend_hint_side`, `_apply_arm_ik_prebend_hint`
- **当前调用者**：
  - `WholeBodyController`、`PlaygroundCharacterAssembly`、动画管线驱动脚本、测试套件
- **当前被调用者**：
  - `_arm_rig_transaction`、`_get_or_create_empty`、`transform_utils`（矩阵与旋转解算）、`_depsgraph_update`
- **输入数据**：
  - 用户/上层规划器传入的手臂侧向、世界坐标、手部旋转角度、肘部极向坐标、伸展截断标志、Influence 权重
- **输出数据**：
  - 控制器对象字典或实际执行后的状态字典（包含误差、解算长度、实际世界坐标等）
- **持有的状态**：
  - 无持久业务状态；状态保存在场景骨骼与控制器中。
- **允许执行的资源操作**：
  - 计算空间变换并赋值给控制器或骨骼（`location`, `rotation_*`, `influence`, `pole_angle` 等）；
  - 请求事务协调器提供原子保护。
- **禁止执行的资源操作**：
  - 严禁在预检阶段对场景进行任何写入（Phase A/B 绝对零副作用）；
  - 严禁绕开事务直接对场景做不可逆删除。
- **异常处理职责**：
  - 在 Phase A 严格校验所有参数类型与范围，非法时直接拒绝并抛出 `TypeError`/`ValueError`；
  - 允许事务内部异常向外正常传播。
- **生命周期边界**：
  - 请求发起至状态返回，为完整的单次调用周期。

---

### 职责 5：Snapshot & Verification（快照捕获与全字段核验）

- **当前对应函数/结构**：
  - `_snapshot_arm_rig_state(arm)` (L244-L409)
  - `_clone_snapshot_property_value(val)` (L227-L242)
  - `_verify_arm_rig_state_restored(arm, snapshot, active_tx)` (L858-L1257)
- **当前调用者**：
  - `_arm_rig_transaction`
- **当前被调用者**：
  - `_depsgraph_update`、mathutils 对象的深拷贝方法（`copy()`）、`as_pointer()`
- **输入数据**：
  - Armature 对象、已记录的基线快照字典
- **输出数据**：
  - 完整不可变深拷贝快照字典（包含 collections, controllers, pose_bones）
- **持有的状态**：
  - 生成不可变的快照数据结构，供后续比对使用。
- **允许执行的资源操作**：
  - **绝对只读**（Zero Mutation Guarantee）；
  - 严禁对任何 Blender 场景对象、骨骼、集合进行修改；
  - 仅允许触发 `_depsgraph_update` 确保读取到的世界变换为最新求值数据。
- **禁止执行的资源操作**：
  - 严禁修改任何属性；严禁创建或删除任何 Blender 数据。
- **异常处理职责**：
  - 快照生成时若属性读取失败，抛出带详细属性与骨骼名称的 `RuntimeError`；
  - 核验时若发现任何字段偏差（超出 $10^{-5}$ 容差或指针身份不匹配），抛出包含详尽差异列表的 `RuntimeError`。
- **生命周期边界**：
  - 快照在事务进入 `SNAPSHOTTING` 阶段时生成；核验在 `ROLLING_BACK` 阶段结束时执行。

---

### 职责 6：Commit & Cleanup（提交确认与不可逆资源清理）

- **当前对应函数/结构**：
  - `_ArmRigTransactionContext.retry_cleanup()` (L1316-L1509)
  - `retry_pending_arm_rig_cleanup(tx_id: str)` (L1543-L1570)
  - Phase 3 清理触发块 (L1681-L1705)
- **当前调用者**：
  - `_arm_rig_transaction`（提交后阶段）、`retry_pending_arm_rig_cleanup`（外部显式重试）
- **当前被调用者**：
  - `pbone.constraints.remove`、`bpy.data.objects.remove`、`target_coll.remove`（DataBlock 清理）
- **输入数据**：
  - 暂存资源记录列表（`uncleaned_stashed_constraints`, `uncleaned_stashed_objects`）
- **输出数据**：
  - 无（成功时清空未清理列表，失败时抛出异常并置 `CLEANUP_PENDING`）
- **持有的状态**：
  - `cleanup_error`、`uncleaned_*` 资源残留状态。
- **允许执行的资源操作**：
  - 仅允许针对本事务确认暂存的已废弃资源（Doomed Objects, Doomed DataBlocks, Stashed Constraints）执行物理删除；
  - 必须对物理指针与引用存活性做双重核验，严禁删除存活的同名替代物。
- **禁止执行的资源操作**：
  - 严禁删除有外部引用的 DataBlock（`user_count > 0` 必须保留）；
  - 严禁删除事务自建控制器或未暂存的正常资源；
  - 严禁执行场景回滚。
- **异常处理职责**：
  - 记录清理过程中的所有子项失败；
  - 若部分成功、部分失败，严禁标记为完全提交，必须保持 `CLEANUP_PENDING` 并向外抛出异常。
- **生命周期边界**：
  - 逻辑提交后（Phase 2 达成 `COMMITTED`）方可启动；失败时转入挂起注册表，直到重试成功后从注册表移除并结束生命周期。
