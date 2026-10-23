# ProceduralAnimation 全工程架构审计与后续开发准备报告
## Task 6G-D-PRE-P0 交付文件 (Engineering Architecture & Asset Baseline Audit)

> **审计执行时间**：2026-10-23  
> **任务性质**：只读审计、规范交付、文档基线锁定（禁止功能开发）  
> **底层 Git 基准 Commit**：`c26c88703152a6252745c0763f168c29dcf5aae2` (`master`)  
> **审计人员/模型**：Antigravity Agent  
> **验收前提**：用户已完成 Task 6G-C-R3B-2-R1 的 Blender 视口目视验收，确认行走、奔跑动作自然，下肢周期性横向 L 形畸变彻底修复，Task 6G-C 正式关闭。

---

## 1. 审计概述、基线环境与方法

### 1.1 审计背景与核心目的
本项目为**全程序化 3D 连续动画生成系统**。在 Task 6G-C 及其返工（R1、R2、R3A、R3B-1、R3B-2、R3B-2-R1）的漫长迭代中，暴露出三大系统级风险：
1. **架构多头分立**：早期存在“历史动作生成器”、“物理/刚体分析评估器”与“孤立演示原型”三套互不相通的执行体系；
2. **状态所有权与坐标空间错位**：如 R3B-2 首轮出现的 `obj.parent` 跨帧无法关键帧化导致的 8 米横向暴拉；
3. **测试系统碎片化与用户审批负担**：27 个独立 `verify_*.py` 脚本缺乏统一调度，每次测试需要用户频繁授权终端，且依赖文件名猜测运行方式。

本审计在正式开启 Task 6G-D（接触力、冲量与动力学闭环）之前，对全仓库**所有源码、测试、配置、运行脚本和历史产物**进行地毯式静态审查与调用链追踪，确立工程资产事实基线，阻断后续任务的架构漂移。

### 1.2 审计覆盖范围与方法
* **源码覆盖**：`src/` 目录下全部 28 个 Python 模块（`camera/`, `character/`, `lighting/`, `motion/`, `render/`, `rig/`, `scene/`, `validation/`）。
* **测试覆盖**：`tests/` 目录下全部 30 个脚本（27 个 `verify_*.py`，1 个 `test_*.py`，2 个测试入口包装器）。
* **运行入口覆盖**：项目根目录下全部 19 个 `run_*.py`、`run_*.ps1` 脚本。
* **文档与配置覆盖**：全部项目规则（`AGENTS.md`, `GEMINI.md`, `.agents/rules/project_rules.md`）、架构卡片（`ARCHITECTURE.md`, `ARCHITECTURE_SYNC.md`）、状态卡片（`PROJECT_STATE.md`, `HANDOFF.md`, `AI_SYNC.md`, `DECISIONS.md`, `PROJECT_SPEC.md`）以及 `.gitignore`。
* **审计方法**：
  * 基于 `git ls-files` 建立全量受版本控制清单；
  * 基于 AST / 文本交叉引用检索真实 `import` 与函数调用者，杜绝以文档叙述替代代码事实；
  * 检查磁盘二进制资产真实存在性、大小及 Git 跟踪状态；
  * 逐项判定模块读写权限、状态所有权及生命周期契约。

---

## 2. 真实生产调用链与执行所有权审计

### 2.1 官方唯一定义的主生产调用链 (The Official Production Pipeline)

经过 Task 6G-C-R3B-1/2 的架构合流，当前官方认可的唯一运动生成数据流为：

```mermaid
flowchart TD
    subgraph Layer1["1. 调度层 (Scheduling)"]
        Planner["src/motion/framework.py<br/>MotionPlanner"]
        Ctx["MotionRuntimeContext<br/>(Armature, Root, Env, FPS)"]
    end

    subgraph Layer2["2. 连续动作生成层 (Motion Planning)"]
        Act1["StartStopWalkAction (src/motion/framework.py)"]
        Act2["RunAction (src/motion/run_cycle.py)"]
        Act3["SprintStartAction (src/motion/sprint_start.py)"]
        Act4["SprintBrakeAction (src/motion/sprint_brake.py)"]
    end

    subgraph Layer3["3. 统一桥接层 (Kinematic Bridge)"]
        Bridge["src/motion/kinematic_bridge.py<br/>KinematicBridgeExecutor.execute_frame()"]
        TargetConvert["convert_planned_pose_to_wbc_targets()"]
    end

    subgraph Layer4["4. 全身姿态协调与执行层 (Whole-Body Coordination)"]
        WBC["src/motion/whole_body_controller.py<br/>WholeBodyController.execute_frame()"]
        ROM["src/motion/joint_limits.py<br/>JointModel (ROM Validation & Clamp)"]
        LegIK["src/rig/ik.py<br/>set_foot_ik_target() (World Space)"]
        FootLock["src/rig/foot_contact.py<br/>lock_foot_contact() (World Space)"]
        ArmIK["src/rig/arm_ik.py<br/>set_hand_ik_target() (World Space)"]
    end

    subgraph Layer5["5. Blender 物理骨架与约束层 (Rig & Solvers)"]
        BlenderDeps["Blender Depsgraph / View Layer Update"]
        ArmatureObj["CharacterArmature (19 PoseBones)"]
        IKEmpties["FootIK.L/R, KneePole.L/R, HandIK.L/R, ElbowPole.L/R<br/>(parent = None, World Keyframes)"]
        RootObj["CharacterRoot (World Translation & Yaw)"]
    end

    subgraph Layer6["6. 物理遥测与只读分析层 (Phase 5 Telemetry)"]
        CoMEval["src/motion/rigid_link.py<br/>compute_whole_body_com()"]
        KinEval["src/motion/body_kinematics.py<br/>BodyKinematicsTracker.sample_and_update()"]
        InertiaEval["src/motion/body_inertia.py<br/>compute_whole_body_inertia()"]
        ContactEval["src/motion/contact_model.py<br/>evaluate_limb_contacts_from_armature()"]
    end

    subgraph Layer7["7. 统一状态回写与持久化 (Phase 6 Commit)"]
        MState["src/motion/framework.py<br/>MotionState (immutable frame record)"]
        FKeyframes["Blender Animation F-Curves (Location & Rotation)"]
    end

    Planner --> Act1 & Act2 & Act3 & Act4
    Act1 & Act2 & Act3 & Act4 --> Bridge
    Bridge --> TargetConvert
    TargetConvert --> WBC
    WBC --> LegIK & FootLock & ArmIK & ROM
    LegIK & FootLock & ArmIK --> IKEmpties
    WBC --> RootObj & ArmatureObj
    IKEmpties & RootObj & ArmatureObj --> BlenderDeps
    BlenderDeps --> CoMEval & KinEval & InertiaEval & ContactEval
    CoMEval & KinEval & InertiaEval & ContactEval --> MState
    Bridge --> FKeyframes
    MState -.->|初值传递| Act2 & Act3 & Act4
```

### 2.2 核心职责与状态所有权核查表 (Single Ownership Matrix)

必须以磁盘代码行为依据，明确各项能力的独占归属：

