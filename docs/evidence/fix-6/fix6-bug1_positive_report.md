# TASK: fix6-bug1 — TYPE A POSITIVE VERIFICATION REPORT

* **任务编号 / 子任务**：`fix6-bug1`（所属主任务 `fix6`，历史问题追溯 `R1-TAIL-02`，阶段类型：`TEST ONLY — 失败后重新审计并冻结执行范围`）
* **仓库 / 分支**：`cgfe10231-ai/ProceduralAnimation` / `audit/task-10-b-9`
* **固定基线 Commit SHA**：`62909875359b44ad065aaa48e3ca32d6db3d592b`（未创建新提交、未推送、未合并 `master`）
* **Blender 完整版本**：`Blender 5.1.1 (hash b70da489d7f4 built 2026-04-14 01:37:22)`
* **治理规范**：`origin/master:WORKFLOW_GOVERNANCE.md`（`APPROVED`）；已只读核对 `WORKFLOW_GOVERNANCE.md`、[ARCHITECTURE_SYNC.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/ARCHITECTURE_SYNC.md)、[CORE_REPAIR_LEDGER.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/task10b15/CORE_REPAIR_LEDGER.md) 与 [arm_ik.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/src/rig/arm_ik.py)
* **历史失败证据（完整保留，未覆盖/未重跑）**：
  * [fix6-bug1_test_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug1_test_execution.log)
  * [fix6-bug1_test_report.md](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug1_test_report.md)
* **本轮正向验证原始日志**：
  * [fix6-bug1_positive_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug1_positive_execution.log)

---

## 1. 测试前后 Git 状态与非预期修改核对

* **测试前检查**：
  * 分支：`audit/task-10-b-9`
  * `HEAD`：`62909875359b44ad065aaa48e3ca32d6db3d592b`
  * `git diff --exit-code`：`0`
  * `git diff --cached --exit-code`：`0`
* **测试后检查**：
  * 分支：`audit/task-10-b-9`
  * `HEAD`：`62909875359b44ad065aaa48e3ca32d6db3d592b`
  * `git diff --exit-code`：`0`
  * `git diff --cached --exit-code`：`0`
* **是否发生非预期文件修改**：**否**。`src/`、[test_task10b_transaction_atomicity.py](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/tests/test_task10b_transaction_atomicity.py)、`fix-4`/`fix-5` 证据、既有 `TEST-64` 失败证据及预存 8 项未跟踪文件均保持原状；本轮仅新增 `docs/evidence/fix-6/fix6-bug1_positive_execution.log` 与本报告。

---

## 2. 分类结论总表

| 类别 | 范围 | 结论 | 备注 |
| :--- | :--- | :---: | :--- |
| **TEST-64（历史 FAIL）** | `test_64_commit_cleanup_failure_and_datablock_lifecycle` | **`FAIL — LEGACY FIXTURE CONFLICT`** | 本轮按冻结范围未重跑、未修改，原始日志与报告保留于 `fix6-bug1_test_report.md`（退出码 `1`） |
| **第一阶段：其余已有专项** | `TEST-83`, `TEST-188`, `TEST-191`, `TEST-192`, `TEST-193` | **5/5 PASS** | 全部使用 Blender 5.1.1 逐项独立执行，退出码均为 `0` |
| **第二阶段：Type A 正向验证** | `TestFix6Bug1TypeAPositiveLifecycle`（A–D：`test_01`, `test_02`） | **2/2 PASS** | 纯内存 `--python-expr` 在 Blender 5.1.1 独立进程执行，退出码 `0`（`Ran 2 tests in 0.353s`, `OK`） |
| **四级全量回归** | `quick` / `physics` / `motion` / `full` | **NOT EXECUTED** | 按任务边界禁止自动执行全量回归 |

---

## 3. 第一阶段：其余已有 DataBlock 专项测试 (`tests/test_task10b_transaction_atomicity.py`)

执行结果：**5/5 PASS**（不含已冻结历史失败的 `TEST-64`）

