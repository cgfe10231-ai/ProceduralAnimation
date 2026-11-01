# ARCHITECTURE_SYNC：工程动态架构与模块调用同步

> **文档定位**：动态工程架构同步文档。记录当前已经实现、已经核实的真实调用关系、模块职责、状态所有权、审计进度与后续准入边界。
>
> **总架构保护**：`ARCHITECTURE.md` 是全项目总架构蓝图，本文件不得替代、复制、重构或擅自修改总架构。
>
> **本次审计基准 HEAD**：`2904857433af01c2a7991e2da085b3c0f53a145f`
>
> **当前修复节点**：PKG-5 / 09-B-3。
>
> **当前验收状态**：`IN PROGRESS — NOT ACCEPTED`。不得将历史 09-B 验收结果直接视为当前 09-B-3 已验收。
>
> **当前工程核心事实**：19 骨骼角色运动学执行管线与 6-DOF 数值质心动力学管线保持独立；二者未来的合流属于 Phase 7C，不是当前 09-B 或 PKG-5 的待修缺陷。

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
| 08 Rig | 刚体平移与世界空间隔离回归 | 历史完成记录 |
| 09-A | Lower-Limb Ground × Reach：三维地面高程和可达域约束 | 已有历史专项验收记录 |
| 09-B-3 | Lower-Limb World Rotation：有效父级变换、世界旋转数学域、控制器生命周期与失败原子性第三次修复 | 当前冻结节点，等待重新核验，不得标记通过 |
| 10 | Upper-Limb IK/FK：双臂接口合同与独立轨迹控制 | 待准入 |
| 11 | FootLock：锁定元数据生命周期与状态查询/支撑维持副作用合同 | 待修复 |
| 12 | PKG-5 综合接口闭环和全仓联合验收 | 待 09-B-3、10、11 完成后执行 |

### 4.1 09-B-3 当前准确状态

当前源代码文件：

- `src/rig/ik.py`
- `tests/test_leg_ik_world_rotation_contract.py`

最新代码使用的有效父级矩阵：

\[
M_{\mathrm{eff}}=M_{\mathrm{parent}}\cdot M_{\mathrm{parent\_inverse}}
\]

当前实现的数学支持域：

- 拒绝非有限矩阵元素。
- 拒绝非仿射矩阵。
- 拒绝负行列式的镜像反射。
- 拒绝零行列式的奇异矩阵。
- 拒绝 \(s^2\leq 10^{-12}\) 的退化尺度。
- 拒绝 Gram 矩阵相对偏差大于 \(10^{-6}\) 的非共形变换。
- 支持纯旋转以及正均匀缩放和旋转组合。

当前测试文件已有 TEST-01 至 TEST-21。

但现存 `AI_SYNC.md` 中的最新实际执行记录为此前的 17/17，并且该记录早于 TEST-18 至 TEST-21 的增加。

测试文件顶部 TEST-15 的说明仍写着 `det <= 1e-7`，与当前实现使用 `det == 0` 的奇异矩阵判断不一致。

本次文档必须明确记录：

1. TEST-18 至 TEST-21 已经出现在测试源文件。
2. 当前仓库文档没有提供这四项新增测试的最新实际执行记录。
3. 不得声明 21/21 已通过。
4. 09-B-3 当前状态必须保持 `IN PROGRESS — NOT ACCEPTED`。
5. 只有后续实际运行、检查输出和独立审查后才能改变状态。

### 4.2 节点 10：Upper-Limb IK/FK

目标：

- 双臂独立三维目标。
- 手部末端世界空间目标和 3D 姿态。
- 正确区分 FK 摆臂与独立 IK 目标。
- 解耦 TerrainWalk 中经验性正弦摆臂。
- 审核左右臂独立性、手肘 pole、手腕旋转、可达性与 ROM。
- 审核 `matrix_parent_inverse`、有效父级矩阵、世界空间输入输出。
- 审核非有限输入和异常处理。
- 审核写入前后失败原子性。
- 复用现有 `src/rig/arm_ik.py` 和 WBC，不建第二套 IK/FK。

### 4.3 节点 11：FootLock

必须处理：

- `FIND-R3-03`：`unlock_foot_contact()`、`reset_leg_ik()` 的元数据残留与生命周期语义。
- `FIND-R3-04`：`evaluate_foot_support()` 的未声明状态维持副作用。

必须明确：

- 哪些函数只查询。
- 哪些函数会修改。
- 修改哪些控制器和骨骼。
- 哪些数据属于锁定状态，哪些属于历史快照。
- 解锁与重新锁定如何保持世界位置和姿态不跳变。
- 不允许简单清除全部元数据。
- 不允许简单删除现有支撑维持写入。

### 4.4 节点 12：综合闭环

12 不等于把三个专项测试通过数量相加。

必须分别审计模块自身，再审计模块之间的接口关系。

需要覆盖：

- MotionPlanner / MotionAction 与 Bridge。
- Bridge 与 WBC 的目标、结果、失败传播。
- WBC 与 FK、Leg IK、Arm IK、FootLock。
- IK/FK 与 ROM。
- FootLock 与 ContactModel。
- CoM、BodyKinematics、BodyInertia 的输入、输出、状态更新与只读边界。
- ContactModel 与 MotionState。
- 历史动作和 7A 地形动作是否保留。
- 连续帧、失败帧、重置、左右肢体独立和动作切换。

必须进行跨模块场景和联合回归，不得仅凭单模块通过判定整体通过。

## 5. 后续 Phase 阶段门禁

### Phase 7A

已有 7A 地形角色与生产场景相关代码和验证资料。

不得将早期项目状态摘要中“尚未实现”的旧记录直接当成当前状态。

对 7A 的具体验收状态只能以对应实际产物与验证证据为准。

### Phase 7B：Upper-Limb Independent Motion & End-Effector Target Verification

状态：`NOT AUTHORIZED`

前置条件：

1. PKG-5 / 09-B-3 完成独立核验。
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

- 09-B-3 不得标记为已验收。
- 10、11、12 尚未完成，不得开启 7B。
- Pipeline A 与 Pipeline B 的独立性目前是设计事实，不是故障。
- 7C 才负责未来的系统级动力学合流。
- CoM、BodyKinematics、BodyInertia 不得被描述为已经驱动姿态补偿。
- ContactModel 不得取代 FootLock。
- WBC 不得取代动作规划器或底层 IK/FK。
- 所有历史成熟步态必须保留。

本文件随真实工程演进，但每次修改必须能追溯至实际代码、测试、批准决策或项目负责人明确要求。
