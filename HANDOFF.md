# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-D-C1-B-R1（多帧动力学闭环三维重力统一、旋转反馈陀螺耦合修正与物理不可行性解耦准入门禁）：
1. 完整三维重力统一：扩展 `ContactWrenchTarget.from_target_motion` 支持传入 `gravity_acceleration_world: Optional[Vec3]`，使目标外力计算与前向动力学积分使用完全相同的 3D 重力向量，保持旧 `gravity_z` 调用兼容；
2. 修正旋转反馈中的世界坐标陀螺耦合：世界系完整刚体转动动力学为 $\frac{d\mathbf{L}}{dt} = I_{\text{world}} \boldsymbol{\alpha} + \boldsymbol{\omega} \times \mathbf{L}$。反馈角加速度 $\boldsymbol{\alpha}_{\text{fb}}$ 转换为力矩时正确计入陀螺力矩 $\boldsymbol{\tau}_{\text{gyro}} = \boldsymbol{\omega} \times \mathbf{L}$。无旋转反馈目标时严格保留纯前馈语义，避免陀螺项重复计入；
3. 解耦数值失败与物理不可行性准入门禁：
   - 数值失败（非法输入、NaN、积分崩溃）：严格保全原状态（失败原子性，`state_advanced = False`）；
   - 控制目标物理不可实现（如空中要求悬停）：不虚构受力，不把目标写成实际状态，真实物理受力（重力 + 零接触反力）确定时自然前向推进（`state_advanced = True`，标定为 `CONTROL_INFEASIBLE_PHYSICS_ADVANCED`），角色在空中自然受重力下落；保留 `strict_freeze_on_infeasible` 严格停止模式；
4. 接触几何与多帧仿真边界规范：明确 `ContactConstraintSpec` 为单帧即时输入，后续 Task 6G-D-C2 须接入环境查询与接触模型动态更新接触点与状态；
5. 交付 `tests/verify_task6gd_closed_loop_dynamics.py` 20 项测试全绿，分层回归 `quick` (9/9), `physics` (14/14) 100% 零退化。**零生产运动代码开发，严格停止等待用户下一步指示**。

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
* 完成刚体连杆惯性张量与全身角动量模型（Task 6G-B）。
* 完成多部位接触几何、约束与支撑状态系统（Task 6G-C）。
* 完成 Task 6G-C-R3A 系统架构深度审计与规范锁定。
* 完成 Task 6G-C-R3B-1 统一架构规范修订与最小兼容桥接层初版。
* 完成 Task 6G-C-R3B-1-Final 架构漏洞修补与 GitHub 自动化安全同步机制。
* 完成 Task 6G-C-R3B-2 历史四大动作向统一桥接层与全身控制架构无损迁移。
* 完成 Task 6G-C-R3B-2-R1 历史正确动画对照、视口下肢周期性 L 形畸变根因定位与修复（用户已目视验收通过）。
* 完成 Task 6G-D-PRE-P0 全工程架构审计与后续开发准备（交付 `docs/ENGINEERING_AUDIT.md`）。
* 完成 Task 6G-D-PRE-P1 统一测试执行接口、回归资产管理与永久架构门禁（交付 `docs/ARCHITECTURE_CHANGE_GATE.md`）。
* 完成 Task 6G-D-PRE-P1-R1 统一测试运行器严格验收修复与单元测试落地（交付 `tests/test_runner_unit.py` 10/10 单元测试）。
* 完成 Task 6G-D-PRE-P2 可视化动力学训练场与统一环境查询基础（交付 21 个表面与 `output/dynamics_playground.blend`）。
* 完成 Task 6G-D-PRE-P2-R1 环境查询过滤修复、距离语义统一与动力学训练场单一 SSOT 门禁。
* 完成 Task 6G-D-A 接触动力学基础与冲量动量系统（交付纯数学模块与 15 项数学几何测试）。
* 完成 Task 6G-D-A-R1 接触动力学时间步长一致性与物理接触有效性契约修复（交付 17 项测试与环境接触间隙门禁）。
* 完成 Task 6G-D-A-R2 MultiContactDynamics 时间步长更新原子性与状态不可变保全。
* 完成 Task 6G-D-B 多接触力逆向求解与约束分配系统。
* 完成 Task 6G-D-B-R1 接触力求解器数值可靠性与状态契约修复。
* 完成 Task 6G-D-B-R2 接触力求解器终止状态契约与优化收敛真值解耦。
* 完成 Task 6G-D-C1-A 前向动力学单步积分内核与刚体物理状态解耦。
* 完成 Task 6G-D-C1-A-R1 前向动力学状态不可变性防御性复制与非各向同性刚体二阶中点姿态积分修正。
* 完成 Task 6G-D-C1-B 多帧动力学闭环控制与状态反馈。
* **完成 Task 6G-D-C1-B-R1 完整三维重力统一、旋转反馈陀螺耦合修正与物理不可行性解耦准入门禁**：
  * 扩展 `ContactWrenchTarget.from_target_motion` 支持传入完整 3D 重力向量，保持旧 `gravity_z` 调用兼容；
  * 修正旋转反馈律计入世界系陀螺耦合力矩 $\boldsymbol{\tau}_{\text{gyro}} = \boldsymbol{\omega} \times \mathbf{L}$，无旋转反馈时保全纯前馈角动量语义；
  * 解耦数值失败与物理不可行性，空中无接触悬停需求自然受重力下落；
  * 交付 20 项场景测试全绿通过，分层回归 `quick` (9/9, 15.09s) 与 `physics` (14/14, 66.27s) 100% 零退化。

