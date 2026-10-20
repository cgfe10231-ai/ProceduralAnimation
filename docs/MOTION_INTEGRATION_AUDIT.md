# 动作生成与接触系统工程架构审计报告 (Task 6G-C Rework)

## 1. 历史运动能力全景总览

本表完整梳理自 Task 3 角色建模与骨架绑定以来，各阶段所构建并验证的核心能力、承载文件与关键接口。磁盘代码与测试表明，历史能力均完好无损。

| 任务编号 | 核心能力描述 | 核心代码文件 | 核心类 / 函数 / 接口 | 自动化测试套件 |
|---|---|---|---|---|
| **Task 3** | 19骨骼刚性连杆骨架与人型胶囊体网格绑定 | `src/character/builder.py`, `src/rig/builder.py` | `build_character`, `build_rig`, `bind_character_to_rig` | `tests/verify_rig.py` |
| **Task 4A-4C** | 双腿两骨 IK 解算与极向控制 | `src/rig/ik.py` | `setup_leg_ik`, `set_foot_ik_target`, `FootIK.L/R`, `KneePole.L/R` | `tests/verify_leg_ik.py` |
| **Task 4D** | 物理接触锁定与微米级防滑支撑 | `src/rig/foot_contact.py` | `lock_foot_contact`, `unlock_foot_contact`, `evaluate_foot_support`, `move_character_root_with_support` | `tests/verify_foot_contact.py` |
| **Task 5A** | 原地行走循环 (Walk Cycle Biomechanics) | `src/motion/walk_cycle.py` | `generate_walk_cycle`, `compute_foot_trajectory` | `tests/verify_task5a_walk_cycle.py` |
| **Task 5B** | 连续向前直线行走与脚步轨迹解算 | `src/motion/forward_walk.py` | `generate_forward_walk`, `compute_forward_swing_point` | `tests/verify_task5b_forward_walk.py` |
| **Task 5C** | 起步-加速-匀速-减速-停步全套连续步态 | `src/motion/start_stop_walk.py` | `evaluate_root_kinematics`, `build_step_schedule`, `_evaluate_gait_phase_and_envelopes`, `generate_start_stop_walk` | `tests/verify_task5c_start_stop_walk.py` |
| **Task 6A** | 统一运动状态机与动作框架 (Motion Framework) | `src/motion/framework.py` | `MotionPlanner`, `MotionAction`, `MotionState`, `ContactPointState`, `ContactConstraintAdapter`, `BlenderPoseApplicator`, `StartStopWalkAction` | `tests/verify_task6a_framework.py` |
| **Task 6B** | 跑步步态与腾空相机制 (Running & Flight Phase) | `src/motion/framework.py`, `src/motion/running.py` | `RunAction`, `evaluate_run_root_kinematics`, `build_run_step_schedule` | `tests/verify_task6b_running.py` |
| **Task 6C** | 冲刺起步与大步幅躯干大幅前倾冲刺 | `src/motion/sprint.py` | `SprintStartAction`, `evaluate_sprint_kinematics`, `build_sprint_step_schedule` | `tests/verify_task6c_sprint.py` |
| **Task 6D** | 急停制动、反向躯干后仰与滑移减速 | `src/motion/sprint_brake.py` | `SprintBrakeAction`, `evaluate_brake_kinematics`, `build_brake_step_schedule` | `tests/verify_task6d_brake.py` |
| **Task 6E** | 连续动作序列状态机串联与转移动态重采样 | `src/motion/action_sequencer.py`, `src/motion/transition.py` | `ActionSequencer`, `PlanSequence`, `blend_motion_states`, `resample_transition` | `tests/verify_task6e_sequencer.py` |
| **Task 6F-A** | 双臂独立 IK 与世界空间姿态控制 | `src/rig/arm_ik.py` | `setup_arm_ik`, `set_hand_ik_target`, `HandIK.L/R`, `ElbowPole.L/R` | `tests/verify_task6fa_arm_ik.py` |
| **Task 6F-B** | 刚体连杆质量分布与全身质心 (CoM) 模型 | `src/motion/rigid_link.py` | `RigidLinkSegment`, `HumanMassModel`, `compute_whole_body_com` | `tests/verify_task6fb_mass_model.py` |
| **Task 6F-C** | 关节自由度 (DOF) 与活动范围 (ROM) 约束系统 | `src/motion/joint_limits.py` | `JointConstraint`, `HumanoidJointModel`, `validate_pose_rom`, `clamp_pose_to_rom` | `tests/verify_task6fc_joint_limits.py` |
| **Task 6F-D** | 统一全身控制接口与最小协调器 | `src/motion/whole_body_controller.py` | `WholeBodyController`, `WholeBodyControlTargets`, `WholeBodyControlResult` | `tests/verify_task6fd_controller.py` |
| **Task 6G-A** | 连续身体运动状态与速度学跟踪 | `src/motion/body_kinematics.py` | `BodyKinematicsTracker`, `BodyPoseSnapshot`, `BodyVelocityState`, `BodyMotionState` | `tests/verify_task6ga_kinematics.py` |
| **Task 6G-B** | 刚体连杆惯性张量与全身角动量模型 | `src/motion/body_inertia.py` | `BodySegmentInertia`, `WholeBodyInertiaState`, `compute_whole_body_inertia_and_momentum` | `tests/verify_task6gb_inertia.py` |
| **Task 6G-C** | 多部位接触几何、约束与支撑状态系统 | `src/motion/contact_model.py` | `ContactRecord`, `MultiContactState`, `ContactType`, `ContactLifecycle`, `SupportType`, `evaluate_limb_contacts_from_armature` | `tests/verify_task6gc_contact_model.py` |

