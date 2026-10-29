# ProceduralAnimation — Production Interface Audit — R3
## Rig, Foot Contact & IK Execution Contract Audit (底层绑定、足部接触与 IK 执行合同审计报告)

### 0. 审计基准与工作区状态检查
* **Repository**: `cgfe10231-ai/ProceduralAnimation`
* **Branch**: `master`
* **Baseline Commit SHA**: `ff7232d2a77335d64091576d8f5293c097044d00`
* **复核闭环阶段**: `R3-CLOSE` (全生命周期合同闭环与副作用纠错)
* **Working Tree Check**: 除受保护的未跟踪补丁 `P2_R1_recovery.patch` 外，工作树严格干净。
* **审计性质确认**: 本次审计属于**完全只读**的底层绑定、足部接触与 IK 执行合同专项复核，未对生产源码、测试用例、配置或场景资产做任何修改，未提前开发 Phase 7B，未重新实现任何 IK 算法。

---

### 1. 文件概况 (File Summaries & Symbol Enumeration)

| 审计代号 | 生产源码文件路径 | 规模 | 核心职责 | 生产方法 / 函数 (物理行号核准) |
| :--- | :--- | :---: | :--- | :--- |
| **R3-A** | [`src/rig/foot_contact.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/foot_contact.py) | 333 行 | 足部世界坐标接触锁定、地面支撑稳定性评估与微米级漂移监测 | `_ensure_ik_controls()` (L49–L56)<br>`_classify_reach()` (L59–L67)<br>`lock_foot_contact()` (L70–L146)<br>`unlock_foot_contact()` (L149–L191)<br>`evaluate_foot_support()` (L194–L307)<br>`get_foot_support_state()` (L310–L312)<br>`move_character_root_with_support()` (L315–L333) |
| **R3-B** | [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py) | 404 行 | 下肢双骨反向运动学 (Two-Bone IK) 约束配置、膝盖极向防翻转与足部目标应用 | `_resolve_armature()` (L42–L47)<br>`_ensure_character_collection()` (L50–L56)<br>`_get_or_create_empty()` (L59–L85)<br>`_apply_ik_prebend_hint()` (L88–L109)<br>`setup_leg_ik()` (L112–L208)<br>`reset_leg_ik()` (L211–L233)<br>`get_leg_ik_state()` (L236–L292)<br>`set_foot_ik_target()` (L295–L404) |
| **R3-C** | [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py) | 510 行 | 上肢双骨反向运动学与手部姿态约束配置、手腕可达性检测与约束权重调制 | `_resolve_armature()` (L59–L65)<br>`_ensure_character_collection()` (L68–L75)<br>`_get_or_create_empty()` (L78–L105)<br>`_apply_arm_ik_prebend_hint()` (L108–L131)<br>`setup_arm_ik()` (L134–L240)<br>`set_arm_ik_influence()` (L243–L269)<br>`reset_arm_ik()` (L272–L312)<br>`get_arm_ik_state()` (L315–L389)<br>`set_hand_ik_target()` (L392–L510) |

---

### 2. 逐方法检查表 (Method-by-Method Inspection Tables)

#### 2.1 R3-A: [`src/rig/foot_contact.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/foot_contact.py)

