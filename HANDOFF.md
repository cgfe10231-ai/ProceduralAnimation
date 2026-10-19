# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6E（刚体连杆人体运动控制审计与最小架构设计），等待用户指示开启 Task 6F（最小刚体连杆控制层与双手 IK 原型实现）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一物理世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现统一运动框架 `MotionState`、`MotionAction`、`MotionPlanner` 与 Blender 姿态适配层（Task 6A）。
* 实现程序化跑步模式 `RunAction`（Task 6B）。
* 实现爆发式起步与冲刺加速 `SprintStartAction`（Task 6C）。
* 实现主动制动与急停 `SprintBrakeAction`（Task 6D）。
* 完成刚体连杆人体运动控制源码全面审计与最小架构设计（Task 6E）：
  * 审计 19 根骨骼几何/轴向/DOFs/限位缺失状态。
  * 梳理经验曲线依赖与手部世界空间目标缺失瓶颈。
  * 确定“物理约束辅助的程序化动画”技术路线。
  * 设计轻量级刚体连杆数据接口（连杆质量比率、质心 CoM、关节 ROM 限位、双手 IK）。
  * 制定 Task 6F 最小实现范围、测试标准与向后兼容策略。
* 录入 `[DEC-015]`，更新 `ARCHITECTURE.md` 第 4 节。

## 3. 已验证
* 审计事实核对：100% 以磁盘源码（`src/rig/builder.py`、`src/rig/ik.py`、`src/rig/foot_contact.py`、`src/motion/framework.py` 等）为依据，核准所有骨骼长度、层级、控制器及物理模型缺失现状。
* 现有能力回归：Task 6D、Task 6C、Task 6B、Task 5C 运行与验证能力完好无损。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6d_sprint_brake.py`、`verify_task6c_sprint_start.py`、`verify_task6b_run.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 6F（最小刚体连杆控制层与双手 IK 实现）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
