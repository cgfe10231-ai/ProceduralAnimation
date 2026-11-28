# ARCHITECTURE_SYNC：工程动态架构与模块调用同步

> **核验日期**：2026-11-28
> **核验源码及证据收归基线**：**Task 12 / PKG-5** 冻结生产源码基线 `eee276b39d204ccd46f4c17f37a09ec483bfcbae`、冻结测试基线 `90f4628a0c4212f4bb0468941cdde362cd68bef2`、最终验收证据提交 `e15d342b805ef45e7d54db2edf1c2804973e81a7`（BUG-01 过程保全 `c9c9a2d7949aee916fa44273399aa6aff937cd54`），经 `task/12` 合并收归 `master`；**Task 7B-1** 专项验收提交 `fcb35bd58eeb4e5300d5f3b28e3615be8cb7c946`、**Task 7B-2** 专项验收提交 `a92280bbcb2243f0b43edd10b61bbadb39c72869`（保留于 `task/7b-1` → `task/7b-2` → `task/7b-3` → `task/7b-4` 连续子分支，已合入 `master`）；Task 11 历史基线 `added88a7e27eaaa6d1644473d560c5dcf45bc80` / `07aec5d8d35e5d77ff956f160840d1c2491b770e`（收归 `task/11`）；Task 10-D 历史基线 `824c52ec73f86aa3d08245a58297118cb4a9f110` / `7f14ff722caecadec555194cc7d08f454c94c6c8`（收归 `task/10-d`）；10-B 历史合入 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`（回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`、证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`）；10-C 历史合入 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`（集成复验基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae`）。 Task 7B-3 专项最终证据：`d9862ada5c392080a03efb38ea7f2e90201580d2`。 冻结执行基线 `a3720711bfdae1e759485c13f4fc3379be951534`；证据提交 `4a2f4a0743803e1cb747f0927b236dd357694c39`、`1cc2a4b18a309723dc5a0cae2a4e981e2e263f82`，证据目录 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`。
> **文档职责**：记录真实存在的模块、调用链、职责和当前任务进度；不修改 `ARCHITECTURE.md` 的永久规则或既有合同正文。
> **10-A**：`COMPLETED — ARCHIVED`；**10-B / 10-C / 10-D / Task 10（整体）**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。
> **Task 11（`11-A` + `11-B`）**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`FIND-R3-03` 与 `FIND-R3-04` 正式关闭，原 16 项历史 Finding 已全部关闭：16 CLOSED / 0 OPEN）。
> **Task 12 / PKG-5**：**`Task 12-A/B/C/D` `COMPLETED`，`Task 12-D BUG-01` `CLOSED`，`Task 12 / PKG-5` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`**。
> **当前节点与阶段门禁**：**`Task 7B-1` — `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`**（Blender 5.1.1 专项 `T01–T12` `12/12 PASS`，`BUG-01 CLOSED`，生产源码零修改，证据提交 `fcb35bd5`，已合入 `master`）；**`Task 7B-2` — `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`**（Blender 5.1.1 专项 `T01–T14` `14/14 PASS`，`BUG-01、BUG-02 CLOSED`、`src/motion/contact_model.py` Blob `267c6c99`、证据提交 `a92280bb`、`docs/evidence/7b-2/verification/`，已合入 `master`）；`Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（20/20 PASS，`d9862ada`）；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。
> **现行实现核对**：`src/motion/whole_body_controller.py` (`230a86acaa92b580c5c0aad0e0cdacd7df224a7a`) 在 Task 12-A 收归 ROM 截断后最终四肢/CoM 重测、`ROM_CONFLICT` 真实请求误差及单帧失败原子恢复；`src/motion/kinematic_bridge.py` (`4f9cc856b9c9b34c59dd4c6a4f0cee1e1d86ef96`) 在 Task 12-B/C 收敛 `effective_dt` 准入门禁、失败帧不提交 7 项跨帧状态，并移除废弃 `_reconcile_post_rom_feedback()`（ROM 后最终反馈归 WBC 独占）；`src/motion/body_kinematics.py` (`e204793ca3a326a798f75a66e24e98a945e53be7`) 与 `src/motion/body_inertia.py` (`0cd7efadf265072fd1665615815792f41b792f1b`) 在 Task 12-C 收敛有效支撑接触测量与时空快照一致性；`src/rig/ik.py` 与 `src/rig/foot_contact.py`、`src/rig/arm_ik.py` 与 `src/scene_transaction_integrity/`、`src/motion/upper_limb_trajectory.py` 维持既有已验收实现。
> **证据边界**：Task 12 最终联合验收见 `docs/evidence/12/final_acceptance/`（BUG-01 过程保全见 `docs/evidence/12/unified_verification/`，Task 12 人工视觉验收登记为 `OWNER WAIVED`）；Task 11 见 `docs/evidence/11/unified_verification/`；10-D 见 `docs/evidence/10-d/final_acceptance/` 与 `docs/evidence/10-d/10-d-5/centralized_verification/`；10-B 见 `docs/evidence/10b_sixlayer_split/regression/`（九项历史视觉待办独立保留；10-D 人工验收仅登记 `task10d_centralized_whole_body.blend` 与 `task10d_running_whole_body.blend`；10-D 复验 JSON 的 `head` 引用旧常量但实际 Worker 运行于当前仓库，原始报告未篡改；B19 保留部分 F-Curve 写故障残余风险）。
> **跨管线状态**：19骨骼运动学生产管线与独立6-DOF数值动力学管线仍分离，尚未完成 Phase 7C 合流。

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
| 动作编排 | `src/motion/framework.py` | `MotionPlanner`、`MotionRuntimeContext.compose_planned_pose()`、`MotionAction`、中央与历史动作时间轴及状态流转 |
| 上肢轨迹参数化 | `src/motion/upper_limb_trajectory.py` | 无状态 `UpperLimbSegment`、五次时间平滑与序列验证（`terrain_walk.py` 保留兼容重导出） |
| 地形步态规划 | `src/motion/terrain_walk.py` | 真实地形查询、根轨迹、落脚调度、摆动脚轨迹及局部上肢兼容接入 |
| 帧级桥接 | `src/motion/kinematic_bridge.py` | 将规划目标转换成 WBC 目标，组织单帧执行、约束权重关键帧持久化及反馈同步 |
| 全身协调 | `src/motion/whole_body_controller.py` | Root、Pelvis、躯干 FK、四肢 IK/FK 的统一调度和验证 |
| 下肢 IK | `src/rig/ik.py` | 双腿 IK 目标、可达性、地面高程与世界旋转合同 |
| 上肢 IK | `src/rig/arm_ik.py` | 双臂 IK、手腕目标与手部 3D 姿态 |
| FootLock | `src/rig/foot_contact.py` | 支撑脚锁定、解锁、7 项锁定元数据生命周期、主动支撑维持（`evaluate_foot_support()`）与零副作用纯查询（`get_foot_support_state()`） |
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
- 收集由 WBC（含 ROM 截断后重测）输出的最终末端追踪、ROM 诊断、真实请求误差及接触几何/遥测数据（废弃 `_reconcile_post_rom_feedback()` 已于 Task 12-C 移除）。
- 执行 `effective_dt` 准入门禁与 WBC/ContactModel 失败防提交门禁（失败帧仅返回诊断状态，禁止插入关键帧或更新跨帧 7 项提交状态）。
- 构建并仅在成功时提交 `MotionState` 与关键帧。

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

文件：`src/rig/foot_contact.py`（与 `src/rig/ik.py` 共享 `FOOT_LOCK_METADATA_KEYS` 与快照回滚机制）

职责：

- 支撑脚锁定和解锁及 7 项锁定元数据生命周期管理（`lock_foot_contact()`、`unlock_foot_contact()`、`setup_leg_ik()`、`reset_leg_ik()`）。
- 显式主动支撑维持（`evaluate_foot_support()`、`move_character_root_with_support()`）：先核验锁定快照与双侧控制器存在性（不经过退化自动重建消除有效锁定），再维护世界空间接触目标、KneePole 位置、预弯与场景刷新。
- 零副作用只读状态查询（`get_foot_support_state()`）：经 `get_leg_ik_state(..., update_scene=False)` 读取当前已求解场景中的控制器及骨骼世界位置、可达性与漂移指标，不创建/改写对象、骨骼、约束或自定义属性。

历史 Finding 状态：

- `FIND-R3-03`：**`CLOSED / VERIFIED`**（Task 11-A 完成生命周期清理、7 键覆盖顺序及 `IDPropertyArray` 脱离快照/回滚验证）。
- `FIND-R3-04`：**`CLOSED / VERIFIED`**（Task 11-B 完成零副作用纯查询与主动支撑维持分离，含 BUG-01 准入顺序修复）。

不得为了形式上的只读而删除既有支撑维持逻辑，已完整保留现有 FootLock 真实稳定性合同。

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
- 单一无状态手掌环境目标几何转换函数 `compute_hand_target_from_surface()`（Task 7B-2 已验收：由真实 Mesh `SurfaceQueryResult` 与切向参考向量纯数学计算世界空间手腕位置与三维欧拉姿态，不访问 `bpy`、不建立接触、不执行 IK/ROM）。

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
| 10 | Upper-Limb IK/FK：双臂接口合同与独立轨迹控制 | `10-A` 已归档；`10-B` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）；`10-C` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）；`10-D` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（2026-11-27）；**Task 10 整体 `COMPLETED`** |
| 11 | FootLock：锁定元数据生命周期与状态查询/支撑维持副作用合同 | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`**（`11-A`、`11-B` 均通过独立审计与联合验收，`FIND-R3-03`、`FIND-R3-04` 已关闭） |
| 12 | PKG-5 综合接口闭环和全仓联合验收（含 12-D BUG-01） | **`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`**（`12-A/B/C/D COMPLETED`、`12-D BUG-01 CLOSED`；`eee276b39d` / `90f4628a0c` / `e15d342b80` / 主干合并 `d1645452`；PKG-5 全部完成并收归 `master`；`Task 7B-1`、`Task 7B-2` `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`；`Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`） |

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

> **版本边界**：本节包含历史任务设计与实现过程；涉及旧节点“当前”措辞时，均以本文件顶部和第8节的2026-11-20状态为准；合同正文不作追认或重写。

状态（分阶段精确状态）：

- **10-A**：已归档验收（`COMPLETED — ARCHIVED`）。
- **10-B**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（原负责人验收日期：2026-11-20；批准设计基准 `124747e900a1db5790ed5f4159f561dba19890ff`；六层拆分回归基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`，回归证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`，主干合并提交 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`；当时主干生产及测试源码与拆分后验收版本完全一致；12 项批准合同正文不变，WBC 独立合同不属于 10-B 结项门槛且不宣称 Task 12 完成）。
- **10-C**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Task 10-C 四个子节点于 2026-11-21 完成历史分支验收（`task/10-c-child4`，`d3d7f135975ac5a2a9b01e2706434d0463a563cd`）；2026-11-26 在六层架构集成基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 复验通过并收归 `master`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）；已在 `824c52ec` 现行 `kinematic_bridge.py` 复验通过。
- **10-D**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（2026-11-27 人工视觉验收两份中央全身场景通过；最终回归与 T01–T17 全部通过）。**Task 10 整体 `COMPLETED`。**

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

- `src/rig/arm_ik.py`（保留五个公开领域入口及领域配置常量，不再承载历史事务私有实现和兼容代理）
- `src/scene_transaction_integrity/`（六层物理架构实现、`wiring.py` 装配入口与 `fault_injection.py`）
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

以上属于 Task 10 的目标合同；对应六层物理实现已完成拆分、全量回归与主干收归。

##### 4.2.3 实际物理架构归属（`src/scene_transaction_integrity/`）

`src/scene_transaction_integrity/` 目录中共 81 个 Python 文件，包含包初始化文件（`__init__.py`），不将其误称为 81 个独立业务模块。

| 物理位置 | 已迁移职责 |
|---|---|
| layer1/ | 事务协调、准入、生命周期、隔离授权、清理调度 |
| layer2/ | 会话身份、事务上下文、状态及所有权注册表、关系日志 |
| layer3/ | 受权资源创建、删除、链接、解绑、Parent及Constraint关系操作 |
| layer4/ | 上肢IK输入验证、业务数值操作、状态查询及依赖图更新 |
| layer5/ | 快照捕获、结构指纹、回滚恢复、完整性及隔离证据核验 |
| layer6/ | 提交后受权清理与清理结果 |
| wiring.py | 现有各层显式依赖装配与统一接线 |
| fault_injection.py | 唯一共享测试故障注入机制 |

- `src/rig/arm_ik.py` 保留五个公开领域入口及领域配置常量，不再承载历史事务私有实现和兼容代理。
- 事务上下文由 `wiring._create_arm_rig_transaction_context()` 装配 15 项显式依赖。

#### 4.2.3.1 10-B 后验收物理拆分：按正常上肢初始化调用链（负责人指定，2026-11-22）— `COMPLETED — MERGED TO MASTER`

> **用途与状态**：本节已达 **`COMPLETED — MERGED TO MASTER`**，作为 10-B 六层物理拆分的顺序执行链及历史归档保留。原执行次序、异常保护规则和历史拆分约束均完整保留，不删除原调用链；10-B 不再重新打开，不得借历史拆分边界扩展至整个角色创建、下肢、FootLock、WBC 全身帧级事务、Bridge、环境以及 10-C/10-D。

**排序起点与原则**：沿正常、无异常、首次调用 `setup_arm_ik()` 的真实执行顺序，从上到下逐段审计并确定拆分边界。先追踪左手 `HandIK.L` 和 `ElbowPole.L`；真实代码随后在**同一个外层事务**中初始化右手，不允许为左手单独提交。六层会重复进入，不是 `Layer 1 → 2 → 3 → 4 → 5 → 6` 的单向流水线。

| 顺序 | 正常执行阶段 | 职责层与主要行为 | 本批拆分的审计边界 |
|---|---|---|---|
| 01 | 上肢业务入口 | **Layer 4**：输入验证、解析 Armature、发起 `setup_arm_ik()` | 业务入口与前置检查 |
| 02 | 第一次写入前准入 | **Layer 1 / Layer 2 / Layer 3**：已有会话的准入门禁、控制器归属和同名冲突检查；多层交叉，按实际源码核对先后 | 准入判定与只读边界 |
| 03 | 外层事务开启 | **Layer 1**：`_arm_rig_transaction()` 的入口与嵌套控制 | 事务唯一入口 |
| 04 | 身份与活动事务建立 | **Layer 2**：Armature Session、TransactionContext 和活动事务登记；Layer 1 继续实施门禁 | 状态所有权与层间交接 |
| 05 | 第一次业务写入前 | **Layer 5**：捕获预写入结构指纹及 Arm Rig 状态快照，进入 ACTIVE | 快照独占的读写边界 |
| 06 | 调度左手初始化 | **Layer 4**：选择左侧控制器、目标姿态及约束配置 | 业务调用资源服务的界面 |
| 07 | 左手资源创建和绑定 | **Layer 3 → Layer 2 → Layer 3**：取得/创建 Collection、`HandIK.L`、`ElbowPole.L`，登记新资源创建凭证，再建立 Collection Link 与 Parent；若复用旧资源，则不得伪造创建记录 | 创建、凭证、关系修改的三方界面 |
| 08 | 左手姿态及约束配置 | **Layer 4 ↔ Layer 3**：设置新控制器中立位和上肢骨骼参数，创建/复用并绑定 `ArmIK.L`、`HandRotation.L`，赋予初始 Influence | 业务数值与约束资源边界 |
| 09 | 右手初始化 | **沿 06～08 复用相同调用结构**：处理 `HandIK.R`、`ElbowPole.R`、右臂约束 | 左右两侧共用同一外层事务 |
| 10 | 正常提交 | **Layer 1**：提交前准备、身份核验、COMMITTED、活动事务退出 | 唯一提交决定权 |
| 11 | 提交后清理和返回 | **Layer 1 → Layer 6 → Layer 1**：协调器发起清理、接收与确认结果；没有废弃资源时不得删除正常控制器 | 清理执行、结果交接及最终返回 |

**正常路径简图**：

```text
Layer 4
  → Layer 1/2/3（前置准入）
  → Layer 1（事务入口）
  → Layer 2（会话／事务登记）
  → Layer 5（指纹／快照）
  → Layer 4（左臂初始化调度）
  → Layer 3 → Layer 2 → Layer 3（创建／登记／绑定）
  → Layer 4 ↔ Layer 3（姿态与约束）
  → 同一事务内重复右臂
  → Layer 1（提交）
  → Layer 6（清理）
  → Layer 1（结果确认／结束）
```

**每一次 10-B 物理拆分的强制规则**：

