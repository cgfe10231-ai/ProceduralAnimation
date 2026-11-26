# TASK: fix6-bug2 — TYPE A EXCEPTION WINDOWS & PENDING CONVERGENCE REPORT

* **任务编号 / 归属**：`fix6-bug2`（所属主任务 `fix6`，对应冻结问题 `R1-TAIL-03`，任务性质 `TEST ONLY`）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **测试基准 Commit SHA**：`e1b5796d3abc38057720c126c0ba849db18098dc`
* **Blender 完整版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **治理规范核对**：`origin/master:WORKFLOW_GOVERNANCE.md`（`APPROVED`）；已只读核对 `WORKFLOW_GOVERNANCE.md`、`AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`、[ARCHITECTURE_CHANGE_GATE.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md)、[PROJECT_STATE.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/PROJECT_STATE.md)、[ARCHITECTURE_SYNC.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE_SYNC.md)、[CORE_REPAIR_LEDGER.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task10b15/CORE_REPAIR_LEDGER.md) 与 [arm_ik.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)
* **完整原始日志**：[fix6-bug2_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug2_test_execution.log)

---

## 1. 执行摘要与退出码

* **执行命令**：`"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr <IN_MEMORY_EXPR>`（完整脚本与原文输出见 [fix6-bug2_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug2_test_execution.log#L20-L362)）
* **测试类**：`TestFix6Bug2TypeAExceptionWindows`
* **真实退出码**：`0`（`Ran 2 tests in 0.330s`，`OK`）
* **测试结论**：**专项 PASS**（测试 A **PASS**，测试 B **PASS**）

---

## 2. 测试 A：物理删除之前发生异常 (`during_cleanup_datablock_after_auth_before_remove`)

* **测试方法**：`test_A_fault_after_auth_before_remove_enters_pending_and_retries_cleanly`
* **结果**：**PASS**（退出码 `0`）
* **事务与资源标识**：`tx_id = 'be7eb9fa'`，真实 Type A Mesh `'Fix6Bug2_A_TypeA.001'`（指针 `1853253727624`）

| 阶段 | 验证要点 | 实测观测结果 | 判定 |
| :--- | :--- | :--- | :---: |
| **故障触发窗口** | 1. 故障钩子触发一次 | `hook_calls == [('during_cleanup_datablock_after_auth_before_remove', 1853253727624, 0, 'COMMITTED')]` | **PASS** |
| | 2. Type A 授权校验已完成 | 凭据与授权均已存在于 `tx._type_a_datablock_receipts` / `datablock_authorizations`（`TYPE_A_TX_CREATED`, `TX_CREATE_RECEIPT`），12 项前置校验通过后才触发该钩子 | **PASS** |
| | 3. 注入前 Mesh `users` 为 0 | 钩子内部与异常退出后均实测 `type_a_mesh.users == 0`（`'HandIK.L'` 旧对象已清理 `obj_cleaned == True`） | **PASS** |
| | 4. 事务业务逻辑已提交 | 钩子内读取 `tx_arg.state == COMMITTED` | **PASS** |
| | 5. 物理删除尚未发生 | `uncleaned_stashed_objects` 保留 1 条且 `data_cleaned == False`，`len(datablock_cleanup_outcomes) == 0` | **PASS** |
| | 6. 原始 Mesh 指针仍在 `bpy.data.meshes` | `1853253727624` 与 `'Fix6Bug2_A_TypeA.001'` 仍在 `bpy.data.meshes` | **PASS** |
| | 7–8. `CLEANUP_PENDING` 与 Pending Registry | `tx.state == CLEANUP_PENDING`；`tx` 在 `_PENDING_ARM_RIG_CLEANUPS['be7eb9fa']` 与 `get_pending_arm_rig_cleanup_ids()` 中保留为同一对象 | **PASS** |
| | 9. 异常传播不吞没 | 外层 `RuntimeError` 包含 `INJECTED_TEST_A_BEFORE_REMOVE` 且 `__cause__` 保留该异常 | **PASS** |
| | 10. Pending Gate 阻断同 Armature 新写入 | `query_admission_gate_status(arm)` 报告 `cleanup_pending_blocked=True, pending_cleanup_transaction_ids=['be7eb9fa']`；调用 `set_arm_ik_influence` 抛出 `Arm IK write blocked: unresolved cleanup for the same Armature; pending transactions=be7eb9fa` | **PASS** |
| **重试收口 (`retry_pending_arm_rig_cleanup('be7eb9fa')`)** | 物理删除与记录唯一性 | 指针 `1853253727624` 与名称 `'Fix6Bug2_A_TypeA.001'` 从 `bpy.data.meshes` 消失；`datablock_cleanup_outcomes` 存在唯一记录 `{'action': 'DELETED', 'status': 'PHYSICALLY_DELETED', 'reason': 'AUTHORIZED_CLEANUP', 'resource_kind': 'Mesh', 'resource_name': 'Fix6Bug2_A_TypeA.001', 'resource_pointer': 1853253727624, 'tx_id': 'be7eb9fa'}` | **PASS** |
| | Coordinator 状态与 Gate 解除 | `tx.state == COMMITTED`、`cleanup_error is None`、`_PENDING_ARM_RIG_CLEANUPS` 与 `uncleaned_stashed_objects` 清空；`query_admission_gate_status(arm)['cleanup_pending_blocked'] == False`；后续 `set_arm_ik_influence(..., 0.25)` 正常写入 | **PASS** |
| | 无授权外部 Mesh 保留 | `Fix6Bug2_A_ExtUnauth`（`1853254500616`, `users=0`）与 `Fix6Bug2_A_TypeA`（`1853255407112`, `users=0`）均完整保留 | **PASS** |

---

## 3. 测试 B：物理删除之后、结果确认之前发生异常 (`during_cleanup_datablock_after_remove_before_verify`)

* **测试方法**：`test_B_fault_after_remove_before_verify_enters_pending_and_converges_without_redelete`
* **结果**：**PASS**（退出码 `0`）
* **事务与资源标识**：`tx_id = '2ea61395'`，真实 Type A Mesh `'Fix6Bug2_B_TypeA.001'`（已删原指针 `1851539884936`）

| 阶段 | 验证要点 | 实测观测结果 | 判定 |
| :--- | :--- | :--- | :---: |
| **故障触发窗口** | 1. 故障钩子触发一次 | `hook_calls == [('during_cleanup_datablock_after_remove_before_verify', 1851539884936, 'COMMITTED')]` | **PASS** |
| | 2–3. 删除已执行、原指针已消失 | 钩子内与事务抛出后均验证 `1851539884936` 与 `'Fix6Bug2_B_TypeA.001'` 已不在 `bpy.data.meshes` | **PASS** |
| | 4. 清理结果尚未确认 | `stashed_rec['data_cleaned'] == False`，`data_cleanup_status != 'PHYSICALLY_DELETED'`，`len(datablock_cleanup_outcomes) == 0` | **PASS** |
| | 5–6. `CLEANUP_PENDING` 与 Pending Registry | `tx.state == CLEANUP_PENDING`；`_PENDING_ARM_RIG_CLEANUPS['2ea61395'] is tx` | **PASS** |
| | 7–8. 异常传播且不虚报完整成功 | 抛出含 `INJECTED_TEST_B_AFTER_REMOVE_BEFORE_VERIFY` 的 `RuntimeError`（保留 `__cause__`）；Pending Gate 阻断同 Armature 新写入 `set_arm_ik_influence` | **PASS** |
| **重试收口 (`retry_pending_arm_rig_cleanup('2ea61395')`)** | 不重复删除、不按名寻找替代 | 重试前将预分配不同指针无授权诱饵（`1851539666312`, `users=0`）改名为精确同名的 `'Fix6Bug2_B_TypeA.001'`；重试时监测 `during_cleanup_datablock_after_auth_before_remove` 触发 `0` 次，诱饵 `1851539666312` 完整保留 | **PASS** |
| | 按真实缺失状态收敛至 `COMMITTED` | `stashed_rec['data_cleaned'] == True` 且 `stashed_rec['data_cleanup_status'] == 'DATA_ALREADY_ABSENT'`；未产生虚假重复 `PHYSICALLY_DELETED` 记录；`tx.state == COMMITTED`、`cleanup_error is None` | **PASS** |
| | Pending Registry 与 Gate 解除 & 外部保留 | `_PENDING_ARM_RIG_CLEANUPS` 清空；`cleanup_pending_blocked == False`；后续 `set_arm_ik_influence(..., 0.25)` 正常通过；外部 `Fix6Bug2_B_ExtUnauth`（`1851539887624`）及同名诱饵 `Fix6Bug2_B_TypeA.001`（`1851539666312`）与 `Fix6Bug2_B_TypeA` 均保留 | **PASS** |

---

## 4. 状态流转与门禁总览

* **资源物理删除状态**：
  * 测试 A：故障窗口未删除（`users == 0` 在库） → 重试后物理删除（`PHYSICALLY_DELETED` 唯一记录）。
  * 测试 B：故障窗口已物理删除（未确认） → 重试不重复删除，按 `DATA_ALREADY_ABSENT` 真实状态完成记录收敛。
* **Coordinator 状态流转**：测试 A 与测试 B 均严格遵循 `ACTIVE -> COMMITTED -> CLEANUP_PENDING -> COMMITTED`；异常均由 Coordinator 捕获并经 `_coordinator_apply_cleanup_result` 登记门禁，重试均通过公开入口 `retry_pending_arm_rig_cleanup(tx_id)` 驱动收敛。
* **Pending Gate 状态**：两项测试在故障发生后均触发 `cleanup_pending_blocked == True` 阻断同 Armature 新写入，重试成功后均自动注销 `_PENDING_ARM_RIG_CLEANUPS` 并恢复正常准入。

---

## 5. 未执行的测试范围与 Git 修改边界

* **NOT EXECUTED（按任务冻结禁止执行范围）**：
  * 四级全量回归（`quick` / `physics` / `motion` / `full`）：**`NOT EXECUTED`**
  * 历史失败项 `TEST-64` 重跑 / 修改：**`NOT EXECUTED`**（历史证据保留为 `FAIL — LEGACY FIXTURE CONFLICT`，未改为 PASS）
  * `fix6-bug3` 及其他后续任务：**`NOT EXECUTED`**
* **Git 修改范围与源码零改动证明**：
  * `src/`、[test_task10b_transaction_atomicity.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py)、`fix6-bug1` 及历史 `fix-4`/`fix-5` 证据、既有 8 项预存未跟踪文件均**零修改、零清理**；
  * `git diff --exit-code` 与 `git diff --cached --exit-code` 测试前后均为 `0`；
  * 本轮仅新增 [fix6-bug2_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug2_test_execution.log) 与 [fix6-bug2_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug2_test_report.md)。
