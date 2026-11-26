# TASK 10-B-15 (Round 6/6: F-06 / CONTRACT-10 / 十二项合同证据收束) Contract Status Delta

> **审计基线**: TASK 10-B-14 基线 (`792262e8e7dc7e19c10444d4ff407cb2a87ad8aa`)
> **当前评估节点**: TASK 10-B-15 Round 6/6 收束节点 (`56fcf62630b331b3e6c7233351d7ddc263be9919`)
> **分支**: `audit/task-10-b-9`
> **时间**: 2026-11-10

---

## 1. 合同状态变动总览

在 TASK 10-B-15 的 6 轮受控迭代中：
- Round 1/6 (F14-01): 引入 DataBlock 授权容器与授权删除；
- Round 2/6 (F14-05, F14-06): 修复非 Empty 错误类型对象识别与 Collection 登记前置；
- Round 3/6 (F14-02, F14-03): 实现约束创建/删除及 Target 关系的 Layer 3 授权与回滚；
- Round 4/6 (F14-02): 实现 Object Parent 与 Collection Parent/Child 关系的授权与倒序回滚；
- Round 5/6 (F14-04): 纯化 Layer 6 清理器，确立 Coordinator 独占状态决策权与 Pending Registry 管理权；
- Round 6/6 (F-06, CONTRACT-10): 补充 F-06 双臂/跨 Armature 隔离测试（TEST-246～253 全过），并通过新增的 `tests/test_task10b_wbc_failure_contract.py` 专项实测 CONTRACT-10，揭示了 4 项 WBC 单帧跨子系统失败处理缺陷。

### 汇总统计变化

| 状态类别 | TASK 10-B-14 基线 | TASK 10-B-15 Round 6/6 当前 | 状态变化说明 |
|---|---|---|---|
| **VERIFIED** | 5 | 5 | CONTRACT-01, 02, 06, 07, 11 保持稳定通过 |
| **DEFECT** | 6 | 7 | CONTRACT-03, 04, 05, 08, 09, 12 保留历史未决缺陷，**CONTRACT-10 确认为 DEFECT** |
| **UNVERIFIED** | 1 | 0 | **CONTRACT-10** 从 UNVERIFIED 转为确定的 **DEFECT** |

---

## 2. 十二项生产合同最新状态矩阵

| Contract | 10-B-14 状态 | 10-B-15 状态 | 变动说明 | 现存遗留项 / 缺陷依据 |
|---|---|---|---|---|
| **CONTRACT-01** | VERIFIED | **VERIFIED** | 无退化，30/30 PASS | 无 |
| **CONTRACT-02** | VERIFIED | **VERIFIED** | 无退化，嵌套事务与 rollback_only 验证完整 | 无 |
| **CONTRACT-03** | DEFECT | **DEFECT** | R1/R2 完成主体修复，但按规则保留 Tail 项 | 遗留项 R1-TAIL-01～03, R2-TAIL-01～02 |
| **CONTRACT-04** | DEFECT | **DEFECT** | R3/R4 完成 Object/Collection 关系日志与回滚接入 | 遗留项 R3-TAIL-01, R4-TAIL-01～05 |
| **CONTRACT-05** | DEFECT | **DEFECT** | R3 完成约束操作 Layer 3 收敛 | 外部非托管约束边界仍存 Tail 项 |
| **CONTRACT-06** | VERIFIED | **VERIFIED** | 无退化，快照、指纹与 FAILED-A 稳定通过 | 无 |
| **CONTRACT-07** | VERIFIED | **VERIFIED** | 无退化，会话隔离与解除授权稳定通过 | 无 |
| **CONTRACT-08** | DEFECT | **DEFECT** | R1/R5 实现了 CleanupOutcome 与数据块清理记录 | 缺少受保护只读数据块删除的异常分支穷尽 |
| **CONTRACT-09** | DEFECT | **DEFECT** | R5 实现了 Coordinator 独占状态决策权与注销权 | 待历史前序遗留项整体关闭后方可结项 |
| **CONTRACT-10** | UNVERIFIED | **DEFECT** | **状态转移**：由 UNVERIFIED 确认为 **DEFECT** | `test_task10b_wbc_failure_contract.py` 暴露 4 项断言失败 (02, 03, 04, 06) |
| **CONTRACT-11** | VERIFIED | **VERIFIED** | 无退化，左右双臂 Reset 共同事务稳定通过 | 无 |
| **CONTRACT-12** | DEFECT | **DEFECT** | 历史范围维持，未作越权改动 | 零引用未授权数据块保护合同待后续批次解决 |

---

## 3. CONTRACT-10 状态转移详细说明

在 TASK 10-B-14 审计中，CONTRACT-10 标记为 `UNVERIFIED`，原因在于当时缺少针对 WholeBodyController 与 Arm IK 单帧交互边界的专项故障注入测试。

在 Round 6/6 中，编写并执行了 `tests/test_task10b_wbc_failure_contract.py`：
- `CONTRACT10-01`：验证正常双臂反馈（PASS）；
- `CONTRACT10-02`：验证 CLEANUP_PENDING 准入拒绝时的 WBC 状态保护（**FAIL**，Root 位置在拒绝前已被写入且未回退）；
- `CONTRACT10-03`：验证 FAILED 墓碑隔离时的 WBC 状态保护（**FAIL**，Root 位置在抛出隔离异常前已被写入且未回退）；
- `CONTRACT10-04`：验证 Arm IK 自身回滚与 WBC 协调状态（**FAIL**，Arm IK 自身恢复但 WBC Root 残留已写入位置）；
- `CONTRACT10-05`：验证超范围不可达目标的真实反馈（PASS，真实反馈 `is_reachable=False`，无截断伪报）；
- `CONTRACT10-06`：验证双臂执行中后手失败时的整帧原子性（**FAIL**，左手保持 influence=1.0 提交，右手失败，造成半边不对称提交）。

因此，真实代码证据确凿地证明 CONTRACT-10 存在系统性缺陷。状态由 `UNVERIFIED` 明确转为 **DEFECT**，并忠实记录于 `deferred_observations.md`，不掩盖、不修改生产代码、不放宽测试断言。