| 生产函数名 | 源码物理行号 | 输入参数与签名核准 | 输出结果 | 失败与异常处理 | 状态流转、实际写入与副作用 (R3-CLOSE 纠正) | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `_ensure_ik_controls()` | L49–L56 | `arm: bpy.types.Object, side: str` | `Tuple[bpy.types.Object, bpy.types.Object]` (`ik_obj`, `pole_obj`) | 若控制器不存在则自动触发 `setup_leg_ik(arm)` | 保证控制器对象存在 | `NO_ISSUE` |
| `_classify_reach()` | L59–L67 | `distance: float, max_reach: float = MAX_LEG_REACH` | `Tuple[bool, bool, str]` (`strictly_in_reach`, `is_reachable`, `status`) | 阈值比较，不抛异常 | 状态分级判定纯计算逻辑 | `NO_ISSUE` |
| `lock_foot_contact()` | L70–L146 | `armature_obj: Optional[bpy.types.Object], side: str, contact_world_xyz: Optional[Tuple[float, float, float]] = None, target_rotation_deg: Optional[Tuple[float, float, float]] = None` | `dict` (调用 `evaluate_foot_support`) | 校验 side 必须为 'L'/'R'，非法时抛出 `ValueError` | **解耦父级并写入锁定点**：将 `FootIK` 与 `KneePole` 解绑为绝对世界空间 (`parent = None`)，在 Empty 上写入锁定元数据快照 | `NO_ISSUE` (严格遵守解耦世界空间原则) |
| `unlock_foot_contact()` | L149–L191 | `armature_obj: Optional[bpy.types.Object], side: str, reparent_to_root: bool = True` | `dict` (调用 `get_foot_support_state`) | 校验 side 必须为 'L'/'R' | **默认重新绑定父级**：置 `is_locked = False`；默认形参 `reparent_to_root=True` 重新将控制器绑定为 `CharacterRoot` 的子物体（违反门禁 Rule 7）；旋转赋值未做父矩阵逆变换；未清理 `locked_ankle_world_xyz` 等历史元数据 | **CONTRACT_GAP / ARCHITECTURAL_VIOLATION** (违反门禁 Rule 7，详见 FIND-R3-01 与 FIND-R3-03) |
| `evaluate_foot_support()` | L194–L307 | `armature_obj: Optional[bpy.types.Object], side: str` | `dict` (包含 `is_locked`, `reach_status`, 骨骼/控制器/网格世界漂移量及膝盖弯曲度) | 纯几何计算不抛异常 | **严重未声明副作用 (R3-CLOSE 纠正)**：**绝非纯只读！** 函数内部执行 7 项强写入：<br>1. 改写两侧小腿姿态骨骼 `shin.L/R` 旋转 (`_apply_ik_prebend_hint`)；<br>2. 两次触发全场景依赖图更新 (`bpy.context.view_layer.update`)；<br>3. 锁定状态下强行解绑控制器父级 (`parent = None`)；<br>4. 强制覆写 `ik_obj.location` 回到锁定踝点；<br>5. 强制覆写 `ik_obj.rotation_euler`；<br>6. 强制解绑 `pole_obj.parent`；<br>7. 强制根据髋骨刷新 `pole_obj.location`。充当了未声明的锁态强制维持器 | **CONTRACT_GAP** (接口强副作用未声明，见 FIND-R3-04) |
| `get_foot_support_state()` | L310–L312 | `armature_obj: Optional[bpy.types.Object], side: str` | `dict` | 委托 `evaluate_foot_support(armature_obj, side)` | 表面为状态查询，但在内部同样间接触发上述 7 项强写入 | **CONTRACT_GAP** (受 FIND-R3-04 波及) |
| `move_character_root_with_support()` | L315–L333 | `armature_obj: Optional[bpy.types.Object], new_root_world_xyz: Tuple[float, float, float]` | `Dict[str, dict]` (返回包含 "L" 与 "R" 的支撑评估字典) | 若 `CharacterRoot` 不存在抛出 `RuntimeError` | 历史遗留辅助函数，仅平移根节点，未处理旋转；主执行链已迁移至 WBC | `NO_ISSUE` (遗留兼容接口) |

#### 2.2 R3-B: [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py)