1. **先读本文**：Antigravity 每轮开工都必须重新读取 `ARCHITECTURE_SYNC.md` 本节、`WORKFLOW_GOVERNANCE.md`、`AGENTS.md` 与 `docs/ARCHITECTURE_CHANGE_GATE.md`，并核对当前分支、HEAD 和真实生产源码；不得使用上一轮缓存替代。
2. **先定位再拆分**：在任何修改前，终端必须输出「已读取 ARCHITECTURE_SYNC.md §4.2.3.1」、当前 HEAD、本批对应的**顺序编号、Layer、真实上游、下游、跨层调用与返回、唯一状态及资源所有权**。每批按正常路径从上到下推进；发现真实源码顺序不同，先停止交由 ChatGPT 审计修正。
3. **不得按文件大小或纯目录排序**：函数若横跨多个职责，只能在 ChatGPT 独立审计、负责人明确批准的精确边界内搬运；禁止把整函数直接塞进某一层、另建第二套机制或更改原有外部 API。
4. **每批单独批准**：本节只确定拆分追踪顺序，不授权自动修改生产代码、增加函数/模块/状态、运行测试、更新 Markdown、提交或合并。每批必须遵守先独立审计 → 负责人准入 → 执行 → Diff 审阅 → 另行授权专项/回归测试 → 验收 → 负责人决定 Git 收尾；未批准下一批前必须停止。
5. **正常路径排序≠异常保护可删除**：回滚、失败隔离、提交后挂起和清理权限等已有保护必须在迁移中完整保留，只是不以异常路径作为当前拆分的排序起点。不得更改左右双臂共同原子性、正常创建/复用、世界空间数学、Influence 和资源所有权合同。
6. **文档真实同步**：目标职责与实际物理目录仍应区分；本次物理迁移已完成，并具有独立回归证据（`docs/evidence/10b_sixlayer_split/regression/`，测试基线 `2f248bf4b98776222e37bc3228506a4fb85f7c32`，证据提交 `dcf305738aa9191daeab0f002f97cf4975c12498`，主干合并提交 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）；历史证据不可重写。

---

#### 4.2.4 10-C：PlannedHandTarget、Bridge 与 WBC 无损接口合同

> **10-C当前边界：**`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Task 10-C 四个子节点于 2026-11-21 完成历史分支验收（`task/10-c-child4`，`d3d7f135975ac5a2a9b01e2706434d0463a563cd`）；2026-11-26 在六层架构集成基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 复验通过，已 fast-forward 收归 `master`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）。 本节点结项，不再修改生产实现；10-D 必须另行冻结执行范围。

10-C 专项 A/B/C/D 分别 10/10、15/15、6/6、7/7（合计 38/38 PASS），历史 Bridge 兼容回归 14/14 PASS，累计执行 52/52 PASS；各组退出码为 0。证据：`docs/evidence/10-c-integration/`（`revalidation_manifest.json`、`source_blob_verification.json`、`execution_provenance.json` 及各组原始结果/日志）。

集成测试源码基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 至主干收归基线 `f2501ddc7d610d554d1e813b13564ea56ce2b51a` 的 `src/` 与 `tests/` 无差异；唯一相对 10-C 集成前主干修改的生产文件为 `src/motion/kinematic_bridge.py`（Blob `abdc74455075b83f7188c3dffabc64e456258326`）。

### Task 10-C正式子节点划分（2026-11-20项目负责人批准）

Task 10-C采用独立子节点编号：

`10-c-childN`

`child`仅表示子节点序号，不表示修复轮次、测试轮次或Git提交次数。

本节点严格负责上肢规划目标与现有接口合同收敛。

| 子节点 | 唯一职责 | 修改范围 | 状态 |
|---|---|---|---|
| `10-c-child1` | 现有上肢目标数据结构、转换链、FK/IK仲裁、坐标语义及历史兼容性独立审计 | 只读 | `COMPLETED — AUDITED` |
| `10-c-child2` | 补足PlannedHandTarget的Pole Hint与Reach Clamp表达能力 | `src/motion/kinematic_bridge.py`中的PlannedHandTarget定义 | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（历史验收保留；2026-11-26 集成复验通过并收归主干） |
| `10-c-child3` | 补齐左右手目标转换及FK/IK仲裁语义，保持接触意图独立 | `src/motion/kinematic_bridge.py`中的convert_planned_pose_to_wbc_targets() | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（历史验收保留；2026-11-26 集成复验通过并收归主干） |
| `10-c-child4` | 10-C专项验证、历史兼容回归和最终独立验收 | 已批准的 Bridge 内 ROM 截断后反馈同步（`_reconcile_post_rom_feedback()` 及 `KinematicBridgeExecutor.execute_frame()` 调用点）与冻结测试 | `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（历史验收保留；2026-11-26 集成复验通过并收归主干） |

#### 10-c-child1：已完成审计

ChatGPT已独立核查：

- PlannedHandTarget现有字段。
- KinematicPlannedPose左右手目标容器。
- convert_planned_pose_to_wbc_targets()转换逻辑。
- 既有下游消费接口。
- FK/IK启用及权重语义。
- 手腕世界坐标和手部世界朝向合同。
- 接触意图与IK有效权重的独立性。
- 现有专项测试覆盖情况。

确认两个规划字段缺口：

1. `pole_hint_world_xyz`
2. `clamp_reach`

（历史时间边界保留：2026-11-20 `10-c-child1` 独立审计完成时上述缺口尚未编码；Task 10-C 四个子节点于 2026-11-21 完成历史分支验收（`task/10-c-child4`，`d3d7f135975ac5a2a9b01e2706434d0463a563cd`）；2026-11-26 在六层架构集成基线 `2e65a9463ab88714cfb864b4d63f1547135c29ae` 复验通过，已 fast-forward 收归 `master`（`f2501ddc7d610d554d1e813b13564ea56ce2b51a`）。）

#### 10-c-child2：PlannedHandTarget 字段定义合同（已实现、集成复验通过）

唯一目标：

在PlannedHandTarget末尾增加：

```python
pole_hint_world_xyz: Optional[Tuple[float, float, float]] = None
clamp_reach: bool = True
```

必须保持全部既有字段顺序、默认值和位置参数构造兼容性。

禁止新增函数、模块、状态机或控制器。

（历史时间边界保留：2026-11-20 文档同步任务当时未修改生产代码。当前两项字段已在既有字段末尾实现，并完成集成复验。）

#### 10-c-child3：目标转换

唯一候选函数：

`convert_planned_pose_to_wbc_targets()`

必须保证：

- 左右手Pole Hint分别传递。
- 左右手Clamp Reach分别传递。
- 位置、旋转、权重及enabled语义保持正确。
- FK/IK仲裁不发生左右串扰。
- 合法零权重与接触意图不被错误合并。
- 不修改Root、Pelvis、下肢及其他非上肢目标转换逻辑。

不得新增第二套转换器。

#### 10-c-child4：专项验证及验收

必须覆盖六组：

1. 数据结构及历史构造兼容。
2. 左右手目标字段无损传递。
3. 左右独立性与FK/IK切换。
4. 零权重、无效权重及输入边界。
5. 接触意图与IK独立语义。
6. 手腕位置、姿态及现有可达性反馈合同。

测试方案和允许修改的测试文件必须经过ChatGPT独立审计后冻结。

测试失败不得由Antigravity自行修改生产代码。

当前已验收的 Bridge 实现：PlannedHandTarget 末尾追加 `pole_hint_world_xyz=None` 与 `clamp_reach=True`，保留历史构造兼容；`convert_planned_pose_to_wbc_targets()` 对左右手独立传递字段、仲裁 FK/IK，接触意图独立。`KinematicBridgeExecutor.execute_frame()` 在启用 ROM 截断且 WBC 报告 ROM 违反时，更新场景后调用 `_reconcile_post_rom_feedback()`，从同一最终姿态重算四末端反馈并生成独立结果对象，保留原 ROM 诊断、不将失败变为成功；不修改 WBC/Rig 事务归属。

10-C 专项 A/B/C/D 分别 10/10、15/15、6/6、7/7（合计 38/38 PASS），历史 Bridge 兼容回归 14/14 PASS，累计执行 52/52 PASS；各组退出码为 0。证据：`docs/evidence/10-c-integration/`（`revalidation_manifest.json`、`source_blob_verification.json`、`execution_provenance.json` 及各组原始结果/日志）。

### 10-C跨模块禁止事项

Task 10-C禁止：

- 修改`src/motion/whole_body_controller.py`。
- 修改`src/rig/arm_ik.py`。
- 修改下肢IK和FootLock。
- 开发全身帧级事务。
- 修改ContactModel。
- 开发10-D独立上肢运动轨迹。
- 拆分10-B大型事务代码。
- 创建新控制器或第二条姿态写入管线。

已有下游接口仅允许只读核对。

若验证发现下游问题，必须停止并交回ChatGPT独立审计，不得将其自行加入10-C开发。

负责范围：

- `src/motion/kinematic_bridge.py`（10-C 唯一生产修改文件）
- `src/motion/whole_body_controller.py`（下游接口只读核对，不属于 10-C 生产修改范围）

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

以及 10-C 已向后兼容追加的 WBC / Rig 对应字段：

- `pole_hint_world_xyz`
- `clamp_reach`

WBC 已有对应的 Pole Hint 和 Reach Clamp 能力；Bridge 已分别传递左右手字段。

已收敛的规划数据结构与转换接口继续遵循以下调用链：

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

10-C 已实现 Bridge 返回结果的最终姿态反馈同步并通过 Group D 7/7；这不等于调整原生 IK 与 JointModel 的边界，也不替代 Task 12 全身帧级合同验收。

#### 4.2.5 10-D：独立上肢运动轨迹与中央全身控制收敛 (`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`)

负责模块：

- `src/motion/upper_limb_trajectory.py`（公共无状态上肢轨迹模块：`UpperLimbSegment`、`_evaluate_upper_limb_progress()`、`_validate_upper_limb_vector()`、`_evaluate_upper_limb_segment()`、`validate_upper_limb_segment_sequence()`）
- `src/motion/framework.py`（`MotionPlanner`、`MotionRuntimeContext.compose_planned_pose()`、`StartStopWalkAction`，重复执行前清空 `HandIK`/`ElbowPole` 历史动画曲线）
- `src/motion/terrain_walk.py`（保留 `upper_limb_trajectory` 兼容重导出、`TerrainWalkAction` 消费中央/局部目标）
- `src/motion/run_cycle.py`、`src/motion/sprint_start.py`、`src/motion/sprint_brake.py`（接入 `MotionRuntimeContext.compose_planned_pose()` 中央上肢目标组合）
- `src/motion/kinematic_bridge.py`（Phase 6 保留控制器旋转模式关键帧及 `ArmIK`/`HandRotation` 约束 `influence` `CONSTANT` 插值持久化）

当前已实现架构：

- `MotionPlanner -> MotionRuntimeContext -> MotionAction -> compose_planned_pose() -> KinematicPlannedPose -> KinematicBridgeExecutor.execute_frame() -> WholeBodyController.execute_frame() -> Rig -> MotionState` 为唯一全身控制执行链，禁止第二套控制器或动作调度框架。
- 全部五种生产 `MotionAction`（`StartStopWalkAction`、`TerrainWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）已支持通过 `MotionPlanner` 下发中央 `upper_limb_L/R` 独立 FK/IK 轨迹（须配合显式 `sequence_duration_sec` 与完整性校验），并在未传入独立上肢轨迹时保持历史行为零回归（T02 / T03 `0.0` 差异）。
- 中央全身控制专项验证（`docs/evidence/10-d/10-d-5/centralized_verification/`）：T01–T17 `17/17 PASS`（`rc=0`）；最终分层回归（`docs/evidence/10-d/final_acceptance/`）：`quick` 19/19、`physics` 27/27、`motion` 12/12、`full` 42/42 全部 `rc=0`，受影响 10-C（38/38 + 14/14）、10-d-2（12/12）、10-d-3（18/18 含 T15 68/68）、10-d-4 重复清理均已在当前实现复验通过。
- 2026-11-27 人工视觉验收已批准：`output/task10d_centralized_whole_body.blend`（1026 帧，24 FPS）与 `output/task10d_running_whole_body.blend`（528 帧，24 FPS），其余历史未经人工检查场景不并入本轮已验收登记。

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

`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（2026-11-27；已验收生产基线 `added88a7e27eaaa6d1644473d560c5dcf45bc80`，联合测试证据提交 `07aec5d8d35e5d77ff956f160840d1c2491b770e`）

正式范围：

FootLock — 锁定元数据生命周期、状态查询与支撑维持副作用合同

Task 11 已正式关闭：

- `FIND-R3-03`（Task 11-A）
- `FIND-R3-04`（Task 11-B）

#### 4.3.1 11-A：锁定元数据与生命周期（`COMPLETED / VERIFIED`）

负责文件与 Blob：

- `src/rig/foot_contact.py`（`0b74e83a835362e9ff400106847a6f6c83dd18fc`）
- `src/rig/ik.py`（`f1492c748f8f143041bc6ed4b29d9529824d527f`）

已冻结实现合同：

- 在 `src/rig/ik.py` 定义不可变常量 `FOOT_LOCK_METADATA_KEYS` 统一收敛 `FootIK.<side>` 的 7 项运行时锁定快照键（`contact_world_xyz`、`locked_ankle_world_xyz`、`target_rotation_deg`、`locked_foot_head_xyz`、`locked_foot_tail_xyz`、`locked_foot_center_xyz`、`locked_foot_min_z`）。
- `setup_leg_ik()`、`reset_leg_ik()` 与 `unlock_foot_contact()`（Phase B 事务内）将 `is_locked` 置为 `False` 后统一清理全部 7 项元数据，消除残留脏快照。
- `lock_foot_contact()` 由当次实测世界锁定几何构造全量 7 项载荷并先全部写入，再最后发布 `is_locked = True`。
- `_snapshot_leg_rig_state()` 与 `_rollback_leg_rig_state()` 对 `FootIK.L/R` 执行脱离 Blender `IDPropertyArray` 的 7 键存在性与数值双维度捕获、恢复及回滚后核验（不伪造原本缺失字段，不影响无关自定义属性），完整保持 `09-B-4` Phase B 回滚原子性（TEST-24 未经修改 PASS）。

#### 4.3.2 11-B：状态查询与支撑维持副作用边界（`COMPLETED / VERIFIED`）

负责文件与 Blob：

- `src/rig/ik.py`（`f1492c748f8f143041bc6ed4b29d9529824d527f`）
- `src/rig/foot_contact.py`（`0b74e83a835362e9ff400106847a6f6c83dd18fc`）
- `src/scene/playground_character_assembly.py`（`5bb437d92cbd0d2816fffcae52ae026b35ceb0a4`）

已冻结分离合同：

- 下游读取接口 `get_leg_ik_state(..., *, update_scene: bool = True)` 保留默认兼容刷新，同时提供 `update_scene=False` 无刷新只读通道。
- 纯查询入口 `get_foot_support_state()` 从 `evaluate_foot_support()` 完整迁移状态读取、可达性分类与漂移计算：零对象创建、零 PoseBone/控制器/父级/元数据修改、零隐式 `view_layer.update()` / `frame_set()`；缺失 `FootIK.<side>` 或 `KneePole.<side>` 直接拒绝；`is_locked=True` 严格校验全部 7 项快照完整性与数值格式（拒绝缺失、非有限数、布尔值及非法序列）；`is_locked=False` 沿用解锁测量公式，不消费也不删除残留历史字段。
- 主动维持入口 `evaluate_foot_support()` 在调用 `_ensure_ik_controls()` 之前先只读读取已有 `FootIK` 锁定态，若已锁定则优先调用 `get_foot_support_state()` 完成准入校验（防止缺失 `KneePole` 触发 `setup_leg_ik()` 洗白原有锁定元数据 — 11-B BUG-01），随后执行 `_apply_ik_prebend_hint()`、显式 `view_layer.update()`、锁定 `FootIK`/`KneePole` 世界空间维护与维护后刷新，最后委托 `get_foot_support_state()` 返回统一结构。
- `unlock_foot_contact()` 在 Phase B `try:` 事务体内、最终纯查询前显式执行 `_apply_ik_prebend_hint()` 与 `view_layer.update()`；`WholeBodyController`、`ContactConstraintAdapter`、`move_character_root_with_support()` 及历史步态动作延续使用 `evaluate_foot_support()`；`src/scene/playground_character_assembly.py` Stage D 在 `bridge.execute_frame()` 后切换为 `get_foot_support_state()`。

#### 4.3.3 Task 11 联合验收事实（`docs/evidence/11/unified_verification/`）

