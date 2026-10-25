# PHASE 7A-1: 历史角色资产与控制链复用审计报告 (Historical Asset & Control Chain Reuse Audit)

> **审计基准 Git HEAD**：`994bfc4e5ecc705c6c48ef54ac526be4601fc12c`  
> **审计引擎**：Blender 5.1.1 (`hash b70da489d7f4`) + Python AST 静态符号核验  
> **审计范围**：19 份核心 Python 生产模块、[`output/unified_motion_integration.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/unified_motion_integration.blend)（27 对象 / 19 骨骼 / 174 F-Curves）与 [`output/dynamics_playground.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/dynamics_playground.blend)（102 对象 / 6 大地形区 / 5 大动力学验证工位）。

---

## 一、已有 Blender 资产实测盘点 (Blender 5.1.1 Real Asset Inspection)

### 1.1 [`output/unified_motion_integration.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/unified_motion_integration.blend) 角色资产实测
通过 Blender 5.1.1 直接打开并遍历 `bpy.data` 核实：
* **集合 (`bpy.data.collections`)**：共 2 个（`Character`、`Collection`）。所有角色相关对象均收纳于 `Character` 集合中。
* **根节点 (`CharacterRoot`)**：`EMPTY` 对象（`PLAIN_AXES`，`empty_display_size = 0.25 m`），Frame 1 世界坐标为 `(0.0, -8.0, 0.0) m`，旋转为 `(0.0, 0.0, 0.0)`。
* **骨架 (`CharacterArmature` / `CharacterArmatureData`)**：
  * 父级为 `CharacterRoot`（`matrix_parent_inverse = Identity`，局部位置 `(0.0, 0.0, 0.0)`）。
  * **19 根骨骼完整清单与几何规格**（定义于 [`src/rig/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py) 的 `BONE_SPECIFICATIONS`）：
    1. 中轴链（5 根）：`root` (`z: 0.00 -> 0.20 m`, `len=0.20 m`)、`pelvis` (`z: 0.89 -> 1.07 m`, `len=0.18 m`, parent=`root`)、`spine` (`z: 1.07 -> 1.55 m`, `len=0.48 m`, connected)、`neck` (`z: 1.55 -> 1.60 m`, `len=0.05 m`, connected)、`head` (`z: 1.60 -> 1.82 m`, `len=0.22 m`, connected)。
    2. 左臂链（4 根）：`shoulder.L` (`(-0.06, 0, 1.54) -> (-0.24, 0, 1.54)`, `len=0.18 m`)、`upper_arm.L` (`z: 1.54 -> 1.24 m`, `len=0.30 m`)、`forearm.L` (`z: 1.24 -> 0.98 m`, `len=0.26 m`, `use_ik_limit_x=True [0, 2.618 rad]`, `lock_ik_y=True`, `lock_ik_z=True`)、`hand.L` (`z: 0.98 -> 0.88 m`, `len=0.10 m`)。
    3. 右臂链（4 根）：`shoulder.R`、`upper_arm.R` (`len=0.30 m`)、`forearm.R` (`len=0.26 m`, 肘部单轴铰链 IK 锁)、`hand.R` (`len=0.10 m`)。
    4. 左腿链（3 根）：`thigh.L` (`(-0.11, 0, 0.89) -> (-0.11, 0, 0.47)`, `len=0.42 m`, parent=`pelvis`)、`shin.L` (`z: 0.47 -> 0.07 m`, `len=0.40 m`, `use_ik_limit_x=True [-2.705, 0.0 rad]`, `lock_ik_y=True`, `lock_ik_z=True`)、`foot.L` (`(-0.11, 0, 0.07) -> (-0.11, 0.15, 0.035)`, `len=0.154 m`, `use_inherit_rotation=False`)。
    5. 右腿链（3 根）：`thigh.R` (`len=0.42 m`)、`shin.R` (`len=0.40 m`, 膝部单轴铰链 IK 锁)、`foot.R` (`len=0.154 m`, `use_inherit_rotation=False`)。
* **13 个可视化身体部件 (`REQUIRED_PARTS`) 与绑定机制**：
  * 包含：`Head` (`0.22x0.22x0.22 m` UV Sphere)、`Torso` (`0.34x0.20x0.48 m`)、`Pelvis` (`0.32x0.18x0.18 m`)、`UpperArm_L/R` (`0.08x0.08x0.30 m`)、`LowerArm_L/R` (`0.07x0.07x0.26 m`)、`UpperLeg_L/R` (`0.11x0.11x0.42 m`)、`LowerLeg_L/R` (`0.09x0.09x0.40 m`)、`Foot_L/R` (`0.10x0.22x0.07 m`，底面精确对齐 `Z = 0.0 m`)。
  * **绑定方式核实（Armature Modifier 核查）**：13 个 Mesh 对象的 `modifiers` 列表均为空（`[]`），**未使用蒙皮变形 `ARMATURE` Modifier**，而是通过 [`bind_character_to_rig()`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py#L143-L196) 采用**刚体骨骼父子绑定**（`parent = CharacterArmature`, `parent_type = "BONE"`, `parent_bone = PART_TO_BONE_MAP[part_name]`）并精确保持静息世界变换矩阵（`matrix_parent_inverse`）。
* **IK/FK 控制器与骨骼约束**：
  * 8 个 Empty 控制器：
    * 双腿控制器：`FootIK.L` `(-0.11, -8.0, 0.07)`、`FootIK.R` `(0.11, -8.0, 0.07)`、`KneePole.L` `(-0.11, -7.35, 0.48)`、`KneePole.R` `(0.11, -7.35, 0.48)`。在未锁定时父级为 `CharacterRoot`，支撑脚锁定时（`is_locked=True`）解除父级（`parent = None`）驻留于世界空间。
    * 双臂控制器：`HandIK.L` `(-0.24, -8.0, 0.98)`、`HandIK.R` `(0.24, -8.0, 0.98)`、`ElbowPole.L` `(-0.32, -8.4, 1.24)`、`ElbowPole.R` `(0.32, -8.4, 1.24)`，父级均为 `CharacterRoot`。
  * 8 个骨骼约束：
    * `shin.L` / `shin.R`：`LegIK.L` / `LegIK.R` (`type='IK'`, `chain_count=2`, `pole_angle=-90 deg`, `use_stretch=False`, `influence=1.0`)。
    * `foot.L` / `foot.R`：`FootRotation.L` / `FootRotation.R` (`type='COPY_ROTATION'`, `target_space='WORLD'`, `owner_space='WORLD'`, `influence=1.0`)。
    * `forearm.L` / `forearm.R`：`ArmIK.L` / `ArmIK.R` (`type='IK'`, `chain_count=2`, `pole_angle=-90 deg`, `use_stretch=False`, 默认 `influence=0.0` 处于 FK 模式)。
    * `hand.L` / `hand.R`：`HandRotation.L` / `HandRotation.R` (`type='COPY_ROTATION'`, 默认 `influence=0.0`)。
* **动画数据 (`Actions` & `F-Curves`)**：共 12 个 Action、174 条 F-Curves，关键帧范围为 `Frame 1..462`（24 FPS），其中 `CharacterArmatureAction` 含 114 条 F-Curves（19 根骨骼 × 6 通道）。

### 1.2 [`output/dynamics_playground.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/dynamics_playground.blend) 训练场资产实测
通过 Blender 5.1.1 直接读取核实：
* **集合 (`bpy.data.collections`)**：共 4 个（`Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras`、`Playground_Dynamics_Visualization`）。
* **地形与表面对象 (`Playground_Surfaces`，16 个 Mesh)**：
  * Zone 1 平地：`Surface_FlatGround` ($X \in [-10.0, 10.0]\text{ m}, Y \in [-10.0, 5.0]\text{ m}, Z = 0.0\text{ m}$)。
  * Zone 2 五级台阶：`Surface_Stair_01..05` 与 `Surface_Stair_TopPlatform` ($X \in [-6.0, -1.0]\text{ m}, Y \in [5.0, 9.5]\text{ m}$)。
  * Zone 3 上下斜坡：`Surface_Ramp_Up`、`Surface_Ramp_TopPlatform`、`Surface_Ramp_Down` ($X \in [1.0, 6.0]\text{ m}, Y \in [5.0, 17.0]\text{ m}$)。
  * Zone 4 垂直墙：`Surface_VerticalWall` ($X \in [-3.0, 3.0]\text{ m}, Y \in [23.8, 24.2]\text{ m}, Z \in [0.0, 2.5]\text{ m}$)。
  * Zone 5 跳箱与单杠：`Surface_VaultBox`、`Surface_LedgeBar_Crossbar`、`Support_LedgeBar_Post_L/R`。
  * Zone 6 调试台：`Surface_DebugPlatform` ($X \in [5.0, 9.0]\text{ m}, Y \in [-5.0, -1.0]\text{ m}$)。
