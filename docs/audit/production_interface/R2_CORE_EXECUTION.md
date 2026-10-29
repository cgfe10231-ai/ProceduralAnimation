# ProceduralAnimation — Production Interface Audit — R2
## Core Execution Chain & State Contract Audit (核心执行链、状态传递和接口合同联合审计报告)

### 0. 审计基准与工作区状态检查
* **Repository**: `cgfe10231-ai/ProceduralAnimation`
* **Branch**: `master`
* **Baseline Commit SHA**: `3fc9896f6867d49a01f6d5c39b9819d51200c7a0`
* **Working Tree Check**:
  ```text
  $ git status --short
  ?? P2_R1_recovery.patch
  $ git diff --stat
  (clean)
  ```
* **性质确认**: 本次审计为**完全只读**的生产接口审查，未对生产源码、测试用例、配置、文档或场景做任何修改，未执行任何 Git commit / push，未进入 Phase 7B。

---

### 1. 文件概况 (File Summaries & Symbol Enumeration)

| 审计代号 | 生产源码文件路径 | 核心类 / 数据结构 | 生产方法 / 函数 |
| :--- | :--- | :--- | :--- |
| **R2-A** | [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py) | `PlannedFootTarget`<br>`PlannedHandTarget`<br>`KinematicPlannedPose`<br>`BridgeExecutionResult`<br>`KinematicBridgeExecutor` | `convert_planned_pose_to_wbc_targets()`<br>`KinematicBridgeExecutor.__init__()`<br>`KinematicBridgeExecutor.reset()`<br>`KinematicBridgeExecutor.execute_frame()` |
| **R2-B** | [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py) | `MotionMode`<br>`ContactPointState`<br>`MotionState`<br>`ContactConstraintAdapter`<br>`BlenderPoseApplicator`<br>`MotionRuntimeContext`<br>`ActionExecutionResult`<br>`MotionAction`<br>`StartStopWalkAction`<br>`MotionPlanner` | `_make_default_contacts()`<br>`MotionState.clone_with()`<br>`ContactConstraintAdapter.to_dict()`<br>`BlenderPoseApplicator.apply()`<br>`MotionAction.execute()`<br>`StartStopWalkAction.execute()`<br>`MotionPlanner.execute()` |
| **R2-C** | [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py) | `ContactType`<br>`ContactLifecycle`<br>`SupportType`<br>`GeometricConstraintResult`<br>`ContactRecord`<br>`MultiContactState`<br>`EnvironmentalSurface` | `ContactRecord.check_geometric_compliance()`<br>`MultiContactState.update_support_type()`<br>`MultiContactState.get_support_polygon_2d()`<br>`contact_record_to_legacy_contact_point()`<br>`legacy_contact_point_to_contact_record()`<br>`enrich_motion_state_with_contacts()`<br>`evaluate_limb_contacts_from_armature()` |
| **R2-D** | [`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py) | `EndEffectorTarget`<br>`WholeBodyControlTargets`<br>`UnmetConstraint`<br>`EndEffectorFeedback`<br>`WholeBodyControlResult`<br>`WholeBodyController` | `WholeBodyController.__init__()`<br>`WholeBodyController.execute_frame()`<br>`WholeBodyController.reset_all_controls()` |

---

### 2. 逐方法检查表 (Method-by-Method Inspection Tables)

#### 2.1 R2-A: [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py)

| 生产类 / 方法 | 入口与调用方 | 输入检查 | 输出检查 | 失败处理与返回 | 状态来源与消费 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `convert_planned_pose_to_wbc_targets()` (L114-170) | `KinematicBridgeExecutor.execute_frame()` (L269) | `planned: KinematicPlannedPose` (类型与空检查完整) | 返回 `WholeBodyControlTargets` (包含 root, spine, pelvis, feet, hands, arm FK) | 无抛出，按字段映射生成目标数据结构 | 规划目标输入，供 WBC 消费 | **NO_ISSUE** |
| `KinematicBridgeExecutor.__init__()` (L176-218) | 动作初始化 (如 `StartStopWalkAction`, `TerrainWalkAction`) | `armature_obj`, `wbc`, `ground_query_func`, `mesh_query_func`, `mesh_adapter` | 保存依赖实例与执行模式标志位 (`use_mesh_environment`) | 校验 armature 必须有 pose 属性，异常时抛出 `ValueError` | 初始化只读配置与内部引用 | **NO_ISSUE** |
| `KinematicBridgeExecutor.reset()` (L220-226) | 动作边界重置 | 无入参 | 重置内部缓存帧号与状态 | 显式重置并委托 `wbc.reset_all_controls()` | 重置 Bridge 瞬态数据 | **NO_ISSUE** |
| `KinematicBridgeExecutor.execute_frame()` (L228-560) | 动作单帧主循环 (`Action.execute()`) | `planned_pose: KinematicPlannedPose`, `keyframe: bool`, `dt: float` | 返回 `BridgeExecutionResult` (包含 `overall_success`, `wbc_result`, `motion_state`, `unmet_constraints`) | 统一聚合 WBC 失败、ROM 越界与接触几何失败 (`overall_success = wbc_res.success and (len(unmet) == 0)`)；但 L512 引用了不存在的枚举 `ContactLifecycle.TOUCHDOWN` | Phase 1-6 状态流经 ContactModel、WBC，最终打包生成 `MotionState` | **CONFIRMED_DEFECT** (L512 存在非法枚举崩溃隐患，见 FIND-R2-01) |

#### 2.2 R2-B: [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py)

| 生产类 / 方法 | 入口与调用方 | 输入检查 | 输出检查 | 失败处理与返回 | 状态来源与消费 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `MotionState.clone_with()` (L108-124) | Bridge 与各 Action 状态流转 | `**kwargs` 覆盖更新 | 返回不可变 `MotionState` 新实例 | 内部浅拷贝字段，校验必填项 | 状态流动管道核心载体 | **NO_ISSUE** |
| `ContactConstraintAdapter.to_dict()` (L158-179) | 历史字典兼容转换 | 读自身属性 | 返回兼容字典格式的接触状态 | 缺省值填充防护 | 遗留接口适配器 | **NO_ISSUE** |
| `BlenderPoseApplicator.apply()` (L208-321) | 骨骼姿态写入 (仅用于测试/非主链场景) | `armature`, `state` | 修改姿态骨骼并打关键帧 | 校验骨骼存在性 | 独立应用工具，主执行链由 WBC 写入 | **NO_ISSUE** |
| `StartStopWalkAction.execute()` (L570-813) | `MotionPlanner.execute()` | `context: MotionRuntimeContext` | 返回 `ActionExecutionResult` | 严格检查 `if not bridge_res.success:`，收集 unmet constraints 并在达到阈值时抛出 `RuntimeError` | 消费 Bridge 状态，仅修改 `ms.params`，完整保留 `ms.contacts` | **NO_ISSUE** |
| `MotionPlanner.execute()` (L832-865) | 生产动画顶层入口 | `initial_state: Optional[MotionState]` | 返回 `List[ActionExecutionResult]` | **缺失失败处理合同**：无条件顺序执行 Action，`current_state = result.final_state`，无法感知 Action 内部静默失败 | 将上一个 Action 的 `final_state` 作为下一 Action 的 `initial_state` | **CONTRACT_GAP** (见 FIND-R2-04) |

#### 2.3 R2-C: [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py)

| 生产类 / 方法 | 入口与调用方 | 输入检查 | 输出检查 | 失败处理与返回 | 状态来源与消费 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `ContactRecord.check_geometric_compliance()` (L180-213) | `KinematicBridgeExecutor.execute_frame()` (Phase 5) | `max_penetration_m=0.01`, `max_gap_m=0.015` | 返回 `GeometricConstraintResult(is_valid, ...)` | **只读校验，不直接修改自身 `lifecycle` 或 `is_active`**，完全依赖调用者显式处理 | 消费骨骼与表面接触坐标 | **CONTRACT_GAP** (几何不合规与 SupportType 解耦，见 FIND-R2-05) |
| `MultiContactState.update_support_type()` (L243-263) | 接触状态评估函数 | 读活跃脚部接触 | 更新 `self.support_type` (`FLIGHT`, `SINGLE_STANCE`, `DOUBLE_STANCE`, `TRIPLE_SUPPORT` 等) | 仅依据 `rec.is_active` (`lifecycle == ESTABLISHED`) 统计活跃数，不校验几何合规结果 | 接触拓扑判定 | **CONTRACT_GAP** (同 FIND-R2-05) |
| `MultiContactState.get_support_polygon_2d()` (L265-293) | 质心稳定性与可视化 | 读接触点 2D 坐标 | 返回二维凸包多边形顶点序列 | 点数 $<3$ 时返回退化线段/单点/空列表，不抛出异常 | 动力学与遥测消费 | **NO_ISSUE** |
| `enrich_motion_state_with_contacts()` (L415-442) | `KinematicBridgeExecutor.execute_frame()` (Phase 5) | `ms: MotionState`, `multi_contact: MultiContactState` | 返回携带 contacts 的新 `MotionState` | 安全提取 foot/hand 接触记录并注入 `contacts` 字典 | 物理测量结果注入不可变状态载体 | **NO_ISSUE** |
| `evaluate_limb_contacts_from_armature()` (L445-555) | `KinematicBridgeExecutor.execute_frame()` (Phase 1) | `armature_obj`, `planned_pose`, `environment_query`, `thresholds` | 返回 `MultiContactState` (包含各肢体真实测量与几何关联) | 当查询未命中真实 Mesh 且不回退默认平地时标记 `surface_id="MISS"`，产生未满足约束 | 从 Armature 骨骼真实矩阵计算足跟/脚尖/脚踝世界坐标，严格区分布局意图与物理测量 | **NO_ISSUE** |

#### 2.4 R2-D: [`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py)

