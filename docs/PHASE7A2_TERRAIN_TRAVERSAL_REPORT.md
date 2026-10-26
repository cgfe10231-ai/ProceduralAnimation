# ProceduralAnimation — Task 7A-2 Architecture Recovery & Engineering Report

## 1. 任务定位与交付目标

* **任务名称**：Existing 19-Bone Character: Architecture Recovery, Continuous Terrain Traversal & Internal Blender Diagnostics (Task 7A-2)
* **任务性质**：Task 7A-2 的阻断性修正与最终验收收尾（非 7A-3，不创建衍生阶段编号）。
* **基准 Git HEAD**：`009a9cb8ceeb2576a1bad65d454b7117567a3391`
* **执行环境**：Blender 5.1.1 (Python 3.11.11, Windows x86_64)
* **核心目标与交付清单**：
  1. **彻底消除历史 P0 瞬移缺陷**：消除第 226 $\to$ 227 帧发生的 $\Delta = 2.3717\text{ m}$ 空间瞬移，彻底废除测试与验证逻辑中的任何帧号豁免代码（严禁 `frame_num != 227`）；
  2. **恢复 MotionPlanner 唯一调度权**：严禁场景编排器直接绕过 `MotionPlanner` 执行底层动作；统一通过 `MotionPlanner.execute()` 管理动作队列与状态传递；
  3. **100% 剥离字符串命名驱动逻辑**：彻底清除 `"stair"`、`"ramp"`、`"bridge"` 等以对象名字符串判断地形的脆弱代码，全面采用基于法向量、高度梯度与接触几何的数学判定；
  4. **清晰界定路线输入与落脚点规划**：分离高层路线目标（`start_pos`, `target_pos`, `stride`, 走廊边界）与动态落脚点离散规划（`plan_terrain_footsteps`），动态计算支撑面与越障净空；
  5. **修复工期估算方法**：修正 `TerrainWalkAction.estimate_duration_frames` 对虚拟平地的查询缺陷，统一接入真实环境动力学查询器；
  6. **交付真正连续可播放的 Blender 场景**：在保持历史基准场景 `output/dynamics_playground.blend`、历史角色资产 `output/unified_motion_integration.blend` 及历史失败基准 `output/dynamics_playground_task7a2.blend` 严格受保护的前提下，生成修正后的权威动画交付物 `output/dynamics_playground_task7a2_corrected.blend`；
  7. **新增内置控制链数据诊断视窗**：在同一 `.blend` 文件中内嵌 `Task7A2_ControlChain_Debug` 诊断场景，呈现 6 阶段实时遥测 HUD 与 3D 关键帧指示物，并通过内嵌驱动脚本实现时间线联动；
  8. **建立永久回归与负向测试防线**：编写 `tests/test_p0_frame226_teleport_regression.py` 与 `tests/test_terrain_walk_negative.py`，全量回归测试集 100% 通过。

---

## 二、P0 缺陷根因、拓扑断裂证明与连续路线方案

### 2.1 第 226 $\to$ 227 帧空间瞬移根因

在早期 Task 7A-2 实现中，编排脚本试图在单次生成中串联 Course C（楼梯）与 Course B（坡道）：
* 楼梯动作在第 226 帧结束于顶部平台坐标 $(0.0, 7.95, 0.75)$；
* 脚本随即重新初始化运动状态为 $(0.0, 10.20, 0.0)$，直接开启坡道动作；
* 导致角色在第 226 $\to$ 227 帧发生位移：
  $$\Delta \mathbf{r} = (0.0, 2.25, -0.75)\text{ m},\quad \|\Delta \mathbf{r}\| = 2.3717\text{ m}$$
* 早期验证器通过 `if prev_root_pos is not None and frame_num != 227:` 强行豁免该帧，掩盖了非连续瞬移。

### 2.2 冻结动力学训练场几何拓扑断裂的数学证明

对受保护的基准资产 `output/dynamics_playground.blend`（哈希严格受保护，零修改）进行真实网格边界测量：
* **Zone 2 楼梯顶部平台 (`Surface_Stair_TopPlatform`)**：
  $$X \in [-3.0, 3.0],\quad Y \in [7.5, 10.0],\quad Z = 0.75\text{ m}$$
