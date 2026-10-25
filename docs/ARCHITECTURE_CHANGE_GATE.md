# ARCHITECTURE_CHANGE_GATE: 永久架构门禁规范 (ACG)
## ProceduralAnimation 系统架构变更准入、行为清规与防漂移纪律

> **版本**：v1.0 (Task 6G-D-PRE-P1 确立)  
> **地位**：**单一规范权威来源 (Single Source of Truth, SSOT)**  
> **生效范围**：全工程所有后续任务（包括 Task 6G-D、6H、7 及后续里程碑）  
> **引用关系**：`AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 统一引用本规范，禁止建立分立版本。

---

## 1. 架构门禁的核心宗旨与原则

本项目为**全程序化 3D 连续动画生成系统**。为彻底根除历史迭代中出现的“多头执行管线并立”、“状态所有权错位引发肢体暴拉”、“独立脚本摆拍冒充连续运动”及“只读指标冒充动力学闭环”等严重架构退化问题，特制定本永久架构门禁（Architecture Change Gate, ACG）。

### 核心铁律
1. **真实代码为准**：磁盘上的实际代码与可复现测试结果是唯一事实依据。
2. **唯一主生产执行链**：所有连续动作必须接入统一执行链：
   $$\text{MotionPlanner} \longrightarrow \text{MotionAction} \longrightarrow \text{KinematicBridgeExecutor} \longrightarrow \text{WholeBodyController} \longrightarrow \text{Blender Rig/IK} \longrightarrow \text{物理遥测} \longrightarrow \text{MotionState}$$
3. **姿态写入权唯一收敛**：`WholeBodyController` 独占全身骨架与控制物体的写入权。
4. **测试退出码绝对一票否决**：任何测试非零退出码或检测到失败标记，绝对不得判定为通过。

---

## 2. 架构防漂移前后置十步闭环检查协议 (Ten-Step Anti-Drift Lifecycle Protocol)

后续所有 Antigravity 开发任务，在执行任何代码编写或修改**前**，必须逐条完成以下前置审查；在任务验证完成收尾**后**，必须再次全量核查闭环：

1. **读取规范与门禁**：完整读取 `AGENTS.md`、`GEMINI.md` 与本架构门禁规范 (`docs/ARCHITECTURE_CHANGE_GATE.md`)。
2. **读取交接卡片**：完整读取最新版 `AI_SYNC.md`，确认当前 Git HEAD commit SHA 与未提交文件现场。
3. **查阅真实源码**：深入查阅相关的真实 Python 模块源码，严禁仅凭架构图、文字概述或聊天记忆推断接口。
4. **核对符号物理存在**：核对所调用的方法、类、枚举成员、数据结构与文件在磁盘上 100% 物理存在（必须通过 `python tests/audit_c2_final_inspector.py --verify-docs` 自动化校验，严禁引用虚构符号）。
5. **杜绝功能职责重叠**：确认新开发内容不会创建与现有系统职责重叠的模块（严禁制造第二套控制器、第二套求解器或第二套场景）。
6. **严禁绕开生产管线**：确认所有运动与骨骼解算接入既有统一管线（$\text{MotionPlanner} \to \text{KinematicBridgeExecutor} \to \text{WholeBodyController} \to \text{Rig/IK/FK}$），严禁私自绕道。
7. **确认任务当前准入**：确认任务属于当前明确准入的阶段（当前为 Task 6G-D-C2-FINAL 冻结维护，后续阶段必须按 7A $\to$ 7B $\to$ 7C $\to$ 7D $\to$ 7E $\to$ 7F $\to$ 6H 顺序逐级准入，严禁提前越级或自设衍生阶段）。
8. **确保历史零退化**：确认修改不会破坏历史回归基准与测试阈值（严禁篡改成熟动作参数、时间轴或静默放宽 ROM 阈值）。
9. **保护跨宿主复用边界**：确认纯 Python 动力学内核与 Blender `bpy` 保持解耦，不破坏未来跨宿主/游戏引擎复用边界。
10. **架构变更事前报批**：核对所有新的架构变更与接口调整是否获得用户明确书面授权并录入 `DECISIONS.md`。

任务执行结束收尾前，必须再次运行相同门禁核验（包括 `--verify-docs` 与统一回归测试套件），严禁假通过。

---

## 3. 架构变更准入前置审查 11 问清单 (Pre-flight Checklist)

任何后续任务在编写或修改生产代码之前，必须在思考过程或技术方案中明确回答以下 11 项审查问题：

| 序号 | 审查项目 | 核心问题与准入要求 |
| :---: | :--- | :--- |
| **Q01** | **已有实现排查** | 所要开发的功能（运动学、约束、物理分析、接触几何），工程内是否已有可复用实现？严禁重复造轮子。 |
| **Q02** | **唯一职责归属** | 新功能归属于哪一层级（调度层 / 动作规划层 / 桥接层 / 全身协调层 / 骨架约束层 / 物理分析层）？是否破坏单一职责？ |
| **Q03** | **真实调用者确权** | 明确指明其真实调用者（Caller）与被调用者（Callee）。严禁建立无上游调用的孤立执行分支。 |
| **Q04** | **数据结构合同** | 明确声明输入参数结构体与输出结果数据类，字段与类型必须在 `kinematic_bridge.py` 或 `framework.py` 中有据可查。 |
| **Q05** | **空间坐标与单位** | 所有位置与矢量是否严格遵循：$+Z$ 轴向上、地面位于 $Z=0.0\text{ m}$、单位为米、角度为度、时间为秒的物理世界坐标约定？ |
| **Q06** | **状态写入所有权** | 是否存在两个或以上模块向同一骨骼、Empty 物体或约束写入位姿的竞争风险？写入权必须唯一收敛。 |
| **Q07** | **历史动作零退化** | 修改是否会对 Walk、Run、SprintStart、SprintBrake 现存成熟步态产生任何退化或位移漂移？ |
| **Q08** | **回归套件明确** | 本次开发完成后，必须执行哪一级别的自动化测试套件（`quick` / `physics` / `motion` / `full`）？ |
| **Q09** | **真实可视化验收** | 功能成果如何通过 Blender 视口直接播放检验？是否能够生成直接可播放的 `.blend` 文件？ |
| **Q10** | **单帧 6 阶段定位** | 新功能挂载在单帧执行协议的哪一阶段（Phase 1 规划 $\to$ Phase 2 接触 $\to$ Phase 3 WBC 求解 $\to$ Phase 4 真实性校验 $\to$ Phase 5 遥测 $\to$ Phase 6 状态提交）？ |
| **Q11** | **未接入隔离边界** | 若为前瞻性数学算法暂不接入主姿态写入链，如何确保其处于纯只读评估层，绝不干扰骨架运动？ |

---

## 3. 架构绝对禁止清规 (Strict Prohibitions)

所有 Agent 与开发者在任何开发过程中，必须无条件遵守以下 10 大清规：

1. **严禁绕开统一控制器**：禁止在业务脚本或动作类中通过 `bpy.ops` 或直接赋值修改骨骼欧拉角/位置，所有姿态解算必须统一由 `WholeBodyController` 分配。
2. **严禁私造并立执行管线**：禁止编写绕开 `KinematicBridgeExecutor` 的独立动作执行器，禁止制造孤立演示分支。
3. **严禁修改成熟历史步态**：禁止为了配合局部新算法，私自篡改 Walk、Run、SprintStart、SprintBrake 经久验证的步长、触地周期和速度剖面。
4. **严禁静态摆拍冒充运动**：禁止在时间轴上通过对静态姿态进行平移或硬编码关键帧来冒充具有连续运动学生命周期的动作。
5. **严禁静默吞没错误与虚报成功**：当 IK 不可达、ROM 超限或接触间隙超差时，必须真实记录失败并返回 `success = False`，绝对禁止截断或掩盖误差后伪报成功。
6. **严禁放宽医学解剖 ROM 阈值**：禁止为了迎合局部测试通过而擅自放宽 `joint_limits.py` 中的解剖生理活动角上下限。
7. **严禁动态切换物体父级指针**：下肢与上肢控制器（`FootIK.L/R`、`KneePole.L/R`）在动画全生命周期内必须恒定保持在绝对世界空间（`parent = None`），禁止任何跨帧动态 reparent 行为。
8. **严禁未实际运行声称完成**：严禁在未实际执行命令、未核对返回码与输出产物前宣称任务“已完成”或“已验证”。
9. **严禁私造孤立动力学训练场**：`output/dynamics_playground.blend` 为 6G-D、6H 及 7A 阶段的单一基准场景（SSOT），严禁为孤立模块重复制造第二套或分立训练场。
10. **严禁摆设虚假动力学遥测箭头**：场景中呈现的所有接触力、法向反作用力、力矩与角动量可视化几何体，必须 100% 绑定来自真实物理模型解算的数值输出，严禁摆设无物理计算支撑的静态伪造几何体。

---

## 4. 架构偏差事前报批流程 (Deviation Protocol)

若在开发中确有充分的数学或工程理由必须变更架构（例如需要变更骨架结构、引入新求解器或调整单帧阶段协议）：
1. **立即暂停代码修改**，保护当前工作区现场；
2. **编写架构变更提案**，详细列明：
   - 拟变更的模块与代码路径；
   - 变更的根本原因与不可替代性；
   - 对现有主调用链与历史动作的影响评估；
   - 历史回归保证措施；
3. **正式向用户提交审批申请**，明确等待用户书面授权；
4. **获得批准后**方可修改代码，并在 `DECISIONS.md` 录入正式决策记录，同步更新 `ARCHITECTURE_SYNC.md` 与本规范。

---

## 5. 自动化测试与目视验收防线 (Verification Gate)

1. **统一测试套件强制执行**：
   - 每次任务结束前，必须通过 `python tests/run_test_suite.py --tier <tier>` 执行回归；
   - 退出码非零一律判定为失败，严禁提交代码。
2. **目视验收防线分离**：
   - 自动化测试通过只能标定为 `Automated Pass`；
   - 任何涉及视觉姿态自然度、步态交替协调性的功能，必须经由用户在 Blender 中目视检查，并由用户明确批准后方可最终关闭任务。

---

## 6. 标准动力学训练场基准场景复用与可视化门禁 (Dynamics Playground Gate)

> **核心原则**：统一基准、场景唯一、环境只读、物理真实、分级验证。

1. **单一标准动力学基准场景权威指定 (SSOT)**：
   - `output/dynamics_playground.blend`（由 `run_dynamics_playground.py` 与 `src/scene/builder.py:build_dynamics_playground` 构建，解析内核为 `src/scene/environment_query.py`）正式确立为 Task 6G-D（多表面接触自适应）、Task 6H（全身平衡与动量控制）及 Task 7A（复杂地形与多接触运动生成）的**唯一标准基准场景 (Single Source of Truth, SSOT)**。
2. **严禁重复建造训练场 (Anti-Duplication Constraint)**：
   - 严禁任何子模块（例如斜坡步行、台阶踏步、墙体支撑、手部支撑跳跃、天花板抓握悬挂等）在代码或脚本中独立生成第二套分立场景、临时台阶或孤立障碍物。
   - 所有环境交互算法必须通过 `DynamicsEnvironmentQuery`（`src/scene/environment_query.py`）统一获取几何与法向参数，并统一部署在 `output/dynamics_playground.blend` 的 6 大标准功能区进行验证。
3. **视觉调试 Collection 隔离与环境不可变原则 (Debug Collection Isolation)**：
   - 后续动力学开发产生的任何调试几何体（例如接触法向箭头、反作用力矢量、ZMP 投影、零动量面轨迹等），必须写入独立的专用 Blender Collection（例如 `Playground_Telemetry_Debug`）。
   - **绝对严禁直接修改、移动、删除或覆盖 `Playground_Surfaces`、`Playground_Visuals` 原有 6 大区域的环境网格物体**。原始训练场几何与视觉布局属于已通过视觉验收的保护对象。
4. **真实物理遥测与严禁伪造动力学箭头 (Physical Telemetry vs Fake Decorative Visuals)**：
   - 场景中呈现的任何接触力矢量（Contact Force）、法向反作用力（Normal Reaction）、关节力矩（Joint Torques）及角动量（Angular Momentum）可视化 Empty/Mesh，其长度、方向与作用点必须**100% 绑定自物理计算模块的真实输出**（如 `ContactModel`、`WholeBodyInertia`、`DifferentialKinematics`）。
   - **绝对严禁为了视觉美观或应付验收，在场景中手工摆放、硬编码静态装饰性箭头来伪报或冒充动力学计算**。未接入计算的静态摆拍一律视为伪造。
5. **单元测试与集成验收分级复用规范 (Tiered Verification Reuse)**：
   - 算法底层的纯数学单元测试（如四元数旋转、射线求交、投影点截断），允许使用最小合成数值或独立参数运行纯 Python 测试以保证毫秒级反馈。
   - **凡涉及多表面步态、障碍自适应、力学平衡或场景集成的正式验收（`physics`、`motion`、`full` 级别），必须统一部署并运行于标准 `DynamicsPlayground` 之上**。
