# ARCHITECTURE: 全程序化 3D 动画系统架构与工程规范蓝图

> **最新架构审计版本**：v2.0 (Task 6G-C-R3A 深度审计更新)  
> **审计基准 Git SHA**：`8582bc3` / `4111a51`  
> **核心原则**：磁盘源码与真实可运行调用链是唯一事实标准。严禁将“设计目标”或“仅存在于测试/独立脚本中的调用”描述为已经完成集成的生产架构。

---

## 1. 统一物理与世界坐标约定 (Physical & World Coordinate Conventions)

所有模块（场景、环境障碍物、角色网格、骨架 Armature、IK 约束、动力学模型与摄像机系统）必须严格执行以下物理世界坐标约定，严禁任何局部私有坐标混淆：

* **坐标轴定义**：
  * **$+Z$ 轴向上**（天顶方向，$-Z$ 为重力指向地心方向）。
  * **$+X$ 轴向右**（角色右侧，$-X$ 为角色左侧）。
  * **$+Y$ 轴向前**（深度前进主走廊，角色初始正对方向）。
* **地面基准参考面**：
  * **地面顶表面严格处于 $Z = 0.0\text{ m}$**。
  * 角色静止站立时，脚底接触面与地面零点严格切齐（$Z_{\text{sole}} = 0.0\text{ m}$，踝关节原点位于 $Z_{\text{ankle}} = 0.070\text{ m}$）。
* **物理度量单位**：
  * 长度单位：**米 (m)**。
  * 时间单位：**秒 (s)**（主时间轴标准帧率：$24\text{ FPS}$，单帧时间步长 $\Delta t = 1/24\approx 0.041667\text{ s}$）。
  * 速度单位：**米/秒 ($\text{m/s}$)**。
  * 角速度单位：**弧度/秒 ($\text{rad/s}$)** 或 度/秒 ($\text{deg/s}$)。
  * 质量单位：**千克 (kg)**（标准成人参考体质量 $75.0\text{ kg}$）。
  * 转动惯量单位：**$\text{kg}\cdot\text{m}^2$**。
* **运动空间与安全走廊走势**：
  * 起点站立区：$(0.0, -8.0, 0.0)\text{ m}$。
  * 主直线运动通道：沿 $+Y$ 轴从 $Y = -8.0\text{ m}$ 延伸至 $Y = 0.0\text{ m}$（以及后续扩展）。
  * 走廊安全净空带宽：沿走廊中心线保持半径 $\ge 2.4\text{ m}$ 的无碰撞净空，环境布局算法禁止非规划障碍物侵入。

---

## 2. 当前真实架构图 (Current Real Architecture)

根据对仓库受 Git 管理的全部源码审计，当前工程中实际存在**三套互不相通、分立并行的执行管线**：