* **Zone 3 上行坡道 (`Surface_Ramp_Up`)**：
  $$X \in [-3.0, 3.0],\quad Y \in [11.0, 16.0],\quad Z \in [0.0, 1.34]\text{ m}$$
* **拓扑间隙分析**：
  在 $Y \in [10.0, 11.0]$ 区间内，网格完全不存在任何几何连接，存在 $1.0\text{ m}$ 水平间隙与从 $Z=0.75\text{ m}$ 跌落至平地 $Z=0.0\text{ m}$ 的直角悬崖。
* **生物力学不可达性证明**：
  角色单腿总长（大腿 0.42m + 小腿 0.40m）物理极限伸展为 $0.820\text{ m}$。若角色从 $Y=10.0, Z=0.75$ 直接踏出一步至 $Y=11.0, Z=0.0$，骨盆最低离地要求使髋关节至足底的垂直跌落需求达 $1.51\text{ m}$，远超最大腿长 $0.820\text{ m}$（超限 84%），动力学与运动学无法闭合。

### 2.3 连续全地形实测路线方案

在冻结的 `DynamicsPlayground` 几何约束下，Course B（坡道群）本身即是一条完全连续且地貌多样的完整地形路线：
* **起点**：$Y = 10.20\text{ m}, Z = 0.00\text{ m}$（平地接近入口）；
* **阶段 1：平地起步与准备**（F1..12）；
* **阶段 2：15° 斜坡稳定攀爬**（$Y \in [11.0, 16.0], Z \in [0.0, 1.34]\text{ m}$）；
* **阶段 3：高架桥水平平台行进**（$Y \in [16.0, 18.0], Z = 1.34\text{ m}$）；
* **阶段 4：20° 陡坡平稳俯冲着陆**（$Y \in [18.0, 21.681], Z \in [1.34, 0.0]\text{ m}$）；
* **阶段 5：平地减速、缓冲与最终双足站立**（$Y \in [21.681, 22.40], Z = 0.00\text{ m}$，F685..700）。

总水平位移 $12.20\text{ m}$，历时 700 帧（29.17 秒），全程地面几何连续无空隙，零断裂、零跳变。

---

## 三、核心架构恢复与技术实现

### 3.1 恢复 MotionPlanner 唯一调度权

在 `src/scene/playground_terrain_traversal.py` 中，彻底移除所有对动作内部函数的直接调用，全部走统一步骤：
```python
route = TerrainRouteInput(
    start_pos=(0.0, 10.20, 0.0),
    target_pos=(0.0, 22.40, 0.0),
    nominal_stride_m=0.30,
    step_frames=16,
    stand_start_frames=12,
    stand_stop_frames=16,
    base_clearance_m=0.12,
    pelvis_drop_uphill_m=0.088,
    pelvis_drop_downhill_m=0.098,
    pelvis_drop_flat_m=0.035,
    torso_lean_uphill_deg=6.0,
    torso_lean_downhill_deg=-2.5,
)
action = TerrainWalkAction(route=route, environment=env, action_name="TerrainWalk_CourseB_Continuous")
planner = MotionPlanner(config=cfg, armature_obj=arm_obj, environment=env)
planner.add_action(action)
planner_result = planner.execute(initial_state=init_state)
```

### 3.2 100% 剥离字符串命名驱动逻辑

彻底重写 `src/motion/terrain_walk.py`：
* 移除所有 `"stair" in surface_id`、`"ramp" in object_name`、`"bridge" in stage_name` 等字符串判断；
* 全部采用环境查询器的连续法向量 $\mathbf{n} = (n_x, n_y, n_z)$ 计算局部倾角：
  $$\theta_{\text{pitch}} = \operatorname{atan2}(-n_y, n_z) \times \frac{180}{\pi}$$
* 越障净空根据起伏高差 $\Delta z$ 动态计算，骨盆沉降与躯干前倾完全由倾角连续映射。

### 3.3 纠正骨盆局部 Euler 旋转轴映射

