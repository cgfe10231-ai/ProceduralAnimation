# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6G-C-R3B-1-Final（架构漏洞修补与 GitHub 自动同步）
* **任务状态**：已验证（时间步长 dt 动态校验、手部 IK/接触语义彻底解耦、Phase 5 惯性张量与全身体角动量遥测闭环集成，14 项严苛测试 100% 通过，历史 6 大核心测试 100% 全绿；永久 GitHub 自动化同步协议确立并推送完成）
* **Git 状态**：
  * **当前分支**：`master`
  * **基准 Commit SHA**：`a8987ac`
  * **本任务提交 Commit SHA**：`339c38a`
  * **远程仓库**：`origin https://github.com/cgfe10231-ai/ProceduralAnimation.git` (`master`)
  * **未提交文件**：无（收尾精准提交后）

---

### 1. R3B-1-Final 架构漏洞修补与同步机制成果
* **时间步长 (dt) 动态支持与物理缩放 (`src/motion/kinematic_bridge.py`)**：
  * `KinematicPlannedPose` 引入可选 `dt`，`KinematicBridgeExecutor.execute_frame` 支持显式 `dt` 传入或由 `time_seconds` 自动差分计算；
  * 引入严格单调递增时间戳与正数步长校验（`dt > 0.0`，反向或零时间戳抛出 `ValueError`）；
  * 有限差分速度与惯性张量物理缩放完全一致，默认维持 24 FPS 标准兼容。
* **手部 IK 与接触语义彻底解耦 (`src/motion/kinematic_bridge.py`)**：
  * 在 `PlannedFootTarget` 与 `PlannedHandTarget` 中显式分离 IK 目标激活（`enabled`）、接触意图（`contact_intent`）、世界锁定（`is_locked`）、接触类型与表面 ID；
  * 自由空间伸手（`contact_intent=False`）绝不产生虚假接触，维持正常双足或单足支撑分类；
  * 接触合规性校验：对声明接触意图的肢体，通过 `ContactModel` 校验与环境表面的几何间隙、穿透与法向容差，超差真实报警 `success=False`；
  * 支撑足地面锚点在局部坐标上依据踝关节原点 $(x, y, z - 0.070\text{ m})$ 精准对齐地面 $Z=0$，消除足底中心人为滑移。
* **Phase 5 惯性张量与全身体角动量遥测集成 (`src/motion/kinematic_bridge.py`)**：
  * 在 Phase 5 姿态解算完成后，直接调用 `compute_whole_body_inertia`，基于已评估的 Armature 姿态与 `kin_result.velocity` 计算全身体惯性张量、自转角动量与质心轨道角动量，并注入 `MotionState.params`；保持纯只读物理遥测。
* **永久 GitHub 自动化安全同步协议确立 (`AGENTS.md` / `GEMINI.md` / `.agents/rules/project_rules.md`)**：
  * 任务完成并通过全部验证后，自动精确暂存、本地 commit，并自动执行 `git push origin master`，校验远程 SHA 与本地 HEAD 一致。

---

### 2. 验证结果清单 (`tests/verify_task6gc_r3b1_bridge.py` 14/14 全绿)
1. **Test 01: Lossless Input Mapping**：100% 空间与运动学字段无损转换。
2. **Test 02: FK/IK Arbitration & Control Ownership**：显式手部仲裁，腕部追踪误差仅 0.041 mm。
3. **Test 03: Stance Foot Ground Anchor Preservation**：控制器漂移 0.000000 mm，骨骼漂移 0.246 mm。
4. **Test 04: Truthful ROM & Reach Failure Reporting**：超限及越界严格诚实汇报 `success=False`。
5. **Test 05: Quantitative Pose Equivalence**：桥接与历史动作姿态在骨盆、左踝、右踝误差严格为 **0.0000 mm**。
6. **Test 06: Immutability of Historical Gait Curves**：历史 7 步排期、0.24 m/s 稳态速度、1.26 m 总位移 100% 完整保留。
7. **Test 07: Data Types, Units & Coordinate Consistency**：+Z Up，地面 Z=0.0，双支撑标识完全兼容。
8. **Test 08: Duplicate Write Conflict Prevention**：WBC 与 foot_contact 独占写所有权零冲突。
9. **Test 09: Full Single-Frame 6-Phase Pipeline Execution**：5 帧完整 6 阶段流水线执行，关键帧正确写入。
10. **Test 10: Variable Time Step (dt) & Kinematic Scaling**：0.01s 100FPS 与 0.04s 25FPS 速度换算精确吻合，非法步长与反向时间戳异常拦截成功。
11. **Test 11: Hand IK vs Contact Intent Decoupling**：自由空间抓空与主动表面接触精准区分，越界接触真实报警 `success=False`。
12. **Test 12: Whole-Body Inertia & Angular Momentum Telemetry**：静态姿态角动量严格为 0.0，运动状态惯性张量正定且质量 > 50 kg。
13. **Test 13: Historical Motion Actions Intactness & Planning**：Walk 7 步、Run 24 帧周期、SprintStart 36 帧、SprintBrake 26 帧动作完全完好。
14. **Test 14: Core Historical Regression Suite**：历史 6 大核心模块回归测试 100% 全绿（WBC, Joint Limits, Rigid Link, Arm IK, Kinematics, Inertia）。

---

### 3. 下一步建议与禁止事项
* **下一步**：严格停止，等待用户指示。后续进入 **Task 6G-C-R3B-2（历史动作向统一桥接层无损迁移）**：
  * 将 `StartStopWalkAction`、`RunAction`、`SprintStartAction`、`SprintBrakeAction` 的底层姿态落地重构调用 `KinematicBridgeExecutor.execute_frame`；
  * 保持步态生成、速度曲线与步态排期 100% 零修改；
  * 彻底废除控制器双轨制。
* **禁止事项**：
  * 严禁跳入 Task 6G-D。
  * 严禁重写成熟历史步态曲线。
  * 严禁使用独立脚本拼凑演示。