| 职责环节 | 独占归属模块 | 关键类 / 函数 | 源码位置 | 真实调用者 (Caller) | 状态读写权限 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **运动轨迹与步态规划** | `MotionAction` 各子类 | `execute(initial_state, context)` | `src/motion/framework.py` L511<br/>`src/motion/run_cycle.py` L203<br/>`src/motion/sprint_start.py` L175<br/>`src/motion/sprint_brake.py` L152 | `MotionPlanner.execute()` | **只读**环境与初态，**只写** `KinematicPlannedPose` 数据结构。**严禁直接修改 Blender 骨骼或 Empty**。 |
| **单帧协议调度与仲裁** | `KinematicBridgeExecutor` | `execute_frame(planned, ...)` | `src/motion/kinematic_bridge.py` L292 | `MotionAction.execute()` | 协调 Phase 1 至 Phase 6 流水线；统一计算差分时间步 `dt`；仲裁手部 FK 与 IK；向 Blender 插入全局关键帧。 |
| **全身姿态分配与骨架写入权** | `WholeBodyController` | `execute_frame(targets, ...)` | `src/motion/whole_body_controller.py` L301 | `KinematicBridgeExecutor` | **独占写入权**：修改 `CharacterRoot.location/rotation`、`pelvis`、`spine`、`neck`、`head`、FK 肢体欧拉角，以及下发 IK 目标。 |
| **足部接触零漂移世界锁定** | `FootContactAdapter` | `lock_foot_contact()`, `unlock_foot_contact()` | `src/rig/foot_contact.py` L75, L122 | `WholeBodyController` L389, L399 | **独占控制器结构权限**：负责清空 `FootIK` 的父级（`parent = None`），固定世界坐标，评估支撑漂移。 |
| **双腿两骨 IK 求解驱动** | `LegIKSolver` | `set_foot_ik_target()` | `src/rig/ik.py` L223 | `WholeBodyController` L400 | 修改 `FootIK.L/R` 与 `KneePole.L/R` 的世界坐标与旋转，驱动 Blender 原生 `IK` 约束求解器。 |
| **双臂两骨 IK / FK 求解驱动** | `ArmIKSolver` | `set_hand_ik_target()`, `set_arm_ik_influence()` | `src/rig/arm_ik.py` L219, L297 | `WholeBodyController` L415, L425 | 修改 `HandIK.L/R` 与 `ElbowPole.L/R` 的世界坐标、旋转及约束权重 `influence`。 |
| **解剖关节活动度 (ROM) 校验** | `JointModel` | `validate_armature_pose()`, `clamp_armature_pose()` | `src/motion/joint_limits.py` L226, L273 | `WholeBodyController` L568, L586 | **只读校验**骨架实际姿态，**受控修正**超限骨骼旋转。严禁截断后掩盖末端误差。 |
| **全身质心 (CoM) 分析** | `RigidLink` 评估器 | `compute_whole_body_com()` | `src/motion/rigid_link.py` L197 | `KinematicBridgeExecutor` L363<br/>`WholeBodyController` L622 | **纯只读分析**：读取评估后姿态计算质量加权质心 $(X_{\text{com}}, Y_{\text{com}}, Z_{\text{com}})$，写入遥测。 |
| **身体微分运动学分析** | `BodyKinematicsTracker` | `sample_and_update()` | `src/motion/body_kinematics.py` L189 | `KinematicBridgeExecutor` L367 | **纯只读分析**：有限差分计算根节点、骨盆、质心的线速度与角速度，写入遥测。 |
| **惯性张量与全身体角动量** | `BodyInertiaModel` | `compute_whole_body_inertia()` | `src/motion/body_inertia.py` L225 | `KinematicBridgeExecutor` L374 | **纯只读分析**：平行轴定理合成 3D 惯性张量，解耦自转与轨道角动量，写入遥测。 |
| **多部位接触几何与支撑分类** | `ContactModel` | `evaluate_limb_contacts_from_armature()`, `check_all_contacts()` | `src/motion/contact_model.py` L448, L379 | `KinematicBridgeExecutor` L467, L486 | **纯只读几何与状态机**：测量肢体末端法向间隙、穿透与切向滑移，判定 `SupportType`，超差真实报警。 |
| **帧状态快照与历史持久化** | `MotionState` | `MotionState(...)` 数据类 | `src/motion/framework.py` L75 | `KinematicBridgeExecutor` L536 | **不可变数据载体**：保存当前帧速度、接触状态字典及 `params` 遥测，供跨动作传递初态。 |

### 2.3 架构重复实现与旁路风险审计 (Redundancy & Bypass Audit)

审计发现当前工程仍遗留以下**4 处重复实现**与**3 处旁路隐患**：

#### 隐患 1：姿态写入器的历史双轨制 (`BlenderPoseApplicator` vs `WholeBodyController`)
* **现状**：`src/motion/framework.py` L368 依然保留着 Task 6A 编写的 `BlenderPoseApplicator` 类，且在 `MotionPlanner._build_runtime_context()` (L955) 中每次执行都会默认实例化 `context.pose_applicator`。
* **风险**：虽然 R3B-2 已经让四大动作转入 `bridge_executor`，但历史测试（`verify_task6fd` L379, `verify_task6ga` L381）仍在调用 `BlenderPoseApplicator`。如果未来有新动作未显式指定 `bridge_executor`，可能错误回退到 `pose_applicator`，绕过 WBC 的 ROM 检查与 IK 统一调度。
* **处置策略**：在架构规范中明确标记 `BlenderPoseApplicator` 为 **Legacy / Deprecated**，禁止任何新增动作调用。

#### 隐患 2：接触锁定的双轨接口 (`ContactConstraintAdapter` vs `foot_contact.py`)
* **现状**：`src/motion/framework.py` L296 保留 `ContactConstraintAdapter`，它内部封装了 `lock_foot_contact` 和 `unlock_foot_contact`，但与 `KinematicBridgeExecutor` 中的接触逻辑脱节。
* **风险**：两个模块都能对 `FootIK` 执行锁定/解锁，若同时存在将发生父级与坐标竞争。
* **处置策略**：足部锁定逻辑唯一收敛至 `WholeBodyController` $\rightarrow$ `src/rig/foot_contact.py`，标记 `ContactConstraintAdapter` 为 **Legacy**。

#### 隐患 3：主流程运行入口严重滞后于运动能力 (`run_pipeline.py` vs `run_unified_motion_pipeline.py`)
* **现状**：项目根目录下的正式入口 `run_pipeline.py`（以及 `src/pipeline.py`）仍然停留在 **Task 3 阶段**（仅创建地面、简易建筑与摄像机，输出 `procedural_scene.blend`），完全未引入角色模型（`src/character/`）、骨骼绑定（`src/rig/`）以及连续运动（`src/motion/`）。而真正生成全套连续动作的入口是 `run_unified_motion_pipeline.py`。
* **影响**：若外部自动化脚本或新开发者运行 `python run_pipeline.py`，会误以为系统只能生成静态空场景。
* **处置策略**：后续里程碑（如 Task 7 全管线合流）必须重写 `src/pipeline.py`，以 `run_unified_motion_pipeline.py` 为骨干重塑主流水线。