| 生产函数名 | 源码物理行号 | 输入参数与签名核准 | 输出结果 | 失败与异常处理 | 状态流转、实际写入与生命周期状态 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `_resolve_armature()` | L42–L47 | `armature_obj: Optional[bpy.types.Object]` | `bpy.types.Object` | 找不到骨骼对象时抛出 `RuntimeError` | 全局对象解析器 | `NO_ISSUE` |
| `_ensure_character_collection()` | L50–L56 | `scene: Optional[bpy.types.Scene] = None` | `bpy.types.Collection` | 自动创建或获取 `Character_Rig` 集合 | 场景层级管理 | `NO_ISSUE` |
| `_get_or_create_empty()` | L59–L85 | `name: str, display_type: str, display_size: float, parent: Optional[bpy.types.Object], collection: bpy.types.Collection` | `bpy.types.Object` | 创建或获取 Empty 对象 | 控制器物体生成底座 | `NO_ISSUE` |
| `_apply_ik_prebend_hint()` | L88–L109 | `arm: bpy.types.Object` | `None` | 静默容错，若骨骼不存在则安全跳过 | 为膝关节提供 $-0.05$ rad 前屈诱导，改写 `shin.L/R` 骨骼局部旋转 | `NO_ISSUE` |
| `setup_leg_ik()` | L112–L208 | `armature_obj: Optional[bpy.types.Object] = None` | `Dict[str, bpy.types.Object]` | 幂等清除已有约束后重建；根据大腿骨朝向自适应校验极向角 ($\pm 90^\circ$) | **初始化挂载父级**：创建控制器并强制设置 `parent = root_obj` (L127, L134)，控制器世界坐标受 Root 位姿影响，形成非世界空间初始态 | **CONTRACT_GAP** (全生命周期违规 FIND-R3-01 组成部分) |
| `reset_leg_ik()` | L211–L233 | `armature_obj: Optional[bpy.types.Object] = None` | `None` | 缺失对象时安全容错 | **重置恢复父级挂载**：强制重设 `parent = root_obj` (L221, L227)；重置局部坐标；仅置 `is_locked = False`，未清除历史快照元数据 | **CONTRACT_GAP** (全生命周期违规 FIND-R3-01 及元数据残留 FIND-R3-03 组成部分) |
| `get_leg_ik_state()` | L236–L292 | `armature_obj: Optional[bpy.types.Object], side: str` | `dict` (包含骨骼世界点、目标误差、膝盖屈曲角度、最低离地高度) | 校验 side 非法抛 `ValueError` | 只读测量函数，为 WBC 与接触模型提供底层几何数据 | `NO_ISSUE` |
| `set_foot_ik_target()` | L295–L404 | `armature_obj: Optional[bpy.types.Object], side: str, world_xyz: Tuple[float, float, float], foot_rotation_deg: Optional[Tuple[float, float, float]] = None, clamp_reach: bool = True, clamp_ground: bool = True` | `dict` (包含 requested/applied 位置、超限标记及最新 IK 测量状态) | 若 `ik_obj["is_locked"]` 为 True 抛出 `RuntimeError` 拒绝写入；`clamp_ground=True` 时硬编码根高程导致下坡截断；父级非空时直接将世界欧拉角赋给局部属性产生偏角 | 写入 `FootIK` 与 `KneePole` 变换矩阵并驱动场景更新 | **CONTRACT_GAP** (地面截断缺陷 FIND-R3-02；父级旋转未反解 FIND-R3-01) |

#### 2.3 R3-C: [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)

