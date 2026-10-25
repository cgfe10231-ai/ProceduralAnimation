# PROJECT_STATE: 项目当前真实状态

> **记录时间**：2026-10-25  
> **当前阶段**：任务 6G-D-C2-FINAL 已完成验收纠偏、全部验证通过并正式冻结（完成 73 状态 Frame 1..73 时空标准化；通过只读机器审计脚本 `tests/audit_c2_final_inspector.py` 导出 51 个 `src/` 模块、42 个 `tests/` 脚本、19 个 `run_*.py` 脚本及 18 个 `output/*.blend` 场景的真实 AST 与 Blender 5.1.1 资产清单；完整修正并交付 6 份架构冻结与验收文档，恢复 `MotionPlanner -> KinematicBridgeExecutor -> WholeBodyController` 真实生产运动学管线、精确到源码行号的依赖拓扑、严格区分当前实现与未来汇流的状态所有权矩阵、462 帧 `unified_motion_integration.blend` 真实场景参数，以及 7A–7F 与 6H 权威演进路线图；`quick` 9/9, `physics` 16/16, `--verify-docs` 全绿通过；6G-D 正式冻结并进入只读维护，严格停止等待人类指令）  

---

## 1. 状态分类一览

### [已验证]
* **任务 6G-D-C2-FINAL 文档真实性门禁、通用 AST 符号校验器与架构约束彻底冻结 (Documentation Integrity Gate)**：
  * **枚举与接口引用纠偏**：修正 `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`，明确区分离散触地事件（Touchdown Event）与持续接触生命周期状态（`ContactLifecycle`: `CANDIDATE`, `ESTABLISHED`, `RELEASED`, `BROKEN`），未向源码增加假枚举；纠偏 `ClosedLoopDynamicsCoordinator.simulate`、`DynamicsEnvironmentQuery.query_surface_at_point` 与 `KinematicBridgeExecutor` 真实几何检查；
  * **通用 AST 存在性校验器 (`tests/audit_c2_final_inspector.py`)**：通过 Python AST 解析提取全库 51 个模块的类、方法、函数、属性及 Enum 成员，构建 `CodebaseSymbolIndex` 与 Blender 资产索引，实现跨文档通用符号存在性核验；
  * **四态契约与自测试套件**：引入 `IMPLEMENTED`、`EXISTS_NOT_INTEGRATED`、`PROPOSED`、`INVALID` 四态模型；内置自测试套件覆盖 Positive、Negative、Proposed、Prose Safety 四大用例，实测零假通过、零自然语言误报；
  * **前后置十步闭环架构防漂移门禁**：在 `docs/ARCHITECTURE_CHANGE_GATE.md` 确立十步防漂移协议并在 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 强制引用；
  * **全量文档机器核验**：`tests/audit_c2_final_inspector.py --verify-docs` 100% 全绿通过 (Exit Code 0)。
* **任务 6G-D-C2-FINAL 6G 动力学最终收口、完整工程审计与通用程序化运动底座架构冻结（含 C2-FINAL 验收纠偏）**：
  * **机器可验证全库 AST 与 `.blend` 资产审计 (`tests/audit_c2_final_inspector.py`)**：
    * 编写并在 Blender 5.1.1 无头模式下执行只读审计脚本 [`tests/audit_c2_final_inspector.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/audit_c2_final_inspector.py)，导出 [`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/codebase_and_blend_audit.json) 与 [`docs/evidence/task6gd_c2a/blend_inspection_log.txt`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/blend_inspection_log.txt)；
    * 实测清点：51 个 `src/` Python 模块、42 个 `tests/` 测试脚本、19 个根目录 `run_*.py` 脚本（均 100% 纳入 Git 跟踪），以及 `output/` 下 18 个 `.blend` 场景文件（受 `.gitignore` 规则保护在本地持久化）；
    * 核实 `output/unified_motion_integration.blend` 为 462 帧连续运动整合资产（298,537 字节，`frame_start=1..frame_end=462`，27 个物体，`CharacterArmature` 19 骨骼，12 个 Action，180 条 F-Curve，80,628 个关键帧）；
    * 核实 `output/dynamics_playground.blend` 为 73 帧动力学训练场与代理遥测资产（234,436 字节，`frame_start=1..frame_end=73`，101 个物体，0 骨骼，30 个 Action，182 条 F-Curve）。
  * **时空标准化与 73 状态闭环收口 (`src/scene/dynamics_visualizer.py`, `src/scene/dynamics_visual_evidence.py`)**：
    * 72 步离散积分严格映射为 73 个物理状态（$S_0$ 至 $S_{72}$），对准 Blender 时间轴 Frame 1 至 Frame 73（$F = k + 1$）；
    * 采样时刻标准化为 $t = 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0\text{s}$（F01, F13, F25, F37, F49, F61, F73）；
    * 编码输出 73 帧连续全局运动动画 GIF (`dynamics_overview_anim.gif`，24 FPS，delay 4cs) 及综合联系表 [`docs/evidence/task6gd_c2a/contact_sheet.png`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/contact_sheet.png)。
  * **物理模型与双管线边界正式划定**：
    * 完整恢复真实生产运动学管线（Pipeline A）：`MotionPlanner` / `MotionAction` $\to$ `KinematicBridgeExecutor.execute_frame()` $\to$ `WholeBodyController.execute_frame()` $\to$ 既有 Blender Rig / IK / FK $\to$ 只读物理遥测（`rigid_link.py`, `body_kinematics.py`, `body_inertia.py`, `contact_model.py`）$\to$ `MotionState`；
    * 明确 6G-D 质心动力学管线（Pipeline B：`contact_dynamics.py`, `contact_force_solver.py`, `forward_dynamics.py`, `closed_loop_dynamics.py`, `dynamics_visualizer.py`）当前驱动 `output/dynamics_playground.blend` 中的刚体代理对象，尚未与 19 骨骼 `WholeBodyController` 管线汇流（汇流定位于未来 **Phase 7C**）。
  * **发布并机器校验五大权威架构冻结规范与综合验证报告**：
    * `docs/FOUNDATION_ASSET_AUDIT.md` (全量 51 模块、42 测试、19 入口脚本与 18 个 `.blend` 场景机器核查清单)
    * `docs/FOUNDATION_ARCHITECTURE_AUDIT.md` (Pipeline A 19 骨骼生产管线与 Pipeline B 6G-D 质心动力学管线架构及数学闭环边界)
    * `docs/FOUNDATION_DEPENDENCY_MAP.md` (含真实调用文件、被调文件、精确函数/类名与源码行号的 44 条依赖边及独立 `Future Architecture` 章节)
    * `docs/FOUNDATION_STATE_OWNERSHIP.md` (严格区分当前实际实现与未完成汇流边界的状态所有权矩阵)
    * `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md` (权威 7A $\to$ 7B $\to$ 7C $\to$ 7D $\to$ 7E $\to$ 7F $\to$ 6H 演进路线图)
    * `docs/C2_FINAL_VALIDATION.md` (Task 6G-D-C2-FINAL 综合验收与纠偏报告)
  * **机器遥测硬断言与分级回归全绿**：
    * `tests/audit_c2_final_inspector.py --verify-docs`：0 缺失路径、0 幻觉符号（Exit Code 0）；
    * Blender 求值位置误差实测 `0.00e+00 m`（门禁 $< 10^{-5}\text{ m}$）；姿态误差实测 `3.50e-07 rad`（门禁 $< 10^{-5}\text{ rad}$）；
    * S4 滑移发散 $\Delta p = 5.30\text{ m}$；S5 滚转发散 $\Delta q = 1.55\text{ rad}$ ($88.8^\circ$)，绝无目标冒充；
    * 自动化回归：`quick` (9/9 PASS)，`physics` (16/16 PASS)，历史成熟步态 100% 零退化。
  * **架构正式冻结承诺**：
    * 6G-D 正式冻结并进入维护模式，严禁自动创建 C2-B/C3/6G-E 分支；
    * 严格停止，不自动触发 Phase 7A 或 Phase 6H。