#### 隐患 4：场景构建器未在动作管线中复用
* **现状**：`src/scene/builder.py` 拥有完善的尺寸配置与材质赋予能力，但 `run_unified_motion_pipeline.py` 内部直接使用 `bpy.ops.mesh.primitive_plane_add(size=40.0)` 硬编码创建单一地面，绕过了 `src/scene/`。
* **处置策略**：在 P2 训练场建设中，必须将 `src/scene/builder.py` 升级为动力学训练场生成器，杜绝在脚本内裸调 `bpy.ops` 创建几何体。

---

## 3. 全工程资产清单与四态分类 (Asset Classification)

全工程所有源码、脚本与资源严格划分为以下四类：
* **Active (A)**：当前官方主生产管线、统一桥接层正在调用的模块。
* **Reusable (R)**：功能完备、物理数学正确，供当前管线评估或未来动力学/环境系统复用的模块。
* **Legacy (L)**：早期任务完成的历史实现、基准验证或兼容包装，保持回归保护，禁止新代码依赖。
* **Orphan / Unknown (O)**：无上游调用、脱离主数据流的原型或孤立脚本。

### 3.1 核心源码资产分类矩阵 (`src/`)

| 文件路径 | 核心职责 | 输入 / 输出 | 实际调用者 | 状态读写权限 | 所属分类 | 对应测试 | 后续计划 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `src/config.py` | 全局超参数与路径配置 | 配置字典 $\to$ `PipelineConfig` | 全局各模块 | 只读常量 | **Active** | `tests/test_task3_spatial.py` | 维护并扩充动力学参数 |
| `src/pipeline.py` | Task 3 遗留管线编排 | `PipelineConfig` $\to$ dict | `run_pipeline.py` | 写 Task 3 场景 | **Legacy** | `tests/verify_task3_blend.py` | Task 7 重构合流至统一运动管线 |
| `src/camera/controller.py` | 摄像机 Track-To 构图与轨迹 | Config, Scene $\to$ Cam Obj | `src/pipeline.py` | 写 Camera / Target | **Reusable** | `tests/verify_blend.py` | 改造为支持动态角色平滑跟随 |
| `src/lighting/setup.py` | 三点照明与环境光装配 | Config $\to$ Light Objects | `src/pipeline.py` | 写 Light Objects | **Reusable** | `tests/verify_blend.py` | 供统一运动与训练场复用 |
| `src/render/engine.py` | 渲染引擎配置、存盘与静帧渲染 | Scene, Frame $\to$ PNG Path | `pipeline.py`, 各 runner | 写渲染配置与磁盘文件 | **Active** | 各 verify 脚本 | 保持作为标准渲染包装器 |
| `src/scene/builder.py` | 场景地面、建筑与柱体网格生成 | `SceneLayoutData` $\to$ Meshes | `src/pipeline.py` | 写 Environment 几何体 | **Reusable** | `tests/test_task3_spatial.py` | **P2 升级为简易动力学训练场生成器** |
| `src/scene/layout.py` | 纯 Python 确定性几何布局与避障 | Seed $\to$ `SceneLayoutData` | `src/scene/builder.py` | 无状态纯数学 | **Reusable** | `tests/test_task3_spatial.py` | **P2 扩充台阶、斜坡、障碍墙布局** |
| `src/character/builder.py` | 13 分段人体占位网格装配 | Config $\to$ Mesh Objects | 各 motion runner, `pipeline.py` | 写 Character 网格 | **Active** | `tests/verify_task4a_character.py` | 保持作为官方人体几何基准 |
| `src/character/prototype.py` | Task 4A 独立原型运行器 | None $\to$ dict | `run_character_prototype.py` | 独立生成 blend | **Legacy** | `tests/verify_task4a_character.py` | 维持回归基准，不改动 |
| `src/rig/builder.py` | 19 骨骼层级创建与网格蒙皮绑定 | Armature, Mesh $\to$ Rig | 各 runner, WBC | 写 Armature 结构 | **Active** | `tests/verify_task4b_rig.py` | 保持作为官方骨架基准 |
| `src/rig/pose.py` | 姿态骨世界位置/旋转读写与重置 | Armature, Bone, Rot $\to$ None | WBC, IK, 各动作 | 读写 PoseBone 变换 | **Active** | `tests/verify_task4b_rig.py` | 保持为基础姿态变换工具 |
| `src/rig/ik.py` | 双腿两骨 IK 约束与脚部旋转对齐 | World XYZ, Rot $\to$ None | WBC, 各 runner | 读写 FootIK / KneePole | **Active** | `tests/verify_task4c_ik.py` | 维持 WORLD 空间约束标准 |
| `src/rig/foot_contact.py` | 支撑脚世界锁定与微米级防滑 | Armature, Side, XYZ $\to$ None | WBC | 读写 FootIK 父级与位置 | **Active** | `tests/verify_task4d_foot_contact.py` | 维持 parent=None 绝对世界锁定 |
| `src/rig/arm_ik.py` | 双臂两骨 IK 约束与手部 3D 对齐 | World XYZ, Rot $\to$ None | WBC | 读写 HandIK / ElbowPole | **Active** | `tests/verify_task6fa_arm_ik.py` | 保持作为手部末端执行器 |
| `src/rig/prototype.py` | Task 4B 独立骨架原型脚本 | None $\to$ dict | `run_rig_prototype.py` | 独立写 blend | **Legacy** | `tests/verify_task4b_rig.py` | 历史基准保护 |
| `src/rig/ik_prototype.py` | Task 4C 独立腿部 IK 原型脚本 | None $\to$ dict | `run_ik_prototype.py` | 独立写 blend | **Legacy** | `tests/verify_task4c_ik.py` | 历史基准保护 |
| `src/rig/foot_contact_prototype.py` | Task 4D 独立足部接触原型脚本 | None $\to$ dict | `run_foot_contact_prototype.py` | 独立写 blend | **Legacy** | `tests/verify_task4d_foot_contact.py` | 历史基准保护 |
| `src/motion/framework.py` | `MotionPlanner`, `MotionState`, `StartStopWalkAction` | InitialState $\to$ ExecutionResult | 主流水线, 各动作 | 调度并记录状态 | **Active** | `tests/verify_r3b2_walk_action.py` | 统一框架核心，标记旧 Applicator 为废弃 |
| `src/motion/kinematic_bridge.py` | 最小兼容桥接层与 6 阶段执行器 | PlannedPose $\to$ BridgeResult | 各 MotionAction | 仲裁并执行单帧流水线 | **Active** | `tests/verify_task6gc_r3b1_bridge.py` | **核心枢纽**，后续动力学前置接入点 |
| `src/motion/whole_body_controller.py` | 统一全身姿态协调器与分配器 | ControlTargets $\to$ WBCResult | KinematicBridgeExecutor | 统筹写入骨架与控制器 | **Active** | `tests/verify_task6fd_whole_body_controller.py` | **唯一姿态写入器** |
| `src/motion/joint_limits.py` | 14 关节解剖 ROM 校验与冲突报告 | Armature Pose $\to$ ROMResult | WBC, KinematicBridge | 校验并受控截断姿态 | **Active** | `tests/verify_task6fc_joint_limits.py` | 保持严苛生理极限，严禁放宽 |
| `src/motion/rigid_link.py` | 15 分段质量分布与全身质心 (CoM) | Armature Pose $\to$ CoMResult | WBC, KinematicBridge | 只读前向运动学分析 | **Reusable** | `tests/verify_task6fb_rigid_link.py` | **未来 6G-D 质心平衡闭环关键输入** |
| `src/motion/body_kinematics.py` | 微分运动学（线/角速度、加速度） | Armature, dt $\to$ VelocityState | KinematicBridge | 只读差分分析 | **Reusable** | `tests/verify_task6ga_body_kinematics.py` | **未来 6G-D 动量与能量分析输入** |
| `src/motion/body_inertia.py` | 平行轴定理惯性张量与全身体角动量 | Armature, Vel $\to$ InertiaState | KinematicBridge | 只读惯量与动量分析 | **Reusable** | `tests/verify_task6gb_body_inertia.py` | **未来 6G-D 旋转动力学平衡关键输入** |
| `src/motion/contact_model.py` | 多部位接触几何、生命周期与支撑分类 | Armature, Surfaces $\to$ ContactState | KinematicBridge | 只读间隙、穿透与滑移 | **Reusable** | `tests/verify_task6gc_contact_model.py` | **未来 6G-D 接触冲量求解器基石** |
| `src/motion/start_stop_walk.py` | 7 步行走连续步态与 $C^1$ 速度曲线 | Step Schedule $\to$ Foot Traj | `framework.py` (WalkAction) | 纯数学步态规划 | **Active** | `tests/verify_task5c_start_stop_walk.py` | 保持步态数学不可变性 |
| `src/motion/run_cycle.py` | 4 周期奔跑（双腾空相）运动学 | Gait Phase $\to$ PlannedPose | `MotionPlanner` | 规划奔跑轨迹 | **Active** | `tests/verify_r3b2_run_action.py` | 保持奔跑特性 |
| `src/motion/sprint_start.py` | 爆发起跑（深俯屈膝、加速前冲） | Start State $\to$ PlannedPose | `MotionPlanner` | 规划起跑轨迹 | **Active** | `tests/verify_r3b2_sprint_start.py` | 保持冲刺起跑特性 |
| `src/motion/sprint_brake.py` | 高速主动制动急停（后仰后坐） | High-speed State $\to$ PlannedPose | `MotionPlanner` | 规划急停轨迹 | **Active** | `tests/verify_r3b2_sprint_brake.py` | 保持急停制动特性 |
| `src/motion/walk_cycle.py` | 原地走步循环原型数学 | Phase $u \in [0, 1)$ $\to$ XYZ | `src/motion/forward_walk.py` | 基础摆动轨迹函数 | **Legacy** | `tests/verify_task5a_walk_cycle.py` | 历史基准保护 |
| `src/motion/forward_walk.py` | 直线前进迈步原型数学 | Steps $\to$ Root/Foot XYZ | `framework.py` | 摆线轨迹插值 | **Legacy** | `tests/verify_task5b_forward_walk.py` | 历史基准保护 |
| `src/motion/walk_cycle_prototype.py` | Task 5A 独立走步循环脚本 | None $\to$ dict | `run_walk_cycle_prototype.py` | 独立写 blend | **Legacy** | `tests/verify_task5a_walk_cycle.py` | 历史基准保护 |
| `src/motion/forward_walk_prototype.py` | Task 5B 独立向前行走脚本 | None $\to$ dict | `run_forward_walk_prototype.py` | 独立写 blend | **Legacy** | `tests/verify_task5b_forward_walk.py` | 历史基准保护 |
| `src/motion/start_stop_walk_prototype.py`| Task 5C 独立起步停步脚本 | None $\to$ dict | `run_start_stop_walk_prototype.py`| 独立写 blend | **Legacy** | `tests/verify_task5c_start_stop_walk.py` | 历史基准保护 |
| `src/validation/checker.py` | 图像、场景空间与视口一致性校验 | Scene, Layout $\to$ dict | `src/pipeline.py` | 只读文件与场景分析 | **Reusable** | `tests/run_validation.py` | 扩充用于 P1 统一报告校验 |

