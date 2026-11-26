# 03. 资源所有权合同规范（Resource Ownership Contract）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`  
> **性质**：Blender 实体物理身份与所有权分类模型  
> **审计日期**：2026-11-06  

---

## 1. 核心清规：所有权不可推断定理 (Non-Inference Principle)

在 Blender Python (bpy) 环境下，底层 C 内存分配器可能在对象销毁后重新分配相同的虚拟内存地址，或者用户代码可能创建具有相同名称的新对象。因此确立以下铁律：
1. **禁止通过名称（Name）推断所有权**：场景中存在名为 `"HandIK.L"` 或 `"Character"` 的对象，绝不能推断其为本事务所有。
2. **禁止通过快照差集（Snapshot Diff）推断所有权**：快照中不存在但在当前场景中存在的对象，可能是外部并发代码或用户操作创建的，绝不可视为本事务产物。
3. **禁止通过单独的指针整数（Raw Pointer Alone）推断所有权**：指针可能在物理销毁后被内存池回收重用；必须结合原始活体 Python 包装器引用（`obj_ref`）与底层存活指针（`as_pointer()`）联合核验，并确认未触发 `ReferenceError`。

---

## 2. Resource Identity（资源物理身份模型）

针对 Blender 4 大核心实体，建立严格的物理身份定义：

| 实体类型 | 身份判定合同 | 失效与替换检测机制 | 源码实现位置 |
| :--- | :--- | :--- | :--- |
| **Object** | `(obj_ref, obj_ptr == obj_ref.as_pointer(), obj_ref in bpy.data.objects)` | 1. `ReferenceError` 捕获（底层 C 结构已释放）<br>2. 指针比对（防止内存重用错判）<br>3. 活体集合比对（`bpy.data.objects` 包含性） | `_find_live_object_by_identity` (L411-L438) |
| **Constraint** | `(con_ref, con_ptr == con_ref.as_pointer(), con_ref in pbone.constraints)` | 1. `ReferenceError` 捕获（底层约束已销毁）<br>2. 指针一致性比对<br>3. 归属 PoseBone 的约束链包含性验证 | `retry_cleanup` (L1325-L1375)<br>`_rollback_arm_rig_state` (L606-L639) |
| **Collection** | `(col_ref, col_ptr == col_ref.as_pointer(), col_ref.name in bpy.data.collections)` | 1. `ReferenceError` 捕获<br>2. 指针匹配核对<br>3. 场景与全局集合包含性核对 | `_verify_arm_rig_state_restored` (L900-L930)<br>`_rollback_arm_rig_state` (L725-L777) |
| **DataBlock** | `(data_ref, data_ptr == data_ref.as_pointer(), data_ref in bpy.data.<collection>)` | 1. 对应库（如 meshes, curves）中的包含性<br>2. 引用计数 `user_count` 检查（`users > 0` 严禁删除） | `retry_cleanup` (L1442-L1494) |

---

## 3. Relationship Mutation（关系变更模型）

除实体自身存在性外，Blender 场景拓扑变更必须建立双向可逆合同：

| 关系变更类型 | 正向变更路径 | 回滚恢复合同 | 提交后清理合同 |
| :--- | :--- | :--- | :--- |
| **Collection ↔ Object**<br>(成员链接关系) | `col.objects.link(obj)` | 恢复快照记录的所有原始所属集合：<br>1. 补全快照中存在但当前丢失的 link<br>2. 移除当前存在但快照中不存在的 unlink | 随着事务 Doomed 对象物理删除自动脱绑；或保留正常控制器的链接。 |
| **Collection ↔ Collection**<br>(父子集合层级) | `scene.collection.children.link(col)`<br>`parent_col.children.link(col)` | 依据快照记录的 `parent_refs` 与 `child_refs` 物理指针完全对齐恢复父子层级，杜绝集合孤立或错误挂接。 | 若集合为事务创建且已提交，则维持现状；若回滚则解绑全部层级后物理删除。 |
| **Object ↔ Parent**<br>(控制器父级变换) | `obj.parent = parent`<br>`obj.matrix_parent_inverse = M` | 严格恢复快照中的 `parent` 引用及不可变深拷贝的 `matrix_parent_inverse`，消除逆矩阵失真。 | 提交后维持正确父级与逆矩阵。 |
| **Constraint ↔ Target**<br>(约束目标指向) | `con.target = target_obj`<br>`con.pole_target = pole_obj` | 严格恢复快照中记录的 `target` 与 `pole_target` 对象引用及 `subtarget` 骨骼名称字符串。 | 维持有效指向；若指向 Doomed 暂存对象，则必须已在逻辑提交前完成重定向。 |

