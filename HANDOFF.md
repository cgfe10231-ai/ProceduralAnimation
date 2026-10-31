# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标与当前状态

* **当前任务**：ProceduralAnimation — PKG-5 / 09 Lower-Limb IK: 三维 Ground × Reach 约束求解器最终工程收口 (Task ID: PKG5-09A-COMPLETE-CONSTRAINT-CLOSURE)。
* **当前状态**：`PKG-5 / 09-A — AWAITING INDEPENDENT REVIEW`（严格停止等待外部审查，严禁自行推进 Task 09-B，严禁修改 `foot_contact.py`，严禁进入 Phase 7B）。
* **核心成果**：09-A 底层 `set_foot_ik_target` 三维几何解析极值求解器已完整实现并验证。四种约束模式、全几何空间分类（CASE-1至5）、两阶段原子性提交、真实性遥测、20项专项测试（含Categories A-T及独立Oracle）、历史4C/4D与四级回归（Full 39/39）100%通过。

### 核心基准成果 (PKG5-09A-COMPLETE-CONSTRAINT-CLOSURE)
1. **算法接口完备实现 (`src/rig/ik.py:322–640` `set_foot_ik_target`)**：
   - **四模式完备解耦**：Mode A(原样)、Mode B(仅Ground)、Mode C(仅Reach)、Mode D(联合极值投影)；
   - **全几何分类完备性**：CASE-1 空可行域抛出 `GROUND_REACH_INFEASIBLE`；CASE-2 顶部切点；CASE-3/4 地面截断球体候选极值搜索；CASE-5 极低地面退化（杜绝零半径伪装交圆）；
   - **两阶段写入原子性**：Phase A 校验全部输入、有限性与约束求解；Phase B 仅在通过后写入控制器并触发 prebend hint，前置失败绝不污染骨架；
   - **真实性遥测与求解校验**：内部求解失败抛出 `GROUND_REACH_CONSTRAINT_UNSATISFIED`；真实返回 `requested_world`, `applied_world`, `clamped_reach`, `clamped_ground`, `ground_z`, `constraints_satisfied`, `ground_clearance_m`, `hip_to_target_dist_m`；
2. **专项测试 (`tests/test_leg_ik_ground_height_contract.py`)**：
   - 完整保留 TEST-1 至 TEST-18；
   - 新增 TEST-19（完整几何分类法 Categories A 至 T，20个边界全量检查 8 大字段）；
   - 新增 TEST-20（独立数值网格与边界采样 Oracle 参数化与伪随机交叉验证，5mm网格公差内 100% 吻合）；
   - 专项 20 项 100% 通过（2.12s）；
3. **全量分级自动化回归全部 100% 通过**：
   - `legacy_leg_ik` (verify_task4c_ik): **PASS (1.58s)**；
   - `legacy_foot_contact` (verify_task4d_foot_contact): **PASS (1.62s)**；
   - `leg_ik_worldspace_init_reset` (PKG-5/WS-01): **PASS (0.53s)**；
   - `physics_rigid_link_com`: **PASS (1.75s)**；
   - `physics_body_inertia`: **PASS (11.45s)**；
   - `physics_contact_model`: **PASS (22.58s)**；
   - `physics_bridge_contract`: **PASS (22.36s)**；
   - Quick: **19/19 PASSED (48.71s)**；
   - Physics: **24/24 PASSED (94.97s)**；
   - Motion: **12/12 PASSED (48.36s)**；
   - Full: **39/39 PASSED (146.79s)**；
   - 架构文档与符号物理校验 `tests/audit_c2_final_inspector.py --verify-docs`: **PASS (0 errors, 0 phantom symbols)**。

---

