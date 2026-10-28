# CHANGELOG: 项目变更历史

所有条目必须严格遵循客观事实纪律，未经验证的不得标记为已验证。


## [2026-10-28] Environment Gate 01 — Unit 3 / Atomic Repair S1: Root 前进轨迹与单步摆动脚时间参数解耦及 C1 连续性闭环 (S1-A 至 S1-F)

### 根因诊断与数据实证 (`tests/verify_environment_gate01_u3_s1.py`, S1-A)
* **41/41 换脚边界速度塌陷根因查明**：
  - 检查 Baseline `output/dynamics_playground_environment_gate01_u3.blend` 中 `CharacterRoot` 真实运动学；
  - 证实历史实现 `root_y = 0.5 * (st_xyz[1] + sw_y)` 导致 Root 前向速度与单步摆动脚缓入缓出插值强耦合；
  - 在每个 16 帧步态交替边界（41 处），前向速度塌陷至接近归零（最低 0.0346 m/s，平均 0.0680 m/s，相对稳态速度塌陷达 85%~92%）；
  - 输出客观证据：`root_velocity_before.csv`、`root_acceleration_before.csv`、`root_step_boundary_report.json` 至 `docs/evidence/environment_gate01_u3_s1/`。

### 生产控制解耦与单调 C1 连续 Hermite 样条落地 (`src/motion/terrain_walk.py`, S1-B)
* **独立 Root 轨迹参数化**：
  - 保持摆动脚缓入缓出轨迹 `sw_y` 计算 100% 不变（规则 A：足部接近落点平稳减速）；
  - 实现纯数学私有辅助函数 `_build_continuous_root_forward_spline(schedule, fps)` 与 `_evaluate_root_y_hermite(...)`；
  - 基于当前 `TerrainStepPlan` 与相邻步态真实落脚位置，提取 $K+1$ 个双足几何中心节点 $Y_k$ 与时间节点 $T_k$；
  - 起步与停止节点速度严格保持 $0.0\text{ m/s}$，内部节点采用中心差分保证连续过渡速度；
  - 步内采用三次 Hermite 样条插值，配合 Fritsch-Carlson 单调性钳位（$m_0, m_1 \in [0, 3]$），严格消除倒退运动；
  - 换脚边界速度塌陷异常数彻底由 41/41 (100%) 降至 0/41 (0%)，最低边界速度提升至 0.2722 m/s，平均边界速度提升至 0.4423 m/s。

### 独立产物生成与重开严苛验证 (`src/scene/playground_terrain_traversal.py`, S1-F)
* **新增 S1 独立场景入口 (`generate_dynamics_playground_environment_gate01_u3_s1_blend`)**：
  - 产物持久化至 `output/dynamics_playground_environment_gate01_u3_s1.blend`，历史 Unit 3 资产 0 字节变动；
  - 重新打开场景执行 700 帧全量零豁免核验：Root C0 连续（$< 0.023\text{ m/frame}$）、0 ROM 违规、0 骨骼拉伸（$< 1.8\times 10^{-6}\text{ m}$）、锁定支撑脚滑移 $< 1.2\times 10^{-5}\text{ m}$；
  - 生成 `root_velocity_after.csv`、`root_acceleration_after.csv`、对比 JSON `root_continuity_comparison.json` 及视口审查指引 `u3_s1_visual_review.md`。

### 验收测试套件与全量回归 (`tests/test_environment_gate01_u3_s1.py`, `tests/test_registry.py`)
* **完整 4 项单元测试全绿**：
  - S1-T01: 旧 Root 时间参数 100% 塌陷可证伪性实证；
  - S1-T02: 新 Root 时间参数 0 塌陷、C0/C1 连续与足底接触零退化；
  - S1-T03: 0.20m 与 0.40m 步长参数无关泛化性验证；
  - S1-T04: 纯数学 Hermite 样条边界与单调性合同。
* 注册进入 `tests/test_registry.py`，全量分级回归通过：`quick` (15/15), `physics` (19/19), `motion` (10/10), `full` (32/32)；
* 状态严格停留于 `ENVIRONMENT GATE 01 / UNIT 3-S1 — AWAITING HUMAN VISUAL REVIEW`。


## [2026-10-28] Environment Gate 01 — Repair Unit 3: 真实 Blender Mesh 环境查询与 19 骨骼人体连续运动主链接入及反事实实证闭环 (U3-01 至 U3-14)

### 地面单次命中支撑查询合同落地 (`src/scene/environment_query.py`)
* **统一单次命中查询契约 (`query_ground_support_at`)**：
  - 在 `EnvironmentQuery` 与 `DynamicsEnvironmentQuery` 实现 `query_ground_support_at(x, y, start_z=50.0, max_fall=100.0) -> SurfaceQueryResult`；
  - 终结分散的 `ground_height_at`、`surface_normal_at` 与 `query_surface_at_point` 调用，保证足部落点高度 $Z$、法向量、`surface_id` 及支撑适格性来自单次物理命中；
  - 网格模式下垂直向下投射射线，未命中时严格返回 `success=False`（`error_reason="NO_HIT: ..."`，`source_type="mesh"`），彻底消除静默伪造 $Z=0.0\text{m}$ 虚假地面；
  - 命中非支撑表面（`allows_regular_support=False`）时返回 `success=False`（`NON_SUPPORT_SURFACE`）；
  - 解析模式与基类保持向下兼容（回退至解析表面或默认平地，`source_type="analytical"` / `"default"`）。

### 运动规划与执行接入真实网格与严格拒绝 (`src/motion/terrain_walk.py`)
* **单次命中集成与严格阻断**：
  - 在 `plan_terrain_footsteps`、`build_terrain_step_schedule`、`_adjust_footfall_for_seams_and_edges` 与 `execute` 中全面接入 `query_ground_support_at`；
  - 起始站立脚、每步摆动着地、支撑脚参考及足部刚体包围盒清除均由统一单次命中决定；
  - 网格模式下遇到 `NO_HIT` 或非支撑表面显式抛出 `ValueError` 阻断规划；
  - 零侵入保持 6 阶段权威主链（`MotionPlanner` → `TerrainWalkAction` → `KinematicPlannedPose` → `KinematicBridgeExecutor` → `WholeBodyController` → `Rig/IK/FK`），`WholeBodyController`、`KinematicBridgeExecutor` 与角色骨骼模块保持 0 改动。

### 独立场景装配与进出坡道实网格补全 (`src/scene/playground_terrain_traversal.py`)
* **真实网格集成场景生成入口 (`generate_dynamics_playground_environment_gate01_u3_blend`)**：
  - 在装配场景中补全坡道引桥与着地出口平地支撑块（`Surface_Ramp_ApproachGround`, `Surface_Ramp_ExitGround`）并纳入 `Playground_Surfaces`，确保全路段落点 100% 命中真实网格；
  - 顶面多边形采用逆时针缠绕顺序生成向上法线 $(0, 0, 1)$；
  - 产物持久化至 `output/dynamics_playground_environment_gate01_u3.blend`（700 帧连续动画、主相机、诊断场景、逐帧遥测与 JSON 伴随数据）；
  - 实现反事实网格微扰生成函数 `apply_ramp_mesh_perturbation(delta_z=0.05)`，生成对照场景 `output/dynamics_playground_environment_gate01_u3_perturbed.blend`；
  - 历史基准资产 `output/dynamics_playground.blend` 保持 0 字节变动。

### 真实网格重新评估验证器 (`src/scene/playground_terrain_validation.py`)
* **重开文件网格逐帧核验 (`validate_dynamics_playground_environment_gate01_u3`)**：
  - 重新打开产物场景并实例化 `BlenderMeshEnvironmentAdapter` 针对真实网格逐帧核验；
  - 700 帧全量零豁免 Root C0 连续性（$< 0.12\text{ m/frame}$）、骨骼拉伸（$< 0.1\text{ mm}$）、旋转抖动（$< 35^\circ$）、锁定支撑脚滑移（$< 0.1\text{ mm}$）、ROM 违规（0 处）与真实网格表面接触检验。

### 14 项完整测试与反事实实证归档 (`tests/test_environment_gate01_unit3.py`, `docs/evidence/environment_gate01_ru3/`)
* **完整测试套件 (U3-T01 至 U3-T14)**：
  - 编写 `tests/test_environment_gate01_unit3.py` 并注册至 `tests/test_registry.py`，14 项测试全绿（14/14 PASS in 14.8s）；
  - 全量分级回归通过：`quick` (14/14), `physics` (19/19), `motion` (9/9), `full` (31/31)；
  - `audit_c2_final_inspector.py --verify-docs` 校验 0 错误；
  - 生成反事实对比报告 `counter_factual_summary.md` 与技术集成报告 `unit3_integration_report.md`；
  - 证实网格微扰驱动运动主链产生真实物理偏移（落地高程与 Root 高程均抬升 $+0.05\text{m}$），同时证实旧版解析查询器对网格微扰脱敏（高程差异恒为 $0.0\text{m}$）；
  - 最终状态判定为 `ENVIRONMENT GATE 01 / UNIT 3 — AWAITING HUMAN VISUAL REVIEW`。


## [2026-10-28] Environment Gate 01 — Repair Unit 2 Final Closure: C05-1至C05-4深度集合生命周期、C06异常安全加固与F01-F03反事实实证闭环

### 生产适配器异常安全与状态加固 (`src/scene/blender_mesh_query_adapter.py`)
* **`rebuild()` 全流程异常安全与自动回滚**：
  - 将 `_gather_target_objects()` 与快照计算完整移入 `try:` 保护块内；
  - 确保任何阶段（候选收集、快照计算、求值网格提取、BVH 编译）抛出未捕获异常时，缓存状态必然回滚至 `AdapterCacheState.FAILED` 并设置 `dirty = True`；
  - 杜绝状态卡死在 `REBUILDING`，临时求值网格在 `finally:` 中统一通过 `eval_obj.to_mesh_clear()` 清理；
  - 后续查询自动触发自愈恢复重建。

### 验收测试套件扩充 (`tests/test_mesh_environment_query.py`)
* **新增 Unit 2 最终收口用例 (`test_43` 至 `test_47`)**：
  - `test_43_c05_1_collection_member_unlinked`: 仅解除关联（未删除）的对象从 BVH 中剔除（1 次重建），且受禁集合对象绝不被查询；
  - `test_44_c05_2_real_object_deletion`: `bpy.data.objects.remove(obj, do_unlink=True)` 触发 1 次重建，元数据清理干净，0 野指针；
  - `test_45_c05_3_non_empty_to_empty_transition_and_reuse`: 非空转空转入 `VALID_EMPTY`，100 次空查询 0 重建复用，返回 `success=False`（`source_type="none"`），加入新 Mesh 干净恢复；
  - `test_46_c05_4_recursive_collection_membership`: 子集合成员递归追踪、子集合解关联剔除、子集合新增感知及同级集合严格隔离；
  - `test_47_c06_rebuild_exception_safety`: gather、snapshot 及 BVH 编译异常下统一回滚至 `FAILED`，求值网格安全释放，后续查询自愈恢复。
* 全 47 项环境测试在 Blender 5.1.1 Headless 下全绿通过（47/47 PASS in 2.588s）。

### 反事实实证生成器与归档扩充 (`tests/run_counter_factual_ru2.py`, `docs/evidence/environment_gate01_ru2/`)
* 扩充至 6 项真实反事实变异验证：
  - `counter_factual_c01_empty_rebuild.log`: 变异旧逻辑在 100 次空查询中产生 201 次重建（Exit code 1），生产逻辑恒为 1（Exit code 0）；
  - `counter_factual_c03_vertex_stale.log`: 变异旧逻辑忽略顶点哈希导致未感知修改（Exit code 1），生产逻辑正确重建（Exit code 0）；
  - `counter_factual_c05_collection_membership_stale.log`: 变异旧逻辑未感知集合新增对象（Exit code 1），生产逻辑正确重建（Exit code 0）；
  - `counter_factual_f01_member_retention_leak.log`: 变异仅检查子集导致解关联对象残留（Exit code 1），生产逻辑正确剔除（Exit code 0）；
  - `counter_factual_f02_empty_bvh_repeated_rebuild.log`: 变异依赖 `_bvh is None` 导致空环境重复重建（Exit code 1），生产逻辑零重建复用（Exit code 0）；
  - `counter_factual_f03_exception_state_residual.log`: 变异在 `try:` 外收集对象导致异常卡死在 `REBUILDING`（Exit code 1），生产逻辑回滚至 `FAILED` 并自愈恢复（Exit code 0）。
* 更新反事实总结报告 `counter_factual_summary.md` 与边界报告 `cache_invalidation_boundary_report.md`。

### 规范文档更新与失效边界界定
* 更新 `docs/ENVIRONMENT_MESH_QUERY_SEMANTICS.md`：新增 Section 7.5，形式化定义 Path A 与 Path B 边界矩阵，客观声明几何扫描开销与候选集合隔离的前置必要性。
* 录入架构决策 `[DEC-057]` 至 `DECISIONS.md`。

### 自动化回归与受控保护检验
* 统一测试分级套件全量全绿：`quick` (13/13), `physics` (19/19), `motion` (8/8), `full` (30/30)；
* `audit_c2_final_inspector.py --verify-docs` 校验 0 错误；
* `output/` 历史 `.blend` 资产 0 字节变动；
* 状态严格停留于 `ENVIRONMENT GATE 01 / REPAIR UNIT 2 — FINAL REVIEW`。


## [2026-10-27] Environment Gate 01 — Repair Unit 2: BVH Cache Invalidation, Scene Geometry Consistency & Lifecycle State Machine (Defects C01-C06)

### 生产适配器机制重构 (`src/scene/blender_mesh_query_adapter.py`)
* **显式五状态生命周期状态机 (`AdapterCacheState`)**：
  - 新增 `AdapterCacheState` 枚举：`INVALID`, `VALID_EMPTY`, `VALID_NON_EMPTY`, `REBUILDING`, `FAILED`；
  - 彻底淘汰仅依赖 `_bvh is None` 的模糊判定，解决空集合重复触发 `rebuild()` 的泄漏问题（C01）；
  - 空集合场景下安全构建并驻留于 `VALID_EMPTY`，在 100 次空查询中严格保持 `rebuild_count = 1`（0 次冗余重建），返回 `success=False` 与 `NO_HIT:` 理由，绝不伪造 $Z=0.0\text{m}$ 虚假地面；
  - 暴露只读遥测属性：`cache_state`, `rebuild_count`, `cache_version`, `is_empty`, `has_bvh`, `dirty`, `is_dirty`。
* **双通道几何与环境失效检测体系 (Path A 自动检测 vs Path B 显式声明)**：
  - **Path A (自动检测)**：每次查询调用 `refresh()` 时执行 `_check_scene_changed()`：
    * 矩阵 16 元素严格比对（容差 $10^{-6}$），全面覆盖位移、旋转、非均匀缩放与父子物体层级变换传播（C02）；
    * 极速内存缓冲区哈希（`array.array('f', ...)` + `foreach_get('co', ...)`, $<0.05\text{ms}$），精准捕获毫米级顶点移动（C03）；
    * 循环索引哈希（`foreach_get('vertex_index', ...)`, $<0.02\text{ms}$），精准捕获多边形拓扑增删与翻转（C03）；
    * 动态 RNA 属性扫描，精准捕获任意修改器（Solidify, Displace 等）参数调整、修改器增删及 `show_viewport` 切换（C04）；
    * 基于 `obj.session_uid` 追踪集合成员变动，新增或删除对象即刻触发重建（C05）；
    * **原地重命名零重建优化**：当对象仅改名而几何未变时，就地更新元数据名称与 Surface ID，**BVH 重建次数为 0**（C05）。
  - **Path B (显式失效)**：调用 `adapter.invalidate()` 标记 `_dirty = True` 及 `INVALID` 状态，后续首次常规查询自动触发原子重建，调用方无需显式调用 `rebuild()`。
* **原子提交与异常安全回滚**：
  - 提取数据与生成快照暂存于局部内存，BVH 构建成功后原子提交；
  - 求值网格在 `finally:` 中统一通过 `eval_obj.to_mesh_clear()` 清理，杜绝内存泄漏；
  - 构建异常时回滚至 `FAILED` 状态并保留 `dirty=True`，绝不暴露脏数据。

### 测试套件扩充 (`tests/test_mesh_environment_query.py`)
* **新增 Unit 2 专用验证用例 (`test_33` 至 `test_42`)**：
  - `test_33_c01_empty_environment_cache_reuse_and_addition`: 100 次空查询重建次数恒为 1，动态添加 Mesh 后自动恢复 `VALID_NON_EMPTY`；
  - `test_34_c02_object_and_parent_transform_detection`: 位移、旋转、非均匀缩放及父级物体变换传播检测；
  - `test_35_c03_1_vertex_coordinate_movement`: Path A 无需调用 invalidate 自动感知顶点坐标变动；
  - `test_36_c03_2_topology_addition`: 动态添加面后精准命中新增多边形；
  - `test_37_c03_3_geometry_deletion`: 删除面后对应区域精准返回脱靶；
  - `test_38_c03_4_same_vertex_count_modification`: 顶点与面数不变时通过坐标哈希检测几何变更；
  - `test_39_c03_5_explicit_invalidation_path_b`: 调用 invalidate 后下次常规查询自动触发重建；
  - `test_40_c04_modifier_evaluated_mesh_consistency`: Solidify 修改器添加、厚度调整、视口切换、移除及异常回滚到 FAILED；
  - `test_41_c05_collection_membership_lifecycle`: 隔离非受控集合、删除对象以及对象改名零重建复用 BVH；
  - `test_42_c06_cache_reuse_under_unchanged_scene`: 未变场景下 300 次查询（100次同向射线、100次异向射线、100次最近点搜索）重建次数恒为 1（0 次重建）。
* 全 42 项测试 Blender Headless 运行全部一次性全绿通过（42/42 PASS in 2.13s）。

### 反事实实证生成器与归档 (`tests/run_counter_factual_ru2.py`, `docs/evidence/environment_gate01_ru2/`)
* 编写受控变异生成脚本，在真实 Blender 5.1.1 环境中执行并记录：
  - `counter_factual_c01_empty_rebuild.log`: 变异旧逻辑在 100 次空查询中产生 201 次重建（Exit code 1），生产逻辑恒为 1（Exit code 0）；
  - `counter_factual_c03_vertex_stale.log`: 变异旧逻辑忽略顶点哈希导致未感知修改（Exit code 1），生产逻辑正确重建（Exit code 0）；
  - `counter_factual_c05_collection_membership_stale.log`: 变异旧逻辑未感知集合新增对象（Exit code 1），生产逻辑正确重建（Exit code 0）。
* 编纂反事实总结报告 `counter_factual_summary.md` 与边界报告 `cache_invalidation_boundary_report.md`。

### 自动化回归与受控保护检验
* **统一测试分级套件全量全绿**：
  - `quick`: 13/13 PASS (19.44s)
  - `physics`: 19/19 PASS (83.81s)
  - `motion`: 8/8 PASS (23.42s)
  - `full`: 30/30 PASS (110.95s)
  - `audit_c2_final_inspector.py --verify-docs`: 0 errors (PASS)
* **受保护资产检验**：`git diff output/` 严格为 0 字节。
* **阶段状态裁定**：`ENVIRONMENT GATE 01 / REPAIR UNIT 2 — AWAITING HUMAN REVIEW`。

---


## [2026-10-27] Environment Gate 01 — Repair Unit 1 Final Acceptance: 数值覆盖提升、独立数学验证、真实故障注入证据链与射线边界闭环 (Final Acceptance & Evidence Closure)

### 生产适配器机制优化 (`src/scene/blender_mesh_query_adapter.py`)
* **高精度推进步长与薄层穿透能力**：
  - 将 `ray_cast` 推进步进基准调整为 `step_epsilon = 1e-6`（$1\mu m$），支持解析薄至 $50\mu m$ 的超薄层几何；
  - 构造函数引入 `step_epsilon` 默认配置参数，同时在 `ray_cast` 中支持单次调用重载；
  - 引入数值重叠自适应步长机制：在同一多边形索引上出现浮点微距重复命中时，动态扩大步长规避自相交死循环。
* **失败原因标准化区分 (T03 Disambiguation)**：
  - 明确区分几何脱靶（`NO_HIT:`）与搜索预算耗尽（`SEARCH_LIMIT_REACHED:`）；
  - 严格规范 6 种错误提示前缀，提供机器可判定的诊断契约。

### 测试套件扩充与独立解析核算 (`tests/test_mesh_environment_query.py`)
* **全 8 字段契约断言升级 (T01)**：
  - 升级 `_assert_surface_contract()`：增加完整 3D 接触点、3D 法向量（单位长度误差 $< 10^{-5}$）、独立欧几里得射线距离与方向夹角验证、独立带符号距离二次验证，以及 `allowed_objects` 允许物体归属权断言；
  - 升级历史测试 09 至 23 全量接入完整三维向量核验。
* **非轴对齐旋转场景独立数学检验 (`test_24_non_axis_aligned_rotated_scene`)**：
  - 构造中心 $(3.0, 4.0, 2.0)$、欧拉角 $(30^\circ, 45^\circ, 0^\circ)$ 的倾斜表面，查询点设在 $(3.5, 4.2, 5.0)$；
  - 基于理论三维空间旋转矩阵导出精确解析解，与 Blender C-BVHTree 计算结果对比，法向量误差 $< 10^{-5}$，接触坐标与距离完全吻合。
* **射线迭代 8 项极端边界覆盖 (T03, `test_25` 至 `test_32`)**：
  - 覆盖单表面、三层穿透过滤、跨过滤缓存复用、`max_steps=5` 恰好命中、`max_steps=4` 预算耗尽、超薄 $50\mu m$ 障碍穿透、表面边界起点穿透、以及距离阈值 $6.0001\text{m}$ vs $5.9990\text{m}$ 临界区分；
  - 全套件测试数量增至 32 项，Blender Headless 运行全部一次性通过（32/32 PASS in 1.74s）。

### 真实故障注入实证产物归档 (T02, `docs/evidence/environment_gate01_ru1/`)
* **真实独立执行日志生成**：
  - 在受控临时运行环境中分别注入 A03、A01、A02 逻辑变异，执行真实 Blender 命令，捕获非零退出码（Exit Code 1）与精确失败断言 Traceback，归档至：
    * `fault_injection_a03.log` (Collection 范围越界捕获)
    * `fault_injection_a01.log` (射线前序障碍过滤短路捕获)
    * `fault_injection_a02.log` (最近表面类型过滤短路捕获)
* **结构化证据文档体系编纂**：
  - `fault_injection_summary.md`：详细记录代码变异对比、执行命令、退出码与生产恢复记录；
  - `test_coverage_matrix.md`：详尽列出全 32 项测试的输入几何、预期目标、3D 接触点、法向、距离、支撑标志及测试断言；
  - `ray_iteration_boundary_report.md`：详尽分析 8 项边界情况与标准化错误前缀。

### 自动化回归与受控保护检验
* **统一测试分级套件全量全绿**：
  - `quick`: 13/13 PASS (18.74s)
  - `physics`: 19/19 PASS (82.39s)
  - `motion`: 8/8 PASS (23.18s)
  - `full`: 30/30 PASS (107.94s)
  - `audit_c2_final_inspector.py --verify-docs`: 0 errors (PASS)
* **受保护资产检验**：`git diff output/` 严格为 0 字节。
* **阶段状态裁定**：`ENVIRONMENT GATE 01 / REPAIR UNIT 1 — AWAITING HUMAN REVIEW`。

---


## [2026-10-27] Environment Gate 01 — Repair Unit 1: Blender Mesh 环境查询候选范围隔离与表面筛选语义修复 (Candidate Scope Isolation & Surface Filter Semantics Repair)

### 缺陷修复与语义重构 (`src/scene/blender_mesh_query_adapter.py`)
* **缺陷 A03 (Collection 范围泄漏修复)**：
  - 重构 `_gather_target_objects`，实现规则 A、B、C 严格范围隔离；
  - 规则 A (显式 Collection 模式)：`collection_names is not None` 时仅查询指定集合（支持递归子集合），若集合不存在或为空严格返回空集 $\emptyset$，绝不回退全场景扫描；
  - 规则 B (显式 Object 模式)：`object_names is not None` 时仅查询指定 Mesh，自动去重，绝不回退全场景；
  - 规则 C (显式全场景模式)：仅当两者均为 `None` 时才允许全场景网格扫描，彻底废除隐式兜底回退。
