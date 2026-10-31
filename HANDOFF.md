# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标与当前状态

* **当前任务**：ProceduralAnimation — PKG-5 / 09 Lower-Limb IK: 足部 IK 地面高度合同与根节点解耦 (Task ID: PKG5-09-IK-GROUND-A)。
* **当前状态**：`PKG-5 / 09 Lower IK / Task A — AWAITING FINAL INDEPENDENT REVIEW`（严格停止等待外部独立审查，禁止自行进入 Task B，禁止修改 `foot_contact.py`，禁止进入 Phase 7B）。
* **任务性质**：底层 Rig 生产接口缺陷修复，解耦足部地面防穿透限制与角色根节点高程的错误绑定。

### 本任务核心核准成果 (PKG5-09-IK-GROUND-A)
1. **生产接口合同修复 (`src/rig/ik.py:322–441` `set_foot_ik_target`)**：
   - 追加可选参数 `ground_z: Optional[float] = None`，保持历史调用者完全向后兼容；
   - 显式传入 `ground_z` 时使用其值计算 `min_ankle_z = effective_ground_z + ANKLE_REST_Z`；未传入时回退到历史平地基准 `0.0m`；
   - 彻底移除对 `root_obj.matrix_world.translation.z` 的采样，解耦足部高度限制与 CharacterRoot 坐标的绑定；
   - 保留 `clamp_ground=False` 旁路能力，以及与可达性约束（`MAX_LEG_REACH` / `MIN_LEG_REACH`）的真实几何交互；
   - 返回状态字典中如实返回 `state["ground_z"] = effective_ground_z`；
2. **针对性单元测试 (`tests/test_leg_ik_ground_height_contract.py`)**：
   - 覆盖 TEST-1（平地兼容）、TEST-2（根节点高度解耦）、TEST-3（凹陷负高程）、TEST-4（凸起平台）、TEST-5（clamp_ground=False旁路）、TEST-6（根节点偏航/旋转独立性）、TEST-7（双重边界几何交互与控制器坐标对齐）、TEST-8（非法输入防御）全部 8 项通过（0.69s）；
3. **全套分层自动化回归全量 100% 通过**：
   - Quick: **19/19 PASSED (53.94s)**；
   - Physics: **24/24 PASSED (94.26s)**；
   - Motion: **12/12 PASSED (51.32s)**；
   - Full: **39/39 PASSED (148.27s)**；
   - 架构文档门禁 `tests/audit_c2_final_inspector.py --verify-docs`: **PASS (0 errors, 0 phantom symbols)**；
4. **调用链状态澄清**：
   - 底层 Rig 接口 `set_foot_ik_target` 现已完全支持显式外部 `ground_z` 并与 Root 解耦；
   - 现有上层调用者（如 `WholeBodyController.execute_frame()`）目前仍通过遗留接口 `ground_z=None` 调用，安全平滑回退至平地 Z=0.0m 基准；
   - 上层 WBC/Action 地形射线查询结果透传至 `set_foot_ik_target(..., ground_z=...)` 将在后续上层集成任务中完成，本次仅修复底层 Rig 接口合同。

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
