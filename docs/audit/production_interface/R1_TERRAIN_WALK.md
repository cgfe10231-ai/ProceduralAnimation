# ProceduralAnimation — Production Interface Audit: Task 01
## 审查对象：`src/motion/terrain_walk.py`

* **任务性质**：单脚本、逐方法、只读生产接口审查（只证实漏洞，不修复、不重构、不进入 Phase 7B）。
* **Git 基准**：
  * Commit SHA：`3fc9896f6867d49a01f6d5c39b9819d51200c7a0` (`master`)
  * 工作区状态：除受保护的 `P2_R1_recovery.patch` 外，工作树严格干净。
* **文件修改约束**：本审计未修改、未新增任何文件，未产生任何 Git 提交。

---

### 8.1 文件概况

* **文件路径**：[`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py)
* **行数规模**：1236 行
* **在系统中的定位**：连续 19 骨骼地形自适应行走动作规划与执行模块，负责从离散落脚点规划（`plan_terrain_footsteps`）到连续每帧位姿生成（`TerrainWalkAction.execute`），是当前生产管线中生成 3D 地形行走的核心驱动者。
* **类与函数清单（AST 语法树解析）**：
  1. `_smoothstep01(t: float) -> float` (Line 55)
  2. `_smooth_bell01(t: float) -> float` (Line 61)
  3. `_compute_swing_clearance_z(...) -> float` (Line 67)
  4. `pitch_from_surface_normal(normal: Tuple[float, float, float]) -> float` (Line 85)
  5. `TerrainStepPlan` (Line 109, `@dataclass`)
  6. `TerrainRouteInput` (Line 132, `@dataclass`)
  7. `TerrainTraversalSpec` (Line 158, `@dataclass`)
  8. `_adjust_footfall_for_seams_and_edges(env, x, y, corridor_y_min, corridor_y_max) -> float` (Line 178)
  9. `plan_terrain_footsteps(route, environment, start_frame) -> Tuple[List[TerrainStepPlan], int]` (Line 223)
  10. `build_terrain_step_schedule(spec, environment, start_frame) -> Tuple[List[TerrainStepPlan], int]` (Line 404)
  11. `_build_continuous_root_forward_spline(schedule, fps) -> Tuple[List[int], List[float], List[float]]` (Line 526)
  12. `_evaluate_root_y_hermite(current_frame, step_k, knot_frames, knot_y, knot_v, fps) -> float` (Line 568)
  13. `TerrainWalkAction(MotionAction)` (Line 611):
      * `__init__(self, spec, route, action_name, environment)` (Line 614)
      * `name(self) -> str` (Line 651)
      * `estimate_duration_frames(self, initial_state, config) -> int` (Line 654)
      * `execute(self, initial_state, context) -> ActionExecutionResult` (Line 683)

---

### 8.2 逐方法检查表

| 类 / 方法名 | 源码行号 | 输入合同 | 输出合同 | 失败处理机制 | 状态所有权与流向 | 检查结论 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `_smoothstep01` | L55–L59 | 标量 `t: float` | 归一化插值因子 $[0.0, 1.0]$ | 内部执行 `clamp(0.0, 1.0)`，无异常抛出 | 纯数学无副作用局部函数 | `NO_ISSUE` |
| `_smooth_bell01` | L61–L65 | 标量 `t: float` | 正弦钟形曲线高度 $[0.0, 1.0]$ | 内部执行 `clamp(0.0, 1.0)`，无异常抛出 | 纯数学无副作用局部函数 | `NO_ISSUE` |
| `_compute_swing_clearance_z` | L67–L83 | `step_alpha`, `z_base`, `arc_z`, `z_terr_foot`, `min_clearance_amp` | 摆动脚目标高度 `sw_z_clean: float` | 数值混合，无异常抛出 | 纯数学几何混合计算 | `NO_ISSUE` |
| `pitch_from_surface_normal` | L85–L106 | 3D 表面法线向量元组 | 俯仰欧拉角（度）`pitch_deg: float` | $n_z=0$ 时 `atan2` 自动返回 $\pm 90^\circ$，防死锁 | 纯数学转换，无副作用 | `NO_ISSUE` |
| `TerrainStepPlan` | L109–L130 | 步态参数与时空关键点 | 结构化单步参数容器 | `@dataclass` 默认构造 | 纯数据载体 | `NO_ISSUE` |
| `TerrainRouteInput` | L132–L156 | 起点、终点、步长、净空等参数 | 路线配置载体 | 提供全套生理默认值，无跨字段边界校验 | 纯数据载体，但未声明对非 $+Y$ 路线的不支持 | `CONTRACT_GAP` |
| `TerrainTraversalSpec` | L158–L176 | 历史 Course B 航点与几何参数 | 航点配置载体 | Legacy 数据容器 | 纯数据载体 | `NO_ISSUE` |
| `_adjust_footfall_for_seams_and_edges` | L178–L220 | `environment`, `x`, `y`, `corridor_y_min`, `corridor_y_max` | 微调后的前向坐标 `best_y: float` | 射线未击中时回退为默认法线，返回原 `y` | 仅读取环境法线，无状态写入 | `CONFIRMED_DEFECT` (调用时硬编码走廊中心 $X$，脱离实际落脚侧翼) |
| `plan_terrain_footsteps` | L223–L401 | `TerrainRouteInput`, `EnvironmentQuery`, `start_frame` | `(schedule, total_frames)` | 初始站立或落点未命中/不可支撑时显式抛出 `ValueError` 阻断 | 生成前向步态调度，不修改 Armature | `DESIGN_LIMITATION` (写死 $X=x_0$ 走廊并忽略 $x_{\text{tgt}}$) / `CONTRACT_GAP` (负向行进跳步缺陷) |
| `build_terrain_step_schedule` | L404–L520 | `TerrainTraversalSpec`, `EnvironmentQuery`, `start_frame` | `(schedule, total_frames)` | 查询失败时静默调用旧解析方法回退至平地（与严格拒绝合同冲突） | Legacy 调度生成 | `CONTRACT_GAP` (静默回退导致双轨制行为分歧) |
| `_build_continuous_root_forward_spline` | L526–L565 | `schedule`, `fps` | 样条节点 `knot_frames`, `knot_y`, `knot_v` | 计算一阶单调导数，无异常抛出 | 纯数学Hermite样条构建 | `NO_ISSUE` |
| `_evaluate_root_y_hermite` | L568–L608 | `current_frame`, `step_k`, 样条节点元组, `fps` | 根节点当前前向位移 `root_y: float` | 超界截断至末端节点，无异常抛出 | 纯数学插值计算 | `NO_ISSUE` |
| `TerrainWalkAction.__init__` | L614–L649 | `spec`, `route`, `action_name`, `environment` | `TerrainWalkAction` 实例 | `route` 与 `spec` 均为空时抛出 `ValueError` | 初始化只读配置参数 | `NO_ISSUE` |
| `TerrainWalkAction.name` | L651–L652 | 无 | 动作标识字符串 | 无 | 属性读取器 | `NO_ISSUE` |
| `TerrainWalkAction.estimate_duration_frames` | L654–L681 | `initial_state: MotionState`, `config: PipelineConfig` | 预估帧数 `total_frames: int` | `self.environment` 为空时静默回退为解析平地 $Z=0$ | 离散预估，无执行状态产生 | `CONTRACT_GAP` (与 `execute` 获取的真实网格环境源脱节) |
| `TerrainWalkAction.execute` | L683–L1236 | `initial_state: MotionState`, `context: MotionRuntimeContext` | `ActionExecutionResult` | 仅检查初始脚位有效性；**完全忽略 `bridge_res.success`**，IK 不可达仅记 Warning | **越权覆盖** `MotionState.contacts`，抹杀 Bridge 权威物理接触数据；上肢正弦摆臂硬编码强耦合 | `CONFIRMED_DEFECT` (失败传播丢失、状态覆盖、摆臂耦合) |

---

### 8.3 确认的问题 (Confirmed Findings)

#### Finding ID: FIND-T01-01
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `execute()`
* **Line Range**: Lines 1080–1091
* **Trigger**: 任何导致 `KinematicBridgeExecutor.execute_frame()` 返回 `success=False` 的物理或运动学异常（包括：足底接触几何违规 `NO_SUPPORT_SURFACE`、穿透超差 $>15\,\text{mm}$、气隙超差、ROM 冲突无法满足、两骨 IK 求解失效）。
* **Actual Behavior**: 
  1. `TerrainWalkAction.execute()` 完全不读取、不检查 `bridge_res.success`；
  2. 仅在 `not bridge_res.wbc_result.is_all_reachable` 时向终端输出一条 `[WARN] IK Unreachable...` 并递增 `unreachable_count += 1`；
  3. 当且仅当失败属于接触几何或 ROM 冲突时，系统甚至连警告都不打印，`unreachable_count` 依然为 0；
  4. 每一帧无条件继续流转，生成下一帧；最终动作正常返回包含全部帧的 `ActionExecutionResult`，向调用方 `MotionPlanner` 隐瞒全部底层执行失败。
* **Expected Contract**: 遵循门禁与错误传播规范，当底座 `bridge_res.success == False` 时，Action 层必须能够捕获该失败；要么阻断当前动作并触发回退/报警，要么在返回的 `ActionExecutionResult` 中显式标定执行失败并携带错误详情。严禁在骨骼未成功就位或受力违规时伪造动作成功。
* **Evidence**:
  ```python
  # terrain_walk.py:1080-1090
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
  # -> 完全缺失 if not bridge_res.success: 判定分支！
  ```
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Next Stage**: `YES` (阻碍 Phase 7B 建立健壮的动作级错误仲裁机制；在上肢出现接触失败或解算崩溃时会静默假死)
* **Suggested Minimal Repair**: 在第 1083 行后增加对 `bridge_res.success`、`bridge_res.contact_geometry_errors` 与 `bridge_res.rom_violations` 的统一汇总；记录 `failed_frames` 并在 `ActionExecutionResult.metrics` 中输出真实执行状态。

---

#### Finding ID: FIND-T01-02
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `execute()`
* **Line Range**: Lines 1100–1139
* **Trigger**: 每一帧执行至第 1125–1139 行时无条件触发。
* **Actual Behavior**:
  1. `ms.clone_with(contacts=c_dict, mode=mode)` 使用动作层局部构造的 `c_dict` 直接覆盖了 `bridge_res.motion_state.contacts`；
  2. 彻底抹除了 `KinematicBridgeExecutor`（通过 `contact_model.py`）评估的权威接触数据：所有手部接触（`hand_L`, `hand_R`）被直接丢弃；
  3. `is_locked` 被强行写为规划意图 `foot_l_tgt.is_locked`。即使网格查询判定为不可支撑立面导致 Bridge 将接触生命周期标定为 `ContactLifecycle.BROKEN` 且 `is_active=False`，`c_dict` 依然将其强行洗白为 `is_locked=True`；
  4. `contact_world_xyz` 被重置为规划层预设的 `last_known_xyz`，覆盖了 Bridge 返回的真实地形表面物理接触点 (Point B)。
* **Expected Contract**: 遵循单向状态所有权原则（SSOT），已评估姿态的接触状态所有权归属于 `ContactModel` 与 `KinematicBridge`（Phase 5/Phase 6）。动作规划层作为 Phase 1 的期望生成者，严禁在 Phase 6 姿态求解完毕后，用前向期望数据反向覆盖权威物理评估结果。
* **Evidence**:
  ```python
  # terrain_walk.py:1137-1138
  else:
      ms = ms.clone_with(contacts=c_dict, mode=mode)
  # 强制将 kinematic_bridge.py:668 中 enrich_motion_state_with_contacts() 写入的
  # legacy_contacts (包含手部与真实生命周期) 完全抹杀，退化为仅含 foot_L/foot_R 的局部字典
  ```
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Next Stage**: `YES` (Phase 7B 核心目标是引入独立上肢运动学与抓握/触碰意图；若 `TerrainWalkAction` 持续无脑抹除 hand contacts 并篡改锁定状态，7B 上肢接触数据将完全无法在 `MotionState` 中持久化)
* **Suggested Minimal Repair**: 移除 `TerrainWalkAction` 中用 `c_dict` 覆盖 `ms.contacts` 的逻辑；若需保留 `drift_m` 等动作层诊断数据，应以扩展形式写入 `ms.params` 或 `frame_records`，严格保护 `bridge_res.motion_state.contacts` 的权威所有权。

---

#### Finding ID: FIND-T01-03
* **File**: `src/motion/framework.py` & `src/motion/terrain_walk.py`
* **Class**: `ActionExecutionResult` & `TerrainWalkAction`
* **Method**: `execute()`
* **Line Range**: `framework.py:821–836`, `terrain_walk.py:1209–1236`
* **Trigger**: 动作执行中发生任何局部异常或失败时。
* **Actual Behavior**: 
  1. `ActionExecutionResult` 数据结构根本没有定义 `success: bool` 或 `error_message` 字段；
  2. `TerrainWalkAction.execute()` 返回时，将所有生成的 `states` 组装返回，无法表达“本动作已失败”；
  3. `MotionPlanner.execute()` 盲目接收 `result.states` 与 `result.final_state`，无条件将末帧状态作为下一个动作的起始输入，导致失败状态被悄悄继承并污染后续时间轴。
* **Expected Contract**: 动作执行合同必须包含布尔型执行成功状态与错误诊断容器，以便上层 `MotionPlanner` 执行可靠的中断、重试或上报。
* **Evidence**:
  ```python
  # framework.py:821
  @dataclass
  class ActionExecutionResult:
      action_name: str
      initial_state: MotionState
      final_state: MotionState
      states: List[MotionState]
      frame_records: List[dict]
      step_schedule: List[dict] = field(default_factory=list)
      unreachable_count: int = 0
      metrics: Dict[str, Any] = field(default_factory=dict)
      # 缺失: success, failure_reason, failed_frames
  ```
* **Classification**: `CONTRACT_GAP`
* **Blocks Next Stage**: `YES` (多动作编排与状态传递缺乏安全断言，后续动作无法得知前序动作是否有效就位)
* **Suggested Minimal Repair**: 在 `ActionExecutionResult` 中补充 `success: bool = True` 与 `errors: List[str] = field(default_factory=list)` 字段；并在 `TerrainWalkAction` 与 `MotionPlanner` 中补充对应的合同判断。

---

#### Finding ID: FIND-T01-04
* **File**: `src/motion/terrain_walk.py`
* **Class**: N/A
* **Method**: `plan_terrain_footsteps()`
* **Line Range**: Lines 310–312, 322
* **Trigger**: 地形在横向（$X$ 轴方向）存在接缝、局部台阶边缘或不对称斜坡时。
* **Actual Behavior**: 
  1. 在第 310 行计算候选落脚点 $Y$ 坐标时，调用 `_adjust_footfall_for_seams_and_edges(environment, corridor_x, curr_lead_y, y0, y_tgt)`；
  2. 传入的横向坐标硬编码为 `corridor_x`（即中心线 $X=0.0\,\text{m}$）；
  3. 但在下文第 322 行，实际落脚点位于横向偏移处：`sw_x = right_x` 或 `left_x`（即 $X = \pm 0.13\,\text{m}$）；
  4. 导致接缝检测只探测了身体正下方的中央地面，若侧翼落脚点恰好踩在台阶边缘或裂缝上，算法完全无法感知和避让。
* **Expected Contract**: 接缝避让微调应当以该步实际着地的左右脚横向坐标（`left_x` 或 `right_x`）为准进行足底刚体范围探测。
* **Evidence**:
  ```python
  # terrain_walk.py:310-322
  adjusted_y = _adjust_footfall_for_seams_and_edges(
      environment, corridor_x, curr_lead_y, y0, y_tgt  # <- 此处使用的是中心线 corridor_x
  )
  ...
  sw_x = right_x if swing_side == "R" else left_x     # <- 实际落脚使用的是两侧 sw_x
  ```
* **Classification**: `CONFIRMED_DEFECT`
* **Blocks Next Stage**: `NO` (属于横向非均匀地形的步态稳健性缺陷，当前测试地形在横向均为均匀延展，不阻碍 Phase 7B 运动学开发)
* **Suggested Minimal Repair**: 将微调函数调用移至交替步态循环内部，传入真实的摆动脚横向位置 `sw_x` 进行检测。

---

#### Finding ID: FIND-T01-05
* **File**: `src/motion/terrain_walk.py`
* **Class**: N/A
* **Method**: `build_terrain_step_schedule()`
* **Line Range**: Lines 421–428, 461–464
* **Trigger**: 在纯网格环境（未定义解析曲面）中调用 legacy 调度器 `build_terrain_step_schedule` 且射线投射未击中网格时。
* **Actual Behavior**: 
  与 `plan_terrain_footsteps`（未命中直接抛出 `ValueError` 阻断）不同，`build_terrain_step_schedule` 在 `sw_landing_res.success` 为 `False` 时，静默调用 `environment.ground_height_at`、`environment.surface_normal_at`，最终静默回退至平地 $Z=0$ 与 `surface_id="ground"`，产生了已被 Unit 1/Unit 3 淘汰的双轨制静默回退缺陷。
* **Expected Contract**: 遵循环境门禁单一真实网格查询合同，未命中网格时必须执行严格拒绝，严禁静默回退伪造平地。
* **Evidence**:
  ```python
  # terrain_walk.py:460-464
  else:
      sw_landing_z = environment.ground_height_at(sw_x, target_y)
      sw_landing_norm = environment.surface_normal_at(sw_x, target_y)
      surf_res = environment.query_surface_at_point((sw_x, target_y, sw_landing_z))
      surf_id = surf_res.surface_id if hasattr(surf_res, "surface_id") else "ground"
  ```
* **Classification**: `CONTRACT_GAP`
* **Blocks Next Stage**: `NO` (生产主链已全面切换至 `plan_terrain_footsteps`，本函数仅作为 legacy 兼容保留)
* **Suggested Minimal Repair**: 对齐 `build_terrain_step_schedule` 与 `plan_terrain_footsteps` 的错误处理行为，网格模式下未命中显式抛出异常或返回失败。

---

#### Finding ID: FIND-T01-06
* **File**: `src/motion/terrain_walk.py`
* **Class**: `TerrainWalkAction`
* **Method**: `estimate_duration_frames()`
* **Line Range**: Lines 656, 689
* **Trigger**: 当 `TerrainWalkAction` 构造时未显式传入 `environment`，而在 `execute` 时由 `context.environment` 提供真实网格环境。
* **Actual Behavior**: 
  `estimate_duration_frames` 在缺少实例环境时直接降级为 `EnvironmentQuery(ground_z=0.0)`（解析平地）；而在 `execute` 时从 `context.environment` 读取真实网格环境。若真实复杂地形（包含陡坡、台阶）导致步幅被接缝算法微调或出现步数差异，预估帧数与实际执行帧数将产生偏差，破坏 `MotionPlanner` 的时间轴预规划。
* **Expected Contract**: 预估接口应能够获取与执行阶段一致的环境感知源，或者在无法获取网格时明确抛出警告/声明为平地粗略近似。
* **Evidence**:
  ```python
  # terrain_walk.py:656 vs 689
  env = self.environment or EnvironmentQuery(ground_z=0.0)  # estimate_duration_frames: 降级平地
  ...
  environment = context.environment                         # execute: 强制使用上下文真实环境
  ```
* **Classification**: `CONTRACT_GAP`
* **Blocks Next Stage**: `NO`
* **Suggested Minimal Repair**: 为 `estimate_duration_frames` 增加上下文接收能力，或在未绑定环境时输出明确的近似标记。

---

#### Finding ID: FIND-T01-07
* **File**: `src/motion/terrain_walk.py`
* **Class**: N/A
* **Method**: `plan_terrain_footsteps()`
* **Line Range**: Lines 308–318
* **Trigger**: 输入参数 `route.target_pos` 的 $Y$ 坐标小于 `route.start_pos` 的 $Y$ 坐标（向后行进或沿 $-Y$ 方向）。
* **Actual Behavior**: 
  `while curr_lead_y + stride < y_tgt - ...` 判定条件直接为 `False`（因为 `stride > 0` 且 `curr_lead_y > y_tgt`），循环被完全跳过；紧随其后的代码直接执行 `step_ys.append(y_tgt)` 两次，导致角色在两步内从起点瞬间跳跃跨越任意负向距离（如从 $Y=0$ 瞬间跳至 $Y=-10\,\text{m}$），完全丢失生理步幅约束。
* **Expected Contract**: 若本规划器仅支持正向行走，输入校验阶段必须抛出 `ValueError("TerrainRouteInput only supports forward traversal: target_pos.y > start_pos.y")`；若支持双向，应根据位移符号反转步进逻辑。
* **Evidence**:
  ```python
  # terrain_walk.py:307-317
  curr_lead_y = y0
  while curr_lead_y + stride < y_tgt - (route.min_step_length_m * 0.5):
      curr_lead_y += stride
      ...
  step_ys.append(y_tgt)
  step_ys.append(y_tgt)
  ```
* **Classification**: `CONTRACT_GAP`
* **Blocks Next Stage**: `NO` (当前工程场景全部为 $+Y$ 前进走廊)
* **Suggested Minimal Repair**: 在 `plan_terrain_footsteps` 入口处增加显式的正向前进校验断言。

---

### 8.4 已知设计限制 (Known Design Limitations)

以下内容属于经过项目架构门禁（`docs/ARCHITECTURE_CHANGE_GATE.md` 与 `DECISIONS.md`）书面批准的阶段性设计限制，**严禁与生产 Bug 混淆**：

1. **`LIMIT-01`: 单一直线走廊导航限制 (Single-Corridor $Y$-Axis Assumption)**
   * **位置**：`src/motion/terrain_walk.py` Line 240–245
   * **内容**：`plan_terrain_footsteps` 写死 `corridor_x = x0`，完全忽略 `target_pos[0]`，落脚点只能沿平行于 $+Y$ 轴的直线走廊推进，不支持曲面样条或航向角转弯。
   * **规划**：已登记于 `HARDCODE_REGISTER.md` (HC-02, HC-03)，留待 Phase 7D（通用路线导航）统一重构为参数化航点。
2. **`LIMIT-02`: 上肢正弦波摆臂硬编码强耦合 (Contralateral FK Arm Swing Coupling)**
   * **位置**：`src/motion/terrain_walk.py` Line 1048–1060
   * **内容**：左右手臂欧拉角直接根据下肢步态相位公式 `arm_l_rx = -arm_swing_amp * sin(2*pi*gait_u)` 计算，未接入 WBC 的独立上肢 IK 槽位。
   * **规划**：已登记于 `FINAL_FINDINGS.md` (FIND-01)，已批准作为 **Phase 7B 首要解耦攻坚子任务**。
3. **`LIMIT-03`: IK 超程开环告警 (Open-Loop IK Reachability Logging)**
   * **位置**：`src/motion/terrain_walk.py` Line 1084–1091
   * **内容**：两骨 IK 目标超程时，仅记录日志并截断至 $0.999 \times \text{max\_reach}$，未触发步态自适应重规划。
   * **规划**：已登记于 `FINAL_FINDINGS.md` (FIND-05)，留待 Phase 7A-3 步态自适应优化。

---

### 8.5 未验证项 (Unverified Items)

1. **`UNVERIFIED-01`: 极限悬崖/垂直掉落工况下执行循环的级联反应**
   * **缺失证据**：当前测试均在有效支撑网格上运行。尽管前置 `plan_terrain_footsteps` 遇到不可支撑面时会直接抛出 `ValueError` 阻断，但如果外部绕开规划器直接向 `execute()` 注入落空悬空的步态，`TerrainWalkAction.execute()` 循环内缺乏深层掉落处理，该极端路径尚未在无头 Blender 真实场景中执行观察。
2. **`UNVERIFIED-02`: 手部激活抓握意图时 `c_dict` 抹杀对上身姿态计算的副作用**
   * **缺失证据**：当前生产场景中手部均为自由摆动（`ContactType.FREE`）。虽然代码分析证实 `c_dict` 100% 抹除了手部 contacts，但由于目前没有动作激活手部接触意图，该覆盖行为在现有视觉产物和既有测试中未产生破坏性表现，留待 Phase 7B 激活手部 IK 后方可进行故障注入实证。

---

### 8.6 建议修复顺序 (Suggested Remediation Roadmap)

严禁在当前只读审计阶段编写修复代码。建议在后续获得明确授权的独立修复单元中，按以下优先级逐步收口：

* **第一优先级（解除 Phase 7B 架构阻塞）**：
  1. **收口 FIND-T01-02**：彻底消除 `TerrainWalkAction.execute()` 中用局部 `c_dict` 越权覆盖 `ms.contacts` 的行为，恢复 `KinematicBridge` 与 `ContactModel` 对接触状态（含手部接触）的权威所有权；
  2. **收口 FIND-T01-01**：在 `TerrainWalkAction.execute()` 中接入对 `bridge_res.success` 与各级错误（接触几何超差、ROM 冲突）的显式捕获与处理；
  3. **收口 FIND-T01-03**：在 `ActionExecutionResult` 中补充 `success` 与错误信息字段，打通动作层到规划层的失败传播链路。
* **第二优先级（算法健壮性与合同对齐）**：
  4. **修复 FIND-T01-04**：修正 `_adjust_footfall_for_seams_and_edges`，改为按真实摆动脚侧翼横向坐标 `sw_x` 进行接缝微调；
  5. **修复 FIND-T01-07**：在 `plan_terrain_footsteps` 增加对 `y_tgt <= y0` 反向位移的显式输入合法性校验。
* **第三优先级（Legacy 代码规范与边界微调）**：
  6. **对齐 FIND-T01-05**：对齐 `build_terrain_step_schedule` 与 `plan_terrain_footsteps` 的网格查询错误处理行为；
  7. **微调 FIND-T01-06**：为 `estimate_duration_frames` 提供一致的环境感知源。

---

### 9. 结束检查证明 (Verification of Non-Modification)

严格执行只读纪律，核实本审计任务未对仓库造成任何变动：

```powershell
PS C:\Users\64701\OneDrive\Desktop\ProceduralAnimation> git status --short
?? P2_R1_recovery.patch

PS C:\Users\64701\OneDrive\Desktop\ProceduralAnimation> git diff --stat
# (输出为空，严格 0 行变更，未创建新文件，未提交任何 Commit)
```

---

### 10. 强制停止与最终状态

本审查严格限定于 `src/motion/terrain_walk.py` 单一脚本，未向外扩展，未编写任何修复代码，未进入 Phase 7B。

**最终报告状态标定**：  
$$\mathbf{PRODUCTION\ INTERFACE\ AUDIT\ /\ TASK\ 01\ —\ AWAITING\ EXTERNAL\ REVIEW}$$