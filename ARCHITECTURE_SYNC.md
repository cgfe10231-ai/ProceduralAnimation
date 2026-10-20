# ARCHITECTURE_SYNC: 架构同步与模块调用规范卡片

> **最新架构审计基准版本**：v2.0 (Task 6G-C-R3A 深度审计)  
> **审计基准 Git SHA**：`8582bc3` (对应文档更新 `4111a51`)  
> **状态**：架构审计完成，锁定调用规范，等待 R3B 执行合流修复  
> **核心原则**：磁盘代码与真实运行调用链是唯一事实依据。严禁将离散演示或只读遥测称为闭环控制。

---

## 1. 架构版本与核心设计思想 (Architecture Version & Core Principles)

* **技术定位**：**物理约束辅助的程序化 3D 连续跑酷动画系统**。
* **物理模型边界**：
  * 系统基于 19 骨骼刚体连杆分段质量模型、解析运动学、两骨 IK 求解与生理活动范围（ROM）硬性限制。
  * **不开发肌肉/肌腱模拟器，不构建全自由度数值物理动力学积分器（无力矩驱动关节仿真）**。
* **核心设计思想**：
  * **生成由运动学主导**：身体质心运动、足部步态相位、腾空抛物线及四肢接触意图由基于物理法则的解析运动学生成器计算（Analytical Kinematics）。
  * **姿态由协调器收敛**：`WholeBodyController` 作为姿态协调中枢，负责统一分配四肢 IK、骨盆与脊柱姿态，并执行生理活动范围（ROM）截断。
  * **物理层作为约束与遥测**：接触模型执行零漂移世界坐标锁定；质心、速度、角动量、接触状态作为不可篡改的遥测数据写入 `MotionState`，供动作决策与物理验证。

---

## 2. 模块依赖关系与数据流向图 (Module Dependency Graph)

```mermaid
flowchart TD
    subgraph SchedLayer["1. 调度与规划层"]
        Planner["src/motion/framework.py<br/>MotionPlanner"]
        Context["MotionRuntimeContext<br/>(Armature, Scene, Limits)"]
    end

    subgraph ActionLayer["2. 连续动作生成层"]
        ActionBase["MotionAction (基类)"]
        WalkAction["StartStopWalkAction<br/>(src/motion/start_stop_walk.py)"]
        RunAction["RunAction<br/>(src/motion/run_cycle.py)"]
        SprintAction["SprintStartAction<br/>(src/motion/sprint_start.py)"]
        BrakeAction["SprintBrakeAction<br/>(src/motion/sprint_brake.py)"]
        VaultAction["Future Parkour Actions<br/>(VaultAction / WallRunAction)"]
    end

    subgraph CoordLayer["3. 全身姿态协调层"]
        WBC["src/motion/whole_body_controller.py<br/>WholeBodyController"]
        Targets["WholeBodyControlTargets<br/>(Root pos/yaw, Pelvis, HandIK, FootIK)"]
        ROM["src/motion/joint_limits.py<br/>JointModel (ROM Clamp)"]
    end

    subgraph RigLayer["4. 骨架与约束解算层 (Blender Pose)"]
        ArmIK["src/rig/arm_ik.py<br/>(HandIK.L/R, ElbowPole)"]
        LegIK["src/rig/ik.py<br/>(FootIK.L/R, KneePole)"]
        FootLock["src/rig/foot_contact.py<br/>(Foot Locking & Root Offset)"]
        PoseBones["19-Bone Armature<br/>(CharacterRoot, Pelvis, Spine...)"]
    end

    subgraph TelemetryLayer["5. 物理遥测与状态回写层 (只读分析)"]
        CoMEval["src/motion/rigid_link.py<br/>compute_whole_body_com"]
        KinEval["src/motion/body_kinematics.py<br/>BodyKinematicsTracker"]
        InertiaEval["src/motion/body_inertia.py<br/>WholeBodyInertiaState"]
        ContactEval["src/motion/contact_model.py<br/>MultiContactState / SupportType"]
    end

    subgraph StateLayer["6. 统一状态载体"]
        MotionState["src/motion/framework.py<br/>MotionState (params, contacts, com)"]
    end

    Planner --> ActionBase
    ActionBase <|-- WalkAction
    ActionBase <|-- RunAction
    ActionBase <|-- SprintAction
    ActionBase <|-- BrakeAction
    ActionBase <|-- VaultAction

    WalkAction & RunAction & SprintAction & BrakeAction & VaultAction --> Targets
    Targets --> WBC
    WBC --> ROM
    WBC --> ArmIK
    WBC --> LegIK
    WBC --> PoseBones
    FootLock --> LegIK

    PoseBones --> CoMEval
    PoseBones --> KinEval
    KinEval --> InertiaEval
    PoseBones --> ContactEval

    CoMEval & KinEval & InertiaEval & ContactEval --> MotionState
    MotionState -.->|前一动作最终状态| ActionBase
```