| 生产类 / 方法 | 入口与调用方 | 输入检查 | 输出检查 | 失败处理与返回 | 状态来源与消费 | 审计结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `WholeBodyController.__init__()` (L124-206) | Bridge 初始化 | `armature_obj: bpy.types.Object` | 绑定骨骼引用、腿部 IK 解算器、手臂 IK 解算器、极向目标 | 校验骨骼与必要约束，缺失时报错 | 控制器底座初始化 | **NO_ISSUE** |
| `WholeBodyController.execute_frame()` (L208-410) | `KinematicBridgeExecutor.execute_frame()` (Phase 4) | `targets: WholeBodyControlTargets`, `keyframe: bool` | 返回 `WholeBodyControlResult` (包含 `is_all_reachable`, `rom_validation`, `tracking_errors`, `unmet_constraints`) | 捕获 IK 解算超限与 ROM 碰撞，记录 `UnmetConstraint`，`success = is_all_reachable and rom_validation.is_valid` | 独占写入 `CharacterRoot`、`pose.bones` 及各 IK Empty，无并发写冲突 | **NO_ISSUE** |
| `WholeBodyController.reset_all_controls()` (L412-447) | Bridge 重置 / 动作切换 | 无入参 | 重置 IK 目标位置、极向与骨骼缓存 | 归位各控制手柄至 Rest 姿态 | 保证动作切换零历史残留 | **NO_ISSUE** |

