# ARCHITECTURE_SYNC：工程动态架构与模块调用同步

> **文档定位**：动态工程架构同步文档。记录当前已经实现、已经核实的真实调用关系、模块职责、状态所有权、审计进度与后续准入边界。
>
> **总架构保护**：`ARCHITECTURE.md` 是全项目总架构蓝图，本文件不得替代、复制、重构或擅自修改总架构。
>
> **09-B-4 生产修复基准**：`52d66dfd529627a9fbc8bae6ffcf6f4fee6c64d8`
>
> **TEST-24 断言补充基准**：`3881aaadd58f76ffce18faf5d9e880bc49b82f97`
>
> **完整测试证据基准**：`0b42cb1d7dc685d1be7210bc1280519658f85809`
>
> **最近完成节点**：PKG-5 / Task 10-A（10-A-1 至 10-A-4 归档验收）；当前已实现节点：PKG-5 / Task 10-B（10-B-1、10-B-2、10-B-3 已实现测试归档）。
>
> **最近完成状态**：10-A 为 `COMPLETED — ARCHIVED`；10-B-1 至 10-B-3 为 `IMPLEMENTED — TESTED — ARCHIVED`；生产级事务快照与回滚为 `NOT IMPLEMENTED`；整体 Task 10-B 为 `IN PROGRESS — NOT ACCEPTED`。
>
> **下一执行节点**：后续计划 `10-B-4`（生产级事务快照与故障回滚，仅作为后续计划记录，本次不执行）；Task 10-C 保持 `BLOCKED — NOT STARTED`。
>
> **下一节点状态**：`PLANNED / NOT STARTED`。
>
> **当前工程核心事实**：19 骨骼角色运动学执行管线与 6-DOF 数值质心动力学管线保持独立；二者未来的合流属于 Phase 7C，不是当前 PKG-5 的待修缺陷。

---

## 1. 文档层级与维护边界

本项目中的架构、状态、问题和决策文件具有不同职责，不得互相替代。

| 文件 | 职责 | 维护规则 |
|---|---|---|
| `ARCHITECTURE.md` | 全项目总架构蓝图、核心设计原则、总体结构 | 保护文件。未经项目负责人明确授权不得修改 |
| `ARCHITECTURE_SYNC.md` | 当前真实工程架构、模块职责、调用链和阶段状态 | 动态维护。只随真实实现和已批准决策更新 |
| `docs/ARCHITECTURE_CHANGE_GATE.md` | 架构变更准入、禁止事项与防漂移规范 | 权威门禁，不得私自另建一份替代规范 |
| `docs/audit/production_interface/OPEN_FINDINGS.md` | 全项目问题登记总表 | 维护现有 Finding ID、证据与修复节点 |
| `docs/audit/production_interface/REPAIR_GROUPING.md` | 历史审计问题与修复分组方案 | 保留历史事实，不得擅自重写历史统计 |
| `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md` | 7A 至 7F 及 6H 阶段路线图 | 作为未来阶段范围与依赖依据 |
| `DECISIONS.md` | 已经批准的重要工程决策 | 只有已批准决策才可记录为正式决策 |
| `PROJECT_STATE.md` | 经核实的当前工程状态 | 不得将摘要或旧验收记录当作最新事实 |
| `HANDOFF.md`、`AI_SYNC.md` | 跨会话摘要和交接 | 不得覆盖原始证据 |

**核心规则：**

1. 总架构与动态架构是两个不同层次。
2. 动态架构只能反映实际存在的生产调用链。
3. 尚未实现的规划功能不得画入当前真实执行链。
4. 历史审计快照不得被改写成当前状态。
5. 所有未知内容必须明确标注未知，不得自行补全。

## 2. 当前真实执行架构

当前工程必须区分两条独立管线。

### Pipeline A：19-Bone 生产运动学与全身控制管线

```text
Scene / Environment Query
          |
          v
MotionPlanner / MotionAction
          |
          v
TerrainWalkAction / Planned Motion
          |
          v
KinematicPlannedPose
          |
          v
KinematicBridgeExecutor.execute_frame()
          |
          v
WholeBodyController.execute_frame()
          |
          +----------------------+
          |                      |
          v                      v
     FK / Pose Dispatch      IK Dispatch
          |                      |
          |                +-----+------+
          |                |            |
          |                v            v
          |             Lower IK      Upper IK
          |                |            |
          |          FootContact     Arm IK
          |                |            |
          +----------------+------------+
                           |
                           v
                 Blender 19-Bone Rig
                           |
                           v
                 Evaluated Body Pose
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
         CoM          Kinematics         Inertia
          |                |                |
          +----------------+----------------+
                           |
                           v
                    Contact Evaluation
                           |
                           v
                      MotionState
```

主要真实模块：

