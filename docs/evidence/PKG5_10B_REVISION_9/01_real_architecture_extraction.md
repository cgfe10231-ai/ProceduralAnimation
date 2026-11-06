# 01. 真实架构提取报告（Real Architecture Extraction）

> **任务**：PKG-5 / Task 10-B-9 (Architecture-First Transaction Consolidation)  
> **代码基准**：`src/rig/arm_ik.py`（SHA: `6d9fd089c4a42600c397889e4e5449f9034975d9`）  
> **性质**：只读静态与动态架构提取（Zero Production Mutation）  
> **审计日期**：2026-11-06  

---

## 1. 概述与提取范围

本报告基于 `src/rig/arm_ik.py`（共 2414 行）以及其实际跨模块调用者（`src/motion/whole_body_controller.py`、`src/scene/playground_character_assembly.py`、`run_arm_ik_prototype.py` 以及测试套件），对当前真实存在的符号、入口、资源操作、快照边界与异常出口进行逐行定位核实。

---

## 2. 公开 Arm IK API 清单

以下为 `src/rig/arm_ik.py` 向外暴露的正式公共 API（在 `src/rig/__init__.py` 中导出并在生产管线中消费）：

| API 函数名 | 源码定位 | 签名与参数 | 外部调用者 | 事务保护状态 |
| :--- | :--- | :--- | :--- | :--- |
| `setup_arm_ik` | L1799-L2010 | `(armature_obj=None, initial_influence=0.0) -> Dict[str, bpy.types.Object]` | `whole_body_controller.py:303`<br>`playground_character_assembly.py:223`<br>`run_arm_ik_prototype.py:190`<br>测试套件 | 受 `_arm_rig_transaction` 保护 |
| `set_hand_ik_target` | L2253-L2414 | `(armature_obj, side, world_xyz, hand_rotation_deg=None, pole_world_xyz=None, clamp_reach=True, influence=1.0) -> dict` | `whole_body_controller.py:424`<br>测试套件 | 受 `_arm_rig_transaction` 保护（Phase C/D） |
| `set_arm_ik_influence` | L2012-L2042 | `(armature_obj=None, side="BOTH", influence=1.0) -> None` | `whole_body_controller.py:434`<br>`run_arm_ik_prototype.py:191`<br>测试套件 | 受 `_arm_rig_transaction` 保护 |
| `reset_arm_ik` | L2044-L2104 | `(armature_obj=None) -> None` | `whole_body_controller.py:657`<br>`playground_character_assembly.py:224, 396, 922, 1301`<br>测试套件 | **无事务保护**（直接修改场景，仅刷新 depsgraph） |
| `get_arm_ik_state` | L2106-L2178 | `(armature_obj, side: str) -> dict` | `whole_body_controller.py:524, 601`<br>`set_hand_ik_target:2408`<br>测试套件 | 只读函数（触发 `_depsgraph_update`） |
| `get_pending_arm_rig_cleanup_ids` | L1535-L1541 | `() -> Tuple[str, ...]` | 运行时诊断与测试套件 | 只读访问 `_PENDING_ARM_RIG_CLEANUPS` |
| `retry_pending_arm_rig_cleanup` | L1543-L1570 | `(tx_id: str) -> None` | 运行时重试与测试套件 | 驱动特定挂起事务的 `tx.retry_cleanup()` |

---

## 3. 内部事务入口与调用点

所有事务均由上下文管理器 `_arm_rig_transaction(arm: bpy.types.Object)`（L1605-L1705）统一管理：

| 入口位置 | 调用函数 | 触发条件 | 嵌套上下文行为 |
| :--- | :--- | :--- | :--- |
| `src/rig/arm_ik.py:1823` | `setup_arm_ik` | 配置或幂等更新控制器与约束 | 若外部无事务，创建外层事务；若已有同一 Armature 事务，复用；若跨 Armature 则拒绝。 |
| `src/rig/arm_ik.py:2029` | `set_arm_ik_influence` | 更新约束 Influence 权重 | 同上 |
| `src/rig/arm_ik.py:2375` | `set_hand_ik_target` | 经 Phase A 验证与 Phase B 预检通过后进入 | 同上；若触发内部 `setup_arm_ik`（L2377），形成同 Armature 可重入复用嵌套。 |

---

## 4. Blender 资源操作位置清单（CRUD 完整审计）

### 4.1 资源创建（Create / New）
1. **Character 集合创建**：
   - 定位：`src/rig/arm_ik.py:142`（`bpy.data.collections.new("Character")`）
   - 条件：`bpy.data.collections.get("Character") is None`
   - 登记：L145 `_ACTIVE_TRANSACTION_STACK[-1].register_created_collection(col, initial_parent=scene.collection)`
2. **Empty 控制器创建**：
   - 定位：`src/rig/arm_ik.py:1750`（`bpy.data.objects.new(name, None)`）
   - 条件：控制器不存在，或原有同名对象为非 Empty 类型被暂存。
   - 登记：L1753 `active_tx.register_created_controller(obj)`（**创建后立即登记所有权，早于集合链接**）
