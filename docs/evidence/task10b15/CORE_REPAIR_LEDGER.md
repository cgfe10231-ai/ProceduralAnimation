# 10-B-15 收敛修复主账｜由 ChatGPT 独立维护

基线：`0bd2097a58064c956b33631afe305fb9ffe3e914`（`audit/task-10-b-9`）。
此账与执行 Agent 自动生成的 `deferred_observations.md` 分离，禁止执行 Agent 改写编号、定义、所属模块、严重程度或关闭状态。
**21 为遗留/测试记录数量，不是 21 个独立代码 Bug。**

## 当前证据状态（2026-11-19；不改写以下21项冻结原定义）

- 本账中的 **21项** 为历史遗留、测试缺口及合同失败观察的冻结编号，**不是21个独立代码BUG**；原编号、严重程度与原始观察正文不可修改。
- fix-1～7 后 `arm_ik.py` 与 `whole_body_controller.py` 已存在针对历史遗留的生产实现；代码存在并不自动宣告每个旧观察已消失。
- `TEST-31..253` 跨批次去重有效 `223/223 PASS`；BUG11 `8/8 PASS`；BUG12 `4/4 PASS`；FULL `42/42` 自动化通过且9项视觉待验收。
- 本账 `CONTRACT10-02/03/04/06` 行写的是**历史实测FAIL**，不是新HEAD的实时FAIL；当前代码对应 `CONTRACT10-01..06` 六项专项尚无完整新运行结论，不得改成已验证PASS或继续声称当前实测FAIL。
- BUG12 的4项测试证明所构造真实资源场景的隔离与清理，不能单独证明所有自然生成路径的端到端覆盖。
- 当前主状态由 `PROJECT_STATE.md`、`ARCHITECTURE_SYNC.md`、`OPEN_FINDINGS.md` 共同维护；冻结清单与历史故障窗口继续保留供后续验收映射。
- 证据：`docs/evidence/fix-7/remaining_regression/round2/fix7_report.md`。

## 双轴排序法

- **影响范围 S**：5 = 全身/WBC/Bridge 单帧；4 = 全部 Arm IK 事务与准入；3 = 通用资源所有权与回滚；2 = 单一资源类型；1 = 仅测试或证据。
- **严重程度 P**：P0 = 已复现全身半提交或可能造成未授权破坏性写入的底层授权漏洞；P1 = 严重回滚/授权/错误传播缺口；P2 = 故障窗口不完整或缺失正向/异常测试；P3 = 证据偏差。
- **排序优先级**：先 S 由大至小，同一 S 内先 P0 到 P3；实现前按依赖确认是否需要限制写入和做保守准入。
- **历史测试时点**：当时未经 Blender 复现的代码风险不得写成已发生破坏；`CONTRACT10-02/03/04/06` 的原始失败日志属于旧代码版本，不能据此宣称当前版本仍然 FAIL。

## 核心与模块修复顺序

| 优先 | 逻辑模块 / 核心函数 | S | P | 归属问题 | 阶段验收合同 |
|---|---|---:|---|---|---|
| 01 | **全局主心骨：`WholeBodyController.execute_frame()`**；边界 `KinematicBridgeExecutor.execute_frame()` | 5 | **P0** | CONTRACT10-02/03/04/06 | 失败帧无 Root/Pelvis/Spine/Leg/Arm 部分提交；只允许真实失败或完整成功；异常必须传播。 |
| 02 | **事务主心骨：`_arm_rig_transaction()` + `_coordinator_apply_cleanup_result()` + Pending Gate** | 4 | **P0/P1** | R5-TAIL-01/02/03/04；历史 F-03 | 所有受管写入先验权；状态/门禁唯一 Coordinator 决策；验证异常必然 fail-closed；Grant 全生命周期可信。 |
| 03 | **资源身份/授权底座：Registry/Ownership + Layer 3 Guard** | 3 | **P0/P1** | R1-TAIL-01；R2-TAIL-01；R4-TAIL-01；R4-TAIL-03 | 名称、字符串、伪登记不是所有权；Object/Collection/DataBlock 准入及销毁都绑定可信活体身份与来源。 |
| 04 | **统一回滚与关系状态：`_rollback_arm_rig_state()` + 七状态日志** | 3 | **P1** | R3-TAIL-02/03；R4-TAIL-02 | 部分写入不得宣称 NO_EFFECT；回滚不能绕过资源授权，也不得因身份不明继续改写；错误不可吞没。 |
| 05 | **资源生命周期故障窗口：Collection 与 Constraint** | 2 | **P1/P2** | R2-TAIL-02；R3-TAIL-01 | 创建 → 立即登记 → 授权链接/配置；失败能以同一身份受控清理，清理失败显式报错。 |
| 06 | **DataBlock 删除正向/异常路径与 F-06 真实资源交叉隔离** | 2 | **P2** | R1-TAIL-02/03；历史 F-06 | 合法 Type A 真删除、非法/异常拒绝、两 Armature 实际待清理资源互不干扰。 |
| 07 | **联合验证与文档可信性** | 1 | **P2/P3** | 合同 01–12；独立测试清单；执行 Agent 的遗留定义漂移 | 原始测试及新增专项不删不改、不 xfail；失败保持失败；修复完成后统一运行 Blender 全套与 CONTRACT-10。 |

