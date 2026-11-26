# TASK: fix6-bug3 — DUAL ARMATURE REAL RESOURCE & CLEANUP PENDING ISOLATION REPORT

* **任务编号 / 归属**：`fix6-bug3`（主任务 `Task 10-B / fix6`，对应冻结问题 `HIST-F06`，任务性质 `TEST ONLY`）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **固定基线 HEAD**：`32c70f946f2e3024786d0889f2a66b80c7375633`
* **Blender 完整版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **前置治理核验**：已只读核对 `WORKFLOW_GOVERNANCE.md`、`origin/master:WORKFLOW_GOVERNANCE.md`（`APPROVED`）、`AGENTS.md`、`GEMINI.md`、`.agents/rules/project_rules.md`、`PROJECT_SPEC.md`、`ARCHITECTURE.md`、`ARCHITECTURE_SYNC.md`、`DECISIONS.md`、[PROJECT_STATE.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/PROJECT_STATE.md)、`HANDOFF.md`、`AI_SYNC.md`、[ARCHITECTURE_CHANGE_GATE.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/ARCHITECTURE_CHANGE_GATE.md)、[CORE_REPAIR_LEDGER.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task10b15/CORE_REPAIR_LEDGER.md)、[test_task10b_transaction_atomicity.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py)、[builder.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/builder.py) 与 [arm_ik.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)。
* **完整原始日志**：[fix6-bug3_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug3_test_execution.log)

---

## 1. 总结判定：PARTIAL（遵循失败熔断规则，不关闭 `HIST-F06`，不提交 Git）

