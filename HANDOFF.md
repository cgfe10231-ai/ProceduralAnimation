# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-D-A（接触动力学基础与冲量动量系统）：交付纯数学模块 `src/motion/contact_dynamics.py`，建立 `SingleContactDynamics` 与 `MultiContactDynamics` 数据结构；实现世界空间接触点、接触力、质心位矢、接触力矩、线/角冲量与动量变化计算；严格区分力（N）、力矩（N*m）、冲量（N*s）、动量（kg*m/s）与质心/原点参考点；实现单侧法向 $F_n \ge 0$ 与库仑摩擦锥 $\|\mathbf{F}_t\| \le \mu F_n$ 约束校验；接口契约 100% 绑定标准训练场 `DynamicsEnvironmentQuery` 真实平地、斜坡与垂直墙几何参数；交付 `tests/verify_task6gd_contact_dynamics.py` 15 项数学与契约断言全绿；纳管注册 `tests/test_registry.py`；实测 quick 6/6、physics 11/11、motion 5/5 全绿通过。**零生产运动代码开发，严格停止等待用户下一步指示**。

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
* **完成 Task 6G-D-A 接触动力学基础与冲量动量系统**：
  * 构建纯数学接触动力学模块 `src/motion/contact_dynamics.py`；
  * 实现 `SingleContactDynamics` 与 `MultiContactDynamics`，支持接触力、质心力矩、线冲量、角冲量与动量变化；
  * 证明并验证 6 大数学定理（零力、质心力、偏心力、平移不变、旋转协变、冲量动量等价）；
  * 严格区分绕质心力矩/角动量与绕世界原点力矩/角动量；
  * 实现单侧法向力（$F_n \ge 0$）与库仑摩擦锥（$\|\mathbf{F}_t\| \le \mu F_n$）合规性校验；
  * 绑定标准训练场 `DynamicsEnvironmentQuery` 真实地表（平地、斜坡、垂直墙）法线与摩擦系数；
  * 交付纯 Python 测试套件 `tests/verify_task6gd_contact_dynamics.py`（15/15 项数学与契约断言全绿通过）；
  * 登记入 `tests/test_registry.py`，分层回归 `quick` (6/6), `physics` (11/11), `motion` (5/5) 全绿通过。

## 3. 已验证
* 单元测试与分层回归套件实测全绿：
  * `contact_dynamics_math`：15/15 项数学与契约定理全绿（0.12s，退出码 0）；
  * `dynamics_environment_query`：13/13 项数学定理全绿（0.11s，退出码 0）；
  * `dynamics_playground_blend`：45 个场景对象与材质完整性通过（1.28s，退出码 0，标定为 `AUTOMATED_PASS (Visual Inspection Required)`）；
  * `quick` Tier：6/6 项通过（8.13s，退出码 0）；
  * `physics` Tier：11/11 项通过（56.09s，退出码 0），历史物理模块 100% 零退化；
  * `motion` Tier：5/5 项通过（15.29s，退出码 0），历史步态 100% 零退化；
* 状态标定为：Task 6G-D-A 已完成并验证，严格停止。

## 4. 当前文件
* 核心测试系统：`tests/test_registry.py`、`tests/run_test_suite.py`、`run_tests.ps1`
* 测试输出报告：`tests/output/test_report.json`、`tests/output/test_report.md`
* 核心规范与门禁：`docs/ARCHITECTURE_CHANGE_GATE.md` (SSOT)、`docs/ENGINEERING_AUDIT.md`、`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md` (`[DEC-032]`)
* 规则文件：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`、`PROJECT_STATE.md`、`CHANGELOG.md`
* 核心源码：`src/motion/contact_dynamics.py`、`src/motion/framework.py`、`src/motion/kinematic_bridge.py`、`src/motion/whole_body_controller.py`、`src/scene/environment_query.py`、`src/scene/builder.py`
* 核心生成与产物：`output/dynamics_playground.blend`、`output/unified_motion_integration.blend`

## 5. 已知问题与未实现功能清单 (Unimplemented Features)
* 接触力求解器（根据全身加速度或外部扰动自动分配脚底 GRF 和接触反力）：尚未实现（Task 6G-D-B 规划）；
* 接触冲量与动力学平衡闭环（根据 GRF 冲量主动调节 CoM 加速度与动量）：尚未实现（Task 6G-D-C 规划）；
* 动态视觉验收（Blender 视口播放接触反力动画）：尚未进行（本轮为纯数学与接口契约基础）。

## 6. 下一步
* **严格停止，等待用户审阅并下达下一阶段指令（建议进入 Task 6G-D-B 接触力求解与分配）**。
* **严禁自动进入 Task 6G-D-B 或 6H**。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**。
* **严禁编写独立脚本拼凑动画冒充连续动作**。
* **严禁直接进入 Task 6G-D**。
