# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6C（基于统一运动框架实现爆发式起步与加速冲刺），等待指示开启任务 6D 或后续运动动作编排（如冲刺急停、转向或跑跳越障衔接）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一物理世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现统一运动框架 `MotionState`、`MotionAction`、`MotionPlanner` 与 Blender 姿态适配层（Task 6A）。
* 实现程序化跑步模式 `RunAction`（含支撑相与腾空相，Task 6B）。
* 实现爆发式起步与加速冲刺 `SprintStartAction`（Task 6C）：静止蓄力 -> 前倾蹬地 -> 解析连续加速至 2.0 m/s -> 稳定冲刺，步长/步频/支撑腾空自适应。
* 保留动量继承向量 `(0.0, 2.0, 0.0) m/s`，验证经由 `MotionPlanner` 在任意起始帧平滑衔接后续动作。
* 输出原型 `output/character_sprint_start_prototype.blend`（114 帧）及 5 张关键预览图。
* 完成永久 Git 自动收尾规则设立与执行。

## 3. 已验证
* 速度与位移：速度从 0.0 平滑单调加速至 2.0000 m/s，114 帧总位移 6.5833 m。
* 步态自适应：步时 12->10 帧，步频 2.00->2.40 步/秒，支撑 9->4 帧，腾空 3->6 帧，步长 0.350->0.833 m。
* 接触与约束质量：支撑脚漂移 $\le 0.000024\text{ m}$，落点误差 $\le 0.000003\text{ m}$，腾空离地 $\ge +0.0240\text{ m}$，脚底最低 $Z = -0.000033\text{ m}$（无穿地）。
* 骨骼与姿态：双膝前屈偏移 $\ge +0.1414\text{ m}$（无反折），最大髋踝距 $0.82000\text{ m} \le 0.82\text{ m}$（0 IK 不可达，0 IK 钳制）。
* 回归测试：Task 6A、6B、5C 回归套件全部通过（退出码 0）。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`test_task3_spatial.py`、`verify_task3_blend.py`、`test_env.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 规则分级机制中，`.agents/rules/` 独立加载及外部新会话自动恢复状态按纪律保持为“未完整验证”。

## 6. 下一步
* 等待用户指示开启任务 4（程序化人形占位角色生成与骨骼装配基础）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
