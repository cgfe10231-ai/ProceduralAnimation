# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6G-A（连续身体运动状态与速度学基础）
* **任务状态**：已验证（经 `tests/verify_task6ga_body_kinematics.py` 10 项测试完整验证；Task 6F-D/6F-C/6F-B/6F-A/6D 全部回归通过）
* **Git 状态**：
  * **当前分支**：`master`
  * **最新 Commit SHA**：`c55864c`
  * **未提交文件**：无（工作区干净，所有 Task 6G-A 源码、测试与文档已完整提交）

---

### 1. 本次新增/修改文件
* **核心模块与算法**：
  * `src/motion/body_kinematics.py`：
    * 建立 SO(3) 测地线最短路径四元数相对差分与同半球投影对齐（`relative_angular_velocity`），彻底消除欧拉角差分与跨 $\pm 180^\circ$ 边界突刺。
    * 建立单帧姿态快照结构 `BodyPoseSnapshot`，支持从 Armature（`sample_body_pose_snapshot`）或 `WholeBodyControlResult`（`sample_body_pose_from_controller_result`）采样包含世界根节点、CoM、15 刚体质量分段、17 解剖关节、4 四肢末端的世界/局部姿态。
    * 建立微分速度结构 `BodyVelocityState` 与综合运动状态 `BodyMotionState`。
    * 建立 `BodyKinematicsTracker`，支持在线逐帧采样更新与整段离散时间轴批处理微分（支持向后一阶差分与中心二阶差分）。
    * 提供 `enrich_motion_state_with_kinematics` 无缝注入现存 `MotionState.params`，100% 保持现有动作流与接口兼容。
  * `src/motion/__init__.py`（导出 body_kinematics 核心接口）
* **自动化测试套件**：
  * `tests/verify_task6ga_body_kinematics.py`：10 项严格自动化测试（静态微分零漂、纯平移线速度绝对对齐、单轴旋转空间角速度严格对齐、复合 3D 空间角速度精确计算、短测地线与 $\pm 180^\circ$ 环绕跳跃平滑消除、变时间步长 $\Delta t$ 尺度缩放不变性、单肢局部运动绝对隔离、全身质心动量守恒物理一致性、真实骨架 IK 姿态连续采样无 NaN/Inf、冲刺加速-制动急停过渡区连续速度与加速度注入）。
* **配置与文档**：
  * `DECISIONS.md`（新增 `[DEC-020]`）
  * `PROJECT_STATE.md`、`CHANGELOG.md`、`HANDOFF.md`、`AI_SYNC.md`

### 2. 核心实测指标
* **静态微分零速零漂**：$\Delta t = 0.041667\text{ s}$（24 FPS）静态下，根节点、CoM、15 刚体质量分段、17 解剖关节、4 四肢末端线速度与角速度严格全为 **`0.000000 m/s`** 与 **`0.000000 rad/s`**，零漂移。
* **纯平移线速度严格一致**：根节点 $+0.100\text{ m}$ 前向平移，导出线速度 $2.400000\text{ m/s}$（理论值 $2.400000\text{ m/s}$，误差 **`0.000000 m/s`**）；CoM 及全部 15 刚体分段线速度严格等于 $2.400000\text{ m/s}$，角速度全为 $0$。
* **单轴旋转空间角速度严格对齐**：根节点 $0.1\text{ s}$ 内绕 $Z$ 轴纯旋转 $30^\circ$，导出空间角速度 $\omega_z = 5.235988\text{ rad/s}$（$300.0000^\circ/\text{s}$），绝对误差严格 $< 3 \times 10^{-8}\text{ rad/s}$。
* **复合 3D 轴空间角速度精准计算**：绕归一化任意轴 $(0.577, 0.577, 0.577)$ 旋转 $45^\circ$，理论模长 $15.707963\text{ rad/s}$，导出模长 $15.707962\text{ rad/s}$，三维矢量误差严格 $< 1.5 \times 10^{-6}\text{ rad/s}$。
* **短测地线与 $\pm 180^\circ$ 环绕跳跃消除**：从 $+170^\circ$ 旋转至 $-170^\circ$（测地线角位移 $+20^\circ$），在 $\Delta t=0.1\text{ s}$ 下精确测得角速度 $3.490659\text{ rad/s}$（$200.0000^\circ/\text{s}$），误差严格为 **`0.000000 rad/s`**，彻底杜绝欧拉角微分的虚假高速突刺。
* **变时间步长 $\Delta t$ 尺度缩放严格线性**：在 $\Delta t \in [0.01, 0.041667, 0.1, 0.5]\text{ s}$ 任意步长下，导出速度与 $1/\Delta t$ 严格成反比，缩放误差为 **`0.000000 m/s`**。
* **单肢运动局部角速度绝对隔离**：仅右臂前臂肘屈 $45^\circ$，`forearm.R` 局部角速度精准测得 $18.750000\text{ rad/s}$（$1074.2959^\circ/\text{s}$），左臂、躯干、双腿等非子级关节角速度严格保持 **`0.000000 rad/s`**，零串扰零泄漏。
* **全身质心动量守恒物理一致性**：多肢体复合运动下，总动量求和 $\sum m_i v_i = 127.3276\text{ kg}\cdot\text{m/s}$ 与总质量质心动量 $M \cdot v_{\text{com}} = 127.3280\text{ kg}\cdot\text{m/s}$ 高度吻合，数值差异仅 $6.1 \times 10^{-6}\text{ m/s}$（$0.006\text{ mm/s}$），完全满足 Blender 32 位浮点累加容差（$< 10^{-5}\text{ m/s}$）。
* **真实骨架 IK 姿态连续采样**：与真实 Blender Armature 及 `WholeBodyController` 联调采样，完整提取根节点、15 分段、17 关节及 4 末端微分运动学特征，零 NaN、零 Inf。
* **动作边界速度加速度连续过渡与无缝注入**：冲刺加速与制动急停过渡区（Frame 20）速度平滑衍生，二阶加速度连续计算，通过 `enrich_motion_state_with_kinematics` 无缝注入 `MotionState.params`，完全向下兼容现有动作流。
* **全量回归验证**：Task 6F-D（10 项）、Task 6F-C（10 项）、Task 6F-B（8 项）、Task 6F-A（8 项）、Task 6D（冲刺急停原型验证）均 100% 全绿通过（退出码 `0`）。

### 3. 遗留问题与限制
1. 本次仅实现运动状态与微分速度学基础，不涉及支撑多边形与动态平衡补偿算法（留待 Task 6G-B）或动力学接触力求解。

### 4. 下一步建议
* 等待用户指示后开启 Task 6G-B（支撑多边形与动态平衡补偿），或高难度特技跑酷动作。

### 5. 是否需要用户批准
* **否**。