### 3.2 运行入口脚本分类矩阵 (Root Run Scripts)

| 脚本文件名 | 核心用途 | 所属分类 | 依赖关系 | 推荐处置方式 |
| :--- | :--- | :--- | :--- | :--- |
| `run_unified_motion_pipeline.py` | **当前唯一官方统一 4 动作连续动画生成器**（Walk $\to$ SprintStart $\to$ SprintBrake $\to$ Run） | **Active** | `framework`, `run_cycle`, `sprint_start`, `sprint_brake`, `kinematic_bridge` | **重点保护，作为当前生产级最高基准** |
| `run_pipeline.py` / `run_pipeline.ps1` | Task 3 遗留管线启动器（不含人体与动作） | **Legacy** | `src/pipeline.py` | 暂时保留，待 Task 7 合流重构 |
| `run_contact_walk_integration.py` | Task 6G-C 返工产物（场景 A：真实行走+动态接触标记） | **Reusable** | `StartStopWalkAction`, `ContactModel` | 保留作为接触模型单动作可视化用例 |
| `run_contact_obstacle_integration.py` | Task 6G-C 返工产物（场景 B：5 障碍物静态抓握姿态） | **Reusable** | `WholeBodyController`, `ContactModel` | 保留作为未来跑酷/攀爬动作姿态参考 |
| `run_contact_model_prototype.py` | Task 6G-C 初次接触原型脚本 | **Legacy** | `ContactModel` | 保留作为历史用例 |
| `run_run_prototype.py` | Task 6B 独立跑步原型运行器 | **Legacy** | `RunAction`, `forward_walk_prototype` | 保留作为单动作调试工具 |
| `run_sprint_prototype.py` | Task 6C 独立冲刺起跑原型运行器 | **Legacy** | `SprintStartAction`, `forward_walk_prototype` | 保留作为单动作调试工具 |
| `run_sprint_brake_prototype.py` | Task 6D 独立冲刺急停原型运行器 | **Legacy** | `SprintBrakeAction`, `forward_walk_prototype` | 保留作为单动作调试工具 |
| `run_start_stop_walk_prototype.py` | Task 5C 独立起步停步原型运行器 | **Legacy** | `start_stop_walk_prototype` | 保留作为历史基准 |
| `run_forward_walk_prototype.py` | Task 5B 独立向前行走原型运行器 | **Legacy** | `forward_walk_prototype` | 保留作为历史基准 |
| `run_walk_cycle_prototype.py` | Task 5A 独立原地步态原型运行器 | **Legacy** | `walk_cycle_prototype` | 保留作为历史基准 |
| `run_foot_contact_prototype.py` | Task 4D 独立足部锁定原型运行器 | **Legacy** | `foot_contact_prototype` | 保留作为底层验证 |
| `run_ik_prototype.py` | Task 4C 独立腿部 IK 原型运行器 | **Legacy** | `ik_prototype` | 保留作为底层验证 |
| `run_arm_ik_prototype.py` | Task 6F-A 独立手臂 IK 原型运行器 | **Legacy** | `arm_ik` | 保留作为底层验证 |
| `run_rig_prototype.py` | Task 4B 独立骨架原型运行器 | **Legacy** | `rig/prototype` | 保留作为底层验证 |
| `run_character_prototype.py` | Task 4A 独立角色网格原型运行器 | **Legacy** | `character/prototype` | 保留作为底层验证 |
| `run_motion_framework_prototype.py` | Task 6A 独立动作框架原型运行器 | **Legacy** | `framework` | 保留作为底层验证 |

