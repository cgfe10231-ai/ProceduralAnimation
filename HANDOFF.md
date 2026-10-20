# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-C-R3B-1（统一架构规范修订与最小兼容桥接层），建立统一的单帧 6 阶段执行协议与无损桥接层，经严苛测试（10/10通过）验证 0.0000 mm 姿态等价性与历史步态曲线不可变性，为后续 Task 6G-C-R3B-2 历史动作无损迁移奠定统一骨干基石。

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
* **完成 Task 6G-C-R3B-1 统一架构规范修订与最小兼容桥接层**：
  * 修订 `ARCHITECTURE.md` (v2.1) 与 `ARCHITECTURE_SYNC.md` (v2.1)，锁定 10 大架构设计原则、三层架构演化视图、单帧 6-Phase 执行协议表与 12 大模块合同；
  * 同步永久规则 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`（阶段接入、防伪造、真实失败汇报）；
  * 实现最小兼容桥接层 `src/motion/kinematic_bridge.py`（`KinematicPlannedPose`、`convert_planned_pose_to_wbc_targets`、`KinematicBridgeExecutor`）；
  * 确立足部接地锁定由 `foot_contact.py` 独占世界空间管理、WBC 感知 `is_locked` 严禁解绑覆盖；
  * 确立手臂显式 FK/IK 仲裁机制；
  * 确立 ROM 与到达性真实校验，超限严格诚实返回 `success=False`；
  * 录入 `[DEC-025]`。

## 3. 已验证
* `tests/verify_task6gc_r3b1_bridge.py` 10/10 项测试全部通过：
  * 输入无损映射、FK/IK 仲裁、接地锚定保持、真实失败汇报、0.0000 mm 姿态定量等价、历史步态曲线不可变、类型单位规范、重复写杜绝、单帧 6 阶段流水线完整执行、历史 6 大核心模块回归（WBC、Joint Limits、Rigid Link、Arm IK、Kinematics、Inertia）。
* 状态标定为：Task 6G-C-R3B-1 已验证通过，工作区干净，等待进入 R3B-2。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`、`ARCHITECTURE_SYNC.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/motion/kinematic_bridge.py`、`src/motion/whole_body_controller.py` 等
* 测试套件：`tests/verify_task6gc_r3b1_bridge.py` 等

## 5. 已知问题
* 历史成熟动作（Walk/Run/Sprint/Brake）尚未迁移接入 `KinematicBridgeExecutor`（定于 R3B-2 开展）。
* 障碍物连续动作类尚未实现。
* 物理闭环未接入。

## 6. 下一步
* 进入 **Task 6G-C-R3B-2（历史动作向统一桥接层无损迁移）**。严禁跳入 Task 6G-D。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**。
* **严禁编写独立脚本拼凑动画冒充连续动作**。
* **严禁直接进入 Task 6G-D**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-024] 保持有效。
* [DEC-025] 统一架构规范修订与最小兼容桥接层 (Task 6G-C-R3B-1)。
