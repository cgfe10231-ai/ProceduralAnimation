# STATE_OWNERSHIP_AND_SEMANTICS: 状态所有权、坐标空间与物理语义审计

**审计基准 Commit**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计时间**：2026-10-29  
**所属门禁**：Environment Gate 01 — Final Architecture Audit (Audit E)  

---

## 1. 核心状态数据结构审计矩阵

| 状态数据结构 | 创建者 (Creator) | 修改者 (Mutator) | 主要消费方 (Consumer) | 生命周期 | 坐标空间与单位 | 数据性质 (计划/实际/测量) | 是否进入下一时刻求解 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **`SurfaceQueryResult`** | `BlenderMeshEnvironmentAdapter.ray_cast()` 或 `DynamicsEnvironmentQuery` | 不可变 (Frozen/Read-only) | `TerrainWalkAction`, `KinematicBridgeExecutor` | 瞬时（单次射线查询命中后销毁或打包） | **World Space**<br>位置/法线: $\text{m}$, 距离: $\text{m}$, 摩擦: 无量纲 | **真实测量值 (Measured Ground Truth)** | 是（决定步态落点与锁定锚点） |
| **`TerrainStepPlan`** | `plan_terrain_footsteps()` (`terrain_walk.py`) | 不可变 (一次性生成全场 42 步列表) | `TerrainWalkAction.execute()` 逐帧插值器 | 动作全程持久化 | **World Space**<br>坐标: $\text{m}$, 倾角: $\text{deg}$, 帧: 整数 | **离散全局计划值 (Planned Schedule)** | 是（逐帧驱动摆动脚与支撑脚切换） |
| **`KinematicPlannedPose`** | `TerrainWalkAction.execute()` 或各 `MotionAction` | 动作内计算并打包传递 | `KinematicBridgeExecutor.execute_frame()` | 单帧瞬时 | **World Space**<br>Root/脚部: $\text{m}$, 旋转: $\text{deg}$, 时间: $\text{s}$ | **连续控制意图值 (Control Intent)** | 是（驱动 WBC 骨骼与 IK 分发） |
| **`WholeBodyControlTargets`** | `KinematicBridgeExecutor.execute_frame()` | 桥接层组装后提交 | `WholeBodyController.execute_frame()` | 单帧瞬时 | **World Space & Local Frame**<br>Root: World, 姿态骨: Bone Local | **控制分发中间值 (Dispatched Target)** | 是（直接写入 Blender 物体与姿态骨） |
| **`WholeBodyControlResult`** | `WholeBodyController.execute_frame()` | WBC 内部生成 | `KinematicBridgeExecutor` | 单帧瞬时 | **World Space**<br>误差: $\text{m}$, 质心: $\text{m}$ | **底层解算后实际计算值 (Evaluated Actual)** | 否（仅单向返回桥接层） |
| **`ContactRecord`** | `evaluate_limb_contacts_from_armature()` (`contact_model.py`) | 不可变 (单帧评估记录) | `MultiContactState`, 遥测富集器 | 单帧瞬时 | **World Space**<br>位置: $\text{m}$, 法线: 归一化向量 | **物理几何核验状态 (Validated State)** | 否（仅存入遥测，不闭环修正控制） |
| **`MultiContactState`** | `evaluate_limb_contacts_from_armature()` | 桥接层汇聚各肢接触 | `KinematicBridgeExecutor`, 导出遥测 JSON | 单帧瞬时 | 集合包 (World Space) | **多肢接触瞬时快照 (Multi-Limb Snapshot)** | 否（仅用于遥测与违规检测） |
| **`MotionState`** | `MotionPlanner` 初始化，经桥接层逐帧丰富 | `enrich_motion_state_with_*()` | `MotionPlanner`, 渲染器, 伴随 JSON 文件 | 随帧持久化至列表 | **World Space**<br>位置: $\text{m}$, 速度: $\text{m/s}$, 加速度: $\text{m/s}^2$ | **全系统权威状态快照 (Authoritative Snapshot)** | 仅提供给下一帧时间戳/当前帧号，不提供状态反馈 |
| **`ForwardDynamicsState`** | `ForwardDynamicsIntegrator.integrate_step()` | 动力学内核 | 仅独立测试用例 | 测试单步 | **World Space**<br>位置: $\text{m}$, 速度: $\text{m/s}$, 四元数, 角速度: $\text{rad/s}$ | **动力学数值积分值 (Simulated State)** | **未接入主链（与 19 骨骼人体零交互）** |

---

## 2. 核心语义深度审计与结论

