# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6G-B（刚体连杆惯性张量与全身角动量模型），等待用户指示开启下一阶段（Task 6G-C/Task 7 支撑多边形与动态平衡补偿，或特技动作）。

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
* 完成连续身体运动状态与速度学基础（Task 6G-A）。
* 完成刚体连杆惯性张量与全身角动量模型（Task 6G-B）：
  * `src/motion/body_inertia.py`：`InertiaTensor`、`SegmentGeometrySpec`、`BodyInertiaModel`、`SegmentInertiaState`、`WholeBodyInertiaState`。
  * 15 刚体质量分段局部惯性张量（对称且正定），支持椭球体、圆柱体、椭圆柱体与长方体几何近似。
  * 3D 平行轴定理（Steiner's Theorem）统一合成全身相对于 CoM 的惯性张量。
  * 全身空间平移严格不变性与刚体旋转张量变换协变性（$\mathbf{Q} \mathbf{I} \mathbf{Q}^T$）。
  * 多连杆全身角动量解耦求和（自转 Spin 与轨道 Orbital 项）。
  * 刚性旋转下多连杆角动量严格等于单刚体解析解 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$（相对误差 $< 10^{-7}$）。
  * 四肢展开与紧收姿态偏航惯性差异比达 2.540 倍。
  * `enrich_motion_state_with_inertia` 无缝注入 `MotionState.params`。
  * `tests/verify_task6gb_body_inertia.py`：自动化验证套件（13 项测试全部通过）。
  * 录入 `[DEC-021]`。

## 3. 已验证
* 分段局部惯性张量对称且正定：15 分段主惯量全正（$0.00025 \sim 0.61690\text{ kg}\cdot\text{m}^2$）。
* 几何闭式公式绝对匹配：圆柱、椭球、椭圆柱、长方体公式误差 $< 3 \times 10^{-17}$。
* 3D 平行轴定理数值正确：与独立解析值误差仅 $4.77 \times 10^{-8}$。
* 空间平移不变性：位移 $(12.5, -45.0, 3.2)\text{ m}$，相对 CoM 惯性差 Frobenius 范数仅 $8.96 \times 10^{-6}\text{ kg}\cdot\text{m}^2$。
* 刚体旋转协变性：绕任意轴旋转 $40^\circ$，与 $\mathbf{Q} \mathbf{I} \mathbf{Q}^T$ 误差仅 $7.06 \times 10^{-6}\text{ kg}\cdot\text{m}^2$。
* 中立站姿对称合理：$I_{xy} = I_{xz} = 0.00000$，$I_{xx} = 13.46, I_{yy} = 14.21, I_{zz} = 1.08\text{ kg}\cdot\text{m}^2$。
* 单臂侧平举响应灵敏：$I_{zz}$ 增加 $+0.65442\text{ kg}\cdot\text{m}^2$（$+60.7\%$），$I_{xy} = 0.10313\text{ kg}\cdot\text{m}^2$。
* 四肢收展惯性比显著：展开 $2.403\text{ kg}\cdot\text{m}^2$ vs 收束 $0.946\text{ kg}\cdot\text{m}^2$，比值 $2.540$ 倍。
* 静止全身角动量严格为零：模长 $0.00000000\text{ kg}\cdot\text{m}^2/\text{s}$。
* 刚性旋转角动量一致性：与 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$ 误差仅 $1.07 \times 10^{-6}\text{ kg}\cdot\text{m}^2/\text{s}$。
* 四肢独立运动物理分解：Spin 与 Orbital 各自贡献清晰量化。
* 框架无损集成：CoM 误差 $0.00\text{ m}$，快照与骨架计算差异 $7.33 \times 10^{-7}\text{ kg}\cdot\text{m}^2$。
* 全量回归测试：Task 6G-A、6F-D、6F-C、6F-B、6F-A 及 6D 全部 100% 回归通过。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6gb_body_inertia.py`、`verify_task6ga_body_kinematics.py`、`verify_task6fd_whole_body_controller.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 6G-C（支撑多边形与动态平衡补偿）或高难度特技运动扩展。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-020] 保持有效。
* [DEC-021] 刚体连杆分段惯性张量与多连杆全身角动量模型架构规范。

