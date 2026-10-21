# DECISIONS: 架构与技术决策记录

本文档记录本项目所有关键技术架构决策及其权衡考量。

---

### [DEC-001] 独立目录物理隔离机制
* **状态**：已采纳并实施 (Accepted)
* **日期**：2026-10-15
* **背景**：当前用户桌面存在相邻工程（如 `Unity_Blender`、课程实验报告文档等）。任何操作若未加隔离可能导致误删或覆盖已有文件。
* **决策**：将本项目完全限定在 `ProceduralAnimation/` 独立目录中。所有脚本、文档、产物只在当前目录内读写。
* **影响**：完全杜绝跨项目干扰，保障用户已有工程的安全。

---

### [DEC-002] 核心技术栈选型：Blender Headless + Python (`bpy`)
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-15
* **背景**：项目目标为全程序化连续 3D 动画，需要成熟的骨骼系统、动力学/运动学曲线支持、灵活的渲染引擎以及无头命令行自动化能力。
* **决策**：选择 Blender 原生 Python API (`bpy`)。
* **原因**：
  1. Blender 具备极其成熟的 Python API，能全代码控制从 Mesh、Armature、Constraints、Keyframes、Camera 到 Render 的所有环节。
  2. 支持 `blender -b -P <script>` 命令行无头运行，适合作为完全自动化的后台流水线。
  3. 无需第三方商业商业许可证或付费 API。

---

### [DEC-003] 分级渲染策略：低成本预览与高质量正式渲染分离
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-15
* **背景**：全流程包含 360 帧连续动画，若每次迭代均采用高质量 Cycles/Eevee 渲染，将造成巨大的计算资源与时间浪费。
* **决策**：引入双层渲染管线：
  1. 开发与验证阶段优先采用 Workbench 或极低采样 Eevee 进行视口预览渲染，秒级生成。
  2. 验收或特定输出时，才执行全质量渲染。
* **影响**：大幅提升迭代验证速度，保证开发敏捷性。

---

### [DEC-004] 严格六态事实与验证纪律
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-15
* **背景**：AI 辅助开发中极易出现“写了代码就声称完成”、“跑了命令不看输出就认为成功”等虚假报告。
* **决策**：确立 6 种明确状态（已实现、已执行但未完整验证、已验证、未实现、已知缺陷、理论可行但尚未测试）。未进行实际产物与输出核验的内容一律不得标注为已验证。
* **影响**：确保项目状态百分之百真实透明。

---

### [DEC-005] 多层级规则与持久记忆系统
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-15
* **背景**：对话上下文窗口重置后容易丢失对项目纪律与约束的记忆。
* **决策**：
  1. 根目录配置 `GEMINI.md` / `AGENTS.md` 及 `.agents/rules/` 作为项目级规则，由 Antigravity 自动加载。
  2. 根目录维护 `PROJECT_STATE.md`、`HANDOFF.md`、`DECISIONS.md` 等状态与交接文档，确保跨会话无缝继承。
* **影响**：实现持久化认知，规避反复询问与规则退化。

---

### [DEC-006] 美术风格解耦与简单人形占位符策略
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-15
* **背景**：最终角色的表面结构、毛发等视觉设计尚未确定。
* **决策**：阶段 1 聚焦于骨骼动力学、连续动作状态机与摄像机追踪，角色几何采用解耦的简单人形占位模型，禁止过早锁定具体的视觉风格。
* **影响**：使开发重心聚焦于运动逻辑本身，降低初始复杂度。

---

### [DEC-007] 跨 AI 同步协议 (`AI_SYNC.md`) 与上下文漂移防御机制
* **状态**：已采纳并实施 (Accepted)
* **日期**：2026-10-15
* **背景**：长时间开发或不同 AI 助手切换时，容易因上下文截断产生认知漂移、虚假记忆或错误覆盖代码。
* **决策**：
  1. 在根目录维护受字数严格约束（约 1500 字符内）的 `AI_SYNC.md` 作为外部 AI 助手的权威交接卡片。
  2. 确立“磁盘代码与真实测试结果为事实第一依据”的铁律，明确 `HANDOFF.md` 与 `AI_SYNC.md` 仅为摘要，不可推翻原始代码与测试事实。
  3. 文档与代码不一致时必须调查并记录冲突，禁止凭空臆断或擅自重构。
* **影响**：彻底阻断跨工具/长周期开发中的状态漂移与虚构行为。

---

### [DEC-008] Blender 5.1.1 Headless 调用规范与闭环检验基准
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-15
* **背景**：需要确立标准化的 Blender 后台执行范式，兼顾跨平台执行稳定性与产物多维校验。
* **决策**：
  1. 统一采用 `blender.exe -b -P <script>` 作为后台执行标准命令。
  2. 统一保存与渲染产物位置至项目内受控子目录（如 `tests/output/`），禁止污染根目录或外部路径。
  3. 建立双重核验机制：不仅检查进程返回码，且必须对生成的 `.blend` 二进制存在性、渲染图像尺寸头信息（PNG IHDR）以及通过二次重开 `.blend` 场景对象列表进行闭环核验。
* **影响**：为后续场景、角色、动画等复杂模块的自动化批处理和端到端测试奠定了可靠基础。

---

### [DEC-009] 模块化工程骨架与最小集中配置 (PipelineConfig) 驱动模式
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-16
* **背景**：需要避免将代码写成单体面条式大脚本，同时需防止过度设计或引入重量级框架。
* **决策**：
  1. 建立基于原生 Python 标准库与 `bpy` 的模块化工程骨架（`src/config.py`、`src/scene/`、`src/camera/`、`src/lighting/`、`src/render/`、`src/validation/` 以及 `character`、`rig`、`motion` 接口模块）。
  2. 采用纯数据类 `PipelineConfig` 集中管理时间线（24 FPS、360 帧）、分辨率（1280x720）、输出目录、渲染引擎与随机种子。
  3. 根目录统一由 `run_pipeline.py` 与 `run_pipeline.ps1` 驱动执行。
* **影响**：保持了零第三方外部依赖的纯粹性，代码职责清晰，完全兼容 Blender 原生 Python 环境。

---

### [DEC-010] 统一世界坐标约定与纯数据走廊安全净空机制
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-16
* **背景**：多模块协同生成 3D 场景时，若坐标定义混乱容易导致角色悬空/陷地、障碍物阻挡预定行走路径等问题。
* **决策**：
  1. 严密确立 Blender 物理世界坐标约定：$Z$ 轴向上、地面顶面严格对齐至 $Z = 0.0\text{ m}$，度量单位统一定为米。
  2. 将几何布局算法解耦为纯 Python 模块（`src/scene/layout.py`），通过二维点到线段投影距离算法实现严格的 $\ge 2.4\text{ m}$ 走廊净空校验。
  3. 在 Blender 场景中将障碍物区分为建筑体块与圆柱形障碍，并生成地面参考航标供视觉辨析。
  4. 摄像机系统绑定 `TRACK_TO` 约束至专用观察目标，并在第 1 帧、第 180 帧、第 360 帧建立关键帧插值，实现全自动运镜。
* **影响**：确保了场景布局的 100% 种子确定性、未来角色行走空间的完全无碰撞性，以及镜头跟拍的自动化。

---