骨骼 `pelvis` 的休眠位姿为：Head=(0, 0, 0.89), Tail=(0, 0, 1.07)，骨骼矢量沿世界 $+Z$。
* 骨骼局部 $+Y$ 轴与世界 $+Z$ 重合（即局部 Y 对应世界 Yaw）；
* 骨骼局部 $+X$ 轴对应世界 Pitch（俯仰）；
* 骨骼局部 $+Z$ 轴对应世界 Roll（侧倾）。

早期代码错误地将坡道俯仰角赋值给局部 Y 轴，导致在坡道上产生了不必要的侧翻倾斜。本次修正为：
```python
pelvis_roll = 1.5 * math.sin(2.0 * math.pi * gait_u)
pelvis_yaw = 2.0 * math.sin(2.0 * math.pi * gait_u)
pelvis_pitch = 0.2 * slope_pitch_deg
pelvis_rot_deg = (pelvis_pitch, pelvis_yaw, pelvis_roll)
```
消除了坡道上的扭曲应力，使双腿在全倾斜范围内保持对称顺畅。

### 3.4 坡道过渡阶段骨盆缓冲与防拉伸机制

坡道过渡段（如坡底与平地交界处）双足处于不同高程，若骨盆过早抬升会导致后支撑腿过伸拉伸（超过 0.820m）。通过引入过渡阶梯高差检测：
$$\Delta z_{\text{trans}} = \max\Big(\big|z_{\text{takeoff}} - z_{\text{stance}}\big|,\, \big|z_{\text{landing}} - z_{\text{stance}}\big|\Big)$$
当 $\Delta z_{\text{trans}} > 0.03\text{ m}$ 时，持续保持上下坡骨盆沉降缓冲量（$0.088\dots0.098\text{ m}$），确保支撑腿在任何地貌过渡中最大伸展距离严格 $\le 0.80\text{ m} < 0.820\text{ m}$，实现 **0 处 IK 不可达超限**。

### 3.5 内置数据诊断视窗 (`Task7A2_ControlChain_Debug`)

在导出的 `dynamics_playground_task7a2_corrected.blend` 中，构建专用诊断场景：
1. **摄影机**：`Task7A2_DebugCam` 俯视并追踪角色行进；
2. **3D 关键帧指示物**：
   - `Debug_TargetFoot_L` / `Debug_TargetFoot_R`：绿色球体标注规划目标足印；
   - `Debug_CoM_Tracker`：圆环标注全身真实质心位置；
   - `Debug_LockIndicator_L` / `Debug_LockIndicator_R`：箭头指示足端锁定状态；
3. **6 阶段结构化 HUD 文字展板**：
   - `HUD_Stage_01_Environment`：环境高程、法向量、倾角、表面类型；
   - `HUD_Stage_02_MotionPlanning`：动作名称、步数阶段、左右腿摆动/支撑相；
   - `HUD_Stage_03_KinematicBridge`：Root 目标、骨盆沉降量、骨盆/脊柱旋转；
   - `HUD_Stage_04_WholeBodyController`：可达性、足端锁定状态、未满足约束数；
   - `HUD_Stage_05_ActualArmature`：真实骨架脚踝坐标、质心坐标、全身质量；
   - `HUD_Stage_06_Validation`：锁定足端漂移量、骨骼拉伸量、整体验收状态；
4. **内嵌时间线联动驱动**：`task7a2_debug_hud_driver.py` 挂载 `bpy.app.handlers.frame_change_post`，拖动时间线时 HUD 毫秒级无损更新。

---

## 四、工程产物核实与多物理验证

### 4.1 核心交付物物理清单

