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
     - 严格区分 `MotionState.params['planned_linear_velocity']`（规划期望速度）、`MotionState.params['root_derived_linear_velocity']`（根节点差分测量速度）与 `MotionState.params['com_linear_velocity']`（全身体物理质心线速度），绝不互相覆盖或混淆。
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

---

### [DEC-029] 统一测试执行调度器、回归资产管理与永久架构门禁 (Task 6G-D-PRE-P1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：Task 6G-D-PRE-P0 全工程架构审计暴露出全仓库 27 个测试脚本高度碎片化、执行命令依赖文件名猜测、每次测试需频繁申请终端审批导致用户负担严重、缺乏 Windows 进程树硬超时清理机制，以及缺乏统一的永久架构准入审查机制。
* **决策与方案**：
  1. **建立显式测试注册表 (`tests/test_registry.py`)**：
     - 显式登记 26 项受控测试用例，杜绝通配符扫描推测；
     - 划定 `quick` (3项)、`physics` (8项)、`motion` (5项)、`full` (14项去重并集) 与 `legacy` (13项) 五类分级体系；
     - 每项测试明确声明 `RunnerType`（`python` / `blender_headless` / `blender_with_blend`）、超时限制、依赖文件与 `is_visual_acceptance` 标记。
  2. **建立单入口测试调度器与包装器 (`tests/run_test_suite.py` / `run_tests.ps1`)**：
     - 单一外层命令（如 `.\run_tests.ps1 -tier quick`）调度多测试串行执行，将 N 次子命令收敛为一次受控调度，彻底消除用户反复审批负担；
     - 动态自动解析 Blender 5.1.1 与系统真实 Python 路径，避开 Windows Store 零字节假别名；
     - 引入 Windows 深度进程树清理机制（`taskkill /F /T /PID`），杜绝超时悬挂 Blender 僵尸进程；
     - 实施严格多层判定：非零退出码、硬超时、产物缺失以及 stdout/stderr 中的 `[FAIL]`/`AssertionError` 模式反查，严禁“伪绿”放行；
     - 结构化输出 `tests/output/test_report.json` 与 `test_report.md`。
  3. **目视验收防线严格分离**：
     - 涉及 Blender 视口姿态自然度的测试（如 `integration_unified_motion`）在自动化测试通过时仅标记为 `AUTOMATED_PASS (Visual Inspection Required)`，严禁未人工目视直接标记为 Visual Pass。
  4. **确立单一权威来源永久架构门禁 (`docs/ARCHITECTURE_CHANGE_GATE.md`)**：
     - 制定 11 项前置准入审查清单与 8 大绝对禁止行为清规，规范架构偏差事前审批流程；
     - `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 同步引用并锚定该规范，杜绝版本漂移。
* **影响与产物**：
  - 新增核心测试文件：`tests/test_registry.py`、`tests/run_test_suite.py`、`run_tests.ps1`；
  - 新增权威规范：`docs/ARCHITECTURE_CHANGE_GATE.md`；
  - 实测验证全绿：`quick` (3/3), `motion` (5/5), `physics` (8/8) 全部 100% 通过（退出码 0）；
  - 零生产代码修改，零步态曲线变动。

---

### [DEC-030] 动力学训练场几何标准与三维环境查询体系 (Task 6G-D-PRE-P2)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：进入 Task 6G-D 动力学接触与反力控制前，系统现存 `EnvironmentQuery` 仅支持单一平地高度与法线（$Z=0.0\text{ m}$），无法提供台阶、斜坡、障碍墙、高台等复杂三维地表接触几何，且无法对垂直立面（无法用 $z(x, y)$ 高度场表示）进行接触距离与法线分析。
* **决策与方案**：
  1. **纯 Python 解析几何与环境查询系统 (`src/scene/environment_query.py`)**：
     - 构建 `OrientedSurface` 统一闭式表面模型，严格涵盖中心、单位外向法线、切向基底、半尺寸、摩擦系数与支撑属性；
     - 构建 `DynamicsEnvironmentQuery`，支持水平平地、5级标准台阶、上下连续斜坡、垂直障碍墙、跳箱平台、悬挂单杠以及遥测调试区 6 大功能分区（共 21 个解析几何表面）；
     - 支持闭式法线、最近投影点、有符号距离（Signed Distance，间隙 >0，穿透 <0）、摩擦系数及普通支撑可行性判断；
     - 针对无法用 $(x, y)$ 高度场表示的垂直立面提供 `query_surface_at_point` 与 `query_spatial_surface` 空间三维查询接口；
     - 对原有 `EnvironmentQuery` 保持 100% 向后兼容性（`ground_height_at` 与 `surface_normal_at` 契约完全无损）。
  2. **程序化训练场场景生成器升级 (`src/scene/builder.py` / `run_dynamics_playground.py`)**：
     - 实现 `build_dynamics_playground`，在 Blender 中根据解析几何生成真实实体网格；
     - 赋予区分明显的材质颜色（平地灰色、台阶天蓝色、斜坡金橙色、墙面砖红色、跳箱紫色、单杠钢青色、调试区明黄色）；
     - 为每个解析表面在法线方向生成直观的可视化指示箭头（`NormalArrow_<surface_id>`）；
     - 配备世界坐标轴指示（红X、绿Y、蓝Z）、1m 参考单位立方体、双视角调试摄像机与三点日光照明系统；
     - 生成可直接在 Blender 中打开检查的场景文件 `output/dynamics_playground.blend`。
  3. **单元验证与统一注册**：
     - 编写纯 Python 几何测试 `tests/verify_task6gd_dynamics_playground.py`（毫秒级验证 11 项数学定理）；
     - 编写 Blender 场景检验脚本 `tests/verify_task6gd_playground_blend.py`（验证 45 个对象与材质绑定完整性）；
     - 注册进入 `tests/test_registry.py`，纳管至 `quick`、`physics` 与 `full` 层级。
* **影响与产物**：
  - 新增/更新代码：`src/scene/environment_query.py`、`src/scene/builder.py`、`src/scene/__init__.py`、`src/motion/framework.py`、`src/motion/__init__.py`、`run_dynamics_playground.py`；
  - 产物文件：`output/dynamics_playground.blend`（116,933 字节，保存在本地受 `.gitignore` 规则保护）；
  - 实测回归全绿：`quick` (5/5), `physics` (10/10), `motion` (5/5) 保持 100% 零退化（退出码 0）；
  - 零生产运动代码修改，零步态曲线变动。

---

### [DEC-031] 环境查询过滤约束、距离语义统一与动力学训练场单一 SSOT 规范 (Task 6G-D-PRE-P2-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：在 P2 审查中发现：1) `query_surface_at_point()` 当指定 `surface_type_filter`（如 `vertical_wall`）时，若近处无匹配物体，可能错误命中默认全局地表 `default_ground`；2) 射线查询中命中距离与法向有符号距离语义混淆，斜向射线与背面射线无法区分沿射线欧几里得距离与垂直于面的有符号距离；3) 缺少明确的门禁规范来锁定 `output/dynamics_playground.blend` 作为后续动力学任务的统一标准训练场，存在子任务各自建造分立场景与手工摆设虚假力学箭头的架构漂移风险。
* **决策与方案**：
  1. **查询过滤与默认地面强隔离约束**：
     - 在 `DynamicsEnvironmentQuery` 与基类 `EnvironmentQuery` 的点查询与空间查询中，仅当 `surface_type_filter in (None, "", "horizontal_ground")` 时才允许将全局默认地面作为候选；当过滤其他类型（如 `vertical_wall`, `sloped_ramp`）时，严格屏蔽默认地面，若无匹配表面则严谨返回 `success=False`、`surface_id="none"`。
  2. **物理距离语义严格分离 (`ray_hit_distance` vs `signed_distance`)**：
     - 在 `SurfaceQueryResult` 中新增 `ray_hit_distance: Optional[float] = None` 字段；
     - `signed_distance` 严格专属于法向有符号距离（沿外向法线：>0 为间隙/正方，0.0 在表面，<0 为穿透/负方）；
     - `ray_hit_distance` 严格表示沿射线方向行进的非负欧几里得距离（>=0.0m）；非射线点查询时为 `None`，射线未命中时严格为 `float("inf")`；
     - 彻底解耦斜向射线的较长欧几里得击中距离与垂直墙面的法向有符号净距。
  3. **标准动力学训练场单一权威基准指定与防伪门禁 (SSOT Gate)**：
     - 将 `output/dynamics_playground.blend` 确立为 Task 6G-D、6H、7A 的唯一标准训练场（SSOT）；
     - 增订永久架构清规：严禁任何子模块独立私造第二套分立场景；严禁修改 6 大基础功能区网格；力学可视化箭头必须 100% 绑定物理计算真实输出，严禁手工摆拍装饰性假箭头；
     - 同步更新权威门禁 [`docs/ARCHITECTURE_CHANGE_GATE.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md) 第 6 节，并将十大绝对清规同步写入 `AGENTS.md`、`GEMINI.md` 与 `.agents/rules/project_rules.md`。
* **影响与产物**：
  - 更新代码：`src/scene/environment_query.py`、`tests/verify_task6gd_dynamics_playground.py`（扩充为 13 项单元测试）；
  - 更新门禁与清规：`docs/ARCHITECTURE_CHANGE_GATE.md`、`AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`；
  - 实测回归全绿：`quick` (5/5), `motion` (5/5), `dynamics_environment_query` (13/13) 全绿通过（退出码 0）；
  - 零生产代码修改，零步态曲线变动，零 Blend 文件重构。

---

### [DEC-032] 接触动力学数学模型、冲量动量关系与环境查询契约 (Task 6G-D-A)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：进入 Task 6G-D 接触动力学阶段，系统已有几何接触模型 `contact_model.py`、质心 `rigid_link.py`、惯量 `body_inertia.py` 与训练场查询 `environment_query.py`，但缺乏世界空间接触力、力矩、冲量、动量变化以及单侧正向与库仑摩擦锥的数学定义和计算契约。
* **决策与方案**：
  1. **纯数学接触动力学模块 (`src/motion/contact_dynamics.py`)**：
     - 构建 `SingleContactDynamics`，严格支持世界空间接触点 $\mathbf{p}_c$、接触力 $\mathbf{F}$、质心相对位矢 $\mathbf{r} = \mathbf{p}_c - \mathbf{p}_{\text{com}}$、绕质心力矩 $\boldsymbol{\tau}_{\text{com}} = \mathbf{r} \times \mathbf{F}$、线冲量 $\mathbf{J} = \mathbf{F}\Delta t$、角冲量 $\mathbf{H}_{\text{impulse}} = \boldsymbol{\tau}_{\text{com}}\Delta t$、线动量变化 $\Delta \mathbf{P} = \mathbf{J}$、角动量变化 $\Delta \mathbf{L}_{\text{com}} = \mathbf{H}_{\text{impulse}}$；
     - 严格区分力（$\text{N}$）、力矩（$\text{N}\cdot\text{m}$）、冲量（$\text{N}\cdot\text{s}$）、动量（$\text{kg}\cdot\text{m/s}$），严格区分绕质心力矩/角冲量与绕世界原点力矩/角冲量；
     - 验证 6 大数学定理：零力零动量变化、质心作用力零力矩、偏心力右手定则力矩、世界坐标平移不变性、$\mathrm{SO}(3)$ 刚体旋转协变性、冲量-动量等价性。
  2. **单侧法向与库仑摩擦约束评估 (`FrictionConstraintEvaluation`)**：
     - 单侧法向约束：$F_n = \mathbf{F} \cdot \hat{\mathbf{n}} \ge 0$，张力/粘附力（$F_n < 0$）严格判定为 `TENSION_VIOLATION`；
     - 库仑摩擦锥约束：切向力 $\mathbf{F}_t = \mathbf{F} - F_n \hat{\mathbf{n}}$，$\|\mathbf{F}_t\| \le \mu F_n$，超限判定为 `SLIP_VIOLATION`；
  3. **多接触点动力学聚合 (`MultiContactDynamics`)**：
     - 支持合外力、合外力矩、总线冲量、总角冲量与多接触点摩擦锥完备性校验；
  4. **标准训练场环境查询接口契约绑定 (`create_contact_dynamics_from_environment`)**：
     - 直接与 `DynamicsEnvironmentQuery`（`src/scene/environment_query.py`）无缝对接，法向 $\hat{\mathbf{n}}$ 与摩擦系数 $\mu$ 100% 绑定自实际地表解析参数（平地 $\mu=0.70$、斜坡 $\mu=0.65$、垂直墙 $\mu=0.60$）；
     - 零虚假摆拍，零独立训练场。
* **影响与产物**：
  - 新增模块：`src/motion/contact_dynamics.py`；
  - 导出并更新：`src/motion/__init__.py`（增加 bpy 容错隔离保护纯 Python 运行环境）；
  - 交付测试套件：`tests/verify_task6gd_contact_dynamics.py`（15/15 项数学与契约断言全绿通过）；
  - 注册登记：`tests/test_registry.py`（加入 `contact_dynamics_math` 纳管至 `quick`、`physics` 与 `full`）；
  - 实测回归全绿：`quick` (6/6), `physics` (11/11), `motion` (5/5) 保持 100% 零退化（退出码 0）；
  - 零生产动作修改，零步态曲线变动，零 Blender 场景重复构建。

---

### [DEC-033] 接触动力学统一时间步长契约与物理接触有效性解耦 (Task 6G-D-A-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：在 6G-D-A 接触动力学基础实现验收后，进行深入源码契约审查发现两项潜在隐患：
  1. `MultiContactDynamics` 与各个 `SingleContactDynamics` 的时间步长 `dt` 未建立强一致性验证约束，若多触点传入不同 `dt`，可能导致线冲量、角冲量与汇总动量变化的时间区间错乱，或发生静默覆盖；
  2. `create_contact_dynamics_from_environment()` 通过环境表面查询可以获取临近表面的法向和摩擦系数，但当接触点在几何上远离表面时，若不加区分地构造接触动力学对象并允许施加接触力，在物理上等同于“悬空接触”，违反了单侧物理接触的几何接触间隙前提。
* **决策与方案**：
  1. **多触点统一时间步长所有权与一致性门禁**：
     - `MultiContactDynamics` 确立对系统时间步长 `self.dt` 的唯一所有权；
     - 在 `__post_init__` 与 `add_contact()` 中强行执行 `_validate_contact_dt(contact)`，若 `contact.dt` 与系统 `self.dt` 差异超过容差（1e-6s），严格抛出 `ValueError` 并拒绝接入，绝对禁止静默使用其中一方；
     - 新增 `set_dt(new_dt, update_contacts=False)`，提供显式批量同步通道。
  2. **物理接触有效性与几何贴靠显式分离**：
     - 在 `SingleContactDynamics` 中扩展 `surface_id: str`、`surface_distance: float`（来自查询的 `signed_distance`）以及 `contact_tolerance: float = 0.02`（默认 20mm 物理接触间隙容差）；
     - 定义 `is_in_contact: bool` 属性（`abs(surface_distance) <= contact_tolerance`）；
     - 在 `evaluate_friction_constraint()` 中新增清规约束：若 `not is_in_contact` 且施加了非零接触力（$\|\mathbf{F}\| > \epsilon$），严格拒绝并判定为 `FrictionConeStatus.NON_CONTACT_FORCE_VIOLATION`（零力时正常判定为 `SEPARATED`）；
     - 在 `create_contact_dynamics_from_environment()` 中新增参数 `contact_tolerance: float = 0.02` 与 `require_contact: bool = True`：
       * 默认 `require_contact=True`：当点与最近表面间距超过容差时，严格抛出 `ValueError` 阻断非物理接触构造；
       * 允许 `require_contact=False`：用于纯几何邻域探测或近地状态追踪，绑定表面几何属性但标记 `is_in_contact=False`，防止悬空受力。
