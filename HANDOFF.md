# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6G-A（连续身体运动状态与速度学基础），等待用户指示开启下一阶段（Task 6G-B 支撑多边形与动态平衡补偿，或特技动作）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一物理世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现统一运动框架 `MotionState`、`MotionAction`、`MotionPlanner` 与 Blender 姿态适配层（Task 6A）。
* 实现程序化跑步模式 `RunAction`（Task 6B）。
* 实现爆发式起步与冲刺加速 `SprintStartAction`（Task 6C）。
* 实现主动制动与急停 `SprintBrakeAction`（Task 6D）。
* 完成刚体连杆人体运动控制源码全面审计与最小架构设计（Task 6E）。
* 完成双臂独立 IK 与手部三维世界朝向控制系统（Task 6F-A）。
* 完成刚体连杆分段、质量分布模型与全身质心（CoM）计算（Task 6F-B）。
* 完成关节自由度（DOF）与生理活动范围（ROM）约束系统（Task 6F-C）。
* 完成统一全身控制接口与最小协调器（Task 6F-D）。
* 完成连续身体运动状态与速度学基础（Task 6G-A）：
  * `src/motion/body_kinematics.py`：`BodyPoseSnapshot`、`BodyVelocityState`、`BodyMotionState`、`BodyKinematicsTracker`。
  * 根节点空间线/角速度矢量（rad/s 与 deg/s）、全身 CoM 线速度。
  * 15 刚体质量分段世界 CoM 位置与空间线/角速度。
  * 17 解剖关节相对父骨骼局部朝向四元数与局部角速度（rad/s 与 deg/s）。
  * 4 四肢末端世界空间位置与线速度。
  * SO(3) 测地线最短路径四元数差分与同半球投影对齐，彻底消除 $\pm 180^\circ$ 虚假突刺。
  * 显式时间步长 $\Delta t$ 参数化，严格线性尺度不变性。
  * `enrich_motion_state_with_kinematics` 无缝注入 `MotionState.params`，100% 保持现有动作流与接口兼容。
  * `tests/verify_task6ga_body_kinematics.py`：自动化验证套件（10 项测试全部通过）。
  * 录入 `[DEC-020]`。

## 3. 已验证
* 静态微分零速零漂：$\Delta t = 0.041667\text{ s}$ 静态下所有线速度与角速度严格全为 $0.000000\text{ m/s}$ 与 $0.000000\text{ rad/s}$。
* 纯平移线速度严格一致：根节点 $+0.100\text{ m}$ 平移，导出线速度 $2.400000\text{ m/s}$（误差 $0.000000\text{ m/s}$），分段及 CoM 线速度完全一致。
* 单轴旋转角速度对齐：$0.1\text{ s}$ 内绕 $Z$ 旋转 $30^\circ$，导出 $\omega_z = 5.235988\text{ rad/s}$（$300.0000^\circ/\text{s}$），误差 $< 3 \times 10^{-8}\text{ rad/s}$。
* 复合 3D 轴角速度精准：绕任意轴旋转 $45^\circ$，理论模长 $15.707963\text{ rad/s}$，矢量误差 $< 1.5 \times 10^{-6}\text{ rad/s}$。
* 测地线最短路径消除环绕突变：$+170^\circ \rightarrow -170^\circ$ 测地线转动 $20^\circ$，精准导出 $3.490659\text{ rad/s}$（$200^\circ/\text{s}$），误差 $0.000000\text{ rad/s}$。
* 变 $\Delta t$ 尺度不变性：$\Delta t \in [0.01, 0.5]\text{ s}$ 下导出速度与 $1/\Delta t$ 严格成反比，误差 $0.000000\text{ m/s}$。
* 单肢局部运动绝对隔离：仅右臂屈肘 $45^\circ$，局部角速度 $18.750000\text{ rad/s}$，其余非子级关节严格全为 $0.000000\text{ rad/s}$。
* 全身质心动量守恒物理一致性：总动量求和与总质量质心动量吻合，差异仅 $6.1 \times 10^{-6}\text{ m/s}$（$< 10^{-5}\text{ m/s}$ 浮点容差）。
* 真实骨架 IK 姿态连续采样：联调 Blender Armature 与 `WholeBodyController`，无 NaN、无 Inf。
* 动作过渡平滑与无缝注入：加速-制动过渡区连续二阶加速度计算，无缝接入 `MotionState.params`。
* 全量回归验证：Task 6F-D、6F-C、6F-B、6F-A、6D 全部 100% 回归通过。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6ga_body_kinematics.py`、`verify_task6fd_whole_body_controller.py`、`verify_task6fc_joint_limits.py`、`verify_task6fb_rigid_link.py`、`verify_task6fa_arm_ik.py`、`verify_task6d_sprint_brake.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 6G-B（支撑多边形与动态平衡补偿）或高难度特技运动扩展。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-019] 保持有效。
* [DEC-020] 连续身体运动状态与速度学微分计算架构规范。
