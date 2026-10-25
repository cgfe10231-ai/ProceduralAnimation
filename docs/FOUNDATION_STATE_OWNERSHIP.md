# FOUNDATION_STATE_OWNERSHIP: 状态权威归属与读写所有权矩阵

* **文档版本**：1.0.0 (Architecture Freeze Edition)
* **对应任务**：Task 6G-D-C2-FINAL
* **基准 Commit**：`d0d73d476e2f2d3f3b629d767744ab12ba867bf8`
* **适用标准**：ACG SSOT ([`docs/ARCHITECTURE_CHANGE_GATE.md`](ARCHITECTURE_CHANGE_GATE.md))
* **最后审计日期**：2026-10-25

---

## 一、状态归属与读写所有权矩阵 (State Ownership Matrix)

在多层级程序化运动生成系统中，各物理量、时间线和骨骼变换必须具备明确的**唯一写入权威 (Single Writer SSOT)**。严禁多模块写竞争或模糊所有权：

| 物理量 / 状态范畴 | 权威数据持有者 (State Owner / SSOT) | 唯一写入权威 (Writer) | 允许只读方 (Readers) | 空间 / 坐标系与物理单位 |
| :--- | :--- | :--- | :--- | :--- |
| **仿真时间与步长**<br>($t_k, \Delta t, F$) | `ClosedLoopDynamicsCoordinator`<br>/ `Scene.frame_current` | 时间调度循环 (Time Stepper) | 全系统所有模块 | 时间：秒 ($\text{s}$)，帧率：$24\text{ FPS}$，步长 $\Delta t = 1/24\text{ s}$，Frame $F = k + 1$ |
| **目标运动参考**<br>($p_{\text{target}}, v_{\text{target}}, q_{\text{target}}$) | `MotionReferenceTrajectory`<br>/ `TargetReferenceSchedule` | 高层动作规划器 (Motion Planner) | 接触力求解器、遥测审计、目标虚影渲染器 | 世界坐标系 (+Z Up, Ground Z=0.0m)，单位：$\text{m}, \text{m/s}, \text{quat}$ |
| **接触约束规范**<br>($p_{\text{contact}}, n, \mu, F_{\text{min/max}}$) | `ContactConstraintSpec` | 环境几何查询 / 步态落足规划器 | 接触力求解器、接触标记圆盘渲染器 | 世界坐标系，力单位：$\text{N}$，摩擦系数无量纲 |
| **实际接触反力**<br>($F_{\text{contact}}, \tau_{\text{contact}}$) | `ContactSolverResult`<br>/ `ClosedLoopFrameData` | `ContactForceSolver.solve()` | 前向动力学积分器、力矢量箭头渲染器、遥测记录器 | 世界坐标系，单位：$\text{N}, \text{N}\cdot\text{m}$ |
| **物理实际质心状态**<br>($p_{\text{actual}}, v_{\text{actual}}, q, L$) | `ForwardDynamicsState`<br>(Frozen Immutability) | `ForwardDynamicsKernel.integrate_step()` | 全身控制器、遥测审计、轨迹曲线渲染器 | 世界坐标系，单位：$\text{m}, \text{m/s}, \text{quat}, \text{kg}\cdot\text{m}^2/\text{s}$ |
| **骨盆与 Root 根骨骼**<br>(`root`, `pelvis`) | Blender Armature PoseBones | `WholeBodyController.apply_pose()` | 摄像机追踪器、环境避障碰撞体 | 骨骼局部/世界变换矩阵 |
| **四肢与脊椎关节角**<br>(19 根骨骼 Pose) | Blender Armature PoseBones | `WholeBodyController.apply_pose()` | 渲染引擎、视口显示、导出器 | 欧拉角 / 四元数，弧度或四元数无量纲 |
| **足端 / 手腕 IK 目标**<br>(End-Effectors IK Targets) | `KinematicPoseTarget`<br>/ IK Control Bones | `KinematicsService.solve_leg_ik()` | Blender IK 约束解算器 | 骨架对象空间 / 世界空间，单位：$\text{m}$ |
| **跨系统遥测与误差指标**<br>($\Delta p, \Delta q, \text{err}$) | `telemetry.json`<br>/ `VisualTelemetryRecord` | `dynamics_visual_evidence.py` | 自动化审计套件、跨 AI 审阅报告 | 误差单位：$\text{m}, \text{rad}$，防冒充指标 |

---

## 二、状态所有权四大约束法则 (Strict Ownership Invariants)

1. **法则一：实际物理状态不可篡改法则 (Physical State Immutability)**：
   - 实际质心状态由且仅由 `forward_dynamics.py` 依据牛顿-欧拉方程经辛积分生成；
   - 严禁任何高层规划器或 IK 求解器直接将目标参考 ($p_{\text{target}}$) 硬赋值为实际物理状态 ($p_{\text{actual}}$)。
2. **法则二：接触力由物理优化器独占产出 (Forces Solely by Solver)**：
   - 所有接触反力 $F_{\text{contact}}$ 必须经由 `ContactForceSolver` 严格求解（满足法向单侧性 $F_n \ge 0$ 与有界库仑摩擦锥 $\|F_t\| \le \mu F_n$）；
   - 严禁在控制器中直接硬编码伪造外力，严禁在空中悬空时生成非零接触反力。
3. **法则三：Blender 骨骼独占写锁 (Exclusive Armature Write Lock)**：
   - 遵循 ACG 清规第 6 条：严禁绕开 `WholeBodyController` 直接向角色骨骼写入姿态；
   - 所有动作层（Walk/Run/Turn）只能向 WBC 提交 `KinematicPoseTarget`，由 WBC 统一进行软限位裁决、生理角度保护和帧级骨骼写入。
4. **法则四：状态审计独立性 (Independent Audit Ownership)**：
   - 遥测收集模块 `dynamics_visual_evidence.py` 作为只读审计方，独立于仿真计算循环；
   - 必须基于 Blender 求值后的实际物体变换矩阵（`obj.matrix_world`）与纯 Python 数值状态进行跨空间比对，误差超过容差（$< 10^{-5}\text{ m}$）直接判负。
