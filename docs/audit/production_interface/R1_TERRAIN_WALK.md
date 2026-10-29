# ProceduralAnimation — Production Interface Audit: Task 01
## 审查对象：`src/motion/terrain_walk.py`

* **任务性质**：单脚本、逐方法、只读生产接口审查（只证实漏洞，不修复、不重构、不进入 Phase 7B）。
* **Git 基准**：
  * Commit SHA：`3fc9896f6867d49a01f6d5c39b9819d51200c7a0` (`master`)
  * 复核闭环 Commit：`c2bd19696aa3c2ae31fc8408ba031ab157a166e1` (R2-CLOSE)
  * 工作区状态：除受保护的 `P2_R1_recovery.patch` 外，工作树严格干净。
* **文件修改约束**：本审计未修改生产源码与测试，未产生任何破坏性变更。

---

### 8.1 文件概况

* **文件路径**：[`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **行数规模**：1236 行
* **在系统中的定位**：连续 19 骨骼地形自适应行走动作规划与执行模块，负责从离散落脚点规划（`plan_terrain_footsteps`）到连续每帧位姿生成（`TerrainWalkAction.execute`），是当前生产管线中生成 3D 地形行走的核心驱动者。
* **类与函数清单（AST 语法树实测核对）**：
  1. `_smoothstep01(t: float) -> float` (Lines 55–59)
  2. `_smooth_bell01(t: float) -> float` (Lines 61–65)
  3. `_compute_swing_clearance_z(...) -> float` (Lines 67–83)
  4. `pitch_from_surface_normal(normal: Tuple[float, float, float]) -> float` (Lines 85–106)
  5. `TerrainStepPlan` (Lines 109–130, `@dataclass`)
  6. `TerrainRouteInput` (Lines 132–156, `@dataclass`)
  7. `TerrainTraversalSpec` (Lines 158–176, `@dataclass`)
  8. `_adjust_footfall_for_seams_and_edges(env, x, y, corridor_y_min, corridor_y_max) -> float` (Lines 178–220)
  9. `plan_terrain_footsteps(route, environment, start_frame) -> Tuple[List[TerrainStepPlan], int]` (Lines 223–401)
  10. `build_terrain_step_schedule(spec, environment, start_frame) -> Tuple[List[TerrainStepPlan], int]` (Lines 404–520)
  11. `_build_continuous_root_forward_spline(schedule, fps) -> Tuple[List[int], List[float], List[float]]` (Lines 526–565)
  12. `_evaluate_root_y_hermite(current_frame, step_k, knot_frames, knot_y, knot_v, fps) -> float` (Lines 568–608)
  13. `TerrainWalkAction(MotionAction)` (Lines 611–1236):
      * `__init__(self, spec, route, action_name, environment)` (Lines 614–649)
      * `name(self) -> str` (Lines 651–652)
      * `estimate_duration_frames(self, initial_state, config) -> int` (Lines 654–681)
      * `execute(self, initial_state, context) -> ActionExecutionResult` (Lines 683–1236)

---

### 8.2 逐方法检查表

| 类 / 方法名 | 源码行号 | 输入合同 | 输出合同 | 失败处理机制 | 状态所有权与流转 | 检查结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `_smoothstep01` | L55–L59 | 标量 `t: float` | 归一化插值因子 $[0.0, 1.0]$ | 内部执行 `clamp(0.0, 1.0)`，无异常抛出 | 纯数学无副作用局部函数 | `NO_ISSUE` |
| `_smooth_bell01` | L61–L65 | 标量 `t: float` | 正弦钟形曲线高度 $[0.0, 1.0]$ | 内部执行 `clamp(0.0, 1.0)`，无异常抛出 | 纯数学无副作用局部函数 | `NO_ISSUE` |
| `_compute_swing_clearance_z` | L67–L83 | `step_alpha`, `z_base`, `arc_z`, `z_terr_foot`, `min_clearance_amp` | 摆动脚目标高度 `sw_z_clean: float` | 数值混合，无异常抛出 | 纯数学几何混合计算 | `NO_ISSUE` |
| `pitch_from_surface_normal` | L85–L106 | 3D 表面法线向量元组 | 俯仰欧拉角（度）`pitch_deg: float` | $n_z=0$ 时 `atan2` 自动返回 $\pm 90^\circ$，防死锁 | 纯数学转换，无副作用 | `NO_ISSUE` |
| `TerrainStepPlan` | L109–L130 | 步态参数与时空关键点 | 结构化单步参数容器 | `@dataclass` 默认构造 | 纯数据载体 | `NO_ISSUE` |
| `TerrainRouteInput` | L132–L156 | 起点、终点、步长、净空等参数 | 路线配置载体 | 提供全套生理默认值，无跨字段边界校验 | 纯数据载体，但未声明对非 $+Y$ 路线的不支持 | `CONTRACT_GAP` |
| `TerrainTraversalSpec` | L158–L176 | 历史 Course B 航点与几何参数 | 航点配置载体 | Legacy 数据容器 | 纯数据载体 | `NO_ISSUE` |
| `_adjust_footfall_for_seams_and_edges` | L178–L220 | `environment`, `x`, `y`, `corridor_y_min`, `corridor_y_max` | 微调后的前向坐标 `best_y: float` | 射线未击中时回退为默认法线，返回原 `y` | 仅读取环境法线，无状态写入；但在 `plan_terrain_footsteps` L310 调用时硬编码传入中心线 `corridor_x` | `CONFIRMED_DEFECT` |
| `plan_terrain_footsteps` | L223–L401 | `TerrainRouteInput`, `EnvironmentQuery`, `start_frame` | `(schedule, total_frames)` | 初始站立或落点未命中/不可支撑时显式抛出 `ValueError` 阻断 | 生成前向步态调度，不修改 Armature | `DESIGN_LIMITATION` (写死 $X=x_0$ 走廊) / `CONTRACT_GAP` (负向行进跳步缺陷 L308) |
| `build_terrain_step_schedule` | L404–L520 | `TerrainTraversalSpec`, `EnvironmentQuery`, `start_frame` | `(schedule, total_frames)` | 查询失败时静默调用旧解析方法回退至平地（与严格拒绝合同冲突） | Legacy 调度生成 | `CONTRACT_GAP` (静默回退导致双轨制行为分歧) |
| `_build_continuous_root_forward_spline` | L526–L565 | `schedule`, `fps` | 样条节点 `knot_frames`, `knot_y`, `knot_v` | 计算一阶单调导数，无异常抛出 | 纯数学Hermite样条构建 | `NO_ISSUE` |
| `_evaluate_root_y_hermite` | L568–L608 | `current_frame`, `step_k`, 样条节点元组, `fps` | 根节点当前前向位置 `root_y: float` | 超界截断至末端节点，无异常抛出 | 纯数学插值计算 | `NO_ISSUE` |
| `TerrainWalkAction.__init__` | L614–L649 | `spec`, `route`, `action_name`, `environment` | `TerrainWalkAction` 实例 | `route` 与 `spec` 均为空时抛出 `ValueError` | 初始化只读配置参数 | `NO_ISSUE` |
| `TerrainWalkAction.name` | L651–L652 | 无 | 动作标识字符串 | 无 | 属性读取器 | `NO_ISSUE` |
| `TerrainWalkAction.estimate_duration_frames` | L654–L681 | `initial_state: MotionState`, `config: PipelineConfig` | 预估帧数 `total_frames: int` | `self.environment` 为空时静默回退为解析平地 $Z=0$ | 离散预估，无执行状态产生 | `CONTRACT_GAP` (与 `execute` 获取的真实网格环境源脱节) |
| `TerrainWalkAction.execute` | L683–L1236 | `initial_state: MotionState`, `context: MotionRuntimeContext` | `ActionExecutionResult` | 仅检查初始脚位有效性；L1080–1091 **完全忽略 `bridge_res.success`**，IK 不可达仅打 Warning | L1138 **覆盖** `MotionState.contacts`，导致真实测量数据被规划意图替换；上肢正弦摆臂硬编码强耦合 | `CONFIRMED_DEFECT` (失败传播丢失、状态覆盖、摆臂耦合) |

---

### 8.3 确认的问题 (Confirmed Findings)

#### Finding ID: FIND-T01-01 (对应 R2: FIND-R2-03)
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `execute()`
* **Line Range**: Lines 1080–1091
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 任何导致 `KinematicBridgeExecutor.execute_frame()` 返回 `success=False` 的物理或运动学异常（包括：足底接触几何违规 `NO_SUPPORT_SURFACE`、穿透超差 $>15\,\text{mm}$、气隙超差、ROM 冲突无法满足、两脚 IK 求解失效）。
* **Actual Behavior**: 
  1. `TerrainWalkAction.execute()` 在 L1080 调用 `bridge_executor.execute_frame()` 后，完全不读取、不检查 `bridge_res.success`。
  2. 仅在 `not bridge_res.wbc_result.is_all_reachable` 时向终端输出一条 `[WARN] IK Unreachable...` 并递增 `unreachable_count += 1`。
  3. 当且仅当失败属于接触几何或 ROM 冲突时，系统甚至连警告都不打印，`unreachable_count` 依然为 0。
  4. 每一帧无条件继续流转，生成下一帧；最终动作正常返回包含全部帧的 `ActionExecutionResult`，向调用方 `MotionPlanner` 隐瞒全部底层执行失败。
* **Expected Contract**: 遵循门禁与错误传播规范，当底层 `bridge_res.success == False` 时，Action 层必须能够捕获该失败；要么阻断当前动作并触发回退/报警，要么在返回的 `ActionExecutionResult` 中显式标定执行失败并携带错误详情。严禁在骨骼未成功就位或受力违规时伪造动作成功。
* **Evidence**:
  ```python
  # src/motion/terrain_walk.py:1080-1090
  bridge_res = bridge_executor.execute_frame(
      planned=planned_pose,
  )

  if not bridge_res.wbc_result.is_all_reachable:
      for uc in bridge_res.unmet_constraints:
          print(
              f"[WARN] IK Unreachable at Frame {current_frame}: "
              f"{uc.target_name} ({uc.category}) error={uc.error_amount:.4f}: {uc.description}"
          )
      unreachable_count += 1
  # -> 完全缺失 if not bridge_res.success: 判定分支
  ```
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `YES` (阻碍 Phase 7B 建立健壮的动作级错误仲裁机制；在上肢出现接触失败或解算崩溃时会静默假冒成功)
* **Suggested Minimal Repair**: 在第 1083 行后增加对 `bridge_res.success`、`bridge_res.contact_geometry_errors` 与 `bridge_res.rom_violations` 的统一汇总；记录 `failed_frames` 并在 `ActionExecutionResult.metrics` 中输出真实执行状态。

---

#### Finding ID: FIND-T01-02 (对应 R2: FIND-R2-02)
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `execute()`
* **Line Range**: Lines 1100–1138 (覆写点: Line 1138)
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 每一帧执行 L1100–1138 时。
* **Actual Behavior**: 
  Action 内部以规划目标拼装字典 `c_dict`（仅含 `foot_L` 与 `foot_R`），在 L1138 执行 `ms = ms.clone_with(contacts=c_dict, mode=mode)`，覆写了 Bridge Phase 5 通过 `enrich_motion_state_with_contacts()` 注入的 `MotionState.contacts`。
* **核实与证据区分 (R2-CLOSE-05)**:
  * **已确认事实**：`ms.contacts` 确实被 `c_dict` 覆写（`STATIC_CONFIRMED`）。
  * **实际字段影响**：
    1. 遗漏上肢：`c_dict` 仅硬编码构造左右脚，如果 Bridge/ContactModel 产生了手部接触（`hand_L`/`hand_R`），在进入 `ms.contacts` 时会被销毁；
    2. 坐标差异：`c_dict` 中的 `contact_world_xyz` 存入的是规划落点 `last_known_xyz`，而非由真实 Mesh 射线相交解算出的真实接触点 Point B；
    3. 法线差异：`surface_normal` 存入的是规划预期的目标法线，而非足底实际受力点法线；
    4. 状态锁定：`is_locked` 直接跟随规划布尔值，忽略了 Bridge 判定的 `BROKEN` 状态。
  * **仍被妥善保存的数据**：
    1. `ms.params` 中的 `support_type`、`supporting_limbs`、`active_contact_count`、`support_polygon_2d` 未被覆盖，依然完整保留；
    2. `bridge_res.multi_contact` 与 `bridge_executor.last_multi_contact` 保持完整对象，未被破坏。
  * **下游影响与复现性**：在当前双脚平地与地形测试中，未引发运行时崩溃（因为现有验证脚本多直接读取 WBC 或 Bridge 遥测），但在进入 Phase 7B 激活上肢接触或依赖 `MotionState.contacts` 做动力学解算时将产生致命的数据失真。
* **Expected Contract**: Action 必须保护底层权威传感器与几何测量产物，严禁用意图覆写事实。
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Further Development**: `YES`
* **Suggested Minimal Repair**: 移除 `terrain_walk.py:1138` 中对 `contacts=c_dict` 的覆盖，仅保留 `ms = ms.clone_with(mode=mode, params=ms_params)`。

---

#### Finding ID: FIND-T01-03 (对应 R2: FIND-R2-04)
* **File**: `src/motion/framework.py` & `src/motion/terrain_walk.py`
* **Class**: `ActionExecutionResult` & `MotionPlanner`
* **Method**: `execute()`
* **Line Range**: `framework.py` Lines 405–416 (`ActionExecutionResult`), Lines 915–1010 (`MotionPlanner.execute()`)
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 执行链中发生局部物理失败或几何约束违规时。
* **Actual Behavior**: 
  `ActionExecutionResult` 缺失显式 `success: bool` 标识与 `unmet_constraints` 字段。`MotionPlanner.execute()` 在 L967–981 采用无条件迭代：`current_state = result.final_state`，无法捕获前序动作执行失败，前序错误被静默吞没并级联传给下一动作。
* **Expected Contract**: 动作执行结果必须携带明确的执行成功状态；规划器必须提供基于状态的阻断或回退分支。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `YES`
* **Suggested Minimal Repair**: 在 `ActionExecutionResult` 中增加 `success: bool = True` 字段；在 `MotionPlanner.execute()` 中建立基于 `success` 的阻断/告警合同。

---

#### Finding ID: FIND-T01-04 (对应 R2: FIND-R2-07)
* **File**: `src/motion/terrain_walk.py`
* **Class / Function**: `plan_terrain_footsteps()`
* **Line Range**: Lines 310–312 (调用点)；Lines 178–220 (函数定义)
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 地形在横向（$X$ 轴方向）存在接缝、局部台阶边缘或不对称斜坡时。
* **Actual Behavior**: 
  在 `plan_terrain_footsteps()` 的第 310 行，调用 `_adjust_footfall_for_seams_and_edges(environment, corridor_x, curr_lead_y, y0, y_tgt)` 时，固定传入走廊中心线坐标 `corridor_x`（通常为 0.0m），而不是摆动脚真实的侧向落点位置 `sw_x`（$\pm 0.13$m）。
* **Expected Contract**: 接缝探测应以左右摆动脚真实的预估世界坐标 $(sw_x, y)$ 为中心进行探测与避障。
* **Evidence**:
  ```python
  # src/motion/terrain_walk.py:308-313
  while curr_lead_y + stride < y_tgt - (route.min_step_length_m * 0.5):
      curr_lead_y += stride
      adjusted_y = _adjust_footfall_for_seams_and_edges(
          environment, corridor_x, curr_lead_y, y0, y_tgt
      )
      step_ys.append(adjusted_y)
  ```
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Further Development**: `NO`
* **Suggested Minimal Repair**: 在步态规划循环中结合左右脚侧向位移，传入实际摆动脚预估坐标 `sw_x`。

---

#### Finding ID: FIND-T01-05 (对应 R2: FIND-R2-06)
* **File**: `src/motion/terrain_walk.py`
* **Class / Function**: `build_terrain_step_schedule()` vs `plan_terrain_footsteps()`
* **Line Range**: Lines 223–401 (`plan_terrain_footsteps`), Lines 404–520 (`build_terrain_step_schedule`)
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 在大范围 Mesh 环境中调用 Legacy 调度函数 `build_terrain_step_schedule` 且射线未击中时。
* **Actual Behavior**: 
  `build_terrain_step_schedule` 在查询失败时无声回退到 `environment.ground_height_at(x, y)` 并设置 `surface_id="ground"`，而新版 `plan_terrain_footsteps` 严格抛出 `ValueError`。系统内部存在未命中处理的双轨制。
* **Expected Contract**: 全局统一未命中与非支撑表面的处理合同。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `NO`
* **Suggested Minimal Repair**: 废除或包装遗留调度生成函数，统一采用严格抛出或标准错误码。

---

#### Finding ID: FIND-T01-06
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `estimate_duration_frames()`
* **Line Range**: Lines 654–681
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 当 `TerrainWalkAction` 实例化时未显式传入 `environment`，而在 `execute()` 时才通过 `context.environment` 获取真实网格环境。
* **Actual Behavior**: 
  `estimate_duration_frames` 检查 `self.environment` 为空，静默回退至解析平地假定计算步数与耗时。
* **Expected Contract**: 预估函数应接受 `context` 或统一从环境源读取，保证规划耗时与实际执行耗时一致。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `NO`
* **Suggested Minimal Repair**: 为 `estimate_duration_frames` 补充可选的 `environment` 或 `context` 参数。

---

#### Finding ID: FIND-T01-07
* **File**: `src/motion/terrain_walk.py`
* **Class / Function**: `plan_terrain_footsteps()`
* **Line Range**: Lines 304–318
* **Evidence Grade**: `STATIC_CONFIRMED`
* **Trigger**: 当 `route.target_pos` 的 $Y$ 坐标小于 `route.start_pos` 的 $Y$ 坐标（即需要倒退行走或向 $-Y$ 方向行走）时。
* **Actual Behavior**: 
  循环终止条件 `while curr_lead_y + stride < y_tgt - (route.min_step_length_m * 0.5):` 立即判定为 False，直接跳过所有步态规划，返回仅含两个终点步的异常调度表。
* **Expected Contract**: 步态规划循环条件应基于标量有向距离或步数计数器判断，支持任意方向路线规划。
* **Classification**: `CONTRACT_GAP`
* **Blocks Further Development**: `NO`
* **Suggested Minimal Repair**: 将循环条件修改为基于有向步数或向量投影计算。

---

### 8.4 已知设计限制 (Known Design Limitations)

* **LIMIT-01: 单一前进走廊 $+Y$ 导航假定**: 当前 `TerrainWalkAction` 及其动力学计算均硬编码沿世界坐标 $+Y$ 轴前进，未解耦世界坐标系与角色局部导航坐标系（Heading）。
* **LIMIT-02: 上肢开环正向运动学（FK）摆臂**: 在行进过程中，手臂摆动由纯正弦经验公式生成并以欧拉角写入 WBC FK，手臂 IK 解算器处于休眠挂起状态。
* **LIMIT-03: IK 超限单向开环警报**: WBC 检测到 IK 目标超出肢体极限长度时，将拉伸截断至极限位置并记录 `UnmetConstraint`，但执行链缺乏“由于腿长不够而自动降低骨盆高度”的自适应全身闭环调整。

---

### 8.5 未验证项 (Unverified Items)

* **UNVERIFIED-01: 全身多接触动力学求解稳定性**: 当未来激活手部支撑时（手脚 4 点接触），`WholeBodyController` 中手臂 IK 与腿部 IK 同时锁定时质心与骨盆的姿态平衡尚未在真实三维物理场景中完整验证。
* **UNVERIFIED-02: 极端负高程（大落差跳跃/坠落）下的插值连续性**: 当前 S1/S2 摆动脚修复主要针对台阶与连续坡道，尚未在大落差（$> 0.8$m）瞬时断崖下进行数值平滑与冲击吸收验证。

---

### 8.6 建议修复顺序 (Suggested Remediation Roadmap)

1. **第一优先级（阻塞 Phase 7B）**：
   - FIND-T01-01 / FIND-R2-03（接入 `bridge_res.success` 与失败汇总）
   - FIND-T01-02 / FIND-R2-02（移除恶意覆盖 `contacts` 字典代码，保护真实物理接触）
   - FIND-T01-03 / FIND-R2-04（在 `ActionExecutionResult` 中建立失败合同）
2. **第二优先级（健壮性与精度优化）**：
   - FIND-T01-04 / FIND-R2-07（修正接缝探测的横向足部坐标）
   - FIND-T01-05 / FIND-R2-06（统一步态预规划的未命中回退语义）
   - FIND-T01-06（统一 `estimate_duration_frames` 的环境源）
   - FIND-T01-07（支持倒退与全向路线步态规划）

---

### 9. 零修改验证 (Verification of Non-Modification)

```text
C:\Users\64701\OneDrive\Desktop\ProceduralAnimation> git diff -- src/ tests/ output/
# (输出严格为空，0 行生产或测试代码被修改)
```

---

### 10. 强制停止与最终状态

严格限定在只读复核与证据核对范围，未修改生产代码，未进入 Phase 7B。

**最终证据复核状态标定**：  
$$\mathbf{PRODUCTION\ INTERFACE\ AUDIT\ /\ R2\ —\ EVIDENCE\ VERIFIED}$$
