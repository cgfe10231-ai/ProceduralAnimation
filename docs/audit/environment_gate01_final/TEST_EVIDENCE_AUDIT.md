# ProceduralAnimation — Audit G: 测试真实性与覆盖缺口审计报告

**文档标识**：`docs/audit/environment_gate01_final/TEST_EVIDENCE_AUDIT.md`  
**审计基准 HEAD**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计性质**：Environment Gate 01 最终独立架构审计（Audit G）

---

## 1. 测试真实性定性与分类矩阵

本审计针对仓库内全部核心测试进行深入源码审查，重点核实测试执行的真实性、测试覆盖的有效性，并严格区分 **Mock 合同测试（Mock Contract Tests）** 与 **真实场景 BVH 集成测试（Real Scene BVH Integration Tests）**。

### 1.1 测试方法论真伪核查标准
1. **真实生产调用验证**：测试是否直接调用生产类与方法（如 `KinematicBridgeExecutor.execute_frame()`、`TerrainWalkAction.execute()`、`BlenderMeshEnvironmentAdapter.ray_cast_ground()`），还是仅在测试脚本内部复制一段公式进行自我验证？
   * **核实结论**：所有通过注册表的测试均真实导入并调用 `src/` 下的生产函数，不存在脱离生产代码的纯公式复刻。
2. **Mock 测试与真实场景测试边界**：
   * `tests/test_environment_gate01_unit4_closure.py`：**Mock 合同测试**。使用 `MockMeshEnvironmentQuery` 注入特定的 `SurfaceQueryResult`（如垂直墙面 `allows_regular_support=False`、空网格集合 `success=False`），专门验证 `KinematicBridgeExecutor` 的条件分支与状态回退逻辑。其证明范围是 **控制流与状态机语义合同**，而非真实 Blender 渲染。耗时约 1.90s。
   * `tests/test_environment_gate01_unit3.py`、`test_environment_gate01_u3_s1.py`、`test_environment_gate01_u3_s2.py`、`test_environment_gate01_unit4.py`：**真实场景 BVH 集成测试**。在无头 Blender 中真实构建地形 Mesh、创建 19 骨骼 Armature、构建 BVH 树，运行 462 帧完整运动管线，导出 `.blend` 文件并逐帧检验骨骼位姿、着地高程、连续性与接触间隙。
3. **阈值篡改与放宽排查**：
   * 严密核对 `src/rig/joint_limits.py`、`tests/test_environment_gate01_u3_s2.py`（$\Delta z \le 0.005\,\text{m}$ 间隙要求）、`tests/test_environment_gate01_u3_s1.py`（$\Delta v < 0.1\,\text{m/s}$ 连续性要求）。
   * **核实结论**：Unit 1 至 Unit 4 期间 **严禁且未发生任何放宽生理阈值或扩大容差以掩盖缺陷的行为**。

---

## 2. 真实测试执行数据（现场验证记录）

于 2026-10-29 在真实环境（Blender 5.1 Python 3.11 环境）重新完整执行四级回归套件，全量保留真实日志与退出码：

| 测试级别 (Tier) | 计划套件数 | 实际执行套件数 | 通过数 (PASS / AUTO_PASS) | 失败数 (FAIL) | 跳过数 (SKIP) | 真实耗时 | 退出码 (Exit Code) | 真实性定性 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`quick`** | 18 | 18 | 18 | 0 | 0 | 44.53s | **0** | **真实有效 (通过)** |
| **`physics`** | 21 | 21 | 21 | 0 | 0 | 83.07s | **0** | **真实有效 (通过)** |
| **`motion`** | 11 | 11 | 11 | 0 | 0 | 45.42s | **0** | **真实有效 (通过)** |
| **`full`** | 35 | 35 | 35 | 0 | 0 | 136.34s | **0** | **真实有效 (通过)** |

---

## 3. Environment Gate 01 单元测试逐项审计明细

