# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-D-PRE-P2-R1（环境查询过滤修复、距离语义统一与动力学训练场单一 SSOT 门禁）：修复 `query_surface_at_point()` 中 `surface_type_filter` 未约束默认地面的缺陷；统一 `signed_distance` 物理语义并将射线命中距离解耦表示为 `ray_hit_distance`；将 `output/dynamics_playground.blend` 确立为 Task 6G-D/6H/7A 统一标准训练场并增补 ACG 规范与十大绝对清规；新增 `test_12` 与 `test_13` 测试扩充至 13 项纯 Python 数学断言全绿；实测 quick 5/5、motion 5/5、playground_blend 1/1 全绿通过。**零生产运动代码开发，严格停止等待用户下一步指示**。

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
* **完成 Task 6G-D-PRE-P2 可视化动力学训练场与统一环境查询基础**：
  * 构建纯 Python 解析几何与环境查询系统 `src/scene/environment_query.py`，支持 21 个闭式解析表面；
  * 支持 6 大标准分区：平坦地面、5级标准台阶、上下连续斜坡、垂直障碍墙、跳箱与单杠、遥测调试区；
  * 支持有符号距离（Signed Distance，间隙 >0，穿透 <0）、外向单位法线、表面边界欧几里得距离与垂直墙面定向查询；
  * 保持对 `EnvironmentQuery` 的 100% 向后兼容性（`ground_height_at` 与 `surface_normal_at` 契约无损）；
  * 升级场景生成器 `src/scene/builder.py` 与入口 `run_dynamics_playground.py`，生成 `output/dynamics_playground.blend`；
  * 配备 21 个表面法线指示箭头、世界坐标系红绿蓝指示轴、1m 参考立方体、双视角调试摄像机与日光系统；
  * 交付纯 Python 几何测试 `tests/verify_task6gd_dynamics_playground.py` 与 Blender 场景检验脚本 `tests/verify_task6gd_playground_blend.py`，注册进入测试表。
* **完成 Task 6G-D-PRE-P2-R1 环境查询过滤修复、距离语义统一与动力学训练场单一 SSOT 门禁**：
  * 修复 `query_surface_at_point` 与 `query_spatial_surface` 中 `surface_type_filter` 过滤非水平地表时误中默认全局平地的逻辑漏洞；
  * 解耦 `ray_hit_distance`（欧几里得射线行进距离）与 `signed_distance`（法向有符号距离），实现对斜向与背面射线的严格物理距离刻画；
  * 确立 `output/dynamics_playground.blend` 为 6G-D、6H、7A 单一标准训练场（SSOT），禁止私造分立场景，禁止手工摆设虚假力学箭头，写入 ACG 权威门禁；
  * 修订 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md`，确立十大绝对清规；
  * 扩充 `tests/verify_task6gd_dynamics_playground.py`（13/13 项纯 Python 数学断言全绿通过）；
  * 执行 `quick` (5/5) 与 `motion` (5/5) 分层回归全绿通过，历史动作 100% 零退化。

## 3. 已验证
* 单元测试与分层回归套件实测全绿：
  * `dynamics_environment_query`：13/13 项数学定理全绿（0.001s，退出码 0）；
  * `dynamics_playground_blend`：45 个场景对象与材质完整性通过（1.31s，退出码 0，标定为 `AUTOMATED_PASS (Visual Inspection Required)`）；
  * `runner_unit_tests`：10/10 项测试全绿（1.05s，退出码 0）；
  * `quick` Tier：5/5 项通过（5.11s，退出码 0）；
  * `motion` Tier：5/5 项通过（15.81s，退出码 0），历史步态 100% 零退化；
* 状态标定为：Task 6G-D-PRE-P2-R1 已完成并验证，严格停止。

## 4. 当前文件
* 核心测试系统：`tests/test_registry.py`、`tests/run_test_suite.py`、`run_tests.ps1`
* 测试输出报告：`tests/output/test_report.json`、`tests/output/test_report.md`
* 核心规范与门禁：`docs/ARCHITECTURE_CHANGE_GATE.md` (SSOT)、`docs/ENGINEERING_AUDIT.md`、`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md` (`[DEC-031]`)
* 规则文件：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`、`PROJECT_STATE.md`、`CHANGELOG.md`
* 核心源码：`src/motion/framework.py`、`src/motion/kinematic_bridge.py`、`src/motion/whole_body_controller.py`、`src/scene/environment_query.py`、`src/scene/builder.py`
* 核心生成与产物：`output/dynamics_playground.blend`、`output/unified_motion_integration.blend`

## 5. 已知问题与限制
* 动力学遥测目前为纯只读开环，未接入受力闭环控制（留待 Task 6G-D 规划）。

## 6. 下一步
* **严格停止，等待用户审阅并下达下一阶段指令（建议进入 Task 6G-D-A 接触力与动力学平衡闭环）**。
* **严禁自动进入 Task 6G-D-A**。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**。
* **严禁编写独立脚本拼凑动画冒充连续动作**。
* **严禁直接进入 Task 6G-D**。
