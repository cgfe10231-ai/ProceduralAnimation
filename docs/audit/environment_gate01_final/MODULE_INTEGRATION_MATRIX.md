# MODULE_INTEGRATION_MATRIX: 全仓库模块清点与集成状态矩阵

**审计基准 Commit**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计时间**：2026-10-29  
**所属门禁**：Environment Gate 01 — Final Architecture Audit (Audit A)  

---

## 1. 集成状态分类定义与准则

为杜绝“代码写了即代表接入”、“函数被调用即代表进入生产闭环”的认知漂移，全仓库所有模块严格采用以下 7 级集成状态标定：

| 状态标识 | 定义与判定准则 |
| :--- | :--- |
| **`PRODUCTION_ACTIVE`** | **主链活跃生产模块**：深度接入 19 骨骼角色连续动画生成生产主链，其输出直接决定骨骼姿态、IK 目标或环境几何判定。 |
| **`PARTIALLY_INTEGRATED`** | **部分接入模块**：在主链中被实例化或调用，但仅部分输出被消费，核心反馈回路处于开环状态（如纯前馈、单向记录）。 |
| **`TELEMETRY_ONLY`** | **遥测专用模块**：在主链或执行器中运行，但计算结果仅写入遥测数据结构、日志或 Scene ID 属性，对实际骨骼姿态零影响。 |
| **`PROTOTYPE_ONLY`** | **早期原型模块**：历史阶段验证原型，独立运行或仅供独立 demo 调用，未接入当前 19 骨骼地形连续通行主链。 |
| **`TEST_ONLY`** | **测试专用内核**：算法实现完备且单元测试全绿，但仅在独立测试脚本中被调用，未接入生产流水线或 19 骨骼角色。 |
| **`UNUSED`** | **闲置代码**：已被更高阶模块完全替代的历史辅助函数或占位代码。 |
| **`UNVERIFIED`** | **未验证模块**：存在代码但无直接单元测试覆盖或无生产调用者。 |

---

## 2. 全仓库核心生产模块清点矩阵 (`src/`)

### 2.1 运动控制与动力学模块 (`src/motion/`)