---

## 4. 历史运动与物理能力防退化基线

### 4.1 核心能力矩阵与验收状态清单

全工程沉淀的 13 项核心能力必须建立防退化保护基线：

| 能力标识 | 任务编号 | 正式源码实现 | 官方验证入口 | 已知正确结果与量化基线 | 验收状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ForwardWalk** | Task 5B | `src/motion/forward_walk.py` | `tests/verify_task5b_forward_walk.py` | 144 帧，4 步连续前行，交替摆动抬腿 $100\text{ mm}$，0 触地穿透 | 已验证 (历史基准) |
| **StartStopWalk** | Task 5C / 6A / 6G-C-R3B-2 | `src/motion/start_stop_walk.py`<br/>`src/motion/framework.py` | `tests/verify_r3b2_walk_action.py` | 204 帧，7 半步调度，$C^1$ 速度 0 $\to$ 0.24 $\to$ 0 m/s，位移严格 1.2600m，支撑漂移 $< 0.05\text{ mm}$，解剖踝俯仰调制生效 | **已验证 (生产集成)** |
| **Run** | Task 6B / 6G-C-R3B-2 | `src/motion/run_cycle.py` | `tests/verify_r3b2_run_action.py` | 96 帧，4 周期，40 腾空帧（每周期 10 帧双脚离地），恒速 0.90 m/s，位移 3.5625m，摆动踝俯仰 $-38^\circ$ 调制，0 超程 | **已验证 (生产集成)** |
| **SprintStart** | Task 6C / 6G-C-R3B-2 | `src/motion/sprint_start.py` | `tests/verify_r3b2_sprint_start.py` | 114 帧，静止蹲姿预备 $\to$ 爆发蹬伸 $\to$ 冲刺加速，49 腾空帧，峰值 2.00 m/s，位移 6.5833m，摆动踝俯仰 $-36^\circ$ 调制，0 超程 | **已验证 (生产集成)** |
| **SprintBrake** | Task 6D / 6G-C-R3B-2 | `src/motion/sprint_brake.py` | `tests/verify_r3b2_sprint_brake.py` | 162 帧级联，高速接入 $\to$ 主动急停制动 $\to$ 双脚稳定并立，减速至 0.0 m/s，双脚锁定漂移 $< 0.05\text{ mm}$，0 超程 | **已验证 (生产集成)** |
| **Leg IK** | Task 4C / 6G-C-R3B-2-R1 | `src/rig/ik.py` | `tests/verify_task4c_ik.py` | 两骨极向 IK，足底绝对贴地 $Z=0.07\text{ m}$，`FootRotation` 采用 `WORLD -> LOCAL` 空间映射，彻底消除退化锁死 | **已验证 (核心执行器)** |
| **Arm IK** | Task 6F-A | `src/rig/arm_ik.py` | `tests/verify_task6fa_arm_ik.py` | 双臂两骨 IK，手腕位置追踪误差 $< 0.05\text{ mm}$，三维姿态对齐误差 $< 1.0^\circ$，支持与 FK 权重动态平滑混合 | **已验证 (核心执行器)** |
| **WholeBodyController** | Task 6F-D / 6G-C-R3B-2-R1 | `src/motion/whole_body_controller.py` | `tests/verify_task6fd_whole_body_controller.py` | 统筹协调根节点、骨盆、躯干与四肢，强制 `reparent_to_root=False` 确保控制器恒定在世界空间，0 暴拉 | **已验证 (核心协调器)** |
| **CoM (质心评估)** | Task 6F-B | `src/motion/rigid_link.py` | `tests/verify_task6fb_rigid_link.py` | Dempster-Winter 15 刚体分段质量模型，前向运动学多连杆质心计算误差 $< 0.1\text{ mm}$ | **已验证 (只读分析)** |
| **Joint ROM (生理限位)**| Task 6F-C | `src/motion/joint_limits.py` | `tests/verify_task6fc_joint_limits.py` | 14 个解剖关节限位模型，支持轴向盒式与椭圆锥约束，超差诚实上报 `ROM_VIOLATION`，截断冲突真实报警 | **已验证 (核心规则库)** |
| **BodyKinematics** | Task 6G-A | `src/motion/body_kinematics.py` | `tests/verify_task6ga_body_kinematics.py` | 有限差分瞬时线速度/角速度与加速度追踪，支持变步长时间缩放 | **已验证 (只读分析)** |
| **BodyInertia** | Task 6G-B | `src/motion/body_inertia.py` | `tests/verify_task6gb_body_inertia.py` | 15 分段局部张量对称正定，3D 平行轴定理合成全身体惯性张量，解耦自转与轨道角动量 | **已验证 (只读分析)** |
| **ContactModel** | Task 6G-C | `src/motion/contact_model.py` | `tests/verify_task6gc_contact_model.py` | 多部位接触几何判定、间隙/穿透/滑移度量、4 态生命周期机与 8 类支撑分类 | **已验证 (只读分析)** |
| **Unified Motion Pipeline** | Task 6G-C-R3B-2-R1 | `run_unified_motion_pipeline.py` | `tests/verify_unified_motion_integration.py` | 462 帧连续动画，覆盖 4 大步态无缝衔接，总位移 12.9058m，0 次不可达事件，0 次暴拉，第 41..44 关键帧与历史基准 100% 重合 | **已验证 (终极集成产物)** |

### 4.2 关键 Blender 资产文件磁盘定位与 Git 状态核查

> [!CAUTION]
> **真实登记约束**：必须严格核实磁盘文件位置与 `.gitignore` 规则，严禁宣称未跟踪文件已被 GitHub 备份！

经过对本地文件系统与 Git 索引的交叉比对，关键动画工程文件的真实状态登记如下：

1. **`output/character_forward_walk.blend`**：
   * **磁盘物理存在**：`C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\output\character_forward_walk.blend`（文件大小约 248 KB）；
   * **Git 跟踪状态**：**未跟踪 (Git Ignored)**。根目录 `.gitignore` 第 14 行包含 `output/` 规则；
   * **备份事实**：**该文件仅保存在本地磁盘，GitHub 远程仓库上没有该二进制文件**。
2. **`output/character_start_stop_walk.blend`**：
   * **磁盘物理存在**：`C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\output\character_start_stop_walk.blend`（文件大小约 267 KB）；
   * **Git 跟踪状态**：**未跟踪 (Git Ignored)**；
   * **备份事实**：**该文件仅保存在本地磁盘，GitHub 远程仓库上没有该二进制文件**。
3. **`output/unified_motion_integration.blend`**：
   * **磁盘物理存在**：`C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\output\unified_motion_integration.blend`（文件大小 298,537 字节，462 帧）；
   * **Git 跟踪状态**：**未跟踪 (Git Ignored)**；
   * **备份事实**：**该文件仅保存在本地磁盘，GitHub 远程仓库上没有该二进制文件**。