---

## 3. 官方认可的连续运动管线数据流 (Official Continuous Motion Pipeline Flow)

在后续所有任务中，唯一合法的单帧生成数据流必须严格遵循以下 **6 个阶段**：

1. **Phase 1: 动作运动学规划 (Kinematic Planning)**  
   * 动作实例（`MotionAction`）根据当前时间步 $t$、步态周期 $u$ 及上一状态 $S_{k-1}$，解析计算出：
     * 角色根节点期望世界位置与朝向：$P_{\text{root}}(t), \theta_{\text{root}}(t)$；
     * 双脚踝关节世界空间目标坐标与接地/摆动布尔标记；
     * 双手手腕世界空间目标坐标与三维朝向（若有交互目标）；
     * 骨盆下沉高度与脊柱躯干倾角。
   * 产物：`WholeBodyControlTargets` 实例。

2. **Phase 2: 接触约束锁定 (Contact Locking)**  
   * 对于处于支撑相（Stance Phase）的足部或手部，通过 `foot_contact.py` 将 IK 控制体在世界坐标系下原位锁定（漂移严控 $< 0.005\text{ mm}$）。
   * 根节点位移带动的世界坐标系变换必须经过零漂移补偿。

3. **Phase 3: 全身协调与 ROM 截断 (Coordination & ROM Enforcement)**  
   * `WholeBodyController.execute_frame(armature, targets)` 接收目标：
     * 计算并写入根节点与骨盆局部位置；
     * 驱动四肢两骨双轴 IK 求解器（`arm_ik` 与 `ik`）；
     * 读取骨骼姿态矩阵，由 `JointModel` 执行生理活动范围（ROM）硬性限制校验与截断。

4. **Phase 4: Blender 场景评估与插帧 (Blender Evaluation & Keyframing)**  
   * 调用 `depsgraph.update()` 刷新全部约束。
   * 向骨骼与控制物体打入动画关键帧。

5. **Phase 5: 物理遥测与特征提取 (Physics Telemetry)**  
   * 从更新后的骨架姿态中提取：
     * `compute_whole_body_com`：真实物理质心世界坐标 $(X_{\text{com}}, Y_{\text{com}}, Z_{\text{com}})$；
     * `BodyKinematicsTracker`：有限差分计算根节点、连杆、质心的瞬时线速度与角速度；
     * `WholeBodyInertiaState`：合成全身体惯性张量与自转/轨道角动量；
     * `ContactModel`：评估肢体末端与环境的间隙、穿透、滑移和支撑状态分类（`STABLE_FEET` / `HAND_SUPPORT` / `FLIGHT` 等）。

6. **Phase 6: 状态回写 (State Commit)**  
   * 将上述遥测数据组装为新的 `MotionState`，回写至动作的 `frame_states` 列表，为下一时间步或动作切换提供初值。

---

## 4. 历史动作入口点与重用规范 (Historical Action Reuse Matrix)