```mermaid
flowchart TD
    subgraph Pipeline1["管线一：历史程序化动作管线 (Task 5A - 6D，真实驱动连续步态)"]
        Planner["MotionPlanner (src/motion/framework.py)"]
        Action["MotionAction<br/>(StartStopWalkAction / RunAction / SprintStartAction / SprintBrakeAction)"]
        StepSched["步态调度与解析运动学<br/>(build_step_schedule / evaluate_root_kinematics)"]
        ContactAdapt["ContactConstraintAdapter (src/motion/framework.py)"]
        FootLock["src/rig/foot_contact.py<br/>(lock_foot_contact / move_root_preserving_locks)"]
        PoseApp["BlenderPoseApplicator (src/motion/framework.py)"]
        UpperPose["经验上身姿态函数<br/>(_apply_start_stop_upper_body_pose / apply_run_upper_body_pose)"]
        RigDirect["Blender Armature & Controllers<br/>(CharacterRoot, FootIK.L/R, KneePole.L/R, PoseBones)"]
        
        Planner -->|execute_plan| Action
        Action --> StepSched
        StepSched --> ContactAdapt
        StepSched --> UpperPose
        ContactAdapt --> FootLock
        FootLock -->|直接操作 Empty 物体坐标与父级| RigDirect
        UpperPose --> PoseApp
        PoseApp -->|直接写入 Euler 旋转并插帧| RigDirect
    end

    subgraph Pipeline2["管线二：Task 6F/6G 物理分析与全身控制工具链 (孤立运行，未并入历史动作)"]
        WBC["WholeBodyController (src/motion/whole_body_controller.py)"]
        WBC_Targets["WholeBodyControlTargets"]
        ArmIK["src/rig/arm_ik.py<br/>(set_hand_ik_target / HandIK.L/R)"]
        LegIK["src/rig/ik.py<br/>(set_foot_ik_target / FootIK.L/R)"]
        ROM["src/motion/joint_limits.py<br/>(JointModel / validate_pose_rom)"]
        CoM_Calc["src/motion/rigid_link.py<br/>(compute_whole_body_com)"]
        Kin_Calc["src/motion/body_kinematics.py<br/>(BodyKinematicsTracker)"]
        Inertia_Calc["src/motion/body_inertia.py<br/>(WholeBodyInertiaState)"]
        Contact_Calc["src/motion/contact_model.py<br/>(MultiContactState / SupportType)"]
        
        WBC_Targets --> WBC
        WBC -->|驱动手脚 IK| ArmIK
        WBC -->|驱动双腿 IK| LegIK
        WBC -->|事后读取校验| ROM
        WBC -->|事后只读求算| CoM_Calc
        RigDirect -.->|事后姿态采样| Kin_Calc
        Kin_Calc -.->|事后速度输入| Inertia_Calc
        RigDirect -.->|事后距离检测| Contact_Calc
    end

    subgraph Pipeline3["管线三：6G-C 原型脚本与测试演示 (硬编码目标摆拍)"]
        ProtoScript["run_contact_obstacle_integration.py / test_16"]
        HardcodedTargets["硬编码静态目标姿态 (t1..t5)<br/>(手脚坐标直接人工写死)"]
        
        HardcodedTargets --> WBC
        ProtoScript -->|按帧循环执行静态目标并插帧| WBC
    end
```

### 真实调用链核心审计事实：
1. **历史动作管线（管线一）完全独立**：`StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction` 在执行中，直接通过 `ContactConstraintAdapter` 和各自私有的 `apply_upper_body` 函数写入 Blender 骨架。**它们完全不调用 `WholeBodyController`，也不调用 `JointModel` ROM 校验，也不调用 `ContactModel`**。
2. **物理分析模块（管线二）仅为事后只读遥测**：`rigid_link.py`（CoM）、`body_kinematics.py`（速度）、`body_inertia.py`（转动惯量与角动量）、`contact_model.py`（接触间隙与支撑分类）目前只对已生成的 Blender 姿态进行后处理读取，并将计算出的浮点数/向量写入 `MotionState.params` 字典。**它们对骨骼姿态的生成没有任何前向驱动、约束反馈或闭环控制作用**。
3. **障碍物原型（管线三）是静态摆拍而不是动作生成**：`run_contact_obstacle_integration.py` 之所以呈现僵硬的 30 帧固定切片，是因为它没有通过任何 `MotionAction` 生成连续运动学曲线，而是直接在 Python 中写死了 5 组静态坐标赋予 `WholeBodyControlTargets`，由 `WholeBodyController` 强行将骨骼吸附在目标点上。

---

## 3. 目标生产级架构图 (Target Production Architecture)

系统最终必须收敛并合流为**唯一定义的单向正向驱动与物理闭环数据流**：