- A 组生命周期 `A01–A19`：`19/19 PASS`；B 组查询分离 `B01–B20`：`20/20 PASS`（B08 含 37 项子测试全部通过）；联合专项脚本 `38/38 PASS`。
- 独立进程场景重开：两份新建锁定/解锁场景独立 Blender 进程重开 `PASS`（`verify_footlock_reopen.py`）；历史 `legacy_foot_contact` `PASS`（原 `.blend` SHA-256 保持一致）。
- 连续生产链：五种生产动作（`StartStopWalkAction` 含中央双侧独立上肢轨迹、`TerrainWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）累计 542 帧、支撑状态转换 44 次、锁定控制器最大漂移 `0`。
- 历史专项复验：WBC 历史失败合同 `CONTRACT10-01..06` `6/6`；历史 `09-B-4` `27/27`；地面高度合同 `20/20`；初始化与重置 `6/6`。
- 四级 `--fail-fast` 统一回归：`quick` `19/19`（16 PASSED + 3 AUTOMATED_PASS）、`physics` `27/27`（24 PASSED + 3 AUTOMATED_PASS）、`motion` `12/12`（6 PASSED + 6 AUTOMATED_PASS）、`full` `42/42`（33 PASSED + 9 AUTOMATED_PASS），全部 `rc=0`。`AUTOMATED_PASS` 不登记为人工视觉验收。

### 4.4 节点 12：PKG-5 跨模块联合闭环

状态：

`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（2026-11-27；`Task 12-A/B/C/D` `COMPLETED`，`Task 12-D BUG-01` `CLOSED`；冻结生产基线 `eee276b39d204ccd46f4c17f37a09ec483bfcbae`，冻结测试基线 `90f4628a0c4212f4bb0468941cdde362cd68bef2`，最终验收证据提交 `e15d342b805ef45e7d54db2edf1c2804973e81a7`）

正式范围：

PKG-5 Cross-Module Integration, Failure Atomicity & Joint Acceptance

Task 12 不新增独立运动功能，不重新实现已有模块。

Task 12 的作用是核对各模块组合以后是否仍满足真实的数据流、状态所有权、失败传播和连续动作合同。

#### 4.4.1 12-A：WBC 单帧写入与失败原子性（`COMPLETED / VERIFIED`）

负责文件：

- `src/motion/whole_body_controller.py`（Blob `230a86acaa92b580c5c0aad0e0cdacd7df224a7a`）

已收敛执行合同：

1. Root / Pelvis。
2. Spine / Neck / Head。
3. FK Joint Rotations。
4. Leg IK / FootLock。
5. Arm IK / FK。
6. 场景更新。
7. ROM 校验与可选截断。
8. 截断后（与最终骨架一致的）末端位置/姿态反馈重算与 CoM 计算（`ROM_CONFLICT` 记录真实请求误差）。
9. 失败阶段原子状态捕获与回滚（`_wbc_capture_frame_state()` / `_wbc_restore_frame_state()`）。
10. 结果状态返回（ROM 后最终反馈所有权归 WBC 独占）。

#### 4.4.2 12-B：Bridge 帧提交和失败传播（`COMPLETED / VERIFIED`）

负责文件：

- `src/motion/kinematic_bridge.py`（Blob `4f9cc856b9c9b34c59dd4c6a4f0cee1e1d86ef96`）
- `src/motion/framework.py`

已收敛提交合同：

- `effective_dt` 在转换进 WBC 前完成有限数且严格 `> 1e-9` 准入校验。
- WBC 或 ContactModel 几何检查失败时仍真实构建诊断 `motion_state`/`multi_contact`，但**禁止插入关键帧、禁止提交 7 项跨帧状态**（`_last_time_sec`、`_last_frame`、`last_multi_contact`、`last_active_limb_targets`、`kinematics_tracker._prev_snapshot`/`_prev_velocity`/`_history`）。
- B19 底层关键帧写入故障注入验证 7 项提交状态保持完整，同时保留底层部分 F-Curve 写残余风险记录。

#### 4.4.3 12-C：跨模块状态所有权与接口一致性（`COMPLETED / VERIFIED`）

负责文件：

- `src/motion/kinematic_bridge.py`（Blob `4f9cc856b9c9b34c59dd4c6a4f0cee1e1d86ef96`）
- `src/motion/body_kinematics.py`（Blob `e204793ca3a326a798f75a66e24e98a945e53be7`）
- `src/motion/body_inertia.py`（Blob `0cd7efadf265072fd1665615815792f41b792f1b`）

已收敛所有权合同：

- 删除废弃 `_reconcile_post_rom_feedback()`，Bridge 不再重算或拼接四肢 ROM 后反馈。
- ContactModel 有效支撑判定与 `MotionState.contacts`、BodyKinematics 快照、BodyInertia 时空对齐一致，无双写或历史兜底叠加。

#### 4.4.4 12-D：全系统连续动作与联合回归（`COMPLETED / VERIFIED`，`BUG-01 CLOSED`）

实测验收证据（Blender 5.1.1，`docs/evidence/12/final_acceptance/`）：

- 第一阶段联合专项：WBC A01–A20 `20/20 PASS`；Bridge B01–B19 `19/19 PASS`；C01–C16 及 10-C Retirement `17/17 PASS`；连续生产链（5 动作、`296f` 四种双臂 FK/IK 组合、10 次锁切换、`Reset` 与不等步长重试）`PASS`；B20 场景保存与独立进程重开 `2/2 PASS`。
- 第二阶段历史复验：WBC 失败合同 `6/6`；10-D T01–T15 `15/15`；Task 11 FootLock `38/38`；09-B 世界空间合同 `27/27`；地面高度合同 `20/20`；初始化与重置 `6/6`；历史 Bridge 合同 `14/14`（10-D 复验 JSON 的 `head` 保留旧常量但实际运行于当前仓库，原始报告未篡改）。
- 第三阶段四级 `--fail-fast` 回归（全部 `rc=0`，`FAILED=SKIPPED=NOT_RUN=0`）：Quick `19/19`（16 PASSED + 3 AUTOMATED_PASS）、Physics `27/27`（24 PASSED + 3 AUTOMATED_PASS）、Motion `12/12`（6 PASSED + 6 AUTOMATED_PASS）、Full `42/42`（33 PASSED + 9 AUTOMATED_PASS）。
- 视觉验收与 BUG-01：Task 12 人工视觉验收登记为 **`OWNER WAIVED`**（历史九项视觉待办保持原登记）；`Task 12-D BUG-01` (`tests/verify_task6gc_r3b1_bridge.py` `test_10` 合法姿态输入与零 `dt` 隔离迁移，Blob `eb99144187291e8acd3ad2f3399fc955096c9e45`) 已正式关闭并保全过程证据于 `docs/evidence/12/unified_verification/`。

#### 4.4.5 Task 12 通过与结项结论

九项通过条件中第 1–7 及第 9 项已由真实运行证据闭环满足，第 8 项 Task 12 人工视觉验收已由项目负责人明确豁免登记为 `OWNER WAIVED`。**Task 12 / PKG-5 已正式结项并合并至 `master`。**

### 4.5 PKG-5 子任务编号规则

正式使用：

`节点编号 - 模块字母 - 修复轮次`

例如：

- `10-a-1`
- `10-a-2`
- `10-b-1`
- `10-c-child1`
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

> 项目负责人已明确批准：Task 10-C采用`10-c-childN`作为正式子节点编号。此处child表示子节点序号，不使用原有数字修复轮次含义；其他任务的既有命名规范保持不变。

当前执行节点：

Task 7B-1、Task 7B-2、Task 7B-3：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（已合入 master）；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。

> **Task 12 / PKG-5**（`12-A` / `12-B` / `12-C` / `12-D`，`BUG-01 CLOSED`）已完成全部独立审计、Blender 5.1.1 联合验收与四级 `--fail-fast` 最终回归并收归 `master`（冻结生产基线 `eee276b39d`，冻结测试基线 `90f4628a0c`，最终验收证据 `e15d342b80`，主干合并 `d1645452`，`docs/evidence/12/final_acceptance/`）。**`Task 7B-1`**（`fcb35bd5`）与 **`Task 7B-2`**（`a92280bb`）均已完成独立验收并保留于 Phase 7B 子分支（已合入 `master`）。`Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（20/20 PASS，`d9862ada`）；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。

## 5. 后续 Phase 阶段门禁

### Phase 7A

已有 7A 地形角色与生产场景相关代码和验证资料。

不得将早期项目状态摘要中“尚未实现”的旧记录直接当成当前状态。

对 7A 的具体验收状态只能以对应实际产物与验证证据为准。

### Phase 7B：Upper-Limb Independent Motion & End-Effector Target Verification

状态：Task 7B-1、Task 7B-2、Task 7B-3 均为 `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。

| 节点 | 职责 |
|---|---|
| Task 7B-1 | 真实环境末端目标获取与查询合同验证（`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`，`12/12 PASS`，`BUG-01 CLOSED`） |
| Task 7B-2 | 环境目标至手腕位置及三维姿态的几何转换（`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`，`14/14 PASS`，`BUG-01、BUG-02 CLOSED`，`a92280bb`） |
| Task 7B-3 | 现有独立上肢轨迹与生产控制链集成验证（`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`，20/20 PASS，BUG-01、BUG-02、BUG-03 CLOSED，生产源码零修改，`d9862ada`） |
| Task 7B-4 | 联合专项验收与完整回归（`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`；Blender 5.1.1 联合专项 46/46 PASS（7B-1 12/12、7B-2 14/14、7B-3 20/20），独立相关回归 47/47 PASS；四级回归 quick 19/19、physics 27/27、motion 12/12、full 42/42，最终各组 rc=0、FAILED=SKIPPED=NOT_RUN=0。第一轮 physics 因隔离资产遗漏停止，补齐后通过，原始失败证据保留。源训练场 SHA-256 不变；AUTOMATED_PASS 不等于人工视觉验收。冻结执行基线 `a3720711bfdae1e759485c13f4fc3379be951534`；证据提交 `4a2f4a0743803e1cb747f0927b236dd357694c39`、`1cc2a4b18a309723dc5a0cae2a4e981e2e263f82`，证据目录 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`。） |

> Phase 7B 优先复用已有真实 Mesh 查询、手掌目标几何转换、独立上肢轨迹、中央 MotionPlanner 调度、KinematicBridge、WBC、Arm IK/FK 与 ROM 校验能力。禁止重新实现已有模块。7B-1 已通过 Blender 5.1.1 T01–T12（`12 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`, `rc=0`）；7B-2 已通过 Blender 5.1.1 T01–T14（`14 PASS / 0 FAIL / 0 SKIP / 0 NOT_RUN`, `rc=0`）；7B-3 已完成生产链集成专项。Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。

前置条件核验情况：

1. PKG-5 / 09-B 完成独立核验（09-B-4 已验收）。（已满足）
2. PKG-5 / 10 Upper-Limb IK/FK 完成。（已满足）
3. PKG-5 / 11 FootLock 完成。（已满足）
4. PKG-5 / 12 全仓联合验收通过并合入 `master`。（已满足，`e15d342b80` / `d1645452`）
5. `Task 7B-1` 专项验证通过并获负责人验收（`12/12 PASS`, `fcb35bd5`, `docs/evidence/7b-1/verification/`）。（已满足）
6. `Task 7B-2` 专项验证通过并获负责人验收（`14/14 PASS`, `BUG-01、BUG-02 CLOSED`, `a92280bb`, `docs/evidence/7b-2/verification/`）；项目负责人已基于 `task/7b-2` 开启 `Task 7B-3`（`task/7b-3`，仅限集成验证脚本准备及文档同步，禁止运行测试）。
7. `Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Blender 5.1.1 专项 T01–T20 两轮累计 20/20 PASS；第一轮 T01–T15 PASS、T16 FAIL、T17–T20 NOT_RUN，退出码 1；BUG-03 修复后第二轮 T16–T20 全部 PASS，退出码 0；BUG-01、BUG-02、BUG-03 CLOSED；生产源码零修改。第一轮证据提交 `238383869203aaa39218d2695c2592bd80d44a2e`，`docs/evidence/7b-3/verification/`；第二轮证据提交 `d9862ada5c392080a03efb38ea7f2e90201580d2`，`docs/evidence/7b-3/verification_round2/`。`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。
8. `Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Blender 5.1.1 联合专项 46/46 PASS（7B-1 12/12、7B-2 14/14、7B-3 20/20），独立相关回归 47/47 PASS；四级回归 quick 19/19、physics 27/27、motion 12/12、full 42/42，最终各组 rc=0、FAILED=SKIPPED=NOT_RUN=0。第一轮 physics 因隔离资产遗漏停止，补齐后通过，原始失败证据保留。源训练场 SHA-256 不变；AUTOMATED_PASS 不等于人工视觉验收。冻结执行基线 `a3720711bfdae1e759485c13f4fc3379be951534`；证据提交 `4a2f4a0743803e1cb747f0927b236dd357694c39`、`1cc2a4b18a309723dc5a0cae2a4e981e2e263f82`，证据目录 `docs/evidence/7b-4/final_acceptance/`、`docs/evidence/7b-4/final_acceptance_round2/`。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。

### Phase 7C：Pipeline A / Pipeline B Confluence

状态：`7C-2 OWNER AUTHORIZED`

7C-1：实际人体状态至动力学状态转换；7C-2：有效接触至受力约束转换；7C-3：动力学结果至运动目标转换；7C-4：唯一生产链与统一帧提交合流；7C-5：连续反馈闭环验证及联合回归。

`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。

定位：

- 将生产运动学管线与现有 6-DOF 数值动力学状态合流。
- 复用现有数值动力学模块。
- 不得提前创建第二套 IK、WBC 或动力学求解器。

**7C 是独立架构合流节点，不重开 09-B、10、11。**

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

- PKG-5 / 09-B、Task 10（`10-A/B/C/D`）、Task 11（`11-A/B`）及 **Task 12（`12-A/B/C/D`，`BUG-01 CLOSED`）**均已完成独立验收并合入 `master`（Task 12 冻结生产基线 `eee276b39d`，冻结测试基线 `90f4628a0c`，最终验收证据 `e15d342b80`，`docs/evidence/12/final_acceptance/`）。**PKG-5 已完成并合入主干。**
- 原 16 项历史 Finding `16 CLOSED / 0 OPEN`；21 项冻结记录与 12 项架构合同定义保持不变。
- Task 7B-1、Task 7B-2、Task 7B-3 均为 `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。19 骨骼运动学管线与 6-DOF 数值动力学管线仍然独立，尚未完成 7C 合流。
- Pipeline A 与 Pipeline B 的独立性目前是设计事实，不是故障。
- 7C 才负责未来的系统级动力学合流。
- CoM、BodyKinematics、BodyInertia 不得被描述为已经驱动姿态补偿。
- ContactModel 不得取代 FootLock。
- WBC 不得取代动作规划器或底层 IK/FK。
- 所有历史成熟步态必须保留。

本文件随真实工程演进，但每次修改必须能追溯至实际代码、测试、批准决策或项目负责人明确要求。

## 9. Task 10-B-9：架构驱动事务统一模型（Architecture-First Transaction Consolidation — 历史提取与初版提案记录）

> **历史版本说明（重要）**：
> - 本第 9 节保留自 Task 10-B-9 早期架构提取与初版迁移提案快照（对应 `docs/evidence/PKG5_10B_REVISION_9/01...07.md`）。
> - 本节中的初版提案描述（例如将 `DataBlock` 的 `users == 0` 单独列为物理身份删除条件、3 状态关系日志、以及当时尚未接入事务包装的 `reset_arm_ik` 早期计划）属于**历史提案记录**，**不得覆盖第 10 节已正式批准的目标架构合同**。
> - **已批准目标架构来源**：第 10 节（`## 10. Task 10-B-9 Approved Target Architecture`）保留 Task 10-B 的批准设计约束；“自 `10-B-11` 起”仅为当时实施计划，不能据此认定当前仍处于首轮实施，更不能推定合同已验证。
>
> **归档位置**：`docs/evidence/PKG5_10B_REVISION_9/`
> **架构状态标记**：
> - `[CURRENT]`：当前代码已实际存在并运行
> - `[VERIFIED]`：已通过真实源码与自动化测试逐项核对
> - `[PROPOSED]`：早期架构提案记录（已被第 10 节 `APPROVED TARGET ARCHITECTURE` 收敛取代）
> - `[UNKNOWN]`：缺乏客观证据，严禁虚构

### 9.1 真实架构与六大职责解耦 `[CURRENT / VERIFIED]`

经过对 `src/rig/arm_ik.py`（2414 行）及其调用者（`whole_body_controller.py`、`playground_character_assembly.py`、`run_arm_ik_prototype.py`）只读扫描，当前逻辑划分为六大职责：

1. **Transaction Coordinator（事务协调器）** `[CURRENT / VERIFIED]`：
   - 核心入口：`_arm_rig_transaction` (L1605-L1705)、`_assert_arm_rig_cleanup_gate` (L1571-L1603)、`_ACTIVE_TRANSACTION_STACK` (L1510)。
   - 职责：驱动 9 状态生命周期、维护单一 Armature 事务独占性、提供重入复用与跨 Armature 隔离。
2. **State & Ownership Registry（状态与所有权注册表）** `[CURRENT / VERIFIED]`：
   - 核心结构：`_ArmRigTransactionContext` (L1259-L1509)、`_ArmRigTransactionState` 枚举、`_PENDING_ARM_RIG_CLEANUPS` 全局字典。
   - 职责：严格记录本事务自建资源、暂存资源指针与待清理队列。
3. **Resource Operations（底层资源操作引擎）** `[CURRENT / VERIFIED]`：
   - 核心函数：`_get_or_create_empty` (L1707-L1772)、`_ensure_character_collection` (L137-L147)、`_find_live_object_by_identity` (L411-L438)。
   - 职责：执行 Blender C 实体创建、指针比对、集合成员链接/解绑、约束绑定与安全删除。