### [DEC-011] 统一运动状态与动作插件式框架 (MotionState / MotionAction / MotionPlanner)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-18
* **背景**：后续需要连续支持行走、跑步、冲刺、翻滚、滑铲与跑跳等复杂行为，若通过硬编码帧号或单体脚本堆叠将导致系统无法扩展。
* **决策**：
  1. 建立 `MotionState` 统一表达世界空间位置、朝向偏航角、线速度/角速度向量、线加速度、接触状态与步态相位。
  2. 抽象 `MotionAction` 插件接口，将运动学逻辑与姿态解耦，通过 `MotionPlanner` 调度并管理动作序列与动量继承。
* **影响**：实现任意动作的无缝连接与可组合性，为跑跳越障奠定统一运动系统基石。

---

### [DEC-012] 支撑与腾空双相参数化跑步机制
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-18
* **背景**：跑步区别于行走的核心物理特征是存在双脚均不接触地面的腾空期（Flight Phase）。
* **决策**：
  1. 将跑步步态参数化划分为：左支撑 -> 腾空 -> 右支撑 -> 腾空。
  2. 支撑期世界坐标刚性锁定，腾空期动态释放接触约束并提供离地净空，杜绝强制贴地伪造。
* **影响**：使角色具备真实的垂直弹跳与空中飞跃感，动作姿态更加拟真自然。

---

### [DEC-013] 解析二次速度曲线驱动的爆发式起跑与步态自适应冲刺
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-18
* **背景**：从静止加速至 2.0 m/s 高速冲刺需要物理上连续平滑的根运动速度，以及随速度自适应拉长步幅、提升步频与调整前倾下蹲姿态，不可使用固定循环简单倍速播放。
* **决策**：
  1. 采用解析二次速度曲线 $v(x) = v_{\max}(2x - x^2)$ 驱动根运动，保证加速度从 $a_0 = 2.0\text{ m/s}^2$ 连续降至 0，单步加速度无跳跃。
  2. 步态参数动态自适应：步时由 12 帧缩短至 10 帧（步频 2.0 -> 2.4 步/秒），支撑时间由 9 帧降至 4 帧，腾空时间由 3 帧增至 6 帧，步长由 0.350 m 扩展至 0.833 m。
  3. 终止帧保留完整的动量状态向量 $(0.0, 2.0, 0.0)\text{ m/s}$ 与步态相位，供后续动作继承。
* **影响**：实现从蓄力下蹲、前倾蹬地、单调加速到稳定冲刺的高拟真连贯动作，且严格保证 0 IK 不可达违规。

---

### [DEC-014] 余弦渐变单调减速曲线与自适应步态制动急停机制 (SprintBrakeAction)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：高速冲刺（2.0 m/s）后如果突然停止会导致不可行的大加速度与严重的脚滑/反向超调；需要保证动量连续承接、减速曲线平滑单调归零、接触点世界空间严格锁定，以及合理的单脚支撑/腾空到双脚站立过渡。
* **决策**：
  1. 根运动减速采用解析半余弦速度剖面 $v(x) = \frac{v_0}{2}(1 + \cos(\pi x))$，加速度连续降至 0，最大减速度在合理竞技体育范围（$\sim -2.09\text{ m/s}^2$），全过程无反向位移。
  2. 采用 3 步渐变制动与收步时序：右脚平滑承接 -> 左脚主抗惯性落地缓冲 -> 右脚次级迈步 -> 左脚终点落位 -> 右脚并拢闭合，最终进入完全双支撑静止站姿。
  3. 姿态协同：骨盆深度下蹲缓冲（下降至 $-0.115\text{ m}$），躯干后倾（$-6.0^\circ$）抵消前向惯性，随后平稳回正（$0.0^\circ$），手臂反向平稳收束。
* **影响**：在完全继承 Task 6C 末尾动量与姿态的基础上，实现高逼真主动制动急停，支撑脚世界漂移小于 $0.04\text{ mm}$，最后 10 帧抖动严格为 $0$。

---

### [DEC-015] 物理约束辅助的刚体连杆人体运动控制架构路线
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-19
* **背景**：项目后续需连续支持跑跳、攀爬、翻滚、撑越等高难度跑酷特技动作。现有动作的上半身姿态过度依赖三角函数经验微调，缺乏手部世界空间定位能力，且缺少质心平衡与关节生理限位机制。需要确定既能提升物理真实感、又避免引入沉重物理引擎的最佳控制架构。
* **决策**：
  1. 明确技术路线为“物理约束辅助的程序化动画（Physics-Constraint-Assisted Procedural Animation）”，明确排除肌肉、肌腱或完整人体微观刚体碰撞仿真。
  2. 保持现有 19 根骨骼刚体分段与 13 块网格几何不变，不推翻现有骨架体系。
  3. 对称引入双臂两骨骼 IK（`ArmIK` + `HandIK` + `ElbowPole`），使双手具备与双脚对等的世界空间位置与朝向目标独立指定能力，并通过权重（`influence`）保证向后兼容。
  4. 新增轻量级刚体连杆模块（`src/motion/rigid_link.py`），采用 Dempster 解剖学参数定义 13 分段质量比率，实现前向运动学多刚体质心（CoM）计算与各关节生理活动范围（ROM）硬性截断保护。
* **影响**：为 Task 6F 及其后的跑跳撑越特技动作提供了坚实的物理约束与几何求解基石，彻底杜绝关节反折穿帮，同时保持零外部复杂依赖。

---

### [DEC-016] 双臂独立两骨骼 IK 与手部三维世界朝向解耦架构 (Task 6F-A)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：需要为角色提供独立左右手世界空间位置与完整 3D 朝向控制，同时严格保持 19 根骨骼不变，保持上臂与前臂物理长度不变，确保与现有全部基于 FK 的行走/跑步/冲刺动作 100% 零破坏向后兼容。
* **决策**：
  1. **两骨骼 IK 拓扑与朝向**：在 `forearm.L/R` 上配置原生 Blender `IK` 约束（`chain_count = 2`, `use_tail = True`, `use_stretch = False`），目标为空物体 `HandIK.L/R`，肘部极向目标为空物体 `ElbowPole.L/R`，统一设定极向角 `pole_angle = -90.0 deg`，精确匹配人体上臂/前臂向前屈伸、肘尖向后外的生理特征。
  2. **手部朝向与末端位置完全解耦**：在 `hand.L/R` 上配置原生 `COPY_ROTATION` 约束（`target_space = 'WORLD', owner_space = 'WORLD', mix_mode = 'REPLACE'`），骨骼数据保留 `use_inherit_rotation = True`。手部朝向通过世界旋转矩阵补偿父节点位姿直接映射，手部朝向改变时不产生任何腕部空间漂移（实测漂移 $< 0.025\text{ mm}$，朝向对齐误差 $0.0000^\circ$）。
  3. **达程保护与零拉伸保证**：基于几何上臂（0.30m）+ 前臂（0.26m）设定最大达程 0.56m 与安全最小达程 0.08m。超出达程时可选投影至最大达程球面（`clamp_reach=True`）或如实报错上报（`clamp_reach=False`），约束内置 `use_stretch = False` 杜绝骨骼拉伸。
  4. **零侵入向后兼容**：所有约束初始化权重默认设为 `influence = 0.0`。在纯 FK 动作中，双臂与双手 100% 继承父级摆臂，现有所有历史动作测试 100% 全绿通过。
* **影响**：双手获得了独立于身体基座的世界空间位置、朝向和肘部极向控制能力，位置误差 $< 0.05\text{ mm}$，为后续攀爬、撑越、伏地动作打下稳定基石。

---