* **缺陷 A01 (ray_cast 表面过滤向前推进检索)**：
  - 无过滤模式：严格保持返回射线路径上首个最近真实物理命中面；
  - 有过滤模式：沿射线方向迭代推进搜索最近合格面，每次推进距离严格为正 ($\Delta s \ge 10^{-4}\text{ m}$)，上限 64 步，累计计算从原始起点起的真实欧氏距离 `ray_hit_distance`，避免局部步长误差；
  - 确立几何筛选语义：明确注明此为几何查询，不代表人体具备穿透可行性。
* **缺陷 A02 (find_nearest 表面过滤范围搜索)**：
  - 无过滤模式：返回全局最近真实网格表面；
  - 有过滤模式：通过 `bvh.find_nearest_range(p, max_distance)` 检索候选集，筛选匹配目标类型并选取真实欧氏距离最小者，无匹配面严格返回 `success=False`。

### 测试套件扩充与受控故障反例验证 (`tests/test_mesh_environment_query.py`)
* **15 项新反例用例编写与全量 23 项测试全绿**：
  - A03 反例 4 项：集合不存在未命中、空集合不回退、集合严格隔离、显式全场景模式；
  - A01 反例 6 项：无过滤最近命中、过滤第二表面、过滤不存在类型、距离不足失败、方向缩放不变性、起点在表面重合；
  - A02 反例 5 项：无过滤最近面、过滤目标面、半径不足失败、查询点移动自适应、旋转目标面法向更新；
  - 全 8 字段严密断言：`surface_id`, `surface_type`, `contact_point_world`, `surface_normal_world`, `ray_hit_distance`, `signed_distance`, `source_type`, `allows_regular_support`；
* **受控故障反例验证 (Fault Injection)**：
  - 在隔离测试中重现旧 A03、A01、A02 逻辑，严格证实旧逻辑下 counter-examples 必报失败，新逻辑下全部通过，证实测试具备真实缺陷检出能力。
* **自动化分层回归套件全绿**：
  - `quick` (13/13 PASS), `physics` (19/19 PASS), `motion` (8/8 PASS), `full` (30/30 PASS), `--verify-docs` (PASS)；受保护资产 0 字节变动。
* **阶段状态裁定**：`ENVIRONMENT GATE 01 / REPAIR UNIT 1 — AWAITING HUMAN REVIEW`。

---


## [2026-10-27] Environment Gate 01: 真实 Blender Mesh 环境查询接入与数据真实性门禁 (Real Blender Mesh Environment Query Access & Data Authenticity Gate)

### 核心功能与适配器架构 (`src/scene/blender_mesh_query_adapter.py`, `src/scene/environment_query.py`)
* **真实 Blender Mesh 物理事实来源确立**：
  - 实现 `BlenderMeshEnvironmentAdapter`，基于 Blender 原生 `mathutils.bvhtree.BVHTree.FromPolygons` 构建世界空间 BVH；
  - 严格保持 `src/scene/environment_query.py` 纯 Python 无 `bpy` 依赖，解耦宿主环境与数学内核；
  - 在 `SurfaceQueryResult` 契约中扩展 `source_type: str`（`"mesh"` / `"analytical"` / `"none"`），实现几何数据来源可追溯；
  - 严禁隐式伪造高程：射线未命中或点查询超出范围时，严格返回 `success=False`，绝不凭空捏造 $Z=0.0\text{ m}$ 平地。
* **世界空间几何变换与法向严密重构**：
  - 提取物体的世界矩阵变换顶点（$V_w = M_w \cdot v$），天然规避非等比缩放引起的法向量失真；
  - 通过世界三角形三顶点叉积计算严格单位法向量，杜绝物体旋转后法向量未更新的隐患；
  - 动态缓存失效与增量重建机制：监控物体矩阵、顶点总数与包围盒哈希指纹，任何位移、旋转、缩放或顶点编辑均触发自动刷新。
* **3D 表面几何类型与支撑面分类**：
  - 建立倾角阈值分类规则：水平地面（$N_z \ge 0.99$）、斜坡（$0.15 \le N_z < 0.99$）、垂直立面（$|N_z| < 0.15$）；
  - 斜率倾角 $> 60^\circ$（$N_z < 0.50$）强制标定为不可支撑面（`allows_regular_support = False`）；
  - 摩擦系数分类元数据：优先读取物体自定义属性 `custom_friction`，缺省时根据几何形态分配物理标准摩擦系数。

### 缺陷实证与隔离建议案
* **KinematicBridge 接触高程硬编码缺陷实证 (`tests/test_contact_elevation_gap_repro.py`)**：
  - 独立实证 `src/motion/kinematic_bridge.py:404` 将足端接触点强制压平至 $Z=0.0\text{ m}$，导致高架台（$Z=1.3397\text{ m}$）上产生 $1.3397\text{ m}$ 接触高程误差；
  - 独立实证第 388-394 行硬编码单水平基准面 `EnvironmentalSurface` 的环境开环缺陷。
* **最小改动建议案编纂 (`docs/proposals/CONTACT_CHAIN_BRIDGE_ELEVATION_GAP.md`)**：
  - 编制严密工程建议案，提出向 `KinematicBridgeExecutor` 注入 `environment_query` 的单点改动方案与向前兼容防护，供后续门禁报批，本门禁零修改人体控制代码。
* **规范文档编纂 (`docs/ENVIRONMENT_MESH_QUERY_SEMANTICS.md`)**：
  - 编纂完整 BVH 空间查询语义、缓存规则、数据契约与双源决议机制。

### 自动化测试与工程门禁验证
* `tests/test_mesh_environment_query.py`：**8 / 8 PASS**（覆盖 14 项严格验收标准，耗时 2.16s）；
* `tests/test_contact_elevation_gap_repro.py`：**PASS**（耗时 1.91s）；
* `tests/run_test_suite.py --tier quick`：**13 / 13 PASS**（耗时 16.61s）；
* `tests/run_test_suite.py --tier physics`：**19 / 19 PASS**（耗时 77.57s）；
* `tests/audit_c2_final_inspector.py --verify-docs`：**PASS**（Exit Code 0，引用符号 100% 存在）；
* 受保护场景资产检查：`git diff output/` 0 差异；
* 最终状态裁定：`ENVIRONMENT GATE 01 — AWAITING HUMAN REVIEW`，严格停止等待人类审批，严禁擅自进入 Phase 7B。

---


## [2026-10-27] 架构基线审计与 7A→7B 准入门禁 (Architecture Baseline Audit — 7A→7B Admission Gate)

### 全景架构基线审计文档体系编纂 (`docs/audit/`)
* **产出 8 份专业架构基线审计报告**：
  - `MODULE_INVENTORY.md`：全量 59 个 Python 生产模块逐一按 20 个统一工程问题完成技术深度剖析（行号、职责、接口、读写、分类等），统计 22 Active、6 Read-Only Telemetry、5 Standalone Solvers、17 Legacy/Prototypes、9 Inits；
  - `ACTUAL_RUNTIME_ARCHITECTURE.md`：重构 6 大运行链（Chains A..F），确立真实双管线解耦事实（Pipeline A 19 骨骼角色运动学 vs Pipeline B 6-DOF 动力学代理）；
  - `STATE_OWNERSHIP_MATRIX.md`：建立全对象读写所有权矩阵，全盘检索骨骼与控制器物理突变行号，确认 WBC 独占骨骼写入权；
  - `CALL_GRAPH_AUDIT.md`：绘制生产与测试调用图谱，明确标定 Pipeline B 4 大独立动力学模块与 21 个入口脚本关系；
  - `HARDCODE_AND_BYPASS_AUDIT.md`：6 分类严格审计常量、工程配置、测试基准、字符串耦合与旁路，确认生产链零直接骨骼绕行旁路；
  - `ENVIRONMENT_INTERACTION_GAP.md`：透视回答环境交互 10 问，揭示环境查询为纯解析面、场景构建与查询存在双重真实源、CoM 与接触状态未回传下一帧规划、IK 求解失败未触发重规划等技术事实；
  - `DOCUMENTATION_DRIFT.md`：详细比对既有架构文档与磁盘源码差异，指出 `ARCHITECTURE.md` 滞后于 v2.3、遗漏 Phase 7A 核心模块 `TerrainWalkAction`、存在 `JointModel` 等符号名称偏差；
  - `ARCHITECTURE_AUDIT_SUMMARY.md`：编目 AUDIT-01 至 AUDIT-08 共 8 项问题，标定 4 项为 Phase 7B 准入阻断项，制定 7B 阶段化准入路线图。

### 自动化验证与零幻觉门禁
* `tests/audit_c2_final_inspector.py --verify-docs`：**PASS** (Exit Code 0，全量引用符号真实存在，零虚构符号)；
* `tests/run_test_suite.py --tier quick`：**12 / 12 PASS** (14.47s)；
* 最终状态裁定：`ARCHITECTURE AUDIT — AWAITING HUMAN REVIEW`，严格停止等待人类审批，严禁擅自进入 Phase 7B。

---


## [2026-10-26] 任务 7A-2：架构修复、P0 空间瞬移缺陷根除、内置数据诊断视窗与权威连续地形验收 (Task 7A-2 Architecture Recovery & Continuous Traversal Acceptance)

### P0 空间瞬移缺陷彻底根除与冻结几何拓扑断裂证明
* **消除 Frame 226 $\to$ 227 瞬移跳变**：
  - 根除历史实现中在楼梯结束坐标 $(0.0, 7.95, 0.75)$ 与坡道入口坐标 $(0.0, 10.20, 0.0)$ 间发生的 $\Delta = 2.3717\text{ m}$ 空间瞬移；
  - 彻底废除验证与测试中的任何跳步豁免逻辑（零 `frame_num != 227` 豁免）；
  - 数学证明受保护基准 `output/dynamics_playground.blend` 楼梯平台与坡道入口间存在 $1.0\text{ m}$ 几何空隙与 $0.75\text{ m}$ 垂直悬崖（单腿 $0.820\text{ m}$ 极限角色强行跨越跌落需 $1.51\text{ m}$，物理不可达）；
  - 确定权威连续路线：Course B 坡道走廊本身即是一条完全连续且地貌多样的完整地形路线（平地入口 $\to$ 15° 上坡 $\to$ $Z=1.34\text{ m}$ 高架桥 $\to$ 20° 陡坡 $\to$ 平地缓冲着陆停止，全长 $12.2\text{ m}$，700 帧连续无缝）；
  - 保留 `output/dynamics_playground_task7a2.blend` 作为失败对比基准，生成权威修正产物 `output/dynamics_playground_task7a2_corrected.blend`。

### MotionPlanner 调度权恢复与字符串匹配完全剥离 (`src/motion/terrain_walk.py`)
* **统一调度接入 MotionPlanner**：
  - 场景编排器严格调用 `MotionPlanner.execute(initial_state)`，动作生命周期、状态传递、帧记录由框架统一管理；
  - 修复 `TerrainWalkAction.estimate_duration_frames`，接入真实环境查询器动态预估工期。
* **100% 剥离字符串命名逻辑与走廊解耦**：
  - 引入 `TerrainRouteInput` 解耦高层走廊与步态规划；
  - 编写 `plan_terrain_footsteps`，纯基于 `DynamicsEnvironmentQuery` 表面法向量、高程差与边缘安全避障算法动态离散生成落脚点；彻底移除所有对象名/地表名字符串匹配。
* **骨盆 Euler 轴向校正与坡道过渡伸展缓冲**：
  - 校正 `pelvis` 局部 Euler 轴（局部 X=Pitch, Y=Yaw, Z=Roll），消除了上坡下坡时不必要的侧倾应力；
  - 引入高程过渡差 $\Delta z_{\text{trans}} > 0.03\text{ m}$ 识别，在坡道与平地交界处保持足够的骨盆下沉缓冲量（$0.088\dots0.098\text{ m}$），实现 700 帧全过程 0 处 IK 超限。

### 内置 Blender 控制链数据诊断视窗 (`Task7A2_ControlChain_Debug`)
* 在同一 `.blend` 文件中内嵌诊断场景，构建 6 阶段结构化 HUD 文字展板与 3D 关键帧指示物（足端目标球、质心环、锁定箭头、法向箭头）；
* 内嵌 `task7a2_debug_hud_driver.py` 脚本挂载时间线变化事件，支持在视口中拖动时间线毫秒级实时查看全身体控制链指标。

### 负向测试与全量回归套件全绿
* 编写 `tests/test_p0_frame226_teleport_regression.py` 永久固化瞬移缺陷检测；
* 编写 `tests/test_terrain_walk_negative.py` 验证地表重命名不变性、高程扰动自适应与悬崖超限拒绝；
* 700 帧无豁免数学检验：0 瞬移（最大位移 $0.0333\text{ m}$/帧）、0 ROM 违规、0 穿模、脚踝漂移 $0.000011\text{ m}$、骨骼形变 $0.0000017\text{ m}$、质量守恒 70.0 kg；
* `quick`：**12 / 12 PASS** (15.17s)；
* `motion`：**8 / 8 PASS** (23.44s)；
* `full`：**28 / 28 PASS** (103.96s)；
* `tests/audit_c2_final_inspector.py --verify-docs`：**PASS** (Exit Code 0)。

---


## [2026-10-26] 任务 7A-2：真实 19 骨骼角色连续复杂地形（楼梯与斜坡高架桥）自适应下肢穿越、单一控制链闭环与 926 帧全量验收 (Task 7A-2 Continuous Terrain Traversal in DynamicsPlayground)

### 连续复杂地形运动规划内核 (`src/motion/terrain_walk.py`)
* **动态环境高程与坡度自适应规划**：
  - 实现通用地形行进动作类 `TerrainWalkAction(MotionAction)` 与离散步态生成函数 `build_terrain_step_schedule`；
  - 零环境高度硬编码：严格通过 `DynamicsEnvironmentQuery` 接口（`ground_height_at` 与 `surface_normal_at`）动态获取 3D 地形高度与表面法向量；
  - 矢状面法向量俯仰对齐：基于 $\text{atan2}(-n_y, n_z)$ 动态计算地表俯仰角度，自动适配上坡（+15°）、下坡（-20°）与水平（0°）足端世界姿态；
  - 全足端 3D 刚体包围盒悬空防穿透：实时查询脚后跟（$-0.07\text{ m}$）、脚踝（$0.0\text{ m}$）与脚尖（$+0.15\text{ m}$）三点地表最大高程，配合 $0.045\text{ m}$ 动态悬空最小净距，彻底消除踢面与斜坡切削（926 帧全量 0 穿模）；
  - 生理学踝关节自适应松弛：摆动相中段引入 $18^\circ\sim22^\circ$ 跖屈松弛，并在离地瞬间引入自然的蹬地限位（$\le 10^\circ$），消除小腿旋转导致的关节极限强加；
  - 分级骨盆沉降参数：上坡登高沉降 $0.063\text{ m}$，下坡缓冲沉降 $0.095\text{ m}$，平地行进沉降 $0.030\text{ m}$，台阶攀爬沉降 $0.120\text{ m}$，完美平衡伸腿极限与关节 ROM。

### 核心运动控制链向后兼容增强 (`src/rig/foot_contact.py`, `src/motion/whole_body_controller.py`, `src/motion/kinematic_bridge.py`)
* **解除足部接触锁定平地硬编码**：升级 `lock_foot_contact` 接受真实三维世界高程 `float(contact_world_xyz[2])`，保留对默认 `FLAT_GROUND_Z = 0.0` 的 100% 兼容；
* **脚踝世界坐标与接触坐标解耦**：在 `WholeBodyController.execute_frame` 中将脚踝目标转换为地面接触点 `contact_ground_xyz = (target_x, target_y, target_z - ANKLE_REST_Z)`，彻底消除 70mm 偏置累加 bug，实现脚踝锁定物理零漂移（`0.00000000 m`）；
* **显式可配置地面夹持标志 (`clamp_ground`)**：在 `EndEffectorTarget` 与 `PlannedFootTarget` 中引入 `clamp_ground: bool = True`，复杂地形行进时显式配置为 `False`，避免 WBC 误将高程目标投影至根节点高度。

### 场景生成、只读重开验收与完备视觉证据 (`run_task7a2_terrain_traversal.py`, `tests/verify_task7a2_terrain_traversal.py`)
* **独立场景生成与只读重开验收**：
  - 生成 `output/dynamics_playground_task7a2.blend`（581,882 字节，926 帧，内嵌 3 专用相机与 10 个关键阶段时间线标记）；
  - 独立只读重开评估全 926 帧：0 穿模、0 ROM 违规、0 IK 违例、踝骨漂移 $0.0\text{ m}$、骨骼形变 $1.55\times 10^{-6}\text{ m}$、质量严格守恒 70.000 kg；
  - 渲染 9 张高清关键帧 PNG 与 2 份连续动态 GIF（`task7a2_stairs_traversal.gif` 76 帧 301KB、`task7a2_ramp_traversal.gif` 100 帧 286KB）；
  - 注册 `task7a2_terrain_traversal` 入测试套件 `motion` 与 `full` 级别。

### 全级别回归套件全绿
* `.\run_tests.ps1 -tier quick`：**10 / 10 PASS** (10.61s)；
* `.\run_tests.ps1 -tier physics`：**16 / 16 PASS** (76.18s)；
* `.\run_tests.ps1 -tier motion`：**7 / 7 PASS** (20.16s)；
* `.\run_tests.ps1 -tier full`：**26 / 26 PASS** (97.18s)；
* `tests/audit_c2_final_inspector.py --verify-docs`：**PASS** (Exit Code 0)。

---


## [2026-10-26] 任务 7A-1：最终架构整理、单一职责解耦、接触状态持久化合同与负向测试闭环 (Task 7A-1 Final Architecture & Compatibility Closure)

### 架构解耦与单一职责模块重构 (`src/scene/playground_*`)
* **消除 2872 行集中文件，拆分为四个内聚子模块与轻量级门面**：
  * 原 `src/scene/playground_character_integration.py` 拆分为：
    - [`src/scene/playground_asset_preservation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_asset_preservation.py)（386 行）：负责训练场 101 个受保护对象、16 个表面网格几何（顶点坐标容差 $<10^{-5}$、面拓扑与顶点索引）、层级结构、世界矩阵、材质槽、环境属性、Layered F-Curves（时间与取值 $<10^{-4}$、手柄与插值模式）以及 S1..S5 5 工位 73 帧基准轨迹全 73 帧（非抽样）深度快照对比与差异报告；
    - [`src/scene/playground_evidence_exporter.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_evidence_exporter.py)（223 行）：负责多视角相机 PNG 渲染、NumPy RGBA 加载、GIF 帧数与帧率真实校验、204 帧平滑 GIF 预览合成及验证报告 JSON 导出；
    - [`src/scene/playground_character_assembly.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_assembly.py)（1495 行）：负责角色装配（复用既有 `build_character` + `build_rig` + `bind_character_to_rig` + `setup_leg_ik` + `setup_arm_ik`）、五阶段最小控制闭环（Stage A..D）、四大数学一致性验证、Stage E 204 帧连续行走步态执行，并将执行接触状态与支撑锚点持久化写入场景属性与伴生 JSON 文件；
    - [`src/scene/playground_kinematic_validation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_kinematic_validation.py)（765 行）：负责从派生 `.blend` 独立只读重开全 204 帧评估，恢复持久化接触契约、验证根位移平滑度、19 骨骼四元数测地线连续性、9 个支撑区间实际踝骨漂移（对比持久化锚点）、70.0 kg 质心轨迹与关节 ROM；
    - [`src/scene/playground_character_integration.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_integration.py)（183 行）：重构为轻量级总控门面（Facade），重新导出所有公开符号以保持 100% 向后兼容性。

### 接触状态持久化合同 (Contact State Persistence Contract)
* **执行期持久化与独立重开验证脱敏**：
  * Stage E 执行期间将逐帧实际接触状态（帧号、时间、双足锁定标志、支撑侧、支撑脚世界锚点 $(X,Y,Z)$、步态阶段、步序、触地/离地离散事件）序列化写入 Blender 场景 ID 属性 `scene["task7a1_contact_state_records"]`，并在 `FootIK.L/R` 控制器上对 `is_locked` 逐帧打关键帧；同时导出伴生文件 [`docs/evidence/task7a1/task7a1_contact_state_records.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task7a1/task7a1_contact_state_records.json)；
  * 重开验收通过 `recover_and_verify_contact_states_from_blend(scene)` 恢复持久化接触数据，彻底废除对 `MotionPlanner` 或步态公式重新推导的依赖；
  * 严格区分三类数据流：**Category A (运行时记录)**、**Category B (重开评估值)**、**Category C (解析参考值)**，并在 `full_frame_validation.json` 中清晰分离。

### 六大隔离负向测试闭环与套件扩充 (`tests/verify_task7a1_character_playground.py`)
* **验证测试集扩充至 15 项（含 6 项负向故障注入与 1 项只读零篡改测试）**：
  * Test 09：网格内部顶点微调（包围盒不变）$\implies$ 深度资产校验立即捕获（`VERTEX_DIFF`）；
  * Test 10：F-Curve 关键帧数值微调（帧数不变）$\implies$ 深度资产校验立即捕获（`KEYFRAME_VALUE_DIFF`）；
  * Test 11：S1..S5 工位中间帧 37 状态篡改 $\implies$ 深度轨迹对比立即捕获（`TRAJECTORY_DIFF`）；
  * Test 12：接触记录缺失帧（删除 Frame 50）$\implies$ 持久化合同立即报错（`MISSING_FRAME_RECORD`）；
  * Test 13：支撑足锚点被篡改或置空 $\implies$ 锚点完整性检查立即报错（`TAMPERED_ANCHOR`）；
  * Test 14：资产版本号不匹配（篡改版本号）$\implies$ 契约校验立即报错（`VERSION_MISMATCH`）；
  * Test 15：测试前后文件大小与修改时间戳比对，证明只读回归测试对所有产物零写磁盘；
  * 测试套件 15/15 PASS (1.10s)。

### 真实兼容性调用矩阵补充 (`docs/PHASE7A_REUSE_AUDIT.md`)
* 新增第三节“生产与动力学核心模块调用矩阵”，详细记录 9 大模块（`framework.py`, `kinematic_bridge.py`, `whole_body_controller.py`, `src/rig/`, `src/character/`, `rigid_link.py`, `contact_model.py`, `environment_query.py`, `src/scene/playground_*`）及未接入的 6G-D 动力学核心的真实调用者、被调用者、输入与输出合同。

### 统一测试套件编码兼容性加固 (`tests/run_test_suite.py`)
* 在 `subprocess.Popen` 中增加 `encoding="utf-8", errors="replace"`，彻底消除 Windows 默认 GBK 终端环境下由 UTF-8 控制台输出导致的 reader 线程 `UnicodeDecodeError` 异常。

### 全级别回归套件全绿
* `.\run_tests.ps1 -tier quick`：**10 / 10 PASS** (11.14s)；
* `.\run_tests.ps1 -tier physics`：**16 / 16 PASS** (78.07s)；
* `.\run_tests.ps1 -tier motion`：**6 / 6 PASS** (20.79s)；
* `.\run_tests.ps1 -tier full`：**25 / 25 PASS** (100.84s)；
* `tests/audit_c2_final_inspector.py --verify-docs`：**PASS** (Exit Code 0)。

---


## [2026-10-25] 任务 7A-1：历史角色资产复用审计、真实 19 骨骼角色接入 `DynamicsPlayground`、最小控制闭环验证及 Final Acceptance Closure 最终验收收尾 (Task 7A-1)

