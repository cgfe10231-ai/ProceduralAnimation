# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6F-D（统一全身控制接口与最小协调器），等待用户指示开启下一阶段特技动作或系统集成。

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
* 完成统一全身控制接口与最小协调器（Task 6F-D）：
  * `src/motion/whole_body_controller.py`：`EndEffectorTarget`、`WholeBodyControlTargets`、`WholeBodyController`、`WholeBodyControlResult`。
  * 四肢末端（双手双脚）、浮动骨盆、躯干 FK 姿态及空间根节点原子化统一控制。
  * 真实反馈：毫米级位置追踪误差、度级朝向误差、达程真实评估与违规上报。
  * 实时全身质心同步与活动姿态 17 关节解剖学 ROM 约束拦截。
  * `WholeBodyDemoAction(MotionAction)` 证明能够无缝嵌入标准动画动作管线。
  * `tests/verify_task6fd_whole_body_controller.py`：自动化验证套件（10 项测试全部通过）。
  * 录入 `[DEC-019]`。

## 3. 已验证
* 双臂独立控制：左右手独立目标跟踪，误差 $< 0.045\text{ mm}$，朝向对齐误差严格为 $0.000^\circ$。
* 双脚独立控制：支撑脚接地误差 $0.003\text{ mm}$，空中摆动脚抬升误差 $0.029\text{ mm}$。
* 单帧四肢末端同时控制：hand_L, hand_R, foot_L, foot_R 同时激活，误差 $< 0.05\text{ mm}$，ROM 0 违规。
* 选择性禁用独立性：禁用单末端平滑回退至 FK 模式，完全不干扰其他肢体追踪。
* 骨盆与基座协调：骨盆下蹲（$Z=0.83\text{ m}$）并俯仰躯干，末端世界绝对坐标目标稳定保持（误差 $< 0.03\text{ mm}$）。
* 手部位置与 3D 朝向解耦：腕部位置固定，手部变动 3 组朝向，腕部漂移 $< 0.04\text{ mm}$，朝向误差 $0.0000^\circ$。
* ROM 校验一致性：控制器内部 ROM 校验与独立 `JointModel` 校验完全一致（超限量严格为 $20.00^\circ$）。
* 真实冲突截获：不可达目标与 ROM 冲突 100% 真实截获，`success = False`，零虚假放行。
* 全身质心一致性：控制器内部全身质心与 `rigid_link` 独立计算数值差异严格为 $0.0000000000\text{ m}$。
* 动作管线无缝接入：`WholeBodyDemoAction(MotionAction)` 连续执行 8 帧，每帧生成合法 `MotionState` 并持久化参数。
* 现有能力全量回归：Task 6F-C、6F-B、6F-A、6D 等回归测试均 100% 全绿通过。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6fc_joint_limits.py`、`verify_task6fb_rigid_link.py`、`verify_task6fa_arm_ik.py`、`verify_task6d_sprint_brake.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 7 或高难度特技运动扩展（如跑跳 Running Jump、障碍撑越 Vault 或急转弯 Sharp Turn）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