### 3.1 Unit 1 & Unit 2: BVH 查询与网格变更检测
* **测试文件**：[`tests/test_mesh_environment_query.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_mesh_environment_query.py)
* **执行方式**：Blender 无头独立进程执行。
* **验证点**：
  * 平地、斜坡、台阶三角网格上的 BVH 射线投射与高程计算；
  * 网格顶点位移与拓扑修改后的 BVH 自动失效与重建；
  * `allows_regular_support` 判据（法线 $n_z \ge 0.5$）；
  * 阻挡墙面法线返回。
* **审计判定**：**已验证 (PASS)**。真实调用 `bmesh` 与 `mathutils.bvhtree.BVHTree`。

### 3.2 Unit 3: 真实网格与 19 骨骼人形管线集成
* **测试文件**：[`tests/test_environment_gate01_unit3.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_environment_gate01_unit3.py)
* **执行方式**：Blender 无头执行，生成 462 帧全管线运动。
* **验证点**：
  * 真实 Mesh 环境查询无缝替换旧解析环境；
  * 足部落点自动适应 Mesh 表面高程变化；
  * 反事实验证（Counter-factual Verification）：在网格被移开或修改时，落点产生对应几何位移，证明查询真实生效而非假象。
* **审计判定**：**已验证 (AUTOMATED_PASS, Visual Inspection Required)**。

### 3.3 Unit 3-S1: Root 前进连续性修复 (C1 速度连续性)
* **测试文件**：[`tests/test_environment_gate01_u3_s1.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_environment_gate01_u3_s1.py)
* **执行方式**：Blender 无头执行。
* **验证点**：
  * 检测 Frame 0 至 462 的 Root 前进速度曲线 $v_y(t)$；
  * 验证换步交替点速度跌落消除，最大速度跳变 $\Delta v_y < 0.1\,\text{m/s}$。
* **审计判定**：**已验证 (AUTOMATED_PASS, Visual Inspection Required)**。

### 3.4 Unit 3-S2: 摆动腿到支撑腿着地连续性修复 (C0/C1 着地连续性)
* **测试文件**：[`tests/test_environment_gate01_u3_s2.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_environment_gate01_u3_s2.py)
* **执行方式**：Blender 无头执行。
* **验证点**：
  * 摆动脚在着地瞬间与真实网格高程的绝对间隙 $\Delta z \le 0.005\,\text{m}$；
  * 锁定支撑脚在世界坐标中的零漂移（Stance Foot Lock Drift $< 0.001\,\text{m}$）；
  * 切换帧前后坚直加速度跳变抑制。
* **审计判定**：**已验证 (AUTOMATED_PASS, Visual Inspection Required)**。

### 3.5 Unit 4: 接触高程与接触状态一致性
* **测试文件**：[`tests/test_environment_gate01_unit4.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_environment_gate01_unit4.py)
* **执行方式**：Blender 无头执行。
* **验证点**：
  * 三坐标严密区分：踝关节 IK 目标 (Point A) vs 真实地面几何点 (Point B) vs 人形足底接触锚点 (Point C)；
  * `ContactRecord` 记录真实接触网格名称（`surface_id`）、法线与高程。
* **审计判定**：**已验证 (PASS)**。

### 3.6 Unit 4 Closure: 接触合同关闭 (非支撑表面拒绝与空网格拒绝)
* **测试文件**：[`tests/test_environment_gate01_unit4_closure.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_environment_gate01_unit4_closure.py)
* **执行方式**：Blender 独立单元测试。
* **验证点**：
  * 垂直立面（`allows_regular_support=False`）即使查询成功，也强制设置接触生命周期为 `BROKEN`，禁止建立虚假支撑；
  * 真实 Mesh 查询失败（空网格或超界）时，严禁解析地面回退伪造接触，接触生命周期为 `BROKEN`，`surface_id="none"`。
* **审计判定**：**已验证 (PASS)**。5 项断言全部通过。

---

## 4. 覆盖缺口与风险提示 (Coverage Gaps)

1. **弯曲与任意路径测试覆盖缺失**：
   * 当前所有地形步行测试（`test_environment_gate01_unit3`、`unit4` 等）均在 Course B（固定 $X=0.0$ 走廊，沿 $+Y$ 前进）中运行。
   * **缺口**：对于任意弯曲路径、转向横移（Sidestep）或后退步态，当前自动化测试套件 **覆盖为 0**（由于底层 `plan_terrain_footsteps` 尚未支持多轴导航）。
2. **闭环受力与倾倒测试覆盖缺失**：
   * 尽管 `test_task6gd_contact_force_solver.py` 测试了 QP 接触力，但测试对象仅为虚拟刚体盒子，未测试 19 骨骼人体在足底打滑、外力推搡下的动力学响应。
3. **目视验收防线提示**：
   * 标记为 `AUTOMATED_PASS (Visual Inspection Required)` 的测试（如 `unit3`、`u3_s1`、`u3_s2`）代表其数值与连续性指标在代码层通过断言，但最终艺术性与步态自然度仍需在 Blender 视口中由用户目视审查。