## 3. 已验证
* 单元测试与分层回归套件实测全绿：
  * `closed_loop_dynamics`：20/20 项闭环场景与数学测试全绿通过（纯 Python 6.50s，Blender 0.48s）；
  * `forward_dynamics`：22/22 项解析与状态测试全绿通过（纯 Python 0.009s，Blender 0.009s）；
  * `contact_force_solver`：38/38 项测试全绿通过（纯 Python 0.406s，Blender 0.087s）；
  * `contact_dynamics_math`：18/18 项数学与契约定理全绿（0.79s，退出码 0）；
  * `dynamics_environment_query`：13/13 项数学定理全绿（0.13s，退出码 0）；
  * `dynamics_playground_blend`：45 个场景对象与材质完整性通过（1.31s，退出码 0，标定为 `AUTOMATED_PASS (Visual Inspection Required)`）；
  * `quick` Tier：9/9 项通过（15.09s，退出码 0）；
  * `physics` Tier：14/14 项通过（66.27s，退出码 0），历史物理模块 100% 零退化；
* 状态标定为：Task 6G-D-C1-B-R1 已完成并验证，严格停止。

## 4. 当前文件
* 核心测试系统：`tests/test_registry.py`、`tests/run_test_suite.py`、`run_tests.ps1`
* 测试输出报告：`tests/output/test_report.json`、`tests/output/test_report.md`
* 核心规范与门禁：`docs/ARCHITECTURE_CHANGE_GATE.md` (SSOT)、`docs/ENGINEERING_AUDIT.md`、`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md` (`[DEC-040]`)
* 规则文件：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`、`PROJECT_STATE.md`、`CHANGELOG.md`
* 核心源码：`src/motion/closed_loop_dynamics.py`、`src/motion/forward_dynamics.py`、`src/motion/contact_force_solver.py`、`src/motion/contact_dynamics.py`、`src/motion/framework.py`、`src/motion/kinematic_bridge.py`、`src/motion/whole_body_controller.py`、`src/scene/environment_query.py`、`src/scene/builder.py`
* 核心生成与产物：`output/dynamics_playground.blend`、`output/unified_motion_integration.blend`

## 5. 已知问题与未实现功能清单 (Unimplemented Features)
* 连续步态动力学平衡（Task 6G-D-C2：步频、摆动腿着地点调整与双足动态行走的动力学耦合）；
* 动态视觉验收（Blender 视口播放接触反力动画与遥测箭头）：尚未进行（本轮为纯数学与多帧闭环基础）。

## 6. 下一步
* **严格停止，等待用户审阅并下达下一阶段指令（建议进入 Task 6G-D-C2 连续步态动力学平衡）**。
* **严禁自动进入 Task 6G-D-C2 或 6H**。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**。
* **严禁编写独立脚本拼凑动画冒充连续动作**。
* **严禁擅自进入 Task 6G-D-C2 或 6H**。