```mermaid
flowchart TD
    Sequencer["动作编排与规划层<br/>(MotionPlanner / ActionSequencer)"]
    
    subgraph ActionLayer["动作生成层 (MotionAction)"]
        ActionImpl["具体动作实现<br/>(StartStopWalk / Run / Sprint / Vault / WallRun)"]
        AnalyticalGait["根节点解析轨迹 + 步态调度器 + 相位发生器<br/>(Root Kinematics & Foot Step Schedulers)"]
    end
    
    subgraph CoordinationLayer["全身姿态协调与约束层 (WholeBodyController)"]
        WBC_Core["WholeBodyController 统一协调器"]
        TargetSpec["WholeBodyControlTargets<br/>(Root pos/yaw, Pelvis, Trunk FK, Hand/Foot Targets)"]
        ROM_Enforce["关节生理活动范围约束强制截断<br/>(JointModel ROM Enforcement)"]
        IK_Dispatch["四肢对称双骨骼 IK 统一解算<br/>(LegIK + ArmIK World Space Solvers)"]
    end
    
    subgraph ExecutionLayer["物理骨架执行层 (Blender Armature)"]
        Armature["19 骨骼刚性连杆骨架与控制器<br/>(CharacterArmature, FootIK, HandIK)"]
    end
    
    subgraph TelemetryLayer["运动感知与物理遥测层"]
        Kinematics["微分运动学跟踪<br/>(BodyKinematicsTracker -> Velocities)"]
        Inertia["惯性张量与全连杆角动量<br/>(BodyInertia -> Momentum)"]
        CoM_Eval["加权多刚体物理质心<br/>(rigid_link -> Whole-Body CoM)"]
        Contact_Eval["多部位接触几何约束与支撑状态机<br/>(ContactModel -> MultiContactState)"]
    end
    
    subgraph StateUpdate["统一状态容器 (MotionState)"]
        StateData["MotionState<br/>(Pos, Vel, Accel, Mode, Contacts, CoM, Inertia, Telemetry)"]
    end

    Sequencer -->|规划下一个动作| ActionImpl
    ActionImpl --> AnalyticalGait
    AnalyticalGait -->|每帧输出连续全身目标| TargetSpec
    TargetSpec --> WBC_Core
    WBC_Core --> ROM_Enforce
    ROM_Enforce --> IK_Dispatch
    IK_Dispatch -->|写入骨骼并评估| Armature
    
    Armature --> Kinematics
    Armature --> CoM_Eval
    Armature --> Contact_Eval
    Kinematics --> Inertia
    
    Kinematics --> StateData
    Inertia --> StateData
    CoM_Eval --> StateData
    Contact_Eval --> StateData
    
    StateData -.->|物理状态与支撑拓扑反馈| ActionImpl
    StateData -.->|连续动作衔接状态| Sequencer
```

### 目标架构的关键规范：
1. **动作层 (MotionAction)** 负责“期望什么”：通过运动学生成连续的根节点移动、质心高度起伏、四肢末端在世界空间的期望轨迹与接触意图。
2. **协调层 (WholeBodyController)** 负责“合法落地”：统一接收目标，执行解剖 ROM 强制限制，求解 Arm IK 与 Leg IK，确保四肢末端精准达标，杜绝历史私有姿态函数绕过 IK/ROM 的做法。
3. **遥测层 (Kinematics / Inertia / ContactModel)** 负责“真实评估”：从解算后的骨架中提取真实速度、真实角动量、真实质心与真实接触间隙，写入 `MotionState`，为下一帧动作或状态机转移提供反馈依据。

---

## 4. 模块数据流合同 (Module Data Flow Contracts)

下表对工程中涉及运动生成的全部 11 个核心模块制定严格的数据合同：