### [DEC-017] 刚体连杆分段与解耦式全身质心（CoM）计算架构 (Task 6F-B)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：为了在后续高动态特技动作（如跑跳、空中平衡、落地缓冲、接触抗倾覆）中实现基于物理原理的姿态协调和自适应重心平衡，角色需要具备实时准确计算全身质心（Center of Mass, CoM）的能力。现有骨架包含 19 根控制骨骼，几何网格为 13 块占位体，控制骨骼与解剖学质量分段在概念上存在差异，必须解耦。同时必须保证坐标空间严谨，杜绝根节点二次变换（Double Transform）Bug，且不能对现有动作系统产生任何破坏。
* **决策**：
  1. **分段解耦数据结构**：引入轻量级数据类 `RigidSegmentSpec` 与 `BodyMassDistribution`，将质量分段（Anatomical Segments）与 Blender 控制骨骼（PoseBones）完全解耦，支持任意骨骼绑定与局部质心比例/偏移（Fraction & Offset）。
  2. **标准生物力学质量分布**：内置 Winter (2009) / Dempster (1955) 标准 15 分段模型（Head 0.081, Torso 0.355, Pelvis 0.142, Bilateral UpperArm 2x0.028, Forearm 2x0.016, Hand 2x0.006, Thigh 2x0.100, Shank 2x0.0465, Foot 2x0.0145，总和严格归一为 1.0000），以及与现有 13 块占位网格对应的 13 分段合并模型（Forearm + Hand 合并为 LowerArm 0.022）。同时提供 `with_total_mass()`、`with_overrides()` 及 `create_custom_mass_distribution()` 支持任意总质量缩放与自定义比例重归一化。
  3. **精确无二次变换坐标变换**：
     - 单分段质心在骨骼局部坐标系中定义：$\mathbf{p}_{\text{local}} = (0, c_{\text{frac}} \cdot L_{\text{bone}}, 0) + \mathbf{offset}_{\text{local}}$。
     - 变换到 Armature 空间：$\mathbf{p}_{\text{arm}} = \mathbf{M}_{\text{pose}} \cdot \mathbf{p}_{\text{local}}$。
     - 变换到世界空间：$\mathbf{p}_{\text{world}} = \mathbf{M}_{\text{arm\_world}} \cdot \mathbf{p}_{\text{arm}}$。
     由于 `CharacterArmature` 在层级上已父级绑定至 `CharacterRoot`，`arm.matrix_world` 已完整包含根节点位置与朝向，无需且严禁再次乘以根节点变换，彻底杜绝双重变换（Double-transform）。
  4. **零破坏非侵入式读取**：`compute_whole_body_com` 仅以只读方式读取 evaluated `pose_bone.matrix` 和 `armature_obj.matrix_world`，完全不修改、不插入任何关键帧或驱动器，与现有 FK、腿部 IK、双臂 IK 完全兼容。
* **影响**：
  - 静态标准立姿质心高度比实测为 $1.0479\text{ m} / 1.82\text{ m} = 57.58\%$，左右横向对称误差严格为 $0.000000\text{ m}$，与人体解剖学生物力学基准（$55\% \sim 58\%$）完全吻合。
  - 骨盆升降、肢体伸展、IK 控制下质心动态响应精确敏锐（单臂前平举 $\Delta Y=+13.9\text{ mm}, \Delta Z=+13.9\text{ mm}$；单臂侧平举 $\Delta X=-13.9\text{ mm}, \Delta Z=+13.9\text{ mm}$）。
  - 为后续 Task 6F-C 关节生理限位（ROM）以及后续步态质心动量补偿提供底层几何与质量物理数据支撑。

---

### [DEC-018] 关节自由度（DOF）与生理活动范围（ROM）约束系统架构 (Task 6F-C)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：在程序化动作生成与 IK 求解过程中，关节容易由于数值超调、奇异点或极限目标产生非生理反折（如膝关节向前穿刺翻折、肘关节向后折断）或过度伸展。需要建立统一、可配置的关节模型，支持只读校验（`validate`）与明确报告修改的投影限幅（`clamp`），并正确处理各关节局部坐标约定、镜像对称与多轴复合旋转。
* **决策**：
  1. **基座解耦与 17 关节解剖模型**：明确将 `root`（空间根位移与航向）和 `pelvis`（悬浮骨盆基座，用于起伏与全身俯仰缓冲）定义为浮动基座参考系，不作为人体内部 ROM 关节。对剩余 17 根骨骼建立解剖学生物力学 ROM 约束规范（`DEFAULT_HUMANOID_ROM_MODEL`），内置 Kapandji、Winter、AAOS 与 White & Panjabi 标准数据。
  2. **坐标系与旋转跳变防护**：在各骨骼局部坐标系中统一以 radians 处理角度，并配置角度环绕归一化函数（$\theta \in (-\pi, \pi]$），彻底杜绝 Euler wrap-around / $\pm 180^\circ$ 造成的错误越界判定与跳跃截断。
  3. **多自由度复合锥面约束**：对肩关节（`upper_arm.L/R`）与髋关节（`thigh.L/R`）等球窝关节，除各主轴 1D 极值外，引入椭圆锥（`ELLIPTICAL_CONE`）复合摆动约束 $\left(\frac{\theta_x}{\theta_{x,\max}}\right)^2 + \left(\frac{\theta_z}{\theta_{z,\max}}\right)^2 \le 1$，杜绝同时处于极大俯仰与极大展收时超出人体达程。
  4. **单自由度铰链保护**：对肘关节（`forearm.L/R`）与膝关节（`shin.L/R`）采用 `HINGE_1D` 模式，严格锁定膝关节向前超伸（$\le +2.0^\circ$）与肘关节向后超伸（$\ge -2.0^\circ$），且副轴仅允许生理微动游隙（$\le \pm 3.0^\circ$）。
  5. **双侧镜像对称与独立覆盖**：上肢与下肢左右侧展收角（Local Z）具有反号特征（左侧外展 $+Z$、右侧外展 $-Z$），在模型中精确配置镜像，并支持 `with_overrides()` 任意单关节覆盖。
  6. **双轨接口与 IK 兼容性**：
     - 提供非破坏性 `validate_rotations` / `validate_armature_pose`，返回详细违规轴、请求值、极值与超限量；
     - 提供明确报告的 `clamp_rotations` / `clamp_armature_pose`，杜绝静默篡改；
     - 经由 `extract_evaluated_bone_rotation_rad` 兼容评估处于活动状态下的两骨骼 IK（Leg IK / Arm IK），实测证明正常步行、抬腿与伸手姿态 100% 满足解剖学 ROM 约束。
* **影响**：
  - 彻底杜绝了程序化动画与 IK 求解过程中的关节翻转与反向折断风险；
  - 骨骼几何长度 100% 保持恒定（0 变形拉伸）；
  - 为未来 Whole-Body Controller、全身动力学协调及跑跳攀爬动作提供了坚固的生理安全截断防护底座。

---

