# TASK 10-B-14 · Remaining Findings & Contract Verification Register

> **基线 Commit**：`792262e8e7dc7e19c10444d4ff407cb2a87ad8aa`
> **审计分支**：`audit/task-10-b-9`
> **状态**：`AUDIT_COMPLETED_WITH_CONFIRMED_ARCHITECTURE_GAPS`
> **合同状态汇总**：`VERIFIED: 5` | `DEFECT: 6` | `UNVERIFIED: 1`
> **当前确认架构缺口数 (`open_defects_count`)**：`6`（`F14-01` ～ `F14-06`）

---

## 1. 当前确认的生产架构缺口 (Confirmed Production Architecture Findings: F14-01 ～ F14-06)

### F14-01 · DataBlock 删除缺少显式授权

位置：`src/rig/arm_ik.py:3527–3578`

现状：

- 删除依据主要为 `users == 0`。
- 缺少 `AuthorizedCleanup(D,t)` 的显式证明。
- `ReferenceError` 被转换为 `user_count = 0`。
- 无授权 DataBlock 未实现批准的 `PRESERVED_NO_DELETE_AUTHORITY` 终态。

影响合同：CONTRACT-03、08、12。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

### F14-02 · 关系操作日志覆盖不完整

位置：

- `src/rig/arm_ik.py:144`
- `src/rig/arm_ik.py:2374–2375`
- `src/rig/arm_ik.py:2560–2564`
- `src/rig/arm_ik.py:2693`
- `src/rig/arm_ik.py:2713`
- `src/rig/arm_ik.py:4689`
- `src/rig/arm_ik.py:4870–4871`

现状：

Collection ↔ Object 已有七状态日志。

Object Parent、Constraint Target/Pole Target、Collection Parent/Child 未全部经过相同授权与关系记录流程。

影响合同：CONTRACT-04、05。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

### F14-03 · Constraint 资源操作执行权未完全统一

位置：`src/rig/arm_ik.py:4830–4930`

现状：

Constraint 创建、删除仍存在业务层直接执行 Blender API 的路径。

已有身份登记和回滚测试，但不满足批准的全部 Layer 3 操作职责。

影响合同：CONTRACT-05。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

### F14-04 · Cleanup 状态所有权未收敛

位置：

- `src/rig/arm_ik.py:3590–3595`
- `src/rig/arm_ik.py:3631–3670`

现状：

Layer 6 的 `retry_cleanup()` 直接更新事务状态。

重试入口直接删除 `_PENDING_ARM_RIG_CLEANUPS` 条目。

与 Coordinator 独占状态决策和门禁注销的批准合同不一致。

影响合同：CONTRACT-08、09。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

### F14-05 · 同名错误类型对象缺少充分所有权证明

位置：`src/rig/arm_ik.py:4638–4675`

现状：

通过 `bpy.data.objects.get(name)` 取得错误类型对象后直接进入暂存和后续废弃流程。

没有充分证明该对象属于当前事务有权清理的 Rig 资源。

影响合同：CONTRACT-03、12。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

### F14-06 · Collection 创建后登记顺序错误

位置：`src/rig/arm_ik.py:138–146`

现状：

先 `scene.collection.children.link(col)`，后 `register_created_collection()`。

违反创建后、外部链接前登记所有权的批准顺序。

实际异常残留仍需专项测试，不得宣称已经复现。

影响合同：CONTRACT-03、04。

状态：CONFIRMED_ARCHITECTURE_DEFECT。

---

## 2. 历史 Finding 状态记录（遵循 `docs/evidence/task10b13/round04/confirmed_findings.md` 原始定义）

原始证据文件：`docs/evidence/task10b13/round04/confirmed_findings.md`（保持只读，不改写原始历史文档）。

| 编号 | 原始含义（严禁重定义） | 对应源码 / 测试证据 | 当前核实状态 |
|---|---|---|---|
| **F-01** | TEST-151 的 `RECOVERY_UNCERTAIN` 验证分支短路 | `src/rig/arm_ik.py:3827–4014` (`verify_armature_deisolation_evidence`), `tests/test_task10b_transaction_atomicity.py` (`TEST-151`) | **CLOSED**（已由 TEST-151 传入可信快照到达 Case 1 Condition 6 验证关闭） |
| **F-02** | `UNKNOWN` 错误升级为 `FAILED-D` | `src/rig/arm_ik.py:4333–4557`, `tests/test_task10b_transaction_atomicity.py` (`TEST-174`～`178`, `TEST-181`) | **CLOSED**（已由专项测试验证 `UNKNOWN` 不再升级为 `FAILED-D`） |
| **F-03** | Coordinator Grant 授权回退歧义及授权记录累积问题 | `src/rig/arm_ik.py:864–955`, `957–1062`, `tests/test_task10b_transaction_atomicity.py` (`TEST-182`) | **PARTIALLY_OPEN**（`verification_evidence` 回退歧义已由 TEST-182 关闭；但授权记录期限/清理问题尚无对应证据，未完全关闭） |
| **F-04** | 嵌套事务双异常链测试缺口 | `tests/test_task10b_transaction_atomicity.py` (`TEST-183`) | **CLOSED**（已由 TEST-183 验证嵌套双异常链与隔离记录保留） |
| **F-05** | 非 Mesh 共享 DataBlock 测试缺口 | `tests/test_task10b_transaction_atomicity.py` (`TEST-184`) | **CLOSED**（已由 TEST-184 验证共享 curve 与 armature DataBlock 保留） |
| **F-06** | `CLEANUP_PENDING` 下双臂及跨 Armature 门禁覆盖缺口 | `tests/test_task10b_transaction_atomicity.py` | **OPEN_COVERAGE_GAP**（尚未提供 `CLEANUP_PENDING` 下双臂 Reset 与跨 Armature 完整联合覆盖的独立专项证据，不得宣称完全关闭） |

---

## 3. 准入边界声明

- 本文件仅归档独立审计确认的合同状态与架构缺口（`F14-01` ～ `F14-06`）及历史 Finding 真实状态。
- 在 `F14-01` ～ `F14-06` 及相关合同缺口按批准方案完成修复与独立验收前，严禁宣布 Task 10-B 完成，严禁进入 Task 10-C。
