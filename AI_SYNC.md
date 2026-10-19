# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6F-D（统一全身控制接口与最小协调器）
* **任务状态**：已验证（经 `tests/verify_task6fd_whole_body_controller.py` 10 项测试完整验证；Task 6F-C/6F-B/6F-A/6D 全部回归通过）
* **Git 状态**：
  * **当前分支**：`master`
  * **最新 Commit SHA**：待提交 (Pending commit)
  * **未提交文件**：Task 6F-D 源码、测试与必要文档更新

---

### 1. 本次新增/修改文件
* **核心模块与算法**：
  * `src/motion/whole_body_controller.py`：
    * 引入 `EndEffectorTarget`、`WholeBodyControlTargets`、`UnmetConstraint`、`EndEffectorFeedback`、`WholeBodyControlResult`。
    * 实现 `WholeBodyController`，严格复用现有 19 骨骼层级、双腿 IK、双臂 IK、ROM 模型与刚体质心计算。
    * 提供双手/双脚独立世界空间位置目标、手部独立 3D 欧拉朝向目标、肘/膝极向引导、根节点与骨盆多轴控制。
    * 提供毫米级位置与度级朝向可量化追踪误差反馈。
    * 真实物理达程与不可达性判定，超限目标真实上报 `REACHABILITY`。
    * 活动 IK 链解剖学 ROM 约束拦截（基于 `DEFAULT_HUMANOID_ROM_MODEL`），违规真实置 `success = False`，绝不静默放行。
    * 实时同步全身质心（`compute_whole_body_com`）。
  * `src/motion/__init__.py`（导出 whole_body_controller 接口）
* **自动化测试套件**：
  * `tests/verify_task6fd_whole_body_controller.py`：10 项严格自动化测试（双臂独立 IK、双脚独立 IK、四肢末端单帧同时控制、选择性禁用独立性、骨盆下蹲基座协调、手部位置与朝向解耦、控制器 ROM 校验一致性、不可达目标与 ROM 冲突真实截获、全身质心一致性、`WholeBodyDemoAction(MotionAction)` 连续 8 帧动作管线无缝接入）。
* **配置与文档**：
  * `DECISIONS.md`（新增 `[DEC-019]`）
  * `PROJECT_STATE.md`、`CHANGELOG.md`、`HANDOFF.md`、`AI_SYNC.md`

### 2. 核心实测指标
* **双臂独立控制**：左右手同时跟踪不同目标，位置误差分别为 $0.041\text{ mm}$ 与 $0.020\text{ mm}$，3D 朝向对齐误差严格为 **`0.000 deg`**。
* **双脚独立控制**：支撑脚接地误差 $0.003\text{ mm}$，空中摆动脚抬升误差 $0.029\text{ mm}$。
* **单帧四肢末端同时控制**：四肢（hand_L, hand_R, foot_L, foot_R）同时激活，各末端误差均 $< 0.05\text{ mm}$，全肢体处于物理达程内，ROM 0 违规。
* **选择性禁用独立性**：禁用左手（`enabled=False`）平滑回退至 FK 模式，完全不干扰右手与双脚（右手误差保持 $0.015\text{ mm}$）。
* **骨盆与基座协调不变性**：骨盆下蹲 $-0.06\text{ m}$（世界 $Z=0.8300\text{ m}$）并俯仰躯干，手脚世界绝对坐标目标精准保持（误差 $< 0.03\text{ mm}$）。
* **手部位置与 3D 朝向解耦**：腕部位置固定，手部在生理 ROM 内变动 3 组朝向，腕部漂移 $< 0.04\text{ mm}$，朝向对齐误差 $0.0000^\circ$。
* **ROM 校验一致性**：控制器内部 ROM 校验与独立 `JointModel` 校验完全一致（故意过弯脊柱，两者量化超限量严格相等：$20.00^\circ$）。
* **不可达与 ROM 冲突真实截获**：超出达程目标（$Y=-6.5\text{ m}$ 远超 $0.56\text{ m}$）真实报告 `REACHABILITY` 与 `ROM_VIOLATION`，`success = False`，杜绝虚假成功。
* **全身质心一致性**：控制器内部全身质心与 `rigid_link` 独立计算数值差异严格为 **`0.0000000000 m`**。
* **动作架构无缝接入**：`WholeBodyDemoAction(MotionAction)` 连续执行 8 帧，每帧生成合法 `MotionState` 并持久化 CoM 与追踪参数。
* **全量回归验证**：Task 6F-C 关节 ROM 测试、Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 全绿通过（退出码 `0`）。

### 3. 遗留问题与限制
1. 本次仅实现全身控制接口与最小协调器，不涉及动力学优化求解器、支撑多边形自动平衡恢复或高难度特技跑酷动作。

### 4. 下一步建议
* 等待用户指示后开启下一阶段任务（如支撑多边形与动态平衡补偿，或高难度特技动作跑跳 Running Jump、障碍撑越 Vault、急转弯 Sharp Turn）。

### 5. 是否需要用户批准
* **否**。
