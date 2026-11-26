# TASK 10-B-15 (Round 5/6) Test Change Audit: Historical Call Site Migration

## 1. 概述与迁移背景

在 TASK 10-B-15 (Round 5/6) 中，实施了架构缺陷 **F14-04 (CleanupOutcome 与 Coordinator 状态决策权统一)** 的修复：
1. **Layer 6 纯化**：`_ArmRigTransactionContext.retry_cleanup()` 不再直接修改事务生命周期状态（移除 `self.state = COMMITTED / CLEANUP_PENDING`），也不直接操作全局挂起队列 `_PENDING_ARM_RIG_CLEANUPS.pop()`，而是作为幂等只读式清理执行器，返回结构化、不可变的 `_CleanupResult`（包含 `_CleanupOutcome` 枚举、错误列表、剩余资源统计与原始异常因果链）。
2. **Coordinator 状态所有权闭环**：生命周期状态决策与注销权完全归收于 Layer 1 事务协调器。外部业务调用入口为 `retry_pending_arm_rig_cleanup(tx_id)`，其委托 `_coordinator_apply_cleanup_result(tx, cleanup_result, phase="PENDING_RETRY")` 执行 10 项前置校验与独占状态转移。

因此，历史测试中直接调用 `tx.retry_cleanup()` 并期望其自动修改 `tx.state` 或注销注册表的 6 处调用点，必须依据架构规范迁移至合法入口。

---

## 2. 迁移清单核验

| 测试用例 | 原始调用模式 | 迁移后调用模式 | 迁移理由 | 语义完整性核验 |
|---|---|---|---|---|
| **TEST-66** | `tx.retry_cleanup()` | `retry_pending_arm_rig_cleanup(tx.tx_id)` | 清理失败后已进入 `CLEANUP_PENDING` 并登记注册表，重试应通过协调器入口触发状态转入 `COMMITTED` | 完全一致，业务断言 `tx.state == COMMITTED` 正常通过 |
| **TEST-67** | `tx.retry_cleanup()` | `retry_pending_arm_rig_cleanup(tx.tx_id)` | 验证注入故障清除后重试清理收敛，由协调器完成注销与转入 `COMMITTED` | 完全一致，断言 `tx.state == COMMITTED` 正常通过 |
| **TEST-88** | `tx.retry_cleanup()` | `tx.state = CLEANUP_PENDING; res = tx.retry_cleanup()` | 专项核验 Layer 6 约束清理逻辑与返回值，断言 `res.outcome == CLEANUP_SUCCESS` 与 `res.remaining_constraints == 0` | 增强了对 Layer 6 结构化返回值的直接断言 |
| **TEST-97** | `with self.assertRaises(RuntimeError): tx.retry_cleanup()` | `tx.state = CLEANUP_PENDING; res = tx.retry_cleanup()` | Layer 6 不再在清理不完整时抛异常，而是捕获底层异常并返回 `CLEANUP_INCOMPLETE` | 断言 `res.outcome == CLEANUP_INCOMPLETE` 且包含原异常信息，语义精准对齐 |
| **TEST-192** | `tx.retry_cleanup()` | `retry_pending_arm_rig_cleanup(tx.tx_id)` | 验证 Type A 资源在重试清理失败时向上传播异常，应通过协调器入口 | 完全一致，协调器向上重新抛出异常链并包含原标识 |
| **TEST-208** | `tx.retry_cleanup()` | `retry_pending_arm_rig_cleanup(tx.tx_id)` | 验证清除 fault hook 后约束重试清理收敛，通过协调器完成 COMMITTED 转移 | 完全一致，断言 `tx.state == COMMITTED` 正常通过 |

---

## 3. 详细代码比对

### 3.1 TEST-66
```diff
-        _clear_test_fault_injection_hook()
-        tx.retry_cleanup()
+        _clear_test_fault_injection_hook()
+        retry_pending_arm_rig_cleanup(tx.tx_id)
```

### 3.2 TEST-67
```diff
         # Retry cleanup converges cleanly
         _clear_test_fault_injection_hook()
-        tx.retry_cleanup()
-        self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)
+        retry_pending_arm_rig_cleanup(tx.tx_id)
+        self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)
```

### 3.3 TEST-88
```diff
         # Execute retry_cleanup()
-        tx.retry_cleanup()
+        tx.state = _ArmRigTransactionState.CLEANUP_PENDING
+        res88 = tx.retry_cleanup()
+        self.assertEqual(res88.outcome, _CleanupOutcome.CLEANUP_SUCCESS)
+        self.assertEqual(res88.remaining_constraints, 0)
```

### 3.4 TEST-97
```diff
-        with self.assertRaises(RuntimeError) as cm:
-            tx.retry_cleanup()
-
-        self.assertIn("original reference invalid", str(cm.exception))
+        tx.state = _ArmRigTransactionState.CLEANUP_PENDING
+        res97 = tx.retry_cleanup()
+        self.assertEqual(res97.outcome, _CleanupOutcome.CLEANUP_INCOMPLETE)
+        self.assertTrue(any("original reference invalid" in e for e in res97.errors))
```

### 3.5 TEST-192
```diff
             _clear_test_fault_injection_hook()
             with self.assertRaises(RuntimeError) as cm:
-                tx.retry_cleanup()
+                retry_pending_arm_rig_cleanup(tx.tx_id)

             self.assertIn("TYPE_A_TX_CREATED", str(cm.exception))
```

### 3.6 TEST-208
```diff
         # Clear fault hook and retry cleanup
-        tx.retry_cleanup()
+        retry_pending_arm_rig_cleanup(tx.tx_id)
         self.assertEqual(len(tx.uncleaned_stashed_constraints), 0)
         self.assertEqual(tx.state, _ArmRigTransactionState.COMMITTED)
```

---

## 4. 审计结论

1. 6 处历史测试调用点已全部依据 F14-04 架构规范完成精确适配。
2. 无任何断言放宽或静默跳过行为。
3. 全套 Atomicity 测试（215/215）在适配后 100% 通过。
