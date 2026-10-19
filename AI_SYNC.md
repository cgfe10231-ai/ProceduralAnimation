# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6F-C（关节自由度与生理活动范围 ROM 约束系统）
* **任务状态**：已验证（经 `tests/verify_task6fc_joint_limits.py` 完整验证；Task 6F-B/6F-A/6D 全部回归通过）
* **Git 状态**：
  * **当前分支**：`master`
  * **最新 Commit SHA**：待提交（自动收尾提交即将执行）
  * **待提交文件**：
    * `src/motion/joint_limits.py`（关节自由度与生理活动范围 ROM 约束系统核心实现）
    * `src/motion/__init__.py`（导出 joint_limits 相关符号）
    * `tests/verify_task6fc_joint_limits.py`（Task 6F-C 完整自动化验证套件）
    * `DECISIONS.md`（录入 `[DEC-018]`）
    * `PROJECT_STATE.md`、`CHANGELOG.md`、`HANDOFF.md`、`AI_SYNC.md`（同步更新状态、变更历史与交接卡片）

---

### 1. 本次新增/修改文件
* **核心模块与算法**：
  * `src/motion/joint_limits.py`：
    * 引入 `JointLimitSpec`、`JointModel`、`DEFAULT_HUMANOID_ROM_MODEL`。
    * 覆盖 17 根解剖骨骼（`root` 与 `pelvis` 明确定义为浮动基座参考系，排除出人体内部 ROM 关节）。
    * 内置 Kapandji / Winter / AAOS 生物力学文献标准参数与局部坐标系约定。
    * 提供 `normalize_angle_deg` / `normalize_angle_rad` 环绕跳变保护，防止 $\pm 180^\circ$ 错误截断。
    * 支持 `BOX_EULER`、`ELLIPTICAL_CONE`（肩/髋复合摆动锥）、`HINGE_1D`（肘/膝反向折断硬锁定）。
    * 支持左右侧外展局部坐标异号镜像对称与 `with_overrides()` 独立覆盖。
    * 提供双轨非静默接口：`validate_rotations` / `validate_armature_pose` 只读校验，`clamp_rotations` / `clamp_armature_pose` 投影限幅并报告修改量。
    * 提供 `extract_evaluated_bone_rotation_rad`，无缝评估活跃 IK 链姿态。
* **自动化测试套件**：
  * `tests/verify_task6fc_joint_limits.py`：10 项核心测试用例（中立站姿合规、边界姿态、明确超限检出、安全投影截断、双侧镜像对称、铰链反折硬锁、复合多轴椭圆锥、环绕保护、骨骼长度恒定、活跃 IK 兼容性）。
* **配置与文档**：
  * `src/motion/__init__.py`（导出 joint_limits 接口）
  * `DECISIONS.md`（新增 `[DEC-018]`）
  * `PROJECT_STATE.md`、`CHANGELOG.md`、`HANDOFF.md`、`AI_SYNC.md`

### 2. 核心实测指标
* **中立站姿与合法边界**：
  * 17 个解剖关节中立站姿违规数严格为 **`0`**。
  * 合法边界姿态测试 100% 通过，修改量严格为 **`0.00 deg`**。
* **超限检出与安全投影截断**：
  * 脊柱过屈（+85°）、肘关节向后反折（-25°）、膝关节向前反折（+35°）、肩关节过度外展（+170°）均被精准检出，超限量计算误差 $\le 0.1^\circ$。
  * 投影截断后精准落入边界（脊柱 +60°，肘关节 -2°，膝关节 +2°，肩关节 +150°），截断后二次校验 100% 合法，无静默篡改。
* **双侧镜像对称与铰链防反折**：
  * 左右侧上臂与大腿外展（Local Z）镜像反号处理完全正确。
  * 膝关节向前弯折被截断至 $\le +2.0^\circ$；肘关节向后弯折被截断至 $\ge -2.0^\circ$。
* **复合多轴旋转与角度环绕**：
  * 肩关节（`upper_arm.L`）极大俯仰（140°）+ 极大外展（130°）合成摆角 $191.0^\circ$ 超限 $35.9^\circ$，被椭圆锥平滑径向投影至 $(113.7^\circ, 0.0^\circ, 105.6^\circ)$。
  * $365^\circ \rightarrow 10^\circ$（合法），$270^\circ \rightarrow -90^\circ$（准确检出超限），杜绝跳变。
* **骨骼几何恒定性**：
  * 骨架姿态截断下 19 根骨骼长度变化严格为 **`0.000000 m`**（0 变形拉伸）。
* **活跃 IK 兼容性**：
  * 双腿 IK 活跃站立姿态：100% 处于 ROM 范围内；
  * 双腿 IK 前屈抬腿（提脚 $0.20\text{ m}$）：髋关节屈曲 $+56.36^\circ$（ROM $[-25^\circ, +120^\circ]$），膝关节屈曲 $-70.79^\circ$（ROM $[-145^\circ, +2^\circ]$），100% 满足解剖规范；
  * 双手 IK 前向伸手抓取：上臂俯仰 $+9.60^\circ$，前臂肘屈 $+93.67^\circ$（ROM $[-2^\circ, +145^\circ]$），100% 满足解剖规范。
* **回归验证**：
  * Task 6F-B 刚体连杆质心测试、Task 6F-A 双臂 IK 测试、Task 6D 冲刺制动急停测试均 100% 全绿通过（退出码 `0`）。

### 3. 遗留问题与限制
1. 本次仅实现关节自由度与生理活动范围（ROM）约束系统；全身平衡恢复控制、接触力与高难度跑酷特技留待后续任务。

### 4. 下一步建议
* 等待用户指示后开启 Task 7 或高难度特技运动扩展（如跑跳 Running Jump、障碍撑越 Vault 或急转弯 Sharp Turn）。

### 5. 是否需要用户批准
* **否**。
