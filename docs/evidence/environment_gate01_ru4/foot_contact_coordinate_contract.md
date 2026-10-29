# ProceduralAnimation — Environment Gate 01 / Repair Unit 4
## Foot Contact Coordinate Contract & 3D Geometry Specification
### 足部接触坐标语义、空间划分与几何变换合同

> **文档性质**：Unit 4 架构准入前提文档 (Prerequisite Specification)  
> **涉及核心文件**：
> - [`src/motion/kinematic_bridge.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py)
> - [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py)
> - [`src/scene/environment_query.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/scene/environment_query.py)

---

## 1. 核心定义：三类足部坐标的严格区分

在全程序化 3D 动力学与运动学管线中，足部相关的空间坐标长期存在三类不同物理含义的概念。在复杂地形（坡道、台阶、高架桥顶台）下，必须严格区分这三个坐标，**严禁混用**：

```
                    [人体骨骼 Armature]
                            │
               Shin Bone (shin.L / shin.R)
                            │
                      (Ankle Joint)  ◄─── 坐标 A: 规划脚踝 IK 目标 (PlannedFootTarget.world_xyz)
                            │              = (st_x, st_y, z_surf + ANKLE_REST_Z)
              Foot Bone (foot.L / foot.R)
              [带有 pitch 旋转 θ]
                            │
               (Foot Bottom / Sole Anchor) ◄─── 坐标 C: 实际足部接触锚点 (Actual Foot Contact Anchor)
                            │              = M_bone_world @ anchor_local
                      [间隙 Gap / 接触]
                            │
            (Real Mesh Surface Geometry) ◄─── 坐标 B: 真实地面接触点 (SurfaceQueryResult.contact_point_world)
                                           = (x_surf, y_surf, z_surf), 法线 n_surf
```

### 坐标 A：规划脚踝 IK 目标 (Planned Ankle IK Target)
* **载体对象**：`PlannedFootTarget.world_xyz`
* **所处空间**：物理世界坐标空间 (World Space, +Z Up, Ground Z=0.0m)
* **解剖学物理实体**：
  - 踝关节旋转中心（Talocrural joint center）；
  - `foot.L` / `foot.R` 骨骼的 Head（起始关节端点）；
  - `shin.L` / `shin.R` 骨骼的 Tail（终止关节端点）；
  - 脚部 IK 约束目标物体（`IK_Foot_L` / `IK_Foot_R`）在世界空间中的放置目标。
* **高程构造规律**：
  在静止站立或步态支撑期（Stance），规划器查询地面表面高度 $z_{\text{surf}}$ 后，按足部静止高度偏置加上脚踝离地高程：
  $$\mathbf{p}_{\text{ankle\_tgt}} = \begin{pmatrix} x_{\text{step}} \\ y_{\text{step}} \\ z_{\text{surf}} + \text{ANKLE\_REST\_Z} \end{pmatrix}$$
  其中 $\text{ANKLE\_REST\_Z} = 0.070\text{ m}$（70 mm）。
* **重要结论**：**坐标 A 是脚踝关节目标，不是足底鞋底接触点。将其直接传入接触求解器作为接触目标属于严重的物理语义错误。**

---

### 坐标 B：真实地面/网格接触点 (Real Ground/Mesh Contact Point)
* **载体对象**：`SurfaceQueryResult.contact_point_world`
* **数据来源**：调用 `environment.query_ground_support_at(x, y)` 经由 BVH 射线与 evaluated Blender mesh 求交得出。
* **所处空间**：物理世界坐标空间 (World Space)
* **几何物理实体**：
  - 环境网格在 $(x, y)$ 处的真实上表面接触点；
  - 平地段为 $(x, y, 0.0)$；
  - 10°~15° 坡道段为 $(x, y, z_{\text{mesh}})$；
  - 高架桥顶台段为 $(x, y, 1.3397)$（精确网格高程）；
  - 伴随属性：
    * `surface_id`: 网格表面唯一标识（例如 `"mesh:Surface_Ramp_TopPlatform:3"`）；
    * `surface_normal_world`: 该三角面真实向外法向量 $\mathbf{n}_{\text{surf}} = (n_x, n_y, n_z)$；
    * `allows_regular_support`: 表面是否适格作为人行支撑面。
* **重要结论**：**坐标 B 是环境网格能够提供法向支撑力的物理表面接触点，是 ContactModel / ContactRecord 的权威基准目标 (target_world)。**

---

### 坐标 C：实际足部接触锚点 (Actual Foot Contact Anchor)
* **载体对象**：`ContactRecord.body_local_anchor` 经当前姿态变换后的世界坐标，或 `actual_positions`。
* **所处空间**：世界空间 (World Space)，由骨骼局部空间变换而来。
* **解剖学物理实体**：
  - 人体脚底板鞋底（Sole）的物理接触参考点。
  - 在静止平地（$\theta=0$）上，脚踝位于 $Z=0.07\text{ m}$，足底位于 $Z=0.00\text{ m}$，足底位于脚踝下方 $0.07\text{ m}$ 处。