| 层级 | 文件 | 主要职责 |
|---|---|---|
| 动作编排 | `src/motion/framework.py` | `MotionPlanner`、`MotionAction`、动作时间轴和状态流转 |
| 地形步态规划 | `src/motion/terrain_walk.py` | 真实地形查询、根轨迹、落脚调度和摆动脚轨迹 |
| 帧级桥接 | `src/motion/kinematic_bridge.py` | 将规划目标转换成 WBC 目标，组织单帧执行协议 |
| 全身协调 | `src/motion/whole_body_controller.py` | Root、Pelvis、躯干 FK、四肢 IK/FK 的统一调度和验证 |
| 下肢 IK | `src/rig/ik.py` | 双腿 IK 目标、可达性、地面高程与世界旋转合同 |
| 上肢 IK | `src/rig/arm_ik.py` | 双臂 IK、手腕目标与手部 3D 姿态 |
| FootLock | `src/rig/foot_contact.py` | 支撑脚锁定、解锁、支撑状态评估 |
| FK / Pose | `src/rig/pose.py`、`src/motion/whole_body_controller.py` | Pose 重置、关节旋转及 WBC 内部 FK 分发 |
| ROM | `src/motion/joint_limits.py` | 解剖活动范围校验与可选截断 |
| CoM | `src/motion/rigid_link.py` | 读取姿态后计算全身质心 |
| BodyKinematics | `src/motion/body_kinematics.py` | 姿态快照、差分速度与加速度追踪 |
| BodyInertia | `src/motion/body_inertia.py` | 全身惯性张量与角动量计算 |
| ContactModel | `src/motion/contact_model.py` | 接触几何、生命周期、合规性与支撑分类 |

### Pipeline B：独立 6-DOF 质心数值动力学管线

```text
ClosedLoopDynamics
        |
        v
ContactForceSolver
        |
        v
ForwardDynamics
        |
        v
ForwardDynamicsState
        |
        v
Dynamics Visualization / Numerical Tests
```

主要代码：

- `src/motion/contact_dynamics.py`
- `src/motion/contact_force_solver.py`
- `src/motion/forward_dynamics.py`
- `src/motion/closed_loop_dynamics.py`

该管线是独立的纯 Python 数值动力学基础，不应被描述为已经驱动 19 骨骼角色的生产姿态控制。

**Pipeline A 与 Pipeline B 尚未实现系统级合流。**

两者共享物理世界坐标约定及环境概念，但不代表已经形成统一闭环。正式合流节点属于 Phase 7C。

不得把目前的管线独立状态登记为当前故障，也不得提前在 PKG-5 中实现 7C。

## 3. 模块职责与数据所有权

### 3.1 MotionPlanner / MotionAction

文件：

- `src/motion/framework.py`
- `src/motion/terrain_walk.py`
- 历史动作文件 `src/motion/start_stop_walk.py`
- `src/motion/run_cycle.py`
- `src/motion/sprint_start.py`
- `src/motion/sprint_brake.py`

职责：

- 负责连续动作时间轴与动作规划。
- 生成每帧运动目标。
- 不应绕过 `KinematicBridgeExecutor` 直接操作生产骨骼姿态。
- 不得为了新增动作而破坏既有 Walk、Run、SprintStart、SprintBrake 和 TerrainWalk 能力。

### 3.2 KinematicBridgeExecutor

文件：`src/motion/kinematic_bridge.py`

职责：

- 接收 `KinematicPlannedPose`。
- 转换成 `WholeBodyControlTargets`。
- 调用 WBC。
- 收集末端追踪、ROM、接触几何及遥测数据。
- 构建 `MotionState`。
- 执行关键帧与帧状态提交。

桥接层是规划目标与实际角色执行之间的统一接口。

任何失败处理和关键帧提交行为都必须保证失败状态不会被伪装成成功状态。

### 3.3 WholeBodyController

文件：`src/motion/whole_body_controller.py`

职责：

- 统一协调 Root、Pelvis、Spine、Neck、Head 等姿态。
- 分发 FK 关节目标。
- 调度左右脚 IK、左右手 IK。
- 读取末端追踪结果。
- 执行 ROM 检查与 CoM 评估。
- 形成 `WholeBodyControlResult`。

WBC 是生产姿态协调层，不负责动作时间轴和步态调度。

WBC 通过既有低层模块完成具体写入，不得建立第二套 IK 或 FK 求解系统。

### 3.4 IK / FK

现有执行模块：

- `src/rig/ik.py`
- `src/rig/arm_ik.py`
- `src/rig/pose.py`
- `src/motion/whole_body_controller.py`

FK 与 IK 都属于既有姿态执行体系。

后续必须先独立审核各执行器的输入输出和空间合同，再审核二者之间的协作。

不得把“有 IK 类”或“测试通过”直接等同于 IK/FK 已完成生产级联合闭环。

### 3.5 FootLock

文件：`src/rig/foot_contact.py`

职责：

- 支撑脚锁定和解锁。
- 维护世界空间接触目标。
- 评估锁定状态及骨骼、网格漂移。

现存问题：

- `FIND-R3-03`：解除锁定或重置时的锁定元数据语义及残留问题。
- `FIND-R3-04`：`evaluate_foot_support()` 具有实际姿态与控制器写入副作用，不能继续将其简单描述为纯查询函数。

不得为了形式上的只读而直接删除支撑维持逻辑。必须保留现有 FootLock 真实稳定性合同。

