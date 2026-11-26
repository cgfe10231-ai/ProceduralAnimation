# TASK 10-B-15 (Round 6/6: F-06 / CONTRACT-10 / 十二项合同证据收束) Implementation Evidence

## 1. 概述与基线
- **Task**: TASK 10-B-15, Round 6/6
- **Focus**: F-06 历史门禁补充、CONTRACT-10 跨子系统单帧失败边界专项验证及十二项合同证据收束
- **基线 Commit**: `56fcf62630b331b3e6c7233351d7ddc263be9919`
- **分支**: `audit/task-10-b-9`
- **生产代码状态**: **严格冻结（0 修改）**
  - `src/rig/arm_ik.py` (只读)
  - `src/motion/whole_body_controller.py` (只读)
  - `src/motion/kinematic_bridge.py` (只读)
  - `src/motion/framework.py` (只读)
  - `src/rig/ik.py` (只读)
  - `src/rig/foot_contact.py` (只读)

---

## 2. 测试套件实现与新增用例

### A. Atomicity Suite 补充用例 (TEST-246 至 TEST-253，共 8 项)
在 `tests/test_task10b_transaction_atomicity.py` 中追加历史 F-06 专项测试用例，覆盖双臂及跨 Armature 在 `CLEANUP_PENDING` 状态下的准入隔离：

| 编号 | 测试用例 | 验证核心行为 | 结果 |
|---|---|---|---|
| **TEST-246** | `test_246_bilateral_arms_cleanup_pending_armature_level_isolation` | 单臂事务进入 CLEANUP_PENDING 后，同 Armature 另一臂的事务准入必须被同等拒绝 | **PASS** |
| **TEST-247** | `test_247_cross_armature_pending_cleanup_strict_isolation` | Armature A 处于 CLEANUP_PENDING 不得影响独立的 Armature B 事务准入 | **PASS** |
| **TEST-248** | `test_248_cleanup_pending_admission_rejection_zero_side_effect` | 因 CLEANUP_PENDING 拒绝准入时，保证 100% 零写入与零状态副作用 | **PASS** |
| **TEST-249** | `test_249_cleanup_pending_recovery_unblocks_admission_for_both_arms` | CLEANUP_PENDING 经 Coordinator 成功恢复并注销后，双臂准入立即全部解除阻塞 | **PASS** |
| **TEST-250** | `test_250_concurrent_left_pending_right_active_prohibited` | 严禁单 Armature 上一臂处于 ACTIVE 事务的同时另一臂并发进入 PENDING 清理 | **PASS** |
| **TEST-251** | `test_251_armature_session_id_mismatch_in_pending_registry_blocks_both` | 注册表中 Session ID 校验失败时，保护性拒绝双臂一切新事务写入 | **PASS** |
| **TEST-252** | `test_252_pending_retry_failure_preserves_admission_lock_both_arms` | 清理重试再度失败时，双臂准入门禁必须持续保持锁定 | **PASS** |
| **TEST-253** | `test_253_stale_cleanup_ticket_cannot_unlock_active_pending_admission` | 伪造或过期的清理票据不得解开当前的活跃准入门禁 | **PASS** |

**Atomicity 测试套件总规模扩展至 223 项，实际执行结果：223/223 PASS (100%)**。

---

### B. CONTRACT-10 专项测试套件 (`tests/test_task10b_wbc_failure_contract.py`)
为落实 CONTRACT-10 单帧失败边界合同，新建独立测试套件 `tests/test_task10b_wbc_failure_contract.py`，设计 6 个典型交互场景：