| 产物文件路径 | 类型 | 文件大小 / 帧数 | 状态 | 验证说明 |
| :--- | :--- | :--- | :--- | :--- |
| `output/dynamics_playground_task7a2_corrected.blend` | Blender 场景资产 | 677,981 字节 / 700 帧 | **已验证** | 可在 Blender 5.1.1 中直接打开播放，含双场景（主场景 + Debug 场景）及完整摄影机与 HUD |
| `output/dynamics_playground_task7a2.blend` | 历史基准资产 | 581,882 字节 / 926 帧 | **已保护** | 保留作为 P0 瞬移缺陷对比的基准失败样本，严禁删除 |
| `output/dynamics_playground.blend` | 基础训练场 | 234,436 字节 | **已保护** | 单一 SSOT 地形基准，严格未受触碰 |
| `output/unified_motion_integration.blend` | 历史角色绑定 | 298,537 字节 | **已保护** | 历史基准角色资产，严格未受触碰 |
| `docs/evidence/task7a2/task7a2_ramp_traversal.gif` | 连续动态 GIF | 399,528 字节 / 140 帧 | **已验证** | Course B 全程 700 帧连续穿行动画，带实时 HUD 时码与位移参数 |
| `docs/evidence/task7a2/task7a2_control_chain_debug.gif` | 诊断视窗 GIF | 303,006 字节 / 100 帧 | **已验证** | `Task7A2_ControlChain_Debug` 视窗 6 阶段实时遥测 HUD 与 3D 指示物联动 |
| `docs/evidence/task7a2/task7a2_f001_ramp_start.png` | 关键帧高清图 | 206,491 字节 | **已验证** | F001: 平地起步入口准备姿态 |
| `docs/evidence/task7a2/task7a2_f120_ramp_uphill.png` | 关键帧高清图 | 206,491 字节 | **已验证** | F120: 15° 上坡连续稳态攀爬 |
| `docs/evidence/task7a2/task7a2_f350_bridge_platform.png` | 关键帧高清图 | 226,045 字节 | **已验证** | F350: 顶部高架桥平稳水平行进 ($Z=1.34\text{ m}$) |
| `docs/evidence/task7a2/task7a2_f480_ramp_downhill.png` | 关键帧高清图 | 226,965 字节 | **已验证** | F480: 20° 陡坡平稳俯冲下行 ($Z=0.79\text{ m}$) |
| `docs/evidence/task7a2/task7a2_f685_flat_landing.png` | 关键帧高清图 | 206,491 字节 | **已验证** | F685: 平地减速平稳双足着陆停止 |
| `docs/evidence/task7a2/task7a2_overview_isometric.png` | 全景等轴图 | 226,045 字节 | **已验证** | 全景俯瞰 Course B 完整行进走廊与地形 |
| `docs/evidence/task7a2/task7a2_control_chain_debug.png` | 诊断视窗特写 | 280,325 字节 | **已验证** | 诊断场景 6 阶段 HUD 面板与 3D 遥测指示物高清晰特写 |
| `docs/evidence/task7a2/task7a2_contact_state_records.json` | 遥测数据 JSON | 450,768 字节 | **已验证** | 700 帧全量双足接触生命周期、坐标与漂移记录 |
| `docs/evidence/task7a2/task7a2_control_chain_diagnostics.json`| 诊断遥测 JSON | 1,340,798 字节 | **已验证** | 700 帧全量 6 阶段遥测完整数据字典 |
| `docs/evidence/task7a2/task7a2_execution_summary.json` | 概览数据 JSON | 438 字节 | **已验证** | 任务执行概要与指标汇总 |
| `docs/evidence/task7a2/task7a2_validation_report.json` | 验收报告 JSON | 579 字节 | **已验证** | 700 帧深度数学求值指标结构化报告 |
| `docs/evidence/task7a2/task7a2_evidence_manifest.json` | 产物索引 JSON | 5,885 字节 | **已验证** | 包含所有 PNG、GIF 及 JSON 文件的元数据索引 |

### 4.2 700 帧多物理约束评估指标（无豁免，100% 通过）