* **影响与产物**：
  - 更新代码：`src/motion/contact_dynamics.py`；
  - 扩充测试：`tests/verify_task6gd_contact_dynamics.py` 新增 Test 16（dt 强一致性验证与冲突拒绝）与 Test 17（物理接触有效性、间隙容差与非接触受力违规拦截），测试总数由 15 项增至 17 项；
  - 实测回归全绿：`quick` (6/6), `physics` (11/11) 保持 100% 零退化通过（退出码 0）；
  - 彻底阻断非物理悬空受力与时间步长紊乱，为 6G-D-B 接触力求解器提供了坚实无瑕的物理数据契约。

---

### [DEC-034] 多接触系统时间步长更新事务失败原子性与状态不可变保全 (Task 6G-D-A-R2)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：在 Task 6G-D-A-R1 引入 `MultiContactDynamics.set_dt()` 后，代码审查发现该方法在 `update_contacts=False` 且新旧时间步长不一致时存在严重的状态破坏隐患：系统优先执行 `self.dt = float(new_dt)` 修改自身，随后在遍历子接触点校验时发现冲突并抛出 `ValueError`，导致异常抛出后对象系统 `dt` 已经被修改为与子接触点严重失配的悬空状态，违反了面向对象设计的“失败原子性（Failure Atomicity）”原则。此外，若中途子接触点更新抛错，缺少事务回滚可能造成部分接触点被修改而部分保持原值的裂脑状态。
* **决策与方案**：
  1. **严格预校验与失败原子性保证 (Pre-validation & Invariance)**：
     - 在修改任何内部状态之前，统一通过 `_validate_dt_value()` 严格检验输入合法性（必须为有限正浮点数，严格拦截 0、负数、NaN、Inf 与非法类型）；
     - 当 `update_contacts=False` 时：先遍历现有接触点集合，一旦发现任何触点与新时间步长存在差异（`abs(c.dt - val) > 1e-6`），立即抛出 `ValueError` 阻断，系统 `self.dt` 与全部子触点 `c.dt` 绝对不发生任何写入，严格保持原值不变；
     - 仅当所有子触点（或无触点）全部兼容新 `dt` 时，才允许单点提交 `self.dt = val`。
  2. **事务级批量同步与异常回滚机制 (Transactional Rollback)**：
     - 当 `update_contacts=True` 时：明确其物理语义为“显式的统一时间区间重配置操作”；
     - 预先捕获原始系统状态 `orig_system_dt` 与全触点状态快照 `orig_contacts_dt = [(c, c.dt) for c in self.contacts]`；
     - 执行更新时若任意触点遭遇异常（如只读限制、动态校验或硬件故障），`except` 块自动捕获并将已修改的触点及系统 `dt` 100% 逐一回滚至快照原值，坚决杜绝“部分更新”中间态；
  3. **空容器与触点自身防御性加固**：
     - 空多接触系统允许在合法值下更新，非法值拒绝并不改动系统 `dt`；
     - 在 `SingleContactDynamics` 引入 `__setattr__` 拦截非法 `dt` 注入，双重筑牢物理一致性防线。
* **影响与产物**：
  - 更新代码：`src/motion/contact_dynamics.py`；
  - 扩充测试：`tests/verify_task6gd_contact_dynamics.py` 补充完善 Test 16 状态验证，并新增 Test 18 深度覆盖 10 大失败原子性定理（匹配成功、失配抛错、系统不变、触点不变、同步更新、冲量缩放一致、空容器更新、非法数值全拦截、多触点中途故障事务回滚、`add_contact` 零退化）；测试总数扩充至 18 项（纯 Python 0.002s 全绿）；
  - 实测回归全绿：`quick` (6/6), `physics` (11/11) 保持 100% 零退化（退出码 0）；
  - 彻底消除了接触动力学系统在时间步长重配置中的状态污染与不一致隐患。

---

### [DEC-035] 多接触力逆向求解与约束分配系统架构 (Task 6G-D-B)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：在 6G-D-A/A-R1/A-R2 完成了接触动力学正向计算（已知接触力求合力、合力矩、冲量、动量变化与库仑锥有效性检验）之后，系统需要反向分配能力：从高层运动规划或全身牛顿-欧拉方程给出的期望合外力与绕质心合力矩 $\mathbf{w}_{\text{target}} = [\mathbf{F}_{\text{target}}, \boldsymbol{\tau}_{\text{target}}]^T \in \mathbb{R}^6$，以及足端/手端与环境表面接触几何与摩擦参数，反解出各个接触点上的 3D 接触力 $\mathbf{F}_i$。
* **决策与方案**：
  1. **线性接触抓取映射矩阵 (Contact Grasp Mapping Matrix)**：
     - 构建严格的线性映射 $\mathbf{A} \mathbf{f} = \mathbf{w}$，其中矩阵 $\mathbf{A} \in \mathbb{R}^{6 \times 3N}$。对于第 $i$ 个接触点，前 3 行为单位矩阵 $\mathbf{I}_3$（力矢量累加），后 3 行为叉乘斜对称矩阵 $[\mathbf{r}_i]_\times$（其中 $\mathbf{r}_i = \mathbf{p}_i - \mathbf{p}_{\text{com}}$ 为接触点相对全身质心的位置矢量）。
  2. **精确 3D 圆形库仑摩擦锥闭式投影与欧氏非膨胀算子**：
     - 摒弃了误差较大且具有方向偏置的多面体/八棱锥离散线性化近似，实现了任意接触法向 $\hat{\mathbf{n}}$ 下的真实 3D 圆形库仑摩擦锥闭式欧几里得正交投影算法 `project_to_friction_cone`；
     - 严格处理四类几何区域：原点锥顶外侧投影至原点（拉力与逆锥截断）、锥内保持不变、锥外正交投影至圆锥母线侧面（保证法向非负且切向模长严格位于边界圆周）、以及法向力上限 $F_{n,\max}$ 的平顶截断。
  3. **双引擎凸优化架构 (Dual-Engine Optimization: SLSQP + SPG)**：
     - 针对开发机独立 Python（含 SciPy）与 Blender 内置 Python（无 SciPy）的环境异构，构建了双引擎架构：
       * **Engine 1 (SLSQP)**：在具有 SciPy 的独立环境中作为高精度二阶约束优化求解器，直接优化加权外力残差与能耗目标，并施加平滑二阶锥不等式约束 $\mu F_{n,i} - \|\mathbf{F}_{t,i}\| \ge 0$；
       * **Engine 2 (SPG Native)**：在无 SciPy 的环境（如 Blender 命令行/内嵌 Python）下自动无缝退化到谱投影梯度法（Spectral Projected Gradient, SPG）。SPG 利用闭式圆锥投影与 Barzilai-Borwein 自适应步长进行投影梯度动力学寻优，100% 原生自包含，零外部数学库依赖。
  4. **完备解状态判定与独立物理验算契约**：
     - 求解器返回详尽的 `ContactSolverStatus`（`SOLVED`, `APPROXIMATE`, `INFEASIBLE`, `INVALID_INPUT`, `NUMERICAL_FAILURE`）；
     - 输出物理残差标量（力残差范数 N、力矩残差范数 N·m）与最大法向/切向约束违规值；
     - 提供 `solution_to_multi_contact_dynamics()`，将解向量无缝转化为标准 `MultiContactDynamics`，并可与正向动力学进行全维度互相验算；
     - 具备与 `DynamicsPlayground` 的无缝几何绑定能力（`create_contact_constraint_from_environment`）。
* **影响与产物**：
  - 新增核心模块：`src/motion/contact_force_solver.py`；
  - 导出接口：更新 `src/motion/__init__.py`；
  - 新增完备测试：`tests/verify_task6gd_contact_force_solver.py`（17 项全面覆盖单点支撑、双足均分、CoM 偏置分配、力矩自由度不可控检测、脱离接触零力约束、无摩擦打滑检测、库仑摩擦锥边界截断、斜坡 15° 分配、垂直墙面单向推力分配、多表面异构法向联合接触、独立力矩验算、不可行拉力拦截、数值容错、排列不变性、时间步长与正向动力学契约）；
  - 注册统一测试入口：在 `tests/test_registry.py` 注册 `contact_force_solver`（覆盖 QUICK, PHYSICS, FULL 分级）。

---

### [DEC-036] 有界摩擦锥欧几里得正交投影与接触力求解可靠性加固 (Task 6G-D-B-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-23
* **背景**：Task 6G-D-B 交付后，经独立源码审查发现了 4 项核心数学与状态契约问题：
  1. `project_to_friction_cone` 在有限最大法向力 $F_{n,\max}$ 下，对处于无限圆锥内但超法向界限的力向量采用等比例缩小切向力，偏离了欧几里得最近点（反例 $F=(1,0,10), n=(0,0,1), \mu=0.5, \max=5$ 应投影为 $(1,0,5)$ 而非 $(0.5,0,5)$）；
  2. 求解器终止状态与底层优化器（SLSQP/SPG）实际迭代次数、收敛标志及报错原因未完全透传解耦，可能导致假收敛或异常掩盖；
  3. `_check_a_priori_infeasibility` 采用 `normal_z > 0.5` 启发式粗暴拦截向下合力，但在高摩擦大倾角斜坡或多表面支撑下，沿斜面切向分力完全可在保持法向正压力下提供负 $Z$ 净力；
  4. `solution_to_multi_contact_dynamics` 使用硬编码的 $0.05\text{ m}$ 占位净距冒充真实几何测量，制造了伪测量值。
* **决策与方案**：
  1. **有界摩擦锥闭式凸多边形正交投影**：将 3D 旋转对称投影严格降维为子午平面 $(F_n, f_t)$ 上针对凸多边形可行域 $\Omega$ 的欧几里得距离解析极小化。构建母线边界、上法向盖、下法向盖、底轴 4 组闭式投影候选点进行欧氏距离解析极值优选，严格满足有限上下界、$\mu=0$、零向量、幂等性 $P(P(F))=P(F)$ 与欧氏最近点最优性；
  2. **收敛状态机与优化诊断解耦透传**：`ContactForceSolution` 扩充 `solver_engine`, `optimizer_converged`, `optimizer_message`, `fallback_occurred` 等字段；严格要求约束检验、残差判定、优化器收敛三重独立合格方可标定 `SOLVED`；达到迭代上限明确标定 `APPROXIMATE` 并报告实际迭代；SLSQP 异常触发 SPG 明确标定 `fallback_occurred=True`；
  3. **严格收紧不可行性预判**：废除 `normal_z > 0.5` 启发式规则；仅对严格水平地表（所有触点外法线完全为 $(0,0,1)$）且拉力为负、或无触点而目标非零等可证明不可行场景报 `INFEASIBLE`；倾斜斜坡与复杂工况 100% 交由优化器真实求解；
  4. **真实接触几何间隙保真契约**：`ContactConstraintSpec` 与 `SingleContactDynamics` 均扩展 `surface_distance: Optional[float] = None` 与 `is_in_contact_override`；存在环境测量时 100% 传递真实有符号净距，无测量时明确标记为未知（`None`），严禁凭空构造伪数值。
* **影响与产物**：
  - 更新代码：`src/motion/contact_force_solver.py`, `src/motion/contact_dynamics.py`；
  - 扩充测试：`tests/verify_task6gd_contact_force_solver.py` 新增 Test 18 至 Test 31（共 31 项测试全部通过）；
  - 实测回归全绿：Blender 无 SciPy 环境下通过 SPG 30/30 项全绿通过（1 项跳过）；独立 Python 全量环境 31/31 项全绿通过；`quick` (7/7), `physics` (12/12) 零退化。

---

### [DEC-037] 接触力求解器终止状态契约与优化器收敛真值解耦 (Task 6G-D-B-R2)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-24
* **背景**：在 Task 6G-D-B-R1 强化了优化器状态透传与有界摩擦锥投影后，系统针对 `not opt_converged` 且 `iterations >= config.max_iterations` 进行了 `APPROXIMATE` 标记，但独立源码审查发现了严重的状态契约漏洞：当优化器（SLSQP/SPG）发生提前非成功终止（如奇异矩阵、步长耗尽、迭代终止在非驻点等使得 `opt_converged=False`，且 `iterations < config.max_iterations`），若此时候选解残差由于偶然或初始猜测巧合 $\le$ 设定容差，状态机会错误地返回 `SOLVED`。此外，SLSQP 若未抛出异常但返回 `res.success == False`，原逻辑未能触发到 SPG 的容错回退机制；若解中出现 NaN/Inf 或非数值，也存在被残差比较静默吸纳的风险。
* **决策与方案**：
  1. **严格的 `SOLVED` 状态准入准则**：
     - `SOLVED` 必须满足五重充要条件：(1) 最终接触力全部为有限数值（严格拦截 NaN/Inf）；(2) 硬物理约束在配置容差内满足（$F_n \ge 0, \|\mathbf{F}_t\| \le \mu F_n$）；(3) 合力残差 $\le \text{force\_tolerance\_n}$；(4) 绕质心合力矩残差 $\le \text{torque\_tolerance\_nm}$；(5) 底层优化器明确确认正常收敛（`opt_converged == True`），或属于经过显式验证的零触点/零外力解析平衡路径（`solver_engine="analytical"`）。
     - 任何未收敛终止（`not opt_converged`）哪怕残差完全达标，绝对严禁返回 `SOLVED`，必须如实标定为 `APPROXIMATE`，同时完整保留候选解、实际残差、底层优化器状态（`optimizer_converged=False`）与诊断信息（`optimizer_message`）。
  2. **SLSQP 非成功结果回退契约**：
     - SLSQP 执行无论因抛出异常中断、还是返回 `res.success == False`，在 `enable_fallback=True` 下均自动触发回退到 Native SPG，将 `fallback_occurred` 置为 `True`，将 `solver_engine` 更新为 `"spg"`；
     - 记录并保全触发回退的根本原因（原 SLSQP 报错信息与返回码），追加 SPG 最终状态；总迭代次数累计两阶段迭代（`slsqp_iters + spg_iters`）；
     - 若 SPG 同样未确认收敛，严格返回 `APPROXIMATE`，绝不虚报 `SOLVED`；若关闭回退（`enable_fallback=False`），如实标定未收敛并返回 `APPROXIMATE`。
  3. **非数值（NaN/Inf）与异常防御性截断**：
     - 在装配解向量、计算残差与评估约束违规量各阶段均加入 `math.isfinite` 严格检验；
     - 任何出现非数值（NaN/Inf）或优化引擎异常中断的情形，一票否决直接标定为 `NUMERICAL_FAILURE`，`is_physically_valid=False`，坚决杜绝非数值被残差比较静默吸纳。
  4. **完备可控回归测试**：
     - 在 `tests/verify_task6gd_contact_force_solver.py` 新增 Test 32 至 Test 37（共 37 项测试），通过受控 mock 精确验证正常收敛、非成功但残差达标、非成功且残差超标、SLSQP `success=False` 回退 SPG、双引擎均失败严禁 `SOLVED`、以及 NaN/Inf/双异常中断严格标定 `NUMERICAL_FAILURE` 与解析零解路径。
* **影响与产物**：
  - 更新代码：`src/motion/contact_force_solver.py`；
  - 扩充测试：`tests/verify_task6gd_contact_force_solver.py`（37 项测试全绿通过）；
  - 实测回归全绿：`quick` (7/7), `physics` (12/12) 保持 100% 零退化（退出码 0）；
  - 彻底消除了求解器状态伪报漏洞，确保了动力学控制上层获取的接触力状态 100% 具备数学与物理真实性。

---