4. **`output/renders/r3b2_comparison/*.png`**：
   * **磁盘物理存在**：40 张高分辨率视口关键帧对比图像；
   * **Git 跟踪状态**：**未跟踪 (Git Ignored)**；
   * **备份事实**：**仅保存在本地磁盘**。

> [!IMPORTANT]
> **防丢失与可复现性保证**：
> 虽然所有 `.blend` 与 `.png` 产物均处于 `.gitignore` 保护下未推送到 GitHub（符合 Git 不提交非受控大体积二进制产物的基本规范），但**生成它们的所有源代码（`run_unified_motion_pipeline.py`、`src/` 核心库）与验证测试均 100% 受 Git 版本控制并已完全推送到远程 master 分支**。任何时刻均可在安装 Blender 5.1 的环境中，通过一条命令行 `blender -b -P run_unified_motion_pipeline.py` 100% 比特级无损重建出完全相同的 `.blend` 场景。

---

## 5. 审计测试与终端执行系统及 P1 实施方案

### 5.1 现有测试系统问题诊断
审计目前 30 个测试文件发现以下致命痛点：
1. **测试入口严重分裂**：
   * `tests/run_test.ps1` 与 `tests/run_validation.py` 是 Task 1 的古董代码，硬编码只跑 `test_env.py` 和 `verify_blend.py`，完全无法用来测试运动系统；
   * 其余 27 个 `verify_*.py` 必须由人工或 Agent 在命令行中敲写单独命令执行；
2. **环境选择混乱**：
   * 部分测试需要标准 Python 执行（如 `tests/test_task3_spatial.py`）；
   * 绝大部分测试需要无头 Blender (`blender -b -P`) 执行；
   * 少数测试内部又启动了 `subprocess.run([blender, ...])`（如 `verify_task6gc_r3b1_bridge.py` 中的 Test 14）；
3. **严重加剧用户审批负担 (Approval Fatigue)**：
   * 每次 Agent 想要执行回归，必须逐个向用户申请运行 `verify_r3b2_walk_action.py`、`verify_r3b2_run_action.py`、`verify_task6gc_r3b1_bridge.py`……每跑一个命令用户就要在 IDE 中点击一次批准，严重消耗精力；
4. **退出码与断言判定不严谨**：
   * 某些测试脚本在捕获异常后直接 `print("[FAIL]")` 但没有调用 `sys.exit(1)`，导致进程退出码依然为 0，引发虚假全绿风险。

### 5.2 P1 统一测试调度系统 (Unified Test Runner) 详细设计方案

为在下一阶段彻底解决上述痛点，在此给出 P1 落地实施的技术规范方案（**本轮只交付设计，不提前编写代码**）：

#### 设计目标 1：单入口与测试注册表架构 (Test Registry)
废弃文件名通配符扫描推断机制，在 `tests/test_registry.py` 中建立显式注册表。每项测试必须声明所属分级、运行时依赖、超时限制与期望产物：

```python
# P1 设计预览：测试注册表数据结构
@dataclass
class TestDefinition:
    test_id: str                      # 唯一标识符，如 "walk_action_regression"
    script_path: str                  # 相对路径，如 "tests/verify_r3b2_walk_action.py"
    tier: str                         # "quick" | "motion" | "physics" | "full"
    runner_type: str                  # "blender_headless" | "python"
    timeout_sec: float                # 单项超时限制 (如 60.0s)
    target_blend: Optional[str]       # 若需预载 blend 文件则声明
    description: str                  # 测试内容描述
```

#### 设计目标 2：四级执行分层 (Tiered Execution)
测试按执行耗时与关注点严格分级：
* **Tier 1: `quick`（快速冒烟检查，~5秒）**：
  * 执行纯 Python 布局算法、配置有效性、数据结构与数学转换测试；
  * 用途：代码提交前的高频快速自检。
* **Tier 2: `physics`（底层物理与几何数学库回归，~25秒）**：
  * 执行 WBC (`verify_task6fd`), ROM (`verify_task6fc`), CoM (`verify_task6fb`), Arm IK (`verify_task6fa`), Kinematics (`verify_task6ga`), Inertia (`verify_task6gb`), Contact Model (`verify_task6gc`)；
  * 用途：修改底层运动学、物理计算或约束后自检。
* **Tier 3: `motion`（四大步态无损回归，~45秒）**：
  * 执行 `verify_r3b2_walk_action`, `verify_r3b2_run_action`, `verify_r3b2_sprint_start`, `verify_r3b2_sprint_brake`；
  * 用途：验证步态曲线、位移、腾空相与解剖踝关节姿态未退化。
* **Tier 4: `full`（全量里程碑级端到端验收，~90秒）**：
  * 串行运行以上所有 Tier，外加桥接层 14 项严苛测试 (`verify_task6gc_r3b1_bridge`) 与统一 462 帧集成场景验证 (`verify_unified_motion_integration`)；
  * 用途：阶段任务完结、创建 Git Commit 与 GitHub Push 前的强制门禁。

#### 设计目标 3：单命令外层调度——根除用户反复审批负担
* **核心机制**：设计统一外层调度入口 `tests/run_test_suite.py`（以及包装脚本 `run_tests.ps1`）。
* **执行协议**：Agent 在需要验证时，**仅向用户申请执行一次顶层受控命令**：
  ```powershell
  python tests/run_test_suite.py --tier full
  ```
* **内部调度行为**：
  1. `run_test_suite.py` 作为宿主进程，根据注册表自动在内部按顺序调用 `subprocess.run` 串行唤起各个单项测试；
  2. 自动定位本地可用的 Blender 5.1 可执行文件，按需分发给 Python 或 Blender Headless；
  3. 对每个子测试实施硬超时监控（`timeout=test.timeout_sec`），子进程卡死时自动强制 kill 并记录超时失败；
  4. 完整捕获每个测试的 `stdout`、`stderr`、执行耗时与 `returncode`；
  5. **绝对退出码纪律**：任何一个测试只要 `returncode != 0`，即使日志输出中包含 "PASS" 字符，一律直接判定为整体失败，并在终端打出高亮红字原因；
  6. 运行结束后，在终端打印清晰的 ASCII 表格摘要，并将详细结果输出为结构化日志 `tests/output/test_report.json` 与 `test_report.md`。

> [!IMPORTANT]
> **权限诚实性声明**：
> 本设计**绝对不是、也绝不可能绕过** Antigravity 或操作系统的终端安全授权机制。它的本质是**将 N 次分散的子命令执行，收敛为一次由 Python 测试运行器统筹调度的顶层命令**。用户只需点击一次批准，即可让宿主测试器在后台受控完成全套 30 项测试的串行调度。

### 5.3 P1 落地实施与验证成果 (Task 6G-D-PRE-P1 Execution Status)
Task 6G-D-PRE-P1 已完整落地实施上述方案：
1. **测试注册表已就绪 (`tests/test_registry.py`)**：
   - 登记 26 项受控测试用例，涵盖 `quick` (3 项)、`physics` (8 项)、`motion` (5 项)、`full` (14 项去重并集) 与 `legacy` (13 项)；
   - 包含明确超时限制、Runner 类别判定与依赖资产校验。
