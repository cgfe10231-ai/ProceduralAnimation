# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标
完成任务 6F-C（关节自由度与生理活动范围 ROM 约束系统），等待用户指示开启下一阶段特技动作或系统集成。

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
* 完成关节自由度（DOF）与生理活动范围（ROM）约束系统（Task 6F-C）：
  * `src/motion/joint_limits.py`：`JointLimitSpec`、`JointModel`、`DEFAULT_HUMANOID_ROM_MODEL`。
  * 覆盖 17 根解剖骨骼（`root` 与 `pelvis` 明确解耦为浮动基座参考系）。
  * 支持 `BOX_EULER`、`ELLIPTICAL_CONE`（肩/髋复合摆动锥）、`HINGE_1D`（肘/膝反向折断硬锁定）。
  * 具备 $(-\pi, \pi]$ 环绕跳变防护、左右侧外展镜像对称支持。
  * 双轨非静默接口：`validate` 只读校验与 `clamp` 投影截断（报告详细违规与修正量）。
  * `tests/verify_task6fc_joint_limits.py`：自动化验证套件（10 项关键测试全部通过）。
  * 录入 `[DEC-018]`。

## 3. 已验证
* 中立站姿合规性：17 个解剖关节中立站姿 100% 合规（0 违规）。
* 边界容许性：合法生理姿态 100% 通过且修改量严格为 $0.00^\circ$。
* 违规精确检出：脊柱过屈、肘反折、膝向前弯折、肩过度外展精准定位，超限量误差 $\le 0.1^\circ$。
* 投影截断精度：超限角度准确投影至极限边界，二次校验 100% 合法，无静默篡改。
* 镜像对称处理：左右侧外展对称符号处理完全准确。
* 铰链防反折锁：膝关节向前弯折被截断至 $\le +2.0^\circ$；肘关节向后弯折被截断至 $\ge -2.0^\circ$。
* 复合锥面限位：肩关节复合摆动超限 $35.9^\circ$ 被椭圆锥平滑径向投影至合法包络面。
* 环绕保护：$365^\circ \rightarrow 10^\circ$ 合法通过，$270^\circ \rightarrow -90^\circ$ 准确检出越界，杜绝 $\pm 180^\circ$ 跳变。
* 骨骼几何恒定性：骨骼长度变化严格为 $0.000000\text{ m}$（0 变形拉伸）。
* 活跃 IK 兼容性：活跃双腿 IK（站立、抬腿）与活跃双手 IK（前向伸手）完全满足解剖学 ROM 约束。
* 现有能力回归：Task 6F-B、6F-A、6D 等回归测试均 100% 全绿通过。

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