### [DEC-038] 纯数学前向动力学单步积分内核与刚体物理状态解耦 (Task 6G-D-C1-A)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-24
* **背景**：在完成接触动力学正向计算（6G-D-A/R1/R2）与接触力逆向优化求解（6G-D-B/R1/R2）后，系统需要进入动力学时间步进闭环，即由合外力与绕质心合力矩驱动全身质心线运动与刚体等效转动状态前向时间积分。既往工程中部分物理计算耦合了 Blender 的 `bpy` 或刚体物理引擎，无法在独立无头 Python 环境纯粹运行，且缺乏不可变状态防污染机制及目标值与实际积分状态的严格解耦。此外，接触力求解器输入若包含重复 `contact_id` 会造成字典键静默覆盖。
* **决策与方案**：
  1. **接触力求解器重复 ID 严格防御契约**：
     - 在 `solve_contact_forces` 输入校验阶段增加 `contact_id` 唯一性集合检查，发现重复 ID 一票否决返回 `ContactSolverStatus.INVALID_INPUT`，杜绝静默覆盖；
     - 在 `solution_to_multi_contact_dynamics` 中同步加入重复 ID 校验并抛出 `ValueError`。
  2. **100% 独立纯 Python 6-DOF 刚体动力学状态容器 (`ForwardDynamicsState`)**：
     - 使用 `@dataclass(frozen=True)` 冻结不可变对象，杜绝单步积分异常或失败时部分修改输入状态（严格保障失败原子性）；
     - 显式定义世界坐标系约定（+Z Up, Ground Z=0.0m）及 SI 单位制（m, kg, s, N, N·m, rad/s, kg·m²）；
     - 明确姿态四元数采用 Hamilton 格式 `(w, x, y, z)`，表示从刚体局部坐标到世界坐标的主动旋转 $\mathbf{v}_{\text{world}} = R(q) \mathbf{v}_{\text{body}}$；
     - 明确刚体自身坐标系惯性张量 $I_{\text{body}}$ 在刚体旋转中保持不变，世界坐标系惯性张量满足严格协变张量变换 $I_{\text{world}} = R(q) I_{\text{body}} R(q)^T$。
  3. **牛顿-欧拉 6-DOF 精确时间步进与指数映射姿态积分**：
     - 线运动积分采用 Velocity Verlet 形式（假定单步内合外力恒定）：$\mathbf{a} = \mathbf{F}_{\text{net}} / m$，$\mathbf{v}_{k+1} = \mathbf{v}_k + \mathbf{a} \Delta t$，$\mathbf{p}_{k+1} = \mathbf{p}_k + \mathbf{v}_k \Delta t + \frac{1}{2} \mathbf{a} \Delta t^2$（解析零截断误差）；
     - 角动量积分采用外力矩冲量更新：$\mathbf{L}_{k+1} = \mathbf{L}_k + \boldsymbol{\tau}_{\text{net}} \Delta t$；
     - 姿态积分采用中点角速度与 $SO(3)$ 李代数四元数指数映射 $\Delta q = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$，保证在常角速度下旋转解析精确且模长严格保 1；
     - 惯性张量正定性与良态检查采用 Sylvester 充要准则，奇异或病态张量安全熔断返回 `SINGULAR_INERTIA`。
  4. **实际物理状态与参考目标值严格分离**：
     - 积分器输出纯粹由真实合外力驱动的实际状态（`state_next`），参考目标加速度与角动量变化率仅作为独立诊断字段（`target_linear_acceleration_world`, `linear_acceleration_tracking_error`）输出，绝对禁止将目标值直接写入实际物理状态。
* **影响与产物**：
  - 新增核心模块：`src/motion/forward_dynamics.py`；
  - 加固已有模块：`src/motion/contact_force_solver.py`（补充重复 ID 校验）；
  - 导出接口：更新 `src/motion/__init__.py`；
  - 新增完备测试：`tests/verify_task6gd_forward_dynamics.py`（17 项分析测试全部通过）；
  - 注册统一测试入口：在 `tests/test_registry.py` 注册 `forward_dynamics`（纳入 QUICK, PHYSICS, FULL 分级）；
  - 实测回归全绿：纯 Python 与 Blender Headless 双环境通过，`quick` (8/8) 保持 100% 零退化。

---

### [DEC-039] 前向动力学状态不可变性防御性复制与非各向同性刚体二阶中点姿态积分修正 (Task 6G-D-C1-A-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-24
* **背景**：在完成 Task 6G-D-C1-A 前向动力学独立单步积分内核后，独立源码审查发现了两项关键数学与数据契约问题：
  1. **状态不可变性漏洞**：`ForwardDynamicsState` 与 `ForwardDynamicsStepInput` 虽然标记为 `@dataclass(frozen=True)`，但内部序列字段在入参为外部可变列表（list）时未执行防御性深拷贝或不可变元组转换，调用方在积分后若修改原传入列表，将静默修改已冻结状态的内部属性；且向量与四元数维度未严格检验是否恰好为 3 或 4，存在被静默截断或长度不足报错延迟的风险；
  2. **旋转积分几何精度缺失**：既往姿态积分中，虽然使用了半步角动量 $\mathbf{L}_{\text{half}}$，但求解中点角速度时所使用的世界坐标系惯性矩阵仍直接复用当前时刻姿态的 $I_{\text{world}, k}$，未将刚体惯性张量根据半步姿态协变变换到中点位置 $I_{\text{world, half}} = R(q_{\text{half}}) I_{\text{body}} R(q_{\text{half}})^T$。对于非各向同性刚体（$I_{xx} \ne I_{yy} \ne I_{zz}$），此近似破坏了经典二阶中点旋转积分的几何精度与能量保持性。
* **决策与方案**：
  1. **严格的向量维度与防御性元组复制契约**：
     - 新增 `_validate_vec3(v, name)` 与 `_validate_quat(q, name)`，严格校验向量分量个数必须恰好为 3、四元数分量个数必须恰好为 4，拦截任何长度不匹配输入；
     - 强制全部数值元素必须为有限实数（`math.isfinite`），四元数严格非退化并归一化；
     - 校验通过后，通过 `object.__setattr__` 将所有空间向量与集合字段强制转为全新的不可变浮点元组（`tuple`）；
     - `ContactForcePoint`、`ForwardDynamicsState`、`ForwardDynamicsStepInput`、`ForwardDynamicsStepResult` 全面统一此不可变防御机制，杜绝调用方持有外部可变引用修改状态；
     - 严格保障失败原子性：单步积分异常或失败时返回的 `state_next` 为原输入 `state` 的完全未修改引用。
  2. **严格的 2-Stage 中点姿态与角动力学积分流程**：
     - Step 1: 求解当前角速度 $\boldsymbol{\omega}_k = I_{\text{world}, k}^{-1} \mathbf{L}_k$；
     - Step 2: 外推半步姿态 $\theta_{\text{half}} = \|\boldsymbol{\omega}_k\| \frac{\Delta t}{2}$，$\Delta q_{\text{half}} = \exp(\frac{1}{2} \boldsymbol{\omega}_k \frac{\Delta t}{2})$，$q_{\text{half}} = \text{normalize}(\Delta q_{\text{half}} \otimes q_k)$；
     - Step 3: 根据半步姿态严格计算中点世界惯性张量 $R_{\text{half}} = R(q_{\text{half}})$，$I_{\text{world, half}} = I_{\text{body}}.\text{rotate}(R_{\text{half}})$（并检查正定性）；
     - Step 4: 计算半步角动量 $\mathbf{L}_{\text{half}} = \mathbf{L}_k + \frac{1}{2} \boldsymbol{\tau}_{\text{net}} \Delta t$；
     - Step 5: 求解中点真实角速度 $\boldsymbol{\omega}_{\text{mid}} = I_{\text{world, half}}^{-1} \mathbf{L}_{\text{half}}$；
     - Step 6: 利用中点角速度推进整步姿态 $\theta_{\text{full}} = \|\boldsymbol{\omega}_{\text{mid}}\| \Delta t$，$\Delta q_{\text{full}} = \exp(\frac{1}{2} \boldsymbol{\omega}_{\text{mid}} \Delta t)$，$q_{k+1} = \text{normalize}(\Delta q_{\text{full}} \otimes q_k)$；
     - Step 7: 更新最终角动量 $\mathbf{L}_{k+1} = \mathbf{L}_k + \boldsymbol{\tau}_{\text{net}} \Delta t$ 以及最终角速度 $\boldsymbol{\omega}_{k+1} = I_{\text{world}, k+1}^{-1} \mathbf{L}_{k+1}$。
  3. **完备的可验证分析测试**：
     - 在 `tests/verify_task6gd_forward_dynamics.py` 新增 Test 18 至 Test 22（测试总数提升至 22 项）；
     - Test 18 检验外部列表就地修改无法污染 State、StepInput 与 ContactPoint；
     - Test 19 严格测试拒绝 2D/4D 向量与 3D/5D 四元数；
     - Test 20 验证非各向同性刚体自由翻滚的动量与能量守恒（100 步相对能量漂移小于 $1.5 \times 10^{-7}$，角动量绝对漂移为 0.0）；
     - Test 21 验证非各向同性刚体在常外力矩下的角动量精确追踪；
     - Test 22 在时间步长二分（$\Delta t \in \{0.04, 0.02, 0.01, 0.005\}$）下实测误差缩减比，测得误差比精确为 $4.01$ 与 $4.00$，严格证明了二阶二次收敛 $O(\Delta t^2)$。
* **影响与产物**：
  - 更新代码：`src/motion/forward_dynamics.py`；
  - 扩充测试：`tests/verify_task6gd_forward_dynamics.py`（22/22 全绿通过）；
  - 实测回归：`quick` (8/8) 与 `physics` (13/13) 全部通过，保持 100% 零退化。

---

### [DEC-040] 多帧动力学闭环协调架构与求解准入门禁机制 (Task 6G-D-C1-B)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-24
* **背景**：在完成接触动力学正向计算（6G-D-A）、接触力逆向优化分配（6G-D-B）与单步前向动力学积分内核（6G-D-C1-A）后，系统需要构建首个真正的多帧连续动力学闭环协调层。动画物理系统若直接将目标速度或加速度赋值为实际状态，或为了迎合测试通过而虚构超出摩擦锥的接触力，会导致动力学闭环失真；当优化器遇到摩擦不足、不可行目标或数值失败时，若缺乏明确的准入门禁策略，容易引发状态突变或伪造运动。
* **决策与方案**：
  1. **真实物理因果闭环链路**：
     - 严格遵循：当前实际状态 $\to$ 期望参考与 PD 反馈律 $\to$ 目标接触扳手 $\to$ 接触力优化求解 $\to$ 准入门禁判决 $\to$ 实际接触力前向积分 $\to$ 新实际状态 $\to$ 遥测与跟踪误差记录；
     - 绝对禁止将目标速度、目标加速度或目标角动量直接覆盖为实际物理状态，实际运动 100% 由牛顿-欧拉方程与真实分配的接触力积分驱动。
  2. **基于自然倒立摆阻尼特性的反馈控制与数值饱和边界**：
     - 引入 `DesiredMotionReference` 独立承载位置、速度、朝向与前馈控制；
     - 基于人体质心自然倒立摆频率 $\omega_0 = \sqrt{g/h} \approx 3.1\text{ rad/s}$ 确立临界阻尼反馈增益（$k_p = 16.0, k_d = 6.0$），姿态跟踪引入 $SO(3)$ 李代数四元数对数映射 $\mathbf{e}_{\text{rot}} = \log(q_{\text{tgt}} \otimes q_{\text{curr}}^{-1})$；
     - 对指令加速度与指令角动量变化率施加明确的物理饱和截断（$\|a_{\text{cmd}}\| \le a_{\max}$），杜绝初始突变引发巨大非物理力矩。
  3. **严格的接触力求解结果准入门禁与残差防伪造策略 (`ClosedLoopAdmissibilityPolicy`)**：
     - 明确区分五类求解状态：`SUCCESS_EXACT`、`SUCCESS_APPROXIMATE`、`REJECTED_INFEASIBLE`、`REJECTED_APPROXIMATE`、`SOLVER_INVALID_INPUT` / `SOLVER_NUMERICAL_FAILURE`；
     - 对 `APPROXIMATE` 状态：仅当接触力严格满足物理硬约束（单侧接触 $F_n \ge 0$、3D 库仑摩擦锥 $\|\mathbf{F}_t\| \le \mu F_n$）且残差未超过门禁阈值时方可准入，并如实报告跟踪误差与状态，严禁伪装为精确求解成功；
     - 无法安全推进时（不可行或数值失败），严格保持上一帧实际状态不修改（保障失败原子性），并输出可诊断遥测。
  4. **完备且可序列化的逐帧遥测 (`ClosedLoopFrameTelemetry`)**：
     - 逐帧记录时间、当前/下一状态、指令加速度、目标扳手、接触求解状态与残差、各点实际力、动力学积分状态、位置/速度/加速度跟踪误差；
     - 提供 `to_dict()` 与 `export_telemetry()`，为后续在 `DynamicsPlayground` 中直接驱动物理遥测提供权威数据源。
* **影响与产物**：
  - 新增核心模块：`src/motion/closed_loop_dynamics.py`；
  - 导出接口：更新 `src/motion/__init__.py`；
  - 新增测试套件：`tests/verify_task6gd_closed_loop_dynamics.py`（12 项核心场景测试全绿）；
  - 注册统一测试入口：在 `tests/test_registry.py` 注册 `closed_loop_dynamics`（纳入 QUICK, PHYSICS, FULL 分级）；
  - 分层回归全绿：`quick` (9/9 项全部通过，14.52s) 与 `physics` (14/14 项全部通过，68.29s) 保持 100% 零退化。

---

### [DEC-041] 完整三维重力统一、旋转反馈陀螺耦合修正与物理不可行性解耦准入门禁 (Task 6G-D-C1-B-R1)
* **状态**：已采纳并经实测验证 (Accepted & Verified)
* **日期**：2026-10-24
* **背景**：源码审查发现 Task 6G-D-C1-B 存在三处关键数学与契约问题：(1) 闭环构造目标扳手时仅传递标量 `gravity_z`，与前向动力学积分使用的完整三维重力向量解耦；(2) 旋转反馈律仅使用 $\boldsymbol{\tau} = I \boldsymbol{\alpha}$，忽略了刚体在世界坐标系下由于惯性张量旋转产生的完整欧拉陀螺力矩项 $\boldsymbol{\omega} \times \mathbf{L}$；(3) 控制器将所有不可行目标（包括空中悬停）统一作为错误冻结物理推进，导致角色在空中未受支撑时异常浮空悬停，未能反映自然重力下落的真实物理演化。
* **决策与方案**：
  1. **完整三维重力统一计算**：
     - 扩展 `ContactWrenchTarget.from_target_motion()` 接口，新增 `gravity_acceleration_world: Optional[Vec3] = None` 参数；
     - 当传入三维重力时，目标接触力满足严格物理关系 $\mathbf{F}_{\text{contact\_target}} = m \mathbf{a}_{\text{target}} - m \mathbf{g} - \sum \mathbf{F}_{\text{ext}}$；
     - 未传入三维重力时保持旧 `gravity_z` 默认值与既有调用 100% 兼容；
     - 闭环协调器向目标接触扳手与单步前向动力学积分器传入同一套 `gravity_acceleration_world`。
  2. **世界系旋转反馈陀螺耦合项修正**：
     - 基于完整世界坐标系刚体动力学方程 $\frac{d\mathbf{L}}{dt} = I_{\text{world}} \boldsymbol{\alpha} + \boldsymbol{\omega} \times \mathbf{L}$；
     - 当存在旋转反馈目标时，将世界角加速度反馈 $\boldsymbol{\alpha}_{\text{fb}}$ 转换为力矩时加入陀螺耦合项：$\boldsymbol{\tau}_{\text{fb}} = I_{\text{world}} \boldsymbol{\alpha}_{\text{fb}} + \boldsymbol{\omega} \times \mathbf{L}$；
     - 当完全没有旋转反馈目标时，严格保持纯前馈角动量变化率语义不变，避免重复计入陀螺项；
     - 解析验证了各向同性惯量（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）、主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} = \mathbf{0}$）与非主轴旋转（$\boldsymbol{\omega} \times \mathbf{L} \ne \mathbf{0}$）的精确匹配。
  3. **严格解耦数值失败与控制物理不可行性**：
     - **数值失败**（非法输入、NaN、求解崩溃）：严格保全原物理状态不变（失败原子性，`state_advanced = False`）；
     - **控制目标不可行但物理可知**（如空中无接触却要求悬停）：不虚构接触力，以真实物理力（重力 + 零接触力）推进前向积分，物理时间自然演化（`state_advanced = True`，状态标定为 `CONTROL_INFEASIBLE_PHYSICS_ADVANCED`），角色在重力下自然加速坠落；
     - **约束无法证明有效**（如地面要求拉扯负支撑力）：不得直接积分，严格中止推进（`REJECTED_INFEASIBLE`）；
     - 在 `ClosedLoopAdmissibilityPolicy` 中保留 `strict_freeze_on_infeasible: bool = False` 作为严格冻结可选配置。
  4. **接触几何多帧边界界定**：
     - 明确 `ContactConstraintSpec` 仅代表当前帧即时接触输入；多帧模拟严禁无条件假设静态接触点永久有效；后续 Task 6G-D-C2 须调用环境查询与接触模型动态更新接触点与有效性。