### 3.6 CoM / BodyKinematics / BodyInertia

文件：

- `src/motion/rigid_link.py`
- `src/motion/body_kinematics.py`
- `src/motion/body_inertia.py`

当前角色：

- CoM：读取已评估骨骼矩阵，按质量分布计算全身质心。
- BodyKinematics：根据连续姿态快照计算速度、角速度及加速度。
- BodyInertia：读取姿态和速度状态，计算惯性张量及角动量。

这些模块目前属于姿态后评估与物理遥测，不得宣称已向 Pipeline A 提供主动动力学反馈或姿态补偿。

同时要明确：只读指的是不直接改写 Blender 姿态；内部时间历史、遥测对象和接触记录可以有各自的数据更新行为。

### 3.7 ContactModel

文件：`src/motion/contact_model.py`

职责：

- ContactRecord 生命周期。
- 接触法向间隙、穿透深度、切向滑移的几何计算。
- 多肢体支撑拓扑与 SupportType 分类。

ContactModel 不取代 FootLock，也不直接取代 IK 执行器。

其 `check_all_contacts()` 会更新接触记录中的合规性结果，这类内部状态写入必须和 Blender 骨架姿态写入区分。

### 3.8 ROM

文件：`src/motion/joint_limits.py`

职责：

- 定义解剖关节 ROM。
- 验证关节姿态。
- 在明确启用时执行姿态截断。
- 截断后必须重新核验末端目标误差，不能隐藏目标冲突。

### 3.9 Environment Query

文件：

- `src/scene/environment_query.py`
- `src/scene/blender_mesh_query_adapter.py`

职责：

- 统一查询真实场景网格几何。
- 提供有效支撑点、高程与法向。
- 不允许用虚假地面回退掩盖查询失败。

此前 R4 的环境查询合同问题属于已有历史修复记录，不得在无新证据时重复登记为新缺陷。

## 4. 当前 PKG-5 任务节点

| 节点 | 工作内容 | 当前状态 |
|---|---|---|
| 08 Rig | 刚体平移与世界空间隔离回归 | `COMPLETED / VERIFIED` |
| 09-A | Lower-Limb Ground × Reach：三维地面高程和可达域约束 | `COMPLETED / VERIFIED` |
| 09-B | Lower-Limb World Rotation：有效父级变换、世界旋转数学域、控制器生命周期与失败原子性 | `ACCEPTED — VERIFIED`，最近补强节点 09-B-4 |
| 10 | Upper-Limb IK/FK：双臂接口合同与独立轨迹控制 | `ROUTE FROZEN — IMPLEMENTATION NOT STARTED` |
| 11 | FootLock：锁定元数据生命周期与状态查询/支撑维持副作用合同 | 待修复 |
| 12 | PKG-5 综合接口闭环和全仓联合验收 | 待 10、11 完成后执行 |

### 4.1 09-B：Lower-Limb World Rotation 当前准确状态

**当前状态：`ACCEPTED — VERIFIED`。**

最近补强与独立复核节点：PKG-5 / 09-B-4。

当前源码：

- `src/rig/ik.py`
- `src/rig/foot_contact.py`

专项测试：

- `tests/test_leg_ik_world_rotation_contract.py`

证据：

- 生产修复：`52d66dfd529627a9fbc8bae6ffcf6f4fee6c64d8`
- TEST-24 补充：`3881aaadd58f76ffce18faf5d9e880bc49b82f97`
- 证据归档：`docs/evidence/PKG5_09B4/`

#### 数学支持域

有效父级矩阵：

\[
M_{\mathrm{eff}} =
M_{\mathrm{parent}}
M_{\mathrm{parent\_inverse}}
\]

当前支持域：

- 16 个矩阵元素必须有限。
- 仿射矩阵最后一行误差不得超过 `1e-6`。
- `det(A) < 0`：拒绝镜像反射。
- `det(A) == 0`：拒绝奇异矩阵。
- `s_sq <= 1e-12`：拒绝退化尺度。
- Gram 矩阵相对偏差 `> 1e-6`：拒绝非共形变换。
- 支持纯旋转与正均匀缩放和旋转的组合。

不得将 `det(A) == 0` 替换成 `det(A) <= 1e-7`。
不得将 Gram 矩阵相对偏差阈值放宽至 `1e-4`。

#### 状态完整性与失败原子性

`_snapshot_leg_rig_state()`：

- 捕获 4 个腿部控制器。
- 每个控制器快照覆盖 15 个状态字段。
- 捕获 6 根腿部姿态骨骼。
- 每根骨骼快照覆盖 8 个状态字段。

`_rollback_leg_rig_state()`：

- 恢复控制器父级、父级逆矩阵、TRS、delta TRS、锁定属性等状态。
- 恢复骨骼旋转模式、位置、旋转、尺度、matrix_basis。
- 更新依赖图。
- 对已保存状态逐字段检查恢复结果。

`unlock_foot_contact()`：