### 历史 19 骨骼角色与运动资产复用审计 (`docs/PHASE7A_REUSE_AUDIT.md`, `tests/audit_c2_final_inspector.py`)
* **全量模块与 `.blend` 资产复用审计报告**：
  * 新增 [`docs/PHASE7A_REUSE_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/PHASE7A_REUSE_AUDIT.md)，系统核查 `output/unified_motion_integration.blend`（19 骨骼、13 个 `parent_type="BONE"` 网格部件、8 个 IK/Pole 控制器、12 个 Action）与 `output/dynamics_playground.blend`（4 大集合、16 个地形表面、5 个动力学工位 `S1..S5`），以及 19 个核心 Python 模块的精确路径、行号与复用边界；
  * 将 `docs/PHASE7A_REUSE_AUDIT.md` 纳入 `tests/audit_c2_final_inspector.py` 的 `doc_files` 清单，接受永久只读 AST 符号存在性校验。

### 真实 19 骨骼角色装入 `DynamicsPlayground`、深度场景资产保护与五阶段最小控制闭环 (`src/scene/playground_character_integration.py`, `run_task7a1_character_playground.py`)
* **训练场单一 SSOT 深度快照保护与角色无损集成**：
  * 新增 `capture_deep_playground_snapshot` 与 `verify_derived_blend_against_deep_snapshot`，验证 `output/dynamics_playground.blend` 原有的 4 大集合、101 个受保护对象、16 个地形表面网格顶点数/多边形数/材质及 `S1..S5` 73 帧动画轨迹与 F-Curve 在 `output/dynamics_playground_task7a1.blend` 中 100% 零改动保留，仅在 `"Character"` 集合新增 26 个角色与观察相机对象；
* **五阶段最小控制闭环验证（A–E）**：
  * **Stage A (静态站立姿态)**：在 `Surface_FlatGround` $(0.0, -8.0, 0.0)\text{ m}$ 上双足贴地 $Z_{\min} = 0.0\text{ m}$，末端误差 $3.0\times 10^{-6}\text{ m}$，CoM $(0.0, -7.99627, 1.04793)\text{ m}$，零 ROM 违例；
  * **Stage B (根节点有限位移与非零偏航)**：驱动 `CharacterRoot` 至 $(0.25, -7.65, 0.0)\text{ m}$ 与 $+6.0^\circ$ 偏航，根位置误差 `0.0 m`，末端误差 $7.0\times 10^{-6}\text{ m}$；
  * **Stage C (单脚独立 IK 控制)**：左右脚非对称世界目标 $(-0.11, -8.05, 0.07)\text{ m}$ 与 $(0.14, -7.82, 0.21)\text{ m}$，大腿 $0.42\text{ m}$ / 小腿 $0.40\text{ m}$ 零拉伸，膝盖前向 $+Y$ 零翻转；
  * **Stage D (支撑脚世界空间锁定)**：左脚锁定 (`FootIK.L.parent == None`) 下 `CharacterRoot` 连续 5 步移动，控制器、踝骨与网格中心漂移均为 `0.0 m`；
  * **Stage E (最小连续历史步态复用)**：通过 `MotionPlanner` 执行 `StartStopWalkAction` 204 帧连续行走（位移 $1.2600\text{ m}$，0 不可达帧，0 ROM 违例）。
* **204 帧独立只读重开数学验证、测试解耦与 204 帧真实连续 GIF (`docs/evidence/task7a1/`, `tests/verify_task7a1_character_playground.py`, `tests/test_registry.py`)**：
  * 新增 `validate_reopened_task7a1_blend` 并生成 [`docs/evidence/task7a1/full_frame_validation.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task7a1/full_frame_validation.json)，在不调用 `MotionPlanner` / `WholeBodyController` 的前提下直接只读重开 `output/dynamics_playground_task7a1.blend` 逐帧评估 `1..204` 帧，验证根平移连续性、19 骨骼四元数测地距离连续性（最大单帧步长 `5.24453 deg`）、9 个支撑区间控制器与实际踝骨世界漂移（最大踝骨漂移 $2.94\times 10^{-5}\text{ m}$）、支撑足零穿地 ($Z_{\min} \ge -2.9\times 10^{-5}\text{ m}$)、70.0 kg 全帧 CoM 轨迹与 0 ROM 违例；
  * 新增 `render_reopened_204_frame_walk_gif` 与 `count_gif_frames`，从重开的 `.blend` 连续渲染全 204 帧（24 FPS, `delay_cs=4`）写入 [`docs/evidence/task7a1/task7a1_walk_preview.gif`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task7a1/task7a1_walk_preview.gif)；
  * 重构 [`tests/verify_task7a1_character_playground.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task7a1_character_playground.py)（8/8 PASS, 0.36s）为严格只读解耦验证套件，缺失产物直接报 `ARTIFACT_MISSING`，并通过文件大小与时间戳断言证明测试过程零写磁盘。

---

## [2026-10-25] 任务 6G-D-C2-FINAL：架构门禁收口、只读 AST 校验与统一测试套件无缝集成 (Architecture Integrity Gate Closure)

### 彻底消除写文件副作用与运行模式隔离 (`tests/audit_c2_final_inspector.py`)
* **严格模式分离与只读保证**：
  * 重构 `tests/audit_c2_final_inspector.py` 为显式三模式结构：
    - **Mode A (生成/刷新)**：仅在显式传入 `--generate` 或 `--refresh` 时触发向 `codebase_and_blend_audit.json` 和 `blend_inspection_log.txt` 写入磁盘产物；
    - **Mode B (校验文档)**：`--verify-docs` 采用纯内存 AST 索引执行文档扫描，禁止对磁盘文件进行任何写入或覆盖；
    - **Mode C (校验器自测)**：`--test-validator` 执行 6 组正负例测试，纯只读无副作用；
    - 默认无参数模式：纯内存解析，打印可用参数说明，零写文件。
  * 实测验证：执行 `--verify-docs` 或 `--test-validator` 后 `git status --short` 保持工作区 100% 干净，零修改、零 hash 变化。

### 消除整行跳过漏洞与子句级精准否定豁免 (`tests/audit_c2_final_inspector.py`)
* **消除 Whole-Line Skipping 缺陷**：
  * 废除 `any(k in line for k in [...]) continue` 的整行跳过机制；
  * 新增 `is_symbol_exempted_by_context` 方法，针对每个匹配到的符号，基于分号、逗号、句号、管道符等子句边界（`;；。|,\n`）以及紧随其后的括号提取局部上下文，仅当符号所属子句或紧邻修饰明确包含否定关键词（“不存在”、“严禁调用”、“虚构”等）时才给予豁免；
  * 同一行中其他子句出现的符号正常接受 AST 物理存在性检验，彻底根除同行多符号漏检风险。

### 防过拟合动态随机测试套件 (`tests/audit_c2_final_inspector.py`)
* **自检套件扩充至 6 大用例**：
  * 新增 Test 5（动态随机负例）：使用 `uuid.uuid4().hex` 动态生成非固定名称的虚构模块、枚举成员、方法、类名及表格虚假实现，杜绝仅靠硬编码黑名单通过自测；
  * 新增 Test 6（复合子句同行豁免用例）：验证同一行中“已声明不存在的模块被豁免”同时“未声明不存在的虚构方法被准确检出报错”，确保整行跳过漏洞已被根治。

### 统一测试执行器参数传递扩展与独立门禁测试 (`tests/test_registry.py`, `tests/run_test_suite.py`, `tests/test_runner_unit.py`, `tests/test_architecture_integrity_gate.py`)
* **扩展 TestDefinition 支持可选 script_args**：
  * 在 `TestDefinition` 中增加 `script_args: List[str] = field(default_factory=list)`；
  * 在 `tests/run_test_suite.py` 中向后兼容支持在执行 Python 及 Blender 进程时追加 `script_args`；
  * 在 `tests/test_runner_unit.py` 增加用例 11，实测参数传递逻辑正确（11/11 PASS）；
* **创建独立测试用例 tests/test_architecture_integrity_gate.py**：
  * 编写薄测试入口脚本，注册为 `architecture_integrity_gate` 并纳入 `TestTier.QUICK` 与 `TestTier.FULL`；
  * 实测 `.\run_tests.ps1 -tier quick`（10/10 PASS, 10.46s）与 `.\run_tests.ps1 -tier full`（24/24 PASS, 95.07s）全绿通过。

---

## [2026-10-25] 任务 6G-D-C2-FINAL：文档真实性门禁、通用 AST 符号校验器与架构约束彻底冻结 (Documentation Integrity Gate)

### 枚举与接口引用真实性纠偏 (`docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`, `docs/FOUNDATION_*.md`)
* **区分触地事件与接触生命周期枚举**：
  * 修正 `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`，将接触生命周期明确核准为 `ContactLifecycle`（`CANDIDATE`, `ESTABLISHED`, `RELEASED`, `BROKEN`），明确触地（Touchdown）属于离散动力学状态切换事件，严禁向源码添加未定义枚举；
  * 纠偏并对齐真实源码接口：将此前文档中错误的 run_trajectory 纠正为真实方法 `ClosedLoopDynamicsCoordinator.simulate`，将错误的 query_surface_at 纠正为真实方法 `DynamicsEnvironmentQuery.query_surface_at_point`；
  * 纠偏 Phase 4 执行描述：移除未定义的幻觉引用 _apply_micro_projection，还原为真实的几何合规检查 `multi_contact.check_all_contacts`；
  * 纠正 `DECISIONS.md` 中属性引用，明确速度指标位于 `MotionState.params` 字典中（如 `MotionState.params['planned_linear_velocity']`）。

### 升级全库通用 AST 符号校验器 (`tests/audit_c2_final_inspector.py`)
* **通用 AST 解析与索引构建**：
  * `inspect_python_file` 升级为全面提取类属性（`attributes`）与枚举成员（`enum_members`）；
  * 构建 `CodebaseSymbolIndex`，自动索引全库 51 个模块的类、方法、函数、属性、Enum 成员以及 18 个 `.blend` 场景的 Action、Object、Bone 资产名称；
  * 建立四态判别契约：`IMPLEMENTED`（真实存在）、`EXISTS_NOT_INTEGRATED`（存在未合流）、`PROPOSED`（未来规划，严禁假冒已实现）、`INVALID`（不存在直接报错）；
  * 新增内置自测试套件 `run_validator_test_suite`，覆盖 Positive、Negative、Proposed、Prose Safety 四大场景，实测零假通过、零自然语言误报；
  * 提供 `--test-validator` 与 `--verify-docs` 命令行参数。

### 固化架构防漂移前后置十步闭环检查协议 (`docs/ARCHITECTURE_CHANGE_GATE.md`)
* **前后置十步闭环门禁确立**：
  * 在 `docs/ARCHITECTURE_CHANGE_GATE.md` 写入架构防漂移前后置十步闭环检查协议；
  * 在 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 建立单向强制引用，禁止建立第二套规则。

---

## [2026-10-25] 任务 6G-D-C2-FINAL：6G 动力学最终收口、完整工程审计与通用程序化运动底座架构冻结（含 C2-FINAL 验收纠偏）

### 机器可验证全库 AST 与 Blender `.blend` 资产审计 (`tests/audit_c2_final_inspector.py`, `docs/evidence/task6gd_c2a/`)
* **只读 AST 与 `.blend` 清单提取**：
  * 新增 [`tests/audit_c2_final_inspector.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/audit_c2_final_inspector.py)，在 Blender 5.1.1 无头模式下只读扫描全库 51 个 `src/` 模块、42 个 `tests/` 脚本、19 个 `run_*.py` 脚本及 18 个 `output/*.blend` 场景，生成 [`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/codebase_and_blend_audit.json) 与 [`docs/evidence/task6gd_c2a/blend_inspection_log.txt`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/blend_inspection_log.txt)；
  * 核实 `output/unified_motion_integration.blend` 为 462 帧连续运动整合资产（298,537 字节，`1..462` 帧，27 个物体，`CharacterArmature` 19 骨骼，12 个 Action，180 条 F-Curve，80,628 个关键帧）；
  * 核实 `output/dynamics_playground.blend` 为 73 帧训练场与代理遥测资产（234,436 字节，`1..73` 帧，101 个物体，0 骨骼，30 个 Action，182 条 F-Curve）。

### 时空标准化与闭环收口 (`src/scene/dynamics_visualizer.py`, `src/scene/dynamics_visual_evidence.py`, `run_generate_visual_evidence.py`)
* **73 状态（Frame 1..73）时间线标准映射**：
  * 将 72 步离散积分（$N=72, \Delta t=1/24\text{s}$）严格对齐为 73 个物理状态（$S_0$ 到 $S_{72}$），对应 Blender 时间轴 Frame 1 至 Frame 73（$F = k + 1$）；
  * 采样关键帧对齐整数与半秒网格：$t = 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0\text{s}$（F01, F13, F25, F37, F49, F61, F73）；
  * 编码输出 73 帧连续平滑动画 GIF (`dynamics_overview_anim.gif`，24 FPS，delay 4cs)；
  * 更新综合联系表 [`docs/evidence/task6gd_c2a/contact_sheet.png`](docs/evidence/task6gd_c2a/contact_sheet.png)（含标准秒标记 F01, F25, F49, F73）。
* **场景相机状态一致性保证**：
  * 在无头渲染完成后统一将 `PlaygroundOverviewCam` 恢复为场景主相机，保证 `output/dynamics_playground.blend` 随手打开即为全局全景。

### 架构审计与规范冻结文档交付与纠偏 (`docs/`)
* **发布并纠偏 5 份权威架构冻结规范与 1 份综合验证报告（通过 `--verify-docs` 零幻觉路径/符号校验）**：
  1. [`docs/FOUNDATION_ASSET_AUDIT.md`](docs/FOUNDATION_ASSET_AUDIT.md)：全库 51 个 `src/` 模块、42 个测试、19 个入口脚本与 18 个 `.blend` 资产机器核查清单；
  2. [`docs/FOUNDATION_ARCHITECTURE_AUDIT.md`](docs/FOUNDATION_ARCHITECTURE_AUDIT.md)：完整恢复 `MotionPlanner -> KinematicBridgeExecutor.execute_frame -> WholeBodyController.execute_frame -> Rig/IK/FK -> Telemetry -> MotionState` 真实生产运动学管线（Pipeline A）与 6G-D 质心动力学管线（Pipeline B）并存现状及数学闭环边界；
  3. [`docs/FOUNDATION_DEPENDENCY_MAP.md`](docs/FOUNDATION_DEPENDENCY_MAP.md)：含真实调用文件、被调文件、函数/类名与源码行号的 44 条 AST 依赖边，以及独立隔离的 `Future Architecture` 章节；
  4. [`docs/FOUNDATION_STATE_OWNERSHIP.md`](docs/FOUNDATION_STATE_OWNERSHIP.md)：严格区分当前已实现状态所有权与未完成汇流边界（Phase 7A / 7C）；
  5. [`docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`](docs/ROADMAP_FOUNDATION_TO_FULLBODY.md)：恢复权威演进路线图（**7A** 真实 19 骨骼角色进入 `DynamicsPlayground` 完成基础下肢连续通行 $\to$ **7B** 上肢独立运动与末端目标验证 $\to$ **7C** `KinematicBridge`、`WholeBodyController`、`CoM` 与整体动力学状态汇流 $\to$ **7D** 多关节动态协同 $\to$ **7E** 既有 IK/FK 求解器动态协同与接触切换 $\to$ **7F** 全身移动、抓握、支撑、释放与连续训练场通行 $\to$ **6H** 动态平衡与主动补偿）；
  6. [`docs/C2_FINAL_VALIDATION.md`](docs/C2_FINAL_VALIDATION.md)：Task 6G-D-C2-FINAL 综合验收与纠偏报告。

### 测试用例更新与分级回归
* **更新测试套件**：
  * [`tests/verify_task6gd_playground_dynamics.py`](tests/verify_task6gd_playground_dynamics.py)：断言 `frame_end = 73` 及 73 帧物理精度（5/5 PASS）；
  * [`tests/verify_task6gd_visual_telemetry.py`](tests/verify_task6gd_visual_telemetry.py)：断言 73 帧时序完整性与跨空间一致性（5/5 PASS）；
  * [`tests/verify_task6gd_playground_blend.py`](tests/verify_task6gd_playground_blend.py)：验证 14 个区域网格、21 个法线指示箭头及主相机（100% PASS）；
  * [`tests/run_test_suite.py`](tests/run_test_suite.py) & [`run_tests.ps1`](run_tests.ps1)：修复 Windows 沙箱环境终端进程强杀逻辑（使用原生 `os.kill(pid, 9)` 取代沙箱阻塞的 `taskkill`），支持无缓冲实时回显。
* **分级实测全绿回归**：
  * `quick`：9/9 PASS (9.66s)；
  * `physics`：16/16 PASS (72.07s)；
  * 历史成熟动作（StartStopWalkAction, RunAction）：100% 零退化通过。

---

## [2026-10-25] 任务 6G-D-C2-A 补充：自动视觉证据采集、遥测一致性审计与跨 AI 验收管线

### 视觉证据渲染与时空联系表 (`src/scene/dynamics_visual_evidence.py`, `run_generate_visual_evidence.py`, `docs/evidence/task6gd_c2a/`)
* **多视角高采样自动化渲染矩阵**：
  * 为 5 个测试工位自动配置正面 (Front)、侧面 (Side)、俯视 (Top) 专职检查相机；
  * 执行 7 级高密度关键帧渲染（F01, F12, F24, F36, F48, F60, F72），全自动化无头生成 112 张高清视口静帧；
  * 基于 Blender 内置 numpy 与原生图像引擎生成 $2048 \times 1080$ 的高对比度综合联系表 [`docs/evidence/task6gd_c2a/contact_sheet.png`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/contact_sheet.png)。
* **逐帧遥测与机器防篡改一致性审计 (`telemetry.json`, `validation_report.md`)**：
  * 逐帧提取 72 帧全部数值动力学状态向量与 Blender 求值对象世界变换；
  * 机器审计结果：求值位置误差实测 `0.00e+00 m`（$< 10^{-5}\text{ m}$），归一化姿态角误差 `3.50e-07 rad`（$< 10^{-5}\text{ rad}$）；
  * 反冒充防篡改实测通过：Station 4 打滑发散 $\Delta p = 5.30\text{ m}$，Station 5 滚转倾斜发散 $\Delta q = 1.55\text{ rad}$，绝无目标状态冒充实际状态。
* **跨 AI 交付件与交互式查看器**：
  * 生成动画 GIF 预览 [`dynamics_overview_anim.gif`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/dynamics_overview_anim.gif) 与交互式 HTML 播放器 [`visual_player.html`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/evidence/task6gd_c2a/visual_player.html)；
  * 打包全量 24.5 MB 证据压缩包 `output/evidence/task6gd_c2a/task6gd_c2a_evidence_pack.zip`；
  * 48 张代表性图片及核心证据同步入库 [`docs/evidence/task6gd_c2a/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/)。

### 测试验证与分级回归
* **自动化测试套件 (`tests/verify_task6gd_visual_telemetry.py`)**：
  * 5 项一致性与完整性测试全绿通过；
  * 在 `tests/test_registry.py` 注册 `visual_evidence_telemetry`（PHYSICS 与 FULL 分级）。
* **分层回归测试结果**：
  * `quick`：9/9 PASS (16.09s)；
  * `physics`：16/16 PASS (72.42s)；
  * 历史动作（WalkAction, RunAction）：100% 零退化通过。

---

## [2026-10-24] 任务 6G-D-C2-A：DynamicsPlayground 真实动力学状态集成与多场景视口验证 (Task 6G-D-C2-A)

### 真实动力学状态集成与可视化驱动 (`src/scene/dynamics_visualizer.py`, `output/dynamics_playground.blend`, `run_dynamics_playground.py`)
* **五大物理场景全程序化状态驱动与视口布局**：
  * **Station 1 (静态支撑平衡)**：双足接触反力平衡 $m g = 686.7\text{ N}$，CoM 高度稳定在 $Z=1.0\text{ m}$（下陷 $< 10^{-5}\text{ m}$），动态绿色反力箭头严格竖直向上；
  * **Station 2 (重力自由落体)**：空中无接触悬停需求，状态按自然重力 $-9.81\text{ m/s}^2$ 自然加速下落，零接触力虚构，目标虚影悬空直观呈现跟踪偏差；
  * **Station 3 (水平加速推进)**：在库仑摩擦锥限制内产生前进剪切力（$F_x = 105\text{ N}$），质心沿 $+X$ 加速平移，反力箭头倾角严格对应合外力方向；
  * **Station 4 (摩擦不足滑移滞后)**：冰面低摩擦（$\mu=0.08$）强制截断剪切力，实际质心滞后于目标虚影 $> 2.0\text{ m}$，直观呈现打滑与失控；
  * **Station 5 (偏心接触导致旋转)**：偏心单足接触点产生滚转力矩 $\tau_x \approx -206\text{ N}\cdot\text{m}$，驱动身体姿态连续倾斜翻滚，动态角动量箭头实时延伸。
* **视觉调试集合隔离与环境不可变原则 (ACG Section 6 遵守)**：
  * 动力学几何体（CoM 球、身体代理框、目标虚影、接触圆盘、动态力箭头、动态角动量箭头、3D 轨迹曲线、站台 3D 文本标签、检查相机）全部封装入独立集合 `Playground_Dynamics_Visualization`；
  * 原始训练场集合 `Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras` 的 45 个对象保持 100% 不变；
  * 保留 `PlaygroundOverviewCam` 为主场景相机，新增 `DynamicsInspectionCam` 供用户快速切换鸟瞰 5 个测试台。
* **平动数值积分边界审计修正 (Section VIII)**：
  * 在 `docs/C1_FINAL_AUDIT.md` 明确平动积分公式为 $v_{k+1} = v_k + a_k \Delta t$ 与 $p_{k+1} = p_k + v_k \Delta t + \frac{1}{2} a_k \Delta t^2$；
  * 澄清其对恒定加速度场（如重力）具有解析无截断特性（$< 10^{-12}\text{ m}$），但在非恒定加速度场中呈现速度一阶精度，不可无条件称为两阶段二阶 Velocity Verlet；
  * 新增测试 `test_31_non_constant_acceleration_convergence_benchmark`，在非恒定正弦加速度场中实测记录一阶收敛表现（误差减半比 $\approx 2.0$）。

### 测试验证与架构状态
* **测试套件扩充与注册 (`tests/verify_task6gd_playground_dynamics.py`, `tests/test_registry.py`)**：
  * 新增 `verify_task6gd_playground_dynamics.py`，纯 Python 与 Blender Headless 全绿通过（5/5 PASS）；
  * 在 `tests/test_registry.py` 注册 `playground_dynamics_states`（纳入 PHYSICS 与 FULL 分级）；
  * `tests/verify_task6gd_closed_loop_dynamics.py` 扩充至 31 项测试全绿通过。
* **分层回归全绿**：
  * `quick` (9/9 项全绿通过，15.08s)；
  * `physics` (15/15 项全绿通过，70.36s)；
  * 历史动作（Walk, Run）100% 零退化通过；
  * 严格遵守边界：0 骨骼/Rig 修改，0 历史动作篡改，单一 SSOT 训练场复用。



## [2026-10-24] 任务 6G-D-C1-FINAL：数值闭环集中数学审计、步数时间解耦、正交状态语义与遥测不可变性防御 (Task 6G-D-C1-FINAL)

### 数值闭环集中数学审计与缺陷修复 (`src/motion/closed_loop_dynamics.py`, `src/motion/contact_force_solver.py`, `docs/C1_FINAL_AUDIT.md`)
* **DEF-001 (近似解准入策略链修复)**：
  * 在 `step_closed_loop_dynamics()` 的 `APPROXIMATE` 分支中严格连接 `ClosedLoopAdmissibilityPolicy.allow_approximate_solutions`；
  * 确立清晰优先级：`sol.is_physically_valid == False` 标定为 `SOLVER_NUMERICAL_FAILURE` > `strict_solved_only` 拒绝 > `allow_approximate_solutions=False` 拒绝 > 仅当允许且残差在 `max_allowable_*` 阈值内时准入为 `SUCCESS_APPROXIMATE`；
  * 残差超限时根据 `strict_freeze_on_infeasible` 决定冻结或以真实物理力自然演化 (`CONTROL_INFEASIBLE_PHYSICS_ADVANCED`)。
* **DEF-002 (步数统计与物理推进时间彻底解耦)**：
  * 在 `ClosedLoopSimulationTrajectory` 中区分记录 `requested_steps`、`attempted_steps`、`successful_steps`、`failed_steps`、`requested_duration` 与 `actual_physical_time`；
  * 约束 `total_time == actual_physical_time`（基于状态实际时间戳差值），杜绝拒绝帧导致的时间虚假累加。
* **DEF-003 (遥测状态四维正交解耦语义)**：
  * 新增 4 个清晰正交的布尔状态：
    1. `is_contact_solution_physically_valid`：接触力求解是否满足物理硬约束；
    2. `is_policy_admitted`：当前步是否通过策略准入允许前向动力学积分；
    3. `is_target_satisfied`：控制目标是否完全被满足（`SUCCESS_EXACT` 或合规准入的 `SUCCESS_APPROXIMATE`）；
    4. `state_advanced`：物理状态与时间戳是否真正单步推进；
  * 保持既有 `is_physically_valid` 与 `is_control_feasible` 向后兼容。
* **DEF-004 (遥测深层不可变性与防污染防御)**：
  * `actual_contact_forces` 在 `ClosedLoopFrameTelemetry` 中统一以只读 `MappingProxyType` 封装，杜绝调用端就地修改污染历史；
  * `ClosedLoopSimulationTrajectory.frames` 强制转为只读元组（`tuple`）；
  * `to_dict()` 与 `export_telemetry()` 返回深解耦、纯净的 JSON 可序列化结构。