---

## 4. 5 大资源所有权分类标准

每个资源在事务运行期间必须且只能归属于以下 5 种所有权类别之一：

```
                           Blender 场景内所有资源
                                     │
           ┌─────────────────────────┴─────────────────────────┐
           ▼                                                   ▼
     事务直接感知资源                                     外部与未知资源
           │                                                   │
  ┌────────┼────────┐                                 ┌────────┴────────┐
  ▼        ▼        ▼                                 ▼                 ▼
类别 1    类别 2   类别 3                            类别 4            类别 5
原始已存在  本事务自建 本事务暂存                           外部已登记        所有权不可证明
```

### 类别 1：原始已存在资源（Pre-existing Original Resources）
- **定义**：在事务开启前（`_snapshot_arm_rig_state` 捕获时）已经存在于场景中、且由快照完整记录其物理指针与属性的资源。
- **典型代表**：已存在的 `CharacterArmature`、已存在的 `Character` 集合、原有有效 `HandIK.L`、原有姿态骨骼及既有约束。
- **所有权操作边界**：
  - **允许**：在快照保护下读取属性、临时修改变换、调整约束 Influence；
  - **禁止**：严禁在本事务回滚时物理删除！严禁未暂存前直接覆盖销毁！
  - **回滚责任**：回滚时必须严格依据快照恢复其全部属性、矩阵与关系，恢复后通过全字段比对器核验。

### 类别 2：本事务自建资源（Transaction-Created Resources）
- **定义**：在当前事务生命周期内新分配并立即通过 `register_created_*` 显式登记物理指针的资源。
- **典型代表**：`_get_or_create_empty` 创建的新 Empty 控制器、`_ensure_character_collection` 创建的新集合、`setup_arm_ik` 新建的 IK/COPY_ROTATION 约束。
- **所有权操作边界**：
  - **强制要求**：**先登记所有权，后向场景/集合链接**（Creation-First Registration）；
  - **回滚责任**：回滚时负有 100% 物理清理责任。必须通过物理指针安全删除，绝不留下孤儿对象；
  - **提交责任**：提交后转为合法的持久场景资源。

### 类别 3：本事务暂存资源（Stashed Doomed Resources）
- **定义**：事务运行期间因类型错误或配置冲突而被重命名并从集合脱绑、等待提交后物理销毁的原有资源。
- **典型代表**：非 Empty 类型的旧控制器（`__stashed_doomed_<name>__`）、旧的冲突类型约束（`__stashed_con_<name>_<uuid>__`）。
- **所有权操作边界**：
  - **事务中**：处于隔离状态（脱绑、重命名、Mute 禁用），不可见也不参与解算；
  - **回滚责任**：事务失败回滚时，必须 100% 恢复其原始名称、集合链接、所属骨骼与激活状态；
  - **提交后责任**：事务成功提交后，由 Phase 3 的 `retry_cleanup()` 负责物理销毁（若 DataBlock 用户计数归零则级联删除 DataBlock）。

### 类别 4：外部登记资源（Externally Registered Resources）
- **定义**：由上层模块（如 WBC、Rig 构建器、场景初始化器）创建并传入事务边界的合法外部资源。
- **典型代表**：外部传入的 `armature_obj`、外部预置的 `CharacterRoot`。
- **所有权操作边界**：
  - **只读引用**：事务仅持有只读引用与使用权；
  - **禁止**：严禁修改外部对象的生命周期；严禁修改外部对象的名称或删除；严禁改变其与外部父级的结构关系。

### 类别 5：所有权不可证明资源（Unprovable Ownership Resources）
- **定义**：名称与预期资源相同，但既不在快照中、未在当前事务登记、且物理指针无法匹配任何历史记录的资源。
- **典型代表**：在事务执行期间被外部线程/代码注入的同名 Empty 或同名 Collection。
- **保护清规**：
  - **绝对保护原则**：遇到此类资源，**一律视为不可证明所有权，严禁擅自删除或覆盖**！
  - **回滚行为**：记录命名占用冲突错误（`restoration_errors.append("... name occupied by another object ...")`），触发告警并中止回滚，绝不误伤外部资源。