---

### 3. 跨模块核心执行链与接口一致性核对 (R2-E Cross-Module Verification)

```mermaid
flowchart TD
    MP["1. MotionPlanner.execute()"] --> TA["2. TerrainWalkAction.execute()"]
    TA -->|"KinematicPlannedPose"| KB["3. KinematicBridgeExecutor.execute_frame()"]
    KB -->|"Phase 1: evaluate_limb_contacts_from_armature"| CM["4. ContactModel (MultiContactState)"]
    KB -->|"Phase 4: WholeBodyControlTargets"| WBC["5. WholeBodyController.execute_frame()"]
    WBC -->|"Pose Bones / IK Empties Write"| RIG["6. Character Armature & IK Handlers"]
    WBC -->|"WholeBodyControlResult"| KB
    CM -->|"Phase 5: check_geometric_compliance"| KB
    KB -->|"BridgeExecutionResult (MotionState + contacts)"| TA
    TA -->|"ActionExecutionResult (final_state)"| MP
```

* **E1. Bridge $\to$ WBC (目标传递与执行)**:
  * **核对结果**: **一致**。`KinematicBridgeExecutor` 通过 `convert_planned_pose_to_wbc_targets()` 将 `KinematicPlannedPose` 转换为 `WholeBodyControlTargets`，完整包含 Root 偏置、Spine/Pelvis 姿态、左右脚 IK/FootLock、手臂 IK/FK 旋转。`WholeBodyController.execute_frame()` 逐项完整消费，未遗漏任何控制维度。
