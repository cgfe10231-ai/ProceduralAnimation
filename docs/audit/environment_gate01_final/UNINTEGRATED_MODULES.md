# UNINTEGRATED_MODULES: 未完全纳入人体闭环体系模块深度审计

**审计基准 Commit**：`7a3e244825cd87bf3d787c530318055dc94a3e1f`  
**审计时间**：2026-10-29  
**所属门禁**：Environment Gate 01 — Final Architecture Audit (Audit D)  

---

## 1. 四级接入状态分类定义

严禁将“算法能够运行”直接混淆为“算法已进入人体闭环控制”。全模块审计严格使用以下 4 级准绳：

* **级别 ① [算法存在]**：源码中存在该类或函数，数据结构完整。
* **级别 ② [算法可运行]**：具备单元测试或独立运行脚本，算法能够正确执行且数学验证通过。
* **级别 ③ [算法接入人体]**：生产 19 骨骼运行入口实际调用了该模块，骨骼姿态或遥测中实际包含其输出数据。
* **级别 ④ [算法进入反馈闭环]**：该模块的实时计算结果能够反向改变下一时刻人体的实际运动控制、脚步规划或关节力矩。

---

## 2. 核心模块接入级别审计矩阵

| 模块文件 | 核心算法与已有能力 | 实际接入级别 | 缺失的调用链 (Missing Caller) | 缺失的输入 (Missing Input) | 缺失的消费方 (Missing Consumer) | 状态语义冲突与架构阻碍 | 推荐复用方式与后续阶段 |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| [`src/motion/forward_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/forward_dynamics.py) | 二阶辛中点/RK4 刚体状态前向积分器、非各向同性惯性张量与李代数四元数姿态积分 | **级别 ② [算法可运行]** | 生产主链 `KinematicBridgeExecutor` 与 `MotionPlanner` 完全未调用该积分器 | 缺失 19 骨骼全身等效驱动力与关节广义力向量 $\boldsymbol{\tau}$ | 积分产生的 `ForwardDynamicsState` 仅被测试断言读取，**未写入 19 骨骼 Root** | **状态语义冲突**：当前生产主链 Root 位姿完全由运动学样条决定，若直接并联动力学积分会导致双重写竞争 | **Phase 7C**：作为全身质心前向预测器接入，驱动 Root 动力学运动。 |
| [`src/motion/closed_loop_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/closed_loop_dynamics.py) | 质心轨迹跟踪、PD 姿态误差反馈控制律、陀螺耦合修正与外力扰动恢复 | **级别 ② [算法可运行]** | 生产动作 `TerrainWalkAction` 完全未实例化该闭环控制器 | 缺失 19 骨骼角色真实的实时传感器状态（如实际角速度差、质心误差反馈） | 计算出的修正加速度与控制力矩未施加给人体系，仅驱动代理物体 | **架构脱节**：当前闭环控制基于质心代理单刚体，缺乏向 19 骨骼各关节力矩的逆动力学映射 (ID) | **Phase 7C / 6H**：扩展为全身多刚体平衡控制器与倒立摆 (LIPM) 协调器。 |
| [`src/motion/contact_force_solver.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_force_solver.py) | 多接触力二次规划 (QP) 求解器、摩擦锥线性化约束求解、法向单侧接触约束 | **级别 ② [算法可运行]** | 生产主链中无任何调用者；仅在 `tests/verify_task6gd_contact_force_solver.py` 中运行 | 缺失 19 骨骼角色每帧期望的全身净外力与力矩目标 $(\mathbf{F}_{\text{des}}, \boldsymbol{\tau}_{\text{des}})$ | 求解出的各接触点三维接触力向量 $\mathbf{f}_i$ 未被任何骨骼或控制器消费 | **物理开环**：角色行走时足底与地面**零接触力交互**，既不检测反作用力也不依据摩擦锥限制剪切力 | **Phase 7C**：在桥接层接入，根据期望加速度求解双足地面反作用力 (GRF)。 |
| [`src/motion/contact_dynamics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_dynamics.py) | 多接触冲量动量传递模型、接触点恢复系数与滑动库仑阻尼计算 | **级别 ② [算法可运行]** | 生产主链无调用；仅在 `verify_task6gd_contact_dynamics.py` 中测试 | 缺失真实脚底着地撞击瞬间的动量交换信号 | 冲量与接触力学更新仅写入 `ContactDynamicState` 测试结构体 | **刚性假设冲突**：当前主链将支撑脚视为理想刚性几何粘附（极小滑移即视为违规），无冲量物理吸收机制 | **Phase 7C**：用于着地缓冲阶段的冲击动量吸收计算。 |
| [`src/motion/rigid_link.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/rigid_link.py) | 19 骨骼刚体质量分布模型、各段局部质心世界变换与 $70.0\text{kg}$ 全身质心 (CoM) 计算 | **级别 ③ [算法接入人体]** | 已接入 `WholeBodyController.execute_frame()` | 输入骨骼当前姿态骨矩阵序列 | 输出 `com_world` 仅存入 `WholeBodyControlResult` 供遥测展示，**零下游消费方** | **无闭环**：质心位置未与零力矩点 (ZMP) 或足底支撑多边形进行相对位移比对，无法纠偏平衡 | **Phase 7C / 6H**：作为主动质心平衡补偿器 (CoM Balancer) 的基准输入。 |
| [`src/motion/body_inertia.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_inertia.py) | 19 骨骼局部转动惯量张量、平行轴定理世界惯性张量与全身角动量积分 | **级别 ③ [算法接入人体]** | 已接入 `KinematicBridgeExecutor.execute_frame()` | 输入 19 骨骼当前角速度与世界变换矩阵 | 惯性张量与角动量仅存入 `motion_state.params["inertia_state"]`，**无任何动力学消费方** | **纯遥测**：不参与姿态动量平衡计算，不计算质心角动量变化率 $\dot{\mathbf{H}}_{\text{com}}$ | **Phase 7C**：用于全身角动量变化率跟踪与防止行走过程中的上身扭动倾覆。 |
| [`src/motion/body_kinematics.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/body_kinematics.py) | 数值差分运动学微分器、骨骼段线速度与角速度滤波计算 | **级别 ③ [算法接入人体]** | 已接入 `KinematicBridgeExecutor.execute_frame()` | 输入骨骼历史帧位姿队列 | 输出速度仅赋予 `KinematicVelocityState` 记入遥测 | **纯观察器**：速度仅用于计算动能和动量，不参与任何速度伺服回路 | **Phase 7C**：作为状态反馈闭环的实际速度传感器输入。 |
| [`src/motion/contact_model.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/motion/contact_model.py) | 多肢接触几何约束计算、脚底与地面气隙/滑移/穿透检测、支撑状态分类 (`SupportType`) | **级别 ③ [算法接入人体]** | 已接入 `KinematicBridgeExecutor.execute_frame()` | 输入骨骼姿态与网格环境查询结果 | 评价结果输出给 `contact_geom_errors` 与 `unmet_constraints`，存入遥测 JSON | **单向监测**：当足底发生滑移或不可支撑时，仅抛出违规记录，**不反馈修正下一步落点** | **Phase 7C / 7E**：将接触违规反馈给规划器作为自适应调整或重规划触发条件。 |
| [`src/rig/arm_ik.py`](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py) | 双臂 2 骨骼 IK 约束配置、手部三维世界朝向控制、肘部极向目标与可达性约束 | **级别 ③ [算法接入人体]** | 约束已装配入 `CharacterArmature`，受 `WholeBodyController` 调度 | 手部目标世界坐标 `hand_L.target_world_xyz` | 在当前地形通行主链中权重设为 0 (`weight=0.0`)，手臂实际运行纯 FK 摆动 | **功能被抑制**：上肢 IK 能力完备，但被下肢行走的对侧简谐摆动 FK 逻辑完全覆盖 | **Phase 7B 核心接入点**：激活双臂 IK，引入上肢独立任务空间控制与末端目标。 |

