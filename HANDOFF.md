# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6F-B（刚体连杆、质量分布与全身质心计算），等待用户指示开启 Task 6F-C（各关节生理活动范围 ROM 限位保护与姿态平衡恢复辅助机制）。

## 2. 已完成
* 确认环境隔离（保护桌面无关 Unity 及实验报告等工程）。
* 建立统一物理世界坐标约定（$Z$ 轴向上，地表精准对齐 $Z=0.0\text{ m}$，单位米）。
* 实现统一运动框架 `MotionState`、`MotionAction`、`MotionPlanner` 与 Blender 姿态适配层（Task 6A）。
* 实现程序化跑步模式 `RunAction`（Task 6B）。
* 实现爆发式起步与冲刺加速 `SprintStartAction`（Task 6C）。
* 实现主动制动与急停 `SprintBrakeAction`（Task 6D）。
* 完成刚体连杆人体运动控制源码全面审计与最小架构设计（Task 6E）。
* 完成双臂独立 IK 与手部三维世界朝向控制系统（Task 6F-A）。
* 完成刚体连杆分段、质量分布模型与全身质心（CoM）计算（Task 6F-B）：
  * `src/motion/rigid_link.py`：`RigidSegmentSpec`、`BodyMassDistribution`、`compute_whole_body_com`。
  * 内置 Winter (2009) / Dempster (1955) 标准 15 分段模型与 13 几何分段合并模型，支持自定义质量重缩放与比例覆盖。
  * 前向运动学多坐标系计算（局部/骨架/世界），严格杜绝根节点二次变换（Zero Double-Transform）。
  * `tests/verify_task6fb_rigid_link.py`：自动化验证套件（8 项核心检验全数通过）。
  * 录入 `[DEC-017]`。

## 3. 已验证
* 质量守恒与合法性：15 分段与 13 分段模型质量比严格归一为 $1.000000$。
* 静态中立立姿质心高度：$Z = 1.047881\text{ m}$，占全身高 $1.82\text{ m}$ 的 $57.58\%$（解剖学黄金区间 $55\% \sim 58\%$），横向绝对对称误差严格为 $0.000000\text{ m}$。
* 独立数值验算精度：API 与独立分段加权和差异严格为 $0.0000000000\text{ m}$。
* 动态姿态敏感性：单臂前平举（$+90^\circ$）质心前移 $\Delta Y = +13.915\text{ mm}$、上抬 $\Delta Z = +13.915\text{ mm}$；单臂侧平举质心外展 $\Delta X = -13.915\text{ mm}$、上抬 $\Delta Z = +13.915\text{ mm}$。双臂不对称回归复原漂移严格为 $0.0000000000\text{ m}$。
* 主动 IK 兼容性：抬腿与双侧伸手姿态下质心正确响应（$\Delta Z = +29.07\text{ mm}$），骨骼变换矩阵零干扰。
* 零二次变换保证：骨盆下蹲 $-80\text{ mm}$ 全身质心实测下降 $-80.00\text{ mm}$；根节点平移 $(+2.5, +5.0, +0.3)\text{ m}$ 世界空间质心精确平移对应矢量，Armature 局部空间质心坐标完全不变（差异严格为 $0.0000000000\text{ m}$）。
* 现有能力回归：Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 全绿通过。

## 4. 当前文件
* 核心规则与交接：`GEMINI.md`、`AGENTS.md`、`.agents/rules/project_rules.md`、`AI_SYNC.md`、`HANDOFF.md`
* 规范与状态文档：`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`DECISIONS.md`、`PROJECT_STATE.md`、`CHANGELOG.md`、`README.md`
* 核心源码：`src/`（`config.py`、`pipeline.py`、`scene/`、`camera/`、`lighting/`、`render/`、`validation/`、`character/`、`rig/`、`motion/`）
* 管线入口：`run_sprint_brake_prototype.py`、`run_sprint_prototype.py`、`run_pipeline.py`、`run_pipeline.ps1`
* 测试套件：`tests/`（`verify_task6fb_rigid_link.py`、`verify_task6fa_arm_ik.py`、`verify_task6d_sprint_brake.py` 等）
* 运行产物：`output/`（受 `.gitignore` 忽略）

## 5. 已知问题
* 无代码阻碍。
* 终点附近场景存在圆柱体块，当前原型聚焦于平地动力学，未接入几何避障。

## 6. 下一步
* 等待用户指示开启 Task 6F-C（各关节生理活动范围 ROM 限位保护与姿态平衡恢复辅助机制）。

## 7. 禁止事项
* **严禁修改、删除或移动项目目录外的任何文件**。
* **严禁虚报测试结果**，严格执行 6 态划分。
* **以磁盘代码和实际测试结果为事实第一依据**，`HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要。
* **重大变更必须事先获得用户批准**。
* **禁止未经指示擅自开始制作角色或正式动画**。

## 8. 最近重要决策
* [DEC-001] ~ [DEC-009] 保持有效。
* [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制。