* **E2. WBC $\to$ Bridge (执行结果与约束反馈)**:
  * **核对结果**: **一致**。WBC 返回的 `WholeBodyControlResult` 携带 `is_all_reachable`、`tracking_errors`、`rom_validation` 以及 `unmet_constraints`。Bridge 在 L547-555 将 WBC 的 unmet constraints 与自身的接触几何约束合并，严格通过 `overall_success = wbc_res.success and (len(unmet) == 0)` 决定整帧成功状态。
* **E3. Bridge $\to$ ContactModel (足底位置、环境接触点及生命周期语义)**:
  * **核对结果**: **一致**。Bridge 在 Phase 1 调用 `evaluate_limb_contacts_from_armature()` 时，传入真实骨骼的世界矩阵、足底局部锚点及地形查询句柄；区分了骨骼锚点（Point C）与表面投影接触点（Point B）。
* **E4. ContactModel $\to$ Bridge (几何失败与错误捕获)**:
  * **核对结果**: **存在设计合同空隙 (CONTRACT_GAP)**。ContactModel 内部 `check_geometric_compliance()` 仅输出 `GeometricConstraintResult(is_valid=False)`，并不改变自身 `rec.lifecycle`（仍维持 `ESTABLISHED`），也不降低 `multi_contact.support_type`。Bridge 必须在外层手动拦截 `rec.is_active and not geom_res.is_valid` 并注入 `UnmetConstraint(category="CONTACT_GEOMETRY")`（见 FIND-R2-05）。
* **E5. Bridge $\to$ MotionState (接触记录与物理状态注入)**:
  * **核对结果**: **Bridge 端正确，但在 TerrainWalkAction 端被篡改覆盖 (CONFIRMED_DEFECT)**。Bridge 在 Phase 5 通过 `enrich_motion_state_with_contacts()` 正确将物理测量的 `ContactRecord` 填入 `ms.contacts`。然而，在 [`src/motion/terrain_walk.py:1138`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L1138) 中，Action 强制执行 `ms.clone_with(contacts=c_dict)`，用规划意图生成的 `c_dict` 完全冲刷掉了 Bridge 生成的真实接触状态（见 FIND-R2-02）。
* **E6. MotionState $\to$ MotionPlanner (Planner 消费的状态源)**:
  * **核对结果**: **合同脆弱 (CONTRACT_GAP)**。`ActionExecutionResult` 仅返回 `final_state: MotionState`。由于 FIND-R2-02 的存在，`final_state.contacts` 保存的是被覆盖后的规划假定接触，而非物理传感器测量接触。
* **E7. MotionPlanner $\to$ 下一 Action (错误传播与断约)**:
  * **核对结果**: **严重断约 (CONTRACT_GAP)**。`ActionExecutionResult` 缺失 `success: bool` 或 `error_events` 字段。在 `TerrainWalkAction` 中，即使全帧发生 IK 不可达或接触穿透，Action 仅内部打印日志并照常返回 `ActionExecutionResult`。`MotionPlanner.execute()` 盲目将上一个 Action 的 `final_state` 赋给下一个 Action，上游严重几何错误不会引发中断或重规划（见 FIND-R2-03、FIND-R2-04）。

---

### 4. 确认的问题清单 (Confirmed Defects & Contract Gaps)