* **求值数学公式**：
  给定骨骼的当前世界位姿矩阵 $\mathbf{M}_{\text{bone\_world}} = \mathbf{M}_{\text{armature\_world}} \cdot \mathbf{M}_{\text{pose\_bone}}$，局部锚点 $\mathbf{a}_{\text{local}}$：
  $$\mathbf{p}_{\text{sole\_actual}} = \mathbf{M}_{\text{bone\_world}} \cdot \begin{pmatrix} \mathbf{a}_{\text{local}} \\ 1 \end{pmatrix}$$
* **重要结论**：**实际接触锚点随骨骼的世界位移与 3D 旋转实时演化，必须包含脚踝 pitch 旋转的刚体变换。**

---

## 2. 坐标变换、足部旋转与局部锚点审查

### 2.1 审查现行 `ankle.z - ANKLE_REST_Z` 标量减法的几何缺陷

在历史代码 [`src/motion/kinematic_bridge.py:483`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/kinematic_bridge.py#L483) 中：
```python
ankle_world = arm.matrix_world @ p_shin.tail
actual_positions[f"foot_{side}"] = (ankle_world.x, ankle_world.y, ankle_world.z - ANKLE_REST_Z)
```
该公式直接将世界空间 $Z$ 坐标减去常数标量 $0.07\text{ m}$，**完全忽略了脚部的旋转矩阵**：

1. **水平地面 ($\theta = 0^\circ$)**：
   脚踝在 $Z=0.07$，足底在 $Z=0.00$，标量减法 $0.07 - 0.07 = 0.00$，与实际吻合。
2. **倾斜坡道 ($\theta \neq 0^\circ$)**：
   脚部绕脚踝产生 pitch 旋转 $\theta$。从脚踝指向正下方足底的向量在脚部参考系中为 $(0, 0, -h)$。
   经 pitch 旋转后，该向量在世界空间中的投影为：
   $$\Delta \mathbf{p}_{\text{world}} = \begin{pmatrix} 0 \\ h \sin\theta \\ -h \cos\theta \end{pmatrix}$$
   垂直高度落差变为 $-h \cos\theta$，同时伴随前向位移 $h \sin\theta$。
   - 在 $10^\circ$ 坡面上：$-0.07 \cos(10^\circ) = -0.0689\text{ m}$（相差 $1.1\text{ mm}$）；
   - 在 $15^\circ$ 坡面上：$-0.07 \cos(15^\circ) = -0.0676\text{ m}$（相差 $2.4\text{ mm}$）；
   - 在 $20^\circ$ 坡面上：$-0.07 \cos(20^\circ) = -0.0658\text{ m}$（相差 $4.2\text{ mm}$）。
3. 若直接粗暴地用标量减去 $0.07$，就会在倾斜坡道上人为制造 $2\sim 5\text{ mm}$ 的伪几何穿透或虚假间隙。
4. **正确做法**：足底接触点必须通过骨骼矩阵 $\mathbf{M}_{\text{bone\_world}}$ 乘以足底骨骼局部锚点计算，让旋转矩阵自然参与变换。

---

### 2.2 审查 `DEFAULT_LIMB_LOCAL_ANCHORS` 的历史倾角偏差

在 [`src/motion/contact_model.py:78-87`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py#L78-L87) 中：
```python
DEFAULT_LIMB_LOCAL_ANCHORS: Dict[str, Tuple[float, float, float]] = {
    "foot_L": (0.0, 0.077, -0.070),
    "foot_R": (0.0, 0.077, -0.070),
```
注释中声明该锚点旨在放置于足底鞋底中心。然而核查 [`src/rig/builder.py:45`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py#L45)：
```python
("foot.L", "shin.L", (-0.11, 0.0, 0.07), (-0.11, 0.15, 0.035), True, (0.0, 0.0, 1.0))
```
- `foot.L` / `foot.R` EditBone 的 Head 位于 $Z = 0.07$，Tail 位于 $Y = 0.15, Z = 0.035$；
- 骨骼自身的局部 Y 轴沿 $(0, 0.15, -0.035)$ 倾斜下倾，倾角为 $\alpha = \arctan(-0.035 / 0.15) \approx -13.134^\circ$；
- 历史局部向量 `(0.0, 0.077, -0.070)` 是按照骨骼未倾斜的假设手写的。将其直接代入骨骼矩阵后，旋转耦合导致计算出的点在静止平地上为 $Z = -0.0157\text{ m}$（陷入地下 15.7 mm）；
- **正确局部锚点推导**：
  在静止站立下，若要求锚点世界坐标精确对应脚踝投影足底点 $(0, 0, -0.070)$：
  $$\mathbf{a}_{\text{bone\_local}} = \mathbf{R}_{\text{bone}}^{-1} \begin{pmatrix} 0.0 \\ 0.0 \\ -0.070 \end{pmatrix} = \begin{pmatrix} 0.0 \\ 0.015906 \\ -0.068168 \end{pmatrix}$$
  若要求对应鞋底几何中心 $(0, 0.040, -0.070)$：
  $$\mathbf{a}_{\text{sole\_center\_local}} = \mathbf{R}_{\text{bone}}^{-1} \begin{pmatrix} 0.0 \\ 0.040 \\ -0.070 \end{pmatrix} = \begin{pmatrix} 0.0 \\ 0.054859 \\ -0.059081 \end{pmatrix}$$
  经 Blender 5.1 实际矩阵验算：
  - 代入 `(0.0, 0.015906, -0.068168)` 时，静止平地足底求值结果为 $(x_a, y_a, 0.0000\text{ m})$，高度差严格为 $0.000000\text{ m}$！

---

## 3. 错误产生的具体接口与传播链

整个接触链产生高程归零与虚假间隙的传播链如下：

```
[Phase 1: MotionPlanner / TerrainWalkAction]
  └─ planned_pose.foot_L.world_xyz = (st_x, st_y, z_mesh + 0.07)  <-- 正确脚踝 IK 目标
  └─ planned_pose.foot_L.surface_id = "Surface_Ramp_TopPlatform"  <-- 正确网格表面 ID
  └─ planned_pose.foot_L.normal_world = (0, 0, 1)                <-- 正确网格表面法线
           │
           ▼
[Phase 2: KinematicBridgeExecutor.execute_frame()]
  ├─ 错误 1 (第 388 行): surfaces 变量默认硬编码单一平地 EnvironmentalSurface(Z=0, Normal=(0,0,1))
  │                      未将 self.environment 的真实查询结果接入！
  │
  ├─ 错误 2 (第 404 行): active_limb_targets["foot_L"]["target_world"] = (x, y, 0.0) !
  │                      粗暴地将高程硬编码截断为 0.0，使高架顶台（Z=1.3397）被重置为 0.0！
  │
  └─ 错误 3 (第 483 行): actual_positions["foot_L"] = (x, y, ankle_z - 0.07)
                         用标量减法代替骨骼局部锚点旋转变换！
           │
           ▼
[Phase 3: evaluate_limb_contacts_from_armature()]
  └─ ContactRecord.world_position 被赋予 target_world (Z=0.0)
           │
           ▼
[Phase 4: check_geometric_compliance()]
  └─ disp = actual_positions - ContactRecord.world_position
     当角色在高架桥 (Z=1.3397) 时：
     actual_positions.z = 1.3397
     world_position.z = 0.0
     disp.z = 1.3397 m  ==>  gap = 1339.7 mm >> max_gap (15.0 mm)
     ==> 错误判定为 EXCESSIVE_GAP 违规！
```

---

## 4. Unit 4 修复合同规范 (Contract Specification)

针对上述诊断，Unit 4 的修复合同规范确立如下：

### 规则 1：接触目标世界高程必须来自真实 Mesh 支撑查询
在 `KinematicBridgeExecutor.execute_frame()` 中：
当 `ft.is_locked` 为 True（或 `ft.contact_intent` 为 True）时：
1. 调用 `res = self.environment.query_ground_support_at(ft.world_xyz[0], ft.world_xyz[1])`；
2. 若 `res.success` 为 True：
   - `target_world` 必须设置为真实网格接触点 `res.contact_point_world`（高程等于真实 Mesh 表面）；
   - `normal_world` 必须设置为真实网格表面法线 `res.surface_normal_world`；
   - `surface_id` 必须设置为真实网格标识 `res.surface_id`；
   - 构造局部 `EnvironmentalSurface` 放入 `surfaces` 列表；
3. 若 `res.success` 为 False（例如下方悬空或无支撑 Mesh）：
   - 严禁静默回退到 $Z=0$ 虚假平地；
   - 标记无接触支撑，生命周期置为非建立状态（`RELEASED` 或 `CANDIDATE`），真实反映悬空状态。

### 规则 2：实际足底接触点必须通过骨骼姿态矩阵与修正锚点求值
在 `actual_positions` 与 `active_limb_targets` 中：
1. 采用与骨骼倾角解耦匹配的校准局部锚点：
   `FOOT_LOCAL_SOLE_ANCHOR = (0.0, 0.015906, -0.068168)`（脚踝正下方足底接触参考点）；
2. 实际足底位置通过骨骼世界矩阵计算：
   $$\mathbf{p}_{\text{actual}} = \mathbf{M}_{\text{armature\_world}} \cdot \mathbf{M}_{\text{pose\_bone}} \cdot \mathbf{a}_{\text{anchor}}$$
3. 确保在平地、上坡、顶台及下坡全路段中，足部旋转 $\theta$ 自然参与变换，几何间隙严格保持在 $\le 5\text{ mm}$ 真实物理范围内。

### 规则 3：保持向下兼容与零动画退化
1. 保持现存解析环境 `EnvironmentQuery` 测试 100% 兼容通过；
2. 保持 700 帧人体动画规划（`TerrainWalkAction`）0 字节修改；
3. 保持已验收的 S1 Root 连续性与 S2 着地连续性 0 退化。