---

## 2. 核心动作生成机制深入分析

以 `StartStopWalkAction` / `generate_start_stop_walk` 为核心基准，步态生成分为严谨的三层计算：

### 2.1 根节点运动学规划 (`evaluate_root_kinematics`)
- **速度分布**：采用 C1 连续的余弦平滑升降曲线 $v(\tau)$（单位：m/s 或 m/frame）。
  - $[0, \tau_s]$（0-12 帧）：静止站立，初始速度 $0$。
  - $[\tau_s, \tau_a]$（12-66 帧）：起步平滑加速至稳态目标巡航速度 $v_{\max} = 0.24\text{ m/s}$。
  - $[\tau_a, \tau_w]$（66-138 帧）：稳态匀速巡航。
  - $[\tau_w, \tau_d]$（138-192 帧）：平滑减速至 0。
  - $[\tau_d, \tau_{\text{end}}]$（192-204 帧）：结束静止站立。
- **位移积分**：对速度曲线进行解析精确积分 $y(\tau) = y_0 + \int_0^\tau v(t)\,dt$，保证根节点连续平滑位移，杜绝加速度跳变。

### 2.2 离散步态调度 (`build_step_schedule`)
- 将连续时间轴切分为左右腿交替的 $k = 0 \dots 6$ 步：
  - 明确标注每一步的起始帧 `tau_start`、持续帧数 `duration_frames`。
  - 明确标注当前支撑腿 `stance_side`（如 L）与支撑锁定世界坐标 `stance_y`。
  - 明确标注摆动腿 `swing_side`（如 R）、起步坐标 `swing_y_start` 与落地点目标 `swing_y_end`。
  - 确定抬腿高度 `step_height`。

### 2.3 支撑相与摆动相判定与脚部执行
- **支撑相 (Stance Phase)**：
  - 调用 `lock_foot_contact(arm, limb, contact_world_xyz)`。
  - 支撑脚世界坐标锁定在真实地面 $Z=0$ 及对应落地点 $Y$，随着根节点向前移动，脚踝 IK 控制器通过世界坐标保持绝对不动，漂移量严格 $< 0.05\text{ mm}$。