| 模块名称 | 主要输入 (Input) | 主要输出 (Output) | 坐标系 (Coords) | 单位 (Units) | 调用者 (Caller) | 被调用者 (Callee) | 状态读写责任 (State R/W) | 每帧执行阶段 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MotionPlanner** | 动作序列名列表, `initial_state` | 连续 `List[MotionState]`, 帧范围 | World Space | m, deg, s | 顶层管线 / 运行脚本 | 各具体 `MotionAction` | 读初始状态，聚合最终状态轨迹 | 动作序列级调度 |
| **MotionAction** | `MotionState`, `MotionRuntimeContext` | `ActionExecutionResult` (含 per-frame 姿态与步态) | World + Local | m, m/s, deg | `MotionPlanner` | 步态调度器, `WholeBodyController` | 读前序状态，生成新状态帧序列 | 帧循环驱动核心 |
| **MotionState** | 瞬时运动学参数, 接触字典, 遥测字典 | 不可变快照对象，支持 `.to_dict()`, `.clone_with()` | World Space | m, m/s, m/s², deg | `MotionAction`, 各遥测模块 | 纯数据类，无下游调用 | 承载单帧完整物理与运动状态 | 状态持久化容器 |
| **WholeBodyController** | `WholeBodyControlTargets` (根位姿, 躯干FK, 四肢IK目标) | `WholeBodyControlResult` (追踪误差, ROM合规性, CoM) | World (外) / Local (内) | m, deg, mm | `MotionAction` (目标) / 原型脚本 | `arm_ik`, `ik`, `joint_limits`, `rigid_link` | 写入 Blender 骨架与 IK Empty 物体 | 帧姿态求解与写入 |
| **ContactConstraintAdapter** | 锁定/摆动足部世界坐标, 步态相位 | 底层锁定状态, `ContactPointState` | World Space | m, mm, deg | 现有 `MotionAction` | `foot_contact.py`, `ik.py` | 读写 `FootIK` 物理层约束与父级 | 姿态应用前/后 |
| **src/rig/ik.py** | 双腿踝关节世界目标 `(x, y, z)`, 偏航角 | `FootIK.L/R` 物体变换, 膝关节弯曲姿态 | World $\rightarrow$ Bone Local | m, deg | `ContactConstraintAdapter`, `WBC` | Blender `IK` Constraint Solver | 写入 `FootIK` 与 `KneePole` 物体位姿 | IK 求解器阶段 |
| **src/rig/arm_ik.py** | 双手手腕世界目标 `(x, y, z)`, 3D 旋转目标 | `HandIK.L/R` 物体变换, 肘关节后外侧弯曲 | World $\rightarrow$ Bone Local | m, deg | `WholeBodyController` | Blender `IK` + `CopyRotation` | 写入 `HandIK` 与 `ElbowPole` 物体位姿 | IK 求解器阶段 |
| **joint_limits.py** | Blender 评估骨骼当前局部旋转 | ROM 越界诊断列表, 截断后欧拉角 | Bone Local Axis | rad, deg | `WholeBodyController` | 纯数学算法，无外部依赖 | 只读校验；截断模式下覆盖骨骼旋转 | IK 求解后校验/截断 |
| **rigid_link.py** | Armature 对象当前全局矩阵与骨骼变换 | 全身物理质心 `com_world`, 分段质心 | World Space | m, kg | `WholeBodyController`, 遥测器 | 纯数学矩阵变换 | 只读前向运动学计算，无写权限 | 姿态生成后遥测 |
| **body_kinematics.py** | 连续多帧骨架姿态快照 `BodyPoseSnapshot` | 根节点/CoM/关节/连杆线速度与角速度 | World + Bone Local | m/s, rad/s | 动作后处理 / 测试套件 | 纯数值有限差分 | 只读微分推导，注入 `MotionState.params` | 姿态生成后遥测 |
| **body_inertia.py** | 连杆几何规范, 姿态快照, 速度状态 | $3\times 3$ 惯性张量, 自转/轨道角动量 | World Space (CoM) | $\text{kg}\cdot\text{m}^2$, $\text{kg}\cdot\text{m}^2/\text{s}$ | 动作后处理 / 测试套件 | 纯代数张量运算 | 只读张量合成，注入 `MotionState.params` | 速度学求出后遥测 |
| **contact_model.py** | Armature 骨架, 环境表面列表, 四肢目标 | `MultiContactState` (间隙/穿透/滑移/支撑类型) | World Space | m, mm, 模长无量纲 | 动作后处理 / 视口标记更新 | 纯几何相交与凸包检测 | 只读几何约束评估，更新可视化标记 | 姿态解算后物理校验 |

---

## 5. 历史动作复用与实现关系全表 (Historical Action Reuse Matrix)

为彻底防止重新造轮子或编造伪动作，全工程对历史已验证的 6 大基础动作建立唯一权威实现入口映射表：

