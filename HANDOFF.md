# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6G-C（多部位接触几何、约束与支撑状态系统），等待用户指示开启下一阶段（Task 6G-D 质心平衡、接触动量与简化接触动力学，或特技动作）。

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
* 完成多部位接触几何、约束与支撑状态系统（Task 6G-C）：
  * `src/motion/contact_model.py`：`ContactType`、`ContactLifecycle`、`SupportType`、`ContactRecord`、`GeometricConstraintResult`、`MultiContactState`、`EnvironmentalSurface`。
  * 接触类型区分：单向推力（UNILATERAL）、全向抓握（GRASP）与自由状态（FREE）。
  * 骨骼关节原点与身体接触局部锚点解耦（脚底偏置 $(0, 0.077, -0.070)\text{ m}$，手掌偏置 $(0, 0.050, -0.015)\text{ m}$）。
  * 环境物体刚体变换协变性（位置与外法线逆转置矩阵自动协变更新）。
  * 6 大多表面支撑状态拓扑分类（双脚支撑、单脚站立、手撑台面、蹬墙接触、抓杆悬垂、腾空飞跃）。
  * 共面 2D 凸包支撑多边形求解（物理免责声明：不代表 ZMP 或动态稳定性）。
  * `enrich_motion_state_with_contacts` 向后兼容 `ContactPointState`。
  * `tests/verify_task6gc_contact_model.py`：自动化验证套件（15 项测试全部通过）。
  * `run_contact_model_prototype.py`：生成独立视口验收工程 `output/contact_model_debug.blend`（144 KB）。
  * 录入 `[DEC-022]`。

## 3. 已验证
* 骨骼局部锚点到世界坐标变换绝对误差严格为 0.00e+00 m。
* 外法线单位化模长误差严格为 0.00e+00，且始终指向环境外侧。
* 单向推力（拉开间隙违规、下压穿透违规）与双向抓握（3D 偏移违规）严格区分。
* 6 种支撑状态准确分类与拓扑识别（含垂直墙面非共面拒绝虚假 2D 凸包与腾空 0 接触）。
* 量化几何误差分解精确（穿透误差 $4.47 \times 10^{-10}\text{ m}$，切向滑移误差 $4.77 \times 10^{-8}\text{ m}$）。
* 环境物体刚体旋转平移协变更新误差严格为 0.00e+00 m。
* WholeBodyController 与 MotionState 姿态完全兼容（末端追踪误差 $< 0.015\text{ mm}$）。
* 全量回归测试：Task 6G-B、6G-A、6F-D、6F-C、6F-B、6F-A 核心测试全部 100% 回归通过。
* 生成并实际验证 `output/contact_model_debug.blend` 文件存在且在 Blender 中正常播放。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_contact_model_prototype.py`、`run_arm_ik_prototype.py`、`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6gc_contact_model.py`、`verify_task6gb_body_inertia.py`、`verify_task6ga_body_kinematics.py`、`verify_task6fd_whole_body_controller.py` 等）
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

