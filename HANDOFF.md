# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标与当前状态

* **当前任务**：ProceduralAnimation — PKG-5 / 08 Rig 最终回归收口 (Task ID: PKG5-RIG08-COM-REGRESSION-CLOSURE)。
* **当前状态**：`PKG-5 / 08 Rig — AWAITING FINAL INDEPENDENT REVIEW`（严格停止等待外部独立审查，禁止自行进入 09 Lower IK，禁止修改 `foot_contact.py`，禁止进入 Phase 7B）。
* **任务性质**：历史测试语义修复，恢复 CoM 刚体变换测试及其级联回归，保证 08 原有世界空间不变量继续成立。

### 本任务核心核准成果 (PKG5-RIG08-COM-REGRESSION-CLOSURE)
1. **历史测试语义修复 (`tests/verify_task6fb_rigid_link.py` Test 8B)**：
   - 彻底解决因世界空间 FootIK 保持原地导致根节点平移时局部姿态变动的语义前提问题；
   - 严格实施原子 5 步方案：Step A 记录 Root 变换与影响局部姿态的约束；Step B 临时将相关约束 influence 置为 0.0，确立固定的局部骨架姿态实验条件；Step C 重新采样局部固定状态下的真实基准 CoM，记录 7 关键骨骼局部矩阵；Step D 执行原位移 `(2.5, 5.0, 0.3)`，断言世界质心误差（实测 $0.0000007907\text{m} \le 10^{-4}\text{m}$）、Armature 空间质心误差（实测 $0.0000000000\text{m} \le 10^{-6}\text{m}$）及关键骨骼局部矩阵漂移（实测 $0.0000000000\text{m} \le 10^{-6}\text{m}$）；Step E 在 `try/finally` 中精准恢复 Root 变换、约束 influences 及 pose；
   - 生产代码 0 修改、测试断言阈值 0 放宽、FootIK 世界空间无父级不变量（`parent is None`）100% 保持；
2. **级联回归测试全绿通过**：
   - `tests/verify_task6fb_rigid_link.py`: **ALL PASSED (Test 1 至 8B 全绿)**；
   - `tests/verify_task6gb_body_inertia.py`: **13/13 PASSED**；
   - `tests/verify_task6gc_contact_model.py`: **17/17 PASSED**；
   - `tests/verify_task6gc_r3b1_bridge.py`: **14/14 PASSED**；
   - `tests/test_leg_ik_worldspace_init_reset.py`: **6/6 PASSED**（四个控制器恒定 `parent is None`）；
3. **全套分层自动化回归全量 100% 通过**：
   - Quick: **19/19 PASSED (50.69s)**；
   - Physics: **23/23 PASSED (92.02s)**；
   - Motion: **12/12 PASSED (53.22s)**；
   - Full: **38/38 PASSED (159.0s)**；
   - 架构文档门禁 `tests/audit_c2_final_inspector.py --verify-docs`: **PASS (0 errors, 0 phantom symbols)**。

---

## 2. 已完成历史里程碑
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
   - **严禁自行进入 09 Lower IK**；
   - **严禁提前进入 Phase 7B（双向环境动力学）**；
   - **严禁修改 `src/rig/foot_contact.py`、`src/rig/arm_ik.py`、`src/rig/builder.py`**；
   - **严禁修改 WholeBodyController、KinematicBridge、contact_model.py、terrain_walk.py**；
   - **严禁修改 set_foot_ik_target() 或 get_leg_ik_state()**；
   - **严禁修改生产代码以适配测试**。
2. **下一步建议**：
   - 等待外部独立审查确认 PKG-5 / 08 Rig 最终回归收口成果；
   - 待审查批准后，按既定排期推进下一组任务（09 Lower IK / WS-02）。