| 动作标识 | 任务编号 | 真实源码实现入口 | 步态调度核心机制 | 使用的 IK / FK 机制 | 接触锁定与防滑机制 | Blender 姿态生成路径 | 生产集成状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Walk Cycle** | Task 5A | `src/motion/walk_cycle.py` $\rightarrow$ `generate_walk_cycle` | 固定循环周期（36 帧/步），归一化相位 $u \in [0, 1)$ | 两骨腿部 IK（`FootIK.L/R`）；双臂固定正弦波 FK | 每步半周期足部锁定；摆动期正弦抬升 | 直接调用 `set_foot_ik_target` + `set_bone_rotation` 插帧 | **独立原型算法**（未封装为 MotionAction） |
| **Forward Walk** | Task 5B | `src/motion/forward_walk.py` $\rightarrow$ `generate_forward_walk` | 沿 $+Y$ 直线匀速前向跨步，步幅累加调度 | 两骨腿部 IK；上身前倾与骨盆起伏经验 FK | `lock_foot_contact` 锁定支撑脚；摆腿跨步 | 直接调用 `move_character_root_with_support` 插帧 | **独立原型算法**（未封装为 MotionAction） |
| **StartStopWalkAction** | Task 5C / 6A | `src/motion/start_stop_walk.py` $\rightarrow$ `generate_start_stop_walk`<br/>`src/motion/framework.py` $\rightarrow$ `StartStopWalkAction` | `build_step_schedule`（7 个协调半步）；余弦平滑 $C^1$ 速度曲线 $v(\tau)$（0 $\rightarrow$ 0.24 $\rightarrow$ 0 m/s） | 两骨腿部 IK；骨盆下沉、躯干倾角与反向摆臂经验 FK | `lock_foot_contact` 世界锁定，漂移 $< 0.05\text{ mm}$；摆动相正弦抬升 | 通过 `ContactConstraintAdapter` + `BlenderPoseApplicator` 插帧 | **已完全封装为标准 MotionAction** |
| **RunAction** | Task 6B | `src/motion/run_cycle.py` $\rightarrow$ `RunAction` | 腾空相步态调度（半步 12 帧，支撑 7 帧，单腾空 5 帧）；高速周期 $v = 1.0\text{ m/s}$ | 两骨腿部 IK；跑动大幅屈肘与大摆幅手臂 FK | 支撑期足底锁定；双脚同时离地进入 `flight` 状态 | 通过 `ContactConstraintAdapter` 驱动双腿 IK 与根节点位移 | **已完全封装为标准 MotionAction** |
| **SprintStartAction** | Task 6C | `src/motion/sprint_start.py` $\rightarrow$ `SprintStartAction` | 三阶段爆发式起跑调度（准备预备 12 帧 $\rightarrow$ 蹬地起步 24 帧 $\rightarrow$ 冲刺加速）；峰值 $v = 3.6\text{ m/s}$ | 两骨腿部 IK；大幅躯干前倾与大步幅交替摆臂 FK | 强力后蹬锁定；长步幅腾空迈步 | 通过 `contact_adapter` 驱动并平滑过渡到稳态冲刺 | **已完全封装为标准 MotionAction** |
| **SprintBrakeAction** | Task 6D | `src/motion/sprint_brake.py` $\rightarrow$ `SprintBrakeAction` | 4 阶段主动急停制动调度（后仰缓冲 $\rightarrow$ 强力前掌滑移制动 $\rightarrow$ 步幅收束 $\rightarrow$ 停步）；加速度达 $-6.0\text{ m/s}^2$ | 两骨腿部 IK；躯干向后反向倾角抵消惯性 | 允许受控前向滑移制动；最终平稳合拢双足锁定 | 通过 `contact_adapter` 驱动受控减速与停止锁定 | **已完全封装为标准 MotionAction** |

---

## 6. 当前工程断裂点与架构缺口审计 (Architectural Break Points)

严禁对架构现实进行粉饰。磁盘代码显示当前系统存在以下明确断裂点：

### 6.1 已经真实集成的部分 (Truly Integrated)
1. 19 骨骼层级与 13 占位网格装配体系（`src/rig/builder.py`）；
2. 双腿两骨 IK、极向引导与世界空间达程保护（`src/rig/ik.py`）；
3. 双脚世界空间零漂移锁定与解锁机制（`src/rig/foot_contact.py`，实测漂移严格 $< 0.005\text{ mm}$）；
4. 四大核心运动动作（`StartStopWalkAction`, `RunAction`, `SprintStartAction`, `SprintBrakeAction`）在各自的运动学规划内高度成熟、平滑、零穿穿帮、零超程；
5. `MotionPlanner` 能够按顺序串联上述动作，并在动作边界无缝衔接位移与速度。