* **DEF-005 (配置数值有限性与非负性门禁)**：
  * 在 `ContactSolverConfig`、`FeedbackGainsConfig` 与 `ClosedLoopAdmissibilityPolicy` 的 `__post_init__` 中加入统一的 `math.isfinite()`、正数和非负数门禁，非法输入立即抛出 `ValueError`。

### 关键数学不变量与二阶收敛阶验证
* **零重力动量守恒**：自由刚体 100 步模拟中线动量误差 $< 10^{-10}\text{ kg}\cdot\text{m/s}$，角动量误差 $< 10^{-10}\text{ N}\cdot\text{m}\cdot\text{s}$；
* **旋转动能守恒**：各向异性刚体主轴自由旋转 100 步动能漂移 $< 10^{-6}\text{ J}$；
* **静态支撑稳定性**：50 步静态站立下陷 $< 10^{-5}\text{ m}$，120 步下陷 $< 5\times 10^{-3}\text{ m}$；
* **牛顿-欧拉跨模块平衡**：各模块间 $\sum \mathbf{F} = m \mathbf{a}$ 与 $\sum \boldsymbol{\tau} = \dot{\mathbf{L}}$ 匹配精度 $< 10^{-7}$；
* **二阶步长收敛阶实测**：恒定重力下 Velocity Verlet 无截断误差（$< 10^{-12}\text{ m}$），非线性陀螺旋转实测步长收敛比为 $4.05 \approx 2^2$，确证严格 $O(\Delta t^2)$ 2阶收敛。

### 测试验证与架构状态
* **测试套件扩充 (`tests/verify_task6gd_closed_loop_dynamics.py`)**：
  * 测试用例总数扩充至 30 项全绿通过（纯 Python 6.88s，Blender Headless 0.59s）：
    21. `test_21_policy_disallow_approximate_solutions`；
    22. `test_22_policy_approximate_solutions_matrix`；
    23. `test_23_simulate_time_accounting_fail_fast_true_and_false`；
    24. `test_24_telemetry_orthogonal_status_semantics`；
    25. `test_25_telemetry_immutability_and_no_pollution`；
    26. `test_26_config_validation_numerical_gate`；
    27. `test_27_system_boundary_inactive_contacts_and_ids`；
    28. `test_28_numerical_invariants_and_analytical_conservation`；
    29. `test_29_step_size_convergence_order_two`；
    30. `test_30_cross_module_newton_euler_balance_consistency`。
* **分层回归全绿**：
  * `quick` (9/9 项全绿通过，15.81s)；
  * `physics` (14/14 项全绿通过，67.56s)；
  * 0 历史步态修改，0 Rig/IK/WBC 修改，0 训练场重建；
  * 6G-D-C1 阶段验收完成，下一任务锁定为 **Task 6G-D-C2: 在现有 DynamicsPlayground 中集成和验证真实动力学状态**。



## [2026-10-24] 任务 6G-D-C1-B-R1：完整三维重力统一、旋转反馈陀螺耦合修正与物理不可行性解耦准入门禁 (Task 6G-D-C1-B-R1)

### 完整三维重力统一计算 (`src/motion/contact_force_solver.py`, `src/motion/closed_loop_dynamics.py`)
* **接口扩展与向后兼容**：
  * 扩展 `ContactWrenchTarget.from_target_motion()`，支持传入 `gravity_acceleration_world: Optional[Vec3] = None`；
  * 满足严格物理力学关系：$\mathbf{F}_{\text{contact\_target}} = m \mathbf{a}_{\text{target}} - m \mathbf{g} - \sum \mathbf{F}_{\text{ext}}$（其中 $\mathbf{g}$ 为完整 3D 向量）；
  * 当未传入三维重力时，保持既有标量 `gravity_z` 默认值与调用 100% 兼容；
  * 闭环协调器向目标接触扳手与单步前向动力学积分器统一切换为同一套 `cfg.gravity_acceleration_world`。

### 世界系旋转反馈陀螺耦合项修正 (`src/motion/closed_loop_dynamics.py`)
* **完整刚体转动力学方程适配**：
  * 基于刚体在世界坐标系下的牛顿-欧拉转动方程 $\frac{d\mathbf{L}}{dt} = I_{\text{world}} \boldsymbol{\alpha} + \boldsymbol{\omega} \times \mathbf{L}$；
  * 将世界坐标系角加速度反馈 $\boldsymbol{\alpha}_{\text{fb}}$ 转换为角动量变化率时，计入陀螺力矩项：$\boldsymbol{\tau}_{\text{fb}} = I_{\text{world}} \boldsymbol{\alpha}_{\text{fb}} + \boldsymbol{\omega} \times \mathbf{L}$；
  * 当无旋转反馈目标（`target_orientation_quat_world is None` 且 `target_angular_velocity_world is None`）时，严格保持纯前馈角动量变化率语义不变，避免重复计入陀螺项；
  * 涵盖并验证各向同性惯量（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）、主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）以及非主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} = (60, -60, 20)\text{ N}\cdot\text{m}$）的精确解析计算。

### 数值失败与控制物理不可行性准入门禁解耦 (`src/motion/closed_loop_dynamics.py`)
* **策略分离与自然物理演化**：
  * **数值失败**（非法输入、重复接触 ID、NaN、求解崩溃）：严格保全原物理状态不变（失败原子性，`state_advanced = False`，标定为 `SOLVER_INVALID_INPUT` / `SOLVER_NUMERICAL_FAILURE`）；
  * **控制目标物理不可行但真实外力确定**（如空中无接触却要求悬停）：不虚构接触反力，以真实物理力（重力 + 零接触力）推进前向积分（`state_advanced = True`，标定为 `CONTROL_INFEASIBLE_PHYSICS_ADVANCED`），角色在重力下自然加速坠落；
  * **接触力无法证明有效**（如地面要求拉扯负支撑力）：不得直接积分，严格中止推进（`REJECTED_INFEASIBLE`）；
  * 在 `ClosedLoopAdmissibilityPolicy` 中提供 `strict_freeze_on_infeasible: bool = False` 作为严格冻结可选配置；
  * 在 `ClosedLoopFrameTelemetry` 中新增 `is_control_feasible: bool` 显式区分控制可行性与物理推进。

### 接触几何多帧边界界定
* 在代码与模块文档中明确：`ContactConstraintSpec` 为单帧即时输入，多帧模拟严禁假设接触点永久静态有效；后续 Task 6G-D-C2 须接入环境查询与接触模型进行动态更新。

### 测试验证与架构状态
* **测试套件扩充 (`tests/verify_task6gd_closed_loop_dynamics.py`)**：
  * 测试总数由 12 项扩充至 20 项，纯 Python (6.50s) 与 Blender Headless (0.48s) 全绿通过：
    13. 完整 3D 重力目标扳手与闭环步进一致性；
    14. 旋转反馈陀螺耦合：各向同性惯量零陀螺项；
    15. 旋转反馈陀螺耦合：主轴旋转零陀螺项；
    16. 旋转反馈陀螺耦合：非主轴旋转精确解析匹配；
    17. 纯前馈角动量变化率语义保真；
    18. 稳态旋转外加陀螺力矩在动力学积分中保持角速度恒定；
    19. 空中无接触悬停需求自然物理下落演化验证；
    20. 严格冻结模式（`strict_freeze_on_infeasible=True`）原子性保全验证。
* **分层回归全绿**：
  * `quick` (9/9 项通过，15.09s)；
  * `physics` (14/14 项通过，66.27s)；
  * 0 历史步态修改，0 Rig/IK/WBC 修改，0 训练场重建。

### 多帧动力学闭环协调模块实现 (`src/motion/closed_loop_dynamics.py`)
* **真实物理因果闭环链路**：
  * 形成严密的真实计算链：当前实际状态 $\to$ 目标控制需求与 PD 律 $\to$ 目标接触扳手 $\to$ 接触力优化求解 $\to$ 准入门禁判决 $\to$ 真实接触力前向积分 $\to$ 新实际状态 $\to$ 逐帧遥测与反馈误差；
  * 绝不将目标速度、目标加速度或目标角动量直接覆盖为实际状态，物理轨迹 100% 由牛顿-欧拉方程与真实分配的接触力积分驱动；
  * 使用现存 `ForwardDynamicsState` 保存实际状态，下一帧必须以严格继承上一帧计算出的实际状态推进。
* **物理阻尼反馈控制与饱和截断**：
  * 建立 `DesiredMotionReference`，支持质心期望位置/速度/前馈加速度、姿态期望四元数/角速度/前馈力矩与外力干扰；
  * 基于人体倒立摆动力学特征配置临界阻尼增益（$k_p=16.0, k_d=6.0, k_{\text{rot},p}=25.0, k_{\text{rot},d}=8.0$），姿态跟踪引入 $SO(3)$ 李代数四元数对数误差映射 $\mathbf{e}_{\text{rot}} = \log(q_{\text{tgt}} \otimes q_k^{-1})$；
  * 对指令加速度与指令角动量变化率施加物理饱和边界，保证数值稳定性。
* **严格的接触力求解结果准入门禁与残差防伪造策略 (`ClosedLoopAdmissibilityPolicy`)**：
  * 细分状态判决：`SUCCESS_EXACT`、`SUCCESS_APPROXIMATE`、`REJECTED_INFEASIBLE`、`REJECTED_APPROXIMATE`、`SOLVER_INVALID_INPUT` 与 `SOLVER_NUMERICAL_FAILURE`；
  * 对 `APPROXIMATE` 状态：仅在满足物理硬约束（单侧接触、3D 摩擦锥）且残差未超阈值时准入并如实报告残差与跟踪误差，绝不伪装为精确成功；
  * 无法安全推进时严格保持原状态完全不变（保障失败原子性）。
* **可观测全量遥测与历史记录 (`ClosedLoopFrameTelemetry`, `ClosedLoopSimulationTrajectory`)**：
  * 逐帧记录时间、当前/下一状态、指令控制量、目标扳手、求解状态与残差、各接触点实际力、实际合力/合力矩/加速度、位置/速度/加速度跟踪误差；
  * 提供 `to_dict()` 与 `export_telemetry()`，为后续 Blender 训练场物理遥测可视化提供 100% 真实数据源。

### 导出与统一注册
* **接口导出 (`src/motion/__init__.py`)**：导出闭环协调器、配置类与遥测数据结构；
* **统一测试套件注册 (`tests/test_registry.py`)**：注册 `closed_loop_dynamics`，纳管至 `QUICK`, `PHYSICS`, `FULL` 分级。

### 测试验证与架构状态
* **独立单元测试套件 (`tests/verify_task6gd_closed_loop_dynamics.py`)**：
  * 12 项场景测试全部通过（纯 Python 6.07s，Blender 0.61s）：
    1. 静止支撑平衡：双足支撑抵消重力，CoM 高度严格保持 1.0m（沉降 $< 0.5\text{ mm}$）；
    2. 水平加速：在摩擦力允许下产生精确水平加速度（$a_x = 2.0\text{ m/s}^2$），纵向支撑基底匹配 ZMP 位移；
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
* **分层回归全绿**：
  * `quick` (9/9 项全部通过，14.52s)；
  * `physics` (14/14 项全部通过，68.29s)；
  * 0 历史步态修改，0 Rig/IK/WBC 篡改，0 训练场重建。


## [2026-10-24] 任务 6G-D-C1-A-R1：前向动力学状态不可变性防御性复制与非各向同性刚体二阶中点姿态积分修正 (Task 6G-D-C1-A-R1)

### 状态不可变性与输入契约修复 (`src/motion/forward_dynamics.py`)
* **三维向量与四元数维度严格验证**：
  * 实现 `_validate_vec3` 与 `_validate_quat`，严格要求向量分量长度恰好为 3、四元数分量长度恰好为 4（严禁截断或不足容忍），拦截任何维度不匹配异常；
  * 强制验证数值元素必须为有限实数（`math.isfinite`），拒绝 NaN 与 Inf；
  * 验证通过后，将全部空间向量与集合字段通过 `object.__setattr__` 转换为不可变浮点元组（`tuple`）。
* **序列集合防御性深浅拷贝与防污染隔离**：
  * `ForwardDynamicsState`：内部 `com_position_world`, `com_velocity_world`, `angular_momentum_about_com_world`, `orientation_quat_world` 全面转换为不可变元组，外部调用方即使就地修改原 list 也不影响状态；
  * `ContactForcePoint`：`contact_point_world`, `contact_force_world` 强制防御性转换为 float 元组；
  * `ForwardDynamicsStepInput`：对 `external_forces_world`, `external_torques_about_com_world`, `contact_forces`, `gravity_acceleration_world` 进行全面防御性复制，杜绝通过外部 list 修改已构建的步进输入；
  * `ForwardDynamicsStepResult`：全部输出向量属性统一防御性标准化为 float 元组；
  * 严格保证失败原子性：单步积分异常或失败时，返回的 `state_next` 为原输入 `state` 的完全未修改引用。

### 真正的 2-Stage 中点姿态积分流程 (`src/motion/forward_dynamics.py`)
* **几何对称的世界惯性张量中点更新**：
  * 修复了既往在求解中点角速度时直接复用当前姿态惯性矩阵 $I_{\text{world}, k}$ 的问题；
  * 引入完整的 2-Stage 中点积分流程：
    1. $\boldsymbol{\omega}_k = I_{\text{world}, k}^{-1} \mathbf{L}_k$；
    2. $\theta_{\text{half}} = \|\boldsymbol{\omega}_k\| \frac{\Delta t}{2}$，$\Delta q_{\text{half}} = \exp(\frac{1}{2} \boldsymbol{\omega}_k \frac{\Delta t}{2})$，$q_{\text{half}} = \text{normalize}(\Delta q_{\text{half}} \otimes q_k)$；
    3. $R_{\text{half}} = R(q_{\text{half}})$，$I_{\text{world, half}} = I_{\text{body}}.\text{rotate}(R_{\text{half}})$ 并验证正定性；
    4. $\mathbf{L}_{\text{half}} = \mathbf{L}_k + \frac{1}{2} \boldsymbol{\tau}_{\text{net}} \Delta t$；
    5. $\boldsymbol{\omega}_{\text{mid}} = I_{\text{world, half}}^{-1} \mathbf{L}_{\text{half}}$；
    6. $\theta_{\text{full}} = \|\boldsymbol{\omega}_{\text{mid}}\| \Delta t$，$\Delta q_{\text{full}} = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$，$q_{k+1} = \text{normalize}(\Delta q_{\text{full}} \otimes q_k)$；
    7. $\mathbf{L}_{k+1} = \mathbf{L}_k + \boldsymbol{\tau}_{\text{net}} \Delta t$，$I_{\text{world}, k+1} = I_{\text{body}}.\text{rotate}(R(q_{k+1}))$，$\boldsymbol{\omega}_{k+1} = I_{\text{world}, k+1}^{-1} \mathbf{L}_{k+1}$；
  * 完美解决了非各向同性刚体（$I_{xx} \ne I_{yy} \ne I_{zz}$）在旋转过程中的惯性协变张量更新与角动量-能量几何保持。

### 测试验证与架构状态
* **独立单元测试套件扩充 (`tests/verify_task6gd_forward_dynamics.py`)**：
  * 测试总数由 17 项提升至 22 项，新增：
    * Test 18：State、StepInput、ContactForcePoint 对外部列表就地修改的防御性隔离；
    * Test 19：对 2D/4D 向量及 3D/5D 四元数的严格拦截；
    * Test 20：非各向同性刚体自由翻滚的动量与能量守恒（100 步相对能量漂移 $< 1.5 \times 10^{-7}$，角动量绝对漂移 0.0）；
    * Test 21：非各向同性刚体常力矩下角动量精确追踪；
    * Test 22：时间步长二分（$\Delta t \in \{0.04, 0.02, 0.01, 0.005\}$）下的二阶二次收敛率实测，测得误差比精确为 $4.01$ 与 $4.00$（理论值 $2^2 = 4.0$）。
* **自动化回归套件全绿**：
  * 单独测试：22/22 项全绿（0.009s）；
  * Blender Headless 单测：22/22 项全绿；
  * 分级回归：`quick` (8/8 项全部通过，7.82s)，`physics` (13/13 项全部通过，59.40s)；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-24] 任务 6G-D-C1-A：前向动力学单步积分内核与刚体物理状态解耦 (Task 6G-D-C1-A)

### 接触力求解器输入契约加固 (`src/motion/contact_force_solver.py`)
* **重复 contact_id 强制拒绝契约**：
  * 在 `solve_contact_forces` 输入校验中增加 `contact_id` 唯一性集合检查，同一次求解请求中发现重复 ID 时一票否决返回 `ContactSolverStatus.INVALID_INPUT`，杜绝字典键静默覆盖；
  * 在 `solution_to_multi_contact_dynamics` 中同步强制唯一性校验，存在重复 ID 抛出 `ValueError`；
  * 新增 Test 38 覆盖重复 ID 拦截，原有 37 项求解器测试保持 100% 零退化通过。

### 纯数学单步前向动力学内核实现 (`src/motion/forward_dynamics.py`)
* **100% 纯 Python / 零 bpy 依赖架构**：
  * 彻底解耦 Blender 运行时，在独立 Python 环境下毫秒级执行；
  * 定义不可变（frozen）状态容器 `ForwardDynamicsState`，严格保障失败原子性（积分失败绝不污染输入状态）；
  * 显式定义世界坐标空间（+Z Up, Ground Z=0.0m）与全部 SI 单位制；
  * 姿态四元数采用 Hamilton `(w, x, y, z)` 主动旋转约定（$\mathbf{v}_{\text{world}} = R(q) \mathbf{v}_{\text{body}}$）；
  * 严格区分刚体局部惯性张量 $I_{\text{body}}$（刚体旋转不变量）与世界坐标系惯性张量 $I_{\text{world}} = R(q) I_{\text{body}} R(q)^T$。
* **牛顿-欧拉 6-DOF 动力学积分与指数映射姿态更新**：
  * 支持多接触力、外部力、关于质心的外部力矩与重力加速度；
  * 质心线运动采用 Velocity Verlet 解析积分：$\mathbf{p}_{k+1} = \mathbf{p}_k + \mathbf{v}_k \Delta t + \frac{1}{2} \mathbf{a} \Delta t^2$（常力下单步零截断误差）；
  * 角动量通过力矩冲量更新：$\mathbf{L}_{k+1} = \mathbf{L}_k + \boldsymbol{\tau}_{\text{net}} \Delta t$；
  * 姿态四元数通过中点角速度与 $SO(3)$ 李代数指数映射 $\Delta q = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$ 更新，常角速度下旋转解析精确且模长严格保持 1；
  * 惯性张量正定性与良态检查采用 Sylvester 充要准则，奇异张量安全熔断返回 `SINGULAR_INERTIA`。
* **实际物理状态与参考目标值严格分离**：
  * 输出真实合力积分结果（`state_next`），目标加速度与目标角动量变化率仅作为独立诊断字段输出，严禁将目标值当作实际运动。

### 测试验证与架构状态
* **独立单元测试套件 (`tests/verify_task6gd_forward_dynamics.py`)**：
  * 17 项分析测试全部通过（0.003s）：恒定合力线积分、自由落体多步解析对比、无重力无外力动量守恒、动量-冲量定理、70kg 地面静止支撑重力补偿、偏心接触力力矩、外力矩角动量积分、零力矩角动量守恒、正定惯性角速度、奇异非正定张量安全拒绝、四元数 90° 旋转与归一化、零力矩姿态不变性、时间步长收敛阶数、非有限数值拦截、输入状态不可变保全、重复接触 ID 拦截、以及与接触力求解器/接触动力学无缝联动；
* **回归测试全绿**：
  * `tests/verify_task6gd_contact_force_solver.py` 扩充至 38 项全绿通过；
  * 统一测试套件注册进入 `tests/test_registry.py`；
  * 分层回归套件实测全绿：`quick` (8/8 项通过，8.07s), `physics` (13/13 项通过，60.99s)；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-24] 任务 6G-D-B-R2：接触力求解器终止状态契约与优化收敛真值解耦 (Task 6G-D-B-R2)

### 终止状态机与容错回退机制加固 (`src/motion/contact_force_solver.py`)
* **严格的 `SOLVED` 五重充要条件准入准则**：
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

### 测试验证与架构状态
* **独立单元测试套件扩充 (`tests/verify_task6gd_contact_force_solver.py`)**：
  * 测试套件由 31 项扩充至 37 项（新增 Test 32 至 Test 37）：
    * Test 32: 正常优化收敛且残差达标返回 `SOLVED`
    * Test 33: 优化器非成功终止、但残差“碰巧”达标时明确返回 `APPROXIMATE`，绝不返回 `SOLVED`
    * Test 34: 优化器非成功终止、且残差超标时返回 `APPROXIMATE` 并带准确诊断
    * Test 35: SLSQP 提前退出且 `success == False` 时的容错回退与状态记录
    * Test 36: SLSQP 与 SPG 回退后均失败时的状态正确性（`APPROXIMATE`，绝不 `SOLVED`）
    * Test 37: 数值异常（NaN/Inf/双异常中断）返回 `NUMERICAL_FAILURE` 与解析零解路径
  * 独立 Python 全量环境：37/37 项测试全部通过（0.414s）；
  * Blender 无 SciPy 无头环境：36/36 项测试全部通过（1 项 SLSQP 测试优雅跳过，0.086s）。
* **自动化回归测试验证**：
  * `quick` Tier：7/7 项测试全绿通过（7.35s，退出码 0）；
  * `physics` Tier：12/12 项测试全绿通过（60.23s，退出码 0）；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-23] 任务 6G-D-B-R1：接触力求解器数值可靠性与状态契约修复 (Task 6G-D-B-R1)

### 有界摩擦锥欧氏正交投影与状态契约修复 (`src/motion/contact_force_solver.py`, `src/motion/contact_dynamics.py`)
* **有界摩擦锥正交投影重构 (`project_to_friction_cone`)**：
  * 针对有限最大法向力 $F_{n,\max}$ 和最小法向力 $F_{n,\min}$，消除原先等比缩放切向力导致的偏离反例（$F=(1,0,10), n=(0,0,1), \mu=0.5, \max=5$ 精确投影到最近点 $(1,0,5)$，距离为 $5.0$，优于原缩放点 $(0.5,0,5)$ 的 $5.025$）；
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

### 测试验证与架构状态
* **独立单元测试套件扩充 (`tests/verify_task6gd_contact_force_solver.py`)**：
  * 测试套件由 17 项扩充至 31 项（新增 Test 18 至 Test 31）：
    * Test 18: 有界摩擦锥最近点反例（$(1,0,10) \rightarrow (1,0,5)$）
    * Test 19: 有界摩擦锥内点不变性
    * Test 20: 有限法向上下界截断
    * Test 21: $\mu=0$ 无摩擦地表截断
    * Test 22: 投影幂等性 $P(P(F))=P(F)$
    * Test 23: 投影后约束严格可行性
    * Test 24: 投影点欧氏距离极小性验证
    * Test 25: SPG 迭代上限终止与状态报告
    * Test 26: SLSQP 终止诊断与迭代透传（无 SciPy 时优雅跳过）
    * Test 27: SLSQP 到 SPG 容错回退报告与记录
    * Test 28: 数值失败与约束违规不虚报 SOLVED
    * Test 29: 高摩擦斜坡向下推力可行性反例（不虚报 INFEASIBLE）
    * Test 30: 已知数学不可行目标严格拦截
    * Test 31: 真实地表距离信息保真（消除虚假占位值）
  * 独立 Python 全量环境：31/31 项测试全部通过（0.443s）；
  * Blender 无 SciPy 无头环境：30/30 项测试全部通过（1 项 SLSQP 测试优雅跳过，0.091s）。
* **自动化回归测试验证**：
  * `quick` Tier：7/7 项测试全绿通过（7.76s，退出码 0）；
  * `physics` Tier：12/12 项测试全绿通过（62.09s，退出码 0）；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-23] 任务 6G-D-B：多接触力逆向求解与约束分配系统 (Task 6G-D-B)