| 编号 | 测试用例 | 场景说明 | 预期行为 | 实际执行结果 |
|---|---|---|---|---|
| **CONTRACT10-01** | `test_contract10_01_normal_execution_bilateral_feedback` | 正常可达目标派发 | WBC 正确协调双臂，返回精确反馈 | **PASS** |
| **CONTRACT10-02** | `test_contract10_02_pending_cleanup_isolation_propagation_to_wbc` | CLEANUP_PENDING 隔离下的帧派发 | WBC 应当感知拒绝并保持整帧零污染 | **FAIL** (Root 坐标在 Arm IK 拒绝前已被写入残留) |
| **CONTRACT10-03** | `test_contract10_03_failed_isolation_propagation_to_wbc` | FAILED 墓碑隔离下的帧派发 | WBC 应当在入口被拒绝并保护场景 | **FAIL** (Root 坐标被修改为 -6.8m 后报错中断) |
| **CONTRACT10-04** | `test_contract10_04_arm_ik_rollback_vs_wbc_prior_writes_restoration` | Arm IK 内部回滚与 WBC 协调 | Arm IK 回滚后 WBC 应回滚其先序写入 | **FAIL** (Arm IK 自身回滚成功，但 WBC Root 残留污染) |
| **CONTRACT10-05** | `test_contract10_05_unreachable_target_reports_truthful_failure` | 远超手臂最大伸展范围目标 | 诚实反馈 `is_reachable=False`，无截断伪报 | **PASS** |
| **CONTRACT10-06** | `test_contract10_06_second_hand_failure_bilateral_partial_commit` | 单帧双臂先后派发，后手失败 | 避免非对称提交，应整帧回退先手手腕 | **FAIL** (左手 influence=1.0 提交，右手回滚，形成半边提交) |

**CONTRACT-10 结论**:
- 2 项通过（正常反馈通道及不可达诚实报告）；
- 4 项失败（忠实揭示了 WBC 缺少单帧事务机制导致的场景残留与撕裂）；
- 测试结果与异常调用链已完整归档入 `docs/evidence/task10b15/round6/deferred_observations.md`。

---

## 3. 全量自动化回归与门禁核验汇总

| 验证项 | 测试命令 | 预期数量 | 实际执行 | 结果 | 耗时 | 证据日志 |
|---|---|---|---|---|---|---|
| **Atomicity Suite** | `tests/test_task10b_transaction_atomicity.py` | 223 | 223 | **223 PASS (0 FAIL, 0 ERR)** | 15.02s | `atomicity.log` |
| **WBC Failure Contract** | `tests/test_task10b_wbc_failure_contract.py` | 6 | 6 | **2 PASS, 4 FAIL (True Contract Defects)** | 0.55s | `wbc_failure_contract.log` |
| **Input Validation** | `tests/test_task10b_input_validation.py` | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 2.37s | `input_validation.log` |
| **Lifecycle Contract** | `tests/test_arm_ik_lifecycle_world_transform_contract.py` | 30 | 30 | **30 PASS (0 FAIL, 0 ERR)** | 4.01s | `lifecycle.log` |
| **Tier Quick** | `tests/run_test_suite.py --tier quick` | 19 | 19 | **19 PASS (0 FAIL, 0 ERR)** | 45.94s | `tier_quick.log` |
| **Tier Physics** | `tests/run_test_suite.py --tier physics` | 27 | 27 | **27 PASS (0 FAIL, 0 ERR)** | 103.87s | `tier_physics.log` |
| **Tier Motion** | `tests/run_test_suite.py --tier motion` | 12 | 12 | **12 PASS (0 FAIL, 0 ERR)** | 50.57s | `tier_motion.log` |
| **Tier Full** | `tests/run_test_suite.py --tier full` | 42 | 42 | **42 PASS (0 FAIL, 0 ERR)** | 158.39s | `tier_full.log` |
| **Architecture Gate** | `tests/audit_c2_final_inspector.py --verify-docs` | N/A | N/A | **PASS (Zero phantom symbols)** | 1.15s | `architecture_integrity_gate.log` |

---

## 4. 生产与测试文件改动审计

- **生产代码文件**:
  - `src/rig/arm_ik.py` 等 6 份生产文件：**0 修改**。
- **测试代码文件**:
  - `tests/test_task10b_transaction_atomicity.py`: 追加 TEST-246 至 TEST-253。
  - `tests/test_task10b_wbc_failure_contract.py`: 新增 CONTRACT-10 专项测试套件。
- **文档与证据文件**:
  - `docs/evidence/task10b15/round6/`:
    - `verification.json`
    - `implementation_evidence.md`
    - `contract_status_delta.md`
    - `deferred_observations.md`
    - 8 份原始执行日志 (`atomicity.log`, `wbc_failure_contract.log`, `input_validation.log`, `lifecycle.log`, `tier_quick.log`, `tier_physics.log`, `tier_motion.log`, `tier_full.log`) 与 1 份架构门禁日志 (`architecture_integrity_gate.log`)。
