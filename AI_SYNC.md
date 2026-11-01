# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务**：ProceduralAnimation — PKG-5 / 09-B RC-1: Parent Transform Domain & Atomic Commit (Task ID: `PKG5-09B-RC1-PARENT-TRANSFORM-DOMAIN`)
* **门禁状态**：`RE-VERIFICATION IN PROGRESS — NOT ACCEPTED`（等待 ChatGPT 独立审查 RC-1）
* **核心状态与 RC-1 交付物**：
  1. **有效父级变换数学域显式定义与 Phase A 前置校验 (src/rig/ik.py:set_foot_ik_target)**：
     - 在 Phase A 针对 `ik_obj.parent` 与 `pole_obj.parent` 显式计算有效父级矩阵 $M_{\text{eff}} = M_{\text{parent}} \cdot M_{\text{parent\_inverse}}$；
     - 严格限定支持域为：纯 3D 旋转以及正均匀缩放与旋转的组合（共形变换）；
     - 在执行任何场景写操作或骨骼位姿提示前，全面校验并拦截不支持的矩阵：
       - 有限性：16 个元素必须均为有限浮点数；
       - 仿射性：最后一行必须严格满足 $[0, 0, 0, 1]$（公差 $10^{-6}$）；
       - 行列式：$3 \times 3$ 线性子矩阵行列式 $\det(A) > 10^{-7}$，严格拒绝奇异退化（$\det \le 10^{-7}$）与镜像反射（$\det < 0$）；
       - 共形正交性：通过 Gram 矩阵 $G = A^T A$ 与等效标量 $s^2 = \text{Tr}(G) / 3.0$ 计算相对偏差，当相对偏差 $> 10^{-4}$ 时严格判定为非均匀缩放或剪切畸变并抛出明确的 `ValueError`（包含 Phase A 校验失败及支持域提示）。
  2. **Phase B 提交快照与原子事务回滚保障 (src/rig/ik.py:set_foot_ik_target)**：
     - 在 Phase B 写入前（在调用 `_apply_ik_prebend_hint` 之前），完整快照双侧 4 个控制器（`FootIK.L/R`、`KneePole.L/R`）与 6 根腿部姿态骨骼（`thigh.L/R`、`shin.L/R`、`foot.L/R`）的完整通道（包括 `parent`、`matrix_parent_inverse`、`location`、`rotation_mode`、`rotation_euler`、`rotation_quaternion`、`rotation_axis_angle`、`scale`、`delta` 通道、`is_locked` 属性及 `matrix_basis`/`matrix`/`matrix_world`）；
     - 将 Phase B 写入过程（骨骼提示弯曲、控制器位置与旋转写入、视图层刷新、状态读取）置于 `try ... except` 事务保护内；
     - 若 Phase B 发生任何异常，自动触发 `_rollback_leg_rig_state` 完整恢复 6 根骨骼与 4 个控制器的所有通道，刷新视图层并校验恢复矩阵最大偏差 $\le 10^{-4}$，保障现场原子性后重新抛出原始异常（若回滚自身异常则抛出 `RuntimeError("ROLLBACK FAILURE...")`）。
  3. **专项测试集全量覆盖与断言强化 (tests/test_leg_ik_world_rotation_contract.py)**：
     - 修正 TEST-12 Part B：保留非均匀缩放与复合旋转，直接调用真实 `set_foot_ik_target()`，断言 Phase A 抛出 `ValueError`，并断言调用失败后全部 4 控制器与 6 骨骼状态与调用前完全一致（偏差 $< 10^{-6}$）；
     - 新增 TEST-14：通过 `matrix_parent_inverse` 构造包含剪切（Shear）的有效父级矩阵，验证 Phase A 拦截与失败原子性（$< 10^{-6}$）；
     - 新增 TEST-15：构造奇异父级矩阵（$\det(A) \le 10^{-7}$），验证 Phase A 拦截与失败原子性（$< 10^{-6}$）；
     - 新增 TEST-16：构造镜像反射父级矩阵（$\det(A) < 0$），验证 Phase A 拦截与失败原子性（$< 10^{-6}$）；
     - 新增 TEST-17：针对 Phase B 执行故障注入（mock `get_leg_ik_state` 抛出 `RuntimeError`），验证回滚事务捕获故障、原子性还原 4 控制器与 6 骨骼（$< 10^{-6}$）并重新抛出原异常。
  4. **专项测试执行结果 (Headless Blender 5.1)**：
     - 测试命令：`blender.exe -b -P tests/test_leg_ik_world_rotation_contract.py`
     - 执行结果：**17 tests planned, 17 executed, 17 passed, 0 failed (1.21s)**。
     - 说明：按 RC-1 任务协议第七条约束，仅执行了该专项测试，未执行 Quick/Physics/Motion/Full 全仓测试。
* **Git 现场状态**：
  * **当前分支**：master
  * **起始基准 Commit SHA**：83c233c1ed6414476a44d7376ffd3e654a021367
  * **受保护文件**：`P2_R1_recovery.patch` 严格保留未暂存。