## 2. 已完成历史里程碑
* **PKG-5 / 09 Lower-Limb IK (Task A)**: Foot IK Ground-Height Contract & CharacterRoot Decoupling (FIND-R3-02 归档) (`FIXED / VERIFIED`)。
* **PKG-5 / 08 Rig (Regression Closure)**: 历史测试语义修复与 CoM 刚体平移全量回归收口归档 (`FIXED / VERIFIED`)。
* **PKG-5 / WS-01**: Leg IK Controller World-Space Initialization & Reset Invariant (FIND-R3-01 部分子问题归档) (`FIXED / VERIFIED`)。
* **Final Closure (Contact Model 07)**: CONTACT-MODEL-07-FINAL-CLOSURE 接触记录唯一性与几何容差失效验收收口归档 (`FIXED / VERIFIED`)。
* **Joint Repair (Contact Model)**: FIND-R2-05 ContactModel 几何有效性与支撑拓扑解耦修复归档 (`FIXED / VERIFIED`)。
* **Joint Repair Acceptance Closure (Terrain Planning)**: ISSUE-A 最大步长单脚 3D 位移硬约束与 ISSUE-B 复合门禁验收收口归档 (`FIXED / VERIFIED`)。
* **Joint Repair (Terrain Planning)**: FIND-R2-06 / FIND-R2-07 / FIND-T01-07 / FIND-T01-08 地形规划方向、接缝与时间基准联合修复归档 (`FIXED / VERIFIED`)。
* **Joint Repair Closure (Env & Scene)**: JOINT-REPAIR-ENV-SCENE-CLOSE 动作环境所有权冲突防御、0.12m连续性门禁及真实无mock场景集成验证归档 (`FIXED / VERIFIED`)。
* **Joint Repair (Env & Scene)**: FIND-R4-02 / FIND-T01-06 / FIND-R4-01 环境查询合同、动作环境所有权与场景交付门禁联合修复归档 (`FIXED / VERIFIED`)。
* **Production Interface Repair 04 Closure**: 严重程度判定优先级修复与物理失败防降级加固归档 (`FIXED / VERIFIED`)。
* **Production Interface Repair 04**: FIND-R2-04 / FIND-T01-03 统一动作结果与 MotionPlanner 失败处理合同归档 (`FIXED / VERIFIED`)。
* **Production Interface Repair 03 Closure**: 斜坡脚踝摆动参数审核、回归测试边界恢复与根因闭环归档 (`AUDITED / PENDING REVIEW`)。
* **Production Interface Repair 03**: FIND-R2-03 / FIND-T01-01 地形行走执行失败阻断传播与死分支清理归档 (`FIXED / VERIFIED`)。
* **Production Interface Repair 02**: FIND-R2-02 / FIND-T01-02 接触状态所有权与 Bridge 物理接触保留修复归档 (`FIXED / VERIFIED`)。
* **Production Interface Repair 01**: FIND-R2-01 手部接触生命周期枚举修复归档 (`FIXED / VERIFIED`)。
* **Production Interface Audit R4**: 环境查询、网格适配器与场景集成生产接口审计及全仓库修复分组归档 (`REPAIR PENDING`)。
* **Production Interface Audit R3-CLOSE**: 全生命周期合同闭环与副作用纠错归档 (`EVIDENCE VERIFIED`)。
* **Production Interface Audit R3**: 底层绑定、足部接触与 IK 执行合同只读审查归档 (`docs/audit/production_interface/R3_RIG_IK.md`)。
* **Production Interface Audit R2-CLOSE**: 证据校准、签名行号核实与正式闭环归档 (`EVIDENCE VERIFIED`)。
* **Production Interface Audit (R1, R2)**: 生产接口逐方法联合审计与缺陷登记归档。

---

## 3. 下一步建议与禁止项
1. **当前禁止**：
   - **严禁自行进入 09 Lower IK Task B**；
   - **严禁提前进入 Phase 7B（双向环境动力学）**；
   - **严禁修改 `src/rig/foot_contact.py`、`src/rig/arm_ik.py`、`src/rig/builder.py`**；
   - **严禁修改 WholeBodyController、KinematicBridge、contact_model.py、terrain_walk.py**；
   - **严禁修改 set_foot_ik_target() 或 get_leg_ik_state()**；
   - **严禁修改生产代码以适配测试**。
2. **下一步建议**：
   - 等待外部独立审查确认 PKG-5 / 08 Rig 最终回归收口成果；
   - 待审查批准后，按既定排期推进下一组任务（09 Lower IK / WS-02）。