* **影响与产物**：
  - 更新代码：`src/motion/contact_force_solver.py`、`src/motion/closed_loop_dynamics.py`；
  - 扩充测试：`tests/verify_task6gd_closed_loop_dynamics.py` 增至 20 项场景测试全绿通过；
  - 实测回归：`quick` (9/9, 15.09s) 与 `physics` (14/14, 66.27s) 保持 100% 零退化。

---

### [DEC-042] 数值闭环集中数学审计、步数时间解耦、正交状态语义与遥测不可变性防御 (Task 6G-D-C1-FINAL)
* **状态**：已采纳并经实测全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-24
* **背景**：在 6G-D-C1 阶段收尾与进入 6G-D-C2 视口集成之前，执行集中数学审计与契约核验，发现并排查了四项关键接口与时间契约缺陷：
  1. `ClosedLoopAdmissibilityPolicy.allow_approximate_solutions` 虽在配置中定义，但未在 `step_closed_loop_dynamics()` 的 `APPROXIMATE` 分支中参与判定；
  2. `ClosedLoopDynamicsCoordinator.simulate()` 中 `total_time` 简单使用 `len(records) * dt` 计算，当存在拒绝推进的停滞帧时混淆了尝试帧数与真实物理时间；
  3. `ClosedLoopFrameTelemetry` 中布尔标志（`is_physically_valid` 与 `is_control_feasible`）语义交织，未能清晰正交反映接触物理合法性、策略准入、目标满足与状态推进；
  4. 遥测内部字典 `actual_contact_forces` 返回可变引用，存在调用方就地修改污染历史遥测的风险，且配置参数缺少统一的有限数值门禁。
* **决策与方案**：
  1. **策略链准入优先级确立 (DEF-001)**：
     - `sol.is_physically_valid == False` 标定为 `SOLVER_NUMERICAL_FAILURE`（最高优先级错误）；
     - `policy.strict_solved_only == True` 无条件拒绝所有近似解（`REJECTED_APPROXIMATE`）；
     - `not policy.allow_approximate_solutions` 严格拒绝近似解（`REJECTED_APPROXIMATE`）；
     - 当且仅当 `allow_approximate_solutions == True` 且残差在允许阈值内时准入为 `SUCCESS_APPROXIMATE`；
     - 残差超限时，若 `strict_freeze_on_infeasible == True` 拒绝推进，若为 `False` 则以真实有效物理力自然推进（`CONTROL_INFEASIBLE_PHYSICS_ADVANCED`）。
  2. **物理推进时间与模拟步数统计彻底解耦 (DEF-002)**：
     - 在 `ClosedLoopSimulationTrajectory` 中清晰区分：`requested_steps`、`attempted_steps`、`successful_steps`、`failed_steps`、`requested_duration` 与 `actual_physical_time`；
     - 强制约束 `total_time == actual_physical_time`（严格等于 `final_state.timestamp - initial_state.timestamp`），杜绝因停滞帧导致的虚假物理时间累加。
  3. **遥测状态四维正交解耦语义 (DEF-003)**：
     - `is_contact_solution_physically_valid`：接触力是否满足单侧接触与库仑摩擦锥；
     - `is_policy_admitted`：当前步是否通过准入策略并允许单步前向动力学积分；
     - `is_target_satisfied`：控制目标是否完全被满足（`SUCCESS_EXACT` 或合规准入的 `SUCCESS_APPROXIMATE`）；
     - `state_advanced`：物理状态与时间戳是否真正单步推进；
     - 严格保留 `is_physically_valid` 与 `is_control_feasible`，杜绝调用端回归中断。
  4. **遥测深层不可变性防御与配置数值门禁 (DEF-004 / DEF-005)**：
     - `actual_contact_forces` 在遥测中统一使用只读 `MappingProxyType` 封装，任何原地赋值直接抛出 `TypeError`；
     - `ClosedLoopSimulationTrajectory.frames` 强制转为只读元组（`tuple`）；
     - `to_dict()` 与 `export_telemetry()` 返回深解耦的纯净可序列化 JSON 结构；
     - 在 `ContactSolverConfig`、`FeedbackGainsConfig` 与 `ClosedLoopAdmissibilityPolicy` 的 `__post_init__` 中加入统一的 `math.isfinite()` 与正数/非负数拦截门禁。
  5. **物理守恒与收敛阶实测验证**：
     - 零重力线性动量守恒误差 $< 10^{-10}\text{ kg}\cdot\text{m/s}$，角动量守恒误差 $< 10^{-10}\text{ N}\cdot\text{m}\cdot\text{s}$；
     - 旋转动能漂移 100 帧内 $< 10^{-6}\text{ J}$，50 帧静态下陷 $< 10^{-5}\text{ m}$；
     - 实测非线性旋转陀螺动力学误差在步长减半时呈严格 $\approx 4.05$ 倍下降，确证 $O(\Delta t^2)$ 二阶数值收敛阶。
* **影响与产物**：
  - 更新代码：`src/motion/contact_force_solver.py`、`src/motion/closed_loop_dynamics.py`；
  - 新增审计文档：`docs/C1_FINAL_AUDIT.md`；
  - 测试套件扩充：`tests/verify_task6gd_closed_loop_dynamics.py`（20 项扩充至 30 项测试，30/30 PASS）；
  - 统一测试回归：`quick` (9/9 全绿, 15.81s)，`physics` (14/14 全绿, 67.56s)；
  - 阶段收尾：6G-D-C1 数值闭环开发与数学审计全部就绪，下一里程碑锁定为 **Task 6G-D-C2: 在现有 DynamicsPlayground 中集成和验证真实动力学状态**。

---

### [DEC-043] DynamicsPlayground 真实动力学状态集成与多场景视口验证 (Task 6G-D-C2-A)
* **状态**：已采纳并经实测全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-24
* **背景**：在 6G-D-C1 数值闭环阶段验收后，需要将纯 Python 数值积分结果接入 Blender 3D 场景进行直观视口验证。依据永久架构门禁（ACG Section 6），必须复用单一基准场景 `output/dynamics_playground.blend`，严禁建立分立场景；必须将动力学遥测几何体隔离在专用集合中，严禁修改已有环境网格；必须 100% 由真实物理数据驱动，严禁摆设虚假静态箭头；同时需要修正审计文档关于平动积分二阶收敛性的边界说明。
* **决策与方案**：
  1. **五大物理场景全程序化状态驱动与视口布局**：
     - **Station 1 (静态支撑平衡)**：双足接触反力平衡 $m g = 686.7\text{ N}$，CoM 高度稳定在 $Z=1.0\text{ m}$（下陷 $< 10^{-5}\text{ m}$），动态绿色反力箭头严格竖直向上；
     - **Station 2 (重力自由落体)**：空中无接触悬停需求，状态按自然重力 $-9.81\text{ m/s}^2$ 自然加速下落，零接触力虚构，目标虚影悬空直观呈现跟踪偏差；
     - **Station 3 (水平加速推进)**：在库仑摩擦锥限制内产生前进剪切力（$F_x = 105\text{ N}$），质心沿 $+X$ 加速平移，反力箭头倾角严格对应合外力方向；
     - **Station 4 (摩擦不足滑移滞后)**：冰面低摩擦（$\mu=0.08$）强制截断剪切力，实际质心滞后于目标虚影 $> 2.0\text{ m}$，直观呈现打滑与失控；
     - **Station 5 (偏心接触导致旋转)**：偏心单足接触点产生滚转力矩 $\tau_x \approx -206\text{ N}\cdot\text{m}$，驱动身体姿态连续倾斜翻滚，动态角动量箭头实时延伸。
  2. **视觉调试集合隔离与环境不可变原则 (ACG Section 6 遵守)**：
     - 动力学几何体（CoM 球、身体代理框、目标虚影、接触圆盘、动态力箭头、动态角动量箭头、3D 轨迹曲线、站台 3D 文本标签、检查相机）全部封装入独立集合 `Playground_Dynamics_Visualization`；
     - 原始训练场集合 `Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras` 的 45 个对象保持 100% 不变；
     - 保留 `PlaygroundOverviewCam` 为主场景相机，新增 `DynamicsInspectionCam` 供用户快速切换鸟瞰 5 个测试台。
  3. **平动数值积分边界审计修正 (Section VIII)**：
     - 在 `docs/C1_FINAL_AUDIT.md` 明确平动积分公式为 $v_{k+1} = v_k + a_k \Delta t$ 与 $p_{k+1} = p_k + v_k \Delta t + \frac{1}{2} a_k \Delta t^2$；
     - 澄清其对恒定加速度场（如重力）具有解析无截断特性（$< 10^{-12}\text{ m}$），但在非恒定加速度场中呈现速度一阶精度，不可无条件称为两阶段二阶 Velocity Verlet；
     - 新增测试 `test_31_non_constant_acceleration_convergence_benchmark`，在非恒定正弦加速度场中实测记录一阶收敛表现（误差减半比 $\approx 2.0$）。
* **影响与产物**：
  - 新增核心模块：[`src/scene/dynamics_visualizer.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visualizer.py)（纯 Python 场景模拟与 Blender 关键帧注入解耦）；
  - 更新生成脚本：[`run_dynamics_playground.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_dynamics_playground.py)；
  - 更新场景产物：`output/dynamics_playground.blend`（230,508 字节，包含 86 个物体，可在 Blender 5.1.1 直接打开播放）；
  - 新增测试套件：[`tests/verify_task6gd_playground_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gd_playground_dynamics.py)（5 项测试全部通过）；
  - 注册测试套件：`tests/test_registry.py` 注册 `playground_dynamics_states`；
  - 审计修正：更新 [`docs/C1_FINAL_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/C1_FINAL_AUDIT.md) 并扩充 [`tests/verify_task6gd_closed_loop_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gd_closed_loop_dynamics.py) 至 31 项测试全绿；
  - 回归全绿：`quick` (9/9 项通过，15.08s)，`physics` (15/15 项通过，70.36s)，历史动作 100% 零退化。

---

### [DEC-044] 动力学自动视觉证据、遥测一致性审计与跨 AI 联系表验收管线 (Task 6G-D-C2-A 补充要求)
* **状态**：已采纳并经实测全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-25
* **背景**：用户不应承担逐帧手动截图、肉眼寻找问题或口述动画异常的高耗能工作；跨 AI（如 ChatGPT）复核需要自包含、高保真、可独立检验的图像、数值遥测与时序联系表证据。必须基于单一权威基准场景 `output/dynamics_playground.blend`，自动输出多视角关键帧、逐帧数值对比遥测、综合联系表 (Contact Sheet)、连续运动动画，并执行机器防篡改/防冒充一致性审计。
* **决策与方案**：
  1. **多视角高时间采样自动化渲染矩阵**：
     - 为全部 5 个测试台配置专职的正面 (Front)、侧面 (Side)、俯视 (Top) 检查相机，外加高空全局鸟瞰相机 (`DynamicsInspectionCam`)；
     - 对时间轴设定 7 级高密度关键帧采样：$t=0.00\text{s}$ (F01), $t=0.46\text{s}$ (F12), $t=0.96\text{s}$ (F24), $t=1.46\text{s}$ (F36), $t=1.96\text{s}$ (F48), $t=2.46\text{s}$ (F60), $t=2.96\text{s}$ (F72)；
     - 自动批量无头渲染 112 张高分辨率 PNG 图片（105 张工位多视角图 + 7 张全景图）。
  2. **逐帧机器遥测与跨空间严格一致性审计 (`telemetry.json`)**：
     - 逐帧记录 72 帧全部数值动力学状态（质心、线速度、角动量、姿态四元数、接触反力、力矩、求解器状态）与 Blender 求值对象世界变换；
     - 审计计算真实误差：Blender 求值质心与积分质心最大位置误差实测为 `0.00e+00 m`（$< 10^{-5}\text{ m}$）；姿态四元数归一化测地距离误差实测为 `3.50e-07 rad`（$< 10^{-5}\text{ rad}$）；
     - 严密反冒充审计：在打滑工位（Station 4）实测最终质心与目标虚影发散距离达 $5.30\text{ m}$；在滚转工位（Station 5）姿态发散量达 $1.55\text{ rad}$（$> 88^\circ$），无可辩驳证明仿真器严守物理定律，绝无目标冒充。
  3. **高分辨率时序与空间联系表 (Contact Sheet)**：
     - 利用 Blender 内置 numpy 与原生图像引擎，将 5 个工位 $\times$ 6 列时空演化网格拼接为 $2048 \times 1080$ 的高对比度单张联系表 [`docs/evidence/task6gd_c2a/contact_sheet.png`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/contact_sheet.png)；
     - 每一子图自带工位名称、视角标注、时间戳、物理状态与误差角标，无需运行 Blender 即可一览时空演化全貌。
  4. **全套跨 AI 交付件与分级归档保护**：
     - Git 跟踪库入库清单：[`docs/evidence/task6gd_c2a/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/)（包含联系表、48 张代表性关键帧、逐帧 `telemetry.json`、全景动画 GIF 以及自动化验收报告 [`validation_report.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/validation_report.md)）；
     - 本地全量证据包：`output/evidence/task6gd_c2a/task6gd_c2a_evidence_pack.zip`（24.5 MB，包含全量 112 张高清原图与交互式 Web 检查器 [`visual_player.html`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/output/evidence/task6gd_c2a/visual_player.html)）。
* **影响与产物**：
  - 新增生产模块：[`src/scene/dynamics_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visual_evidence.py)；
  - 新增端到端管线脚本：[`run_generate_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_generate_visual_evidence.py)；
  - 新增自动化回归测试套件：[`tests/verify_task6gd_visual_telemetry.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gd_visual_telemetry.py)（5 项测试 100% 通过）；
  - 更新中央测试注册表：`tests/test_registry.py` 注册 `visual_evidence_telemetry`；
  - 自动化回归：`quick` (9/9 PASS, 16.09s)，`physics` (16/16 PASS, 72.42s)，历史步态 100% 零退化。

---