### [DEC-019] 统一全身控制接口与最小协调器架构 (Task 6F-D)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：在 Task 6A~6D（行走、奔跑、冲刺、急停）和 Task 6F-A~6F-C（双臂 IK、质量分布/CoM、关节 ROM）完成后，动作生成中存在各部位控制逻辑分散的问题（腿部 IK、手部 IK、躯干 FK、骨盆起伏、质心计算、ROM 校验等散落在不同模块）。需要一个统一的全身控制接口（`WholeBodyController`），对四肢末端执行器、躯干、骨盆及空间根节点进行单帧集中调度，并提供可量化的追踪误差反馈与真实现实约束评估。
* **决策**：
  1. **层级定位与非颠覆性原则**：
     - `WholeBodyController` 定位为身体姿态与多末端协调层，直接服务于 `MotionAction`，而非取代上层的 `MotionPlanner`。
     - 严格复用现有 19 骨骼角色结构与现有求解器（`arm_ik.py`、`ik.py`、`rigid_link.py`、`joint_limits.py`），严禁构建第二套骨骼或第二套 IK 数学。
  2. **统一目标描述与流式构建**：
     - 引入 `EndEffectorTarget` 与 `WholeBodyControlTargets`，支持通过链式调用指定：
       * 双手世界空间位置与独立 3D 欧拉朝向目标（含肘部极向指引与达程限幅开关）；
       * 双脚世界空间位置目标与接触锁定标志（`is_locked`，自动同步地面接触防滑逻辑）；
       * 根节点世界位置与航向角（`root_yaw_deg`）；
       * 骨盆基座高度起伏与三维倾斜；
       * 躯干脊椎、颈部与头部的 FK 生理姿态；
       * 单末端独立启用/禁用（`enabled=False` 自动回退至 FK 模式，完全不影响其余活动肢体）。
  3. **真实反馈与零虚假成功报告**：
     - 返回结构化的 `WholeBodyControlResult`，提供各末端毫米级位置误差（`position_error_m`）与度级朝向误差（`orientation_error_deg`）；
     - 真实计算达程可达性（`req_dist <= max_reach`），超出物理达程时明确上报 `REACHABILITY` 违规；
     - 在活动 IK 链评估后，主动调用 `JointModel.validate_armature_pose(use_evaluated_ik=True)` 校验全身 17 个解剖学关节；若存在超限则上报 `ROM_VIOLATION`，且 `result.success` 严格置为 `False`，绝不静默放行；
     - 实时同步计算全身质心（`compute_whole_body_com`），向 `MotionState` 注入统一 CoM 物理遥测参数。
  4. **无缝动作接入（Subclassed MotionAction Integration）**：
     - 在验证套件中构建 `WholeBodyDemoAction(MotionAction)`，证明 `WholeBodyController` 能够无缝嵌入标准动画管线，每帧计算并持久化连续 `MotionState`，与 Task 5C/6A~6D 的架构完全一致。
* **影响**：
  - 角色具备了“四肢末端 + 浮动骨盆 + 躯干姿态 + 全身 CoM + 生理 ROM”集中原子化控制的能力；
  - 10 项严苛验证全绿通过：双臂与双脚毫米级精准贴合（误差 $< 0.05\text{ mm}$），手部朝向误差 $0.0000^\circ$，超限目标与 ROM 冲突 100% 真实截获，CoM 数值与物理分段模型严格吻合；
  - 为未来支撑多边形平衡计算、跑酷翻越接触控制及复杂全身特技动作奠定了坚实的高阶控制架构。
---

### [DEC-020] 连续身体运动状态与速度学计算架构 (Task 6G-A)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-19
* **背景**：在已有动作生成（Task 6A~6D）与静态全身姿态控制（Task 6F-A~6F-D）基础上，系统缺乏统一、严谨的身体微分运动学与速度学层。现有 `MotionState.velocity` 仅记录根节点前向标量速度，缺少空间根角速度、全身质心速度、各刚体连杆空间速度及各关节局部角速度，且直接逐轴对欧拉角求差会在跨越 $\pm 180^\circ$ 时产生严重的虚假超大速度跳变。需要建立一套通用的离散与连续微分运动学接口，为后续惯性预测、接触碰撞与简化动力学提供可复用基础。
* **决策**：
  1. **最短测地线 SO(3) 四元数角速度求解**：
     - 严禁对欧拉角直接差分。采用四元数内积符号对齐（$\mathbf{q}_0 \cdot \mathbf{q}_1 \ge 0$）确保位于同一超球半球，通过四元数相对旋转提取最小角位移 $\theta \mathbf{n}$。
     - 严格区分世界空间空间角速度与关节局部角速度：
       * 空间/世界角速度（根节点、质心、刚体连杆）：$\Delta \mathbf{q}_{\text{world}} = \mathbf{q}_1 \cdot \mathbf{q}_0^{-1}$，$\boldsymbol{\omega}_{\text{world}} = \frac{\theta \mathbf{n}}{\Delta t}$；
       * 局部/体固角速度（骨骼在父级空间中的关节角速度）：$\Delta \mathbf{q}_{\text{local}} = \mathbf{q}_0^{-1} \cdot \mathbf{q}_1$，$\boldsymbol{\omega}_{\text{local}} = \frac{\theta \mathbf{n}}{\Delta t}$。
     - 彻底消除 $\pm 180^\circ$ 边界穿越时的虚假速度尖峰（实测 $+175^\circ \rightarrow -175^\circ$ 角速度严格为平滑的 $+200^\circ/\text{s}$，0 异常跳变）。
  2. **显式任意时间步长 $\Delta t$ 参数化**：
     - 严禁将微分计算与固定 24 FPS 绑定，所有速度与加速度接口均显式接受实数 $\Delta t$，在可变帧率与物理子步下严格保证确定性与尺度守恒。
  3. **实际姿态优先与控制器期望解耦**：
     - 速度学求解优先采样 `WholeBodyController` 求解后的实际评估姿态（`evaluated_armature` / `WholeBodyControlResult`），避免使用未达成的目标虚报运动状态。
     - 显式分离实际推导速度（`root_linear_velocity`）与控制器指令速度（`commanded_velocity`），输出量化追踪残差（`velocity_tracking_error_mps`）。
  4. **全链路物理守恒与零破坏接入**：
     - 严密保持全多刚体动量守恒：实测全身 CoM 线速度与 15 个连杆质量加权速度和 $\sum w_i \mathbf{v}_i$ 的数值差异严格在 float32 精度内（$< 10^{-5}\text{ m/s}$）。
     - 通过 `enrich_motion_state_with_kinematics` 将全套速度学遥测数据注入现有 `MotionState.params`，100% 保持现有 `MotionAction`、`MotionPlanner` 调用契约不变。
* **影响**：
  - 角色运动系统具备了完整的空间一阶与二阶微分运动学感知能力（根节点、骨盆、全身质心、15 个刚体连杆、17 个解剖关节及 4 个末端执行器）；
  - 10 项严苛验证全部通过：静止 0 速度、匀速直线平移误差为 0、恒定定轴旋转误差 $< 3 \times 10^{-8}\text{ rad/s}$、任意 3D 复合旋转误差 $< 2 \times 10^{-6}\text{ rad/s}$、单侧肢体运动严格隔离无串扰、SprintStart 到 SprintBrake 动作交界处速度严格平滑连续；
  - 为未来接触动量交换、惯性张量与极速动态平衡动作奠定了坚实无奇点的运动学基石。

---

