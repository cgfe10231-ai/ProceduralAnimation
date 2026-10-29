# ProceduralAnimation — Audit F: 物理与数学真实性审计报告

**文档标识**：`docs/audit/environment_gate01_final/PHYSICS_AND_CONTROL_GAPS.md`  
**审计基准 HEAD**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计性质**：Environment Gate 01 最终独立架构审计（Audit F）

---

## 1. 核心结论与驱动范式定性

经过对全工程生产主执行链（`src/scene/playground_terrain_traversal.py` $\to$ `src/motion/terrain_walk.py` $\to$ `src/motion/kinematic_bridge.py` $\to$ `src/motion/whole_body_controller.py` $\to$ `src/rig/`）以及动力学模块源码的严密审计，得出以下唯一定量定性结论：

> **核心结论**：  
> 当前 19 骨骼人体运动系统是 **100% 运动学驱动伴随几何环境自适应（Purely Kinematically Driven with Geometric Environment Perception）**。  
> 该系统 **不是动力学驱动系统**，也 **不是动力学-运动学混合系统**。  
> 仓库中虽已实现高质量的接触力 QP 求解器（`contact_force_solver.py`）、多接触动力学（`contact_dynamics.py`）以及闭环动力学校正器（`closed_loop_dynamics.py`），但这些动力学模块目前 **仅运行在单刚体质点/代理盒体单元测试中（Level ②: TEST_ONLY）**，**完全未接入 19 骨骼人体的主循环**。人体骨骼的最终姿态 100% 由解析规划器与双骨骼 IK 求解器决定，受力、力矩与加速度为零闭环反馈。

---

## 2. 物理与数学参数逐项核实表

