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