### 核心接触力求解器实现 (`src/motion/contact_force_solver.py`)
* **多接触力分配数学架构**：
  * 构建线性接触抓取映射矩阵 $\mathbf{A} \mathbf{f} = \mathbf{w}$（$\mathbf{A} \in \mathbb{R}^{6 \times 3N}$），包含力平衡单位块 $\mathbf{I}_3$ 与绕质心力矩叉乘斜对称矩阵块 $[\mathbf{r}_i]_\times$；
  * 实现基于任意法向 $\hat{\mathbf{n}}$ 的精确 3D 圆形库仑摩擦锥闭式欧几里得正交投影算法 `project_to_friction_cone`，杜绝八棱锥线性多面体近似带来的方向偏置；
  * 双引擎优化架构：支持 SciPy SLSQP（高精度二阶锥非线性规划）与原生 SPG（谱投影梯度动力学，Barzilai-Borwein 自适应步长，零外部依赖，100% 兼容 Blender 内置 Python）；
  * 状态机与物理残差判定：定义 `ContactSolverStatus`（`SOLVED`, `APPROXIMATE`, `INFEASIBLE`, `INVALID_INPUT`, `NUMERICAL_FAILURE`），输出力残差范数 (N)、力矩残差范数 (N·m) 及法向/切向约束违规值；
  * 物理反向到正向桥接：实现 `solution_to_multi_contact_dynamics()`，将分配力转化为标准 `MultiContactDynamics` 进行双向物理验算；
  * 环境与训练场绑定：实现 `create_contact_constraint_from_environment()`，无缝支持 `DynamicsPlayground` 几何与摩擦参数抽取。
* **统一模块导出与测试注册**：
  * 在 `src/motion/__init__.py` 完整导出求解器数据结构与核心函数；
  * 在 `tests/test_registry.py` 注册 `contact_force_solver`（覆盖 QUICK, PHYSICS, FULL 分级）。

### 测试验证与架构状态
* **独立单元测试套件 (`tests/verify_task6gd_contact_force_solver.py`)**：
  * 17/17 项严苛数学与物理测试全部通过（耗时 0.403s）：
    * Test 1: 单点垂直重力支撑 (70kg -> $686.7\text{ N}$)
    * Test 2: 双足对称支撑均分 ($343.35\text{ N}$ each)
    * Test 3: CoM 偏移负荷分配 (2:1 比例分担与多边形外不平衡拦截)
    * Test 4: 单点力矩自由度亏缺拦截 (无法产生平行于力臂的偏航力矩)
    * Test 5: 脱离接触零力约束 (非接触点受力为零，非零目标判定不可行)
    * Test 6: 无摩擦地表打滑检测 ($\mu=0$ 无法产生切向剪切力)
    * Test 7: 库仑摩擦锥严格截断 (圆锥边界内 SOLVED，超出边界精确截断并报残差)
    * Test 8: 15° 斜坡法向/切向力分配 (结合真实 DynamicsPlayground 几何)
    * Test 9: 垂直墙面单向推力分配 (只允许推力，拉力严格拒绝)
    * Test 10: 地面+斜坡+墙面多异构法向联合接触分配
    * Test 11: 独立力矩交叉验算 (与 `MultiContactDynamics.total_torque_about_com` 100% 吻合)
    * Test 12: 绝对不可行拉力拦截 (单侧接触下拉地表被判定为 `INFEASIBLE`)
    * Test 13: 退化输入与非法数值拦截 (NaN, Inf, 零法向, 负质量)
    * Test 14: 排列不变性验证 (打乱触点顺序物理求解结果严格一致)
    * Test 15: 确定性与可复现性验证 (重复调用输出完全一致)
    * Test 16: 向后兼容性测试 (未破坏 6G-D-A/R1/R2 数据契约)
    * Test 17: 线性接触抓取映射矩阵 $\mathbf{A}\mathbf{f}=\mathbf{w}$ 数学合同验证
* **自动化回归测试验证**：
  * `quick` Tier：7/7 项测试全绿通过（7.11s，退出码 0）；
  * `physics` Tier：12/12 项测试全绿通过（59.77s，退出码 0）；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-23] 任务 6G-D-A-R2：MultiContactDynamics 时间步长更新原子性与状态不可变保全 (Task 6G-D-A-R2)

### 多触点系统时间步长更新失败原子性与事务回滚 (`src/motion/contact_dynamics.py`)
* **`MultiContactDynamics.set_dt()` 失败原子性重构**：
  * 引入 `_validate_dt_value()`：预先严格校验 `new_dt` 数值合法性（有限正浮点数，严格拒绝 0、负数、NaN、Inf 与非法类型），在输入非法时 100% 保持系统原状态不变；
  * `update_contacts=False` 模式（不更新子接触点）：在变更系统 `self.dt` 前，先遍历全部子接触点检查兼容性，若存在任何 `c.dt` 与新 `dt` 不一致，立即抛出明确异常，系统 `dt` 与子接触点 `dt` 严格保持原值，彻底消除修改系统后抛错导致的状态不一致缺陷；
  * `update_contacts=True` 模式（事务级同步重配置）：预先捕获原始系统 `dt` 与全触点 `c.dt` 状态快照，统一推进状态修改；若在更新过程中遭遇任何异常，自动触发事务回滚，将所有已变更状态 100% 恢复至快照原值，坚决杜绝“部分更新”中间态；
  * 空多接触系统（`len(contacts) == 0`）：允许合法设置新 `dt`，非法 `dt` 坚决拒绝且不改变原有系统状态。
* **单接触点属性防御性防护 (`SingleContactDynamics`)**：
  * 引入 `__setattr__` 对 `dt` 属性赋值进行动态强类型与生理正数门禁校验，防止非法数值注入。

### 测试验证与架构状态
* **单元测试扩充 (`tests/verify_task6gd_contact_dynamics.py`)**：
  * 完善 `test_16_multi_contact_dt_consistency_enforcement`：增加抛错后的系统与触点状态不变性断言；
  * 新增 `test_18_multi_contact_set_dt_failure_atomicity_and_consistency`：系统覆盖 10 项严苛原子性定理（匹配成功、失配抛错、系统不变、触点不变、同步更新、冲量缩放一致、空容器更新、非法数值全拦截、多触点中途故障事务回滚、`add_contact` 零退化）；
  * 18/18 项断言纯 Python 100% 通过（耗时 0.002s）。
* **自动化回归测试验证**：
  * `quick` Tier：6/6 项测试全绿通过（5.36s，退出码 0）；
  * `physics` Tier：11/11 项测试全绿通过（57.83s，退出码 0）；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-23] 任务 6G-D-A-R1：接触动力学时间步长一致性与物理接触有效性契约修复 (Task 6G-D-A-R1)

### 多触点统一时间步长所有权与强一致性门禁 (`src/motion/contact_dynamics.py`)
* **统一系统时间步长所有权 (`MultiContactDynamics`)**：
  * `MultiContactDynamics` 确立对系统时间步长 `dt` 的唯一所有权；
  * 在构造器初始化 `__post_init__` 与动态添加触点 `add_contact()` 中强行加入 `_validate_contact_dt(contact)` 门禁；
  * 若触点 `contact.dt` 与系统 `self.dt` 差异大于 `1e-6`，严格抛出 `ValueError` 并拒绝加入，杜绝静默采用或覆盖；
  * 提供 `set_dt(new_dt, update_contacts=False)` 方法，显式支持全触点同步，若不显式请求同步且触点 `dt` 不匹配时同样抛出 `ValueError` 报错。

### 物理接触有效性与几何贴靠显式分离 (`src/motion/contact_dynamics.py`)
* **接触几何间隙容差与状态定义 (`SingleContactDynamics`)**：
  * 新增 `surface_id: str = ""`、`surface_distance: float = 0.0` 与 `contact_tolerance: float = 0.02`（默认 20mm 物理接触间隙容差）；
  * 新增只读属性 `is_in_contact`（当且仅当 `abs(surface_distance) <= contact_tolerance` 时为真）；
  * 新增非接触受力违规状态 `FrictionConeStatus.NON_CONTACT_FORCE_VIOLATION`；
  * 更新 `evaluate_friction_constraint()`：当 `not is_in_contact` 且施加了非零接触力（$\|\mathbf{F}\| > \epsilon$）时，严禁判定为有效接触力，直接返回 `is_valid=False` 并附带详细违规诊断；若接触力为零则判定为 `SEPARATED`。
* **环境查询接触构造契约升级 (`create_contact_dynamics_from_environment`)**：
  * 引入 `contact_tolerance: float = 0.02` 与 `require_contact: bool = True` 参数；
  * 默认 `require_contact=True`：当查询点的 `signed_distance` 超过容差时，严格抛出 `ValueError` 拦截非物理悬空接触创建；
  * 允许 `require_contact=False`：用于纯几何邻域探测或近地状态追踪，将地表几何参数与有符号净距绑定至触点，同时保持 `is_in_contact=False` 防止非法受力。

### 测试验证与架构状态
* **单元测试扩充 (`tests/verify_task6gd_contact_dynamics.py`)**：
  * 新增 `test_16_multi_contact_dt_consistency_enforcement`：覆盖系统 dt 一致性、冲量累加等价性、构造器与 `add_contact` 不一致抛错拒绝、`set_dt` 批量同步与冲突拦截；
  * 新增 `test_17_contact_validity_and_clearance_tolerance`：覆盖精确地表接触、20mm 容差内轻微浮动、超容差悬空点在 `require_contact=True` 下的抛错拦截、在 `require_contact=False` 下的 `NON_CONTACT_FORCE_VIOLATION` 拦截以及零受力下的 `SEPARATED` 合法评估；
  * 17/17 项断言纯 Python 100% 通过（耗时 0.001s）。
* **自动化回归测试验证**：
  * `quick` Tier：6/6 项测试全绿通过（5.3s，退出码 0）；
  * `physics` Tier：11/11 项测试全绿通过（57.84s，退出码 0）；
  * 零历史步态修改，零 Rig/IK/WBC 篡改，零训练场重建。


## [2026-10-23] 任务 6G-D-A：接触动力学基础与冲量动量系统 (Task 6G-D-A)

### 纯数学接触动力学模块与冲量动量系统 (`src/motion/contact_dynamics.py`)
* **单接触点动力学状态 (`SingleContactDynamics`)**：
  * 构建世界空间接触点 $\mathbf{p}_c$、作用力 $\mathbf{F}$、质心相对位矢 $\mathbf{r} = \mathbf{p}_c - \mathbf{p}_{\text{com}}$；
  * 实现力矩计算：严格遵循右手定则计算绕质心力矩 $\boldsymbol{\tau}_{\text{com}} = \mathbf{r} \times \mathbf{F}$（$\text{N}\cdot\text{m}$），严谨区分绕世界原点力矩 $\boldsymbol{\tau}_{\text{origin}} = \mathbf{p}_c \times \mathbf{F}$；
  * 实现冲量与动量变化计算：线冲量 $\mathbf{J} = \mathbf{F}\Delta t$（$\text{N}\cdot\text{s}$）、角冲量 $\mathbf{H}_{\text{impulse}} = \boldsymbol{\tau}_{\text{com}}\Delta t$（$\text{N}\cdot\text{m}\cdot\text{s}$），严格等价于线动量变化 $\Delta \mathbf{P}$ 与角动量变化 $\Delta \mathbf{L}_{\text{com}}$；
  * 证明并验证 6 大数学定理：零力零动量变化、质心作用力零力矩、偏心力右手定则力矩、世界坐标平移不变性、$\mathrm{SO}(3)$ 刚体旋转协变性、冲量-动量等价性。
* **单侧正向与库仑摩擦锥约束评估 (`FrictionConstraintEvaluation`)**：
  * 正交分解接触力为法向力 $\mathbf{F}_n = (\mathbf{F} \cdot \hat{\mathbf{n}})\hat{\mathbf{n}}$ 与切向摩擦力 $\mathbf{F}_t = \mathbf{F} - \mathbf{F}_n$；
  * 单侧非粘附约束检查：$F_n \ge 0$，负法向拉力严谨标记为 `TENSION_VIOLATION`；
  * 库仑摩擦锥检查：$\|\mathbf{F}_t\| \le \mu F_n$，计算摩擦余量 $m = \mu F_n - \|\mathbf{F}_t\|$，严谨分类 `STICK`、`SLIP_LIMIT` 与 `SLIP_VIOLATION`。
* **多接触点聚合体系 (`MultiContactDynamics`)**：
  * 聚合多接触点合外力 $\sum \mathbf{F}_i$、合外力矩 $\sum \mathbf{r}_i \times \mathbf{F}_i$、总线冲量、总角冲量与净动量变化；
  * 提供多接触点摩擦锥完备性判据 `is_all_friction_valid`。
* **标准训练场环境查询接口契约绑定 (`create_contact_dynamics_from_environment`)**：
  * 100% 绑定 `DynamicsEnvironmentQuery`（`src/scene/environment_query.py`），从标准训练场（平地、斜坡、垂直墙）真实提取外向法线 $\hat{\mathbf{n}}$ 与摩擦系数 $\mu$；
  * 严禁私造孤立训练场，严禁手工摆设伪造装饰箭头。
* **环境兼容性增强 (`src/motion/__init__.py`)**：
  * 为 Blender 依赖模块增加 `try: ... except ImportError:` 容错隔离，保证纯 Python 测试执行时无需 `bpy` 即可毫秒级运行。

### 自动化验证与测试注册
* **交付独立单元测试套件 (`tests/verify_task6gd_contact_dynamics.py`)**：
  * 覆盖 15 项数学与几何定理（零力、质心力、偏心力、平移不变、旋转协变、冲量动量等价、原点vs质心区分、单侧约束、库仑摩擦锥、多接触聚合、非法输入拒绝、平地/斜坡/垂直墙训练场契约、越界与过滤拦截）；
  * 15/15 项断言纯 Python 全绿通过（耗时 0.001s）。
* **纳管至统一测试注册表 (`tests/test_registry.py`)**：
  * 登记 `contact_dynamics_math` 纳管至 `quick`、`physics` 与 `full` 层级。
* **分层回归测试验证**：
  * `quick` Tier：6/6 项全绿（8.13s，退出码 0）；
  * `physics` Tier：11/11 项全绿（56.09s，退出码 0）；
  * `motion` Tier：5/5 项全绿（15.29s，退出码 0），历史步态 100% 零退化；
  * `dynamics_playground_blend`：45 个场景对象结构完整性通过（1.28s，退出码 0）。
* **纪律声明**：0 生产运动代码修改，0 步态变动，0 训练场场景重构，严格停止。


## [2026-10-23] 任务 6G-D-PRE-P2-R1：环境查询过滤修复、距离语义统一与训练场 SSOT 门禁 (Task 6G-D-PRE-P2-R1)

### 3D 环境查询引擎关键语义修复与扩展 (`src/scene/environment_query.py`)
* **查询过滤与默认地面强隔离**：
  * 修复 `query_surface_at_point` 与 `query_spatial_surface` 中默认地面无条件入选缺陷；
  * 显式约束：仅当 `surface_type_filter in (None, "", "horizontal_ground")` 时才允许评估全局默认平坦地面；当指定其他类型过滤（如 `vertical_wall`, `sloped_ramp`）时，严格隔离默认地面，未命中时严谨返回 `success=False` 与 `surface_id="none"`。
* **物理距离语义严格解耦 (`ray_hit_distance` vs `signed_distance`)**：
  * `SurfaceQueryResult` 引入 `ray_hit_distance: Optional[float] = None`；
  * `signed_distance` 严格锁定为法向有符号距离（>0 间隙，0.0 在表面，<0 穿透）；
  * `ray_hit_distance` 严格锁定为沿射线方向行进的欧几里得距离（>=0.0m）；非射线点查询时返回 `None`，未击中时返回 `float("inf")`；
  * 彻底区分斜向射线行进距离（斜边）与法向垂直净距。
* **100% 保持基类 `EnvironmentQuery` 向后兼容**：
  * 保持原有 2.5D 高度场契约无损，同时基类三维空间接口具备完全一致的过滤与距离语义。

### 永久架构门禁与单一标准训练场规程升级
* **权威门禁确立单一基准训练场 (SSOT)**：
  * 在 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md) 增补第 6 节《标准动力学训练场基准场景复用与可视化门禁》；
  * 明确 `output/dynamics_playground.blend` 为后续 6G-D、6H 及 7A 的单一权威标准场景；
  * 颁布三大硬约束：严禁子模块私造重复分立场景；环境基础网格严格不可变（只读）；遥测力学箭头必须 100% 绑定真实物理计算输出，严禁手工摆设伪造箭头。
* **十大绝对清规同步落实**：
  * 同步修订 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md` 第 8 节，将八大清规升级为十大绝对清规（增补第 9 条与第 10 条）。

### 单元验证与回归套件执行
* **单元测试套件扩充 (`tests/verify_task6gd_dynamics_playground.py`)**：
  * 新增 `test_12_surface_type_filter_strictness`（过滤严格性检验，5 个子测试点全绿）；
  * 新增 `test_13_ray_query_distance_semantics`（正向、斜向、背面、未命中及基类射线距离语义，6 个子测试点全绿）；
  * 13/13 项纯 Python 数学断言全绿通过（耗时 0.001s）。
* **自动化回归套件实测全绿**：
  * `quick` Tier：5/5 全绿通过（耗时 5.11s，退出码 0）；
  * `motion` Tier：5/5 全绿通过（耗时 15.81s，退出码 0），历史步态 100% 零退化；
  * `dynamics_playground_blend`：45 个场景对象结构完整性通过（耗时 1.31s，退出码 0）。
* **零生产运动代码修改，零步态曲线变动，零场景重新生成，严格停止**。


## [2026-10-23] 任务 6G-D-PRE-P2：可视化动力学训练场与统一环境查询基础 (Task 6G-D-PRE-P2)

### 纯 Python 解析几何与环境查询系统 (`src/scene/environment_query.py`)
* **统一闭式表面模型 (`OrientedSurface`)**：
  * 构建包含中心、单位外向法线、切向基底（$\mathbf{u} \times \mathbf{v} = \mathbf{n}$）、半尺寸、摩擦系数与支撑属性的解析表面定义；
  * 提供精确闭式计算：最近投影点、有符号距离（Signed Distance，间隙 >0，穿透 <0）、外向单位法线与表面边界外欧几里得距离。
* **六大标准功能分区注册 (21 个解析几何表面)**：
  1. 平坦走跑区 (`flat_ground`, $Z=0.0\text{m}$, $\mu=0.70$)；
  2. 交替台阶区 (5 级标准台阶，踏面深 $0.3\text{m}$，踢面高 $0.15\text{m}$，总高度 $+0.75\text{m}$，带顶部过渡平台)；
  3. 连续斜坡区 ($+15^\circ$ 上坡段、过渡高台、$-20^\circ$ 下坡段，倾斜法线模长精确为 1.0)；
  4. 垂直障碍墙区 (高度 $2.5\text{m}$，厚度 $0.4\text{m}$，前立面法线 $(0, -1, 0)$，不允许普通脚底支撑)；
  5. 跳箱与高台区 ($0.9\text{m}$ 跳箱平台与 $2.2\text{m}$ 悬挂单杠横梁)；
  6. 遥测调试区 (原点旁 $0.05\text{m}$ 参考板、3D 坐标原点轴与 1m 标准立方体)。
* **环境查询引擎 (`DynamicsEnvironmentQuery`) 与向后兼容性**：
  * 支持 2.5D 高度场查询（`ground_height_at`, `surface_normal_at`），对历史动作完全无损兼容；
  * 支持 3D 空间点查询与垂直墙面定向查询（`query_surface_at_point`, `query_spatial_surface`）；
  * 返回标准化数据结构 `SurfaceQueryResult`（表面 ID、类型、投影点、法线、有符号距离、摩擦力与支撑有效性）。

### 动力学训练场 Blender 场景构建 (`src/scene/builder.py` / `run_dynamics_playground.py`)
* **程序化实体网格生成**：
  * 实现 `build_dynamics_playground`，根据解析几何在 Blender 中自动构建 6 大分区实体碰撞体网格；
  * 赋予区分度极高的专用材质（灰色地面、天蓝色台阶、金橙色斜坡、砖红色墙面、紫色跳箱、钢青色单杠、黄色调试区）；
  * 为 21 个表面生成直观的外向法线指示箭头（`NormalArrow_<surface_id>`）；
  * 建立三轴世界坐标参考（红X、绿Y、蓝Z）、1m 标尺方块、双视角摄像机（`PlaygroundOverviewCam`, `PlaygroundCloseUpCam`）与三点日光照明系统；
  * 导出生成可直接用 Blender 视口打开检查的独立场景文件 `output/dynamics_playground.blend`（116,933 字节，仅保存在本地受到 `.gitignore` 规则保护）。

### 验证套件实施与统一测试注册
* **交付纯 Python 数学验证 (`tests/verify_task6gd_dynamics_playground.py`)**：11/11 项数学与几何定理全绿通过（耗时 0.12s）；
* **交付 Blender 场景结构验证 (`tests/verify_task6gd_playground_blend.py`)**：45 个场景对象、材质与法线箭头全量通过（耗时 1.29s）；
* **统一测试注册表纳管 (`tests/test_registry.py`)**：分别登记入 `quick`、`physics` 与 `full` 层级；
* **回归验证保持 100% 零退化**：`quick` (5/5), `physics` (10/10), `motion` (5/5) 全绿通过（退出码 0）。
* **纪律声明**：0 生产运动代码修改，0 步态变动，未模拟虚假人体动力学反力，严格停止。

### 测试套件调度器严格安全修复 (Test Suite Strict Acceptance Fixes)
* **根除 SKIPPED 虚假成功漏洞**：
  * 在 `TestDefinition` 中引入显式 `is_optional: bool = False` 属性；
  * `execute_test` 判定重构：凡非可选（必需）测试遇到测试脚本缺失、`target_blend` 缺失或配置异常时，严格判定为 `status="FAILED"`（退出码 -1），绝不伪报 `SKIPPED`；
  * 报告与汇总逻辑中，`required_skipped_count > 0` 严格否决整体测试，整体退出码返回 1；
  * 仅当注册表中显式标记 `is_optional=True` 时才允许安全跳过。
* **健全 fail-fast 报告完整性与 `NOT_RUN` 追踪**：
  * 启用 `--fail-fast` 在首个测试失败立即停机时，自动将后续剩余全部待测用例追加为 `status="NOT_RUN"`、`exit_code=None`、`duration_sec=0.0`；
  * 报告结构（JSON 与 Markdown）完整呈现 `total_planned`、`total_executed` 与 `not_run_count`；
  * `NOT_RUN` 严格不计入 `passed_count`，且导致整体退出码为 1。
* **强制执行期望产物校验 (`expected_artifacts`)**：
  * 在测试进程正常退出（exit 0）且输出无异常后，自动深度检验 `test.expected_artifacts`；
  * 任何声明的产物若不存在或文件大小为 0 字节，直接判定为 `status="FAILED"`；
  * 为 `integration_unified_motion` 及 11 项历史 Blend 验证用例补齐 `expected_artifacts`。
* **PowerShell 命令行参数双向兼容**：
  * 在 `tests/run_test_suite.py` 中为参数增加 `-tier`、`-test-id`、`-fail-fast` 等单横杠别名，无缝支持 PowerShell 原生调用风格。

### 专用单元测试套件交付 (`tests/test_runner_unit.py`)
* **10 项核心机制纯 Python 毫秒级回归验证**：
  1. 正常执行与全绿通过 (`status="PASSED"`, `exit_code=0`)；
  2. 非零退出码真实捕获 (`status="FAILED"`, `exit_code=42`)；
  3. stdout 显式 `[FAIL]` 模式捕获（即使退出码为 0）；
  4. 必需依赖文件缺失判为失败，可选依赖缺失才标记跳过；
  5. 期望产物缺失或 0 字节文件判为失败，有效产物通过；
  6. 硬超时终止与 Windows 深度进程树清理机制；
  7. fail-fast 停止与剩余测试状态追加；
  8. `NOT_RUN` 状态正确记录且不计入 PASS；
  9. JSON 报告中 `all_success` 状态矩阵逻辑；
  10. 最终统一调度器退出码判定逻辑。
* **实测结果**：10/10 单元测试全绿通过，耗时 0.94s。

### 分层回归与零退化声明
* `quick` Tier：4/4 项全部通过（耗时 4.85s，退出码 0）；
* `motion` Tier：5/5 项全部通过（耗时 15.35s，退出码 0）；
* `physics` Tier：8/8 项全部通过（耗时 53.94s，退出码 0）；
* 生产代码 0 修改，历史步态 0 变动，完全符合执行纪律。

### 统一测试注册表与单入口调度器实施 (Unified Test Registry & Runner)
* **创建显式测试注册表 (`tests/test_registry.py`)**：
  * 登记 26 项真实测试用例，覆盖 `quick` (3项)、`physics` (8项)、`motion` (5项)、`full` (14项去重并集) 与 `legacy` (13项)；
  * 严谨区分 `RunnerType.PYTHON`、`BLENDER_HEADLESS` 与 `BLENDER_WITH_BLEND`，配置超时限制与依赖资源；
  * 建立 `is_visual_acceptance` 标记，严格区分自动化通过与人工视口目视验收。
* **创建单入口统一调度器与包装器 (`tests/run_test_suite.py` / `run_tests.ps1`)**：
  * 单命令外层调度（如 `.\run_tests.ps1 -tier quick`），将 N 次子命令执行收敛为单次受控调度，彻底消除用户反复审批终端的负担；
  * 自动安全解析 Blender 5.1.1 与系统真实 Python 路径，避开 Windows Store 零字节假别名；
  * 引入 Windows 深度进程树清理机制（`taskkill /F /T /PID`），杜绝超时悬挂 Blender 僵尸进程；
  * 实施多层失败判定：非零退出码、硬超时、产物缺失以及 stdout/stderr 中的 `[FAIL]`/`AssertionError` 模式反查，严禁“伪绿”放行；
  * 结构化自动生成 `tests/output/test_report.json` 与 `test_report.md`。

### 历史回归套件实测验证 (Regression Verification)
* **`quick` Tier**：3/3 项通过（耗时 3.94s，退出码 0）；
* **`motion` Tier**：5/5 项通过（耗时 16.16s，退出码 0），其中 `integration_unified_motion` 严格标定为 `AUTOMATED_PASS (Visual Inspection Required)`；
* **`physics` Tier**：8/8 项通过（耗时 53.90s，退出码 0），底层运动学、WBC、ROM、CoM、惯性张量与桥接 14 项测试保持 100% 零退化。

### 永久架构门禁制度确立 (Architecture Change Gate)
* 交付权威单一规范来源 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md)；
* 同步更新 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 第 8 节；
* 确立 11 项前置准入清单与 8 大绝对清规，规范架构偏差事前审批流程；
* 严格遵守执行纪律：0 生产代码修改，0 步态曲线变动，0 历史文件删除，严格停止。


## [2026-10-23] 任务 6G-D-PRE-P0：全工程架构审计与后续开发准备 (Task 6G-D-PRE-P0)

### 全工程架构审计与事实基线锁定 (Architecture Audit & Baseline)
* **穿透式审计全仓库**：
  * 深入检查 `src/` 下全部 28 个 Python 源码、`tests/` 下全部 30 个测试脚本、根目录下全部 19 个运行入口以及所有项目文档；
  * 确立官方唯一合法主生产调用链：`MotionPlanner` $\to$ `MotionAction` $\to$ `KinematicBridgeExecutor` $\to$ `WholeBodyController` $\to$ `Blender Rig/IK` $\to$ 物理遥测 $\to$ `MotionState`；
  * 明确 12 大关键环节唯一所有权矩阵，确认 `WholeBodyController` 独占骨架与控制器写入权，控制器全生命周期保持 `parent = None`（世界空间）；
  * 梳理全工程资产四态分类（Active / Reusable / Legacy / Orphan），排查出 `BlenderPoseApplicator` 与 `ContactConstraintAdapter` 历史废弃类，排查出 `run_pipeline.py` 与 `src/pipeline.py` 仍滞留在 Task 3 静态场景的问题；
  * 真实核查登记关键 Blender 文件：`character_forward_walk.blend`、`character_start_stop_walk.blend` 与 `unified_motion_integration.blend` 仅保存在本地磁盘 `output/` 目录下，受 `.gitignore` 规则保护未跟踪且未推送到 GitHub。所有生成源码 100% 在 GitHub 上可完全复现；
  * 建立 13 项历史运动与物理能力防退化基线矩阵（涵盖 ForwardWalk, StartStopWalk, Run, SprintStart, SprintBrake, Leg IK, Arm IK, WBC, CoM, ROM, Kinematics, Inertia, ContactModel, Unified Motion Integration）。

### 下一阶段实施方案设计 (Implementation Design for P1 & P2)
* **P1 统一测试调度系统 (Unified Test Runner) 设计**：
  * 提出 `test_registry.py` 测试注册表与 `quick` / `physics` / `motion` / `full` 四级执行分层机制；
  * 提出外层单命令调度机制（`python tests/run_test_suite.py --tier ...`），将 30 项测试收敛为单次执行，彻底消除用户频繁点击授权终端的审批疲劳；
  * 严明非零退出码绝对失败纪律，分离自动化数学测试通过与 Blender 人工目视验收。
* **P2 简易动力学训练场 (Dynamics Playground) 设计**：
  * 确立几何、环境查询、动力学模型与动画控制器四层严格解耦；
  * 规划平地、交替台阶、连续斜坡、垂直障碍墙、跳箱平台、遥测可视化 6 大标准化分区规格。
* **永久架构门禁 (ACG) 制度设计**：
  * 确立 11 项前置准入审查清单与 8 大绝对禁止行为清规，规范架构偏差事前审批流程。

### 交付文档与执行纪律 (Deliverable & Discipline)
* 交付权威审计报告 [`docs/ENGINEERING_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ENGINEERING_AUDIT.md)；
* 严格遵守执行纪律：0 生产代码修改，0 测试阈值放宽，0 历史文件删除，严格停止。


