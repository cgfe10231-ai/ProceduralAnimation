# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-C-R3B-1-Final（桥接层接口漏洞修补与永久 GitHub 自动同步），补齐动态时间步长校验、手部 IK 与接触语义彻底解耦、Phase 5 惯性张量与全身体角动量遥测闭环集成，经严苛测试（14/14 通过，含历史 6 大回归套件）验证，确立自动化 GitHub 安全同步推送协议。

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
* **完成 Task 6G-C-R3B-1-Final 架构漏洞修补与 GitHub 自动同步**：
  * 补齐 `dt` 动态支持与时间戳推导，单调递增时间保护，统一物理时间尺度；
  * 彻底解耦手部 IK 激活与接触语义，结合 `ContactModel` 校验几何合规性，消除自由空间伪造接触；
  * 足部地面锚点在局部坐标上依据踝关节原点 $(x, y, z - 0.070\text{ m})$ 精准对齐地面 $Z=0$，消除人工滑移；
  * 闭环集成 Phase 5 `compute_whole_body_inertia`，纯只读注入 `MotionState.params`；
  * 在规则中确立自动化 GitHub 安全同步协议（测试通过 -> 文档更新 -> commit -> auto `git push origin master` -> SHA 校验）；
  * 录入 `[DEC-026]`。

## 3. 已验证
* `tests/verify_task6gc_r3b1_bridge.py` 14/14 项测试全部通过：
  * 输入无损映射、FK/IK 仲裁、接地锚定保持、真实失败汇报、0.0000 mm 姿态定量等价、历史步态曲线不可变、类型单位规范、重复写杜绝、单帧 6 阶段流水线完整执行、变量 dt 物理缩放、手部 IK/接触解耦、全身体惯性与角动量遥测、历史 4 大动作规划完好、历史 6 大核心模块回归（WBC、Joint Limits、Rigid Link、Arm IK、Kinematics、Inertia）。
* 状态标定为：Task 6G-C-R3B-1-Final 已验证通过，远程自动推送完成，工作区干净，严格停止，等待用户指示。

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
* [DEC-026] 桥接层接口补全、多部位接触语义解耦与 GitHub 自动化安全同步机制 (Task 6G-C-R3B-1-Final)。