- Phase B 提交前捕获共享腿部状态快照。
- 修改 `is_locked`、解除父级、恢复 TRS、更新视图层及返回最终支撑状态的过程位于事务保护范围内。
- 任一提交后异常均调用共享 `_rollback_leg_rig_state()`。
- 不得另建第二套快照或回滚实现。

#### 专项测试

`tests/test_leg_ik_world_rotation_contract.py`：

- TEST-01 至 TEST-27。
- 27/27 PASS。

重要边界：

- TEST-17：Phase B 全状态事务回滚。
- TEST-22：FootIK 解锁剪切拒绝。
- TEST-23：KneePole 独立解锁剪切拒绝。
- TEST-24：解锁提交后故障注入及七项元数据逐项相等性核验。
- TEST-25：NaN / Inf 拒绝。
- TEST-26：非仿射矩阵拒绝。
- TEST-27：正行列式退化尺度拒绝。

#### 回归证据

| 测试 | 结果 |
|---|---:|
| 09-B World Rotation | 27/27 PASS |
| 09-A Ground Height | 20/20 PASS |
| 08 Worldspace Init/Reset | 6/6 PASS |
| Quick | 19/19 |
| Physics | 25/25 |
| Motion | 12/12 |
| Full | 40/40 |
| C2 Final Inspector | PASS |

四级回归退出码均为 0，FAIL 0、SKIPPED 0、NOT_RUN 0。

其中 `AUTOMATED_PASS` 不等于视觉验收通过。相关场景视觉审查状态应单独记录。

09-B-4 已经完成，不得继续标记为 `IN PROGRESS — NOT ACCEPTED`。

### 4.2 节点 10：Upper-Limb IK/FK

状态：

`ROUTE FROZEN — IMPLEMENTATION NOT STARTED`

正式范围：

Upper-Limb IK/FK — 双臂接口合同、独立控制与轨迹解耦

#### 4.2.1 节点目标

现有项目已经具备：

- 双臂原生 Blender 两骨骼 IK。
- 左右独立 HandIK 控制器。
- 左右独立 ElbowPole 控制器。
- 手部世界空间旋转约束。
- FK / IK influence 控制。
- 双臂世界空间位置目标。
- 手腕位置与姿态反馈。
- WBC 中的手部目标分发。
- Bridge 中的 PlannedHandTarget 数据结构。
- JointModel 上肢 ROM 校验。

Task 10 不重新实现以上基础能力。

Task 10 的目标是对现有 Rig、WBC、Bridge 和 MotionAction 路径进行合同收敛，使双臂具有可靠、可独立调用、可连续执行、可真实验证的生产控制能力。

禁止另建第二套 Arm IK、FK、WBC 或动作规划框架。

#### 4.2.2 10-A：Rig 初始化、控制器生命周期与世界空间矩阵合同

负责范围：

- `src/rig/arm_ik.py`
- 与有效父级变换合同有关的既有数学实现。

主要接口：

- `setup_arm_ik()`
- `reset_arm_ik()`
- `get_arm_ik_state()`
- `set_hand_ik_target()`
- `HandIK.L` / `HandIK.R`
- `ElbowPole.L` / `ElbowPole.R`

必须核验和收敛的问题：

- `setup_arm_ik()` 的幂等性声明与真实行为是否一致。
- 重复调用 `setup_arm_ik()` 是否会重置正在使用的 HandIK / ElbowPole 目标。
- `WholeBodyController.__init__()` 每次构造都会调用 `setup_arm_ik()`，该初始化调用是否会意外覆盖运行状态。
- IK 约束和 COPY_ROTATION 约束是否需要每次删除重建，还是只需检查并修复配置。
- `reset_arm_ik()` 是否具有明确且独立的重置语义。
- `matrix_world` 与 `matrix_parent_inverse` 是否共同参与位置、旋转和 Pole 的世界空间反解。
- 父级旋转、正均匀缩放、非均匀缩放、剪切、反射、奇异矩阵的行为是否具有明确支持边界。

世界空间矩阵合同：

- 控制器世界矩阵：不得在父级逆矩阵非单位矩阵时，仅用 `parent.matrix_world` 的逆矩阵反解控制器局部坐标。
- 位置与旋转必须使用同一个有效父级变换语义。
- Task 10 必须复用 09-B 已经确立的有效父级变换支持域，不能复制出第二套阈值不同的校验器。

既有支持域为：

- 所有矩阵元素必须有限。
- 必须为仿射矩阵，最后一行容差 `1e-6`。
- `det(A) < 0` 拒绝反射。
- `det(A) == 0` 拒绝奇异矩阵。
- `s_sq <= 1e-12` 拒绝退化尺度。
- Gram 矩阵相对偏差大于 `1e-6` 拒绝非共形变换。
- 支持纯旋转及正均匀缩放和旋转组合。

允许在真实架构需要时整理共享实现位置，但不得未经审计直接复制、改写或改变 09-B 的数学阈值。

#### 4.2.3 10-B：Rig 输入验证、写入事务与 Influence 合同

负责范围：

- `src/rig/arm_ik.py`
- 与手臂目标输入和状态写入直接相关的调用边界。

重点接口：

