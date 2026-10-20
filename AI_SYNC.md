# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6G-C-R3A（系统架构深度审计与规范锁定阶段）
* **任务状态**：已验证（全仓库代码审计完成，建立 ARCHITECTURE.md v2.0，创建 ARCHITECTURE_SYNC.md 永久卡片，同步永久项目规则，回答 6 大物理数学模块代码级质询，锁定架构规范；等待用户确认后进入 R3B 执行合流修复）
* **Git 状态**：
  * **当前分支**：`master`
  * **审计依据基准 Commit SHA**：`8582bc3` (对应文档更新 `4111a51`)
  * **本任务提交 Commit SHA**：待自动收尾提交后回填
  * **未提交文件**：无遗留未受控代码或脚本

---

### 1. R3A 架构审计核心结论
* **查清三套分立管线现实**：
  1. 历史动作管线（`StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction`）：使用私有姿态函数与 `ContactConstraintAdapter` 直接驱动骨架，未接入 `WholeBodyController`。
  2. 物理分析与全身控制工具链（`WholeBodyController`、`JointModel`、`rigid_link`、`body_kinematics`、`body_inertia`、`contact_model`）：作为事后只读遥测存在，未被历史动作调用，无物理闭环。
  3. 演示原型脚本（`run_contact_obstacle_integration.py`）：脱离动作系统，通过在 30 帧循环中重复执行完全相同的静态目标硬编码摆拍，导致画面呈现僵硬切片。
* **物理数学模块定位**：
  * 系统当前是严格的“开环解析运动学驱动 + 事后只读物理遥测”。
  * `rigid_link.py`（CoM）、`body_kinematics.py`（速度/加速度）、`body_inertia.py`（惯性张量/角动量）、`contact_model.py`（接触几何/支撑分类）均为只读数据采集，无力矩驱动、姿态修正或平衡闭环。
* **更新权威文档与规则**：
  * 更新 `ARCHITECTURE.md` (v2.0)，确立统一世界坐标系、两套架构图、11 大模块合同、6 大历史动作复用表及 4 大架构断裂点。
  * 创建永久架构同步卡片 `ARCHITECTURE_SYNC.md`（包含 12 项必填章节）。
  * 同步更新 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`，新增第 8 节“架构对齐与防伪造纪律”。

---

### 2. 6 大物理数学模块真实调用事实清单
1. **`rigid_link.py` (CoM)**：未被任何动作调用，仅被 `whole_body_controller`、`body_kinematics`、`body_inertia` 事后读取，纯只读指标。
2. **`body_kinematics.py` (速度学)**：输入为已评估的骨架姿态快照，输出有限差分速度，仅写入 `MotionState.params`，不驱动骨骼。
3. **`body_inertia.py` (惯性/角动量)**：仅在测试中被调用，无转动力矩，无阻尼修正，与当前动画无因果驱动关系。
4. **`contact_model.py` (接触几何)**：只读检测四肢与环境间隙及支撑分类，不改变 IK 目标位置，未与 `foot_contact.py` 接地锁定打通。
5. **`WholeBodyController`**：未被任何生产级 `MotionAction` 调用；仅被独立原型脚本与测试脚本调用。
6. **物理闭环状态**：不存在双向力学/姿态反馈闭环，系统为纯单向只读数据流。

---

### 3. 下一步建议与禁止事项
* **下一步**：等待用户指令进入 **Task 6G-C-R3B（架构合流与连续运动修复）**。
* **禁止事项**：
  * 严禁跳入 Task 6G-D。
  * 严禁在 R3A 阶段编写新动作算法或修改 rig。
  * 严禁编写独立脚本拼凑动画冒充连续动作。