* **执行命令**：`"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr <IN_MEMORY_EXPR>`（完整脚本与原文输出见 [fix6-bug3_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug3_test_execution.log#L21-L514)）
* **测试类**：`TestFix6Bug3DualArmatureIsolation`
* **真实退出码**：`0`（`Ran 5 tests in 0.483s`，`OK`）
* **测试单项结果**：
  * **测试 A**（`test_A_armature_a_holds_real_pending_type_a_resource`）：**PASS**（退出码 `0`）
  * **测试 B**（`test_B_while_a_pending_b_runs_with_real_type_a_mesh_and_a_retries_isolated`）：**PASS**（退出码 `0`）
  * **测试 C1a**（`test_C1a_concurrent_pending_retry_a_then_b`）：**PASS (PARTIAL DUAL PENDING)**（退出码 `0`）
  * **测试 C1b**（`test_C1b_concurrent_pending_retry_b_first_while_a_still_pending`）：**PASS (PARTIAL DUAL PENDING REVERSE ORDER)**（退出码 `0`）
  * **测试 C2**（`test_C2_dual_armature_setup_arm_ik_global_controller_name_conflict_probe`）：**PASS (CONFLICT PROBE DOCUMENTED)**（退出码 `0`）
* **HIST-F06 整体覆盖结论**：**`PARTIAL`（部分覆盖 / 未形成双 Armature 各自同时持有 `uncleaned_stashed_objects` 待清理资源的交叉证明）**。
  * 已实际证明：
    1. Armature A 可通过 `_authorized_create_type_a_mesh()` + `register_created_controller()` + `setup_arm_ik()` 持有真实 Type A `uncleaned_stashed_objects` 并进入 `CLEANUP_PENDING`；
    2. A 处于真实 Pending 期间，同进程内另一独立 19 骨 Armature B（独立 `Armature` 对象、独立 `registry_session_id`、独立 `tx_id`）可正常进入并提交 `_arm_rig_transaction(arm_b)`、创建并持有属于 B 的真实合法 Type A Mesh（绑定 B 的 `registry_session_id` 与 `tx_id`），不会误借用 A 的 Pending Gate、不会清除 A 的 Pending 状态或待清理资源，且即使给 B 的 Mesh 起同名基名（`Fix6Bug3_SharedName` -> `Fix6Bug3_SharedName.001`），随后对 A 执行 `retry_pending_arm_rig_cleanup(tx_a.tx_id)` 仅物理删除 A 的指针目标而完整保留 B 的存活 Mesh 及其授权/回执；
    3. 当 A 与 B **同时处于 `CLEANUP_PENDING`**（A 持有真实待清理 `uncleaned_stashed_objects` 项，B 持有真实创建的合法 Type A Mesh 且通过 `during_commit_cleanup` 故障注入进入 `CLEANUP_PENDING`）时，无论是**先重试 A 再重试 B**（测试 C1a）还是**先重试 B 再重试 A**（测试 C1b），双方的 `_PENDING_ARM_RIG_CLEANUPS` 条目、Pending Gate 阻断状态、Type A 回执以及各自 Mesh 均严格隔离、独立收敛，不发生交叉删除或交叉释放。
  * **明确未覆盖缺口（触发 `PARTIAL` 熔断）**：
    * 依据真实生产源码 [arm_ik.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py) 核验，全模块中仅 `setup_arm_ik()` 路径（`_get_or_create_empty` 第 8792 行及约束替换第 8995/9014/9066/9085 行）会向 `tx.uncleaned_stashed_objects` / `tx.uncleaned_stashed_constraints` 写入待清理资源；且 `setup_arm_ik()` 在第 8898 行调用 `_require_existing_arm_ik_controller_ownership(arm, scope='setup_arm_ik')`（第 2551–2598 行），按全局对象名遍历 `ARM_IK_TARGET_NAMES` 与 `ARM_POLE_TARGET_NAMES`（`'HandIK.L'`、`'HandIK.R'`、`'ElbowPole.L'`、`'ElbowPole.R'`）。
    * 当 Armature A 已创建并持有这 4 个全局命名 Controller 对象（含 A 处于 `CLEANUP_PENDING`）时，对 Armature B 合法调用 `setup_arm_ik(arm_b, initial_influence=0.5)` 必然在进入 `_arm_rig_transaction` 前触发 `ExternalControllerNameConflictError`（测试 C2 实测复现）。
    * 因此，**在不违反 Section 8 禁令（禁止篡改全局常量/绕过所有权检查/删除或改名 A 的 Controller/人工向队列塞入伪造记录）的前提下，Armature B 无法通过合法生产接口同时在自己的 `tx_b.uncleaned_stashed_objects` 中持有待清理资源**（实测 C1a/C1b 中 `len(tx_b.uncleaned_stashed_objects) == 0`，B 的资源是 `COMMITTED` 前创建于 `_type_a_datablock_receipts` 的存活 Type A Mesh，而非 B 的 `uncleaned_stashed_objects` 待清理资源）。
    * 依据 Section 9 与 Section 12 规则：**本轮必须标定为 `PARTIAL`，不得宣布 `HIST-F06` 全部关闭，且不得创建虚假成功提交或推送 Git。**

---

## 2. 历史测试核验与本轮验证区分（Section 3）

| 维度 | 历史测试 `TEST-246` ~ `TEST-253`（[test_task10b_transaction_atomicity.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py#L8944-L9360)） | 本轮 `fix6-bug3`（[fix6-bug3_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug3_test_execution.log)） |
| :--- | :--- | :--- |
| **验证性质** | **已有状态隔离验证**：主要验证两 Armature 的 session/tx 状态机与准入/Pending Gate 隔离 | **真实资源与 Controller 冲突边界验证** |
| **Armature B 夹具** | `TEST-249`~`253` 使用无骨骼的空 `Armature` 对象 `arm_b` 与空 `_arm_rig_transaction(arm)`/`during_commit_cleanup` 注入（`TEST-251` 第 9206 行另含手工构造字典） | 复制 19 骨 `arm_a.data` 建立真实 19 骨 `CharacterArmatureB`（偏移位置 `(2.0, 0.0, 0.0)`，避免覆盖 `CharacterArmature`） |
| **真实 DataBlock / 待清理对象** | 未用 `_authorized_create_type_a_mesh()` + `setup_arm_ik()` 验证双 Armature 下真实 `uncleaned_stashed_objects` | **A 侧**使用真实 `_authorized_create_type_a_mesh()` + `register_created_controller()` + `setup_arm_ik()` 真实压入 `uncleaned_stashed_objects`；**B 侧**使用真实 `_authorized_create_type_a_mesh()` 生成受控 DataBlock，并以实测探针验证 `setup_arm_ik(arm_b)` 的全局命名冲突边界 |

---

## 3. 分场景实测证据记录（Section 9 逐项核对）

### 3.1 测试 A：Armature A 持有真实待清理 Type A 资源（`test_A_armature_a_holds_real_pending_type_a_resource`）

* **结果**：**PASS**（退出码 `0`）
* **Armature 标识**：`arm_a = 'CharacterArmature'`（指针 `2164275577096`），`sess_a = 'b41c7620-f1b4-48df-a2a6-0521cfc53538'`
* **事务标识**：`tx_a = 'c98f303d'`
* **创建的 DataBlock 指针与外部对照组**：
  * 授权 Type A Mesh：`'Fix6Bug3_A_TypeA'`（指针 `2164345427464`，事务前不存在，`users == 0`）
  * 无授权外部对照组：`'Fix6Bug3_A_ExtUnauth'`（指针 `2164345435528`，`users == 0`）
* **创建授权与回执**：
  * 回执 `(tx_id, session_id)`：`('c98f303d', 'b41c7620-f1b4-48df-a2a6-0521cfc53538')`（`_type_a_datablock_receipts[2164345427464]` 4 元组校验及印章 `_type_a_datablock_receipt_seal` 通过）
  * 授权记录：`{'resource_kind': 'meshes', 'original_reference': bpy.data.meshes['Fix6Bug3_A_TypeA'], 'original_pointer': 2164345427464, 'provenance': 'TYPE_A_TX_CREATED', 'authorization_source': 'TX_CREATE_RECEIPT', 'authorization_scope': 'PHYSICAL_DELETE_IF_ZERO_USERS', 'authorized_transaction': 'c98f303d', 'expected_lifecycle': 'COMMITTED_CLEANUP'}`
* **真实待清理资源清单 (`uncleaned_stashed_objects`)**：
  * `[{'original_name': 'HandIK.L', 'obj_cleaned': True, 'data_cleaned': False, 'stashed_data_name': 'Fix6Bug3_A_TypeA', 'stashed_data_ptr': 2164345427464}]`
* **Pending 状态、Registry 与 Gate**：
  * `tx_a.state == CLEANUP_PENDING`，`tx_a.cleanup_error == 'Failed to clean up datablock for HandIK.L: INJECTED_PENDING_ON_ARMATURE_A'`
  * Pending Registry：`{'c98f303d': ('c98f303d', 'CLEANUP_PENDING', 1)}`
  * 调用 `set_arm_ik_influence(arm_a, side='L', influence=0.25)` 触发 `RuntimeError` 包含 `'Arm IK write blocked: unresolved cleanup'`
* **异常信息与 Traceback（节选自日志 L396–L416）**：
  * 注入函数与阶段：`src/rig/arm_ik.py` 第 7247 行 `retry_cleanup` -> `during_cleanup_datablock_after_auth_before_remove` -> `RuntimeError: INJECTED_PENDING_ON_ARMATURE_A`
  * Coordinator 上抛：`RuntimeError: Arm rig transaction commit cleanup CLEANUP_INCOMPLETE: transaction=c98f303d; phase=INITIAL_CLEANUP; remaining_objects=1; remaining_constraints=0; errors=Failed to clean up datablock for HandIK.L: INJECTED_PENDING_ON_ARMATURE_A`（对应 `INITIAL_CLEANUP` 的 `_CleanupOutcome.CLEANUP_INCOMPLETE`）
* **清理前后 `bpy.data.meshes` 自定义资源集合**：
  * 事务前：`[('Fix6Bug3_A_ExtUnauth', 2164345435528, 0)]`
  * Pending 中：`[('Fix6Bug3_A_ExtUnauth', 2164345435528, 0), ('Fix6Bug3_A_TypeA', 2164345427464, 0)]`
  * 重试后：`[('Fix6Bug3_A_ExtUnauth', 2164345435528, 0)]`
* **重试、Coordinator 收口与物理删除结果**：
  * `retry_pending_arm_rig_cleanup('c98f303d')` 返回 `None`（由 Coordinator 通过 `_coordinator_validate_cleanup_preflight(..., phase="PENDING_RETRY")`、内部 `tx.retry_cleanup()` 返回 `_CleanupResult(outcome=CLEANUP_SUCCESS, remaining_objects=0, remaining_constraints=0, errors=())` 后经 `_coordinator_apply_cleanup_result` 收口）
  * 终态：`tx_a.state == COMMITTED`，`tx_a.cleanup_error is None`，`uncleaned_stashed_objects` 清空，`_PENDING_ARM_RIG_CLEANUPS == {}`
  * 物理删除结果：`{'action': 'DELETED', 'status': 'PHYSICALLY_DELETED', 'reason': 'AUTHORIZED_CLEANUP', 'resource_kind': 'Mesh', 'resource_name': 'Fix6Bug3_A_TypeA', 'resource_pointer': 2164345427464, 'tx_id': 'c98f303d'}`

### 3.2 测试 B：A 处于真实 Pending 期间，B 独立创建真实 Type A Mesh 并提交，随后 A 重试互不误删（`test_B_while_a_pending_b_runs_with_real_type_a_mesh_and_a_retries_isolated`）

* **结果**：**PASS**（退出码 `0`）
* **Armature / Session / 事务标识**：
  * A：`arm_a = 'CharacterArmature'`（`2164299067912`），`sess_a = '4939b88c-a032-46b7-9b52-663ba2bbb87e'`，`tx_a = 'caba54a6'`（`CLEANUP_PENDING`）
  * B：`arm_b = 'CharacterArmatureB'`（`2164299060744`），`sess_b = 'ba17148f-8169-4681-ab77-92e14467e17e'`，`tx_b = '3a0ecee2'`（`COMMITTED`）
* **Gate 隔离**：`query_admission_gate_status(arm_a)['cleanup_pending_blocked'] == True`，`query_admission_gate_status(arm_b)['cleanup_pending_blocked'] == False`
* **DataBlock 指针及 B 创建授权与回执（注：B 为存活 Type A Mesh，未进入 `uncleaned_stashed_objects`）**：
  * A Pending Mesh：`'Fix6Bug3_SharedName'`（指针 `2164300737288`，位于 `tx_a.uncleaned_stashed_objects`）
  * B 存活 Type A Mesh：以同名请求创建得 `'Fix6Bug3_SharedName.001'`（指针 `2164343870984`，`users == 0`，`len(tx_b.uncleaned_stashed_objects) == 0`）
  * B 回执与授权：`receipt_b_tx_sess = ('3a0ecee2', 'ba17148f-8169-4681-ab77-92e14467e17e')`，`auth_b = {'resource_kind': 'meshes', 'original_reference': bpy.data.meshes['Fix6Bug3_SharedName.001'], 'original_pointer': 2164343870984, 'provenance': 'TYPE_A_TX_CREATED', 'authorization_source': 'TX_CREATE_RECEIPT', 'authorization_scope': 'PHYSICAL_DELETE_IF_ZERO_USERS', 'authorized_transaction': '3a0ecee2', 'expected_lifecycle': 'COMMITTED_CLEANUP'}`
* **清理前后集合与 Pending Registry**：
  * B 提交后 Pending Registry 仍为 `{'caba54a6': 'CLEANUP_PENDING'}`；`A` 的待清理 Mesh 未被 B 提交误处理。
  * 重试 A 前：`[('Fix6Bug3_SharedName', 2164300737288, 0), ('Fix6Bug3_SharedName.001', 2164343870984, 0)]`
  * `retry_pending_arm_rig_cleanup('caba54a6')` 后：`[('Fix6Bug3_SharedName.001', 2164343870984, 0)]`，`pending_registry_after == {}`
* **物理删除与隔离验证**：
  * A 仅删除 `2164300737288`：`{'action': 'DELETED', 'status': 'PHYSICALLY_DELETED', 'reason': 'AUTHORIZED_CLEANUP', 'resource_kind': 'Mesh', 'resource_name': 'Fix6Bug3_SharedName', 'resource_pointer': 2164300737288, 'tx_id': 'caba54a6'}`
  * B 的 `'Fix6Bug3_SharedName.001'`（`2164343870984`）、回执 `receipt_b` 与 `auths_b` 原封保留，无按名称误删。

### 3.3 测试 C1a & C1b：双 Armature 并发 `CLEANUP_PENDING` 的双向重试隔离（`PARTIAL` 覆盖说明）

> [!IMPORTANT]
> **严格区分“持有真实创建资源”与“位于待清理队列”**：在 C1a 与 C1b 中，Armature A 真实持有待清理 Type A 资源（`len(tx_a.uncleaned_stashed_objects) == 1`）；Armature B 通过 `_authorized_create_type_a_mesh()` 真实创建并绑定了属于 B 事务与会话的 Type A Mesh，但因全局 Controller 命名限制无法安全执行 `setup_arm_ik(arm_b)`（见 3.4），故 `len(tx_b.uncleaned_stashed_objects) == 0`，B 的 Pending 由真实 `during_commit_cleanup` 故障注入门禁触发。本节不将该场景伪称为“B 也持有一条待清理 stashed 资源”。

* **C1a（并发 Pending → 先重试 A，再重试 B）**：**PASS**（退出码 `0`）
  * 标识：`arm_a = 'CharacterArmature'`（`2164273512712`，`sess_a = '24b230d4-79fe-494b-9f33-d548aa3a46fc'`，`tx_a = '07282a36'`）；`arm_b = 'CharacterArmatureB'`（`2164345361928`，`sess_b = 'd396ce24-7a9b-4fd7-919e-fc3e35deab8f'`，`tx_b = 'c5c66b10'`）
  * DataBlock：`a_pending_name = 'Fix6Bug3_C1a_A'`（指针 `2164300360456`）；`b_created_name = 'Fix6Bug3_C1a_B'`（指针 `2164343122696`，`b_uncleaned_len = 0`）
  * B 故障注入堆栈（节选自日志 L439–L457）：`src/rig/arm_ik.py` 第 8702 行 `_arm_rig_transaction` -> `"during_commit_cleanup"` -> `RuntimeError: Arm rig transaction committed, but post-commit cleanup failed (irreversible cleanup failed): INJECTED_PENDING_ON_ARMATURE_B`
  * 并发 Pending Registry：`{'07282a36': ('CLEANUP_PENDING', 1), 'c5c66b10': ('CLEANUP_PENDING', 0)}`
  * 先 `retry_pending_arm_rig_cleanup('07282a36')`：`tx_a -> COMMITTED`，`tx_b` 保持 `CLEANUP_PENDING`；Pending Registry 为 `{'c5c66b10': 'CLEANUP_PENDING'}`；`gate_a == False, gate_b == True`；A 的 `2164300360456` 删除，B 的 `2164343122696` 及回执保留。
  * 再 `retry_pending_arm_rig_cleanup('c5c66b10')`：`tx_b -> COMMITTED`，`_PENDING_ARM_RIG_CLEANUPS` 清空，`gate_b == False`；`bpy.data.meshes` 中仅剩 `[('Fix6Bug3_C1a_B', 2164343122696, 0)]`；`outcomes_a` 1 条 `PHYSICALLY_DELETED`，`len(tx_b.datablock_cleanup_outcomes) == 0`。
* **C1b（反向顺序：并发 Pending → 先重试 B，再重试 A）**：**PASS**（退出码 `0`）
  * 标识：`arm_a`（`2164299949064`，`sess_a = '04f064d1-db68-4ed8-b135-453cb753fe70'`，`tx_a = 'cafdaf97'`，`a_pending_ptr = 2164358540040`）；`arm_b`（`2164358441736`，`sess_b = '6c2bb7a5-5705-4fba-b210-563c99d3eb0f'`，`tx_b = 'c526d6f4'`，`b_created_ptr = 2164342707720`）
  * 并发 Pending Registry：`{'cafdaf97': ('CLEANUP_PENDING', 1), 'c526d6f4': ('CLEANUP_PENDING', 0)}`
  * 先 `retry_pending_arm_rig_cleanup('c526d6f4')`：`tx_b -> COMMITTED` 离开注册表；**`tx_a` 保持 `CLEANUP_PENDING`**，Pending Registry 精确剩余 `{'cafdaf97': ('CLEANUP_PENDING', 1)}`，`gate_a == True, gate_b == False`，`tx_a.uncleaned_stashed_objects`（含 `2164358540040`）、`bpy.data.meshes` 中的 `2164358540040` 与 A 的回执及 B 的存活 Mesh `2164342707720` 均完好。
  * 再 `retry_pending_arm_rig_cleanup('cafdaf97')`：`tx_a -> COMMITTED`，A 的 `2164358540040` 记录 `PHYSICALLY_DELETED`，Pending Registry 清空，B 的 `2164342707720` 完整保留。

### 3.4 测试 C2：双 Armature `setup_arm_ik` 全局命名冲突探针（Section 8 & 9 核心审计发现）

* **结果**：**PASS (CONFLICT DOCUMENTED)**（退出码 `0`）
* **测试上下文**：`arm_a = 'CharacterArmature'`（`2164357353224`，`sess_a = '6b6c79d7-6136-4582-bc5d-e7a8b09173d1'`，`tx_a = '08484d00'`，Pending Mesh `'Fix6Bug3_C2_TypeA_A'` 指针 `2164300177544`）；`arm_b = 'CharacterArmatureB'`（`2164297522440`，`sess_b = '718de94b-41ae-4996-b63e-f56344fe6689'`）。
* **阻塞点精准定位**：
  * 精确函数：`_require_existing_arm_ik_controller_ownership(arm, scope='setup_arm_ik')`（[arm_ik.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L2551-L2598)，被 `setup_arm_ik` 于 [第 8898 行](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py#L8898) 调用）
  * 冲突对象名称：`'HandIK.L'`（全局常量 `ARM_IK_TARGET_NAMES` / `ARM_POLE_TARGET_NAMES` 首检对象）
  * 精确异常：`ExternalControllerNameConflictError("EXTERNAL_CONTROLLER_NAME_CONFLICT: setup_arm_ik: controller 'HandIK.L' is present without a verified owning Armature/transaction binding")`
  * 实测完整 Traceback（原文自日志 L480–L489）：
    ```text
    Traceback (most recent call last):
      File "<string>", line 333, in test_C2_dual_armature_setup_arm_ik_global_controller_name_conflict_probe
      File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\src\rig\arm_ik.py", line 8898, in setup_arm_ik
        _require_existing_arm_ik_controller_ownership(arm, scope='setup_arm_ik')
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^
      File "C:\Users\64701\OneDrive\Desktop\ProceduralAnimation\src\rig\arm_ik.py", line 2595, in _require_existing_arm_ik_controller_ownership
        raise ExternalControllerNameConflictError(
        ...<2 lines>...
        )
    src.rig.arm_ik.ExternalControllerNameConflictError: EXTERNAL_CONTROLLER_NAME_CONFLICT: setup_arm_ik: controller 'HandIK.L' is present without a verified owning Armature/transaction binding
    ```
* **隔离与后续收口验证**：
  * 冲突发生并抛错后，A 的事务 `tx_a` 仍为 `CLEANUP_PENDING`，`_PENDING_ARM_RIG_CLEANUPS` 仅含 `{'08484d00'}`（无 B 残留事务），待清理 Mesh `2164300177544` 仍在库。
  * 随后 `retry_pending_arm_rig_cleanup('08484d00')` 成功物理删除 `2164300177544`（`PHYSICALLY_DELETED`）并收敛至 `COMMITTED`。

---

## 4. 未执行范围与源码 / Git 冻结状态

* **`NOT EXECUTED`（遵循任务边界禁止执行）**：
  * 四级全量回归（`quick` / `physics` / `motion` / `full`）：**`NOT EXECUTED`**
  * `TEST-64` 重跑 / 修改：**`NOT EXECUTED`**
  * 历史文档偏差处理、`fix7`、`10-C`、`10-D`、`arm_ik.py` 拆分：**`NOT EXECUTED`**
* **源码、历史文件与 Git 状态**：
  * 固定基线分支 / HEAD 保持为 `audit/task-10-b-9` @ `32c70f946f2e3024786d0889f2a66b80c7375633`。
  * `git diff --exit-code` 与 `git diff --cached --exit-code` 测试前后均为 `0`；`src/`、[test_task10b_transaction_atomicity.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py)、`fix6-bug1`/`fix6-bug2` 证据、`CORE_REPAIR_LEDGER.md`、`PROJECT_STATE.md` 及 8 项预存未跟踪文件均**零修改、零删除**。
  * 遵循 Section 12 失败熔断规则：因 `HIST-F06` 只能形成 **`PARTIAL`** 覆盖（受制于 `HandIK.L`/`HandIK.R`/`ElbowPole.L`/`ElbowPole.R` 全局名称冲突接口限制），**未执行 `git commit`、`git push` 或任何向 `master` 合并动作**，仅保留本地实测证据文件 [fix6-bug3_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug3_test_execution.log) 与本报告以供独立审计。