| 生产函数名 | 源码物理行号 | 输入参数与签名核准 | 输出结果 | 失败与异常处理 | 状态流转、实际写入与生命周期状态 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `_resolve_armature()` | L59–L65 | `armature_obj: Optional[bpy.types.Object]` | `bpy.types.Object` | 找不到骨骼对象时抛出 `RuntimeError` | 全局对象解析器 | `NO_ISSUE` |
| `_ensure_character_collection()` | L68–L75 | `scene: Optional[bpy.types.Scene] = None` | `bpy.types.Collection` | 自动创建或获取 `Character_Rig` 集合 | 场景层级管理 | `NO_ISSUE` |
| `_get_or_create_empty()` | L78–L105 | `name: str, display_type: str, display_size: float, parent: Optional[bpy.types.Object], collection: bpy.types.Collection` | `bpy.types.Object` | 创建或获取 Empty 对象 | 控制器物体生成底座 | `NO_ISSUE` |
| `_apply_arm_ik_prebend_hint()` | L108–L131 | `arm: bpy.types.Object` | `None` | 静默容错，若骨骼不存在则跳过 | 提供 $+0.05$ rad 肘关节前屈诱导 | `NO_ISSUE` |
| `setup_arm_ik()` | L134–L240 | `armature_obj: Optional[bpy.types.Object] = None, initial_influence: float = 0.0` | `Dict[str, bpy.types.Object]` | 幂等清除并重建两骨 IK 约束；肘关节严格限制在局部 X 轴 ($0^\circ \sim 150^\circ$) 单自由度铰链 | 配置手臂两骨 IK 与手腕世界旋转拷贝，控制器初始挂载 `parent = root_obj`，初始 influence 为 0.0 | `NO_ISSUE` (上肢初始挂载符合 FK 摆动基准) |
| `set_arm_ik_influence()` | L243–L269 | `armature_obj: Optional[bpy.types.Object] = None, side: str = "BOTH", influence: float = 1.0` | `None` | 截断 `influence` 在 $[0.0, 1.0]$；校验 side 非法抛 `ValueError` | 平滑调制上肢 IK/FK 权重 | `NO_ISSUE` |
| `reset_arm_ik()` | L272–L312 | `armature_obj: Optional[bpy.types.Object] = None` | `None` | 安全容错 | 将手臂 IK 约束权重重置为 0.0，骨骼与控制器归位，重新挂载 `parent = root_obj` | `NO_ISSUE` |
| `get_arm_ik_state()` | L315–L389 | `armature_obj: Optional[bpy.types.Object], side: str` | `dict` (包含肩膀/手肘/手腕骨骼点、目标误差、三维朝向误差、屈曲角度及权重) | 校验 side 非法抛 `ValueError` | 只读测量，为 WBC 提供上肢几何遥测与超限数据 | `NO_ISSUE` |
| `set_hand_ik_target()` | L392–L510 | `armature_obj: Optional[bpy.types.Object], side: str, world_xyz: Tuple[float, float, float], hand_rotation_deg: Optional[Tuple[float, float, float]] = None, pole_world_xyz: Optional[Tuple[float, float, float]] = None, clamp_reach: bool = True, influence: float = 1.0` | `dict` (包含 requested/applied 位置、可达性与超限截断标记及最新 IK 测量状态) | 校验 side；球形截断超限目标；父级非空时正确执行逆矩阵坐标与旋转变换 | 独占写入 `HandIK` 与 `ElbowPole`，同步更新约束权重 | `NO_ISSUE` (算法设计严密，父矩阵反解逻辑完整) |

---

### 3. 控制器全生命周期状态流转与跨模块调用核对 (R3-CLOSE-01 & R3-D)

```mermaid
stateDiagram-v2
    [*] --> Setup: setup_leg_ik() / setup_arm_ik()
    state "1. 初始化挂载态 (Parented to Root)" as Setup {
        note right of Setup: parent = CharacterRoot<br/>local_xyz = (±0.09, 0, 0.07)<br/>world_xyz 随 Root 移动与旋转
    }

    Setup --> UnlockedSwing: 行走开始 / Swing 摆动 (WBC.execute_frame)
    state "2. 摆动跟踪态 (Swing Phase)" as UnlockedSwing {
        note right of UnlockedSwing: set_foot_ik_target()<br/>若 parent != None 则执行位置逆变换<br/>旋转未反解直接赋值 (FIND-R3-01)
    }

    UnlockedSwing --> LockedStance: 着地锁定 (WBC: foot_tgt.is_locked)
    state "3. 绝对世界锁定态 (World-Space Stance)" as LockedStance {
        note right of LockedStance: lock_foot_contact()<br/>parent = None<br/>matrix_parent_inverse = Identity(4)<br/>evaluate_foot_support() 强行维持锁定 (FIND-R3-04)
    }

    LockedStance --> UnlockedSwing_WBC: 离地解锁 (WBC 显式 reparent=False)
    state "4. 世界空间自由摆动态 (Pure World Swing)" as UnlockedSwing_WBC {
        note right of UnlockedSwing_WBC: parent = None<br/>set_foot_ik_target() 走直接赋值分支
    }

    LockedStance --> Setup: 离地解锁 (外部/默认 reparent=True)
    note right of LockedStance: unlock_foot_contact(reparent=True)<br/>父级被重新挂回 CharacterRoot! (违规回退)

    UnlockedSwing_WBC --> Setup: 动作重置 (Bridge/WBC.reset_all_controls)
    LockedStance --> Setup: 动作重置 (reset_leg_ik)
    note right of Setup: reset_leg_ik() 再次强制挂回 CharacterRoot!<br/>周期性破坏恒定世界空间规则
```