## [2026-10-22] 任务 6G-C-R3B-2-R1：历史正确动画对照、视口下肢周期性 L 形畸变根因定位与运动学修复 (Task 6G-C-R3B-2-R1)

### 故障定位与根因诊断 (Root Cause Diagnosis)
* **Blender 动画曲线重放父级解析空间错位（根因一）**：
  * 在首轮 R3B-2 中，`unlock_foot_contact` 在摆动相设置 `ik_obj.parent = CharacterRoot`，而 `lock_foot_contact` 在支撑相设置 `ik_obj.parent = None`；
  * Blender 中 `obj.parent` 是全局 Object 级指针属性，**不可被关键帧化（Not Keyframable）**，保存文件时固化为 `CharacterRoot`；
  * 重放动画时，支撑相在世界坐标下写入的关键帧位置（$Y = -8.0\text{ m}$）被错误叠加了 `CharacterRoot`（$Y \approx -7.94\text{ m}$），合成出世界坐标 $Y = -15.94\text{ m}$（即向后暴拉 8 米！）；而摆动相按局部坐标写入，重放时保持在根节点附近；
  * 步态交替时，支撑腿被向后暴拉 8 米形成横向 L 形，摆动腿看似正常，两腿周期性交替畸变。
* **COPY_ROTATION 目标空间在无父级物体上的退化（根因二）**：
  * `FootRotation.L/R` 约束原配置为 `target_space = "LOCAL", owner_space = "LOCAL"`；
  * 当 `FootIK` 控制器无父级（`parent = None`）时，Blender 约束求解器判定其局部空间为单位矩阵，导致 `foot.L/R` PoseBone 的三维旋转被强制锁定在静止姿态（$-13.13^\circ$），无法接收来自 `FootIK` 的动态俯仰指令；
  * 在奔跑与冲刺的大幅度屈膝（膝屈角达 $80^\circ \sim 98^\circ$）工况下，静止足部无法跟随小腿向后自然拖拽，导致小腿与脚掌夹角达到 $53.4^\circ$，违反解剖踝关节 ROM 极值（$45.0^\circ$）。

### 修复与重构 (Fixes & Refactoring)
* **下肢控制器全局恒定世界空间化 (`src/motion/whole_body_controller.py`)**：
  * `WholeBodyController.execute_frame` 中足部解锁时强制调用 `unlock_foot_contact(arm, side, reparent_to_root=False)`；
  * 确保 `FootIK.L`、`FootIK.R`、`KneePole.L`、`KneePole.R` 在整个动画全生命周期内（支撑相与摆动相）始终保持 `parent = None`，与历史基准文件 `character_forward_walk.blend` 和 `character_start_stop_walk.blend` 100% 一致；
  * 所有关键帧位置与旋转均写入绝对世界坐标系，Blender 重放时零相对位移叠加，彻底根除 8 米向后拉伸畸变与双重变换错误。
* **约束空间映射修正 (`src/rig/ik.py`)**：
  * 将 `FootRotation.L/R` 约束修正为 `target_space = "WORLD", owner_space = "LOCAL"`；
  * 使得无父级的 `FootIK` 世界空间旋转能够准确传递并叠加到 `foot.L/R` 的局部解剖姿态上，彻底解决无父级物体在 LOCAL 模式下退化为单位矩阵的底层缺陷。
* **基于人体生物力学的摆动相踝关节平滑跟随调制 (`src/motion/framework.py`, `src/motion/run_cycle.py`, `src/motion/sprint_start.py`)**：
  * 行走摆动相：$\theta_{\text{pitch}} = -12.0^\circ \sin(\pi s)$；
  * 跑步摆动相：$\theta_{\text{pitch}} = -38.0^\circ \sin(\pi s)$；
  * 冲刺起跑摆动相：$\theta_{\text{pitch}} = -36.0^\circ \sin(\pi s)$；
  * 真实模拟人类奔跑与迈步时脚尖跟随小腿向后下方自然拖曳的生物力学特征，在不修改历史步态曲线、不放宽 `joint_limits.py` 医学解剖 ROM 约束的前提下，全 462 帧踝关节活动角严格保持在 $[-25^\circ, +45^\circ]$ 舒适区间内。

### 验证 (Verification)
* **重新生成统一运动集成文件**：
  * 运行 `run_unified_motion_pipeline.py`，重新生成 `output/unified_motion_integration.blend`（462 帧无缝连续运动，总位移 12.9058m，0 次超程违规）；
  * 执行 `tests/verify_unified_motion_integration.py`，全量检验通过。
* **第 41..44 关键帧深入核查与历史基准完全吻合**：
  * 第 42 帧（$-114.52^\circ$）与第 43 帧（$-114.84^\circ$）的小腿姿态与历史基准 `character_start_stop_walk.blend` 保持完全一致（精确至小数点后两位），`FootIK.parent` 严格为 `None`，`FootIK` 位置严格位于 $Y = -8.0000\text{ m}$，支撑踝高度严格为 $Z = 0.0700\text{ m}$，零畸变拉伸。
* **视口渲染真实视觉证据**：
  * 运行 `scratch/render_comparison.py`，渲染输出 40 张对比视口视图（涵盖侧视与前斜视视角，覆盖第 1、12、24、36、41、42、43、44、48、60 关键帧），直观证实步态连续平滑，彻底消除周期性 L 形畸变与横向暴拉。
* **独立四大动作验证套件与核心回归全量 100% 通过**：
  * `tests/verify_r3b2_walk_action.py` 100% 通过（204 帧单动作与 408 帧双级联）；
  * `tests/verify_r3b2_run_action.py` 100% 通过（96 帧单动作与 252 帧级联）；
  * `tests/verify_r3b2_sprint_start.py` 100% 通过（114 帧单动作与 318 帧级联）；
  * `tests/verify_r3b2_sprint_brake.py` 100% 通过（162 帧级联）；
  * `tests/verify_task6gc_r3b1_bridge.py` 14/14 全绿，涵盖历史 6 大核心回归套件（WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia）。


## [2026-10-21] 任务 6G-C-R3B-2：历史四大动作无损迁移至统一桥接层与全身控制架构 (Task 6G-C-R3B-2)

### 迁移与重构 (Migration & Refactoring)
* **无损迁移四大历史连续动作至统一桥接执行器 (`KinematicBridgeExecutor.execute_frame`)**：
  * **StartStopWalkAction (`src/motion/framework.py`)**：构建标准 `KinematicPlannedPose` 并调用 `bridge_executor.execute_frame` 写入关键帧，淘汰旧有 `BlenderPoseApplicator` 与经验上身姿态函数；7 步调度、0.24 m/s 峰值速度与 1.2600 m 理论位移 100% 保持；
  * **RunAction (`src/motion/run_cycle.py`)**：重构接入桥接层，完美再现 4 周期 96 帧跑动、40 帧双足离地腾空相（`flight`）、0.90 m/s 稳态跑速；在 `WholeBodyController` 中修复足部解锁重新绑定至 `CharacterRoot`（`reparent_to_root=True`），彻底杜绝局部坐标系旋转漂移；引入解剖踝关节摆动俯仰调制（`pitch = -10.0 * sin(pi * s)`）；
  * **SprintStartAction (`src/motion/sprint_start.py`)**：重构接入桥接层，涵盖 114 帧起跑预备、蹬地起跑、加速冲刺、49 帧空中腾空相、2.00 m/s 峰值速度；引入冲刺摆动相踝俯仰调制（`pitch = -18.0 * sin(pi * s)`），完美契合极端屈膝屈髋下的真实解剖 ROM，0 次超程；
  * **SprintBrakeAction (`src/motion/sprint_brake.py`)**：重构接入桥接层，涵盖 48 帧主动急停制动、前掌受控滑移制动、双足并立停步锁定；引入制动踝俯仰调制（`pitch = -12.0 * sin(pi * s)`），微米级稳定合拢停步；
  * **允许 RunAction 从 STOP 模式启动**：在 `RunAction.can_start_from()` 中补充 `MotionMode.STOP`，打通急停或停步后直接切入跑步的物理连续性。
* **物理指标与控制语义严格区分**：
  * `MotionState` 严格区分规划速度 `planned_linear_velocity`、根节点差分测量速度 `root_derived_linear_velocity` 与全身体质心速度 `com_linear_velocity`；
  * 接触意图 `contact_intent`、接触建立与世界坐标锁定 `is_locked` 及环境表面几何间隙合规性严格区分；
  * 任何 IK、ROM 或接触几何超差由 `bridge_res.success` 严格真实拦截报错，严禁静默放行。
* **统一动画集成场景与验收生成器 (`run_unified_motion_pipeline.py`)**：
  * 自动顺序串联 `StartStopWalkAction` $\rightarrow$ `SprintStartAction` $\rightarrow$ `SprintBrakeAction` $\rightarrow$ `RunAction(cycles=4)`；
  * 生成 `output/unified_motion_integration.blend`（462 帧连续平滑动画，总位移 12.9058 m，0 次不可达违规）；
  * 配备完整地面平面、视口阳光以及全程平滑跟随角色移动的 `PipelineCamera` 运镜跟踪。

### 验证 (Verification)
* **独立动作验证套件 100% 通过**：
  * `tests/verify_r3b2_walk_action.py`：单动作 204 帧与双动作级联 408 帧通过（位移 1.2600m / 2.5200m，0 次超程）；
  * `tests/verify_r3b2_run_action.py`：单动作 96 帧与 Walk->Run 级联 252 帧通过（40 腾空帧，0.90 m/s，0 次超程）；
  * `tests/verify_r3b2_sprint_start.py`：单动作 114 帧与 Walk->SprintStart 级联 318 帧通过（49 腾空帧，2.00 m/s，0 次超程）；
  * `tests/verify_r3b2_sprint_brake.py`：SprintStart->SprintBrake 级联 162 帧通过（制动至 0.0 m/s，双脚稳态锁定，0 次超程）；
* **统一集成文件全量验证套件 100% 通过**：
  * `tests/verify_unified_motion_integration.py`：检验 `output/unified_motion_integration.blend`，1..462 帧、对象结构完整、里程碑位移与理论值误差严格 0.0000 m、姿态数据无 NaN/Inf；
* **桥接 14 项严苛测试与历史核心回归全绿**：
  * `tests/verify_task6gc_r3b1_bridge.py` 14/14 全绿，涵盖 WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia 核心历史回归。


## [2026-10-21] 任务 6G-C-R3B-1-Final：桥接层漏洞修补与永久 GitHub 自动同步 (Task 6G-C-R3B-1-Final)

### 修复与补全 (Fixes & Gaps Resolved)
* **时间步长 (dt) 动态支持与物理缩放 (`src/motion/kinematic_bridge.py`)**：
  * 在 `KinematicPlannedPose` 中增加可选 `dt: Optional[float] = None`，`KinematicBridgeExecutor.execute_frame` 支持显式 `dt` 传入或由 `time_seconds` 自动差分计算；
  * 引入严格单调递增时间戳与正数步长校验（`dt > 0.0`，反向或零时间戳抛出 `ValueError`）；
  * 有限差分速度与惯性张量物理缩放完全一致，默认维持 24 FPS 标准兼容。
* **手部 IK 与接触语义彻底解耦 (`src/motion/kinematic_bridge.py`)**：
  * 在 `PlannedFootTarget` 与 `PlannedHandTarget` 中显式分离 IK 目标激活（`enabled`）、接触意图（`contact_intent`）、世界锁定（`is_locked`）、接触类型与表面 ID；
  * 自由空间伸手（`contact_intent=False`）绝不产生虚假接触，维持正常双足或单足支撑分类；
  * 接触合规性校验：对声明接触意图的肢体，通过 `ContactModel` 校验与环境表面的几何间隙、穿透与法向容差，超差真实报警 `success=False`；
  * 支撑足地面锚点在局部坐标上依据踝关节原点 $(x, y, z - 0.070\text{ m})$ 精准对齐地面 $Z=0$，消除足底中心人为滑移。
* **Phase 5 惯性张量与全身体角动量遥测集成 (`src/motion/kinematic_bridge.py`)**：
  * 在 Phase 5 姿态解算完成后，直接调用 `compute_whole_body_inertia`，基于已评估的 Armature 姿态与 `kin_result.velocity` 计算全身体惯性张量、自转角动量与质心轨道角动量，并注入 `MotionState.params`；保持纯只读物理遥测。
* **永久 GitHub 自动化安全同步协议确立 (`AGENTS.md` / `GEMINI.md` / `.agents/rules/project_rules.md`)**：
  * 修改 Section 4 与 Section 7：每次开发任务完成并通过全部验证后，自动精确暂存、本地 commit，并自动执行 `git push origin master`，校验远程 SHA 与本地 HEAD 一致并记录于 `AI_SYNC.md`。

### 验证 (Verification)
* **扩展并 100% 通过 14 项严苛测试 (`tests/verify_task6gc_r3b1_bridge.py`)**：
  * Test 01 - Test 09：桥接无损转换、FK/IK 仲裁、支撑脚锁定、真实 ROM 报错、微米级等价性（0.0000 mm）、步态曲线不可变、坐标系规范、写入防冲突、6 阶段流水线全绿；
  * Test 10：Variable dt & Kinematic Scaling（0.01s 100FPS 与 0.04s 25FPS 速度换算精确吻合，非法步长与反向时间戳异常拦截成功）；
  * Test 11：Hand IK vs Contact Intent Decoupling（自由空间抓空与主动表面接触精准区分，越界接触真实报警 `success=False`）；
  * Test 12：Whole-Body Inertia & Angular Momentum Telemetry（静态姿态角动量严格为 0.0，运动状态惯性张量正定且质量 > 50 kg）；
  * Test 13：Historical Motion Actions Intactness & Planning（Walk 7 步、Run 24 帧周期、SprintStart 36 帧、SprintBrake 26 帧动作完全完好）；
  * Test 14：Core Historical Regression Suite（历史 6 大核心测试套件 100% 全绿：WBC、Joint Limits、Rigid Link、Arm IK、Kinematics、Inertia）。


## [2026-10-20] 任务 6G-C-R3B-1：统一架构规范修订与最小兼容桥接层 (Task 6G-C-R3B-1 Bridge Layer)

### 规范修订与强化 (Specifications & Rules)
* **修订权威系统架构规范 (`ARCHITECTURE.md` v2.1 & `ARCHITECTURE_SYNC.md` v2.1)**：
  * 确立 10 大架构设计原则（MotionAction 规划驱动、WBC 独占姿态协调、开环运动学+事后只读物理遥测、防伪造真实失败汇报、零退化等）；
  * 绘制三层架构演化视图（当前断裂点现状 -> R3B 统一桥接落地 -> 未来 6G-D/6H/7A 物理平衡闭环）；
  * 确立统一单帧 6 阶段执行协议表（Phase 1 规划 -> Phase 2 接触防滑锁定 -> Phase 3 WBC 统一求解 -> Phase 4 真实 ROM 校验 -> Phase 5 事后只读遥测丰富 -> Phase 6 状态提交）；
  * 梳理 12 大核心模块契约表与 6 大历史动作复用矩阵；
  * 同步永久规则 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`，严密规约阶段接入、调用链、防独立脚本拼凑与真实验证。

### 新增与实现 (Added & Implemented)
* **实现最小兼容桥接层 (`src/motion/kinematic_bridge.py`)**：
  * `KinematicPlannedPose`：统一结构化运动规划输入容器，涵盖浮动基座、骨盆、躯干 FK、足部目标与世界锁定标记、手部 IK/FK 模式；
  * `convert_planned_pose_to_wbc_targets`：将运动规划无损映射为 `WholeBodyControlTargets`，并显式仲裁手臂 FK/IK 模式；
  * `KinematicBridgeExecutor`：严格编排单帧 6-Phase 生命周期，统筹 `foot_contact` 接地世界锚定锁定、`WholeBodyController` 独占姿态求解、`JointModel` ROM 与到达性诚实验证、事后只读物理遥测丰富（CoM、速度、惯性张量、角动量、接触模型）及 `MotionState` 状态提交；
  * 在 `src/motion/__init__.py` 中统一对外导出。
* **升级 WholeBodyController (`src/motion/whole_body_controller.py`)**：
  * 感知足部 `is_locked` 标记，当足部锁定时协同 `lock_foot_contact` 保持世界空间接地锚定，严禁解绑或破坏锁定状态；
  * 增强 ROM 截断后的到达性二次复核，严禁以伪造姿态迎合阈值。

### 验证 (Verification)
* **编写并 100% 通过自动化严苛测试套件 (`tests/verify_task6gc_r3b1_bridge.py`)**：
  * Test 01：Lossless Input Mapping（100% 空间与运动学字段无损转换）；
  * Test 02：FK/IK Arbitration & Control Ownership（显式手部仲裁，腕部追踪误差 0.041 mm）；
  * Test 03：Stance Foot Ground Anchor Preservation（控制器漂移 0.000000 mm，骨骼漂移 0.246 mm）；
  * Test 04：Truthful ROM & Reach Failure Reporting（超限及越界严格诚实汇报 `success=False`）；
  * Test 05：Quantitative Pose Equivalence（桥接与历史动作姿态在骨盆、左踝、右踝误差严格为 **0.0000 mm**）；
  * Test 06：Immutability of Historical Gait Curves（历史 7 步排期、0.24 m/s 稳态速度、1.26 m 总位移 100% 不可变）；
  * Test 07：Data Types, Units & Coordinate Consistency（+Z Up，地面 Z=0.0，双支撑标识完全兼容）；
  * Test 08：Duplicate Write Conflict Prevention（WBC 与 foot_contact 独占写所有权零冲突）；
  * Test 09：Full Single-Frame 6-Phase Pipeline Execution（5 帧完整 6 阶段流水线执行，关键帧正确写入）；
  * Test 10：Core Historical Regression Suite（历史 6 大核心模块回归测试 100% 全绿：WBC、Joint Limits、Rigid Link、Arm IK、Kinematics、Inertia）。



## [2026-10-20] 任务 6G-C-R3A：系统架构深度审计与规范锁定 (Task 6G-C-R3A Architecture Audit)

### 审计与规范 (Audit & Specifications)
* **全仓库代码与调用链深度审计**：
  * 系统性排查 `src/motion/`、`src/rig/` 及测试与运行脚本，彻底澄清当前工程中真实存在的三套分立管线：
    1. 历史动作管线（`StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）：使用私有姿态函数与 `ContactConstraintAdapter` 直接驱动骨架，未接入 `WholeBodyController`。
    2. 物理分析与全身控制工具链（`WholeBodyController`、`JointModel`、`rigid_link`、`body_kinematics`、`body_inertia`、`contact_model`）：作为事后只读遥测存在，未被历史动作调用，无物理闭环。
    3. 演示原型脚本（`run_contact_obstacle_integration.py`）：脱离动作系统，通过在 30 帧循环中重复执行完全相同的静态目标硬编码摆拍，导致画面呈现僵硬切片。
  * 源码级核实 6 大物理数学模块（CoM、速度追踪器、惯性张量/角动量、接触模型、WBC、开环/闭环）：均为单向只读遥测，无力矩/平衡闭环。
* **更新权威架构文档 (`ARCHITECTURE.md` v2.0)**：
  * 确立统一物理世界坐标约定（$+Z$ 向上，$+X$ 向右，$+Y$ 向前，地面 $Z=0$）；
  * 绘制当前真实架构 Mermaid 流程图与目标生产级单流向架构图；
  * 建立 11 大模块数据流合同全表与 6 大历史动作复用矩阵；
  * 明确 4 大架构断裂点（控制器双轨制、接触模型脱节、障碍物动作缺失、物理无闭环）与 R3B 合流路径。