| 模块文件 | 主要类与函数 | 核心职责 | 调用方 (Caller) | 被调用方 (Callee) | 创建数据 | 消费方 (Consumer) | 集成状态 | 重复实现排查 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py) | `MotionPlanner`, `MotionAction`, `MotionState`, `ContactPointState` | 统一动作编排框架、时间线调度、步态状态机与帧级上下文维护 | `playground_terrain_traversal.py`, `run_unified_motion_pipeline.py` | `KinematicBridgeExecutor`, `TerrainWalkAction`, `reset_pose`, `setup_leg_ik` | `MotionState`, `MotionRuntimeContext`, `ActionExecutionResult` | `playground_terrain_traversal.py`, 渲染管线 | **`PRODUCTION_ACTIVE`** | 无重复；为全局动作调度单一权威入口 (SSOT)。 |
| [`src/motion/terrain_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/terrain_walk.py) | `TerrainWalkAction`, `plan_terrain_footsteps`, `_evaluate_root_y_hermite`, `_compute_swing_clearance_z` | 地形自适应步态规划、Hermite 样条 Root 轨迹、摆动脚正弦越障包络、躯干与骨盆几何倾角调度 | `MotionPlanner.execute()` | `query_ground_support_at`, `KinematicBridgeExecutor.execute_frame()` | `TerrainStepPlan`, `KinematicPlannedPose`, `PlannedFootTarget` | `KinematicBridgeExecutor` | **`PRODUCTION_ACTIVE`** | 无重复；为当前复杂 3D 地形行走唯一动作实现。 |
| [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py) | `KinematicBridgeExecutor`, `KinematicPlannedPose`, `BridgeExecutionResult` | 6 阶段权威运动学桥接器：解耦运动规划意图与物理场景、调度 WBC、执行几何接触合规检查与遥测富集 | `TerrainWalkAction.execute()`, `MotionPlanner` | `WholeBodyController`, `query_ground_support_at`, `evaluate_limb_contacts_from_armature` | `BridgeExecutionResult`, `MultiContactState`, `active_limb_targets` | `TerrainWalkAction`, `MotionState`, Blender 关键帧系统 | **`PRODUCTION_ACTIVE`** | 无重复；桥接层唯一实现。消除了 Z=0 扁平化硬编码。 |
| [`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py) | `WholeBodyController`, `WholeBodyControlTargets`, `WholeBodyControlResult` | 全身协调器：分发 Root 平移/偏航、骨盆位姿、躯干 FK、手脚 IK，更新 Blender 视图层并校验 ROM 与可达性 | `KinematicBridgeExecutor.execute_frame()` | `set_foot_ik_target`, `lock_foot_contact`, `set_hand_ik_target`, `check_armature_joint_limits`, `compute_whole_body_com` | `WholeBodyControlResult`, `EndEffectorFeedback`, `UnmetConstraint` | `KinematicBridgeExecutor` | **`PRODUCTION_ACTIVE`** | 骨骼操作唯一合法写入者。 |
| [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py) | `ContactRecord`, `MultiContactState`, `evaluate_limb_contacts_from_armature`, `DEFAULT_LIMB_LOCAL_ANCHORS` | 多肢接触几何约束计算、接触点/法线/摩擦力、局部锚点校准与瞬时支撑状态分类 (`SupportType`) | `KinematicBridgeExecutor` | `mathutils.Vector`, `mathutils.Matrix` | `MultiContactState`, `ContactRecord`, `GeometricConstraintResult` | `KinematicBridgeExecutor`, 遥测 JSON | **`PARTIALLY_INTEGRATED`** | 几何计算完全接入，但接触合规结果仅单向记入遥测，未闭环反馈给步态规划。 |
| [`src/motion/rigid_link.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/rigid_link.py) | `RigidLinkSegmentModel`, `compute_whole_body_com`, `HUMAN_BODY_MASS_KG` | 19 骨骼刚体质量分布模型、局部连杆质心变换与全身质心 (CoM) 计算 | `WholeBodyController.execute_frame()` | `mathutils.Vector`, `armature.pose.bones` | `com_world: Tuple[float, float, float]` | `WholeBodyControlResult`, 遥测面板 | **`TELEMETRY_ONLY`** | 准确计算 70.0kg 全身质心，但 CoM 仅作为遥测指标，不影响人体姿态与平衡。 |
| [`src/motion/body_inertia.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_inertia.py) | `RigidLinkInertiaModel`, `compute_whole_body_inertia` | 19 骨骼局部惯性张量、平行轴定理世界惯性张量与全身角动量计算 | `KinematicBridgeExecutor.execute_frame()` | `compute_segment_angular_velocity`, `pose.bones` | `InertiaState`, 惯性张量矩阵, 角动量向量 | `motion_state.params["inertia_state"]` | **`TELEMETRY_ONLY`** | 纯遥测记录，无受力或姿态动力学反馈。 |
| [`src/motion/body_kinematics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_kinematics.py) | `KinematicsDifferentiator`, `compute_segment_velocities` | 骨骼段线速度与角速度数值差分计算、中心差分滤波 | `KinematicBridgeExecutor.execute_frame()` | `pose.bones` 矩阵历史队列 | `KinematicVelocityState` | `motion_state.params` | **`TELEMETRY_ONLY`** | 纯微分遥测，不驱动人体运动。 |
| [`src/motion/joint_limits.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/joint_limits.py) | `AnatomicalJointLimitModel`, `check_armature_joint_limits` | 解剖学生理活动范围 (ROM) 门禁约束、欧拉角与相对四元数越界检查 | `WholeBodyController.execute_frame()` | `pose.bones` 旋转角 | `ROMValidationResult`, `ROMViolation` | `WholeBodyControlResult`, 门禁拦截 | **`PRODUCTION_ACTIVE`** | 处于门禁激活状态；发生越界时如实抛出违规，但不执行姿态软裁剪。 |
| [`src/motion/forward_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/forward_dynamics.py) | `ForwardDynamicsIntegrator`, `ForwardDynamicsState` | 单刚体二阶辛 Runge-Kutta / 中点姿态积分器、牛顿-欧拉重力与外力积分 | `verify_task6gd_forward_dynamics.py`, `verify_task6gd_playground_dynamics.py` | 纯数学矩阵运算 (无 `bpy`) | `ForwardDynamicsState` | 仅单元测试与可视化刚体代理消费 | **`TEST_ONLY`** | 算法完备且自测通过，但与 19 骨骼人体主链完全脱节。 |
| [`src/motion/closed_loop_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/closed_loop_dynamics.py) | `MultiFrameDynamicsController`, `DynamicsClosedLoopState` | 质心轨迹跟踪、PD 姿态误差反馈、陀螺耦合补偿与闭环状态前向推进 | `verify_task6gd_closed_loop_dynamics.py` | `ForwardDynamicsIntegrator`, `MultiContactForceSolver` | `DynamicsClosedLoopState` | 仅单元测试消费 | **`TEST_ONLY`** | 闭环动力学未连接到生产动作 `TerrainWalkAction`。 |
| [`src/motion/contact_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_dynamics.py) | `ContactDynamicsIntegrator`, `ContactKinematicState` | 多接触点冲量动量更新、切向滑动阻尼与恢复系数计算 | `verify_task6gd_contact_dynamics.py` | `MultiContactState` | `ContactDynamicState` | 仅单元测试消费 | **`TEST_ONLY`** | 仅供 Task 6G-D 独立质心动力学测试。 |
| [`src/motion/contact_force_solver.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_force_solver.py) | `MultiContactForceSolver`, `ContactForceDistribution` | 摩擦锥二次规划 (QP) 求解器、多接触支撑力优化分配与质心力分配 | `verify_task6gd_contact_force_solver.py`, `closed_loop_dynamics.py` | `numpy` / 自研解析投影解算法 | `ContactForceDistribution`, 各足接触力向量 | 仅动力学单元测试消费 | **`TEST_ONLY`** | 角色骨骼从未读取受力求解结果，人体处于零受力反馈状态。 |
| [`src/motion/start_stop_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/start_stop_walk.py) | `StartStopWalkAction` | 历史 Task 5C / 6A 起停步态动作（平地） | `verify_r3b2_walk_action.py` | `KinematicBridgeExecutor` | `KinematicPlannedPose` | 回归测试套件 | **`PROTOTYPE_ONLY`** | 历史平地起跑步态，已被通用 `TerrainWalkAction` 包含与超越。 |
| [`src/motion/run_cycle.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/run_cycle.py) | `RunAction` | 历史 Task 6B 匀速跑步动作（腾空步态） | `verify_r3b2_run_action.py` | `KinematicBridgeExecutor` | `KinematicPlannedPose` | 回归测试套件 | **`PROTOTYPE_ONLY`** | 历史平地跑步原型。 |
| [`src/motion/sprint_start.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/sprint_start.py) | `SprintStartAction` | 历史 Task 6C 冲刺加速爆发起步动作 | `verify_r3b2_sprint_start.py` | `KinematicBridgeExecutor` | `KinematicPlannedPose` | 回归测试套件 | **`PROTOTYPE_ONLY`** | 历史爆发起步原型。 |
| [`src/motion/sprint_brake.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/sprint_brake.py) | `SprintBrakeAction` | 历史 Task 6D 急停减速制动动作 | `verify_r3b2_sprint_brake.py` | `KinematicBridgeExecutor` | `KinematicPlannedPose` | 回归测试套件 | **`PROTOTYPE_ONLY`** | 历史急停制动原型。 |
| [`src/motion/forward_walk.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/forward_walk.py) | `ForwardWalkAction` | Task 5B 前向连续行走动作（旧平地） | 历史验证测试 | `IK`, `FK` | 关键帧 | 回归测试 | **`PROTOTYPE_ONLY`** | 早期平地步态。 |
| [`src/motion/walk_cycle.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/walk_cycle.py) | `WalkCycleAction` | Task 5A 原地行走循环动作 | 历史验证测试 | `IK`, `FK` | 关键帧 | 回归测试 | **`PROTOTYPE_ONLY`** | 早期原地步态。 |

