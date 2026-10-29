# HARDCODE_REGISTER: 全工程硬编码与预设参数审计登记表

**审计基准 Commit**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计时间**：2026-10-29  
**所属门禁**：Environment Gate 01 — Final Architecture Audit (Audit C)  

---

## 1. 分类定义与原则说明

全工程所有常数、预设阈值与经验参数严格划分为以下 6 类，严禁将所有常数简单粗暴地判定为缺陷：

1. **`DEMO_CONFIGURATION` (演示配置)**：针对当前 Course B（坡道演示）设置的起点、终点和摄像机视角。属于合理测试场景装配参数。
2. **`VALID_PHYSICAL_PARAMETER` (合理物理/解剖学生理常数)**：符合人体测量学（Anthropometry）或经典物理常数的客观真值（如人体质量 70kg、重力加速度 9.81m/s²、脚掌长 22cm 等）。
3. **`CONFIGURATION_LIMITATION` (配置局限性)**：当前以默认常量形式提供，但在数据结构上已留有参数接口，仅需提升为更高层级配置。
4. **`ARCHITECTURAL_COUPLING` (架构耦合与结构限制)**：算法结构深度绑定了单轴走廊或固定方向，妨碍了任意 3D 轨迹通用化。
5. **`INCORRECT_ASSUMPTION` (不恰当假设)**：基于历史单一平地或简单地形作出的简化推论，在复杂地形中存在失效隐患。
6. **`DEFECT` (真实缺陷)**：违反接口规范或导致逻辑错误的硬编码。

---

## 2. 硬编码与预设参数全量审计表