### 2.1 三坐标空间合同审计 (Point A vs Point B vs Point C)
在 Unit 4 中正式确立并固化了三坐标严格分工合同：
* **点 A (Point A - Planned Ankle Target)**：
  - 变量：`PlannedFootTarget.world_xyz` $(x_a, y_a, z_a)$；
  - 语义：运动学规划器指定的**脚踝关节中心 IK 目标世界坐标**；在水平平地上 $z_a = \text{ANKLE\_REST\_Z} = 0.070\text{ m}$；
  - 物理意义：由腿部 2 骨骼 IK 求解器驱动胫骨末端抵达该点。
* **点 B (Point B - Real Ground Contact Point)**：
  - 变量：`SurfaceQueryResult.contact_point_world` $(x_c, y_c, z_c)$，保存在 `active_limb_targets["target_world"]` 与 `ContactRecord.world_position`；
  - 语义：真实 3D 环境网格表面被射线命中的**真实地面接触点世界坐标**；
  - 物理意义：支撑多边形几何顶点、法向支持力作用点。
* **点 C (Point C - Actual Humanoid Sole Anchor)**：
  - 变量：$\mathbf{p}_{\text{sole}} = \mathbf{M}_{\text{bone\_world}} \cdot \mathbf{a}_{\text{bone\_local}}$；
  - 语义：在当前骨骼姿态下，人体模型脚底接触锚点的**实际物理世界空间坐标**；
  - 物理意义：足部网格底面中心，用于与点 B 核算气隙、穿透与切向滑移。
* **审计结论**：**三坐标语义清晰严谨，无概念混淆**。消除了历史将脚踝点直接视为地表接触点的几何错位。

### 2.2 `MotionState.contacts` 的数据真实性
* **审计发现**：
  在 [`src/motion/terrain_walk.py:1100-1123`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py#L1100-L1123)，`TerrainWalkAction` 在每一帧组装了 `c_dict: Dict[str, ContactPointState]`，并将 `MotionState.contacts` 覆盖为：
  ```python
  c_dict["foot_L"] = ContactPointState(
      limb="foot_L",
      phase=phase_l,
      is_locked=foot_l_tgt.is_locked,
      contact_world_xyz=last_known_l_xyz,
      current_world_xyz=eff_l.actual_world_xyz if eff_l else last_known_l_xyz,
      drift_m=drift_l,
      is_reachable=reach_l,
      surface_normal=foot_l_tgt.normal_world,
  )
  ```
* **语义核实**：
  - `contact_world_xyz` 记录的是支撑脚锁定时踩踏的真实地表网格高程（Point B）；
  - `current_world_xyz` 记录的是骨骼实际姿态反馈位置（Point A）；
  - `drift_m` 记录了实际位置与目标位置的偏差（最大滑移 $< 1.55\text{ mm}$）；
  - `MotionState.contacts` 忠实记录了真实接触状态，无数据伪造。

### 2.3 `ContactLifecycle.ESTABLISHED` 的语义真值
* **审计问题**：`ContactLifecycle.ESTABLISHED` 到底是表示“步态运动意图”，还是“经几何核验后的物理接触状态”？
* **真实代码流动分析**：
  1. 在 `KinematicBridgeExecutor.execute_frame():410-440`：当锁定脚 `ft.is_locked=True` 且 `query_res.success and query_res.allows_regular_support` 为真时，将 `active_limb_targets[limb]["lifecycle"]` 标定为 `ContactLifecycle.ESTABLISHED`；
  2. 随后在 `evaluate_limb_contacts_from_armature():537-550`，构造出生命周期为 `ESTABLISHED` 的 `ContactRecord`；
  3. 紧接着在 `multi_contact.check_all_contacts():554-571`，核对骨骼姿态与地表网格的几何距离。如果气隙 $> 15\text{ mm}$ 或穿透 $> 10\text{ mm}$，虽然记录了违规并导致 `result.success=False`，但 **`ContactRecord.lifecycle` 仍然保持为 `ESTABLISHED`**（仅在查询彻底失败或非支撑面时才标记为 `BROKEN`）。
* **审计结论**：
  **当前 `ContactLifecycle.ESTABLISHED` 在语义上偏向“已成功与有效表面建立几何约束关系的接触意图”**，而非“完全无几何偏差的绝对刚体接触”。此项设计符合运动学前向积分阶段的惯例，但建议后续在 Phase 7C 动力学求解阶段，明确将“几何违规”状态下的接触生命周期动态降级为 `BROKEN`。

### 2.4 Root Position 的状态所有权
* **所有权归属**：**100% 归属于规划器样条（Kinematic Spline Ownership）**。
* **物理事实**：
  - Root 前进速度与位移由 `_build_continuous_root_forward_spline()` 构建的三次 Hermite 样条生成；
  - 质心动力学积分器（`ForwardDynamicsIntegrator`）产生的位移与速度**完全没有注入 `CharacterRoot`**；
  - 角色躯干与质心的运动目前不存在受力反馈扰动或反作用力加速度，系统处于纯开环运动学追踪状态。