---

### 2.2 场景装配与环境查询模块 (`src/scene/`)

| 模块文件 | 主要类与函数 | 核心职责 | 调用方 (Caller) | 被调用方 (Callee) | 创建数据 | 消费方 (Consumer) | 集成状态 | 重复实现排查 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| [`src/scene/blender_mesh_query_adapter.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/blender_mesh_query_adapter.py) | `BlenderMeshEnvironmentAdapter`, `AdapterCacheState` | 基于 `mathutils.bvhtree.BVHTree` 的真实 3D 网格射线与最近邻查询、双通道场景失效检测体系 (Path A/B)、集合生命周期隔离与异常安全加固 | `DynamicsEnvironmentQuery` | `bpy.types.Depsgraph`, `BVHTree.FromPolygons` | `MeshRayCastResult`, `MeshNearestResult` | `DynamicsEnvironmentQuery` | **`PRODUCTION_ACTIVE`** | 真实 3D 几何网格射线检测单一权威底层 (SSOT)。 |
| [`src/scene/environment_query.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/environment_query.py) | `EnvironmentQuery`, `DynamicsEnvironmentQuery`, `SurfaceQueryResult`, `OrientedSurface` | 环境感知中间层：单次物理命中支撑查询契约 (`query_ground_support_at`)、网格优先 (`prefer_mesh`)、严格无支撑拒绝 | `TerrainWalkAction`, `KinematicBridgeExecutor` | `BlenderMeshEnvironmentAdapter.ray_cast` | `SurfaceQueryResult` | `TerrainWalkAction`, `KinematicBridgeExecutor` | **`PRODUCTION_ACTIVE`** | 生产主链环境感知单一接口。 |
| [`src/scene/playground_terrain_traversal.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_terrain_traversal.py) | `generate_dynamics_playground_environment_gate01_u3_blend`, `generate_dynamics_playground_environment_gate01_u3_s1_blend`, `generate_dynamics_playground_environment_gate01_u3_s2_blend`, `setup_task7a2_cameras_and_markers` | 生产场景装配总入口：打开基准 Blend、装配 19 骨骼角色、实例化网格查询器、编排 Course B 步态、运行 MotionPlanner、生成伴随 JSON | `tests/test_environment_gate01_unit3.py`, `test_environment_gate01_u3_s1.py`, `test_environment_gate01_u3_s2.py` | `assemble_character_in_playground`, `MotionPlanner`, `TerrainWalkAction` | 派生 `.blend` 场景、逐帧遥测 JSON | 用户视觉验收、回归检验器 | **`PRODUCTION_ACTIVE`** | 生产场景装配权威入口。 |
| [`src/scene/playground_character_assembly.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_assembly.py) | `assemble_character_in_playground` | 将 19 骨骼角色（网格、骨架、IK 约束、材质）无污染合流装配入 `DynamicsPlayground` 场景集合 | `playground_terrain_traversal.py` | `build_character`, `build_rig`, `bind_character_to_rig`, `setup_leg_ik` | 包含角色的装配后场景 | `playground_terrain_traversal.py` | **`PRODUCTION_ACTIVE`** | 角色场景装配 SSOT。 |
| [`src/scene/playground_terrain_validation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_terrain_validation.py) | `validate_dynamics_playground_terrain_traversal`, `validate_dynamics_playground_environment_gate01_u3` | 只读重开场景核验器：零豁免校验 700 帧 C0 连续性、骨骼拉伸、支撑滑移、ROM 越界与真实接触 | 测试套件 | `BlenderMeshEnvironmentAdapter`, `check_armature_joint_limits` | `TerrainValidationReport` | 测试断言与验收记录 | **`PRODUCTION_ACTIVE`** | 物理合规独立核验器。 |
| [`src/scene/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/builder.py) | `build_scene`, `build_dynamics_playground` | 生成基准训练场场景（14 区地形网格与标记） | `tests/verify_task6gd_playground_blend.py` | `bpy.ops.mesh.primitive_*` | `output/dynamics_playground.blend` | 训练场资产源头 | **`PRODUCTION_ACTIVE`** | 基准训练场地貌生成源。 |
| [`src/scene/dynamics_visualizer.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visualizer.py) | `DynamicsVisualizer` | 动力学遥测箭头与接触点 3D 可视化物体生成（力向量、法线、支撑多边形） | `playground_terrain_traversal.py:setup_control_chain_debug_scene()` | `bpy.data.objects.new` | `ControlChain_Debug` 视窗物体 | 开发者视口调试 | **`PARTIALLY_INTEGRATED`** | 接入诊断场景 (`Task7A2_ControlChain_Debug`)，但仅作为可视化显示，无物理反馈。 |
| [`src/scene/dynamics_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visual_evidence.py) | `capture_viewport_screenshot`, `render_multi_view_evidence` | 自动化视口截图与多视角关键帧渲染工具 | 验收测试与报告生成脚本 | `bpy.ops.render.render` | PNG 图像、GIF 动图 | 证据目录 (`docs/evidence/`) | **`PRODUCTION_ACTIVE`** | 视觉证据自动采集管线。 |