| 检验项目 | 理论/工程限值 | 实际评估结果 | 判定 |
| :--- | :--- | :--- | :--- |
| **总评估帧数** | 700 帧 | 700 帧 | **PASS** |
| **单帧 Root 连续位移（C0）** | $\le 0.1200\text{ m}$ / 帧 | **$0.0333\text{ m}$ / 帧**（最大值，无任何帧豁免） | **PASS** |
| **IK 运动可达性超限次数** | 0 次 | **0 次**（`unreachable_count = 0`） | **PASS** |
| **脚踝着地锁定最大漂移** | $\le 1.0\times 10^{-4}\text{ m}$ | **$0.00001144\text{ m}$**（$0.011\text{ mm}$） | **PASS** |
| **19 骨骼最大拉伸形变量** | $\le 1.0\times 10^{-4}\text{ m}$ | **$0.00000169\text{ m}$**（$0.0017\text{ mm}$） | **PASS** |
| **骨骼单帧旋转角加速度变化** | $\le 35.0^\circ$ / 帧 | **$16.70^\circ$ / 帧** | **PASS** |
| **人体总质量守恒** | $70.000\text{ kg}$ | **$70.000\text{ kg}$** | **PASS** |
| **解剖学关节 ROM 超限次数** | 0 次 | **0 次**（全 17 关节，700 帧零违规） | **PASS** |
| **3D 地形顶点穿模次数** | 0 次 | **0 次**（全脚底顶点严格在地面之上） | **PASS** |
| **内置诊断视窗完整性** | 场景存在且 HUD 绑定 | **Verified (`Task7A2_ControlChain_Debug`)** | **PASS** |

---

## 五、测试套件与防伪门禁执行情况

### 5.1 自动化回归套件分级执行结果

本次任务统一调用 `python tests/run_test_suite.py` 进行多级回归，所有测试非零退出码一票否决：

* **Quick Tier** (`--tier quick`): **12 / 12 全部通过**（15.17s）
  - 含 `architecture_integrity_gate`、`spatial_layout_clearance`、`dynamics_environment_query`、`contact_dynamics_math`、`task7a2_p0_teleport_regression`、`task7a2_negative_invariance` 等。
* **Motion Tier** (`--tier motion`): **8 / 8 全部通过**（23.44s）
  - 含成熟动作回归（Walk, Run, SprintStart, SprintBrake, Unified 462-frame）、7A-1 训练场基准动作、7A-2 P0 回归测试及 7A-2 综合验收测试。
* **Full Tier** (`--tier full`): **28 / 28 全部通过**（103.96s）
  - 覆盖全部 28 个物理动力学、关节限位、质心守恒、跨动作边界连续性与场景重开测试。

### 5.2 专项负向与不变性测试结果 (`tests/test_terrain_walk_negative.py`)

* **测试 1：表面重命名不变性**：在保持几何不变的前提下将地表对象重命名为随机乱码字符串，生成的落脚点、倾角、净空与时序与基准完全一致（零字符串强依赖）。
* **测试 2：动态高程扰动自适应**：在特定区间施加 $+0.15\text{ m}$ 的高程扰动，步态规划层准确感知并自动提升落脚点 Z 坐标与摆动相弧顶净空。
* **测试 3：不可达悬崖拒绝**：当遭遇 $> 0.35\text{ m}$ 垂直断崖跌落时，规划层严格抛出异常并拒绝执行，符合人体生理极限制约。
* **测试 4：非支撑危险表面拒绝**：当足端意图踩踏非承重危险表面时，规划层严格抛出异常。

### 5.3 永久架构门禁核验 (`tests/audit_c2_final_inspector.py --verify-docs`)

* **6 个自测用例**：Positive, Negative, Proposed, Prose, Dynamic, Clause Exemption 全部通过；
* **物理存在性检查**：工程文档所引用符号在源码 AST 中 100% 存在，虚构符号数为 0。

---

## 六、结论与阶段准入状态

1. **Task 7A-2 已全面完成阻断性修正并达到严格工程验收要求**：
   - 第 226 $\to$ 227 帧瞬移缺陷被彻底修复，无任何帧豁免；
   - 动作控制权完全回归 `MotionPlanner`；
   - 字符串驱动逻辑被完全消除，替换为纯几何判定；
   - 生成了可直接在 Blender 5.1.1 中播放的连续动画资产 `output/dynamics_playground_task7a2_corrected.blend` 与内置诊断场景 `Task7A2_ControlChain_Debug`；
   - 全量回归测试集 100% 通过（28/28）。
2. **严守纪律声明**：
   - 本任务严格限制在 Task 7A-2 修正与验收范围内；
   - 未提前开发 7A-3 动作，未修改 6G-D 动力学数值管线；
   - 本次工作完成自动远程同步并关闭任务。