- `set_hand_ik_target()`
- `set_arm_ik_influence()`
- `setup_arm_ik()`

必须建立统一的输入验证合同。

`set_hand_ik_target()` 的输入至少需要覆盖：

| 输入 | 验证要求 |
|---|---|
| `side` | 只能为 `L` 或 `R` |
| `world_xyz` | 恰好 3 个有限数值 |
| `hand_rotation_deg` | `None` 或恰好 3 个有限数值 |
| `pole_world_xyz` | `None` 或恰好 3 个有限数值 |
| `influence` | 必须为有限数值，且位于 `[0, 1]` |
| `clamp_reach` | 必须有明确布尔语义 |

要求：

- 所有输入必须在第一次场景状态写入之前完成验证。
- 非有限输入不得传入 Blender 控制器。
- 不允许一部分控制器写入成功、另一部分写入失败后留下半提交状态。
- 应建立手臂专用的状态快照与回滚边界。
- 快照应覆盖相关控制器、父级与父级逆矩阵、TRS、必要的骨骼姿态及约束 Influence。
- 任一提交阶段发生异常，必须恢复并核验修改前状态。
- 快照与回滚机制必须有单一实现归属，不得让 Rig 和 WBC 分别建立互相独立的回滚系统。

Influence 合同：

统一要求：

- NaN / Inf 拒绝。
- 小于 0 或大于 1 的输入拒绝。
- 不允许某个函数自动截断而另一个函数直接接受。
- 实际约束 Influence 与反馈中的有效权重必须保持语义一致。
- 非法输入拒绝必须发生在任何场景写入之前。

以上属于 Task 10 的目标合同，不代表当前源码已经完成。

#### 4.2.4 10-C：PlannedHandTarget、Bridge 与 WBC 无损接口合同

负责范围：

- `src/motion/kinematic_bridge.py`
- `src/motion/whole_body_controller.py`

主要数据结构：

- `PlannedHandTarget`
- `KinematicPlannedPose`
- `EndEffectorTarget`
- `WholeBodyControlTargets`

必须收敛以下接口问题。

##### A. Bridge 字段无损传递

当前：

`PlannedHandTarget` 已经具备：

- `world_xyz`
- `rotation_deg`
- `enabled`
- `weight`
- `contact_intent`
- `is_locked`
- `surface_id`
- `contact_type`
- `normal_world`

但尚未提供与 WBC / Rig 对应的：

- `pole_hint_world_xyz`
- `clamp_reach`

WBC 已有对应的 Pole Hint 和 Reach Clamp 能力。

Task 10 必须核验并补全规划数据结构与转换接口，避免：

```
MotionAction
    |
PlannedHandTarget
    |
KinematicBridge
    |
WholeBodyControlTargets
    |
WholeBodyController
    |
Arm IK
```

过程中丢失规划端可以表达的控制信息。

新增数据字段必须放在兼容位置，保持既有构造方式的语义和历史调用兼容。

##### B. FK / IK 仲裁

必须明确：

- `enabled=False`：IK 关闭，由 FK 关节姿态控制。
- `enabled=True`：IK 目标生效。
- 左右手分别仲裁。
- 禁用一侧不得关闭另一侧。
- 目标权重为 0 时不得错误保留上一帧的有效 IK 权重。
- FK 与 IK 不得同时成为同一侧的冲突写入源。

##### C. 目标位置与姿态语义

现有系统中的手部目标位置语义必须冻结为：

`Wrist World Position`（即手腕关节的世界坐标）。

姿态语义：

`Hand Bone World Orientation`（即手部骨骼的世界朝向）。

当前目标不是手指尖位置，也不是掌心表面接触点。

WBC 的位置误差反馈必须与该定义保持一致。

未来若需要指尖目标，必须另行定义掌部局部锚点和指尖几何偏移，不得把该能力提前描述为 Task 10 已具备。

##### D. ROM 与可达性反馈

必须保证：

- 实际手腕位置误差可追踪。
- 3D 手部旋转误差可追踪。
- 左右臂可达性独立报告。
- ROM 违反明确进入失败反馈。
- ROM 截断后重新计算实际末端误差。
- 不允许 IK 目标已到达、ROM 截断后仍伪报成功。

#### 4.2.5 10-D：独立上肢运动轨迹与历史动作兼容

负责范围：

- `src/motion/terrain_walk.py`
- `src/motion/kinematic_bridge.py`
- 必要时涉及现有 MotionAction 的目标生成逻辑。

当前实际情况：

- `TerrainWalkAction` 中的左右上臂、前臂和手部 FK 旋转仍然由步态相位与经验性正弦函数直接驱动。
- 其他历史动作也保留各自的 FK 摆臂计算。

Task 10 必须解决：

- 上肢运动不再被强制绑定为下肢 `gait_phase` 的直接函数。
- 左右手应能够独立指定目标。
- 上肢轨迹应拥有独立的时间或进度参数。
- 上肢轨迹可以明确选择 FK 或 IK 模式。
- IK 模式下目标通过 `PlannedHandTarget` 进入现有 Bridge / WBC。
- FK 模式仍使用现有 FK 控制路径。
- 不建立第二套 MotionAction 或动作调度系统。
- 不允许直接绕过 Bridge / WBC 操作生产骨骼。
- 可以与下肢步态同步，但不能在架构上强制依附于下肢相位。