4. **Arm IK Business Operations（领域业务操作）** `[CURRENT / VERIFIED]`：
   - 核心 API：`setup_arm_ik`、`set_hand_ik_target`、`set_arm_ik_influence`、`reset_arm_ik`、`get_arm_ik_state`。
   - 职责：Phase A 严格参数校验、Phase B 零副作用父级共形预检、Phase C/D 空间目标求解与姿态赋值。
5. **Snapshot & Verification（快照捕获与全字段核验）** `[CURRENT / VERIFIED]`：
   - 核心函数：`_snapshot_arm_rig_state` (L244-L409)、`_verify_arm_rig_state_restored` (L858-L1257)。
   - 职责：不可变深拷贝（Collections, Controllers, PoseBones, Constraints）；回滚后 $10^{-5}$ 容差全字段与物理指针身份比对。
6. **Commit & Cleanup（提交确认与不可逆资源清理）** `[CURRENT / VERIFIED]`：
   - 核心函数：`tx.retry_cleanup()` (L1316-L1509)、`retry_pending_arm_rig_cleanup` (L1543-L1570)。
   - 职责：Phase 2 达成 `COMMITTED` 后启动 Phase 3 不可逆垃圾回收；失败转入 `CLEANUP_PENDING` 并登记注册表，杜绝重入死锁。

### 9.2 资源物理身份与 5 类所有权分类合同 `[CURRENT / VERIFIED]`

- **非推断铁律 (Non-Inference Principle)**：禁止以名称、快照差集或孤立指针整数推断所有权。
- **物理身份判定**：
  - `Object`：`(obj_ref, obj_ptr == obj_ref.as_pointer(), obj_ref in bpy.data.objects)`
  - `Constraint`：`(con_ref, con_ptr == con_ref.as_pointer(), con_ref in pbone.constraints)`
  - `Collection`：`(col_ref, col_ptr == col_ref.as_pointer(), col_ref.name in bpy.data.collections)`
  - `DataBlock`：`(data_ref, data_ptr == data_ref.as_pointer(), users == 0)`
- **5 类所有权分类**：
  1. **原始已存在资源 (Pre-existing)**：快照完整记录，受回滚引擎保护，严禁物理删除；
  2. **本事务自建资源 (Created)**：先登记所有权后链接集合，回滚负有 100% 指针级删除责任；
  3. **本事务暂存资源 (Stashed)**：隔离脱绑与重命名，回滚时恢复原状，提交后由 Phase 3 物理删除；
  4. **外部登记资源 (External)**：持有只读引用，严禁更改生命周期或删除；
  5. **所有权不可证明资源 (Unprovable)**：命名冲突但不匹配任何历史指针，一律报错保护现场，严禁擅自覆盖。

### 9.3 事务 9 状态生命周期模型 `[CURRENT / VERIFIED]`

- **状态集合**：`CREATED` $\to$ `SNAPSHOTTING` $\to$ `ACTIVE` $\to$ `COMMITTING` $\to$ `COMMITTED` $\to$ `CLEANUP_PENDING` / `ROLLING_BACK` $\to$ `ROLLED_BACK` / `FAILED`。
- **不可逆提交红线**：跨越 Phase 2 达成 `COMMITTED` 之后，严禁执行普通回滚；任何后续异常统一转入 `CLEANUP_PENDING` 并锁入 `_PENDING_ARM_RIG_CLEANUPS`。
- **准入门禁**：同 Armature 存在未清理事务时，`_assert_arm_rig_cleanup_gate` 阻断新事务开启。

### 9.4 架构迁移方案与演进建议 `[PROPOSED — HISTORICAL SNAPSHOT]`

- **建议 1（reset_arm_ik 事务化）** `[PROPOSED — 历史记录说明]`：早期提案建议将 `reset_arm_ik` 纳入 `with _arm_rig_transaction(arm):` 保护。**2026-11-19 源码核实**：事务上下文包装及前置检查已存在；该建议不得再被当作未开始的编码任务。第 10.9 节是批准合同，其余细节是否通过仍以当前实际专项结果为准。
- **建议 2（单文件分节重整首选）** `[PROPOSED]`：保持单一 `src/rig/arm_ik.py`，但在内部划分为 6 个显式职责 Section，避免多文件拆分引入循环依赖或打断 Git 追溯历史。
- **建议 3（清理非事务历史死代码）** `[PROPOSED]`：安全移除 `_get_or_create_empty` 和 `setup_arm_ik` 中 `else: bpy.data.objects.remove` 等已不可达分支。
- **建议 4（资源记录结构归一化）** `[PROPOSED]`：将分散的 `created_controller_objects`、`created_collections` 统一映射为 `created_resources`，保留原有属性作为 `@property` 兼容层。


---

## 10. Task 10-B-9 Approved Target Architecture

```text
APPROVED TARGET ARCHITECTURE (DESIGN CONTRACT PRESERVED)
ARCHITECTURE: APPROVED TARGET
DESIGN-APPROVAL-TIME STATUS: HISTORICAL IMPLEMENTATION PLAN
AS-OF-2026-11-26 IMPLEMENTATION: SIX-LAYER SPLIT & FULL REGRESSION COMPLETE (2f248bf / dcf3057)
AS-OF-2026-11-26 ACCEPTANCE: COMPLETED — OWNER ACCEPTED (2026-11-20) — MERGED TO MASTER (c45a40c)
WBC CONTRACT10-01..06: SEPARATELY TRACKED (NOT A 10-B CLOSURE GATE / TASK 12 UNCLAIMED)
```

### 10.1 架构地位及版本 (Planned Target Architecture)