| 编号 | 完整方法名 (`TestArmIKTransactionAtomicity.*`) | 耗时 | 退出码 | 状态 | 验证内容与结果摘要 | 测试前后 SHA |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **TEST-83** | `test_83_datablock_shared_users_and_same_name_replacement_preserved` | 0.869s | `0` | **PASS** | 无异常；共享 DataBlock (`users > 0`) 与同名不同身份资源均保留 | `62909875...592b` -> 一致 |
| **TEST-188** | `test_188_zero_user_unauthorized_mesh_datablock_preserved_on_commit` | 0.237s | `0` | **PASS** | 无异常；无删除授权的零用户 Mesh 在提交后保持 `users == 0` 保留且无 Pending | `62909875...592b` -> 一致 |
| **TEST-191** | `test_191_same_name_different_identity_datablocks_protected` | 0.233s | `0` | **PASS** | 无异常；同名不同身份两个 Mesh 指针全部保留，`tx.state == COMMITTED` | `62909875...592b` -> 一致 |
| **TEST-192** | `test_192_forged_type_a_authorization_rejected_and_datablock_protected` | 0.233s | `0` | **PASS** | `retry_pending_arm_rig_cleanup` 拒绝 `FORGED_TEST_FIXTURE_CLAIM`，抛出 `lacks credible transaction creation provenance` 并保护 Mesh | `62909875...592b` -> 一致 |
| **TEST-193** | `test_193_preserved_no_delete_authority_terminal_state_and_idempotency` | 0.233s | `0` | **PASS** | 无授权 Mesh 记为 `PRESERVED_NO_DELETE_AUTHORITY`，多次 `retry_cleanup()` 幂等且保持 `COMMITTED` | `62909875...592b` -> 一致 |

**第一阶段逐项独立执行命令模板**：
```powershell
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr "import os, sys, unittest; sys.path.insert(0, os.path.abspath('.')); name = 'tests.test_task10b_transaction_atomicity.TestArmIKTransactionAtomicity.<METHOD_NAME>'; suite = unittest.TestLoader().loadTestsFromName(name); result = unittest.TextTestRunner(verbosity=2).run(suite); sys.exit(0 if result.wasSuccessful() and result.testsRun == 1 else 1)"
```

---

## 4. 第二阶段：Type A 正向生命周期验证（纯内存 `--python-expr`）