3. **IK 约束创建**：
   - 定位：`src/rig/arm_ik.py:1934`（`p_fore.constraints.new(type="IK")`）
   - 条件：骨骼上不存在名为 `ArmIK.<side>` 的 IK 约束。
4. **COPY_ROTATION 约束创建**：
   - 定位：`src/rig/arm_ik.py:1993`（`p_hand.constraints.new(type="COPY_ROTATION")`）
   - 条件：骨骼上不存在名为 `HandRotation.<side>` 的 COPY_ROTATION 约束。

### 4.2 资源删除（Delete / Remove）
1. **事务自建控制器回滚删除**：
   - 定位：`src/rig/arm_ik.py:461`（`bpy.data.objects.remove(live_obj, do_unlink=True)`）
   - 条件：回滚阶段遍历 `active_tx.created_controller_objects`，指针与活体对象一致。
2. **非事务下非 Empty 冲突对象直接删除**：
   - 定位：`src/rig/arm_ik.py:1745`（`bpy.data.objects.remove(obj, do_unlink=True)`）
   - 条件：无活跃事务栈且同名对象为非 Empty 类型（仅发生于未受事务保护的独立调用，属于历史遗留分支）。
3. **暂存 Doomed 对象提交后清理**：
   - 定位：`src/rig/arm_ik.py:1424`（`bpy.data.objects.remove(target_obj, do_unlink=True)`）
   - 条件：Phase 3 提交后调用 `retry_cleanup()`，比对指针找到存活 doomed 对象后删除。
4. **暂存 Doomed 数据块（DataBlock）提交后清理**：
   - 定位：`src/rig/arm_ik.py:1483`（`target_coll.remove(target_data, do_unlink=True)`）
   - 条件：暂存对象删除成功且对应底层数据块（如 Mesh、Curve）用户引用计数归零（`user_count == 0`）。
5. **事务期间新增约束回滚删除**：
   - 定位：`src/rig/arm_ik.py:590`（`pbone.constraints.remove(con)`）
   - 条件：回滚阶段比对骨骼约束，不在快照 `saved_con_refs` 集合内的约束被物理移除。
6. **暂存约束提交后物理清理**：
   - 定位：`src/rig/arm_ik.py:1376`（`pbone.constraints.remove(target)`）
   - 条件：Phase 3 提交后调用 `retry_cleanup()`，验证原始引用及物理指针完全匹配后物理删除。
7. **非事务下非目标类型约束直接删除**：
   - 定位：`src/rig/arm_ik.py:1911, 1930, 1971, 1990`（`pbone.constraints.remove(con)`）
   - 条件：无活跃事务栈时遇到同名但类型错误的约束直接移除（历史遗留分支）。
8. **事务自建集合回滚删除**：
   - 定位：`src/rig/arm_ik.py:743`（`bpy.data.collections.remove(target_col)`）
   - 条件：回滚阶段遍历 `active_tx.created_collections`，解除所有父级与场景链接后彻底删除。

### 4.3 资源链接与解绑（Link / Unlink）
1. **集合链接至场景**：
   - `src/rig/arm_ik.py:143`：`scene.collection.children.link(col)`
   - `src/rig/arm_ik.py:789`：回滚时恢复集合至场景子集合
2. **集合解绑**：
   - `src/rig/arm_ik.py:739`：回滚删除自建集合前从所有父集合解绑（`p_col.children.unlink(target_col)`）
   - `src/rig/arm_ik.py:742`：回滚删除自建集合前从场景集合解绑（`scene.collection.children.unlink(target_col)`）
3. **集合间父子层级链接**：
   - `src/rig/arm_ik.py:809`：回滚时恢复原父集合对 Character 集合的链接（`parent.children.link(col)`）
   - `src/rig/arm_ik.py:829`：回滚时恢复 Character 集合对其子集合的链接（`col.children.link(child)`）
4. **对象链接至集合**：
   - `src/rig/arm_ik.py:1755, 1768`：控制器创建或复用时链接至 Character 集合
   - `src/rig/arm_ik.py:517, 552, 850`：回滚时恢复原对象链接至对应集合
5. **对象从集合解绑**：
   - `src/rig/arm_ik.py:1741`：暂存 Doomed 对象时从所有所属集合解绑
   - `src/rig/arm_ik.py:521`：回滚时将控制器从事务多链接的集合中解绑
6. **约束 Target 与 Pole Target 绑定**：
   - `src/rig/arm_ik.py:1939`：`ik_con.target = ik_obj`
   - `src/rig/arm_ik.py:1940`：`ik_con.pole_target = pole_obj`
   - `src/rig/arm_ik.py:1997`：`rot_con.target = ik_obj`
   - `src/rig/arm_ik.py:682, 686`：回滚时恢复快照记录的 target 与 pole_target
