# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6F-A（双臂独立 IK 与世界空间控制），等待用户指示开启 Task 6F-B（刚体连杆动力学、质心 CoM 与关节 ROM 限位系统）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一物理世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现统一运动框架 `MotionState`、`MotionAction`、`MotionPlanner` 与 Blender 姿态适配层（Task 6A）。
* 实现程序化跑步模式 `RunAction`（Task 6B）。
* 实现爆发式起步与冲刺加速 `SprintStartAction`（Task 6C）。
* 实现主动制动与急停 `SprintBrakeAction`（Task 6D）。
* 完成刚体连杆人体运动控制源码全面审计与最小架构设计（Task 6E）。
* 完成双臂独立 IK 与手部三维世界朝向控制系统（Task 6F-A）：
  * `src/rig/arm_ik.py`：双臂两骨骼 IK、肘部极向控制、手部独立 3D 世界朝向控制、达程球面保护、FK 零侵入兼容。
  * `run_arm_ik_prototype.py`：生成独立交互式验收原型 `output/character_arm_ik_prototype.blend`（216 帧，带 4 彩色标记与专属机位）。
  * `tests/verify_task6fa_arm_ik.py`、`tests/verify_task6fa_visual_prototype.py`：自动化验证套件。
  * 录入 `[DEC-016]`。

## 3. 已验证
* 双臂到达精度：左右手各 5 处可达空间目标位置误差均 $\le 0.051\text{ mm}$（规格 $\le 1\text{ mm}$）。
* 骨骼连杆长度：上臂严格为 $0.3000\text{ m}$、前臂严格为 $0.2600\text{ m}$，零异常伸缩。
* 双侧独立性：双臂同时指定不同目标零冲突，对侧腕部漂移严格为 **`0.00000000 m`**。
* 手部朝向解耦：手部 3D 朝向对齐误差 **`0.0000^\circ`**，腕部伴生漂移 $\le 0.025\text{ mm}$。
* 肘部极向偏转：极向引导肘部偏转位移达 **`19.31 cm`**，腕部零漂移（$\le 0.005\text{ mm}$）。
* 超达程保护：超限时安全投影至 0.5600m，骨骼零拉长。
* 可视化验收原型：`output/character_arm_ik_prototype.blend` 直接重开验证通过，时间轴 1..216 帧，5 阶段动作流畅，0 关节翻转。
* 现有能力回归：Task 6D、Task 6C、Task 6B、Task 5C、Task 4C 自动化测试全绿通过。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6fa_arm_ik.py`、`verify_task6d_sprint_brake.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 6F-B（刚体连杆动力学、质心 CoM 与关节 ROM 限位系统）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