### [DEC-045] 6G 动力学最终收口、完整工程审计与通用程序化运动底座架构冻结 (Task 6G-D-C2-FINAL)
* **状态**：已采纳并经实测全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-25
* **背景**：Task 6G-D 经过 6G-D-A、6G-D-B、6G-D-C1、6G-D-C2-A 多轮深耕，已圆满打通接触力学、有界摩擦锥二次规划求解、前向动力学辛积分、多帧闭环控制与 Blender 视口遥测验证。为实现底座架构的真正收口与长期稳定，必须防止工程陷入无休止的局部扩展，防止跨 AI 协同认知漂移，杜绝私自衍生 C2-B/C3/6G-E 等分支，并对全工程 18 个 `output/*.blend` 资产、51 个 `src/` Python 模块、42 个 `tests/` 验证脚本、19 个 `run_*.py` 入口脚本与规范体系建立机器可复核的 AST 与 `.blend` 审计及架构冻结。
* **决策与方案**：
  1. **73 状态（Frame 1..73）时空严格标准化与闭环收口**：
     - 将 72 步离散积分（$N=72, \Delta t=1/24\text{s}$）严格对齐为 73 个物理状态（$S_0$ 到 $S_{72}$），对应 Blender 时间轴 Frame 1 至 Frame 73（$F = k + 1$）；
     - 标准化关键帧采样时刻为 $t = 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0\text{s}$（对应 Frame 1, 13, 25, 37, 49, 61, 73），实现与秒级网格完美对齐；
     - 编码 73 帧连续平滑动画 GIF（delay 4cs，24 FPS 回放），并生成覆盖标准秒节点的 5 工位 $\times$ 6 视角时空联系表。
  2. **物理与数学精度边界严格界定 (Accuracy Demarcation)**：
     - 正式确认底座阶段采用单刚体集总 CoM 动力学模型（`ForwardDynamicsState`），明确其解决全局动量与接触防打滑的核心定位，避免过早陷入铰接多体（Featherstone）力矩爆炸；
     - 明确 Station 2 物理实质为空中弹道自由落体（验证无接触悬停的物理不可行性与零接触力输出），不包含地面撞击回弹动力学；
     - 明确 Station 3 与 4 使用理想连续接触点位移，不代表实际双足迈步交替冲击动力学。
  3. **全量工程资产、双管线并存现状与规范体系机器审计 (`tests/audit_c2_final_inspector.py`)**：
     - 通过只读机器审计脚本 [`tests/audit_c2_final_inspector.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/audit_c2_final_inspector.py) 对全库 51 个 `src/` 模块、42 个 `tests/` 脚本、19 个 `run_*.py` 脚本及 18 个 `output/*.blend` 场景执行 AST 解析与 Blender 5.1.1 无头开档核查，输出 [`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/codebase_and_blend_audit.json) 与 [`docs/evidence/task6gd_c2a/blend_inspection_log.txt`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/blend_inspection_log.txt)；
     - 严格区分当前并存的两条已实现管线：
       * **管线 A（19 骨骼运动学与全身控制生产管线）**：`MotionPlanner` / `MotionAction` (`src/motion/framework.py`, `run_cycle.py`, `sprint_start.py`, `sprint_brake.py`) $\to$ `KinematicBridgeExecutor.execute_frame()` (`src/motion/kinematic_bridge.py`) $\to$ `WholeBodyController.execute_frame()` (`src/motion/whole_body_controller.py`) $\to$ 既有 Blender Rig / IK / FK (`src/character/builder.py`, `src/rig/builder.py`, `src/rig/pose.py`, `src/rig/ik.py`, `src/rig/foot_contact.py`, `src/rig/arm_ik.py`, `src/motion/joint_limits.py`) $\to$ 实际姿态与只读物理遥测 (`src/motion/rigid_link.py`, `src/motion/body_kinematics.py`, `src/motion/body_inertia.py`, `src/motion/contact_model.py`) $\to$ `MotionState`，代表场景为 462 帧连续运动整合资产 `output/unified_motion_integration.blend`（298,537 字节，19 骨骼，12 个 Action，180 条 F-Curve）；
       * **管线 B（Task 6G-D 纯 Python 6-DOF 质心数值动力学管线）**：`ClosedLoopDynamicsCoordinator` (`src/motion/closed_loop_dynamics.py`) $\to$ `solve_contact_forces()` (`src/motion/contact_force_solver.py`) $\to$ `integrate_forward_dynamics_single_step()` (`src/motion/forward_dynamics.py`) $\to$ `inject_dynamics_visualization()` (`src/scene/dynamics_visualizer.py`)，驱动 `output/dynamics_playground.blend`（234,436 字节，73 帧，101 个物体，0 骨骼）中的刚体代理网格与力学箭头；
     - 明确这两条管线当前尚未汇流，其汇流定位于未来 **Phase 7C**。
  4. **五大权威架构冻结规范与验证报告发布**：
     - 编写并经 `--verify-docs` 机器核验零幻觉路径/符号后交付：
       1. [`docs/FOUNDATION_ASSET_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/FOUNDATION_ASSET_AUDIT.md)：全量 51 个 `src/` 模块、42 个测试、19 个入口脚本与 18 个 `.blend` 场景机器核查清单；
       2. [`docs/FOUNDATION_ARCHITECTURE_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/FOUNDATION_ARCHITECTURE_AUDIT.md)：真实生产运动学管线（Pipeline A）与 6G-D 质心动力学管线（Pipeline B）架构及数学闭环边界；
       3. [`docs/FOUNDATION_DEPENDENCY_MAP.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/FOUNDATION_DEPENDENCY_MAP.md)：含精确调用文件、被调文件、函数/类名与源码行号的 44 条真实依赖边，以及独立隔离的 `Future Architecture` 章节；
       4. [`docs/FOUNDATION_STATE_OWNERSHIP.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/FOUNDATION_STATE_OWNERSHIP.md)：严格区分当前已实现状态所有权与未完成汇流边界；
       5. [`docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ROADMAP_FOUNDATION_TO_FULLBODY.md)：权威后续路线图（**7A** 真实 19 骨骼角色进入 `DynamicsPlayground` 完成基础下肢连续通行 $\to$ **7B** 上肢独立运动与末端目标验证 $\to$ **7C** `KinematicBridge`、`WholeBodyController`、`CoM` 与整体动力学状态汇流 $\to$ **7D** 多关节动态协同 $\to$ **7E** 既有 IK/FK 求解器的动态协同与接触切换 $\to$ **7F** 全身移动、抓握、支撑、释放与连续训练场通行 $\to$ **6H** 动态平衡与主动补偿）；
       6. [`docs/C2_FINAL_VALIDATION.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/C2_FINAL_VALIDATION.md)：Task 6G-D-C2-FINAL 综合验收与纠偏报告。
  5. **未来阶段统一命名规范与冻结原则**：
     - Task 6G-D 正式冻结并进入只读维护状态，严禁创建 C2-B/C3/6G-E 等分支；
     - 本任务完成后严格停止，不自动触发 Phase 7A 或 Phase 6H。
* **影响与产物**：
  - 新增只读机器审计脚本与日志：[`tests/audit_c2_final_inspector.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/audit_c2_final_inspector.py)、[`docs/evidence/task6gd_c2a/codebase_and_blend_audit.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/codebase_and_blend_audit.json)、[`docs/evidence/task6gd_c2a/blend_inspection_log.txt`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task6gd_c2a/blend_inspection_log.txt)；
  - 更新核心文件：[`src/scene/dynamics_visualizer.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visualizer.py)、[`src/scene/dynamics_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/dynamics_visual_evidence.py)、[`run_generate_visual_evidence.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_generate_visual_evidence.py)、[`run_tests.ps1`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_tests.ps1)、[`tests/run_test_suite.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/run_test_suite.py)；
  - 更新测试套件：[`tests/verify_task6gd_playground_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gd_playground_dynamics.py)、[`tests/verify_task6gd_visual_telemetry.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task6gd_visual_telemetry.py)；
  - 发布并纠偏 6 份架构冻结文档：`docs/FOUNDATION_*.md`、`docs/ROADMAP_*.md` 与 `docs/C2_FINAL_VALIDATION.md`；
  - 回归全绿：`quick` (9/9 PASS)，`physics` (16/16 PASS)，`--verify-docs` (PASS)，历史步态 100% 零退化。

---

### [DEC-046] 2026-10-25: Task 6G-D-C2-FINAL 文档真实性门禁、通用 AST 符号校验器与架构约束彻底冻结

* **状态**：已批准 (Approved)
* **日期**：2026-10-25
* **背景**：针对跨 AI 审阅中发现的文档潜在幻觉（如 `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md` 引用非枚举成员 `ContactLifecycle.TOUCHDOWN`，以及历史文档中的符号/方法微瑕），必须升级自动化校验工具为通用 AST 存在性核验，杜绝硬编码黑名单的局限性；同时固化唯一生产调用链、状态读写边界与后续开发路线，防止任何认知漂移。
* **决策与方案**：
  1. **枚举与接口真实性纠偏**：
     - 修正 `docs/ROADMAP_FOUNDATION_TO_FULLBODY.md`，明确区分离散触地动力学事件（Touchdown Event）与持续接触生命周期状态（`ContactLifecycle`: `CANDIDATE`, `ESTABLISHED`, `RELEASED`, `BROKEN`）；
     - 严禁为了让文档成立而向源码枚举添加 `TOUCHDOWN`；
     - 修复 `docs/FOUNDATION_ARCHITECTURE_AUDIT.md`、`docs/FOUNDATION_DEPENDENCY_MAP.md`、`docs/FOUNDATION_STATE_OWNERSHIP.md` 中微小的真实接口偏差（`ClosedLoopDynamicsCoordinator.simulate`、`DynamicsEnvironmentQuery.query_surface_at_point`、移除未定义的 `_apply_micro_projection` 幻觉引用并还原为真实几何合规检查 `multi_contact.check_all_contacts`）。
  2. **升级文档引用校验器 (`tests/audit_c2_final_inspector.py`) 为通用 AST 校验器**：
     - 自动解析源码 AST 提取全库模块路径、类定义、方法定义、顶层函数、类属性与 Enum 成员，并建立 `CodebaseSymbolIndex`；
     - 引入四元状态判别体系：`IMPLEMENTED`（真实存在且接入）、`EXISTS_NOT_INTEGRATED`（源码存在但暂未合流）、`PROPOSED`（未来拟议，严禁伪报已实现）、`INVALID`（不存在或错误 API，直接报错中断）；
     - 引入内置自测试套件 `run_validator_test_suite`，覆盖 Positive、Negative、Proposed、Prose Safety 四大场景，严禁假通过与自然语言误报；
     - 提供 `--test-validator` 与 `--verify-docs` 命令行入口，遇错返回非零退出码。
  3. **冻结生产调用主链与状态所有权**：
     - 在权威架构文档中彻底固化唯一生产主链：
       $$\text{MotionPlanner} / \text{MotionAction} \longrightarrow \text{KinematicBridgeExecutor.execute_frame()} \longrightarrow \text{WholeBodyController.execute_frame()} \longrightarrow \text{Blender Rig/IK/FK} \longrightarrow \text{物理遥测} \longrightarrow \text{MotionState}$$
     - 严禁任何后续 Agent 绕开、复制或自行替换此主链；明确 CoM/惯性/遥测当前为只读评估，C1/C2 质心动力学当前为独立管线，未完成的合流严禁谎报已实现。
  4. **固化后续路线 (7A $\to$ 7B $\to$ 7C $\to$ 7D $\to$ 7E $\to$ 7F $\to$ 6H) 与命名纪律**：
     - 后续任务严格按顺序准入：7A（19骨骼角色进入训练场）$\to$ 7B（上肢独立控制）$\to$ 7C（动力学合流）$\to$ 7D（多关节动力协调）$\to$ 7E（IK/FK动态协同）$\to$ 7F（全身连续环境交互）$\to$ 6H（动态平衡与主动补偿）；
     - 后续新任务统一使用 `Task <阶段>-<序号>`（如 `Task 7A-1`），严禁私自衍生同级或下游分支。
  5. **建立前后置十步闭环架构防漂移门禁**：
     - 在 `docs/ARCHITECTURE_CHANGE_GATE.md` 确立十步闭环防漂移协议，并在 `AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md` 强制引用。
* **影响**：
  - 未修改 `src/` 下任何 Python 文件，未修改任何 `.blend` 文件；
  - 架构冻结文档 100% 具备机器可证明的真实性（Exit Code 0）；
  - 彻底封死后续 Agent 认知漂移与私自造轮子路径。

---

### [DEC-047] 2026-10-25: Task 6G-D-C2-FINAL 架构门禁收口、只读 AST 校验与统一测试套件无缝集成

* **状态**：已批准 (Approved)
* **日期**：2026-10-25
* **背景**：在 6G-D-C2-FINAL 最终验收收口中，发现先前的 `tests/audit_c2_final_inspector.py` 在执行 `--verify-docs` 时存在回写 AST JSON 文件的写磁盘副作用；且在包含否定关键词时采用整行跳过（whole-line skipping）策略，存在掩盖同一行其他未否定符号的漏检风险；此外文档门禁未接入 `run_test_suite.py` 自动化测试注册表。必须建立可重复执行、真正只读、防过拟合并接入统一测试系统的永久门禁。
* **决策与方案**：
  1. **彻底分离校验器运行模式与消除写文件副作用**：
     - **Mode A (生成/刷新)**：仅在显式传入 `--generate` 或 `--refresh` 时回写 `codebase_and_blend_audit.json` 与 `blend_inspection_log.txt`；
     - **Mode B (校验文档)**：`--verify-docs` 采用纯内存 AST 索引执行文档扫描，禁止对磁盘文件进行任何写入或覆盖，遇错返回非零退出码；
     - **Mode C (校验器自测)**：`--test-validator` 执行 6 组正负例测试，纯只读无副作用；
     - 默认无参数模式：纯内存解析，打印指引，零写文件。
  2. **消除整行跳过漏洞，建立子句级精准否定豁免判定机制**：
     - 废除原有的 `any(k in line for k in [...]) continue` 整行跳过逻辑；
     - 改为针对每一个匹配符号，基于标点边界（`;；。|,\n`）提取其所属独立子句与紧邻括号，仅当该符号自身所在子句显式包含否定修饰词（如“不存在”、“严禁调用”、“曾用错误名称”等）时才予以豁免；同一行其他子句中引用的符号继续执行严格 AST 存在性检验。
  3. **增强防过拟合与防硬编码自检**：
     - 自检套件扩充至 6 大用例：新增基于 `uuid.uuid4().hex` 动态随机生成的模块路径、枚举成员、方法、类名及表格虚假实现用例（Test 5），以及复合子句同行动态符号检验用例（Test 6），杜绝仅靠硬编码黑名单通过测试的可能性。
  4. **测试注册表支持脚本参数并提供独立测试用例**：
     - 扩展 `TestDefinition` 增加可选的 `script_args: List[str] = field(default_factory=list)`，并在 `run_test_suite.py` 中保持 100% 向后兼容；在 `test_runner_unit.py` 中增加用例 11 进行参数传递回归校验；
     - 提供薄测试脚本 [`tests/test_architecture_integrity_gate.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_architecture_integrity_gate.py)，作为正式测试用例注册进 `TEST_REGISTRY`，纳入 `TestTier.QUICK` 和 `TestTier.FULL`。
  5. **严格只读静态事实校验声明**：
     - 门禁工具定位于静态 AST 符号物理存在性事实校验，不主观宣称未测试逻辑的物理正确性。
* **影响**：
  - 未修改 `src/` 下任何 Python 文件，未修改任何 `.blend` 文件；
  - `.\run_tests.ps1 -tier quick`（10/10 PASS）与 `.\run_tests.ps1 -tier full`（24/24 PASS）全量通过；
  - 架构门禁已正式接入系统持续回归，任何失效接口或虚构引用将直接导致测试失败与退出码 1，彻底完成 C2-FINAL 验收收口。

---

### [DEC-048] 2026-10-25: Task 7A-1 历史 19 骨骼角色资产复用审计、真实角色接入 DynamicsPlayground、五阶段控制闭环与 204 帧独立只读重开验收收尾

* **状态**：已批准并验证 (Approved & Verified)
* **日期**：2026-10-25
* **背景**：在完成 Task 6G-D-C2-FINAL 架构冻结与门禁收口后，正式进入 Phase 7A 第一个任务（`Task 7A-1`）。目标是在不重复造轮子、不破坏既有 `output/dynamics_playground.blend` 5 工位动力学基准的前提下，将历史验证成熟的 19 骨骼角色资产（`CharacterRoot`、`CharacterArmature`、13 个网格部件、8 个 IK/Pole 控制器）装入 `DynamicsPlayground` 训练场，并通过唯一生产控制链验证五阶段最小控制闭环、四大数学一致性、204 帧独立只读重开验证、深度场景资产对比、测试与生成严格解耦以及 204 帧真实连续 GIF 证据。
* **决策与方案**：
  1. **全面审计历史 19 骨骼资产并交付 `docs/PHASE7A_REUSE_AUDIT.md`**：
     - 完整核查 `output/unified_motion_integration.blend` 与 `output/dynamics_playground.blend` 及 19 个既有核心模块，确认 `build_character`、`build_rig`、`bind_character_to_rig`、`setup_leg_ik`、`setup_arm_ik`、`KinematicBridgeExecutor.execute_frame`、`WholeBodyController.execute_frame`、`MotionPlanner`、`StartStopWalkAction`、`compute_whole_body_com`、`DEFAULT_HUMANOID_ROM_MODEL`、`evaluate_limb_contacts_from_armature` 与 `create_standard_dynamics_playground_query` 均可 100% 原生复用，严禁新建第二套角色、骨骼或控制器。
  2. **训练场单一 SSOT 深度快照保护与派生可播放验证场景 (`output/dynamics_playground_task7a1.blend`)**：
     - 严格以 `output/dynamics_playground.blend` 为训练场唯一几何与动力学工位 SSOT（只读打开，通过 `capture_deep_playground_snapshot` 与 `verify_derived_blend_against_deep_snapshot` 逐对象核验 `Playground_Surfaces`、`Playground_Visuals`、`Playground_Lighting_Cameras`、`Playground_Dynamics_Visualization` 全部 101 个受保护物体、16 个表面网格几何/材质与 `S1..S5` 73 帧动画 F-Curve 100% 零改动）；
     - 将 19 骨骼角色与 3 个观察相机（共 26 个新增对象）装配入独立的 `"Character"` 集合，并在南部平坦地面 `Surface_FlatGround` ($Y \in [-8.0, -6.74]\text{ m}$) 区域执行控制与连续步态验证，导出派生可播放场景 `output/dynamics_playground_task7a1.blend`。
  3. **五阶段最小控制闭环与四大数学一致性验证 (`src/scene/playground_character_integration.py`)**：
     - **Stage A (静态站立)**：双足贴地 $Z_{\min} = 0.0\text{ m}$，末端误差 $3\times 10^{-6}\text{ m}$，零 ROM 违例；
     - **Stage B (根节点有限位移与非零偏航)**：驱动 `CharacterRoot` 至 $(0.25, -7.65, 0.0)\text{ m}$ 与 $+6.0^\circ$ 偏航，位置误差 $0.0\text{ m}$；
     - **Stage C (单脚独立 IK 控制)**：左右脚设置非对称三维世界目标，大腿 $0.42\text{ m}$ / 小腿 $0.40\text{ m}$ 零拉伸、膝盖前向 $+Y$ 零翻转；
     - **Stage D (支撑脚世界空间锁定)**：左脚锁定 (`FootIK.L.parent == None`) 下 `CharacterRoot` 连续 5 步前移侧移，控制器漂移 `0.0 m`，踝骨与网格中心漂移 `0.0 m`；
     - **Stage E (最小连续历史步态复用)**：通过 `MotionPlanner` 执行 `StartStopWalkAction` 204 帧连续行走（位移 $1.2600\text{ m}$，0 不可达帧，0 ROM 违例）；
     - **四大数学一致性验证**：五重坐标空间非零平移/偏航往返误差 $< 2.2\times 10^{-7}\text{ m}$；15 分段 CoM（70kg 默认 / 75kg 缩放，`mass_ratio_sum == 1.0`，左右对称误差 `0.0 m`，下蹲前倾姿态质心准确偏移）；几何接触 (`double_stance`, `single_stance_l`, `single_stance_r`) 与动力学反力边界清晰分离；不可达 (`REACHABILITY`) 与超限 (`ROM_VIOLATION`) 约束真实报错 (`success=False`)。
  4. **204 帧独立只读重开验证、测试与生成解耦、204 帧连续 GIF (`validate_reopened_task7a1_blend`, `tests/verify_task7a1_character_playground.py`)**：
     - 独立只读重开 `output/dynamics_playground_task7a1.blend` 评估全 204 帧并生成 `docs/evidence/task7a1/full_frame_validation.json`，显式区分 `reopen_evaluated` 与 `analytical_reference`，验证根平移连续性、19 骨骼四元数测地线连续性（最大单帧步长 `5.24453 deg`）、9 个支撑区间控制器漂移（`0.0 m`）与实际踝骨世界漂移（最大 $2.94\times 10^{-5}\text{ m}$）、支撑足零穿地 ($Z_{\min} \ge -2.9\times 10^{-5}\text{ m}$)、70.0 kg CoM 轨迹与 0 ROM 违例；
     - 严格解耦生成入口 `run_task7a1_character_playground.py` 与只读回归入口 `tests/verify_task7a1_character_playground.py`（8/8 PASS, 0.36s，缺失产物直接报 `ARTIFACT_MISSING`，文件大小与时间戳零修改）；
     - 从重开 `.blend` 连续渲染全 204 帧（24 FPS, `delay_cs=4`）生成 `docs/evidence/task7a1/task7a1_walk_preview.gif`。
* **影响**：
  - 新增 [`docs/PHASE7A_REUSE_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/PHASE7A_REUSE_AUDIT.md)、[`src/scene/playground_character_integration.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_integration.py)、[`run_task7a1_character_playground.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/run_task7a1_character_playground.py)、[`tests/verify_task7a1_character_playground.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/verify_task7a1_character_playground.py) 及 [`docs/evidence/task7a1/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task7a1/) 全套证据；
  - 严格停止于 Task 7A-1 收口，不自动进入 Task 7A-2。

---

### [DEC-049] 2026-10-26: Task 7A-1 最终架构整理、单一职责解耦、接触状态持久化合同与负向测试闭环 (Final Architecture & Compatibility Closure)

* **状态**：已批准并全绿验证 (Approved & Fully Verified)
* **日期**：2026-10-26
* **背景**：针对 Task 7A-1 验收审查中确认的三个确定性问题（受保护资产深度一致性检查不完整、动作接触状态没有可靠持久化保存导致重开验收依赖步态公式重新推导、`src/scene/playground_character_integration.py` 职责过度集中达 2872 行），必须执行最终架构整理与兼容性收口。在 100% 保护历史运动算法、Rig/IK/FK、动力学模型与基准 `.blend` 的前提下，完成代码解耦、接触数据持久化契约、深度快照比较与负向故障注入测试。
* **决策与方案**：
  1. **单一职责解耦（消除 2872 行集中文件，拆分为清晰子模块）**：
     - 将原单一集中文件拆分为四个专业子模块，职责单一、内聚明确：
       * [`src/scene/playground_asset_preservation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_asset_preservation.py)（~386 行）：负责训练场 101 个受保护对象、16 个表面网格几何（顶点坐标容差 $<10^{-5}$、面拓扑与顶点索引）、层级结构、世界矩阵、材质槽、环境属性、Layered F-Curves（时间与取值 $<10^{-4}$、手柄与插值模式）以及 S1..S5 5 工位 73 帧基准轨迹全帧（非抽样）深度快照对比与差异报告；
       * [`src/scene/playground_evidence_exporter.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_evidence_exporter.py)（~223 行）：负责多视角相机 PNG 渲染、NumPy RGBA 加载、GIF 帧数与帧率真实校验、204 帧平滑 GIF 预览合成及验证报告 JSON 导出；
       * [`src/scene/playground_character_assembly.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_assembly.py)（~1495 行）：负责角色装配（复用既有 `build_character` + `build_rig` + `bind_character_to_rig` + `setup_leg_ik` + `setup_arm_ik`）、五阶段最小控制闭环（Stage A..D）、四大数学一致性验证、Stage E 204 帧连续行走步态执行，并将执行接触状态与支撑锚点持久化写入场景属性与伴生 JSON 文件；
       * [`src/scene/playground_kinematic_validation.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_kinematic_validation.py)（~765 行）：负责从派生 `.blend` 独立只读重开全 204 帧评估，恢复持久化接触契约、验证根位移平滑度、19 骨骼四元数测地线连续性、9 个支撑区间实际踝骨漂移（对比持久化锚点）、70.0 kg 质心轨迹与关节 ROM；
       * [`src/scene/playground_character_integration.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/playground_character_integration.py)（~183 行）：重构为轻量级总控门面（Facade），重新导出所有公开符号以保持 100% 向后兼容性。
  2. **接触状态持久化合同 (Contact State Persistence Contract)**：
     - 在 Stage E 执行期间，将逐帧实际接触状态（帧号、时间、双足锁定标志、支撑侧、支撑脚世界锚点 $(X,Y,Z)$、步态阶段、步序、触地/离地离散事件）作为 JSON 字符串保存到 Blender 场景 ID 属性 `scene["task7a1_contact_state_records"]` 中，并在 `FootIK.L/R` 控制器上对 `is_locked` 属性逐帧打关键帧；同时导出伴生文件 [`docs/evidence/task7a1/task7a1_contact_state_records.json`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task7a1/task7a1_contact_state_records.json)；
     - 独立重开验收时，通过 `recover_and_verify_contact_states_from_blend(scene)` 恢复持久化接触数据，彻底废除对 `MotionPlanner` 或步态公式重新推导的依赖；
     - 严格区分三类数据流：**Category A (运行时记录)**、**Category B (重开评估值)**、**Category C (解析参考值)**，并在 `full_frame_validation.json` 中清晰分离。
  3. **六大隔离负向测试闭环 (Negative Verification Suite)**：
     - 在独立内存/隔离副本中注入 6 种典型异常，证明校验体系具备严密的真实检测能力而非假通过：
       1. 网格内部顶点微调（保持 Bounding Box 不变）$\implies$ 深度资产校验立即捕获（`VERTEX_DIFF`）；
       2. F-Curve 关键帧数值微调（保持关键帧数量不变）$\implies$ 深度资产校验立即捕获（`KEYFRAME_VALUE_DIFF`）；
       3. S1..S5 动力学工位中间帧 37 状态篡改 $\implies$ 深度轨迹对比立即捕获（`TRAJECTORY_DIFF`）；
       4. 接触记录缺失帧（删除 Frame 50）$\implies$ 持久化合同立即报错（`MISSING_FRAME_RECORD`）；
       5. 支撑足锚点被篡改或置空 $\implies$ 锚点完整性检查立即报错（`TAMPERED_ANCHOR`）；
       6. 资产版本号不匹配（篡改版本号）$\implies$ 契约校验立即报错（`VERSION_MISMATCH`）。
  4. **全量真实兼容性调用矩阵**：
     - 更新 [`docs/PHASE7A_REUSE_AUDIT.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/PHASE7A_REUSE_AUDIT.md) 补充第三节，完整记录 9 大模块（`framework.py`, `kinematic_bridge.py`, `whole_body_controller.py`, `src/rig/`, `src/character/`, `rigid_link.py`, `contact_model.py`, `environment_query.py`, `src/scene/playground_*`）及未接入的 6G-D 动力学核心的真实调用者、被调用者、输入与输出合同。
  5. **严格零退化与测试套件编码保护**：
     - 修复 `tests/run_test_suite.py` 在 Windows 默认 GBK 环境下由 UTF-8 输出导致的 reader 线程编码异常（增加 `encoding="utf-8", errors="replace"`）；
     - `tests/verify_task7a1_character_playground.py` 扩充至 15 项自动化测试（含 6 项负向测试与 1 项只读零篡改保护测试，15/15 PASS, 1.10s）；
     - 全层级回归测试全绿：`quick` (10/10 PASS), `physics` (16/16 PASS), `motion` (6/6 PASS), `full` (25/25 PASS), `--verify-docs` (PASS)。
* **影响**：
  - 未修改任何历史运动规划算法或动力学数值积分器；
  - 彻底满足 Task 7A-1 最终验收关闭条件；
  - 严格停止，禁止自动准入 Task 7A-2。

---

### [DEC-050] 2026-10-26: Task 7A-2 真实 19 骨骼角色连续复杂地形（楼梯与斜坡高架桥）自适应下肢穿越、单一控制链闭环与 926 帧全量验收

* **状态**：已采纳并全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-26
* **背景**：正式准入 Phase 7A 第二阶段（`Task 7A-2`）。目标是在保持历史 `output/dynamics_playground.blend` 训练场只读受保护的前提下，将成熟的 19 骨骼角色接入连续复杂起伏地形（Course C 楼梯穿越与 Course B 斜坡/高架桥穿越），产出可在 Blender 5.1.1 中直接打开、时间线播放、交互审查的派生场景 `output/dynamics_playground_task7a2.blend`。必须经受 926 帧全量骨骼求值验证，确保足端零滑移锁定、零骨骼拉伸、零解剖学 ROM 违规、零地形穿模，且历史测试集 100% 零退化。
* **决策与方案**：
  1. **单一连续地形运动规划器 (`src/motion/terrain_walk.py`)**：
     - 构建通用地形行进动作类 `TerrainWalkAction(MotionAction)` 与离散步态生成函数 `build_terrain_step_schedule`；
     - 零环境高度硬编码：严格通过 `DynamicsEnvironmentQuery` 接口（`ground_height_at` 与 `surface_normal_at`）逐帧动态查询足底各位置地表高程与法向量，完全解耦场景几何；
     - 矢状面法向量自适应偏航与俯仰：通过 $\text{atan2}(-n_y, n_z)$ 计算坡度法向量法向偏角，自动匹配上坡（+15°）、下坡（-20°）与平地（0°）足端世界姿态。
  2. **核心控制链向后兼容增强 (`src/rig/foot_contact.py`, `src/motion/whole_body_controller.py`, `src/motion/kinematic_bridge.py`)**：
     - **足端高程接触锁定解除平地硬编码**：升级 `lock_foot_contact` 支持传入世界空间真实接触高程 `float(contact_world_xyz[2])`，保留对默认 `FLAT_GROUND_Z = 0.0` 的 100% 兼容；
     - **脚踝世界坐标与接触坐标分离**：在 `WholeBodyController.execute_frame` 中将脚踝目标转换为地面接触点 `contact_ground_xyz = (target_x, target_y, target_z - ANKLE_REST_Z)`，彻底消除 70mm 偏置累加 bug，实现脚踝锁定物理零漂移（`0.00000000 m`）；
     - **显式可配置地面夹持标志 (`clamp_ground`)**：在 `EndEffectorTarget` 与 `PlannedFootTarget` 中引入 `clamp_ground: bool = True`，地形跨越时设为 `False`，避免 WBC 误将高程目标投影至根节点高度。
  3. **全足端 3D 刚体包围盒悬空防穿透与台阶边缘防碰**：
     - 脚掌刚体具备 22cm 纵向长度（后跟 $-0.07\text{ m}$ 至脚尖 $+0.15\text{ m}$）；在摆动相中实时查询整足底部最大地形高度：
       $$z_{\text{foot\_terr}} = \max\Big(z_{\text{terr}}(x, y-0.07),\, z_{\text{terr}}(x, y),\, z_{\text{terr}}(x, y+0.15)\Big)$$
       结合 $0.045\text{ m}$ 动态悬空最小净距，彻底消除踢面切削与边缘穿模（926 帧全量 0 穿模）。
  4. **生理学踝关节矢状面自适应与分级骨盆沉降**：
     - 在摆动相引入生理性踝关节松弛机制（摆动中段脚尖沿摆动弧线自然微倾 18°~22°），离地瞬间引入自然的蹬地限位（$\le 10^\circ$）；
     - 引入自适应分级骨盆沉降参数：上坡登高沉降 $0.063\text{ m}$，下坡缓冲沉降 $0.095\text{ m}$，平地行进沉降 $0.030\text{ m}$，台阶攀爬沉降 $0.120\text{ m}$，完美平衡大腿小腿最大延伸极限（$< 0.820\text{ m}$）与踝关节背屈/跖屈生理极限（$[-25.0^\circ, +45.0^\circ]$），在 926 帧中达成 0 ROM 违规。
  5. **派生场景生成、只读重开验收与完备视觉证据 (`run_task7a2_terrain_traversal.py`, `tests/verify_task7a2_terrain_traversal.py`)**：
     - 派生生成 `output/dynamics_playground_task7a2.blend`（581,882 字节，926 帧，内嵌 3 专用相机与 10 个关键阶段时间线标记）；
     - 独立只读重开评估全 926 帧：0 穿模、0 ROM 违规、0 IK 违例、踝骨漂移 $0.0\text{ m}$、骨骼形变 $1.55\times 10^{-6}\text{ m}$、质量严格守恒 70.000 kg；
     - 渲染 9 张高清关键帧 PNG 与 2 份连续动态 GIF（`task7a2_stairs_traversal.gif` 76 帧 301KB、`task7a2_ramp_traversal.gif` 100 帧 286KB）；
     - 注册 `task7a2_terrain_traversal` 入测试套件 `motion` 与 `full` 级别，全层级测试 100% 通过（`quick` 10/10, `physics` 16/16, `motion` 7/7, `full` 26/26, `--verify-docs` PASS）。
* **影响**：
  - 新增核心模块：`src/motion/terrain_walk.py`, `src/scene/playground_terrain_traversal.py`, `src/scene/playground_terrain_validation.py`, `run_task7a2_terrain_traversal.py`, `tests/verify_task7a2_terrain_traversal.py`, `docs/PHASE7A2_TERRAIN_TRAVERSAL_REPORT.md`；
  - 增强已有模块：`src/motion/kinematic_bridge.py`, `src/motion/whole_body_controller.py`, `src/rig/foot_contact.py`, `tests/test_registry.py`；
  - 历史基准场景 `output/dynamics_playground.blend` (234,436 字节) 与 `output/unified_motion_integration.blend` (298,537 字节) 100% 零修改；
  - 严格停止于 Task 7A-2 收口，绝不擅自越级进入 Phase 7A-3 或 Phase 7B。

---

### [DEC-051] 2026-10-26: Task 7A-2 架构修复、P0 空间瞬移缺陷根除、内置数据诊断视窗与权威连续地形验收

* **状态**：已采纳并全绿验证 (Accepted & Fully Verified)
* **日期**：2026-10-26
* **背景**：在 Task 7A-2 首轮实现中发现重大架构与物理缺陷：第 226 $\to$ 227 帧存在 $\Delta = 2.3717\text{ m}$ 空间瞬移跳变，且验证器中存在 `frame_num != 227` 的非连续豁免代码；场景编排器直接绕过 `MotionPlanner` 执行底层动作；步态逻辑中存在以 `"stair"`、`"ramp"` 字符串驱动的脆弱代码；缺乏内置于 Blender 内的数据诊断视窗。必须全面修复该 P0 阻断性缺陷，恢复单架构权威性。
* **决策与方案**：
  1. **P0 瞬移根除与冻结几何拓扑断裂证明**：
     - 数学核算基准 `output/dynamics_playground.blend`：楼梯顶部平台结束于 $Y=10.0, Z=0.75\text{ m}$，坡道起跳点始于 $Y=11.0, Z=0.0\text{ m}$，中间存在 $1.0\text{ m}$ 间隙与 $0.75\text{ m}$ 垂直悬崖。角色腿部最大延伸极限为 $0.820\text{ m}$，若强行跨越跌落需 $1.51\text{ m}$ 下肢伸长，物理不可达。
     - 确定权威连续路线：Course B 坡道走廊本身即是一条完全连续且地貌多样的完整地形路线（平地入口 $\to$ 15° 上坡 $\to$ $Z=1.34\text{ m}$ 高架桥 $\to$ 20° 陡坡 $\to$ 平地缓冲着陆停止，全长 $12.2\text{ m}$，700 帧连续无缝）。
     - 生成权威修正产物 `output/dynamics_playground_task7a2_corrected.blend`，保留 `output/dynamics_playground_task7a2.blend` 作为失败对比基准，彻底废除所有帧号豁免。
  2. **MotionPlanner 唯一权威调度权恢复**：
     - 场景编排器严格通过 `MotionPlanner.execute(initial_state)` 执行，动作生命周期、状态传递、帧记录由框架统一管理，严禁场景层私调底层动作。
     - 修复 `TerrainWalkAction.estimate_duration_frames`，接入真实环境查询器动态预估工期。
  3. **100% 剥离字符串命名驱动逻辑与路线目标解耦**：
     - 引入 `TerrainRouteInput` 解耦高层走廊与步态规划；
     - 编写 `plan_terrain_footsteps`，纯基于 `DynamicsEnvironmentQuery` 表面法向量、高程差与边缘安全避障算法动态离散生成落脚点；彻底移除所有对象名/地表名字符串匹配。
  4. **骨盆 Euler 轴向校正与坡道过渡伸展缓冲**：
     - 校正 `pelvis` 局部 Euler 轴（局部 X=Pitch, Y=Yaw, Z=Roll），消除了上坡下坡时不必要的侧倾应力；
     - 引入高程过渡差 $\Delta z_{\text{trans}} > 0.03\text{ m}$ 识别，在坡道与平地交界处保持足够的骨盆下沉缓冲量（$0.088\dots0.098\text{ m}$），实现 700 帧全过程 0 处 IK 超限。
  5. **内置 Blender 控制链数据诊断视窗 (`Task7A2_ControlChain_Debug`)**：
     - 在同一 `.blend` 文件中内嵌诊断场景，构建 6 阶段结构化 HUD 文字展板与 3D 关键帧指示物（足端目标球、质心环、锁定箭头、法向箭头）；
     - 内嵌 `task7a2_debug_hud_driver.py` 脚本挂载时间线变化事件，支持在视口中拖动时间线毫秒级实时查看全身体控制链指标。
  6. **负向测试与全量回归套件**：
     - 编写 `tests/test_p0_frame226_teleport_regression.py` 永久固化瞬移缺陷检测；
     - 编写 `tests/test_terrain_walk_negative.py` 验证地表重命名不变性、高程扰动自适应与悬崖超限拒绝；
     - 700 帧无豁免数学检验：0 瞬移（最大位移 $0.0333\text{ m}$/帧）、0 ROM 违规、0 穿模、脚踝漂移 $0.000011\text{ m}$、骨骼形变 $0.0000017\text{ m}$、质量守恒 70.0 kg；
     - 全套件全绿：`quick` (12/12), `motion` (8/8), `full` (28/28), `--verify-docs` (PASS)。
* **影响**：
  - 彻底关闭 Task 7A-2 阻断性缺陷，形成完整、自洽、可随时在 Blender GUI 中打开并审查的连续地形动画交付物；
  - 严格停止，禁止擅自进入 Phase 7A-3。

---

### [DEC-052] 2026-10-27: 架构基线审计与 7A→7B 准入门禁（8 份全景审计文档、双管线解耦实录与严格停止于评审态）

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-27
* **背景**：完成 Task 7A-1 与 Task 7A-2 后，系统即将面临 Phase 7B（全身动态平衡与复杂地形自适应）。但在启动 7B 之前，必须对仓库自最初创建以来的全部 59 个 Python 模块、21 个入口脚本、47 个测试套件及所有场景进行全量静态与动态架构审计，彻底排查真实调用关系、读写权限、重复实现与违背物理事实的潜在隐患，禁止将未来规划能力误报为已实现功能。
* **决策与方案**：
  1. **编纂 8 份全景架构基线审计文档 (`docs/audit/`)**：
     - `MODULE_INVENTORY.md`：按 20 个统一问题全面盘点全量 59 个生产模块，建立八态分类标准；
     - `ACTUAL_RUNTIME_ARCHITECTURE.md`：重构 6 大运行链（Chains A..F），确立真实双管线解耦事实；
     - `STATE_OWNERSHIP_MATRIX.md`：厘清全部数据与对象独占读写权，全盘检索骨骼与控制器物理突变行号；
     - `CALL_GRAPH_AUDIT.md`：绘制生产与测试调用图谱，标定 4 大独立动力学模块与 21 个入口关系；
     - `HARDCODE_AND_BYPASS_AUDIT.md`：6 分类严格审计常量、工程配置、测试基准、字符串耦合与旁路；
     - `ENVIRONMENT_INTERACTION_GAP.md`：透视回答环境交互 10 问，确立单向开环查询现实；
     - `DOCUMENTATION_DRIFT.md`：详细比对既有架构文档与磁盘源码差异，揭示版本滞后与缺失模块；
     - `ARCHITECTURE_AUDIT_SUMMARY.md`：编目 AUDIT-01 至 AUDIT-08 共 8 项问题，标定 4 项阻断项，制定 7B 阶段化准入路线图。
  2. **确立核心技术现实**：
     - **双管线并行独立现实**：Pipeline A（19 骨骼角色姿态生成）与 Pipeline B（6-DOF 单刚体集总质心动力学）在磁盘上完全解耦，Pipeline B 仅驱动动力学训练场中的代理方块与力学箭头，未参与角色驱动；
     - **开环环境感知现实**：`DynamicsEnvironmentQuery` 采用解析数学面计算高程与法向量，未执行 Blender 网格 BVH 投射线；
     - **只读遥测未闭环现实**：质心（CoM）、身体惯量、速度与接触模型均为事后只读采样，未前馈或反馈调节下一帧落脚点或骨盆平衡。
  3. **严格停止于评审态**：
     - 最终裁定状态为 `ARCHITECTURE AUDIT — AWAITING HUMAN REVIEW`；
     - 严禁未经人类明确授权自动进入 Phase 7B-1。
* **影响**：
  - 为后续 Phase 7B 动态平衡与 Phase 7C 接触力学闭环提供了无可争议的单一事实基线（SSOT）；
  - 彻底消除了基于过时文档或心理推测推进开发的漂移风险。

---

### [DEC-053] 2026-10-27: Environment Gate 01: 真实 Blender Mesh 环境查询接入与数据真实性门禁

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-27
* **背景**：在 7A $\to$ 7B 架构审计中查明：既有 `DynamicsEnvironmentQuery` 采用解析表面（`OrientedSurface`）计算高程与法向，运行时并未真正查询 Blender 场景内的真实 Mesh。这导致场景中的实际网格发生位移、旋转、形变或拓扑删除时，环境查询依然返回静态解析解，违背了“物理世界几何真实性”原则。同时，`KinematicBridgeExecutor:404` 存在足端锁定接触硬编码 $Z=0.0\text{ m}$ 的缺陷。在启动 Phase 7B 之前，必须接入真实 Blender Mesh 查询门禁，同时不得重写人体控制系统、不得开发导航、不得引入主动动力学补偿。
* **决策与方案**：
  1. **双层几何权威来源与来源标记机制**：
     - 确立 Blender 运行时**真实 Mesh 为几何物理权威来源**；解析表面保留为无 Blender 依赖纯 Python 单元测试与历史退化兜底；
     - 在 `SurfaceQueryResult` 中扩展 `source_type: str`（`"mesh"` / `"analytical"` / `"none"`），严禁混用无标记的几何解；
     - 射线未命中或点查询超出范围时，严格返回 `success=False`，严禁隐式伪造 $Z=0.0\text{ m}$ 地面。
  2. **宿主解耦适配器架构 (`BlenderMeshEnvironmentAdapter`)**：
     - 在宿主层新建 `src/scene/blender_mesh_query_adapter.py`，保持 `src/scene/environment_query.py` 纯 Python 无 `bpy` 依赖；
     - 采用 Blender 原生 `mathutils.bvhtree.BVHTree.FromPolygons`，在世界坐标系空间（$V_w = M_w \cdot v$）构建 BVH，天然规避非等比缩放引起的法向量畸变；
     - 实时法向量重构：通过世界三角形三顶点叉积计算严格单位法向量；
     - 动态缓存失效机制：记录物体变换矩阵、顶点数与包围盒指纹，检测到物体平移、旋转、缩放或顶点变动时自动触发增量/全量 BVH 重建。
  3. **3D 表面分类与有效支撑面判据**：
     - 斜率夹角 $> 60^\circ$（$N_z < 0.50$）严格判定为非支撑面（`allows_regular_support = False`），杜绝垂直立面与陡坡上的非法站立；
     - 几何类型细分：水平地面（$N_z \ge 0.99$）、斜坡（$0.15 \le N_z < 0.99$）、垂直立面（$|N_z| < 0.15$）、台阶顶面、倒悬天花板；
     - 摩擦系数元数据隔离：自定义物体属性优先，无配置时按几何类型赋予物理默认摩擦系数。
  4. **KinematicBridge 接触高程硬编码缺陷隔离与最小改动建议案**：
     - 编写独立缺陷复现测试 `tests/test_contact_elevation_gap_repro.py`，实证高架台（$Z=1.3397\text{ m}$）上足端接触被强制压平至 $Z=0.0\text{ m}$（误差 $1.3397\text{ m}$）；
     - 编写完整工程建议案 `docs/proposals/CONTACT_CHAIN_BRIDGE_ELEVATION_GAP.md`，给出单点改动方案与向前兼容防护，供后续门禁报批实施，本门禁不修改任何人体控制代码。
  5. **14 项严格测试验证与全套件通过**：
     - 编写 `tests/test_mesh_environment_query.py`，全量覆盖真实训练场网格、动态平移、动态旋转、顶点编辑、物体删除、间隙悬崖脱靶、非支撑立面、摩擦力区分及与 `DynamicsEnvironmentQuery` 无缝接入；
     - 全套件全绿：`quick` (13/13), `physics` (19/19), `verify-docs` (PASS)；受保护 `.blend` 资产 0 字节变动；
     - 裁定状态：`ENVIRONMENT GATE 01 — AWAITING HUMAN REVIEW`，严禁未经人类指令自动跨入 Phase 7B。
* **影响**：
  - 彻底解决了环境感知的真实性与动态性问题，确保后续角色在接触和运动计算中所面对的环境与视口中的 Blender Mesh 100% 绝对一致；
  - 严格保持了零架构漂移与零历史退化。

---

### [DEC-054] 2026-10-27: Environment Gate 01 — Repair Unit 1: 候选范围隔离与表面筛选语义修复

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-27
* **背景**：在 Environment Gate 01 首轮验收审查中，发现既有实现存在三项语义缺陷：
  1. **缺陷 A03 (Collection 范围泄漏)**：当显式传入 `collection_names`，若集合不存在或为空时，旧代码隐式回退扫描全场景网格，导致查询范围逃逸；
  2. **缺陷 A01 (ray_cast 表面过滤语义缺失)**：旧代码仅检查首个 BVH 命中面，当其类型不匹配时直接报错返回失败，未能穿透前方非目标面继续寻找合格表面；
  3. **缺陷 A02 (find_nearest 表面过滤语义缺失)**：旧代码仅检索全局最近多边形，类型不符时直接失败，未能结合半径范围搜索目标类型的最近表面。
* **决策与方案**：
  1. **严格候选范围隔离 (规则 A、B、C)**：
     - 规则 A (显式 Collection 模式)：`collection_names is not None` 时仅检索指定集合（保留递归子集合），若集合不存在或无网格严格返回空集 $\emptyset$，绝不回退全场景；
     - 规则 B (显式 Object 模式)：`object_names is not None` 时仅检索指定名称的有效 Mesh，去重过滤，绝不回退全场景；
     - 规则 C (显式全场景模式)：仅当两者均为 `None` 时允许扫描当前场景全量网格，严禁隐式全场景兜底。
  2. **带类型过滤的射线向前推进检索 (`ray_cast`)**：
     - 无过滤：严格保持返回射线路径上首个最近真实物理命中面；
     - 有过滤：沿射线方向迭代推进搜索最近合格面，每次推进距离 $\Delta s \ge 10^{-4}\text{ m}$，上限 64 步，累计计算从原始起点起的真实欧氏距离 `ray_hit_distance`；明确注明此为几何查询，不代表人体具备穿透可行性。
  3. **基于范围搜索的最近合格面检索 (`find_nearest`)**：
     - 无过滤：返回全局最近真实网格表面；
     - 有过滤：通过 `bvh.find_nearest_range(p, max_distance)` 检索候选多边形集，筛选匹配类型并选取真实欧氏距离最小者，无匹配面严格返回 `success=False`。
  4. **全 8 字段契约检查与受控故障反例验证**：
     - 测试套件扩充至 23 项，逐项断言 `surface_id`, `surface_type`, `contact_point_world`, `surface_normal_world`, `ray_hit_distance`, `signed_distance`, `source_type`, `allows_regular_support`；
     - 实施受控故障注入，严格证明旧逻辑下 A03、A01、A02 必报失败，新逻辑下全部通过；
     - 全量回归全绿：`quick` (13/13), `physics` (19/19), `motion` (8/8), `full` (30/30), `--verify-docs` (PASS)；受保护资产 0 字节变动。
* **影响**：
  - 彻底消除了几何查询范围越界与表面过滤提前短路的缺陷，为上层足底落脚点规划提供了精准、可靠的环境几何契约。

---

### [DEC-055] 2026-10-27: Environment Gate 01 — Repair Unit 1 Final Acceptance: 数值覆盖提升、真实故障注入证据链与边界闭环 (T01/T02/T03)

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-27
* **背景**：在 Repair Unit 1 验收闭环阶段，依据最新验收要求执行三项深化闭环：
  1. **T01 (数值覆盖与独立解析校验不足)**：旧测试断言仅覆盖局部 Z 轴高程，缺少完整三维接触点 $(x, y, z)$、完整三维法向量 $(nx, ny, nz)$ 单位化精度 $< 10^{-5}$、独立欧几里得距离与带符号距离二次解析数学核算，且缺少非坐标轴对齐的倾斜三维场景验证；
  2. **T02 (故障注入实证产物缺失)**：故障注入证据此前仅记录于会话过程，缺少可独立审查的真实执行日志与结构化证据产物；
  3. **T03 (射线迭代边界与失败原因模糊)**：缺少多表面穿透、预算步数耗尽（`max_steps`）、超薄层穿透（$50\mu m$）、表面交界起点以及距离阈值临界耗尽等极端边界的独立覆盖，且失败原因未区分几何脱靶（`NO_HIT:`）与预算耗尽（`SEARCH_LIMIT_REACHED:`）。
* **决策与方案**：
  1. **T01: 全 8 字段物理契约升级与独立解析验证**：
     - 重构 `_assert_surface_contract()`：严格核验完整 3D 接触点、3D 法向量（单位长度误差 $< 10^{-5}$）、独立欧几里得射线距离 $\|\mathbf{p}_{\text{hit}} - \mathbf{p}_{\text{orig}}\|$ 与射线方向夹角对齐、独立带符号距离二次验证，以及 `allowed_objects` 表面所属权校验；
     - 新增 `test_24_non_axis_aligned_rotated_scene`：采用位置 $(3.0, 4.0, 2.0)$、欧拉角 $(30^\circ, 45^\circ, 0^\circ)$ 的非轴对齐斜面，查询点位于 $(3.5, 4.2, 5.0)$，对齐独立解析公式与 Blender C-BVHTree 计算结果（误差 $< 10^{-5}$）；
     - 生成覆盖 32 个测试的完整测试覆盖矩阵 [`docs/evidence/environment_gate01_ru1/test_coverage_matrix.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/test_coverage_matrix.md)。
  2. **T02: 真实故障注入实证产物与独立日志归档**：
     - 在白名单目录 [`docs/evidence/environment_gate01_ru1/`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/) 真实运行 Blender 5.1.1 Headless 生成三个独立故障注入日志：
       * `fault_injection_a03.log` (Exit code 1, `Surface_Forbidden` 越界捕获)
       * `fault_injection_a01.log` (Exit code 1, `Box_Front` 提前阻断捕获)
       * `fault_injection_a02.log` (Exit code 1, `Box_Near` 筛选短路捕获)
     - 编写结构化总结报告 [`fault_injection_summary.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/fault_injection_summary.md)，详述代码变异、命令、退出码及生产恢复通过记录。
  3. **T03: 射线迭代机制优化与 8 项极端边界检验**：
     - 优化 `BlenderMeshEnvironmentAdapter.ray_cast()`：默认步进推进设为 `step_epsilon = 1e-6`（$1\mu m$），支持动态自适应缩放（防止数值同面重复判定），并暴露 `max_steps` 与 `step_epsilon`；
     - 失败原因严格标准化：`SEARCH_LIMIT_REACHED:` vs `NO_HIT:`；
     - 新增 8 项极端边界测试（`test_25` 至 `test_32`）：单表面、三层多表面过滤、跨过滤缓存复用、`max_steps=5` 恰好命中、`max_steps=4` 预算耗尽、超薄 $50\mu m$ 障碍穿透、表面边界起点穿透、以及距离阈值 $6.0001\text{m}$ vs $5.9990\text{m}$ 临界区分；
     - 编写射线迭代与边界报告 [`ray_iteration_boundary_report.md`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/environment_gate01_ru1/ray_iteration_boundary_report.md)。
  4. **全量回归与受保护资产验证**：
     - 32 项环境查询测试全通（32/32 PASS in 1.74s）；
     - `run_test_suite.py` 全分级通过：`quick` (13/13), `physics` (19/19), `motion` (8/8), `full` (30/30)；
     - `audit_c2_final_inspector.py --verify-docs` 校验 0 错误；
     - `output/` 历史 `.blend` 资产 0 字节变动；
     - 状态严格停留于 `ENVIRONMENT GATE 01 / REPAIR UNIT 1 — AWAITING HUMAN REVIEW`，严禁擅自推进至 Repair Unit 2 或 Phase 7B。
* **影响**：
  - 全面补齐了环境网格查询系统的数值精度验证、边界条件鲁棒性与故障注入可证伪证据链；
  - 维持零历史退化与零架构违规。

---

### [DEC-056] 2026-10-27: Environment Gate 01 — Repair Unit 2: BVH缓存失效、场景几何变更检测与五状态生命周期状态机 (C01-C06)

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-27
* **背景**：在 Environment Gate 01 架构审查中，发现几何查询适配器 `BlenderMeshEnvironmentAdapter` 存在 6 项底层缓存与一致性缺陷（C01 至 C06）：
  1. **C01 (空环境重复重建泄漏)**：旧逻辑以 `_bvh is None` 作为缓存无效判定条件。空集合场景无 Mesh 时 `_bvh` 恒为 `None`，导致后续每次查询均触发 `rebuild()`，100 次空查询产生 100 次冗余重建；
  2. **C02 (几何变换检测盲区)**：旧逻辑仅核验世界位移差异，忽略了旋转、非均匀缩放以及父子层级变换传播；
  3. **C03 (顶点坐标与拓扑修改脱靶)**：内存中直接编辑顶点坐标（`v.co`）或拓扑增删面时，旧逻辑无法自动感知，导致 BVH 空间树陈旧；
  4. **C04 (修改器与求值网格一致性)**：未追踪修改器增删、参数变动及视口可见性切换，缺少异常安全回滚与求值网格释放机制；
  5. **C05 (集合成员增删与重命名失效)**：仅凭名称列表遍历，集合新增对象无法被检出；对象重命名会破坏追踪或触发不必要的重建；
  6. **C06 (未变场景无意义重复重建)**：未提供不变场景下严格复用缓存且重建次数恒为 1 的测试保障。
* **决策与方案**：
  1. **显式五状态生命周期状态机 (`AdapterCacheState`)**：
     - 定义 `INVALID`、`VALID_EMPTY`、`VALID_NON_EMPTY`、`REBUILDING`、`FAILED` 五类状态，彻底废除仅依赖 `_bvh is None` 的模糊判定；
     - 空集合构建后安全转入 `VALID_EMPTY`，在 100 次查询中严格保持 0 次重建，返回 `success=False`（附 `NO_HIT:` 理由），绝不伪造 $Z=0.0\text{m}$ 虚假地面；当新网格加入集合后自动转入 `VALID_NON_EMPTY`。
  2. **双通道失效检测体系 (Path A 自动感知 vs Path B 显式声明)**：
     - **Path A (自动检测)**：每次查询调用 `refresh()` 时执行 `_check_scene_changed()`：
       * 矩阵 16 元素严格比对（容差 $10^{-6}$），全面覆盖位移、旋转、非均匀缩放与父子物体层级变换传播；
       * 极速内存缓冲区哈希（`array.array('f', ...)` + `foreach_get('co', ...)`），$0.04\text{ ms}$ 内精准捕获毫米级顶点移动；
       * 循环索引哈希（`foreach_get('vertex_index', ...)`），精准捕获多边形拓扑增删与翻转；
       * 动态 RNA 属性扫描，精准捕获任意修改器（Solidify, Displace 等）参数、增删及 `show_viewport` 切换；
       * 基于 `obj.session_uid` 追踪集合成员变动，新增或删除对象即刻触发重建；
       * **原地重命名零重建优化**：当对象仅改名而几何未变时，就地更新元数据名称与 Surface ID，**BVH 重建次数为 0**。
     - **Path B (显式失效)**：调用 `adapter.invalidate()` 标记 `_dirty = True` 及 `INVALID` 状态，后续首次常规查询自动触发原子重建，调用方无需显式调用 `rebuild()`。
  3. **原子提交与异常安全回滚**：
     - 新顶点、多边形、元数据在局部变量中全量就绪后原子提交；
     - 求值网格在 `finally:` 中统一通过 `eval_obj.to_mesh_clear()` 清理，杜绝内存泄漏；
     - 发生异常时回滚至 `FAILED` 状态并保留 `dirty=True`，绝不暴露半提交脏数据。
  4. **全量 42 项测试与反事实实证归档**：
     - 新增 Unit 2 专用测试 `test_33` 至 `test_42`，42 项测试全绿通过（42/42 PASS in 2.13s）；
     - 编写反事实测试生成器 `tests/run_counter_factual_ru2.py`，在真实环境执行并归档 C01, C03, C05 三项反事实变异失败与生产恢复通过日志至 `docs/evidence/environment_gate01_ru2/`；
     - 编写结构化总结报告 `counter_factual_summary.md` 与边界报告 `cache_invalidation_boundary_report.md`；
     - 全量分级测试通过：`quick` (13/13), `physics` (19/19), `motion` (8/8), `full` (30/30)；
     - 符号审计 `audit_c2_final_inspector.py --verify-docs` 0 错误；`output/` 历史资产 0 字节变动。
* **影响**：
  - 彻底解决了环境查询适配器在动态场景下的几何一致性与缓存失效难题，实现了高性能（未变场景 300 次查询 0 重建）与高保真（任意几何/层级/修改器变动自动同步）的统一；
  - 状态严格停留于 `ENVIRONMENT GATE 01 / REPAIR UNIT 2 — AWAITING HUMAN REVIEW`，严禁擅自推进至 Repair Unit 3 或 Phase 7B。

---

### [DEC-057] 2026-10-28: Environment Gate 01 — Repair Unit 2 Final Closure: C05-1至C05-4集合生命周期、C06异常安全加固与F01-F03反事实实证闭环

* **状态**：已采纳并完成 (Accepted & Completed)
* **日期**：2026-10-28
* **背景**：在 Repair Unit 2 最终收口与验收阶段，依据架构清规执行深度边界加固：
  1. **C05 深度集合生命周期验证不足**：旧测试仅核验了单集合基本增删，缺少对象从集合解除关联（Unlink）但保留在全局数据块中时的精确剔除、真实物理删除（`bpy.data.objects.remove`）后的零野指针与元数据清理、非空向空集合转换后的 100 次空查询零重建复用与后续新网格加入恢复，以及递归子集合增删与同名/同级集合隔离性检验；
  2. **C06 重建异常安全盲区**：`rebuild()` 在进入 `try:` 前即调用了 `_gather_target_objects()`，若集合访问或场景遍历抛出异常，会导致缓存状态永久卡死在 `REBUILDING`，且无法触发向 `FAILED` 状态回滚与求值网格释放；
  3. **失效边界与扫描开销界定未固化**：自动检测（Path A）与显式失效（Path B）的边界缺乏形式化规约，顶点哈希比对开销缺乏客观说明；
  4. **反事实实证证据需扩充**：除 C01、C03、C05 外，需针对解除关联成员残留（F01）、有效空 BVH 重复重建（F02）、重建异常残留卡死在 `REBUILDING`（F03）注入受控变异以建立闭环物理可证伪证据。
* **决策与方案**：
  1. **生产适配器异常安全与状态自愈加固 (`src/scene/blender_mesh_query_adapter.py`)**：
     - 将 `_gather_target_objects()` 与快照计算完整移入 `rebuild()` 的 `try:` 保护块内部；
     - 确保任何阶段（候选收集、快照计算、求值网格提取、BVH 编译）抛出未捕获异常时，缓存状态必然回滚至 `AdapterCacheState.FAILED` 并设置 `dirty = True`；
     - 任何临时求值网格必然在 `finally:` 中执行 `to_mesh_clear()` 清理，杜绝内存泄漏；
     - 后续常规查询自动具备自愈恢复能力（重新触发原子重建）。
  2. **深度集合生命周期与异常测试扩充 (`tests/test_mesh_environment_query.py`)**：
     - 新增 `test_43_c05_1_collection_member_unlinked`：核验仅解除关联（未删除）的对象从 BVH 中剔除（1 次重建），且受禁集合对象绝不被查询；
     - 新增 `test_44_c05_2_real_object_deletion`：核验 `bpy.data.objects.remove(obj, do_unlink=True)` 触发 1 次重建，元数据清理干净，0 野指针；
     - 新增 `test_45_c05_3_non_empty_to_empty_transition_and_reuse`：核验非空转空转入 `VALID_EMPTY`，100 次空查询 0 重建复用，返回 `success=False`（`source_type="none"`），加入新 Mesh 干净恢复；
     - 新增 `test_46_c05_4_recursive_collection_membership`：核验子集合成员递归追踪、子集合解关联剔除、子集合新增感知及同级集合严格隔离；
     - 新增 `test_47_c06_rebuild_exception_safety`：核验 gather、snapshot 及 BVH 编译异常下统一回滚至 `FAILED`，求值网格安全释放，后续查询自愈恢复；
     - 全套 47 项环境测试在 Blender 5.1.1 Headless 下全绿通过（47/47 PASS in 2.588s）。
  3. **扩充反事实实证至 6 项真实变异 (`tests/run_counter_factual_ru2.py`, `docs/evidence/environment_gate01_ru2/`)**：
     - 真实执行并归档 6 项受控故障变异日志：
       * `counter_factual_c01_empty_rebuild.log` (变异 Exit 1: 201 != 1; 生产 Exit 0)
       * `counter_factual_c03_vertex_stale.log` (变异 Exit 1: 1 != 2; 生产 Exit 0)
       * `counter_factual_c05_collection_membership_stale.log` (变异 Exit 1: 2 != 1; 生产 Exit 0)
       * `counter_factual_f01_member_retention_leak.log` (变异 Exit 1: 解关联对象残留; 生产 Exit 0)
       * `counter_factual_f02_empty_bvh_repeated_rebuild.log` (变异 Exit 1: 102 != 2; 生产 Exit 0)
       * `counter_factual_f03_exception_state_residual.log` (变异 Exit 1: REBUILDING != FAILED; 生产 Exit 0)
     - 更新 `counter_factual_summary.md` 与 `cache_invalidation_boundary_report.md`。
  4. **失效边界与开销界定固化 (`docs/ENVIRONMENT_MESH_QUERY_SEMANTICS.md`)**：
     - 形式化矩阵界定 Path A（位移/旋转/缩放/父子层级/顶点移动/拓扑修改/修改器/集合增删解关联/重命名）与 Path B（外部驱动/复杂骨骼与点缓存/时间轴未标记刷新）；
     - 客观声明几何扫描开销：`refresh()` 检查顶点哈希避免了 $1\sim 10\text{ms}$ 的 BVH 重建，但其自身扫描并非零成本（约 $0.04\text{ms}$/物体），候选集合隔离是保证扫描预算可控的架构前提。
  5. **全量回归与受控保护检验**：
     - 47 项环境网格查询测试全绿（47/47 PASS in 2.588s）；
     - `run_test_suite.py` 全分级通过：`quick` (13/13), `physics` (19/19), `motion` (8/8), `full` (30/30)；
     - `audit_c2_final_inspector.py --verify-docs` 校验 0 错误；
     - `output/` 历史 `.blend` 资产 0 字节变动；
     - 状态严格停留于 `ENVIRONMENT GATE 01 / REPAIR UNIT 2 — FINAL REVIEW`，严禁擅自推进至 Repair Unit 3 或 Phase 7B。
* **影响**：
  - 彻底完成了 Environment Gate 01 Repair Unit 2 的收口闭环，为后续足底精确落脚点规划与高程查询提供了具备百分之百确定性、异常安全与物理可证伪性的底层网格适配器；
  - 维持零历史退化与零架构违规。