- **批准架构基准 Git SHA**：`124747e900a1db5790ed5f4159f561dba19890ff`
- **批准目标架构源文件**：`docs/evidence/PKG5_10B_REVISION_9/architecture_draft_candidate.json`
- **架构设计范围**：`src/rig/arm_ik.py` 上肢 IK 领域入口与 `src/scene_transaction_integrity/` 六层事务完整性实现（协调、状态与所有权注册表、受权资源与关系操作、业务数值写入、快照恢复与全字段核验、提交后清理、双臂原子复位及与上层 `WholeBodyController` 的接口边界）。
- **状态严格分离声明**：
  - `ARCHITECTURE: APPROVED TARGET`（目标架构设计已通过静态架构审计并获得正式批准）。
  - **历史实施状态**：设计批准时处于分阶段落地，`10-B-11` 曾是下一步计划。**2026-11-26 当前状态**：已完成六层物理拆分、同一冻结源码基线（`2f248bf4b98776222e37bc3228506a4fb85f7c32`）全量回归并合并至 `master`（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`）；不得继续把历史实施计划标记为当前节点，亦不得将测试通过外推为所有跨层运行时路径均经过穷尽证明。
  - **当前验收状态**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（2026-11-20 原项目负责人正式验收，2026-11-26 完成拆分回归 `2f248bf` / `dcf3057` 及主干合并 `c45a40c`；FULL 42/42 自动化通过含 33 PASSED + 9 AUTOMATED_PASS，9 项人工视觉验收仍作为独立待办；WBC 独立合同不属于 10-B 结项门槛，不扩大其职责或宣称 Task 12 完成）。
- **与 `ARCHITECTURE.md` 及历史材料的优先级关系（Source Precedence）**：
  1. **Level 1 — 权威总架构与门禁约束**：`ARCHITECTURE.md`、`docs/ARCHITECTURE_CHANGE_GATE.md`（定义全系统主执行链 `MotionPlanner -> Bridge -> WBC -> Rig/IK/FK` 与十步防漂移清规，本节严格服从总架构，不改变上层管线拓扑）。
  2. **Level 2 — 当前代码与已核实实现事实**：`ARCHITECTURE_SYNC.md` 第 1～8 节、`src/rig/arm_ik.py`（5 个公开领域入口及领域配置常量）、`src/scene_transaction_integrity/`（六层物理架构实现与 `wiring.py`、`fault_injection.py`）、`src/motion/whole_body_controller.py`（代表当前磁盘已实现事实）。
  3. **Level 3 — 已批准目标事务架构合同**：本第 10 节及 `docs/evidence/PKG5_10B_REVISION_9/architecture_draft_candidate.json`（Commit `124747e900a1db5790ed5f4159f561dba19890ff`，作为 Task 10-B 后续生产修复的唯一批准目标架构来源）。
  4. **Level 4 — 历史提案文档（非权威）**：`docs/evidence/PKG5_10B_REVISION_9/01...07.md` 及本文第 9 节早期提案记录。凡历史提案与本第 10 节冲突之处（如 `02` 中的反向箭头、`03` 中的快照差集解绑与 `users == 0` 自动级联删除、`04` 中的 3 状态关系日志、`05` 中的反向影响边），一律以本第 10 节为准。

---

### 10.2 六层职责 (Planned Target Architecture)

目标架构将 `src/rig/arm_ik.py` 内部事务与业务职责严格划分为六个正交层级。**Layer 1 Transaction Coordinator 是事务生命周期与门禁状态的唯一决策者**。

| 层级 | 名称 | 核心职责与归属函数 | 输入 (Input) | 输出 (Output) | 状态所有者 (State Owner) | 允许的调用方向 (Allowed Calls) | 禁止的调用方向 (Forbidden Calls) | 允许的状态修改 (Allowed Writes) | 禁止的状态修改 (Forbidden Writes) | 异常传播 (Exception Propagation) | 恢复责任 (Recovery Responsibility) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Layer 1** | **Transaction Coordinator** | 事务生命周期唯一决策者；管理重入、准入门禁、回滚调度、提交后清理分发与解除隔离审批（`_arm_rig_transaction`, `_assert_arm_rig_cleanup_gate`, `_dispatch_retry_cleanup`, `request_armature_deisolation`, `retire_dead_armature_tombstone`） | `arm: bpy.types.Object`、恢复/重试请求 | 产出事务上下文；返回重试或解除隔离结果 | `_ACTIVE_TRANSACTION_STACK` 控制权；9 状态事务状态机与门禁注册/注销的**唯一决策权** | 调用 Layer 2（查询门禁、授权状态与门禁写入）、Layer 5（快照、回滚、核验）、Layer 6（提交后清理） | 禁止直接调用 Layer 3 绕过抽象做 CRUD；禁止反向调用 Layer 4 | 授权 Layer 2 更新 9 状态生命周期、推入/弹出事务栈、提交边界调用 `depsgraph.update()`、设置 `rollback_only`、根据 Layer 6 返回结果授权 Layer 2 注册/注销 `CLEANUP_PENDING`、根据 Layer 5 核验报告授权 Layer 2 记录/解除 `FAILED` 隔离或归档墓碑 | 禁止直接写骨骼变换、控制器变换、约束权重或直接创建/删除场景实体与 DataBlock | 拦截业务异常，触发 Layer 5 回滚，将失败分类为 `FAILED-A/B/C/D`，评估 Layer 6 清理结果，回滚核验失败时抛出复合异常 | 协调 Layer 5 执行回滚与核验，唯一决定转入 `ROLLED_BACK` 或 `FAILED` |
| **Layer 2** | **State & Ownership Registry** | 被动状态与所有权注册表（`_ArmRigTransactionContext`, `ensure_armature_session_identity`, `register_created_*`, `register_datablock_cleanup_authority`, `prepare_relationship_mutation`, `update_relationship_mutation_state`, `query_admission_gate_status`, `_record_pending_arm_rig_cleanup`, `_clear_pending_arm_rig_cleanup_by_coordinator`, `_record_armature_failure_isolation_by_coordinator`, `_clear_or_retire_failure_isolation_by_coordinator`） | 实体引用/指针、DataBlock 授权记录、关系日志状态转换、Coordinator 状态/门禁指令 | 所有权记录、会话身份记录、门禁查询结果、审计日志记录 | 事务内存集合（`created_*`, `stashed_*`, `datablock_authorizations`, `prepared_relationship_mutations`）及全局字典（`_MANAGED_ARMATURE_IDENTITIES`, `_PENDING_ARM_RIG_CLEANUPS`, `_ISOLATED_FAILED_ARMATURES`, `_DEISOLATION_AUDIT_LOG`） | 仅允许调用 Python 标准库、`uuid.uuid4()`、只读 `as_pointer()` | **严禁调用任何其他层（Layer 1 / 3 / 4 / 5 / 6）** | 写入内部内存记录集合、单条目清理进度标志（`obj_cleaned`, `data_cleaned`, `preserved_no_authority`）、7 状态关系操作日志；**仅在 Layer 1 Coordinator 明确授权下**更新事务生命周期状态与门禁索引 | 禁止写任何 Blender 场景数据或自定义属性；禁止自主决定事务生命周期状态；禁止未经 Coordinator 授权自行清除 `CLEANUP_PENDING` 或 `FAILED` 隔离 | 重复注册、非法关系日志状态转换或未授权状态修改时抛出 `RuntimeError` | 纯被动状态容器，提供所有权证据、关系日志与会话身份记录 |
| **Layer 3** | **Authorized Resource Operations** | 受权资源与关系操作执行引擎（`_get_or_create_empty`, `_ensure_character_collection`, `_authorized_link_object_to_collection`, `_authorized_unlink_object_from_collection`, `_authorized_link_child_collection`, `_authorized_unlink_child_collection`, `_authorized_assign_object_parent`, `_authorized_assign_constraint_targets`, `_authorized_restore_relationship`, `_authorized_create_constraint`, `_authorized_remove_constraint`, `_authorized_remove_object`, `_authorized_remove_datablock_if_permitted`） | 来自 Layer 4 / Layer 5 / Layer 6 的明确受权参数与所有权记录 | Blender 实体包装对象或删除/保留/恢复状态 | 无（无状态执行引擎） | 调用 Layer 2（登记实体/DataBlock 授权、更新 7 状态关系日志）及 Blender C-API 接口 | 禁止调用 Layer 1、Layer 4、Layer 5、Layer 6 | 受权创建/删除 Object、Constraint、Collection 及满足 `CanDelete(D,t)` 的 DataBlock；受权执行全部正向与回滚关系引用修改（`col.objects.link/unlink`, `col.children.link/unlink`, `obj.parent`, 绑定耦合的 `matrix_parent_inverse`, `con.target`, `con.pole_target`）并同步更新 Layer 2 的 7 状态关系日志 | 禁止在向 Layer 2 登记前暴露新建实体；禁止无 7 状态关系日志追踪直接修改或恢复关系引用；禁止未验证所有权/授权即删除实体或 DataBlock；禁止调用 `bpy.data.orphans_purge()`；禁止自主决定提交、回滚或门禁 | 捕获 `ReferenceError` 并包装为描述性 `RuntimeError`；Apply 失败时将关系日志更新为 `NO_EFFECT` 或 `RECOVERY_UNCERTAIN` 并向上传递异常 | 被 Layer 5 调用时执行单步受权删除、解绑或关系恢复，并将关系日志更新为 `REVERTED` 或 `RECOVERY_UNCERTAIN` |
| **Layer 4** | **Arm IK Business Operations** | 上肢 IK 领域业务与数值计算（`setup_arm_ik`, `set_hand_ik_target`, `set_arm_ik_influence`, `reset_arm_ik`, `get_arm_ik_state`, `_preflight_arm_ik_parent_transforms`） | 目标坐标、侧别、旋转、权重、可达性截断标志、Armature 对象 | IK 求解字典、控制器字典、可达性状态 | Python 内存无状态；业务状态体现在场景骨骼与控制器数值属性 | 调用 Layer 1（进入事务上下文）、Layer 3（受权资源与关系操作）、同层预检与嵌套函数、`transform_utils` | 禁止直接调用 Layer 5（不得私自触发快照/回滚）或 Layer 6（不得私自触发提交后清理） | **仅在 `ACTIVE` 状态下**：直接写入 PoseBone 数值变换（`location`, `rotation_euler`, `rotation_quaternion`, `scale`）、控制器数值 TRS、以及 Constraint **纯数值参数**（`influence`, `pole_angle`, `chain_count`, `use_stretch`） | 禁止在预检阶段发生任何场景写入（零写入保证）；禁止在 Layer 1 事务外执行未保护写入；**严禁绕过 Layer 3 直接写入任何关系引用**（`con.target`, `con.pole_target`, `obj.parent`, `matrix_parent_inverse` 父级绑定, `col.objects.link/unlink`, `col.children.link/unlink`）；禁止绕过 Layer 3 直接创建或删除资源 | 预检拒绝时抛出 `TypeError`/`ValueError`；内部异常向调用方传播；嵌套事务失败时调用 `outer_tx.mark_rollback_only(reason)` | 无直接回滚逻辑，完全依赖 Layer 1 事务包装 |
| **Layer 5** | **Snapshot / Restore / Verification** | 快照捕获、回滚恢复与全字段/解除隔离证据核验（`_snapshot_arm_rig_state`, `_clone_snapshot_property_value`, `_rollback_arm_rig_state`, `_verify_arm_rig_state_restored`, `verify_armature_deisolation_evidence`） | Armature 对象、快照字典、活动事务上下文、解除隔离核验请求 | 不可变快照字典、回滚核验结果、解除隔离证据核验报告 | 不可变快照字典结构 | 调用 Layer 2（只读查询所有权与关系日志）、Layer 3（回滚期间受权删除新建实体与恢复关系引用）及 Blender 只读属性检查 | 禁止调用 Layer 1（不反向调用 Coordinator，仅通过栈返回值传递结果）、Layer 4、Layer 6 | **仅在 `ROLLING_BACK` 状态下**：直接恢复数值与变换属性（PoseBone 变换、控制器 TRS、Constraint 数值属性 `influence`/`pole_angle`）；通过调用 Layer 3 恢复或撤销已验证的关系引用（使关系日志转入 `REVERTED`）并删除事务新建实体 | 禁止在快照捕获或核验阶段发生任何场景写入；**严禁在 `ROLLING_BACK` 期间绕过 Layer 3 直接写关系引用**（`Object.parent`, `Constraint.target`/`pole_target`, `Collection` link/unlink）；禁止删除非本事务资源或无授权 DataBlock；禁止直接修改事务生命周期状态 | 快照读取失败、关系日志处于 `RECOVERY_UNCERTAIN` 或核验偏差 $> 10^{-5}$ 时抛出 `RuntimeError` 或返回结构化失败报告 | 执行回滚恢复（数值直接恢复，关系与删除经由 Layer 3）并核验 100% 基准匹配，向 Layer 1 报告结果 |
| **Layer 6** | **Commit & Cleanup** | 提交后受权清理执行器（`retry_cleanup`, `execute_stashed_cleanup_pass`） | 已提交事务清理上下文、暂存资源队列、DataBlock 授权记录 | 清理结果枚举 `CleanupOutcome`（`CLEANUP_SUCCESS`, `CLEANUP_INCOMPLETE`, `CLEANUP_FAILED`），作为 `RESULT` 返回给 Layer 1 | 单条目清理进度标志（`obj_cleaned`, `data_cleaned`, `preserved_no_authority`） | 调用 Layer 2（读取暂存队列与 DataBlock 授权，仅更新单条目进度标志）、Layer 3（受权删除废弃实体与满足 `CanDelete(D,t)` 的零引用 DataBlock） | **严禁调用 Layer 1**、Layer 4、Layer 5 | 调用 Layer 3 删除受权废弃 Object、Constraint 及满足 `CanDelete(D,t)` 的 DataBlock；在 Layer 2 记录单条目进度（`obj_cleaned`, `data_cleaned`, `PRESERVED_NO_DELETE_AUTHORITY`） | 禁止删除无明确删除授权的 DataBlock（无授权 Type B、Type C）或 `Users(D) > 0` / 存在保护依赖的 DataBlock；禁止删除活动控制器；**禁止直接修改事务生命周期状态或自行在 Layer 2 注销 `CLEANUP_PENDING` 门禁**；禁止触发场景回滚 | 捕获清理异常，保留已清理条目进度，记录失败原因，并向 Layer 1 返回 `CLEANUP_INCOMPLETE` 或 `CLEANUP_FAILED` | 无回滚职责；严格在 Layer 1 监督下执行提交后垃圾回收 |

---

### 10.3 统一依赖图 (Planned Target Architecture)

#### 10.3.1 依赖边分类定义（5 类 `edge_type`）

1. **`CALL`**：高层模块向低层模块发起的函数调用依赖，参与调用有向无环图（DAG）拓扑排序。
2. **`RESULT`**：被调用函数沿 Python 调用栈向调用者返回的操作结果数据流（如 `CleanupOutcome`、`VerificationResult`、`GateResult`），**不属于反向调用依赖，不参与 CALL DAG 环路判定**。
3. **`STATE_READ`**：对 Layer 2 被动注册表数据结构的只读查询。
4. **`STATE_WRITE`**：对 Layer 2 注册表记录、生命周期状态或门禁索引的受权写入（其中事务生命周期状态、门禁注册/注销与 `FAILED` 隔离写入权由 Layer 1 Coordinator 独占）。
5. **`PROTECTION`**：主动执行保护检查的事务层（Source：Layer 5 / Layer 6 / Layer 3）对被保护外部场景资源或未授权 DataBlock（Target）实施的只读所有权边界保护。

#### 10.3.2 完整 18 项规范依赖记录（Canonical Dependency Edges）

| Edge ID | Source | Target | `edge_type` | 操作与契约语义 | 参与 CALL DAG |
|---|---|---|---|---|---|
| `DAG-01` | `Upper Pipeline: WBC` | `Layer 4` | `CALL` | 调用 `setup_arm_ik` / `set_hand_ik_target` / `set_arm_ik_influence` / `reset_arm_ik` | `true` |
| `DAG-02` | `Layer 4` | `Layer 4` | `CALL` | 层内调用 `_preflight_arm_ik_parent_transforms` 及嵌套 `setup_arm_ik` / `reset_arm_ik` | `false` |
| `DAG-03` | `Layer 4` | `Layer 1` | `CALL` | 请求进入 `_arm_rig_transaction` 事务上下文 | `true` |
| `DAG-04` | `Layer 4` | `Layer 3` | `CALL` | 调用受权实体创建与关系引用修改接口 | `true` |
| `DAG-05` | `Layer 1` | `Layer 2` | `STATE_READ` | 通过 `_assert_arm_rig_cleanup_gate` 调用 `query_admission_gate_status` 查询准入门禁与会话身份记录 | `true` |
| `DAG-06` | `Layer 1` | `Layer 2` | `STATE_WRITE` | 唯一决策并授权写入 9 状态生命周期、注册/注销 `CLEANUP_PENDING` 门禁、记录/解除 `FAILED-A/B/C/D` 隔离 | `true` |
| `DAG-07` | `Layer 1` | `Layer 5` | `CALL` | 调用 `_snapshot_arm_rig_state`、`_rollback_arm_rig_state`、`_verify_arm_rig_state_restored`、`verify_armature_deisolation_evidence` | `true` |
| `DAG-08` | `Layer 1` | `Layer 6` | `CALL` | 分发提交后清理或重试清理（`retry_cleanup`） | `true` |
| `DAG-09` | `Layer 5` | `Layer 2` | `STATE_READ` | 查询已登记所有权集合与 7 状态关系操作日志 | `true` |
| `DAG-10` | `Layer 5` | `Layer 3` | `CALL` | 在 `ROLLING_BACK` 期间调用受权实体删除与关系引用恢复接口 | `true` |
| `DAG-11` | `Layer 6` | `Layer 2` | `STATE_READ` | 读取暂存清理队列与 DataBlock 清理授权记录 | `true` |
| `DAG-12` | `Layer 6` | `Layer 2` | `STATE_WRITE` | 仅更新单条目清理进度标志（`obj_cleaned`, `data_cleaned`, `PRESERVED_NO_DELETE_AUTHORITY`） | `true` |
| `DAG-13` | `Layer 6` | `Layer 3` | `CALL` | 调用 `_authorized_remove_object`、`_authorized_remove_constraint`、`_authorized_remove_datablock_if_permitted` | `true` |
| `DAG-14` | `Layer 3` | `Layer 2` | `STATE_WRITE` | 登记新建实体、Type A DataBlock 授权及 7 状态关系操作日志状态转换 | `true` |
| `DAG-15` | `Layer 2` | `Layer 1` | `RESULT` | 沿调用栈向 Coordinator 返回 `GateResult` | `false` |
| `DAG-16` | `Layer 5` | `Layer 1` | `RESULT` | 沿调用栈向 Coordinator 返回快照、回滚核验结果与解除隔离核验报告 | `false` |
| `DAG-17` | `Layer 6` | `Layer 1` | `RESULT` | 沿调用栈向 Coordinator 返回 `CleanupOutcome`（`CLEANUP_SUCCESS` / `CLEANUP_INCOMPLETE` / `CLEANUP_FAILED`） | `false` |
| `DAG-18` | `Layer 5 / Layer 6 / Layer 3` | `External Scene Resources & Unproven DataBlocks` | `PROTECTION` | 执行非推断铁律与 `CanDelete(D,t)` 保护边界，拒绝未授权删除或解绑 | `false` |

> **无环证明（Cycle Elimination Proof）**：所有跨层 `CALL` 边构成严格有向无环图（DAG），拓扑序为：`WBC -> Layer 4 -> Layer 1 -> Layer 5 -> Layer 6 -> Layer 3 -> Layer 2`。Layer 2 无任何外向调用；Layer 5 与 Layer 6 仅通过栈返回值（`RESULT`）向 Layer 1 汇报结果，绝不反向调用 Layer 1。

---

### 10.4 资源所有权 (Planned Target Architecture)

#### 10.4.1 核心定理与绝对禁令

1. **资源删除所有权定理**：
   $$Delete(r) \Rightarrow OwnershipVerified(r,t) \land IdentityVerified(r)$$
2. **DataBlock 物理删除充要谓词**：
   $$CanDelete(D,t) \iff AuthorizedCleanup(D,t) \land IdentityVerified(D) \land Users(D)=0 \land NoProtectedDependency(D)$$
3. **五项绝对非推断禁令（Prohibitions）**：
   - **禁止名称推断**：`name(r) == expected_name` 绝不蕴涵 `Owned(r, t)`。
   - **禁止快照差集推断**：`r not in Snapshot` 绝不蕴涵 `Owned(r, t)`。
   - **禁止孤立指针推断**：`as_pointer(r) == saved_ptr` 必须结合活跃 Python 引用（无 `ReferenceError`）、原始引用相等性及 Blender 数据集合包含性共同核验。
   - **禁止零引用推断删除权**：`Users(D) == 0` 仅表示当前无活跃引用，绝不蕴涵事务对 DataBlock $D$ 拥有删除授权 `AuthorizedCleanup(D, t)`。
   - **禁止 Object 到 DataBlock 权限自动继承**：对 `Object` 的所有权或废弃删除权，绝不自动传递或授予对其绑定 `obj.data`（DataBlock）的物理删除权。

#### 10.4.2 四类资源实体所有权模型

| 资源类型 | 所有权判定标准 | 修改权限 | 删除权限 | 失效/死亡检测 |
|---|---|---|---|---|
| **Object** | 仅限创建时登记于 `active_tx.created_controller_objects` 或具有已证实历史 Rig 所有权并登记于 `active_tx.stashed_objects` 的对象 | `ACTIVE` 下由 Layer 4 修改数值 TRS；`ROLLING_BACK` 下由 Layer 5 恢复数值 TRS；父级与集合关系仅限通过 Layer 3 配合 Layer 2 7 状态日志修改/恢复 | 回滚仅允许经由 Layer 3 删除已登记且身份核验通过的 `created_controller_objects`；提交后清理仅允许经由 Layer 3 删除受权的 `stashed_objects` | 访问触发 `ReferenceError`、指针不一致或不在 `bpy.data.objects` 中 |
| **Constraint** | 仅限创建时登记于 `active_tx.created_constraints` 或登记于 `active_tx.stashed_constraints` 的约束 | `ACTIVE` 下由 Layer 4 修改数值参数（`influence`, `pole_angle` 等）；`ROLLING_BACK` 下由 Layer 5 恢复数值参数；`target`/`pole_target` 引用仅限经由 Layer 3 配合 7 状态日志修改/恢复 | 回滚仅允许经由 Layer 3 删除匹配所属骨骼、引用与指针的 `created_constraints`；提交后清理仅允许删除受权 `stashed_constraints` | 访问触发 `ReferenceError`、指针不一致或不在 `pose_bone.constraints` 中 |
| **Collection** | 仅限当前事务新建并登记于 `active_tx.created_collections` 的集合 | 集合成员（`objects.link/unlink`）与子集合层级（`children.link/unlink`）仅限在 `ACTIVE` 或 `ROLLING_BACK` 下经由 Layer 3 配合 Layer 2 7 状态日志修改/恢复 | 回滚仅允许经由 Layer 3 删除已登记且不包含任何外部对象与外部子集合的 `created_collections` | 访问触发 `ReferenceError`、指针不匹配或不在 `bpy.data.collections` 中 |
| **DataBlock** | 严格区分三类来源：<br>1. `TYPE_A_TX_CREATED`（本事务直接分配并登记）<br>2. `TYPE_B_PRE_EXISTING`（事务前已存在，含绑定于被删 Object 的 DataBlock）<br>3. `TYPE_C_EXTERNAL_OR_UNPROVEN`（外部创建或来源不可证明） | 事务不直接篡改外部或未授权 DataBlock 内部结构 | 仅当满足 `CanDelete(D, t)` 时由 Layer 3 物理删除：<br>- `TYPE_A`：满足身份核验、`Users(D)==0` 且无保护依赖时允许删除；<br>- `TYPE_B`：除非存在独立、显式、经证实的 `TYPE_B_PRE_EXISTING_EXPLICIT_GRANT` 删除授权记录，否则**严禁删除**，必须保留并标记为 `PRESERVED_NO_DELETE_AUTHORITY`（合法终态，不触发 `CLEANUP_PENDING`）；<br>- `TYPE_C`：**任何情况下严禁删除**（即使 `Users(D)==0`） | 访问触发 `ReferenceError`、指针与 `original_pointer` 不匹配或不在对应 `bpy.data` 集合中 |

- **DataBlock 清理授权记录 8 字段模式**：`resource_kind`、`original_reference`、`original_pointer`、`provenance`（`TYPE_A_TX_CREATED` / `TYPE_B_PRE_EXISTING_EXPLICIT_GRANT` / `TYPE_C_EXTERNAL_OR_UNPROVEN`）、`authorization_source`、`authorization_scope`（`PHYSICAL_DELETE_IF_ZERO_USERS` / `DETACH_ONLY_PRESERVE_DATABLOCK`）、`authorized_transaction`、`expected_lifecycle`。
- **外部关系冲突与未知所有权保护（`OWNERSHIP_UNPROVEN`）**：若事务新建实体在事务期间被外部系统引用且无法安全解绑，或遇到来源无法证明的实体/关系，回滚必须立即停止破坏性删除，标记 `OWNERSHIP_CONFLICT` / `RECOVERY_UNCERTAIN`，保留现场并向 Layer 1 报告失败。

---

### 10.5 关系变更合同 (Planned Target Architecture)

#### 10.5.1 五类关系分类与回滚规则

1. **`PRE_EXISTING_ORIGINAL`**：事务进入前已存在的关系（如角色集合已链接至场景主集合、骨骼原有约束、控制器原有集合链接）。严格受保护；若事务执行重复链接，直接转入 `NO_EFFECT`，**绝不获得撤销或解绑权限**。
2. **`TX_ADDED`**：本事务新建立的关系。回滚时仅在满足受权 `PREPARED` 记录、有效身份、因果证据与零外部伤害条件下，经由 Layer 3 撤销并转入 `REVERTED`。
3. **`TX_UNLINKED_ORIGINAL`**：本事务显式解绑的原有关系。回滚时必须经由 Layer 3 恢复原链接与相对顺序，并转入 `REVERTED`。
4. **`EXTERNAL_ADDED`**：外部脚本或用户在事务期间新增的关系。严格免于回滚删除。
5. **`OWNERSHIP_UNKNOWN`**：来源或因果历史无法证明的关系。视为 `OWNERSHIP_UNPROVEN`，禁止解绑/删除，关系日志转入 `RECOVERY_UNCERTAIN` 并使回滚核验失败。

#### 10.5.2 七状态关系操作日志（7-State Relationship Operation Log）

关系操作日志状态机保存在 `active_tx.prepared_relationship_mutations` 中，与 9 状态事务生命周期状态机严格分离，严禁混同或新增第 8 个关系日志状态：

| 日志状态 | 精确定义 |
|---|---|
| `PREPARED` | 调用任何 Blender C-API 关系修改前，已完成授权与身份核验并在事务内存中建立意图记录。 |
| `APPLYING` | 已发起受权 Blender C-API 关系操作，正在执行中（可能成功、部分生效或抛出异常）。 |
| `APPLIED_VERIFIED` | 调用后经实时 RNA 检查确认目标关系修改已在 Blender 中物理生效，等待业务步骤确认。 |
| `CONFIRMED` | 关系操作在当前活动业务步骤内确认完成。事务提交时作为合法完成态；若外层事务回滚，仍必须经由 Layer 3 撤销并转入 `REVERTED`（或失败转入 `RECOVERY_UNCERTAIN`）。 |
| `NO_EFFECT` | 终态：证明未产生任何需要撤销的 Blender 关系修改（如在 `PREPARED` 阶段发现关系属于 `PRE_EXISTING_ORIGINAL` 无需修改、在 `APPLYING` 前中止、或 `APPLYING` 抛错且实时 RNA 检查证明零副作用）。 |
| `REVERTED` | 回滚终态：证明本事务产生的关系修改已由 Layer 3 合法撤销/恢复，且撤销后核验确认已恢复原关系状态。 |
| `RECOVERY_UNCERTAIN` | 错误终态：关系来源、实际物理副作用或安全撤销前提无法证明；严禁盲目解绑/删除，保留现场并触发回滚核验失败。 |

#### 10.5.3 十条合法状态转换与异常恢复协议

$$Undo(m) \Rightarrow Authorized(m,t) \land Prepared(m,t) \land IdentityVerified(m) \land CausalEvidence(m) \land NoExternalHarm(m)$$

| 序号 | 源状态 (`from`) | 目标状态 (`to`) | 触发条件与恢复协议 |
|---:|---|---|---|
| 1 | `PREPARED` | `APPLYING` | Layer 3 开始调用受权 Blender C-API 关系修改接口。 |
| 2 | `PREPARED` | `NO_EFFECT` | 调用 `APPLYING` 前事务中止，或前置检查确认关系已属于 `PRE_EXISTING_ORIGINAL` 无需执行 C-API 写入。 |
| 3 | `APPLYING` | `APPLIED_VERIFIED` | Blender C-API 调用返回（或部分生效后捕获异常），实时 RNA 检查证明目标关系变更已实际生效。 |
| 4 | `APPLYING` | `NO_EFFECT` | Blender C-API 调用抛出异常，且实时 RNA 检查证明未产生任何关系副作用。 |
| 5 | `APPLYING` | `RECOVERY_UNCERTAIN` | Blender C-API 调用失败，且实时 RNA 拓扑不可读、损坏或存在无法证明的外部干扰。 |
| 6 | `APPLIED_VERIFIED` | `CONFIRMED` | Layer 3 完成变更后登记，在活动事务中确认该关系操作。 |
| 7 | `APPLIED_VERIFIED` | `REVERTED` | 在确认前事务进入 `ROLLING_BACK`，Layer 5 调用 Layer 3 合法撤销已生效变更并核验恢复成功。 |
| 8 | `APPLIED_VERIFIED` | `RECOVERY_UNCERTAIN` | 在确认前事务进入 `ROLLING_BACK`，但撤销失败、身份失效或存在外部冲突无法安全撤销。 |
| 9 | `CONFIRMED` | `REVERTED` | 操作确认后外层事务进入 `ROLLING_BACK`，Layer 5 调用 Layer 3 按所有权合同撤销/恢复该变更并核验成功。 |
| 10 | `CONFIRMED` | `RECOVERY_UNCERTAIN` | 操作确认后外层事务进入 `ROLLING_BACK`，但撤销失败或存在外部依赖冲突无法安全恢复。 |

- **回滚核验耦合要求**：在 `ROLLING_BACK` 期间，所有处于 `APPLIED_VERIFIED` 或 `CONFIRMED` 的事务关系记录必须收敛至 `REVERTED`（或证实无变更的 `NO_EFFECT`）。任何记录停留在 `APPLIED_VERIFIED`、`CONFIRMED` 或转入 `RECOVERY_UNCERTAIN`，均导致 Layer 5 回滚核验失败，由 Layer 1 将事务置为 `FAILED`（`FAILED-B` / `FAILED-C`）。
---

### 10.6 九状态事务生命周期 (Planned Target Architecture)

#### 10.6.1 九状态集合与唯一决策权

- **严格九状态集合（严禁增加第 10 个事务状态）**：
  `CREATED`、`SNAPSHOTTING`、`ACTIVE`、`COMMITTING`、`COMMITTED`、`ROLLING_BACK`、`ROLLED_BACK`、`CLEANUP_PENDING`、`FAILED`。
- **唯一状态与门禁决策者**：**Layer 1 Transaction Coordinator** 是全部 9 个事务生命周期状态转换及所有准入门禁（`CLEANUP_PENDING`、`FAILED` 隔离/墓碑）注册与注销的**唯一决策者**。Layer 2 仅被动存储，Layer 6 严禁自行注销门禁。

#### 10.6.2 十二条规范状态转换表（Canonical Lifecycle State Transitions）

| 源状态 | 目标状态 | 触发条件 (Trigger) | 守卫条件 (Guard) | 决策者 | 执行者 | 失败行为 | 核验要求 |
|---|---|---|---|---|---|---|---|
| `CREATED` | `SNAPSHOTTING` | 准入门禁核验通过后进入事务上下文 | `query_admission_gate_status` 返回 `ALLOWED`（无 `CLEANUP_PENDING`，无活动 `FAILED-B/C` 隔离） | Layer 1 | Layer 1 指令 Layer 2 更新状态并调用 Layer 5 `_snapshot_arm_rig_state` | 门禁阻断时零写入拒绝进入 | 状态为 `SNAPSHOTTING`，栈深为 1 |
| `CREATED` | `FAILED` | 快照前上下文初始化失败 | 零受管写入发生 | Layer 1 | Layer 1 分类为 `FAILED-A`（若 Armature 已死亡则为 `FAILED-D`）并更新 Layer 2 | 抛出 `RuntimeError`；`FAILED-A` 不永久隔离健康 Armature | 零场景写入；结构完好时 Armature 仍可准入 |
| `SNAPSHOTTING` | `ACTIVE` | Layer 5 完成只读基准快照捕获 | 4 控制器、6 骨骼、约束与集合深拷贝完成且零场景写入 | Layer 1 | Layer 1 更新 Layer 2 状态并向 Layer 4 产出上下文 | 快照读取异常时转入 `FAILED` | 快照不可变且捕获期间零写入 |
| `SNAPSHOTTING` | `FAILED` | 基准快照捕获期间抛出异常 | 零业务写入执行 | Layer 1 | 零写入且结构完好时分类为 `FAILED-A`；若检测到既有结构损坏/死亡则分类为 `FAILED-C/D` | 弹出事务栈并抛出 `RuntimeError` | `FAILED-A` 不隔离健康骨架；`FAILED-C/D` 执行隔离/墓碑 |
| `ACTIVE` | `COMMITTING` | Layer 4 业务块正常退出且无未处理异常 | `active_tx.rollback_only` 为 `False`，且所有关系日志处于 `CONFIRMED` 或 `NO_EFFECT` | Layer 1 | Layer 1 更新状态并执行提交准备 `_depsgraph_update` | 若 `rollback_only == True`，拒绝提交并强制转入 `ROLLING_BACK` | 无被吞没的内层失败 |
| `ACTIVE` | `ROLLING_BACK` | Layer 4/3 抛出异常，或退出时检测到 `rollback_only == True` | 基准快照存在 | Layer 1 | Layer 1 更新状态并调用 Layer 5 `_rollback_arm_rig_state` | 回滚执行异常时转入 `FAILED` (`FAILED-B/D`) | 触发 Layer 5 回滚与回滚后核验 |
| `COMMITTING` | `COMMITTED` | 提交准备 `_depsgraph_update` 成功完成 | `depsgraph.update()` 无异常 | Layer 1 | Layer 1 将状态更新为 `COMMITTED`（跨越不可逆提交红线） | 提交准备在跨越红线前失败则转入 `ROLLING_BACK` | 跨越不可逆提交边界，后续禁止普通回滚 |
| `COMMITTING` | `ROLLING_BACK` | 跨越提交红线前 `_depsgraph_update` 抛出异常 | 状态尚未到达 `COMMITTED` | Layer 1 | Layer 1 调用 Layer 5 执行完整回滚与核验 | 回滚/核验失败则转入 `FAILED` (`FAILED-B/C/D`) | 完整恢复基准状态 |
| `COMMITTED` | `CLEANUP_PENDING` | Layer 6 提交后清理对必选清理项返回 `CLEANUP_INCOMPLETE` 或 `CLEANUP_FAILED` | 至少一项废弃实体或具显式删除授权的必选 DataBlock 删除失败 | Layer 1 | Layer 1 更新状态并指令 Layer 2 登记 `_PENDING_ARM_RIG_CLEANUPS` | 阻断同会话身份 Armature 的后续写事务直至重试成功 | `PRESERVED_NO_DELETE_AUTHORITY` 条目绝不触发该转换 |
| `CLEANUP_PENDING` | `COMMITTED` | Coordinator 分发的 `retry_cleanup` 返回 `CLEANUP_SUCCESS` | 全部必选废弃项已清理（无授权 DataBlock 已标为保留） | Layer 1 | Layer 1 指令 Layer 2 `_clear_pending_arm_rig_cleanup_by_coordinator` 并更新状态为 `COMMITTED` | 重试仍失败则保持 `CLEANUP_PENDING` | 从待清理门禁移除，恢复写事务准入 |
| `ROLLING_BACK` | `ROLLED_BACK` | Layer 5 回滚恢复与 `_verify_arm_rig_state_restored` 100% 通过 | 属性偏差 $\le 10^{-5}$，且全部关系日志处于 `NO_EFFECT` 或 `REVERTED` | Layer 1 | Layer 1 更新状态为 `ROLLED_BACK`，弹出栈并重新抛出原业务异常 | 存在偏差或 `RECOVERY_UNCERTAIN` 则转入 `FAILED` | 100% 匹配基准快照，Armature 保持健康可准入 |
| `ROLLING_BACK` | `FAILED` | 回滚执行异常 (`FAILED-B`)、核验不匹配/`RECOVERY_UNCERTAIN` (`FAILED-C`) 或 Armature 死亡 (`FAILED-D`) | 回滚或核验未能干净完成 | Layer 1 | Layer 1 指令 Layer 2 记录会话隔离或死亡墓碑，并抛出复合 `RuntimeError` | 在 Layer 2 强制保持持久化会话隔离或墓碑 | 后续写事务被门禁拒绝；解除隔离须经 Layer 5 分类证据核验与 Layer 1 批准 |

#### 10.6.3 嵌套事务与 `rollback_only` 合同

- 同一 Armature 会话身份上的重入事务请求复用外层事务上下文（栈深保持为 1，共享单一基准快照）。
- 若内层操作发生异常或预检失败（即使被调用方 `try/except` 捕获），必须显式调用 `outer_tx.mark_rollback_only(reason)`。
- 外层退出尝试提交时，Layer 1 Coordinator 检查 `tx.rollback_only`；若为 `True`，拒绝 `COMMITTING` 并强制转入 `ROLLING_BACK`，从结构上杜绝内层失败后的静默提交。

#### 10.6.4 会话身份模型（`ArmatureSessionIdentityRecord`）与四类 `FAILED-A/B/C/D` 隔离及解除机制

- **作用域边界声明**：会话身份与 `FAILED` 隔离严格作用于当前活跃 Blender 进程的 Python 内存会话（不修改 Blender 对象自定义属性以保护零写入快照不变量；跨进程重启或重新打开 `.blend` 文件属于独立持久化边界）。
- **会话身份记录（`ArmatureSessionIdentityRecord` 8 字段）**：`registry_session_id`（UUID4）、`original_blender_ref`、`registration_pointer`、`original_data_pointer`、`liveness_status`（`ALIVE_VERIFIED` / `INVALIDATED_DEAD`）、`in_live_blender_collection`、`isolation_state`（`NONE` / `ISOLATED_FAILED_B` / `ISOLATED_FAILED_C` / `TOMBSTONED_FAILED_D` / `ARCHIVED_RETIRED`）、`tombstone_record`。
- **身份匹配与新骨架防误伤规则**：仅当 `original_blender_ref` 未触发 `ReferenceError`、引用相等、指针等于 `registration_pointer` 且存在于 `bpy.data.objects.values()` 时才匹配同一会话身份。若原 Armature 被销毁（转入 `TOMBSTONED_FAILED_D`），后续新建的同名或复用 C 地址的新 Armature 会分配全新 `registry_session_id`——既不将新对象误判为已死对象的恢复，也不让已死对象的墓碑错误阻断合法新 Armature。
- **四类失败分类（`FAILED-A/B/C/D`）**：
  - `FAILED-A`（写前失败）：发生在进入 `ACTIVE` 之前且证实零受管写入、骨架结构完好；事务以 `FAILED` 结束，但**不将健康 Armature 置入持久隔离**。
  - `FAILED-B`（回滚执行异常）：强制置入 `ISOLATED_FAILED_B` 会话隔离，阻断该骨架后续一切写事务。
  - `FAILED-C`（回滚后核验不匹配）：强制置入 `ISOLATED_FAILED_C` 会话隔离，阻断后续写事务，严禁同名替代资源蒙混过关。
  - `FAILED-D`（原始 Armature 身份失效/死亡）：记录转入 `TOMBSTONED_FAILED_D` 永久死亡墓碑。
- **三类解除隔离与墓碑归档合同（由 Layer 5 核验、Layer 1 Coordinator 唯一批准、Layer 2 记录 `_DEISOLATION_AUDIT_LOG`）**：
  - **Case 1（存在可信完整快照，适用于 `FAILED-B/C`）**：原骨架 `ALIVE_VERIFIED`、原快照子资源身份完好、Layer 5 `_verify_arm_rig_state_restored` 零偏差通过、零关系日志残留于 `RECOVERY_UNCERTAIN` 或未撤销态。
  - **Case 2（无完整可信快照）**：严禁伪造快照；由 Layer 5 执行独立结构完整性与不变量核验（骨骼层级完整、控制器/约束要么 100% 干净未初始化要么 100% 符合共形合同、零孤立事务残留）。
  - **Case 3（`TOMBSTONED_FAILED_D` 死亡墓碑）**：绝不接受新对象冒充恢复；仅允许通过 `retire_dead_armature_tombstone` 在 Layer 5 确认原对象彻底不存在且关联孤立产物已清理后，由 Coordinator 归档为 `ARCHIVED_RETIRED`。
  - **与 `CLEANUP_PENDING` 的严格区分**：普通 `retry_pending_arm_rig_cleanup` **绝不能清除 `FAILED` 隔离**，`FAILED` 永远不可转入 `COMMITTED`。

---

### 10.7 十八项资源操作权限 (Planned Target Architecture)

以下完整固化 `architecture_audit_evidence.canonical_resource_operation_permissions` 的全部 18 项资源与关系操作权限：

| 序号 | Operation | Initiator | Authorized Executor | Transaction Phase | Ownership Requirement | Prepare Requirement | Rollback Responsibility | Verification Requirement |
|---:|---|---|---|---|---|---|---|---|
| 1 | `Object Creation` | Layer 4 (`ACTIVE`) | Layer 3 (`_get_or_create_empty`) | `ACTIVE` | 名称冲突检查；在集合链接前立即登记至 Layer 2 `created_controller_objects` | 确认 `active_tx` 为 `ACTIVE` 且无外部同名对象冲突 | Layer 5 调用 Layer 3 `_authorized_remove_object` 按核验引用+指针删除 | 回滚后不在 `bpy.data.objects` 中；提交后指针核验一致 |
| 2 | `Object Deletion` | Layer 5 (`ROLLING_BACK`) 或 Layer 6 (`POST_COMMIT_CLEANUP`) | Layer 3 (`_authorized_remove_object`) | `ROLLING_BACK` 或 `POST_COMMIT_CLEANUP` | 证实属于 `created_controller_objects`（回滚）或 `stashed_objects`（清理）+ `IdentityVerified` + 零外部依赖关系 | 核验活跃引用、指针相等、`bpy.data.objects` 包含性及无外部挂载 | 若检测到外部依赖则以 `OWNERSHIP_CONFLICT` 停止删除并保留现场；清理成功则 Layer 6 标记 `obj_cleaned = True` | 确认目标对象从 `bpy.data.objects` 移除且外部对象完好无损 |
| 3 | `Constraint Creation` | Layer 4 (`ACTIVE`) | Layer 3 (`_authorized_create_constraint`) | `ACTIVE` | 创建时立即登记至 Layer 2 `created_constraints`（骨骼名、引用、指针） | 核验 PoseBone 存活且 `active_tx` 为 `ACTIVE` | Layer 5 调用 Layer 3 `_authorized_remove_constraint` 按核验引用+指针移除 | 回滚后从 `pose_bone.constraints` 移除且原有约束顺序完好 |
| 4 | `Constraint Deletion` | Layer 5 (`ROLLING_BACK`) 或 Layer 6 (`POST_COMMIT_CLEANUP`) | Layer 3 (`_authorized_remove_constraint`) | `ROLLING_BACK` 或 `POST_COMMIT_CLEANUP` | 证实属于 `created_constraints` 或 `stashed_constraints` + `IdentityVerified` | 核验活跃引用、指针相等且存在于 `pose_bone.constraints` | 身份不匹配时立即中止删除；清理成功则记录完成 | 同骨骼上的外部约束保持完全相同的指针、属性与相对顺序 |
| 5 | `Collection Creation` | Layer 4 (`ACTIVE`) | Layer 3 (`_ensure_character_collection`) | `ACTIVE` | 父集合链接前立即登记至 Layer 2 `created_collections` | 确认无外部集合冲突并登记引用+指针 | Layer 5 调用 Layer 3 解绑并删除该新建集合（仅限零外部成员与零外部子集合时） | 回滚后从 `bpy.data.collections` 移除（若含外部实体则保留并报错） |
| 6 | `Collection Deletion` | Layer 5 (`ROLLING_BACK`) | Layer 3 | `ROLLING_BACK` | 已登记于 `created_collections` + `IdentityVerified` + 零外部对象 + 零外部子集合 | 检查 `collection.objects` 与 `collection.children` 是否存在非本事务实体 | 若含外部实体则保留集合并标记 `OWNERSHIP_CONFLICT` | 原有已存在集合与非空外部集合绝不被删除 |
| 7 | `DataBlock Creation` | Layer 4 / Layer 3 (`ACTIVE`) | Layer 3 | `ACTIVE` | 立即在 Layer 2 `datablock_authorizations` 登记 `provenance = TYPE_A_TX_CREATED` 且 `scope = PHYSICAL_DELETE_IF_ZERO_USERS` | 捕获 `original_reference`、`original_pointer`、`resource_kind` 与 `tx_id` | Layer 5 在所属 Object 移除后调用 Layer 3 `_authorized_remove_datablock_if_permitted` 删除 | 回滚后零孤立 Type A DataBlock 残留 |
| 8 | `DataBlock Deletion` | Layer 5 (`ROLLING_BACK`) 或 Layer 6 (`POST_COMMIT_CLEANUP`) | Layer 3 (`_authorized_remove_datablock_if_permitted`) | `ROLLING_BACK` 或 `POST_COMMIT_CLEANUP` | 满足 `CanDelete(D, t) <=> AuthorizedCleanup(D, t) and IdentityVerified(D) and Users(D) == 0 and NoProtectedDependency(D)` | 核验显式授权记录（`TYPE_A` 或 `TYPE_B_PRE_EXISTING_EXPLICIT_GRANT`）、引用/指针匹配、`users == 0`、`use_fake_user == False`、`library is None` | 无授权 DataBlock（无授权 Type B、Type C）必须保留并记为 `PRESERVED_NO_DELETE_AUTHORITY`；必选删除失败则返回 `CLEANUP_FAILED` | 零引用的无授权 Type B 与 Type C DataBlock 绝不被删除，也绝不触发假性 `CLEANUP_PENDING` |
| 9 | `Collection Object Link` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复 `TX_UNLINKED_ORIGINAL`） | Layer 3 (`_authorized_link_object_to_collection` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | 控制器与集合身份有效且具当前事务授权 | 在 Layer 2 7 状态日志建立 `PREPARED` 记录；若已存在链接（`PRE_EXISTING_ORIGINAL`），直接转入 `NO_EFFECT` 不执行 C-API 写入 | Layer 5 调用 Layer 3 解绑 `TX_ADDED` 链接并将日志从 `APPLIED_VERIFIED`/`CONFIRMED` 更新为 `REVERTED` | 回滚后日志终态为 `REVERTED` 或 `NO_EFFECT`；原有已存在链接完好保留 |
| 10 | `Collection Object Unlink` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 撤销 `TX_ADDED`） | Layer 3 (`_authorized_unlink_object_from_collection` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | 具备已证实的 `TX_ADDED` 因果记录（用于回滚解绑）或显式业务解绑记录（`TX_UNLINKED_ORIGINAL`） | 核验 `Undo(m)` 定理前提或记录 `PREPARED` 解绑意图 | 对 `TX_UNLINKED_ORIGINAL`，Layer 5 调用 Layer 3 重新链接并将日志更新为 `REVERTED` | 外部链接及标记为 `NO_EFFECT` 的 `PRE_EXISTING_ORIGINAL` 链接绝不被解绑 |
| 11 | `Collection Child Link` | Layer 4 (`ACTIVE`) 或 Layer 5 (`ROLLING_BACK`) | Layer 3 (`_authorized_link_child_collection` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | 父子集合身份有效 | 在 7 状态日志登记 `PREPARED`；若已链接则直接转入 `NO_EFFECT` | Layer 5 调用 Layer 3 解绑 `TX_ADDED` 子集合并将日志更新为 `REVERTED` | 原有已存在的集合父子层级在回滚时绝不被解绑 |
| 12 | `Collection Child Unlink` | Layer 5（`ROLLING_BACK` 撤销 `TX_ADDED` 子集合链接） | Layer 3 (`_authorized_unlink_child_collection` / `_authorized_restore_relationship`) | `ROLLING_BACK` | 证实属于处于 `APPLIED_VERIFIED` 或 `CONFIRMED` 的 `TX_ADDED` 子集合链接且零外部伤害 | 核验 `Undo(m)` 定理前提 | 核验解绑成功后日志转入 `REVERTED`，不安全则转入 `RECOVERY_UNCERTAIN` | 集合父子层级拓扑与基准快照完全一致 |
| 13 | `Object Parent Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 3 (`_authorized_assign_object_parent` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | 目标控制器受本事务管理且父对象身份核验有效 | 在 Layer 2 7 状态日志登记 `PREPARED` 父级变更记录并保存原父级引用/指针 | Layer 5 调用 Layer 3 `_authorized_restore_relationship` 恢复原父级引用并将日志更新为 `REVERTED` | 控制器父级引用与指针完全匹配快照；回滚后日志状态为 `REVERTED` |
| 14 | `Matrix Parent Inverse Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 3（与 `Object.parent` 绑定/恢复耦合时）或 Layer 5（数值矩阵核验） | `ACTIVE` 或 `ROLLING_BACK` | 控制器受本事务管理且父级共形预检通过 | 非奇异父级矩阵预检通过，并与父级关系日志记录耦合 | 随原父级绑定经由 Layer 3 / Layer 5 恢复为快照中的精确 $4\times 4$ 矩阵 | $4\times 4$ 矩阵全部元素与快照偏差 $\le 10^{-5}$ |
| 15 | `Constraint Target Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 3 (`_authorized_assign_constraint_targets` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | 约束属于受管 Rig PoseBone 且目标控制器身份核验有效 | 在 Layer 2 7 状态日志登记 `PREPARED` 目标引用变更记录 | Layer 5 调用 Layer 3 `_authorized_restore_relationship` 恢复原 `con.target`/`subtarget` 并将日志更新为 `REVERTED` | `con.target` 引用/指针与 `subtarget` 匹配快照；回滚后日志到达 `REVERTED` |
| 16 | `Constraint Pole Target Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 3 (`_authorized_assign_constraint_targets` / `_authorized_restore_relationship`) | `ACTIVE` 或 `ROLLING_BACK` | IK 约束受本事务管理且极向控制器身份核验有效 | 在 Layer 2 7 状态日志登记 `PREPARED` 极向目标引用变更记录 | Layer 5 调用 Layer 3 `_authorized_restore_relationship` 恢复原 `con.pole_target`/`pole_subtarget` 并将日志更新为 `REVERTED` | `con.pole_target` 引用/指针匹配快照；回滚后日志到达 `REVERTED` |
| 17 | `Constraint Influence Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 4（`ACTIVE` 下）与 Layer 5（`ROLLING_BACK` 下） | `ACTIVE` 或 `ROLLING_BACK` | 受管 Rig 约束上的数值属性，基准值已捕获于 Layer 5 快照 | 预检阶段完成 $[0.0, 1.0]$ 有限值校验且基准快照已激活 | Layer 5 直接将数值 `influence` 恢复为快照值 | 恢复后的 `influence` 与快照偏差 $\le 10^{-5}$ |
| 18 | `Constraint Numeric Parameter Assignment` | Layer 4 (`ACTIVE`) 或 Layer 5（`ROLLING_BACK` 恢复） | Layer 4（`ACTIVE` 下）与 Layer 5（`ROLLING_BACK` 下） | `ACTIVE` 或 `ROLLING_BACK` | 受管 Rig 约束上的纯数值参数（`pole_angle`, `chain_count`, `use_stretch`），基准已捕获于快照 | 预检阶段完成有限数值校验且基准快照已激活 | Layer 5 直接将数值参数恢复为快照值 | 恢复后的数值参数与快照偏差 $\le 10^{-5}$ |

---

### 10.8 十二项架构合同 (`CONTRACT-01` ～ `CONTRACT-12`) 与十四条影响矩阵 (Planned Target Architecture)

#### 10.8.1 十二项架构合同注册表（Contract Registry）

| Contract ID | 合同名称 | 负责层级 | 核心不变量 (Invariant) | 失败条件 (Failure Condition) | 异常传播与恢复责任 (Recovery Responsibility) | 验证要求摘要 (Verification Requirement) |
|---|---|---|---|---|---|---|
| `CONTRACT-01` | Input Validation & Pre-Write Preflight | Layer 4 (Business) | 所有参数（`side`, `world_xyz`, `rotation`, `pole`, `influence`, `clamp_reach`）及父级有效变换域必须在任何场景写入前完成验证；拒绝时零场景写入 | 非有限值、越界 `influence`、非法 `side` 或奇异/非共形父级矩阵 | 立即抛出 `TypeError` 或 `ValueError`，不进入事务；天然零写入不变量 | 校验非法参数与奇异父矩阵下抛出对应异常且场景与调用前快照 0 差异 |
| `CONTRACT-02` | Same-Armature Nested Transaction & Failure Propagation | Layer 1 (Coordinator) | 同一 Armature 会话身份上的重入事务复用活动上下文，栈深保持为 1；内层失败通过显式报告路径标记 `rollback_only = True` | 跨 Armature 嵌套请求，或内层失败被调用方吞没 | 跨骨架抛出 `RuntimeError`；内层失败在外层提交门禁触发强制完整回滚 | 验证单快照捕获、栈深恒为 1、内层失败被捕获后外层依然强制完整回滚 |
| `CONTRACT-03` | Controller & Created DataBlock Provenance Registration | Layer 3 (Resource Ops) & Layer 2 (Registry) | 新建控制器 Empty 及任何 Type A 事务新建 DataBlock 必须在创建后、集合链接前立即在 `active_tx` 登记引用与指针身份；回滚严格按身份删除新建资源 | 创建失败、重复登记或集合链接前异常 | 异常向 Layer 1 传播并触发回滚；Layer 5 经由 Layer 3 按核验身份删除新建控制器与满足 `CanDelete(D,t)` 的 Type A DataBlock | 在创建后、链接前注入故障，验证零孤立 Empty 或 Type A DataBlock 残留 |
| `CONTRACT-04` | Relationship Mutation 7-State Log & Evidence-Based Rollback | Layer 2, Layer 3, Layer 5 | 全部关系引用修改（无论由 Layer 4 在 `ACTIVE` 发起还是由 Layer 5 在 `ROLLING_BACK` 恢复）必须经由 Layer 3 执行并遵循 7 状态日志与 10 条合法转换；满足 `Undo(m)` 定理；`PRE_EXISTING_ORIGINAL` 重复链接转入 `NO_EFFECT` 零撤销权；回滚时事务变更须收敛至 `REVERTED`，不可证状态转入 `RECOVERY_UNCERTAIN` 并保留现场 | RNA 赋值失败、非法集合链接、Apply 期间指针损坏或关系状态不可证明 | 向 Layer 1 报错；`RECOVERY_UNCERTAIN` 导致 Layer 5 回滚核验失败并由 Layer 1 置为 `FAILED-B/C` | 验证 `PREPARED -> APPLYING -> APPLIED_VERIFIED -> CONFIRMED -> REVERTED`、重复链接 `NO_EFFECT` 保护及 `RECOVERY_UNCERTAIN` 阻断盲目解绑 |
| `CONTRACT-05` | Constraint Configuration, Identity & Restoration | Layer 4, Layer 3, Layer 5 | 约束删除严格基于引用+指针身份经由 Layer 3 执行；`target`/`pole_target` 绑定经由 Layer 3 配合 7 状态日志执行；数值参数由 Layer 4 写入、Layer 5 恢复；外部约束及其相对顺序严格保护 | 约束创建失败、外部同名冲突或原始约束被销毁 | 冒泡至 Coordinator；Layer 5 经由 Layer 3 删除新建约束并恢复目标引用，恢复原有数值属性与相对顺序 | 存在外部同名/前置约束时注入故障，验证事务约束被删且外部约束指针、属性与顺序完好 |
| `CONTRACT-06` | Snapshot Integrity, Zero-Mutation Capture & FAILED-A Classification | Layer 5 & Layer 1 | 快照只读深拷贝 4 控制器、6 骨骼、约束与集合树且零场景写入；若写前只读快照失败且证实零写入、骨架完好，Coordinator 归类为 `FAILED-A` 而不永久封锁健康骨架 | 属性不可读、缺失骨骼或视图层刷新失败 | 抛出 `RuntimeError`；零写入完好时置为 `FAILED-A`（无需回滚、不隔离骨架），结构损坏时置为 `FAILED-C/D` | 快照阶段注入只读异常，验证零场景修改且健康骨架后续事务仍可正常准入 |
| `CONTRACT-07` | Rollback Verification Symmetry & Categorized FAILED Session Isolation | Layer 5, Layer 1, Layer 2 | 回滚恢复与回滚后核验严格对称（容差 $10^{-5}$，全部变更关系日志收敛至 `REVERTED` 或 `NO_EFFECT`）；回滚异常 (`FAILED-B`)、核验偏差 (`FAILED-C`) 或骨架死亡 (`FAILED-D`) 由 Layer 1 指令 Layer 2 记录会话隔离/墓碑；解除隔离须经 Layer 5 分类证据核验与 Layer 1 批准并记入 `_DEISOLATION_AUDIT_LOG` | 恢复报错、指针/引用身份失配、关系日志处于 `RECOVERY_UNCERTAIN` 或属性偏差 $> 10^{-5}$ | 汇总差异抛出复合 `RuntimeError`，在 Layer 2 持久化会话隔离或墓碑，且不误伤独立新 Armature 身份 | 验证 `FAILED-B/C` 阻断同骨架后续写入、未核验解除请求被拒、经核验解除获批并记录审计日志、`FAILED-D` 防冒充且放行新骨架 |
| `CONTRACT-08` | Irreversible Commit, Authorized DataBlock Cleanup & Coordinator Outcome Evaluation | Layer 1, Layer 6, Layer 3, Layer 2 | 跨越 `COMMITTED` 后严禁普通回滚；DataBlock 删除须满足 `CanDelete(D, t)`；无授权 Type B 与 Type C DataBlock 保存在 `PRESERVED_NO_DELETE_AUTHORITY`（非失败）；Layer 6 向 Layer 1 返回 `CleanupOutcome`，严禁自行修改生命周期状态或注销门禁 | 必选清理项因意外活跃引用或 Blender 内部错误无法删除 | Layer 6 返回 `CLEANUP_INCOMPLETE`/`FAILED`，Layer 1 将状态置为 `CLEANUP_PENDING` 并指令 Layer 2 登记门禁；`CLEANUP_SUCCESS` 时由 Layer 1 唯一授权注销门禁 | 验证 `users == 0` 的无授权 Type B / Type C DataBlock 被保留为 `PRESERVED_NO_DELETE_AUTHORITY` 且不触发 `CLEANUP_PENDING`；必选清理失败触发 `CLEANUP_PENDING` |
| `CONTRACT-09` | Unidirectional Admission Gate & Coordinator-Authorized Gate Deregistration | Layer 1 & Layer 2 | Layer 1 单向查询 Layer 2 准入门禁；当同 `ArmatureSessionIdentityRecord` 存在未解决 `CLEANUP_PENDING` 或活动 `FAILED-B/C` 隔离时阻断新写事务；仅 Layer 1 Coordinator 有权授权清除门禁或解除隔离 | 对存在 `CLEANUP_PENDING` 或 `FAILED-B/C` 隔离的骨架发起写入，或用 Cleanup Retry 尝试清除 `FAILED` | 零写入抛出 `RuntimeError`；`CLEANUP_PENDING` 经 Coordinator 监督重试解除，`FAILED` 仅能经解除隔离治理流程解除 | 验证门禁阻断写入、Coordinator 授权重试清除 `CLEANUP_PENDING`、Cleanup Retry 严禁清除 `FAILED-B/C/D` |
| `CONTRACT-10` | WBC / Arm IK Cross-Module Interface | Upper Pipeline (WBC) & Layer 4 | WBC 依赖 Arm IK 获取单帧可达性反馈与零副作用异常安全性；Arm IK 抛出的准入拒绝或事务失败向 WBC 明确报告单帧规划失败 | Arm IK 抛出异常或返回不可达目标 | 异常传播至 WBC 单帧步骤，由 WBC 处理回退或中止当前帧，绝不静默泄漏半提交状态 | 验证可恢复错误下场景保持干净基准态，隔离错误下向 WBC 抛出明确异常 |
| `CONTRACT-11` | Bilateral Reset Atomic Transaction | Layer 4 & Layer 1 | `reset_arm_ik` 在单一统一事务内执行左右双臂复位；每侧顺序更新：(1) Hand Controller, (2) Elbow Pole, (3) PoseBones 中立旋转, (4) Constraint Influences 归零, (5) Prebend Hint；预检失败零写入；中途失败双臂共同回滚；嵌套失败报告 `rollback_only = True` | 父级矩阵预检失败、控制器/权重/预弯写入错误或依赖图刷新失败 | 预检抛出 `ValueError`；写入错误触发左右双臂完整回滚并重抛；嵌套错误标记外层 `rollback_only` | 验证预检失败 0 写入、左臂完成后右臂失败触发双臂完整回滚、嵌套复位失败强制外层回滚 |
| `CONTRACT-12` | External Resource, Unproven DataBlock & New Armature Isolation Protection | Layer 5, Layer 6, Layer 3, Layer 1 | 外部资源（未登记对象/约束/集合、无显式删除授权的 Type B DataBlock、即使 `users == 0` 的 Type C DataBlock、以及 `EXTERNAL_ADDED`/`OWNERSHIP_UNKNOWN` 关系）严格免受删除或解绑；同名冲突拒绝覆盖；`FAILED-D` 死亡墓碑绝不阻断新建独立 Armature | 外部对象占用预期名称、遇到不可证明关系或清理时遇到无授权 DataBlock | 冲突/未知关系标记 `OWNERSHIP_UNPROVEN`/`RECOVERY_UNCERTAIN` 并中止破坏性回滚；无授权 DataBlock 安全保留为 `PRESERVED_NO_DELETE_AUTHORITY` | 验证外部同名对象完好、零引用外部 DataBlock 保留、`FAILED-D` 后新建 Armature 正常执行事务 |

#### 10.8.2 十四条架构影响矩阵记录（Architecture Impact Matrix, `EDGE-01` ～ `EDGE-14`）

| Edge ID | Source | Target | `edge_type` | Direction & Data Flow | State Ownership | Failure Propagation | Recovery Responsibility | Contract ID |
|---|---|---|---|---|---|---|---|---|
| `EDGE-01` | `Layer 4: set_hand_ik_target` | `Layer 4: _preflight_arm_ik_parent_transforms` | `CALL` | `Layer 4 -> Layer 4 (CALL)` | Layer 4 无状态预检 | 抛出 `ValueError`/`TypeError`，进入事务前中止 | 天然零写入不变量 | `CONTRACT-01` |
| `EDGE-02` | `Layer 4: set_hand_ik_target` | `Layer 4: setup_arm_ik` | `CALL` | `Layer 4 -> Layer 4 (CALL)`; 内层向外层上下文写入 `rollback_only` | 最外层 Layer 1 事务 | 内层初始化失败向上冒泡并标记外层 `rollback_only = True` | 最外层 Layer 1 Coordinator | `CONTRACT-02` |
| `EDGE-03` | `Layer 4: setup_arm_ik` | `Layer 3: _get_or_create_empty` | `CALL` | `Layer 4 -> Layer 3 (CALL) -> Layer 2 (STATE_WRITE)` | Layer 3 执行与 Layer 2 所有权存储 | 分配或登记失败中止初始化并冒泡至 Layer 1 | Layer 5 经由 Layer 3 按核验身份删除新建控制器与 Type A DataBlock | `CONTRACT-03` |
| `EDGE-04` | `Layer 3: Authorized Relationship Operations` | `Layer 2: 7-State Relationship Operation Log` | `STATE_WRITE` | `Layer 3 -> Layer 2 (STATE_WRITE)` | Layer 2 关系日志存储 | Prepare 失败零写入转入 `NO_EFFECT`；Apply 错误按实际副作用转入 `NO_EFFECT`、`APPLIED_VERIFIED` 或 `RECOVERY_UNCERTAIN` | Layer 5 调用 Layer 3 将 `APPLIED_VERIFIED`/`CONFIRMED` 撤销为 `REVERTED`；`RECOVERY_UNCERTAIN` 中止回滚 | `CONTRACT-04` |
| `EDGE-05` | `Layer 5: _rollback_arm_rig_state & _verify_arm_rig_state_restored` | `Layer 2: 7-State Relationship Operation Log` | `STATE_READ` | `Layer 5 -> Layer 2 (STATE_READ)`; `Layer 5 -> Layer 3 (CALL Undo) -> Layer 2 (STATE_WRITE REVERTED)` | Layer 2 关系日志与 Layer 5 核验器 | 任何未恢复或处于 `RECOVERY_UNCERTAIN` 的事务关系记录均使回滚后核验失败 | Layer 1 将事务置为 `FAILED` (`FAILED-B/C`) 并隔离 Armature | `CONTRACT-04` |
| `EDGE-06` | `Layer 4: setup_arm_ik` | `Layer 3: _authorized_create_constraint & _authorized_assign_constraint_targets` | `CALL` | `Layer 4 -> Layer 3 (CALL)` | 场景约束栈与 Layer 2 所有权/关系日志 | 约束创建或目标绑定异常冒泡至 Layer 1 并触发回滚 | Layer 5 经由 Layer 3 移除新建约束并恢复原目标绑定，同时恢复数值属性与顺序 | `CONTRACT-05` |
| `EDGE-07` | `Layer 1: _arm_rig_transaction` | `Layer 5: _snapshot_arm_rig_state` | `CALL` | `Layer 1 -> Layer 5 (CALL)`; `Layer 5 -> Layer 1 (RESULT Snapshot)` | Layer 5 不可变快照存储 | 快照失败将事务置为 `FAILED`（零写入且结构完好时归为 `FAILED-A`） | `FAILED-A` 无需回滚且不错误封锁健康骨架 | `CONTRACT-06` |
| `EDGE-08` | `Layer 1: _arm_rig_transaction & request_armature_deisolation` | `Layer 5: _rollback_arm_rig_state, _verify_arm_rig_state_restored & verify_armature_deisolation_evidence` | `CALL` | `Layer 1 -> Layer 5 (CALL)`; `Layer 5 -> Layer 1 (RESULT VerificationResult / DeisolationVerificationReport)` | Layer 5 核验器与 Layer 1 唯一状态决策权 | 回滚错误 (`FAILED-B`)、核验偏差 (`FAILED-C`) 或骨架死亡 (`FAILED-D`) 通过 `RESULT` 报送 Layer 1，由 Layer 1 指令 Layer 2 隔离/立碑 | 解除隔离须由 Layer 5 返回分类核验报告 (`RESULT`) 并经 Layer 1 批准 (`STATE_WRITE` 至 Layer 2) | `CONTRACT-07` |
| `EDGE-09` | `Layer 1: _arm_rig_transaction & _dispatch_retry_cleanup` | `Layer 6: retry_cleanup` | `CALL` | `Layer 1 -> Layer 6 (CALL)`; `Layer 6 -> Layer 1 (RESULT CleanupOutcome)` | Layer 1 独占生命周期/门禁状态；Layer 6 维护单条目进度标志 | 必选清理错误返回 `CLEANUP_INCOMPLETE`/`FAILED`；无授权 DataBlock 记为 `PRESERVED_NO_DELETE_AUTHORITY` 并返回 `CLEANUP_SUCCESS` | 必选清理失败时 Layer 1 设置 `CLEANUP_PENDING`，并在收到 `CLEANUP_SUCCESS` 时唯一授权注销门禁 | `CONTRACT-08` |
| `EDGE-10` | `Layer 6: retry_cleanup` | `Layer 2: DataBlock Cleanup Authorization Records & Layer 3: _authorized_remove_datablock_if_permitted` | `CALL` | `Layer 6 -> Layer 2 (STATE_READ Auth & STATE_WRITE Item Progress)`; `Layer 6 -> Layer 3 (CALL Conditional Delete)` | Layer 2 DataBlock 清理授权记录 | 缺少删除授权时保留为 `PRESERVED_NO_DELETE_AUTHORITY` 不报错；必选删除报错向 Layer 1 返回 `CLEANUP_FAILED` | Layer 6 保留无授权 Type B 与 Type C DataBlock，仅重试受权必选 DataBlock | `CONTRACT-08` |
| `EDGE-11` | `Layer 1: _arm_rig_transaction & _assert_arm_rig_cleanup_gate` | `Layer 2: query_admission_gate_status & Session Identity Registry` | `STATE_READ` | `Layer 1 -> Layer 2 (STATE_READ / STATE_WRITE)`; `Layer 2 -> Layer 1 (RESULT GateResult)` | Layer 1 决策权；Layer 2 被动索引存储 | 未解决 `CLEANUP_PENDING` 或活动 `FAILED-B/C` 隔离抛出 `RuntimeError` 拒绝准入；`FAILED-D` 墓碑防冒充但放行新骨架身份 | 仅 Layer 1 Coordinator 有权指令 Layer 2 清除 `CLEANUP_PENDING` 或解除 `FAILED` 隔离 | `CONTRACT-09` |
| `EDGE-12` | `Upper Pipeline: WBC` | `Layer 4: Arm IK Public APIs` | `CALL` | `WBC -> Layer 4 (CALL)`; `Layer 4 -> WBC (RESULT Reachability / Exception)` | WBC 轨迹状态 | Arm IK 准入拒绝或回滚/隔离异常向 WBC 冒泡，指示当前帧 IK 失败 | Arm IK 保证干净回滚或显式隔离；WBC 调整或中止帧规划 | `CONTRACT-10` |
| `EDGE-13` | `Layer 4: reset_arm_ik` | `Layer 1: _arm_rig_transaction` | `CALL` | `Layer 4 -> Layer 1 (CALL)` | Layer 1 统一事务 | 左臂或右臂复位写入失败触发双臂完整回滚；嵌套失败设置外层 `rollback_only` | Layer 5 恢复双臂骨骼姿态、控制器、权重与预弯提示 | `CONTRACT-11` |
| `EDGE-14` | `Layer 5: _rollback_arm_rig_state, Layer 6: retry_cleanup & Layer 3: Authorized Resource Operations` | `External Scene Resources & Unproven DataBlocks` | `PROTECTION` | `Layer 5 / Layer 6 / Layer 3 -> External Scene Resources & Unproven DataBlocks (PROTECTION)` | 外部调用方 / 外部场景图 | 对象/关系冲突抛出 `OWNERSHIP_UNPROVEN` / `RECOVERY_UNCERTAIN`；无授权 DataBlock 保留为 `PRESERVED_NO_DELETE_AUTHORITY` | 拒绝在外部对象、外部关系及未授权 DataBlock 上执行破坏性操作 | `CONTRACT-12` |

---

### 10.9 Reset 双臂事务 (Planned Target Architecture)

#### 10.9.1 执行序列与状态流

```text
Admission Check (_assert_arm_rig_cleanup_gate)
    ↓
Parent Transform Preflight (L & R HandIK / ElbowPole non-singular conformal check, Zero Writes)
    ↓
Unified Snapshot (Single immutable dual-arm baseline snapshot via Layer 5)
    ↓
Left Arm Reset (5-Step Sequential Writes: HandIK.L -> ElbowPole.L -> PoseBones.L -> Influences.L -> Prebend.L)
    ↓
Right Arm Reset (5-Step Sequential Writes: HandIK.R -> ElbowPole.R -> PoseBones.R -> Influences.R -> Prebend.R)
    ↓
Commit Preparation (_depsgraph_update)
    ↓
Logical Commit (Crosses irreversible COMMITTED boundary)
    ↓
Post-Commit Cleanup (Coordinator dispatches Layer 6 retry_cleanup -> evaluates CleanupOutcome)
```

#### 10.9.2 核心不变量与当前代码区分

- **左右双臂共同原子性**：左臂与右臂复位隶属于同一个统一事务；任何一侧在任意步骤失败，必须完整回滚左右双臂的全部控制器、骨骼旋转、约束权重与预弯状态，严禁留下“左臂已复位、右臂未复位”的半重置状态。
- **单一快照与五项复位序列**：仅捕获一次覆盖双臂的基准快照；每侧严格按顺序复位：(1) Hand Controller 变换，(2) Elbow Pole 变换，(3) `upper_arm`/`forearm`/`hand` 欧拉角归零 `(0,0,0)`，(4) `ArmIK` 与 `HandRotation` 约束 `influence` 归零 `0.0`，(5) 施加 Prebend Hint。
- **嵌套事务复用与 `rollback_only`**：当 `reset_arm_ik` 在同一 Armature 的外层事务内被嵌套调用时，直接复用外层事务上下文（不新建第二份快照、不提前提交外层事务、不独立执行提交后清理）；若预检或写入失败，显式调用 `outer_tx.mark_rollback_only(reason)` 强制外层事务在退出时回滚。
- **提交后清理门禁**：逻辑提交后若必选清理项失败，由 Layer 6 返回 `CLEANUP_INCOMPLETE`/`CLEANUP_FAILED`，Layer 1 Coordinator 将状态置为 `CLEANUP_PENDING` 并登记门禁。
- **当前代码与批准目标合同的准确区分**：
  - **当前已实现部分**：`reset_arm_ik` 事务业务实现物理归属为 `src/scene_transaction_integrity/layer4/reset.py` 及 `src/scene_transaction_integrity/wiring.py` 接线入口（`src/rig/arm_ik.py` 保留公开领域入口 `reset_arm_ik()` 委托调用），已经接入 `with _arm_rig_transaction(arm):` 包装、具备前置父级矩阵预检及故障注入边界（`reset_arm_ik_after_influence_l`、`reset_arm_ik_after_influence_r`、`reset_arm_ik_during_depsgraph_update`）。
  - **当前合同核验边界**：底层关系恢复、关系日志、DataBlock 受权清理、`CleanupOutcome` 结果汇报及失败会话隔离均已有后续生产实现，不能继续标记为“尚未开始落地”；其与第10节全部批准合同的符合程度必须以对应源码审计及专项测试独立核验，不能仅凭存在性宣布 PASS。

---

### 10.10 验证与后续实施 (Planned Target Architecture)

> **状态与合同边界**：第10节批准的目标合同及14条影响关系原样保留；第3项同步为2026-11-26的实际进度。旧实施节点只属于历史，不得重新被当成当前任务准入。

1. **十二项合同验证要求**：
   - `CONTRACT-01` 至 `CONTRACT-12` 的正向场景、故障场景、外部共享状态影响、待核验不变量及通过/失败判据已在批准架构 JSON（`f3_verification_requirements`）与本节 10.8.1 表中完整固化。
2. **静态设计验收与运行测试的严格区分**：
   - 本节的固化代表 **目标架构设计（`APPROVED TARGET ARCHITECTURE`）已通过静态架构审计**。
   - **静态架构验收通过绝不等于生产代码实现已完成或运行测试已通过**。
   - 严禁用历史提交（如 10-B-8 的 `102/102 PASS`）代替新生产修复的真实回归运行结果。
   - 严禁以自动化测试（`Automated Pass`）代替 Blender GUI 视口真实目视验收。
3. **后续受控原子实施路线与准入边界**：
   - **Task 10-B**：已于 2026-11-20 获项目负责人正式验收，并已完成六层架构物理拆分、拆分后全量回归（`2f248bf4b98776222e37bc3228506a4fb85f7c32` / `dcf305738aa9191daeab0f002f97cf4975c12498`）及双父节点主干收归（`c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`，`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`），不再重新打开；禁止把历史“继续按原子阶段实施”解释为新修复授权。
   - **历史计划：Task 10-B-11**：当时聚焦 `Collection ↔ Object` 关系所有权；该轮已不再是当前执行节点。当前不因该旧计划自行新增代码或重复修复。
   - **Task 10-C、Task 10-D、Task 11 与 Task 12 / PKG-5 状态**：Task 10-C（`f2501ddc`）、Task 10-D（`824c52ec` / `7f14ff72`）、Task 11（`added88a7e` / `07aec5d8`）与 **Task 12 / PKG-5**（`12-A/B/C/D` `COMPLETED`、`12-D BUG-01 CLOSED`，冻结生产基线 `eee276b39d`、冻结测试基线 `90f4628a0c`、最终验收证据 `e15d342b80`、主干合并 `d1645452`，`docs/evidence/12/final_acceptance/`）均已收归 `master`；原 16 项历史 Finding `16 CLOSED / 0 OPEN`；`Task 7B-1`（`fcb35bd5`）与 `Task 7B-2`（`a92280bb`）均 `COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（已合入 `master`）；`Task 7B-3`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（20/20 PASS，`d9862ada`）；`Task 7B-4`：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。Phase 7B 已收归 `master`。`Phase 7C` 五节点划分已获负责人批准。`Task 7C-1`：`SPECIALIZED VERIFIED — OWNER ACCEPTED`，Blender 5.1.1 专项 T01–T12 全部通过（12 PASS / 0 FAIL / 0 ERROR / 0 SKIP / 0 NOT_RUN，退出码 0），冻结生产提交 `9311cfef22ac8c8651d97bcd9d00dca41dbb57fa`，证据提交 `7820fe9aec9d9831ec986ec2e3558777e48c7dc8`，证据目录 `docs/evidence/7c-1/verification/`。缓存导致的证据交付阻塞已完成完整性复核，不登记生产 BUG。当前唯一实施节点：`Task 7C-2`（`IMPLEMENTATION — OWNER AUTHORIZED`，分支 `task/7c-2`）。仅允许有效接触至单边受力约束的无状态转换函数及其专项测试脚本准备；有效 GRASP 不得静默降级或丢弃；禁止执行测试，禁止接入生产帧执行链。`7C-3` 至 `7C-5` 尚未开放实施。Phase 7C 尚未合入 master。本次文档同步不改变任何已批准架构合同定义。