所有历史动作必须通过其官方类与生成器重用，**严禁重新编写重复的步态生成逻辑**：

| 动作标识 | 任务编号 | 源码实现位置 | 核心调用入口 | 步态与速度特性 |
| :--- | :--- | :--- | :--- | :--- |
| **Walk Cycle** | Task 5A | `src/motion/walk_cycle.py` | `generate_walk_cycle(armature, frames=72)` | 固定原地循环周期（36 帧/步），归一化相位 $u \in [0, 1)$ |
| **Forward Walk** | Task 5B | `src/motion/forward_walk.py` | `generate_forward_walk(armature, steps=4)` | 沿 $+Y$ 直线前向跨步，步幅累加调度 |
| **StartStopWalkAction** | Task 5C / 6A | `src/motion/start_stop_walk.py`<br/>`src/motion/framework.py` | `StartStopWalkAction(steps=7, step_duration=12)`<br/>`generate_start_stop_walk(...)` | 7 个连续步态调度；$C^1$ 速度曲线（0 $\rightarrow$ 0.24 $\rightarrow$ 0 m/s）；世界空间零漂移锁定 |
| **RunAction** | Task 6B | `src/motion/run_cycle.py` | `RunAction(cycles=4, half_period_frames=12)` | 具备双脚离地单腾空相（支撑 7 帧，腾空 5 帧）；速度 $1.0\text{ m/s}$；跑动屈肘 |
| **SprintStartAction** | Task 6C | `src/motion/sprint_start.py` | `SprintStartAction(prep_frames=12, drive_frames=24)` | 三阶段爆发式起跑；躯干深俯；峰值速度 $3.6\text{ m/s}$ |
| **SprintBrakeAction** | Task 6D | `src/motion/sprint_brake.py` | `SprintBrakeAction(target_stop_pos=...)` | 4 阶段主动急停；躯干后仰制动；峰值减速度 $-6.0\text{ m/s}^2$ |

---

## 5. WholeBodyController 真实定位与调用规范 (WholeBodyController Specification)

* **模块位置**：`src/motion/whole_body_controller.py`。
* **真实定位**：**姿态求解与约束协调器（Pose Coordinator）**。它不是动作发生器（Action Generator），不维护时间轴轨迹，不自行决定脚何时离地。
* **输入规范**：必须接收由 `MotionAction` 计算好的 `WholeBodyControlTargets`，包含：
  * `root_position` 与 `root_yaw`；
  * `pelvis_local_offset`；
  * `trunk_pitch_deg`, `trunk_roll_deg`, `trunk_yaw_deg`；
  * `hand_targets`: 左右手 `WorldSpaceArmTarget`（世界坐标 + 期望朝向 + 极向权重）；
  * `foot_targets`: 左右脚世界坐标目标与偏航角；
  * `left_arm_mode`, `right_arm_mode`: `IK` 或 `FK`。
* **输出规范**：返回 `WholeBodyControlResult`，包含：
  * `tracking_errors`: 四肢末端实际位置与目标的欧氏距离；
  * `rom_violations`: 越界骨骼列表及最大越界角度；
  * `com_world`: 求解完成后的全身世界质心坐标。
* **禁止用法**：严禁在演示脚本中绕过 `MotionAction` 直接手动编写多帧连续 `execute_frame` 来充当动画动作。

---

## 6. IK/FK 求解与 ROM 限制边界 (IK/FK & ROM Boundary)

* **四肢解算职责**：
  * **双腿**：由 `src/rig/ik.py` 驱动两骨 IK 约束，极向引导器 `KneePole.L/R` 控制膝关节向正前偏外方向弯曲。
  * **双臂**：由 `src/rig/arm_ik.py` 驱动两骨 IK 约束与 `Copy Rotation` 约束，极向引导器 `ElbowPole.L/R` 控制肘关节向后偏外方向弯曲。