## 21 项冻结主定义（不可改写）

| 原编号 | 主归属模块 | 类型 | 内容 |
|---|---|---|---|
| R1-TAIL-01 | 03 | 所有权/授权边界 | Type B 删除授权真实性证明不足。 |
| R1-TAIL-02 | 06 | 测试缺口 | Type A 合法授权删除路径未验证。 |
| R1-TAIL-03 | 06 | 故障注入缺口 | 授权删除异常分支测试不足。 |
| R2-TAIL-01 | 03 | 所有权边界 | 回滚删除未复核事务入口所有权基线。 |
| R2-TAIL-02 | 05 | 异常恢复 | Collection 登记失败后的清理异常被吞没。 |
| R3-TAIL-01 | 05 | 资源创建/异常恢复 | Constraint 创建登记异常与补救清理不完整。 |
| R3-TAIL-02 | 04 | 关系状态 | Target/Subtarget 部分写入可能错误归类 NO_EFFECT。 |
| R3-TAIL-03 | 04 | 恢复授权 | 无事务回滚的 Constraint Target 身份证明不完整。 |
| R4-TAIL-01 | 03 | 授权边界 | Object Parent 授权仍允许名称推断所有权。 |
| R4-TAIL-02 | 04 | 回滚/层级边界 | 回滚层仍有直接关系写入和异常吞没。 |
| R4-TAIL-03 | 03 | 关系所有权 | Collection Parent/Child 授权缺少完整关系所有权证明。 |
| R5-TAIL-01 | 02 | Coordinator 错误传播 | FAILED 隔离核验吞没异常。 |
| R5-TAIL-02 | 02 | Coordinator 顺序 | Pending Retry 先执行清理，后完整验权。 |
| R5-TAIL-03 | 02 | 结果验证 | CleanupResult 非法 Outcome 未严格拒绝。 |
| R5-TAIL-04 | 02 | 门禁恢复 | 初次 Cleanup 的 Coordinator 结果校验异常缺少 Pending 兜底。 |
| HIST-F03 | 02 | Grant 生命周期 | Coordinator Grant 签发、消费、作废和过期流程待全面验证。 |
| HIST-F06 | 06 | 跨会话实资源验证 | CLEANUP_PENDING 下双臂与跨 Armature 门禁测试已过，真实待清理资源交叉覆盖不足。 |
| CONTRACT10-02 | 01 | **实测 FAIL** | Pending 拒绝后 WBC Root 已写入未回滚。 |
| CONTRACT10-03 | 01 | **实测 FAIL** | FAILED 隔离拒绝后 WBC Root 已写入未回滚。 |
| CONTRACT10-04 | 01 | **实测 FAIL** | Arm IK 局部回滚后 WBC Root/其他先序写入未恢复。 |
| CONTRACT10-06 | 01 | **实测 FAIL** | 左手独立提交、右手失败，整帧半提交。 |

## 历史时点记录：当时已编写的生产修复（后续已有更多实现）

- `10B_CORE_WBC_01_apply.py`：仅精确修改 `src/motion/whole_body_controller.py`，增加构造和帧执行的 **Armature admission fail-fast gate**。
- 修复目标：在 Leg IK/Root/Pelvis/FK/Hand IK 任意场景写入前，发现当前 Armature 的 `CLEANUP_PENDING` / FAILED / identity-invalid 并抛出明确异常。
- **尚未解决**：运行期的 WBC 单帧回滚与双臂共同提交（CONTRACT10-04/06）；这些留待主心骨下一代码单元。
- **测试状态**：按用户要求，生产运行测试延期到所有逻辑模块修复完成后统一执行。本补丁不宣称 PASS。

## 历史阶段执行边界（仅留档，不构成当前授权）

1. Agent 不得设计、改写或补全生产代码；只允许执行 ChatGPT 写好的逐字补丁，核对目标 Diff 并完成 Git 提交及推送。
2. 原文件必须与固定基线一致；不一致立即停止，不能自动合并、找替代锚点或修改补丁。
3. 禁止自主修改任何测试断言、跳过测试、修改测试运行器、伪造 PASS。
4. **历史阶段限定**：当时集中修复完成前不进行 Blender 全量回归；当前 fix-7 FULL 自动化回归已有42/42证据，不得再把该历史暂缓指令当作当前禁跑令。
5. 功能行为稳定、历史遗留清零、联合测试通过之后，**由 ChatGPT** 决定六层的物理文件归属，Agent 只执行搬运和最终回归。