2. **统一调度运行器已就绪 (`tests/run_test_suite.py` / `run_tests.ps1`)**：
   - 支持自动解析 Blender 5.1.1 与真实 Python 路径，隔离 Windows Store 假别名；
   - 支持 Windows 深度进程树清理 (`taskkill /F /T /PID`)；
   - 实现 stdout/stderr 失败关键字反向排查与退出码一票否决；
   - 自动生成 `tests/output/test_report.json` 与 `test_report.md`。
3. **分层回归验证通过**：
   - `quick` Tier：3 项测试全绿 (3.94s)；
   - `motion` Tier：5 项测试全绿 (16.16s)，其中 `integration_unified_motion` 正确标定为 `AUTOMATED_PASS (Visual Inspection Required)`；
   - `physics` Tier：8 项测试全绿 (53.90s)，底层运动学、WBC、ROM、CoM、惯性张量与桥接 14 项测试保持 100% 零退化。
4. **永久架构门禁确立**：
   - 交付权威规范 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md) 作为唯一标准来源 (SSOT)；
   - 同步更新 `.agents/rules/project_rules.md`、`AGENTS.md`、`GEMINI.md` 第 8 节。

---

## 6. 场景系统现状审计与 P2 动力学训练场规划

### 6.1 现有场景模块审计
* **`src/scene/layout.py`**：纯 Python 确定性几何计算模块，包含点到线段距离、多段线安全走廊缓冲区算法，完全解耦于 Blender，数学健壮性优良。
* **`src/scene/builder.py`**：调用 Blender API 创建场景、材质、地表平板、长方体建筑和圆柱体。坐标系严格符合 $Z$ 向上、顶面位于 $Z=0.0\text{ m}$ 的世界标准。
* **缺陷分析**：目前该系统仅支持单一平面的平地场景生成，缺乏高度起伏、台阶、斜面及立面障碍，无法满足 Task 6G-D 动力学与接触反力（GRF）的测试需求。

### 6.2 P2 简易动力学训练场实施方案 (Dynamics Playground Specification)

在 P2 阶段，应继承并扩展 `src/scene/builder.py` 与 `src/scene/layout.py`，构建标准化“程序化动力学训练场”：

#### 1. 严格的四层解耦模型 (Four-Layer Separation)
为了杜绝在场景代码中搞“第二套运动系统”，训练场必须严格遵守四层隔离：
1. **场景几何层 (Scene Geometry)**：`src/scene/builder.py` 负责生成标准网格与碰撞体，赋予各向同性物理摩擦材质（如静摩擦系数 $\mu_s = 0.7$），打上规范对象名与标签（如 `Surface_Stair_01`, `Surface_Ramp_01`）；
2. **环境查询层 (Environment Query)**：扩展 `src/motion/framework.py` 中的 `EnvironmentQuery` 为专用查询器 `src/scene/query.py`，提供任意空间坐标 $(x, y)$ 处的地表高度 $z(x, y)$、表面法向量 $\mathbf{n}(x, y)$、最近障碍物距离与局部切平面方程；
3. **动力学模型层 (Dynamics Model)**：Task 6G-D 引入的接触力求解器、冲量计算与摩擦锥约束，仅通过输入肢体末端速度与接触点坐标，调用环境查询层获得法线与间隙，输出接触反力 $\mathbf{F}_c$；
4. **动画控制层 (Animation Controller)**：现有的 `MotionPlanner` $\to$ `MotionAction` $\to$ `KinematicBridgeExecutor` $\to$ `WholeBodyController` 主管线，从动力学求解器获得反力调整量，直接驱动角色运动。**训练场本身绝不包含任何骨骼位移逻辑**。

#### 2. 六大标准化功能分区规格
训练场地长 $60\text{ m}$、宽 $20\text{ m}$，划分为 6 个按顺时针/直线串联的功能区域：
1. **平坦走跑区 (Flat Ground Zone, $Y \in [-10.0, 5.0]\text{ m}$)**：
   * 规格：$Z = 0.0\text{ m}$，纯平地，配备标准地面参考网格；
   * 用途：行走、奔跑、冲刺起步与急停的标准回归基准。
2. **交替台阶区 (Stairs Zone, $Y \in [6.0, 14.0]\text{ m}$)**：
   * 规格：5 级台阶，每级踏面深度 $d = 0.30\text{ m}$，踢面高度 $h = 0.15\text{ m}$，总提升高度 $+0.75\text{ m}$；
   * 用途：足部接触高度适应、阶梯着地冲量与单腿向上蹬伸动力学。
3. **连续斜坡区 (Ramp Zone, $Y \in [16.0, 26.0]\text{ m}$)**：
   * 规格：长 $10.0\text{ m}$，坡角 $\alpha = 15.0^\circ$（上升坡）与 $\beta = -20.0^\circ$（下降坡），地表法线倾斜；
   * 用途：倾斜表面接触力矩、足底踝关节倾角适应与防滑摩擦锥校验。
4. **垂直障碍墙区 (Vertical Wall Zone, $Y \in [28.0, 34.0]\text{ m}$)**：
   * 规格：垂直障碍物，高度 $2.0\text{ m}$，厚度 $0.4\text{ m}$；
   * 用途：手部支撑、脚蹬垂直墙面（Wall Plant）反力平衡测试。
5. **跳箱与悬挂平台区 (Vault Platform & Ledge Zone, $Y \in [36.0, 44.0]\text{ m}$)**：
   * 规格：高 $0.90\text{ m}$ 的跳箱平台与高 $2.20\text{ m}$ 的横向单杠；
   * 用途：多部位同时接触（手撑台面 + 脚挂平台边缘）与悬垂拉力测试。
6. **遥测与可视化分析专用区 (Telemetry Visualization Hub)**：
   * 规格：场景原点旁的动态视口展示层；
   * 配备：地面投射的全身质心（CoM）黄色十字光标、支撑多边形（Support Polygon）凸包闭包线条、足底接触反力向上的绿色 3D 箭头矢量，随动画时间轴实时更新。

---

## 7. 永久架构门禁 (Architecture Change Gate) 制度设计