* **执行命令**：`"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python-exit-code 1 --python-expr <IN_MEMORY_EXPR>`（完整脚本与输出见 [fix6-bug1_positive_execution.log](file:///c:/Users/64701/OneDrive/Desktop/ProceduralAnimation/docs/evidence/fix-6/fix6-bug1_positive_execution.log#L122-L413)）
* **测试类**：`TestFix6Bug1TypeAPositiveLifecycle`
* **退出码**：`0`（`Ran 2 tests in 0.353s`，`OK`）
* **原始异常**：无非预期异常（2/2 PASS）

### 4.1 关键实测遥测数据（`test_01_type_a_full_positive_lifecycle_and_idempotency`）
* **事务与会话身份**：`tx_id = '558ef5b0'`，`session_id = '6f139419-54f4-4c09-be92-82827e2105ba'`，状态由 `ACTIVE` 收敛至终态 `COMMITTED`（`cleanup_error = None`，`_PENDING_ARM_RIG_CLEANUPS` 为空，`len(get_pending_arm_rig_cleanup_ids()) == 0`）。
* **A. 合法创建 (`_authorized_create_type_a_mesh`)**：
  * 创建前 `bpy.data.meshes` 基线计数：`16` 个指针，新指针不在此基线集合内。
  * 新建 Type A Mesh：`resource_name = 'Fix6_TypeA_Target.001'`，**Mesh 创建指针 `2572049072392`**，创建时 `users = 0`。
  * Type A 创建凭据 (`tx._type_a_datablock_receipts[2572049072392]`)：长度 `4` 元组 `(type_a_mesh, session_id='6f139419-54f4-4c09-be92-82827e2105ba', tx_id='558ef5b0', seal is tx._type_a_datablock_receipt_seal)`。
  * 自动生成唯一授权记录 (`tx.datablock_authorizations`)：`resource_kind = 'meshes'`、`original_pointer = 2572049072392`、`provenance = 'TYPE_A_TX_CREATED'`、`authorization_source = 'TX_CREATE_RECEIPT'`、`authorization_scope = 'PHYSICAL_DELETE_IF_ZERO_USERS'`、`authorized_transaction = '558ef5b0'`、`expected_lifecycle = 'COMMITTED_CLEANUP'`。
* **B. 注册受管对象与控制器替换**：
  * 测试起始时场景无 `HandIK.L` 与 `HandIK.R` 对象。
  * 使用 `type_a_mesh` 创建错误类型对象 `'HandIK.L'`（`type_a_mesh.users` 变为 `1`），依次通过 `tx.register_created_controller(wrong_obj_l)` 与 Layer 3 `_authorized_link_object_to_collection(...)` 登记链接；同期使用无授权 `Fix6_Unauth_HandIK_R`（指针 `2572049080456`）创建 `'HandIK.R'` 作为同事务保护对照。
  * 调用 `arm_ik.setup_arm_ik(self.armature, initial_influence=0.5)` 后，`HandIK.L` 与 `HandIK.R` 均被替换为新 `EMPTY` 控制器，旧对象正确进入 `tx.stashed_objects`。
* **C. 事务提交与真实物理删除**：
  * 旧受管 `'HandIK.L'` / `'HandIK.R'` 错误类型 Object 全部从 `bpy.data.objects` 清除。
  * 通过只读观测钩子 `during_cleanup_datablock_after_auth_before_remove` 实测删除前一刻引用计数：`pre_remove_users = [(2572049072392, 0, 'Fix6_TypeA_Target.001')]`（`users == 0`）。
  * 事务提交后，`2572049072392` 与 `'Fix6_TypeA_Target.001'` 从 `bpy.data.meshes` 彻底消失；`stashed_objects` 状态为 `obj_cleaned=True, data_cleaned=True, data_cleanup_status='PHYSICALLY_DELETED'`。
  * `tx.datablock_cleanup_outcomes` 存在唯一合法删除记录：`{'action': 'DELETED', 'status': 'PHYSICALLY_DELETED', 'reason': 'AUTHORIZED_CLEANUP', 'resource_kind': 'Mesh', 'resource_name': 'Fix6_TypeA_Target.001', 'resource_pointer': 2572049072392, 'tx_id': '558ef5b0'}`。
* **D. 外部/未授权资源保护与清理幂等性**：
  * 预存无授权零用户 Mesh `Fix6_ExtUnauthorized_Pre`（指针 `2572049470984`, `users=0`）完整保留。
  * 外部同名基准 Mesh `Fix6_TypeA_Target`（指针 `2572049473672`, `users=0`）完整保留。
  * 同事务暂存无授权 Mesh `Fix6_Unauth_HandIK_R`（指针 `2572049080456`, `users=0`）记录为唯一 `{'action': 'PRESERVED', 'status': 'PRESERVED_NO_DELETE_AUTHORITY', 'reason': 'NO_DELETE_AUTHORITY', 'resource_kind': 'Mesh', 'resource_name': 'Fix6_Unauth_HandIK_R', 'resource_pointer': 2572049080456, 'tx_id': '558ef5b0'}` 并完整保留。
  * 在 Type A Mesh 物理删除释放名称 `'Fix6_TypeA_Target.001'` 后，新建同精确名零用户诱饵 `decoy_same_name`（指针 `2572048864776`），再连续两次调用 `tx.retry_cleanup()`：均返回 `CLEANUP_SUCCESS`，`decoy_same_name` 完整保留，`tx.state` 保持 `COMMITTED`，`datablock_cleanup_outcomes` 未产生第二条删除或保留记录。

### 4.2 跨事务隔离对照（`test_02_no_cross_transaction_type_a_authority_borrowing`）
* 事务 `tx1`（`tx_id = 'e03a5e83'`）合法创建 Type A Mesh（指针 `2572118393096`）并在替换 `'HandIK.L'` 提交后物理删除；随后独立场景 `arm2` 上的事务 `tx2`（`tx_id = '590b87c6'`）使用同名无授权 Mesh `'Fix6_Tx1_TypeA'`（指针 `2572118540552`）绑定并替换 `'HandIK.L'`：验证 `tx2` 的 `_type_a_datablock_receipt_seal` 与 `tx1` 严格隔离，该无授权 Mesh 不发生跨事务借用，以 `PRESERVED_NO_DELETE_AUTHORITY` 且 `users == 0` 完整保留。

---

## 5. 范围冻结与等待裁决声明

* 本轮未修改任何生产源码、测试源码、测试断言、Controller 角色校验或历史 `TEST-64` 失败报告，未执行四级全量回归，未合并 `master`。
* 本轮保留 `TEST-64` 为 `FAIL — LEGACY FIXTURE CONFLICT`，不自行宣布 `fix6-bug1` 全部验收通过。
* 测试执行完成，当前停止并等待 ChatGPT 独立验收及项目负责人针对 `TEST-64` 夹具迁移的决策。
