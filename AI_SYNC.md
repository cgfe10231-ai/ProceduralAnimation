# AI_SYNC: 跨 AI 状态同步与交接卡片

* **项目名称**：ProceduralAnimation（全程序化 3D 连续动画生成系统）
* **当前任务编号**：任务 6G-B（刚体连杆惯性张量与全身角动量模型）
* **任务状态**：已验证（经 `tests/verify_task6gb_body_inertia.py` 13 项测试完整验证；Task 6G-A/6F-D/6F-C/6F-B/6F-A/6D 全部回归通过）
* **Git 状态**：
  * **当前分支**：`master`
  * **最新 Commit SHA**：`d9fcc36`
  * **未提交文件**：无（工作区干净，所有 Task 6G-B 源码、测试与文档已完整提交）

---

### 1. 本次新增/修改文件
* **核心模块与算法**：
  * `src/motion/body_inertia.py`：
    * 建立三维对称 $3 \times 3$ 惯性张量类 `InertiaTensor`（SI 单位 $\text{kg}\cdot\text{m}^2$），支持 Sylvester 判据正定性校验、Cardano 闭式特征值求解（主转动惯量）、SO(3) 刚体旋转张量变换（$\mathbf{R} \mathbf{I} \mathbf{R}^T$）、3D 平行轴定理（Steiner's Theorem: $\mathbf{I} + m (\|\mathbf{r}\|^2 \mathbf{E} - \mathbf{r} \mathbf{r}^T)$）与 Frobenius 范数。
    * 建立分段几何近似模型 `SegmentGeometrySpec`，支持圆柱体、椭球体、椭圆柱体、长方体及自定义对角惯性配置。
    * 预设 `DEFAULT_15_SEGMENT_INERTIA_MODEL` 与 `DEFAULT_13_SEGMENT_INERTIA_MODEL`，与现有 Dempster/Winter 质量模型完全一致。
    * 建立 `SegmentInertiaState` 与 `WholeBodyInertiaState`，记录各分段局部/世界/相对全身 CoM 惯性及自转（Spin）与轨道（Orbital）角动量，明确标注坐标系（`WORLD_Z_UP`）、参考基准（`WHOLE_BODY_COM`）与物理量单位。
    * 提供 `compute_whole_body_inertia`（基于 Armature）与 `compute_whole_body_inertia_from_snapshots`（基于离散快照）双模接口。
    * 提供 `enrich_motion_state_with_inertia` 将惯性张量与角动量无缝注入 `MotionState.params`。
  * `src/motion/__init__.py`（导出 body_inertia 核心接口）
* **自动化测试套件**：
  * `tests/verify_task6gb_body_inertia.py`：13 项严格自动化测试（分段局部张量对称正定、解析几何公式完全匹配、3D 平行轴定理数值正确、空间平移不变性、刚体旋转张量变换协变性、中立站姿对称合理性、单臂侧平举敏锐响应、四肢展开收束惯性比、静止角动量严格为 0、刚性旋转角动量与 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$ 解析一致性、四肢独立运动自转轨道解耦、CoM/快照/MotionState 框架无损集成、历史全量回归测试套件）。
* **配置与文档**：
  * `DECISIONS.md`（新增 `[DEC-021]`）
  * `PROJECT_STATE.md`、`CHANGELOG.md`、`HANDOFF.md`、`AI_SYNC.md`