| ID | 文件路径 | 函数/方法/代码位置 | 实际值或表达式 | 当前用途 | 分类判定 | 是否妨碍通用化 | 建议接口边界 / 推荐后续阶段 |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **HC-01** | `playground_terrain_traversal.py` | `generate_dynamics_playground_environment_gate01_u3_blend():604-616` | `start_pos=(0.0, 10.20, 0.0)`, `target_pos=(0.0, 22.40, 0.0)`, `nominal_stride_m=0.30` | 定义 Course B 坡道测试路线起点终点 | **`DEMO_CONFIGURATION`** | 否（仅为测试场景入参） | 保持为测试场景入参；后续由上层 Navigation/Waypoint 系统传入。 |
| **HC-02** | `terrain_walk.py` | `plan_terrain_footsteps():243-245` | `corridor_x = x0`, `left_x = corridor_x - step_width/2`, `right_x = corridor_x + step_width/2` | 将双足搜索横向坐标锁定在恒定常数 `x0`（当前为 0.0m） | **`ARCHITECTURAL_COUPLING`** | **是（无法转弯或曲线行走）** | **Task 7A-3 / 7C**：解耦单一 X 轴走廊，引入 2D/3D 航向切向量 $\mathbf{t}(s)$ 与法向量 $\mathbf{n}(s)$。 |
| **HC-03** | `terrain_walk.py` | `plan_terrain_footsteps():271` | `curr_lead_y += stride` | 沿世界 +Y 轴单向前进步进 | **`ARCHITECTURAL_COUPLING`** | **是（无法沿任意方向行走）** | **Task 7A-3**：将单轴 Y 步进改为沿参考轨迹弧长 $s$ 步进。 |
| **HC-04** | `terrain_walk.py` | `_adjust_footfall_for_seams_and_edges():188-190` | `Heel: y - 0.07m`, `Toe: y + 0.15m`, 刚性足长 $0.22\text{ m}$ | 脚掌前后边缘相对于踝关节的物理包围盒边界 | **`VALID_PHYSICAL_PARAMETER`** | 否（符合人体解剖学生理尺度） | 可提升为 `CharacterMorphology` 参数类；建议在 Phase 7 架构优化中提取。 |
| **HC-05** | `terrain_walk.py` | `execute():891-893` | `res_heel = query(sw_x, sw_y - 0.07)`, `res_toe = query(sw_x, sw_y + 0.15)` | 摆动脚下落时探查脚跟与脚尖最大越障高程 | **`VALID_PHYSICAL_PARAMETER`** | 否（真实网格避障几何） | 保持。 |
| **HC-06** | `terrain_walk.py` | `execute():903` | `min_clearance_amp = 0.045` (45mm) | 摆动脚正弦越障抬升基准裕度 | **`VALID_PHYSICAL_PARAMETER`** | 否（行走自然度参数） | 可接入 `TerrainRouteInput.base_clearance_m`。 |
| **HC-07** | `terrain_walk.py` | `execute():914-921` | `swing_relax_amp = 19.0` (台阶), `22.0` (坡道), `8.0` (平地) | 摆动脚中段踝关节跖屈放松经验角度，防止小腿-脚踝 ROM 冲突 | **`CONFIGURATION_LIMITATION`** | 否（纯几何放松，无破坏性） | 未来在 Phase 7E 由自适应多关节优化器统一规划。 |
| **HC-08** | `terrain_walk.py` | `execute():1007-1017` | `pelvis_drop_stairs=0.12`, `pelvis_drop_uphill=0.088`, `pelvis_drop_downhill=0.098`, `pelvis_drop_flat=0.035` | 依据坡度梯度的骨盆下沉量（防止腿部伸直奇异态与骨骼拉伸） | **`CONFIGURATION_LIMITATION`** | 否（参数化解耦良好） | 已经由 `TerrainRouteInput` 参数化定义，属于合法配置。 |
| **HC-09** | `terrain_walk.py` | `execute():1035-1042` | `forward_lean = torso_lean_uphill_deg * (slope_pitch / 15.0)` | 躯干前倾角与坡度比例线性映射 | **`CONFIGURATION_LIMITATION`** | 否（保证上下坡平衡姿态） | 保持；后续接入 CoM 动力学力矩反馈时自适应调节。 |
| **HC-10** | `terrain_walk.py` | `execute():1049-1051` | `arm_l_rx = -arm_swing_amp * sin(2*pi*gait_u)`, `arm_r_rx = ...` | 对侧前后摆臂简谐运动 | **`CONFIGURATION_LIMITATION`** | **是（无法做抓握/避障/平衡手）** | **Phase 7B 核心重构项**：解除手臂 FK 简谐摆动，改为上肢独立任务空间控制。 |
| **HC-11** | `kinematic_bridge.py` | `execute_frame():473` | `if not surfaces: default_gz = 0.0; surfaces.append(EnvironmentalSurface(surface_id="ground", ...))` | 当场景无任何表面时生成默认水平平地兜底 | **`CONFIGURATION_LIMITATION`** | 否（实证已确认不污染足部接触记录） | 保持兼容兜底；当连接真实网格时该分支休眠。 |
| **HC-12** | `kinematic_bridge.py` | `execute_frame():507` | `"lifecycle": ContactLifecycle.ESTABLISHED if dist <= 0.015 else ContactLifecycle.TOUCHDOWN` | 手臂主动触碰障碍物表面的休眠分支中引用不存在的 `TOUCHDOWN` | **`DEFECT` (已登记休眠缺陷)** | **是（若激活手臂接触会导致崩溃）** | **Phase 7B 必修项**：将 `ContactLifecycle.TOUCHDOWN` 修正为合法枚举 `CANDIDATE`。 |
| **HC-13** | `contact_model.py` | `DEFAULT_LIMB_LOCAL_ANCHORS` | `foot_L/R: (0.0, 0.015906, -0.068169)` | 补偿脚骨 -13.134° 倾角的足底接触局部锚点 | **`VALID_PHYSICAL_PARAMETER`** | 否（19 骨骼几何校准真值） | 经 Unit 4 严格数学校验，静止误差 $< 0.001\text{ mm}$，永久固化。 |
| **HC-14** | `rigid_link.py` | `HUMAN_BODY_MASS_KG` | `70.0` kg | 人体全身刚体连杆总质量基准 | **`VALID_PHYSICAL_PARAMETER`** | 否（标准人体测量学常量） | 保持。可作为 PipelineConfig 的配置项暴露。 |
| **HC-15** | `forward_dynamics.py` | `gravity_acceleration` | `-9.81` m/s² | 标准重力加速度常量 | **`VALID_PHYSICAL_PARAMETER`** | 否（物理标准常量） | 保持。 |
| **HC-16** | `whole_body_controller.py` | `leg_targets` | `[("L", targets.foot_L), ("R", targets.foot_R)]` | 左右腿二元硬编码分支 | **`VALID_PHYSICAL_PARAMETER`** | 否（双足人形机器人固定生理构型） | 保持。 |
| **HC-17** | `playground_terrain_traversal.py` | `ensure_ramp_corridor_ground_surfaces():460-520` | `verts = [(-3.0, 8.5, ...), ...]` | 在场景中自动补全引桥与出口平地网格，确保落点 100% 命中真实网格 | **`DEMO_CONFIGURATION`** | 否（场景辅助构建器） | 属于装配层代码，不侵入运动核心。 |

---

## 3. 关键架构评估结论

1. **阻碍通用化的关键架构耦合**：
   - **`HC-02` 与 `HC-03`**：`plan_terrain_footsteps` 中将横向走廊固定为 `x0`，且前进方向仅限单向 $+Y$ 轴。这决定了当前系统是一个**单向走廊地形通行系统**，尚不能直接输入带有转弯、折返的 3D 曲线轨迹（定位于 Task 7A-3 扩展）。
2. **Phase 7B 上肢独立控制的直接阻塞项**：
   - **`HC-10`**：手臂前后摆动目前在 `TerrainWalkAction` 中被硬编码为纯 FK 简谐摆动，直接占据了手臂姿态。进入 Phase 7B 时，必须将上肢从 `TerrainWalkAction` 中解耦，移交给独立的手臂控制器。
   - **`HC-12`**：`kinematic_bridge.py:507` 处的休眠 `TOUCHDOWN` 引用在 Phase 7B 激活手臂与环境接触时必须修正为 `CANDIDATE`。
3. **参数合理性结论**：
   - 全身质量 70kg、足底局部锚点、足长 22cm 均为**合理生理与解剖学参数**，不存在无依据的伪造或魔法数字。