- **摆动相 (Swing Phase)**：
  - 归一化进度 $s = (\tau - \tau_{\text{start}}) / \Delta\tau \in [0, 1]$。
  - 调用 `compute_forward_swing_point` 计算平滑向前跨步与垂直正弦抬腿弧线：
    $$y_{\text{swing}} = y_{\text{start}} + (y_{\text{end}} - y_{\text{start}}) \cdot s_{\text{smoothstep}}$$
    $$z_{\text{lift}} = h_{\text{step}} \cdot \sin(\pi s)$$
  - 调用 `unlock_foot_contact` 并更新 `set_foot_ik_target`。
- **对侧手臂与躯干协同**：
  - 上半身和下半身形成对角线惯性互补：左腿前摆时右臂前摆，右腿前摆时左臂前摆；
  - 加速与减速阶段引入平滑骨盆下沉 (`crouch_env`) 与躯干前倾/后仰角 (`trans_lean_deg`)。

---

## 3. 统一状态与数据流闭环

系统设计的数据流架构图如下：

```
[MotionPlanner / ActionSequencer]
                │
                ▼ (Plan action sequence)
        [MotionAction]  <-- (e.g. StartStopWalkAction, SprintAction)
                │
                ▼ (Generate per-frame trajectory & contact plan)
         [MotionState]  <-- (Root pos, vel, mode, contacts dict)
                │
                ▼ (Dispatch to whole body solver)
     [WholeBodyController]
       ├── Body Targets (Root, Pelvis, Spine, Arms, Legs)
       ├── Arm IK & Leg IK World Solvers
       └── Joint Model DOF & ROM Clamp (src/motion/joint_limits.py)
                │
                ▼ (Apply transforms & keyframe)
        [Armature Pose]
        ├── PoseBones (19 bones)
        └── IK Target Objects (FootIK.L/R, HandIK.L/R, Pole targets)
                │
                ├──────────────────────────────────────┐
                ▼                                      ▼
    [BodyKinematicsTracker]                  [ContactModel]
    (Velocities, CoM trajectory)             (MultiContactState)
                │                                      │
                ▼                                      ▼
    [BodyInertia / AngularMomentum]         [Geometric Constraint Check]
                                            (Unilateral / Grasp / Flight)
                                                       │
                                                       ▼
                                            [Feedback / Visual Markers]
```

### 闭环关键机制：
1. **生成端**：`MotionAction` 根据环境与运动模式，产出高层位移、步态相位和四肢末端时空轨迹。
2. **控制端**：`WholeBodyController` 作为统一部署网关，校验关节 ROM，解算并写入 Blender 姿态骨骼。
3. **感知与物理约束端**：
   - `BodyKinematicsTracker` 与 `BodyInertia` 提取实际骨骼角动量与质心；
   - `ContactModel` 针对实际姿态骨骼末端（结合 `body_local_anchor` 偏移），对环境表面执行法向距离（脱离 vs 穿透）与切向滑移检测；
   - 将检测到的接触生命周期（`ESTABLISHED`、`RELEASED`）回填并更新可视化标记物。

---

## 4. 为什么老步态在 6G-C 原型中消失了？（根本原因剖析）

在 Task 6G-C 初次实现中，产生“角色单腿抬起直接平移滑行 2 米”的根本原因是：**试图将连续步态与静态障碍物测试塞入同一个脚本，且彻底脱离了现有的动作引擎。**

具体表现在：
1. **彻底绕过了现有的步态状态机**：
   `run_contact_model_prototype.py` 没有调用 `StartStopWalkAction` 或 `start_stop_walk.py`，而是硬编码了 6 个离散的姿态快照：
   - 目标 1：双脚站立（$Y = -8.00$）
   - 目标 2：单脚离地（$Y = -8.00$，右脚抬起）
   - 目标 3：障碍物金库支撑（Vault Touch，根节点位于 $Y = -5.85$）
