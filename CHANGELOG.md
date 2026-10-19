# CHANGELOG: 项目变更历史

所有条目必须严格遵循客观事实纪律，未经验证的不得标记为已验证。

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