#### R3-CLOSE-01 核心生命周期核验结论：
1. **是否存在“一处修复世界空间，另一处又恢复旧父级”的循环违规？**
   - **事实确认：绝对存在！**
   - `lock_foot_contact()` (L110, L121) 执行 `parent = None` 将控制器剥离至绝对世界空间；
   - 但是：`unlock_foot_contact()` 的默认参数 `reparent_to_root: bool = True` (L152, L172)、`reset_leg_ik()` (L221, L227) 以及 `setup_leg_ik()` (L127, L134)，均显式执行 `ik_obj.parent = root_obj` 和 `pole_obj.parent = root_obj`；
   - 实际调用链表明：当 `KinematicBridgeExecutor.reset()` $\to$ `WholeBodyController.reset_all_controls()` $\to$ `reset_leg_ik()` 被调用时，无论此前控制器如何维持世界空间，都会被无条件刷回 `CharacterRoot` 的子级。这直接构成了对 [`docs/ARCHITECTURE_CHANGE_GATE.md:73`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md#L73) 清规第七条（控制器在动画全生命周期内必须恒定保持在绝对世界空间 `parent = None`）的系统性违规。

---

### 4. 详细审计缺陷与合同缺口分析

#### FIND-R3-01: 控制器生命周期动态父级违规循环，且父级非空时 `set_foot_ik_target` 姿态未反解产生旋转偏差
* **Finding ID**: `FIND-R3-01`
* **Source Files**:
  - `src/rig/foot_contact.py`
  - `src/rig/ik.py`
* **Function**:
  - `unlock_foot_contact()` (`foot_contact.py:149–191`)
  - `setup_leg_ik()` (`ik.py:112–208`)
  - `reset_leg_ik()` (`ik.py:211–233`)
  - `set_foot_ik_target()` (`ik.py:295–404`)
* **Exact Line Range**:
  - `foot_contact.py`: Line 152, Lines 170–179
  - `ik.py`: Lines 127–134, Lines 220–228, Lines 380–384
* **Trigger**:
  1. 调用 `unlock_foot_contact(arm, side)` 未显式传入 `reparent_to_root=False`；
  2. 调用 `reset_leg_ik()` 或 `setup_leg_ik()` 重置系统；
  3. 控制器处于父级非空状态下，角色 Root 存在非零旋转（偏航、俯仰或倾斜），并调用 `set_foot_ik_target()`。
* **Actual Behavior**:
  1. `setup_leg_ik()` 与 `reset_leg_ik()` 强制设置 `ik_obj.parent = root_obj`；`unlock_foot_contact()` 默认参数将控制器重新挂载回 Root，与 `lock_foot_contact()` 的 `parent = None` 构成跨生命周期动态父级切换闭环，直接违反门禁清规第七条；
  2. 在父级非空时，`set_foot_ik_target()` 行 375–378 对位置执行了逆变换，但在行 380–384 中，`foot_rotation_deg` 却直接以世界欧拉角赋值给 `ik_obj.rotation_euler`（未进行局部旋转矩阵反解）。导致脚部实际世界旋转变成 $R_{\text{parent}} \cdot R_{\text{world}}$，产生严重姿态偏角。
* **Evidence**:
  ```python
  # src/rig/foot_contact.py:152, 172
  def unlock_foot_contact(..., reparent_to_root: bool = True):
      if reparent_to_root and root_obj is not None:
          ik_obj.parent = root_obj

  # src/rig/ik.py:221
  if root_obj is not None:
      ik_obj.parent = root_obj

  # src/rig/ik.py:380-384 (对比 arm_ik.py:468 的矩阵反解，此处缺失)
  if foot_rotation_deg is not None:
      rx, ry, rz = (math.radians(v) for v in foot_rotation_deg)
      ik_obj.rotation_euler = Euler((rx, ry, rz), "XYZ")
  ```
* **Affected Callers**:
  - `WholeBodyController.reset_all_controls()`
  - `KinematicBridgeExecutor.reset()`
  - `MotionPlanner.execute()`
  - 遗留行走动作与测试脚本。
* **Contract Violation**:
  - 违反 `docs/ARCHITECTURE_CHANGE_GATE.md:73` 恒定世界空间清规；
  - 违反世界旋转输入数据合同。
* **Repair Boundary**:
  1. 统一 `setup_leg_ik`、`reset_leg_ik`、`unlock_foot_contact`，彻底废弃动态 reparent，全生命周期锁定 `parent = None`；
  2. 在 `set_foot_ik_target` 中防御性补齐类似于 `arm_ik.py:468` 的逆旋转转换矩阵逻辑。
* **Evidence Grade**:
  - 动态父级循环与代码行静态确证：`STATIC_CONFIRMED`
  - 旋转偏差代码存在性确证：`STATIC_CONFIRMED`
  - 非零偏航下具体偏差数值的运行测试：`UNVERIFIED / RUNTIME PENDING`
* **Blocks Further Development**: `YES` (门禁清规强制要求，且阻碍 7B 全身动力学坐标系统一)

---

#### FIND-R3-02: `set_foot_ik_target` 地面防穿透硬编码根节点高程，阻断非平整 3D 地形下潜
* **Finding ID**: `FIND-R3-02`
* **Source File**: `src/rig/ik.py`
* **Function**: `set_foot_ik_target()`
* **Exact Line Range**: Lines 334–346
* **Trigger**: 调用 `set_foot_ik_target()` 时开启 `clamp_ground=True`（默认值即为 `True`），且目标着地点低于当前 `CharacterRoot.location.z`（如下坡、走下台阶或下探坑洞）。
* **Actual Behavior**:
  行 335–336 硬编码从 `root_obj.matrix_world.translation.z` 获取 `ground_z`。当下坡时，目标足部高程必然低于根节点高程，此时函数错误触发防穿透，强制将脚底拉升截断至 `root_obj.z + 0.07`m，导致脚部悬空且无法踩实下坡地面。
  为规避此底层缺陷，生产代码中 `TerrainWalkAction` 不得不全流程强制传递 `clamp_ground=False`（见 `terrain_walk.py` 行 805, 813, 840, 847, 874, 932）。
* **Evidence**:
  ```python
  # src/rig/ik.py:334-336
  root_obj = arm.parent or bpy.data.objects.get("CharacterRoot")
  ground_z = root_obj.matrix_world.translation.z if root_obj is not None else 0.0
  min_ankle_z = ground_z + ANKLE_REST_Z

  # src/rig/ik.py:344-346
  if clamp_ground and applied.z < min_ankle_z:
      applied.z = min_ankle_z
      clamped_ground = True
  ```
* **Affected Callers**:
  - `WholeBodyController.execute_frame()`
  - 任何未显式指定 `clamp_ground=False` 的调用者。
* **Contract Violation**: 违反 3D 任意连续地形运动学合同；将局部根高程误当世界地表高程。
* **Repair Boundary**: 允许传入显式 `ground_z: Optional[float] = None`（由上层环境查询提供），或在地形模式下解耦与 Root 高度的硬编码绑定；严禁暴力直接将既有 `clamp_ground=False` 替换为 True，严禁删除防穿透保护。
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Blocks Further Development**: `NO` (生产主线已通过 `clamp_ground=False` 临时规避)

---

#### FIND-R3-03: `unlock_foot_contact` 与 `reset_leg_ik` 支撑元数据混淆与跨动作残留
* **Finding ID**: `FIND-R3-03`
* **Source Files**:
  - `src/rig/foot_contact.py:168–170`
  - `src/rig/ik.py:219`
* **Function**: `unlock_foot_contact()` / `reset_leg_ik()`
* **Exact Line Range**: `foot_contact.py:168–170`, `ik.py:219`
* **Trigger**: 足部由锁定支撑（Stance）切换为摆动（Swing），或动作完成调用系统重置。
* **Actual Behavior**:
  函数仅将自定义属性 `ik_obj["is_locked"] = False`，但此前写入的 `contact_world_xyz`、`locked_ankle_world_xyz` 等几何元数据仍然持久留存在 Blender Empty 物体上。
* **消费者排查与证据澄清 (R3-CLOSE-04)**：
  - 经全量排查，现有生产消费者（`whole_body_controller.py:395`、`evaluate_foot_support:213, 260`）均严格前置检查了 `is_locked`，未发生有效支撑的误读；
  - 这些属性在摆动期间属于有意保留的历史快照（记录最后一次着地锚点）；
  - 但在系统全局 `reset_leg_ik()` 时，这些历史快照依然残留，可能对跨动作调试或未加锁校验的第三方检查产生脏数据干扰。
* **Expected Contract**:
  摆动期间历史快照允许保留但应明确标记为历史态；全局重置时应彻底清空。
* **Repair Boundary**: 在 `reset_leg_ik()` 中清理 Empty 上的历史锁定属性；在只读查询中明确区分当前活跃支撑点与历史落点快照。
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Blocks Further Development**: `NO`

---

#### FIND-R3-04: `evaluate_foot_support` 充当隐式约束维持器，具有未声明的控制器强写入与骨骼修改副作用
* **Finding ID**: `FIND-R3-04`
* **Source File**: `src/rig/foot_contact.py`
* **Function**: `evaluate_foot_support()`
* **Exact Line Range**: Lines 207–235
* **Trigger**: 任何调用 `evaluate_foot_support()` 或包装函数 `get_foot_support_state()` 的时机。
* **Actual Behavior**:
  该函数在名称和文档上声明为“状态与漂移评估”（只读查询），但实际上在执行时具有极其强烈的副作用与写入行为：
  1. 行 207 调用 `_apply_ik_prebend_hint(arm)`，直接改写了双侧小腿骨骼 `shin.L/R` 的局部欧拉角；
  2. 行 208 和行 235 两次触发全场景依赖图强制更新 `bpy.context.view_layer.update()`；
  3. 只要 `is_locked` 为 True，行 219–224 强制解绑 `ik_obj.parent = None` 并将 `ik_obj.location` 和 `rotation_euler` 覆写回锁定点；
  4. 行 227–234 强制解绑 `pole_obj.parent = None` 并基于当前髋关节重新计算并写入 `pole_obj.location`。
* **严重性与稳定性权衡 (R3-CLOSE-03)**：
  - 调用者在仅想查询遥测时（如 `ContactConstraintAdapter` 或测试代码），在未知情情况下触发了骨骼与控制器写操作；
  - 但在现有执行链中，`WholeBodyController` (L405) 在脚部持续锁定时，**正是依赖调用 `evaluate_foot_support` 来完成每帧对膝盖极向目标的动态更新和对 FootIK 的绝对世界钉死**；
  - 如果盲目将该函数改为纯只读或删除写入，现有的微米级防滑步态将立即损坏！
* **Repair Boundary**:
  1. 严禁简单删除现有写入；
  2. 应在架构重构时将职责拆分为显式的 `enforce_foot_support_lock()`（负责写入与约束刷新）与真正纯只读的 `query_foot_support_state()`（负责遥测提取与漂移计算）。
* **Contract Violation**: 违反函数单一职责原则（SRP）与无副作用查询合同。
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Blocks Further Development**: `NO` (现有 WBC 已形成隐式闭环，但阻碍接口正规化)

---

### 5. 良好设计与验证通过项 (Verified Robust Mechanisms)

1. **上肢 IK 独立性与解剖学约束闭环 ([`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py))**：
   - 左右手目标（`HandIK.L/R`、`ElbowPole.L/R`）与两骨约束（`ArmIK.L/R`、`HandRotation.L/R`）完全物理隔离解耦，互不干扰；
   - 肘关节严格限制为局部 X 轴单自由度解剖铰链（伸展 $0^\circ \sim$ 屈曲 $150^\circ$），并匹配 $-90^\circ$ 极向角，从几何底层杜绝反向折断奇点；
   - 具备幂等性清理重建机制（L206–L209），约束重建不会产生冗余堆叠；
   - 支持平滑连续的 FK/IK 切换，`set_arm_ik_influence` 与 `reset_arm_ik` 动态缩放影响权重，不产生骨骼跳变；
   - 手臂伸缩截断算法严密（L448–L456），当手腕越界时球形投影至最大臂长 ($0.56$m) 极限球面，并如实返回 `is_reachable = False`；
   - 父矩阵逆变换与旋转反解完整严密（L468），堪称标准示范实现。
2. **WBC 统一协调与误差传播鲁棒性 ([`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py))**：
   - WBC 维持单权威写入原则，在单帧执行中独占操控 Rig 目标；
   - 锁态支撑切换平滑，在步态相位切换时通过 `was_locked` 与 `foot_tgt.is_locked` 形成精确的时序闭环；
   - IK 跟踪误差与超出肢体物理极限的违规，通过 `UnmetConstraint(category="REACHABILITY")` 忠实上传至规划层与动力学遥测，未做任何误差隐瞒。

---

### 6. 仍需运行验证的项目说明 (Pending Verification)

* **UNVERIFIED-ROT-01: 非零 Root 偏航下 FootIK 局部旋转偏差实际数值量测**：
  - 现象：`src/rig/ik.py:380–384` 未对局部旋转进行父矩阵逆反解；
  - 现状：当前地形测试均在直线行走走廊（Root Yaw = 0）下运行，该分支尚未在带有转向（Yaw $\ne 0$）的连续步态中进行帧级欧拉角量化校验；
  - 标定：代码逻辑已证实（`STATIC_CONFIRMED`），真实运行场景偏差量测标定为待运行验证（`UNVERIFIED / RUNTIME PENDING`）。

---

### 7. 审计结论与门禁状态 (Audit Conclusion)

* **已审计脚本**:
  1. `src/rig/foot_contact.py` (333 行，7 个生产函数) — **AUDITED & FULL LIFECYCLE CLOSED**
  2. `src/rig/ik.py` (404 行，8 个生产函数) — **AUDITED & FULL LIFECYCLE CLOSED**
  3. `src/rig/arm_ik.py` (510 行，9 个生产函数) — **AUDITED & FULL LIFECYCLE CLOSED**
  4. 跨模块 WBC 与 Rig 执行链接口 — **AUDITED & VERIFIED**
* **发现问题总计**:
  - 本轮 R3 审计确认 **4** 项接口问题（FIND-R3-01 属门禁清规违规且阻碍 Phase 7B；FIND-R3-02、FIND-R3-03、FIND-R3-04 属底层合同缺口）；
  - 全仓库累计确认缺陷与合同缺口增至 **13** 项（3 项 `CONFIRMED_DEFECT`、10 项 `CONTRACT_GAP`）；
  - 阻碍 Phase 7B 的严重缺陷维持 **5** 项。
* **门禁状态标定**:
  - **Phase 7B**: **STRICTLY PROHIBITED**
  - **生产代码修改**: **STRICTLY PROHIBITED (READ-ONLY AUDIT)**
  - **当前审计归档状态**: `PRODUCTION INTERFACE AUDIT / R3 — EVIDENCE VERIFIED`