2. **错误的连续插值假设**：
   脚本编写了 `interpolate_targets(t0, t1, progress)`，并在段 2（单腿站立）到段 3（金库支撑）之间直接对根节点位置进行平滑插值（$Y: -8.00 \to -5.85$）。
   在这一区间内，控制器收到的目标是：**根节点沿 +Y 方向高速平移 2.15 米，而右腿目标仍保持在抬起状态**。
3. **物理与步态逻辑完全断裂**：
   人类跨越 2.15 米需要完成至少 4~5 个完整步幅（左右交替触地、换脚、摆臂）。通过简单的数学平移，既没有生成中间步态，也没有进行落脚点规划，导致角色呈现像雕塑滑冰一样“抬着单脚悬空漂移 2 米”的荒诞画面。

---

## 5. 返工方案与集成路径（两套独立原型设计）

为了彻底解决上述架构断层，坚决杜绝“单腿滑行”与局部补丁修复，本次返工将展示任务完全解耦为两套独立工程：

### 5.1 场景 A：真实连续步态集成场景 (`output/contact_walk_integration.blend`)
- **驱动引擎**：基于 `StartStopWalkAction` / `src/motion/start_stop_walk.py` 完整历史算法。
- **动作表现**：完整的 204 帧标准人类连续行走：
  - 0-12 帧：双脚稳稳平踏地面的静止站立；
  - 12-66 帧：左脚起步、右脚跟进的平滑起步加速；
  - 66-138 帧：左右脚稳健交替支撑与摆腿、对侧双臂自然前后摆动、骨盆上下波动的稳态行走；
  - 138-192 帧：平滑减速与收腿合拢；
  - 192-204 帧：双脚并拢、平贴地面的自然静止站立。
- **ContactModel 实时闭环集成**：
  - 每一帧调用 `ContactModel` 实时分析左右脚足底与地面的接触状态；
  - 支撑相（Stance）：识别为 `ESTABLISHED`、`UNILATERAL`，切向滑移 $< 0.05\text{ mm}$，地面法向箭头向上，绿色八面体标记物稳固锚定在足底真实接触点；
  - 摆动相（Swing）：识别为 `RELEASED`、`FREE`，接触标记物自动熄灭（或移至隐藏层/缩放为0），法向箭头隐去；
  - 完整呈现 `DOUBLE_STANCE` $\to$ `SINGLE_STANCE_L` $\to$ `SINGLE_STANCE_R` $\to$ `DOUBLE_STANCE` 的支撑类型实时切换。

### 5.2 场景 B：多部位障碍物接触场景 (`output/contact_obstacle_integration.blend`)
- **驱动引擎**：使用 `WholeBodyController`，在离散的独立观察区展示多部位接触。
- **彻底杜绝伪造行走**：绝对不在长距离之间使用硬编码平移插值伪造步态。各个接触姿态采用**分段独立展示或短时微动悬停 (Hold Clips)**：
  - **片段 1 (Double Stance)**：自然站立，双手自然下垂于身体两侧；
  - **片段 2 (Vault Touch)**：面对金库障碍物前倾，右手掌心平按于箱体顶面（$Z=1.05\text{ m}$，法向向上），左手平衡展开；
  - **片段 3 (Foot on Wall)**：面对垂直墙面，右脚抬起平踩在垂直墙面上（$Y=-4.00\text{ m}$，法向指向 $-Y$）；
  - **片段 4 (Ledge Hang)**：双手向上抓握单杠（$Z=1.95\text{ m}$，`GRASP` 双向约束），身体自然垂挂，双腿微屈悬空；
  - **片段 5 (Flight Phase)**：空中的腾空迈步姿态，全身 0 接触，识别为 `FLIGHT` 模式。
- **环境交互精确度**：
  - 角色朝向与障碍物表面法向严格匹配；
  - 接触锚点误差 $< 5\text{ mm}$；
  - 关节姿态 100% 满足 ROM 约束。
