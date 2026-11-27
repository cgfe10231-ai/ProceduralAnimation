# HANDOFF — 当前项目交接卡片

> 核验日期：2026-11-27；Task 11 已验收生产基线：`added88a7e27eaaa6d1644473d560c5dcf45bc80`，联合验收证据提交 `07aec5d8d35e5d77ff956f160840d1c2491b770e`，收归合入自 `task/11`；10-D 历史生产基线 `824c52ec73f86aa3d08245a58297118cb4a9f110` / `7f14ff722caecadec555194cc7d08f454c94c6c8`；10-C 历史合入 `f2501ddc7d610d554d1e813b13564ea56ce2b51a`；10-B 历史合入 `c45a40cbd8bfffb0447ee73bd18bccff85d6f37e`。
> 本文件是摘要，不授予任务准入；须以 `PROJECT_STATE.md`、`ARCHITECTURE_SYNC.md`、`OPEN_FINDINGS.md` 及 Git 实况核对。

## 当前交接状态
- **当前节点：Task 11（`11-A` + `11-B`）FootLock 已完成验收并合入 `master`；下一工程节点为 `Task 12-A`（WBC 单帧写入与失败原子性独立审计）。**
- **工作性质**：Task 11 正式结项与主干合并。无剩余 OPEN 历史 Finding（原 16 项历史 Finding **16/16 全部关闭**）；禁止自行开始 Task 12 编码；不得宣称 PKG-5 已整体完成；**Phase 7B / Phase 7C** 保持 `NOT AUTHORIZED`。
- **Task 11（`11-A` + `11-B`）**：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`（`FIND-R3-03`、`FIND-R3-04` 正式关闭）。
- Task 10（`10-A` / `10-B` / `10-C` / `10-D`）：`COMPLETED — OWNER ACCEPTED — MERGED TO MASTER`。

| 子节点 | 工作与实现边界 | 状态 |
|---|---|---|
| 11-A (`FIND-R3-03`) | `src/rig/ik.py` 定义 7 键常量 `FOOT_LOCK_METADATA_KEYS`，`setup_leg_ik()` / `reset_leg_ik()` / `unlock_foot_contact()` 清理 7 项元数据；`_snapshot_leg_rig_state()` / `_rollback_leg_rig_state()` 脱离 `IDPropertyArray` 完整恢复/校验存在性与值；`lock_foot_contact()` 先全量重建 7 键再发布 `is_locked=True` | 已通过独立源码审计及 A01–A19 验收 |
| 11-B (`FIND-R3-04`) | `get_leg_ik_state(..., *, update_scene: bool = True)` 增加无刷新纯读取路径；`get_foot_support_state()` 收敛为零副作用纯查询（缺失控制器/快照拒绝，解锁态不消费不清理残留）；`evaluate_foot_support()` 保留主动维护并在写入前拒绝不完整锁定，随后委托 `get_foot_support_state()`；`unlock_foot_contact()` 在 Phase B 事务内显式执行预弯与刷新；`src/scene/playground_character_assembly.py` Stage D 改用纯查询 | 已通过独立源码审计（含 BUG-01）及 B01–B20 验收 |

## Task 11 联合专项与最终回归证据（`docs/evidence/11/unified_verification/`）
| 范围 | 实测结果 | 证据路径与说明 |
|---|---|---|
| A 组 / B 组与连续生产链 | **A01–A19 `19/19`**、**B01–B20 `20/20`**（B08 37 子项全过）、联合专项 **`38/38`**；五动作 542 帧、支撑转换 44 次、锁脚控制器最大漂移 `0`；两份新测试场景独立重开 `PASS` | `results.json`、`execution_manifest.json`、`verify_footlock_contract.py`、`verify_footlock_reopen.py` |
| 历史专项复验 | WBC 失败合同 `CONTRACT10-01..06` `6/6`；`09-B-4` `27/27`；地面高度 `20/20`；初始化/重置 `6/6`；`legacy_foot_contact` `PASS`（原 `.blend` SHA-256 未变） | `wbc_failure_contract_*.log`、`legacy_foot_contact/`、`regression_physics/` |
| `quick` 回归 (`--fail-fast`) | **19/19 PASS** (`rc=0`, 16 PASSED + 3 AUTOMATED_PASS, 78.26s) | `regression_quick/test_report.json` |
| `physics` 回归 (`--fail-fast`) | **27/27 PASS** (`rc=0`, 24 PASSED + 3 AUTOMATED_PASS, 136.26s) | `regression_physics/test_report.json` |
| `motion` 回归 (`--fail-fast`) | **12/12 PASS** (`rc=0`, 6 PASSED + 6 AUTOMATED_PASS, 60.59s) | `regression_motion/test_report.json` |
| `full` 回归 (`--fail-fast`) | **42/42 PASS** (`rc=0`, 33 PASSED + 9 AUTOMATED_PASS, 199.32s) | `regression_full/test_report.json`（`AUTOMATED_PASS` 不登记为人工视觉验收） |

## 10-B / 10-C / 10-D 既有归档证据
- 10-D 人工视觉验收（2026-11-27）与最终回归：`docs/evidence/10-d/final_acceptance/`、`docs/evidence/10-d/10-d-5/centralized_verification/`（仅登记 `output/task10d_centralized_whole_body.blend` 与 `output/task10d_running_whole_body.blend`）。
- 10-B 六层事务回归归档：`docs/evidence/10b_sixlayer_split/regression/`（WBC 独立合同已在 Task 11 复验 6/6 PASS）；10-C 历史归档：`docs/evidence/10-c-integration/`。

## 权限与纪律
- 架构合同 `CONTRACT-01..12` 定义不动，21 项冻结主账定义不动；原 16 项历史 Finding 已 **16/16 全部关闭**（其余 14 项历史结论保持不变）。
- Task 12 未完成前不得宣称 PKG-5 已整体完成；不得提前开启 Phase 7B / Phase 7C；不得将 `AUTOMATED_PASS` 登记为人工视觉验收。
- Antigravity 对 Markdown 默认只读；完成本轮结项交付后恢复默认只读并停止，等待 ChatGPT 独立核验及 Task 12 审计。
