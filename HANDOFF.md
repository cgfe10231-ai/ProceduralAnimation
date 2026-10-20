# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成 Task 6G-C-R3A（系统架构深度审计与规范锁定阶段），全面梳理当前仓库分立管线、只读遥测本质及障碍物僵硬成因，锁定目标生产架构与模块调用合同，等待用户指示进入 Task 6G-C-R3B 执行架构合流与连续运动修复。

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
* **完成 Task 6G-C-R3A 系统架构深度审计与规范锁定**：
  * 全面审计全部源码，查清当前真实存在的三套分立管线；
  * 证明物理数学模块（CoM、速度追踪器、惯性张量、角动量、接触模型）均为事后只读遥测，无闭环平衡控制；
  * 证明 `WholeBodyController` 未被历史成熟动作调用；
  * 查明 `run_contact_obstacle_integration.py` 呈现 30 帧僵硬切片的根因是缺乏障碍物 `MotionAction`、在循环中对完全相同静态目标重复 `execute_frame`；
  * 更新权威 `ARCHITECTURE.md` (v2.0)；
  * 创建永久架构同步卡片 `ARCHITECTURE_SYNC.md`（12 项必填章节）；
  * 更新永久规则 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`（新增第 8 节架构对齐与防伪造纪律）；
  * 录入 `[DEC-024]`。

## 3. 已验证
* 架构审计结论经磁盘源码全文搜索严格核实，无任何虚假推断。
* 权威架构文档、架构同步卡片与三大规则文件已就位并相互一致。
* 历史全量测试套件（Task 6G-C 17 项测试、6G-B 13 项、6G-A 10 项、6F-D 10 项）保持全绿。
* 状态标定为：Task 6G-C-R3A 架构审计完成，等待 R3B 集成修复。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`、`ARCHITECTURE_SYNC.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_contact_walk_integration.py`、`run_contact_obstacle_integration.py`、`run_contact_model_prototype.py` 等
* 测试套件：`tests/`（`verify_task6gc_contact_model.py`、`verify_task6gb_body_inertia.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 控制器双轨制：历史动作未接入 `WholeBodyController`。
* 接触模型脱节：`contact_model.py` 未与 `foot_contact.py` 接地锁定打通。
* 障碍物动作缺失：系统中尚未实现针对障碍物交互的 `MotionAction` 连续动作类。
* 物理无闭环：CoM 与角动量均为只读遥测。

## 6. 下一步
* 等待用户指示开启 Task 6G-C-R3B（架构合流与连续运动修复）。严禁跳入 Task 6G-D。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**。
* **严禁编写独立脚本拼凑动画冒充连续动作**。
* **严禁在 R3A 阶段编写新动作或修改 rig**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-023] 保持有效。
* [DEC-024] 系统架构合流基准与反伪造工程纪律 (Task 6G-C-R3A)。