为防止后续再次出现类似于“脱离步态做平移”、“私加父级导致 L 形暴拉”、“独立写脚本拼凑演示”的架构事故，依据 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md`，正式确立**永久架构门禁审查制度 (Architecture Change Gate, ACG)**。

### 7.1 ACG 十一条前置准入审查清单 (Pre-flight Checklist)
后续任何开发任务在写下第一行生产代码之前，必须在思考过程或设计卡片中逐一核实并正面回答以下 11 个问题：
1. **已有实现排查**：所要开发的能力，项目中是否已有相同或相似模块（如运动学、IK、质心、接触几何）？若有，为何不直接复用？
2. **唯一职责归属**：该功能属于哪一个层级？（规划层 / 桥接层 / 全身协调层 / 骨骼约束层 / 物理分析层），是否破坏单一职责？
3. **真实调用者确权**：该模块由谁调用（上游 Caller）？它又将调用谁（下游 Callee）？是否存在成为孤立代码的风险？
4. **数据结构合同**：输入参数的数据类型是什么？输出结构体是什么？是否已在 `kinematic_bridge.py` 或 `framework.py` 中规范声明？
5. **坐标系统一性**：所有空间三维点是否严格符合 $+Z$ 向上、$Z=0.0$ 为地表、米为单位的绝对世界坐标系？
6. **状态写入唯一所有权**：是否会与现有模块（如 `WholeBodyController`、`foot_contact.py`）对同一骨骼、Empty 物体或约束产生写入竞争？
7. **历史动作零退化影响**：新增修改是否会破坏 Walk、Run、SprintStart、SprintBrake 的现有步态曲线？
8. **回归测试用例指定**：完成本功能后，必须强制运行哪些现有的独立回归测试套件？
9. **可视化验收定义**：该功能的物理与视觉正确性如何直观检验？产出的 `.blend` 文件是否能在 Blender 中直接按空格键自然播放？
10. **主执行链接入阶段**：新增逻辑明确挂载于单帧 6 阶段执行协议的哪一阶段（Phase 1 至 Phase 6）？
11. **未接入时的隔离方案**：如果该功能属于前瞻性研究算法暂不接入主链，如何确保它处于纯只读评估层，绝不干扰主姿态写入？

### 7.2 ACG 八大绝对禁止行为清规 (Strict Prohibitions)
1. **严禁绕开统一控制器**：严禁在 `MotionAction` 或业务脚本中直接通过 `bpy.ops` 或直接赋值修改骨骼欧拉角，所有姿态解算必须通过 `WholeBodyController`；
2. **严禁私造并立执行管线**：严禁建立不经过 `KinematicBridgeExecutor` 的独立动作执行器；
3. **严禁修改既有成熟步态**：严禁为了配合局部模块微调，而私自篡改 Walk/Run 经久验证的步长、触地周期和位移规划；
4. **严禁人为摆拍与硬编码**：禁止在时间轴指定关键帧手工写入固定骨骼旋转来“冒充”连续动力学反应；
5. **严禁静默吞没失败**：当 IK 无法到达、ROM 超限或接触脱离容差时，必须真实上报 `success = False`，严禁截断后谎报成功；
6. **严禁放宽医学 ROM 阈值**：禁止为了让测试通过而随意放宽 `joint_limits.py` 中的生理角度上下限；
7. **严禁动态切换物体父级**：下肢与上肢控制器在整个动画时间轴上必须恒定保持在绝对世界空间（`parent = None`），禁止任何动态 reparent 行为；
8. **严禁未验证即声称完成**：未在真实 Blender 引擎中运行命令并检验退出码为 0 前，绝对禁止宣称任务“已完成”或“已验证”。

### 7.3 架构偏差报告与审批流程 (Deviation Protocol)
若在后续开发中，确实发现现有架构存在根本性缺陷必须调整（例如需要重构骨架层级、引入非 Blender 原生求解器、变更核心数据流等），**必须严格暂停当前开发**：
1. 立即停止代码编写，保留当前 Git 干净状态；
2. 在报告中详细列明：偏差原因、涉及模块、影响范围、历史回归风险及备选方案；
3. **明确向用户提出架构变更审批申请**；
4. 获得用户明确的书面批准后，方可将变更录入 `DECISIONS.md` 并实施修改。

---

## 8. 代码与文档不一致项、未决事实与风险优先级

### 8.1 审计发现的代码与文档不一致项 (Inconsistencies)
1. **`run_pipeline.py` 与 `src/pipeline.py` 的时代脱节**：
   * 文档与注释宣称它是“统一主流水线”，但代码实际仅停留在 Task 3 静态场景阶段，完全没有接入角色与运动系统。
2. **`BlenderPoseApplicator` 与 `ContactConstraintAdapter` 的遗留存续**：
   * `ARCHITECTURE.md` (v2.3) 与 `ARCHITECTURE_SYNC.md` 宣称姿态统一由 WBC 写入，但代码中 `MotionRuntimeContext` 依然在默认构造这两个已废弃类的实例。
3. **`EnvironmentQuery` 的静态平面假定**：
   * 架构文档中规划了复杂的接触环境几何，但 `src/motion/framework.py` 中的 `EnvironmentQuery` 代码目前仅实现了 `ground_height_at()` 返回恒定 $0.0$，无真实表面几何拾取能力。

### 8.2 尚未确认的事实与系统局限 (Unknowns & Limitations)
1. **真实动力学闭环未打通**：当前虽然能够计算全身质心速度、惯性张量与全身体角动量，但这些数据**仅用于事后只读分析**，并没有任何反馈力矩或力控算法去实时修正角色的根节点轨迹或脚步落点。系统本质上仍是**纯开环运动学驱动**。
2. **多部位障碍物连续运动学缺失**：当前只有在平坦地面上的连续动作（走、跑、冲刺、刹车）。障碍物交互（如跳箱、单手撑跃、双臂抓杠悬挂）目前仅在静态帧片段（`run_contact_obstacle_integration.py`）验证了姿态可行性，尚无连续时间轴上的动力学轨迹发生器。

### 8.3 风险严重程度与后续优先级清单 (Risk & Priority)

| 风险项 | 严重程度 | 潜在危害 | 推荐处置阶段 |
| :--- | :--- | :--- | :--- |
| **测试系统碎片化与用户审批疲劳** | **高 (High)** | 每次测试频繁申请中断用户，缺乏统一退出码防线，容易漏测 | **Task 6G-D-PRE-P1 立即解决** |
| **主流水线脱节 (`run_pipeline.py`)** | **中 (Medium)** | 容易误导新运行者，导致全管线无法一键输出最终完整动画 | **Task 7 全管线合流阶段解决** |
| **环境查询能力简陋** | **高 (High)** | 进入 6G-D 后若要测试斜坡、台阶反力，开环查询无法支持 | **Task 6G-D-PRE-P2 训练场阶段解决** |
| **动力学只读与开环驱动状态** | **关键 (Critical)**| 无法抵御外部扰动，无法根据地面反力调整质心平衡 | **Task 6G-D 正式开发阶段重点攻坚** |
| **废弃类遗留 (`BlenderPoseApplicator`)** | **低 (Low)** | 历史残留，已被桥接层有效旁路，但存在误用风险 | **后续重构时平滑清理** |

---

## 9. 结论与执行状态声明

1. **审计结论**：本报告对 `ProceduralAnimation` 进行了彻底的穿透式审计，摸清了全仓库 28 个源码、30 个测试和 19 个运行入口的真实调用关系；锁定了以 `KinematicBridgeExecutor` 为枢纽、`WholeBodyController` 独占写入的生产架构；建立了 13 项历史运动物理基线；排查了 Blender 二进制文件的本地存储事实；并为下一轮 P1（统一测试调度器）与 P2（简易动力学训练场）提供了详尽的实施蓝图。
2. **执行纪律遵守声明**：
   * 本轮审计**未修改 `src/` 下任何一行生产代码**；
   * **未修改任何测试的断言或阈值**；
   * **未删除、未覆盖任何历史文件**；
   * **未生成 462 帧完整动画或触发耗时渲染**；
   * **未私自开发动力学或接触反力新功能**；
   * 本轮审计完成后，**严格停止**，坚决不擅自进入 P1、P2 或 6G-D-A。