---

### 2.3 角色模型与绑定控制模块 (`src/character/`, `src/rig/`)

| 模块文件 | 主要类与函数 | 核心职责 | 调用方 (Caller) | 被调用方 (Callee) | 创建数据 | 消费方 (Consumer) | 集成状态 | 重复实现排查 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| [`src/character/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/character/builder.py) | `build_character` | 构建 13 段简单人形几何占位物体（Head, Torso, Pelvis, 4肢等）及材质 | `assemble_character_in_playground`, 测试 | `bpy.data.meshes.new` | 13 个角色 Mesh 物体字典 | `bind_character_to_rig` | **`PRODUCTION_ACTIVE`** | 角色占位模型单一源头。 |
| [`src/rig/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py) | `build_rig`, `bind_character_to_rig` | 构建 19 骨骼标准人形骨架 (`CharacterArmature`)，建立父子层级与蒙皮绑定 | `assemble_character_in_playground`, 测试 | `arm.edit_bones.new`, 顶点组绑定 | `CharacterArmature` 骨架物体 | `setup_leg_ik`, `WholeBodyController` | **`PRODUCTION_ACTIVE`** | 19 骨骼标准骨架 SSOT。 |
| [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py) | `setup_leg_ik`, `set_foot_ik_target`, `ANKLE_REST_Z`, `HIP_X_OFFSET` | 双腿 2 骨骼 IK 约束配置、膝盖极向目标、足底世界坐标锁定与解除 | `WholeBodyController.execute_frame()`, `assemble_character_in_playground` | Blender 原生 `IK` 骨骼约束 | `FootIK.L`, `FootIK.R`, `KneePole.L`, `KneePole.R` | `WholeBodyController` | **`PRODUCTION_ACTIVE`** | 下肢 IK 单一实现。 |
| [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py) | `setup_arm_ik`, `set_hand_ik_target`, `set_arm_ik_influence` | 双臂 2 骨骼 IK 约束配置、肘部极向目标与手部末端朝向控制 | `WholeBodyController.execute_frame()` | Blender 原生 `IK` 约束 | `HandIK.L`, `HandIK.R`, `ElbowPole.L`, `ElbowPole.R` | `WholeBodyController` | **`PARTIALLY_INTEGRATED`** | 约束已就绪并受 WBC 管理；但在当前地形行走中权重设为 0，手臂走 FK 摆臂。 |
| [`src/rig/foot_contact.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/foot_contact.py) | `lock_foot_contact`, `unlock_foot_contact`, `evaluate_foot_support` | 支撑脚世界空间锁定器（解除与 Root 的父子绑定，严格锁定于世界地表，消除滑移） | `WholeBodyController.execute_frame()` | `ik_obj.matrix_world` 操作 | `is_locked`, `contact_world_xyz` | Blender IK 求解器 | **`PRODUCTION_ACTIVE`** | 足底世界锁定单一实现。 |

---

## 3. 根目录运行脚本审计清单

| 根目录脚本文件 | 核心职责 | 当前调用链路与依赖 | 实际使用状态 |
| :--- | :--- | :--- | :---: |
| [`run_task7a2_terrain_traversal.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_task7a2_terrain_traversal.py) | Task 7A-2 复杂地形行走命令行主运行入口，调用 `generate_dynamics_playground_task7a2_blend` 并渲染动图 | 依赖 `src/scene/playground_terrain_traversal.py` | **活跃生产入口** |
| [`run_pipeline.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_pipeline.py) | 历史 Phase 1 阶段简单动画渲染流程入口 | 依赖 `src/pipeline.py` | **历史维护 (PROTOTYPE)** |
| [`run_unified_motion_pipeline.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_unified_motion_pipeline.py) | Task 6A-6D 统一 462 帧平地多动作连续过渡流程入口 | 依赖 `src/motion/framework.py` | **活跃回归入口** |
| [`run_dynamics_playground.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_dynamics_playground.py) | 重新生成基准 `output/dynamics_playground.blend` 的构建脚本 | 依赖 `src/scene/builder.py` | **资产构建入口** |
| `run_character_prototype.py`, `run_rig_prototype.py`, `run_ik_prototype.py`, `run_arm_ik_prototype.py` | 早期各子系统独立可视化验证原型 | 依赖对应 `src/*/prototype.py` | **历史原型 (PROTOTYPE_ONLY)** |
| `run_walk_cycle_prototype.py`, `run_forward_walk_prototype.py`, `run_start_stop_walk_prototype.py`, `run_run_prototype.py`, `run_sprint_prototype.py`, `run_sprint_brake_prototype.py` | 历史各单一动作平地行走/跑步独立验证原型 | 依赖对应 `src/motion/*_prototype.py` | **历史原型 (PROTOTYPE_ONLY)** |
| [`run_generate_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_generate_visual_evidence.py) | Task 6G-D 动力学多视角截图自动化生成脚本 | 依赖 `src/scene/dynamics_visual_evidence.py` | **证据工具** |

---

## 4. 关键结论与职责重叠排查

1. **零控制器重复实现**：
   全仓库严格遵循单一权威写入者原则：
   $$\text{MotionPlanner} \longrightarrow \text{TerrainWalkAction} \longrightarrow \text{KinematicBridgeExecutor} \longrightarrow \text{WholeBodyController} \longrightarrow \text{Rig/IK/FK}$$
   没有任何模块绕过 `WholeBodyController` 直接在生产中操作骨骼或写入变换矩阵。
2. **纯数学内核跨宿主解耦**：
   `ForwardDynamicsIntegrator`、`MultiContactForceSolver`、`ContactDynamicsIntegrator` 均为零 `bpy` 依赖的纯 Python/NumPy 实现，保持了未来脱离 Blender 移植至其他实时物理引擎的架构潜力。
3. **主链与动力学合流状态**：
   当前 19 骨骼人体运动由运动学与几何感知完全驱动（`TerrainWalkAction` + `KinematicBridgeExecutor` + `WholeBodyController`）；已实现的质心动力学积分器与接触力二次规划求解器处于 `TEST_ONLY` 状态，尚未接入 19 骨骼人体的主闭环控制。