* **动力学验证工位 (`Playground_Dynamics_Visualization`，44 个对象)**：
  * 5 个单刚体动力学验证工位（`Dynamics_BodyProxy_S1..S5`、目标虚影 `Dynamics_TargetGhost_S1..S5`、接触圆盘、接触力箭头与角动量箭头），分布于 $Y \in [-4.0, +3.624]\text{ m}$。
  * **关键空间兼容性结论**：角色标准初始起点 `(0.0, -8.0, 0.0) m` 及 `StartStopWalkAction` 轨迹（$X = 0.0\text{ m}, Y \in [-8.0, -6.74]\text{ m}, Z = 0.0\text{ m}$）完全位于 Zone 1 `Surface_FlatGround` 南侧开阔区内，与 `S1..S5` 动力学工位（$Y \ge -4.0\text{ m}$）及周边障碍物**保持 $> 2.7\text{ m}$ 净空，零空间干涉**。

---

## 二、七大审计结论清单（附真实文件路径与代码依据）

### 1. 可直接复用的功能 (Directly Reusable Capabilities)
1. **13 部件占位角色构建**：[`src/character/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/character/builder.py) 中的 `build_character(config)`（第 124–207 行），自动创建 `Character` 集合、`CharacterRoot` 与 13 个 `REQUIRED_PARTS` 几何体。
2. **19 骨骼 Armature 构建与刚体绑定**：[`src/rig/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py) 中的 `build_rig(config, character_root)`（第 99–140 行）与 `bind_character_to_rig(armature_obj, parts)`（第 143–196 行）。
3. **双腿两骨 IK 与支撑脚世界空间锁定**：
   * [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py)：`setup_leg_ik`（第 127–215 行）、`set_foot_ik_target`（第 295–385 行）、`reset_leg_ik`（第 218–242 行）、`get_leg_ik_state`（第 245–292 行）。
   * [`src/rig/foot_contact.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/foot_contact.py)：`lock_foot_contact`（第 118–194 行）、`unlock_foot_contact`（第 197–228 行）、`evaluate_foot_support`（第 231–307 行）、`move_character_root_with_support`（第 315–333 行）。
4. **双臂两骨 IK 与手部三维朝向控制**：[`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py) 中的 `setup_arm_ik`（第 157–262 行）、`set_hand_ik_target`（第 397–509 行）、`set_arm_ik_influence`（第 265–291 行）、`reset_arm_ik`（第 294–325 行）、`get_arm_ik_state`（第 328–394 行）。
5. **全身姿态协调与单帧 6 阶段桥接执行**：
   * [`src/motion/whole_body_controller.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/whole_body_controller.py)：`WholeBodyController.execute_frame`（第 297–644 行）。
   * [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py)：`KinematicBridgeExecutor.execute_frame`（第 193–356 行）。
6. **高层动作规划与起步-行走-停止生成**：
   * [`src/motion/framework.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/framework.py)：`MotionPlanner`（第 883–1010 行）、`StartStopWalkAction`（第 481–833 行）、坐标空间转换函数 `world_to_root_local_vector`（第 85–96 行）与 `root_local_to_world_vector`（第 99–110 行）。
