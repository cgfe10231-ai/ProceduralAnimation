# CHANGELOG: 项目变更历史

所有条目必须严格遵循客观事实纪律，未经验证的不得标记为已验证。


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