### 2. 核心实测指标
* **分段局部惯性张量对称且正定**：15 刚体质量分段局部惯性张量严格对称，主惯量全正（$0.00025 \sim 0.61690\text{ kg}\cdot\text{m}^2$），100% 满足物理真实性。
* **几何近似闭式公式精确一致**：圆柱体、椭球体、椭圆柱体、长方体公式与独立解析理论值完全一致，最大误差严格 $< 3 \times 10^{-17}$。
* **3D 平行轴定理数值无损**：位移 $r=(0.3, -0.4, 0.5)\text{ m}$，计算结果与理论增量完全一致（最大单精度浮点累积误差仅 $4.77 \times 10^{-8}$）。
* **空间平移不变性**：角色整体平移位移 $(12.5, -45.0, 3.2)\text{ m}$，相对自身 CoM 的全身惯性张量差值 Frobenius 范数仅 **`8.96e-06 kg*m^2`**（完全保持不变）。
* **刚体旋转张量变换协变性**：角色整体绕任意 3D 轴 $(0.577, 0.577, 0.577)$ 旋转 $40^\circ$，合成惯性张量与张量变换定律 $\mathbf{Q} \mathbf{I} \mathbf{Q}^T$ 误差仅 **`7.06e-06 kg*m^2`**。
* **中立站姿矢状面对称与合理量级**：左右对称矢状面惯性积严格为 $0$（$I_{xy} = I_{xz} = 0.00000$）；俯仰 $I_{xx} = 13.46\text{ kg}\cdot\text{m}^2$、滚转 $I_{yy} = 14.21\text{ kg}\cdot\text{m}^2$、偏航 $I_{zz} = 1.08\text{ kg}\cdot\text{m}^2$，处于人体生物力学标准区间。
* **单臂侧平举敏锐物理响应**：右臂侧平举引发偏航转动惯量显著增加 $+0.65442\text{ kg}\cdot\text{m}^2$（增幅达 $+60.7\%$），并引入非对称惯性积 $I_{xy} = 0.10313\text{ kg}\cdot\text{m}^2$。
* **四肢展开与紧收姿态惯性比**：大字展开（T-Pose: $I_{zz} = 2.40271\text{ kg}\cdot\text{m}^2$）与抱胸收束（Tucked: $I_{zz} = 0.94590\text{ kg}\cdot\text{m}^2$）差异显著，偏航惯性比达 **`2.540 倍`**（差值 $+1.45682\text{ kg}\cdot\text{m}^2$）。
* **静止身体角动量严格为零**：零速度下全身体自转、轨道及总角动量严格等于 **`0.00000000 kg*m^2/s`**。
* **刚性旋转多连杆角动量解析一致性**：整个人体绕 CoM 以 $\boldsymbol{\omega}=(0.4, 0.8, -0.6)\text{ rad/s}$ 发生刚体旋转时，多连杆自转+轨道求和角动量与单刚体 $\mathbf{I}_{\text{body}} \boldsymbol{\omega}$ 绝对矢量误差仅 **`1.07e-06 kg*m^2/s`**（相对误差 **`8.54e-08`**）。
* **四肢独立运动自转与轨道解耦**：单侧手臂挥动时，自转角动量模长 $0.09087\text{ kg}\cdot\text{m}^2/\text{s}$ 与肢体轨道角动量模长 $1.69233\text{ kg}\cdot\text{m}^2/\text{s}$ 清晰解耦，总角动量严格矢量守恒。
* **与 CoM、速度学追踪器及动作状态机无缝集成**：全身质心误差严格为 $0.00\text{ m}$，离散快照与 Armature 姿态求算张量差仅 $7.33 \times 10^{-7}\text{ kg}\cdot\text{m}^2$，通过 `enrich_motion_state_with_inertia` 无损注入 `MotionState.params`。
* **全量回归验证**：Task 6G-A、6F-D、6F-C、6F-B、6F-A 及 6D 测试均 100% 全绿通过（退出码 `0`）。

### 3. 遗留问题与限制
1. 本次仅实现刚体连杆分段惯性张量与多连杆角动量计算模型，不包含地面反作用力求解、接触力矩、支撑多边形与动态平衡补偿算法（留待 Task 6G-C）或全动力学正向仿真。测试中的角动量一致性属于离散运动学与惯性张量数学一致性校验，非主动外力碰撞模拟。

### 4. 下一步建议
* 等待用户指示后开启 Task 6G-C（支撑多边形与动态平衡补偿系统），或高难度特技跑酷动作。

### 5. 是否需要用户批准
* **否**。
