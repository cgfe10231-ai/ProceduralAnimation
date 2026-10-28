# Environment Gate 01 / Repair Unit 3: Counter-Factual Verification Summary

## 1. 实验背景与核心目标

在 **Environment Gate 01 / Unit 3** 中，系统的核心任务是将由 live Blender evaluated mesh 构建的 BVH 树适配器（`BlenderMeshEnvironmentAdapter`）无缝接入到现有的 19 骨骼人体连续运动控制主链（`MotionPlanner` $\to$ `TerrainWalkAction` $\to$ `KinematicBridgeExecutor` $\to$ `WholeBodyController` $\to$ `Rig/IK/FK`）。

为了彻底杜绝“表象接入、底层仍走解析硬编码”的虚假接入，本单元设立了**反事实物理变异实验（Counter-Factual Physical Mutation Experiment）**：
- **实验 A（基准环境，Unperturbed）**：基于 `output/dynamics_playground.blend` 场景，在 `Playground_Surfaces` 网格集合下执行连续 Course B 斜坡越障，生成 `output/dynamics_playground_environment_gate01_u3.blend`。
- **实验 B（几何微扰环境，Perturbed）**：对 `Playground_Surfaces` 中的斜坡几何网格执行真实顶点提升微扰（`delta_z = +0.05m`，斜坡顶台高度由 1.3397m 提升至 1.3897m），生成 `output/dynamics_playground_environment_gate01_u3_perturbed.blend`。
- **反事实对比目标**：证实 Mesh 几何发生微扰后，主运动规划管线输出的网格查询接触点、规划足部目标高度、Root 轨迹高度以及骨骼姿态均发生相应物理偏移；同时证实旧版解析查询器（`DynamicsEnvironmentQuery` 无 Mesh 适配模式）对该网格微扰完全脱敏（Insensitive，0 偏移），实证真实 Mesh 驱动的必要性与有效性。

---

## 2. 反事实对比数据矩阵 (Experiment A vs Experiment B)

| 物理与几何指标 | 实验 A (Unperturbed Baseline) | 实验 B (Perturbed Counter-Factual) | 差异量 ($\Delta$) | 物理含义与实证结论 |
| :--- | :---: | :---: | :---: | :--- |
| **场景文件** | `dynamics_playground_environment_gate01_u3.blend` | `dynamics_playground_environment_gate01_u3_perturbed.blend` | 独立文件 | 两份产物均独立持久化并完全可播放 |
| **斜坡顶台网格 Z 坐标** | $1.3397\text{ m}$ | $1.3897\text{ m}$ | $+0.0500\text{ m}$ | 真实网格顶点发生物理位移 |
| **Mesh 查询命中 Z (Y=17.0m)** | $1.3397\text{ m}$ | $1.3897\text{ m}$ | $+0.0500\text{ m}$ | BVH 树即刻捕获顶点位移，0 滞后 |
| **解析查询器命中 Z (Y=17.0m)** | $1.3397\text{ m}$ | $1.3397\text{ m}$ | $0.0000\text{ m}$ | **解析模型对网格修改完全脱敏** (证实旧系统盲区) |
| **Footstep 规划落点 Z (顶台区)** | $1.3397\text{ m}$ | $1.3897\text{ m}$ | $+0.0500\text{ m}$ | 运动规划足部落点精确贴合真实网格 |
| **Root 轨迹最高点 Z** | $2.2618\text{ m}$ | $2.3118\text{ m}$ | $+0.0500\text{ m}$ | 骨盆与质心高度自适应随地形抬升 |
| **下坡段 (Y in [18, 21.68]) 坡度** | $20.00^\circ$ | $20.68^\circ$ | $+0.68^\circ$ | 表面法向量由真实网格实时计算产生 |
| **下坡段足部俯仰角 (Pitch)** | $-20.00^\circ$ | $-20.68^\circ$ | $-0.68^\circ$ | 摆动脚着地姿态随斜面倾角物理自适应 |
| **运动总帧数** | 700 帧 (24 FPS, 29.17s) | 700 帧 (24 FPS, 29.17s) | 0 帧 | 步频与步态周期保持稳定连续 |
| **不可达步数 (Unreachable)** | 0 | 0 | 0 | 5cm 微扰在人体生理可达范围内 |
| **Root C0 最大位移** | $0.0333\text{ m/frame}$ | $0.0334\text{ m/frame}$ | $< 0.0001\text{ m}$ | 远低于 $0.12\text{ m/frame}$ 门禁，零空间瞬移 |
| **锁定脚滑移 (Locked Drift)** | $1.144 \times 10^{-5}\text{ m}$ | $1.144 \times 10^{-5}\text{ m}$ | $< 10^{-8}\text{ m}$ | 远低于 $0.1\text{ mm}$ 门禁，支撑脚牢固锁定 |
| **骨骼拉伸 (Bone Stretch)** | $1.51 \times 10^{-6}\text{ m}$ | $1.51 \times 10^{-6}\text{ m}$ | $< 10^{-8}\text{ m}$ | 远低于 $0.1\text{ mm}$ 门禁，刚性骨骼严格保持 |
| **关节 ROM 违规数** | 0 处违规 | 0 处违规 | 0 | 人体生理限位完全满足 |

---

## 3. 伴随实证产物与日志清单

- `output/dynamics_playground_environment_gate01_u3.blend`：基准连续网格越障场景（700 帧，双场景，完整控制器链）。
- `output/dynamics_playground_environment_gate01_u3_perturbed.blend`：反事实几何微扰场景（700 帧，物理自适应）。
- `docs/evidence/environment_gate01_ru3/u3_execution_summary.json`：实验 A 执行元数据摘要。
- `docs/evidence/environment_gate01_ru3/u3_perturbed_execution_summary.json`：实验 B 执行元数据摘要。
- `docs/evidence/environment_gate01_ru3/u3_contact_state_records.json`：实验 A 逐帧接触状态记录（700 帧）。
- `docs/evidence/environment_gate01_ru3/u3_perturbed_contact_state_records.json`：实验 B 逐帧接触状态记录（700 帧）。
- `docs/evidence/environment_gate01_ru3/u3_control_chain_diagnostics.json`：实验 A 逐帧 6 阶段控制链完整诊断数据。
- `docs/evidence/environment_gate01_ru3/u3_perturbed_control_chain_diagnostics.json`：实验 B 逐帧 6 阶段控制链完整诊断数据。

---

## 4. 结论

通过反事实微扰实验，确凿证实：
1. **真实几何耦合性**：当且仅当场景实际 Mesh 发生物理改变时，`BlenderMeshEnvironmentAdapter` 能够 100% 捕获几何变化并驱动 `MotionPlanner` 做出真实的运动响应。
2. **零硬编码依赖**：运动主链中不存在任何针对地形高度的硬编码数值，所有落点、法向量与着地倾角均由单一实际 Mesh 查询（`query_ground_support_at`）决定。
3. **管线安全性**：在接入真实 Mesh 查询后，历史成熟的 6 阶段人体动力学/运动学管线完全零退化，700 帧无瞬移、无拉伸、无 ROM 违规。