### 6.2 仅通过适配器连接或单向只读的部分 (Connected via Adapter / Read-Only Only)
1. **`WholeBodyController` 未接入现有动作**：`WholeBodyController` 作为 Task 6F-D 的成果，理论上具备同时调度双臂 IK、双腿 IK、骨盆与躯干的能力，但**所有现有的 `MotionAction` 根本没有调用它**，仍然通过旧有的 `ContactConstraintAdapter` 和硬编码私有上身函数工作。
2. **`ContactModel` 仅在事后做几何检测**：`src/motion/contact_model.py` 拥有完善的接触记录（`ContactRecord`）、生命周期（`ContactLifecycle`）和支撑状态机（`SupportType`），但**它目前完全不参与前向控制**，既不负责锁定脚部，也不向上层传递法向推力约束，仅在每一帧姿态生成完毕后，计算一下当前脚底离地面的距离与滑移量。
3. **CoM、惯性与动量未参与姿态平衡**：`rigid_link.py`、`body_kinematics.py`、`body_inertia.py` 能够极其精确地计算全身质心位置、线速度、空间角速度、惯性张量与自转/轨道角动量，但这些物理量仅仅被写入 `MotionState.params` 作为日志和字典数据存储，**没有任何控制器读取质心来调整躯干倾角，没有任何反作用力反馈**。

### 6.3 被演示脚本绕过与硬编码伪造的部分 (Bypassed by Demo Scripts)
1. **障碍物演示脚本彻底脱离了动作系统**：
   * 在 `run_contact_obstacle_integration.py` 中，角色在不同障碍物之间的姿态展示完全没有调用任何 `MotionAction`，没有经过任何物理步态调度；
   * 脚本直接构造离散静态目标（例如金库跳箱支撑、脚踩竖直墙、双手抓单杠），直接调用 `WholeBodyController.execute_frame()` 将角色瞬间定位并硬性保持 30 帧；
   * **这是导致障碍物原型僵硬、缺乏连续运动学过渡的根本原因**。它是一个纯静态的姿态评估测试，不是连续程序化动画系统。
2. **尚未存在生产级障碍物动作 (Missing Parkour MotionActions)**：
   * 系统中目前**完全不存在**针对障碍物交互的动作类（如 `VaultAction` 撑越动作、`WallRunAction` 蹬墙动作、`LedgeClimbAction` 攀爬动作、`JumpHurdleAction` 跨越动作）；
   * 在没有编写这些具体动作的连续运动学生成器之前，试图用一段连续时间线同时展示行走和障碍物接触，必然会导致伪造滑行（如 R2 返工中的单腿平移 2 米）或静态片段切片（如 R3 原型中的 30 帧静止展台）。

---

## 7. 架构合流路线图 (Integration Convergence Path: R3B 及后续规划)

为了彻底根除上述断裂点，后续阶段必须按以下顺序实施合流，禁止跳步：

1. **第一步（底层调用链合流）**：
   * 将 `BlenderPoseApplicator` 与 `ContactConstraintAdapter` 进行统一重构，使其内部调度收敛至 `WholeBodyController`；
   * 确保 `StartStopWalkAction`、`RunAction` 在生成每一帧时，统一输出 `WholeBodyControlTargets` 交由 `WholeBodyController` 执行解算与 ROM 校验，消除姿态生成的双轨制。
2. **第二步（接触模型前向闭环）**：
   * 改造 `src/rig/foot_contact.py`，将其底层的 `lock_foot_contact` / `unlock_foot_contact` 与 `ContactModel` 的 `ContactRecord`（`ESTABLISHED` / `RELEASED`）直接绑定；
   * 使足部和手部的接地/抓握锁定直接成为 `ContactModel` 约束执行的具象化体现，消除两套接触状态字段的不一致。
3. **第三步（规范化实现首个连续障碍物交互动作）**：
   * 严禁再在展示脚本中硬编码摆放身体姿态；
   * 正式构建标准的 `VaultTouchAction(MotionAction)` 或 `StepOverObstacleAction(MotionAction)`，从 `MotionState` 继承前向速度，通过严谨的时间轴运动学曲线计算身体腾空、单手触碰跳箱支撑、身体推离与双脚落地的完整连续轨迹，彻底解决“僵硬片段”问题。
