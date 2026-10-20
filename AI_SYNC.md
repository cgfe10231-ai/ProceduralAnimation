# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6G-C-R3B-1（统一架构规范修订与最小兼容桥接层）
* **任务状态**：已验证（权威架构修订至 v2.1，完成最小兼容桥接层 `kinematic_bridge.py`，实现足部接地锁定独占性与手臂 FK/IK 仲裁，10 项严苛验证 100% 通过，0.0000 mm 姿态等价性与历史步态曲线不可变性全量核验通过，历史 6 大核心测试 100% 全绿）
* **Git 状态**：
  * **当前分支**：`master`
  * **基准 Commit SHA**：`d283ba8`
  * **本任务提交 Commit SHA**：`892116c`
  * **未提交文件**：无

---

### 1. R3B-1 架构修订与桥接层核心成果
* **权威架构规范锁定 (ARCHITECTURE.md v2.1 & ARCHITECTURE_SYNC.md v2.1)**：
  * 确立 10 大架构设计原则、三层架构演化视图（现状断裂点 -> R3B 统一桥接落地 -> 未来 6G-D/6H/7A 物理平衡闭环）；
  * 确立单帧 6 阶段执行协议表（Phase 1 规划 -> Phase 2 接触防滑锁定 -> Phase 3 WBC 统一求解 -> Phase 4 真实 ROM 校验 -> Phase 5 事后只读遥测丰富 -> Phase 6 状态提交）；
  * 梳理 12 大核心模块契约表与 6 大历史动作复用矩阵；
  * 同步永久规则 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`，确立防伪造与阶段接入纪律。
* **实现最小兼容桥接层 (`src/motion/kinematic_bridge.py`)**：
  * `KinematicPlannedPose`：结构化输入容器，包含根节点、骨盆位姿、躯干 FK、足部目标与锁定标记、手部 IK/FK 目标；
  * `convert_planned_pose_to_wbc_targets`：手部 FK/IK 显式仲裁，足部接地锁定标记无损转发；
  * `KinematicBridgeExecutor`：严格编排 6-Phase 生命周期，统筹 `foot_contact` 接地世界锚定锁定、`WholeBodyController` 独占姿态求解、`JointModel` ROM 与到达性诚实验证、事后只读物理遥测丰富（CoM、速度、惯性张量、角动量、接触模型）及 `MotionState` 状态提交。
* **所有权与防冲突纪律**：
  * 足部接地防滑锁定由 `src/rig/foot_contact.py` 独占世界空间管理；WBC 在求解时感知 `is_locked`，严禁解绑或破坏锁定状态。
  * 手部显式仲裁：`enabled=False` 时 arm IK 约束 influence 归零，由 FK 关节角完全主导；`enabled=True` 时 arm IK 接管，保证双臂摆动与抓握各得其所。
  * 真实失败汇报机制：ROM 截断后重新评估末端到达性，若发生超限或 ROM 违背，`execute_frame` 严格诚实汇报 `success=False`，绝对禁止伪造通过。

---

### 2. 验证结果清单 (`tests/verify_task6gc_r3b1_bridge.py` 10/10 全绿)
1. **Test 01: Lossless Input Mapping**：100% 空间与运动学字段无损转换。
2. **Test 02: FK/IK Arbitration & Control Ownership**：显式手部仲裁，腕部追踪误差仅 0.041 mm。
3. **Test 03: Stance Foot Ground Anchor Preservation**：控制器漂移 0.000000 mm，骨骼漂移 0.246 mm。
4. **Test 04: Truthful ROM & Reach Failure Reporting**：超限及越界严格诚实汇报 `success=False`。
5. **Test 05: Quantitative Pose Equivalence**：桥接与历史动作姿态在骨盆、左踝、右踝误差严格为 **0.0000 mm**。
6. **Test 06: Immutability of Historical Gait Curves**：历史 7 步排期、0.24 m/s 稳态速度、1.26 m 总位移 100% 完整保留。
7. **Test 07: Data Types, Units & Coordinate Consistency**：+Z Up，地面 Z=0.0，双支撑标识完全兼容。
8. **Test 08: Duplicate Write Conflict Prevention**：WBC 与 foot_contact 独占写所有权零冲突。
9. **Test 09: Full Single-Frame 6-Phase Pipeline Execution**：5 帧完整 6 阶段流水线执行，关键帧正确写入。
10. **Test 10: Core Historical Regression Suite**：历史 6 大核心模块回归测试 100% 全绿（WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia）。

---

### 3. 下一步建议与禁止事项
* **下一步**：进入 **Task 6G-C-R3B-2（历史动作向统一桥接层无损迁移）**：
  * 将 `StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction` 的底层姿态落地重构调用 `KinematicBridgeExecutor.execute_frame`；
  * 保持步态生成、速度曲线与步态排期 100% 零修改；
  * 彻底废除控制器双轨制。
* **禁止事项**：
  * 严禁跳入 Task 6G-D。
  * 严禁重写成熟历史步态曲线。
  * 严禁使用独立脚本拼凑演示。