---

## 3. 核心未接入总结与解耦边界

1. **动力学闭环的真实边界**：
   - 仓库内实现的动力学模块（`forward_dynamics.py`、`closed_loop_dynamics.py`、`contact_force_solver.py`、`contact_dynamics.py`）**已经达到了极高的算法与数值质量**（二次规划、二阶辛积分、陀螺修正均通过严格数学验证）；
   - 但它们此前仅仅作为一个**单刚体质心质点代理系统**在独立测试和基准场景中运行，**从未与 19 骨骼人形骨架建立受力、力矩与加速度通道**；
   - 当前 19 骨骼人体是 **100% 运动学驱动（Kinematic Driven）** 的几何自适应系统，依靠高精度的 BVH 射线求交与平滑样条在复杂 3D 地形上实现了无穿透、无滑移的通行。
2. **Phase 7B 与动力学合流的依赖解耦**：
   - **Phase 7B（上肢独立运动学控制）完全不依赖动力学合流**：`src/rig/arm_ik.py` 与 `WholeBodyController.set_hand_ik_target` 已经具备完整的世界空间手部目标控制能力，只需在上层解除与 `TerrainWalkAction` 纯摆臂的强耦合，即可独立实施 7B；
   - **动力学合流属于 Phase 7C 的明确职责**：在 Phase 7C 之前，严禁擅自强行将动力学前向积分器接入 19 骨骼骨架，以免破坏成熟稳定的运动学主链。