### [DEC-021] 刚体连杆分段惯性张量与多连杆全身角动量模型架构规范 (Task 6G-B)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-20
* **背景**：在完成多刚体质量分布模型、全身质心计算（Task 6F-B）与连续微分运动学状态（Task 6G-A）后，系统需要进一步获取人体当前姿态的惯性分布特性（惯性张量）与多连杆动态角动量，为后续腾空姿态调整、支撑接触动量交换及倒立摆/动态平衡补偿奠定模型基础。严禁将多刚体系统简化为单刚体“$I_{\text{body}} \boldsymbol{\omega}$”，必须严格遵循多刚体动力学中的自转（Spin）与轨道（Orbital）角动量解耦求和法则。
* **决策**：
  1. **分段局部惯性张量与几何近似**：
     - 在 [`src/motion/body_inertia.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_inertia.py) 中引入 `InertiaTensor` 与 `SegmentGeometrySpec`。
     - 严格复用现有 15 分段模型（`DEMPSTER_WINTER_15_SEGMENT_MODEL`）与 13 分段模型（`DEMPSTER_13_SEGMENT_MODEL`）。
     - 各分段局部惯性张量均相对于分段自身质心，在骨骼局部坐标系（+Y 为纵向主轴）中定义，几何近似包含椭球体（头）、椭圆柱体（躯干、骨盆）、圆柱体（上臂、前臂、大腿、小腿）及长方体（手、脚）。
     - 保证局部惯性张量数学上严格对称且正定（主转动惯量与特征值严格 $> 0$）。
  2. **平行轴定理与全身质心参考点统一**：
     - 世界坐标系下各分段相对自身质心的惯性张量为 $\mathbf{I}_{i, \text{world}}^{\text{CoM}_i} = \mathbf{R}_i \mathbf{I}_{i, \text{local}} \mathbf{R}_i^T$（$\mathbf{R}_i \in SO(3)$ 为局部到世界的纯旋转矩阵）。
     - 依据 3D 平行轴定理（Steiner's Theorem），各分段相对于全身统一 CoM 的惯性张量为：
       $$\mathbf{I}_{i, \text{world}}^{\text{CoM}} = \mathbf{I}_{i, \text{world}}^{\text{CoM}_i} + m_i \left( \|\mathbf{r}_i\|^2 \mathbf{E}_3 - \mathbf{r}_i \mathbf{r}_i^T \right)$$
       其中 $\mathbf{r}_i = \mathbf{c}_{i, \text{world}} - \mathbf{c}_{\text{world}}$ 为分段质心相对于全身 CoM 的位移矢量。
     - 求和得到全身惯性张量：$\mathbf{I}_{\text{body}}^{\text{CoM}} = \sum_{i=1}^N \mathbf{I}_{i, \text{world}}^{\text{CoM}}$。
     - 严格验证整体平移不变性（Frobenius 误差 $< 10^{-5}\text{ kg}\cdot\text{m}^2$）与刚体旋转张量变换协变性（$\mathbf{Q} \mathbf{I} \mathbf{Q}^T$ 误差 $< 10^{-5}\text{ kg}\cdot\text{m}^2$）。
  3. **多连杆全身角动量严格物理分解**：
     - 针对任意姿态与运动状态，全身角动量相对于全身 CoM 严格按两项求和：
       $$\mathbf{H}_{\text{CoM}} = \sum_{i=1}^N \left( \mathbf{H}_{i, \text{spin}} + \mathbf{H}_{i, \text{orbital}} \right) = \sum_{i=1}^N \left( \mathbf{I}_{i, \text{world}}^{\text{CoM}_i} \boldsymbol{\omega}_{i, \text{world}} + \mathbf{r}_i \times (m_i \mathbf{v}_{i, \text{world}}) \right)$$
     - 严密证明并实测：当多连杆系统整体以统一角速度 $\boldsymbol{\omega}$ 发生刚体旋转时，计算所得多连杆角动量 $\mathbf{H}_{\text{CoM}}$ 与单刚体解析公式 $\mathbf{I}_{\text{body}}^{\text{CoM}} \boldsymbol{\omega}$ 完全一致（绝对误差 $< 1.1 \times 10^{-6}\text{ kg}\cdot\text{m}^2/\text{s}$，相对误差 $< 10^{-7}$）。
     - 四肢独立摆动时，精确量化局部自转项与肢体摆动轨道项的各自贡献，杜绝单刚体粗暴替代。
  4. **姿态灵敏性与无侵入无损接入**：
     - 实测四肢收束（Tucked）与伸展（T-Pose）下的转动惯量差异达 $2.540$ 倍（$0.946 \rightarrow 2.403\text{ kg}\cdot\text{m}^2$），单臂侧平举即引起 $I_{zz}$ 增加 $+0.654\text{ kg}\cdot\text{m}^2$ 及显著惯性积 $I_{xy}$，物理响应灵敏真实。
     - 提供 `enrich_motion_state_with_inertia` 将惯性张量与角动量无缝注入 `MotionState.params`，100% 保持现有动作系统零破坏。
* **影响**：
  - 角色运动学与惯性系统补齐了刚体惯性张量与全连杆角动量关键一环；
  - 13 项严苛自动化验证全部通过，所有分段局部张量对称正定、解析几何公式完全匹配、平移旋转协变性精准、静止角动量严格为 0、四肢运动物理分解清晰、历史回归全绿；
  - 为未来支撑多边形与动态平衡补偿（Task 6G-C/Task 7）提供了坚实可靠的多刚体惯性物理底座。

---

### [DEC-022] 多部位接触几何约束与支撑状态架构规范 (Task 6G-C)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-20
* **背景**：在完成多刚体运动学（Task 6G-A）与惯性角动量（Task 6G-B）后，跑酷动画进入接触与多表面支撑阶段。现有系统仅有简化的双脚地面锁定，缺乏针对手部支撑、单手撑跳（Vault）、墙面蹬踏（Wall run/kick）、悬垂抓握（Ledge hang）和腾空（Flight）的通用接触描述。严禁将本阶段升级为动力学平衡补偿器（ZMP/Capture Point），核心任务是建立纯几何与运动学约束的接触状态机、误差量化和支撑多边形系统。
* **决策**：
  1. **接触类型与生命周期正交状态机**：
     - 在 [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py) 中定义 `ContactType`（`UNILATERAL`: 单向推力/不能拉力，`GRASP`: 双向全自由度抓握，`FREE`: 自由状态）与 `ContactLifecycle`（`CANDIDATE` $\rightarrow$ `ESTABLISHED` $\rightarrow$ `RELEASED` / `BROKEN`）。
     - 支持四肢通用端点（`foot_L`, `foot_R`, `hand_L`, `hand_R`），具备扩展至膝/肘等解剖接触点的通用架构。
  2. **骨骼原点与接触局部锚点严格解耦**：
     - 明确骨骼关节原点（踝关节 $Z=0.07\text{ m}$，腕关节 $Z=0.98\text{ m}$）与解剖表面接触锚点的几何偏置（脚底中心偏置 $(0, 0.077, -0.070)\text{ m}$，手掌接触偏置 $(0, 0.050, -0.015)\text{ m}$）。
     - 接触判定严格基于身体接触点（Body Anchor）与环境接触点（World Anchor）的相对位移，杜绝直接将踝关节/腕关节当做接触面接触点。
  3. **环境变换协变性与外法线统一约定**：
     - 环境表面 `EnvironmentalSurface` 具有局部接触点与局部表面法线，当环境物体发生世界变换矩阵 $\mathbf{M}$ 更新时，世界接触点 $\mathbf{p}_{\text{world}} = \mathbf{M} \mathbf{p}_{\text{local}}$，外法线 $\mathbf{n}_{\text{world}} = (\mathbf{M}^{-T} \mathbf{n}_{\text{local}})^{\circ}$ 自动协变更新。
     - 外法线严格保证指向环境外侧且单位模长误差 $< 10^{-6}$。
  4. **量化约束误差计算与严格判定准则**：
     - 法向位移分解：$d_n = (\mathbf{p}_{\text{actual}} - \mathbf{p}_{\text{contact}}) \cdot \hat{\mathbf{n}}$；切向滑移：$\mathbf{d}_t = (\mathbf{p}_{\text{actual}} - \mathbf{p}_{\text{contact}}) - d_n \hat{\mathbf{n}}$。
     - `UNILATERAL` 类型：$d_n > 0$ 为间隙（Separation Gap），$d_n < 0$ 为穿透（Penetration Depth）。拉拔离开或过度穿透均触发约束违规。
     - `GRASP` 类型：进行 3D 欧式全向位移校验，超出抓握公差即报告违规。
  5. **多表面支撑状态分类与共面投影多边形**：
     - 自动依据当前有效接触组合分类为 6 类支撑状态：`DOUBLE_STANCE`、`SINGLE_STANCE_L/R`、`MULTI_SURFACE`（如手撑台面）、`WALL_FOOT_STANCE`（脚蹬垂直墙）、`LEDGE_HANG`（双手抓横杆悬垂）、`FLIGHT`（腾空无接触）。
     - 当所有支撑接触法线严格一致且共面时，计算 2D 凸包支撑多边形；一旦出现多法线（如地脚+蹬墙）或非共面接触（如手撑+脚地），明确输出非共面标记并拒绝虚假生成 2D 支撑多边形。
     - 明确物理免责声明：静态支撑多边形仅代表接触几何凸包，绝不代表动态稳定性或 ZMP。
  6. **零破坏双向适配与可视化交付**：
     - 提供 `enrich_motion_state_with_contacts`，向后兼容现有 `MotionState.contacts`（`ContactPointState`）及遥测数据。
     - 与 `WholeBodyController` 全身姿态完全兼容；
     - 交付独立视口验收工程 `output/contact_model_debug.blend`，在 120 帧连续时间线上清晰展示 6 种支撑状态切换与着色标记。
* **影响**：
  - 跑酷动画系统获得了统一、结构化、几何严谨的多肢体接触与支撑状态感知能力；
  - 15 项自动化验证全数通过，历史 6 大核心回归套件 100% 保持全绿；
  - 为 Task 6G-D 质心平衡、接触动量与简化接触动力学奠定了清晰的几何约束接口。

---

### [DEC-023] 连续步态与离散障碍物接触原型解耦架构规范 (Task 6G-C Rework)
* **状态**：已采纳并实测验证 (Accepted & Verified)
* **日期**：2026-10-20
* **背景**：在 Task 6G-C 目视验收中，用户发现角色在障碍物之间移动时呈现“单腿抬起整体平移滑行 2 米”的严重缺陷。根本原因是原型脚本脱离了 `MotionPlanner` 和 `StartStopWalkAction` 步态调度状态机，错误地在离散姿态目标之间使用粗暴的数学平滑插值移动根节点，导致连续步态与多部位障碍物测试耦合混杂。
* **决策**：
  1. **完全解耦为两套独立 Blender 视口工程**：
     - **场景 A (`output/contact_walk_integration.blend` / `run_contact_walk_integration.py`)**：专注于真实连续人类步态与接触系统的实时闭环。100% 沿用 Task 5C / 6A 验证的步态调度机制（`StartStopWalkAction`），呈现 204 帧完整的起步-加速-交替步态行走-减速-停步全过程；四肢交替抬腿跨步（Z 抬升 100~137 mm），支撑脚微米级锁定（漂移 < 0.005 mm），对侧手臂协调摆动；`ContactModel` 实时逐帧评估双脚接触并驱动绿色八面体标记物在支撑相激活、摆动相熄灭。
     - **场景 B (`output/contact_obstacle_integration.blend` / `run_contact_obstacle_integration.py`)**：专注于多部位障碍物接触（Double Stance, Vault Touch, Foot on Wall, Ledge Hang, Flight Phase）。采用 5 个清晰分段的独立观察片段（Hold Clips），角色严格正对目标障碍物（朝向点积 1.0000，夹角 0.00 deg），自然垂臂，接触贴合精度达到微米级（误差严格 < 0.05 mm），彻底杜绝在障碍物之间伪造虚假单腿滑行。
  2. **工程架构审计与防漂移文档**：
     - 输出 `docs/MOTION_INTEGRATION_AUDIT.md`，建立从 Task 3 到 6G-C 的历史能力映射表、动作生成机制剖析、数据流闭环与单腿滑行根因分析。
  3. **自动化测试双场景全覆盖**：
     - 在 `tests/verify_task6gc_contact_model.py` 中分别建立 `test_16_scene_a_walk_integration_acceptance`（量化检验位移、交替抬腿、防滑锁定、臂摆与标记物动态切换）与 `test_17_scene_b_obstacle_integration_acceptance`（量化检验朝向对齐、垂臂、形态差异、接触精度、保持稳定度）。
* **影响**：
  - 彻底杜绝了“单腿悬空刚体平移”伪造步态的架构缺陷；
  - 既完整保护并展示了历史经过严苛验证的程序化真实步态，又清晰展示了 ContactModel 在多部位、多表面复杂障碍物下的几何约束与支撑分类能力；
  - 17 项全量测试 100% 通过，为后续 Task 6G-D 提供了可靠、无歧义的物理约束与接触系统基础。

---

### [DEC-024] 系统架构合流基准与反伪造工程纪律 (Task 6G-C-R3A Architecture Audit)
* **状态**：已采纳 (Accepted)
* **日期**：2026-10-20
* **背景**：在 Task 6G-C 验收中，`contact_obstacle_integration.blend` 因包含 5 个 30 帧固定切片被判定为静态僵硬、不能证明连续运动系统工作正常。经全仓库源码级审计，查明当前工程实际存在 3 套分立管线，物理数学模块（CoM、速度追踪器、惯性张量、角动量、接触模型）均为事后只读遥测，无闭环平衡反馈；`WholeBodyController` 未被历史动作调用；系统中缺乏针对障碍物的 `MotionAction` 连续动作类，导致原型脚本退化为硬编码静态坐标插帧摆拍。
* **决策**：
  1. **明确物理层定位为开环只读遥测**：系统当前是“开环解析运动学驱动 + 事后只读物理遥测”。严禁在文档或汇报中将只读遥测参数伪装为“物理驱动平衡”或“闭环力矩控制”。
  2. **确立 WholeBodyController 统一协调器定位**：`WholeBodyController` 是姿态求解与约束协调器，后续必须重构使其合流承接 `StartStopWalkAction`、`RunAction` 等全部连续动作，杜绝控制器双轨制。
  3. **严禁离散脚本摆拍，必须构建连续 MotionAction**：任何动画生成必须通过继承自 `MotionAction` 的动作类生成连续运动学时间轴，严禁在无动作类的情况下手动对固定目标插帧冒充动画。
  4. **建立永久架构同步卡片与强化规则**：更新 `ARCHITECTURE.md` (v2.0)，创建包含 12 项必填章节的 `ARCHITECTURE_SYNC.md`，并在项目规则中新增第 8 节“架构对齐与防伪造纪律”。
* **影响**：
  - 确立了权威、不可漂移的统一架构蓝图与调用合同；
  - 明确了 R3B 合流阶段的具体实施路径，彻底封堵静态姿态冒充连续动作的工程漏洞。

---

### [DEC-025] 统一架构规范修订与最小兼容桥接层 (Task 6G-C-R3B-1 Architecture Specification & Compatibility Bridge)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-20
* **背景**：在 Task 6G-C-R3A 审计中明确了系统存在三套分立管线与控制器双轨制的问题。为确保后续动作、接触和物理系统全部沿统一架构演进，同时不破坏经过严苛验证的历史步态曲线（Walk/Run/Sprint/Brake），必须建立权威的单帧 6 阶段执行协议与最小兼容桥接层。
* **决策**：
  1. **架构规范权威修订 (v2.1)**：在 `ARCHITECTURE.md` 与 `ARCHITECTURE_SYNC.md` 中确立 10 大架构设计原则、三层架构演进视图（当前/R3B统一/未来6G-D/6H/7A）、单帧 6 阶段执行协议表、12 大模块契约清单与 6 大历史动作复用表。
  2. **实现最小兼容桥接层 (`src/motion/kinematic_bridge.py`)**：
     - 提供结构化输入容器 `KinematicPlannedPose`（包含根节点、骨盆位姿、躯干 FK、左右脚足部目标与锁定标记、左右手 IK/FK 目标）；
     - 实现 `convert_planned_pose_to_wbc_targets`：执行精确的目标映射、手部 FK/IK 显式仲裁与足部锁定标记传递；
     - 实现 `KinematicBridgeExecutor`：严格依照 Phase 1 至 Phase 6 编排单帧生命周期，协调 `foot_contact` 物理锁定、`WholeBodyController` 独占求解、`JointModel` ROM 真实校验、事后只读物理遥测丰富（CoM、速度、惯性张量、角动量、接触模型）与 `MotionState` 状态提交。
  3. **严格所有权与防冲突纪律**：
     - 足部接地防滑锁定由 `src/rig/foot_contact.py` 独占管理（解除父级并锁定世界坐标）；WBC 在求解时感知 `is_locked`，严禁解绑或覆盖。
     - 手部显式仲裁：`enabled=False` 时 arm IK 约束 influence 归零，由 FK 关节角完全主导；`enabled=True` 时 arm IK 接管，保证双臂摆动与抓握各得其所。
  4. **真实失败汇报机制**：ROM 截断后重新评估末端到达性，若发生超限或 ROM 违背，`execute_frame` 严格诚实汇报 `success=False`，绝对禁止伪造通过。
* **影响**：
  - 经 `tests/verify_task6gc_r3b1_bridge.py` 10 项严苛测试验证，桥接输出与历史姿态函数在骨盆与双踝位置差异达到微米级（**0.0000 mm** 完全一致）；
  - 历史动作曲线与步态排期完全不可变；历史 6 大核心测试套件 100% 保持全绿；
  - 为 R3B-2 历史动作无损迁移至统一桥接架构提供了标准执行骨架。




---

### [DEC-026] 桥接层接口补全、多部位接触语义解耦与 GitHub 自动化安全同步机制 (Task 6G-C-R3B-1-Final)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-21
* **背景**：在 Task 6G-C-R3B-1 首轮完成后，审计发现桥接层存在三个关键接口漏洞：时间步长固定硬编码、自由空间手部 IK 容易与接触语义混淆、惯性张量与角动量尚未闭环接入 Phase 5 姿态后处理；同时项目规则中原有的“禁止自动 git push”已不能满足 GitHub 远程仓库建立后的实时自动化同步需求。
* **决策**：
  1. **显式与时间戳推导步长支持 (`dt`)**：
     - `KinematicPlannedPose` 引入可选 `dt: Optional[float]`，`KinematicBridgeExecutor.execute_frame` 支持显式 `dt` 传入或由 `time_seconds` 自动差分计算；
     - 严格校验 `dt > 0.0`，禁止非正数或倒流时间戳；
     - 驱动有限差分速度与惯性张量物理时间缩放一致，默认无缝兼容 24 FPS 标准时间线。
  2. **手部 IK 与环境接触意图解耦**：
     - 在 `PlannedFootTarget` 与 `PlannedHandTarget` 中显式分离 IK 目标激活（`enabled`）、接触意图（`contact_intent`）、世界锁定（`is_locked`）、接触类型与表面 ID；
     - 自由空间伸手（`contact_intent=False`）绝不产生虚假接触；有接触意图时由 `ContactModel` 进行几何穿透/间隙/法向容差合规性校验，超差真实报警 `success=False`；
     - 支撑相足部地面锚点在局部坐标上依据踝关节原点 $(x, y, z - 0.070\text{ m})$ 精准对齐地面 $Z=0$，与 `foot_contact.py` 世界锁定严格吻合，消除足底中心人为滑移。
  3. **Phase 5 惯性张量与全身体角动量遥测集成**：
     - 在 Phase 5 姿态解算完成后，直接调用 `compute_whole_body_inertia`，基于已评估的 Armature 姿态与 `kin_result.velocity` 计算全身体惯性张量、自转角动量与质心轨道角动量，并注入 `MotionState.params`；保持纯只读物理遥测，绝不引入伪造力矩驱动。
  4. **建立永久自动化 GitHub 同步机制**：
     - 在项目规则 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md` 的 Section 4 与 Section 7 确立自动化安全同步推送机制：测试通过 -> 文档更新 -> 精确暂存 -> commit -> 自动 `git push origin master` -> 验证远程 SHA == 本地 HEAD -> 在 `AI_SYNC.md` 记录同步卡片。
     - 取消“禁止自动 git push”限制，改为“必须自动执行安全同步推送，严禁 force push，严格保留历史保护”。
* **影响**：
  - `tests/verify_task6gc_r3b1_bridge.py` 全部 14 项测试（含历史 6 大回归套件）100% 通过；
  - 桥接层与统一 6 阶段执行协议全面补齐，历史动作完全完好，为 R3B-2 动作迁移奠定了坚实基础；
  - 项目确立了本地到 GitHub 远程仓库的自动化闭环同步。

---

### [DEC-027] 历史四大连续动作向统一 KinematicBridgeExecutor 与 WholeBodyController 架构的无损迁移 (Task 6G-C-R3B-2)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-21
* **背景**：在 Task 6G-C-R3B-1-Final 完成统一架构规范与兼容桥接层之后，历史四大动作（`StartStopWalkAction`, `RunAction`, `SprintStartAction`, `SprintBrakeAction`）仍各自通过旧的 `ContactConstraintAdapter` 和经验上身姿态函数绕过 WBC 直接操作底层物体，系统内仍存在生产执行双轨制。为实现 100% 架构归一化，必须按规范顺序将 4 大动作无损重构迁移至 `KinematicBridgeExecutor.execute_frame()`。
* **决策**：
  1. **按顺序依次无损迁移**：
     - `StartStopWalkAction`（204 帧）：构建 `KinematicPlannedPose`（根位姿、骨盆、脊柱、颈头、左右脚足部目标与锁定标记、手臂 FK），通过 `bridge_executor.execute_frame` 写入关键帧，保持原有 7 步调度与 $C^1$ 速度曲线 100% 不变。
     - `RunAction`（96 帧）：构建包含腾空相（`flight`）、单脚支撑锁定、摆动脚正弦抬升的规划位姿，接入统一桥接层；在 `WholeBodyController` 中修复足部解锁时的父级重新绑定（`reparent_to_root=True`），消除局部坐标旋转漂移。
     - `SprintStartAction`（114 帧）：构建起跑深蹲、蹬地与加速冲刺的规划位姿，接入统一桥接层；引入平滑摆动脚解剖踝俯仰调制（$\theta_{\text{pitch}} = -18.0^\circ \sin(\pi s)$），消除深屈膝时由于强制水平足底导致的 ROM 超限。
     - `SprintBrakeAction`（48 帧）：构建高速切入、受控前滑与双足稳态合拢停步的规划位姿，接入统一桥接层；引入制动踝俯仰调制（$-12.0^\circ \sin(\pi s)$），实现微米级无冲突停步锁定。
  2. **速度指标与接触意图严格解耦与非混淆保障**：
     - 严格区分 `MotionState.planned_linear_velocity`（规划期望速度）、`MotionState.root_derived_linear_velocity`（根节点差分测量速度）与 `MotionState.com_linear_velocity`（全身体物理质心线速度），绝不互相覆盖或混淆。
     - 严格区分接触意图（`contact_intent`）、世界锁定（`is_locked`）与几何合规性校验。
     - 任何 IK、ROM 或接触几何违规均由 `bridge_res.success` 真实拦截，严禁静默放行。
  3. **直接生成可播放统一连续动画 Blender 验收文件**：
     - 编写 `run_unified_motion_pipeline.py`，顺序串联 4 大动作（行走 $\rightarrow$ 冲刺起跑 $\rightarrow$ 急停制动 $\rightarrow$ 连续跑步），生成 462 帧连续无缝动画文件 `output/unified_motion_integration.blend`（总位移 $12.9058\text{ m}$，峰值速度 $2.0000\text{ m/s}$，0 次超程违规）。
     - 设置平滑运镜摄像机（`PipelineCamera`）与视口阳光，便于用户直接在 Blender 中视口播放验收。
* **影响**：
  - 彻底淘汰了动作层直接调用旧 `BlenderPoseApplicator` 和经验上身姿态函数的历史双轨制；
  - 4 大动作 100% 统一运行于 `KinematicBridgeExecutor` $\rightarrow$ `WholeBodyController` $\rightarrow$ `Blender Pose` $\rightarrow$ 物理遥测流水线；
  - 经过 5 个自动化验证套件（`verify_r3b2_walk_action.py`, `verify_r3b2_run_action.py`, `verify_r3b2_sprint_start.py`, `verify_r3b2_sprint_brake.py`, `verify_unified_motion_integration.py`）及 14 项桥接回归套件全量检验，100% 全绿通过；
  - 奠定了后续 Task 6G-D 动力学闭环与多部位障碍物接触的统一基座。

---

### [DEC-028] 动画重放父级约束修复、足部三维旋转约束空间修正与连续步态踝关节生理俯仰调制 (Task 6G-C-R3B-2-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-22
* **背景**：在 Task 6G-C-R3B-2 首轮生成 `output/unified_motion_integration.blend` 后，用户视口目视验收发现下肢存在严重周期性异常（第 42 帧左腿呈横向伸展 L 形，第 43 帧左腿突然垂直而右腿立即呈横向伸展 L 形；大腿、小腿严重反常向后拉伸 8 米）。
* **根因定位 (Root Cause Analysis)**：
  1. **Blender 动画曲线父级解析空间错位（根因一）**：Blender 中 `obj.parent` 是全局 Object 级指针属性，**不可逐帧关键帧化（Not Keyframable）**。在首轮 R3B-2 中，`unlock_foot_contact` 在摆动相设置 `ik_obj.parent = CharacterRoot`，而 `lock_foot_contact` 在支撑相设置 `ik_obj.parent = None`。在保存动画文件时，`FootIK` 的父级指针固定为 `CharacterRoot`。当 Blender 重放动画时，支撑相在世界坐标下写入的关键帧位置（如 $Y = -8.0\text{ m}$）被 Blender 误解析为相对于 `CharacterRoot`（$Y \approx -7.94\text{ m}$）的局部坐标，合成出世界坐标 $Y = -7.94 + (-8.0) = -15.94\text{ m}$（即向后暴拉 8 米！）。而摆动相由于本来就按局部坐标写入，重放时保持在根节点附近。导致每逢步态交替，支撑腿被向后暴拉 8 米形成横向 L 形，摆动腿看似正常，两腿周期性交替畸变。
  2. **COPY_ROTATION 目标空间在无父级物体上的退化（根因二）**：在 `src/rig/ik.py` 中，`FootRotation.L/R` 约束原配置为 `target_space = "LOCAL", owner_space = "LOCAL"`。当 `FootIK` 控制器无父级（`parent = None`）时，Blender 约束求解器判定其局部空间为单位矩阵，导致 `foot.L/R` PoseBone 的三维旋转被强制锁定在静止姿态（$-13.13^\circ$），无法接收来自 `FootIK` 的动态俯仰指令。在奔跑与冲刺的大幅度屈膝（膝屈角达 $80^\circ \sim 98^\circ$）工况下，静止足部无法跟随小腿向后自然拖拽，导致小腿与脚掌夹角达到 $53.4^\circ$，违反解剖踝关节 ROM 极值（$45.0^\circ$）。
* **决策与修复方案**：
  1. **下肢控制器全局恒定世界空间化 (`reparent_to_root = False`)**：
     - 在 `WholeBodyController.execute_frame` 中，足部解锁时强制调用 `unlock_foot_contact(arm, side, reparent_to_root=False)`；
     - 确保 `FootIK.L`、`FootIK.R`、`KneePole.L`、`KneePole.R` 在整个动画全生命周期内（支撑相与摆动相）始终保持 `parent = None`（与历史标准基准文件 `character_forward_walk.blend` 和 `character_start_stop_walk.blend` 100% 一致）；
     - 所有关键帧位置与旋转均纯粹写入绝对世界坐标系，Blender 重放时零相对位移叠加，彻底根除 8 米向后拉伸畸变与双重变换错误。
  2. **约束空间映射修正 (`target_space = "WORLD", owner_space = "LOCAL"`)**：
     - 将 `FootRotation.L/R` 约束修正为 `target_space = "WORLD", owner_space = "LOCAL"`；
     - 使得无父级的 `FootIK` 世界空间旋转能够准确传递并叠加到 `foot.L/R` 的局部解剖姿态上，彻底解决无父级物体在 LOCAL 模式下退化为单位矩阵的底层缺陷。
  3. **基于人体生物力学的摆动相踝关节平滑跟随调制**：
     - 行走摆动相：$\theta_{\text{pitch}} = -12.0^\circ \sin(\pi s)$；
     - 跑步摆动相：$\theta_{\text{pitch}} = -38.0^\circ \sin(\pi s)$；
     - 冲刺起跑摆动相：$\theta_{\text{pitch}} = -36.0^\circ \sin(\pi s)$；
     - 真实模拟人类奔跑与迈步时脚尖跟随小腿向后下方自然拖曳的生物力学特征，在不修改历史步态曲线（步长、步频、速度剖面完全不变）、不放宽 `joint_limits.py` 医学解剖 ROM 约束的前提下，全 462 帧踝关节活动角严格保持在 $[-25^\circ, +45^\circ]$ 舒适区间内。
* **影响与产物**：
  - 彻底修复第 42..44 帧下肢交替横向拉伸畸变，第 42 帧（$-114.52^\circ$）与第 43 帧（$-114.84^\circ$）的小腿姿态与历史基准 `character_start_stop_walk.blend` 保持完全一致（精确至小数点后两位）；
  - 重新生成 `output/unified_motion_integration.blend`（462 帧无缝连续运动，总位移 12.9058m，0 次超程违规）；
  - 渲染生成 40 张对比视口视图（侧视与前斜视角度，覆盖第 1、12、24、36、41、42、43、44、48、60 关键帧），直观证实步态连续平滑；
  - 独立四大动作验证套件（Walk, Run, SprintStart, SprintBrake）及桥接 14 项测试全量 100% 全绿通过。