历史动作保护：

- Walk / StartStopWalk。
- Run。
- SprintStart。
- SprintBrake。
- TerrainWalk。

上述动作必须保留原有下肢运动、根运动、接触和时间连续性。

不得为了完成上肢 IK 而整体推翻历史动作。

本次重点是解耦独立上肢运动能力和 TerrainWalk 的经验性正弦摆臂。其他历史动作的迁移必须依据明确的兼容测试和任务范围，不得擅自批量改写。

#### 4.2.6 Task 10 验收范围

Task 10 必须分别通过：

- Rig 初始化与重复调用合同。
- 世界空间矩阵合同。
- 左右臂独立性。
- HandIK / ElbowPole 独立控制。
- 输入有限性与边界拒绝。
- 写入事务与完整状态回滚。
- Influence 合同。
- Bridge 字段无损传递。
- FK / IK 明确仲裁。
- 手腕位置与手部姿态反馈。
- ROM 边界和截断后误差。
- 独立上肢轨迹。
- 历史动作回归。
- Blender 场景真实姿态检查。

自动化测试通过不代表视觉验收完成。

Task 10 必须整体验收，不得只凭 `verify_task6fa_arm_ik.py` 已经存在就宣称 Task 10 完成。

### 4.3 节点 11：FootLock

状态：

`PLANNED — NOT STARTED`

正式范围：

FootLock — 锁定元数据生命周期、状态查询与支撑维持副作用合同

Task 11 负责关闭：

- `FIND-R3-03`
- `FIND-R3-04`

不得创建重复 Finding ID。

#### 4.3.1 11-A：锁定元数据与生命周期

负责文件：

- `src/rig/foot_contact.py`
- `src/rig/ik.py`

主要接口：

- `lock_foot_contact()`
- `unlock_foot_contact()`
- `reset_leg_ik()`

当前 FootIK 控制器上的锁定状态包括：

| 字段 | 语义 |
|---|---|
| `is_locked` | 当前锁定状态 |
| `contact_world_xyz` | 锁定接触点 |
| `locked_ankle_world_xyz` | 锁定踝部世界坐标 |
| `target_rotation_deg` | 锁定姿态 |
| `locked_foot_head_xyz` | 锁定时足部骨骼头位置 |
| `locked_foot_tail_xyz` | 锁定时足部骨骼尾位置 |
| `locked_foot_center_xyz` | 锁定时足部网格中心 |
| `locked_foot_min_z` | 锁定时足部最低点 |

必须严格区分：

- 当前有效锁定状态。
- 锁定期间需要使用的参考快照。
- 已解锁或已重置后不再有效的历史元数据。

必须解决：

- `unlock_foot_contact()` 设置 `is_locked=False` 后仍保留旧快照字段的问题。
- `reset_leg_ik()` 设置 `is_locked=False` 后仍保留旧快照字段的问题。
- 后续重新锁定是否会完整覆盖所有旧值。
- 消费者是否可能读取到过期快照并将其误认为当前锁定状态。
- 解锁、重置、重新锁定与场景重开后的生命周期一致性。

成功解锁或重置后，必须统一使旧锁定快照失效，不得让失效数据继续被解释为当前锁定状态。

具体采取删除、显式失效标记还是独立状态容器，必须在读取全部消费者后确定，不能只清理写入端。

必须保留 09-B-4 已经建立的事务回滚合同。

失败回滚时，七项锁定元数据必须完整恢复，不允许为了清理旧状态破坏回滚能力。

#### 4.3.2 11-B：状态查询与支撑维持副作用边界

负责文件：

- `src/rig/foot_contact.py`

主要接口：

- `evaluate_foot_support()`
- `get_foot_support_state()`
- `move_character_root_with_support()`

当前问题：

`get_foot_support_state()` 直接调用 `evaluate_foot_support()`。

而 `evaluate_foot_support()` 不只是计算和读取，它还可能：

- 调用 `_apply_ik_prebend_hint()`。
- 修改 PoseBone 姿态。
- 解除 FootIK 父级。
- 修改 FootIK 的世界位置和旋转。
- 解除 KneePole 父级。
- 修改 KneePole 的世界位置。
- 调用 View Layer Update。

因此现有函数名称与实际副作用之间存在接口语义缺口。

必须把以下两类职责分离：

只读查询：

- 读取当前真实锁定状态。
- 读取实际控制器及骨骼世界位置。
- 计算漂移、可达性与支撑指标。
- 不修改骨骼。
- 不修改控制器。
- 不改变父级。
- 不修改锁定元数据。
- 不通过隐藏的场景刷新产生状态写入。

显式支撑维持：

- 需要时维持锁定 FootIK 的世界位置。
- 需要时更新 KneePole 支撑位置。
- 必要时执行姿态预弯。
- 明确执行场景更新。
- 返回维持后的真实状态。