7. **控制器父级绑定（Parent）**：
   - `src/rig/arm_ik.py:1760`：`obj.parent = parent`（`matrix_parent_inverse = Identity(4)`）
   - `src/rig/arm_ik.py:523, 524`：回滚时恢复快照记录的 `parent` 与 `matrix_parent_inverse`

### 4.4 资源重命名（Rename）
1. **Doomed 对象隔离重命名**：
   - `src/rig/arm_ik.py:1739`：`obj.name = f"__stashed_doomed_{name}__"`
2. **控制器名称回滚恢复**：
   - `src/rig/arm_ik.py:512, 548`：恢复原始控制器名称 `live_original.name = original_name`
3. **Doomed 约束隔离重命名**：
   - `src/rig/arm_ik.py:1899, 1918, 1959, 1978`：`con.name = f"__stashed_con_{orig_name}_{uuid.uuid4().hex[:6]}"`
4. **约束名称回滚恢复**：
   - `src/rig/arm_ik.py:598`：`c.name = item["orig_name"]`（暂存约束原名恢复）
   - `src/rig/arm_ik.py:653`：`con.name = sc["name"]`（快照原约束名恢复）
5. **Character 集合名称回滚恢复**：
   - `src/rig/arm_ik.py:781`：`col.name = orig_name`

---

## 5. 快照与验证调用点

1. **`_snapshot_arm_rig_state(arm)` 调用点**：
   - `src/rig/arm_ik.py:1629`：外层事务开启时创建基线不可变深拷贝快照（`SNAPSHOTTING` 阶段）。
   - `src/rig/arm_ik.py:868`：回滚完成后在 `_verify_arm_rig_state_restored()` 中获取当前活体状态进行全量逐字段对比。
2. **`_verify_arm_rig_state_restored(arm, tx.snapshot, active_tx=tx)` 调用点**：
   - `src/rig/arm_ik.py:1658`：回滚操作执行完毕且 `_depsgraph_update()` 后，强制执行核验。核验失败抛出 `RuntimeError`，阻断状态转入 `ROLLED_BACK` 并标记为 `FAILED`。

---

## 6. 异常出口与清理挂起入口

1. **Phase A 输入与预检异常（Zero Mutation 保证）**：
   - `_validate_side`、`_validate_vec3`、`_validate_influence`、`_validate_bool` 抛出 `TypeError` / `ValueError`。
   - `_preflight_arm_ik_parent_transforms` 抛出非共形变换异常或找不到 Armature 错误。
   - **特点**：此时尚未进入事务上下文，未触碰任何场景数据，天然零副作用。
2. **门禁阻断异常**：
   - `src/rig/arm_ik.py:1598`（`_assert_arm_rig_cleanup_gate`）：存在未决的 `CLEANUP_PENDING` 事务时阻断新写入。
   - `src/rig/arm_ik.py:1612`：跨 Armature 嵌套事务抛出 `RuntimeError`。
3. **Phase 1~2 突变与提交准备异常（回滚出口）**：
   - `src/rig/arm_ik.py:1648-1675`：若在 `COMMITTED` 达成之前发生异常，进入 `ROLLING_BACK`。
   - 执行 `_rollback_arm_rig_state()` $\to$ `_verify_arm_rig_state_restored()` $\to$ `ROLLED_BACK`。
   - 若回滚核验也失败，则包装复合异常 `RuntimeError("... AND rollback verification failed with ...")` 并置 `FAILED`。
4. **Phase 3 提交后不可逆清理异常（`CLEANUP_PENDING` 入口）**：
   - `src/rig/arm_ik.py:1696-1704`：事务逻辑已 `COMMITTED`，在执行 `retry_cleanup()` 时发生异常。
   - 事务状态变更为 `CLEANUP_PENDING`，保存 `cleanup_error`。
   - 调用 `_register_pending_arm_rig_cleanup(tx)` 登记入全局表 `_PENDING_ARM_RIG_CLEANUPS`。
   - 抛出 `RuntimeError("Arm rig transaction committed, but post-commit cleanup failed...")` 提醒调用者。

---

## 7. 跨模块实际调用拓扑

```
[src/motion/framework.py] (PlannedHandTarget)
          │
          ▼
[src/motion/kinematic_bridge.py] (KinematicBridge)
          │
          ▼
[src/motion/whole_body_controller.py] (WholeBodyController)
   ├── setup_arm_ik(arm, 0.0)             (L303)
   ├── set_hand_ik_target(arm, side, ...)   (L424)
   ├── set_arm_ik_influence(arm, side, 0.0) (L434)
   ├── get_arm_ik_state(arm, side)          (L524, L601)
   └── reset_arm_ik(arm)                    (L657)
          │
          ▼
[src/rig/arm_ik.py] (Core API)
   ├── _arm_rig_transaction (Transaction Coordinator)
   │     ├── _snapshot_arm_rig_state
   │     ├── _rollback_arm_rig_state
   │     └── _verify_arm_rig_state_restored
   ├── _get_or_create_empty
   └── transform_utils (Parent Inversion & Conformal Check)
```