* **ROM 限制时机与边界**：
  * 模块：`src/motion/joint_limits.py`。
  * 覆盖 9 大类核心关节：`spine`, `neck`, `shoulder.L/R`, `upper_arm.L/R`, `forearm.L/R`, `hand.L/R`, `thigh.L/R`, `shin.L/R`, `foot.L/R`。
  * **边界划分**：
    * `CharacterRoot` 与 `pelvis` 属于自由刚体自由度（6-DOF），不施加解剖 ROM 限制。
    * 四肢骨骼受解剖角限制，在 `execute_frame` 的阶段四（Stage 4）进行骨骼矩阵提取与姿态校验。
    * 若启用截断模式（Clamp Mode），越界旋转将被强制投影回生理极限内。

---

## 7. 物理遥测调用时机与回写位置 (Physics Telemetry Protocols)

所有物理与动力学模块在系统中的性质均为**纯只读遥测（Read-Only Telemetry）**：

| 遥测模块 | 源码位置 | 评估对象 | 调用时机 | 回写目标位置 | 是否提供闭环反馈 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **全身质心 (CoM)** | `src/motion/rigid_link.py` | 13 分段骨骼全局矩阵与质量权重 | `depsgraph.update()` 之后 | `MotionState.params["com_world"]`<br/>`WholeBodyControlResult.com_world` | **否**（只读指标，不产生平衡推力） |
| **微分运动学 (Kinematics)** | `src/motion/body_kinematics.py` | 连续姿态快照 `BodyPoseSnapshot` | 关键帧插入完成后 | `MotionState.params["kinematics"]`<br/>`MotionState.velocity` | **否**（只读数值差分，不驱动骨骼） |
| **惯性张量与角动量** | `src/motion/body_inertia.py` | 骨骼连杆几何与线/角速度 | 运动学计算完成后 | `MotionState.params["inertia"]` | **否**（只读动量统计，不产生旋转力矩） |
| **多部位接触模型** | `src/motion/contact_model.py` | 四肢末端世界坐标与环境表面几何 | 全身姿态解算后 | `MotionState.params["contacts"]`<br/>`MotionState.contacts` 字典 | **否**（只读几何检测，不执行脚部锁定） |

---

## 8. 模块分类清单 (Module Classification List)

根据磁盘代码真实调用关系，当前工程模块被严格划分为两类：

### 8.1 已集成模块 (Integrated Production Modules)
此类模块已被正式纳入生产调用链，直接参与动画生成或姿态解算：
1. `src/motion/framework.py`：`MotionPlanner`, `MotionState`, `ContactConstraintAdapter`, `BlenderPoseApplicator`
2. `src/motion/start_stop_walk.py`：`StartStopWalkAction`, 7 步步态调度器
3. `src/motion/run_cycle.py`：`RunAction`, 腾空相步态发生器
4. `src/motion/sprint_start.py`：`SprintStartAction`, 爆发起跑运动学
5. `src/motion/sprint_brake.py`：`SprintBrakeAction`, 急停制动运动学
6. `src/rig/builder.py`：19 骨骼层级与 13 分段占位体装配
7. `src/rig/ik.py`：腿部两骨 IK 求解与极向约束
8. `src/rig/foot_contact.py`：脚部世界坐标锁定与根节点零漂移移动
9. `src/rig/arm_ik.py`：手臂双骨 IK 求解与手部空间姿态对齐

### 8.2 独立工具模块 (Standalone Tool Modules)
此类模块仅在独立测试或原型脚本中运行，**尚未并入现有 `MotionAction` 的生产循环**：
1. `src/motion/whole_body_controller.py`：仅被 Task 6F-D/6G 原型脚本单独调用，历史 4 大动作未接入。
2. `src/motion/joint_limits.py`：仅被 `WholeBodyController` 在测试时校验，未在主动画管线中前向拦截。
3. `src/motion/rigid_link.py`：仅作为只读质心计算器使用。
4. `src/motion/body_kinematics.py`：仅作为事后有限差分速度分析器使用。
5. `src/motion/body_inertia.py`：仅作为事后角动量与转动惯量分析器使用。
6. `src/motion/contact_model.py`：仅作为事后接触几何与支撑分类器使用，未参与前向锁定。