* **任务 6G-D-C2-A 自动视觉证据采集、遥测一致性审计与跨 AI 验收管线 (Task 6G-D-C2-A 补充)**：
  * **自动化多视角渲染矩阵 (`src/scene/dynamics_visual_evidence.py`, `run_generate_visual_evidence.py`)**：
    * 5 大工位配置专职正面 (Front)、侧面 (Side)、俯视 (Top) 检查相机及全局鸟瞰相机；
    * 7 级高采样关键帧（F01, F12, F24, F36, F48, F60, F72），全自动化无头生成 112 张视口静帧；
    * 自动拼接生成高对比度综合联系表 [`docs/evidence/task6gd_c2a/contact_sheet.png`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/contact_sheet.png)（含工位、视角、时间戳与状态角标）。
  * **逐帧遥测与机器防篡改审计 (`docs/evidence/task6gd_c2a/telemetry.json`, `docs/evidence/task6gd_c2a/validation_report.md`)**：
    * 逐帧对比 Blender 求值对象世界变换与积分状态：位置误差实测 `0.00e+00 m`，姿态角测地距离误差实测 `3.50e-07 rad`；
    * 反冒充实测通过：Station 4 打滑发散 $\Delta p = 5.30\text{ m}$，Station 5 滚转倾斜发散 $\Delta q = 1.55\text{ rad}$，绝无目标冒充。
  * **跨 AI 交付件与分级归档保护**：
    * Git 跟踪库入库清单：[`docs/evidence/task6gd_c2a/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/)（联系表、48 张代表性静帧、逐帧遥测 JSON、全景动画 GIF、验收报告）；
    * 本地全量证据包：`output/evidence/task6gd_c2a/task6gd_c2a_evidence_pack.zip`（24.5 MB，包含全量 112 张高清原图与交互式 Web 检查器 [`visual_player.html`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/evidence/task6gd_c2a/visual_player.html)）。
  * **回归测试全绿**：
    * 新增 `tests/verify_task6gd_visual_telemetry.py`（5/5 PASS）；
    * `quick` (9/9 PASS, 16.09s)，`physics` (16/16 PASS, 72.42s)，历史步态 100% 零退化。
* **任务 6G-D-C2-A DynamicsPlayground 真实动力学状态集成与多场景视口验证 (Task 6G-D-C2-A)**：
  * **五大物理场景全程序化状态驱动与视口布局 (`src/scene/dynamics_visualizer.py`, `output/dynamics_playground.blend`)**：
    * **Station 1 (静态支撑平衡)**：双足接触反力平衡 $m g = 686.7\text{ N}$，CoM 高度稳定在 $Z=1.0\text{ m}$（下陷 $< 10^{-5}\text{ m}$），动态绿色反力箭头严格竖直向上；
    * **Station 2 (重力自由落体)**：空中无接触悬停需求，状态按自然重力 $-9.81\text{ m/s}^2$ 自然加速下落，零接触力虚构，目标虚影悬空直观呈现跟踪偏差；
    * **Station 3 (水平加速推进)**：在库仑摩擦锥限制内产生前进剪切力（$F_x = 105\text{ N}$），质心沿 $+X$ 加速平移，反力箭头倾角严格对应合外力方向；
    * **Station 4 (摩擦不足滑移滞后)**：冰面低摩擦（$\mu=0.08$）强制截断剪切力，实际质心滞后于目标虚影 $> 2.0\text{ m}$，直观呈现打滑与失控；
    * **Station 5 (偏心接触导致旋转)**：偏心单足接触点产生滚转力矩 $\tau_x \approx -206\text{ N}\cdot\text{m}$，驱动身体姿态连续倾斜翻滚，动态角动量箭头实时延伸。
  * **视觉调试集合隔离与环境不可变原则 (ACG Section 6 遵守)**：
    * 动力学几何体（CoM 球、身体代理框、目标虚影、接触圆盘、动态力箭头、动态角动量箭头、3D 轨迹曲线、站台 3D 文本标签、检查相机）全部封装入独立集合 `Playground_Dynamics_Visualization`；
    * 原始训练场集合 `Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras` 的 45 个对象保持 100% 不变；
    * 保留 `PlaygroundOverviewCam` 为主场景相机，新增 `DynamicsInspectionCam` 供用户快速切换鸟瞰 5 个测试台；
    * 场景文件位于 `output/dynamics_playground.blend` (230,508 字节，Blender 5.1.1 直接打开播放)。
  * **平动数值积分边界审计修正 (Section VIII)**：
    * 在 `docs/C1_FINAL_AUDIT.md` 明确平动积分公式为 $v_{k+1} = v_k + a_k \Delta t$ 与 $p_{k+1} = p_k + v_k \Delta t + \frac{1}{2} a_k \Delta t^2$；
    * 澄清其对恒定加速度场具有解析无截断特性（$< 10^{-12}\text{ m}$），但在非恒定加速度场中呈现速度一阶精度，不可无条件称为两阶段二阶 Velocity Verlet；
    * 新增测试 `test_31_non_constant_acceleration_convergence_benchmark`，在非恒定正弦加速度场中实测记录一阶收敛表现（误差减半比 $\approx 2.0$）。
  * **测试验证与回归全绿**：
    * 新增 `tests/verify_task6gd_playground_dynamics.py`，纯 Python 与 Blender Headless 全绿通过（5/5 PASS）；
    * 在 `tests/test_registry.py` 注册 `playground_dynamics_states`；
    * `tests/verify_task6gd_closed_loop_dynamics.py` 扩充至 31 项测试全绿通过；
    * `quick` (9/9, 15.08s), `physics` (15/15, 70.36s), 历史动作（Walk, Run）100% 零退化。
* **任务 6G-D-C1-FINAL 数值闭环集中数学审计、步数时间解耦、正交状态语义与遥测不可变性防御 (Task 6G-D-C1-FINAL)**：
  * **DEF-001 近似解准入策略链修复 (`src/motion/closed_loop_dynamics.py`)**：
    * 在 `step_closed_loop_dynamics()` 的 `APPROXIMATE` 分支中严格连接 `allow_approximate_solutions`；
    * 确立严格优先级：`not sol.is_physically_valid` (数值失败) > `strict_solved_only` (必须拒绝) > `not allow_approximate_solutions` (严格拒绝) > 残差在 `max_allowable_*` 阈值内准入为 `SUCCESS_APPROXIMATE`；
    * 残差超限时，依据 `strict_freeze_on_infeasible` 决定冻结或以真实物理力自然演化推进 (`CONTROL_INFEASIBLE_PHYSICS_ADVANCED`)。
  * **DEF-002 步数统计与物理推进时间彻底解耦 (`src/motion/closed_loop_dynamics.py`)**：
    * 在 `ClosedLoopSimulationTrajectory` 中区分记录 `requested_steps`、`attempted_steps`、`successful_steps`、`failed_steps`、`requested_duration` 与 `actual_physical_time`；
    * 强制约束 `total_time == actual_physical_time`（基于状态实际时间戳差值），彻底杜绝拒绝推进帧导致的虚假物理时间累加。
  * **DEF-003 遥测状态四维正交解耦语义 (`src/motion/closed_loop_dynamics.py`)**：
    * 新增 4 个清晰正交的布尔状态：
      1. `is_contact_solution_physically_valid`：接触力求解是否满足物理硬约束；
      2. `is_policy_admitted`：当前步是否通过策略准入允许前向动力学积分；
      3. `is_target_satisfied`：控制目标是否完全被满足（`SUCCESS_EXACT` 或合规准入的 `SUCCESS_APPROXIMATE`）；
      4. `state_advanced`：物理状态与时间戳是否真正单步推进；
    * 保持既有 `is_physically_valid` 与 `is_control_feasible` 向后兼容。
  * **DEF-004 遥测深层不可变性与防污染防御 (`src/motion/closed_loop_dynamics.py`)**：
    * `actual_contact_forces` 在 `ClosedLoopFrameTelemetry` 中统一以只读 `MappingProxyType` 封装，杜绝调用端就地修改污染历史；
    * `ClosedLoopSimulationTrajectory.frames` 强制转为只读元组（`tuple`）；
    * `to_dict()` 与 `export_telemetry()` 返回深解耦、纯净的 JSON 可序列化结构。
  * **DEF-005 配置数值有限性与非负性门禁 (`src/motion/contact_force_solver.py`, `src/motion/closed_loop_dynamics.py`)**：
    * 在 `ContactSolverConfig`、`FeedbackGainsConfig` 与 `ClosedLoopAdmissibilityPolicy` 的 `__post_init__` 中加入统一的 `math.isfinite()`、正数和非负数门禁，非法输入立即抛出 `ValueError`。
  * **物理守恒与二阶收敛阶验证**：
    * 零重力动量守恒：自由刚体 100 步模拟中线动量误差 $< 10^{-10}\text{ kg}\cdot\text{m/s}$，角动量误差 $< 10^{-10}\text{ N}\cdot\text{m}\cdot\text{s}$；
    * 旋转动能守恒：各向异性刚体主轴自由旋转 100 步动能漂移 $< 10^{-6}\text{ J}$；
    * 静态支撑稳定性：50 步静态站立下陷 $< 10^{-5}\text{ m}$，120 步下陷 $< 5\times 10^{-3}\text{ m}$；
    * 牛顿-欧拉跨模块平衡：各模块间 $\sum \mathbf{F} = m \mathbf{a}$ 与 $\sum \boldsymbol{\tau} = \dot{\mathbf{L}}$ 匹配精度 $< 10^{-7}$；
    * 二阶步长收敛阶实测：恒定重力下 Velocity Verlet 无截断误差（$< 10^{-12}\text{ m}$），非线性陀螺旋转实测步长收敛比为 $4.05 \approx 2^2$，确证严格 $O(\Delta t^2)$ 2阶收敛。
  * **审计文档与测试验证**：
    * 撰写完整审计文档 `docs/C1_FINAL_AUDIT.md`；
    * `tests/verify_task6gd_closed_loop_dynamics.py` 扩充至 30 项测试全绿通过（纯 Python 6.88s，Blender 0.59s）；
    * 分层回归套件实测全绿：`quick` (9/9 项全部通过，15.81s), `physics` (14/14 项全部通过，67.56s)；
    * 6G-D-C1 阶段正式验收，下一里程碑锁定为 **Task 6G-D-C2: 在现有 DynamicsPlayground 中集成和验证真实动力学状态**。
* **任务 6G-D-C1-B-R1 多帧动力学闭环三维重力统一、旋转反馈陀螺耦合修正与物理不可行性解耦准入门禁 (Task 6G-D-C1-B-R1)**：
  * **完整三维重力统一计算 (`src/motion/contact_force_solver.py`, `src/motion/closed_loop_dynamics.py`)**：
    * 扩展 `ContactWrenchTarget.from_target_motion()`，支持可选传入完整三维重力加速度向量 `gravity_acceleration_world: Optional[Vec3]`；
    * 严格满足物理力学关系：$\mathbf{F}_{\text{contact\_target}} = m \mathbf{a}_{\text{target}} - m \mathbf{g} - \sum \mathbf{F}_{\text{ext}}$（$\mathbf{g}$ 为完整 Vec3）；
    * 未传入三维重力时保持既有标量 `gravity_z` 默认值与旧代码调用 100% 兼容；
    * 闭环协调器向目标接触扳手与单步前向动力学积分器统一切换为同一套 `cfg.gravity_acceleration_world`。
  * **世界系旋转反馈陀螺耦合项修正 (`src/motion/closed_loop_dynamics.py`)**：
    * 基于完整世界坐标系刚体动力学方程 $\frac{d\mathbf{L}}{dt} = I_{\text{world}} \boldsymbol{\alpha} + \boldsymbol{\omega} \times \mathbf{L}$；
    * 当存在旋转反馈目标时，将世界角加速度反馈 $\boldsymbol{\alpha}_{\text{fb}}$ 转换为力矩时计入陀螺耦合项：$\boldsymbol{\tau}_{\text{fb}} = I_{\text{world}} \boldsymbol{\alpha}_{\text{fb}} + \boldsymbol{\omega} \times \mathbf{L}$；
    * 当无旋转反馈目标（`target_orientation_quat_world is None` 且 `target_angular_velocity_world is None`）时，严格保持纯前馈角动量变化率语义不变，杜绝重复计入陀螺项；
    * 解析验证了各向同性惯量（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）、主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）以及非主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} = (60, -60, 20)\text{ N}\cdot\text{m}$）的精确解析计算。
  * **数值失败与控制物理不可行性准入门禁解耦 (`src/motion/closed_loop_dynamics.py`)**：
    * **数值失败**（非法输入、重复接触 ID、NaN、求解崩溃）：严格保全原物理状态不变（失败原子性，`state_advanced = False`，标定为 `SOLVER_INVALID_INPUT` / `SOLVER_NUMERICAL_FAILURE`）；
    * **控制目标物理不可行但真实外力确定**（如空中无接触却要求悬停）：不虚构接触反力，以真实物理力（重力 + 零接触力）推进前向积分（`state_advanced = True`，标定为 `CONTROL_INFEASIBLE_PHYSICS_ADVANCED`），角色在重力下自然加速坠落；
    * **接触力无法证明有效**（如地面要求拉扯负支撑力）：不得直接积分，严格中止推进（`REJECTED_INFEASIBLE`）；
    * 在 `ClosedLoopAdmissibilityPolicy` 中提供 `strict_freeze_on_infeasible: bool = False` 作为严格冻结可选配置；
    * 在 `ClosedLoopFrameTelemetry` 中新增 `is_control_feasible: bool` 显式区分控制可行性与物理推进。
  * **接触几何多帧边界界定**：
    * 在代码与模块文档中明确：`ContactConstraintSpec` 为单帧即时输入，多帧模拟严禁假设接触点永久静态有效；后续 Task 6G-D-C2 须接入环境查询与接触模型进行动态更新。
  * **测试验证与回归全绿**：
    * `tests/verify_task6gd_closed_loop_dynamics.py` 扩充至 20 项测试全绿通过（纯 Python 6.50s，Blender 0.48s）：包含 3D 重力一致性检验、各向同性/主轴/非主轴陀螺力矩解析检验、纯前馈角动量保真、陀螺力矩维持稳态自旋无进动、空中悬停自然重力坠落检验、严格冻结选项检验；
    * 分层回归套件实测全绿：`quick` (9/9 项全部通过，15.09s), `physics` (14/14 项全部通过，66.27s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-C1-B 多帧动力学闭环控制与状态反馈 (Task 6G-D-C1-B)**：
  * **真实物理因果闭环协调链路 (`src/motion/closed_loop_dynamics.py`)**：
    * 建立纯 Python 多帧动力学闭环计算链：当前实际状态 $\to$ 目标运动参考与反馈控制 $\to$ 目标接触扳手 $\to$ 接触力求解器优化分配 $\to$ 准入门禁判决 $\to$ 真实分配外力前向动力学单步积分 $\to$ 新实际状态 $\to$ 逐帧遥测与跟踪误差度量；
    * 绝对禁止将目标速度、目标加速度或目标角动量直接覆盖为实际物理状态，质心轨迹与身体姿态 100% 由 6-DOF 刚体牛顿-欧拉方程经接触反力积分演化推进；
    * 严格遵循帧间递推关系：第 $k+1$ 帧状态必须以第 $k$ 帧前向动力学积分实际产生的状态作为唯一初始状态推进。
  * **基于自然倒立摆阻尼特性的反馈控制与数值饱和边界**：
    * 独立定义 `DesiredMotionReference`，包含目标质心位置/速度/前馈加速度、目标姿态四元数/角速度/前馈力矩与外部扰动；
    * 根据人体自然倒立摆频率 $\omega_0 = \sqrt{g/h} \approx 3.13\text{ rad/s}$ 设定临界阻尼增益（$k_p = 16.0, k_d = 6.0, k_{\text{rot},p} = 25.0, k_{\text{rot},d} = 8.0$）；
    * 姿态跟踪基于 Hamilton 四元数乘积求取相对旋转差 $\Delta q = q_{\text{tgt}} \otimes q_{\text{curr}}^{-1}$，并通过 $SO(3)$ 李代数对数映射解析提取三维角误差向量 $\mathbf{e}_{\text{rot}} = \log(\Delta q) = \frac{\theta}{\sin(\theta/2)} \mathbf{v}$；
    * 指令加速度与指令角动量变化率施加物理饱和边界截断（$\|a_{\text{cmd}}\| \le a_{\max}$），杜绝初始突变引发巨大非物理力矩。
  * **严格的接触力求解结果准入门禁与残差防伪造策略 (`ClosedLoopAdmissibilityPolicy`)**：
    * 明确区分 6 类执行结果：`SUCCESS_EXACT`、`SUCCESS_APPROXIMATE`、`REJECTED_INFEASIBLE`、`REJECTED_APPROXIMATE`、`SOLVER_INVALID_INPUT` 与 `SOLVER_NUMERICAL_FAILURE`；
    * 对 `APPROXIMATE` 状态：仅在满足物理硬约束（法向推力 $F_n \ge 0$、3D 摩擦锥 $\|\mathbf{F}_t\| \le \mu F_n$）且残差未超阈值时准入并如实报告残差与跟踪误差，绝不伪装为精确成功；
    * 无法安全推进时（不可行或数值失败），严格保持上一帧实际状态不修改（保障失败原子性），并输出可诊断遥测。
  * **可观测全量逐帧遥测与序列化 (`ClosedLoopFrameTelemetry`, `ClosedLoopSimulationTrajectory`)**：
    * 逐帧记录时间、当前/下一状态、指令控制量、目标扳手、接触求解状态与残差、各点实际力、实际合力/力矩/加速度、位置/速度/加速度跟踪误差；
    * 提供 `to_dict()` 与 `export_telemetry()`，为后续在 Blender 视口中驱动力学箭头与动态遥测提供权威数据源。
  * **测试验证与回归全绿**：
    * `tests/verify_task6gd_closed_loop_dynamics.py` 12 项场景测试全绿通过（纯 Python 6.07s，Blender 0.61s）：
      1. 静止支撑平衡：双足支撑抵消重力，CoM 高度稳定在 1.0m（沉降 $< 0.5\text{ mm}$）；
      2. 水平加速：在摩擦力允许下产生精确水平加速度（$a_x = 2.0\text{ m/s}^2$），纵向错步支撑基底精确平衡俯仰力矩；
      3. 摩擦不足钳位：在冰面（$\mu=0.05$）上受力被摩擦锥刚性限制，真实报告跟踪误差，绝不伪造受力；
      4. 无接触自由落体：空中零触点下按纯重力积分抛体运动，水平速度严格守恒；
      5. 偏心接触力矩：偏心作用点产生滚转力矩并驱动姿态与角动量更新；
      6. 多帧反馈跟踪：闭环自适应调整加速度驱动质心平滑跟踪目标轨迹；
      7. 不可行目标拒绝：拒绝向下拉扯地表的拉力需求，保全原状态；
      8. 求解失败原子性：非法输入安全熔断，输入状态零污染；
      9. 确定性复现：两次独立仿真 30 帧全部物理状态 100% 位级一致；
      10. 长程连续模拟稳定性：120 帧（5.0s）持续模拟全部数值有限、四元数保模、高度稳定；
      11. 遥测序列化与诊断完整性检验；
      12. 李代数四元数对数旋转误差向量精度检验。
    * 分层回归套件实测全绿：`quick` (9/9 项全部通过，14.52s), `physics` (14/14 项全部通过，68.29s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-C1-A-R1 前向动力学状态不可变性防御性复制与非各向同性刚体二阶中点姿态积分修正 (Task 6G-D-C1-A-R1)**：
  * **三维空间向量与四元数严格维度与有限性门禁 (`src/motion/forward_dynamics.py`)**：
    * 新增 `_validate_vec3(v, name)` 与 `_validate_quat(q, name)`，强制检查向量分量个数必须恰好为 3、四元数分量个数必须恰好为 4（严禁截断或不足容忍）；
    * 强制所有数值元素必须为有限实数（`math.isfinite`），彻底杜绝 NaN/Inf 渗透；四元数严格非退化并归一化；
    * 校验通过后，通过 `object.__setattr__` 将所有空间向量与集合字段强制转为全新的不可变浮点元组（`tuple`）。
  * **序列集合防御性深浅拷贝与防污染隔离**：
    * `ForwardDynamicsState`：内部 `com_position_world`, `com_velocity_world`, `angular_momentum_about_com_world`, `orientation_quat_world` 全面转换为不可变元组，外部调用方即使就地修改原 list 也不影响状态；
    * `ContactForcePoint`：`contact_point_world`, `contact_force_world` 强制防御性转换为 float 元组；
    * `ForwardDynamicsStepInput`：对 `external_forces_world`, `external_torques_about_com_world`, `contact_forces`, `gravity_acceleration_world` 进行全面防御性复制，杜绝通过外部 list 修改已构建的步进输入；
    * `ForwardDynamicsStepResult`：全部输出向量属性统一防御性标准化为 float 元组；
    * 严格保证失败原子性：单步积分异常或失败时，返回的 `state_next` 为原输入 `state` 的完全未修改引用。
  * **真正的 2-Stage 中点姿态与角动力学积分流程 (`src/motion/forward_dynamics.py`)**：
    * 修复既往在求解中点角速度时直接复用当前姿态惯性矩阵 $I_{\text{world}, k}$ 的问题；
    * 引入完整的 2-Stage 中点积分流程：
      1. $\boldsymbol{\omega}_k = I_{\text{world}, k}^{-1} \mathbf{L}_k$；
      2. $\theta_{\text{half}} = \|\boldsymbol{\omega}_k\| \frac{\Delta t}{2}$，$\Delta q_{\text{half}} = \exp(\frac{1}{2} \boldsymbol{\omega}_k \frac{\Delta t}{2})$，$q_{\text{half}} = \text{normalize}(\Delta q_{\text{half}} \otimes q_k)$；
      3. $R_{\text{half}} = R(q_{\text{half}})$，$I_{\text{world, half}} = I_{\text{body}}.\text{rotate}(R_{\text{half}})$ 并验证正定性；
      4. $\mathbf{L}_{\text{half}} = \mathbf{L}_k + \frac{1}{2} \boldsymbol{\tau}_{\text{net}} \Delta t$；
      5. $\boldsymbol{\omega}_{\text{mid}} = I_{\text{world, half}}^{-1} \mathbf{L}_{\text{half}}$；
      6. $\theta_{\text{full}} = \|\boldsymbol{\omega}_{\text{mid}}\| \Delta t$，$\Delta q_{\text{full}} = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$，$q_{k+1} = \text{normalize}(\Delta q_{\text{full}} \otimes q_k)$；
      7. $\mathbf{L}_{k+1} = \mathbf{L}_k + \boldsymbol{\tau}_{\text{net}} \Delta t$，$I_{\text{world}, k+1} = I_{\text{body}}.\text{rotate}(R(q_{k+1}))$，$\boldsymbol{\omega}_{k+1} = I_{\text{world}, k+1}^{-1} \mathbf{L}_{k+1}$；
    * 完美解决了非各向同性刚体（$I_{xx} \ne I_{yy} \ne I_{zz}$）在旋转过程中的惯性协变张量更新与角动量-能量几何保持。
  * **测试验证与回归全绿**：
    * `tests/verify_task6gd_forward_dynamics.py` 扩充至 22 项测试（新增 Test 18 至 Test 22，全部通过，耗时 0.009s）；
    * Blender Headless 5.1 单测全绿通过（22/22）；
    * 分层回归套件实测全绿：`quick` (8/8 项通过，7.82s), `physics` (13/13 项通过，59.40s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-C1-A 前向动力学单步积分内核与刚体物理状态解耦 (Task 6G-D-C1-A)**：
  * **接触力求解器输入重复 contact_id 拒绝契约 (`src/motion/contact_force_solver.py`)**：
    * `solve_contact_forces` 输入校验增加唯一性检查，发现重复 ID 一票否决返回 `ContactSolverStatus.INVALID_INPUT`；
    * `solution_to_multi_contact_dynamics` 同步强制唯一性校验，杜绝字典覆盖；
    * `tests/verify_task6gd_contact_force_solver.py` 扩充至 38 项测试全绿通过。
  * **纯数学单步前向动力学内核实现 (`src/motion/forward_dynamics.py`)**：
    * 100% 独立纯 Python / 零 `bpy` 依赖架构，不可变（frozen）状态容器保障失败原子性；
    * 显式定义世界坐标系约定（+Z Up, Ground Z=0.0m）及 SI 单位制；
    * 姿态四元数采用 Hamilton `(w, x, y, z)` 主动旋转约定（$\mathbf{v}_{\text{world}} = R(q) \mathbf{v}_{\text{body}}$）；
    * 严格区分刚体局部惯性张量 $I_{\text{body}}$（旋转不变量）与世界坐标系惯性张量 $I_{\text{world}} = R(q) I_{\text{body}} R(q)^T$；
    * 质心线运动采用 Velocity Verlet 解析积分，角动量通过外力矩冲量更新，姿态通过中点角速度指数映射 $\Delta q = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$ 精确更新；
    * 惯性张量正定性与良态检查采用 Sylvester 充要准则，奇异张量安全熔断返回 `SINGULAR_INERTIA`；
    * 实际物理状态与参考目标值严格分离，目标加速度与角动量变化率仅作为诊断输出。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_forward_dynamics.py` 17/17 项解析测试全部通过（0.003s）；
    * 统一注册进入 `tests/test_registry.py`，纳管至 `quick`、`physics` 与 `full` 层级；
    * 分层回归套件实测全绿：`quick` (8/8 项通过，8.07s), `physics` (13/13 项通过，60.99s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-B-R2 接触力求解器终止状态契约与优化收敛真值解耦 (Task 6G-D-B-R2)**：
  * **严格的 `SOLVED` 五重充要条件准入准则 (`src/motion/contact_force_solver.py`)**：
    * 废除提前非成功终止下若残差巧合达标误报 `SOLVED` 的漏洞；
    * `SOLVED` 必须满足：(1) 最终接触力全有限数值（无 NaN/Inf）；(2) 硬物理约束在配置容差内满足；(3) 合力残差 $\le$ `force_tolerance_n`；(4) 合力矩残差 $\le$ `torque_tolerance_nm`；(5) 优化器明确确认正常收敛（`opt_converged=True`）或属于显式单独验证的零触点零外力解析平衡路径（`solver_engine="analytical"`）；
    * 当优化器未收敛（`opt_converged=False`）时，哪怕残差满足容差，一律如实标定为 `APPROXIMATE`，严禁伪报 `SOLVED`；保全候选解、真实残差、`optimizer_converged=False` 与诊断信息 `optimizer_message`。
  * **SLSQP 非成功结果回退到 SPG 契约 (`enable_fallback=True`)**：
    * 支持配置 `enable_fallback: bool = True`；
    * 当 SLSQP 抛出异常或返回 `res.success == False` 时，均自动触发回退到 Native SPG，置 `fallback_occurred=True`，更新 `solver_engine="spg"`；
    * 记录触发回退的根本原因（原 SLSQP 报错信息与返回码），追加 SPG 最终状态；总迭代次数累计两阶段迭代（`slsqp_iters + spg_iters`）；
    * 若 SPG 同样未确认收敛，严格返回 `APPROXIMATE`，绝不虚报 `SOLVED`；若关闭回退（`enable_fallback=False`），如实标定未收敛并返回 `APPROXIMATE`。
  * **非数值（NaN/Inf）与异常防御性截断**：
    * 在装配解向量、计算残差与评估约束违规量各阶段均加入 `math.isfinite` 严格检验；
    * 任何出现非数值（NaN/Inf）或优化引擎异常中断的情形，一票否决直接标定为 `NUMERICAL_FAILURE`，`is_physically_valid=False`，坚决杜绝非数值被残差比较静默吸纳。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_contact_force_solver.py` 扩充至 37 项测试（新增 Test 32 至 Test 37）；独立 Python 全量环境 37/37 项测试全部通过（0.414s）；Blender 无 SciPy 无头环境 36/36 项测试全部通过（1 项 SLSQP 测试优雅跳过，0.086s）；
    * 分层回归套件实测全绿：`quick` (7/7 项通过，7.35s), `physics` (12/12 项通过，60.23s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-B-R1 接触力求解器数值可靠性与状态契约修复 (Task 6G-D-B-R1)**：
  * **有界三维摩擦锥精确欧几里得投影重构 (`project_to_friction_cone`)**：
    * 消除原先有限最大法向力下切向力等比例缩小导致的偏离反例（$F=(1,0,10), n=(0,0,1), \mu=0.5, \max=5$ 精确正交投影为 $(1,0,5)$，距离为 5.0，优于缩放点 $(0.5,0,5)$ 的 5.025）；
    * 构建母线、上法向盖、下法向盖、底轴 4 组闭式投影候选点，通过欧几里得距离解析极小化确保全局最优性；
    * 严格保证 $\mu=0$、内部点不变性、幂等性 $P(P(F))=P(F)$ 与切向方向保真。
  * **求解状态机与底层优化诊断透传 (`ContactForceSolution`)**：
    * 新增 `solver_engine`, `optimizer_converged`, `optimizer_message`, `fallback_occurred` 诊断字段；
    * 独立评估物理约束可行性与外力残差，严禁仅凭优化器 `success=True` 虚报 `SOLVED`，达到迭代上限明确标定 `APPROXIMATE` 并报告实际迭代；
    * 记录 SLSQP 到 SPG 的容错回退机制（`fallback_occurred=True`）。
  * **收紧不可行性预判 (`_check_a_priori_infeasibility`)**：
    * 废除 `normal_z > 0.5` 启发式规则，仅对严格水平地表（法向均为 $(0,0,1)$）且拉力为负、或无触点且目标非零等可证明场景报 `INFEASIBLE`；倾斜斜坡（含高摩擦负 $Z$ 切向推力）交由优化器真实求解。
  * **真实接触几何间隙保真 (`ContactConstraintSpec`, `SingleContactDynamics`)**：
    * 扩展 `surface_distance: Optional[float] = None` 与 `is_in_contact_override`；
    * 存在环境测量时 100% 传递真实有符号净距，无测量时明确标记为未知（`None`），严禁凭空构造伪数值（如 $0.05\text{ m}$）。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_contact_force_solver.py` 扩充至 31 项测试（新增 Test 18 至 Test 31）；独立 Python 全量环境 31/31 项测试全部通过（0.406s）；Blender 无 SciPy 无头环境 30/30 项测试全部通过（1 项 SLSQP 测试优雅跳过，0.087s）；
    * 分层回归套件实测全绿：`quick` (7/7 项通过，7.13s), `physics` (12/12 项通过，62.09s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-B 多接触力逆向求解与约束分配系统 (Task 6G-D-B)**：
  * **多接触力分配数学与优化架构 (`src/motion/contact_force_solver.py`)**：
    * 建立线性接触抓取映射矩阵 $\mathbf{A} \mathbf{f} = \mathbf{w}$（$\mathbf{A} \in \mathbb{R}^{6 \times 3N}$），包含力平衡单位块 $\mathbf{I}_3$ 与绕质心力矩叉乘斜对称矩阵块 $[\mathbf{r}_i]_\times$；
    * 实现基于任意接触法向 $\hat{\mathbf{n}}$ 的精确 3D 圆形库仑摩擦锥闭式欧几里得正交投影算法 `project_to_friction_cone`，杜绝八棱锥线性多面体近似带来的方向偏置；
    * 双引擎优化架构：支持 SciPy SLSQP（高精度二阶锥非线性规划）与原生 SPG（谱投影梯度动力学，Barzilai-Borwein 自适应步长，零外部依赖，100% 兼容 Blender 内置 Python）；
    * 状态机与物理残差判定：定义 `ContactSolverStatus`（`SOLVED`, `APPROXIMATE`, `INFEASIBLE`, `INVALID_INPUT`, `NUMERICAL_FAILURE`），输出力残差范数 (N)、力矩残差范数 (N·m) 及法向/切向约束违规值；
    * 物理反向到正向桥接：实现 `solution_to_multi_contact_dynamics()`，将分配力转化为标准 `MultiContactDynamics` 进行双向物理验算；
    * 环境与训练场绑定：实现 `create_contact_constraint_from_environment()`，无缝支持 `DynamicsPlayground` 几何与摩擦参数抽取。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_contact_force_solver.py` 17/17 项严苛数学定理纯 Python 全绿通过（耗时 0.403s）；
    * 注册进入 `tests/test_registry.py`，纳管至 `quick`、`physics` 与 `full` 层级；
    * 分层回归套件实测全绿：`quick` (7/7 项通过，7.11s), `physics` (12/12 项通过，59.77s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-A-R2 MultiContactDynamics 时间步长更新原子性与状态不可变保全 (Task 6G-D-A-R2)**：
  * **失败原子性与预校验门禁重构 (`src/motion/contact_dynamics.py`)**：
    * 引入 `_validate_dt_value()`，在修改任何状态前强行校验 `new_dt` 数值合法性（有限正浮点数，严格拦截 0、负数、NaN、Inf 与非法类型）；
    * `update_contacts=False` 模式：先遍历检查全部子接触点与新 `dt` 的一致性，一旦失配立即抛错，系统 `self.dt` 与触点 `c.dt` 绝对不发生修改，彻底解决先改后抛破坏一致性的隐患；
    * `update_contacts=True` 模式：建立快照并提供事务回滚机制，若中途任何触点抛出异常，自动恢复所有触点与系统 `dt` 至调用前快照，杜绝“部分更新”中间态；
    * 空系统（`len(contacts) == 0`）：支持合法重设 `dt`，非法值拒绝且系统 `dt` 保持不变；
    * `SingleContactDynamics` 引入 `__setattr__` 动态防御，防止非正或非有限 `dt` 注入。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_contact_dynamics.py` 扩充 Test 18（覆盖 10 项严苛失败原子性与状态不变性定理），完善 Test 16 状态断言；18/18 项数学与契约定理纯 Python 全绿通过（耗时 0.002s）；
    * 分层回归套件实测全绿：`quick` (6/6 项通过，5.36s), `physics` (11/11 项通过，57.83s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-A-R1 接触动力学时间步长一致性与物理接触有效性契约修复 (Task 6G-D-A-R1)**：
  * **多触点统一时间步长所有权与强一致性门禁 (`src/motion/contact_dynamics.py`)**：
    * `MultiContactDynamics` 确立对系统时间步长 `dt` 的唯一所有权；
    * 构造器 `__post_init__` 与 `add_contact()` 中强行执行 `_validate_contact_dt(contact)`；
    * 若触点 `contact.dt` 与系统 `self.dt` 差异大于 `1e-6`，严格抛出 `ValueError` 并拒绝加入，杜绝静默采用或覆盖；
    * 新增 `set_dt(new_dt, update_contacts=False)`，提供显式批量同步通道。
  * **物理接触有效性与几何贴靠显式分离 (`src/motion/contact_dynamics.py`)**：
    * `SingleContactDynamics` 扩展 `surface_id: str`、`surface_distance: float`（来自查询的 `signed_distance`）以及 `contact_tolerance: float = 0.02`（默认 20mm 物理接触间隙容差）；
    * 定义只读属性 `is_in_contact: bool`（当且仅当 `abs(surface_distance) <= contact_tolerance` 时为真）；
    * 新增非接触受力违规状态 `FrictionConeStatus.NON_CONTACT_FORCE_VIOLATION`；
    * 更新 `evaluate_friction_constraint()`：当 `not is_in_contact` 且施加了非零接触力（$\|\mathbf{F}\| > \epsilon$）时，严禁判定为有效接触力，直接返回 `is_valid=False` 并附带详细违规诊断；若接触力为零则判定为 `SEPARATED`。
  * **环境查询接触构造契约升级 (`create_contact_dynamics_from_environment`)**：
    * 引入 `contact_tolerance: float = 0.02` 与 `require_contact: bool = True` 参数；
    * 默认 `require_contact=True`：当查询点的 `signed_distance` 超过容差时，严格抛出 `ValueError` 拦截非物理悬空接触创建；
    * 允许 `require_contact=False`：用于纯几何邻域探测或近地状态追踪，将地表几何参数与有符号净距绑定至触点，同时保持 `is_in_contact=False` 防止非法受力。
  * **单元验证与统一注册全绿**：
    * `tests/verify_task6gd_contact_dynamics.py` 扩充 Test 16 与 Test 17，17/17 项数学与契约定理纯 Python 全绿通过（耗时 0.001s）；
    * 分层回归套件实测全绿：`quick` (6/6 项通过，5.3s), `physics` (11/11 项通过，57.84s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-A 接触动力学基础与冲量动量系统 (Task 6G-D-A)**：
  * **纯数学接触动力学计算模块就绪 (`src/motion/contact_dynamics.py`)**：
    * 建立 `SingleContactDynamics` 数据结构，封装世界空间接触点 $\mathbf{p}_c$、接触力 $\mathbf{F}$、质心相对位矢 $\mathbf{r} = \mathbf{p}_c - \mathbf{p}_{\text{com}}$；
    * 严格遵循右手定则计算绕质心力矩 $\boldsymbol{\tau}_{\text{com}} = \mathbf{r} \times \mathbf{F}$（$\text{N}\cdot\text{m}$），严谨区分绕世界原点力矩 $\boldsymbol{\tau}_{\text{origin}} = \mathbf{p}_c \times \mathbf{F}$；
    * 实现线冲量 $\mathbf{J} = \mathbf{F}\Delta t$（$\text{N}\cdot\text{s}$）与角冲量 $\mathbf{H}_{\text{impulse}} = \boldsymbol{\tau}_{\text{com}}\Delta t$（$\text{N}\cdot\text{m}\cdot\text{s}$），严格等价于线动量变化 $\Delta \mathbf{P}$ 与角动量变化 $\Delta \mathbf{L}_{\text{com}}$；
    * 解析证明并实测验证 6 大数学定理：零力零动量变化、质心作用力零力矩、偏心力右手定则力矩、世界坐标平移不变性、$\mathrm{SO}(3)$ 刚体旋转协变性、冲量-动量等价性。
  * **单侧正向与库仑摩擦锥约束评估就绪 (`FrictionConstraintEvaluation`)**：
    * 正交分解接触力为法向力 $\mathbf{F}_n = (\mathbf{F} \cdot \hat{\mathbf{n}})\hat{\mathbf{n}}$ 与切向摩擦力 $\mathbf{F}_t = \mathbf{F} - \mathbf{F}_n$；
    * 单侧非粘附约束检查：$F_n \ge 0$，负法向拉力严谨标记为 `TENSION_VIOLATION`；
    * 库仑摩擦锥检查：$\|\mathbf{F}_t\| \le \mu F_n$，计算摩擦余量 $m = \mu F_n - \|\mathbf{F}_t\|$，严谨分类 `STICK`、`SLIP_LIMIT` 与 `SLIP_VIOLATION`。
  * **多接触点动力学聚合就绪 (`MultiContactDynamics`)**：
    * 聚合多接触点合外力 $\sum \mathbf{F}_i$、合外力矩 $\sum \mathbf{r}_i \times \mathbf{F}_i$、总线冲量、总角冲量与净动量变化；
    * 提供多接触点摩擦锥完备性判据 `is_all_friction_valid`。
  * **标准训练场环境查询接口契约绑定 (`create_contact_dynamics_from_environment`)**：
    * 100% 绑定 `DynamicsEnvironmentQuery`（`src/scene/environment_query.py`），从标准训练场（平地、斜坡、垂直墙）真实提取外向法线 $\hat{\mathbf{n}}$ 与摩擦系数 $\mu$；
    * 真实测试平地（$\mu=0.70$）、斜坡（$\mu=0.65$）、垂直墙（$\mu=0.60$）的正反向合法与非法接触，严禁私造孤立训练场，严禁手工摆设伪造装饰箭头。
  * **单元验证与统一注册全绿**：
    * 纯 Python 几何测试 `tests/verify_task6gd_contact_dynamics.py` 15/15 项数学与契约定理全绿通过（0.001s）；
    * 注册进入 `tests/test_registry.py`，纳管至 `quick`、`physics` 与 `full` 层级；
    * 分层回归套件实测全绿：`quick` (6/6 项通过，8.13s), `physics` (11/11 项通过，56.09s), `motion` (5/5 项通过，15.29s), `dynamics_playground_blend` (1/1 项通过，1.28s)；
    * 0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。
* **任务 6G-D-PRE-P2-R1 环境查询过滤修复、距离语义统一与动力学训练场单一 SSOT 门禁 (Task 6G-D-PRE-P2-R1)**：
  * **查询过滤与默认地面强隔离已修复 (`src/scene/environment_query.py`)**：
    * 修复点查询与空间查询中默认全局地面无条件作为候选的逻辑缺陷；
    * 仅当 `surface_type_filter in (None, "", "horizontal_ground")` 时才允许评估全局地面；过滤垂直墙或斜坡等非平地类型时严格隔离默认地面，未命中时严谨返回 `success=False`、`surface_id="none"` 与明确错误原因。
  * **物理距离语义严格解耦 (`ray_hit_distance` vs `signed_distance`)**：
    * `SurfaceQueryResult` 引入 `ray_hit_distance: Optional[float] = None` 字段；
    * `signed_distance` 严格锁定为法向有符号距离（>0 间隙，0.0 表面，<0 穿透）；
    * `ray_hit_distance` 严格锁定为沿射线方向行进的欧几里得距离（>=0.0m）；非射线点查询时为 `None`，射线未命中时严格为 `float("inf")`；
    * 彻底解耦斜向射线行进距离（斜边）与垂直平面的法向有符号净距。
  * **动力学训练场单一 SSOT 权威门禁与十大绝对清规**：
    * 在 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md) 增订第 6 节《标准动力学训练场基准场景复用与可视化门禁》；
    * 确立 `output/dynamics_playground.blend` 为 6G-D、6H 与 7A 单一基准场景（SSOT）；严禁子模块私造重复分立场景；环境基础网格严格只读不可变；
    * 颁布防伪门禁：动力学遥测箭头必须 100% 绑定真实物理计算输出，严禁手工摆设伪造箭头；
    * 同步修订 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md` 第 8 节，确立十大绝对清规。
  * **单元测试与分层回归全绿**：
    * `tests/verify_task6gd_dynamics_playground.py` 扩充 `test_12_surface_type_filter_strictness` 与 `test_13_ray_query_distance_semantics`，13/13 项纯 Python 数学断言全绿通过（0.001s）；
    * `quick` Tier：5/5 全绿通过（5.11s，退出码 0）；
    * `motion` Tier：5/5 全绿通过（15.81s，退出码 0），历史步态 100% 零退化；
    * `dynamics_playground_blend`：45 个场景对象结构完整性通过（1.31s，退出码 0）；
    * 0 生产运动代码修改，0 步态曲线变动，0 场景重复构建，严格停止。
* **任务 6G-D-PRE-P2 可视化动力学训练场与统一环境查询基础 (Task 6G-D-PRE-P2)**：
  * **纯 Python 解析几何与环境查询系统就绪 (`src/scene/environment_query.py`)**：
    * 建立 `OrientedSurface` 统一闭式表面模型，严格涵盖中心、单位外向法线、切向基底、半尺寸、摩擦系数与支撑属性；
    * 构建 `DynamicsEnvironmentQuery`，支持平坦地面、5级标准台阶、上下连续斜坡、垂直障碍墙、跳箱高台、单杠与调试区 6 大功能分区（共 21 个解析几何表面）；
    * 支持闭式法线、最近投影点、有符号距离（Signed Distance，间隙 >0，穿透 <0）、摩擦系数及普通支撑可行性判断；
    * 针对无法用 $(x, y)$ 高度场表示的垂直立面提供 `query_surface_at_point` 与 `query_spatial_surface` 空间三维查询接口；
    * 对原有 `EnvironmentQuery` 保持 100% 向后兼容性（`ground_height_at` 与 `surface_normal_at` 契约完全无损）。
  * **程序化训练场场景生成器就绪 (`src/scene/builder.py` / `run_dynamics_playground.py`)**：
    * 实现 `build_dynamics_playground`，在 Blender 中根据解析几何生成真实实体网格；
    * 赋予区分明显的材质颜色（平地灰色、台阶天蓝色、斜坡金橙色、墙面砖红色、跳箱紫色、单杠钢青色、调试区明黄色）；
    * 为 21 个表面生成直观的外向法线指示箭头（`NormalArrow_<surface_id>`）；
    * 配备世界坐标轴指示（红X、绿Y、蓝Z）、1m 参考单位立方体、双视角调试摄像机（`PlaygroundOverviewCam`, `PlaygroundCloseUpCam`）与三点日光照明系统；
    * 导出生成可直接在 Blender 中打开检查的场景文件 `output/dynamics_playground.blend`（116,933 字节，保存在本地磁盘受 `.gitignore` 保护）。
  * **单元验证与统一注册全绿**：
    * 纯 Python 几何测试 `tests/verify_task6gd_dynamics_playground.py` 11/11 项数学定理全绿通过（0.12s）；
    * Blender 场景检验脚本 `tests/verify_task6gd_playground_blend.py` 45 个对象与材质完整性全量通过（1.29s）；
    * 注册进入 `tests/test_registry.py`，纳管至 `quick`、`physics` 与 `full` 层级；
    * 分层回归套件验证保持 100% 零退化：`quick` (5/5), `physics` (10/10), `motion` (5/5) 全部通过（退出码 0）。
  * **执行纪律遵守**：0 生产运动代码修改，0 步态曲线变动，0 历史文件删除，严格停止。
* **任务 6G-D-PRE-P1-R1 统一测试运行器严格验收修复与单元测试落地 (Task 6G-D-PRE-P1-R1)**：
  * **根除 SKIPPED 虚假成功风险**：
    * `TestDefinition` 引入 `is_optional: bool = False`，所有必需测试遇到依赖缺失、脚本缺失或配置错误时一律判定为 `status="FAILED"`（退出码 -1），绝不伪报 `SKIPPED`；
    * 运行器汇报中只要存在未标记为可选的跳过测试（`required_skipped_count > 0`），整体即判定为不成功，最终退出码返回 1。
  * **健全 fail-fast 报告完整性与 `NOT_RUN` 追踪**：
    * 当 `--fail-fast` 在首个测试失败停机时，自动将后续剩余全部待测用例追加为 `status="NOT_RUN"`（`exit_code=None`, `duration_sec=0.0`）；
    * 报告（JSON 与 Markdown）完整呈现 `total_planned`、`total_executed` 与 `not_run_count`；
    * `NOT_RUN` 严格不计入 `passed_count`，且导致整体退出码为 1。
  * **强制执行期望产物校验 (`expected_artifacts`)**：
    * 在测试进程正常退出（exit 0）且输出无异常后，自动深度检验 `test.expected_artifacts`；
    * 任何声明的产物若不存在或文件大小为 0 字节，直接判定为 `status="FAILED"`；
    * 为 `integration_unified_motion` 及 11 项历史 Blend 验证用例补齐 `expected_artifacts`。
  * **交付专用纯 Python 单元测试套件 (`tests/test_runner_unit.py`)**：
    * 覆盖 10 项核心机制：正常通过、非零退出码、stdout 模式反查、必需 vs 可选缺失、期望产物缺失/0字节、硬超时与进程树终止、fail-fast 停机、NOT_RUN 报告追踪、all_success 状态矩阵逻辑、最终退出码判定；
    * 10/10 单元测试全绿通过，耗时 0.94s。
  * **分层回归测试验证全绿**：
    * `quick` Tier：4/4 项通过（耗时 4.85s，退出码 0）；
    * `motion` Tier：5/5 项通过（耗时 15.35s，退出码 0），其中 `integration_unified_motion` 严格标定为 `AUTOMATED_PASS (Visual Inspection Required)`；
    * `physics` Tier：8/8 项通过（耗时 53.94s，退出码 0），历史物理模块 100% 零退化。
  * **执行纪律遵守**：0 生产代码修改，0 步态曲线变动，0 历史文件删除，严格停止。
* **任务 6G-D-PRE-P1 统一测试执行接口、回归资产管理与永久架构门禁 (Task 6G-D-PRE-P1)**：
  * **显式测试注册表就绪 (`tests/test_registry.py`)**：
    * 登记 26 项真实受控测试用例，覆盖 `quick` (3项)、`physics` (8项)、`motion` (5项)、`full` (14项去重并集) 与 `legacy` (13项)；
    * 严谨区分 `RunnerType.PYTHON`、`BLENDER_HEADLESS` 与 `BLENDER_WITH_BLEND`，配置超时限制与依赖资源；
    * 建立 `is_visual_acceptance` 标记，严格区分自动化通过与人工视口目视验收。
  * **单入口统一调度器就绪 (`tests/run_test_suite.py` / `run_tests.ps1`)**：
    * 单命令外层调度（如 `.\run_tests.ps1 -tier quick`），将 N 次子命令执行收敛为单次受控调度，彻底消除用户反复审批终端的负担；
    * 自动安全解析 Blender 5.1.1 与系统真实 Python 路径，避开 Windows Store 零字节假别名；
    * 引入 Windows 深度进程树清理机制（`taskkill /F /T /PID`），杜绝超时悬挂 Blender 僵尸进程；
    * 实施多层失败判定：非零退出码、硬超时、产物缺失以及 stdout/stderr 中的 `[FAIL]`/`AssertionError` 模式反查，严禁“伪绿”放行；
    * 结构化自动生成 `tests/output/test_report.json` 与 `test_report.md`。
  * **分层回归测试验证全绿**：
    * `quick` Tier：3/3 项通过（耗时 3.94s，退出码 0）；
    * `motion` Tier：5/5 项通过（耗时 16.16s，退出码 0），其中 `integration_unified_motion` 严格标定为 `AUTOMATED_PASS (Visual Inspection Required)`；
    * `physics` Tier：8/8 项通过（耗时 53.90s，退出码 0），底层运动学、WBC、ROM、CoM、惯性张量与桥接 14 项测试保持 100% 零退化。
  * **永久架构门禁制度确立**：
    * 交付单一权威规范来源 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md)；
    * 同步更新 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 第 8 节；
    * 确立 11 项前置准入清单与 8 大绝对清规，规范架构偏差事前审批流程。
  * **执行纪律遵守**：0 生产代码修改，0 步态曲线变动，0 历史文件删除，严格停止。
* **任务 6G-D-PRE-P0 全工程架构审计与后续开发准备 (Task 6G-D-PRE-P0)**：
  * **全工程代码与资产穿透式审计**：
    * 覆盖 `src/` 下全部 28 个 Python 源码、`tests/` 下全部 30 个测试脚本、根目录下全部 19 个运行入口以及所有项目文档；
    * 建立官方唯一合法主生产调用链：`MotionPlanner` $\to$ `MotionAction` $\to$ `KinematicBridgeExecutor` $\to$ `WholeBodyController` $\to$ `Blender Rig/IK` $\to$ 物理遥测 $\to$ `MotionState`；
    * 确立 12 大关键环节唯一所有权矩阵，确认 `WholeBodyController` 独占骨架与控制器写入权，控制器全生命周期保持 `parent = None`（世界空间）；
    * 梳理全工程资产四态分类（Active / Reusable / Legacy / Orphan），排查出 `BlenderPoseApplicator` 与 `ContactConstraintAdapter` 历史废弃类，排查出 `run_pipeline.py` 与 `src/pipeline.py` 仍滞留在 Task 3 静态场景的问题；
    * 真实核查登记关键 Blender 文件：`character_forward_walk.blend`、`character_start_stop_walk.blend` 与 `unified_motion_integration.blend` 仅保存在本地磁盘 `output/` 目录下，受 `.gitignore` 规则保护未跟踪且未推送到 GitHub。所有生成源码 100% 在 GitHub 上可完全复现；
    * 建立 13 项历史运动与物理能力防退化基线矩阵（涵盖 ForwardWalk, StartStopWalk, Run, SprintStart, SprintBrake, Leg IK, Arm IK, WBC, CoM, ROM, Kinematics, Inertia, ContactModel, Unified Motion Integration）；
    * 完成 P1 统一测试调度系统（`tests/run_test_suite.py` + `test_registry.py`，支持 `quick`/`physics`/`motion`/`full` 四级分层，单命令外层调度彻底根除用户反复审批疲劳，非零退出码绝对失败纪律）实施设计方案；
    * 完成 P2 简易动力学训练场（几何、环境查询、动力学模型与动画控制器四层严格解耦，平地、台阶、斜坡、障碍墙、跳箱平台、遥测可视化 6 大功能分区）实施设计方案；
    * 确立永久架构门禁（ACG）11 项前置准入清单与 8 大绝对禁止行为清规，规范架构偏差事前审批流程；
    * 交付 [`docs/ENGINEERING_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ENGINEERING_AUDIT.md) 权威审计报告；
    * 遵守执行纪律：0 生产代码修改，0 测试阈值放宽，0 历史文件删除，严格停止。
* **任务 6G-C-R3B-2-R1 历史正确动画对照、下肢视口故障定位与运动学修复 (Task 6G-C-R3B-2-R1)**：
  * **根因定位完成并获得数学与工程级 100% 证实**：
    1. **Blender 动画曲线父级解析空间错位（根因一）**：在首轮 R3B-2 中，`WholeBodyController.execute_frame` 的摆动相设置 `ik_obj.parent = CharacterRoot`，而支撑相设置 `ik_obj.parent = None`。因为 Blender 中 `obj.parent` 是全局对象级指针属性，**不可逐帧关键帧化（Not Keyframable）**。当保存动画文件时，`FootIK` 的父级指针被固化为 `CharacterRoot`。动画重放时，支撑相在世界坐标下写入的关键帧位置（如 $Y = -8.0\text{ m}$）被 Blender 误解析为相对于 `CharacterRoot`（$Y \approx -7.94\text{ m}$）的局部坐标，合成出世界坐标 $Y = -7.94 + (-8.0) = -15.94\text{ m}$（即向后暴拉 8 米！）。而摆动相按局部坐标写入，重放时保持在根节点附近。导致步态交替时，支撑腿被向后暴拉 8 米形成横向 L 形，摆动腿看似正常，两腿周期性交替畸变。
    2. **COPY_ROTATION 目标空间在无父级物体上的退化（根因二）**：在 `src/rig/ik.py` 中，`FootRotation.L/R` 约束原配置为 `target_space = "LOCAL", owner_space = "LOCAL"`。当 `FootIK` 控制器无父级（`parent = None`）时，Blender 约束求解器判定其局部空间为单位矩阵，导致 `foot.L/R` PoseBone 的三维旋转被强制锁定在静止姿态（$-13.13^\circ$），无法接收来自 `FootIK` 的动态俯仰指令。在奔跑与冲刺的大幅度屈膝（膝屈角达 $80^\circ \sim 98^\circ$）工况下，静止足部无法跟随小腿向后自然拖拽，导致小腿与脚掌夹角达到 $53.4^\circ$，违反解剖踝关节 ROM 极值（$45.0^\circ$）。
  * **工程级修复落地**：
    1. **下肢控制器全局恒定世界空间化 (`reparent_to_root = False`)**：在 `WholeBodyController.execute_frame` 中，强制设置 `reparent_to_root=False`，确保 `FootIK.L`、`FootIK.R`、`KneePole.L`、`KneePole.R` 在整个动画全生命周期内（支撑相与摆动相）始终保持 `parent = None`（与历史标准基准文件 `character_forward_walk.blend` 和 `character_start_stop_walk.blend` 100% 一致）；所有关键帧位置与旋转均纯粹写入绝对世界坐标系，Blender 重放时零相对位移叠加，彻底根除 8 米向后拉伸畸变与双重变换错误。
    2. **约束空间映射修正 (`target_space = "WORLD", owner_space = "LOCAL"`)**：将 `FootRotation.L/R` 约束修正为 `target_space = "WORLD", owner_space = "LOCAL"`，使得无父级的 `FootIK` 世界空间旋转能够准确传递并叠加到 `foot.L/R` 的局部解剖姿态上，彻底解决无父级物体在 LOCAL 模式下退化为单位矩阵的底层缺陷。
    3. **基于人体生物力学的摆动相踝关节平滑跟随调制**：行走摆动相 $\theta_{\text{pitch}} = -12.0^\circ \sin(\pi s)$；跑步摆动相 $\theta_{\text{pitch}} = -38.0^\circ \sin(\pi s)$；冲刺起跑摆动相 $\theta_{\text{pitch}} = -36.0^\circ \sin(\pi s)$。真实模拟人类奔跑与迈步时脚尖跟随小腿向后下方自然拖曳的生物力学特征，在不修改历史步态曲线、不放宽 `joint_limits.py` 医学解剖 ROM 约束的前提下，全 462 帧踝关节活动角严格保持在 $[-25^\circ, +45^\circ]$ 舒适区间内。
  * **定量测试与比对结果**：
    * 重新生成 `output/unified_motion_integration.blend`（462 帧无缝连续运动，总位移 12.9058m，0 次超程违规）；
    * 深入核查第 41..44 关键帧：第 42 帧（$-114.52^\circ$）与第 43 帧（$-114.84^\circ$）的小腿姿态与历史基准 `character_start_stop_walk.blend` 保持完全一致（精确至小数点后两位），`FootIK.parent` 严格为 `None`，`FootIK` 位置严格位于 $Y = -8.0000\text{ m}$，支撑踝高度严格为 $Z = 0.0700\text{ m}$；
    * 渲染输出 40 张对比视口视图（涵盖侧视与前斜视视角，覆盖第 1、12、24、36、41、42、43、44、48、60 关键帧），直观证实步态连续平滑，彻底消除周期性 L 形畸变与横向暴拉；
    * 独立四大动作验证套件（Walk 204 帧/408 帧, Run 96 帧/252 帧, SprintStart 114 帧/318 帧, SprintBrake 162 帧）及桥接 14 项测试全量 100% 全绿通过。
* **任务 6G-C-R3B-2 历史四大动作向统一 KinematicBridgeExecutor 与 WholeBodyController 架构的无损迁移 (Task 6G-C-R3B-2)**：
  * **按规范顺序依次完成四大动作无损迁移**：
    1. `StartStopWalkAction`（`src/motion/framework.py`）：迁移至 `bridge_executor.execute_frame()`，204 帧连续平滑步态、7 个协调半步、0.24 m/s 稳态峰值速度、1.2600 m 理论位移保持 100% 零退化（`tests/verify_r3b2_walk_action.py` 100% 通过）；
    2. `RunAction`（`src/motion/run_cycle.py`）：迁移至统一桥接层，96 帧跑动步态、4 个周期、40 帧真实空中腾空相、0.90 m/s 恒速前进保持 100% 零退化；在 `WholeBodyController` 中修复足部解锁重新绑定到 `CharacterRoot`（`reparent_to_root=True`），彻底杜绝踝关节局部旋转伪偏移；增加生理踝关节摆动俯仰调制（`pitch = -10.0 * sin(pi * s)`）（`tests/verify_r3b2_run_action.py` 100% 通过）；
    3. `SprintStartAction`（`src/motion/sprint_start.py`）：迁移至统一桥接层，114 帧爆发式起跑、49 帧空中腾空相、2.00 m/s 峰值速度、6.5833 m 位移保持 100% 零退化；增加冲刺摆动相踝俯仰调制（`pitch = -18.0 * sin(pi * s)`），完美契合极端屈膝屈髋下的真实解剖 ROM，0 次超程（`tests/verify_r3b2_sprint_start.py` 100% 通过）；
    4. `SprintBrakeAction`（`src/motion/sprint_brake.py`）：迁移至统一桥接层，48 帧主动急停制动、从 2.0 m/s 减速至 0.0 m/s、双脚稳态并立锁定保持 100% 零退化；增加制动踝俯仰调制（`pitch = -12.0 * sin(pi * s)`）（`tests/verify_r3b2_sprint_brake.py` 100% 通过）。
  * **三大物理核心指标与控制语义严格校验**：
    1. `MotionState` 中严格区分规划期望速度 `planned_linear_velocity`、根节点差分测量速度 `root_derived_linear_velocity` 与全身体物理质心速度 `com_linear_velocity`，绝不混淆；
    2. 接触意图 `contact_intent`、接触建立与世界坐标锁定 `is_locked` 及环境表面几何间隙合规性严格区分；
    3. 任何 IK、ROM 或接触几何超差由 `bridge_res.success` 严格真实拦截报错，严禁静默放行。
  * **直接生成可播放统一连续动画 Blender 验收文件**：
    * 运行 `run_unified_motion_pipeline.py`，完整顺序串联 `StartStopWalkAction` $\rightarrow$ `SprintStartAction` $\rightarrow$ `SprintBrakeAction` $\rightarrow$ `RunAction(cycles=4)`；
    * 产物：`output/unified_motion_integration.blend`（296,509 字节，1..462 帧连续动画，总位移 12.9058 m，0 次不可达事件）；
    * 包含完整的骨架 19 骨骼、13 占位网格、地面参考平板、视口阳光以及全程平滑跟随角色移动的 `PipelineCamera` 运镜跟踪；
    * 编写并执行专用验收脚本 `tests/verify_unified_motion_integration.py`，全量检验骨架姿态数据（无 NaN/Inf）与关键里程碑位移（误差严格 0.0000 m），100% 通过。
  * **全量回归套件保持 100% 全绿**：
    * 运行 14 项桥接层严苛套件（`tests/verify_task6gc_r3b1_bridge.py`）及 6 大历史核心测试套件（WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia），100% 全绿通过（退出码 0）。
* **任务 6G-C-R3B-1-Final 统一架构规范修订、桥接层漏洞修补与永久 GitHub 自动同步 (Task 6G-C-R3B-1-Final)**：
  * **规范修订与永久同步协议 (`ARCHITECTURE.md` v2.2, `ARCHITECTURE_SYNC.md` v2.2, `AGENTS.md`, `GEMINI.md`, `.agents/rules/project_rules.md`)**：
    * 确立 10 大架构设计原则、三层架构演进图（当前断裂点现状 -> R3B 统一桥接落地 -> 未来 6G-D/6H/7A 物理平衡闭环）；
    * 确立单帧 6 阶段执行协议表（Phase 1 规划 -> Phase 2 接触防滑锁定 -> Phase 3 WBC 统一求解 -> Phase 4 真实 ROM 校验 -> Phase 5 事后只读遥测丰富 -> Phase 6 状态提交）；
    * 梳理 12 大核心模块契约表与 6 大历史动作复用矩阵；
    * 确立永久自动化 GitHub 同步机制：每次任务完成并通过全量验证后，自动精确暂存、commit 并 `git push origin master`，校验远程与本地 HEAD 一致。
  * **最小兼容桥接层深度补全 (`src/motion/kinematic_bridge.py`)**：
    * `KinematicPlannedPose` 引入可选 `dt`，支持显式步长与时间戳自动差分推导（`dt > 0.0` 严格单调递增保护），确保有限差分速度与惯性张量物理时间缩放一致；
    * 彻底解耦手部 IK 激活与接触语义（`enabled` vs `contact_intent` vs `is_locked`），自由空间伸手抓空绝不产生伪造接触；支持结合 `ContactModel` 进行接触表面几何间隙与穿透容差合规性校验，超差真实报警 `success=False`；
    * 足部地面锚点在局部坐标上依据踝关节原点 $(x, y, z - 0.070\text{ m})$ 精准对齐地面 $Z=0$，与 `foot_contact.py` 世界锁定严格吻合，消除足底人为滑移；
    * Phase 5 姿态后处理闭环集成 `compute_whole_body_inertia`，基于已评估 Armature 姿态与速度状态计算惯性张量与自转/轨道角动量，纯只读注入 `MotionState.params`。
  * **自动化测试套件 (`tests/verify_task6gc_r3b1_bridge.py`) 14/14 项全部通过**：
    * Test 01：输入字段无损映射（100% 空间与运动学字段无损转换）；
    * Test 02：FK/IK 仲裁与手臂控制所有权（腕部追踪误差 0.041 mm）；
    * Test 03：支撑脚地面锚定保护（控制器漂移 0.000000 mm，骨骼漂移 0.246 mm）；
    * Test 04：真实 ROM 与到达性失败汇报（超限及越界严格诚实汇报 `success=False`）；
    * Test 05：定量姿态等价性（桥接与历史动作姿态在骨盆、左踝、右踝误差严格为 **0.0000 mm**）；
    * Test 06：历史步态曲线不可变性（7 步排期、0.24 m/s 稳态速度、1.26 m 总位移 100% 完整保留）；
    * Test 07：数据类型、单位与坐标系一致性（+Z Up，地面 Z=0.0，双支撑标识完全兼容）；
    * Test 08：重复写冲突杜绝（WBC 与 foot_contact 独占写所有权零冲突）；
    * Test 09：单帧 6 阶段流水线全流程执行（5 连续帧正确写入，动画关键帧生成）；
    * Test 10：Variable dt & Kinematic Scaling（0.01s 100FPS 与 0.04s 25FPS 速度换算精确吻合，非法步长与反向时间戳异常拦截成功）；
    * Test 11：Hand IK vs Contact Intent Decoupling（自由空间抓空与主动表面接触精准区分，越界接触真实报警 `success=False`）；
    * Test 12：Whole-Body Inertia & Angular Momentum Telemetry（静态姿态角动量严格为 0.0，运动状态惯性张量正定且质量 > 50 kg）；
    * Test 13：Historical Motion Actions Intactness & Planning（Walk 7 步、Run 24 帧周期、SprintStart 36 帧、SprintBrake 26 帧动作完全完好）；
    * Test 14：历史 6 大核心模块全量回归（WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia）100% 通过（退出码 `0`）。
* **任务 6G-C-R3A 架构审计与规范锁定 (Task 6G-C-R3A: Architecture Audit & Specification Protocol)**：
  * **全仓库源码与调用链深度审计**：系统性审计 `src/motion/`、`src/rig/` 及测试与运行脚本，彻底澄清当前工程中真实存在的三套分立管线（历史动作管线、物理分析与全身控制工具链、演示原型脚本），并以源码证明障碍物原型（`run_contact_obstacle_integration.py`）之所以呈现 30 帧僵硬片段，是因为它在各片段中循环对完全相同的静态目标执行 `execute_frame`，缺乏连续步态调度和时间轴运动学。
  * **更新权威架构文档 (`ARCHITECTURE.md` v2.0)**：补充世界坐标统一约定、当前真实架构 Mermaid 流程图、目标生产级架构图、11 大模块数据流合同全表、6 大历史动作复用矩阵及架构断裂点审计。
  * **创建永久架构卡片 (`ARCHITECTURE_SYNC.md`)**：完整包含 12 项必填章节（设计思想、依赖图、官方数据流、动作矩阵、WBC 定位、IK/ROM 边界、物理遥测时机、模块分类、断裂点、使用与绕过纪律、基准 Git SHA、变更日志与维护规则）。
  * **更新永久项目规则 (`AGENTS.md` / `GEMINI.md` / `.agents/rules/project_rules.md`)**：在第 4 节加入前置必读 `ARCHITECTURE_SYNC.md`，新增第 8 节“架构对齐与防伪造纪律”，严禁重复造轮子、强制接入主数据流、禁止独立脚本拼凑动画、历史测试零退化、架构不一致暂停报告。
  * **完成 6 大物理数学模块代码级质询**：严格以代码行号和引用证明 `rigid_link.py`、`body_kinematics.py`、`body_inertia.py`、`contact_model.py` 均为纯只读事后遥测，无闭环驱动或姿态修正；证明 `WholeBodyController` 未被历史动作调用；证明系统为开环解析运动学驱动。
  * **状态结论**：R3A 架构审计全面完成，禁止编写新动作算法或修改 rig，等待 R3B 执行合流修复。
* **任务 6G-C 多部位接触几何、约束与支撑状态系统（第二次工程级返工交付）**：
  * **工程架构审计与根因分析**：编写 [`docs/MOTION_INTEGRATION_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/MOTION_INTEGRATION_AUDIT.md)（13.4 KB），系统性梳理 Task 3 到 6G 历史运动能力，剖析 6G-C 初次实现中脱离步态调度、使用数学插值平移根节点导致“单腿悬空滑行”的根本原因，确立解耦返工方案与双原型设计边界。
  * **场景 A：真实连续行走与接触系统集成原型 (`output/contact_walk_integration.blend` / `run_contact_walk_integration.py`)**：
    * 100% 沿用 Task 5C / 6A 验证的 `StartStopWalkAction`，生成 204 帧真实人类连续平滑步态（起步-加速-交替步态行走-减速-合拢停步）；
    * 根节点总位移严格符合理论规划（$Y: -8.0000\text{ m} \rightarrow -6.7400\text{ m}$，位移 $1.2600\text{ m}$，峰值速度 $0.2400\text{ m/s}$）；
    * 左右腿交替摆动与支撑，摆动脚具备清晰地面抬升（Step 0 右脚抬升 $100.0\text{ mm}$，Step 1 左脚抬升 $127.7\text{ mm}$，Step 2 右脚抬升 $137.6\text{ mm}$），彻底杜绝贴地拖动或刚体滑行；
    * 支撑脚微米级防滑锁定（左脚支撑漂移 $0.0012\text{ mm}$，右脚支撑漂移 $0.0047\text{ mm}$，严格 $< 0.05\text{ mm}$）；
    * 对侧手臂自然协调摆动（F28 夹角差 $+26.00^\circ$，F54 夹角差 $-51.56^\circ$，反向摆动）；
    * `ContactModel` 实时逐帧评估双脚接触并驱动绿色八面体标记物与向上外法线箭头在支撑相激活、摆动相熄灭。
  * **场景 B：多部位障碍物接触与支撑状态原型 (`output/contact_obstacle_integration.blend` / `run_contact_obstacle_integration.py`)**：
    * 包含 5 个清晰分段的 30 帧独立观察片段（F1..150）：Double Stance、Vault Touch（单手撑跳箱）、Foot on Wall（脚蹬垂直墙面）、Ledge Hang（双手抓杆悬垂）、Flight Phase（空中奔跑腾空）；
    * 角色前向矢状面严格正对障碍物（朝向点积严格为 $1.0000$，偏转夹角 $0.00^\circ$）；
    * 基础站姿自然垂臂（腕部位于肩部下方 $0.560\text{ m} \ge 0.40\text{ m}$）；
    * 5 场景形态显著分明（最小两两关节欧氏角差异达 $70.06^\circ \ge 20.0^\circ$）；
    * 接触锚点贴合精度达到微米级（地表 $0.00\text{ mm}$、箱顶 $0.02\text{ mm}$、蹬墙 $0.04\text{ mm}$、抓杆 $0.01\text{ mm}$，均严格 $< 10\text{ mm}$）；
    * 观察片段内接触锚点绝对锁定（漂移严格为 $0.0000\text{ mm} \le 0.1\text{ mm}$）；
    * 彻底杜绝在障碍物之间伪造虚假单腿滑行。
  * **自动化测试套件 (`tests/verify_task6gc_contact_model.py`) 17/17 项全部通过**：
    * 14 项接触几何、生命周期、刚体协变数学测试全绿；
    * 历史 6 大核心回归套件（Task 6G-B, 6G-A, 6F-D, 6F-C, 6F-B, 6F-A）100% 保持全绿（退出码 `0`）；
    * Test 16（场景 A 行走集成验收）全绿；
    * Test 17（场景 B 障碍物接触验收）全绿。
  * **目视验收状态**：已完成自动化集成验收，**待用户 Blender 目视复验**。坚决不进入 Task 6G-D。
* **任务 6G-B 刚体连杆惯性张量与全身角动量模型 (`InertiaTensor` / `WholeBodyInertiaState`)**：
  * 在 [`src/motion/body_inertia.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_inertia.py) 中实现分段几何惯性建模、3D 平行轴定理全身惯性张量合成与多连杆角动量（Spin/Orbital 解耦求和），经由 [`tests/verify_task6gb_body_inertia.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gb_body_inertia.py) 自动化测试套件（13 项严苛测试）完整验证。
  * **实测关键指标**：
    * **分段局部惯性张量对称且正定**：15 刚体质量分段（头、躯干、骨盆、双上臂、双前臂、双手、双大腿、双小腿、双脚）局部惯性张量严格对称，主惯量（特征值）全为正（最小 $0.00025\text{ kg}\cdot\text{m}^2$ 到最大 $0.61690\text{ kg}\cdot\text{m}^2$），100% 满足物理真实性。
    * **几何近似闭式公式精确一致**：圆柱体、椭球体、椭圆柱体、长方体闭式惯性公式与独立解析理论值完全一致，最大数值误差严格 $< 3 \times 10^{-17}$。
    * **3D 平行轴定理数值无损**：位移 $r=(0.3, -0.4, 0.5)\text{ m}$，计算结果与理论增量完全一致（最大单精度浮点累积误差仅 $4.77 \times 10^{-8}$）。
    * **空间平移不变性**：角色整体平移位移 $(12.5, -45.0, 3.2)\text{ m}$，相对自身 CoM 的全身惯性张量差值 Frobenius 范数仅 **`8.96e-06 kg*m^2`**（完全保持不变）。
    * **刚体旋转张量变换协变性**：角色整体绕任意 3D 轴 $(0.577, 0.577, 0.577)$ 旋转 $40^\circ$，合成惯性张量与张量变换定律 $\mathbf{Q} \mathbf{I} \mathbf{Q}^T$ 误差仅 **`7.06e-06 kg*m^2`**。
    * **中立站姿矢状面对称与合理量级**：左右对称矢状面惯性积严格为 $0$（$I_{xy} = I_{xz} = 0.00000$）；俯仰 $I_{xx} = 13.46\text{ kg}\cdot\text{m}^2$、滚转 $I_{yy} = 14.21\text{ kg}\cdot\text{m}^2$、偏航 $I_{zz} = 1.08\text{ kg}\cdot\text{m}^2$，处于人体生物力学标准区间。
    * **单臂侧平举敏锐物理响应**：右臂侧平举引发偏航转动惯量显著增加 $+0.65442\text{ kg}\cdot\text{m}^2$（增幅达 $+60.7\%$），并引入非对称惯性积 $I_{xy} = 0.10313\text{ kg}\cdot\text{m}^2$。
    * **四肢展开与紧收姿态惯性比**：大字展开（T-Pose: $I_{zz} = 2.40271\text{ kg}\cdot\text{m}^2$）与抱胸收束（Tucked: $I_{zz} = 0.94590\text{ kg}\cdot\text{m}^2$）差异显著，偏航惯性比达 **`2.540 倍`**（差值 $+1.45682\text{ kg}\cdot\text{m}^2$）。
    * **静止身体角动量严格为零**：零速度下全身体自转、轨道及总角动量严格等于 **`0.00000000 kg*m^2/s`**。
    * **刚性旋转多连杆角动量解析一致性**：整个人体绕 CoM 以 $\boldsymbol{\omega}=(0.4, 0.8, -0.6)\text{ rad/s}$ 发生刚体旋转时，多连杆自转+轨道求和角动量与单刚体 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$ 绝对矢量误差仅 **`1.07e-06 kg*m^2/s`**（相对误差 **`8.54e-08`**）。
    * **四肢独立运动自转与轨道解耦**：单侧手臂挥动时，自转角动量模长 $0.09087\text{ kg}\cdot\text{m}^2/\text{s}$ 与肢体轨道角动量模长 $1.69233\text{ kg}\cdot\text{m}^2/\text{s}$ 清晰解耦，总角动量严格矢量守恒。
    * **与 CoM、速度学追踪器及动作状态机无缝集成**：全身质心误差严格为 $0.00\text{ m}$，离散快照与 Armature 姿态求算张量差仅 $7.33 \times 10^{-7}\text{ kg}\cdot\text{m}^2$，通过 `enrich_motion_state_with_inertia` 无损注入 `MotionState.params`。
    * **全量回归验证**：Task 6G-A、6F-D、6F-C、6F-B、6F-A 及 6D 测试均 100% 全绿通过（退出码 `0`）。
* **任务 6G-A 连续身体运动状态与速度学基础 (`BodyKinematicsTracker`)**：
  * 在 [`src/motion/body_kinematics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_kinematics.py) 中实现连续身体姿态快照采样、微分速度学与运动状态追踪器，经由 [`tests/verify_task6ga_body_kinematics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6ga_body_kinematics.py) 自动化测试套件（10 项严苛测试）完整验证。
  * **实测关键指标**：
    * **静态微分零速零漂**：$\Delta t = 0.041667\text{ s}$（24 FPS）静态下，根节点、CoM、15 刚体质量分段、17 解剖关节、4 四肢末端线速度与角速度严格全为 **`0.000000 m/s`** 与 **`0.000000 rad/s`**，零漂移。
    * **纯平移线速度严格一致**：根节点 $+0.100\text{ m}$ 前向平移，导出线速度 $2.400000\text{ m/s}$（理论值 $2.400000\text{ m/s}$，误差 **`0.000000 m/s`**）；CoM 及全部 15 刚体分段线速度严格等于 $2.400000\text{ m/s}$，角速度全为 $0$。
    * **单轴旋转空间角速度严格对齐**：根节点 $0.1\text{ s}$ 内绕 $Z$ 轴纯旋转 $30^\circ$，导出空间角速度 $\omega_z = 5.235988\text{ rad/s}$（$300.0000^\circ/\text{s}$），绝对误差严格 $< 3 \times 10^{-8}\text{ rad/s}$。
    * **复合 3D 轴空间角速度精准计算**：绕归一化任意轴 $(0.577, 0.577, 0.577)$ 旋转 $45^\circ$，理论模长 $15.707963\text{ rad/s}$，导出模长 $15.707962\text{ rad/s}$，三维矢量误差严格 $< 1.5 \times 10^{-6}\text{ rad/s}$。
    * **短测地线与 $\pm 180^\circ$ 环绕跳跃消除**：从 $+170^\circ$ 旋转至 $-170^\circ$（测地线角位移 $+20^\circ$），在 $\Delta t=0.1\text{ s}$ 下精确测得角速度 $3.490659\text{ rad/s}$（$200.0000^\circ/\text{s}$），误差严格为 **`0.000000 rad/s`**，彻底杜绝欧拉角微分的虚假高速突刺（如 $3400^\circ/\text{s}$）。
    * **变时间步长 $\Delta t$ 尺度缩放严格线性**：在 $\Delta t \in [0.01, 0.041667, 0.1, 0.5]\text{ s}$ 任意步长下，导出速度与 $1/\Delta t$ 严格成反比，缩放误差为 **`0.000000 m/s`**。
    * **单肢运动局部角速度绝对隔离**：仅右臂前臂肘屈 $45^\circ$，`forearm.R` 局部角速度精准测得 $18.750000\text{ rad/s}$（$1074.2959^\circ/\text{s}$），左臂、躯干、双腿等非子级关节角速度严格保持 **`0.000000 rad/s`**，零串扰零泄漏。
    * **全身质心动量守恒物理一致性**：多肢体复合运动下，总动量求和 $\sum m_i v_i = 127.3276\text{ kg}\cdot\text{m/s}$ 与总质量质心动量 $M \cdot v_{\text{com}} = 127.3280\text{ kg}\cdot\text{m/s}$ 高度吻合，数值差异仅 $6.1 \times 10^{-6}\text{ m/s}$（$0.006\text{ mm/s}$），完全满足 Blender 32 位浮点累加容差（$< 10^{-5}\text{ m/s}$）。
    * **真实骨架 IK 姿态连续采样**：与真实 Blender Armature 及 `WholeBodyController` 联调采样，完整提取根节点、15 分段、17 关节及 4 末端微分运动学特征，零 NaN、零 Inf。
    * **动作边界速度加速度连续过渡与无缝注入**：冲刺加速与制动急停过渡区（Frame 20）速度平滑衍生，二阶加速度连续计算，通过 `enrich_motion_state_with_kinematics` 无缝注入 `MotionState.params`，完全向下兼容现有动作流。
    * **全量回归验证**：Task 6F-D（10 项）、Task 6F-C（10 项）、Task 6F-B（8 项）、Task 6F-A（8 项）、Task 6D（冲刺急停原型验证）均 100% 全绿通过（退出码 `0`）。
* **任务 6F-D 统一全身控制接口与最小协调器 (`WholeBodyController`)**：
  * 在 [`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py) 中实现多末端协调与统一接口，经由 [`tests/verify_task6fd_whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6fd_whole_body_controller.py) 自动化测试套件（10 项严苛测试）完整验证。
  * **实测关键指标**：
    * **双臂独立控制**：左右手同时跟踪不同目标，位置误差分别为 $0.041\text{ mm}$ 与 $0.020\text{ mm}$，3D 朝向对齐误差严格为 **`0.000 deg`**。
    * **双脚独立控制**：支撑脚接地误差 $0.003\text{ mm}$，空中摆动脚抬升误差 $0.029\text{ mm}$。
    * **单帧四肢末端同时控制**：四肢（hand_L, hand_R, foot_L, foot_R）同时激活，各末端误差均 $< 0.05\text{ mm}$，全肢体处于物理达程内，ROM 0 违规。
    * **选择性禁用独立性**：禁用左手（`enabled=False`）平滑回退至 FK 模式，完全不干扰右手与双脚（右手误差保持 $0.015\text{ mm}$）。
    * **骨盆与基座协调不变性**：骨盆下蹲 $-0.06\text{ m}$（世界 $Z=0.8300\text{ m}$）并俯仰躯干，手脚世界绝对坐标目标精准保持（误差 $< 0.03\text{ mm}$）。
    * **手部位置与 3D 朝向解耦**：腕部位置固定，手部在生理 ROM 内变动 3 组朝向，腕部漂移 $< 0.04\text{ mm}$，朝向对齐误差 $0.0000^\circ$。
    * **ROM 校验一致性**：控制器内部 ROM 校验与独立 `JointModel` 校验完全一致（故意过弯脊柱，两者量化超限量严格相等：$20.00^\circ$）。
    * **不可达与 ROM 冲突真实截获**：超出达程目标（$Y=-6.5\text{ m}$ 远超 $0.56\text{ m}$）真实报告 `REACHABILITY` 与 `ROM_VIOLATION`，`success = False`，杜绝虚假成功。
    * **全身质心一致性**：控制器内部全身质心与 `rigid_link` 独立计算数值差异严格为 **`0.0000000000 m`**。
    * **动作架构无缝接入**：`WholeBodyDemoAction(MotionAction)` 连续执行 8 帧，每帧生成合法 `MotionState` 并持久化 CoM 与追踪参数。
    * **全量回归验证**：Task 6F-C 关节 ROM 测试、Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 全绿通过（退出码 `0`）。
* **任务 6F-C 关节自由度（DOF）与生理活动范围（ROM）约束系统**：
  * 在 [`src/motion/joint_limits.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/joint_limits.py) 中实现解耦式关节模型与非静默校验/截断系统，经由 [`tests/verify_task6fc_joint_limits.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6fc_joint_limits.py) 自动化测试套件完整验证。
  * **实测关键指标**：
    * **中立站姿合规性**：17 个解剖关节（覆盖脊柱、颈、头、双肩、双臂、双前臂、双腕、双髋、双膝、双踝）在中立站姿下 100% 满足 ROM 规范（0 违规）。
    * **合法边界容许性**：测试全主要关节在生理边界内的复合动作，100% 通过验证且修改量严格为 **`0.00 deg`**。
    * **超限精准检出与量化**：脊柱过屈（+85°）、肘关节向后反折（-25°）、膝关节向前反折（+35°）、肩关节过度外展（+170°）均被精准检出，超限量计算误差严格 $\le 0.1^\circ$。
    * **安全投影截断与非静默报告**：超限角度被准确投影至生理极限边界（脊柱 +60°，肘关节 -2°，膝关节 +2°，肩关节 +150°），截断后二次校验 100% 合法，修改报告完整输出。
    * **双侧镜像对称性**：上肢与下肢展收角（Local Z）镜像反号处理完全正确（左侧外展 $+Z$、右侧外展 $-Z$），双侧对称外展动作验证通过。
    * **反向折断硬性锁定**：膝关节向前穿刺反折被铰链锁硬性截断在 $\le +2.0^\circ$；肘关节向后反折被硬性截断在 $\ge -2.0^\circ$。
    * **复合多轴旋转椭圆锥限位**：肩关节（`upper_arm.L`）同时处于极大俯仰（140°）与极大外展（130°）时，合成摆角达 $191.0^\circ$，超限 $35.9^\circ$ 被椭圆锥平滑径向投影至 $(113.7^\circ, 0.0^\circ, 105.6^\circ)$。
    * **环绕跳变防护稳定性**：$365^\circ \rightarrow 10^\circ$（合法通过），$270^\circ \rightarrow -90^\circ$（准确检出越界），彻底杜绝 $\pm 180^\circ$ 截断突变跳跃。
    * **骨骼长度恒定性**：骨架姿态截断下 19 根骨骼长度变化严格为 **`0.000000 m`**（100% 保持恒定）。
    * **活动 IK 兼容性**：
      * 双腿 IK 活跃站立姿态：100% 处于 ROM 范围内；
      * 双腿 IK 前屈抬腿（提脚 $0.20\text{ m}$）：髋关节屈曲 $+56.36^\circ$（ROM $[-25^\circ, +120^\circ]$），膝关节屈曲 $-70.79^\circ$（ROM $[-145^\circ, +2^\circ]$），100% 满足解剖规范；
      * 双手 IK 前向伸手抓取：上臂俯仰 $+9.60^\circ$，前臂肘屈 $+93.67^\circ$（ROM $[-2^\circ, +145^\circ]$），100% 满足解剖规范。
    * **回归验证**：原有 Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 全绿通过（退出码 `0`）。
* **任务 6F-B 刚体连杆分段、质量分布模型与全身质心（CoM）计算**：已验证。
* **任务 6F-A 双臂独立 IK 与世界空间控制及可视化验收原型**：已验证。
* **任务 6E 刚体连杆人体运动控制审计与最小架构设计**：已验证。
* **任务 6D 基于统一运动框架实现冲刺后的主动制动与急停 (SprintBrakeAction)**：已验证。
* **任务 6C 基于统一运动框架实现爆发式起步与加速冲刺**：已验证。
* **任务 6B 程序化跑步模式 Run**：已验证。
* **任务 6A 建立可扩展的程序化运动系统基础架构**：已验证。
* **任务 5C / 5B / 5A / 4D / 4C / 4B / 4A / 3**：已验证。

### [已实现]
* 只读 AST 与 Blender 资产机器审计器：`tests/audit_c2_final_inspector.py`、`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`、`docs/evidence/task6gd_c2a/blend_inspection_log.txt`
* 动力学训练场自动视觉证据与逐帧遥测系统：`src/scene/dynamics_visualizer.py`、`src/scene/dynamics_visual_evidence.py`、`run_generate_visual_evidence.py`、`tests/verify_task6gd_playground_dynamics.py`、`tests/verify_task6gd_visual_telemetry.py`
* 多帧动力学闭环控制与状态反馈系统：`src/motion/closed_loop_dynamics.py`、`tests/verify_task6gd_closed_loop_dynamics.py`
* 6-DOF 刚体前向动力学单步积分内核与不可变状态机：`src/motion/forward_dynamics.py`、`tests/verify_task6gd_forward_dynamics.py`
* 多接触力优化求解与分配器（SLSQP/SPG 双引擎）：`src/motion/contact_force_solver.py`、`tests/verify_task6gd_contact_force_solver.py`
* 接触力学、冲量与动量时间步长系统：`src/motion/contact_dynamics.py`、`tests/verify_task6gd_contact_dynamics.py`
* 统一环境查询接口与动力学训练场单一 SSOT：`src/scene/environment_query.py`、`output/dynamics_playground.blend`、`tests/verify_task6gd_dynamics_playground.py`、`tests/verify_task6gd_playground_blend.py`
* 统一测试管理与运行接口：`tests/test_registry.py`、`tests/run_test_suite.py`、`run_tests.ps1`
* 最小兼容桥接层与单帧 6 阶段流水线执行器：`src/motion/kinematic_bridge.py`、`tests/verify_task6gc_r3b1_bridge.py`
* 多部位接触几何、约束与支撑状态系统：`src/motion/contact_model.py`、`run_contact_model_prototype.py`、`tests/verify_task6gc_contact_model.py`、`output/contact_model_debug.blend`
* 刚体连杆惯性张量与全身角动量模型：`src/motion/body_inertia.py`、`tests/verify_task6gb_body_inertia.py`
* 连续身体运动状态与速度学基础：`src/motion/body_kinematics.py`、`tests/verify_task6ga_body_kinematics.py`
* 统一全身控制接口与最小协调器：`src/motion/whole_body_controller.py`、`tests/verify_task6fd_whole_body_controller.py`
* 关节自由度与生理活动范围（ROM）约束系统：`src/motion/joint_limits.py`、`tests/verify_task6fc_joint_limits.py`
* 刚体连杆分段、质量分布模型与全身质心计算：`src/motion/rigid_link.py`、`tests/verify_task6fb_rigid_link.py`
* 双臂独立 IK 与世界空间控制：`src/rig/arm_ik.py`、`run_arm_ik_prototype.py`、`tests/verify_task6fa_arm_ik.py`、`tests/verify_task6fa_visual_prototype.py`、`output/character_arm_ik_prototype.blend`
* 刚体连杆人体运动控制审计与最小架构设计：`ARCHITECTURE.md`（第 4 节）、`DECISIONS.md`（`[DEC-015]`、`[DEC-016]`、`[DEC-017]`、`[DEC-018]`）、`CHANGELOG.md`、`HANDOFF.md`
* 冲刺主动制动与急停：`src/motion/sprint_brake.py`、`run_sprint_brake_prototype.py`、`tests/verify_task6d_sprint_brake.py`
* 爆发式起步与冲刺加速：`src/motion/sprint_start.py`、`run_sprint_prototype.py`、`tests/verify_task6c_sprint_start.py`
* 程序化跑步模式：`src/motion/run_cycle.py`、`run_run_prototype.py`、`tests/verify_task6b_run.py`
* 可扩展运动框架：`src/motion/framework.py`、`run_motion_framework_prototype.py`、`tests/verify_task6a_motion_framework.py`
* 变速行走、匀速行走与原地步态：`src/motion/start_stop_walk.py`、`src/motion/forward_walk.py`、`src/motion/walk_cycle.py`
* 基础绑定、IK、接触约束与场景系统：`src/rig/`、`src/character/`、`src/scene/`、`src/camera/`、`src/lighting/`、`src/config.py`

### [已执行但未完整验证]
* `.agents/rules/project_rules.md` 独立加载及外部新会话自动恢复状态保持为未完整验证。

### [未实现]
* **Phase 7A**：真实 19 骨骼角色（`src/character/builder.py` + `src/rig/builder.py`）进入 `DynamicsPlayground`（`output/dynamics_playground.blend`），完成基础下肢连续通行（落脚点规划作为 7A 下肢移动的内部能力）。
* **Phase 7B**：上肢独立运动与末端目标验证。
* **Phase 7C**：既有 `KinematicBridge`（`src/motion/kinematic_bridge.py`）、`WholeBodyController`（`src/motion/whole_body_controller.py`）、`CoM`（`src/motion/rigid_link.py`）与整体动力学状态（`src/motion/closed_loop_dynamics.py` / `src/motion/forward_dynamics.py`）汇流。
* **Phase 7D**：多关节动态协同。
* **Phase 7E**：既有 IK/FK 求解器的动态协同与接触切换。
* **Phase 7F**：全身移动、抓握、支撑、释放与连续训练场通行。
* **Phase 6H**：动态平衡与主动补偿。

### [已知缺陷与遗留说明]
1. **双管线尚未汇流（计划于 Phase 7A / 7C 解决）**：当前 `output/dynamics_playground.blend` 仅包含 14 区环境网格与 6G-D 刚体代理可视化（`Playground_Dynamics_Visualization`，0 骨骼），尚未放入 19 骨骼 `CharacterArmature`（定位于 **Phase 7A**），且 6G-D 质心动力学尚未与 `KinematicBridgeExecutor` + `WholeBodyController` 闭环汇流（定位于 **Phase 7C**）。
2. **Station 2 / 3 / 4 模型边界**：Station 2 为空中自由落体弹道（不含触地回弹碰撞）；Station 3 与 4 在训练场代理阶段采用连续移动接触点（待 7A/7C 替换为真实 19 骨骼双足交替落脚）。
3. **`src/motion/kinematic_bridge.py:447` 存在休眠引用 `ContactLifecycle.TOUCHDOWN`**：在手臂主动触碰障碍物表面的未激活分支中，存在一行休眠代码引用了不存在的枚举成员 `ContactLifecycle.TOUCHDOWN`；由于本任务严格禁止修改任何 `src/` 文件，该缺陷已明确登记为已知缺陷，待后续允许修改生产代码的任务统一修复。

### [理论可行但尚未测试]
* 外部第三方 AI 助手粘贴 `AI_SYNC.md` 恢复完整上下文的人工交互效果。

---

## 2. 下一步建议
* **严格停止，等待人类与 ChatGPT 复核 Task 6G-D-C2-FINAL 验收纠偏结果**；
* **暂停且严禁提前进入 Phase 7A 或 Phase 6H**。