#### FIND-R2-01: Bridge 中引用不存在的非法枚举成员 `ContactLifecycle.TOUCHDOWN`
* **Source File**: [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py)
* **Class / Function**: `KinematicBridgeExecutor.execute_frame()`
* **Exact Line Range**: [Line 512](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py#L512)
* **Trigger Condition**: 任何规划的手部目标启用接触意图（`pht.enabled=True`, `pht.contact_intent=True`），但尚未锁定（`pht.is_locked=False`）且手部到接触面距离 $> 0.015$m。
* **Actual Behavior**: 试图访问 `ContactLifecycle.TOUCHDOWN`，直接抛出 `AttributeError: type object 'ContactLifecycle' has no attribute 'TOUCHDOWN'` 崩溃。
* **Expected Contract**: `ContactLifecycle` 枚举（定义于 `contact_model.py:45-51`）仅包含 `CANDIDATE`、`ESTABLISHED`、`RELEASED`、`BROKEN`。未建立稳定接触前应标定为 `ContactLifecycle.CANDIDATE`。
* **Evidence**:
  ```python
  # src/motion/kinematic_bridge.py:512
  lifecycle = ContactLifecycle.ESTABLISHED if (dist <= 0.015 or pht.is_locked) else ContactLifecycle.TOUCHDOWN
  ```
  当前测试用例未覆盖手部接触意图，故此分支处于静默休眠状态。
* **Responsible Module**: `src/motion/kinematic_bridge.py`
* **Downstream Impact**: 一旦开启攀爬、障碍支撑或手部环境交互（Phase 7B 核心场景），主管线立即崩溃中断。
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Further Development**: `YES`
* **Suggested Repair Boundary**: 将 `kinematic_bridge.py:512` 的 `ContactLifecycle.TOUCHDOWN` 修正为 `ContactLifecycle.CANDIDATE`，并在单元测试中补全手部接触生命周期流转验证。

---

#### FIND-R2-02: `TerrainWalkAction` 强制覆盖 `MotionState.contacts` 导致上肢接触丢失与虚假物理确认
* **Source File**: [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **Class / Function**: `TerrainWalkAction.execute()`
* **Exact Line Range**: [Lines 1137-1138](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L1137-L1138)
* **Trigger Condition**: 正常运行 `TerrainWalkAction.execute()` 的每一帧。
* **Actual Behavior**:
  ```python
  # src/motion/terrain_walk.py:1138
  ms = ms.clone_with(contacts=c_dict, mode=mode)
  ```
  Action 内部根据步态规划意图自行构造仅包含 `foot_L` 和 `foot_R` 的 `c_dict`，并调用 `clone_with(contacts=c_dict)`，直接覆盖掉此前由 Bridge Phase 5 通过 `enrich_motion_state_with_contacts()` 计算出的完整物理接触记录。
* **Expected Contract**:
  1. `ms.contacts` 必须真实记录物理测量接触状态（Point B 接触坐标、法线、间隙、穿透量）；
  2. 若 Bridge 判定某脚几何约束失败（如落在悬崖外 `BROKEN`），Action 不得将其强行置为 `is_locked=True` 的稳定支撑；
  3. Action 不得擅自擦除上肢（如 `hand_L` / `hand_R`）可能存在的接触记录。
  4. 历史动作（如 `StartStopWalkAction:785`、`RunAction`）仅更新 `ms.params`，严禁外部覆写 `ms.contacts`。
* **Evidence**:
  * 在 `kinematic_bridge.py:557`，Bridge 已经完成了 `ms = enrich_motion_state_with_contacts(ms, multi_contact)`。
  * `terrain_walk.py:1138` 无条件将 `ms.contacts` 倒退回由 `last_known_xyz` 拼凑的二维字典。
* **Responsible Module**: `src/motion/terrain_walk.py`
* **Downstream Impact**: 物理遥测与动力学计算无法获取真实法线与滑动状态；手部接触在进入 MotionState 时被完全销毁；下游模块读取到虚假接触锁定。
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Further Development**: `YES`
* **Suggested Repair Boundary**: 移除 `terrain_walk.py:1138` 中对 `contacts=c_dict` 的覆盖，仅保留 `ms = ms.clone_with(mode=mode, params=ms_params)`，对必须保留的规划步态相位通过 `params` 传递。

---

#### FIND-R2-03: `TerrainWalkAction` 吞没 `BridgeExecutionResult.success` 与物理约束失败
* **Source File**: [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **Class / Function**: `TerrainWalkAction.execute()`
* **Exact Line Range**: [Lines 988-1025](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L988-L1025)
* **Trigger Condition**: 发生 IK 不可达、关节越界（ROM 违规）或接触表面无效（`allows_regular_support=False`）。
* **Actual Behavior**:
  `bridge_res = bridge_executor.execute_frame(...)` 执行后，代码仅读取了 `bridge_res.wbc_result.end_effectors`，对 `bridge_res.success` 与 `bridge_res.unmet_constraints` 完全视而不见。IK 超限仅打印 `logger.warning` 并自增计数器，整个 Action 照常返回完成状态。
* **Expected Contract**:
  对比 `src/motion/framework.py:745-753`（`StartStopWalkAction` 规范实现）：
  ```python
  if not bridge_res.success:
      for uc in bridge_res.unmet_constraints:
          unreachable_events.append(...)
  ```
  在关键物理约束失败时，必须记录并在超出容忍阈值时向调用者抛出明确的异常或在结果中标记失败。
* **Evidence**: `terrain_walk.py` 全文没有任何一处引用 `bridge_res.success` 或 `bridge_res.unmet_constraints`。
* **Responsible Module**: `src/motion/terrain_walk.py`
* **Downstream Impact**: 当地形崎岖导致完全脱离人体解剖学极限时，系统不报错、不重试，生成断裂扭曲的无意义动画，使得自动化测试管线失去门禁拦截能力。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `YES`
* **Suggested Repair Boundary**: 统一 `TerrainWalkAction` 与 `StartStopWalkAction` 的失败处理协议，接入 `bridge_res.success` 校验与 `unmet_constraints` 统计汇总。

---

#### FIND-R2-04: `ActionExecutionResult` 与 `MotionPlanner.execute()` 缺失动作失败处理合同
* **Source File**: [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py)
* **Class / Function**: `ActionExecutionResult` / `MotionPlanner.execute()`
* **Exact Line Range**: [Lines 405-419](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py#L405-L419), [Lines 832-865](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py#L832-L865)
* **Trigger Condition**: 序列化多动作规划中，前序 Action 发生不可达或物理违规。
* **Actual Behavior**:
  `ActionExecutionResult` 数据类仅包含 `action_name`, `start_frame`, `end_frame`, `states`, `frame_records`, `final_state`，缺少 `success: bool` 和 `unmet_constraints` 字段。`MotionPlanner.execute()` 采用盲目顺序流：
  ```python
  result = action.execute(current_state, ctx)
  results.append(result)
  current_state = result.final_state
  ```
* **Expected Contract**:
  Action 执行结果必须显式标明自身执行的成功状态；当发生致死性物理违背时，`MotionPlanner` 必须决定是阻断流程、回退重试还是触发应急过渡。
* **Evidence**: 审查 `MotionPlanner.execute()` 源码，整段循环无任何 `if not result.success` 检查逻辑。
* **Responsible Module**: `src/motion/framework.py`
* **Downstream Impact**: 复合动作（如 Walk $\to$ Stop $\to$ Turn $\to$ Climb）在第一阶段已经失效崩溃的情况下，后续动作仍强行以崩溃状态作为基准继续求解，导致级联错误。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `YES`
* **Suggested Repair Boundary**: 在 `ActionExecutionResult` 中增加 `success: bool = True` 与 `unmet_constraints: List[Any] = field(default_factory=list)` 字段，并在 `MotionPlanner.execute()` 中建立基于动作执行状态的异常流转合同。

---

#### FIND-R2-05: `ContactModel` 几何合规性校验与 `SupportType` 拓扑判定脱节
* **Source File**: [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py)
* **Class / Function**: `ContactRecord.check_geometric_compliance()` / `MultiContactState.update_support_type()`
* **Exact Line Range**: [Lines 180-213](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py#L180-L213), [Lines 243-263](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py#L243-L263)
* **Trigger Condition**: 脚部处于 `ContactLifecycle.ESTABLISHED`，但在物理测量时发生穿透超过阈值（如 $> 10$mm）或悬空离开接触面（如 $> 15$mm）。
* **Actual Behavior**:
  `check_geometric_compliance()` 返回 `GeometricConstraintResult(is_valid=False)`，但该函数属于只读方法，不会修改 `ContactRecord` 本身；随后 `MultiContactState.update_support_type()` 仅依靠 `[c for c in feet if c.is_active]` 计数，仍将该脚计为有效支撑，判定为 `SupportType.DOUBLE_STANCE`。
* **Expected Contract**: 当几何接触严重失效或离开支撑面时，支撑拓扑状态应能感知到该接触已失效（或由 Bridge 协同置为 `BROKEN`），避免在无物理支撑的情况下误判为双脚着地。
* **Evidence**: `MultiContactState.update_support_type()` 源码统计仅判断 `c.is_active`，而 `is_active` 仅要求 `lifecycle == ESTABLISHED and contact_type != FREE`，完全不耦合 `GeometricConstraintResult`。
* **Responsible Module**: `src/motion/contact_model.py`
* **Downstream Impact**: 动力学计算（如重力平衡、质心支撑多边形计算）在足部严重悬空或穿透时，仍按正常双支撑多边形计算，导致物理遥测数据失真。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `NO`
* **Suggested Repair Boundary**: 在 `kinematic_bridge.py` Phase 5 中，当 `check_geometric_compliance()` 返回 `is_valid=False` 且间隙过大时，显式将该记录标记为 `ContactLifecycle.BROKEN`，并同步刷新 `multi_contact.update_support_type()`。

---

#### FIND-R2-06: 地形步态预规划在环境查询未命中时的回退语义不一致
* **Source File**: [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **Class / Function**: `build_terrain_step_schedule()` vs `plan_terrain_footsteps()`
* **Exact Line Range**: [Lines 473-510](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L473-L510), [Lines 577-628](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L577-L628)
* **Trigger Condition**: 在复杂 Mesh 地形边界或断崖边缘执行步态预规划。
* **Actual Behavior**:
  * `plan_terrain_footsteps()`：当 `query_surface_at` 失败或落点在不可支撑表面时，严格抛出 `ValueError(f"Footstep {k} at ({x}, {y}) missed terrain...")`；
  * `build_terrain_step_schedule()`（遗留入口）：当查询失败时，无声回退到 `environment.ground_height_at(x, y)`，并将 `surface_id` 硬编码标定为 `"ground"`。
* **Expected Contract**: 统一步态预规划失败语义，真实 Mesh 模式下不允许出现“一处抛异常，另一处静默伪造平地支撑”的双重标准。
* **Evidence**: 对比两方法的实现代码分支，回退逻辑与异常抛出策略截然不同。
* **Responsible Module**: `src/motion/terrain_walk.py`
* **Downstream Impact**: 当使用不同入口函数进行规划时，产生非确定性行为。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `NO`
* **Suggested Repair Boundary**: 在后续版本中将 `build_terrain_step_schedule()` 废弃或重构为 `plan_terrain_footsteps()` 的兼容包装，统一未命中时的拦截策略。

---

#### FIND-R2-07: 边缘/接缝横向探测位置偏置缺陷
* **Source File**: [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **Class / Function**: `TerrainWalkAction.execute()`
* **Exact Line Range**: [Line 950](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L950)
* **Trigger Condition**: 在具有横向凹凸、边缘或接缝的地形上行走。
* **Actual Behavior**:
  调用 `_adjust_footfall_for_seams_and_edges(env, corridor_x, forward_y, ...)` 时，传入的是走廊中心线坐标 `corridor_x`（通常为 $0.0$），而不是摆动脚真实的横向落点位置 `sw_x`（左右脚偏移通常为 $\pm 0.13$m）。
* **Expected Contract**: 边缘与接缝探测必须以真实预计着地点 `(sw_x, forward_y)` 为中心进行射线与梯度检测。
* **Evidence**: `terrain_walk.py:950` 实参为 `corridor_x`，导致系统始终在身体正中线检测地形边缘，无法感知位于身体侧面 $\pm 13$cm 处踩在台阶边缘的情况。
* **Responsible Module**: `src/motion/terrain_walk.py`
* **Downstream Impact**: 脚部落在台阶或接缝边缘时未触发避障微调，容易出现脚底悬空或踩入接缝。
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Further Development**: `NO`
* **Suggested Repair Boundary**: 将 `corridor_x` 替换为实际落点横向坐标 `sw_x`。

---

### 5. 已知设计限制 (Known Design Limitations)

* **LIMIT-01: 单一前进走廊 $+Y$ 导航假定**:
  当前 `TerrainWalkAction` 及其动力学计算均硬编码沿世界坐标 $+Y$ 轴前进，未解耦世界坐标系与角色局部导航坐标系（Heading）。此为 Phase 6/7A 的设计范围边界，非代码缺陷。
* **LIMIT-02: 上肢开环正向运动学（FK）摆臂**:
  在行进过程中，手臂摆动由纯正弦经验公式生成并以欧拉角写入 WBC FK，手臂 IK 解算器处于休眠挂起状态。这满足当前步态自然度需求，但不支持行进中的动态触碰与抓握。
* **LIMIT-03: IK 超限单向开环警报**:
  WBC 检测到 IK 目标超出肢体极限长度时，将拉伸截断至极限位置并记录 `UnmetConstraint`，但执行链缺乏“由于腿长不够而自动降低骨盆高度”的自适应全身闭环调整。

---

### 6. 未验证项 (Unverified Items)

* **UNVERIFIED-01: 全身多接触动力学求解稳定性**:
  当未来激活手部支撑时（手脚 4 点接触），`WholeBodyController` 中手臂 IK 与腿部 IK 同时锁定时质心与骨盆的姿态平衡尚未在真实三维物理场景中完整验证。
* **UNVERIFIED-02: 极端负高程（大落差跳跃/坠落）下的插值连续性**:
  当前 S1/S2 摆动脚修复主要针对台阶与连续坡道，尚未在大落差（$> 0.8$m）瞬时断崖下进行数值平滑与冲击吸收验证。

---

### 7. 建议集中修复清单与模块分组 (Suggested Remediation Plan)

为了实现彻底收口并不引发系统退化，建议按以下 **4 个原子维护包** 逐步安排修复：

#### 维护包 1: Bridge 健壮性与枚举修复 (Bridge Robustness)
* **修复目标**: FIND-R2-01 (`ContactLifecycle.TOUCHDOWN` 崩溃隐患)
* **修改范围**: 仅 [`src/motion/kinematic_bridge.py:512`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py#L512)
* **影响评估**: 纯局部修复，零副作用，彻底消除手部接触规划时的致命崩溃隐患。

#### 维护包 2: 状态所有权与接触记录保护 (State Integrity)
* **修复目标**: FIND-R2-02 (`MotionState.contacts` 被规划字典冲刷)
* **修改范围**: 仅 [`src/motion/terrain_walk.py:1138`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L1138)
* **影响评估**: 确保物理测量的接触真实保留至 `MotionState`，打通向 Phase 7B 动力学传递的通道。

#### 维护包 3: 执行链失败传播与规划器合同闭环 (Error Propagation Contract)
* **修复目标**: FIND-R2-03、FIND-R2-04 (吞没 WBC 失败、`ActionExecutionResult` 缺失失败状态)
* **修改范围**: [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py) (`ActionExecutionResult` 增加状态字段), [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py) (接入 `bridge_res.success` 校验)
* **影响评估**: 建立全管线统一的错误拦截与报警机制，防止生成扭曲静默动画。

#### 维护包 4: 接缝探测精度与规划一致性 (Footfall Planning Precision)
* **修复目标**: FIND-R2-06、FIND-R2-07 (接缝横向坐标偏置、规划入口回退语义)
* **修改范围**: [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **影响评估**: 优化足部落点精度，避免边缘踩空。

---

### 8. 审计结论与最终状态

本次 R2 联合审计已完成对 `kinematic_bridge.py`、`framework.py`、`contact_model.py`、`whole_body_controller.py` 四大核心脚本的逐方法深入检查，确认了执行链中的 1 处崩溃枚举缺陷、2 处核心状态/错误丢失缺陷、3 处接口合同空隙与 1 处落点偏置缺陷。

工作区保持绝对干净，未进行任何代码更改或文件产生。

```text
PRODUCTION INTERFACE AUDIT / R2 — AWAITING REVIEW
```