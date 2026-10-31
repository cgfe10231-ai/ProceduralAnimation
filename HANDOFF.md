# HANDOFF: 会话交接说明书

> 本文件供新会话启动或与其他 AI 协作时无缝交接，保持简短清晰，勿填充冗长日志。

---

## 1. 当前目标与当前状态

* **当前任务**：ProceduralAnimation — PKG-5 / WS-01 Leg IK Controller World-Space Initialization Invariant (FIND-R3-01 部分子问题)。
* **当前状态**：`PKG-5 / WS-01 — AWAITING INDEPENDENT REVIEW`（严格停止等待外部独立审查，禁止自行开始 WS-02，禁止修改 `foot_contact.py`，禁止进入 Phase 7B）。
* **任务性质**：生产接口合同修复，关闭底层 Rig/IK 控制器初始化与重置时的无父级世界空间不变量子问题（FIND-R3-01 局部）。

### 本任务核心核准成果 (PKG-5 / WS-01)
1. **生产代码修复 (`src/rig/ik.py`)**：
   - `_get_or_create_empty()`：当调用方传入 `parent=None` 时，若获取到的已有对象仍挂在某个父级下，显式执行解绑（`obj.parent = None` 并重置 `obj.matrix_parent_inverse = Matrix.Identity(4)`）；
   - `setup_leg_ik()`：创建或获取 `FootIK.L`, `FootIK.R`, `KneePole.L`, `KneePole.R` 时显式传入 `parent=None`；显式校验若已有对象存在父级则解绑；通过 `root_mat = root_obj.matrix_world.copy()` 将角色当前根节点空间的中立站立坐标投影至世界坐标（`ik_obj.location = root_mat @ ik_local`, `ik_obj.rotation_euler = root_rot`），重置 `is_locked = False`；
   - `reset_leg_ik()`：移除 `ik_obj.parent = root_obj` 与 `pole_obj.parent = root_obj` 强行挂载逻辑；若控制器存在残留父级则解绑清理；重新计算根节点世界变换并将控制器准确放回当前根节点对应的世界空间中立站立位置与朝向，重置 `is_locked = False`；
2. **独立单元测试全绿 (`tests/test_leg_ik_worldspace_init_reset.py`)**：
   - 覆盖 TEST-1 至 TEST-6（初始无父级、非原点根位移、非零偏航旋转、已有父级回收、位移后重置与零累积漂移、后续根运动不拖拽控制器），6 项全绿通过（6/6 PASS in 0.663s）；
3. **分层回归与旧测试假设排查**：
   - `tests/test_runner_unit.py`: **11/11 PASS (1.107s)**；
   - `tests/audit_c2_final_inspector.py --verify-docs`: **PASS (0 errors, 0 phantom symbols)**；
   - `.\run_tests.ps1 -tier motion`: **12/12 PASS (58.9s, 100%)**；
   - `tests/verify_task4c_ik.py` & `tests/verify_task4d_foot_contact.py`: **PASS**；
   - **历史回归测试失败排查与证据留存 (Legacy Parenting Assumption Regression)**:
     - `tests/verify_task6fb_rigid_link.py` Test 8: 历史测试在未失活 IK 或未调用重置的情况下，直接在 Pose 模式下平移 `root_obj.location`，依赖“FootIK 会随 root_obj 刚性平移”的旧假设。在 WS-01 确立 `parent is None` 后，FootIK 保持世界原地，IK 解算器将腿部拉伸导致世界 CoM 偏差 0.146m；
     - 级联子进程测试：`tests/verify_task6gb_body_inertia.py` Test 13、`tests/verify_task6gc_contact_model.py` Test 15、`tests/verify_task6gc_r3b1_bridge.py` Test 14 因调用 `verify_task6fb_rigid_link.py` 同步呈现该项失败；各自本身功能测试全部 PASS；
     - 依据任务清规，严格保留真实失败证据，不擅自修改断言阈值，不回退无父级合同，登记并等待独立审查。

---

## 2. 已完成历史里程碑
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
   - **严禁进入 WS-02**；
   - **严禁提前进入 Phase 7B（双向环境动力学）**；
   - **严禁自行修改 `src/rig/foot_contact.py`、`src/rig/arm_ik.py`、`src/rig/builder.py`**；
   - **严禁修改 WholeBodyController、KinematicBridge、contact_model.py、terrain_walk.py**；
   - **严禁修改 set_foot_ik_target() 或 get_leg_ik_state()**；
   - **严禁修改断言阈值或通过回退父级制造全绿**。
2. **下一步建议**：
   - 等待外部独立审查确认 PKG-5 / WS-01 成果；
   - 待审查批准后，按既定排期推进 WS-02（清理 `foot_contact.py:152` `unlock_foot_contact` 的 `reparent_to_root` 逻辑与 `set_foot_ik_target` 姿态反解防护）。