---

## 9. 当前架构断裂点与未打通路径 (Architectural Break Points)

1. **断裂点 1（控制器双轨制）**：
   * 历史成熟动作（`StartStopWalkAction` 等）使用私有的 `ContactConstraintAdapter` 和经验上身函数直接修改骨架。
   * 新开发的 `WholeBodyController` 具有更完整的全身协调和 ROM 校验能力，但没有被历史动作调用。
2. **断裂点 2（接触模型脱离接地锁定）**：
   * 真实的零漂移足部锁定由 `src/rig/foot_contact.py` 执行。
   * `src/motion/contact_model.py` 内部拥有接触点生命周期管理（`ESTABLISHED`, `HELD`, `RELEASED`），但它与 `foot_contact.py` 完全互不调用，属于两套独立的接触状态体系。
3. **断裂点 3（障碍物跑酷动作缺失）**：
   * 系统中目前没有任何继承自 `MotionAction` 的障碍物交互动作类（无 `VaultAction`、无 `WallRunAction`）。
   * 原型脚本通过硬编码坐标直接调用 `WholeBodyController.execute_frame` 拍摄静态切片，造成“僵硬片段”的严重假象。
4. **断裂点 4（物理无闭环）**：
   * 系统完全缺乏从质心（CoM）、角动量或接触力向运动学层反馈调整的机制。系统是严格的单向只读流。

---

## 10. 后续开发任务允许使用的模块与禁止绕过的模块 (Usage Permissions & Prohibitions)

* **允许且推荐使用的模块**：
  * 步态调度与根节点轨迹：复用 `src/motion/start_stop_walk.py` 等成熟解析运动学算法；
  * 足部世界锁定：必须调用 `src/rig/foot_contact.py` 保障零漂移；
  * 全身姿态求解：后续新动作必须以 `WholeBodyControlTargets` 为目标接口，统一经由 `WholeBodyController` 落地。
* **绝对禁止的操作与绕过行为**：
  * **禁止独立脚本拼凑动画**：严禁在无 `MotionAction` 的情况下直接写循环硬插固定姿态帧；
  * **禁止绕过足部世界锁定**：严禁在支撑相通过局部骨骼平移代替真正的世界空间零漂移锁定；
  * **禁止伪造物理闭环**：严禁在报告或文档中将 `rigid_link.py` 或 `body_inertia.py` 的只读统计宣称为“物理驱动平衡”；
  * **禁止破坏历史动作**：任何重构不得导致 `test_08_start_stop_walk`、`test_12_run_cycle`、`test_13_sprint_start`、`test_14_sprint_brake` 发生退化或穿帮。

---

## 11. 本次审计依据的 Git Commit SHA

* **底层基准 Commit**：`8582bc3`（Task 6G-C 第二次返工提交点）
* **文档基准 Commit**：`4111a51`（同步 `AI_SYNC.md` / `PROJECT_STATE.md` 文档）
* **工作树核查状态**：代码与测试套件完全对应，无未跟踪的幽灵实现。

---

## 12. 变更日志与维护规则 (Change Log & Maintenance Protocol)

* **维护规则**：
  1. 本文件为工程架构调用的唯一授权卡片，所有后续任务（包括 Task 6G-C-R3B、Task 6G-D 及跑酷动作开发）必须严格遵从本规范。
  2. 凡涉及跨模块调用、接口变更、新增动作类或合流重构，必须在任务结束前同步更新本卡片与 `ARCHITECTURE.md`。
* **变更记录**：
  * `2026-10-20 (Task 6G-C-R3A)`：创建本卡片，完成全仓库架构深度审计，彻底澄清三套管线、只读物理遥测性质及障碍物僵硬成因。