必须对所有调用者做审计，尤其是 WBC 的锁定脚执行分支。

不能为了让查询变成只读而删除现有必要的支撑维持逻辑。

必须通过独立函数或清晰接口职责分离两类行为，函数命名与副作用必须一致，并保留合理的历史调用兼容性。

#### 4.3.3 Task 11 验收范围

- 锁定状态与元数据一致性。
- 锁定快照失效和重建。
- Unlock / Reset / Relock 生命周期。
- 09-B-4 回滚回归。
- 只读查询零副作用。
- 支撑维持功能完整保留。
- WBC 调用路径正确。
- 连续动作中的脚部世界位置保持。
- Blender 场景重开后状态一致。

Task 11 必须关闭 `FIND-R3-03` 和 `FIND-R3-04`。

### 4.4 节点 12：PKG-5 跨模块联合闭环

状态：

`PLANNED — BLOCKED BY TASK 10 / TASK 11 ACCEPTANCE`

正式范围：

PKG-5 Cross-Module Integration, Failure Atomicity & Joint Acceptance

Task 12 不新增独立运动功能，不重新实现已有模块。

Task 12 的作用是核对各模块组合以后是否仍满足真实的数据流、状态所有权、失败传播和连续动作合同。

#### 4.4.1 12-A：WBC 单帧写入与失败原子性

负责文件：

- `src/motion/whole_body_controller.py`

审查执行顺序：

1. Root / Pelvis。
2. Spine / Neck / Head。
3. FK Joint Rotations。
4. Leg IK / FootLock。
5. Arm IK / FK。
6. 场景更新。
7. 末端位置及姿态反馈。
8. ROM 校验与可选截断。
9. CoM 计算。
10. 结果状态返回。

必须验证：

- 任一阶段异常时，前序写入是否留下残留。
- 左右臂、左右腿是否可能出现一侧成功、一侧失败。
- FootLock 状态与 WBC 目标是否一致。
- ROM 截断后的末端误差是否真实。
- 失败结果是否反映最终实际骨架状态。
- 是否存在需要事务恢复的部分提交。

#### 4.4.2 12-B：Bridge 帧提交和失败传播

负责文件：

- `src/motion/kinematic_bridge.py`
- `src/motion/framework.py`

必须核验：

- WBC 失败后是否仍插入关键帧。
- ContactModel 几何失败后是否仍提交无效帧。
- 失败帧是否更新 `_last_time_sec` 和 `_last_frame`。
- 失败帧是否更新跨帧接触状态。
- Bridge 的 `overall_success` 与 WBC 结果是否一致。
- MotionPlanner 是否阻止失败状态继续流转。
- 失败帧是否污染后续动画轨迹。

#### 4.4.3 12-C：跨模块状态所有权与接口一致性

至少覆盖：

| 模块关系 | 核验重点 |
|---|---|
| Bridge ↔ WBC | 目标、反馈、异常与帧状态 |
| WBC ↔ FK / IK | 唯一骨骼写入所有权 |
| Arm IK ↔ Joint ROM | 实际姿态、约束和反馈一致性 |
| FootLock ↔ ContactModel | 接触生命周期与有效支撑 |
| ContactModel ↔ MotionState | 状态提交与跨帧更新 |
| CoM ↔ BodyKinematics | 输入姿态快照和时间戳 |
| BodyKinematics ↔ BodyInertia | 速度、角速度和惯性状态 |
| MotionAction ↔ Bridge | 规划目标与生产写入路径 |
| WBC ↔ Rig | 所有控制器和 PoseBone 写入职责 |

必须识别重复状态、隐式状态、双写状态和过期快照。

不得为了统一接口而破坏现有向后兼容能力。

#### 4.4.4 12-D：全系统连续动作与联合回归

必须覆盖：

- Task 09 下肢世界空间合同。
- Task 10 双臂独立 IK/FK。
- Task 11 FootLock 生命周期。
- Walk / StartStopWalk。
- Run。
- SprintStart。
- SprintBrake。
- TerrainWalk。
- 双手和双脚同时控制。
- 左右肢体独立目标。
- 连续帧切换。
- IK / FK 模式切换。
- 锁定 / 解锁。
- 动作中断。
- 异常恢复。
- Reset 后重新执行。
- Blender 场景保存与重开。

必须运行适当的 Quick、Physics、Motion、Full 回归。

不得仅把专项测试数量相加来判定系统通过。

必须分别记录：

- 普通 PASS。
- AUTOMATED_PASS。
- SKIPPED。
- NOT_RUN。
- 视觉待检查项。
- 已完成视觉检查的项目。

Task 12 必须建立独立的联合验收证据包。

#### 4.4.5 Task 12 通过条件

以下条件必须同时满足：

1. Task 10 独立验收通过。
2. Task 11 独立验收通过。
3. 所有开放 Finding 已关闭并具有证据。
4. WBC / Bridge 失败传播合同通过。
5. 跨模块状态所有权无冲突。
6. 历史动作回归无退化。
7. 联合回归通过。
8. 视觉验收单独完成并明确记录。
9. 完整交付证据归档。