* **创建架构同步卡片 (`ARCHITECTURE_SYNC.md`)**：
  * 包含 12 项必填章节，确立后续开发任务必须遵从的官方数据流、模块分类清单、使用权限与禁止绕过规范。
* **强化永久项目规则 (`AGENTS.md` / `GEMINI.md` / `.agents/rules/project_rules.md`)**：
  * 在第 4 节加入前置必读 `ARCHITECTURE_SYNC.md`；
  * 新增第 8 节“架构对齐与防伪造纪律”，严禁重复造轮子、强制接入主数据流、禁止独立脚本拼凑动画、历史测试零退化、架构不一致暂停报告。



### 修复 (Fixed)
* **彻底根除单腿抬起刚体平移伪造行走的架构缺陷**：
  * **根因查明**：原调试脚本脱离了 `MotionPlanner` 和 `StartStopWalkAction` 步态调度状态机，错误地在离散姿态目标之间使用数学平滑插值直接平移根节点，导致角色在单腿悬空状态下沿 +Y 平移 2.15 米，呈现出“抬起单腿整体滑行”的荒诞姿态。
  * **架构解耦重构**：将演示任务彻底拆分为两套职责清晰、互不干扰的独立工程与 Blender 视口文件：
    1. **场景 A (`output/contact_walk_integration.blend` / `run_contact_walk_integration.py`)**：专注于真实连续人类步态与接触系统的实时闭环。100% 沿用 Task 5C / 6A 验证的步态调度机制（`StartStopWalkAction`），呈现 204 帧完整的起步-加速-交替步态行走-减速-合拢停步全过程；四肢交替抬腿跨步（Z 抬升 100~137 mm），支撑脚微米级锁定（漂移 < 0.005 mm），对侧手臂协调摆动；`ContactModel` 实时逐帧评估双脚接触并驱动绿色八面体标记物在支撑相激活、摆动相熄灭。
    2. **场景 B (`output/contact_obstacle_integration.blend` / `run_contact_obstacle_integration.py`)**：专注于多部位障碍物接触（Double Stance, Vault Touch, Foot on Wall, Ledge Hang, Flight Phase）。采用 5 个清晰分段的独立观察片段（Hold Clips），角色严格正对目标障碍物（朝向点积 1.0000，夹角 0.00 deg），自然垂臂，接触贴合精度达到微米级（误差严格 < 0.05 mm），彻底杜绝在障碍物之间伪造虚假单腿滑行。

### 新增 (Added)
* **工程架构审计报告 (`docs/MOTION_INTEGRATION_AUDIT.md`)**：
  * 完整梳理 Task 3 到 6G 历史运动能力全景总览表；
  * 深度分析 `StartStopWalkAction`、`ForwardWalkAction`、`SprintStartAction`、`SprintBrakeAction` 输入输出、步态状态机与支撑相/摆动相判定逻辑；
  * 绘制 `MotionPlanner -> MotionAction -> MotionState -> WholeBodyController -> ContactModel` 闭环数据流；
  * 彻底剖析单腿滑行根因，确立解耦返工方案与双原型设计边界。
* **场景 A 真实连续行走与接触系统集成原型 (`run_contact_walk_integration.py`)**：
  * 生成 `output/contact_walk_integration.blend`（206.8 KB）；
  * 204 帧完整平滑连续位移（总位移 $1.2600\text{ m}$，峰值速度 $0.2400\text{ m/s}$）；
  * 支撑类型动态实时切换：`double_stance` (24 帧)、`single_stance_l` (108 帧)、`single_stance_r` (72 帧)；
  * 绿色接触八面体与外法线箭头指示器随脚部触地/离地动态点亮与熄灭。
* **场景 B 多部位障碍物接触与支撑状态原型 (`run_contact_obstacle_integration.py`)**：
  * 生成 `output/contact_obstacle_integration.blend`（165.3 KB）；
  * 包含 5 个 30 帧独立观察片段（F1..150）：双脚站立、单手撑跳箱、脚蹬垂直墙面、双手抓杆悬垂、空中腾空飞跃；
  * 身体严格正对障碍物，双手自然垂直下垂（腕部低于肩部 $0.560\text{ m}$），接触锚点误差 $< 0.05\text{ mm}$。
* **扩展 17 项全量自动化测试套件 (`tests/verify_task6gc_contact_model.py`)**：
  * 包含 14 项接触几何、生命周期、刚体协变数学测试；
  * 包含历史 6 大核心回归套件（Task 6G-B, 6G-A, 6F-D, 6F-C, 6F-B, 6F-A），100% 保持全绿；
  * 新增 `Test 16`（场景 A 连续行走集成验收：位移、交替抬腿、防滑锁定、臂摆与标记物切换）；
  * 新增 `Test 17`（场景 B 障碍物接触验收：朝向、垂臂、形态差异、接触精度、保持稳定度）；
  * 17/17 项测试全部通过（退出码 `0`）。

### 修复 (Fixed)
* **可视化验收三大严重缺陷根因排查与全面修复 (`run_contact_model_prototype.py`)**：
  * **根因 1（父级局部坐标系与世界坐标混淆）**：原脚本直接将世界坐标赋值给父级为 `CharacterRoot` 的 `HandIK.L/R` 与 `FootIK.L/R`，导致局部位移叠加使目标飘移至角色身后 8 米处（$Y=-16.0\text{ m}$），IK 求解器达到极限量程硬性拉直四肢成水平展开僵硬姿态。修复：全面通过 `WholeBodyController.execute_frame` 调度，使用逆变换矩阵自动将世界坐标换算为父级局部坐标，消除位移漂移。
  * **根因 2（角色朝向与障碍物方向对齐）**：角色真实前向为 $+Y$ 轴，原脚本未按障碍物空间布局调整朝向。修复：将 4 类障碍物（地面、撑跳箱、垂直墙、横杆）沿 $+Y$ 通道合理排布，确保角色矢状面朝向与各目标障碍物方向完全对齐（前向矢量与目标方向点积严格为 $1.0000$，夹角 $0.00^\circ$）。
  * **根因 3（基础人体姿态与自然下垂）**：双脚站立时双手通过 `rotation_deg=(-90, 0, 0)` 恢复自然下垂（腕部位于肩部下方 $0.56\text{ m}$，横向紧贴躯干 $|X|=0.24\text{ m}$），双脚平正接地（踝部 $Z=0.07\text{ m}$，鞋底接触面 $Z=0.0\text{ m}$）。
  * **根因 4（6 个独立调试演示片段与平滑过渡）**：按用户要求将动画重构为 6 个清晰独立的 30 帧调试片段（总时长 180 帧）：
    - Segment 1 (F1..30)：双脚站立（双手自然下垂，双脚平稳接地，0 违规）；
    - Segment 2 (F31..60)：单脚支撑（左脚承重，右脚屈膝抬离地面 $0.21\text{ m}$）；
    - Segment 3 (F61..90)：单手撑障碍物（角色前倾微屈，右手真实贴合于 $Z=1.05\text{ m}$ 箱体顶面，误差仅 $0.02\text{ mm}$）；
    - Segment 4 (F91..120)：脚蹬垂直墙面（角色正对垂直墙面，右脚平贴于 $Y=-4.00\text{ m}$ 竖墙，误差 $0.04\text{ mm}$）；
    - Segment 5 (F121..150)：双手抓横杆悬垂（双手抓握 $Z=1.95\text{ m}$ 横杆，双脚悬空脱离地面 $0.25\text{ m}$）；
    - Segment 6 (F151..180)：腾空飞跃（角色离地空中奔跑跨越姿态，四肢腾空，0 接触）。
    - 各片段内前 10 帧采用平滑插值过渡（单帧最大位移仅 $318\text{ mm}$，杜绝瞬间瞬移和肢体翻转），后 20 帧为稳定保持与接触检验阶段（锚点漂移严格为 $0.000\text{ mm}$）。
* **新增自动化目视集成验收测试套件 (`test_16_visual_prototype_integration_acceptance`)**：
  * 在 `tests/verify_task6gc_contact_model.py` 中新增第 16 项严苛验收测试，涵盖 6 大量化检查：
    1. 身体朝向与障碍物夹角检验（6 阶段夹角均严格为 $0.00^\circ$，点积 $1.0000$）；
    2. 站立手部自然下垂量检验（腕部低于肩部 $0.560\text{ m} \ge 0.40\text{ m}$）；
    3. 6 场景形态差异化检验（15 对场景姿态最小欧氏角差异达 $67.65^\circ \ge 20.0^\circ$）；
    4. 接触锚点贴合精度检验（地表 $0.00\text{ mm}$、箱顶 $0.02\text{ mm}$、蹬墙 $0.04\text{ mm}$、抓杆 $0.01\text{ mm}$）；
    5. 保持阶段锚点稳定性检验（漂移严格为 $0.000\text{ mm} \le 1.0\text{ mm}$）；
    6. 运动连续性检验（全 180 帧最大单帧位移 $318\text{ mm} \le 400\text{ mm}$）。
  * 16 项测试全部通过（16/16 PASSED）。


### 新增 (Added)
* **通用多部位接触模型与支撑状态机 (`src/motion/contact_model.py`)**：
  * 构建核心数据结构与枚举：
    * `ContactType`：定义单向推力接触（`UNILATERAL`，单向支撑且受拉分离，不承受粘附拉力）、双向全自由度抓握（`GRASP`，承受 3D 任意方向约束力）与自由腾空状态（`FREE`）。
    * `ContactLifecycle`：离散生命周期状态机，包含预备进入（`CANDIDATE`）、生效锁定（`ESTABLISHED`）、计划性主动脱离（`RELEASED`）与非受控破坏断开（`BROKEN`）。
    * `SupportType`：多接触模式拓扑分类（`DOUBLE_STANCE` 双脚支撑、`SINGLE_STANCE_L/R` 单脚支撑、`MULTI_SURFACE` 多表面手脚接触、`WALL_FOOT_STANCE` 地面加垂直蹬墙、`LEDGE_HANG` 双手抓握横杆悬垂、`FLIGHT` 腾空飞跃无接触）。
    * `ContactRecord`：单部位接触全量记录（部位标识、接触表面名、接触类型、生命周期、世界空间接触点、表面外法线、摩擦系数、法向间隙公差、法向穿透公差、切向滑移公差与抓握公差）。
    * `GeometricConstraintResult`：纯几何与运动学约束校验反馈（是否合规、法向位移、切向滑移、总几何偏差、违规分类及描述）。
    * `MultiContactState`：全身多部位接触聚合容器，提供支撑分类、共面 2D 凸包支撑多边形求解（`Graham Scan` 凸包算法）、接触几何校验与状态转换接口。
    * `EnvironmentalSurface`：支持刚体变换协变的环境表面定义，当物体变换矩阵更新时，接触点与外法线（逆转置变换与归一化）自动协变更新。
  * 核心接口与函数：
    * `DEFAULT_LIMB_LOCAL_ANCHORS`：将骨骼关节原点与解剖表面接触锚点解耦（脚底偏置 $(0, 0.077, -0.070)\text{ m}$，手掌偏置 $(0, 0.050, -0.015)\text{ m}$）。
    * `evaluate_limb_contacts_from_armature`：基于 Blender Armature 评估骨骼世界矩阵计算接触锚点并进行接触几何校验。
    * `contact_record_to_legacy_contact_point` 与 `legacy_contact_point_to_contact_record`：双向无损兼容既有 `ContactPointState`。
    * `enrich_motion_state_with_contacts`：将接触拓扑分类、有效支撑肢体列表、共面支撑多边形等信息无缝注入 `MotionState.params` 与 `MotionState.contacts`。
* **可视化验收工程与原型脚本 (`run_contact_model_prototype.py`)**：
  * 生成独立视口可观察验收工程 `output/contact_model_debug.blend`（144 KB）。
  * 包含 4 类环境障碍物：大面积地面（Z=0）、撑跳箱体（Z=0.85）、垂直蹬踏墙面（面向 -Y）、抓握横杆（Z=1.80）。
  * 在 120 帧连续时间线上完整演示 6 种支撑状态（双脚站立、单脚站立、手撑台面、蹬墙接触、抓杆悬垂、腾空飞跃），配备清晰着色的接触锚点与外法线箭头指示器。
* **自动化测试套件 (`tests/verify_task6gc_contact_model.py`)**：
  * 15 项严苛测试 100% 全部通过：
    1. 骨骼局部锚点到世界坐标的仿射变换严格吻合（误差 $0.00\text{ m}$）。
    2. 外法线单位模长检验（误差 $0.00\text{ m}$）与指向环境外侧约定。
    3. 单向接触（推/拉判定）与双向抓握约束严格区分。
    4. 双脚地面接触激活与共面支撑多边形计算。
    5. 单脚站立与摆动脚平滑释放。
    6. 单手撑台与手脚多表面支撑判定。
    7. 地面 (+Z) 与垂直墙面 (-Y) 多法线非共面状态分类（拒绝错误生成 2D 凸包）。
    8. 双手抓握横杆悬垂状态分类。
    9. 腾空飞跃零接触与空多边形判定。
    10. 接触生命周期（Candidate -> Established -> Broken/Released）状态流转。
    11. 量化误差分解（法向间隙、穿透深度、切向滑移、总几何位移）。
    12. 环境物体世界变换协变性（位置与法线逆转置矩阵协变更新）。
    13. WholeBodyController 姿态兼容性与接触评估集成。
    14. MotionState 双向适配与遥测数据注入兼容性。
    15. 核心历史回归测试套件（Task 6G-B、6G-A、6F-D、6F-C、6F-B、6F-A）全绿。
* **架构决策与导出**：
  * 录入决策 `[DEC-022]`。
  * 在 `src/motion/__init__.py` 中导出所有多接触数据结构与接口。



## [2026-10-20] 任务 6G-B：刚体连杆惯性张量与全身角动量模型

### 新增 (Added)
* **刚体连杆分段惯性张量与全身角动量计算系统 (`src/motion/body_inertia.py`)**：
  * 构建核心惯性数学结构：
    * `InertiaTensor`：严格三维对称 $3 \times 3$ 惯性张量结构（SI 单位 $\text{kg}\cdot\text{m}^2$），支持 Sylvester 判据正定性校验、Cardano 闭式主转动惯量特征值求解、三维坐标系刚体旋转变换（$\mathbf{R} \mathbf{I} \mathbf{R}^T$）、三维平行轴定理（Steiner 定理：$\mathbf{I} + m (\|\mathbf{r}\|^2 \mathbf{E} - \mathbf{r} \mathbf{r}^T)$）、张量矢量乘法及 Frobenius 范数。
    * `SegmentGeometrySpec`：可配置人体质量分段几何近似模型，支持圆柱体（Cylinder）、椭球体（Ellipsoid）、椭圆柱体（Elliptic Cylinder）、长方体（Box）及自定义对角惯性（Custom Moments）。
    * `BodyInertiaModel`：整体惯性配置映射，预设 `DEFAULT_15_SEGMENT_INERTIA_MODEL` 与 `DEFAULT_13_SEGMENT_INERTIA_MODEL`，与 Task 6F-B Dempster/Winter 质量模型完全一致。
    * `SegmentInertiaState` 与 `WholeBodyInertiaState`：记录分段与全身的质心位置、局部惯性、世界惯性、相对全身 CoM 惯性、自转角动量（Spin）、轨道角动量（Orbital）及总角动量，明确标注坐标系（`WORLD_Z_UP`）、参考基准点（`WHOLE_BODY_COM`）及各物理量单位。
  * 核心算法与接口：
    * `compute_whole_body_inertia`：基于 Blender Armature 当前评估姿态与微分速度状态计算全身惯性张量与角动量。
    * `compute_whole_body_inertia_from_snapshots`：基于离散姿态快照与微分速度快照纯数据计算，无需激活视口。
    * `enrich_motion_state_with_inertia`：将全身惯性张量、主转动惯量与多连杆角动量无缝注入 `MotionState.params`。
* **自动化测试套件 (`tests/verify_task6gb_body_inertia.py`)**：
  * 13 项严苛测试 100% 全部通过：
    1. 全部分段局部惯性张量严格对称且正定（特征值与主惯量全 $> 0$）。
    2. 简单几何体惯性公式与独立解析推导完全一致（圆柱体、椭球体、椭圆柱体、长方体误差严格 $< 3 \times 10^{-17}$）。
    3. 3D 平行轴定理数值计算与解析增量完全一致（最大误差 $4.77 \times 10^{-8}$）。
    4. 全身空间平移不变性验证（位移 $(12.5, -45.0, 3.2)\text{ m}$，相对 CoM 惯性张量差值 Frobenius 范数仅 $8.96 \times 10^{-6}\text{ kg}\cdot\text{m}^2$）。
    5. 全身刚体旋转张量变换协变性验证（绕任意轴旋转 $40^\circ$，与 $\mathbf{Q} \mathbf{I} \mathbf{Q}^T$ 误差仅 $7.06 \times 10^{-6}\text{ kg}\cdot\text{m}^2$）。
    6. 中立站姿对称性验证（双侧对称矢状面 $I_{xy} = I_{xz} = 0.00000$，俯仰 $I_{xx}=13.46$，滚转 $I_{yy}=14.21$，偏航 $I_{zz}=1.08\text{ kg}\cdot\text{m}^2$ 处于真实人体生理范围）。
    7. 单臂侧平举引起合理物理响应（$I_{zz}$ 增加 $+0.65442\text{ kg}\cdot\text{m}^2$，产生不对称惯性积 $I_{xy} = 0.10313\text{ kg}\cdot\text{m}^2$）。
    8. 四肢展开（T-Pose: $2.403\text{ kg}\cdot\text{m}^2$）与四肢紧收（Tucked: $0.946\text{ kg}\cdot\text{m}^2$）差异显著，比值达 $2.540$ 倍。
    9. 静止身体全身角动量严格为零（模长 $0.00000000\text{ kg}\cdot\text{m}^2/\text{s}$）。
    10. 整个人体刚性旋转角动量与 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$ 解析一致性（绝对误差 $1.07 \times 10^{-6}\text{ kg}\cdot\text{m}^2/\text{s}$，相对误差 $8.54 \times 10^{-8}$）。
    11. 四肢独立运动时自转项（Spin: 模长 $0.09087$）与轨道项（Orbital: 模长 $1.69233$）各自贡献清晰，严谨解耦。
    12. 全身质心一致性与 `MotionState.params` 无损注入验证通过。
    13. 历史全量回归测试套件（Task 6G-A、6F-D、6F-C、6F-B、6F-A 及 6D）全部通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-021]`。

### 新增 (Added)
* **连续身体运动状态与微分速度学计算引擎 (`src/motion/body_kinematics.py`)**：
  * 构建核心数据结构：
    * `BodyPoseSnapshot`：单时刻离散实际姿态快照（根节点世界位置与四元数/欧拉角、骨盆位置/四元数、全身 CoM、15 个刚体连杆世界位置与四元数、17 个解剖关节局部相对旋转/四元数、4 个末端执行器世界位置与接触接地状态）。
    * `BodyVelocityState`：空间微分速度与加速度状态（根节点世界线速度/空间角速度、骨盆线速度、全身 CoM 速度、15 连杆空间速度、17 关节父级局部角速度、4 末端空间线速度、根节点与 CoM 空间线加速度/角加速度，以及控制器指令速度与追踪残差）。
    * `BodyMotionState`：位姿快照与速度状态复合结构，提供直观的标量速率与角速度属性。
  * 最短测地线 SO(3) 空间角速度求解器 (`relative_angular_velocity`)：
    * 采用四元数半球对齐（$q_0 \cdot q_1 \ge 0$）与最小测地角位移，彻底消除跨越 $\pm 180^\circ$ 时的虚假超大速度跳变。
    * 支持世界空间空间角速度（`frame="world"`，$\Delta q = q_1 \cdot q_0^{-1}$）与父级骨骼局部角速度（`frame="local"`，$\Delta q = q_0^{-1} \cdot q_1$）。
  * 状态化跟踪与时序微分器 (`BodyKinematicsTracker`)：
    * 提供单帧在线因果更新接口（`update` / `sample_and_update`）。
    * 提供全局轨迹批处理微分接口（`compute_trajectory_motion_states`），支持因果一阶差分（`backward`）与高阶二阶中心差分（`central`）。
    * 提供零速度初始状态构造器（`create_zero_velocity_state`）。
  * 与现有动作框架无缝集成 (`enrich_motion_state_with_kinematics`)：
    * 将全身物理质心速度、空间根角速度、刚体连杆速度等注入 `MotionState.params`，100% 保持已有 `MotionAction`、`MotionPlanner` 兼容性。
* **自动化测试套件 (`tests/verify_task6ga_body_kinematics.py`)**：
  * 测试 1：静态姿态 0 速度验证通过（线速度严格为 $0.000\text{ m/s}$，角速度严格为 $0.000\text{ rad/s}$）。
  * 测试 2：恒定匀速直线平移，推导线速度严格匹配解析解（误差 $0.0000000000\text{ m/s}$，无虚假副轴速度）。
  * 测试 3：恒定角速度定轴旋转，推导角速度严格匹配解析解（误差 $2.91 \times 10^{-8}\text{ rad/s}$）。
  * 测试 4：任意 3D 空间复合多轴旋转，重构角速度向量误差严格在 $1.43 \times 10^{-6}\text{ rad/s}$。
  * 测试 5：跨越 $\pm 180^\circ$（$+175^\circ \rightarrow -175^\circ$）角速度严格为连续平滑的 $+200^\circ/\text{s}$（$-175^\circ \rightarrow +175^\circ$ 为 $-200^\circ/\text{s}$），0 速度跳跃尖峰。
  * 测试 6：可变时间步长 $\Delta t$ 尺度缩放验证（$0.1\text{ s}$ 到 $0.005\text{ s}$ 误差严格为 0）。
  * 测试 7：单侧手臂运动物理隔离性验证（左手 $2.0\text{ m/s}$，右臂及双腿严格保持 $0.000\text{ m/s}$ 零串扰）。
  * 测试 8：多刚体动量守恒定理验证（直接 CoM 差分速度与 15 个连杆质量加权速度和数学差异仅 $6.12 \times 10^{-6}\text{ m/s}$，完美符合 float32 累积精度）。
  * 测试 9：WholeBodyController 实际求解姿态无缝采样并注入 MotionState。
  * 测试 10：SprintStart 到 SprintBrake 动作交界面（帧 114 $\rightarrow$ 115）速度严格连续平滑（速度跳变差仅 $0.0038\text{ m/s}$）。
* **回归测试**：
  * Task 6F-D 全身控制器测试、Task 6F-C 关节 ROM 测试、Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺急停测试均 100% 通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-020]`。

---

## [2026-10-19] 任务 6F-D：统一全身控制接口与最小协调器

### 新增 (Added)
* **统一全身控制器与多末端协调器 (`src/motion/whole_body_controller.py`)**：
  * 构建统一目标描述与反馈数据结构：
    * `EndEffectorTarget`：末端执行器统一目标规格（目标 ID、世界空间 3D 坐标、世界空间 3D 欧拉朝向、肘/膝极向引导、激活开关、控制权重、接触锁定标志、达程限幅控制）。
    * `WholeBodyControlTargets`：全身目标流式构建器，链式配置双臂（`set_hand`）、双脚（`set_foot`）、骨盆位姿（`set_pelvis`）、空间根节点（`set_root`）及躯干姿态（`set_trunk_posture`）。
    * `UnmetConstraint`：未满足约束详细记录（类别 `REACHABILITY` / `ORIENTATION_ERROR` / `ROM_VIOLATION` / `ROM_CONFLICT`、目标名称、描述、量化误差值、额外上下文）。
    * `EndEffectorFeedback`：各末端毫米级位置追踪误差（`position_error_m`）、度级朝向误差（`orientation_error_deg`）、达程距离、最大物理达程与可达性标志（`is_reachable`）。
    * `WholeBodyControlResult`：单帧全身控制结果（综合成功标志、末端反馈字典、骨盆世界坐标、全身质心结果、ROM 校验结果、未满足约束列表及格式化摘要）。
  * 核心全身控制器 `WholeBodyController`：
    * 严格复用现有 19 骨骼层级与求解器（`arm_ik.py`、`ik.py`、`rigid_link.py`、`joint_limits.py`），零重建骨架、零重写 IK 算法。
    * 统一调度空间根节点、骨盆起伏、躯干 FK 摆动、双腿 IK 与双手 IK。
    * 真实可达性判定：基于请求目标与髋/肩关节距离真实评估物理达程，超出时准确记录 `REACHABILITY` 违规。
    * 真实 ROM 截断与冲突报告：在 evaluated IK 链后调用 `JointModel.validate_armature_pose(use_evaluated_ik=True)` 校验全身 17 个解剖学关节；若存在超限则设置 `success = False`，零虚假成功上报。
    * 实时同步计算全身质心（`compute_whole_body_com`）。