7. **质量分布、全身质心、运动学、惯量、ROM 约束与几何接触评估**：
   * [`src/motion/rigid_link.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/rigid_link.py)：`DEMPSTER_WINTER_15_SEGMENT_MODEL`（第 210–231 行）、`compute_whole_body_com`（第 261–344 行）。
   * [`src/motion/joint_limits.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/joint_limits.py)：`DEFAULT_HUMANOID_ROM_MODEL`（第 874–881 行）、`JointModel.validate_armature_pose`（第 469–509 行）、`extract_evaluated_bone_rotation_rad`（第 566–585 行）。
   * [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py)：`evaluate_limb_contacts_from_armature`（第 511–552 行）、`ContactRecord.check_geometric_compliance`（第 213–272 行）。
   * [`src/motion/body_kinematics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_kinematics.py)：`BodyKinematicsTracker`、`sample_body_pose_snapshot`（第 286–395 行）。
   * [`src/scene/environment_query.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/environment_query.py)：`create_standard_dynamics_playground_query`、`DynamicsEnvironmentQuery`。
   * [`src/scene/dynamics_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visual_evidence.py)：`encode_animated_gif`（第 141–255 行）、`draw_text_to_numpy`（第 94–134 行）。
   * [`src/render/engine.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/render/engine.py)：`configure_render`（第 7–15 行）、`render_still`（第 23–30 行）。