Task 12 未通过，不得宣布 PKG-5 全部完成。

### 4.5 PKG-5 子任务编号规则

正式使用：

`节点编号 - 模块字母 - 修复轮次`

例如：

- `10-a-1`
- `10-a-2`
- `10-b-1`
- `10-c-1`
- `10-d-1`
- `11-a-1`
- `11-b-1`
- `12-a-1`
- `12-d-1`

编号含义：

- 第一段：PKG-5 主节点。
- 第二段：固定模块字母。
- 第三段：该模块的修复轮次。

规则：

1. 每个节点的模块字母职责固定，不得随意变化。
2. 同一模块第一次执行为 `-1`。
3. 同一模块第一次修复未通过，第二轮为 `-2`。
4. 不得把修复轮次误当成提交次数。
5. 不得为了编号整齐创造没有实际工作内容的模块。
6. 不得擅自创建 `09-B-5`。
7. 每个具体子任务必须对应独立任务卡、独立验证结果和 Git 提交证据。

只有项目负责人明确确认后，才允许改变上述模块划分。

当前下一任务：

`10-a-1`

但本次文档同步任务完成前，不得开始代码修改。

## 5. 后续 Phase 阶段门禁

### Phase 7A

已有 7A 地形角色与生产场景相关代码和验证资料。

不得将早期项目状态摘要中“尚未实现”的旧记录直接当成当前状态。

对 7A 的具体验收状态只能以对应实际产物与验证证据为准。

### Phase 7B：Upper-Limb Independent Motion & End-Effector Target Verification

状态：`NOT AUTHORIZED`

前置条件：

1. PKG-5 / 09-B 完成独立核验（09-B-4 已验收）。
2. PKG-5 / 10 Upper-Limb IK/FK 完成。
3. PKG-5 / 11 FootLock 完成。
4. PKG-5 / 12 全仓联合验收通过。
5. 项目负责人明确批准开启 Phase 7B。

### Phase 7C：Pipeline A / Pipeline B Confluence

状态：`NOT AUTHORIZED`

定位：

- 将生产运动学管线与现有 6-DOF 数值动力学状态合流。
- 复用现有数值动力学模块。
- 不得提前创建第二套 IK、WBC 或动力学求解器。

**7C 是未来的架构合流节点，不是当前 09-B、10、11 的修复要求。**

### Phase 7D

多关节动态协调。

### Phase 7E

复用现有 IK/FK 求解器，完成动态合作与接触切换。

### Phase 7F

全身移动、抓握、支撑、释放与连续训练场通行。

### Phase 6H

动态平衡与主动补偿，必须遵循路线图的前置依赖。

不得提前跨越阶段，也不得创建未经批准的衍生阶段。

## 6. 模块审计与跨模块审计纪律

今后每个模块必须先独立审计。

每个模块至少检查：

1. 真实源码和公开符号。
2. 输入参数及单位。
3. 输出数据结构。
4. 调用者与消费者。
5. 世界空间和局部空间合同。
6. 状态所有权。
7. 内部写入与外部副作用。
8. 异常和失败传播。
9. 事务原子性。
10. 边界值和非有限输入。
11. 已有自动化测试覆盖。
12. 历史回归和视觉验收条件。

模块独立审计之后，才进行跨模块接口审计。

模块问题不能凭想象增加 Finding ID。未验证内容只能标为 `AUDIT_PENDING` 或 `UNVERIFIED`。

## 7. 坐标与单位约定

- 世界坐标：+Z Up。
- +X：角色右侧。
- +Y：角色前方。
- 地面参考面：Z = 0.0m。
- 距离：m。
- 速度：m/s。
- 加速度：m/s²。
- 时间：s。
- 角度：deg 或 rad，必须明确。
- 质量：kg。
- 转动惯量：kg·m²。

世界空间目标不得在缺少有效父级矩阵合同的情况下直接当作局部空间赋值。

## 8. 当前架构同步状态规则

- PKG-5 / 09-B 已完成，09-B-4 已通过独立验收。
- 当前 Task 10 进行中（10-A 已归档验收，10-B-1 至 10-B-3 已实现测试归档，生产级事务快照与回滚尚未实现，整体 10-B 保持 IN PROGRESS — NOT ACCEPTED，后续计划 10-B-4，Task 10-C 尚未准入）。
- Task 11 负责 FIND-R3-03、FIND-R3-04。
- Task 12 负责 PKG-5 跨模块联合审计与验收。
- 10、11、12 全部通过联合验收并获得项目负责人明确批准之前，不得开启 Phase 7B。
- Pipeline A 与 Pipeline B 的独立性目前是设计事实，不是故障。
- 7C 才负责未来的系统级动力学合流。
- CoM、BodyKinematics、BodyInertia 不得被描述为已经驱动姿态补偿。
- ContactModel 不得取代 FootLock。
- WBC 不得取代动作规划器或底层 IK/FK。
- 所有历史成熟步态必须保留。

本文件随真实工程演进，但每次修改必须能追溯至实际代码、测试、批准决策或项目负责人明确要求。