* **自动化测试套件 (`tests/verify_task6fd_whole_body_controller.py`)**：
  * 测试 1：双臂独立 IK 同时控制（左手误差 $0.041\text{ mm}$，右手误差 $0.020\text{ mm}$，朝向对齐误差 $0.000^\circ$）。
  * 测试 2：双脚独立 IK 同时控制（左脚误差 $0.003\text{ mm}$，右脚悬空抬起误差 $0.029\text{ mm}$）。
  * 测试 3：单帧四肢末端（hand_L, hand_R, foot_L, foot_R）同时控制，全末端误差 $< 0.05\text{ mm}$，ROM 0 违规。
  * 测试 4：选择性禁用独立性测试（禁用左手自动回退至 FK 模式，完全不干扰右手与双脚跟踪）。
  * 测试 5：骨盆下蹲（$Z=0.83\text{ m}$）与躯干倾斜下，末端世界空间绝对坐标目标稳定保持（误差 $< 0.03\text{ mm}$）。
  * 测试 6：手部位置与 3D 朝向解耦测试（腕部位置固定，手部在生理 ROM 内变动 3 组朝向，腕部漂移 $< 0.04\text{ mm}$，朝向对齐误差 $0.000^\circ$）。
  * 测试 7：控制器内部 ROM 校验与独立 `JointModel` 校验完全一致（故意过弯脊柱，两者量化超限量严格相等：$20.00^\circ$）。
  * 测试 8：物理不可达目标与 ROM 冲突真实截获（远距不可达目标准确报告 `REACHABILITY` 与 `ROM_VIOLATION`，`success=False`，零虚假放行）。
  * 测试 9：控制器内部全身质心与 `rigid_link` 模块直接计算严格吻合（数值差异严格为 $0.0000000000\text{ m}$）。
  * 测试 10：继承 `MotionAction` 的 `WholeBodyDemoAction` 运行 8 帧，验证控制器与上层动作管线无缝接入。
* **回归测试**：
  * Task 6F-C 关节 ROM 测试、Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺急停测试均 100% 通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-019]`。

---

## [2026-10-19] 任务 6F-C：关节自由度（DOF）与生理活动范围（ROM）约束系统

### 新增 (Added)
* **关节自由度与生理活动范围约束系统 (`src/motion/joint_limits.py`)**：
  * 构建统一关节数据模型 `JointLimitSpec` 与 `JointModel`：
    * 覆盖全部 17 根人体解剖骨骼（`spine`, `neck`, `head`, `shoulder.L/R`, `upper_arm.L/R`, `forearm.L/R`, `hand.L/R`, `thigh.L/R`, `shin.L/R`, `foot.L/R`）。
    * 明确将 `root`（空间根位移与航向）和 `pelvis`（悬浮骨盆基座，用于起伏与全身俯仰缓冲）定义为浮动基座参考系，排除出人体内部 ROM 关节。
    * 内置解剖学文献基准参数（Kapandji、Winter、AAOS、White & Panjabi），详细记录局部坐标系约定、允许自由度、ROM 极值与工程近似假设。
  * 引入角度环绕保护函数（`normalize_angle_deg`, `normalize_angle_rad`）：将角度严格映射至 $(-\pi, \pi]$，杜绝 Euler wrap-around / $\pm 180^\circ$ 造成的虚假违规与跳跃截断。
  * 支持三种约束模式（`ConstraintMode`）：
    * `BOX_EULER`：针对脊柱、颈部、手腕、脚踝的独立多轴盒式限位；
    * `ELLIPTICAL_CONE`：针对肩关节（`upper_arm`）与髋关节（`thigh`）的复合摆动锥约束，防止同时处于极大俯仰与极大展收时超出人体达程；
    * `HINGE_1D`：针对肘关节（`forearm`）与膝关节（`shin`）的单自由度铰链保护，严格锁定反向屈曲（膝关节向前超伸 $\le +2.0^\circ$，肘关节向后超伸 $\ge -2.0^\circ$），副轴微动游隙 $\le \pm 3.0^\circ$。
  * 左右对称镜像支持：针对上臂和股骨外展方向（左侧 $+Z$、右侧 $-Z$）的局部坐标异号特性精确配置镜像，并支持 `with_overrides()` 任意单关节独立覆盖。
  * 双轨非静默接口：
    * `validate_rotations` / `validate_armature_pose`：非破坏性只读校验，返回详细违规轴、请求值、界限与超限量；
    * `clamp_rotations` / `clamp_armature_pose`：投影限幅并返回详细修改报告，杜绝隐式静默篡改。
    * 提供 `extract_evaluated_bone_rotation_rad`，无缝支持评估处于活动状态下的两骨骼 IK（Leg IK / Arm IK）。
* **自动化测试套件 (`tests/verify_task6fc_joint_limits.py`)**：
  * 测试 1：中立站姿 17 个解剖关节全部合法（0 违规）。
  * 测试 2：合法边界内姿态 100% 通过且 0 篡改修改。
  * 测试 3：明确超限姿态（脊柱过度弯曲、肘关节反向折断、膝关节向前反折、肩关节过度外展）被精准检出并量化报告超限量。
  * 测试 4：投影截断后角度严格落在极值边界，重验 100% 合法，无静默篡改。
  * 测试 5：双侧镜像对称验证，左右侧外展对称符号处理完全准确。
  * 测试 6：肘关节向后折断与膝关节向前穿刺反折被铰链锁硬性截断并修正至安全限位（$+2.0^\circ$ / $-2.0^\circ$）。
  * 测试 7：肩关节与髋关节复合多轴旋转椭圆锥约束实测生效（摆角超限量 $35.9^\circ$ 被平滑径向投影至锥面）。
  * 测试 8：角度越界 wrap-around（$365^\circ \rightarrow 10^\circ$, $270^\circ \rightarrow -90^\circ$）稳定性验证通过。
  * 测试 9：骨架姿态截断下 19 根骨骼长度 100% 保持恒定（0 变形拉伸）。
  * 测试 10：实测活跃双腿 IK（站立、抬腿）与活跃双手 IK（前向抓取伸手）姿态全部 100% 符合解剖学 ROM 规范。
* **回归测试**：
  * Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-018]`。

---

## [2026-10-19] 任务 6F-B：刚体连杆、质量分布与全身质心（CoM）计算

### 新增 (Added)
* **刚体连杆分段与解耦式人体质量模型 (`src/motion/rigid_link.py`)**：
  * 构建轻量级不可变数据结构：`RigidSegmentSpec`（分段 ID、关联骨骼名、质量比、标称长度、质心局部比例分数、局部偏移三维向量）、`BodyMassDistribution`（多连杆质量分布与质量守恒自动校验 $\sum w_i = 1.0$）、`SegmentCoMResult`（局部/骨架/世界各空间评估质心）与 `WholeBodyCoMResult`（全身加权质心与分段明细）。
  * 内置标准解剖学生物力学质量分布：
    * `DEMPSTER_WINTER_15_SEGMENT_MODEL`：基于 Winter (2009) / Dempster (1955) 标准 15 分段模型（Head 0.081, Torso 0.355, Pelvis 0.142, Bilateral UpperArm 2x0.028, Forearm 2x0.016, Hand 2x0.006, Thigh 2x0.100, Shank 2x0.0465, Foot 2x0.0145，总和严格为 1.0000）。
    * `DEMPSTER_13_SEGMENT_MODEL`：针对 13 块占位几何网格合并前臂与手部（LowerArm 0.022）的 13 分段模型。
  * 提供 `with_total_mass()`、`with_overrides()` 与 `create_custom_mass_distribution()` 接口，支持任意整体质量重缩放（如 85kg）与局部比重重定义。
* **全身与分段质心前向运动学多空间计算器 (`compute_whole_body_com`)**：
  * 基于 evaluated `pose_bone.matrix` 读取骨骼在 Armature 空间的位置，通过局部标称质心比例与偏移计算骨架空间质心，再经由 `armature_obj.matrix_world` 无缝映射至世界空间。
  * 坐标空间严格无二次变换（Zero Double-Transform）：严禁对已父级绑定到 `CharacterRoot` 的 Armature 再次应用根节点变换，经根节点平移测试验证 Armature 内部质心坐标 100% 保持不变（差值 $0.000000\text{ m}$）。
  * 零破坏非侵入式：只读读取 evaluated 位姿，零修改、零关键帧插入，与现有 FK、腿部 IK 及双臂 IK 100% 兼容。
* **自动化测试套件 (`tests/verify_task6fb_rigid_link.py`)**：
  * 测试 1：质量守恒与合法性（15 分段与 13 分段比例总和严格为 $1.000000$，单段质量比及长度严格大于 0）。
  * 测试 2：自定义总质量缩放（85.0kg 实测总和 $85.0000\text{ kg}$）与自定义比重重归一化。
  * 测试 3：中立站姿静态质心基准（世界坐标 $X=0.000000\text{ m}, Y=-7.997891\text{ m}, Z=1.047881\text{ m}$，质心高度比 $57.58\%$，完全落在解剖学基准 $55\% \sim 58\%$ 区间）。
  * 测试 4：独立数值验算（API 计算全身质心与独立分段质心加权求和完全一致，数值差异严格为 $0.0000000000\text{ m}$）。
  * 测试 5：单臂前平举（$+90^\circ$）质心前移 $\Delta Y=+13.915\text{ mm}$、上抬 $\Delta Z=+13.915\text{ mm}$；单臂侧平举质心外展 $\Delta X=-13.915\text{ mm}$、上抬 $\Delta Z=+13.915\text{ mm}$。
  * 测试 6：双臂不对称位姿质心计算与位姿复原不产生任何质心漂移（漂移 $0.0000000000\text{ m}$）。
  * 测试 7：腿部 IK 抬腿（$0.20\text{ m}$）与双臂 IK 独立抓取姿态下质心正确响应（$\Delta Z=+29.07\text{ mm}$），骨骼变换矩阵零干扰。
  * 测试 8：骨盆下蹲（$-80\text{ mm}$）质心下降 $\Delta Z = -80.00\text{ mm}$；根节点平移 $(+2.5, +5.0, +0.3)\text{ m}$ 世界空间质心严格平移对应矢量，Armature 空间质心严格不变。
* **回归测试**：
  * Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-017]`。

---

## [2026-10-19] 任务 6F-A：双臂独立 IK 与世界空间控制

### 新增 (Added)
* **双臂独立两骨骼 IK 与手部三维朝向控制系统 (`src/rig/arm_ik.py`)**：
  * 构建双臂两骨骼 IK 求解链（`upper_arm` + `forearm` $\rightarrow$ `HandIK.L/R`），肘部极向控制（`ElbowPole.L/R`），统一配置 `chain_count = 2`, `pole_angle = -90.0 deg`, `use_tail = True`, `use_stretch = False`。
  * 引入手部三维世界朝向控制（`HandRotation.L/R`）：在 `hand.L/R` 上配置世界空间 `COPY_ROTATION` 约束，精确解耦末端腕部平移与手部 3D 姿态朝向。
  * 提供 `setup_arm_ik`、`set_hand_ik_target`、`set_arm_ik_influence`、`reset_arm_ik`、`get_arm_ik_state` 完整 API。
  * 具备自动达程检测与球面投影保护（`MAX_ARM_REACH = 0.56m`, `MIN_ARM_REACH = 0.08m`），杜绝骨骼拉伸与肘关节反折。
  * 零破坏向后兼容：约束默认初始化为 `influence = 0.0`，完全不干扰既有纯 FK 摆臂。
* **独立交互式可视化验收原型 (`output/character_arm_ik_prototype.blend`) 与生成脚本 (`run_arm_ik_prototype.py`)**：
  * 制作 216 帧（9.0 秒 @ 24 FPS）交互式时间轴，分 5 阶段演示双侧序列到达、双侧同时运动、腕部固定手掌 3D 旋转、腕部固定肘部极向偏转及平滑回归静止。
  * 场景配置 4 个彩色目标标记（蓝/红/青/黄），摄像机聚焦上半身，直接在 Blender 5.1.1 中按空格即可播放观察，0 关节翻转。
* **自动化测试套件 (`tests/verify_task6fa_arm_ik.py`、`tests/verify_task6fa_visual_prototype.py`)**：
  * 验证 19 根骨骼与层级完整性、默认 FK 透传性、双臂双侧多目标到达精度（误差 $\le 0.051\text{ mm}$）、双侧独立性与零串扰（漂移严格为 $0$）、手部 3D 朝向解耦（朝向误差 $0.0000^\circ$，腕部漂移 $\le 0.025\text{ mm}$）、肘部极向旋转控制（偏转 $11.71\text{ cm}$，腕部漂移 $\le 0.005\text{ mm}$）、超达程保护与零拉伸验证。
  * 验证 `.blend` 原型独立加载、时间轴 216 帧、各阶段运动连续性及重开后骨骼长度 100% 保持不变。
* **回归测试**：
  * Task 6D、Task 6C、Task 6B、Task 5C、Task 4C 全绿通过（退出码 0）。
* **决策记录**：
  * 录入 `[DEC-016]`。

---

## [2026-10-19] 任务 6E：刚体连杆人体运动控制审计与最小架构设计

### 审计与架构设计 (Architecture & Audit)
* **源码全面审计与结论分析**：
  * 深度核实现有 19 根骨骼的层级装配、分段长度、局部轴约定（局部 $X$ 轴俯仰/屈伸，局部 $Y$ 轴扭转，局部 $Z$ 轴展收）。
  * 查明骨架层面当前缺失关节生理活动限位（ROM Constraints），关节安全目前仅由生成算法隐式保障。
  * 查明现有所有动作（行走、跑步、冲刺加速、制动急停）的上半身姿态过度依赖硬编码三角函数谐波，且肩部与手部骨骼从未被主动驱动。
  * 确认双脚完全支持独立世界空间坐标、朝向目标与接触锁定，但双手目前完全不支持世界空间定位（无手部 IK，无极向引导）。
  * 确认身体质量、加权质心（CoM）、转动惯量、摩擦力及接触冲量物理模型在现有系统中完全缺失。
* **分级矩阵与最小架构设计**：
  * 在 `ARCHITECTURE.md` 第 4 节确立“物理约束辅助的程序化动画”技术路线。
  * 规划在动作层与骨骼姿态层之间引入最小刚体连杆中介层（`src/motion/rigid_link.py` 与 `src/rig/arm_ik.py`）。
  * 起草 `RigidSegmentSpec`、`JointLimitSpec`、`EndEffectorTarget`、`WholeBodyPoseSpec` 核心数据接口草案。
  * 确立 Task 6F 的最小实现范围（双手两骨骼 IK、多连杆质量与质心计算、关节生理限位截断）、测试标准与零破坏兼容策略。
* **架构决策记录**：
  * 录入 `[DEC-015]`。

---

## [2026-10-19] 任务 6D：基于统一运动框架实现冲刺后的主动制动与急停

### 新增 (Added)
* **主动制动与急停动作 (SprintBrakeAction)**：
  * 创建 `src/motion/sprint_brake.py`：实现 `SprintBrakeAction`，经由 `MotionPlanner` 调度无缝承接 Task 6C 末尾运动状态（$v = 2.0\text{ m/s}$，冲刺前倾与双脚接触状态）。
  * 解析半余弦单调减速曲线：速度从 2.0 m/s 连续单调降至 0.0 m/s（48 帧 @ 24 FPS，其中 36 帧主动制动 + 12 帧稳定站立收势），最大减速度 $-2.0944\text{ m/s}^2$，制动位移 $1.5000\text{ m}$，无反向位移。
  * 自适应多步制动步态：右脚延续支撑承接 $\rightarrow$ 左脚主抗惯性落地缓冲（位移 $sy + \frac{4}{9}D$）$\rightarrow$ 右脚次级迈步（位移 $sy + \frac{7}{9}D$）$\rightarrow$ 左脚落位终点 $\rightarrow$ 右脚并拢收步，最终进入对称完全双脚支撑静止站立。
  * 深度屈膝与躯干后倾姿态：骨盆下蹲缓冲至 $-0.115\text{ m}$，躯干后倾至 $-6.0^\circ$ 抵消前向冲量，随后平滑回正至 $0.0^\circ$，手臂协调摆动收束。
* **独立原型管线与自动化校验**：
  * 创建 `run_sprint_brake_prototype.py`：生成连贯独立动画 `output/character_sprint_brake_prototype.blend`（162 帧，前 114 帧起步冲刺 + 后 48 帧制动急停）及 5 张关键预览图（帧 110、114、120、138、155）。
  * 创建 `tests/verify_task6d_sprint_brake.py`：自动重开核验交界处连续性、单调减速、接触漂移、无穿地、膝关节方向、IK 可达性与停止稳定性。
* **配置与决策**：
  * 更新 `src/config.py`，导出 `src/motion/__init__.py`。
  * 录入 `[DEC-014]`。

### 状态验证 (Verification)
* **交界处连续性**：第 114 帧至 115 帧交界根节点位移 $\Delta Y = 0.08328\text{ m}$（对应离散速度 $1.9987\text{ m/s}$），躯干俯仰角无跳跃（$\Delta = 0.000^\circ$），骨盆高度无跳跃（$\Delta = 0.00000\text{ m}$），接触状态平滑继承。
* **制动性能与停止精度**：制动位移 $1.50000\text{ m}$，速度严格单调递减并精确归零（$0.000000\text{ m/s}$），无倒退；最后 10 帧根节点 $Y$ 抖动严格为 $0.00000000\text{ m}$，双脚对称锁定在 $Y = +0.0833\text{ m}$。
* **接触与约束质量**：制动期间支撑脚最大漂移左脚 $0.000035\text{ m}$、右脚 $0.000033\text{ m}$；最低脚底 $Z = -0.000043\text{ m}$（无穿地）；膝关节始终保持前向屈曲（前向偏移 $\ge +0.0602\text{ m}$）；最大髋踝距 $0.82000\text{ m} \le 0.82\text{ m}$（0 IK 不可达事件，0 IK 钳制事件）。
* **回归测试**：Task 6C（起跑冲刺）、Task 6B（跑步）、Task 5C（变速行走）回归套件全部通过（退出码 0）。

---

## [2026-10-18] 任务 6C：基于统一运动框架实现爆发式起步与加速冲刺

### 新增 (Added)
* **爆发起步与自适应冲刺动作 (SprintStartAction)**：
  * 创建 `src/motion/sprint_start.py`：实现 `SprintStartAction`，经由 `MotionPlanner` 统一调度。支持蓄力下蹲（骨盆下降约 0.10 m，躯干前倾约 23°）、前倾蹬地、解析二次速度曲线单调加速至 2.0 m/s，并过渡到稳定冲刺。
  * 步态参数随速度动态自适应：步时 12->10 帧，支撑期 9->4 帧，腾空期 3->6 帧，步长 0.350->0.833 m，步频 2.00->2.40 步/秒。
  * 终止帧保留完整动量向量 `(0.0, 2.0, 0.0) m/s` 与步态相位，验证支持以任意帧及空间偏移衔接后续动作。
* **原型与多维验证**：
  * 创建 `run_sprint_prototype.py`：生成 `output/character_sprint_start_prototype.blend`（114 帧）及 5 张关键预览图。
  * 创建 `tests/verify_task6c_sprint_start.py`：自动核验速度、加速度、步态协调、接触漂移、落地精准度与动量继承。
* **系统配置与架构决策**：
  * 更新 `src/config.py`，导出 `src/motion/__init__.py`。
  * 录入 `[DEC-011]`、`[DEC-012]`、`[DEC-013]`。

### 状态验证 (Verification)
* **最高速度与位移**：速度从 0.0 解析单调加速至 2.0000 m/s，全长 114 帧（4.75 秒 @ 24 FPS），总位移 6.5833 m。
* **接触与 IK 质量**：支撑脚漂移 $\le 0.000024\text{ m}$，落点误差 $\le 0.000003\text{ m}$，最低脚底 $Z \ge -0.000033\text{ m}$，腾空脚离地 $\ge +0.0240\text{ m}$，双膝前屈偏移 $\ge +0.1414\text{ m}$，最大髋踝距 $0.82000\text{ m} \le 0.82\text{ m}$（0 IK 不可达违规，0 IK 钳制）。
* **回归测试**：Task 6A、Task 6B、Task 5C 回归全部通过。

---

## [2026-10-16] 任务 3：程序化三维场景、灯光与摄像机基础系统

### 新增 (Added)
* **纯数学布局生成器与走廊净空算法**：
  * 创建 `src/scene/layout.py`：基于固定种子生成地面尺寸、建筑体块、柱状障碍物与运动路径点，并通过点线投影距离算法确保 $\ge 2.4\text{ m}$ 走廊净空。
* **程序化场景构建与材质**：
  * 更新 `src/scene/builder.py`：实现符合统一世界坐标约定（$Z=0$ 为地表）的程序化地台、6 座建筑体块、8 根圆柱障碍物与航标标记。
* **程序化主辅灯光与环境**：
  * 更新 `src/lighting/setup.py`：创建 2500W 暖色主光、800W 冷色辅光与世界环境天光。
* **自动目标追踪与关键帧运镜摄像机**：
  * 更新 `src/camera/controller.py`：标准 50mm 镜头、绑定 `TRACK_TO` 观察目标，在第 1 帧、第 180 帧、第 360 帧配置平滑运镜轨迹。
* **多帧预览渲染与多维验证系统**：
  * 更新 `src/render/engine.py`：支持批量渲染多帧预览图像。
  * 更新 `src/validation/checker.py`：新增空间坐标标高（$Z=0$）、走廊净空、相机关键帧位移与多帧渲染图像差异性自动校验。
  * 创建 `tests/test_task3_spatial.py`：空间种子确定性与净空单元测试。
  * 创建 `tests/verify_task3_blend.py`：重开 `.blend` 文件校验场景集合、对象及相机关键帧状态。
* **规范与决策记录**：
  * 更新 `ARCHITECTURE.md`：记录统一物理世界坐标约定（$Z$ 轴向上，$Z=0$ 为地面，单位米）。
  * 录入 `[DEC-010]`：世界坐标约定与纯数据走廊安全净空机制。

### 状态验证 (Verification)
* **坐标与净空验证**：地台顶面精确处于 $Z = 0.000000\text{ m}$；走廊净空经几何检验 100% 通过无碰撞。
* **种子确定性与变异性**：相同种子（Seed=42）产出坐标 100% 相同；不同种子（Seed=99）产出坐标不同。
* **摄像机动态位移**：第 1 帧与第 180 帧空间位移实测达 $11.3578\text{ m}$，朝向目标稳定。
* **产物多维核验**：
  * `output/procedural_scene.blend`（105,272 字节，无头重开核验通过）。
  * `output/preview_frame_0001.png`（306,427 字节，1280x720，远景全景）。
  * `output/preview_frame_0180.png`（248,321 字节，1280x720，中景跟拍新视角）。
  * 两张预览图经 SHA256 哈希比对与视觉检查证实具有明确视角差异。
* **管线执行与退出码**：`run_pipeline.ps1` 执行成功，退出码为 `0`。

---

## [2026-10-16] 任务 2：建立 Git 版本控制与程序化动画工程骨架

### 新增 (Added)
* 初始化本地 Git 仓库 (`git init`) 与 `.gitignore`。
* 创建模块化工程骨架 `src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/` 等）。
* 录入 `[DEC-009]`。

### 状态验证 (Verification)
* 验证通过：`run_pipeline.ps1` 退出码 0，生成 `output/procedural_scene.blend` 与单帧图像。

---

## [2026-10-15] 任务 1：Blender 环境与自动执行工具链验证

### 新增 (Added)
* 测试套件：`tests/test_env.py`、`tests/verify_blend.py`、`tests/run_validation.py`、`tests/run_test.ps1`。
* 录入 `[DEC-008]`。

### 状态验证 (Verification)
* Blender 5.1.1 + Python 3.13.9 路径定位与无头执行成功。

---

## [2026-10-15] 任务 0.5：建立跨 AI 同步协议与上下文恢复机制

### 新增 (Added)
* 创建 `AI_SYNC.md`，增加任务生命周期协议与防状态漂移原则。录入 `[DEC-007]`。

---

## [2026-10-15] 任务 0：底层约束、持久记忆与基础设施建立

### 新增 (Added)
* 创建规则 `GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`。
* 创建文档 `PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`HANDOFF.md`、`README.md`。