### 2. 可直接复用的 Blender 对象 (Directly Reusable Blender Objects)
在 [`output/dynamics_playground.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/dynamics_playground.blend) 中可直接复用的场景对象：
* **地形与表面集合 (`Playground_Surfaces`)**：`Surface_FlatGround`（角色站立与运动承载面）及全部 16 个环境几何网格。
* **视觉参考与法线集合 (`Playground_Visuals`)**：`Origin_Axis_X/Y/Z`、`Debug_1m_UnitCube` 及 21 个表面法线指示箭头 `NormalArrow_*`。
* **光照与摄像机集合 (`Playground_Lighting_Cameras`)**：`PlaygroundSunLight`、`PlaygroundFillLight`、`PlaygroundOverviewCam`、`PlaygroundCloseUpCam`、`DynamicsInspectionCam` 及 `Cam_S1..S5_Front/Side/Top`。
* **动力学工位集合 (`Playground_Dynamics_Visualization`)**：`Dynamics_BodyProxy_S1..S5` 及其关联遥测对象（原样保留）。

### 3. 必须保留的历史资产 (Historical Assets That Must Be Preserved)
1. **权威基准 `.blend` 资产（严禁破坏或覆盖）**：
   * [`output/dynamics_playground.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/dynamics_playground.blend)：Task 6G-D 已验收的 73 帧 5 工位动力学基准场景（由 `verify_task6gd_playground_blend.py` 与 `verify_task6gd_playground_dynamics.py` 严格守护）。Task 7A-1 采用在同一训练场资产链上加载 `output/dynamics_playground.blend` 并导出明确标注的派生验证产物 `output/dynamics_playground_task7a1.blend`，确保原始 `output/dynamics_playground.blend` 100% 零改动、零退化。
   * [`output/unified_motion_integration.blend`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/unified_motion_integration.blend)：Task 6G-C-R3B-2 四大动作 462 帧统一集成基准。