| 物理/数学要素 | 生产实现模块与行号 | 实际数值 / 数学公式 | 坐标空间与单位 | 是否闭环进入主控 | 真实性评估与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **世界坐标系** | 全工程约定，[blender_mesh_query_adapter.py#L31](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/blender_mesh_query_adapter.py#L31) | $+X$ 向右，$+Y$ 前进，$+Z$ 坚直向上（右手系） | 世界坐标系，米 (m) | 是 | 统一且严格遵守，符合 Blender 标准。 |
| **参考水平基准** | `kinematic_bridge.py#L472`, `terrain_walk.py#L182` | 地面基准高度 $Z = 0.0\,\text{m}$ | 世界坐标系，米 (m) | 是 | 作为平地基线，Mesh 高程查询叠加于此基准。 |
| **时间步长 ($\Delta t$)** | `framework.py#L34`, `terrain_walk.py#L193` | $\text{fps} = 24.0 \implies \Delta t = \frac{1}{24} \approx 0.041667\,\text{s}$ | 时间标量，秒 (s) | 是 | 帧率与物理积分步长统一为 24 FPS。 |
| **骨骼几何长度** | `src/rig/builder.py#L65-L120`, `src/rig/ik.py#L12` | 股骨 (Femur): $0.40\,\text{m}$<br>胫骨 (Tibia): $0.40\,\text{m}$<br>大腿+小腿全长: $0.80\,\text{m}$<br>上臂 (Humerus): $0.28\,\text{m}$<br>前臂 (Radius): $0.25\,\text{m}$ | 局部与世界，米 (m) | 是 | 19 骨骼标准人形比例，符合人体解剖学生物力学基准。 |
| **关节 ROM 约束** | `src/motion/joint_limits.py#L15-L80` | 膝关节屈曲: $[0^\circ, 140^\circ]$<br>髋屈伸: $[-30^\circ, 110^\circ]$<br>脊柱前屈: $[-15^\circ, 35^\circ]$ 等 | 局部欧拉角，度 (deg) | 部分通过测试验证 | 在 `src/rig/ik.py` / `arm_ik.py` 中有两骨几何限制；`joint_limits.py` 具有生理边界检测工具，但 WBC 未执行主动投影裁剪。 |
| **IK 可达性与奇异性** | `src/rig/ik.py#L35`, `arm_ik.py#L35` | 极距截断: $d_{\max} = (L_1 + L_2) \times 0.999$<br>$d_{\text{clamped}} = \min(\text{dist}, d_{\max})$ | 局部/世界标量，米 (m) | 是 | 几何余弦定理两骨 IK，奇异点通过 $0.999$ 防死锁伸直保护。超范围时发出一票只读 warning（不反馈改步长）。 |
| **质心 (CoM) 计算** | `src/motion/rigid_link.py#L210-L245` | $M = 75.0\,\text{kg}$，基于 Dempster 人体分段质量比值累加分段 CoM | 世界坐标系，米 (m) | **否 (TELEMETRY_ONLY)** | 每一帧在 `kinematic_bridge.py` 中被正确计算并记录至遥测日志，但 **未反馈给 Root 位置或足部规划**。 |
| **转动惯量张量** | `src/motion/body_inertia.py#L85-L135` | 19 骨骼各段圆柱/椭球分段惯量，平行轴定理累加 $3 \times 3$ 张量 $\mathbf{I}_{\text{world}}$ | 质心世界系，$\text{kg}\cdot\text{m}^2$ | **否 (TELEMETRY_ONLY)** | 纯遥测记录，未用于欧拉动力学方程 $\boldsymbol{\tau} = \mathbf{I}\boldsymbol{\alpha} + \boldsymbol{\omega}\times\mathbf{I}\boldsymbol{\omega}$。 |
| **环境法线提取** | `blender_mesh_query_adapter.py#L125` | 从 BVH 三角面法线经 `obj.matrix_world` 变换并归一化输出 $\vec{n} = (n_x, n_y, n_z)$ | 世界坐标系，无量纲单位向量 | 是 | 真实几何法线。在 `terrain_walk.py` 中用于根据斜坡法线计算躯干前后倾角。 |
| **足底接触锚点 (三坐标区分)** | `kinematic_bridge.py#L395-L425` | 点 A: 踝关节 IK 目标 $(X, Y, Z_{\text{ankle}})$<br>点 B: 真实地面接触点 $(X, Y, Z_{\text{mesh}})$<br>点 C: 足底着地点，下移 $h_{\text{ankle}} = 0.08\,\text{m}$ | 世界坐标系，米 (m) | 是 | **Unit 4 关键成果**：彻底澄清了踝关节中心与足底真实接触点的几何映射，间隙 $\Delta z = \|Z_{\text{sole}} - Z_{\text{mesh}}\|$ 实测 $< 0.005\,\text{m}$。 |
| **支撑多边形 (Support Polygon)** | `src/motion/contact_model.py#L120-L160` | 双足着地点构成的 2D 凸包，计算质心投影与边界距离 margin | 世界水平投影面，米 (m) | **否 (TELEMETRY_ONLY)** | 仅记录稳定裕度日志，未引发任何失稳保护或倾倒动力学行为。 |
| **库仑摩擦锥约束** | `src/motion/contact_dynamics.py#L185` | 摩擦系数 $\mu = 0.6$，切向力约束 $\|\mathbf{f}_t\| \le \mu f_n$ | 力学标量，牛顿 (N) | **否 (TEST_ONLY)** | 仅在 `test_task6gd_contact_dynamics.py` 等单元测试中被验证，19 骨骼步态中足底无切向摩擦滑移判定。 |
| **接触力求解 (QP Solver)** | `src/motion/contact_force_solver.py#L65-L140` | $\min_{\mathbf{f}} \frac{1}{2}\mathbf{f}^T \mathbf{Q}\mathbf{f} + \mathbf{c}^T\mathbf{f}$ s.t. 摩擦锥与单边法向力约束 | 力学标量，牛顿 (N) | **否 (TEST_ONLY)** | 求解器数学完备且数值鲁棒，但输入来自虚拟盒体代理，未连接人体足部接触力。 |
| **正向动力学积分 (Forward Dynamics)** | `src/motion/forward_dynamics.py#L45-L95` | 半隐式欧拉 / RK4 积分 $\dot{\mathbf{v}} = \mathbf{M}^{-1}(\mathbf{f} - \mathbf{C}\mathbf{v} - \mathbf{g})$ | 世界动力学状态，$\text{m/s}, \text{rad/s}$ | **否 (TEST_ONLY)** | 仅驱动单刚体运动，未对 19 骨骼 Armature 的 Root 或关节执行正向积分。 |

---

## 3. 物理与控制缺口 (Physics & Control Gaps)

### 缺口 1：开环纯运动学轨迹，无反作用力与质心调整 (No Ground Reaction Force Feedback)
* **表现**：Root 位置和骨盆旋转完全由 `TerrainWalkAction` 内部根据预设步长、Hermite 曲线插值及 Mesh 高程算得，地面不施加法向力 $\mathbf{F}_n$ 或切向力 $\mathbf{F}_t$。
* **影响**：即使人体踩在冰面或极端陡坡上，只要几何高度查询成功且满足 $n_z \ge 0.5$，步态轨迹仍然按预设曲线行进，不会发生物理滑移或失稳摔倒。

### 缺口 2：动量与角动量平衡缺失 (Zero Angular Momentum Regulation)
* **表现**：手臂摆动由预设正弦波硬编码驱动（`arm_l_rx = -arm_swing_amp * sin(2*pi*gait_u)`），躯干倾角由斜坡俯仰预设比例调整，而非为了抵消下肢摆动引起的坚直轴角动量 $\dot{\mathbf{H}}_G$。
* **影响**：动画呈现出形态学上的步态特征，但缺乏深层动力学平衡（例如重心偏移引起的自发性摆臂补偿）。

### 缺口 3：IK 超程开环告警，未触发自适应跨步重规划 (Open-loop Reachability Logging)
* **表现**：在 `terrain_walk.py:1084` 中，当足部目标超过腿部最大伸展极限时，系统仅记录 `logger.warning(...)` 并强行几何截断至 $0.999 \times \text{max\_reach}$。
* **影响**：步态规划器不会因为脚够不着台阶而缩短步长或重新规划下一个落脚点，可能导致骨盆被动拉扯或膝关节死锁。

---

## 4. 结论与架构准入建议

1. **真实性定性通过**：本工程从几何、运动学和生物力学角度是极其严谨且真实的（严密的骨骼层级、真实的 BVH 射线与法线投射、严谨的足底-网格间隙消除、精确的身体分段质心遥测）。
2. **拒绝动力学冒充**：文档与报告中 **绝对禁止声称 19 骨骼系统“已经具有动力学受力平衡”**，必须实事求是标定为“基于真实网格感知的连续运动学人形系统”。
3. **后续准入明确**：
   * **Phase 7B（独立上肢运动学）**：完全属于纯运动学范畴，与动力学反馈解耦，**完全不依赖动力学闭环**，可直接基于当前严谨的运动学主链开展。
   * **Phase 7C / 6H（动力学与主动平衡闭环）**：必须在此阶段才将 `contact_force_solver.py` 与 `closed_loop_dynamics.py` 引入人体主控制循环。