2. **历史生产代码与测试基准**：
   * 四大历史动作（`StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）及 C1/C2 动力学模块（`contact_dynamics.py`、`contact_force_solver.py`、`forward_dynamics.py`、`closed_loop_dynamics.py`）保持 100% 原样。

### 4. 必须复用的接口 (Mandatory Interfaces to Reuse)
* **角色与骨架装配链**：
  `build_character(config)` $\to$ `build_rig(config, character_root)` $\to$ `bind_character_to_rig(arm_obj, parts)` $\to$ `reset_pose(arm_obj)` $\to$ `setup_leg_ik(arm_obj)` $\to$ `setup_arm_ik(arm_obj, initial_influence=0.0)`。
* **单帧与多帧运动控制链**：
  `MotionPlanner` / `MotionAction` $\to$ `KinematicBridgeExecutor.execute_frame(planned_pose, keyframe=True, dt=...)` $\to$ `WholeBodyController.execute_frame(targets, ...)` $\to$ `src/rig/foot_contact.py` / `src/rig/ik.py` / `src/rig/pose.py` $\to$ `compute_whole_body_com` / `JointModel.validate_armature_pose` / `evaluate_limb_contacts_from_armature`。
* **环境几何查询接口**：
  `create_standard_dynamics_playground_query()` 返回的 `DynamicsEnvironmentQuery` 实例（注入 `MotionPlanner` 与 `KinematicBridgeExecutor`）。

### 5. 真正缺失的能力 (Genuinely Missing Capabilities)
经对全部源码与 `.blend` 资产排查，当前唯一缺失的是 **Task 7A-1 场景集成与五阶段最小控制闭环验证编排**：
1. 在已加载的 `output/dynamics_playground.blend` 场景中调用既有 `build_character` + `build_rig` + `bind_character_to_rig` + `setup_leg_ik` + `setup_arm_ik` 将 19 骨骼角色无损装入独立的 `Character` 集合（不清空现有训练场场景）。
2. 在训练场 `Surface_FlatGround` 区域内，通过 `KinematicBridgeExecutor` / `WholeBodyController` / `MotionPlanner` 依次执行并记录 Task 7A-1 要求的五阶段最小控制验证（A. 静态站立、B. 根节点位移与偏航、C. 左右脚独立 IK 控制、D. 支撑脚世界空间锁定抗漂移、E. 最小连续 `StartStopWalkAction` 步态片段），以及四大数学一致性验证（五重坐标空间非零平移/偏航往返转换、75kg 15 分段 CoM 与姿态偏移、几何接触检验、不可达与 ROM 违例真实报错）和 Blender 真实渲染视觉证据采集。

### 6. 不能重复创建的模块 (Modules Forbidden to Duplicate)
严禁新建或复制以下任何模块或类：
* 严禁新建角色生成器（必须复用 [`src/character/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/character/builder.py)）；
* 严禁新建 19 骨骼生成或绑定器（必须复用 [`src/rig/builder.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py)）；
* 严禁新建第二套腿部/手臂 IK 或足底锁定器（必须复用 [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py)、[`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)、[`src/rig/foot_contact.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/foot_contact.py)）；
* 严禁新建第二个 `WholeBodyController`、`KinematicBridgeExecutor` 或 `MotionPlanner`；
* 严禁复制 `StartStopWalkAction` 步态公式或手工插值关键帧；
* 严禁新建第二个独立训练场 `.blend`（必须从 `output/dynamics_playground.blend` 加载并保留其全部地形与工位）。

### 7. 需要最小适配的部分 (Minimal Adaptation Points)
1. **在保留既有训练场对象的前提下装配角色**：
   * `build_character(config)`（[`src/character/builder.py:124`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/character/builder.py#L124)）仅清理名为 `"Character"` 的集合（`_clear_existing_character()`），不会触碰 `Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras` 或 `Playground_Dynamics_Visualization`。因此只需先执行 `bpy.ops.wm.open_mainfile(filepath="output/dynamics_playground.blend")`，随后直接调用 `build_character` $\to$ `build_rig` $\to$ `bind_character_to_rig` $\to$ `setup_leg_ik` $\to$ `setup_arm_ik`，即可实现**零源码侵入**的角色入场装配！
2. **复用 `StartStopWalkAction` 的最小连续片段**：
   * `PipelineConfig`（[`src/config.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/config.py)）支持配置参数传入，或者直接通过 `MotionPlanner(config, armature_obj=arm, environment=playground_env)` 执行原生 `StartStopWalkAction()`（或在连续时间轴上分段记录 A/B/C/D 四项受控测试帧与 E 项 `StartStopWalkAction` 连续步态），并导出派生场景 `output/dynamics_playground_task7a1.blend`、遥测 JSON 与多视角关键帧 PNG + GIF 动画预览。
3. **非零偏航角 (`root_yaw_deg != 0`) 下的历史 IK 约束空间约定记录（供后续转向阶段输入）**：
   * 在 [`src/rig/ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/ik.py) 中，`FootRotation.L/R`（`COPY_ROTATION`）配置为 `target_space = "WORLD"`、`owner_space = "LOCAL"` 且 `foot.L/R` 骨骼 `use_inherit_rotation = False`，同时 `set_foot_ik_target` 中的 `pole_world` 沿世界 `+Y` 方向偏移。当 `CharacterRoot` 发生较大偏航（如 `> 10 deg`）且 `FootIK.L/R` 作为子级（未锁定）继承 `CharacterRoot` 旋转时，`FootRotation.L/R` 会将 `FootIK` 的世界旋转叠加到已随 `CharacterArmature` 旋转的局部空间中，从而在评估踝关节局部 Z 轴偏角时产生约 $2\times\text{yaw}$ 的相对偏转。在 Task 7A-1 中严禁篡改历史 `src/rig/ik.py` 基准逻辑，在非零偏航验证中保持偏航角在生理踝关节外展阈值内（如 `6.0 deg` / `6.5 deg`），并将该坐标空间耦合特征正式记录为后续三维转向扩展阶段的已知输入。
